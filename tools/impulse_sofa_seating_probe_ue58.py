"""Read-only Muuto Rest geometry probe. Renderer calls run(request) in warm Editor.

No actor writes, asset saves, console commands or automatic seating acceptance.
Request must pin exact labels/paths, source hash and explicit triangle selections.
"""
import hashlib
import json
import math

SOURCE_SHA256 = '286115af3c6dc71f679f34bca3d639d2689df7cd377053893189ae1651dc0b4e'
LABELS = {'SUB01_GenuineMuutoRest_MuutoRest_000', 'SUB01_GenuineMuutoRest_MuutoRest_001'}


def vector(value):
    return [float(getattr(value, axis)) for axis in ('x', 'y', 'z')]


def transform(value):
    q = value.rotation
    return {'translation': vector(value.translation), 'rotation_xyzw': [float(getattr(q, a)) for a in ('x', 'y', 'z', 'w')], 'scale': vector(value.scale3d)}


def validate_request(request):
    if request.get('source_sha256') != SOURCE_SHA256:
        raise ValueError('Actual Muuto source SHA required')
    actors = request.get('actors', {})
    if set(actors) != LABELS or any(not isinstance(p, str) or not p for p in actors.values()) or len(set(actors.values())) != 2:
        raise ValueError('Pin both exact distinct Muuto actor labels and object paths')
    floors = request.get('floor_components', [])
    if not isinstance(floors, list):
        raise ValueError('floor_components must be an explicit list')
    seen = set()
    for floor in floors:
        if not isinstance(floor, dict) or any(not isinstance(floor.get(k), str) or not floor[k] for k in ('actor', 'component', 'mesh')):
            raise ValueError('Pin exact floor actor, component and mesh object paths')
        if floor['component'] in seen:
            raise ValueError('Duplicate pinned floor component')
        seen.add(floor['component'])
    for field in ('seat_triangle_indices', 'floor_triangle_indices'):
        selections = request.get(field, {})
        if not isinstance(selections, dict) or any(not isinstance(k, str) or not isinstance(v, list) or any(isinstance(i, bool) or not isinstance(i, int) or i < 0 for i in v) or len(v) != len(set(v)) for k,v in selections.items()):
            raise ValueError('Explicit unique nonnegative triangle ordinals required')
    for sample in request.get('collision_samples', []):
        if not isinstance(sample.get('id'), str) or not sample['id']:
            raise ValueError('Sample ID required')
        for key in ('start_cm', 'end_cm'):
            v = sample.get(key)
            if not isinstance(v, list) or len(v) != 3 or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in v):
                raise ValueError('Finite explicit world trace endpoints required')
    return request


def extract_sections(u, component, selections, surface_name):
    """Extract actual component triangles; selections are reviewed triangle ordinals."""
    mesh = component.get_editor_property('static_mesh')
    result = []
    for section in range(mesh.get_num_sections(0)):
        vertices, indices, *_ = u.ProceduralMeshLibrary.get_section_from_static_mesh(mesh, 0, section)
        points = [vector(component.get_world_transform().transform_location(v)) for v in vertices]
        triangles = [list(indices[k:k+3]) for k in range(0, len(indices), 3)]
        identity = component.get_path_name() + ':' + str(section)
        selected = selections.get(identity, [])
        if any(not 0 <= i < len(triangles) for i in selected):
            raise ValueError('Reviewed triangle ordinal outside actual native section: ' + identity)
        result.append({'component': component.get_path_name(), 'mesh': mesh.get_path_name(), 'lod': 0, 'section': section,
            'vertices_world_cm': points, 'triangles': triangles, surface_name: {'triangle_indices': [triangles[i] for i in selected],
            'selection': 'caller-reviewed actual mesh triangles; not contact verification'}})
    return result


