"""Anatomically constrained seated pose on the MEASURED actual chair, gated by origin/main's STRONG seat-patch rule.

29b941b (tools/recheck_seat_fit_main_rule.py) showed that every committed seat-pose-fit clip fails main's rule on every
gated frame through the MEDIAN / COVERAGE conditions (never penetration): the captured toe plant leaves the heels
6.5-8 cm up and the buttocks / posterior-thigh patches are wider than the 3 cm band. No rigid shift can fix that. This
tool re-poses the body instead, with explicit anatomical joint ranges, and judges the result with main's validator
bytes exactly as the recheck does.

Pose model (per frame, applied to the TRUE source capture; the original clips are never edited):
 * PELVIS: tilt about the pelvis' own lateral axis through the Spine joint with the Spine counter-rotated, so the WORLD
   orientation of Spine and everything above it (chest, neck, head, arms, fingers) stays exactly as captured
   (fit_seat_pelvis_pitch.pelvis_pitch); plus a ROOT (Hips) translation: vertical (sit height) and fore-aft (seat
   depth). The upper body therefore only translates.
 * LEGS: non-stretch two-bone IK (UpLeg / Leg / Foot, fit_seat_pose_trial.Skeleton.two_bone_pose: bone lengths exact),
   knee pole = the captured knee carried with the pelvis and swivelled by a hip-rotation angle about the hip-ankle
   line; the ankle target is the captured ankle plus a fore-aft / lateral offset, at the height that puts the lowest
   plantar witness vertex on the floor support (+SOLE_CLEAR_CM).
 * FEET: FLAT, heel down: the foot's world rotation is the bind (standing, plantar-flat) foot rotation turned about the
   vertical by the captured foot's heading (swing-twist about +Y), and the toes (ToeBase / Toe_End) go back to their
   bind locals (neutral MTP). Ankle dorsiflexion / plantarflexion and subtalar inversion / eversion are whatever that
   implies; they are measured and limited (ANATOMICAL_LIMITS_DEG).
No bone is edited, no non-root translation is changed (write_clip writes rotations for every joint and the Hips
translation only; every other captured track is kept), and nothing below the Spine counter-rotation touches the arms.

Measurement: the fitter's own read-back (Trial.seat / Trial.soles patch metrics over the actual cushion triangles and
the 2.5 cm floor support, the owner patch vertex sets of private-audit/seat-fit-source.npz). The optimiser uses a
sparse-matrix form of the SAME linear-blend skinning (FastMeasure, equal to E.Source.skin to 1e-12 m, tested) and the
same T.patch_metrics; the final verdict re-reads the WRITTEN GLB through tools/recheck_seat_fit_main_rule.py's
measure_clip / recheck (main validator bytes, sha256 pinned).

    python tools/solve_seat_pose_anatomical.py --out-dir docs/proposed/seat-pose-anatomical [--max-seconds 3000]
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
import export_seat_fit_source as E  # noqa: E402
import fit_seat_pelvis_pitch as P  # noqa: E402
import fit_seat_pose_trial as T  # noqa: E402
import life_gltf as G  # noqa: E402

SCHEMA = 'sub01.seat-pose-anatomical.v1'
OUT_DIR = ROOT / 'docs/proposed/seat-pose-anatomical'
FIT_DIR = ROOT / 'docs/proposed/seat-pose-fit'
SOLE_CLEAR_CM = .05            # lowest plantar vertex this far above the support (float32 storage keeps it >= 0)
UPPER_BODY = ('Spine1', 'Spine2', 'Neck', 'Head', 'LeftShoulder', 'RightShoulder', 'LeftArm', 'RightArm',
              'LeftForeArm', 'RightForeArm', 'LeftHand', 'RightHand')

# ---------------------------------------------------------------- anatomical ranges (degrees)
# Normal active ranges of motion, American Academy of Orthopaedic Surgeons, "Joint Motion: Method of Measuring and
# Recording" (AAOS 1965; restated in Greene & Heckman, The Clinical Measurement of Joint Motion, AAOS 1994, and in
# Norkin & White, Measurement of Joint Motion, 5th ed., appendix): hip flexion 120 / extension 30 / abduction 45 /
# adduction 30 / internal 45 / external rotation 45; knee flexion 135 (0 = straight, hyperextension not allowed beyond
# 5); ankle dorsiflexion 20 / plantarflexion 50; hindfoot (subtalar) inversion 35 / eversion 15; first MTP flexion 45 /
# extension 70. LUMBAR (Hips->Spine local, the lumbar segment only): flexion 52 / extension 16, the radiographic L1-S1
# sagittal ranges of Pearcy, Portek & Shepherd (Spine 1984;9(3):294-7).
# Pelvis tilt in sitting is not a joint ROM: relative to the standing (bind) pelvis, seated pelvic posterior rotation is
# reported at about 20-40 deg in radiographic studies (e.g. Lord et al., Spine 1997; De Carvalho et al., Spine 2010:
# lumbar flexion and pelvic posterior rotation on sitting). The limit used is 0..45 deg POSTERIOR (no anterior tilt
# beyond standing).
# Every joint angle is the joint's rotation relative to its bind (T-pose standing, feet flat) local, expressed in the
# bind world anatomical axes X lateral (+X = the character's left), Y up, Z forward, intrinsic X-Z-Y (flexion, then
# ab/adduction, then axial rotation), with anatomical signs (see joint_angles).
ANATOMICAL_LIMITS_DEG = {
    'pelvis_posterior_tilt': (0., 45.),
    'hip_flexion': (-30., 120.), 'hip_abduction': (-30., 45.), 'hip_internal_rotation': (-45., 45.),
    'knee_flexion': (-5., 135.),
    'ankle_dorsiflexion': (-50., 20.), 'subtalar_inversion': (-15., 35.),
    'mtp_extension': (-45., 70.), 'lumbar_flexion': (-16., 52.),
}
EDIT_LIMITS = {'pelvis_tilt_change_deg': 35., 'root_vertical_cm': (-14., 6.),
               'root_fore_aft_cm': (-12., 12.), 'ankle_offset_cm': 15., 'hip_swivel_deg': 25.}
LIMIT_SOURCES = ['AAOS (1965) Joint Motion: Method of Measuring and Recording; Greene & Heckman (1994) AAOS',
                 'Norkin & White, Measurement of Joint Motion: A Guide to Goniometry (normal values appendix)',
                 'Lord MJ et al. (1997) Spine 22(21):2571-4; De Carvalho DE et al. (2010) Spine 35(18):E926 '
                 '(seated pelvic posterior rotation / lumbar flexion)']

# ---------------------------------------------------------------- the pose parameters
PARAMS = ('pelvis_tilt_deg', 'root_down_cm', 'root_back_cm', 'left_ankle_forward_cm', 'left_ankle_lateral_cm',
          'right_ankle_forward_cm', 'right_ankle_lateral_cm', 'left_hip_swivel_deg', 'right_hip_swivel_deg')
SIDES = {'left': 'Left', 'right': 'Right'}


def yaw_matrix(a):
    c, s = np.cos(a), np.sin(a)
    R = np.zeros(np.shape(a) + (3, 3))
    R[..., 0, 0], R[..., 0, 2], R[..., 1, 1], R[..., 2, 0], R[..., 2, 2] = c, s, 1., -s, c
    return R


def twist_about_y(R):
    """Angle (rad) of the twist part about +Y of rotations R (..., 3, 3) (swing-twist decomposition)."""
    q = P.quat_from_matrix(np.asarray(R).reshape(-1, 3, 3)).reshape(np.shape(R)[:-2] + (4,))
    return 2 * np.arctan2(q[..., 1], q[..., 3])


class FastMeasure:
    """Trial.seat / Trial.soles with sparse linear-blend skinning (same operators as E.Source._blend)."""

    def __init__(self, trial: T.Trial):
        import scipy.sparse as sp
        self.trial, self.src = trial, trial.src
        self.ops = {}
        for n in T.SEAT_PATCHES + T.SOLE_PATCHES:
            S, Sn = self.src._blend(n)
            self.ops[n] = (sp.csr_matrix(S.T), sp.csr_matrix(Sn.T))
        self.ibm = np.asarray(self.src.ibm)

    def skin(self, name, W):
        F, J = len(W), len(self.src.names)
        mats = (W @ self.ibm[None])[..., :3, :]
        lin = np.ascontiguousarray(mats.transpose(0, 2, 1, 3)).reshape(F * 3, J * 4)
        rot = np.ascontiguousarray(mats[..., :3].transpose(0, 2, 1, 3)).reshape(F * 3, J * 3)
        S, Sn = self.ops[name]
        pos = (S @ lin.T).T.reshape(F, 3, -1).transpose(0, 2, 1)
        nrm = (Sn @ rot.T).T.reshape(F, 3, -1).transpose(0, 2, 1)
        nrm = nrm / np.maximum(np.linalg.norm(nrm, axis=-1, keepdims=True), 1e-12)
        return pos, nrm

    def metrics(self, W, soles=True, seat=True):
        out = {}
        if seat:
            for n in T.SEAT_PATCHES:
                p, nr = self.skin(n, W)
                out[n] = T.patch_metrics(E.to_ue(p), E.to_ue_dir(nr), self.trial.cushion.height, T.SEAT_BAND_CM)
        if soles:
            for n in T.SOLE_PATCHES:
                p, nr = self.skin(n, W)
                pu = E.to_ue(p)
                m = T.patch_metrics(pu, E.to_ue_dir(nr), self.trial.support_height, T.SOLE_BAND_CM)
                m['lowest_any_z'] = pu[..., 2].min(axis=1)
                out[n] = m
        return out


def main_margins(V, m, coverage_cm=6.):
    """Per patch and frame, main validate()'s four conditions as signed margins (cm; >= 0 passes): minGap - band low,
    band high - median, (coverage - MIN_BAND_COVERAGE) * coverage_cm, (over - MIN_PATCH_VERTICES) / 10."""
    out = {}
    for n, x in m.items():
        lo, hi = V.band(n)
        over = np.asarray(x['over'], float)
        cov = np.asarray(x['band'], float) / np.maximum(over, 1.)
        out[n] = {'min_gap': np.nan_to_num(x['lowest'], nan=-99.) - lo, 'median': hi - np.nan_to_num(x['median'], nan=99.),
                  'coverage': (cov - V.MIN_BAND_COVERAGE) * coverage_cm, 'over': (over - V.MIN_PATCH_VERTICES) / 10.}
    return out


def worst_margin(mg):
    return np.min([np.minimum.reduce(list(d.values())) for d in mg.values()], axis=0)     # (F,)


# ---------------------------------------------------------------- anatomy
def unit(R):
    return R / np.linalg.norm(R, axis=-2, keepdims=True)


def euler_xzy(R):
    """Intrinsic X-Z-Y angles (deg) of R = Rx(a) Rz(b) Ry(c)."""
    from scipy.spatial.transform import Rotation
    shp = np.shape(R)[:-2]
    e = Rotation.from_matrix(np.asarray(R).reshape(-1, 3, 3)).as_euler('XZY', degrees=True)
    return e.reshape(shp + (3,))


def relative_anat(W, B, child, parent):
    """Child rotation relative to its parent, relative to the bind, in bind-world anatomical axes:
    D = (Rp_bind Rp^T) Rc Rc_bind^T."""
    Rp, Rc = unit(W[:, parent, :3, :3]), unit(W[:, child, :3, :3])
    Rpb, Rcb = unit(B[parent, :3, :3]), unit(B[child, :3, :3])
    return Rpb @ np.swapaxes(Rp, -1, -2) @ Rc @ Rcb.T


def joint_angles(W, B, names):
    """Anatomical angles (deg, (F,) each) of the pelvis, lumbar, hips, knees, ankles and MTPs."""
    j = names.index
    out = {}
    H = j('Hips')
    Rh = unit(W[:, H, :3, :3]) @ unit(B[H, :3, :3]).T
    psi = twist_about_y(Rh)
    e = euler_xzy(yaw_matrix(-psi) @ Rh)
    out['pelvis_posterior_tilt'] = -e[:, 0]                        # Rx(+a) tips the pelvis top forward (anterior)
    out['pelvis_obliquity'], out['pelvis_heading'] = e[:, 1], np.degrees(psi)
    lum = euler_xzy(relative_anat(W, B, j('Spine'), H))
    out['lumbar_flexion'] = lum[:, 0]                              # Rx(+a) tips the spine forward
    for side, pre in SIDES.items():
        s = 1. if side == 'left' else -1.                         # +X is the left side's lateral
        hip = euler_xzy(relative_anat(W, B, j(f'{pre}UpLeg'), H))
        out[f'{side}_hip_flexion'] = -hip[:, 0]
        out[f'{side}_hip_abduction'] = s * hip[:, 1]
        out[f'{side}_hip_internal_rotation'] = -s * hip[:, 2]
        knee = euler_xzy(relative_anat(W, B, j(f'{pre}Leg'), j(f'{pre}UpLeg')))
        out[f'{side}_knee_flexion'] = knee[:, 0]
        out[f'{side}_knee_varus'], out[f'{side}_knee_axial'] = s * knee[:, 1], -s * knee[:, 2]
        ank = euler_xzy(relative_anat(W, B, j(f'{pre}Foot'), j(f'{pre}Leg')))
        out[f'{side}_ankle_dorsiflexion'] = -ank[:, 0]
        out[f'{side}_subtalar_inversion'] = -s * ank[:, 1]
        out[f'{side}_foot_adduction'] = -s * ank[:, 2]
        mtp = euler_xzy(relative_anat(W, B, j(f'{pre}ToeBase'), j(f'{pre}Foot')))
        out[f'{side}_mtp_extension'] = -mtp[:, 0]
    return out


def limit_excess(angles, capture_angles=None):
    """Per frame, the summed degrees outside ANATOMICAL_LIMITS_DEG (0 = every joint inside), plus the pelvis tilt edit
    bound relative to the capture."""
    F = len(next(iter(angles.values())))
    ex = np.zeros(F)
    for k, v in angles.items():
        base = k.split('_', 1)[1] if k.split('_', 1)[0] in SIDES else k
        if base in ANATOMICAL_LIMITS_DEG:
            lo, hi = ANATOMICAL_LIMITS_DEG[base]
            ex += np.maximum(lo - v, 0.) + np.maximum(v - hi, 0.)
    if capture_angles is not None:
        ex += np.maximum(np.abs(angles['pelvis_posterior_tilt'] - capture_angles['pelvis_posterior_tilt'])
                         - EDIT_LIMITS['pelvis_tilt_change_deg'], 0.)
    return ex


# ---------------------------------------------------------------- the pose model
class PoseModel:
    """Applies PARAMS (F, 9) to captured joint worlds (glTF metres). See the module docstring."""

    def __init__(self, fit: P.SeatFit, measure: FastMeasure):
        self.fit, self.sk, self.measure = fit, fit.sk, measure
        self.names = fit.sk.names
        self.B = np.linalg.inv(np.asarray(fit.trial.src.ibm))       # bind worlds
        self.floor_y = (fit.trial.support_z - E.BODY_CM[2]) / 100.   # the support plane in glTF y (metres)
        j = self.sk.j
        self.legs = {}
        for side, pre in SIDES.items():
            f, t, e = j(f'{pre}Foot'), j(f'{pre}ToeBase'), j(f'{pre}Toe_End')
            self.legs[side] = {'chain': (f'{pre}UpLeg', f'{pre}Leg', f'{pre}Foot'), 'hip': j(f'{pre}UpLeg'),
                               'knee': j(f'{pre}Leg'), 'foot': f, 'toe': t, 'end': e,
                               'toe_local': np.linalg.inv(self.B[f]) @ self.B[t],
                               'end_local': np.linalg.inv(self.B[t]) @ self.B[e]}

    def flat_foot(self, W0, side):
        """(F, 4, 4) rotation part: the bind foot rotation turned about +Y by the captured foot's heading."""
        lg = self.legs[side]
        Rb = self.B[lg['foot'], :3, :3]
        rel = unit(W0[:, lg['foot'], :3, :3]) @ unit(Rb).T
        psi = twist_about_y(rel)
        M = np.tile(np.eye(4), (len(W0), 1, 1))
        M[:, :3, :3] = yaw_matrix(psi) @ Rb
        return M, psi

    def apply(self, W0, prm, sole_iterations=2):
        prm = np.broadcast_to(np.asarray(prm, float), (len(W0), len(PARAMS)))
        th, down, back = prm[:, 0], prm[:, 1], prm[:, 2]
        W = P.pelvis_pitch(self.sk, W0, th, down, self.fit.axis)
        W[:, :, 2, 3] -= back[:, None] / 100.                      # glTF -Z = backward (deeper into the seat)
        lift = {s: np.zeros(len(W0)) for s in SIDES}
        Wp = W
        for it in range(sole_iterations):
            W = Wp.copy()
            for k, side in enumerate(SIDES):
                lg = self.legs[side]
                M, _ = self.flat_foot(W0, side)
                tgt = W0[:, lg['foot'], :3, 3].copy()
                tgt[:, 2] += prm[:, 3 + 2 * k] / 100.
                tgt[:, 0] += (1. if side == 'left' else -1.) * prm[:, 4 + 2 * k] / 100.
                off = self.B[lg['foot'], 1, 3] - self.bind_lowest_plantar[side]
                tgt[:, 1] = self.floor_y + off + SOLE_CLEAR_CM / 100. + lift[side]
                hip, knee = W[:, lg['hip'], :3, 3], W[:, lg['knee'], :3, 3]
                axis = tgt - hip
                pole = hip + np.einsum('fij,fj->fi', P.rodrigues(axis, np.radians(prm[:, 7 + k])), knee - hip)
                W, reach, _, _ = self.sk.two_bone_pose(W, lg['chain'], tgt, pole, end_world_rot=M)
                W[:, lg['toe']] = W[:, lg['foot']] @ lg['toe_local']
                W[:, lg['end']] = W[:, lg['toe']] @ lg['end_local']
            if it + 1 < sole_iterations:
                so = self.measure.metrics(W, seat=False)
                for k, side in enumerate(SIDES):
                    low = so[f'{side}_sole']['lowest_any_z'] - self.fit.trial.support_z
                    lift[side] = lift[side] + (SOLE_CLEAR_CM - low) / 100.
        self.last_reach = reach
        return W

    @property
    def bind_lowest_plantar(self):
        if not hasattr(self, '_blp'):
            self._blp = {}
            for side in SIDES:
                p, _ = self.measure.skin(f'{side}_sole', self.B[None])
                self._blp[side] = float(p[0, :, 1].min())
        return self._blp


