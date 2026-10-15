"""Actual private source-cloth import, refusing opaque or unlit substitutions.

Sole Editor operator. Two single cloth surfaces and one rail group; no collision,
input, FOV, settings, old geometry or door-runtime changes. Source/render proof
never substitutes for viewing actual native light filtering and shadows.
"""
import hashlib,json,time,shutil
from pathlib import Path
from uuid import uuid4
ROOT=Path('/workspace/sub01-home-private/reference-curtain-source-r1/output')
SHA='b531ac1eaa30995be9c133c8aea18e59a795c84157d47f699a74740702ff1d2c'
DOOR_SHA='5b8a2bb8b4bb8fe19af1d0c086fb78f3e7f9dff9e06170a06642a8f3d1761a0c'
NAMES={'SCLeft','SCRight','SCHardware'}


def validate_source_proof(proof,names):
 if (proof.get('schema')!='sub01.reference-sheer-actual-source-bvh.v1' or proof.get('source_sha256')!=SHA
     or proof.get('ok')is not True or proof.get('epsilon_cm')!=0 or proof.get('unresolved')!=[]
     or proof.get('full91cm_door_sweep_separated')is not True or proof.get('current_door_source_sha256')!=DOOR_SHA
     or proof.get('retired_old_balcony_nodes_excluded')!=list(range(41,49))
     or names.get('prepared_sha256')!=SHA or names.get('geometry_PBR_image_binary_unchanged')is not True
     or set(names.get('node_names',[]))!=NAMES or names.get('material_names')!=['SCM00','SCM01']):
  raise RuntimeError('Actual complete zero-intersection source/door and names-only cloth proof required')


def lit_translucent_material(u,material):
 """Read effective owned parent/instance state; no material or source mutation."""
 current=material;seen=set();blend=two_sided=shading=None;chain=[]
 while current:
  path=current.get_path_name()
  if path in seen or len(seen)>=16:raise RuntimeError('Material parent cycle or excessive chain')
  seen.add(path);chain.append(path)
  if isinstance(current,u.MaterialInstance):
   overrides=current.get_editor_property('base_property_overrides')
   if blend is None and overrides.get_editor_property('override_blend_mode'):blend=overrides.get_editor_property('blend_mode')
   if two_sided is None and overrides.get_editor_property('override_two_sided'):two_sided=overrides.get_editor_property('two_sided')
   if shading is None and overrides.get_editor_property('override_shading_model'):shading=overrides.get_editor_property('shading_model')
   current=current.get_editor_property('parent');continue
  if not isinstance(current,u.Material):raise RuntimeError('Actual source cloth has no concrete native material root')
  if blend is None:blend=current.get_editor_property('blend_mode')
  if two_sided is None:two_sided=current.get_editor_property('two_sided')
  if shading is None:shading=current.get_editor_property('shading_model')
  break
 lit_models={getattr(u.MaterialShadingModel,name)for name in('MSM_DEFAULT_LIT','MSM_THIN_TRANSLUCENT','MSM_CLOTH','MSM_SUBSURFACE','MSM_TWO_SIDED_FOLIAGE')if hasattr(u.MaterialShadingModel,name)}
 if blend!=u.BlendMode.BLEND_TRANSLUCENT or not two_sided or shading not in lit_models:
  raise RuntimeError('Cloth requires an actual lit two-sided translucent shader; no opaque/unlit fallback')
 mel=u.MaterialEditingLibrary;parameters={str(n):n for n in mel.get_scalar_parameter_names(material)}
 transmission=parameters.get('TransmissionFactor')
 value=float(mel.get_material_instance_scalar_parameter_value(material,transmission))if transmission is not None else None
 if value is not None and abs(value-.12)>1e-5:raise RuntimeError('Actual source thin transmission factor differs')
 return {'material':material.get_path_name(),'parent_chain':chain,'effective_blend':str(blend),'effective_shading':str(shading),'two_sided':bool(two_sided),'transmission_parameter_available':transmission is not None,'actual_transmission_factor':value,'native_lit_translucent_shader_verified':True}


