"""Reversible whole-actor retirement; rejected replacement source is never imported."""
from pathlib import Path
import copy,hashlib,json,shutil,time

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 assert active_candidate_guard()
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors)
 old=[a for a in actors if a.get_name()=='full-home_node_275'];assert len(old)==1;old=old[0];cs=old.get_components_by_class(u.StaticMeshComponent);assert len(cs)==1;c=cs[0]
 path='/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.full-home_node_275'
 assert old.get_path_name()==path and old.get_actor_label()=='modern_coffee_table_01' and c.get_path_name()==path+'.StaticMeshComponent0'
 assert c.get_editor_property('static_mesh').get_path_name()=='/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Cube_003.Cube_003'
 trs=before[path]['components'][0]['transform'];pinned={'translation':[-320.0000286102295,9.971301257610321,.013431409024633467],'rotation':[0.,0.,0.,1.],'scale':[1.1666666269302368]*3}
 assert all(len(trs[k])==len(v)and all(abs(a-b)<=1e-9 for a,b in zip(trs[k],v))for k,v in pinned.items())
 assert not before[path]['hidden']
 mapfile=CANDIDATE/'Content/Sub01Home/ActualHome.umap';backup=CANDIDATE/'Saved/PrivateMapBackups'/('obsolete-table-retirement-'+str(time.time_ns()));backup.mkdir(parents=True);shutil.copy2(mapfile,backup/'ActualHome.umap')
 expected=copy.deepcopy(before);row=expected[path];row['hidden']=True;row['editor_hidden']=True;row['components'][0]['collision']=str(u.CollisionEnabled.NO_COLLISION);row['components'][0]['profile']='NoCollision'
 try:
  old.set_actor_hidden_in_game(True);old.set_is_temporarily_hidden_in_editor(True);c.set_collision_profile_name('NoCollision');c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
  assert snapshot(u,eas.get_all_level_actors())==expected and active_candidate_guard()
  assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
  result={'schema':'sub01.obsolete-living-table-retirement.v1','saved':True,'only_retired_actor':path,'before':before[path],'after':expected[path],'all_other_actors_exact':True,'original_mesh_modified':False,'replacement_table_imported':False,'reason':'Whole obsolete table authorized for retirement; its old placement intersects accepted under-TV cabinet. New proposed replacement was rejected and remains unimported.','backup':str(backup),'map_sha256':hashlib.sha256(mapfile.read_bytes()).hexdigest(),'epoch':time.time(),'actual_game_changed':False}
  (CANDIDATE/'private-audit/obsolete-living-table-retired.json').write_text(json.dumps(result,indent=2)+'\n');return result
 except Exception:
  row=before[path];old.set_actor_hidden_in_game(row['hidden']);old.set_is_temporarily_hidden_in_editor(row['editor_hidden']);c.set_collision_profile_name(row['components'][0]['profile']);name=row['components'][0]['collision'].split('CollisionEnabled.',1)[1].split(':',1)[0];c.set_collision_enabled(getattr(u.CollisionEnabled,name));assert snapshot(u,eas.get_all_level_actors())==before;assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level();raise
