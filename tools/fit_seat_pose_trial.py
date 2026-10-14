"""TRIAL seated pose fit on the ACTUAL 301 DeskTyping frames (proposal; never a verification).

Source: tools/export_seat_fit_source.py (fixed patch vertex sets, bind data, captured joint world
matrices; sole parity with root's UE numbers <= 1e-5 cm). Every output is labelled `trial`,
`verified: false`, `requires_server_reaudit: true`; nothing here sets or names a seat receipt.

Steps (docs/proposed/seat-pose-fit.md):
 (a) LOWER the captured body by one constant L (cm) solved from the seat support patch on the
     cushion triangles after the horizontal chair placement; the pelvis and upper-body capture
     are otherwise unchanged (a rigid translation of the whole skeleton).
 (b) LEGS: per leg, a non-stretch two-link (thigh/shin) analytic IK, UE SolveTwoBoneIK
     formulation (FindBetween on each bone, no stretch), knee pole = the captured knee; the
     captured FOOT WORLD ORIENTATION is preserved (genuine toe plant) and the foot is raised by one
     constant per leg so its lowest plantar point touches the support at the worst frame.
 (c) ARMS: the existing keyboard arm correction, reproduced from SolveCapturedKeyboardArmContact
     (tools/unreal_skin_contact_native.py) and Sub01KeyboardContactCorrection
     (tools/unreal_keyboard_contact_target.py): over-key distal skin minimum -> vertical shift to
     KeyTop + 0.08 cm, two-bone IK with the captured elbow as pole, captured wrist world rotation
     kept, finger locals unchanged, three passes; no stretch, so unreachable frames stay short.
 (d) HEAD: the captured head socket moves with the body; its height change is reported.

Gates are imported from tools/validate_unreal_seat_contact.py (every patch a LOCAL support
patch: lowest >= band low, lowest <= band high, >= MIN_SUPPORT_VERTICES in band) and
tools/validate_unreal_contact_profile.py (key gap <= 0.2 cm, penetration <= 0.1 cm).

    python tools/fit_seat_pose_trial.py --source private-audit/seat-fit-source.npz \
        [--chair private-audit/native-chair-surface.json] --out private-audit/native-seat-pose-trial.json
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
import export_seat_fit_source as E  # noqa: E402
import life_gltf as G  # noqa: E402
import validate_unreal_contact_profile as contact_profile  # noqa: E402
import validate_unreal_seat_contact as seat_contact  # noqa: E402
from fit_seat_rigid_placement import Surface  # noqa: E402  (Sub01SurfaceHeightAt rule)

SCHEMA = 'sub01.seat-pose-trial.v1'
SEAT_BAND_CM, SOLE_BAND_CM = seat_contact.SEAT_BAND_CM, seat_contact.SOLE_BAND_CM
MIN_PATCH_VERTICES, MIN_SUPPORT_VERTICES = seat_contact.MIN_PATCH_VERTICES, seat_contact.MIN_SUPPORT_VERTICES
SEAT_PATCHES, SOLE_PATCHES = seat_contact.SEAT_REGIONS, seat_contact.SOLE_REGIONS
KEY_GAP_MAX_CM, KEY_PENETRATION_MAX_CM, KEY_CONTACT_TARGET_CM = contact_profile.KEY_GAP_MAX_CM, .1, .08
KEY_MIN_OVER_VERTICES, KEY_MAX_SHIFT_CM, KEY_MIN_SHIFT_CM, ARM_PASSES = 4, 12., .001, 3   # native constants
FACING_DOWN_MAX_NZ = -.5
SUPPORT_Z_CM = 2.5                     # root: the support under the soles near Y=-270
CHAIR_SHIFT_CM = (3.875, -36.875)      # horizontal chair candidate (fit_seat_rigid_placement on the real bounds)
CHAIR_GLB = ROOT / 'web/room/chair_owner.glb'
CHAIR_HOME_M = (2., 0., -1.9)          # web/house/home.js: chair.position.set(2, 0, -1.9)
KEYBOARD_GLB = ROOT / 'web/house/assets/keyboard/keyboard.glb'
KEYBOARD_HOME = (2., .846, -2.94, .371)  # web/house/home.js: furnished("keyboard", 2, 0.846, -2.94, 0.371)
ROOT_KEY_TOP_CM = 87.38975858
LEGS = {'left': ('LeftUpLeg', 'LeftLeg', 'LeftFoot'), 'right': ('RightUpLeg', 'RightLeg', 'RightFoot')}
ARMS = {'left': ('LeftArm', 'LeftForeArm', 'LeftHand'), 'right': ('RightArm', 'RightForeArm', 'RightHand')}
UP = np.array([0., 1., 0.])            # glTF up; UE z


def _r(v, d=6):
    v = float(v)
    return None if not math.isfinite(v) else (0.0 if round(v, d) == 0 else round(v, d))


# ---------------------------------------------------------------- scene geometry
def ue_from_home(p):
    """three.js / glTF home metres -> UE world cm (extract_keyboard_keycaps.py contract)."""
    p = np.asarray(p, dtype=float)
    return np.stack([p[..., 0], p[..., 2], p[..., 1]], axis=-1) * 100.


def cushion_from_report(report):
    tri = np.asarray(seat_contact.cushion_triangles(report), dtype=float).reshape(-1, 3, 3)
    return tri, {'source': 'root chair surface report (actual UE cushion triangles)', 'proxy': False}


def cushion_proxy(cache):
    """Repo fallback: chair_fabric upward triangles of web/room/chair_owner.glb at its home placement,
    selected by unreal_chair_surface_audit.cushion_top's rule (normal z > .65, centre within 8 cm of the
    authored 50.5 cm seat and 40 cm of the authored origin). A PROXY: root's UE cushion replaces it."""
    g = G.Gltf(E.decoded(CHAIR_GLB, cache))
    d = g.doc
    node = d['nodes'][0]
    t, s = np.array(node.get('translation', (0, 0, 0))), np.array(node.get('scale', (1, 1, 1)))
    for prim in d['meshes'][node['mesh']]['primitives']:
        if d['materials'][prim['material']]['name'] != 'chair_fabric':
            continue
        pos = E.accessor(g, prim['attributes']['POSITION']) * s + t + np.array(CHAIR_HOME_M)
        world = ue_from_home(pos)
        idx = E.accessor(g, prim['indices']).astype(int).reshape(-1, 3)[:, [0, 2, 1]]   # mirror keeps faces up
        a, b, c = world[idx[:, 0]], world[idx[:, 1]], world[idx[:, 2]]
        n = np.cross(b - a, c - a)
        length = np.linalg.norm(n, axis=1)
        centre = (a + b + c) / 3
        keep = (length > 0) & (n[:, 2] / np.maximum(length, 1e-12) > .65) & (np.abs(centre[:, 2] - 50.5) < 8) \
            & (np.abs(centre[:, 0] - 200) < 40) & (np.abs(centre[:, 1] + 190) < 40)
        tri = np.stack([a[keep], b[keep], c[keep]], axis=1)
        return tri, {'source': 'PROXY: web/room/chair_owner.glb chair_fabric at home.js placement, '
                               'unreal_chair_surface_audit rule; not the UE cushion', 'proxy': True,
                     'sha256': hashlib.sha256(CHAIR_GLB.read_bytes()).hexdigest()}
    raise ValueError('chair_owner.glb has no chair_fabric primitive')


