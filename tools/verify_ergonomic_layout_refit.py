"""INDEPENDENT verifier of the ergonomic layout refit proposal (source only, local math; never a receipt).

It is deliberately separate from the layout solver (tools/solve_seated_typing_arm_ik.py and the refit agent's changes):
no solver function, constant or geometry JSON is imported or read for a verdict. The geometry is rebuilt here from the
pinned origin/main bytes:

* DESK: origin/main web/house/assets/real-linea140/originalsource.glb (sha256 pinned), placed by root's place_bytes()
  mapping whose constants (SCALE, DESK_Y, the root node translation) are parsed from origin/main
  tools/prepare_real_linea140_placement.py bytes (sha256 recorded): UE cm = 100 * (tx + S x, DESK_Y + S z, ty + S y).
  Every node's triangles are kept; node AABBs are the (conservative) clearance volumes; the worktop's flat top faces
  (the support plane, excluding eased edges and the grommet opening) are the keyboard/mouse support.
* OTHER DESK ITEMS: the monitor frame and stand as origin/main web/house/home.js authors them (box() calls), rigidly
  lifted by origin/main docs/proposed/monitor-support-fix-20261015.json (desk top - stand bottom); root's device XY
  envelopes from place_bytes' device_bounds (monitor, phone); the clamp lamp AABB of root's lamp mount record; the
  grommet rim (LINEA node).
* CHAIR: origin/main web/room/chair_owner.glb (every triangle: shell, arm pads, back mesh, base, castors, gas lift) at
  root's measured native transform (+ the proposal's declared lift), checked against root's measured native shell.
* KEYBOARD / MOUSE: origin/main GLBs at web/house/home.js furnished() placement plus the proposal's declared deltas.
* BODY: the owner skin read back through the existing fitter path (export_seat_fit_source / fit_seat_pelvis_pitch /
  fit_seat_pose_trial: compact source, LBS, Trial.seat/soles patch metrics) and the seat rule judged by origin/main's
  own validate_unreal_seat_contact.validate() bytes (sha256 dd95f1b1..., as tools/recheck_seat_fit_main_rule.py does).

World model (the one the seated pipeline uses; stated so it can be checked): a clip GLB's joint worlds are in the
solver frame (body at export_seat_fit_source.BODY_CM, chair at chair_start + r0). At frame f the chair is at
chair_start + roll(f) and the body rides with it: body shift(f) = roll(f) - r0 (UE cm, horizontal).

    python tools/verify_ergonomic_layout_refit.py --proposal docs/proposed/ergonomic-layout-refit/<proposal>.json \
        --out-dir docs/proposed/ergonomic-layout-refit-verification

`ready` is never written true: nothing native is verified here.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import operator
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

SCHEMA = 'sub01.ergonomic-layout-refit-verification.v1'
MAIN_REF = 'origin/main'
PINS = {   # origin/main path -> sha256 of the bytes this verifier accepts
    'web/house/assets/real-linea140/originalsource.glb': '99bdf3fd42eea5fc4cb2fadd52c8cae18c4459a94000b85f7df4c515234ba43d',
    'web/room/chair_owner.glb': 'd27084af80035c7ab278f90daf77a422fabe738095dad0b015a531f86249e2dc',
    'web/house/assets/keyboard/keyboard.glb': '86989af770a2caa655680bdb7f0a9bbc13c417795ab8c9c734d66fcc44b89fdf',
    'web/room/mouse.glb': 'ad9ee242415eb5de55781f8bf7befb70dcbe9dba03d1ccb587a58b5e6cd1fcec',
    'tools/validate_unreal_seat_contact.py': 'dd95f1b1a8c3fc9a7d08b6d599985b86440c84752d85ae9f12fa8d480397a18f',
}
MAIN_SOURCES = {   # recorded (sha256 + last commit), parsed for constants
    'placement': 'tools/prepare_real_linea140_placement.py',
    'home_js': 'web/house/home.js',
    'monitor_fix': 'docs/proposed/monitor-support-fix-20261015.json',
    'lamp_mount': 'docs/proposed/real-linea-grommet-lamp-mount-20261014.json',
    'linea_record': 'docs/proposed/real-linea140-guarded-placement-20261014.json',
}
CHAIR_REPORT = ROOT / 'docs/proposed/native-chair-measured/20261014-actual-native-chair-surface.json'
FLOOR_CM = 2.5
CHAIR_SHELL_TOL_CM = .5          # root's native LOD0 shell vertices must lie on the source surface within this
ROLES = ('SitDown_seated', 'SeatedIdle', 'SitToType_seated', 'DeskTyping_seated', 'TypeToSit_seated', 'GetUp_seated')
SEQUENCE = (('SitDown_seated', 'SeatedIdle'), ('SeatedIdle', 'SeatedIdle'), ('SeatedIdle', 'SitToType_seated'),
            ('SitToType_seated', 'DeskTyping_seated'), ('DeskTyping_seated', 'DeskTyping_seated'),
            ('DeskTyping_seated', 'TypeToSit_seated'), ('TypeToSit_seated', 'SeatedIdle'), ('SeatedIdle', 'GetUp_seated'))
CAPTURES = {'DeskTyping_seated': 'web/room/mh_mx/room_mx_typing.glb', 'SitToType_seated': 'web/room/mh_mx/room_mx_sit_to_type.glb',
            'TypeToSit_seated': 'web/room/mh_mx/room_mx_type_to_sit.glb', 'SeatedIdle': 'web/room/mh_mx/room_seated_idle.glb',
            'SitDown_seated': 'web/room/mh_mx/room_mx_stand_to_sit.glb', 'GetUp_seated': 'web/room/mh_mx/room_mx_sit_to_stand.glb'}

# acceptance thresholds (this verifier's, stated in the output)
TH = {
    'device_foot_gap_cm': (-0.01, 0.05),        # lowest device point vs the worktop top plane
    'device_slab_margin_cm': 1.0,               # device footprint inside the flat walnut top by at least this
    'device_item_margin_cm': 1.0,               # device footprint clear of other desk items' footprints
    'body_desk_clearance_cm': 0.0,              # > 0: no skin inside any desk part AABB
    'chair_desk_clearance_cm': 0.0,
    'chair_floor_gap_cm': (-1e-6, 0.01),        # castors on the floor, never below
    'sole_floor_penetration_cm': -0.01,         # lowest sole point never below the floor by more than this
    'seam_position_cm': 0.5,                    # any joint, world position jump at a clip boundary
    'seam_velocity_cm_s': 30.,                  # any body joint (fingers excluded) velocity change at a boundary
    'accel_vs_capture_peak_ratio': 1.0,         # pelvis / hand acceleration may not exceed the capture's own peak
    'ergo_elbow_above_desk_cm': (0., 12.),      # elbow joint height above the worktop top (strict target)
    'ergo_upper_arm_from_vertical_deg': 25.,
    'ergo_shoulder_elevation_vs_idle_deg': 5.,  # clavicle elevation above the seated-idle neutral (shrug)
    'ergo_wrist_flexion_deg': (-20., 20.),      # (extension, flexion), bind (straight-hand) relative
    'ergo_wrist_deviation_deg': (-20., 10.),    # (ulnar, radial)
    'ergo_frame_share': 0.95,                   # share of DeskTyping frames that must meet each ergonomic target
}


# ---------------------------------------------------------------- small utilities
def git_bytes(path, ref=MAIN_REF):
    return subprocess.run(['git', 'show', f'{ref}:{path}'], cwd=ROOT, check=True, capture_output=True).stdout


def git_last_commit(path, ref=MAIN_REF):
    r = subprocess.run(['git', 'log', '-1', '--format=%h', ref, '--', path], cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip() or None


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def pinned(path, ref=MAIN_REF):
    raw = git_bytes(path, ref)
    if sha256(raw) != PINS[path]:
        raise ValueError(f'{ref}:{path} sha256 {sha256(raw)} != pinned {PINS[path]}')
    return raw


def r_(v, d=4):
    v = float(v)
    return None if not math.isfinite(v) else (0.0 if round(v, d) == 0 else round(v, d))


def worst(values, times=None, lowest=True):
    v = np.asarray(values, float)
    ok = np.isfinite(v)
    if not ok.any():
        return None
    i = int(np.argmin(np.where(ok, v, np.inf)) if lowest else np.argmax(np.where(ok, v, -np.inf)))
    out = {'value': r_(v[i]), 'frame': i}
    if times is not None:
        out['t'] = r_(times[i], 4)
    return out


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.USub: operator.neg, ast.UAdd: operator.pos}


def arith(expr, names=None):
    """Evaluate a numeric literal expression (+ - * / and given names) without eval()."""
    names = names or {}

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.Name) and n.id in names:
            return float(names[n.id])
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        raise ValueError(f'unsupported expression {ast.dump(n)}')
    return ev(ast.parse(expr.strip(), mode='eval'))


# ---------------------------------------------------------------- a minimal GLB reader (uncompressed GLBs)
def parse_glb(raw):
    magic, _, length = struct.unpack_from('<4sII', raw, 0)
    if magic != b'glTF':
        raise ValueError('not a GLB')
    off, doc, binary = 12, None, b''
    while off < length:
        clen, ctype = struct.unpack_from('<II', raw, off)
        chunk = raw[off + 8: off + 8 + clen]
        if ctype == 0x4E4F534A:
            doc = json.loads(chunk)
        elif ctype == 0x004E4942:
            binary = chunk
        off += 8 + clen
    if any(ext in (doc.get('extensionsUsed') or []) for ext in ('EXT_meshopt_compression', 'KHR_draco_mesh_compression')):
        raise ValueError('compressed GLB: decode first')
    return doc, binary


def accessor(doc, binary, i):
    a = doc['accessors'][i]
    dt = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5122: np.int16, 5121: np.uint8, 5120: np.int8}[a['componentType']]
    width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[a['type']]
    v = doc['bufferViews'][a['bufferView']]
    item = np.dtype(dt).itemsize
    stride = v.get('byteStride', width * item)
    start = v.get('byteOffset', 0) + a.get('byteOffset', 0)
    arr = np.ndarray((a['count'], width), dtype=dt, buffer=binary, offset=start, strides=(stride, item)).astype(np.float64)
    if a.get('normalized'):          # KHR_mesh_quantization: normalized integers
        arr = np.maximum(arr / {np.uint8: 255., np.uint16: 65535., np.int16: 32767., np.int8: 127.}[dt], -1.)
    return arr[:, 0] if width == 1 else arr


def quat_matrix(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def node_local(n):
    if 'matrix' in n:
        return np.asarray(n['matrix'], float).reshape(4, 4).T
    m = np.eye(4)
    m[:3, :3] = quat_matrix(n.get('rotation', (0, 0, 0, 1))) * np.asarray(n.get('scale', (1, 1, 1)), float)[None]
    m[:3, 3] = n.get('translation', (0, 0, 0))
    return m


def node_worlds(doc):
    out = {}
    roots = doc['scenes'][doc.get('scene', 0)]['nodes']
    stack = [(r, np.eye(4)) for r in roots]
    while stack:
        i, parent = stack.pop()
        out[i] = parent @ node_local(doc['nodes'][i])
        stack += [(c, out[i]) for c in doc['nodes'][i].get('children', [])]
    return out


def glb_triangles(doc, binary):
    """[(node, node name, material name, (N, 3, 3) source-space triangles)] for every mesh node in the scene."""
    Wn = node_worlds(doc)
    rows = []
    for ni, M in sorted(Wn.items()):
        node = doc['nodes'][ni]
        if 'mesh' not in node:
            continue
        for prim in doc['meshes'][node['mesh']]['primitives']:
            P = accessor(doc, binary, prim['attributes']['POSITION'])
            P = P @ M[:3, :3].T + M[:3, 3]
            idx = accessor(doc, binary, prim['indices']).astype(int).reshape(-1, 3) if 'indices' in prim \
                else np.arange(len(P)).reshape(-1, 3)
            mat = doc['materials'][prim['material']].get('name', '') if 'material' in prim else ''
            rows.append((ni, node.get('name', ''), mat, P[idx]))
    return rows


def three_to_ue(p):
    """three.js / glTF home metres (x, y up, z) -> UE cm (x, y = z, z = y)."""
    p = np.asarray(p, float)
    return np.stack([p[..., 0], p[..., 2], p[..., 1]], -1) * 100.


# ---------------------------------------------------------------- geometry: signed distance to boxes, triangles
def box_sdf(points, lo, hi):
    """Signed distance (cm) of points to an AABB: > 0 outside, < 0 inside (depth)."""
    p = np.asarray(points, float)
    d = np.maximum(np.asarray(lo) - p, p - np.asarray(hi))
    return np.linalg.norm(np.maximum(d, 0.), axis=-1) + np.minimum(d.max(-1), 0.)


def min_box_sdf(points, boxes, reach=None):
    """Per point: the smallest signed distance to any of the (B, 2, 3) boxes and its index (reach: cap)."""
    p = np.asarray(points, float).reshape(-1, 3)
    best = np.full(len(p), np.inf if reach is None else float(reach))
    which = np.full(len(p), -1)
    for b, (lo, hi) in enumerate(boxes):
        if reach is not None:
            near = np.all((p >= lo - reach) & (p <= hi + reach), axis=1)
            if not near.any():
                continue
            idx = np.nonzero(near)[0]
            d = box_sdf(p[idx], lo, hi)
        else:
            idx = np.arange(len(p))
            d = box_sdf(p, lo, hi)
        better = d < best[idx]
        best[idx[better]], which[idx[better]] = d[better], b
    shape = np.shape(points)[:-1]
    return best.reshape(shape), which.reshape(shape)


def sample_triangles(tris, spacing):
    """Points on every triangle on a barycentric grid no coarser than `spacing` (cm); returns points and triangle ids."""
    tris = np.asarray(tris, float)
    L = np.max(np.linalg.norm(tris[:, [1, 2, 0]] - tris, axis=-1), axis=1)
    k_all = np.maximum(1, np.ceil(L / spacing)).astype(int)
    pts, ids = [], []
    for k in np.unique(k_all):
        sel = np.nonzero(k_all == k)[0]
        u, v = np.meshgrid(np.arange(k + 1) / k, np.arange(k + 1) / k)
        m = (u + v) <= 1 + 1e-9
        u, v = u[m], v[m]
        t = tris[sel]
        P = t[:, None, 0] + u[None, :, None] * (t[:, None, 1] - t[:, None, 0]) + v[None, :, None] * (t[:, None, 2] - t[:, None, 0])
        pts.append(P.reshape(-1, 3))
        ids.append(np.repeat(sel, len(u)))
    return np.concatenate(pts), np.concatenate(ids)


def closest_on_triangles(p, a, b, c):
    """Exact closest points on triangles (a, b, c) to points p (all (N, 3)); returns distance."""
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = (ab * ap).sum(-1), (ac * ap).sum(-1)
    bp = p - b
    d3, d4 = (ab * bp).sum(-1), (ac * bp).sum(-1)
    cp = p - c
    d5, d6 = (ab * cp).sum(-1), (ac * cp).sum(-1)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    out = np.empty_like(p)
    # regions (Ericson 5.1.5), evaluated in order of precedence
    with np.errstate(divide='ignore', invalid='ignore'):
        den = 1. / np.where(np.abs(va + vb + vc) < 1e-300, 1e-300, va + vb + vc)
        out[:] = a + ab * (vb * den)[:, None] + ac * (vc * den)[:, None]
        m = (va <= 0) & (d4 - d3 >= 0) & (d5 - d6 >= 0)
        w = (d4 - d3) / np.where((d4 - d3) + (d5 - d6) == 0, 1, (d4 - d3) + (d5 - d6))
        out[m] = (b + (c - b) * w[:, None])[m]
        m = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
        w = d2 / np.where(d2 - d6 == 0, 1, d2 - d6)
        out[m] = (a + ac * w[:, None])[m]
        m = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
        v = d1 / np.where(d1 - d3 == 0, 1, d1 - d3)
        out[m] = (a + ab * v[:, None])[m]
    out[(d6 >= 0) & (d5 <= d6)] = c[(d6 >= 0) & (d5 <= d6)]
    out[(d3 >= 0) & (d4 <= d3)] = b[(d3 >= 0) & (d4 <= d3)]
    out[(d1 <= 0) & (d2 <= 0)] = a[(d1 <= 0) & (d2 <= 0)]
    return np.linalg.norm(p - out, axis=-1)


def point_in_triangles_2d(pts, tris):
    """For each 2D point: inside (or on) any of the 2D triangles."""
    pts = np.asarray(pts, float)[:, None, :]
    a, b, c = (np.asarray(tris, float)[None, :, k, :2] for k in range(3))

    def cross(o, u, v):
        return (u[..., 0] - o[..., 0]) * (v[..., 1] - o[..., 1]) - (u[..., 1] - o[..., 1]) * (v[..., 0] - o[..., 0])
    s1, s2, s3 = cross(a, b, pts), cross(b, c, pts), cross(c, a, pts)
    eps = 1e-9
    inside = ((s1 >= -eps) & (s2 >= -eps) & (s3 >= -eps)) | ((s1 <= eps) & (s2 <= eps) & (s3 <= eps))
    return inside.any(axis=1)


def rect_gap(a, b):
    """Horizontal separation (cm) of two XY rectangles [[x0, y0], [x1, y1]]; negative = overlap depth."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = np.maximum(a[0] - b[1], b[0] - a[1])           # per-axis separation
    return float(np.linalg.norm(np.maximum(d, 0.))) if (d > 0).any() else float(d.max())


