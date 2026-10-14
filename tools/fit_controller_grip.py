"""TRIAL rigid two-hand controller grip solver (pure Python + numpy). verified: false.

Fits the ACTUAL controller mesh (web/room/controller.glb, CC0, room_build/build_desk_tech.mjs) into the
ACTUAL captured hands of the owner skin (web/room/char_mixamo.glb, decoded once by the existing
tools/uncompress_unreal_glb.mjs + vendored MeshoptDecoder) posed by a captured clip on the owner's
Mixamo skeleton. No codec is written here: GLBs are read with tools/life_gltf.py and the accessor
reader of tools/export_seat_fit_source.py; skinning is the same compact linear-blend operator idea
(fixed bind-space vertex sets, per-frame joint world matrices).

What it does, per clip frame:
* poses only fixed bind-space hand vertex sets (selected ONCE, never per pose):
  - palm patch: {Side}Hand weight >= 0.5 and bind normal facing the palm (palm normal from the
    hand's own bind joints, checked against the thumb tip side);
  - distal thumb / distal index skin: native AnalyzeCapturedFingerSkin rule (Thumb3 / Index3 weight
    >= 0.30 of the vertex);
  - the whole hand (Hand + all finger joints >= 0.5) for collision;
* solves ONE rigid controller transform attached to the right Hand bone with a FIXED offset over the
  whole clip (mode `fixed`), and, separately, a per-frame rigid fit (mode `per_frame`) to measure how
  much a fixed attachment costs when the captured hands move relative to each other;
* measures, never assumes:
  - palm LOCAL SUPPORT PATCH against the controller surface (validate_unreal_seat_contact idea):
    nothing deeper than -0.3 cm (skin compression band), the lowest point within +0.3 cm, and at
    least MIN_SUPPORT_VERTICES palm vertices inside the band;
  - full-hand collision: exact signed distance (exact point-triangle distance; inside/outside by the
    generalized winding number) of every hand vertex, per frame;
  - thumbs vs the measured stick caps / face-button cluster, index fingers vs the triggers;
  - the drift of the left Hand bone in the right Hand bone frame, and the minimal left-arm two-bone
    IK (wrist world orientation and every finger local preserved) that a fixed rigid controller would
    need, reported as a residual (never applied here).

Captured finger motion is retained exactly: nothing here poses a finger or a bone.

    python tools/fit_controller_grip.py controller            # real controller mesh metrics only
    python tools/fit_controller_grip.py fit --clip CLIP.glb [--out REPORT.json] [--stride N]
    python tools/fit_controller_grip.py sofa                  # authored sofa seat (source GLB) metrics

A Mixamo FBX is first converted with the existing room_build/kimodo/mixamo_glb.mjs (nothing renamed or
retargeted). Every result carries verified: false; nothing here accepts a contact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import life_gltf as G  # noqa: E402
from export_seat_fit_source import accessor, decoded, trs  # noqa: E402  (existing readers, no new codec)

SCHEMA = 'sub01.controller-grip-trial.v1'
OWNER = ROOT / 'web/room/char_mixamo.glb'
CONTROLLER = ROOT / 'web/room/controller.glb'
SOFA = ROOT / 'web/house/assets/haven-sofa/sofa.glb'
SOFA_META = ROOT / 'web/house/assets/haven-sofa/sofa.json'
CACHE = ROOT / 'out/seat-fit-cache'

# Contact rule (cm): the seat's local-support-patch idea with a hand skin-compression band.
PALM_BAND_CM = (-.3, .3)
PENETRATION_LIMIT_CM = -.3
MIN_SUPPORT_VERTICES = 12          # provisional, like validate_unreal_seat_contact (tune only from real reports)
REGION_MIN_SHARE = .30             # native distal-finger rule
PALM_MIN_HAND_SHARE = .5
PALM_MIN_FACING = .5
FINGERS = ('Thumb', 'Index', 'Middle', 'Ring', 'Pinky')
# Authoring constants of the controller (room_build/build_desk_tech.mjs, metres, its local frame:
# x across, y up, z toward the player). Used only to NAME regions; positions are re-measured on the mesh.
AUTHORED = {'cap_top_y': .0475 + .0085, 'left_stick': (-.033, -.012), 'right_stick': (.017, .011),
            'dpad': (-.017, .011), 'face_buttons': (.033, -.012),
            'trigger': {'x': .045, 'y': .031, 'z': -.042},
            'grip_axis': ((.043, .034, .004), (.054, .0145, .044)), 'grip_radius': (.019, .0145)}
# Standing capsule of the renderer (Sub01HomeLab: InitCapsuleSize(17, 92)).
CAPSULE_RADIUS_CM, CAPSULE_HALF_HEIGHT_CM = 17., 92.
SOFA_NODE_M = (-2.55, .1)          # home_world.NODES['sofa'] web (x, z): the standing gap in front of the sofa


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canon(name: str) -> str:
    """Mixamo joint identity: 'mixamorig:Hips', 'mixamorigHips', 'mixamorig1:Hips' -> 'Hips'."""
    return re.sub(r'^mixamorig\d*:?', '', str(name))


# ================================================================ rigid math
def rotvec_to_matrix(r):
    r = np.asarray(r, float)
    th = np.linalg.norm(r)
    if th < 1e-12:
        return np.eye(3)
    k = r / th
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * K @ K


def matrix_to_rotvec(R):
    c = max(-1., min(1., (np.trace(R) - 1) / 2))
    th = math.acos(c)
    if th < 1e-9:
        return np.zeros(3)
    if abs(th - math.pi) < 1e-6:
        w, v = np.linalg.eigh((R + R.T) / 2)
        return v[:, np.argmax(w)] * th
    return th / (2 * math.sin(th)) * np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])


def pose(params):
    m = np.eye(4)
    m[:3, :3] = rotvec_to_matrix(params[:3])
    m[:3, 3] = params[3:6]
    return m


def params_of(m):
    return np.concatenate([matrix_to_rotvec(m[:3, :3]), m[:3, 3]])


def rigid(m):
    """Rotation-only (orthonormal, det +1) copy of a possibly scaled 4x4 (bone worlds carry 0.01 scale)."""
    u, _, vt = np.linalg.svd(m[:3, :3])
    r = u @ vt
    if np.linalg.det(r) < 0:
        u[:, -1] *= -1
        r = u @ vt
    out = np.eye(4)
    out[:3, :3], out[:3, 3] = r, m[:3, 3]
    return out


def angle_deg(Ra, Rb):
    return math.degrees(math.acos(max(-1., min(1., (np.trace(Ra.T @ Rb) - 1) / 2))))


def apply(m, p):
    return p @ m[:3, :3].T + m[:3, 3]


def kabsch(src, dst, w=None):
    """Rigid M (4x4) minimising sum w |M src - dst|^2."""
    src, dst = np.asarray(src, float), np.asarray(dst, float)
    w = np.ones(len(src)) if w is None else np.asarray(w, float)
    cs, cd = (w[:, None] * src).sum(0) / w.sum(), (w[:, None] * dst).sum(0) / w.sum()
    H = ((src - cs) * w[:, None]).T @ (dst - cd)
    u, _, vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(vt.T @ u.T)) or 1.
    R = vt.T @ np.diag([1, 1, d]) @ u.T
    m = np.eye(4)
    m[:3, :3], m[:3, 3] = R, cd - R @ cs
    return m


def nelder_mead(f, x0, step, iters=400, tol=1e-10):
    """Plain Nelder-Mead (no scipy available here)."""
    n = len(x0)
    pts = [np.asarray(x0, float)] + [np.asarray(x0, float) + np.eye(n)[i] * step[i] for i in range(n)]
    vals = [f(p) for p in pts]
    for _ in range(iters):
        order = np.argsort(vals)
        pts, vals = [pts[i] for i in order], [vals[i] for i in order]
        if abs(vals[-1] - vals[0]) <= tol * (1 + abs(vals[0])):
            break
        c = np.mean(pts[:-1], axis=0)
        xr = c + (c - pts[-1])
        fr = f(xr)
        if fr < vals[0]:
            xe = c + 2 * (c - pts[-1])
            fe = f(xe)
            pts[-1], vals[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = xr, fr
        else:
            xc = c + .5 * (pts[-1] - c)
            fc = f(xc)
            if fc < vals[-1]:
                pts[-1], vals[-1] = xc, fc
            else:
                pts = [pts[0]] + [pts[0] + .5 * (p - pts[0]) for p in pts[1:]]
                vals = [vals[0]] + [f(p) for p in pts[1:]]
    i = int(np.argmin(vals))
    return pts[i], vals[i]


# ================================================================ exact mesh distance
class Mesh:
    """Triangle mesh (metres) with exact unsigned distance and generalized-winding-number inside test."""

    def __init__(self, V, F):
        self.V = np.asarray(V, float)
        self.F = np.asarray(F, int).reshape(-1, 3)
        self.A, self.B, self.C = self.V[self.F[:, 0]], self.V[self.F[:, 1]], self.V[self.F[:, 2]]
        self.centroid = (self.A + self.B + self.C) / 3
        self.radius = np.max(np.stack([np.linalg.norm(x - self.centroid, axis=1) for x in (self.A, self.B, self.C)]), axis=0)
        self.lo, self.hi = self.V.min(0), self.V.max(0)

    def boundary_edges(self):
        e = np.sort(np.concatenate([self.F[:, [0, 1]], self.F[:, [1, 2]], self.F[:, [2, 0]]]), axis=1)
        _, counts = np.unique(e, axis=0, return_counts=True)
        return int((counts == 1).sum()), int((counts > 2).sum())

    @staticmethod
    def _closest(p, a, b, c):
        """Exact closest point on triangles (Ericson, Real-Time Collision Detection 5.1.5), vectorised."""
        ab, ac, ap = b - a, c - a, p - a
        d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
        bp = p - b
        d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
        cp = p - c
        d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
        va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
        denom = va + vb + vc
        denom = np.where(np.abs(denom) < 1e-30, 1e-30, denom)
        v, w = vb / denom, vc / denom
        out = a + ab * v[:, None] + ac * w[:, None]
        sel = lambda m, q: np.where(m[:, None], q, out)  # noqa: E731
        with np.errstate(divide='ignore', invalid='ignore'):
            m = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
            out = sel(m, a + ac * np.nan_to_num(d2 / (d2 - d6))[:, None])
            m = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
            out = sel(m, a + ab * np.nan_to_num(d1 / (d1 - d3))[:, None])
            m = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
            out = sel(m, b + (c - b) * np.nan_to_num((d4 - d3) / ((d4 - d3) + (d5 - d6)))[:, None])
        out = sel((d6 >= 0) & (d5 <= d6), c)
        out = sel((d3 >= 0) & (d4 <= d3), b)
        out = sel((d1 <= 0) & (d2 <= 0), a)
        return out

    def distance_brute(self, P, chunk=96):
        """Exact unsigned distance against every triangle (bounding-sphere pruning); the reference for tests."""
        P = np.asarray(P, float)
        dist, tri = np.full(len(P), np.inf), np.zeros(len(P), int)
        for s in range(0, len(P), chunk):
            p = P[s:s + chunk]
            D = np.linalg.norm(p[:, None, :] - self.centroid[None], axis=2)
            ub = (D + self.radius[None]).min(1)
            pi, ti = np.nonzero(D - self.radius[None] <= ub[:, None])
            dist[s:s + chunk], tri[s:s + chunk] = self._best(p, pi, ti)
        return dist, tri

    def _best(self, p, pi, ti):
        q = self._closest(p[pi], self.A[ti], self.B[ti], self.C[ti])
        d = np.linalg.norm(p[pi] - q, axis=1)
        best = np.full(len(p), np.inf)
        np.minimum.at(best, pi, d)
        hit = d <= best[pi] + 1e-15
        bt = np.zeros(len(p), int)
        bt[pi[hit]] = ti[hit]
        return best, bt

    @staticmethod
    def _solid(p, A, B, C):
        """Exact signed solid angles (van Oosterom-Strackee) of triangles A,B,C (T,3) seen from points p (N,3)."""
        a, b, c = A[None] - p[:, None], B[None] - p[:, None], C[None] - p[:, None]
        la, lb, lc = (np.linalg.norm(x, axis=2) for x in (a, b, c))
        num = (a * np.cross(b, c)).sum(2)
        den = la * lb * lc + (a * b).sum(2) * lc + (b * c).sum(2) * la + (c * a).sum(2) * lb
        return 2 * np.arctan2(num, den)

    def winding_brute(self, P, chunk=128):
        P = np.asarray(P, float)
        out = np.zeros(len(P))
        for s in range(0, len(P), chunk):
            out[s:s + chunk] = self._solid(P[s:s + chunk], self.A, self.B, self.C).sum(1) / (4 * math.pi)
        return out

    # ---- spatially grouped evaluation (same exact distance; winding exact near, dipole far field)
    CELL, NEAR = .01, .02

    def _cells(self):
        if not hasattr(self, '_cell'):
            key = np.floor((self.centroid - self.lo) / self.CELL).astype(int)
            uniq, inv = np.unique(key, axis=0, return_inverse=True)
            inv = inv.ravel()
            area = .5 * np.cross(self.B - self.A, self.C - self.A)
            w = np.linalg.norm(area, axis=1) + 1e-18
            cen = np.zeros((len(uniq), 3))
            np.add.at(cen, inv, self.centroid * w[:, None])
            cen /= np.bincount(inv, weights=w, minlength=len(uniq))[:, None]
            vec = np.zeros((len(uniq), 3))
            np.add.at(vec, inv, area)
            rad = np.zeros(len(uniq))
            np.maximum.at(rad, inv, np.linalg.norm(self.centroid - cen[inv], axis=1) + self.radius)
            self._cell = (inv, cen, vec, rad)
        return self._cell

    def _groups(self, P):
        key = np.floor((P - self.lo) / self.CELL).astype(int)
        _, inv = np.unique(key, axis=0, return_inverse=True)
        inv = inv.ravel()
        order = np.argsort(inv, kind='stable')
        bounds = np.flatnonzero(np.diff(inv[order])) + 1
        for idx in np.split(order, bounds):
            g = P[idx].mean(0)
            yield idx, g, float(np.linalg.norm(P[idx] - g, axis=1).max())

    def distance(self, P):
        """Exact unsigned distance and closest triangle (grouped candidate pruning; equals distance_brute)."""
        P = np.asarray(P, float)
        dist, tri = np.full(len(P), np.inf), np.zeros(len(P), int)
        for idx, g, rg in self._groups(P):
            lb = np.linalg.norm(self.centroid - g, axis=1) - self.radius - rg
            first = np.argpartition(lb, min(32, len(lb) - 1))[:32]
            p = P[idx]
            pi, ti = np.repeat(np.arange(len(p)), len(first)), np.tile(first, len(p))
            ub, _ = self._best(p, pi, ti)
            cand = np.flatnonzero(lb <= ub.max() + 1e-12)
            pi, ti = np.repeat(np.arange(len(p)), len(cand)), np.tile(cand, len(p))
            dist[idx], tri[idx] = self._best(p, pi, ti)
        return dist, tri

    def winding(self, P):
        """Generalized winding number: exact solid angles within NEAR of a point group, cell dipoles beyond."""
        P = np.asarray(P, float)
        inv, cen, vec, rad = self._cells()
        out = np.zeros(len(P))
        for idx, g, rg in self._groups(P):
            near = np.linalg.norm(cen - g, axis=1) - rad - rg < self.NEAR
            tris = near[inv]
            p = P[idx]
            w = self._solid(p, self.A[tris], self.B[tris], self.C[tris]).sum(1)
            if (~near).any():
                r = cen[~near][None] - p[:, None]
                w += ((vec[~near][None] * r).sum(2) / np.linalg.norm(r, axis=2) ** 3).sum(1)
            out[idx] = w / (4 * math.pi)
        return out

    def signed_distance(self, P, margin=.03):
        """Signed distance in metres (negative inside, |winding| > 0.5); points beyond margin of the box get +margin."""
        P = np.asarray(P, float)
        out = np.full(len(P), float(margin))
        near = np.all((P > self.lo - margin) & (P < self.hi + margin), axis=1)
        if near.any():
            d, _ = self.distance(P[near])
            inside = np.zeros(near.sum(), bool)
            box = np.all((P[near] >= self.lo) & (P[near] <= self.hi), axis=1)
            if box.any():
                inside[box] = np.abs(self.winding(P[near][box])) > .5
            out[near] = np.where(inside, -d, np.minimum(d, margin))
        return out


class SDFGrid:
    """Trilinear signed-distance grid of a Mesh: an OPTIMISER SURROGATE only; reports use Mesh.signed_distance."""

    def __init__(self, mesh: Mesh, spacing=.003, margin=.03, cache: Path | None = None, key: str | None = None):
        self.lo = mesh.lo - margin
        self.n = np.ceil((mesh.hi + margin - self.lo) / spacing).astype(int) + 1
        self.h, self.margin = spacing, margin
        file = Path(cache) / f'sdf.{key}.{spacing:.4f}.{margin:.3f}.npy' if cache and key else None
        if file and file.exists():
            self.values = np.load(file)
        else:
            axes = [self.lo[i] + np.arange(self.n[i]) * spacing for i in range(3)]
            g = np.stack(np.meshgrid(*axes, indexing='ij'), -1).reshape(-1, 3)
            self.values = mesh.signed_distance(g, margin=margin).reshape(*self.n)
            if file:
                file.parent.mkdir(parents=True, exist_ok=True)
                np.save(file, self.values)

    def __call__(self, P):
        u = (np.asarray(P, float) - self.lo) / self.h
        outside = np.any((u < 0) | (u > self.n - 1.001), axis=1)
        u = np.clip(u, 0, self.n - 1.001)
        i = np.floor(u).astype(int)
        f = u - i
        v = self.values
        out = np.zeros(len(u))
        for dx in (0, 1):
            for dy in (0, 1):
                for dz in (0, 1):
                    w = (f[:, 0] if dx else 1 - f[:, 0]) * (f[:, 1] if dy else 1 - f[:, 1]) * (f[:, 2] if dz else 1 - f[:, 2])
                    out += w * v[i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz]
        return np.where(outside, self.margin, out)


# ================================================================ the actual controller
def load_controller(path=CONTROLLER, cache=CACHE):
    """The controller's own primitive (not its contact-shadow quad) in its node frame, metres."""
    g = G.Gltf(decoded(path, cache))
    doc = g.doc
    node = next(i for i, n in enumerate(doc['nodes']) if n.get('name') == 'controller')
    worlds = G.world_pose(g, G.RestPose, 0)
    verts, faces, excluded = [], [], []
    for i, n in enumerate(doc['nodes']):
        if 'mesh' not in n:
            continue
        if doc['meshes'][n['mesh']].get('name') != 'controller':
            excluded.append(doc['meshes'][n['mesh']].get('name'))
            continue
        anc, j = set(), i
        while j in g.parent:
            j = g.parent[j]
            anc.add(j)
        if node not in anc and i != node:
            continue
        t, q, s = worlds[i]
        M = trs(t, q, s)
        for prim in doc['meshes'][n['mesh']]['primitives']:
            mat = doc.get('materials', [{}])[prim['material']] if prim.get('material') is not None else {}
            if mat.get('alphaMode') == 'BLEND' or 'contact' in str(mat.get('name', '')).lower():
                excluded.append(mat.get('name'))     # a baked contact shadow is not grip/collision geometry
                continue
            p = accessor(g, prim['attributes']['POSITION'])
            idx = accessor(g, prim['indices']).astype(int).ravel()
            faces.append(idx.reshape(-1, 3) + sum(len(v) for v in verts))
            verts.append(apply(M, p))
    if not verts:
        raise ValueError('controller mesh primitive not found')
    return Mesh(np.concatenate(verts), np.concatenate(faces)), {'excluded_primitives': excluded, 'file': str(Path(path).relative_to(ROOT)) if Path(path).is_relative_to(ROOT) else str(path),
                                                               'sha256': sha256(path)}


