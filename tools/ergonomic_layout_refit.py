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
* the IK target of every frame is a HAND FRAME: the palm point (60% from the wrist joint to the middle MCP, main's
  desk-hands contact rule) relative to the device under the hand, plus the hand's CAPTURED world attitude (no added
  flexion, no soft wrist limit). Fingers are carried rigidly and never drive the solve;
* the old fingertips are reported only as `old_finger_contact_diagnostic` (never a gate);
* the per-frame solution is stored as targets + elbow swivel + six arm-bone worlds, so root can re-run the hand
  contact with the new hands on the same arm/layout solution (a robustness envelope of the palm target is reported).

Arm IK (palm/wrist-target mode): non-stretch two-bone IK (UE SolveTwoBoneIK form) shoulder -> elbow -> wrist with the
captured elbow pole swivelled about the shoulder-wrist axis. The swivel is the RELAXED one: among the swivels whose arm
skin clears the real desk (>= 0.5 cm design target), the complete chair, the keyboard case and the owner's own torso and
thighs, the one with the LOWEST elbow (gravity; the shoulder girdle stays as captured), smoothed in time (periodic).

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
ARM_BODY_MIN_CM = 1.0              # arm skin (shoulder cap excluded) to torso / thigh skin vertices: a real gap, never through
SHOULDER_CAP_EXCLUDE_CM = 12.      # arm vertices this close to the Arm joint are the shoulder cap / armpit (always touching)
ERGO_ELBOW_ABOVE_DESK_CM = A.ERGO_ELBOW_ABOVE_DESK_CM   # (0, 10): soft target, unchanged
ERGO_UPPER_ARM_MAX_DEG = A.ERGO_UPPER_ARM_MAX_DEG       # 20: soft target, unchanged
WRIST_FLEX_DEG, WRIST_DEV_DEG = A.WRIST_SOFT_FLEX_DEG, A.WRIST_SOFT_DEV_DEG
PALM_FRACTION = A.MOUSE_PALM_FRACTION                   # main desk-hands rule: palm 60% from wrist to middle MCP
SWIVEL_DEG = tuple(float(v) for v in np.arange(-90., 90.01, 5.))
SWIVEL_SMOOTH_S = .15
ENVELOPE_CM = {'z': (-1.5, 1.5), 'y': (-1.0, 1.0)}      # palm-target robustness envelope for root's new-hand contact
MODE_KEY, MODE_MOUSE, MODE_TRANSIT = A.MODE_KEY, A.MODE_MOUSE, A.MODE_TRANSIT


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


class Targets:
    """Per side, per frame: the hand-frame target in the world (palm point, UE cm) relative to the device under the
    hand, the captured hand attitude (solver glTF rotation, unchanged), and the device weight. Built from the
    source-ready solve's palm path (device-relative), never its fingers."""

    def __init__(self, ctx, W_base, W_solved, finish, times):
        self.sk = ctx.sk
        self.times = np.asarray(times, float)
        self.dt = float(np.mean(np.diff(self.times)))
        old_shift = Layout().shift
        self.mode, self.w_mouse, self.palm0_ue, self.R_cap, self.palm_off = {}, {}, {}, {}, {}
        for s in A.SIDES:
            mode = np.asarray(finish[f'mode_{s}'], int)
            self.mode[s] = mode
            self.w_mouse[s] = segment_weights(mode, self.dt)
            _, _, palm = hand_points(self.sk, W_solved, s)
            self.palm0_ue[s] = E.to_ue(palm) + old_shift                # world, original layout
            h = self.sk.j(f'{A.SIDES[s]}Hand')
            self.R_cap[s] = A.unit_rot(W_base[:, h, :3, :3])           # captured hand attitude (base clip)
            wb, _, pb = hand_points(self.sk, W_base, s)
            self.palm_off[s] = pb - wb                                  # palm - wrist under the captured attitude (glTF m)

    def device_delta(self, s, layout):
        w = self.w_mouse[s][:, None]
        return (1. - w) * layout.kb[None] + w * layout.mouse[None]

    def wrist_target(self, s, layout, extra_ue=None):
        """(F, 3) glTF solver-frame wrist target: palm target (world) -> solver frame, minus the captured palm offset."""
        palm = self.palm0_ue[s] + self.device_delta(s, layout)
        if extra_ue is not None:
            palm = palm + np.asarray(extra_ue, float)
        palm_solver = ue_to_gltf_points(palm - layout.shift)
        return palm_solver - self.palm_off[s], palm


