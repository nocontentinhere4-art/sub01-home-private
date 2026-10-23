"""Bridge from live_server.py to the Vagon PC: start the machine when it is off, then open a link on it.

Off unless enabled(). A chat link is refused at once unless vagon_pc.is_plain_link accepts it (a public http or https
name) and the caps allow it. Accepted links are queued and opened by one worker thread, in arrival order, with at most
MAX_QUEUED waiting behind the one in progress. The caps are the bridge's own estimates, kept in this process and reset
by a restart:

- links per hour, all viewers together (VAGON_LINKS_PER_HOUR, default 20), and per viewer when the caller passes the
  viewer's key (VAGON_LINKS_PER_VIEWER_PER_HOUR, default 6);
- machine starts per day (VAGON_STARTS_PER_DAY, default 4), counted before each start;
- machine time per day (VAGON_ON_MINUTES_PER_DAY, default 120): each use keeps the machine on for AUTO_STOP_S after it,
  and overlapping windows count once. Vagon's own metering is not read; the estimate assumes the idle stop works, which
  is not verified yet (docs/design/vagon-pc/README.md).

Nothing retries a start, a link or a refused call, HTTP 429 included, with one exception: the idle stop. It is set after
every start, with one retry, and when the retry fails too the machine is asked to stop. status() shows the last step
this process took, not a live reading of the machine. Logs carry the action, the link's host (sanitised) and the
outcome, never the link itself, a credential or a signature.
"""
import logging
import os
import re
import threading
import time
import urllib.parse
from collections import deque

import vagon_pc

log = logging.getLogger("vagon_bridge")


def _int_env(name, default):
    """A whole number from the environment, or the default. A value that is not a whole number is logged and ignored."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        log.warning("%s is not a whole number; using %d", name, default)
        return default


AUTO_STOP_S = 900                                   # idle seconds before the machine stops (a vendor step)
AUTO_STOP_RETRY_S = 5.0                             # the pause before the one retry of the idle stop
MAX_QUEUED = 3                                      # links waiting behind the one in progress
HOST_MAX = 80                                       # the longest host that a log line carries
HOUR_S, DAY_S = 3600.0, 86400.0
LINKS_PER_HOUR = _int_env("VAGON_LINKS_PER_HOUR", 20)                  # all viewers together
LINKS_PER_VIEWER_PER_HOUR = _int_env("VAGON_LINKS_PER_VIEWER_PER_HOUR", 6)
STARTS_PER_DAY = _int_env("VAGON_STARTS_PER_DAY", 4)                   # a start is a billed action
ON_MINUTES_PER_DAY = _int_env("VAGON_ON_MINUTES_PER_DAY", 120)         # machine time, estimated

_mu = threading.Lock()                              # guards the state below, and the budget inside _status
_queue = deque()                                    # (url, host) waiting, in arrival order
_worker_running = False                             # True from the thread start until the worker finds the queue empty
_status = {"state": "off", "detail": ""}            # the last step; the caps' counters are kept here too (_budget)
_last_refusal = ""
_probe = {"state": "not run", "detail": ""}
_probe_done = False
_auto_stop = {"state": "not run", "detail": ""}
_auto_stop_lock = threading.Lock()
_auto_stop_done = False                             # set by the first attempt, whatever its outcome


class _Budget:
    """The counters the caps read. Created on first use inside _status (see _budget), so resetting the bridge's state
    resets the caps with it."""

    def __init__(self):
        self.links = deque()                        # monotonic times of accepted links (the last hour)
        self.viewers = {}                           # viewer key -> deque of accepted times (the last hour)
        self.starts = deque()                       # monotonic times of machine starts (the last day)
        self.on = deque()                           # (monotonic time, seconds) of machine time counted (the last day)
        self.covered = float("-inf")                # the machine is counted as on until this instant


class _Refused(Exception):
    """One queued open stopped by a cap or a check. Its text is for the owner's status and carries no link."""


def enabled():
    """True only when VAGON_PC_ENABLED is '1' and VAGON_MACHINE_ID, VAGON_API_KEY and VAGON_API_SECRET are set.
    Presence only: no value is read out or logged."""
    env = os.environ
    return (env.get("VAGON_PC_ENABLED") == "1" and bool(env.get("VAGON_MACHINE_ID"))
            and bool(env.get("VAGON_API_KEY")) and bool(env.get("VAGON_API_SECRET")))