def controller_features(mesh: Mesh):
    """Stick caps measured on the mesh; other regions = authored constants shifted by the measured stick offset."""
    V = mesh.V
    top = V[:, 1] >= V[:, 1].max() - .003
    sticks = {}
    for side, sign in (('left', -1), ('right', 1)):
        m = top & (np.sign(V[:, 0]) == sign)
        if m.sum() < 3:
            raise ValueError('stick caps not found on the controller mesh')
        sticks[side] = np.array([V[m, 0].mean(), V[m, 1].max(), V[m, 2].mean()])
    authored = {'left': np.array([AUTHORED['left_stick'][0], AUTHORED['cap_top_y'], AUTHORED['left_stick'][1]]),
                'right': np.array([AUTHORED['right_stick'][0], AUTHORED['cap_top_y'], AUTHORED['right_stick'][1]])}
    shift = (sticks['left'] - authored['left'] + sticks['right'] - authored['right']) / 2
    fb = np.array([AUTHORED['face_buttons'][0], .0475 + .0042, AUTHORED['face_buttons'][1]]) + shift
    tr = AUTHORED['trigger']
    triggers = {s: np.array([k * tr['x'], tr['y'], tr['z']]) + shift for s, k in (('left', -1), ('right', 1))}
    grips = {}
    for s, k in (('left', -1), ('right', 1)):
        a, b = (np.array([k * p[0], p[1], p[2]]) + shift for p in AUTHORED['grip_axis'])
        ab = b - a
        t = np.clip(((V - a) @ ab) / (ab @ ab), 0, 1)
        r = AUTHORED['grip_radius'][0] + (AUTHORED['grip_radius'][1] - AUTHORED['grip_radius'][0]) * t
        on = np.linalg.norm(V - (a + t[:, None] * ab), axis=1) <= r + .004
        grips[s] = {'axis': (a, b), 'vertex_mask': on, 'centre': (a + b) / 2}
    near = lambda p: float(mesh.distance(p[None])[0][0])  # noqa: E731
    return {'sticks': sticks, 'face_buttons': fb, 'triggers': triggers, 'grips': grips, 'authoring_shift_m': shift,
            'stick_authoring_error_mm': float(1000 * np.linalg.norm((sticks['left'] - authored['left']) - (sticks['right'] - authored['right']))),
            'surface_distance_mm': {'face_buttons': 1000 * near(fb), 'left_trigger': 1000 * near(triggers['left']),
                                    'right_trigger': 1000 * near(triggers['right'])}}


