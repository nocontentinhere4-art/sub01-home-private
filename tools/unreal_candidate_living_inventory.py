"""Read exact existing TV, rug, window and cabinet state before layout mutations."""
import json,os,time,hashlib
from pathlib import Path

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 from unreal_extend_private_entry import world_bounds
 assert active_candidate_guard();eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);rows=[]
 for a in actors:
  for c in a.get_components_by_class(u.StaticMeshComponent):
   mesh=c.get_editor_property('static_mesh')
   if not mesh:continue
   b=world_bounds(u,c);span=[b['max'][i]-b['min'][i]for i in range(3)];label=a.get_actor_label();name=a.get_name()
   selected=(name in ['full-home_node_61','full-home_node_130','full-home_node_131','full-home_node_172','full-home_node_173','full-home_node_174','full-home_node_175','full-home_node_275']or 'rug'in label.lower()or label=='house-static-8'or label.startswith('SUB01ReferenceMedia_')or label.startswith('WCPart')or label.startswith('SUB01_RealWindow_')or(b['max'][2]<15 and b['min'][0]<0 and span[0]>70 and span[1]>70))
   if not selected:continue
   rows.append({'actor':a.get_path_name(),'name':name,'label':label,'component':c.get_path_name(),'mesh':mesh.get_path_name(),'bounds_cm':b,'actor_hidden':bool(a.get_editor_property('hidden')),'editor_hidden':a.is_temporarily_hidden_in_editor(),'actor_collision':bool(a.get_actor_enable_collision()),'visible':bool(c.get_editor_property('visible')),'component_hidden_in_game':bool(c.get_editor_property('hidden_in_game')),'collision':str(c.get_collision_enabled()),'collision_profile':str(c.get_collision_profile_name()),'actor_tags':[str(v)for v in a.get_editor_property('tags')],'component_tags':[str(v)for v in c.get_editor_property('component_tags')],'snapshot':before[a.get_path_name()]})
 assert snapshot(u,list(eas.get_all_level_actors()))==before
 report={'schema':'sub01.actual-candidate-living-inventory.v1','editor_pid':os.getpid(),'read_only':True,'world_unchanged':True,'map_sha256':hashlib.sha256((CANDIDATE/'Content/Sub01Home/ActualHome.umap').read_bytes()).hexdigest(),'components':rows,'epoch':time.time()};(CANDIDATE/'private-audit/living-layout-inventory.json').write_text(json.dumps(report,indent=2)+'\n');return {'read_only':True,'world_unchanged':True,'components':len(rows),'editor_pid':os.getpid()}
