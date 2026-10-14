"""Verify a standing-idle candidate clip against the owner skeleton; measure only, never fix.

    python3 tools/verify_life_idle_candidate.py CANDIDATE.glb [--owner web/room/char_mixamo.glb]
        [--animation NAME] [--mapping MAP.json] [--out REPORT.json] [--no-soles]

CANDIDATE is a GLB or .gltf (JSON + .bin or data: URIs), e.g. a Mixamo FBX converted with
room_build/kimodo/mixamo_glb.mjs, or the output of tools/retarget_life_clip.py. A
meshopt-compressed file is first decoded with the existing tools/uncompress_unreal_glb.mjs (the
vendored official decoder) into a temporary file; nothing is decoded in Python.

Two modes:
* default, bone for bone: the candidate must BE the owner skeleton (the 65 semantic joints with the
  owner's parents; the Mixamo prefix may differ, e.g. mixamorig1:), plus at most one constant
  structural root (tools/native_life_skeleton_parity.py: the 66-vs-65 rule, never a raw count).
  Only this mode can return "accepted_for_binding": true.
* --mapping MAP.json ({"<owner joint, no prefix>": "<candidate node name>" | null, ...}, naming
  every one of the owner's 65 joints explicitly): a retarget SOURCE on another rig. Reports the
  measured bone-length ratios and the source's own stretch, loop, travel and feet; never binding.

Invariants (each: pass/fail + measured numbers + threshold; overall pass = all pass):
  skeleton, rest_offsets (per-bone offset and length vs owner, <= 0.05 cm), bone_length_constancy
  (every frame, <= 0.05 cm), root_in_place (hips horizontal travel, structural root constant),
  loop (start/end hips-relative pose <= 0.5 cm and velocity <= 5 cm/s), feet_joints (foot/toe joint
  height std/range, slide, no sinking below the owner's rest joint height), soles (the owner's fixed
  plantar vertex set skinned per frame: floor penetration, lift and slide per foot), standing,
  timing (30 fps uniform keys, 1..60 s), symmetry (left joints stay on the left).
Exit code 0 only when every invariant passes; 1 otherwise. A failing clip is refused; nothing is
posed, trimmed or edited here.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import life_gltf as G  # noqa: E402
import native_life_skeleton_parity as parity  # noqa: E402

SCHEMA = 'sub01.life-idle-candidate-verification.v1'
OWNER = ROOT / 'web/room/char_mixamo.glb'
PREFIX = re.compile(r'^mixamorig\d*[:_]?', re.I)
OWNER_PREFIX = 'mixamorig:'

# Acceptance numbers (stated, not tuned to a result).
REST_TOLERANCE_CM = 0.05
STRETCH_TOLERANCE_CM = 0.05
HIPS_MAX_TRAVEL_CM = 5.0            # same bound as inventory_native_life_clips IDLE_MAX_HIPS_TRAVEL_CM
HIPS_MAX_NET_CM = 0.5
LOOP_MAX_POSE_CM = 0.5
LOOP_MAX_VELOCITY_CM_S = 5.0
FOOT_MAX_HEIGHT_STD_CM = 0.5
FOOT_MAX_HEIGHT_RANGE_CM = 2.0
FOOT_MAX_SLIDE_CM = 2.0
FLOOR_PENETRATION_CM = 0.5          # below the owner's rest joint height / the floor (y = 0)
EXPECTED_FPS = 30.0
FPS_TOLERANCE = 0.5
MIN_DURATION_S, MAX_DURATION_S = 1.0, 60.0
STANDING_MAX_TILT_DEG = 30.0
STANDING_MIN_LEG_EXTENSION = 0.85
# The owner's plantar (sole) vertices: a FIXED rest-mesh selection, never a per-pose minimum.
SOLE_MATERIAL = 'feet'              # slides and socks share it; the rule below excludes the socks
SOLE_MAX_REST_Y_M = 0.004
SOLE_MAX_NORMAL_Y = -0.7
FEET = ('LeftFoot', 'LeftToeBase', 'RightFoot', 'RightToeBase')
SYMMETRY_PAIRS = ('Shoulder', 'Arm', 'Hand', 'UpLeg', 'Foot')


def canonical(name):
    return PREFIX.sub('', name or '')


def r6(v):
    return None if v is None else round(float(v), 6)


def decoded(path: Path, workdir: Path) -> Path:
    """The file itself, or a copy decoded by the vendored meshopt decoder (Node)."""
    if not G.is_compressed(path):
        return path
    out = workdir / (path.stem + '.decoded.glb')
    if not out.exists():
        subprocess.run(['node', str(ROOT / 'tools/uncompress_unreal_glb.mjs'), str(path), str(out)], check=True,
                       stdout=subprocess.DEVNULL)
    return out


# ------------------------------------------------------------------ owner
class Owner:
    def __init__(self, gltf: G.Gltf):
        self.gltf = gltf
        skin = gltf.doc['skins'][0]
        self.skin_nodes = skin['joints']
        self.names = [canonical(gltf.nodes[j]['name']) for j in self.skin_nodes]
        self.node = dict(zip(self.names, self.skin_nodes))
        self.parent = {}
        for n, i in self.node.items():
            p = gltf.parent.get(i)
            self.parent[n] = canonical(gltf.nodes[p]['name']) if p in self.skin_nodes else None
        rest = G.world_pose(gltf, G.RestPose, 0)
        self.rest_world = {n: rest[i] for n, i in self.node.items()}
        self.offset_cm = {n: offset_cm(gltf, rest, i) for n, i in self.node.items()}
        self.ibm = None

    def full_parents(self):
        return {OWNER_PREFIX + n: (OWNER_PREFIX + p if p else None) for n, p in self.parent.items()}


def offset_cm(gltf, world, i):
    """Rest offset of node i from its parent, in the parent's frame, world-scaled, in cm."""
    p = gltf.parent.get(i)
    t, _, _ = gltf.rest(i)
    s = world[p][2] if p is not None else 1.0
    return tuple(c * s * 100 for c in t)


