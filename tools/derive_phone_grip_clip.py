"""DERIVED phone-grip clip from the actual Texting capture (label ``derived_from_capture``). verified: false.

This is NOT the original capture and never reports capture invariance. The original
docs/proposed/phone-capture/texting.glb stays the unchanged baseline; this writes a separate derived clip.

What is derived (rotations only, so every bone length is exactly the source length):
* Right Index/Middle/Ring/Pinky: one constant anatomical cradle for the exact 7.5 x 15 x 1.5 cm phone, set as
  rest-local * flex(local +X) [* abduction(local +Z) on joint 1] with natural limits (MCP -5..85, PIP 0..105,
  DIP 0..75 deg, abduction +-15 deg). Rest is the owner's straight-finger T-pose, so 0 = straight, and limits
  exclude hyperextension ("knuckle inversion"). Twist is not invented.
* RightHand local: captured * one constant bounded correction (<= 25 deg) so the screen faces the actual eye.
* RightHandThumb1 (CMC): captured * one constant bounded offset (<= 45 deg) and, per frame, the smallest lift
  (<= 35 deg) that stops the actual thumb skin at the glass/case. RightHandThumb2 (MCP): captured * one constant
  bounded offset (<= 30 deg). The captured thumb texting motion (Thumb2/Thumb3 variation) is kept; frames where the
  stop holds the pad on the glass are tap events (time, screen uv); no timer.
* Phone: one rigid mount of the original five-part assembly in the derived RightHand frame.
Left arm/hand, spine, head and every other joint keep the captured values exactly.

Run:  python tools/derive_phone_grip_clip.py --out-dir docs/proposed/phone-grip-derived
The full-mesh audit is separate (tools/audit_phone_grip_clip.py) and uses the three.js skinning path.
"""
import argparse
import hashlib
import json
import math
import multiprocessing
import struct
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fit_phone_grip as FG  # noqa: E402
from phone_rig import ROOT, Rig, Skin, q_angle_deg, q_axis_angle, q_mul, q_to_m, qnorm, read_glb  # noqa: E402

LABEL = 'derived_from_capture'
SCHEMA = 'sub01.phone-grip-derived.v1'
CLIP = ROOT/'docs/proposed/phone-capture/texting.glb'
OWNER = ROOT/'web/room/char_mixamo.glb'
FINGERS = ('Index', 'Middle', 'Ring', 'Pinky')
FLEX_LIMITS = {1: (-5.0, 85.0), 2: (0.0, 105.0), 3: (0.0, 75.0)}
ABD_LIMIT, HAND_CORR_MAX, THUMB1_MAX, THUMB2_MAX, THUMB_STOP_MAX = 15.0, 25.0, 45.0, 30.0, 35.0
COMPRESSION_CM, BAND_CM, CLEAR_CM, TOUCH_CM, GLASS_TOUCH_CM = 0.15, 0.3, 0.2, 0.1, 0.02
PALM_CONTACT_MIN, PROXIMAL_CONTACT_MIN = 60, 40
PALM_WEIGHT = 3.0
RIM_CLEAR_CM, PAD_U, PAD_V = 0.1, (0.25, 0.75), (0.2, 0.7)     # texting thumb: pad over the glass interior, side off the rim
HOVER_MEDIAN_CM, DIP_QUANTILE, DIP_DEPTH_CM = 0.4, 0.2, -0.15   # thumb rests above glass; captured dips reach it
NP = 31                    # mount 6, hand correction 3, fingers 4x4, thumb1 (CMC) 3, thumb2 (MCP) 3


def rotvec_q(v):
    v = np.asarray(v, float)
    a = np.linalg.norm(v)
    return np.array([0, 0, 0, 1.0]) if a < 1e-12 else q_axis_angle(v/a, a)


def ensure_skin(cache):
    stem = Path(cache)/'owner-skin'
    if not stem.with_suffix('.json').exists():
        Path(cache).mkdir(parents=True, exist_ok=True)
        subprocess.run(['node', str(ROOT/'tools/phone_grip_owner_skin.mjs'), '--owner', str(OWNER), '--out', str(stem)], check=True, cwd=ROOT)
    return stem