# ---------------------------------------------------------------- the REAL desk (root's place_bytes mapping)
def placement_constants(text):
    """SCALE, DESK_Y and the root node translation, parsed from root's prepare_real_linea140_placement.py source."""
    m = re.search(r'^SCALE\s*=\s*(.+)$', text, re.M)
    scale = arith(m.group(1))
    desk_y = arith(re.search(r'^DESK_Y\s*=\s*(.+)$', text, re.M).group(1))
    t = re.search(r"'translation'\s*:\s*\[([^\]]+)\]", text).group(1).split(',')
    translation = [arith(x, {'DESK_Y': desk_y}) for x in t]
    dev = re.search(r"device_bounds\s*=\s*(\{.+?\})\s*\n", text)
    devices = ast.literal_eval(dev.group(1)) if dev else {}
    return {'scale': scale, 'desk_y': desk_y, 'translation_m': translation, 'device_bounds_m': devices}


def part_kind(name):
    n = name.lower()
    for key, kind in (('worktop', 'worktop'), ('apron', 'apron'), ('square leg', 'leg'), ('leg shoe', 'leg'),
                      ('elastomer foot', 'leg'), ('drawer', 'drawer_carcass'), ('grommet', 'grommet'),
                      ('trough', 'cable_trough'), ('fixing', 'fixing'), ('plate', 'fixing')):
        if key in n:
            return kind
    return 'other'


def desk_geometry(ref=MAIN_REF):
    raw = pinned('web/house/assets/real-linea140/originalsource.glb', ref)
    ptxt = git_bytes(MAIN_SOURCES['placement'], ref)
    c = placement_constants(ptxt.decode())
    doc, binary = parse_glb(raw)
    S, (tx, ty, tz) = c['scale'], c['translation_m']
    parts = []
    for ni, name, mat, tri in glb_triangles(doc, binary):
        ue = np.stack([tx + S * tri[..., 0], tz + S * tri[..., 2], ty + S * tri[..., 1]], -1) * 100.
        found = next((p for p in parts if p['node'] == ni), None)
        if found:
            found['tris'] = np.concatenate([found['tris'], ue])
            continue
        parts.append({'node': ni, 'name': name, 'kind': part_kind(name), 'tris': ue})
    for p in parts:
        v = p['tris'].reshape(-1, 3)
        p['min'], p['max'] = v.min(0), v.max(0)
    top = [p for p in parts if p['kind'] == 'worktop']
    if len(top) != 1:
        raise ValueError('expected exactly one worktop node')
    top = top[0]
    tz_ = top['max'][2]
    t = top['tris']
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    flat = (np.abs(t[..., 2] - tz_) < 1e-4).all(1) & (np.linalg.norm(n, axis=1) > 1e-9)
    allv = np.concatenate([p['tris'].reshape(-1, 3) for p in parts])
    return {'parts': parts, 'worktop': top, 'top_cm': float(tz_), 'flat_top_tris': t[flat],
            'floor_cm': float(allv[:, 2].min()), 'bounds': [allv.min(0), allv.max(0)], 'constants': c,
            'source_sha256': sha256(raw), 'placement_source_sha256': sha256(ptxt)}


def desk_items(desk, ref=MAIN_REF):
    """Other desk items as UE boxes, with provenance (monitor frame + stand from home.js lifted by the support fix,
    root's device envelopes, the clamp lamp and the grommet rim)."""
    js = git_bytes(MAIN_SOURCES['home_js'], ref).decode()
    fix_raw = git_bytes(MAIN_SOURCES['monitor_fix'], ref)
    fix = json.loads(fix_raw)
    lift = float(fix['actual_source_support']['derived_delta_z_cm'])
    items = {}
    num = r'(-?[\d.]+)'
    pat = r'box\(\s*' + r'\s*,\s*'.join([num] * 6) + r'\s*,\s*M\.(\w+)'
    found = []
    for m in re.finditer(pat, js):
        w, h, d, x, y, z = map(float, m.groups()[:6])
        found.append((w, h, d, x, y, z, m.group(7), js[:m.start()].count('\n') + 1))
    # the monitor: the black 0.72 x 0.44 panel and the metal stand at the desk (x 2, z -3.3)
    mon = [f for f in found if f[6] == 'black' and abs(f[3] - 2) < 1e-9 and abs(f[5] + 3.3) < 1e-9 and f[0] > .5]
    stand = [f for f in found if f[6] == 'metal' and abs(f[3] - 2) < 1e-9 and abs(f[5] + 3.3) < 1e-9]
    if len(mon) != 1 or len(stand) != 1:
        raise ValueError('home.js monitor/stand box() calls not found uniquely')
    for key, (w, h, d, x, y, z, mat, line) in (('monitor_frame', mon[0]), ('monitor_stand', stand[0])):
        lo = three_to_ue([x - w / 2, y - h / 2, z - d / 2])
        hi = three_to_ue([x + w / 2, y + h / 2, z + d / 2])
        lo, hi = np.minimum(lo, hi), np.maximum(lo, hi)
        lo[2] += lift
        hi[2] += lift
        items[key] = {'min_cm': lo, 'max_cm': hi, 'on_slab': key == 'monitor_stand',
                      'provenance': f'{ref}:web/house/home.js line {line} box({w}, {h}, {d}, {x}, {y}, {z}, M.{mat}) '
                                    f'+ {lift:.4f} cm rigid lift ({MAIN_SOURCES["monitor_fix"]})'}
    stand_bottom = items['monitor_stand']['min_cm'][2]
    screen = np.asarray(fix['new_screen_expected_center_ue_cm'], float)
    items['monitor_stand']['support_check'] = {'stand_bottom_cm': r_(stand_bottom), 'desk_top_cm': r_(desk['top_cm']),
                                               'stand_on_top': bool(abs(stand_bottom - desk['top_cm']) < .01)}
    items['monitor_frame']['screen_centre_check'] = {
        'support_fix_expected_screen_centre_cm': screen.tolist(),
        'home_js_frame_centre_lifted_cm': [r_(v) for v in (items['monitor_frame']['min_cm'] + items['monitor_frame']['max_cm']) / 2],
        'z_matches': bool(abs((items['monitor_frame']['min_cm'][2] + items['monitor_frame']['max_cm'][2]) / 2 - screen[2]) < .01)}
    for name, b in desk['constants']['device_bounds_m'].items():
        if name in ('keyboard', 'mouse'):
            continue      # the devices under test are measured from their GLBs at the proposed transforms
        (x0, z0), (x1, z1) = b
        items[f'{name}_root_envelope'] = {'min_cm': np.array([x0 * 100, z0 * 100, desk['top_cm']]),
                                          'max_cm': np.array([x1 * 100, z1 * 100, desk['top_cm'] + (60. if name == 'monitor' else 2.)]),
                                          'on_slab': True,
                                          'provenance': f'{ref}:{MAIN_SOURCES["placement"]} device_bounds[{name!r}] (XY support envelope)'}
    lamp = json.loads(git_bytes(MAIN_SOURCES['lamp_mount'], ref))
    if 'lamp_world_aabb_m' in lamp:
        lo, hi = (np.asarray(v, float) * 100 for v in lamp['lamp_world_aabb_m'])
        items['clamp_lamp'] = {'min_cm': lo, 'max_cm': hi, 'on_slab': True,
                               'provenance': f'{ref}:{MAIN_SOURCES["lamp_mount"]} lamp_world_aabb_m (UE metres x, y, z)'}
    for p in desk['parts']:
        if p['kind'] == 'grommet' and p['max'][2] > desk['top_cm']:
            items[f'grommet_node{p["node"]}'] = {'min_cm': p['min'], 'max_cm': p['max'], 'on_slab': True,
                                                 'provenance': f'LINEA node {p["node"]} {p["name"]}'}
    return items, {'monitor_fix_sha256': sha256(fix_raw), 'lift_cm': lift, 'home_js_sha256': sha256(js.encode())}


