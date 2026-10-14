"""Real lamp replacement builder: real CC0 Poly Haven lamp models for the actual home.

Wording: desk_lamp_arm_01, modern_ceiling_lamp_01 and industrial_pipe_lamp are MODELED Poly
Haven assets (CC0); none is documented here as scanned or photographed.

Server-only (Blender 4.5.3, run by root/the renderer; never on the owner's Mac):

  /workspace/sub01-tools/blender-4.5.3-linux-x64/blender --background --factory-startup \
    --python tools/build_real_lamps.py -- \
    --source-glb out/lighting-v23/unreal-home-lab/Sub01HomeLab/SourceAssets/full-home.glb \
    --source-sha 9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b \
    --ceiling-lamp out/furniture-refresh/<...>/modern_ceiling_lamp_01_1k.gltf \
    --desk-lamp web/house/assets/desk_lamp_arm_01/desk_lamp_arm_01.gltf \
    --bedside-lamp /workspace/sub01-home-private/reviewed-furniture/industrial_pipe_lamp \
    [--rail-excision <root rail builder triangle-ID manifest.json>] \
    --output-dir out/real-lamps [--dry-run]

A base .blend may be passed instead of --factory-startup ONLY if it is the plain
glTF import of the same full-home.glb (every GLB mesh node must match one Blender
object by evaluated world bounds); the GLB is always required because it is the
exact source Unreal imported (actor ``full-home_node_<index>``).

What it does (fail closed; nothing pre-existing is modified, saved or deleted):
* identifies the procedural lamp geometry to retire from the GLB by exact home.js
  signatures (file:line cited in ORIGINAL_SIGNATURES). Standalone nodes are HIDDEN via
  the manifest (never destroyed: emitter nodes 126/127/129/198/199 keep the native
  fixture guards valid). Parts merged into SHARED batches (e.g. the white desk-lamp
  stem inside the rail-metal batch node 163 / Material 8) are selected by EXACT
  connected components (cylinder endpoints + radius) and emitted as triangle IDs,
  unioned with root's rail excision into ONE remainder spec; a shared batch is never
  hidden as a whole;
* relocates the single existing red ``desk_lamp_arm_01`` (home.js:625, matched by
  its exact material names) to the left of the desk, and replaces the procedural
  bedside lamp (tools/build_home_bedside_lamp.py) with industrial_pipe_lamp;
* measures supports from depsgraph-evaluated geometry with BVH ray casts: the
  desk top under the left lamp, the ceiling underside above each pendant;
* places the real lamps at real size (uniform scale 1.0), checks support edges,
  intersections and clearances against every other evaluated mesh;
* zeroes every imported emissive (no uncontrolled glow; the emission-toggle owner
  hooks the documented slot names);
* exports ONLY the new collection: real-lamps.glb (world placed, additive),
  one local-frame GLB per role for Unreal, placement-report.json,
  original-hide-manifest.json and provenance.json.

The pure section below has no bpy dependency and is unit tested
(tests/test_real_lamps.py).
"""
import argparse
import hashlib
import json
import math
import re
import struct
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# Constants and citations
# --------------------------------------------------------------------------
SCHEMA = 'sub01.real-lamps.v1'
COLLECTION = 'SUB01_RealLamps'
ACTOR_PREFIX = 'SUB01_RealLamp_'
REVIEWED_SOURCE_SHA = '9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
ACQUISITION = 'modeled Poly Haven CC0 asset (not documented as scanned or photographed)'
POLYHAVEN = {
    'modern_ceiling_lamp_01': {'url': 'https://polyhaven.com/a/modern_ceiling_lamp_01',
                               'api': 'https://api.polyhaven.com/files/modern_ceiling_lamp_01',
                               'licence': 'CC0 1.0', 'author': 'James Ray Cock', 'acquisition': ACQUISITION,
                               'real_dimensions_mm': [431.65, 431.66, 951.55]},
    'desk_lamp_arm_01': {'url': 'https://polyhaven.com/a/desk_lamp_arm_01',
                         'api': 'https://api.polyhaven.com/files/desk_lamp_arm_01',
                         'licence': 'CC0 1.0', 'acquisition': ACQUISITION},
    'industrial_pipe_lamp': {'url': 'https://polyhaven.com/a/industrial_pipe_lamp',
                             'api': 'https://api.polyhaven.com/files/industrial_pipe_lamp',
                             'licence': 'CC0 1.0', 'acquisition': ACQUISITION,
                             'real_dimensions_cm': [18.3, 36.4, 26.2]},
}
# Authored light table: tools/unreal_home_lights.py:17-21 (authored_lights) and
# web/house/home.js:1132-1133 (warm PointLight at 1.1,1.35,-3.15), home.js:1146-1158 (pendants).
LIGHT_SOURCE = {
    'DeskLamp': (1.1, 1.35, -3.15),
    'LowerPendant': (-2.0, 2.43, 0.5),
    'UpperPendant': (2.0, 4.98, -0.2),
    'BedLamp': (-3.55, 3.768, -3.1),  # unreal_home_lights.py:18, home.js:1135
}
ROLE_LIGHT = {'DeskLamp': 'SUB01_AuthoredLight_DeskLamp',
              'LowerPendant': 'SUB01_AuthoredLight_LowerPendant',
              'UpperPendant': 'SUB01_AuthoredLight_UpperPendant',
              'BedLamp': 'SUB01_AuthoredLight_BedLamp'}
# Reviewed source fixture emitters (tools/unreal_fixture_emission_audit.py:24-31).
FIXTURE_EMITTERS = {66: 'KitchenWork', 126: 'DeskLamp', 127: 'LowerPendant',
                    129: 'UpperPendant', 198: 'BedLamp', 199: 'BedLamp'}
NEVER_HIDE_NODES = {66}  # kitchen work strip is not a replaced lamp
BEDSIDE_PARTS = {'Brass_base': None, 'Brass_socket': None, 'Brass_stem': None, 'Bulb': 198, 'Linen_shade': 199}
# Old procedural bedside lamp: tools/build_home_bedside_lamp.py, placed by web/house/home.js:1117-1131
BEDSIDE_OLD_REGION = {'x': (-3.85, -3.25), 'z': (-3.4, -2.8), 'y': (3.3, 4.1)}
BEDSIDE_YAW_DEG = 0.0
SCREEN_PATTERN = re.compile(r'screen|monitor|display|lcd|tv|television|phone|keyboard|keycap|pc_|tower|'
                            r'computer|laptop|tablet', re.I)
DESK_LAMP_MATERIALS = ('desk_lamp_arm_01', 'desk_lamp_arm_01_light')
# Old red-lamp placement: web/house/home.js:625 furnished("desk_lamp_arm_01", 2.65, 0.863, -3.18, 0.24, -0.7)
RED_LAMP_OLD_REGION = {'x': (1.9, 3.3), 'z': (-3.6, -2.7), 'y': (0.80, 2.2)}
DESK_YAW_DEG = 180.0  # shade leans over the desk toward the seated user (+Z); arm toward the wall

AABB_TOL = 0.004


def _cyl(r, h, x, y, z, seg=24):
    # three.js CylinderGeometry(rad, rad, h, seg): vertical axis through (x, z), y in [y-h/2, y+h/2]
    return {'x': x, 'z': z, 'r': r, 'y0': y - h / 2, 'y1': y + h / 2, 'seg': seg}