def keycaps_from_glb():
    """Keycap top triangles of web/house/assets/keyboard/keyboard.glb at its home.js placement
    (furnished(): uniform scale to 0.371 m width, centred, bottom at 0.846 m); tops chosen as in
    tools/extract_keyboard_keycaps.py (welded components, |n.z| > .9, within 0.12 cm of the top)."""
    g = G.Gltf(KEYBOARD_GLB)
    d = g.doc
    allp = np.concatenate([E.accessor(g, p['attributes']['POSITION']) for m in d['meshes'] for p in m['primitives']])
    lo, hi = allp.min(axis=0), allp.max(axis=0)
    x, y, z, width = KEYBOARD_HOME
    scale = width / (hi[0] - lo[0])
    centre = (lo + hi) / 2
    offset = np.array([x - centre[0] * scale, y - lo[1] * scale, z - centre[2] * scale])
    caps = max(range(len(d['meshes'])), key=lambda i: d['accessors'][d['meshes'][i]['primitives'][0]['attributes']['POSITION']]['count'])
    prim = d['meshes'][caps]['primitives'][0]
    pts = ue_from_home(E.accessor(g, prim['attributes']['POSITION']) * scale + offset)
    idx = E.accessor(g, prim['indices']).astype(int).reshape(-1, 3)
    parent = np.arange(len(pts))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    weld = {}
    for i, p in enumerate(np.round(pts / 100, 7)):
        key = tuple(p)
        if key in weld:
            parent[find(i)] = find(weld[key])
        else:
            weld[key] = i
    for t in idx:
        parent[find(t[1])] = find(t[0])
        parent[find(t[2])] = find(t[0])
    comp = np.array([find(i) for i in range(len(pts))])
    comp_top = {c: pts[comp == c, 2].max() for c in np.unique(comp[idx[:, 0]])}
    tops = []
    key_tops = []
    for c, top in comp_top.items():
        tris = idx[comp[idx[:, 0]] == c]
        a, b, cc = pts[tris[:, 0]], pts[tris[:, 1]], pts[tris[:, 2]]
        n = np.cross(b - a, cc - a)
        length = np.linalg.norm(n, axis=1)
        flat = (length > 1e-9) & (np.abs(n[:, 2]) / np.maximum(length, 1e-12) > .9) & ((a[:, 2] + b[:, 2] + cc[:, 2]) / 3 >= top - .12)
        if flat.any():
            tops.append(np.stack([a[flat], b[flat], cc[flat]], axis=1))
            key_tops.append(top)
    tri = np.concatenate(tops)
    return {'triangles': tri, 'key_min': pts.min(axis=0), 'key_max': pts.max(axis=0), 'top_cm': float(pts[:, 2].max()),
            'keycaps': len(key_tops), 'top_spread_cm': float(max(key_tops) - min(key_tops)),
            'source': 'web/house/assets/keyboard/keyboard.glb at home.js placement (UE keycap top check vs root 87.38975858)'}


