"""Save the visually chosen real bathroom fixture4000K in the candidate only."""
import hashlib,json,shutil,time
from pathlib import Path

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 assert active_candidate_guard(u.Paths.project_dir());eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);lights=[c for a in actors for c in a.get_components_by_class(u.LightComponent)]
 def states():return {c.get_path_name():{k:str(c.get_editor_property(k))for k in('intensity','temperature','use_temperature','light_color')}for c in lights}
 original=states();found=[a for a in actors if a.get_actor_label()=='SUB01_AuthoredLight_BathroomCeiling'];assert len(found)==1;cs=found[0].get_components_by_class(u.LightComponent);assert len(cs)==1;c=cs[0]
 if c.get_class().get_name()!='PointLightComponent'or float(c.get_editor_property('temperature'))!=3000 or float(c.get_editor_property('intensity'))!=5.5 or not c.get_editor_property('use_temperature'):raise RuntimeError('Exact approved existing real bath light baseline required')
 expected={k:dict(v)for k,v in original.items()};expected[c.get_path_name()]['temperature']='4000.0';map_path=CANDIDATE/'Content/Sub01Home/ActualHome.umap';backup=CANDIDATE/'Saved/PrivateMapBackups'/('bath4000-'+str(time.time_ns()));backup.mkdir(parents=True);shutil.copy2(map_path,backup/'ActualHome.umap');save_attempted=False
 try:
  c.set_editor_property('temperature',4000.)
  if states()!=expected or snapshot(u,list(eas.get_all_level_actors()))!=before:raise RuntimeError('Only the one actual existing bathroom fixture colour temperature may change')
  assert active_candidate_guard(u.Paths.project_dir());save_attempted=True
  if not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Chosen bathroom light save refused')
  result={'schema':'sub01.actual-candidate-chosen-bath-light.v1','saved':True,'actual_existing_component':c.get_path_name(),'prior_K':3000,'chosen_K':4000,'intensity_candela_unchanged':5.5,'existing_fixture_only':True,'other_lights_original_exact':True,'all_actor_component_geometry_transforms_materials_collisions_exact':True,'map_sha256':hashlib.sha256(map_path.read_bytes()).hexdigest(),'backup':str(backup),'live_game_or_runtime_gates_changed':False,'runtime_switch_retest_required':True};(CANDIDATE/'private-audit/chosen-bath4000-native.json').write_text(json.dumps(result,indent=2)+'\n');return result
 except Exception:
  c.set_editor_property('temperature',3000.)
  if states()!=original or snapshot(u,list(eas.get_all_level_actors()))!=before:raise RuntimeError('Chosen light rollback must restore all actual light and actor state')
  if save_attempted and not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Chosen light rollback save refused')
  raise