# ---------------------------------------------------------------- solver
def edit_cost(prm):
    s = np.array([10., 5., 5., 5., 5., 5., 5., 15., 15.])
    base = np.zeros(len(PARAMS))
    return float(np.sum(((np.asarray(prm) - base) / s) ** 2))


def param_bounds_excess(prm):
    prm = np.asarray(prm, float)
    lo = np.array([-EDIT_LIMITS['pelvis_tilt_change_deg'], EDIT_LIMITS['root_vertical_cm'][0], EDIT_LIMITS['root_fore_aft_cm'][0]]
                  + [-EDIT_LIMITS['ankle_offset_cm']] * 4 + [-EDIT_LIMITS['hip_swivel_deg']] * 2)
    hi = np.array([EDIT_LIMITS['pelvis_tilt_change_deg'], EDIT_LIMITS['root_vertical_cm'][1], EDIT_LIMITS['root_fore_aft_cm'][1]]
                  + [EDIT_LIMITS['ankle_offset_cm']] * 4 + [EDIT_LIMITS['hip_swivel_deg']] * 2)
    # root_down: positive = lower; bounds are on the vertical root change (+ up) = -root_down
    v = prm.copy()
    v[1] = -prm[1]
    return float(np.sum(np.maximum(lo - v, 0.) + np.maximum(v - hi, 0.)))


