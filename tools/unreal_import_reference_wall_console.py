"""Sole Editor owner: replace only six saved media device parts with wall assembly.

Saved cabinet, original TV/Minecraft, doors, windows, input and held controller
remain byte-identical. Source preview is never native/gameplay acceptance.
"""
import copy,hashlib,json,shutil,time
from pathlib import Path
from uuid import uuid4
ROOT=Path('/workspace/sub01-home-private/reference-wall-console-r1/output')
SHA='6768a9972ce5f21533f75fbc49b0860233e877d6adf0348db1398bc80ca1e522'
MEDIA_SHA='7a27cdf114d219968c7e5aa39f491be2ff979d58d3965344acf0ebdb6a651a96'
HOME_SHA='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
NAMES={f'WCPart{i:02}'for i in range(6)}
OLD_MATERIALS={'RM05':'Console satin black polymer','RM06':'Console white textured polymer','RM07':'Console vent shadow','RM08':'Console dim blue status trim','RM09':'Console stand satin steel','RM10':'controller'}


def validate_contract(report,proof):
 if (report.get('schema')!='sub01.reference-wall-console-source.v1' or report.get('sha256')!=SHA
     or report.get('triangles')!=39636 or report.get('controller_display_width_m')!=.16
     or report.get('controller_held_source_changed')is not False
     or report.get('actual_tv_screen_geometry_or_minecraft_changed')is not False
     or report.get('existing_cabinet_changed')is not False or report.get('wall_contact_x_m')!=-3.77
     or {p.get('node')for p in report.get('parts',[])}!=NAMES):
  raise RuntimeError('Frozen exact rigid reused wall-console source contract required')
 if (proof.get('schema')!='sub01.reference-wall-console-bvh.v1' or proof.get('sha256')!=SHA
     or proof.get('protected_home_sha256')!=HOME_SHA or proof.get('protected_cabinet_source_sha256')!=MEDIA_SHA
     or proof.get('actual_window_source_sha256')!='7119c36483ec3ba22aa71c0cab6a5a7d46d6daf1e544410a6d8fa5f8e933aa57'
     or proof.get('actual_door_source_sha256')!='5b8a2bb8b4bb8fe19af1d0c086fb78f3e7f9dff9e06170a06642a8f3d1761a0c'
     or proof.get('protected_parts')!=521 or proof.get('parts')!=6 or proof.get('epsilon_m')!=0
     or proof.get('ignored_pairs')!=0 or proof.get('unresolved')!=[] or proof.get('ok')is not True):
  raise RuntimeError('Complete actual source/home/window/door/cabinet no-penetration proof required')
 congruency=proof.get('rigid_reuse_congruency',[])
 if len(congruency)!=5 or any(r.get('ok')is not True or r.get('original_triangles')!=r.get('current_triangles')or not 0<=r.get('maximum_bidirectional_triangle_edge_shape_distance_m',-1)<.000002 for r in congruency):
  raise RuntimeError('Existing original console/controller rigid geometry evidence required')
 for contact in proof.get('measured_attachment_contacts',[]):
  if (contact.get('part')!='WCPart04' or contact.get('protected_part')!='house-static-67'
      or contact.get('actual_wall_plane_x_m')!=-3.7699999809265137
      or contact.get('classification')!='exact rear surface attachment, no vertex behind actual float32 wall plane'):
   raise RuntimeError('Only exact manufactured rear-face contact with actual wall is permitted')