def _beam(x, z, y0, y1, r, seg=10):
    # home.js beam(a, b, r): CylinderGeometry(r, r, |b-a|, 10) between the endpoints
    return {'x': x, 'z': z, 'r': r, 'y0': y0, 'y1': y1, 'seg': seg}


def cyl_aabb(c):
    sx = max(abs(math.sin(2 * math.pi * k / c['seg'])) for k in range(c['seg'])) * c['r']
    return ((c['x'] - sx, c['y0'], c['z'] - c['r']), (c['x'] + sx, c['y1'], c['z'] + c['r']))


# role -> part -> (cylinder, citation, fixture emitter node or None)
ORIGINAL_SIGNATURES = {
    'DeskLamp': {
        'white_glow_disc': (_cyl(.14, .035, 1.1, 1.3, -3.15), 'web/house/home.js:1113', 126),
        # endpoints [1.1,.85,-3.15] -> [1.1,1.3,-3.15], r .014; batched with rail metal (node 163 / Material 8)
        'white_lamp_stem': (_beam(1.1, -3.15, .85, 1.3, .014), 'web/house/home.js:1114', None),
    },
    'LowerPendant': {
        'white_body': (_cyl(.23, .15, -2, 2.55, .5), 'web/house/home.js:1150', None),
        'black_cable': (_beam(-2, .5, 2.65, 6, .006), 'web/house/home.js:1151', None),
        'glow_disc': (_cyl(.18, .013, -2, 2.55 - .077, .5), 'web/house/home.js:1152', 127),
    },
    'UpperPendant': {
        'white_body': (_cyl(.23, .15, 2, 5.1, -.2), 'web/house/home.js:1150', None),
        'black_cable': (_beam(2, -.2, 5.2, 6, .006), 'web/house/home.js:1151', None),
        'glow_disc': (_cyl(.18, .013, 2, 5.1 - .077, -.2), 'web/house/home.js:1152', 129),
    },
}
ROLES = ('DeskLamp', 'LowerPendant', 'UpperPendant', 'BedLamp')


# --------------------------------------------------------------------------
# Coordinates
# --------------------------------------------------------------------------
def source_to_blender(p):
    """glTF/three.js home metres (Y up) -> Blender world after glTF import (Z up)."""
    x, y, z = p
    return (x, -z, y)


def blender_to_source(p):
    x, y, z = p
    return (x, z, -y)


def source_to_ue_cm(p):
    """Contract used by extract_keyboard_keycaps.py/fit_seat_pose_trial.py: (x, z, y) * 100.

    Unreal still re-verifies the actual import transform from anchors
    (tools/unreal_home_coordinates.infer_import_transform)."""
    x, y, z = p
    return (x * 100.0, z * 100.0, y * 100.0)


def rotate_y(p, yaw_deg):
    """Rotate a source-frame point about +Y (three.js object.rotation.y)."""
    t = math.radians(yaw_deg)
    x, y, z = p
    return (x * math.cos(t) + z * math.sin(t), y, -x * math.sin(t) + z * math.cos(t))


def ue_yaw_from_source(yaw_deg, axes=(0, 2, 1), signs=(1, 1, 1)):
    """Conjugate a source yaw by the verified axis mapping into an Unreal yaw (deg)."""
    def m(v):
        return tuple(signs[i] * v[axes[i]] for i in range(3))
    a = m((1.0, 0.0, 0.0))
    b = m(rotate_y((1.0, 0.0, 0.0), yaw_deg))
    psi = math.degrees(math.atan2(b[1], b[0]) - math.atan2(a[1], a[0]))
    return (psi + 180.0) % 360.0 - 180.0


# --------------------------------------------------------------------------
# glTF/GLB reading (pure python)
# --------------------------------------------------------------------------
def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def load_gltf(path):
    path = Path(path)
    raw = path.read_bytes()
    if raw[:4] == b'glTF':
        if struct.unpack_from('<I', raw, 4)[0] != 2 or struct.unpack_from('<I', raw, 8)[0] != len(raw):
            raise ValueError(f'{path}: not a complete GLB v2')
        length, kind = struct.unpack_from('<II', raw, 12)
        if kind != 0x4E4F534A:
            raise ValueError(f'{path}: GLB first chunk is not JSON')
        doc = json.loads(raw[20:20 + length])
        offset = 20 + length
        bin_chunk = b''
        if offset < len(raw):
            blen, bkind = struct.unpack_from('<II', raw, offset)
            bin_chunk = raw[offset + 8:offset + 8 + blen]
        buffers = [bin_chunk]
    else:
        doc = json.loads(raw)
        buffers = []
        for b in doc.get('buffers', []):
            uri = b.get('uri')
            if not uri or uri.startswith('data:') or '..' in Path(uri).parts:
                raise ValueError(f'{path}: unsupported buffer uri {uri!r}')
            buffers.append((path.parent / uri).read_bytes())
    return doc, buffers


def accessor_vec3(doc, buffers, index):
    a = doc['accessors'][index]
    if a.get('componentType') != 5126 or a.get('type') != 'VEC3' or a.get('sparse'):
        raise ValueError('POSITION accessor must be dense float VEC3')
    view = doc['bufferViews'][a['bufferView']]
    data = buffers[view.get('buffer', 0)]
    stride = view.get('byteStride') or 12
    base = view.get('byteOffset', 0) + a.get('byteOffset', 0)
    return [struct.unpack_from('<3f', data, base + i * stride) for i in range(a['count'])]


def primitive_vertices(path):
    """[(material_name, emissive, [(x,y,z), ...]), ...] in the asset's own glTF frame."""
    doc, buffers = load_gltf(path)
    out = []
    for n in doc.get('nodes', []):
        if n.get('scale') not in (None, [1, 1, 1]) or 'matrix' in n:
            raise ValueError(f'{path}: asset node carries a scale/matrix; real size cannot be guaranteed')
    for n in doc.get('nodes', []):
        if 'mesh' not in n:
            continue
        m = _mul([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], node_local_matrix(n))
        mesh = doc['meshes'][n['mesh']]
        for prim in mesh['primitives']:
            mat = doc['materials'][prim['material']] if 'material' in prim else {}
            names = ' '.join(str(v) for v in (n.get('name'), mesh.get('name'), mat.get('name')) if v).lower()
            emissive = (any(c > 0 for c in mat.get('emissiveFactor', [0, 0, 0])) or 'emissiveTexture' in mat
                        or 'bulb' in names)
            out.append((mat.get('name'), emissive,
                        [_apply(m, v) for v in accessor_vec3(doc, buffers, prim['attributes']['POSITION'])]))
    return out


def resolve_asset(path):
    """A .gltf/.glb file, or a reviewed directory holding exactly one of them."""
    path = Path(path)
    if path.is_dir():
        found = sorted(list(path.glob('*.gltf')) + list(path.glob('*.glb')))
        if len(found) != 1:
            raise ValueError(f'{path}: expected exactly one .gltf/.glb, found {[f.name for f in found]}')
        return found[0]
    return path


def bounds(points):
    xs, ys, zs = zip(*points)
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _quat_matrix(q):
    x, y, z, w = q
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]


def node_local_matrix(node):
    if 'matrix' in node:
        m = node['matrix']
        return [[m[0], m[4], m[8], m[12]], [m[1], m[5], m[9], m[13]], [m[2], m[6], m[10], m[14]], [0, 0, 0, 1]]
    t = node.get('translation', [0, 0, 0])
    r = _quat_matrix(node.get('rotation', [0, 0, 0, 1]))
    s = node.get('scale', [1, 1, 1])
    return [[r[i][0] * s[0], r[i][1] * s[1], r[i][2] * s[2], t[i]] for i in range(3)] + [[0, 0, 0, 1]]


