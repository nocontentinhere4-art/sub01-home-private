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


def solve_arm(sk, W, side, target, pole, ibm, hand_world=None, D=None, limit=True):
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
CONTACT_PASSES, CONTACT_TOL_CM = 8, 1e-4
FOREARM_TARGET_CLEARANCE_CM = .5     # design target for arm skin to the real desk (the gate is > 0, every frame)
SWIVEL_GRID_DEG = tuple(float(v) for v in np.arange(0., 120.01, 2.5))
SWIVEL_COARSE_STEP_DEG = 10.
SWIVEL_COARSE_DEG = tuple(float(v) for v in np.arange(0., SWIVEL_GRID_DEG[-1] + .01, SWIVEL_COARSE_STEP_DEG))
SEARCH_CONTACT_PASSES = 4
SWIVEL_ENVELOPE_S, SWIVEL_SMOOTH_S = .15, .1       # the seat fit's own envelope/smoothing rule (max filter, Gaussian)
LIFT_STEP_CM, LIFT_MAX_CM = .25, 15.
ROLL_OFFSET_CM = (3.875, -32.5)      # the seat fit's chair offset (docs/proposed/seat-pose-fit, chosen dy -32.5)
SEARCH_REACH_CM = FOREARM_TARGET_CLEARANCE_CM + 1.5
CLEARANCE_STRIDE = 3                 # arm skin sampling for the search; reports use every vertex


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


