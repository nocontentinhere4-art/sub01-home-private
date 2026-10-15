"""Candidate-only reversible six-part bed finish + material-only existing cloth.

Original240/260/261 visuals alone retire; their collisions remain unchanged.
Actual mattress262,slats265,lamp195–199 and every other actor stay exact.
"""
import copy,hashlib,json,shutil,struct,time
from pathlib import Path
from uuid import uuid4
ROOT=Path('/workspace/sub01-home-private/reference-bed-finish-r2/output')
HOME_SHA='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
BED_SHA='fbdee3c59a43a4693f5aab0e22bf173cff42c5fe678360932153c6f63b217859'
CLOTH_SHA='d5936142290790c5fb4fad059537c862547439bd9763d95fcb56a3ef3088e08c'
OLD_CLOTH_SHA='e1c4a48e4d6c391a428a20fa56a5575c50963e08a0a914e2df5c50b6d6fbc2f7'
BED_NAMES={'BFLeftPost','BFRightPost','BFLowerPanel','BFUpperPanel','BFNightstand','BFFrame'}
CLOTH_NAMES={'Duvet':'SUB01ReferenceBedding_Duvet','Foot throw':'SUB01ReferenceBedding_FootThrow','Pillow 1':'SUB01ReferenceBedding_Pillow1','Pillow 2':'SUB01ReferenceBedding_Pillow2'}
ORIGINAL_BINDINGS={240:'/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Mesh_169.Mesh_169',260:'/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/CC0_queen_0.CC0_queen_0',261:'/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/CC0_queen_1.CC0_queen_1'}

def validate_contract(report,proof):
 if(report.get('schema')!='sub01.reference-bed-finish-source.v1'or report.get('new_source_sha256')!=BED_SHA or report.get('cloth_material_variant_sha256')!=CLOTH_SHA or report.get('source_home_sha256')!=HOME_SHA or report.get('retire_only_source_nodes')!=[240,260,261]or report.get('new_parts')!=6 or report.get('cloth_source_original_unchanged_sha256')!=OLD_CLOTH_SHA or report.get('all72200cloth_triangles_and_original_binary_unchanged')is not True or report.get('mattress262_unchanged')is not True or report.get('slats265_unchanged')is not True or report.get('functional_bedside_lamp195_199_unchanged')is not True):raise RuntimeError('Exact six-part bed / unchanged cloth and protected mattress/lamp source contract required')
 if(proof.get('schema')!='sub01.reference-bed-finish-physical-proof.v1'or proof.get('source_sha256')!=BED_SHA or proof.get('new_cloth_material_variant_sha256')!=CLOTH_SHA or proof.get('all_cloth_geometry_UV_and_binary_exact')is not True or proof.get('new_head_source_bvh',{}).get('unresolved_intersections')!=[]or proof.get('new_head_source_bvh',{}).get('epsilon_m')!=0 or len(proof.get('new_headboard_inside_original_261',[]))!=4 or any(r.get('inside_old_headboard_AABB')is not True for r in proof.get('new_headboard_inside_original_261',[]))):raise RuntimeError('Complete exact physical source proof required')

def prepare(source,target,prefix):
 from home_asset_audit import read_gltf
 doc,blob=read_gltf(Path(source));out=copy.deepcopy(doc);mapping={}
 if any('mesh'not in n for n in doc['nodes']):raise RuntimeError('Standalone source parts required')
 for i,n in enumerate(out['nodes']):
  mapping[f'{prefix}{i:02}']=n['name'];n['name']=f'{prefix}{i:02}';out['meshes'][n['mesh']]['name']=n['name']
 text=json.dumps(out,separators=(',',':')).encode();text+=b' '*(-len(text)%4);binary=bytes(blob);binary+=b'\0'*(-len(binary)%4);target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
 if target.exists():raise RuntimeError('Fresh owned prepared source required')
 target.write_bytes(struct.pack('<III',0x46546c67,2,28+len(text)+len(binary))+struct.pack('<II',len(text),0x4e4f534a)+text+struct.pack('<II',len(binary),0x004e4942)+binary)
 check,payload=read_gltf(target);restored=copy.deepcopy(check)
 for i,n in enumerate(doc['nodes']):restored['nodes'][i]['name']=n['name']
 for i,m in enumerate(doc['meshes']):
  if'name'in m:restored['meshes'][i]['name']=m['name']
  else:restored['meshes'][i].pop('name',None)
 if restored!=doc or bytes(payload)!=bytes(blob):raise RuntimeError('Names-only source preparation changed binary/PBR/transforms')
 return check,payload,mapping

