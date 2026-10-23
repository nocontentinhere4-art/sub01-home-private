#!/usr/bin/env python3
"""Start the patched read-only window viewer (manual + live modes) for the live game, as uid 1001.

usage: start-live-viewer-20261023.py --pid P --start-ticks T --port 8894 [--stop-old]
--stop-old terminates the viewer currently bound to the old game (its runuser wrapper, python and ffmpeg).
"""
import argparse
import json
import os
import signal
import subprocess
import time
import urllib.request
from pathlib import Path

PRIVATE = Path('/home/unreal/.sub01-private')
VIEW = PRIVATE / 'native-live-window-20261023' / 'native_readonly_window_view.py'
OLD_VIEW = PRIVATE / 'native-readonly-window' / 'rebind_final_game_readonly_viewer.py'
AUTH = PRIVATE / 'native-xauthority'
ENV = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/home/unreal', 'USER': 'unreal', 'LANG': 'C.UTF-8',
       'DISPLAY': ':99', 'XAUTHORITY': str(AUTH)}


def as_unreal():
    os.setgid(1001)
    os.initgroups('unreal', 1001)
    os.setuid(1001)


def window_for(pid):
    out = subprocess.run(['xdotool', 'search', '--pid', str(pid)], env=ENV, preexec_fn=as_unreal,
                         capture_output=True, text=True, timeout=20).stdout.split()
    windows = [int(w) for w in out]
    named = []
    for w in windows:
        name = subprocess.run(['xdotool', 'getwindowname', str(w)], env=ENV, preexec_fn=as_unreal,
                              capture_output=True, text=True, timeout=20).stdout.strip()
        named.append((w, name))
    return named


def stop_old():
    stopped = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            argv = (proc / 'cmdline').read_bytes().split(b'\0')
        except OSError:
            continue
        if str(OLD_VIEW).encode() in argv:
            os.kill(int(proc.name), signal.SIGTERM)
            stopped.append(int(proc.name))
    return stopped


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid', type=int, required=True)
    p.add_argument('--start-ticks', type=int, required=True)
    p.add_argument('--port', type=int, default=8894)
    p.add_argument('--stop-old', action='store_true')
    a = p.parse_args()
    named = window_for(a.pid)
    game = [w for w, name in named if name.startswith('Sub01HomeLab')]
    assert len(game) == 1, f'expected one game window for pid {a.pid}, got {named}'
    window = game[0]
    if a.stop_old:
        print('stopped old viewer processes', stop_old())
        time.sleep(1.5)
    log = (PRIVATE / 'native-live-window-20261023' / f'viewer-{a.pid}-{a.port}.log').open('ab')
    child = subprocess.Popen(['python3', str(VIEW), '--pid', str(a.pid), '--start-ticks', str(a.start_ticks),
                              '--window-id', hex(window), '--port', str(a.port)],
                             env=ENV, preexec_fn=as_unreal, cwd=str(VIEW.parent), stdin=subprocess.DEVNULL,
                             stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    health = None
    for _ in range(30):
        time.sleep(1)
        if child.poll() is not None:
            break
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{a.port}/health', timeout=2) as r:
                health = json.load(r)
            if health.get('captureEnabled'):
                break
        except (OSError, ValueError):
            pass
    print(json.dumps({'viewer_pid': child.pid, 'exited': child.poll(), 'window': hex(window), 'port': a.port,
                      'health': health}))


if __name__ == '__main__':
    main()