class ClipArmIK:
    """Whole-arm IK on one seated clip. W_fit: the seat-fitted clip's joint worlds (solver frame = the rolled world);
    W_raw: the raw capture at the same times (wrist relative rotation and elbow pole). body_shift_cm (F, 3): the body's
    UE offset from the rolled placement at each frame (the roll still to go; zero once rolled)."""

    def __init__(self, base, W_fit, W_raw, times, keys, cushion_tri, arm_skins, geometry, body_shift_cm=None,
                 contact=True, roll=ROLL_OFFSET_CM, finger_xy_target=None, on_mask=None):
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
        # Horizontal fingertip targets (UE world XY per frame): the seat fit's own distal finger skin centroid, i.e. the
        # captured horizontal hand path the existing contact pipeline placed over the keycaps. The wrist target gets a
        # per-frame horizontal correction (self.hand_xy, glTF metres) so the IK hand lands on the same keycaps.
        self.finger_xy_target = finger_xy_target
        self.on_mask = on_mask
        self.hand_xy = {s: np.zeros((F, 3)) for s in SIDES}

    # --- measurements (UE cm, at each frame's actual body placement)
    def arm_points(self, W, side, stride=1, frames=None, posed_frames=False):
        pos, jts, wts = self.arm_skins[side]['skin']
        part = self.arm_skins[side]['part']
        sel = slice(None, None, stride)
        Wf = W if (frames is None or posed_frames) else W[frames]
        shift = self.body_shift if frames is None else self.body_shift[frames]
        pts = E.to_ue(P.skin_points((pos[sel], jts[sel], wts[sel]), self.ibm, Wf)) + shift[:, None, :]
        return pts, part[sel]

    def clearance(self, W, side, stride=1, frames=None, reach=None, posed_frames=False):
        pts, part = self.arm_points(W, side, stride, frames, posed_frames)
        d, which = boxes_min_distance(pts, self.boxes, reach)
        return d.min(axis=1), d, which, pts, part

    def key_audit(self, W, frames=None):
        """The existing keyboard rule at each frame's actual body placement (hands translated with the body)."""
        shift = self.body_shift if frames is None else self.body_shift[frames]
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

    def pose(self, W, side, delta_cm, phi_rad, lift_cm=None, frames=None):
        A, pole, wrist, hand_world, _ = self.inputs[side]
        if frames is not None:
            A, pole, wrist, hand_world = A[frames], pole[frames], wrist[frames], hand_world[frames]
        hxy = self.hand_xy[side] if frames is None else self.hand_xy[side][frames]
        tgt = wrist + hxy + UP * (np.asarray(delta_cm) + (0. if lift_cm is None else np.asarray(lift_cm)))[:, None] / 100.
        sign = self.raise_sign[side] if frames is None else self.raise_sign[side][frames]
        p = swivel_pole(A, tgt, pole, np.asarray(phi_rad) * sign)
        W, reach, length, dist, _ = solve_arm(self.sk, W.copy(), side, tgt, p, self.ibm, hand_world=hand_world)
        return W, reach, length, dist

    def solve(self):
        """Per side and frame: contact first (swivel 0), then the smallest elbow swivel (grid, raising the elbow) whose
        contact-resolved pose keeps every arm skin vertex FOREARM_TARGET_CLEARANCE_CM from the real desk; the swivel is
        then a smooth upper envelope over time and the contact is re-solved. Off-key frames that no swivel clears lift
        the hand; on-key frames that no swivel clears keep the best swivel and are reported (never hidden)."""
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
        delta = {s: zero.copy() for s in SIDES}
        phi = {s: zero.copy() for s in SIDES}
        lift = {s: zero.copy() for s in SIDES}
        history = []
        for s in SIDES:
            delta[s] = self.solve_contact_side(s, delta[s], phi[s], lift[s])
            for outer in range(3):
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
                off = bad[todo][~self.on[s][bad[todo]]]
                if len(off):                                      # off-key: lift the hand (no key contact required)
                    lift[s] = np.maximum(lift[s], self.lift_need(s, delta[s], phi[s], lift[s], off))
                    delta[s] = self.solve_contact_side(s, delta[s], phi[s], lift[s])
        W = self.W_fit.copy()
        for s in SIDES:
            W = self.pose(W, s, delta[s], phi[s], lift[s])[0]
        self.delta, self.phi, self.lift, self.history = delta, phi, lift, history
        return W

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
        return envelope(out, self.dt)

    def solve_contact_side(self, s, delta, phi, lift, frames=None, passes=CONTACT_PASSES):
        """Vertical wrist correction so the over-key distal skin minimum sits at KeyTop + 0.08 cm on every on-key frame
        (iterated: the hand rides on the forearm, so its orientation follows the IK), and the horizontal correction that
        keeps the distal finger centroid on the fit's hand path. Off-key frames start from the time interpolation of the
        neighbouring on-key corrections (the hand travels at typing height) and are only ever lifted, so a hand passing
        over the keyboard never enters the keycaps."""
        top = self.keys['top_cm'] + KEY_TOP_TARGET_CM
        delta = delta.copy()
        fr = np.arange(len(self.times)) if frames is None else np.asarray(frames)
        on = self.on[s][fr]
        if frames is None and self.on[s].any():
            idx = np.nonzero(self.on[s])[0]
            delta[~self.on[s]] = np.interp(np.nonzero(~self.on[s])[0], idx, delta[idx])
        for _ in range(passes):
            Wt = self.pose(self.W_fit[fr].copy(), s, delta[fr], phi[fr], lift[fr], fr)[0]
            hres = 0.
            if self.finger_xy_target is not None:
                cen = self.trial.skin_ue(f'{s}_fingers', Wt)[0].mean(axis=1)[:, :2] + self.body_shift[fr][:, :2]
                dxy = self.finger_xy_target[s][fr] - cen
                self.hand_xy[s][fr] += gltf_shift(np.c_[dxy, np.zeros(len(fr))])
                hres = float(np.abs(dxy).max())
                Wt = self.pose(self.W_fit[fr].copy(), s, delta[fr], phi[fr], lift[fr], fr)[0]
            a = self.key_audit(Wt, fr)[s]
            res = np.where(on, top - a['over_min'], np.where(a['over'] > 0, np.maximum(top - a['over_min'], 0.), 0.))
            res = np.where(np.isfinite(res), res, 0.)
            delta[fr] = delta[fr] + res
            if np.abs(res).max() < CONTACT_TOL_CM and hres < CONTACT_TOL_CM * 10:
                break
        return delta


# ---------------------------------------------------------------- the chair roll ACTIVITY (declared, reversible)
CHAIR_REPORT = ROOT / 'docs/proposed/native-chair-measured/20261014-actual-native-chair-surface.json'


def smootherstep(x):
    x = np.clip(np.asarray(x, float), 0., 1.)
    return x * x * x * (x * (6 * x - 15) + 10)


