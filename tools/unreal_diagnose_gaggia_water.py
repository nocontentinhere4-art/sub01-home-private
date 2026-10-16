"""Read-only actual quarantined Gaggia Water material inheritance and numeric opacity."""
import json
from pathlib import Path

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard
 from unreal_import_reference_entry import snapshot
 project=Path(u.Paths.project_dir()).resolve();assert active_candidate_guard(project)
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors)
 refusal=json.loads((project/'private-audit/gaggia-gran-refusal.json').read_text());assert refusal['complete_world_rollback_verified']is True
 dest=refusal['quarantined_owned_destination'];assert dest.startswith('/Game/Sub01Home/GenuineGaggiaGran/Attempt_')or dest.startswith('/Game/Sub01Home/GenuineGaggiaGran/V_')
 rows=[];mel=u.MaterialEditingLibrary
 for path in u.EditorAssetLibrary.list_assets(dest,recursive=True,include_folder=False):
  m=u.EditorAssetLibrary.load_asset(path)
  if not isinstance(m,u.MaterialInstanceConstant)or 'water'not in m.get_name().lower():continue
  chain=[];p=m
  for depth in range(10):
   row={'path':p.get_path_name(),'class':p.get_class().get_name()}
   if isinstance(p,u.MaterialInstanceConstant):
    ov=p.get_editor_property('base_property_overrides');row['base_property_overrides']={k:str(ov.get_editor_property(k))for k in('override_blend_mode','blend_mode','override_two_sided','two_sided')};chain.append(row);p=p.get_editor_property('parent');assert p
   else:
    row['root_blend_mode']=str(p.get_editor_property('blend_mode'));row['root_two_sided']=str(p.get_editor_property('two_sided'));row['root_shading_model']=str(p.get_editor_property('shading_model'));chain.append(row);break
  vectors={}
  for name in mel.get_vector_parameter_names(m):
   c=mel.get_material_instance_vector_parameter_value(m,name);vectors[str(name)]=[c.r,c.g,c.b,c.a]
  scalars={str(n):mel.get_material_instance_scalar_parameter_value(m,n)for n in mel.get_scalar_parameter_names(m)}
  rows.append({'material':m.get_path_name(),'chain':chain,'vector_parameters':vectors,'scalar_parameters':scalars})
 assert rows,'No actual quarantined Water material found';assert snapshot(u,eas.get_all_level_actors())==before
 result={'schema':'sub01.gaggia-quarantine-water-readonly.v1','owned_destination':dest,'rows':rows,'world_unchanged':True,'materials_mutated':False};(project/'private-audit/gaggia-water-material-diagnostic.json').write_text(json.dumps(result,indent=2));return result
