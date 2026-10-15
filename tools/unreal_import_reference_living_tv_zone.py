"""Replace only the private candidate TV-wall finish and existing media cabinet.

The actual TV screen/case, its input surface, saved Game, devices and other
windows remain unchanged. Real closed source surfaces provide new collision.
"""
from pathlib import Path
import json,hashlib,copy,struct,shutil,time,uuid
ROOT=Path('/workspace/sub01-home-private/reference-living-tv-wall-r3/output')
WALL_SHA='828d7078120975c830db7016152936378617295c86a54cde5b6888b79940bc0a'
CAB_SHA='63e025252dfaa4d0db66800d5b1b36de54d46b61af2bff64e878a39287985979'
MEDIA_SHA='7a27cdf114d219968c7e5aa39f491be2ff979d58d3965344acf0ebdb6a651a96'
RUG_RECEIPT_SHA='a4b1416718bc1d2fff5564537d909e7c342720329f5e6f59f10ff2c0a5ac4b0f'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def prepare(source,target,prefix,split=False):
 from home_asset_audit import read_gltf
 doc,blob=read_gltf(source);d=copy.deepcopy(doc)
 if split:
  nodes=[n for n in doc['nodes']if'mesh'in n];assert len(nodes)==1 and len(doc['nodes'])==1;prims=doc['meshes'][nodes[0]['mesh']]['primitives'];assert len(prims)==5
  d['nodes']=[];d['meshes']=[]
  for i,p in enumerate(prims):
   node={k:copy.deepcopy(v)for k,v in nodes[0].items()if k not in('mesh','name','children')};node.update(name=f'{prefix}{i:02}',mesh=i);d['nodes'].append(node);d['meshes'].append({'name':node['name'],'primitives':[copy.deepcopy(p)]})
  d['scenes']=[{'nodes':list(range(5))}];d['scene']=0
 else:
  assert len(d['nodes'])==9 and all('mesh'in n for n in d['nodes'])
  for i,n in enumerate(d['nodes']):n['name']=f'{prefix}{i:02}';d['meshes'][n['mesh']]['name']=n['name']
 for i,m in enumerate(d['materials']):m['name']=f'{prefix}M{i:02}'
 for i,m in enumerate(d.get('images',[])):m['name']=f'{prefix}T{i:02}'
 raw=json.dumps(d,separators=(',',':')).encode();raw+=b' '*(-len(raw)%4);binary=bytes(blob);binary+=b'\0'*(-len(binary)%4);target.parent.mkdir(parents=True,exist_ok=True);assert not target.exists();target.write_bytes(struct.pack('<III',0x46546c67,2,28+len(raw)+len(binary))+struct.pack('<II',len(raw),0x4e4f534a)+raw+struct.pack('<II',len(binary),0x004e4942)+binary)
 check,payload=read_gltf(target);assert bytes(payload)==bytes(blob);return check,payload

