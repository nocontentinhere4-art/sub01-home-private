"""Measured, horizontal RIGID placement candidates for the chair (and keyboard/desk) vs the seated body.

Proposal only. It ranks candidate placements from ACTUAL exported samples and reports, for every
candidate, every gate that still fails, by how much and at which frames. It never claims a seat:
the output always carries `verified: false` and `requires_server_reaudit: true`, and any chosen
candidate must be applied on the server and re-audited by tools/unreal_audit_seat_contact.py and
the keyboard contact audit before anything is claimed. docs/proposed/seat-rigid-placement.md has
the export schema and how to read the result.

Transform model: ONE rigid horizontal transform (dx, dy, yaw about a stated pivot) applied to one
unit -- the chair (preferred), the body, or the keyboard+desk. The body never moves vertically, is
never scaled or stretched and no bone changes. A chair dz is allowed only inside the chair's real
height-adjustment range stated in the scene export (default none), and it is reported. Thresholds
are the documented ones, imported from the existing validators; nothing is relaxed.

    python tools/fit_seat_rigid_placement.py --skin S.json --chair native-chair-surface.json \
        --scene SCENE.json --keyboard K.json --out private-audit/native-seat-rigid-candidates.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_unreal_contact_profile as contact_profile  # noqa: E402
import validate_unreal_seat_contact as seat_contact  # noqa: E402

SCHEMA_OUT = 'sub01.seat-rigid-candidates.v1'
SCHEMA_SKIN = 'sub01.seat-fit-skin.v1'
SCHEMA_SCENE = 'sub01.seat-fit-scene.v1'
SCHEMA_KEYBOARD = 'sub01.seat-fit-keyboard.v1'

# --- Documented thresholds, never relaxed (docs/qa/contact.md and the existing validators).
SEAT_BAND_CM = seat_contact.SEAT_BAND_CM                  # (-2.5, +0.5) buttocks / posterior thighs
SOLE_BAND_CM = seat_contact.SOLE_BAND_CM                  # (0, +1) soles on their support
MIN_PATCH_VERTICES = seat_contact.MIN_PATCH_VERTICES      # 12 downward-facing vertices over the surface
MIN_BAND_COVERAGE = seat_contact.MIN_BAND_COVERAGE        # reported only since 9ff9880 (not gated)
MIN_SUPPORT_VERTICES = seat_contact.MIN_SUPPORT_VERTICES  # 12 patch vertices in band, every patch
SEAT_PATCHES = seat_contact.SEAT_REGIONS
SOLE_PATCHES = seat_contact.SOLE_REGIONS
PATCHES = seat_contact.REGIONS
FACING_DOWN_MAX_NZ = -.5                                  # AnalyzeCapturedSeatSkin: N.Z > -.5 is skipped
KEY_GAP_MAX_CM = contact_profile.KEY_GAP_MAX_CM           # 0.2: fingertips over keycaps, 0..+2 mm
KEY_PENETRATION_MAX_CM = .1                               # validate_unreal_contact_profile: penetrationCm > .1
KEY_CONTACT_TARGET_CM = .08                               # unreal_keyboard_contact_target.py: KeyTop+.08
REACH_TOLERANCE_CM = 0.                                   # no stretch: requested distance <= arm length
BODY_COLLISION_ALLOWED_CM = 0.                            # contact.md: chair frame / desk "out, 0 vertices inside"
SAMPLE_COUNT, SAMPLE_T0_S, SAMPLE_RATE_HZ = 301, 3., 60.  # DeskTyping 3-8 s at 60 Hz
GROUPS = ('body', 'chair', 'keyboard')
FAMILIES = ('chair', 'body', 'keyboard')
LEGS = ('left', 'right')
LEG_OF = {'left_posterior_thigh': 0, 'left_sole': 0, 'right_posterior_thigh': 1, 'right_sole': 1}


# ---------------------------------------------------------------- geometry
@dataclass(frozen=True)
class Rigid:
    """Horizontal rigid motion: rotate by yaw (deg, UE convention: +X toward +Y) about pivot, then translate."""
    dx: float = 0.
    dy: float = 0.
    dz: float = 0.
    yaw: float = 0.
    pivot: tuple = (0., 0.)

    def _rot(self, p, yaw, pivot):
        a = math.radians(yaw)
        c, s = math.cos(a), math.sin(a)
        out = np.array(p, dtype=float, copy=True)
        x, y = out[..., 0] - pivot[0], out[..., 1] - pivot[1]
        out[..., 0], out[..., 1] = c * x - s * y + pivot[0], s * x + c * y + pivot[1]
        return out

    def apply(self, p):
        out = self._rot(p, self.yaw, self.pivot)
        out[..., 0] += self.dx
        out[..., 1] += self.dy
        out[..., 2] += self.dz
        return out

    def inverse(self, p):
        out = np.array(p, dtype=float, copy=True)
        out[..., 0] -= self.dx
        out[..., 1] -= self.dy
        out[..., 2] -= self.dz
        return self._rot(out, -self.yaw, self.pivot)

    def is_identity(self):
        return self.dx == 0 and self.dy == 0 and self.dz == 0 and self.yaw == 0

    def to_json(self):
        return {'dx_cm': _r(self.dx), 'dy_cm': _r(self.dy), 'dz_cm': _r(self.dz), 'yaw_deg': _r(self.yaw),
                'pivot_cm': [_r(self.pivot[0]), _r(self.pivot[1])]}


IDENTITY = Rigid()


def _r(value, digits=6):
    value = float(value)
    if not math.isfinite(value):
        return None
    out = round(value, digits)
    return 0.0 if out == 0 else out


def _finite_array(value, shape_tail, what):
    arr = np.asarray(value, dtype=float)
    if arr.ndim < len(shape_tail) or (shape_tail and arr.shape[-len(shape_tail):] != tuple(shape_tail)):
        raise ValueError(f'{what}: expected shape (..., {", ".join(map(str, shape_tail))}), got {arr.shape}')
    if not np.all(np.isfinite(arr)):
        raise ValueError(f'{what}: nonfinite values')
    return arr


def mesh_triangles(obj, what):
    """{vertices_world_cm, triangle_indices} -> (T, 3, 3) world triangles."""
    vertices = _finite_array(obj['vertices_world_cm'], (3,), f'{what} vertices')
    faces = obj['triangle_indices']
    if not faces or any(len(f) != 3 for f in faces):
        raise ValueError(f'{what}: malformed triangle_indices')
    idx = np.asarray(faces, dtype=int)
    if idx.min() < 0 or idx.max() >= len(vertices):
        raise ValueError(f'{what}: triangle index out of range')
    return vertices[idx]


class Surface:
    """Upward height lookup identical in rule to Sub01SurfaceHeightAt (unreal_skin_contact_native.py):
    the highest triangle under (X, Y) by vertical projection, barycentric tolerance -1e-6, triangles
    with |det| < 1e-9 ignored. A uniform 2-D cell table only narrows the candidate triangles."""

    def __init__(self, triangles):
        tri = np.asarray(triangles, dtype=float).reshape(-1, 3, 3)
        a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
        det = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
        keep = np.abs(det) >= 1e-9
        self.tri, self.det = tri[keep], det[keep]
        if not len(self.tri):
            raise ValueError('Surface has no nondegenerate triangles')
        a, b, c = self.tri[:, 0], self.tri[:, 1], self.tri[:, 2]
        # Sub01SurfaceHeightAt: L1=((B.y-C.y)(X-C.x)+(C.x-B.x)(Y-C.y))/Det, L2=((C.y-A.y)(X-C.x)+(A.x-C.x)(Y-C.y))/Det
        self.coef = np.stack([b[:, 1] - c[:, 1], c[:, 0] - b[:, 0], c[:, 0], c[:, 1],
                              c[:, 1] - a[:, 1], a[:, 0] - c[:, 0], a[:, 2], b[:, 2], 1. / self.det])
        self.cz = c[:, 2]
        lo, hi = self.tri[..., :2].min(axis=(0, 1)), self.tri[..., :2].max(axis=(0, 1))
        extent = np.maximum(hi - lo, 1e-3)
        cell = max(1., math.sqrt(extent[0] * extent[1] / (2. * len(self.tri))))
        while math.ceil(extent[0] / cell) * math.ceil(extent[1] / cell) > 400_000:
            cell *= 1.5
        self.lo, self.cell = lo - 1e-4, cell
        self.n = (int(math.ceil((extent[0] + 2e-4) / cell)) + 1, int(math.ceil((extent[1] + 2e-4) / cell)) + 1)
        cells = [[] for _ in range(self.n[0] * self.n[1])]
        tmin = np.floor((self.tri[..., :2].min(axis=1) - 1e-5 - self.lo) / cell).astype(int)
        tmax = np.floor((self.tri[..., :2].max(axis=1) + 1e-5 - self.lo) / cell).astype(int)
        tmin, tmax = np.clip(tmin, 0, np.array(self.n) - 1), np.clip(tmax, 0, np.array(self.n) - 1)
        for t in range(len(self.tri)):
            for i in range(tmin[t, 0], tmax[t, 0] + 1):
                for j in range(tmin[t, 1], tmax[t, 1] + 1):
                    cells[i * self.n[1] + j].append(t)
        width = max(1, max(len(c) for c in cells))
        self.table = np.full((len(cells), width), -1, dtype=np.int64)
        for k, c in enumerate(cells):
            self.table[k, :len(c)] = c

    def height(self, xy):
        """(found bool[N], z float[N] with nan where not found)."""
        xy = np.asarray(xy, dtype=float).reshape(-1, 2)
        found = np.zeros(len(xy), dtype=bool)
        z = np.full(len(xy), np.nan)
        for start in range(0, len(xy), 65536):
            sl = slice(start, start + 65536)
            f, h = self._height(xy[sl])
            found[sl], z[sl] = f, h
        return found, z

    def _height(self, xy):
        found = np.zeros(len(xy), dtype=bool)
        z = np.full(len(xy), np.nan)
        ij = np.floor((xy - self.lo) / self.cell).astype(np.int64)
        inside = (ij[:, 0] >= 0) & (ij[:, 1] >= 0) & (ij[:, 0] < self.n[0]) & (ij[:, 1] < self.n[1])
        if not inside.any():
            return found, z
        sub = xy[inside]
        cand = self.table[ij[inside, 0] * self.n[1] + ij[inside, 1]]
        valid = cand >= 0
        t = np.where(valid, cand, 0)
        k = self.coef[:, t]                                  # (9, n, K) per-triangle constants
        x, y = sub[:, 0:1], sub[:, 1:2]
        l1 = (k[0] * (x - k[2]) + k[1] * (y - k[3])) * k[8]
        l2 = (k[4] * (x - k[2]) + k[5] * (y - k[3])) * k[8]
        l3 = 1 - l1 - l2
        hit = valid & (l1 >= -1e-6) & (l2 >= -1e-6) & (l3 >= -1e-6)
        h = np.where(hit, l1 * k[6] + l2 * k[7] + l3 * self.cz[t], -np.inf)
        f = hit.any(axis=1)
        found[inside] = f
        z[inside] = np.where(f, h.max(axis=1), np.nan)
        return found, z

    def projected_area_cm2(self):
        a, b, c = self.tri[:, 0], self.tri[:, 1], self.tri[:, 2]
        return float(np.sum(np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]))) / 2)

    def bounds(self):
        return self.tri.reshape(-1, 3).min(axis=0), self.tri.reshape(-1, 3).max(axis=0)


@dataclass
class Convex:
    """A rigid collision primitive in its exported world pose: a vertical-axis box or a closed convex hull."""
    name: str
    group: str
    normals: np.ndarray                 # (P, 3) outward unit normals
    offsets: np.ndarray                 # (P,)   n . x = d on the face
    vertices: np.ndarray                # (V, 3)
    allowed_cm: float = 0.
    box: tuple | None = None            # (center(3), half(3), yaw_deg) for exact box-box SAT

    def depth(self, points):
        """Inside depth (cm, > 0 inside) of points given in this primitive's exported frame."""
        p = np.asarray(points, dtype=float).reshape(-1, 3)
        lo, hi = self.vertices.min(axis=0), self.vertices.max(axis=0)
        near = np.all((p >= lo - 1e-6) & (p <= hi + 1e-6), axis=1)    # outside the bounds is outside the convex
        out = np.full(len(p), -1.)
        if near.any():
            out[near] = np.min(self.offsets[None, :] - p[near] @ self.normals.T, axis=1)
        return out


