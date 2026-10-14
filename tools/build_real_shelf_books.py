"""Replace the office shelf's procedural cube books with real scanned books (additive only).

Source books: Poly Haven `book_encyclopedia_set_01` (CC0, https://polyhaven.com/a/book_encyclopedia_set_01),
downloaded on the server under out/furniture-refresh/set-dressing/ (out/ is gitignored).

What the cube books are (the real source, not an estimate):
  * web/house/home.js:361-368 `books(x, y, z, n)` makes n RoundedBox meshes: width 0.035-0.055 m,
    height 0.16-0.28 m, depth exactly 0.14 m, centres at x + i*0.054, bottom at y, z fixed, one new
    `mat(color)` each (home.js:202), so batchArchitecture (home.js:2766-2806, groups need >= 3
    meshes sharing one material uuid) never merges them.
  * home.js:856-860 places them on the office shelf: boards at y = .25 + k*.45; only the boards with
    y > 1.6 get `books(1.2, y + .02, -3.71, 15)`. In IEEE doubles the loop gives 1.5999999999999999
    (not > 1.6), 2.05 and 2.5, so exactly 2 rows x 15 = 30 books, bottoms at runtime y 2.07 and 2.52.
  * home.js:2819-2833 names every remaining static scene child `house-static-<N>` (name and
    userData.bakeId), which the GLTFExporter (home.js:3145) writes as the node name and extras.
    N depends on scene order, so the builder matches the name PATTERN plus the exact geometric
    signature above, and refuses unless exactly those 30 objects are found.
  * home.js:938 `books(-3.3, 3.035, 1, 5)` (5 loft books) is NOT on the shelf and is excluded.
  * The shelf they stand on: tools/build_home_office_shelves.py (6 boards, tops .2675 + i*.45, 2.35 x
    .34 m, three back cleats), loaded at runtime (2.125, 0, -3.72) by home.js:861-876 with bakeIds
    `house-office-shelves-<name>`. Support surfaces are measured here from the evaluated geometry.

Patterns reused from tools/reference_home_dressing.py (imported, not edited): coordinate helpers,
verify_base, evaluate_object fingerprints, tri_box_overlap, _ray_triangle, glb_json, sha256_file.

Server only (root runs it; never on the Mac, never renders, never saves over the base):
    B=/workspace/sub01-tools/blender-4.5.3-linux-x64/blender
    BASE=/workspace/sub01-home-private/out/native-reference-base/house.blend
    "$B" --background --factory-startup "$BASE" --python tools/build_real_shelf_books.py -- \
        --allow-unassembled --books-asset <book_encyclopedia_set_01 .blend/.gltf> --output-dir out/real-books
See docs/proposed/real-shelf-books.md.
"""
import argparse
import hashlib
import json
import math
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reference_home_dressing as rd  # noqa: E402  (pure-Python helpers; bpy optional)
from real_furniture_base import verify_base, sha256_file, glb_json

try:  # Blender only
    import bpy  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None

COLLECTION = 'SUB01_RealShelfBooks'
SOURCE_COLLECTION = 'SUB01_RealShelfBooks_Source'
NAME_PREFIX = 'SUB01_RealBook_'
TAG = 'sub01RealShelfBooks'
ASSET_NAME = 'book_encyclopedia_set_01'
ASSET_URL = 'https://polyhaven.com/a/book_encyclopedia_set_01'
ASSET_LICENSE = 'CC0 1.0'
DEFAULT_SEED = 20261014

# ---------------------------------------------------------------- original cube-book signature
# All values are runtime metres from web/house/home.js (see module docstring); Blender = (x, -z, y).
ORIGINAL_NAME_RE = re.compile(r'^house-static-\d+$')
ORIGINAL_ROW_X0 = 1.2          # home.js:859 books(1.2, ...)
ORIGINAL_STEP = 0.054          # home.js:366 x + i * 0.054
ORIGINAL_PER_ROW = 15          # home.js:859 n = 15
ORIGINAL_Z = -3.71             # home.js:859 z
ORIGINAL_DEPTH = 0.14          # home.js:366 box depth
ORIGINAL_BOTTOMS = (2.07, 2.52)  # home.js:856-859 y + .02 for y in (2.05, 2.5)
ORIGINAL_WIDTH = (0.035, 0.055)  # home.js:364 .035 + random() * .02
ORIGINAL_HEIGHT = (0.16, 0.28)   # home.js:363 .16 + random() * .12
EXPECTED_ORIGINALS = ORIGINAL_PER_ROW * len(ORIGINAL_BOTTOMS)
SIG_TOL = 0.003
# Shelf search region (Blender metres) around home.js shelf 2.125 +- 1.175, runtime z -3.72 +- .17.
SHELF_REGION = ((0.85, 3.40, 0.05), (3.40, 4.00, 3.00))
# Unreal stable reference pivots (bakeId prefixes cited in reference_home_dressing.ANCHOR_SOURCES).
REFERENCE_PIVOT_PREFIXES = ('house-office-desk-', 'house-sofa-', 'house-cc0-coffee-table-',
                            'house-coffee-table-', 'house-office-shelves-')

CONTACT_GAP = 0.0005      # planned air gap at every resting contact
CONTACT_TOL = 0.002       # accepted contact distance
COLLISION_SHRINK = 0.0008  # boxes shrink this much before triangle / box tests (touching allowed)
BOOK_LIMITS = {'height': (0.12, 0.45), 'thickness': (0.008, 0.12), 'depth': (0.08, 0.36)}


class RefusedError(RuntimeError):
    """Inputs do not match what the builder was written against; nothing is written."""


def canonical(name):
    return re.sub('[^a-z0-9]', '', str(name).lower())


# ---------------------------------------------------------------- small linear algebra (no numpy)
def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(len(b))) for j in range(len(b[0]))] for i in range(len(a))]


def mat_vec(m, v):
    return tuple(sum(m[i][k] * v[k] for k in range(3)) for i in range(3))


def transpose(m):
    return [list(r) for r in zip(*m)]


def rot_z(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]


def rot_y(rad):
    """Rotation about the local depth axis: u' = x cos + z sin, w' = -x sin + z cos."""
    c, s = math.cos(rad), math.sin(rad)
    return [[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]]


def matrix4(rot, trans):
    return [list(rot[0]) + [trans[0]], list(rot[1]) + [trans[1]], list(rot[2]) + [trans[2]], [0.0, 0.0, 0.0, 1.0]]


def mat4_point(m, p):
    return tuple(m[i][0] * p[0] + m[i][1] * p[1] + m[i][2] * p[2] + m[i][3] for i in range(3))


def jacobi_eigen(a, sweeps=60):
    """Symmetric 3x3 eigen-decomposition: (values, vectors as columns)."""
    a = [list(map(float, r)) for r in a]
    v = [[1.0 if i == j else 0.0 for j in range(3)] for i in range(3)]
    for _ in range(sweeps):
        off = sum(a[i][j] ** 2 for i in range(3) for j in range(3) if i != j)
        if off < 1e-30:
            break
        for p, q in ((0, 1), (0, 2), (1, 2)):
            if abs(a[p][q]) < 1e-30:
                continue
            theta = (a[q][q] - a[p][p]) / (2 * a[p][q])
            t = (1.0 if theta >= 0 else -1.0) / (abs(theta) + math.sqrt(theta * theta + 1))
            c = 1 / math.sqrt(t * t + 1)
            s = t * c
            for k in range(3):
                akp, akq = a[k][p], a[k][q]
                a[k][p], a[k][q] = c * akp - s * akq, s * akp + c * akq
            for k in range(3):
                apk, aqk = a[p][k], a[q][k]
                a[p][k], a[q][k] = c * apk - s * aqk, s * apk + c * aqk
            for k in range(3):
                vkp, vkq = v[k][p], v[k][q]
                v[k][p], v[k][q] = c * vkp - s * vkq, s * vkp + c * vkq
    return [a[i][i] for i in range(3)], v


