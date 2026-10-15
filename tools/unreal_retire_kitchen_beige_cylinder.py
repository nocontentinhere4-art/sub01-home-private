"""Retire only the owner's rejected complete beige kitchen cylinder actor72."""
from pathlib import Path
import copy,json,shutil,time,hashlib

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 from unreal_component_collision_state import capture,restore
 assert active_candidate_guard();receipt=CANDIDATE/'private-audit/kitchen-beige-cylinder-retired.json';assert not receipt.exists(),'Inspect existing retirement receipt rather than repeating'
 inventory=json.loads((CANDIDATE/'private-audit/kitchen-detail-inventory.json').read_text());assert inventory['read_only']and inventory['world_unchanged'];entry=next(x for x in inventory['components']if x['name']=='full-home_node_72');assert entry['label']=='house-static-15'and entry['original_source']['node']==72 and entry['original_source']['source_triangles']==96
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);a=next(x for x in actors if x.get_path_name()==entry['actor']);cs=a.get_components_by_class(u.StaticMeshComponent);assert len(cs)==1;c=cs[0];assert c.get_path_name()==entry['component']and c.get_editor_property('static_mesh').get_path_name()=='/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Mesh_55.Mesh_55'and before[a.get_path_name()]==entry['snapshot']and not a.get_editor_property('hidden');state=capture(u,c)
 mapfile=CANDIDATE/'Content/Sub01Home/ActualHome.umap';backup=CANDIDATE/'Saved/PrivateMapBackups'/('kitchen-cylinder-'+str(time.time_ns()));backup.mkdir(parents=True);shutil.copy2(mapfile,backup/'ActualHome.umap');saved=False
 try:
  a.set_actor_hidden_in_game(True);a.set_is_temporarily_hidden_in_editor(True);c.set_collision_profile_name('NoCollision');c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION);expected=copy.deepcopy(before);row=expected[a.get_path_name()];row['hidden']=True;row['editor_hidden']=True;row['components'][0]['profile']='NoCollision';row['components'][0]['collision']=str(u.CollisionEnabled.NO_COLLISION);assert snapshot(u,actors)==expected and active_candidate_guard();saved=True;assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level();result={'schema':'sub01.kitchen-beige-cylinder-whole-actor-retirement.v1','saved':True,'retired_original_node':72,'retirement_scope':'entire uniquely bound owner-rejected actor only; original shared mesh/material unchanged','actor':a.get_path_name(),'source_inventory_sha256':hashlib.sha256((CANDIDATE/'private-audit/kitchen-detail-inventory.json').read_bytes()).hexdigest(),'before':before[a.get_path_name()],'after':expected[a.get_path_name()],'protected_all_other_actors_exact':True,'replacement_added':False,'backup':str(backup),'candidate_map_sha256':hashlib.sha256(mapfile.read_bytes()).hexdigest(),'actual_live_game_changed':False,'input_changed':False,'epoch':time.time()};receipt.write_text(json.dumps(result,indent=2)+'\n');return result
 except Exception:
  a.set_actor_hidden_in_game(before[a.get_path_name()]['hidden']);a.set_is_temporarily_hidden_in_editor(before[a.get_path_name()]['editor_hidden']);restore(u,c,state);assert snapshot(u,actors)==before
  if saved:assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
  raise
