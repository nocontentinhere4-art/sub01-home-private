"""Bed transitions, corrected: LieDown -> SleepLoop -> GetUp on the owner skeleton (private; CPU only).

    python3 tools/bed_transition_corrections.py OUT_DIR [--work DIR] [--owner web/room/char_mixamo.glb]

Provenance label (not a refusal, not "mocap"): the lie-down and get-up are `derived_library_asset`:
web/room/mh_v5/room_bed_lie.glb / room_bed_wake.glb, which are preview/mh-motion clips retargeted through
room_build/kimodo/mh_retarget.mjs; their capture method is undocumented. The verbatim quotes and the sha256
of every source stay in each report (bed_transition_pipeline.check_documented). Every output GLB carries the
label in asset.extras.sub01_provenance, so the inventory can show it (inventory_native_life_clips --derived).

Corrections, each one labelled in the GLB and measured raw vs corrected in the report:

1. `seated_slide_removed` (GetUp). Between 4.80 and 6.27 s the source carries the hips ~79 cm at sitting
   height (184 cm/s) with both feet off the floor. It is an artefact: with it, the get-up's lying spot is
   ~1 m from its bed-edge seat, while the lie-down's own lying spot is ~25 cm from its seat. The hips'
   horizontal position is HELD through that window (the captured displacement inside it is subtracted,
   smoothed by a Gaussian of SLIDE_SMOOTH_FRAMES so no step is introduced); the travel is not
   redistributed, it is removed, because no step of the feet carries it (the native walk does the rest).
2. `walk_in_trimmed` + `ease_in_retime` (LieDown). The adapter arrives at the approach point by
   CharacterMovement and turns in place, i.e. from a stand-still; the source starts mid-walk at 66 cm/s. The
   start is trimmed to the last standing frame with both feet planted before he sits (min hips speed), and
   the first EASE_IN_S of playback is time-warped (u = t^2 / 2R) so the clip starts at zero velocity with
   captured poses only. The residual against the native Idle and every phase of the native Walk is reported.
3. `leg_ik_floor_contact` (GetUp end, LieDown start). tools/leg_ik_life_clip.correct (imported, unchanged:
   analytic two-bone leg IK, captured knee plane, captured world foot orientation, bounded vertical root
   support) on the frames where both feet are planted, faded in/out over IK_FADE_FRAMES. Contact is then
   measured with root's plantar rule (verify_life_idle_candidate.sole_selection): lowest plantar vertex
   0..+1 cm, >= 12 plantar vertices in that band, no penetration.
4. `sleep_settle_blend` + `sleep_loop_seam_blend`. The chosen sleep loop is the get-up source's own captured
   lying-still head (a derived_library_asset lying segment), loop-closed with
   leg_ik_life_clip.seam_blend (imported). The lie-down settles into it over SETTLE_S with BOTH ends held
   at captured poses (the lie-down frozen at its truncation frame, the loop advancing), smootherstep weight.
   The get-up starts exactly where the loop starts, so its side needs no blend. Measured alternatives
   (Sova sleep_back / sleep_side, Mixamo Laying_Sleeping) are in the report with their transition speeds.

Nothing here is run in Unreal or Blender, nothing is deployed, and nothing claims the native bed or a
runtime receipt. The bed stays unmeasured (tools/unreal_bed_surface_audit.py is root's server step).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import bed_transition_pipeline as B  # noqa: E402  (our b7b099b pipeline: retarget, Motion, root path)
import leg_ik_life_clip as LI  # noqa: E402  (read-only import: two-bone leg IK, seam blend, soles)
import life_gltf as G  # noqa: E402
import verify_life_idle_candidate as V  # noqa: E402  (read-only import: plantar rule)

SCHEMA = 'sub01.bed-transition-corrected-clip.v1'
FPS = 30.0
PROVENANCE_LABEL = 'derived_library_asset'
PROVENANCE_TEXT = ('derived library asset: preview/mh-motion clips retargeted via room_build/kimodo/mh_retarget.mjs '
                   '(web/room/mh_v5), then onto the owner skeleton by tools/retarget_first_person.mjs; capture method '
                   'undocumented; corrected by tools/bed_transition_corrections.py (controlled adaptation, labelled)')
# Stated settings (not tuned to a result).
SLIDE_SEATED_MAX_TILT_DEG = 45.0       # the slide happens at sitting height (torso near upright, not standing)
SLIDE_MIN_PEAK_CM_S = 50.0             # B.BED_SLIDE_SPEED_CM_S: hips speed while not standing that is implausible
SLIDE_EDGE_CM_S = B.SETTLED_SPEED_CM_S  # the window extends to the nearest settled frame on each side
SLIDE_SMOOTH_FRAMES = 4.0              # Gaussian sigma of the subtracted displacement (frames)
EASE_IN_S = 0.5                        # zero-velocity start
PLANTED_FOOT_CM_S = 20.0               # foot joint horizontal speed of a planted foot
PLANTED_FOOT_RISE_CM = 3.0             # foot joint no higher than its standing minimum + this
IK_FADE_FRAMES = 8
SETTLE_S = 2.5                         # owner window 1.5-2.5 s
SETTLE_OPTIONS_S = (1.5, 2.0, 2.5)
TARGET_JOINT_SPEED_CM_S = 40.0
LOOP_STILL_CM_S = 10.0                 # captured lying frames moving less than this (max joint, hips-relative)
LOOP_SEAM_BLEND_S = LI.DEFAULT_BLEND_S  # 0.4 s, the idle tool's own loop crossfade
LOOP_MAX_SEAM_CM = 1.0               # inventory_native_life_clips.LOOP_MAX_JOINT_CM: captured gap the seam blend closes
ALTERNATIVE_LOOPS = {
    'sova_sleep_back': ROOT / 'web/room/desk_states/bed/sleep_back.glb',
    'sova_sleep_side': ROOT / 'web/room/desk_states/bed/sleep_side.glb',
    'mixamo_laying_sleeping_v5': ROOT / 'web/room/mh_v5/room_laying_sleeping.glb',
}


# ------------------------------------------------------------------ small helpers
def smootherstep(x):
    x = np.clip(np.asarray(x, float), 0.0, 1.0)
    return x ** 3 * (x * (6 * x - 15) + 10)


def joint_speed(m: B.Motion):
    """Per frame step: max hips-relative joint speed (cm/s) and max world joint speed (cm/s)."""
    f = B.hips_relative(m)
    rel = np.linalg.norm(np.diff(f, axis=0), axis=2).max(axis=1) * m.fps
    pos, _ = m.world()
    world = np.linalg.norm(np.diff(pos, axis=0), axis=2).max(axis=1) * m.fps
    return rel, world


def path_stats(m: B.Motion):
    p = B.root_path(m)
    return {k: p[k] for k in ('path_length_cm', 'net_distance_cm', 'net_displacement_cm', 'max_speed_cm_s',
                              'max_speed_at_s', 'max_acceleration_cm_s2', 'max_acceleration_at_s', 'max_frame_step_cm',
                              'discontinuity')}


def sample(m: B.Motion, s):
    """Captured frames at fractional frame positions s (slerp / lerp between neighbours)."""
    s = np.clip(np.asarray(s, float), 0, len(m) - 1)
    a = np.floor(s).astype(int)
    b = np.minimum(a + 1, len(m) - 1)
    w = s - a
    return B.slerp(m.q[a], m.q[b], w[:, None]), m.t[a] * (1 - w[:, None]) + m.t[b] * w[:, None]


def foot_kinematics(m: B.Motion):
    pos, _ = m.world()
    out = {}
    for side in ('Left', 'Right'):
        p = pos[:, m.sk.index[side + 'Foot']]
        out[side] = {'height': p[:, 1], 'speed': np.linalg.norm(B.velocities(p[:, [0, 2]], m.fps), axis=1)}
    return out


# ------------------------------------------------------------------ 1. get-up seated slide
def detect_seated_slide(m: B.Motion):
    """The hips' run at sitting height above SLIDE_MIN_PEAK_CM_S, out to the nearest settled frame each side."""
    speed = B.hips_speed(m)
    tilt = B.torso_tilt_deg(m)
    standing = B.standing_mask(m)
    seated = (~standing) & (tilt <= SLIDE_SEATED_MAX_TILT_DEG)
    cand = np.where(seated & (speed > SLIDE_MIN_PEAK_CM_S))[0]
    if not len(cand):
        return None
    peak = int(cand[np.argmax(speed[cand])])
    a = peak
    while a > 0 and speed[a] > SLIDE_EDGE_CM_S:
        a -= 1
    b = peak
    while b < len(m) - 1 and speed[b] > SLIDE_EDGE_CM_S:
        b += 1
    return {'start_frame': a, 'end_frame': b, 'peak_frame': peak, 'peak_speed_cm_s': round(float(speed[peak]), 3),
            'start_s': round(a / m.fps, 4), 'end_s': round(b / m.fps, 4),
            'rule': f'peak = the fastest hips frame that is not standing with torso tilt <= {SLIDE_SEATED_MAX_TILT_DEG} deg '
                    f'and speed > {SLIDE_MIN_PEAK_CM_S} cm/s; window = out to the nearest frame <= {SLIDE_EDGE_CM_S} cm/s'}


