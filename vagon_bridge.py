"""Bridge from live_server.py to the Vagon PC: start the machine when it is off, then open a link on it.

Off unless enabled(). Links are queued and opened by one worker thread, in arrival order. Up to MAX_QUEUED wait behind
the one in progress; a link that finds the queue full is dropped, the newest one, with a reason. Nothing retries, HTTP
429 included. probe() lists the machines once at startup, so a bad key or machine id shows in the log and in status().
status() shows the last step this process took, not a live reading of the machine. Logs carry the action, the link's
host and the outcome: never the link itself, a credential or a signature.
"""
import logging
import os
import re
import threading
import urllib.parse
from collections import deque

import vagon_pc

log = logging.getLogger("vagon_bridge")
AUTO_STOP_S = 900
MAX_QUEUED = 3                                   # links waiting behind the one in progress
HOST_MAX = 100

_mu = threading.Lock()                           # guards the state below
_queue = deque()                                 # (url, host) waiting, in arrival order
_worker_running = False                          # True from the thread start until the worker finds the queue empty
_status = {"state": "off", "detail": ""}         # the last step this process took
_last_refusal = ""
_probe = {"state": "not run", "detail": ""}
_probe_done = False
_auto_stop = {"state": "not run", "detail": ""}
_auto_stop_lock = threading.Lock()
_auto_stop_done = False                          # set by the first attempt, whatever its outcome


def enabled():
    """True only when VAGON_PC_ENABLED is '1' and VAGON_MACHINE_ID, VAGON_API_KEY and VAGON_API_SECRET are set.
    Presence only: no value is read out or logged."""
    env = os.environ
    return (env.get("VAGON_PC_ENABLED") == "1" and bool(env.get("VAGON_MACHINE_ID"))
            and bool(env.get("VAGON_API_KEY")) and bool(env.get("VAGON_API_SECRET")))


def status():
    """{'enabled', 'state', 'detail', 'waiting', 'last_refusal', 'probe', 'auto_stop'}. 'state' is the last step this
    process took ('off' before any); 'waiting' counts the links queued behind it."""
    with _mu:
        return {"enabled": enabled(), **_status, "waiting": len(_queue), "last_refusal": _last_refusal,
                "probe": dict(_probe), "auto_stop": dict(_auto_stop)}


def probe():
    """Lists the machines once, at startup: one GET /machines, no retry. It checks that the key works and that
    VAGON_MACHINE_ID is listed, and logs the machine's status string. A failure is logged at ERROR and kept in status().
    Never raises. Does nothing when the bridge is off, and only the first call does anything."""
    global _probe_done
    if not enabled():
        return
    with _mu:
        if _probe_done:
            return
        _probe_done = True
    machine_id = os.environ["VAGON_MACHINE_ID"]
    try:
        machines = vagon_pc.list_machines()
        mine = next((m for m in machines if m.get("id") == machine_id), None)
        if mine is None:
            _set_probe("machine_missing", f"VAGON_MACHINE_ID is not among the {len(machines)} machines listed")
            log.error("vagon probe outcome=machine-missing: VAGON_MACHINE_ID is not in GET /machines (%d listed)",
                      len(machines))
            return
        st = vagon_pc.safe_token(vagon_pc.status_of(mine))
        _set_probe("ok", f"machine listed, status {st}")
        log.info("vagon probe outcome=ok status=%s", st)
    except Exception as e:
        detail = _describe(e)
        _set_probe("error", detail)
        log.error("vagon probe outcome=error: %s", detail)


