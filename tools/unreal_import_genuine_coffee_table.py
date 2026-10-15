"""Candidate-only exact genuine4504-triangle coffee table; reversible single275 retirement."""
from pathlib import Path
import copy,hashlib,json,shutil,time
from uuid import uuid4
ROOT=Path('/workspace/sub01-home-private/reference-gaming-lounge-r1/table-output')
SHA='c05a5d343ff55dd9e486f62626374e4879cab24e456fa14b8da58605ff88abb9'
HOME_SHA='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
BINDINGS={275:'/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Cube_003.Cube_003'}
LABEL='SUB01_GenuineCoffeeTable'
def contract(report,doc):
 assert report['schema']=='sub01.genuine-coffee-table-source.v1'and report['source_output_sha256']==SHA and report['retire_only_original_table_node']==275 and report['source_physical_dimensions_preserved_1_to_1']is True
 assert report['source']['asset']=='modern_coffee_table_01'and report['source']['license']=='CC0-1.0'
 assert len(doc['nodes'])==1 and doc['nodes'][0]['name']=='GamingCoffeeTable_000'and len(doc['meshes'])==1 and len(doc['materials'])==1
 pr=doc['meshes'][doc['nodes'][0]['mesh']]['primitives'];assert len(pr)==1 and doc['materials'][pr[0]['material']]['name']=='modern_coffee_table_01'
 attrs=pr[0]['attributes'];assert {'POSITION','NORMAL','TEXCOORD_0'}<=set(attrs)and doc['accessors'][attrs['POSITION']]['count']==3995 and doc['accessors'][pr[0]['indices']]['count']==4504*3
 return True