def gaussian_smooth(x, sigma):
    r = int(math.ceil(3 * sigma))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    pad = np.concatenate([np.repeat(x[:1], r, 0), x, np.repeat(x[-1:], r, 0)])
    return np.stack([np.convolve(pad[:, c], k, mode='valid') for c in range(x.shape[1])], axis=1)


def remove_seated_slide(m: B.Motion, window):
    """Hold the hips' horizontal position through the window; everything after keeps its captured path, offset."""
    a, b = window['start_frame'], window['end_frame']
    xz = m.t[:, [0, 2]]
    disp = xz[np.clip(np.arange(len(m)), a, b)] - xz[a]
    removed = gaussian_smooth(disp, SLIDE_SMOOTH_FRAMES)
    t = m.t.copy()
    t[:, [0, 2]] = xz - removed
    return B.Motion(m.sk, m.q.copy(), t, m.fps, m.name), removed


def seat_to_lying_offset(m: B.Motion, lying_frame, seated_frame):
    pos, _ = m.world()
    h = m.sk.index['Hips']
    return round(float(np.linalg.norm(pos[lying_frame, h, [0, 2]] - pos[seated_frame, h, [0, 2]])), 3)


def first_seated_frame(m: B.Motion, after=0, before=None):
    """First frame after `after` that is seated: torso <= 30 deg from vertical and leg extension < 0.9 x rest."""
    tilt, ext = B.torso_tilt_deg(m), B.leg_extension(m)
    for k in range(after, before if before is not None else len(m)):
        if tilt[k] <= B.STANDING_MAX_TILT_DEG and ext[k] < 0.9 * m.sk.rest_extension:
            return k
    return None


# ------------------------------------------------------------------ 2. lie-down start
def choose_standing_start(m: B.Motion):
    """The last standing frame before he leaves standing, with both feet planted and the lowest hips speed."""
    tilt, ext = B.torso_tilt_deg(m), B.leg_extension(m)
    upright = tilt <= B.STANDING_MAX_TILT_DEG
    leave = int(np.argmin(upright)) if not upright.all() else len(m)       # he starts to sit here
    standing = upright & (ext >= V.STANDING_MIN_LEG_EXTENSION * m.sk.rest_extension)
    feet = foot_kinematics(m)
    low = {s: feet[s]['height'][:leave].min() for s in feet}
    speed = B.hips_speed(m)
    planted = [k for k in range(leave) if standing[k] and all(
        feet[s]['speed'][k] <= PLANTED_FOOT_CM_S and feet[s]['height'][k] <= low[s] + PLANTED_FOOT_RISE_CM for s in feet)]
    if not planted:
        raise RuntimeError('no standing frame with both feet planted')
    k = min(planted, key=lambda i: (speed[i], -i))
    return {'frame': int(k), 'time_s': round(k / m.fps, 4), 'hips_speed_cm_s': round(float(speed[k]), 3),
            'foot_speed_cm_s': {s: round(float(feet[s]['speed'][k]), 3) for s in feet},
            'standing_until_frame': leave, 'candidates': len(planted),
            'rule': f'standing frames (torso <= {B.STANDING_MAX_TILT_DEG} deg, leg extension >= {V.STANDING_MIN_LEG_EXTENSION} x rest, '
                    f'the verifier\'s standing rule) before he starts to sit, with both foot joints <= {PLANTED_FOOT_CM_S} cm/s '
                    f'and within {PLANTED_FOOT_RISE_CM} cm of their standing minimum; the lowest hips speed wins'}


