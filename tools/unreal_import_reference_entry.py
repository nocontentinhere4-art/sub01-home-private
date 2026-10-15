"""Replace only courtyard visuals in the sole warm private ActualHome Editor.

All four existing courtyard support/barrier actors retain their original meshes,
transforms, materials and collision. Four new exact-source material groups have
no collision. This does not change panorama projection, FOV or walking physics.
"""
import copy
import hashlib
import json
import shutil
import time
from pathlib import Path
from uuid import uuid4

ROOT=Path('/workspace/sub01-home-private/reference-entry-source-r1/output')
SHA='1a7cc5ac9948a81161549af7d2f7f5b9d6ff22ea115a77228939b6c6ab1e60a1'
HOME_SHA='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
PREFIX='SUB01ReferenceEntry_'
NAMES={PREFIX+str(i)for i in range(4)}
OLD={
 'SUB01_PrivateEntry_Support':([75,580,-2.5],[325,870,2.5]),
 'SUB01_PrivateEntry_LeftWall':([75,580,2.5],[80,870,112.5]),
 'SUB01_PrivateEntry_RightWall':([320,580,2.5],[325,870,112.5]),
 'SUB01_PrivateEntry_FarWall':([75,865,2.5],[325,870,112.5]),
}


def validate_source(source,report):
 from home_asset_audit import read_gltf
 if hashlib.sha256(Path(source).read_bytes()).hexdigest()!=SHA:
  raise RuntimeError('Frozen actual courtyard GLB required')
 if (report.get('schema')!='sub01.reference-entry-courtyard-source.v1'
     or report.get('sha256')!=SHA or report.get('triangles')!=19252
     or report.get('material_groups')!=4
     or report.get('existing_floor_and_barrier_collisions_must_remain')is not True
     or set(report.get('retire_visual_only_labels',[]))!=set(OLD)
     or report.get('new_paver_top_cm')!=2.52
     or report.get('existing_collision_floor_top_cm')!=2.5
     or report.get('ground_gap_cm')!=6.):
  raise RuntimeError('Exact visual-only source and unchanged floor/barrier contract required')
 doc,blob=read_gltf(Path(source))
 nodes=[n for n in doc['nodes']if'mesh'in n]
 if len(nodes)!=4 or {n.get('name')for n in nodes}!=NAMES or len(doc.get('materials',[]))!=4:
  raise RuntimeError('Exact four uniquely named material-group source nodes required')
 total=0
 for n in nodes:
  primitives=doc['meshes'][n['mesh']]['primitives']
  if len(primitives)!=1 or not {'NORMAL','TEXCOORD_0'}<=set(primitives[0]['attributes']):
   raise RuntimeError('Exact complete normals/UV/source material per part required')
  total+=doc['accessors'][primitives[0]['indices']]['count']//3
 if total!=19252:raise RuntimeError('Actual complete source triangle count differs')
 return doc,blob


def snapshot(u,actors):
 from unreal_import_reference_dressing import fingerprint
 rows=fingerprint(u,actors)
 for a in actors:
  row=rows[a.get_path_name()]
  row['hidden']=bool(a.get_editor_property('hidden'))
  row['editor_hidden']=bool(a.is_temporarily_hidden_in_editor())
  row['actor_collision']=bool(a.get_actor_enable_collision())
  row['component_visibility']={c.get_path_name():bool(c.get_editor_property('visible'))for c in a.get_components_by_class(u.StaticMeshComponent)}
 return rows


def expected_hidden(before,old):
 result=copy.deepcopy(before)
 for actor in old:
  result[actor.get_path_name()]['hidden']=True
  result[actor.get_path_name()]['editor_hidden']=True
 return result


def assigned_material_binding(c,source,destination):
 """Source-node geometry identifies its sole actually assigned owned material.

 Material/slot basenames can be shortened by Interchange. They are never used
 as identity here; explicit binding is followed by numeric/texture PBR checks.
 """
 material=c.get_material(0)
 if c.get_num_materials()!=1 or not material or not material.get_path_name().startswith(destination+'/'):
  raise RuntimeError('Exactly one actually assigned newly owned material required')
 return {source['name']:material.get_path_name()}


