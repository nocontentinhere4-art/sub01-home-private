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
    # ---- the ACTUAL chair: the chair is never moved; the body is placed at E.BODY_CM - shift instead, and every clip
    # is re-measured there (finish_clip). The placement search shows whether one body placement serves both the seat
    # and the keyboard on the actual chair.
    body_offset = body_offset_for(shift)
    placement = {'body_offset': body_offset, 'chair': cushion_meta}
    scan_frames = np.unique(np.linspace(0, len(fit_aud.trial.src.times) - 1, PLACEMENT_SCAN_FRAMES).round().astype(int))
    scan = placement_scan(fit_aud, theta, L, tri, keys, scan_frames, offset_x=body_offset[0])
    summary['chair_horizontal_shift_cm'] = [0.0, 0.0]
    # The fitted placement on the actual chair (read by tools/unreal_audit_seated_typing_seat_contact.py as
    # source_meta.body_cm / body_yaw); the source export's own audited transform is kept as export_body_cm.
    summary['source_meta'] = dict(base.meta, body_cm=[E.BODY_CM[0] + body_offset[0], E.BODY_CM[1] + body_offset[1],
                                                      E.BODY_CM[2]], body_yaw=E.BODY_YAW,
                                  export_body_cm=list(base.meta.get('body_cm', E.BODY_CM)),
                                  body_cm_rule='the body placement on the ACTUAL chair (chair never moved)')
    summary['actual_chair'] = {
        'rule': 'the native chair transform is protected: the chair stays at its measured transform and only the body '
                'placement is searched; every clip is re-measured with the body at body_cm',
        'chair_report': {k: cushion_meta.get(k) for k in ('file', 'sha256', 'source')},
        'chair_transform': cushion_meta.get('chair_transform'),
        'body_cm': [_r(E.BODY_CM[0] + body_offset[0], 4), _r(E.BODY_CM[1] + body_offset[1], 4), _r(E.BODY_CM[2], 4)],
        'body_yaw': E.BODY_YAW, 'body_offset_from_audited_transform_cm': [_r(v, 4) for v in body_offset],
        'audited_body_cm': list(E.BODY_CM),
        'solver_frame': {'chair_offset_cm': list(shift), 'note': 'the solver measures with the body at the audited '
                         'transform and the cushion offset by chair_offset_cm; identical chair-relative geometry'},
        'keyboard': {'source': keys.get('source'), 'top_cm': _r(keys['top_cm'], 4),
                     'min_cm': [_r(v, 3) for v in keys['key_min']], 'max_cm': [_r(v, 3) for v in keys['key_max']]},
        'placement_search': scan}

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
                                               source_clip='web/room/mh_mx/room_mx_typing.glb', arms_info=arms_t,
                                               placement=placement)

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
                                            loop=True, window_s=rec['best_loop_s'], placement=placement)
        reports['SeatedIdle']['source_choice'] = (
            'captured Sitting stable window' if idle_src == 'Sitting' else
            'Sitting has NO stable window (it is a sit-down transition); the repo\'s captured room_seated_idle loop '
            'is used instead and must be imported as a NEW asset (SUB01_SeatedIdle), not as SUB01_Sitting')

    # ---- transitions: correction weighted by how seated the hips are
    seated_h = float(hips_track(g_typing, [0.])[0, 1])
    for name, fname, arms_end in TRANSITIONS:
        blend = SEAM_BLEND.get(name)
        if blend and blend[1] not in reports:
            blend = None
        tr = fit_transition(name, fname, arms_end, base, tri, keys, shift, fit.axis, seated_h, seam_values,
                            skip_ease=(blend[0],) if blend else ())
        W_c, c_c, gate_mask, per_frame_mask = tr['W'], tr['constants'], tr['settled'], None
        if blend:
            W_c, c_c['seam_blend'], per_frame_mask = seam_blend_search(tr, reports[blend[1]], blend[0])
            gate_mask = per_frame_mask['support']
        seam = None
        if arms_end:
            times = tr['times']
            u = (np.asarray(times) - times[0]) / (times[-1] - times[0])
            ramp = smootherstep(u if name == 'SitToType' else 1 - u)
            W_c, c_c['arm_ramp'] = tr['fit'].ramp_arms(W_c, ramp)
            seam = len(times) - 1 if name == 'SitToType' else 0
        reports[name] = finish_clip(tr['fit'], tr['g'], W_c, out_dir, f'SUB01_{name}_seated', name, labels_common, c_c, base,
                                    tri, keys, shift, arms=arms_end, source_clip=f'web/room/mh_mx/{fname}', weight=tr['weight'],
                                    gate_mask=gate_mask, key_seam=seam, per_frame=per_frame_mask,
                                    seam_neighbour=reports.get(blend[1]) if blend else None, seam_end=blend[0] if blend else None,
                                    placement=placement)

    # ---- alignment between clips (corrected), plus raw for comparison
    summary['alignment'] = alignment(base, out_dir, reports)
    summary['capsule'] = capsule_envelope(reports, cushion_meta, shift)
    summary['clips'] = {k: {kk: v[kk] for kk in ('glb', 'bytes', 'sha256', 'all_gates_pass', 'fit_frame_all_gates_pass',
                                                 'chair_report', 'audit', 'seam') if kk in v}
                        for k, v in reports.items()}
    summary['trial_gates_pass'] = {k: v['all_gates_pass'] for k, v in reports.items()}
    summary['trial_gates_pass_rule'] = 'on the ACTUAL chair (measured transform, never moved), body at actual_chair.body_cm'
    summary['fit_frame_gates_pass'] = {k: v.get('fit_frame_all_gates_pass') for k, v in reports.items()}
    summary['actual_chair']['clips_pass'] = summary['trial_gates_pass']
    summary['chair_reposition_proposal'] = 'chair-reposition-proposal.json (proposal only; never acceptance)'
    write_proposal(out_dir, base, reports, cushion_meta, shift, body_offset, summary)
    (out_dir / 'seat-pose-fit.report.json').write_text(json.dumps(summary, indent=1) + '\n')
    return summary, reports


# ---------------------------------------------------------------- the ACTUAL chair (root: the chair transform is protected)
# The seat fit is chair-relative: theta, L, the leg IK and the skin-to-cushion gaps depend only on where the body is
# relative to the cushion. The solver works in a frame where the body sits at the audited transform E.BODY_CM and the
# cushion is offset by `shift`; in the ACTUAL world the chair stays at its measured transform and the BODY is placed at
# E.BODY_CM - shift instead. Every clip is re-measured in that actual world (body translated, chair unshifted, keyboard
# at its world placement), so a gate passes on the actual chair only if it passes there; nothing is inferred.
DESK_ASSET_JSON = ROOT / 'web/house/assets/office-desk-original/desk.json'
DESK_GLB = ROOT / 'web/house/assets/office-desk-original/desk.glb'
NATIVE_DESK = {'centre_xy_cm': (210., -302.), 'top_cm': 84.5, 'yaw_deg': 0.,
               'source': 'coordinator relay of root: native desk centre UE X210 Y-302, tabletop 84.5 cm'}
FLOOR_CM = 2.5001                                   # root: floor top under the seated feet
PLACEMENT_SCAN_BY_CM = tuple(float(v) for v in np.arange(0., 52.5, 2.5))
PLACEMENT_SCAN_FRAMES = 31


def ue_delta_to_gltf(d_ue):
    """A UE world-cm translation as a glTF world-metre translation under the audited body transform (E.to_ue)."""
    o = E.to_ue(np.zeros(3))
    J = np.stack([E.to_ue(np.eye(3)[i]) - o for i in range(3)])          # row i: UE cm per glTF metre along axis i
    return np.linalg.solve(J.T, np.asarray(d_ue, float))


def place_body(W, body_offset_ue):
    """Joint worlds translated so the body stands at E.BODY_CM + body_offset_ue (UE cm, horizontal)."""
    W = np.array(W, copy=True)
    W[..., :3, 3] += ue_delta_to_gltf([body_offset_ue[0], body_offset_ue[1], 0.])
    return W


def body_offset_for(shift):
    """Body placement in the actual world that reproduces the solver's chair-relative geometry."""
    return (-float(shift[0]), -float(shift[1]))


