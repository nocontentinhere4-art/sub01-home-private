"""Private candidate only: licensed iraida Gaggia thirty-six detailed parts; replace six whole old coffee actors.

Old meshes are never edited. This whole-object retirement proves exact identity,
not original Nanite face acceptance. New source world triangles/PBR stay strict.
"""
import copy,hashlib,json,shutil,time
from pathlib import Path
from uuid import uuid4
ROOT=Path('/workspace/sub01-home-private/real-gaggia-gran-iraida-r1/placed-idle-r4')
SHA='5fdf89fbf47a5a8851a84183ac5526a94ac153f12360e4e2d89bd95fb14fdba2'
HOME_SHA='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
BINDINGS={267+i:(f'CC0_espresso_{i}',f'/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/CC0_espresso_{i}.CC0_espresso_{i}')for i in range(6)}
NAMES={f'GaggiaIdle_{i:03}'for i in range(36)}
PREFIX='SUB01_GenuineGaggiaGran_'
INVENTORY_SHA='0546829c39e6aa6e250265fe22d14946e020f44cf2ba010dbbf6d92d97857a1b'
INVENTORY_PATH=Path('/workspace/sub01-home-private/official-grohe-concetto-r1/source/original-faucet-inventory-106.json')

def contract(report,doc):
 assert report['schema']=='sub01.genuine-gaggia-idle-placement.v1'and report['placed_sha256']==SHA
 assert report['original_source_sha256']=='72acd995c06761ea7470f828c080bedc77d528a61232533dc0240877b5efc098'
 assert report['author']=='iraida'and report['license']=='CC-BY-4.0'and report['not_manufacturer_CAD']is True
 assert report['part_count']==36 and report['unchanged_source_geometry']is True and report['source_materials_unchanged']is True
 assert report['omitted_source_meshes']==['pCylinder34_Coffee_0','pCylinder34_Coffee_dark_0','pCylinder35_Coffee_0','pCylinder35_Coffee_dark_0','polySurface71_Coffee_light_0','polySurface72_Kruzka_1_0','polySurface73_Coffee_light_0']
 assert len(doc['nodes'])==36 and {n['name']for n in doc['nodes']}==NAMES and len(doc['meshes'])==36 and len(doc['materials'])==15
 total=0
 for n in doc['nodes']:
  ps=doc['meshes'][n['mesh']]['primitives'];assert len(ps)==1 and {'POSITION','NORMAL'}<=set(ps[0]['attributes'])
  total+=doc['accessors'][ps[0]['indices']]['count']//3
 assert total==54529
 return True

def original_identity(state,node):
 label,mesh=BINDINGS[node]
 assert state['label']==label and not state['hidden']and not state['editor_hidden']
 assert len(state['components'])==1 and state['components'][0]['mesh']==mesh
 return True

