"""Fixed, root-requested asset tasks for the independent real-home candidate."""
import importlib,json,time,traceback,os,sys
from pathlib import Path
from private_home_candidate_scope import active_candidate_guard,trusted_json,SCOPE,CANDIDATE
STYLE=Path('/workspace/sub01-home-private/reference-teal-bathroom-r5/output')
PROOF=STYLE.parent/'independent-proof-r2/independent-source-proof.json'
TASKS={'gaggia_water_probe','real_gaggia','gaggia_review','genuine_indoor_syngonium','official_grohe_faucet','kitchen_corrections_view','retire_kitchen_cylinder','kitchen_detail_inventory','refresh_scope_adapter','table_controller_clearance','scanned_collectible','genuine_lived_props','dualsense_lightbars','ps5_lightbars','genuine_gaming_review','preserve_spawn_pose','genuine_gaming_assembly','original_ps5_assets', 'dualsense_material_readonly','real_dualsense_view','real_dualsense_assets','muuto_around_table','muuto_sofa_view','muuto_rest_sofa','owner_idle_preflight','owner_idle','idle_component_pose_audit','idle_first_person_review','tv_console_shift','tv_preview_exposure','living_wall_r4','tv_screen_readonly','retire_obsolete_living_table','probe','wall_console_preflight','wall_console','teal_bath_preflight','teal_bath','sheer_material_readonly','plant_placement_inventory','bed_finish_preflight','bed_finish','photo_plants_preflight','photo_plants','visual_review','visual_review_cancel','lighting_readonly','settled_review','practical_light_comparison','plant_material_readonly','practical_light_refinement','kitchen_grain_preflight','kitchen_grain','owned_alpha_probe','chosen_bath4000','bed_lamp_readonly','mirror_readonly','bed_lamp_source','aligned_bed_lamp','save_bed_lamp','chosen_full_review','warm_idle','owner_gltf_preflight','owner_gltf','owner_fbx_preflight','owner_fbx','owner_material_readonly','owner_body_pose_audit','owner_source_materials','owner_first_person_review','owner_component_pose_audit','owner_grip_preflight','owner_grip','reference_controller_assets','grip_body_pose_audit','grip_component_pose_audit','living_inventory','living_rug_readonly','living_tv_zone_preflight','living_tv_zone','living_tv_zone_view'}
def dispatch(task,probe):
 if task=='gaggia_water_probe':return importlib.reload(importlib.import_module('unreal_diagnose_gaggia_water')).run()
 if task=='real_gaggia':return importlib.reload(importlib.import_module('unreal_import_real_gaggia')).run(dry_run=False)
 if task=='gaggia_review':return importlib.reload(importlib.import_module('unreal_candidate_gaggia_review')).run()
 if task=='genuine_indoor_syngonium':return importlib.reload(importlib.import_module('unreal_import_genuine_indoor_syngonium')).run(dry_run=False)
 if task=='official_grohe_faucet':return importlib.reload(importlib.import_module('unreal_import_official_grohe_faucet')).run(dry_run=False)
 if task=='kitchen_corrections_view':return importlib.reload(importlib.import_module('unreal_candidate_kitchen_corrections_review')).run()
 if task=='retire_kitchen_cylinder':return importlib.reload(importlib.import_module('unreal_retire_kitchen_beige_cylinder')).run()
 if task=='kitchen_detail_inventory':return importlib.reload(importlib.import_module('unreal_candidate_kitchen_detail_inventory')).run()
 if task=='refresh_scope_adapter':return {'scope_adapter_loaded':importlib.reload(importlib.import_module('private_home_candidate_scope')).active_candidate_guard()}
 if task=='table_controller_clearance':return importlib.reload(importlib.import_module('unreal_candidate_table_controller_clearance')).run()
 if task=='scanned_collectible':return importlib.reload(importlib.import_module('unreal_import_scanned_collectible')).run(dry_run=False)
 if task=='genuine_lived_props':return importlib.reload(importlib.import_module('unreal_import_genuine_lived_props')).run(dry_run=False)
 if task=='dualsense_lightbars':return importlib.reload(importlib.import_module('unreal_candidate_dualsense_lightbars')).run()
 if task=='ps5_lightbars':return importlib.reload(importlib.import_module('unreal_candidate_ps5_lightbars')).run()
 if task=='genuine_gaming_review':return importlib.reload(importlib.import_module('unreal_candidate_genuine_gaming_review')).run()
 if task=='genuine_gaming_assembly':return importlib.reload(importlib.import_module('unreal_candidate_genuine_gaming_assembly')).run()
 if task=='preserve_spawn_pose':return importlib.reload(importlib.import_module('unreal_candidate_preserve_player_pose')).run()
 if task=='original_ps5_assets':return importlib.reload(importlib.import_module('unreal_import_original_ps5_assets')).run()
 if task=='retire_obsolete_living_table':return importlib.reload(importlib.import_module('unreal_retire_obsolete_living_table')).run()
 if task=='tv_screen_readonly':return importlib.reload(importlib.import_module('unreal_candidate_tv_screen_readonly')).run()
 if task=='tv_preview_exposure':return importlib.reload(importlib.import_module('unreal_candidate_tv_preview_material')).run()
 if task=='living_wall_r4':return importlib.reload(importlib.import_module('unreal_candidate_tv_wall_r4')).run()
 if task=='tv_console_shift':return importlib.reload(importlib.import_module('unreal_candidate_tv_console_shift')).run()
 if task in('owner_idle_preflight','owner_idle'):return importlib.reload(importlib.import_module('unreal_import_anatomical_idle_candidate')).run(dry_run=task.endswith('_preflight'))
 if task=='idle_component_pose_audit':return importlib.reload(importlib.import_module('unreal_anatomical_component_pose_audit')).run(idle=True)
 if task=='idle_first_person_review':return importlib.reload(importlib.import_module('unreal_anatomical_first_person_review')).run(idle=True)
 if task=='muuto_rest_sofa':return importlib.reload(importlib.import_module('unreal_import_muuto_rest_sofa')).run(dry_run=False)
 if task=='muuto_sofa_view':return importlib.reload(importlib.import_module('unreal_candidate_muuto_sofa_review')).run()
 if task=='muuto_around_table':return importlib.reload(importlib.import_module('unreal_import_manufacturer_around_table')).run(dry_run=False)
 if task=='real_dualsense_assets':return importlib.reload(importlib.import_module('unreal_import_real_dualsense')).run()
 if task=='real_dualsense_view':return importlib.reload(importlib.import_module('unreal_candidate_real_dualsense_review')).run()
 if task=='dualsense_material_readonly':return importlib.reload(importlib.import_module('unreal_dualsense_material_readonly')).run()
 if task=='probe':return probe
 if task=='living_tv_zone_view':return importlib.reload(importlib.import_module('unreal_candidate_tv_zone_review')).run()
 if task=='living_rug_readonly':return importlib.reload(importlib.import_module('unreal_probe_retired_living_rug')).run()
 if task in('living_tv_zone_preflight','living_tv_zone'):return importlib.reload(importlib.import_module('unreal_import_reference_living_tv_zone')).run(dry_run=task.endswith('_preflight'))
 if task=='living_inventory':return importlib.reload(importlib.import_module('unreal_candidate_living_inventory')).run()
 if task=='grip_body_pose_audit':return importlib.reload(importlib.import_module('unreal_anatomical_body_pose_audit')).run(grip=True)
 if task=='grip_component_pose_audit':return importlib.reload(importlib.import_module('unreal_anatomical_component_pose_audit')).run(grip=True)
 if task=='reference_controller_assets':
  importlib.reload(importlib.import_module('unreal_remove_frame_backings'));return importlib.reload(importlib.import_module('unreal_import_reference_controller_candidate')).run(dry_run=False)
 if task in('owner_grip_preflight','owner_grip'):return importlib.reload(importlib.import_module('unreal_import_anatomical_grip_candidate')).run(dry_run=task.endswith('_preflight'))
 if task=='owner_component_pose_audit':return importlib.reload(importlib.import_module('unreal_anatomical_component_pose_audit')).run()
 if task=='owner_first_person_review':return importlib.reload(importlib.import_module('unreal_anatomical_first_person_review')).run()
 if task=='owner_source_materials':return importlib.reload(importlib.import_module('unreal_anatomical_source_materials')).run()
 if task=='owner_body_pose_audit':return importlib.reload(importlib.import_module('unreal_anatomical_body_pose_audit')).run()
 if task=='owner_material_readonly':return importlib.reload(importlib.import_module('unreal_anatomical_material_inventory')).run()
 if task in('owner_fbx_preflight','owner_fbx'):return importlib.reload(importlib.import_module('unreal_import_anatomical_owner_candidate')).run(dry_run=task.endswith('_preflight'),fbx=True)
 if task in('owner_gltf_preflight','owner_gltf'):return importlib.reload(importlib.import_module('unreal_import_anatomical_owner_candidate')).run(dry_run=task.endswith('_preflight'))
 if task in('wall_console_preflight','wall_console'):
  module=importlib.reload(importlib.import_module('unreal_import_reference_wall_console'));return module.run(dry_run=task.endswith('_preflight'))
 if task in('teal_bath_preflight','teal_bath'):
  module=importlib.reload(importlib.import_module('unreal_import_reference_teal_bathroom'));return module.run(STYLE,PROOF,dry_run=task.endswith('_preflight'))
 if task in('bed_finish_preflight','bed_finish'):
  module=importlib.reload(importlib.import_module('unreal_import_reference_bed_finish'));return module.run(dry_run=task.endswith('_preflight'))
 if task in('photo_plants_preflight','photo_plants'):
  module=importlib.reload(importlib.import_module('unreal_import_candidate_photo_plants'));return module.run(dry_run=task.endswith('_preflight'))
 if task in('kitchen_grain_preflight','kitchen_grain'):return importlib.reload(importlib.import_module('unreal_candidate_kitchen_grain')).run(dry_run=task.endswith('_preflight'))
 if task in('practical_light_comparison','practical_light_refinement'):
  importlib.reload(importlib.import_module('unreal_candidate_visual_review'));return importlib.reload(importlib.import_module('unreal_candidate_practical_light_comparison')).run(refinement=task.endswith('_refinement'))
 if task=='warm_idle':return importlib.reload(importlib.import_module('unreal_candidate_idle')).run()
 if task=='chosen_full_review':
  for n in ['chosen-bed-lamp-native.json','reference-photo-plants-native.json','reference-kitchen-grain-native.json']:
   assert json.loads((CANDIDATE/'private-audit'/n).read_text())['saved']is True
  return importlib.reload(importlib.import_module('unreal_candidate_visual_review')).run()
 if task=='save_bed_lamp':return importlib.reload(importlib.import_module('unreal_candidate_save_bed_lamp')).run()
 if task=='aligned_bed_lamp':
  importlib.reload(importlib.import_module('unreal_candidate_visual_review'));return importlib.reload(importlib.import_module('unreal_candidate_aligned_bed_lamp')).run()
 if task=='bed_lamp_source':return importlib.reload(importlib.import_module('unreal_candidate_bed_lamp_source')).run()
 if task=='mirror_readonly':return importlib.reload(importlib.import_module('unreal_candidate_mirror_readonly')).run()
 if task=='bed_lamp_readonly':return importlib.reload(importlib.import_module('unreal_candidate_bed_lamp_readonly')).run()
 if task=='chosen_bath4000':return importlib.reload(importlib.import_module('unreal_candidate_chosen_lights')).run()
 if task=='owned_alpha_probe':return importlib.reload(importlib.import_module('unreal_candidate_alpha_probe')).run()
 if task=='plant_material_readonly':return importlib.reload(importlib.import_module('unreal_candidate_plant_material_readonly')).run()
 if task=='lighting_readonly':return importlib.reload(importlib.import_module('unreal_candidate_lighting_readonly')).run()
 if task=='settled_review':return importlib.reload(importlib.import_module('unreal_candidate_visual_review')).settled_review()
 if task=='visual_review_cancel':return importlib.reload(importlib.import_module('unreal_candidate_visual_review')).cancel()
 if task=='visual_review':return importlib.reload(importlib.import_module('unreal_candidate_visual_review')).run()
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
  assert body.get('world_mutations_authorized')is (task in('real_gaggia','genuine_indoor_syngonium','official_grohe_faucet','retire_kitchen_cylinder','table_controller_clearance','scanned_collectible','genuine_lived_props','dualsense_lightbars','ps5_lightbars','genuine_gaming_assembly','preserve_spawn_pose','original_ps5_assets','wall_console','teal_bath','bed_finish','photo_plants','practical_light_comparison','practical_light_refinement','kitchen_grain','owned_alpha_probe','chosen_bath4000','bed_lamp_source','aligned_bed_lamp','save_bed_lamp','owner_first_person_review','owner_component_pose_audit','reference_controller_assets','grip_component_pose_audit','living_tv_zone','retire_obsolete_living_table','tv_preview_exposure','living_wall_r4','tv_console_shift','idle_component_pose_audit','idle_first_person_review','muuto_rest_sofa','muuto_around_table','real_dualsense_assets','real_dualsense_view')),'Explicit candidate-only mutation phase required'
  review=sys.modules.get('unreal_candidate_visual_review')
  if review is not None and getattr(review,'_handle',None)is not None and task!='visual_review_cancel':return
  seen.add(request.name);result={'schema':'sub01.private-next-home-task-result.v1','task':task,'editor_pid':os.getpid(),'started_epoch':time.time(),'original_game_preserved':False,'promoted_to_live':False}
  try:
   result['result']=dispatch(task,probe);assert active_candidate_guard(CANDIDATE);result['ok']=True;result['original_game_preserved']=True
  except Exception as exc:
   result.update(ok=False,error=type(exc).__name__,message=str(exc),traceback=traceback.format_exc())
  result['finished_epoch']=time.time();(CANDIDATE/'private-audit'/(request.stem+'-result.json')).write_text(json.dumps(result,indent=2)+'\n')
