"""Offline checks for the Vagon bridge: vagon_pc is faked, so no network and no credentials. Safe to run anywhere."""
import logging
import threading
import time
import types
from collections import deque

import pytest

import vagon_bridge
import vagon_pc

ENV = {"VAGON_PC_ENABLED": "1", "VAGON_MACHINE_ID": "machine-test", "VAGON_API_KEY": "key-test",
       "VAGON_API_SECRET": "secret-test"}
URL = "https://example.com/page?q=1"
LINKS = [f"https://example.com/{letter}" for letter in "abcde"]


def _env(monkeypatch, env):
    for name in ENV:
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)


def _wait_idle(bridge, timeout=10.0):
    """Returns once the worker has emptied the queue and ended, so no thread outlives its test."""
    end = time.monotonic() + timeout
    while True:
        with bridge._mu:
            if not bridge._worker_running:
                return
        assert time.monotonic() < end, "the worker did not end"
        time.sleep(0.005)


class NoNetwork:
    def open(self, *args, **kwargs):
        raise AssertionError("a request was sent")


@pytest.fixture(autouse=True)
def no_real_vagon(monkeypatch):
    """Each test starts with the Vagon variables removed (a pod shell may export them) and with an opener that fails."""
    for name in ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(vagon_pc, "_OPENER", NoNetwork())


@pytest.fixture
def bridge(monkeypatch):
    monkeypatch.setattr(vagon_bridge, "_queue", deque())
    monkeypatch.setattr(vagon_bridge, "_worker_running", False)
    monkeypatch.setattr(vagon_bridge, "_status", {"state": "off", "detail": ""})   # the caps' budget lives in here
    monkeypatch.setattr(vagon_bridge, "_last_refusal", "")
    monkeypatch.setattr(vagon_bridge, "_probe", {"state": "not run", "detail": ""})
    monkeypatch.setattr(vagon_bridge, "_probe_done", False)
    monkeypatch.setattr(vagon_bridge, "_auto_stop", {"state": "not run", "detail": ""})
    monkeypatch.setattr(vagon_bridge, "_auto_stop_done", False)
    monkeypatch.setattr(vagon_bridge, "AUTO_STOP_RETRY_S", 0.0)
    for name, value in (("LINKS_PER_HOUR", 20), ("LINKS_PER_VIEWER_PER_HOUR", 6), ("STARTS_PER_DAY", 4),
                        ("ON_MINUTES_PER_DAY", 120)):          # fixed here, whatever the environment of this run says
        monkeypatch.setattr(vagon_bridge, name, value)
    _env(monkeypatch, ENV)
    unexpected = []   # a call the test did not fake is recorded here and fails the test, so none reaches the network
    for name in ("status", "start_machine", "wait_ready", "open_url", "set_auto_stop", "stop_machine", "list_machines"):
        monkeypatch.setattr(vagon_pc, name, lambda *a, _n=name, **k: unexpected.append(_n))
    yield vagon_bridge
    _wait_idle(vagon_bridge)
    assert unexpected == []


# --- switch, status and environment ---------------------------------------------------------------------------------

def test_enabled_needs_the_switch_and_all_three_values(monkeypatch):
    _env(monkeypatch, {})
    assert vagon_bridge.enabled() is False
    _env(monkeypatch, ENV)
    assert vagon_bridge.enabled() is True
    for name in ENV:
        _env(monkeypatch, {k: v for k, v in ENV.items() if k != name})
        assert vagon_bridge.enabled() is False, name
    for value in ("0", "true", ""):
        _env(monkeypatch, dict(ENV, VAGON_PC_ENABLED=value))
        assert vagon_bridge.enabled() is False, value


def test_a_disabled_bridge_starts_nothing(bridge, monkeypatch):
    _env(monkeypatch, {})
    assert bridge.submit_link(URL) == (False, "off")
    assert bridge.open_url_async(URL) is False
    bridge.probe()
    bridge.configure_auto_stop()
    st = bridge.status()
    assert st["enabled"] is False and st["state"] == "off" and st["waiting"] == 0
    assert st["probe"]["state"] == "not run" and st["auto_stop"]["state"] == "not run"


