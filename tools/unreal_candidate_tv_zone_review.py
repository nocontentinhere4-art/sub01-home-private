"""One actual lit candidate viewport, saved zone only, no live Game inputs."""
from pathlib import Path
import hashlib,json,time

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 import importlib
 import unreal_candidate_visual_review as review
 assert review._handle is None
 review=importlib.reload(review)
 assert active_candidate_guard()and review._handle is None
 receipt=json.loads((CANDIDATE/'private-audit/reference-living-tv-zone-native.json').read_text());assert receipt['saved']and receipt['protected_other_actors_exact']
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);mapfile=CANDIDATE/'Content/Sub01Home/ActualHome.umap';mapsha=hashlib.sha256(mapfile.read_bytes()).hexdigest();prior=u.EditorLevelLibrary.get_level_viewport_camera_info()
 # Old table must already be replaced/retired before photographing this zone:
 # its obsolete placement intersects the newly positioned genuine cabinet.
 old=[a for a in actors if a.get_name()=='full-home_node_275'];assert len(old)==1 and old[0].get_editor_property('hidden')and all(c.get_collision_enabled()==u.CollisionEnabled.NO_COLLISION for c in old[0].get_components_by_class(u.StaticMeshComponent))
 def finish(error=None):
  u.EditorLevelLibrary.set_level_viewport_camera_info(*prior);world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world();u.SystemLibrary.execute_console_command(world,'t.MaxFPS 1');assert snapshot(u,eas.get_all_level_actors())==before and hashlib.sha256(mapfile.read_bytes()).hexdigest()==mapsha and active_candidate_guard();(CANDIDATE/'private-audit/living-tv-zone-view-restored.json').write_text(json.dumps({'schema':'sub01.actual-living-tv-zone-viewport-restored.v1','camera_restored':True,'world_restored_exact':True,'map_unchanged':True,'live_game_input_changed':False,'capture_error':str(error)if error else None,'epoch':time.time()},indent=2)+'\n')
 world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world();u.SystemLibrary.execute_console_command(world,'t.MaxFPS 15')
 try:return review.run([('living-tv-zone',(-230,-210,160),(-3,126.1932,0))],capture_delay=3,initial_delay=3,on_finish=finish)
 except Exception:finish('setup refused');raise
