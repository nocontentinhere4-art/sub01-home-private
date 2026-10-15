"""Read actual owned botanical alpha and UV bindings without world changes."""
import json,time
from pathlib import Path

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 from unreal_sheer_material_readonly import root_graph,_property
 from unreal_import_candidate_photo_plants import actual_material_property
 assert active_candidate_guard(u.Paths.project_dir());eas=u.get_editor_subsystem(u.EditorActorSubsystem);before=snapshot(u,list(eas.get_all_level_actors()));rows=[];mel=u.MaterialEditingLibrary
 for path in u.EditorAssetLibrary.list_assets('/Game/Sub01Home/PhotoPlants',recursive=True,include_folder=False):
  m=u.EditorAssetLibrary.load_asset(path)
  if not isinstance(m,u.MaterialInstanceConstant):continue
  rows.append({'material':m.get_path_name(),'parent':_property(m,'parent'),'root_graph':root_graph(u,m),'actual_properties':{k:str(actual_material_property(m,k,f))for k,f in [('blend_mode','override_blend_mode'),('two_sided','override_two_sided'),('opacity_mask_clip_value','override_opacity_mask_clip_value')]},'base_overrides':_property(m,'base_property_overrides'),'scalars':{str(n):float(mel.get_material_instance_scalar_parameter_value(m,n))for n in mel.get_scalar_parameter_names(m)},'vectors':{str(n):[float(getattr(mel.get_material_instance_vector_parameter_value(m,n),c))for c in('r','g','b','a')]for n in mel.get_vector_parameter_names(m)},'textures':{str(n):_property(mel.get_material_instance_texture_parameter_value(m,n),'path_name')for n in mel.get_texture_parameter_names(m)}})
 assert snapshot(u,list(eas.get_all_level_actors()))==before
 report={'schema':'sub01.actual-candidate-botanical-material-readonly.v1','epoch':time.time(),'world_snapshot_unchanged':True,'materials':rows};p=CANDIDATE/'private-audit/plant-material-readonly.json';p.write_text(json.dumps(report,indent=2)+'\n');return {'report':str(p),'materials':len(rows),'world_snapshot_unchanged':True}
