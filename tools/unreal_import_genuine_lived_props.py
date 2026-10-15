"""Seven genuine CC0 decorative parts; candidate-only atomic addition, no retirement/input."""
import hashlib,json,shutil,time
from pathlib import Path
from uuid import uuid4
ROOT=Path('/workspace/sub01-home-private/real-lived-props-r1/output')
SOURCES=(('genuine-kitchen-lived-props.glb','966f2798427c6726cbdca404f73792474e69349016662dc8f1e18c084b363626',3,3,24654,'KLP'),('genuine-around-plant.glb','17f547cd694ceb85d15f7eb49890ec0f8a4de6e0f8c23eec08d19ab63c728abf',4,1,8929,'ALP'))
PREFIX='SUB01GenuineLived_'

def source_contract(doc,count,mats,tris):
 assert len(doc['nodes'])==count and len(doc['meshes'])==count and len(doc['materials'])==mats
 assert all('mesh'in n and not n.get('children')for n in doc['nodes'])
 total=0
 for n in doc['nodes']:
  ps=doc['meshes'][n['mesh']]['primitives'];assert len(ps)==1
  p=ps[0];assert {'POSITION','NORMAL','TEXCOORD_0'}<=set(p['attributes'])
  total+=doc['accessors'][p['indices']]['count']//3
 assert total==tris
 return True

