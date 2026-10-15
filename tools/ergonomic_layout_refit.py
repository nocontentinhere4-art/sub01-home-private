"""PROPOSAL (source only): ergonomic layout refit of the seated typing station -- keyboard and mouse toward the body
and/or the chair pulled in further, solved with a PALM/WRIST-TARGET arm IK instead of wrist corrections.

Labelled `proposal`, `verified: false`, `native_ready: false`, `ready: false`. Nothing in the runtime moves; the output
is a packet (docs/proposed/ergonomic-layout-refit/) for root to integrate. The original transforms are recorded and
preserved (the refit is a pure, reversible delta on three transforms).

Inputs (all committed, the same ones as tools/solve_seated_typing_arm_ik.py):
* the anatomical seated base (docs/proposed/seat-pose-anatomical/chair-lift-proposal, bfe7dc8 / 136195b) on the +2.5001 cm
  chair lift, solver frame = chair at the initial transform + (3.875, -32.5), body at the audited transform;
* the source-ready arm solve on that base (docs/proposed/seated-arms-on-anatomical, 26b3a8e3 DeskTyping GLB and its
  finish checkpoint): ONLY its palm path relative to the device under the hand and its keyboard / mouse / transit
  segmentation are used, never its fingers or its wrist corrections;
* the real LINEA140 desk boxes, the complete owner chair, the home.js keyboard (keycaps + case) and mouse (shell + pad).

Arm/finger separation (the old finger rests are known WRONG; root builds a 65-bone owner with the same root, arms and
wrists and new CC0 finger rests):
* the IK target of every frame is a HAND FRAME defined without any finger: the home-row frame (middle MCP 5.5 cm toward
  the body from the middle finger's home key, D / K, and 3.5 cm over the key tops; level hand, fingers at the rows,
  palm down) or main's mouse palm target (hand pitched 15 deg over the shell), blended over the source-ready solve's
  keyboard / mouse / transit segmentation, plus that solve's device-relative HORIZONTAL typing motion of the palm;
* the target point is the palm (60% wrist -> middle MCP, main's desk-hands rule); the wrist angle on the solved forearm
  is an OUTCOME, reported raw (no soft limit, no added flexion);
* fingers are carried rigidly with their base locals and never gate or drive the solve; the old fingertips are
  reported only as `old_finger_contact_diagnostic` (and fingers vs the desk as a reported, ungated number);
* the per-frame solution is stored as palm targets + elbow swivel + six arm-bone worlds (arm-solution.npz), with a
  palm-target robustness envelope, so root can re-run the hand contact with the new hands on the same solution.

Arm IK (palm/wrist-target mode): non-stretch two-bone IK (UE SolveTwoBoneIK form) shoulder -> elbow -> wrist with the
captured elbow pole swivelled about the shoulder-wrist axis (-120..120 deg, 5 deg). Per frame the swivel with the lowest
ergonomic cost (elbow band, raw wrist zone, then upper arm; elbow height breaks ties) whose arm skin clears the real
desk (>= 0.5 cm design target), the complete chair, the keyboard case and the owner's own torso and thighs is kept,
then smoothed in time (periodic Gaussian, failing frames pinned). The shoulder girdle stays as captured.

    python tools/ergonomic_layout_refit.py [--search] [--max-seconds 3000] [--out-dir docs/proposed/ergonomic-layout-refit]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import solve_seated_typing_arm_ik as A  # noqa: E402

E, P, T = A.E, A.P, A.T
SCHEMA = 'sub01.ergonomic-layout-refit.v1'
OUT_DIR = ROOT / 'docs/proposed/ergonomic-layout-refit'

# ---------------------------------------------------------------- the ORIGINAL layout (reversibility record)
BASE_DIR = 'docs/proposed/seat-pose-anatomical/chair-lift-proposal'
SOLVER_CHAIR_OFFSET_CM = (3.875, -32.5)            # the base clips' solver frame (seat-pose-fit actual-chair offset)
CHAIR_INITIAL_CM = (200.0199556350708, -186.69002056121826, 63.1876777245)   # measured + 2.5001 cm lift (bfe7dc8)
CHAIR_ROLL_ORIGINAL_CM = (3.875, -21.279)          # the seated-arms typing roll (336b5f8): extra pull-in 11.221 vs the solver
SOLVED_DIR = ROOT / 'docs/proposed/seated-arms-on-anatomical'
SOLVED_GLB = SOLVED_DIR / 'SUB01_DeskTyping_seated.glb'
SOLVED_SHA256 = '26b3a8e324259779394ef9e1576bbeac30d6ddfc876f4c818139ba98c4899134'
SOLVED_FINISH = SOLVED_DIR / 'SUB01_DeskTyping_seated.finish-checkpoint.npz'
KEYBOARD_HOME_JS = 'furnished("keyboard", 2, 0.846, -2.94, 0.371, 0, "/house/assets/keyboard/keyboard.glb")'
KEYBOARD_THREE_M = (2.0, 0.846, -2.94)
MOUSE_HOME_JS = 'furnished("mouse", 2.4, 0.846, -2.91, 0.22, 0, "/room/mouse.glb")'
MOUSE_THREE_M = (2.4, 0.846, -2.91)
# other items on the LINEA top (home.js, three.js metres -> UE cm): all BEHIND the devices, so a move toward the body
# (+UE Y) only increases their distance; listed for the record.
DESK_ITEMS_UE_CM = {'monitor_stand (box .12 x .12 at 2, .88, -3.3)': [[194., -336.], [206., -324.]],
                    'monitor_panel (box .72 x .035 at 2, 1.16, -3.3)': [[164., -331.75], [236., -328.25]],
                    'desk_lamp_arm_01 (2.65, .863, -3.18)': [[265., -318.], [265., -318.]],
                    'plant (3, .855, -3.25)': [[300., -325.], [300., -325.]]}

# ---------------------------------------------------------------- limits (hard) and soft targets (never loosened)
SLAB_EDGE_MARGIN_MIN_CM = 2.0      # a device footprint stays >= 2 cm inside every worktop edge: the worktop's eased top
                                   # edge (84.5 -> 84.283 cm, geometry note) is < 1 cm wide, so >= 1 cm of FLAT top remains
DEVICE_GAP_MIN_CM = 1.0            # keyboard case to mouse pad, plan view
TORSO_DESK_MIN_CM = 5.0            # torso skin to every desk part (design: no abdomen against the worktop edge)
ARM_DESK_TARGET_CM = A.FOREARM_TARGET_CLEARANCE_CM   # 0.5 cm design target (the gate is > 0, every frame)
ARM_BODY_MIN_CM = 0.0              # arm skin (shoulder cap excluded) vs the torso / thigh skin: no arm vertex inside the
                                   # body's convex plan section (section_gap; conservative), contact allowed, never through
BODY_SKIN_STRIDE = 2               # torso / thigh skin sampling for the self-collision test
BODY_CORE_WEIGHT = .9              # torso core: skin with >= 90% of its weight on Hips/Spine/Spine1/Spine2 (legs: on the leg bones)
                                   # (the shoulder / armpit blend skin that moves with the arm is not 'torso')
SHOULDER_CAP_EXCLUDE_CM = 12.      # arm vertices this close to the Arm joint are the shoulder cap / armpit (always touching)
ERGO_ELBOW_ABOVE_DESK_CM = A.ERGO_ELBOW_ABOVE_DESK_CM   # (0, 10): soft target, unchanged
ERGO_UPPER_ARM_MAX_DEG = A.ERGO_UPPER_ARM_MAX_DEG       # 20: soft target, unchanged
WRIST_FLEX_DEG, WRIST_DEV_DEG = A.WRIST_SOFT_FLEX_DEG, A.WRIST_SOFT_DEV_DEG
PALM_FRACTION = A.MOUSE_PALM_FRACTION                   # main desk-hands rule: palm 60% from wrist to middle MCP
SWIVEL_DEG = tuple(float(v) for v in np.arange(-120., 120.01, 5.))
SWIVEL_SMOOTH_S = .15
ENVELOPE_CM = {'z': (-1.5, 1.5), 'y': (-1.0, 1.0)}      # palm-target robustness envelope for root's new-hand contact
MODE_KEY, MODE_MOUSE, MODE_TRANSIT = A.MODE_KEY, A.MODE_MOUSE, A.MODE_TRANSIT


def _np(o):
    """json default: numpy scalars / arrays."""
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o).__name__)


def _r(v, d=3):
    return A._r(v, d)


def rng(a, d=3):
    return A.rng(a, d)


# ---------------------------------------------------------------- frames
def three_to_ue(p):
    """home.js three.js metres (x, y up, z) -> UE cm (x, z, y) * 100."""
    p = np.asarray(p, float)
    return np.array([p[0], p[2], p[1]]) * 100.


def ue_to_gltf_points(p_ue):
    """Inverse of E.to_ue (audited body transform, yaw 180): UE world cm -> glTF world metres (solver frame)."""
    p = np.asarray(p_ue, float) - np.asarray(E.BODY_CM, float)
    a = np.radians(E.BODY_YAW)
    c, s = np.cos(a), np.sin(a)
    cx, cy = c * p[..., 0] + s * p[..., 1], -s * p[..., 0] + c * p[..., 1]
    return np.stack([cx, p[..., 2], cy], -1) / 100.


class Layout:
    """One candidate: keyboard and mouse plan deltas on the worktop (UE cm), and the extra chair pull-in along UE Y
    (negative = toward the desk) added to the original typing roll. The body rolls rigidly with the chair."""

    def __init__(self, kb=(0., 0.), mouse=(0., 0.), chair_dy=0.):
        self.kb = np.array([kb[0], kb[1], 0.], float)
        self.mouse = np.array([mouse[0], mouse[1], 0.], float)
        self.chair_dy = float(chair_dy)

    @property
    def roll(self):
        return np.array([CHAIR_ROLL_ORIGINAL_CM[0], CHAIR_ROLL_ORIGINAL_CM[1] + self.chair_dy, 0.])

    @property
    def shift(self):
        """Body shift (UE cm) from the solver frame to the world at the typing roll."""
        return self.roll - np.array([*SOLVER_CHAIR_OFFSET_CM, 0.])

    def key(self):
        return (round(float(self.kb[0]), 3), round(float(self.kb[1]), 3), round(float(self.mouse[0]), 3),
                round(float(self.mouse[1]), 3), round(self.chair_dy, 3))

    def describe(self):
        kb0, ms0 = np.array(KEYBOARD_THREE_M), np.array(MOUSE_THREE_M)
        kb1 = kb0 + np.array([self.kb[0], 0., self.kb[1]]) / 100.
        ms1 = ms0 + np.array([self.mouse[0], 0., self.mouse[1]]) / 100.
        c0 = np.array(CHAIR_INITIAL_CM)
        return {
            'keyboard': {'delta_ue_cm': [_r(v) for v in self.kb], 'delta_three_m': [_r(self.kb[0] / 100, 5), 0.0, _r(self.kb[1] / 100, 5)],
                         'original_three_m': list(kb0), 'proposed_three_m': [_r(v, 5) for v in kb1],
                         'original_home_js': KEYBOARD_HOME_JS,
                         'proposed_home_js': f'furnished("keyboard", {kb1[0]:.4f}, 0.846, {kb1[2]:.4f}, 0.371, 0, "/house/assets/keyboard/keyboard.glb")',
                         'rotation_and_scale': 'unchanged'},
            'mouse': {'delta_ue_cm': [_r(v) for v in self.mouse], 'delta_three_m': [_r(self.mouse[0] / 100, 5), 0.0, _r(self.mouse[1] / 100, 5)],
                      'original_three_m': list(ms0), 'proposed_three_m': [_r(v, 5) for v in ms1],
                      'original_home_js': MOUSE_HOME_JS,
                      'proposed_home_js': f'furnished("mouse", {ms1[0]:.4f}, 0.846, {ms1[2]:.4f}, 0.22, 0, "/room/mouse.glb")',
                      'rotation_and_scale': 'unchanged'},
            'chair': {'initial_translation_cm': list(c0), 'initial_is': 'measured native + 2.5001 cm lift (bfe7dc8), unchanged',
                      'original_typing_roll_cm': [*CHAIR_ROLL_ORIGINAL_CM, 0.0],
                      'original_typing_translation_cm': [_r(v, 4) for v in c0 + [*CHAIR_ROLL_ORIGINAL_CM, 0.]],
                      'extra_pull_in_dy_cm': _r(self.chair_dy),
                      'proposed_typing_roll_cm': [_r(v, 4) for v in self.roll],
                      'proposed_typing_translation_cm': [_r(v, 4) for v in c0 + self.roll],
                      'rotation_scale_z': 'unchanged (castor roll on the floor)'},
            'body': {'solver_to_world_shift_cm': [_r(v, 4) for v in self.shift],
                     'rule': 'the seated body rolls rigidly with the chair (seat-relative pose = the anatomical base, unchanged)'}}


# ---------------------------------------------------------------- devices on the worktop
def keyboard_geometry():
    """The keyboard case (every vertex) and keycaps at the home.js placement (UE cm)."""
    g = A.G.Gltf(T.KEYBOARD_GLB)
    d = g.doc
    allp = np.concatenate([E.accessor(g, p['attributes']['POSITION']) for m in d['meshes'] for p in m['primitives']])
    lo, hi = allp.min(0), allp.max(0)
    x, y, z, width = T.KEYBOARD_HOME
    sc = width / (hi[0] - lo[0])
    c = (lo + hi) / 2
    off = np.array([x - c[0] * sc, y - lo[1] * sc, z - c[2] * sc])
    ue = T.ue_from_home(allp * sc + off)
    keys = T.keycaps_from_glb()
    return {'vertices_cm': ue, 'footprint_cm': [ue.min(0), ue.max(0)], 'bottom_cm': float(ue[:, 2].min()),
            'bottom_vertices_cm': ue[ue[:, 2] <= ue[:, 2].min() + .15], 'keys': keys,
            'case_box_cm': [ue.min(0), np.array([*ue.max(0)[:2], keys['key_min'][2]])],
            'sha256': hashlib.sha256(Path(T.KEYBOARD_GLB).read_bytes()).hexdigest()}


def slab_margins(points_xy, slab):
    lo, hi = np.asarray(slab['min_cm'][:2]), np.asarray(slab['max_cm'][:2])
    p = np.asarray(points_xy, float)
    return {'front_cm': float(hi[1] - p[:, 1].max()), 'rear_cm': float(p[:, 1].min() - lo[1]),
            'left_cm': float(p[:, 0].min() - lo[0]), 'right_cm': float(hi[0] - p[:, 0].max())}


def device_check(ctx, kbg, layout):
    """Support and plan clearances of the moved keyboard and mouse (hard gates)."""
    slab = ctx.geometry['tabletop_slab']
    top = float(slab['top_cm'])
    kb_v = kbg['vertices_cm'] + layout.kb
    kb_bottom = kbg['bottom_vertices_cm'] + layout.kb
    m_lo, m_hi = (np.asarray(v, float) + layout.mouse for v in ctx.mouse['footprint_ue_cm'])
    mouse_xy = np.array([[m_lo[0], m_lo[1]], [m_hi[0], m_hi[1]]])
    kb_m = slab_margins(kb_v[:, :2], slab)
    ms_m = slab_margins(mouse_xy, slab)
    kb_lo, kb_hi = kb_v.min(0), kb_v.max(0)
    gap_x = max(m_lo[0] - kb_hi[0], kb_lo[0] - m_hi[0])
    gap_y = max(m_lo[1] - kb_hi[1], kb_lo[1] - m_hi[1])
    gap = gap_x if gap_y < 0 else (gap_y if gap_x < 0 else math.hypot(gap_x, gap_y))
    grommet = [p for p in ctx.geometry['parts'] if p['kind'] == 'grommet']
    def plan_gap(lo, hi, parts):
        out = np.inf
        for p in parts:
            dx = max(p['min_cm'][0] - hi[0], lo[0] - p['max_cm'][0], 0.)
            dy = max(p['min_cm'][1] - hi[1], lo[1] - p['max_cm'][1], 0.)
            out = min(out, math.hypot(dx, dy))
        return out
    items = {k: min(plan_gap(kb_lo, kb_hi, [{'min_cm': v[0], 'max_cm': v[1]}]),
                    plan_gap(m_lo, m_hi, [{'min_cm': v[0], 'max_cm': v[1]}])) for k, v in DESK_ITEMS_UE_CM.items()}
    gates = {'keyboard_on_slab_margin': min(kb_m.values()) >= SLAB_EDGE_MARGIN_MIN_CM,
             'keyboard_feet_all_on_flat_top': bool(np.all([v >= SLAB_EDGE_MARGIN_MIN_CM for v in slab_margins(kb_bottom[:, :2], slab).values()])),
             'mouse_pad_on_slab_margin': min(ms_m.values()) >= SLAB_EDGE_MARGIN_MIN_CM,
             'keyboard_mouse_gap': gap >= DEVICE_GAP_MIN_CM,
             'clear_of_grommets': plan_gap(kb_lo, kb_hi, grommet) > 0 and plan_gap(m_lo, m_hi, grommet) > 0,
             'clear_of_other_desk_items': all(v > 0 for v in items.values())}
    return {'keyboard': {'footprint_cm': [[_r(v) for v in kb_lo], [_r(v) for v in kb_hi]],
                         'key_field_cm': [[_r(v) for v in kbg['keys']['key_min'] + layout.kb], [_r(v) for v in kbg['keys']['key_max'] + layout.kb]],
                         'dimensions_cm': [_r(v) for v in kb_hi - kb_lo], 'slab_margins_cm': {k: _r(v) for k, v in kb_m.items()},
                         'bottom_cm': _r(kbg['bottom_cm'], 4), 'bottom_above_worktop_cm': _r(kbg['bottom_cm'] - top, 4),
                         'bottom_note': 'the case bottom floats 0.1 cm over the 84.5 cm top at the home.js placement '
                                        '(root\'s pending device-foot check); the refit changes X/Y only',
                         'bottom_support_vertices': int(len(kb_bottom)),
                         'bottom_support_margins_cm': {k: _r(v) for k, v in slab_margins(kb_bottom[:, :2], slab).items()}},
            'mouse': {'footprint_cm': [[_r(v) for v in m_lo], [_r(v) for v in m_hi]], 'dimensions_cm': [_r(v) for v in m_hi - m_lo],
                      'slab_margins_cm': {k: _r(v) for k, v in ms_m.items()},
                      'palm_target_cm': [_r(v) for v in np.asarray(ctx.mouse['palm_target_cm']) + layout.mouse]},
            'keyboard_mouse_plan_gap_cm': _r(gap), 'other_items_plan_gap_cm': {k: _r(v) for k, v in items.items()},
            'limits': {'slab_edge_margin_min_cm': SLAB_EDGE_MARGIN_MIN_CM, 'device_gap_min_cm': DEVICE_GAP_MIN_CM},
            'gates': gates, 'pass': all(gates.values())}


# ---------------------------------------------------------------- hand-frame targets (palm/wrist target mode)
def hand_points(sk, W, side):
    """(F, 3) glTF: wrist joint, middle MCP and the palm point (PALM_FRACTION from wrist to middle MCP)."""
    p = A.SIDES[side]
    w = W[:, sk.j(f'{p}Hand'), :3, 3]
    m = W[:, sk.j(f'{p}HandMiddle1'), :3, 3]
    return w, m, w + PALM_FRACTION * (m - w)


def segment_weights(mode, dt, blend_s=None):
    """Per frame: weight of the MOUSE device (0 keyboard, 1 mouse). Transit runs between a keyboard and a mouse segment
    ramp with a quintic smootherstep over the run; runs touching a clip end take the neighbour's device."""
    mode = np.asarray(mode)
    F = len(mode)
    w = np.where(mode == MODE_MOUSE, 1., 0.)
    k = 0
    while k < F:
        if mode[k] != MODE_TRANSIT:
            k += 1
            continue
        e = k
        while e < F and mode[e] == MODE_TRANSIT:
            e += 1
        a = mode[k - 1] if k > 0 else (mode[e] if e < F else MODE_KEY)
        b = mode[e] if e < F else a
        wa, wb = float(a == MODE_MOUSE), float(b == MODE_MOUSE)
        s = A.smootherstep((np.arange(k, e) - k + 1) / (e - k + 1))
        w[k:e] = wa + (wb - wa) * s
        k = e
    return w


