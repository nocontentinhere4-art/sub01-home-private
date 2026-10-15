"""Hidden WIP review import in the authenticated independent candidate project only.

Does not replace or assign any live/display/held controller, change input, grant
hand contact readiness, or promote the candidate to the public/private live Game.
"""
import copy,hashlib,json,struct,time
from pathlib import Path
from uuid import uuid4
ROOT=Path('/workspace/sub01-home-private/reference-controller-r11/output')
HELD_SHA='18e02de2601f6dca59c336fb3df2154a54f94a5dc73aab6fd951bf2287e35247'
DISPLAY_SHA='70a509ae1bc7be500904f9514758088368f663f1f8bb7f6fb1b4518d7c6d9bd5'
LOD_SHA='1a312ae7bdafd73d837a96b0562d5467624abd2bc0b163856bbb7422f9a11e7e'

def prepare_groups(source,target,prefix):
 """Split source material primitives into owned nodes; binary and PBR stay exact."""
 from home_asset_audit import read_gltf
 doc,blob=read_gltf(Path(source));prepared=copy.deepcopy(doc)
 nodes=[n for n in doc['nodes']if'mesh'in n]
 if len(nodes)!=1 or len(doc['nodes'])!=1 or len(doc['materials'])!=6:raise RuntimeError('One frozen source mesh and six materials required')
 node=nodes[0];primitives=doc['meshes'][node['mesh']]['primitives']
 if len(primitives)!=6:raise RuntimeError('Every source material primitive required')
 prepared['nodes']=[];prepared['meshes']=[]
 for i,primitive in enumerate(primitives):
  name=f'{prefix}{i:02}';n={k:copy.deepcopy(v)for k,v in node.items()if k not in('mesh','name','children')};n.update(mesh=i,name=name)
  prepared['nodes'].append(n);prepared['meshes'].append({'name':name,'primitives':[copy.deepcopy(primitive)]})
 prepared['scenes']=[{'nodes':list(range(6))}];prepared['scene']=0
 raw=json.dumps(prepared,separators=(',',':')).encode();raw+=b' '*(-len(raw)%4);binary=bytes(blob);binary+=b'\0'*(-len(binary)%4)
 target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
 if target.exists():raise RuntimeError('Prepared source must be newly owned')
 target.write_bytes(struct.pack('<III',0x46546c67,2,28+len(raw)+len(binary))+struct.pack('<II',len(raw),0x4e4f534a)+raw+struct.pack('<II',len(binary),0x004e4942)+binary)
 check,payload=read_gltf(target)
 if bytes(payload)!=bytes(blob)or check['materials']!=doc['materials']or any(check['meshes'][i]['primitives'][0]!=p for i,p in enumerate(primitives)):raise RuntimeError('Source binary/PBR/complete primitive content changed')
 return check,payload

