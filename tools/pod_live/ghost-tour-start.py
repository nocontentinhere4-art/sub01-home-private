#!/usr/bin/env python3
"""Grant the live game a root ghost-view policy (spectator cameras) and start the pilot as uid 1001, detached."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PID, TICKS = int(sys.argv[1]), int(sys.argv[2])
HOURS = float(sys.argv[3]) if len(sys.argv) > 3 else 4
POLICY = Path('/run/sub01-home-private/ghost-policy.json')
DIR = Path('/home/unreal/.sub01-private/ghost-visitors')
PILOT = Path('/root/.sub01-windows-recovery/ghost-pilot.py')

stat = (Path('/proc') / str(PID) / 'stat').read_text()
assert int(stat.rsplit(')', 1)[1].split()[19]) == TICKS, 'game identity differs'
POLICY.parent.mkdir(exist_ok=True)
doc = {'schema': 'sub01.root-ghost-policy.v1', 'native_pid': PID, 'native_start_ticks': TICKS,
       'deadline_epoch': int(time.time() + HOURS * 3600), 'capacity': 2, 'fps_per_view': 10,
       'minimum_cm': [-2500, -2500, -50], 'maximum_cm': [3000, 3000, 800], 'spawn_eye_cm': [130, -75, 150]}
tmp = POLICY.with_suffix('.tmp')
tmp.write_text(json.dumps(doc))
os.chmod(tmp, 0o644)
os.replace(tmp, POLICY)
DIR.mkdir(exist_ok=True)
os.chown(DIR, 1001, 1001)
DIR.chmod(0o700)
pilot_copy = Path('/home/unreal/.sub01-private/ghost-tour-20261023')
pilot_copy.mkdir(exist_ok=True)
os.chown(pilot_copy, 1001, 1001)
pilot_copy.chmod(0o700)
target = pilot_copy / 'ghost-pilot.py'
target.write_bytes(PILOT.read_bytes())
os.chown(target, 1001, 1001)
target.chmod(0o700)


def as_unreal():
    os.setgid(1001)
    os.initgroups('unreal', 1001)
    os.setuid(1001)


env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/home/unreal', 'USER': 'unreal', 'LANG': 'C.UTF-8'}
out = open(pilot_copy / 'pilot.out', 'ab')
child = subprocess.Popen(['python3', str(target)], env=env, preexec_fn=as_unreal, stdin=subprocess.DEVNULL,
                         stdout=out, stderr=subprocess.STDOUT, start_new_session=True, cwd=str(pilot_copy))
print(json.dumps({'policy': doc, 'pilot_pid': child.pid}))
