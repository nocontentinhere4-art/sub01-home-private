"""Import only verified new dressing into the existing private native map.

Execute on the authorized server, with the native game stopped. Existing
actors, components, materials and collision settings must remain identical.
The Blender receipt must prove the baseline remained unchanged. No full-home
reimport, map recreation or live/public deployment is permitted here.
"""
import hashlib
import json
from pathlib import Path

LEVEL = '/Game/Sub01Home/ActualHome'
DESTINATION = '/Game/Sub01Home/ReferenceDressing'


def validate_receipt(report, source):
    export = report.get('additive_glb') or {}
    if (report.get('mode') != 'blender' or report.get('basis') != 'evaluated-geometry'
            or report.get('existing_objects_verified_unchanged', 0) < 1
            or not report.get('built') or not export.get('objects')):
        raise ValueError('Missing successful real additive Blender receipt')
    if any(not name.startswith('SUB01_RefDress_') for name in export['objects']):
        raise ValueError('Export contains an object outside the owned dressing collection')
    actual = hashlib.sha256(source.read_bytes()).hexdigest()
    if actual != export.get('sha256'):
        raise ValueError('Actual additive GLB differs from the Blender receipt')
    return actual


def fingerprint(u, actors):
    def measured_transform(transform):
        translation, rotation, scale = transform.translation, transform.rotation, transform.scale3d
        return {'translation': [float(translation.x), float(translation.y), float(translation.z)],
                'rotation': [float(rotation.x), float(rotation.y), float(rotation.z), float(rotation.w)],
                'scale': [float(scale.x), float(scale.y), float(scale.z)]}

    result = {}
    for actor in actors:
        components = []
        for component in actor.get_components_by_class(u.StaticMeshComponent):
            mesh = component.get_editor_property('static_mesh')
            transform = component.get_world_transform()
            components.append({
                'path': component.get_path_name(), 'mesh': mesh.get_path_name() if mesh else None,
                'transform': measured_transform(transform), 'collision': str(component.get_collision_enabled()),
                'profile': str(component.get_collision_profile_name()),
                'materials': [material.get_path_name() if material else None
                              for material in component.get_materials()],
                'tags': [str(tag) for tag in component.get_editor_property('component_tags')],
            })
        result[actor.get_path_name()] = {
            'label': actor.get_actor_label(), 'transform': measured_transform(actor.get_actor_transform()),
            'components': sorted(components, key=lambda entry: entry['path']),
        }
    return result


def run():
    import unreal as u

    root = Path('/workspace/sub01-home-private/out/native-reference-dressing')
    report = json.loads((root / 'reference-dressing.json').read_text())
    source = root / 'reference-dressing.glb'
    digest = validate_receipt(report, source)
    baseline = json.loads((root.parent / 'native-reference-base/house.json').read_text())
    actual_source = Path(u.Paths.project_dir()) / 'SourceAssets/full-home.glb'
    if hashlib.sha256(actual_source.read_bytes()).hexdigest() != baseline['source_sha256']:
        raise RuntimeError('Native baseline changed since the additive authoring pass')
    level = u.get_editor_subsystem(u.LevelEditorSubsystem)
    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    if not level.load_level(LEVEL):
        raise RuntimeError('Existing private native map is unavailable')
    original = list(actors.get_all_level_actors())
    before = fingerprint(u, original)
    if any('SUB01_RefDress_' in actor.get_actor_label()
           or actor.get_actor_label().startswith('SUB01_ReferenceDressing_') for actor in original):
        raise RuntimeError('Dressing already placed; inspect before adding another version')
    destination = DESTINATION + '/V_' + digest[:12]
    manager = u.InterchangeManager.get_interchange_manager_scripted()
    params = u.ImportAssetParameters()
    params.set_editor_property('is_automated', True)
    data = manager.create_source_data(str(source))
    if not manager.can_translate_source_data(data, True):
        raise RuntimeError('Official additive glTF scene translator unavailable')
    if not manager.import_scene(destination, data, params):
        raise RuntimeError('Additive scene import failed; existing map not saved')
    manager.wait_until_all_tasks_done(False)
    current = list(actors.get_all_level_actors())
    original_paths = set(before)
    retained = [actor for actor in current if actor.get_path_name() in original_paths]
    if fingerprint(u, retained) != before:
        raise RuntimeError('Import changed an existing actor; refuse to save the map')
    added = [actor for actor in current if actor.get_path_name() not in original_paths]
    meshes = []
    for actor in added:
        actor.set_actor_label('SUB01_ReferenceDressing_' + actor.get_actor_label())
        for component in actor.get_components_by_class(u.StaticMeshComponent):
            mesh = component.get_editor_property('static_mesh')
            if not mesh:
                continue
            if not mesh.get_path_name().startswith(destination + '/'):
                raise RuntimeError('Additive import reused an unowned mesh; refuse collision edits')
            body = mesh.get_editor_property('body_setup')
            if not body:
                raise RuntimeError('New dressing mesh has no real collision geometry')
            body.set_editor_property('collision_trace_flag', u.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
            component.set_collision_profile_name('BlockAll')
            component.set_collision_enabled(u.CollisionEnabled.QUERY_AND_PHYSICS)
            meshes.append(component.get_path_name())
    if not meshes:
        raise RuntimeError('Import placed no actual dressing mesh components')
    if fingerprint(u, retained) != before:
        raise RuntimeError('Dressing setup changed an original component; refuse to save')
    u.EditorAssetLibrary.save_directory(destination, only_if_is_dirty=False, recursive=True)
    if not level.save_current_level():
        raise RuntimeError('Existing map failed to save after additive import')
    result = {
        'schema': 'sub01.native-reference-dressing-import.v1', 'source_sha256': digest,
        'level': LEVEL, 'original_actors_verified_unchanged': len(before),
        'added_actors': len(added), 'added_mesh_components': meshes,
        'physical_route_verified': False, 'visually_verified': False,
    }
    (Path(u.Paths.project_dir()) / 'reference-dressing-import.json').write_text(
        json.dumps(result, indent=2) + '\n')
    u.log('SUB01_REFERENCE_DRESSING_IMPORTED ' + json.dumps(result))
    return result


if __name__ == '__main__':
    run()