# ------------------------------------------------------------------ candidate model
class Candidate:
    def __init__(self, gltf: G.Gltf, owner: Owner, mapping=None, animation=None):
        self.gltf, self.owner, self.mapping = gltf, owner, mapping
        self.clip = gltf.animation(animation) if gltf.doc.get('animations') else None
        if mapping is None:
            found = {}
            for i, n in enumerate(gltf.nodes):
                if PREFIX.match(n.get('name', '')) and canonical(n['name']) in owner.node and 'mesh' not in n:
                    found.setdefault(canonical(n['name']), i)
            self.node = found
        else:
            self.node = {o: gltf.by_name[c] for o, c in mapping.items() if c is not None and c in gltf.by_name}

    def times(self):
        if self.clip is None:
            return [0.0]
        return self.clip.key_times()

    def frames(self):
        sampler = self.clip if self.clip is not None else G.RestPose
        return [(t, G.world_pose(self.gltf, sampler, t)) for t in self.times()]


def hips_frame_positions(world, cand):
    """Every mapped joint relative to the hips, in the hips' own frame (cm)."""
    hp, hq, _ = world[cand.node['Hips']]
    inv = G.qinv(hq)
    return {n: G.qrot(inv, tuple((a - b) * 100 for a, b in zip(world[i][0], hp))) for n, i in cand.node.items()}


