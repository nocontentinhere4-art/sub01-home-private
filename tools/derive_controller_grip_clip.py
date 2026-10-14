"""TRIAL derived controller-grip clip from the REAL Gaming capture (label: derived_from_capture). verified: false.

Input: docs/proposed/controller-capture/gaming-owner.glb (owner-skeleton retarget of the owner's Mixamo Gaming.fbx).
Output: docs/proposed/controller-play/SUB01_GamingGrip_derived.glb + a per-frame report.

The derivation (no codec, no new geometry):
* ONE fixed controller offset X in the right Hand socket (controller -> right hand) and one left grip G_L; per frame the
  controller sits at the rigid midpoint of where each captured hand would hold it, and both arms are re-solved by
  analytic two-bone IK (LeftArm/LeftForeArm and RightArm/RightForeArm rotations, the Hand local re-derived so the hand
  reaches its grip). Translations are untouched, so every bone length is exact. Clavicles, spine, neck and head are
  untouched (nothing above the shoulders changes).
* Fingers: the captured finger local rotations are the BASE. A bounded per-joint delta is ADDED (post-multiplied in the
  joint's own frame): one curl angle per finger joint chain and one spread angle on joint 1, each |delta| <= 15 deg,
  constant over the clip (so it is smooth and the captured thumb/index variation is preserved exactly as variation).
* Non-penetration: palm and finger skin no deeper than the existing -0.3 cm band, no compression beyond it, measured
  with the exact winding-number distance on every hand vertex in every frame.

    python tools/derive_controller_grip_clip.py [--out-glb ...] [--out-report ...] [--frames-sample N]

`all_frames_pass` is true only when EVERY frame passes every gate; it never claims native contact.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import fit_controller_grip as F  # noqa: E402
import life_gltf as G  # noqa: E402

CLIP = ROOT / 'docs/proposed/controller-capture/gaming-owner.glb'
OUT_GLB = ROOT / 'docs/proposed/controller-play/SUB01_GamingGrip_derived.glb'
OUT_REPORT = ROOT / 'docs/proposed/controller-play/SUB01_GamingGrip_derived.report.json'
SEARCH = ROOT / 'docs/proposed/controller-play/controller-search-contact.summary.json'
LABEL = 'derived_from_capture'
SCHEMA = 'sub01.controller-grip-derived.v1'
FINGER_DELTA_MAX_DEG = 15.0
IK_BOUND_CM, IK_BOUND_DEG = F.IK_BOUND_CM, F.IK_BOUND_DEG
FINGERS = F.FINGERS


# ================================================================ quaternion helpers (x, y, z, w), vectorised
def q_to_m(q):
    q = np.asarray(q, float)
    x, y, z, w = (q[..., i] for i in range(4))
    return np.stack([np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], -1),
                     np.stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], -1),
                     np.stack([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], -1)], -2)


def m_to_q(R):
    R = np.asarray(R, float)
    flat = R.reshape(-1, 3, 3)
    out = np.zeros((len(flat), 4))
    for i, m in enumerate(flat):
        t = np.trace(m)
        if t > 0:
            s = math.sqrt(t + 1) * 2
            out[i] = [(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, s / 4]
        else:
            k = int(np.argmax(np.diag(m)))
            j, l = (k + 1) % 3, (k + 2) % 3
            s = math.sqrt(max(1e-12, 1 + m[k, k] - m[j, j] - m[l, l])) * 2
            q = np.zeros(4)
            q[k], q[j], q[l], q[3] = s / 4, (m[j, k] + m[k, j]) / s, (m[l, k] + m[k, l]) / s, (m[l, j] - m[j, l]) / s
            out[i] = q
    out /= np.linalg.norm(out, axis=1, keepdims=True)
    return out.reshape(R.shape[:-2] + (4,))


def q_mul(a, b):
    ax, ay, az, aw = (a[..., i] for i in range(4))
    bx, by, bz, bw = (b[..., i] for i in range(4))
    return np.stack([aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz], -1)


def q_axis(axis, deg):
    axis = np.asarray(axis, float) / np.linalg.norm(axis)
    h = math.radians(deg) / 2
    return np.array([*(axis * math.sin(h)), math.cos(h)])


def rot_between(a, b):
    """(F,3,3) minimal rotations taking directions a to b."""
    a = a / np.linalg.norm(a, axis=-1, keepdims=True)
    b = b / np.linalg.norm(b, axis=-1, keepdims=True)
    v = np.cross(a, b)
    c = (a * b).sum(-1)
    K = np.zeros(a.shape[:-1] + (3, 3))
    K[..., 0, 1], K[..., 0, 2], K[..., 1, 0], K[..., 1, 2], K[..., 2, 0], K[..., 2, 1] = -v[..., 2], v[..., 1], v[..., 2], -v[..., 0], -v[..., 1], v[..., 0]
    return np.eye(3) + K + K @ K * (1 / (1 + c))[..., None, None]


def unit_rot(M):
    R = M[..., :3, :3]
    return R / np.linalg.norm(R[..., :, 0], axis=-1)[..., None, None]


# ================================================================ the clip as editable local TRS
class Clip:
    def __init__(self, path=CLIP):
        self.path = Path(path)
        self.g = G.Gltf(path)
        self.anim = self.g.animation()
        self.times = np.array(self.anim.key_times())
        n = len(self.g.nodes)
        self.t = np.zeros((len(self.times), n, 3))
        self.q = np.zeros((len(self.times), n, 4))
        self.s = np.zeros((len(self.times), n))
        for i in range(n):
            rt, rq, rs = self.g.rest(i)
            for f, t in enumerate(self.times):
                self.t[f, i] = self.anim.sample(i, 'translation', t, rt)
                self.q[f, i] = G.qnorm(self.anim.sample(i, 'rotation', t, rq))
                self.s[f, i] = np.mean(self.anim.sample(i, 'scale', t, rs))
        self.order, seen = [], set()

        def visit(i):
            if i in seen:
                return
            if i in self.g.parent:
                visit(self.g.parent[i])
            seen.add(i)
            self.order.append(i)
        for i in range(n):
            visit(i)
        self.index = {}
        for i, nd in enumerate(self.g.nodes):
            if nd.get('name', '').startswith('mixamorig'):
                self.index.setdefault(F.canon(nd['name']), i)

    def worlds(self, q=None):
        q = self.q if q is None else q
        L = np.zeros(q.shape[:2] + (4, 4))
        L[..., :3, :3] = q_to_m(q) * self.s[..., None, None]
        L[..., :3, 3] = self.t
        L[..., 3, 3] = 1
        W = np.zeros_like(L)
        for i in self.order:
            W[:, i] = W[:, self.g.parent[i]] @ L[:, i] if i in self.g.parent else L[:, i]
        return W

    def joint_worlds(self, names, W):
        return W[:, [self.index[n] for n in names]]


# ================================================================ edits
def finger_axes(clip: Clip, hands: F.Hands):
    """Per finger joint: curl and spread axes in the joint's OWN local frame (from the owner bind pose)."""
    bind = np.linalg.inv(hands.ibm)
    J = {n: k for k, n in enumerate(hands.names)}
    out = {}
    for side in ('Left', 'Right'):
        pos = lambda n: bind[J[n], :3, 3]  # noqa: E731
        axis = pos(f'{side}HandMiddle1') - pos(f'{side}Hand')
        lateral = pos(f'{side}HandIndex1') - pos(f'{side}HandPinky1')
        normal = np.cross(axis, lateral) * (-1 if side == 'Right' else 1)
        normal /= np.linalg.norm(normal)
        for f in FINGERS:
            for k in (1, 2, 3):
                n = f'{side}Hand{f}{k}'
                child = f'{side}Hand{f}{k + 1}'
                bone = pos(child) - pos(n)
                curl = np.cross(bone, normal)
                curl /= np.linalg.norm(curl)
                Rw = bind[J[n], :3, :3] / np.linalg.norm(bind[J[n], :3, 0])
                # sign: positive curl must move the child toward the palm side
                moved = rotvec(curl, .1) @ bone
                if (moved - bone) @ normal < 0:
                    curl = -curl
                out[n] = {'curl_local': Rw.T @ curl, 'spread_local': Rw.T @ normal}
    return out