def box_primitive(obj, group):
    center = _finite_array(obj['center_cm'], (3,), f'box {obj.get("name")} center')
    half = _finite_array(obj['half_extents_cm'], (3,), f'box {obj.get("name")} half extents')
    yaw = float(obj.get('yaw_deg', 0.))
    if np.any(half <= 0) or not math.isfinite(yaw):
        raise ValueError(f'box {obj.get("name")}: half extents must be positive, yaw finite')
    a = math.radians(yaw)
    ax = np.array([[math.cos(a), math.sin(a), 0.], [-math.sin(a), math.cos(a), 0.], [0., 0., 1.]])
    normals, offsets = [], []
    for k in range(3):
        for sign in (1., -1.):
            n = sign * ax[k]
            normals.append(n)
            offsets.append(float(n @ center + half[k]))
    corners = np.array([center + sx * half[0] * ax[0] + sy * half[1] * ax[1] + sz * half[2] * ax[2]
                        for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])
    return Convex(str(obj['name']), group, np.array(normals), np.array(offsets), corners,
                  float(obj.get('allowed_penetration_cm', 0.)), (center, half, yaw))


def hull_primitive(obj, group):
    tri = mesh_triangles(obj, f'convex hull {obj.get("name")}')
    vertices = np.unique(tri.reshape(-1, 3), axis=0)
    centroid = vertices.mean(axis=0)
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(n, axis=1)
    keep = length > 1e-9
    n, a = n[keep] / length[keep, None], tri[keep, 0]
    d = np.sum(n * a, axis=1)
    flip = (n @ centroid - d) > 0               # orient outward: the centroid is behind every face
    n[flip], d[flip] = -n[flip], -d[flip]
    if np.max(vertices @ n.T - d[None, :]) > 1e-3:
        raise ValueError(f'convex hull {obj.get("name")} is not convex/closed')
    return Convex(str(obj['name']), group, n, d, vertices, float(obj.get('allowed_penetration_cm', 0.)))


def _box_sat_depth(a, ta, b, tb):
    """Exact overlap depth of two vertical-axis boxes after their group transforms (<= 0: apart)."""
    (ca, ha, ya), (cb, hb, yb) = a.box, b.box
    ca, cb = ta.apply(ca), tb.apply(cb)
    ya, yb = ya + ta.yaw, yb + tb.yaw
    axes = []
    for yaw in (ya, yb):
        r = math.radians(yaw)
        axes += [np.array([math.cos(r), math.sin(r)]), np.array([-math.sin(r), math.cos(r)])]

    def radius(h, yaw, axis):
        r = math.radians(yaw)
        u, v = np.array([math.cos(r), math.sin(r)]), np.array([-math.sin(r), math.cos(r)])
        return h[0] * abs(u @ axis) + h[1] * abs(v @ axis)

    depth = (ha[2] + hb[2]) - abs(ca[2] - cb[2])
    for axis in axes:
        depth = min(depth, radius(ha, ya, axis) + radius(hb, yb, axis) - abs((ca[:2] - cb[:2]) @ axis))
    return depth


# ---------------------------------------------------------------- problem
@dataclass
class Problem:
    times: np.ndarray
    body_location: np.ndarray
    body_yaw: float
    patch_pos: dict
    patch_nrm: dict
    collision_pts: np.ndarray            # (F, M, 3) body points tested against rigid primitives
    cushion: Surface
    cushion_area_cm2: float
    chair_pivot: tuple
    chair_component: str
    chair_height_range: tuple
    chair_height_source: str
    support: Surface | None              # fixed support surfaces (floor)
    support_adjustable: Surface | None   # surfaces a real object could change (rug, footrest)
    support_alternatives: list
    collision_leg: np.ndarray            # (M,) -1 body, 0 left leg, 1 right leg
    primitives: list
    keycaps: Surface | None
    keyboard_pivot: tuple
    shoulders: np.ndarray                # (F, 2, 3) left, right
    targets: np.ndarray                  # (F, 2, 3)
    arm_cm: np.ndarray                   # (2,)
    key_gap: np.ndarray                  # (F, 2) corrected over-key skin minimum - key top
    keycap_spread_cm: float
    sole_membership: dict
    actors: dict = field(default_factory=dict)
    digests: dict = field(default_factory=dict)
    input_problems: list = field(default_factory=list)


