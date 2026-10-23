"""Offline checks for the Vagon bridge: vagon_pc is faked, so no network and no credentials. Run on the pod."""
import threading

import pytest

import vagon_bridge
import vagon_pc

ENV = {"VAGON_PC_ENABLED": "1", "VAGON_MACHINE_ID": "machine-test", "VAGON_API_KEY": "key-test",
       "VAGON_API_SECRET": "secret-test"}
URL = "https://example.com/page?q=1"


def _env(monkeypatch, env):
    for name in ENV:
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)


def _wait_idle(bridge):
    """Returns once the open thread, if one was started, has released the lock, which means it has ended."""
    assert bridge._busy.acquire(timeout=10)
    bridge._busy.release()


@pytest.fixture
def bridge(monkeypatch):
    monkeypatch.setattr(vagon_bridge, "_busy", threading.Lock())
    monkeypatch.setattr(vagon_bridge, "_status", {"state": "off", "detail": ""})
    monkeypatch.setattr(vagon_bridge, "_auto_stop_done", False)
    _env(monkeypatch, ENV)
    unexpected = []   # a call the test did not fake is recorded here and fails the test, so none reaches the network
    for name in ("status", "start_machine", "wait_ready", "open_url", "set_auto_stop"):
        monkeypatch.setattr(vagon_pc, name, lambda *a, _n=name, **k: unexpected.append(_n))
    yield vagon_bridge
    _wait_idle(vagon_bridge)   # no thread may outlive its test
    assert unexpected == []


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
    assert bridge.open_url_async(URL) is False
    bridge.configure_auto_stop()
    assert bridge.status() == {"enabled": False, "state": "off", "detail": ""}


def test_a_machine_that_is_not_ready_is_started_once_then_opened(bridge, monkeypatch):
    calls = []
    monkeypatch.setattr(vagon_pc, "status", lambda m: calls.append("status") or "off")
    monkeypatch.setattr(vagon_pc, "start_machine", lambda m: calls.append("start"))
    monkeypatch.setattr(vagon_pc, "wait_ready", lambda m, *a, **k: calls.append("wait"))
    monkeypatch.setattr(vagon_pc, "open_url", lambda m, u: calls.append(("open", m, u)))
    assert bridge.open_url_async(URL) is True
    _wait_idle(bridge)
    assert calls == ["status", "start", "wait", ("open", "machine-test", URL)]
    assert bridge.status()["state"] == "ready"


def test_a_ready_machine_is_opened_without_a_start(bridge, monkeypatch):
    calls = []
    monkeypatch.setattr(vagon_pc, "status", lambda m: "ready")
    monkeypatch.setattr(vagon_pc, "open_url", lambda m, u: calls.append("open"))
    assert bridge.open_url_async(URL) is True
    _wait_idle(bridge)
    assert calls == ["open"]


def test_open_url_async_runs_one_open_at_a_time(bridge, monkeypatch):
    entered, release, opened = threading.Event(), threading.Event(), []

    def slow_open(machine, url):
        opened.append(url)
        entered.set()
        release.wait(10)

    monkeypatch.setattr(vagon_pc, "status", lambda m: "ready")
    monkeypatch.setattr(vagon_pc, "open_url", slow_open)
    assert bridge.open_url_async(URL) is True
    assert entered.wait(10)
    assert bridge.open_url_async(URL) is False       # the first open is still running
    assert bridge.status()["state"] == "opening"
    release.set()
    _wait_idle(bridge)
    assert opened == [URL]
    assert bridge.open_url_async(URL) is True        # free again once the first one has ended
    _wait_idle(bridge)
    assert opened == [URL, URL]
    assert bridge.status()["state"] == "ready"


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
    assert bridge.open_url_async(URL) is True        # the caller gets True and no exception
    _wait_idle(bridge)
    st = bridge.status()
    assert st["state"] == "error"
    assert st["detail"].startswith("RuntimeError: ")
    for secret in ("key-test", "sig-test", "nonce-test", "example.com"):
        assert secret not in st["detail"]


@pytest.mark.parametrize("bad", ["file:///etc/passwd", "https://a.com/ b", "https://a.com/\n",
                                 "https://a.com/" + "x" * 2000])
def test_a_refused_link_starts_nothing(bridge, bad):
    assert bridge.open_url_async(bad) is True        # refused inside the thread, before any machine call
    _wait_idle(bridge)
    assert bridge.status()["state"] == "error"


def test_auto_stop_is_set_to_900_seconds_once(bridge, monkeypatch):
    sent = []
    monkeypatch.setattr(vagon_pc, "set_auto_stop", lambda m, s: sent.append((m, s)))
    bridge.configure_auto_stop()
    bridge.configure_auto_stop()
    assert sent == [("machine-test", 900)]
    assert bridge.status()["state"] == "off"


def test_a_failed_auto_stop_is_recorded_and_not_retried(bridge, monkeypatch):
    sent = []

    def rate_limited(machine_id, seconds):
        sent.append((machine_id, seconds))
        raise vagon_pc.VagonError("PATCH /machines/machine-test failed with HTTP 429")

    monkeypatch.setattr(vagon_pc, "set_auto_stop", rate_limited)
    bridge.configure_auto_stop()
    bridge.configure_auto_stop()
    assert sent == [("machine-test", 900)]
    st = bridge.status()
    assert st["state"] == "error" and "429" in st["detail"]