def rotvec(axis, angle):
    return F.rotvec_to_matrix(np.asarray(axis) * angle)


def apply_finger_deltas(q, clip: Clip, axes, deltas):
    """deltas: {'Left'/'Right': {finger: (curl_deg, spread_deg)}} -> new local q (curl on joints 1-3, spread on 1)."""
    q = q.copy()
    per_joint = {}
    nf = len(q)
    for side, fingers in deltas.items():
        for f, (curl, spread) in fingers.items():
            curl = np.broadcast_to(np.asarray(curl, float), (nf,))
            spread = np.broadcast_to(np.asarray(spread, float), (nf,))
            for k in (1, 2, 3):
                n = f'{side}Hand{f}{k}'
                i = clip.index[n]
                d = q_axis_v(axes[n]['curl_local'], curl)
                if k == 1:
                    d = q_mul(d, q_axis_v(axes[n]['spread_local'], spread))
                q[:, i] = q_mul(q[:, i], d)
                per_joint[n] = {'curl_deg': curl.copy(), 'spread_deg': spread.copy() if k == 1 else np.zeros(nf)}
    return q, per_joint


def q_axis_v(axis, deg):
    axis = np.asarray(axis, float) / np.linalg.norm(axis)
    h = np.radians(np.asarray(deg, float)) / 2
    return np.concatenate([axis[None] * np.sin(h)[:, None], np.cos(h)[:, None]], 1)