def run(dry_run=True):
 import unreal as u
 from home_asset_audit import read_gltf
 from unreal_import_reference_entry import guard,snapshot,assigned_material_binding
 from unreal_import_real_wc import owned_geometry,expected_triangles
 from unreal_remove_frame_backings import native_triangles,same_triangles
 from unreal_import_real_linea140 import verify_materials
 from unreal_owned_import_cleanup import detach_added
 guard();source=ROOT/'reference-sheer-native.glb'
 if hashlib.sha256(source.read_bytes()).hexdigest()!=SHA:raise RuntimeError('Frozen actual cloth source required')
 validate_source_proof(json.loads((ROOT/'source-bvh-proof.json').read_text()),json.loads((ROOT/'native-name-proof.json').read_text()))
 doc,blob=read_gltf(source)
 if {n.get('name')for n in doc['nodes']}!=NAMES or len(doc['materials'])!=2:raise RuntimeError('Exact three-part/two-material cloth source required')
 cloth=next(m for m in doc['materials']if m['name']=='SCM00')
 if cloth.get('alphaMode')!='BLEND' or cloth.get('doubleSided')is not True or 'KHR_materials_unlit'in cloth.get('extensions',{}):raise RuntimeError('Actual lit alpha-fibre cloth source required')
 project=Path(u.Paths.project_dir()).resolve();world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
 if not world or world.get_path_name().split('.',1)[0]!='/Game/Sub01Home/ActualHome':raise RuntimeError('ActualHome already loaded required')
 doors=json.loads((project/'private-audit/authentic-doors-native.json').read_text())
 if doors.get('source_sha256')!=DOOR_SHA or doors.get('saved')is not True:raise RuntimeError('Exact actually saved current patio-door geometry required')
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors)
 if any(a.get_actor_label()in NAMES or a.get_actor_label().startswith('SUB01ReferenceSheer_')for a in actors):raise RuntimeError('Cloth already installed; inspect actual saved receipt')
 result={'schema':'sub01.reference-sheer-native.v1','source_sha256':SHA,'dry_run':dry_run,'native_visual_verified':False,'native_light_filtering_verified':False,'native_shadow_quality_verified':False,'window_door_physics_changed':False,'activity_gates_changed':False}
 if dry_run:return result
 backup=project/'Saved/PrivateMapBackups'/('reference-sheer-'+str(time.time_ns()));backup.mkdir(parents=True);shutil.copy2(project/'Content/Sub01Home/ActualHome.umap',backup/'ActualHome.umap')
 for name in('__ExternalActors__','__ExternalObjects__'):
  directory=project/'Content'/name/'Sub01Home/ActualHome'
  if directory.exists():shutil.copytree(directory,backup/name)
 dest='/Game/Sub01Home/Sheer/V_'+SHA[:12]+'/A_'+uuid4().hex;audit=project/'private-audit';audit.mkdir(exist_ok=True);save_attempted=False
 try:
  manager=u.InterchangeManager.get_interchange_manager_scripted();params=u.ImportAssetParameters();params.set_editor_property('is_automated',True)
  if not manager.import_scene(dest,manager.create_source_data(str(source)),params):raise RuntimeError('Actual cloth source import refused')
  manager.wait_until_all_tasks_done(False);added=[a for a in eas.get_all_level_actors()if a.get_path_name()not in before]
  for a in added:a.set_actor_hidden_in_game(True);a.set_actor_enable_collision(False)
  by={}
  for a in added:
   for c in a.get_components_by_class(u.StaticMeshComponent):
    mesh=c.get_editor_property('static_mesh')
    if mesh and mesh.get_path_name().startswith(dest+'/'):
     for name in{a.get_actor_label(),mesh.get_name()}:
      if name in NAMES:by.setdefault(name,[]).append((a,c))
  parts=[];pbr=[];shader=[];total=0
  for ni,n in enumerate(doc['nodes']):
   found=by.get(n['name'],[])
   if len(found)!=1:raise RuntimeError('Exact unique cloth source-node actor required '+n['name'])
   a,c=found[0]
   if len(a.get_components_by_class(u.StaticMeshComponent))!=1:raise RuntimeError('Standalone cloth source component required')
   owned_geometry(u,c.get_editor_property('static_mesh'),dest)
   expected=expected_triangles(doc,blob,ni);actual=native_triangles(u,c)
   if not same_triangles(expected,actual,tolerance=.0001):raise RuntimeError('Actual complete cloth world triangles differ')
   material=doc['materials'][doc['meshes'][n['mesh']]['primitives'][0]['material']]
   binding=assigned_material_binding(c,material,dest);pbr+=verify_materials(u,[c],{'materials':[material]},dest,material_bindings=binding)
   if n['name']!='SCHardware':
    shader.append(lit_translucent_material(u,c.get_material(0)));c.set_editor_property('cast_volumetric_translucent_shadow',True)
    if not c.get_editor_property('cast_volumetric_translucent_shadow'):raise RuntimeError('Actual cloth translucent shadow flag refused')
   c.set_cast_shadow(True);c.set_collision_profile_name('NoCollision');c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
   if c.get_collision_enabled()!=u.CollisionEnabled.NO_COLLISION:raise RuntimeError('Cloth must not add walking or door collision')
   a.set_actor_label(n['name']);parts.append((a,c));total+=len(actual)
  if len(parts)!=3 or total!=15620 or len(shader)!=2 or snapshot(u,actors)!=before:raise RuntimeError('Complete cloth source and exact protected original state required')
  if not u.EditorAssetLibrary.save_directory(dest,only_if_is_dirty=False,recursive=True):raise RuntimeError('Actual owned cloth asset save failed')
  for a,c in parts:a.set_actor_hidden_in_game(False)
  if snapshot(u,actors)!=before:raise RuntimeError('Cloth visibility altered original actors')
  guard();result.update(owned_destination=dest,backup=str(backup),parts=[{'actor':a.get_path_name(),'component':c.get_path_name()}for a,c in parts],complete_native_triangles=total,actual_native_shaders=shader,materials=pbr,protected_originals_unchanged=True)
  pending=audit/'reference-sheer-native.pending.json';pending.write_text(json.dumps(result,indent=2));save_attempted=True
  if not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Actual cloth map save failed')
  result['saved']=True;pending.write_text(json.dumps(result,indent=2));pending.replace(audit/'reference-sheer-native.json');return result
 except Exception:
  detach_added(u,eas,before)
  if snapshot(u,actors)!=before:raise RuntimeError('Cloth rollback altered original scene; preserve backup')
  if save_attempted and not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Cloth rollback map save failed')
  raise
