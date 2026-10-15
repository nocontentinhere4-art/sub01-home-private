"""Sole warm-Editor kitchen transaction; no level load, restart or provider work.

Only accepts the next-window protected-home/cross-door proof, never the earlier
sink-only receipt. Stages unique owned assets, verifies all152 actual native
parts/PBR, builds eight movable five-part hinges, then retires exact63/178.
"""
import hashlib
import itertools
import json
import math
import shutil
import time
from pathlib import Path

from home_asset_audit import read_gltf
from prepare_real_kitchen_bundle import HOME_SHA
from prepare_real_kitchen_native_bundle import validate_manifest, OLD
from unreal_import_real_linea140 import surface, verify_materials, close
from unreal_import_reference_dressing import fingerprint
from structural_rail_source_patch import accessor, world_matrices, transformed

LEVEL = '/Game/Sub01Home/ActualHome'


def same_triangles(source, actual, tolerance_cm=.02):
    """Independent of index/vertex splitting/order; every actual triangle consumed."""
    if len(source) != len(actual):
        return False
    if any(len(t) != 3 or any(len(p) != 3 or not all(math.isfinite(v) for v in p) for p in t)
           for group in (source, actual) for t in group):
        return False
    cell = .05
    def key(triangle):
        return tuple(math.floor(sum(p[k] for p in triangle)/3/cell) for k in range(3))
    buckets = {}
    for index, triangle in enumerate(actual):
        buckets.setdefault(key(triangle), set()).add(index)
    for triangle in source:
        center = key(triangle)
        matched = None
        for offset in itertools.product((-1, 0, 1), repeat=3):
            bucket = buckets.get(tuple(a+b for a, b in zip(center, offset)), set())
            for index in bucket:
                if any(all(math.dist(a, b) <= tolerance_cm for a, b in zip(triangle, order))
                       for order in itertools.permutations(actual[index])):
                    matched = (bucket, index)
                    break
            if matched:
                break
        if matched is None:
            return False
        matched[0].remove(matched[1])
    return True


def verify_retained_native(u, original, source):
    doc, binary = read_gltf(source)
    matrices = world_matrices(doc)
    rows = []
    for node, mesh_index in ((65, 48), (66, 49), (164, 123)):
        matches = [a for a in original if a.get_name() == 'full-home_node_'+str(node)]
        if len(matches) != 1:
            raise RuntimeError('Retained source countertop/strip/sink identity missing')
        components = matches[0].get_components_by_class(u.StaticMeshComponent)
        expected_path = f'/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Mesh_{mesh_index}.Mesh_{mesh_index}'
        if (len(components) != 1 or components[0].get_editor_property('static_mesh').get_path_name() != expected_path
                or bool(matches[0].get_editor_property('hidden')) or not components[0].get_editor_property('visible')):
            raise RuntimeError('Exact retained kitchen source geometry/binding unavailable')
        expected = []
        for primitive in doc['meshes'][doc['nodes'][node]['mesh']]['primitives']:
            points = [transformed(matrices[node], p) for p in accessor(doc, binary, primitive['attributes']['POSITION'])]
            points = [[p[k]*100 for k in (0, 2, 1)] for p in points]
            ids = [r[0] for r in accessor(doc, binary, primitive['indices'])]
            expected += [[points[k] for k in ids[j:j+3]] for j in range(0, len(ids), 3)]
        c = components[0]
        mesh = c.get_editor_property('static_mesh')
        actual = []
        for section in range(mesh.get_num_sections(0)):
            vertices, ids, *_ = u.ProceduralMeshLibrary.get_section_from_static_mesh(mesh, 0, section)
            world = c.get_world_transform()
            pts = [world.transform_location(p) for p in vertices]
            points = [[float(p.x), float(p.y), float(p.z)] for p in pts]
            actual += [[points[k] for k in ids[j:j+3]] for j in range(0, len(ids), 3)]
        if not same_triangles(expected, actual):
            raise RuntimeError('Retained native countertop/strip/sink differs from actual source triangles '+str(node))
        rows.append({'node': node, 'component': c.get_path_name(), 'triangles': len(actual),
                     'source_triangle_positions_verified_cm': .02})
    return rows


