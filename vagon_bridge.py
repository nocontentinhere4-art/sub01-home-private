"""Bridge from live_server.py to the Vagon PC: start the machine when it is not ready, then open one link on it.

Off unless enabled(). One open runs at a time, in a daemon thread that ends when its work ends. Nothing retries, HTTP
429 included. status() shows the last step this process took, not a live reading of the machine. Logs carry only the
action, the link's host and the outcome.
"""
import logging
import os
import re
import threading
import urllib.parse

import vagon_pc

log = logging.getLogger("vagon_bridge")
AUTO_STOP_S = 900
_busy = threading.Lock()      # held from open_url_async until its thread ends: one open, so one start, at a time
_mu = threading.Lock()        # guards _status
_status = {"state": "off", "detail": ""}
_auto_stop_lock = threading.Lock()
_auto_stop_done = False       # set by the first attempt, whatever its outcome


def enabled():
    """True only when VAGON_PC_ENABLED is '1' and VAGON_MACHINE_ID, VAGON_API_KEY and VAGON_API_SECRET are set.
    Presence only: no value is read out or logged."""
    env = os.environ
    return (env.get("VAGON_PC_ENABLED") == "1" and bool(env.get("VAGON_MACHINE_ID"))
            and bool(env.get("VAGON_API_KEY")) and bool(env.get("VAGON_API_SECRET")))


def status():
    """{'enabled', 'state', 'detail'}: the last step this process took, 'off' before any."""
    with _mu:
        return {"enabled": enabled(), **_status}


def open_url_async(url):
    """Starts one background open of `url` on the PC. True when a thread was started, even if the link is then refused
    (the refusal goes into status()). False when the bridge is off or another open is still running. Never raises."""
    if not enabled() or not _busy.acquire(blocking=False):
        return False
    try:
        threading.Thread(target=_open, args=(url,), name="vagon-open", daemon=True).start()
        return True
    except Exception as e:    # no thread was started, so release the lock here
        _busy.release()
        _set("error", _describe(e))
        return False


def configure_auto_stop():
    """Sets the machine's auto-stop to 900 s of idle time, once per process. A failure goes into status() and is not
    retried. It makes one HTTP call, so keep it off the event loop."""
    global _auto_stop_done
    if not enabled():
        return
    with _auto_stop_lock:
        if _auto_stop_done:
            return
        _auto_stop_done = True
        try:
            vagon_pc.set_auto_stop(os.environ["VAGON_MACHINE_ID"], AUTO_STOP_S)
            log.info("vagon auto-stop %d s outcome=ok", AUTO_STOP_S)
        except Exception as e:
            detail = _describe(e)
            _set("error", "auto-stop: " + detail)
            log.warning("vagon auto-stop outcome=error: %s", detail)


def _open(url):
    """Thread body: refuse a bad link, start the machine if needed, open the link; always releases the lock."""
    host = "?"
    try:
        host = urllib.parse.urlsplit(url).hostname or "?"
        if len(url) > 2000 or not vagon_pc.WEB_LINK.fullmatch(url):   # refused before the machine is touched
            raise ValueError("only plain http or https links without spaces")
        machine = os.environ["VAGON_MACHINE_ID"]
        if vagon_pc.status(machine) != "ready":
            _set("starting", "starting the machine")
            log.info("vagon start host=%s", host)
            vagon_pc.start_machine(machine)   # once per open, no retry
            vagon_pc.wait_ready(machine)      # bounded by its max_wait_s
        _set("opening", "opening a link on " + host)
        vagon_pc.open_url(machine, url)
        _set("ready", "opened a link on " + host)
        log.info("vagon open host=%s outcome=ok", host)
    except Exception as e:
        detail = _describe(e)
        _set("error", detail)
        log.warning("vagon open host=%s outcome=error: %s", host, detail)
    finally:
        _busy.release()


def _set(state, detail):
    with _mu:
        _status["state"], _status["detail"] = state, detail


def _describe(e):
    """Short exception text for status and logs. Links and the Authorization header are cut out here; the messages
    from vagon_pc carry no credentials."""
    return re.sub(r"https?://\S+|HMAC \S+", "<redacted>", f"{type(e).__name__}: {e}")[:160]