def actual_fit(fit_out, tri, keys, body_offset):
    """The same source and skin, the body at the actual placement, the chair at its measured transform."""
    d = dict(fit_out.trial.src.d)
    d['joint_world'] = place_body(fit_out.trial.src.joint_world, body_offset)
    return SeatFit(E.Source(d), tri, keys, (0., 0.), axis_local=fit_out.axis)


def placement_scan(fit, theta, L, tri, keys, frames, offsets_y=PLACEMENT_SCAN_BY_CM, offset_x=None):
    """Body placement search on the ACTUAL chair (DeskTyping, the given frames, the solved pitch theta and lowering L,
    arms baked as solved). For each body offset along UE +Y (away from the desk, toward the chair): the seat gates
    with the lowering re-centred for that placement, and the keyboard coverage (hands over the key tops)."""
    W_rel, _ = fit.body(theta, L)
    W_rel, _ = fit.bake_arms(W_rel, L)
    W_rel = W_rel[frames]
    sub = fit.trial.src.subset(frames)
    rows = []
    bx = 0. if offset_x is None else offset_x
    for by in offsets_y:
        d = dict(sub.d)
        d['joint_world'] = place_body(sub.joint_world, (bx, by))
        f = SeatFit(E.Source(d), tri, keys, (0., 0.), axis_local=fit.axis)
        f.raise_cm = fit.foot_raise()
        try:
            Lc, hi, lo = f.solve_lowering(theta, None, L)
        except RuntimeError:
            Lc, hi, lo = float('nan'), float('nan'), float('nan')
        Wp = place_body(W_rel, (bx, by))
        Wp[..., :3, 3] -= T.UP * ((Lc - L) if math.isfinite(Lc) else 0.) / 100.
        s = f.trial.seat(Wp)
        seat_ok = all(T.support_gate(s[n], SEAT_BAND_CM)[0].all() for n in T.SEAT_PATCHES)
        ka = f.trial.key_audit(Wp)
        over = {side: int((ka[side]['over'] >= T.KEY_MIN_OVER_VERTICES).sum()) for side in T.ARMS}
        rows.append({'body_offset_cm': [_r(bx, 3), _r(by, 3)], 'seat_lowering_recentred_cm': _r(Lc, 4),
                     'seat_lowest_gap_cm': [_r(lo), _r(hi)],
                     'seat_min_over_surface_vertices': {n: int(s[n]['over'].min()) for n in T.SEAT_PATCHES},
                     'seat_gates_pass_all_frames': bool(seat_ok),
                     'frames_hand_over_keys': over, 'frames': len(frames),
                     'typing_keys_reachable': bool(min(over.values()) == len(frames))})
    seat_ys = [r['body_offset_cm'][1] for r in rows if r['seat_gates_pass_all_frames']]
    key_ys = [r['body_offset_cm'][1] for r in rows if r['typing_keys_reachable']]
    both = [r['body_offset_cm'][1] for r in rows if r['seat_gates_pass_all_frames'] and r['typing_keys_reachable']]
    return {'rule': 'body moved along UE +Y (chair fixed); x offset %.3f cm; pitch %.2f deg and the arm bake as solved; '
                    'lowering re-centred per placement' % (bx, theta),
            'rows': rows, 'seat_feasible_offsets_y_cm': seat_ys, 'keyboard_reachable_offsets_y_cm': key_ys,
            'both_feasible_offsets_y_cm': both, 'typing_feasible_on_actual_chair': bool(both)}


# ---------------------------------------------------------------- desk clearance (proposal data)
def desk_world_samples(centre_xy, top_cm, step_cm=1.):
    """Dense points on every desk triangle (desk.glb, Y-up metres, origin at the floor centre) in UE cm at the native
    desk placement (yaw 0). The glb top is 0.845 m; the native top is matched by a vertical offset."""
    g = G.Gltf(DESK_GLB)
    w = G.world_pose(g, G.RestPose, 0.)
    pts = []
    for i, n in enumerate(g.nodes):
        if 'mesh' not in n:
            continue
        M = E.trs(*w[i])
        for pr in g.doc['meshes'][n['mesh']]['primitives']:
            P = E.accessor(g, pr['attributes']['POSITION']) @ M[:3, :3].T + M[:3, 3]
            idx = E.accessor(g, pr['indices']).astype(int).reshape(-1, 3)
            a, b, c = P[idx[:, 0]], P[idx[:, 1]], P[idx[:, 2]]
            for ta, tb, tc in zip(a, b, c):
                ln = max(np.linalg.norm(tb - ta), np.linalg.norm(tc - ta), np.linalg.norm(tc - tb)) * 100
                k = max(1, int(math.ceil(ln / step_cm)))
                u, v = np.meshgrid(np.arange(k + 1) / k, np.arange(k + 1) / k)
                m = u + v <= 1
                pts.append(ta + np.outer(u[m], tb - ta) + np.outer(v[m], tc - ta))
    P = np.concatenate(pts)
    ue = np.stack([P[:, 0], P[:, 2], P[:, 1]], -1) * 100.
    top = ue[:, 2].max()
    ue[:, 0] += centre_xy[0]
    ue[:, 1] += centre_xy[1]
    ue[:, 2] += top_cm - top
    return ue


def owner_skin(stride=6, cache=None):
    """Every stride-th skinned owner vertex (all skinned primitives): bind position, joints, weights (LBS)."""
    g = G.Gltf(E.decoded(E.OWNER, cache or ROOT / 'out/seat-fit-cache'))
    d = g.doc
    pos, jts, wts = [], [], []
    seen = set()
    for node in d['nodes']:
        if 'mesh' not in node or node.get('skin') != 0 or node['mesh'] in seen:
            continue
        seen.add(node['mesh'])
        for pr in d['meshes'][node['mesh']]['primitives']:
            a = pr['attributes']
            pos.append(E.accessor(g, a['POSITION'])[::stride])
            jts.append(E.accessor(g, a['JOINTS_0']).astype(int)[::stride])
            wts.append(E.accessor(g, a['WEIGHTS_0'])[::stride])
    pos, jts, wts = np.concatenate(pos), np.concatenate(jts), np.concatenate(wts)
    keep = wts.sum(1) > 0
    return pos[keep], jts[keep], wts[keep] / wts[keep].sum(1, keepdims=True)


def skin_points(skin, ibm, W):
    """(F, V, 3) glTF metres, linear blend skinning."""
    pos, jts, wts = skin
    M = W @ ibm                                                # (F, J, 4, 4)
    hom = np.c_[pos, np.ones(len(pos))]
    out = np.zeros((len(W), len(pos), 3))
    for k in range(4):
        Mk = M[:, jts[:, k], :3, :]                            # (F, V, 3, 4)
        out += wts[None, :, k, None] * np.einsum('fvij,vj->fvi', Mk, hom)
    return out