def run(dry_run=True):
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
 project=Path(u.Paths.project_dir()).resolve();assert active_candidate_guard(project)
 proofpath=ROOT/'independent-contacts.json';assert hashlib.sha256(proofpath.read_bytes()).hexdigest()=='e2e92347b87a9882b5c2103669c2bac7b269c5adda3c1d0adbb83b4e209c0d5c';proof=json.loads(proofpath.read_text());assert proof['schema']=='sub01.independent-real-lived-props-source.v1'and proof['accepted']is True and proof['triangleIntersectionFindings']==[] and proof['nativeChanged']is False
 # Frozen independent receipt is retained in the native receipt; exact inputs are checked below.
 assert all(sha in proofpath.read_text()for _,sha,*_ in SOURCES),'Independent contact proof must pin both exact final GLBs'
 sources=[]
 for name,sha,count,mats,tris,prefix in SOURCES:
  path=ROOT/name;assert hashlib.sha256(path.read_bytes()).hexdigest()==sha
  doc,blob=read_gltf(path);assert source_contract(doc,count,mats,tris);sources.append((path,sha,count,prefix))
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors)
 assert not any(a.get_actor_label().startswith(PREFIX)for a in actors),'Already installed; inspect genuine-lived-props-native receipt'
 result={'schema':'sub01.genuine-lived-props-native.v1','dry_run':dry_run,'source_shas':[s[1]for s in sources],'independent_contacts':proof,'contact_receipt_sha256':hashlib.sha256(proofpath.read_bytes()).hexdigest(),'actual_game_changed':False,'native_visual_verified':False,'interaction_contact_ready':False,'original_actor_retirements':[]}
 if dry_run:return result
 dest='/Game/Sub01Home/GenuineLivedProps/Attempt_'+uuid4().hex
 backup=project/'Saved/PrivateMapBackups'/('genuine-lived-'+str(time.time_ns()));backup.mkdir(parents=True)
 shutil.copy2(project/'Content/Sub01Home/ActualHome.umap',backup/'ActualHome.umap')
 for name in('__ExternalActors__','__ExternalObjects__'):
  folder=project/'Content'/name/'Sub01Home/ActualHome'
  if folder.exists():shutil.copytree(folder,backup/name)
 saved=False;parts=[];records=[]
 try:
  for source,sha,count,prefix in sources:
   prior={a.get_path_name()for a in eas.get_all_level_actors()}
   prepared=project/'Saved/PrivateImportInputs'/('lived-'+uuid4().hex+'.glb');pd,pb,mapping=prepare(source,prepared,prefix)
   manager=u.InterchangeManager.get_interchange_manager_scripted();params=u.ImportAssetParameters();params.set_editor_property('is_automated',True)
   assert manager.import_scene(dest+'/'+prefix,manager.create_source_data(str(prepared)),params);manager.wait_until_all_tasks_done(False)
   added=[a for a in eas.get_all_level_actors()if a.get_path_name()not in prior];roots=[];by={}
   for actor in added:
    actor.set_actor_hidden_in_game(True);comps=actor.get_components_by_class(u.StaticMeshComponent)
    if not comps:
     kind=actor.get_class().get_name();ac=actor.get_components_by_class(u.ActorComponent)
     assert kind in('Actor','InterchangeSceneActor')and(kind!='Actor'or(len(ac)==1 and ac[0].get_class().get_name()=='SceneComponent'))
     assert not actor.get_attach_parent_actor()or actor.get_attach_parent_actor().get_path_name()not in before
     assert not any(ch.get_path_name()in before for ch in actor.get_attached_actors());roots.append(actor)
    for c in comps:
     mesh=c.get_editor_property('static_mesh');assert mesh and mesh.get_path_name().startswith(dest+'/')
     for key in{actor.get_actor_label(),mesh.get_name()}:
      if key in mapping:by.setdefault(key,{})[c.get_path_name()]=(actor,c)
   assert set(by)==set(mapping)and len(by)==count
   group=[]
   for i,node in enumerate(pd['nodes']):
    matches=list(by[node['name']].values());assert len(matches)==1
    actor,c=matches[0];assert len(actor.get_components_by_class(u.StaticMeshComponent))==1
    owned_geometry(u,c.get_editor_property('static_mesh'),dest)
    assert u.Sub01HomeHandsInstance.finish_pending_static_compilation()==0
    expected,zeros=positive_triangles(expected_triangles(pd,pb,i));actual=native_triangles(u,c)
    assert same_triangles(expected,actual,tolerance=.0001),'Complete source geometry differs '+node['name']
    primitive=pd['meshes'][node['mesh']]['primitives'][0];mat=pd['materials'][primitive['material']]
    pbr=verify_owned_material(u,c,mat,dest,source_primitive_verified=True)
    c.set_collision_profile_name('BlockAll');c.set_collision_enabled(u.CollisionEnabled.QUERY_AND_PHYSICS)
    assert str(c.get_collision_profile_name())=='BlockAll'and c.get_collision_enabled()==u.CollisionEnabled.QUERY_AND_PHYSICS
    actor.set_actor_label(PREFIX+mapping[node['name']]);group.append(actor);parts.append(actor)
    records.append({'source_sha256':sha,'source_node':mapping[node['name']],'actor':actor.get_path_name(),'component':c.get_path_name(),'positive_triangles':len(actual),'exact_zero_source_triangle_indices':zeros,'material':pbr})
   assert snapshot(u,actors)==before
   states=snapshot(u,group);rootpaths={a.get_path_name()for a in roots}
   for actor in group:
    if actor.get_attach_parent_actor():
     assert actor.get_attach_parent_actor().get_path_name()in rootpaths
     actor.detach_from_actor(u.DetachmentRule.KEEP_WORLD,u.DetachmentRule.KEEP_WORLD,u.DetachmentRule.KEEP_WORLD)
   assert snapshot(u,group)==states
   for actor in reversed(roots):
    assert not actor.get_components_by_class(u.StaticMeshComponent)and not actor.get_attached_actors();assert eas.destroy_actor(actor)
  assert len(parts)==7
  for actor in parts:actor.set_actor_hidden_in_game(False)
  assert snapshot(u,actors)==before,'Existing actors/device/TV state changed'
  assert {a.get_path_name()for a in eas.get_all_level_actors()if a.get_path_name()not in before}=={a.get_path_name()for a in parts}
  assert u.EditorAssetLibrary.save_directory(dest,only_if_is_dirty=False,recursive=True)and active_candidate_guard(project)
  result.update(owned_destination=dest,backup=str(backup),parts=records,new_parts=7,source_world_tolerance_cm=.0001,protected_originals_exact=True)
  pending=project/'private-audit/genuine-lived-props-native.pending.json';pending.write_text(json.dumps(result,indent=2));saved=True
  assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level();result['saved']=True;pending.write_text(json.dumps(result,indent=2));pending.replace(project/'private-audit/genuine-lived-props-native.json');return result
 except Exception as error:
  detach_added(u,eas,before);assert snapshot(u,eas.get_all_level_actors())==before,'Complete world rollback failed'
  if saved:assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
  (project/'private-audit/genuine-lived-props-refusal.json').write_text(json.dumps({'error':str(error),'complete_world_rollback_verified':True,'backup':str(backup),'quarantined_destination':dest},indent=2));raise