def load_chair(path=CHAIR_REPORT):
    """The measured native chair: transform (the INITIAL state, never changed), shell vertices and cushion triangles."""
    path = Path(path)
    rep = json.loads(path.read_text())
    ch = rep['chair']
    verts = np.concatenate([np.asarray(s['vertices_world_cm'], float) for s in ch['sections']])
    return {'file': rel(path) if path.is_relative_to(ROOT) else str(path),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'translation_cm': list(map(float, ch['transform']['translation_cm'])),
            'rotation_xyzw': ch['transform']['rotation_xyzw'], 'scale': ch['transform']['scale'],
            'component_world_bounds_cm': ch['component_world_bounds_cm'], 'shell_vertices_cm': verts,
            'cushion_triangles_cm': np.asarray(seat_contact.cushion_triangles(rep), float).reshape(-1, 3, 3)}


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
    """Signed distance of points to the complete chair at a roll offset: exact distance to the nearest of the K_TRI
    nearest-centroid triangles, signed by that triangle's outward normal (negative = inside). Upholstery may be pressed
    in down to the seat band's lower edge (SEAT_BAND_CM[0], the cushion compression the seat gates allow); every other
    part (plastic frame and arms, arm pads, back mesh, base, castors, gas lift) allows no penetration."""
    K_TRI, REACH_CM = 8, 15.

    def __init__(self, complete):
        from scipy.spatial import cKDTree
        self.c = complete
        self.cen = complete['triangles_cm'].mean(1)
        self.tree = cKDTree(self.cen)
        self.allow = np.where(np.isin(complete['material'], UPHOLSTERY), seat_contact.SEAT_BAND_CM[0], 0.)

    def margin(self, points, offset):
        """(signed distance - allowed depth) per point (REACH_CM where no triangle is near), and the nearest material."""
        shape = np.shape(points)[:-1]
        p = np.asarray(points, float).reshape(-1, 3) - np.asarray(offset, float)
        m = np.full(len(p), self.REACH_CM)
        mat = np.full(len(p), '', dtype=object)
        d0, _ = self.tree.query(p, distance_upper_bound=self.REACH_CM + 10.)
        near = np.nonzero(np.isfinite(d0))[0]
        if len(near):
            _, ii = self.tree.query(p[near], k=self.K_TRI)
            T_ = self.c['triangles_cm']
            best, arg = np.full(len(near), np.inf), np.zeros(len(near), int)
            for k in range(self.K_TRI):
                tri = T_[ii[:, k]]
                d = point_triangle_distance(p[near], tri[:, 0], tri[:, 1], tri[:, 2])
                better = d < best
                best[better], arg[better] = d[better], ii[better, k]
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
        bones = [sk.j(n) for n in ARM_BONES[s]]
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


def gltf_shift(shift_ue):
    return np.stack([P.ue_delta_to_gltf(v) for v in np.asarray(shift_ue, float)])


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


class Context:
    """Everything shared by the clips: source, real desk, chair, keys, skins."""

    def __init__(self, source, geometry=GEOMETRY_JSON, cache=None):
        self.base = E.Source.load(source)
        self.geometry = load_geometry(geometry)
        self.geometry_sha256 = hashlib.sha256(Path(geometry).read_bytes()).hexdigest()
        self.boxes, self.box_nodes = desk_boxes(self.geometry)
        self.chair = load_chair()
        self.tri = self.chair['cushion_triangles_cm']
        self.complete_chair = load_complete_chair(self.chair, cache)
        self.collider = ChairCollider(self.complete_chair)
        self.finger_joints = [k for k, n in enumerate(self.base.names) if any(f in n for f in FINGERS)]
        self.keys = T.keycaps_from_glb()
        self.arms = arm_skin(self.base.names, stride=1, cache=cache)
        self.body_skin = P.owner_skin(stride=BODY_SKIN_STRIDE, cache=cache)
        dom = self.body_skin[1][np.arange(len(self.body_skin[1])), self.body_skin[2].argmax(1)]
        g = body_parts(self.base.names)
        self.body_group = np.array([g[int(j)] for j in dom])
        self.sk = T.Skeleton(self.base)

    def clip(self, role, times=None):
        fit, raw = CLIPS[role]
        src_f, g_f = P.clip_source(self.base, FIT_DIR / fit, times)
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
        return ClipArmIK(self.base, W_fit, W_raw, times, self.keys, self.tri, self.arms, self.geometry,
                         body_shift_cm=shift, contact=contact, finger_xy_target=target, on_mask=on)

    def seat_fit(self, W_raw, times, chair_offset):
        d = dict(self.base.d)
        d['joint_world'], d['times'] = W_raw, np.asarray(times, float)
        return P.SeatFit(E.Source(d), self.tri, self.keys, tuple(chair_offset))


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