def desk_clearance(skin, ibm, W, body_offset, desk_pts, desk_top_cm, desk_thickness_cm, names, bin_cm=2.):
    """Body skin vs the desk at the native placement, every frame. Per 2 cm XY bin the desk structure spans from its
    lowest desk-mesh point up to the top (legs, aprons, drawers, desktop); bins without desk geometry (the cable
    opening) are open. Reported: the clearance of skin under the structure (knees / thighs under the tabletop), and
    skin INSIDE the structure (between its lowest point and the top): samples, frames, the deepest penetration below
    the top and the body parts (dominant joint) involved. Skin above the top (hands on the keys) is not counted."""
    lo, hi = desk_pts.min(0), desk_pts.max(0)
    nx, ny = int(math.ceil((hi[0] - lo[0]) / bin_cm)) + 1, int(math.ceil((hi[1] - lo[1]) / bin_cm)) + 1
    ix = ((desk_pts[:, 0] - lo[0]) / bin_cm).astype(int)
    iy = ((desk_pts[:, 1] - lo[1]) / bin_cm).astype(int)
    zmin = np.full((nx, ny), np.inf)
    np.minimum.at(zmin, (ix, iy), desk_pts[:, 2])
    dom = skin[1][np.arange(len(skin[1])), skin[2].argmax(1)]
    worst_under, worst_knee, inside, frames_inside, depth = np.inf, -np.inf, 0, 0, 0.
    parts = {}
    for a in range(0, len(W), 40):
        Wp = place_body(W[a:a + 40], body_offset)
        P = E.to_ue(skin_points(skin, ibm, Wp))               # (f, V, 3)
        bx = ((P[..., 0] - lo[0]) / bin_cm).astype(int)
        by = ((P[..., 1] - lo[1]) / bin_cm).astype(int)
        inb = (bx >= 0) & (bx < nx) & (by >= 0) & (by < ny)
        z_struct = np.where(inb, zmin[np.clip(bx, 0, nx - 1), np.clip(by, 0, ny - 1)], np.inf)
        solid = inb & np.isfinite(z_struct)
        below = solid & (P[..., 2] < z_struct)
        if below.any():
            worst_under = min(worst_under, float((z_struct - P[..., 2])[below].min()))
            worst_knee = max(worst_knee, float(P[..., 2][below].max()))
        hit = solid & (P[..., 2] >= z_struct) & (P[..., 2] <= desk_top_cm)
        inside += int(hit.sum())
        frames_inside += int(hit.any(axis=1).sum())
        if hit.any():
            depth = max(depth, float((desk_top_cm - P[..., 2])[hit].max()))
            for j, n in zip(*np.unique(dom[np.nonzero(hit)[1]], return_counts=True)):
                parts[names[j]] = parts.get(names[j], 0) + int(n)
    return {'min_clearance_under_desk_structure_cm': _r(worst_under, 3) if math.isfinite(worst_under) else None,
            'highest_skin_under_desk_structure_cm': _r(worst_knee, 3) if math.isfinite(worst_knee) else None,
            'desktop_underside_cm': _r(desk_top_cm - desk_thickness_cm, 3),
            'skin_samples_inside_desk_structure': inside, 'frames_with_skin_inside_desk_structure': frames_inside,
            'deepest_inside_below_desk_top_cm': _r(depth, 3),
            'inside_by_dominant_joint': dict(sorted(parts.items(), key=lambda kv: -kv[1])[:8]),
            'clear': inside == 0}


# ---------------------------------------------------------------- full-pose seam blend into the SeatedIdle loop
# SitDown ends, and GetUp starts, ON the validated SeatedIdle loop: the captured transition is kept unchanged up to the
# blend window, then every joint's local rotation (slerp) and the Hips translation (lerp) blend toward the SeatedIdle
# loop played in time with the clip (SitDown: the loop's tail, so the last frame IS SeatedIdle's first frame and the
# incoming velocity is the loop's own; GetUp: the loop's head, first frame IS SeatedIdle's last frame). The weight is
# the quintic smootherstep, so the weight's first and second derivatives vanish at both window ends: position,
# velocity and acceleration are continuous into the capture and into the loop.
SEAM_BLEND = {'SitDown': ('end', 'SeatedIdle'), 'GetUp': ('start', 'SeatedIdle')}


def slerp_arrays(q0, q1, w):
    """(F, J, 4) xyzw quaternions, per-frame weight w (F,): shortest-arc slerp, normalised."""
    w = np.asarray(w, float)[:, None, None]
    dot = np.sum(q0 * q1, axis=-1, keepdims=True)
    q1 = np.where(dot < 0, -q1, q1)
    dot = np.clip(np.abs(dot), -1., 1.)
    th = np.arccos(dot)
    s = np.sin(th)
    small = s < 1e-9
    a = np.where(small, 1 - w, np.sin((1 - w) * th) / np.where(small, 1., s))
    b = np.where(small, w, np.sin(w * th) / np.where(small, 1., s))
    q = a * q0 + b * q1
    return q / np.linalg.norm(q, axis=-1, keepdims=True)


def seam_blend_pose(sk, A, W_clip, W_target, w):
    """Per frame f: every joint's LOCAL rotation slerped from the clip toward the target by w[f], the Hips local
    translation lerped, then forward kinematics (bone offsets and scales unchanged: the owner rig). Frames with w == 0
    are the clip and frames with w == 1 the target, exactly (no re-derivation round trip)."""
    w = np.asarray(w, float)
    L0, L1 = joint_locals(sk, W_clip, A), joint_locals(sk, W_target, A)
    mid = (w > 0) & (w < 1)
    out = W_clip.copy()
    if mid.any():
        q = slerp_arrays(quat_from_matrix(L0[mid][..., :3, :3]), quat_from_matrix(L1[mid][..., :3, :3]), w[mid])
        H = sk.j('Hips')
        ht = L0[mid, H, :3, 3] + (L1[mid, H, :3, 3] - L0[mid, H, :3, 3]) * w[mid][:, None]
        out[mid] = fk_from_locals(sk, W_clip[mid], A, q, ht, L0[mid])
    out[w >= 1] = W_target[w >= 1]
    return out


def seam_target(W_loop, end, F):
    """(F, J, 4, 4): the loop played in time with the clip, closed on the seam frame. The loop's first and last frames
    are the same pose (period N - 1). end 'end': the clip's last frame is the loop's FIRST frame and the frames before it
    are the loop's tail (the loop as it plays into its own first frame). end 'start': the clip's first frame is the
    loop's LAST frame and the frames after it are the loop's head (the loop as it plays on from its last frame)."""
    N = len(W_loop)
    period = N - 1
    out = np.empty((F,) + W_loop.shape[1:])
    for k in range(F):
        if end == 'end':
            out[F - 1 - k] = W_loop[0] if k == 0 else W_loop[(-k) % period]
        else:
            out[k] = W_loop[N - 1] if k == 0 else W_loop[k % period]
    return out


def seam_weight(end, F, a, b):
    """Blend weight toward the loop. end 'end': 0 up to frame a, quintic smootherstep a -> b, 1 from frame b to the
    last frame. end 'start': 1 from the first frame to frame a, quintic down to 0 at frame b, 0 after. The quintic's
    first and second derivatives vanish at a and b."""
    idx = np.arange(F, dtype=float)
    x = (idx - a) / max(b - a, 1e-9)
    return smootherstep(x) if end == 'end' else 1. - smootherstep(x)


def seam_blend_legs(sk, W_blend, W_clip, W_target, w, frames=None, foot_lift_cm=None):
    """Feet of the blended frames: each ankle goes from the clip's (fitted) ankle to the loop's ankle along the same
    weight (straight line), its world rotation slerped by the weight (toe plant kept at both ends), plus an optional
    vertical lift per side and frame (foot_lift_cm, cm); non-stretch two-bone IK with the blended knee as pole. Bone
    lengths unchanged. frames (default: 0 < w < 1) are the frames solved; every other frame is untouched."""
    mid = ((w > 0) & (w < 1)) if frames is None else np.asarray(frames, bool)
    info = {}
    if not mid.any():
        return W_blend, info
    Wm = W_blend[mid].copy()
    wm = w[mid]
    for side, chain in T.LEGS.items():
        fj = sk.j(chain[2])
        a, b = W_clip[mid, fj], W_target[mid, fj]
        target = a[:, :3, 3] + (b[:, :3, 3] - a[:, :3, 3]) * wm[:, None]
        if foot_lift_cm is not None:
            target = target + T.UP * np.asarray(foot_lift_cm[side], float)[mid][:, None] / 100.
        qa, qb = quat_from_matrix(a[None, :, :3, :3])[0], quat_from_matrix(b[None, :, :3, :3])[0]
        q = slerp_arrays(qa[:, None], qb[:, None], wm)[:, 0]
        x, y, z, qw = q.T
        R = np.stack([np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * qw), 2 * (x * z + y * qw)], -1),
                      np.stack([2 * (x * y + z * qw), 1 - 2 * (x * x + z * z), 2 * (y * z - x * qw)], -1),
                      np.stack([2 * (x * z - y * qw), 2 * (y * z + x * qw), 1 - 2 * (x * x + y * y)], -1)], -2)
        M = a.copy()
        M[:, :3, :3] = R * np.linalg.norm(a[:, :3, 0], axis=-1)[:, None, None]
        Wm, reach, length, dist = sk.two_bone_pose(Wm, chain, target, Wm[:, sk.j(chain[1]), :3, 3], end_world_rot=M)
        info[side] = {'reached_all_frames': bool(reach.all()), 'min_reach_margin_cm': _r(((length - dist) * 100).min())}
    W_blend = W_blend.copy()
    W_blend[mid] = Wm
    return W_blend, info


