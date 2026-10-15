"""Genuine indoor Syngonium; exact four whole-actor retirement and three-part candidate replacement."""
import copy,hashlib,json,shutil,time
from pathlib import Path
from uuid import uuid4
ROOT=Path('/workspace/sub01-home-private/real-kitchen-syngonium-r1/indoor-output-r2')
SHA='216360732abb3e660e499d4aa5fefbdb7764a724c1f6d8220649b875464f26af'
SOURCES=(('genuine-kitchen-syngonium.glb',SHA,3,3,68366,'SKN'),)
PREFIX='SUB01GenuineIndoorSyngonium_'
APPROVED_STATIC_COSMETIC=True  # Root viewed exact close source and accepted only declared65internal leaf/rim pairs.
EXPECTED_ORIGINAL={'/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.full-home_node_216': {'label': 'potted_plant_01_leaves_003', 'transform': {'translation': [-79.90845441818237, -352.80442237854004, 94.64170932769775], 'rotation': [0.0, 0.0, 0.0, 1.0], 'scale': [0.4681750535964966, 0.4681750535964966, 0.4681750535964966]}, 'components': [{'path': '/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.full-home_node_216.StaticMeshComponent0', 'mesh': '/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Mesh_165.Mesh_165', 'transform': {'translation': [-79.90845441818237, -352.80442237854004, 94.64170932769775], 'rotation': [0.0, 0.0, 0.0, 1.0], 'scale': [0.4681750535964966, 0.4681750535964966, 0.4681750535964966]}, 'collision': '<CollisionEnabled.QUERY_AND_PHYSICS: 3>', 'profile': 'Custom', 'materials': ['/Game/Sub01Home/ImportedScene/full-home/Materials/potted_plant_01_leaves.potted_plant_01_leaves'], 'tags': []}], 'hidden': False, 'editor_hidden': False, 'actor_collision': True, 'component_visibility': {'/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.full-home_node_216.StaticMeshComponent0': True}}, '/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.full-home_node_217': {'label': 'potted_plant_01_pebbles_003', 'transform': {'translation': [-79.90845441818237, -352.80442237854004, 93.99999657079547], 'rotation': [0.0, 0.0, 0.0, 1.0], 'scale': [0.46919884719648053, 0.46919884719648053, 0.46919884719648053]}, 'components': [{'path': '/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.full-home_node_217.StaticMeshComponent0', 'mesh': '/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Mesh_163.Mesh_163', 'transform': {'translation': [-79.90845441818237, -352.80442237854004, 93.99999657079547], 'rotation': [0.0, 0.0, 0.0, 1.0], 'scale': [0.46919884719648053, 0.46919884719648053, 0.46919884719648053]}, 'collision': '<CollisionEnabled.QUERY_AND_PHYSICS: 3>', 'profile': 'Custom', 'materials': ['/Game/Sub01Home/ImportedScene/full-home/Materials/potted_plant_01_pot.potted_plant_01_pot'], 'tags': []}], 'hidden': False, 'editor_hidden': False, 'actor_collision': True, 'component_visibility': {'/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.full-home_node_217.StaticMeshComponent0': True}}, '/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.full-home_node_218': {'label': 'potted_plant_01_pot_003', 'transform': {'translation': [-79.90845441818237, -352.80442237854004, 94.64170932769775], 'rotation': [0.0, 0.0, 0.0, 1.0], 'scale': [0.4681750535964966, 0.4681750535964966, 0.4681750535964966]}, 'components': [{'path': '/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.full-home_node_218.StaticMeshComponent0', 'mesh': '/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Mesh_164.Mesh_164', 'transform': {'translation': [-79.90845441818237, -352.80442237854004, 94.64170932769775], 'rotation': [0.0, 0.0, 0.0, 1.0], 'scale': [0.4681750535964966, 0.4681750535964966, 0.4681750535964966]}, 'collision': '<CollisionEnabled.QUERY_AND_PHYSICS: 3>', 'profile': 'Custom', 'materials': ['/Game/Sub01Home/ImportedScene/full-home/Materials/potted_plant_01_pot.potted_plant_01_pot'], 'tags': []}], 'hidden': False, 'editor_hidden': False, 'actor_collision': True, 'component_visibility': {'/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.full-home_node_218.StaticMeshComponent0': True}}, '/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.full-home_node_219': {'label': 'potted_plant_01_stem_003', 'transform': {'translation': [-79.90845441818237, -352.80442237854004, 94.64170932769775], 'rotation': [0.0, 0.0, 0.0, 1.0], 'scale': [0.4681750535964966, 0.4681750535964966, 0.4681750535964966]}, 'components': [{'path': '/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.full-home_node_219.StaticMeshComponent0', 'mesh': '/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Mesh_162.Mesh_162', 'transform': {'translation': [-79.90845441818237, -352.80442237854004, 94.64170932769775], 'rotation': [0.0, 0.0, 0.0, 1.0], 'scale': [0.4681750535964966, 0.4681750535964966, 0.4681750535964966]}, 'collision': '<CollisionEnabled.QUERY_AND_PHYSICS: 3>', 'profile': 'Custom', 'materials': ['/Game/Sub01Home/ImportedScene/full-home/Materials/potted_plant_01_pot.potted_plant_01_pot'], 'tags': []}], 'hidden': False, 'editor_hidden': False, 'actor_collision': True, 'component_visibility': {'/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.full-home_node_219.StaticMeshComponent0': True}}}

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

