"""Source-mesh support-surface measurement of the home's BED and SOFA GLBs (pure Python + numpy; SOURCE, never native).

    python3 tools/measure_source_support_surface.py bed  [--glb web/house/assets/cc0-queen-bed/queen-bed.glb] [--out OUT.json]
    python3 tools/measure_source_support_surface.py sofa [--glb web/house/assets/haven-sofa/sofa.glb] [--out OUT.json]
    python3 tools/measure_source_support_surface.py compare SOURCE.json <project>/private-audit/native-bed-surface.json
    python3 tools/measure_source_support_surface.py compare SOURCE.json <project>/private-audit/native-sofa-surface.json

What it measures, with the SAME rules the native editor audits apply to the imported meshes:
  * bed: tools/unreal_bed_surface_audit.py mattress_top / duvet_top / head_end_direction (imported, not copied) on
    the cream (mattress), linen (pillows) and blue_fabric (duvet) material groups of the prepared CC0 queen bed;
  * sofa: tools/unreal_sofa_surface_audit.py seat_surface (upward > 0.65, edge-connected, exposed, per-cushion area
    >= the controller adapter's MIN_SEAT_AREA_CM2) on the Haven_linen group of the prepared Haven sofa.
Frames: glTF is Y-up metres; UE is Z-up centimetres with UE = 100 * (x, z, y) (the export_seat_fit_source.py /
fit_controller_grip.py contract). That swap is a reflection, so every triangle is re-wound (i, k, j) to keep its
outward cross-product normal; the file's own NORMAL attribute is mapped the same way and its agreement is reported.
Placement: the asset metadata's authored runtime position/yaw (three.js rotation.y) as the web room places it, then
the same UE mapping. That is the AUTHORED placement, not the native one: the native report is the only measurement
of the imported home, and `compare` only reports the deltas (no tolerance exists for them, so none is gated).

Output label: 'source_measured', native_verified: false. Nothing here can make a readiness gate pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import life_gltf as G  # noqa: E402  (existing glTF reader; refuses meshopt-compressed views)
from export_seat_fit_source import accessor  # noqa: E402  (existing accessor decoder)
import unreal_bed_surface_audit as bed_audit  # noqa: E402  (read-only: the native bed rule)
import unreal_sofa_surface_audit as sofa_audit  # noqa: E402  (read-only: the native sofa rule)
from unreal_life_clips_runtime import MIN_MATTRESS_AREA_CM2  # noqa: E402
from unreal_controller_play_runtime import MIN_SEAT_AREA_CM2  # noqa: E402

SCHEMA = 'sub01.source-support-surface.v1'
LABEL = 'source_measured'
ASSETS = {
    'bed': {'glb': ROOT / 'web/house/assets/cc0-queen-bed/queen-bed.glb', 'meta': ROOT / 'web/house/assets/cc0-queen-bed/queen-bed.json',
            'position_key': 'runtime_position', 'yaw_key': 'runtime_yaw'},
    'sofa': {'glb': ROOT / 'web/house/assets/haven-sofa/sofa.glb', 'meta': ROOT / 'web/house/assets/haven-sofa/sofa.json',
             'position_key': 'runtime_origin', 'yaw_key': 'runtime_yaw'},
}
SOFA_SEAT_NODE = 'Haven_linen'      # tools/build_home_haven_sofa.py: 'Oatmeal' upholstery merged into Haven_linen


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rel(path) -> str:
    path = Path(path).resolve()
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


# ------------------------------------------------------------------ frames
def gltf_to_ue_cm(points) -> np.ndarray:
    """glTF Y-up metres -> UE Z-up centimetres: UE = 100 * (x, z, y)."""
    p = np.asarray(points, float)
    return 100.0 * p[..., [0, 2, 1]]


def rewind(faces) -> np.ndarray:
    """The (x, z, y) swap mirrors handedness: (i, j, k) -> (i, k, j) keeps the outward cross-product normal."""
    return np.asarray(faces, int)[:, [0, 2, 1]]


def place_web(points_m, position, yaw) -> np.ndarray:
    """three.js object.position + rotation.y (web metres): x' = c x + s z, z' = -s x + c z."""
    p = np.asarray(points_m, float)
    c, s = math.cos(yaw), math.sin(yaw)
    out = np.empty_like(p)
    out[:, 0] = position[0] + c * p[:, 0] + s * p[:, 2]
    out[:, 1] = position[1] + p[:, 1]
    out[:, 2] = position[2] - s * p[:, 0] + c * p[:, 2]
    return out


def rotate_web_dir(normals, yaw) -> np.ndarray:
    return place_web(normals, (0.0, 0.0, 0.0), yaw)


def node_matrices(doc) -> dict:
    """World matrix of every node (glTF TRS or matrix, parent chain)."""
    parents = {c: i for i, n in enumerate(doc['nodes']) for c in n.get('children', [])}
    local = {}
    for i, n in enumerate(doc['nodes']):
        if 'matrix' in n:
            m = np.asarray(n['matrix'], float).reshape(4, 4).T
        else:
            x, y, z, w = n.get('rotation', (0, 0, 0, 1))
            r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                          [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                          [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
            m = np.eye(4)
            m[:3, :3] = r * np.asarray(n.get('scale', (1, 1, 1)), float)[None, :]
            m[:3, 3] = n.get('translation', (0, 0, 0))
        local[i] = m
    world = {}

    def get(i):
        if i not in world:
            world[i] = (get(parents[i]) @ local[i]) if i in parents else local[i]
        return world[i]
    return {i: get(i) for i in local}


def load_groups(path) -> list:
    """Every mesh primitive as {'node','material','positions_m','normals','faces'} with node transforms baked."""
    g = G.Gltf(path)
    doc = g.doc
    mats = node_matrices(doc)
    out = []
    for i, n in enumerate(doc['nodes']):
        if 'mesh' not in n:
            continue
        m = mats[i]
        for prim in doc['meshes'][n['mesh']]['primitives']:
            if prim.get('mode', 4) != 4:
                raise ValueError(f'{path}: node {n.get("name")} primitive is not TRIANGLES')
            v = accessor(g, prim['attributes']['POSITION'])
            nr = accessor(g, prim['attributes']['NORMAL']) if 'NORMAL' in prim['attributes'] else None
            f = accessor(g, prim['indices']).astype(int).reshape(-1, 3) if 'indices' in prim else np.arange(len(v)).reshape(-1, 3)
            pw = v @ m[:3, :3].T + m[:3, 3]
            nw = None
            if nr is not None:
                nw = nr @ np.linalg.inv(m[:3, :3])
                nw /= np.maximum(np.linalg.norm(nw, axis=1, keepdims=True), 1e-12)
            mat = doc['materials'][prim['material']].get('name') if 'material' in prim else None
            out.append({'node': n.get('name'), 'material': mat, 'positions_m': pw, 'normals': nw, 'faces': f})
    return out


def ue_group(group, position, yaw):
    """A group in UE world cm at the authored placement: (vertices list, flat index list, normals list or None)."""
    v = gltf_to_ue_cm(place_web(group['positions_m'], position, yaw))
    n = None if group['normals'] is None else rotate_web_dir(group['normals'], yaw)[:, [0, 2, 1]]
    f = rewind(group['faces'])
    return v.tolist(), [int(i) for i in f.ravel()], None if n is None else n.tolist()


def normal_agreement(vertices, indices, normals) -> float | None:
    """Share of non-degenerate triangles whose re-wound cross-product normal agrees in sign of z with the file's
    mapped vertex normals (a check of the frame mapping, not a selection input)."""
    if normals is None:
        return None
    v = np.asarray(vertices)
    f = np.asarray(indices).reshape(-1, 3)
    n = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    vn = np.asarray(normals)[f].mean(axis=1)
    ok = (np.linalg.norm(n, axis=1) > 0) & (np.abs(vn[:, 2]) > 1e-6) & (np.abs(n[:, 2]) > 1e-9)
    return round(float(np.mean(np.sign(n[ok, 2]) == np.sign(vn[ok, 2]))), 6) if ok.any() else None


def source_block(kind, glb, meta):
    meta_doc = json.loads(Path(meta).read_text())
    spec = ASSETS[kind]
    position, yaw = meta_doc[spec['position_key']], float(meta_doc[spec['yaw_key']])
    if len(position) != 3 or not all(math.isfinite(float(x)) for x in [*position, yaw]):
        raise ValueError(f'{meta}: authored runtime placement is not finite')
    block = {'glb': rel(glb), 'glb_sha256': sha256(glb), 'metadata': rel(meta), 'metadata_sha256': sha256(meta),
             'authored_runtime_position_web_m': [float(x) for x in position], 'authored_runtime_yaw_rad': yaw,
             'frame': 'UE world cm = 100 * (x, z, y) of the web world (three.js rotation.y yaw then position); AUTHORED placement, not native',
             'metadata_recorded_sha256': meta_doc.get('sha256') or meta_doc.get('prepared_sha256')}
    if block['metadata_recorded_sha256'] and block['metadata_recorded_sha256'] != block['glb_sha256']:
        block['metadata_sha_mismatch'] = True
    return block, position, yaw


def envelope(kind, source):
    return {'schema': SCHEMA, 'kind': kind, 'label': LABEL, 'native_verified': False, 'runtime_ready': False,
            'source': source, 'errors': []}


# ------------------------------------------------------------------ bed
def measure_bed(glb=None, meta=None, cfg=None) -> dict:
    glb, meta = Path(glb or ASSETS['bed']['glb']), Path(meta or ASSETS['bed']['meta'])
    cfg = dict(cfg or bed_audit.DEFAULT_CONFIG)
    source, position, yaw = source_block('bed', glb, meta)
    report = envelope('bed', source)
    report['rule'] = ('tools/unreal_bed_surface_audit.py mattress_top/duvet_top/head_end_direction on the material groups '
                      f'(mattress {cfg["mattress_material_regex"]!r}, pillows {cfg["pillow_material_regex"]!r}, '
                      f'duvet {cfg["duvet_material_regex"]!r}); min mattress area {MIN_MATTRESS_AREA_CM2:.0f} cm2')
    mattress, pillows, duvet, groups = [], [], [], []
    for group in load_groups(glb):
        names = [group['node'] or '', group['material'] or '']
        v, f, n = ue_group(group, position, yaw)
        row = {'node': group['node'], 'material': group['material'], 'vertices': len(v), 'triangles': len(f) // 3,
               'world_bounds_cm': {'min': np.min(v, 0).round(4).tolist(), 'max': np.max(v, 0).round(4).tolist()},
               'normal_agreement': normal_agreement(v, f, n)}
        groups.append(row)
        if bed_audit.material_identity(names, cfg['pillow_material_regex']):
            pillows.extend(v)
        if bed_audit.material_identity(names, cfg['duvet_material_regex']):
            top, why = bed_audit.duvet_top(v, f, cfg)
            duvet.append({'material': group['material'], 'top_surface': _summary(top), 'top_surface_refused': why})
        if bed_audit.material_identity(names, cfg['mattress_material_regex']):
            mattress.append((group, v, f))
    report['groups'] = groups
    if len(mattress) != 1:
        report['errors'].append(f'Expected ONE mattress material group, got {len(mattress)}')
        return report
    group, v, f = mattress[0]
    try:
        top = bed_audit.mattress_top(v, f, cfg)
        top['head_end_direction_xy'] = bed_audit.head_end_direction(top, pillows)
    except ValueError as error:
        report['errors'].append(str(error))
        return report
    report['mattress'] = {'material': group['material'], **_summary(top)}
    report['pillows'] = {'vertices': len(pillows), 'world_bounds_cm': {'min': np.min(pillows, 0).round(4).tolist(),
                                                                      'max': np.max(pillows, 0).round(4).tolist()} if pillows else None}
    report['duvet'] = duvet
    return report


def _summary(top):
    if top is None:
        return None
    out = {k: v for k, v in top.items() if k != 'triangle_indices'}
    out['triangle_count'] = len(top['triangle_indices'])
    return out


# ------------------------------------------------------------------ sofa
def measure_sofa(glb=None, meta=None, cfg=None, seat_node=SOFA_SEAT_NODE) -> dict:
    glb, meta = Path(glb or ASSETS['sofa']['glb']), Path(meta or ASSETS['sofa']['meta'])
    cfg = dict(cfg or sofa_audit.DEFAULT_CONFIG)
    source, position, yaw = source_block('sofa', glb, meta)
    report = envelope('sofa', source)
    report['rule'] = ('tools/unreal_sofa_surface_audit.py seat_surface on the %s group: mean vertex normal z > %.2f, '
                      'edge-connected, exposed, per-cushion exposed projected area >= %.0f cm2 (MIN_SEAT_AREA_CM2)'
                      % (seat_node, cfg['min_up_normal'], cfg['min_cushion_area_cm2']))
    groups, seat, footprint = [], [], []
    for group in load_groups(glb):
        v, f, n = ue_group(group, position, yaw)
        footprint.extend(v)
        groups.append({'node': group['node'], 'material': group['material'], 'vertices': len(v), 'triangles': len(f) // 3,
                       'world_bounds_cm': {'min': np.min(v, 0).round(4).tolist(), 'max': np.max(v, 0).round(4).tolist()},
                       'normal_agreement': normal_agreement(v, f, n)})
        if group['node'] == seat_node:
            seat.append((v, f, n))
    report['groups'] = groups
    report['footprint_world_bounds_cm'] = {'min': np.min(footprint, 0).round(4).tolist(), 'max': np.max(footprint, 0).round(4).tolist()}
    report['seat_identity_basis'] = f'glTF node name {seat_node} (sofa.glb has no material records; native uses the Haven_linen material)'
    if len(seat) != 1:
        report['errors'].append(f'Expected ONE {seat_node} group, got {len(seat)}')
        return report
    v, f, n = seat[0]
    try:
        surface = sofa_audit.seat_surface(v, f, n, cfg)
    except sofa_audit.SurfaceRefused as error:
        report['errors'].append(str(error))
        report['measured_surface'] = error.measured_surface
        return report
    report['seat'] = {k: val for k, val in surface.items() if k != 'triangle_indices'}
    report['seat']['triangle_count'] = len(surface['triangle_indices'])
    report['seat']['meets_controller_min_seat_area'] = surface['area_cm2'] >= MIN_SEAT_AREA_CM2
    return report


# ------------------------------------------------------------------ source vs native (deltas only)
def _vec_delta(a, b):
    return [round(float(y) - float(x), 4) for x, y in zip(a, b)]


def compare(source: dict, native: dict) -> dict:
    """Native minus source for the same rule's outputs. No tolerance for these deltas exists in the repository, so
    nothing is gated: the result only says whether both reports measured a surface and what the differences are.
    The existing area minimums (MIN_MATTRESS_AREA_CM2, MIN_SEAT_AREA_CM2) are re-stated, as each consumer gates them."""
    if source.get('schema') != SCHEMA or source.get('label') != LABEL:
        raise ValueError('not a source_measured support-surface report')
    kind = source['kind']
    out = {'schema': 'sub01.source-native-surface-comparison.v1', 'kind': kind, 'gated': False,
           'native_verified': False, 'source_glb_sha256': source['source']['glb_sha256'],
           'source_errors': source.get('errors'), 'native_errors': native.get('errors')}
    if source.get('errors') or native.get('errors') != []:
        out['comparable'] = False
        return out
    if kind == 'bed':
        s = source['mattress']
        n = native['bed']['sections'][0]['mattress_surface']
        minimum = MIN_MATTRESS_AREA_CM2
        out['deltas'] = {'area_cm2': round(n['area_cm2'] - s['area_cm2'], 3),
                         'top_z_cm': _vec_delta(s['top_z_cm'], n['top_z_cm']),
                         'centroid_xy_cm': _vec_delta(s['centroid_xy_cm'], n['centroid_xy_cm']),
                         'length_cm': round(n['length_cm'] - s['length_cm'], 3), 'width_cm': round(n['width_cm'] - s['width_cm'], 3),
                         'bounds_min_cm': _vec_delta(s['world_bounds_cm']['min'], n['world_bounds_cm']['min']),
                         'bounds_max_cm': _vec_delta(s['world_bounds_cm']['max'], n['world_bounds_cm']['max'])}
        sh, nh = s.get('head_end_direction_xy'), n.get('head_end_direction_xy')
        out['deltas']['head_end_angle_deg'] = (round(math.degrees(math.acos(max(-1., min(1., sh[0] * nh[0] + sh[1] * nh[1])))), 4)
                                               if sh and nh else None)
        out['source_area_cm2'], out['native_area_cm2'] = s['area_cm2'], n['area_cm2']
    else:
        s = source['seat']
        n = native['sofa']['sections'][0]['seat_surface']
        minimum = MIN_SEAT_AREA_CM2
        out['deltas'] = {'area_cm2': round(n['area_cm2'] - s['area_cm2'], 3),
                         'projected_area_cm2': round(n['projected_area_cm2'] - s['projected_area_cm2'], 3),
                         'top_z_cm': _vec_delta(s['top_z_cm'], n['top_z_cm']),
                         'cushion_count': len(n['cushions']) - len(s['cushions']),
                         'bounds_min_cm': _vec_delta(s['world_bounds_cm']['min'], n['world_bounds_cm']['min']),
                         'bounds_max_cm': _vec_delta(s['world_bounds_cm']['max'], n['world_bounds_cm']['max'])}
        out['cushions'] = [{'source_centroid_xy_cm': a.get('centroid_xy_cm'), 'native_centroid_xy_cm': b.get('centroid_xy_cm'),
                            'area_delta_cm2': round(b['exposed_projected_area_cm2'] - a['exposed_projected_area_cm2'], 3),
                            'top_delta_cm': round(b['top_z_cm'] - a['top_z_cm'], 4)}
                           for a, b in zip(sorted(s['cushions'], key=lambda c: c['centroid_xy_cm']),
                                           sorted(n['cushions'], key=lambda c: c['centroid_xy_cm']))]
        out['source_area_cm2'], out['native_area_cm2'] = s['area_cm2'], n['area_cm2']
    out['comparable'] = True
    out['both_meet_existing_area_minimum'] = out['source_area_cm2'] >= minimum and out['native_area_cm2'] >= minimum
    out['note'] = 'deltas = native - source; the source is the AUTHORED placement, so a placement offset shows here; not gated'
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = p.add_subparsers(dest='cmd', required=True)
    for kind in ('bed', 'sofa'):
        s = sub.add_parser(kind)
        s.add_argument('--glb', type=Path)
        s.add_argument('--meta', type=Path)
        s.add_argument('--out', type=Path)
    c = sub.add_parser('compare')
    c.add_argument('source', type=Path)
    c.add_argument('native', type=Path)
    c.add_argument('--out', type=Path)
    a = p.parse_args(argv)
    if a.cmd == 'compare':
        result = compare(json.loads(a.source.read_text()), json.loads(a.native.read_text()))
    else:
        result = (measure_bed if a.cmd == 'bed' else measure_sofa)(a.glb, a.meta)
    text = json.dumps(result, indent=2) + '\n'
    if getattr(a, 'out', None):
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text)
    print(text if not getattr(a, 'out', None) else a.out)
    return 0 if not result.get('errors') else 2


if __name__ == '__main__':
    sys.exit(main())