def _yaw_from_quat(q):
    x, y, z, w = q
    return math.degrees(math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))


def build_problem(skin, chair_report, scene, keyboard, digests=None):
    """Validate the exported JSON (see the doc) and build the measured problem. Raises ValueError."""
    problems = []
    if skin.get('schema') != SCHEMA_SKIN:
        raise ValueError(f'skin export schema must be {SCHEMA_SKIN}')
    if scene.get('schema') != SCHEMA_SCENE:
        raise ValueError(f'scene export schema must be {SCHEMA_SCENE}')
    if keyboard.get('schema') != SCHEMA_KEYBOARD:
        raise ValueError(f'keyboard export schema must be {SCHEMA_KEYBOARD}')
    body = skin['body']
    location = _finite_array(body['location_cm'], (3,), 'body location')
    rotation = _finite_array(body.get('rotation_pyr', [0., body['yaw_deg'], 0.]), (3,), 'body rotation')
    scale = _finite_array(body.get('scale_xyz', [1., 1., 1.]), (3,), 'body scale')
    if rotation[0] != 0 or rotation[2] != 0 or rotation[1] != body['yaw_deg']:
        raise ValueError('Audited body rotation must be yaw-only and agree with yaw_deg')
    if not np.all(scale == 1.):
        raise ValueError('Audited body scale must be exactly 1 (no scaling)')
    times = _finite_array(skin['times_s'], (), 'times').reshape(-1)
    expected = SAMPLE_T0_S + np.arange(SAMPLE_COUNT) / SAMPLE_RATE_HZ
    if len(times) != SAMPLE_COUNT or np.max(np.abs(times - expected)) > 1e-6:
        problems.append('skin times are not the complete 301 samples at 60 Hz over 3-8 s')
    frames = len(times)
    pos, nrm = {}, {}
    for name in PATCHES:
        patch = skin['patches'].get(name)
        if patch is None:
            raise ValueError(f'skin export missing patch {name}')
        pos[name] = _finite_array(patch['positions_cm'], (3,), f'{name} positions')
        nrm[name] = _finite_array(patch['normals'], (3,), f'{name} normals')
        if pos[name].ndim != 3 or pos[name].shape != nrm[name].shape or pos[name].shape[0] != frames:
            raise ValueError(f'{name}: positions/normals must both be [frames][vertices][3] for every frame')
    # Soles: a FIXED rest-mesh plantar selection (root: slides material, rest Y <= 0.004 m, bind normal
    # Y < -0.7; 4177 vertices; cuffs and socks excluded). The same indices are scored every frame;
    # nothing here re-picks the lowest vertices per pose.
    membership = skin.get('sole_membership')
    if not isinstance(membership, dict) or not membership.get('rule'):
        raise ValueError('sole_membership.rule (root fixed rest-mesh plantar selection) must be stated')
    sole_counts = {}
    for name in SOLE_PATCHES:
        ids = skin['patches'][name].get('vertex_indices')
        if not isinstance(ids, list) or not ids or any(isinstance(i, bool) or not isinstance(i, int) or i < 0 for i in ids):
            raise ValueError(f'{name}: vertex_indices (the fixed plantar index set) are required')
        if len(set(ids)) != len(ids) or len(ids) != pos[name].shape[1]:
            raise ValueError(f'{name}: vertex_indices must be unique and match the posed positions one to one')
        sole_counts[name] = len(ids)
    expected = membership.get('expected_vertex_count')
    if expected is not None and sum(sole_counts.values()) != int(expected):
        raise ValueError(f'sole index sets hold {sum(sole_counts.values())} vertices, membership states {expected}')
    if set(skin['patches']['left_sole']['vertex_indices']) & set(skin['patches']['right_sole']['vertex_indices']):
        raise ValueError('left and right sole index sets overlap')
    membership = dict(membership, vertex_counts=sole_counts)
    extra = skin.get('collision_samples')
    cols = [pos[n] for n in PATCHES]
    legs = [np.full(pos[n].shape[1], LEG_OF.get(n, -1)) for n in PATCHES]
    if extra is not None:
        cpos = _finite_array(extra['positions_cm'], (3,), 'collision samples')
        if cpos.ndim != 3 or cpos.shape[0] != frames:
            raise ValueError('collision_samples.positions_cm must be [frames][vertices][3]')
        cols.append(cpos)
        labels = extra.get('leg') or [None] * cpos.shape[1]
        if len(labels) != cpos.shape[1] or any(l not in (None, 'left', 'right') for l in labels):
            raise ValueError('collision_samples.leg must label every vertex left, right or null')
        legs.append(np.array([-1 if l is None else LEGS.index(l) for l in labels]))

    cushion_tri = np.asarray(seat_contact.cushion_triangles(chair_report), dtype=float).reshape(-1, 3, 3)
    cushion = Surface(cushion_tri)
    area = cushion.projected_area_cm2()
    from unreal_seat_transition_runtime import MIN_CUSHION_AREA_CM2, cushion_area_cm2
    if cushion_area_cm2(cushion_tri.reshape(-1, 3).tolist()) < MIN_CUSHION_AREA_CM2:
        raise ValueError(f'Cushion area {area:.1f} cm2 is not the broad seat cushion')
    lo, hi = cushion.bounds()
    chair = chair_report['chair']
    if 'transform' in chair and 'translation_cm' in chair['transform']:
        t = chair['transform']['translation_cm']
        chair_pivot = (float(t[0]), float(t[1]))
        chair_yaw = _yaw_from_quat(chair['transform'].get('rotation_xyzw', [0, 0, 0, 1]))
    else:
        chair_pivot, chair_yaw = (float(lo[0] + hi[0]) / 2, float(lo[1] + hi[1]) / 2), None
    adj = scene.get('chair_height_adjustment_cm') or {'range_cm': [0., 0.], 'source': 'none stated: chair dz fixed at 0'}
    height_range = tuple(float(v) for v in adj['range_cm'])
    if len(height_range) != 2 or height_range[0] > 0 or height_range[1] < 0 or not all(map(math.isfinite, height_range)):
        raise ValueError('chair_height_adjustment_cm.range_cm must be finite [lo<=0, hi>=0]')

    support = adjustable = None
    surfaces = scene.get('floor_support') or []
    fixed = [mesh_triangles(s, f'support {s.get("name")}') for s in surfaces if not s.get('adjustable')]
    movable = [mesh_triangles(s, f'support {s.get("name")}') for s in surfaces if s.get('adjustable')]
    if fixed:
        support = Surface(np.concatenate(fixed))
    if movable:
        adjustable = Surface(np.concatenate(movable))
    if not surfaces:
        problems.append('no floor support surfaces exported: soles cannot be measured')
    alternatives = []
    for alt in scene.get('support_alternatives') or []:
        delta = float(alt['delta_cm'])
        if not math.isfinite(delta) or not alt.get('source') or adjustable is None:
            raise ValueError('support_alternatives need a finite delta_cm, a real source and an adjustable surface')
        alternatives.append({'name': str(alt['name']), 'delta_cm': delta, 'source': str(alt['source'])})
    prims = []
    for group, key in (('chair', 'chair_collision'), ('static', 'static_collision'), ('keyboard', 'keyboard_collision')):
        spec = scene.get(key) or {}
        prims += [box_primitive(b, group) for b in spec.get('boxes', [])]
        prims += [hull_primitive(h, group) for h in spec.get('convex_hulls', [])]
    if not any(p.group == 'chair' for p in prims):
        problems.append('no chair collision primitives exported: body/chair collision is not measured')
    if not any(p.group != 'chair' for p in prims):
        problems.append('no desk/furniture collision primitives exported: body/furniture collision is not measured')

    if abs(float(keyboard['key_contact_target_cm']) - KEY_CONTACT_TARGET_CM) > 1e-12:
        raise ValueError('key_contact_target_cm must be the fixed 0.08 cm target (unreal_keyboard_contact_target.py)')
    keycaps = Surface(mesh_triangles(keyboard['keycap_tops'], 'keycap tops'))
    klo, khi = keycaps.bounds()
    hands = keyboard['frames']
    if len(hands) != frames:
        raise ValueError('keyboard frames must match the skin frames one to one')
    shoulders = np.zeros((frames, 2, 3))
    targets = np.zeros((frames, 2, 3))
    gaps = np.zeros((frames, 2))
    for f, row in enumerate(hands):
        if abs(float(row['time_s']) - times[f]) > 1e-6:
            raise ValueError('keyboard frame times differ from skin times')
        by_side = {h['side']: h for h in row['hands']}
        if set(by_side) != {'left', 'right'} or len(row['hands']) != 2:
            raise ValueError('each keyboard frame needs exactly the left and right hand')
        for k, side in enumerate(('left', 'right')):
            h = by_side[side]
            shoulders[f, k] = _finite_array(h['shoulder_cm'], (3,), 'shoulder')
            targets[f, k] = _finite_array(h['target_cm'], (3,), 'hand target')
            gaps[f, k] = float(h['corrected_over_key_min_cm']) - float(h['key_top_cm'])
    if not np.all(np.isfinite(gaps)):
        raise ValueError('nonfinite key contact measurement')
    arm = keyboard['arm_length_cm']
    arm_cm = np.array([float(arm['left']), float(arm['right'])])
    if not np.all(np.isfinite(arm_cm)) or np.any(arm_cm <= 0):
        raise ValueError('arm lengths must be positive and finite')
    actors = {'chair_component': {'location_cm': chair['transform']['translation_cm'], 'yaw_deg': chair_yaw}
              if chair_yaw is not None else None,
              'body': {'location_cm': location.tolist(), 'yaw_deg': float(body['yaw_deg'])},
              'keyboard': keyboard.get('keyboard_actor_world')}
    return Problem(times=times, body_location=location, body_yaw=float(body['yaw_deg']), patch_pos=pos, patch_nrm=nrm,
                   collision_pts=np.concatenate(cols, axis=1), cushion=cushion, cushion_area_cm2=area,
                   chair_pivot=chair_pivot, chair_component=str(chair.get('component', '')),
                   chair_height_range=height_range, chair_height_source=str(adj.get('source', '')), support=support,
                   support_adjustable=adjustable, support_alternatives=alternatives,
                   collision_leg=np.concatenate(legs),
                   primitives=prims, keycaps=keycaps,
                   keyboard_pivot=(float(klo[0] + khi[0]) / 2, float(klo[1] + khi[1]) / 2),
                   shoulders=shoulders, targets=targets, arm_cm=arm_cm, key_gap=gaps,
                   keycap_spread_cm=float(keyboard.get('keycap_top_spread_cm', float('nan'))),
                   sole_membership=membership, actors=actors, digests=dict(digests or {}),
                   input_problems=problems)


