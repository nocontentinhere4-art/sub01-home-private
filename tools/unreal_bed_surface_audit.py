"""Read-only SERVER UE editor audit of the actual native bed's mattress top (the chair audit's bed twin).

    UnrealEditor-Cmd <project>/Sub01HomeLab.uproject -ExecutePythonScript="<repo>/tools/unreal_bed_surface_audit.py" -unattended
    (optional) SUB01_BED_AUDIT_CONFIG=/srv/private/bed-audit.json   overrides DEFAULT_CONFIG below

Pattern: tools/unreal_chair_surface_audit.py. Official API: ProceduralMeshLibrary.get_section_from_static_mesh,
StaticMeshEditorSubsystem.get_lod_material_slot. Writes <project>/private-audit/native-bed-surface.json in the
shape tools/unreal_life_clips_runtime.py validate_bed() reads:
    {"errors": [], "bed": {"component": ..., "sections": [{"vertices_world_cm": [...],
                                                            "mattress_surface": {"triangle_indices": [[i,j,k], ...]}}]}}
plus the measured top, area, long axis, head-end direction and the duvet/pillow overlap. No mesh, collision or
actor is edited; nothing here accepts a placement (native-life-bed-evidence.json is written only by the placement
audit after measuring the imported clips' skin on this exact report).

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
from unreal_life_clips_runtime import MIN_MATTRESS_AREA_CM2  # noqa: E402  (read-only import: 15,000 cm2)

SCHEMA = 'sub01.native-bed-surface.v1'
# The native bed is the CC0 Innerscene queen bed (tools/stage_unreal_home.py ASSETS; components tagged
# SUB01Device:Bed by tools/unreal_setup_home.py). Its prepared materials (web/house/assets/cc0-queen-bed/queen-bed.glb)
# are 'Original walnut grain', 'Original teal upholstery', 'Original cream upholstery', 'Original linen upholstery',
# 'Original blue_fabric upholstery', 'Original oak grain'. In the asset, accessor bounds put the cream group at
# 0.38-0.60 m (mattress), linen at the -Z end 0.55-0.77 m (pillows), blue_fabric 0.51-0.70 m over most of the
# length (duvet). These are file facts, NOT a measurement of the native placement; the audit measures.
DEFAULT_CONFIG = {
    'device_tag': 'SUB01Device:Bed',
    'mattress_material_regex': r'cream[ _]?upholstery',
    'pillow_material_regex': r'linen[ _]?upholstery',
    'duvet_material_regex': r'blue[ _]?fabric',
    'min_up_normal': 0.9,          # |n_z| of a top triangle
    'top_band_cm': 4.0,            # triangles within this of the highest top point (crowned mattress)
    'min_area_cm2': MIN_MATTRESS_AREA_CM2,
}


def tri_normal(a, b, c):
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
    length = math.sqrt(sum(x * x for x in n))
    return n, length


def mattress_top(vertices, indices, cfg=DEFAULT_CONFIG):
    """Upward top triangles of one actual mattress section (world cm, Z up). Raises when it is not a bed top."""
    if not vertices or len(indices) % 3:
        raise ValueError('Missing/invalid real section triangles')
    if any(len(v) != 3 or not all(math.isfinite(x) for x in v) for v in vertices):
        raise ValueError('Nonfinite world geometry')
    if any(isinstance(i, bool) or not isinstance(i, int) or i < 0 or i >= len(vertices) for i in indices):
        raise ValueError('Invalid actual section index')
    up = []
    for j in range(0, len(indices), 3):
        ids = indices[j:j + 3]
        a, b, c = (vertices[i] for i in ids)
        n, length = tri_normal(a, b, c)
        if length and n[2] / length >= cfg['min_up_normal']:
            up.append((ids, (a[2] + b[2] + c[2]) / 3, length / 2))
    if not up:
        raise ValueError('No upward mattress triangles')
    top = max(z for _, z, _ in up)
    selected = [(ids, area) for ids, z, area in up if z >= top - cfg['top_band_cm']]
    area = sum(a for _, a in selected)
    if area < cfg['min_area_cm2']:
        raise ValueError(f'Mattress top {area:.0f} cm2 < {cfg["min_area_cm2"]:.0f} cm2: not a bed (pillow/rail?)')
    pts = [vertices[i] for ids, _ in selected for i in ids]
    frame = surface_frame([(ids, a) for ids, a in selected], vertices)
    return {'triangle_indices': [list(ids) for ids, _ in selected], 'area_cm2': round(area, 3),
            'top_z_cm': [round(min(p[2] for p in pts), 3), round(max(p[2] for p in pts), 3)],
            'world_bounds_cm': {'min': [min(p[i] for p in pts) for i in range(3)], 'max': [max(p[i] for p in pts) for i in range(3)]},
            **frame,
            'selection': 'actual mattress-material upward triangles (|n_z| >= %.2f) within %.1f cm of the highest top '
                         'point; not a replacement box' % (cfg['min_up_normal'], cfg['top_band_cm']),
            'collision_trace_verified': False}


def surface_frame(selected, vertices):
    """Area-weighted centroid and principal axes (XY) of a set of triangles (exact second moments of the
    triangle areas, so shared or repeated vertices do not bias the axis): long axis, width and length."""
    cx = cy = total = 0.0
    for ids, area in selected:
        a, b, c = (vertices[i] for i in ids)
        cx += (a[0] + b[0] + c[0]) / 3 * area
        cy += (a[1] + b[1] + c[1]) / 3 * area
        total += area
    cx, cy = cx / total, cy / total
    sxx = syy = sxy = 0.0
    for ids, area in selected:
        d = [(vertices[i][0] - cx, vertices[i][1] - cy) for i in ids]
        s0, s1 = sum(p[0] for p in d), sum(p[1] for p in d)
        sxx += area / 12 * (sum(p[0] * p[0] for p in d) + s0 * s0)
        syy += area / 12 * (sum(p[1] * p[1] for p in d) + s1 * s1)
        sxy += area / 12 * (sum(p[0] * p[1] for p in d) + s0 * s1)
    theta = 0.5 * math.atan2(2 * sxy, sxx - syy)
    ax = (math.cos(theta), math.sin(theta))
    pts = [vertices[i] for ids, _ in selected for i in ids]
    along = [p[0] * ax[0] + p[1] * ax[1] for p in pts]
    across = [-p[0] * ax[1] + p[1] * ax[0] for p in pts]
    length, width = max(along) - min(along), max(across) - min(across)
    if width > length:                       # make the long axis the long one
        ax = (-ax[1], ax[0])
        length, width = width, length
    return {'centroid_xy_cm': [round(cx, 3), round(cy, 3)], 'long_axis_xy': [round(ax[0], 6), round(ax[1], 6)],
            'length_cm': round(length, 3), 'width_cm': round(width, 3)}


def head_end_direction(mattress: dict, pillow_points):
    """The long-axis direction pointing to the head end: toward the pillows' centroid. None without pillows."""
    if not pillow_points:
        return None
    px = sum(p[0] for p in pillow_points) / len(pillow_points)
    py = sum(p[1] for p in pillow_points) / len(pillow_points)
    cx, cy = mattress['centroid_xy_cm']
    ax = mattress['long_axis_xy']
    s = (px - cx) * ax[0] + (py - cy) * ax[1]
    if abs(s) < 10:
        raise ValueError('Pillows are not toward one end of the mattress; head end ambiguous')
    return [ax[0] if s > 0 else -ax[0], ax[1] if s > 0 else -ax[1]]


