"""Sole-owner executable genuine desk replacement in already-loaded ActualHome.

run(export_glb, dry_run=True) reads exact native bindings. run(...,dry_run=False)
imports unique owned scene assets, measures actual triangle/PBR/contact geometry,
fits the verified authentic side-edge clamp + paired bulb/light, preserves the
grommet hardware, then hides exactly original181/182. Rollback restores
original component/actor states on failure. No level loading or runtime restart.
"""
import hashlib,json,math,re,shutil,time
from pathlib import Path
from home_asset_audit import read_gltf
from unreal_owned_mesh_source_geometry import prepare as prepare_owned_geometry
from unreal_import_reference_dressing import fingerprint
from prepare_real_linea140_placement import SHA
LEVEL='/Game/Sub01Home/ActualHome'
PREFIX='SUB01_RealLinea140_99bdf3fd_'


def close(a,b,tolerance=.05):return len(a)==len(b) and max(abs(x-y)for x,y in zip(a,b))<=tolerance

def vec(v):return [float(v.x),float(v.y),float(v.z)]

def surface(u,c):
 mesh=c.get_editor_property('static_mesh');points=[];triangles=0
 if not mesh or not hasattr(u,'ProceduralMeshLibrary'):raise RuntimeError('Actual native triangle API unavailable')
 for section in range(mesh.get_num_sections(0)):
  local,ids,*_=u.ProceduralMeshLibrary.get_section_from_static_mesh(mesh,0,section)
  if len(ids)%3:raise RuntimeError('Incomplete actual native triangles')
  triangles+=len(ids)//3;transform=c.get_world_transform();points.extend(vec(transform.transform_location(p))for p in local)
 if not points:raise RuntimeError('Actual native mesh geometry absent')
 return points,triangles


def verify_materials(u,components,doc,dest):
 unique={m.get_path_name():m for c in components for m in c.get_materials() if m}
 if len(unique)!=len(doc['materials']):raise RuntimeError('Real furniture imported material count differs original source')
 def canon(s):return re.sub('[^a-z0-9]','',s.lower())
 rows=[];mel=u.MaterialEditingLibrary
 for source in doc['materials']:
  matches=[m for m in unique.values()if canon(source['name']) in canon(m.get_name())]
  if len(matches)!=1:raise RuntimeError('Original material identity ambiguous '+source['name'])
  mat=matches[0]
  if not mat.get_path_name().startswith(dest+'/') or not isinstance(mat,u.MaterialInstanceConstant):raise RuntimeError('Material is not exact owned imported instance')
  vectors={str(n):n for n in mel.get_vector_parameter_names(mat)};scalars={str(n):n for n in mel.get_scalar_parameter_names(mat)};textures={str(n):n for n in mel.get_texture_parameter_names(mat)}
  pbr=source.get('pbrMetallicRoughness',{});factor=pbr.get('baseColorFactor',[1,1,1,1])
  if 'BaseColorFactor' not in vectors or 'EmissiveFactor' not in vectors:raise RuntimeError('Actual required colour/emission parameters unavailable')
  value=mel.get_material_instance_vector_parameter_value(mat,vectors['BaseColorFactor'])
  if not close([value.r,value.g,value.b,value.a],factor,1e-5):raise RuntimeError('Authored original base factor changed')
  e=mel.get_material_instance_vector_parameter_value(mat,vectors['EmissiveFactor'])
  if max(abs(e.r),abs(e.g),abs(e.b))>1e-6:raise RuntimeError('Unexpected source desk emission')
  expected={'MetallicFactor':pbr.get('metallicFactor',1),'RoughnessFactor':pbr.get('roughnessFactor',1)}
  if 'normalTexture'in source:expected['NormalScale']=source['normalTexture'].get('scale',1)
  clearcoat=source.get('extensions',{}).get('KHR_materials_clearcoat')
  if clearcoat:
   parent=mat.get_editor_property('parent')
   if not parent or parent.get_path_name()!='/InterchangeAssets/gltf/MaterialInstances/MI_ClearCoat_Opaque_DS.MI_ClearCoat_Opaque_DS':raise RuntimeError('Original double-sided clearcoat material parent differs')
   expected['ClearCoatFactor']=clearcoat.get('clearcoatFactor',0);expected['ClearCoatRoughnessFactor']=clearcoat.get('clearcoatRoughnessFactor',0)
  for name,want in expected.items():
   if name not in scalars or abs(mel.get_material_instance_scalar_parameter_value(mat,scalars[name])-want)>1e-5:raise RuntimeError('Authored scalar differs '+name)
  roles=[]
  for field,param,srgb,compression in [('baseColorTexture','BaseColorTexture',True,u.TextureCompressionSettings.TC_DEFAULT),('metallicRoughnessTexture','MetallicRoughnessTexture',False,u.TextureCompressionSettings.TC_MASKS),('normalTexture','NormalTexture',False,u.TextureCompressionSettings.TC_NORMALMAP)]:
   desc=source if field=='normalTexture' else pbr
   if field not in desc:continue
   if param not in textures:raise RuntimeError('Actual texture parameter absent '+param)
   tex=mel.get_material_instance_texture_parameter_value(mat,textures[param])
   if not tex or not tex.get_path_name().startswith(dest+'/'):raise RuntimeError('Authored PBR texture reused unowned asset')
   tex.set_editor_property('srgb',srgb);tex.set_editor_property('compression_settings',compression)
   if bool(tex.get_editor_property('srgb'))!=srgb or tex.get_editor_property('compression_settings')!=compression:raise RuntimeError('Owned texture role correction refused')
   roles.append({'parameter':param,'texture':tex.get_path_name(),'srgb':srgb,'compression':str(compression)})
  rows.append({'source_material':source['name'],'actual_material':mat.get_path_name(),'textures':roles})
 return rows