def snapshot(u, actors):
    result = fingerprint(u, actors)
    for actor in actors:
        row = result[actor.get_path_name()]
        row['hidden'] = bool(actor.get_editor_property('hidden'))
        row['visible'] = {c.get_path_name(): bool(c.get_editor_property('visible'))
                          for c in actor.get_components_by_class(u.StaticMeshComponent)}
        row['light_intensities'] = {c.get_path_name(): c.get_editor_property('intensity')
                                    for c in actor.get_components_by_class(u.LightComponent)}
    return result


def preflight(root, u):
    root = Path(root)
    proof = validate_manifest(json.loads((root/'native-kitchen.json').read_text()))
    source = root/'native-kitchen.glb'
    if hashlib.sha256(source.read_bytes()).hexdigest() != proof['export_sha256']:
        raise RuntimeError('Actual protected kitchen GLB differs proved bytes')
    project = Path(u.Paths.project_dir())
    if hashlib.sha256((project/'SourceAssets/full-home.glb').read_bytes()).hexdigest() != HOME_SHA:
        raise RuntimeError('Actual native baseline source955 required')
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if not world or world.get_path_name().split('.', 1)[0] != LEVEL:
        raise RuntimeError('Sole owner must already have ActualHome loaded')
    eas = u.get_editor_subsystem(u.EditorActorSubsystem)
    original = list(eas.get_all_level_actors())
    old = []
    for node, (label, mesh_index) in OLD.items():
        matches = [a for a in original if a.get_name() == 'full-home_node_'+str(node)]
        if len(matches) != 1:
            raise RuntimeError('Exact original cabinet identity missing '+str(node))
        actor = matches[0]
        components = actor.get_components_by_class(u.StaticMeshComponent)
        expected = f'/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Mesh_{mesh_index}.Mesh_{mesh_index}'
        if (actor.get_actor_label() != label or len(components) != 1
                or components[0].get_editor_property('static_mesh').get_path_name() != expected
                or bool(actor.get_editor_property('hidden'))):
            raise RuntimeError('Original cabinet binding/visibility differs; no batch guesses')
        old.append((actor, components[0]))
    # Actual source geometry, not just actor names or coincident bounding boxes.
    retained = verify_retained_native(u, original, project/'SourceAssets/full-home.glb')
    if any(any(str(tag).startswith('SUB01Kitchen:') for tag in c.get_editor_property('component_tags'))
           for a in original for c in a.get_components_by_class(u.StaticMeshComponent)):
        raise RuntimeError('Owned kitchen already present; inspect receipt before any reimport')
    destination = '/Game/Sub01Home/RealKitchen/V_'+proof['export_sha256'][:12]
    if u.EditorAssetLibrary.does_directory_exist(destination):
        raise RuntimeError('Kitchen asset version exists; no duplicate scene import')
    return proof, source, project, eas, original, old, destination, retained


