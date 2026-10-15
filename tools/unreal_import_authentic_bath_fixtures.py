"""Atomic warm-Editor bath fixture replacement, with exact shared-face remainders.

Sole native integrator executes. No door, room/wall/floor/camera or privacy writes.
Existing CC0 WC, old vanity and shower are retired only after full actual surface
and material verification. Original actors/assets stay present for exact rollback.
"""
import copy,hashlib,json,shutil,time,uuid,struct
from pathlib import Path
from home_asset_audit import read_gltf
from prepare_frame_backing_remainder import SOURCE_SHA
from prepare_real_wc_bundle import node_geometry
from structural_rail_source_patch import world_matrices
from unreal_import_real_wc import expected_triangles,owned_geometry
from unreal_remove_frame_backings import native_triangles,same_triangles
from unreal_import_real_linea140 import verify_materials
from unreal_import_reference_dressing import fingerprint
from unreal_component_collision_state import capture,restore
from unreal_owned_import_cleanup import detach_added
from unreal_import_real_home_windows import clear_glass
ROOT=Path('/workspace/sub01-home-private/authentic-bath-doors-fit-r3/output')
SHA='b8d190b7d7cf274126b4be35cf2ccf447b25c742da037cc222c43fe57f437a92'
REMAINDERS={167:('fc5d6a36471ff6192628149685a21f4478d53a0ab75dc4c6bdc9cbfaf6e2296d',192,68)}

def source_proof(root=ROOT):
 report=json.loads((root/'source-report.json').read_text());proof=json.loads((root/'remainder-proof.json').read_text());source=root/'bath-fixtures.glb'
 if report.get('fixture_sha256')!=SHA or hashlib.sha256(source.read_bytes()).hexdigest()!=SHA or len(report.get('fixture_parts',[]))!=90:raise RuntimeError('Frozen complete90part actual bathroom source required')
 if proof.get('home_sha256')!=SOURCE_SHA or len(proof.get('parts',[]))!=2:raise RuntimeError('Actual shared-source corner preservation proof required')
 for ni,(sha,count,material)in REMAINDERS.items():
  rows=[r for r in proof['parts']if r['source_node']==ni]
  if len(rows)!=1 or rows[0]['sha256']!=sha or rows[0]['retained_triangles']!=count or rows[0]['material']!=material or rows[0]['retained_corner_bytes_exact']is not True or hashlib.sha256((root/f'remainder-{ni}.glb').read_bytes()).hexdigest()!=sha:raise RuntimeError('Exact unrelated shared geometry bytes required')
 bvh=json.loads((root/'actual-architecture-bvh.json').read_text())
 if bvh.get('fixture_sha256')!=SHA or bvh.get('target_corridor_sha256')!='5ffac2406e668a327427e60bc75e3ee3ecf13a89381d0312b821277386cb9c91' or bvh.get('fixture_meshes')!=90 or bvh.get('protected_nodes')!=[117,158] or bvh.get('unresolved_positive_crossings')!=0 or bvh.get('surface_contact_epsilon_cm')!=.001:raise RuntimeError('Actual exported fixture-versus-target-architecture BVH proof required')
 return report