# ---------------------------------------------------------------- evaluation
def support_height(problem, xy, delta=0.):
    """Highest support under (X, Y): fixed surfaces, and adjustable ones moved by `delta` cm."""
    xy = np.asarray(xy, dtype=float).reshape(-1, 2)
    found, z = np.zeros(len(xy), bool), np.full(len(xy), -np.inf)
    for surface, dz in ((problem.support, 0.), (problem.support_adjustable, delta)):
        if surface is not None:
            f, h = surface.height(xy)
            z = np.where(f, np.maximum(z, h + dz), z)
            found |= f
    return found, np.where(found, z, np.nan)


def _leg_shift(placement, n_points, legs):
    """(n, 3) translation of each point from the per-leg rigid leg-chain translations, if any."""
    out = np.zeros((n_points, 3))
    for k, side in enumerate(LEGS):
        t = placement.get(f'{side}_leg')
        if t is not None:
            out[legs == k] = (t.dx, t.dy, t.dz)
    return out


def _patch_stats(gap, over, band):
    """Per-frame native statistics: count over surface, min, p50 (AnalyzeCapturedSeatSkin quantile rule)."""
    n = over.sum(axis=1)
    g = np.sort(np.where(over, gap, np.inf), axis=1)
    idx = np.clip(np.floor(.5 * np.maximum(n - 1, 0) + .5).astype(int), 0, g.shape[1] - 1)
    p50 = np.take_along_axis(g, idx[:, None], axis=1)[:, 0]
    mn = g[:, 0]
    has = n > 0
    return n, np.where(has, mn, np.nan), np.where(has, p50, np.nan), band.sum(axis=1)


def _gate(name, subject, amount, fail, times, unit, extra=None):
    fail = np.asarray(fail, dtype=bool)
    if not fail.any():
        return None
    amt = np.where(fail, amount, -np.inf)
    worst = int(np.argmax(amt))
    out = {'gate': name, 'subject': subject, 'unit': unit, 'failing_frames': int(fail.sum()),
           'of_frames': int(len(fail)), 'worst_amount': _r(amount[worst]), 'worst_time_s': _r(times[worst], 4),
           'failing_times_s': [_r(t, 4) for t in times[fail]]}
    if extra:
        out.update(extra(worst))
    return out