class Solver:
    def __init__(self, model: PoseModel, V, W0, target_cm=.25, edit_weight=.004):
        self.model, self.V, self.W0 = model, V, W0
        self.target, self.edit_weight = target_cm, edit_weight
        self.cap_angles = joint_angles(W0, model.B, model.names)
        self.evals = 0

    def evaluate(self, prm, frames):
        W = self.model.apply(self.W0[frames], prm)
        m = self.model.measure.metrics(W)
        mg = main_margins(self.V, m)
        worst = worst_margin(mg)
        ang = joint_angles(W, self.model.B, self.model.names)
        cap = {k: v[frames] for k, v in self.cap_angles.items()}
        ex = limit_excess(ang, cap)
        return W, m, mg, worst, ang, ex

    def cost(self, prm, frames):
        self.evals += 1
        _, _, _, worst, _, ex = self.evaluate(prm, frames)
        w = np.minimum(worst, self.target)
        # soft-min over frames (the worst frame dominates) + anatomical / edit-bound penalties + small edit cost
        soft = -np.min(w) - .1 * np.mean(w)
        return soft + 1. * float(ex.max()) + 5. * param_bounds_excess(prm) + self.edit_weight * edit_cost(prm)

    def optimise(self, x0, frames, deadline, maxfev=900):
        from scipy.optimize import minimize
        best = (self.cost(x0, frames), np.asarray(x0, float))
        steps = np.array([4., 2., 2., 3., 2., 3., 2., 8., 8.])
        x = best[1]
        for rnd in range(3):
            if time.time() > deadline:
                break
            simplex = np.vstack([x] + [x + np.eye(len(x))[i] * steps[i] * (.5 ** rnd) for i in range(len(x))])
            r = minimize(self.cost, x, args=(frames,), method='Nelder-Mead',
                         options={'initial_simplex': simplex, 'maxfev': maxfev, 'xatol': 1e-3, 'fatol': 1e-5})
            if r.fun < best[0]:
                best = (float(r.fun), np.asarray(r.x, float))
            x = best[1]
        return best[1], best[0]


