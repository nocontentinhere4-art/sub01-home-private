"""Owned temporary-component proof of Custom collision restore; originals untouched."""
import hashlib
import json
from pathlib import Path
from unreal_component_collision_state import capture,restore,signature
from unreal_owned_import_cleanup import release_temporary

DEST='/Game/Sub01Home/RealOfficeBooks/V_611a3d848858_FullSource_9279b89011474be0afe7704b39f800f9'


def run(u=None):
    if u is None:
        import unreal as u
    eas=u.get_editor_subsystem(u.EditorActorSubsystem)
    found=[a for a in eas.get_all_level_actors()if a.get_actor_label()=='SUB01_RealBook_01']
    if len(found)!=1:raise RuntimeError('Unique saved book01 required')
    cs=found[0].get_components_by_class(u.StaticMeshComponent)
    if len(cs)!=1:raise RuntimeError('Unique saved book01 component required')
    original=cs[0];mesh=original.get_editor_property('static_mesh');key=mesh.get_path_name()
    if not key.startswith('/Game/Sub01Home/RealBooks/V_611a3d848858/'):raise RuntimeError('Saved611 book01 binding changed')
    name='Mesh_'+hashlib.sha256(key.encode()).hexdigest()[:12];path=DEST+'/'+name+'.'+name
    clone=u.find_object(None,path)
    if clone is None:raise RuntimeError('Exact quarantined full-source book clone not loaded; no load attempted')
    saved=capture(u,original);temp=tc=None
    report={'schema':'sub01.temporary-book-collision-restore.v1','original_scene_mutations':0,'body_instances_copied':False,'source_component':original.get_path_name(),'clone':path}
    try:
        temp=eas.spawn_actor_from_class(u.StaticMeshActor,u.Vector(0,0,-100000))
        temp.set_actor_label('SUB01_Temporary_CustomCollision_Proof');temp.set_actor_hidden_in_game(True)
        tc=temp.get_component_by_class(u.StaticMeshComponent);tc.set_static_mesh(mesh)
        restore(u,tc,saved,force_response_copy=True);report['initial_temporary_custom_profile']=str(tc.get_collision_profile_name())
        tc.set_static_mesh(clone);report['after_mesh_profile']=str(tc.get_collision_profile_name())
        restore(u,tc,saved,force_response_copy=True)
        report.update({'restored_profile':str(tc.get_collision_profile_name()),'effective_collision_configuration_equal':signature(capture(u,tc))==signature(saved),'standard_channels_independently_verified':len(saved['visible_responses']),'hidden_channels_independently_queried':saved['hidden_container_export']is not None,'original_unchanged':signature(capture(u,original))==signature(saved) and original.get_editor_property('static_mesh')==mesh,'success':True})
        return report
    except Exception as error:
        report.update({'success':False,'error':str(error)})
        raise
    finally:
        try:release_temporary(eas,temp,tc)
        finally:
            temp=tc=None
            target=Path(u.Paths.project_dir())/'private-audit'/'temporary-book-collision-restore.json';target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report,indent=2)+'\n')