def test_the_caps_read_their_environment_overrides(monkeypatch, caplog):
    monkeypatch.setenv("VAGON_TEST_CAP", " 7 ")
    assert vagon_bridge._int_env("VAGON_TEST_CAP", 3) == 7
    monkeypatch.setenv("VAGON_TEST_CAP", "-4")
    assert vagon_bridge._int_env("VAGON_TEST_CAP", 3) == 0           # a negative cap blocks, it does not lift the limit
    monkeypatch.setenv("VAGON_TEST_CAP", "x")
    with caplog.at_level(logging.WARNING, logger="vagon_bridge"):
        assert vagon_bridge._int_env("VAGON_TEST_CAP", 3) == 3
    assert "VAGON_TEST_CAP is not a whole number" in caplog.text
    monkeypatch.delenv("VAGON_TEST_CAP")
    assert vagon_bridge._int_env("VAGON_TEST_CAP", 3) == 3


# --- starting and opening ---------------------------------------------------------------------------------------------

def test_an_off_machine_is_started_once_then_armed_then_opened(bridge, monkeypatch):
    calls = []
    monkeypatch.setattr(vagon_pc, "status", lambda m: calls.append("status") or "off")
    monkeypatch.setattr(vagon_pc, "start_machine", lambda m: calls.append("start"))
    monkeypatch.setattr(vagon_pc, "set_auto_stop", lambda m, s: calls.append(("auto_stop", s)))
    monkeypatch.setattr(vagon_pc, "wait_ready", lambda m, *a, **k: calls.append("wait"))
    monkeypatch.setattr(vagon_pc, "open_url", lambda m, u: calls.append(("open", m, u)))
    assert bridge.submit_link(URL) == (True, "")
    _wait_idle(bridge)
    assert calls == ["status", "start", ("auto_stop", 900), "wait", ("open", "machine-test", URL)]
    assert bridge.status()["state"] == "ready"


@pytest.mark.parametrize("value", vagon_pc.READY_STATUSES)
def test_a_ready_machine_is_opened_without_a_start(bridge, monkeypatch, value):
    calls = []
    monkeypatch.setattr(vagon_pc, "status", lambda m: value)
    monkeypatch.setattr(vagon_pc, "open_url", lambda m, u: calls.append("open"))
    assert bridge.submit_link(URL) == (True, "")
    _wait_idle(bridge)
    assert calls == ["open"]


@pytest.mark.parametrize("value", ["turning_on", "creating", "paused-by-vendor", "turning_off"])
def test_a_machine_that_is_not_off_is_waited_for_and_never_started(bridge, monkeypatch, value):
    calls = []
    monkeypatch.setattr(vagon_pc, "status", lambda m: value)
    monkeypatch.setattr(vagon_pc, "start_machine", lambda m: calls.append("start"))
    monkeypatch.setattr(vagon_pc, "wait_ready", lambda m, *a, **k: calls.append("wait"))
    monkeypatch.setattr(vagon_pc, "open_url", lambda m, u: calls.append("open"))
    bridge.submit_link(URL)
    _wait_idle(bridge)
    assert calls == ["wait", "open"]


def test_a_machine_with_no_status_is_not_started(bridge, monkeypatch):
    calls = []
    monkeypatch.setattr(vagon_pc, "status", lambda m: None)
    monkeypatch.setattr(vagon_pc, "start_machine", lambda m: calls.append("start"))
    bridge.submit_link(URL)
    _wait_idle(bridge)
    st = bridge.status()
    assert calls == [] and st["state"] == "error" and "no status" in st["detail"]


def test_open_url_async_still_returns_a_bool(bridge, monkeypatch):
    monkeypatch.setattr(vagon_pc, "status", lambda m: "ready")
    monkeypatch.setattr(vagon_pc, "open_url", lambda m, u: None)
    assert bridge.open_url_async(URL) is True
    assert bridge.open_url_async("file:///etc/passwd") is False
    _wait_idle(bridge)


# --- the idle stop: set after every start, one retry, then the machine is stopped if it still fails -------------------

def test_a_failed_idle_stop_after_a_start_is_retried_once(bridge, monkeypatch):
    calls, tries = [], []

    def flaky(machine, seconds):
        tries.append(seconds)
        if len(tries) == 1:
            raise vagon_pc.VagonError("PATCH failed with HTTP 429 (rate limited; not retried)")
    monkeypatch.setattr(vagon_pc, "status", lambda m: "off")
    monkeypatch.setattr(vagon_pc, "start_machine", lambda m: calls.append("start"))
    monkeypatch.setattr(vagon_pc, "set_auto_stop", flaky)
    monkeypatch.setattr(vagon_pc, "wait_ready", lambda m, *a, **k: calls.append("wait"))
    monkeypatch.setattr(vagon_pc, "open_url", lambda m, u: calls.append("open"))
    bridge.submit_link(URL)
    _wait_idle(bridge)
    assert tries == [900, 900] and calls == ["start", "wait", "open"]
    assert bridge.status()["state"] == "ready"


