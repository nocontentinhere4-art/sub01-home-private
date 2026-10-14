"""Private phone grip solver: rigid wrist-frame mount of the original five-part phone.

Proposal only. It never verifies, binds or accepts anything (``verified: false``,
``requires_native_reaudit: true``). Inputs are the exact owner GLB and the exact captured
clip (``--owner``/``--clip``), skinned by ``tools/phone_grip_hand_export.mjs`` with every
vertex of every skinned primitive. No bone, finger, clip time or animation value is changed;
the only free variable is one rigid phone transform in the right-hand joint frame.

Contact is measured from geometry alone (signed distance of actual skinned vertices to the
actual part boxes, triangle/box separating-axis tests, eye rays against actual triangles).
Joint names label vertices for reporting only and never count as contact.

Coordinates: owner model space, centimetres, glTF right-handed (Y up). Native Unreal values
are derived with the FBX handedness mirror (local Y negated), the same convention that maps the
natively verified head-local eye offset onto the actual ``owner_head`` surface; root must check
the emitted ``native_parity`` numbers against the SUB01_PHONE_CAPTURED_WRIST/HEAD log lines.
"""
import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'sub01.phone-grip-fit.v1'
# Original five-part assembly, UE world bounds from tools/unreal_phone_grip_diagnostic.py PARTS.
UE_CENTER = (270.0, -292.0, 85.8)
UE_PARTS = [('case', (270, -292, 85.8), (3.75, 7.5, .75)), ('speaker', (270, -298.2, 86.7), (.95, .15, .05)),
            ('volume', (266.2, -294, 85.8), (.1, 1.25, .2)), ('power', (273.8, -294, 85.8), (.1, .7, .2)),
            ('screen', (270, -292, 86.6), (3.35, 6.85, 0))]
# Natively verified Head-local eye (UE convention), tools/unreal_phone_grip_diagnostic.py.
UE_EYE_HEAD_LOCAL = (.11885198390986161, -13.382490930007885, 12.634526097714183)
MIRROR = np.diag([1.0, -1.0, 1.0])


# ---------------------------------------------------------------- rotations
def quat_to_matrix(q):
    x, y, z, w = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def matrix_to_quat(m):
    t = np.trace(m)
    if t > 0:
        s = math.sqrt(t+1)*2
        q = [(m[2, 1]-m[1, 2])/s, (m[0, 2]-m[2, 0])/s, (m[1, 0]-m[0, 1])/s, s/4]
    else:
        i = int(np.argmax(np.diag(m)))
        j, k = (i+1) % 3, (i+2) % 3
        s = math.sqrt(1+m[i, i]-m[j, j]-m[k, k])*2
        q = [0.0]*4
        q[i] = s/4
        q[j] = (m[j, i]+m[i, j])/s
        q[k] = (m[k, i]+m[i, k])/s
        q[3] = (m[k, j]-m[j, k])/s
    q = np.array(q)
    q /= np.linalg.norm(q)
    return q if q[3] >= 0 else -q


def rotvec_to_matrix(v):
    theta = float(np.linalg.norm(v))
    if theta < 1e-12:
        return np.eye(3)
    k = np.asarray(v)/theta
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3)+math.sin(theta)*K+(1-math.cos(theta))*K@K


def matrix_to_rotvec(m):
    q = matrix_to_quat(m)
    s = np.linalg.norm(q[:3])
    if s < 1e-12:
        return np.zeros(3)
    return q[:3]/s*2*math.atan2(s, q[3])


def ue_rotator_from_quat(q):
    """FQuat::Rotator() (UnrealMath.cpp), degrees: pitch, yaw, roll."""
    x, y, z, w = q
    singularity = z*x-w*y
    yaw = math.degrees(math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z)))
    if singularity < -0.4999995:
        return -90.0, yaw, _norm_deg(-yaw-2*math.degrees(math.atan2(x, w)))
    if singularity > 0.4999995:
        return 90.0, yaw, _norm_deg(yaw-2*math.degrees(math.atan2(x, w)))
    pitch = math.degrees(math.asin(2*singularity))
    roll = math.degrees(math.atan2(-2*(w*x+y*z), 1-2*(x*x+y*y)))
    return pitch, yaw, roll


def ue_quat_from_rotator(pitch, yaw, roll):
    """FRotator::Quaternion() (UnrealMath.cpp)."""
    sp, cp = math.sin(math.radians(pitch)/2), math.cos(math.radians(pitch)/2)
    sy, cy = math.sin(math.radians(yaw)/2), math.cos(math.radians(yaw)/2)
    sr, cr = math.sin(math.radians(roll)/2), math.cos(math.radians(roll)/2)
    return np.array([cr*sp*sy-sr*cp*cy, -cr*sp*cy-sr*cp*sy, cr*cp*sy-sr*sp*cy, cr*cp*cy+sr*sp*sy])


def _norm_deg(a):
    return (a+180) % 360-180


def gltf_to_ue_local(offset_cm, rotation):
    """Mirror a wrist-local glTF mount (phone frame also mirrored) into UE wrist-local values."""
    r = MIRROR@np.asarray(rotation)@MIRROR
    q = matrix_to_quat(r)
    return MIRROR@np.asarray(offset_cm, float), q, ue_rotator_from_quat(q)


def ue_to_gltf_local(offset_cm, pitch, yaw, roll):
    q = ue_quat_from_rotator(pitch, yaw, roll)
    return MIRROR@np.asarray(offset_cm, float), MIRROR@quat_to_matrix(q)@MIRROR