def evaluate(problem, placement, frames=None):
    """Score one placement {group: Rigid} on the ACTUAL samples. Returns (gates, metrics, penalty).
    `frames` limits the skin/collision frames (ranking only); reach and key use every frame."""
    fi = np.arange(len(problem.times)) if frames is None else np.asarray(frames)
    skin_fi = fi
    times = problem.times[fi]
    tb, tc, tk = (placement.get(g, IDENTITY) for g in GROUPS)
    if tb.dz != 0:
        raise ValueError('Body dz is fixed at 0: no global body lift')
    gates, metrics, penalty = [], {'patches': {}}, 0.
    if problem.input_problems:
        gates.append({'gate': 'inputs_incomplete', 'subject': 'export', 'unit': 'issues',
                      'worst_amount': len(problem.input_problems), 'issues': list(problem.input_problems)})

    delta = float(placement.get('support_delta_cm', 0.))
    for name in PATCHES:
        p = tb.apply(problem.patch_pos[name][fi])
        if name in LEG_OF:
            p = p + _leg_shift(placement, 1, np.array([LEG_OF[name]]))[0]
        facing = problem.patch_nrm[name][fi][..., 2] <= FACING_DOWN_MAX_NZ   # horizontal yaw keeps N.z
        low, high = seat_contact.band(name)
        if name in SEAT_PATCHES:
            q = tc.inverse(p)
            found, top = problem.cushion.height(q[..., :2])
            gap = q[..., 2] - top.reshape(q.shape[:2])
        else:
            found, top = support_height(problem, p[..., :2], delta)
            gap = p[..., 2] - top.reshape(p.shape[:2])
        found = found.reshape(p.shape[:2])
        over = facing & found
        band = over & (gap >= low) & (gap <= high)
        n, mn, p50, nb = _patch_stats(gap, over, band)
        nfacing = facing.sum(axis=1)
        overlap = np.where(nfacing > 0, n / np.maximum(nfacing, 1), 0.)
        cov = np.where(n > 0, nb / np.maximum(n, 1), 0.)
        enough = n >= MIN_PATCH_VERTICES
        surface = 'cushion' if name in SEAT_PATCHES else 'floor support'
        checks = [_gate('patch_not_over_surface', name, (MIN_PATCH_VERTICES - n).astype(float), ~enough, times, 'vertices short',
                        lambda w: {'over_surface_vertices': int(n[w]), 'facing_vertices': int(nfacing[w]),
                                   'horizontal_overlap_fraction': _r(overlap[w]), 'surface': surface}),
                  _gate('penetration', name, low - mn, enough & (mn < low), times, 'cm below band',
                        lambda w: {'min_gap_cm': _r(mn[w]), 'band_cm': [low, high]})]
        # Every patch is a LOCAL support patch (validate_unreal_seat_contact.py, 9ff9880): nothing deeper than the
        # band's lower edge, the lowest point within the upper edge, at least MIN_SUPPORT_VERTICES vertices in band.
        # Seat median and coverage are reported only (a curved buttock/thigh is not a flat patch).
        checks += [_gate('lowest_above_band', name, mn - high, enough & (mn > high), times, 'cm above band',
                         lambda w: {'min_gap_cm': _r(mn[w]), 'median_gap_cm': _r(p50[w]), 'band_cm': [low, high]}),
                   _gate('support_vertices', name, (MIN_SUPPORT_VERTICES - nb).astype(float),
                         enough & (nb < MIN_SUPPORT_VERTICES), times, 'vertices short',
                         lambda w: {'band_vertices': int(nb[w]), 'required': MIN_SUPPORT_VERTICES})]
        gates += [g for g in checks if g]
        with np.errstate(invalid='ignore'):
            metrics['patches'][name] = {
                'surface': surface,
                'min_horizontal_overlap_fraction': _r(overlap.min()), 'mean_horizontal_overlap_fraction': _r(overlap.mean()),
                'min_over_surface_vertices': int(n.min()),
                'worst_min_gap_cm': _r(np.nanmin(mn)) if np.isfinite(mn).any() else None,
                'max_median_gap_cm': _r(np.nanmax(p50)) if np.isfinite(p50).any() else None,
                'min_median_gap_cm': _r(np.nanmin(p50)) if np.isfinite(p50).any() else None,
                'min_coverage': _r(cov[enough].min()) if enough.any() else None,
                'min_band_vertices': int(nb.min())}
        # Ranking penalty (never a gate): a patch off its surface ranks below any patch on it, whatever its
        # vertical gap (a vertical gap cannot be closed horizontally); then band excursions, capped per frame.
        penalty += 100. * float(np.mean(~enough)) + 20. * float(np.mean(1. - overlap))
        if enough.any():
            excursion = np.maximum(0, low - mn[enough]) + np.maximum(0, mn[enough] - high)
            penalty += float(np.mean(np.minimum(excursion, 20.))) * float(np.mean(enough))
            short = (MIN_SUPPORT_VERTICES - nb[enough]) / MIN_SUPPORT_VERTICES
            penalty += 5. * float(np.mean(np.maximum(0, short))) * float(np.mean(enough))

    # Reach and key contact are cheap: always every frame, whatever subset the skin is ranked on.
    fi = np.arange(len(problem.times))
    times = problem.times
    # Reach: requested shoulder-to-target distance vs arm length, no stretch.
    shoulders = tb.apply(problem.shoulders[fi])
    targets = tk.apply(problem.targets[fi])
    vec = targets - shoulders
    dist = np.linalg.norm(vec, axis=2)
    excess = dist - problem.arm_cm[None, :]
    metrics['reach'] = {}
    for k, side in enumerate(('left', 'right')):
        e = excess[:, k]

        def detail(w, k=k):
            return {'requested_cm': _r(dist[w, k]), 'arm_length_cm': _r(problem.arm_cm[k]),
                    'horizontal_cm': _r(np.linalg.norm(vec[w, k, :2])), 'vertical_cm': _r(vec[w, k, 2])}
        g = _gate('reach_exceeds_arm', f'{side}_hand', e, e > REACH_TOLERANCE_CM, times, 'cm over arm length', detail)
        if g:
            gates.append(g)
        metrics['reach'][side] = {'max_requested_cm': _r(dist[:, k].max()), 'arm_length_cm': _r(problem.arm_cm[k]),
                                  'frames_over_arm': int((e > REACH_TOLERANCE_CM).sum()), 'worst_excess_cm': _r(e.max())}
        penalty += 4. * float(np.maximum(e, 0).max()) + 2. * float(np.mean(e > 0))

    # Key contact: vertical, measured after the server's arm IK; horizontal placement cannot change it.
    metrics['key_contact'] = {'target_cm': KEY_CONTACT_TARGET_CM, 'keycap_top_spread_cm': _r(problem.keycap_spread_cm),
                              'invariant_under_horizontal_rigid_placement': True}
    for k, side in enumerate(('left', 'right')):
        gap = problem.key_gap[fi, k]
        for g in (_gate('key_contact_gap', f'{side}_hand', gap - KEY_GAP_MAX_CM, gap > KEY_GAP_MAX_CM + 1e-9, times,
                        'cm above the 2 mm band', lambda w, gap=gap: {'gap_cm': _r(gap[w]),
                                                                       'target_deviation_cm': _r(gap[w] - KEY_CONTACT_TARGET_CM)}),
                  _gate('key_penetration', f'{side}_hand', -gap - KEY_PENETRATION_MAX_CM, -gap > KEY_PENETRATION_MAX_CM,
                        times, 'cm beyond 0.1 cm penetration', lambda w, gap=gap: {'gap_cm': _r(gap[w])})):
            if g:
                gates.append(g)
        metrics['key_contact'][side] = {'max_gap_cm': _r(gap.max()), 'min_gap_cm': _r(gap.min()),
                                        'max_target_deviation_cm': _r(np.abs(gap - KEY_CONTACT_TARGET_CM).max())}
    _, on_caps = problem.keycaps.height(problem.targets[fi][..., :2].reshape(-1, 2))  # moves with the keycaps
    metrics['key_contact']['targets_over_keycaps_fraction'] = _r(np.mean(np.isfinite(on_caps)))

    # Collision: every body point vs every rigid primitive, and furniture vs furniture.
    fi = skin_fi
    times = problem.times[fi]
    pts = tb.apply(problem.collision_pts[fi]) + _leg_shift(placement, problem.collision_pts.shape[1], problem.collision_leg)
    transforms = {'chair': tc, 'keyboard': tk, 'static': IDENTITY}
    metrics['collision'] = {}
    for prim in problem.primitives:
        local = transforms[prim.group].inverse(pts)
        depth = prim.depth(local).reshape(pts.shape[:2])
        allowed = max(prim.allowed_cm, BODY_COLLISION_ALLOWED_CM)
        inside = depth > allowed + 1e-9
        worst = np.where(inside, depth, 0.).max(axis=1)
        count = inside.sum(axis=1)
        g = _gate('body_collision', f'{prim.group}:{prim.name}', worst - allowed, count > 0, times, 'cm inside',
                  lambda w: {'vertices_inside': int(count[w]), 'allowed_cm': allowed})
        if g:
            gates.append(g)
        metrics['collision'][f'{prim.group}:{prim.name}'] = {'max_depth_cm': _r(worst.max()), 'frames': int((count > 0).sum())}
        penalty += 5. * float(worst.max()) + 5. * float(np.mean(count > 0))
    prims = problem.primitives
    for i in range(len(prims)):
        for j in range(i + 1, len(prims)):
            a, b = prims[i], prims[j]
            if a.group == b.group:
                continue
            ta, tbb = transforms[a.group], transforms[b.group]
            if a.box is not None and b.box is not None:
                depth, method = _box_sat_depth(a, ta, b, tbb), 'exact box SAT'
            else:
                d1 = b.depth(tbb.inverse(ta.apply(a.vertices))).max()
                d2 = a.depth(ta.inverse(tbb.apply(b.vertices))).max()
                depth, method = max(d1, d2), 'vertex containment (hull)'
            if depth > 1e-9:
                gates.append({'gate': 'furniture_overlap', 'subject': f'{a.group}:{a.name} x {b.group}:{b.name}',
                              'unit': 'cm', 'worst_amount': _r(depth), 'method': method,
                              'failing_frames': int(len(times)), 'of_frames': int(len(times))})
                penalty += 5. * depth
    if not problem.primitives:
        gates.append({'gate': 'collision_not_measured', 'subject': 'scene', 'unit': 'n/a', 'worst_amount': None})
    return gates, metrics, penalty


# ---------------------------------------------------------------- search
@dataclass(frozen=True)
class SearchConfig:
    xy_bound_cm: float = 40.
    yaw_bound_deg: float = 10.
    coarse_xy_step_cm: float = 4.
    coarse_yaw_step_deg: float = 2.5
    min_xy_step_cm: float = .25
    min_yaw_step_deg: float = .125
    refine_seeds: int = 6
    top_n: int = 5
    coarse_frame_stride: int = 10
    families: tuple = FAMILIES
    leg_dz_bound_cm: float = 6.          # per-leg rigid leg-chain translation bounds (leg support family)
    leg_xy_bound_cm: float = 0.          # horizontal leg translation off by default
    leg_xy_step_cm: float = .5

    def to_json(self):
        return {k: (list(v) if isinstance(v, tuple) else v) for k, v in self.__dict__.items()}


def _pivot(problem, family):
    if family == 'body':
        return (float(problem.body_location[0]), float(problem.body_location[1]))
    return problem.chair_pivot if family == 'chair' else problem.keyboard_pivot


def _chair_dz(problem, rigid, frames):
    """Chair lift within the REAL height adjustment only, chosen from the seat gaps like propose_vertical_anchor."""
    lo_adj, hi_adj = problem.chair_height_range
    if lo_adj == hi_adj == 0:
        return 0., None
    need = _needed_chair_dz(problem, rigid, frames)
    if need is None:
        return 0., need
    lo, hi = need
    if lo <= hi:
        dz = 0. if lo <= 0 <= hi else (lo if lo > 0 else hi)
    else:
        dz = (lo + hi) / 2
    return float(min(max(dz, lo_adj), hi_adj)), need