def test_an_idle_stop_that_fails_twice_stops_the_machine_and_opens_nothing(bridge, monkeypatch):
    calls = []

    def refused(machine, seconds):
        calls.append(("auto_stop", seconds))
        raise vagon_pc.VagonError("PATCH failed with HTTP 500")
    monkeypatch.setattr(vagon_pc, "status", lambda m: "off")
    monkeypatch.setattr(vagon_pc, "start_machine", lambda m: calls.append("start"))
    monkeypatch.setattr(vagon_pc, "set_auto_stop", refused)
    monkeypatch.setattr(vagon_pc, "stop_machine", lambda m, graceful=True: calls.append(("stop", graceful)))
    monkeypatch.setattr(vagon_pc, "wait_ready", lambda m, *a, **k: calls.append("wait"))
    monkeypatch.setattr(vagon_pc, "open_url", lambda m, u: calls.append("open"))
    bridge.submit_link(URL)
    _wait_idle(bridge)
    assert calls == ["start", ("auto_stop", 900), ("auto_stop", 900), ("stop", True)]
    st = bridge.status()
    assert st["state"] == "error" and "idle stop could not be set" in st["detail"]


def test_a_stop_that_also_fails_is_logged_and_the_error_is_kept(bridge, monkeypatch, caplog):
    def refused(machine, seconds):
        raise vagon_pc.VagonError("PATCH failed with HTTP 500")

    def no_stop(machine, graceful=True):
        raise vagon_pc.VagonError("POST stop failed with HTTP 500")
    monkeypatch.setattr(vagon_pc, "status", lambda m: "off")
    monkeypatch.setattr(vagon_pc, "start_machine", lambda m: None)
    monkeypatch.setattr(vagon_pc, "set_auto_stop", refused)
    monkeypatch.setattr(vagon_pc, "stop_machine", no_stop)
    caplog.set_level(logging.INFO, logger="vagon_bridge")
    bridge.submit_link(URL)
    _wait_idle(bridge)
    assert bridge.status()["state"] == "error"
    assert "stop after a failed idle stop did not go through" in caplog.text


@pytest.mark.parametrize("failing", ["status", "start_machine", "wait_ready", "open_url"])
def test_an_exception_becomes_a_status_error_and_is_not_raised(bridge, monkeypatch, failing):
    def boom(*args, **kwargs):
        raise RuntimeError(f"HMAC key-test:sig-test:nonce-test:1 {URL}")

    def ok(*args, **kwargs):
        return None

    monkeypatch.setattr(vagon_pc, "status", boom if failing == "status" else (lambda m: "off"))
    monkeypatch.setattr(vagon_pc, "start_machine", boom if failing == "start_machine" else ok)
    monkeypatch.setattr(vagon_pc, "set_auto_stop", ok)
    monkeypatch.setattr(vagon_pc, "wait_ready", boom if failing == "wait_ready" else ok)
    monkeypatch.setattr(vagon_pc, "open_url", boom if failing == "open_url" else ok)
    assert bridge.submit_link(URL) == (True, "")             # the caller gets True and no exception
    _wait_idle(bridge)
    st = bridge.status()
    assert st["state"] == "error"
    assert st["detail"].startswith("RuntimeError: ")
    for secret in ("key-test", "sig-test", "nonce-test", "page?q=1"):
        assert secret not in st["detail"]


# --- the caps ---------------------------------------------------------------------------------------------------------

def test_links_open_in_arrival_order_and_the_newest_is_dropped_when_three_wait(bridge, monkeypatch):
    entered, release, opened = threading.Event(), threading.Event(), []

    def open_fn(machine, url):
        opened.append(url)
        if url == LINKS[0]:
            entered.set()
            release.wait(10)

    monkeypatch.setattr(vagon_pc, "status", lambda m: "ready")
    monkeypatch.setattr(vagon_pc, "open_url", open_fn)
    assert bridge.submit_link(LINKS[0]) == (True, "")
    assert entered.wait(10)                                  # the first link is in progress
    for url in LINKS[1:4]:
        assert bridge.submit_link(url) == (True, "")
    assert bridge.submit_link(LINKS[4]) == (False, "full")
    st = bridge.status()
    assert st["waiting"] == 3 and st["state"] == "opening"
    assert "not taken" in st["last_refusal"] and "3 links already wait" in st["last_refusal"]
    assert "example.com" in st["last_refusal"]
    release.set()
    _wait_idle(bridge)
    assert opened == LINKS[:4]                               # FIFO; LINKS[4] never reached the PC