# ---------------------------------------------------------------- reporting helpers
def _r(v, d=4):
    v = float(v)
    return None if not math.isfinite(v) else (0.0 if round(v, d) == 0 else round(v, d))


class Clock:
    """Wall-clock cap with checkpoints: every stage writes the partial report (ready: false) before it starts."""

    def __init__(self, seconds, path):
        self.t0, self.cap, self.path = time.time(), float(seconds), Path(path)
        self.stages = []

    def left(self):
        return self.cap - (time.time() - self.t0)

    def checkpoint(self, stage, doc):
        self.stages.append({'stage': stage, 'elapsed_s': round(time.time() - self.t0, 1)})
        doc = dict(doc, ready=False, checkpoint=stage, stages=self.stages, wall_clock_cap_s=self.cap)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(doc, indent=1, default=_json) + '\n')


def rel(p):
    p = Path(p)
    return str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)


def _json(o):
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.floating, np.integer, np.bool_)):
        return o.item()
    raise TypeError(type(o))


def patch_table(V, m, frames=None):
    """Per patch: worst min gap, worst median, worst coverage, fewest over-surface vertices (value, frame)."""
    out = {}
    for n, x in m.items():
        idx = np.arange(len(x['over'])) if frames is None else np.asarray(frames)
        low, med = np.asarray(x['lowest'], float)[idx], np.asarray(x['median'], float)[idx]
        cov = np.asarray(x['band'], float)[idx] / np.maximum(np.asarray(x['over'], float)[idx], 1.)
        over = np.asarray(x['over'])[idx]
        a, b, c, d = np.nanargmin(low), np.nanargmax(med), np.argmin(cov), np.argmin(over)
        out[n] = {'band_cm': list(V.band(n)), 'min_gap_cm': {'value': _r(low[a]), 'frame': int(idx[a])},
                  'max_median_gap_cm': {'value': _r(med[b]), 'frame': int(idx[b])},
                  'min_coverage': {'value': _r(cov[c]), 'frame': int(idx[c])},
                  'min_over_surface_vertices': {'value': int(over[d]), 'frame': int(idx[d])}}
    return out


def joint_edit_table(sk, W0, W, A, threshold_deg=.01):
    """Every joint's LOCAL rotation change vs the capture (max / mean deg, frames over threshold) and the Hips
    translation change (cm); non-root local translations are reported as a check (must be 0)."""
    L0, L1 = P.joint_locals(sk, W0, A), P.joint_locals(sk, W, A)
    out = {}
    for k, n in enumerate(sk.names):
        a = P.rot_angle_deg(L0[:, k, :3, :3], L1[:, k, :3, :3])
        row = {'max_deg': _r(a.max(), 4), 'mean_deg': _r(a.mean(), 4), 'frames_changed': int((a > threshold_deg).sum())}
        dt = np.linalg.norm(L1[:, k, :3, 3] - L0[:, k, :3, 3], axis=1)
        if n == 'Hips':
            d = (W[:, k, :3, 3] - W0[:, k, :3, 3]) * 100
            row['root_translation_cm'] = {'max': _r(np.linalg.norm(d, axis=1).max()),
                                          'mean_xyz_gltf': [_r(v) for v in d.mean(0)]}
        else:
            s = np.linalg.norm(L0[:, k, :3, 0], axis=1)
            row['local_translation_change_cm'] = _r((dt / s).max() * 100 * s.max() / max(s.max(), 1e-12), 7)
        if row['frames_changed'] or n == 'Hips':
            out[n] = row
    unchanged = [n for n in sk.names if n not in out]
    return out, unchanged


def upper_body_deltas(sk, W0, W):
    out = {}
    for n in UPPER_BODY:
        k = sk.j(n)
        out[n] = {'world_rotation_change_deg_max': _r(P.rot_angle_deg(W0[:, k, :3, :3], W[:, k, :3, :3]).max(), 5),
                  'world_translation_cm': [_r(v, 3) for v in ((W[:, k, :3, 3] - W0[:, k, :3, 3]) * 100).mean(0)],
                  'translation_spread_cm': _r(np.ptp(np.linalg.norm((W[:, k, :3, 3] - W0[:, k, :3, 3]) * 100, axis=1)), 4)}
    return out


def bone_length_error_cm(sk, W0, W):
    err = 0.
    for k, p in enumerate(sk.parents):
        if p >= 0:
            a = np.linalg.norm(W0[:, k, :3, 3] - W0[:, p, :3, 3], axis=1)
            b = np.linalg.norm(W[:, k, :3, 3] - W[:, p, :3, 3], axis=1)
            err = max(err, float(np.abs(a - b).max()) * 100)
    return err