# ---------------------------------------------------------------- phone geometry
def default_phone():
    """Original parts in the glTF phone frame: x across (power +x), y long (speaker/top +y), z screen."""
    parts = []
    for name, c, e in UE_PARTS:
        local = MIRROR@(np.array(c, float)-UE_CENTER)
        parts.append({'name': name, 'center': local.tolist(), 'half_extent': list(map(float, e))})
    return {'source': 'tools/unreal_phone_grip_diagnostic.py PARTS (actual UE world bounds, axis aligned)', 'parts': parts}


def load_phone(path):
    if path is None:
        return default_phone()
    doc = json.loads(Path(path).read_text())
    parts = doc.get('parts')
    if not parts or not all({'name', 'center', 'half_extent'} <= set(p) for p in parts):
        raise ValueError('Measured phone JSON needs parts[].name/center/half_extent (glTF phone frame, cm)')
    if sum(p['name'] == 'case' for p in parts) != 1 or sum(p['name'] == 'screen' for p in parts) != 1:
        raise ValueError('Exactly one case and one screen part required')
    return {'source': str(path), 'parts': parts}


def box_sdf(local, center, half):
    q = np.abs(local-np.asarray(center))-np.asarray(half)
    outside = np.linalg.norm(np.maximum(q, 0), axis=-1)
    return outside+np.minimum(q.max(axis=-1), 0)


def tri_box_overlap(a, b, c, half, eps=1e-9):
    """Vectorised Akenine-Moller separating-axis triangle/AABB test (box centred at origin)."""
    h = np.asarray(half, float)
    v = np.stack([a, b, c], 1)                      # (n,3,3)
    e = np.stack([b-a, c-b, a-c], 1)                # (n,3,3)
    sep = np.zeros(len(a), bool)
    for k in range(3):                              # box face normals
        sep |= (v[:, :, k].min(1) > h[k]+eps) | (v[:, :, k].max(1) < -h[k]-eps)
    n = np.cross(e[:, 0], e[:, 1])
    d = np.einsum('ij,ij->i', n, a)
    r = np.abs(n)@h
    sep |= np.abs(d) > r+eps
    basis = np.eye(3)
    for i in range(3):
        for j in range(3):
            axis = np.cross(np.broadcast_to(basis[i], e[:, j].shape), e[:, j])
            p = np.einsum('nkj,nj->nk', v, axis)
            r = np.abs(axis)@h
            sep |= (p.min(1) > r+eps) | (p.max(1) < -r-eps)
    return ~sep


def ray_hits(origins, target, a, b, c):
    """Moller-Trumbore: which origin->target segments are blocked by any triangle."""
    blocked = np.zeros(len(origins), bool)
    e1, e2 = b-a, c-a
    for i, o in enumerate(origins):
        d = target-o
        p = np.cross(d, e2)
        det = np.einsum('ij,ij->i', e1, p)
        ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1/np.where(ok, det, 1), 0)
        s = o-a
        u = np.einsum('ij,ij->i', s, p)*inv
        q = np.cross(s, e1)
        v = (q@d)*inv
        t = np.einsum('ij,ij->i', e2, q)*inv
        blocked[i] = np.any(ok & (u >= 0) & (v >= 0) & (u+v <= 1) & (t > 1e-4) & (t < 1-1e-4))
    return blocked


# ---------------------------------------------------------------- data
class HandExport:
    def __init__(self, stem):
        stem = Path(stem)
        self.meta = json.loads(stem.with_suffix('.json').read_text())
        if self.meta.get('schema') != 'sub01.phone-grip-hand-export.v1':
            raise ValueError('Unknown hand export schema')
        f, n, t = self.meta['frames'], self.meta['vertices'], self.meta['triangles']
        raw = np.memmap(stem.with_suffix('.bin'), dtype=np.uint8, mode='r')
        if raw.size != f*n*12+t*12+2*n:
            raise ValueError('Hand export binary size mismatch')
        self.positions = np.frombuffer(raw[:f*n*12], np.float32).reshape(f, n, 3)
        self.triangles = np.frombuffer(raw[f*n*12:f*n*12+t*12], np.uint32).reshape(t, 3).astype(np.int64)
        self.labels = np.frombuffer(raw[f*n*12+t*12:f*n*12+t*12+n], np.uint8)
        self.times = np.array(self.meta['times'])
        self.joints = self.meta['joints']

    def frame_index(self, time):
        i = int(np.argmin(np.abs(self.times-time)))
        if abs(self.times[i]-time) > 1e-4:
            raise ValueError(f'No sampled frame at {time}s')
        return i

    def eye_in_wrist(self, f, eye_head_local):
        w, h = self.meta['wrists'][f], self.meta['heads'][f]
        eye = np.array(h['position'])+quat_to_matrix(h['quaternion'])@np.asarray(eye_head_local)
        return quat_to_matrix(w['quaternion']).T@(eye-np.array(w['position']))

    def gravity_in_wrist(self, f):
        return quat_to_matrix(self.meta['wrists'][f]['quaternion']).T@np.array([0.0, -1.0, 0.0])


def export_hand(owner, clip, out, radius, pose_time):
    cmd = ['node', str(ROOT/'tools/phone_grip_hand_export.mjs'), '--owner', str(owner), '--clip', str(clip),
           '--out', str(out), '--radius', str(radius), '--pose-time', str(pose_time)]
    subprocess.run(cmd, check=True, cwd=ROOT)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------- evaluation
def fibonacci_directions(n):
    i = np.arange(n)+0.5
    phi, z = i*math.pi*(3-math.sqrt(5)), 1-2*i/n
    r = np.sqrt(1-z*z)
    return np.stack([r*np.cos(phi), r*np.sin(phi), z], 1)


