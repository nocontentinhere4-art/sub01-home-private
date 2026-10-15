"""Private candidate only: genuine Haven33 parts; replace four complete old actors.

Old meshes are never edited. This whole-object retirement proves exact identity,
not original Nanite face acceptance. New source world triangles/PBR stay strict.
"""
import copy,hashlib,json,shutil,time
from pathlib import Path
from uuid import uuid4
ROOT=Path('/workspace/sub01-home-private/reference-gaming-lounge-r1/haven-output-r2')
SHA='b69d4cbcf53ad4603bcc852a3dc158b1424d2969bbf688d7ce4b39ae108e24f3'
HOME_SHA='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
BINDINGS={172:('Haven_felt',131),173:('Haven_legs',132),174:('Haven_linen',133),175:('Haven_seams',134)}
NAMES={f'GamingHaven_{i:03}' for i in range(27)}|{f'GamingLoosePillow_{i:02}_{j:03}' for i in range(2) for j in range(3)}
PREFIX='SUB01_GenuineHaven_'
OLD_TRS={'translation':[-179.99999523162842,10.000000149011612,0.0],'rotation':[0.0,0.0,.7071068407911908,.7071067215818992],'scale':[1.0,1.0,1.0]}

def contract(report,doc):
 assert report['schema']=='sub01.genuine-haven-gaming-source.v1' and report['source_output_sha256']==SHA
 assert report['original_source_sha256']=='acad7fd3d9431929c303b1ae5cd476d7a108ce352a99ddf40e4e78ea7b9f2643' and report['license']=='CC0-1.0'
 assert report['retire_only_original_sofa_nodes']==[172,173,174,175] and report['base_physical_dimensions_unchanged'] is True and report['floor_feet_bottom_cm']==2.505
 assert len(report['base_source_local_geometry_exact'])==27 and all(r['local_geometry_exact'] is True for r in report['base_source_local_geometry_exact'])
 assert len(doc['nodes'])==33 and {n['name'] for n in doc['nodes']}==NAMES and len(doc['meshes'])==33 and len(doc['materials'])==10
 count=0
 for node in doc['nodes']:
  ps=doc['meshes'][node['mesh']]['primitives'];assert len(ps)==1
  p=ps[0];assert {'POSITION','NORMAL','TEXCOORD_0'}<=set(p['attributes'])
  count+=doc['accessors'][p['indices']]['count']//3
 assert count==126556
 return True

def original_identity(state,node):
 label,index=BINDINGS[node];mesh=f'/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Mesh_{index}.Mesh_{index}'
 assert state['label']==label and state['transform']==OLD_TRS and not state['hidden'] and not state['editor_hidden']
 assert len(state['components'])==1 and state['components'][0]['mesh']==mesh and state['components'][0]['transform']==OLD_TRS
 return True