# ---------------------------------------------------------------- 1. identify the cube books
def original_signature(aabb):
    """None if a connected component with this world AABB (Blender metres) is one of the home.js
    shelf cube books, else the reason it is not. Geometry only: a material-batched node may carry
    any name, so the name never qualifies or disqualifies a component."""
    lo, hi = aabb
    w, d, h = (hi[i] - lo[i] for i in range(3))
    if abs(d - ORIGINAL_DEPTH) > SIG_TOL:
        return f'depth {d:.4f}'
    if not ORIGINAL_WIDTH[0] - SIG_TOL <= w <= ORIGINAL_WIDTH[1] + SIG_TOL:
        return f'width {w:.4f}'
    if not ORIGINAL_HEIGHT[0] - SIG_TOL <= h <= ORIGINAL_HEIGHT[1] + SIG_TOL:
        return f'height {h:.4f}'
    if abs((lo[1] + hi[1]) / 2 - (-ORIGINAL_Z)) > SIG_TOL:
        return f'depth centre {(lo[1] + hi[1]) / 2:.4f}'
    if not any(abs(lo[2] - b) <= SIG_TOL for b in ORIGINAL_BOTTOMS):
        return f'bottom {lo[2]:.4f}'
    k = ((lo[0] + hi[0]) / 2 - ORIGINAL_ROW_X0) / ORIGINAL_STEP
    if abs(k - round(k)) * ORIGINAL_STEP > SIG_TOL or not 0 <= round(k) < ORIGINAL_PER_ROW:
        return f'x centre {(lo[0] + hi[0]) / 2:.4f}'
    return None