def positive_triangles(triangles):
 kept=[];zero=[]
 for index,t in enumerate(triangles):
  a=[t[1][k]-t[0][k]for k in range(3)];b=[t[2][k]-t[0][k]for k in range(3)]
  cross=(a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
  if cross==(0.,0.,0.):zero.append(index)
  else:kept.append(t)
 return kept,zero


def run(dry_run=True):
 import unreal as u
 from home_asset_audit import read_gltf
 from unreal_import_reference_entry import guard,snapshot
 from unreal_import_real_wc import owned_geometry,expected_triangles
 from unreal_remove_frame_backings import native_triangles,same_triangles
 from unreal_import_real_bathroom_pendant import verify_owned_material
 from unreal_owned_import_cleanup import detach_added
 guard();source=ROOT/'wall-console.glb'
 if hashlib.sha256(source.read_bytes()).hexdigest()!=SHA:raise RuntimeError('Frozen source bytes required')
 report=json.loads((ROOT/'source-report.json').read_text());proof=json.loads((ROOT/'source-collision-proof.json').read_text());validate_contract(report,proof)
 doc,blob=read_gltf(source)
 if len(doc['nodes'])!=6 or {n.get('name')for n in doc['nodes']}!=NAMES:raise RuntimeError('Exact six material-group sources required')
 project=Path(u.Paths.project_dir()).resolve()
 if project!=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab')or hashlib.sha256((project/'SourceAssets/full-home.glb').read_bytes()).hexdigest()!=HOME_SHA:raise RuntimeError('Exact private project and protected home source required')
 world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
 if not world or world.get_path_name().split('.',1)[0]!='/Game/Sub01Home/ActualHome':raise RuntimeError('ActualHome must already be loaded')
 audit=project/'private-audit';receipt=json.loads((audit/'reference-media-native-import.json').read_text())
 if receipt.get('saved')is not True or receipt.get('source_sha256')!=MEDIA_SHA or len(receipt.get('parts',[]))!=11 or any(receipt.get('material_aliases',{}).get(k)!=v for k,v in OLD_MATERIALS.items()):raise RuntimeError('Exact actually saved eleven-part media receipt required')
 old_doc,old_blob=read_gltf(Path('/workspace/sub01-home-private/real-media-console-source-r1/output/media-console-side-native.glb'))
 if hashlib.sha256(Path('/workspace/sub01-home-private/real-media-console-source-r1/output/media-console-side-native.glb').read_bytes()).hexdigest()!=MEDIA_SHA:raise RuntimeError('Exact previous source required')
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);by_path={a.get_path_name():a for a in actors}
 if any(a.get_actor_label()in NAMES for a in actors):raise RuntimeError('Wall console already exists; inspect saved receipt')
 retired=[];states=[]
 for index in range(5,11):
  item=receipt['parts'][index];a=by_path.get(item['actor'])
  if not a:raise RuntimeError('Saved media actor absent')
  components=a.get_components_by_class(u.StaticMeshComponent)
  if len(components)!=1 or components[0].get_path_name()!=item['component']:raise RuntimeError('Exact standalone saved device component required')
  c=components[0];mesh=c.get_editor_property('static_mesh');mat=c.get_material(0)
  if not mesh or not mesh.get_path_name().startswith(receipt['owned_destination']+'/')or not mat or mat.get_name()!=f'RM{index:02}'or a.get_editor_property('hidden'):raise RuntimeError('Saved device ownership/assigned unique material/visible state differs')
  expected,zero=positive_triangles(expected_triangles(old_doc,old_blob,index))
  if not same_triangles(expected,native_triangles(u,c),tolerance=.0001):raise RuntimeError('Saved device complete actual positive geometry differs')
  retired.append((a,c));states.append((a,bool(a.get_editor_property('hidden')),a.is_temporarily_hidden_in_editor(),c,c.get_collision_enabled(),c.get_collision_profile_name()))
 result={'schema':'sub01.reference-wall-console-native.v1','source_sha256':SHA,'dry_run':dry_run,'native_visual_verified':False,'gameplay_available':False,'held_controller_changed':False,'tv_minecraft_changed':False,'cabinet_changed':False,'retired_saved_media_indices':list(range(5,11))}
 if dry_run:return result
 backup=project/'Saved/PrivateMapBackups'/('wall-console-'+str(time.time_ns()));backup.mkdir(parents=True);shutil.copy2(project/'Content/Sub01Home/ActualHome.umap',backup/'ActualHome.umap')
 for name in('__ExternalActors__','__ExternalObjects__'):
  directory=project/'Content'/name/'Sub01Home/ActualHome'
  if directory.exists():shutil.copytree(directory,backup/name)
 destination='/Game/Sub01Home/WallConsole/V_'+SHA[:12]+'/A_'+uuid4().hex;save_attempted=False
 try:
  manager=u.InterchangeManager.get_interchange_manager_scripted();params=u.ImportAssetParameters();params.set_editor_property('is_automated',True)
  if not manager.import_scene(destination,manager.create_source_data(str(source)),params):raise RuntimeError('Exact wall console import refused')
  manager.wait_until_all_tasks_done(False);added=[a for a in eas.get_all_level_actors()if a.get_path_name()not in before]
  for a in added:a.set_actor_hidden_in_game(True)
  by={}
  for a in added:
   for c in a.get_components_by_class(u.StaticMeshComponent):
    mesh=c.get_editor_property('static_mesh')
    if mesh and mesh.get_path_name().startswith(destination+'/'):
     for key in{mesh.get_name(),a.get_actor_label()}:
      if key in NAMES:by.setdefault(key,[]).append((a,c))
  parts=[];pbr=[];geometry=[]
  for ni,node in enumerate(doc['nodes']):
   matches=by.get(node['name'],[])
   if len(matches)!=1:raise RuntimeError('Exact unique wall-console node binding required')
   a,c=matches[0];mesh=c.get_editor_property('static_mesh')
   if len(a.get_components_by_class(u.StaticMeshComponent))!=1:raise RuntimeError('One source primitive/component required')
   owned_geometry(u,mesh,destination);expected,zero=positive_triangles(expected_triangles(doc,blob,ni));actual=native_triangles(u,c)
   if not same_triangles(expected,actual,tolerance=.0001):raise RuntimeError('Complete positive wall-console triangles differ')
   primitives=doc['meshes'][node['mesh']]['primitives']
   if len(primitives)!=1:raise RuntimeError('Exactly one source material per node required')
   material=doc['materials'][primitives[0]['material']];pbr.append(verify_owned_material(u,c,material,destination,source_primitive_verified=True))
   c.set_collision_profile_name('NoCollision');c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION);c.set_cast_shadow(True);a.set_actor_label(node['name']);parts.append((a,c));geometry.append({'source_node':node['name'],'positive_triangles':len(actual),'source_exact_zero_indices':zero})
  if len(parts)!=6 or snapshot(u,actors)!=before:raise RuntimeError('Complete assembly and unchanged protected originals required')
  if not u.EditorAssetLibrary.save_directory(destination,only_if_is_dirty=False,recursive=True):raise RuntimeError('New owned asset save failed')
  expected_after=copy.deepcopy(before)
  for a,c in retired:
   a.set_actor_hidden_in_game(True);a.set_is_temporarily_hidden_in_editor(True);c.set_collision_profile_name('NoCollision');c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
   row=expected_after[a.get_path_name()];row['hidden']=True;row['editor_hidden']=True
   component=next(x for x in row['components']if x['path']==c.get_path_name());component['profile']='NoCollision';component['collision']=str(u.CollisionEnabled.NO_COLLISION)
  for a,c in parts:a.set_actor_hidden_in_game(False)
  if snapshot(u,actors)!=expected_after:raise RuntimeError('Exact device-only retirement changed protected state')
  result.update(owned_destination=destination,backup=str(backup),parts=[{'actor':a.get_path_name(),'component':c.get_path_name()}for a,c in parts],materials=pbr,geometry=geometry,original_devices_preserved_hidden=True,protected_other_actors_exact=True)
  pending=audit/'reference-wall-console-native.pending.json';pending.write_text(json.dumps(result,indent=2));guard();save_attempted=True
  if not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Wall assembly map save failed')
  result['saved']=True;pending.write_text(json.dumps(result,indent=2));pending.replace(audit/'reference-wall-console-native.json');return result
 except Exception:
  for a,h,eh,c,collision,profile in states:
   a.set_actor_hidden_in_game(h);a.set_is_temporarily_hidden_in_editor(eh);c.set_collision_profile_name(profile);c.set_collision_enabled(collision)
  detach_added(u,eas,before)
  if snapshot(u,actors)!=before:raise RuntimeError('Wall-console rollback changed protected state; preserve map backup')
  if save_attempted and not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Rollback map save failed')
  raise