# ---------------------------------------------------------------- arm IK with the relaxed swivel
class ArmSolver:
    """Palm/wrist-target arm IK on a fixed seated base (only Arm, ForeArm, Hand + carried fingers change)."""

    def __init__(self, ctx, W_base, kbg, stride=1):
        self.ctx, self.sk, self.Wb = ctx, ctx.sk, W_base
        self.names, self.ibm = ctx.base.names, ctx.base.ibm
        self.kbg = kbg
        self.arms = A.arm_skin(self.names, stride=stride) if stride != 1 else ctx.arms
        # torso / thigh skin of the owner (dominant joint), for the arm-vs-own-body gap
        pos, jts, wts = P.owner_skin(stride=2)
        dom = jts[np.arange(len(jts)), wts.argmax(1)]
        g = A.body_parts(self.names)
        grp = np.array([g[int(j)] for j in dom])
        self.torso_skin = (pos[grp == 'torso_head'], jts[grp == 'torso_head'], wts[grp == 'torso_head'])
        self.legs_skin = (pos[grp == 'legs'], jts[grp == 'legs'], wts[grp == 'legs'])

    # -- posing
    def pose(self, frames, side, wrist_t, phi_deg, W=None):
        """Two-bone IK of `side` on base frames to the wrist targets with the captured elbow pole swivelled by phi;
        the hand keeps its CAPTURED world attitude (no limit, no added flexion)."""
        W = np.array(self.Wb[frames] if W is None else W, copy=True)
        a, b, c = (self.sk.j(n) for n in A.ARM_BONES[side])
        S_, E0 = W[:, a, :3, 3], self.Wb[frames][:, b, :3, 3]
        pole = A.swivel_pole(S_, wrist_t, E0, np.radians(np.broadcast_to(phi_deg, len(frames)).astype(float)))
        hand_world = W[:, c].copy()
        W, reach, length, dist = self.sk.two_bone_pose(W, A.ARM_BONES[side], wrist_t, pole, end_world_rot=hand_world)
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
    def side_clearance(self, W, side, shift, roll, kb_delta, frames_times=None, chunk=64):
        """Per frame: min desk distance per arm part, torso and thigh gaps, chair margin, keyboard-case distance."""
        ctx = self.ctx
        pos, jts, wts = self.arms[side]['skin']
        part = self.arms[side]['part']
        a = self.sk.j(A.ARM_BONES[side][0])
        F = len(W)
        res = {k: np.full(F, np.inf) for k in ('upper_arm', 'forearm', 'hand', 'fingers', 'torso', 'legs', 'chair', 'keyboard_case', 'slab_vertical')}
        lo, hi = (np.asarray(v, float) + kb_delta for v in self.kbg['case_box_cm'])
        from scipy.spatial import cKDTree
        for s0 in range(0, F, chunk):
            sl = slice(s0, min(F, s0 + chunk))
            Wc = W[sl]
            pts = E.to_ue(A.lbs((pos, jts, wts), self.ibm, Wc)) + shift
            d, _ = A.boxes_min_distance(pts, ctx.boxes, reach_cm=A.MEASURE_REACH_CM)
            v, _ = A.slab_clearance(pts, ctx.geometry['tabletop_slab'])
            for p_ in ('upper_arm', 'forearm', 'hand', 'fingers'):
                m = part == p_
                res[p_][sl] = d[:, m].min(1)
            res['slab_vertical'][sl] = v[:, part != 'fingers'].min(1)
            nf = part != 'fingers'
            res['keyboard_case'][sl] = A.box_signed_distance(pts[:, nf], lo, hi).min(1)
            cm, _ = ctx.collider.margin(pts[:, nf], roll)
            res['chair'][sl] = cm.min(1)
            sh = E.to_ue(Wc[:, a, :3, 3]) + shift
            far = np.linalg.norm(pts - sh[:, None], axis=-1) > SHOULDER_CAP_EXCLUDE_CM
            tor = E.to_ue(A.lbs(self.torso_skin, self.ibm, Wc)) + shift
            leg = E.to_ue(A.lbs(self.legs_skin, self.ibm, Wc)) + shift
            for i in range(len(Wc)):
                q = pts[i][far[i] & (part != 'fingers')]
                if len(q) == 0:
                    continue
                res['torso'][s0 + i] = cKDTree(tor[i]).query(q, k=1, distance_upper_bound=20.)[0].min()
                res['legs'][s0 + i] = cKDTree(leg[i]).query(pts[i][part != 'fingers'], k=1, distance_upper_bound=20.)[0].min()
        res['desk_min'] = np.minimum.reduce([res[p_] for p_ in ('upper_arm', 'forearm', 'hand', 'fingers')])
        return res

    @staticmethod
    def clear(res):
        return ((res['desk_min'] >= ARM_DESK_TARGET_CM) & (res['torso'] >= ARM_BODY_MIN_CM) & (res['legs'] >= ARM_BODY_MIN_CM)
                & (res['chair'] > 0) & (res['keyboard_case'] > 0))

    # -- the relaxed swivel
    def solve_side(self, frames, side, wrist_t, layout, max_rounds=12, smooth=True, periodic=True, dt=1 / 60.):
        """Lowest-elbow swivel whose posed arm clears everything; then a periodic Gaussian smoothing of the swivel with
        failing frames pinned to their own clear swivel (3 passes)."""
        phis = np.asarray(SWIVEL_DEG)
        el, reach = self.elbows(frames, side, wrist_t, phis)
        order = np.argsort(E.to_ue(el)[..., 2], axis=0)                    # (K, F): lowest elbow first
        F = len(frames)
        chosen = np.full(F, np.nan)
        rnk = np.zeros(F, int)
        todo = np.arange(F)
        rounds = 0
        while len(todo) and rounds < max_rounds:
            ph = phis[order[rnk[todo], todo]]
            W, _, _ = self.pose(frames[todo], side, wrist_t[todo], ph)
            ok = self.clear(self.side_clearance(W, side, layout.shift, layout.roll, layout.kb))
            chosen[todo[ok]] = ph[ok]
            rnk[todo[~ok]] += 1
            todo = todo[~ok]
            todo = todo[rnk[todo] < len(phis)]
            rounds += 1
        unresolved = np.isnan(chosen)
        # unresolved frames keep the lowest-elbow swivel (reported as failing; never hidden)
        base_phi = phis[order[0]]
        phi = np.where(unresolved, base_phi, chosen)
        info = {'rounds': rounds, 'unresolved_frames': int(unresolved.sum()), 'reach_all': bool(np.all(reach))}
        if smooth and F > 3:
            sig = SWIVEL_SMOOTH_S / dt
            pinned = np.zeros(F, bool)
            for _ in range(3):
                ps = gaussian(phi, sig, periodic)
                ps = np.where(pinned, phi, ps)
                W, _, _ = self.pose(frames, side, wrist_t, ps)
                ok = self.clear(self.side_clearance(W, side, layout.shift, layout.roll, layout.kb))
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