def triangle_components(tris, weld=1e-5):
    """Exact connected components of a triangle list: vertices are welded by position (three.js
    BoxGeometry / RoundedBoxGeometry duplicate vertices per face, and the glTF importer keeps them
    split), then triangles sharing a welded vertex are joined. Returns
    [{'triangle_ids': [...ascending], 'aabb': (lo, hi)}] ordered by first triangle id."""
    parent = list(range(len(tris)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    owner = {}
    for ti, tri in enumerate(tris):
        for p in tri:
            key = tuple(round(c / weld) for c in p)
            if key in owner:
                a, b_ = find(owner[key]), find(ti)
                if a != b_:
                    parent[max(a, b_)] = min(a, b_)
            else:
                owner[key] = ti
    groups = {}
    for ti in range(len(tris)):
        groups.setdefault(find(ti), []).append(ti)
    out = []
    for root in sorted(groups):
        ids = groups[root]
        out.append({'triangle_ids': ids, 'aabb': _aabb([p for i in ids for p in tris[i]])})
    return out


def _region_hit(aabb, pad=0.05):
    return all(aabb[0][k] <= SHELF_REGION[1][k] + pad and aabb[1][k] >= SHELF_REGION[0][k] - pad for k in range(3))


def _round_tri(tri):
    return [[round(c, 5) for c in rd.blender_to_runtime(p)] for p in tri]


def identify_original_books(records):
    """Exactly the 30 shelf cube books, one per (row, index) slot, found per EXACT connected component
    of every evaluated node in the shelf region. Returns {'books', 'separate', 'batched'}:
      separate: a node whose only component is one book -> safe to hide that node;
      batched:  a node holding several books and/or non-book geometry -> NEVER hidden; a triangle-ID
                excision set (the book components) plus a remainder spec is emitted instead.
    Raises RefusedError (listing matches and near misses) on any count/slot ambiguity."""
    books, near, nodes = [], [], {}
    for rec in records:
        if not _region_hit(rec['aabb']):
            continue
        comps = triangle_components(rec['tris'])
        hits = []
        for ci, comp in enumerate(comps):
            reason = original_signature(comp['aabb'])
            lo, hi = comp['aabb']
            if reason is None:
                row = min(range(len(ORIGINAL_BOTTOMS)), key=lambda r: abs(lo[2] - ORIGINAL_BOTTOMS[r]))
                index = round(((lo[0] + hi[0]) / 2 - ORIGINAL_ROW_X0) / ORIGINAL_STEP)
                centre = tuple((lo[i] + hi[i]) / 2 for i in range(3))
                hits.append({'name': rec['name'], 'ident': rec.get('ident', rec['name']), 'component': ci,
                             'triangle_ids': comp['triangle_ids'], 'row': row, 'index': index,
                             'aabb_blender': [list(lo), list(hi)],
                             'centre_runtime': list(rd.blender_to_runtime(centre))})
            elif abs((hi[1] - lo[1]) - ORIGINAL_DEPTH) <= SIG_TOL:
                near.append({'name': rec['name'], 'component': ci, 'reason': reason})
        if hits:
            nodes[rec['name']] = (rec, comps, hits)
            books += hits
    slots = {(m['row'], m['index']) for m in books}
    if len(books) != EXPECTED_ORIGINALS or len(slots) != EXPECTED_ORIGINALS:
        raise RefusedError(json.dumps({
            'error': f'expected exactly {EXPECTED_ORIGINALS} shelf cube-book components (2 rows x 15, '
                     f'home.js:856-860), found {len(books)} in {len(slots)} slots',
            'matched': sorted(f"{m['name']}#{m['component']}" for m in books), 'near_misses': near[:60]}))
    separate, batched = [], []
    for name, (rec, comps, hits) in sorted(nodes.items()):
        if len(comps) == 1 and len(hits) == 1:
            h = hits[0]
            h['pivot_runtime'] = list(rd.blender_to_runtime(rec.get('pivot', rd.runtime_to_blender(h['centre_runtime']))))
            h['mode'] = 'hide'
            separate.append(h)
            continue
        excise = sorted(i for h in hits for i in h['triangle_ids'])
        keep = sorted(set(range(len(rec['tris']))) - set(excise))
        for h in hits:
            h['mode'] = 'excise'
        batched.append({
            'node': name, 'ident': rec.get('ident', name), 'canonical': canonical(name),
            'canonical_ident': canonical(rec.get('ident', name)),
            'triangle_order': 'blender evaluated loop_triangles of the glTF-imported node (world space)',
            'triangle_count': len(rec['tris']), 'components_total': len(comps),
            'excise': {'components': [{'component': h['component'], 'row': h['row'], 'index': h['index'],
                                       'triangle_ids': h['triangle_ids'], 'aabb_blender': h['aabb_blender']}
                                      for h in hits],
                       'triangle_ids': excise, 'triangle_count': len(excise),
                       'triangles_runtime_m': [_round_tri(rec['tris'][i]) for i in excise]},
            'remainder': {'triangle_count': len(keep), 'components': len(comps) - len(hits),
                          'aabb_blender': [list(x) for x in _aabb([p for i in keep for p in rec['tris'][i]])] if keep else None,
                          'positions_sha256': hashlib.sha256(json.dumps([_round_tri(rec['tris'][i]) for i in keep])
                                                             .encode()).hexdigest()},
            'never_hide_whole_node': True})
    books.sort(key=lambda m: (m['row'], m['index']))
    return {'books': books, 'separate': separate, 'batched': batched}


# ---------------------------------------------------------------- 2. shelf support surfaces
def _tri_normal(tri):
    a, b, c = tri
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    area2 = math.sqrt(sum(x * x for x in n))
    return (tuple(x / area2 for x in n) if area2 else (0.0, 0.0, 0.0)), area2 / 2


def detect_boards(tris, min_area=0.3, level_tol=0.0015, normal_min=0.995):
    """Horizontal support levels from evaluated triangles (Blender world metres, Z up).
    Groups upward faces by height; a level with >= min_area of top surface is a board. The
    underside (downward faces) of the next board above sets the clearance."""
    up, down = {}, {}
    for tri in tris:
        n, area = _tri_normal(tri)
        if area <= 0 or abs(n[2]) < normal_min:
            continue
        z = sum(p[2] for p in tri) / 3
        bucket = up if n[2] > 0 else down
        key = round(z / level_tol)
        entry = bucket.setdefault(key, {'z': [], 'area': 0.0, 'lo': [1e9, 1e9], 'hi': [-1e9, -1e9]})
        entry['z'].append(z)
        entry['area'] += area
        for p in tri:
            for i in range(2):
                entry['lo'][i] = min(entry['lo'][i], p[i])
                entry['hi'][i] = max(entry['hi'][i], p[i])

    def merged(bucket):
        levels = []
        for key in sorted(bucket):
            e = bucket[key]
            z = sum(e['z']) / len(e['z'])
            if levels and abs(levels[-1]['z'] - z) <= level_tol:
                prev = levels[-1]
                prev['area'] += e['area']
                prev['lo'] = [min(prev['lo'][i], e['lo'][i]) for i in range(2)]
                prev['hi'] = [max(prev['hi'][i], e['hi'][i]) for i in range(2)]
            else:
                levels.append({'z': z, 'area': e['area'], 'lo': list(e['lo']), 'hi': list(e['hi'])})
        return levels
    boards = [l for l in merged(up) if l['area'] >= min_area]
    undersides = [l for l in merged(down) if l['area'] >= min_area]
    for b in boards:
        above = [u['z'] for u in undersides if u['z'] > b['z'] + 0.01
                 and u['lo'][0] < b['hi'][0] and u['hi'][0] > b['lo'][0]]
        b['clearance'] = (min(above) - b['z']) if above else None
        b['z'] = round(b['z'], 6)
    return boards


def board_frame(board, front_axis='-Y'):
    """(origin, rotation board->world, u_len, v_len). u runs along the board, v from the front edge
    to the back, w up. Spines (book local -y) face -v, i.e. the room."""
    yaw = {'-Y': 0.0, '+Y': 180.0, '-X': -90.0, '+X': 90.0}[front_axis]
    rot = rot_z(yaw)
    (x0, y0), (x1, y1), z = board['lo'], board['hi'], board['z']
    corners = [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]
    inv = transpose(rot)
    local = [mat_vec(inv, (x, y, 0.0)) for x, y in corners]
    umin, vmin = min(p[0] for p in local), min(p[1] for p in local)
    u_len, v_len = max(p[0] for p in local) - umin, max(p[1] for p in local) - vmin
    origin = mat_vec(rot, (umin, vmin, 0.0))
    return (origin[0], origin[1], z), rot, u_len, v_len


# ---------------------------------------------------------------- 3. the real books in the asset
def islands(n_verts, faces):
    """Connected vertex sets (union-find over face vertices)."""
    parent = list(range(n_verts))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for f in faces:
        r0 = find(f[0])
        for v in f[1:]:
            r = find(v)
            if r != r0:
                parent[r] = r0
    groups = {}
    for f in faces:
        for v in f:
            groups.setdefault(find(v), set()).add(v)
    return [groups[k] for k in sorted(groups, key=lambda k: min(groups[k]))]


def _aabb(points):
    return (tuple(min(p[i] for p in points) for i in range(3)), tuple(max(p[i] for p in points) for i in range(3)))


def _volume(lo, hi):
    return max(0.0, hi[0] - lo[0]) * max(0.0, hi[1] - lo[1]) * max(0.0, hi[2] - lo[2])


def cluster_parts(parts, overlap=0.5):
    """Merge parts (cover, page block, ...) whose AABBs overlap by >= overlap of the smaller one.
    parts: [{'points': [...], ...}] -> list of lists of part indices. Neighbouring books only touch
    by a sliver, so they stay separate."""
    boxes = [_aabb(p['points']) for p in parts]
    volumes = [_volume(*box) for box in boxes]
    parent = list(range(len(parts)))

    def find(i):
        while parent[i] != i:
            i = parent[i]
        return i
    # Keep legacy i,j union order: component roots affect returned group order.
    # Positive-overlap finite AABBs can only merge with strictly overlapping
    # intervals on all axes. Zero-volume UV-seam islands cannot pass the legacy
    # positive threshold (their smaller volume falls back to 1e-12).
    regular = math.isfinite(overlap) and overlap > 0 and all(
        math.isfinite(volume) and overlap * (volume or 1e-12) > 0 and all(math.isfinite(value) for corner in box for value in corner)
        for box, volume in zip(boxes, volumes))
    if regular:
        import heapq
        eligible = [i for i, volume in enumerate(volumes) if volume > 0]
        candidates = [[] for _ in parts]
        if eligible:
            def separation(axis):
                extent = max(boxes[i][1][axis] for i in eligible) - min(boxes[i][0][axis] for i in eligible)
                width = sum(boxes[i][1][axis] - boxes[i][0][axis] for i in eligible) / len(eligible)
                return extent / width if width > 0 else 0
            axis = max(range(3), key=separation)
            active, ends = set(), []
            for i in sorted(eligible, key=lambda i: (boxes[i][0][axis], i)):
                low = boxes[i][0][axis]
                while ends and ends[0][0] <= low:
                    _, expired = heapq.heappop(ends)
                    active.remove(expired)
                for j in active:
                    if all(min(boxes[i][1][k], boxes[j][1][k]) > max(boxes[i][0][k], boxes[j][0][k]) for k in range(3)):
                        first, second = sorted((i, j))
                        candidates[first].append(second)
                active.add(i)
                heapq.heappush(ends, (boxes[i][1][axis], i))
        pairs = ((i, j) for i, neighbours in enumerate(candidates) for j in sorted(neighbours))
    else:
        # Preserve legacy comparisons for zero/negative/NaN thresholds or
        # nonfinite boxes/volumes rather than guessing their merge semantics.
        pairs = ((i, j) for i in range(len(parts)) for j in range(i + 1, len(parts)))
    for i, j in pairs:
        lo = tuple(max(boxes[i][0][k], boxes[j][0][k]) for k in range(3))
        hi = tuple(min(boxes[i][1][k], boxes[j][1][k]) for k in range(3))
        small = min(volumes[i], volumes[j]) or 1e-12
        if _volume(lo, hi) >= overlap * small:
            parent[find(j)] = find(i)
    groups = {}
    for i in range(len(parts)):
        groups.setdefault(find(i), []).append(i)
    return [groups[k] for k in sorted(groups)]


AXES = {'+X': (1, 0, 0), '-X': (-1, 0, 0), '+Y': (0, 1, 0), '-Y': (0, -1, 0)}


def book_frame(points, spine_axis='-Y', max_tilt_deg=25.0):
    """Measured canonical frame of one book: rows of `rot` are the book's local axes in asset
    space (x thickness, y depth with the spine at -y, z height). Returns rot, dims (t, d, h) and
    the asset-space origin at the bottom centre. Rigid only: no scaling."""
    n = len(points)
    c = tuple(sum(p[i] for p in points) / n for i in range(3))
    cov = [[sum((p[i] - c[i]) * (p[j] - c[j]) for p in points) / n for j in range(3)] for i in range(3)]
    _, vecs = jacobi_eigen(cov)
    cols = [tuple(vecs[r][k] for r in range(3)) for k in range(3)]
    up = max(range(3), key=lambda k: abs(cols[k][2]))
    z = cols[up] if cols[up][2] > 0 else tuple(-x for x in cols[up])
    tilt = math.degrees(math.acos(min(1.0, abs(z[2]))))
    if tilt > max_tilt_deg:
        raise RefusedError(f'book is tilted {tilt:.1f} deg in the asset; not an upright book')
    rest = [cols[k] for k in range(3) if k != up]
    spine = AXES[spine_axis]
    yk = max(range(2), key=lambda k: abs(sum(rest[k][i] * spine[i] for i in range(3))))
    y = rest[yk]
    if sum(y[i] * spine[i] for i in range(3)) > 0:   # local -y must point along the spine direction
        y = tuple(-v for v in y)
    x = (y[1] * z[2] - y[2] * z[1], y[2] * z[0] - y[0] * z[2], y[0] * z[1] - y[1] * z[0])
    rot = [list(x), list(y), list(z)]
    local = [mat_vec(rot, tuple(p[i] - c[i] for i in range(3))) for p in points]
    lo, hi = _aabb(local)
    dims = tuple(hi[i] - lo[i] for i in range(3))
    centre_local = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2])
    origin = tuple(c[i] + sum(rot[k][i] * centre_local[k] for k in range(3)) for i in range(3))
    return {'rot': rot, 'dims': dims, 'origin': origin, 'asset_tilt_deg': round(tilt, 3)}