# ---------------------------------------------------------------- kinematics (glTF world metres)
def find_between(u, v):
    """(F, 3, 3) minimal rotations taking unit u to unit v (FQuat::FindBetweenNormals)."""
    u = u / np.linalg.norm(u, axis=-1, keepdims=True)
    v = v / np.linalg.norm(v, axis=-1, keepdims=True)
    axis = np.cross(u, v)
    s = np.linalg.norm(axis, axis=-1)
    c = np.sum(u * v, axis=-1)
    k = axis / np.maximum(s, 1e-15)[..., None]
    K = np.zeros(u.shape[:-1] + (3, 3))
    K[..., 0, 1], K[..., 0, 2], K[..., 1, 0] = -k[..., 2], k[..., 1], k[..., 2]
    K[..., 1, 2], K[..., 2, 0], K[..., 2, 1] = -k[..., 0], -k[..., 1], k[..., 0]
    eye = np.broadcast_to(np.eye(3), K.shape)
    return eye + s[..., None, None] * K + (1 - c)[..., None, None] * (K @ K)


def two_bone(root, joint, end, effector, pole):
    """AnimationCore::SolveTwoBoneIK, bAllowStretching=false: new joint/end positions, reached flags."""
    l1 = np.linalg.norm(joint - root, axis=-1)
    l2 = np.linalg.norm(end - joint, axis=-1)
    delta = effector - root
    dist = np.linalg.norm(delta, axis=-1)
    direction = delta / np.maximum(dist, 1e-12)[..., None]
    target = pole - root
    bend = target - np.sum(target * direction, axis=-1)[..., None] * direction
    degenerate = np.linalg.norm(bend, axis=-1) < 1e-10        # pole on the line: UE FindBestAxisVectors fallback
    if degenerate.any():
        helper = np.where((np.abs(direction[..., 2]) < .9)[..., None], [0., 0., 1.], [1., 0., 0.])
        fallback = np.cross(np.cross(direction, helper), direction)
        bend = np.where(degenerate[..., None], fallback, bend)
    bend = bend / np.maximum(np.linalg.norm(bend, axis=-1), 1e-12)[..., None]
    reach = dist < l1 + l2
    cos = np.clip((dist ** 2 + l1 ** 2 - l2 ** 2) / np.maximum(2 * l1 * dist, 1e-12), -1, 1)
    line = l1 * np.sqrt(1 - cos ** 2)
    proj = l1 * cos
    joint_new = np.where(reach[..., None], root + proj[..., None] * direction + line[..., None] * bend,
                         root + l1[..., None] * direction)
    end_new = np.where(reach[..., None], effector, root + (l1 + l2)[..., None] * direction)
    return joint_new, end_new, reach, l1 + l2, dist


class Skeleton:
    def __init__(self, source):
        self.src = source
        self.names = source.names
        self.parents = source.parents
        self.children = {j: [k for k, p in enumerate(self.parents) if p == j] for j in range(len(self.names))}

    def j(self, name):
        return self.names.index(name)

    def subtree(self, j):
        out, stack = [], [j]
        while stack:
            k = stack.pop()
            out.append(k)
            stack += self.children[k]
        return out

    def rebase(self, W, j, new_j):
        """Set joint j's world matrix and carry its whole subtree rigidly (descendant locals unchanged)."""
        delta = new_j @ np.linalg.inv(W[:, j])
        for k in self.subtree(j):
            W[:, k] = delta @ W[:, k] if k != j else new_j
        return W

    def two_bone_pose(self, W, chain, effector, pole, end_world_rot=None):
        """Apply the UE two-bone IK to chain (upper, lower, end) for all frames; end rotation kept."""
        a, b, c = (self.j(n) for n in chain)
        A, B, C = W[:, a, :3, 3], W[:, b, :3, 3], W[:, c, :3, 3]
        jn, en, reach, length, dist = two_bone(A, B, C, effector, pole)
        R1 = find_between(B - A, jn - A)
        R2 = find_between(C - B, en - jn)
        old_c = W[:, c].copy() if end_world_rot is None else end_world_rot.copy()
        up = W[:, a].copy()
        up[:, :3, :3] = R1 @ W[:, a, :3, :3]
        lo = W[:, b].copy()
        lo[:, :3, :3] = R2 @ W[:, b, :3, :3]
        lo[:, :3, 3] = jn
        end = old_c
        end[:, :3, 3] = en
        carry = end @ np.linalg.inv(W[:, c])
        for k in self.subtree(c):
            if k != c:
                W[:, k] = carry @ W[:, k]                    # descendants (toes / fingers) keep their locals
        W[:, a], W[:, b], W[:, c] = up, lo, end
        return W, reach, length, dist