def controller_report(path=CONTROLLER, cache=CACHE):
    mesh, ident = load_controller(path, cache)
    f = controller_features(mesh)
    boundary, nonmanifold = mesh.boundary_edges()
    ext = mesh.hi - mesh.lo
    r = lambda v: [round(float(x), 6) for x in v]  # noqa: E731
    return {'schema': SCHEMA, 'verified': False, **ident, 'licence': 'CC0 (web/room/CREDITS.md: modelled in code for this project, room_build/build_desk_tech.mjs)',
            'frame': 'controller node: x across, y up (face plate), z toward the player; grips rest on y = 0; metres',
            'vertices': int(len(mesh.V)), 'triangles': int(len(mesh.F)), 'bounds_m': {'min': r(mesh.lo), 'max': r(mesh.hi)},
            'size_cm': r(100 * ext), 'boundary_edges': boundary, 'nonmanifold_edges': nonmanifold,
            'closed': boundary == 0, 'inside_test': 'generalized winding number |w| > 0.5 (open lathe caps/D-pad tolerated, reported)',
            'sticks_m': {k: r(v) for k, v in f['sticks'].items()}, 'face_buttons_m': r(f['face_buttons']),
            'triggers_m': {k: r(v) for k, v in f['triggers'].items()},
            'grip_axes_m': {k: [r(p) for p in v['axis']] for k, v in f['grips'].items()},
            'grip_vertices': {k: int(v['vertex_mask'].sum()) for k, v in f['grips'].items()},
            'authoring_shift_m': r(f['authoring_shift_m']), 'stick_authoring_error_mm': round(f['stick_authoring_error_mm'], 4),
            'region_surface_distance_mm': {k: round(v, 3) for k, v in f['surface_distance_mm'].items()},
            'note': 'Stick caps are measured on the mesh; the face-button, trigger and grip regions are the authoring '
                    'constants of build_desk_tech.mjs moved by the measured stick offset, with their distance to the actual surface reported.'}