def measure(ctx, role, W, W_raw, times, shift, chair_offset_world, ik=None, key_seam=None, finger_frames=None,
            finger_seams=()):
    """Every gate and metric on the given (read-back) pose, every frame. Solver frame: body at the audited transform,
    chair at measured + ROLL_OFFSET_CM. World at frame f: the body moved by shift[f] (UE cm), the chair at the measured
    transform + chair_offset_world[f]. Seat/sole gates are chair-relative (chair and body roll rigidly together), so they
    are measured in the solver frame AND re-measured literally at the final rolled position."""
    F = len(times)
    out = {'frames': F}
    fit = ctx.seat_fit(W_raw, times, ROLL_OFFSET_CM)
    g = P.gates(fit, W, None, seated=np.ones(F, bool), with_keys=False)
    out['seat_sole_gates_solver_frame'] = {k: g[k] for k in ('seat', 'soles', 'bone_length_max_error_cm',
                                                               'foot_world_rotation_max_change_deg', 'upper_body_world')}
    # literal re-measure at the final rolled position (constant part of the shift; rigid roll of chair + body)
    final = shift[-1] if key_seam is None or key_seam == len(times) - 1 else shift[0]
    fit_r = ctx.seat_fit(P.place_body(W_raw, final[:2]), times, np.asarray(ROLL_OFFSET_CM) + final[:2])
    g_r = P.gates(fit_r, P.place_body(W, final[:2]), None, seated=np.ones(F, bool), with_keys=False)
    out['seat_sole_gates_at_rolled_chair'] = {'chair_translation_cm': [_r(v) for v in np.asarray(ctx.chair['translation_cm']) + [*(np.asarray(ROLL_OFFSET_CM) + final[:2]), 0.]],
                                             'seat': g_r['seat'], 'soles': g_r['soles']}
    seat_pass = all(v['pass_all_frames'] for v in g['seat'].values()) and all(v['pass_all_frames'] for v in g['soles'].values())
    seat_pass_r = all(v['pass_all_frames'] for v in g_r['seat'].values()) and all(v['pass_all_frames'] for v in g_r['soles'].values())
    c = P.contact_per_frame(fit, W)
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
        else:
            ok = not bad_pen.any() and bool(over[key_seam]) and not bad_gap[key_seam]
            rule = f'contact at the seam frame {key_seam}; penetration <= 0.1 cm on every frame'
        keys_out[s] = {'pass': bool(ok), 'rule': rule, 'frames_over_keys': int(over.sum()),
                       'frames_on_keys_by_ik': int(ik.on[s].sum()) if ik is not None else None,
                       'gap_cm': rng(gap), 'worst_gap': worst_frame(gap, times, lowest=False),
                       'worst_penetration': worst_frame(gap, times, lowest=True),
                       'frames_gap_over_0_2cm': int(bad_gap.sum()), 'frames_penetration_over_0_1cm': int(bad_pen.sum())}
    out['keys'] = keys_out
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
            pts = E.to_ue(P.skin_points((pos, jts, wts), ctx.base.ibm, W[sl])) + shift[sl][:, None, :]
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
            'upper_arm_from_vertical_deg': rng(ua, 2), 'elbow_height_cm': rng(el[:, 2], 2)}
    out['arms'] = arms_out
    # whole body vs the real desk (knees / thighs / torso)
    pos, jts, wts = ctx.body_skin
    body_min = {k: np.full(F, np.inf) for k in ('legs', 'torso_head', 'arms')}
    for a in range(0, F, 40):
        sl = slice(a, a + 40)
        pts = E.to_ue(P.skin_points((pos, jts, wts), ctx.base.ibm, W[sl])) + shift[sl][:, None, :]
        d, _ = boxes_min_distance(pts, ctx.boxes, reach_cm=MEASURE_REACH_CM)
        for k in body_min:
            m = ctx.body_group == k
            body_min[k][sl] = d[:, m].min(1)
    for k in body_min:
        pf[f'body_{k}_desk_clearance_cm'] = [_r(v, 3) for v in body_min[k]]
    out['body_vs_desk'] = {k: worst_frame(v, times) for k, v in body_min.items()}
    out['body_vs_desk']['legs_and_torso_clear'] = bool((body_min['legs'] > 0).all() and (body_min['torso_head'] > 0).all())
    out['body_vs_desk']['sampling'] = f'every {BODY_SKIN_STRIDE}th owner skin vertex'
    out['seat_pass'] = bool(seat_pass)
    out['seat_pass_at_rolled_chair'] = bool(seat_pass_r)
    out['fingers'] = finger_contract(ctx, W, W_raw, times, finger_seams)
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
        pts = E.to_ue(P.skin_points((pos, jts, wts), ctx.base.ibm, W[f:f + 1]))[0] + shift[f]
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
                                 and out['chair']['body_vs_chair_pass'])
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
            out |= ik.clearance(Wb, side, CLEARANCE_STRIDE, frames, SEARCH_REACH_CM, posed_frames=posed)[0] \
                < FOREARM_TARGET_CLEARANCE_CM
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