class Derivation:
    def __init__(self, rig, skin, phone=None, pose_time=4.0, view_frames=None, active_frames=()):
        self.rig, self.skin = rig, skin
        self.phone = phone or FG.default_phone()
        self.parts = [(p['name'], np.array(p['center'], float), np.array(p['half_extent'], float)) for p in self.phone['parts']]
        self.case = next(p for p in self.parts if p[0] == 'case')
        self.reach = max(np.linalg.norm(np.abs(c)+h) for _, c, h in self.parts)
        self.screen = next(p for p in self.parts if p[0] == 'screen')
        self.f0 = int(np.argmin(np.abs(rig.times-pose_time)))
        self.hand = rig.index('RightHand')
        sub, inside = [], {self.hand}
        for i in rig.order:
            if i == self.hand or rig.parent.get(i) in inside:
                inside.add(i)
                sub.append(i)
        self.sub = sub
        self.rest = np.array([n['rotation'] for n in rig.nodes], float)
        self.Wcap = rig.worlds()
        names = np.array(skin.joint_names)
        right = np.array(['RightHand' in n for n in names])
        self.moving = np.nonzero((right[skin.joint]*(skin.weight > 0)).any(1))[0]
        dom = names[skin.dominant[self.moving]]
        self.dom = dom
        self.thumb_tip = np.isin(dom, ['mixamorigRightHandThumb2', 'mixamorigRightHandThumb3'])
        self.thumb_pad = dom == 'mixamorigRightHandThumb3'
        self.palm = dom == 'mixamorigRightHand'
        self.proximal = np.isin(dom, [f'mixamorigRightHand{f}1' for f in FINGERS])
        self.pads = {f: np.isin(dom, [f'mixamorigRightHand{f}2', f'mixamorigRightHand{f}3']) for f in FINGERS}
        self.static = np.setdiff1d(np.arange(len(skin.bind)), self.moving)
        head = rig.index('Head')
        eye_local = FG.MIRROR@np.array(FG.UE_EYE_HEAD_LOCAL)
        Rhd = self.Wcap[:, head, :3, :3]/np.linalg.norm(self.Wcap[:, head, :3, 0], axis=-1)[:, None, None]
        self.eye = self.Wcap[:, head, :3, 3]*100+np.einsum('fij,j->fi', Rhd, eye_local)
        self.head_up = Rhd[:, :, 1]
        self.view_frames = sorted(set(view_frames if view_frames is not None else [self.f0]+[int(np.argmin(np.abs(rig.times-t))) for t in (2.5, 7, 10, 13, 15.5)]))
        self.body = {f: self.near_static(f) for f in self.view_frames}
        self.thumb_frames = sorted(set([int(np.argmin(np.abs(rig.times-t))) for t in np.arange(2.0, 16.01, 0.7)]) | {int(f) for f in active_frames})
        self.active_frames = sorted(int(f) for f in active_frames)

    # ---------------------------------------------------------------- kinematics
    def near_static(self, f, radius=25.0):
        P = self.skin.deform(self.Wcap[f], self.static)
        w = self.Wcap[f, self.hand, :3, 3]*100
        return P[np.sum((P-w)**2, 1) < radius**2]

    def edit(self, f, p, thumb_stop=0.0, thumb_axis=None):
        """Derived local rotations for frame f (all nodes). Anatomical limits are hard clamps."""
        p = clamp_params(p)
        q = self.rig.q[f].copy()
        q[self.hand] = q_mul(q[self.hand], rotvec_q(p[6:9]))
        for k, finger in enumerate(FINGERS):
            th = p[9+4*k:12+4*k]
            phi = p[12+4*k]
            for j in (1, 2, 3):
                i = self.rig.index(f'RightHand{finger}{j}')
                local = q_mul(self.rest[i], q_axis_angle([1, 0, 0], math.radians(th[j-1])))
                if j == 1:
                    local = q_mul(local, q_axis_angle([0, 0, 1], math.radians(phi)))
                q[i] = local
        t1, t2 = self.rig.index('RightHandThumb1'), self.rig.index('RightHandThumb2')
        q[t1] = q_mul(q[t1], rotvec_q(p[25:28]))
        q[t2] = q_mul(q[t2], rotvec_q(p[28:31]))
        if thumb_stop and thumb_axis is not None:
            j = self.rig.index(thumb_axis[0])
            q[j] = q_mul(q[j], q_axis_angle(thumb_axis[1], math.radians(thumb_stop)))
        return qnorm(q)

    def worlds(self, f, q):
        W = self.Wcap[f].copy()
        L = np.zeros((4, 4))
        for i in self.sub:
            L[:3, :3] = q_to_m(q[i])*self.rig.s[f, i][None, :]
            L[:3, 3] = self.rig.t[f, i]
            L[3] = [0, 0, 0, 1]
            W[i] = W[self.rig.parent[i]]@L
        return W

    def hand_frame(self, W):
        R = W[self.hand, :3, :3]
        return R/np.linalg.norm(R[:, 0]), W[self.hand, :3, 3]*100

    def phone_pose(self, W, p):
        Rh, ph = self.hand_frame(W)
        Rm = FG.rotvec_to_matrix(p[:3])
        return Rh@Rm, ph+Rh@p[3:6]          # phone -> world rotation, centre (cm)

    def to_phone(self, P, Rp, cp):
        return (P-cp)@Rp

    def sdf(self, L):
        return np.min([FG.box_sdf(L, c, h) for _, c, h in self.parts], axis=0)

    # ---------------------------------------------------------------- objective
    def cost(self, p):
        c = 0.0
        th = p[9:25].reshape(4, 4)
        for j, (lo, hi) in FLEX_LIMITS.items():
            c += 0.2*float(np.sum(np.maximum(lo-th[:, j-1], 0)**2+np.maximum(th[:, j-1]-hi, 0)**2))
        c += 0.2*float(np.sum(np.maximum(np.abs(th[:, 3])-ABD_LIMIT, 0)**2))
        for v, lim in ((p[6:9], HAND_CORR_MAX), (p[25:28], THUMB1_MAX), (p[28:31], THUMB2_MAX)):
            a = math.degrees(np.linalg.norm(v))
            c += 0.2*max(0.0, a-lim)**2+0.002*a**2
        # Natural cascade: DIP follows PIP, neighbouring fingers curl alike.
        c += 0.002*float(np.sum((th[:, 2]-0.7*th[:, 1])**2))+0.001*float(np.sum(np.diff(th[:, :3], axis=0)**2))
        f = self.f0
        q = self.edit(f, p)
        W = self.worlds(f, q)
        Rp, cp = self.phone_pose(W, p)
        P = self.skin.deform(W, self.moving)
        L = self.to_phone(P, Rp, cp)
        s = self.sdf(L)
        hold = ~self.thumb_tip
        keys = np.min([FG.box_sdf(L, c_, h_) for n_, c_, h_ in self.parts if n_ in ('volume', 'power', 'speaker')], axis=0)
        c += 200*float(np.sum(np.maximum(-keys[hold], 0)**2))      # resting skin must not press a key
        pen = np.maximum(-s[hold]-COMPRESSION_CM, 0)
        c += 200*float(np.sum(pen**2))+0.5*float(np.sum(pen > 0))
        for finger in FINGERS:
            m = self.pads[finger]
            c += 2*float(min(s[m].min(), 3.0))**2
        contact = hold & (s <= BAND_CM)
        # Cradle: the palm itself must carry the phone (not only fingertips), plus proximal phalanges.
        palm_n = float(np.sum(self.palm & contact))
        prox_n = float(np.sum(self.proximal & contact))
        c += PALM_WEIGHT*max(0.0, 1-palm_n/PALM_CONTACT_MIN)+PALM_WEIGHT/2*max(0.0, 1-prox_n/PROXIMAL_CONTACT_MIN)
        sup = FG.Evaluator.support(L[contact], self.case[1], self.case[2], np.array([0, -1.0, 0])@Rp)
        c += 0 if sup['supported'] else 4
        c += 0 if sup.get('com_inside_support_hull') else 1
        # Thumb: the pad may press into the glass only as deep as the bounded per-frame stop can lift it,
        # and the proximal thumb segment never enters the case (the stop cannot fix it).
        thumb_seg = self.thumb_tip & ~self.thumb_pad
        c += 200*float(np.sum(np.maximum(-s[thumb_seg], 0)**2))
        c += 50*float(np.sum(np.maximum(-s[self.thumb_pad]-0.4, 0)**2))
        pad = L[self.thumb_pad]
        tip = pad[np.argmin(pad[:, 2])]
        u = (tip[0]-self.screen[1][0])/(2*self.screen[2][0])+.5
        v = (tip[1]-self.screen[1][1])/(2*self.screen[2][1])+.5
        c += 20*(max(0, PAD_U[0]-u)**2+max(0, u-PAD_U[1])**2+max(0, PAD_V[0]-v)**2+max(0, v-PAD_V[1])**2)
        h = tip[2]-self.screen[1][2]
        c += 2*(max(0.0, h-1.0)**2+max(0.0, -0.8-h)**2)
        # Captured thumb motion before the stop: hover above the glass, dip through it only at its minima.
        h = []
        for ft in self.thumb_frames:
            qt = self.edit(ft, p)
            Wt = self.worlds(ft, qt)
            Rt, ct = self.phone_pose(Wt, p)
            Lm = self.to_phone(self.skin.deform(Wt, self.moving), Rt, ct)
            sa = self.sdf(Lm)
            h.append(float(FG.box_sdf(Lm[self.thumb_pad], self.screen[1], self.screen[2]).min()))   # pad to glass
            n = len(self.thumb_frames)
            # Every sampled hold frame: palm/thenar/finger skin within the compression band, the proximal thumb
            # segment (which a tap lift cannot move) clear, and the pad dipping only as far as an MCP lift returns it.
            c += 200*float(np.sum(np.maximum(-sa[~self.thumb_tip]-COMPRESSION_CM, 0)**2))/n
            c += 200*float(np.sum(np.maximum(RIM_CLEAR_CM-sa[self.thumb_tip & ~self.thumb_pad], 0)**2))/n   # thumb side off the rim
            c += 50*float(np.sum(np.maximum(-sa[self.thumb_pad]-0.4, 0)**2))/n
        h = np.array(h)
        c += 4*(np.median(h)-HOVER_MEDIAN_CM)**2+4*(np.quantile(h, DIP_QUANTILE)-DIP_DEPTH_CM)**2
        for fv in self.view_frames:
            if fv != f:
                q = self.edit(fv, p)
                W = self.worlds(fv, q)
                Rp, cp = self.phone_pose(W, p)
            Lb = self.to_phone(self.body[fv], Rp, cp)
            Lb = Lb[np.sum(Lb**2, 1) < (self.reach+CLEAR_CM)**2]
            if len(Lb):
                sb = self.sdf(Lb)
                c += 2*float(np.sum(np.maximum(CLEAR_CM-sb, 0)**2))/len(self.view_frames)
            e = self.to_phone(self.eye[fv], Rp, cp)-self.screen[1]
            ang = math.degrees(math.acos(np.clip(e[2]/np.linalg.norm(e), -1, 1)))
            n = Rp[:, 2]
            up = self.head_up[fv]-(self.head_up[fv]@n)*n
            upright = math.degrees(math.acos(np.clip(Rp[:, 1]@up/max(np.linalg.norm(up), 1e-9), -1, 1)))
            c += (0.02*max(0.0, ang-30)**2+0.02*max(0.0, upright-25)**2)/len(self.view_frames)
        return c

    # ---------------------------------------------------------------- per-frame thumb stop
    def thumb_stop(self, f, p, previous=0.0):
        """Smallest thumb lift (deg) that keeps the actual thumb skin on/above the glass and case.

        Tries the MCP (Thumb2, the joint of a thumb tap) first, then the CMC (Thumb1). A lift is accepted only
        if no other right-hand skin (thenar, palm, fingers) goes deeper than the compression band, and never
        deeper than it already was. Returns (deg, (joint, local axis), thumb clearance, thumb phone-local pts)."""
        q = self.edit(f, p)
        W = self.worlds(f, q)
        Rp, cp = self.phone_pose(W, p)
        tip_idx = self.moving[self.thumb_tip]
        rest_mask = ~self.thumb_tip
        pad = self.skin.deform(W, self.moving[self.thumb_pad]).mean(0)

        def measure(stop):
            WW = self.worlds(f, self.edit(f, p, stop[0], stop[1]))
            L = self.to_phone(self.skin.deform(WW, self.moving), Rp, cp)
            s = self.sdf(L)
            return float(s[self.thumb_tip].min()), float(s[rest_mask].min()), L[self.thumb_tip]
        tip0, other0, L0 = measure((0.0, None))
        if tip0 >= 0:
            return 0.0, None, tip0, L0
        floor = min(other0, -COMPRESSION_CM)
        best = None
        for name in ('RightHandThumb2', 'RightHandThumb1'):
            j = self.rig.index(name)
            Rj = W[j, :3, :3]/np.linalg.norm(W[j, :3, 0])
            axis_world = np.cross(pad-W[j, :3, 3]*100, Rp[:, 2])
            axis = (name, Rj.T@(axis_world/np.linalg.norm(axis_world)))
            tip, other, L = measure((THUMB_STOP_MAX, axis))
            if tip < 0 or other < floor:
                score = min(tip, other-floor)
                if best is None or score > best[0]:
                    best = (score, THUMB_STOP_MAX, axis, tip, L)
                continue
            lo, hi, found = 0.0, THUMB_STOP_MAX, (tip, L)
            for _ in range(18):
                mid = (lo+hi)/2
                tm, om, Lm = measure((mid, axis))
                if tm < 0 or om < floor:
                    lo = mid
                else:
                    hi, found = mid, (tm, Lm)
            return hi, axis, found[0], found[1]
        _, deg, axis, tip, L = best
        return deg, axis, tip, L