def angle_summary(ang, cap=None):
    out = {}
    for k, v in ang.items():
        base = k.split('_', 1)[1] if k.split('_', 1)[0] in SIDES else k
        row = {'range_deg': [_r(v.min(), 2), _r(v.max(), 2)]}
        if base in ANATOMICAL_LIMITS_DEG:
            lo, hi = ANATOMICAL_LIMITS_DEG[base]
            row['limit_deg'] = [lo, hi]
            row['within_limit'] = bool(v.min() >= lo - 1e-6 and v.max() <= hi + 1e-6)
        if cap is not None:
            row['capture_range_deg'] = [_r(cap[k].min(), 2), _r(cap[k].max(), 2)]
            row['max_change_deg'] = _r(np.abs(v - cap[k]).max(), 2)
        out[k] = row
    return out


# ---------------------------------------------------------------- clearances (existing checks)
_SKIN = {}


def body_skin(stride=6):
    if stride not in _SKIN:
        _SKIN[stride] = P.owner_skin(stride)
    return _SKIN[stride]


def chair_clearance(collider, ibm, W_actual, chair_offset, frames, stride=6):
    """Whole-body skin (every stride-th owner vertex) vs the COMPLETE chair (solve_seated_typing_arm_ik.ChairCollider:
    upholstery may be pressed in to the seat band's lower edge, every other part allows no penetration), per frame."""
    skin = body_skin(stride)
    worst, frames_hit, by_mat = math.inf, 0, {}
    for f in frames:
        pts = E.to_ue(P.skin_points(skin, ibm, W_actual[f:f + 1]))[0]
        m, mat = collider.margin(pts, chair_offset)
        k = int(np.argmin(m))
        worst = min(worst, float(m[k]))
        hit = m < 0
        frames_hit += int(hit.any())
        for mm in np.unique(mat[hit]):
            by_mat[str(mm)] = min(by_mat.get(str(mm), 0.), float(m[hit & (mat == mm)].min()))
    return {'min_margin_cm': _r(worst, 3), 'frames_with_penetration': frames_hit, 'frames_checked': len(frames),
            'deepest_by_chair_part_cm': {k: _r(v, 3) for k, v in by_mat.items()}, 'clear': frames_hit == 0,
            'skin_sampling': f'every {stride}th skinned owner vertex',
            'rule': 'ChairCollider (tools/solve_seated_typing_arm_ik.py): margin = signed distance - allowed depth; '
                    'chair_fabric allows -2.5 cm (seat band), every other part 0'}


def desk_clear(ibm, W, body_offset, names, desk_cache={}):
    """fit_seat_pelvis_pitch.desk_clearance (the seat fit's own desk check, native desk placement)."""
    if 'pts' not in desk_cache:
        meta = json.loads(P.DESK_ASSET_JSON.read_text())
        desk_cache['pts'] = P.desk_world_samples(P.NATIVE_DESK['centre_xy_cm'], P.NATIVE_DESK['top_cm'])
        desk_cache['th'] = float(meta['desktop_thickness_m']) * 100
    return P.desk_clearance(body_skin(), ibm, W, body_offset, desk_cache['pts'], P.NATIVE_DESK['top_cm'],
                            desk_cache['th'], names)


# ---------------------------------------------------------------- pipeline
CLIPS = ROOT / 'web/room/mh_mx'
IDLE_CLIP = 'room_seated_idle.glb'
TRANSITIONS = {'SitDown': ('room_mx_stand_to_sit.glb', 'end'), 'GetUp': ('room_mx_sit_to_stand.glb', 'start')}
CHAIR_LIFT_CM = 2.5001          # caster bottoms (z 0.0) onto the actual floor top (2.5001 cm): root's chair-model note
# Warm start found by this solver on the 13-frame probe of SeatedIdle (pelvis axis of the idle capture); the run
# re-solves from it on the gated frames and verifies every frame.
WARM_START = (30.35, 12.44, -10.49, 4.17, 2.67, 3.99, .89, -.51, -4.65)
SEAM_A_STEP, SEAM_MIN_FRAMES = 3, 3


def fast_trial(trial, measure):
    """Point the fitter's Trial.seat / Trial.soles at the sparse (identical) skinning, for the seam search speed."""
    def seat(W, frames=None):
        return measure.metrics(W if frames is None else W[frames], soles=False)

    def soles(W):
        out = {}
        for n in T.SOLE_PATCHES:
            p, nr = measure.skin(n, W)
            pu = E.to_ue(p)
            m = T.patch_metrics(pu, E.to_ue_dir(nr), trial.support_height, T.SOLE_BAND_CM)
            m['centroid_xy'], m['lowest_any_z'] = pu[..., :2].mean(axis=1), pu[..., 2].min(axis=1)
            out[n] = m
        return out
    trial.seat, trial.soles = seat, soles
    return trial


class Context:
    def __init__(self, V, base, keys, chair_lift_cm=0.):
        self.V, self.base, self.keys = V, base, keys
        tri, self.cushion_meta = P.load_cushion()
        self.tri = np.array(tri, float)
        self.tri[..., 2] += chair_lift_cm
        self.lift = chair_lift_cm
        old = json.loads((FIT_DIR / 'SUB01_SeatedIdle.report.json').read_text())
        self.body_offset = tuple(old['actual_chair']['body_offset_from_audited_transform_cm'])
        self.shift = (-self.body_offset[0], -self.body_offset[1])          # P.body_offset_for inverse
        g30 = G.Gltf(CLIPS / 'room_mx_typing.glb')
        src30, _ = P.clip_source(base, CLIPS / 'room_mx_typing.glb', g30.animation().key_times())
        self.axis = P.hips_lateral_local(T.Skeleton(src30), src30.joint_world)  # the seat fit's pelvis axis
        self.seated_h = float(P.hips_track(g30, [0.])[0, 1])
        summ = json.loads((FIT_DIR / 'seat-pose-fit.report.json').read_text())
        self.idle_frames = tuple(summ['stable_seated_interval']['room_seated_idle']['best_loop_frames'])

    def fit(self, src):
        f = P.SeatFit(src, self.tri, self.keys, self.shift, axis_local=self.axis)
        m = FastMeasure(f.trial)
        fast_trial(f.trial, m)
        return f, m


def solver_cost_worst(mg):
    """The optimiser's worst margin: every main condition except the sole minimum gap, which the flat-foot model sets
    to SOLE_CLEAR_CM by construction (it is still gated in every verification)."""
    rows = []
    for n, d in mg.items():
        keys = [k for k in d if not (n in T.SOLE_PATCHES and k == 'min_gap')]
        rows.append(np.minimum.reduce([d[k] for k in keys]))
    return np.min(rows, axis=0)