def post_contact(ctx, ik, W, window, seam_frame=None):
    """After the DeskTyping-side seam blend (and with the captured finger curls kept on every frame), per side a smooth
    vertical wrist correction (non-stretch two-bone IK, current elbow as pole, current wrist-relative hand rotation,
    fingers carried) over the window: exact key contact (KeyTop + 0.08 cm) at the seam frame when that hand is over the
    keys there, tapered by the window weight, plus the smallest smooth lift that removes any keycap penetration or desk
    contact inside the window. Zero outside the window."""
    F = len(W)
    window = np.asarray(window, float)
    gate = window > 0
    top = ik.keys['top_cm']
    lift = {s: np.zeros(F) for s in SIDES}
    seam_d = {s: 0. for s in SIDES}
    W0 = np.array(W, copy=True)
    Wc = W0
    for _ in range(16):
        a = ik.key_audit(Wc)
        more = False
        for s in SIDES:
            need = np.where(gate & (a[s]['over'] > 0), np.maximum(0., top - a[s]['over_min']), 0.)
            cl = ik.clearance(Wc, s, CLEARANCE_STRIDE, reach=SEARCH_REACH_CM)[0]
            need = np.nan_to_num(np.maximum(need, np.where(gate & (cl < 0), LIFT_STEP_CM, 0.)))
            if seam_frame is not None:
                need[seam_frame] = 0.
                if a[s]['over'][seam_frame] >= KEY_MIN_OVER_VERTICES:
                    res = top + KEY_TOP_TARGET_CM - a[s]['over_min'][seam_frame]
                    if abs(res) > CONTACT_TOL_CM:
                        seam_d[s] += float(res)
                        more = True
            if need.any():
                more = True
                lift[s] = envelope(lift[s] + need, ik.dt) * gate
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
            for n in ARM_BONES[s]:
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
    W1, legs_idle = seam_blend_with_soles(ctx, A, W_fit, Tg, w_idle, r_c.joint_world, t_c)
    # arms: whole-arm IK, blended in along the roll
    contact_shift = shift_c[-1] if at_end else shift_c[0]
    ikc = ctx.ik(W1, r_c.joint_world, t_c, shift_c, contact_shift=contact_shift)
    W_ik = ikc.solve()
    W2, weights = transition_arms(ctx, ikc, W1, W_ik, s, w_idle)
    # DeskTyping side: the written DeskTyping first (SitToType) / last (TypeToSit) frame, held
    Td = np.repeat((W_dt[0] if at_end else W_dt[-1])[None], F, axis=0)
    w_dt = P.seam_weight('end', F, F - 1 - n, F - 1) if at_end else P.seam_weight('start', F, 0, n)
    W3, legs_dt = seam_blend_with_soles(ctx, A, W2, Td, w_dt, r_c.joint_world, t_c)
    # fingers keep THIS clip's captured curls on every frame (gate (a): all-frame invariance, no seam exemption); the
    # finger change at the clip boundary is then a seam jump, measured and reported in the seam table
    W3 = finger_override(ctx, W3, r_c.joint_world, [])
    W3, seam_lift = post_contact(ctx, ikc, W3, w_dt, seam_frame=F - 1 if at_end else 0)
    path, sha = write(ctx, g_c, W3, t_c, out_dir, f'SUB01_{role}', dict(LABELS, role=role))
    Wcb = readback(ctx, path, t_c)
    seam_frame = F - 1 if at_end else 0
    rep = {'role': role, 'glb': rel(path), 'sha256': sha, 'bytes': path.stat().st_size, 'keys': F,
           'input_fit_clip': f'docs/proposed/seat-pose-fit/{CLIPS[role][0]}', 'raw_capture': CLIPS[role][1],
           'chair_roll': roll.describe(t_c, s) | {'activity': 'pull chair in' if at_end else 'push chair back'},
           'seam_windows': {'seated_idle_side_weight': [_r(v, 4) for v in w_idle], 'desk_typing_side_weight': [_r(v, 4) for v in w_dt],
                            'window_frames': n, 'fingers': 'captured curls kept on every frame (all-frame invariance gate)',
                            'legs': {'seated_idle_side': legs_idle, 'desk_typing_side': legs_dt},
                            'desk_typing_side_wrist_contact': seam_lift},
           'arm_weights': weights, 'ik_history': ikc.history,
           'measure': measure(ctx, role, Wcb, r_c.joint_world, t_c, shift_c, off, ikc, key_seam=seam_frame,
                              finger_seams=())}
    rep['all_gates_pass'] = bool(rep['measure']['all_gates_pass'])
    return rep, Wcb, shift_c, t_c


