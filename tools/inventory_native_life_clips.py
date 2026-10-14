"""Inventory the real clips for native standing idle and bed/sleep; read-only, Python only.

Measures every candidate from the actual file bytes (GLB JSON plus binary accessors, or a
binary FBX through the existing tools/stage_first_person_assets.inspect_fbx reader). It
never imports, retargets, poses, trims, synthesizes or edits a clip. A role without a
genuine clip on the owner's 65-bone skeleton is reported as missing, never substituted.

    python3 tools/inventory_native_life_clips.py                  # JSON to stdout
    python3 tools/inventory_native_life_clips.py --out docs/proposed/native-life-clips-inventory.json
    python3 tools/inventory_native_life_clips.py --extra Idle=/srv/private/SourceAssets/Breathing_Idle.fbx

`--extra ROLE=PATH` (server, private sources such as a downloaded Mixamo FBX that stays out
of Git) inventories one more file for ROLE; its record is gated exactly like the others.

Coordinates: glTF, metres, +Y up, measured from the clip's own floor (y=0) after the
armature node's 0.01 scale. Hips-local translations are reported in the clip's centimetres.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

SCHEMA = 'sub01.native-life-clips-inventory.v1'
OWNER = 'web/room/char_mixamo.glb'          # the skin SUB01_OriginalOwner was imported from (rig_source)
ARMATURE = 'mixamo'
BONE_PREFIX = 'mixamorig:'
OWNER_BONES = 65
REST_TOLERANCE = 1e-4                       # same tolerance class as inventory_native_seating (1e-5 on TRS)

# Acceptance numbers (stated, not tuned to a result).
LOOP_MAX_JOINT_CM = 1.0      # any joint, world, first vs last sample
LOOP_MAX_ROTATION_DEG = 2.0  # any rotation track, first vs last sample
IDLE_MAX_HIPS_TRAVEL_CM = 5.0
STANDING_MAX_TILT_DEG = 30.0
STANDING_MIN_LEG_EXTENSION = 0.85   # (hips height - lower foot height) / owner rest thigh+shin length
LYING_MIN_TILT_DEG = 60.0
SAMPLES = 9                  # evenly spaced FK samples per clip (first and last included)

# Provenance classes. Only these may ever feed a native binding.
# operator_declared_capture: only a file root names on the command line (--extra), declaring it a
# genuine capture (e.g. a Mixamo FBX kept out of Git); it is still measured and gated like the rest.
ACCEPTED_PROVENANCE = {'mixamo_capture', 'third_party_authored_with_permission', 'operator_declared_capture'}
# ADDITIVE (owner direction, 14 Oct 2026; tools/bed_transition_corrections.py): derived_library_asset is a library
# clip whose derivation is documented and whose capture method is not (e.g. preview/mh-motion clips retargeted via
# mh_retarget.mjs). It is never called a capture. Such a file (--derived ROLE=PATH) may become a Candidate ONLY when
# the label is visible in the file itself (asset.extras.sub01_provenance.label) and it then stays in the row's
# provenance, provenance_label and verdict_reason. It is deliberately NOT in ACCEPTED_PROVENANCE.
DERIVED_LIBRARY_ASSET = 'derived_library_asset'

# Every role the native life adapter needs, and the files the repository actually holds for it.
ROLES = {
    'Idle': 'standing idle that loops in place (breathing, weight shift), on the owner skeleton',
    'LieDown': 'standing beside the bed -> lying on the mattress, on the owner skeleton',
    'SleepLoop': 'asleep, lying, looping, on the owner skeleton',
    'GetUp': 'lying -> standing beside the bed, on the owner skeleton',
}

CANDIDATES = [
    # (role, path, animation name or None, provenance class, provenance note)
    ('Idle', 'web/room/boy_idle.glb', None, 'ai_generated',
     'Earlier Meshy/Higgsfield character clip (web/room/CREDITS.md); 26-node rig.'),
    ('Idle', 'web/room/boy_m_idle.glb', None, 'ai_generated',
     'NVIDIA ARDY text-to-motion output (web/room/CREDITS.md "clips generated with NVIDIA ARDY").'),
    ('Idle', 'web/room/boy_moves.glb', 'stand_idle', 'retargeted_library_clip',
     'Quaternius UAL Idle_Loop retargeted onto the earlier boy rig (CREDITS.md); not the owner skeleton.'),
    ('Idle', 'web/room/char_v5.glb', 'idle', 'unknown',
     'Tripo v5 rig idle (41-bone v5 rig), not the owner skeleton.'),
    ('LieDown', 'web/room/mh_mx/room_bed_lie.glb', None, 'v5_carryover_source_undocumented',
     'mh_v5 clip carried onto the owner skeleton by room_build/kimodo/mx_convert.mjs (web/room/mh_mx/README.md); '
     'its original source (preview/mh-motion) is not documented in this repository.'),
    ('GetUp', 'web/room/mh_mx/room_bed_wake.glb', None, 'v5_carryover_source_undocumented',
     'As room_bed_lie: v5 carry-over, original source undocumented here.'),
    ('SleepLoop', 'web/room/mh_mx/room_bedtime.glb', None, 'v5_carryover_source_undocumented',
     'Desk stretch, walk to bed, lie down; the web page holds its LAST frame as the sleeping pose (a still).'),
    ('SleepLoop', 'web/room/desk_states/bed/sleep_side.glb', None, 'third_party_authored_with_permission',
     'SovaSims bed clip (G23), used with the author\'s permission (web/room/desk_states/README.md); preview-only '
     'licence, capture method not documented; fitted to the web room bed, not the native bed.'),
    ('SleepLoop', 'web/room/desk_states/bed/sleep_back.glb', None, 'third_party_authored_with_permission',
     'SovaSims bed clip (G23), as sleep_side.'),
    ('SleepLoop', 'web/room/desk_states/bed/sleep_back_idle.glb', None, 'third_party_authored_with_permission',
     'SovaSims bed clip (G23), as sleep_side.'),
    ('SleepLoop', 'web/room/desk_states/bed/sleep_roll_to_back.glb', None, 'third_party_authored_with_permission',
     'SovaSims bed clip (G23): a one-shot roll from side to back, not a loop.'),
    ('SleepLoop', 'web/room/mh_v5/room_sleeping_idle.glb', None, 'mixamo_capture',
     'Mixamo Sleeping_Idle retargeted onto the v5 rig (room_build/kimodo/mixamo_clips.json); not the owner skeleton.'),
    ('SleepLoop', 'web/room/mh_v5/room_laying_sleeping.glb', None, 'mixamo_capture',
     'Mixamo Laying_Sleeping retargeted onto the v5 rig; not the owner skeleton.'),
    ('LieDown', 'web/room/mh_v5/room_bed_lie.glb', None, 'v5_carryover_source_undocumented',
     'The v5-rig original of mh_mx/room_bed_lie; not the owner skeleton.'),
]


# ------------------------------------------------------------------ GLB reading (pure Python)
class Compressed(ValueError):
    """An accessor needs a meshopt decoder; values are never guessed from compressed bytes."""


def read_glb(path: Path):
    raw = path.read_bytes()
    if raw[:4] != b'glTF' or struct.unpack_from('<I', raw, 4)[0] != 2:
        raise ValueError(f'{path}: not a glTF 2 binary')
    doc, binary, offset = None, b'', 12
    while offset < len(raw):
        size, kind = struct.unpack_from('<II', raw, offset)
        chunk = raw[offset + 8:offset + 8 + size]
        if kind == 0x4E4F534A:
            doc = json.loads(chunk)
        elif kind == 0x004E4942:
            binary = chunk
        offset += 8 + size
    if doc is None:
        raise ValueError(f'{path}: missing JSON chunk')
    return doc, binary, hashlib.sha256(raw).hexdigest()


def accessor(doc, binary, index):
    a = doc['accessors'][index]
    if 'sparse' in a:
        raise ValueError('sparse accessor unsupported')
    view = doc['bufferViews'][a['bufferView']]
    if view.get('buffer', 0) != 0 or 'EXT_meshopt_compression' in view.get('extensions', {}):
        raise Compressed('accessor is meshopt-compressed')
    width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[a['type']]
    fmt, size, norm = {5126: ('f', 4, 0), 5122: ('h', 2, 32767), 5120: ('b', 1, 127),
                       5123: ('H', 2, 65535), 5121: ('B', 1, 255), 5125: ('I', 4, 0)}[a['componentType']]
    stride = view.get('byteStride', width * size)
    start = view.get('byteOffset', 0) + a.get('byteOffset', 0)
    out = []
    for i in range(a['count']):
        v = struct.unpack_from('<' + fmt * width, binary, start + i * stride)
        if norm and a.get('normalized'):
            v = tuple(max(x / norm, -1.0) for x in v)
        out.append(v)
    return out


# ------------------------------------------------------------------ math
def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def qrot(q, v):
    x, y, z, w = q
    u = (x, y, z)
    t = (2 * (u[1] * v[2] - u[2] * v[1]), 2 * (u[2] * v[0] - u[0] * v[2]), 2 * (u[0] * v[1] - u[1] * v[0]))
    return (v[0] + w * t[0] + (u[1] * t[2] - u[2] * t[1]),
            v[1] + w * t[1] + (u[2] * t[0] - u[0] * t[2]),
            v[2] + w * t[2] + (u[0] * t[1] - u[1] * t[0]))


def qnorm(q):
    n = math.sqrt(sum(c * c for c in q)) or 1.0
    return tuple(c / n for c in q)


def qangle_deg(a, b):
    dot = abs(sum(x * y for x, y in zip(qnorm(a), qnorm(b))))
    return math.degrees(2 * math.acos(min(1.0, dot)))


def slerp(a, b, t):
    dot = sum(x * y for x, y in zip(a, b))
    if dot < 0:
        b, dot = tuple(-c for c in b), -dot
    if dot > .9995:
        return qnorm(tuple(x + (y - x) * t for x, y in zip(a, b)))
    theta = math.acos(dot)
    s = math.sin(theta)
    wa, wb = math.sin((1 - t) * theta) / s, math.sin(t * theta) / s
    return tuple(wa * x + wb * y for x, y in zip(a, b))


def r6(v):
    return round(v, 6)


# ------------------------------------------------------------------ skeleton + clip model
def skeleton(doc):
    nodes = doc.get('nodes', [])
    parent = {c: i for i, n in enumerate(nodes) for c in n.get('children', [])}
    bones = {n['name']: i for i, n in enumerate(nodes) if n.get('name', '').startswith(BONE_PREFIX)}
    return nodes, parent, bones


def owner_reference():
    doc, _, sha = read_glb(ROOT / OWNER)
    nodes, parent, bones = skeleton(doc)
    rest = {name: (nodes[i].get('translation', [0, 0, 0]), nodes[i].get('rotation', [0, 0, 0, 1]),
                   nodes[i].get('scale', [1, 1, 1])) for name, i in bones.items()}
    parents = {name: nodes[parent[i]].get('name') if i in parent else None for name, i in bones.items()}
    skin_joints = sorted(nodes[j]['name'] for j in doc['skins'][0]['joints'])
    return {'sha256': sha, 'bones': sorted(bones), 'rest': rest, 'parents': parents, 'skin_joints': skin_joints}


class Channels:
    def __init__(self, doc, binary, animation):
        self.tracks = {}
        self.interpolations = set()
        for c in animation['channels']:
            s = animation['samplers'][c['sampler']]
            self.interpolations.add(s.get('interpolation', 'LINEAR'))
            times = [t[0] for t in accessor(doc, binary, s['input'])]
            self.tracks[(c['target']['node'], c['target']['path'])] = (times, accessor(doc, binary, s['output']))
        if self.interpolations - {'LINEAR', 'STEP'}:
            raise ValueError(f'unsupported interpolation {sorted(self.interpolations)}')
        self.start = min(t[0][0] for t in self.tracks.values())
        self.end = max(t[0][-1] for t in self.tracks.values())

    def sample(self, node, path, t, default):
        track = self.tracks.get((node, path))
        if not track:
            return tuple(default)
        times, values = track
        if t <= times[0]:
            return tuple(values[0])
        if t >= times[-1]:
            return tuple(values[-1])
        i = bisect.bisect_right(times, t) - 1
        if 'STEP' in self.interpolations:
            return tuple(values[i])
        w = (t - times[i]) / (times[i + 1] - times[i])
        if path == 'rotation':
            return slerp(values[i], values[i + 1], w)
        return tuple(a + (b - a) * w for a, b in zip(values[i], values[i + 1]))


class RestPose:
    """No animation: every node at its file rest transform."""
    @staticmethod
    def sample(node, path, t, default):
        return tuple(default)


def body_shape(world, bones):
    """Every joint relative to the hips, in the hips' own frame (cm): a frame-independent pose."""
    hp, hq, _ = world[bones[BONE_PREFIX + 'Hips']]
    inv = (-hq[0], -hq[1], -hq[2], hq[3])
    return {name: qrot(inv, tuple((p - h) * 100 for p, h in zip(world[i][0], hp))) for name, i in bones.items()}