# The HOME-ROW HAND FRAME (independent of any finger rest): the middle-finger MCP over the middle finger's home key (D for
# the left hand, K for the right), MCP_BEHIND_CM toward the body and MCP_ABOVE_CM over the key tops -- a relaxed curled
# middle finger of this rig (3.84 + 2.45 + 2.17 = 8.5 cm, natural MCP/PIP/DIP curl) reaches the key top from there;
# root's new CC0 finger rests re-solve the contact INSIDE the palm-target envelope (ENVELOPE_CM). The hand attitude is
# fixed relative to the keyboard: fingers pointing straight at the key rows (-UE Y), palm facing the desk, pitched down
# HAND_PITCH_DEG. The wrist angle on the solved forearm is an OUTCOME (reported raw; no correction is ever added).
HOME_KEYS_UE_CM = {'left': ('D', (190.52, -293.02)), 'right': ('K', (200.02, -293.59))}   # keycap top centres, home.js keyboard
MCP_BEHIND_CM, MCP_ABOVE_CM = 5.5, 3.5
HAND_PITCH_DEG = 0.                # keyboard: level hand (bind-neutral axis)
HAND_YAW_ADAPT_DEG = 20.           # the hand frame may turn toward the forearm about the palm point (fingers at <= 20 deg
                                   # to the key columns, as touch typists do) ...