def _needed_chair_dz(problem, rigid, frames):
    """[lo, hi] chair lift (cm) that puts every seat patch's lowest point in band, or None if off-surface."""
    fi = np.arange(len(problem.times)) if frames is None else np.asarray(frames)
    lo, hi = -math.inf, math.inf
    for name in SEAT_PATCHES:
        p = problem.patch_pos[name][fi]
        facing = problem.patch_nrm[name][fi][..., 2] <= FACING_DOWN_MAX_NZ
        q = rigid.inverse(p)
        found, top = problem.cushion.height(q[..., :2])
        found = found.reshape(p.shape[:2])
        gap = q[..., 2] - top.reshape(p.shape[:2])
        over = facing & found
        n, mn, p50, _ = _patch_stats(gap, over, over)
        ok = n >= MIN_PATCH_VERTICES
        if not ok.any():
            return None
        low, high = SEAT_BAND_CM
        lo = max(lo, float(np.max(mn[ok] - high)))      # lifting the chair by dz lowers every gap by dz
        hi = min(hi, float(np.min(mn[ok] - low)))
    return (lo, hi)


def _placement(family, rigid):
    return {family: rigid}


def _score_key(params, penalty):
    disp = abs(params[0]) + abs(params[1]) + abs(params[2]) * .1
    return (round(penalty, 9), round(disp, 9), tuple(round(v, 6) for v in params))


def _family_eval(problem, family, params, frames):
    dx, dy, yaw = params
    rigid = Rigid(dx, dy, 0., yaw, _pivot(problem, family))
    if family == 'chair':
        dz, _ = _chair_dz(problem, rigid, frames)
        rigid = Rigid(dx, dy, dz, yaw, rigid.pivot)
    gates, metrics, penalty = evaluate(problem, _placement(family, rigid), frames)
    return rigid, gates, metrics, penalty


def _grid(bound, step):
    n = int(math.floor(bound / step + 1e-9))
    return [round(k * step, 9) for k in range(-n, n + 1)]


def _search(problem, family, config, objective, frames):
    """Deterministic grid then pattern-search refinement; returns sorted [(key, params)]."""
    seen = {}

    def score(params):
        params = tuple(round(v, 6) for v in params)
        if params not in seen:
            seen[params] = _score_key(params, objective(params))
        return seen[params]

    for dx in _grid(config.xy_bound_cm, config.coarse_xy_step_cm):
        for dy in _grid(config.xy_bound_cm, config.coarse_xy_step_cm):
            for yaw in _grid(config.yaw_bound_deg, config.coarse_yaw_step_deg):
                score((dx, dy, yaw))
    seeds = [p for _, p in sorted((k, p) for p, k in seen.items())][:config.refine_seeds]
    for seed in seeds:
        cur, sxy, syaw = seed, config.coarse_xy_step_cm / 2, config.coarse_yaw_step_deg / 2
        while True:
            best = cur
            for axis, step in ((0, sxy), (1, sxy), (2, syaw)):
                for sign in (-1, 1):
                    cand = list(cur)
                    cand[axis] += sign * step
                    bound = config.yaw_bound_deg if axis == 2 else config.xy_bound_cm
                    if abs(cand[axis]) > bound + 1e-9:
                        continue
                    if score(cand) < score(best):
                        best = tuple(round(v, 6) for v in cand)
            if best != cur:
                cur = best
                continue
            if sxy <= config.min_xy_step_cm and syaw <= config.min_yaw_step_deg:
                break
            sxy, syaw = max(sxy / 2, config.min_xy_step_cm), max(syaw / 2, config.min_yaw_step_deg)
    return sorted((k, p) for p, k in seen.items())


def _coarse_frames(problem, stride):
    """Skin/collision frames used for RANKING only (reach and key gaps always use every frame);
    every reported candidate is re-scored on all frames."""
    base = set(range(0, len(problem.times), max(1, stride)))
    base.add(len(problem.times) - 1)
    return np.array(sorted(base))


def _candidate(problem, family, rigid, gates, metrics, penalty, transforms=None):
    transforms = {family: rigid} if transforms is None else transforms
    moved = {}
    for group, t in transforms.items():
        actor = problem.actors.get('chair_component' if group == 'chair' else group)
        if actor and actor.get('location_cm') is not None:
            loc = t.apply(np.asarray(actor['location_cm'], dtype=float))
            moved[group] = {'location_cm': [_r(v) for v in loc],
                            'yaw_deg': _r(actor['yaw_deg'] + t.yaw) if actor.get('yaw_deg') is not None else None,
                            'from_location_cm': [_r(v) for v in actor['location_cm']]}
    return {'family': family, 'transforms': {g: t.to_json() for g, t in transforms.items()},
            'body': {'dz_cm': 0.0, 'scaled': False, 'per_bone_changes': False,
                     'moved_horizontally': 'body' in transforms and not transforms['body'].is_identity()},
            'moved_world_transforms': moved,
            'passing': not gates, 'failing_gates': gates, 'failing_gate_count': len(gates),
            'metrics': metrics, 'rank_penalty': _r(penalty), 'verified': False, 'requires_server_reaudit': True}


def _reach_objective(problem, family):
    def objective(params):
        rigid = Rigid(params[0], params[1], 0., params[2], _pivot(problem, family))
        tb = rigid if family == 'body' else IDENTITY
        tk = rigid if family == 'keyboard' else IDENTITY
        e = np.linalg.norm(tk.apply(problem.targets) - tb.apply(problem.shoulders), axis=2) - problem.arm_cm[None, :]
        return 100. * float(np.maximum(e, 0).max()) + float((e > REACH_TOLERANCE_CM).sum())
    return objective


