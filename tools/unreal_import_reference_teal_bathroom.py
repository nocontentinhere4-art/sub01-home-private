"""Future sole-owner warm Editor transaction for a PROVED private teal finish.

Never invoked by source preparation. Default dry-run. Refuses source contacts,
collapsed wood UVs, changed saved bath/corridor/doors, and unknown fixture owners.
Keeps existing90 actors and physical transforms/collision. Only four wood meshes
may receive UV-only owned replacements; other opaque parts receive materials.
Existing clear-glass helper bindings remain exact. Source dressing is additive.
"""
import copy,hashlib,json,shutil,time,uuid
from pathlib import Path
ORIGINAL=Path('/workspace/sub01-home-private/authentic-bath-doors-fit-r3/output/bath-fixtures.glb')
BASE_SHA='b8d190b7d7cf274126b4be35cf2ccf447b25c742da037cc222c43fe57f437a92'
CORRIDOR_SHA='5ffac2406e668a327427e60bc75e3ee3ecf13a89381d0312b821277386cb9c91'
DOOR_SHA='5b8a2bb8b4bb8fe19af1d0c086fb78f3e7f9dff9e06170a06642a8f3d1761a0c'
WOOD={'SUB01_vanity_004','SUB01_vanity_016','SUB01_vanity_017','SUB01_vanity_018'}

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def contract(root,proof_path):
 root=Path(root);proof=json.loads(Path(proof_path).read_text());report=json.loads((root/'source-report.json').read_text())
 if (proof.get('schema')!='sub01.reference-teal-bathroom-independent-source.v1'or proof.get('source_ready')is not True or proof.get('native_imported')is not False or proof.get('native_visual_physical_accepted')is not False or proof.get('unresolved_positive_crossings')!=[] or proof.get('wood_positive_triangles_with_collapsed_uvs')!=0):raise RuntimeError('Independent exported geometry/contact/wood proof must pass; no safety waiver')
 parity=proof.get('fixture_corner_parity',{})
 if not parity.get('ok')or parity.get('matched_parts')!=90 or parity.get('unmatched_styled_parts')!=0 or parity.get('tolerance_cm')!=.0001 or len(parity.get('rows',[]))!=90:raise RuntimeError('Exact90 fixture corner bijection required')
 if report.get('source_sha256')!=BASE_SHA or report.get('fixture_parts')!=90 or digest(ORIGINAL)!=BASE_SHA:raise RuntimeError('Frozen baseline fixtures required')
 for name in ('bath-style-fixtures.glb','bath-style-dressing.glb'):
  path=root/name;value=digest(path)
  if report['files'].get(name)!=value or proof['inputs'].get(str(path))!=value:raise RuntimeError('Actual proved style source changed '+name)
 if any(not r.get('all_positive_faces_have_uv_area')for r in proof.get('wood_uv',[])):raise RuntimeError('Collapsed positive wood UV face refused')
 return proof,report