def verify_alpha(u,c,source,dest):
 mat=c.get_material(0);assert mat and mat.get_path_name().startswith(dest+'/')
 current=mat;seen=set();chain=[];actual=None;effective_from=None
 # Interchange deliberately puts glTF blend overrides on an intermediate MI.
 # Resolve the closest explicit override, not only the assigned MI or root.
 for _ in range(16):
  path=current.get_path_name();assert path not in seen,'Cyclic material inheritance';seen.add(path)
  if isinstance(current,u.MaterialInstanceConstant):
   overrides=current.get_editor_property('base_property_overrides')
   override=bool(overrides.get_editor_property('override_blend_mode'))
   value=overrides.get_editor_property('blend_mode')
   chain.append({'path':path,'override_blend_mode':override,'blend_mode':str(value)})
   if actual is None and override:actual=value;effective_from=path
   parent=current.get_editor_property('parent');assert parent and parent!=current;current=parent
  else:
   assert isinstance(current,u.Material),'Unsupported material inheritance root'
   value=current.get_editor_property('blend_mode');chain.append({'path':path,'root_blend_mode':str(value)})
   if actual is None:actual=value;effective_from=path
   break
 else:raise AssertionError('Material inheritance exceeds bounded depth')
 mode=source.get('alphaMode','OPAQUE');assert mode in ('BLEND','OPAQUE'),'Unsupported source alpha mode'
 wanted=u.BlendMode.BLEND_TRANSLUCENT if mode=='BLEND'else u.BlendMode.BLEND_OPAQUE
 assert actual==wanted,'Authored source opacity/blend differs '+source['name']
 return {'alpha_mode':mode,'actual_blend_mode':str(actual),'effective_blend_from':effective_from,'inheritance_chain':chain,'base_alpha_verified_with_PBR':True}

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
 from unreal_component_collision_state import capture as capture_collision,restore as restore_collision
 project=Path(u.Paths.project_dir()).resolve();assert active_candidate_guard(project)
 source=ROOT/'gaggia-gran-idle-placed.glb';assert hashlib.sha256(source.read_bytes()).hexdigest()==SHA
 assert hashlib.sha256((project/'SourceAssets/full-home.glb').read_bytes()).hexdigest()==HOME_SHA
 doc,blob=read_gltf(source);assert contract(json.loads((ROOT/'source-report.json').read_text()),doc)
 proofpath=ROOT/'independent-fit.json';assert hashlib.sha256(proofpath.read_bytes()).hexdigest()=='f788be9ca09691db69b39806ea988ba2a8f2fc71a8c4a117f17ebb53b624967d';proof=json.loads(proofpath.read_text());assert proof['schema']=='sub01.genuine-gaggia-independent-fit.v1'and proof['source_sha256']==SHA and proof['ok']is True and proof['intersections']==[] and proof['cupSupportAccepted']is True,'Exact counter/cup/plant fit proof required'
 inventory_path=INVENTORY_PATH;assert hashlib.sha256(inventory_path.read_bytes()).hexdigest()==INVENTORY_SHA
 inventory=json.loads(inventory_path.read_text());pinned={r['name']:r['snapshot']for r in inventory['components']}
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors)
 assert not any(a.get_actor_label().startswith(PREFIX) for a in actors),'Gaggia Gran already installed; inspect receipt'
 old={}
 for node in BINDINGS:
  matches=[a for a in actors if a.get_name()==f'full-home_node_{node}'];assert len(matches)==1
  actor=matches[0];assert original_identity(before[actor.get_path_name()],node);assert before[actor.get_path_name()]==pinned[f'full-home_node_{node}']
  component=actor.get_components_by_class(u.StaticMeshComponent)[0]
  assert component.get_path_name()==actor.get_path_name()+'.StaticMeshComponent0'
  old[node]=(actor,component)
 collision_states={c.get_path_name():capture_collision(u,c)for actor,c in old.values()}
 result={'schema':'sub01.gaggia-gran-native.v1','source_sha256':SHA,'dry_run':dry_run,'retirement_method':'six complete coffee actors; exact106 live identity/TRS/snapshot; original mesh geometry not reaccepted','independent_fit':proof,'retire_only_source_nodes':list(BINDINGS),'native_visual_verified':False,'actual_game_changed':False,'coffee_interaction_ready':False,'cup_actual_touch_accepted':False,'cup_dynamic_stability_accepted':False,'cup_acceptance_scope':'Numerical static decorative placement only; root reviewed maximum support clearance0.25mm'}
 if dry_run:return result
 dest='/Game/Sub01Home/GenuineGaggiaGran/V_'+SHA[:12]+'/Attempt_'+uuid4().hex
 backup=project/'Saved/PrivateMapBackups'/('gaggia-gran-'+str(time.time_ns()));backup.mkdir(parents=True)
 shutil.copy2(project/'Content/Sub01Home/ActualHome.umap',backup/'ActualHome.umap')
 for name in ('__ExternalActors__','__ExternalObjects__'):
  folder=project/'Content'/name/'Sub01Home/ActualHome'
  if folder.exists():shutil.copytree(folder,backup/name)
 saved=False
 try:
  prepared=project/'Saved/PrivateImportInputs'/('gaggia-gran-'+uuid4().hex+'.glb');pd,pb,mapping=prepare(source,prepared,'GGC')
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
  assert set(by)==set(mapping) and len(by)==36
  parts=[];records=[];allpoints=[]
  for i,node in enumerate(pd['nodes']):
   key=node['name'];matches=list(by[key].values());assert len(matches)==1
   actor,c=matches[0];assert len(actor.get_components_by_class(u.StaticMeshComponent))==1
   owned_geometry(u,c.get_editor_property('static_mesh'),dest)
   assert u.Sub01HomeHandsInstance.finish_pending_static_compilation()==0
   expected,zeros=positive_triangles(expected_triangles(pd,pb,i));actual=native_triangles(u,c)
   assert same_triangles(expected,actual,tolerance=.0001),'Complete source world geometry differs '+key
   primitive=pd['meshes'][node['mesh']]['primitives'][0];mat=pd['materials'][primitive['material']]
   pbr=verify_owned_material(u,c,mat,dest,source_primitive_verified=True);pbr['authored_alpha']=verify_alpha(u,c,mat,dest)
   c.set_collision_profile_name('BlockAll');c.set_collision_enabled(u.CollisionEnabled.QUERY_AND_PHYSICS)
   assert str(c.get_collision_profile_name())=='BlockAll' and c.get_collision_enabled()==u.CollisionEnabled.QUERY_AND_PHYSICS
   actor.set_actor_label(PREFIX+mapping[key]);parts.append(actor);allpoints.extend(p for tri in actual for p in tri)
   records.append({'source_node':mapping[key],'actor':actor.get_path_name(),'component':c.get_path_name(),'positive_triangles':len(actual),'exact_zero_source_triangle_indices':zeros,'material':pbr})
  # Full-source floor fit is measured from actual imported geometry, not bounds of a proxy.
  low=min(p[2] for p in allpoints);assert abs(low-92.25101)<.0001,('Actual feet bottom changed',low)
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
  result.update(owned_destination=dest,backup=str(backup),parts=records,actual_feet_bottom_cm=low,new_parts=36,source_world_tolerance_cm=.0001,originals_before={a.get_path_name():before[a.get_path_name()] for a,c in old.values()},originals_after={a.get_path_name():after[a.get_path_name()] for a,c in old.values()},protected_others_exact=True)
  pending=project/'private-audit/gaggia-gran-native.pending.json';pending.write_text(json.dumps(result,indent=2));saved=True
  assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level();result['saved']=True;pending.write_text(json.dumps(result,indent=2));pending.replace(project/'private-audit/gaggia-gran-native.json');return result
 except Exception as error:
  for actor,c in old.values():
   row=before[actor.get_path_name()];actor.set_actor_hidden_in_game(row['hidden']);actor.set_is_temporarily_hidden_in_editor(row['editor_hidden']);restore_collision(u,c,collision_states[c.get_path_name()],force_response_copy=True)
  detach_added(u,eas,before);assert snapshot(u,eas.get_all_level_actors())==before,'Gaggia Gran complete world rollback failed'
  if saved:assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
  (project/'private-audit/gaggia-gran-refusal.json').write_text(json.dumps({'error':str(error),'complete_world_rollback_verified':True,'backup':str(backup),'quarantined_owned_destination':dest},indent=2));raise