def test_a_link_turned_away_because_the_queue_is_full_uses_no_budget(bridge, monkeypatch):
    monkeypatch.setattr(vagon_bridge, "_queue", deque([(LINKS[0], "example.com")] * vagon_bridge.MAX_QUEUED))
    monkeypatch.setattr(vagon_bridge, "_worker_running", True)      # a worker is running: no new thread
    try:
        assert bridge.submit_link(LINKS[1]) == (False, "full")
        assert bridge.status()["budget"]["links_this_hour"] == 0
    finally:
        monkeypatch.setattr(vagon_bridge, "_worker_running", False)


def test_a_refused_link_queues_nothing_and_starts_no_thread(bridge, monkeypatch):
    monkeypatch.setattr(vagon_pc, "status", lambda m: pytest.fail("a refused link touched the PC"))
    for bad in ("file:///etc/passwd", "https://a.com/ b", "https://a.com/\n", "https://a.com/" + "x" * 2000,
                "https://10.0.0.5/admin", "https://[::1]/", "https://user:pw@example.com/"):
        assert bridge.submit_link(bad) == (False, "invalid")
    st = bridge.status()
    assert st["waiting"] == 0 and st["last_refusal"] == "not a public http or https link"
    assert bridge._worker_running is False


def test_links_are_capped_per_hour_for_all_viewers(bridge, monkeypatch):
    monkeypatch.setattr(vagon_bridge, "LINKS_PER_HOUR", 2)
    monkeypatch.setattr(vagon_pc, "status", lambda m: "ready")
    opened = []
    monkeypatch.setattr(vagon_pc, "open_url", lambda m, u: opened.append(u))
    assert bridge.submit_link(LINKS[0]) == (True, "")
    _wait_idle(bridge)
    assert bridge.submit_link(LINKS[1]) == (True, "")
    _wait_idle(bridge)
    assert bridge.submit_link(LINKS[2]) == (False, "hour")
    assert opened == LINKS[:2]
    st = bridge.status()
    assert st["budget"]["links_this_hour"] == 2 and "this hour is used up (2 links)" in st["last_refusal"]


def test_one_viewer_has_its_own_hourly_cap_when_the_key_is_given(bridge, monkeypatch):
    monkeypatch.setattr(vagon_bridge, "LINKS_PER_VIEWER_PER_HOUR", 1)
    monkeypatch.setattr(vagon_pc, "status", lambda m: "ready")
    monkeypatch.setattr(vagon_pc, "open_url", lambda m, u: None)
    assert bridge.submit_link(LINKS[0], viewer="10.0.0.1") == (True, "")
    _wait_idle(bridge)
    assert bridge.submit_link(LINKS[1], viewer="10.0.0.1") == (False, "viewer")
    assert bridge.submit_link(LINKS[2], viewer="10.0.0.2") == (True, "")
    _wait_idle(bridge)
    assert bridge.submit_link(LINKS[3]) == (True, "")        # without a key the viewer cap does not apply
    _wait_idle(bridge)


def test_starts_are_capped_per_day_and_a_capped_start_is_not_made(bridge, monkeypatch):
    monkeypatch.setattr(vagon_bridge, "STARTS_PER_DAY", 2)
    calls = []
    monkeypatch.setattr(vagon_pc, "status", lambda m: "off")          # the machine has idle-stopped each time
    monkeypatch.setattr(vagon_pc, "start_machine", lambda m: calls.append("start"))
    monkeypatch.setattr(vagon_pc, "set_auto_stop", lambda m, s: calls.append("auto_stop"))
    monkeypatch.setattr(vagon_pc, "wait_ready", lambda m, *a, **k: calls.append("wait"))
    monkeypatch.setattr(vagon_pc, "open_url", lambda m, u: calls.append("open"))
    for url in LINKS[:3]:
        assert bridge.submit_link(url) == (True, "")         # the link is taken; the cap is checked when it runs
        _wait_idle(bridge)
    assert calls.count("start") == 2 and calls.count("open") == 2
    st = bridge.status()
    assert st["state"] == "refused" and "started 2 times today (limit 2)" in st["detail"]
    assert st["budget"]["starts_today"] == 2


