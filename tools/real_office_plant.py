"""Rigid placement of the exact genuine office plant; preserve all other plants."""
import hashlib,json
from real_linea_lamp_mount import geometry
from pathlib import Path
NODES=(221,222,223,224);ROOT_NODE=225;DELTA=(-.4,0.,-.01)
MESHES={221:165,222:163,223:164,224:162}

def source_plan(home):
 if hashlib.sha256(Path(home).read_bytes()).hexdigest()!='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b':raise ValueError('Actual source identity differs')
 doc,rows=geometry(home);children=doc['nodes'][ROOT_NODE].get('children',[])
 if set(children)!=set(NODES):raise ValueError('Exact office225 parent/221..224 child identities differ; never move kitchen220')
 members=[r for r in rows if r['node']in NODES]
 if len(members)!=4 or any(not doc['nodes'][r['node']].get('name','').endswith('.004')for r in members):raise ValueError('Exact four genuine office plant mesh identities differ')
 legacy=[r for r in rows if r['node']==259]
 if len(legacy)!=1 or doc['nodes'][259].get('name')!='Mesh_181' or legacy[0]['material']!='Material_14':raise ValueError('Exact obsolete generated lamp base259 identity differs')
 lp=[(p[0],p[2],p[1])for p in legacy[0]['points']];lb=[[min(p[a]for p in lp)for a in range(3)],[max(p[a]for p in lp)for a in range(3)]]
 expected=[[2.590996563434601,-3.2401549220085144,.844999972730875],[2.720996558666229,-3.1101549267768858,.8629999719560146]]
 if max(abs(x-y)for a,b in zip(lb,expected)for x,y in zip(a,b))>1e-6:raise ValueError('Actual generated radius65mm/height18mm obsolete foot bounds differ')
 legacy_plan={'source_node':259,'source_name':'Mesh_181','source_material':'Material_14','source_triangle_count':len(legacy[0]['triangles']),'old_bounds_ue_m':lb,'native_mesh':'/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Mesh_181.Mesh_181','native_material':'/Game/Sub01Home/ImportedScene/full-home/Materials/Material_14.Material_14','source_evidence':'home.js625 old red arm +644 generated cylinder radius.065,height.018; real-lamps saved hide receipt omitted259','action':'hide_only_exact259_and_NoCollision_in_same_office_transaction'}
 plans=[];contacts=[];boundary=[];allpoints=[]
 for row in members:
  old=[(p[0],p[2],p[1])for p in row['points']];new=[tuple(p[a]+DELTA[a]for a in range(3))for p in old];allpoints+=new
  bounds=lambda ps:[[min(p[a]for p in ps)for a in range(3)],[max(p[a]for p in ps)for a in range(3)]]
  for i,t in enumerate(row['triangles']):
   if min(new[v][2]for v in t)>=.845-1e-8 and any(abs(new[v][2]-.845)<=1e-7 for v in t):boundary.append({'node':row['node'],'triangle':i})
   if all(abs(new[v][2]-.845)<=1e-7 for v in t):contacts.append({'node':row['node'],'triangle':i,'points_ue_m':[new[v]for v in t]})
  plans.append({'node':row['node'],'old_bounds_ue_m':bounds(old),'new_bounds_ue_m':bounds(new),'source_triangle_count':len(row['triangles'])})
 if abs(min(p[2]for p in allpoints)-.845)>1e-7 or not contacts:raise ValueError('Actual authored plant base lacks exact tabletop contact faces')
 return {'root_source_node':225,'mesh_source_nodes':list(NODES),'rigid_delta_ue_cm':[v*100 for v in DELTA],'members':plans,'exact_base_contact_faces':contacts,'exact_nonpenetrating_base_boundary_faces':boundary,'geometry_uv_pbr_unchanged':True,'retire_only_obsolete_generated_lamp_base':legacy_plan,'watering_anchor_status':'No watering implementation/coordinate anchor found in local native source; actual interaction acceptance remains unverified'},members



def native_geometry_api_audit(u,mesh):
 """Read-only API/settings receipt; never rebuilds or changes shared assets."""
 report={'unreal_module_name':getattr(u,'__name__',None),'apis':{name:hasattr(mesh,name)for name in ('get_mesh_description','get_num_source_models','get_num_lods')},'nanite_settings':{},'errors':{}}
 try:
  settings=mesh.get_editor_property('nanite_settings')
  for prop in ('enabled','fallback_percent_triangles','fallback_relative_error','keep_percent_triangles','trim_relative_error','fallback_target'):
   try:
    value=settings.get_editor_property(prop)
    report['nanite_settings'][prop]=value if isinstance(value,(bool,int,float,str))else str(value)
   except Exception as error:report['errors']['nanite_settings.'+prop]=str(error)
 except Exception as error:report['errors']['nanite_settings']=str(error)
 if hasattr(u,'StaticMeshEditorSubsystem'):
  try:
   sub=u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
   report['subsystem_apis']={name:hasattr(sub,name)for name in ('get_nanite_settings','set_nanite_settings','get_lod_count','get_lod_vertex_count')}
  except Exception as error:report['errors']['StaticMeshEditorSubsystem']=str(error)
 if hasattr(mesh,'get_mesh_description'):
  try:
   description=mesh.get_mesh_description(0)
   report['mesh_description_present']=description is not None
   for method in ('get_triangle_count','get_vertex_count','get_polygon_count'):
    if description is not None and hasattr(description,method):report['mesh_description_'+method]=getattr(description,method)()
  except Exception as error:report['errors']['mesh_description']=str(error)
 return report