HAND_PITCH_ADAPT_DEG = 10.         # ... and pitch within +-10 deg of its device attitude
MOUSE_HAND_PITCH_DEG = 15.         # mouse: the hand drapes over the shell
PALM_LENGTH_CM = {'left': 7.07, 'right': 8.76}     # bind wrist -> middle MCP (owner rig, measured)


def ue_dir_to_gltf(v):
    """Inverse of E.to_ue_dir (yaw 180)."""
    v = np.asarray(v, float)
    a = np.radians(E.BODY_YAW)
    c, s_ = np.cos(a), np.sin(a)
    cx, cy = c * v[..., 0] + s_ * v[..., 1], -s_ * v[..., 0] + c * v[..., 1]
    return np.stack([cx, v[..., 2], cy], -1)


def home_hand_rotation(names, ibm, side, pitch_deg=HAND_PITCH_DEG):
    """(3, 3) unit glTF world rotation of the hand bone for the home-row attitude: the bind anatomical triad (b forearm/
    hand axis, r radial, n palmar) mapped to b -> -UE Y pitched down, n -> down (palm on the desk side); proper rotation,
    so the thumb side follows the hand's own chirality."""
    b, r, n = A.wrist_frame_bind(names, ibm, side)
    pb = math.radians(pitch_deg)
    bw = ue_dir_to_gltf(np.array([0., -math.cos(pb), -math.sin(pb)]))
    down = ue_dir_to_gltf(np.array([0., 0., -1.]))
    nw = down - down.dot(bw) * bw
    nw /= np.linalg.norm(nw)
    sgn = np.sign(np.dot(r, np.cross(n, b)))
    rw = sgn * np.cross(nw, bw)
    Mb = np.stack([b, r, n], 1)
    Mw = np.stack([bw, rw, nw], 1)
    Rw = Mw @ np.linalg.inv(Mb)
    h = names.index(A.ARM_BONES[side][2])
    return A.unit_rot(Rw @ A.unit_rot(np.linalg.inv(ibm)[h][:3, :3]))


class Targets:
    """Per side, per frame: the hand-frame target in the world (palm point, UE cm) relative to the device under the
    hand, the hand's home attitude (constant relative to the keyboard), and the device weight.

    palm(f) = anchor_blend(f) + XY of (old palm path(f) - its device-mean blend(f)) + device delta blend(f):
    the anchors are the home-row hand frame (keyboard) and main's mouse palm target (mouse); the source-ready solve's
    palm path contributes only its device-relative horizontal typing motion and its keyboard / mouse / transit
    segmentation, never its height or fingertips."""

    def __init__(self, ctx, W_base, W_solved, finish, times):
        self.sk = ctx.sk
        self.times = np.asarray(times, float)
        self.dt = float(np.mean(np.diff(self.times)))
        old_shift = Layout().shift
        top = float(ctx.keys['top_cm'])
        self.mode, self.w_mouse, self.palm0_ue, self.R_cap, self.palm_off, self.anchor = {}, {}, {}, {}, {}, {}
        for s in A.SIDES:
            mode = np.asarray(finish[f'mode_{s}'], int)
            self.mode[s] = mode
            w = segment_weights(mode, self.dt)
            self.w_mouse[s] = w
            _, _, palm = hand_points(self.sk, W_solved, s)
            p0 = E.to_ue(palm) + old_shift
            kf, mf = mode == MODE_KEY, mode == MODE_MOUSE
            mk = p0[kf].mean(0)
            mm = p0[mf].mean(0) if mf.any() else mk
            dev = p0 - ((1 - w)[:, None] * mk + w[:, None] * mm)
            dev[:, 2] = 0.
            key, (kx, ky) = HOME_KEYS_UE_CM[s]
            mcp = np.array([kx, ky + MCP_BEHIND_CM, top + MCP_ABOVE_CM])
            pb = math.radians(HAND_PITCH_DEG)
            axis = np.array([0., -math.cos(pb), -math.sin(pb)])            # wrist -> MCP, UE
            palm_k = mcp - (1 - PALM_FRACTION) * PALM_LENGTH_CM[s] * axis
            palm_m = np.asarray(ctx.mouse['palm_target_cm'], float)
            self.anchor[s] = {'home_key': key, 'home_key_centre_cm': [kx, ky], 'middle_mcp_cm': mcp.tolist(),
                              'keyboard_palm_cm': palm_k.tolist(), 'mouse_palm_cm': palm_m.tolist(),
                              'typing_motion_xy_cm': {'x': rng(dev[:, 0], 2), 'y': rng(dev[:, 1], 2)}}
            self.palm0_ue[s] = (1 - w)[:, None] * palm_k + w[:, None] * palm_m + dev
            Rk = home_hand_rotation(ctx.base.names, ctx.base.ibm, s, HAND_PITCH_DEG)
            Rm = home_hand_rotation(ctx.base.names, ctx.base.ibm, s, MOUSE_HAND_PITCH_DEG)
            qk, qm = P.quat_from_matrix(Rk[None]), P.quat_from_matrix(Rm[None])
            R = A.quat_to_matrix(P.slerp_arrays(np.repeat(qk, len(w), 0)[:, None], np.repeat(qm, len(w), 0)[:, None], w)[:, 0])
            h = self.sk.j(A.ARM_BONES[s][2])
            sc = np.linalg.norm(W_base[:, h, :3, 0], axis=-1)[:, None, None]
            M = np.array(W_base[:, h], copy=True)
            M[:, :3, :3] = R * sc
            self.R_cap[s] = M
            Bw = np.linalg.inv(ctx.base.ibm)
            v_bind = Bw[self.sk.j(f'{A.SIDES[s]}HandMiddle1')][:3, 3] - Bw[h][:3, 3]           # wrist -> middle MCP, bind
            v_world = R @ (A.unit_rot(Bw[h][:3, :3]).T @ v_bind)                                # the same bones, home attitude
            self.anchor[s]['wrist_to_mcp_ue_dir_keyboard'] = [_r(x, 4) for x in E.to_ue_dir(v_world[0] / np.linalg.norm(v_world[0]))] if not w[0] else None
            self.anchor[s]['hand_pitch_deg'] = {'keyboard': HAND_PITCH_DEG, 'mouse': MOUSE_HAND_PITCH_DEG, 'transit': 'slerp by the device weight'}
            self.palm_off[s] = PALM_FRACTION * v_world

    def device_delta(self, s, layout):
        w = self.w_mouse[s][:, None]
        return (1. - w) * layout.kb[None] + w * layout.mouse[None]

    def wrist_target(self, s, layout, extra_ue=None):
        """(F, 3) glTF solver-frame wrist target (palm target -> solver frame, minus the palm offset along the hand
        axis) and the world palm target (UE cm)."""
        palm = self.palm0_ue[s] + self.device_delta(s, layout)
        if extra_ue is not None:
            palm = palm + np.asarray(extra_ue, float)
        palm_solver = ue_to_gltf_points(palm - layout.shift)
        return palm_solver - self.palm_off[s], palm


# ---------------------------------------------------------------- arm IK with the relaxed swivel
def owner_skin_normals(stride=2, cache=None):
    """Every stride-th skinned owner vertex with its bind NORMAL (P.owner_skin plus normals)."""
    g = A.G.Gltf(E.decoded(E.OWNER, cache or ROOT / 'out/seat-fit-cache'))
    d = g.doc
    pos, nrm, jts, wts = [], [], [], []
    seen = set()
    for node in d['nodes']:
        if 'mesh' not in node or node.get('skin') != 0 or node['mesh'] in seen:
            continue
        seen.add(node['mesh'])
        for pr in d['meshes'][node['mesh']]['primitives']:
            a = pr['attributes']
            pos.append(E.accessor(g, a['POSITION'])[::stride])
            nrm.append(E.accessor(g, a['NORMAL'])[::stride])
            jts.append(E.accessor(g, a['JOINTS_0']).astype(int)[::stride])
            wts.append(E.accessor(g, a['WEIGHTS_0'])[::stride])
    pos, nrm, jts, wts = (np.concatenate(x) for x in (pos, nrm, jts, wts))
    keep = wts.sum(1) > 0
    return pos[keep], nrm[keep], jts[keep], wts[keep] / wts[keep].sum(1, keepdims=True)


def posed_with_normals(skin, ibm, W):
    """UE cm positions and unit normals (LBS is affine per vertex, so the normal is the posed difference of a 1 cm
    step along the bind normal) in the solver frame."""
    pos, nrm, jts, wts = skin
    p = E.to_ue(A.lbs((pos, jts, wts), ibm, W))
    q = E.to_ue(A.lbs((pos + .01 * nrm, jts, wts), ibm, W))
    n = q - p
    return p, n / np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-9)


HULL_BIN_CM = 2.0


