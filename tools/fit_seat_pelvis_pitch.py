"""TRIAL seated pose: pelvis pitch + lowering, non-stretch leg IK, baked keyboard arm IK, on the ACTUAL inputs.

Labelled `trial`, `verified: false`, `requires_server_reaudit: true`. Nothing here sets a seat receipt or
NativeSeatVerified. It produces importable corrected clips on the owner skeleton (glTF, the same 65 joints as
web/room/char_mixamo.glb) and a per-clip JSON report with raw vs corrected numbers.

Why: a4ed0ce showed that one body lowering cannot seat buttocks and thighs together. At the lowering that makes the
buttocks touch, the captured thighs, which slope down to the knees, go 2.7-3.9 cm into the cushion front.

Correction, per clip (constants solved once on DeskTyping, then reused for every clip):
 (a) PELVIS PITCH theta about the pelvis' own lateral axis (Hips local rotation; pivot = the Spine joint, so the
     spine base does not move) and a vertical LOWERING L. Spine is counter-rotated so the WORLD orientation of
     Spine and everything above it (chest, head, arms) stays as captured; the upper body only translates by -L.
     theta and L are the smallest pitch, and the lowering, that put every seat patch's lowest gap inside the band
     on every frame, centred in the band (equal margin at both edges).
 (b) LEGS: non-stretch two-bone IK (UpLeg/Leg/Foot), knee pole = the captured knee (carried with the pelvis),
     foot WORLD rotation = captured (the genuine toe plant), ankle = captured + one constant vertical raise per leg
     that puts the lowest plantar point on the 2.5 cm support (root's fixed 4171 plantar witness vertices).
 (c) ARMS (DeskTyping): the existing keyboard arm correction (fit_seat_pose_trial.Trial.fit_arms, the Python
     counterpart of SolveCapturedKeyboardArmContact + Sub01KeyboardContactCorrection): over-key distal skin
     minimum -> KeyTop + 0.08 cm, two-bone IK with the captured elbow pole, captured wrist WORLD rotation, finger
     locals untouched. Baked OFFLINE into the clip; the requests over the native 12 cm cap are reported.
 (d) HEAD: the head socket height change is reported.

Gates come from tools/validate_unreal_seat_contact.py and tools/validate_unreal_contact_profile.py, unchanged.

    python tools/export_seat_fit_source.py --out private-audit/seat-fit-source.npz      # uses root's plantar witness
    python tools/fit_seat_pelvis_pitch.py --source private-audit/seat-fit-source.npz \\
        [--chair docs/proposed/native-chair-measured/20261014-actual-native-chair-surface.json | --proxy] \\
        --out-dir docs/proposed/seat-pose-fit
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
import fit_seat_pose_trial as T  # noqa: E402
import life_gltf as G  # noqa: E402
import validate_unreal_contact_profile as contact_profile  # noqa: E402
import validate_unreal_seat_contact as seat_contact  # noqa: E402
import verify_life_idle_candidate as V  # noqa: E402

SCHEMA = 'sub01.seat-pelvis-pitch-trial.v1'
REAL_CHAIR = ROOT / 'docs/proposed/native-chair-measured/20261014-actual-native-chair-surface.json'
CLIPS = ROOT / 'web/room/mh_mx'
SEAT_BAND_CM, SOLE_BAND_CM = seat_contact.SEAT_BAND_CM, seat_contact.SOLE_BAND_CM
MIN_PATCH_VERTICES, MIN_SUPPORT_VERTICES = seat_contact.MIN_PATCH_VERTICES, seat_contact.MIN_SUPPORT_VERTICES
KEY_GAP_MAX_CM = contact_profile.KEY_GAP_MAX_CM
KEY_PENETRATION_MAX_CM = .1                        # validate_unreal_contact_profile: penetrationCm > .1 fails
BAND_CENTRE_CM = sum(SEAT_BAND_CM) / 2
THETA_GRID_DEG = tuple(float(x) for x in np.arange(0, 30.5, 2.))
THETA_REQUIRED_MARGIN_CM = .4                      # choose the smallest pitch with >= 0.4 cm margin at both edges
# Chair XY candidates (root: XY-only chair translation; buttock full-cover dy interval [-52.457, -32.089] in
# 20261014-existing-seat-foot-fit-analysis.json). The earlier rigid-placement candidate first, then two inside the
# cover interval nearer its upper bound.
CHAIR_DY_CANDIDATES_CM = (T.CHAIR_SHIFT_CM[1], -34.5, -32.5)
NATIVE_KEY_CAP_CM = T.KEY_MAX_SHIFT_CM             # 12 cm, reported, never relaxed natively
FOOT_FLOAT_MARGIN_CM = .001
ARM_RAMP_S = .25
SEAM_EASE_S = .5                                   # transitions ease their pitch/lowering to the neighbour's seam value                                   # off-key hand shift eases to/from the key correction over 0.25 s
PER_FRAME_SECANT_ITERATIONS, PER_FRAME_SECANT_TOL_CM = 8, 1e-3
PER_FRAME_STRIDE = 3                               # the pitch need is found every 3rd key, then interpolated
PER_FRAME_SMOOTH_S = .1                            # Gaussian sigma of the per-frame pitch envelope
PER_FRAME_ENVELOPE_S = .15                         # max-filter half width (every frame keeps at least its own need)
STANDING_CAPSULE = {'half_height_cm': 92., 'radius_cm': 17.}
UPPER = ('Spine', 'Spine1', 'Spine2', 'Neck', 'Head', 'LeftShoulder', 'RightShoulder')
FINGER_TOKENS = ('Thumb', 'Index', 'Middle', 'Ring', 'Pinky')
# Stable seated interval (stated, not tuned): hips speed and travel near zero over at least one second.
STABLE_MAX_HIPS_SPEED_CM_S = 2.
STABLE_MAX_HIPS_TRAVEL_CM = 1.
STABLE_MIN_SECONDS = 1.
LOOP_MAX_POSE_CM, LOOP_MAX_VELOCITY_CM_S = V.LOOP_MAX_POSE_CM, V.LOOP_MAX_VELOCITY_CM_S


def _r(v, d=4):
    v = float(v)
    return None if not math.isfinite(v) else (0.0 if round(v, d) == 0 else round(v, d))


# ---------------------------------------------------------------- rotation helpers
def rodrigues(axis, ang):
    """(F, 3, 3) rotations about unit axes (F, 3) by angles (F,) radians."""
    axis = axis / np.linalg.norm(axis, axis=-1, keepdims=True)
    K = np.zeros(axis.shape[:-1] + (3, 3))
    K[..., 0, 1], K[..., 0, 2], K[..., 1, 0] = -axis[..., 2], axis[..., 1], axis[..., 2]
    K[..., 1, 2], K[..., 2, 0], K[..., 2, 1] = -axis[..., 0], -axis[..., 1], axis[..., 0]
    s, c = np.sin(ang)[..., None, None], np.cos(ang)[..., None, None]
    return np.eye(3) + s * K + (1 - c) * (K @ K)


def unit_rot(m):
    return m / np.linalg.norm(m, axis=-2, keepdims=True)


def rot_angle_deg(a, b):
    """Angle between rotation parts of (..., 3, 3) (scale removed)."""
    rel = np.swapaxes(unit_rot(a), -1, -2) @ unit_rot(b)
    return np.degrees(np.arccos(np.clip((np.trace(rel, axis1=-2, axis2=-1) - 1) / 2, -1, 1)))


def quat_from_matrix(m):
    """(F, 3, 3) proper rotations -> (F, 4) xyzw."""
    m = unit_rot(m)
    q = np.zeros(m.shape[:-2] + (4,))
    tr = np.trace(m, axis1=-2, axis2=-1)
    for idx in np.ndindex(m.shape[:-2]):
        r, t = m[idx], tr[idx]
        if t > 0:
            s = math.sqrt(t + 1) * 2
            q[idx] = ((r[2, 1] - r[1, 2]) / s, (r[0, 2] - r[2, 0]) / s, (r[1, 0] - r[0, 1]) / s, s / 4)
        elif r[0, 0] > r[1, 1] and r[0, 0] > r[2, 2]:
            s = math.sqrt(1 + r[0, 0] - r[1, 1] - r[2, 2]) * 2
            q[idx] = (s / 4, (r[0, 1] + r[1, 0]) / s, (r[0, 2] + r[2, 0]) / s, (r[2, 1] - r[1, 2]) / s)
        elif r[1, 1] > r[2, 2]:
            s = math.sqrt(1 + r[1, 1] - r[0, 0] - r[2, 2]) * 2
            q[idx] = ((r[0, 1] + r[1, 0]) / s, s / 4, (r[1, 2] + r[2, 1]) / s, (r[0, 2] - r[2, 0]) / s)
        else:
            s = math.sqrt(1 + r[2, 2] - r[0, 0] - r[1, 1]) * 2
            q[idx] = ((r[0, 2] + r[2, 0]) / s, (r[1, 2] + r[2, 1]) / s, s / 4, (r[1, 0] - r[0, 1]) / s)
    return q / np.linalg.norm(q, axis=-1, keepdims=True)


def smootherstep(x):
    x = np.clip(x, 0., 1.)
    return x * x * x * (x * (6 * x - 15) + 10)


# ---------------------------------------------------------------- (a) pelvis pitch + lowering
def hips_lateral_local(sk: T.Skeleton, W):
    """The pelvis' lateral axis (LeftUpLeg -> RightUpLeg) in the Hips' local frame, mean over frames.
    Positive pitch about it lifts the knees (posterior pelvic tilt)."""
    H = sk.j('Hips')
    lat = W[:, sk.j('RightUpLeg'), :3, 3] - W[:, sk.j('LeftUpLeg'), :3, 3]
    local = np.einsum('fji,fj->fi', unit_rot(W[:, H, :3, :3]), lat)
    a = local.mean(axis=0)
    return a / np.linalg.norm(a)


def pelvis_pitch(sk: T.Skeleton, W, theta_deg, lower_cm, axis_local, weight=None):
    """Rotate the Hips subtree by theta about the pelvis lateral axis through the Spine joint, restore the Spine
    world rotation (counter-rotation), then lower the whole skeleton by L. weight (F,) scales both (transitions)."""
    W = W.copy()
    F = len(W)
    w = np.ones(F) if weight is None else np.asarray(weight, float)
    H, S = sk.j('Hips'), sk.j('Spine')
    axis = np.einsum('fij,j->fi', unit_rot(W[:, H, :3, :3]), axis_local)
    R = rodrigues(axis, np.radians(theta_deg) * w)
    pivot = W[:, S, :3, 3].copy()
    D = np.tile(np.eye(4), (F, 1, 1))
    D[:, :3, :3] = R
    D[:, :3, 3] = pivot - np.einsum('fij,fj->fi', R, pivot)
    spine_old = W[:, S].copy()
    for k in sk.subtree(H):
        W[:, k] = D @ W[:, k]
    new_s = W[:, S].copy()
    new_s[:, :3, :3] = spine_old[:, :3, :3]
    delta = new_s @ np.linalg.inv(W[:, S])
    for k in sk.subtree(S):
        W[:, k] = delta @ W[:, k]
    W[:, :, :3, 3] -= T.UP * (lower_cm * w)[:, None, None] / 100.
    return W


# ---------------------------------------------------------------- inputs
def load_cushion(chair=None, proxy=False, cache=None):
    """Real cushion (root's chair surface report) by default; --proxy only for comparison."""
    if proxy:
        return T.cushion_proxy(cache or ROOT / 'out/seat-fit-cache')
    path = Path(chair or REAL_CHAIR)
    report = json.loads(path.read_text())
    tri, meta = T.cushion_from_report(report)
    meta.update({'file': str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
                 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                 'chair_transform': report.get('chair', {}).get('transform'),
                 'chair_component_world_bounds_cm': report.get('chair', {}).get('component_world_bounds_cm'),
                 'chair_collision': {k: str(report.get('chair', {}).get(k)) for k in
                                     ('collision_enabled', 'collision_profile', 'collision_trace_flag')}})
    return tri, meta


def clip_source(base: E.Source, clip_path, times=None):
    """The compact source (same owner vertex sets) driven by another clip's joint worlds (its own key times)."""
    g = G.Gltf(clip_path)
    if times is None:
        times = g.animation().key_times()
    W, parents = E.joint_worlds(g, base.names, times)
    if not np.array_equal(parents, base.parents):
        raise ValueError(f'{clip_path}: skeleton hierarchy differs from the owner')
    d = dict(base.d)
    d['joint_world'], d['times'] = W, np.asarray(times, float)
    return E.Source(d), g


# ---------------------------------------------------------------- the fit
class SeatFit:
    def __init__(self, source, cushion_tri, keycaps, chair_shift=T.CHAIR_SHIFT_CM, support_z=T.SUPPORT_Z_CM,
                 axis_local=None):
        self.trial = T.Trial(source, cushion_tri, keycaps, chair_shift, support_z)
        self.sk = self.trial.sk
        self.W0 = self.trial.W0
        self.axis = hips_lateral_local(self.sk, self.W0) if axis_local is None else np.asarray(axis_local)
        self.raise_cm = None

    def foot_raise(self):
        if self.raise_cm is None:
            r = self.trial.solve_foot_raise(self.W0.copy())
            # lowest plantar point at +0.001 cm (float32 storage of the written clip; never below the support)
            self.raise_cm = {k: float(v) + FOOT_FLOAT_MARGIN_CM for k, v in r.items()}
        return self.raise_cm

    def body(self, theta, L, weight=None):
        Wp = pelvis_pitch(self.sk, self.W0, theta, L, self.axis, weight)
        W, legs = self.trial.fit_legs(Wp, self.foot_raise())
        return W, legs

    def seat_stats(self, W, frames=None):
        s = self.trial.seat(W, frames)
        hi = max(float(np.nanmax(s[n]['lowest'])) for n in T.SEAT_PATCHES)
        lo = min(float(np.nanmin(s[n]['lowest'])) for n in T.SEAT_PATCHES)
        return hi, lo, s

    def solve_lowering(self, theta, frames=None, guess=7.):
        """L (cm) that centres the seat patches' lowest gaps in the band: (max lowest + min lowest)/2 = band centre."""
        def f(L):
            hi, lo, _ = self.seat_stats(self.body(theta, L)[0], frames)
            return (hi + lo) / 2 - BAND_CENTRE_CM, hi, lo
        a = guess
        fa, _, _ = f(a)
        b = a + fa
        for _ in range(25):
            fb, hi, lo = f(b)
            if abs(fb) < 1e-5 or fb == fa:
                return b, hi, lo
            a, b, fa = b, b - fb * (b - a) / (fb - fa), fb
        raise RuntimeError('lowering did not converge')

    def bake_arms(self, W, lowering_cm):
        """DeskTyping arms, continuous over the whole clip. Per side and frame:
        * hand over the keys (>= 4 over-key distal vertices): the keyboard correction shift
          KeyTop + 0.08 - over-key minimum (exact on that frame);
        * hand off the keys (mouse / desk): +lowering, i.e. the hand keeps its CAPTURED world height (the desk did not
          move), except within ARM_RAMP_S of an over-key segment, where the shift eases (smootherstep) from the
          segment's boundary value to +lowering, so the hand never jumps when it enters or leaves the keyboard.
        One two-bone IK per frame (captured elbow pole, captured wrist world rotation, finger locals unchanged)."""
        F = len(W)
        times = np.asarray(self.trial.src.times, float)
        Lf = np.broadcast_to(np.asarray(lowering_cm, float), (F,))
        audit = self.trial.key_audit(W)
        info = {}
        for side, chain in T.ARMS.items():
            a = audit[side]
            on = a['over'] >= T.KEY_MIN_OVER_VERTICES
            delta = np.where(on, self.trial.keys['top_cm'] + T.KEY_CONTACT_TARGET_CM - a['over_min'], np.nan)
            shift = Lf.copy()
            if on.any():
                on_idx = np.nonzero(on)[0]
                for f in np.nonzero(~on)[0]:
                    j = on_idx[np.argmin(np.abs(on_idx - f))]
                    d = abs(times[f] - times[j])
                    if d < ARM_RAMP_S:
                        w = float(smootherstep(1 - d / ARM_RAMP_S))
                        shift[f] = Lf[f] + (delta[j] - Lf[f]) * w
                shift[on] = delta[on]
            shoulder, elbow, hand = (W[:, self.sk.j(n), :3, 3] for n in chain)
            arm = (np.linalg.norm(elbow - shoulder, axis=-1) + np.linalg.norm(hand - elbow, axis=-1)) * 100
            effector = hand + T.UP * shift[:, None] / 100.
            requested = np.linalg.norm(effector - shoulder, axis=-1) * 100
            W, reach, _, _ = self.sk.two_bone_pose(W.copy(), chain, effector, elbow)
            info[side] = {'requested_cm': requested, 'arm_cm': arm, 'shift_cm': shift, 'corrected': on,
                          'refused_by_cap': on & (np.abs(np.nan_to_num(delta)) > NATIVE_KEY_CAP_CM),
                          'off_key_frames': int((~on).sum()), 'on_off_changes_s': [_r(times[i + 1], 4) for i in np.nonzero(np.diff(on.astype(int)))[0]],
                          'off_key_shift_minus_lowering_cm': [_r(np.min((shift - Lf)[~on]), 4), _r(np.max((shift - Lf)[~on]), 4)] if (~on).any() else None,
                          'max_shift_step_cm_per_frame': _r(np.abs(np.diff(shift)).max(), 4) if F > 1 else 0.}
        return W, info

    def ramp_arms(self, W, ramp):
        """Transition arms: the keyboard correction of the seam frame (ramp = 1), carried in by a smootherstep ramp:
        per side one vertical hand shift delta (KeyTop + 0.08 - over-key minimum at the seam), applied as
        delta * ramp(t) with the same two-bone IK (captured elbow pole, captured wrist world rotation, finger locals
        unchanged). The approach motion stays genuine; only the seam frame is forced onto the keys."""
        e = int(np.argmax(ramp))
        audit = self.trial.key_audit(W)
        info = {}
        for side, chain in T.ARMS.items():
            a = audit[side]
            if a['over'][e] < T.KEY_MIN_OVER_VERTICES:
                info[side] = {'seam_shift_cm': None, 'reason': 'hand not over the keys at the seam frame'}
                continue
            delta = self.trial.keys['top_cm'] + T.KEY_CONTACT_TARGET_CM - a['over_min'][e]
            shoulder, elbow, hand = (W[:, self.sk.j(n), :3, 3] for n in chain)
            effector = hand + T.UP * (delta * ramp)[:, None] / 100.
            W, reach, length, dist = self.sk.two_bone_pose(W.copy(), chain, effector, elbow)
            info[side] = {'seam_shift_cm': _r(delta), 'reached_all_frames': bool(reach.all()),
                          'min_margin_cm': _r(((length - dist) * 100).min()),
                          'over_native_12cm_cap': bool(abs(delta) > NATIVE_KEY_CAP_CM)}
        return W, info

    def per_frame_stats(self, W):
        s = self.trial.seat(W)
        hi = np.max([np.nan_to_num(s[n]['lowest'], nan=np.inf) for n in T.SEAT_PATCHES], axis=0)
        lo = np.min([np.nan_to_num(s[n]['lowest'], nan=-np.inf) for n in T.SEAT_PATCHES], axis=0)
        band = np.min([s[n]['band'] for n in T.SEAT_PATCHES], axis=0)
        over = np.min([s[n]['over'] for n in T.SEAT_PATCHES], axis=0)
        return hi, lo, band, over

    def solve_lowering_per_frame(self, theta_f, guess_f):
        """Vector secant: per frame, the L that centres that frame's seat lowest gaps in the band."""
        def f(L):
            hi, lo, band, over = self.per_frame_stats(self.body(theta_f, L)[0])
            val = np.where(np.isfinite(hi) & np.isfinite(lo), (hi + lo) / 2 - BAND_CENTRE_CM, 0.)
            return val, hi, lo, band, over
        a = np.asarray(guess_f, float).copy()
        fa = f(a)[0]
        b = a + fa
        for _ in range(PER_FRAME_SECANT_ITERATIONS):
            fb, hi, lo, band, over = f(b)
            if np.all(np.abs(fb) < PER_FRAME_SECANT_TOL_CM):
                break
            den = fb - fa
            step = np.where(np.abs(den) > 1e-12, fb * (b - a) / np.where(np.abs(den) > 1e-12, den, 1.), 0.)
            a, fa, b = b, fb, b - step
        return b, hi, lo, band, over

    def solve_per_frame(self, grid=THETA_GRID_DEG):
        """Per frame: the smallest pitch whose centred lowering leaves >= THETA_REQUIRED_MARGIN_CM at both band
        edges with the support counts met (else the largest margin), found every PER_FRAME_STRIDE-th key and
        interpolated; then a smooth upper envelope of that pitch over time (max filter, Gaussian) and the per-frame
        centred lowering for it on EVERY key (the gates are then measured on every key)."""
        F = len(self.W0)
        all_times = np.asarray(self.trial.src.times, float)
        probe = np.unique(np.r_[np.arange(0, F, PER_FRAME_STRIDE), F - 1])
        sub = SeatFit(self.trial.src.subset(probe), self.trial.cushion_tri - np.array([*self.trial.chair_shift, 0.]),
                      self.trial.keys, self.trial.chair_shift, self.trial.support_z, self.axis)
        sub.raise_cm = self.foot_raise()
        Fp = len(probe)
        L = np.full(Fp, 7.)
        table = []
        settled = np.zeros(Fp, bool)
        for th in grid:
            L, hi, lo, band, over = sub.solve_lowering_per_frame(np.full(Fp, th), L)
            margin = np.minimum(SEAT_BAND_CM[1] - hi, lo - SEAT_BAND_CM[0])
            ok = (margin >= 0) & (band >= MIN_SUPPORT_VERTICES) & (over >= MIN_PATCH_VERTICES)
            table.append((th, L.copy(), margin, ok))
            settled |= ok & (margin >= THETA_REQUIRED_MARGIN_CM)
            if settled.all():
                break
        need_p = np.full(Fp, np.nan)
        for f in range(Fp):
            good = [t for t, _, m, ok in table if ok[f] and m[f] >= THETA_REQUIRED_MARGIN_CM]
            if not good:
                good = [max(((t, m[f]) for t, _, m, ok in table if ok[f]), key=lambda x: x[1], default=(None,))[0]]
            if good[0] is None:
                good = [max(((t, m[f]) for t, _, m, ok in table), key=lambda x: x[1])[0]]
            need_p[f] = good[0]
        # a probe's need holds over its neighbourhood: take the max of the two bracketing probes
        need = np.empty(F)
        for f in range(F):
            k = np.searchsorted(probe, f)
            need[f] = need_p[min(k, Fp - 1)] if probe[min(k, Fp - 1)] == f else max(need_p[max(k - 1, 0)], need_p[min(k, Fp - 1)])
        L_guess = np.interp(np.arange(F), probe, [np.interp(need_p[i], [t for t, *_ in table], [l[i] for _, l, _, _ in table])
                                                  for i in range(Fp)])
        times = all_times
        dt = float(np.median(np.diff(times))) if F > 1 else 1.
        k = int(round(PER_FRAME_ENVELOPE_S / dt))
        env = np.array([need[max(0, f - k):f + k + 1].max() for f in range(F)])
        sig = PER_FRAME_SMOOTH_S / dt
        if F > 1 and sig > 0:
            x = np.arange(-3 * int(math.ceil(sig)), 3 * int(math.ceil(sig)) + 1)
            ker = np.exp(-.5 * (x / sig) ** 2)
            ker /= ker.sum()
            pad = np.pad(env, len(x) // 2, mode='edge')
            smooth = np.convolve(pad, ker, mode='valid')
            theta = np.maximum(smooth, need)     # never below a frame's own need
        else:
            theta = env
        L, hi, lo, band, over = self.solve_lowering_per_frame(theta, L_guess)
        return theta, L, {'theta_needed_deg': [_r(v, 3) for v in need], 'theta_deg': [_r(v, 4) for v in theta],
                          'lowering_cm': [_r(v, 4) for v in L],
                          'theta_range_deg': [_r(theta.min(), 3), _r(theta.max(), 3)],
                          'lowering_range_cm': [_r(L.min(), 4), _r(L.max(), 4)],
                          'lowering_max_rate_cm_s': _r(np.abs(np.diff(L)).max() / dt, 3) if F > 1 else 0.,
                          'theta_max_rate_deg_s': _r(np.abs(np.diff(theta)).max() / dt, 3) if F > 1 else 0.}

    def scan(self, frames, grid=THETA_GRID_DEG):
        rows = []
        L = 7.
        for th in grid:
            L, hi, lo = self.solve_lowering(th, frames, L)
            _, _, s = self.seat_stats(self.body(th, L)[0], frames)
            band_min = {n: int(s[n]['band'].min()) for n in T.SEAT_PATCHES}
            over_min = {n: int(s[n]['over'].min()) for n in T.SEAT_PATCHES}
            margin = min(SEAT_BAND_CM[1] - hi, lo - SEAT_BAND_CM[0])
            rows.append({'theta_deg': th, 'lowering_cm': _r(L, 5), 'max_lowest_gap_cm': _r(hi), 'min_lowest_gap_cm': _r(lo),
                         'edge_margin_cm': _r(margin), 'min_band_vertices': band_min, 'min_over_surface_vertices': over_min,
                         'feasible': bool(margin >= 0 and min(band_min.values()) >= MIN_SUPPORT_VERTICES
                                          and min(over_min.values()) >= MIN_PATCH_VERTICES)})
        return rows

    def choose(self, rows):
        ok = [r for r in rows if r['feasible'] and r['edge_margin_cm'] >= THETA_REQUIRED_MARGIN_CM]
        if ok:
            return ok[0], 'smallest pitch with >= %.1f cm margin at both band edges' % THETA_REQUIRED_MARGIN_CM
        ok = [r for r in rows if r['feasible']]
        if ok:
            return max(ok, key=lambda r: r['edge_margin_cm']), 'no pitch reaches the margin; the largest feasible margin'
        return max(rows, key=lambda r: r['edge_margin_cm']), 'NO feasible pitch; best compromise (largest margin)'


# ---------------------------------------------------------------- gates and residuals
def joint_locals(sk, W, parent_world):
    """(F, J, 4, 4) local matrices; parent_world is the (4, 4) armature matrix above Hips."""
    L = np.empty_like(W)
    for k, p in enumerate(sk.parents):
        P = parent_world if p < 0 else W[:, p]
        L[:, k] = np.linalg.inv(P) @ W[:, k]
    return L


def gates(fit: SeatFit, W, arms_info=None, seated=None, with_keys=False, key_seam=None, require_over=True):
    """All gates per frame (seated mask limits the seat gates; soles on every frame)."""
    tr, sk, W0 = fit.trial, fit.sk, fit.W0
    F = len(W)
    seated = np.ones(F, bool) if seated is None else seated
    out = {'frames': F, 'seated_frames': int(seated.sum())}
    if seated.any():
        s = tr.seat(W[seated])
        s0 = tr.seat(W0[seated])
        out['seat'] = {}
        for n in T.SEAT_PATCHES:
            passed, fails = T.support_gate(s[n], SEAT_BAND_CM)
            p0, _ = T.support_gate(s0[n], SEAT_BAND_CM)
            out['seat'][n] = {
                'pass_all_frames': bool(passed.all()), 'failing_frames': int((~passed).sum()),
                'failures': {k: int(v.sum()) for k, v in fails.items() if v.any()},
                'corrected': {'lowest_gap_cm': [_r(np.nanmin(s[n]['lowest'])), _r(np.nanmax(s[n]['lowest']))],
                              'min_band_vertices': int(s[n]['band'].min()), 'min_over_surface_vertices': int(s[n]['over'].min())},
                'raw': {'pass_frames': int(p0.sum()),
                        'lowest_gap_cm': [_r(np.nanmin(s0[n]['lowest'])), _r(np.nanmax(s0[n]['lowest']))]
                        if np.isfinite(s0[n]['lowest']).any() else None,
                        'min_over_surface_vertices': int(s0[n]['over'].min())}}
    so, so0 = tr.soles(W), tr.soles(W0)
    out['soles'] = {}
    for n in T.SOLE_PATCHES:
        passed, fails = T.support_gate(so[n], SOLE_BAND_CM)
        unseated_pen = int((fails['penetration'] & ~seated).sum())
        passed, fails = passed[seated], {k: v[seated] for k, v in fails.items()}
        p0, _ = T.support_gate(so0[n], SOLE_BAND_CM)
        slide = np.linalg.norm(so[n]['centroid_xy'] - so[n]['centroid_xy'][0], axis=1)
        slide0 = np.linalg.norm(so0[n]['centroid_xy'] - so0[n]['centroid_xy'][0], axis=1)
        out['soles'][n] = {'pass_all_frames': bool(passed.all()), 'failing_frames': int((~passed).sum()),
                           'failures': {k: int(v.sum()) for k, v in fails.items() if v.any()},
                           'corrected': {'lowest_gap_cm': [_r(np.nanmin(so[n]['lowest'])), _r(np.nanmax(so[n]['lowest']))],
                                         'min_band_vertices': int(so[n]['band'].min())},
                           'raw': {'pass_frames': int(p0.sum()),
                                   'lowest_gap_cm': [_r(np.nanmin(so0[n]['lowest'])), _r(np.nanmax(so0[n]['lowest']))]},
                           'added_foot_slide_cm_max': _r(np.abs(slide - slide0).max()),
                           'gated_frames': 'seated frames' if not seated.all() else 'all frames',
                           'unseated_frames_penetration': unseated_pen,
                           'unseated_note': 'stepping frames lift a foot genuinely; only penetration is counted there'}
    # bone lengths
    err = 0.
    for k, p in enumerate(sk.parents):
        if p >= 0:
            a = np.linalg.norm(W0[:, k, :3, 3] - W0[:, p, :3, 3], axis=1)
            b = np.linalg.norm(W[:, k, :3, 3] - W[:, p, :3, 3], axis=1)
            err = max(err, float(np.abs(a - b).max()) * 100)
    out['bone_length_max_error_cm'] = _r(err, 7)
    out['foot_world_rotation_max_change_deg'] = _r(max(float(rot_angle_deg(W0[:, sk.j(c[2]), :3, :3], W[:, sk.j(c[2]), :3, :3]).max())
                                                       for c in T.LEGS.values()), 7)
    up = {n: rot_angle_deg(W0[:, sk.j(n), :3, :3], W[:, sk.j(n), :3, :3]) for n in UPPER}
    dpos = W[:, sk.j('Spine'), :3, 3] - W0[:, sk.j('Spine'), :3, 3]
    out['upper_body_world'] = {'rotation_max_change_deg': {n: _r(v.max(), 7) for n, v in up.items()},
                               'spine_translation_cm': {'vertical': [_r(dpos[:, 1].min() * 100), _r(dpos[:, 1].max() * 100)],
                                                        'horizontal_max': _r(np.linalg.norm(dpos[:, [0, 2]], axis=1).max() * 100, 7)}}
    head = (W[:, sk.j('Head'), 1, 3] - W0[:, sk.j('Head'), 1, 3]) * 100
    out['head_height_change_cm'] = [_r(head.min()), _r(head.max())]
    if with_keys:
        final, cap = tr.key_audit(W), tr.key_audit(W0)
        out['key_contact'] = {}
        for side in T.ARMS:
            gap = final[side]['over_min'] - tr.keys['top_cm']
            gap0 = cap[side]['over_min'] - tr.keys['top_cm']
            over_any = final[side]['over'] > 0
            bad_gap, bad_pen = over_any & (gap > KEY_GAP_MAX_CM + 1e-9), over_any & (-gap > KEY_PENETRATION_MAX_CM)
            if key_seam is None:
                ok = not (bad_gap | bad_pen).any() and (final[side]['over'].min() > 0 or not require_over)
            elif not over_any[key_seam] and cap[side]['over'][key_seam] == 0:
                ok = not bad_pen.any()  # the captured hand is not over the keys at the seam: no contact to require
            else:   # transition: contact is required at the seam frame only; no penetration anywhere
                ok = not bad_pen.any() and bool(over_any[key_seam]) and not bad_gap[key_seam]
            gap_f = np.where(over_any, gap, np.nan)
            gap0 = np.where(cap[side]['over'] > 0, gap0, np.nan)
            out['key_contact'][side] = {
                'pass_all_frames': bool(ok), 'gate': 'every frame' if key_seam is None else f'gap at seam frame {key_seam}; penetration on every frame',
                'seam_gap_cm': None if key_seam is None else _r(gap_f[key_seam]),
                'seam_hand_over_keys': None if key_seam is None else bool(over_any[key_seam]),
                'frames_over_keys': int(over_any.sum()),
                'frames_gap_over_0_2cm': int(bad_gap.sum()), 'frames_penetration_over_0_1cm': int(bad_pen.sum()),
                'corrected_gap_cm': [_r(np.nanmin(gap_f)), _r(np.nanmax(gap_f))] if over_any.any() else None,
                'raw_gap_cm': [_r(np.nanmin(gap0)), _r(np.nanmax(gap0))] if np.isfinite(gap0).any() else None,
                'min_over_key_vertices': int(final[side]['over'].min())}
        if arms_info is not None:
            out['reach'] = {}
            for side, a in arms_info.items():
                over = a['requested_cm'] - a['arm_cm']
                out['reach'][side] = {'arm_length_cm': _r(a['arm_cm'].max()), 'worst_requested_cm': _r(a['requested_cm'].max()),
                                      'min_margin_cm': _r((a['arm_cm'] - a['requested_cm']).min()),
                                      'frames_over_arm_length': int((over > 0).sum()),
                                      'vertical_shift_cm': [_r(np.nanmin(a['shift_cm'])), _r(np.nanmax(a['shift_cm']))],
                                      'frames_over_native_12cm_cap': int(a['refused_by_cap'].sum()),
                                      **{k: a[k] for k in ('off_key_frames', 'on_off_changes_s', 'off_key_shift_minus_lowering_cm',
                                                           'max_shift_step_cm_per_frame') if k in a}}
    return out


def finger_local_error_deg(sk, W0, W, parent_world):
    L0, L1 = joint_locals(sk, W0, parent_world), joint_locals(sk, W, parent_world)
    js = [k for k, n in enumerate(sk.names) if any(t in n for t in FINGER_TOKENS)]
    return float(max(rot_angle_deg(L0[:, k, :3, :3], L1[:, k, :3, :3]).max() for k in js))


def all_pass(g):
    ok = all(v['pass_all_frames'] for v in g.get('seat', {}).values()) and all(v['pass_all_frames'] for v in g['soles'].values())
    if 'key_contact' in g:
        ok &= all(v['pass_all_frames'] for v in g['key_contact'].values())
    if 'reach' in g:
        ok &= all(v['frames_over_arm_length'] == 0 for v in g['reach'].values())
    return bool(ok and g['bone_length_max_error_cm'] <= .01)


# ---------------------------------------------------------------- glTF output
def armature_world(g: G.Gltf, hips_node):
    parent = g.parent.get(hips_node)
    if parent is None:
        return np.eye(4)
    w = G.world_pose(g, G.RestPose, 0.)
    return E.trs(*w[parent])


def write_clip(g: G.Gltf, sk, W, times, out_path, name, labels, extras, keep_from=None):
    """Owner-skeleton glTF clip: every joint's local rotation from W, the Hips translation from W, every other
    captured track unchanged. keep_from: ((node, path) -> per-frame values) override for tracks not in W."""
    clip = g.animation()
    node = {E.short(n.get('name', '')): i for i, n in enumerate(g.nodes) if n.get('name', '').startswith('mixamorig')}
    hips = node['Hips']
    A = armature_world(g, hips)
    Lm = joint_locals(sk, W, A)
    q = quat_from_matrix(Lm[..., :3, :3])
    tracks = {}
    for (n, path) in clip.tracks:
        tracks[(n, path)] = [tuple(clip.sample(n, path, t, None)) for t in times]
    if keep_from:
        tracks.update(keep_from)
    for k, jn in enumerate(sk.names):
        n = node[jn]
        ref = np.array(tracks.get((n, 'rotation'), [tuple(g.rest(n)[1])] * len(times)))
        qq = q[:, k] * np.where(np.sum(q[:, k] * ref, axis=1) < 0, -1., 1.)[:, None]
        tracks[(n, 'rotation')] = [tuple(map(float, v)) for v in qq]
    tracks[(hips, 'translation')] = [tuple(map(float, v)) for v in Lm[:, sk.j('Hips'), :3, 3]]
    bw = G.BinWriter()
    ti = bw.add([float(t - times[0]) for t in times], 'SCALAR', minmax=True)
    anim = {'name': name, 'samplers': [], 'channels': [], 'extras': {'sub01_labels': labels}}
    for (n, prop) in sorted(tracks):
        vi = bw.add(tracks[(n, prop)], 'VEC4' if prop == 'rotation' else 'VEC3')
        anim['samplers'].append({'input': ti, 'output': vi, 'interpolation': 'LINEAR'})
        anim['channels'].append({'sampler': len(anim['samplers']) - 1, 'target': {'node': n, 'path': prop}})
    asset = {'version': '2.0', 'generator': 'SUB01 fit_seat_pelvis_pitch (trial)', 'extras': dict(extras, sub01_labels=labels)}
    nodes = json.loads(json.dumps(g.doc['nodes']))
    for nd in nodes:
        nd.pop('mesh', None), nd.pop('skin', None)
    doc = {'asset': asset, 'scene': 0, 'scenes': g.doc['scenes'], 'nodes': nodes, 'animations': [anim],
           'accessors': bw.accessors, 'bufferViews': bw.views, 'buffers': [{'byteLength': len(bw.data) + (-len(bw.data)) % 4}]}
    return G.write_glb(out_path, doc, bytes(bw.data)), tracks


# ---------------------------------------------------------------- stable interval and seam
def hips_track(g: G.Gltf, times):
    clip = g.animation()
    h = g.by_name['mixamorig:Hips']
    return np.array([G.world_pose(g, clip, t)[h][0] for t in times]) * 100.


def stable_windows(hips_cm, fps, max_speed=STABLE_MAX_HIPS_SPEED_CM_S, max_travel=STABLE_MAX_HIPS_TRAVEL_CM,
                   min_seconds=STABLE_MIN_SECONDS):
    """Maximal frame windows [a, b] where the hips speed stays <= max_speed and every hips position stays within
    max_travel of the window's first frame. Returns (windows, per-frame speed)."""
    hips_cm = np.asarray(hips_cm, float)
    speed = np.zeros(len(hips_cm))
    if len(hips_cm) > 1:
        v = np.gradient(hips_cm, 1. / fps, axis=0)
        speed = np.linalg.norm(v, axis=1)
    out, a = [], 0
    n = len(hips_cm)
    while a < n:
        if speed[a] > max_speed:
            a += 1
            continue
        b = a
        while b + 1 < n and speed[b + 1] <= max_speed and np.linalg.norm(hips_cm[b + 1] - hips_cm[a]) <= max_travel:
            b += 1
        if (b - a) / fps >= min_seconds:
            out.append((a, b))
        a = b + 1
    return out, speed


def seam_measure(shapes_cm, hips_cm, a, b, fps):
    """loop_metrics on arrays: shapes (F, J, 3) joint positions in the hips frame (cm), hips (F, 3) world cm."""
    pose = float(np.linalg.norm(shapes_cm[b] - shapes_cm[a], axis=1).max())
    hw = float(np.linalg.norm(hips_cm[b] - hips_cm[a]))
    vel = 0.
    if b - a >= 2:
        v0, v1 = shapes_cm[a + 1] - shapes_cm[a], shapes_cm[b] - shapes_cm[b - 1]
        vel = float(np.linalg.norm(v1 - v0, axis=1).max() * fps)
    return {'pose_cm': _r(pose, 5), 'hips_world_cm': _r(hw, 5), 'velocity_cm_s': _r(vel, 5),
            'pass': bool(pose <= LOOP_MAX_POSE_CM and hw <= LOOP_MAX_POSE_CM and vel <= LOOP_MAX_VELOCITY_CM_S)}


def hips_frame_shapes(sk, W):
    """(F, J, 3) every joint relative to the hips, in the hips' own frame (cm)."""
    H = sk.j('Hips')
    R = unit_rot(W[:, H, :3, :3])
    return np.einsum('fji,fkj->fki', R, W[:, :, :3, 3] - W[:, H, None, :3, 3]) * 100.


def best_loop(shapes_cm, hips_cm, window, fps, min_seconds=STABLE_MIN_SECONDS):
    """Within a stable window, the [a, b] (>= min_seconds) with the smallest seam pose mismatch."""
    a0, b0 = window
    m = int(round(min_seconds * fps))
    best = None
    for a in range(a0, b0 - m + 1):
        for b in range(a + m, b0 + 1):
            s = seam_measure(shapes_cm, hips_cm, a, b, fps)
            key = (not s['pass'], s['pose_cm'] + s['hips_world_cm'] + s['velocity_cm_s'] / 10)
            if best is None or key < best[0]:
                best = (key, a, b, s)
    return best[1], best[2], best[3]


def seam_blend_arrays(local_q, hips_t, n):
    """The standard captured-pose loop crossfade (tools/leg_ik_life_clip.seam_blend) on arrays:
    O[j] = C[j+N]; the last N+1 frames are slerped / lerped toward C[j+2N-L] with smootherstep weights, so the last
    frame equals the first and the seam velocity is continuous. local_q (F, J, 4), hips_t (F, 3)."""
    L = len(local_q) - 1
    M = L - n
    if n < 1 or M - n < 1:
        raise ValueError('blend window too long for this clip')
    oq, ot, w_out = [], [], []
    for j in range(M + 1):
        qm, tm = local_q[j + n], hips_t[j + n]
        if j < M - n:
            oq.append(qm), ot.append(tm), w_out.append(0.)
            continue
        qp, tp = local_q[j + 2 * n - L], hips_t[j + 2 * n - L]
        w = float(smootherstep((j - (M - n)) / n))
        oq.append(np.array([G.slerp(G.qnorm(a), G.qnorm(b), w) for a, b in zip(qm, qp)]))
        ot.append(tm + (tp - tm) * w)
        w_out.append(w)
    return np.array(oq), np.array(ot), np.array(w_out)


# ---------------------------------------------------------------- orchestration
def ue_point(p_m):
    return E.to_ue(np.asarray(p_m))


def pose_delta(sk, Wa, Wb):
    """Hips world position (cm, UE) and rotation (deg) delta between two single-frame poses."""
    H = sk.j('Hips')
    d = ue_point(Wb[H, :3, 3]) - ue_point(Wa[H, :3, 3])
    return {'hips_delta_cm': [_r(v, 3) for v in d], 'hips_distance_cm': _r(np.linalg.norm(d), 3),
            'hips_rotation_deg': _r(rot_angle_deg(Wa[H, :3, :3], Wb[H, :3, :3]), 3),
            'upper_body_shape_max_cm': _r(np.linalg.norm(hips_frame_shapes(sk, Wb[None])[0] - hips_frame_shapes(sk, Wa[None])[0], axis=1).max(), 3)}


def seated_weight(hips_cm, seated_height_cm, standing_height_cm):
    """1 when the hips are at the seated height, 0 when standing, smootherstep between (transitions)."""
    span = max(standing_height_cm - seated_height_cm, 1e-6)
    return smootherstep((standing_height_cm - hips_cm[:, 1]) / span)


def run(args):
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = E.Source.load(args.source)
    tri, cushion_meta = load_cushion(args.chair, args.proxy, args.cache)
    keys = T.keycaps_from_glb()
    shift = (args.chair_dx, args.chair_dy if args.chair_dy is not None else T.CHAIR_SHIFT_CM[1])
    labels_common = {'label': 'trial', 'verified': False, 'requires_server_reaudit': True,
                     'requires_native_collision_audit': True, 'cushion': cushion_meta['source'],
                     'cushion_is_proxy': bool(cushion_meta.get('proxy')), 'chair_horizontal_shift_cm': list(shift)}
    summary = {'schema': SCHEMA, **labels_common, 'cushion': cushion_meta, 'source_meta': base.meta,
               'gates_from': ['tools/validate_unreal_seat_contact.py', 'tools/validate_unreal_contact_profile.py'],
               'constants': {'seat_band_cm': list(SEAT_BAND_CM), 'sole_band_cm': list(SOLE_BAND_CM),
                             'min_patch_vertices': MIN_PATCH_VERTICES, 'min_support_vertices': MIN_SUPPORT_VERTICES,
                             'key_gap_max_cm': KEY_GAP_MAX_CM, 'key_penetration_max_cm': KEY_PENETRATION_MAX_CM,
                             'key_contact_target_cm': T.KEY_CONTACT_TARGET_CM, 'native_key_cap_cm': NATIVE_KEY_CAP_CM,
                             'support_z_cm': T.SUPPORT_Z_CM}}

    # ---- solve chair dy, theta, L on the DeskTyping audit frames (a 31-frame scan, then all 301)
    # The constants hold for the WHOLE looping clip (every captured key, 0..16.47 s), not only the 3..8 s audit.
    g30 = G.Gltf(CLIPS / 'room_mx_typing.glb')
    src30, _ = clip_source(base, CLIPS / 'room_mx_typing.glb', g30.animation().key_times())
    n30 = len(src30.times)
    subset = np.unique(np.r_[np.arange(0, n30, 16), n30 - 1])
    dys = CHAIR_DY_CANDIDATES_CM if args.chair_dy is None else (args.chair_dy,)
    scans, best = {}, None
    coarse = np.unique(np.r_[np.arange(0, n30, 33), n30 - 1])
    for dy in dys:
        f = SeatFit(src30, tri, keys, (args.chair_dx, dy))
        rows = f.scan(coarse, tuple(float(x) for x in np.arange(0, 30.5, 4.)))
        pick, why = f.choose(rows)
        scans[str(dy)] = rows
        good = pick['feasible'] and pick['edge_margin_cm'] >= THETA_REQUIRED_MARGIN_CM
        key = (not good, pick['theta_deg'], abs(dy - T.CHAIR_SHIFT_CM[1]))
        if best is None or key < best[0]:
            best = (key, dy, f, pick, why)
    _, dy, fit, pick, why = best
    fine = fit.scan(subset, tuple(float(x) for x in np.arange(max(pick['theta_deg'] - 4, 0), pick['theta_deg'] + .01, .5)))
    pick2, why = fit.choose(fine)
    if pick2['feasible']:
        pick = pick2
    rows = scans[str(dy)] + fine
    shift = (args.chair_dx, dy)
    labels_common['chair_horizontal_shift_cm'] = list(shift)
    summary['chair_horizontal_shift_cm'] = list(shift)
    theta = pick['theta_deg']
    L, hi, lo = fit.solve_lowering(theta, None, pick['lowering_cm'])          # all captured keys of the clip
    raised = []
    for _ in range(20):   # the subset scan can miss a frame: confirm on every key, raise the pitch by 0.5 deg if needed
        _, _, s_all = fit.seat_stats(fit.body(theta, L)[0])
        ok = all(T.support_gate(s_all[n], SEAT_BAND_CM)[0].all() for n in T.SEAT_PATCHES)
        if ok and min(SEAT_BAND_CM[1] - hi, lo - SEAT_BAND_CM[0]) >= THETA_REQUIRED_MARGIN_CM:
            break
        raised.append({'theta_deg': theta, 'failing_frames': {n: int((~T.support_gate(s_all[n], SEAT_BAND_CM)[0]).sum())
                                                              for n in T.SEAT_PATCHES}})
        theta += .5
        L, hi, lo = fit.solve_lowering(theta, None, L)
    fit_aud = SeatFit(base, tri, keys, shift, axis_local=fit.axis)              # the 301 native audit frames
    W_aud, legs = fit_aud.body(theta, L)
    W_aud_arms, arms_info = fit_aud.bake_arms(W_aud.copy(), L)
    summary['solve'] = {'theta_scan_coarse_by_chair_dy': scans, 'fine_scan': fine, 'scan_frames': {'coarse': len(coarse), 'fine': len(subset)}, 'chosen_theta_deg': theta,
                        'chosen_chair_dy_cm': dy, 'rule': why + '; chair dy: smallest pitch, ties to the earlier candidate',
                        'lowering_cm': _r(L, 5), 'solved_on': f'all {n30} captured keys of room_mx_typing (0..16.47 s)', 'all_keys_lowest_gap_cm': [_r(lo), _r(hi)],
                        'pelvis_axis_hips_local': [_r(v, 6) for v in fit.axis], 'pivot': 'Spine joint',
                        'foot_raise_cm': {k: _r(v, 5) for k, v in fit.foot_raise().items()},
                        'leg_ik': legs, 'raised_after_all_key_check': raised}
    rows = scans[str(dy)]
    summary['solve']['lowering_only_feasible_by_chair_dy'] = {k: [r for r in v if r['theta_deg'] == 0.][0]['feasible'] for k, v in scans.items()}
    g_aud = gates(fit_aud, W_aud_arms, arms_info, with_keys=True)
    g_aud['finger_local_max_change_deg'] = _r(finger_local_error_deg(fit_aud.sk, fit_aud.W0, W_aud_arms, np.eye(4)), 7)
    summary['desk_typing_audit_frames_in_memory'] = g_aud
    constants = {'theta_deg': theta, 'lowering_cm': round(L, 5), 'axis_local': fit.axis.tolist()}
    reports = {}

    # ---- DeskTyping: every key of the captured clip, then re-read the written GLB at the 301 audit times
    # Written at 60 Hz so the native 3..8 s @60 Hz audit samples are exact keys (no interpolation of the bake).
    g_typing = G.Gltf(CLIPS / 'room_mx_typing.glb')
    kt = g_typing.animation().key_times()
    t60 = [kt[0] + i / 60 for i in range(int(round((kt[-1] - kt[0]) * 60)) + 1)]
    src_full, g_typing = clip_source(base, CLIPS / 'room_mx_typing.glb', t60)
    fit_t = SeatFit(src_full, tri, keys, shift, axis_local=fit.axis)
    W_t, _ = fit_t.body(theta, L)
    W_t, arms_t = fit_t.bake_arms(W_t, L)
    reports['DeskTyping_seated'] = finish_clip(fit_t, g_typing, W_t, out_dir, 'SUB01_DeskTyping_seated', 'DeskTyping_seated',
                                               labels_common, constants, base, tri, keys, shift, arms=True,
                                               source_clip='web/room/mh_mx/room_mx_typing.glb', arms_info=arms_t)

    seam_values = {'DeskTyping_seated': {'first': (float(theta), float(L)), 'last': (float(theta), float(L))}}
    # ---- seated interval: the captured Sitting clip first (root's import), then the repo's seated idle
    stable = {}
    for key, fname in (('Sitting', 'room_mx_sitting.glb'), ('room_seated_idle', 'room_seated_idle.glb'),
                       ('SitToType', 'room_mx_sit_to_type.glb'), ('TypeToSit', 'room_mx_type_to_sit.glb')):
        g = G.Gltf(CLIPS / fname)
        times = g.animation().key_times()
        fps = (len(times) - 1) / (times[-1] - times[0])
        hips = hips_track(g, times)
        wins, speed = stable_windows(hips, fps)
        rec = {'file': f'web/room/mh_mx/{fname}', 'duration_s': _r(times[-1] - times[0]), 'fps': _r(fps, 3),
               'hips_travel_cm': _r(np.linalg.norm(hips.max(0) - hips.min(0))), 'hips_max_speed_cm_s': _r(speed.max()),
               'thresholds': {'max_hips_speed_cm_s': STABLE_MAX_HIPS_SPEED_CM_S, 'max_hips_travel_cm': STABLE_MAX_HIPS_TRAVEL_CM,
                              'min_seconds': STABLE_MIN_SECONDS},
               'stable_windows_s': [[_r(times[a]), _r(times[b])] for a, b in wins]}
        if wins:
            src_c, _ = clip_source(base, CLIPS / fname, times)
            sk = T.Skeleton(src_c)
            shapes = hips_frame_shapes(sk, src_c.joint_world)
            a, b = max(wins, key=lambda w: w[1] - w[0])
            la, lb, seam = best_loop(shapes, hips, (a, b), fps)
            rec['best_loop_s'] = [_r(times[la]), _r(times[lb])]
            rec['best_loop_frames'] = [la, lb]
            rec['raw_seam'] = seam
        stable[key] = rec
    summary['stable_seated_interval'] = stable

    # ---- SeatedIdle: only from an actually stable interval; Sitting first, else the repo's captured seated idle
    idle_src = None
    for key in ('Sitting', 'room_seated_idle'):
        if stable[key].get('best_loop_frames'):
            idle_src = key
            break
    if idle_src is None:
        summary['SeatedIdle'] = {'bound': False, 'loop_gate': False, 'reason': 'no stable window in any seated source'}
    else:
        rec = stable[idle_src]
        la, lb = rec['best_loop_frames']
        g = G.Gltf(ROOT / rec['file'])
        times = g.animation().key_times()[la:lb + 1]
        src_i, _ = clip_source(base, ROOT / rec['file'], times)
        fit_i = SeatFit(src_i, tri, keys, shift, axis_local=fit.axis)
        th_i, L_i, pf = fit_i.solve_per_frame()
        # loop: the first and last keys share one pitch/lowering (the larger need), so the loop seam stays closed
        th_i[0] = th_i[-1] = max(th_i[0], th_i[-1])
        L_i[0] = L_i[-1] = max(L_i[0], L_i[-1])
        seam_values['SeatedIdle'] = {'first': (float(th_i[0]), float(L_i[0])), 'last': (float(th_i[-1]), float(L_i[-1]))}
        W_i, _ = fit_i.body(th_i, L_i)
        c_i = {'theta_deg': pf['theta_range_deg'], 'lowering_cm': pf['lowering_range_cm'], 'per_frame': pf}
        reports['SeatedIdle'] = finish_clip(fit_i, g, W_i, out_dir, 'SUB01_SeatedIdle', 'SeatedIdle', labels_common, c_i,
                                            base, tri, keys, shift, arms=False, source_clip=rec['file'],
                                            loop=True, window_s=rec['best_loop_s'])
        reports['SeatedIdle']['source_choice'] = (
            'captured Sitting stable window' if idle_src == 'Sitting' else
            'Sitting has NO stable window (it is a sit-down transition); the repo\'s captured room_seated_idle loop '
            'is used instead and must be imported as a NEW asset (SUB01_SeatedIdle), not as SUB01_Sitting')

    # ---- transitions: correction weighted by how seated the hips are
    seated_h = float(hips_track(g_typing, [0.])[0, 1])
    for name, fname, arms_end in (('SitDown', 'room_mx_stand_to_sit.glb', False), ('GetUp', 'room_mx_sit_to_stand.glb', False),
                                  ('SitToType', 'room_mx_sit_to_type.glb', True), ('TypeToSit', 'room_mx_type_to_sit.glb', True)):
        src_c, g = clip_source(base, CLIPS / fname)
        times = src_c.times
        hips = hips_track(g, times)
        standing_h = max(float(hips[:, 1].max()), seated_h + 1.)
        w = seated_weight(hips, seated_h, standing_h) if hips[:, 1].max() - hips[:, 1].min() > 1. else np.ones(len(times))
        fit_c = SeatFit(src_c, tri, keys, shift, axis_local=fit.axis)
        fps = (len(times) - 1) / (times[-1] - times[0])
        speed = np.linalg.norm(np.gradient(hips, 1. / fps, axis=0), axis=1)
        at_height = w > .999
        settled = at_height & (speed <= STABLE_MAX_HIPS_SPEED_CM_S) if not at_height.all() else at_height
        seated = np.nonzero(settled)[0]
        sub = SeatFit(src_c.subset(seated), tri, keys, shift, axis_local=fit.axis)
        sub.raise_cm = fit_c.foot_raise()
        th_s, L_s, pf = sub.solve_per_frame()
        idx = np.arange(len(times))
        near = seated[np.abs(idx[:, None] - seated[None, :]).argmin(axis=1)]
        pos = {f: i for i, f in enumerate(seated)}
        th_all = np.array([th_s[pos[f]] for f in near]) * w
        L_all = np.array([L_s[pos[f]] for f in near]) * w
        # Seams: ease the pitch/lowering into the neighbouring corrected clip's value at the shared seam frame, so the
        # chain SitDown -> SeatedIdle -> SitToType -> DeskTyping -> TypeToSit -> SeatedIdle -> GetUp has no pitch pop.
        nb = {'SitDown': (None, ('SeatedIdle', 'first')), 'GetUp': (('SeatedIdle', 'last'), None),
              'SitToType': (('SeatedIdle', 'last'), ('DeskTyping_seated', 'first')),
              'TypeToSit': (('DeskTyping_seated', 'last'), ('SeatedIdle', 'first'))}[name]
        tt = np.asarray(times, float)
        span = min(SEAM_EASE_S, (tt[-1] - tt[0]) / 2)
        seam_info = {}
        for end, ref in zip(('start', 'end'), nb):
            if ref is None or ref[0] not in seam_values:
                continue
            th_t, L_t = seam_values[ref[0]][ref[1]]
            d = (tt - tt[0]) if end == 'start' else (tt[-1] - tt)
            r = smootherstep(1 - d / span)
            th_all = th_all + (th_t - th_all) * r
            seam_info[end] = {'neighbour': f'{ref[0]}.{ref[1]}', 'theta_deg': _r(th_t, 4), 'neighbour_lowering_cm': _r(L_t, 4),
                              'ease_s': _r(span, 3)}
        if seam_info:
            # the lowering is re-solved (band-centred) for the eased pitch on every gated frame
            L_g, *_ = sub.solve_lowering_per_frame(th_all[seated], L_all[seated])
            L_all = np.array([L_g[pos[f]] for f in near]) * w
            L_all[seated] = L_g
            for end in seam_info:
                f = 0 if end == 'start' else len(times) - 1
                seam_info[end]['own_lowering_at_seam_cm'] = _r(L_all[f], 4)
                seam_info[end]['vertical_mismatch_cm'] = _r(L_all[f] - seam_info[end]['neighbour_lowering_cm'], 4)
        W_c, _ = fit_c.body(th_all, L_all)
        c_c = {'theta_deg': pf['theta_range_deg'], 'lowering_cm': pf['lowering_range_cm'], 'per_frame_on_gated_frames': pf,
               'seated_weight': [_r(v, 4) for v in w],
               'gated_frames': 'hips at the seated height AND settled (hips speed <= %.1f cm/s)' % STABLE_MAX_HIPS_SPEED_CM_S
               if not at_height.all() else 'all frames (hips stay at the seated height)',
               'gated_frame_count': int(settled.sum()), 'at_seat_height_frame_count': int(at_height.sum()),
               'seam_ease': seam_info, 'theta_applied_deg': [_r(v, 4) for v in th_all], 'lowering_applied_cm': [_r(v, 4) for v in L_all]}
        seam = None
        if arms_end:
            u = (np.asarray(times) - times[0]) / (times[-1] - times[0])
            ramp = smootherstep(u if name == 'SitToType' else 1 - u)
            W_c, c_c['arm_ramp'] = fit_c.ramp_arms(W_c, ramp)
            seam = len(times) - 1 if name == 'SitToType' else 0
        reports[name] = finish_clip(fit_c, g, W_c, out_dir, f'SUB01_{name}_seated', name, labels_common, c_c, base, tri,
                                    keys, shift, arms=arms_end, source_clip=f'web/room/mh_mx/{fname}', weight=w,
                                    gate_mask=settled, key_seam=seam)

    # ---- alignment between clips (corrected), plus raw for comparison
    summary['alignment'] = alignment(base, out_dir, reports)
    summary['capsule'] = capsule_envelope(reports, cushion_meta, shift)
    summary['clips'] = {k: {kk: v[kk] for kk in ('glb', 'bytes', 'sha256', 'all_gates_pass', 'audit') if kk in v}
                        for k, v in reports.items()}
    summary['trial_gates_pass'] = {k: v['all_gates_pass'] for k, v in reports.items()}
    (out_dir / 'seat-pose-fit.report.json').write_text(json.dumps(summary, indent=1) + '\n')
    return summary, reports


def finish_clip(fit, g, W, out_dir, asset, role, labels_common, constants, base, tri, keys, shift, arms, source_clip,
                arms_info=None, weight=None, loop=False, window_s=None, gate_mask=None, key_seam=None):
    times = list(map(float, fit.trial.src.times))
    labels = dict(labels_common, role=role, source_clip=source_clip,
                  corrections=['pelvis_pitch_about_hips_lateral_axis_pivot_spine', 'vertical_lowering',
                               'spine_counter_rotation_keeps_upper_body_world_orientation',
                               'non_stretch_two_bone_leg_ik_captured_knee_pole_captured_foot_world_rotation',
                               'constant_per_leg_foot_raise_to_support'] +
                              (['baked_keyboard_arm_ik_captured_elbow_pole_captured_wrist_world_rotation_finger_locals_unchanged']
                               if arms else []) + (['seam_blend'] if loop else []) +
                              (['correction_weighted_by_seated_hips_height'] if weight is not None else []),
                  theta_deg=constants['theta_deg'], lowering_cm=constants['lowering_cm'],
                  foot_raise_cm={k: round(v, 5) for k, v in fit.foot_raise().items()})
    if window_s:
        labels['source_window_s'] = window_s
    rep = {'role': role, 'asset': f'/Game/Sub01Hands/Seating/{asset}', 'labels': labels,
           'correction_curve': {k: v for k, v in constants.items() if k not in ('theta_deg', 'lowering_cm', 'axis_local')}}
    sk = fit.sk
    seated = gate_mask
    mem = gates(fit, W, arms_info, seated=seated, with_keys=arms, key_seam=key_seam, require_over=False)
    mem['note'] = 'every key of the written clip in memory; over-key contact is gated where the hand is over the keys'
    rep['in_memory_all_keys'] = mem
    keep = None
    if loop:
        node = {E.short(n.get('name', '')): i for i, n in enumerate(g.nodes) if n.get('name', '').startswith('mixamorig')}
        A = armature_world(g, node['Hips'])
        Lm = joint_locals(sk, W, A)
        q = quat_from_matrix(Lm[..., :3, :3])
        ht = Lm[:, sk.j('Hips'), :3, 3]
        fps = (len(times) - 1) / (times[-1] - times[0])
        shapes, hipsw = hips_frame_shapes(sk, W), ue_point(W[:, sk.j('Hips'), :3, 3])
        raw_seam = seam_measure(shapes, hipsw, 0, len(W) - 1, fps)
        rep['seam'] = {'raw': raw_seam}
        if not raw_seam['pass']:
            n = max(2, int(round(.4 * fps)))
            qb, tb, wts = seam_blend_arrays(q, ht, n)
            Wb = fk_from_locals(sk, W, A, qb, tb, Lm)
            times = [times[j + n] for j in range(len(qb))]
            fit.trial.src = fit.trial.src.subset(np.arange(n, n + len(qb)))
            W = Wb
            shapes, hipsw = hips_frame_shapes(sk, W), ue_point(W[:, sk.j('Hips'), :3, 3])
            rep['seam'].update({'blend_frames': n, 'blend_s': _r(n / fps), 'blended': seam_measure(shapes, hipsw, 0, len(W) - 1, fps)})
        rep['seam']['loop_gate'] = bool(rep['seam'].get('blended', raw_seam)['pass'])
    path = out_dir / f'{asset}.glb'
    sha, _ = write_clip(g, sk, W, times, path, asset, labels, {'sub01_report': f'{asset}.report.json'}, keep)
    rep.update({'glb': str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path), 'sha256': sha,
                'bytes': path.stat().st_size, 'key_count': len(times), 'duration_s': _r(times[-1] - times[0])})
    # Re-read the WRITTEN clip: DeskTyping at the native audit times (3..8 s @60 Hz), else every written key.
    g_out = G.Gltf(path)
    t0 = times[0]
    t_aud = [t - t0 for t in E.TIMES] if role == 'DeskTyping_seated' else [float(t - t0) for t in times]
    W_out, _ = E.joint_worlds(g_out, sk.names, t_aud)
    W_cap, _ = E.joint_worlds(G.Gltf(ROOT / source_clip), sk.names, [t + t0 for t in t_aud])
    d = dict(base.d)
    d['joint_world'], d['times'] = W_cap, np.array(t_aud)
    fit_out = SeatFit(E.Source(d), tri, keys, shift, axis_local=fit.axis)
    w_out = gate_mask                     # transitions: read back at their own keys (same frame count)
    aud = gates(fit_out, W_out, None, seated=w_out, with_keys=arms, key_seam=key_seam)
    if weight is not None and gate_mask is not None and not np.array_equal(gate_mask, weight > .999):
        res = gates(fit_out, W_out, None, seated=weight > .999)
        aud['residual_on_all_seat_height_frames'] = {'seat': res.get('seat'), 'note': 'frames where the hips are at the seated '
                                                     'height but still sliding back/forward on the cushion (not gated)'}
    if role == 'DeskTyping_seated':
        _, reach = fit_out.trial.fit_arms(W_out.copy(), max_shift_cm=NATIVE_KEY_CAP_CM)
        aud['runtime_correction_after_bake'] = {
            side: {'vertical_shift_cm': [_r(np.nanmin(r['shift_cm'])), _r(np.nanmax(r['shift_cm']))],
                   'frames_refused_by_12cm_cap': int(r['refused_by_cap'].sum())} for side, r in reach.items()}
    aud['finger_local_max_change_deg'] = _r(finger_local_error_deg(sk, W_cap, W_out, armature_world(g_out, g_out.by_name['mixamorig:Hips'])), 7)
    rep['audit'] = {'times': 'DeskTyping 3..8 s @60 Hz (301, the native audit)' if role == 'DeskTyping_seated' else 'every written key',
                    'read_back_from_written_glb': True, **aud}
    rep['all_gates_pass'] = all_pass(aud)
    rep['hips_path_ue_cm'] = [[_r(v, 3) for v in p] for p in ue_point(W_out[:, sk.j('Hips'), :3, 3])[::max(1, len(W_out) // 30)]]
    rep['first_pose'], rep['last_pose'] = W_out[0], W_out[-1]
    rep['raw_first_pose'], rep['raw_last_pose'] = W_cap[0], W_cap[-1]
    (out_dir / f'{asset}.report.json').write_text(json.dumps({k: v for k, v in rep.items() if not k.endswith('_pose')},
                                                             indent=1) + '\n')
    return rep


def fk_from_locals(sk, W, A, q, hips_t, Lm):
    """World matrices from blended local quaternions (bone translations from the input locals' frame 0)."""
    F = len(q)
    out = np.zeros((F,) + W.shape[1:])
    for k, p in enumerate(sk.parents):
        Lk = np.tile(np.eye(4), (F, 1, 1))
        x, y, z, w = q[:, k].T
        R = np.stack([np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], -1),
                      np.stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], -1),
                      np.stack([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], -1)], -2)
        s = np.linalg.norm(Lm[0, k, :3, 0])
        Lk[:, :3, :3] = R * s
        Lk[:, :3, 3] = hips_t if p < 0 else Lm[0, k, :3, 3]
        out[:, k] = (A if p < 0 else out[:, p]) @ Lk
    return out


