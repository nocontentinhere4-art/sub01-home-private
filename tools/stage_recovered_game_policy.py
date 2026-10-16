"""Stage, never install, the exact recovered kitchen Game's Minecraft binding.

Only the native runtime owner may install the returned file and refresh its
backend. Historical handoff and snapshot helpers remain unchanged.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import time

PROJECT = '/workspace/sub01-private-playable-kitchen-r1-20261016/Sub01HomeLab/Sub01HomeLab.uproject'
OLD_GAME = (225250, 980289227)
GUARD = (239097, 980716622)
DEADLINE = 1792203575
POLICY = Path('/home/unreal/sub01-backend/home_minecraft_input.py')
STAGED = Path('/home/unreal/runtime-tools/home_minecraft_input.recovered-next.py')


def rebound(text, pid, start):
    if type(pid) is not int or type(start) is not int or pid <= 0 or start <= 0:
        raise ValueError('Positive exact process identity required')
    expected = {'PROJECT': PROJECT, 'NATIVE_PID': OLD_GAME[0], 'NATIVE_START_TICKS': OLD_GAME[1]}
    wanted = dict(expected, NATIVE_PID=pid, NATIVE_START_TICKS=start)
    spans = {}
    for node in ast.parse(text).body:
        names = [target.id for target in node.targets if isinstance(target, ast.Name)] if isinstance(node, ast.Assign) else []
        for name in names:
            if name in expected:
                if len(node.targets) != 1 or name in spans or ast.literal_eval(node.value) != expected[name]:
                    raise ValueError('Exact single old binding required: ' + name)
                spans[name] = (node.lineno, node.end_lineno)
        if isinstance(node, (ast.AnnAssign, ast.AugAssign)) and isinstance(node.target, ast.Name) and node.target.id in expected:
            raise ValueError('Unexpected binding syntax')
    if set(spans) != set(expected):
        raise ValueError('All three original bindings required')
    lines = text.splitlines(keepends=True)
    for name, (lo, hi) in sorted(spans.items(), key=lambda item: item[1][0], reverse=True):
        lines[lo - 1:hi] = [name + ' = ' + repr(wanted[name]) + '\n']
    result = ''.join(lines)
    ast.parse(result)
    return result


def identity(pid, start, uid):
    p = Path('/proc') / str(pid)
    fields = (p / 'stat').read_text().rsplit(')', 1)[1].split()
    actual_uid = int((p / 'status').read_text().split('Uid:', 1)[1].split()[0])
    if fields[0] == 'Z' or int(fields[19]) != start or actual_uid != uid:
        raise ValueError('Process identity mismatch')
    return (p / 'cmdline').read_bytes().split(b'\0')


def stage(pid, start, expected_sha):
    if os.getuid() != 1001 or len(expected_sha) != 64 or any(c not in '0123456789abcdef' for c in expected_sha):
        raise ValueError('Native owner and exact prior SHA required')
    window_path = Path('/run/sub01-home-private/runtime-window.json')
    mode = window_path.stat()
    if not stat.S_ISREG(mode.st_mode) or mode.st_uid != 0 or mode.st_mode & 0o022:
        raise ValueError('Authenticated root-owned window required')
    w = json.loads(window_path.read_text())
    if not (w['pod'] == 'dgtgepkz7h1zy5' and w['deadline_epoch'] == DEADLINE and time.time() + 60 < DEADLINE
            and w['root_guard_pid'] == GUARD[0] and w['root_guard_start_ticks'] == GUARD[1]
            and w['root_guard_authenticated'] is True and w['stop_guards_authenticated'] is True
            and w['total_cap'] <= 100 and w['minimum_balance_reserve'] >= 10):
        raise ValueError('Current extended guard/window required')
    identity(*GUARD, 0)
    args = identity(pid, start, 1001)
    if PROJECT.encode() not in args or b'-game' not in args:
        raise ValueError('Exact same private kitchen project required')
    try:
        identity(*OLD_GAME, 1001)
    except (OSError, ValueError):
        pass
    else:
        raise ValueError('Old Game must have exited')
    raw = POLICY.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError('Prior policy SHA mismatch')
    generated = rebound(raw.decode('utf-8'), pid, start).encode('utf-8')
    if STAGED.exists():
        if STAGED.read_bytes() != generated:
            raise ValueError('Different staged recovery already exists')
    else:
        fd, temporary = tempfile.mkstemp(prefix='.recovered-policy-', dir=STAGED.parent)
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(generated)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(temporary, 0o600)
            os.link(temporary, STAGED)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return {'schema': 'sub01.recovered-game-policy-stage.v1', 'installed': False,
            'project': PROJECT, 'game_identity': [pid, start], 'old_policy_sha256': expected_sha,
            'staged_path': str(STAGED), 'staged_sha256': hashlib.sha256(generated).hexdigest(),
            'deadline_epoch': DEADLINE, 'guard_identity': list(GUARD)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--start', type=int, required=True)
    parser.add_argument('--expected-policy-sha', required=True)
    args = parser.parse_args()
    print(json.dumps(stage(args.pid, args.start, args.expected_policy_sha)))