def ease_in(m: B.Motion, start, ease_s=EASE_IN_S):
    """Playback from `start` with u(t) = t^2 / 2R for t < R, then t - R/2: zero velocity at the first frame."""
    R = ease_s
    n_src = (len(m) - 1 - start) / m.fps
    total = n_src + R / 2
    t = np.arange(int(math.floor(total * m.fps)) + 1) / m.fps
    u = np.where(t < R, t ** 2 / (2 * R), t - R / 2)
    q, tr = sample(m, start + u * m.fps)
    return B.Motion(m.sk, q, tr, m.fps, m.name), start + u * m.fps


def native_handoff_residual(sk, m: B.Motion, frame, work: Path):
    """Pose residual of `frame` against the native Idle candidate's frames and every native Walk phase."""
    out = {}
    f = B.hips_relative(m)[frame]
    for label, path in (('native_walk_walking_glb', ROOT / 'web/house/assets/first-person/walking.glb'),
                        ('idle_candidate_stand_idle_ual_ik', ROOT / 'docs/proposed/standing-idle-retarget/stand_idle_ual_ik.glb')):
        if not path.is_file():
            out[label] = {'file': B.rel(path), 'missing': True}
            continue
        ref = B.Motion.from_glb(sk, V.decoded(path, work))
        d = np.linalg.norm(B.hips_relative(ref) - f, axis=2)
        k = int(np.argmin(d.max(axis=1)))
        out[label] = {'file': B.rel(path), 'sha256': B.sha256(path), 'best_frame': k,
                      'max_joint_cm': round(float(d[k].max()), 3), 'rms_joint_cm': round(float(np.sqrt((d[k] ** 2).mean())), 3),
                      'worst_joint': m.sk.names[int(np.argmax(d[k]))]}
    return out


# ------------------------------------------------------------------ 3. foot contact (leg IK + plantar rule)
class Plantar:
    """Root's fixed plantar vertices skinned on our motions (via leg_ik_life_clip.Soles)."""

    def __init__(self, owner_path: Path, template: Path, work: Path):
        self.template = G.Gltf(template)
        self.soles = LI.Soles(G.Gltf(V.decoded(owner_path, work)), self.template)
        self.node = {n: self.template.by_name[LI.P + n] for n in B.Skeleton(owner_path).names}

    def frames(self, m: B.Motion, idx):
        out = []
        for f in idx:
            vals = {(self.node[n], 'rotation'): tuple(map(float, m.q[f, k])) for k, n in enumerate(m.sk.names)}
            vals[(self.node['Hips'], 'translation')] = tuple(map(float, m.t[f]))
            out.append(vals)
        return out

    def support(self, m: B.Motion, idx):
        rows = []
        for vals in self.frames(m, idx):
            pts = self.soles.heights(LI.world(self.template, vals))
            rows.append({s: self.soles.support(pts[s]) for s in LI.SIDES})
        return rows


def contact_summary(rows):
    out = {}
    for s in LI.SIDES:
        lows = [r[s][0] for r in rows]
        bands = [r[s][1] for r in rows]
        out[s] = {'lowest_cm': [round(min(lows), 4), round(max(lows), 4)], 'min_band_vertices': int(min(bands)),
                  'penetration_cm': round(min(0.0, min(lows)), 4),
                  'pass': min(lows) >= -LI.FLOAT_FLOOR_TOL_M * 100 and max(lows) <= LI.SOLE_BAND_CM[1]
                  and min(bands) >= LI.MIN_SUPPORT_VERTICES}
    out['rule'] = (f'per frame, per foot: lowest plantar vertex in {list(LI.SOLE_BAND_CM)} cm (no penetration) and >= '
                   f'{LI.MIN_SUPPORT_VERTICES} plantar vertices in that band (verify_life_idle_candidate.sole_selection)')
    out['pass'] = all(out[s]['pass'] for s in LI.SIDES)
    out['frames'] = len(rows)
    return out


def planted_frames(m: B.Motion, lo, hi):
    """Frames in [lo, hi) where both feet are planted (joint speed and height rule)."""
    feet = foot_kinematics(m)
    low = {s: feet[s]['height'][lo:hi].min() for s in feet}
    return [k for k in range(lo, hi) if all(feet[s]['speed'][k] <= PLANTED_FOOT_CM_S
                                           and feet[s]['height'][k] <= low[s] + PLANTED_FOOT_RISE_CM for s in feet)]


def plant(m: B.Motion, frames, plantar: Plantar, fade=IK_FADE_FRAMES):
    """leg_ik_life_clip.correct on a contiguous run of planted frames; outside the run the boundary frame's
    correction (local rotation deltas and the vertical hips delta) fades out over `fade` frames."""
    a, b = min(frames), max(frames)
    if b - a + 1 != len(frames):
        raise ValueError('plant() needs a contiguous run of frames')
    idx = list(range(a, b + 1))
    vals = plantar.frames(m, idx)
    times = [k / m.fps for k in range(len(idx))]
    owner = V.Owner(G.Gltf(B.OWNER))
    fixed, report = LI.correct(plantar.template, owner, plantar.soles, times, vals)
    q, t = m.q.copy(), m.t.copy()
    for j, k in enumerate(idx):
        q[k] = np.array([fixed[j][(plantar.node[n], 'rotation')] for n in m.sk.names])
        t[k] = np.array(fixed[j][(plantar.node['Hips'], 'translation')])
    ident = np.array([0.0, 0.0, 0.0, 1.0])
    for edge, direction in ((a, -1), (b, 1)):
        delta = B.qmul(q[edge], B.qconj(m.q[edge]))            # local delta, applied on the left
        dt = t[edge] - m.t[edge]
        for d in range(1, fade + 1):
            k = edge + direction * d
            if not 0 <= k < len(m):
                break
            w = float(smootherstep(1 - d / (fade + 1)))
            q[k] = B.qnormalize(B.qmul(B.slerp(np.broadcast_to(ident, delta.shape), delta, w), m.q[k]))
            t[k] = m.t[k] + dt * w
    report = {**report, 'frames': [a, b], 'fade_frames': fade,
              'fade': 'the boundary frame\'s IK correction (leg local-rotation deltas, vertical hips delta) faded out '
                      'with smootherstep outside the planted run; upper body untouched',
              'tool': 'tools/leg_ik_life_clip.correct (imported unchanged)'}
    return B.Motion(m.sk, q, t, m.fps, m.name), report