def status():
    """{'enabled', 'state', 'detail', 'waiting', 'last_refusal', 'probe', 'auto_stop', 'budget'}. 'state' is the last
    step this process took ('off' before any); 'waiting' counts the links queued behind it; 'budget' is what the caps
    count now, with their limits."""
    with _mu:
        now = time.monotonic()
        b = _status.get("budget") or _Budget()
        budget = {"links_this_hour": len(_recent(b.links, now, HOUR_S)),
                  "starts_today": len(_recent(b.starts, now, DAY_S)),
                  "on_minutes_today": round(_on_minutes(b, now), 1),
                  "limits": {"links_per_hour": LINKS_PER_HOUR, "links_per_viewer_per_hour": LINKS_PER_VIEWER_PER_HOUR,
                             "starts_per_day": STARTS_PER_DAY, "on_minutes_per_day": ON_MINUTES_PER_DAY}}
        return {"enabled": enabled(), "state": _status["state"], "detail": _status["detail"], "waiting": len(_queue),
                "last_refusal": _last_refusal, "probe": dict(_probe), "auto_stop": dict(_auto_stop), "budget": budget}


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
    """Sets the machine's idle stop once per process, at startup; every start sets it again (see _start). One retry
    after a failure, and a failure after the retry is kept in status(). It makes HTTP calls: keep it off the loop."""
    global _auto_stop_done
    if not enabled():
        return
    with _auto_stop_lock:
        if _auto_stop_done:
            return
        _auto_stop_done = True
        try:
            _idle_stop(os.environ["VAGON_MACHINE_ID"])
            _set_auto_stop("ok", f"{AUTO_STOP_S} s")
            log.info("vagon auto-stop %d s outcome=ok", AUTO_STOP_S)
        except Exception as e:
            detail = _describe(e)
            _set_auto_stop("error", detail)
            log.warning("vagon auto-stop outcome=error: %s", detail)


def submit_link(url, viewer=""):
    """Queues one link to open on the PC, or refuses it at once. Returns (True, '') when it is queued, or (False, code):
    'off' (the bridge is disabled), 'invalid' (not a public http or https link), 'ontime', 'hour' or 'viewer' (a cap;
    the reason is in status()['last_refusal']), 'full' (MAX_QUEUED links already wait) or 'thread' (no worker thread
    could start). viewer is the chat key of the sender, when the caller has one. A refused link never reaches the PC.
    Never raises, and never waits on the network."""
    global _worker_running, _last_refusal
    if not enabled():
        return False, "off"
    if not vagon_pc.is_plain_link(url):
        log.info("vagon link refused: not a public http or https link")
        _set_refusal("not a public http or https link")
        return False, "invalid"
    host = _host(url)
    now = time.monotonic()
    with _mu:
        why, code = _link_reason(viewer, now)
        if not why and len(_queue) >= MAX_QUEUED:
            why, code = f"{MAX_QUEUED} links already wait for the PC", "full"
        if why:
            _last_refusal = f"link for {host} not taken: {why}"
            log.info("vagon link refused host=%s code=%s", host, code)
            return False, code
        _queue.append((url, host))
        if not _worker_running:
            _worker_running = True
            try:
                threading.Thread(target=_work, name="vagon-open", daemon=True).start()
            except Exception as e:                  # no thread: take the link back out and say why
                detail = _describe(e)
                _worker_running = False
                _queue.pop()
                _status.update(state="error", detail=detail)
                log.warning("vagon worker not started: %s", detail)
                return False, "thread"
        _record_link(viewer, now)
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
    except BaseException:                           # a dying worker clears the flag, or no later link starts one
        with _mu:
            _worker_running = False
        raise


def _open(url, host):
    """One queued open: check the day's machine time, start the machine if it is off, wait until it is ready, then open
    the link. A cap that stops it is recorded as 'refused'; any other failure as 'error'. Never raises."""
    try:
        machine = os.environ["VAGON_MACHINE_ID"]
        with _mu:
            why = _ontime_reason(time.monotonic())
        if why:
            raise _Refused(why)
        _ensure_ready(machine, host)
        _set("opening", "opening a link on " + host)
        with _mu:
            _count_on(_budget(), time.monotonic())
        vagon_pc.open_url(machine, url)
        _set("ready", "opened a link on " + host)
        log.info("vagon open host=%s outcome=ok", host)
    except _Refused as e:
        _set("refused", str(e))
        log.info("vagon open host=%s refused: %s", host, e)
    except Exception as e:
        detail = _describe(e)
        _set("error", detail)
        log.warning("vagon open host=%s outcome=error: %s", host, detail)


def _ensure_ready(machine, host):
    """Makes the machine ready for a link. It starts only when it reports an off state, so a machine that is starting
    or whose value is unknown is never started again. A list with no status at all is an error: nothing is started on
    a reading that is not there."""
    st = vagon_pc.status(machine)
    if st in vagon_pc.READY_STATUSES:
        return
    if st is None:
        raise vagon_pc.VagonError("GET /machines gives the machine no status, so it was not started")
    if st in vagon_pc.OFF_STATUSES:
        _start(machine, host, st)
    _set("starting", "waiting for the machine to be ready")
    vagon_pc.wait_ready(machine)                    # bounded by its own max_wait_s