def world_pose(nodes, parent, channels, t):
    """World (t, q, s) of every node at time t; uniform scale only (refused otherwise)."""
    cache = {}

    def visit(i):
        if i in cache:
            return cache[i]
        n = nodes[i]
        if n.get('matrix'):
            raise ValueError('matrix node transforms are not interpreted silently')
        lt = channels.sample(i, 'translation', t, n.get('translation', [0, 0, 0]))
        lq = channels.sample(i, 'rotation', t, n.get('rotation', [0, 0, 0, 1]))
        ls = channels.sample(i, 'scale', t, n.get('scale', [1, 1, 1]))
        if max(ls) - min(ls) > 1e-9:
            raise ValueError('non-uniform node scale')
        if i in parent:
            pt, pq, ps = visit(parent[i])
            r = qrot(pq, lt)
            cache[i] = ((pt[0] + ps * r[0], pt[1] + ps * r[1], pt[2] + ps * r[2]), qmul(pq, lq), ps * ls[0])
        else:
            cache[i] = (lt, lq, ls[0])
        return cache[i]

    for i in range(len(nodes)):
        visit(i)
    return cache


def posture(world, bones, hips_rest_world_q, leg_length_m):
    hips, head = world[bones[BONE_PREFIX + 'Hips']][0], world[bones[BONE_PREFIX + 'Head']][0]
    feet = min(world[bones[BONE_PREFIX + side + 'Foot']][0][1] for side in ('Left', 'Right'))
    extension = (hips[1] - feet) / leg_length_m
    axis = tuple(h - p for h, p in zip(head, hips))
    length = math.sqrt(sum(c * c for c in axis)) or 1.0
    tilt = math.degrees(math.acos(max(-1.0, min(1.0, axis[1] / length))))
    # The character's front: the owner's rest-pose forward (+Z) carried by the hips' rotation since rest.
    hq = world[bones[BONE_PREFIX + 'Hips']][1]
    inv_rest = (-hips_rest_world_q[0], -hips_rest_world_q[1], -hips_rest_world_q[2], hips_rest_world_q[3])
    front = qrot(qmul(hq, inv_rest), (0.0, 0.0, 1.0))
    if tilt <= STANDING_MAX_TILT_DEG:
        kind = 'standing' if extension >= STANDING_MIN_LEG_EXTENSION else 'sitting_or_crouching'
    elif tilt < LYING_MIN_TILT_DEG:
        kind = 'reclined_or_sitting'
    elif front[1] > .7:
        kind = 'lying_supine'
    elif front[1] < -.7:
        kind = 'lying_prone'
    else:
        kind = 'lying_side'
    lowest = min(world[i][0][1] for i in bones.values())
    torso_heading = math.degrees(math.atan2(axis[0], axis[2])) if tilt >= LYING_MIN_TILT_DEG else None
    return {'kind': kind, 'torso_tilt_from_vertical_deg': r6(tilt), 'hips_height_m': r6(hips[1]),
            'head_height_m': r6(head[1]), 'lowest_joint_height_m': r6(lowest), 'leg_extension': r6(extension),
            'hips_world_m': [r6(c) for c in hips], 'front_up_component': r6(front[1]),
            'torso_heading_deg_about_y': r6(torso_heading) if torso_heading is not None else None}