def run(export_glb,dry_run=True,u=None,defer_activation=False):
 if u is None:import unreal as u
 source=Path(export_glb);report=json.loads(source.with_suffix('.json').read_text());digest=hashlib.sha256(source.read_bytes()).hexdigest();doc,_=read_gltf(source)
 if report.get('source_sha256')!=SHA or report.get('output_sha256')!=digest or not report.get('source_binary_unchanged'):raise RuntimeError('Actual complete desk export proof missing')
 mount=report.get('lamp_mount',{})
 if not mount.get('collision_proof',{}).get('ok') or mount.get('mount_mechanism')!='C-clamp-side-edge':raise RuntimeError('Actual C-clamp support and source triangle collision proof missing')
 if any(not n.get('name','').startswith('SUB01_RealLinea140_')for n in doc['nodes']):raise RuntimeError('Desk scene node UID uniqueness not verified')
 world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
 if not world or world.get_path_name().split('.',1)[0]!=LEVEL:raise RuntimeError('ActualHome must already be loaded by sole editor owner')
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);original=list(eas.get_all_level_actors());before=fingerprint(u,original)
 def exact(predicate,label):
  found=[a for a in original if predicate(a)]
  if len(found)!=1:raise RuntimeError('Actual identity unavailable '+label)
  return found[0]
 old=[exact(lambda a:a.get_name()==f'full-home_node_{i}',str(i))for i in (181,182)]
 for a,name in zip(old,('Desk_hardware','Oak_desk')):
  comps=a.get_components_by_class(u.StaticMeshComponent)
  if a.get_actor_label()!=name or len(comps)!=1 or not comps[0].get_editor_property('static_mesh').get_path_name().startswith('/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/'):raise RuntimeError('Exact original desk source identity differs; no shared batch hide')
 lamp=exact(lambda a:a.get_path_name()==mount['actual_saved_lamp_actor'],'saved DeskLamp actor')
 light=exact(lambda a:a.get_actor_label()==mount['light_actor_label_for_exact_component_preflight'],'actual authored DeskLamp light')
 lc=lamp.get_components_by_class(u.StaticMeshComponent);lights=light.get_components_by_class(u.LightComponent)
 if len(lc)!=1 or len(lights)!=1:raise RuntimeError('Lamp component/light binding ambiguous')
 if [m.get_path_name()for m in lc[0].get_materials()]!=mount['actual_saved_material_paths']:raise RuntimeError('Actual saved lamp material binding changed')
 if not close(vec(lamp.get_actor_location()),mount['actual_saved_origin_cm']) or not close(vec(lights[0].get_world_location()),mount['actual_old_light_ue_cm']):raise RuntimeError('Actual saved lamp/light transform changed')
 lamp_points,lamp_triangles=surface(u,lc[0]);lamp_bounds=[[min(p[a]for p in lamp_points)for a in range(3)],[max(p[a]for p in lamp_points)for a in range(3)]]
 if lamp_triangles!=mount['lamp_source_triangle_count'] or not all(close(a,b)for a,b in zip(lamp_bounds,mount['old_native_aabb_cm'])):raise RuntimeError('Actual native lamp source geometry differs measured support model')
 old_points=[]
 for c in old[1].get_components_by_class(u.StaticMeshComponent):old_points.extend(surface(u,c)[0])
 if abs(max(p[2]for p in old_points)-84.5)>.05:raise RuntimeError('Actual old desk support top differs84.5; no assumed offset')
 result={'schema':'sub01.real-linea140-native-import.v1','dry_run':dry_run,'source_sha256':SHA,'export_sha256':digest,'exact_lamp_actor':lamp.get_path_name(),'exact_lamp_component':lc[0].get_path_name(),'exact_light_component':lights[0].get_path_name(),'old_desk_actors':[a.get_path_name()for a in old],'native_visual_verified':False}
 if dry_run:return result
 dest='/Game/Sub01Home/RealLinea140/V_'+digest[:12]
 if u.EditorAssetLibrary.does_directory_exist(dest):raise RuntimeError('Desk version already imported; inspect saved receipt instead of duplicate import')
 states=[(a,a.get_actor_transform(),a.get_actor_label(),bool(a.get_editor_property('hidden')),[(c,c.get_world_transform(),c.get_editor_property('static_mesh'),list(c.get_materials()),list(c.get_editor_property('component_tags')),bool(c.get_editor_property('visible')),c.get_collision_enabled(),c.get_collision_profile_name())for c in a.get_components_by_class(u.StaticMeshComponent)])for a in original]
 project=Path(u.Paths.project_dir());backup=project/'Saved/PrivateMapBackups'/('real-linea140-'+str(time.time_ns()));backup.mkdir(parents=True)
 shutil.copy2(project/'Content/Sub01Home/ActualHome.umap',backup/'ActualHome.umap')
 for directory in ('__ExternalActors__','__ExternalObjects__'):
  folder=project/'Content'/directory/'Sub01Home/ActualHome'
  if folder.exists():shutil.copytree(folder,backup/directory)
 result['map_backup']=str(backup)
 added=[];created_lampdest=None
 try:
  manager=u.InterchangeManager.get_interchange_manager_scripted();params=u.ImportAssetParameters();params.set_editor_property('is_automated',True);data=manager.create_source_data(str(source))
  if not manager.import_scene(dest,data,params):raise RuntimeError('Owned real desk import refused')
  manager.wait_until_all_tasks_done(False)
  added=[a for a in eas.get_all_level_actors()if a.get_path_name()not in before]
  if fingerprint(u,original)!=before:raise RuntimeError('Import altered an existing actor before any old hide')
  expected=report['expected_actor_nodes'];by_node={};components=[];allpoints=[];triangles=0
  for index,name in expected.items():
   matches=[a for a in added if a.get_actor_label()==name]
   if len(matches)!=1:raise RuntimeError('Original source node did not import uniquely '+name)
   actor=matches[0];comps=actor.get_components_by_class(u.StaticMeshComponent)
   if len(comps)!=1:raise RuntimeError('Source node component count differs')
   c=comps[0];mesh=c.get_editor_property('static_mesh')
   if not mesh or not mesh.get_path_name().startswith(dest+'/'):raise RuntimeError('New desk reused existing mesh identity')
   prepare_owned_geometry(u,mesh,dest)
   points,count=surface(u,c);allpoints.extend(points);triangles+=count;components.append(c);by_node[int(index)]=(actor,c,points)
  if triangles!=20024:raise RuntimeError('Actual native desk lost original triangles')
  wanted=[[b[0]*100,b[2]*100,b[1]*100]for b in report['actual_export_bounds_m']]
  actual=[[min(p[a]for p in allpoints)for a in range(3)],[max(p[a]for p in allpoints)for a in range(3)]]
  if not all(close(a,b)for a,b in zip(actual,wanted)):raise RuntimeError('Actual native placed dimensions differ source')
  if abs(max(p[2]for p in by_node[44][2])-84.5)>.05:raise RuntimeError('Actual native worktop support height differs baseline')
  result['materials']=verify_materials(u,components,doc,dest)
  for c in components:
   body=c.get_editor_property('static_mesh').get_editor_property('body_setup')
   if not body:raise RuntimeError('Real furniture physical collision missing')
   body.set_editor_property('collision_trace_flag',u.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE);c.set_collision_profile_name('BlockAll');c.set_collision_enabled(u.CollisionEnabled.QUERY_AND_PHYSICS)
  if fingerprint(u,original)!=before:raise RuntimeError('New owned material/collision setup changed originals')
  posed_path=source.parent/'lamp-posed.glb';posed_hash=hashlib.sha256(posed_path.read_bytes()).hexdigest()
  if posed_hash!=mount['posed_lamp']['sha256']or not mount['posed_lamp']['other_positions_normals_uv_indices_unchanged']:raise RuntimeError('Actual rigid screw derivative proof differs')
  lampdest='/Game/Sub01Home/RealEdgeClampLamp/V_'+posed_hash[:12]
  if u.EditorAssetLibrary.does_directory_exist(lampdest):raise RuntimeError('Posed lamp version already exists; preserve prior asset')
  task=u.AssetImportTask();task.set_editor_property('filename',str(posed_path));task.set_editor_property('destination_path',lampdest);task.set_editor_property('automated',True);task.set_editor_property('replace_existing',False);task.set_editor_property('save',False)
  created_lampdest=lampdest
  u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
  posed_meshes=[u.EditorAssetLibrary.load_asset(path)for path in u.EditorAssetLibrary.list_assets(lampdest,recursive=True,include_folder=False)]
  posed_meshes=[m for m in posed_meshes if isinstance(m,u.StaticMesh)]
  if len(posed_meshes)!=1:raise RuntimeError('Authentic posed C-clamp must import one complete source mesh')
  posed_mesh=posed_meshes[0];prepare_owned_geometry(u,posed_mesh,lampdest);slots=list(posed_mesh.get_editor_property('static_materials'))
  if len(slots)!=2 or posed_mesh.get_num_sections(0)!=2:raise RuntimeError('Source body/light material slots changed')
  counts=[len(u.ProceduralMeshLibrary.get_section_from_static_mesh(posed_mesh,0,i)[1])//3 for i in range(2)]
  if counts!=[22598,1504]:raise RuntimeError('Actual posed body/light section identities differ; no guessed material order')
  for slot,material in zip(slots,lc[0].get_materials()):slot.set_editor_property('material_interface',material)
  posed_mesh.set_editor_property('static_materials',slots)
  body=posed_mesh.get_editor_property('body_setup')
  if not body:raise RuntimeError('Authentic clamp physical collision missing')
  body.set_editor_property('collision_trace_flag',u.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
  if fingerprint(u,original)!=before:raise RuntimeError('Posed lamp import changed originals before activation')
  if defer_activation:
   return result,{'u':u,'old':old,'lamp':lamp,'light':light,'lights':lights,'by_node':by_node,'mount':mount,'original':original,'before':before,'added':added,'triangles':triangles,'actual':actual,'dest':dest,'source':source,'posed_mesh':posed_mesh,'lampdest':lampdest,'lamp_component':lc[0]}
  for hardware in mount['opened_hardware_source_nodes']:
   cap,cc,_=by_node[hardware];cap.set_actor_hidden_in_game(True);cc.set_visibility(False);cc.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
  lc[0].set_static_mesh(posed_mesh)
  for slot,material in enumerate(mount['actual_saved_material_paths']):lc[0].set_material(slot,u.EditorAssetLibrary.load_asset(material))
  lamp.set_actor_location(u.Vector(*mount['new_origin_ue_cm']),False,False)
  light.set_actor_location(u.Vector(*mount['new_bulb_ue_cm']),False,False)
  if not close(vec(lights[0].get_world_location()),mount['new_bulb_ue_cm']):raise RuntimeError('Exact light component failed paired bulb move')
  untouched=[a for a in original if a not in (lamp,light)]
  if fingerprint(u,untouched)!={k:v for k,v in before.items()if k not in (lamp.get_path_name(),light.get_path_name())}:raise RuntimeError('Lamp move changed unrelated actors')
  for a in old:
   a.set_actor_hidden_in_game(True)
   for c in a.get_components_by_class(u.StaticMeshComponent):c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
  allowed={a.get_path_name()for a in old+[lamp,light]}
  if fingerprint(u,[a for a in original if a.get_path_name()not in allowed])!={k:v for k,v in before.items()if k not in allowed}:raise RuntimeError('Old desk hide changed protected originals')
  result.update(native_triangle_count=triangles,native_bounds_cm=actual,desk_original_states=before,lamp_mount=mount,added_actors=[a.get_path_name()for a in added],opened_exact_hardware_actors=[by_node[i][0].get_path_name()for i in mount['opened_hardware_source_nodes']],device_contact='Actual worktop matches baseline84.5cm; device mesh/transform/material bindings remain byte-identical in native fingerprint. Existing device penetration is not corrected or called perfect.')
  if not u.EditorAssetLibrary.save_directory(lampdest,only_if_is_dirty=False,recursive=True) or not u.EditorAssetLibrary.save_directory(dest,only_if_is_dirty=False,recursive=True) or not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Real desk asset/map save failed')
  source.with_name('native-real-linea140-import.json').write_text(json.dumps(result,indent=2)+'\n');return result
 except Exception:
  for actor,transform,label,hidden,comps in states:
   actor.set_actor_transform(transform,False,False);actor.set_actor_label(label);actor.set_actor_hidden_in_game(hidden)
   for c,world,mesh,materials,tags,visible,collision,profile in comps:
    c.set_static_mesh(mesh);c.set_world_transform(world,False,False);c.set_editor_property('component_tags',tags);c.set_visibility(visible);c.set_collision_profile_name(profile);c.set_collision_enabled(collision)
    for slot,material in enumerate(materials):c.set_material(slot,material)
  for a in added:eas.destroy_actor(a)
  for owned in (dest,created_lampdest):
   if owned and u.EditorAssetLibrary.does_directory_exist(owned):u.EditorAssetLibrary.delete_directory(owned)
  raise
