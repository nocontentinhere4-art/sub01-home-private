"""Leg-IK support and loop-seam correction for a retargeted owner idle; measured and labelled.

    python3 tools/leg_ik_life_clip.py RETARGET.glb OUTPUT.glb [--owner web/room/char_mixamo.glb]
        [--blend auto|none|SECONDS] [--work DIR] [--raw-report RETARGET.glb.report.json]

Input: an owner-skeleton clip from tools/retarget_life_clip.py. Output: the same clip with only
these documented changes, each reported in OUTPUT.report.json and labelled in the GLB
(asset.extras.sub01_labels and animation extras):

* seam_blend (only when the raw loop seam fails the verifier): the standard captured-pose loop
  crossfade. The clip is shortened by N frames, and its last N frames are slerped (rotations) /
  lerped (hips translation) toward its first N frames with smootherstep (C2) weights, so the last frame is
  the first frame and the seam velocity is continuous. Every frame outside that window is a
  captured frame, unchanged. N, and the raw and blended seam pose and velocity, are reported.
* leg_ik_support (only for a foot whose fixed plantar patch is not supported on the floor): an
  analytic two-bone IK per leg (UpLeg -> Leg -> Foot). The ankle target is the captured ankle moved
  VERTICALLY so the foot's lowest plantar vertex sits on the floor (y = 0, plus a 0.001 cm float
  margin). The knee stays in the captured knee plane (pole = captured knee direction of that
  frame), the foot keeps its captured WORLD orientation, and the toe its captured local rotation.
  Only the UpLeg, Leg and Foot local rotations change. Bone translations are the owner's, so bone
  lengths cannot change.
* root_support (only if a foot target is out of the leg's reach): a smooth, bounded, purely
  VERTICAL hips offset, applied as part of the hips track (never a horizontal move).

A foot whose lowest plantar vertex is already within 0 to +0.1 cm is left untouched, so a clip
whose feet are on the floor comes out unchanged. Plantar vertices are root's fixed rule
(verify_life_idle_candidate.sole_selection: material "feet", rest Y <= 0.004 m, bind normal
Y < -0.7). The support patch needs at least 12 plantar vertices within 0 to +1 cm per foot
(MIN_SUPPORT_VERTICES and SOLE_BAND_CM of tools/validate_unreal_seat_contact.py). Upper-body
rotations are copied from the input value for value: their reported delta must be 0.
The verifier (thresholds untouched) then judges the output.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import life_gltf as G  # noqa: E402
import verify_life_idle_candidate as V  # noqa: E402

SCHEMA = 'sub01.life-clip-leg-ik.v1'
P = V.OWNER_PREFIX
SOLE_BAND_CM = (0.0, 1.0)            # tools/validate_unreal_seat_contact.py SOLE_BAND_CM
MIN_SUPPORT_VERTICES = 12            # tools/validate_unreal_seat_contact.py MIN_SUPPORT_VERTICES
TOUCH_TOLERANCE_CM = 0.1             # a lowest plantar vertex in 0..0.1 cm is already on the floor
FLOAT_FLOOR_TOL_M = 1e-6             # float noise below y = 0 still counts as touching
FLOOR_MARGIN_M = 1e-5                # targets put the lowest vertex 0.001 cm above y = 0 (float32 safety)
REACH_MARGIN = 1e-3                  # a leg is never solved straighter than (1 - margin) of its length
MAX_ROOT_SUPPORT_CM = 3.0
DEFAULT_BLEND_S = 0.4
LEG = ('UpLeg', 'Leg', 'Foot')
SIDES = ('Left', 'Right')


class Frame:
    """A sampler over one frame's local values {(node, path): value}."""

    def __init__(self, values):
        self.values = values

    def sample(self, node, path, t, default):
        return tuple(self.values.get((node, path), default))


def smootherstep(x):
    """C2 ramp (zero velocity and acceleration at both ends of the blend window)."""
    x = min(1.0, max(0.0, x))
    return x * x * x * (x * (6 * x - 15) + 10)


