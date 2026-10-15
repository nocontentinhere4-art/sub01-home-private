"""Actual saved manufacturer sofa in the complete candidate home, no scene edits."""
import importlib,json,hashlib,time

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 import unreal_candidate_visual_review as review
 assert active_candidate_guard()and review._handle is None;review=importlib.reload(review);receipt=json.loads((CANDIDATE/'private-audit/genuine-gaming-static-assembly.json').read_text());assert receipt['saved']and receipt['tv_input_plane_unchanged']
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);before=snapshot(u,eas.get_all_level_actors());mapfile=CANDIDATE/'Content/Sub01Home/ActualHome.umap';mapsha=hashlib.sha256(mapfile.read_bytes()).hexdigest();prior=u.EditorLevelLibrary.get_level_viewport_camera_info();world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
 def restore(error=None):
  u.EditorLevelLibrary.set_level_viewport_camera_info(*prior);u.SystemLibrary.execute_console_command(world,'t.MaxFPS 1');assert snapshot(u,eas.get_all_level_actors())==before and hashlib.sha256(mapfile.read_bytes()).hexdigest()==mapsha and active_candidate_guard();(CANDIDATE/'private-audit/genuine-gaming-view-restored.json').write_text(json.dumps({'schema':'sub01.actual-genuine-gaming-view-restored.v1','world_camera_map_restored':True,'actual_game_changed':False,'capture_error':str(error)if error else None,'epoch':time.time()},indent=2)+'\n');return True
 u.SystemLibrary.execute_console_command(world,'t.MaxFPS 15')
 try:return review.run([('genuine-complete-living',(-90,220,165),(-10,-141.7,0)),('genuine-ps5-dock',(-290,-205,158),(-5,132,0)),('genuine-table-controller',(-225,30,108),(-52,-132,0))],capture_delay=5,initial_delay=3,on_finish=restore)
 except Exception:restore('setup refused');raise