# ------------------------------------------------------------------ invariants
def check_skeleton(cand: Candidate, owner: Owner, duration):
    if cand.mapping is not None:
        missing_keys = sorted(set(owner.names) - set(cand.mapping))
        unknown = sorted(c for c in cand.mapping.values() if c is not None and c not in cand.gltf.by_name)
        explicit_none = sorted(o for o, c in cand.mapping.items() if c is None)
        ok = not missing_keys and not unknown and 'Hips' in cand.node
        return {'pass': ok, 'mode': 'mapping', 'mapped': len(cand.node), 'explicitly_unmapped': explicit_none,
                'owner_joints_missing_from_mapping': missing_keys, 'unknown_candidate_nodes': unknown}
    g = cand.gltf
    names, parents = [], {}
    for n, i in cand.node.items():
        full = OWNER_PREFIX + n
        names.append(full)
        p = g.parent.get(i)
        parents[full] = (OWNER_PREFIX + canonical(g.nodes[p]['name'])) if p is not None and p in cand.node.values() else None
    structural, samples = None, []
    hips = cand.node.get('Hips')
    if hips is not None and hips in g.parent:
        root = g.parent[hips]
        structural = g.nodes[root].get('name') or f'node{root}'
        names.insert(0, structural)
        parents[OWNER_PREFIX + 'Hips'] = structural
        parents[structural] = None
        sampler = cand.clip if cand.clip is not None else G.RestPose
        start = cand.clip.start if cand.clip is not None else 0.0
        # A file without animation is static by construction: its rest is sampled twice at t=0.
        times = parity.sample_times(duration) if cand.clip is not None else [0.0, 0.0]
        for t in times:
            w = G.world_pose(g, sampler, start + t, [root])[root]
            samples.append((t, tuple(c * 100 for c in w[0]), w[1], (w[2],) * 3))
    result = parity.structural_root_parity(names, parents, owner.full_parents(), samples)
    prefixes = sorted({PREFIX.match(g.nodes[i]['name']).group(0) for i in cand.node.values()})
    return {'pass': result['pass'] and len(cand.node) == len(owner.names), 'mode': 'bone_for_bone',
            'joint_count': len(cand.node), 'owner_joint_count': len(owner.names), 'prefixes': prefixes,
            'parity': result}


def check_rest(cand: Candidate, owner: Owner):
    g = cand.gltf
    rest = G.world_pose(g, G.RestPose, 0)
    per_bone, worst = {}, 0.0
    ratios = {}
    for n, i in cand.node.items():
        if cand.mapping is None:
            got = offset_cm(g, rest, i)
            ref = owner.offset_cm[n]
            dev = max(abs(a - b) for a, b in zip(got, ref))
            dlen = abs(G.vlen(got) - G.vlen(ref))
            rot = G.qangle_deg(g.rest(i)[1], owner.gltf.rest(owner.node[n])[1])
            per_bone[n] = {'offset_max_component_dev_cm': r6(dev), 'length_dev_cm': r6(dlen), 'rest_rotation_dev_deg': r6(rot)}
            worst = max(worst, dev, dlen)
        else:
            parent = nearest_mapped_parent(n, cand, owner)
            if parent is None:
                continue
            src = G.vlen(G.vsub(rest[i][0], rest[cand.node[parent]][0])) * 100
            own = G.vlen(G.vsub(owner.rest_world[n][0], owner.rest_world[parent][0])) * 100
            ratios[n] = {'parent': parent, 'candidate_cm': r6(src), 'owner_cm': r6(own),
                         'owner_over_candidate': r6(own / src) if src > 1e-9 else None}
    if cand.mapping is not None:
        return {'pass': None, 'applicable': False, 'reason': 'retarget source: lengths differ by design; ratios measured',
                'bone_length_ratios': ratios}
    return {'pass': worst <= REST_TOLERANCE_CM, 'max_deviation_cm': r6(worst), 'tolerance_cm': REST_TOLERANCE_CM,
            'per_bone': per_bone}


def nearest_mapped_parent(n, cand, owner):
    p = owner.parent.get(n)
    while p is not None and p not in cand.node:
        p = owner.parent.get(p)
    return p


def check_lengths(frames, cand: Candidate, owner: Owner):
    g = cand.gltf
    rest = G.world_pose(g, G.RestPose, 0)
    worst_self, worst_owner, per_bone = 0.0, 0.0, {}
    for n, i in cand.node.items():
        parent = nearest_mapped_parent(n, cand, owner) if cand.mapping is not None else owner.parent.get(n)
        if parent is None or parent not in cand.node:
            continue
        j = cand.node[parent]
        rest_len = G.vlen(G.vsub(rest[i][0], rest[j][0])) * 100
        own_len = G.vlen(G.vsub(owner.rest_world[n][0], owner.rest_world[parent][0])) * 100
        dev_self = dev_owner = 0.0
        for _, w in frames:
            L = G.vlen(G.vsub(w[i][0], w[j][0])) * 100
            dev_self = max(dev_self, abs(L - rest_len))
            dev_owner = max(dev_owner, abs(L - own_len))
        per_bone[n] = {'max_dev_from_own_rest_cm': r6(dev_self), 'max_dev_from_owner_cm': r6(dev_owner)}
        worst_self = max(worst_self, dev_self)
        worst_owner = max(worst_owner, dev_owner)
    ok = worst_self <= STRETCH_TOLERANCE_CM and (cand.mapping is not None or worst_owner <= STRETCH_TOLERANCE_CM)
    return {'pass': ok, 'max_stretch_cm': r6(worst_self), 'max_dev_from_owner_lengths_cm': r6(worst_owner),
            'owner_length_rule_applies': cand.mapping is None, 'tolerance_cm': STRETCH_TOLERANCE_CM, 'per_bone': per_bone}