def solve_arm(clip: Clip, q, W, side, target):
    """Two-bone IK on {side}Arm/{side}ForeArm and the Hand local so the Hand bone reaches target (F,4,4) rigid."""
    A, Fa, H = (clip.index[f'{side}{b}'] for b in ('Arm', 'ForeArm', 'Hand'))
    P = clip.g.parent[A]
    S, E, Wr = W[:, A, :3, 3], W[:, Fa, :3, 3], W[:, H, :3, 3]
    Tp = target[:, :3, 3]
    a, b = np.linalg.norm(E - S, axis=1), np.linalg.norm(Wr - E, axis=1)
    d_vec = Tp - S
    d = np.linalg.norm(d_vec, axis=1)
    reach = (d <= a + b) & (d >= np.abs(a - b))
    dc = np.clip(d, np.abs(a - b) + 1e-9, a + b - 1e-9)
    u = d_vec / d[:, None]
    pole = (E - S) - ((E - S) * u).sum(1)[:, None] * u
    pole /= np.linalg.norm(pole, axis=1)[:, None]
    x = (a * a - b * b + dc * dc) / (2 * dc)
    h = np.sqrt(np.maximum(0, a * a - x * x))
    E2 = S + u * x[:, None] + pole * h[:, None]
    R1 = rot_between(E - S, E2 - S)
    Rarm = R1 @ unit_rot(W[:, A])
    q = q.copy()
    q[:, A] = m_to_q(np.swapaxes(unit_rot(W[:, P]), 1, 2) @ Rarm)
    Wr1 = S + np.einsum('fij,fj->fi', R1, Wr - S)
    R2 = rot_between(Wr1 - E2, Tp - E2)
    Rfa = R2 @ R1 @ unit_rot(W[:, Fa])
    q[:, Fa] = m_to_q(np.swapaxes(Rarm, 1, 2) @ Rfa)
    q[:, H] = m_to_q(np.swapaxes(Rfa, 1, 2) @ unit_rot(target))
    return q, reach


# ================================================================ evaluation
class Derivation:
    def __init__(self, clip=CLIP, controller=None, cache=F.CACHE):
        self.clip = Clip(clip)
        self.hands = F.Hands.from_owner(cache=cache)
        path, self.csrc = (Path(controller), {'used': 'explicit', 'sha256': F.sha256(controller)}) if controller else F.controller_source()
        self.mesh, self.cinfo = F.load_controller(path, cache)
        self.feats = F.controller_features(self.mesh)
        self.tg = F.targets(self.feats)
        self.sdf = F.SDFGrid(self.mesh, spacing=.002, margin=.02, cache=cache, key=self.cinfo['sha256'][:16])
        self.axes = finger_axes(self.clip, self.hands)
        self.W0 = self.clip.worlds()
        self.J0 = self.clip.joint_worlds(self.hands.names, self.W0)
        self.names = self.hands.names
        self.jx = {n: k for k, n in enumerate(self.names)}

    def hand_frames(self, J):
        return {s: np.stack([F.rigid(m) for m in J[:, self.jx[f'{s.capitalize()}Hand']]]) for s in ('left', 'right')}

    def build(self, X, GL, deltas, frames=None):
        """Edited local q for (fixed X = controller in right hand, GL = controller in left hand, finger deltas)."""
        clip = self.clip
        q = clip.q if frames is None else clip.q[frames]
        sub = copy.copy(clip)
        if frames is not None:
            sub.q, sub.t, sub.s = clip.q[frames], clip.t[frames], clip.s[frames]
        q, per_joint = apply_finger_deltas(q, sub, self.axes, deltas)
        W = sub.worlds(q)
        J = sub.joint_worlds(self.names, W)
        hf = self.hand_frames(J)
        C = np.stack([F.blend(hf['right'][f] @ X, hf['left'][f] @ GL) for f in range(len(q))])
        targets = {'right': C @ np.linalg.inv(X), 'left': C @ np.linalg.inv(GL)}
        reach = {}
        for side in ('Right', 'Left'):
            q, reach[side.lower()] = solve_arm(sub, q, W, side, targets[side.lower()])
            W = sub.worlds(q)
        J = sub.joint_worlds(self.names, W)
        return q, W, J, C, targets, hf, reach, per_joint

    def side_cost(self, side, Gs, deltas, frames, sub=3, aim=(.5, .3)):
        """Contact cost of one hand in its own frame: depends only on its grip and finger deltas (IK is rigid on the hand)."""
        sub_clip = copy.copy(self.clip)
        sub_clip.q, sub_clip.t, sub_clip.s = self.clip.q[frames], self.clip.t[frames], self.clip.s[frames]
        q, _ = apply_finger_deltas(sub_clip.q, sub_clip, self.axes, {side.capitalize(): deltas})
        J = sub_clip.joint_worlds(self.names, sub_clip.worlds(q))
        H = np.stack([F.rigid(m) for m in J[:, self.jx[f'{side.capitalize()}Hand']]])
        costs = []
        for f in range(len(frames)):
            loc = {k: F.apply(np.linalg.inv(H[f]), v) for k, v in
                   ((k[len(side) + 1:], self.hands.skin(k, J[f:f + 1])[0]) for k in self.hands.sets if k.startswith(side + '_'))}
            costs.append(F.grip_cost(self.sdf, self.tg, side, loc, Gs, sub=sub, aim=aim))
        return float(np.mean(costs) + np.max(costs))      # every frame matters, not only the average

    def metrics(self, J, C):
        sets = {k: self.hands.skin(k, J) for k in self.hands.sets}
        prob = F.Problem(self.mesh, self.feats, None, sets)
        return [prob.metrics(C[f], f) for f in range(len(C))]