def run(root, dry_run=True, u=None):
    if u is None:
        import unreal as u
    root = Path(root)
    proof, source, project, eas, original, old, dest, retained = preflight(root, u)
    before = snapshot(u, original)
    result = {'schema': 'sub01.real-kitchen-native-import.v1', 'export_sha256': proof['export_sha256'],
              'retire_only_original_nodes': [63, 178], 'native_visual_verified': False,
              'native_hinge_motion_verified': False, 'native_backend_state_verified': False,
              'retained_native_source_geometry': retained, 'interactions_enabled': False}
    if dry_run:
        return {**result, 'dry_run': True, 'mutations': 0,
                'protected_originals': len(original), 'required_hinges': 8, 'required_parts': 152}
    backup = project/'Saved/PrivateMapBackups'/('real-kitchen-'+str(time.time_ns()))
    backup.mkdir(parents=True)
    shutil.copy2(project/'Content/Sub01Home/ActualHome.umap', backup/'ActualHome.umap')
    for directory in ('__ExternalActors__', '__ExternalObjects__'):
        folder = project/'Content'/directory/'Sub01Home/ActualHome'
        if folder.exists():
            shutil.copytree(folder, backup/directory)
    states = [(a, a.get_actor_transform(), a.get_actor_label(), bool(a.get_editor_property('hidden')),
               [(c, c.get_world_transform(), c.get_editor_property('static_mesh'), list(c.get_materials()),
                 list(c.get_editor_property('component_tags')), bool(c.get_editor_property('visible')),
                 c.get_collision_enabled(), c.get_collision_profile_name(), c.get_editor_property('mobility'))
                for c in a.get_components_by_class(u.StaticMeshComponent)]) for a in original]
    level_save_attempted = False
    # Interchange may label its scene owner from the filename rather than the
    # glTF scene name. Give that owner the same deterministic UID too.
    staging_source = root/(proof['prefix']+'Scene.glb')
    staging_source_created = False
    try:
        if staging_source.exists():
            if hashlib.sha256(staging_source.read_bytes()).hexdigest() != proof['export_sha256']:
                raise RuntimeError('Owned kitchen staging filename exists with different bytes')
        else:
            shutil.copy2(source, staging_source)
            staging_source_created = True
        manager = u.InterchangeManager.get_interchange_manager_scripted()
        params = u.ImportAssetParameters()
        params.set_editor_property('is_automated', True)
        if not manager.import_scene(dest, manager.create_source_data(str(staging_source)), params):
            raise RuntimeError('Unique authentic kitchen import failed')
        manager.wait_until_all_tasks_done(False)
        if snapshot(u, original) != before:
            raise RuntimeError('Scene import altered protected originals before activation')
        added = [a for a in eas.get_all_level_actors() if a.get_path_name() not in before]
        if any(not a.get_actor_label().startswith(proof['prefix']) for a in added):
            raise RuntimeError('Importer added an unowned/unexpected actor')
        by_name, components, rows = {}, [], []
        moving = {name: hinge['index'] for hinge in proof['hinges'] for name in hinge['parts']}
        mesh_subsystem = u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
        for expected in proof['parts']:
            matches = [a for a in added if a.get_actor_label() == expected['name']]
            if len(matches) != 1:
                raise RuntimeError('Actual kitchen source part not unique '+expected['name'])
            actor = matches[0]
            cs = actor.get_components_by_class(u.StaticMeshComponent)
            if len(cs) != 1:
                raise RuntimeError('Kitchen part has unexpected native components')
            c = cs[0]
            mesh = c.get_editor_property('static_mesh')
            if not mesh or not mesh.get_path_name().startswith(dest+'/'):
                raise RuntimeError('Kitchen reused an unowned mesh')
            points, count = surface(u, c)
            actual = [[f(p[k] for p in points) for k in range(3)] for f in (min, max)]
            wanted = [[b[k]*100 for k in (0, 2, 1)] for b in expected['bounds_browser_m']]
            if count != expected['triangles'] or not all(close(a, b, .02) for a, b in zip(actual, wanted)):
                raise RuntimeError('Actual native kitchen triangle count/world placement changed '+expected['name'])
            body = mesh.get_editor_property('body_setup')
            if not body:
                raise RuntimeError('Owned kitchen collision body absent')
            c.set_simulate_physics(False)
            if expected['name'] in moving:
                # Every authored handle/inset/panel remains a separate rigid part.
                # Native swept conservative boxes protect the pawn and other doors.
                if not hasattr(mesh_subsystem, 'add_simple_collisions'):
                    raise RuntimeError('Actual native simple collision API unavailable')
                mesh_subsystem.remove_collisions(mesh)
                if mesh_subsystem.add_simple_collisions(mesh, u.ScriptingCollisionShapeType.BOX) < 0:
                    raise RuntimeError('Actual moving hinge simple collision creation refused')
                body.set_editor_property('collision_trace_flag', u.CollisionTraceFlag.CTF_USE_SIMPLE_AND_COMPLEX)
                actor.get_root_component().set_mobility(u.ComponentMobility.MOVABLE)
                c.set_mobility(u.ComponentMobility.MOVABLE)
                tag = f"SUB01Kitchen:{proof['export_sha256']}:D{moving[expected['name']]}:{expected['source_part']}"
                c.set_editor_property('component_tags', list(c.get_editor_property('component_tags'))+[tag])
            else:
                body.set_editor_property('collision_trace_flag', u.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
            c.set_collision_profile_name('BlockAll')
            c.set_collision_enabled(u.CollisionEnabled.QUERY_AND_PHYSICS)
            c.set_visibility(True)
            actor.set_actor_hidden_in_game(False)
            by_name[expected['name']] = (actor, c)
            components.append(c)
            rows.append({'part': expected['name'], 'component': c.get_path_name(), 'mesh': mesh.get_path_name(),
                         'triangles': count, 'bounds_cm': actual, 'moving_hinge': moving.get(expected['name'])})
        owned_mesh_components = [c for a in added for c in a.get_components_by_class(u.StaticMeshComponent)]
        if len(owned_mesh_components) != 152 or set(c.get_path_name() for c in components) != set(c.get_path_name() for c in owned_mesh_components):
            raise RuntimeError('Actual native import contains extra/missing geometry')
        doc, _ = read_gltf(source)
        materials = []
        source_bindings = {}
        for node in doc['nodes']:
            if 'mesh' not in node:
                continue
            cs = by_name[node['name']][1]
            primitives = doc['meshes'][node['mesh']]['primitives']
            if len(primitives) != 1 or cs.get_num_materials() != 1:
                raise RuntimeError('Expected exact authored single-slot kitchen part')
            material_index = primitives[0]['material']
            actual_material = cs.get_material(0)
            if not actual_material:
                raise RuntimeError('Actual authored kitchen material absent')
            if material_index in source_bindings:
                if source_bindings[material_index] != actual_material.get_path_name():
                    raise RuntimeError('Shared authored kitchen material split unexpectedly')
                continue
            # The source contains Material_0 and Material_0.001. Resolve each
            # through its actual primitive/slot, never a global name substring.
            materials += verify_materials(u, [cs], {'materials': [doc['materials'][material_index]]}, dest)
            source_bindings[material_index] = actual_material.get_path_name()
        if len(source_bindings) != len(doc['materials']):
            raise RuntimeError('Authored kitchen material coverage incomplete')
        if snapshot(u, original) != before:
            raise RuntimeError('Owned geometry/material setup changed protected originals')
        for actor, c in old:
            actor.set_actor_hidden_in_game(True)
            c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
        protected = [a for a in original if a not in [r[0] for r in old]]
        if snapshot(u, protected) != {a.get_path_name(): before[a.get_path_name()] for a in protected}:
            raise RuntimeError('Kitchen activation altered sink/counter/light/chair/stairs/devices')
        result.update({'map_backup': str(backup), 'parts': rows, 'materials': materials,
                       'hinges': proof['hinges'], 'protected_originals_verified': len(protected),
                       'hidden_originals': [a.get_path_name() for a, c in old]})
        # Write a pending receipt before saving, never mark interaction/visual tests passed.
        pending = root/'native-kitchen-import.pending.json'
        pending.write_text(json.dumps(result, indent=2)+'\n')
        if not u.EditorAssetLibrary.save_directory(dest, only_if_is_dirty=False, recursive=True):
            raise RuntimeError('Owned kitchen asset save failed')
        level_save_attempted = True
        if not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():
            raise RuntimeError('Kitchen level save failed; restore private map backup')
        pending.replace(root/'native-kitchen-import.json')
        return result
    except Exception:
        def depth(actor):
            seen = set()
            while actor.get_attach_parent_actor():
                actor = actor.get_attach_parent_actor()
                if actor.get_path_name() in seen:
                    raise RuntimeError('Attachment cycle during kitchen rollback')
                seen.add(actor.get_path_name())
            return len(seen)
        for actor, transform, label, hidden, cs in sorted(states, key=lambda row: depth(row[0])):
            actor.set_actor_transform(transform, False, False)
        for actor, transform, label, hidden, cs in states:
            actor.set_actor_label(label)
            actor.set_actor_hidden_in_game(hidden)
            for c, world, mesh, materials, tags, visible, collision, profile, mobility in cs:
                c.set_static_mesh(mesh)
                c.set_world_transform(world, False, False)
                c.set_editor_property('component_tags', tags)
                c.set_visibility(visible)
                c.set_collision_profile_name(profile)
                c.set_collision_enabled(collision)
                c.set_mobility(mobility)
                for slot, mat in enumerate(materials):
                    c.set_material(slot, mat)
        for actor in list(eas.get_all_level_actors()):
            if actor.get_path_name() not in before:
                eas.destroy_actor(actor)
        if u.EditorAssetLibrary.does_directory_exist(dest):
            u.EditorAssetLibrary.delete_directory(dest)
        if staging_source_created:
            staging_source.unlink(missing_ok=True)
        if snapshot(u, original) != before:
            raise RuntimeError('Kitchen rollback differs from protected originals; preserve map backup '+str(backup))
        if level_save_attempted and not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():
            raise RuntimeError('Kitchen rollback map save failed; restore private map backup '+str(backup))
        raise