def solve(problem, config=SearchConfig()):
    """Propose ranked rigid horizontal placements. Never verifies; see module docstring."""
    for family in config.families:
        if family not in FAMILIES:
            raise ValueError(f'unknown family {family}')
    frames = _coarse_frames(problem, config.coarse_frame_stride)
    gates0, metrics0, pen0 = evaluate(problem, {})
    result = {'schema': SCHEMA_OUT, 'verified': False, 'requires_server_reaudit': True,
              'claim': 'candidates only; nothing here is a seat or keyboard verification',
              'inputs': {'digests': problem.digests, 'chair_component': problem.chair_component,
                         'cushion_projected_area_cm2': _r(problem.cushion_area_cm2),
                         'sole_membership': problem.sole_membership, 'frames': int(len(problem.times)),
                         'body_location_cm': [_r(v) for v in problem.body_location], 'body_yaw_deg': problem.body_yaw,
                         'chair_height_adjustment_cm': list(problem.chair_height_range),
                         'chair_height_adjustment_source': problem.chair_height_source,
                         'input_problems': list(problem.input_problems)},
              'constants': {'seat_band_cm': list(SEAT_BAND_CM), 'sole_band_cm': list(SOLE_BAND_CM),
                            'min_patch_vertices': MIN_PATCH_VERTICES, 'min_band_coverage_reported_only': MIN_BAND_COVERAGE,
                            'min_support_vertices': MIN_SUPPORT_VERTICES,
                            'facing_down_max_normal_z': FACING_DOWN_MAX_NZ, 'key_gap_max_cm': KEY_GAP_MAX_CM,
                            'key_penetration_max_cm': KEY_PENETRATION_MAX_CM, 'key_contact_target_cm': KEY_CONTACT_TARGET_CM,
                            'reach_tolerance_cm': REACH_TOLERANCE_CM, 'body_collision_allowed_cm': BODY_COLLISION_ALLOWED_CM},
              'search': config.to_json(),
              'baseline': _candidate(problem, 'baseline', IDENTITY, gates0, metrics0, pen0, transforms={}),
              'families': {}}
    best = {}
    for family in config.families:
        ranked = _search(problem, family, config, lambda p, f=family: _family_eval(problem, f, p, frames)[3], frames)
        finals, seen = [], set()
        for _, params in ranked[:max(config.top_n * 3, config.refine_seeds)]:
            rigid, gates, metrics, penalty = _family_eval(problem, family, params, None)
            sig = tuple(round(v, 3) for v in (rigid.dx, rigid.dy, rigid.dz, rigid.yaw))
            if sig in seen:
                continue
            seen.add(sig)
            finals.append((_score_key(params, penalty), _candidate(problem, family, rigid, gates, metrics, penalty), rigid))
        finals.sort(key=lambda x: (not x[1]['passing'], x[0]))
        cands = [c for _, c, _ in finals[:config.top_n]]
        best[family] = finals[0][2]
        entry = {'pivot_cm': list(_pivot(problem, family)), 'candidates': cands,
                 'any_passing': any(c['passing'] for c in cands)}
        if family == 'chair':
            need = _needed_chair_dz(problem, Rigid(best['chair'].dx, best['chair'].dy, 0., best['chair'].yaw,
                                                   best['chair'].pivot), None)
            entry['chair_dz_needed_for_seat_band_cm'] = None if need is None else [_r(need[0]), _r(need[1])]
            entry['chair_dz_needed_note'] = (
                'lift range (cm) that would put every seat patch lowest point in band at the best horizontal placement; '
                'empty (lo > hi) means no single chair height does, so pose work is needed; outside the stated real '
                'chair adjustment it is NOT applied (body dz is forbidden)')
            entry['reach_note'] = 'chair placement moves neither the shoulders nor the keyboard: reach is unchanged'
        if family in ('body', 'keyboard'):
            reach = _search(problem, family, config, _reach_objective(problem, family), None)
            params = reach[0][1]
            rigid, gates, metrics, penalty = _family_eval(problem, family, params, None)
            entry['reach_best'] = _candidate(problem, family, rigid, gates, metrics, penalty)
            entry['trade_off'] = _trade_off(problem, family, best[family], rigid)
        result['families'][family] = entry
    if 'chair' in best and 'keyboard' in best:
        kb = result['families']['keyboard']['reach_best']['transforms']['keyboard']
        tk = Rigid(kb['dx_cm'], kb['dy_cm'], 0., kb['yaw_deg'], tuple(kb['pivot_cm']))
        transforms = {'chair': best['chair'], 'keyboard': tk}
        gates, metrics, penalty = evaluate(problem, transforms)
        result['combined_chair_and_keyboard'] = _candidate(problem, 'chair+keyboard', None, gates, metrics, penalty,
                                                           transforms=transforms)
        result['combined_chair_and_keyboard']['note'] = (
            'TWO rigid units (best chair candidate + reach-best keyboard/desk); the body is untouched')
    base = {'chair': best['chair']} if 'chair' in best else {}
    result['leg_support'] = _leg_support(problem, base, config)
    result['leg_support']['note'] = 'on top of the best chair candidate; the body root is not moved'
    result['support_surface'] = _support_surface(problem, base)
    result['irreducible_residuals'] = _irreducible(problem, result)
    return result


def _sole_frame_min(problem, placement, name):
    """Per-frame lowest gap (cm) of the facing plantar vertices over a support, and their world z."""
    p = placement.get('body', IDENTITY).apply(problem.patch_pos[name])
    p = p + _leg_shift(placement, 1, np.array([LEG_OF[name]]))[0]
    facing = problem.patch_nrm[name][..., 2] <= FACING_DOWN_MAX_NZ
    found, top = support_height(problem, p[..., :2], float(placement.get('support_delta_cm', 0.)))
    found, top = found.reshape(p.shape[:2]), top.reshape(p.shape[:2])
    ok = facing & found
    gap = np.where(ok, p[..., 2] - top, np.inf).min(axis=1)
    z = np.where(ok, p[..., 2], np.inf).min(axis=1)
    fixed = None
    if problem.support is not None:
        f, h = problem.support.height(p[..., :2])
        fixed = np.where(f.reshape(p.shape[:2]) & ok, h.reshape(p.shape[:2]), -np.inf).max(axis=1)
    return gap, z, fixed


def _with(base, **extra):
    out = dict(base)
    out.update(extra)
    return out


def _leg_support(problem, base, config):
    """Per-leg RIGID translation of the whole leg chain (thigh, calf, foot, toe as one unit; bone lengths kept),
    vertical by the analytic support-patch rule and optionally horizontal on a bounded grid. Any nonzero
    translation opens the hip joint by its length: that is reported as a failing residual and the candidate
    is flagged as needing a real pose solution (pelvis/hip rotation keeping bone lengths, or another clip)."""
    legs, detail = {}, {}
    for k, side in enumerate(LEGS):
        name = f'{side}_sole'
        best = None
        for dx in _grid(config.leg_xy_bound_cm, config.leg_xy_step_cm) if config.leg_xy_bound_cm > 0 else [0.]:
            for dy in _grid(config.leg_xy_bound_cm, config.leg_xy_step_cm) if config.leg_xy_bound_cm > 0 else [0.]:
                trial = _with(base, **{f'{side}_leg': Rigid(dx, dy, 0.)})
                mn, _, _ = _sole_frame_min(problem, trial, name)
                if not np.all(np.isfinite(mn)):
                    continue
                lo, hi = float(np.max(-mn)), float(np.min(SOLE_BAND_CM[1] - mn))
                key = (lo > hi, abs(lo), abs(dx) + abs(dy), dx, dy)
                if best is None or key < best[0]:
                    best = (key, dx, dy, lo, hi)
        if best is None:
            detail[side] = {'feasible': False, 'reason': 'sole not over any support surface'}
            continue
        _, dx, dy, lo, hi = best
        dz = min(max(lo, -config.leg_dz_bound_cm), config.leg_dz_bound_cm)
        legs[f'{side}_leg'] = Rigid(dx, dy, dz)
        detail[side] = {'translation_cm': [_r(dx), _r(dy), _r(dz)],
                        'needed_vertical_range_cm': [_r(lo), _r(hi)],
                        'feasible_within_bounds': bool(lo <= hi and abs(lo) <= config.leg_dz_bound_cm),
                        'hip_joint_discontinuity_cm': _r(math.sqrt(dx * dx + dy * dy + dz * dz)),
                        'bone_lengths_preserved': True}
    placement = _with(base, **legs)
    gates, metrics, penalty = evaluate(problem, placement)
    for side, d in detail.items():
        gap = d.get('hip_joint_discontinuity_cm') or 0.
        if gap > 0:
            gates.append({'gate': 'hip_joint_discontinuity', 'subject': f'{side}_leg', 'unit': 'cm',
                          'worst_amount': gap, 'failing_frames': int(len(problem.times)),
                          'of_frames': int(len(problem.times)),
                          'note': 'UpLeg root separated from the pelvis socket: not a pure rigid placement; needs a '
                                  'real pose solution (pelvis/hip rotation keeping bone lengths) or a different clip'})
    transforms = {g: placement[g] for g in GROUPS if g in placement}
    cand = _candidate(problem, 'leg_support', None, gates, metrics, penalty, transforms=transforms)
    discontinuous = any((d.get('hip_joint_discontinuity_cm') or 0) > 0 for d in detail.values())
    cand['legs'] = detail
    cand['pure_rigid_placement'] = not discontinuous
    cand['requires_pose_solution'] = discontinuous
    cand['body']['per_bone_changes'] = discontinuous
    cand['body']['leg_chain_translation'] = discontinuous
    return cand


def _support_surface(problem, base):
    """Change the support itself (a real rug/footrest of measured thickness): no body change at all."""
    feet, common = {}, [-math.inf, math.inf]
    for side in LEGS:
        mn, z, fixed = _sole_frame_min(problem, base, f'{side}_sole')
        if not np.all(np.isfinite(z)):
            feet[side] = {'feasible': False, 'reason': 'sole not over any support surface'}
            common = [math.inf, -math.inf]
            continue
        lo, hi = float(np.max(z) - SOLE_BAND_CM[1]), float(np.min(z))      # support top z that satisfies every frame
        floor = float(np.max(fixed)) if fixed is not None and np.isfinite(fixed).any() else None
        feet[side] = {'lowest_plantar_z_cm': [_r(np.min(z)), _r(np.max(z))],
                      'needed_support_top_z_cm': [_r(lo), _r(hi)],
                      'fixed_floor_under_sole_z_cm': _r(floor) if floor is not None else None,
                      'feasible': bool(lo <= hi and (floor is None or hi >= floor - 1e-9)),
                      'reason': None if lo <= hi and (floor is None or hi >= floor - 1e-9) else
                      ('lowest plantar point varies more than 1 cm over the clip' if lo > hi else
                       'needed support top is below the fixed floor: no real support object can do it')}
        common = [max(common[0], lo), min(common[1], hi)]
    alternatives = []
    for alt in problem.support_alternatives:
        gates, metrics, penalty = evaluate(problem, _with(base, support_delta_cm=alt['delta_cm']))
        cand = _candidate(problem, 'support_surface', None, gates, metrics, penalty,
                          transforms={g: base[g] for g in GROUPS if g in base})
        cand['support_change'] = alt
        alternatives.append(cand)
    return {'feet': feet, 'common_needed_support_top_z_cm': [_r(common[0]), _r(common[1])],
            'one_surface_for_both_feet_feasible': bool(common[0] <= common[1] and all(f['feasible'] for f in feet.values())),
            'alternatives_evaluated': alternatives,
            'note': 'a support change must be a real object of measured thickness; a proposed height is not one'}


