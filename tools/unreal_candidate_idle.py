"""Keep the independent Editor warm at one frame/sec for live Game headroom."""
import hashlib,json,time

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 assert active_candidate_guard(u.Paths.project_dir());eas=u.get_editor_subsystem(u.EditorActorSubsystem);before=snapshot(u,list(eas.get_all_level_actors()));map_sha=hashlib.sha256((CANDIDATE/'Content/Sub01Home/ActualHome.umap').read_bytes()).hexdigest();world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world();u.SystemLibrary.execute_console_command(world,'t.MaxFPS 1')
 if u.SystemLibrary.get_console_variable_float_value('t.MaxFPS')!=1:raise RuntimeError('Candidate Editor frame budget did not apply')
 assert snapshot(u,list(eas.get_all_level_actors()))==before and hashlib.sha256((CANDIDATE/'Content/Sub01Home/ActualHome.umap').read_bytes()).hexdigest()==map_sha
 result={'schema':'sub01.private-candidate-warm-idle.v1','epoch':time.time(),'candidate_editor_max_fps':1,'world_map_unchanged':True,'original_game_unchanged':True,'editor_kept_warm':True};(CANDIDATE/'private-audit/candidate-warm-idle.json').write_text(json.dumps(result,indent=2)+'\n');return result
