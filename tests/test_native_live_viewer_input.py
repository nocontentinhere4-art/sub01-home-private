"""The live viewer can deliver physical controls, never arbitrary host commands."""
import pytest
from tools.pixel_streaming.native_live_viewer import validate_input


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