def section_gap(body_pts, q, bin_cm=HULL_BIN_CM, reach=20.):
    """Smallest plan-section gap (cm) of points q to a body part: per horizontal slice of bin_cm, the CONVEX HULL of the
    body skin vertices in that slice (conservative: concavities are filled); for each point in the slice the largest
    hull-plane value (> 0 outside, < 0 inside = penetration depth). Robust to double-sided clothing / lining normals."""
    from scipy.spatial import ConvexHull, QhullError
    zq, zb = q[:, 2], body_pts[:, 2]
    lo = max(zq.min(), zb.min())
    hi = min(zq.max(), zb.max())
    if lo > hi:
        return reach
    best = reach
    for z0 in np.arange(np.floor(lo / bin_cm) * bin_cm, hi + bin_cm, bin_cm):
        bp = body_pts[(zb >= z0) & (zb < z0 + bin_cm)][:, :2]
        qq = q[(zq >= z0) & (zq < z0 + bin_cm)][:, :2]
        if len(bp) < 4 or not len(qq):
            continue
        try:
            h = ConvexHull(bp)
        except QhullError:
            continue
        v = (qq @ h.equations[:, :2].T + h.equations[:, 2]).max(1)
        best = min(best, float(v.min()))
    return best


class ArmSolver:
    """Palm/wrist-target arm IK on a fixed seated base (only Arm, ForeArm, Hand + carried fingers change)."""

    def __init__(self, ctx, W_base, kbg, stride=1):
        self.ctx, self.sk, self.Wb = ctx, ctx.sk, W_base
        self.names, self.ibm = ctx.base.names, ctx.base.ibm
        self.kbg = kbg
        self.arms = A.arm_skin(self.names, stride=stride) if stride != 1 else ctx.arms
        # torso / thigh skin of the owner (dominant joint) WITH bind normals, for the signed arm-vs-own-body test
        pos, nrm, jts, wts = owner_skin_normals(stride=BODY_SKIN_STRIDE)
        dom = jts[np.arange(len(jts)), wts.argmax(1)]
        torso_j = [self.names.index(n) for n in ('Hips', 'Spine', 'Spine1', 'Spine2')]
        leg_j = [k for k, n in enumerate(self.names) if n.endswith('UpLeg') or n.endswith('Leg')]
        tsel = (np.where(np.isin(jts, torso_j), wts, 0.).sum(1) >= BODY_CORE_WEIGHT) & np.isin(dom, torso_j)
        lsel = (np.where(np.isin(jts, leg_j), wts, 0.).sum(1) >= BODY_CORE_WEIGHT) & np.isin(dom, leg_j)
        self.torso_skin = tuple(x[tsel] for x in (pos, nrm, jts, wts))
        self.legs_skin = tuple(x[lsel] for x in (pos, nrm, jts, wts))

    # -- posing
    def pose(self, frames, side, wrist_t, phi_deg, W=None, hand_rot=None, palm_off=None, info=None):
        """Two-bone IK of `side` on base frames to the wrist targets with the captured elbow pole swivelled by phi; the
        hand takes `hand_rot` (the hand frame). With `palm_off` (wrist -> palm, glTF) the hand frame ADAPTS to the
        solved forearm within HAND_YAW_ADAPT_DEG / HAND_PITCH_ADAPT_DEG about the palm point (the palm target stays;
        the wrist moves with the hand), two fixed-point passes. No wrist limit, no added flexion."""
        W0 = np.array(self.Wb[frames] if W is None else W, copy=True)
        a, b, c = (self.sk.j(n) for n in A.ARM_BONES[side])
        S_, E0 = W0[:, a, :3, 3], self.Wb[frames][:, b, :3, 3]
        phi = np.radians(np.broadcast_to(phi_deg, len(frames)).astype(float))
        R = W0[:, c].copy() if hand_rot is None else np.array(hand_rot, copy=True)
        target = np.asarray(wrist_t, float)
        passes = 1 if palm_off is None else 3
        for it in range(passes):
            pole = A.swivel_pole(S_, target, E0, phi)
            W, reach, length, dist = self.sk.two_bone_pose(np.array(W0, copy=True), A.ARM_BONES[side], target, pole,
                                                           end_world_rot=np.array(R, copy=True))
            if it == passes - 1:
                break
            palm = np.asarray(wrist_t, float) + palm_off
            u0 = E.to_ue_dir(palm_off)
            u0 /= np.linalg.norm(u0, axis=-1, keepdims=True)
            fore = E.to_ue_dir(W[:, c, :3, 3] - W[:, b, :3, 3])
            fore /= np.linalg.norm(fore, axis=-1, keepdims=True)
            y0, p0 = np.arctan2(u0[:, 0], -u0[:, 1]), np.arcsin(np.clip(u0[:, 2], -1, 1))
            yf, pf = np.arctan2(fore[:, 0], -fore[:, 1]), np.arcsin(np.clip(fore[:, 2], -1, 1))
            dy = np.clip((yf - y0 + np.pi) % (2 * np.pi) - np.pi, -math.radians(HAND_YAW_ADAPT_DEG), math.radians(HAND_YAW_ADAPT_DEG))
            dp = np.clip(pf - p0, -math.radians(HAND_PITCH_ADAPT_DEG), math.radians(HAND_PITCH_ADAPT_DEG))
            y1, p1 = y0 + dy, p0 + dp
            d = np.stack([np.cos(p1) * np.sin(y1), -np.cos(p1) * np.cos(y1), np.sin(p1)], -1)
            Q = T.find_between(ue_dir_to_gltf(u0), ue_dir_to_gltf(d))
            R = np.array(hand_rot, copy=True)
            R[:, :3, :3] = Q @ hand_rot[:, :3, :3]
            target = palm - np.einsum('fij,fj->fi', Q, palm_off)
            if info is not None:
                info['hand_yaw_deg'], info['hand_pitch_deg'] = np.degrees(y1), np.degrees(p1)
        return W, reach, dist / np.maximum(length, 1e-12)

    def elbows(self, frames, side, wrist_t, phis):
        """(K, F, 3) glTF elbow per swivel (analytic) and the per-frame reach flag."""
        a, b, c = (self.sk.j(n) for n in A.ARM_BONES[side])
        W = self.Wb[frames]
        S_, E0, C0 = W[:, a, :3, 3], W[:, b, :3, 3], W[:, c, :3, 3]
        out = []
        for ph in phis:
            pole = A.swivel_pole(S_, wrist_t, E0, np.full(len(frames), math.radians(ph)))
            jn, en, reach, length, dist = T.two_bone(S_, E0, C0, wrist_t, pole)
            out.append(jn)
        return np.stack(out), reach

    # -- clearances of one posed side
    def body_trees(self, frames):
        """Per base frame (cached): KD-trees of the owner's torso and thigh skin in the SOLVER frame (UE cm, no shift):
        the base body never changes, so arm points are compared in the same frame."""
        from scipy.spatial import cKDTree
        cache = self.__dict__.setdefault('_trees', {})
        need = [int(f) for f in frames if int(f) not in cache]
        for s0 in range(0, len(need), 64):
            fr = np.asarray(need[s0:s0 + 64])
            tor, tn = posed_with_normals(self.torso_skin, self.ibm, self.Wb[fr])
            leg, ln = posed_with_normals(self.legs_skin, self.ibm, self.Wb[fr])
            for i, f in enumerate(fr):
                cache[int(f)] = (tor[i], leg[i])
        return [cache[int(f)] for f in frames]

    def side_clearance(self, W, side, layout, frames, chunk=64):
        """Per frame: min desk distance per arm part, torso and thigh gaps, chair margin, keyboard-case distance."""
        ctx = self.ctx
        shift, roll, kb_delta = layout.shift, layout.roll, layout.kb
        pos, jts, wts = self.arms[side]['skin']
        part = self.arms[side]['part']
        nf = part != 'fingers'
        a = self.sk.j(A.ARM_BONES[side][0])
        F = len(W)
        res = {k: np.full(F, np.inf) for k in ('upper_arm', 'forearm', 'hand', 'fingers', 'torso', 'legs', 'chair', 'keyboard_case', 'slab_vertical')}
        lo, hi = (np.asarray(v, float) + kb_delta for v in self.kbg['case_box_cm'])
        trees = self.body_trees(frames)
        for s0 in range(0, F, chunk):
            sl = slice(s0, min(F, s0 + chunk))
            Wc = W[sl]
            solver = E.to_ue(A.lbs((pos, jts, wts), self.ibm, Wc))
            pts = solver + shift
            d, _ = A.boxes_min_distance(pts, ctx.boxes, reach_cm=A.MEASURE_REACH_CM)
            v, _ = A.slab_clearance(pts, ctx.geometry['tabletop_slab'])
            for p_ in ('upper_arm', 'forearm', 'hand', 'fingers'):
                res[p_][sl] = d[:, part == p_].min(1)
            res['slab_vertical'][sl] = v[:, nf].min(1)
            res['keyboard_case'][sl] = A.box_signed_distance(pts[:, nf], lo, hi).min(1)
            cm, _ = ctx.collider.margin(pts[:, nf], roll)
            res['chair'][sl] = cm.min(1)
            sh = E.to_ue(Wc[:, a, :3, 3])
            far = np.linalg.norm(solver - sh[:, None], axis=-1) > SHOULDER_CAP_EXCLUDE_CM
            for i in range(len(Wc)):
                tt, lt = trees[s0 + i]
                q = solver[i][far[i] & nf]
                if len(q):
                    res['torso'][s0 + i] = section_gap(tt, q)
                res['legs'][s0 + i] = section_gap(lt, solver[i][nf])
        # the gate: upper arm, forearm and hand (palm). The OLD finger rests are known wrong: fingers vs desk is
        # reported, never gated (root re-runs the hand contact with the new CC0 finger rests)
        res['desk_min'] = np.minimum.reduce([res[p_] for p_ in ('upper_arm', 'forearm', 'hand')])
        return res

    @staticmethod
    def clear(res):
        return ((res['desk_min'] >= ARM_DESK_TARGET_CM) & (res['torso'] >= ARM_BODY_MIN_CM) & (res['legs'] >= ARM_BODY_MIN_CM)
                & (res['chair'] > 0) & (res['keyboard_case'] > 0))

    # -- the relaxed swivel
    def candidate_costs(self, frames, side, wrist_t, hand_rot, layout, phis, palm_off=None):
        """(K, F) ergonomic cost of every swivel (soft targets, unchanged) + a 1e-3/cm elbow-height tie-break (the
        relaxed, gravity-low elbow among equals)."""
        out = []
        for ph in phis:
            W, _, _ = self.pose(frames, side, wrist_t, ph, hand_rot=hand_rot, palm_off=palm_off)
            m = arm_metrics(self.ctx, W, self.Wb[frames], side, layout.shift)
            ev, uv, fv, dvv = ergo_violation(m)
            out.append((ev / SCORE_SCALE['elbow_cm']) ** 2 + (uv / SCORE_SCALE['upper_arm_deg']) ** 2
                       + (fv / SCORE_SCALE['wrist_deg']) ** 2 + (dvv / SCORE_SCALE['wrist_deg']) ** 2
                       + 1e-3 * m['elbow_above_top_cm'])
        return np.stack(out)

    def solve_side(self, frames, side, wrist_t, hand_rot, layout, max_rounds=len(SWIVEL_DEG), smooth=True, periodic=True, dt=1 / 60.,
                   palm_off=None):
        """Per frame, the swivel with the lowest ergonomic cost (elbow band, upper arm, RAW wrist angles; ties to the
        lowest elbow) whose posed arm clears everything; then a periodic Gaussian smoothing of the swivel with failing
        frames pinned to their own clear swivel (3 passes)."""
        phis = np.asarray(SWIVEL_DEG)
        cost = self.candidate_costs(frames, side, wrist_t, hand_rot, layout, phis, palm_off)
        order = np.argsort(cost, axis=0)                                   # (K, F): best first
        F = len(frames)
        chosen = np.full(F, np.nan)
        rnk = np.zeros(F, int)
        todo = np.arange(F)
        rounds = 0
        while len(todo) and rounds < max_rounds:
            ph = phis[order[rnk[todo], todo]]
            W, _, _ = self.pose(frames[todo], side, wrist_t[todo], ph, hand_rot=hand_rot[todo],
                                palm_off=None if palm_off is None else palm_off[todo])
            ok = self.clear(self.side_clearance(W, side, layout, frames[todo]))
            chosen[todo[ok]] = ph[ok]
            rnk[todo[~ok]] += 1
            todo = todo[~ok]
            todo = todo[rnk[todo] < len(phis)]
            rounds += 1
        unresolved = np.isnan(chosen)
        phi = np.where(unresolved, phis[order[0]], chosen)       # unresolved frames are reported failing, never hidden
        _, reach, _ = self.pose(frames, side, wrist_t, phi, hand_rot=hand_rot, palm_off=palm_off)
        info = {'rounds': rounds, 'unresolved_frames': int(unresolved.sum()), 'reach_all': bool(np.all(reach))}
        if smooth and F > 3:
            sig = SWIVEL_SMOOTH_S / dt
            pinned = np.zeros(F, bool)
            for _ in range(3):
                ps = gaussian(phi, sig, periodic)
                ps = np.where(pinned, phi, ps)
                W, _, _ = self.pose(frames, side, wrist_t, ps, hand_rot=hand_rot, palm_off=palm_off)
                ok = self.clear(self.side_clearance(W, side, layout, frames))
                if ok.all() or (~ok & ~pinned & ~unresolved).sum() == 0:
                    break
                pinned |= ~ok
            phi_out = ps
            info['smoothing_pinned_frames'] = int(pinned.sum())
        else:
            phi_out = phi
        return phi_out, info


