#!/usr/bin/env python3
"""Patch the copied read-only window viewer so it also serves frames while the game is in live mode.

The original viewer only shows pixels in the manual (cinematic review) view mode. Live mode is the game
following the backend through the 8831 bridge; privacy (bathroom) handling stays exactly as before.
"""
import re
import sys
from pathlib import Path

ROOT = Path('/home/unreal/.sub01-private/native-live-window-20261023')
FINAL_PROJECT = b'/home/unreal/.sub01-private/cinematic-source-v3-final/Sub01HomeLab/Sub01HomeLab.uproject'


def replace_once(path, old, new):
    text = path.read_text()
    count = text.count(old)
    assert count == 1, f'{path.name}: expected exactly one occurrence of {old!r}, found {count}'
    path.write_text(text.replace(old, new))
    print(f'patched {path.name}: {old[:60]!r}')


view = ROOT / 'native_readonly_window_view.py'
replace_once(view, "PRIVATE = Path('/home/unreal/.sub01-private')\n",
             "PRIVATE = Path('/home/unreal/.sub01-private')\nLIVE_MODES = ('manual', 'live')   # 2026-10-23: frames also while the game follows the backend\n")
replace_once(view, "            if self.privacy() == (False, 'manual'):\n",
             "            if self.privacy()[0] is False and self.privacy()[1] in LIVE_MODES:\n")
replace_once(view, "b'/workspace/sub01-private-completion-20261021/Sub01HomeLab/Sub01HomeLab.uproject' in args",
             "b'" + FINAL_PROJECT.decode() + "' in args")
replace_once(view, "and privacy is False and mode == 'manual' and fresh",
             "and privacy is False and mode in LIVE_MODES and fresh")
replace_once(view, "state.privacy() != (False, 'manual'):",
             "(state.privacy()[0] is not False or state.privacy()[1] not in LIVE_MODES):")
replace_once(view, "    parser.add_argument('--window-id', type=lambda x: int(x, 0), required=True)\n    args = parser.parse_args()\n",
             "    parser.add_argument('--window-id', type=lambda x: int(x, 0), required=True)\n    parser.add_argument('--port', type=int, default=8893)\n    args = parser.parse_args()\n")
replace_once(view, "ThreadingHTTPServer(('127.0.0.1', 8893), Handler)", "ThreadingHTTPServer(('127.0.0.1', args.port), Handler)")

ws = ROOT / 'native_owner_websocket.py'
replace_once(ws, "allowed=public is False and mode=='manual' and s.owner_window_matches()",
             "allowed=public is False and mode in ('manual','live') and s.owner_window_matches()")

for name in ('native_owner_control.py', 'native_owner_client.js'):
    for number, line in enumerate((ROOT / name).read_text().splitlines(), 1):
        if re.search(r"manual|viewMode|view_mode", line):
            print(f'{name}:{number}: {line.strip()[:170]}')

import py_compile
for name in ('native_readonly_window_view.py', 'native_owner_websocket.py', 'native_owner_control.py'):
    py_compile.compile(str(ROOT / name), doraise=True)
print('compiled ok')