def read_clip(g: G.Gltf):
    clip = g.animation()
    times = clip.key_times()
    frames = [{key: tuple(clip.sample(key[0], key[1], t, None)) for key in clip.tracks} for t in times]
    return clip, times, frames


def world(g, frame):
    return G.world_pose(g, Frame(frame), 0.0)


def seam_metrics(g, owner, times, frames):
    cand = V.Candidate(g, owner)
    shapes = [V.hips_frame_positions(world(g, f), cand) for f in frames]
    hips = [world(g, f)[cand.node['Hips']][0] for f in (frames[0], frames[-1])]
    fps = (len(times) - 1) / (times[-1] - times[0])
    pose, _, vel = V.loop_metrics(shapes, {0: hips[0], len(frames) - 1: hips[1]}, 0, len(frames) - 1, fps)
    hw = G.vlen(G.vsub(hips[1], hips[0])) * 100
    return {'pose_cm': round(pose, 6), 'hips_world_cm': round(hw, 6), 'velocity_cm_s': round(vel, 6),
            'passes': pose <= V.LOOP_MAX_POSE_CM and hw <= V.LOOP_MAX_POSE_CM and vel <= V.LOOP_MAX_VELOCITY_CM_S}


def seam_blend(times, frames, n):
    """Loop crossfade: O[j] = C[j+N]; the last N+1 frames blend toward C[j+2N-L] (L = last index)."""
    L = len(frames) - 1
    M = L - n
    if n < 1 or M - n < 1:
        raise ValueError('blend window too long for this clip')
    out, source = [], []
    for j in range(M + 1):
        main = frames[j + n]
        if j < M - n:
            out.append(dict(main))
            source.append({'main': j + n})
            continue
        partner = frames[j + 2 * n - L]
        w = smootherstep((j - (M - n)) / n)
        f = {}
        for key, a in main.items():
            b = partner[key]
            f[key] = G.slerp(G.qnorm(a), G.qnorm(b), w) if key[1] == 'rotation' else tuple(x + (y - x) * w for x, y in zip(a, b))
        out.append(f)
        source.append({'main': j + n, 'partner': j + 2 * n - L, 'weight': round(w, 6)})
    new_times = [times[j + n] - times[n] for j in range(M + 1)]
    return new_times, out, source


class Soles:
    def __init__(self, owner_decoded: G.Gltf, g: G.Gltf):
        import numpy as np
        self.np = np
        self.sel = V.sole_selection(owner_decoded)
        self.node = {n: g.by_name[P + n] for n in self.sel['names']}
        self.needed = sorted(set(self.sel['joints'].ravel().tolist()))
        self.homog = np.hstack([self.sel['pos'], np.ones((len(self.sel['pos']), 1))])

    def heights(self, w):
        np = self.np
        mats = np.zeros((len(self.sel['names']), 4, 4))
        for j in self.needed:
            wt = w[self.node[self.sel['names'][j]]]
            mats[j] = V.trs_matrix(wt[0], wt[1], wt[2]) @ self.sel['ibm'][j]
        sk = np.zeros((len(self.homog), 4))
        for k in range(4):
            sk += self.sel['weights'][:, k:k + 1] * np.einsum('nij,nj->ni', mats[self.sel['joints'][:, k]], self.homog)
        return {'Left': sk[self.sel['left'], :3], 'Right': sk[~self.sel['left'], :3]}

    def support(self, pts):
        y = pts[:, 1] * 100
        low = float(y.min())
        band = int(((y >= SOLE_BAND_CM[0]) & (y <= SOLE_BAND_CM[1])).sum())
        return low, band


def two_bone(H, K0, A0, T, a, b):
    """Knee K for hip H, target ankle T, keeping the captured knee plane (pole from K0)."""
    d_vec = G.vsub(T, H)
    d = G.vlen(d_vec)
    if d > (a + b) * (1 - REACH_MARGIN) or d < abs(a - b) + 1e-9:
        raise ValueError('target out of reach')
    u = G.vunit(d_vec)
    pole = G.vsub(K0, H)
    pole = G.vsub(pole, G.vscale(u, G.vdot(pole, u)))
    v = G.vunit(pole)
    cos_a = (a * a + d * d - b * b) / (2 * a * d)
    sin_a = math.sqrt(max(0.0, 1 - cos_a * cos_a))
    return G.vadd(H, G.vadd(G.vscale(u, a * cos_a), G.vscale(v, a * sin_a)))