def check_book_dims(dims, unit_scale=1.0):
    t, d, h = (x * unit_scale for x in dims)
    for key, val in (('thickness', t), ('depth', d), ('height', h)):
        lo, hi = BOOK_LIMITS[key]
        if not lo <= val <= hi:
            return f'{key} {val:.4f} m outside {lo}-{hi}'
    if t > d or t > h:
        return 'thickness is not the smallest dimension'
    return None


# ---------------------------------------------------------------- 4. deterministic layout
def local_corners(dims):
    t, d, h = dims
    return [(x, y, z) for x in (-t / 2, t / 2) for y in (-d / 2, d / 2) for z in (0.0, h)]


def _place(rot, dims, target_min):
    pts = [mat_vec(rot, c) for c in local_corners(dims)]
    lo = _aabb(pts)[0]
    return tuple(target_min[i] - lo[i] for i in range(3))


def _bounds(rot, trans, dims):
    pts = [tuple(p[i] + trans[i] for i in range(3)) for p in (mat_vec(rot, c) for c in local_corners(dims))]
    return _aabb(pts)


def plan_board(board_index, u_range, v_len, clearance, books, rng, template):
    """Board-frame placements for one board. books: {key: (t, d, h)} measured, unscaled."""
    keys = sorted(books)
    out = []
    u = u_range[0] + 0.004

    def pick(max_h=None, max_d=None):
        for _ in range(12):
            k = keys[int(rng.random() * len(keys))]
            t, d, h = books[k]
            if (max_h is None or h <= max_h) and (max_d is None or d <= max_d):
                return k
        return None

    def inset():
        return 0.010 + rng.random() * 0.008

    def upright(n):
        nonlocal u
        for _ in range(n):
            k = pick(max_h=clearance - 0.01, max_d=v_len - 0.04)
            if k is None:
                return
            dims = books[k]
            rot = [[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]]
            if u + dims[0] > u_range[1]:
                return
            trans = _place(rot, dims, (u, inset(), CONTACT_GAP))
            out.append({'mode': 'upright', 'source': k, 'board': board_index, 'rot': rot, 'trans': trans,
                        'dims': dims, 'lean_deg': 0.0, 'rests_on': 'board'})
            u = _bounds(rot, trans, dims)[1][0] + 0.0008 + rng.random() * 0.0012

    def lean():
        nonlocal u
        if not out or out[-1]['mode'] != 'upright':
            return
        nb = out[-1]
        nb_hi = _bounds(nb['rot'], nb['trans'], nb['dims'])[1]
        k = pick(max_h=clearance - 0.01, max_d=v_len - 0.04)
        if k is None:
            return
        t, d, h = books[k]
        theta = math.radians(10 + rng.random() * 12)
        if h * math.cos(theta) > nb['dims'][2] - 0.004:      # top corner must meet the neighbour's side
            ratio = (nb['dims'][2] - 0.004) / h
            if ratio <= math.cos(math.radians(32)):
                return
            theta = math.acos(ratio)
        rot = rot_y(-theta)                                  # top tips toward -u, onto the neighbour
        trans = _place(rot, (t, d, h), (nb_hi[0] + CONTACT_GAP, inset(), CONTACT_GAP))
        lo, hi = _bounds(rot, trans, (t, d, h))
        if hi[0] > u_range[1] or hi[2] > clearance - 0.005:
            return
        out.append({'mode': 'lean', 'source': k, 'board': board_index, 'rot': rot, 'trans': trans,
                    'dims': (t, d, h), 'lean_deg': round(math.degrees(theta), 3), 'rests_on': 'board',
                    'leans_on': len(out) - 1})
        u = hi[0] + 0.006 + rng.random() * 0.01

    def stack(n):
        nonlocal u
        chosen = [k for k in (pick(max_d=v_len - 0.04) for _ in range(n)) if k]
        chosen.sort(key=lambda k: -books[k][2])          # longest at the bottom: upper books never overhang
        if not chosen:
            return
        width = max(books[k][2] for k in chosen)
        if u + width > u_range[1]:
            return
        w = CONTACT_GAP
        below = None
        base_inset = inset()
        rot = rot_y(math.pi / 2)                             # height along +u, thickness up, spine still -v
        for k in chosen:
            t, d, h = books[k]
            if w + t > clearance - 0.01:
                break
            slack = (width - h) / 2 if below is None else min(width - h, 0.006) / 2
            target = (u + (width - h) / 2 + (rng.random() - 0.5) * slack, base_inset + rng.random() * 0.004, w)
            trans = _place(rot, (t, d, h), target)
            out.append({'mode': 'stack', 'source': k, 'board': board_index, 'rot': rot, 'trans': trans,
                        'dims': (t, d, h), 'lean_deg': 0.0,
                        'rests_on': 'board' if below is None else below})
            below = len(out) - 1
            w = _bounds(rot, trans, (t, d, h))[1][2] + CONTACT_GAP
        u = u + width + 0.012 + rng.random() * 0.01

    for step, arg in template:
        if step == 'gap':
            u += arg
        elif step == 'row':
            upright(arg if arg else 10 ** 6)
        elif step == 'lean':
            lean()
        elif step == 'stack':
            stack(arg)
    return out


TEMPLATES = (
    (('row', 5), ('lean', 0), ('gap', 0.02), ('stack', 3), ('gap', 0.01), ('row', 0)),
    (('stack', 2), ('gap', 0.01), ('row', 6), ('lean', 0), ('gap', 0.02), ('row', 0)),
)


def plan_layout(hosts, books, seed=DEFAULT_SEED):
    """hosts: [{'board': board dict, 'frame': board_frame(...), 'u_range': (u0, u1)}] in order.
    Returns world placements with stable ids."""
    rng = random.Random(seed)
    placements = []
    for bi, host in enumerate(hosts):
        origin, brot, u_len, v_len = host['frame']
        clearance = host['board']['clearance'] or host.get('top_clearance', 0.40)
        local = plan_board(bi, host['u_range'], v_len, clearance, books, rng, TEMPLATES[bi % len(TEMPLATES)])
        base = len(placements)
        for p in local:
            for key in ('leans_on',):
                if key in p:
                    p[key] = base + p[key]
            if isinstance(p['rests_on'], int):
                p['rests_on'] = base + p['rests_on']
            wrot = mat_mul(brot, p['rot'])
            wtrans = tuple(origin[i] + mat_vec(brot, p['trans'])[i] for i in range(3))
            p['world'] = matrix4(wrot, wtrans)
            placements.append(p)
    for i, p in enumerate(placements):
        p['id'] = f'{NAME_PREFIX}{i + 1:02d}'
    return placements