def audit_original_full_source(u,eas,c,expected,node,bindings,destination,dry_run=False):
 """Explicit caller binding table; clone-only full-source proof, no original edits."""
 from private_home_candidate_scope import active_candidate_guard
 from unreal_remove_frame_backings import native_triangles,same_triangles
 from unreal_import_reference_wall_console import positive_triangles
 from unreal_import_real_wc import owned_geometry
 if not active_candidate_guard(Path(u.Paths.project_dir()).resolve()):raise RuntimeError('Isolated candidate scope required')
 mesh=c.get_editor_property('static_mesh');owner=c.get_owner()
 if node not in bindings or owner.get_name()!=f'full-home_node_{node}'or not mesh or mesh.get_path_name()!=bindings[node]:raise RuntimeError('Exact allowlisted original actor/component/mesh binding required')
 expected,zero=positive_triangles(expected);actual=native_triangles(u,c)
 if same_triangles(expected,actual,tolerance=.0001):return {'source_node':node,'method':'complete actual original CPU source','positive_triangles':len(actual),'exact_zero_source_triangles':zero}
 sub=u.get_editor_subsystem(u.StaticMeshEditorSubsystem);settings=sub.get_nanite_settings(mesh);keys=('enabled','fallback_target','fallback_relative_error','fallback_percent_triangles','keep_percent_triangles','trim_relative_error');before={k:str(settings.get_editor_property(k))for k in keys}
 if not settings.get_editor_property('enabled'):raise RuntimeError('Original non-Nanite source geometry differs')
 if dry_run:return {'source_node':node,'requires_owned_full_source_clone_before_retirement':True,'retirement_geometry_proven':False,'actual_fallback_triangles':len(actual),'source_positive_triangles':len(expected)}
 clone=u.EditorAssetLibrary.duplicate_asset(mesh.get_path_name().split('.',1)[0],destination+'/OriginalAudit/'+uuid4().hex+'/'+mesh.get_name())
 if not clone:raise RuntimeError('Owned original source clone refused')
 actor=None
 try:
  owned_geometry(u,clone,destination)
  if u.Sub01HomeHandsInstance.finish_pending_static_compilation()!=0:raise RuntimeError('Owned full-source clone compilation incomplete')
  actor=eas.spawn_actor_from_class(u.StaticMeshActor,u.Vector(0,0,0));actor.set_actor_hidden_in_game(True);actor.set_is_temporarily_hidden_in_editor(True);cc=actor.get_component_by_class(u.StaticMeshComponent);cc.set_static_mesh(clone);cc.set_collision_enabled(u.CollisionEnabled.NO_COLLISION);cc.set_world_transform(c.get_world_transform(),False,True);full=native_triangles(u,cc)
  if not same_triangles(expected,full,tolerance=.0001):raise RuntimeError('Owned complete original-source clone geometry differs')
  return {'source_node':node,'method':'independent owned full-source clone','positive_triangles':len(full),'original_fallback_triangles':len(actual),'clone':clone.get_path_name(),'original_untouched':True,'exact_zero_source_triangles':zero}
 finally:
  if actor and not eas.destroy_actor(actor):raise RuntimeError('Temporary original-source audit actor cleanup failed')
  if {k:str(sub.get_nanite_settings(mesh).get_editor_property(k))for k in keys}!=before or c.get_editor_property('static_mesh')!=mesh:raise RuntimeError('Original source binding/settings changed during clone-only audit')