class IdleSolver(Solver):
    def cost(self, prm, frames):
        self.evals += 1
        _, _, mg, _, _, ex = self.evaluate(prm, frames)
        w = np.minimum(solver_cost_worst(mg), self.target)
        return -np.min(w) - .1 * np.mean(w) + 20. * float(ex.max()) + 5. * param_bounds_excess(prm) + \
            self.edit_weight * edit_cost(prm)


def solve_idle(ctx, clock, report, cand, x0=WARM_START, max_rounds=4):
    g = G.Gltf(CLIPS / IDLE_CLIP)
    la, lb = ctx.idle_frames
    times = g.animation().key_times()[la:lb + 1]
    src, _ = P.clip_source(ctx.base, CLIPS / IDLE_CLIP, times)
    fit, meas = ctx.fit(src)
    model = PoseModel(fit, meas)
    W0 = src.joint_world
    F = len(W0)
    sol = IdleSolver(model, ctx.V, W0)
    frames = np.unique(np.r_[np.arange(0, F, 10), F - 1])
    x = np.asarray(x0, float)
    history = []
    for rnd in range(max_rounds):
        budget = min(clock.left() * .5, 420.)
        if budget < 30:
            break
        x, c = sol.optimise(x, frames, time.time() + budget, maxfev=500)
        W, m, mg, worst, ang, ex = sol.evaluate(x, np.arange(F))
        bad = np.nonzero(worst < 0)[0]
        history.append({'round': rnd, 'probe_frames': len(frames), 'params': [_r(v, 4) for v in x],
                        'all_frames_worst_margin_cm': _r(worst.min()), 'failing_frames': int(len(bad)),
                        'anatomical_excess_deg_max': _r(ex.max(), 4),
                        'per_patch': patch_table(ctx.V, m)})
        cand['idle_solve_history'] = history
        clock.checkpoint(f'SeatedIdle round {rnd}', report)
        if not len(bad) and ex.max() == 0:
            break
        frames = np.unique(np.r_[frames, bad[np.argsort(worst[bad])][:6]])
    return {'g': g, 'times': list(map(float, times)), 'src': src, 'fit': fit, 'meas': meas, 'model': model, 'W0': W0,
            'x': x, 'W': W, 'metrics': m, 'worst': worst, 'angles': ang, 'excess': ex, 'solver': sol}


def write_and_report(ctx, out_dir, role, asset, g, sk, W, W0, times, labels, extra, support_mask=None, end=None,
                     loop_readback=None):
    """Write the GLB (P.write_clip: every joint's local rotation + the Hips translation; other captured tracks kept),
    read it back, store the per-frame patch metrics in the shape tools/recheck_seat_fit_main_rule.py reads."""
    path = Path(out_dir) / f'{asset}.glb'
    sha, _ = P.write_clip(g, sk, W, times, path, asset, labels, {'sub01_report': f'{asset}.report.json'})
    g_out = G.Gltf(path)
    t_rel = [float(t - times[0]) for t in times]
    W_out, _ = E.joint_worlds(g_out, sk.names, t_rel)
    d = dict(ctx.base.d)
    d['joint_world'], d['times'] = W_out, np.array(t_rel)
    fit_out, meas_out = ctx.fit(E.Source(d))
    m = meas_out.metrics(W_out)
    F = len(W_out)
    mask = np.ones(F, bool) if support_mask is None else np.asarray(support_mask, bool)
    rep = {'schema': SCHEMA, 'role': role, 'asset': f'/Game/Sub01Hands/Seating/{asset}', 'labels': labels,
           'glb': rel(path), 'sha256': sha, 'bytes': path.stat().st_size, 'key_count': F,
           'duration_s': _r(times[-1] - times[0]),
           'readback_max_joint_error_cm': _r(np.abs(W_out[:, :, :3, 3] - W[:, :, :3, 3]).max() * 100, 6),
           'actual_chair': {'body_offset_from_audited_transform_cm': list(ctx.body_offset),
                            'chair_lift_cm': ctx.lift,
                            'per_frame': {'support_mask': [bool(v) for v in mask],
                                          'patches': {n: {'lowest_cm': [_r(v, 6) for v in m[n]['lowest']],
                                                          'median_cm': [_r(v, 6) for v in m[n]['median']],
                                                          'band_vertices': [int(v) for v in m[n]['band']],
                                                          'over_vertices': [int(v) for v in m[n]['over']]}
                                                      for n in m}}}}
    rep.update(extra)
    rep['bone_length_max_error_cm'] = _r(bone_length_error_cm(sk, W0, W_out), 7)
    A = P.armature_world(g, g.by_name['mixamorig:Hips'])
    rep['joint_edits_vs_capture'], rep['joints_unchanged'] = joint_edit_table(sk, W0, W_out, A)
    rep['upper_body_world_vs_capture'] = upper_body_deltas(sk, W0, W_out)
    B = np.linalg.inv(np.asarray(ctx.base.ibm))
    ang, cap = joint_angles(W_out, B, sk.names), joint_angles(W0, B, sk.names)
    rep['anatomical_angles'] = angle_summary(ang, cap)
    ex_edit, ex_abs, ex_cap = limit_excess(ang, cap), limit_excess(ang), limit_excess(cap)
    rep['anatomical_limits_ok'] = bool(ex_edit[mask].max() == 0)
    rep['anatomical_limits_ok_all_frames'] = bool(ex_edit.max() == 0)
    rep['anatomical_limit_frames'] = {
        'gated_frames_outside': [int(i) for i in np.nonzero((ex_edit > 0) & mask)[0]],
        'frames_outside_absolute_ranges': [int(i) for i in np.nonzero(ex_abs > 0)[0]],
        'frames_outside_pelvis_edit_bound_only': [int(i) for i in np.nonzero((ex_edit > 0) & (ex_abs == 0))[0]],
        'capture_itself_outside_absolute_ranges': [int(i) for i in np.nonzero(ex_cap > 0)[0]],
        'max_excess_deg': _r(ex_edit.max(), 3),
        'note': 'the ranges are SEATED / normal-ROM ranges; ungated stand/sit motion frames keep the capture, which '
                'already leaves them (e.g. anterior pelvic tilt while rising)'}
    fps = (F - 1) / (times[-1] - times[0])
    if end is None:
        rep['loop_closure'] = P.seam_measure(P.hips_frame_shapes(sk, W_out), P.ue_point(W_out[:, sk.j('Hips'), :3, 3]),
                                             0, F - 1, fps)
    else:
        rep['seam_to_SeatedIdle'] = P.seam_report(sk, W_out, loop_readback, end, fps)
    Wa = P.place_body(W_out, ctx.body_offset)
    rep['clearance'] = {'chair_complete': chair_clearance(ctx.collider, np.asarray(ctx.base.ibm), Wa,
                                                          (0., 0., ctx.lift), range(0, F, 5)),
                        'desk': desk_clear(np.asarray(ctx.base.ibm), W_out, ctx.body_offset, sk.names)}
    (Path(out_dir) / f'{asset}.report.json').write_text(json.dumps(rep, indent=1, default=_json) + '\n')
    rep['_W_out'] = W_out
    return rep


