"""PROPOSAL: seated PC typing on the ACTUAL chair at the REAL LINEA140 desk, with whole-arm IK (source only).

Labelled `proposal`, `verified: false`, `requires_server_reaudit: true`, `requires_native_collision_audit: true`.
Nothing here sets a seat, contact or collision receipt.

Inputs (all committed or reproducible):
* REAL DESK: root's LINEA140 source GLB (sha256 99bdf3fd...; on origin/main as
  web/house/assets/real-linea140/originalsource.glb), placed exactly as root's tools/prepare_real_linea140_placement.py
  place_bytes() does (node translation [2.1, .025, -3.02] m, uniform scale (.845 - .025) / .755) and mapped to UE cm as
  root's tools/real_linea_edge_clamp.py does: UE = 100 * (2.1 + S x, -3.02 + S z, .025 + S y). Every source node's UE
  AABB is extracted once (`desk_geometry`) and committed as docs/proposed/seated-typing-ik/real-linea140-geometry.json.
  Node AABBs are conservative for clearance (the worktop's eased edges and rounded corners lie inside its box).
* CHAIR: root's measured native chair (docs/proposed/native-chair-measured/20261014-actual-native-chair-surface.json):
  transform [200.020, -186.690, 60.688] is the INITIAL state and is never changed. Pulling the chair in is an explicit,
  reversible ACTIVITY transform (`ChairRoll`): a declared runtime offset with start/end transforms, a quintic
  smootherstep path, clearance against the real desk at every frame, and a push-back that is the exact time reverse.
* KEYBOARD: the repo home.js placement (furnished("keyboard", 2, .846, -2.94, .371)), the same keycap triangles the
  seat fit uses (fit_seat_pose_trial.keycaps_from_glb). Root's LINEA placement record lists the home's keyboard source
  nodes 184-187 at X 181.45..218.55, Y -302.05..-285.95 (UE cm): the same footprint, so the keyboard did not move with
  the desk; its 0.1 cm float above the 84.5 cm top is root's pending device-foot check.
* BODY: the seated fits in docs/proposed/seat-pose-fit/ (pelvis pitch, lowering, leg IK; tools/fit_seat_pelvis_pitch.py),
  re-measured here with the existing gates. Their solver frame IS the rolled world: the chair rolled by
  ROLL_OFFSET_CM = the fit's chair offset (+3.875, -32.5) and the body at the audited transform.

Arms (`ArmIK`, only the six arm bones change; fingers keep their captured locals):
  shoulder -> elbow -> wrist non-stretch two-bone IK (fit_seat_pose_trial.two_bone, the UE SolveTwoBoneIK form) with the
  elbow pole from the capture; the hand rides on the forearm through a wrist local rotation that is the captured one with
  its flexion/extension and radial/ulnar deviation softly limited to the neutral zone (WRIST_SOFT_*, soft targets, never
  gates); the wrist target is the captured wrist moved vertically so the over-key distal skin minimum lands on
  KeyTop + 0.08 cm (the existing keyboard contact rule); if any arm skin is closer than FOREARM_TARGET_CLEARANCE_CM to the
  real desk, the elbow swivels about the shoulder-wrist axis (smallest swivel that clears, then a smooth envelope over
  time), and, only when no swivel clears, the whole hand lifts.

    python tools/solve_seated_typing_arm_ik.py --source private-audit/seat-fit-source.npz \
        [--desk-source <LINEA140 source.glb>] --out-dir docs/proposed/seated-typing-ik
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

SCHEMA = 'sub01.seated-typing-arm-ik.v1'

# ---------------------------------------------------------------- the REAL desk (root's LINEA140 placement)
LINEA_SHA256 = '99bdf3fd42eea5fc4cb2fadd52c8cae18c4459a94000b85f7df4c515234ba43d'
LINEA_SCALE = (.845 - .025) / .755          # root prepare_real_linea140_placement.SCALE
LINEA_TRANSLATION_M = (2.1, .025, -3.02)     # root place_bytes(): node translation (x, y up, z) metres
LINEA_ROOT_PROVENANCE = {
    'placement': 'origin/main tools/prepare_real_linea140_placement.py (place_bytes, SCALE, DESK_Y) @ b17952c',
    'ue_mapping': 'origin/main tools/real_linea_edge_clamp.py contact_coverage: (2.1 + x S, DESK_Y + z S, .025 + y S) * 100',
    'record': 'origin/main docs/proposed/real-linea140-guarded-placement-20261014.json @ bb24ae5',
    'source': 'origin/main web/house/assets/real-linea140/originalsource.glb'}
GEOMETRY_JSON = ROOT / 'docs/proposed/seated-typing-ik/real-linea140-geometry.json'
WORKTOP_NODE = 44


def linea_nodes_ue(glb_path):
    """{node: (name, materials, (N, 3) UE cm points)} for every mesh node of the verified LINEA source."""
    from home_asset_audit import read_gltf
    from structural_rail_source_patch import accessor, transformed, world_matrices
    path = Path(glb_path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != LINEA_SHA256:
        raise ValueError('LINEA140 source bytes differ from root\'s reviewed source')
    doc, binary = read_gltf(path)
    M = world_matrices(doc)
    out = {}
    for ni, node in enumerate(doc['nodes']):
        if 'mesh' not in node:
            continue
        pts, mats = [], set()
        for prim in doc['meshes'][node['mesh']]['primitives']:
            pts += [transformed(M[ni], x) for x in accessor(doc, binary, prim['attributes']['POSITION'])]
            mats.add(doc['materials'][prim['material']]['name'])
        P = np.asarray(pts, float)
        tx, ty, tz = LINEA_TRANSLATION_M
        ue = np.stack([tx + P[:, 0] * LINEA_SCALE, tz + P[:, 2] * LINEA_SCALE, ty + P[:, 1] * LINEA_SCALE], -1) * 100.
        out[ni] = (node.get('name', ''), sorted(mats), ue)
    return out


def part_kind(name):
    n = name.lower()
    for key, kind in (('worktop', 'worktop'), ('leg shoe', 'leg_shoe'), ('square leg', 'leg'), ('elastomer foot', 'foot'),
                      ('apron', 'apron'), ('drawer', 'drawer'), ('grommet', 'grommet'), ('trough', 'cable_trough'),
                      ('fixing', 'fixing'), ('slide', 'drawer'), ('plate', 'fixing')):
        if key in n:
            return kind
    return 'other'


def desk_geometry(glb_path):
    """Per-node UE AABBs of the real desk plus the derived tabletop slab, knee bay and front edge (UE cm)."""
    nodes = linea_nodes_ue(glb_path)
    parts = []
    for ni, (name, mats, ue) in sorted(nodes.items()):
        parts.append({'node': ni, 'name': name, 'kind': part_kind(name), 'materials': mats, 'vertices': int(len(ue)),
                      'min_cm': [round(float(v), 4) for v in ue.min(0)], 'max_cm': [round(float(v), 4) for v in ue.max(0)]})
    allp = np.concatenate([u for _, _, u in nodes.values()])
    top = next(p for p in parts if p['node'] == WORKTOP_NODE)
    legs = [p for p in parts if p['kind'] == 'leg']
    drawer = [p for p in parts if p['kind'] == 'drawer']
    aprons = [p for p in parts if p['kind'] == 'apron']
    front_apron = max((p for p in aprons if 'long' in p['name'].lower()), key=lambda p: p['max_cm'][1])
    left_legs_inner = max(p['max_cm'][0] for p in legs if p['max_cm'][0] < top['min_cm'][0] + 20)
    drawer_left = min(p['min_cm'][0] for p in drawer)
    return {
        'schema': 'sub01.real-linea140-ue-geometry.v1', 'source_sha256': LINEA_SHA256, 'scale': LINEA_SCALE,
        'translation_m': list(LINEA_TRANSLATION_M), 'provenance': LINEA_ROOT_PROVENANCE,
        'mapping': 'UE cm = 100 * (2.1 + S x, -3.02 + S z, .025 + S y), glTF source node world points',
        'overall_min_cm': [round(float(v), 4) for v in allp.min(0)], 'overall_max_cm': [round(float(v), 4) for v in allp.max(0)],
        'overall_dims_cm': [round(float(v), 4) for v in allp.max(0) - allp.min(0)],
        'floor_cm': round(float(allp[:, 2].min()), 4),
        'tabletop_slab': {'node': WORKTOP_NODE, 'name': top['name'], 'min_cm': top['min_cm'], 'max_cm': top['max_cm'],
                          'top_cm': top['max_cm'][2], 'bottom_cm': top['min_cm'][2],
                          'thickness_cm': round(top['max_cm'][2] - top['min_cm'][2], 4),
                          'front_edge_y_cm': top['max_cm'][1], 'rear_edge_y_cm': top['min_cm'][1],
                          'centre_xy_cm': [round((top['min_cm'][a] + top['max_cm'][a]) / 2, 4) for a in range(2)],
                          'front_is_positive_ue_y': True,
                          'note': 'AABB of the worktop node: the eased top/bottom edges (84.283 / 81.785 cm) and rounded '
                                  'plan corners lie inside it, so box clearance is conservative'},
        'front_apron': {'node': front_apron['node'], 'min_cm': front_apron['min_cm'], 'max_cm': front_apron['max_cm'],
                        'bottom_cm': front_apron['min_cm'][2]},
        'knee_bay_cm': {'x': [round(left_legs_inner, 4), round(drawer_left, 4)], 'below_z': front_apron['min_cm'][2],
                        'left_leg_inner_x': round(left_legs_inner, 4), 'drawer_carcass_left_x': round(drawer_left, 4)},
        'grommet_rim_top_cm': max(p['max_cm'][2] for p in parts if p['kind'] == 'grommet'),
        'parts': parts}


def load_geometry(path=GEOMETRY_JSON):
    return json.loads(Path(path).read_text())


def desk_boxes(geometry, kinds=None):
    """(B, 2, 3) part AABBs (UE cm) and their node ids."""
    rows = [p for p in geometry['parts'] if kinds is None or p['kind'] in kinds]
    return np.array([[p['min_cm'], p['max_cm']] for p in rows], float), [p['node'] for p in rows]


# ---------------------------------------------------------------- box clearance
def box_signed_distance(points, lo, hi):
    """Signed Euclidean distance (cm) from points (..., 3) to an axis-aligned box: > 0 outside, < 0 inside (depth)."""
    p = np.asarray(points, float)
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    d = np.maximum(lo - p, p - hi)                          # per-axis outside distance (negative inside)
    outside = np.linalg.norm(np.maximum(d, 0.), axis=-1)
    inside = np.minimum(d.max(axis=-1), 0.)
    return outside + inside


def boxes_min_distance(points, boxes, reach_cm=None):
    """Per point: the smallest signed distance to any box, and that box's index. reach_cm: only boxes within reach of
    the points' overall AABB are evaluated (a point farther than reach_cm from every box reports min(true, reach) >=
    reach_cm, never a false small value)."""
    p = np.asarray(points, float)
    flat = p.reshape(-1, 3)
    best = np.full(len(flat), np.inf)
    which = np.full(len(flat), -1)
    cand = range(len(boxes))
    if reach_cm is not None and len(flat):
        plo, phi = flat.min(0) - reach_cm, flat.max(0) + reach_cm
        cand = [b for b, (lo, hi) in enumerate(boxes) if np.all(np.asarray(hi) >= plo) and np.all(np.asarray(lo) <= phi)]
        best[:] = reach_cm
    for b in cand:
        lo, hi = boxes[b]
        near = np.all((flat >= np.asarray(lo) - best[:, None]) & (flat <= np.asarray(hi) + best[:, None]), axis=1)
        if not near.any():
            continue
        d = box_signed_distance(flat[near], lo, hi)
        idx = np.nonzero(near)[0]
        better = d < best[idx]
        best[idx[better]], which[idx[better]] = d[better], b
    return best.reshape(p.shape[:-1]), which.reshape(p.shape[:-1])


def slab_clearance(points, slab):
    """Vertical clearance (cm) of points over the tabletop footprint to the slab (above: z - top; below: bottom - z;
    inside: negative depth to the nearer face); points outside the footprint return +inf. Also the signed 3D distance."""
    p = np.asarray(points, float)
    lo, hi = np.asarray(slab['min_cm'], float), np.asarray(slab['max_cm'], float)
    over = (p[..., 0] >= lo[0]) & (p[..., 0] <= hi[0]) & (p[..., 1] >= lo[1]) & (p[..., 1] <= hi[1])
    above, below = p[..., 2] - hi[2], lo[2] - p[..., 2]
    vert = np.where(above >= 0, above, np.where(below >= 0, below, -np.minimum(-above, -below)))
    return np.where(over, vert, np.inf), box_signed_distance(p, lo, hi)


# ---------------------------------------------------------------- rig helpers (glTF world metres, the owner skeleton)
import export_seat_fit_source as E  # noqa: E402
import fit_seat_pelvis_pitch as P  # noqa: E402
import fit_seat_pose_trial as T  # noqa: E402
import life_gltf as G  # noqa: E402
import validate_unreal_contact_profile as contact_profile  # noqa: E402
import validate_unreal_seat_contact as seat_contact  # noqa: E402

SIDES = {'left': 'Left', 'right': 'Right'}
ARM_BONES = {s: (f'{p}Arm', f'{p}ForeArm', f'{p}Hand') for s, p in SIDES.items()}
FINGERS = ('Thumb', 'Index', 'Middle', 'Ring', 'Pinky')
UP = T.UP


def arm_joint_sets(names):
    """Per side: skeleton indices of {upper arm, forearm, hand, fingers} (skin vertices whose dominant joint is one)."""
    out = {}
    for s, p in SIDES.items():
        out[s] = {'upper_arm': [names.index(f'{p}Arm')], 'forearm': [names.index(f'{p}ForeArm')],
                  'hand': [names.index(f'{p}Hand')],
                  'fingers': [k for k, n in enumerate(names) if n.startswith(f'{p}Hand') and any(f in n for f in FINGERS)]}
    return out


def arm_skin(names, stride=1, cache=None):
    """Owner skin vertices (web/room/char_mixamo.glb, LBS data) whose dominant joint is an arm joint, per side, with the
    part label of that joint (upper_arm / forearm / hand / fingers)."""
    pos, jts, wts = P.owner_skin(stride=stride, cache=cache)
    dom = jts[np.arange(len(jts)), wts.argmax(1)]
    sets = arm_joint_sets(names)
    out = {}
    for s, parts in sets.items():
        label = np.full(len(pos), '', dtype=object)
        for part, ids in parts.items():
            label[np.isin(dom, ids)] = part
        keep = label != ''
        out[s] = {'skin': (pos[keep], jts[keep], wts[keep]), 'part': label[keep].astype(str)}
    return out


def bind_worlds(ibm):
    return np.linalg.inv(ibm)


def wrist_frame_bind(names, ibm, side):
    """Anatomical wrist frame at bind (glTF metres): b = forearm axis (elbow -> wrist), r = radial (pinky MCP -> index MCP,
    orthogonal to b), n = palmar normal (the side the captured finger curl bends toward). The owner bind is a relaxed
    A-pose with straight wrists; the wrist angle is the hand's rotation relative to the forearm away from bind."""
    B = bind_worlds(ibm)
    p = SIDES[side]
    j = lambda n: names.index(n)
    fore, hand = B[j(f'{p}ForeArm')][:3, 3], B[j(f'{p}Hand')][:3, 3]
    b = hand - fore
    b /= np.linalg.norm(b)
    r = B[j(f'{p}HandIndex1')][:3, 3] - B[j(f'{p}HandPinky1')][:3, 3]
    r -= r.dot(b) * b
    r /= np.linalg.norm(r)
    n = np.cross(b, r)
    # palmar side: the distal finger joints sit on the palmar side of the MCP line in the relaxed bind curl
    m1, m3 = B[j(f'{p}HandMiddle1')][:3, 3], B[j(f'{p}HandMiddle4')][:3, 3]
    if (m3 - m1).dot(n) < 0:
        n = -n
    return b, r, n


def unit_rot(M):
    return M / np.linalg.norm(M[..., :, 0], axis=-1)[..., None, None]


def wrist_angles(W, names, ibm, side):
    """(flexion, deviation, twist) degrees per frame: the hand's rotation relative to the forearm, away from bind,
    expressed in the forearm's anatomical frame. flexion > 0 palmar flexion, < 0 extension; deviation > 0 radial,
    < 0 ulnar; twist = residual rotation about the forearm axis (pro/supination carried at the wrist)."""
    B = bind_worlds(ibm)
    a, h = names.index(ARM_BONES[side][1]), names.index(ARM_BONES[side][2])
    b, r, n = wrist_frame_bind(names, ibm, side)
    Rf0, Rh0 = unit_rot(B[a][:3, :3]), unit_rot(B[h][:3, :3])
    Rf, Rh = unit_rot(W[:, a, :3, :3]), unit_rot(W[:, h, :3, :3])
    # hand relative to forearm, mapped into the forearm's bind (anatomical) frame
    D = Rf0 @ np.swapaxes(Rf, -1, -2) @ Rh @ Rh0.T
    hb, rh, nh = D @ b, D @ r, D @ n
    # Twist (pro/supination) belongs to the forearm, so flexion/deviation are read in the HAND's own frame: the forearm
    # axis seen from the hand. A palmar flexion by t gives D b = cos t b + sin t n, so b.(D n) = -sin t.
    c = hb @ b
    flex = np.degrees(np.arctan2(-(nh @ b), c))
    dev = np.degrees(np.arctan2(-(rh @ b), c))
    swing = T.find_between(np.broadcast_to(b, hb.shape), hb)
    rs = swing @ r
    tw = np.degrees(np.arctan2(np.sum(np.cross(rs, rh) * hb, -1), np.sum(rs * rh, -1)))
    return flex, dev, tw


# ---------------------------------------------------------------- wrist: soft neutral zone (SOFT TARGETS, never gates)
# Standard ergonomics for keyboard work, stated as soft targets only (no repo constant exists):
#   flexion/extension within +-15 deg: RULA (McAtamney & Corlett 1993) scores 0..15 deg as its lowest non-neutral band;
#   ulnar deviation within 20 deg and radial deviation within 10 deg: the usual keyboard comfort zone
#   (e.g. ANSI/HFES 100-2007 keyboard guidance; ulnar deviation is the natural typing direction).
WRIST_SOFT_FLEX_DEG = (-15., 15.)        # (extension, flexion)
WRIST_SOFT_DEV_DEG = (-20., 10.)         # (ulnar, radial)
WRIST_SOFT_KNEE_DEG = 3.                 # softplus knee width of the soft limit


def softplus(x, w):
    return w * np.logaddexp(0., np.asarray(x, float) / w)


def soft_limit(a, lo, hi, knee=WRIST_SOFT_KNEE_DEG):
    """Smooth saturation of angle(s) a into (lo, hi): lo + softplus(a - lo) - softplus(a - hi). Monotone, ~identity
    well inside, asymptotic to lo / hi outside, never beyond them."""
    a = np.asarray(a, float)
    return lo + softplus(a - lo, knee) - softplus(a - hi, knee)


def wrist_relative(W, names, ibm, side):
    """D (F, 3, 3): the hand's rotation relative to the forearm, mapped into the forearm's bind (anatomical) frame;
    D = I at bind. Rh = Rf Rf0^T D Rh0 rebuilds the hand world rotation on any forearm."""
    B = bind_worlds(ibm)
    a, h = names.index(ARM_BONES[side][1]), names.index(ARM_BONES[side][2])
    Rf0, Rh0 = unit_rot(B[a][:3, :3]), unit_rot(B[h][:3, :3])
    Rf, Rh = unit_rot(W[:, a, :3, :3]), unit_rot(W[:, h, :3, :3])
    return Rf0 @ np.swapaxes(Rf, -1, -2) @ Rh @ Rh0.T


def limit_wrist(D, names, ibm, side, flex_lim=WRIST_SOFT_FLEX_DEG, dev_lim=WRIST_SOFT_DEV_DEG):
    """D with its flexion and deviation soft-limited to the neutral zone; the twist about the hand axis is kept. The
    correction is the minimal rotation, in the hand's frame, that takes the forearm axis seen from the hand to the
    limited direction (so only flexion/deviation change)."""
    b, r, n = wrist_frame_bind(names, ibm, side)
    u = np.swapaxes(D, -1, -2) @ b                       # forearm axis in hand coordinates (bind frame basis)
    ub, ur, un = u @ b, u @ r, u @ n
    flex = np.degrees(np.arctan2(-un, ub))
    dev = np.degrees(np.arctan2(-ur, ub))
    fl, dv = soft_limit(flex, *flex_lim), soft_limit(dev, *dev_lim)
    want = b[None] - np.tan(np.radians(fl))[:, None] * n[None] - np.tan(np.radians(dv))[:, None] * r[None]
    want /= np.linalg.norm(want, axis=-1, keepdims=True)
    C = np.swapaxes(T.find_between(u, want), -1, -2)    # C^T u = want  ->  (D C)^T b = want
    return D @ C, {'flex_in': flex, 'dev_in': dev, 'flex_out': fl, 'dev_out': dv}


def hand_world_rotation(W, names, ibm, side, D):
    """Unit hand world rotation from the CURRENT forearm and a wrist-relative D."""
    B = bind_worlds(ibm)
    a, h = names.index(ARM_BONES[side][1]), names.index(ARM_BONES[side][2])
    Rf0, Rh0 = unit_rot(B[a][:3, :3]), unit_rot(B[h][:3, :3])
    return unit_rot(W[:, a, :3, :3]) @ Rf0.T @ D @ Rh0


# ---------------------------------------------------------------- whole-arm IK
def rotate_about(v, axis, ang):
    """Rodrigues rotation of vectors v (F, 3) about unit axes (F, 3) by angles (F,) radians."""
    axis = axis / np.linalg.norm(axis, axis=-1, keepdims=True)
    c, s = np.cos(ang)[:, None], np.sin(ang)[:, None]
    return v * c + np.cross(axis, v) * s + axis * np.sum(axis * v, -1, keepdims=True) * (1 - c)


def swivel_pole(shoulder, target, pole, phi):
    """Pole rotated by phi (radians) about the shoulder->target axis (the elbow swivel / arm plane angle)."""
    return shoulder + rotate_about(pole - shoulder, target - shoulder, phi)


# Shoulder girdle (sternoclavicular) ranges used as HARD limits of the ergonomic search: depression 0..10 deg,
# protraction/retraction +-15 deg (Kapandji, The Physiology of the Joints vol. 1: SC depression ~10 deg, pro/retraction
# ~15 deg each way; AAOS joint motion). The girdle is a rotation of the Shoulder (clavicle) joint carrying the arm.
GIRDLE_DEPRESSION_DEG = (0., 10.)
GIRDLE_PROTRACTION_DEG = (-15., 15.)
# Clearance only (a HARD gate outranks the soft ergonomic targets): where the arm is fully extended to the keys (the
# non-stretch two-bone chain saturated, so no elbow swivel changes it) and the sleeve still meets the desk, the shoulder
# girdle may ELEVATE up to 10 deg (clavicular elevation reaches ~30-40 deg: Kapandji, The Physiology of the Joints,
# vol. 1; Neumann, Kinesiology of the Musculoskeletal System, ch. 5), with retraction inside the cited +-15 deg.
# Candidates in order (depression < 0 is elevation; protraction < 0 is retraction):
# Clearance first by the WRIST (a six-arm-bone change): added palmar flexion toward neutral, where the captured hand
# attitude holds the wrist at the soft extension limit (-15 deg) and the sleeve under the forearm meets the desk; the
# result is still soft-limited to the +-15 deg RULA zone. The girdle (below) is only the fallback.
PITCH_CLEAR_CANDIDATES = (5., 10., 15., 20., 25., 30., 35., 40., 45.)
PITCH_CLEAR_ROUNDS = 3
GIRDLE_CLEAR_CANDIDATES = ((-2.5, 0.), (-5., 0.), (-7.5, 0.), (-10., 0.), (-10., -7.5), (-10., -15.))


def shoulder_girdle(sk, W, side, g):
    """Rotate the Shoulder (clavicle) joint about its own position by depression g[:,0] (lateral end down, about the
    body's forward axis, glTF +z) and protraction g[:,1] (lateral end forward, about the vertical, glTF +y); the
    whole arm is carried (locals below unchanged). Mirrored per side."""
    g = np.asarray(g, float)
    sgn = -1. if side == 'left' else 1.              # left clavicle points +x, right -x
    dep = np.radians(g[:, 0]) * sgn
    pro = np.radians(g[:, 1]) * sgn
    def rot(axis, a):
        c, s_ = np.cos(a), np.sin(a)
        R = np.tile(np.eye(3), (len(a), 1, 1))
        i, j = [(1, 2), (2, 0), (0, 1)][axis]
        R[:, i, i], R[:, i, j], R[:, j, i], R[:, j, j] = c, -s_, s_, c
        return R
    R = rot(1, pro) @ rot(2, dep)
    k = sk.j(f'{SIDES[side]}Shoulder')
    piv = W[:, k, :3, 3].copy()
    M = np.tile(np.eye(4), (len(g), 1, 1))
    M[:, :3, :3] = R
    M[:, :3, 3] = piv - np.einsum('fij,fj->fi', R, piv)
    for j in sk.subtree(k):
        W[:, j] = M @ W[:, j]
    return W


def axis_rotation(axis, ang):
    """(F, 3, 3) rotations by ang (F,) radians about one fixed unit axis (Rodrigues)."""
    k = np.asarray(axis, float) / np.linalg.norm(axis)
    K_ = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    a = np.asarray(ang, float)[:, None, None]
    return np.eye(3)[None] + np.sin(a) * K_[None] + (1 - np.cos(a)) * (K_ @ K_)[None]


