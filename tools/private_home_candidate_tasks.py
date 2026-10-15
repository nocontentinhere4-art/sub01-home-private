"""Fixed, root-requested asset tasks for the independent real-home candidate."""
import importlib,json,time,traceback,os
from pathlib import Path
from private_home_candidate_scope import active_candidate_guard,trusted_json,SCOPE,CANDIDATE
STYLE=Path('/workspace/sub01-home-private/reference-teal-bathroom-r5/output')
PROOF=STYLE.parent/'independent-proof-r2/independent-source-proof.json'
TASKS={'probe','wall_console_preflight','wall_console','teal_bath_preflight','teal_bath','sheer_material_readonly','plant_placement_inventory','bed_finish_preflight','bed_finish','photo_plants_preflight','photo_plants'}
def dispatch(task,probe):
 if task=='probe':return probe
 if task in('wall_console_preflight','wall_console'):
  module=importlib.reload(importlib.import_module('unreal_import_reference_wall_console'));return module.run(dry_run=task.endswith('_preflight'))
 if task in('teal_bath_preflight','teal_bath'):
  module=importlib.reload(importlib.import_module('unreal_import_reference_teal_bathroom'));return module.run(STYLE,PROOF,dry_run=task.endswith('_preflight'))
 if task in('bed_finish_preflight','bed_finish'):
  module=importlib.reload(importlib.import_module('unreal_import_reference_bed_finish'));return module.run(dry_run=task.endswith('_preflight'))
 if task in('photo_plants_preflight','photo_plants'):
  module=importlib.reload(importlib.import_module('unreal_import_candidate_photo_plants'));return module.run(dry_run=task.endswith('_preflight'))
 if task=='plant_placement_inventory':return importlib.reload(importlib.import_module('unreal_candidate_placement_inventory')).run()
 if task=='sheer_material_readonly':return importlib.reload(importlib.import_module('unreal_sheer_material_readonly')).run()
 raise RuntimeError('No free-form candidate task execution')
# importlib.reload preserves module globals: retain this latch across hot edits.
if '_busy' not in globals():_busy=False

def poll(seen,probe):
 global _busy
 if _busy:return
 _busy=True
 try:
  return _poll_once(seen,probe)
 finally:_busy=False

def _poll_once(seen,probe):
 assert active_candidate_guard(CANDIDATE);scope=trusted_json(SCOPE)
 for request in sorted((SCOPE.parent/'candidate-requests').glob('*.json')):
  if request.name in seen:continue
  body=trusted_json(request);task=body.get('task');assert body.get('schema')=='sub01.private-next-home-task.v1'and body.get('candidate_editor_pid')==os.getpid();assert task in TASKS and task in scope.get('allowed_tasks',[])
  assert body.get('world_mutations_authorized')is (task in('wall_console','teal_bath','bed_finish','photo_plants')),'Explicit candidate-only mutation phase required'
  seen.add(request.name);result={'schema':'sub01.private-next-home-task-result.v1','task':task,'editor_pid':os.getpid(),'started_epoch':time.time(),'original_game_preserved':False,'promoted_to_live':False}
  try:
   result['result']=dispatch(task,probe);assert active_candidate_guard(CANDIDATE);result['ok']=True;result['original_game_preserved']=True
  except Exception as exc:
   result.update(ok=False,error=type(exc).__name__,message=str(exc),traceback=traceback.format_exc())
  result['finished_epoch']=time.time();(CANDIDATE/'private-audit'/(request.stem+'-result.json')).write_text(json.dumps(result,indent=2)+'\n')