def main_rule_verdict(ctx, out_dir, name, R):
    """tools/recheck_seat_fit_main_rule.py's own measure_clip + recheck on the written GLB (main validator bytes)."""
    R.FIT_DIR = Path(out_dir)
    rep, metrics, mask, repro, F = R.measure_clip(name, ctx.base, ctx.tri, ctx.keys, P, E, G)
    res = R.recheck(ctx.V, name, metrics, mask, F)
    res['measurement_reproduction_max_abs_lowest_gap_diff_cm'] = {n: round(v, 6) for n, v in repro.items()}
    res['glb_sha256'] = rep['sha256']
    res['per_patch_on_gated_frames'] = patch_table(ctx.V, metrics, np.nonzero(mask)[0])
    return res


def seam_window_search(ctx, tr, W_loop, end, deadline):
    """The existing full-pose seam blend (fit_seat_pelvis_pitch.seam_blend_eval: quintic window, loop-target legs,
    no-penetration lifts) restricted to windows in which every settled (gated) frame is already exactly the loop, so
    no gated frame keeps the capture's tiptoe pose. Choice: (1) no failing frame - main's rule on the support frames,
    no penetration elsewhere; (2) pelvis peak acceleration ratio <= 1 and no added sole sliding; (3) most captured
    frames kept; (4) smallest ratio (the order of seam_blend_search)."""
    fit, W, F, fps, g = tr['fit'], tr['W'], len(tr['W']), tr['fps'], tr['g']
    A = P.armature_world(g, g.by_name['mixamorig:Hips'])
    Tg = P.seam_target(W_loop, end, F)
    gated = np.nonzero(tr['settled'])[0]
    kin0 = P.pelvis_kinematics(fit.sk, W, fps)
    cap_acc, cap_ang = float(kin0['acc_cm_s2'].max()), float(kin0['ang_acc_deg_s2'].max())
    meas = FastMeasure(fit.trial)
    cache, rows, best = {}, [], None
    if end == 'end':
        bs = [b for b in range(min(int(gated.min()), F - 2), max(int(gated.min()) - 7, SEAM_MIN_FRAMES), -2)]
        cands = [(a, b) for b in bs for a in range(max(0, b - 45), b - SEAM_MIN_FRAMES + 1, SEAM_A_STEP)]
    else:
        As = [a for a in range(max(int(gated.max()), 1), min(int(gated.max()) + 7, F - SEAM_MIN_FRAMES), 2)]
        cands = [(a, b) for a in As for b in range(a + SEAM_MIN_FRAMES, min(F, a + 46), SEAM_A_STEP)]
    for a, b in cands:
        if time.time() > deadline:
            break
        ev = P.seam_blend_eval(fit, A, W, Tg, end, a, b, tr['settled'], fps, cache)
        sup = ev['support']
        c = ev['contact']
        pen = np.zeros(F, bool)
        for n in T.SEAT_PATCHES + T.SOLE_PATCHES:
            lo = (T.SEAT_BAND_CM if n in T.SEAT_PATCHES else T.SOLE_BAND_CM)[0]
            pen |= (c[n]['over'] > 0) & (np.nan_to_num(c[n]['lowest'], nan=np.inf) < lo)
        fail = pen & ~sup
        if sup.any():
            mg = main_margins(ctx.V, meas.metrics(ev['W'][sup]))
            fail[np.nonzero(sup)[0][worst_margin(mg) < 0]] = True
        acc, ang = float(ev['kin']['acc_cm_s2'].max()), float(ev['kin']['ang_acc_deg_s2'].max())
        ratio = max(acc / cap_acc, ang / cap_ang)
        if 'clip_touch' not in cache:
            cache['clip_touch'] = P.touching_sole_speed(cache['clip'], fps)
        touch = P.touching_sole_speed(c, fps)
        feet_ok = all(touch[n] <= cache['clip_touch'][n] + 1e-6 for n in touch)
        kept = int(((ev['w'] <= 0) & (ev['lift_cm'] <= 0)).sum())
        row = {'a': a, 'b': b, 'failing_frames': int(fail.sum()), 'peak_ratio_to_capture': _r(ratio, 4),
               'feet_within_capture': bool(feet_ok), 'captured_frames_kept': kept,
               'lifted_frames': int((ev['lift_cm'] > 0).sum()), 'max_lift_cm': _r(ev['lift_cm'].max(), 4)}
        rows.append(row)
        key = (row['failing_frames'], ratio > 1 + 1e-9 or not feet_ok, -kept, ratio)
        if best is None or key < best[0]:
            best = (key, row, ev)
    _, row, ev = best
    info = {'mode': 'full-pose seam blend into the anatomical SeatedIdle (%s)' % ('loop tail' if end == 'end' else 'loop head'),
            'end': end, 'window_frames': [row['a'], row['b']], 'chosen': row, 'candidates': len(rows),
            'gated_frames': [int(i) for i in gated], 'search_rule': seam_window_search.__doc__.split('Choice: ')[1],
            'rows': rows, 'weight': 'quintic smootherstep',
            'no_penetration_lift_max_cm': _r(ev['lift_cm'].max(), 4),
            'foot_lift_max_cm': {k: _r(v.max(), 4) for k, v in ev['foot_lift_cm'].items()}}
    return ev, info


