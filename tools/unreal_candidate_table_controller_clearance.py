"""Rigidly shift ONLY genuine table controller after the new actual plant fit."""
import json,time,copy
from pathlib import Path

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 from unreal_remove_frame_backings import native_triangles,same_triangles
 assert active_candidate_guard();root=CANDIDATE/'private-audit';assembly=json.loads((root/'genuine-gaming-static-assembly.json').read_text());props=json.loads((root/'genuine-lived-props-native.json').read_text());assert assembly['saved']and props['saved'];proof=json.loads(Path('/workspace/sub01-home-private/real-lived-props-r1/output/independent-controller-plant-clearance.json').read_text());assert proof['ok']and proof['controllerOnlyDeltaYcm']==-20 and proof['fullSourceBVHFindings']==[] and proof['controllerRootTranslationUEcm']==[-257,-25,37.426253204345706]
 offsets=[row['offset_cm']for row in assembly['parts']if row['role']=='dualsense-table'];assert len(offsets)==2 and offsets[0]==offsets[1]and offsets[0][:2]==[-257,-5]
 delta=[0,-20,proof['controllerRootTranslationUEcm'][2]-offsets[0][2]];assert abs(delta[2])<.02
 assert not(root/'table-controller-plant-clearance.json').exists(),'Already installed; do not shift twice'
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);by={a.get_path_name():a for a in actors};selected=[by[r['actor']]for r in assembly['parts']if r['role']=='dualsense-table'];assert len(selected)==2;prior={};expected=copy.deepcopy(before)
 try:
  for a in selected:
   key=a.get_path_name();c=a.get_components_by_class(u.StaticMeshComponent)[0];prior[key]=native_triangles(u,c);t=before[key]['transform']['translation'];a.set_actor_location(u.Vector(t[0],t[1]-20,t[2]+delta[2]),False,False);actual=native_triangles(u,c);assert same_triangles([[[p[0],p[1]-20,p[2]+delta[2]]for p in tri]for tri in prior[key]],actual,.0001,deadline_monotonic=time.monotonic()+25)
   for row in (expected[key]['transform'],expected[key]['components'][0]['transform']):row['translation'][1]-=20;row['translation'][2]+=delta[2]
  assert snapshot(u,actors)==expected and active_candidate_guard();assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level();r={'schema':'sub01.static-table-controller-plant-clearance.v1','saved':True,'controller_delta_UE_cm':delta,'source_proof':proof,'before':{a.get_path_name():before[a.get_path_name()]for a in selected},'after':{a.get_path_name():expected[a.get_path_name()]for a in selected},'only_two_static_controller_actors_changed':True,'geometry_materials_unchanged':True,'game_changed':False,'epoch':time.time()};(root/'table-controller-plant-clearance.json').write_text(json.dumps(r,indent=2)+'\n');return r
 except Exception:
  for a in selected:a.set_actor_location(u.Vector(*before[a.get_path_name()]['transform']['translation']),False,False)
  assert snapshot(u,actors)==before;raise
