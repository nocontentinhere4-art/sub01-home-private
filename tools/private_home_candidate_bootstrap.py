"""Read-only probe and fixed reviewed queue for the isolated next-home Editor."""
import hashlib,json,os,sys,time,traceback
from pathlib import Path
import unreal
sys.path.insert(0,'/home/unreal/runtime-tools')
from private_home_candidate_scope import active_candidate_guard,CANDIDATE,SCOPE,trusted_json
assert active_candidate_guard(unreal.Paths.project_dir())
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
audit=CANDIDATE/'private-audit';world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world();assert world and world.get_path_name()=='/Game/Sub01Home/ActualHome.ActualHome'
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors();components=[c for a in actors for c in a.get_components_by_class(unreal.StaticMeshComponent)]
nullrhi=b'-nullrhi'in Path('/proc/self/cmdline').read_bytes().split(b'\0')
receipt={'schema':'sub01.private-next-home-candidate-probe.v1','editor_pid':os.getpid(),'editor_start_ticks':int(Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]),'candidate_project':str(CANDIDATE),'world':world.get_path_name(),'nullrhi_requested':nullrhi,'actor_count':len(actors),'static_component_count':len(components),'missing_static_meshes':[c.get_path_name()for c in components if not c.get_editor_property('static_mesh')],'live_home_unchanged':True,'map_saved':False,'epoch':time.time()}
assert not receipt['missing_static_meshes'];(audit/('candidate-probe.json'if nullrhi else'candidate-vulkan-probe.json')).write_text(json.dumps(receipt,indent=2)+'\n');unreal.log('SUB01_ISOLATED_CANDIDATE_PROBE_PASS '+json.dumps(receipt))
# The initial authority permits read-only probe only. No original shared task
# queue, runtime activity/tick bridge, viewer or input service is installed here.
# A new exact Editor identity must never re-run the previous Editor's completed
# requests. The root relauncher independently checks that none remain pending.
_seen={p.name for p in(SCOPE.parent/'candidate-requests').glob('*.json')};_next=0
def tick(delta):
 global _next
 if time.time()<_next:return
 _next=time.time()+10
 try:
  assert active_candidate_guard(unreal.Paths.project_dir());scope=trusted_json(SCOPE)
  import importlib
  tasks=importlib.reload(importlib.import_module('private_home_candidate_tasks'))
  tasks.poll(_seen,receipt)
 except Exception as exc:
  (audit/'candidate-guard-refusal.json').write_text(json.dumps({'epoch':time.time(),'error':type(exc).__name__,'message':str(exc),'native_mutations_attempted':False},indent=2)+'\n')
_handle=unreal.register_slate_post_tick_callback(tick)