def _summary(gates, metrics):
    return {'failing_gates': sorted({f'{g["gate"]}:{g["subject"]}' for g in gates}),
            'reach_frames_over_arm': {s: metrics['reach'][s]['frames_over_arm'] for s in ('left', 'right')},
            'reach_worst_excess_cm': {s: metrics['reach'][s]['worst_excess_cm'] for s in ('left', 'right')},
            'seat_min_overlap_fraction': {n: metrics['patches'][n]['min_horizontal_overlap_fraction'] for n in SEAT_PATCHES},
            'sole_min_overlap_fraction': {n: metrics['patches'][n]['min_horizontal_overlap_fraction'] for n in SOLE_PATCHES}}


def _trade_off(problem, family, seat_best, reach_best):
    """Straight path from the seat-ranked best to the reach-best placement: what each end gives up."""
    steps = []
    for k in range(5):
        f = k / 4
        rigid = Rigid(*(a + (b - a) * f for a, b in ((seat_best.dx, reach_best.dx), (seat_best.dy, reach_best.dy))),
                      0. if family != 'chair' else seat_best.dz,
                      seat_best.yaw + (reach_best.yaw - seat_best.yaw) * f, seat_best.pivot)
        gates, metrics, _ = evaluate(problem, {family: rigid})
        steps.append({'fraction_toward_reach_best': f, 'transform': rigid.to_json(), **_summary(gates, metrics)})
    return {'family': family, 'path': steps,
            'reading': 'fraction 0 is the best-ranked placement for this family, 1 the placement that minimises reach '
                       'excess alone; a gate that clears at one end and fails at the other is the trade-off'}


def _irreducible(problem, result):
    out = []
    vec = problem.targets - problem.shoulders
    vertical = np.abs(vec[..., 2]) - problem.arm_cm[None, :]
    if (vertical > REACH_TOLERANCE_CM).any():
        f, k = np.unravel_index(np.argmax(vertical), vertical.shape)
        out.append({'residual': 'reach_vertical_component_exceeds_arm', 'scope': 'any horizontal placement, any bounds',
                    'frames': int((vertical > 0).any(axis=1).sum()), 'worst_excess_cm': _r(vertical[f, k]),
                    'worst_time_s': _r(problem.times[f], 4), 'side': ('left', 'right')[k]})
    reach_fail = {}
    for family, entry in result['families'].items():
        cand = entry.get('reach_best') or entry['candidates'][0]
        rg = [g for g in cand['failing_gates'] if g['gate'] == 'reach_exceeds_arm']
        reach_fail[family] = rg
    base_reach = [g for g in result['baseline']['failing_gates'] if g['gate'] == 'reach_exceeds_arm']
    if base_reach:
        for family, rg in reach_fail.items():
            if rg:
                out.append({'residual': 'reach_exceeds_arm', 'scope': f'{family} family within the search bounds',
                            'reason': 'chair placement does not move shoulders or keyboard' if family == 'chair'
                            else 'best reach-only placement within bounds still over arm length',
                            'gates': rg})
        if all(reach_fail.values()):
            out.append({'residual': 'reach_exceeds_arm', 'scope': 'every single rigid horizontal family searched',
                        'frames_over_arm_at_baseline': {g['subject']: g['failing_frames'] for g in base_reach},
                        'worst_excess_at_baseline_cm': {g['subject']: g['worst_amount'] for g in base_reach},
                        'failing_times_s': {g['subject']: g['failing_times_s'] for g in base_reach}})
    key = [g for g in result['baseline']['failing_gates'] if g['gate'] in ('key_contact_gap', 'key_penetration')]
    if key:
        out.append({'residual': 'key_contact', 'scope': 'any horizontal rigid placement',
                    'reason': 'the post-IK key gap is vertical; the 0.08 cm target and 0.2 cm band are unchanged',
                    'keycap_top_spread_cm': _r(problem.keycap_spread_cm), 'gates': key})
    sole_gates = ('patch_not_over_surface', 'penetration', 'lowest_above_band', 'support_vertices')
    soles = [g for g in result['baseline']['failing_gates'] if g['gate'] in sole_gates and g['subject'] in SOLE_PATCHES]
    if soles and all(any(g['gate'] in sole_gates and g['subject'] in SOLE_PATCHES for g in e['candidates'][0]['failing_gates'])
                     for e in result['families'].values()):
        leg = result.get('leg_support', {})
        out.append({'residual': 'sole_support', 'scope': 'every rigid horizontal family (a flat floor does not change)',
                    'gates': soles,
                    'leg_support_option': {s: {k: d.get(k) for k in ('translation_cm', 'hip_joint_discontinuity_cm')}
                                           for s, d in leg.get('legs', {}).items()},
                    'leg_support_requires_pose_solution': leg.get('requires_pose_solution'),
                    'support_surface_option': {s: {k: f.get(k) for k in ('needed_support_top_z_cm', 'feasible', 'reason')}
                                               for s, f in result.get('support_surface', {}).get('feet', {}).items()}})
    chair = result['families'].get('chair')
    if chair:
        need = chair.get('chair_dz_needed_for_seat_band_cm')
        lo_adj, hi_adj = problem.chair_height_range
        if need is None:
            out.append({'residual': 'seat_patch_off_cushion', 'scope': 'best chair placement within bounds'})
        elif need[0] > need[1] or need[0] > hi_adj + 1e-9 or need[1] < lo_adj - 1e-9:
            out.append({'residual': 'seat_vertical_gap', 'scope': 'best chair placement with the stated chair height range',
                        'needed_chair_dz_cm': need, 'allowed_chair_dz_cm': [lo_adj, hi_adj],
                        'reason': 'horizontal placement cannot close a vertical gap; body dz is forbidden'})
    return out


# ---------------------------------------------------------------- CLI
def _load(path):
    data = Path(path).read_bytes()
    return json.loads(data), hashlib.sha256(data).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--skin', required=True)
    ap.add_argument('--chair', required=True, help='private-audit/native-chair-surface.json')
    ap.add_argument('--scene', required=True)
    ap.add_argument('--keyboard', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--families', default=','.join(FAMILIES))
    ap.add_argument('--top', type=int, default=5)
    ap.add_argument('--xy-bound', type=float, default=40.)
    ap.add_argument('--yaw-bound', type=float, default=10.)
    ap.add_argument('--xy-step', type=float, default=4.)
    ap.add_argument('--yaw-step', type=float, default=2.5)
    args = ap.parse_args(argv)
    loaded = {k: _load(getattr(args, k)) for k in ('skin', 'chair', 'scene', 'keyboard')}
    problem = build_problem(*(loaded[k][0] for k in ('skin', 'chair', 'scene', 'keyboard')),
                            digests={k: v[1] for k, v in loaded.items()})
    config = SearchConfig(xy_bound_cm=args.xy_bound, yaw_bound_deg=args.yaw_bound, coarse_xy_step_cm=args.xy_step,
                          coarse_yaw_step_deg=args.yaw_step, top_n=args.top, families=tuple(args.families.split(',')))
    result = solve(problem, config)
    Path(args.out).write_text(json.dumps(result, indent=1, sort_keys=True) + '\n')
    for family, entry in result['families'].items():
        c = entry['candidates'][0]
        print(f'{family}: best {c["transforms"][family]} passing={c["passing"]} failing={c["failing_gate_count"]}')
    print(f'irreducible residuals: {len(result["irreducible_residuals"])}; verified=false; server re-audit required')
    return 0


if __name__ == '__main__':
    sys.exit(main())