def correct(g: G.Gltf, owner: V.Owner, soles: Soles, times, frames):
    """Root support (vertical, smooth, bounded) and per-frame leg IK. Returns new frames and a report."""
    idx = {n: g.by_name[P + n] for n in owner.names}
    hips = idx['Hips']
    n_frames = len(frames)
    # Pass 1: what each foot needs, and the vertical hips drop that reach requires.
    need = []
    for f in frames:
        w = world(g, f)
        pts = soles.heights(w)
        row = {}
        for side in SIDES:
            low = float(pts[side][:, 1].min())
            touching = -FLOAT_FLOOR_TOL_M <= low <= TOUCH_TOLERANCE_CM / 100
            dy = 0.0 if touching else FLOOR_MARGIN_M - low
            up, leg, foot = (idx[side + x] for x in LEG)
            a = G.vlen(G.vsub(w[leg][0], w[up][0]))
            b = G.vlen(G.vsub(w[foot][0], w[leg][0]))
            T = G.vadd(w[foot][0], (0.0, dy, 0.0))
            H = w[up][0]
            R = (a + b) * (1 - REACH_MARGIN) - 1e-7
            h2 = (T[0] - H[0]) ** 2 + (T[2] - H[2]) ** 2
            vertical = H[1] - T[1]
            drop = max(0.0, vertical - math.sqrt(max(0.0, R * R - h2))) if not touching else 0.0
            row[side] = {'low_cm': low * 100, 'dy': dy, 'touching': touching, 'drop': drop}
        need.append(row)
    required = [max(r[s]['drop'] for s in SIDES) for r in need]
    k = max(1, int(round(0.2 * (n_frames - 1) / (times[-1] - times[0]))))           # 0.2 s half-window

    def cyclic(vals, fn):
        return [fn([vals[(i + o) % (n_frames - 1)] for o in range(-k, k + 1)]) for i in range(n_frames - 1)]
    if any(required):
        env = cyclic(cyclic(required, max), lambda v: sum(v) / len(v))      # closing then mean: >= required
        env.append(env[0])
    else:
        env = [0.0] * n_frames
    if max(env) * 100 > MAX_ROOT_SUPPORT_CM:
        raise RuntimeError(f'root support of {max(env) * 100:.3f} cm exceeds the {MAX_ROOT_SUPPORT_CM} cm bound')
    out, per_frame = [], []
    knee_plane_dev, foot_world_dev, ik_feet = 0.0, 0.0, {s: 0 for s in SIDES}
    for fi, f in enumerate(frames):
        f = dict(f)
        if env[fi]:
            t = f[(hips, 'translation')]
            pw = G.world_pose(g, G.RestPose, 0, [g.parent[hips]])[g.parent[hips]]
            f[(hips, 'translation')] = (t[0], t[1] - env[fi] / pw[2], t[2])
        captured = world(g, frames[fi])
        moved = world(g, f)
        pts = soles.heights(moved)
        info = {}
        for side in SIDES:
            low = float(pts[side][:, 1].min())
            if -FLOAT_FLOOR_TOL_M <= low <= TOUCH_TOLERANCE_CM / 100:
                info[side] = {'ik': False, 'dy_cm': 0.0}
                continue
            up, leg, foot = (idx[side + x] for x in LEG)
            for _ in range(3):                              # converge on the skinned plantar patch
                w = world(g, f)
                low = float(soles.heights(w)[side][:, 1].min())
                dy = FLOOR_MARGIN_M - low
                if abs(dy) < 1e-7:
                    break
                H, K0, A0 = w[up][0], w[leg][0], w[foot][0]
                a, b = G.vlen(G.vsub(K0, H)), G.vlen(G.vsub(A0, K0))
                T = G.vadd(A0, (0.0, dy, 0.0))
                K = two_bone(H, K0, A0, T, a, b)            # pole: this frame's captured knee plane
                R1 = G.arc(G.vsub(K0, H), G.vsub(K, H))
                w_up = G.qnorm(G.qmul(R1, w[up][1]))
                R2 = G.arc(G.qrot(R1, G.vsub(A0, K0)), G.vsub(T, K))
                w_leg = G.qnorm(G.qmul(R2, G.qmul(R1, w[leg][1])))
                w_foot = captured[foot][1]                   # the captured world foot orientation
                f[(up, 'rotation')] = G.qnorm(G.qmul(G.qinv(w[hips][1]), w_up))
                f[(leg, 'rotation')] = G.qnorm(G.qmul(G.qinv(w_up), w_leg))
                f[(foot, 'rotation')] = G.qnorm(G.qmul(G.qinv(w_leg), w_foot))
            w = world(g, f)
            n0 = G.vcross(G.vsub(captured[leg][0], captured[up][0]), G.vsub(captured[foot][0], captured[up][0]))
            n1 = G.vcross(G.vsub(w[leg][0], w[up][0]), G.vsub(w[foot][0], w[up][0]))
            if G.vlen(n0) > 1e-9 and G.vlen(n1) > 1e-9:
                knee_plane_dev = max(knee_plane_dev, math.degrees(math.acos(max(-1.0, min(1.0, abs(G.vdot(G.vunit(n0), G.vunit(n1))))))))
            foot_world_dev = max(foot_world_dev, G.qangle_deg(w[foot][1], captured[foot][1]))
            ik_feet[side] += 1
            info[side] = {'ik': True, 'dy_cm': round((w[foot][0][1] - moved[foot][0][1]) * 100, 6)}
        out.append(f)
        per_frame.append(info)
    report = {
        'root_support_cm': {'required_max': round(max(required) * 100, 6), 'max': round(max(env) * 100, 6), 'min': round(min(env) * 100, 6),
                            'frames_nonzero': sum(1 for e in env if e), 'bound_cm': MAX_ROOT_SUPPORT_CM,
                            'vertical_only': True},
        'ik_frames_per_foot': ik_feet,
        'foot_target_dy_cm': {s: [round(min(p[s]['dy_cm'] for p in per_frame), 6), round(max(p[s]['dy_cm'] for p in per_frame), 6)]
                              for s in SIDES},
        'captured_lowest_plantar_cm': {s: [round(min(r[s]['low_cm'] for r in need), 6), round(max(r[s]['low_cm'] for r in need), 6)]
                                       for s in SIDES},
        'knee_plane_max_change_deg': round(knee_plane_dev, 6),
        'foot_world_orientation_max_change_deg': round(foot_world_dev, 6),
        'foot_orientation_adjusted_for_support': False,
    }
    return out, report