def gaussian(x, sigma, periodic=True):
    x = np.asarray(x, float)
    if sigma <= 0 or len(x) < 3:
        return x
    r = int(math.ceil(3 * sigma))
    k = np.exp(-.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    pad = np.r_[x[-r:], x, x[:r]] if periodic and len(x) > r else np.pad(x, r, mode='edge')
    return np.convolve(pad, k, mode='valid')


# ---------------------------------------------------------------- per-frame arm metrics
def arm_metrics(ctx, W, W_base, side, shift):
    """Elbow height, upper-arm angle from vertical, shoulder elevation (vs captured), RAW wrist angles (no soft limit,
    no added flexion: the captured hand attitude on the new forearm), reach geometry; world UE cm."""
    sk = ctx.sk
    a, b, c = (sk.j(n) for n in A.ARM_BONES[side])
    sh = E.to_ue(W[:, a, :3, 3]) + shift
    el = E.to_ue(W[:, b, :3, 3]) + shift
    wr = E.to_ue(W[:, c, :3, 3]) + shift
    cl = E.to_ue(W[:, sk.j(f'{A.SIDES[side]}Shoulder'), :3, 3]) + shift
    ua = np.degrees(np.arccos(np.clip((sh[:, 2] - el[:, 2]) / np.linalg.norm(el - sh, axis=1), -1, 1)))
    v = sh - cl
    elev = np.degrees(np.arctan2(v[:, 2], np.linalg.norm(v[:, :2], axis=1)))
    v0 = E.to_ue(W_base[:, a, :3, 3]) - E.to_ue(W_base[:, sk.j(f'{A.SIDES[side]}Shoulder'), :3, 3])
    elev0 = np.degrees(np.arctan2(v0[:, 2], np.linalg.norm(v0[:, :2], axis=1)))
    fl, dv, tw = A.wrist_angles(W, ctx.base.names, ctx.base.ibm, side)
    fl0, dv0, _ = A.wrist_angles(W_base, ctx.base.names, ctx.base.ibm, side)
    fore = wr - el
    fore_slope = np.degrees(np.arctan2(fore[:, 2], np.linalg.norm(fore[:, :2], axis=1)))
    dh = np.linalg.norm((wr - sh)[:, :2], axis=1)
    l1, l2 = np.linalg.norm(el - sh, axis=1), np.linalg.norm(wr - el, axis=1)
    floor = np.degrees(np.arcsin(np.clip(np.maximum(dh - l2, 0.) / l1, 0, 1)))
    top = ctx.geometry['tabletop_slab']['top_cm']
    # the upper arm can be no closer to vertical than this with the elbow at/above the desk top (shoulder too low)
    elbow_at_top_ua = np.degrees(np.arccos(np.clip((sh[:, 2] - top) / l1, -1, 1)))
    return {'shoulder': sh, 'elbow': el, 'wrist': wr, 'upper_arm_deg': ua, 'elbow_above_top_cm': el[:, 2] - top,
            'shoulder_elevation_deg': elev, 'shoulder_elevation_capture_deg': elev0,
            'wrist_flexion_deg': fl, 'wrist_deviation_deg': dv, 'wrist_twist_deg': tw,
            'wrist_flexion_capture_deg': fl0, 'wrist_deviation_capture_deg': dv0,
            'forearm_slope_deg': fore_slope, 'shoulder_wrist_horizontal_cm': dh, 'upper_arm_cm': l1, 'forearm_cm': l2,
            'upper_arm_reach_floor_deg': floor, 'upper_arm_deg_if_elbow_at_top': elbow_at_top_ua,
            'shoulder_above_top_cm': sh[:, 2] - top}


def ergo_flags(m):
    eat = m['elbow_above_top_cm']
    elbow_ok = (eat >= ERGO_ELBOW_ABOVE_DESK_CM[0]) & (eat <= ERGO_ELBOW_ABOVE_DESK_CM[1])
    ua_ok = m['upper_arm_deg'] <= ERGO_UPPER_ARM_MAX_DEG
    wrist_ok = (m['wrist_flexion_deg'] >= WRIST_FLEX_DEG[0]) & (m['wrist_flexion_deg'] <= WRIST_FLEX_DEG[1])
    dev_ok = (m['wrist_deviation_deg'] >= WRIST_DEV_DEG[0]) & (m['wrist_deviation_deg'] <= WRIST_DEV_DEG[1])
    return elbow_ok, ua_ok, wrist_ok, dev_ok


# ---------------------------------------------------------------- body, chair and seat at the new roll
def body_check(ctx, W_base, layout, frames):
    """Owner body skin (stride 6: legs, torso/head) vs every real desk part at the new roll (hard: legs > 0, torso >=
    TORSO_DESK_MIN_CM); thigh top under the front apron; the complete chair along the WHOLE roll path."""
    pos, jts, wts = ctx.body_skin
    grp = ctx.body_group
    pts = E.to_ue(A.lbs((pos, jts, wts), ctx.base.ibm, W_base[frames])) + layout.shift
    out = {}
    for g in ('legs', 'torso_head'):
        q = pts[:, grp == g]
        d, w = A.boxes_min_distance(q, ctx.boxes, reach_cm=30.)
        k = np.unravel_index(np.argmin(d), d.shape)
        out[g] = {'min_cm': _r(d.min()), 'frame': int(frames[k[0]]), 'nearest_desk_node': ctx.box_nodes[w[k]] if w[k] >= 0 else None,
                  'point_cm': [_r(v, 2) for v in q[k]]}
    apron = ctx.geometry['front_apron']
    legs = pts[:, grp == 'legs']
    under = (legs[..., 1] <= apron['max_cm'][1] + 5) & (legs[..., 0] >= apron['min_cm'][0]) & (legs[..., 0] <= apron['max_cm'][0])
    top_leg = np.where(under, legs[..., 2], -np.inf).max()
    out['thigh_knee_top_under_front_apron_cm'] = _r(top_leg) if np.isfinite(top_leg) else None
    out['front_apron_bottom_cm'] = _r(apron['bottom_cm'])
    kb = ctx.geometry['knee_bay_cm']
    lx = legs[..., 0][legs[..., 1] < ctx.geometry['tabletop_slab']['front_edge_y_cm']]
    out['legs_under_desk_x_cm'] = [_r(lx.min()), _r(lx.max())] if lx.size else None
    out['knee_bay_x_cm'] = kb['x']
    roll = A.ChairRoll(np.asarray(CHAIR_INITIAL_CM, float), layout.roll[:2])
    path = A.chair_path_clearance(ctx.complete_chair, roll, ctx.boxes, ctx.box_nodes)
    out['complete_chair_roll_path'] = {k: path[k] for k in ('samples', 'worst_desk', 'desk_clear_all_samples', 'floor_gap_cm',
                                                            'floor_no_penetration', 'floor_gap_constant_along_roll', 'method')}
    cc = ctx.complete_chair
    pads = cc['triangles_cm'][cc['material'] == 'chair_armpad'].reshape(-1, 3) + layout.roll
    d, w = A.boxes_min_distance(pads, ctx.boxes, reach_cm=60.)
    k = int(np.argmin(d))
    out['chair_arm_pads'] = {'top_cm': _r(pads[:, 2].max()), 'bounds_cm': [[_r(v) for v in pads.min(0)], [_r(v) for v in pads.max(0)]],
                             'min_desk_distance_cm': _r(d[k]), 'nearest_desk_node': ctx.box_nodes[w[k]] if w[k] >= 0 else None,
                             'below_front_apron_by_cm': _r(apron['bottom_cm'] - pads[:, 2].max())}
    rev = A.reversibility(roll, np.linspace(0, 1, 31), np.linspace(0, 1, 31))
    out['roll_reversibility'] = rev
    gates = {'legs_clear_of_desk': out['legs']['min_cm'] > 0,
             'torso_clear_of_desk_min': out['torso_head']['min_cm'] >= TORSO_DESK_MIN_CM,
             'complete_chair_clear_of_desk_along_roll': bool(path['desk_clear_all_samples']),
             'chair_floor_no_penetration': bool(path['floor_no_penetration']),
             'roll_reversible_exact': bool(rev['reversible'])}
    out['gates'] = gates
    out['pass'] = all(gates.values())
    return out


def seat_check(ctx, W_base, W_raw, times, layout, frames):
    """Main's strong seat rule (origin/main validate_unreal_seat_contact.validate() @ 9792a35) re-measured LITERALLY at
    the new rolled chair: body and chair placed together at the world roll (the seat-relative pose is the base's)."""
    xy = layout.shift[:2]
    fit = ctx.seat_fit(P.place_body(W_raw[frames], xy), np.asarray(times)[frames], np.asarray(SOLVER_CHAIR_OFFSET_CM) + xy)
    res = A.main_strong_seat_rule(fit, P.place_body(W_base[frames], xy), np.asarray(times)[frames])
    res['chair_translation_cm'] = [_r(v, 4) for v in np.asarray(CHAIR_INITIAL_CM) + layout.roll]
    res['frames'] = f'{len(frames)} frames (every {int(frames[1] - frames[0]) if len(frames) > 1 else 1}th of DeskTyping)'
    return res


# ---------------------------------------------------------------- the old fingers: DIAGNOSTIC ONLY
def old_finger_diagnostic(ctx, W, layout, shift, side, mode):
    """Old (known wrong) finger rests carried rigidly on the new hand frames: over-key distal skin minimum minus the key
    top, in the MOVED keyboard. Reported only; never a gate, never optimised."""
    p, _ = ctx.base.skin(f'{side}_fingers', W)
    q = E.to_ue(p) + shift - layout.kb
    keys = ctx.keys
    inbox = (q[..., 0] >= keys['key_min'][0]) & (q[..., 0] <= keys['key_max'][0]) & (q[..., 1] >= keys['key_min'][1]) & (q[..., 1] <= keys['key_max'][1])
    over = inbox & ctx.key_raster.over(q[..., :2])
    gap = np.where(over, q[..., 2], np.inf).min(1) - keys['top_cm']
    kf = (np.asarray(mode) == MODE_KEY)
    n_over = over.sum(1)
    on = kf & (n_over >= A.KEY_MIN_OVER_VERTICES)
    g = gap[on]
    return {'label': 'DIAGNOSTIC ONLY: old finger rests (known wrong), carried rigidly; not a gate, not optimised',
            'keyboard_frames': int(kf.sum()), 'keyboard_frames_with_fingers_over_keys': int(on.sum()),
            'gap_cm_over_keys': rng(g, 3) if g.size else None,
            'frames_in_existing_key_gate': int(((g >= -P.KEY_PENETRATION_MAX_CM) & (g <= A.contact_profile.KEY_GAP_MAX_CM)).sum()) if g.size else 0,
            'gap_median_cm': _r(np.median(g)) if g.size else None}


def readiness(gates):
    """source_ready = every real source gate passes; native_ready is never set by a source run; ready = both."""
    src = bool(gates) and all(bool(v) for v in gates.values())
    return {'source_ready': src, 'native_ready': False, 'ready': False}


# ---------------------------------------------------------------- search objective
# Solver trade-off weights (the TARGETS are unchanged): the upper-arm target (<= 20 deg) is geometrically incompatible with
# the elbow band (>= desk top) on this rig at this desk (upper_arm_deg_if_elbow_at_top >= 26 deg on every frame), so the
# upper arm is minimised AFTER the elbow band and the wrist zone (a weaker weight), and reported as missed.
SCORE_SCALE = {'elbow_cm': 2., 'upper_arm_deg': 30., 'wrist_deg': 5.}
MOVE_COST_PER_CM = 1e-3            # tie-break only: the smaller change wins among equal postures


def ergo_violation(m):
    eat = m['elbow_above_top_cm']
    ev = np.maximum(0., ERGO_ELBOW_ABOVE_DESK_CM[0] - eat) + np.maximum(0., eat - ERGO_ELBOW_ABOVE_DESK_CM[1])
    uv = np.maximum(0., m['upper_arm_deg'] - ERGO_UPPER_ARM_MAX_DEG)
    fl, dv = m['wrist_flexion_deg'], m['wrist_deviation_deg']
    fv = np.maximum(0., WRIST_FLEX_DEG[0] - fl) + np.maximum(0., fl - WRIST_FLEX_DEG[1])
    dvv = np.maximum(0., WRIST_DEV_DEG[0] - dv) + np.maximum(0., dv - WRIST_DEV_DEG[1])
    return ev, uv, fv, dvv


def ergo_score(ms, layout):
    tot = []
    for m in ms:
        ev, uv, fv, dvv = ergo_violation(m)
        tot.append((ev / SCORE_SCALE['elbow_cm']) ** 2 + (uv / SCORE_SCALE['upper_arm_deg']) ** 2
                   + (fv / SCORE_SCALE['wrist_deg']) ** 2 + (dvv / SCORE_SCALE['wrist_deg']) ** 2)
    move = abs(layout.kb[0]) + abs(layout.kb[1]) + abs(layout.mouse[0]) + abs(layout.mouse[1]) + abs(layout.chair_dy)
    return float(np.mean(np.concatenate(tot))) + MOVE_COST_PER_CM * move


# ---------------------------------------------------------------- pipeline
SEARCH_STRIDE = 40                 # search frames: every 40th DeskTyping key (25 frames)
SEARCH_ARM_STRIDE = 3              # arm skin stride for the swivel search; every report re-measures every vertex
FINAL_CHECK_STRIDE = 10            # seat / body / envelope frames in the final run
SEARCH_GRID = {'kb_dy': (15., 17.),                   # keyboard toward the body (17: front feet 2.25 cm inside the edge)
               'chair_dy': (0., 3., 6., 9.),          # roll vs the original typing roll (+ = less pull-in: room for the
                                                      # elbows between the belly and the worktop edge)
               'mouse_dx': (-8., 0.),                 # mouse beside the keyboard (pad 1.45 cm from the case) or as is
               }


def mouse_dy_for(kb_dy, mouse_front_y, slab_front_y):
    """The mouse moves with the keyboard toward the body, but never closer than SLAB_EDGE_MARGIN_MIN_CM to the edge."""
    return float(min(kb_dy, slab_front_y - SLAB_EDGE_MARGIN_MIN_CM - mouse_front_y))


class Setup:
    def __init__(self, source, cache, arm_stride=SEARCH_ARM_STRIDE):
        A.configure(BASE_DIR, SOLVER_CHAIR_OFFSET_CM)
        self.ctx = ctx = A.Context(source, cache=cache, chair_translation=list(CHAIR_INITIAL_CM))
        f, r, _, t = ctx.clip('DeskTyping_seated')
        self.times, self.Wb, self.Wr = t, f.joint_world, r.joint_world
        if hashlib.sha256(SOLVED_GLB.read_bytes()).hexdigest() != SOLVED_SHA256:
            raise ValueError('source-ready DeskTyping GLB differs from 26b3a8e3')
        self.Ws = A.readback(ctx, SOLVED_GLB, t)
        self.finish = dict(np.load(SOLVED_FINISH))
        self.kbg = keyboard_geometry()
        self.targets = Targets(ctx, self.Wb, self.Ws, self.finish, t)
        self.solver = ArmSolver(ctx, self.Wb, self.kbg, stride=arm_stride)
        self.dt = float(np.mean(np.diff(t)))

    def layout_for(self, kb_dy, chair_dy, mouse_dx, kb_dx=0.):
        slab = self.ctx.geometry['tabletop_slab']
        mdy = mouse_dy_for(kb_dy, self.ctx.mouse['footprint_ue_cm'][1][1], slab['front_edge_y_cm'])
        return Layout((kb_dx, kb_dy), (mouse_dx, mdy), chair_dy)

    def evaluate(self, layout, frames, smooth=False, extra_ue=None):
        """Solve both arms on `frames`; returns (W, per-side metrics, per-side solve info, per-side wrist targets)."""
        W = np.array(self.Wb[frames], copy=True)
        ms, infos, phis, palms = {}, {}, {}, {}
        for s in A.SIDES:
            wt, palm = self.targets.wrist_target(s, layout, extra_ue)
            hr = self.targets.R_cap[s][frames]
            po = np.asarray(self.targets.palm_off[s])[frames]
            phi, info = self.solver.solve_side(frames, s, wt[frames], hr, layout, smooth=smooth, palm_off=po,
                                               dt=self.dt * (frames[1] - frames[0] if len(frames) > 1 else 1))
            hand = {}
            W, reach, ratio = self.solver.pose(frames, s, wt[frames], phi, W=W, hand_rot=hr, palm_off=po, info=hand)
            self.last_hand = getattr(self, 'last_hand', {})
            self.last_hand[s] = hand
            info['hand_frame_yaw_deg'] = rng(hand.get('hand_yaw_deg', np.zeros(1)), 2)
            info['hand_frame_pitch_deg'] = rng(hand.get('hand_pitch_deg', np.zeros(1)), 2)
            info['reach_all_frames'] = bool(np.all(reach))
            info['max_distance_over_chain_length'] = _r(ratio.max(), 4)
            ms[s] = arm_metrics(self.ctx, W, self.Wb[frames], s, layout.shift)
            infos[s], phis[s], palms[s] = info, phi, palm[frames]
        return W, ms, infos, phis, palms


def search(setup, out_dir, deadline):
    ckpt = Path(out_dir) / 'search-checkpoint.json'
    done = json.loads(ckpt.read_text()) if ckpt.exists() else {'rows': []}
    seen = {tuple(r['layout_key']) for r in done['rows']}
    frames = np.arange(0, len(setup.times), SEARCH_STRIDE)
    complete = True
    for kb_dy in SEARCH_GRID['kb_dy']:
        for chair_dy in SEARCH_GRID['chair_dy']:
            for mouse_dx in SEARCH_GRID['mouse_dx']:
                lay = setup.layout_for(kb_dy, chair_dy, mouse_dx)
                if lay.key() in seen:
                    continue
                if deadline and time.time() > deadline:
                    complete = False
                    break
                t0 = time.time()
                dev = device_check(setup.ctx, setup.kbg, lay)
                body = body_check(setup.ctx, setup.Wb, lay, frames)
                row = {'layout_key': list(lay.key()), 'device_pass': dev['pass'], 'device_gates': dev['gates'],
                       'body_pass': body['pass'], 'body_gates': body['gates'], 'torso_desk_min_cm': body['torso_head']['min_cm']}
                if dev['pass'] and body['pass']:
                    _, ms, infos, _, _ = setup.evaluate(lay, frames)
                    row['unresolved_frames'] = {s: infos[s]['unresolved_frames'] for s in A.SIDES}
                    row['reach_all'] = all(infos[s]['reach_all_frames'] for s in A.SIDES)
                    row['score'] = ergo_score(list(ms.values()), lay)
                    for s, m in ms.items():
                        e, u, w, d = ergo_flags(m)
                        row[s] = {'elbow_above_top_cm': rng(m['elbow_above_top_cm'], 2), 'upper_arm_deg': rng(m['upper_arm_deg'], 1),
                                  'wrist_flexion_deg': rng(m['wrist_flexion_deg'], 1), 'wrist_deviation_deg': rng(m['wrist_deviation_deg'], 1),
                                  'frames_ok': {'elbow': int(e.sum()), 'upper_arm': int(u.sum()), 'wrist_flex': int(w.sum()),
                                                'wrist_dev': int(d.sum()), 'of': len(frames)}}
                row['seconds'] = round(time.time() - t0, 1)
                done['rows'].append(row)
                seen.add(lay.key())
                ckpt.write_text(json.dumps(done, indent=1, default=_np) + '\n')
                print('search', row['layout_key'], row.get('score'), row.get('unresolved_frames'), row['seconds'], flush=True)
    done['complete'] = complete
    ckpt.write_text(json.dumps(done, indent=1, default=_np) + '\n')
    return done


def pick(rows):
    ok = [r for r in rows if r['device_pass'] and r['body_pass'] and 'score' in r and r['reach_all']
          and all(v == 0 for v in r['unresolved_frames'].values())]
    if not ok:
        return None
    return min(ok, key=lambda r: r['score'])


def continuity(points, dt):
    """Max speed / acceleration (cm/s, cm/s^2) of a per-frame path and the loop step (last -> first frame)."""
    p = np.asarray(points, float)
    v = np.diff(p, axis=0) / dt
    acc = np.diff(v, axis=0) / dt
    return {'max_speed_cm_s': _r(np.linalg.norm(v, axis=1).max(), 2), 'max_accel_cm_s2': _r(np.linalg.norm(acc, axis=1).max(), 1),
            'loop_step_cm': _r(np.linalg.norm(p[-1] - p[0]), 4), 'max_frame_step_cm': _r(np.linalg.norm(np.diff(p, axis=0), axis=1).max(), 4)}


def side_report(setup, layout, frames, W, side, m, res, info, phi, palm):
    e, u, w, d = ergo_flags(m)
    ev, uv, fv, dvv = ergo_violation(m)
    t = setup.times[frames]
    dt = float(np.mean(np.diff(t)))
    return {
        'ik': info, 'swivel_deg': rng(phi, 2),
        'elbow_height_cm': rng(m['elbow'][:, 2], 2), 'elbow_above_desk_top_cm': rng(m['elbow_above_top_cm'], 2),
        'upper_arm_from_vertical_deg': rng(m['upper_arm_deg'], 2),
        'upper_arm_deg_if_elbow_at_desk_top': rng(m['upper_arm_deg_if_elbow_at_top'], 2),
        'shoulder_height_cm': rng(m['shoulder'][:, 2], 2), 'shoulder_above_desk_top_cm': rng(m['shoulder_above_top_cm'], 2),
        'shoulder_elevation_deg': rng(m['shoulder_elevation_deg'], 2), 'shoulder_elevation_capture_deg': rng(m['shoulder_elevation_capture_deg'], 2),
        'shoulder_girdle': 'unchanged (captured): only Arm, ForeArm, Hand (+ carried fingers) change',
        'wrist_flexion_deg_raw': rng(m['wrist_flexion_deg'], 2), 'wrist_deviation_deg_raw': rng(m['wrist_deviation_deg'], 2),
        'wrist_twist_deg': rng(m['wrist_twist_deg'], 2),
        'wrist_flexion_capture_deg': rng(m['wrist_flexion_capture_deg'], 2), 'wrist_deviation_capture_deg': rng(m['wrist_deviation_capture_deg'], 2),
        'wrist_note': 'RAW: the captured hand attitude on the new forearm; no soft limit and no added flexion applied',
        'forearm_slope_deg': rng(m['forearm_slope_deg'], 2),
        'shoulder_to_wrist_horizontal_cm': rng(m['shoulder_wrist_horizontal_cm'], 2),
        'upper_arm_cm': _r(m['upper_arm_cm'].mean()), 'forearm_cm': _r(m['forearm_cm'].mean()),
        'upper_arm_reach_floor_deg': rng(m['upper_arm_reach_floor_deg'], 2),
        'clearance_cm': {'desk_upper_arm': rng(res['upper_arm']), 'desk_forearm': rng(res['forearm']), 'desk_hand': rng(res['hand']),
                         'desk_fingers': rng(res['fingers']), 'vertical_over_worktop_non_finger': rng(res['slab_vertical']),
                         'own_torso': rng(res['torso']), 'own_thighs': rng(res['legs']), 'complete_chair': rng(res['chair']),
                         'keyboard_case_non_finger': rng(res['keyboard_case'])},
        'clearance_frames_failing': {'desk_gt_0': int((res['desk_min'] <= 0).sum()), 'desk_design_0p5': int((res['desk_min'] < ARM_DESK_TARGET_CM).sum()),
                                     'torso': int((res['torso'] < ARM_BODY_MIN_CM).sum()), 'thighs': int((res['legs'] < ARM_BODY_MIN_CM).sum()),
                                     'chair': int((res['chair'] <= 0).sum()), 'keyboard_case': int((res['keyboard_case'] <= 0).sum())},
        'ergonomic_soft_targets': {'elbow_above_desk_cm': list(ERGO_ELBOW_ABOVE_DESK_CM), 'upper_arm_max_deg': ERGO_UPPER_ARM_MAX_DEG,
                                   'wrist_flexion_deg': list(WRIST_FLEX_DEG), 'wrist_deviation_deg': list(WRIST_DEV_DEG),
                                   'frames': len(frames), 'frames_ok': {'elbow': int(e.sum()), 'upper_arm': int(u.sum()),
                                                                         'wrist_flexion': int(w.sum()), 'wrist_deviation': int(d.sum()),
                                                                         'all_four': int((e & u & w & d).sum())},
                                   'worst_excess': {'elbow_cm': _r(ev.max(), 2), 'upper_arm_deg': _r(uv.max(), 2),
                                                    'wrist_flexion_deg': _r(fv.max(), 2), 'wrist_deviation_deg': _r(dvv.max(), 2)}},
        'continuity': {'elbow': continuity(m['elbow'], dt), 'wrist': continuity(m['wrist'], dt), 'palm_target': continuity(palm, dt)},
        'by_device': by_device(m, setup.targets.mode[side][frames], ergo_flags(m)),
    }


def by_device(m, mode, flags):
    e, u, w, d = flags
    out = {}
    for name, code in (('keyboard', MODE_KEY), ('mouse', MODE_MOUSE), ('transit', MODE_TRANSIT)):
        k = np.asarray(mode) == code
        if not k.any():
            continue
        out[name] = {'frames': int(k.sum()), 'elbow_above_desk_top_cm': rng(m['elbow_above_top_cm'][k], 2),
                     'upper_arm_from_vertical_deg': rng(m['upper_arm_deg'][k], 2),
                     'wrist_flexion_deg_raw': rng(m['wrist_flexion_deg'][k], 2), 'wrist_deviation_deg_raw': rng(m['wrist_deviation_deg'][k], 2),
                     'forearm_slope_deg': rng(m['forearm_slope_deg'][k], 2),
                     'frames_ok': {'elbow': int(e[k].sum()), 'upper_arm': int(u[k].sum()), 'wrist_flexion': int(w[k].sum()),
                                   'wrist_deviation': int(d[k].sum())},
                     'median': {'elbow_above_desk_top_cm': _r(np.median(m['elbow_above_top_cm'][k]), 2),
                                'upper_arm_deg': _r(np.median(m['upper_arm_deg'][k]), 2),
                                'wrist_flexion_deg': _r(np.median(m['wrist_flexion_deg'][k]), 2),
                                'wrist_deviation_deg': _r(np.median(m['wrist_deviation_deg'][k]), 2)}}
    return out


def per_frame_rows(frames, times, side, m, res, phi, palm, mode, wmouse):
    out = []
    for i, f in enumerate(frames):
        out.append({'frame': int(f), 't': _r(times[f], 4), 'device': ['keyboard', 'mouse', 'transit'][int(mode[f])], 'mouse_weight': _r(wmouse[f], 3),
                    'palm_target_cm': [_r(v, 3) for v in palm[i]], 'wrist_cm': [_r(v, 3) for v in m['wrist'][i]],
                    'elbow_cm': [_r(v, 3) for v in m['elbow'][i]], 'shoulder_cm': [_r(v, 3) for v in m['shoulder'][i]],
                    'swivel_deg': _r(phi[i], 2), 'elbow_above_top_cm': _r(m['elbow_above_top_cm'][i], 2),
                    'upper_arm_deg': _r(m['upper_arm_deg'][i], 2), 'shoulder_elevation_deg': _r(m['shoulder_elevation_deg'][i], 2),
                    'wrist_flexion_deg': _r(m['wrist_flexion_deg'][i], 2), 'wrist_deviation_deg': _r(m['wrist_deviation_deg'][i], 2),
                    'desk_min_cm': _r(res['desk_min'][i], 3), 'forearm_desk_cm': _r(res['forearm'][i], 3),
                    'torso_gap_cm': _r(res['torso'][i], 3), 'thigh_gap_cm': _r(res['legs'][i], 3), 'chair_margin_cm': _r(res['chair'][i], 3)})
    return out


def final(setup, layout, out_dir, search_rows=None, t_start=None):
    """The ONE proposed configuration on every DeskTyping key: solve, full-skin measurement, envelope, packet."""
    out_dir = Path(out_dir)
    ctx = setup.ctx
    frames = np.arange(len(setup.times))
    t0 = time.time()
    W, ms, infos, phis, palms = setup.evaluate(layout, frames, smooth=True)
    np.savez_compressed(out_dir / 'arm-solution.npz', **{
        **{f'{s}_{b}_world_gltf': W[:, ctx.sk.j(n)] for s in A.SIDES for b, n in zip(('upper_arm', 'forearm', 'hand'), A.ARM_BONES[s])},
        **{f'{s}_swivel_deg': phis[s] for s in A.SIDES}, **{f'{s}_palm_target_ue_cm': palms[s] for s in A.SIDES},
        **{f'{s}_mouse_weight': setup.targets.w_mouse[s] for s in A.SIDES}, **{f'{s}_mode': setup.targets.mode[s] for s in A.SIDES},
        **{f'{s}_hand_frame_yaw_deg': setup.last_hand[s].get('hand_yaw_deg') for s in A.SIDES},
        **{f'{s}_hand_frame_pitch_deg': setup.last_hand[s].get('hand_pitch_deg') for s in A.SIDES},
        'times': setup.times, 'solver_to_world_shift_cm': layout.shift, 'keyboard_delta_cm': layout.kb, 'mouse_delta_cm': layout.mouse})
    solve_s = time.time() - t0
    full = ArmSolver(ctx, setup.Wb, setup.kbg, stride=1)
    sides, rows, diag = {}, {}, {}
    for s in A.SIDES:
        res = full.side_clearance(W, s, layout, frames)
        sides[s] = side_report(setup, layout, frames, W, s, ms[s], res, infos[s], phis[s], palms[s])
        rows[s] = per_frame_rows(frames, setup.times, s, ms[s], res, phis[s], palms[s], setup.targets.mode[s], setup.targets.w_mouse[s])
        diag[s] = old_finger_diagnostic(ctx, W, layout, layout.shift, s, setup.targets.mode[s])
    sub = frames[::FINAL_CHECK_STRIDE]
    dev = device_check(ctx, setup.kbg, layout)
    body = body_check(ctx, setup.Wb, layout, sub)
    seat = seat_check(ctx, setup.Wb, setup.Wr, setup.times, layout, sub)
    env = {}
    for axis, (lo, hi) in ENVELOPE_CM.items():
        for v in (lo, hi):
            ex = np.zeros(3)
            ex['xyz'.index(axis)] = v
            _, me, ie, _, _ = setup.evaluate(layout, sub, extra_ue=ex)
            env[f'{axis}{v:+.1f}cm'] = {s: {'unresolved_frames': ie[s]['unresolved_frames'], 'reach_all': ie[s]['reach_all_frames'],
                                            'elbow_above_top_cm': rng(me[s]['elbow_above_top_cm'], 2), 'upper_arm_deg': rng(me[s]['upper_arm_deg'], 1),
                                            'wrist_flexion_deg': rng(me[s]['wrist_flexion_deg'], 1)} for s in A.SIDES}
    orig = Layout()
    _, m0, i0, _, _ = setup.evaluate(orig, sub)
    before = {s: {'elbow_above_top_cm': rng(m0[s]['elbow_above_top_cm'], 2), 'upper_arm_deg': rng(m0[s]['upper_arm_deg'], 1),
                  'wrist_flexion_deg_raw': rng(m0[s]['wrist_flexion_deg'], 1), 'shoulder_to_wrist_horizontal_cm': rng(m0[s]['shoulder_wrist_horizontal_cm'], 1),
                  'unresolved_frames': i0[s]['unresolved_frames']} for s in A.SIDES}
    arm_gates = {}
    for s, r in sides.items():
        cf = r['clearance_frames_failing']
        arm_gates[f'{s}_arm_desk_clear_every_frame'] = cf['desk_gt_0'] == 0
        arm_gates[f'{s}_arm_clear_of_own_body'] = cf['torso'] == 0 and cf['thighs'] == 0
        arm_gates[f'{s}_arm_clear_of_chair'] = cf['chair'] == 0
        arm_gates[f'{s}_arm_clear_of_keyboard_case'] = cf['keyboard_case'] == 0
        arm_gates[f'{s}_ik_non_stretch_reached_every_frame'] = r['ik']['reach_all_frames']
        arm_gates[f'{s}_swivel_resolved_every_frame'] = r['ik']['unresolved_frames'] == 0
        arm_gates[f'{s}_wrist_flexion_raw_within_soft_zone'] = r['ergonomic_soft_targets']['frames_ok']['wrist_flexion'] == len(frames)
    gates = {**{f'device_{k}': v for k, v in dev['gates'].items()}, **{f'body_{k}': v for k, v in body['gates'].items()},
             'seat_main_strong_rule_at_new_roll': bool(seat['pass']), **arm_gates}
    ready = readiness(gates)
    proposal = {
        'schema': SCHEMA, 'status': 'complete', 'label': 'proposal', 'source_only': True, 'verified': False,
        'requires_native_collision_audit': True, 'requires_server_reaudit': True, 'never_a_receipt': True,
        **ready, 'ready_rule': 'source_ready = every gate below true; native_ready never set by a source run; ready = both',
        'configuration': layout.describe(), 'reversibility': {
            'original_preserved': True, 'original': Layout().describe(),
            'rule': 'the refit is three transform deltas (keyboard, mouse, chair typing roll); restoring the original values '
                    'restores the original layout exactly; the chair roll path is the exact time reverse (push-back)',
            'chair_roll': body['roll_reversibility']},
        'devices': dev, 'body': body, 'seat': seat, 'arms': sides,
        'old_finger_contact_diagnostic': diag,
        'palm_target_envelope_for_new_hands': {'offsets_cm': ENVELOPE_CM, 'frames': f'every {FINAL_CHECK_STRIDE}th', 'results': env,
                                               'meaning': "root's new-hand contact may move the palm target inside this box; the arm "
                                                          'solution stays resolved with these ergonomics'},
        'before_after_same_method': {'original_layout': before, 'frames': f'every {FINAL_CHECK_STRIDE}th'},
        'gates': gates,
        'method': {'module': 'tools/ergonomic_layout_refit.py', 'hand_frame': 'palm point (60% wrist -> middle MCP) on the source-ready '
                   'palm path relative to the device under the hand (keyboard / mouse / quintic transit blend) + captured hand attitude',
                   'swivel': 'lowest elbow (relaxed) among clear swivels -90..90 deg (5 deg) about the shoulder-wrist axis from the '
                             'captured elbow plane, periodic Gaussian smoothing sigma 0.15 s, failing frames pinned',
                   'search_arm_skin_stride': SEARCH_ARM_STRIDE, 'reported_arm_skin_stride': 1,
                   'inputs': {'base_dir': BASE_DIR, 'solved_desk_typing_glb': A.rel(SOLVED_GLB), 'solved_sha256': SOLVED_SHA256,
                              'geometry_sha256': ctx.geometry_sha256, 'chair_source_sha256': A.CHAIR_SOURCE_SHA256,
                              'keyboard_sha256': setup.kbg['sha256'], 'mouse_sha256': ctx.mouse['sha256']}},
        'solution_file': 'docs/proposed/ergonomic-layout-refit/arm-solution.npz',
        'per_frame_file': 'docs/proposed/ergonomic-layout-refit/per-frame.json',
        'timing_s': {'solve': round(solve_s, 1), 'total': round(time.time() - (t_start or t0), 1)}}
    if search_rows is not None:
        proposal['search'] = {'grid': SEARCH_GRID, 'frames': f'every {SEARCH_STRIDE}th DeskTyping key', 'rows': len(search_rows),
                              'objective': 'mean over frames/sides of (elbow band excess/3 cm)^2 + (upper-arm excess/10 deg)^2 + '
                                           '(wrist flex/dev excess/5 deg)^2, + 0.001/cm of total move; hard gates first',
                              'file': 'docs/proposed/ergonomic-layout-refit/search-checkpoint.json'}
    (out_dir / 'per-frame.json').write_text(json.dumps(rows, separators=(',', ':'), default=_np) + '\n')
    (out_dir / 'ergonomic-layout-refit.proposal.json').write_text(json.dumps(proposal, indent=1, allow_nan=False, default=_np) + '\n')
    return proposal


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--source', default=str(ROOT / 'private-audit/seat-fit-source.npz'))
    ap.add_argument('--cache', default=str(ROOT / 'out/seat-fit-cache'))
    ap.add_argument('--out-dir', default=str(OUT_DIR))
    ap.add_argument('--search', action='store_true', help='run / resume the layout grid search (checkpointed)')
    ap.add_argument('--layout', type=lambda v: [float(x) for x in v.split(',')], default=None,
                    help='kb_dy,chair_dy,mouse_dx[,kb_dx]: skip the pick and solve this one')
    ap.add_argument('--max-seconds', type=float, default=3000.)
    args = ap.parse_args(argv)
    t_start = time.time()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    setup = Setup(args.source, args.cache)
    rows = None
    if args.search:
        done = search(setup, out, t_start + args.max_seconds - 900)
        rows = done['rows']
        if not done.get('complete'):
            print('search stopped on the bound; rerun --search to resume', flush=True)
            return 3
    if args.layout:
        layout = setup.layout_for(*args.layout)
    else:
        rows = rows or json.loads((out / 'search-checkpoint.json').read_text())['rows']
        best = pick(rows)
        if best is None:
            print('no layout passes the hard gates', flush=True)
            return 3
        k = best['layout_key']
        layout = Layout((k[0], k[1]), (k[2], k[3]), k[4])
    prop = final(setup, layout, out, rows, t_start)
    print(json.dumps({k: prop[k] for k in ('source_ready', 'native_ready', 'ready', 'gates')}, indent=1, default=_np))
    return 0 if prop['source_ready'] else 3


if __name__ == '__main__':
    sys.exit(main())