def native_preflight(u,actors,plan,surface,close,allow_owned_nanite_rebuild=False):
 base=plan['retire_only_obsolete_generated_lamp_base'];found=[a for a in actors if a.get_name()=='full-home_node_259']
 if len(found)!=1:raise RuntimeError('Exact obsolete lamp base259 native actor unavailable')
 oldbase=found[0];bc=oldbase.get_components_by_class(u.StaticMeshComponent)
 if len(bc)!=1 or bc[0].get_editor_property('static_mesh').get_path_name()!=base['native_mesh']or bc[0].get_num_materials()!=1 or bc[0].get_material(0).get_path_name()!=base['native_material']:raise RuntimeError('Exact obsolete259 native mesh/material identity differs')
 bp,bt=surface(u,bc[0]);bb=[[min(p[a]for p in bp)for a in range(3)],[max(p[a]for p in bp)for a in range(3)]]
 if bt!=base['source_triangle_count']or not all(close(a,[v*100 for v in b])for a,b in zip(bb,base['old_bounds_ue_m'])):raise RuntimeError('Actual native259 source cylinder bounds/count differ')
 rows=[];deferred=[]
 for p in plan['members']:
  found=[a for a in actors if a.get_name()=='full-home_node_'+str(p['node'])]
  if len(found)!=1:raise RuntimeError('Exact genuine office plant actor missing')
  actor=found[0];comps=actor.get_components_by_class(u.StaticMeshComponent)
  expected=f'/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Mesh_{MESHES[p["node"]]}.Mesh_{MESHES[p["node"]]}'
  if len(comps)!=1 or comps[0].get_editor_property('static_mesh').get_path_name()!=expected:raise RuntimeError('Exact actual saved office plant mesh identity differs')
  pts,count=surface(u,comps[0]);box=[[min(v[a]for v in pts)for a in range(3)],[max(v[a]for v in pts)for a in range(3)]]
  if count!=p['source_triangle_count']or not all(close(a,[v*100 for v in b])for a,b in zip(box,p['old_bounds_ue_m'])):
   wanted=[[v*100 for v in b]for b in p['old_bounds_ue_m']]
   mesh=comps[0].get_editor_property('static_mesh');parent=actor.get_attach_parent_actor()
   details={'source_node':p['node'],'actor':actor.get_name(),'expected_mesh':expected,'actual_mesh':mesh.get_path_name(),'expected_triangle_count':p['source_triangle_count'],'actual_triangle_count':count,'expected_world_bounds_ue_cm':wanted,'actual_world_bounds_ue_cm':box,'actual_minus_expected_bounds_cm':[[x-y for x,y in zip(a,b)]for a,b in zip(box,wanted)],'attach_parent_actor':parent.get_name()if parent else None,'actor_transform':str(actor.get_actor_transform())if hasattr(actor,'get_actor_transform')else None,'component_world_transform':str(comps[0].get_world_transform())if hasattr(comps[0],'get_world_transform')else None,'native_lod0_sections':mesh.get_num_sections(0)if hasattr(mesh,'get_num_sections')else None,'native_lod_count':mesh.get_num_lods()if hasattr(mesh,'get_num_lods')else None}
   details['geometry_api_audit']=native_geometry_api_audit(u,mesh)
   if hasattr(u,'Paths'):
    audit=Path(u.Paths.project_dir())/'private-audit'/'office-plant-native-refusal.json'
    audit.parent.mkdir(parents=True,exist_ok=True)
    audit.write_text(json.dumps(details,indent=2,sort_keys=True)+'\n')
   settings=details['geometry_api_audit'].get('nanite_settings',{})
   apis=details['geometry_api_audit'].get('subsystem_apis',{})
   if allow_owned_nanite_rebuild and settings.get('enabled')is True and settings.get('keep_percent_triangles')==1.0 and settings.get('trim_relative_error')==0.0 and apis.get('get_nanite_settings')and apis.get('set_nanite_settings'):
    deferred.append(details)  # NOT a geometry pass: exact proof is required on owned full-source clones before activation.
   else:raise RuntimeError('Actual genuine plant geometry/world bounds differ: '+json.dumps(details,sort_keys=True))
  rows.append((actor,comps[0],p))
 root=[a for a in actors if a.get_name()=='full-home_node_225']
 if len(root)!=1 or root[0].get_components_by_class(u.StaticMeshComponent):raise RuntimeError('Exact empty office parent225 identity differs')
 parents=[a.get_attach_parent_actor()for a,c,p in rows]
 if all(a==root[0]for a in parents):move=[root[0]]
 elif all(a!=root[0]for a in parents):
  if any(a in [r[0]for r in rows]for a in parents):raise RuntimeError('Ambiguous office plant child hierarchy; no double translation')
  move=[root[0]]+[r[0]for r in rows]
 else:raise RuntimeError('Mixed office plant225 attachment; no guessed double translation')
 return {'requires_owned_geometry_rebuild':deferred,'native_source_geometry_verified':not deferred,'rows':rows,'move':move,'root':root[0],'plan':plan,'oldbase':oldbase,'oldbase_actual_hidden_before':bool(oldbase.get_editor_property('hidden')),'oldbase_actual_collision_before':str(bc[0].get_collision_enabled())}


