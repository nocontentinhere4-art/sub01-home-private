"""Single explicit recovery: only two PlayerStarts, no Game exists, no geometry edit."""
from pathlib import Path
import json,hashlib,time,shutil,copy

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE,trusted_json,SCOPE
 from unreal_import_reference_entry import snapshot
 assert active_candidate_guard();a=trusted_json(SCOPE.parent/'expired-runtime-recovery-approved.json');eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);starts=[x for x in actors if isinstance(x,u.PlayerStart)];assert len(starts)==2 and{x.get_name()for x in starts}=={'PlayerStart_0','PlayerStart_1'}
 mapfile=CANDIDATE/'Content/Sub01Home/ActualHome.umap';assert hashlib.sha256(mapfile.read_bytes()).hexdigest()==a['live_map_before_sha256'];backup=CANDIDATE/'Saved/PrivateMapBackups'/('expired-runtime-'+str(time.time_ns()));backup.mkdir();shutil.copy2(mapfile,backup/'ActualHome.umap')
 for x in starts:x.set_actor_location_and_rotation(u.Vector(*a['last_observed_capsule_cm']),u.Rotator(pitch=a['recovery_pitch_degrees'],yaw=a['derived_yaw_degrees'],roll=0),False,False)
 after=snapshot(u,actors);check=copy.deepcopy(after)
 for x in starts:check[x.get_path_name()]=before[x.get_path_name()]
 assert check==before and not Path('/proc/225250').exists();assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
 r={'saved':True,'only_two_playerstarts_changed':True,'before':{x.get_path_name():before[x.get_path_name()]for x in starts},'after':{x.get_path_name():after[x.get_path_name()]for x in starts},'map_before_sha256':a['live_map_before_sha256'],'map_after_sha256':hashlib.sha256(mapfile.read_bytes()).hexdigest(),'location_source':'last existing native Game tick log, rounded to .001 cm','orientation_limit':'yaw derived from public camera and physical offset; pitch not last-measured, retained last reflected pitch','backup':str(backup),'input_sent':False,'epoch':time.time()}
 (CANDIDATE/'private-audit/expired-runtime-spawn-recovery.json').write_text(json.dumps(r,indent=2));return r