def prepare_import(source,target,prefix='SUB01_AuthenticBath_'):
 """Unique legal identifiers and exactzeroarea removal; all physical corner bytes exact."""
 from prepare_frame_backing_remainder import elements,read
 from prepare_real_wc_bundle import glb
 doc,original=read_gltf(Path(source));out=copy.deepcopy(doc);blob=bytearray(original);removed={};names={}
 for ni,n in enumerate(out['nodes']):
  if 'mesh'not in n:continue
  legal=prefix+str(ni).zfill(3);names[n['name']]=legal;n['name']=legal;out['meshes'][n['mesh']]['name']=legal
  for pi,p in enumerate(out['meshes'][n['mesh']]['primitives']):
   pos,pfmt=elements(doc,original,p['attributes']['POSITION']);pos=[struct.unpack(pfmt,v)for v in pos];ids,ff=elements(doc,original,p['indices']);ids=[struct.unpack(ff,v)[0]for v in ids];keep=[];zero=[]
   for ti in range(0,len(ids),3):
    a,b,c=(pos[j]for j in ids[ti:ti+3]);x=[b[k]-a[k]for k in range(3)];y=[c[k]-a[k]for k in range(3)];cross=(x[1]*y[2]-x[2]*y[1],x[2]*y[0]-x[0]*y[2],x[0]*y[1]-x[1]*y[0])
    if cross==(0,0,0):zero.append(ti//3)
    else:keep.extend(ids[ti:ti+3])
   if zero:
    raw=struct.pack('<'+'I'*len(keep),*keep);blob.extend(b'\0'*(-len(blob)%4));offset=len(blob);blob.extend(raw);vi=len(out['bufferViews']);out['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':len(raw),'target':34963});ai=len(out['accessors']);out['accessors'].append({'bufferView':vi,'componentType':5125,'count':len(keep),'type':'SCALAR'});p['indices']=ai;removed[legal+':'+str(pi)]=zero
 out['buffers'][0]['byteLength']=len(blob);encoded=glb(out,blob);actual,ab=read(encoded)
 if bytes(ab[:len(original)])!=bytes(original):raise RuntimeError('Original fixture attribute/material/image bytes changed')
 for ni,n in enumerate(out['nodes']):
  if 'mesh'not in n:continue
  for pi,p in enumerate(out['meshes'][n['mesh']]['primitives']):
   old=doc['meshes'][doc['nodes'][ni]['mesh']]['primitives'][pi];iv,ff=elements(actual,ab,p['indices']);ii=[struct.unpack(ff,v)[0]for v in iv];ov,ff=elements(doc,original,old['indices']);oi=[struct.unpack(ff,v)[0]for v in ov];zero=set(removed.get(n['name']+':'+str(pi),[]));wanted=[j for ti in range(len(oi)//3)if ti not in zero for j in oi[ti*3:ti*3+3]]
   for role,ai in old['attributes'].items():
    a,_=elements(doc,original,ai);b,_=elements(actual,ab,p['attributes'][role])
    if [a[i]for i in wanted]!=[b[i]for i in ii]:raise RuntimeError('Physical fixture triangle corner changed')
 Path(target).parent.mkdir(parents=True,exist_ok=True);Path(target).write_bytes(encoded)
 return actual,ab,{'names':names,'exact_zero_area_faces_removed':removed,'all_positive_triangle_corner_bytes_exact':True,'original_binary_prefix_exact':True,'prepared_sha256':hashlib.sha256(encoded).hexdigest()}

def audit_original_167_source(u,eas,c,expected,project,allow_clone):
 """Rebuild an independent fullsource copy; never mutate the original Nanite asset."""
 mesh=c.get_editor_property('static_mesh');want='/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Mesh_126.Mesh_126'
 if not mesh or mesh.get_path_name()!=want:raise RuntimeError('Exact frozen original167 mesh126 binding required')
 sub=u.get_editor_subsystem(u.StaticMeshEditorSubsystem);keys=('enabled','fallback_target','fallback_relative_error','fallback_percent_triangles','keep_percent_triangles','trim_relative_error');settings={k:str(sub.get_nanite_settings(mesh).get_editor_property(k))for k in keys};actual=native_triangles(u,c)
 def bounds(tris):
  pts=[p for t in tris for p in t];return [[f(p[k]for p in pts)for k in range(3)]for f in(min,max)]if pts else None
 diagnostic={'schema':'sub01.original-bath167-source-diagnostic.v1','component':c.get_path_name(),'mesh':want,'source_triangles':len(expected),'native_render_fallback_triangles':len(actual),'source_bounds_cm':bounds(expected),'native_fallback_bounds_cm':bounds(actual),'original_nanite':settings,'original_changed':False}
 (project/'private-audit/authentic-bath-original167-diagnostic.json').write_text(json.dumps(diagnostic,indent=2)+'\n')
 if not sub.get_nanite_settings(mesh).get_editor_property('enabled')or not allow_clone:raise RuntimeError('Original167 fallback differs; execute requires bounded owned fullsource clone audit')
 dest='/Game/Sub01Home/AuthenticBath/Original167Audit/Attempt_'+uuid.uuid4().hex;clone=u.EditorAssetLibrary.duplicate_asset(want.split('.',1)[0],dest+'/Mesh_126')
 if not clone:raise RuntimeError('Original167 ownedclone creation failed')
 actor=None
 try:
  owned_geometry(u,clone,dest)
  if u.Sub01HomeHandsInstance.finish_pending_static_compilation()!=0:raise RuntimeError('Original167 ownedclone stillcompiling')
  actor=eas.spawn_actor_from_class(u.StaticMeshActor,u.Vector(0,0,0));actor.set_actor_label('SUB01_TemporaryOriginalBath167Audit');actor.set_actor_hidden_in_game(True);cc=actor.get_component_by_class(u.StaticMeshComponent);cc.set_static_mesh(clone);cc.set_collision_enabled(u.CollisionEnabled.NO_COLLISION);cc.set_world_transform(c.get_world_transform(),False,True);full=native_triangles(u,cc)
  if not same_triangles(expected,full,tolerance=.0001):raise RuntimeError('Original167 fullsource ownedclone differs: source='+str(len(expected))+' clone='+str(len(full)))
  diagnostic.update(method='independent actual complete-source clone',clone_mesh=clone.get_path_name(),full_source_clone_triangles=len(full),all_source_world_triangles_exact=True,tolerance_cm=.0001)
  return diagnostic
 finally:
  if actor and not eas.destroy_actor(actor):raise RuntimeError('Temporary original167 audit actorcleanup failed')
  if settings!={k:str(sub.get_nanite_settings(mesh).get_editor_property(k))for k in keys}or c.get_editor_property('static_mesh')!=mesh:raise RuntimeError('Original167 binding/settingschanged duringcloneaudit')

def run(dry_run=True):
 import unreal as u
 report=source_proof();project=Path(u.Paths.project_dir());audit=project/'private-audit';home=project/'SourceAssets/full-home.glb'
 if hashlib.sha256(home.read_bytes()).hexdigest()!=SOURCE_SHA:raise RuntimeError('Immutable955 actual home required')
 corridor=json.loads((audit/'bathroom-corridor-native-import.json').read_text())
 if corridor.get('export_sha256')!='5ffac2406e668a327427e60bc75e3ee3ecf13a89381d0312b821277386cb9c91' or not corridor.get('saved')or not corridor.get('originals_preserved'):raise RuntimeError('Exact actual saved resizedroom required before bathroom fitting')
 world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
 if not world or world.get_path_name()!='/Game/Sub01Home/ActualHome.ActualHome':raise RuntimeError('Actual loaded home required')
 if(audit/'authentic-bath-fixtures-native.json').exists():raise RuntimeError('Existing bath receipt must be inspected; no duplicate import')
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);original=list(eas.get_all_level_actors());before=fingerprint(u,original);by_path={a.get_path_name():a for a in original};hd,hb=read_gltf(home);old=[];originals={};original_source_proofs=[]
 def take(a,expected=None,mesh_path=None):
  cs=a.get_components_by_class(u.StaticMeshComponent)
  if len(cs)!=1:raise RuntimeError('Unique actual retiredfixture component required '+a.get_path_name())
  c=cs[0];m=c.get_editor_property('static_mesh')
  if not m or(mesh_path and m.get_path_name()!=mesh_path)or bool(a.get_editor_property('hidden'))or not c.get_editor_property('visible'):raise RuntimeError('Exact live retiredfixture binding required '+a.get_path_name())
  if expected is not None and not same_triangles(expected,native_triangles(u,c),tolerance=.0001):
   if a.get_name()!='full-home_node_167':raise RuntimeError('Retiredfixture full native surface differs '+a.get_path_name())
   original_source_proofs.append(audit_original_167_source(u,eas,c,expected,project,not dry_run))
  old.append((a,c,bool(a.get_editor_property('hidden')),bool(c.get_editor_property('visible')),a.is_temporarily_hidden_in_editor(),capture(u,c)));return c
 for ni in (119,121,122,167):
  found=[a for a in original if a.get_name()==f'full-home_node_{ni}']
  if len(found)!=1:raise RuntimeError('Exact existing bathroom source node required '+str(ni))
  c=take(found[0],expected_triangles(hd,hb,ni));originals[ni]=c
 # Rails and office already retired the fullchrome163; its sole live160face
 # union is EXACTLY the old bathroom tap+shower pipe. Retire that union only,
 # never restore the1680 unrelatedfaces (approved realstairs replaced them).
 found=[a for a in original if a.get_name()=='full-home_node_163']
 if len(found)!=1:raise RuntimeError('Exact hidden originalchrome163 required')
 cs=found[0].get_components_by_class(u.StaticMeshComponent)
 if len(cs)!=1 or not bool(found[0].get_editor_property('hidden'))or cs[0].get_collision_enabled()!=u.CollisionEnabled.NO_COLLISION or cs[0].get_editor_property('static_mesh').get_path_name()!='/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Mesh_122.Mesh_122':raise RuntimeError('Fullchrome163 must remain alreadyhidden/NoCollision')
 union=json.loads((audit/'native-structural-lamp-union.json').read_text())
 if union.get('union_sha256')!='920edd7a573eaddf186929f026365e3d20fb7db0bcfaa215bcd3f26d3e41e74e' or union.get('source_sha256')!=SOURCE_SHA or not union.get('roundtrip',{}).get('ok'):raise RuntimeError('Exact saved160face bathroom-only chrome union required')
 path=union['new_union_component'];matches=[a for a in original if any(c.get_path_name()==path for c in a.get_components_by_class(u.StaticMeshComponent))]
 if len(matches)!=1:raise RuntimeError('Current bathroom-only chrome union not unique')
 c=take(matches[0],expected_triangles(hd,hb,163)[1640:1800])
 if not c.get_editor_property('static_mesh').get_path_name().startswith('/Game/Sub01Home/StructuralLampUnionMeshOnly/V_920edd7a573e/')or c.get_material(0)!=cs[0].get_material(0):raise RuntimeError('Exact160face union ownedmesh/material differs')
 # Prior picture retirement left only bathroom mirrorframe+cabinet. Do not
 # resurrect the first600 picture backings which were intentionally removed.
 frames=json.loads((audit/'frame-backings-retired.json').read_text());path=frames['remainder_actor'];a=by_path.get(path)
 if not a or frames['preserved_native_triangles']!=600 or frames['removed_only_source_triangles']!=list(range(600)):raise RuntimeError('Exact current600face bathroom-only frame remainder required')
 take(a,expected_triangles(hd,hb,165)[600:1200],frames['remainder_mesh'])
 wc=json.loads((audit/'real-compact-wc-import.json').read_text())
 if wc['source_proof']['output_sha256']!='ec3df0b92b0734f2705318e7c1c57a58164ef08926c0bde1240af4e4137067c3' or len(wc['authentic_actors'])!=10:raise RuntimeError('Exact previous realWC receipt required')
 for path in wc['authentic_actors']:
  a=by_path.get(path)
  if not a:raise RuntimeError('Existing realWC part missing')
  c=take(a)
  if not c.get_editor_property('static_mesh').get_path_name().startswith(wc['owned_destination']+'/'):raise RuntimeError('Existing realWC owned namespace differs')
 row=next(r for r in wc['remainders']if r['source_node']==166);a=by_path.get(row['actor'])
 if not a:raise RuntimeError('Exact current vanitytop remainder missing')
 take(a,expected_triangles(hd,hb,166)[:300])
 if len(old)!=17:raise RuntimeError('Exact17 retiredfixture owners required')
 result={'schema':'sub01.authentic-bath-fixtures-native.v1','source_sha256':SHA,'dry_run':dry_run,'native_visual_verified':False,'bathroom_activity_ready':False,'door_or_privacy_or_room_changed':False,'original_source_proofs':original_source_proofs}
 if dry_run:return result
 backup=project/'Saved/PrivateMapBackups'/('authentic-bath-'+str(time.time_ns()));backup.mkdir(parents=True);shutil.copy2(project/'Content/Sub01Home/ActualHome.umap',backup/'ActualHome.umap')
 for name in ('__ExternalActors__','__ExternalObjects__'):
  folder=project/'Content'/name/'Sub01Home/ActualHome'
  if folder.exists():shutil.copytree(folder,backup/name)
 dest='/Game/Sub01Home/AuthenticBath/V_'+SHA[:12]+'/Attempt_'+uuid.uuid4().hex;added=[];parts=[];active=False
 try:
  prepared=project/'Saved/PrivateImportInputs'/('authentic-bath-'+uuid.uuid4().hex+'.glb');doc,blob,prepared_proof=prepare_import(ROOT/'bath-fixtures.glb',prepared)
  manager=u.InterchangeManager.get_interchange_manager_scripted();params=u.ImportAssetParameters();params.set_editor_property('is_automated',True)
  if not manager.import_scene(dest,manager.create_source_data(str(prepared)),params):raise RuntimeError('Authentic bathroom scene import refused')
  manager.wait_until_all_tasks_done(False);added=[a for a in eas.get_all_level_actors()if a.get_path_name()not in before]
  for a in added:a.set_actor_hidden_in_game(True)
  glass=[];opaque=[];bindings={}
  for ni,n in enumerate(doc['nodes']):
   if'mesh'not in n:continue
   matches=[a for a in added if a.get_actor_label()==n['name']]
   if len(matches)!=1:raise RuntimeError('Exact bathroom part not unique '+n['name'])
   a=matches[0];cs=a.get_components_by_class(u.StaticMeshComponent)
   if len(cs)!=1:raise RuntimeError('One component per genuine bathroom part required')
   c=cs[0];owned_geometry(u,c.get_editor_property('static_mesh'),dest)
   if not same_triangles(expected_triangles(doc,blob,ni),native_triangles(u,c)):raise RuntimeError('Full bath actual worldgeometry differs '+n['name'])
   ps=doc['meshes'][n['mesh']]['primitives']
   if len(ps)!=1 or c.get_num_materials()!=1:raise RuntimeError('Exact source material section perpart required')
   material=doc['materials'][ps[0]['material']];is_glass=material.get('extensions',{}).get('KHR_materials_transmission',{}).get('transmissionFactor',0)>.5
   
   if not is_glass:
    path=c.get_material(0).get_path_name();prior=bindings.setdefault(material['name'],path)
    if prior!=path:raise RuntimeError('Actual source material split unexpectedly')
   (glass if is_glass else opaque).append(c);c.set_collision_profile_name('BlockAll');c.set_collision_enabled(u.CollisionEnabled.QUERY_AND_PHYSICS);parts.append((a,c))
  if len(parts)!=90 or not glass:raise RuntimeError('Complete90bathparts plus actual clearshower glazing required')
  od=copy.deepcopy(doc);glass_names={doc['materials'][p['material']]['name']for m in doc['meshes']for p in m['primitives']if doc['materials'][p['material']].get('extensions',{}).get('KHR_materials_transmission',{}).get('transmissionFactor',0)>.5};od['materials']=[m for m in od['materials']if m['name']not in glass_names];material_proof=verify_materials(u,opaque,od,dest,bindings);gm=clear_glass(u,dest)
  for c in glass:c.set_material(0,gm);c.set_editor_property('cast_shadow',False)
  remainders=[]
  for ni,(sha,count,material)in REMAINDERS.items():
   rd=dest+'/Preserved_'+str(ni);task=u.AssetImportTask();task.filename=str(ROOT/f'remainder-{ni}.glb');task.destination_path=rd;task.automated=True;task.replace_existing=False;task.save=False;u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task]);meshes=[u.EditorAssetLibrary.load_asset(p)for p in u.EditorAssetLibrary.list_assets(rd,recursive=True,include_folder=False)];meshes=[m for m in meshes if isinstance(m,u.StaticMesh)]
   if len(meshes)!=1:raise RuntimeError('One preserved sharedbath mesh required')
   mesh=meshes[0];owned_geometry(u,mesh,rd);a=eas.spawn_actor_from_class(u.StaticMeshActor,u.Vector(0,0,0));added.append(a);c=a.get_components_by_class(u.StaticMeshComponent)[0];c.set_static_mesh(mesh);c.set_material(0,originals[ni].get_material(0));a.set_actor_hidden_in_game(True);a.set_actor_label('SUB01_BathPreserved_'+str(ni));restore(u,c,capture(u,originals[ni]),force_response_copy=True)
   dd,bb=read_gltf(ROOT/f'remainder-{ni}.glb')
   if len(native_triangles(u,c))!=count or not same_triangles(expected_triangles(dd,bb,0),native_triangles(u,c)):raise RuntimeError('Unrelated sharedhouse faces not preserved '+str(ni))
   remainders.append((a,c))
  if fingerprint(u,original)!=before:raise RuntimeError('Staging bathroom altered existinghome')
  if not u.EditorAssetLibrary.save_directory(dest,only_if_is_dirty=False,recursive=True):raise RuntimeError('Actual bathroom asset save refused')
  active=True
  for a,c,*_ in old:a.set_actor_hidden_in_game(True);a.set_is_temporarily_hidden_in_editor(True);c.set_visibility(False);c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
  for a,c in parts+remainders:a.set_actor_hidden_in_game(False);c.set_visibility(True)
  excluded={a.get_path_name()for a,c,*_ in old};retained=[a for a in original if a.get_path_name()not in excluded]
  if fingerprint(u,retained)!={k:v for k,v in before.items()if k not in excluded}:raise RuntimeError('Bathroom activation changed unrelated actualhome')
  if not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Actual bathroom map save refused')
  result.update(saved=True,parts=[{'actor':a.get_path_name(),'component':c.get_path_name()}for a,c in parts],retired=[a.get_path_name()for a,c,*_ in old],remainders=[a.get_path_name()for a,c in remainders],materials=material_proof,glass_material=gm.get_path_name(),map_backup=str(backup),owned_destination=dest,protected_originals_unchanged=True,prepared_source_proof=prepared_proof)
  (audit/'authentic-bath-fixtures-native.json').write_text(json.dumps(result,indent=2)+'\n');return result
 except Exception as error:
  for a,c,h,v,t,st in old:a.set_actor_hidden_in_game(h);a.set_is_temporarily_hidden_in_editor(t);c.set_visibility(v);restore(u,c,st)
  cleanup=detach_added(u,eas,before);equal=fingerprint(u,original)==before;(audit/'authentic-bath-fixtures-refusal.json').write_text(json.dumps({'error':str(error),'rollback_verified':equal,'owned_destination':dest,'backup':str(backup),'cleanup':cleanup},indent=2)+'\n')
  if not equal:raise RuntimeError('Actual bathroom rollback failed; retain backup and stop')from error
  if active and not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Bathroom rollback save refused')from error
  raise