def optimise(d: Derivation, frames, rounds=3, iters=300, log=print):
    """Fixed grips + constant bounded finger deltas, penetration first; returns X, GL, deltas."""
    search = json.loads(SEARCH.read_text()) if SEARCH.exists() else None
    if search:
        X = np.array(F.grip_variation(search['per_frame'], 'right')['mean_controller_in_hand'])
        GL = np.array(F.grip_variation(search['per_frame'], 'left')['mean_controller_in_hand'])
    else:
        hf = d.hand_frames(d.J0)
        sets = {k: d.hands.skin(k, d.J0) for k in d.hands.sets}
        X = F.solve_hand(d.mesh, d.feats, hf['right'], sets, 'right', frames, d.sdf)
        GL = F.solve_hand(d.mesh, d.feats, hf['left'], sets, 'left', frames, d.sdf)
    grips = {'right': X, 'left': GL}
    deltas = {s: {f: [0., 0.] for f in FINGERS} for s in ('right', 'left')}
    lim = FINGER_DELTA_MAX_DEG

    def unpack(p):
        return {f: (float(np.clip(p[2 * i], -lim, lim)), float(np.clip(p[2 * i + 1], -lim, lim))) for i, f in enumerate(FINGERS)}
    for r in range(rounds):
        for side in ('right', 'left'):
            g, _ = F.nelder_mead(lambda p: d.side_cost(side, F.pose(p), unpack(np.ravel(list(deltas[side].values()))), frames),
                                 F.params_of(grips[side]), [.04, .04, .04, .004, .004, .004], iters)
            grips[side] = F.pose(g)
            x, v = F.nelder_mead(lambda p: d.side_cost(side, grips[side], unpack(p), frames) + .002 * float((np.asarray(p) ** 2).sum()),
                                 np.ravel(list(deltas[side].values())), [4.] * 10, iters)
            deltas[side] = {f: list(v_) for f, v_ in unpack(x).items()}
            log(f'round {r} {side}: cost {v:.4f} deltas {deltas[side]}')
    return grips['right'], grips['left'], {s.capitalize(): {f: tuple(v) for f, v in deltas[s].items()} for s in deltas}


REFINE_KEY_STEP = 4            # per-frame refinement keys every 4 frames, linearly interpolated, then temporally filtered
SMOOTH_SIGMA_FRAMES = 2.0
MAX_DELTA_RATE_DEG_PER_FRAME = 1.5
REFINE_AIM = (4., 3.)          # refinement pulls thumbs/index toward their gates harder than the contact-first base