# ================================================================ owner hands (bind space, once)
class Hands:
    """Fixed bind-space hand vertex sets of the owner skin with exact linear-blend skinning on demand."""

    SETS = ('palm', 'thumb', 'index', 'hand')

    def __init__(self, names, ibm, sets):
        self.names, self.ibm, self.sets = list(names), np.asarray(ibm), sets
        self._ops = {}

    @classmethod
    def from_owner(cls, owner=OWNER, cache=CACHE):
        g = G.Gltf(decoded(owner, cache))
        doc = g.doc
        skin = doc['skins'][0]
        names = [canon(doc['nodes'][j]['name']) for j in skin['joints']]
        ibm = accessor(g, skin['inverseBindMatrices']).reshape(-1, 4, 4).transpose(0, 2, 1)
        bind = np.linalg.inv(ibm)
        J = {n: k for k, n in enumerate(names)}
        sets = {}
        for side in ('Left', 'Right'):
            hand = J[f'{side}Hand']
            chain = {J[f'{side}Hand{f}{i}'] for f in FINGERS for i in (1, 2, 3) if f'{side}Hand{f}{i}' in J} | {hand}
            pos = lambda n: bind[J[n], :3, 3]  # noqa: E731
            axis = pos(f'{side}HandMiddle1') - pos(f'{side}Hand')
            lateral = pos(f'{side}HandIndex1') - pos(f'{side}HandPinky1')
            normal = np.cross(axis, lateral) * (-1 if side == 'Right' else 1)
            normal /= np.linalg.norm(normal)
            if (pos(f'{side}HandThumb3') - pos(f'{side}Hand')) @ normal <= 0:
                raise ValueError(f'{side} palm normal does not face the thumb tip side')
            rows = {k: {'pos': [], 'nrm': [], 'joints': [], 'weights': []} for k in cls.SETS}
            seen = set()
            for node in doc['nodes']:
                if 'mesh' not in node or node.get('skin') != 0 or node['mesh'] in seen:
                    continue
                seen.add(node['mesh'])
                for prim in doc['meshes'][node['mesh']]['primitives']:
                    a = prim['attributes']
                    p, n = accessor(g, a['POSITION']), accessor(g, a['NORMAL'])
                    jt, wt = accessor(g, a['JOINTS_0']).astype(int), accessor(g, a['WEIGHTS_0'])
                    total = wt.sum(1)
                    ok = total > 0
                    share = lambda js: sum(np.where(np.isin(jt[:, k], list(js)), wt[:, k], 0.) for k in range(4)) / np.maximum(total, 1e-12)  # noqa: E731
                    masks = {'hand': ok & (share(chain) >= PALM_MIN_HAND_SHARE),
                             'palm': ok & (share({hand}) >= PALM_MIN_HAND_SHARE) & ((n @ normal) >= PALM_MIN_FACING),
                             'thumb': ok & (share({J[f'{side}HandThumb3']}) >= REGION_MIN_SHARE),
                             'index': ok & (share({J[f'{side}HandIndex3']}) >= REGION_MIN_SHARE)}
                    for k, m in masks.items():
                        idx = np.nonzero(m)[0]
                        rows[k]['pos'].append(p[idx])
                        rows[k]['nrm'].append(n[idx])
                        rows[k]['joints'].append(jt[idx])
                        rows[k]['weights'].append(wt[idx] / total[idx, None])
            for k, r in rows.items():
                sets[f'{side.lower()}_{k}'] = {c: np.concatenate(v) for c, v in r.items()}
        out = cls(names, ibm, sets)
        out.owner = {'file': str(Path(owner).relative_to(ROOT)) if Path(owner).is_relative_to(ROOT) else str(owner), 'sha256': sha256(owner),
                     'joints': len(names), 'bind': bind}
        return out

    def counts(self):
        return {k: int(len(v['pos'])) for k, v in self.sets.items()}

    def skin(self, name, worlds):
        """Posed (F, N, 3) positions in the clip's world metres (exact LBS: sum_k w_k M_jk ibm_jk p)."""
        s = self.sets[name]
        mats = (worlds @ self.ibm[None])[..., :3, :]                          # (F, J, 3, 4)
        hom = np.hstack([s['pos'], np.ones((len(s['pos']), 1))])
        out = np.zeros((len(worlds), len(hom), 3))
        for k in range(4):
            m = mats[:, s['joints'][:, k]]                                     # (F, N, 3, 4)
            out += s['weights'][None, :, k, None] * np.einsum('fnij,nj->fni', m, hom)
        return out


# ================================================================ captured clip
def clip_worlds(clip_path, names, times=None, rate=30.):
    """(F, J, 4, 4) captured joint world matrices (glTF metres, the clip's own node graph), the times."""
    g = G.Gltf(clip_path)
    anim = g.animation()
    index = {}
    for i, n in enumerate(g.nodes):
        nm = n.get('name', '')
        if nm.startswith('mixamorig'):
            index.setdefault(canon(nm), i)
    missing = [n for n in names if n not in index]
    if missing:
        raise ValueError(f'capture lacks owner joints {missing[:6]}')
    if times is None and rate is None:
        times = np.array(anim.key_times())                              # the captured frames themselves
    elif times is None:
        count = max(2, int(round((anim.end - anim.start) * rate)) + 1)
        times = np.linspace(anim.start, anim.end, count)
    nodes = [index[n] for n in names]
    out = np.zeros((len(times), len(names), 4, 4))
    for f, t in enumerate(times):
        w = G.world_pose(g, anim, float(t))
        for k, i in enumerate(nodes):
            out[f, k] = trs(*w[i])
    info = {'file': str(Path(clip_path).relative_to(ROOT)) if Path(clip_path).is_relative_to(ROOT) else str(clip_path),
            'sha256': g.sha256, 'animation': anim.name, 'duration_s': float(anim.end - anim.start),
            'frames_sampled': int(len(times)), 'sampling': 'captured key times' if rate is None else f'{rate} Hz'}
    audit = Path(str(clip_path) + '.audit.json')
    if audit.is_file():
        a = json.loads(audit.read_text())
        info['audit'] = {k: a.get(k) for k in ('algorithm', 'sourceSHA256', 'targetSHA256', 'outputSHA256', 'frames', 'duration',
                                               'checks', 'movingSourceFingerChannels', 'proceduralMotionAdded')}
        info['audit']['output_sha256_matches_clip'] = a.get('outputSHA256') == g.sha256
    return out, np.asarray(times, float), info


def seated_metrics(worlds, names):
    """Seated test from captured joints: thighs near horizontal and hips low over the feet."""
    J = {n: k for k, n in enumerate(names)}
    P = worlds[:, :, :3, 3]
    out = []
    for f in range(len(P)):
        thighs = []
        for side in ('Left', 'Right'):
            d = P[f, J[f'{side}Leg']] - P[f, J[f'{side}UpLeg']]
            thighs.append(math.degrees(math.acos(abs(d[1]) / max(np.linalg.norm(d), 1e-9))))
        feet = min(P[f, J['LeftFoot'], 1], P[f, J['RightFoot'], 1])
        out.append({'thigh_from_vertical_deg': thighs, 'hips_over_feet_m': float(P[f, J['Hips'], 1] - feet)})
    seated = all(min(r['thigh_from_vertical_deg']) >= 55 for r in out)
    return {'seated': seated, 'rule': 'both thighs >= 55 deg from vertical in every sampled frame',
            'thigh_from_vertical_deg_min': float(min(min(r['thigh_from_vertical_deg']) for r in out)),
            'hips_over_feet_m': [float(min(r['hips_over_feet_m'] for r in out)), float(max(r['hips_over_feet_m'] for r in out))]}