def run(dry_run=True):
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard
 from controller_reference_packet import validate_packet
 from unreal_import_reference_entry import snapshot
 from unreal_import_real_wc import owned_geometry,expected_triangles
 from unreal_remove_frame_backings import native_triangles,same_triangles
 from unreal_import_reference_wall_console import positive_triangles
 from unreal_import_real_bathroom_pendant import verify_owned_material
 from unreal_owned_import_cleanup import detach_added
 project=Path(u.Paths.project_dir()).resolve()
 if not active_candidate_guard(project):raise RuntimeError('Only the independently copied authenticated candidate Editor is allowed')
 source=json.loads((ROOT/'source-report.json').read_text());proof=json.loads((ROOT/'exported-source-proof.json').read_text());validate_packet(source,proof,HELD_SHA,DISPLAY_SHA)
 for name,sha in [('controller-r11-held.glb',HELD_SHA),('controller-r11-display.glb',DISPLAY_SHA),('controller-r11-display-lod.glb',LOD_SHA)]:
  if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=sha:raise RuntimeError('Frozen complete controller source differs')
 lod=json.loads((ROOT/'display-lod-proof.json').read_text())
 if(lod.get('schema')!='sub01.reference-controller-r11-display-lod.v1'or lod.get('base_display_sha256')!=DISPLAY_SHA or lod.get('sha256')!=LOD_SHA or lod.get('triangles')!=37964 or abs(lod.get('width_m',0)-.16)>1e-7 or lod.get('material_count')!=6 or lod.get('display_only')is not True or any(lod.get(k)is not False for k in('native_imported','hand_contact_accepted','activity_ready'))):raise RuntimeError('Frozen display-only LOD evidence required')
 result={'schema':'sub01.reference-controller-r11-candidate-import.v1','dry_run':dry_run,'held_sha256':HELD_SHA,'display_sha256':DISPLAY_SHA,'display_lod_sha256':LOD_SHA,'source_wip':True,'remaining_surface_dimples':True,'native_visual_accepted':False,'hand_contact_accepted':False,'activity_ready':False,'current_controller_retired':False,'controller_assignment_changed':False,'live_promotion':False,'new_review_actors_hidden_no_collision':True}
 if dry_run:return result
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors)
 destination='/Game/Sub01Home/ControllerWIP/V_'+HELD_SHA[:12]+'/A_'+uuid4().hex;prepared=project/'Saved/ControllerWIP'/uuid4().hex
 result.update(owned_destination=destination,parts=[])
 try:
  for role,filename,prefix in [('held','controller-r11-held.glb','C11H'),('display_lod','controller-r11-display-lod.glb','C11D')]:
   target=prepared/(role+'.glb');doc,blob=prepare_groups(ROOT/filename,target,prefix);names={n['name']for n in doc['nodes']}
   manager=u.InterchangeManager.get_interchange_manager_scripted();params=u.ImportAssetParameters();params.set_editor_property('is_automated',True)
   if not manager.import_scene(destination+'/'+role,manager.create_source_data(str(target)),params):raise RuntimeError('Candidate source import refused')
   manager.wait_until_all_tasks_done(False);added=[a for a in eas.get_all_level_actors()if a.get_path_name()not in before]
   matches={}
   for a in added:
    a.set_actor_hidden_in_game(True);a.set_is_temporarily_hidden_in_editor(True)
    for c in a.get_components_by_class(u.StaticMeshComponent):
     mesh=c.get_editor_property('static_mesh')
     if not mesh or not mesh.get_path_name().startswith(destination+'/'+role+'/'):continue
     for key in {a.get_actor_label(),mesh.get_name()}:
      if key in names:matches.setdefault(key,{})[c.get_path_name()]=(a,c)
   for ni,node in enumerate(doc['nodes']):
    found=list(matches.get(node['name'],{}).values())
    if len(found)!=1:raise RuntimeError('Exact newly owned complete primitive label required')
    a,c=found[0];mesh=c.get_editor_property('static_mesh');owned_geometry(u,mesh,destination)
    wanted,zero=positive_triangles(expected_triangles(doc,blob,ni));actual=native_triangles(u,c)
    if not same_triangles(wanted,actual,tolerance=.0001):raise RuntimeError('Actual positive source/controller primitive geometry differs')
    primitive=doc['meshes'][node['mesh']]['primitives'][0];material=doc['materials'][primitive['material']]
    pbr=verify_owned_material(u,c,material,destination,source_primitive_verified=True)
    c.set_collision_profile_name('NoCollision');c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
    result['parts'].append({'role':role,'source_node':node['name'],'actor':a.get_path_name(),'component':c.get_path_name(),'mesh':mesh.get_path_name(),'positive_triangles':len(actual),'source_exact_zero_triangle_indices':zero,'pbr':pbr})
  if snapshot(u,actors)!=before:raise RuntimeError('Candidate original actors changed')
  if not u.EditorAssetLibrary.save_directory(destination,only_if_is_dirty=False,recursive=True):raise RuntimeError('Owned candidate controller assets could not save')
  # Imported scene actors were temporary geometry/PBR probes only. Save only owned
  # assets, then remove every new scene actor before any unrelated batch map save.
  detach_added(u,eas,before)
  if snapshot(u,list(eas.get_all_level_actors()))!=before:raise RuntimeError('Asset-only review import left scene state changed')
  if not active_candidate_guard(project):raise RuntimeError('Candidate scope expired before asset receipt')
  for part in result['parts']:part['temporary_actor_destroyed_after_verification']=True
  audit=project/'private-audit';audit.mkdir(exist_ok=True);result.update(saved_assets=True,map_saved=False,protected_candidate_actors_exact=True,all_temporary_review_actors_destroyed=True,complete_candidate_world_snapshot_restored_exact=True)
  (audit/'reference-controller-r11-candidate-import.json').write_text(json.dumps(result,indent=2));return result
 except Exception:
  detach_added(u,eas,before)
  if snapshot(u,actors)!=before:raise RuntimeError('Candidate rollback changed original actors')
  raise