def gaussian_smooth(x, sigma):
    r = int(3 * sigma)
    k = np.exp(-.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    pad = np.pad(x, (r, r), mode='wrap')            # the clip loops: filter across the seam
    return np.convolve(pad, k, mode='valid')


def refine(d: Derivation, grips, base, iters=150, log=print):
    """Smooth per-frame finger delta keys on top of the constant base, bounded to |base + extra| <= 15 deg.

    Keys every REFINE_KEY_STEP frames are optimised on the frames around them, linearly interpolated, Gaussian
    filtered (sigma SMOOTH_SIGMA_FRAMES) and clipped; the captured variation stays (the delta is added)."""
    nf = len(d.clip.times)
    keys = list(range(0, nf, REFINE_KEY_STEP)) + ([nf - 1] if (nf - 1) % REFINE_KEY_STEP else [])
    lim = FINGER_DELTA_MAX_DEG
    out = {}
    for side in ('right', 'left'):
        S = side.capitalize()
        b = np.array([base[S][f] for f in FINGERS], float).ravel()          # 10 params
        extra = np.zeros((len(keys), 10))
        prev = np.zeros(10)
        for n, k in enumerate(keys):
            near = sorted({max(0, k - 1), k, min(nf - 1, k + 1)})

            def cost(p):
                tot = np.clip(b + p, -lim, lim)
                dl = {f: (float(tot[2 * i]), float(tot[2 * i + 1])) for i, f in enumerate(FINGERS)}
                return d.side_cost(side, grips[side], dl, near, sub=2, aim=REFINE_AIM) + .01 * float(((p - prev) ** 2).sum()) + .002 * float((p ** 2).sum())
            x, v = F.nelder_mead(cost, prev, [3.] * 10, iters)
            extra[n] = np.clip(b + x, -lim, lim) - b
            prev = extra[n]
        # periodic keys: the last frame takes the first key's value, so the loop seam stays continuous
        kx = np.array(keys[:-1] + [nf - 1]) if keys[-1] == nf - 1 else np.array(keys + [nf - 1])
        ky = np.vstack([extra[:len(kx) - 1], extra[:1]])
        dense = np.stack([np.interp(np.arange(nf), kx, ky[:, j]) for j in range(10)], 1)
        dense = np.stack([gaussian_smooth(dense[:, j], SMOOTH_SIGMA_FRAMES) for j in range(10)], 1)
        tot = np.clip(b[None] + dense, -lim, lim)
        out[S] = {f: (tot[:, 2 * i], tot[:, 2 * i + 1]) for i, f in enumerate(FINGERS)}
        log(f'refine {side}: max |extra| {np.abs(dense).max():.2f} deg, max rate {np.abs(np.diff(tot, axis=0)).max():.3f} deg/frame')
    return out


PATCH_SIGMA_FRAMES = 3.0


def deltas_from_report(report):
    """Exact per-frame (curl, spread) arrays per finger from a derived report (curl is shared by joints 1-3)."""
    pj = report['finger_deltas_deg']['per_joint_per_frame']
    return {S: {f: (np.array(pj[f'{S}Hand{f}1']['curl_deg']), np.array(pj[f'{S}Hand{f}1']['spread_deg'])) for f in FINGERS}
            for S in ('Right', 'Left')}


def patch(d: Derivation, grips, deltas, bad, iters=300, log=print):
    """Local smooth bump (Gaussian window, sigma PATCH_SIGMA_FRAMES, periodic) of the finger deltas around failing frames,
    optimised on the failing frames and their neighbours with a stricter penetration margin; bounds kept."""
    nf = len(d.clip.times)
    out = {S: {f: (np.array(c, float), np.array(sp, float)) for f, (c, sp) in fs.items()} for S, fs in deltas.items()}
    centre = int(round(np.mean(bad)))
    t = np.arange(nf)
    dist = np.minimum(np.abs(t - centre), nf - np.abs(t - centre))
    window = np.exp(-.5 * (dist / PATCH_SIGMA_FRAMES) ** 2)
    near = sorted({(b + k) % nf for b in bad for k in (-2, -1, 0, 1, 2)})
    lim = FINGER_DELTA_MAX_DEG
    for side in ('right', 'left'):
        S = side.capitalize()

        def at(p, frames):
            res = {}
            for i, f in enumerate(FINGERS):
                c, sp = out[S][f]
                res[f] = (np.clip(c + p[2 * i] * window, -lim, lim)[frames], np.clip(sp + p[2 * i + 1] * window, -lim, lim)[frames])
            return res

        def cost(p):
            tot = 0.
            for fr in near:
                dl = {f: (float(c[0]), float(sp[0])) for f, (c, sp) in at(p, [fr]).items()}
                tot = max(tot, d.side_cost(side, grips[side], dl, [fr], sub=1, aim=REFINE_AIM))
            return tot + .002 * float((np.asarray(p) ** 2).sum())
        x0 = np.zeros(10)
        base_cost = cost(x0)
        x, v = F.nelder_mead(cost, x0, [2.] * 10, iters)
        if v < base_cost:
            for i, f in enumerate(FINGERS):
                c, sp = out[S][f]
                out[S][f] = (np.clip(c + x[2 * i] * window, -lim, lim), np.clip(sp + x[2 * i + 1] * window, -lim, lim))
        log(f'patch {side} around frame {centre}: cost {base_cost:.4f} -> {min(v, base_cost):.4f}')
    return out


def bound_report(d: Derivation, hf, targets, reach):
    rows = []
    for f in range(len(targets['right'])):
        row = {}
        for side in ('left', 'right'):
            move = float(100 * np.linalg.norm(targets[side][f][:3, 3] - hf[side][f][:3, 3]))
            turn = float(F.angle_deg(targets[side][f][:3, :3], hf[side][f][:3, :3]))
            row[side] = {'wrist_displacement_cm': move, 'wrist_rotation_deg': turn, 'reachable': bool(reach[side][f]),
                         'within_bound': bool(reach[side][f] and move <= IK_BOUND_CM and turn <= IK_BOUND_DEG)}
        rows.append(row)
    return rows


def seam(q0, q1, names_idx):
    """Largest joint rotation jump (deg) between last and first frame (loop seam)."""
    return float(max(G.qangle_deg(tuple(q0[i]), tuple(q1[i])) for i in names_idx))


def derive(clip=CLIP, controller=None, sample=10, rounds=3, iters=300, log=print, refine_iters=150, start=None, reopt=(), patch_from=None, patch_frames=()):
    d = Derivation(clip, controller)
    nfr = len(d.clip.times)
    frames = list(np.unique(np.linspace(0, nfr - 1, sample).astype(int)))
    if patch_from:
        # Keep a previous derivation exactly (offset, grip, every per-frame delta) and patch only around failing frames.
        X, GL = np.array(patch_from['fixed_offset']['controller_in_right_hand_gltf']), np.array(patch_from['left_grip_gltf'])
        base = {S: {f: tuple(v) for f, v in fs.items()} for S, fs in patch_from['base_finger_deltas_deg'].items()}
        deltas = patch(d, {'right': X, 'left': GL}, deltas_from_report(patch_from), list(patch_frames), iters, log)
        refine_iters, reopt = 0, ()
    elif start:
        X, GL = np.array(start['fixed_offset']['controller_in_right_hand_gltf']), np.array(start['left_grip_gltf'])
        deltas = {S: {f: tuple(v) for f, v in fs.items()} for S, fs in start['base_finger_deltas_deg'].items()}
    else:
        X, GL, deltas = optimise(d, frames, rounds, iters, log)
    if not patch_from:
        base = deltas
    grips = {'right': X, 'left': GL}
    for side in reopt:                  # re-seat a fixed grip with the stronger thumb/index pull (still one fixed offset)
        S = side.capitalize()
        g, v = F.nelder_mead(lambda p: d.side_cost(side, F.pose(p), base[S], frames, sub=2, aim=REFINE_AIM),
                             F.params_of(grips[side]), [.03, .03, .03, .003, .003, .003], iters)
        grips[side] = F.pose(g)
        log(f'reopt {side} grip: cost {v:.4f}')
    X, GL = grips['right'], grips['left']
    if refine_iters:
        deltas = refine(d, {'right': X, 'left': GL}, base, refine_iters, log)
    q, W, J, C, targets, hf0, reach, per_joint = d.build(X, GL, deltas)
    hf_after = d.hand_frames(J)
    rows = d.metrics(J, C)
    bounds = bound_report(d, d.hand_frames(d.J0), targets, reach)
    # fixed offset check: the controller relative to the DERIVED right Hand socket in every frame
    off = [np.linalg.inv(hf_after['right'][f]) @ C[f] for f in range(nfr)]
    var_t = max(float(100 * np.linalg.norm(o[:3, 3] - X[:3, 3])) for o in off)
    var_r = max(float(F.angle_deg(o[:3, :3], X[:3, :3])) for o in off)
    # bone lengths / unchanged upper body
    bl = []
    for n, i in d.clip.index.items():
        p = d.clip.g.parent.get(i)
        if p is None or not d.clip.g.nodes[p].get('name', '').startswith('mixamorig'):
            continue
        L0 = np.linalg.norm(d.W0[:, i, :3, 3] - d.W0[:, p, :3, 3], axis=1)
        L1 = np.linalg.norm(W[:, i, :3, 3] - W[:, p, :3, 3], axis=1)
        bl.append(float(np.abs(L1 - L0).max()))
    upper = [d.clip.index[n] for n in ('Hips', 'Spine', 'Spine1', 'Spine2', 'Neck', 'Head', 'HeadTop_End', 'LeftShoulder', 'RightShoulder')]
    upper_err = float(np.abs(W[:, upper] - d.W0[:, upper]).max())
    edited = sorted({d.clip.index[n] for n in per_joint} | {d.clip.index[f'{s}{b}'] for s in ('Left', 'Right') for b in ('Arm', 'ForeArm', 'Hand')})
    per_frame = []
    for f in range(nfr):
        r = rows[f]
        ok = r['grip'] and bounds[f]['left']['within_bound'] and bounds[f]['right']['within_bound']
        th_idx = all(min(r[s]['thumb_to_target_cm'].values()) <= F.THUMB_GATE_CM and r[s]['index_to_trigger_cm'] <= F.INDEX_GATE_CM for s in ('left', 'right'))
        per_frame.append({'frame': f, 'gltf_t': float(d.clip.times[f]), 'native_t': F.native_time(d.clip.times[f]),
                          'pass': bool(ok and th_idx), 'contact_pass': bool(ok), 'thumbs_index_pass': bool(th_idx),
                          **{s: {**{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r[s].items() if not k.endswith('_local_m')},
                                 'thumb_to_target_cm': {k: round(v, 4) for k, v in r[s]['thumb_to_target_cm'].items()},
                                 **{k: round(v, 4) if isinstance(v, float) else v for k, v in bounds[f][s].items()}} for s in ('left', 'right')}})
    # captured finger variation preserved: delta constant -> local angle path identical up to the constant offset
    var = {}
    for n in per_joint:
        i = d.clip.index[n]
        a0 = [G.qangle_deg(tuple(d.clip.q[0, i]), tuple(d.clip.q[f, i])) for f in range(nfr)]
        a1 = [G.qangle_deg(tuple(q[0, i]), tuple(q[f, i])) for f in range(nfr)]
        var[n] = {'captured_amplitude_deg': round(max(a0), 4), 'derived_amplitude_deg': round(max(a1), 4)}
    passing = sum(p['pass'] for p in per_frame)
    report = {'schema': SCHEMA, 'label': LABEL, 'verified': False, 'trial': True,
              'source_clip': {'file': str(Path(clip).relative_to(ROOT)), 'sha256': d.clip.g.sha256,
                              'source_fbx_sha256': 'declared by root: 84dfc60ab9e13b9c896e89def81478a5e47f45b80cc3d8902c5b8a0ae8d8fc7f'},
              'controller': dict(d.cinfo, source=d.csrc, width_cm=float(100 * (d.mesh.hi[0] - d.mesh.lo[0])), oversized=False),
              'frames': nfr, 'frames_passing': int(passing), 'frames_contact_pass': int(sum(p['contact_pass'] for p in per_frame)),
              'frames_thumbs_index_pass': int(sum(p['thumbs_index_pass'] for p in per_frame)),
              'all_frames_pass': bool(passing == nfr), 'status': 'all_frames_pass' if passing == nfr else 'partial',
              'failing_frames': [p['frame'] for p in per_frame if not p['pass']],
              'gates': {'palm_band_cm': F.PALM_BAND_CM, 'penetration_limit_cm': F.PENETRATION_LIMIT_CM, 'compression_allowance_beyond_band_cm': 0,
                        'min_support_vertices': F.MIN_SUPPORT_VERTICES, 'thumb_cm': F.THUMB_GATE_CM, 'index_cm': F.INDEX_GATE_CM,
                        'ik_bound': {'wrist_displacement_cm': IK_BOUND_CM, 'wrist_rotation_deg': IK_BOUND_DEG},
                        'finger_delta_max_deg': FINGER_DELTA_MAX_DEG, 'fixed_offset_tolerance': [.3, 1.]},
              'fixed_offset': {'controller_in_right_hand_gltf': X.tolist(), 'max_translation_cm': var_t, 'max_rotation_deg': var_r,
                               'holds': bool(var_t <= .3 and var_r <= 1.)},
              'left_grip_gltf': GL.tolist(),
              'base_finger_deltas_deg': {S: {f: [float(np.mean(v[0])), float(np.mean(v[1]))] for f, v in fs.items()} for S, fs in base.items()},
              'finger_deltas_deg': {'rule': 'constant base + smooth per-frame keys (every %d frames, Gaussian sigma %.1f), added to the captured local rotation' % (REFINE_KEY_STEP, SMOOTH_SIGMA_FRAMES)
                                    + ('; plus a local periodic Gaussian bump (sigma %.1f frames) around frames %s' % (PATCH_SIGMA_FRAMES, list(patch_frames)) if patch_from else '')
                                    if (refine_iters or patch_from) else 'constant per joint over the clip, added to the captured local rotation',
                                    'max_abs_deg': float(max(max(np.abs(v['curl_deg']).max(), np.abs(v['spread_deg']).max()) for v in per_joint.values())),
                                    'max_rate_deg_per_frame': float(max(max(np.abs(np.diff(v['curl_deg'])).max(), np.abs(np.diff(v['spread_deg'])).max()) for v in per_joint.values())),
                                    'per_joint_per_frame': {n: {'curl_deg': [round(float(x), 4) for x in v['curl_deg']], 'spread_deg': [round(float(x), 4) for x in v['spread_deg']]}
                                                            for n, v in per_joint.items()}},
              'captured_finger_variation': var,
              'bone_length_max_error_cm': 100 * max(bl), 'upper_body_max_world_change': upper_err,
              'loop_seam_max_jump_deg': {'captured': seam(d.clip.q[-1], d.clip.q[0], edited), 'derived': seam(q[-1], q[0], edited)},
              'summary': {s: {'palm_min_gap_cm': [min(p[s]['palm_min_gap_cm'] for p in per_frame), max(p[s]['palm_min_gap_cm'] for p in per_frame)],
                              'hand_min_signed_cm': min(p[s]['hand_min_signed_cm'] for p in per_frame),
                              'frames_penetrating': sum(1 for p in per_frame if p[s]['hand_vertices_penetrating']),
                              'thumb_to_target_cm': [min(min(p[s]['thumb_to_target_cm'].values()) for p in per_frame), max(min(p[s]['thumb_to_target_cm'].values()) for p in per_frame)],
                              'index_to_trigger_cm': [min(p[s]['index_to_trigger_cm'] for p in per_frame), max(p[s]['index_to_trigger_cm'] for p in per_frame)],
                              'max_wrist_displacement_cm': max(p[s]['wrist_displacement_cm'] for p in per_frame),
                              'max_wrist_rotation_deg': max(p[s]['wrist_rotation_deg'] for p in per_frame)} for s in ('left', 'right')},
              'per_frame': per_frame}
    return d, q, report


def write_glb(d: Derivation, q, report, out):
    """The source GLB with the edited nodes' rotation samplers replaced (same key times, LINEAR); nothing else changes."""
    raw = d.clip.path.read_bytes()
    doc = copy.deepcopy(d.clip.g.doc)
    binary = bytearray(d.clip.g.buffers[0])
    anim = doc['animations'][0]
    edited = {d.clip.index[n] for n in report['finger_deltas_deg']['per_joint_per_frame']} | {d.clip.index[f'{s}{b}'] for s in ('Left', 'Right') for b in ('Arm', 'ForeArm', 'Hand')}
    by_node = {(c['target']['node'], c['target']['path']): c for c in anim['channels']}
    for i in sorted(edited):
        ch = by_node.get((i, 'rotation'))
        if ch is None:
            raise ValueError(f'no rotation channel on edited node {i}')
        sampler = anim['samplers'][ch['sampler']]
        if doc['accessors'][sampler['input']]['count'] != len(d.clip.times):
            raise ValueError('edited channel key count differs from the clip key times')
        while len(binary) % 4:
            binary.append(0)
        off = len(binary)
        binary += struct.pack('<' + 'f' * (4 * len(q)), *q[:, i].astype(np.float32).ravel())
        doc['bufferViews'].append({'buffer': 0, 'byteOffset': off, 'byteLength': 16 * len(q)})
        doc['accessors'].append({'bufferView': len(doc['bufferViews']) - 1, 'componentType': 5126, 'count': len(q), 'type': 'VEC4'})
        sampler['output'] = len(doc['accessors']) - 1
    doc['buffers'][0]['byteLength'] = len(binary)
    doc['asset']['generator'] = 'SUB01 derived_from_capture controller grip (tools/derive_controller_grip_clip.py), TRIAL verified false'
    doc['asset']['extras'] = {'label': LABEL, 'source_sha256': hashlib.sha256(raw).hexdigest(), 'all_frames_pass': report['all_frames_pass'],
                              'verified': False}
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    return G.write_glb(out, doc, bytes(binary))


def start_from(report):
    """Fixed offset, left grip and constant base deltas of a previous derived report."""
    if 'base_finger_deltas_deg' in report:
        base = report['base_finger_deltas_deg']
    else:
        pj = report['finger_deltas_deg'].get('per_joint') or report['finger_deltas_deg']['per_joint_per_frame']
        val = lambda x: float(np.mean(x))  # noqa: E731
        base = {S: {f: [val(pj[f'{S}Hand{f}1']['curl_deg']), val(pj[f'{S}Hand{f}1']['spread_deg'])] for f in FINGERS} for S in ('Right', 'Left')}
    return {'fixed_offset': report['fixed_offset'], 'left_grip_gltf': report['left_grip_gltf'], 'base_finger_deltas_deg': base}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--clip', default=str(CLIP))
    ap.add_argument('--controller')
    ap.add_argument('--sample', type=int, default=10)
    ap.add_argument('--rounds', type=int, default=3)
    ap.add_argument('--iters', type=int, default=300)
    ap.add_argument('--refine-iters', type=int, default=150, help='0: constant deltas only')
    ap.add_argument('--patch-from', help='a previous derived report to keep exactly, patching only --patch-frames')
    ap.add_argument('--patch-frames', default='', help='comma list of failing frames to patch')
    ap.add_argument('--reopt', default='', help='comma list of sides whose fixed grip is re-optimised with the refinement pull')
    ap.add_argument('--start', help='a previous derived report: reuse its fixed offset, left grip and base deltas')
    ap.add_argument('--out-glb', default=str(OUT_GLB))
    ap.add_argument('--out-report', default=str(OUT_REPORT))
    args = ap.parse_args(argv)
    start = start_from(json.loads(Path(args.start).read_text())) if args.start else None
    d, q, report = derive(Path(args.clip), args.controller, args.sample, args.rounds, args.iters,
                          log=lambda m: print(m, file=sys.stderr, flush=True), refine_iters=args.refine_iters, start=start,
                          reopt=tuple(x for x in args.reopt.split(',') if x),
                          patch_from=json.loads(Path(args.patch_from).read_text()) if args.patch_from else None,
                          patch_frames=tuple(int(x) for x in args.patch_frames.split(',') if x))
    report['output_glb_sha256'] = write_glb(d, q, report, args.out_glb)
    report['output_glb'] = str(Path(args.out_glb).relative_to(ROOT)) if Path(args.out_glb).is_relative_to(ROOT) else args.out_glb
    Path(args.out_report).write_text(json.dumps(report, indent=0) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('per_frame', 'captured_finger_variation')}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