def finger_motion(clip_path, names, times):
    """Captured local rotation amplitude (deg from the clip's first sample) of thumb and index joints."""
    g = G.Gltf(clip_path)
    anim = g.animation()
    idx = {canon(n.get('name', '')): i for i, n in enumerate(g.nodes) if n.get('name', '').startswith('mixamorig')}
    out = {}
    for side in ('Left', 'Right'):
        for f in ('Thumb', 'Index'):
            for k in (1, 2, 3):
                n = f'{side}Hand{f}{k}'
                if n not in idx:
                    continue
                rest = g.rest(idx[n])[1]
                qs = [G.qnorm(anim.sample(idx[n], 'rotation', float(t), rest)) for t in times]
                out[n] = round(max(G.qangle_deg(qs[0], q) for q in qs), 4)
    return out


# ================================================================ the solver
def frame_features(hands: Hands, worlds):
    """Per frame: right Hand rigid frame and every hand vertex set (world metres)."""
    J = {n: k for k, n in enumerate(hands.names)}
    right = np.stack([rigid(w[J['RightHand']]) for w in worlds])
    left = np.stack([rigid(w[J['LeftHand']]) for w in worlds])
    sets = {k: hands.skin(k, worlds) for k in hands.sets}
    return right, left, sets


def targets(features):
    return {'left_thumb': features['sticks']['left'], 'right_thumb': (features['sticks']['right'], features['face_buttons']),
            'left_index': features['triggers']['left'], 'right_index': features['triggers']['right'],
            'left_palm': features['grips']['left']['centre'], 'right_palm': features['grips']['right']['centre']}


def initial_offset(right, sets, features):
    """Weighted Kabsch of hand features (in the right Hand frame, clip mean) onto controller features."""
    tg = targets(features)
    src, dst, w = [], [], []
    inv = np.linalg.inv(right)
    for key, weight in (('left_palm', 3.), ('right_palm', 3.), ('left_thumb', 2.), ('right_thumb', 2.), ('left_index', 1.), ('right_index', 1.)):
        pts = sets[key].mean(1)                                                     # (F, 3) world
        local = np.einsum('fij,fj->fi', inv[:, :3, :3], pts) + inv[:, :3, 3]
        src.append(local.mean(0))
        t = tg[key]
        dst.append((t[0] + t[1]) / 2 if isinstance(t, tuple) else t)
        w.append(weight)
    # controller-in-hand X maps controller points into the hand frame: hand = X ctrl  ->  X = kabsch(ctrl, hand)
    return kabsch(np.array(dst), np.array(src), np.array(w))


class Problem:
    """Cost and exact metrics of a controller placement for a set of frames."""

    def __init__(self, mesh: Mesh, features, right, sets, grid: SDFGrid | None = None, sub=6):
        self.mesh, self.features, self.right, self.sets, self.grid = mesh, features, right, sets, grid
        self.tg = targets(features)
        self.sub = {k: v[:, ::sub] if k.endswith('_hand') else v for k, v in sets.items()}

    def controller_world(self, X, f):
        return self.right[f] @ X

    def local(self, C, P):
        inv = np.linalg.inv(C)
        return apply(inv, P)

    def cost(self, X, frames, Xs=None, sides=('left', 'right')):
        sd = self.grid if self.grid is not None else (lambda p: self.mesh.signed_distance(p))
        total = 0.
        for n, f in enumerate(frames):
            C = self.right[f] @ (Xs[n] if Xs is not None else X)
            for side in sides:
                g = sd(self.local(C, self.sub[f'{side}_palm'][f])) * 100
                low = g.min()
                band = np.sort(g)[:MIN_SUPPORT_VERTICES].max()
                total += 4 * max(0., low - .1) ** 2 + 4 * max(0., band - PALM_BAND_CM[1]) ** 2 + 20 * max(0., PALM_BAND_CM[0] - low) ** 2
                h = sd(self.local(C, self.sub[f'{side}_hand'][f])) * 100
                total += 20 * (np.maximum(0., PENETRATION_LIMIT_CM - h) ** 2).mean() * 10
                # Non-saturating pull of the palm centre toward its grip axis (the surrogate SDF is flat beyond its margin).
                pc = self.local(C, self.sub[f'{side}_palm'][f]).mean(0)
                a, b = self.features['grips'][side]['axis']
                tt = np.clip((pc - a) @ (b - a) / ((b - a) @ (b - a)), 0, 1)
                total += .5 * max(0., 100 * np.linalg.norm(pc - (a + tt * (b - a))) - 3.) ** 2
                th = self.local(C, self.sub[f'{side}_thumb'][f]).mean(0)
                t = self.tg[f'{side}_thumb']
                dt = min(np.linalg.norm(th - x) for x in t) if isinstance(t, tuple) else np.linalg.norm(th - t)
                ix = self.local(C, self.sub[f'{side}_index'][f]).mean(0)
                total += .02 * (100 * dt) ** 2 + .01 * (100 * np.linalg.norm(ix - self.tg[f'{side}_index'])) ** 2
        return total / max(1, len(frames))

    def metrics(self, C, f):
        """EXACT per-frame residuals (cm) for controller world pose C at frame f."""
        row = {}
        for side in ('left', 'right'):
            palm = self.mesh.signed_distance(self.local(C, self.sets[f'{side}_palm'][f])) * 100
            hand = self.mesh.signed_distance(self.local(C, self.sets[f'{side}_hand'][f])) * 100
            band = int(((palm >= PALM_BAND_CM[0]) & (palm <= PALM_BAND_CM[1])).sum())
            th = self.local(C, self.sets[f'{side}_thumb'][f])
            ix = self.local(C, self.sets[f'{side}_index'][f])
            t = self.tg[f'{side}_thumb']
            tdist = {('stick' if k == 0 else 'face_buttons'): float(100 * np.linalg.norm(th.mean(0) - x)) for k, x in enumerate(t if isinstance(t, tuple) else (t,))}
            row[side] = {'palm_min_gap_cm': float(palm.min()), 'palm_band_vertices': band,
                         'palm_support_patch': bool(palm.min() >= PALM_BAND_CM[0] and palm.min() <= PALM_BAND_CM[1] and band >= MIN_SUPPORT_VERTICES),
                         'hand_min_signed_cm': float(hand.min()), 'hand_vertices_penetrating': int((hand < PENETRATION_LIMIT_CM).sum()),
                         'hand_vertices_inside': int((hand < 0).sum()),
                         'thumb_to_target_cm': tdist, 'thumb_min_gap_cm': float((self.mesh.signed_distance(th) * 100).min()),
                         'index_to_trigger_cm': float(100 * np.linalg.norm(ix.mean(0) - self.tg[f'{side}_index'])),
                         'thumb_local_m': [float(x) for x in th.mean(0)], 'index_local_m': [float(x) for x in ix.mean(0)]}
        row['grip'] = all(row[s]['palm_support_patch'] and row[s]['hand_vertices_penetrating'] == 0 for s in ('left', 'right'))
        return row


def solve_fixed(problem: Problem, X0, frames, iters=600):
    x, val = nelder_mead(lambda p: problem.cost(pose(p), frames), params_of(X0), [.08, .08, .08, .01, .01, .01], iters)
    x, val = nelder_mead(lambda p: problem.cost(pose(p), frames), x, [.02, .02, .02, .003, .003, .003], iters)
    return pose(x), float(val)


def solve_per_frame(problem: Problem, X, frames, iters=250):
    out = []
    for f in frames:
        x, _ = nelder_mead(lambda p: problem.cost(pose(p), [f]), params_of(X), [.03, .03, .03, .004, .004, .004], iters)
        out.append(pose(x))
    return out


def contact_spacing(sets):
    """Spacing of the captured CONTACT geometry (palm patch, thumb and index distal skin centroids), per frame (cm)."""
    out = {}
    for k in ('palm', 'thumb', 'index'):
        d = 100 * np.linalg.norm(sets[f'left_{k}'].mean(1) - sets[f'right_{k}'].mean(1), axis=1)
        out[f'{k}_centroids'] = {'min': float(d.min()), 'max': float(d.max()), 'per_frame': [round(float(v), 4) for v in d]}
    inner = 100 * np.array([np.linalg.norm(sets['left_palm'][f][:, None] - sets['right_palm'][f][None], axis=2).min() for f in range(len(sets['left_palm']))])
    out['palm_patch_closest'] = {'min': float(inner.min()), 'max': float(inner.max())}
    return out