# ------------------------------------------------------------------ 4. sleep loop and settle
def lying_still_run(m: B.Motion, limit=LOOP_STILL_CM_S):
    """The first run of captured lying frames moving less than `limit` (max joint, hips-relative)."""
    rel, _ = joint_speed(m)
    tilt = B.torso_tilt_deg(m)
    k = 0
    while k < len(rel) and rel[k] < limit and tilt[k] > B.LYING_MIN_TILT_DEG:
        k += 1
    return k                                              # frames 0..k are still


def make_loop(m: B.Motion, last, n):
    """leg_ik_life_clip.seam_blend over captured frames 0..last: O[j] = C[j+n], closed with smootherstep."""
    names = m.sk.names
    frames = [{**{(k, 'rotation'): tuple(map(float, m.q[f, k])) for k in range(len(names))},
               ('hips', 'translation'): tuple(map(float, m.t[f]))} for f in range(last + 1)]
    times = [f / m.fps for f in range(last + 1)]
    _, out, src = LI.seam_blend(times, frames, n)
    q = np.array([[o[(k, 'rotation')] for k in range(len(names))] for o in out])
    t = np.array([o[('hips', 'translation')] for o in out])
    return B.Motion(m.sk, B.qnormalize(q), t, m.fps, 'SleepLoop'), src


def best_loop_end(m: B.Motion, still_last, n, max_gap_cm=LOOP_MAX_SEAM_CM):
    """Loop length: the LAST captured still frame (>= 3n) whose pose is within max_gap_cm of frame n (where the
    loop starts), so the loop is as long as the still capture allows; else the closest frame."""
    f = B.hips_relative(m)
    cand = range(3 * n, still_last + 1)
    d = {k: float(np.linalg.norm(f[k] - f[n], axis=1).max()) for k in cand}
    ok = [k for k in cand if d[k] <= max_gap_cm]
    k = max(ok) if ok else min(d, key=d.get)
    return k, d[k]


def settle(lie: B.Motion, i, loop: B.Motion, p, N):
    """N+1 frames: the lie-down held at captured frame i, the loop advancing from phase p; smootherstep."""
    L = len(loop) - 1
    kb = (np.arange(p, p + N + 1)) % L
    w = smootherstep(np.arange(N + 1) / N)
    qa = np.broadcast_to(lie.q[i], (N + 1,) + lie.q[i].shape)
    ta = np.broadcast_to(lie.t[i], (N + 1, 3))
    return B.slerp(qa, loop.q[kb], w[:, None]), ta * (1 - w[:, None]) + loop.t[kb] * w[:, None]


def settle_peak(lie, i, loop, p, N):
    q, t = settle(lie, i, loop, p, N)
    rel, world = joint_speed(B.Motion(lie.sk, q, t, lie.fps))
    return float(rel.max()), float(world.max())


def place(onto: B.Motion, i, m: B.Motion, p):
    th, off = B.fit_yaw_translation(onto.world()[0][i], m.world()[0][p], anchor=onto.sk.index['Hips'])
    return th, off


def search_settle(lie: B.Motion, lie_frames, loop: B.Motion, N, end_phase=0, top=40):
    """Lie frame i (truncation) for a settle that ENDS at loop phase `end_phase`; minimal peak joint speed."""
    L = len(loop) - 1
    p = (end_phase - N) % L
    fl, fo = B.hips_relative(lie), B.hips_relative(loop)
    d = np.array([np.linalg.norm(fo[p] - fl[i], axis=1).max() for i in lie_frames])
    order = np.argsort(d)[:top]
    best = None
    for o in order:
        i = int(lie_frames[o])
        th, off = place(lie, i, loop, p)
        rel, world = settle_peak(lie, i, loop.placed(th, off), p, N)
        row = (rel, i, float(d[o]), world, th, off)
        if best is None or row[0] < best[0]:
            best = row
    rel, i, pose, world, th, off = best
    return {'lie_frame': i, 'loop_phase_at_start': int(p), 'loop_phase_at_end': end_phase, 'frames': N,
            'pose_gap_cm': round(pose, 3), 'peak_joint_speed_hips_relative_cm_s': round(rel, 3),
            'peak_joint_speed_world_cm_s': round(world, 3), '_placement': (th, off)}


def search_any_phase(lie: B.Motion, lie_frames, loop: B.Motion, N, top=30):
    """For the alternatives: any loop phase (both ends held / advancing as in settle()); minimal peak speed."""
    L = len(loop) - 1
    fl, fo = B.hips_relative(lie), B.hips_relative(loop)[:L]
    D = np.array([np.linalg.norm(fo - fl[i], axis=2).max(axis=1) for i in lie_frames])
    best = None
    for o in np.argsort(D.ravel())[:top]:
        a, p = np.unravel_index(o, D.shape)
        i = int(lie_frames[a])
        th, off = place(lie, i, loop, int(p))
        rel, world = settle_peak(lie, i, loop.placed(th, off), int(p), N)
        if best is None or rel < best[0]:
            best = (rel, i, int(p), float(D[a, p]), world)
    return {'lie_frame': best[1], 'loop_phase': best[2], 'pose_gap_cm': round(best[3], 3),
            'peak_joint_speed_hips_relative_cm_s': round(best[0], 3), 'peak_joint_speed_world_cm_s': round(best[4], 3)}