def clamp_params(p):
    p = np.array(p, float)
    th = p[9:25].reshape(4, 4)
    for j, (lo, hi) in FLEX_LIMITS.items():
        th[:, j-1] = np.clip(th[:, j-1], lo, hi)
    th[:, 3] = np.clip(th[:, 3], -ABD_LIMIT, ABD_LIMIT)
    p[9:25] = th.ravel()
    for sl, lim in ((slice(6, 9), HAND_CORR_MAX), (slice(25, 28), THUMB1_MAX), (slice(28, 31), THUMB2_MAX)):
        a = math.degrees(np.linalg.norm(p[sl]))
        if a > lim:
            p[sl] *= lim/a
    return p


def audit_violations(audit, compression=COMPRESSION_CM):
    """Per-frame severity from an independent audit: hand/thenar/body depth beyond compression, key or glass
    crossings by resting skin. Returns [(severity, frame_index)] sorted worst first."""
    out = []
    for i, r in enumerate(audit['frames']):
        sev = 0.0
        for g in ('fingers_palm', 'thumb', 'body', 'forearm'):
            sev += max(0.0, r[g]['max_depth_cm']-(compression if g != 'body' else 0.0))
            ov = r[g]['triangle_overlaps']
            sev += 0.01*(ov.get('volume', 0)+ov.get('power', 0)+ov.get('speaker', 0)+(ov.get('screen', 0) if g != 'thumb' else 0))
        if sev > 0:
            out.append((sev, i))
    return sorted(out, reverse=True)