FK_PARITY_T4_CM = {'Hips': (2.3456, 50.5276, 11.0024), 'Head': (2.6834, 105.621, 16.4187),
                   'LeftHand': (20.1514, 88.0128, 50.2592), 'RightHand': (-8.7231, 85.4654, 51.5078)}   # root's FK, glTF cm


def fk_parity(clip, names):
    w, _, _ = clip_worlds(clip, names, times=[4.0])
    J = {n: k for k, n in enumerate(names)}
    err = {n: float(np.abs(100 * w[0, J[n], :3, 3] - np.array(v)).max()) for n, v in FK_PARITY_T4_CM.items()}
    return {'t_s': 4.0, 'root_cm': FK_PARITY_T4_CM, 'max_abs_error_cm': err, 'within_0_01_cm': all(v <= .01 for v in err.values())}


def hand_drift(right, left):
    """Left Hand bone in the right Hand frame, per frame, against its clip mean."""
    rel = np.einsum('fij,fjk->fik', np.linalg.inv(right), left)
    t = rel[:, :3, 3]
    mean_t = t.mean(0)
    u, _, vt = np.linalg.svd(rel[:, :3, :3].sum(0))
    mean_r = u @ vt
    dt = np.linalg.norm(t - mean_t, axis=1) * 100
    dr = np.array([angle_deg(mean_r, r[:3, :3]) for r in rel])
    wrists = np.linalg.norm(right[:, :3, 3] - left[:, :3, 3], axis=1) * 100
    return {'translation_from_mean_cm': {'max': float(dt.max()), 'p95': float(np.percentile(dt, 95)), 'per_frame': [round(float(v), 4) for v in dt]},
            'rotation_from_mean_deg': {'max': float(dr.max()), 'p95': float(np.percentile(dr, 95)), 'per_frame': [round(float(v), 4) for v in dr]},
            'wrist_distance_cm': {'min': float(wrists.min()), 'max': float(wrists.max()), 'per_frame': [round(float(v), 4) for v in wrists]},
            'mean_left_in_right': {'translation_m': [float(v) for v in mean_t], 'rotation_rotvec': [float(v) for v in matrix_to_rotvec(mean_r)]}}


def two_bone_ik(shoulder, elbow, wrist, target):
    """Minimal analytic two-bone IK: same bone lengths, elbow in the captured elbow plane.

    Returns (new_elbow, reachable, elbow_angle_change_deg, wrist_error_m). Wrist WORLD orientation and
    finger locals are kept by construction (only shoulder/elbow rotate; the wrist local is re-solved).
    """
    a, b = np.linalg.norm(elbow - shoulder), np.linalg.norm(wrist - elbow)
    d_vec = target - shoulder
    d = np.linalg.norm(d_vec)
    reach = abs(a - b) <= d <= a + b
    dc = np.clip(d, abs(a - b) + 1e-9, a + b - 1e-9)
    u = d_vec / max(d, 1e-12)
    pole = elbow - shoulder
    pole = pole - (pole @ u) * u
    if np.linalg.norm(pole) < 1e-9:
        pole = np.cross(u, [0, 1, 0])
    pole /= np.linalg.norm(pole)
    x = (a * a - b * b + dc * dc) / (2 * dc)
    h = math.sqrt(max(0., a * a - x * x))
    new_elbow = shoulder + u * x + pole * h
    reached = shoulder + u * dc
    ang = lambda s, e, w: math.degrees(math.acos(np.clip(((s - e) @ (w - e)) / (np.linalg.norm(s - e) * np.linalg.norm(w - e)), -1, 1)))  # noqa: E731
    return new_elbow, bool(reach), ang(shoulder, new_elbow, reached) - ang(shoulder, elbow, wrist), float(np.linalg.norm(reached - target))


def ik_proposal(worlds, names, right, left, X, Y_left):
    """Left arm IK a FIXED right-hand controller would need, per frame (proposal + residual only)."""
    J = {n: k for k, n in enumerate(names)}
    rows = []
    for f in range(len(worlds)):
        want = right[f] @ X @ Y_left                       # where the left Hand must be to keep the grip
        s, e, w = (worlds[f, J[n], :3, 3] for n in ('LeftArm', 'LeftForeArm', 'LeftHand'))
        _, reach, dang, err = two_bone_ik(s, e, w, want[:3, 3])
        rows.append({'wrist_translation_cm': float(100 * np.linalg.norm(want[:3, 3] - w)), 'reachable': reach,
                     'elbow_angle_change_deg': float(dang), 'position_residual_cm': float(100 * err),
                     'wrist_rotation_residual_deg': float(angle_deg(left[f][:3, :3], want[:3, :3]))})
    k = lambda key: [r[key] for r in rows]  # noqa: E731
    return {'rule': 'left two-bone IK (LeftArm/LeftForeArm), wrist WORLD orientation and finger locals preserved; '
                    'the remaining wrist rotation is reported as a residual, never forced',
            'max_wrist_translation_cm': float(max(k('wrist_translation_cm'))), 'all_reachable': all(k('reachable')),
            'max_elbow_angle_change_deg': float(max(map(abs, k('elbow_angle_change_deg')))),
            'max_position_residual_cm': float(max(k('position_residual_cm'))),
            'max_wrist_rotation_residual_deg': float(max(k('wrist_rotation_residual_deg'))), 'per_frame': rows}


IK_BOUND_CM, IK_BOUND_DEG = 10.0, 25.0     # provisional bound on the per-wrist IK change (proposal only)


def blend(A, B, t=.5):
    """Rigid interpolation of two 4x4 poses (translation lerp, rotation along the geodesic)."""
    out = np.eye(4)
    out[:3, :3] = A[:3, :3] @ rotvec_to_matrix(t * matrix_to_rotvec(A[:3, :3].T @ B[:3, :3]))
    out[:3, 3] = (1 - t) * A[:3, 3] + t * B[:3, 3]
    return out


def solve_hand(mesh, feats, anchor, sets, side, frames, grid, iters=500):
    """Controller fixed to ONE hand that grips it alone (palm patch, no penetration, thumb/index targets)."""
    prob = Problem(mesh, feats, anchor, sets, grid)
    X0 = initial_offset(anchor, {k: v for k, v in sets.items()}, feats)
    f = lambda p: prob.cost(pose(p), frames, sides=(side,))  # noqa: E731
    x, _ = nelder_mead(f, params_of(X0), [.08, .08, .08, .01, .01, .01], iters)
    x, _ = nelder_mead(f, x, [.02, .02, .02, .003, .003, .003], iters)
    return pose(x)