def wake_side_alternative(loop: B.Motion, wake: B.Motion, wake_frames, N, top=30):
    """Loop (advancing, from phase s) into the get-up held at a still lying frame m, then the get-up plays."""
    L = len(loop) - 1
    fo, fw = B.hips_relative(loop)[:L], B.hips_relative(wake)
    D = np.array([np.linalg.norm(fw[m] - fo, axis=2).max(axis=1) for m in wake_frames]).T      # (L, |wake|)
    best = None
    for o in np.argsort(D.ravel())[:top]:
        s, b = np.unravel_index(o, D.shape)
        m = int(wake_frames[b])
        kb = (np.arange(s, s + N + 1)) % L
        w = smootherstep(np.arange(N + 1) / N)
        q = B.slerp(loop.q[kb], np.broadcast_to(wake.q[m], (N + 1,) + wake.q[m].shape), w[:, None])
        th, off = place(loop, int((s + N) % L), wake, m)
        wp = wake.placed(th, off)
        t = loop.t[kb] * (1 - w[:, None]) + wp.t[m] * w[:, None]
        q[:, 0] = B.slerp(loop.q[kb, 0], wp.q[m, 0], w)
        rel, world = joint_speed(B.Motion(loop.sk, q, t, loop.fps))
        if best is None or rel.max() < best[0]:
            best = (float(rel.max()), int(s), m, float(D[s, b]), float(world.max()))
    return {'loop_phase': best[1], 'wake_frame': best[2], 'pose_gap_cm': round(best[3], 3),
            'peak_joint_speed_hips_relative_cm_s': round(best[0], 3), 'peak_joint_speed_world_cm_s': round(best[4], 3)}


def seconds_for(peak_at, N_at, target=TARGET_JOINT_SPEED_CM_S):
    """Window length that would bring a settle's peak to `target` (peak scales ~1/T for held endpoints)."""
    return round(peak_at * (N_at / FPS) / target, 3)


# ------------------------------------------------------------------ writer
def write_labelled(m: B.Motion, template: Path, out: Path, name: str, labels, provenance: dict, extras=None):
    g = G.Gltf(template)
    node = {V.canonical(n.get('name', '')): i for i, n in enumerate(g.nodes) if V.PREFIX.match(n.get('name', ''))}
    bw = G.BinWriter()
    ti = bw.add([k / m.fps for k in range(len(m))], 'SCALAR', minmax=True)
    anim = {'name': name, 'samplers': [], 'channels': [], 'extras': {'sub01_labels': list(labels)}}
    q = m.q.copy()
    for f in range(1, len(q)):
        flip = np.sum(q[f] * q[f - 1], axis=1) < 0
        q[f, flip] *= -1
    for k, n in enumerate(m.sk.names):
        vi = bw.add([tuple(map(float, v)) for v in q[:, k]], 'VEC4')
        anim['samplers'].append({'input': ti, 'output': vi, 'interpolation': 'LINEAR'})
        anim['channels'].append({'sampler': len(anim['samplers']) - 1, 'target': {'node': node[n], 'path': 'rotation'}})
        if n == 'Hips':
            vt = bw.add([tuple(map(float, v)) for v in m.t], 'VEC3')
            anim['samplers'].append({'input': ti, 'output': vt, 'interpolation': 'LINEAR'})
            anim['channels'].append({'sampler': len(anim['samplers']) - 1, 'target': {'node': node[n], 'path': 'translation'}})
    asset = {'version': '2.0', 'generator': 'SUB01 bed_transition_corrections (PRIVATE)',
             'extras': {'sub01_labels': list(labels), 'sub01_provenance': provenance, **(extras or {})}}
    doc = {'asset': asset, 'scene': 0, 'scenes': g.doc['scenes'], 'nodes': g.doc['nodes'], 'animations': [anim],
           'accessors': bw.accessors, 'bufferViews': bw.views,
           'buffers': [{'byteLength': len(bw.data) + (-len(bw.data)) % 4}]}
    return G.write_glb(out, doc, bytes(bw.data))


def in_place_common(m: B.Motion, origin_xz):
    t = m.t.copy()
    t[:, 0], t[:, 2] = origin_xz[0], origin_xz[1]
    return B.Motion(m.sk, m.q, t, m.fps, m.name)


def common_path(m: B.Motion, origin):
    """Mesh root path in the component frame of the LieDown's first frame (forward/right cm)."""
    pos, _ = m.world()
    h = pos[:, m.sk.index['Hips']] - origin
    return {'t_s': [round(k / m.fps, 5) for k in range(len(m))],
            'forward_cm': [round(float(v), 3) for v in h @ m.sk.forward],
            'right_cm': [round(float(v), 3) for v in h @ m.sk.right]}