# ---------------------------------------------------------------- 5. checks on the actual geometry
def obb(p, shrink=0.0):
    t, d, h = p['dims']
    m = p['world']
    centre = mat4_point(m, (0.0, 0.0, h / 2))
    axes = [tuple(m[r][k] for r in range(3)) for k in range(3)]
    half = (max(1e-5, t / 2 - shrink), max(1e-5, d / 2 - shrink), max(1e-5, h / 2 - shrink))
    return centre, axes, half


def world_corners(p):
    return [mat4_point(p['world'], c) for c in local_corners(p['dims'])]


def obb_overlap(a, b):
    """Separating-axis test for two oriented boxes."""
    ca, aa, ha = a
    cb, ab, hb = b
    t = [cb[i] - ca[i] for i in range(3)]
    axes = list(aa) + list(ab)
    for u in aa:
        for v in ab:
            cr = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            if sum(x * x for x in cr) > 1e-12:
                axes.append(cr)
    for ax in axes:
        ra = sum(ha[i] * abs(sum(aa[i][k] * ax[k] for k in range(3))) for i in range(3))
        rb = sum(hb[i] * abs(sum(ab[i][k] * ax[k] for k in range(3))) for i in range(3))
        if abs(sum(t[k] * ax[k] for k in range(3))) > ra + rb:
            return False
    return True


def tri_hits_obb(tri, box):
    centre, axes, half = box
    local = [tuple(sum((p[k] - centre[k]) * axes[i][k] for k in range(3)) for i in range(3)) for p in tri]
    return rd.tri_box_overlap((0.0, 0.0, 0.0), half, local)


def validate_placements(placements, obstacles, hosts, support_tris):
    """Check every placement against the evaluated home. obstacles: [{'ident', 'aabb', 'tris'}]
    (Blender metres, the cube books excluded); support_tris: shelf board triangles. Returns
    (accepted, rejected); a book that loses its support (neighbour/base rejected) is rejected too."""
    accepted, rejected = {}, []
    for i, p in enumerate(placements):
        reasons, checks = [], {}
        host = hosts[p['board']]
        origin, brot, u_len, v_len = host['frame']
        board_z = host['board']['z']
        inv = transpose(brot)
        corners = world_corners(p)
        local = [mat_vec(inv, tuple(c[k] - origin[k] for k in range(3))) for c in corners]
        lo, hi = _aabb(local)
        clearance = host['board']['clearance'] or host.get('top_clearance', 0.40)
        if lo[0] < -1e-6 or hi[0] > u_len + 1e-6 or lo[1] < -1e-6 or hi[1] > v_len + 1e-6:
            reasons.append('outside_board')
        if hi[2] > clearance - 0.003:
            reasons.append(f'height_clearance {hi[2]:.3f}>{clearance:.3f}')
        checks['board_frame_bounds'] = [list(map(lambda x: round(x, 5), lo)), list(map(lambda x: round(x, 5), hi))]
        # support
        if p['rests_on'] == 'board':
            gap = lo[2]
            checks['bottom_gap_m'] = round(gap, 6)
            if not -1e-6 <= gap <= CONTACT_TOL:
                reasons.append(f'not_on_board gap {gap:.4f}')
            bottom = [c for c, l in zip(corners, local) if l[2] <= lo[2] + 0.001]
            hits = 0
            for c in bottom:
                origin_ray = (c[0], c[1], c[2] + 0.005)
                for tri in support_tris:
                    t = rd._ray_triangle(origin_ray, (0.0, 0.0, -1.0), tri)
                    if t is not None and t <= 0.005 + CONTACT_TOL + 0.001:
                        hits += 1
                        break
            checks['support_rays_hit'] = f'{hits}/{len(bottom)}'
            if hits < len(bottom):
                reasons.append(f'unsupported {hits}/{len(bottom)} bottom contacts on an evaluated board')
        else:
            below = p['rests_on']
            if below not in accepted:
                reasons.append(f'support_lost {below}')
            else:
                b = placements[below]
                bl = _aabb([mat_vec(inv, tuple(c[k] - origin[k] for k in range(3))) for c in world_corners(b)])
                gap = lo[2] - bl[1][2]
                checks['stack_gap_m'] = round(gap, 6)
                if not -1e-6 <= gap <= CONTACT_TOL:
                    reasons.append(f'not_on_book_below gap {gap:.4f}')
                if lo[0] < bl[0][0] - 1e-6 or hi[0] > bl[1][0] + 1e-6 or lo[1] < bl[0][1] - 0.02 or hi[1] > bl[1][1] + 0.02:
                    reasons.append('overhangs_book_below')
                checks['supported_by'] = b.get('id')
        if p['mode'] == 'lean':
            nb_index = p['leans_on']
            if nb_index not in accepted:
                reasons.append(f'lean_neighbour_lost {nb_index}')
            else:
                nb = placements[nb_index]
                nbl = _aabb([mat_vec(inv, tuple(c[k] - origin[k] for k in range(3))) for c in world_corners(nb)])
                top = min(local, key=lambda l: l[0])            # the corner that touches the neighbour
                gap = top[0] - nbl[1][0]
                checks['lean_contact'] = {'neighbour': nb.get('id'), 'gap_m': round(gap, 6),
                                          'contact_height_m': round(top[2], 4), 'neighbour_top_m': round(nbl[1][2], 4)}
                if not -1e-6 <= gap <= CONTACT_TOL or not 0 < top[2] <= nbl[1][2]:
                    reasons.append('lean_without_neighbour_contact')
        box = obb(p, COLLISION_SHRINK)
        wlo, whi = _aabb(corners)
        hit_idents = {}
        for rec in obstacles:
            if any(rec['aabb'][0][k] > whi[k] or rec['aabb'][1][k] < wlo[k] for k in range(3)):
                continue
            for tri in rec['tris']:
                if any(min(q[k] for q in tri) > whi[k] or max(q[k] for q in tri) < wlo[k] for k in range(3)):
                    continue
                if tri_hits_obb(tri, box):
                    hit_idents[rec['ident']] = hit_idents.get(rec['ident'], 0) + 1
        if hit_idents:
            reasons.append('collides:' + ','.join(sorted(hit_idents)))
        for j in accepted:
            if obb_overlap(box, obb(placements[j], COLLISION_SHRINK)):
                reasons.append(f'interpenetrates {placements[j]["id"]}')
        if p['mode'] == 'lean' and not reasons:
            checks['contacts'] = ['board', placements[p['leans_on']]['id']]
        p['checks'] = checks
        if reasons:
            rejected.append({'id': p['id'], 'source': p['source'], 'mode': p['mode'], 'reasons': reasons})
        else:
            accepted[i] = p
    return [accepted[i] for i in sorted(accepted)], rejected


# ---------------------------------------------------------------- 6. fingerprint, manifest, GLB checks
def fingerprint_rows(rows):
    return {name: hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest() for name, row in rows.items()}


def fingerprint_changes(before, after):
    changed = sorted(n for n in before if before[n] != after.get(n))
    return changed