def bounded_two_arm_ik(worlds, names, right, left, sets, mesh, feats, grid, frames):
    """Bounded two-arm IK PROPOSAL that lets both captured hands hold one rigid controller.

    Each hand's own grip of the controller (H_R, H_L: controller -> hand, solved per hand over the clip) is
    kept; per frame the controller is the rigid midpoint of where each hand puts it, and each wrist moves
    rigidly to its grip of that controller. The arm chain (LeftArm/LeftForeArm, RightArm/RightForeArm) is
    re-solved by analytic two-bone IK; the wrist WORLD orientation changes only by the grip mismatch; every
    captured finger LOCAL rotation is untouched (the hand + fingers move as one rigid unit). Measured after
    the proposal with the same exact contact metrics. Never applied to the clip here.
    """
    XR = solve_hand(mesh, feats, right, sets, 'right', frames, grid)
    XL = solve_hand(mesh, feats, left, sets, 'left', frames, grid)
    J = {n: k for k, n in enumerate(names)}
    rows, after_sets, C_all = [], {k: np.empty_like(v) for k, v in sets.items()}, []
    for f in range(len(worlds)):
        C = blend(right[f] @ XR, left[f] @ XL)
        C_all.append(C)
        row = {}
        for side, cap, X, arm in (('right', right[f], XR, 'Right'), ('left', left[f], XL, 'Left')):
            target = C @ np.linalg.inv(X)
            delta = target @ np.linalg.inv(cap)
            for k in sets:
                if k.startswith(side):
                    after_sets[k][f] = apply(delta, sets[k][f])
            s_, e_, w_ = (worlds[f, J[n], :3, 3] for n in (f'{arm}Arm', f'{arm}ForeArm', f'{arm}Hand'))
            _, reach, dang, err = two_bone_ik(s_, e_, w_, target[:3, 3])
            move, turn = float(100 * np.linalg.norm(target[:3, 3] - cap[:3, 3])), float(angle_deg(target[:3, :3], cap[:3, :3]))
            row[side] = {'wrist_displacement_cm': move, 'wrist_rotation_deg': turn, 'reachable': reach,
                         'elbow_angle_change_deg': float(dang), 'position_residual_cm': float(100 * err),
                         'within_bound': bool(reach and move <= IK_BOUND_CM and turn <= IK_BOUND_DEG)}
        rows.append(row)
    after = Problem(mesh, feats, right, after_sets, grid)
    metrics = [after.metrics(C_all[f], f) for f in range(len(worlds))]
    k = lambda side, key: [r[side][key] for r in rows]  # noqa: E731
    return {'rule': 'bounded two-arm two-bone IK; hand+fingers rigid (captured finger locals exact); wrist world orientation changed '
                    'only by the per-hand grip mismatch; proposal and residuals only',
            'bound': {'wrist_displacement_cm': IK_BOUND_CM, 'wrist_rotation_deg': IK_BOUND_DEG},
            'controller_in_right_hand': XR.tolist(), 'controller_in_left_hand': XL.tolist(),
            'per_side': {s: {'max_wrist_displacement_cm': float(max(k(s, 'wrist_displacement_cm'))),
                             'max_wrist_rotation_deg': float(max(k(s, 'wrist_rotation_deg'))),
                             'max_elbow_angle_change_deg': float(max(map(abs, k(s, 'elbow_angle_change_deg')))),
                             'max_position_residual_cm': float(max(k(s, 'position_residual_cm'))),
                             'frames_within_bound': int(sum(k(s, 'within_bound')))} for s in ('left', 'right')},
            'after_ik_summary': summarise(metrics), 'per_frame': rows, 'per_frame_after_ik': metrics}


def summarise(rows):
    out = {}
    for side in ('left', 'right'):
        g = lambda k: [r[side][k] for r in rows]  # noqa: E731
        out[side] = {'palm_min_gap_cm': [float(min(g('palm_min_gap_cm'))), float(max(g('palm_min_gap_cm')))],
                     'palm_band_vertices_min': int(min(g('palm_band_vertices'))),
                     'palm_support_patch_frames': int(sum(g('palm_support_patch'))),
                     'hand_min_signed_cm': float(min(g('hand_min_signed_cm'))),
                     'frames_with_penetration': int(sum(1 for v in g('hand_vertices_penetrating') if v)),
                     'max_vertices_penetrating': int(max(g('hand_vertices_penetrating'))),
                     'thumb_to_stick_cm': [float(min(t['stick'] for t in g('thumb_to_target_cm'))), float(max(t['stick'] for t in g('thumb_to_target_cm')))],
                     'index_to_trigger_cm': [float(min(g('index_to_trigger_cm'))), float(max(g('index_to_trigger_cm')))]}
        if side == 'right':
            fb = [t['face_buttons'] for t in g('thumb_to_target_cm')]
            out[side]['thumb_to_face_buttons_cm'] = [float(min(fb)), float(max(fb))]
        th = np.array(g('thumb_local_m'))
        out[side]['thumb_motion_in_controller_frame_cm'] = {'range_xyz': [float(v) for v in 100 * (th.max(0) - th.min(0))],
                                                           'path_extent': float(100 * np.linalg.norm(th.max(0) - th.min(0)))}
        ix = np.array(g('index_local_m'))
        out[side]['index_motion_in_controller_frame_cm'] = {'range_xyz': [float(v) for v in 100 * (ix.max(0) - ix.min(0))]}
    out['frames'] = len(rows)
    out['frames_full_grip'] = int(sum(r['grip'] for r in rows))
    return out


def fit(clip, owner=OWNER, controller=CONTROLLER, cache=CACHE, stride=1, rate=None, opt_frames=8, per_frame=True, label=None, source_fbx_sha256=None):
    hands = Hands.from_owner(owner, cache)
    mesh, cinfo = load_controller(controller, cache)
    feats = controller_features(mesh)
    worlds, times, info = clip_worlds(clip, hands.names, rate=rate)
    if source_fbx_sha256:
        info['source_fbx_sha256'] = source_fbx_sha256
        info['source_fbx_sha256_basis'] = 'declared by root for the private owner Mixamo download (raw FBX not in Git)'
    worlds, times = worlds[::stride], times[::stride]
    right, left, sets = frame_features(hands, worlds)
    grid = SDFGrid(mesh, cache=cache, key=cinfo['sha256'][:16])
    prob = Problem(mesh, feats, right, sets, grid)
    X0 = initial_offset(right, sets, feats)
    opt = np.unique(np.linspace(0, len(worlds) - 1, min(opt_frames, len(worlds))).astype(int))
    X, cost = solve_fixed(prob, X0, opt)
    rows = [prob.metrics(right[f] @ X, f) for f in range(len(worlds))]
    J = {n: k for k, n in enumerate(hands.names)}
    # the left hand's grip relative to the controller, as the fit holds it on average
    Y_left = np.linalg.inv(X) @ np.mean(np.einsum('fij,fjk->fik', np.linalg.inv(right), left), axis=0)
    Y_left = rigid(Y_left)
    report = {'schema': SCHEMA, 'verified': False, 'trial': True, 'label': label or 'TRIAL grip fit; no contact accepted',
              'clip': info, 'owner': {k: v for k, v in hands.owner.items() if k != 'bind'}, 'controller': cinfo,
              'hand_vertex_counts': hands.counts(), 'seated': seated_metrics(worlds, hands.names),
              'captured_finger_rotation_amplitude_deg': finger_motion(clip, hands.names, times),
              'hand_drift': hand_drift(right, left),
              'controller_width_cm': float(100 * (mesh.hi[0] - mesh.lo[0])),
              'contact_spacing_cm': contact_spacing(sets),
              'fk_parity_t4s_cm': fk_parity(clip, hands.names),
              'contact_rule': {'palm_band_cm': PALM_BAND_CM, 'penetration_limit_cm': PENETRATION_LIMIT_CM,
                               'min_support_vertices': MIN_SUPPORT_VERTICES,
                               'distance': 'exact point-triangle distance, inside by generalized winding number'},
              'fixed': {'controller_in_right_hand': X.tolist(), 'optimiser_cost': cost, 'optimiser_frames': opt.tolist(),
                        'summary': summarise(rows), 'per_frame': rows},
              'ik_proposal': ik_proposal(worlds, hands.names, right, left, X, Y_left)}
    if per_frame:
        Xs = solve_per_frame(prob, X, range(len(worlds)))
        prow = [prob.metrics(right[f] @ Xs[f], f) for f in range(len(worlds))]
        dev_t = [float(100 * np.linalg.norm(x[:3, 3] - X[:3, 3])) for x in Xs]
        dev_r = [angle_deg(x[:3, :3], X[:3, :3]) for x in Xs]
        report['per_frame_fit'] = {'summary': summarise(prow), 'offset_change_from_fixed_cm_max': max(dev_t),
                                   'offset_change_from_fixed_deg_max': max(dev_r), 'per_frame': prow}
    opt_all = np.unique(np.linspace(0, len(worlds) - 1, min(opt_frames, len(worlds))).astype(int))
    report['bounded_two_arm_ik'] = bounded_two_arm_ik(worlds, hands.names, right, left, sets, mesh, feats, grid, opt_all)
    head = worlds[:, J['Head'], :3, 3]
    report['head_socket_m'] = {'range_cm': [float(v) for v in 100 * (head.max(0) - head.min(0))], 'first': [float(v) for v in head[0]]}
    report['ue_contract'] = ('UE component cm = 100 * (x, z, y) of glTF metres (export_seat_fit_source.py contract); the offset in UE '
                             'is P X P^-1 with P = that axis swap, translation x100; unverified for the static-mesh import until root\'s receipt.')
    return report