def run(dry_run=True,retired_receipt=None,retired_receipt_sha=None):
 raise RuntimeError('Human rejected c05a5 table visual source; retained importer is historical and must not execute')
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard
 from home_asset_audit import read_gltf
 from unreal_import_reference_entry import snapshot
 from unreal_import_reference_bed_finish import prepare
 from unreal_import_real_wc import expected_triangles,owned_geometry
 from unreal_remove_frame_backings import native_triangles,same_triangles
 from unreal_import_reference_wall_console import positive_triangles
 from unreal_import_real_bathroom_pendant import verify_owned_material
 from unreal_owned_import_cleanup import detach_added
 project=Path(u.Paths.project_dir()).resolve();assert active_candidate_guard(project);source=ROOT/'genuine-coffee-table.glb';home=project/'SourceAssets/full-home.glb'
 assert hashlib.sha256(source.read_bytes()).hexdigest()==SHA and hashlib.sha256(home.read_bytes()).hexdigest()==HOME_SHA
 doc,blob=read_gltf(source);assert contract(json.loads((ROOT/'table-only-source-report.json').read_text()),doc);hd,hb=read_gltf(home);eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors)
 assert not any(a.get_actor_label()==LABEL for a in actors),'Genuine table already installed; inspect receipt'
 old=[a for a in actors if a.get_name()=='full-home_node_275'];assert len(old)==1;old=old[0];cs=old.get_components_by_class(u.StaticMeshComponent);assert len(cs)==1;c=cs[0];assert c.get_path_name()==old.get_path_name()+'.StaticMeshComponent0'and c.get_editor_property('static_mesh').get_path_name()==BINDINGS[275]and old.get_actor_label()=='modern_coffee_table_01'
 if old.get_editor_property('hidden'):
  assert retired_receipt and retired_receipt_sha,'Already hidden original275 requires exact explicit prior single-retirement receipt'
  raw=Path(retired_receipt).read_bytes();assert hashlib.sha256(raw).hexdigest()==retired_receipt_sha;r=json.loads(raw);assert r['sourceHomeSha256']==HOME_SHA and r['sourceNode']==275 and r['retiredActorAfter']==before[old.get_path_name()]and r['onlyRetiredActor']==old.get_path_name();assert r['originalSourceGeometryProven']is True
 # Whole uniquely bound actor replacement: no shared mesh modification or partial surgery.
 assert old.get_path_name()=='/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.full-home_node_275'
 node=hd['nodes'][275];assert 'mesh'in node and len(hd['meshes'][node['mesh']]['primitives'])==1
 trs=before[old.get_path_name()]['components'][0]['transform'];pinned={'translation':[-320.0000286102295,9.971301257610321,.013431409024633467],'rotation':[0.,0.,0.,1.],'scale':[1.1666666269302368]*3}
 assert all(len(trs[k])==len(v)and all(abs(a-b)<=1e-9 for a,b in zip(trs[k],v))for k,v in pinned.items()),'Whole275 exact source binding/TRS changed'
 originalaudit={'method':'owner-authorized-whole-unique-actor-replacement','source_home_sha256':HOME_SHA,'source_node':275,'source_mesh':node['mesh'],'source_primitive_count':1,'native_actor':old.get_path_name(),'native_mesh':BINDINGS[275],'component_world_trs':trs,'original_mesh_modified':False,'discarded_original_triangle_audit_required':False,'scope':'entire unique actor only; no shared-mesh or partial-batch edits'}
 dest='/Game/Sub01Home/GenuineCoffeeTable/V_'+SHA[:12]+'/Attempt_'+uuid4().hex
 result={'schema':'sub01.genuine-coffee-table-native.v1','dry_run':dry_run,'source_sha256':SHA,'only_retire_original_source_node':275,'original_source_audit':originalaudit,'native_visual_verified':False,'actual_game_changed':False}
 if dry_run:return result
 backup=project/'Saved/PrivateMapBackups'/('genuine-coffee-'+str(time.time_ns()));backup.mkdir(parents=True);shutil.copy2(project/'Content/Sub01Home/ActualHome.umap',backup/'ActualHome.umap')
 for name in('__ExternalActors__','__ExternalObjects__'):
  folder=project/'Content'/name/'Sub01Home/ActualHome'
  if folder.exists():shutil.copytree(folder,backup/name)
 saved=False;parts=[];roots=[]
 try:
  prepared=project/'Saved/PrivateImportInputs'/('genuine-coffee-'+uuid4().hex+'.glb');pd,pb,mapping=prepare(source,prepared,'GCT');manager=u.InterchangeManager.get_interchange_manager_scripted();params=u.ImportAssetParameters();params.set_editor_property('is_automated',True)
  assert manager.import_scene(dest,manager.create_source_data(str(prepared)),params),'Genuine table import refused';manager.wait_until_all_tasks_done(False);added=[a for a in eas.get_all_level_actors()if a.get_path_name()not in before];by={}
  for a in added:
   a.set_actor_hidden_in_game(True);comps=a.get_components_by_class(u.StaticMeshComponent)
   if not comps:
    kind=a.get_class().get_name();allc=a.get_components_by_class(u.ActorComponent);assert kind in('Actor','InterchangeSceneActor')and(kind!='Actor'or(len(allc)==1 and allc[0].get_class().get_name()=='SceneComponent'))
    assert not a.get_attach_parent_actor()or a.get_attach_parent_actor().get_path_name()not in before;assert not any(ch.get_path_name()in before for ch in a.get_attached_actors());roots.append(a)
   for nc in comps:
    mesh=nc.get_editor_property('static_mesh');assert mesh and mesh.get_path_name().startswith(dest+'/')
    for key in{a.get_actor_label(),mesh.get_name()}:
     if key in mapping:by.setdefault(key,{})[nc.get_path_name()]=(a,nc)
  matches=list(by.get('GCT00',{}).values());assert len(matches)==1;new,nc=matches[0];assert len(new.get_components_by_class(u.StaticMeshComponent))==1;owned_geometry(u,nc.get_editor_property('static_mesh'),dest);assert u.Sub01HomeHandsInstance.finish_pending_static_compilation()==0,'Fresh table source compilation incomplete';expected,zero=positive_triangles(expected_triangles(pd,pb,0));actual_raw=native_triangles(u,nc);actual,native_zero=positive_triangles(actual_raw);assert len(native_zero)in(0,12) and len(expected)==4492 and len(zero)==12 and len(expected)+len(zero)==4504 and same_triangles(expected,actual,tolerance=.0001),'Complete4504triangle/world geometry changed'
  mat=pd['materials'][pd['meshes'][pd['nodes'][0]['mesh']]['primitives'][0]['material']];pbr=verify_owned_material(u,nc,mat,dest,source_primitive_verified=True);nc.set_collision_profile_name('BlockAll');nc.set_collision_enabled(u.CollisionEnabled.QUERY_AND_PHYSICS);assert nc.get_collision_enabled()==u.CollisionEnabled.QUERY_AND_PHYSICS and str(nc.get_collision_profile_name())=='BlockAll';new.set_actor_label(LABEL);parts=[new]
  assert snapshot(u,actors)==before,'Source import changed original actors'
  rootpaths={a.get_path_name()for a in roots};state=snapshot(u,parts)
  if new.get_attach_parent_actor():
   assert new.get_attach_parent_actor().get_path_name()in rootpaths;new.detach_from_actor(u.DetachmentRule.KEEP_WORLD,u.DetachmentRule.KEEP_WORLD,u.DetachmentRule.KEEP_WORLD)
  assert snapshot(u,parts)==state
  for root in reversed(roots):
   assert not root.get_components_by_class(u.StaticMeshComponent)and not root.get_attached_actors();assert eas.destroy_actor(root)
  old.set_actor_hidden_in_game(True);old.set_is_temporarily_hidden_in_editor(True);c.set_collision_profile_name('NoCollision');c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION);expected_after=copy.deepcopy(before);row=expected_after[old.get_path_name()];row['hidden']=True;row['editor_hidden']=True;row['components'][0]['collision']=str(u.CollisionEnabled.NO_COLLISION);row['components'][0]['profile']='NoCollision';new.set_actor_hidden_in_game(False)
  assert snapshot(u,actors)==expected_after,'Unrelated original actor changed';assert {a.get_path_name()for a in eas.get_all_level_actors()if a.get_path_name()not in before}=={new.get_path_name()},'Unexpected import/audit actors remain'
  assert u.EditorAssetLibrary.save_directory(dest,only_if_is_dirty=False,recursive=True)and active_candidate_guard(project);result.update(owned_destination=dest,backup=str(backup),source_positive_triangles=len(actual),source_indexed_triangles=4504,source_exact_zero_triangle_indices=zero,native_indexed_triangles=len(actual_raw),native_exact_zero_triangle_indices=native_zero,source_world_geometry_tolerance_cm=.0001,material=pbr,new_actor=new.get_path_name(),new_component=nc.get_path_name(),old_retirement_before=before[old.get_path_name()],old_retirement_after=expected_after[old.get_path_name()],protected_originals_exact=True);pending=project/'private-audit/genuine-coffee-table-native.pending.json';pending.write_text(json.dumps(result,indent=2));saved=True;assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level();result['saved']=True;pending.write_text(json.dumps(result,indent=2));pending.replace(project/'private-audit/genuine-coffee-table-native.json');return result
 except Exception as error:
  previous=before[old.get_path_name()];old.set_actor_hidden_in_game(previous['hidden']);old.set_is_temporarily_hidden_in_editor(previous['editor_hidden']);c.set_collision_profile_name(previous['components'][0]['profile']);name=previous['components'][0]['collision'].split('CollisionEnabled.',1)[1].split(':',1)[0];c.set_collision_enabled(getattr(u.CollisionEnabled,name));detach_added(u,eas,before);assert snapshot(u,eas.get_all_level_actors())==before,'Table rollback failed exact complete world restoration'
  if saved:assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level(),'Rollback map save refused'
  (project/'private-audit/genuine-coffee-table-refusal.json').write_text(json.dumps({'error':str(error),'complete_world_rollback_verified':True,'backup':str(backup),'quarantined_owned_destination':dest},indent=2));raise