# ---------------------------------------------------------------- devices (keyboard, mouse) at home.js placement + delta
HOME_DEVICES = {'keyboard': ('web/house/assets/keyboard/keyboard.glb', (2., .846, -2.94, .371)),
                'mouse': ('web/room/mouse.glb', (2.4, .846, -2.91, .22))}


def furnished_check(js, name, path, params):
    """The furnished() call in home.js must match the placement used here."""
    m = re.search(r'furnished\(\s*"' + name + r'"\s*,\s*([^)]*)\)', js)
    if not m:
        return False
    args = [a.strip() for a in m.group(1).split(',')]
    vals = [float(a) for a in args[:4]]
    return bool(np.allclose(vals, params) and path.split('/')[-1] in m.group(1))


def device_geometry(name, delta_cm=(0., 0., 0.), ref=MAIN_REF):
    """home.js loadFurnished(): uniform scale = width / scene-bounds x size, centred on (x, z), bottom at y; then the
    proposal's UE delta. Returns UE triangles per material and the lowest ('feet') points."""
    path, (x, y, z, width) = HOME_DEVICES[name]
    raw = pinned(path, ref)
    doc, binary = parse_glb(raw)
    rows = glb_triangles(doc, binary)
    allp = np.concatenate([t.reshape(-1, 3) for *_, t in rows])
    lo, hi = allp.min(0), allp.max(0)
    s = width / (hi[0] - lo[0])
    centre = (lo + hi) / 2 * s
    off = np.array([x - centre[0], y - lo[1] * s, z - centre[2]])
    d = np.asarray(delta_cm, float)
    out = []
    for ni, nname, mat, t in rows:
        out.append((nname, mat, three_to_ue(t * s + off) + d))
    V = np.concatenate([t.reshape(-1, 3) for *_, t in out])
    feet = V[V[:, 2] <= V[:, 2].min() + .15]
    return {'name': name, 'source': path, 'sha256': sha256(raw), 'scale': s, 'home_params': [x, y, z, width],
            'delta_cm': d.tolist(), 'parts': out, 'vertices': V, 'feet': feet,
            'footprint_cm': [V[:, :2].min(0), V[:, :2].max(0)], 'bottom_cm': float(V[:, 2].min()),
            'top_cm': float(V[:, 2].max())}


def device_support(dev, desk, items, other_devices=()):
    """Feet on the flat walnut top, footprint inside the slab with margin, clear of every other desk item."""
    th = TH
    gap = dev['bottom_cm'] - desk['top_cm']
    on_flat = point_in_triangles_2d(dev['feet'][:, :2], desk['flat_top_tris'])
    fp = np.asarray(dev['footprint_cm'])
    # footprint corners and a 1 cm grid over the footprint must be over the flat top, at least `margin` from its edge
    xs = np.arange(fp[0, 0], fp[1, 0] + 1e-9, 1.)
    ys = np.arange(fp[0, 1], fp[1, 1] + 1e-9, 1.)
    gx, gy = np.meshgrid(np.r_[xs, fp[1, 0]], np.r_[ys, fp[1, 1]])
    grid = np.stack([gx.ravel(), gy.ravel()], -1)
    grid_over = point_in_triangles_2d(grid, desk['flat_top_tris'])
    wt = desk['worktop']
    slab_margin = float(min(fp[0, 0] - wt['min'][0], fp[0, 1] - wt['min'][1], wt['max'][0] - fp[1, 0], wt['max'][1] - fp[1, 1]))
    # margin to the flat region's boundary: shrink test (the footprint grown by the margin must still be over flat top)
    m = th['device_slab_margin_cm']
    grown = np.concatenate([grid + [m, 0], grid - [m, 0], grid + [0, m], grid - [0, m]])
    grown_over = point_in_triangles_2d(grown, desk['flat_top_tris'])
    clear = {}
    for k, it in list(items.items()) + [(o['name'], {'min_cm': np.r_[o['footprint_cm'][0], o['bottom_cm']],
                                                      'max_cm': np.r_[o['footprint_cm'][1], o['top_cm']], 'on_slab': True,
                                                      'provenance': 'device GLB at its proposed transform'})
                                        for o in other_devices]:
        hgap = rect_gap(fp, [it['min_cm'][:2], it['max_cm'][:2]])
        zover = min(dev['top_cm'], it['max_cm'][2]) - max(dev['bottom_cm'], it['min_cm'][2])
        clear[k] = {'horizontal_gap_cm': r_(hgap), 'vertical_overlap_cm': r_(zover),
                    'collides': bool(hgap < th['device_item_margin_cm'] and (it.get('on_slab') or zover > 0)),
                    'provenance': it['provenance']}
    ok_gap = th['device_foot_gap_cm'][0] <= gap <= th['device_foot_gap_cm'][1]
    res = {'bottom_minus_top_cm': r_(gap), 'feet_points': int(len(dev['feet'])),
           'feet_over_flat_top': int(on_flat.sum()), 'all_feet_over_flat_top': bool(on_flat.all()),
           'footprint_cm': [[r_(v) for v in fp[0]], [r_(v) for v in fp[1]]],
           'footprint_grid_over_flat_top': bool(grid_over.all()),
           'footprint_margin_to_slab_aabb_cm': r_(slab_margin),
           'footprint_grown_by_margin_over_flat_top': bool(grown_over.all()),
           'items': clear}
    res['pass'] = bool(ok_gap and on_flat.all() and grid_over.all() and grown_over.all()
                       and not any(c['collides'] for c in clear.values()))
    res['rule'] = (f"lowest device point within {th['device_foot_gap_cm']} cm of the worktop top; every foot point and a "
                   f"1 cm footprint grid (also grown by {m} cm) over the worktop's flat top faces (eased edges and the "
                   f"grommet opening excluded); footprint >= {th['device_item_margin_cm']} cm from every other desk "
                   "item's footprint (items resting on the slab collide on footprint overlap; floating ones only with "
                   "vertical overlap)")
    return res


# ---------------------------------------------------------------- the COMPLETE chair
def chair_geometry(start_cm, ref=MAIN_REF, cache=None):
    import export_seat_fit_source as E
    raw = pinned('web/room/chair_owner.glb', ref)
    local = ROOT / 'web/room/chair_owner.glb'
    if sha256(local.read_bytes()) != sha256(raw):
        raise ValueError('local chair_owner.glb differs from origin/main')
    dec = E.decoded(local, Path(cache or ROOT / 'out/seat-fit-cache'))       # meshopt decode (cached), bytes as main
    doc, binary = parse_glb(dec.read_bytes())
    rep_raw = CHAIR_REPORT.read_bytes()
    rep = json.loads(rep_raw)['chair']
    tr = rep['transform']
    if tr['rotation_xyzw'] != [0.0, 0.0, 0.0, 1.0]:
        raise ValueError('chair rotation is not identity')
    sc = float(tr['scale'][0])
    mesh_nodes = [i for i, n in enumerate(doc['nodes']) if 'mesh' in n]
    if len(mesh_nodes) != 1:
        raise ValueError('chair: one mesh node expected')
    node = doc['nodes'][mesh_nodes[0]]
    nsc = np.asarray(node.get('scale', [1, 1, 1]), float)
    if not np.allclose(nsc, sc, atol=1e-6) or node.get('rotation') not in (None, [0, 0, 0, 1]):
        raise ValueError('chair node scale/rotation differs from the measured native transform')
    start = np.asarray(start_cm, float)
    measured = np.asarray(tr['translation_cm'], float)
    shell = np.concatenate([np.asarray(s['vertices_world_cm'], float) for s in rep['sections']]) + (start - measured)
    local, mats = [], []
    for prim in doc['meshes'][node['mesh']]['primitives']:
        P = accessor(doc, binary, prim['attributes']['POSITION'])
        idx = accessor(doc, binary, prim['indices']).astype(int).reshape(-1, 3)
        local.append(P[idx])
        mats += [doc['materials'][prim['material']].get('name', '')] * len(idx)
    local, mats = np.concatenate(local), np.array(mats)
    from scipy.spatial import cKDTree

    def shell_error(tris):
        fab = tris[mats == 'chair_fabric']
        _, ii = cKDTree(fab.mean(1)).query(shell, k=24)
        return np.min([closest_on_triangles(shell, *np.moveaxis(fab[ii[:, k]], 1, 0)) for k in range(24)], axis=0)
    # two placement hypotheses, decided by root's measured native shell: the native static mesh is the glTF mesh at
    # the actor (translation, scale) WITHOUT the glTF node translation, or WITH it
    hyp = {'actor_scale_without_node_translation': start + three_to_ue(local * sc),
           'actor_scale_with_node_translation': start + three_to_ue(local * sc + np.asarray(node.get('translation', [0, 0, 0]), float))}
    errs = {k: shell_error(v) for k, v in hyp.items()}
    pick = min(errs, key=lambda k: float(errs[k].max()))
    tris, err = hyp[pick], errs[pick]
    return {'source': 'web/room/chair_owner.glb', 'sha256': sha256(raw), 'report_sha256': sha256(rep_raw),
            'measured_translation_cm': measured.tolist(), 'start_cm': start.tolist(), 'scale': sc,
            'tris': tris, 'material': mats,
            'triangles_by_material': {m: int((mats == m).sum()) for m in np.unique(mats)},
            'native_shell_on_source_cm': {'median': r_(np.median(err)), 'max': r_(err.max()), 'tolerance': CHAIR_SHELL_TOL_CM,
                                          'pass': bool(err.max() <= CHAIR_SHELL_TOL_CM), 'placement': pick,
                                          'hypotheses_max_cm': {k: r_(v.max()) for k, v in errs.items()}},
            'lowest_cm': float(tris[..., 2].min()), 'bounds_cm': [tris.reshape(-1, 3).min(0).tolist(), tris.reshape(-1, 3).max(0).tolist()]}


def smootherstep(x):
    x = np.clip(np.asarray(x, float), 0., 1.)
    return x * x * x * (x * (6 * x - 15) + 10)


def chair_path_check(chair, desk, roll_xy, extra_offsets=(), samples=101, spacing=1.):
    """The complete chair along the roll path (s = 0..1 under the declared quintic and any per-frame offsets given)
    vs every desk part AABB and the floor."""
    pts, ids = sample_triangles(chair['tris'], spacing)
    mat = chair['material'][ids]
    boxes = np.array([[p['min'], p['max']] for p in desk['parts']])
    roll = np.array([roll_xy[0], roll_xy[1], 0.])
    offs = [roll * smootherstep(s) for s in np.linspace(0, 1, samples)] + [np.asarray(o, float) for o in extra_offsets]
    rows = []
    near_lo, near_hi = desk['bounds'][0] - 30, desk['bounds'][1] + 30
    for o in offs:
        p = pts + o
        sel = np.nonzero(np.all((p >= near_lo) & (p <= near_hi), axis=1))[0]
        if len(sel):
            d, w = min_box_sdf(p[sel], boxes, reach=20.)
            k = int(np.argmin(d))
            dm, part, cpart = float(d[k]), desk['parts'][w[k]] if w[k] >= 0 else None, str(mat[sel[k]])
        else:
            dm, part, cpart = 20., None, None
        rows.append({'offset_cm': [r_(v) for v in o], 'desk_min_cm': r_(min(dm, 20.)),
                     'nearest_desk_part': f"{part['node']} {part['name']}" if part else None, 'chair_part': cpart,
                     'floor_gap_cm': r_(float(p[:, 2].min()) - FLOOR_CM, 6)})
    w_ = min(rows, key=lambda r: r['desk_min_cm'])
    floor = [r['floor_gap_cm'] for r in rows]
    return {'positions_checked': len(rows), 'sample_spacing_cm': spacing, 'chair_points': int(len(pts)),
            'worst_desk': w_, 'desk_clear': bool(all(r['desk_min_cm'] > TH['chair_desk_clearance_cm'] for r in rows)),
            'floor_gap_cm': [min(floor), max(floor)],
            'floor_ok': bool(TH['chair_floor_gap_cm'][0] <= min(floor) and max(floor) <= TH['chair_floor_gap_cm'][1]),
            'pulled_in_end': rows[samples - 1],
            'rows_every_10th': rows[:samples:10]}