# ================================================================ sofa (authored source, NOT a native measurement)
def sofa_seat(path=SOFA, meta=SOFA_META):
    """Upward linen triangles of the authored sofa GLB placed at its runtime origin/yaw, in UE world cm.

    Same selection idea as unreal_chair_surface_audit.cushion_top (upward normal > 0.65, edge-connected
    patches), parameterised for the sofa. Source geometry only: the native sofa surface is unmeasured.
    """
    g = G.Gltf(path)
    m = json.loads(Path(meta).read_text())
    node = next(i for i, n in enumerate(g.doc['nodes']) if n.get('name') == 'Haven_linen')
    prim = g.doc['meshes'][g.doc['nodes'][node]['mesh']]['primitives'][0]
    V = accessor(g, prim['attributes']['POSITION'])
    F = accessor(g, prim['indices']).astype(int).reshape(-1, 3)
    yaw = m['runtime_yaw']
    ox, oy, oz = m['runtime_origin']
    c, s = math.cos(yaw), math.sin(yaw)
    wx, wy, wz = ox + c * V[:, 0] + s * V[:, 2], oy + V[:, 1], oz - s * V[:, 0] + c * V[:, 2]    # three.js rotation.y
    W = np.stack([100 * wx, 100 * wz, 100 * wy], 1)                                               # UE (x, y, z) cm
    a, b, cc = W[F[:, 0]], W[F[:, 1]], W[F[:, 2]]
    n = -np.cross(b - a, cc - a)            # the (x, z, y) swap mirrors winding: restore the outward normal
    ln = np.linalg.norm(n, axis=1)
    up = np.where(ln > 0, n[:, 2] / np.maximum(ln, 1e-12), 0)
    sel = np.nonzero((up > .65) & (np.maximum(np.maximum(a[:, 2], b[:, 2]), cc[:, 2]) < 60) & (np.minimum(np.minimum(a[:, 2], b[:, 2]), cc[:, 2]) > 35))[0]
    parent = list(range(len(sel)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    weld = [tuple(np.round(v, 3)) for v in W]
    edges = {}
    for i, t in enumerate(sel):
        ids = list(F[t])
        for x, y in zip(ids, ids[1:] + ids[:1]):
            key = tuple(sorted((weld[x], weld[y])))
            if key in edges:
                parent[find(i)] = find(edges[key])
            else:
                edges[key] = i
    groups = {}
    for i in range(len(sel)):
        groups.setdefault(find(i), []).append(sel[i])
    patches = []
    for tris in groups.values():
        pts = W[F[tris].ravel()]
        area = float((np.abs(n[tris, 2]) / 2).sum())
        patches.append({'triangles': len(tris), 'projected_area_cm2': area, 'min_cm': [float(v) for v in pts.min(0)],
                        'max_cm': [float(v) for v in pts.max(0)], 'top_cm': float(pts[:, 2].max())})
    patches.sort(key=lambda p: -p['projected_area_cm2'])
    top = 100 * m['seat_top_m']
    cushions = [p for p in patches if abs(p['top_cm'] - top) < 2 and p['projected_area_cm2'] >= 1000]
    lo, hi = np.array(m['blender_bounds'][0]), np.array(m['blender_bounds'][1])
    corners = np.array([[x, z] for x in (lo[0], hi[0]) for z in (lo[1], hi[1])])       # blender (x, y) = glTF (x, -z)
    fx = ox + c * corners[:, 0] + s * (-corners[:, 1])
    fz = oz - s * corners[:, 0] + c * (-corners[:, 1])
    footprint = ([100 * float(fx.min()), 100 * float(fz.min())], [100 * float(fx.max()), 100 * float(fz.max())])
    approach = [100 * SOFA_NODE_M[0], 100 * SOFA_NODE_M[1]]
    return {'schema': SCHEMA, 'verified': False, 'source': str(Path(path).relative_to(ROOT)), 'sha256': sha256(path),
            'licence': m.get('license'), 'runtime_origin_m': m['runtime_origin'], 'runtime_yaw_rad': yaw,
            'authored_seat_top_cm': 100 * m['seat_top_m'], 'mapping': 'UE = 100 * (web x, web z, web y) (home_world NODES -> native route targets)',
            'upward_patches_35_60cm': patches[:6], 'seat_cushions': cushions, 'native_measurement': None,
            'footprint_ue_cm': {'min': footprint[0], 'max': footprint[1]},
            'standing_capsule_at_sofa_node': {'approach_ue_cm': approach, 'radius_cm': CAPSULE_RADIUS_CM,
                                              'half_height_cm': CAPSULE_HALF_HEIGHT_CM,
                                              'horizontal_clearance_cm': capsule_clear(approach, *footprint)},
            'note': 'Authored source geometry at the web runtime placement; NOT the native imported sofa. A native '
                    'sofa audit (docs/proposed/sofa-controller-play.md) must replace this before any contact claim.'}


def capsule_clear(approach_cm, footprint_min_cm, footprint_max_cm, radius=CAPSULE_RADIUS_CM):
    """Horizontal clearance (cm) of the standing capsule at the approach from a sofa footprint rectangle (> 0: outside)."""
    dx = max(footprint_min_cm[0] - approach_cm[0], 0., approach_cm[0] - footprint_max_cm[0])
    dy = max(footprint_min_cm[1] - approach_cm[1], 0., approach_cm[1] - footprint_max_cm[1])
    inside = dx == 0 and dy == 0
    d = -min(approach_cm[0] - footprint_min_cm[0], footprint_max_cm[0] - approach_cm[0],
             approach_cm[1] - footprint_min_cm[1], footprint_max_cm[1] - approach_cm[1]) if inside else math.hypot(dx, dy)
    return d - radius


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('controller')
    sub.add_parser('sofa')
    f = sub.add_parser('fit')
    f.add_argument('--clip', required=True)
    f.add_argument('--owner', default=str(OWNER))
    f.add_argument('--controller', default=str(CONTROLLER))
    f.add_argument('--stride', type=int, default=1)
    f.add_argument('--rate', type=float, default=None, help='resample rate; default = the captured key times')
    f.add_argument('--source-fbx-sha256')
    f.add_argument('--no-per-frame', action='store_true')
    f.add_argument('--label')
    f.add_argument('--out')
    args = ap.parse_args(argv)
    if args.cmd == 'controller':
        out = controller_report()
    elif args.cmd == 'sofa':
        out = sofa_seat()
    else:
        if args.clip.lower().endswith('.fbx'):
            raise SystemExit('Convert the Mixamo FBX first (nothing renamed or retargeted):\n'
                             '  node room_build/kimodo/mixamo_glb.mjs Gaming.fbx Gaming.glb --no-textures')
        out = fit(Path(args.clip), args.owner, args.controller, stride=args.stride, rate=args.rate,
                  per_frame=not args.no_per_frame, label=args.label, source_fbx_sha256=args.source_fbx_sha256)
    text = json.dumps(out, indent=1)
    if getattr(args, 'out', None):
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + '\n')
        brief = {k: out[k] for k in ('clip', 'seated', 'hand_drift', 'controller_width_cm', 'fk_parity_t4s_cm', 'captured_finger_rotation_amplitude_deg', 'hand_vertex_counts') if k in out}
        brief['contact_spacing_cm'] = {k: {a: b for a, b in v.items() if a != 'per_frame'} for k, v in out['contact_spacing_cm'].items()}
        brief['bounded_two_arm_ik'] = {k: v for k, v in out['bounded_two_arm_ik'].items() if not k.startswith('per_frame')}
        brief['fixed'] = out['fixed']['summary']
        if 'per_frame_fit' in out:
            brief['per_frame_fit'] = out['per_frame_fit']['summary']
        brief['ik_proposal'] = {k: v for k, v in out['ik_proposal'].items() if k != 'per_frame'}
        for k in ('translation_from_mean_cm', 'rotation_from_mean_deg', 'wrist_distance_cm'):
            brief['hand_drift'] = dict(brief['hand_drift'])
            brief['hand_drift'][k] = {a: b for a, b in brief['hand_drift'][k].items() if a != 'per_frame'}
        print(json.dumps(brief, indent=1))
    else:
        print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
