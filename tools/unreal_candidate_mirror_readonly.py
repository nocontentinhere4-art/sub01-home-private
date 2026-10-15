"""Inspect actual saved mirror shading/reflection settings, no new scene capture."""
import json,time

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 from unreal_extend_private_entry import world_bounds
 from unreal_sheer_material_readonly import _property,root_graph
 assert active_candidate_guard(u.Paths.project_dir());eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);rows=[];captures=[];mel=u.MaterialEditingLibrary;receipt=json.loads((CANDIDATE/'private-audit/reference-teal-bathroom-native.json').read_text());bath_dressing={x['actor']for x in receipt['dressing_parts']}
 for a in actors:
  cls=a.get_class().get_name()
  if any(x in cls for x in('Reflection','SceneCapture')):captures.append({'actor':a.get_path_name(),'label':a.get_actor_label(),'class':cls,'hidden':bool(a.get_editor_property('hidden')),'transform':str(a.get_actor_transform())})
  for c in a.get_components_by_class(u.StaticMeshComponent):
   mesh=c.get_editor_property('static_mesh');materials=list(c.get_materials());identity=' '.join([a.get_actor_label(),mesh.get_name()if mesh else'',*[m.get_name()for m in materials if m]])
   if'mirror'not in identity.lower()and a.get_path_name()not in bath_dressing:continue
   entry={'actor':a.get_path_name(),'label':a.get_actor_label(),'hidden':bool(a.get_editor_property('hidden')),'mesh':mesh.get_path_name()if mesh else None,'bounds_cm':world_bounds(u,c),'transform':str(c.get_world_transform()),'materials':[]}
   for m in materials:
    if not isinstance(m,u.MaterialInstanceConstant):entry['materials'].append({'material':m.get_path_name()if m else None,'class':m.get_class().get_name()if m else None});continue
    entry['materials'].append({'material':m.get_path_name(),'parent':_property(m,'parent'),'root_graph':root_graph(u,m),'vectors':{str(n):[float(getattr(mel.get_material_instance_vector_parameter_value(m,n),k))for k in('r','g','b','a')]for n in mel.get_vector_parameter_names(m)},'scalars':{str(n):float(mel.get_material_instance_scalar_parameter_value(m,n))for n in mel.get_scalar_parameter_names(m)}})
   rows.append(entry)
 names=['r.ReflectionMethod','r.Lumen.Reflections.Allow','r.Lumen.Reflections.ScreenTraces','r.Lumen.HardwareRayTracing','r.RayTracing','r.Lumen.Reflections.HardwareRayTracing','r.Lumen.Reflections.MaxRoughnessToTrace','r.Lumen.TranslucencyReflections.FrontLayer.Allow','r.Lumen.Reflections.Quality'];cvars={n:u.SystemLibrary.get_console_variable_float_value(n)for n in names}
 assert snapshot(u,list(eas.get_all_level_actors()))==before
 result={'schema':'sub01.actual-candidate-mirror-reflection-readonly.v1','epoch':time.time(),'world_unchanged':True,'materials':rows,'existing_capture_actors':captures,'actual_cvars':cvars,'new_capture_added':False,'live_runtime_reflection_verified':False};p=CANDIDATE/'private-audit/mirror-reflection-readonly.json';p.write_text(json.dumps(result,indent=2)+'\n');return {'report':str(p),'mirror_components':len(rows),'capture_actors':len(captures),'world_unchanged':True}