def test_the_day_machine_time_is_capped_and_links_are_refused_with_a_reason(bridge, monkeypatch):
    monkeypatch.setattr(vagon_bridge, "ON_MINUTES_PER_DAY", 10)      # one use counts 15 minutes: the next link waits
    monkeypatch.setattr(vagon_pc, "status", lambda m: "ready")
    opened = []
    monkeypatch.setattr(vagon_pc, "open_url", lambda m, u: opened.append(u))
    assert bridge.submit_link(LINKS[0]) == (True, "")
    _wait_idle(bridge)
    assert bridge.submit_link(LINKS[1]) == (False, "ontime")
    st = bridge.status()
    assert "time for the day is used up" in st["last_refusal"] and "an estimate" in st["last_refusal"]
    assert opened == [LINKS[0]] and st["budget"]["on_minutes_today"] >= 10


def test_a_queued_link_is_refused_at_its_turn_when_the_day_time_has_run_out(bridge, monkeypatch):
    entered, release, opened = threading.Event(), threading.Event(), []

    def open_fn(machine, url):
        opened.append(url)
        if url == LINKS[0]:
            entered.set()
            release.wait(10)
    monkeypatch.setattr(vagon_pc, "status", lambda m: "ready")
    monkeypatch.setattr(vagon_pc, "open_url", open_fn)
    assert bridge.submit_link(LINKS[0]) == (True, "")
    assert entered.wait(10)
    assert bridge.submit_link(LINKS[1]) == (True, "")        # accepted before the day's time was used up
    monkeypatch.setattr(vagon_bridge, "ON_MINUTES_PER_DAY", 10)
    release.set()
    _wait_idle(bridge)
    assert opened == [LINKS[0]]                              # LINKS[1] was refused at its turn, with a reason
    st = bridge.status()
    assert st["state"] == "refused" and "time for the day is used up" in st["detail"]


def test_machine_time_windows_that_overlap_are_counted_once():
    b = vagon_bridge._Budget()
    vagon_bridge._count_on(b, 100.0)
    vagon_bridge._count_on(b, 400.0)                          # inside the first window: 300 s more
    vagon_bridge._count_on(b, 5000.0)                         # a new session: a full window
    assert [round(seconds) for _, seconds in b.on] == [900, 300, 900]
    assert vagon_bridge._on_minutes(b, 5000.0) == pytest.approx(35.0)
    # the first window is a day old by then, so only the other two count
    assert vagon_bridge._on_minutes(b, 100.0 + vagon_bridge.DAY_S + 1) == pytest.approx(20.0)


def test_the_budget_lives_with_the_bridge_state(bridge, monkeypatch):
    monkeypatch.setattr(vagon_pc, "status", lambda m: "ready")
    monkeypatch.setattr(vagon_pc, "open_url", lambda m, u: None)
    bridge.submit_link(URL)
    _wait_idle(bridge)
    assert bridge.status()["budget"]["links_this_hour"] == 1
    monkeypatch.setattr(vagon_bridge, "_status", {"state": "off", "detail": ""})   # a reset of the bridge's state
    assert bridge.status()["budget"]["links_this_hour"] == 0


def test_a_host_in_a_log_line_is_ascii_and_at_most_80_characters():
    assert vagon_bridge._host("https://example.com/page?q=1") == "example.com"
    assert vagon_bridge._host("https://ex" + chr(0xE4) + "mple.com:443/") == "ex?mple.com"
    assert vagon_bridge._host("https://a\x1b.com/x") == "a?.com"
    assert vagon_bridge._host("https://" + "a" * 120 + ".com/") == "a" * 80
    assert vagon_bridge._host("not a link") == "?"


def test_the_worker_thread_ends_when_the_queue_is_empty(bridge, monkeypatch):
    monkeypatch.setattr(vagon_pc, "status", lambda m: "ready")
    monkeypatch.setattr(vagon_pc, "open_url", lambda m, u: None)
    bridge.submit_link(URL)
    _wait_idle(bridge)
    assert bridge._worker_running is False and bridge.status()["waiting"] == 0


