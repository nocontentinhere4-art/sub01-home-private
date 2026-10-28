#!/usr/bin/env python3
"""Fly one ghost (spectator) camera through the live native home and save a frame catalogue.

Runs as uid 1001 on the pod. The game's FSub01GhostViews reads request-<key>.json (keys + look deltas), moves a
scene-capture camera with collision, and writes frame-<key>.png (640x360) plus a receipt with the camera position.
Nothing here touches SUB-01: the ghost camera is a separate actor with no owner chain to him.
"""
import json
import math
import os
import re
import shutil
import sys
import time
import uuid
from pathlib import Path

DIR = Path('/home/unreal/.sub01-private/ghost-visitors')
OUT = Path('/home/unreal/.sub01-private/ghost-tour-20261023')
OUT.mkdir(mode=0o700, exist_ok=True)
LOG = open(OUT / 'pilot.log', 'a', buffering=1)
KEY = uuid.uuid4().hex
REQ = DIR / f'request-{KEY}.json'
TMP = DIR / f'pending-{KEY}.tmp'
FRAME = DIR / f'frame-{KEY}.png'
META = DIR / f'frame-{KEY}.json'
SPAWN = (130.0, -75.0, 150.0)
EYE = 150.0            # camera height above a floor node (floor nodes are z=0 ground, z=300 loft)
PITCH = -10.0

NODES = {'desk': (200, -75, 0), 'aisle': (130, -75, 0), 'back': (130, -220, 0), 'kitchen_gate': (-50, -220, 0),
         'kitchen': (-180, -180, 0), 'sofa': (-255, 10, 0), 'sofa_front_approach': (-255, 160, 0),
         'sofa_rear_approach': (-255, -160, 0), 'lounge_gate': (-45, 320, 0), 'front': (130, 320, 0),
         'stair_approach': (30, 320, 0), 'stair_bottom': (30, 255, 0), 'stair_top': (30, -170, 300),
         'landing': (30, -210, 300), 'loft': (-50, -210, 300), 'bed': (-120, -290, 300),
         'bath_aisle': (-60, -20, 300), 'bath_door': (-56.7, 135, 300), 'balcony_gate': (-50, 320, 300),
         'balcony_door': (-220, 320, 300)}
# (waypoint, take a 4-direction shot here?)
ROUTE = [('desk', True), ('aisle', False), ('back', True), ('kitchen_gate', False), ('kitchen', True),
         ('kitchen_gate', False), ('sofa_rear_approach', False), ('sofa', True), ('sofa_front_approach', True),
         ('lounge_gate', True), ('stair_approach', False), ('front', True), ('stair_approach', False),
         ('stair_bottom', False), ('stairs_1', False), ('stairs_2', False), ('stairs_3', False), ('stairs_4', False),
         ('stairs_5', False), ('stair_top', False), ('landing', False), ('loft', True), ('bed', True),
         ('bath_aisle', True), ('bath_door', False), ('balcony_gate', False), ('balcony_door', True)]
for i in range(1, 6):   # the staircase: straight line from stair_bottom up to stair_top
    f = i / 6
    NODES[f'stairs_{i}'] = (30, 255 + (-170 - 255) * f, 300 * f)

state = {'seq': 0, 'yaw': 0.0, 'pitch': 0.0, 'shots': 0}


def log(*parts):
    print(time.strftime('%H:%M:%S'), *parts, file=LOG, flush=True)


def write(keys=(), look=(0.0, 0.0)):
    state['seq'] += 1
    now = time.time()
    doc = {'schema': 'sub01.private-ghost-camera.v1', 'expires_utc': now + 2.5, 'captured_utc': now,
           'sequence': state['seq'],
           'keys': {k: (k in keys) for k in ('forward', 'back', 'left', 'right', 'up', 'down', 'fast')},
           'look_delta': [float(look[0]), float(look[1])]}
    TMP.write_text(json.dumps(doc))
    os.chmod(TMP, 0o600)
    os.replace(TMP, REQ)