# ------------------------------------------------------------------ the run
def run(out_dir: Path, work: Path, owner_path: Path = B.OWNER, write=True):
    out_dir.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    sk = B.Skeleton(owner_path)
    quotes = B.check_documented()
    raw, templates, rt = {}, {}, {}
    for role, src in B.SOURCES.items():
        path, _, rep = B.retarget_v5(src, work / role, owner_path)
        raw[role], templates[role], rt[role] = B.Motion.from_glb(sk, path, name=role), path, rep
    template = templates['LieDown']
    plantar = Plantar(owner_path, template, work)
    lie_raw, wake_raw = raw['LieDown'], raw['GetUp']

    # ---- GetUp: seated slide
    win = detect_seated_slide(wake_raw)
    wake_ns, removed = remove_seated_slide(wake_raw, win)
    crop_raw = B.detect_standing_crop(B.standing_mask(wake_raw), B.hips_speed(wake_raw), FPS)
    crop = B.detect_standing_crop(B.standing_mask(wake_ns), B.hips_speed(wake_ns), FPS)
    lie_seat = first_seated_frame(lie_raw, after=int(np.argmin(B.standing_mask(lie_raw))))
    wake_seat = first_seated_frame(wake_raw, after=win['end_frame'])
    geometry = {
        'lie_down_seat_to_lying_end_cm': seat_to_lying_offset(lie_raw, len(lie_raw) - 1, lie_seat),
        'get_up_lying_start_to_seat_cm_raw': seat_to_lying_offset(wake_raw, 0, wake_seat),
        'get_up_lying_start_to_seat_cm_corrected': seat_to_lying_offset(wake_ns, 0, wake_seat),
        'seated_frames': {'lie_down': lie_seat, 'get_up': wake_seat},
        'reading': 'the lie-down sits on the bed edge and lies down ~25 cm further in; the raw get-up lies ~1 m from '
                   'its seat. After the hold the two agree, so the 79 cm run is a source artefact, not a scoot.'}
    in_win = slice(win['start_frame'], win['end_frame'] + 1)
    slide = {'window': win, 'removed_horizontal_cm': [round(float(v), 3) for v in removed[-1]],
             'removed_distance_cm': round(float(np.linalg.norm(removed[-1])), 3),
             'hips_travel_inside_window_cm': {
                 'raw': round(float(np.linalg.norm(np.diff(wake_raw.t[in_win][:, [0, 2]], axis=0), axis=1).sum()), 3),
                 'corrected': round(float(np.linalg.norm(np.diff(wake_ns.t[in_win][:, [0, 2]], axis=0), axis=1).sum()), 3)},
             'feet_during_window': {s: {'max_joint_height_cm': round(float(v['height'][in_win].max()), 2)}
                                    for s, v in foot_kinematics(wake_raw).items()},
             'geometry_check': geometry,
             'root_path_full_clip': {'raw': path_stats(wake_raw), 'corrected': path_stats(wake_ns)},
             'root_path_to_crop': {'raw': path_stats(wake_raw.slice(0, crop_raw['crop_frame'] + 1)),
                                   'corrected': path_stats(wake_ns.slice(0, crop['crop_frame'] + 1))},
             'crop_raw': crop_raw, 'crop_corrected': crop,
             'method': f'hips horizontal displacement inside the window subtracted (Gaussian sigma {SLIDE_SMOOTH_FRAMES} '
                       'frames); rotations untouched; the vertical path untouched; frames after the window keep their '
                       'captured path, offset by the removed travel; not redistributed (no step carries it)'}

    # ---- the sleep loop: the get-up's captured lying-still head, loop-closed
    n_seam = int(round(LOOP_SEAM_BLEND_S * FPS))
    still = lying_still_run(wake_ns)
    last, seam_raw = best_loop_end(wake_ns, still, n_seam)
    loop, loop_src = make_loop(wake_ns, last, n_seam)
    L = len(loop) - 1
    loop_rel, loop_world = joint_speed(loop)
    loop_seam = B.gap(loop, L, loop, 0)

    # ---- LieDown start: trim + ease-in
    start = choose_standing_start(lie_raw)
    lie_e, src_pos = ease_in(lie_raw, start['frame'])
    handoff = native_handoff_residual(sk, lie_raw, start['frame'], work)

    # ---- settle: lie-down (held at a still lying frame) into the loop, ending at loop phase 0
    lie_rel, _ = joint_speed(lie_e)
    tilt_e = B.torso_tilt_deg(lie_e)
    lie_still = [i for i in range(len(lie_e) - 1) if tilt_e[i] > B.LYING_MIN_TILT_DEG
                 and lie_rel[max(0, i - 3):i + 3].max() < LOOP_STILL_CM_S]
    N = int(round(SETTLE_S * FPS))
    options = {}
    for s in SETTLE_OPTIONS_S:
        r = search_settle(lie_e, lie_still, loop, int(round(s * FPS)))
        options[f'{s:.1f}s'] = {k: v for k, v in r.items() if not k.startswith('_')}
    chosen = search_settle(lie_e, lie_still, loop, N)
    i = chosen['lie_frame']
    th, off = chosen['_placement']
    loop_p = loop.placed(th, off)
    wake_p = wake_ns.placed(th, off)            # the loop is the get-up's own frames: one rigid placement for both
    get_c = wake_p.slice(n_seam, crop['crop_frame'] + 1)
    get_c.name = 'GetUp'

    # ---- floor reference: one constant vertical shift per clip, so the planted soles start on y = 0
    def head_run(m, hi):
        run = planted_frames(m, 0, hi)
        return list(range(0, next((k for k in range(len(run)) if run[k] != k), len(run))))

    def tail_run(m, lo):
        run = set(planted_frames(m, lo, len(m)))
        out = []
        for k in range(len(m) - 1, lo - 1, -1):
            if k not in run:
                break
            out.append(k)
        return sorted(out)

    run_lie = head_run(lie_e, int(np.argmin(B.torso_tilt_deg(lie_e) <= B.STANDING_MAX_TILT_DEG)))
    standing = B.standing_mask(get_c)
    onset = len(get_c) - 1
    while onset > 0 and standing[onset - 1]:
        onset -= 1
    run_get = tail_run(get_c, onset)
    if not run_lie or not run_get:
        raise RuntimeError('no planted standing run to put on the floor')

    def floor_shift(m, frames):
        rows = plantar.support(m, frames)
        return -min(min(r[s][0] for s in LI.SIDES) for r in rows)

    shift = {'LieDown': floor_shift(lie_e, run_lie), 'SleepLoop_and_GetUp': floor_shift(get_c, run_get)}
    lie_e.t = lie_e.t.copy()
    lie_e.t[:, 1] += shift['LieDown']
    lie_e._pos = None
    for m in (loop_p, wake_p):
        m.t = m.t.copy()
        m.t[:, 1] += shift['SleepLoop_and_GetUp']
        m._pos = None
    get_c = wake_p.slice(n_seam, crop['crop_frame'] + 1)
    get_c.name = 'GetUp'
    floor_reference = {
        'shift_cm': {k: round(v, 4) for k, v in shift.items()},
        'rule': 'one constant vertical hips shift per clip so that the lower foot of the planted standing run has its '
                'lowest plantar vertex at y = 0 (no penetration); the source floor sits off y = 0',
        'lying_height_change_inside_settle_cm': round(shift['SleepLoop_and_GetUp'] - shift['LieDown'], 4),
        'note': 'the loop and the get-up share one placement, so the settle carries the difference smoothly'}
    sq, st = settle(lie_e, i, loop_p, chosen['loop_phase_at_start'], N)
    lie_c = B.Motion(sk, np.concatenate([lie_e.q[:i], sq]), np.concatenate([lie_e.t[:i], st]), FPS, 'LieDown')

    # ---- foot contact: LieDown standing start and GetUp standing end (leg IK on the planted runs)
    contact = {}
    contact['LieDown_raw'] = contact_summary(plantar.support(lie_raw, range(0, int(0.2 * FPS) + 1)))
    contact['LieDown_before_ik'] = contact_summary(plantar.support(lie_c, run_lie))
    lie_c, ik_lie = plant(lie_c, run_lie, plantar)
    contact['LieDown_corrected'] = contact_summary(plantar.support(lie_c, run_lie))
    contact['GetUp_raw_end'] = contact_summary(plantar.support(wake_raw, range(crop_raw['crop_frame'] - int(0.2 * FPS),
                                                                                crop_raw['crop_frame'] + 1)))
    contact['GetUp_before_ik'] = contact_summary(plantar.support(get_c, run_get))
    get_c, ik_get = plant(get_c, run_get, plantar)
    contact['GetUp_corrected'] = contact_summary(plantar.support(get_c, run_get))

    # ---- continuity of the composed chain
    whole = B.concat(sk, [(lie_c.q, lie_c.t), (loop_p.q[1:], loop_p.t[1:]), (get_c.q[1:], get_c.t[1:])], FPS, 'chain')
    a0 = i
    a1 = len(lie_c) - 1
    b0 = a1 + L
    seams = B.seam_metrics(whole, {'settle_window': (a0, a1), 'lie_down_into_loop': (a1 - 2, a1 + 3),
                                    'loop_into_get_up': (b0 - 2, b0 + 3), 'loop_itself': (a1, b0)})
    get_rel, _ = joint_speed(wake_raw.slice(0, 80))
    continuity = {
        'settle': {**{k: v for k, v in chosen.items() if not k.startswith('_')}, 'seconds': SETTLE_S,
                   'weight': 'smootherstep (C2); lie-down held at its captured frame, loop advancing'},
        'settle_options': options,
        'lie_down_end_vs_loop_start': B.gap(lie_c, len(lie_c) - 1, loop_p, 0),
        'loop_end_vs_get_up_start': B.gap(loop_p, L, get_c, 0),
        'seams': seams,
        'loop_own_joint_speed_cm_s': {'max': round(float(loop_rel.max()), 3), 'median': round(float(np.median(loop_rel)), 3)},
        'get_up_source_lying_head_speed_cm_s': {'max': round(float(get_rel.max()), 3)},
        'raw_b7b099b_blend_peaks_cm_s': {'lie_blend': 204, 'wake_blend': 231, 'source': 'docs/proposed/bed-transition-pipeline.md'},
    }

    # ---- alternatives, measured with the same held-endpoint settle
    alternatives = {}
    wake_still = [k for k in range(still + 1)]
    for name, path in ALTERNATIVE_LOOPS.items():
        if 'mh_v5' in str(path):
            p, _, _ = B.retarget_v5(path, work / name, owner_path)
            alt = B.Motion.from_glb(sk, p, name=name)
        else:
            alt = B.Motion.from_glb(sk, path, name=name)
        row = {'file': B.rel(path), 'sha256': B.sha256(path), 'posture': max(set(B.posture(alt)), key=B.posture(alt).count)}
        for s in SETTLE_OPTIONS_S:
            n = int(round(s * FPS))
            row[f'lie_side_{s:.1f}s'] = search_any_phase(lie_e, lie_still, alt, n)
            row[f'wake_side_{s:.1f}s'] = wake_side_alternative(alt, wake_ns, wake_still, n)
        worst = max(row['lie_side_2.5s']['peak_joint_speed_hips_relative_cm_s'], row['wake_side_2.5s']['peak_joint_speed_hips_relative_cm_s'])
        row['seconds_needed_for_40_cm_s'] = seconds_for(worst, 75)
        alternatives[name] = row
    alternatives['notes'] = [
        'mixamo_laying_sleeping_v5 is the Mixamo capture after the mh_retarget + bed_fit chain; docs/design/mixamo/README.md: '
        '"The lift and the raised fists came from the retarget and bed-fit chain, not from the captures."',
        'Sova loops: their right arm lies over the head; every lie-down / get-up lying frame has it at the side (~85 cm '
        'apart at the fingertips), so no window inside 2.5 s keeps the joints under 40 cm/s.']

    # ---- outputs
    origin = lie_c.world()[0][0, sk.index['Hips']].copy()
    origin_xz = lie_c.t[0, [0, 2]].copy()
    prov = {'label': PROVENANCE_LABEL, 'text': PROVENANCE_TEXT,
            'sources_sha256': {B.rel(p): B.sha256(p) for p in B.SOURCES.values()}, 'capture_claimed': False,
            'capture_method': 'undocumented'}
    labels = {'LieDown': ['retargeted', 'walk_in_trimmed', 'ease_in_retime', 'leg_ik_floor_contact', 'sleep_settle_blend',
                          'lie_down_truncated'],
              'SleepLoop': ['retargeted', 'seated_slide_removed', 'lying_segment_of_get_up_source', 'sleep_loop_seam_blend'],
              'GetUp': ['retargeted', 'seated_slide_removed', 'head_trimmed_to_loop_start', 'cropped_before_walk',
                        'leg_ik_floor_contact']}
    motions = {'LieDown': lie_c, 'SleepLoop': loop_p, 'GetUp': get_c}
    outputs, paths = {}, {}
    for role, m in motions.items():
        outputs[role] = {}
        for var, mm in (('in_place', in_place_common(m, origin_xz)), ('travel_in_hips', m)):
            glb = (out_dir if write else work) / f'SUB01_{role}.corrected.{var}.glb'
            sha = write_labelled(mm, template, glb, f'SUB01_{role}', labels[role] + [var],
                                 prov, {'sub01_variant': var, 'sub01_role': role})
            outputs[role][var] = {'path': B.rel(glb), 'sha256': sha, 'bytes': glb.stat().st_size, 'frames': len(mm),
                                  'duration_s': round(mm.duration, 4)}
        paths[role] = {'clip_sha256_in_place': outputs[role]['in_place']['sha256'], **common_path(m, origin)}
    root_paths = {'schema': 'sub01.bed-mesh-root-path.v1',
                  'frame': 'component frame of the LieDown first frame: forward = owner rest facing, right = owner rest '
                           'right, cm; UE character-local X forward, Y right. The capsule stays at the approach point; '
                           'the mesh offset is this path (tools/unreal_bed_root_motion.py; docs/proposed/bed-transition-pipeline.md).',
                  'fps': FPS, 'roles': paths,
                  'return_residual_cm': [paths['GetUp']['forward_cm'][-1], paths['GetUp']['right_cm'][-1]],
                  'return_distance_cm': round(math.hypot(paths['GetUp']['forward_cm'][-1], paths['GetUp']['right_cm'][-1]), 3)}
    (out_dir / 'SUB01_bed_mesh_root_paths.json').write_text(B.dump(root_paths, work))

    raw_paths = {'LieDown': path_stats(lie_raw), 'GetUp_to_crop': slide['root_path_to_crop']['raw']}
    common = {'schema': SCHEMA, 'private': True, 'provenance_label': PROVENANCE_LABEL, 'provenance': prov,
              'documented_quotes': quotes, 'accepted_for_binding': False, 'native_bed_verified': False,
              'never': 'not run in Unreal or Blender; no runtime receipt; the bed is unmeasured; nothing deployed'}
    reports = {
        'LieDown': {**common, 'role': 'LieDown', 'labels': labels['LieDown'], 'outputs': outputs['LieDown'],
                    'retarget': {k: v for k, v in rt['LieDown'].items() if k != 'mapping'},
                    'walk_in_handoff': {'start': start, 'ease_in_s': EASE_IN_S,
                                        'raw_start_hips_speed_cm_s': round(float(B.hips_speed(lie_raw)[0]), 3),
                                        'corrected_start_hips_speed_cm_s': round(float(B.hips_speed(lie_c)[0]), 3),
                                        'native_pose_residual': handoff,
                                        'adapter': 'WalkToBed stops within 12 cm, then TurnInPlace: the clip starts from a '
                                                   'stand-still, so a stand-still start is the matching hand-off'},
                    'root_path': {'raw': raw_paths['LieDown'], 'corrected': path_stats(lie_c)},
                    'foot_contact': {'raw_first_0.2s': contact['LieDown_raw'], 'before_ik': contact['LieDown_before_ik'],
                                     'corrected': contact['LieDown_corrected'], 'leg_ik': ik_lie},
                    'floor_reference': floor_reference,
                    'settle': continuity['settle'], 'duration_s': {'raw': round(lie_raw.duration, 4), 'corrected': round(lie_c.duration, 4)}},
        'SleepLoop': {**common, 'role': 'SleepLoop', 'labels': labels['SleepLoop'], 'outputs': outputs['SleepLoop'],
                      'source': {'clip': 'GetUp source (web/room/mh_v5/room_bed_wake.glb), seated slide removed',
                                 'captured_frames': [n_seam, last], 'still_run_frames': [0, still],
                                 'rule': f'captured lying frames moving < {LOOP_STILL_CM_S} cm/s; loop end = the last of them within '
                                         f'{LOOP_MAX_SEAM_CM} cm of the loop start; leg_ik_life_clip.seam_blend over {n_seam} frames'},
                      'seam': {'captured_gap_before_blend_cm': round(seam_raw, 3), 'after_blend': loop_seam,
                               'seam_blend_source_map': loop_src[-3:]},
                      'loop_own_joint_speed_cm_s': continuity['loop_own_joint_speed_cm_s'],
                      'continuity': continuity, 'alternatives_measured': alternatives,
                      'chosen_because': 'lowest transition joint speeds of every option measured (see alternatives); '
                                        'same posture class (supine) at both ends; zero gap into the get-up'},
        'GetUp': {**common, 'role': 'GetUp', 'labels': labels['GetUp'], 'outputs': outputs['GetUp'],
                  'retarget': {k: v for k, v in rt['GetUp'].items() if k != 'mapping'},
                  'seated_slide': slide, 'floor_reference': floor_reference,
                  'head_trim_frames': n_seam,
                  'root_path': {'raw_to_crop': raw_paths['GetUp_to_crop'], 'corrected': path_stats(get_c)},
                  'foot_contact': {'raw_last_0.2s': contact['GetUp_raw_end'], 'before_ik': contact['GetUp_before_ik'],
                                   'corrected': contact['GetUp_corrected'], 'leg_ik': ik_get},
                  'duration_s': {'raw_cropped': round(crop_raw['crop_frame'] / FPS, 4), 'corrected': round(get_c.duration, 4)}},
    }
    for role, rep in reports.items():
        (out_dir / f'SUB01_{role}.corrected.report.json').write_text(B.dump(rep, work, indent=1))
    summary = {'schema': 'sub01.bed-transition-corrections.v1', 'outputs': outputs, 'continuity': continuity,
               'return_residual_cm': root_paths['return_residual_cm'], 'contact': {k: v['pass'] for k, v in contact.items()},
               'accepted_for_binding': False, 'provenance_label': PROVENANCE_LABEL}
    (out_dir / 'bed-transition-corrections.summary.json').write_text(B.dump(summary, work, indent=1))
    return reports, summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('out_dir', type=Path)
    ap.add_argument('--work', type=Path)
    ap.add_argument('--owner', type=Path, default=B.OWNER)
    args = ap.parse_args(argv)
    _, summary = run(args.out_dir, args.work or args.out_dir / 'work', args.owner)
    print(json.dumps({k: summary[k] for k in ('contact', 'return_residual_cm', 'provenance_label')}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
