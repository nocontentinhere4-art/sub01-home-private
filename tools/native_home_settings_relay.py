"""Publish the backend's Tokyo hour and room lights to the native Game's lamps.

The Game already owns six authored lamps and a daylight hour behind
``viewSettings`` in the private native-control file; nothing fed them from the
backend, so the native house stayed at 11:00 with fixed lamps while the brain
lived on the real Tokyo clock. This relay is the only writer of that file: it
re-publishes when the hour or a lamp changes and folds in operator capture
requests (``capture-request.txt``) so revisions stay strictly increasing.
Loopback only; it never moves the pawn or changes the view mode.
"""
import argparse
import json
import os
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PRIVATE = Path('/home/unreal/.sub01-private')
ROOM_LAMPS = {'bedroom': ('BedLamp', 'UpperPendant'), 'living': ('LowerPendant', 'DeskLamp'),
              'kitchen': ('KitchenWork',), 'bathroom': ('BathroomCeiling',)}
SAFE = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.')


def tokyo_hour(now=None):
    local = datetime.fromtimestamp(time.time() if now is None else now, ZoneInfo('Asia/Tokyo'))
    # Quarter-hour steps keep the sun moving without rewriting every poll.
    return round((local.hour + local.minute / 60) * 4) / 4


def desired_settings(home, hour):
    rooms = home['lights']['rooms']
    lamps = {lamp: bool(rooms[room]['on']) for room, names in ROOM_LAMPS.items() for lamp in names}
    return {'hour': hour, 'lamps': lamps}


def safe_capture(name):
    name = name.strip()
    return name if 0 < len(name) < 80 and name.endswith('.png') and set(name) <= SAFE else None


def write_control(path, document):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(document))
    temp.chmod(0o600)
    os.replace(temp, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', default='http://127.0.0.1:8820')
    parser.add_argument('--deadline-epoch', type=int, required=True)
    parser.add_argument('--interval', type=float, default=2.0)
    args = parser.parse_args()
    assert args.backend.startswith('http://127.0.0.1:'), 'Loopback backend only'
    control, request = PRIVATE / 'native-control.json', PRIVATE / 'capture-request.txt'
    receipt = PRIVATE / 'native-view-settings-receipt.json'
    published, game = None, None
    while time.time() < args.deadline_epoch:
        try:
            with urllib.request.urlopen(args.backend + '/api/home', timeout=3) as response:
                settings = desired_settings(json.load(response)['home'], tokyo_hour())
        except Exception as error:
            print('BACKEND_READ_RETRY', type(error).__name__, flush=True)
            time.sleep(args.interval)
            continue
        try:
            current_game = json.loads(receipt.read_text()).get('native_pid')
        except (OSError, ValueError):
            current_game = game
        if current_game != game:
            # A restarted Game boots at its authored defaults; publish again.
            published, game = None, current_game
        capture = None
        if request.exists():
            capture = safe_capture(request.read_text())
            request.unlink()
        if settings != published or capture:
            try:
                current = int(json.loads(control.read_text()).get('revision', 0))
            except (OSError, ValueError):
                current = 0
            revision = max(current + 1, int(time.time()) - 1792000000)
            document = {'revision': revision, 'viewSettings': settings}
            if capture:
                document['capture'] = capture
            write_control(control, document)
            print('PUBLISHED', revision, json.dumps(settings), capture or '', flush=True)
            published = settings
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