# ---------------------------------------------------------------- measurements
def patch_metrics(points, normals, height_fn, band):
    """Per frame: facing, over-surface count, lowest gap, band count (native rule, all facing-down skin)."""
    facing = normals[..., 2] <= FACING_DOWN_MAX_NZ
    found = np.zeros(points.shape[:2], dtype=bool)
    top = np.full(points.shape[:2], np.nan)
    f, h = height_fn(points[facing][:, :2])                 # only facing-down skin can count
    found[facing], top[facing] = f, h
    gap = points[..., 2] - top
    over = facing & found
    low, high = band
    lowest = np.where(over, gap, np.inf).min(axis=1)
    inband = (over & (gap >= low) & (gap <= high)).sum(axis=1)
    return {'facing': facing.sum(axis=1), 'over': over.sum(axis=1), 'lowest': np.where(np.isfinite(lowest), lowest, np.nan),
            'band': inband, 'median': np.array([np.median(g[o]) if o.any() else np.nan for g, o in zip(gap, over)])}


def support_gate(m, band):
    low, high = band
    over_ok = m['over'] >= MIN_PATCH_VERTICES
    pen = over_ok & (m['lowest'] < low)
    above = over_ok & (m['lowest'] > high)
    short = over_ok & (m['band'] < MIN_SUPPORT_VERTICES)
    passed = over_ok & ~pen & ~above & ~short
    return passed, {'not_over_surface': ~over_ok, 'penetration': pen, 'lowest_above_band': above, 'support_vertices_short': short}