def configure_auto_stop():
    """Sets the machine's auto-stop to 900 s of idle time, once per process. A failure is kept in status() and is not
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
            _set_auto_stop("ok", f"{AUTO_STOP_S} s")
            log.info("vagon auto-stop %d s outcome=ok", AUTO_STOP_S)
        except Exception as e:
            detail = _describe(e)
            _set_auto_stop("error", detail)
            log.warning("vagon auto-stop outcome=error: %s", detail)


def submit_link(url):
    """Queues one link to open on the PC. Returns (True, '') when it is queued, or (False, reason) when it is not:
    'off' (the bridge is disabled), 'invalid' (not a plain http or https link), 'full' (MAX_QUEUED links already wait,
    so this newest one is dropped) or 'thread' (no worker thread could start). Never raises and never waits on the
    network."""
    global _worker_running, _last_refusal
    if not enabled():
        return False, "off"
    if not vagon_pc.is_plain_link(url):
        log.info("vagon link refused: not a plain http or https link without spaces")
        _set_refusal("not a plain http or https link without spaces")
        return False, "invalid"
    host = _host(url)
    with _mu:
        if len(_queue) >= MAX_QUEUED:
            _last_refusal = f"newest link dropped: {MAX_QUEUED} already wait for the PC (host {host})"
            log.warning("vagon queue full, newest dropped host=%s waiting=%d", host, len(_queue))
            return False, "full"
        _queue.append((url, host))
        if not _worker_running:
            _worker_running = True
            try:
                threading.Thread(target=_work, name="vagon-open", daemon=True).start()
            except Exception as e:                # no thread: take the link back out and say why
                detail = _describe(e)
                _worker_running = False
                _queue.pop()
                _status.update(state="error", detail=detail)
                log.warning("vagon worker not started: %s", detail)
                return False, "thread"
        waiting = len(_queue)
    log.info("vagon queued host=%s waiting=%d", host, waiting)
    return True, ""


def open_url_async(url):
    """The earlier entry point, kept so live_server.py works unchanged: True when the link was queued, else False."""
    return submit_link(url)[0]


def _work():
    """Thread body: opens the queued links in arrival order, one at a time, and ends when the queue is empty."""
    global _worker_running
    try:
        while True:
            with _mu:
                if not _queue:
                    _worker_running = False
                    return
                url, host = _queue.popleft()
            _open(url, host)
    except BaseException:                         # a dying worker must clear the flag, or no later link would start one
        with _mu:
            _worker_running = False
        raise


def _open(url, host):
    """One queued open: start the machine if it is off, wait until it is ready, then open the link. Never raises."""
    try:
        machine = os.environ["VAGON_MACHINE_ID"]
        _ensure_ready(machine, host)
        _set("opening", "opening a link on " + host)
        vagon_pc.open_url(machine, url)
        _set("ready", "opened a link on " + host)
        log.info("vagon open host=%s outcome=ok", host)
    except Exception as e:
        detail = _describe(e)
        _set("error", detail)
        log.warning("vagon open host=%s outcome=error: %s", host, detail)


def _ensure_ready(machine, host):
    """Starts the machine only when it reports an off state, so a machine that is starting, or whose value is unknown,
    is never started again. A list that gives no status at all is an error: nothing is started on a reading that is
    not there."""
    st = vagon_pc.status(machine)
    if st in vagon_pc.READY_STATUSES:
        return
    if st is None:
        raise vagon_pc.VagonError("GET /machines gives the machine no status, so it was not started")
    if st in vagon_pc.OFF_STATUSES:
        _set("starting", "starting the machine")
        log.info("vagon start host=%s from=%s", host, vagon_pc.safe_token(st))
        vagon_pc.start_machine(machine)           # once per link, no retry
    _set("starting", "waiting for the machine to be ready")
    vagon_pc.wait_ready(machine)                  # bounded by its own max_wait_s


def _set(state, detail):
    with _mu:
        _status["state"], _status["detail"] = state, detail


def _set_refusal(reason):
    global _last_refusal
    with _mu:
        _last_refusal = reason


def _set_probe(state, detail):
    with _mu:
        _probe.update(state=state, detail=detail)


def _set_auto_stop(state, detail):
    with _mu:
        _auto_stop.update(state=state, detail=detail)


def _host(url):
    """The link's host name only: the one part of a link that a log line may show."""
    try:
        host = urllib.parse.urlsplit(url).hostname or "?"
    except ValueError:
        host = "?"
    return host[:HOST_MAX]


def _describe(e):
    """Short exception text for status and logs. The credentials in the environment, the Authorization header and every
    link are cut out here, so no message can carry them out of this module."""
    text = f"{type(e).__name__}: {e}"
    for name in ("VAGON_API_KEY", "VAGON_API_SECRET"):
        value = os.environ.get(name, "")
        if value:
            text = text.replace(value, "<redacted>")
    return re.sub(r"https?://\S+|HMAC \S+", "<redacted>", text)[:160]