def alignment(base, out_dir, reports):
    sk = T.Skeleton(base)
    pairs = [('SitDown', 'last', 'SeatedIdle', 'first'), ('SeatedIdle', 'last', 'SitToType', 'first'),
             ('SitToType', 'last', 'DeskTyping_seated', 'first'), ('DeskTyping_seated', 'last', 'TypeToSit', 'first'),
             ('TypeToSit', 'last', 'SeatedIdle', 'first'), ('SeatedIdle', 'last', 'GetUp', 'first'),
             ('SitDown', 'last', 'SitToType', 'first')]
    out = []
    for a, ea, b, eb in pairs:
        if a in reports and b in reports:
            Wa = reports[a][f'{ea}_pose']
            Wb = reports[b][f'{eb}_pose']
            out.append({'from': f'{a}.{ea}', 'to': f'{b}.{eb}', 'corrected': pose_delta(sk, Wa, Wb),
                        'raw': pose_delta(sk, reports[a][f'raw_{ea}_pose'], reports[b][f'raw_{eb}_pose'])})
    return out


def capsule_envelope(reports, cushion_meta, shift):
    """Seat capsule envelope and root trajectory facts from the corrected clips (UE world cm at the audited body
    transform). Chair collision is only known as the component AABB in the chair report; a swept test against the
    actual chair collision shapes remains a root audit."""
    chair = cushion_meta.get('chair_component_world_bounds_cm')
    out = {'standing_capsule': STANDING_CAPSULE, 'chair_collision_data': 'component AABB only (no collision primitives in the report)'}
    if not chair:
        out['note'] = 'no chair component bounds (proxy run)'
        return out
    lo = np.array(chair['min']) + [shift[0], shift[1], 0]
    hi = np.array(chair['max']) + [shift[0], shift[1], 0]
    out['chair_aabb_after_shift_cm'] = {'min': [_r(v, 3) for v in lo], 'max': [_r(v, 3) for v in hi]}
    sd = reports.get('SitDown')
    if sd:
        start = np.array(sd['hips_path_ue_cm'][0])
        end = np.array(sd['hips_path_ue_cm'][-1])
        dx = max(lo[0] - start[0], 0, start[0] - hi[0])
        dy = max(lo[1] - start[1], 0, start[1] - hi[1])
        clearance = math.hypot(dx, dy) - STANDING_CAPSULE['radius_cm']
        out['approach_point_cm'] = [_r(v, 3) for v in start[:2]]
        out['standing_capsule_at_approach_clearance_to_chair_aabb_cm'] = _r(clearance, 3)
        out['sitdown_hips_travel_cm'] = [_r(v, 3) for v in end - start]
        out['recommended'] = (
            'Keep the CharacterMovement capsule at the approach point (standing size, collision on) and drive the mesh by '
            'the clip\'s hips root motion into the seat (no capsule move, no teleport, no collision disable). '
            'While seated the capsule stays at the approach point; the mesh offset from capsule is the SitDown hips travel. '
            'GetUp reverses it and ends at the same approach point.')
        out['seated_capsule_option'] = {
            'centre_xy_cm': [_r(v, 3) for v in end[:2]], 'radius_cm': 17.,
            'note': 'a capsule at the seated hips XY overlaps the chair AABB by construction; it may only be used with a '
                    'collision channel that ignores the owned chair actor, which counts as a bypass -> NOT recommended'}
        out['root_audit_required'] = ['sweep the standing capsule at the approach point against the actual chair and desk '
                                      'collision (component AABB clearance above is only conservative-by-AABB)',
                                      'skin/chair and foot audits on the imported corrected clips']
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--source', default=str(ROOT / 'private-audit/seat-fit-source.npz'))
    ap.add_argument('--chair', default=None, help='chair surface report (default: the committed actual native report)')
    ap.add_argument('--proxy', action='store_true', help='use the repo GLB proxy cushion instead (comparison only)')
    ap.add_argument('--cache', default=str(ROOT / 'out/seat-fit-cache'))
    ap.add_argument('--chair-dx', type=float, default=T.CHAIR_SHIFT_CM[0])
    ap.add_argument('--chair-dy', type=float, default=None, help='fix the chair dy (default: solve over CHAIR_DY_CANDIDATES_CM)')
    ap.add_argument('--out-dir', default=str(ROOT / 'docs/proposed/seat-pose-fit'))
    args = ap.parse_args(argv)
    summary, _ = run(args)
    print(json.dumps({'solve': {k: v for k, v in summary['solve'].items() if k != 'theta_scan_on_31_frames'},
                      'trial_gates_pass': summary['trial_gates_pass']}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