def hips_travel(frames, cand):
    hips = cand.node['Hips']
    first = frames[0][1][hips][0]
    travel = max(math.hypot(w[hips][0][0] - first[0], w[hips][0][2] - first[2]) for _, w in frames) * 100
    last = frames[-1][1][hips][0]
    net = math.hypot(last[0] - first[0], last[2] - first[2]) * 100
    heights = [w[hips][0][1] * 100 for _, w in frames]
    return travel, net, max(heights) - min(heights)


def check_root(frames, cand, skeleton):
    travel, net, vertical = hips_travel(frames, cand)
    root_ok = True
    if cand.mapping is None:
        root_ok = not any('structural root' in f for f in skeleton.get('parity', {}).get('failures', []))
    ok = travel <= HIPS_MAX_TRAVEL_CM and net <= HIPS_MAX_NET_CM and root_ok
    return {'pass': ok, 'hips_max_horizontal_travel_cm': r6(travel), 'hips_net_horizontal_cm': r6(net),
            'hips_vertical_range_cm': r6(vertical), 'structural_root_constant': root_ok,
            'max_travel_cm': HIPS_MAX_TRAVEL_CM, 'max_net_cm': HIPS_MAX_NET_CM}


def loop_metrics(shapes, hips_world, i, j, fps):
    """Pose and velocity mismatch between frame i (start) and frame j (end) of a candidate loop."""
    pose = max(G.vlen(G.vsub(shapes[j][n], shapes[i][n])) for n in shapes[i])
    hips = G.vlen(G.vsub(hips_world[j], hips_world[i])) * 100
    vel = 0.0
    if j - i >= 2:
        for n in shapes[i]:
            v0 = G.vsub(shapes[i + 1][n], shapes[i][n])
            v1 = G.vsub(shapes[j][n], shapes[j - 1][n])
            vel = max(vel, G.vlen(G.vsub(v1, v0)) * fps)
    return pose, hips, vel


def check_loop(frames, cand, fps):
    shapes = [hips_frame_positions(w, cand) for _, w in frames]
    hips = [w[cand.node['Hips']][0] for _, w in frames]
    if len(frames) < 3:
        return {'pass': False, 'reason': 'fewer than 3 frames'}
    pose, hw, vel = loop_metrics(shapes, hips, 0, len(frames) - 1, fps)
    return {'pass': pose <= LOOP_MAX_POSE_CM and hw <= LOOP_MAX_POSE_CM and vel <= LOOP_MAX_VELOCITY_CM_S,
            'start_end_hips_relative_pose_cm': r6(pose), 'start_end_hips_world_cm': r6(hw),
            'start_end_velocity_delta_cm_s': r6(vel), 'max_pose_cm': LOOP_MAX_POSE_CM,
            'max_velocity_cm_s': LOOP_MAX_VELOCITY_CM_S}