def owner_skeleton_check(doc, owner):
    nodes, parent, bones = skeleton(doc)
    names = sorted(bones)
    errors = []
    if len(names) != OWNER_BONES:
        errors.append(f'{len(names)} {BONE_PREFIX}* joints, owner has {OWNER_BONES}')
    if set(names) != set(owner['bones']):
        missing = sorted(set(owner['bones']) - set(names))
        errors.append(f'joint names differ from owner (missing {len(missing)}, extra {len(set(names) - set(owner["bones"]))})')
    max_rest = 0.0
    if not errors:
        for name, i in bones.items():
            p = nodes[parent[i]].get('name') if i in parent else None
            if p != owner['parents'][name]:
                errors.append(f'{name} parent {p} != owner {owner["parents"][name]}')
            for got, ref in zip((nodes[i].get('translation', [0, 0, 0]), nodes[i].get('rotation', [0, 0, 0, 1]),
                                 nodes[i].get('scale', [1, 1, 1])), owner['rest'][name]):
                max_rest = max(max_rest, max(abs(a - b) for a, b in zip(got, ref)))
        hips = bones[BONE_PREFIX + 'Hips']
        root = nodes[parent[hips]] if hips in parent else None
        if not root or root.get('name') != ARMATURE or root.get('scale') != [.01, .01, .01] \
                or any(root.get(k) not in (None, [0, 0, 0], [0, 0, 0, 1]) for k in ('translation', 'rotation')) or root.get('matrix'):
            errors.append('armature node is not the owner\'s unrotated 0.01-scale "mixamo" root')
    rest_match = not errors and max_rest <= REST_TOLERANCE
    if not errors and not rest_match:
        errors.append(f'rest pose differs from owner by up to {max_rest:.6g}')
    return {'joint_count': len(names), 'joint_names_sha256': hashlib.sha256('\n'.join(names).encode()).hexdigest(),
            'same_owner_skeleton': not errors, 'max_rest_trs_error': r6(max_rest), 'errors': errors}