def write(g: G.Gltf, clip, times, frames, labels, extras, out_path):
    bw = G.BinWriter()
    ti = bw.add(list(times), 'SCALAR', minmax=True)
    anim = {'name': clip.name or 'Idle', 'samplers': [], 'channels': [], 'extras': {'sub01_labels': labels}}
    for (node, prop) in sorted(clip.tracks):
        vi = bw.add([f[(node, prop)] for f in frames], 'VEC4' if prop == 'rotation' else 'VEC3')
        anim['samplers'].append({'input': ti, 'output': vi, 'interpolation': 'LINEAR'})
        anim['channels'].append({'sampler': len(anim['samplers']) - 1, 'target': {'node': node, 'path': prop}})
    asset = {'version': '2.0', 'generator': 'SUB01 leg_ik_life_clip', 'extras': dict(extras, sub01_labels=labels)}
    doc = {'asset': asset, 'scene': 0, 'scenes': g.doc['scenes'], 'nodes': g.doc['nodes'], 'animations': [anim],
           'accessors': bw.accessors, 'bufferViews': bw.views,
           'buffers': [{'byteLength': len(bw.data) + (-len(bw.data)) % 4}]}
    return G.write_glb(out_path, doc, bytes(bw.data))


def upper_body_delta(g, owner, raw_frames, frames, mapping):
    """Max local-rotation delta of every joint but the legs, and world hand-orientation change."""
    legs = {g.by_name[P + s + x] for s in SIDES for x in LEG}
    joints = [g.by_name[P + n] for n in owner.names]
    worst, worst_in_blend, wrist, differing = 0.0, 0.0, 0.0, 0
    for j, f in enumerate(frames):
        src = mapping[j]
        if 'partner' in src:
            ref = raw_frames[src['main']]
            for n in joints:
                if n not in legs and (n, 'rotation') in f:
                    worst_in_blend = max(worst_in_blend, G.qangle_deg(f[(n, 'rotation')], ref[(n, 'rotation')]))
            continue
        ref = raw_frames[src['main']]
        for n in joints:
            if n not in legs and (n, 'rotation') in f:
                worst = max(worst, G.qangle_deg(f[(n, 'rotation')], ref[(n, 'rotation')]))
                differing += f[(n, 'rotation')] != ref[(n, 'rotation')]
        wa, wb = world(g, f), world(g, ref)
        for s in SIDES:
            h = g.by_name[P + s + 'Hand']
            wrist = max(wrist, G.qangle_deg(wa[h][1], wb[h][1]))
    return {'upper_body_values_differing_outside_blend': differing,
            'max_local_rotation_delta_deg_outside_blend': round(worst, 9),
            'note': 'values are copied bit for bit; a nonzero angle here is acos rounding of identical quaternions',
            'max_local_rotation_delta_deg_inside_blend': round(worst_in_blend, 6),
            'world_hand_orientation_max_change_deg_outside_blend': round(wrist, 9)}