def material_identity(names, regex):
    return any(re.search(regex, str(n), re.I) for n in names)


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    path = os.environ.get('SUB01_BED_AUDIT_CONFIG')
    if path:
        cfg.update(json.loads(Path(path).read_text()))
    return cfg


def run():  # pragma: no cover - server only (Unreal Editor Python)
    import unreal as u
    cfg = load_config()
    root = Path(u.Paths.project_dir()).resolve()
    out = root / 'private-audit/native-bed-surface.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    report = {'schema': SCHEMA, 'level': '/Game/Sub01Home/ActualHome', 'config': cfg, 'runtime_ready': False,
              'placement_verified': False, 'errors': []}
    try:
        level = u.get_editor_subsystem(u.LevelEditorSubsystem)
        if not level.load_level(report['level']):
            raise RuntimeError('Existing ActualHome map unavailable')
        if not hasattr(u, 'ProceduralMeshLibrary'):
            raise RuntimeError('Official ProceduralMeshComponent editor API not loaded; no bounds-only fallback is accepted')
        editor = u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
        actors = u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()
        matches, pillows, duvet = [], [], []
        for actor in actors:
            for component in actor.get_components_by_class(u.StaticMeshComponent):
                tags = [str(t) for t in component.get_editor_property('component_tags')]
                if cfg['device_tag'] not in tags:
                    continue
                mesh = component.get_editor_property('static_mesh')
                if not mesh:
                    continue
                slots = list(mesh.get_editor_property('static_materials'))
                transform = component.get_world_transform()
                sections = []
                for section in range(mesh.get_num_sections(0)):
                    slot = editor.get_lod_material_slot(mesh, 0, section)
                    material = component.get_material(slot)
                    names = [str(slots[slot].material_slot_name), str(slots[slot].imported_material_slot_name),
                             material.get_name() if material else '', material.get_path_name() if material else '']
                    local, indices, *_ = u.ProceduralMeshLibrary.get_section_from_static_mesh(mesh, 0, section)
                    points = []
                    for p in local:
                        q = transform.transform_location(p)
                        points.append([float(q.x), float(q.y), float(q.z)])
                    if material_identity(names, cfg['pillow_material_regex']):
                        pillows.extend(points)
                    if material_identity(names, cfg['duvet_material_regex']):
                        duvet.append({'section': section, 'material_identity': names,
                                      'world_bounds_cm': {'min': [min(p[i] for p in points) for i in range(3)],
                                                          'max': [max(p[i] for p in points) for i in range(3)]}})
                    if not material_identity(names, cfg['mattress_material_regex']):
                        continue
                    if material is None:
                        raise RuntimeError('Mattress section has no actual assigned material')
                    surface = mattress_top(points, list(indices), cfg)
                    sections.append({'lod': 0, 'section': section, 'material_slot': slot, 'material_identity': names,
                                     'vertices_world_cm': points, 'triangles': list(indices), 'mattress_surface': surface})
                if sections:
                    if component.get_collision_enabled() == u.CollisionEnabled.NO_COLLISION:
                        raise RuntimeError('Real bed component collision disabled')
                    loc, rot, scale = transform.translation, transform.rotation, transform.scale3d
                    matches.append({'actor': actor.get_path_name(), 'component': component.get_path_name(),
                                    'mesh': mesh.get_path_name(),
                                    'transform': {'translation_cm': [loc.x, loc.y, loc.z], 'rotation_xyzw': [rot.x, rot.y, rot.z, rot.w],
                                                  'scale': [scale.x, scale.y, scale.z]},
                                    'collision_profile': str(component.get_collision_profile_name()),
                                    'pawn_response': str(component.get_collision_response_to_channel(u.CollisionChannel.ECC_PAWN)),
                                    'sections': sections})
        if len(matches) != 1 or len(matches[0]['sections']) != 1:
            raise RuntimeError(f'Expected ONE mattress section on ONE tagged bed component, got {len(matches)} components; '
                               'no ambiguous or name-only bed acceptance')
        surface = matches[0]['sections'][0]['mattress_surface']
        surface['head_end_direction_xy'] = head_end_direction(surface, pillows)
        report.update({'bed': matches[0], 'duvet_sections': duvet,
                       'open_requirements': [
                           'approach side (which long edge he walks to) is a placement decision, recorded in the evidence',
                           'the duvet is a rigid mesh over the mattress: the lying body under it intersects it unless it '
                           'is hidden, swapped or deformed while he sleeps (the web room built its duvet over his skin)',
                           'collision: the capsule cannot move onto the mattress by walking; see docs/proposed/bed-transition-pipeline.md'],
                       'mattress_measured': True, 'physical_lying_verified': False})
    except Exception as exc:
        report['errors'].append(str(exc))
        out.write_text(json.dumps(report, indent=2) + '\n')
        raise
    out.write_text(json.dumps(report, indent=2) + '\n')
    u.log('SUB01_BED_SURFACE_AUDIT ' + str(out))


if __name__ == '__main__':
    run()