def glb_record(path: Path, animation_name, owner):
    doc, binary, sha = read_glb(path)
    nodes, parent, bones = skeleton(doc)
    anims = doc.get('animations', [])
    picked = [a for a in anims if animation_name is None or a.get('name') == animation_name]
    rec = {'format': 'GLB', 'sha256': sha, 'bytes': path.stat().st_size, 'node_count': len(nodes),
           'all_joint_like_nodes': len([n for n in nodes if 'mesh' not in n]),
           'animations_in_file': [a.get('name') for a in anims]}
    if len(picked) != 1:
        rec['error'] = f'expected exactly one animation {animation_name!r}, found {len(picked)}'
        return rec
    anim = picked[0]
    rec['animation'] = anim.get('name')
    rec['skeleton'] = owner_skeleton_check(doc, owner)
    if not rec['skeleton']['same_owner_skeleton']:
        # Still measure duration from accessor bounds (stored in JSON, valid even when compressed).
        ends = [doc['accessors'][s['input']].get('max', [None])[0] for s in anim['samplers']]
        starts = [doc['accessors'][s['input']].get('min', [None])[0] for s in anim['samplers']]
        if None not in ends and None not in starts:
            rec['duration_s'] = r6(max(ends) - min(starts))
        rec['measured'] = False
        return rec
    try:
        ch = Channels(doc, binary, anim)
    except Compressed as error:
        rec['error'] = str(error)
        return rec
    times = sorted({t for tr in ch.tracks.values() for t in tr[0]})
    steps = sorted(b - a for a, b in zip(times, times[1:]))
    median = steps[len(steps) // 2] if steps else 0
    rec['duration_s'] = r6(ch.end - ch.start)
    rec['frame_rate_hz'] = r6(1 / median) if median else None
    rec['key_count'] = len(times)
    rec['uniform_keys'] = bool(steps) and steps[-1] - steps[0] < 1e-3
    rec['interpolation'] = sorted(ch.interpolations)
    hips = bones[BONE_PREFIX + 'Hips']
    rec['animated_bones'] = len({n for n, _ in ch.tracks if n in bones.values()})
    # Non-root bone translation tracks: bone lengths that move away from the owner's rest.
    drift = 0.0
    for (node, path), (_, values) in ch.tracks.items():
        if path != 'translation' or node == hips or node not in bones.values():
            continue
        ref = owner['rest'][nodes[node]['name']][0]
        drift = max(drift, max(max(abs(v[k] - ref[k]) for k in range(3)) for v in values))
    rec['non_root_translation_tracks'] = sum(1 for n, p in ch.tracks if p == 'translation' and n != hips)
    rec['max_bone_translation_drift_from_owner_rest_cm'] = r6(drift)
    rec['scale_tracks'] = sum(1 for _, p in ch.tracks if p == 'scale')
    # Hips local translation (clip centimetres) over every key.
    ht = ch.tracks.get((hips, 'translation'))
    if ht:
        values = ht[1]
        first = values[0]
        horizontal = max(math.hypot(v[0] - first[0], v[2] - first[2]) for v in values)
        rec['hips_local_cm'] = {'first': [r6(c) for c in first], 'last': [r6(c) for c in values[-1]],
                                'min': [r6(min(v[k] for v in values)) for k in range(3)],
                                'max': [r6(max(v[k] for v in values)) for k in range(3)],
                                'max_horizontal_from_first': r6(horizontal),
                                'net_horizontal_first_to_last': r6(math.hypot(values[-1][0] - first[0], values[-1][2] - first[2])),
                                'height_range': r6(max(v[1] for v in values) - min(v[1] for v in values))}
    # World FK samples (metres): posture, lying height/orientation, loop.
    rest_world = world_pose(nodes, parent, RestPose(), 0)
    hips_rest_q = rest_world[hips][1]
    leg = math.dist(rest_world[bones[BONE_PREFIX + 'LeftUpLeg']][0], rest_world[bones[BONE_PREFIX + 'LeftLeg']][0]) \
        + math.dist(rest_world[bones[BONE_PREFIX + 'LeftLeg']][0], rest_world[bones[BONE_PREFIX + 'LeftFoot']][0])
    rec['owner_rest_leg_length_m'] = r6(leg)
    samples = []
    for k in range(SAMPLES):
        t = ch.start + (ch.end - ch.start) * k / (SAMPLES - 1)
        w = world_pose(nodes, parent, ch, t)
        samples.append((t, w, posture(w, bones, hips_rest_q, leg)))
    rec['posture_samples'] = [dict(time_s=r6(t), **p) for t, _, p in samples]
    first_w, last_w = samples[0][1], samples[-1][1]
    joint_cm = max(math.dist(first_w[i][0], last_w[i][0]) * 100 for i in bones.values())
    rot_deg = 0.0
    for (node, path), (_, values) in ch.tracks.items():
        if path == 'rotation' and node in bones.values():
            rot_deg = max(rot_deg, qangle_deg(values[0], values[-1]))
    rec['loop'] = {'max_joint_world_delta_cm': r6(joint_cm), 'max_rotation_delta_deg': r6(rot_deg),
                   'loops': joint_cm <= LOOP_MAX_JOINT_CM and rot_deg <= LOOP_MAX_ROTATION_DEG,
                   'rule': f'first vs last key: every joint <= {LOOP_MAX_JOINT_CM} cm and every rotation <= {LOOP_MAX_ROTATION_DEG} deg'}
    rec['_shape'] = (body_shape(first_w, bones), body_shape(last_w, bones))
    kinds = [p['kind'] for _, _, p in samples]
    rec['posture'] = {'first': kinds[0], 'last': kinds[-1], 'all': sorted(set(kinds))}
    rec['measured'] = True
    return rec


def fbx_record(path: Path, owner):
    from stage_first_person_assets import inspect_fbx  # existing pure-Python binary FBX reader (read-only)
    raw = path.read_bytes()
    info = inspect_fbx(path)
    rec = {'format': 'FBX', 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
    if 'unsupported' in info:
        rec['error'] = info['unsupported']
        return rec
    names = sorted(set(info['joint_names']))
    errors = []
    if len(names) != OWNER_BONES:
        errors.append(f'{len(names)} joints, owner has {OWNER_BONES}')
    if set(names) != set(owner['bones']):
        errors.append('joint names differ from owner')
    rec['skeleton'] = {'joint_count': len(names), 'joint_names_sha256': hashlib.sha256('\n'.join(names).encode()).hexdigest(),
                       'same_owner_skeleton': not errors, 'errors': errors,
                       'note': 'FBX: names and hierarchy only here; rest-pose equality is checked by the server import on the owner USkeleton.'}
    if errors:
        rec['measured'] = False
        return rec
    clips = info.get('clips') or []
    if not clips:
        rec['error'] = 'no animation curves'
        return rec
    tracks = clips[0]['tracks']
    rec['duration_s'] = r6(clips[0]['duration_s'])
    keys = max(t['keys'] for t in tracks)
    rec['frame_rate_hz'] = r6((keys - 1) / clips[0]['duration_s']) if clips[0]['duration_s'] else None
    hips = [t for t in tracks if t['node'] == BONE_PREFIX + 'Hips' and 'Translation' in str(t['path'])]
    if hips:
        rec['hips_local_cm'] = {f'{t["axis"]}': {'first': r6(t['first_value']), 'last': r6(t['last_value']), 'range': r6(t['range'])}
                                for t in hips}
    rot = [abs(t['last_value'] - t['first_value']) for t in tracks if 'Rotation' in str(t['path'])]
    pos = [abs(t['last_value'] - t['first_value']) for t in tracks if 'Translation' in str(t['path'])]
    rec['loop'] = {'max_rotation_curve_delta_deg': r6(max(rot, default=0)), 'max_translation_curve_delta_cm': r6(max(pos, default=0)),
                   'loops': bool(tracks) and max(rot, default=0) <= LOOP_MAX_ROTATION_DEG and max(pos, default=0) <= LOOP_MAX_JOINT_CM,
                   'rule': 'first vs last key of every Euler rotation / translation curve'}
    rec['posture'] = None   # FBX: posture needs the server import (no FK of FBX pre-rotations here)
    rec['measured'] = not errors
    return rec


def role_verdict(role, rec, provenance):
    """Why this file can or cannot be the native clip for role; explicit, never inferred from a name."""
    if rec.get('error') and 'skeleton' not in rec:
        return 'Unreadable', rec['error']
    if not rec.get('skeleton', {}).get('same_owner_skeleton'):
        return 'SkeletonMismatch', '; '.join(rec.get('skeleton', {}).get('errors', [])) or 'not the owner skeleton'
    if provenance == DERIVED_LIBRARY_ASSET:                     # additive: see DERIVED_LIBRARY_ASSET
        if (rec.get('provenance_label') or {}).get('label') != DERIVED_LIBRARY_ASSET:
            return 'ProvenanceLabelMissing', 'a derived_library_asset must carry asset.extras.sub01_provenance.label in the file'
    elif provenance not in ACCEPTED_PROVENANCE:
        return 'ProvenanceUnverified', f'provenance class {provenance!r} is not a documented genuine capture'
    if rec.get('error'):
        return 'Unreadable', rec['error']
    if rec.get('format') == 'FBX':
        return ('Candidate', 'owner names; loop and posture verified only by the server import') if rec['loop']['loops'] \
            else ('NotLooping', 'first and last keys differ') if role in ('Idle', 'SleepLoop') else ('Candidate', 'owner names')
    post, loop = rec['posture'], rec['loop']
    hips = rec.get('hips_local_cm', {})
    if role == 'Idle':
        if post['all'] != ['standing']:
            return 'WrongPosture', f'postures {post["all"]}, an idle must be standing throughout'
        if hips.get('max_horizontal_from_first', 0) > IDLE_MAX_HIPS_TRAVEL_CM:
            return 'NotStationary', f'hips travel {hips["max_horizontal_from_first"]} cm > {IDLE_MAX_HIPS_TRAVEL_CM}'
        return ('Candidate', 'standing, stationary, loops') if loop['loops'] else ('NotLooping', 'first and last poses differ')
    if role == 'SleepLoop':
        if not all(k.startswith('lying') for k in post['all']):
            return 'WrongPosture', f'postures {post["all"]}, a sleep loop must be lying throughout'
        return ('Candidate', 'lying throughout, loops') if loop['loops'] else ('NotLooping', 'first and last poses differ')
    if role == 'LieDown':
        ok = post['first'] == 'standing' and post['last'].startswith('lying')
        return ('Candidate', 'ends lying') if ok else ('WrongPosture', f'{post["first"]} -> {post["last"]}')
    if role == 'GetUp':
        ok = post['first'].startswith('lying') and post['last'] == 'standing'
        return ('Candidate', 'lying -> standing') if ok else ('WrongPosture', f'{post["first"]} -> {post["last"]}')
    return 'Unknown', role


def continuity(a, b):
    """End pose of clip a vs start pose of clip b, for a candidate chain.

    hips_world_delta_cm compares the raw clip frames (meaningful only when both clips share one
    frame); body_shape_max_delta_cm compares the poses themselves (joints in the hips' frame), so
    it holds whatever frame each clip was authored in. A crossfade cannot hide either gap.
    """
    if not (a.get('measured') and b.get('measured')):
        return None
    pa, pb = a['posture_samples'][-1], b['posture_samples'][0]
    end, start = a['_shape'][1], b['_shape'][0]
    return {'hips_world_delta_cm': r6(math.dist(pa['hips_world_m'], pb['hips_world_m']) * 100),
            'hips_height_delta_cm': r6((pb['hips_height_m'] - pa['hips_height_m']) * 100),
            'body_shape_max_delta_cm': r6(max(math.dist(end[n], start[n]) for n in end)),
            'kinds': [pa['kind'], pb['kind']]}


def owner_skeleton_scan(owner, listed):
    """Every other animated GLB under web/ on the owner skeleton: proves what exists, nothing more.

    idle_shaped = standing throughout, hips within IDLE_MAX_HIPS_TRAVEL_CM, loops. Shape is not
    provenance or purpose: an activity clip (phone, walk-in-place) is never an idle substitute.
    """
    rows = []
    for path in sorted((ROOT / 'web').rglob('*.glb')):
        rel = path.relative_to(ROOT).as_posix()
        if rel in listed or rel == OWNER:
            continue
        try:
            doc, _, _ = read_glb(path)
        except ValueError:
            continue
        if not doc.get('animations') or len(skeleton(doc)[2]) != OWNER_BONES:
            continue
        for anim in doc['animations']:
            rec = glb_record(path, anim.get('name'), owner)
            if not rec.get('measured'):
                rows.append({'file': rel, 'animation': anim.get('name'), 'measured': False,
                             'reason': rec.get('error') or rec['skeleton']['errors']})
                continue
            travel = rec.get('hips_local_cm', {}).get('max_horizontal_from_first', 0)
            rows.append({'file': rel, 'animation': anim.get('name'), 'measured': True, 'duration_s': rec['duration_s'],
                         'postures': rec['posture']['all'], 'loops': rec['loop']['loops'], 'hips_travel_cm': travel,
                         'max_bone_translation_drift_cm': rec['max_bone_translation_drift_from_owner_rest_cm'],
                         'idle_shaped': rec['posture']['all'] == ['standing'] and travel <= IDLE_MAX_HIPS_TRAVEL_CM and rec['loop']['loops']})
    return rows


def derived_label(path: Path):
    """Additive: the provenance label a derived clip carries in its own GLB (asset.extras.sub01_provenance), or None."""
    try:
        doc, _, _ = read_glb(path)
    except ValueError:
        return None
    label = doc.get('asset', {}).get('extras', {}).get('sub01_provenance')
    return {'label': label.get('label'), 'text': label.get('text')} if isinstance(label, dict) else None


def inventory(extra=(), derived=()):
    owner = owner_reference()
    rows = []
    declared = [(r, p, None, 'operator_declared_capture', 'declared a genuine capture by the operator (--extra)') for r, p in extra]
    # Additive: derived library assets (--derived), labelled, never declared captures.
    declared += [(r, p, None, DERIVED_LIBRARY_ASSET, 'derived library asset (--derived); capture method undocumented')
                 for r, p in derived]
    for role, rel, anim, prov, note in list(CANDIDATES) + declared:
        path = Path(rel) if Path(rel).is_absolute() else ROOT / rel
        if not path.is_file():
            rows.append({'role': role, 'file': rel, 'missing_file': True, 'verdict': 'ClipMissing'})
            continue
        if path.suffix.lower() == '.fbx':
            rec = fbx_record(path, owner)
        else:
            rec = glb_record(path, anim, owner)
        if prov == DERIVED_LIBRARY_ASSET:                       # additive: the label stays visible in the row
            rec['provenance_label'] = derived_label(path) if path.suffix.lower() == '.glb' else None
        verdict, reason = role_verdict(role, rec, prov)
        if prov == DERIVED_LIBRARY_ASSET and verdict == 'Candidate':
            reason = f'{DERIVED_LIBRARY_ASSET} (label visible; not a capture): {reason}'
        rows.append({'role': role, 'file': rel, 'provenance': prov, 'provenance_note': note, **rec,
                     'verdict': verdict, 'verdict_reason': reason})
    by_file = {r['file']: r for r in rows}
    chains = {
        'room_bed_lie -> sleep_side': continuity(by_file['web/room/mh_mx/room_bed_lie.glb'], by_file['web/room/desk_states/bed/sleep_side.glb']),
        'room_bed_lie -> sleep_back_idle': continuity(by_file['web/room/mh_mx/room_bed_lie.glb'], by_file['web/room/desk_states/bed/sleep_back_idle.glb']),
        'sleep_back_idle -> room_bed_wake': continuity(by_file['web/room/desk_states/bed/sleep_back_idle.glb'], by_file['web/room/mh_mx/room_bed_wake.glb']),
        'room_bed_lie -> room_bed_wake': continuity(by_file['web/room/mh_mx/room_bed_lie.glb'], by_file['web/room/mh_mx/room_bed_wake.glb']),
    }
    scan = owner_skeleton_scan(owner, set(by_file))
    for r in rows:
        r.pop('_shape', None)
    accepted = {role: sorted(r['file'] for r in rows if r['role'] == role and r['verdict'] == 'Candidate') for role in ROLES}
    return {
        'schema': SCHEMA, 'source_only': True,
        'owner': {'file': OWNER, 'sha256': owner['sha256'], 'joint_count': len(owner['bones']),
                  'skin_joints_equal_bones': owner['skin_joints'] == owner['bones'],
                  'native_asset': '/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner'},
        'roles': ROLES,
        'thresholds': {'loop_max_joint_cm': LOOP_MAX_JOINT_CM, 'loop_max_rotation_deg': LOOP_MAX_ROTATION_DEG,
                       'idle_max_hips_travel_cm': IDLE_MAX_HIPS_TRAVEL_CM, 'standing_max_tilt_deg': STANDING_MAX_TILT_DEG,
                       'lying_min_tilt_deg': LYING_MIN_TILT_DEG, 'standing_min_leg_extension': STANDING_MIN_LEG_EXTENSION,
                       'rest_trs_tolerance': REST_TOLERANCE},
        'accepted_provenance': sorted(ACCEPTED_PROVENANCE),
        'candidates': rows,
        'chain_continuity': chains,
        'owner_skeleton_scan': scan,
        'idle_shaped_in_scan': sorted(r['file'] for r in scan if r.get('idle_shaped')),
        'accepted_by_role': accepted,
        'missing_roles': sorted(role for role, files in accepted.items() if not files),
        'native_bed_surface_report': None,
        'notes': ['No FBX source for idle or bed exists in the repository; the Mixamo FBX are kept out of Git by licence.',
                  'Bed clips were fitted to the web room bed; none is measured against the native house bed.'],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--extra', action='append', default=[], help='ROLE=PATH, a private source on the server')
    parser.add_argument('--derived', action='append', default=[],
                        help='ROLE=PATH, a labelled derived_library_asset GLB (additive; see DERIVED_LIBRARY_ASSET)')
    args = parser.parse_args(argv)
    extra, derived = [], []
    for items, out, flag in ((args.extra, extra, '--extra'), (args.derived, derived, '--derived')):
        for item in items:
            role, _, path = item.partition('=')
            if role not in ROLES or not path:
                parser.error(f'{flag} expects ROLE=PATH with ROLE in {sorted(ROLES)}')
            out.append((role, path))
    text = json.dumps(inventory(extra, derived), indent=1, sort_keys=True) + '\n'
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
    else:
        sys.stdout.write(text)


if __name__ == '__main__':
    main()