def table(raw, fixed):
    def pick(r):
        inv = r['invariants']
        soles = inv.get('soles', {}).get('feet', {})
        return {
            'soles_lowest_left_cm': [soles.get('left', {}).get('lowest_vertex_min_cm'), soles.get('left', {}).get('lowest_vertex_max_cm')],
            'soles_lowest_right_cm': [soles.get('right', {}).get('lowest_vertex_min_cm'), soles.get('right', {}).get('lowest_vertex_max_cm')],
            'soles_penetration_cm': [soles.get(s, {}).get('penetration_below_floor_cm') for s in ('left', 'right')],
            'soles_slide_cm': [soles.get(s, {}).get('centroid_horizontal_slide_cm') for s in ('left', 'right')],
            'foot_joint_max_slide_cm': max((j or {}).get('horizontal_slide_cm') or 0 for j in inv['feet_joints']['joints'].values()),
            'loop_pose_cm': inv['loop'].get('start_end_hips_relative_pose_cm'),
            'seam_velocity_cm_s': inv['loop'].get('start_end_velocity_delta_cm_s'),
            'hips_travel_cm': inv['root_in_place'].get('hips_max_horizontal_travel_cm'),
            'hips_vertical_range_cm': inv['root_in_place'].get('hips_vertical_range_cm'),
            'bone_length_max_dev_from_owner_cm': inv['bone_length_constancy'].get('max_dev_from_owner_lengths_cm'),
            'duration_s': inv['timing'].get('duration_s'),
            'failed': r['failed'],
        }
    a, b = pick(raw), pick(fixed)
    return {k: {'raw': a[k], 'corrected': b[k]} for k in a}


