"""Inspect actual TV material/exposure and bracket world bounds, no changes."""
import json,time,hashlib

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 from unreal_extend_private_entry import world_bounds
 from unreal_sheer_material_readonly import root_graph,_property
 from unreal_candidate_lighting_readonly import read,POST
 assert active_candidate_guard();eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);mel=u.MaterialEditingLibrary;rows=[]
 for a in actors:
  if a.get_name()not in('full-home_node_130','full-home_node_131')and not a.get_actor_label().startswith(('WCPart','LW')):continue
  for c in a.get_components_by_class(u.StaticMeshComponent):
   mats=[]
   for i in range(c.get_num_materials()):
    m=c.get_material(i);v={'slot':i,'material':m.get_path_name(),'class':m.get_class().get_name(),'graph':root_graph(u,m)}
    if isinstance(m,u.MaterialInstance):
     v['vectors']={str(n):_property(mel.get_material_instance_vector_parameter_value(m,n),'r')if False else [float(getattr(mel.get_material_instance_vector_parameter_value(m,n),k))for k in('r','g','b','a')]for n in mel.get_vector_parameter_names(m)}
     v['scalars']={str(n):float(mel.get_material_instance_scalar_parameter_value(m,n))for n in mel.get_scalar_parameter_names(m)}
     v['textures']={str(n):(lambda t:t.get_path_name()if t else None)(mel.get_material_instance_texture_parameter_value(m,n))for n in mel.get_texture_parameter_names(m)}
    mats.append(v)
   rows.append({'actor':a.get_path_name(),'label':a.get_actor_label(),'hidden':bool(a.get_editor_property('hidden')),'bounds':world_bounds(u,c),'materials':mats})
 live=u.load_asset('/Game/Sub01Home/Devices/M_Sub01LivePC.M_Sub01LivePC');posts=[{'actor':a.get_path_name(),'settings':read(a.get_editor_property('settings'),POST)}for a in actors if isinstance(a,u.PostProcessVolume)]
 assert snapshot(u,eas.get_all_level_actors())==before and active_candidate_guard()
 r={'schema':'sub01.candidate-tv-screen-readonly.v1','epoch':time.time(),'rows':rows,'actual_live_screen_parent_graph':root_graph(u,live)if live else None,'post_process':posts,'world_unchanged':True,'game_modified':False}
 p=CANDIDATE/'private-audit/tv-screen-readonly.json';p.write_text(json.dumps(r,indent=2)+'\n');return {'read_only':True,'report':str(p),'rows':len(rows)}