def update_active_set(path, audit_path=None, k=8, min_gap=3):
    """Constraint generation: persisted extrema set, extended with the audit's worst separated frames."""
    path = Path(path)
    doc = json.loads(path.read_text()) if path.exists() else {'frames': [], 'history': []}
    if audit_path:
        audit = json.loads(Path(audit_path).read_text())
        added = []
        for sev, f in audit_violations(audit):
            if len(added) >= k:
                break
            if all(abs(f-g) >= min_gap for g in doc['frames']+added):
                added.append(f)
        doc['frames'] = sorted(set(doc['frames']) | set(added))
        doc['history'].append({'audit_clip_sha256': audit['clip']['sha256'], 'added': added})
        path.write_text(json.dumps(doc, indent=1)+'\n')
    return doc['frames']


def seed_params():
    """Classic one-hand hold: back on palm/fingers, fingers across the back round the far edge, thumb over glass."""
    R = np.array([[0, 1.0, 0], [-1.0, 0, 0], [0, 0, 1.0]])        # phone x = -hand Y, y = hand X, z = hand Z
    out = []
    for yaw in (-25, 0, 25):
        Rz = FG.rotvec_to_matrix([0, 0, math.radians(yaw)])
        for t in ((1.5, 6.0, 3.4), (3.0, 7.0, 3.4), (0.0, 5.5, 3.6)):
            p = np.zeros(NP)
            p[:3] = FG.matrix_to_rotvec(R@Rz)
            p[3:6] = t
            for k in range(4):
                p[9+4*k:13+4*k] = (40, 55, 35, 0)
            # Thumb out of opposition toward the glass: CMC offsets about each local axis.
            for axis in ((0, 0, 0), (1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1)):
                pp = p.copy()
                pp[25:28] = np.array(axis, float)*math.radians(30)
                out.append(pp)
    return out