def hide_manifest(found, shelf_objects, reference_pivots, glb_sha=None):
    """found = identify_original_books(...). Only nodes whose single component is one book are listed
    under `originals` (hide). Books inside a material-batched node go to `excisions` (triangle IDs +
    remainder spec); such a node is never listed for hiding."""
    separate, batched = found['separate'], found['batched']
    hide_names = {o['name'] for o in separate}
    if hide_names & {b_['node'] for b_ in batched}:
        raise RuntimeError('a batched node was listed for hiding')
    return {
        'schema': 'sub01.real-shelf-books.hide-manifest.v2',
        'source': 'web/house/home.js:361-368 books(); :856-860 office shelf rows; :2819-2833 house-static naming',
        'policy': 'separate book nodes: hide only (bHiddenInGame + editor hidden), never destroy, collision '
                  'unchanged; material-batched nodes: never hidden whole, excise the listed book triangles only',
        'expected_count': EXPECTED_ORIGINALS,
        'books_total': len(found['books']),
        'originals': [{'name': o['name'], 'bakeId': o['ident'], 'canonical': canonical(o['name']),
                       'canonical_ident': canonical(o['ident']),
                       'row': o['row'], 'index': o['index'], 'pivot_runtime_m': o['pivot_runtime']}
                      for o in separate],
        'excisions': batched,
        'shelf_objects': shelf_objects,
        'reference_pivots': reference_pivots,
        'additive_glb_sha256': glb_sha,
    }


def glb_texture_roles(doc):
    """{image name: role} from a parsed GLB: base_color (sRGB), normal, metallic_roughness, occlusion.
    Raises if a material is emissive or an image has two incompatible roles."""
    images = doc.get('images', [])
    textures = doc.get('textures', [])
    roles = {}

    def mark(info, role):
        if not info:
            return
        src = textures[info['index']].get('source')
        name = images[src].get('name') or images[src].get('uri') or f'image{src}'
        if roles.get(name, role) != role and {roles[name], role} != {'metallic_roughness', 'occlusion'}:
            raise RuntimeError(f'image {name} used as {roles[name]} and {role}')
        roles.setdefault(name, role)
    for m in doc.get('materials', []):
        if m.get('emissiveTexture') or any(m.get('emissiveFactor', [0, 0, 0])):
            raise RuntimeError(f'material {m.get("name")} is emissive')
        pbr = m.get('pbrMetallicRoughness', {})
        mark(pbr.get('baseColorTexture'), 'base_color')
        mark(m.get('normalTexture'), 'normal')
        mark(pbr.get('metallicRoughnessTexture'), 'metallic_roughness')
        mark(m.get('occlusionTexture'), 'occlusion')
    return roles


def verify_additive_glb(doc, expected_nodes):
    nodes = [n.get('name', '') for n in doc.get('nodes', [])]
    foreign = sorted(n for n in nodes if not n.startswith(NAME_PREFIX) or n not in set(expected_nodes))
    foreign_mats = sorted(m.get('name', '') for m in doc.get('materials', []) if not m.get('name', '').startswith(NAME_PREFIX))
    missing = sorted(set(expected_nodes) - set(nodes))
    if foreign or foreign_mats or missing:
        raise RuntimeError('additive GLB is not additive-only: ' + json.dumps(
            {'foreign_nodes': foreign, 'foreign_materials': foreign_mats, 'missing': missing}))
    return True


SOCKET_COLORSPACE = {'Base Color': 'sRGB', 'Color': None, 'Roughness': 'Non-Color', 'Metallic': 'Non-Color',
                     'Normal': 'Non-Color', 'Strength': 'Non-Color', 'Alpha': 'Non-Color', 'Fac': None}


def image_roles(material):
    """{image name: required colour space} by following each image node's links to the Principled
    BSDF (through Normal Map / Separate / Math nodes). Duck-typed: works on bpy and test fakes."""
    tree = getattr(material, 'node_tree', None)
    if tree is None:
        return {}
    outgoing = {}
    for link in tree.links:
        outgoing.setdefault(link.from_node.name, []).append(link)
    roles = {}

    def walk(node, seen):
        found = set()
        for link in outgoing.get(node.name, []):
            to = link.to_node
            sock = link.to_socket.name
            if to.bl_idname == 'ShaderNodeNormalMap':
                found.add('Non-Color')
            elif to.bl_idname == 'ShaderNodeBsdfPrincipled':
                if sock == 'Base Color':
                    found.add('sRGB')
                elif sock.startswith('Emission'):
                    found.add('EMISSIVE')
                else:
                    found.add('Non-Color')
            elif to.name not in seen:
                found |= walk(to, seen | {to.name})
        return found
    for node in tree.nodes:
        image = getattr(node, 'image', None)
        if node.bl_idname == 'ShaderNodeTexImage' and image is not None:
            found = walk(node, {node.name})
            if 'EMISSIVE' in found:
                raise RuntimeError(f'{material.name}: image {image.name} drives emission')
            if len(found) > 1:
                raise RuntimeError(f'{material.name}: image {image.name} feeds both colour and data inputs')
            if found:
                roles[image.name] = found.pop()
    return roles


# ---------------------------------------------------------------- Blender run
def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--books-asset', required=True, help='book_encyclopedia_set_01 .blend/.gltf/.glb on the server')
    ap.add_argument('--output-dir', default='out/real-books')
    ap.add_argument('--dry-run', action='store_true', help='measure, place and check; write the report but no GLB')
    ap.add_argument('--list-originals', action='store_true', help='read-only: list cube-book candidates and boards')
    ap.add_argument('--allow-unassembled', action='store_true')
    ap.add_argument('--source-sha256')
    ap.add_argument('--base-sha256')
    ap.add_argument('--base-bytes', type=int)
    ap.add_argument('--seed', type=int, default=DEFAULT_SEED)
    ap.add_argument('--spine-axis', default='-Y', choices=sorted(AXES),
                    help='direction the spines face in the asset file (verify on the asset preview)')
    ap.add_argument('--front-axis', default='-Y', choices=sorted(AXES),
                    help='room side of the shelf in Blender (home.js shelf at runtime z -3.72, room toward +z = Blender -Y)')
    ap.add_argument('--uniform-scale', type=float, default=1.0,
                    help='only if the asset is not in metres; uniform, recorded in the report')
    ap.add_argument('--top-clearance', type=float, default=0.40)
    return ap.parse_args(argv)


def _blender_argv():
    return sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def _evaluated_records(objects, depsgraph):
    rows, records = {}, []
    for obj in sorted(objects, key=lambda o: o.name):
        row, record = rd.evaluate_object(obj, depsgraph)
        rows[obj.name] = row
        if record:
            tris = [tuple(rd.runtime_to_blender(p) for p in tri) for tri in record['tris']]
            pts = [p for tri in tris for p in tri]
            records.append({'name': obj.name, 'ident': record['ident'], 'tris': tris, 'aabb': _aabb(pts),
                            'pivot': tuple(obj.matrix_world.translation)})
    return rows, records


def _in_region(aabb, region=SHELF_REGION, pad=0.0):
    return all(aabb[0][k] <= region[1][k] + pad and aabb[1][k] >= region[0][k] - pad for k in range(3))


def _load_asset(path, source_collection):
    path = Path(path)
    before = set(bpy.data.objects)
    if path.suffix.lower() in ('.gltf', '.glb'):
        bpy.ops.import_scene.gltf(filepath=str(path))
        new = [o for o in bpy.data.objects if o not in before]
        for o in new:
            for c in list(o.users_collection):
                c.objects.unlink(o)
            source_collection.objects.link(o)
    elif path.suffix.lower() == '.blend':
        with bpy.data.libraries.load(str(path), link=False) as (src, dst):
            dst.objects = list(src.objects)
        new = [o for o in dst.objects if o is not None]
        for o in new:
            source_collection.objects.link(o)
    else:
        raise RefusedError(f'unsupported asset type {path.suffix}')
    meshes = [o for o in new if o.type == 'MESH']
    if not meshes:
        raise RefusedError('asset contains no mesh objects')
    for o in new:
        o[TAG + 'Source'] = True
    bpy.context.view_layer.update()
    return new, meshes


