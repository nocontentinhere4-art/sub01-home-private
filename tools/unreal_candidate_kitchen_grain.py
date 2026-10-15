"""Source-exact owned materials on existing152 kitchen parts; no mesh replacement."""
import copy,hashlib,json,shutil,time
from pathlib import Path
from uuid import uuid4
ROOT=Path('/workspace/sub01-home-private/reference-kitchen-grain-r3/output')
VARIANT_SHA='961900d8c57d1c143b44417878778e5b74cc4a91f166c167b0bf444314e1b2c6'
CARRIER_SHA='dae5de70b8c53f3659facb208c0ef58dedd6c802fee540c9d49434c55b536479'
RECEIPT_SHA='6b12c76f4c3df583efd664eadaf64191a83d2a82e336b26117e50c30f7fb4c2f'

def verify_sampling(u,material,source):
 mel=u.MaterialEditingLibrary;rows=[];pbr=source.get('pbrMetallicRoughness',{})
 for obj,key,param in [(pbr,'baseColorTexture','BaseColorTexture'),(pbr,'metallicRoughnessTexture','MetallicRoughnessTexture'),(source,'normalTexture','NormalTexture')]:
  if key not in obj:continue
  info=obj[key];transform=info.get('extensions',{}).get('KHR_texture_transform',{});expected=[*transform.get('offset',[0,0]),*transform.get('scale',[1,1])];value=mel.get_material_instance_vector_parameter_value(material,param+'_OffsetScale');actual=[value.r,value.g,value.b,value.a]
  if any(abs(a-b)>1e-5 for a,b in zip(actual,expected)):raise RuntimeError('Actual owned shader UV offset/scale differs '+param+' '+str((actual,expected)))
  rotation=float(mel.get_material_instance_scalar_parameter_value(material,param+'_Rotation'));texcoord=float(mel.get_material_instance_scalar_parameter_value(material,param+'_TexCoord'))
  if abs(rotation-transform.get('rotation',0))>1e-5 or abs(texcoord-transform.get('texCoord',info.get('texCoord',0)))>1e-5:raise RuntimeError('Actual owned shader UV rotation/coordinate differs')
  rows.append({'parameter':param,'actual_offset_scale':actual,'rotation':rotation,'texcoord':texcoord})
 return rows