def solve_arm(sk, W, side, target, pole, ibm, hand_world=None, D=None, limit=True, flex_add_deg=None):
    """Non-stretch two-bone IK of shoulder -> elbow -> wrist (UE SolveTwoBoneIK, fit_seat_pose_trial.two_bone) with the
    given elbow pole. The hand then rides on the NEW forearm: its wrist-relative rotation is D, or the one implied by the
    captured hand WORLD rotation `hand_world` (the genuine hand-to-keyboard attitude), with flexion/deviation softly
    limited to the neutral zone when `limit`. Fingers are carried rigidly (locals unchanged). Only Arm, ForeArm and Hand
    change (plus the carried finger subtree). Returns (W, reached, length, distance, wrist-limit info)."""
    chain = ARM_BONES[side]
    W, reach, length, dist = sk.two_bone_pose(W, chain, target, pole)
    names = sk.names
    if D is None:
        B = bind_worlds(ibm)
        a, h = names.index(chain[1]), names.index(chain[2])
        D = unit_rot(B[a][:3, :3]) @ np.swapaxes(unit_rot(W[:, a, :3, :3]), -1, -2) @ unit_rot(hand_world) @ unit_rot(B[h][:3, :3]).T
    if flex_add_deg is not None and np.any(flex_add_deg):
        # extra palmar flexion (deg) of the wrist about its radial axis (wrist_frame_bind), before the soft limit
        b_, r_, n_ = wrist_frame_bind(names, ibm, side)
        D = axis_rotation(r_, np.radians(flex_add_deg)) @ D
    info = None
    if limit:
        D, info = limit_wrist(D, names, ibm, side)
    h = sk.j(chain[2])
    scale = np.linalg.norm(W[:, h, :3, 0], axis=-1)[:, None, None]
    new = W[:, h].copy()
    new[:, :3, :3] = hand_world_rotation(W, names, ibm, side, D) * scale
    carry = new @ np.linalg.inv(W[:, h])
    for k in sk.subtree(h):
        if k != h:
            W[:, k] = carry @ W[:, k]
    W[:, h] = new
    return W, reach, length, dist, info


# ---------------------------------------------------------------- the per-clip solve
KEY_TOP_TARGET_CM = T.KEY_CONTACT_TARGET_CM          # over-key distal minimum -> KeyTop + 0.08 cm (native rule)
KEY_MIN_OVER_VERTICES = T.KEY_MIN_OVER_VERTICES      # >= 4 over-key distal vertices: the hand is on the keys
CONTACT_PASSES, CONTACT_TOL_CM = 12, 1e-4
CONTACT_BRACKET_CM, CONTACT_BISECTIONS = 2., 14
CONTACT_ACCEPT_CM = .02          # well inside the 0..0.2 cm key gate around the 0.08 cm target
FOREARM_TARGET_CLEARANCE_CM = .5     # design target for arm skin to the real desk (the gate is > 0, every frame)
SWIVEL_GRID_DEG = tuple(float(v) for v in np.arange(0., 120.01, 2.5))
# Ergonomic SOFT targets (never gates): elbow at or just above the desk / keyboard home-row height (ANSI/HFES 100-2007:
# keyboard at or slightly below elbow height, forearms about horizontal) -> elbow 0..10 cm above the 84.5 cm top;
# relaxed upper arm close to vertical (RULA upper-arm score 1: within 20 deg of the trunk line).
ERGO_ELBOW_ABOVE_DESK_CM = (0., 10.)
ERGO_UPPER_ARM_MAX_DEG = 20.
ERGO_ELBOW_SCALE_CM, ERGO_UPPER_ARM_SCALE_DEG = 1., 5.
ERGO_SWIVEL_DEG = tuple(float(v) for v in np.arange(-30., 120.01, 15.))
ERGO_GIRDLE = ((0., 0.), (10., 0.), (10., 15.))      # (depression, protraction) candidates, deg
SWIVEL_COARSE_STEP_DEG = 10.
SWIVEL_COARSE_DEG = tuple(float(v) for v in np.arange(0., SWIVEL_GRID_DEG[-1] + .01, SWIVEL_COARSE_STEP_DEG))
SEARCH_CONTACT_PASSES = 4
SWIVEL_ENVELOPE_S, SWIVEL_SMOOTH_S = .15, .1       # the seat fit's own envelope/smoothing rule (max filter, Gaussian)
LIFT_STEP_CM, LIFT_MAX_CM = .25, 15.
POLISH_GRID_CM = np.round(np.arange(-3., 3.0001, .05), 4)   # contact polish: vertical wrist corrections around the current
POLISH_XY_CM = (.25, .5, 1.)                                 # horizontal hand moves tried when the gap jumps
POLISH_ACCEPT_GAP_CM = (0., .16)                             # inside the 0.2 cm gap / 0.1 cm penetration key gate
ROLL_OFFSET_CM = (3.875, -32.5)      # the seat fit's chair offset (docs/proposed/seat-pose-fit, chosen dy -32.5)
SEARCH_REACH_CM = FOREARM_TARGET_CLEARANCE_CM + 1.5
CLEARANCE_STRIDE = 1                 # arm skin sampling for the search; reports use every vertex


