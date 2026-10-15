"""Exact four-part cloth import in the already loaded private ActualHome.

Sole Editor owner only. Keep real mattress, frame, devices and approved stairs.
Source/render validation is separate from native visual acceptance.
"""
import copy,hashlib,json,shutil,struct,time,uuid
from pathlib import Path
SHA='e1c4a48e4d6c391a428a20fa56a5575c50963e08a0a914e2df5c50b6d6fbc2f7'
HOME_SHA='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
NAMES={'Duvet':'SUB01ReferenceBedding_Duvet','Foot throw':'SUB01ReferenceBedding_FootThrow','Pillow 1':'SUB01ReferenceBedding_Pillow1','Pillow 2':'SUB01ReferenceBedding_Pillow2'}
OLD=(263,264)

def prepare(source,target):
 from home_asset_audit import read_gltf
 source=Path(source)
 if hashlib.sha256(source.read_bytes()).hexdigest()!=SHA:raise RuntimeError('Frozen actual cloth bake required')
 doc,blob=read_gltf(source);doc=copy.deepcopy(doc)
 if len(doc.get('nodes',[]))!=4 or {n.get('name')for n in doc['nodes']}!=set(NAMES):raise RuntimeError('Exact4 textile parts required')
 for n in doc['nodes']:
  n['name']=NAMES[n['name']];doc['meshes'][n['mesh']]['name']=n['name']
  ps=doc['meshes'][n['mesh']]['primitives']
  if len(ps)!=1 or 'NORMAL'not in ps[0]['attributes']or 'TEXCOORD_0'not in ps[0]['attributes']:raise RuntimeError('Complete textured source required')
 text=json.dumps(doc,separators=(',',':')).encode();text+=b' '*(-len(text)%4);blob=bytes(blob);blob+=b'\0'*(-len(blob)%4)
 target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
 if target.exists():raise RuntimeError('New prepared source required')
 target.write_bytes(struct.pack('<III',0x46546c67,2,28+len(text)+len(blob))+struct.pack('<II',len(text),0x4e4f534a)+text+struct.pack('<II',len(blob),0x004e4942)+blob)
 return doc,blob