def run(dry_run=True):
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard
 from home_asset_audit import read_gltf
 from unreal_import_reference_entry import snapshot
 from unreal_import_real_wc import expected_triangles,owned_geometry
 from unreal_remove_frame_backings import native_triangles,same_triangles
 from unreal_import_reference_wall_console import positive_triangles
 from unreal_import_real_bathroom_pendant import verify_owned_material
 from unreal_owned_import_cleanup import detach_added
 project=Path(u.Paths.project_dir()).resolve();assert active_candidate_guard(project)
 carrier=ROOT/'kitchen-grain-real-source-carrier.glb';variant=ROOT/'kitchen-grain-152.glb'
 if hashlib.sha256(variant.read_bytes()).hexdigest()!=VARIANT_SHA or hashlib.sha256(carrier.read_bytes()).hexdigest()!=CARRIER_SHA:raise RuntimeError('Frozen kitchen R3 source required')
 vd,vb=read_gltf(variant);cd,cb=read_gltf(carrier)
 if len(vd['nodes'])!=152 or len(cd['nodes'])!=3 or len(cd['materials'])!=3:raise RuntimeError('Exact152 installed roles and3 genuine carrier parts required')
 original=Path('/workspace/sub01-home-private/kitchen-lowerfit-source-20261015/output/native-kitchen-import.json');rb=original.read_bytes()
 if hashlib.sha256(rb).hexdigest()!=RECEIPT_SHA:raise RuntimeError('Exact actual saved R7 receipt required')
 receipt=json.loads(rb);parts=receipt['parts'];eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);components={c.get_path_name():(a,c)for a in actors for c in a.get_components_by_class(u.StaticMeshComponent)};nodes={n['name']:n for n in vd['nodes']};installed=[]
 if len(parts)!=152 or len(receipt['hinges'])!=8 or len(nodes)!=152:raise RuntimeError('Exact R7 part/hinge ownership required')
 for p in parts:
  a,c=components.get(p['component'],(None,None));n=nodes.get(p['part'])
  if c is None or n is None or c.get_editor_property('static_mesh').get_path_name()!=p['mesh']or c.get_num_materials()!=1:raise RuntimeError('Exact current152 mesh/component binding differs')
  prim=vd['meshes'][n['mesh']]['primitives']
  if len(prim)!=1:raise RuntimeError('One material source per owned component required')
  installed.append((a,c,prim[0]['material'],c.get_material(0)))
 result={'schema':'sub01.candidate-kitchen-grain-native.v1','dry_run':dry_run,'source_sha256':VARIANT_SHA,'carrier_sha256':CARRIER_SHA,'existing152_geometry_hinges_unchanged':True,'native_visual_accepted':False,'runtime_hinges_retested':False,'live_promotion':False}
 if dry_run:return result
 dest='/Game/Sub01Home/KitchenGrain/V_'+VARIANT_SHA[:12]+'/A_'+uuid4().hex;backup=project/'Saved/PrivateMapBackups'/('kitchen-grain-'+str(time.time_ns()));backup.mkdir(parents=True);shutil.copy2(project/'Content/Sub01Home/ActualHome.umap',backup/'ActualHome.umap');save_attempted=False;materials={};proof=[]
 try:
  manager=u.InterchangeManager.get_interchange_manager_scripted();params=u.ImportAssetParameters();params.set_editor_property('is_automated',True)
  if not manager.import_scene(dest,manager.create_source_data(str(carrier)),params):raise RuntimeError('Genuine kitchen carrier import refused')
  manager.wait_until_all_tasks_done(False);newactors=[a for a in eas.get_all_level_actors()if a.get_path_name()not in before];matches={}
  for a in newactors:
   a.set_actor_hidden_in_game(True)
   for c in a.get_components_by_class(u.StaticMeshComponent):
    mesh=c.get_editor_property('static_mesh')
    if not mesh or not mesh.get_path_name().startswith(dest+'/'):continue
    c.set_collision_profile_name('NoCollision');c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
    for key in {a.get_actor_label(),mesh.get_name()}:
     if key in {'KG30','KG31','KG32'}:matches.setdefault(key,{})[c.get_path_name()]=(a,c)
  for ni,n in enumerate(cd['nodes']):
   found=list(matches.get(n['name'],{}).values())
   if len(found)!=1:raise RuntimeError('Unique full source kitchen carrier part required')
   a,c=found[0];owned_geometry(u,c.get_editor_property('static_mesh'),dest);wanted,zero=positive_triangles(expected_triangles(cd,cb,ni))
   if not same_triangles(wanted,native_triangles(u,c),tolerance=.0001):raise RuntimeError('Every positive carrier source triangle must match actual')
   mi=cd['meshes'][n['mesh']]['primitives'][0]['material'];source=cd['materials'][mi];pbr=verify_owned_material(u,c,source,dest,source_primitive_verified=True);sampling=verify_sampling(u,c.get_material(0),source);materials[mi]=c.get_material(0);proof.append({'source':source['name'],'pbr':pbr,'sampling':sampling,'source_positive_triangles':len(wanted),'exact_zero_indices':zero})
  if set(materials)!={0,1,2}or snapshot(u,actors)!=before:raise RuntimeError('Three exact materials and unchanged originals required')
  expected=copy.deepcopy(before)
  for a,c,mi,old in installed:
   c.set_material(0,materials[mi]);r=next(x for x in expected[a.get_path_name()]['components']if x['path']==c.get_path_name());r['materials']=[materials[mi].get_path_name()]
  detach_added(u,eas,before)
  if snapshot(u,list(eas.get_all_level_actors()))!=expected:raise RuntimeError('Only152 material bindings may change; all source meshes/TRS/tags/hinges/collisions and actors must stay exact')
  if not u.EditorAssetLibrary.save_directory(dest,only_if_is_dirty=False,recursive=True):raise RuntimeError('Owned grain materials save refused')
  assert active_candidate_guard(project);result.update(materials=proof,backup=str(backup),owned_destination=dest,temporary_carriers_destroyed=True,protected_other_actors_exact=True);p=project/'private-audit/reference-kitchen-grain-native.pending.json';p.write_text(json.dumps(result,indent=2));save_attempted=True
  if not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Candidate kitchen materials map save refused')
  result['saved']=True;p.write_text(json.dumps(result,indent=2));p.replace(project/'private-audit/reference-kitchen-grain-native.json');return result
 except Exception:
  for a,c,mi,old in installed:c.set_material(0,old)
  detach_added(u,eas,before)
  if snapshot(u,list(eas.get_all_level_actors()))!=before:raise RuntimeError('Kitchen material rollback must restore exact complete candidate world')
  if save_attempted and not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Kitchen rollback map save refused')
  raise