def _measure_books(meshes, spine_axis, unit_scale, asset_path=None):
    from verified_encyclopedia_book_nodes import source_contract, verify_objects
    try:
        contract=source_contract(asset_path)
        complete=verify_objects(meshes,contract) if contract is not None else None
    except ValueError as error:
        raise RefusedError(str(error)) from error
    if complete is not None:
        # The pinned provider authored one whole cover+page mesh per book.
        # Retain every vertex/face/material/UV; seam islands are not book objects.
        books=[]
        for obj,proof in complete:
            points=[tuple(obj.matrix_world @ v.co) for v in obj.data.vertices]
            frame=book_frame(points,spine_axis)
            problem=check_book_dims(frame['dims'],unit_scale)
            if problem:raise RefusedError(obj.name+': '+problem)
            part={'obj':obj,'verts':list(range(len(points))),'points':points}
            books.append({'key':f'book{len(books)+1:02d}','parts':[part],'provider_full_geometry_proof':proof,**frame})
        return books,[]
    parts = []
    for obj in meshes:
        mw = obj.matrix_world
        verts = [tuple(mw @ v.co) for v in obj.data.vertices]
        for isl in islands(len(verts), [tuple(p.vertices) for p in obj.data.polygons]):
            parts.append({'obj': obj, 'verts': sorted(isl), 'points': [verts[i] for i in isl]})
    books, ignored = [], []
    for gi, group in enumerate(cluster_parts(parts)):
        pts = [p for i in group for p in parts[i]['points']]
        try:
            frame = book_frame(pts, spine_axis)
        except RefusedError as error:
            ignored.append({'group': gi, 'reason': str(error)})
            continue
        problem = check_book_dims(frame['dims'], unit_scale)
        if problem:
            ignored.append({'group': gi, 'reason': problem, 'dims': frame['dims']})
            continue
        books.append({'key': f'book{len(books) + 1:02d}', 'parts': [parts[i] for i in group], **frame})
    if len(books) < 3:
        raise RefusedError(json.dumps({'error': f'only {len(books)} measurable books in the asset', 'ignored': ignored}))
    return books, ignored


def _book_mesh(book, unit_scale, collection_tmp):
    """One mesh per real book, in the canonical frame (bottom centre at the origin), rigid +
    optional uniform scale only. Source vertices, UVs, normals and materials are kept."""
    import bmesh  # type: ignore
    from mathutils import Matrix  # type: ignore
    rot, origin = book['rot'], book['origin']
    canon = Matrix([list(r) + [-sum(r[k] * origin[k] for k in range(3))] for r in rot] + [[0, 0, 0, 1]])
    canon = Matrix.Scale(unit_scale, 4) @ canon
    temps = []
    for part in book['parts']:
        src = part['obj']
        me = src.data.copy()
        bm = bmesh.new()
        bm.from_mesh(me)
        keep = set(part['verts'])
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.index not in keep], context='VERTS')
        bm.to_mesh(me)
        bm.free()
        me.transform(canon @ src.matrix_world)
        tmp = bpy.data.objects.new(f'{NAME_PREFIX}tmp', me)
        collection_tmp.objects.link(tmp)
        temps.append(tmp)
    if len(temps) > 1:
        with bpy.context.temp_override(active_object=temps[0], selected_editable_objects=temps,
                                       selected_objects=temps):
            bpy.ops.object.join()
    mesh = temps[0].data
    mesh.name = f'{NAME_PREFIX}Mesh_{book["key"]}'
    bpy.data.objects.remove(temps[0])
    return mesh


def _own_materials(meshes, report):
    """Copy the scanned materials under our prefix; enforce colour spaces; refuse emission."""
    copies = {}
    for mesh in meshes:
        for i, mat in enumerate(mesh.materials):
            if mat is None:
                continue
            if mat.name not in copies:
                new = mat.copy()
                new.name = NAME_PREFIX + mat.name
                new[TAG] = True
                for node in getattr(new.node_tree, 'nodes', []):
                    if node.bl_idname == 'ShaderNodeBsdfPrincipled':
                        for sock in ('Emission Strength',):
                            if sock in node.inputs:
                                node.inputs[sock].default_value = 0.0
                roles = image_roles(new)
                for image_name, space in roles.items():
                    image = bpy.data.images[image_name]
                    if image.colorspace_settings.name != space:
                        image.colorspace_settings.name = space
                    if image.colorspace_settings.name != space:
                        raise RefusedError(f'{image_name} colour space cannot be set to {space}')
                report.setdefault('textures', {}).update(
                    {n: {'colorspace': s, 'filepath': bpy.data.images[n].filepath} for n, s in roles.items()})
                copies[mat.name] = new
            mesh.materials[i] = copies[mat.name]
    return list(copies.values())


def _export(scene, collection, glb, names):
    view_layer = bpy.context.view_layer

    def find(layer):
        if layer.collection == collection:
            return layer
        for child in layer.children:
            hit = find(child)
            if hit:
                return hit
        return None
    previous = view_layer.active_layer_collection
    selected = {o.name for o in scene.objects if o.select_get()}
    active = view_layer.objects.active
    try:
        view_layer.active_layer_collection = find(view_layer.layer_collection)
        for obj in scene.objects:
            obj.select_set(obj.name in names)
        bpy.ops.export_scene.gltf(filepath=str(glb.resolve()), export_format='GLB', use_selection=True,
                                  use_active_collection=True, use_active_collection_with_nested=True,
                                  use_visible=False, export_yup=True, export_extras=True, export_apply=True,
                                  export_lights=False, export_cameras=False, export_image_format='AUTO')
    finally:
        view_layer.active_layer_collection = previous
        for obj in scene.objects:
            obj.select_set(obj.name in selected)
        view_layer.objects.active = active
    doc = glb_json(glb)
    try:
        verify_additive_glb(doc, names)
        roles = glb_texture_roles(doc)
    except Exception:
        glb.unlink(missing_ok=True)
        raise
    return {'path': str(glb), 'sha256': sha256_file(glb), 'objects': sorted(names),
            'texture_roles': roles, 'verified_additive_only': True}


