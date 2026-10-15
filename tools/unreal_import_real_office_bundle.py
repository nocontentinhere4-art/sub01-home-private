"""One sole-owner warm-Editor transaction for the complete authentic office bundle.

All imports/native geometry/material/support checks happen before original desk/
shelves, lamp or46 owned books move. One final map save. Failure restores every
original actor/component reference and removes only actors/assets newly owned by
this transaction. No level load, pod operation, controller edit or restart.
"""
import copy,hashlib,json,sys
from pathlib import Path
from home_asset_audit import read_gltf
from unreal_import_reference_dressing import fingerprint
from unreal_import_real_linea140 import run as stage_desk,surface,verify_materials,close,vec
from prepare_real_office_bundle import BOOKS_SHA,SHELF_SHA
from real_office_plant import native_preflight as plant_preflight
LEVEL='/Game/Sub01Home/ActualHome'


def verify_native_structural_union(u,actors):
 """Read actual saved receipt/bytes and native bindings; no staging/mutations."""
 project=Path(u.Paths.project_dir());receipt_path=project/'private-audit/native-structural-lamp-union.json'
 receipt=json.loads(receipt_path.read_text());source=Path('/workspace/sub01-home-private/structural-rails-20261014/structural-lamp-union-remainder-only.glb')
 digest=hashlib.sha256(source.read_bytes()).hexdigest();roundtrip=receipt.get('roundtrip',{})
 if receipt.get('source_sha256')!='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b' or receipt.get('union_sha256')!=digest or not roundtrip.get('ok') or roundtrip.get('replacement_sha256')!=digest or len(roundtrip.get('checks',[]))!=1 or roundtrip['checks'][0].get('triangle_count')!=160:raise RuntimeError('Actual saved exact160 union receipt/byte proof unavailable')
 def unique(predicate,label):
  matches=[a for a in actors if predicate(a)]
  if len(matches)!=1:raise RuntimeError('Exact structural native prerequisite identity differs '+label)
  return matches[0]
 batches=[]
 for node in (162,163):
  actor=unique(lambda a:a.get_name()==f'full-home_node_{node}',str(node));components=actor.get_components_by_class(u.StaticMeshComponent)
  if len(components)!=1 or components[0].get_editor_property('static_mesh').get_path_name()!=f'/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Mesh_{node-41}.Mesh_{node-41}' or components[0].get_num_materials()!=1 or components[0].get_material(0).get_path_name()!=f'/Game/Sub01Home/ImportedScene/full-home/Materials/Material_{1 if node==162 else 8}.Material_{1 if node==162 else 8}' or not bool(actor.get_editor_property('hidden')) or components[0].get_collision_enabled()!=u.CollisionEnabled.NO_COLLISION:raise RuntimeError('Original162/163 must be hidden and NoCollision before office staging')
  batches.append(actor)
 actor=unique(lambda a:a.get_actor_label()=='SUB01_VerifiedLampUnion160_'+digest[:12],'owned160 actor');components=actor.get_components_by_class(u.StaticMeshComponent)
 if len(components)!=1:raise RuntimeError('Exact owned160 component count differs')
 component=components[0];mesh=component.get_editor_property('static_mesh')
 if component.get_path_name()!=receipt.get('new_union_component') or not mesh or not mesh.get_path_name().startswith('/Game/Sub01Home/StructuralLampUnionMeshOnly/V_'+digest[:12]+'/') or bool(actor.get_editor_property('hidden')) or not bool(component.get_editor_property('visible')) or component.get_collision_enabled()!=u.CollisionEnabled.QUERY_AND_PHYSICS or str(component.get_collision_profile_name())!='BlockAll':raise RuntimeError('Exact owned160 native geometry is not active/physical')
 points,count=surface(u,component)
 if count!=160 or component.get_num_materials()!=1 or component.get_material(0)!=batches[1].get_components_by_class(u.StaticMeshComponent)[0].get_material(0):raise RuntimeError('Owned160 triangle/material binding differs saved exact union')
 from structural_rail_source_patch import accessor
 from home_asset_audit import node_matrix,IDENTITY
 doc,binary=read_gltf(source)
 if len(doc['nodes'])!=1 or node_matrix(doc['nodes'][0])!=IDENTITY:raise RuntimeError('Actual160 source identity transform differs')
 source_points=accessor(doc,binary,doc['meshes'][0]['primitives'][0]['attributes']['POSITION'])
 expected=[[(min if side==0 else max)(p[k]for p in source_points)*100 for k in(0,2,1)]for side in(0,1)]
 actual=[[(min if side==0 else max)(p[k]for p in points)for k in range(3)]for side in(0,1)]
 if not all(close(a,b)for a,b in zip(actual,expected)):raise RuntimeError('Owned160 actual native world bounds differ exact source bytes')
 old_path=receipt.get('old_owned_remainder_hidden')
 if not old_path:raise RuntimeError('Saved union lacks exact prior200 identity')
 for old in actors:
  prior=old.get_path_name()==old_path or (old.get_actor_label().startswith('SUB01_VerifiedRails_')and 'PreservedSource_163_0'in old.get_actor_label())
  if not prior:continue
  comps=old.get_components_by_class(u.StaticMeshComponent)
  if len(comps)!=1 or '/StructuralRails/V_d586193fee24/'not in comps[0].get_editor_property('static_mesh').get_path_name() or not bool(old.get_editor_property('hidden')) or comps[0].get_collision_enabled()!=u.CollisionEnabled.NO_COLLISION:raise RuntimeError('Old200 remainder must be absent or hidden/NoCollision before office staging')
 return {'union_sha256':digest,'exact_native_component':component.get_path_name(),'native_triangles':count,'actual_native_bounds_cm':actual,'old162163_hidden_nocollision':True,'old200_remainder_inactive':True,'mutations':0}