SIGMA = np.array([.15]*3+[1.0]*3+[.08]*3+[8, 8, 6, 4]*4+[.12]*3+[.1]*3)
_D = None


def _cem(job):
    k, x0, iterations, population, scale = job
    rng = np.random.default_rng(k)
    mean, std = np.array(x0, float), SIGMA*scale
    best, best_cost = mean.copy(), _D.cost(mean)
    for _ in range(iterations):
        pop = mean+rng.standard_normal((population, NP))*std
        costs = np.array([_D.cost(x) for x in pop])
        order = np.argsort(costs)
        if costs[order[0]] < best_cost:
            best, best_cost = pop[order[0]].copy(), float(costs[order[0]])
        el = pop[order[:max(4, population//6)]]
        mean = 0.7*el.mean(0)+0.3*best
        std = np.maximum(el.std(0), SIGMA*0.02)
    return best, best_cost


def solve(d, workers=4, iterations=60, population=64, log=print, start=None):
    global _D
    _D = d
    if start is not None:
        start = np.concatenate([np.array(start, float), np.zeros(NP)])[:NP]
    seeds = sorted(seed_params()+([start] if start is not None else []), key=d.cost)[:max(workers, 4)]
    jobs = [(k, x, iterations, population, 1.0) for k, x in enumerate(seeds)]
    with multiprocessing.get_context('fork').Pool(workers) as pool:
        res = pool.map(_cem, jobs)
    res.sort(key=lambda r: r[1])
    log(f'stage1 costs {[round(c, 3) for _, c in res]}')
    jobs = [(100+k, x, iterations, population, 0.3) for k, (x, _) in enumerate(res[:workers])]
    with multiprocessing.get_context('fork').Pool(workers) as pool:
        res = pool.map(_cem, jobs)
    res.sort(key=lambda r: r[1])
    log(f'stage2 costs {[round(c, 3) for _, c in res]}')
    return res[0]


def derive_frames(d, p, log=print):
    """Apply the solved constant cradle to every key and the per-frame thumb stop."""
    F = len(d.rig.times)
    q = np.zeros_like(d.rig.q)
    rows = []
    prev = 0.0
    for f in range(F):
        stop, axis, depth, L = d.thumb_stop(f, p, prev)
        prev = stop
        q[f] = d.edit(f, p, stop, axis)
        pad = L[d.thumb_pad[d.thumb_tip]]
        glass = FG.box_sdf(pad, d.screen[1], d.screen[2])
        tip = pad[np.argmin(glass)]
        u = (tip[0]-d.screen[1][0])/(2*d.screen[2][0])+.5
        v = (tip[1]-d.screen[1][1])/(2*d.screen[2][1])+.5
        over = 0 <= u <= 1 and 0 <= v <= 1
        pad_glass = float(glass.min())
        # Tap = force contact of the PAD on the glass: the captured thumb would pass the phone, the stop holds it,
        # and the pad skin is within GLASS_TOUCH_CM of the glass rectangle. A stop on the case rim is not a tap.
        rows.append({'time': round(float(d.rig.times[f]), 5), 'thumb_stop_deg': round(stop, 4),
                     'thumb_stop_joint': axis[0] if axis else None,
                     'thumb_min_clearance_cm': round(depth, 4), 'pad_glass_clearance_cm': round(pad_glass, 4),
                     'thumb_pad_uv': [round(u, 4), round(v, 4)], 'thumb_over_glass': bool(over),
                     'near_glass': bool(over and pad_glass <= TOUCH_CM),
                     'rim_contact': bool(stop > 0 and pad_glass > GLASS_TOUCH_CM),
                     'touch': bool(over and stop > 0 and pad_glass <= GLASS_TOUCH_CM)})
    return q, rows


def tap_events(rows):
    events, start = [], None
    for i, r in enumerate(rows+[{'touch': False}]):
        if r['touch'] and start is None:
            start = i
        elif not r['touch'] and start is not None:
            seg = rows[start:i]
            events.append({'down_time': seg[0]['time'], 'up_time': seg[-1]['time'], 'frames': len(seg),
                           'uv': [round(float(np.mean([s['thumb_pad_uv'][k] for s in seg])), 4) for k in (0, 1)],
                           'press_stop_deg_max': max(s['thumb_stop_deg'] for s in seg)})
            start = None
    return events


def joint_report(d, q):
    """Per-joint angular delta from the captured local rotation, per frame, and anatomy checks."""
    edited = [d.hand]+[d.rig.index(f'RightHand{f}{j}') for f in FINGERS for j in (1, 2, 3)]+[d.rig.index(f'RightHandThumb{j}') for j in (1, 2)]
    out = {}
    for i in edited:
        delta = q_angle_deg(q[:, i], d.rig.q0[:, i])
        vel = np.abs(np.diff(q_angle_deg(q[1:, i], q[:-1, i])))*30 if len(q) > 2 else np.zeros(1)
        speed = q_angle_deg(q[1:, i], q[:-1, i])*30
        out[d.rig.nodes[i]['name']] = {'delta_from_capture_deg': {'min': round(float(delta.min()), 3), 'max': round(float(delta.max()), 3), 'mean': round(float(delta.mean()), 3)},
                                       'max_angular_speed_deg_s': round(float(speed.max()), 3),
                                       'max_angular_accel_deg_s2': round(float(vel.max())*30, 3)}
    return out


def anatomy(d, p):
    th = p[9:25].reshape(4, 4)
    rows = {}
    ok = True
    for k, finger in enumerate(FINGERS):
        lim = {f'joint{j}_flex_deg': round(float(th[k, j-1]), 3) for j in (1, 2, 3)}
        lim['joint1_abduction_deg'] = round(float(th[k, 3]), 3)
        inside = all(FLEX_LIMITS[j][0] <= th[k, j-1] <= FLEX_LIMITS[j][1] for j in (1, 2, 3)) and abs(th[k, 3]) <= ABD_LIMIT
        lim['within_limits'] = bool(inside)
        ok &= inside
        rows[finger] = lim
    return rows, bool(ok)


def bone_lengths(d, q, frames):
    """Max |derived - source| joint-to-child distance (cm) over frames: rotations only, so ~0."""
    W0 = d.rig.worlds(frames=frames)
    W1 = np.array([d.worlds(f, q[f]) for f in frames])
    err = 0.0
    for i, par in d.rig.parent.items():
        a = np.linalg.norm(W0[:, i, :3, 3]-W0[:, par, :3, 3], axis=-1)
        b = np.linalg.norm(W1[:, i, :3, 3]-W1[:, par, :3, 3], axis=-1)
        err = max(err, float(np.abs(a-b).max())*100)
    return err


def write_glb(rig, q, edited, out, extras):
    doc, binary, sha = read_glb(rig.clip_path)
    binary = bytearray(binary)
    for i in edited:
        ch = rig.channels.get((i, 'rotation'))
        if ch is None:
            raise ValueError(f'No rotation channel for {rig.nodes[i]["name"]}')
        anim = doc['animations'][0]
        acc = doc['accessors'][anim['samplers'][ch['sampler']]['output']]
        view = doc['bufferViews'][acc['bufferView']]
        if view.get('byteStride', 16) != 16 or acc['count'] != len(q):
            raise ValueError('Tightly packed per-key rotation output required')
        start = view.get('byteOffset', 0)+acc.get('byteOffset', 0)
        binary[start:start+16*len(q)] = np.asarray(q[:, i], np.float32).tobytes()
        acc.pop('min', None)
        acc.pop('max', None)
    doc['asset'].setdefault('extras', {}).update(extras)
    doc['animations'][0]['name'] = 'SUB01_PhoneGrip_derived'
    js = json.dumps(doc, separators=(',', ':')).encode()
    js += b' '*((-len(js)) % 4)
    binary = bytes(binary)+b'\0'*((-len(binary)) % 4)
    glb = struct.pack('<III', 0x46546c67, 2, 28+len(js)+len(binary))+struct.pack('<II', len(js), 0x4e4f534a)+js+struct.pack('<II', len(binary), 0x004e4942)+binary
    Path(out).write_bytes(glb)
    return hashlib.sha256(glb).hexdigest(), sha


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--clip', type=Path, default=CLIP)
    ap.add_argument('--cache', type=Path, default=ROOT/'out/phone-grip')
    ap.add_argument('--out-dir', type=Path, default=ROOT/'docs/proposed/phone-grip-derived')
    ap.add_argument('--params', type=Path, help='Reuse solved parameters JSON instead of searching')
    ap.add_argument('--start', type=Path, help='Warm-start from a previous derivation report')
    ap.add_argument('--active-set', type=Path, help='JSON {frames:[...]} of audit-found extrema kept in every solve')
    ap.add_argument('--add-worst-from-audit', type=Path, help='Append the worst violating frames of this audit to --active-set')
    ap.add_argument('--worst-k', type=int, default=8)
    ap.add_argument('--iterations', type=int, default=60)
    ap.add_argument('--palm-weight', type=float, default=PALM_WEIGHT)
    ap.add_argument('--population', type=int, default=64)
    ap.add_argument('--workers', type=int, default=4)
    args = ap.parse_args(argv)
    skin = Skin(ensure_skin(args.cache))
    rig = Rig(Path(args.cache)/'owner-skin.json', args.clip)
    if skin.owner_sha != FG.sha256(OWNER):
        raise ValueError('Owner skin cache does not match the owner GLB')
    globals()['PALM_WEIGHT'] = args.palm_weight
    active = update_active_set(args.active_set, args.add_worst_from_audit, args.worst_k) if args.active_set else []
    d = Derivation(rig, skin, active_frames=active)
    if args.params:
        p = np.array(json.loads(args.params.read_text())['params'], float)
        cost = d.cost(p)
    else:
        start = json.loads(args.start.read_text())['params'] if args.start else None
        p, cost = solve(d, args.workers, args.iterations, args.population, start=start)
    p = clamp_params(p)
    q, thumb_rows = derive_frames(d, p)
    edited = [d.hand]+[rig.index(f'RightHand{f}{j}') for f in FINGERS for j in (1, 2, 3)]+[rig.index(f'RightHandThumb{j}') for j in (1, 2)]
    untouched = np.setdiff1d(np.arange(rig.n), edited)
    exact = float(np.abs(q[:, untouched]-rig.q0[:, untouched]).max())
    fingers, inside = anatomy(d, p)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    glb = args.out_dir/'SUB01_PhoneGrip_derived.glb'
    taps = tap_events(thumb_rows)
    R = FG.rotvec_to_matrix(p[:3])
    ue_off, ue_q, ue_rot = FG.gltf_to_ue_local(p[3:6], R)
    extras = {'label': LABEL, 'schema': SCHEMA, 'verified': False, 'source_clip_sha256': rig.clip_sha,
              'owner_sha256': skin.owner_sha, 'edited_joints': [rig.nodes[i]['name'] for i in edited],
              'not': 'original capture; capture-invariance does not apply'}
    out_sha, src_sha = write_glb(rig, q, edited, glb, extras)
    report = {
        'schema': SCHEMA, 'label': LABEL, 'verified': False, 'requires_native_reaudit': True, 'visual_accepted': False,
        'original_capture_invariance': 'NOT APPLICABLE: derived clip; finger, thumb and RightHand local rotations are edited',
        'source': {'clip': str(args.clip.relative_to(ROOT)) if args.clip.is_relative_to(ROOT) else str(args.clip), 'clip_sha256': src_sha,
                   'owner': str(OWNER.relative_to(ROOT)), 'owner_sha256': skin.owner_sha, 'keys': len(rig.times), 'fps': 30},
        'output': {'glb': str(glb.relative_to(ROOT)) if glb.is_relative_to(ROOT) else str(glb), 'sha256': out_sha},
        'params': p.tolist(), 'objective_at_review_pose': round(float(cost), 6),
        'phone_mount': {'gltf_right_hand_local': {'offset_cm': [round(float(v), 5) for v in p[3:6]], 'quaternion_xyzw': [round(float(v), 8) for v in FG.matrix_to_quat(R)]},
                        'ue_phoneGripCandidate': 'X=%.5f Y=%.5f Z=%.5f|P=%.5f Y=%.5f R=%.5f' % (tuple(ue_off)+ue_rot),
                        'frame': 'derived RightHand (the constant hand correction is baked into the clip; no native wrist installer needed)'},
        'edits': {'right_hand_correction_deg': round(math.degrees(np.linalg.norm(p[6:9])), 4),
                  'thumb1_cmc_offset_deg': round(math.degrees(np.linalg.norm(p[25:28])), 4),
                  'thumb2_mcp_offset_deg': round(math.degrees(np.linalg.norm(p[28:31])), 4),
                  'finger_cradle': fingers, 'finger_cradle_within_anatomical_limits': inside,
                  'limits_deg': {'flex': {f'joint{j}': v for j, v in FLEX_LIMITS.items()}, 'abduction': ABD_LIMIT, 'hand_correction': HAND_CORR_MAX,
                                 'thumb1_cmc': THUMB1_MAX, 'thumb2_mcp': THUMB2_MAX, 'thumb_stop_mcp_then_cmc': THUMB_STOP_MAX}},
        'per_joint': joint_report(d, q),
        'untouched_joints_max_quaternion_component_change': exact,
        'bone_length_max_error_cm': bone_lengths(d, q, list(range(0, len(rig.times), 10))),
        'active_set_frames': d.active_frames,
        'thumb': {'frames': thumb_rows, 'tap_events': taps, 'tap_count': len(taps),
                  'rule': 'tap = the per-frame stop is engaged AND the thumb pad skin is within %.2f cm of the glass rectangle; stop on the case rim = rim_contact, not a tap; near_glass = pad within %.1f cm without force; geometry only, no timer' % (GLASS_TOUCH_CM, TOUCH_CM)},
        'left_hand': 'unchanged capture (free hand); audited for phone clearance by tools/audit_phone_grip_clip.py',
        'gates': {'native_import': False, 'native_contact': False, 'visual_acceptance': False, 'activity_binding': False}}
    (args.out_dir/'SUB01_PhoneGrip_derived.report.json').write_text(json.dumps(report, indent=1)+'\n')
    print(json.dumps({'cost': cost, 'glb_sha256': out_sha, 'taps': len(taps), 'cradle_ok': inside,
                      'bone_err_cm': report['bone_length_max_error_cm'], 'untouched': exact, 'mount': report['phone_mount']['ue_phoneGripCandidate']}, indent=1))


if __name__ == '__main__':
    main()
