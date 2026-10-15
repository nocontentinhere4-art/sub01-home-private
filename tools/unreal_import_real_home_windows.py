"""Warm Editor import of source-proven residential window construction only.
Exact lower30 originals retired after207part worldgeometry/PBR verification.
No camera, panorama, upper balcony, entry door, gameplay or activity flags change.
"""
import copy,hashlib,json,re,shutil,struct,time,uuid
from pathlib import Path
from home_asset_audit import read_gltf
from structural_rail_source_patch import world_matrices
from prepare_real_wc_bundle import node_geometry
from unreal_remove_frame_backings import native_triangles,same_triangles
from unreal_import_real_linea140 import verify_materials
from unreal_import_real_bathroom_pendant import source_slot_binding
from unreal_import_reference_dressing import fingerprint
from unreal_import_real_wc import owned_geometry
from unreal_owned_import_cleanup import detach_added
from real_home_window_plan import SOURCE_SHA,plan
ROOT=Path('/workspace/sub01-home-private/out/real-home-windows-r2')
EXPECTED_SHA='7119c36483ec3ba22aa71c0cab6a5a7d46d6daf1e544410a6d8fa5f8e933aa57'


def triangles(doc,blob,node):
 return [[[float(p[0])*100,float(p[2])*100,float(p[1])*100]for p in(row['points'][j]for j in face)]for row in node_geometry(doc,blob,node,world_matrices(doc))for face in row['faces']]


def prepare_legal_import_names(source,target):
 """Unique ASCII-only names prevent FBX/glTF period sanitization collisions.
 All geometry/material/binary bytes remain unchanged; only node/mesh names vary.
 """
 original,blob=read_gltf(source);doc=copy.deepcopy(original);names={}
 for i,n in enumerate(doc['nodes']):
  names[i]=n['name'];n['name']='SUB01_RealWindow_Part_'+str(i)
  doc['meshes'][n['mesh']]['name']=n['name']
 raw=json.dumps(doc,separators=(',',':')).encode();raw+=b' '*(-len(raw)%4);binary=bytes(blob);binary+=b'\0'*(-len(binary)%4)
 Path(target).parent.mkdir(parents=True,exist_ok=True);Path(target).write_bytes(struct.pack('<III',0x46546c67,2,28+len(raw)+len(binary))+struct.pack('<II',len(raw),0x4e4f534a)+raw+struct.pack('<II',len(binary),0x004e4942)+binary)
 actual,actual_blob=read_gltf(target);restored=copy.deepcopy(actual)
 for i,n in enumerate(original['nodes']):restored['nodes'][i]['name']=n['name']
 for i,m in enumerate(original['meshes']):
  if'name'in m:restored['meshes'][i]['name']=m['name']
  else:restored['meshes'][i].pop('name',None)
 if restored!=original or bytes(actual_blob)!=bytes(blob):raise RuntimeError('Names-only legal import preparation changed source content')
 return actual,actual_blob,names


