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


@pytest.mark.parametrize('value', [
    {'fov': 111}, {'fov': True}, {'hour': float('nan')},
    {'lamps': {'SUN': False}}, {'lamps': {'DeskLamp': 1}},
    {'lamps': {'Actor/Other': True}}, {'console': 'anything'},
])
def test_settings_cannot_address_unknown_actors_or_unbounded_camera(value):
    from tools.pixel_streaming.native_live_viewer import validate_settings
    with pytest.raises(ValueError):
        validate_settings(value, {'fov': True, 'hour': True, 'lamps': ['DeskLamp']})


def test_settings_require_actual_native_capability():
    from tools.pixel_streaming.native_live_viewer import validate_settings
    with pytest.raises(ValueError):
        validate_settings({'fov': 75}, {})
    assert validate_settings({'fov': 75, 'lamps': {'DeskLamp': False}},
                             {'fov': True, 'lamps': ['DeskLamp']})


def test_settings_receipt_is_invalid_after_native_replacement(tmp_path):
    state = LiveState(time.time() + 30)
    state.private = tmp_path
    (tmp_path/'native-view-settings-receipt.json').write_text(json.dumps({
        'native_pid': 42, 'native_start_ticks': 100,
        'capabilities': {'fov': True}, 'values': {'fov': 75},
    }))
    state.native = lambda: (42, 100)
    assert state.settings_receipt()['capabilities']['fov']
    state.native = lambda: (42, 101)
    assert state.settings_receipt() is None
