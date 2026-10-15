"""Independent full-mesh audit of a (derived) phone-grip clip. Source audit only; native gates stay false.

Skinning path: tools/phone_grip_hand_export.mjs (three.js, every vertex of every owner primitive), NOT the
numpy solver path, so the derivation is checked by a second implementation. Every sampled frame (30 fps) gets:
* actual skin-triangle / part separating-axis overlaps for case, glass (screen), speaker and keys, split into
  fingers+palm, thumb, forearm and body (body = every other owner vertex within the export reach);
* vertex signed depth per group, with the allowed soft-tissue compression reported separately;
* gravity support (hull or friction pinch) from fingers+palm+thumb contacts;
* eye-ray visibility of a 5x9 glass grid against actual triangles, screen-to-eye and upright angles;
* thumb-to-glass contact events from geometry (no timer);
* left-hand (free hand) clearance to the phone.

    python tools/audit_phone_grip_clip.py --clip docs/proposed/phone-grip-derived/SUB01_PhoneGrip_derived.glb \
        --report docs/proposed/phone-grip-derived/SUB01_PhoneGrip_derived.report.json --out <audit.json>
"""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fit_phone_grip as FG  # noqa: E402

ROOT = FG.ROOT
COMPRESSION_CM = 0.15
GROUPS = ('fingers_palm', 'thumb', 'forearm', 'body')


def groups(hand):
    names = np.array(hand.joints)[hand.labels]
    thumb = np.char.startswith(names.astype(str), 'mixamorigRightHandThumb')
    right = np.char.startswith(names.astype(str), 'mixamorigRightHand')
    forearm = names == 'mixamorigRightForeArm'
    left = np.char.startswith(names.astype(str), 'mixamorigLeftHand')
    g = np.full(len(names), 3, np.int8)            # body
    g[forearm] = 2
    g[right & ~thumb] = 0
    g[thumb] = 1
    return g, left, names


def audit(hand, R, t, phone=None, compression=COMPRESSION_CM, band=0.3, frames=None):
    ev = FG.Evaluator(hand, phone or FG.default_phone(), FG.MIRROR@np.array(FG.UE_EYE_HEAD_LOCAL), 4.0)
    g, left, names = groups(hand)
    tri = hand.triangles
    tri_group = g[tri].max(1)                      # a triangle touching body counts as body
    thumb_pad = names == 'mixamorigRightHandThumb3'
    _, sc, sh = ev.screen
    gx, gy = np.meshgrid(np.linspace(-1, 1, 5)*sh[0]*.95, np.linspace(-1, 1, 9)*sh[1]*.95)
    samples = np.stack([gx.ravel(), gy.ravel(), np.full(gx.size, sc[2]+1e-3)], 1)
    rows = []
    for f in (range(len(hand.times)) if frames is None else frames):
        P = np.asarray(hand.positions[f], float)
        idx = ev.near(f, t, extra=2.0)
        L = (P[idx]-t)@R
        s = ev.sdf(L)
        gi = g[idx]
        row = {'time': round(float(hand.times[f]), 4)}
        mask = np.zeros(len(P), bool)
        mask[idx] = True
        tsel = tri[mask[tri].all(1)]
        tg = tri_group[mask[tri].all(1)]
        Lall = np.zeros_like(P)
        Lall[idx] = L
        for k, name in enumerate(GROUPS):
            sk = s[gi == k]
            row[name] = {'max_depth_cm': round(float(max(0.0, -sk.min())) if len(sk) else 0.0, 4),
                         'vertices_beyond_compression': int(np.sum(sk < -compression)),
                         'contact_vertices': int(np.sum((sk >= -compression) & (sk <= band)))}
            tk = tsel[tg == k]
            row[name]['triangle_overlaps'] = {}
            for pname, c, h in ev.parts:
                # Triangles whose skin only presses within the compression band are contact, not crossing.
                hh = np.maximum(h-compression, 0) if pname == 'case' else h
                a, b, cc = (Lall[tk[:, j]]-c for j in range(3))
                row[name]['triangle_overlaps'][pname] = int(FG.tri_box_overlap(a, b, cc, hh).sum()) if len(tk) else 0
        hold = (gi <= 1) & (s >= -compression) & (s <= band)
        row['gravity_support'] = ev.support(L[hold], ev.case[1], ev.case[2], ev.gravity[f]@R)
        e = (ev.eyes[f]-t)@R-sc
        row['screen_to_eye_angle_deg'] = round(math.degrees(math.acos(np.clip(e[2]/np.linalg.norm(e), -1, 1))), 2)
        row['screen_upright_deg'] = round(math.degrees(math.acos(np.clip(ev.upright(f, R), -1, 1))), 2)
        row['eye_distance_cm'] = round(float(np.linalg.norm(e)), 2)
        world = samples@R.T+t
        eye = ev.eyes[f]
        lo, hi = np.minimum(world.min(0), eye)-0.5, np.maximum(world.max(0), eye)+0.5
        tmin = np.minimum(np.minimum(P[tri[:, 0]], P[tri[:, 1]]), P[tri[:, 2]])
        tmax = np.maximum(np.maximum(P[tri[:, 0]], P[tri[:, 1]]), P[tri[:, 2]])
        near = tri[np.all((tmax >= lo) & (tmin <= hi), 1)]
        blocked = FG.ray_hits(world, eye, P[near[:, 0]], P[near[:, 1]], P[near[:, 2]]) if len(near) else np.zeros(len(world), bool)
        row['screen_visible_fraction'] = round(1-float(blocked.mean()), 4)
        pad = (P[thumb_pad]-t)@R
        ps = ev.sdf(pad)
        tip = pad[np.argmin(ps)]
        u, v = (tip[0]-sc[0])/(2*sh[0])+.5, (tip[1]-sc[1])/(2*sh[1])+.5
        row['thumb_glass'] = {'uv': [round(u, 4), round(v, 4)], 'clearance_cm': round(float(ps.min()), 4),
                        'near_glass': bool(0 <= u <= 1 and 0 <= v <= 1 and ps.min() <= 0.1),
                               'touch_glass': bool(0 <= u <= 1 and 0 <= v <= 1 and ps.min() <= 0.02)}
        lp = P[left]
        row['left_hand_min_clearance_cm'] = round(float(ev.sdf((lp-t)@R).min()), 3) if len(lp) else None
        rows.append(row)
    return rows