def run(argv=None):
    from mathutils import Matrix  # type: ignore
    args = parse_args(_blender_argv() if argv is None else argv)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    blend_path = bpy.data.filepath
    mesh_objects = [o for o in scene.objects if o.type == 'MESH']
    stats = (len(mesh_objects), sum(len(o.data.vertices) for o in mesh_objects))
    base = verify_base(scene, blend_path, args.allow_unassembled, stats, args.source_sha256,
                          args.base_sha256, args.base_bytes)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    existing = list(scene.objects)
    rows_before, records = _evaluated_records(existing, depsgraph)
    before = fingerprint_rows(rows_before)

    found = identify_original_books(records)
    originals = found['books']
    hidden_names = {o['name'] for o in found['separate']}
    excised = {x['node']: set(x['excise']['triangle_ids']) for x in found['batched']}
    nearby = []
    for r in records:                       # obstacles: everything except the cube-book triangles
        if r['name'] in hidden_names or not _in_region(r['aabb'], pad=0.05):
            continue
        if r['name'] in excised:
            tris = [t for i, t in enumerate(r['tris']) if i not in excised[r['name']]]
            r = dict(r, tris=tris, aabb=_aabb([p for t in tris for p in t]) if tris else r['aabb'])
        nearby.append(r)
    shelf_records = [r for r in nearby if r['ident'].startswith('house-office-shelves-')] or \
        [r for r in nearby if (r['aabb'][1][0] - r['aabb'][0][0]) > 2.0]
    if not shelf_records:
        raise RefusedError('no shelf object (house-office-shelves-* or a >2 m board) in the shelf region')
    support_tris = [t for r in shelf_records for t in r['tris']]
    boards = detect_boards(support_tris)
    report = {'schema': 'sub01.real-shelf-books.v1', 'mode': 'list' if args.list_originals else
              ('dry-run' if args.dry_run else 'blender'), 'basis': 'evaluated-geometry', 'base': base,
              'base_blend': blend_path,
              'originals': [{k: v for k, v in o.items() if k != 'triangle_ids'} for o in originals],
              'originals_separate': len(found['separate']), 'originals_batched_nodes': [x['node'] for x in found['batched']],
              'shelf_objects': [{'name': r['name'], 'ident': r['ident'], 'canonical': canonical(r['name']),
                                 'canonical_ident': canonical(r['ident']),
                                 'pivot_runtime_m': list(rd.blender_to_runtime(r['pivot']))} for r in shelf_records],
              'boards': boards}
    if args.list_originals:
        _emit(report, out, 'real-shelf-books-identifiers.json')
        (out / 'original-hide-manifest.preview.json').write_text(json.dumps(
            hide_manifest(found, report['shelf_objects'], []), indent=2) + '\n')
        return report

    hosts = []
    for row in range(len(ORIGINAL_BOTTOMS)):
        row_books = [o for o in originals if o['row'] == row]
        bottom = min(o['aabb_blender'][0][2] for o in row_books)
        board = min(boards, key=lambda b: abs(b['z'] - bottom))
        if not -0.001 <= bottom - board['z'] <= 0.01:
            raise RefusedError(f'row {row}: no evaluated board under the cube books (bottom {bottom:.4f})')
        frame = board_frame(board, args.front_axis)
        origin, brot, u_len, v_len = frame
        inv = transpose(brot)
        us = [mat_vec(inv, tuple(c[k] - origin[k] for k in range(3)))[0]
              for o in row_books for c in (o['aabb_blender'][0], o['aabb_blender'][1])]
        u_range = (max(0.0, min(us) - 0.02), min(u_len, max(us) + 0.10))
        hosts.append({'board': board, 'frame': frame, 'u_range': u_range, 'top_clearance': args.top_clearance})

    provenance = {'asset': ASSET_NAME, 'url': ASSET_URL, 'license': ASSET_LICENSE,
                  'file': str(Path(args.books_asset).resolve()), 'sha256': sha256_file(args.books_asset),
                  'uniform_scale': args.uniform_scale, 'spine_axis_in_asset': args.spine_axis}
    source_col = bpy.data.collections.new(SOURCE_COLLECTION)
    scene.collection.children.link(source_col)
    collection = bpy.data.collections.new(COLLECTION)
    scene.collection.children.link(collection)
    new_objects, meshes = _load_asset(args.books_asset, source_col)
    books, ignored = _measure_books(meshes, args.spine_axis, args.uniform_scale, args.books_asset)
    dims = {b['key']: tuple(x * args.uniform_scale for x in b['dims']) for b in books}
    placements = plan_layout(hosts, dims, args.seed)
    obstacles = nearby
    accepted, rejected = validate_placements(placements, obstacles, hosts, support_tris)
    if len(accepted) < 12:
        raise RefusedError(json.dumps({'error': f'only {len(accepted)} books passed the checks', 'rejected': rejected}))

    book_meshes = {b['key']: _book_mesh(b, args.uniform_scale, source_col) for b in books
                   if any(p['source'] == b['key'] for p in accepted)}
    from verified_encyclopedia_book_nodes import verify_mesh
    for book in books:
        proof=book.get('provider_full_geometry_proof')
        if proof and book['key'] in book_meshes:
            mesh=book_meshes[book['key']]
            try:counts=verify_mesh(mesh,proof)
            except ValueError as error:raise RefusedError(str(error)) from error
            proof.update(output_vertex_count=len(mesh.vertices),output_triangles_per_slot=counts,full_cover_page_geometry_preserved=True)
    _own_materials(book_meshes.values(), report)
    for mesh in book_meshes.values():
        mesh[TAG] = True
    names = []
    for p in accepted:
        obj = bpy.data.objects.new(p['id'], book_meshes[p['source']])
        collection.objects.link(obj)
        obj.matrix_world = Matrix(p['world'])
        obj[TAG] = True
        obj['sub01Source'] = f'{ASSET_NAME}:{p["source"]}'
        names.append(obj.name)
    for o in list(source_col.objects):
        bpy.data.objects.remove(o)
    bpy.data.collections.remove(source_col)
    bpy.context.view_layer.update()

    depsgraph = bpy.context.evaluated_depsgraph_get()
    after_rows, _ = _evaluated_records([o for o in scene.objects if o.name in before], depsgraph)
    changed = fingerprint_changes(before, fingerprint_rows(after_rows))
    stray = sorted(o.name for o in scene.objects if o.name not in before and not o.get(TAG))
    if changed or stray or sorted(o.name for o in collection.all_objects) != sorted(names):
        raise RuntimeError(json.dumps({'error': 'existing objects changed', 'changed': changed, 'stray': stray}))

    reference_pivots = [{'name': r['name'], 'ident': r['ident'], 'canonical': canonical(r['name']),
                         'canonical_ident': canonical(r['ident']),
                         'pivot_runtime_m': list(rd.blender_to_runtime(r['pivot']))}
                        for r in records if r['ident'].startswith(REFERENCE_PIVOT_PREFIXES)]
    report.update({
        'provenance': provenance, 'seed': args.seed, 'front_axis': args.front_axis,
        'asset_books': [{'key': b['key'], 'dims_m': [round(x * args.uniform_scale, 5) for x in b['dims']],
                         'asset_tilt_deg': b['asset_tilt_deg'],
                         'provider_full_geometry_proof': b.get('provider_full_geometry_proof')} for b in books],
        'asset_ignored_parts': ignored,
        'hosts': [{'board_z': h['board']['z'], 'u_range': h['u_range'], 'clearance': h['board']['clearance']} for h in hosts],
        'built': [{'id': p['id'], 'source_mesh': book_meshes[p['source']].name, 'source_book': p['source'],
                   'mode': p['mode'], 'lean_deg': p['lean_deg'], 'dims_m': [round(x, 5) for x in p['dims']],
                   'matrix_world_blender': p['world'],
                   'pivot_runtime_m': list(rd.blender_to_runtime(tuple(p['world'][i][3] for i in range(3)))),
                   'scale': [args.uniform_scale] * 3, 'support': p['rests_on'] if p['rests_on'] == 'board'
                   else placements[p['rests_on']]['id'], 'checks': p['checks']} for p in accepted],
        'rejected': rejected,
        'existing_objects_verified_unchanged': len(before),
        'collision': 'new books carry no collision; originals keep theirs (hidden only)',
    })
    if not args.dry_run:
        glb = out / 'real-shelf-books.glb'
        report['additive_glb'] = _export(scene, collection, glb, names)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        after_rows, _ = _evaluated_records([o for o in scene.objects if o.name in before], depsgraph)
        if fingerprint_changes(before, fingerprint_rows(after_rows)):
            glb.unlink(missing_ok=True)
            raise RuntimeError('existing objects changed during export')
    manifest = hide_manifest(found, report['shelf_objects'], reference_pivots,
                             (report.get('additive_glb') or {}).get('sha256'))
    (out / 'original-hide-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    _emit(report, out)
    return report


def _emit(report, out, filename='real-shelf-books.json'):
    (Path(out) / filename).write_text(json.dumps(report, indent=2, default=list) + '\n')
    print('SUB01_REAL_SHELF_BOOKS ' + json.dumps({'file': str(Path(out) / filename), 'mode': report['mode'],
                                                   'built': len(report.get('built', [])),
                                                   'rejected': len(report.get('rejected', []))}), flush=True)


if __name__ == '__main__' and bpy is not None:
    try:
        run()
    except Exception as error:  # fail closed with a readable reason and a non-zero exit
        print('SUB01_REAL_SHELF_BOOKS_REFUSED ' + str(error), flush=True)
        sys.exit(1)
