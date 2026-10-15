"""Read only the failed owned kitchen import; never load corrupt packages or delete."""
import hashlib
import json
import os
import time
from pathlib import Path

DEST = '/Game/Sub01Home/RealKitchen/V_c5b8f73361d8'
ROOT = Path('/workspace/sub01-private-kitchen-3eb5419-20261015/proof-output-r2/uid1001')


def run(u=None):
    if u is None:
        import unreal as u
    from real_office_plant import native_geometry_api_audit
    from unreal_import_real_linea140 import surface
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if not world or world.get_path_name().split('.', 1)[0] != '/Game/Sub01Home/ActualHome':
        raise RuntimeError('Actual loaded home required for partial import inventory')
    proof = json.loads((ROOT/'native-kitchen.json').read_text())
    expected = {p['name']: p for p in proof['parts']}
    result = {'schema': 'sub01.kitchen-partial-native-inventory.v1',
              'editor_pid': os.getpid(), 'captured_epoch': time.time(),
              'scene_mutations': 0, 'assets_force_loaded': False,
              'expected_parts': len(expected), 'partial_actors': [], 'asset_metadata': []}
    eas = u.get_editor_subsystem(u.EditorActorSubsystem)
    for actor in eas.get_all_level_actors():
        label = actor.get_actor_label()
        components = actor.get_components_by_class(u.StaticMeshComponent)
        owned = label.startswith(proof['prefix'])
        if not owned:
            owned = any(c.get_editor_property('static_mesh') and
                        c.get_editor_property('static_mesh').get_path_name().startswith(DEST+'/')
                        for c in components)
        if not owned:
            continue
        row = {'actor': actor.get_path_name(), 'label': label,
               'transform': str(actor.get_actor_transform()), 'expected': expected.get(label),
               'components': []}
        for component in components:
            item = {'component': component.get_path_name(),
                    'transform': str(component.get_world_transform())}
            try:
                mesh = component.get_editor_property('static_mesh')
                item['mesh'] = mesh.get_path_name() if mesh else None
                if mesh:
                    item['geometry_api_audit'] = native_geometry_api_audit(u, mesh)
                    points, count = surface(u, component)
                    item['cpu_triangles'] = count
                    item['world_bounds_cm'] = [[f(p[k] for p in points) for k in range(3)]
                                               for f in (min, max)]
                    item['sections'] = mesh.get_num_sections(0)
            except Exception as error:
                item['read_error'] = type(error).__name__ + ': ' + str(error)
            row['components'].append(item)
        result['partial_actors'].append(row)
    # Inspect only the already-loaded, exact R2 mesh that lost twelve triangles.
    exact = ('/Game/Sub01Home/RealKitchen/V_c5b8f73361d8_R2/'
             'SUB01_RealKitchen_687d9c6d9bda_Scene/StaticMeshes/'
             'SUB01_RealKitchen_687d9c6d9bda_Mesh_11.'
             'SUB01_RealKitchen_687d9c6d9bda_Mesh_11')
    loaded = u.find_object(None, exact)
    result['failed_r2_mesh'] = {'path': exact, 'loaded': loaded is not None,
                              'assets_force_loaded': False}
    if loaded is not None:
        from unreal_loaded_plant_clone_audit import build_settings, extract
        import gzip
        sub = u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
        local_triangles, local_sections = extract(u, loaded, u.Transform())
        triangle_output = Path(u.Paths.project_dir())/'private-audit/kitchen-r2-mesh11-local-triangles.json.gz'
        triangle_output.write_bytes(gzip.compress(json.dumps({
            'schema': 'sub01.loaded-kitchen-mesh-triangles.v1', 'mesh': exact,
            'coordinate_space': 'native asset local centimetres; identity transform',
            'sections': local_sections, 'triangles': local_triangles,
            'scene_mutations': 0, 'assets_force_loaded': False}).encode()))
        result['failed_r2_mesh'].update({
            'local_triangles_gzip': str(triangle_output),
            'local_triangles_count': len(local_triangles),
            'build_settings': build_settings(u, loaded),
            'geometry_api_audit': native_geometry_api_audit(u, loaded),
            'set_lod_build_settings_doc': str(getattr(sub, 'set_lod_build_settings', None).__doc__)})
    # Registry metadata does not load any potentially corrupt failed package.
    registry = u.AssetRegistryHelpers.get_asset_registry()
    for asset in registry.get_assets_by_path(DEST, recursive=True):
        result['asset_metadata'].append({'package_name': str(asset.package_name),
                                         'asset_name': str(asset.asset_name)})
    project = Path(u.Paths.project_dir())
    current = project/'Content/Sub01Home/ActualHome.umap'
    result['saved_map_sha256'] = hashlib.sha256(current.read_bytes()).hexdigest()
    backups = list((project/'Saved/PrivateMapBackups').glob('real-kitchen-*/ActualHome.umap'))
    if backups:
        backup = max(backups, key=lambda p: p.stat().st_mtime_ns)
        digest = hashlib.sha256(backup.read_bytes()).hexdigest()
        result['latest_pre_kitchen_backup'] = str(backup)
        result['pre_kitchen_backup_sha256'] = digest
        result['saved_map_unchanged_from_pre_kitchen'] = digest == result['saved_map_sha256']
    output = project/'private-audit/kitchen-partial-native-inventory.json'
    output.write_text(json.dumps(result, indent=2)+'\n')
    return result
