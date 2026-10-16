"""Explicit one-off backend-only repair; importing never touches runtime.

Retains fresh Java flush/v86/world saves and all proven exact process guards.
The running renderer remains alive throughout; only its stale consumer binding
and existing backend are refreshed. Native owner alone invokes run().
"""
import ast
import hashlib
from pathlib import Path

RECIPE_SHA = '2f0f674fbb7ca376eac427d1987e310b673ea1cd167de3f83521473e31bc4f18'
PROJECT = '/workspace/sub01-private-playable-next-20261016/Sub01HomeLab/Sub01HomeLab.uproject'
GAME = (215923, 979985246)
BACKEND = (216723, 980003928)
STALE = {'PROJECT': PROJECT, 'NATIVE_PID': 209503, 'NATIVE_START_TICKS': 979714171}


def policy_for_current(text, pid, start):
    assert (pid, start) == GAME
    wanted = {'PROJECT': PROJECT, 'NATIVE_PID': pid, 'NATIVE_START_TICKS': start}
    spans = {}
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in wanted:
                    assert target.id not in spans
                    assert ast.literal_eval(node.value) == STALE[target.id]
                    spans[target.id] = (node.lineno, node.end_lineno)
    assert set(spans) == set(wanted)
    lines = text.splitlines(keepends=True)
    for name, (lo, hi) in sorted(spans.items(), key=lambda row: row[1][0], reverse=True):
        lines[lo - 1:hi] = [name + ' = ' + repr(wanted[name]) + '\n']
    result = ''.join(lines)
    ast.parse(result)
    return result


def run():
    recipe = Path(__file__).with_name('kitchen_game_device_policy_refresh.py')
    raw = recipe.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == RECIPE_SHA
    source = raw.decode()
    old_guard = ''' try:proc(*OLD_GAME)
 except (OSError,AssertionError):pass
 else:raise RuntimeError('OldGame still alive; no backend refresh permitted')'''
    assert source.count(old_guard) == 1
    source = source.replace(old_guard, ''' assert (next_pid,next_start)==OLD_GAME, 'Same exact renderer must remain alive'
 exact_game(*OLD_GAME,OLD_PROJECT)''')
    namespace = {'__name__': '__sub01_exact_backend_recovery__', '__file__': str(recipe)}
    exec(compile(source, str(recipe), 'exec'), namespace)
    namespace.update(OLD_PROJECT=PROJECT, NEXT_PROJECT=PROJECT,
                     OLD_GAME=GAME, BACKEND=BACKEND,
                     policy_for_next=policy_for_current)
    snapshot = namespace['preflight_before_handoff']()
    namespace['exact_game'](*GAME, PROJECT)
    result = namespace['apply_after_launch'](snapshot, *GAME)
    namespace['exact_game'](*GAME, PROJECT)
    assert result['game_identity_unchanged'] == {'pid': GAME[0], 'start_ticks': GAME[1]}
    return {'snapshot_directory': snapshot, 'rollout': result}


if __name__ == '__main__':
    import json
    print(json.dumps(run()))