def run(root,dry_run=True,u=None):
 if u is None:import unreal as u
 if sys.modules.get('unreal') is u:
  from unreal_editor_queue_refresh import refresh
  refresh()  # Reviewed same-instance queue refresh; helper authenticates ownership/guard.
 # A warm Editor retains dependency modules across reviewed source retries.
 import importlib,real_office_plant
 plant_preflight=importlib.reload(real_office_plant).native_preflight
 root=Path(root);proof=json.loads((root/'office-bundle.json').read_text())
 if proof.get('schema')!='sub01.real-office-bundle.v1' or not proof.get('source_triangle_collision_proof',{}).get('ok') or not proof.get('whole_book_geometry_pbr_preserved') or proof.get('complete_original_book_glb_sha256')!=BOOKS_SHA or len(proof.get('books',[]))!=46 or proof.get('hide_only_source_actor_nodes')!=[181,182,190,191,259]:raise RuntimeError('Actual coherent whole office source proof unavailable')
 mount=proof['desk'].get('lamp_mount',{});pose=mount.get('posed_lamp',{})
 if mount.get('mount_mechanism')!='C-clamp-side-edge' or mount.get('opened_hardware_source_nodes')!=[] or pose.get('triangle_count')!=24102 or pose.get('rigid_screw_triangle_count')!=1100 or not pose.get('other_positions_normals_uv_indices_unchanged') or hashlib.sha256((root/'lamp-posed.glb').read_bytes()).hexdigest()!=pose.get('sha256'):raise RuntimeError('Actual complete rigid C-clamp derivative proof unavailable')
 plantproof=proof.get('plant',{})
 if plantproof.get('root_source_node')!=225 or plantproof.get('mesh_source_nodes')!=[221,222,223,224] or plantproof.get('rigid_delta_ue_cm')!=[-40.,0.,-1.] or not plantproof.get('geometry_uv_pbr_unchanged') or not plantproof.get('exact_base_contact_faces') or not plantproof.get('source_collision_proof',{}).get('ok'):raise RuntimeError('Actual complete genuine office plant support/rigid proof unavailable')
 shelfpath=root/'shelves.glb';digest=hashlib.sha256(shelfpath.read_bytes()).hexdigest()
 if digest!=proof['shelf']['sha256'] or proof['shelf']['source_sha256']!=SHELF_SHA or not proof['shelf']['source_binary_unchanged']:raise RuntimeError('Actual complete shelf source identity differs')
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
 if not world or world.get_path_name().split('.',1)[0]!=LEVEL:raise RuntimeError('Already loaded ActualHome required; no new Editor or level load')
 original=list(eas.get_all_level_actors());plantctx=plant_preflight(u,original,plantproof,surface,close);union_prerequisite=verify_native_structural_union(u,original);before=fingerprint(u,original)
 def exact(predicate,description):
  rows=[a for a in original if predicate(a)]
  if len(rows)!=1:raise RuntimeError('Actual original binding is not unique '+description)
  return rows[0]
 old_shelves=[exact(lambda a:a.get_name()==f'full-home_node_{i}',str(i))for i in (190,191)]
 for a,name in zip(old_shelves,('Oak_shelves','Shelf_hardware')):
  comps=a.get_components_by_class(u.StaticMeshComponent)
  if a.get_actor_label()!=name or len(comps)!=1 or not comps[0].get_editor_property('static_mesh').get_path_name().startswith('/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/'):raise RuntimeError('Exact original shelf source identity differs; no shared batch hide')
 books=[]
 for plan in proof['books']:
  actor=exact(lambda a:a.get_actor_label()==plan['id'],plan['id']);comps=actor.get_components_by_class(u.StaticMeshComponent)
  if len(comps)!=1 or not comps[0].get_editor_property('static_mesh').get_path_name().startswith('/Game/Sub01Home/RealBooks/V_'+BOOKS_SHA[:12]+'/'):raise RuntimeError('Book is not exact COMPLETE owned source version '+plan['id'])
  points,count=surface(u,comps[0]);bounds=[[min(p[a]for p in points)for a in range(3)],[max(p[a]for p in points)for a in range(3)]]
  if count!=plan['actual_source_triangle_count'] or not all(close(a,[v*100 for v in b])for a,b in zip(bounds,plan['old_bounds_ue_m'])):raise RuntimeError('Actual complete book geometry differs source '+plan['id'])
  if not close(vec(actor.get_actor_location()),plan['old_pivot_ue_cm']):raise RuntimeError('Actual owned book pivot differs source; no guessed relative transform')
  books.append((actor,comps[0],plan))
 desk_preflight=stage_desk(root/'desk.glb',dry_run=True,u=u)
 if dry_run:return {'schema':'sub01.real-office-native-preflight.v1','desk':desk_preflight,'complete_native_books_verified':46,'old_shelf_paths':[a.get_path_name()for a in old_shelves],'structural_union_prerequisite':union_prerequisite,'plant_native_preflight':{'root':plantctx['root'].get_path_name(),'members':[a.get_path_name()for a,c,p in plantctx['rows']],'move_once':[a.get_path_name()for a in plantctx['move']],'rigid_delta_ue_cm':plantproof['rigid_delta_ue_cm'],'watering_native_activity_verified':False,'obsolete259_actual_hidden_before':plantctx['oldbase_actual_hidden_before'],'obsolete259_actual_collision_before':plantctx['oldbase_actual_collision_before']},'mutations':0}
 states=[]
 for actor in original:
  comps=[(c,c.get_world_transform(),c.get_editor_property('static_mesh'),list(c.get_materials()),list(c.get_editor_property('component_tags')),bool(c.get_editor_property('visible')),c.get_collision_enabled(),c.get_collision_profile_name())for c in actor.get_components_by_class(u.StaticMeshComponent)]
  states.append((actor,actor.get_actor_transform(),actor.get_actor_label(),bool(actor.get_editor_property('hidden')),comps))
 light_values={c.get_path_name():c.get_editor_property('intensity')for a in original for c in a.get_components_by_class(u.LightComponent)}
 dest='/Game/Sub01Home/RealSteelShelves/V_'+digest[:12];deskdigest=proof['desk']['output_sha256'];deskdest='/Game/Sub01Home/RealLinea140/V_'+deskdigest[:12]
 if u.EditorAssetLibrary.does_directory_exist(dest)or u.EditorAssetLibrary.does_directory_exist(deskdest):raise RuntimeError('This office asset version already exists; preserve it and inspect its receipt rather than duplicate import')
 try:
  desk_result,ctx=stage_desk(root/'desk.glb',dry_run=False,u=u,defer_activation=True)
  manager=u.InterchangeManager.get_interchange_manager_scripted();params=u.ImportAssetParameters();params.set_editor_property('is_automated',True);data=manager.create_source_data(str(shelfpath))
  if not manager.import_scene(dest,data,params):raise RuntimeError('Authentic shelf scene import refused')
  manager.wait_until_all_tasks_done(False)
  added=[a for a in eas.get_all_level_actors()if a.get_path_name()not in before]
  if fingerprint(u,original)!=before:raise RuntimeError('Whole office imports changed originals before activation')
  shelf_components=[];shelf_points={};alltris=0
  for label in proof['shelf']['native_actor_labels']:
   found=[a for a in added if a.get_actor_label()==label]
   if len(found)!=1:raise RuntimeError('Authentic shelf source UID not unique '+label)
   comps=found[0].get_components_by_class(u.StaticMeshComponent)
   if len(comps)!=1 or not comps[0].get_editor_property('static_mesh').get_path_name().startswith(dest+'/'):raise RuntimeError('Shelf reused unowned existing geometry')
   pts,count=surface(u,comps[0]);alltris+=count;shelf_points[label]=pts;shelf_components.append(comps[0])
   if count!=proof['shelf']['triangles_per_authentic_shelf']:raise RuntimeError('Native shelf lost source triangles')
  shelfdoc,_=read_gltf(shelfpath);materials=verify_materials(u,shelf_components,shelfdoc,dest)
  for c in shelf_components:
   body=c.get_editor_property('static_mesh').get_editor_property('body_setup')
   if not body:raise RuntimeError('Actual authentic shelf physical collision absent')
   body.set_editor_property('collision_trace_flag',u.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE);c.set_collision_profile_name('BlockAll');c.set_collision_enabled(u.CollisionEnabled.QUERY_AND_PHYSICS)
  # Actual native broad wood-plane vertices must match every source support height.
  for board in proof['shelf']['boards']:
   pts=shelf_points[proof['shelf']['native_actor_labels'][board['instance']]];height=board['top_ue_m']*100
   plane=[p for p in pts if abs(p[2]-height)<.005]
   if len(plane)<4:raise RuntimeError('Actual native board height/support geometry missing')
   a,b=board['xy_bounds_m']
   if not close([min(p[0]for p in plane),min(p[1]for p in plane)],[a[0]*100,a[1]*100]) or not close([max(p[0]for p in plane),max(p[1]for p in plane)],[b[0]*100,b[1]*100]):raise RuntimeError('Actual native full board footprint differs source')
  if fingerprint(u,original)!=before:raise RuntimeError('Owned PBR/collision setup changed originals before activation')
  # Activation starts only after ALL native/source geometry, PBR and board proofs.
  for hardware in ctx['mount']['opened_hardware_source_nodes']:
   cap,cc,_=ctx['by_node'][hardware];cap.set_actor_hidden_in_game(True);cc.set_visibility(False);cc.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
  mount=ctx['mount'];ctx['lamp_component'].set_static_mesh(ctx['posed_mesh'])
  for slot,material in enumerate(mount['actual_saved_material_paths']):ctx['lamp_component'].set_material(slot,u.EditorAssetLibrary.load_asset(material))
  ctx['lamp'].set_actor_location(u.Vector(*mount['new_origin_ue_cm']),False,False);ctx['light'].set_actor_location(u.Vector(*[vec(ctx['light'].get_actor_location())[a]+mount['new_bulb_ue_cm'][a]-vec(ctx['lights'][0].get_world_location())[a]for a in range(3)]),False,False)
  if not close(vec(ctx['lights'][0].get_world_location()),mount['new_bulb_ue_cm']):raise RuntimeError('Actual paired light did not reach verified bulb')
  lamp_points,count=surface(u,ctx['lamp_component']);lamp_bounds=[[min(p[a]for p in lamp_points)for a in range(3)],[max(p[a]for p in lamp_points)for a in range(3)]]
  if count!=24102 or not all(close(a,[v*100 for v in b])for a,b in zip(lamp_bounds,mount['lamp_world_aabb_m'])):raise RuntimeError('Actual posed C-clamp geometry/support bounds differ source')
  if [m.get_path_name()for m in ctx['lamp_component'].get_materials()]!=mount['actual_saved_material_paths']:raise RuntimeError('Posed clamp altered verified old PBR bindings')
  # Move the exact genuine225 group once; independent children each move once.
  plant_old={a.get_path_name():vec(a.get_actor_location())for a,c,p in plantctx['rows']}
  for actor in plantctx['move']:
   location=vec(actor.get_actor_location());actor.set_actor_location(u.Vector(*[location[a]+plantproof['rigid_delta_ue_cm'][a]for a in range(3)]),False,False)
  for actor,c,plan in plantctx['rows']:
   delta=[vec(actor.get_actor_location())[a]-plant_old[actor.get_path_name()][a]for a in range(3)]
   if not close(delta,plantproof['rigid_delta_ue_cm']):raise RuntimeError('Actual plant hierarchy double/missed rigid translation')
   points,count=surface(u,c);box=[[min(p[a]for p in points)for a in range(3)],[max(p[a]for p in points)for a in range(3)]]
   if count!=plan['source_triangle_count']or not all(close(a,[v*100 for v in b])for a,b in zip(box,plan['new_bounds_ue_m'])):raise RuntimeError('Actual whole plant tabletop/support bounds differ source')
   actual=fingerprint(u,[actor])[actor.get_path_name()];expected=copy.deepcopy(before[actor.get_path_name()])
   for field in(actual['transform'],*[r['transform']for r in actual['components']]):
    for a in range(3):field['translation'][a]-=plantproof['rigid_delta_ue_cm'][a]
   for got,want in[(actual['transform'],expected['transform'])]+[(g['transform'],w['transform'])for g,w in zip(actual['components'],expected['components'])]:
    if not close(got['translation'],want['translation'])or not close(got['rotation'],want['rotation'],1e-5)or not close(got['scale'],want['scale'],1e-5):raise RuntimeError('Genuine plant pose changed beyond rigid translation')
    got.update(want)
   if actual!=expected:raise RuntimeError('Genuine plant PBR/mesh/collision changed')
  book_rows=[]
  for actor,c,plan in books:
   location=vec(actor.get_actor_location());new=[location[a]+plan['delta_ue_cm'][a]for a in range(3)];actor.set_actor_location(u.Vector(*new),False,False)
   pts,count=surface(u,c);actual=[[min(p[a]for p in pts)for a in range(3)],[max(p[a]for p in pts)for a in range(3)]]
   if not all(close(a,[v*100 for v in b])for a,b in zip(actual,plan['new_bounds_ue_m'])):raise RuntimeError('Actual book retarget missed physical board '+plan['id'])
   expected=copy.deepcopy(before[actor.get_path_name()])
   for a in range(3):expected['transform']['translation'][a]+=plan['delta_ue_cm'][a]
   for row in expected['components']:
    for a in range(3):row['transform']['translation'][a]+=plan['delta_ue_cm'][a]
   actual_fingerprint=fingerprint(u,[actor])[actor.get_path_name()]
   # Float transforms may differ by ulps; compare exact non-transform fields and bounded poses.
   for got,want in [(actual_fingerprint['transform'],expected['transform'])]+[(g['transform'],w['transform'])for g,w in zip(actual_fingerprint['components'],expected['components'])]:
    if not close(got['translation'],want['translation'])or not close(got['rotation'],want['rotation'],1e-5)or not close(got['scale'],want['scale'],1e-5):raise RuntimeError('Book pose changed beyond proven rigid translation')
   actual_fingerprint['transform']=expected['transform']
   for got,want in zip(actual_fingerprint['components'],expected['components']):got['transform']=want['transform']
   if actual_fingerprint!=expected:raise RuntimeError('Book mesh/PBR/collision changed during rigid retarget')
   book_rows.append({'id':plan['id'],'actor':actor.get_path_name(),'new_bounds_cm':actual,'source_geometry_unchanged':True})
  old_targets=ctx['old']+old_shelves+[plantctx['oldbase']]
  for actor in old_targets:
   actor.set_actor_hidden_in_game(True)
   for c in actor.get_components_by_class(u.StaticMeshComponent):c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
  allowed={a.get_path_name()for a in old_targets+[ctx['lamp'],ctx['light']]+[a for a,c,p in books]+[a for a,c,p in plantctx['rows']]+[plantctx['root']]}
  if fingerprint(u,[a for a in original if a.get_path_name()not in allowed])!={k:v for k,v in before.items()if k not in allowed}:raise RuntimeError('Office activation changed protected stairs/chair/devices/screens/controller geometry')
  if {c.get_path_name():c.get_editor_property('intensity')for a in original for c in a.get_components_by_class(u.LightComponent)}!=light_values:raise RuntimeError('Office placement changed existing lamp switch intensity state')
  for actor,transform,label,hidden,comps in states:
   expected=True if actor in old_targets else hidden
   if bool(actor.get_editor_property('hidden'))!=expected:raise RuntimeError('Office activation changed unplanned visibility')
  if not u.EditorAssetLibrary.save_directory(ctx['lampdest'],only_if_is_dirty=False,recursive=True)or not u.EditorAssetLibrary.save_directory(deskdest,only_if_is_dirty=False,recursive=True) or not u.EditorAssetLibrary.save_directory(dest,only_if_is_dirty=False,recursive=True) or not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Whole office save failed')
  result={'schema':'sub01.real-office-native-import.v1','source_bundle':proof,'structural_union_prerequisite':union_prerequisite,'desk':desk_result,'shelf_native_triangles':alltris,'plant':plantproof,'plant_native_world_deltas_verified':4,'plant_parent225_relocated':True,'watering_native_activity_verified':False,'shelf_materials':materials,'books':book_rows,'hidden_originals':[a.get_path_name()for a in old_targets],'native_protected_original_fingerprints_verified':len(before)-len(allowed),'native_visual_verified':False,'contact_limit':'Original device foot penetration is unchanged at actual baseline top; not described as perfect.'}
  (root/'native-office-bundle.json').write_text(json.dumps(result,indent=2)+'\n');return result
 except Exception:
  def depth(actor):
   level=0;parent=actor.get_attach_parent_actor();seen=set()
   while parent:
    path=parent.get_path_name()
    if path in seen:raise RuntimeError('Native attachment cycle during rollback')
    seen.add(path);level+=1;parent=parent.get_attach_parent_actor()
   return level
  # Restore parent225 before child worlds, then every component world last.
  for actor,transform,label,hidden,comps in sorted(states,key=lambda row:depth(row[0])):actor.set_actor_transform(transform,False,False)
  for actor,transform,label,hidden,comps in states:
   actor.set_actor_label(label);actor.set_actor_hidden_in_game(hidden)
   for c,world,mesh,mats,tags,visible,collision,profile in comps:
    c.set_static_mesh(mesh);c.set_world_transform(world,False,False);c.set_editor_property('component_tags',tags);c.set_visibility(visible);c.set_collision_profile_name(profile);c.set_collision_enabled(collision)
    for slot,mat in enumerate(mats):c.set_material(slot,mat)
  for actor in list(eas.get_all_level_actors()):
   if actor.get_path_name()not in before:eas.destroy_actor(actor)
  for owned in (dest,deskdest,*([ctx['lampdest']]if 'ctx'in locals()else [])):
   if u.EditorAssetLibrary.does_directory_exist(owned):u.EditorAssetLibrary.delete_directory(owned)
  raise