def run(args):
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx = Context(args.source, cache=args.cache)
    T0 = np.asarray(ctx.chair['translation_cm'], float)
    r0 = np.array([*ROLL_OFFSET_CM, 0.])
    summary = {'schema': SCHEMA, **LABELS, 'geometry': {'file': str(GEOMETRY_JSON.relative_to(ROOT)), 'sha256': ctx.geometry_sha256,
                                                         'source_sha256': LINEA_SHA256, **{k: ctx.geometry[k] for k in (
                                                             'provenance', 'overall_dims_cm', 'floor_cm', 'tabletop_slab',
                                                             'front_apron', 'knee_bay_cm', 'grommet_rim_top_cm')}},
               'chair': {k: ctx.chair[k] for k in ('file', 'sha256', 'translation_cm', 'rotation_xyzw', 'scale',
                                                     'component_world_bounds_cm')},
               'keyboard': {'source': ctx.keys['source'], 'key_top_cm': _r(ctx.keys['top_cm']), 'keycaps': ctx.keys['keycaps'],
                            'key_field_min_cm': [_r(v, 3) for v in ctx.keys['key_min']],
                            'key_field_max_cm': [_r(v, 3) for v in ctx.keys['key_max']],
                            'root_home_keyboard_nodes_184_187_xy_cm': [[181.45, -302.0464], [218.55, -285.9536]],
                            'provenance': 'repo web/house/home.js furnished("keyboard", 2, .846, -2.94, .371) = the home\'s '
                                          'keyboard source nodes 184-187 in root\'s LINEA record (same XY footprint): the '
                                          'keyboard did not move with the new desk'},
               'gates_from': ['tools/validate_unreal_seat_contact.py (SEAT_BAND_CM, SOLE_BAND_CM, MIN_PATCH_VERTICES, '
                              'MIN_SUPPORT_VERTICES)', 'tools/validate_unreal_contact_profile.py (KEY_GAP_MAX_CM, validate())',
                              'tools/fit_seat_pelvis_pitch.py gates() / contact_per_frame()'],
               'constants': {'key_contact_target_cm': KEY_TOP_TARGET_CM, 'key_gap_max_cm': contact_profile.KEY_GAP_MAX_CM,
                             'key_penetration_max_cm': P.KEY_PENETRATION_MAX_CM, 'seat_band_cm': list(seat_contact.SEAT_BAND_CM),
                             'sole_band_cm': list(seat_contact.SOLE_BAND_CM), 'min_support_vertices': seat_contact.MIN_SUPPORT_VERTICES,
                             'forearm_target_clearance_cm': FOREARM_TARGET_CLEARANCE_CM, 'desk_clearance_gate': '> 0 cm every frame',
                             'wrist_soft_flexion_deg': list(WRIST_SOFT_FLEX_DEG), 'wrist_soft_deviation_deg': list(WRIST_SOFT_DEV_DEG),
                             'wrist_note': 'soft targets (smooth saturation), never gates'}}
    # ---- roll: the seat fit's chair offset plus the scanned extra pull-in
    f_dt, r_dt, g_dt, t_dt = ctx.clip('DeskTyping_seated')
    pick, scan = roll_scan(ctx, f_dt, r_dt, t_dt, dys=(0.,) if args.quick else ROLL_SCAN_DY_CM)
    if args.quick:                      # smoke run only: a subset of DeskTyping keys, no profile gate
        f_dt, r_dt, g_dt, t_dt = ctx.clip('DeskTyping_seated', list(t_dt[AUDIT_KEYS[0]:AUDIT_KEYS[1] + 1:30]))
    dy = float(pick['extra_pull_in_dy_cm'])
    roll = ChairRoll(T0, (r0[0], r0[1] + dy))
    summary['roll_scan'] = scan
    print('roll', roll.roll, flush=True)
    reports, worlds = {}, {}
    # ---- DeskTyping (every 60 Hz key of the loop)
    F = len(t_dt)
    shift = np.tile(roll.roll - r0, (F, 1))
    ik = ctx.ik(f_dt.joint_world, r_dt.joint_world, t_dt, shift)
    W = ik.solve()
    path, sha = write(ctx, g_dt, W, t_dt, out_dir, 'SUB01_DeskTyping_seated', dict(LABELS, role='DeskTyping_seated'))
    Wb = readback(ctx, path, t_dt)
    rep = {'role': 'DeskTyping_seated', 'glb': rel(path), 'sha256': sha, 'bytes': path.stat().st_size,
           'keys': F, 'input_fit_clip': f'docs/proposed/seat-pose-fit/{CLIPS["DeskTyping_seated"][0]}',
           'raw_capture': CLIPS['DeskTyping_seated'][1], 'readback_max_world_error_cm': _r(np.abs(Wb[..., :3, 3] - W[..., :3, 3]).max() * 100, 6),
           'ik_history': ik.history, 'measure': measure(ctx, 'DeskTyping_seated', Wb, r_dt.joint_world, t_dt, shift,
                                                        np.tile(roll.roll, (F, 1)), ik)}
    rep['contact_profile'] = profile_validation(ctx, Wb, f_dt.joint_world, r_dt.joint_world, t_dt, shift) if not args.quick \
        else {'pass': False, 'skipped': 'quick smoke run'}
    rep['all_gates_pass'] = bool(rep['measure']['all_gates_pass'] and rep['contact_profile']['pass'])
    reports['DeskTyping_seated'], worlds['DeskTyping_seated'] = rep, (Wb, shift, t_dt)
    print('DeskTyping', rep['all_gates_pass'], flush=True)
    # ---- transitions: the roll is played over them (pull-in over SitToType, push-back over TypeToSit)
    f_i, r_i, _, t_i = ctx.clip('SeatedIdle')
    W_idle = f_i.joint_world
    for role, at_end in (('SitToType_seated', True), ('TypeToSit_seated', False)):
        rep, Wcb, shift_c, t_c = transition(ctx, role, at_end, roll, r0, W_idle, Wb, out_dir,
                                            (r_i.joint_world, t_i), (r_dt.joint_world, t_dt))
        reports[role], worlds[role] = rep, (Wcb, shift_c, t_c)
        print(role, rep['all_gates_pass'], flush=True)
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
    for k, v in reports.items():
        (out_dir / f'SUB01_{k}.report.json').write_text(json.dumps(strip(v), indent=1, allow_nan=False) + '\n')
    (out_dir / 'seated-typing-ik.proposal.json').write_text(json.dumps(summary, indent=1, allow_nan=False) + '\n')
    return summary, reports


