"""Rigidly place the existing six-part console on the solid pier, TV unchanged."""
import json,time,hashlib,shutil,copy
from pathlib import Path
SHA='6768a9972ce5f21533f75fbc49b0860233e877d6adf0348db1398bc80ca1e522'
DELTA=[.5,-20.,0.]
def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 from unreal_import_real_wc import expected_triangles
 from unreal_import_reference_wall_console import positive_triangles
 from unreal_remove_frame_backings import native_triangles,same_triangles
 from home_asset_audit import read_gltf
 assert active_candidate_guard();r=json.loads((CANDIDATE/'private-audit/reference-wall-console-native.json').read_text());assert r['saved']and r['source_sha256']==SHA and len(r['parts'])==6
 proof=json.loads(Path('/workspace/sub01-home-private/reference-living-tv-wall-r4/output/independent-front-clearance.json').read_text());assert proof['schema']=='sub01.wall-console-rigid-outward-shift.v1'and proof['assemblySha256']==SHA and proof['deltaUEcm']==DELTA and proof['unresolvedSourceIntersections']==[]and proof['ok']is True
 wall=json.loads((CANDIDATE/'private-audit/living-tv-wall-r4-native.json').read_text());assert wall['saved']and wall['source_sha256']==proof['source_sha256']
 src=Path('/workspace/sub01-home-private/reference-wall-console-r1/output/wall-console.glb');assert hashlib.sha256(src.read_bytes()).hexdigest()==SHA;doc,blob=read_gltf(src)
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);by={a.get_path_name():a for a in actors};parts=[]
 for i,item in enumerate(r['parts']):
  a=by[item['actor']];cs=a.get_components_by_class(u.StaticMeshComponent);assert len(cs)==1;c=cs[0];assert c.get_path_name()==item['component']and c.get_editor_property('static_mesh').get_path_name().startswith(r['owned_destination']+'/')and not a.get_editor_property('hidden')
  n=next(j for j,node in enumerate(doc['nodes'])if node['name']==a.get_actor_label());expected,_=positive_triangles(expected_triangles(doc,blob,n));actual,_=positive_triangles(native_triangles(u,c));assert same_triangles(expected,actual,.0001),'Current exact console source differs';parts.append((a,c,n))
 mapfile=CANDIDATE/'Content/Sub01Home/ActualHome.umap';backup=CANDIDATE/'Saved/PrivateMapBackups'/('console-solid-pier-'+str(time.time_ns()));backup.mkdir(parents=True);shutil.copy2(mapfile,backup/'ActualHome.umap');saved=False
 try:
  for a,c,n in parts:
   t=before[a.get_path_name()]['transform']['translation'];a.set_actor_location(u.Vector(*[t[k]+DELTA[k]for k in range(3)]),False,False)
  after=snapshot(u,eas.get_all_level_actors());check=copy.deepcopy(after)
  for a,c,n in parts:
   path=a.get_path_name();expected,_=positive_triangles(expected_triangles(doc,blob,n));shifted=[[[p[k]+DELTA[k]for k in range(3)]for p in tri]for tri in expected];actual,_=positive_triangles(native_triangles(u,c));assert same_triangles(shifted,actual,.0001),'Rigid moved complete source differs'
   for t,prior in [(after[path]['transform'],before[path]['transform']),(after[path]['components'][0]['transform'],before[path]['components'][0]['transform'])]:
    assert t['rotation']==prior['rotation']and t['scale']==prior['scale']and all(abs(t['translation'][k]-prior['translation'][k]-DELTA[k])<1e-9 for k in range(3))
   check[path]['transform']=copy.deepcopy(before[path]['transform']);check[path]['components'][0]['transform']=copy.deepcopy(before[path]['components'][0]['transform'])
  assert check==before and active_candidate_guard();saved=True;assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
  result={'schema':'sub01.candidate-console-solid-pier.v1','saved':True,'source_sha256':SHA,'rigid_delta_UE_cm':DELTA,'only_six_parts_changed':True,'full_world_geometry_tolerance_cm':.0001,'tv_input_plane_unchanged':True,'protected_other_actors_exact':True,'game_changed':False,'before':{a.get_path_name():before[a.get_path_name()]for a,c,n in parts},'after':{a.get_path_name():after[a.get_path_name()]for a,c,n in parts},'backup':str(backup),'map_sha256':hashlib.sha256(mapfile.read_bytes()).hexdigest(),'epoch':time.time()};(CANDIDATE/'private-audit/tv-console-solid-pier.json').write_text(json.dumps(result,indent=2)+'\n');return result
 except Exception:
  for a,c,n in parts:a.set_actor_location(u.Vector(*before[a.get_path_name()]['transform']['translation']),False,False)
  assert snapshot(u,eas.get_all_level_actors())==before
  if saved:assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
  raise