# ---------------------------------------------------------------- the body (owner skin via the fitter path)
class Body:
    def __init__(self, source_npz, stride=2, cache=None):
        import export_seat_fit_source as E
        import fit_seat_pelvis_pitch as P
        import fit_seat_pose_trial as T
        import life_gltf as G
        self.E, self.P, self.T, self.G = E, P, T, G
        self.base = E.Source.load(source_npz)
        self.names = self.base.names
        self.j = {n: k for k, n in enumerate(self.names)}
        pos, jts, wts = P.owner_skin(stride=stride, cache=cache)
        self.stride = stride
        dom = jts[np.arange(len(jts)), wts.argmax(1)]
        self.segment = np.array([self.seg_of(self.names[int(k)]) for k in dom])
        from scipy import sparse
        J, V = len(self.names), len(pos)
        hom = np.hstack([pos, np.ones((V, 1))])
        rows, cols, vals = [], [], []
        for k in range(jts.shape[1]):
            for c in range(4):
                rows.append(jts[:, k] * 4 + c)
                cols.append(np.arange(V))
                vals.append(wts[:, k] * hom[:, c])
        self.S = sparse.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(J * 4, V))
        self.ibm = self.base.ibm

    @staticmethod
    def seg_of(n):
        if any(f in n for f in ('Thumb', 'Index', 'Middle', 'Ring', 'Pinky')):
            return 'fingers'
        if n.endswith('ForeArm'):
            return 'forearm'
        if n.endswith('Hand'):
            return 'hand'
        if n.endswith('Arm'):
            return 'upper_arm'
        if n.endswith('Shoulder'):
            return 'shoulder'
        if n.endswith('UpLeg'):
            return 'thigh'
        if n.endswith('Leg'):
            return 'knee_shin'
        if 'Foot' in n or 'Toe' in n:
            return 'foot'
        return 'torso_head'

    def skin_ue(self, W, shift):
        """(F, V, 3) UE cm skin at the body placement: to_ue(LBS(W)) + shift."""
        M = (np.asarray(W) @ self.ibm[None])[..., :3, :]
        lin = M.transpose(0, 2, 1, 3).reshape(len(W), 3, -1)
        pos = np.stack([(self.S.T @ lin[f].T) for f in range(len(W))])        # (F, V, 3) glTF metres
        return self.E.to_ue(pos) + np.asarray(shift, float)[:, None, :]

    def joints_ue(self, W, shift):
        return self.E.to_ue(np.asarray(W)[..., :3, 3]) + np.asarray(shift, float)[:, None, :]

    def clip(self, path, times=None):
        g = self.G.Gltf(Path(path))
        if times is None:
            times = [float(t) for t in g.animation().key_times()]
        W, parents = self.E.joint_worlds(g, self.names, times)
        if not np.array_equal(parents, self.base.parents):
            raise ValueError(f'{path}: skeleton differs from the owner')
        return W, np.asarray(times, float)