def _mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _apply(m, p):
    return tuple(m[i][0] * p[0] + m[i][1] * p[1] + m[i][2] * p[2] + m[i][3] for i in range(3))


def glb_mesh_nodes(doc, buffers=None):
    """Every mesh node: index, name, materials, world translation, world AABB (source metres)."""
    parents = {}
    for i, n in enumerate(doc.get('nodes', [])):
        for c in n.get('children', []):
            parents[c] = i
    rows = []
    for i, n in enumerate(doc.get('nodes', [])):
        if 'mesh' not in n:
            continue
        chain, j = [], i
        while j is not None:
            chain.append(j)
            j = parents.get(j)
        m = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
        for j in reversed(chain):
            m = _mul(m, node_local_matrix(doc['nodes'][j]))
        corners = []
        mats = []
        for prim in doc['meshes'][n['mesh']]['primitives']:
            a = doc['accessors'][prim['attributes']['POSITION']]
            if buffers is not None:
                # A rotated local AABB is conservative, not the evaluated mesh
                # bounds. Exact vertices are required to match detailed lamps.
                corners.extend(_apply(m, p) for p in accessor_vec3(doc, buffers, prim['attributes']['POSITION']))
            else:
                lo, hi = a['min'], a['max']
                for cx in (lo[0], hi[0]):
                    for cy in (lo[1], hi[1]):
                        for cz in (lo[2], hi[2]):
                            corners.append(_apply(m, (cx, cy, cz)))
            if 'material' in prim:
                mats.append(doc['materials'][prim['material']].get('name'))
        rows.append({'index': i, 'name': n.get('name'), 'materials': mats,
                     'translation': list(_apply(m, (0, 0, 0))), 'aabb': [list(v) for v in bounds(corners)]})
    return rows


def aabb_match(a, b, tol=AABB_TOL):
    return all(abs(a[k][i] - b[k][i]) <= tol for k in range(2) for i in range(3))


def aabb_contains(outer, inner, tol=AABB_TOL):
    return all(outer[0][i] <= inner[0][i] + tol and outer[1][i] >= inner[1][i] - tol for i in range(3))


# --------------------------------------------------------------------------
# Identification, exact component excision and hide manifest
# --------------------------------------------------------------------------
class RefuseError(RuntimeError):
    pass


def bake_id(name):
    return name if isinstance(name, str) and name.startswith('house-') else None


