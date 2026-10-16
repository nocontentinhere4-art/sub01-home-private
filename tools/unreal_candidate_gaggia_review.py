"""Actual corrected kitchen in saved candidate; isolated Editor cameras only."""
import importlib,json,hashlib,time

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 import unreal_candidate_visual_review as review
 assert active_candidate_guard()and review._handle is None;review=importlib.reload(review);assert json.loads((CANDIDATE/'private-audit/gaggia-gran-native.json').read_text())['saved']
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);before=snapshot(u,eas.get_all_level_actors());mapfile=CANDIDATE/'Content/Sub01Home/ActualHome.umap';mapsha=hashlib.sha256(mapfile.read_bytes()).hexdigest();prior=u.EditorLevelLibrary.get_level_viewport_camera_info();world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
 def restore(error=None):
  u.EditorLevelLibrary.set_level_viewport_camera_info(*prior);u.SystemLibrary.execute_console_command(world,'t.MaxFPS 1');assert snapshot(u,eas.get_all_level_actors())==before and hashlib.sha256(mapfile.read_bytes()).hexdigest()==mapsha and active_candidate_guard();(CANDIDATE/'private-audit/genuine-gaggia-view-restored.json').write_text(json.dumps({'schema':'sub01.actual-genuine-gaggia-view-restored.v1','world_camera_map_restored':True,'actual_game_changed':False,'capture_error':str(error)if error else None,'epoch':time.time()},indent=2)+'\n');return True
 u.SystemLibrary.execute_console_command(world,'t.MaxFPS 15')
 try:return review.run([('kitchen-gaggia-overview',(-175,-190,158),(-12,-117,0)),('genuine-gaggia-close',(-124,-281,124),(-12,-90,0)),('genuine-gaggia-and-plant',(-100,-270,140),(-17,-107.5,0))],capture_delay=7,initial_delay=3,on_finish=restore)
 except Exception:restore('setup refused');raise