def check_feet_joints(frames, cand, owner):
    out, ok = {}, True
    for n in FEET:
        if n not in cand.node:
            out[n] = None
            continue
        i = cand.node[n]
        ys = [w[i][0][1] * 100 for _, w in frames]
        first = frames[0][1][i][0]
        slide = max(math.hypot(w[i][0][0] - first[0], w[i][0][2] - first[2]) for _, w in frames) * 100
        mean = sum(ys) / len(ys)
        std = math.sqrt(sum((y - mean) ** 2 for y in ys) / len(ys))
        if cand.mapping is None:
            floor_ref = owner.rest_world[n][0][1] * 100
        else:
            floor_ref = G.world_pose(cand.gltf, G.RestPose, 0)[i][0][1] * 100
        sink = floor_ref - min(ys)
        good = std <= FOOT_MAX_HEIGHT_STD_CM and max(ys) - min(ys) <= FOOT_MAX_HEIGHT_RANGE_CM \
            and slide <= FOOT_MAX_SLIDE_CM and sink <= FLOOR_PENETRATION_CM
        ok &= good
        out[n] = {'pass': good, 'height_std_cm': r6(std), 'height_range_cm': r6(max(ys) - min(ys)),
                  'min_height_cm': r6(min(ys)), 'rest_height_cm': r6(floor_ref), 'sink_below_rest_cm': r6(sink),
                  'horizontal_slide_cm': r6(slide)}
    return {'pass': ok, 'basis': 'foot/toe JOINT positions (labelled: not the sole surface)', 'joints': out,
            'thresholds': {'height_std_cm': FOOT_MAX_HEIGHT_STD_CM, 'height_range_cm': FOOT_MAX_HEIGHT_RANGE_CM,
                           'slide_cm': FOOT_MAX_SLIDE_CM, 'sink_cm': FLOOR_PENETRATION_CM}}


# ------------------------------------------------------------------ soles (owner's fixed plantar vertices)
def sole_selection(owner_decoded: G.Gltf):
    import numpy as np
    doc = owner_decoded.doc
    mats = [m.get('name') for m in doc.get('materials', [])]
    skin = doc['skins'][0]
    ibm = np.array(owner_decoded.accessor(skin['inverseBindMatrices'])).reshape(-1, 4, 4).transpose(0, 2, 1)
    rows = []
    seen_meshes = set()
    for node in doc['nodes']:
        if 'mesh' not in node or node.get('skin') != 0 or node['mesh'] in seen_meshes:
            continue
        seen_meshes.add(node['mesh'])
        for prim in doc['meshes'][node['mesh']]['primitives']:
            if prim.get('material') is None or mats[prim['material']] != SOLE_MATERIAL:
                continue
            a = prim['attributes']
            pos = np.array(owner_decoded.accessor(a['POSITION']))
            nrm = np.array(owner_decoded.accessor(a['NORMAL']))
            jts = np.array(owner_decoded.accessor(a['JOINTS_0'])).astype(int)
            wts = np.array(owner_decoded.accessor(a['WEIGHTS_0']))
            keep = (pos[:, 1] <= SOLE_MAX_REST_Y_M) & (nrm[:, 1] < SOLE_MAX_NORMAL_Y)
            rows.append((pos[keep], jts[keep], wts[keep]))
    pos = np.concatenate([r[0] for r in rows])
    jts = np.concatenate([r[1] for r in rows])
    wts = np.concatenate([r[2] for r in rows])
    names = [canonical(doc['nodes'][j]['name']) for j in skin['joints']]
    dominant = [names[j[np.argmax(w)]] for j, w in zip(jts, wts)]
    side = np.array([d.startswith('Left') for d in dominant])
    return {'pos': pos, 'joints': jts, 'weights': wts, 'left': side, 'ibm': ibm, 'names': names,
            'count': int(len(pos)), 'rest_y_bounds_m': [float(pos[:, 1].min()), float(pos[:, 1].max())]}


def trs_matrix(t, q, s):
    import numpy as np
    x, y, z, w = q
    r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    m = np.eye(4)
    m[:3, :3] = r * s
    m[:3, 3] = t
    return m