def primitive_components(doc, buffers, node_index):
    """Welded connected components of every primitive of one node (world source metres).

    Triangle ID = index of the triangle inside its primitive (indices // 3), the format
    of the excision manifests. Vertices sharing an exact position are welded."""
    node = doc['nodes'][node_index]
    parents = {c: i for i, n in enumerate(doc['nodes']) for c in n.get('children', [])}
    chain, j = [], node_index
    while j is not None:
        chain.append(j)
        j = parents.get(j)
    m = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    for j in reversed(chain):
        m = _mul(m, node_local_matrix(doc['nodes'][j]))
    out = []
    for p, prim in enumerate(doc['meshes'][node['mesh']]['primitives']):
        verts = [_apply(m, v) for v in accessor_vec3(doc, buffers, prim['attributes']['POSITION'])]
        if 'indices' in prim:
            a = doc['accessors'][prim['indices']]
            view = doc['bufferViews'][a['bufferView']]
            fmt = {5121: 'B', 5123: 'H', 5125: 'I'}[a['componentType']]
            size = struct.calcsize(fmt)
            base = view.get('byteOffset', 0) + a.get('byteOffset', 0)
            data = buffers[view.get('buffer', 0)]
            idx = [struct.unpack_from('<' + fmt, data, base + i * size)[0] for i in range(a['count'])]
        else:
            idx = list(range(len(verts)))
        parent = list(range(len(verts)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        weld = {}
        for i, v in enumerate(verts):
            key = tuple(round(c, 6) for c in v)
            if key in weld:
                parent[find(i)] = find(weld[key])
            else:
                weld[key] = i
        for t in range(len(idx) // 3):
            a0, a1, a2 = idx[3 * t:3 * t + 3]
            parent[find(a1)] = find(a0)
            parent[find(a2)] = find(a0)
        comps = {}
        for t in range(len(idx) // 3):
            comps.setdefault(find(idx[3 * t]), []).append(t)
        for tris in comps.values():
            vs = {i for t in tris for i in idx[3 * t:3 * t + 3]}
            out.append({'node': node_index, 'primitive': p, 'triangle_ids': sorted(tris),
                        'vertices': [verts[i] for i in vs]})
    return out


def fits_cylinder(points, c, tol=0.0015):
    for x, y, z in points:
        if math.hypot(x - c['x'], z - c['z']) > c['r'] + tol or not (c['y0'] - tol <= y <= c['y1'] + tol):
            return False
    return True


def select_cylinder_components(cyl, candidates, tol=0.0015):
    """EXACT component set for one cylinder: every selected component lies inside the cylinder and
    their union spans its full endpoints and radius. Refuses on no match or several candidate sets."""
    sets = {}
    for comp in candidates:
        if fits_cylinder(comp['vertices'], cyl, tol):
            sets.setdefault((comp['node'], comp['primitive']), []).append(comp)
    good = []
    for key, comps in sets.items():
        lo, hi = bounds([v for c in comps for v in c['vertices']])
        want = cyl_aabb(cyl)
        if aabb_match((lo, hi), want, tol + 0.0005):
            good.append((key, comps))
    if not good:
        raise RefuseError(f'no exact connected-component match for cylinder {cyl}')
    if len(good) > 1:
        raise RefuseError(f'ambiguous: {len(good)} candidate component sets match cylinder {cyl}')
    (node, prim), comps = good[0]
    return {'node': node, 'primitive': prim, 'component_count': len(comps),
            'triangle_ids': sorted(t for c in comps for t in c['triangle_ids']),
            'aabb_m': [list(v) for v in bounds([v for c in comps for v in c['vertices']])]}


def identify_originals(nodes, components_of=None):
    """Each signature part -> one standalone node (hidden) or an exact component set in a
    shared batch (excised). Emitters must be standalone (hidden, never excised)."""
    parts = {}
    for role, sigs in ORIGINAL_SIGNATURES.items():
        parts[role] = {}
        for part, (cyl, cite, emitter) in sigs.items():
            aabb = cyl_aabb(cyl)
            hits = [n for n in nodes if aabb_match(n['aabb'], aabb)]
            if len(hits) > 1:
                raise RefuseError(f'{role}.{part}: {len(hits)} nodes match the exact signature ({cite})')
            if hits:
                n = hits[0]
                if emitter is not None and n['index'] != emitter:
                    raise RefuseError(f'{role}.{part}: matched node {n["index"]}, reviewed fixture emitter is {emitter}')
                parts[role][part] = {'status': 'standalone', 'node': n, 'citation': cite, 'emitter': emitter}
                continue
            if emitter is not None:
                raise RefuseError(f'{role}.{part}: reviewed emitter node {emitter} is not a standalone node ({cite}); '
                                  'emitters are hidden, never excised')
            if components_of is None:
                raise RefuseError(f'{role}.{part}: merged into a shared batch and no component reader given')
            holders = [n for n in nodes if aabb_contains(n['aabb'], aabb)]
            candidates = [c for n in holders for c in components_of(n['index'])]
            sel = select_cylinder_components(cyl, candidates)
            sel.update(role=role, part=part, citation=cite)
            parts[role][part] = {'status': 'excise-components', 'selection': sel, 'citation': cite, 'emitter': None}
    return parts


def identify_red_lamp(nodes):
    """The single existing real red desk_lamp_arm_01 instance (home.js:625) by exact material names."""
    hits = [n for n in nodes if n['materials'] and all(m in DESK_LAMP_MATERIALS for m in n['materials'])]
    if not hits:
        raise RefuseError('Existing red desk_lamp_arm_01 instance not found (materials desk_lamp_arm_01*)')
    for n in hits:
        c = [(n['aabb'][0][i] + n['aabb'][1][i]) / 2 for i in range(3)]
        r = RED_LAMP_OLD_REGION
        if not (r['x'][0] <= c[0] <= r['x'][1] and r['y'][0] <= c[1] <= r['y'][1] and r['z'][0] <= c[2] <= r['z'][1]):
            raise RefuseError(f'red lamp node {n["index"]} is not at the old right-hand desk position: second instance?')
    if 'desk_lamp_arm_01' not in {m for n in hits for m in n['materials']}:
        raise RefuseError('red lamp body material missing')
    return hits


def identify_bedside(nodes):
    """Old procedural bedside lamp nodes (build_home_bedside_lamp.py names), exactly one each."""
    found = {}
    r = BEDSIDE_OLD_REGION
    for name, emitter in BEDSIDE_PARTS.items():
        hits = []
        for n in nodes:
            if n.get('name') != name:
                continue
            c = [(n['aabb'][0][i] + n['aabb'][1][i]) / 2 for i in range(3)]
            if r['x'][0] <= c[0] <= r['x'][1] and r['y'][0] <= c[1] <= r['y'][1] and r['z'][0] <= c[2] <= r['z'][1]:
                hits.append(n)
        if len(hits) != 1:
            raise RefuseError(f'bedside part {name}: {len(hits)} nodes at the old bedside position')
        if emitter is not None and hits[0]['index'] != emitter:
            raise RefuseError(f'bedside part {name}: node {hits[0]["index"]}, reviewed emitter is {emitter}')
        found[name] = hits[0]
    return found


def _protect(node):
    if node['index'] in NEVER_HIDE_NODES:
        raise RefuseError(f'node {node["index"]} ({FIXTURE_EMITTERS[node["index"]]}) is not a replaced lamp')
    for text in [node.get('name') or ''] + list(node['materials']):
        if SCREEN_PATTERN.search(text or '') and not str(text).startswith('desk_lamp_arm_01'):
            raise RefuseError(f'protected screen/device identity in hide target {node["index"]}: {text}')


def build_hide_manifest(parts, red_nodes, roles, bedside_nodes=None):
    entries, excisions = [], []

    def add(role, part, node, cite, emitter):
        _protect(node)
        entries.append({'role': role, 'part': part, 'source_node_index': node['index'],
                        'source_node_name': node.get('name'), 'bake_id': bake_id(node.get('name')),
                        'ue_actor_name': f'full-home_node_{node["index"]}',
                        'source_translation_m': node['translation'], 'source_aabb_m': node['aabb'],
                        'materials': node['materials'], 'fixture_emitter_lamp': FIXTURE_EMITTERS.get(node['index']),
                        'citation': cite, 'action': 'hide-not-destroy'})
    for role in roles:
        for part, info in parts.get(role, {}).items():
            if info['status'] == 'standalone':
                add(role, part, info['node'], info['citation'], info['emitter'])
            else:
                excisions.append(dict(info['selection'], action='excise-exact-components'))
    if 'DeskLamp' in roles:
        for n in red_nodes:
            add('DeskLamp', 'relocated_red_desk_lamp_arm_01', n, 'web/house/home.js:625', None)
    if 'BedLamp' in roles:
        for name, n in (bedside_nodes or {}).items():
            add('BedLamp', 'old_procedural_bedside_' + name, n, 'tools/build_home_bedside_lamp.py; web/house/home.js:1117',
                BEDSIDE_PARTS[name])
    indices = [e['source_node_index'] for e in entries]
    if len(set(indices)) != len(indices):
        raise RefuseError('duplicate node in hide manifest')
    batch_nodes = {x['node'] for x in excisions}
    if batch_nodes & set(indices):
        raise RefuseError('a shared batch node would be hidden as a whole')
    return {'schema': SCHEMA + '.hide-manifest', 'policy': 'hide in game and editor; never destroy; collision unchanged; '
            'shared batches are never hidden, only exact components excised by the remainder surgery',
            'entries': entries, 'excisions': excisions,
            'protected_never_hidden': sorted(NEVER_HIDE_NODES), 'protected_pattern': SCREEN_PATTERN.pattern}


def _norm_excision(spec):
    """{(node, primitive): set(triangle ids)} from list or nested-dict manifests."""
    out = {}
    rows = spec.get('excisions') if isinstance(spec, dict) and 'excisions' in spec else None
    if rows is None and isinstance(spec, dict) and 'nodes' in spec:
        rows = []
        for node, val in spec['nodes'].items():
            if 'primitives' in val:
                for prim, pv in val['primitives'].items():
                    rows.append({'node': int(node), 'primitive': int(prim), 'triangle_ids': pv['triangle_ids']})
            else:
                rows.append({'node': int(node), 'primitive': int(val.get('primitive', 0)),
                             'triangle_ids': val['triangle_ids']})
    if rows is None and isinstance(spec, list):
        rows = spec
    if rows is None:
        raise RefuseError('unrecognised excision manifest format')
    for r in rows:
        key = (int(r['node']), int(r.get('primitive', 0)))
        ids = [int(t) for t in r['triangle_ids']]
        if len(set(ids)) != len(ids):
            raise RefuseError(f'duplicate triangle IDs inside one excision row {key}')
        if out.get(key, set()) & set(ids):
            raise RefuseError(f'double removal inside one manifest at {key}')
        out.setdefault(key, set()).update(ids)
    return out


def lamp_excision_manifest(excisions):
    return {'schema': SCHEMA + '.excision', 'triangle_id': 'index within primitive (indices // 3)',
            'excisions': [{k: x[k] for k in ('node', 'primitive', 'triangle_ids', 'component_count', 'role', 'part',
                                             'citation', 'aabb_m')} for x in excisions]}


def combine_remainder(lamp_spec, rail_spec=None, triangle_counts=None):
    """ONE remainder spec per (node, primitive): union of lamp and rail triangle IDs.

    Refuses on any triangle claimed by both (double removal) or out of range."""
    lamp = _norm_excision(lamp_spec)
    rail = _norm_excision(rail_spec) if rail_spec else {}
    out = []
    for key in sorted(set(lamp) | set(rail)):
        a, b = lamp.get(key, set()), rail.get(key, set())
        both = a & b
        if both:
            raise RefuseError(f'double-removal conflict at node {key[0]} primitive {key[1]}: {sorted(both)[:10]}')
        union = sorted(a | b)
        total = (triangle_counts or {}).get(key)
        if total is not None and union and (union[-1] >= total or union[0] < 0):
            raise RefuseError(f'triangle ID out of range at {key}')
        out.append({'node': key[0], 'primitive': key[1], 'remove_triangle_ids': union,
                    'lamp_triangles': len(a), 'rail_triangles': len(b),
                    'remaining_triangles': None if total is None else total - len(union)})
    return {'schema': SCHEMA + '.combined-remainder', 'consumer': "root's remainder surgery (single edit per node)",
            'rail_manifest_included': bool(rail_spec), 'remainders': out}


def triangle_counts(doc):
    out = {}
    for i, n in enumerate(doc.get('nodes', [])):
        if 'mesh' not in n:
            continue
        for p, prim in enumerate(doc['meshes'][n['mesh']]['primitives']):
            acc = prim['indices'] if 'indices' in prim else prim['attributes']['POSITION']
            out[(i, p)] = doc['accessors'][acc]['count'] // 3
    return out


def zero_material_emission(m):
    """No uncontrolled glow: unlink and zero every emission input of one (owned) material."""
    changed = []
    for node in (m.node_tree.nodes if m.use_nodes else []):
        if node.type == 'BSDF_PRINCIPLED':
            for sock, value in (('Emission Strength', 0.0), ('Emission Color', (0, 0, 0, 1))):
                for link in list(node.inputs[sock].links):
                    m.node_tree.links.remove(link)
                node.inputs[sock].default_value = value
                changed.append(sock)
        elif node.type == 'EMISSION':
            for link in list(node.inputs['Strength'].links):
                m.node_tree.links.remove(link)
            node.inputs['Strength'].default_value = 0.0
            changed.append('Emission.Strength')
    return changed


def check_no_second_red_lamp(manifest, placements):
    hidden_red = [e for e in manifest['entries'] if e['part'] == 'relocated_red_desk_lamp_arm_01']
    new_red = [p for p in placements if p['asset'] == 'desk_lamp_arm_01']
    if len(new_red) > 1 or (new_red and not hidden_red):
        raise RefuseError('a second red desk lamp would be visible: the original must be hidden when relocating')
    return True


# --------------------------------------------------------------------------
# Asset measurement (asset glTF frame, metres)
# --------------------------------------------------------------------------
def measure_desk_lamp(prims):
    body = [v for name, em, vs in prims if not em for v in vs]
    bulb = [v for name, em, vs in prims if em for v in vs]
    if not body or not bulb:
        raise RefuseError('desk lamp: body and emissive bulb primitives required')
    flange = [v for v in body if -0.002 <= v[1] <= 0.03]
    pin = [v for v in body if v[1] < -0.002]
    if not [v for v in body if 0 <= v[1] <= 0.008]:
        raise RefuseError('desk lamp: no mounting flange at the asset rest plane y=0')
    (blo, bhi) = bounds(bulb)
    flo, fhi = bounds(flange)
    out = {'rest_plane_y': 0.0, 'bulb_center': [(blo[i] + bhi[i]) / 2 for i in range(3)],
           'flange_xz': [[flo[0], flo[2]], [fhi[0], fhi[2]]], 'aabb': [list(v) for v in bounds(body + bulb)],
           'height_above_rest': bounds(body + bulb)[1][1]}
    if pin:
        plo, phi = bounds(pin)
        out['mount_pin'] = {'aabb': [list(plo), list(phi)], 'depth_below_rest': -plo[1],
                            'center_xz': [(plo[0] + phi[0]) / 2, (plo[2] + phi[2]) / 2]}
    return out


def measure_pendant(prims, max_cable_radius=0.008, bin_m=0.01):
    allv = [v for _, _, vs in prims for v in vs]
    bulb = [v for _, em, vs in prims if em for v in vs]
    if not bulb:
        raise RefuseError('ceiling lamp: emissive bulb primitive required')
    lo, hi = bounds(allv)
    blo, bhi = bounds(bulb)
    top = hi[1]
    canopy = [v for v in allv if v[1] >= top - 0.003]
    clo, chi = bounds(canopy)
    # contiguous vertical band whose radial extent is a thin cable/rod
    nb = int(math.ceil((hi[1] - lo[1]) / bin_m)) + 1
    radius = [0.0] * nb
    count = [0] * nb
    cx, cz = (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2
    for x, y, z in allv:
        k = int((y - lo[1]) / bin_m)
        radius[k] = max(radius[k], math.hypot(x - cx, z - cz))
        count[k] += 1
    best, start = (0, 0), None
    for k in range(nb + 1):
        thin = k < nb and (count[k] == 0 or radius[k] <= max_cable_radius)
        if thin and start is None:
            start = k
        if not thin and start is not None:
            if k - start > best[1] - best[0]:
                best = (start, k)
            start = None
    if best[1] - best[0] < 3:
        raise RefuseError('ceiling lamp: no thin cable/rod band found')
    band = (lo[1] + best[0] * bin_m + bin_m, lo[1] + best[1] * bin_m - bin_m)  # keep 1 bin margin each end
    return {'canopy_top_y': top, 'canopy_radius': max(chi[0] - clo[0], chi[2] - clo[2]) / 2,
            'canopy_center_xz': [(clo[0] + chi[0]) / 2, (clo[2] + chi[2]) / 2],
            'bulb_center': [(blo[i] + bhi[i]) / 2 for i in range(3)], 'cable_band_y': list(band),
            'cable_length': band[1] - band[0], 'aabb': [list(lo), list(hi)],
            'native_drop': top - (blo[1] + bhi[1]) / 2}


def cable_remap(y, band, new_length):
    """Axial-only cable length change: band [lo, hi] -> [hi-new, hi]; below shifts rigidly."""
    lo, hi = band
    k = new_length / (hi - lo)
    if y >= hi:
        return y
    if y >= lo:
        return hi - (hi - y) * k
    return y + (hi - lo) - new_length


# --------------------------------------------------------------------------
# Placement planning (probes are injected: Blender BVH on the server, fakes in tests)
# --------------------------------------------------------------------------
def measure_table_lamp(prims, foot_band=0.006):
    """Free-standing lamp (industrial_pipe_lamp): rests on its lowest vertices."""
    body = [v for _, em, vs in prims if not em for v in vs]
    bulb = [v for _, em, vs in prims if em for v in vs]
    if not body or not bulb:
        raise RefuseError('table lamp: body and bulb primitives required')
    lo, hi = bounds(body + bulb)
    foot = [v for v in body if v[1] <= lo[1] + foot_band]
    flo, fhi = bounds(foot)
    blo, bhi = bounds(bulb)
    return {'rest_plane_y': lo[1], 'bulb_center': [(blo[i] + bhi[i]) / 2 for i in range(3)],
            'flange_xz': [[flo[0], flo[2]], [fhi[0], fhi[2]]], 'aabb': [list(lo), list(hi)],
            'dimensions_m': [hi[i] - lo[i] for i in range(3)], 'height_above_rest': hi[1] - lo[1]}


def plan_desk_lamp(asset, probe_down, anchor=LIGHT_SOURCE['DeskLamp'], yaw_deg=DESK_YAW_DEG,
                   edge_margin=0.01, flat_tol=0.0015, role='DeskLamp', asset_name='desk_lamp_arm_01',
                   align='bulb'):
    """probe_down(x, z) -> (surface_y, object_name, normal_y) or None (source frame).

    align='bulb': bulb above the light's (x, z); align='footprint': footprint centred there."""
    (fx0, fz0), (fx1, fz1) = asset['flange_xz']
    ref = asset['bulb_center'] if align == 'bulb' else ((fx0 + fx1) / 2, 0.0, (fz0 + fz1) / 2)
    bx, _, bz = rotate_y(ref, yaw_deg)
    tx, tz = anchor[0] - bx, anchor[2] - bz
    pts = []
    for x in (fx0 - edge_margin, fx1 + edge_margin):
        for z in (fz0 - edge_margin, fz1 + edge_margin):
            pts.append(rotate_y((x, 0, z), yaw_deg))
    pts.append(rotate_y(((fx0 + fx1) / 2, 0, (fz0 + fz1) / 2), yaw_deg))
    if 'mount_pin' in asset:
        c = asset['mount_pin']['center_xz']
        pts.append(rotate_y((c[0], 0, c[1]), yaw_deg))
    hits = []
    for px, _, pz in pts:
        h = probe_down(px + tx, pz + tz)
        if h is None:
            raise RefuseError(f'{role}: no support under ({px + tx:.3f}, {pz + tz:.3f}) - off the desk edge')
        hits.append(h)
    names = {h[1] for h in hits}
    ys = [h[0] for h in hits]
    if len(names) != 1:
        raise RefuseError(f'{role}: footprint spans several supports {sorted(names)}')
    if max(ys) - min(ys) > flat_tol or min(h[2] for h in hits) < 0.98:
        raise RefuseError(f'{role}: support under footprint is not one flat desk top (edge, hole or slope)')
    top = sum(ys) / len(ys)
    origin = (tx, top - asset['rest_plane_y'], tz)
    bulb = tuple(origin[i] + rotate_y(asset['bulb_center'], yaw_deg)[i] for i in range(3))
    return {'role': role, 'asset': asset_name, 'support_object': names.pop(),
            'support_top_y': top, 'origin_source_m': list(origin), 'yaw_source_deg': yaw_deg,
            'bulb_source_m': list(bulb), 'light_source_m': list(anchor),
            'light_to_bulb_m': [anchor[i] - bulb[i] for i in range(3)], 'uniform_scale': 1.0,
            'probe_points': len(pts)}


def plan_pendant(role, asset, probe_up, anchor=None, flush_tol=0.002, min_cable=0.03, max_cable=3.0):
    """probe_up(x, y_start, z) -> (ceiling_y, object_name, normal_y) or None (source frame)."""
    anchor = anchor or LIGHT_SOURCE[role]
    ax, ay, az = anchor
    c = probe_up(ax, ay, az)
    if c is None or c[2] > -0.98:
        raise RefuseError(f'{role}: no downward-facing ceiling underside above the anchor')
    ring = []
    for k in range(8):
        a = 2 * math.pi * k / 8
        r = asset['canopy_radius']
        h = probe_up(ax + r * math.cos(a), ay, az + r * math.sin(a))
        if h is None or h[1] != c[1] or abs(h[0] - c[0]) > flush_tol:
            raise RefuseError(f'{role}: canopy would not sit flush on one ceiling surface')
        ring.append(h[0])
    ceiling = c[0]
    drop = ceiling - ay
    required = asset['cable_length'] + (drop - asset['native_drop'])
    if required > max_cable:
        raise RefuseError(f'{role}: required cable length {required:.3f} m exceeds {max_cable} m')
    if drop - (asset['native_drop'] - asset['cable_length']) < min_cable - 0.15:
        raise RefuseError(f'{role}: ceiling only {drop:.3f} m above the light; the real fixture cannot fit')
    # Too low a ceiling: shortest real cable, bulb sits below the light (reported, light not moved).
    new_len = max(required, min_cable)
    # origin chosen so the canopy centre sits on the anchor axis, canopy top on the ceiling
    cc = asset['canopy_center_xz']
    origin = (ax - cc[0], ceiling - asset['canopy_top_y'], az - cc[1])
    band = asset['cable_band_y']
    bulb_y = origin[1] + cable_remap(asset['bulb_center'][1], band, new_len)
    return {'role': role, 'asset': 'modern_ceiling_lamp_01', 'support_object': c[1],
            'ceiling_underside_y': ceiling, 'ceiling_flatness_m': max(ring) - min(ring),
            'origin_source_m': list(origin), 'yaw_source_deg': 0.0, 'cable_length_native_m': asset['cable_length'],
            'cable_length_m': new_len, 'cable_band_y': band, 'cable_clamped_to_minimum': new_len != required,
            'required_cable_length_m': required,
            'lowest_point_source_y': origin[1] + cable_remap(asset['aabb'][0][1], band, new_len),
            'bulb_source_m': [ax - cc[0] + asset['bulb_center'][0], bulb_y, az - cc[1] + asset['bulb_center'][2]],
            'light_source_m': list(anchor), 'uniform_scale': 1.0}


def light_relation(plan, shade_radius=0.11):
    d = math.dist(plan['bulb_source_m'], plan['light_source_m'])
    if d <= 0.03:
        status = 'at-bulb'
    elif d <= shade_radius:
        status = 'inside-shade-off-bulb'
    else:
        status = 'outside-shade'
    return {'distance_m': d, 'status': status,
            'proposal': None if status == 'at-bulb' else
            {'light': ROLE_LIGHT[plan['role']], 'move_to_source_m': plan['bulb_source_m'],
             'move_to_ue_cm_contract': list(source_to_ue_cm(plan['bulb_source_m'])),
             'note': 'proposal only; light components are not moved by these tools'}}


def fingerprint_rows(rows):
    blob = json.dumps(sorted(rows, key=lambda r: r['name']), sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()


def provenance(paths):
    out = {}
    for key, p in paths.items():
        p = Path(p)
        doc, _ = load_gltf(p)
        files = [p] + [p.parent / b['uri'] for b in doc.get('buffers', []) if b.get('uri')] + \
                [p.parent / i['uri'] for i in doc.get('images', []) if i.get('uri')]
        out[key] = dict(POLYHAVEN[key], files={str(f.relative_to(p.parent)): sha256_file(f) for f in files})
    return out


def parse_args(argv):
    p = argparse.ArgumentParser(description='Real CC0 lamp replacement builder (server Blender only)')
    p.add_argument('--source-glb', type=Path, required=True)
    p.add_argument('--source-sha', default=REVIEWED_SOURCE_SHA)
    p.add_argument('--ceiling-lamp', type=Path, required=True)
    p.add_argument('--desk-lamp', type=Path, required=True)
    p.add_argument('--bedside-lamp', type=Path,
                   help='reviewed industrial_pipe_lamp directory or .gltf (old procedural bedside lamp is hidden)')
    p.add_argument('--rail-excision', type=Path, help="root's rail builder triangle-ID manifest (read-only)")
    p.add_argument('--bedside-yaw', type=float, default=BEDSIDE_YAW_DEG)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--roles', default=','.join(ROLES))
    p.add_argument('--min-clearance', type=float, default=0.02)
    p.add_argument('--dry-run', action='store_true')
    a = p.parse_args(argv)
    a.roles = tuple(r for r in a.roles.split(',') if r)
    if 'BedLamp' in a.roles and not a.bedside_lamp:
        a.roles = tuple(r for r in a.roles if r != 'BedLamp')
    if not set(a.roles) <= set(ROLES) or not a.roles:
        p.error(f'--roles must be a subset of {ROLES}')
    return a


def plan_bedside(asset, probe_down, yaw_deg=BEDSIDE_YAW_DEG):
    """industrial_pipe_lamp on the actual nightstand top, footprint centred under the BedLamp light's (x, z)
    (the old lamp's axis); the bulb offset from the light is reported, the light is not moved."""
    return plan_desk_lamp(asset, probe_down, anchor=LIGHT_SOURCE['BedLamp'], yaw_deg=yaw_deg,
                          role='BedLamp', asset_name='industrial_pipe_lamp', align='footprint')


# --------------------------------------------------------------------------
# Blender section (server only)
# --------------------------------------------------------------------------
def _blender_main(args):  # pragma: no cover - exercised on the server
    import bpy
    import bmesh
    from mathutils import Matrix, Vector
    from mathutils.bvhtree import BVHTree

    if sha256_file(args.source_glb) != args.source_sha:
        raise RefuseError('full-home GLB sha256 differs from the explicit expected identity')
    doc, buffers = load_gltf(args.source_glb)
    nodes = glb_mesh_nodes(doc, buffers)
    comp_cache = {}

    def components_of(index):
        if index not in comp_cache:
            comp_cache[index] = primitive_components(doc, buffers, index)
        return comp_cache[index]
    parts = identify_originals(nodes, components_of)
    red = identify_red_lamp(nodes) if 'DeskLamp' in args.roles else []
    bedside_nodes = identify_bedside(nodes) if 'BedLamp' in args.roles else {}
    manifest = build_hide_manifest(parts, red, args.roles, bedside_nodes)
    tri_counts = triangle_counts(doc)
    lamp_excision = lamp_excision_manifest(manifest['excisions'])
    rail_spec = json.loads(args.rail_excision.read_text()) if args.rail_excision else None
    remainder = combine_remainder(lamp_excision, rail_spec, tri_counts)
    excised_boxes = [x['aabb_m'] for x in manifest['excisions']]

    scene = bpy.context.scene
    if not [o for o in scene.objects if o.type == 'MESH']:
        bpy.ops.import_scene.gltf(filepath=str(args.source_glb.resolve()))
    depsgraph = bpy.context.evaluated_depsgraph_get()

    def world_bounds_source(obj):
        ev = obj.evaluated_get(depsgraph)
        me = ev.to_mesh()
        pts = [blender_to_source(tuple(obj.matrix_world @ v.co)) for v in me.vertices]
        ev.to_mesh_clear()
        return [list(v) for v in bounds(pts)] if pts else None

    pre = {}
    for obj in scene.objects:
        if obj.type == 'MESH':
            pre[obj.name] = obj
    # GLB node -> Blender object by evaluated world bounds (+ name when present)
    obj_bounds = {name: world_bounds_source(o) for name, o in pre.items()}

    def blender_object_for(node):
        hits = [n for n, b in obj_bounds.items() if b and aabb_match(b, node['aabb'], 0.003)]
        named = [n for n in hits if node.get('name') and n.split('.')[0] == node['name']]
        hits = named or hits
        if len(hits) != 1:
            raise RefuseError(f'GLB node {node["index"]} maps to {len(hits)} Blender objects')
        return hits[0]

    for e in manifest['entries']:
        node = next(n for n in nodes if n['index'] == e['source_node_index'])
        e['blender_object'] = blender_object_for(node)
    excluded = {e['blender_object'] for e in manifest['entries']}

    def fingerprint():
        rows = []
        for o in scene.objects:
            if o.name not in pre and o.type == 'MESH' or o.name.startswith(ACTOR_PREFIX):
                continue
            rows.append({'name': o.name, 'type': o.type, 'matrix': [round(v, 6) for r in o.matrix_world for v in r],
                         'hide': [o.hide_viewport, o.hide_render, o.hide_get()],
                         'data': o.data.name if o.data else None,
                         'verts': len(o.data.vertices) if o.type == 'MESH' else None,
                         'materials': [s.material.name if s.material else None for s in o.material_slots]})
        return fingerprint_rows(rows), len(rows)
    before = fingerprint()

    # BVH trees of every other evaluated mesh (source-frame probes)
    trees = {}
    for name, o in pre.items():
        if name in excluded:
            continue
        ev = o.evaluated_get(depsgraph)
        me = ev.to_mesh()
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.transform(o.matrix_world)
        if excised_boxes:  # excised exact components are not obstacles/supports
            def inside(v, box):
                p = blender_to_source(tuple(v.co))
                return all(box[0][i] - 0.002 <= p[i] <= box[1][i] + 0.002 for i in range(3))
            drop = [f for f in bm.faces if any(all(inside(v, b) for v in f.verts) for b in excised_boxes)]
            if drop:
                bmesh.ops.delete(bm, geom=drop, context='FACES_ONLY')
        trees[name] = BVHTree.FromBMesh(bm)
        bm.free()
        ev.to_mesh_clear()

    def cast(origin_src, direction_blender):
        o = Vector(source_to_blender(origin_src))
        d = Vector(direction_blender)
        best = None
        for name, t in trees.items():
            loc, nor, _, dist = t.ray_cast(o, d)
            if loc is not None and (best is None or dist < best[3]):
                best = (loc, nor, name, dist)
        return best

    probe_start = {'y': 1.30}

    def probe_down(x, z):
        h = cast((x, probe_start['y'], z), (0, 0, -1))
        return None if h is None else (h[0].z, h[2], h[1].z)

    def probe_up(x, y, z):
        h = cast((x, y, z), (0, 0, 1))
        return None if h is None else (h[0].z, h[2], h[1].z)

    report = {'schema': SCHEMA, 'source_glb_sha256': args.source_sha, 'roles': {}, 'refused_roles': {},
              'old_bedside_lamp': 'procedural (tools/build_home_bedside_lamp.py); hidden via manifest when BedLamp is placed'}
    asset_paths = {'modern_ceiling_lamp_01': resolve_asset(args.ceiling_lamp),
                   'desk_lamp_arm_01': resolve_asset(args.desk_lamp)}
    if args.bedside_lamp:
        asset_paths['industrial_pipe_lamp'] = resolve_asset(args.bedside_lamp)
    desk_asset = measure_desk_lamp(primitive_vertices(asset_paths['desk_lamp_arm_01']))
    ceil_asset = measure_pendant(primitive_vertices(asset_paths['modern_ceiling_lamp_01']))
    bed_asset = (measure_table_lamp(primitive_vertices(asset_paths['industrial_pipe_lamp']))
                 if 'industrial_pipe_lamp' in asset_paths else None)
    report['assets'] = {'desk_lamp_arm_01': desk_asset, 'modern_ceiling_lamp_01': ceil_asset,
                        'industrial_pipe_lamp': bed_asset}
    plans = {}
    for role in args.roles:
        try:
            if role == 'DeskLamp':
                probe_start['y'] = 1.30  # below the shelves, above the desk top (0.845)
                plans[role] = plan_desk_lamp(desk_asset, probe_down)
            elif role == 'BedLamp':
                probe_start['y'] = LIGHT_SOURCE['BedLamp'][1]  # old lamp hidden; nightstand top ~3.5
                plans[role] = plan_bedside(bed_asset, probe_down, args.bedside_yaw)
            else:
                plans[role] = plan_pendant(role, ceil_asset, probe_up)
        except RefuseError as exc:
            report['refused_roles'][role] = str(exc)

    coll = bpy.data.collections.get(COLLECTION) or bpy.data.collections.new(COLLECTION)
    if coll.name not in scene.collection.children:
        scene.collection.children.link(coll)
    if coll.objects:
        raise RefuseError(f'{COLLECTION} already has objects; run on a clean base')

    def import_asset(path):
        prior = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(Path(path).resolve()))
        new = [o for o in bpy.data.objects if o not in prior]
        meshes = [o for o in new if o.type == 'MESH']
        for o in meshes:
            if any(abs(s - 1) > 1e-6 for s in o.matrix_world.to_scale()):
                raise RefuseError(f'{path}: imported with non-unit scale')
            o.data.transform(o.matrix_world)
            o.parent = None
            o.matrix_world = Matrix.Identity(4)
        if not meshes:
            raise RefuseError(f'{path}: no mesh imported')
        if len(meshes) > 1:
            with bpy.context.temp_override(active_object=meshes[0], selected_editable_objects=meshes):
                bpy.ops.object.join()
        for o in [o for o in bpy.data.objects if o not in prior]:
            for c in list(o.users_collection):
                c.objects.unlink(o)
            if o.type != 'MESH':
                bpy.data.objects.remove(o)
        return meshes[0]

    emission_slots = {}

    def zero_emission(obj, role):
        for slot in obj.material_slots:
            m = slot.material
            if m is None:
                continue
            if not m.name.startswith(ACTOR_PREFIX):
                m = m.copy()
                m.name = f'{ACTOR_PREFIX}{role}_{slot.material.name}'
                slot.material = m
            zero_material_emission(m)
            emission_slots.setdefault(role, []).append(m.name)

    placed = []
    desk_proto = ceil_proto = bed_proto = None
    for role, plan in plans.items():
        obj = None
        try:
            if role == 'DeskLamp':
                desk_proto = desk_proto or import_asset(asset_paths['desk_lamp_arm_01'])
                obj = desk_proto
            elif role == 'BedLamp':
                bed_proto = bed_proto or import_asset(asset_paths['industrial_pipe_lamp'])
                obj = bed_proto
            else:
                ceil_proto = ceil_proto or import_asset(asset_paths['modern_ceiling_lamp_01'])
                obj = ceil_proto.copy()
                obj.data = ceil_proto.data.copy()
                band = plan['cable_band_y']
                for v in obj.data.vertices:  # Blender local Z == asset glTF Y
                    v.co.z = cable_remap(v.co.z, band, plan['cable_length_m'])
            obj.name = ACTOR_PREFIX + role
            coll.objects.link(obj)
            zero_emission(obj, role)
            obj.matrix_world = (Matrix.Translation(Vector(source_to_blender(plan['origin_source_m'])))
                                @ Matrix.Rotation(math.radians(plan['yaw_source_deg']), 4, 'Z'))
            obj['sub01_role'] = role
            obj['sub01_asset'] = plan['asset']
            bpy.context.view_layer.update()
            # collisions / clearance against every other evaluated mesh
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            bm.transform(obj.matrix_world)
            tree = BVHTree.FromBMesh(bm)
            pts = [v.co.copy() for v in bm.verts]
            face_z = [(min(v.co.z for v in f.verts), max(v.co.z for v in f.verts)) for f in bm.faces]
            bm.free()
            if role in ('DeskLamp', 'BedLamp'):
                def contact_face(i):  # flange and grommet pin only (rest plane + 3 cm)
                    return face_z[i][1] <= plan['support_top_y'] + 0.03
            else:
                def contact_face(i):  # canopy top only
                    return face_z[i][0] >= plan['ceiling_underside_y'] - 0.003
            near = {}
            for name, t in trees.items():
                pairs = tree.overlap(t)
                allowed = name == plan['support_object']
                bad = [i for i, _ in pairs if not (allowed and contact_face(i))]
                if bad:
                    raise RefuseError(f'{role}: intersects {name} ({len(bad)} face pairs outside the support contact)')
                dmin = min((t.find_nearest(p)[3] for p in pts[::7] if t.find_nearest(p)[0] is not None),
                           default=float('inf'))
                if dmin < args.min_clearance and not allowed:
                    raise RefuseError(f'{role}: clearance {dmin:.3f} m to {name} < {args.min_clearance}')
                if dmin < 0.25:
                    near[name] = round(dmin, 4)
            top = max(p.z for p in pts)
            if role in ('LowerPendant', 'UpperPendant') and top > plan['ceiling_underside_y'] + 0.0005:
                raise RefuseError(f'{role}: geometry crosses the ceiling by {top - plan["ceiling_underside_y"]:.4f} m')
            plan['nearby_clearance_m'] = near
            plan['light_relation'] = light_relation(plan)
            plan['ue_location_cm_contract'] = list(source_to_ue_cm(plan['origin_source_m']))
            plan['ue_yaw_deg_contract'] = ue_yaw_from_source(plan['yaw_source_deg'])
            plan['emission_slots'] = emission_slots.get(role, [])
            plan['ue_glb'] = f'{ACTOR_PREFIX}{role}.glb'
            report['roles'][role] = plan
            placed.append(plan)
        except RefuseError as exc:
            report['refused_roles'][role] = str(exc)
            if obj and obj.name in coll.objects:
                coll.objects.unlink(obj)

    # roles refused => their originals stay visible
    manifest['entries'] = [e for e in manifest['entries'] if e['role'] in report['roles']]
    manifest['excisions'] = [x for x in manifest['excisions'] if x['role'] in report['roles']]
    lamp_excision = lamp_excision_manifest(manifest['excisions'])
    remainder = combine_remainder(lamp_excision, rail_spec, tri_counts)
    check_no_second_red_lamp(manifest, placed)
    after = fingerprint()
    if before != after:
        raise RefuseError('pre-existing objects changed (fingerprint mismatch)')
    pre_now = {o.name for o in scene.objects if o.type == 'MESH' and o.name not in coll.objects}
    if pre_now != set(pre):
        raise RefuseError('pre-existing object set changed')
    report['fingerprint_before'] = before
    report['fingerprint_after_excluding_new'] = after
    report['provenance'] = provenance(asset_paths)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / 'placement-report.json').write_text(json.dumps(report, indent=2))
    (args.output_dir / 'original-hide-manifest.json').write_text(json.dumps(manifest, indent=2))
    (args.output_dir / 'provenance.json').write_text(json.dumps(report['provenance'], indent=2))
    (args.output_dir / 'lamp-excision-triangles.json').write_text(json.dumps(lamp_excision, indent=2))
    (args.output_dir / 'combined-remainder-spec.json').write_text(json.dumps(remainder, indent=2))
    if args.dry_run or not placed:
        print(json.dumps({'dry_run': args.dry_run, 'roles': list(report['roles']),
                          'refused': report['refused_roles']}, indent=2))
        return report
    bpy.ops.object.select_all(action='DESELECT')
    for o in coll.objects:
        o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str((args.output_dir / 'real-lamps.glb').resolve()), export_format='GLB',
                              use_selection=True, export_yup=True, export_extras=True, export_apply=True)
    for o in list(coll.objects):
        bpy.ops.object.select_all(action='DESELECT')
        saved = o.matrix_world.copy()
        o.matrix_world = Matrix.Identity(4)
        o.select_set(True)
        bpy.ops.export_scene.gltf(filepath=str((args.output_dir / f'{o.name}.glb').resolve()), export_format='GLB',
                                  use_selection=True, export_yup=True, export_extras=True, export_apply=True)
        o.matrix_world = saved
    report['exports'] = {p.name: sha256_file(p) for p in sorted(args.output_dir.glob('*.glb'))}
    if fingerprint()[0] != after[0]:
        raise RefuseError('pre-existing objects changed during export')
    (args.output_dir / 'placement-report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({'placed': list(report['roles']), 'refused': report['refused_roles'],
                      'exports': report['exports']}, indent=2))
    return report


def main(argv=None):  # pragma: no cover
    argv = sys.argv[sys.argv.index('--') + 1:] if argv is None and '--' in sys.argv else (argv or [])
    args = parse_args(argv)
    try:
        _blender_main(args)
    except RefuseError as exc:
        print('REFUSED:', exc, file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':  # pragma: no cover
    main()
