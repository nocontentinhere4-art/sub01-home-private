"""Actual light/white-balance/exposure data, no relighting or camera changes."""
import json,os,time
from pathlib import Path
PROPS=('intensity','light_color','use_temperature','temperature','indirect_lighting_intensity','volumetric_scattering_intensity','affects_world','visible','hidden_in_game','source_type','real_time_capture','sky_distance_threshold')
POST=('auto_exposure_method','override_auto_exposure_method','auto_exposure_bias','override_auto_exposure_bias','auto_exposure_min_brightness','auto_exposure_max_brightness','auto_exposure_speed_up','auto_exposure_speed_down','white_temp','override_white_temp','white_tint','override_white_tint','color_saturation','color_gain','color_gamma')
def read(obj,fields):
 result={}
 for key in fields:
  try:
   v=obj.get_editor_property(key);result[key]=v if isinstance(v,(bool,int,float,str))else str(v)
  except Exception:pass
 return result
def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 assert active_candidate_guard(u.Paths.project_dir());eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);lights=[];post=[]
 for a in actors:
  for c in a.get_components_by_class(u.LightComponentBase):lights.append({'actor':a.get_path_name(),'label':a.get_actor_label(),'actor_hidden':bool(a.get_editor_property('hidden')),'component':c.get_path_name(),'class':c.get_class().get_name(),'settings':read(c,PROPS)})
  if isinstance(a,u.PostProcessVolume):post.append({'actor':a.get_path_name(),'label':a.get_actor_label(),'enabled':read(a,('enabled','unbound','blend_weight','priority')),'settings':read(a.get_editor_property('settings'),POST)})
 settings={}
 try:
  viewport=u.get_default_object(u.LevelEditorViewportSettings);settings=read(viewport,('per_instance_settings','instance_settings','editor_views','exposure_settings','default_perspective_fov'))
 except Exception as exc:settings={'unavailable':str(exc)}
 cvars={name:u.SystemLibrary.get_console_variable_int_value(name)for name in('r.DynamicGlobalIlluminationMethod','r.Lumen.DiffuseIndirect.Allow','r.EyeAdaptationQuality','r.DefaultFeature.AutoExposure','r.DefaultFeature.AutoExposure.ExtendDefaultLuminanceRange')}
 assert snapshot(u,list(eas.get_all_level_actors()))==before
 result={'schema':'sub01.actual-candidate-light-exposure-readonly.v1','editor_pid':os.getpid(),'epoch':time.time(),'lights':lights,'post_process_volumes':post,'stored_viewport_settings_not_proven_current':settings,'actual_rendering_cvars':cvars,'world_snapshot_unchanged':True,'light_settings_changed':False,'exposure_changed':False};path=CANDIDATE/'private-audit/candidate-lighting-readonly.json';path.write_text(json.dumps(result,indent=2)+'\n');return {'read_only':True,'report':str(path),'lights':len(lights),'post_process_volumes':len(post),'world_snapshot_unchanged':True}
