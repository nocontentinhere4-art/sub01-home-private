import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import native_home_settings_relay as relay


def home(**on):
    rooms = {r: {'on': on.get(r, False), 'mode': 'auto'} for r in ('living', 'kitchen', 'bedroom', 'bathroom')}
    return {'lights': {'rooms': rooms}}


def test_room_lights_map_to_every_native_lamp():
    settings = relay.desired_settings(home(bedroom=True, bathroom=True), 21.5)
    assert settings['hour'] == 21.5
    assert settings['lamps'] == {'BedLamp': True, 'UpperPendant': True, 'LowerPendant': False,
                                 'DeskLamp': False, 'KitchenWork': False, 'BathroomCeiling': True}


def test_tokyo_hour_uses_quarter_steps():
    # 2026-10-17 12:58:00 UTC is 21:58 in Tokyo.
    assert relay.tokyo_hour(1792241880) == 22.0
    assert relay.tokyo_hour(1792241880 - 600) == 21.75


def test_capture_names_are_restricted_like_the_game():
    assert relay.safe_capture('r21-night.png\n') == 'r21-night.png'
    assert relay.safe_capture('../x.png') is None
    assert relay.safe_capture('frame.jpg') is None