def run(dry_run=True):
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE,SOURCE
 from home_asset_audit import read_gltf
 from unreal_import_reference_entry import snapshot,assigned_material_binding
 from unreal_import_real_wc import owned_geometry,expected_triangles
 from unreal_remove_frame_backings import native_triangles,same_triangles
 from unreal_import_reference_wall_console import positive_triangles
 from unreal_import_real_bathroom_pendant import verify_owned_material
 from unreal_owned_import_cleanup import detach_added
 assert active_candidate_guard();assert sha(ROOT/'living-tv-wall.glb')==WALL_SHA and sha(ROOT/'living-cabinet.glb')==CAB_SHA
 source=json.loads((ROOT/'source-report.json').read_text());assert source['files']['living-tv-wall.glb']==WALL_SHA and source['files']['living-cabinet.glb']==CAB_SHA and source['existing_root_spindles_rigid_delta_applied']==2 and len(source['cabinet_component_bounds'])>30
 assert 1.829<source['cabinet_bounds_blender_m'][1][1]-source['cabinet_bounds_blender_m'][0][1]<1.832
 # A source-only BVH cannot decide if an older generated rug is active. Require
 # its exact saved retirement receipt AND actual current component state.
 retirement=SOURCE/'private-audit/rejected-generated-decor-hidden.json';assert sha(retirement)==RUG_RECEIPT_SHA;retired=json.loads(retirement.read_text());rugpath='/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.full-home_node_61';assert rugpath in retired['removed_actor_paths']
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());assert not any(a.get_actor_label().startswith(('LTW','LTC'))for a in actors),'Living zone already staged; inspect receipt';before=snapshot(u,actors);by={a.get_path_name():a for a in actors};rug=by[rugpath];cs=rug.get_components_by_class(u.StaticMeshComponent);assert len(cs)==1 and cs[0].get_editor_property('static_mesh').get_path_name()=='/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Mesh_45.Mesh_45'and rug.get_editor_property('hidden')and cs[0].get_collision_enabled()==u.CollisionEnabled.NO_COLLISION
 # Full explicit geometry proof is pinned to final R3 source; exact boundary
 # wall attachments are classified by separating halfspaces, never filtered.
 proof=json.loads((ROOT/'independent-bvh-proof.json').read_text());assert proof.get('native_import_permitted')is True,'Independent final source geometry / retired-rug proof required'
 assert proof.get('wall_sha256')==WALL_SHA and proof.get('cabinet_sha256')==CAB_SHA and proof.get('rug_retirement_receipt_sha256')==RUG_RECEIPT_SHA
 media=json.loads((CANDIDATE/'private-audit/reference-media-native-import.json').read_text());assert media['saved']and media['source_sha256']==MEDIA_SHA and len(media['parts'])==11
 olddoc,oldblob=read_gltf(Path('/workspace/sub01-home-private/real-media-console-source-r1/output/media-console-side-native.glb'));oldcab=[]
 for i in range(5):
  item=media['parts'][i];a=by[item['actor']];cs=a.get_components_by_class(u.StaticMeshComponent);assert len(cs)==1 and cs[0].get_path_name()==item['component'];c=cs[0];assert not a.get_editor_property('hidden')and c.get_material(0).get_name()==f'RM{i:02}'
  expected,_=positive_triangles(expected_triangles(olddoc,oldblob,i));assert same_triangles(expected,native_triangles(u,c),.0001);oldcab.append((a,c))
 windows=[]
 for i in range(38,74):
  matches=[a for a in actors if a.get_actor_label()==f'SUB01_RealWindow_Part_{i}'];assert len(matches)==1;a=matches[0];cs=a.get_components_by_class(u.StaticMeshComponent);assert len(cs)==1;mesh=cs[0].get_editor_property('static_mesh');assert mesh and mesh.get_path_name().startswith('/Game/Sub01Home/ResidentialWindows/V_7119c36483ec/')and not a.get_editor_property('hidden');windows.append(a)
 result={'schema':'sub01.reference-living-tv-zone-candidate.v1','dry_run':dry_run,'wall_sha256':WALL_SHA,'cabinet_sha256':CAB_SHA,'rug_retirement_receipt_sha256':RUG_RECEIPT_SHA,'actual_old_rug_hidden_no_collision':True,'tv_screen_case_and_input_unchanged':True,'live_game_changed':False,'new_wall_has_real_blocking_geometry':True,'native_visual_accepted':False,'old_cabinet_only_retirement':5,'middle_window_visual_only_retirement':36}
 if dry_run:return result
 backup=CANDIDATE/'Saved/PrivateMapBackups'/('living-tv-zone-'+str(time.time_ns()));backup.mkdir(parents=True);shutil.copy2(CANDIDATE/'Content/Sub01Home/ActualHome.umap',backup/'ActualHome.umap')
 destination='/Game/Sub01Home/LivingTVZone/V_'+CAB_SHA[:12]+'/Attempt_'+uuid.uuid4().hex;prepared=CANDIDATE/'Saved/LivingTVZone'/uuid.uuid4().hex;parts=[];save_attempted=False
 try:
  for role,filename,prefix,split in [('wall','living-tv-wall.glb','LTW',False),('cabinet','living-cabinet.glb','LTC',True)]:
   target=prepared/filename;doc,blob=prepare(ROOT/filename,target,prefix,split);names={n['name']for n in doc['nodes']};manager=u.InterchangeManager.get_interchange_manager_scripted();params=u.ImportAssetParameters();params.set_editor_property('is_automated',True);assert manager.import_scene(destination+'/'+role,manager.create_source_data(str(target)),params);manager.wait_until_all_tasks_done(False)
   matches={}
   for a in eas.get_all_level_actors():
    if a.get_path_name()in before:continue
    a.set_actor_hidden_in_game(True)
    for c in a.get_components_by_class(u.StaticMeshComponent):
     mesh=c.get_editor_property('static_mesh')
     if mesh and mesh.get_path_name().startswith(destination+'/'+role+'/'):
      for key in{a.get_actor_label(),mesh.get_name()}:
       if key in names:matches.setdefault(key,{})[c.get_path_name()]=(a,c)
   for i,node in enumerate(doc['nodes']):
    pairs=list(matches.get(node['name'],{}).values());assert len(pairs)==1;a,c=pairs[0];owned_geometry(u,c.get_editor_property('static_mesh'),destination);expected,zero=positive_triangles(expected_triangles(doc,blob,i));actual=native_triangles(u,c);assert same_triangles(expected,actual,.0001),'Actual full positive source geometry differs: '+node['name'];material=doc['materials'][doc['meshes'][node['mesh']]['primitives'][0]['material']];binding=assigned_material_binding(c,material,destination);pbr=verify_owned_material(u,c,material,destination,source_primitive_verified=True);c.set_collision_profile_name('BlockAll');c.set_collision_enabled(u.CollisionEnabled.QUERY_AND_PHYSICS);a.set_actor_enable_collision(True);c.set_cast_shadow(True);parts.append((a,c,{'role':role,'source_node':node['name'],'actor':a.get_path_name(),'component':c.get_path_name(),'mesh':c.get_editor_property('static_mesh').get_path_name(),'triangles':len(actual),'pbr':pbr,'exact_zero_source_indices':zero}))
  assert len(parts)==14 and snapshot(u,actors)==before
  assert u.EditorAssetLibrary.save_directory(destination,only_if_is_dirty=False,recursive=True)
  expected=copy.deepcopy(before)
  for a,c in oldcab:
   a.set_actor_hidden_in_game(True);a.set_is_temporarily_hidden_in_editor(True);c.set_collision_profile_name('NoCollision');c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION);row=expected[a.get_path_name()];row['hidden']=True;row['editor_hidden']=True;item=next(x for x in row['components']if x['path']==c.get_path_name());item['profile']='NoCollision';item['collision']=str(u.CollisionEnabled.NO_COLLISION)
  for a in windows:a.set_actor_hidden_in_game(True);a.set_is_temporarily_hidden_in_editor(True);expected[a.get_path_name()]['hidden']=True;expected[a.get_path_name()]['editor_hidden']=True
  for a,c,row in parts:a.set_actor_hidden_in_game(False);c.set_visibility(True)
  assert snapshot(u,actors)==expected and active_candidate_guard()
  result.update(owned_destination=destination,parts=[row for a,c,row in parts],backup=str(backup),protected_other_actors_exact=True,original_window_collision_retained_exact=True,original_tv_plane_unchanged=True)
  save_attempted=True;assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level();result.update(saved=True,map_sha256=sha(CANDIDATE/'Content/Sub01Home/ActualHome.umap'));(CANDIDATE/'private-audit/reference-living-tv-zone-native.json').write_text(json.dumps(result,indent=2)+'\n');return result
 except Exception:
  # Restore all changed original state from the immutable pre-operation snapshot.
  for a,c in oldcab:
   prior=before[a.get_path_name()];item=next(x for x in prior['components']if x['path']==c.get_path_name());a.set_actor_hidden_in_game(prior['hidden']);a.set_is_temporarily_hidden_in_editor(prior['editor_hidden']);c.set_collision_profile_name(item['profile']);key=item['collision'].split('CollisionEnabled.',1)[1].split(':',1)[0].split('>',1)[0];c.set_collision_enabled(getattr(u.CollisionEnabled,key))
  for a in windows:a.set_actor_hidden_in_game(before[a.get_path_name()]['hidden']);a.set_is_temporarily_hidden_in_editor(before[a.get_path_name()]['editor_hidden'])
  detach_added(u,eas,before);assert snapshot(u,actors)==before
  if save_attempted:assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
  raise
