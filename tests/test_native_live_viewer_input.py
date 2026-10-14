"""The live viewer can deliver physical controls, never arbitrary host commands."""
import pytest
import json
import time
from tools.pixel_streaming.native_live_viewer import LiveState, validate_input


@pytest.mark.parametrize("event", [
    {"action": "key", "code": "KeyW", "down": True},
    {"action": "key", "code": "Enter", "down": False},
    {"action": "mouse", "dx": -100, "dy": 100},
    {"action": "button", "button": 1, "down": True},
    {"action": "release"},
])
def test_allowed_physical_controls(event):
    assert validate_input(event) == event


@pytest.mark.parametrize("event", [
    {"action": "key", "code": "AltLeft", "down": True},
    {"action": "key", "code": "KeyW", "down": 1},
    {"action": "mouse", "dx": 101, "dy": 0},
    {"action": "mouse", "dx": True, "dy": 0},
    {"action": "button", "button": 2, "down": True},
    {"action": "release", "command": "anything"},
    {"action": "shell", "command": "anything"},
    [],
])
def test_unsupported_or_unbounded_input_is_rejected(event):
    with pytest.raises(ValueError):
        validate_input(event)


def test_capture_permission_cannot_survive_native_process_replacement(tmp_path):
    state = LiveState(time.time() + 30)
    state.private = tmp_path
    flag = tmp_path / "native-viewer-capture-enabled"
    flag.write_text(json.dumps({"native_pid": 42, "native_start_ticks": 100}))
    state.native = lambda: (42, 100)
    assert state.enabled(flag.name)
    state.native = lambda: (42, 101)
    assert not state.enabled(flag.name)
    state.native = lambda: (43, 100)
    assert not state.enabled(flag.name)
    state.native = lambda: None
    assert not state.enabled(flag.name)


@pytest.mark.parametrize("content", ["", "[]", "not-json"])
def test_invalid_capture_permission_fails_closed(tmp_path, content):
    state = LiveState(time.time() + 30)
    state.private = tmp_path
    state.native = lambda: (42, 100)
    flag = tmp_path / "native-viewer-capture-enabled"
    flag.write_text(content)
    assert not state.enabled(flag.name)
