"""Read-only saved-book collision API/configuration inventory; no BodyInstance copies."""
import json
import hashlib
from pathlib import Path


def run(u=None):
    if u is None:
        import unreal as u
    actors=list(u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors())
    found=[a for a in actors if a.get_actor_label()=='SUB01_RealBook_01']
    if len(found)!=1:raise RuntimeError('Exact saved book01 actor not unique')
    cs=found[0].get_components_by_class(u.StaticMeshComponent)
    if len(cs)!=1 or not cs[0].get_editor_property('static_mesh').get_path_name().startswith('/Game/Sub01Home/RealBooks/V_611a3d848858/'):
        raise RuntimeError('Exact original611 saved book binding required')
    c=cs[0]
    result={'schema':'sub01.saved-book-collision-audit.v1','read_only':True,'scene_mutations':0,
            'actor':found[0].get_path_name(),'component':c.get_path_name(),
            'profile':str(c.get_collision_profile_name()),'enabled':str(c.get_collision_enabled()),
            'apis':{},'channels':{},'body_instance_properties':{},'errors':{}}
    for name in ('get_collision_object_type','set_collision_object_type','get_collision_response_to_channel',
                 'set_collision_response_to_channel','get_collision_profile_name','set_collision_profile_name',
                 'get_collision_enabled','set_collision_enabled','get_generate_overlap_events','set_generate_overlap_events'):
        result['apis'][name]=callable(getattr(c,name,None))
    try:result['object_type']=str(c.get_collision_object_type())
    except Exception as error:result['errors']['object_type']=str(error)
    try:result['generate_overlap_events']=bool(c.get_generate_overlap_events())
    except Exception as error:result['errors']['generate_overlap_events']=str(error)
    for name in sorted(dir(u.CollisionChannel)):
        if not name.startswith('ECC_')or name in('ECC_MAX','ECC_OVERLAP_ALL_DEPRECATED'):continue
        try:result['channels'][name]=str(c.get_collision_response_to_channel(getattr(u.CollisionChannel,name)))
        except Exception as error:result['errors']['channel.'+name]=str(error)
    result['enum_cast_available']=callable(getattr(u.CollisionChannel,'cast',None))
    result['all32_indexed_channels']={}
    if result['enum_cast_available']:
        for index in range(32):
            try:
                channel=u.CollisionChannel.cast(index)
                result['all32_indexed_channels'][str(index)]={'enum':str(channel),'response':str(c.get_collision_response_to_channel(channel))}
            except Exception as error:result['errors']['indexed_channel.'+str(index)]=str(error)
    try:result['generate_overlap_events_property']=bool(c.get_editor_property('generate_overlap_events'))
    except Exception as error:result['errors']['generate_overlap_events_property']=str(error)
    try:
        body=c.get_editor_property('body_instance')
        for name in ('collision_profile_name','object_type','collision_enabled','collision_responses','notify_rigid_body_collision','use_ccd'):
            try:result['body_instance_properties'][name]=str(body.get_editor_property(name))
            except Exception as error:result['errors']['body_instance.'+name]=str(error)
    except Exception as error:result['errors']['body_instance']=str(error)
    try:result['use_default_collision']=bool(c.get_editor_property('use_default_collision'))
    except Exception as error:result['errors']['use_default_collision']=str(error)
    result['default_instances']={}
    original=c.get_editor_property('static_mesh');key=original.get_path_name();name='Mesh_'+hashlib.sha256(key.encode()).hexdigest()[:12]
    clone_path='/Game/Sub01Home/RealOfficeBooks/V_611a3d848858_FullSource_9279b89011474be0afe7704b39f800f9/'+name+'.'+name
    clone=u.find_object(None,clone_path)
    for label,mesh in(('original',original),('loaded_clone',clone)):
        row={'loaded':mesh is not None}
        if mesh is not None:
            try:
                default=mesh.get_editor_property('body_setup').get_editor_property('default_instance')
                for field in('collision_profile_name','object_type','collision_enabled','collision_responses'):
                    value=default.get_editor_property(field);row[field]=str(value)
                    if field=='collision_responses':
                        row['responses_copy_available']=callable(getattr(value,'copy',None))
                        row['responses_export_available']=callable(getattr(value,'export_text',None))
                        if row['responses_export_available']:row['responses_export_text']=value.export_text()
            except Exception as error:row['error']=str(error)
        result['default_instances'][label]=row
    try:
        response=c.get_editor_property('body_instance').get_editor_property('collision_responses')
        result['component_responses_copy_available']=callable(getattr(response,'copy',None))
        if callable(getattr(response,'export_text',None)):result['component_responses_export_text']=response.export_text()
    except Exception as error:result['errors']['component_responses_export_text']=str(error)
    out=Path(u.Paths.project_dir())/'private-audit'/'saved-book-collision-state-audit.json'
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n');return result