def envelope(need, dt, half_s=SWIVEL_ENVELOPE_S, sigma_s=SWIVEL_SMOOTH_S):
    """Smooth upper envelope of a per-frame need (max filter +-half_s, Gaussian sigma_s, never below the need)."""
    need = np.asarray(need, float)
    F = len(need)
    if F < 2:
        return need.copy()
    k = int(round(half_s / dt))
    env = np.array([need[max(0, f - k):f + k + 1].max() for f in range(F)])
    sig = sigma_s / dt
    if sig <= 0:
        return env
    x = np.arange(-3 * int(math.ceil(sig)), 3 * int(math.ceil(sig)) + 1)
    ker = np.exp(-.5 * (x / sig) ** 2)
    ker /= ker.sum()
    smooth = np.convolve(np.pad(env, len(x) // 2, mode='edge'), ker, mode='valid')
    return np.maximum(smooth, need)


KEY_RASTER_CM = .02


class KeyRaster:
    """The keycap over-key test of the existing rule (fit_seat_pose_trial.Trial.key_audit: inside the key field and
    over a keycap top triangle, Sub01SurfaceHeightAt) precomputed on a KEY_RASTER_CM grid of cell centres, for the
    SOLVER's inner loop only; every reported gate re-measures with the exact triangle test."""

    def __init__(self, keys, res=KEY_RASTER_CM):
        from fit_seat_rigid_placement import Surface
        self.lo, self.hi, self.res = np.asarray(keys['key_min'][:2], float), np.asarray(keys['key_max'][:2], float), res
        self.n = np.ceil((self.hi - self.lo) / res).astype(int) + 1
        gx, gy = np.meshgrid(self.lo[0] + (np.arange(self.n[0]) + .5) * res, self.lo[1] + (np.arange(self.n[1]) + .5) * res, indexing='ij')
        found, _ = Surface(keys['triangles']).height(np.c_[gx.ravel(), gy.ravel()])
        self.mask = found.reshape(self.n)

    def over(self, xy):
        i = np.floor((xy - self.lo) / self.res).astype(int)
        inb = np.all((xy >= self.lo) & (xy <= self.hi), axis=-1) & np.all((i >= 0) & (i < self.n), axis=-1)
        i = np.clip(i, 0, self.n - 1)
        return inb & self.mask[i[..., 0], i[..., 1]]


class HeightRaster:
    """A surface height map (Sub01SurfaceHeightAt rule at cell centres, KEY_RASTER_CM grid) for the SOLVER's inner loop;
    the reported gates use the exact triangle test."""

    def __init__(self, triangles, res=KEY_RASTER_CM):
        from fit_seat_rigid_placement import Surface
        t = np.asarray(triangles, float)
        self.lo, self.hi, self.res = t[..., :2].reshape(-1, 2).min(0), t[..., :2].reshape(-1, 2).max(0), res
        self.n = np.ceil((self.hi - self.lo) / res).astype(int) + 1
        gx, gy = np.meshgrid(self.lo[0] + (np.arange(self.n[0]) + .5) * res, self.lo[1] + (np.arange(self.n[1]) + .5) * res, indexing='ij')
        found, h = Surface(t).height(np.c_[gx.ravel(), gy.ravel()])
        self.found, self.h = found.reshape(self.n), np.nan_to_num(h).reshape(self.n)

    def height(self, xy):
        xy = np.asarray(xy, float)
        i = np.floor((xy - self.lo) / self.res).astype(int)
        inb = np.all((i >= 0) & (i < self.n), axis=-1)
        i = np.clip(i, 0, self.n - 1)
        return inb & self.found[i[..., 0], i[..., 1]], self.h[i[..., 0], i[..., 1]]


MODE_KEY, MODE_MOUSE, MODE_TRANSIT = 0, 1, 2
MOUSE_PALM_FRACTION = .6                 # main desk-hands contact README: the palm is 60% from wrist to middle knuckle
MOUSE_PALM_BEHIND_CM, MOUSE_PALM_RIGHT_CM = 2.2, 1.2   # ... 2.2 cm behind and 1.2 cm right of the shell's top
MOUSE_PALM_SKIN_CM = 1.6                 # ... the palm rests on the shell: palm skin 16 mm below the bones' line
SEGMENT_SETTLED_CM_S = 20.               # a hand off the keys moving slower than this (smoothed) has arrived
SEGMENT_MIN_S = .2                       # a mouse segment lasts at least this long, else it is transit


def segment_hand(on_keys, palm_ue, dt, keys, mouse):
    """Per frame: KEYBOARD where the existing contact rule has the hand over the keys (the base's own over-key frames);
    MOUSE where the hand is off the keys, beyond the key field's right edge and settled (palm speed below
    SEGMENT_SETTLED_CM_S, Gaussian-smoothed over 0.1 s) for at least SEGMENT_MIN_S; TRANSIT otherwise."""
    F = len(on_keys)
    mode = np.full(F, MODE_TRANSIT)
    mode[on_keys] = MODE_KEY
    if mouse is None:
        return mode
    sp = np.r_[0., np.linalg.norm(np.diff(palm_ue[:, :2], axis=0), axis=1) / dt]
    sig = .1 / dt
    x = np.arange(-3 * int(math.ceil(sig)), 3 * int(math.ceil(sig)) + 1)
    ker = np.exp(-.5 * (x / sig) ** 2)
    sp = np.convolve(np.pad(sp, len(x) // 2, mode='edge'), ker / ker.sum(), mode='valid')
    cand = ~on_keys & (palm_ue[:, 0] > keys['key_max'][0]) & (sp < SEGMENT_SETTLED_CM_S)
    k = 0
    while k < F:
        if not cand[k]:
            k += 1
            continue
        e = k
        while e < F and cand[e]:
            e += 1
        if (e - k) * dt >= SEGMENT_MIN_S:
            mode[k:e] = MODE_MOUSE
        k = e
    return mode


def keyboard_between_keys(mode):
    """Segmentation rule (docs/qa/contact.md, seated "type": both hands' fingertips touch the keycaps, 0 to +2 mm, through
    the whole clip): a TRANSIT run with a KEYBOARD segment on BOTH sides (the hand does not visit the mouse in between)
    is the hand between keystrokes on the keyboard, so it is KEYBOARD (full keycap contact). Only the runs between the
    keyboard and the mouse (or a clip end) stay TRANSIT, and the segment blends live in them."""
    mode = np.array(mode, copy=True)
    F = len(mode)
    k = 0
    while k < F:
        if mode[k] != MODE_TRANSIT:
            k += 1
            continue
        e = k
        while e < F and mode[e] == MODE_TRANSIT:
            e += 1
        if k > 0 and e < F and mode[k - 1] == MODE_KEY and mode[e] == MODE_KEY:
            mode[k:e] = MODE_KEY
        k = e
    return mode


KEY_FIELD_MARGIN_CM = .5          # a keyboard frame's finger target is pulled this far inside the key field ...
KEY_FIELD_MIN_OVER = 2 * T.KEY_MIN_OVER_VERTICES    # ... while fewer distal vertices than this are over the keycaps


def key_field_pull(p_xy, key_min, key_max, n=KEY_FIELD_MIN_OVER, margin=KEY_FIELD_MARGIN_CM):
    """(F, V, 2) distal finger skin XY -> (F, 2) the move of the n-th nearest vertex into the key field (shrunk by
    margin): the nearer vertices need less, so at least n distal vertices end up over the field."""
    lo, hi = np.asarray(key_min[:2], float) + margin, np.asarray(key_max[:2], float) - margin
    d = np.clip(p_xy, lo, hi) - p_xy
    nrm = np.linalg.norm(d, axis=-1)
    idx = np.argsort(nrm, axis=1)[:, n - 1]
    return d[np.arange(len(d)), idx]


def mouse_geometry(cache=None):
    """The actual mouse: web/room/mouse.glb at the home.js placement furnished("mouse", 2.4, .846, -2.91, .22) (width
    0.22 m along x, bottom at .846 m, centred); its pad's UE footprint equals root's LINEA record mouse nodes 236-238
    (X 229..251, Y -301.45..-280.55). The shell top and main's palm target on it (README: 2.2 cm behind, 1.2 cm right
    of the shell's top; palm bone line 1.6 cm over the shell)."""
    path = ROOT / 'web/room/mouse.glb'
    g = G.Gltf(E.decoded(path, Path(cache or ROOT / 'out/seat-fit-cache')))
    w = G.world_pose(g, G.RestPose, 0.)
    parts = {}
    for i, n in enumerate(g.nodes):
        if 'mesh' not in n:
            continue
        M = E.trs(*w[i])
        for pr in g.doc['meshes'][n['mesh']]['primitives']:
            P_ = E.accessor(g, pr['attributes']['POSITION']) @ M[:3, :3].T + M[:3, 3]
            idx = E.accessor(g, pr['indices']).astype(int).reshape(-1, 3)
            parts[n.get('name', str(i))] = (P_, idx)
    A = np.concatenate([v for v, _ in parts.values()])
    lo, hi = A.min(0), A.max(0)
    sc = .22 / (hi[0] - lo[0])
    c = (lo + hi) / 2
    off = np.array([2.4 - c[0] * sc, .846 - lo[1] * sc, -2.91 - c[2] * sc])
    ue = {k: ((v * sc + off)[:, [0, 2, 1]] * 100., idx) for k, (v, idx) in parts.items()}
    shell, sidx = ue['mouse']
    top = shell[shell[:, 2].argmax()]
    tri = shell[sidx][:, [0, 2, 1]]
    from fit_seat_rigid_placement import Surface
    surf = Surface(tri)
    xy = top[:2] + [MOUSE_PALM_RIGHT_CM, MOUSE_PALM_BEHIND_CM]   # +X is his right, +Y toward him (faces -Y)
    found, h = surf.height(xy[None])
    z = float(h[0]) if found[0] else float(top[2])
    allp = np.concatenate([v for v, _ in ue.values()])
    return {'source': rel(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'placement': 'web/house/home.js furnished("mouse", 2.4, 0.846, -2.91, 0.22): width .22 m on x, bottom .846 m',
            'footprint_ue_cm': [allp.min(0).tolist(), allp.max(0).tolist()],
            'root_record_mouse_nodes_236_238_xy_cm': [[229.0, -301.45], [251.0, -280.55]],
            'shell_top_cm': top.tolist(), 'shell_surface_at_palm_cm': z,
            'palm_target_cm': np.array([xy[0], xy[1], z + MOUSE_PALM_SKIN_CM]), 'shell_triangles_cm': tri,
            'rule': 'origin/main docs/design/desk-hands/contact/README.md (resolver step 2-3, mouse)'}


class ClipArmIK:
    """Whole-arm IK on one seated clip. W_fit: the seat-fitted clip's joint worlds (solver frame = the rolled world);
    W_raw: the raw capture at the same times (wrist relative rotation and elbow pole). body_shift_cm (F, 3): the body's
    UE offset from the rolled placement at each frame (the roll still to go; zero once rolled)."""

    def __init__(self, base, W_fit, W_raw, times, keys, cushion_tri, arm_skins, geometry, body_shift_cm=None,
                 contact=True, roll=ROLL_OFFSET_CM, finger_xy_target=None, on_mask=None, ergonomic=True):
        d = dict(base.d)
        d['joint_world'], d['times'] = np.asarray(W_fit), np.asarray(times, float)
        self.src = E.Source(d)
        self.sk = T.Skeleton(self.src)
        self.trial = T.Trial(self.src, cushion_tri, keys, tuple(roll))
        self.W_fit, self.W_raw = np.asarray(W_fit), np.asarray(W_raw)
        self.times = np.asarray(times, float)
        self.dt = float(np.median(np.diff(self.times))) if len(self.times) > 1 else 1 / 60
        self.ibm, self.names = base.ibm, base.names
        self.keys, self.arm_skins, self.geometry = keys, arm_skins, geometry
        self.boxes, self.box_nodes = desk_boxes(geometry)
        F = len(self.times)
        self.body_shift = np.zeros((F, 3)) if body_shift_cm is None else np.asarray(body_shift_cm, float)
        self.contact = contact
        self.ergonomic = ergonomic
        # Horizontal fingertip targets (UE world XY per frame): the seat fit's own distal finger skin centroid, i.e. the
        # captured horizontal hand path the existing contact pipeline placed over the keycaps. The wrist target gets a
        # per-frame horizontal correction (self.hand_xy, glTF metres) so the IK hand lands on the same keycaps.
        self.finger_xy_target = finger_xy_target
        self.mouse = None                 # set by Context.ik: main's mouse contact target at the actual mouse
        self.on_mask = on_mask
        self.hand_xy = {s: np.zeros((F, 3)) for s in SIDES}
        self.girdle = {s: np.zeros((F, 2)) for s in SIDES}      # (depression, protraction) degrees per frame
        self.pitch = {s: np.zeros(F) for s in SIDES}             # added palmar wrist flexion (deg), finish() only
        self.gain = {s: np.ones(F) for s in SIDES}               # per-frame vertical contact response (secant)
        self.deadline = None

    # --- measurements (UE cm, at each frame's actual body placement)
    def arm_points(self, W, side, stride=1, frames=None, posed_frames=False):
        pos, jts, wts = self.arm_skins[side]['skin']
        part = self.arm_skins[side]['part']
        sel = slice(None, None, stride)
        Wf = W if (frames is None or posed_frames) else W[frames]
        shift = self.body_shift if frames is None else self.body_shift[frames]
        pts = E.to_ue(lbs((pos[sel], jts[sel], wts[sel]), self.ibm, Wf)) + shift[:, None, :]
        return pts, part[sel]

    def clearance(self, W, side, stride=1, frames=None, reach=None, posed_frames=False):
        pts, part = self.arm_points(W, side, stride, frames, posed_frames)
        d, which = boxes_min_distance(pts, self.boxes, reach)
        return d.min(axis=1), d, which, pts, part

    def key_audit(self, W, frames=None):
        """The existing keyboard rule at each frame's actual body placement (hands translated with the body). With a
        KeyRaster (solver inner loop) the over-key test is the precomputed raster; otherwise the exact triangle test."""
        shift = self.body_shift if frames is None else self.body_shift[frames]
        if getattr(self, 'raster', None) is not None and not getattr(self, 'exact_audit', False):
            out = {}
            for s in SIDES:
                p, _ = self.trial.skin_ue(f'{s}_fingers', W)
                p = p + shift[:, None, :]
                over = self.raster.over(p[..., :2])
                out[s] = {'over': over.sum(axis=1), 'over_min': np.where(over, p[..., 2], np.inf).min(axis=1)}
            return out
        if not shift.any():
            return self.trial.key_audit(W)
        Ws = np.array(W, copy=True)
        Ws[..., :3, 3] += np.stack([P.ue_delta_to_gltf(v) for v in shift])[:, None, :]
        return self.trial.key_audit(Ws)

    # --- the solve
    def side_inputs(self, side):
        a, b, c = (self.sk.j(n) for n in ARM_BONES[side])
        A = self.W_fit[:, a, :3, 3]
        d = A - self.W_raw[:, a, :3, 3]
        pole = self.W_raw[:, b, :3, 3] + d
        wrist = self.W_raw[:, c, :3, 3] + d
        hand_world = self.W_raw[:, c, :3, :3]        # the upper body keeps its captured world orientation in the fit
        return A, pole, wrist, hand_world, None

    def pose(self, W, side, delta_cm, phi_rad, lift_cm=None, frames=None, girdle=None):
        A, pole, wrist, hand_world, _ = self.inputs[side]
        if frames is not None:
            A, pole, wrist, hand_world = A[frames], pole[frames], wrist[frames], hand_world[frames]
        g = self.girdle[side] if girdle is None else girdle
        g = g if frames is None or girdle is not None else g[frames]
        if np.any(g):
            W = shoulder_girdle(self.sk, W.copy(), side, g)
            A2 = W[:, self.sk.j(ARM_BONES[side][0]), :3, 3]
            pole = pole + (A2 - A)
            A = A2
        hxy = self.hand_xy[side] if frames is None else self.hand_xy[side][frames]
        tgt = wrist + hxy + UP * (np.asarray(delta_cm) + (0. if lift_cm is None else np.asarray(lift_cm)))[:, None] / 100.
        sign = self.raise_sign[side] if frames is None else self.raise_sign[side][frames]
        p = swivel_pole(A, tgt, pole, np.asarray(phi_rad) * sign)
        fl = getattr(self, 'pitch', None)
        fl = None if fl is None else (fl[side] if frames is None else fl[side][frames])
        W, reach, length, dist, _ = solve_arm(self.sk, W.copy(), side, tgt, p, self.ibm, hand_world=hand_world, flex_add_deg=fl)
        return W, reach, length, dist

    def solve(self):
        """Per side and frame: contact first (swivel 0), then the smallest elbow swivel (grid, raising the elbow) whose
        contact-resolved pose keeps every arm skin vertex FOREARM_TARGET_CLEARANCE_CM from the real desk; the swivel is
        then a smooth upper envelope over time and the contact is re-solved. Off-key frames that no swivel clears lift
        the hand; on-key frames that no swivel clears keep the best swivel and are reported (never hidden)."""
        F = len(self.times)
        self.prepare()
        zero = np.zeros(F)
        delta = {s: zero.copy() for s in SIDES}
        phi = {s: zero.copy() for s in SIDES}
        lift = {s: zero.copy() for s in SIDES}
        history = []
        return self._solve(F, zero, delta, phi, lift, history)

    def prepare(self):
        """Inputs, swivel sign, on-key mask and hand segments (also used to rebuild a stitched chunked solve)."""
        F = len(self.times)
        self.inputs = {s: self.side_inputs(s) for s in SIDES}
        self.raise_sign = {}
        for s in SIDES:
            A, pole, wrist, _, _ = self.inputs[s]
            dz = np.cross((wrist - A) / np.linalg.norm(wrist - A, axis=-1, keepdims=True), pole - A)[:, 1]
            self.raise_sign[s] = np.where(dz >= 0, 1., -1.)      # +phi raises the elbow (glTF y is up)
        zero = np.zeros(F)
        W0 = self.W_fit.copy()
        for s in SIDES:
            W0, _, _, _ = self.pose(W0, s, zero, zero)
        audit = self.key_audit(W0)
        if self.on_mask is not None:
            self.on = {s: np.asarray(self.on_mask[s], bool) & self.contact for s in SIDES}
        else:
            self.on = {s: (audit[s]['over'] >= KEY_MIN_OVER_VERTICES) if self.contact else np.zeros(F, bool) for s in SIDES}
        if getattr(self, 'mode_override', None) is not None:
            self.mode = {s: np.asarray(self.mode_override[s]).copy() for s in SIDES}
        else:
            self.mode = {s: keyboard_between_keys(segment_hand(
                self.on[s], self.palm_ue(self.W_fit, s, np.arange(F)), self.dt, self.keys,
                self.mouse if (self.mouse is not None and s == 'right') else None)) for s in SIDES}
        # every KEYBOARD frame is gated as on the keys (the base's over-key frames plus the reclassified runs)
        self.on = {s: self.on[s] | (self.mode[s] == MODE_KEY) for s in SIDES}

    def pose_all(self):
        W = self.W_fit.copy()
        for s in SIDES:
            W = self.pose(W, s, self.delta[s], self.phi[s], self.lift[s])[0]
        return W

    def clear_side(self, s, delta, phi, lift, history, outer_passes=3):
        """Every-arm-vertex desk clearance for one side (mutates the delta / phi / lift dicts): the smallest elbow swivel
        (coarse-to-fine grid) whose contact-resolved pose keeps FOREARM_TARGET_CLEARANCE_CM, a smooth envelope over time,
        and on TRANSIT frames that no swivel clears a smooth hand lift."""
        for outer in range(outer_passes):
            Wc = self.pose(self.W_fit.copy(), s, delta[s], phi[s], lift[s])[0]
            cl = self.clearance(Wc, s, CLEARANCE_STRIDE, reach=SEARCH_REACH_CM)[0]
            bad = np.nonzero(cl < FOREARM_TARGET_CLEARANCE_CM)[0]
            history.append({'side': s, 'pass': outer, 'frames_below_target': int(len(bad)), 'min_cm': float(cl.min())})
            if not len(bad):
                break
            need = phi[s].copy()
            best_cl, best_phi = np.full(len(bad), -np.inf), phi[s][bad].copy()
            found_at = np.full(len(bad), np.nan)

            def probe(g, sel):
                fr = bad[sel]
                ph = phi[s].copy()
                ph[fr] = np.maximum(phi[s][fr], math.radians(g))
                dl = self.solve_contact_side(s, delta[s], ph, lift[s], fr, passes=SEARCH_CONTACT_PASSES)
                Wt = self.pose(self.W_fit[fr].copy(), s, dl[fr], ph[fr], lift[s][fr], fr)[0]
                clt = self.clearance(Wt, s, CLEARANCE_STRIDE, fr, SEARCH_REACH_CM, posed_frames=True)[0]
                idx = np.nonzero(sel)[0]
                better = clt > best_cl[idx]
                best_cl[idx[better]], best_phi[idx[better]] = clt[better], ph[fr][better]
                return idx, clt >= FOREARM_TARGET_CLEARANCE_CM, ph[fr]
            # coarse-to-fine: the first coarse step that clears, then the fine grid inside the step before it
            todo = np.ones(len(bad), bool)
            for g in SWIVEL_COARSE_DEG:
                if not todo.any():
                    break
                idx, ok, ph = probe(g, todo)
                found_at[idx[ok]] = g
                todo[idx[ok]] = False
            fine = ~np.isnan(found_at)
            for g in SWIVEL_GRID_DEG:
                sel = fine & (g > found_at - SWIVEL_COARSE_STEP_DEG) & (g < found_at)
                if not sel.any():
                    continue
                idx, ok, ph = probe(g, sel)
                found_at[idx[ok]] = np.minimum(found_at[idx[ok]], g)
            for k in np.nonzero(fine)[0]:
                need[bad[k]] = max(phi[s][bad[k]], math.radians(found_at[k]))
            need[bad[todo]] = best_phi[todo]                  # no swivel clears: the best one (reported)
            phi[s] = envelope(need, self.dt)
            delta[s] = self.solve_contact_side(s, delta[s], phi[s], lift[s])
            off = bad[todo][self.mode[s][bad[todo]] == MODE_TRANSIT]
            if len(off):                                      # transit: lift the hand (no contact required)
                lift[s] = np.maximum(lift[s], self.lift_need(s, delta[s], phi[s], lift[s], off))
                delta[s] = self.solve_contact_side(s, delta[s], phi[s], lift[s])

    def _solve(self, F, zero, delta, phi, lift, history):
        def clear_side(s, outer_passes=3):
            self.clear_side(s, delta, phi, lift, history, outer_passes)

        for s in SIDES:
            delta[s] = self.solve_contact_side(s, delta[s], phi[s], lift[s])
            clear_side(s)
        self.ergonomics = {}
        if self.ergonomic:
            for s in SIDES:
                phi[s], delta[s], self.ergonomics[s] = self.ergonomic_refine(s, delta[s], phi[s], lift[s])
        self.exact_audit = True                  # final contact passes with the exact keycap triangle test
        for s in SIDES:
            delta[s] = self.solve_contact_side(s, delta[s], phi[s], lift[s], passes=CONTACT_PASSES)
            clear_side(s, 2)                     # the final contact must not undo the clearance (every arm vertex)
        W = self.W_fit.copy()
        for s in SIDES:
            W = self.pose(W, s, delta[s], phi[s], lift[s])[0]
        self.delta, self.phi, self.lift, self.history = delta, phi, lift, history
        return W

    def arm_ergonomics(self, W, s, frames):
        """Elbow height (UE cm, world) and upper-arm angle from vertical-down (deg) of the posed frames."""
        a, b = (self.sk.j(n) for n in ARM_BONES[s][:2])
        sh = E.to_ue(W[:, a, :3, 3]) + self.body_shift[frames]
        el = E.to_ue(W[:, b, :3, 3]) + self.body_shift[frames]
        ua = np.degrees(np.arccos(np.clip((sh[:, 2] - el[:, 2]) / np.linalg.norm(el - sh, axis=1), -1, 1)))
        return el[:, 2], ua

    def ergonomic_cost(self, elbow_z, upper_arm_deg):
        top = self.geometry['tabletop_slab']['top_cm']
        lo, hi = top + ERGO_ELBOW_ABOVE_DESK_CM[0], top + ERGO_ELBOW_ABOVE_DESK_CM[1]
        ez = np.maximum(0., elbow_z - hi) + np.maximum(0., lo - elbow_z)
        ua = np.maximum(0., upper_arm_deg - ERGO_UPPER_ARM_MAX_DEG)
        return (ez / ERGO_ELBOW_SCALE_CM) ** 2 + (ua / ERGO_UPPER_ARM_SCALE_DEG) ** 2

    def ergonomic_refine(self, s, delta, phi, lift):
        """Ergonomic objective (SOFT targets, never gates): among the elbow swivels (signed grid, lowering as well as
        raising) whose contact-resolved pose keeps every arm skin vertex FOREARM_TARGET_CLEARANCE_CM from the real desk
        and the keys unpenetrated, take the one with the lowest cost: elbow height outside [desk top + 0, + 10] cm and
        upper arm beyond 20 deg from vertical (ERGO_*). Then a Gaussian smoothing over time, kept only where it still
        clears. The clearance gate is never traded for the objective."""
        F = len(self.times)
        fr = np.arange(F)
        best_cost = np.full(F, np.inf)
        best_phi, best_delta = phi.copy(), delta.copy()
        Wc = self.pose(self.W_fit.copy(), s, delta, phi, lift)[0]
        ez, ua = self.arm_ergonomics(Wc, s, fr)
        ok0 = self.clearance(Wc, s, CLEARANCE_STRIDE, reach=SEARCH_REACH_CM)[0] >= FOREARM_TARGET_CLEARANCE_CM
        best_cost[ok0] = self.ergonomic_cost(ez, ua)[ok0]
        before = {'elbow_z_cm': rng(ez, 2), 'upper_arm_deg': rng(ua, 2)}
        hxy0 = self.hand_xy[s].copy()
        g0 = self.girdle[s].copy()
        best_hxy, best_g = hxy0.copy(), g0.copy()
        tried, stopped = 0, None
        for gd in ERGO_GIRDLE:
            for g in ERGO_SWIVEL_DEG:
                if self.deadline is not None and time.time() > self.deadline:
                    stopped = f'wall-clock bound reached after {tried} candidates'
                    break
                tried += 1
                ph = np.full(F, math.radians(g))
                self.hand_xy[s] = hxy0.copy()           # every candidate starts from the same horizontal correction
                self.girdle[s] = np.tile(gd, (F, 1))
                dl = self.solve_contact_side(s, delta, ph, lift, fr, passes=SEARCH_CONTACT_PASSES)
                Wt = self.pose(self.W_fit.copy(), s, dl, ph, lift)[0]
                ok = self.clearance(Wt, s, CLEARANCE_STRIDE, reach=SEARCH_REACH_CM)[0] >= FOREARM_TARGET_CLEARANCE_CM
                ez, ua = self.arm_ergonomics(Wt, s, fr)
                c = np.where(ok, self.ergonomic_cost(ez, ua) + 1e-6 * (abs(g) + abs(gd[0]) + abs(gd[1])), np.inf)
                better = c < best_cost
                best_cost[better], best_phi[better], best_delta[better] = c[better], ph[better], dl[better]
                best_hxy[better] = self.hand_xy[s][better]
                best_g[better] = gd
            if stopped:
                break
        self.hand_xy[s] = best_hxy
        sigg = SWIVEL_SMOOTH_S / self.dt
        xg = np.arange(-3 * int(math.ceil(sigg)), 3 * int(math.ceil(sigg)) + 1)
        kg = np.exp(-.5 * (xg / sigg) ** 2)
        kg /= kg.sum()
        self.girdle[s] = np.stack([np.convolve(np.pad(best_g[:, i], len(xg) // 2, mode='edge'), kg, mode='valid') for i in range(2)], 1)
        sig = SWIVEL_SMOOTH_S / self.dt
        x = np.arange(-3 * int(math.ceil(sig)), 3 * int(math.ceil(sig)) + 1)
        ker = np.exp(-.5 * (x / sig) ** 2)
        ker /= ker.sum()
        sm = np.convolve(np.pad(best_phi, len(x) // 2, mode='edge'), ker, mode='valid')
        dl = self.solve_contact_side(s, best_delta, sm, lift)
        Wt = self.pose(self.W_fit.copy(), s, dl, sm, lift)[0]
        ok = self.clearance(Wt, s, CLEARANCE_STRIDE, reach=SEARCH_REACH_CM)[0] >= FOREARM_TARGET_CLEARANCE_CM
        out = np.where(ok, sm, best_phi)
        dl = self.solve_contact_side(s, best_delta, out, lift)
        # final verification on EVERY arm vertex: a frame the objective left closer than the target (or off its key
        # contact) returns exactly to its clearance-solved pose (phi, delta and horizontal correction)
        Wt = self.pose(self.W_fit.copy(), s, dl, out, lift)[0]
        clf = self.clearance(Wt, s, 1, reach=SEARCH_REACH_CM)[0]
        a = self.key_audit(Wt)[s]
        gap = a['over_min'] - (self.keys['top_cm'] + KEY_TOP_TARGET_CM)
        bad = (clf < FOREARM_TARGET_CLEARANCE_CM) | (self.on[s] & ~(np.abs(np.nan_to_num(gap, nan=9.)) < .01))
        out, dl = np.where(bad, phi, out), np.where(bad, delta, dl)
        self.hand_xy[s][bad] = hxy0[bad]
        self.girdle[s][bad] = g0[bad]
        Wt = self.pose(self.W_fit.copy(), s, dl, out, lift)[0]
        ez, ua = self.arm_ergonomics(Wt, s, fr)
        return out, dl, {'before': before, 'after': {'elbow_z_cm': rng(ez, 2), 'upper_arm_deg': rng(ua, 2)},
                         'girdle_depression_deg': rng(self.girdle[s][:, 0], 2), 'girdle_protraction_deg': rng(self.girdle[s][:, 1], 2),
                         'candidates_tried': tried, 'bounded_stop': stopped,
                         'frames_unsmoothed': int((~ok).sum()), 'frames_reverted_to_clearance_pose': int(bad.sum()),
                         'swivel_deg': rng(np.degrees(out), 2)}

    def lift_need(self, s, delta, phi, lift, frames):
        out = lift.copy()
        todo = np.array(frames)
        k = 0.
        while len(todo) and k < LIFT_MAX_CM:
            k += LIFT_STEP_CM
            trial = lift.copy()
            trial[todo] = lift[todo] + k
            Wt = self.pose(self.W_fit[todo].copy(), s, delta[todo], phi[todo], trial[todo], todo)[0]
            ok = self.clearance(Wt, s, CLEARANCE_STRIDE, todo, SEARCH_REACH_CM, posed_frames=True)[0] >= FOREARM_TARGET_CLEARANCE_CM
            out[todo[ok]] = trial[todo[ok]]
            todo = todo[~ok]
        out[todo] = lift[todo] + LIFT_MAX_CM
        # never on a keyboard / mouse frame (contact owns those): the fit's smooth lift, tapered to zero next to them
        return P.smooth_lift(out, self.mode[s] != MODE_TRANSIT)

    def mouse_gap(self, W, s, frames):
        """Lowest hand/finger skin height over the mouse shell (cm; +inf where no skin is over the shell)."""
        pos, jts, wts = self.arm_skins[s]['skin']
        sel = np.isin(self.arm_skins[s]['part'], ('hand', 'fingers'))
        key = ('mouse_skin', s)
        if key not in self.__dict__.setdefault('_sub', {}):
            self._sub[key] = (pos[sel], jts[sel], wts[sel])
        pts = E.to_ue(lbs(self._sub[key], self.ibm, W)) + self.body_shift[frames][:, None, :]
        found, h = self.mouse_surface.height(pts[..., :2].reshape(-1, 2))
        g = np.where(found, pts[..., 2].reshape(-1) - np.nan_to_num(h), np.inf).reshape(pts.shape[:2])
        return g.min(axis=1)

    def palm_ue(self, W, s, frames):
        """Main's mouse palm point (docs/design/desk-hands/contact/README.md): 60% from the wrist to the middle knuckle."""
        p = SIDES[s]
        wr = E.to_ue(W[:, self.sk.j(f'{p}Hand'), :3, 3])
        m1 = E.to_ue(W[:, self.sk.j(f'{p}HandMiddle1'), :3, 3])
        return wr + MOUSE_PALM_FRACTION * (m1 - wr) + self.body_shift[frames]

    def solve_contact_side(self, s, delta, phi, lift, frames=None, passes=CONTACT_PASSES):
        """Per frame by segment (self.mode): KEYBOARD frames - the over-key distal skin minimum to KeyTop + 0.08 cm and the
        distal finger centroid on the fit's hand path; MOUSE frames - main's mouse contact (palm point onto
        self.mouse['palm_target_cm'], the palm bone line MOUSE_PALM_SKIN_CM over the shell); TRANSIT frames - the
        corrections are the C1 (quintic smootherstep) blend of the neighbouring segment-end corrections, and are only
        ever lifted over the keys. Iterated (the hand rides on the forearm, so its orientation follows the IK), with a
        damped update after the first passes."""
        top = self.keys['top_cm'] + KEY_TOP_TARGET_CM
        delta = delta.copy()
        fr = np.arange(len(self.times)) if frames is None else np.asarray(frames)
        mode = self.mode[s][fr]
        key, mouse = mode == MODE_KEY, mode == MODE_MOUSE
        def residual(d):
            Wt = self.pose(self.W_fit[fr].copy(), s, d, phi[fr], lift[fr], fr)[0]
            a_ = self.key_audit(Wt, fr)[s]
            kres = top - a_['over_min']
            vres = np.zeros(len(fr))
            if mouse.any():
                gap = self.mouse_gap(Wt[mouse], s, fr[mouse])
                vres[mouse] = np.where(np.isfinite(gap), KEY_TOP_TARGET_CM - gap, np.nan)
            r_ = np.where(key, kres, np.where(mouse, vres, np.nan))
            return np.where(np.isfinite(r_), r_, np.nan), Wt, a_
        rounds = max(1, passes // 6)
        for _ in range(rounds):
            # (1) horizontal: keyboard frames follow the fit's finger path, mouse frames put the palm on main's point
            for _h in range(3):
                Wt = self.pose(self.W_fit[fr].copy(), s, delta[fr], phi[fr], lift[fr], fr)[0]
                dxy = np.zeros((len(fr), 2))
                if self.finger_xy_target is not None and key.any():
                    pk = self.trial.skin_ue(f'{s}_fingers', Wt[key])[0] + self.body_shift[fr[key]][:, None, :]
                    cen = pk.mean(axis=1)[:, :2]
                    kmin, kmax = self.keys['key_min'], self.keys['key_max']
                    inb = ((pk[..., 0] >= kmin[0]) & (pk[..., 0] <= kmax[0]) & (pk[..., 1] >= kmin[1]) & (pk[..., 1] <= kmax[1])).sum(1)
                    on_caps = self.raster.over(pk[..., :2]).sum(1) if getattr(self, 'raster', None) is not None else inb
                    low = on_caps < KEY_FIELD_MIN_OVER
                    if low.any():      # the fit's path leaves the keycaps: its target moves (persistently) back in
                        pull = key_field_pull(pk[low][..., :2], kmin, kmax)
                        # inside the field but between / beside the keycaps: a 0.5 cm step toward the field centre
                        mid = (np.asarray(kmin[:2]) + np.asarray(kmax[:2])) / 2 - cen[low]
                        step = KEY_FIELD_MARGIN_CM * mid / np.maximum(np.linalg.norm(mid, axis=1, keepdims=True), 1e-9)
                        pull = np.where((np.linalg.norm(pull, axis=1) < 1e-6)[:, None], step, pull)
                        self.finger_xy_target[s][fr[key][low]] = cen[low] + pull
                    dxy[key] = self.finger_xy_target[s][fr[key]] - cen
                if mouse.any():
                    dxy[mouse] = (self.mouse['palm_target_cm'][None] - self.palm_ue(Wt[mouse], s, fr[mouse]))[:, :2]
                if np.abs(dxy).max() < CONTACT_TOL_CM * 10:
                    break
                self.hand_xy[s][fr] += gltf_shift(np.c_[dxy, np.zeros(len(fr))])
            # (2) vertical: bracketed bisection of the contact residual per frame (robust to the hand turning with
            # the forearm, where 1 cm of wrist is not 1 cm of fingertip and can even act the other way)
            act = key | mouse
            if not act.any():
                break
            if passes <= SEARCH_CONTACT_PASSES:
                # search probes (clearance / ergonomics only): a few plain residual steps are enough there; every
                # kept pose is re-solved by the bisection below
                for _p in range(passes):
                    r_ = residual(delta[fr])[0]
                    delta[fr] = delta[fr] + np.where(act & np.isfinite(r_), r_, 0.)
                continue
            d0 = delta[fr].copy()
            lo, hi = d0 - CONTACT_BRACKET_CM, d0 + CONTACT_BRACKET_CM
            flo, fhi = residual(lo)[0], residual(hi)[0]
            for _e in range(2):
                same = act & np.isfinite(flo) & np.isfinite(fhi) & (np.sign(flo) == np.sign(fhi))
                if not same.any():
                    break
                w_ = hi - lo
                lo, hi = np.where(same, lo - w_, lo), np.where(same, hi + w_, hi)
                flo, fhi = residual(lo)[0], residual(hi)[0]
            ok = act & np.isfinite(flo) & np.isfinite(fhi) & (np.sign(flo) != np.sign(fhi))
            for _b in range(CONTACT_BISECTIONS):
                mid = .5 * (lo + hi)
                fm = residual(mid)[0]
                left = ok & np.isfinite(fm) & (np.sign(fm) == np.sign(flo))
                lo, flo = np.where(left, mid, lo), np.where(left, fm, flo)
                hi, fhi = np.where(ok & ~left, mid, hi), np.where(ok & ~left, fm, fhi)
            # regula falsi finish inside the final bracket
            with np.errstate(divide='ignore', invalid='ignore'):
                rf = lo - flo * (hi - lo) / (fhi - flo)
            new = np.where(ok, np.where(np.isfinite(rf), rf, .5 * (lo + hi)), d0)
            # a root is kept only if it really is contact (the residual is not continuous where the lowest finger
            # changes or the hand leaves the key field); otherwise the frame keeps its previous correction
            fn = residual(new)[0]
            good = ok & np.isfinite(fn) & (np.abs(fn) <= CONTACT_ACCEPT_CM)
            delta[fr] = np.where(good, new, d0)
            # frames the bracket did not resolve: plain residual steps from the previous correction, kept per frame
            # whenever they reduce the residual (never a wild jump)
            rest = act & ~good
            if rest.any():
                d = delta[fr].copy()
                r_ = residual(d)[0]
                best_d, best_r = d.copy(), np.where(np.isfinite(r_), np.abs(r_), np.inf)
                for _p in range(CONTACT_PASSES):
                    d = d + np.where(rest & np.isfinite(r_), np.clip(r_, -CONTACT_BRACKET_CM, CONTACT_BRACKET_CM), 0.)
                    r_ = residual(d)[0]
                    ar = np.where(np.isfinite(r_), np.abs(r_), np.inf)
                    imp = rest & (ar < best_r)
                    best_d[imp], best_r[imp] = d[imp], ar[imp]
                    if (best_r[rest] <= CONTACT_TOL_CM).all():
                        break
                delta[fr] = np.where(rest, best_d, delta[fr])
        # frames that are neither keyboard nor mouse: only ever lifted over the keycaps (below)
        if frames is None:
            delta = self.blend_transit(s, delta)
            tr = self.mode[s] == MODE_TRANSIT
            for _ in range(passes if tr.any() else 0):         # transit: only ever lifted over the keycaps
                Wt = self.pose(self.W_fit.copy(), s, delta, phi, lift)[0]
                a = self.key_audit(Wt)[s]
                up = np.where(tr & (a['over'] > 0), np.maximum(top - a['over_min'], 0.), 0.)
                up = np.nan_to_num(up)
                if up.max() < CONTACT_TOL_CM:
                    break
                delta = delta + envelope(up, self.dt) * tr
        return delta

    def blend_transit(self, s, delta):
        """Transit runs take the C1 blend (quintic smootherstep, zero slope at both ends) of the corrections at the
        frames just before and after the run; a run at either end of the clip holds its one neighbour."""
        mode = self.mode[s]
        F = len(mode)
        tr = mode == MODE_TRANSIT
        if not tr.any() or tr.all():
            return delta
        delta = delta.copy()
        k = 0
        while k < F:
            if not tr[k]:
                k += 1
                continue
            e = k
            while e < F and tr[e]:
                e += 1
            a_, b_ = k - 1, e                     # neighbouring segment frames (may be out of range)
            n = e - k
            u = smootherstep((np.arange(n) + 1) / (n + 1))
            for arr in (delta, self.hand_xy[s]):
                va = arr[a_] if a_ >= 0 else arr[b_]
                vb = arr[b_] if b_ < F else arr[a_]
                w = u.reshape((-1,) + (1,) * (np.ndim(arr) - 1))
                arr[k:e] = va + (vb - va) * w
            k = e
        return delta


    def finish(self, loop_frames=0, deadline=None):
        """Full-clip pass on a stitched chunked solve (the chunk states are the warm start; the segmentation is the
        whole clip's, so no run is cut by a chunk edge):
        (1) loop closure: over the last `loop_frames` frames the IK inputs (captured wrist, elbow pole and hand world
            rotation) and the swivel, shoulder girdle and transit lift are C1-blended (quintic smootherstep, weight 1 on
            the last frame) to frame 0's, so the loop's last frame solves to its first pose again (contact and
            clearance re-solved below, never assumed);
        (2) contact on every frame by segment with the exact keycap test;
        (3) every-arm-vertex desk clearance (swivel search / transit lift) and the contact again;
        (4) contact polish: keyboard frames still outside the key gate take the vertical wrist correction from a
            0.05 cm grid that gives contact without reducing the desk clearance below the target."""
        F = len(self.times)
        t0 = time.time()
        delta, phi, lift = ({s: np.array(v[s], float) for s in SIDES} for v in (self.delta, self.phi, self.lift))
        history = []
        if loop_frames:
            self.close_loop(int(loop_frames), phi, lift)
        self.exact_audit = True
        for s in SIDES:
            delta[s] = self.solve_contact_side(s, delta[s], phi[s], lift[s], passes=CONTACT_PASSES)
            self.clear_side(s, delta, phi, lift, history, 2)
        girdle, pitch = {}, {}
        for s in SIDES:
            pitch[s] = []
            for _r_ in range(PITCH_CLEAR_ROUNDS):      # the full-clip contact re-solve can move neighbours: repeat
                pitch[s].append(self.girdle_clear(s, delta, phi, lift, 'pitch', PITCH_CLEAR_CANDIDATES))
                if not pitch[s][-1]['frames']:
                    break
                delta[s] = self.solve_contact_side(s, delta[s], phi[s], lift[s], passes=CONTACT_PASSES)
                self.clear_side(s, delta, phi, lift, history, 1)
            girdle[s] = self.girdle_clear(s, delta, phi, lift)
            if girdle[s]['frames']:
                delta[s] = self.solve_contact_side(s, delta[s], phi[s], lift[s], passes=CONTACT_PASSES)
                self.clear_side(s, delta, phi, lift, history, 1)
        if loop_frames:      # the clearance envelopes reach the clip ends: the tail parameters are blended again
            self.close_loop(int(loop_frames), phi, lift, inputs=False)
            n = int(loop_frames)
            for s in SIDES:
                delta[s] = self.solve_contact_side(s, delta[s], phi[s], lift[s], np.arange(F - n, F), passes=CONTACT_PASSES)
        polish = {s: self.contact_polish(s, delta, phi, lift) for s in SIDES}
        self.delta, self.phi, self.lift = delta, phi, lift
        self.finish_report = {'loop_blend_frames': int(loop_frames), 'clearance_history': history, 'contact_polish': polish, 'wrist_clearance': pitch, 'girdle_clearance': girdle,
                              'seconds': round(time.time() - t0, 1),
                              'segments': {s: {'key': int((self.mode[s] == MODE_KEY).sum()), 'mouse': int((self.mode[s] == MODE_MOUSE).sum()),
                                               'transit': int((self.mode[s] == MODE_TRANSIT).sum())} for s in SIDES},
                              'segmentation_rule': keyboard_between_keys.__doc__.strip()}
        return self.pose_all()


    def close_loop(self, n, phi, lift, inputs=True):
        """Loop closure inputs: the last n frames' captured wrist, elbow pole and hand world rotation, and the swivel,
        girdle and lift, C1-blended (quintic, weight 1 on the last frame) to frame 0's. Mutates inputs / phi / lift."""
        F = len(self.times)
        w = smootherstep((np.arange(n) + 1) / n)
        for s in SIDES:
            for arr in (phi[s], lift[s]):
                arr[F - n:] += (arr[0] - arr[F - n:]) * w
            self.girdle[s] = np.array(self.girdle[s], float)
            self.girdle[s][F - n:] += (self.girdle[s][0] - self.girdle[s][F - n:]) * w[:, None]
            self.pitch[s] = np.array(self.pitch[s], float)
            self.pitch[s][F - n:] += (self.pitch[s][0] - self.pitch[s][F - n:]) * w
            if not inputs:
                continue
            A, pole, wrist, hw, x = self.inputs[s]
            pole, wrist, hw = pole.copy(), wrist.copy(), hw.copy()
            pole[F - n:] += (pole[0] - pole[F - n:]) * w[:, None]
            wrist[F - n:] += (wrist[0] - wrist[F - n:]) * w[:, None]
            q = P.slerp_arrays(P.quat_from_matrix(unit_rot(hw[F - n:]))[:, None],
                               np.repeat(P.quat_from_matrix(unit_rot(hw[:1]))[:, None], n, axis=0), w)[:, 0]
            hw[F - n:] = quat_to_matrix(q)
            self.inputs[s] = (A, pole, wrist, hw, x)
            dz = np.cross((wrist - A) / np.linalg.norm(wrist - A, axis=-1, keepdims=True), pole - A)[:, 1]
            self.raise_sign[s] = np.where(dz >= 0, 1., -1.)

    def girdle_clear(self, s, delta, phi, lift, attr='girdle', candidates=GIRDLE_CLEAR_CANDIDATES):
        """Frames whose every-vertex desk clearance is still below the target after the swivel search: the first
        GIRDLE_CLEAR_CANDIDATES girdle offset (elevation, then elevation with retraction) whose contact-resolved pose
        clears (and, on keyboard frames, keeps the key gate) is the need; the girdle offset is its smooth upper envelope
        over time (never below a frame's need), added to the girdle already there. Mutates self.girdle / delta."""
        F = len(self.times)
        top = self.keys['top_cm']
        W = self.pose(self.W_fit.copy(), s, delta[s], phi[s], lift[s])[0]
        cl = self.clearance(W, s, 1, reach=SEARCH_REACH_CM)[0]
        bad = np.nonzero(cl < FOREARM_TARGET_CLEARANCE_CM)[0]
        out = {'frames': [int(f) for f in bad], 'min_before_cm': _r(cl.min(), 4)}
        if not len(bad):
            return out
        store = getattr(self, attr)
        g0 = np.array(store[s], float)
        sign = -1. if attr == 'girdle' else 1.          # girdle: elevation / retraction are negative; pitch positive
        need = np.zeros(g0.shape)
        found = np.zeros(len(bad), bool)
        for cand in candidates:
            todo = np.nonzero(~found)[0]
            if not len(todo):
                break
            fr = bad[todo]
            store[s] = g0.copy()
            store[s][fr] = cand
            dl = self.solve_contact_side(s, delta[s], phi[s], lift[s], fr)
            Wt = self.pose(self.W_fit[fr].copy(), s, dl[fr], phi[s][fr], lift[s][fr], fr)[0]
            c = self.clearance(Wt, s, 1, fr, SEARCH_REACH_CM, posed_frames=True)[0]
            a = self.key_audit(Wt, fr)[s]
            g = a['over_min'] - top
            keyok = (self.mode[s][fr] != MODE_KEY) | ((a['over'] >= KEY_MIN_OVER_VERTICES) & (g >= POLISH_ACCEPT_GAP_CM[0])
                                                      & (g <= POLISH_ACCEPT_GAP_CM[1]))
            ok = (c >= FOREARM_TARGET_CLEARANCE_CM) & keyok
            need[fr[ok]] = np.asarray(cand) - g0[fr[ok]]
            found[todo[ok]] = True
        nd = need.reshape(F, -1)
        env = np.stack([sign * envelope(np.maximum(0., sign * nd[:, i]), self.dt) for i in range(nd.shape[1])], 1)
        store[s] = g0 + env.reshape(g0.shape)
        out.update({'dof': attr, 'cleared_by_candidate': int(found.sum()), 'not_cleared': [int(f) for f in bad[~found]],
                    'frames_with_offset': int((np.abs(env).sum(1) > 1e-9).sum())})
        if attr == 'girdle':
            out.update({'elevation_deg': rng(-env[:, 0], 2), 'retraction_deg': rng(-env[:, 1], 2)})
        else:
            out.update({'added_palmar_flexion_deg': rng(env[:, 0], 2)})
        return out

    def contact_polish(self, s, delta, phi, lift, grid=POLISH_GRID_CM, accept=POLISH_ACCEPT_GAP_CM):
        """Keyboard frames outside the key gate (fewer than KEY_MIN_OVER_VERTICES over the keys, gap over the accept band
        or penetration): every vertical correction of a grid around the current one is posed (exact keycap test,
        every arm vertex); the one whose gap is nearest KeyTop + 0.08 cm inside `accept` and whose desk clearance stays
        at least min(target, current) wins. Where the lowest fingertip vertex switches keys / edges (the gap jumps over
        the band), the same grid is tried after a small horizontal hand move (POLISH_XY_CM, 8 directions, smallest
        first). Frames with no such correction keep theirs (reported). Mutates delta / hand_xy."""
        top = self.keys['top_cm']
        W = self.pose(self.W_fit.copy(), s, delta[s], phi[s], lift[s])[0]
        a = self.key_audit(W)[s]
        gap = a['over_min'] - top
        bad = np.nonzero((self.mode[s] == MODE_KEY) & ((a['over'] < KEY_MIN_OVER_VERTICES) | ~((gap >= accept[0]) & (gap <= accept[1]))))[0]
        if not len(bad):
            return {'frames': [], 'fixed': [], 'kept': [], 'moved_xy_cm': {}}
        cl0 = dict(zip(bad.tolist(), self.clearance(W[bad], s, 1, bad, SEARCH_REACH_CM, posed_frames=True)[0]))
        offsets = [(0., 0.)] + [(r * math.cos(t), r * math.sin(t)) for r in POLISH_XY_CM for t in np.arange(8) * math.pi / 4]
        todo, fixed, moved = list(bad), [], {}
        for dxy in offsets:
            if not todo:
                break
            fbs = np.array(todo)
            sh = gltf_shift(np.array([[dxy[0], dxy[1], 0.]]))[0]
            nxt = []
            for c0 in range(0, len(fbs), 8):
                fb = fbs[c0:c0 + 8]
                fr = np.repeat(fb, len(grid))
                d = delta[s][fr] + np.tile(grid, len(fb))
                hxy = self.hand_xy[s].copy()
                self.hand_xy[s][fb] += sh
                Wt = self.pose(self.W_fit[fr].copy(), s, d, phi[s][fr], lift[s][fr], fr)[0]
                at = self.key_audit(Wt, fr)[s]
                g = (at['over_min'] - top).reshape(len(fb), -1)
                ov = at['over'].reshape(len(fb), -1)
                cl = self.clearance(Wt, s, 1, fr, SEARCH_REACH_CM, posed_frames=True)[0].reshape(len(fb), -1)
                need = np.minimum(FOREARM_TARGET_CLEARANCE_CM, np.array([cl0[int(f)] for f in fb]))[:, None]
                ok = (ov >= KEY_MIN_OVER_VERTICES) & (g >= accept[0]) & (g <= accept[1]) & (cl >= need) & (cl > 0)
                cost = np.where(ok, np.abs(g - KEY_TOP_TARGET_CM) + 1e-3 * np.abs(grid)[None], np.inf)
                for i, f in enumerate(fb):
                    j = int(cost[i].argmin())
                    if np.isfinite(cost[i, j]):
                        delta[s][f] = d[i * len(grid) + j]
                        fixed.append(int(f))
                        if dxy != (0., 0.):
                            moved[int(f)] = [_r(dxy[0], 3), _r(dxy[1], 3)]
                    else:
                        self.hand_xy[s][f] = hxy[f]
                        nxt.append(int(f))
            todo = nxt
        return {'frames': [int(f) for f in bad], 'fixed': sorted(fixed), 'kept': sorted(todo), 'moved_xy_cm': moved}


# ---------------------------------------------------------------- the chair roll ACTIVITY (declared, reversible)
CHAIR_REPORT = ROOT / 'docs/proposed/native-chair-measured/20261014-actual-native-chair-surface.json'


def smootherstep(x):
    x = np.clip(np.asarray(x, float), 0., 1.)
    return x * x * x * (x * (6 * x - 15) + 10)


def load_chair(path=CHAIR_REPORT, translation_cm=None):
    """The measured native chair: transform (the INITIAL state), shell vertices and cushion triangles. translation_cm
    (optional): a GIVEN initial chair translation (e.g. a proposed rigid lift so the castors touch the floor); every
    measured vertex and cushion triangle moves rigidly by (given - measured), recorded as proposed_delta_cm."""
    path = Path(path)
    rep = json.loads(path.read_text())
    ch = rep['chair']
    verts = np.concatenate([np.asarray(s['vertices_world_cm'], float) for s in ch['sections']])
    measured = np.asarray(ch['transform']['translation_cm'], float)
    delta = np.zeros(3) if translation_cm is None else np.asarray(translation_cm, float) - measured
    cushion = np.asarray(seat_contact.cushion_triangles(rep), float).reshape(-1, 3, 3) + delta
    out = {'measured_translation_cm': measured.tolist(), 'proposed_delta_cm': delta.tolist(),
           'translation_is_measured': bool(not delta.any())}
    verts = verts + delta
    return out | {'file': rel(path) if path.is_relative_to(ROOT) else str(path),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'translation_cm': list(map(float, measured + delta)),
            'rotation_xyzw': ch['transform']['rotation_xyzw'], 'scale': ch['transform']['scale'],
            'component_world_bounds_cm': {k: (np.asarray(v, float) + delta).tolist() for k, v in ch['component_world_bounds_cm'].items()},
            'shell_vertices_cm': verts, 'cushion_triangles_cm': cushion}


class ChairRoll:
    """'Pull chair in' / 'push back': a runtime XY offset of the chair actor AND the seated body together.
    offset(s) = roll_cm * smootherstep(s), s in [0, 1]; start transform = the measured chair (s = 0), end = start +
    roll_cm (s = 1). Pull-in plays s = t / D over SitToType; push-back plays s = 1 - t / D over TypeToSit, i.e. the
    exact reverse path (same positions, reversed order), ending on the measured transform. Rotation, scale and Z are
    never changed (a castor roll on the floor). Zero velocity and acceleration at both ends (quintic)."""

    def __init__(self, start_cm, roll_cm):
        self.start = np.asarray(start_cm, float)
        self.roll = np.array([roll_cm[0], roll_cm[1], 0.], float)

    def offset(self, s):
        return smootherstep(s)[..., None] * self.roll

    def transform(self, s):
        return self.start + self.offset(s)

    @staticmethod
    def pull_in_s(times):
        t = np.asarray(times, float)
        return (t - t[0]) / (t[-1] - t[0])

    @staticmethod
    def push_back_s(times):
        return 1. - ChairRoll.pull_in_s(times)

    def describe(self, times, s):
        t = np.asarray(times, float)
        off = self.offset(s)
        dt = np.gradient(t)
        vel = np.gradient(off[:, :2], t, axis=0)
        acc = np.gradient(vel, t, axis=0)
        return {'start_translation_cm': [round(float(v), 4) for v in self.start],
                'end_translation_cm': [round(float(v), 4) for v in self.start + self.roll],
                'roll_cm': [round(float(v), 4) for v in self.roll], 'distance_cm': round(float(np.linalg.norm(self.roll)), 4),
                'rotation_and_scale': 'unchanged (measured)', 'z': 'unchanged (floor roll)',
                'path': 'offset = roll * smootherstep(s) (quintic: zero velocity and acceleration at both ends)',
                'per_frame': [{'t': round(float(a), 4), 's': round(float(b), 5),
                               'chair_translation_cm': [round(float(v), 4) for v in self.start + o]}
                              for a, b, o in zip(t, s, off)],
                'peak_speed_cm_s': round(float(np.linalg.norm(vel, axis=1).max()), 3),
                'peak_acceleration_cm_s2': round(float(np.linalg.norm(acc, axis=1).max()), 3),
                'mean_dt_s': round(float(dt.mean()), 5)}


# ---------------------------------------------------------------- the COMPLETE chair (shell, arms, base, castors, lift)
CHAIR_SOURCE = ROOT / 'web/room/chair_owner.glb'      # the owner chair source: the native Mesh_174 at scale 0.6069
CHAIR_SOURCE_SHA256 = 'd27084af80035c7ab278f90daf77a422fabe738095dad0b015a531f86249e2dc'
FLOOR_CM = 2.5                                        # root: LINEA feet / support plane (fit FLOOR_CM 2.5001)
UPHOLSTERY = ('chair_fabric',)                        # compressible: may be pressed in down to SEAT_BAND_CM[0]
CHAIR_MATCH_TOL_CM = .5     # native LOD0 is a reduced mesh: its vertices lie ON the source surface, measured max 0.416 cm


def point_triangle_distance(p, a, b, c):
    """Vectorised exact distance from points p (N,3) to triangles (N,3 each) (Ericson, Real-Time Collision Detection)."""
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = np.sum(ab * ap, -1), np.sum(ac * ap, -1)
    bp = p - b; d3, d4 = np.sum(ab * bp, -1), np.sum(ac * bp, -1)
    cp = p - c; d5, d6 = np.sum(ab * cp, -1), np.sum(ac * cp, -1)
    va = d3 * d6 - d5 * d4; vb = d5 * d2 - d1 * d6; vc = d1 * d4 - d3 * d2
    den = np.where(np.abs(va + vb + vc) < 1e-30, 1e-30, va + vb + vc)
    v, w = vb / den, vc / den
    q = a + ab * v[..., None] + ac * w[..., None]
    with np.errstate(divide='ignore', invalid='ignore'):
        t_ab = np.clip(d1 / (d1 - d3), 0, 1); t_ac = np.clip(d2 / (d2 - d6), 0, 1)
        t_bc = np.clip((d4 - d3) / ((d4 - d3) + (d5 - d6)), 0, 1)
    cand = [a, b, c, a + ab * np.nan_to_num(t_ab)[..., None], a + ac * np.nan_to_num(t_ac)[..., None],
            b + (c - b) * np.nan_to_num(t_bc)[..., None]]
    inside = (va >= 0) & (vb >= 0) & (vc >= 0)
    dist = np.min([np.linalg.norm(p - x, axis=-1) for x in cand], axis=0)
    return np.where(inside, np.linalg.norm(p - q, axis=-1), dist)


def load_complete_chair(measured, cache=None):
    """Every triangle (with material and outward face normal) of the actual chair source, placed by root's MEASURED
    native transform (translation, uniform scale, identity rotation; UE = translation + 100 * scale * (x, z, y)). Root's
    measured native chair_fabric shell (a reduced LOD0 mesh of 1121 vertices) must lie on the source's chair_fabric
    surface: exact point-to-triangle distance <= CHAIR_MATCH_TOL_CM for every measured vertex, which proves the source and
    its placement are the native chair."""
    src = Path(CHAIR_SOURCE)
    sha = hashlib.sha256(src.read_bytes()).hexdigest()
    if sha != CHAIR_SOURCE_SHA256:
        raise ValueError('chair source bytes differ from the reviewed owner chair')
    g = G.Gltf(E.decoded(src, Path(cache or ROOT / 'out/seat-fit-cache')))
    node = g.doc['nodes'][0]
    if node.get('rotation') not in (None, [0, 0, 0, 1]) or len(g.doc['nodes']) != 1:
        raise ValueError('unexpected chair node layout')
    sc = float(measured['scale'][0])
    if not np.allclose(node['scale'], [sc] * 3, atol=1e-6) or not np.allclose(measured['scale'], [sc] * 3):
        raise ValueError('chair source scale differs from the measured native scale')
    t = np.asarray(measured['translation_cm'], float)
    tris, fn, mat = [], [], []
    for prim in g.doc['meshes'][node['mesh']]['primitives']:
        v = t + 100. * sc * E.accessor(g, prim['attributes']['POSITION'])[:, [0, 2, 1]]
        vn = E.accessor(g, prim['attributes']['NORMAL'])[:, [0, 2, 1]]
        idx = E.accessor(g, prim['indices']).astype(int).reshape(-1, 3)
        tr = v[idx]
        n = np.cross(tr[:, 1] - tr[:, 0], tr[:, 2] - tr[:, 0])
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        n *= np.where(np.sum(n * vn[idx].sum(1), axis=1) < 0, -1., 1.)[:, None]     # outward: agree with vertex normals
        tris.append(tr), fn.append(n)
        mat += [g.doc['materials'][prim['material']]['name']] * len(idx)
    tris, fn, mat = np.concatenate(tris), np.concatenate(fn), np.array(mat)
    from scipy.spatial import cKDTree
    fab = tris[mat == 'chair_fabric']
    V = measured['shell_vertices_cm']
    _, ii = cKDTree(fab.mean(1)).query(V, k=24)
    err = np.min([point_triangle_distance(V, *np.moveaxis(fab[ii[:, k]], 1, 0)) for k in range(24)], axis=0)
    if err.max() > CHAIR_MATCH_TOL_CM:
        raise ValueError(f'chair source does not reproduce the measured native shell (max {err.max():.4f} cm)')
    edge = np.linalg.norm(tris[:, 1] - tris[:, 0], axis=1)
    return {'source': rel(src), 'source_sha256': sha, 'placement': 'measured native transform (root chair report)',
            'triangles_cm': tris, 'face_normals': fn, 'material': mat, 'vertices_cm': tris.reshape(-1, 3),
            'triangles_by_material': {m: int((mat == m).sum()) for m in np.unique(mat)},
            'measured_shell_on_source_surface_cm': {'median': float(np.median(err)), 'max': float(err.max()),
                                                    'tolerance': CHAIR_MATCH_TOL_CM, 'measured_vertices': int(len(V))},
            'edge_length_median_cm': float(np.median(edge)),
            'bounds_cm': [tris.reshape(-1, 3).min(0).tolist(), tris.reshape(-1, 3).max(0).tolist()],
            'armrest_top_cm': float(tris[mat == 'chair_armpad'][..., 2].max()) if (mat == 'chair_armpad').any() else None,
            'lowest_cm': float(tris[..., 2].min())}


class ChairCollider:
    """Signed distance of points to the complete chair at a roll offset, signed by the nearest triangle's outward normal
    (negative = inside). Broad phase: a KD-tree over surface samples of every chair triangle at <= SAMPLE_CM spacing
    (each sample knows its triangle); a point with no sample within REACH_CM + SAMPLE_CM is farther than REACH_CM from
    the chair and reports REACH_CM. Narrow phase: exact point-to-triangle distance to the triangles of the K_SAMPLES
    nearest samples. Upholstery may be pressed in down to the seat band's lower edge (SEAT_BAND_CM[0], the cushion
    compression the seat gates allow); every other part (plastic frame and arms, arm pads, back mesh, base, castors, gas
    lift) allows no penetration."""
    K_SAMPLES, REACH_CM, SAMPLE_CM = 6, 3., 1.

    def __init__(self, complete):
        from scipy.spatial import cKDTree
        self.c = complete
        tri = complete['triangles_cm']
        self.cen = tri.mean(1)
        self.allow = np.where(np.isin(complete['material'], UPHOLSTERY), seat_contact.SEAT_BAND_CM[0], 0.)
        L = np.max(np.linalg.norm(tri[:, [1, 2, 0]] - tri, axis=-1), axis=1)
        pts, ids = [], []
        for k in np.unique(np.maximum(1, np.ceil(L / self.SAMPLE_CM)).astype(int)):
            sel = np.nonzero(np.maximum(1, np.ceil(L / self.SAMPLE_CM)).astype(int) == k)[0]
            u, v = np.meshgrid(np.arange(k + 1) / k, np.arange(k + 1) / k)
            m = (u + v) <= 1 + 1e-9
            u, v = u[m], v[m]
            t = tri[sel]
            P_ = t[:, None, 0] + u[None, :, None] * (t[:, None, 1] - t[:, None, 0]) + v[None, :, None] * (t[:, None, 2] - t[:, None, 0])
            pts.append(P_.reshape(-1, 3))
            ids.append(np.repeat(sel, len(u)))
        self.samples, self.sample_tri = np.concatenate(pts), np.concatenate(ids)
        self.tree = cKDTree(self.samples)

    def margin(self, points, offset):
        """(signed distance - allowed depth) per point (REACH_CM where no triangle is near), and the nearest material."""
        shape = np.shape(points)[:-1]
        p = np.asarray(points, float).reshape(-1, 3) - np.asarray(offset, float)
        m = np.full(len(p), self.REACH_CM)
        mat = np.full(len(p), '', dtype=object)
        lo, hi = self.samples.min(0) - self.REACH_CM - self.SAMPLE_CM, self.samples.max(0) + self.REACH_CM + self.SAMPLE_CM
        box = np.nonzero(np.all((p >= lo) & (p <= hi), axis=1))[0]          # broad phase: the chair's AABB
        d0 = np.full(len(p), np.inf)
        if len(box):
            d0[box], _ = self.tree.query(p[box], distance_upper_bound=self.REACH_CM + self.SAMPLE_CM, workers=-1)
        near = np.nonzero(np.isfinite(d0))[0]
        if len(near):
            _, ii = self.tree.query(p[near], k=self.K_SAMPLES, workers=-1)
            cand = self.sample_tri[ii]
            T_ = self.c['triangles_cm']
            best, arg = np.full(len(near), np.inf), np.zeros(len(near), int)
            for k in range(self.K_SAMPLES):
                tri = T_[cand[:, k]]
                d = point_triangle_distance(p[near], tri[:, 0], tri[:, 1], tri[:, 2])
                better = d < best
                best[better], arg[better] = d[better], cand[better, k]
            sgn = np.sign(np.sum((p[near] - self.cen[arg]) * self.c['face_normals'][arg], axis=1))
            sd = best * np.where(sgn == 0, 1., sgn)
            m[near] = np.minimum(sd - self.allow[arg], self.REACH_CM)
            mat[near] = self.c['material'][arg]
        return m.reshape(shape), mat.reshape(shape)


def chair_path_clearance(complete, roll, boxes, nodes, samples=101):
    """The COMPLETE chair (every source vertex) vs every real-desk part box and the floor along the whole roll path
    (pull-in s 0 -> 1; push-back retraces the same positions)."""
    s = np.linspace(0., 1., samples)
    rows = []
    V, M = complete['vertices_cm'], complete['material']
    for si in s:
        pts = V + roll.offset(si)
        d, w = boxes_min_distance(pts, boxes, reach_cm=20.)
        k = int(np.argmin(d))
        rows.append({'s': round(float(si), 4), 'desk_min_cm': round(float(d[k]), 4), 'nearest_desk_node': nodes[w[k]] if w[k] >= 0 else None,
                     'chair_part': str(M[k]), 'floor_gap_cm': round(float(pts[:, 2].min() - FLOOR_CM), 4)})
    worst = min(rows, key=lambda r: r['desk_min_cm'])
    floor = [r['floor_gap_cm'] for r in rows]
    return {'samples': samples, 'worst_desk': worst, 'desk_clear_all_samples': all(r['desk_min_cm'] > 0 for r in rows),
            'floor_gap_cm': [min(floor), max(floor)], 'floor_gap_constant_along_roll': bool(max(floor) - min(floor) < 1e-9),
            'floor_no_penetration': bool(min(floor) >= 0.), 'rows': rows[::10] + ([rows[-1]] if (samples - 1) % 10 else []),
            'method': 'every vertex of the complete chair source (shell, arms, arm pads, back mesh, base, castors, gas '
                      'lift) at the measured transform + the roll offset, signed distance to each real desk part AABB '
                      '(conservative, 20 cm reach) and height above the floor support plane'}


def reversibility(roll, times_in, times_out):
    """Pull-in and push-back trace the same positions; push-back ends exactly on the measured start."""
    a = roll.transform(roll.pull_in_s(times_in))
    b = roll.transform(roll.push_back_s(times_out))
    dense = np.linspace(0, 1, 1001)
    fwd, back = roll.transform(dense), roll.transform(1 - dense)[::-1]
    return {'pull_in_start_equals_measured': bool(np.allclose(a[0], roll.start, atol=1e-9)),
            'pull_in_end_cm': [round(float(v), 4) for v in a[-1]],
            'push_back_start_equals_pull_in_end': bool(np.allclose(b[0], a[-1], atol=1e-9)),
            'push_back_end_equals_measured': bool(np.allclose(b[-1], roll.start, atol=1e-9)),
            'same_path_max_deviation_cm': float(np.abs(fwd - back).max()),
            'final_equals_initial_exact': bool(np.array_equal(b[-1], roll.start)),
            'reversible': bool(np.array_equal(a[0], roll.start) and np.array_equal(b[-1], roll.start) and np.allclose(b[0], a[-1], atol=1e-12)
                               and np.abs(fwd - back).max() < 1e-9)}


# ---------------------------------------------------------------- arm-local blending (transitions and seams)
def arm_locals(sk, W):
    """(F, J, 4, 4) locals (joint relative to parent; Hips relative to identity)."""
    return P.joint_locals(sk, W, np.eye(4))


def blend_arm_locals(sk, W_a, W_b, w, sides=SIDES):
    """Pose = W_a with the six arm bones' LOCAL rotations slerped toward W_b by w (F,) (0 -> W_a, 1 -> W_b); bone
    translations unchanged; every descendant (fingers) keeps its local; worlds rebuilt from the shoulders down."""
    La, Lb = arm_locals(sk, W_a), arm_locals(sk, W_b)
    W = np.array(W_a, copy=True)
    for s in sides:
        bones = [sk.j(f'{SIDES[s]}Shoulder')] + [sk.j(n) for n in ARM_BONES[s]]
        L = La.copy()
        for k in bones:
            qa, qb = P.quat_from_matrix(unit_rot(La[:, k, :3, :3])), P.quat_from_matrix(unit_rot(Lb[:, k, :3, :3]))
            q = P.slerp_arrays(qa[:, None], qb[:, None], np.asarray(w, float))[:, 0]
            R = quat_to_matrix(q)
            sc = np.linalg.norm(La[:, k, :3, 0], axis=-1)[:, None, None]
            L[:, k, :3, :3] = R * sc
        top = bones[0]
        order = sk.subtree(top)
        order.sort(key=lambda k: depth(sk, k))
        for k in order:
            W[:, k] = W[:, sk.parents[k]] @ L[:, k]
    return W


def depth(sk, k):
    d = 0
    while sk.parents[k] >= 0:
        k = sk.parents[k]
        d += 1
    return d


def quat_to_matrix(q):
    x, y, z, w = np.moveaxis(np.asarray(q, float), -1, 0)
    return np.stack([np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], -1),
                     np.stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], -1),
                     np.stack([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], -1)], -2)


# ---------------------------------------------------------------- measurement (written, read-back clips)
FIT_DIR = ROOT / 'docs/proposed/seat-pose-fit'
OUT_DIR = ROOT / 'docs/proposed/seated-typing-ik'
CLIPS = {  # role: (fit GLB in docs/proposed/seat-pose-fit, raw capture)
    'DeskTyping_seated': ('SUB01_DeskTyping_seated.glb', 'web/room/mh_mx/room_mx_typing.glb'),
    'SitToType_seated': ('SUB01_SitToType_seated.glb', 'web/room/mh_mx/room_mx_sit_to_type.glb'),
    'TypeToSit_seated': ('SUB01_TypeToSit_seated.glb', 'web/room/mh_mx/room_mx_type_to_sit.glb'),
    'SeatedIdle': ('SUB01_SeatedIdle.glb', 'web/room/mh_mx/room_seated_idle.glb'),
    'SitDown_seated': ('SUB01_SitDown_seated.glb', 'web/room/mh_mx/room_mx_stand_to_sit.glb'),
    'GetUp_seated': ('SUB01_GetUp_seated.glb', 'web/room/mh_mx/room_mx_sit_to_stand.glb')}
ROLL_SCAN_DY_CM = (0., -2.5, -5., -7.5)   # extra pull-in beyond the seat fit's chair offset, scanned on probe frames
SEAM_BLEND_S = .25              # arm-local seam blend into DeskTyping's first / out of its last frame
BODY_SKIN_STRIDE = 6            # whole-body skin sampling for desk clearance (P.desk_clearance's own stride)


def _r(v, d=4):
    v = float(v)
    return None if not math.isfinite(v) else (0.0 if round(v, d) == 0 else round(v, d))


def rng(a, d=4):
    a = np.asarray(a, float)
    a = a[np.isfinite(a)]
    return [_r(a.min(), d), _r(a.max(), d)] if a.size else None


def worst_frame(values, times, lowest=True):
    v = np.asarray(values, float)
    if not np.isfinite(v).any():
        return None
    i = int(np.nanargmin(np.where(np.isfinite(v), v, np.inf))) if lowest else int(np.nanargmax(np.where(np.isfinite(v), v, -np.inf)))
    return {'value': _r(v[i]), 'frame': i, 't': _r(times[i], 4)}


_UE_TO_GLTF = None


def gltf_shift(shift_ue):
    """UE cm translations (..., 3) as glTF metre translations under the audited body transform (vectorised
    fit_seat_pelvis_pitch.ue_delta_to_gltf: the map is linear)."""
    global _UE_TO_GLTF
    if _UE_TO_GLTF is None:
        _UE_TO_GLTF = np.stack([P.ue_delta_to_gltf(e) for e in np.eye(3)])       # row i: glTF for a unit UE axis i
    return np.asarray(shift_ue, float) @ _UE_TO_GLTF


_LBS_CACHE = {}


def lbs(skin, ibm, W):
    """(F, V, 3) glTF metres: linear blend skinning, identical in result to fit_seat_pelvis_pitch.skin_points but as one
    dense operator per skin (the export_seat_fit_source.Source.skin formulation), built once and cached."""
    pos, jts, wts = skin
    key = tuple((a.__array_interface__['data'][0], a.shape, a.strides) for a in (pos, jts, wts))
    if key not in _LBS_CACHE:
        if len(_LBS_CACHE) >= 16:                                  # bounded memory (views of one skin share a key)
            _LBS_CACHE.pop(next(iter(_LBS_CACHE)))
        J, V = len(ibm), len(pos)
        hom = np.hstack([pos, np.ones((V, 1))])
        S = np.zeros((J * 4, V))
        cols = np.arange(V)
        for k in range(jts.shape[1]):
            for c in range(4):
                np.add.at(S, (jts[:, k] * 4 + c, cols), wts[:, k] * hom[:, c])
        _LBS_CACHE[key] = (S, pos, jts)
    S = _LBS_CACHE[key][0]
    M = (np.asarray(W) @ ibm[None])[..., :3, :]                     # (F, J, 3, 4)
    lin = M.transpose(0, 2, 1, 3).reshape(len(W), 3, -1)            # (F, 3, J*4)
    return (lin @ S).transpose(0, 2, 1)


def body_parts(names):
    group = {}
    for k, n in enumerate(names):
        if 'Arm' in n or 'Hand' in n or 'Shoulder' in n:
            group[k] = 'arms'
        elif 'Leg' in n or 'Foot' in n or 'Toe' in n:
            group[k] = 'legs'
        else:
            group[k] = 'torso_head'
    return group


def keycaps_from_world_json(path):
    """Keyboard IK targets from a keyboard-keycaps-world.json (tools/extract_keyboard_keycaps.py producer): the keycap
    top triangles (topTrianglesUECm) and the key field bounds, in the same dict shape as keycaps_from_glb()."""
    path = Path(path)
    d = json.loads(path.read_text())
    tri = np.array([t for k in d['keycaps'] for t in k['topTrianglesUECm']], float)
    tops = [k['topCm'] for k in d['keycaps'] if k['topTrianglesUECm']]
    lo = np.array([min(k['minCm'][a] for k in d['keycaps']) for a in range(3)])
    hi = np.array([max(k['maxCm'][a] for k in d['keycaps']) for a in range(3)])
    return {'triangles': tri, 'key_min': lo, 'key_max': hi, 'top_cm': float(max(tops)), 'keycaps': len(tops),
            'top_spread_cm': float(max(tops) - min(tops)),
            'source': f'{rel(path)} (sha256 {hashlib.sha256(path.read_bytes()).hexdigest()})'}


class Context:
    """Everything shared by the clips: source, real desk, chair, keys, skins."""

    def __init__(self, source, geometry=GEOMETRY_JSON, cache=None, chair_translation=None, keycaps=None):
        self.base = E.Source.load(source)
        self.geometry = load_geometry(geometry)
        self.geometry_sha256 = hashlib.sha256(Path(geometry).read_bytes()).hexdigest()
        self.boxes, self.box_nodes = desk_boxes(self.geometry)
        self.chair = load_chair(translation_cm=chair_translation)
        self.tri = self.chair['cushion_triangles_cm']
        self.complete_chair = load_complete_chair(self.chair, cache)
        self.collider = ChairCollider(self.complete_chair)
        self.finger_joints = [k for k, n in enumerate(self.base.names) if any(f in n for f in FINGERS)]
        self.keys = keycaps_from_world_json(keycaps) if keycaps else T.keycaps_from_glb()
        self.mouse = mouse_geometry(cache)
        self.key_raster = KeyRaster(self.keys)
        self.mouse_raster = HeightRaster(self.mouse['shell_triangles_cm'])
        from fit_seat_rigid_placement import Surface
        self.mouse_surface = Surface(self.mouse['shell_triangles_cm'])
        self.arms = arm_skin(self.base.names, stride=1, cache=cache)
        self.body_skin = P.owner_skin(stride=BODY_SKIN_STRIDE, cache=cache)
        dom = self.body_skin[1][np.arange(len(self.body_skin[1])), self.body_skin[2].argmax(1)]
        g = body_parts(self.base.names)
        self.body_group = np.array([g[int(j)] for j in dom])
        self.sk = T.Skeleton(self.base)

    def clip(self, role, times=None):
        fit, raw = CLIPS[role]
        src_f, g_f = P.clip_source(self.base, Path(FIT_DIR) / fit, times)
        times = src_f.times
        src_r, _ = P.clip_source(self.base, ROOT / raw, times)
        return src_f, src_r, g_f, np.asarray(times, float)

    def ik(self, W_fit, W_raw, times, shift, contact=True, contact_shift=None):
        """The arm IK of one clip; horizontal finger targets and the on-key mask come from the seat fit clip itself (the
        existing contact pipeline's over-key frames and hand path). The fit's hand path is body-relative: at frame f it
        is carried by shift[f] - contact_shift (contact_shift: the body shift at the keyboard contact; default the
        clip's own constant shift, so on the keyboard the targets are the fit's world keycap positions)."""
        shift = np.asarray(shift, float)
        rel = shift - (shift[0] if contact_shift is None else np.asarray(contact_shift, float))
        Wr = np.array(W_fit, copy=True)
        Wr[..., :3, 3] += gltf_shift(rel)[:, None, :]
        tr = T.Trial(E.Source(dict(self.base.d, joint_world=Wr)), self.tri, self.keys, (0., 0.))
        ka = tr.key_audit(Wr)
        on = {s: ka[s]['over'] >= KEY_MIN_OVER_VERTICES for s in SIDES}
        target = {s: tr.skin_ue(f'{s}_fingers', Wr)[0].mean(axis=1)[:, :2] for s in SIDES}
        ik = ClipArmIK(self.base, W_fit, W_raw, times, self.keys, self.tri, self.arms, self.geometry,
                       body_shift_cm=shift, contact=contact, finger_xy_target=target, on_mask=on, roll=ROLL_OFFSET_CM)
        ik.mouse = self.mouse
        ik.mouse_surface = self.mouse_raster
        ik.raster = self.key_raster
        return ik

    def seat_fit(self, W_raw, times, chair_offset):
        d = dict(self.base.d)
        d['joint_world'], d['times'] = W_raw, np.asarray(times, float)
        return P.SeatFit(E.Source(d), self.tri, self.keys, tuple(chair_offset))


# origin/main tools/validate_unreal_seat_contact.py validate() (9792a35): per region and frame, at least
# MIN_PATCH_VERTICES facing skin over the surface, the deepest point >= the band's low edge, the MEDIAN gap <= the
# band's high edge and at least MIN_BAND_COVERAGE (0.5) of the over-surface patch inside the band. Applied as main
# applies it, to the seat patches and the soles. This branch's validator has no coverage constant: the value is main's.
MAIN_MIN_BAND_COVERAGE = .5
SEAT_BAND, SOLE_BAND = seat_contact.SEAT_BAND_CM, seat_contact.SOLE_BAND_CM
MAIN_SEAT_RULE = 'origin/main tools/validate_unreal_seat_contact.py validate() @ 9792a35 (median gap <= band high, coverage >= 0.5)'


def main_strong_seat_rule(fit, W, times, metrics=None):
    """Main's strong seat rule on every frame (see MAIN_SEAT_RULE), per region: pass, worst median, lowest coverage.
    metrics: (seat, soles) already measured on W (same rule, measured once)."""
    s, so = metrics if metrics is not None else (fit.trial.seat(W), fit.trial.soles(W))
    out = {}
    for name, m in list(s.items()) + list(so.items()):
        low, high = seat_contact.band(name)
        over = np.asarray(m['over'], float)
        cov = np.where(over > 0, m['band'] / np.maximum(over, 1), 0.)
        med = np.nan_to_num(np.asarray(m['median'], float), nan=np.inf)
        ok = (over >= seat_contact.MIN_PATCH_VERTICES) & (np.nan_to_num(m['lowest'], nan=-np.inf) >= low) & \
             (med <= high) & (cov >= MAIN_MIN_BAND_COVERAGE)
        out[name] = {'pass_all_frames': bool(ok.all()), 'failing_frames': int((~ok).sum()),
                     'worst_median_gap': worst_frame(med, times, lowest=False), 'lowest_coverage': worst_frame(cov, times),
                     'band_vertices': [int(np.min(m['band'])), int(np.max(m['band']))],
                     'over_surface_vertices': [int(over.min()), int(over.max())]}
    return {'rule': MAIN_SEAT_RULE, 'regions': out, 'pass': all(v['pass_all_frames'] for v in out.values())}


# Owner skin, measured in bind space (ARM_SKIN radial distance of ForeArm-dominant vertices from the elbow->wrist axis,
# 2..10 cm from the elbow): p90 about 10.7-11.3 cm (a bulky sleeve, the joint off-centre). An elbow over the slab must be
# at least this far above the top for its sleeve to clear it.
SLEEVE_RADIUS_NEAR_ELBOW_CM = 10.7
MEASURE_REACH_CM = 10.          # distances beyond this report as 10 (never a false small value)
FINGER_LOCAL_GATE_DEG = .1      # tools/validate_unreal_contact_profile.py: captured finger rotation change <= 0.1 deg


def finger_steps_deg_s(ctx, W):
    """Per finger joint: the capture's own largest frame-to-frame local rotation step, per second."""
    L = arm_locals(ctx.sk, W)
    return {k: P.rot_angle_deg(L[1:, k, :3, :3], L[:-1, k, :3, :3]) for k in ctx.finger_joints}


def finger_contract(ctx, W, W_raw, times, seams=()):
    """Finger gate on EVERY frame. Outside the seam windows: every finger local equals the clip's capture within
    FINGER_LOCAL_GATE_DEG. Inside a full-pose seam window (weight w toward a neighbour pose whose fingers are that
    neighbour's capture): every finger local equals slerp(capture, neighbour capture, w) within FINGER_LOCAL_GATE_DEG,
    and every per-frame finger step is at most the largest step either capture itself makes in the same time
    (max captured angular speed x dt) + FINGER_LOCAL_GATE_DEG. No frame is exempt."""
    F = len(times)
    Lo, Lr = arm_locals(ctx.sk, W), arm_locals(ctx.sk, W_raw)
    expected = Lr.copy()
    inwin = np.zeros(F, bool)
    speed = {k: 0. for k in ctx.finger_joints}
    t = np.asarray(times, float)
    dt = np.diff(t)
    for k, v in finger_steps_deg_s(ctx, W_raw).items():
        speed[k] = max(speed[k], float((v / dt).max()))
    for w, target, target_capture_times in seams:
        w = np.asarray(w, float)
        Lt = arm_locals(ctx.sk, target)
        mid = w > 0
        inwin |= mid
        for k in ctx.finger_joints:
            q = P.slerp_arrays(P.quat_from_matrix(unit_rot(expected[mid, k, :3, :3]))[:, None],
                               P.quat_from_matrix(unit_rot(Lt[mid, k, :3, :3]))[:, None], w[mid])[:, 0]
            expected[mid, k, :3, :3] = quat_to_matrix(q)
        cap = target_capture_times
        if cap is not None:
            for k, v in finger_steps_deg_s(ctx, cap[0]).items():
                speed[k] = max(speed[k], float((v / np.diff(cap[1])).max()))
    err = np.max([P.rot_angle_deg(unit_rot(Lo[:, k, :3, :3]), unit_rot(expected[:, k, :3, :3])) for k in ctx.finger_joints], axis=0)
    steps = np.max([P.rot_angle_deg(Lo[1:, k, :3, :3], Lo[:-1, k, :3, :3]) - (speed[k] * dt + FINGER_LOCAL_GATE_DEG)
                    for k in ctx.finger_joints], axis=0)
    out = {'rule': finger_contract.__doc__.split('No frame')[0].strip() + ' Overlapping windows compose in order.',
           'gate_deg': FINGER_LOCAL_GATE_DEG,
           'max_error_outside_windows_deg': _r(err[~inwin].max(), 6) if (~inwin).any() else None,
           'max_error_inside_windows_deg': _r(err[inwin].max(), 6) if inwin.any() else None,
           'worst_error': worst_frame(err, times, lowest=False), 'window_frames': int(inwin.sum()),
           'worst_step_excess_deg': worst_frame(steps, times[1:], lowest=False),
           'max_capture_speed_deg_s': _r(max(speed.values()), 3)}
    out['pass'] = bool(err.max() <= FINGER_LOCAL_GATE_DEG and (steps <= 0).all())
    return out


def finger_override(ctx, W, W_raw, seams):
    """Set every finger local to the declared seam blend of the captures: slerp(capture, neighbour capture, w), windows
    composed in order. Fingers are leaves of the hand, so only finger (and fingertip) positions change."""
    Lo, Lr = arm_locals(ctx.sk, W), arm_locals(ctx.sk, W_raw)
    exp = Lr[:, :, :3, :3].copy()
    for w, target, _ in seams:
        w = np.asarray(w, float)
        Lt = arm_locals(ctx.sk, target)
        mid = w > 0
        for k in ctx.finger_joints:
            q = P.slerp_arrays(P.quat_from_matrix(unit_rot(exp[mid, k]))[:, None], P.quat_from_matrix(unit_rot(Lt[mid, k, :3, :3]))[:, None], w[mid])[:, 0]
            exp[mid, k] = quat_to_matrix(q)
    out = np.array(W, copy=True)
    order = sorted(ctx.finger_joints, key=lambda k: depth(ctx.sk, k))
    for k in order:
        L = Lo[:, k].copy()
        L[:, :3, :3] = exp[:, k] * np.linalg.norm(Lo[:, k, :3, 0], axis=-1)[:, None, None]
        out[:, k] = out[:, ctx.sk.parents[k]] @ L
    return out


ARMS_ONLY = False           # --arms-only: only the arm chains may differ from the base clip (lower body / pelvis gated)
BASE_INVARIANCE_CM, BASE_INVARIANCE_DEG = 1e-3, 1e-3


def base_invariance(ctx, W, W_base, times):
    """Every joint outside the two arm chains (Arm, ForeArm, Hand and the fingers) vs the base clip: world position and
    rotation change; the pelvis, spine, shoulders, head and legs must be the base's (float32 storage only)."""
    arm = set()
    for s in SIDES:
        arm |= set(ctx.sk.subtree(ctx.sk.j(f'{SIDES[s]}Shoulder')))     # the girdle may move (arms-only + girdle)
    other = [k for k in range(len(ctx.sk.names)) if k not in arm]
    dp = np.linalg.norm(W[:, other][..., :3, 3] - W_base[:, other][..., :3, 3], axis=-1).max(1) * 100
    dr = np.max([P.rot_angle_deg(unit_rot(W[:, k, :3, :3]), unit_rot(W_base[:, k, :3, :3])) for k in other], axis=0)
    return {'joints_checked': len(other), 'max_position_cm': worst_frame(dp, times, lowest=False),
            'max_rotation_deg': worst_frame(dr, times, lowest=False),
            'pass': bool(dp.max() <= BASE_INVARIANCE_CM and dr.max() <= BASE_INVARIANCE_DEG)}


def measure(ctx, role, W, W_raw, times, shift, chair_offset_world, ik=None, key_seam=None, finger_frames=None,
            finger_seams=(), base=None):
    """Every gate and metric on the given (read-back) pose, every frame. Solver frame: body at the audited transform,
    chair at measured + ROLL_OFFSET_CM. World at frame f: the body moved by shift[f] (UE cm), the chair at the measured
    transform + chair_offset_world[f]. Seat/sole gates are chair-relative (chair and body roll rigidly together), so they
    are measured in the solver frame AND re-measured literally at the final rolled position."""
    F = len(times)
    out = {'frames': F}
    fit = ctx.seat_fit(W_raw, times, ROLL_OFFSET_CM)
    seat_m, sole_m = fit.trial.seat(W), fit.trial.soles(W)          # the patches, measured ONCE on every frame
    g = {'seat': {}, 'soles': {}}
    for grp, ms, band in (('seat', seat_m, SEAT_BAND), ('soles', sole_m, SOLE_BAND)):
        for n, m in ms.items():
            passed, fails = T.support_gate(m, band)
            g[grp][n] = {'pass_all_frames': bool(passed.all()), 'failing_frames': int((~passed).sum()),
                         'failures': {k: int(v.sum()) for k, v in fails.items() if v.any()},
                         'corrected': {'lowest_gap_cm': [_r(np.nanmin(m['lowest'])), _r(np.nanmax(m['lowest']))],
                                       'min_band_vertices': int(m['band'].min()), 'min_over_surface_vertices': int(m['over'].min())}}
    g['bone_length_max_error_cm'] = _r(max(float(np.abs(np.linalg.norm(W[:, k, :3, 3] - W[:, p_, :3, 3], axis=1)
                                                        - np.linalg.norm(W_raw[:, k, :3, 3] - W_raw[:, p_, :3, 3], axis=1)).max())
                                           for k, p_ in enumerate(ctx.sk.parents) if p_ >= 0) * 100, 7)
    out['seat_sole_gates_solver_frame'] = g
    # literal re-measure at the final rolled position (rigid roll of chair + body), on every 10th frame
    final = shift[-1] if key_seam is None or key_seam == len(times) - 1 else shift[0]
    sub = np.arange(0, F, 10)
    fit_r = ctx.seat_fit(P.place_body(W_raw[sub], final[:2]), np.asarray(times)[sub], np.asarray(ROLL_OFFSET_CM) + final[:2])
    g_r = P.gates(fit_r, P.place_body(W[sub], final[:2]), None, seated=np.ones(len(sub), bool), with_keys=False)
    out['seat_sole_gates_at_rolled_chair'] = {'chair_translation_cm': [_r(v) for v in np.asarray(ctx.chair['translation_cm']) + [*(np.asarray(ROLL_OFFSET_CM) + final[:2]), 0.]],
                                             'frames': 'every 10th frame (the rigid roll keeps the chair-relative geometry)',
                                             'seat': g_r['seat'], 'soles': g_r['soles']}
    seat_pass = all(v['pass_all_frames'] for v in g['seat'].values()) and all(v['pass_all_frames'] for v in g['soles'].values())
    seat_pass_r = all(v['pass_all_frames'] for v in g_r['seat'].values()) and all(v['pass_all_frames'] for v in g_r['soles'].values())
    c = {n: {'lowest': m['lowest'], 'band': m['band'], 'over': m['over']} for n, m in list(seat_m.items()) + list(sole_m.items())}
    pf = {'t': [_r(t, 4) for t in times],
          'chair_offset_cm': [[_r(v) for v in o[:2]] for o in chair_offset_world],
          'body_shift_from_solver_frame_cm': [[_r(v) for v in o[:2]] for o in shift]}
    for n in T.SEAT_PATCHES + T.SOLE_PATCHES:
        pf[f'{n}_lowest_gap_cm'] = [_r(v) for v in c[n]['lowest']]
        pf[f'{n}_band_vertices'] = [int(v) for v in c[n]['band']]
    # keys (world, per-frame body placement)
    Ws = np.array(W, copy=True)
    Ws[..., :3, 3] += gltf_shift(shift)[:, None, :]
    tr = T.Trial(fit.trial.src, ctx.tri, ctx.keys, (0., 0.))
    ka = tr.key_audit(Ws)
    top = ctx.keys['top_cm']
    keys_out = {}
    for s in SIDES:
        gap = np.where(ka[s]['over'] > 0, ka[s]['over_min'] - top, np.nan)
        pf[f'{s}_key_gap_cm'] = [_r(v) for v in gap]
        pf[f'{s}_over_key_vertices'] = [int(v) for v in ka[s]['over']]
        over = ka[s]['over'] > 0
        bad_gap = over & (gap > contact_profile.KEY_GAP_MAX_CM + 1e-9)
        bad_pen = over & (-gap > P.KEY_PENETRATION_MAX_CM)
        if key_seam is None:
            on = ik.on[s] if ik is not None else over
            ok = not (bad_gap & on).any() and not bad_pen.any() and bool(over[on].all() if on.any() else True)
            rule = 'gap <= 0.2 cm and penetration <= 0.1 cm on every frame the hand is on the keys; penetration on all'
        elif not over[key_seam] and ik is not None and not ik.on[s][key_seam]:
            # fit_seat_pelvis_pitch.gates() key_seam rule: the hand is not on the keys at the seam (it is on the mouse in
            # the capture and in the neighbour pose), so no contact is required there; no penetration on any frame
            ok = not bad_pen.any()
            rule = f'hand not on the keys at the seam frame {key_seam} (capture and neighbour): penetration <= 0.1 cm on every frame'
        else:
            ok = not bad_pen.any() and bool(over[key_seam]) and not bad_gap[key_seam]
            rule = f'contact at the seam frame {key_seam}; penetration <= 0.1 cm on every frame'
        keys_out[s] = {'pass': bool(ok), 'rule': rule, 'frames_over_keys': int(over.sum()),
                       'frames_on_keys_by_ik': int(ik.on[s].sum()) if ik is not None else None,
                       'gap_cm': rng(gap), 'worst_gap': worst_frame(gap, times, lowest=False),
                       'worst_penetration': worst_frame(gap, times, lowest=True),
                       'frames_gap_over_0_2cm': int(bad_gap.sum()), 'frames_penetration_over_0_1cm': int(bad_pen.sum())}
    out['keys'] = keys_out
    # segments and the mouse (right hand): main's mouse contact on MOUSE frames
    if ik is not None and hasattr(ik, 'mode'):
        seg = {}
        for s in SIDES:
            mo = ik.mode[s]
            pf[f'{s}_segment'] = ['key' if m == MODE_KEY else 'mouse' if m == MODE_MOUSE else 'transit' for m in mo]
            seg[s] = {'key_frames': int((mo == MODE_KEY).sum()), 'mouse_frames': int((mo == MODE_MOUSE).sum()),
                      'transit_frames': int((mo == MODE_TRANSIT).sum())}
        mm = ik.mode['right'] == MODE_MOUSE
        if mm.any():
            palm = ik.palm_ue(W[mm], 'right', np.nonzero(mm)[0])
            err = np.linalg.norm(palm - ctx.mouse['palm_target_cm'][None], axis=1)
            pos, jts, wts = ctx.arms['right']['skin']
            pts = E.to_ue(lbs((pos, jts, wts), ctx.base.ibm, W[mm])) + shift[mm][:, None, :]
            found, h = ctx.mouse_surface.height(pts[..., :2].reshape(-1, 2))
            gap = np.where(found, pts[..., 2].reshape(-1) - np.nan_to_num(h), np.inf).reshape(pts.shape[:2]).min(1)
            exy = np.linalg.norm(palm[:, :2] - ctx.mouse['palm_target_cm'][None, :2], axis=1)
            tm = np.asarray(times)[mm]
            seg['mouse'] = {'palm_target_cm': [_r(v, 3) for v in ctx.mouse['palm_target_cm']],
                            'palm_xy_error_cm': worst_frame(exy, tm, lowest=False),
                            'palm_error_cm': worst_frame(err, tm, lowest=False),
                            'hand_skin_over_shell_gap_cm': [worst_frame(gap, tm), worst_frame(gap, tm, lowest=False)],
                            'pass': bool(exy.max() <= contact_profile.KEY_GAP_MAX_CM and np.isfinite(gap).all()
                                         and gap.min() >= -P.KEY_PENETRATION_MAX_CM and gap.max() <= contact_profile.KEY_GAP_MAX_CM),
                            'rule': 'main\'s mouse contact (palm point 2.2 cm behind / 1.2 cm right of the shell top) with '
                                    'the key gates: palm XY within 0.2 cm, the lowest hand skin over the shell within '
                                    '-0.1..+0.2 cm of it (penetration <= 0.1, gap <= 0.2)'}
            pf['right_mouse_palm_error_cm'] = [_r(v, 3) if m else None for v, m in zip(np.interp(np.arange(F), np.nonzero(mm)[0], err), mm)]
        out['segments'] = seg
    # arms vs the real desk (every arm skin vertex), wrist angles, elbows
    arms_out = {}
    chair_box = np.array(ctx.chair['component_world_bounds_cm']['min']), np.array(ctx.chair['component_world_bounds_cm']['max'])
    for s in SIDES:
        pos, jts, wts = ctx.arms[s]['skin']
        part = ctx.arms[s]['part']
        rows = {p: np.full(F, np.inf) for p in ('upper_arm', 'forearm', 'hand', 'fingers')}
        slab = {p: np.full(F, np.inf) for p in rows}
        nearest = np.full(F, -1)
        chair_min = np.full(F, np.inf)
        for a in range(0, F, 60):
            sl = slice(a, a + 60)
            pts = E.to_ue(lbs((pos, jts, wts), ctx.base.ibm, W[sl])) + shift[sl][:, None, :]
            d, which = boxes_min_distance(pts, ctx.boxes, reach_cm=MEASURE_REACH_CM)
            v, _ = slab_clearance(pts, ctx.geometry['tabletop_slab'])
            for p in rows:
                m = part == p
                rows[p][sl] = d[:, m].min(1)
                slab[p][sl] = v[:, m].min(1)
            k = d.argmin(1)
            nearest[sl] = which[np.arange(len(k)), k]
            cp = pts - chair_offset_world[sl][:, None, :]        # chair frame: shell AABB at its frame position
            chair_min[sl] = box_signed_distance(cp, *chair_box).min(1)
        fl, dv, tw = wrist_angles(W, ctx.base.names, ctx.base.ibm, s)
        el = E.to_ue(W[:, ctx.sk.j(ARM_BONES[s][1]), :3, 3]) + shift
        sh = E.to_ue(W[:, ctx.sk.j(ARM_BONES[s][0]), :3, 3]) + shift
        ua = np.degrees(np.arccos(np.clip((sh[:, 2] - el[:, 2]) / np.linalg.norm(el - sh, axis=1), -1, 1)))
        allmin = np.min([rows[p] for p in rows], axis=0)
        for p in rows:
            pf[f'{s}_{p}_desk_clearance_cm'] = [_r(v, 3) for v in rows[p]]
        pf[f'{s}_wrist_flexion_deg'] = [_r(v, 2) for v in fl]
        pf[f'{s}_wrist_deviation_deg'] = [_r(v, 2) for v in dv]
        pf[f'{s}_elbow_ue_cm'] = [[_r(x, 2) for x in e] for e in el]
        cl_ = E.to_ue(W[:, ctx.sk.j(f'{SIDES[s]}Shoulder'), :3, 3]) + shift
        v = sh - cl_
        elev = np.degrees(np.arctan2(v[:, 2], np.linalg.norm(v[:, :2], axis=1)))
        elev0 = E.to_ue(W_raw[:, ctx.sk.j(ARM_BONES[s][0]), :3, 3]) - E.to_ue(W_raw[:, ctx.sk.j(f'{SIDES[s]}Shoulder'), :3, 3])
        elev0 = np.degrees(np.arctan2(elev0[:, 2], np.linalg.norm(elev0[:, :2], axis=1)))
        pf[f'{s}_upper_arm_from_vertical_deg'] = [_r(x, 2) for x in ua]
        # geometric floor: the elbow lies within the forearm length of the wrist, so its horizontal offset from the
        # shoulder is at least (shoulder-wrist horizontal distance - forearm); the upper arm can be no closer to
        # vertical than asin(that / upper arm)
        wr_ = E.to_ue(W[:, ctx.sk.j(ARM_BONES[s][2]), :3, 3]) + shift
        l1 = np.linalg.norm(el - sh, axis=1)
        l2 = np.linalg.norm(wr_ - el, axis=1)
        dh = np.linalg.norm((wr_ - sh)[:, :2], axis=1)
        floor = np.degrees(np.arcsin(np.clip(np.maximum(dh - l2, 0.) / l1, 0, 1)))
        pf[f'{s}_upper_arm_geometric_floor_deg'] = [_r(x, 2) for x in floor]
        pf[f'{s}_shoulder_ue_cm'] = [[_r(x, 2) for x in e] for e in sh]
        pf[f'{s}_shoulder_elevation_deg'] = [_r(x, 2) for x in elev]
        top = ctx.geometry['tabletop_slab']['top_cm']
        ergo_out = (el[:, 2] > top + ERGO_ELBOW_ABOVE_DESK_CM[1]) | (el[:, 2] < top + ERGO_ELBOW_ABOVE_DESK_CM[0]) | (ua > ERGO_UPPER_ARM_MAX_DEG)
        if ik is not None and hasattr(ik, 'phi'):
            pf[f'{s}_elbow_swivel_deg'] = [_r(math.degrees(v), 2) for v in ik.phi[s]]
            pf[f'{s}_hand_lift_cm'] = [_r(v, 3) for v in ik.lift[s]]
        soft_out = (fl < WRIST_SOFT_FLEX_DEG[0] - .5) | (fl > WRIST_SOFT_FLEX_DEG[1] + .5) | \
                   (dv < WRIST_SOFT_DEV_DEG[0] - .5) | (dv > WRIST_SOFT_DEV_DEG[1] + .5)
        arms_out[s] = {
            'desk_clearance_pass': bool((allmin > 0).all()),
            'min_desk_clearance_cm': {p: worst_frame(rows[p], times) for p in rows},
            'min_vertical_over_tabletop_cm': {p: worst_frame(slab[p], times) for p in rows},
            'nearest_desk_nodes': sorted({ctx.box_nodes[i] for i in np.unique(nearest) if i >= 0}),
            'frames_with_arm_skin_inside_desk': int((allmin <= 0).sum()),
            'elbow_and_arm_vs_chair_shell_aabb_cm': worst_frame(chair_min, times),
            'chair_has_armrests': False,
            'wrist_flexion_deg': rng(fl, 2), 'wrist_deviation_deg': rng(dv, 2), 'wrist_twist_deg': rng(tw, 2),
            'wrist_frames_outside_soft_zone': int(soft_out.sum()),
            'upper_arm_from_vertical_deg': rng(ua, 2), 'elbow_height_cm': rng(el[:, 2], 2),
            'shoulder_elevation_deg': rng(elev, 2), 'shoulder_elevation_capture_deg': rng(elev0, 2),
            'reach_geometry': {'shoulder_to_wrist_horizontal_cm': rng(dh, 2), 'upper_arm_cm': _r(l1.mean(), 3),
                               'forearm_cm': _r(l2.mean(), 3), 'upper_arm_floor_deg': rng(floor, 2),
                               'frames_floor_above_soft_target': int((floor > ERGO_UPPER_ARM_MAX_DEG).sum()),
                               'sleeve_radius_near_elbow_cm': SLEEVE_RADIUS_NEAR_ELBOW_CM,
                               'elbow_height_needed_over_slab_cm': _r(ctx.geometry['tabletop_slab']['top_cm'] + SLEEVE_RADIUS_NEAR_ELBOW_CM, 2)},
            'ergonomic_soft_targets': {'elbow_above_desk_cm': list(ERGO_ELBOW_ABOVE_DESK_CM), 'upper_arm_max_deg': ERGO_UPPER_ARM_MAX_DEG,
                                       'frames_outside': int(ergo_out.sum()), 'worst_elbow_height': worst_frame(el[:, 2], times, lowest=False),
                                       'worst_upper_arm': worst_frame(ua, times, lowest=False), 'gate': False},
            'ik_ergonomics': getattr(ik, 'ergonomics', {}).get(s) if ik is not None else None}
    out['arms'] = arms_out
    # whole body vs the real desk (knees / thighs / torso)
    pos, jts, wts = ctx.body_skin
    body_min = {k: np.full(F, np.inf) for k in ('legs', 'torso_head', 'arms')}
    for a in range(0, F, 40):
        sl = slice(a, a + 40)
        pts = E.to_ue(lbs((pos, jts, wts), ctx.base.ibm, W[sl])) + shift[sl][:, None, :]
        d, _ = boxes_min_distance(pts, ctx.boxes, reach_cm=MEASURE_REACH_CM)
        for k in body_min:
            m = ctx.body_group == k
            body_min[k][sl] = d[:, m].min(1)
    for k in body_min:
        pf[f'body_{k}_desk_clearance_cm'] = [_r(v, 3) for v in body_min[k]]
    out['body_vs_desk'] = {k: worst_frame(v, times) for k, v in body_min.items()}
    out['body_vs_desk']['legs_and_torso_clear'] = bool((body_min['legs'] > 0).all() and (body_min['torso_head'] > 0).all())
    out['body_vs_desk']['sampling'] = f'every {BODY_SKIN_STRIDE}th owner skin vertex'
    out['seat_main_strong_rule'] = main_strong_seat_rule(fit, W, times, (seat_m, sole_m))
    out['seat_pass_branch_rule'] = bool(seat_pass)
    seat_pass = bool(seat_pass and out['seat_main_strong_rule']['pass'])
    out['seat_pass'] = bool(seat_pass)
    out['seat_pass_at_rolled_chair'] = bool(seat_pass_r)
    out['fingers'] = finger_contract(ctx, W, W_raw if base is None else base, times, finger_seams)
    out['fingers']['reference'] = 'raw capture' if base is None else 'the seated base clip'
    out['base_invariance'] = base_invariance(ctx, W, base, times) if base is not None else None
    out['finger_local_max_change_deg'] = out['fingers']['worst_error']['value']
    # the COMPLETE chair at this frame's roll offset: vs the real desk, the floor, and the body
    offs, inv = np.unique(np.round(np.asarray(chair_offset_world, float), 9), axis=0, return_inverse=True)
    ch_desk, ch_floor = np.empty(len(offs)), np.empty(len(offs))
    V = ctx.complete_chair['vertices_cm']
    for i, o in enumerate(offs):
        ch_desk[i] = boxes_min_distance(V + o, ctx.boxes, reach_cm=20.)[0].min()
        ch_floor[i] = (V[:, 2] + o[2]).min() - FLOOR_CM
    ch_desk, ch_floor = ch_desk[inv.ravel()], ch_floor[inv.ravel()]
    body_chair = np.full(F, np.inf)
    body_part = np.full(F, '', dtype=object)
    for f in range(F):
        pts = E.to_ue(lbs((pos, jts, wts), ctx.base.ibm, W[f:f + 1]))[0] + shift[f]
        m, mat = ctx.collider.margin(pts, chair_offset_world[f])
        k = int(np.argmin(m))
        body_chair[f], body_part[f] = m[k], f'{ctx.body_group[k]} vs {mat[k]}'
    pf['chair_vs_desk_cm'] = [_r(v, 3) for v in ch_desk]
    pf['chair_floor_gap_cm'] = [_r(v, 4) for v in ch_floor]
    pf['body_vs_chair_margin_cm'] = [_r(v, 3) for v in body_chair]
    out['chair'] = {'chair_vs_desk': worst_frame(ch_desk, times), 'chair_vs_desk_pass': bool((ch_desk > 0).all()),
                    'floor_gap': worst_frame(ch_floor, times), 'floor_pass': bool((ch_floor >= 0).all()),
                    'body_vs_chair_margin': dict(worst_frame(body_chair, times) or {}, contact=str(body_part[int(np.argmin(body_chair))])),
                    'body_vs_chair_pass': bool((body_chair > 0).all()),
                    'rule': 'body skin (every %dth vertex) signed distance to the complete chair minus the allowed depth '
                            '(upholstery: the seat band lower edge %.1f cm; every other part 0) > 0; complete chair vs the '
                            'real desk part boxes > 0; lowest chair point >= the %.1f cm floor' % (
                                BODY_SKIN_STRIDE, seat_contact.SEAT_BAND_CM[0], FLOOR_CM)}
    out['all_gates_pass'] = bool(seat_pass and seat_pass_r and all(v['pass'] for v in keys_out.values())
                                 and all(v['desk_clearance_pass'] for v in arms_out.values())
                                 and out['body_vs_desk']['legs_and_torso_clear']
                                 and g['bone_length_max_error_cm'] <= .01 and out['fingers']['pass']
                                 and out['chair']['chair_vs_desk_pass'] and out['chair']['floor_pass']
                                 and out['chair']['body_vs_chair_pass']
                                 and (out['base_invariance'] is None or out['base_invariance']['pass'])
                                 and out.get('segments', {}).get('mouse', {}).get('pass', True))
    out['per_frame'] = pf
    return out


# ---------------------------------------------------------------- solve: roll scan, DeskTyping, transitions
AUDIT_KEYS = (180, 480)          # DeskTyping 3..8 s at 60 Hz: the native audit window (301 keys of the 60 Hz clip)
PROBE_STRIDE = 25


def roll_scan(ctx, src_f, src_r, times, dys=ROLL_SCAN_DY_CM):
    """Extra pull-in beyond the seat fit's chair offset, scanned on DeskTyping probe frames (every PROBE_STRIDE-th key
    of the 3..8 s audit window). Rule: every probe frame clear of the desk with key contact; then the smallest largest
    elbow swivel; then the smallest hand lift; then the smallest extra pull-in."""
    probe = np.arange(AUDIT_KEYS[0], AUDIT_KEYS[1] + 1, PROBE_STRIDE)
    Wf, Wr, t = src_f.joint_world[probe], src_r.joint_world[probe], times[probe]
    rows = []
    for dy in dys:
        shift = np.tile([0., dy, 0.], (len(probe), 1))
        ik = ctx.ik(Wf, Wr, t, shift)
        W = ik.solve()
        row = {'extra_pull_in_dy_cm': dy, 'sides': {}}
        ok = True
        for s in SIDES:
            cl = ik.clearance(W, s, 1)[0]
            a = ik.key_audit(W)[s]
            gap = np.where(ik.on[s], a['over_min'] - ctx.keys['top_cm'], 0.)
            contact = bool(np.all(np.isfinite(gap)) and np.all(np.abs(gap - KEY_TOP_TARGET_CM) < .05))
            fl, dv, _ = wrist_angles(W, ctx.base.names, ctx.base.ibm, s)
            row['sides'][s] = {'min_clearance_cm': _r(cl.min(), 3), 'max_swivel_deg': _r(math.degrees(ik.phi[s].max()), 1),
                               'max_lift_cm': _r(ik.lift[s].max(), 2), 'on_key_frames': int(ik.on[s].sum()),
                               'contact': contact, 'wrist_flexion_deg': rng(fl, 1), 'wrist_deviation_deg': rng(dv, 1)}
            ok &= bool(cl.min() > 0) and contact
        row['all_clear_with_contact'] = bool(ok)
        row['max_swivel_deg'] = max(v['max_swivel_deg'] for v in row['sides'].values())
        row['max_lift_cm'] = max(v['max_lift_cm'] for v in row['sides'].values())
        rows.append(row)
    pick = min(rows, key=lambda r: (not r['all_clear_with_contact'], r['max_swivel_deg'], r['max_lift_cm'], abs(r['extra_pull_in_dy_cm'])))
    return pick, {'probe_keys': [int(v) for v in probe], 'rule': roll_scan.__doc__.split('Rule: ')[1].replace('\n    ', ' '),
                  'rows': rows, 'chosen_extra_pull_in_dy_cm': pick['extra_pull_in_dy_cm']}


CHUNK_FRAMES, CHUNK_OVERLAP = 100, 12
STATE_KEYS = ('delta', 'phi', 'lift', 'hand_xy', 'girdle', 'gain')


def solve_chunked(ctx, W_fit, W_raw, times, shift, state_dir, deadline=None, chunk=CHUNK_FRAMES, ov=CHUNK_OVERLAP,
                  ergo_budget_s=None):
    """Per-frame bounded solve: the clip is solved in chunks of `chunk` frames, each with `ov` frames of context on both
    sides (its envelopes and blends see the neighbours), and only its core frames are kept. Every finished chunk is a
    checkpoint (<state_dir>/chunk-AAAA-BBBB.npz); a run that reaches `deadline` stops between chunks and a later run
    resumes from the checkpoints. Returns (ik with the stitched per-frame state, None) or (None, progress)."""
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    F = len(times)
    done, info = [], []
    for a in range(0, F, chunk):
        b = min(F, a + chunk)
        f = state_dir / f'chunk-{a:04d}-{b:04d}.npz'
        if not f.exists():
            if deadline is not None and time.time() > deadline:
                return None, {'chunks_done': len(done), 'chunks_total': int(math.ceil(F / chunk)), 'stopped_before_chunk': [a, b]}
            lo, hi = max(0, a - ov), min(F, b + ov)
            ikc = ctx.ik(W_fit[lo:hi], W_raw[lo:hi], times[lo:hi], shift[lo:hi])
            if ergo_budget_s is not None:
                ikc.deadline = time.time() + ergo_budget_s
            ikc.solve()
            core = slice(a - lo, b - lo)
            np.savez_compressed(f, **{f'{k}_{s}': np.asarray(getattr(ikc, k)[s])[core] for k in STATE_KEYS for s in SIDES},
                                ergonomics=json.dumps(ikc.ergonomics), history=json.dumps(ikc.history), lo=lo, hi=hi)
        done.append(f)
    ik = ctx.ik(W_fit, W_raw, times, shift)
    ik.prepare()
    for k in STATE_KEYS:
        setattr(ik, k, {s: np.concatenate([np.load(f)[f'{k}_{s}'] for f in done]) for s in SIDES})
    ik.ergonomics = {s: [json.loads(str(np.load(f)['ergonomics'])).get(s) for f in done] for s in SIDES}
    ik.history = [json.loads(str(np.load(f)['history'])) for f in done]
    ik.chunks = [f.name for f in done]
    return ik, None


def readback(ctx, path, times):
    t = np.asarray(times, float)
    W, parents = E.joint_worlds(G.Gltf(path), ctx.base.names, list(map(float, t - t[0])))
    if not np.array_equal(parents, ctx.base.parents):
        raise ValueError('written clip skeleton differs from the owner')
    return W


def write(ctx, g_fit, W, times, out_dir, asset, labels):
    path = Path(out_dir) / f'{asset}.glb'
    sha, _ = P.write_clip(g_fit, ctx.sk, W, list(map(float, times)), path, asset, labels,
                          {'sub01_report': f'{asset}.report.json'})
    return path, sha


def key_penetration(ik, W, frames=None):
    """Per frame: True where any over-key distal finger vertex is deeper below the key tops than the gate."""
    a = ik.key_audit(W, frames)
    top = ik.keys['top_cm']
    return np.any([(a[s]['over'] > 0) & (top - a[s]['over_min'] > P.KEY_PENETRATION_MAX_CM) for s in SIDES], axis=0)


def transition_arms(ctx, ik, W_fit, W_ik, s, keep_fit):
    """Transition arms: the six arm bones' locals blend from the (seam-blended) seat-fit pose (w = 0) to the whole-arm
    IK pose (w = 1) with w = smootherstep(s) of the roll path, held at 0 where keep_fit (the SeatedIdle seam window),
    raised per frame (then a smooth envelope) wherever the blended arm skin is closer than the target to the real desk
    or a finger enters the keycaps deeper than the key penetration gate."""
    keep = np.asarray(keep_fit, float)
    w = smootherstep(s) * (1. - keep)
    steps = np.linspace(0, 1, 21)

    def bad(Wb, frames=None):
        posed = frames is not None
        out = key_penetration(ik, Wb, frames)
        for side in SIDES:
            out |= ik.clearance(Wb, side, 1, frames, SEARCH_REACH_CM, posed_frames=posed)[0] \
                < FOREARM_TARGET_CLEARANCE_CM                 # every arm vertex (short clips)
        return out
    raised = set()
    for _ in range(2):
        Wb = blend_arm_locals(ctx.sk, W_fit, W_ik, w)
        badf = np.nonzero(bad(Wb))[0]
        if not len(badf):
            break
        need = w.copy()
        for f in badf:
            for v in steps[steps >= w[f]]:
                need[f] = v
                if not bad(blend_arm_locals(ctx.sk, W_fit[f:f + 1], W_ik[f:f + 1], np.array([v])), np.array([f]))[0]:
                    break
            raised.add(int(f))
        w = np.clip(envelope(need, ik.dt), 0., 1.) * (1. - keep)
    Wb = blend_arm_locals(ctx.sk, W_fit, W_ik, w)
    return Wb, {'ik_weight': [_r(v, 4) for v in w], 'frames_raised_for_clearance_or_keys': sorted(raised)}


POST_CONTACT_ITERATIONS = 48


def post_contact(ctx, ik, W, window, seam_frame=None):
    """After the DeskTyping-side seam blend (and with the captured finger curls kept on every frame), per side a smooth
    vertical wrist correction (non-stretch two-bone IK, current elbow as pole, current wrist-relative hand rotation,
    fingers carried) over the window: exact key contact (KeyTop + 0.08 cm) at the seam frame when that hand is over the
    keys there, tapered by the window weight, plus the smallest smooth lift that removes any keycap penetration or desk
    contact inside the window. Zero outside the window."""
    F = len(W)
    window = np.asarray(window, float)
    gate = window > 0
    # the seam frame IS the neighbour's written pose: the smooth lift is tapered to exactly zero there (C1, quintic)
    taper = np.ones(F) if seam_frame is None else seam_taper(F, [seam_frame], ik.dt)
    top = ik.keys['top_cm']
    lift = {s: np.zeros(F) for s in SIDES}
    seam_d = {s: 0. for s in SIDES}
    W0 = np.array(W, copy=True)
    Wc = W0
    for _ in range(POST_CONTACT_ITERATIONS):
        a = ik.key_audit(Wc)
        more = False
        for s in SIDES:
            need = np.where(gate & (a[s]['over'] > 0), np.maximum(0., top - a[s]['over_min']), 0.)
            cl = ik.clearance(Wc, s, 1, reach=SEARCH_REACH_CM)[0]
            need = np.nan_to_num(np.maximum(need, np.where(gate & (cl < 0), LIFT_STEP_CM, 0.)))
            if seam_frame is not None:
                need[seam_frame] = 0.
                if a[s]['over'][seam_frame] >= KEY_MIN_OVER_VERTICES:
                    res = top + KEY_TOP_TARGET_CM - a[s]['over_min'][seam_frame]
                    gap_s = a[s]['over_min'][seam_frame] - top
                    # the seam frame IS the neighbour's written pose: it is only corrected when outside the key gate
                    if not (POLISH_ACCEPT_GAP_CM[0] <= gap_s <= POLISH_ACCEPT_GAP_CM[1]) and abs(res) > CONTACT_TOL_CM:
                        seam_d[s] += float(res)
                        more = True
            if need.any():
                more = True
                lift[s] = envelope(lift[s] + need, ik.dt) * gate * taper
        if not more:
            break
        Wc = np.array(W0, copy=True)
        for s in SIDES:
            v = lift[s] + seam_d[s] * window
            if not v.any():
                continue
            a_, b_, c_ = (ctx.sk.j(n) for n in ARM_BONES[s])
            tgt = Wc[:, c_, :3, 3] + UP * v[:, None] / 100.
            Wc, _, _, _, _ = solve_arm(ctx.sk, Wc, s, tgt, Wc[:, b_, :3, 3], ctx.base.ibm,
                                       D=wrist_relative(Wc, ctx.base.names, ctx.base.ibm, s), limit=False)
    return Wc, {s: {'seam_contact_shift_cm': _r(seam_d[s], 4), 'lift_max_cm': _r(lift[s].max(), 4),
                    'lift_frames': [int(i) for i in np.nonzero(lift[s])[0]]} for s in SIDES}


def seam_blend_with_soles(ctx, A, W_clip, Tg, w, W_raw, times):
    """fit_seat_pelvis_pitch.seam_blend_pose + seam_blend_legs, then the seat fit's own smooth no-penetration foot lift
    (smooth_lift: never below a frame's need, tapered to zero on the clip and on the target) until no sole is below
    the support on a blended frame."""
    fit = ctx.seat_fit(W_raw, times, ROLL_OFFSET_CM)
    lift = {sd: np.zeros(len(w)) for sd in T.LEGS}
    W = P.seam_blend_pose(ctx.sk, A, W_clip, Tg, w)
    W, legs = P.seam_blend_legs(ctx.sk, W, W_clip, Tg, w)
    mid = (w > 0) & (w < 1)
    for _ in range(6):
        so = fit.trial.soles(W)
        need = {sd: np.where(mid, np.maximum(0., P.SEAM_SOLE_CLEAR_CM - np.nan_to_num(
            so[f'{sd}_sole']['lowest_any_z'] - T.SUPPORT_Z_CM, nan=1.)), 0.) for sd in T.LEGS}
        if not any(v.any() for v in need.values()):
            break
        lift = {sd: P.smooth_lift(lift[sd] + need[sd], ~mid) for sd in T.LEGS}
        W = P.seam_blend_pose(ctx.sk, A, W_clip, Tg, w)
        W, legs = P.seam_blend_legs(ctx.sk, W, W_clip, Tg, w, foot_lift_cm=lift)
    legs = dict(legs, foot_lift_cm_max={sd: _r(v.max(), 4) for sd, v in lift.items()})
    return W, legs


def seam(ctx, A, shift_a, B, shift_b, fps_a, fps_b):
    """Position / rotation / velocity deltas between pose A[-1] and B[0] in the world (each with its own body shift)."""
    def world(W, sh):
        return E.to_ue(W[..., :3, 3]) + sh[..., None, :]
    pa, pb = world(A[-2:], shift_a[-2:]), world(B[:2], shift_b[:2])
    H = ctx.sk.j('Hips')
    dpos = np.linalg.norm(pb[0] - pa[1], axis=-1)
    rot = P.rot_angle_deg(A[-1, :, :3, :3], B[0, :, :3, :3])
    va, vb = (pa[1] - pa[0]) * fps_a, (pb[1] - pb[0]) * fps_b
    dv = np.linalg.norm(vb - va, axis=-1)
    arms = [ctx.sk.j(n) for s in SIDES for n in ARM_BONES[s]]
    return {'position_delta_cm': {'hips': _r(dpos[H], 4), 'max_joint': _r(dpos.max(), 4), 'max_arm_joint': _r(dpos[arms].max(), 4),
                                  'max_joint_name': ctx.sk.names[int(dpos.argmax())]},
            'rotation_delta_deg': {'hips': _r(rot[H], 4), 'max_joint': _r(rot.max(), 4)},
            'velocity_delta_cm_s': {'hips': _r(dv[H], 3), 'max_joint': _r(dv.max(), 3), 'max_arm_joint': _r(dv[arms].max(), 3),
                                    'max_joint_name': ctx.sk.names[int(dv.argmax())]}}


def profile_validation(ctx, W_out, W_in, W_raw, times, shift):
    """The DeskTyping 3..8 s audit window as a contact profile, gated by tools/validate_unreal_contact_profile.validate."""
    sl = slice(AUDIT_KEYS[0], AUDIT_KEYS[1] + 1)
    Wo, Wi, Wr, t, sh = W_out[sl], W_in[sl], W_raw[sl], times[sl], shift[sl]
    def audit(W):
        Ws = np.array(W, copy=True)
        Ws[..., :3, 3] += gltf_shift(sh)[:, None, :]
        return T.Trial(E.Source(dict(ctx.base.d, joint_world=Ws)), ctx.tri, ctx.keys, (0., 0.)).key_audit(Ws)
    ko, ki = audit(Wo), audit(Wi)
    top = float(ctx.keys['top_cm'])
    Lo = arm_locals(ctx.sk, Wo)
    sel = {s: int(len(ctx.base.patch(f'{s}_fingers')['pos'])) for s in SIDES}
    fingers = [k for k, n in enumerate(ctx.sk.names) if any(f in n for f in FINGERS)]
    L0, L1 = arm_locals(ctx.sk, Wr), Lo
    Li = arm_locals(ctx.sk, Wi)
    rows = []
    for i in range(len(t)):
        def hands(k, corrected):
            out = []
            for s in SIDES:
                over, mn = int(k[s]['over'][i]), float(k[s]['over_min'][i])
                h = {'side': s, 'selectedVertices': sel[s], 'overKeyVertices': over,
                     'penetrationCm': max(0., top - mn) if over else 0.}
                if corrected:
                    h['overMinCm'] = mn if over else float('nan')
                out.append(h)
            return out
        fl = max(float(P.rot_angle_deg(L0[i:i + 1, k, :3, :3], L1[i:i + 1, k, :3, :3]).max()) for k in fingers)
        bl = max(abs(np.linalg.norm(Wo[i, k, :3, 3] - Wo[i, p, :3, 3]) - np.linalg.norm(Wr[i, k, :3, 3] - Wr[i, p, :3, 3]))
                 for k, p in enumerate(ctx.sk.parents) if p >= 0) * 100
        arms = {}
        for s in SIDES:
            # the clavicle is reported too whenever its local differs from the input clip's (a girdle correction):
            # the profile then states truthfully that more than the six arm bones changed (and is refused)
            sb = ctx.sk.j(f'{SIDES[s]}Shoulder')
            extra = [f'{SIDES[s]}Shoulder'] if float(P.rot_angle_deg(Li[i:i + 1, sb, :3, :3], Lo[i:i + 1, sb, :3, :3]).max()) > 1e-3 else []
            for n in list(ARM_BONES[s]) + extra:
                L = Lo[i, ctx.sk.j(n)]
                sc = np.linalg.norm(L[:3, :3], axis=0)
                q = P.quat_from_matrix((L[:3, :3] / sc)[None])[0]
                arms[n] = {'translation': [float(v) for v in L[:3, 3]], 'rotation': [float(v) for v in q], 'scale': [float(v) for v in sc]}
        rows.append({'time': float(3 + i / 60), 'invalidInfluences': 0, 'finger_local_max_error_degrees': fl,
                     'bone_length_max_error_cm': bl, 'corrected_local_arms': arms, 'hands': hands(ki, False),
                     'corrected': {'invalidInfluences': 0, 'keyTopCm': top, 'hands': hands(ko, True)}})
    try:
        res = contact_profile.validate({'samples': rows})
        return {'validator': 'tools/validate_unreal_contact_profile.py validate()', 'pass': True, 'result': res}
    except ValueError as err:
        return {'validator': 'tools/validate_unreal_contact_profile.py validate()', 'pass': False, 'refusal': str(err)}


LABELS = {'label': 'proposal', 'verified': False, 'requires_server_reaudit': True, 'requires_native_collision_audit': True,
          'never_a_receipt': True, 'method': 'whole-arm IK on the seat-fit clips (tools/solve_seated_typing_arm_ik.py)'}


def rel(path):
    path = Path(path)
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def strip(rep):
    return {k: v for k, v in rep.items() if not k.startswith('_')}


LOOP_BLEND_S = .5              # DeskTyping loop closure: C1 blend of the last 0.5 s to frame 0's swivel / girdle / lift
FINISH_RESERVE_S = 1200.       # the full-clip finish starts only at the beginning of a run (measured 1280 s; one stage)
FINISH_KEYS = ('delta', 'phi', 'lift', 'hand_xy', 'girdle', 'pitch', 'finger_xy_target', 'mode', 'on')
CHUNK_RESERVE_S = 240.          # a chunk is only started with at least this much of the bound left
ERGO_BUDGET_S_PER_CHUNK = 60.   # the ergonomic candidate search per chunk stops after this (the clearance pose is kept)
MEASURE_S_PER_FRAME = .5        # measured (seated-arms profile, 60-frame subset): ~0.5 s per frame for every gate
TRANSITIONS_RESERVE_S = 420.
SEAM_FULL_S = .3                # full-pose seam windows of the transitions (SeatedIdle side and DeskTyping side)


def transition(ctx, role, at_end, roll, r0, W_idle, W_dt, out_dir, idle_capture=None, dt_capture=None):
    """SitToType (at_end: the keyboard is at its end) / TypeToSit. The chair roll plays over the clip. Both ends are
    full-pose seam blends (fit_seat_pelvis_pitch.seam_blend_pose + seam_blend_legs, quintic weights) of every joint
    EXCEPT the fingers: the SeatedIdle end becomes the validated SeatedIdle loop pose (SitToType's first frame = SeatedIdle's
    last; TypeToSit's last = SeatedIdle's first) and the keyboard end the written DeskTyping pose (its first / last frame,
    held), while the fingers keep this clip's captured curls on every frame (their boundary jump is reported).
    Between them the arms blend from the seat-fit arms to the whole-arm IK (contact on the fit's own over-key frames,
    real-desk clearance)."""
    f_c, r_c, g_c, t_c = ctx.clip(role)
    F = len(t_c)
    s = ChairRoll.pull_in_s(t_c) if at_end else ChairRoll.push_back_s(t_c)
    off = roll.offset(s)
    shift_c = off - r0
    fps = (F - 1) / (t_c[-1] - t_c[0])
    n = int(round(SEAM_FULL_S * fps))
    A = P.armature_world(g_c, g_c.by_name['mixamorig:Hips'])
    W_fit = f_c.joint_world
    # SeatedIdle side
    mode = 'start' if at_end else 'end'
    Tg = P.seam_target(W_idle, mode, F)
    w_idle = P.seam_weight('start', F, 0, n) if at_end else P.seam_weight('end', F, F - 1 - n, F - 1)
    if ARMS_ONLY:      # the base already joins SeatedIdle; its lower body and pelvis must not change
        W1, legs_idle = W_fit, 'base unchanged (arms-only mode)'
    else:
        W1, legs_idle = seam_blend_with_soles(ctx, A, W_fit, Tg, w_idle, r_c.joint_world, t_c)
    # arms: whole-arm IK, blended in along the roll
    contact_shift = shift_c[-1] if at_end else shift_c[0]
    ikc = ctx.ik(W1, r_c.joint_world, t_c, shift_c, contact_shift=contact_shift)
    W_ik = ikc.solve()
    W2, weights = transition_arms(ctx, ikc, W1, W_ik, s, w_idle)
    # DeskTyping side: the written DeskTyping first (SitToType) / last (TypeToSit) frame, held
    Td = np.repeat((W_dt[0] if at_end else W_dt[-1])[None], F, axis=0)
    w_dt = P.seam_weight('end', F, F - 1 - n, F - 1) if at_end else P.seam_weight('start', F, 0, n)
    if ARMS_ONLY:      # arm-local seam into DeskTyping's first / last frame; the lower body stays the base's
        W3, legs_dt = blend_arm_locals(ctx.sk, W2, Td, w_dt), 'base unchanged (arms-only mode)'
        W3 = finger_override(ctx, W3, W_fit, [])
    else:
        W3, legs_dt = seam_blend_with_soles(ctx, A, W2, Td, w_dt, r_c.joint_world, t_c)
        # fingers keep THIS clip's captured curls on every frame (gate (a): all-frame invariance, no seam exemption)
        W3 = finger_override(ctx, W3, r_c.joint_world, [])
    W3, seam_lift = post_contact(ctx, ikc, W3, w_dt, seam_frame=F - 1 if at_end else 0)
    # the SitDown / GetUp desk-clearance pass (every arm vertex, every frame); both seam frames never move
    protect = np.zeros(F, bool)
    protect[[0, F - 1]] = True
    W3, desk_pass = desk_clear_arms(ctx, W3, shift_c, t_c, protect, no_down=True, taper_s=SEAM_TAPER_S)
    path, sha = write(ctx, g_c, W3, t_c, out_dir, f'SUB01_{role}', dict(LABELS, role=role))
    Wcb = readback(ctx, path, t_c)
    seam_frame = F - 1 if at_end else 0
    rep = {'role': role, 'glb': rel(path), 'sha256': sha, 'bytes': path.stat().st_size, 'keys': F,
           'input_fit_clip': rel(Path(FIT_DIR) / CLIPS[role][0]), 'raw_capture': CLIPS[role][1],
           'chair_roll': roll.describe(t_c, s) | {'activity': 'pull chair in' if at_end else 'push chair back'},
           'seam_windows': {'seated_idle_side_weight': [_r(v, 4) for v in w_idle], 'desk_typing_side_weight': [_r(v, 4) for v in w_dt],
                            'window_frames': n, 'fingers': 'captured curls kept on every frame (all-frame invariance gate)',
                            'legs': {'seated_idle_side': legs_idle, 'desk_typing_side': legs_dt},
                            'desk_typing_side_wrist_contact': seam_lift},
           'desk_clear_pass': desk_pass,
           'arm_weights': weights, 'ik_history': ikc.history,
           'measure': measure(ctx, role, Wcb, r_c.joint_world, t_c, shift_c, off, ikc, key_seam=seam_frame,
                              finger_seams=(), base=W_fit if ARMS_ONLY else None)}
    rep['all_gates_pass'] = bool(rep['measure']['all_gates_pass'])
    return rep, Wcb, shift_c, t_c


def run(args):
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx = Context(args.source, cache=args.cache, chair_translation=args.chair_translation, keycaps=args.keycaps)
    T0 = np.asarray(ctx.chair['translation_cm'], float)
    r0 = np.array([*ROLL_OFFSET_CM, 0.])
    summary = {'schema': SCHEMA, **LABELS, 'geometry': {'file': str(GEOMETRY_JSON.relative_to(ROOT)), 'sha256': ctx.geometry_sha256,
                                                         'source_sha256': LINEA_SHA256, **{k: ctx.geometry[k] for k in (
                                                             'provenance', 'overall_dims_cm', 'floor_cm', 'tabletop_slab',
                                                             'front_apron', 'knee_bay_cm', 'grommet_rim_top_cm')}},
               'chair': {k: ctx.chair[k] for k in ('file', 'sha256', 'translation_cm', 'rotation_xyzw', 'scale',
                                                     'component_world_bounds_cm', 'measured_translation_cm',
                                                     'proposed_delta_cm', 'translation_is_measured')},
               'base': {'dir': rel(Path(FIT_DIR)), 'solver_frame_chair_offset_cm': list(ROLL_OFFSET_CM),
                        'warm_start': 'the seated base clips (pelvis/legs/seat contact) are inputs; only the six arm bones '
                                      'are re-solved (transitions also seam-blend to their neighbours)'},
               'keyboard': {'source': ctx.keys['source'], 'key_top_cm': _r(ctx.keys['top_cm']), 'keycaps': ctx.keys['keycaps'],
                            'key_field_min_cm': [_r(v, 3) for v in ctx.keys['key_min']],
                            'key_field_max_cm': [_r(v, 3) for v in ctx.keys['key_max']],
                            'root_home_keyboard_nodes_184_187_xy_cm': [[181.45, -302.0464], [218.55, -285.9536]],
                            'provenance': 'repo web/house/home.js furnished("keyboard", 2, .846, -2.94, .371) = the home\'s '
                                          'keyboard source nodes 184-187 in root\'s LINEA record (same XY footprint): the '
                                          'keyboard did not move with the new desk'},
               'gates_from': [MAIN_SEAT_RULE + ' -- the seat gate', 'branch tools/validate_unreal_seat_contact.py (SEAT_BAND_CM, '
                              'SOLE_BAND_CM, MIN_PATCH_VERTICES, MIN_SUPPORT_VERTICES; also reported, weaker than main)',
                              'tools/validate_unreal_contact_profile.py (KEY_GAP_MAX_CM, validate())',
                              'tools/fit_seat_pelvis_pitch.py gates() / contact_per_frame()'],
               'constants': {'key_contact_target_cm': KEY_TOP_TARGET_CM, 'key_gap_max_cm': contact_profile.KEY_GAP_MAX_CM,
                             'key_penetration_max_cm': P.KEY_PENETRATION_MAX_CM, 'seat_band_cm': list(seat_contact.SEAT_BAND_CM),
                             'sole_band_cm': list(seat_contact.SOLE_BAND_CM), 'min_support_vertices': seat_contact.MIN_SUPPORT_VERTICES,
                             'forearm_target_clearance_cm': FOREARM_TARGET_CLEARANCE_CM, 'desk_clearance_gate': '> 0 cm every frame',
                             'wrist_soft_flexion_deg': list(WRIST_SOFT_FLEX_DEG), 'wrist_soft_deviation_deg': list(WRIST_SOFT_DEV_DEG),
                             'wrist_note': 'soft targets (smooth saturation), never gates'}}
    # ---- roll: the seat fit's chair offset plus the scanned extra pull-in
    f_dt, r_dt, g_dt, t_dt = ctx.clip('DeskTyping_seated')
    prior = None
    if args.roll_from_base:
        dy = base_upper_body_shift_y(ctx)
        scan = {'fixed': True, 'chosen_extra_pull_in_dy_cm': dy,
                'rule': 'the base moved the upper body (Spine2, DeskTyping 3..8 s mean) by -dy in UE Y relative to the '
                        'seat-fit base the roll and the keyboard contact were validated on; the chair is pulled in dy less, '
                        'so the captured upper body - keyboard relation is kept'}
        pick = {'extra_pull_in_dy_cm': dy}
    elif args.roll_dy is not None:
        scan = {'fixed': True, 'chosen_extra_pull_in_dy_cm': args.roll_dy,
                'rule': 'fixed by --roll-dy (the earlier probe scan on the seat-fit base chose 0: docs/proposed/seated-typing-ik)'}
        pick = {'extra_pull_in_dy_cm': args.roll_dy}
    elif args.resume:
        prior = json.loads((out_dir / 'seated-typing-ik.proposal.json').read_text())
        scan = prior['roll_scan']
        pick = {'extra_pull_in_dy_cm': scan['chosen_extra_pull_in_dy_cm']}
    else:
        pick, scan = roll_scan(ctx, f_dt, r_dt, t_dt, dys=(0.,) if args.quick else ROLL_SCAN_DY_CM)
    if args.resume and prior is None:
        prior = json.loads((out_dir / 'seated-typing-ik.proposal.json').read_text())
    if args.quick:                      # smoke run only: a subset of DeskTyping keys, no profile gate
        f_dt, r_dt, g_dt, t_dt = ctx.clip('DeskTyping_seated', list(t_dt[AUDIT_KEYS[0]:AUDIT_KEYS[1] + 1:30]))
    dy = float(pick['extra_pull_in_dy_cm'])
    roll = ChairRoll(T0, (r0[0], r0[1] + dy))
    summary['roll_scan'] = scan
    print('roll', roll.roll, flush=True)
    reports, worlds = {}, {}
    import time
    t_start = time.time()
    summary['bounded'] = {'max_wall_seconds': args.max_seconds, 'swivel_grid_deg': [SWIVEL_GRID_DEG[0], SWIVEL_GRID_DEG[-1]],
                          'swivel_outer_passes': 3, 'contact_passes': CONTACT_PASSES, 'search_contact_passes': SEARCH_CONTACT_PASSES,
                          'lift_max_cm': LIFT_MAX_CM, 'post_contact_iterations': POST_CONTACT_ITERATIONS, 'stages_done': []}

    def checkpoint(stage, blocker=None):
        b = summary['bounded']
        b['elapsed_seconds'] = round(time.time() - t_start, 1)
        if stage:
            b['stages_done'].append(stage)
        summary['clips'] = {k: {'glb': v['glb'], 'sha256': v['sha256'], 'all_gates_pass': v['all_gates_pass']} for k, v in reports.items()}
        summary['ready'] = False
        summary['native_verified'] = False
        summary['partial'] = {'stage_reached': b['stages_done'][-1] if b['stages_done'] else 'setup', 'blocker': blocker}
        for k, v in reports.items():
            (out_dir / f'SUB01_{k}.report.json').write_text(json.dumps(strip(v), indent=1, allow_nan=False) + '\n')
        (out_dir / 'seated-typing-ik.proposal.json').write_text(json.dumps(summary, indent=1, allow_nan=False) + '\n')

    def over_budget(next_stage):
        if args.max_seconds and time.time() - t_start > args.max_seconds:
            checkpoint(None, f'wall-clock bound {args.max_seconds} s reached before stage {next_stage}')
            return True
        return False
    # ---- DeskTyping (every 60 Hz key of the loop)
    F = len(t_dt)
    shift = np.tile(roll.roll - r0, (F, 1))
    if args.resume:
        # the committed bounded run's DeskTyping stage: the written GLB (sha256 checked) and its report, re-read
        rep = json.loads((out_dir / 'SUB01_DeskTyping_seated.report.json').read_text())
        path = ROOT / rep['glb']
        if hashlib.sha256(path.read_bytes()).hexdigest() != rep['sha256'] or prior['clips']['DeskTyping_seated']['sha256'] != rep['sha256']:
            raise ValueError('resumed DeskTyping GLB differs from its report')
        Wb = readback(ctx, path, t_dt)
        rep['resumed_from_stage'] = 'DeskTyping_seated (bounded run, same code path; GLB sha256 re-checked)'
        pb = prior.get('bounded', {})
        summary['bounded'] = dict(summary['bounded'], resumed=True, desk_typing_stage_elapsed_seconds=pb.get('elapsed_seconds'),
                                  desk_typing_stage_max_wall_seconds=pb.get('max_wall_seconds'))
        summary['bounded']['stages_done'] = ['DeskTyping_seated']
    else:
        # per-frame bound: chunked solve with a checkpoint per chunk; the run stops between chunks at the deadline
        # (reserving the measured per-frame measurement cost and the transitions) and the next run resumes
        deadline = t_start + args.max_seconds - CHUNK_RESERVE_S if args.max_seconds else None
        ik, progress = solve_chunked(ctx, f_dt.joint_world, r_dt.joint_world, t_dt, shift, out_dir / 'DeskTyping_seated.chunks',
                                     deadline, ergo_budget_s=ERGO_BUDGET_S_PER_CHUNK)
        if ik is None:
            summary['bounded']['desk_typing_chunks'] = progress
            checkpoint(None, f'wall-clock bound {args.max_seconds} s: DeskTyping solved in {progress["chunks_done"]} of '
                             f'{progress["chunks_total"]} chunks (checkpointed); rerun the same command to resume')
            return summary, reports
        summary['bounded']['desk_typing_chunks'] = {'chunks': ik.chunks, 'chunk_frames': CHUNK_FRAMES, 'overlap_frames': CHUNK_OVERLAP}
        # full-clip finish (whole-clip segmentation, loop closure, contact, every-vertex clearance), itself checkpointed
        fin = out_dir / 'SUB01_DeskTyping_seated.finish-checkpoint.npz'
        sig = hashlib.sha256(b''.join((out_dir / 'DeskTyping_seated.chunks' / c).read_bytes() for c in ik.chunks)
                             + repr((LOOP_BLEND_S, KEY_FIELD_MARGIN_CM, KEY_FIELD_MIN_OVER, PITCH_CLEAR_CANDIDATES,
                                    GIRDLE_CLEAR_CANDIDATES, POLISH_XY_CM, PITCH_CLEAR_ROUNDS, 'v3')).encode()).hexdigest()
        if fin.exists() and str(np.load(fin)['signature']) == sig:
            z = np.load(fin)
            ik.close_loop(int(round(LOOP_BLEND_S / ik.dt)), {s_: np.array(ik.phi[s_], float) for s_ in SIDES},
                          {s_: np.array(ik.lift[s_], float) for s_ in SIDES})     # the solved tail's IK inputs
            for k in FINISH_KEYS:
                setattr(ik, k, {s_: z[f'{k}_{s_}'] for s_ in SIDES})
            ik.finish_report = json.loads(str(z['report'])) | {'resumed_from_checkpoint': fin.name}
            W = ik.pose_all()
        else:
            if args.max_seconds and time.time() - t_start > args.max_seconds - FINISH_RESERVE_S:
                checkpoint(None, f'wall-clock bound {args.max_seconds} s: every DeskTyping chunk is solved (checkpointed) '
                                 'but the full-clip finish does not fit in this run; rerun the same command')
                return summary, reports
            W = ik.finish(loop_frames=int(round(LOOP_BLEND_S / ik.dt)))
            np.savez_compressed(fin, signature=sig, report=json.dumps(ik.finish_report),
                                **{f'{k}_{s_}': np.asarray(getattr(ik, k)[s_]) for k in FINISH_KEYS for s_ in SIDES})
        summary['bounded']['desk_typing_finish'] = {k: v for k, v in ik.finish_report.items() if k != 'clearance_history'}
        if args.max_seconds and time.time() - t_start > args.max_seconds - MEASURE_S_PER_FRAME * F:
            checkpoint(None, f'wall-clock bound {args.max_seconds} s: DeskTyping is solved and finished (checkpointed) but '
                             'the measurement does not fit in this run; rerun the same command to measure')
            return summary, reports
        path, sha = write(ctx, g_dt, W, t_dt, out_dir, 'SUB01_DeskTyping_seated', dict(LABELS, role='DeskTyping_seated'))
        np.savez_compressed(out_dir / 'SUB01_DeskTyping_seated.solve-checkpoint.npz', **{
            f'{k}_{s_}': np.asarray(getattr(ik, k)[s_], float) for k in ('phi', 'lift', 'delta', 'mode', 'on', 'girdle') for s_ in SIDES})
        checkpoint('DeskTyping_seated_solve')
        Wb = readback(ctx, path, t_dt)
        rep = {'role': 'DeskTyping_seated', 'glb': rel(path), 'sha256': sha, 'bytes': path.stat().st_size,
               'keys': F, 'input_fit_clip': rel(Path(FIT_DIR) / CLIPS['DeskTyping_seated'][0]),
               'raw_capture': CLIPS['DeskTyping_seated'][1], 'readback_max_world_error_cm': _r(np.abs(Wb[..., :3, 3] - W[..., :3, 3]).max() * 100, 6),
               'ik_history': ik.history, 'finish': ik.finish_report, 'measure': measure(ctx, 'DeskTyping_seated', Wb, r_dt.joint_world, t_dt, shift,
                                                            np.tile(roll.roll, (F, 1)), ik,
                                                            base=f_dt.joint_world if ARMS_ONLY else None)}
        rep['contact_profile'] = profile_validation(ctx, Wb, f_dt.joint_world, r_dt.joint_world, t_dt, shift) if not args.quick \
            else {'pass': False, 'skipped': 'quick smoke run'}
        rep['all_gates_pass'] = bool(rep['measure']['all_gates_pass'] and rep['contact_profile']['pass'])
    reports['DeskTyping_seated'], worlds['DeskTyping_seated'] = rep, (Wb, shift, t_dt)
    print('DeskTyping', rep['all_gates_pass'], flush=True)
    if not args.resume:
        checkpoint('DeskTyping_seated')
    # ---- transitions: the roll is played over them (pull-in over SitToType, push-back over TypeToSit)
    f_i, r_i, _, t_i = ctx.clip('SeatedIdle')
    W_idle = f_i.joint_world
    for role, at_end in (('SitToType_seated', True), ('TypeToSit_seated', False)):
        if over_budget(role):
            return summary, reports
        rep, Wcb, shift_c, t_c = transition(ctx, role, at_end, roll, r0, W_idle, Wb, out_dir,
                                            (r_i.joint_world, t_i), (r_dt.joint_world, t_dt))
        reports[role], worlds[role] = rep, (Wcb, shift_c, t_c)
        print(role, rep['all_gates_pass'], flush=True)
        checkpoint(role)
    # ---- unchanged neighbours (seat-pose-fit GLBs) for the seams: at the measured chair (body at its actual placement)
    for role in ('SeatedIdle', 'SitDown_seated', 'GetUp_seated'):
        f_c, r_c, g_c, t_c = ctx.clip(role)
        worlds[role] = (f_c.joint_world, np.tile(-r0, (len(t_c), 1)), t_c)
    chain = [('SitDown_seated', 'SeatedIdle'), ('SeatedIdle', 'SitToType_seated'), ('SitToType_seated', 'DeskTyping_seated'),
             ('DeskTyping_seated', 'DeskTyping_seated'), ('DeskTyping_seated', 'TypeToSit_seated'),
             ('TypeToSit_seated', 'SeatedIdle'), ('SeatedIdle', 'GetUp_seated')]
    seams = []
    for a, b in chain:
        Wa, sa, ta = worlds[a]
        Wb_, sb, tb = worlds[b]
        fa, fb = 1. / float(np.median(np.diff(ta))), 1. / float(np.median(np.diff(tb)))
        seams.append({'from': f'{a}.last', 'to': f'{b}.first', 'fps': [_r(fa, 3), _r(fb, 3)], **seam(ctx, Wa, sa, Wb_, sb, fa, fb)})
    summary['seams'] = seams
    # ---- the roll activity: chair shell along the whole path, reversibility, per-frame transforms
    summary['chair_roll_activity'] = {
        'model': ChairRoll.__doc__.strip(), 'start_transform_cm': [_r(v) for v in roll.start],
        'end_transform_cm': [_r(v) for v in roll.start + roll.roll], 'roll_cm': [_r(v) for v in roll.roll],
        'seat_fit_chair_offset_cm': list(ROLL_OFFSET_CM), 'extra_pull_in_dy_cm': dy,
        'played_over': {'pull_in': 'SitToType_seated', 'push_back': 'TypeToSit_seated'},
        'held_rolled_during': 'DeskTyping_seated', 'at_measured_transform_during': ['SitDown_seated', 'SeatedIdle', 'GetUp_seated'],
        'complete_chair': {k: v for k, v in ctx.complete_chair.items() if k not in ('triangles_cm', 'face_normals', 'material', 'vertices_cm')},
        'complete_chair_clearance_along_path': chair_path_clearance(ctx.complete_chair, roll, ctx.boxes, ctx.box_nodes),
        'reversibility': reversibility(roll, worlds['SitToType_seated'][2], worlds['TypeToSit_seated'][2]),
        'feet': 'the body rolls rigidly with the chair: sole gaps are unchanged and the soles slide on the floor at the roll '
                'speed (a seated scoot); per-frame sole gates are in each transition report'}
    summary['clips'] = {k: {'glb': v['glb'], 'sha256': v['sha256'], 'all_gates_pass': v['all_gates_pass']} for k, v in reports.items()}
    summary['all_gates_pass'] = {k: v['all_gates_pass'] for k, v in reports.items()}
    act = summary['chair_roll_activity']
    path_ = act['complete_chair_clearance_along_path']
    summary['gates'] = dict({f'clip_{k}': v for k, v in summary['all_gates_pass'].items()},
                            roll_complete_chair_clear_of_desk=path_['desk_clear_all_samples'],
                            roll_complete_chair_floor_no_penetration=path_['floor_no_penetration'],
                            roll_floor_contact_unchanged=path_['floor_gap_constant_along_roll'],
                            roll_reversible_exact=act['reversibility']['reversible'])
    summary['ready'] = bool(all(summary['gates'].values()))
    summary['native_verified'] = False
    summary['ready_rule'] = 'every aggregate gate true; consumers must read `ready` and `gates` (the CLI exits %d when not ready)' % EXIT_REFUSED
    summary.pop('partial', None)
    summary['bounded']['elapsed_seconds'] = round(time.time() - t_start, 1)
    summary['bounded']['stages_done'].append('seams_roll_gates')
    for k, v in reports.items():
        (out_dir / f'SUB01_{k}.report.json').write_text(json.dumps(strip(v), indent=1, allow_nan=False) + '\n')
    (out_dir / 'seated-typing-ik.proposal.json').write_text(json.dumps(summary, indent=1, allow_nan=False) + '\n')
    return summary, reports


def audit_main_seat_rule(out_dir, source, cache=None):
    """Re-read every committed clip of out_dir and gate its seat base with main's strong rule (MAIN_SEAT_RULE); the
    verdicts are written into the reports and the proposal (ready stays false unless everything passes)."""
    out_dir = Path(out_dir)
    base = E.Source.load(source)
    chair = load_chair()
    keys = T.keycaps_from_glb()
    prop = json.loads((out_dir / 'seated-typing-ik.proposal.json').read_text())
    res = {}
    for role, clip in prop['clips'].items():
        rp = out_dir / f'SUB01_{role}.report.json'
        rep = json.loads(rp.read_text())
        path = ROOT / rep['glb']
        if hashlib.sha256(path.read_bytes()).hexdigest() != rep['sha256']:
            raise ValueError(f'{role}: committed GLB differs from its report')
        g = G.Gltf(path)
        t = np.asarray(g.animation().key_times(), float)
        W, _ = E.joint_worlds(g, base.names, list(t))
        raw = ROOT / rep['raw_capture']
        Wr, _ = E.joint_worlds(G.Gltf(raw), base.names, list(t))
        d = dict(base.d, joint_world=Wr, times=t)
        fit = P.SeatFit(E.Source(d), chair['cushion_triangles_cm'], keys, tuple(ROLL_OFFSET_CM))
        r = main_strong_seat_rule(fit, W, t)
        m = rep['measure']
        m['seat_main_strong_rule'] = r
        m['seat_pass_branch_rule'] = m.get('seat_pass_branch_rule', m['seat_pass'])
        m['seat_pass'] = bool(m['seat_pass_branch_rule'] and r['pass'])
        m['all_gates_pass'] = bool(m['all_gates_pass'] and r['pass'])
        rep['all_gates_pass'] = bool(rep['all_gates_pass'] and r['pass'])
        rp.write_text(json.dumps(rep, indent=1, allow_nan=False) + '\n')
        prop['clips'][role]['all_gates_pass'] = rep['all_gates_pass']
        prop.setdefault('gates', {})[f'clip_{role}'] = rep['all_gates_pass']
        res[role] = r
    prop['all_gates_pass'] = {k: v['all_gates_pass'] for k, v in prop['clips'].items()}
    prop['seat_base_main_strong_rule'] = {k: {'pass': v['pass'], 'failing_regions': [n for n, x in v['regions'].items() if not x['pass_all_frames']]}
                                          for k, v in res.items()}
    prop['ready'] = False
    prop['not_ready_because'] = (
        'the seat base (docs/proposed/seat-pose-fit clips) fails main\'s strong seat rule (median gap <= band high and '
        'band coverage >= 0.5; ' + MAIN_SEAT_RULE + '), not only this branch\'s MIN_SUPPORT_VERTICES rule; and the measured '
        'chair\'s castors sit 2.5 cm below the floor support plane. The arm step must be re-run on the corrected seated '
        'base (docs/proposed/seat-pose-anatomical) with its chair transform.')
    prop['gates_from'] = [MAIN_SEAT_RULE + ' -- the seat gate'] + [x for x in prop.get('gates_from', []) if 'MAIN' not in x and 'origin/main' not in x]
    (out_dir / 'seated-typing-ik.proposal.json').write_text(json.dumps(prop, indent=1, allow_nan=False) + '\n')
    return res


# ---------------------------------------------------------------- SitDown / GetUp: desk-clearance arm pass on a base
DESK_PASS_ITERATIONS = 40
DESK_PASS_STEP_MARGIN_CM = .1


def box_push(points, lo, hi, no_down=False):
    """Unit direction that moves each point out of (or away from) the box along the shortest way. no_down: a point
    inside never leaves through the bottom face (an arm reaches a desk part from above: a finger halfway into the
    3.04 cm worktop is pushed up or out of a side, never down through the slab)."""
    p = np.asarray(points, float)
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    q = np.clip(p, lo, hi)
    out = p - q
    n = np.linalg.norm(out, axis=-1)
    inside = n < 1e-9
    dirs = np.where(inside[..., None], 0., out / np.maximum(n, 1e-12)[..., None])
    if inside.any():
        pin = p[inside]
        d = np.concatenate([pin - lo, hi - pin], axis=-1)            # distance to each face
        if no_down:
            d[:, 2] = np.inf
        k = d.argmin(-1)
        v = np.zeros((len(pin), 3))
        v[np.arange(len(pin)), k % 3] = np.where(k < 3, -1., 1.)
        dirs[inside] = v
    return dirs


SEAM_TAPER_S = .2              # corrections reach zero at a protected / seam frame over this time (quintic, C1)


def seam_taper(F, frames, dt, taper_s=SEAM_TAPER_S):
    """(F,) weight: 0 at the given frames, smootherstep up to 1 at taper_s away from the nearest of them."""
    m = max(1, int(round(taper_s / dt)))
    idx = np.arange(F)
    dist = np.min(np.abs(idx[:, None] - np.asarray(frames)[None, :]), axis=1)
    return smootherstep(np.clip(dist / m, 0., 1.))


def desk_clear_arms(ctx, W, shift, times, protect, sides=SIDES, no_down=False, taper_s=0.):
    """Whole-arm desk-clearance pass (SitDown / GetUp): wherever arm skin (upper arm, forearm, hand, fingers) is closer
    than FOREARM_TARGET_CLEARANCE_CM to a real LINEA part, the wrist moves out of the part along the shortest way
    (smoothly over time), with non-stretch two-bone IK, the elbow pole carried with the hand, the captured hand WORLD
    rotation (the natural reach attitude) and the fingers carried (captured curls). Frames in `protect` (the settled
    frames that ARE the validated loop) never move; the correction tapers to them. Returns the pose and a summary."""
    F = len(times)
    dt = float(np.median(np.diff(times))) if F > 1 else 1 / 30
    protect = np.asarray(protect, bool)
    taper = seam_taper(F, np.nonzero(protect)[0], dt, taper_s) if taper_s and protect.any() else (~protect).astype(float)
    W0 = np.array(W, copy=True)
    disp = {s: np.zeros((F, 3)) for s in sides}            # UE cm
    hist = []

    def apply(disp):
        Wc = np.array(W0, copy=True)
        for s in sides:
            if not disp[s].any():
                continue
            a_, b_, c_ = (ctx.sk.j(n) for n in ARM_BONES[s])
            g = gltf_shift(disp[s])
            Wc, _, _, _, _ = solve_arm(ctx.sk, Wc, s, W0[:, c_, :3, 3] + g, W0[:, b_, :3, 3] + .5 * g, ctx.base.ibm,
                                       hand_world=W0[:, c_, :3, :3], limit=False)
        return Wc
    Wc = W0
    for it in range(DESK_PASS_ITERATIONS):
        more = False
        for s in sides:
            pos, jts, wts = ctx.arms[s]['skin']             # every arm skin vertex (the gate's own sampling)
            pts = E.to_ue(lbs((pos, jts, wts), ctx.base.ibm, Wc)) + shift[:, None, :]
            d, which = boxes_min_distance(pts, ctx.boxes, reach_cm=SEARCH_REACH_CM)
            k = d.argmin(1)
            dmin = d[np.arange(F), k]
            bad = (dmin < FOREARM_TARGET_CLEARANCE_CM) & ~protect
            hist.append({'iter': it, 'side': s, 'frames_below_target': int(bad.sum()), 'min_cm': _r(dmin.min(), 4)})
            if not bad.any():
                continue
            more = True
            f = np.nonzero(bad)[0]
            b = which[f, k[f]]
            lo, hi = ctx.boxes[b, 0], ctx.boxes[b, 1]
            dirs = np.stack([box_push(pts[i, k[i]][None], lo[j], hi[j], no_down)[0] for j, i in enumerate(f)])
            need = (FOREARM_TARGET_CLEARANCE_CM - dmin[f] + DESK_PASS_STEP_MARGIN_CM)[:, None] * dirs
            step = np.zeros((F, 3))
            step[f] = need
            for a in range(3):                             # smooth in time, never below a frame's own need
                pos_, neg_ = np.maximum(step[:, a], 0), np.maximum(-step[:, a], 0)
                step[:, a] = envelope(pos_, dt) - envelope(neg_, dt)
            step *= taper[:, None]                         # zero at (and smoothly into) the protected frames
            disp[s] += step
        if not more:
            break
        Wc = apply(disp)
    return Wc, {'iterations': len(hist) // len(sides), 'history_tail': hist[-4:],
                'wrist_displacement_cm': {s: {'max': _r(np.linalg.norm(v, axis=1).max(), 4),
                                              'frames_moved': [int(i) for i in np.nonzero(np.linalg.norm(v, axis=1) > 1e-9)[0]]}
                                          for s, v in disp.items()},
                'protected_frames': [int(i) for i in np.nonzero(protect)[0]]}


def measure_base_clip(ctx, role, W, W_raw, times, shift, chair_offset, gated, W_base=None):
    """Gates of a non-typing seated clip on the given chair: desk clearance of the whole body (arms every vertex, legs
    and torso), the complete chair (margin), main's strong seat rule on the gated settled frames, all-frame finger
    invariance, bone lengths; wrist angles and elbows reported."""
    F = len(times)
    pf = {'t': [_r(t, 4) for t in times]}
    arms = {}
    allmin = np.full(F, np.inf)
    for s in SIDES:
        pos, jts, wts = ctx.arms[s]['skin']
        part = ctx.arms[s]['part']
        pts = E.to_ue(lbs((pos, jts, wts), ctx.base.ibm, W)) + shift[:, None, :]
        d, _ = boxes_min_distance(pts, ctx.boxes, reach_cm=MEASURE_REACH_CM)
        per = {pp: d[:, part == pp].min(1) for pp in ('upper_arm', 'forearm', 'hand', 'fingers')}
        m = np.min(list(per.values()), axis=0)
        allmin = np.minimum(allmin, m)
        fl, dv, _ = wrist_angles(W, ctx.base.names, ctx.base.ibm, s)
        el = E.to_ue(W[:, ctx.sk.j(ARM_BONES[s][1]), :3, 3]) + shift
        pf[f'{s}_arm_desk_clearance_cm'] = [_r(v, 3) for v in m]
        pf[f'{s}_elbow_height_cm'] = [_r(v, 2) for v in el[:, 2]]
        pf[f'{s}_wrist_flexion_deg'] = [_r(v, 2) for v in fl]
        pf[f'{s}_wrist_deviation_deg'] = [_r(v, 2) for v in dv]
        arms[s] = {'desk_clearance_pass': bool((m > 0).all()), **{f'min_{pp}_cm': worst_frame(v, times) for pp, v in per.items()},
                   'wrist_flexion_deg': rng(fl, 2), 'wrist_deviation_deg': rng(dv, 2)}
    pos, jts, wts = ctx.body_skin
    body = {k: np.full(F, np.inf) for k in ('legs', 'torso_head')}
    chair_m = np.full(F, np.inf)
    for f in range(F):
        pts = E.to_ue(lbs((pos, jts, wts), ctx.base.ibm, W[f:f + 1]))[0] + shift[f]
        d, _ = boxes_min_distance(pts, ctx.boxes, reach_cm=MEASURE_REACH_CM)
        for k in body:
            body[k][f] = d[ctx.body_group == k].min()
        chair_m[f] = ctx.collider.margin(pts, chair_offset[f])[0].min()
    pf['body_vs_complete_chair_margin_cm'] = [_r(v, 3) for v in chair_m]
    fit = ctx.seat_fit(W_raw, times, ROLL_OFFSET_CM)
    gated = np.asarray(gated, bool)
    main_rule = main_strong_seat_rule(fit, W[gated], np.asarray(times)[gated]) if gated.any() else {'pass': True, 'regions': {}}
    # fingers: this step never changes them; gated against the BASE clip on every frame (the base's own seam windows
    # blend its fingers into SeatedIdle, so the change vs the raw capture is reported, not gated here)
    fingers = finger_contract(ctx, W, W_raw if W_base is None else W_base, times)
    fingers['reference'] = 'raw capture' if W_base is None else 'the seated base clip'
    fingers['vs_raw_capture_max_deg'] = _r(P.finger_local_error_deg(ctx.sk, W_raw, W, np.eye(4)), 4)
    bl = max(abs(np.linalg.norm(W[:, k, :3, 3] - W[:, p_, :3, 3], axis=1) - np.linalg.norm(W_raw[:, k, :3, 3] - W_raw[:, p_, :3, 3], axis=1)).max()
             for k, p_ in enumerate(ctx.sk.parents) if p_ >= 0) * 100
    out = {'frames': F, 'gated_frames': int(gated.sum()), 'arms': arms,
           'arm_desk_clearance': worst_frame(allmin, times), 'arm_desk_clearance_pass': bool((allmin > 0).all()),
           'body_vs_desk': {k: worst_frame(v, times) for k, v in body.items()},
           'body_vs_desk_pass': bool(all((v > 0).all() for v in body.values())),
           'body_vs_complete_chair': worst_frame(chair_m, times), 'body_vs_chair_pass': bool((chair_m > 0).all()),
           'seat_main_strong_rule_on_gated_frames': main_rule, 'fingers': fingers, 'bone_length_max_error_cm': _r(bl, 7)}
    out['all_gates_pass'] = bool(out['arm_desk_clearance_pass'] and out['body_vs_desk_pass'] and out['body_vs_chair_pass']
                                 and main_rule['pass'] and fingers['pass'] and bl <= .01)
    out['per_frame'] = pf
    return out


def run_base_transitions(args):
    """SitDown / GetUp on the seated base (--base-dir) at the given chair: the desk-clearance arm pass, written and
    re-read; SeatedIdle measured unchanged; seams to SeatedIdle. Writes into --out-dir."""
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx = Context(args.source, cache=args.cache, chair_translation=args.chair_translation, keycaps=args.keycaps)
    r0 = np.array([*ROLL_OFFSET_CM, 0.])
    reports, worlds = {}, {}
    for role in ('SeatedIdle', 'SitDown_seated', 'GetUp_seated'):
        f_c, r_c, g_c, t_c = ctx.clip(role)
        F = len(t_c)
        shift = np.tile(-r0, (F, 1))                # the body on the (unrolled) chair: actual placement
        chair_off = np.zeros((F, 3))
        base_rep = json.loads((Path(FIT_DIR) / f'SUB01_{role}.report.json').read_text())
        gi = base_rep.get('main_rule', {}).get('gated_frame_indices')
        gated = np.zeros(F, bool)
        gated[gi if gi is not None else slice(None)] = True
        W = f_c.joint_world
        info = None
        if role != 'SeatedIdle':
            W, info = desk_clear_arms(ctx, W, shift, t_c, gated)
            path, sha = write(ctx, g_c, W, t_c, out_dir, f'SUB01_{role}', dict(LABELS, role=role, base=rel(Path(FIT_DIR))))
            W = readback(ctx, path, t_c)
        else:
            path = Path(FIT_DIR) / f'SUB01_{role}.glb'
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
        rep = {'role': role, 'glb': rel(path), 'sha256': sha, 'base_glb': rel(Path(FIT_DIR) / f'SUB01_{role}.glb'),
               'base_sha256': hashlib.sha256((Path(FIT_DIR) / f'SUB01_{role}.glb').read_bytes()).hexdigest(),
               'raw_capture': CLIPS[role][1], 'unchanged_from_base': role == 'SeatedIdle', 'desk_clear_pass': info,
               'measure': measure_base_clip(ctx, role, W, r_c.joint_world, t_c, shift, chair_off, gated, W_base=f_c.joint_world)}
        rep['all_gates_pass'] = rep['measure']['all_gates_pass']
        reports[role], worlds[role] = rep, (W, shift, t_c)
        print(role, rep['all_gates_pass'], flush=True)
    seams = []
    for a, b in (('SitDown_seated', 'SeatedIdle'), ('SeatedIdle', 'GetUp_seated')):
        Wa, sa, ta = worlds[a]
        Wb_, sb, tb = worlds[b]
        seams.append({'from': f'{a}.last', 'to': f'{b}.first',
                      **seam(ctx, Wa, sa, Wb_, sb, 1. / float(np.median(np.diff(ta))), 1. / float(np.median(np.diff(tb))))})
    for k, v in reports.items():
        (out_dir / f'SUB01_{k}.report.json').write_text(json.dumps(v, indent=1, allow_nan=False) + '\n')
    return reports, seams, ctx


def base_transitions_packet(args):
    """Run the SitDown/GetUp arm pass on the base and write <out-dir>/seated-arms.packet.json (ready stays false)."""
    reports, seams, ctx = run_base_transitions(args)
    base_dir = Path(FIT_DIR)
    packet = {'schema': 'sub01.seated-arms-on-base.v1', **LABELS, 'ready': False, 'native_verified': False,
              'installer_or_readiness_written': False,
              'base': {'dir': rel(base_dir), 'solver_frame_chair_offset_cm': list(ROLL_OFFSET_CM),
                       'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(base_dir.glob('*.glb'))}},
              'chair': {k: ctx.chair[k] for k in ('file', 'sha256', 'translation_cm', 'measured_translation_cm', 'proposed_delta_cm',
                                                  'rotation_xyzw', 'scale')},
              'complete_chair': {k: v for k, v in ctx.complete_chair.items() if k not in ('triangles_cm', 'face_normals', 'material', 'vertices_cm')},
              'desk_geometry': {'file': rel(GEOMETRY_JSON), 'sha256': ctx.geometry_sha256, 'source_sha256': LINEA_SHA256},
              'models': {'owner': {'file': rel(E.OWNER), 'sha256': hashlib.sha256(Path(E.OWNER).read_bytes()).hexdigest()},
                         'chair': {'file': rel(CHAIR_SOURCE), 'sha256': CHAIR_SOURCE_SHA256}},
              'gates_from': [MAIN_SEAT_RULE + ' (seat, on the base\'s gated settled frames)',
                             'real LINEA part boxes: whole-arm and body clearance > 0 on EVERY frame',
                             'complete chair margin > 0 every frame', 'fingers unchanged vs the base on every frame (<= 0.1 deg)'],
              'clips': {k: {'glb': v['glb'], 'sha256': v['sha256'], 'base_sha256': v['base_sha256'], 'all_gates_pass': v['all_gates_pass'],
                            'arm_desk_clearance': v['measure']['arm_desk_clearance'],
                            'body_vs_complete_chair': v['measure']['body_vs_complete_chair'],
                            'seat_main_strong_rule_on_gated_frames': v['measure']['seat_main_strong_rule_on_gated_frames']['pass'],
                            'fingers_pass': v['measure']['fingers']['pass'],
                            'wrist_displacement_cm': (v['desk_clear_pass'] or {}).get('wrist_displacement_cm')}
                        for k, v in reports.items()},
              'seams': seams}
    packet['gates'] = {f'clip_{k}': v['all_gates_pass'] for k, v in reports.items()}
    Path(args.out_dir, 'seated-arms.packet.json').write_text(json.dumps(packet, indent=1, allow_nan=False) + '\n')
    return packet


def base_upper_body_shift_y(ctx):
    """Mean UE Y of the base DeskTyping Spine2 minus the seat-fit DeskTyping Spine2 over the 3..8 s audit window."""
    t = list(np.arange(AUDIT_KEYS[0], AUDIT_KEYS[1] + 1, 10) / 60)
    a, _ = P.clip_source(ctx.base, Path(FIT_DIR) / CLIPS['DeskTyping_seated'][0], t)
    b, _ = P.clip_source(ctx.base, ROOT / 'docs/proposed/seat-pose-fit' / CLIPS['DeskTyping_seated'][0], t)
    j = ctx.sk.j('Spine2')
    return -round(float((E.to_ue(a.joint_world[:, j, :3, 3]) - E.to_ue(b.joint_world[:, j, :3, 3]))[:, 1].mean()), 3)


def configure(base_dir=None, base_chair_offset=None):
    """Warm-start inputs: the seated base clip directory and its solver-frame chair offset."""
    global FIT_DIR, ROLL_OFFSET_CM
    if base_dir is not None:
        FIT_DIR = Path(base_dir) if Path(base_dir).is_absolute() else ROOT / base_dir
    if base_chair_offset is not None:
        ROLL_OFFSET_CM = tuple(map(float, base_chair_offset))
    return FIT_DIR, ROLL_OFFSET_CM


EXIT_REFUSED = 3


def exit_code(summary):
    """0 only when every aggregate gate passed (summary['ready']); EXIT_REFUSED otherwise (the report is still written)."""
    return 0 if summary.get('ready') is True and all(summary.get('gates', {False: False}).values()) else EXIT_REFUSED


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--source', default=str(ROOT / 'private-audit/seat-fit-source.npz'))
    ap.add_argument('--cache', default=str(ROOT / 'out/seat-fit-cache'))
    ap.add_argument('--out-dir', default=str(OUT_DIR))
    ap.add_argument('--base-dir', default=str(FIT_DIR), help='seated base clips SUB01_<role>.glb (warm start), e.g. '
                    'docs/proposed/seat-pose-anatomical')
    ap.add_argument('--base-chair-offset', type=lambda v: tuple(float(x) for x in v.split(',')), default=None,
                    help='dx,dy: chair offset (from the initial chair) of the base clips\' solver frame (default the seat fit\'s)')
    ap.add_argument('--chair-translation', type=lambda v: [float(x) for x in v.split(',')], default=None,
                    help='x,y,z: the given INITIAL chair translation (default root\'s measured one), e.g. a proposed lift')
    ap.add_argument('--keycaps', default=None, help='keyboard-keycaps-world.json keyboard IK targets (default: home.js keyboard)')
    ap.add_argument('--arms-only', action='store_true', help='only the arm chains may change: no full-pose seam blends; the '
                    'lower body / pelvis are gated identical to the base')
    ap.add_argument('--roll-from-base', action='store_true', help='extra pull-in = minus the base\'s upper-body Y shift vs the '
                    'seat-fit base (keeps the validated upper body - keyboard relation)')
    ap.add_argument('--roll-dy', type=float, default=None, help='fixed extra pull-in (skips the probe scan)')
    ap.add_argument('--base-transitions', action='store_true', help='SitDown/GetUp desk-clearance arm pass on --base-dir '
                    '(SeatedIdle measured unchanged); writes the clips and seated-arms.packet.json into --out-dir')
    ap.add_argument('--audit-main-seat-rule', action='store_true', help='gate the committed clips\' seat base with main\'s '
                    'strong seat rule and update the reports (no solve)')
    ap.add_argument('--max-seconds', type=float, default=3600., help='wall-clock bound; a partial, ready:false report is '
                    'written when it is reached between stages')
    ap.add_argument('--resume', action='store_true', help='reuse the bounded run\'s committed DeskTyping stage (sha256 '
                    'checked) and run the remaining stages')
    ap.add_argument('--quick', action='store_true', help='smoke run on a DeskTyping subset (never a proposal)')
    ap.add_argument('--desk-source', help='LINEA140 source GLB: re-derive docs/proposed/seated-typing-ik/real-linea140-geometry.json')
    args = ap.parse_args(argv)
    configure(args.base_dir, args.base_chair_offset)
    global ARMS_ONLY
    ARMS_ONLY = bool(args.arms_only)
    if args.base_transitions:
        packet = base_transitions_packet(args)
        print(json.dumps(packet['gates']))
        return EXIT_REFUSED if not all(packet['gates'].values()) else 0
    if args.audit_main_seat_rule:
        res = audit_main_seat_rule(args.out_dir, args.source, args.cache)
        print(json.dumps({k: v['pass'] for k, v in res.items()}))
        return EXIT_REFUSED if not all(v['pass'] for v in res.values()) else 0
    if args.desk_source:
        GEOMETRY_JSON.parent.mkdir(parents=True, exist_ok=True)
        GEOMETRY_JSON.write_text(json.dumps(desk_geometry(args.desk_source), indent=1) + '\n')
    summary, _ = run(args)
    print(json.dumps({'ready': summary.get('ready'), 'gates': summary.get('gates'), 'partial': summary.get('partial'),
                      'bounded': summary.get('bounded')}, indent=1))
    return exit_code(summary)


if __name__ == '__main__':
    sys.exit(main())