def run(src: Path, out: Path, owner_path: Path = V.OWNER, blend='auto', work=None, raw_report=None):
    work = Path(work or out.parent / (out.stem + '.work'))
    work.mkdir(parents=True, exist_ok=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    g = G.Gltf(src)
    owner = V.Owner(G.Gltf(owner_path))
    soles = Soles(G.Gltf(V.decoded(owner_path, work)), g)
    clip, times, raw_frames = read_clip(g)
    labels = ['retargeted']
    raw_seam = seam_metrics(g, owner, times, raw_frames)
    fps = (len(times) - 1) / (times[-1] - times[0])
    frames, new_times, mapping, blend_info = raw_frames, [t - times[0] for t in times], [{'main': i} for i in range(len(times))], None
    if blend != 'none' and (blend != 'auto' or not raw_seam['passes']):
        seconds = DEFAULT_BLEND_S if blend == 'auto' else float(blend)
        n = int(round(seconds * fps))
        new_times, frames, mapping = seam_blend(times, raw_frames, n)
        labels.append('seam_blend')
        blend_info = {'frames': n, 'seconds': round(n / fps, 6), 'weights': 'smootherstep', 'clip_shortened_by_frames': n,
                      'blended_frames': sum(1 for m in mapping if 'partner' in m),
                      'raw_seam': raw_seam, 'blended_seam': seam_metrics(g, owner, new_times, frames)}
    corrected, ik = correct(g, owner, soles, new_times, frames)
    if ik['ik_frames_per_foot']['Left'] or ik['ik_frames_per_foot']['Right']:
        labels.append('leg_ik_support')
    if ik['root_support_cm']['frames_nonzero']:
        labels.append('root_support')
    support = {}
    for side in SIDES:
        lows, bands = [], []
        for f in corrected:
            low, band = soles.support(soles.heights(world(g, f))[side])
            lows.append(low)
            bands.append(band)
        support[side] = {'lowest_cm': [round(min(lows), 6), round(max(lows), 6)], 'min_band_vertices': min(bands),
                         'pass': min(lows) >= 0 and max(lows) <= SOLE_BAND_CM[1] and min(bands) >= MIN_SUPPORT_VERTICES}
    extras = {'source_clip': src.name, 'source_sha256': g.sha256, 'tool': 'tools/leg_ik_life_clip.py',
              'derived_from': 'see OUTPUT.report.json (retarget provenance)'}
    sha = write(g, clip, new_times, corrected, labels, extras, out)
    final_seam = seam_metrics(G.Gltf(out), owner, new_times, corrected)
    fixed = V.verify(out, owner_path, workdir=work)
    raw = json.loads(Path(raw_report).read_text())['verification'] if raw_report else V.verify(src, owner_path, workdir=work)
    report = {
        'schema': SCHEMA, 'input': str(src), 'input_sha256': g.sha256, 'output': str(out), 'output_sha256': sha,
        'labels': labels, 'fps': round(fps, 6), 'frames_in': len(times), 'frames_out': len(new_times),
        'seam': {'raw': raw_seam, 'final': final_seam, 'blend': blend_info},
        'leg_ik': ik,
        'support_patch': {'rule': f'lowest plantar vertex in {SOLE_BAND_CM} cm and >= {MIN_SUPPORT_VERTICES} plantar '
                                  'vertices in that band, every frame (validate_unreal_seat_contact.py constants)',
                          'feet': support, 'pass': all(v['pass'] for v in support.values())},
        'upper_body': upper_body_delta(g, owner, raw_frames, corrected, mapping),
        'raw_vs_corrected': table(raw, fixed),
        'verification': fixed,
        'never': 'no horizontal root move, no stretch, no finger or upper-body posing, no keys outside the seam blend window',
    }
    Path(str(out) + '.report.json').write_text(json.dumps(report, indent=1, sort_keys=True) + '\n')
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('source', type=Path)
    ap.add_argument('output', type=Path)
    ap.add_argument('--owner', type=Path, default=V.OWNER)
    ap.add_argument('--blend', default='auto')
    ap.add_argument('--work', type=Path)
    ap.add_argument('--raw-report', type=Path)
    args = ap.parse_args(argv)
    r = run(args.source, args.output, args.owner, args.blend, args.work, args.raw_report)
    ok = r['verification']['pass'] and r['support_patch']['pass']
    print(json.dumps({'output': r['output'], 'labels': r['labels'], 'verifier_pass': r['verification']['pass'],
                      'failed': r['verification']['failed'], 'support_patch_pass': r['support_patch']['pass']}))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