class Trial:
    def __init__(self, source, cushion_tri, keycaps, chair_shift=CHAIR_SHIFT_CM, support_z=SUPPORT_Z_CM):
        self.src, self.sk = source, Skeleton(source)
        self.cushion_tri = np.asarray(cushion_tri, dtype=float).copy()
        self.cushion_tri[..., 0] += chair_shift[0]
        self.cushion_tri[..., 1] += chair_shift[1]
        self.cushion = Surface(self.cushion_tri)
        self.chair_shift = chair_shift
        self.keys = keycaps
        self.key_surface = Surface(keycaps['triangles'])
        self.support_z = support_z
        self.W0 = source.joint_world.copy()

    # --- helpers
    def ue_joint(self, W, name):
        return E.to_ue(W[:, self.sk.j(name), :3, 3])

    def skin_ue(self, name, W):
        pos, nrm = self.src.skin(name, W)
        return E.to_ue(pos), E.to_ue_dir(nrm)

    def support_height(self, xy):
        return np.ones(len(xy), bool), np.full(len(xy), self.support_z)

    def lowered(self, L_cm):
        W = self.W0.copy()
        W[:, :, :3, 3] -= UP * L_cm / 100.
        return W

    def seat(self, W, frames=None):
        out = {}
        if frames is not None:
            W = W[frames]
        for name in SEAT_PATCHES:
            p, n = self.skin_ue(name, W)
            out[name] = patch_metrics(p, n, self.cushion.height, SEAT_BAND_CM)
        return out

    def soles(self, W):
        out = {}
        for name in SOLE_PATCHES:
            p, n = self.skin_ue(name, W)
            m = patch_metrics(p, n, self.support_height, SOLE_BAND_CM)
            m['centroid_xy'] = p[..., :2].mean(axis=1)
            m['lowest_any_z'] = p[..., 2].min(axis=1)
            out[name] = m
        return out

    # --- (b) legs
    def fit_legs(self, W, foot_raise_cm):
        info = {}
        for side, chain in LEGS.items():
            foot = self.sk.j(chain[2])
            captured_foot = self.W0[:, foot].copy()
            target = captured_foot[:, :3, 3] + UP * foot_raise_cm[side] / 100.
            pole = W[:, self.sk.j(chain[1]), :3, 3]          # captured knee (moved with the body)
            W, reach, length, dist = self.sk.two_bone_pose(W, chain, target, pole, end_world_rot=captured_foot)
            info[side] = {'reached_all_frames': bool(reach.all()), 'max_hip_to_ankle_over_leg_cm': _r((dist - length).max() * 100)}
        return W, info

    def solve_foot_raise(self, W_lowered):
        """Constant per-leg raise so the lowest plantar point touches the support at the worst frame."""
        raise_cm = {s: 0. for s in LEGS}
        for _ in range(4):
            W, _ = self.fit_legs(W_lowered.copy(), raise_cm)
            soles = self.soles(W)
            done = True
            for side in LEGS:
                worst = np.nanmin(soles[f'{side}_sole']['lowest_any_z']) - self.support_z
                if abs(worst) > 1e-7:
                    raise_cm[side] -= worst
                    done = False
            if done:
                break
        return raise_cm

    # --- (c) arms
    def key_audit(self, W):
        """Per side: over-key distal vertex count and minimum height (AnalyzeCapturedFingerSkin)."""
        out = {}
        kmin, kmax = self.keys['key_min'], self.keys['key_max']
        for side in ARMS:
            p, _ = self.skin_ue(f'{side}_fingers', W)
            inbox = (p[..., 0] >= kmin[0]) & (p[..., 0] <= kmax[0]) & (p[..., 1] >= kmin[1]) & (p[..., 1] <= kmax[1])
            found, _ = self.key_surface.height(p[..., :2].reshape(-1, 2))
            over = inbox & found.reshape(p.shape[:2])
            out[side] = {'over': over.sum(axis=1), 'over_min': np.where(over, p[..., 2], np.inf).min(axis=1)}
        return out

    def fit_arms(self, W):
        top = self.keys['top_cm']
        first = {}
        for npass in range(ARM_PASSES):
            audit = self.key_audit(W)
            changed = False
            for side, chain in ARMS.items():
                a = audit[side]
                delta = top + KEY_CONTACT_TARGET_CM - a['over_min']
                ok = (a['over'] >= KEY_MIN_OVER_VERTICES) & np.isfinite(delta) & (np.abs(delta) <= KEY_MAX_SHIFT_CM)
                move = ok & (np.abs(delta) > KEY_MIN_SHIFT_CM)
                shift = np.where(ok, delta, 0.)
                shoulder, elbow, hand = (W[:, self.sk.j(n), :3, 3] for n in chain)
                effector = hand + UP * shift[:, None] / 100.
                if npass == 0:
                    # Geometric request: the over-key target regardless of the native 12 cm refusal cap.
                    measured = (a['over'] >= KEY_MIN_OVER_VERTICES) & np.isfinite(delta)
                    target = hand + UP * np.where(measured, delta, 0.)[:, None] / 100.
                    first[side] = {'requested_cm': np.linalg.norm(target - shoulder, axis=-1) * 100,
                                   'arm_cm': (np.linalg.norm(elbow - shoulder, axis=-1) + np.linalg.norm(hand - elbow, axis=-1)) * 100,
                                   'shift_cm': np.where(measured, delta, np.nan), 'corrected': ok,
                                   'refused_by_cap': measured & (np.abs(delta) > KEY_MAX_SHIFT_CM)}
                if move.any():
                    Wn, _, _, _ = self.sk.two_bone_pose(W.copy(), chain, effector, elbow)
                    W = np.where(move[:, None, None, None], Wn, W)
                    changed = True
            if not changed:
                break
        return W, first

    # --- pipeline
    def run(self, L_cm, raise_cm, arms=True):
        W, leg_info = self.fit_legs(self.lowered(L_cm), raise_cm)
        reach = None
        if arms:
            W, reach = self.fit_arms(W)
        return W, leg_info, reach

    def seat_extremes(self, L, raise_cm, frames=None):
        W = self.lowered(L)
        W, _ = self.fit_legs(W, raise_cm)
        s = self.seat(W, frames)
        return (max(np.nanmax(s[n]['lowest']) for n in SEAT_PATCHES), min(np.nanmin(s[n]['lowest']) for n in SEAT_PATCHES))

    def solve_lowering(self, raise_cm, guess=5.1, tol=1e-6):
        """L (cm) at which the highest per-frame lowest seat gap over buttocks and thighs is 0 (touching on
        the worst frame), with the legs refitted at every L; plus the band-feasible interval of L
        [highest lowest at +0.5, deepest lowest at -2.5]. Secant iteration on the measured gaps."""
        subset = np.unique(np.r_[np.arange(0, len(self.src.times), 10), len(self.src.times) - 1])

        def secant(index, target, frames, start):
            a, fa = start, self.seat_extremes(start, raise_cm, frames)[index] - target
            b = a + fa                                                          # gaps move ~1:1 with L
            for _ in range(30):
                fb = self.seat_extremes(b, raise_cm, frames)[index] - target
                if abs(fb) < tol or fb == fa:
                    return b
                a, b, fa = b, b - fb * (b - a) / (fb - fa), fb
            raise RuntimeError('lowering did not converge')

        def solve(index, target):
            # Ranking frames first, then the same secant on ALL 301 frames from there (exact on all frames).
            return secant(index, target, None, secant(index, target, subset, guess))
        return solve(0, 0.), (solve(0, SEAT_BAND_CM[1]), solve(1, SEAT_BAND_CM[0]))

    def solve(self, guess=5.1):
        """Alternate the foot raise (support touch) and the lowering (seat touch) until both settle."""
        L, raise_cm = guess, None
        for _ in range(4):
            raise_cm = self.solve_foot_raise(self.lowered(L))
            L_new, interval = self.solve_lowering(raise_cm, L)
            if abs(L_new - L) < 1e-6:
                return L_new, interval, raise_cm
            L = L_new
        return L, interval, raise_cm