def stage_exact_owned_geometry(u,ctx,eas):
 """Restore full retained source geometry on private copies, leaving originals intact.

 Nanite AUTO fallback is not source geometry. The original asset's settings,
 materials and components are never changed here. Temporary no-collision actors
 verify full source triangles before returning proposed owned replacements.
 """
 if not ctx['requires_owned_geometry_rebuild']:return {'destination':None,'replacements':{},'proof':[]}
 from home_asset_audit import read_gltf
 from unreal_import_real_kitchen import same_triangles
 from unreal_monitor_support_fix import triangles,native_triangles
 source=Path(u.Paths.project_dir())/'SourceAssets/full-home.glb'
 if hashlib.sha256(source.read_bytes()).hexdigest()!='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b':raise RuntimeError('Exact retained plant source955 required for rebuild')
 doc,binary=read_gltf(source)
 dest='/Game/Sub01Home/RealOfficePlant/V_9556495fa816_FullSource'
 if u.EditorAssetLibrary.does_directory_exist(dest):raise RuntimeError('Owned full-source plant version already exists; inspect prior transaction')
 sub=u.get_editor_subsystem(u.StaticMeshEditorSubsystem);temporary=[];replacements={};proof=[]
 original_settings={c.get_editor_property('static_mesh').get_path_name():native_geometry_api_audit(u,c.get_editor_property('static_mesh'))['nanite_settings']for a,c,p in ctx['rows']}
 try:
  for actor,c,plan in ctx['rows']:
   original=c.get_editor_property('static_mesh');name=f"{dest}/SourceNode{plan['node']}"
   clone=u.EditorAssetLibrary.duplicate_asset(original.get_path_name(),name)
   if not clone or clone.get_path_name().split('.',1)[0]!=name:raise RuntimeError('Exact owned plant mesh duplication failed')
   settings=sub.get_nanite_settings(clone)
   settings.set_editor_property('enabled',False)
   settings.set_editor_property('fallback_percent_triangles',1.0)
   settings.set_editor_property('fallback_relative_error',0.0)
   sub.set_nanite_settings(clone,settings,True)
   # Asset save completes pending mesh compilation before CPU triangle extraction.
   if not u.EditorAssetLibrary.save_loaded_asset(clone,only_if_is_dirty=False):raise RuntimeError('Owned full-source plant mesh rebuild/save failed')
   if sub.get_nanite_settings(clone).get_editor_property('enabled'):raise RuntimeError('Owned full-source plant clone still uses Nanite fallback')
   temp=eas.spawn_actor_from_class(u.StaticMeshActor,u.Vector(0,0,0));temporary.append(temp)
   temp.set_actor_label('SUB01_OfficePlant_SourceProof_'+str(plan['node']));temp.set_actor_hidden_in_game(True)
   tc=temp.get_component_by_class(u.StaticMeshComponent);tc.set_static_mesh(clone);tc.set_world_transform(c.get_world_transform(),False,False);tc.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
   for slot,material in enumerate(c.get_materials()):tc.set_material(slot,material)
   wanted=triangles(doc,binary,plan['node']);actual=native_triangles(u,tc)
   if len(wanted)!=plan['source_triangle_count']or not same_triangles(wanted,actual):raise RuntimeError('Owned rebuilt full plant triangle geometry differs exact source '+str(plan['node']))
   if [m.get_path_name()if m else None for m in tc.get_materials()]!=[m.get_path_name()if m else None for m in c.get_materials()]:raise RuntimeError('Owned rebuilt plant altered material bindings')
   replacements[c.get_path_name()]=clone
   proof.append({'node':plan['node'],'original_mesh':original.get_path_name(),'owned_full_mesh':clone.get_path_name(),'source_triangles':len(wanted),'native_full_triangles':len(actual),'full_world_triangle_tolerance_cm':.02,'nanite_enabled':False})
  after={c.get_editor_property('static_mesh').get_path_name():native_geometry_api_audit(u,c.get_editor_property('static_mesh'))['nanite_settings']for a,c,p in ctx['rows']}
  if after!=original_settings:raise RuntimeError('Shared original plant Nanite settings changed')
  return {'destination':dest,'replacements':replacements,'proof':proof}
 except Exception:
  for temp in temporary:eas.destroy_actor(temp)
  temporary=[]
  if u.EditorAssetLibrary.does_directory_exist(dest):u.EditorAssetLibrary.delete_directory(dest)
  raise
 finally:
  for temp in temporary:eas.destroy_actor(temp)
