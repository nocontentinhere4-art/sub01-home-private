"""Read-only GLB UV-to-head-surface witness, never an accepted camera attachment.

UV locations must be explicitly annotated on the original head texture. This measures
actual textured surface points and their Head-joint local coordinates. It does not
invent eyeballs, change bones or move a runtime camera. Run geometry on the server.
"""
import argparse
import hashlib
import json
import math
import struct
from pathlib import Path


def barycentric_uv(point, triangle):
    a, b, c = triangle
    ux, uy, vx, vy = b[0]-a[0], b[1]-a[1], c[0]-a[0], c[1]-a[1]
    d = ux*vy-uy*vx
    if abs(d) < 1e-12:
        return None
    px, py = point[0]-a[0], point[1]-a[1]
    w1, w2 = (px*vy-py*vx)/d, (ux*py-uy*px)/d
    weights = [1-w1-w2, w1, w2]
    return weights if min(weights) >= -1e-8 else None


def surface_point(uv, positions, texcoords, indices):
    if len(uv) != 2 or not all(math.isfinite(v) and 0 <= v <= 1 for v in uv):
        raise ValueError('Explicit finite normalized texture UV required')
    hits = []
    for start in range(0, len(indices), 3):
        ids = indices[start:start+3]
        if len(ids) != 3:
            raise ValueError('Incomplete head triangle')
        w = barycentric_uv(uv, [texcoords[i] for i in ids])
        if w is None:
            continue
        p = [sum(w[k]*positions[ids[k]][axis] for k in range(3)) for axis in range(3)]
        if not all(math.isfinite(v) for v in p):
            raise ValueError('Nonfinite head geometry')
        hits.append({'triangle': start//3, 'vertices': ids, 'weights': w, 'point': p})
    if not hits:
        raise ValueError('Annotated UV has no actual head geometry')
    if any(math.dist(hit['point'], hits[0]['point']) > 1e-6 for hit in hits[1:]):
        raise ValueError('UV annotation maps to ambiguous distinct head surfaces')
    return hits[0]


def read_glb(path):
    raw = path.read_bytes()
    magic, version, length = struct.unpack_from('<III', raw)
    if magic != 0x46546c67 or version != 2 or length != len(raw):
        raise ValueError('Invalid exact source GLB')
    chunks, at = {}, 12
    while at < len(raw):
        size, kind = struct.unpack_from('<II', raw, at)
        chunks[kind] = raw[at+8:at+8+size]
        at += size+8
    return json.loads(chunks[0x4e4f534a]), chunks[0x004e4942], hashlib.sha256(raw).hexdigest()


def accessor(doc, binary, index):
    a = doc['accessors'][index]
    view = doc['bufferViews'][a['bufferView']]
    if a.get('sparse') or view.get('extensions', {}).get('EXT_meshopt_compression'):
        raise ValueError('Use the exact existing decoded owner GLB; no compressed/sparse guessing')
    width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'MAT4': 16}[a['type']]
    fmt, size, maximum = {5126: ('f', 4, None), 5123: ('H', 2, 65535), 5121: ('B', 1, 255)}[a['componentType']]
    stride = view.get('byteStride', width*size)
    offset = view.get('byteOffset', 0)+a.get('byteOffset', 0)
    rows = [list(struct.unpack_from('<'+fmt*width, binary, offset+i*stride)) for i in range(a['count'])]
    if maximum and a.get('normalized'):
        rows = [[v/maximum for v in row] for row in rows]
    return rows


def audit(path, eyes):
    doc, binary, sha = read_glb(path)
    materials = [i for i, m in enumerate(doc['materials']) if m.get('name') == 'owner_head']
    heads = [(i, n) for i, n in enumerate(doc['nodes']) if n.get('name', '').endswith(':Head')]
    meshes = [(i, n, p) for i, n in enumerate(doc['nodes']) if 'mesh' in n and 'skin' in n
              for p in doc['meshes'][n['mesh']]['primitives'] if p.get('material') in materials]
    if len(materials) != 1 or len(heads) != 1 or len(meshes) != 1:
        raise ValueError('Original owner head material, joint and skinned primitive must be unique')
    mesh_node, node, primitive = meshes[0]
    attributes = primitive['attributes']
    pos = accessor(doc, binary, attributes['POSITION'])
    uv = accessor(doc, binary, attributes['TEXCOORD_0'])
    ids = [v[0] for v in accessor(doc, binary, primitive['indices'])]
    skin = doc['skins'][node['skin']]
    matrix = accessor(doc, binary, skin['inverseBindMatrices'])[skin['joints'].index(heads[0][0])]
    rows = []
    for eye in eyes:
        hit = surface_point(eye, pos, uv, ids)
        p = hit['point']
        local = [sum(matrix[k*4+axis]*p[k] for k in range(3))+matrix[12+axis] for axis in range(3)]
        rows.append({'annotated_texture_uv': eye, 'source_mesh_point': p,
                     'head_local_import_units': local, **{k: hit[k] for k in ('triangle', 'vertices', 'weights')}})
    return {'schema': 'sub01.owner-eye-surface-witness.v1', 'source_sha256': sha,
            'head_joint': heads[0][1]['name'], 'mesh_node': mesh_node, 'head_material': 'owner_head',
            'points': rows, 'midpoint_head_local_import_units': [sum(r['head_local_import_units'][a] for r in rows)/len(rows) for a in range(3)],
            'camera_accepted': False, 'runtime_ready': False,
            'limitation': 'Explicit visual iris-texel annotations mapped to actual surface; not eyeball centers. Native owner-joint/unit parity and actual camera visual QA required.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('owner', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--eye-uv', nargs=2, type=float, action='append', required=True)
    args = parser.parse_args()
    if len(args.eye_uv) != 2:
        parser.error('Two annotated iris texture locations are required')
    args.output.write_text(json.dumps(audit(args.owner, args.eye_uv), indent=2)+'\n')