def run(source='/workspace/sub01-home-private/reference-bedding-source-r1/output/bedding.glb',dry_run=True):
 import unreal as u
 from home_asset_audit import read_gltf
 from unreal_import_reference_dressing import fingerprint
 from unreal_import_real_wc import expected_triangles,owned_geometry
 from unreal_remove_frame_backings import native_triangles,same_triangles
 from unreal_import_real_bathroom_pendant import verify_owned_material
 from unreal_owned_import_cleanup import detach_added
 project=Path(u.Paths.project_dir());home=project/'SourceAssets/full-home.glb'
 if hashlib.sha256(home.read_bytes()).hexdigest()!=HOME_SHA:raise RuntimeError('Actual full-home source changed')
 world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
 if not world or world.get_path_name().split('.',1)[0]!='/Game/Sub01Home/ActualHome':raise RuntimeError('ActualHome must already be loaded')
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);original=list(eas.get_all_level_actors());before=fingerprint(u,original)
 if any(a.get_actor_label().startswith('SUB01ReferenceBedding_')for a in original):raise RuntimeError('Bedding already installed; inspect existing receipt')
 olddoc,oldblob=read_gltf(home);old=[]
 for ni in OLD:
  matches=[a for a in original if a.get_name()==f'full-home_node_{ni}']
  if len(matches)!=1:raise RuntimeError('Unique exact original textile actor required')
  actor=matches[0];cs=actor.get_components_by_class(u.StaticMeshComponent)
  if len(cs)!=1 or not same_triangles(expected_triangles(olddoc,oldblob,ni),native_triangles(u,cs[0]),tolerance=.0001):raise RuntimeError('Original textile geometry no longer matches source')
  old.append((actor,cs[0],bool(actor.get_editor_property('hidden')),actor.is_temporarily_hidden_in_editor(),cs[0].get_collision_enabled()))
 prepared=project/'Saved/PrivateImportInputs'/('reference-bedding-'+uuid.uuid4().hex+'.glb');doc,blob=prepare(source,prepared)
 result={'schema':'sub01.reference-bedding-native-import.v1','source_sha256':SHA,'dry_run':dry_run,'native_visual_verified':False,'activity_gates_changed':False,'retired_source_nodes':list(OLD)}
 if dry_run:return result
 backup=project/'Saved/PrivateMapBackups'/('reference-bedding-'+str(time.time_ns()));backup.mkdir(parents=True);shutil.copy2(project/'Content/Sub01Home/ActualHome.umap',backup/'ActualHome.umap')
 dest='/Game/Sub01Home/ReferenceBedding/V_'+SHA[:12]+'/Attempt_'+uuid.uuid4().hex;audit=project/'private-audit';audit.mkdir(exist_ok=True)
 try:
  manager=u.InterchangeManager.get_interchange_manager_scripted();params=u.ImportAssetParameters();params.set_editor_property('is_automated',True)
  if not manager.import_scene(dest,manager.create_source_data(str(prepared)),params):raise RuntimeError('Actual bedding scene import refused')
  manager.wait_until_all_tasks_done(False)
  added=[a for a in eas.get_all_level_actors()if a.get_path_name()not in before]
  for actor in added:actor.set_actor_hidden_in_game(True)
  by={}
  for actor in added:
   for c in actor.get_components_by_class(u.StaticMeshComponent):
    m=c.get_editor_property('static_mesh')
    if m and m.get_path_name().startswith(dest+'/'):by.setdefault(m.get_name(),[]).append((actor,c))
  parts=[];pbr=[];total=0
  for ni,n in enumerate(doc['nodes']):
   matches=by.get(n['name'],[])
   if len(matches)!=1:raise RuntimeError('Unique exact imported bedding part required: '+n['name'])
   actor,c=matches[0];owned_geometry(u,c.get_editor_property('static_mesh'),dest)
   actual=native_triangles(u,c);expected=expected_triangles(doc,blob,ni)
   if not same_triangles(expected,actual,tolerance=.0001):raise RuntimeError('Actual world cloth triangles differ from source')
   material=doc['materials'][doc['meshes'][n['mesh']]['primitives'][0]['material']]
   pbr.append(verify_owned_material(u,c,material,dest));c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION);c.set_cast_shadow(True);actor.set_actor_label(n['name']);parts.append((actor,c));total+=len(actual)
  if len(parts)!=4 or fingerprint(u,original)!=before:raise RuntimeError('Complete4 parts and protected original state required')
  u.EditorAssetLibrary.save_directory(dest,only_if_is_dirty=False,recursive=True)
  for actor,c,_,_,_ in old:actor.set_actor_hidden_in_game(True);actor.set_is_temporarily_hidden_in_editor(True);c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
  for actor,c in parts:actor.set_actor_hidden_in_game(False)
  retained=[a for a in original if a not in [x[0]for x in old]]
  if fingerprint(u,retained)!={k:v for k,v in before.items()if k in {a.get_path_name()for a in retained}}:raise RuntimeError('Protected mattress/frame/other home changed')
  result.update(owned_destination=dest,backup=str(backup),complete_native_triangles=total,parts=[{'actor':a.get_path_name(),'component':c.get_path_name()}for a,c in parts],materials=pbr,protected_originals_unchanged=True,originals_preserved=True)
  pending=audit/'reference-bedding-native-import.pending.json';pending.write_text(json.dumps(result,indent=2)+'\n')
  if not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Native bedding map save failed')
  result['saved']=True;pending.write_text(json.dumps(result,indent=2)+'\n');pending.replace(audit/'reference-bedding-native-import.json');return result
 except Exception:
  for actor,c,h,t,collision in old:actor.set_actor_hidden_in_game(h);actor.set_is_temporarily_hidden_in_editor(t);c.set_collision_enabled(collision)
  detach_added(u,eas,before)
  if fingerprint(u,original)!=before:raise RuntimeError('Bedding rollback failed; preserve map backup and stop')
  u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level();raise