def _start(machine, host, st):
    """Starts an off machine. The start is counted against the day's starts first, then made (one try: a start is
    billed), then given its idle stop. If the idle stop cannot be set, the machine is asked to stop, so that it does not
    run unattended (SUB01-S07)."""
    with _mu:
        b = _budget()
        now = time.monotonic()
        starts = _recent(b.starts, now, DAY_S)
        if len(starts) >= STARTS_PER_DAY:
            raise _Refused(f"the machine was started {len(starts)} times today (limit {STARTS_PER_DAY}); not started")
        b.starts.append(now)
        _count_on(b, now)
    _set("starting", "starting the machine")
    log.info("vagon start host=%s from=%s", host, vagon_pc.safe_token(st))
    vagon_pc.start_machine(machine)
    try:
        _idle_stop(machine)                         # on every start, not only at boot
    except Exception as e:
        _stop_quietly(machine)
        raise vagon_pc.VagonError("the idle stop could not be set, so the machine was asked to stop: "
                                  + _describe(e)) from None


def _idle_stop(machine):
    """Sets the idle stop: one try, then one retry after AUTO_STOP_RETRY_S. The error of the retry is raised."""
    try:
        vagon_pc.set_auto_stop(machine, AUTO_STOP_S)
        return
    except Exception as e:
        log.info("vagon auto-stop: first try failed (%s); retrying once", _describe(e))
    time.sleep(AUTO_STOP_RETRY_S)
    vagon_pc.set_auto_stop(machine, AUTO_STOP_S)


def _stop_quietly(machine):
    try:
        vagon_pc.stop_machine(machine)
    except Exception as e:
        log.warning("vagon stop after a failed idle stop did not go through: %s", _describe(e))


def _recent(q, now, span):
    """Drops the times older than span seconds from the front of q, and returns q. Call with _mu held."""
    while q and now - q[0] > span:
        q.popleft()
    return q


def _budget():
    """The budget. It lives in _status on purpose: a fresh _status (a restart, or a test that resets the bridge's state)
    starts with a fresh budget. Call with _mu held."""
    return _status.setdefault("budget", _Budget())


def _on_minutes(b, now):
    """The machine minutes counted in the last day. Call with _mu held."""
    while b.on and now - b.on[0][0] > DAY_S:
        b.on.popleft()
    return sum(seconds for _, seconds in b.on) / 60.0


def _count_on(b, now):
    """Counts the machine time that one use keeps the machine on: AUTO_STOP_S after it, less what is already counted.
    Call with _mu held."""
    end = now + AUTO_STOP_S
    added = end - max(b.covered, now)
    if added > 0:
        b.on.append((now, added))
        b.covered = end


def _ontime_reason(now):
    """'' while the day's machine time is under its limit, else the reason. Call with _mu held."""
    used = _on_minutes(_budget(), now)
    if used < ON_MINUTES_PER_DAY:
        return ""
    return (f"the PC's time for the day is used up (about {used:.0f} minutes counted against {ON_MINUTES_PER_DAY}; "
            "an estimate)")


def _link_reason(viewer, now):
    """(reason, code) for one new link, or ('', '') when the caps allow it. Counts nothing. Call with _mu held."""
    b = _budget()
    why = _ontime_reason(now)
    if why:
        return why, "ontime"
    if len(_recent(b.links, now, HOUR_S)) >= LINKS_PER_HOUR:
        return f"the link limit for this hour is used up ({LINKS_PER_HOUR} links)", "hour"
    if viewer and len(_recent(b.viewers.get(viewer, deque()), now, HOUR_S)) >= LINKS_PER_VIEWER_PER_HOUR:
        return f"this viewer's link limit for this hour is used up ({LINKS_PER_VIEWER_PER_HOUR} links)", "viewer"
    return "", ""


def _record_link(viewer, now):
    """Counts one accepted link against the hour and against its viewer. Call with _mu held."""
    b = _budget()
    b.links.append(now)
    if viewer:
        b.viewers.setdefault(viewer, deque()).append(now)
    for key in [k for k, q in b.viewers.items() if not _recent(q, now, HOUR_S)]:
        del b.viewers[key]                          # a viewer with nothing in the last hour is dropped


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
    """The link's host for a log line: ASCII letters, digits, dots and hyphens; any other character is shown as '?'.
    At most HOST_MAX characters. '?' when there is no host."""
    try:
        host = urllib.parse.urlsplit(url).hostname or ""
    except (ValueError, AttributeError, TypeError):
        return "?"
    return re.sub(r"[^A-Za-z0-9.-]", "?", host)[:HOST_MAX] or "?"


def _describe(e):
    """Short exception text for status and logs. The credentials in the environment, the Authorization header and every
    link are cut out here, so no message can carry them out of this module."""
    text = f"{type(e).__name__}: {e}"
    for name in ("VAGON_API_KEY", "VAGON_API_SECRET"):
        value = os.environ.get(name, "")
        if value:
            text = text.replace(value, "<redacted>")
    return re.sub(r"https?://\S+|HMAC \S+", "<redacted>", text)[:160]