def check_soles(frames, cand, sole):
    import numpy as np
    needed = sorted(set(sole['joints'].ravel().tolist()))
    missing = [sole['names'][j] for j in needed if sole['names'][j] not in cand.node]
    if missing:
        return {'pass': False, 'reason': f'candidate lacks skin joints {missing}'}
    homog = np.hstack([sole['pos'], np.ones((len(sole['pos']), 1))])
    per_frame_low = {'left': [], 'right': []}
    centroid = {'left': [], 'right': []}
    for _, w in frames:
        mats = np.zeros((len(sole['names']), 4, 4))
        for j in needed:
            wt = w[cand.node[sole['names'][j]]]
            mats[j] = trs_matrix(wt[0], wt[1], wt[2]) @ sole['ibm'][j]
        skinned = np.zeros((len(homog), 4))
        for k in range(4):
            m = mats[sole['joints'][:, k]]
            skinned += sole['weights'][:, k:k + 1] * np.einsum('nij,nj->ni', m, homog)
        for side, mask in (('left', sole['left']), ('right', ~sole['left'])):
            pts = skinned[mask, :3]
            per_frame_low[side].append(float(pts[:, 1].min()))
            centroid[side].append(pts.mean(axis=0))
    out, ok = {}, True
    for side in ('left', 'right'):
        low = np.array(per_frame_low[side]) * 100
        c = np.array(centroid[side])
        slide = float(np.max(np.hypot(c[:, 0] - c[0, 0], c[:, 2] - c[0, 2]))) * 100
        lift = float(low.max() - low.min())
        good = bool(-low.min() <= FLOOR_PENETRATION_CM and lift <= FOOT_MAX_HEIGHT_RANGE_CM and slide <= FOOT_MAX_SLIDE_CM)
        ok = ok and good
        out[side] = {'pass': good, 'vertices': int((sole['left'] if side == 'left' else ~sole['left']).sum()),
                     'lowest_vertex_min_cm': r6(low.min()), 'lowest_vertex_max_cm': r6(low.max()),
                     'penetration_below_floor_cm': r6(max(0.0, -low.min())), 'lift_range_cm': r6(lift),
                     'centroid_horizontal_slide_cm': r6(slide)}
    return {'pass': ok, 'basis': 'owner plantar vertices: material "feet", rest Y <= 0.004 m, bind normal Y < -0.7 '
                                  '(fixed rest-mesh selection, skinned every frame); floor y = 0',
            'selected_vertices': sole['count'], 'rest_y_bounds_m': [r6(v) for v in sole['rest_y_bounds_m']],
            'feet': out, 'thresholds': {'penetration_cm': FLOOR_PENETRATION_CM, 'lift_range_cm': FOOT_MAX_HEIGHT_RANGE_CM,
                                        'slide_cm': FOOT_MAX_SLIDE_CM}}


def check_standing(frames, cand, owner):
    need = ('Hips', 'Head', 'LeftFoot', 'RightFoot', 'LeftUpLeg', 'LeftLeg')
    if any(n not in cand.node for n in need):
        return {'pass': False, 'reason': 'missing hips/head/feet joints'}
    rest = G.world_pose(cand.gltf, G.RestPose, 0)
    leg = G.vlen(G.vsub(rest[cand.node['LeftUpLeg']][0], rest[cand.node['LeftLeg']][0])) \
        + G.vlen(G.vsub(rest[cand.node['LeftLeg']][0], rest[cand.node['LeftFoot']][0]))
    worst_tilt, worst_ext = 0.0, 9.0
    for _, w in frames:
        hips, head = w[cand.node['Hips']][0], w[cand.node['Head']][0]
        feet = min(w[cand.node[s]][0][1] for s in ('LeftFoot', 'RightFoot'))
        axis = G.vsub(head, hips)
        tilt = math.degrees(math.acos(max(-1.0, min(1.0, axis[1] / (G.vlen(axis) or 1)))))
        worst_tilt = max(worst_tilt, tilt)
        worst_ext = min(worst_ext, (hips[1] - feet) / leg)
    return {'pass': worst_tilt <= STANDING_MAX_TILT_DEG and worst_ext >= STANDING_MIN_LEG_EXTENSION,
            'max_torso_tilt_deg': r6(worst_tilt), 'min_leg_extension': r6(worst_ext),
            'thresholds': {'tilt_deg': STANDING_MAX_TILT_DEG, 'leg_extension': STANDING_MIN_LEG_EXTENSION}}