def guard():
 from unreal_editor_task_queue import guard_valid
 if not guard_valid(now=time.time()+60):raise RuntimeError('Authenticated live private budget window required')
 private=Path('/home/unreal/.sub01-private')
 if any((private/n).exists()for n in('native-viewer-capture-enabled','native-viewer-input-enabled')):
  raise RuntimeError('Viewer grants must be revoked before Editor import')
 for proc in Path('/proc').iterdir():
  if not proc.name.isdigit():continue
  try:
   args=(proc/'cmdline').read_bytes().split(b'\0');state=(proc/'stat').read_text().rsplit(')',1)[1].split()[0]
   if state!='Z'and args and args[0]==b'/workspace/sub01-private-recovered-engine/Engine/Binaries/Linux/UnrealEditor-Cmd'and b'-game'in args:
    raise RuntimeError('Owned Game must be absent; sole Editor only')
  except OSError:pass


def run(dry_run=True):
 import unreal as u
 from unreal_import_real_wc import owned_geometry,expected_triangles
 from unreal_remove_frame_backings import native_triangles,same_triangles
 from unreal_import_real_linea140 import verify_materials
 from unreal_extend_private_entry import world_bounds
 from unreal_owned_import_cleanup import detach_added
 guard();source=ROOT/'reference-entry.glb';source_report=json.loads((ROOT/'source-report.json').read_text());doc,blob=validate_source(source,source_report)
 project=Path(u.Paths.project_dir()).resolve();home=project/'SourceAssets/full-home.glb'
 if project!=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab')or hashlib.sha256(home.read_bytes()).hexdigest()!=HOME_SHA:
  raise RuntimeError('Exact private recovered project and home source required')
 world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
 if not world or world.get_path_name().split('.',1)[0]!='/Game/Sub01Home/ActualHome':raise RuntimeError('ActualHome must already be loaded')
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors)
 if any(a.get_actor_label().startswith(PREFIX)for a in actors):raise RuntimeError('Courtyard visual replacement already present; inspect receipt')
 old=[]
 for label,wanted in OLD.items():
  found=[a for a in actors if a.get_actor_label()==label]
  if len(found)!=1:raise RuntimeError('Exact existing courtyard actor missing '+label)
  a=found[0];cs=a.get_components_by_class(u.StaticMeshComponent)
  if len(cs)!=1 or not a.get_actor_enable_collision():raise RuntimeError('Exact active support/barrier actor required')
  c=cs[0];mesh=c.get_editor_property('static_mesh');actual=world_bounds(u,c)
  if (not mesh or mesh.get_path_name()!='/Engine/BasicShapes/Cube.Cube'
      or c.get_collision_enabled()!=u.CollisionEnabled.QUERY_AND_PHYSICS
      or any(abs(actual[key][i]-wanted[j][i])>.001 for j,key in enumerate(('min','max'))for i in range(3))):
   raise RuntimeError('Existing exact courtyard support/barrier geometry/collision differs '+label)
  old.append(a)
 expected=expected_hidden(before,old)
 result={'schema':'sub01.reference-entry-native-import.v1','source_sha256':SHA,'dry_run':dry_run,'native_visual_verified':False,'native_walking_verified':False,'panorama_scale_fixed':False,'camera_fov_changed':False,'walking_collision_changed':False}
 if dry_run:return result
 backup=project/'Saved/PrivateMapBackups'/('reference-entry-'+str(time.time_ns()));backup.mkdir(parents=True)
 shutil.copy2(project/'Content/Sub01Home/ActualHome.umap',backup/'ActualHome.umap')
 for name in('__ExternalActors__','__ExternalObjects__'):
  directory=project/'Content'/name/'Sub01Home/ActualHome'
  if directory.exists():shutil.copytree(directory,backup/name)
 destination='/Game/Sub01Home/ReferenceEntry/V_'+SHA[:12]+'/Attempt_'+uuid4().hex
 audit=project/'private-audit';audit.mkdir(exist_ok=True);save_attempted=False
 try:
  manager=u.InterchangeManager.get_interchange_manager_scripted();params=u.ImportAssetParameters();params.set_editor_property('is_automated',True)
  if not manager.import_scene(destination,manager.create_source_data(str(source)),params):raise RuntimeError('Exact courtyard visual import refused')
  manager.wait_until_all_tasks_done(False)
  added=[a for a in eas.get_all_level_actors()if a.get_path_name()not in before]
  for a in added:a.set_actor_hidden_in_game(True);a.set_actor_enable_collision(False)
  if snapshot(u,actors)!=before:raise RuntimeError('Import altered an original actor before visual retirement')
  bindings={};by={}
  for a in added:
   for c in a.get_components_by_class(u.StaticMeshComponent):
    mesh=c.get_editor_property('static_mesh')
    if mesh and mesh.get_path_name().startswith(destination+'/'):
     for key in{mesh.get_name(),a.get_actor_label()}:
      if key in NAMES:by.setdefault(key,[]).append((a,c))
  parts=[];materials=[];total=0;assigned_paths=[]
  for ni,n in enumerate(doc['nodes']):
   if'mesh'not in n:continue
   found=by.get(n['name'],[])
   if len(found)!=1:raise RuntimeError('Exact unique source courtyard part required '+n['name'])
   a,c=found[0]
   if len(a.get_components_by_class(u.StaticMeshComponent))!=1:raise RuntimeError('Standalone exact source courtyard component required')
   owned_geometry(u,c.get_editor_property('static_mesh'),destination)
   expected_surface=expected_triangles(doc,blob,ni);actual=native_triangles(u,c)
   if not same_triangles(expected_surface,actual,tolerance=.0001):raise RuntimeError('Native courtyard triangles differ from complete source '+n['name'])
   source_material=doc['materials'][doc['meshes'][n['mesh']]['primitives'][0]['material']]
   binding=assigned_material_binding(c,source_material,destination)
   materials+=verify_materials(u,[c],{'materials':[source_material]},destination,material_bindings=binding)
   assigned_paths+=list(binding.values());bindings[n['name']]=binding
   c.set_collision_profile_name('NoCollision');c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
   if c.get_collision_enabled()!=u.CollisionEnabled.NO_COLLISION:raise RuntimeError('New visual part must have no collision')
   a.set_actor_label(n['name']);parts.append((a,c));total+=len(actual)
  if len(parts)!=4 or total!=19252 or len(set(assigned_paths))!=4 or snapshot(u,actors)!=before:
   raise RuntimeError('Complete four-part geometry/PBR and unchanged original actors required')
  if not u.EditorAssetLibrary.save_directory(destination,only_if_is_dirty=False,recursive=True):raise RuntimeError('Owned courtyard assets save failed')
  for a in old:a.set_actor_hidden_in_game(True);a.set_is_temporarily_hidden_in_editor(True)
  for a,c in parts:a.set_actor_hidden_in_game(False)
  if snapshot(u,actors)!=expected:raise RuntimeError('Only four original visibility flags may change; collision/geometry/materials must remain exact')
  guard();result.update({'owned_destination':destination,'backup':str(backup),'complete_native_triangles':total,'materials':materials,'source_node_assigned_materials':bindings,'parts':[{'actor':a.get_path_name(),'component':c.get_path_name(),'collision':str(c.get_collision_enabled())}for a,c in parts],'retired_visual_only':[a.get_path_name()for a in old],'original_collisions_and_all_other_fields_unchanged':True})
  pending=audit/'reference-entry-native-import.pending.json';pending.write_text(json.dumps(result,indent=2)+'\n')
  save_attempted=True
  if not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Courtyard visual map save failed')
  result['saved']=True;pending.write_text(json.dumps(result,indent=2)+'\n');pending.replace(audit/'reference-entry-native-import.json');return result
 except Exception:
  for a in old:
   state=before[a.get_path_name()];a.set_actor_hidden_in_game(state['hidden']);a.set_is_temporarily_hidden_in_editor(state['editor_hidden'])
  detach_added(u,eas,before)
  if snapshot(u,actors)!=before:raise RuntimeError('Courtyard rollback differs from exact original actors; preserve backup')
  if save_attempted and not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Courtyard rollback map save failed')
  raise
