"""Private full-source monitor proofs; never mutate shared meshes or screen75."""
import copy
from uuid import uuid4

from real_office_plant import native_geometry_api_audit
from unreal_import_real_kitchen import same_triangles

PREFIX = '/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/'


def can_rebuild(u, node, component):
    if node not in (73, 74):
        return False
    mesh = component.get_editor_property('static_mesh')
    index = {73: 56, 74: 57}[node]
    if not mesh or mesh.get_path_name() != PREFIX+f'Mesh_{index}.Mesh_{index}':
        return False
    audit = native_geometry_api_audit(u, mesh)
    settings, apis = audit.get('nanite_settings', {}), audit.get('subsystem_apis', {})
    return bool(settings.get('enabled') is True and settings.get('keep_percent_triangles') == 1.
                and settings.get('trim_relative_error') == 0.
                and apis.get('get_nanite_settings') and apis.get('set_nanite_settings'))


def stage(u, eas, rows, native_triangles):
    """Validate copies at original pose before returning any activation bindings.

    Assets remain in their unique owned namespace even on failure. Temporary
    components detach before actor destruction; no force-deletion of compiling
    meshes is attempted. Screen75 is inspected by the caller and never copied.
    """
    dest = '/Game/Sub01Home/RealMonitorSupport/V_9556495fa816_'+uuid4().hex
    replacements, proof = {}, []
    for node, actor, component, source in rows:
        actual = native_triangles(u, component)
        if same_triangles(source, actual):
            proof.append({'node': node, 'full_source_triangles': len(actual), 'rebuilt': False})
            continue
        if not can_rebuild(u, node, component):
            raise RuntimeError('Unreviewed monitor source mismatch '+str(node))
        original = component.get_editor_property('static_mesh')
        original_settings = copy.deepcopy(native_geometry_api_audit(u, original)['nanite_settings'])
        temp = tc = clone = None
        try:
            clone = u.EditorAssetLibrary.duplicate_asset(original.get_path_name(), dest+'/Mesh_'+str(node))
            if not clone or not clone.get_path_name().startswith(dest+'/'):
                raise RuntimeError('Owned monitor duplication failed')
            sub = u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
            settings = sub.get_nanite_settings(clone)
            for prop, value in (('enabled', False), ('keep_percent_triangles', 1.),
                                ('trim_relative_error', 0.), ('fallback_percent_triangles', 1.),
                                ('fallback_relative_error', 0.)):
                settings.set_editor_property(prop, value)
            sub.set_nanite_settings(clone, settings, True)
            if not u.EditorAssetLibrary.save_loaded_asset(clone, only_if_is_dirty=False):
                raise RuntimeError('Owned monitor source rebuild/save failed')
            if sub.get_nanite_settings(clone).get_editor_property('enabled'):
                raise RuntimeError('Owned monitor still exposes reduced fallback')
            temp = eas.spawn_actor_from_class(u.StaticMeshActor, u.Vector(0, 0, 0))
            temp.set_actor_label('SUB01_Monitor_FullSourceProof_'+str(node))
            temp.set_actor_hidden_in_game(True)
            tc = temp.get_component_by_class(u.StaticMeshComponent)
            tc.set_static_mesh(clone)
            tc.set_world_transform(component.get_world_transform(), False, False)
            tc.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
            for slot, material in enumerate(component.get_materials()):
                tc.set_material(slot, material)
            full = native_triangles(u, tc)
            if len(source) != 300 or not same_triangles(source, full):
                raise RuntimeError('Owned complete monitor source triangles differ '+str(node))
            paths = lambda c: [m.get_path_name() if m else None for m in c.get_materials()]
            if paths(tc) != paths(component):
                raise RuntimeError('Owned monitor source material bindings changed')
            if native_geometry_api_audit(u, original)['nanite_settings'] != original_settings:
                raise RuntimeError('Original shared monitor settings changed')
            replacements[node] = clone
            proof.append({'node': node, 'full_source_triangles': len(full), 'rebuilt': True,
                          'owned_mesh': clone.get_path_name(), 'original_mesh': original.get_path_name(),
                          'material_bindings': paths(tc)})
        finally:
            try:
                if tc is not None:
                    tc.set_static_mesh(None)
                if temp is not None and not eas.destroy_actor(temp):
                    raise RuntimeError('Monitor temporary actor cleanup failed; assets quarantined '+dest)
            finally:
                tc = temp = clone = None
    return {'replacements': replacements, 'proof': proof,
            'owned_asset_directory': dest if replacements else None,
            'screen75_copied': False, 'shared_originals_unchanged': True}
