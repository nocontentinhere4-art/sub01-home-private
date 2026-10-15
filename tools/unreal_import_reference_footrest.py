"""Add the frozen Blender footrest as ONE collidable native component.

For the sole Editor owner in a future coherent body batch. This never moves the
chair, changes activity gates, replaces floor collision or claims seated readiness.
All originals remain exact; every authored material's full triangles are checked.
"""
import hashlib
import json
import re
import shutil
import time
import uuid
from pathlib import Path

SHA = '34869299fd7c8428b224e2c4f95cf39186ab2094fd38e54183235eb21cb9876a'
IDLE = '5354462f74fe3d4e417fc5c8975144e9c3bd69daa2a08c08757ef7929c38a0da'
LABEL = 'SUB01_ReferenceFootrest_OneComponent'


def validate_source(source):
    from home_asset_audit import read_gltf
    source = Path(source)
    proof = json.loads(source.with_suffix('.json').read_text())
    if (hashlib.sha256(source.read_bytes()).hexdigest() != SHA
            or proof.get('schema') != 'sub01.reference-footrest-one-component.v1'
            or proof.get('output_sha256') != SHA or proof.get('physical_idle_sha256') != IDLE
            or proof.get('original_parts') != 19 or proof.get('native_mesh_components') != 1
            or proof.get('primitives') != 20
            or not proof.get('source_indices_uv_pbr_unchanged')
            or not proof.get('original_buffer_prefix_unchanged')):
        raise RuntimeError('Frozen complete one-component footrest proof required')
    doc, blob = read_gltf(source)
    if (len(doc.get('nodes', [])) != 1 or len(doc.get('meshes', [])) != 1
            or doc['nodes'][0].get('name') != LABEL or doc['nodes'][0].get('mesh') != 0
            or len(doc['meshes'][0].get('primitives', [])) != 20
            or doc.get('animations') or doc.get('skins')):
        raise RuntimeError('All19 physical parts must remain ONE static component')
    return proof, doc, blob


def expected_by_material(doc, blob):
    from structural_rail_source_patch import accessor, world_matrices, transformed
    matrix = world_matrices(doc)[0]
    rows = {}
    for p in doc['meshes'][0]['primitives']:
        if p.get('mode', 4) != 4:
            raise RuntimeError('Full triangle source required')
        points = [transformed(matrix, v) for v in accessor(doc, blob, p['attributes']['POSITION'])]
        ids = [int(v[0] if isinstance(v, (tuple, list)) else v) for v in accessor(doc, blob, p['indices'])]
        if len(ids) % 3:
            raise RuntimeError('Incomplete source triangle')
        name = doc['materials'][p['material']]['name']
        rows.setdefault(name, []).extend([
            [[points[j][0]*100, points[j][2]*100, points[j][1]*100] for j in ids[k:k+3]]
            for k in range(0, len(ids), 3)])
    return rows


def verify_native_geometry(u, component, expected):
    from unreal_remove_frame_backings import same_triangles
    canon = lambda s: re.sub('[^a-z0-9]', '', s.lower())
    mesh = component.get_editor_property('static_mesh')
    rows = {name: [] for name in expected}
    for section in range(mesh.get_num_sections(0)):
        # Imported sections can merge equal materials; identify actual material
        # assignments instead of assuming20 primitive indices survive import.
        slot = u.get_editor_subsystem(u.StaticMeshEditorSubsystem).get_lod_material_slot(mesh, 0, section)
        material = component.get_material(slot)
        names = [name for name in rows if material and canon(name) in canon(material.get_name())]
        if len(names) != 1:
            raise RuntimeError('Actual section source-material identity ambiguous')
        vertices, ids, *_ = u.ProceduralMeshLibrary.get_section_from_static_mesh(mesh, 0, section)
        if len(ids) % 3:
            raise RuntimeError('Incomplete native triangle')
        world = component.get_world_transform()
        points = [world.transform_location(v) for v in vertices]
        rows[names[0]].extend([[[float(getattr(points[j], a)) for a in ('x', 'y', 'z')]
                               for j in ids[k:k+3]] for k in range(0, len(ids), 3)])
    if any(not same_triangles(expected[name], rows[name], tolerance=.0001) for name in rows):
        raise RuntimeError('Complete per-material native world triangles differ source')
    return {name: len(triangles) for name, triangles in rows.items()}


