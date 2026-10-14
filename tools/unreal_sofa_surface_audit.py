"""Read-only SERVER UE editor audit of the actual native sofa's seat cushions (the chair/bed audits' sofa twin).

    UnrealEditor-Cmd <project>/Sub01HomeLab.uproject -ExecutePythonScript="<repo>/tools/unreal_sofa_surface_audit.py" -unattended
    (optional) SUB01_SOFA_AUDIT_CONFIG=/srv/private/sofa-audit.json   overrides DEFAULT_CONFIG below

Pattern: tools/unreal_chair_surface_audit.py (official API: ProceduralMeshLibrary.get_section_from_static_mesh,
StaticMeshEditorSubsystem.get_lod_material_slot; imported vertex normals decide "upward", because UE's imported
winding is clockwise for upward faces - see tests/test_unreal_chair_surface_audit.py). Writes
<project>/private-audit/native-sofa-surface.json in the shape tools/unreal_controller_play_runtime.py
sofa_seat_triangles() reads:
    {"errors": [], "sofa": {"component": ..., "sections": [{"vertices_world_cm": [...],
                                                             "seat_surface": {"triangle_indices": [[i,j,k], ...]}}]}}
plus each measured cushion (area, top, bounds, centroid), the rejected upward patches and the component's world
bounds (the footprint the controller evidence's capsule clearance needs). No mesh, collision or actor is edited;
nothing here accepts a seating, a placement or a contact.

Identity: the ONE component whose sections carry the Haven linen upholstery (tools/build_home_haven_sofa.py merges
the 'Oatmeal' source objects into Haven_linen; the native import names its material Material_Haven_linen). When any
component carries the device tag (DEFAULT_CONFIG['device_tag']) only tagged components are considered; with
'require_tag': true an untagged home is refused. root's tools/unreal_setup_home.py does not tag a sofa today.

Seat rule (pure Python, shared with tools/measure_source_support_surface.py so the source and native measurements
are the same rule):
  1. upward triangles: mean imported vertex normal z > 0.65 (the chair audit's literal; the sofa spec in
     docs/proposed/sofa-controller-play.md section 4) - cross-product normal only when no normals are given;
  2. edge-connected patches after welding coincident seam vertices (the chair audit's rule);
  3. EXPOSED triangles only: a triangle whose centroid has another triangle of the same component above it is
     covered (e.g. the seat deck under the loose cushions) and is not a support;
  4. a seat cushion is a patch whose exposed projected area is >= MIN_SEAT_AREA_CM2 (imported from the controller
     adapter: "the two authored seat cushions are ~5,800 cm2 each; an arm top is not a seat").

NOT RUN in this repository (no engine here). The pure helpers below are tested on synthetic geometry.
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from unreal_controller_play_runtime import MIN_SEAT_AREA_CM2, SOFA_REPORT  # noqa: E402  (read-only import: 4000 cm2)

SCHEMA = 'sub01.native-sofa-surface.v1'
UP_NORMAL_MIN = 0.65                 # tools/unreal_chair_surface_audit.py cushion_top literal (up > .65)
WELD_DECIMALS = 5                    # tools/unreal_chair_surface_audit.py weld rounding
COVER_EPS_CM = 1e-4                  # numeric only: a coincident duplicate face does not "cover" its twin
GRID_CM = 10.0                       # acceleration grid cell for the cover test (no effect on the result)
DEFAULT_CONFIG = {
    'device_tag': 'SUB01Device:Sofa',
    'require_tag': False,
    'seat_material_regex': r'haven[ _-]?linen|oatmeal',
    'min_up_normal': UP_NORMAL_MIN,
    'min_cushion_area_cm2': MIN_SEAT_AREA_CM2,
}


class SurfaceRefused(ValueError):
    """A refusal that carries what WAS measured (written into the report, never silently dropped)."""

    def __init__(self, message, measured=None):
        super().__init__(message)
        self.measured_surface = measured


# ------------------------------------------------------------------ validation and triangle geometry
def check_geometry(vertices, indices, normals=None):
    if not vertices or not indices or len(indices) % 3:
        raise ValueError('Missing/invalid real section triangles')
    if any(len(v) != 3 or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in v) for v in vertices):
        raise ValueError('Nonfinite world geometry')
    if any(isinstance(i, bool) or not isinstance(i, int) or i < 0 or i >= len(vertices) for i in indices):
        raise ValueError('Invalid actual section index')
    if normals is not None and (len(normals) != len(vertices)
                                or any(len(n) != 3 or not all(math.isfinite(x) for x in n) for n in normals)):
        raise ValueError('Invalid actual section normals')


def _cross(a, b, c):
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    return [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]


def triangle_rows(vertices, indices, normals=None):
    """Per triangle: (ids, up, projected area, surface area). `up` is the mean imported vertex normal z when
    normals are given (the chair audit's rule for UE's clockwise import), else the unit cross-product z."""
    rows = []
    for j in range(0, len(indices), 3):
        ids = list(indices[j:j + 3])
        a, b, c = (vertices[i] for i in ids)
        n = _cross(a, b, c)
        length = math.sqrt(sum(x * x for x in n))
        if normals is not None:
            up = sum(normals[i][2] for i in ids) / 3
        else:
            up = n[2] / length if length else 0.0
        rows.append((ids, up if length else 0.0, abs(n[2]) / 2, length / 2))
    return rows


def upward_patches(vertices, indices, normals=None, min_up=UP_NORMAL_MIN):
    """Edge-connected patches of upward triangles (welded seams; a shared corner never joins two patches)."""
    rows = triangle_rows(vertices, indices, normals)
    selected = [t for t, row in enumerate(rows) if row[3] > 0 and row[1] > min_up]
    welded = [tuple(round(x, WELD_DECIMALS) for x in p) for p in vertices]
    parent = list(range(len(selected)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    edges = {}
    for k, t in enumerate(selected):
        ids = rows[t][0]
        for a, b in zip(ids, ids[1:] + ids[:1]):
            key = tuple(sorted((welded[a], welded[b])))
            if key in edges:
                parent[find(k)] = find(edges[key])
            else:
                edges[key] = k
    groups = {}
    for k, t in enumerate(selected):
        groups.setdefault(find(k), []).append(t)
    return rows, [sorted(g) for g in groups.values()]


class CoverGrid:
    """All triangles of a component binned on an XY grid: is there geometry ABOVE a point?"""

    def __init__(self, vertices, indices, cell=GRID_CM):
        self.v, self.cell, self.bins = vertices, cell, {}
        self.tris = [tuple(indices[j:j + 3]) for j in range(0, len(indices), 3)]
        for t, ids in enumerate(self.tris):
            xs = [vertices[i][0] for i in ids]
            ys = [vertices[i][1] for i in ids]
            for gx in range(int(math.floor(min(xs) / cell)), int(math.floor(max(xs) / cell)) + 1):
                for gy in range(int(math.floor(min(ys) / cell)), int(math.floor(max(ys) / cell)) + 1):
                    self.bins.setdefault((gx, gy), []).append(t)

    def covered(self, point, skip):
        x, y, z = point
        for t in self.bins.get((int(math.floor(x / self.cell)), int(math.floor(y / self.cell))), ()):
            if t == skip:
                continue
            a, b, c = (self.v[i] for i in self.tris[t])
            det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(det) < 1e-12:
                continue
            l1 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / det
            l2 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / det
            l3 = 1 - l1 - l2
            if l1 < -1e-9 or l2 < -1e-9 or l3 < -1e-9:
                continue
            if l1 * a[2] + l2 * b[2] + l3 * c[2] > z + COVER_EPS_CM:
                return True
        return False


def _bounds(points):
    return {'min': [min(p[i] for p in points) for i in range(3)], 'max': [max(p[i] for p in points) for i in range(3)]}


def _centroid_xy(vertices, rows, tris):
    total = sum(rows[t][2] for t in tris) or 1.0
    cx = sum(sum(vertices[i][0] for i in rows[t][0]) / 3 * rows[t][2] for t in tris) / total
    cy = sum(sum(vertices[i][1] for i in rows[t][0]) / 3 * rows[t][2] for t in tris) / total
    return [round(cx, 3), round(cy, 3)]


def seat_surface(vertices, indices, normals=None, cfg=DEFAULT_CONFIG, cover_indices=None):
    """Exposed, broad, upward cushion tops of one actual sofa mesh (world cm, Z up). Raises SurfaceRefused.

    cover_indices: every triangle of the SAME component (all sections) for the cover test; default `indices`.
    """
    check_geometry(vertices, indices, normals)
    rows, patches = upward_patches(vertices, indices, normals, cfg['min_up_normal'])
    if not patches:
        raise SurfaceRefused('No actual upward-facing sofa upholstery triangles', {'patches': []})
    grid = CoverGrid(vertices, list(cover_indices) if cover_indices is not None else list(indices))
    measured = []
    for tris in patches:
        exposed = [t for t in tris if not grid.covered([sum(vertices[i][k] for i in rows[t][0]) / 3 for k in range(3)], t)]
        pts = [vertices[i] for t in tris for i in rows[t][0]]
        exp_pts = [vertices[i] for t in exposed for i in rows[t][0]]
        measured.append({
            'triangles': tris, 'exposed_triangles': exposed,
            'projected_area_cm2': round(sum(rows[t][2] for t in tris), 3),
            'exposed_projected_area_cm2': round(sum(rows[t][2] for t in exposed), 3),
            'exposed_surface_area_cm2': round(sum(rows[t][3] for t in exposed), 3),
            'world_bounds_cm': _bounds(pts),
            'exposed_bounds_cm': _bounds(exp_pts) if exp_pts else None,
            'top_z_cm': max(p[2] for p in pts),
            'centroid_xy_cm': _centroid_xy(vertices, rows, exposed) if exposed else None,
            'mean_up_normal': round(sum(rows[t][1] for t in tris) / len(tris), 6)})
    measured.sort(key=lambda p: p['exposed_projected_area_cm2'], reverse=True)
    summary = [{k: v for k, v in p.items() if k not in ('triangles', 'exposed_triangles')} | {'triangle_count': len(p['triangles'])}
               for p in measured]
    cushions = [p for p in measured if p['exposed_projected_area_cm2'] >= cfg['min_cushion_area_cm2']]
    if not cushions:
        raise SurfaceRefused(f'No exposed upward patch >= {cfg["min_cushion_area_cm2"]:.0f} cm2: not a sofa seat', {'patches': summary})
    faces = [rows[t][0] for p in cushions for t in p['exposed_triangles']]
    pts = [vertices[i] for f in faces for i in f]
    return {
        'triangle_indices': [list(f) for f in faces],
        'area_cm2': round(sum(rows[t][3] for p in cushions for t in p['exposed_triangles']), 3),
        'projected_area_cm2': round(sum(p['exposed_projected_area_cm2'] for p in cushions), 3),
        'top_z_cm': [round(min(p[2] for p in pts), 3), round(max(p[2] for p in pts), 3)],
        'world_bounds_cm': _bounds(pts),
        'cushions': [{k: v for k, v in p.items() if k not in ('triangles', 'exposed_triangles')} | {'triangle_count': len(p['exposed_triangles'])}
                     for p in cushions],
        'patches': summary,
        'selection': ('upward (mean vertex normal z > %.2f) edge-connected upholstery patches, exposed triangles only '
                      '(nothing of the component above the centroid), exposed projected area >= %.0f cm2 per cushion; '
                      'not a replacement box' % (cfg['min_up_normal'], cfg['min_cushion_area_cm2'])),
        'collision_trace_verified': False}


def material_identity(names, regex):
    return any(re.search(regex, str(n), re.I) for n in names)


def choose_component(candidates, cfg=DEFAULT_CONFIG):
    """candidates: [{'tags': [...], 'seat_sections': int, ...}] for every StaticMeshComponent with seat upholstery.
    Exactly ONE is accepted; tags narrow (or, with require_tag, are mandatory). Raises otherwise."""
    tagged = [c for c in candidates if cfg['device_tag'] in c.get('tags', [])]
    if cfg.get('require_tag') and not tagged:
        raise ValueError(f'No component tagged {cfg["device_tag"]}; the sofa audit is configured to require the tag')
    pool = tagged or [c for c in candidates if c.get('seat_sections')]
    pool = [c for c in pool if c.get('seat_sections')]
    if len(pool) != 1:
        raise ValueError(f'Expected ONE real sofa upholstery component, got {len(pool)}; no ambiguous or name-only sofa acceptance')
    return pool[0], ('device tag ' + cfg['device_tag']) if tagged else 'seat material identity ' + cfg['seat_material_regex']


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    path = os.environ.get('SUB01_SOFA_AUDIT_CONFIG')
    if path:
        cfg.update(json.loads(Path(path).read_text()))
    return cfg


def run():  # pragma: no cover - server only (Unreal Editor Python)
    import unreal as u
    cfg = load_config()
    root = Path(u.Paths.project_dir()).resolve()
    out = root / 'private-audit' / SOFA_REPORT
    out.parent.mkdir(parents=True, exist_ok=True)
    report = {'schema': SCHEMA, 'level': '/Game/Sub01Home/ActualHome', 'config': cfg, 'runtime_ready': False,
              'physical_seating_verified': False, 'errors': [], 'candidate_sections': []}
    try:
        level = u.get_editor_subsystem(u.LevelEditorSubsystem)
        if not level.load_level(report['level']):
            raise RuntimeError('Existing ActualHome map unavailable')
        if not hasattr(u, 'ProceduralMeshLibrary'):
            raise RuntimeError('Official ProceduralMeshComponent editor API not loaded; no bounds-only fallback is accepted')
        editor = u.get_editor_subsystem(u.StaticMeshEditorSubsystem) or u.StaticMeshEditorSubsystem()
        candidates = []
        for actor in u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors():
            for component in actor.get_components_by_class(u.StaticMeshComponent):
                mesh = component.get_editor_property('static_mesh')
                if not mesh:
                    continue
                tags = [str(t) for t in component.get_editor_property('component_tags')]
                slots = list(mesh.get_editor_property('static_materials'))
                transform = component.get_world_transform()
                points, normals, all_indices, seat = [], [], [], []
                for section in range(mesh.get_num_sections(0)):
                    slot = editor.get_lod_material_slot(mesh, 0, section)
                    material = component.get_material(slot)
                    names = [str(slots[slot].material_slot_name), str(getattr(slots[slot], 'imported_material_slot_name', '')),
                             material.get_name() if material else '', material.get_path_name() if material else '']
                    is_seat = material_identity(names, cfg['seat_material_regex'])
                    if not is_seat and cfg['device_tag'] not in tags:
                        continue
                    local, indices, local_normals, *_ = u.ProceduralMeshLibrary.get_section_from_static_mesh(mesh, 0, section)
                    base = len(points)
                    for p in local:
                        q = transform.transform_location(p)
                        points.append([float(q.x), float(q.y), float(q.z)])
                    for n in local_normals:
                        q = u.MathLibrary.transform_direction(transform, n)
                        normals.append([float(q.x), float(q.y), float(q.z)])
                    shifted = [base + int(i) for i in indices]
                    all_indices.extend(shifted)
                    if is_seat:
                        if material is None:
                            raise RuntimeError('Sofa upholstery section has no actual assigned material')
                        seat.append({'lod': 0, 'section': section, 'material_slot': slot, 'material_identity': names, 'indices': shifted})
                if not seat and cfg['device_tag'] not in tags:
                    continue
                lo, hi = component.get_local_bounds()
                corners = [transform.transform_location(u.Vector(x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
                loc, rot, scale = transform.translation, transform.rotation, transform.scale3d
                candidates.append({'tags': tags, 'seat_sections': len(seat), 'actor': actor.get_path_name(), 'component': component.get_path_name(),
                                   'mesh': mesh.get_path_name(), '_component': component, '_points': points, '_normals': normals,
                                   '_indices': all_indices, '_seat': seat,
                                   'transform': {'translation_cm': [loc.x, loc.y, loc.z], 'rotation_xyzw': [rot.x, rot.y, rot.z, rot.w],
                                                 'scale': [scale.x, scale.y, scale.z]},
                                   'component_world_bounds_cm': {'min': [min(getattr(v, k) for v in corners) for k in 'xyz'],
                                                                 'max': [max(getattr(v, k) for v in corners) for k in 'xyz']}})
        chosen, basis = choose_component(candidates, cfg)
        component = chosen['_component']
        if component.get_collision_enabled() == u.CollisionEnabled.NO_COLLISION:
            raise RuntimeError('Real sofa component collision disabled')
        if component.get_collision_response_to_channel(u.CollisionChannel.ECC_PAWN) != u.CollisionResponseType.ECR_BLOCK:
            raise RuntimeError('Sofa does not block the actual pawn')
        seat_indices = [i for s in chosen['_seat'] for i in s['indices']]
        try:
            surface = seat_surface(chosen['_points'], seat_indices, chosen['_normals'], cfg, cover_indices=chosen['_indices'])
        except SurfaceRefused as error:
            report['candidate_sections'].append({'component': chosen['component'], 'measured_surface': error.measured_surface,
                                                 'surface_rejection': str(error)})
            raise
        # One section entry carrying the component's world vertices: triangle indices refer to it.
        sofa = {k: v for k, v in chosen.items() if not k.startswith('_')}
        sofa.update({'identity_basis': basis, 'collision_profile': str(component.get_collision_profile_name()),
                     'collision_enabled': str(component.get_collision_enabled()),
                     'seat_material_sections': [{k: v for k, v in s.items() if k != 'indices'} for s in chosen['_seat']],
                     'sections': [{'lod': 0, 'vertices_world_cm': chosen['_points'], 'triangles': seat_indices, 'seat_surface': surface}]})
        report.update({'sofa': sofa, 'seat_measured': True, 'continuous_skin_cushion_contact_verified': False})
    except Exception as exc:
        report['errors'].append(str(exc))
        out.write_text(json.dumps(report, indent=2) + '\n')
        raise
    out.write_text(json.dumps(report, indent=2) + '\n')
    u.log('SUB01_SOFA_SURFACE_AUDIT ' + str(out))


if __name__ == '__main__':
    run()
