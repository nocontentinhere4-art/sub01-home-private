"""Inspect actual bedside lamp/bulb geometry and existing point emitter, read only."""
import json,time

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 from unreal_extend_private_entry import world_bounds
 from unreal_import_real_wc import expected_triangles
 from home_asset_audit import read_gltf
 assert active_candidate_guard(u.Paths.project_dir());eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);doc,blob=read_gltf(CANDIDATE/'SourceAssets/full-home.glb');rows=[];sub=u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
 for a in actors:
  label=a.get_actor_label();node=int(a.get_name().split('_')[-1])if a.get_name()in {'full-home_node_'+str(n)for n in range(195,200)}else None
  if node is None and not('bedlamp'in label.lower()or'bedside'in label.lower()):continue
  row={'actor':a.get_path_name(),'label':label,'class':a.get_class().get_name(),'hidden':bool(a.get_editor_property('hidden')),'editor_hidden':a.is_temporarily_hidden_in_editor(),'world_transform':str(a.get_actor_transform()),'components':[]}
  for c in a.get_components_by_class(u.StaticMeshComponent):
   mesh=c.get_editor_property('static_mesh');entry={'path':c.get_path_name(),'mesh':mesh.get_path_name()if mesh else None,'bounds_cm':world_bounds(u,c),'cast_shadow':bool(c.get_editor_property('cast_shadow')),'visible':bool(c.get_editor_property('visible')),'materials':[m.get_path_name()if m else None for m in c.get_materials()]}
   if label=='SUB01_RealLamp_BedLamp':
    entry['actual_nanite_enabled']=bool(sub.get_nanite_settings(mesh).get_editor_property('enabled'));entry['actual_native_sections']=[]
    for si in range(mesh.get_num_sections(0)):
     vertices,indices,*_=u.ProceduralMeshLibrary.get_section_from_static_mesh(mesh,0,si);points=[c.get_world_transform().transform_location(v)for v in vertices];coordinates=[[float(getattr(p,k))for k in ('x','y','z')]for p in points];entry['actual_native_sections'].append({'section':si,'material':c.get_material(si).get_path_name(),'vertices':len(vertices),'triangles':len(indices)//3,'bounds_cm':{'min':[min(p[i]for p in coordinates)for i in range(3)],'max':[max(p[i]for p in coordinates)for i in range(3)]},'actual_world_triangles_cm':[[coordinates[j]for j in indices[k:k+3]]for k in range(0,len(indices),3)]})
   if node is not None:entry.update(original_source_node=node,source_name=doc['nodes'][node]['name'],immutable_full_source_triangles_cm=expected_triangles(doc,blob,node),source_geometry_not_actual_binding_audited=True)
   row['components'].append(entry)
  for c in a.get_components_by_class(u.LightComponent):
   entry={'path':c.get_path_name(),'class':c.get_class().get_name(),'world_position_cm':[float(getattr(c.get_world_location(),k))for k in ('x','y','z')],'settings':{}}
   for k in ['intensity','intensity_units','temperature','use_temperature','attenuation_radius','source_radius','soft_source_radius','source_length','cast_shadows','use_inverse_squared_falloff']:
    try:entry['settings'][k]=str(c.get_editor_property(k))
    except Exception:pass
   row.setdefault('lights',[]).append(entry)
  rows.append(row)
 assert snapshot(u,list(eas.get_all_level_actors()))==before
 report={'schema':'sub01.actual-candidate-bedside-lamp-geometry-readonly.v1','epoch':time.time(),'world_unchanged':True,'rows':rows};p=CANDIDATE/'private-audit/bedside-lamp-geometry-readonly.json';p.write_text(json.dumps(report,indent=2)+'\n');return {'report':str(p),'rows':len(rows),'world_unchanged':True}