def summarize(rows, hold=(2.0, 16.0)):
    def agg(sel):
        out = {'frames': len(sel)}
        for name in GROUPS:
            out[name] = {'max_depth_cm': max(r[name]['max_depth_cm'] for r in sel),
                         'frames_beyond_compression': sum(r[name]['vertices_beyond_compression'] > 0 for r in sel),
                         'triangle_overlaps_total': {p: sum(r[name]['triangle_overlaps'][p] for r in sel) for p in sel[0][name]['triangle_overlaps']},
                         'frames_with_triangle_overlap': sum(any(r[name]['triangle_overlaps'].values()) for r in sel)}
        out['frames_supported'] = sum(r['gravity_support']['supported'] for r in sel)
        out['screen_to_eye_angle_deg'] = [min(r['screen_to_eye_angle_deg'] for r in sel), max(r['screen_to_eye_angle_deg'] for r in sel)]
        out['screen_upright_deg'] = [min(r['screen_upright_deg'] for r in sel), max(r['screen_upright_deg'] for r in sel)]
        vis = [r['screen_visible_fraction'] for r in sel]
        out['screen_visible_fraction_min_mean'] = [min(vis), round(float(np.mean(vis)), 4)]
        lh = [r['left_hand_min_clearance_cm'] for r in sel if r['left_hand_min_clearance_cm'] is not None]
        out['left_hand_min_clearance_cm'] = min(lh) if lh else 'beyond export reach'
        return out
    touches = [r['thumb_glass']['touch_glass'] for r in rows]
    events, start = [], None
    for i, on in enumerate(touches+[False]):
        if on and start is None:
            start = i
        elif not on and start is not None:
            seg = rows[start:i]
            events.append({'down_time': seg[0]['time'], 'up_time': seg[-1]['time'], 'frames': len(seg),
                           'uv': [round(float(np.mean([s['thumb_glass']['uv'][k] for s in seg])), 4) for k in (0, 1)]})
            start = None
    in_hold = [r for r in rows if hold[0] <= r['time'] <= hold[1]]
    return {'all_frames': agg(rows), 'hold_window': {'seconds': list(hold), **agg(in_hold)},
            'thumb_glass_events': events}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--clip', type=Path, required=True)
    ap.add_argument('--report', type=Path, required=True, help='Derivation report with phone_mount')
    ap.add_argument('--owner', type=Path, default=ROOT/'web/room/char_mixamo.glb')
    ap.add_argument('--cache', type=Path, default=ROOT/'out/phone-grip')
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args(argv)
    owner_sha, clip_sha = FG.sha256(args.owner), FG.sha256(args.clip)
    stem = args.cache/f'hand-{owner_sha[:12]}-{clip_sha[:12]}-r30'
    if not stem.with_suffix('.json').exists():
        FG.export_hand(args.owner, args.clip, stem, 30, 4.0)
    hand = FG.HandExport(stem)
    if hand.meta['clip']['sha256'] != clip_sha or hand.meta['owner']['sha256'] != owner_sha:
        raise ValueError('Export cache does not match the exact clip/owner bytes')
    rep = json.loads(args.report.read_text())
    mount = rep['phone_mount']['gltf_right_hand_local']
    R, t = FG.quat_to_matrix(mount['quaternion_xyzw']), np.array(mount['offset_cm'], float)
    rows = audit(hand, R, t)
    out = {'schema': 'sub01.phone-grip-clip-audit.v1', 'verified': False, 'source_audit_only': True,
           'native_gates': {'native_import': False, 'native_contact': False, 'visual_acceptance': False, 'activity_binding': False},
           'skinning': 'three.js r180 via tools/phone_grip_hand_export.mjs (independent of the numpy derivation path)',
           'clip': {'path': str(args.clip), 'sha256': clip_sha, 'label': rep.get('label')},
           'owner': {'path': str(args.owner), 'sha256': owner_sha, 'vertices_skinned': hand.meta['owner']['vertices']},
           'report_sha256': FG.sha256(args.report), 'mount': mount, 'compression_cm': COMPRESSION_CM,
           'summary': summarize(rows), 'frames': rows}
    args.out.write_text(json.dumps(out, separators=(',', ':'))+'\n')
    print(json.dumps(out['summary'], indent=1)[:4000])


if __name__ == '__main__':
    main()