def receipt():
    try:
        j = json.loads(META.read_text())
        m = re.match(r'X=(-?[\d.]+)\s+Y=(-?[\d.]+)\s+Z=(-?[\d.]+)', j['camera_cm'])
        return (float(m.group(1)), float(m.group(2)), float(m.group(3))), float(j['captured_utc']), int(j['input_sequence'])
    except (OSError, ValueError, KeyError, AttributeError, TypeError):
        return None


def wait_receipt(after_utc, timeout=6):
    end = time.time() + timeout
    while time.time() < end:
        r = receipt()
        if r and r[1] > after_utc:
            return r
        write()
        time.sleep(0.08)
    return None


def turn_to(target_yaw, target_pitch):
    for _ in range(80):
        dyaw = ((target_yaw - state['yaw'] + 180) % 360) - 180
        dp = target_pitch - state['pitch']
        if abs(dyaw) < 0.6 and abs(dp) < 0.6:
            return
        sx = max(-0.34, min(0.34, math.radians(dyaw)))
        sy = max(-0.34, min(0.34, math.radians(dp)))
        write((), (sx, sy))
        state['yaw'] = (state['yaw'] + math.degrees(sx)) % 360
        state['pitch'] = max(-85, min(85, state['pitch'] + math.degrees(sy)))
        time.sleep(0.07)       # the game polls every 25 ms: every sequence is seen exactly once


def goto(name, tol=28, timeout=45):
    x, y, z0 = NODES[name]
    z = z0 + EYE
    started = time.time()
    last_pos, last_move = None, time.time()
    nudges = 0
    while time.time() - started < timeout:
        r = receipt()
        if not r or time.time() - r[1] > 2.5:
            write()
            time.sleep(0.1)
            continue
        (px, py, pz), _, _ = r
        if last_pos is None or math.dist(last_pos, (px, py, pz)) > 4:
            last_pos, last_move = (px, py, pz), time.time()
        dx, dy, dz = x - px, y - py, z - pz
        dh = math.hypot(dx, dy)
        if dh < tol and abs(dz) < tol:
            write()
            return True
        keys = set()
        if dh >= tol:
            want = math.degrees(math.atan2(dy, dx)) % 360
            if abs(((want - state['yaw'] + 180) % 360) - 180) > 4:
                turn_to(want, state['pitch'])
                continue
            keys.add('forward')
        if dz > tol:
            keys.add('up')
        elif dz < -tol:
            keys.add('down')
        if time.time() - last_move > 1.5:       # stuck against something: hop up, then retry
            nudges += 1
            log(f'  stuck near {px:.0f},{py:.0f},{pz:.0f} going to {name}; nudge {nudges}')
            for _ in range(3):
                write({'up'} if nudges % 2 else {'back'})
                time.sleep(0.1)
            write()
            last_move = time.time()
            if nudges >= 4:
                return False
            continue
        far = dh > 90 or abs(dz) > 90
        write(keys)
        time.sleep(0.1 if far else 0.04)
        if not far:
            write()
            time.sleep(0.12)
    return False


def shoot(name, index):
    for yaw in (0, 90, 180, 270):
        turn_to(yaw, PITCH)
        write()
        settled = time.time() + 0.3
        time.sleep(0.3)
        r = wait_receipt(settled)
        if not r:
            log(f'  no frame for {name} yaw {yaw}')
            continue
        target = OUT / f'{index:02d}-{name}-{yaw:03d}.png'
        shutil.copyfile(FRAME, target)
        os.chmod(target, 0o644)
        state['shots'] += 1
        log(f'  shot {target.name} camera={tuple(round(v) for v in r[0])}')


def main():
    log('pilot start key', KEY)
    write()
    r = wait_receipt(0, timeout=20)
    if not r:
        log('no ghost frame within 20 s: policy or directory not accepted')
        sys.exit(1)
    log('ghost camera live at', r[0])
    index = 0
    for name, shot in ROUTE:
        index += 1
        ok = goto(name)
        pos = receipt()
        log(f'{index:02d} {name}: {"reached" if ok else "NOT reached"} at {tuple(round(v) for v in pos[0]) if pos else None}')
        if shot:
            shoot(name, index)
    write()
    log('done; shots', state['shots'])
    try:
        REQ.unlink()
    except OSError:
        pass


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        log('error', type(error).__name__, str(error)[:300])
        raise