def positive_area_triangles(source):
 """Match UE's removal of exact zero-area source faces, never positive geometry.

 The pinned207-part source contains432 exact-zero-area bevel triangles. Their
 coincident vertices have no surface; every strictly positive source face must
 still match one actual native face. No area epsilon or index-count waiver.
 """
 kept=[];removed=[]
 for index,t in enumerate(source):
  a=[t[1][k]-t[0][k]for k in range(3)];b=[t[2][k]-t[0][k]for k in range(3)]
  cross=(a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
  if all(v==0. for v in cross):removed.append(index)
  else:kept.append(t)
 return kept,removed


def clear_glass(u,dest):
 """Owned clear runtimeglass: actual thick geometry, low surface opacity, no opaqueimport fallback."""
 m=u.AssetToolsHelpers.get_asset_tools().create_asset('M_ResidentialClearGlass',dest,u.Material,u.MaterialFactoryNew())
 if not m:raise RuntimeError('Owned glass material creation failed')
 m.set_editor_property('blend_mode',u.BlendMode.BLEND_TRANSLUCENT);m.set_editor_property('two_sided',False)
 mel=u.MaterialEditingLibrary
 def scalar(value,prop):
  e=mel.create_material_expression(m,u.MaterialExpressionConstant);e.set_editor_property('r',value);mel.connect_material_property(e,'',prop)
 e=mel.create_material_expression(m,u.MaterialExpressionConstant3Vector);e.set_editor_property('constant',u.LinearColor(.97,.99,1,1));mel.connect_material_property(e,'',u.MaterialProperty.MP_BASE_COLOR)
 scalar(.025,u.MaterialProperty.MP_ROUGHNESS);scalar(.025,u.MaterialProperty.MP_OPACITY);scalar(.5,u.MaterialProperty.MP_SPECULAR)
 # Refraction intentionally1: static equirectangular background is at infinity;
 # layered thick glass remains geometrical, no arbitrary exterior image warp.
 scalar(1.,u.MaterialProperty.MP_REFRACTION);mel.recompile_material(m)
 if m.get_editor_property('blend_mode')!=u.BlendMode.BLEND_TRANSLUCENT:raise RuntimeError('Actual runtime glass is not translucent')
 return m


def run(dry_run=True):
 import unreal as u
 project=Path(u.Paths.project_dir());report=json.loads((ROOT/'source-report.json').read_text());proof=json.loads((ROOT/'protected-source-bvh-candidates.json').read_text());source=ROOT/'real-home-windows.glb'
 if hashlib.sha256(source.read_bytes()).hexdigest()!=EXPECTED_SHA or report['glb_sha256']!=EXPECTED_SHA:raise RuntimeError('Pinned actual residentialwindow source bytes required')
 if not proof.get('ok')or proof.get('unresolved_pair_count')!=0 or proof['source_sha256']!=SOURCE_SHA or proof.get('actual_export_glb_sha256')!=EXPECTED_SHA or proof.get('tested_export_meshes')!=207:raise RuntimeError('Measured protectedsource collision proof required')
 if report['part_count']!=207 or report['triangles']!=13056 or not report['all_parts_closed_manifold']:raise RuntimeError('Complete actual closed207part construction required')
 if report['old_nodes_to_retire']!=plan()['exact_old_lower_frame_nodes']:raise RuntimeError('Exact30 lowerframe scope required')
 home=project/'SourceAssets/full-home.glb'
 if hashlib.sha256(home.read_bytes()).hexdigest()!=SOURCE_SHA:raise RuntimeError('Exact original955 home required')
 hd,hb=read_gltf(home);doc,blob=read_gltf(source);eas=u.get_editor_subsystem(u.EditorActorSubsystem);original=list(eas.get_all_level_actors());before=fingerprint(u,original);old=[]
 if any(a.get_actor_label().startswith('SUB01_RealWindow_')for a in original):raise RuntimeError('Residential windows already staged/installed; inspect savedreceipt')
 for ni in report['old_nodes_to_retire']:
  actors=[a for a in original if a.get_name()==f'full-home_node_{ni}']
  if len(actors)!=1:raise RuntimeError('Exact original lowerframe actor required '+str(ni))
  a=actors[0];cs=a.get_components_by_class(u.StaticMeshComponent);mi=hd['nodes'][ni]['mesh'];sn=hd['meshes'][mi]['name']
  if len(cs)!=1:raise RuntimeError('Standalone originalframe component required')
  c=cs[0];m=c.get_editor_property('static_mesh')
  if not m or m.get_path_name()!=f'/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/{sn}.{sn}':raise RuntimeError('Originalframe source mesh identity differs '+str(ni))
  if not same_triangles(triangles(hd,hb,ni),native_triangles(u,c)):raise RuntimeError('Originalframe worldgeometry differs '+str(ni))
  old.append((a,c,bool(a.get_editor_property('hidden')),bool(c.get_editor_property('visible')),c.get_collision_enabled()))
 result={'schema':'sub01.real-home-windows-native.v1','source_sha256':EXPECTED_SHA,'dry_run':dry_run,'native_visual_verified':False,'windows_activity_ready':False,'exterior_mapping_changed':False}
 if dry_run:return result
 backup=project/'Saved/PrivateMapBackups'/('real-windows-'+str(time.time_ns()));backup.mkdir(parents=True);shutil.copy2(project/'Content/Sub01Home/ActualHome.umap',backup/'ActualHome.umap')
 for name in ('__ExternalActors__','__ExternalObjects__'):
  folder=project/'Content'/name/'Sub01Home/ActualHome'
  if folder.exists():shutil.copytree(folder,backup/name)
 dest='/Game/Sub01Home/ResidentialWindows/V_'+EXPECTED_SHA[:12]+'/Attempt_'+uuid.uuid4().hex;added=[];audit=project/'private-audit';audit.mkdir(exist_ok=True)
 prepared=project/'Saved/PrivateImportInputs'/('residential-windows-'+uuid.uuid4().hex+'.glb');doc,blob,source_names=prepare_legal_import_names(source,prepared)
 try:
  manager=u.InterchangeManager.get_interchange_manager_scripted();params=u.ImportAssetParameters();params.set_editor_property('is_automated',True)
  if not manager.import_scene(dest,manager.create_source_data(str(prepared)),params):raise RuntimeError('Residential assembly import refused')
  manager.wait_until_all_tasks_done(False);added=[a for a in eas.get_all_level_actors()if a.get_path_name()not in before]
  for a in added:a.set_actor_hidden_in_game(True)
  if fingerprint(u,original)!=before:raise RuntimeError('Import changed protected originals beforeactivation')
  components=[];glass_components=[];parts=[];geometry_parts=[];material_bindings={}
  for ni,node in enumerate(doc['nodes']):
   if'mesh'not in node:continue
   matches=[a for a in added if a.get_actor_label()==node['name']]
   if len(matches)!=1:raise RuntimeError('Actualwindow part not unique '+node['name'])
   a=matches[0];cs=a.get_components_by_class(u.StaticMeshComponent)
   if len(cs)!=1:raise RuntimeError('Windowpart component count differs')
   c=cs[0];owned_geometry(u,c.get_editor_property('static_mesh'),dest);full=triangles(doc,blob,ni);expected,zero_faces=positive_area_triangles(full);actual=native_triangles(u,c)
   if not same_triangles(expected,actual):
    (audit/'residential-window-geometry-refusal.json').write_text(json.dumps({'node':ni,'name':node['name'],'expected':len(expected),'actual':len(actual)},indent=2));raise RuntimeError('Full residential geometry/worldplacement differs '+node['name'])
   geometry_parts.append({'node':ni,'source_name':source_names[ni],'source_triangles':len(full),'exact_zero_area_source_indices':zero_faces,'positive_source_triangles':len(expected),'actual_native_triangles':len(actual),'all_positive_triangles_matched':True})
   c.set_collision_profile_name('BlockAll');c.set_collision_enabled(u.CollisionEnabled.QUERY_AND_PHYSICS)
   components.append(c);parts.append((a,c));pr=doc['meshes'][node['mesh']]['primitives']
   if len(pr)!=1 or c.get_num_materials()!=1:raise RuntimeError('Exact perpart source material required')
   sm=doc['materials'][pr[0]['material']]['name']
   if sm=='Window clear insulated glass':glass_components.append(c)
   else:
    binding=source_slot_binding(c,doc['materials'][pr[0]['material']],dest)
    if sm in material_bindings and material_bindings[sm]!=binding[sm]:raise RuntimeError('Source window material maps to multiple actual instances')
    material_bindings.update(binding)
  if sum(len(x['exact_zero_area_source_indices'])for x in geometry_parts)!=432 or sum(x['positive_source_triangles']for x in geometry_parts)!=12624:raise RuntimeError('Pinned complete positive source surface counts differ')
  if len(parts)!=207 or len(glass_components)!=45:raise RuntimeError('Complete207parts/45glass solids required')
  opaque=copy.deepcopy(doc);opaque['materials']=[m for m in opaque['materials']if m['name']!='Window clear insulated glass'];material_report=verify_materials(u,[c for c in components if c not in glass_components],opaque,dest,material_bindings=material_bindings)
  glass=clear_glass(u,dest)
  for c in glass_components:c.set_material(0,glass);c.set_editor_property('cast_shadow',False)
  # Match actual house mineral wall PBR, without mutating original wall158 or its assets.
  walls=[a for a in original if a.get_name()=='full-home_node_158']
  if len(walls)!=1:raise RuntimeError('Actual protected exteriorwall identity unavailable')
  wc=walls[0].get_components_by_class(u.StaticMeshComponent)
  if len(wc)!=1 or wc[0].get_num_materials()!=1:raise RuntimeError('Actual wall PBR not unique')
  for a,c in parts:
   if 'FacadePier_'in source_names[next(i for i,n in enumerate(doc['nodes'])if n['name']==a.get_actor_label())]:c.set_material(0,wc[0].get_material(0))
  if fingerprint(u,original)!=before:raise RuntimeError('Owned material setup changed protectedhome')
  for a,c,h,v,e in old:a.set_actor_hidden_in_game(True);c.set_visibility(False);c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
  for a,c in parts:a.set_actor_hidden_in_game(False);c.set_visibility(True)
  excluded={a.get_path_name()for a,c,*_ in old};untouched=[a for a in original if a.get_path_name()not in excluded]
  if fingerprint(u,untouched)!={k:v for k,v in before.items()if k not in excluded}:raise RuntimeError('Windowactivation changed unrelated architecture/devices')
  if not u.EditorAssetLibrary.save_directory(dest,only_if_is_dirty=False,recursive=True)or not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Residentialwindow asset/map save refused')
  result.update(parts=len(parts),glass_parts=45,positive_surface_geometry=geometry_parts,retired_original_actors=[a.get_path_name()for a,c,*_ in old],material_proof=material_report,glass_material=glass.get_path_name(),owned_destination=dest,map_backup=str(backup));(audit/'real-home-windows-native.json').write_text(json.dumps(result,indent=2)+'\n');return result
 except Exception as error:
  for a,c,h,v,e in old:
   if bool(a.get_editor_property('hidden'))!=h:a.set_actor_hidden_in_game(h)
   if bool(c.get_editor_property('visible'))!=v:c.set_visibility(v)
   if c.get_collision_enabled()!=e:c.set_collision_enabled(e)
  cleanup=detach_added(u,eas,before);equal=fingerprint(u,original)==before
  (audit/'real-home-windows-native-refusal.json').write_text(json.dumps({'error':str(error),'original_rollback_verified':equal,'quarantined_assets':dest,'cleanup':cleanup,'backup':str(backup)},indent=2)+'\n')
  if not equal:raise RuntimeError('Originalwindow rollback differs; inspect backup')from error
  raise
