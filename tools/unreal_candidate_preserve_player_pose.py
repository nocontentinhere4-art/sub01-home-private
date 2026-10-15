"""Set only existing private spawn transforms from exact fresh live reflection."""
from pathlib import Path
import json,hashlib,time,shutil,copy
def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE,trusted_json
 from unreal_import_reference_entry import snapshot
 assert active_candidate_guard();approved=trusted_json(Path('/run/sub01-home-private/next-pawn-pose-approved.json'));assert approved['native_pid']==193148 and approved['native_start_ticks']==978377926 
 LOCATION=approved['location'];ROTATION=approved['rotation'];assert len(LOCATION)==len(ROTATION)==3
 import math
 assert all(isinstance(v,(float,int))and math.isfinite(v)for v in LOCATION+ROTATION)and max(abs(v)for v in LOCATION)<2000
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);starts=[a for a in actors if isinstance(a,u.PlayerStart)];assert len(starts)==2 and {a.get_name()for a in starts}=={'PlayerStart_0','PlayerStart_1'}
 prior=CANDIDATE/'private-audit/next-spawn-pose-preserved.json'
 if prior.exists():
  previous=json.loads(prior.read_text());assert previous['saved']
  for a in starts:assert before[a.get_path_name()]==previous['after'][a.get_path_name()]
 else:
  for a in starts:assert list(before[a.get_path_name()]['transform']['translation'])==[200.,310.,94.]
 backup=CANDIDATE/'Saved/PrivateMapBackups'/('preserved-player-pose-'+str(time.time_ns()));backup.mkdir(parents=True);shutil.copy2(CANDIDATE/'Content/Sub01Home/ActualHome.umap',backup/'ActualHome.umap')
 try:
  for a in starts:a.set_actor_location_and_rotation(u.Vector(*LOCATION),u.Rotator(pitch=ROTATION[0],yaw=ROTATION[1],roll=0),False,False)
  after=snapshot(u,actors);check=copy.deepcopy(after)
  for a in starts:
   key=a.get_path_name();assert all(abs(after[key]['transform']['translation'][i]-LOCATION[i])<1e-6 for i in range(3));check[key]=before[key]
  assert check==before and active_candidate_guard();assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level();r={'schema':'sub01.next-private-spawn-pose-preserved.v1','saved':True,'source_game_identity':[193148,978377926],'location':LOCATION,'rotation':ROTATION,'only_existing_two_playerstarts_changed':True,'before':{a.get_path_name():before[a.get_path_name()]for a in starts},'after':{a.get_path_name():after[a.get_path_name()]for a in starts},'backup':str(backup),'map_sha256':hashlib.sha256((CANDIDATE/'Content/Sub01Home/ActualHome.umap').read_bytes()).hexdigest(),'epoch':time.time()};(CANDIDATE/'private-audit/next-spawn-pose-preserved.json').write_text(json.dumps(r,indent=2)+'\n');return r
 except Exception:
  for a in starts:
   t=before[a.get_path_name()]['transform'];tr=u.Transform();tr.translation=u.Vector(*t['translation']);tr.rotation=u.Quat(*t['rotation']);tr.scale3d=u.Vector(*t['scale']);a.set_actor_transform(tr,False,True)
  assert snapshot(u,actors)==before;raise
