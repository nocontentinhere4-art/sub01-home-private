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


@pytest.fixture(autouse=True)
def no_real_vagon(monkeypatch):
    """Each test starts with the Vagon variables removed (a pod shell may export them) and with an opener that fails."""
    for name in ENV:
        monkeypatch.delenv(name, raising=False)

    class NoNetwork:
        def open(self, *args, **kwargs):
            raise AssertionError("a request was sent")
    monkeypatch.setattr(vagon_pc, "_OPENER", NoNetwork())


@pytest.fixture
def bridge(monkeypatch):
    monkeypatch.setattr(vagon_bridge, "_queue", deque())
    monkeypatch.setattr(vagon_bridge, "_worker_running", False)
    monkeypatch.setattr(vagon_bridge, "_status", {"state": "off", "detail": ""})
    monkeypatch.setattr(vagon_bridge, "_last_refusal", "")
    monkeypatch.setattr(vagon_bridge, "_probe", {"state": "not run", "detail": ""})
    monkeypatch.setattr(vagon_bridge, "_probe_done", False)
    monkeypatch.setattr(vagon_bridge, "_auto_stop", {"state": "not run", "detail": ""})
    monkeypatch.setattr(vagon_bridge, "_auto_stop_done", False)
    _env(monkeypatch, ENV)
    unexpected = []   # a call the test did not fake is recorded here and fails the test, so none reaches the network
    for name in ("status", "start_machine", "wait_ready", "open_url", "set_auto_stop", "list_machines"):
        monkeypatch.setattr(vagon_pc, name, lambda *a, _n=name, **k: unexpected.append(_n))
    yield vagon_bridge
    _wait_idle(vagon_bridge)
    assert unexpected == []


# --- switch and status ----------------------------------------------------------------------------------------------

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


# --- starting and opening -------------------------------------------------------------------------------------------

def test_an_off_machine_is_started_once_then_opened(bridge, monkeypatch):
    calls = []
    monkeypatch.setattr(vagon_pc, "status", lambda m: calls.append("status") or "off")
    monkeypatch.setattr(vagon_pc, "start_machine", lambda m: calls.append("start"))
    monkeypatch.setattr(vagon_pc, "wait_ready", lambda m, *a, **k: calls.append("wait"))
    monkeypatch.setattr(vagon_pc, "open_url", lambda m, u: calls.append(("open", m, u)))
    assert bridge.submit_link(URL) == (True, "")
    _wait_idle(bridge)
    assert calls == ["status", "start", "wait", ("open", "machine-test", URL)]
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


# --- the queue ------------------------------------------------------------------------------------------------------

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
    assert "newest link dropped" in st["last_refusal"] and "example.com" in st["last_refusal"]
    release.set()
    _wait_idle(bridge)
    assert opened == LINKS[:4]                               # FIFO; LINKS[4] never reached the PC


def test_a_refused_link_queues_nothing_and_starts_no_thread(bridge, monkeypatch):
    monkeypatch.setattr(vagon_pc, "status", lambda m: pytest.fail("a refused link touched the PC"))
    for bad in ("file:///etc/passwd", "https://a.com/ b", "https://a.com/\n", "https://a.com/" + "x" * 2000):
        assert bridge.submit_link(bad) == (False, "invalid")
    st = bridge.status()
    assert st["waiting"] == 0 and st["last_refusal"]
    assert bridge._worker_running is False


def test_a_thread_that_cannot_start_is_reported_and_the_queue_is_left_empty(bridge, monkeypatch):
    class NoThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            raise RuntimeError("can't start new thread")
    monkeypatch.setattr(vagon_bridge, "threading", types.SimpleNamespace(Thread=NoThread))
    assert bridge.submit_link(URL) == (False, "thread")
    st = bridge.status()
    assert st["waiting"] == 0 and st["state"] == "error" and "can't start" in st["detail"]
    assert bridge._worker_running is False


# --- errors, secrets and logs ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("failing", ["status", "start_machine", "wait_ready", "open_url"])
def test_an_exception_becomes_a_status_error_and_is_not_raised(bridge, monkeypatch, failing):
    def boom(*args, **kwargs):
        raise RuntimeError(f"HMAC key-test:sig-test:nonce-test:1 {URL}")

    def ok(*args, **kwargs):
        return None

    monkeypatch.setattr(vagon_pc, "status", boom if failing == "status" else (lambda m: "off"))
    monkeypatch.setattr(vagon_pc, "start_machine", boom if failing == "start_machine" else ok)
    monkeypatch.setattr(vagon_pc, "wait_ready", boom if failing == "wait_ready" else ok)
    monkeypatch.setattr(vagon_pc, "open_url", boom if failing == "open_url" else ok)
    assert bridge.submit_link(URL) == (True, "")             # the caller gets True and no exception
    _wait_idle(bridge)
    st = bridge.status()
    assert st["state"] == "error"
    assert st["detail"].startswith("RuntimeError: ")
    for secret in ("key-test", "sig-test", "nonce-test", "page?q=1"):
        assert secret not in st["detail"]


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


def test_auto_stop_is_set_to_900_seconds_once(bridge, monkeypatch):
    sent = []
    monkeypatch.setattr(vagon_pc, "set_auto_stop", lambda m, s: sent.append((m, s)))
    bridge.configure_auto_stop()
    bridge.configure_auto_stop()
    assert sent == [("machine-test", 900)]
    assert bridge.status()["auto_stop"]["state"] == "ok"
    assert bridge.status()["state"] == "off"


def test_a_failed_auto_stop_is_recorded_and_not_retried(bridge, monkeypatch):
    sent = []

    def rate_limited(machine_id, seconds):
        sent.append((machine_id, seconds))
        raise vagon_pc.VagonError("PATCH /machines/machine-test failed with HTTP 429 (rate limited; not retried)")

    monkeypatch.setattr(vagon_pc, "set_auto_stop", rate_limited)
    bridge.configure_auto_stop()
    bridge.configure_auto_stop()
    assert sent == [("machine-test", 900)]
    st = bridge.status()
    assert st["auto_stop"]["state"] == "error" and "429" in st["auto_stop"]["detail"]
    assert st["state"] == "off"                              # an auto-stop failure does not overwrite the open step


# --- the startup probe ----------------------------------------------------------------------------------------------

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
