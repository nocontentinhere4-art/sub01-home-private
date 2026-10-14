"""Sole server editor: import actual owned gamepad assets, preserve the home map.

Temporary source scene actors are measured and removed. The baked contact-shadow
plane is excluded from the physical assembly. No held grip/sofa/input gate activates.
"""
import hashlib
import json
from pathlib import Path

SOURCE_SHA='c034a1444711a44f0726e7264b1e2e2b47b1bbdba0e5dd615eef27001a4717e4'
DEST='/Game/Sub01Home/Devices/Controller/V_'+SOURCE_SHA[:12]


def physical_slots(names):
    return bool(names) and all(str(n).lower()=='controller' for n in names)


def run():
    import unreal as u
    from unreal_import_reference_dressing import fingerprint
    source=Path('/workspace/sub01-home-private/out/controller-private-source.glb')
    if hashlib.sha256(source.read_bytes()).hexdigest()!=SOURCE_SHA:
        raise RuntimeError('Exact original private controller source changed')
    project=Path(u.Paths.project_dir());out=project/'private-audit/native-controller-asset.json'
    actors=u.get_editor_subsystem(u.EditorActorSubsystem)
    original=list(actors.get_all_level_actors());before=fingerprint(u,original)
    if u.EditorAssetLibrary.does_directory_exist(DEST):
        raise RuntimeError('Owned gamepad namespace exists; inspect prior receipt before reimport')
    manager=u.InterchangeManager.get_interchange_manager_scripted()
    params=u.ImportAssetParameters();params.set_editor_property('is_automated',True)
    data=manager.create_source_data(str(source))
    if not manager.can_translate_source_data(data,True):raise RuntimeError('Official gamepad glTF scene translator unavailable')
    imported=[]
    try:
        if not manager.import_scene(DEST,data,params):raise RuntimeError('Actual controller scene import failed')
        manager.wait_until_all_tasks_done(False)
        current=list(actors.get_all_level_actors())
        imported=[a for a in current if a.get_path_name() not in before]
        if fingerprint(u,[a for a in current if a.get_path_name() in before])!=before:
            raise RuntimeError('Original home changed during gamepad import; no map save permitted')
        if u.Sub01HomeHandsInstance.finish_pending_static_compilation()!=0:
            raise RuntimeError('Actual gamepad static build is incomplete')
        physical=[];excluded=[]
        for actor in imported:
            for component in actor.get_components_by_class(u.StaticMeshComponent):
                mesh=component.get_editor_property('static_mesh')
                if not mesh:continue
                slots=[str(m.get_editor_property('material_slot_name')) for m in mesh.get_editor_property('static_materials')]
                bounds=component.get_editor_property('bounds')
                transform=component.get_world_transform()
                row={'mesh':mesh.get_path_name(),'component':component.get_path_name(),'material_slots':slots,
                     'original_source_transform':{'translation':[transform.translation.x,transform.translation.y,transform.translation.z],
                        'quaternion':[transform.rotation.x,transform.rotation.y,transform.rotation.z,transform.rotation.w],
                        'scale':[transform.scale3d.x,transform.scale3d.y,transform.scale3d.z]},
                     'original_source_bounds_cm':{'center':[bounds.origin.x,bounds.origin.y,bounds.origin.z],
                        'extent':[bounds.box_extent.x,bounds.box_extent.y,bounds.box_extent.z]}}
                if physical_slots(slots):physical.append(row)
                elif slots and all('controller_contact' in n.lower() for n in slots):excluded.append(row)
                else:raise RuntimeError('Unknown controller material identity; no proxy selection')
        if len(physical)!=1 or len(excluded)!=1:
            raise RuntimeError('Actual controller main mesh and baked shadow must be unique')
        if min(physical[0]['original_source_bounds_cm']['extent'])<=0:
            raise RuntimeError('Actual controller geometry is empty')
        report={'schema':'sub01.native-controller-asset.v1','source_sha256':SOURCE_SHA,
                'physical_assembly':physical[0],'excluded_baked_shadow':excluded,
                'original_actor_count':len(before),'original_actor_fingerprints_unchanged':True,
                'placed_in_home':False,'grip_accepted':False,'sofa_seated_accepted':False,'runtime_ready':False}
    finally:
        # Assets may remain for inspection; temporary source actors cannot alter the live layout.
        remaining=[a for a in actors.get_all_level_actors() if a.get_path_name() not in before]
        for actor in remaining:actors.destroy_actor(actor)
    after=list(actors.get_all_level_actors())
    if len(after)!=len(original) or fingerprint(u,after)!=before:
        raise RuntimeError('Gamepad temporary scene cleanup did not preserve original map')
    u.EditorAssetLibrary.save_directory(DEST,only_if_is_dirty=False,recursive=True)
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
    u.log('SUB01_CONTROLLER_ASSET_IMPORTED '+json.dumps(report))
    return report