def run(style_root,proof_path,dry_run=True):
 import unreal as u
 from home_asset_audit import read_gltf
 from unreal_import_authentic_bath_fixtures import prepare_import
 from unreal_import_real_wc import expected_triangles,owned_geometry
 from unreal_remove_frame_backings import native_triangles,same_triangles
 from unreal_import_real_linea140 import verify_materials
 from unreal_import_reference_dressing import fingerprint
 from unreal_component_collision_state import capture,restore,signature
 from unreal_owned_import_cleanup import detach_added
 proof,report=contract(style_root,proof_path);root=Path(style_root);project=Path(u.Paths.project_dir());audit=project/'private-audit'
 if(audit/'reference-teal-bathroom-native.json').exists():raise RuntimeError('Existing style receipt needs deliberate review; no duplicate application')
 world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
 if not world or world.get_path_name()!='/Game/Sub01Home/ActualHome.ActualHome':raise RuntimeError('Exact loaded private ActualHome required')
 receipts={n:(audit/n).read_bytes()for n in ['authentic-bath-fixtures-native.json','bathroom-corridor-native-import.json','authentic-doors-native.json']}
 bath,corridor,doors=[json.loads(receipts[n])for n in receipts]
 if not bath.get('saved')or bath.get('source_sha256')!=BASE_SHA or len(bath.get('parts',[]))!=90:raise RuntimeError('Exact actual90 saved bath receipt required')
 if not corridor.get('saved')or corridor.get('export_sha256')!=CORRIDOR_SHA or not doors.get('saved')or doors.get('source_sha256')!=DOOR_SHA or len(doors.get('parts',[]))!=76:raise RuntimeError('Exact current corridor and complete real doors required')
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);original=list(eas.get_all_level_actors());before=fingerprint(u,original);by_path={a.get_path_name():a for a in original}
 saved_by_label={};snapshots=[]
 for row in bath['parts']:
  a=by_path.get(row['actor']);cs=a.get_components_by_class(u.StaticMeshComponent)if a else[]
  if not a or len(cs)!=1 or cs[0].get_path_name()!=row['component']or bool(a.get_editor_property('hidden'))or not cs[0].get_editor_property('visible'):raise RuntimeError('Exact active saved fixture binding required')
  c=cs[0];mesh=c.get_editor_property('static_mesh')
  if not mesh or not mesh.get_path_name().startswith(bath['owned_destination']+'/')or c.get_num_materials()!=1 or a.get_actor_label()in saved_by_label:raise RuntimeError('Unique original owned fixture mesh/material required')
  saved_by_label[a.get_actor_label()]=(a,c);snapshots.append({'actor':a,'component':c,'mesh':mesh,'materials':list(c.get_materials()),'transform':c.get_world_transform(),'collision':capture(u,c),'cast_shadow':bool(c.get_editor_property('cast_shadow')),'tags':list(c.get_editor_property('component_tags'))})
 # Preparation writes only new owned inputs; no original mesh/body/material edits.
 attempt=uuid.uuid4().hex;inputs=project/'Saved/PrivateImportInputs'/('teal-style-'+attempt);inputs.mkdir(parents=True)
 bd,bb,bp=prepare_import(ORIGINAL,inputs/'baseline.glb')
 source_to_old={}
 for row in proof['fixture_corner_parity']['rows']:
  ni=row['source_node'];label='SUB01_AuthenticBath_'+str(ni).zfill(3)
  if label not in saved_by_label:raise RuntimeError('Exact original prepared source label missing '+label)
  a,c=saved_by_label[label]
  if not same_triangles(expected_triangles(bd,bb,ni),native_triangles(u,c),tolerance=.0001):raise RuntimeError('Current native source surface changed '+label)
  source_to_old[row['styled_node']]=(row,a,c)
 if len(source_to_old)!=90:raise RuntimeError('One-to-one saved actual fixture mapping required')
 result={'schema':'sub01.reference-teal-bathroom-native.v1','dry_run':dry_run,'source_fixture_sha256':digest(root/'bath-style-fixtures.glb'),'source_dressing_sha256':digest(root/'bath-style-dressing.glb'),'independent_proof_sha256':digest(proof_path),'unchanged_actual_fixture_actors':90,'uv_only_mesh_replacements':sorted(WOOD),'existing_glass_bindings_preserved':True,'current_doors_corridor_privacy_untouched':True,'native_visual_verified':False,'activity_ready':False}
 if dry_run:return result
 backup=project/'Saved/PrivateMapBackups'/('teal-style-'+attempt);backup.mkdir(parents=True);shutil.copy2(project/'Content/Sub01Home/ActualHome.umap',backup/'ActualHome.umap')
 for directory in ('__ExternalActors__','__ExternalObjects__'):
  src=project/'Content'/directory/'Sub01Home/ActualHome'
  if src.exists():shutil.copytree(src,backup/directory)
 destination='/Game/Sub01Home/ReferenceTealBath/Attempt_'+attempt;all_added=[];staged={};active=False;material_proofs={}
 try:
  for kind,prefix in [('fixtures','SUB01_TealFixture_'),('dressing','SUB01_TealDressing_')]:
   path=root/('bath-style-'+kind+'.glb');doc,blob,prepared=prepare_import(path,inputs/(kind+'.glb'),prefix);dest=destination+'/'+kind
   prior={a.get_path_name()for a in eas.get_all_level_actors()};manager=u.InterchangeManager.get_interchange_manager_scripted();params=u.ImportAssetParameters();params.set_editor_property('is_automated',True)
   if not manager.import_scene(dest,manager.create_source_data(str(inputs/(kind+'.glb'))),params):raise RuntimeError('Owned style scene import refused')
   manager.wait_until_all_tasks_done(False);added=[a for a in eas.get_all_level_actors()if a.get_path_name()not in prior];all_added.extend(added)
   for a in added:a.set_actor_hidden_in_game(True)
   parts={};opaque=[];bindings={};glass=[]
   for ni,node in enumerate(doc['nodes']):
    if'mesh'not in node:continue
    matches=[a for a in added if a.get_actor_label()==node['name']]
    if len(matches)!=1:raise RuntimeError('Unique exact prepared style part required')
    a=matches[0];cs=a.get_components_by_class(u.StaticMeshComponent)
    if len(cs)!=1:raise RuntimeError('Exactly one style mesh component per part required')
    c=cs[0];mesh=c.get_editor_property('static_mesh');owned_geometry(u,mesh,dest);c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
    if not same_triangles(expected_triangles(doc,blob,ni),native_triangles(u,c),tolerance=.0001):raise RuntimeError('Complete actual imported style geometry differs '+node['name'])
    ps=doc['meshes'][node['mesh']]['primitives']
    if len(ps)!=1 or c.get_num_materials()!=1:raise RuntimeError('Exact source material section required')
    material=doc['materials'][ps[0]['material']];is_glass=material.get('extensions',{}).get('KHR_materials_transmission',{}).get('transmissionFactor',0)>.5
    if is_glass:glass.append(c)
    else:
     actual=c.get_material(0)
     if not actual:raise RuntimeError('Actual imported opaque source material missing')
     old=bindings.setdefault(material['name'],actual.get_path_name())
     if old!=actual.get_path_name():raise RuntimeError('One explicit source material binding required')
     opaque.append(c)
    parts[ni]=(a,c,is_glass);c.set_editor_property('cast_shadow',kind!='dressing'or'Paint'not in str(node.get('name','')))
   dd=copy.deepcopy(doc);glass_names={m['name']for m in dd['materials']if m.get('extensions',{}).get('KHR_materials_transmission',{}).get('transmissionFactor',0)>.5};dd['materials']=[m for m in dd['materials']if m['name']not in glass_names];material_proofs[kind]=verify_materials(u,opaque,dd,dest,bindings)
   staged[kind]={'parts':parts,'doc':doc,'blob':blob,'added':added,'source_prepare':prepared}
  if len(staged['fixtures']['parts'])!=90 or len(staged['dressing']['parts'])!=proof['dressing_parts']:raise RuntimeError('Complete proved style parts required')
  # Verify UV-only incoming meshes at EXISTING actor/component transforms in
  # disposable hidden NoCollision actors BEFORE altering an existing component.
  for ni,(row,a,old)in source_to_old.items():
   if row['source_name']not in WOOD:continue
   incoming=staged['fixtures']['parts'][ni][1];tmp=eas.spawn_actor_from_class(u.StaticMeshActor,u.Vector(0,0,0));all_added.append(tmp);tc=tmp.get_component_by_class(u.StaticMeshComponent);tc.set_static_mesh(incoming.get_editor_property('static_mesh'));tc.set_collision_enabled(u.CollisionEnabled.NO_COLLISION);tc.set_world_transform(old.get_world_transform(),False,True);tmp.set_actor_hidden_in_game(True)
   if not same_triangles(native_triangles(u,old),native_triangles(u,tc),tolerance=.0001):raise RuntimeError('UV-only mesh would move physical fixture surface')
   if not eas.destroy_actor(tmp):raise RuntimeError('Temporary UV mesh witness cleanup failed')
   all_added.remove(tmp)
  if fingerprint(u,original)!=before:raise RuntimeError('Style staging changed protected actual home')
  if not u.EditorAssetLibrary.save_directory(destination,only_if_is_dirty=False,recursive=True):raise RuntimeError('Owned style asset save failed')
  active=True
  for ni,(row,a,old)in source_to_old.items():
   _,incoming,is_glass=staged['fixtures']['parts'][ni]
   if is_glass:continue # Exact existing clear-glass helper and mesh remain bound.
   state=next(s for s in snapshots if s['component']==old)
   if row['source_name']in WOOD:old.set_static_mesh(incoming.get_editor_property('static_mesh'));restore(u,old,state['collision'],force_response_copy=True)
   old.set_material(0,incoming.get_material(0))
   if not same_triangles(expected_triangles(bd,bb,row['source_node']),native_triangles(u,old),tolerance=.0001):raise RuntimeError('Activated fixture geometry changed')
   current_transform=fingerprint(u,[a])[a.get_path_name()]['components'][0]['transform'];old_transform=before[a.get_path_name()]['components'][0]['transform']
   if current_transform!=old_transform or signature(capture(u,old))!=signature(state['collision']):raise RuntimeError('Fixture physical transform/collision changed')
  # Decorative coatings/joinery remain NoCollision: no corridor/navigation/
  # privacy-state modification is authorized by the style transaction.
  for a,c,_ in staged['dressing']['parts'].values():a.set_actor_hidden_in_game(False);c.set_visibility(True)
  for a in staged['fixtures']['added']:
   if not eas.destroy_actor(a):raise RuntimeError('Temporary fixture import actor cleanup failed')
   all_added.remove(a)
  allowed={s['actor'].get_path_name()for s in snapshots};protected=[a for a in original if a.get_path_name()not in allowed]
  if fingerprint(u,protected)!={k:v for k,v in before.items()if k not in allowed}:raise RuntimeError('Style changed other actual house actors')
  for name,raw in receipts.items():
   if(audit/name).read_bytes()!=raw:raise RuntimeError('Saved original bath/doors/corridor receipt changed')
  if not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Actual private style map save failed')
  result.update(saved=True,source_preparation={k:v['source_prepare']for k,v in staged.items()},owned_destination=destination,materials=material_proofs,map_backup=str(backup),dressing_parts=[{'actor':a.get_path_name(),'component':c.get_path_name()}for a,c,_ in staged['dressing']['parts'].values()],original_fixture_actor_paths=sorted(allowed),protected_originals_unchanged=True)
  (audit/'reference-teal-bathroom-native.json').write_text(json.dumps(result,indent=2)+'\n');return result
 except Exception as error:
  for s in snapshots:
   c=s['component'];c.set_static_mesh(s['mesh'])
   for index,material in enumerate(s['materials']):c.set_material(index,material)
   c.set_editor_property('cast_shadow',s['cast_shadow']);restore(u,c,s['collision'],force_response_copy=True)
  cleanup=detach_added(u,eas,before);restored=fingerprint(u,original)==before
  (audit/'reference-teal-bathroom-refusal.json').write_text(json.dumps({'error':str(error),'rollback_verified':restored,'owned_destination':destination,'backup':str(backup),'cleanup':cleanup},indent=2)+'\n')
  if not restored:raise RuntimeError('Style rollback failed; preserve backup and stop')from error
  if active and not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Style rollback save failed')from error
  raise
