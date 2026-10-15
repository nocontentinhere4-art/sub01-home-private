"""Probe only newly owned unused botanical MI copies; never alter world assets."""
import json,time
from uuid import uuid4

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 from unreal_import_candidate_photo_plants import actual_material_property
 assert active_candidate_guard(u.Paths.project_dir());eas=u.get_editor_subsystem(u.EditorActorSubsystem);before=snapshot(u,list(eas.get_all_level_actors()))
 source='/Game/Sub01Home/PhotoPlants/V_70abe763ae23/A_26bc1bb9737c4989b64740ec0f063040/Plant3/placed-photo-plant-3/Materials/PP3M00.PP3M00';original=u.EditorAssetLibrary.load_asset(source)
 if not isinstance(original,u.MaterialInstanceConstant):raise RuntimeError('Exact fresh failed botanical MI required')
 rows=[]
 def state(m):
  o=m.get_editor_property('base_property_overrides');r={}
  for k in ['override_opacity_mask_clip_value','opacity_mask_clip_value']:
   try:r[k]=str(o.get_editor_property(k))
   except Exception as e:r[k]='ERROR:'+str(e)
  try:r['calculated']=float(actual_material_property(m,'opacity_mask_clip_value','override_opacity_mask_clip_value'))
  except Exception as e:r['calculated']='ERROR:'+str(e)
  return r
 for order in ['flag_then_value','value_then_flag']:
  dest='/Game/Sub01Home/AlphaProbe/A_'+uuid4().hex+'/Probe';m=u.EditorAssetLibrary.duplicate_asset(source,dest);row={'order':order,'source_state':state(original),'before':state(m)};o=m.get_editor_property('base_property_overrides')
  for k,v in ([('override_opacity_mask_clip_value',True),('opacity_mask_clip_value',.5)]if order=='flag_then_value'else[('opacity_mask_clip_value',.5),('override_opacity_mask_clip_value',True)]):o.set_editor_property(k,v)
  row['struct_before_assignment']={k:str(o.get_editor_property(k))for k in ['override_opacity_mask_clip_value','opacity_mask_clip_value']};m.set_editor_property('base_property_overrides',o);row['after_assignment']=state(m);u.MaterialEditingLibrary.update_material_instance(m);row['after_update']=state(m);rows.append(row)
 assert snapshot(u,list(eas.get_all_level_actors()))==before
 result={'schema':'sub01.actual-candidate-owned-alpha-api-probe.v1','world_unchanged':True,'only_new_unused_owned_mi_copies':True,'rows':rows};p=CANDIDATE/'private-audit/owned-alpha-probe.json';p.write_text(json.dumps(result,indent=2)+'\n');return result