def verify_material_state(u,material,source):
 expected=u.BlendMode.BLEND_MASKED if source.get('alphaMode')=='MASK'else u.BlendMode.BLEND_OPAQUE
 effective_mode=None;effective_sides=None;chain=[]
 while isinstance(material,u.MaterialInstanceConstant):
  overrides=material.get_editor_property('base_property_overrides')
  if effective_mode is None and overrides.get_editor_property('override_blend_mode'):effective_mode=overrides.get_editor_property('blend_mode')
  if effective_sides is None and overrides.get_editor_property('override_two_sided'):effective_sides=bool(overrides.get_editor_property('two_sided'))
  chain.append(material.get_path_name());material=material.get_editor_property('parent');assert material
 assert isinstance(material,u.Material)
 if effective_mode is None:effective_mode=material.get_editor_property('blend_mode')
 if effective_sides is None:effective_sides=bool(material.get_editor_property('two_sided'))
 assert effective_mode==expected and effective_sides is bool(source.get('doubleSided',False)),'Actual owned material blend/culling differs from genuine source'
 return {'effectiveBlendMode':str(effective_mode),'effectiveTwoSided':effective_sides,'parentChain':chain+[material.get_path_name()]}

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
 assert APPROVED_STATIC_COSMETIC,'Source pending root practical review; rejected terracotta may never be installed'
 proofpath=ROOT/'independent-fit.json';assert hashlib.sha256(proofpath.read_bytes()).hexdigest()=='c1c646c0399d6eb19cc8280540e51e7f5a462a42777c8d999ec72671dddb6934';proof=json.loads(proofpath.read_text())
 assert proof['schema']=='sub01.genuine-kitchen-syngonium-independent-fit.v1'and proof['source_sha256']==SHA and proof['nativeChanged']is False
 # Exact disclosed cosmetic leaf/rim contact is distinct from retained kitchen clearance.
 assert proof['fullSourceTriangleIntersections']==[{'new':'SKPlant01','protected':'genuineWhitePot','pairs':65}]
 assert proof['onlyRetiredOriginalNodes']==[216,217,218,219]and proof['lowestPotSkinVerticesSupported']==49
 assert proof['leafMaterialActualDoubleSidedMasked']is True
 sources=[]
 for name,sha,count,mats,tris,prefix in SOURCES:
  path=ROOT/name;assert hashlib.sha256(path.read_bytes()).hexdigest()==sha
  doc,blob=read_gltf(path);assert source_contract(doc,count,mats,tris);sources.append((path,sha,count,prefix))
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors)
 old=[]
 for path,state in EXPECTED_ORIGINAL.items():
  matches=[a for a in actors if a.get_path_name()==path];assert len(matches)==1 and before[path]==state,'Exact whole original kitchen plant binding changed'
  actor=matches[0];cs=actor.get_components_by_class(u.StaticMeshComponent);assert len(cs)==1;old.append((actor,cs[0]))
 assert not any(a.get_actor_label().startswith(PREFIX)for a in actors),'Already installed; inspect genuine-indoor-syngonium-props-native receipt'
 result={'schema':'sub01.genuine-indoor-syngonium-native.v1','dry_run':dry_run,'source_shas':[s[1]for s in sources],'independent_contacts':proof,'contact_receipt_sha256':hashlib.sha256(proofpath.read_bytes()).hexdigest(),'actual_game_changed':False,'native_visual_verified':False,'interaction_contact_ready':False,'original_actor_retirements':list(EXPECTED_ORIGINAL),'discarded_original_meshes_modified':False,'static_cosmetic_internal_leaf_rim_pairs_disclosed':65}
 if dry_run:return result
 dest='/Game/Sub01Home/GenuineIndoorSyngonium/Attempt_'+uuid4().hex
 backup=project/'Saved/PrivateMapBackups'/('genuine-indoor-syngonium-'+str(time.time_ns()));backup.mkdir(parents=True)
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
    pbr=verify_owned_material(u,c,mat,dest,source_primitive_verified=True);pbr['actualSourceBlendAndCulling']=verify_material_state(u,c.get_material(0),mat)
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
  assert len(parts)==3
  for actor in parts:actor.set_actor_hidden_in_game(False)
  expected_after=copy.deepcopy(before)
  for actor,c in old:
   actor.set_actor_hidden_in_game(True);actor.set_is_temporarily_hidden_in_editor(True);c.set_collision_profile_name('NoCollision');c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
   r=expected_after[actor.get_path_name()];r['hidden']=True;r['editor_hidden']=True;r['components'][0]['profile']='NoCollision';r['components'][0]['collision']=str(u.CollisionEnabled.NO_COLLISION)
  assert snapshot(u,actors)==expected_after,'Unexpected original actor/device/TV state changed' 
  assert {a.get_path_name()for a in eas.get_all_level_actors()if a.get_path_name()not in before}=={a.get_path_name()for a in parts}
  assert u.EditorAssetLibrary.save_directory(dest,only_if_is_dirty=False,recursive=True)and active_candidate_guard(project)
  result.update(owned_destination=dest,backup=str(backup),parts=records,new_parts=3,source_world_tolerance_cm=.0001,protected_originals_exact=True)
  pending=project/'private-audit/genuine-indoor-syngonium-props-native.pending.json';pending.write_text(json.dumps(result,indent=2));saved=True
  assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level();result['saved']=True;pending.write_text(json.dumps(result,indent=2));pending.replace(project/'private-audit/genuine-indoor-syngonium-props-native.json');return result
 except Exception as error:
  for actor,c in old:
   state=before[actor.get_path_name()];actor.set_actor_hidden_in_game(state['hidden']);actor.set_is_temporarily_hidden_in_editor(state['editor_hidden']);c.set_collision_profile_name(state['components'][0]['profile']);name=state['components'][0]['collision'].split('CollisionEnabled.',1)[1].split(':',1)[0];c.set_collision_enabled(getattr(u.CollisionEnabled,name))
  detach_added(u,eas,before);assert snapshot(u,eas.get_all_level_actors())==before,'Complete world rollback failed'
  if saved:assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
  (project/'private-audit/genuine-indoor-syngonium-props-refusal.json').write_text(json.dumps({'error':str(error),'complete_world_rollback_verified':True,'backup':str(backup),'quarantined_destination':dest},indent=2));raise
