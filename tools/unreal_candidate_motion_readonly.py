"""Read-only adapter for externally reviewed candidate scene probes."""
import hashlib,json,time

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 import device_motion_integration_probe
 assert active_candidate_guard()
 actors=u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors();before=snapshot(u,actors)
 mapfile=CANDIDATE/'Content/Sub01Home/ActualHome.umap';old=hashlib.sha256(mapfile.read_bytes()).hexdigest()
 result=device_motion_integration_probe.run()
 assert active_candidate_guard()and snapshot(u,u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors())==before
 assert hashlib.sha256(mapfile.read_bytes()).hexdigest()==old
 return result