class Evaluator:
    """Phone mount in the (corrected) right-hand joint frame.

    rigid   = vertices whose dominant influence is the right hand or a right finger: fixed in the
              hand frame because finger local rotations are never changed.
    forearm = dominant right forearm: moves with an arm IK translation, not with a wrist rotation.
    body    = everything else.
    ``correction`` is a constant extra RightHand local rotation C (hand frame -> captured hand frame),
    bounded by ``max_correction_deg``; identity means the captured wrist."""

    def __init__(self, hand, phone, eye_head_local, pose_time, band=0.3, tolerance=0.0, clearance=0.2, ik_limit=10.0,
                 max_correction_deg=35.0, view_deg=30.0, upright_deg=25.0):
        self.hand, self.phone, self.band, self.tol, self.clear, self.ik_limit = hand, phone, band, tolerance, clearance, ik_limit
        self.max_correction, self.view_deg, self.upright_deg = max_correction_deg, view_deg, upright_deg
        self.parts = [(p['name'], np.array(p['center'], float), np.array(p['half_extent'], float)) for p in phone['parts']]
        self.case = next(p for p in self.parts if p[0] == 'case')
        self.screen = next(p for p in self.parts if p[0] == 'screen')
        self.reach = max(np.linalg.norm(np.abs(c)+h) for _, c, h in self.parts)
        self.pose = hand.frame_index(pose_time)
        self.eye_head_local = np.asarray(eye_head_local, float)
        self.eyes0 = np.array([hand.eye_in_wrist(f, eye_head_local) for f in range(len(hand.times))])
        self.gravity0 = np.array([hand.gravity_in_wrist(f) for f in range(len(hand.times))])
        self.head_up0 = np.array([quat_to_matrix(w['quaternion']).T@quat_to_matrix(h['quaternion'])@[0.0, 1, 0]
                                  for w, h in zip(hand.meta['wrists'], hand.meta['heads'])])
        rigid = np.array([n.startswith('mixamorigRightHand') for n in hand.joints])
        self.rigid = rigid[hand.labels]
        self.forearm = np.array([n == 'mixamorigRightForeArm' for n in hand.joints])[hand.labels]
        self.hand_side = self.rigid | self.forearm
        tri = hand.triangles
        self.rigid_tri = tri[self.rigid[tri].all(1)]
        arms = np.array(hand.meta['arms'])
        wrist = np.array([w['position'] for w in hand.meta['wrists']])
        self.upper = float(np.linalg.norm(arms[0, 1]-arms[0, 2]))
        self.lower = float(np.linalg.norm(arms[0, 2]-wrist[0]))
        self.shoulder0 = np.array([quat_to_matrix(w['quaternion']).T@(arms[f, 1]-wrist[f]) for f, w in enumerate(hand.meta['wrists'])])
        self.directions = fibonacci_directions(160)
        self.set_correction(np.eye(3))

    def set_correction(self, C):
        self.C = np.asarray(C, float)
        self.eyes, self.gravity = self.eyes0@self.C, self.gravity0@self.C
        self.head_up, self.shoulder = self.head_up0@self.C, self.shoulder0@self.C
        return self

    def points(self, f, idx=None):
        """Frame-f vertices in the corrected hand frame (rigid ones unchanged, others counter-rotated)."""
        P = self.hand.positions[f] if idx is None else self.hand.positions[f][idx]
        if np.allclose(self.C, np.eye(3)):
            return np.asarray(P, float)
        rigid = self.rigid if idx is None else self.rigid[idx]
        return np.where(rigid[:, None], P, P@self.C)

    def local(self, f, R, t, idx=None):
        return (self.points(f, idx)-t)@R

    def sdf(self, local):
        return np.min([box_sdf(local, c, h) for _, c, h in self.parts], axis=0)

    def near(self, f, t, extra=1.0):
        # Conservative: the correction rotates about the wrist origin, so test both frames.
        p = self.hand.positions[f]
        r2 = (self.reach+self.band+extra)**2
        return np.nonzero((np.sum((p-t)**2, 1) < r2) | (np.sum((p-self.C@t)**2, 1) < r2))[0]

    def rigid_overlaps(self, f, R, t, idx):
        mask = np.zeros(len(self.hand.labels), bool)
        mask[idx] = True
        tsel = self.rigid_tri[mask[self.rigid_tri].all(1)]
        if not len(tsel):
            return {name: 0 for name, _, _ in self.parts}
        P = self.hand.positions[f]              # rigid vertices: identical in corrected frame
        out = {}
        for name, c, h in self.parts:
            a, b, cc = ((P[tsel[:, k]]-t)@R-c for k in range(3))
            out[name] = int(tri_box_overlap(a, b, cc, h).sum())
        return out

    def upright(self, f, R):
        """Cosine between the phone's top (+y, speaker end) and the head's up axis, both projected
        onto the screen plane: 1 means the live screen reads upright from the actual eye."""
        n = R[:, 2]
        up = self.head_up[f]-(self.head_up[f]@n)*n
        norm = np.linalg.norm(up)
        return float(R[:, 1]@up/norm) if norm > 1e-9 else -1.0

    def contact_spread(self, pts):
        """Largest distance between hand contact points (cm): one patch cannot hold a phone."""
        if len(pts) < 2:
            return 0.0
        sample = pts[:: max(1, len(pts)//200)]
        return float(np.sqrt(((sample[:, None]-sample[None])**2).sum(-1)).max())

    def cost(self, x, frames):
        R, t = rotvec_to_matrix(x[:3]), x[3:6]
        if len(x) > 6:
            angle = math.degrees(np.linalg.norm(x[6:9]))
            self.set_correction(rotvec_to_matrix(x[6:9]))
        else:
            angle = 0.0
        pen_h = pen_b = reward = view = 0.0
        extra = 0.05*angle/10+(10*(angle-self.max_correction)**2 if angle > self.max_correction else 0)
        for f in frames:
            idx = self.near(f, t)
            if not len(idx):
                extra += 25
                continue
            L = (self.points(f, idx)-t)@R
            s = self.sdf(L)
            rg, fa = self.rigid[idx], self.forearm[idx]
            sh, sf, sb = s[rg], s[fa], s[~(rg | fa)]
            pen_h += np.sum(np.maximum(-sh-self.tol, 0)**2)+0.05*np.sum(sh < -self.tol)
            pen_h += np.sum(np.maximum(-sf, 0)**2)+0.05*np.sum(sf < 0)
            pen_b += np.sum(np.maximum(self.clear-sb, 0)**2)
            pos = sh[sh >= 0]
            reward += min(float(np.sum(np.exp(-(pos/self.band)**2))), 400)/400
            if f == self.pose:
                extra += 2*float(np.sort(pos)[:12].mean()) if len(pos) >= 12 else 25
                extra += 2*sum(self.rigid_overlaps(f, R, t, idx).values())
                contact = (sh >= -self.tol) & (sh <= self.band)
                cl = L[rg][contact]
                sup = self.support(cl, self.case[1], self.case[2], self.gravity[f]@R)
                extra += 0 if sup['supported'] else 3
                extra += 0 if sup.get('opposing_side_pinch') else 2
                extra += max(0.0, 6.0-self.contact_spread(cl))
                extra += 10*max(0.0, math.cos(math.radians(self.view_deg))-(R[:, 2]@(self.eyes[f]-t))/np.linalg.norm(self.eyes[f]-t))
                extra += 10*max(0.0, math.cos(math.radians(self.upright_deg))-self.upright(f, R))
            d = self.eyes[f]-t
            view += max(0.0, math.cos(math.radians(self.view_deg))-(R[:, 2]@d)/np.linalg.norm(d))**2
            view += max(0.0, math.cos(math.radians(self.upright_deg))-self.upright(f, R))**2
        n = len(frames)
        return (50*pen_h+0.5*pen_b-reward+20*view)/n+extra

    def ik_delta(self, f, R, t, previous):
        """Smallest bounded wrist translation (hand frame, orientation kept) clearing body skin."""
        idx = self.near(f, t, extra=self.ik_limit+1)
        idx = idx[~self.hand_side[idx]]
        Lb = (self.points(f, idx)-t)@R
        # The captured pose is always reachable; a move may not straighten the arm beyond it or 0.5 cm short.
        reach = max(self.upper+self.lower-0.5, float(np.linalg.norm(self.shoulder[f])))
        if not len(idx) or self.sdf(Lb).min() >= self.clear:
            return np.zeros(3), True
        best, best_score, found_at = None, None, None
        for k, m in enumerate(np.arange(0.25, self.ik_limit+1e-9, 0.25)):
            if found_at is not None and k > found_at+4:
                break
            cand = self.directions*m
            ok = np.linalg.norm(self.shoulder[f][None]-cand, axis=1) <= reach
            P = Lb[None]-(cand@R)[:, None]
            ok &= self.sdf(P.reshape(-1, 3)).reshape(len(cand), -1).min(1) >= self.clear
            if ok.any():
                found_at = k if found_at is None else found_at
                score = m+2*np.linalg.norm(cand[ok]-previous, axis=1)
                j = int(np.argmin(score))
                if best_score is None or score[j] < best_score:
                    best, best_score = cand[ok][j], float(score[j])
        return (np.zeros(3), False) if best is None else (best, True)

    def residuals(self, R, t, frames=None, occlusion_stride=1, screen_grid=(5, 9), ik=True):
        frames = list(range(len(self.hand.times)) if frames is None else frames)
        rows = []
        sx, sy = screen_grid
        _, cc, ch = self.case
        _, scc, sch = self.screen
        gx, gy = np.meshgrid(np.linspace(-1, 1, sx)*sch[0]*.95, np.linspace(-1, 1, sy)*sch[1]*.95)
        samples = np.stack([gx.ravel(), gy.ravel(), np.full(gx.size, scc[2]+1e-3)], 1)
        previous = np.zeros(3)
        tri = self.hand.triangles
        for f in frames:
            idx = self.near(f, t, extra=2.0)
            L = (self.points(f, idx)-t)@R
            s = self.sdf(L)
            rg, fa = self.rigid[idx], self.forearm[idx]
            bd = ~(rg | fa)
            sh = s[rg]
            delta, reachable = self.ik_delta(f, R, t, previous) if ik else (np.zeros(3), True)
            previous = delta
            sb_after = self.sdf(L[bd]-delta@R) if np.any(bd) else np.array([np.inf])
            contact = (sh >= -self.tol) & (sh <= self.band)
            labels = self.hand.labels[idx][rg]
            eye_local = (self.eyes[f]-t-delta)@R
            d = eye_local-scc
            angle = math.degrees(math.acos(np.clip(d[2]/np.linalg.norm(d), -1, 1)))
            row = {'time': round(float(self.hand.times[f]), 4),
                   'hand_penetrating_vertices': int(np.sum(sh < -self.tol)),
                   'hand_max_penetration_cm': round(float(max(0.0, -sh.min())) if len(sh) else 0.0, 4),
                   'forearm_penetrating_vertices': int(np.sum(s[fa] < 0)),
                   'hand_triangle_part_overlaps': self.rigid_overlaps(f, R, t, idx),
                   'hand_contact_vertices': int(contact.sum()),
                   'hand_contact_spread_cm': round(self.contact_spread(L[rg][contact]), 3),
                   'contact_joint_labels_reporting_only': sorted({self.hand.joints[j] for j in labels[contact]}),
                   'hand_nearest_gap_cm': round(float(sh[sh >= 0].min()) if np.any(sh >= 0) else -1.0, 4),
                   'body_penetrating_vertices_before_ik': int(np.sum(s[bd] < 0)),
                   'ik_wrist_delta_cm_gltf_wrist_local': [round(float(v), 4) for v in delta],
                   'ik_wrist_delta_cm_ue_wrist_local': [round(float(v), 4) for v in MIRROR@delta],
                   'ik_reachable': bool(reachable),
                   'body_min_clearance_after_ik_cm': round(float(sb_after.min()), 4) if np.isfinite(sb_after.min()) else None,
                   'shoulder_reach_margin_cm': round(self.upper+self.lower-float(np.linalg.norm(self.shoulder[f]-delta)), 3),
                   'screen_upright_deg': round(math.degrees(math.acos(np.clip(self.upright(f, R), -1, 1))), 2),
                   'screen_to_eye_angle_deg': round(angle, 2), 'eye_distance_cm': round(float(np.linalg.norm(d)), 2),
                   'gravity_support': self.support(L[rg][contact], cc, ch, self.gravity[f]@R)}
            if occlusion_stride and f % occlusion_stride == 0:
                world = samples@R.T+t+delta
                eye = self.eyes[f]
                P = self.points(f)
                Ph = np.where(self.hand_side[:, None], P+delta, P)
                lo, hi = np.minimum(world.min(0), eye)-0.5, np.maximum(world.max(0), eye)+0.5
                tmin = np.minimum(np.minimum(Ph[tri[:, 0]], Ph[tri[:, 1]]), Ph[tri[:, 2]])
                tmax = np.maximum(np.maximum(Ph[tri[:, 0]], Ph[tri[:, 1]]), Ph[tri[:, 2]])
                # Only triangles whose bounds meet the bounds of the screen-to-eye ray bundle can block.
                near = tri[np.all((tmax >= lo) & (tmin <= hi), 1)]
                blocked = ray_hits(world, eye, Ph[near[:, 0]], Ph[near[:, 1]], Ph[near[:, 2]]) if len(near) else np.zeros(len(world), bool)
                row['screen_visible_fraction'] = round(1-float(blocked.mean()), 4)
            rows.append(row)
        return rows

    @staticmethod
    def support(contacts, center, half, gravity_local):
        """Hull test: does the centre of mass project inside contacts that can push against gravity."""
        if len(contacts) == 0:
            return {'supported': False, 'reason': 'no contact'}
        g = gravity_local/np.linalg.norm(gravity_local)
        # Outward face normal of the case at each contact (closest face of the box).
        q = (contacts-center)/half
        axis = np.argmax(np.abs(q), 1)
        normals = np.zeros_like(contacts)
        normals[np.arange(len(q)), axis] = np.sign(q[np.arange(len(q)), axis])
        pushing = normals@g > 0.25          # skin under the phone relative to gravity
        # Friction pinch: at least three skin contacts on each of two opposite case faces.
        faces = {}
        for n in normals.astype(int).tolist():
            faces[tuple(n)] = faces.get(tuple(n), 0)+1
        pinch = any(k >= 3 and faces.get(tuple(-v for v in n), 0) >= 3 for n, k in faces.items())
        pts = contacts[pushing]
        if len(pts) < 3:
            return {'supported': bool(pinch), 'under_contacts': int(len(pts)), 'opposing_side_pinch': bool(pinch)}
        u = np.cross(g, [1, 0, 0] if abs(g[0]) < .9 else [0, 1, 0])
        u /= np.linalg.norm(u)
        v = np.cross(g, u)
        hull = _hull(np.stack([pts@u, pts@v], 1))
        com = np.array([center@u, center@v])
        inside = _inside(hull, com)
        return {'supported': bool(inside or pinch), 'under_contacts': int(len(pts)), 'com_inside_support_hull': bool(inside),
                'opposing_side_pinch': bool(pinch)}


def thumb_screen_track(ev, R, t, touch_cm=0.1):
    """Captured thumb pad versus the screen glass, per frame (corrected hand frame, phone frame).

    uv: screen coordinates of the thumb pad point nearest the glass plane (0..1, origin at the
    volume/bottom corner, v toward the speaker); depth_cm: signed height above the glass (negative
    means the rigid model presses through, i.e. a tap the native finger collision must resolve).
    A touch is reported only from geometry (|depth| <= touch_cm inside the glass), never from names."""
    _, sc, sh = ev.screen
    names = np.array(ev.hand.joints)[ev.hand.labels]
    pad = np.nonzero(np.isin(names, ['mixamorigRightHandThumb3']))[0]
    rows = []
    for f in range(len(ev.hand.times)):
        L = (ev.points(f, pad)-t)@R
        i = int(np.argmin(L[:, 2]))
        p = L[i]
        u, v = (p[0]-sc[0])/(2*sh[0])+.5, (p[1]-sc[1])/(2*sh[1])+.5
        depth = float(p[2]-sc[2])
        inside = 0 <= u <= 1 and 0 <= v <= 1
        rows.append({'time': round(float(ev.hand.times[f]), 4), 'uv': [round(u, 4), round(v, 4)], 'depth_cm': round(depth, 4),
                     'over_glass': bool(inside), 'touch': bool(inside and abs(depth) <= touch_cm), 'press': bool(inside and depth < -touch_cm)})
    return rows


def _hull(points):
    pts = sorted(set(map(tuple, np.round(points, 5))))
    if len(pts) < 3:
        return np.array(pts)

    def cross(o, a, b):
        return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.array(lower[:-1]+upper[:-1])


def _inside(hull, p):
    if len(hull) < 3:
        return False
    for i in range(len(hull)):
        a, b = hull[i], hull[(i+1) % len(hull)]
        if (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]) < 0:
            return False
    return True


# ---------------------------------------------------------------- search
def _frame(z, roll):
    z = z/np.linalg.norm(z)
    ref = np.array([0.0, 1.0, 0.0]) if abs(z[1]) < .9 else np.array([1.0, 0, 0])
    x0 = np.cross(ref, z)
    x0 /= np.linalg.norm(x0)
    y0 = np.cross(z, x0)
    x = math.cos(roll)*x0+math.sin(roll)*y0
    return np.stack([x, np.cross(z, x), z], 1)


def seeds(ev, count_roll=12, kinds=('pinch', 'view')):
    """Initial guesses from geometry: screen toward the actual eye or along the actual palm side."""
    f = ev.pose
    P = ev.hand.positions[f][ev.rigid]
    centroid = P[np.linalg.norm(P, axis=1) < 14].mean(0)
    eye = ev.eyes[f]
    out = []
    # Pinch seeds: case thickness between the thumb pad and the opposing finger pads, by measured skin.
    names = np.array(ev.hand.joints)[ev.hand.labels]
    allp = ev.hand.positions[f]
    thumb = allp[names == 'mixamorigRightHandThumb3']
    for finger in (('mixamorigRightHandMiddle3', 'mixamorigRightHandIndex3') if 'pinch' in kinds else ()):
        pads = allp[names == finger]
        if not len(thumb) or not len(pads):
            continue
        d = np.sqrt(((thumb[:, None]-pads[None])**2).sum(-1))
        i, j = np.unravel_index(np.argmin(d), d.shape)
        mid, z = (thumb[i]+pads[j])/2, thumb[i]-pads[j]
        for k in range(count_roll):
            R = _frame(z, 2*math.pi*k/count_roll)
            for sx in (-3.0, 0.0, 3.0):
                for sy in (-6.0, -3.0, 3.0, 6.0):
                    out.append(np.concatenate([matrix_to_rotvec(R), mid+R[:, 0]*sx+R[:, 1]*sy]))
    for z in ((eye-centroid, np.array([0.0, 0, 1]), (eye-centroid)/np.linalg.norm(eye-centroid)+[0, 0, 1]) if 'view' in kinds else ()):
        for lift in (2.0, 4.0, 6.0):
            for slide in (-2.0, 0.0, 2.0):
                for k in range(count_roll):
                    R = _frame(np.asarray(z, float), 2*math.pi*k/count_roll)
                    t = centroid+R[:, 2]*lift+R[:, 1]*slide
                    out.append(np.concatenate([matrix_to_rotvec(R), t]))
    return out


def cem(ev, x0, frames, iterations=30, population=48, elite=8, rng=None, sigma=(0.25, 1.5, 0.15)):
    rng = rng or np.random.default_rng(0)
    mean = np.array(x0, float)
    std = np.array(([sigma[0]]*3+[sigma[1]]*3+[sigma[2]]*3)[:len(mean)])
    floor = np.array(([0.004]*3+[0.03]*3+[0.004]*3)[:len(mean)])
    best, best_cost = mean.copy(), ev.cost(mean, frames)
    for _ in range(iterations):
        pop = mean+rng.standard_normal((population, len(mean)))*std
        costs = np.array([ev.cost(x, frames) for x in pop])
        order = np.argsort(costs)
        if costs[order[0]] < best_cost:
            best, best_cost = pop[order[0]].copy(), float(costs[order[0]])
        el = pop[order[:elite]]
        mean = el.mean(0)
        std = np.maximum(el.std(0), floor)
    return best, best_cost


_EV = None


def _refine(job):
    k, x, frames = job
    x1, _ = cem(_EV, x, [_EV.pose], iterations=40, rng=np.random.default_rng(k))
    return cem(_EV, x1, frames, iterations=12, population=32, rng=np.random.default_rng(100+k), sigma=(0.08, 0.5, 0.06))


def search(ev, frames, starts=8, workers=4, correction=False, kinds=('pinch', 'view')):
    global _EV
    _EV = ev
    pool = seeds(ev, kinds=kinds)
    if correction:
        pool = [np.concatenate([x, c]) for x in pool for c in (np.zeros(3),)]
    ranked = sorted(((ev.cost(x, [ev.pose]), i, x) for i, x in enumerate(pool)), key=lambda c: c[0])[:starts]
    jobs = [(k, x, frames) for k, (_, _, x) in enumerate(ranked)]
    if workers > 1:
        import multiprocessing
        with multiprocessing.get_context('fork').Pool(workers) as pool:
            results = pool.map(_refine, jobs)
    else:
        results = [_refine(j) for j in jobs]
    return sorted(((c, x) for x, c in results), key=lambda r: r[0])


def _residual_chunk(job):
    R, t, frames, stride = job
    return _EV.residuals(R, t, frames=frames, occlusion_stride=stride)


def parallel_residuals(ev, R, t, occlusion_stride=1, workers=4):
    """Full-clip residuals in contiguous chunks; IK continuity restarts at each chunk boundary."""
    global _EV
    _EV = ev
    frames = list(range(len(ev.hand.times)))
    if workers <= 1:
        return ev.residuals(R, t, occlusion_stride=occlusion_stride)
    chunks = [frames[k*len(frames)//workers:(k+1)*len(frames)//workers] for k in range(workers)]
    import multiprocessing
    with multiprocessing.get_context('fork').Pool(workers) as pool:
        parts = pool.map(_residual_chunk, [(R, t, c, occlusion_stride) for c in chunks])
    return [row for part in parts for row in part]


def summarize(rows):
    worst = max(rows, key=lambda r: (r['hand_max_penetration_cm'], r['hand_penetrating_vertices']))
    parts = rows[0]['hand_triangle_part_overlaps'].keys()
    vis = [r['screen_visible_fraction'] for r in rows if 'screen_visible_fraction' in r]
    ik = [np.linalg.norm(r['ik_wrist_delta_cm_gltf_wrist_local']) for r in rows]
    steps = [float(np.linalg.norm(np.subtract(a['ik_wrist_delta_cm_gltf_wrist_local'], b['ik_wrist_delta_cm_gltf_wrist_local'])))
             for a, b in zip(rows, rows[1:])]
    return {'frames': len(rows),
            'hand_frames_with_penetration': sum(r['hand_penetrating_vertices'] > 0 for r in rows),
            'hand_max_penetration_cm': max(r['hand_max_penetration_cm'] for r in rows),
            'hand_max_penetrating_vertices': max(r['hand_penetrating_vertices'] for r in rows),
            'hand_worst_time': worst['time'],
            'hand_triangle_part_overlaps_total': {p: sum(r['hand_triangle_part_overlaps'][p] for r in rows) for p in parts},
            'hand_triangle_part_overlaps_max_frame': {p: max(r['hand_triangle_part_overlaps'][p] for r in rows) for p in parts},
            'hand_contact_vertices': [min(r['hand_contact_vertices'] for r in rows), max(r['hand_contact_vertices'] for r in rows)],
            'frames_supported': sum(r['gravity_support']['supported'] for r in rows),
            'body_frames_needing_ik': sum(r['body_penetrating_vertices_before_ik'] > 0 for r in rows),
            'ik_delta_cm_max': round(max(ik), 3), 'ik_delta_step_cm_max': round(max(steps), 3) if steps else 0.0,
            'ik_unreachable_frames': sum(not r['ik_reachable'] for r in rows),
            'body_min_clearance_after_ik_cm': min(r['body_min_clearance_after_ik_cm'] for r in rows if r['body_min_clearance_after_ik_cm'] is not None),
            'screen_to_eye_angle_deg': [min(r['screen_to_eye_angle_deg'] for r in rows), max(r['screen_to_eye_angle_deg'] for r in rows)],
            'screen_upright_deg': [min(r['screen_upright_deg'] for r in rows), max(r['screen_upright_deg'] for r in rows)],
            'eye_distance_cm': [min(r['eye_distance_cm'] for r in rows), max(r['eye_distance_cm'] for r in rows)],
            'screen_visible_fraction_min_mean': [min(vis), round(float(np.mean(vis)), 4)] if vis else None}


def correction_record(C):
    q = matrix_to_quat(C)
    qu = matrix_to_quat(MIRROR@C@MIRROR)
    return {'angle_deg': round(math.degrees(2*math.acos(min(1.0, abs(q[3])))), 4),
            'gltf_right_hand_local_post_multiply_xyzw': [round(float(v), 8) for v in q],
            'ue_right_hand_local_post_multiply_xyzw': [round(float(v), 8) for v in qu],
            'ue_rotator': 'P=%.5f Y=%.5f R=%.5f' % ue_rotator_from_quat(qu),
            'apply': 'RightHand local rotation := captured local * correction (every frame); all finger locals, '
                     'bone lengths and other bones unchanged; phone mount is expressed in the corrected RightHand frame'}


def candidate_record(ev, R, t, label, rows):
    ue_offset, ue_q, ue_rot = gltf_to_ue_local(t, R)
    q = matrix_to_quat(R)
    return {'label': label, 'right_hand_correction': correction_record(ev.C),
            'gltf_wrist_local': {'offset_cm': [round(float(v), 5) for v in t], 'quaternion_xyzw': [round(float(v), 8) for v in q]},
            'ue_wrist_local': {'Sub01PhoneMountCm': 'X=%.5f Y=%.5f Z=%.5f' % tuple(ue_offset),
                               'Sub01PhoneMountEuler': 'P=%.5f Y=%.5f R=%.5f' % ue_rot,
                               'quaternion_xyzw': [round(float(v), 8) for v in ue_q],
                               'phoneGripCandidate': 'X=%.5f Y=%.5f Z=%.5f|P=%.5f Y=%.5f R=%.5f' % (tuple(ue_offset)+ue_rot)},
            'pose_frame': next(r for r in rows if abs(r['time']-ev.hand.times[ev.pose]) < 1e-3),
            'fullframe_summary': summarize(rows)}


def native_parity(hand, pose):
    """Numbers root compares against SUB01_PHONE_CAPTURED_WRIST/HEAD (UE head-local, cm)."""
    w, h = hand.meta['wrists'][pose], hand.meta['heads'][pose]
    Rh = quat_to_matrix(h['quaternion'])
    rel = Rh.T@(np.array(w['position'])-np.array(h['position']))
    relR = Rh.T@quat_to_matrix(w['quaternion'])
    q = matrix_to_quat(MIRROR@relR@MIRROR)
    return {'wrist_in_head_frame_cm_ue': (MIRROR@rel).round(4).tolist(),
            'wrist_relative_to_head_quaternion_ue_xyzw': q.round(6).tolist(),
            'check': 'Inverse(H.Rotation).RotateVector(W.Location-H.Location) and Inverse(H.Rotation)*W.Rotation from the captured log must match within 0.5 cm / 1 degree before the mount is imported'}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--owner', type=Path, default=ROOT/'web/room/char_mixamo.glb')
    ap.add_argument('--clip', type=Path, required=True)
    ap.add_argument('--phone', type=Path, help='Measured part JSON (glTF phone frame, cm); default actual UE bounds')
    ap.add_argument('--cache', type=Path, default=ROOT/'out/phone-grip')
    ap.add_argument('--radius', type=float, default=30)
    ap.add_argument('--pose-time', type=float, default=4.0)
    ap.add_argument('--evaluate-gltf', help='JSON {offset_cm, quaternion_xyzw, correction_xyzw?} in the glTF hand frame')
    ap.add_argument('--evaluate-ue', help="Evaluate a UE candidate 'X=.. Y=.. Z=..|P=.. Y=.. R=..' instead of searching")
    ap.add_argument('--frame-stride', type=int, default=20, help='Search frames stride (final residuals use every frame)')
    ap.add_argument('--occlusion-stride', type=int, default=1)
    ap.add_argument('--top', type=int, default=3)
    ap.add_argument('--starts', type=int, default=8)
    ap.add_argument('--wrist-correction', action='store_true',
                    help='Also solve one bounded constant RightHand local rotation (fingers unchanged)')
    ap.add_argument('--max-correction-deg', type=float, default=35.0)
    ap.add_argument('--seed-set', default='pinch,view', help='Comma list: pinch (thumb/finger pads), view (screen to eye)')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args(argv)
    owner_sha, clip_sha = sha256(args.owner), sha256(args.clip)
    stem = args.cache/f'hand-{owner_sha[:12]}-{clip_sha[:12]}-r{args.radius:g}'
    if not stem.with_suffix('.json').exists():
        args.cache.mkdir(parents=True, exist_ok=True)
        export_hand(args.owner, args.clip, stem, args.radius, args.pose_time)
    hand = HandExport(stem)
    if hand.meta['owner']['sha256'] != owner_sha or hand.meta['clip']['sha256'] != clip_sha:
        raise ValueError('Cached export does not match the exact owner/clip bytes')
    phone = load_phone(args.phone)
    eye = MIRROR@np.array(UE_EYE_HEAD_LOCAL)
    ev = Evaluator(hand, phone, eye, args.pose_time, max_correction_deg=args.max_correction_deg)
    result = {'schema': SCHEMA, 'verified': False, 'requires_native_reaudit': True, 'visual_accepted': False,
              'owner': {'path': str(args.owner), 'sha256': owner_sha, 'vertices_skinned': hand.meta['owner']['vertices']},
              'clip': {'path': str(args.clip), 'sha256': clip_sha, 'duration': hand.meta['clip']['duration'], 'frames': len(hand.times)},
              'phone': phone, 'eye_head_local_gltf_cm': eye.tolist(), 'pose_time': args.pose_time,
              'export_radius_cm': args.radius, 'contact_band_cm': ev.band, 'penetration_tolerance_cm': ev.tol,
              'native_parity': native_parity(hand, ev.pose),
              'unchanged': {'bones': True, 'finger_rotations': True, 'bone_lengths': True, 'clip_values': True, 'phone_parts_relative': True},
              'arm_ik': {'kind': 'bounded orientation-preserving two-bone (RightArm/RightForeArm) wrist translation',
                         'limit_cm': ev.ik_limit, 'body_clearance_cm': ev.clear, 'upper_cm': round(ev.upper, 4), 'lower_cm': round(ev.lower, 4),
                         'preserves': 'right-hand world rotation, all finger local rotations, bone lengths',
                         'note': 'IK moves hand and phone together, so hand-phone residuals are invariant; it only clears body skin. '
                                 'Hand-vs-body skin after the move and forearm skin re-deformation are not re-skinned here; root re-audits natively.'}}
    if args.evaluate_gltf:
        cand = json.loads(Path(args.evaluate_gltf).read_text())
        R, t = quat_to_matrix(cand['quaternion_xyzw']), np.array(cand['offset_cm'], float)
        ev.set_correction(quat_to_matrix(cand.get('correction_xyzw', [0, 0, 0, 1])))
        rows = parallel_residuals(ev, R, t, args.occlusion_stride, args.workers)
        result['candidates'] = [candidate_record(ev, R, t, cand.get('label', 'evaluated'), rows)]
        result['candidates'][0]['provenance'] = cand.get('provenance')
        result['candidates'][0]['thumb_screen_track'] = thumb_screen_track(ev, R, t)
        result['frames'] = rows
    elif args.evaluate_ue:
        off, rot = args.evaluate_ue.split('|')
        o = [float(p.split('=')[1]) for p in off.split()]
        r = {k: float(v) for k, v in (p.split('=') for p in rot.split())}
        t, R = ue_to_gltf_local(o, r['P'], r['Y'], r['R'])
        rows = parallel_residuals(ev, R, t, args.occlusion_stride, args.workers)
        result['candidates'] = [candidate_record(ev, R, t, 'evaluated', rows)]
        result['frames'] = rows
    else:
        frames = sorted(set(range(0, len(hand.times), args.frame_stride)) | {ev.pose})
        refined = search(ev, frames, starts=args.starts, workers=args.workers, correction=args.wrist_correction,
                         kinds=tuple(args.seed_set.split(',')))
        result['candidates'] = []
        for rank, (c, x) in enumerate(refined[:args.top]):
            R, t = rotvec_to_matrix(x[:3]), x[3:6]
            ev.set_correction(rotvec_to_matrix(x[6:9]) if len(x) > 6 else np.eye(3))
            rows = parallel_residuals(ev, R, t, args.occlusion_stride, args.workers)
            rec = candidate_record(ev, R, t, f'rank{rank}', rows)
            rec['search_cost'] = round(float(c), 6)
            result['candidates'].append(rec)
            if rank == 0:
                result['frames'] = rows
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1)+'\n')
    best = result['candidates'][0]
    print(json.dumps({'ue': best['ue_wrist_local']['phoneGripCandidate'], 'summary': best['fullframe_summary']}, indent=1))


if __name__ == '__main__':
    sys.exit(main())