SEAM_SEAT_CLEAR_CM = .05           # no-penetration lift target: seat lowest >= band low edge + 0.05 cm
SEAM_SOLE_CLEAR_CM = .002          # sole lowest >= +0.002 cm (float32 storage keeps it >= 0)
SEAM_LIFT_ENVELOPE_FRAMES, SEAM_LIFT_SIGMA_FRAMES, SEAM_LIFT_TAPER_FRAMES = 2, 1.5, 3


def smooth_lift(need, protect):
    """A smooth non-negative lift curve that is never below a frame's own need: max filter, Gaussian, max with the
    need (the solve_per_frame envelope rule), then tapered (smootherstep) to exactly zero on and next to protected
    frames (support-gated frames and frames that are exactly the loop)."""
    need = np.asarray(need, float)
    F = len(need)
    if not (need > 0).any():
        return np.zeros(F)
    k = SEAM_LIFT_ENVELOPE_FRAMES
    env = np.array([need[max(0, f - k):f + k + 1].max() for f in range(F)])
    x = np.arange(-4 * int(math.ceil(SEAM_LIFT_SIGMA_FRAMES)), 4 * int(math.ceil(SEAM_LIFT_SIGMA_FRAMES)) + 1)
    ker = np.exp(-.5 * (x / SEAM_LIFT_SIGMA_FRAMES) ** 2)
    ker /= ker.sum()
    env = np.maximum(np.convolve(np.pad(env, len(x) // 2, mode='edge'), ker, mode='valid'), need)
    prot = np.nonzero(protect)[0]
    if len(prot):
        dist = np.abs(np.arange(F)[:, None] - prot[None, :]).min(axis=1)
        env = env * smootherstep(dist / SEAM_LIFT_TAPER_FRAMES)
    return env


def contact_per_frame(fit, W):
    """Every frame: seat patches (lowest gap, band and over-surface vertex counts) and soles (the same)."""
    s, so = fit.trial.seat(W), fit.trial.soles(W)
    out = {n: {'lowest': s[n]['lowest'], 'band': s[n]['band'], 'over': s[n]['over']} for n in T.SEAT_PATCHES}
    out.update({n: {'lowest': so[n]['lowest'], 'band': so[n]['band'], 'over': so[n]['over'],
                    'centroid_xy': so[n]['centroid_xy']} for n in T.SOLE_PATCHES})
    return out


def per_frame_gate(c, support, sole_support):
    """Every frame gated. support (F,): seat frames in contact -> the full local-support gate (validator constants);
    every other frame -> no penetration (lowest >= band low wherever the patch is over the cushion). Soles: the support
    gate on sole_support frames, no penetration on every frame."""
    F = len(support)
    fail = {}
    for n in T.SEAT_PATCHES + T.SOLE_PATCHES:
        band = SEAT_BAND_CM if n in T.SEAT_PATCHES else SOLE_BAND_CM
        sup = support if n in T.SEAT_PATCHES else sole_support
        passed, fails = T.support_gate(c[n], band)
        over_any = c[n]['over'] > 0
        pen = over_any & (np.nan_to_num(c[n]['lowest'], nan=np.inf) < band[0])
        fail[n] = np.where(sup, ~passed, pen)
    ok = ~np.any([fail[n] for n in fail], axis=0)
    return ok, fail


def rotvec_deg(R):
    """(F, 3, 3) proper rotations -> (F, 3) rotation vectors in degrees (axis * angle)."""
    R = unit_rot(R)
    ang = np.arccos(np.clip((np.trace(R, axis1=-2, axis2=-1) - 1) / 2, -1, 1))
    v = np.stack([R[..., 2, 1] - R[..., 1, 2], R[..., 0, 2] - R[..., 2, 0], R[..., 1, 0] - R[..., 0, 1]], -1)
    s = np.linalg.norm(v, axis=-1, keepdims=True)
    return np.degrees(ang)[..., None] * v / np.maximum(s, 1e-15)


def joint_velocity(Wa, Wb, fps):
    """Per joint: linear velocity (UE cm/s) and world angular velocity (deg/s, rotation vector) from pose a to b."""
    lin = (ue_point(Wb[..., :3, 3]) - ue_point(Wa[..., :3, 3])) * fps
    ang = rotvec_deg(unit_rot(Wb[..., :3, :3]) @ np.swapaxes(unit_rot(Wa[..., :3, :3]), -1, -2)) * fps
    return lin, ang


def pelvis_kinematics(sk, W, fps):
    """Hips: per-step velocity (cm/s, deg/s) and per-frame acceleration (cm/s^2, deg/s^2) by finite differences at the
    key rate (UE world, positions in cm; angular velocity as the world rotation vector of each step)."""
    H = sk.j('Hips')
    v, w = joint_velocity(W[:-1, H], W[1:, H], fps)
    a = np.diff(v, axis=0) * fps
    aa = np.diff(w, axis=0) * fps
    return {'v_cm_s': v, 'speed_cm_s': np.linalg.norm(v, axis=1), 'acc_cm_s2': np.linalg.norm(a, axis=1),
            'ang_vel_deg_s': w, 'ang_speed_deg_s': np.linalg.norm(w, axis=1), 'ang_acc_deg_s2': np.linalg.norm(aa, axis=1)}


SEAM_SEARCH_STEP = 4
SEAM_MAX_PEAK_RATIO = 1.   # the blend never accelerates the pelvis beyond the fitted capture's own peak
SEAM_MIN_FRAMES = 3


def merge_contact(parts, F):
    """Per-frame contact assembled from (frame mask, contact of those frames) parts."""
    out = {}
    for n in parts[0][1]:
        out[n] = {}
        for k in parts[0][1][n]:
            ref = parts[0][1][n][k]
            arr = np.zeros((F,) + ref.shape[1:], dtype=ref.dtype)
            for m, c in parts:
                if m.any():
                    arr[m] = c[n][k]
            out[n][k] = arr
    return out


def touching_sole_speed(c, fps):
    """Per sole: the fastest horizontal centroid motion (cm/s) between frames where the sole touches (both frames'
    lowest gap <= the sole band's upper edge, +1 cm)."""
    out = {}
    for n in T.SOLE_PATCHES:
        xy = np.asarray(c[n]['centroid_xy'], float)
        low = np.nan_to_num(np.asarray(c[n]['lowest'], float), nan=np.inf)
        touch = low <= SOLE_BAND_CM[1]
        sp = np.linalg.norm(np.diff(xy, axis=0), axis=1) * fps
        both = touch[1:] & touch[:-1]
        out[n] = float(sp[both].max()) if both.any() else 0.
    return out


def seam_blend_eval(fit, A, W, Tg, end, a, b, support_base, fps, cache=None):
    """One candidate window. Frames at weight 0 are the fitted clip and frames at weight 1 the loop, exactly, so their
    contact is measured once (cache) and only changed frames are re-skinned. Unsupported frames that would penetrate
    the cushion (or a sole the floor) get a smooth vertical no-penetration lift (smooth_lift; the body is raised, the
    legs re-solved to the same foot targets); support-gated and loop frames are never lifted."""
    F = len(W)
    sk = fit.sk
    w = seam_weight(end, F, a, b)
    support = np.asarray(support_base, bool) | (w >= 1)
    Wpose = seam_blend_pose(sk, A, W, Tg, w)
    Wb, legs = seam_blend_legs(sk, Wpose, W, Tg, w)
    if cache is not None and 'clip' not in cache:
        cache['clip'], cache['loop'] = contact_per_frame(fit, W), contact_per_frame(fit, Tg)
    sel = lambda c, m: {n: {k: v[m] for k, v in d.items()} for n, d in c.items()}

    def measure(Wx, changed):
        if cache is None:
            return contact_per_frame(fit, Wx)
        base = (w <= 0) & ~changed
        loop = (w >= 1) & ~changed
        parts = [(base, sel(cache['clip'], base)), (loop, sel(cache['loop'], loop))]
        rest = ~(base | loop)
        if rest.any():
            parts.append((rest, contact_per_frame(fit, Wx[rest])))
        return merge_contact(parts, F)
    changed = np.zeros(F, bool)
    c = measure(Wb, changed)
    lift = np.zeros(F)
    foot = {side: np.zeros(F) for side in T.LEGS}
    for _ in range(2):
        seat_low = np.nanmin(np.stack([np.where(c[n]['over'] > 0, np.nan_to_num(c[n]['lowest'], nan=np.inf), np.inf)
                                       for n in T.SEAT_PATCHES]), axis=0)
        need = np.where(support, 0., np.maximum(0., SEAT_BAND_CM[0] + SEAM_SEAT_CLEAR_CM - seat_low))
        add = smooth_lift(need, support)
        fneed = {}
        for side, n in zip(('left', 'right'), T.SOLE_PATCHES):
            low = np.nan_to_num(c[n]['lowest'], nan=np.inf)
            moving = (w > 0) & (w < 1) | (add > 0) | (foot[side] > 0)
            fneed[side] = np.where(moving, np.maximum(0., SEAM_SOLE_CLEAR_CM - low), 0.)
        if not (add > 0).any() and not any((v > 0).any() for v in fneed.values()):
            break
        lift += add
        for side in foot:
            foot[side] += smooth_lift(fneed[side], w >= 1)
        changed = ((w > 0) & (w < 1)) | (lift > 0) | np.any([v > 0 for v in foot.values()], axis=0)
        Wl = Wpose.copy()
        Wl[:, :, :3, 3] += T.UP * lift[:, None, None] / 100.
        Wb, legs = seam_blend_legs(sk, Wl, W, Tg, w, frames=changed & (w < 1), foot_lift_cm=foot)
        c = measure(Wb, changed)
    ok, fail = per_frame_gate(c, support, support)
    kin = pelvis_kinematics(sk, Wb, fps)
    return {'a': a, 'b': b, 'w': w, 'W': Wb, 'legs': legs, 'ok': ok, 'support': support, 'contact': c, 'kin': kin,
            'lift_cm': lift, 'foot_lift_cm': foot}


SEAM_REFINE_TOP, SEAM_REFINE_RADIUS = 4, 2


def seam_blend_search(tr, loop_rep, end):
    """Search the blend window [a, b] (frames) on the transition's own fitted frames: a coarse grid (every
    SEAM_SEARCH_STEP frames), then every frame within SEAM_REFINE_RADIUS of the best coarse windows. Every candidate is
    gated on EVERY frame (per_frame_gate: the support gate on the settled frames and the frames that are already the
    loop, no penetration anywhere). Rule, in order: (1) every frame passes; (2) the peak pelvis
    acceleration ratio (peak pelvis linear and angular acceleration over the whole clip, each relative to the fitted
    capture's own peak; the larger) at most SEAM_MAX_PEAK_RATIO, i.e. no abrupt boundary: the blend accelerates the
    pelvis no more than the captured motion itself, and no sole slides faster while touching the floor (lowest gap
    <= +1 cm) than that sole's own fastest touching motion in the fitted capture; (3) the most captured frames kept unchanged (neither blended nor
    lifted); (4) the smallest peak ratio. If no window passes, the candidate with the fewest failing frames, then rule
    2-4, is reported (and the clip fails)."""
    fit, W, F, fps = tr['fit'], tr['W'], len(tr['W']), tr['fps']
    g = tr['g']
    A = armature_world(g, g.by_name['mixamorig:Hips'])
    W_loop = loop_rep['written_world_pose']
    Tg = seam_target(W_loop, end, F)
    kin0 = pelvis_kinematics(fit.sk, W, fps)
    cap_acc, cap_ang = float(kin0['acc_cm_s2'].max()), float(kin0['ang_acc_deg_s2'].max())
    base_support = np.asarray(tr['settled'], bool)
    rows, done, cache, evs = [], set(), {}, {}

    def run(a, b):
        if (a, b) in done or b - a < SEAM_MIN_FRAMES or a < 0 or b > F - 1:
            return
        # The seam STEP itself is the loop's own step (discrete velocity continuity at the key rate): SitDown's last
        # two frames and GetUp's first two frames are exactly loop frames.
        if (end == 'end' and b > F - 2) or (end == 'start' and a < 1):
            return
        done.add((a, b))
        ev = seam_blend_eval(fit, A, W, Tg, end, a, b, base_support, fps, cache)
        nfail = int((~ev['ok']).sum())
        acc, ang = float(ev['kin']['acc_cm_s2'].max()), float(ev['kin']['ang_acc_deg_s2'].max())
        ratio = max(acc / cap_acc, ang / cap_ang)
        if 'clip_touch' not in cache:
            cache['clip_touch'] = touching_sole_speed(cache['clip'], fps)
        touch = touching_sole_speed(ev['contact'], fps)
        feet_ok = all(touch[n] <= cache['clip_touch'][n] + 1e-6 for n in touch)
        kept = int(((ev['w'] <= 0) & (ev['lift_cm'] <= 0)).sum())
        row = {'a': a, 'b': b, 'failing_frames': nfail, 'max_pelvis_acc_cm_s2': _r(acc, 2),
               'max_pelvis_ang_acc_deg_s2': _r(ang, 2), 'peak_ratio_to_capture': _r(ratio, 4),
               'captured_frames_kept': kept, 'lifted_frames': int((ev['lift_cm'] > 0).sum()),
               'max_touching_sole_speed_cm_s': {n: _r(v, 3) for n, v in touch.items()}, 'feet_within_capture': bool(feet_ok),
               'max_lift_cm': _r(ev['lift_cm'].max(), 4)}
        rows.append(row)
        evs[(a, b)] = (row, ev) if nfail == 0 else (row, None)
    key = lambda r: (r['failing_frames'], r['peak_ratio_to_capture'] > SEAM_MAX_PEAK_RATIO + 1e-9 or not r['feet_within_capture'],
                     -r['captured_frames_kept'], r['peak_ratio_to_capture'])
    for a in sorted(set(range(0, F - 1, SEAM_SEARCH_STEP)) | {1}):
        for b in sorted(set(range(a + SEAM_MIN_FRAMES, F, SEAM_SEARCH_STEP)) | {F - 2}):
            run(a, b)
    for r in sorted(rows, key=key)[:SEAM_REFINE_TOP]:
        for a in range(r['a'] - SEAM_REFINE_RADIUS, r['a'] + SEAM_REFINE_RADIUS + 1):
            for b in range(r['b'] - SEAM_REFINE_RADIUS, r['b'] + SEAM_REFINE_RADIUS + 1):
                run(a, b)
    best = min(rows, key=key)
    ev = evs[(best['a'], best['b'])][1] or seam_blend_eval(fit, A, W, Tg, end, best['a'], best['b'], base_support, fps, cache)
    passing = [r for r in rows if r['failing_frames'] == 0]
    info = {'mode': 'full-pose seam blend into %s %s' % (loop_rep['role'], 'first frame (loop tail)' if end == 'end'
                                                          else 'last frame (loop head)'),
            'end': end, 'window_frames': [ev['a'], ev['b']],
            'window_s': [_r(tr['times'][ev['a']] - tr['times'][0], 4), _r(tr['times'][ev['b']] - tr['times'][0], 4)],
            'weight': 'quintic smootherstep (zero 1st and 2nd derivative at both window ends)',
            'frames_exactly_the_loop': int((ev['w'] >= 1).sum()), 'frames_unblended_capture_fit': int((ev['w'] <= 0).sum()),
            'no_penetration_lift': {'frames': [int(i) for i in np.nonzero(ev['lift_cm'] > 0)[0]],
                                    'max_cm': _r(ev['lift_cm'].max(), 4), 'curve_cm': [_r(v, 4) for v in ev['lift_cm']],
                                    'foot_lift_max_cm': {k: _r(v.max(), 4) for k, v in ev['foot_lift_cm'].items()},
                                    'rule': smooth_lift.__doc__.replace('\n', ' ')},
            'search': {'grid_step_frames': SEAM_SEARCH_STEP, 'refine_radius_frames': SEAM_REFINE_RADIUS,
                       'max_peak_ratio': SEAM_MAX_PEAK_RATIO,
                       'min_window_frames': SEAM_MIN_FRAMES, 'candidates': len(rows), 'passing_candidates': len(passing),
                       'capture_fit_max_pelvis_acc_cm_s2': _r(cap_acc, 2),
                       'capture_fit_max_pelvis_ang_acc_deg_s2': _r(cap_ang, 2),
                       'capture_fit_max_touching_sole_speed_cm_s': {n: _r(v, 3) for n, v in cache['clip_touch'].items()},
                       'rule': seam_blend_search.__doc__.split('Rule, in order: ')[1].split(' If no window')[0].replace('\n', ' '),
                       'chosen': best, 'best_passing': sorted(passing, key=key)[:10], 'rows': rows},
            'legs': ev['legs'], 'support_frames': [int(i) for i in np.nonzero(ev['support'])[0]],
            'support_rule': 'seat + sole support gate on the settled seated frames and every frame that is already the '
                            'loop; every other frame: no penetration (lowest >= band low edge)'}
    pf = {'support': ev['support'], 'weight': ev['w'], 'W_pre': W, 'window': (ev['a'], ev['b']), 'fps': fps,
          'end': end}
    return ev['W'], info, pf


def per_frame_report(fa, Wa, pf, rep_times):
    """Every frame of the written clip on the actual chair: contact per patch, the per-frame gate, the worst frame per
    metric, pelvis kinematics (inside vs outside the blend window) and the foot drift added by the blend."""
    c = contact_per_frame(fa, Wa)
    sup = np.asarray(pf['support'], bool)
    ok, fail = per_frame_gate(c, sup, sup)
    F = len(Wa)
    out = {'frames': F, 'support_frames': int(sup.sum()), 'all_frames_pass': bool(ok.all()),
           'failing_frames': [int(i) for i in np.nonzero(~ok)[0]],
           'failing_by_patch': {n: [int(i) for i in np.nonzero(v)[0]] for n, v in fail.items() if v.any()},
           'blend_weight': [_r(v, 5) for v in pf['weight']], 'support_mask': [bool(v) for v in sup],
           'patches': {}, 'worst': {}}
    for n in T.SEAT_PATCHES + T.SOLE_PATCHES:
        band = SEAT_BAND_CM if n in T.SEAT_PATCHES else SOLE_BAND_CM
        low = np.asarray(c[n]['lowest'], float)
        out['patches'][n] = {'lowest_cm': [_r(v, 4) for v in low], 'band_vertices': [int(v) for v in c[n]['band']],
                             'over_vertices': [int(v) for v in c[n]['over']]}
        lowf = np.where(np.isfinite(low), low, np.nan)

        def arg(fn, arr, mask):
            m = mask & np.isfinite(arr)
            if not m.any():
                return None
            i = int(np.nonzero(m)[0][fn(arr[m])])
            return {'value': _r(arr[i], 4), 'frame': i}
        bandv = np.asarray(c[n]['band'], float)
        out['worst'][n] = {'band_cm': list(band),
                           'support_frames_highest_lowest_gap': arg(np.argmax, lowf, sup),
                           'support_frames_deepest_lowest_gap': arg(np.argmin, lowf, sup),
                           'support_frames_fewest_band_vertices': arg(np.argmin, bandv, sup),
                           'all_frames_deepest_lowest_gap': arg(np.argmin, lowf, np.ones(F, bool)),
                           'penetration_frames': int((np.nan_to_num(lowf, nan=np.inf) < band[0]).sum())}
    fps = pf['fps']
    kin = pelvis_kinematics(fa.sk, Wa, fps)
    a, b = pf['window']
    acc_idx = np.arange(1, F - 1)                                  # second differences sit on frames 1..F-2
    inside = (acc_idx >= a) & (acc_idx <= b)
    def mx(v, m):
        return {'value': _r(v[m].max(), 3), 'frame': int(acc_idx[m][np.argmax(v[m])])} if m.any() else None
    out['pelvis'] = {'speed_cm_s': [_r(v, 3) for v in kin['speed_cm_s']],
                     'acc_cm_s2': [_r(v, 2) for v in kin['acc_cm_s2']],
                     'ang_acc_deg_s2': [_r(v, 2) for v in kin['ang_acc_deg_s2']],
                     'max_acc_in_blend_cm_s2': mx(kin['acc_cm_s2'], inside),
                     'max_acc_outside_blend_cm_s2': mx(kin['acc_cm_s2'], ~inside),
                     'max_ang_acc_in_blend_deg_s2': mx(kin['ang_acc_deg_s2'], inside),
                     'max_ang_acc_outside_blend_deg_s2': mx(kin['ang_acc_deg_s2'], ~inside),
                     'note': 'finite differences at the key rate; acc index i is frame i (central second difference)'}
    # foot drift: sole centroid of the blended clip vs the unblended fitted capture (same placement)
    Wp = place_body(pf['W_pre'], pf.get('body_offset', (0., 0.))) if 'body_offset' in pf else None
    if Wp is not None:
        so_b, so_p = fa.trial.soles(Wa), fa.trial.soles(Wp)
        out['foot_drift'] = {}
        for n in T.SOLE_PATCHES:
            d = np.linalg.norm(so_b[n]['centroid_xy'] - so_p[n]['centroid_xy'], axis=1)
            step_b = np.r_[0., np.linalg.norm(np.diff(so_b[n]['centroid_xy'], axis=0), axis=1)] * fps
            step_p = np.r_[0., np.linalg.norm(np.diff(so_p[n]['centroid_xy'], axis=0), axis=1)] * fps
            contact = np.nan_to_num(so_b[n]['lowest'], nan=np.inf) <= SOLE_BAND_CM[1]
            added = np.where(contact, step_b - step_p, -np.inf)
            out['foot_drift'][n] = {
                'max_offset_from_capture_fit_cm': {'value': _r(d.max(), 3), 'frame': int(np.argmax(d))},
                'end_offset_cm': _r(d[-1] if pf['end'] == 'end' else d[0], 3),
                'max_horizontal_speed_while_touching_cm_s': {'blended': _r(np.where(contact, step_b, 0).max(), 3),
                                                              'capture_fit': _r(np.where(contact, step_p, 0).max(), 3)},
                'max_added_speed_while_touching_cm_s': _r(added.max(), 3) if contact.any() else None,
                'touching_frames': int(contact.sum()),
                'note': 'touching = sole lowest gap <= +1 cm; the centroid of the fixed plantar witness set'}
    return out


def seam_report(sk, W_clip, W_loop, end, fps, pf=None):
    """Position and velocity continuity at the seam with the loop, measured on the WRITTEN (read-back) clips.
    end 'end': clip last frame vs loop first frame; incoming velocity = the clip's last step, outgoing = the loop's
    first step. end 'start': loop last frame vs clip first frame; incoming = the loop's last step, outgoing = the
    clip's first step. The loop's own seam (its last step vs its first step) is given for reference."""
    H = sk.j('Hips')
    if end == 'end':
        pa, pb = W_clip[-1], W_loop[0]
        vin, win = joint_velocity(W_clip[-2], W_clip[-1], fps)
        vout, wout = joint_velocity(W_loop[0], W_loop[1], fps)
    else:
        pa, pb = W_loop[-1], W_clip[0]
        vin, win = joint_velocity(W_loop[-2], W_loop[-1], fps)
        vout, wout = joint_velocity(W_clip[0], W_clip[1], fps)
    dp = np.linalg.norm(ue_point(pb[:, :3, 3]) - ue_point(pa[:, :3, 3]), axis=1)
    dr = rot_angle_deg(pa[:, :3, :3], pb[:, :3, :3])
    dv, dw = np.linalg.norm(vout - vin, axis=1), np.linalg.norm(wout - win, axis=1)
    lv, lw = joint_velocity(W_loop[-2], W_loop[-1], fps)
    fv, fw = joint_velocity(W_loop[0], W_loop[1], fps)
    return {'pair': 'clip.last -> loop.first' if end == 'end' else 'loop.last -> clip.first', 'fps': _r(fps, 4),
            'position_delta': {'hips_cm': _r(dp[H], 6), 'max_joint_cm': _r(dp.max(), 6),
                               'hips_rotation_deg': _r(dr[H], 6), 'max_joint_rotation_deg': _r(dr.max(), 6)},
            'velocity_delta': {'hips_cm_s': _r(dv[H], 4), 'max_joint_cm_s': _r(dv.max(), 4),
                               'hips_ang_deg_s': _r(dw[H], 4), 'max_joint_ang_deg_s': _r(dw.max(), 4)},
            'velocity': {'incoming_hips_cm_s': [_r(v, 4) for v in vin[H]], 'outgoing_hips_cm_s': [_r(v, 4) for v in vout[H]]},
            'loop_own_seam_velocity_delta_reference': {
                'hips_cm_s': _r(np.linalg.norm(fv[H] - lv[H]), 4), 'max_joint_cm_s': _r(np.linalg.norm(fv - lv, axis=1).max(), 4),
                'hips_ang_deg_s': _r(np.linalg.norm(fw[H] - lw[H]), 4),
                'max_joint_ang_deg_s': _r(np.linalg.norm(fw - lw, axis=1).max(), 4)}}


TRANSITIONS = (('SitDown', 'room_mx_stand_to_sit.glb', False), ('GetUp', 'room_mx_sit_to_stand.glb', False),
               ('SitToType', 'room_mx_sit_to_type.glb', True), ('TypeToSit', 'room_mx_type_to_sit.glb', True))


def fit_transition(name, fname, arms_end, base, tri, keys, shift, axis, seated_h, seam_values, skip_ease=()):
    """One transition: the per-frame pitch/lowering on its settled seated frames, weighted by how seated the hips are,
    eased into the neighbour's seam value (except at the ends in skip_ease, which get the full-pose seam blend)."""
    src_c, g = clip_source(base, CLIPS / fname)
    times = src_c.times
    hips = hips_track(g, times)
    standing_h = max(float(hips[:, 1].max()), seated_h + 1.)
    w = seated_weight(hips, seated_h, standing_h) if hips[:, 1].max() - hips[:, 1].min() > 1. else np.ones(len(times))
    fit_c = SeatFit(src_c, tri, keys, shift, axis_local=axis)
    fps = (len(times) - 1) / (times[-1] - times[0])
    speed = np.linalg.norm(np.gradient(hips, 1. / fps, axis=0), axis=1)
    at_height = w > .999
    settled = at_height & (speed <= STABLE_MAX_HIPS_SPEED_CM_S) if not at_height.all() else at_height
    seated = np.nonzero(settled)[0]
    sub = SeatFit(src_c.subset(seated), tri, keys, shift, axis_local=axis)
    sub.raise_cm = fit_c.foot_raise()
    th_s, L_s, pf = sub.solve_per_frame()
    idx = np.arange(len(times))
    near = seated[np.abs(idx[:, None] - seated[None, :]).argmin(axis=1)]
    pos = {f: i for i, f in enumerate(seated)}
    th_all = np.array([th_s[pos[f]] for f in near]) * w
    L_all = np.array([L_s[pos[f]] for f in near]) * w
    # Seams: ease the pitch/lowering into the neighbouring corrected clip's value at the shared seam frame, so the
    # chain SitDown -> SeatedIdle -> SitToType -> DeskTyping -> TypeToSit -> SeatedIdle -> GetUp has no pitch pop.
    # An end in skip_ease is closed instead by the full-pose seam blend (seam_blend_search), which supersedes the ease.
    nb = {'SitDown': (None, ('SeatedIdle', 'first')), 'GetUp': (('SeatedIdle', 'last'), None),
          'SitToType': (('SeatedIdle', 'last'), ('DeskTyping_seated', 'first')),
          'TypeToSit': (('DeskTyping_seated', 'last'), ('SeatedIdle', 'first'))}[name]
    tt = np.asarray(times, float)
    span = min(SEAM_EASE_S, (tt[-1] - tt[0]) / 2)
    seam_info = {}
    for end, ref in zip(('start', 'end'), nb):
        if ref is None or ref[0] not in seam_values:
            continue
        if end in skip_ease:
            seam_info[end] = {'neighbour': f'{ref[0]}.{ref[1]}', 'superseded_by': 'full-pose seam blend (seam_blend)'}
            continue
        th_t, L_t = seam_values[ref[0]][ref[1]]
        d = (tt - tt[0]) if end == 'start' else (tt[-1] - tt)
        r = smootherstep(1 - d / span)
        th_all = th_all + (th_t - th_all) * r
        seam_info[end] = {'neighbour': f'{ref[0]}.{ref[1]}', 'theta_deg': _r(th_t, 4), 'neighbour_lowering_cm': _r(L_t, 4),
                          'ease_s': _r(span, 3)}
    eased = [e for e in seam_info if 'superseded_by' not in seam_info[e]]
    if eased:
        # The ease never takes a gated frame below its own pitch need (the same rule as solve_per_frame: never
        # below a key's own need). Between the seam frame (which keeps the neighbour's exact value) and the first/
        # last gated frame the floor is a smootherstep from the seam value to that frame's need.
        need_g = np.asarray(pf['theta_needed_deg'], float)
        floor = np.interp(idx, seated, need_g) * w
        last = len(times) - 1
        for end in eased:
            th_t = seam_info[end]['theta_deg']
            seam_frame = 0 if end == 'start' else len(times) - 1
            if seam_frame in set(seated.tolist()):
                # The seam frame itself is gated: its need and the neighbour's value conflict. No floor on this
                # side (it would only add a pitch pop at the seam); the gates then report the clip honestly.
                d = (tt - tt[0]) if end == 'start' else (tt[-1] - tt)
                floor[d < span] = -np.inf
                seam_info[end]['floor_rule'] = 'not applied: the seam frame is gated and its need conflicts with the neighbour value'
                continue
            if end == 'start':
                g0 = int(seated[0])
                m = idx < g0
                floor[m] = th_t + (need_g[0] - th_t) * smootherstep(idx[m] / max(g0, 1))
                floor[0] = th_t
            else:
                g1 = int(seated[-1])
                m = idx > g1
                floor[m] = th_t + (need_g[-1] - th_t) * smootherstep((last - idx[m]) / max(last - g1, 1))
                floor[last] = th_t
            seam_info[end]['floor_rule'] = ('gated frames never below their own pitch need; the seam frame keeps '
                                            'the neighbour value')
        raised = th_all < floor - 1e-9
        th_all = np.maximum(th_all, floor)
        for end in eased:
            seam_info[end]['frames_raised_to_need_in_clip'] = int(raised.sum())
        # the lowering is re-solved (band-centred) for the eased pitch on every gated frame
        L_g, *_ = sub.solve_lowering_per_frame(th_all[seated], L_all[seated])
        L_all = np.array([L_g[pos[f]] for f in near]) * w
        L_all[seated] = L_g
        for end in eased:
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
    return {'name': name, 'fit': fit_c, 'g': g, 'W': W_c, 'constants': c_c, 'weight': w, 'settled': settled,
            'times': list(map(float, times)), 'fps': fps, 'theta': th_all, 'lowering': L_all}


def write_proposal(out_dir, base, reports, cushion_meta, shift, body_offset, summary, stride=6):
    """Source-only chair-reposition PROPOSAL (never acceptance): written whenever a clip fails on the actual chair.
    Proposed: move the chair by the solver's chair offset so the body keeps the audited transform (the keyboard stays
    reachable). Clearances are measured against the native desk (centre, top from NATIVE_DESK; footprint and structure
    from the repo desk asset) for every written seated clip, at both the proposed and the actual placement."""
    failing = sorted(k for k, v in reports.items() if not v['all_gates_pass'])
    path = out_dir / 'chair-reposition-proposal.json'
    desk_meta = json.loads(DESK_ASSET_JSON.read_text())
    desk = desk_world_samples(NATIVE_DESK['centre_xy_cm'], NATIVE_DESK['top_cm'])
    thickness = float(desk_meta['desktop_thickness_m']) * 100
    skin = owner_skin(stride)
    ibm = np.asarray(base.ibm)
    chair_t = (cushion_meta.get('chair_transform') or {}).get('translation_cm')
    bounds = cushion_meta.get('chair_component_world_bounds_cm') or {}
    proposed_t = None if chair_t is None else [_r(chair_t[0] + shift[0], 4), _r(chair_t[1] + shift[1], 4), _r(chair_t[2], 4)]
    dlo, dhi = desk.min(0), desk.max(0)

    def aabb_gap(off):
        if not bounds:
            return None
        lo = np.array(bounds['min']) + [off[0], off[1], 0]
        hi = np.array(bounds['max']) + [off[0], off[1], 0]
        gx = max(dlo[0] - hi[0], lo[0] - dhi[0], 0.)
        gy = max(dlo[1] - hi[1], lo[1] - dhi[1], 0.)
        overlap_z = lo[2] < dhi[2] and hi[2] > dlo[2]
        return {'chair_aabb_min_cm': [_r(v, 3) for v in lo], 'chair_aabb_max_cm': [_r(v, 3) for v in hi],
                'horizontal_gap_to_desk_aabb_cm': _r(math.hypot(gx, gy), 3), 'gap_x_cm': _r(gx, 3), 'gap_y_cm': _r(gy, 3),
                'aabbs_overlap': bool(gx == 0 and gy == 0 and overlap_z)}
    clips = {}
    for k, rep in reports.items():
        W = rep['readback_world_pose']
        sole_min = min(v['corrected']['lowest_gap_cm'][0] for v in rep['audit']['soles'].values())
        clips[k] = {'frames': len(W), 'fit_frame_all_gates_pass': rep.get('fit_frame_all_gates_pass'),
                    'actual_chair_all_gates_pass': rep['all_gates_pass'],
                    'proposed': desk_clearance(skin, ibm, W, (0., 0.), desk, NATIVE_DESK['top_cm'], thickness, base.names),
                    'actual_placement': desk_clearance(skin, ibm, W, body_offset, desk, NATIVE_DESK['top_cm'], thickness,
                                                       base.names),
                    'feet': {'lowest_sole_gap_to_support_cm': sole_min, 'support_z_cm': T.SUPPORT_Z_CM,
                             'lowest_sole_gap_to_floor_2_5001_cm': _r(sole_min + T.SUPPORT_Z_CM - FLOOR_CM, 4),
                             'feet_on_floor_never_below': bool(sole_min + T.SUPPORT_Z_CM - FLOOR_CM >= -1e-9)}}
    doc = {'schema': 'sub01.chair-reposition-proposal.v1', 'proposal_only': True, 'accepted': False, 'verified': False,
           'requires_root_approval': True,
           'why': ('clips that fail on the ACTUAL chair (chair at its measured transform, body placed on it): %s. '
                   'On the actual chair one body placement cannot both seat the body and reach the keyboard: see '
                   'seat-pose-fit.report.json actual_chair.placement_search.' % (', '.join(failing) or 'none')),
           'failing_on_actual_chair': failing,
           'chair_report': {k: cushion_meta.get(k) for k in ('file', 'sha256')},
           'actual_chair_transform': cushion_meta.get('chair_transform'),
           'proposed_chair_transform': {'translation_cm': proposed_t, 'rotation_xyzw': (cushion_meta.get('chair_transform') or {}).get('rotation_xyzw'),
                                        'scale': (cushion_meta.get('chair_transform') or {}).get('scale'),
                                        'delta_cm': [_r(shift[0], 4), _r(shift[1], 4), 0.0],
                                        'note': 'XY only: no chair raise, no rotation, no scale change'},
           'body_at_proposal_cm': list(E.BODY_CM), 'body_yaw': E.BODY_YAW,
           'body_on_actual_chair_cm': summary['actual_chair']['body_cm'],
           'desk': {**NATIVE_DESK, 'footprint_cm': [[_r(dlo[0], 3), _r(dlo[1], 3)], [_r(dhi[0], 3), _r(dhi[1], 3)]],
                    'structure_z_cm': [_r(dlo[2], 3), _r(dhi[2], 3)], 'desktop_thickness_cm': _r(thickness, 3),
                    'asset': str(DESK_ASSET_JSON.relative_to(ROOT)), 'asset_sha256': desk_meta.get('sha256'),
                    'geometry': 'repo desk.glb (240 x 80 cm, top 84.5 cm, desktop 3.3 cm) placed at the native centre, yaw 0 '
                                '(assumed: root to confirm the native desk mesh, yaw and footprint)'},
           'keyboard': summary['actual_chair']['keyboard'],
           'keyboard_note': ('the fit keyboard is the repo home.js placement; the repo desk centre is UE (200, -310) while the '
                             'native desk centre is (210, -302). If the native keyboard moved with the desk, typing contact '
                             'must be re-solved at the native keyboard before any proposal could be approved.'),
           'chair_vs_desk': {'proposed': aabb_gap(shift), 'actual': aabb_gap((0., 0.))},
           'skin_sampling': f'every {stride}th skinned owner vertex (web/room/char_mixamo.glb), every written frame',
           'clips': clips,
           'root_must_approve': [
               'moving the native chair actor by delta_cm (XY only) to proposed_chair_transform, or an equivalent',
               'the native keyboard world position used for typing (the fit uses the repo home.js keyboard)',
               'a native swept-capsule check of the standing approach to the proposed chair against desk and chair collision',
               'a native seat/foot/keyboard contact audit of the imported clips at the proposed chair (no pass is claimed here)']}
    path.write_text(json.dumps(doc, indent=1) + '\n')
    return doc


def finish_clip(fit, g, W, out_dir, asset, role, labels_common, constants, base, tri, keys, shift, arms, source_clip,
                arms_info=None, weight=None, loop=False, window_s=None, gate_mask=None, key_seam=None, per_frame=None,
                seam_neighbour=None, seam_end=None, placement=None):
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
    if placement is not None:
        rep['chair_report'] = {k: placement['chair'].get(k) for k in ('file', 'sha256', 'source')}
        rep['fit_frame_all_gates_pass'] = rep['all_gates_pass']
        off = placement['body_offset']
        fa = actual_fit(fit_out, tri, keys, off)
        Wa = place_body(W_out, off)
        act = gates(fa, Wa, None, seated=w_out, with_keys=arms, key_seam=key_seam)
        for side, k in act.get('key_contact', {}).items():
            # A hand that is over the keys in the solver frame but not on the actual chair has lost the keyboard: a
            # vacuous 'no contact to require' is never a pass there.
            fit_over = aud['key_contact'][side]['frames_over_keys']
            k['solver_frame_frames_over_keys'] = fit_over
            if k['frames_over_keys'] < fit_over:
                k['pass_all_frames'] = False
                k['keyboard_reach_lost_on_actual_chair'] = True
        act_ok = all_pass(act)
        rep['actual_chair'] = {'chair_moved_cm': [0., 0.], 'chair_transform': placement['chair'].get('chair_transform'),
                               'body_cm': [_r(E.BODY_CM[0] + off[0], 4), _r(E.BODY_CM[1] + off[1], 4), _r(E.BODY_CM[2], 4)],
                               'body_yaw': E.BODY_YAW, 'body_offset_from_audited_transform_cm': [_r(off[0], 4), _r(off[1], 4)],
                               'keyboard': keys.get('source'), 'read_back_from_written_glb': True, 'gates': act}
        if per_frame is not None:
            pf = per_frame_report(fa, Wa, dict(per_frame, body_offset=off), rep_times=t_aud)
            rep['actual_chair']['per_frame'] = pf
            act_ok = act_ok and pf['all_frames_pass']
        rep['actual_chair']['all_gates_pass'] = bool(act_ok)
        rep['all_gates_pass'] = bool(act_ok)
        rep['all_gates_pass_rule'] = ('measured on the ACTUAL chair (measured transform, never moved) with the body at '
                                      'actual_chair.body_cm; fit_frame_all_gates_pass is the chair-relative solver frame')
    if seam_neighbour is not None:
        rep['seam'] = seam_report(sk, W_out, seam_neighbour['readback_world_pose'], seam_end, len(t_aud) and
                                  (len(t_aud) - 1) / (t_aud[-1] - t_aud[0]), per_frame)
    rep['hips_path_ue_cm'] = [[_r(v, 3) for v in p] for p in ue_point(W_out[:, sk.j('Hips'), :3, 3])[::max(1, len(W_out) // 30)]]
    rep['first_pose'], rep['last_pose'] = W_out[0], W_out[-1]
    rep['written_world_pose'], rep['written_times'] = W, times          # in memory, exactly what write_clip wrote
    rep['readback_world_pose'] = W_out
    rep['raw_first_pose'], rep['raw_last_pose'] = W_cap[0], W_cap[-1]
    (out_dir / f'{asset}.report.json').write_text(json.dumps({k: v for k, v in rep.items() if not k.endswith('_pose') and not k.startswith('written_')},
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