def run(dry_run=True):
 raise RuntimeError("OWNER REJECTED b69d Haven source: do not import; select a different realistic model")
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
 source=ROOT/'genuine-navy-haven-with-pillows.glb';assert hashlib.sha256(source.read_bytes()).hexdigest()==SHA
 assert hashlib.sha256((project/'SourceAssets/full-home.glb').read_bytes()).hexdigest()==HOME_SHA
 doc,blob=read_gltf(source);assert contract(json.loads((ROOT/'haven-source-report.json').read_text()),doc)
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors)
 assert not any(a.get_actor_label().startswith(PREFIX) for a in actors),'Haven already installed; inspect receipt'
 old={}
 for node in BINDINGS:
  matches=[a for a in actors if a.get_name()==f'full-home_node_{node}'];assert len(matches)==1
  actor=matches[0];assert original_identity(before[actor.get_path_name()],node)
  component=actor.get_components_by_class(u.StaticMeshComponent)[0]
  assert component.get_path_name()==actor.get_path_name()+'.StaticMeshComponent0'
  old[node]=(actor,component)
 result={'schema':'sub01.genuine-haven-native.v1','source_sha256':SHA,'dry_run':dry_run,'retirement_method':'four complete actors; exact source identity and TRS; original mesh geometry not reaccepted','retire_only_source_nodes':list(BINDINGS),'native_visual_verified':False,'actual_game_changed':False,'seating_contact_ready':False}
 if dry_run:return result
 dest='/Game/Sub01Home/GenuineHaven/V_'+SHA[:12]+'/Attempt_'+uuid4().hex
 backup=project/'Saved/PrivateMapBackups'/('genuine-haven-'+str(time.time_ns()));backup.mkdir(parents=True)
 shutil.copy2(project/'Content/Sub01Home/ActualHome.umap',backup/'ActualHome.umap')
 for name in ('__ExternalActors__','__ExternalObjects__'):
  folder=project/'Content'/name/'Sub01Home/ActualHome'
  if folder.exists():shutil.copytree(folder,backup/name)
 saved=False
 try:
  prepared=project/'Saved/PrivateImportInputs'/('genuine-haven-'+uuid4().hex+'.glb');pd,pb,mapping=prepare(source,prepared,'GHV')
  manager=u.InterchangeManager.get_interchange_manager_scripted();params=u.ImportAssetParameters();params.set_editor_property('is_automated',True)
  assert manager.import_scene(dest,manager.create_source_data(str(prepared)),params);manager.wait_until_all_tasks_done(False)
  added=[a for a in eas.get_all_level_actors() if a.get_path_name() not in before];roots=[];by={}
  for actor in added:
   actor.set_actor_hidden_in_game(True);comps=actor.get_components_by_class(u.StaticMeshComponent)
   if not comps:
    kind=actor.get_class().get_name();ac=actor.get_components_by_class(u.ActorComponent)
    assert kind in ('Actor','InterchangeSceneActor') and (kind!='Actor' or (len(ac)==1 and ac[0].get_class().get_name()=='SceneComponent'))
    assert not actor.get_attach_parent_actor() or actor.get_attach_parent_actor().get_path_name() not in before
    assert not any(ch.get_path_name() in before for ch in actor.get_attached_actors());roots.append(actor)
   for c in comps:
    mesh=c.get_editor_property('static_mesh');assert mesh and mesh.get_path_name().startswith(dest+'/')
    for key in {actor.get_actor_label(),mesh.get_name()}:
     if key in mapping:by.setdefault(key,{})[c.get_path_name()]=(actor,c)
  assert set(by)==set(mapping) and len(by)==33
  parts=[];records=[];allpoints=[]
  for i,node in enumerate(pd['nodes']):
   key=node['name'];matches=list(by[key].values());assert len(matches)==1
   actor,c=matches[0];assert len(actor.get_components_by_class(u.StaticMeshComponent))==1
   owned_geometry(u,c.get_editor_property('static_mesh'),dest)
   assert u.Sub01HomeHandsInstance.finish_pending_static_compilation()==0
   expected,zeros=positive_triangles(expected_triangles(pd,pb,i));actual=native_triangles(u,c)
   assert same_triangles(expected,actual,tolerance=.0001),'Complete source world geometry differs '+key
   primitive=pd['meshes'][node['mesh']]['primitives'][0];mat=pd['materials'][primitive['material']]
   pbr=verify_owned_material(u,c,mat,dest,source_primitive_verified=True)
   c.set_collision_profile_name('BlockAll');c.set_collision_enabled(u.CollisionEnabled.QUERY_AND_PHYSICS)
   assert str(c.get_collision_profile_name())=='BlockAll' and c.get_collision_enabled()==u.CollisionEnabled.QUERY_AND_PHYSICS
   actor.set_actor_label(PREFIX+mapping[key]);parts.append(actor);allpoints.extend(p for tri in actual for p in tri)
   records.append({'source_node':mapping[key],'actor':actor.get_path_name(),'component':c.get_path_name(),'positive_triangles':len(actual),'exact_zero_source_triangle_indices':zeros,'material':pbr})
  # Full-source floor fit is measured from actual imported geometry, not bounds of a proxy.
  low=min(p[2] for p in allpoints);assert abs(low-2.505)<.0001,('Actual feet bottom changed',low)
  assert snapshot(u,actors)==before,'Import changed original actors'
  state=snapshot(u,parts);rootpaths={a.get_path_name() for a in roots}
  for actor in parts:
   if actor.get_attach_parent_actor():
    assert actor.get_attach_parent_actor().get_path_name() in rootpaths
    actor.detach_from_actor(u.DetachmentRule.KEEP_WORLD,u.DetachmentRule.KEEP_WORLD,u.DetachmentRule.KEEP_WORLD)
  assert snapshot(u,parts)==state
  for actor in reversed(roots):
   assert not actor.get_components_by_class(u.StaticMeshComponent) and not actor.get_attached_actors();assert eas.destroy_actor(actor)
  after=copy.deepcopy(before)
  for actor,c in old.values():
   actor.set_actor_hidden_in_game(True);actor.set_is_temporarily_hidden_in_editor(True);c.set_collision_profile_name('NoCollision');c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
   row=after[actor.get_path_name()];row['hidden']=True;row['editor_hidden']=True;row['components'][0]['profile']='NoCollision';row['components'][0]['collision']=str(u.CollisionEnabled.NO_COLLISION)
  for actor in parts:actor.set_actor_hidden_in_game(False)
  assert snapshot(u,actors)==after,'Unrelated actor/device/TV state changed'
  assert {a.get_path_name() for a in eas.get_all_level_actors() if a.get_path_name() not in before}=={a.get_path_name() for a in parts}
  assert u.EditorAssetLibrary.save_directory(dest,only_if_is_dirty=False,recursive=True) and active_candidate_guard(project)
  result.update(owned_destination=dest,backup=str(backup),parts=records,actual_feet_bottom_cm=low,new_parts=33,source_world_tolerance_cm=.0001,originals_before={a.get_path_name():before[a.get_path_name()] for a,c in old.values()},originals_after={a.get_path_name():after[a.get_path_name()] for a,c in old.values()},protected_others_exact=True)
  pending=project/'private-audit/genuine-haven-native.pending.json';pending.write_text(json.dumps(result,indent=2));saved=True
  assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level();result['saved']=True;pending.write_text(json.dumps(result,indent=2));pending.replace(project/'private-audit/genuine-haven-native.json');return result
 except Exception as error:
  for actor,c in old.values():
   row=before[actor.get_path_name()];actor.set_actor_hidden_in_game(row['hidden']);actor.set_is_temporarily_hidden_in_editor(row['editor_hidden']);c.set_collision_profile_name(row['components'][0]['profile']);name=row['components'][0]['collision'].split('CollisionEnabled.',1)[1].split(':',1)[0];c.set_collision_enabled(getattr(u.CollisionEnabled,name))
  detach_added(u,eas,before);assert snapshot(u,eas.get_all_level_actors())==before,'Haven complete world rollback failed'
  if saved:assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
  (project/'private-audit/genuine-haven-refusal.json').write_text(json.dumps({'error':str(error),'complete_world_rollback_verified':True,'backup':str(backup),'quarantined_owned_destination':dest},indent=2));raise