def run(source, dry_run=True):
    import unreal as u
    from unreal_import_reference_dressing import fingerprint
    from unreal_import_real_wc import owned_geometry
    from unreal_import_real_linea140 import verify_materials
    from unreal_owned_import_cleanup import detach_added
    source = Path(source)
    proof, doc, blob = validate_source(source)
    expected = expected_by_material(doc, blob)
    project = Path(u.Paths.project_dir())
    home_sha = hashlib.sha256((project/'SourceAssets/full-home.glb').read_bytes()).hexdigest()
    if home_sha != '9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b':
        raise RuntimeError('Actual original home source differs')
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if not world or world.get_path_name().split('.', 1)[0] != '/Game/Sub01Home/ActualHome':
        raise RuntimeError('Sole owner must already have actual private home loaded')
    eas = u.get_editor_subsystem(u.EditorActorSubsystem)
    original = list(eas.get_all_level_actors())
    before = fingerprint(u, original)
    hidden = {a.get_path_name(): bool(a.get_editor_property('hidden')) for a in original}
    if any(a.get_actor_label().startswith(LABEL) for a in original):
        raise RuntimeError('Footrest already present; inspect existing receipt')
    result = {'schema': 'sub01.reference-footrest-native-import.v1', 'source': proof,
              'dry_run': dry_run, 'native_visual_verified': False, 'runtime_ready': False,
              'chair_moved': False, 'activity_gates_changed': False}
    if dry_run:
        return result
    backup = project/'Saved/PrivateMapBackups'/('reference-footrest-'+str(time.time_ns()))
    backup.mkdir(parents=True)
    shutil.copy2(project/'Content/Sub01Home/ActualHome.umap', backup/'ActualHome.umap')
    for name in ('__ExternalActors__', '__ExternalObjects__'):
        folder = project/'Content'/name/'Sub01Home/ActualHome'
        if folder.exists():
            shutil.copytree(folder, backup/name)
    dest = '/Game/Sub01Home/ReferenceFootrest/V_'+SHA[:12]+'/Attempt_'+uuid.uuid4().hex
    audit = project/'private-audit'
    audit.mkdir(exist_ok=True)
    try:
        manager = u.InterchangeManager.get_interchange_manager_scripted()
        params = u.ImportAssetParameters()
        params.set_editor_property('is_automated', True)
        if not manager.import_scene(dest, manager.create_source_data(str(source)), params):
            raise RuntimeError('Owned Blender footrest import refused')
        manager.wait_until_all_tasks_done(False)
        added = [a for a in eas.get_all_level_actors() if a.get_path_name() not in before]
        for a in added:
            a.set_actor_hidden_in_game(True)
        components = [(a, c) for a in added for c in a.get_components_by_class(u.StaticMeshComponent)]
        if len(components) != 1:
            raise RuntimeError('Real four-point sole support requires ONE native component')
        actor, c = components[0]
        mesh = c.get_editor_property('static_mesh')
        if not c.get_editor_property('visible'):
            raise RuntimeError('Imported full footrest component must be visible')
        owned_geometry(u, mesh, dest)
        counts = verify_native_geometry(u, c, expected)
        materials = verify_materials(u, [c], doc, dest)
        c.set_collision_profile_name('BlockAll')
        c.set_collision_enabled(u.CollisionEnabled.QUERY_AND_PHYSICS)
        if (c.get_collision_enabled() != u.CollisionEnabled.QUERY_AND_PHYSICS
                or mesh.get_editor_property('body_setup').get_editor_property('collision_trace_flag')
                != u.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE):
            raise RuntimeError('Actual full-source footrest collision unavailable')
        if fingerprint(u, original) != before or hidden != {a.get_path_name(): bool(a.get_editor_property('hidden')) for a in original}:
            raise RuntimeError('Import changed a protected original')
        if not u.EditorAssetLibrary.save_directory(dest, only_if_is_dirty=False, recursive=True):
            raise RuntimeError('Owned complete footrest assets save failed')
        actor.set_actor_label(LABEL)
        actor.set_actor_hidden_in_game(False)
        result.update(owned_destination=dest, backup=str(backup), actor=actor.get_path_name(),
                      component=c.get_path_name(), per_material_triangle_counts=counts,
                      materials=materials, protected_originals_unchanged=True)
        pending = audit/'reference-footrest-import.pending.json'
        pending.write_text(json.dumps(result, indent=2)+'\n')
        if not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():
            raise RuntimeError('Additive footrest map save failed')
        pending.replace(audit/'reference-footrest-import.json')
        return result
    except Exception as error:
        cleanup = detach_added(u, eas, before)
        equal = fingerprint(u, original) == before and hidden == {a.get_path_name(): bool(a.get_editor_property('hidden')) for a in original}
        (audit/'reference-footrest-refusal.json').write_text(json.dumps({
            'error': str(error), 'cleanup': cleanup, 'protected_originals_unchanged': equal,
            'quarantined_destination': dest, 'backup': str(backup)}, indent=2)+'\n')
        if not equal:
            raise RuntimeError('Protected original differs; preserve backup and stop') from error
        if not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():
            raise RuntimeError('Footrest rollback map save failed') from error
        raise