def run(args):
    import recheck_seat_fit_main_rule as R
    import solve_seated_typing_arm_ik as S
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    clock = Clock(args.max_seconds, out_dir / 'seat-pose-anatomical.report.json')
    V = R.load_main_validator(R.main_validator_bytes(args.ref))
    base = E.Source.load(args.source)
    keys = T.keycaps_from_glb()
    measured = S.load_chair()
    complete = S.load_complete_chair(measured)
    collider = S.ChairCollider(complete)
    report = {'schema': SCHEMA, 'label': 'proposal', 'verified': False, 'requires_server_reaudit': True,
              'requires_native_collision_audit': True, 'changes_importer_pins_or_verdicts': False,
              'main_validator': {'ref': args.ref, 'sha256': V.SOURCE_SHA256, 'seat_band_cm': list(V.SEAT_BAND_CM),
                                 'sole_band_cm': list(V.SOLE_BAND_CM), 'min_patch_vertices': V.MIN_PATCH_VERTICES,
                                 'min_band_coverage': V.MIN_BAND_COVERAGE},
              'objective': ("main validate()'s four per-patch conditions as signed margins (min gap - band low, band "
                            'high - median, coverage - 0.5, over - 12), worst over patches and frames; anatomical '
                            'limits and edit bounds as penalties; no local-support (MIN_SUPPORT_VERTICES) term'),
              'anatomical_limits_deg': ANATOMICAL_LIMITS_DEG, 'edit_limits': EDIT_LIMITS, 'limit_sources': LIMIT_SOURCES,
              'params': PARAMS, 'source_captures_untouched': True, 'arms': 'not edited (separate later step)',
              'chair': {'file': measured['file'], 'sha256': measured['sha256'],
                        'measured_translation_cm': measured['translation_cm'],
                        'caster_bottom_cm': _r(complete['lowest_cm'], 4), 'floor_top_cm': P.FLOOR_CM},
              'candidates': {}}
    variants = [] if args.only_lift else [('measured_chair', 0., out_dir)]
    if args.chair_lift or args.only_lift:
        variants.append(('chair_lift_proposal', CHAIR_LIFT_CM, out_dir / 'chair-lift-proposal'))
    for vname, lift, vdir in variants:
        vdir.mkdir(parents=True, exist_ok=True)
        ctx = Context(V, base, keys, lift)
        ctx.collider = collider
        cand = report['candidates'].setdefault(vname, {'chair_lift_cm': lift, 'out_dir': rel(vdir)})
        if lift:
            t = measured['translation_cm']
            cand['proposal'] = {'derived': True, 'needs_native_chair_review': True,
                                'rule': 'rigid lift of the WHOLE chair (model unchanged, no rotation/scale change) so the '
                                        'caster bottoms sit on the actual floor top; the floor plane is not redefined',
                                'measured_translation_cm': t,
                                'lifted_translation_cm': [t[0], t[1], _r(t[2] + lift, 6)],
                                'caster_bottom_to_floor_gap_cm': {'measured': _r(complete['lowest_cm'] - P.FLOOR_CM, 4),
                                                                  'lifted': _r(complete['lowest_cm'] + lift - P.FLOOR_CM, 4)},
                                'cushion_height_change_cm': lift,
                                'cushion_top_cm': {'measured': _r(ctx.tri[..., 2].max() - lift, 4),
                                                   'lifted': _r(ctx.tri[..., 2].max(), 4)}}
        clock.checkpoint(f'{vname}: start', report)
        idle = solve_idle(ctx, clock, report, cand, x0=args.warm_start or WARM_START)
        sk = idle['fit'].sk
        x = idle['x']
        labels = {'label': 'proposal', 'verified': False, 'requires_server_reaudit': True,
                  'requires_native_collision_audit': True, 'role': 'SeatedIdle',
                  'source_clip': f'web/room/mh_mx/{IDLE_CLIP}', 'source_frames': list(ctx.idle_frames),
                  'derived_edits': ['pelvis_tilt_about_lateral_axis_pivot_spine_spine_counter_rotated',
                                    'root_vertical_and_fore_aft_translation', 'flat_foot_heel_down_bind_plantar_heading_kept',
                                    'toes_to_bind_local', 'non_stretch_two_bone_leg_ik_ankle_offset_hip_swivel'],
                  'params': dict(zip(PARAMS, [_r(v, 4) for v in x])), 'chair_lift_cm': lift}
        rep = write_and_report(ctx, vdir, 'SeatedIdle', 'SUB01_SeatedIdle', idle['g'], sk, idle['W'], idle['W0'],
                               idle['times'], labels, {'params': labels['params']})
        cand['SeatedIdle'] = {k: v for k, v in rep.items() if not k.startswith('_') and k != 'actual_chair'}
        cand['SeatedIdle']['main_rule'] = main_rule_verdict(ctx, vdir, 'SeatedIdle', R)
        clock.checkpoint(f'{vname}: SeatedIdle written', report)
        loop_W = rep['_W_out']
        for name, (fname, end) in TRANSITIONS.items():
            if clock.left() < 120:
                cand[name] = {'skipped': 'wall-clock cap'}
                continue
            tr = P.fit_transition(name, fname, False, base, ctx.tri, keys, ctx.shift, ctx.axis, ctx.seated_h, {},
                                  skip_ease=(end,))
            fast_trial(tr['fit'].trial, FastMeasure(tr['fit'].trial))
            ev, info = seam_window_search(ctx, tr, loop_W, end, time.time() + min(clock.left() * .4, 600))
            lab = dict(labels, role=f'{name}_seated', source_clip=f'web/room/mh_mx/{fname}',
                       derived_edits=['seat_pose_fit_transition_correction (fit_seat_pelvis_pitch.fit_transition)',
                                      'full_pose_seam_blend_into_anatomical_SeatedIdle'])
            lab.pop('source_frames', None)
            r2 = write_and_report(ctx, vdir, f'{name}_seated', f'SUB01_{name}_seated', tr['g'], tr['fit'].sk, ev['W'],
                                  tr['fit'].W0, tr['times'], lab, {'seam_blend': info}, support_mask=ev['support'],
                                  end=end, loop_readback=loop_W)
            cand[name] = {k: v for k, v in r2.items() if not k.startswith('_') and k != 'actual_chair'}
            cand[name]['main_rule'] = main_rule_verdict(ctx, vdir, f'{name}_seated', R)
            clock.checkpoint(f'{vname}: {name} written', report)
        cand['summary'] = {k: {'pass_main_rule': v['main_rule']['pass_main_rule'],
                               'failing_frames': v['main_rule']['failing_frame_count'],
                               'gated_frames': v['main_rule']['gated_frames'], 'sha256': v['sha256']}
                           for k, v in cand.items() if isinstance(v, dict) and 'main_rule' in v}
    report['summary'] = {k: v.get('summary') for k, v in report['candidates'].items()}
    report['ready'] = True
    report['elapsed_s'] = round(time.time() - clock.t0, 1)
    clock.path.write_text(json.dumps(report, indent=1, default=_json) + '\n')
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--source', default=str(ROOT / 'private-audit/seat-fit-source.npz'))
    ap.add_argument('--ref', default='origin/main')
    ap.add_argument('--out-dir', default=str(OUT_DIR))
    ap.add_argument('--max-seconds', type=float, default=3000.)
    ap.add_argument('--chair-lift', action='store_true', help='also solve on the +2.5001 cm chair-lift PROPOSAL')
    ap.add_argument('--only-lift', action='store_true', help='solve only the chair-lift proposal')
    ap.add_argument('--warm-start', type=float, nargs=len(PARAMS), default=None)
    args = ap.parse_args(argv)
    rep = run(args)
    print(json.dumps(rep['summary'], indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