def run(request):
    validate_request(request)
    import unreal as u
    actors = list(u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors())
    report = {'schema': 'sub01.impulse.muuto-seat-probe.v1', 'source_sha256': SOURCE_SHA256,
              'world': u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world().get_path_name(),
              'read_only': True, 'errors': [], 'sofa': {'sections': []}, 'floor': {'sections': [], 'components': []}, 'actors': [], 'collision_samples': [],
              'native_seat_verified': False, 'approach_verified': False, 'animated_contacts_verified': False,
              'source_bytes_rehashed': False, 'source_identity_evidence': 'caller SHA plus imported mesh namespace; renderer must bind native import receipt'}
    for label, path in request['actors'].items():
        matches = [a for a in actors if a.get_actor_label() == label]
        if len(matches) != 1 or matches[0].get_path_name() != path:
            raise ValueError('Ambiguous or changed Muuto actor: ' + label)
        actor = matches[0]
        components = actor.get_components_by_class(u.StaticMeshComponent)
        if len(components) != 1:
            raise ValueError('Expected one actual mesh component: ' + label)
        c = components[0]
        mesh = c.get_editor_property('static_mesh')
        if not mesh or not mesh.get_path_name().startswith('/Game/Sub01Home/GenuineMuutoRest/V_' + SOURCE_SHA256[:12] + '/'):
            raise ValueError('Muuto mesh provenance path mismatch')
        origin, extent, radius = u.SystemLibrary.get_component_bounds(c)
        row = {'label': label, 'actor': path, 'hidden_in_game': bool(actor.get_editor_property('hidden')), 'editor_hidden': bool(actor.is_temporarily_hidden_in_editor()), 'actor_transform': transform(actor.get_actor_transform()),
               'component': c.get_path_name(), 'component_transform': transform(c.get_world_transform()),
               'mesh': mesh.get_path_name(), 'bounds_world_cm': {'origin': vector(origin), 'extent': vector(extent), 'radius': float(radius)},
               'collision_profile': str(c.get_collision_profile_name()), 'collision_enabled': str(c.get_collision_enabled())}
        try:
            row['import_source_files'] = list(mesh.get_editor_property('asset_import_data').extract_filenames())
        except Exception as error:
            row['import_source_unavailable'] = str(error)
        report['actors'].append(row)
        report['sofa']['sections'].extend(extract_sections(u, c, request.get('seat_triangle_indices', {}), 'seat_surface'))
    for pin in request.get('floor_components', []):
        try:
            matches = [a for a in actors if a.get_path_name() == pin['actor']]
            if len(matches) != 1:
                raise ValueError('Missing or ambiguous pinned floor actor')
            actor = matches[0]
            components = [c for c in actor.get_components_by_class(u.StaticMeshComponent) if c.get_path_name() == pin['component']]
            if len(components) != 1:
                raise ValueError('Missing or ambiguous pinned floor component')
            c = components[0]
            mesh = c.get_editor_property('static_mesh')
            if not mesh or mesh.get_path_name() != pin['mesh']:
                raise ValueError('Pinned floor mesh identity changed')
            sections = extract_sections(u, c, request.get('floor_triangle_indices', {}), 'floor_surface')
            report['floor']['components'].append({'actor': pin['actor'], 'component': pin['component'], 'mesh': pin['mesh'],
                'actor_transform': transform(actor.get_actor_transform()), 'component_transform': transform(c.get_world_transform()),
                'hidden_in_game': bool(actor.get_editor_property('hidden')), 'collision_profile': str(c.get_collision_profile_name()),
                'collision_enabled': str(c.get_collision_enabled())})
            report['floor']['sections'].extend(sections)
        except Exception as error:
            report['errors'].append('Floor probe refused ' + pin['component'] + ': ' + str(error))
    if not any(s['floor_surface']['triangle_indices'] for s in report['floor']['sections']):
        report['errors'].append('Actual floor components and reviewed floor triangles required; no floor plane inferred')
    for sample in request.get('collision_samples', []):
        channel = getattr(u.TraceTypeQuery, request['trace_type_query'])
        hit_ok, hit = u.SystemLibrary.line_trace_single(u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world(),
            u.Vector(*sample['start_cm']), u.Vector(*sample['end_cm']), channel, True, [], u.DrawDebugTrace.NONE, False)
        values = u.GameplayStatics.break_hit_result(hit)
        report['collision_samples'].append({'id': sample['id'], 'start_cm': sample['start_cm'], 'end_cm': sample['end_cm'],
            'blocking_hit': bool(hit_ok), 'initial_overlap': bool(values[1]), 'impact_point_cm': vector(values[5]), 'impact_normal': vector(values[7]),
            'hit_actor': values[9].get_path_name() if values[9] else None, 'hit_component': values[10].get_path_name() if values[10] else None})
    report['geometry_sha256'] = hashlib.sha256(json.dumps(report['sofa'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    report['support_geometry_sha256'] = hashlib.sha256(json.dumps({'sofa': report['sofa'], 'floor': report['floor']}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if not any(s['seat_surface']['triangle_indices'] for s in report['sofa']['sections']):
        report['errors'].append('Seat triangles require explicit reviewed selection; whole upholstery is not a seat')
    return report