def run(dry_run=True):
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard
 from home_asset_audit import read_gltf
 from unreal_import_reference_entry import snapshot
 from unreal_import_real_wc import expected_triangles,owned_geometry
 from unreal_remove_frame_backings import native_triangles,same_triangles
 from unreal_import_reference_wall_console import positive_triangles
 from unreal_import_real_bathroom_pendant import verify_owned_material
 from unreal_import_real_linea140 import verify_materials
 from unreal_owned_import_cleanup import detach_added
 project=Path(u.Paths.project_dir()).resolve()
 if not active_candidate_guard(project):raise RuntimeError('Authenticated independent candidate project only')
 source_report=json.loads((ROOT/'bed-finish-source.json').read_text());source_proof=json.loads((ROOT/'bed-finish-physical-proof.json').read_text());validate_contract(source_report,source_proof)
 for path,sha in [(project/'SourceAssets/full-home.glb',HOME_SHA),(ROOT/'bed-finish.glb',BED_SHA),(ROOT/'bedding-finish.glb',CLOTH_SHA)]:
  if hashlib.sha256(path.read_bytes()).hexdigest()!=sha:raise RuntimeError('Exact full frozen source bytes required')
 old_cloth=Path('/workspace/sub01-home-private/reference-bedding-source-r1/output/bedding.glb')
 if hashlib.sha256(old_cloth.read_bytes()).hexdigest()!=OLD_CLOTH_SHA:raise RuntimeError('Actual installed cloth source changed')
 hd,hb=read_gltf(project/'SourceAssets/full-home.glb');cd,cb=read_gltf(old_cloth);vd,vb=read_gltf(ROOT/'bedding-finish.glb');restore=copy.deepcopy(vd);restore['materials']=cd['materials']
 for m0,m1 in zip(cd['meshes'],restore['meshes']):
  for p0,p1 in zip(m0['primitives'],m1['primitives']):p1['material']=p0['material']
 if restore!=cd or bytes(vb)!=bytes(cb):raise RuntimeError('Material variant changed installed cloth geometry/UV/image binary')
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);old=[];cloth=[];source_audits=[];dest='/Game/Sub01Home/ReferenceBedFinish/V_'+BED_SHA[:12]+'/A_'+uuid4().hex
 if any(a.get_actor_label().startswith('SUB01ReferenceBedFinish_')for a in actors):raise RuntimeError('Bed finish already present; inspect receipt')
 for node in (240,260,261):
  matches=[a for a in actors if a.get_name()==f'full-home_node_{node}']
  if len(matches)!=1:raise RuntimeError('Exact unique original bed actor required')
  a=matches[0];cs=a.get_components_by_class(u.StaticMeshComponent)
  if len(cs)!=1 or a.get_editor_property('hidden'):raise RuntimeError('Visible standalone original bed part required')
  source_audits.append(audit_original_full_source(u,eas,cs[0],expected_triangles(hd,hb,node),node,ORIGINAL_BINDINGS,dest,dry_run));old.append((a,cs[0],bool(a.get_editor_property('hidden')),a.is_temporarily_hidden_in_editor()))
 for ni,n in enumerate(cd['nodes']):
  label=CLOTH_NAMES[n['name']];matches=[a for a in actors if a.get_actor_label()==label]
  if len(matches)!=1:raise RuntimeError('Exact currently installed four textile actors required')
  a=matches[0];cs=a.get_components_by_class(u.StaticMeshComponent)
  if len(cs)!=1:raise RuntimeError('Exact one textile component required')
  c=cs[0];mesh=c.get_editor_property('static_mesh');expected,zero=positive_triangles(expected_triangles(cd,cb,ni))
  if not mesh or not mesh.get_path_name().startswith('/Game/Sub01Home/ReferenceBedding/V_e1c4a48e4d6c/')or not same_triangles(expected,native_triangles(u,c),tolerance=.0001):raise RuntimeError('Installed complete actual cloth geometry/source ownership differs')
  if c.get_num_materials()!=1:raise RuntimeError('Original textile material binding differs')
  cloth.append((a,c,n['name'],c.get_material(0),mesh))
 result={'schema':'sub01.reference-bed-finish-candidate-native.v1','dry_run':dry_run,'bed_source_sha256':BED_SHA,'cloth_material_source_sha256':CLOTH_SHA,'source_audits':source_audits,'only_retire_source_nodes':[240,260,261],'retire_visual_only_original_collision_retained':True,'mattress262_slats265_lamp195_199_preserved':True,'cloth_meshes_transforms_and_collisions_unchanged':True,'native_visual_accepted':False,'physical_contact_accepted':False,'live_promotion':False}
 if dry_run:return result
 backup=project/'Saved/PrivateMapBackups'/('bed-finish-'+str(time.time_ns()));backup.mkdir(parents=True);shutil.copy2(project/'Content/Sub01Home/ActualHome.umap',backup/'ActualHome.umap')
 for name in('__ExternalActors__','__ExternalObjects__'):
  folder=project/'Content'/name/'Sub01Home/ActualHome'
  if folder.exists():shutil.copytree(folder,backup/name)
 new_bed=[];temp_cloth=[];import_roots=[];new_cloth_materials={};pbr=[];geometry=[];save_attempted=False
 try:
  for role,path,prefix in [('bed',ROOT/'bed-finish.glb','BFN'),('cloth',ROOT/'bedding-finish.glb','BFC')]:
   prepared=project/'Saved/PrivateImportInputs'/('bed-finish-'+role+'-'+uuid4().hex+'.glb');doc,blob,mapping=prepare(path,prepared,prefix)
   role_before={a.get_path_name()for a in eas.get_all_level_actors()}
   manager=u.InterchangeManager.get_interchange_manager_scripted();params=u.ImportAssetParameters();params.set_editor_property('is_automated',True)
   if not manager.import_scene(dest+'/'+role,manager.create_source_data(str(prepared)),params):raise RuntimeError('Reviewed bed/cloth source import refused')
   manager.wait_until_all_tasks_done(False);added=[a for a in eas.get_all_level_actors()if a.get_path_name()not in before];by={}
   for a in added:
    if a.get_path_name()not in role_before and not a.get_components_by_class(u.StaticMeshComponent):
     kind=a.get_class().get_name();components=list(a.get_components_by_class(u.ActorComponent));parent=a.get_attach_parent_actor()
     if kind not in('Actor','InterchangeSceneActor'):raise RuntimeError('Unexpected newly imported non-mesh actor class: '+kind)
     if kind=='Actor'and(len(components)!=1 or components[0].get_class().get_name()!='SceneComponent'):raise RuntimeError('New generic source root must contain only one SceneComponent')
     if parent and parent.get_path_name()in role_before:raise RuntimeError('Fresh source root attached outside exact scoped source import')
     if any(child.get_path_name()in role_before for child in a.get_attached_actors()):raise RuntimeError('Fresh source root owns an existing actor')
     import_roots.append(a)
   for a in added:
    a.set_actor_hidden_in_game(True)
    for c in a.get_components_by_class(u.StaticMeshComponent):
     mesh=c.get_editor_property('static_mesh')
     if not mesh or not mesh.get_path_name().startswith(dest+'/'+role+'/'):continue
     for key in {a.get_actor_label(),mesh.get_name()}:
      if key in mapping:by.setdefault(key,{})[c.get_path_name()]=(a,c)
   for ni,n in enumerate(doc['nodes']):
    matches=list(by.get(n['name'],{}).values())
    if len(matches)!=1:raise RuntimeError('Every exact source role must bind one owned component')
    a,c=matches[0];owned_geometry(u,c.get_editor_property('static_mesh'),dest);expected,zero=positive_triangles(expected_triangles(doc,blob,ni));actual=native_triangles(u,c)
    if not same_triangles(expected,actual,tolerance=.0001):raise RuntimeError('Complete positive imported bed/cloth source triangles differ')
    material=doc['materials'][doc['meshes'][n['mesh']]['primitives'][0]['material']];pbr.append(verify_owned_material(u,c,material,dest,source_primitive_verified=True));c.set_collision_profile_name('NoCollision');c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
    original_name=mapping[n['name']];geometry.append({'role':role,'source_part':original_name,'positive_triangles':len(actual),'source_exact_zero_triangle_indices':zero})
    if role=='bed':a.set_actor_label('SUB01ReferenceBedFinish_'+original_name);new_bed.append((a,c))
    else:temp_cloth.append(a);new_cloth_materials[original_name]=(c.get_material(0),material)
  if len(new_bed)!=6 or len(temp_cloth)!=4 or snapshot(u,actors)!=before:raise RuntimeError('Complete source roles and unchanged originals required')
  expected_after=copy.deepcopy(before)
  for a,c,name,oldmat,mesh in cloth:
   mat,source=new_cloth_materials[name];c.set_material(0,mat)
   verify_materials(u,[c],{'materials':[source]},dest,material_bindings={source['name']:mat.get_path_name()})
   row=next(x for x in expected_after[a.get_path_name()]['components']if x['path']==c.get_path_name());row['materials']=[mat.get_path_name()]
   if c.get_editor_property('static_mesh')!=mesh:raise RuntimeError('Material-only textile update changed actual mesh')
  for a in temp_cloth:
   if not eas.destroy_actor(a):raise RuntimeError('Temporary material-source actor cleanup failed')
  for a,c,h,eh in old:a.set_actor_hidden_in_game(True);a.set_is_temporarily_hidden_in_editor(True);expected_after[a.get_path_name()]['hidden']=True;expected_after[a.get_path_name()]['editor_hidden']=True
  # Retain exact approved part world transforms, then remove only newly created
  # exact InterchangeSceneActor roots from the two scoped scene imports.
  root_paths={a.get_path_name()for a in import_roots};part_states=snapshot(u,[a for a,c in new_bed])
  for a,c in new_bed:
   parent=a.get_attach_parent_actor()
   if parent:
    if parent.get_path_name()not in root_paths:raise RuntimeError('Imported bed part attached outside new owned roots')
    a.detach_from_actor(u.DetachmentRule.KEEP_WORLD,u.DetachmentRule.KEEP_WORLD,u.DetachmentRule.KEEP_WORLD)
  if snapshot(u,[a for a,c in new_bed])!=part_states:raise RuntimeError('Root detachment changed exact retained bed part world state')
  for root in reversed(import_roots):
   if root.get_components_by_class(u.StaticMeshComponent)or root.get_class().get_name()not in('Actor','InterchangeSceneActor')or root.get_attached_actors():raise RuntimeError('Only exact newly imported empty scene roots may be destroyed')
   if not eas.destroy_actor(root):raise RuntimeError('Empty owned import root cleanup failed')
  for a,c in new_bed:a.set_actor_hidden_in_game(False)
  if snapshot(u,actors)!=expected_after:raise RuntimeError('Only three original visual flags and four cloth materials may change')
  live_new=[a for a in eas.get_all_level_actors()if a.get_path_name()not in before]
  if {a.get_path_name()for a in live_new}!={a.get_path_name()for a,c in new_bed}:raise RuntimeError('Unexpected import/audit actors remain')
  if not u.EditorAssetLibrary.save_directory(dest,only_if_is_dirty=False,recursive=True):raise RuntimeError('Owned bed/cloth material assets save refused')
  if not active_candidate_guard(project):raise RuntimeError('Candidate scope expired before save')
  result.update(owned_destination=dest,backup=str(backup),geometry=geometry,materials=pbr,new_bed_parts=[{'actor':a.get_path_name(),'component':c.get_path_name()}for a,c in new_bed],new_cloth_materials={name:mat.get_path_name()for name,(mat,source)in new_cloth_materials.items()},temporary_material_actors_destroyed=True,protected_other_actors_exact=True)
  pending=project/'private-audit/reference-bed-finish-native.pending.json';pending.write_text(json.dumps(result,indent=2));save_attempted=True
  if not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Candidate bed map save refused')
  result['saved']=True;pending.write_text(json.dumps(result,indent=2));pending.replace(project/'private-audit/reference-bed-finish-native.json');return result
 except Exception as error:
  refusal={'schema':'sub01.reference-bed-finish-refusal.v1','error':str(error),'added_before_rollback':[{'actor':a.get_path_name(),'class':a.get_class().get_name(),'label':a.get_actor_label(),'parent':a.get_attach_parent_actor().get_path_name()if a.get_attach_parent_actor()else None,'components':[{'path':c.get_path_name(),'class':c.get_class().get_name()}for c in a.get_components_by_class(u.ActorComponent)]}for a in eas.get_all_level_actors()if a.get_path_name()not in before]}
  for a,c,name,mat,mesh in cloth:c.set_material(0,mat)
  for a,c,h,eh in old:a.set_actor_hidden_in_game(h);a.set_is_temporarily_hidden_in_editor(eh)
  detach_added(u,eas,before)
  if snapshot(u,list(eas.get_all_level_actors()))!=before:raise RuntimeError('Bed rollback did not restore complete candidate world')
  if save_attempted and not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Candidate rollback map save refused')
  refusal['complete_candidate_world_restored_exact']=True;(project/'private-audit/reference-bed-finish-refusal.json').write_text(json.dumps(refusal,indent=2))
  raise