EXIT_REFUSED = 3


def exit_code(summary):
    """0 only when every aggregate gate passed (summary['ready']); EXIT_REFUSED otherwise (the report is still written)."""
    return 0 if summary.get('ready') is True and all(summary.get('gates', {False: False}).values()) else EXIT_REFUSED


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--source', default=str(ROOT / 'private-audit/seat-fit-source.npz'))
    ap.add_argument('--cache', default=str(ROOT / 'out/seat-fit-cache'))
    ap.add_argument('--out-dir', default=str(OUT_DIR))
    ap.add_argument('--quick', action='store_true', help='smoke run on a DeskTyping subset (never a proposal)')
    ap.add_argument('--desk-source', help='LINEA140 source GLB: re-derive docs/proposed/seated-typing-ik/real-linea140-geometry.json')
    args = ap.parse_args(argv)
    if args.desk_source:
        GEOMETRY_JSON.parent.mkdir(parents=True, exist_ok=True)
        GEOMETRY_JSON.write_text(json.dumps(desk_geometry(args.desk_source), indent=1) + '\n')
    summary, _ = run(args)
    print(json.dumps({'ready': summary['ready'], 'gates': summary['gates'], 'roll_cm': summary['chair_roll_activity']['roll_cm']}, indent=1))
    return exit_code(summary)


if __name__ == '__main__':
    sys.exit(main())