def timing(times):
    steps = sorted(b - a for a, b in zip(times, times[1:]))
    if not steps:
        return None, None, False
    median = steps[len(steps) // 2]
    fps = 1 / median if median else None
    uniform = steps[-1] - steps[0] < 1e-3
    return fps, times[-1] - times[0], uniform


def check_timing(times):
    fps, duration, uniform = timing(times)
    ok = fps is not None and abs(fps - EXPECTED_FPS) <= FPS_TOLERANCE and uniform \
        and MIN_DURATION_S <= duration <= MAX_DURATION_S
    return {'pass': ok, 'fps': r6(fps), 'duration_s': r6(duration), 'frames': len(times), 'uniform_keys': uniform,
            'expected_fps': EXPECTED_FPS, 'duration_bounds_s': [MIN_DURATION_S, MAX_DURATION_S]}


def check_symmetry(frames, cand, owner):
    """Owner's left is +x in the hips frame at rest; every Left joint must stay left of its Right twin."""
    sign = 1.0 if owner.rest_world['LeftUpLeg'][0][0] > owner.rest_world['RightUpLeg'][0][0] else -1.0
    out, ok = {}, True
    shapes = [hips_frame_positions(w, cand) for _, w in frames]
    for part in SYMMETRY_PAIRS:
        left, right = 'Left' + part, 'Right' + part
        if left not in cand.node or right not in cand.node:
            continue
        margin = min(sign * (s[left][0] - s[right][0]) for s in shapes)
        out[part] = {'min_left_minus_right_cm': r6(margin), 'pass': margin > 0}
        ok &= margin > 0
    return {'pass': ok, 'pairs': out, 'rule': 'hips-frame lateral coordinate of each Left joint > its Right twin, every frame'}


def verify(candidate: Path, owner_path: Path = OWNER, animation=None, mapping=None, soles=True, workdir=None):
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(workdir) if workdir else Path(tmp)
        cand_g = G.Gltf(decoded(candidate, work))
        owner_g = G.Gltf(owner_path)
        owner = Owner(owner_g)
        cand = Candidate(cand_g, owner, mapping, animation)
        if 'Hips' not in cand.node:
            return {'schema': SCHEMA, 'candidate': str(candidate), 'pass': False, 'accepted_for_binding': False,
                    'refusal': 'no Hips joint found (prefix or mapping)', 'invariants': {}}
        times = cand.times()
        frames = cand.frames()
        fps, duration, _ = timing(times)
        inv = {'skeleton': check_skeleton(cand, owner, duration or 0.0),
               'rest_offsets': check_rest(cand, owner),
               'timing': check_timing(times)}
        if cand.clip is None:
            inv['animation'] = {'pass': False, 'reason': 'no animation in the file (rest pose only)'}
        else:
            inv['bone_length_constancy'] = check_lengths(frames, cand, owner)
            inv['root_in_place'] = check_root(frames, cand, inv['skeleton'])
            inv['loop'] = check_loop(frames, cand, fps or EXPECTED_FPS)
            inv['feet_joints'] = check_feet_joints(frames, cand, owner)
            inv['standing'] = check_standing(frames, cand, owner)
            inv['symmetry'] = check_symmetry(frames, cand, owner)
            if soles and mapping is None:
                inv['soles'] = check_soles(frames, cand, sole_selection(G.Gltf(decoded(owner_path, work))))
        failed = sorted(k for k, v in inv.items() if v.get('pass') is False)
        ok = not failed
        return {'schema': SCHEMA, 'candidate': str(candidate), 'candidate_sha256': G.Gltf(candidate).sha256, 'owner': str(owner_path), 'owner_sha256': owner_g.sha256,
                'animation': cand.clip.name if cand.clip else None, 'mode': 'mapping' if mapping else 'bone_for_bone',
                'pass': ok, 'failed': failed, 'accepted_for_binding': ok and mapping is None,
                'note': 'Measured only. A failing clip is refused; it is never posed, trimmed or edited here. '
                        'Renderer validation (native capture) is still required before binding.',
                'invariants': inv}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('candidate', type=Path)
    ap.add_argument('--owner', type=Path, default=OWNER)
    ap.add_argument('--animation')
    ap.add_argument('--mapping', type=Path)
    ap.add_argument('--out', type=Path)
    ap.add_argument('--no-soles', action='store_true')
    args = ap.parse_args(argv)
    mapping = json.loads(args.mapping.read_text()) if args.mapping else None
    report = verify(args.candidate, args.owner, args.animation, mapping, soles=not args.no_soles)
    text = json.dumps(report, indent=1, sort_keys=True) + '\n'
    if args.out:
        args.out.write_text(text)
    print(json.dumps({'pass': report['pass'], 'failed': report['failed'],
                      'accepted_for_binding': report['accepted_for_binding']}))
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