# ---------------------------------------------------------------- report
def frame_list(mask, times):
    return [round(float(t), 4) for t in times[np.asarray(mask)]]


def report(trial: Trial, L_cm, L_interval, raise_cm, cushion_meta):
    src = trial.src
    times = src.times
    W_cap = trial.W0
    W_low = trial.lowered(L_cm)
    W, leg_info, _ = trial.run(L_cm, raise_cm)
    # Reach before (captured body) and after lowering, each from pass 1 of the same arm correction.
    _, reach_before = trial.fit_arms(W_cap.copy())
    W_low_legs, _ = trial.fit_legs(W_low.copy(), raise_cm)
    _, reach_after = trial.fit_arms(W_low_legs.copy())
    out = {'schema': SCHEMA, 'label': 'trial', 'verified': False, 'requires_server_reaudit': True,
           'requires_native_collision_audit': True,
           'source': {k: src.meta[k] for k in ('owner', 'owner_sha256', 'clip', 'clip_sha256', 'counts')},
           'parity_3s': E.parity(src), 'cushion': cushion_meta,
           'chair_horizontal_shift_cm': list(trial.chair_shift),
           'keyboard': {'source': trial.keys['source'], 'top_cm': _r(trial.keys['top_cm']),
                        'root_top_cm': ROOT_KEY_TOP_CM, 'keycaps': trial.keys['keycaps'],
                        'top_spread_cm': _r(trial.keys['top_spread_cm'])},
           'support_z_cm': trial.support_z,
           'constants': {'seat_band_cm': list(SEAT_BAND_CM), 'sole_band_cm': list(SOLE_BAND_CM),
                         'min_patch_vertices': MIN_PATCH_VERTICES, 'min_support_vertices': MIN_SUPPORT_VERTICES,
                         'key_gap_max_cm': KEY_GAP_MAX_CM, 'key_penetration_max_cm': KEY_PENETRATION_MAX_CM,
                         'key_contact_target_cm': KEY_CONTACT_TARGET_CM},
           'times_s': [round(float(t), 6) for t in times]}
    alternatives = {}
    for label, L_alt in (('lowest_at_upper_edge', L_interval[0]), ('deepest_at_lower_edge', L_interval[1])):
        Wa, _ = trial.fit_legs(trial.lowered(L_alt), raise_cm)
        sa = trial.seat(Wa)
        alternatives[label] = {'body_lowering_cm': _r(L_alt), **{n: {'max_lowest_gap_cm': _r(np.nanmax(sa[n]['lowest'])),
                                                                     'min_lowest_gap_cm': _r(np.nanmin(sa[n]['lowest']))}
                                                                 for n in SEAT_PATCHES}}
    out['lowering'] = {'body_lowering_cm': _r(L_cm), 'rule': 'highest per-frame lowest seat gap (buttocks, thighs) = 0',
                       'single_lowering_feasible': bool(L_interval[0] <= L_interval[1]),
                       'at_interval_edges': alternatives,
                       'feasible_interval_cm': [_r(L_interval[0]), _r(L_interval[1])],
                       'interval_rule': '[lowest at +0.5 on the worst frame, deepest at -2.5 on the worst frame]',
                       'mesh_component_z_cm': _r(E.BODY_CM[2] - L_cm)}
    # (a) seat, captured vs fitted
    seat_before, seat_after = trial.seat(trial.lowered(0.)), trial.seat(W)
    out['seat'] = {}
    for name in SEAT_PATCHES:
        m0, m = seat_before[name], seat_after[name]
        passed, fails = support_gate(m, SEAT_BAND_CM)
        out['seat'][name] = {'pass_all_frames': bool(passed.all()), 'failing_frames': int((~passed).sum()),
                             'failures': {k: frame_list(v, times) for k, v in fails.items() if v.any()},
                             'lowest_gap_cm': [_r(v, 4) for v in m['lowest']], 'band_vertices': m['band'].tolist(),
                             'over_surface_vertices': m['over'].tolist(),
                             'worst': {'max_lowest_gap_cm': _r(np.nanmax(m['lowest'])), 'min_lowest_gap_cm': _r(np.nanmin(m['lowest'])),
                                       'min_band_vertices': int(m['band'].min()), 'min_over_surface_vertices': int(m['over'].min()),
                                       'max_median_gap_cm_reported_only': _r(np.nanmax(m['median']))},
                             'captured_body': {'max_lowest_gap_cm': _r(np.nanmax(m0['lowest'])) if np.isfinite(m0['lowest']).any() else None,
                                               'min_over_surface_vertices': int(m0['over'].min())}}
    # (b) soles
    soles_cap, soles = trial.soles(W_cap), trial.soles(W)
    out['soles'] = {}
    for name in SOLE_PATCHES:
        m, m0 = soles[name], soles_cap[name]
        passed, fails = support_gate(m, SOLE_BAND_CM)
        slide = np.linalg.norm(m['centroid_xy'] - m['centroid_xy'][0], axis=1)
        slide0 = np.linalg.norm(m0['centroid_xy'] - m0['centroid_xy'][0], axis=1)
        side = name.split('_')[0]
        out['soles'][name] = {'pass_all_frames': bool(passed.all()), 'failing_frames': int((~passed).sum()),
                              'failures': {k: frame_list(v, times) for k, v in fails.items() if v.any()},
                              'foot_raise_vs_captured_world_cm': _r(raise_cm[side]),
                              'foot_raise_vs_lowered_body_cm': _r(raise_cm[side] + L_cm),
                              'lowest_gap_cm': [_r(v, 4) for v in m['lowest']], 'band_vertices': m['band'].tolist(),
                              'worst': {'min_lowest_gap_cm': _r(np.nanmin(m['lowest'])), 'max_lowest_gap_cm': _r(np.nanmax(m['lowest'])),
                                        'min_band_vertices': int(m['band'].min())},
                              'captured_body': {'min_lowest_gap_cm': _r(np.nanmin(m0['lowest'])),
                                                'min_band_vertices': int(m0['band'].min())},
                              'foot_slide_cm': {'fitted_max': _r(slide.max()), 'captured_max': _r(slide0.max()),
                                                'difference_max': _r(np.abs(slide - slide0).max())},
                              'ik': leg_info[side]}
    # foot orientation preserved
    rot_err = 0.
    for side, chain in LEGS.items():
        f = trial.sk.j(chain[2])
        a, b = W_cap[:, f, :3, :3], W[:, f, :3, :3]
        rel = np.einsum('fji,fjk->fik', a / np.linalg.norm(a[:, :, 0], axis=1)[:, None, None],
                        b / np.linalg.norm(b[:, :, 0], axis=1)[:, None, None])
        ang = np.degrees(np.arccos(np.clip((np.trace(rel, axis1=1, axis2=2) - 1) / 2, -1, 1)))
        rot_err = max(rot_err, float(ang.max()))
    out['foot_world_orientation_max_change_deg'] = _r(rot_err, 9)
    # bone lengths
    err = 0.
    for k, p in enumerate(trial.sk.parents):
        if p < 0:
            continue
        a = np.linalg.norm(W_cap[:, k, :3, 3] - W_cap[:, p, :3, 3], axis=1)
        b = np.linalg.norm(W[:, k, :3, 3] - W[:, p, :3, 3], axis=1)
        err = max(err, float(np.abs(a - b).max()) * 100)
    out['bone_length_max_error_cm'] = _r(err, 9)
    # (c) reach and key contact
    out['reach'] = {}
    for side in ARMS:
        b, a = reach_before[side], reach_after[side]
        over_b, over_a = b['requested_cm'] - b['arm_cm'], a['requested_cm'] - a['arm_cm']
        out['reach'][side] = {
            'arm_length_cm': _r(b['arm_cm'].max()),
            'before': {'frames_over_arm': int((over_b > 0).sum()), 'worst_requested_cm': _r(b['requested_cm'].max()),
                       'worst_time_s': _r(times[int(np.argmax(b['requested_cm']))], 4),
                       'over_arm_times_s': frame_list(over_b > 0, times),
                       'over_arm_cm_at_those_times': [_r(v, 5) for v in over_b[over_b > 0]],
                       'frames_refused_by_native_12cm_cap': int(b['refused_by_cap'].sum()),
                       'requested_cm': [_r(v, 5) for v in b['requested_cm']],
                       'vertical_shift_cm': [_r(v, 5) for v in b['shift_cm']]},
            'after_lowering': {'frames_over_arm': int((over_a > 0).sum()), 'worst_requested_cm': _r(a['requested_cm'].max()),
                               'worst_time_s': _r(times[int(np.argmax(a['requested_cm']))], 4),
                               'over_arm_times_s': frame_list(over_a > 0, times),
                               'min_margin_cm': _r((a['arm_cm'] - a['requested_cm']).min(), 5),
                               'frames_refused_by_native_12cm_cap': int(a['refused_by_cap'].sum()),
                               'refused_times_s': frame_list(a['refused_by_cap'], times),
                               'requested_cm': [_r(v, 5) for v in a['requested_cm']],
                               'vertical_shift_cm': [_r(v, 5) for v in a['shift_cm']]}}
    final = trial.key_audit(W)
    cap = trial.key_audit(W_cap)
    out['key_contact'] = {}
    for side in ARMS:
        gap = final[side]['over_min'] - trial.keys['top_cm']
        gap0 = cap[side]['over_min'] - trial.keys['top_cm']
        bad_gap = gap > KEY_GAP_MAX_CM + 1e-9
        bad_pen = -gap > KEY_PENETRATION_MAX_CM
        out['key_contact'][side] = {'gap_cm': [_r(v, 5) for v in gap], 'max_gap_cm': _r(np.max(gap)),
                                    'min_gap_cm': _r(np.min(gap)), 'frames_gap_over_band': int(bad_gap.sum()),
                                    'frames_penetration_over_limit': int(bad_pen.sum()),
                                    'gap_over_band_times_s': frame_list(bad_gap, times),
                                    'min_over_key_vertices': int(final[side]['over'].min()),
                                    'captured_max_gap_cm': _r(np.max(gap0))}
    # (d) head / camera
    head = trial.ue_joint(W, 'Head')[:, 2] - trial.ue_joint(W_cap, 'Head')[:, 2]
    out['head'] = {'height_change_cm': [_r(head.min()), _r(head.max())],
                   'note': 'the captured head socket moves rigidly with the lowered body; capsule height is the '
                           'runtime\'s and must be re-checked natively'}
    gates_pass = all(v['pass_all_frames'] for v in out['seat'].values()) and \
        all(v['pass_all_frames'] for v in out['soles'].values()) and \
        all(v['after_lowering']['frames_over_arm'] == 0 for v in out['reach'].values()) and \
        all(v['frames_gap_over_band'] == 0 and v['frames_penetration_over_limit'] == 0 for v in out['key_contact'].values())
    out['trial_gates_pass'] = bool(gates_pass)
    out['note'] = ('TRIAL on the actual source capture; the cushion is a proxy unless cushion.proxy is false; '
                   'collisions beyond cushion/floor/keycap heights are not measured; apply natively and re-audit')
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--source', default=str(ROOT / 'private-audit/seat-fit-source.npz'))
    ap.add_argument('--chair', default=None, help='root chair report (actual UE cushion); default: repo proxy')
    ap.add_argument('--cache', default=str(ROOT / 'out/seat-fit-cache'))
    ap.add_argument('--chair-dx', type=float, default=CHAIR_SHIFT_CM[0])
    ap.add_argument('--chair-dy', type=float, default=CHAIR_SHIFT_CM[1])
    ap.add_argument('--out', default=str(ROOT / 'private-audit/native-seat-pose-trial.json'))
    ap.add_argument('--reuse', default=None, help='earlier trial JSON: reuse its solved lowering/raise (report only)')
    args = ap.parse_args(argv)
    source = E.Source.load(args.source)
    if args.chair:
        tri, meta = cushion_from_report(json.loads(Path(args.chair).read_text()))
    else:
        tri, meta = cushion_proxy(args.cache)
    lo, hi = tri.reshape(-1, 3).min(axis=0), tri.reshape(-1, 3).max(axis=0)
    meta.update({'bounds_cm': [[_r(v, 3) for v in lo], [_r(v, 3) for v in hi]], 'root_ue_bounds_cm':
                 [[173.661, -214.063, 44.357], [226.132, -166.341, 51.407]], 'triangles': int(len(tri))})
    trial = Trial(source, tri, keycaps_from_glb(), (args.chair_dx, args.chair_dy))
    if args.reuse:
        old = json.loads(Path(args.reuse).read_text())
        L = old['lowering']['body_lowering_cm']
        interval = tuple(old['lowering']['feasible_interval_cm'])
        raise_cm = {s: old['soles'][f'{s}_sole']['foot_raise_vs_captured_world_cm'] for s in LEGS}
    else:
        L, interval, raise_cm = trial.solve()
    result = report(trial, L, interval, raise_cm, meta)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=1) + '\n')
    print(json.dumps({k: result[k] for k in ('lowering', 'bone_length_max_error_cm', 'foot_world_orientation_max_change_deg',
                                              'head', 'trial_gates_pass')}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