# ---------------------------------------------------------------- seat rule: origin/main validate() bytes
def main_validator(ref=MAIN_REF):
    import importlib.util
    import tempfile
    data = git_bytes('tools/validate_unreal_seat_contact.py', ref)
    if sha256(data) != PINS['tools/validate_unreal_seat_contact.py']:
        raise ValueError('main validator sha256 differs from the pin')
    tmp = Path(tempfile.mkdtemp(prefix='verify-main-seat-')) / 'main_validate_unreal_seat_contact.py'
    tmp.write_bytes(data)
    spec = importlib.util.spec_from_file_location('verify_main_validate_unreal_seat_contact', tmp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.SOURCE_SHA256 = sha256(data)
    return mod


def main_rule_frames(V, metrics, frames):
    """main's validate() on each given frame (as a 301-sample constant block, the shape main requires)."""
    fails = {}
    for f in frames:
        regions = []
        for name, m in metrics.items():
            low, med = m['lowest'][f], m['median'][f]
            low = float(low) if np.isfinite(low) else 1e9
            med = float(med) if np.isfinite(med) else 1e9
            regions.append({'region': name, 'selectedVertices': int(m['facing'][f]), 'facingVertices': int(m['facing'][f]),
                            'overSurfaceVertices': int(m['over'][f]), 'bandVertices': int(m['band'][f]),
                            'minGapCm': low, 'p10GapCm': med, 'p50GapCm': med, 'p90GapCm': med, 'maxGapCm': med})
        data = {'samples': [{'time': 3 + i / 60, 'invalidInfluences': 0, 'regions': regions} for i in range(301)]}
        try:
            V.validate(data)
        except ValueError as e:
            fails[int(f)] = str(e).rsplit(' at ', 1)[0]
    return fails


# ---------------------------------------------------------------- ergonomic angles (independent)
def unit_rot(M):
    u, _, vt = np.linalg.svd(M)
    return u @ vt


def wrist_angles(Wue_rot_f, Wue_rot_h, bind_f, bind_h, a_long, a_palm, a_radial):
    """Wrist flexion (+ toward the palm) and deviation (+ radial), degrees, relative to the straight bind hand: the hand's
    long axis carried into the forearm's bind frame and decomposed on the bind palm-normal and radial axes."""
    M = bind_f @ np.swapaxes(Wue_rot_f, -1, -2) @ Wue_rot_h @ bind_h.T       # current hand in the forearm's bind frame
    l = M @ a_long
    flex = np.degrees(np.arctan2(l @ a_palm, l @ a_long))
    dev = np.degrees(np.arctan2(l @ a_radial, l @ a_long))
    return flex, dev


def wrist_angles_anatomical(elbow, wrist, middle1, palm, radial):
    """Absolute wrist flexion (+ toward the palm) / deviation (+ radial), degrees: the forearm axis (elbow -> wrist
    joint) expressed in the hand frame (long = wrist -> middle knuckle, palm normal, radial, each orthonormalised)."""
    f = wrist - elbow
    f = f / np.linalg.norm(f, axis=-1, keepdims=True)
    l = middle1 - wrist
    l = l / np.linalg.norm(l, axis=-1, keepdims=True)
    n = palm - (palm * l).sum(-1, keepdims=True) * l
    n = n / np.linalg.norm(n, axis=-1, keepdims=True)
    r = radial - (radial * l).sum(-1, keepdims=True) * l - (radial * n).sum(-1, keepdims=True) * n
    r = r / np.linalg.norm(r, axis=-1, keepdims=True)
    fl = (f * l).sum(-1)
    return np.degrees(np.arctan2(-(f * n).sum(-1), fl)), np.degrees(np.arctan2(-(f * r).sum(-1), fl))


def arm_frames(body, W):
    """Per joint world rotations in UE axes (unit), (F, J, 3, 3)."""
    R = np.asarray(W)[..., :3, :3]
    U = np.linalg.svd(R)
    rot = U[0] @ U[2]
    # glTF -> UE: x, z, y swap then yaw 180 about Z
    C = np.array([[1, 0, 0], [0, 0, 1], [0, 1, 0]], float)
    Y = np.diag([-1., -1., 1.])
    A = Y @ C
    return A @ rot @ A.T


def ergonomics(body, W, shift, top_cm, idle_clavicle=None):
    """Per side and frame: elbow height over the worktop, upper arm from vertical, clavicle elevation, wrist angles."""
    J = body.joints_ue(W, shift)
    bindW = np.linalg.inv(body.ibm)                                        # bind joint worlds (glTF)
    Rb = arm_frames(body, bindW[None])[0]
    Jb = body.E.to_ue(bindW[:, :3, 3])
    Rf = arm_frames(body, W)
    out = {}
    for side, P_ in (('left', 'Left'), ('right', 'Right')):
        sh, el, wr = (J[:, body.j[f'{P_}{n}']] for n in ('Arm', 'ForeArm', 'Hand'))
        cl = J[:, body.j[f'{P_}Shoulder']]
        ua = el - sh
        upper = np.degrees(np.arccos(np.clip(-ua[:, 2] / np.linalg.norm(ua, axis=1), -1, 1)))
        cv = sh - cl
        clav = np.degrees(np.arcsin(np.clip(cv[:, 2] / np.linalg.norm(cv, axis=1), -1, 1)))
        # bind axes of the hand (UE): long = middle knuckle - wrist, radial = index knuckle - pinky knuckle, palm normal
        hb, mb, ib, pb = (Jb[body.j[f'{P_}{n}']] for n in ('Hand', 'HandMiddle1', 'HandIndex1', 'HandPinky1'))
        a_long = (mb - hb) / np.linalg.norm(mb - hb)
        rad = ib - pb
        a_rad = rad - (rad @ a_long) * a_long
        a_rad /= np.linalg.norm(a_rad)
        a_palm = np.cross(a_long, a_rad) if side == 'right' else np.cross(a_rad, a_long)
        # orient the palm normal toward the finger curl: the bind middle-finger chain bends that way in the capture's
        # flexed fingers; fall back to the side convention when the bind pose is straight (checked in the tests)
        fb, db = wrist_angles(Rf[:, body.j[f'{P_}ForeArm']], Rf[:, body.j[f'{P_}Hand']],
                              Rb[body.j[f'{P_}ForeArm']], Rb[body.j[f'{P_}Hand']], a_long, a_palm, a_rad)
        Rh = Rf[:, body.j[f'{P_}Hand']] @ Rb[body.j[f'{P_}Hand']].T          # bind -> current, world
        mid = J[:, body.j[f'{P_}HandMiddle1']]
        f_, d_ = wrist_angles_anatomical(el, wr, mid, Rh @ a_palm, Rh @ a_rad)
        fa0, da0 = wrist_angles_anatomical(Jb[body.j[f'{P_}ForeArm']], hb, mb, a_palm, a_rad)
        out[side] = {'elbow_above_top_cm': el[:, 2] - top_cm, 'elbow_z_cm': el[:, 2], 'upper_arm_from_vertical_deg': upper,
                     'clavicle_elevation_deg': clav, 'wrist_flexion_deg': fb, 'wrist_deviation_deg': db,
                     'wrist_flexion_joint_line_deg': f_, 'wrist_deviation_joint_line_deg': d_,
                     'bind_wrist_anatomical_deg': [float(fa0), float(da0)],
                     'palm_down_share': float(np.mean((Rh @ a_palm)[:, 2] < 0))}
    return out


# ---------------------------------------------------------------- the layout under test
R0_DEFAULT = (3.875, -32.5)      # the seated base's solver-frame chair offset (body offset (-3.875, +32.5))
BASELINE_CLIPS = {
    'SeatedIdle': 'docs/proposed/seat-pose-anatomical/chair-lift-proposal/SUB01_SeatedIdle.glb',
    'SitDown_seated': 'docs/proposed/seated-arms-on-anatomical/SUB01_SitDown_seated.glb',
    'GetUp_seated': 'docs/proposed/seated-arms-on-anatomical/SUB01_GetUp_seated.glb',
    'DeskTyping_seated': 'docs/proposed/seated-arms-on-anatomical/SUB01_DeskTyping_seated.glb',
    'SitToType_seated': 'docs/proposed/seated-arms-on-anatomical/SUB01_SitToType_seated.glb',
    'TypeToSit_seated': 'docs/proposed/seated-arms-on-anatomical/SUB01_TypeToSit_seated.glb'}
CHAIR_S_RULE = {'SitDown_seated': 0., 'SeatedIdle': 0., 'GetUp_seated': 0., 'DeskTyping_seated': 1.,
                'SitToType_seated': 'pull_in', 'TypeToSit_seated': 'push_back'}


def _first(d, *keys):
    for k in keys:
        if isinstance(d, dict) and d.get(k) is not None:
            return d[k]
    return None


def device_delta(orig, prop, name):
    """UE delta (cm) of a device from the proposal entry (three_m, or an explicit UE delta/translation)."""
    if prop is None:
        return np.zeros(3), 'unchanged (no proposed entry)'
    d = _first(prop, 'delta_ue_cm', 'delta_cm', 'offset_ue_cm', 'offset_cm', 'translation_delta_ue_cm')
    t = _first(prop, 'proposed_three_m', 'three_m')
    if d is not None:
        d = np.asarray(d, float)
        if t is not None and not np.allclose(three_to_ue(t) - three_to_ue(orig['three_m']), d, atol=1e-3):
            raise ValueError(f'{name}: delta_ue_cm {d.tolist()} disagrees with proposed_three_m {t}')
        return d, 'explicit UE delta' + (' (= proposed_three_m difference)' if t is not None else '')
    if t is not None:
        w0, w1 = orig.get('width_m'), prop.get('width_m', orig.get('width_m'))
        if w0 is not None and abs(float(w0) - float(w1)) > 1e-12:
            raise ValueError(f'{name}: proposed width differs from the original; the verifier needs a rigid move')
        rot = prop.get('rotation', prop.get('yaw', 0))
        if rot:
            raise ValueError(f'{name}: rotation not supported by the verifier (rigid translation only)')
        return three_to_ue(t) - three_to_ue(orig['three_m']), 'home.js three_m (x, y, z) difference'
    raise ValueError(f'{name}: no recognisable proposed transform in {sorted(prop)}')


def layout_from_proposal(path):
    path = Path(path)
    raw = path.read_bytes()
    doc = json.loads(raw)
    orig = doc['original']
    prop = _first(doc, 'proposed', 'proposal', 'layout') or {}
    kd, kdr = device_delta(orig['keyboard'], _first(prop, 'keyboard'), 'keyboard')
    md, mdr = device_delta(orig['mouse'], _first(prop, 'mouse'), 'mouse')
    pc = _first(prop, 'chair') or {}
    chair_start = np.asarray(_first(prop, 'chair_initial_translation_cm') or _first(pc, 'initial_translation_cm')
                             or orig['chair_initial_translation_cm'], float)
    roll = _first(prop, 'chair_roll_cm', 'chair_roll_ue_cm') or _first(pc, 'proposed_typing_roll_cm', 'roll_cm')
    if roll is None and _first(pc, 'proposed_typing_translation_cm') is not None:
        roll = np.asarray(pc['proposed_typing_translation_cm'], float) - chair_start
    if roll is None and _first(prop, 'chair_rolled_translation_cm') is not None:
        roll = np.asarray(prop['chair_rolled_translation_cm'], float) - chair_start
    if roll is None:
        roll = orig['chair_roll_cm']
    roll = np.asarray(roll, float)[:3] if len(roll) >= 3 else np.r_[np.asarray(roll, float), 0.]
    r0 = np.asarray(_first(prop, 'solver_frame_chair_offset_cm') or _first(doc, 'solver_frame_chair_offset_cm') or R0_DEFAULT, float)
    declared_shift = _first(_first(prop, 'body') or {}, 'solver_to_world_shift_cm')
    if declared_shift is not None:     # cross-check: the declared body shift must equal roll - r0 (rigid roll)
        want = np.r_[roll[:2] - r0, 0.]
        if not np.allclose(np.asarray(declared_shift, float)[:2], want[:2], atol=1e-3):
            raise ValueError(f'declared body shift {declared_shift} != roll - r0 {want.tolist()}')
    clips_in = _first(prop, 'clips') or _first(doc, 'clips') or {}
    clips = {}
    for role in ROLES:
        c = clips_in.get(role) if isinstance(clips_in, dict) else None
        if c is None:
            clips[role] = {'glb': BASELINE_CLIPS[role], 'sha256': None, 'source': 'BASELINE (not in the proposal)'}
        else:
            c = {'glb': c} if isinstance(c, str) else dict(c)
            clips[role] = {'glb': c.get('glb') or c.get('path'), 'sha256': c.get('sha256'), 'source': 'proposal',
                           'chair_translation_per_frame_cm': c.get('chair_translation_per_frame_cm'),
                           'report': c.get('report')}
    return {'proposal_file': str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
            'proposal_sha256': sha256(raw), 'status': doc.get('status'),
            'keyboard_delta_cm': kd, 'keyboard_delta_from': kdr, 'mouse_delta_cm': md, 'mouse_delta_from': mdr,
            'chair_start_cm': chair_start, 'chair_roll_cm': roll, 'r0': r0, 'clips': clips,
            'original_chair_start_cm': np.asarray(orig['chair_initial_translation_cm'], float)}


def baseline_layout():
    """The current committed layout (seated-arms-on-anatomical: keyboard/mouse at home.js, roll (3.875, -21.279))."""
    return {'proposal_file': None, 'proposal_sha256': None, 'status': 'baseline',
            'keyboard_delta_cm': np.zeros(3), 'keyboard_delta_from': 'home.js', 'mouse_delta_cm': np.zeros(3),
            'mouse_delta_from': 'home.js', 'chair_start_cm': np.array([200.0199556350708, -186.69002056121826, 63.1876777245]),
            'chair_roll_cm': np.array([3.875, -21.279, 0.]), 'r0': np.asarray(R0_DEFAULT, float),
            'clips': {r: {'glb': p, 'sha256': None, 'source': 'baseline'} for r, p in BASELINE_CLIPS.items()},
            'original_chair_start_cm': np.array([200.0199556350708, -186.69002056121826, 63.1876777245])}


def chair_path_for_clip(role, F, roll, explicit=None):
    """Per-frame chair offset (UE cm) from the chair start: explicit per-frame translations, else the declared rule."""
    if explicit is not None:
        return np.asarray(explicit, float), 'explicit per-frame translations (proposal)'
    rule = CHAIR_S_RULE[role]
    if rule == 'pull_in':
        s = np.linspace(0., 1., F)
    elif rule == 'push_back':
        s = 1. - np.linspace(0., 1., F)
    else:
        s = np.full(F, float(rule))
    return smootherstep(s)[:, None] * roll[None], f'roll * smootherstep(s), s {rule}'


# ---------------------------------------------------------------- per clip
DESK_GROUPS = ('worktop', 'apron', 'leg', 'drawer_carcass', 'grommet', 'cable_trough', 'fixing')
LEG_SEGS = ('thigh', 'knee_shin', 'foot')
ARM_SEGS = ('shoulder', 'upper_arm', 'forearm', 'hand', 'fingers')


def body_desk_clearance(body, W, shift, desk, chunk=20, reach=15.):
    """Per frame, per body segment and desk part group: the smallest signed distance (cm) of any skin vertex to the
    part AABBs (capped at `reach`), and the worst part node."""
    F = len(W)
    segs = np.unique(body.segment)
    out = {s: {g: np.full(F, reach) for g in DESK_GROUPS} for s in segs}
    node_at = {s: {g: np.full(F, -1) for g in DESK_GROUPS} for s in segs}
    groups = {g: [p for p in desk['parts'] if p['kind'] == g] for g in DESK_GROUPS}
    seg_idx = {s: np.nonzero(body.segment == s)[0] for s in segs}
    lo_all, hi_all = desk['bounds'][0] - reach, desk['bounds'][1] + reach
    for a in range(0, F, chunk):
        sl = slice(a, min(F, a + chunk))
        pts = body.skin_ue(W[sl], shift[sl])                    # (f, V, 3)
        for s in segs:
            P = pts[:, seg_idx[s]]
            near = np.all((P >= lo_all) & (P <= hi_all), axis=-1)
            if not near.any():
                continue
            fi, vi = np.nonzero(near)
            Q = P[fi, vi]
            for g, parts in groups.items():
                for p in parts:
                    m = np.all((Q >= p['min'] - reach) & (Q <= p['max'] + reach), axis=1)
                    if not m.any():
                        continue
                    d = box_sdf(Q[m], p['min'], p['max'])
                    fr = fi[m] + a
                    cur = out[s][g]
                    mins = np.full(F, np.inf)
                    np.minimum.at(mins, fr, d)
                    better = mins < cur
                    cur[better] = mins[better]
                    node_at[s][g][better] = p['node']
    return out, node_at


def declared_gate(glb, F):
    """The support-gated frames declared by the seated base report for this clip (main_rule.gated_frame_indices), found
    next to the GLB or in the anatomical base dir; None if absent."""
    p = ROOT / glb
    for cand in (p.with_suffix('.report.json'), ROOT / 'docs/proposed/seat-pose-anatomical/chair-lift-proposal' / (p.stem + '.report.json')):
        if cand.exists():
            gi = json.loads(cand.read_text()).get('main_rule', {}).get('gated_frame_indices')
            if gi is not None and max(gi) < F:
                return np.asarray(gi, int), f'declared support mask ({cand.relative_to(ROOT)} main_rule.gated_frame_indices)'
    return None


def accel(x, dt):
    return np.linalg.norm(np.diff(x, 2, axis=0), axis=-1) / dt ** 2


def run_verification(layout, source_npz, ref=MAIN_REF, stride=2, cache=None, frames_limit=None, log=print):
    t0 = time.time()
    res = {'schema': SCHEMA, 'label': 'independent verification', 'source_only': True, 'ready': False,
           'native_verified': False, 'never_a_receipt': True, 'thresholds': {k: list(v) if isinstance(v, tuple) else v for k, v in TH.items()}}
    desk = desk_geometry(ref)
    items, item_meta = desk_items(desk, ref)
    js = git_bytes(MAIN_SOURCES['home_js'], ref).decode()
    # ---- geometry provenance
    res['geometry'] = {
        'ref': ref, 'ref_commit': subprocess.run(['git', 'rev-parse', '--short', ref], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
        'linea140': {'path': 'web/house/assets/real-linea140/originalsource.glb', 'sha256': desk['source_sha256'],
                     'placement_source': MAIN_SOURCES['placement'], 'placement_source_sha256': desk['placement_source_sha256'],
                     'placement_source_commit': git_last_commit(MAIN_SOURCES['placement'], ref),
                     'scale': desk['constants']['scale'], 'translation_m': desk['constants']['translation_m'],
                     'mapping': 'UE cm = 100 * (tx + S x, DESK_Y + S z, ty + S y)',
                     'top_cm': r_(desk['top_cm']), 'floor_cm': r_(desk['floor_cm']),
                     'worktop_aabb_cm': [[r_(v) for v in desk['worktop']['min']], [r_(v) for v in desk['worktop']['max']]],
                     'flat_top_triangles': int(len(desk['flat_top_tris'])),
                     'parts_by_kind': {k: [p['node'] for p in desk['parts'] if p['kind'] == k] for k in sorted({p['kind'] for p in desk['parts']})},
                     'record_centre_note': 'root record docs/proposed/real-linea140-guarded-placement-20261014.json says centre '
                                           'Y -310; place_bytes (used here) gives Y -302 (known pending root confirmation)'},
        'desk_items': {k: {'min_cm': [r_(v) for v in it['min_cm']], 'max_cm': [r_(v) for v in it['max_cm']],
                           'provenance': it['provenance'], **{x: it[x] for x in ('support_check', 'screen_centre_check') if x in it}}
                       for k, it in items.items()},
        'monitor_provenance': {'home_js': f"{MAIN_SOURCES['home_js']} @ {git_last_commit(MAIN_SOURCES['home_js'], ref)} (sha256 {item_meta['home_js_sha256']})",
                               'lift': f"{MAIN_SOURCES['monitor_fix']} @ {git_last_commit(MAIN_SOURCES['monitor_fix'], ref)} (sha256 {item_meta['monitor_fix_sha256']}): "
                                       f"+{item_meta['lift_cm']:.4f} cm (stand bottom 82 -> top 84.5), screen centre z 118.5"},
        'main_sources': {k: {'path': p, 'sha256': sha256(git_bytes(p, ref)), 'commit': git_last_commit(p, ref)} for k, p in MAIN_SOURCES.items()},
        'pins': PINS}
    # ---- 1. devices
    kb = device_geometry('keyboard', layout['keyboard_delta_cm'], ref)
    ms = device_geometry('mouse', layout['mouse_delta_cm'], ref)
    kb0 = device_geometry('keyboard', np.zeros(3), ref)
    res['devices'] = {}
    for dev, other, d0 in ((kb, ms, kb0), (ms, kb, None)):
        name = dev['name']
        sup = device_support(dev, desk, items, other_devices=(other,))
        orig_dev = device_geometry(name, np.zeros(3), ref)
        sup['original_transform_bottom_minus_top_cm'] = r_(orig_dev['bottom_cm'] - desk['top_cm'])
        sup.update({'source': dev['source'], 'sha256': dev['sha256'], 'home_js_params': dev['home_params'],
                    'home_js_call_matches': furnished_check(js, name, dev['source'], dev['home_params']),
                    'delta_cm': [r_(v) for v in dev['delta_cm']],
                    'delta_from': layout[f'{name}_delta_from']})
        res['devices'][name] = sup
    kd = layout['keyboard_delta_cm']
    res['devices']['keyboard']['moved_toward_body_cm'] = r_(kd[1])
    log(f'devices done {time.time() - t0:.0f}s')
    # ---- 2. chair
    chair = chair_geometry(layout['chair_start_cm'], ref, cache)
    roll = layout['chair_roll_cm']
    body = Body(source_npz, stride=stride, cache=cache)
    clips = {}
    for role in ROLES:
        c = layout['clips'][role]
        p = ROOT / c['glb']
        sha = sha256(p.read_bytes())
        if c.get('sha256') and c['sha256'] != sha:
            raise ValueError(f'{role}: GLB sha256 differs from the proposal')
        W, times = body.clip(p)
        if frames_limit:
            W, times = W[:frames_limit], times[:frames_limit]
        off, rule = chair_path_for_clip(role, len(times), roll, c.get('chair_translation_per_frame_cm'))
        if c.get('chair_translation_per_frame_cm') is not None:
            off = off - layout['chair_start_cm']
        shift = off - np.r_[layout['r0'], 0.][None]
        shift[:, 2] = 0.
        clips[role] = {'W': W, 'times': times, 'chair_off': off, 'shift': shift, 'glb': c['glb'], 'sha256': sha,
                       'clip_source': c['source'], 'chair_rule': rule}
    extra = [o for c in clips.values() for o in np.unique(np.round(c['chair_off'], 6), axis=0)]
    path = chair_path_check(chair, desk, roll[:2], extra_offsets=extra)
    start_exact = {r: bool(np.array_equal(clips[r]['chair_off'][0], np.zeros(3))) for r in ('SitToType_seated',)}
    rev = {'sit_to_type_first_at_start': bool(np.allclose(clips['SitToType_seated']['chair_off'][0], 0, atol=1e-9)),
           'sit_to_type_last_at_pulled_in': bool(np.allclose(clips['SitToType_seated']['chair_off'][-1], roll, atol=1e-6)),
           'desk_typing_all_at_pulled_in': bool(np.allclose(clips['DeskTyping_seated']['chair_off'], roll[None], atol=1e-6)),
           'type_to_sit_first_at_pulled_in': bool(np.allclose(clips['TypeToSit_seated']['chair_off'][0], roll, atol=1e-6)),
           'type_to_sit_last_exactly_start': bool(np.array_equal(clips['TypeToSit_seated']['chair_off'][-1], np.zeros(3))),
           'seated_clips_at_start': bool(all(np.array_equal(clips[r]['chair_off'], np.zeros_like(clips[r]['chair_off']))
                                             for r in ('SitDown_seated', 'SeatedIdle', 'GetUp_seated')))}
    a_, b_ = clips['SitToType_seated']['chair_off'], clips['TypeToSit_seated']['chair_off']
    rev['push_back_retraces_pull_in_cm'] = r_(np.abs(a_ - b_[::-1]).max(), 6) if len(a_) == len(b_) else None
    rev['chair_start_equals_original'] = bool(np.allclose(layout['chair_start_cm'], layout['original_chair_start_cm'], atol=1e-9))
    rev['pass'] = bool(all(v for k, v in rev.items() if isinstance(v, bool)) and _start_exact_ok(start_exact))
    res['chair'] = {'source': chair['source'], 'sha256': chair['sha256'], 'report': str(CHAIR_REPORT.relative_to(ROOT)),
                    'report_sha256': chair['report_sha256'], 'start_cm': [r_(v) for v in chair['start_cm']],
                    'measured_translation_cm': chair['measured_translation_cm'], 'scale': chair['scale'],
                    'roll_cm': [r_(v) for v in roll], 'pulled_in_translation_cm': [r_(v) for v in chair['start_cm'] + roll],
                    'triangles_by_material': chair['triangles_by_material'],
                    'native_shell_on_source': chair['native_shell_on_source_cm'],
                    'lowest_cm_at_start': r_(chair['lowest_cm']), 'path': path, 'reversibility': rev,
                    'per_clip_rule': {r: c['chair_rule'] for r, c in clips.items()}}
    res['chair']['pass'] = bool(path['desk_clear'] and path['floor_ok'] and rev['pass'] and chair['native_shell_on_source_cm']['pass'])
    log(f'chair done {time.time() - t0:.0f}s')
    # ---- 3. body per clip
    V = main_validator(ref)
    import fit_seat_pelvis_pitch as P
    tri, _ = P.load_cushion()
    tri = tri + (layout['chair_start_cm'] - np.asarray(json.loads(CHAIR_REPORT.read_text())['chair']['transform']['translation_cm']))
    keys = body.T.keycaps_from_glb()
    keys_new = dict(keys, triangles=keys['triangles'] + kd, key_min=keys['key_min'] + kd, key_max=keys['key_max'] + kd,
                    top_cm=keys['top_cm'] + kd[2])
    U = np.stack([P.ue_delta_to_gltf(e) for e in np.eye(3)])
    idle_hips = None
    body_out, erg_all, joints_world = {}, {}, {}
    for role in ('SeatedIdle',) + tuple(r for r in ROLES if r != 'SeatedIdle'):
        c = clips[role]
        W, times, shift = c['W'], c['times'], c['shift']
        F = len(times)
        d = dict(body.base.d)
        d['joint_world'], d['times'] = W, times
        fit = P.SeatFit(body.E.Source(d), tri, keys_new, tuple(layout['r0']))
        seat, soles = fit.trial.seat(W), fit.trial.soles(W)
        metrics = {**{n: seat[n] for n in seat}, **{n: soles[n] for n in soles}}
        hips_z = body.joints_ue(W, shift)[:, body.j['Hips'], 2]
        if role == 'SeatedIdle':
            idle_hips = (float(hips_z.min()), float(hips_z.max()))
        if role in ('SitDown_seated', 'GetUp_seated'):
            gated = np.nonzero((hips_z >= idle_hips[0] - .5) & (hips_z <= idle_hips[1] + .5))[0]
            gate_rule = 'settled: Hips height within the SeatedIdle range +- 0.5 cm'
        else:
            gated = np.arange(F)
            gate_rule = 'every frame (seated clip)'
        declared = declared_gate(c['glb'], F) if role in ('SitDown_seated', 'GetUp_seated') else None
        settled_fails = None
        if declared is not None:
            settled_fails = main_rule_frames(V, metrics, gated)
            settled = {'gate_rule': gate_rule, 'gated_frames': int(len(gated)), 'failing_frames': sorted(settled_fails),
                       'messages': {str(k): v for k, v in sorted(settled_fails.items())},
                       'extra_frames_vs_declared': sorted(set(gated.tolist()) - set(declared[0].tolist()))}
            gated, gate_rule = declared
        fails = main_rule_frames(V, metrics, gated)
        seat_res = {'gated_frames': int(len(gated)), 'gate_rule': gate_rule, 'pass_main_rule': not fails,
                    'failing_frames': sorted(fails)[:50], 'failing_frame_count': len(fails),
                    'first_failure_message': fails[min(fails)] if fails else None,
                    'worst': {n: {'min_gap_cm': worst(m['lowest'][gated], times[gated]),
                                  'max_median_gap_cm': worst(m['median'][gated], times[gated], lowest=False),
                                  'min_coverage': worst(np.where(m['over'][gated] > 0, m['band'][gated] / np.maximum(m['over'][gated], 1), 0.), times[gated])}
                              for n, m in metrics.items()}}
        if settled_fails is not None:
            seat_res['independent_settled_gate_crosscheck'] = settled
        for n in seat_res['worst']:     # map back to clip frame indices
            for k, w in seat_res['worst'][n].items():
                if w:
                    w['frame'] = int(gated[w['frame']])
        sole_low = np.minimum(soles['left_sole']['lowest_any_z'], soles['right_sole']['lowest_any_z']) - FLOOR_CM
        soles_res = {'lowest_sole_minus_floor_cm': worst(sole_low, times),
                     'pass_no_penetration_all_frames': bool(np.nanmin(sole_low) >= TH['sole_floor_penetration_cm']),
                     'on_floor_gated_frames_by_main_rule': not any('sole' in m for m in fails.values())}
        clr, nodes = body_desk_clearance(body, W, shift, desk)
        legs = {s: {g: worst(clr[s][g], times) for g in ('apron', 'drawer_carcass', 'leg', 'worktop')} for s in LEG_SEGS if s in clr}
        arms = {s: {g: worst(clr[s][g], times) for g in DESK_GROUPS} for s in ARM_SEGS if s in clr}
        for grp in (legs, arms):
            for s in grp:
                for g, w in grp[s].items():
                    if w:
                        w['node'] = int(nodes[s][g][w['frame']])
        leg_min = min((w['value'] for s in legs.values() for w in s.values() if w), default=15.)
        arm_min = min((w['value'] for s, gs in arms.items() if s != 'fingers' for w in gs.values() if w), default=15.)
        fing_min = min((w['value'] for w in arms.get('fingers', {}).values() if w), default=15.)
        torso = {g: worst(clr['torso_head'][g], times) for g in DESK_GROUPS} if 'torso_head' in clr else {}
        tor_min = min((w['value'] for w in torso.values() if w), default=15.)
        # fingertip contact: DIAGNOSTIC ONLY (old finger rests; new hands pending)
        Ws = np.array(W, copy=True)
        Ws[..., :3, 3] += (shift @ U)[:, None, :]
        tr = body.T.Trial(body.E.Source(dict(d, joint_world=Ws)), tri, keys_new, (0., 0.))
        ka = tr.key_audit(Ws)
        diag = {}
        for s in ('left', 'right'):
            over = ka[s]['over'] > 0
            gap = np.where(over, ka[s]['over_min'] - keys_new['top_cm'], np.nan)
            diag[s] = {'frames_over_keys': int(over.sum()), 'gap_cm_range': [r_(np.nanmin(gap)), r_(np.nanmax(gap))] if over.any() else None,
                       'worst_penetration': worst(gap, times), 'worst_gap': worst(gap, times, lowest=False)}
        erg = ergonomics(body, W, shift, desk['top_cm'])
        erg_all[role] = erg
        joints_world[role] = body.joints_ue(W, shift)
        joints_world[role + '#chair'] = body.joints_ue(W, np.zeros_like(shift))
        body_out[role] = {
            'glb': c['glb'], 'sha256': c['sha256'], 'clip_source': c['clip_source'], 'frames': F,
            'chair_rule': c['chair_rule'],
            'seat_main_rule': seat_res, 'soles': soles_res,
            'legs_vs_desk': {'by_segment': legs, 'min_cm': r_(leg_min), 'pass': bool(leg_min > TH['body_desk_clearance_cm'])},
            'arms_vs_desk': {'by_segment': arms, 'min_cm_excluding_fingers': r_(arm_min),
                             'fingers_min_cm_diagnostic': r_(fing_min), 'pass': bool(arm_min > TH['body_desk_clearance_cm'])},
            'torso_head_vs_desk': {'by_group': torso, 'min_cm': r_(tor_min), 'pass': bool(tor_min > TH['body_desk_clearance_cm'])},
            'fingertip_key_contact_DIAGNOSTIC_ONLY': diag}
        body_out[role]['pass'] = bool(seat_res['pass_main_rule'] and soles_res['pass_no_penetration_all_frames']
                                      and body_out[role]['legs_vs_desk']['pass'] and body_out[role]['arms_vs_desk']['pass']
                                      and body_out[role]['torso_head_vs_desk']['pass'])
        log(f'{role} done {time.time() - t0:.0f}s')
    res['body'] = {'skin': f'owner skin (fit_seat_pelvis_pitch.owner_skin, every {stride}th vertex: {len(body.segment)} vertices), '
                           'segments by dominant joint; desk parts as conservative node AABBs',
                   'source_npz_sha256': sha256(Path(source_npz).read_bytes()),
                   'main_validator': {'path': 'tools/validate_unreal_seat_contact.py', 'ref': ref, 'sha256': V.SOURCE_SHA256},
                   'clips': {r: body_out[r] for r in ROLES}}
    # ---- 4. continuity
    res['continuity'] = continuity(body, clips, joints_world, log)
    # ---- 5. ergonomics
    res['ergonomics'] = ergonomic_report(erg_all, clips)
    # ---- summary
    checks = {
        '1_keyboard_supported': res['devices']['keyboard']['pass'],
        '1_mouse_supported': res['devices']['mouse']['pass'],
        '2_chair_path_and_reversible': res['chair']['pass'],
        '3_body_all_clips': all(b['pass'] for b in body_out.values()),
        '4_continuity': res['continuity']['pass'],
        '5_ergonomics': res['ergonomics']['pass']}
    res['checks'] = checks
    res['all_pass'] = bool(all(checks.values()))
    res['elapsed_s'] = round(time.time() - t0, 1)
    return res


def _start_exact_ok(d):
    return all(d.values())


def continuity(body, clips, J, log=print):
    names = body.names
    fing = np.array([any(f in n for f in ('Thumb', 'Index', 'Middle', 'Ring', 'Pinky')) for n in names])
    seams = []
    for a, b in SEQUENCE:
        Ja, Jb = J[a], J[b]
        dta = float(np.diff(clips[a]['times']).mean())
        dtb = float(np.diff(clips[b]['times']).mean())
        dp = np.linalg.norm(Jb[0] - Ja[-1], axis=-1)
        va = (Ja[-1] - Ja[-2]) / dta
        vb = (Jb[1] - Jb[0]) / dtb
        dv = np.linalg.norm(vb - va, axis=-1)
        step_a = np.linalg.norm(Ja[-1] - Ja[-2], axis=-1)
        step_b = np.linalg.norm(Jb[1] - Jb[0], axis=-1)
        body_j = ~fing
        kp, kv = int(np.argmax(np.where(body_j, dp, -1))), int(np.argmax(np.where(body_j, dv, -1)))
        row = {'from': f'{a}.last', 'to': f'{b}.first',
               'position_delta_cm_max_body': {'value': r_(dp[kp]), 'joint': names[kp]},
               'position_delta_cm_hips': r_(dp[body.j['Hips']]),
               'position_delta_cm_hands': {s: r_(dp[body.j[f'{s}Hand']]) for s in ('Left', 'Right')},
               'velocity_delta_cm_s_max_body': {'value': r_(dv[kv]), 'joint': names[kv]},
               'velocity_delta_cm_s_hips': r_(dv[body.j['Hips']]),
               'velocity_delta_cm_s_hands': {s: r_(dv[body.j[f'{s}Hand']]) for s in ('Left', 'Right')},
               'neighbour_step_cm_max_body': r_(max(step_a[body_j].max(), step_b[body_j].max())),
               'fingers_position_delta_cm_max_DIAGNOSTIC': r_(dp[fing].max())}
        abrupt = dp[kp] > TH['seam_position_cm'] or dv[kv] > TH['seam_velocity_cm_s']
        row['abrupt'] = bool(abrupt)
        seams.append(row)
    # within-clip acceleration (pelvis, hands) vs the capture's own peak: JUDGED in the chair frame (the body's own
    # motion); the world value (body + the declared quintic chair roll) is reported next to the roll's own peak
    import life_gltf as G
    acc = {}
    for role, c in clips.items():
        g = G.Gltf(ROOT / CAPTURES[role])
        tcap = [float(t) for t in g.animation().key_times()]
        Wc, _ = body.E.joint_worlds(g, names, tcap)
        Jc = body.E.to_ue(Wc[..., :3, 3])
        dtc = float(np.diff(tcap).mean())
        dt = float(np.diff(c['times']).mean())
        roll_acc = accel(c['chair_off'], dt) if len(c['chair_off']) > 2 else np.zeros(1)
        acc[role] = {'chair_roll_peak_accel_cm_s2': r_(roll_acc.max(), 1), 'capture': CAPTURES[role],
                     'capture_fps': r_(1 / dtc, 2), 'clip_fps': r_(1 / dt, 2)}
        for jn in ('Hips', 'LeftHand', 'RightHand'):
            k = body.j[jn]
            a_c = accel(Jc[:, k], dtc)
            a_p = accel(J[role + '#chair'][:, k], dt)
            a_w = accel(J[role][:, k], dt)
            peak = float(a_c.max())
            over = np.nonzero(a_p > peak * TH['accel_vs_capture_peak_ratio'])[0] + 1
            acc[role][jn] = {'capture_peak_cm_s2': r_(peak, 1),
                             'clip_peak_chair_frame': {'value': r_(a_p.max(), 1), 'frame': int(np.argmax(a_p)) + 1},
                             'ratio': r_(a_p.max() / peak, 3), 'frames_over_capture_peak': int(len(over)),
                             'first_frames_over': over[:20].tolist(),
                             'world_with_roll_peak_cm_s2': r_(a_w.max(), 1), 'world_ratio': r_(a_w.max() / peak, 3)}
    # seam acceleration: the velocity change across a seam over one frame (chair frame), vs the capture peaks
    for row, (a, b) in zip(seams, SEQUENCE):
        Ja, Jb = J[a + '#chair'], J[b + '#chair']
        dta = float(np.diff(clips[a]['times']).mean())
        dtb = float(np.diff(clips[b]['times']).mean())
        row['seam_accel_ratio_vs_capture_peak'] = {}
        row['seam_accel_cm_s2'] = {}
        for jn in ('Hips', 'LeftHand', 'RightHand'):
            k = body.j[jn]
            dv = np.linalg.norm((Jb[1, k] - Jb[0, k]) / dtb - (Ja[-1, k] - Ja[-2, k]) / dta)
            a_s = dv / dtb
            peak = min(acc[a][jn]['capture_peak_cm_s2'], acc[b][jn]['capture_peak_cm_s2'])
            row['seam_accel_cm_s2'][jn] = r_(a_s, 1)
            row['seam_accel_ratio_vs_capture_peak'][jn] = r_(a_s / peak, 3)
        row['accel_over_capture_peak'] = bool(max(row['seam_accel_ratio_vs_capture_peak'].values()) > TH['accel_vs_capture_peak_ratio'])
    within_ok = all(v['frames_over_capture_peak'] == 0 for r in acc.values() for v in r.values() if isinstance(v, dict))
    return {'seams': seams, 'acceleration_vs_capture': acc,
            'abrupt_seams': [f"{s['from']} -> {s['to']}" for s in seams if s['abrupt']],
            'seams_accel_over_capture_peak': [f"{s['from']} -> {s['to']}" for s in seams if s['accel_over_capture_peak']],
            'within_clip_ok': bool(within_ok),
            'pass': bool(within_ok and not any(s['abrupt'] or s['accel_over_capture_peak'] for s in seams)),
            'abrupt_rule': f"position jump > {TH['seam_position_cm']} cm or velocity change > {TH['seam_velocity_cm_s']} cm/s "
                           "on any body joint (fingers reported separately); accel_over_capture_peak: the one-frame seam "
                           "acceleration of hips/hands exceeds the smaller capture peak of the two neighbours (chair frame)",
            'method': 'world joint positions (body shift with the chair) at the clip keys; seam velocity from one-frame '
                      'differences on each side; acceleration = second difference / dt^2; captures: the raw mh_mx clips '
                      '(their whole key range) under the same formula'}


def ergonomic_report(erg, clips):
    out = {'targets': {k: TH[k] for k in TH if k.startswith('ergo_')}, 'judged_on': 'DeskTyping_seated, every frame',
           'method': 'joint centres in UE world: elbow = ForeArm joint z - worktop top; upper arm = angle of '
                     'Arm->ForeArm from straight down; shoulder elevation = Shoulder->Arm clavicle elevation, minus the '
                     'SeatedIdle mean; wrist (judged) = the hand long axis (wrist -> middle knuckle) carried into the forearm\'s '
                     'bind frame, decomposed on the bind palm-normal (flexion +, toward the palm) and radial (deviation +) '
                     'axes, i.e. relative to the rig\'s straight bind hand: the TOTAL angle of the pose, independent of '
                     'any solver correction. Context only: the same decomposition of the elbow->wrist joint line in the '
                     'hand frame (joint-centre geometry; the bind hand itself reads non-zero on it)'}
    sides = {}
    allpass = True
    dt_t = clips['DeskTyping_seated']['times']
    for s in ('left', 'right'):
        e = erg['DeskTyping_seated'][s]
        idle = float(np.mean(erg['SeatedIdle'][s]['clavicle_elevation_deg']))
        shrug = e['clavicle_elevation_deg'] - idle
        th = TH
        tests = {
            'elbow_above_desk': (e['elbow_above_top_cm'] >= th['ergo_elbow_above_desk_cm'][0]) & (e['elbow_above_top_cm'] <= th['ergo_elbow_above_desk_cm'][1]),
            'upper_arm': e['upper_arm_from_vertical_deg'] <= th['ergo_upper_arm_from_vertical_deg'],
            'shoulder_elevation': shrug <= th['ergo_shoulder_elevation_vs_idle_deg'],
            'wrist_flexion': (e['wrist_flexion_deg'] >= th['ergo_wrist_flexion_deg'][0]) & (e['wrist_flexion_deg'] <= th['ergo_wrist_flexion_deg'][1]),
            'wrist_deviation': (e['wrist_deviation_deg'] >= th['ergo_wrist_deviation_deg'][0]) & (e['wrist_deviation_deg'] <= th['ergo_wrist_deviation_deg'][1])}
        share = {k: float(v.mean()) for k, v in tests.items()}
        ok = {k: v >= th['ergo_frame_share'] for k, v in share.items()}
        allpass &= all(ok.values())

        def rng(v):
            return [r_(np.min(v), 2), r_(np.percentile(v, 50), 2), r_(np.max(v), 2)]
        sides[s] = {
            'elbow_above_top_cm_min_med_max': rng(e['elbow_above_top_cm']),
            'elbow_z_cm_min_med_max': rng(e['elbow_z_cm']),
            'upper_arm_from_vertical_deg_min_med_max': rng(e['upper_arm_from_vertical_deg']),
            'clavicle_elevation_vs_idle_deg_min_med_max': rng(shrug),
            'wrist_flexion_deg_min_med_max': rng(e['wrist_flexion_deg']),
            'wrist_deviation_deg_min_med_max': rng(e['wrist_deviation_deg']),
            'context_wrist_joint_line_flexion_deg_min_med_max': rng(e['wrist_flexion_joint_line_deg']),
            'context_wrist_joint_line_deviation_deg_min_med_max': rng(e['wrist_deviation_joint_line_deg']),
            'context_bind_hand_joint_line_deg': [r_(v, 2) for v in e['bind_wrist_anatomical_deg']],
            'palm_down_share': r_(e['palm_down_share'], 4),
            'worst': {'elbow_highest': worst(e['elbow_above_top_cm'], dt_t, lowest=False),
                      'elbow_lowest': worst(e['elbow_above_top_cm'], dt_t),
                      'upper_arm_max': worst(e['upper_arm_from_vertical_deg'], dt_t, lowest=False),
                      'shoulder_shrug_max': worst(shrug, dt_t, lowest=False),
                      'wrist_flexion_max': worst(e['wrist_flexion_deg'], dt_t, lowest=False),
                      'wrist_extension_max': worst(e['wrist_flexion_deg'], dt_t),
                      'wrist_radial_max': worst(e['wrist_deviation_deg'], dt_t, lowest=False),
                      'wrist_ulnar_max': worst(e['wrist_deviation_deg'], dt_t)},
            'share_of_frames_meeting': {k: r_(v, 4) for k, v in share.items()}, 'pass': ok}
        # the same numbers on the other seated clips, for context (not judged)
        sides[s]['other_clips_context'] = {r: {'elbow_above_top_cm_min_max': [r_(np.min(erg[r][s]['elbow_above_top_cm']), 2), r_(np.max(erg[r][s]['elbow_above_top_cm']), 2)],
                                               'upper_arm_deg_min_max': [r_(np.min(erg[r][s]['upper_arm_from_vertical_deg']), 2), r_(np.max(erg[r][s]['upper_arm_from_vertical_deg']), 2)],
                                               'wrist_flexion_deg_min_max': [r_(np.min(erg[r][s]['wrist_flexion_deg']), 2), r_(np.max(erg[r][s]['wrist_flexion_deg']), 2)]}
                                           for r in ('SitToType_seated', 'TypeToSit_seated', 'SeatedIdle')}
    out['sides'] = sides
    out['pass'] = bool(allpass)
    return out


# ---------------------------------------------------------------- output
def to_jsonable(o):
    if isinstance(o, dict):
        return {str(k): to_jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [to_jsonable(v) for v in o]
    if isinstance(o, np.ndarray):
        return to_jsonable(o.tolist())
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return r_(o, 6)
    return o


def fmt_w(w, unit='cm'):
    if not w:
        return '–'
    return f"{w['value']} {unit} (f{w['frame']})"


def markdown(res, layout):
    L = []
    pf = lambda b: '**PASS**' if b else '**FAIL**'
    L.append('# Ergonomic layout refit: independent verification (source only, `ready: false`)\n')
    L.append(f"Verifier: `tools/verify_ergonomic_layout_refit.py` (independent of the layout solver). Proposal: "
             f"`{layout['proposal_file']}` (sha256 `{layout['proposal_sha256']}`, status `{layout['status']}`). "
             f"Nothing native is verified; `ready` stays false.\n")
    L.append('## Verdicts\n')
    L.append('| Check | Result |\n|---|---|')
    for k, v in res['checks'].items():
        L.append(f'| {k} | {pf(v)} |')
    L.append('')
    L.append('## Layout under test\n')
    L.append(f"- Keyboard delta (UE cm): {[r_(v) for v in layout['keyboard_delta_cm']]} ({layout['keyboard_delta_from']})")
    L.append(f"- Mouse delta (UE cm): {[r_(v) for v in layout['mouse_delta_cm']]} ({layout['mouse_delta_from']})")
    L.append(f"- Chair start {res['chair']['start_cm']}, roll {res['chair']['roll_cm']}, pulled in {res['chair']['pulled_in_translation_cm']}")
    L.append(f"- Clips: " + ', '.join(f"{r} `{c['glb']}` ({c['sha256'][:12]}…, {c['clip_source']})" for r, c in
                                      ((r, res['body']['clips'][r]) for r in ROLES)) + '\n')
    L.append('## 1. Devices on the worktop\n')
    L.append('| Device | Bottom − top (cm) | Feet on flat top | Footprint (UE cm) | Margin to slab AABB | Colliding items | Pass |\n|---|---|---|---|---|---|---|')
    for n, d in res['devices'].items():
        col = [k for k, c in d['items'].items() if c['collides']]
        L.append(f"| {n} | {d['bottom_minus_top_cm']} (original {d['original_transform_bottom_minus_top_cm']}) | {d['feet_over_flat_top']}/{d['feet_points']} | {d['footprint_cm']} | "
                 f"{d['footprint_margin_to_slab_aabb_cm']} | {', '.join(col) or 'none'} | {pf(d['pass'])} |")
    kb = res['devices']['keyboard']['items']
    L.append('\nKeyboard clearance to desk items (horizontal gap cm): ' + ', '.join(f"{k} {v['horizontal_gap_cm']}" for k, v in kb.items()))
    L.append(f"\nMonitor provenance: {res['geometry']['monitor_provenance']['home_js']}; {res['geometry']['monitor_provenance']['lift']}.\n")
    L.append('## 2. Chair (complete source chair, every triangle sampled at 1 cm)\n')
    c = res['chair']
    L.append(f"- Native shell on source surface: max {c['native_shell_on_source']['max']} cm (tol {c['native_shell_on_source']['tolerance']})")
    L.append(f"- Worst desk clearance along the roll: {c['path']['worst_desk']['desk_min_cm']} cm at offset {c['path']['worst_desk']['offset_cm']} "
             f"({c['path']['worst_desk']['chair_part']} vs {c['path']['worst_desk']['nearest_desk_part']})")
    L.append(f"- Floor gap range: {c['path']['floor_gap_cm']} cm; reversibility: {pf(c['reversibility']['pass'])} "
             f"(push-back retraces pull-in within {c['reversibility']['push_back_retraces_pull_in_cm']} cm)")
    L.append(f"- Verdict: {pf(c['pass'])}\n")
    L.append('## 3. Body, every frame\n')
    L.append('| Clip | Seat (main rule) | Soles lowest − floor | Legs vs desk min | Arms vs desk min (no fingers) | Torso | Pass |\n|---|---|---|---|---|---|---|')
    for r in ROLES:
        b = res['body']['clips'][r]
        s = b['seat_main_rule']
        L.append(f"| {r} | {'pass' if s['pass_main_rule'] else 'FAIL ' + str(s['failing_frame_count']) + '/' + str(s['gated_frames'])} | "
                 f"{fmt_w(b['soles']['lowest_sole_minus_floor_cm'])} | {b['legs_vs_desk']['min_cm']} | "
                 f"{b['arms_vs_desk']['min_cm_excluding_fingers']} | {b['torso_head_vs_desk']['min_cm']} | {pf(b['pass'])} |")
    for r in ('SitDown_seated', 'GetUp_seated'):
        x = res['body']['clips'][r]['seat_main_rule'].get('independent_settled_gate_crosscheck')
        if x:
            L.append(f"\n{r}: gate = {res['body']['clips'][r]['seat_main_rule']['gate_rule']}. Cross-check with this verifier's own "
                     f"settled gate ({x['gate_rule']}, {x['gated_frames']} frames): failing {x['failing_frames']} {x['messages']}; "
                     f"frames it adds: {x['extra_frames_vs_declared']}")
    L.append('\nWorst frames per segment (cm, frame, desk node):\n')
    for r in ROLES:
        b = res['body']['clips'][r]
        parts = []
        for grp in ('legs_vs_desk', 'arms_vs_desk'):
            for seg, gs in b[grp]['by_segment'].items():
                w = min((v for v in gs.values() if v), key=lambda v: v['value'], default=None)
                if w and w['value'] < 15:
                    parts.append(f"{seg} {w['value']} f{w['frame']} n{w.get('node')}")
        L.append(f"- {r}: " + ('; '.join(parts) or 'all > 15 cm'))
    L.append('\nFingertip contact (DIAGNOSTIC ONLY; old finger rests, new hands pending):\n')
    for r in ('DeskTyping_seated',):
        for s, d in res['body']['clips'][r]['fingertip_key_contact_DIAGNOSTIC_ONLY'].items():
            L.append(f"- {r} {s}: over keys {d['frames_over_keys']} frames, gap range {d['gap_cm_range']}")
    L.append('\n## 4. Continuity\n')
    L.append('| Seam | Pos Δ max (joint) | Hips Δ | Vel Δ max (joint) | Accel ratio vs capture (hips/L/R) | Abrupt |\n|---|---|---|---|---|---|')
    for s in res['continuity']['seams']:
        a = s['seam_accel_ratio_vs_capture_peak']
        L.append(f"| {s['from']} → {s['to']} | {s['position_delta_cm_max_body']['value']} ({s['position_delta_cm_max_body']['joint']}) | "
                 f"{s['position_delta_cm_hips']} | {s['velocity_delta_cm_s_max_body']['value']} ({s['velocity_delta_cm_s_max_body']['joint']}) | "
                 f"{a['Hips']}/{a['LeftHand']}/{a['RightHand']} | {'**yes**' if s['abrupt'] else 'no'} |")
    L.append(f"\nRule: {res['continuity']['abrupt_rule']}.\n")
    L.append('\nWithin-clip acceleration (chair frame, judged) vs the capture\'s own peak:\n')
    for r, d in res['continuity']['acceleration_vs_capture'].items():
        L.append(f"- {r} (chair roll peak {d['chair_roll_peak_accel_cm_s2']} cm/s², clip {d['clip_fps']} fps, capture {d['capture_fps']} fps): " +
                 ', '.join(f"{j} {v['ratio']}× of {v['capture_peak_cm_s2']} cm/s² ({v['frames_over_capture_peak']} fr over, peak f{v['clip_peak_chair_frame']['frame']}; world+roll {v['world_ratio']}×)"
                           for j, v in d.items() if isinstance(v, dict)))
    L.append(f"\nVerdict: {pf(res['continuity']['pass'])}\n")
    L.append('## 5. Ergonomics (DeskTyping, measured independently, total angles)\n')
    L.append(f"Targets: {res['ergonomics']['targets']}\n")
    L.append('| Side | Elbow above top cm (min/med/max) | Upper arm ° | Shoulder elev. vs idle ° | Wrist flex ° | Wrist dev ° |\n|---|---|---|---|---|---|')
    for s, e in res['ergonomics']['sides'].items():
        L.append(f"| {s} | {e['elbow_above_top_cm_min_med_max']} | {e['upper_arm_from_vertical_deg_min_med_max']} | "
                 f"{e['clavicle_elevation_vs_idle_deg_min_med_max']} | {e['wrist_flexion_deg_min_med_max']} | {e['wrist_deviation_deg_min_med_max']} |")
    L.append('')
    for s, e in res['ergonomics']['sides'].items():
        L.append(f"- {s}: share of frames meeting each target {e['share_of_frames_meeting']}; worst: " +
                 ', '.join(f"{k} {fmt_w(v, '')}" for k, v in e['worst'].items()))
    L.append(f"\nVerdict: {pf(res['ergonomics']['pass'])}\n")
    L.append('## Geometry used (origin/main bytes)\n')
    g = res['geometry']
    L.append(f"- ref `{g['ref']}` @ `{g['ref_commit']}`")
    L.append(f"- LINEA140 `{g['linea140']['path']}` sha256 `{g['linea140']['sha256']}`; placement `{g['linea140']['placement_source']}` "
             f"sha256 `{g['linea140']['placement_source_sha256']}` @ {g['linea140']['placement_source_commit']}: scale {g['linea140']['scale']}, "
             f"translation {g['linea140']['translation_m']} m; top {g['linea140']['top_cm']} cm, floor {g['linea140']['floor_cm']} cm")
    for k, v in g['main_sources'].items():
        L.append(f"- {k}: `{v['path']}` sha256 `{v['sha256']}` @ {v['commit']}")
    for k, v in g['pins'].items():
        L.append(f"- pinned `{k}` sha256 `{v}`")
    L.append(f"- chair report `{res['chair']['report']}` sha256 `{res['chair']['report_sha256']}`")
    L.append(f"- seat-fit source npz sha256 `{res['body']['source_npz_sha256']}`; {res['body']['skin']}")
    L.append(f"\nElapsed {res['elapsed_s']} s. All checks: {pf(res['all_pass'])}. `ready: false` (native unverified).")
    return '\n'.join(L) + '\n'


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--proposal', help='proposal JSON (omit with --baseline)')
    ap.add_argument('--baseline', action='store_true', help='verify the current committed layout instead')
    ap.add_argument('--source', default=str(ROOT / 'private-audit/seat-fit-source.npz'))
    ap.add_argument('--out-dir', default=str(ROOT / 'docs/proposed/ergonomic-layout-refit-verification'))
    ap.add_argument('--name', default=None, help='output basename (default: verification / baseline-verification)')
    ap.add_argument('--stride', type=int, default=2)
    ap.add_argument('--frames-limit', type=int, default=None, help='smoke runs only')
    ap.add_argument('--ref', default=MAIN_REF)
    args = ap.parse_args(argv)
    layout = baseline_layout() if args.baseline else layout_from_proposal(args.proposal)
    res = run_verification(layout, args.source, args.ref, args.stride, frames_limit=args.frames_limit)
    res['layout'] = {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in layout.items()}
    if args.frames_limit:
        res['SMOKE_frames_limit'] = args.frames_limit
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    name = args.name or ('baseline-verification' if args.baseline else 'verification')
    (out / f'{name}.json').write_text(json.dumps(to_jsonable(res), indent=1, allow_nan=False) + '\n')
    (out / f'{name}.md').write_text(markdown(to_jsonable(res), layout))
    print(json.dumps(res['checks'], indent=1))
    print('all_pass', res['all_pass'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