def test_a_thread_that_cannot_start_is_reported_and_the_queue_is_left_empty(bridge, monkeypatch):
    class NoThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            raise RuntimeError("can't start new thread")
    monkeypatch.setattr(vagon_bridge, "threading", types.SimpleNamespace(Thread=NoThread, Lock=threading.Lock))
    assert bridge.submit_link(URL) == (False, "thread")
    st = bridge.status()
    assert st["waiting"] == 0 and st["state"] == "error" and "can't start" in st["detail"]
    assert bridge._worker_running is False
    assert bridge.status()["budget"]["links_this_hour"] == 0


# --- logs and status never carry credentials, links, or a raw host ----------------------------------------------------

def test_secrets_and_the_link_stay_out_of_status_and_logs(bridge, monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise RuntimeError(f"HMAC key-test:sig-test:nonce-test:1 {URL} secret-test")

    caplog.set_level(logging.INFO)
    monkeypatch.setattr(vagon_pc, "status", boom)
    bridge.submit_link(URL)
    _wait_idle(bridge)
    text = caplog.text + repr(bridge.status())
    for leaked in ("key-test", "secret-test", "sig-test", "nonce-test", "page?q=1", "/page"):
        assert leaked not in text
    assert "host=example.com" in caplog.text                 # the host is what a log line may show


# --- the idle stop at boot --------------------------------------------------------------------------------------------

def test_auto_stop_is_set_to_900_seconds_once_at_boot(bridge, monkeypatch):
    sent = []
    monkeypatch.setattr(vagon_pc, "set_auto_stop", lambda m, s: sent.append((m, s)))
    bridge.configure_auto_stop()
    bridge.configure_auto_stop()
    assert sent == [("machine-test", 900)]
    assert bridge.status()["auto_stop"]["state"] == "ok"
    assert bridge.status()["state"] == "off"


def test_a_failed_auto_stop_at_boot_is_retried_once_and_recorded(bridge, monkeypatch):
    sent = []

    def rate_limited(machine_id, seconds):
        sent.append((machine_id, seconds))
        raise vagon_pc.VagonError("PATCH /machines/machine-test failed with HTTP 429 (rate limited; not retried)")

    monkeypatch.setattr(vagon_pc, "set_auto_stop", rate_limited)
    bridge.configure_auto_stop()
    bridge.configure_auto_stop()
    assert sent == [("machine-test", 900), ("machine-test", 900)]     # one retry in the same call; never again
    st = bridge.status()
    assert st["auto_stop"]["state"] == "error" and "429" in st["auto_stop"]["detail"]
    assert st["state"] == "off"                              # an idle-stop failure does not overwrite the open step


# --- the startup probe ------------------------------------------------------------------------------------------------

def test_probe_lists_once_and_reports_the_machine_status(bridge, monkeypatch, caplog):
    calls = []
    off_machine = [{"id": "machine-test", "attributes": {"friendly_status": "off"}}]
    monkeypatch.setattr(vagon_pc, "list_machines", lambda q=None: calls.append(1) or off_machine)
    caplog.set_level(logging.INFO)
    bridge.probe()
    bridge.probe()
    assert calls == [1]
    assert bridge.status()["probe"] == {"state": "ok", "detail": "machine listed, status off"}
    assert "outcome=ok status=off" in caplog.text


def test_probe_says_loudly_when_the_machine_is_not_listed(bridge, monkeypatch, caplog):
    monkeypatch.setattr(vagon_pc, "list_machines", lambda q=None: [{"id": "some-other-machine"}])
    caplog.set_level(logging.INFO)
    bridge.probe()
    assert bridge.status()["probe"]["state"] == "machine_missing"
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_a_bad_key_fails_the_probe_loudly_once_and_does_not_raise(bridge, monkeypatch, caplog):
    calls = []

    def refused(q=None):
        calls.append(1)
        raise vagon_pc.VagonError("GET /machines failed with HTTP 401 (the key, the secret or the clock is wrong)")

    monkeypatch.setattr(vagon_pc, "list_machines", refused)
    caplog.set_level(logging.INFO)
    bridge.probe()
    bridge.probe()
    st = bridge.status()["probe"]
    assert st["state"] == "error" and "401" in st["detail"]
    assert calls == [1]
    assert any(r.levelno == logging.ERROR and "401" in r.getMessage() for r in caplog.records)


def test_probe_does_nothing_when_disabled(bridge, monkeypatch):
    _env(monkeypatch, {})
    monkeypatch.setattr(vagon_pc, "list_machines", lambda q=None: pytest.fail("the probe listed while disabled"))
    bridge.probe()
    assert bridge.status()["probe"]["state"] == "not run"
