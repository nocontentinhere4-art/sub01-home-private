"""One sole-owner warm-Editor transaction for the complete authentic office bundle.

All imports/native geometry/material/support checks happen before original desk/
shelves, lamp or46 owned books move. One final map save. Failure restores every
original actor/component reference and removes only actors/assets newly owned by
this transaction. No level load, pod operation, controller edit or restart.
"""
import copy,hashlib,json
from pathlib import Path
from home_asset_audit import read_gltf
from unreal_import_reference_dressing import fingerprint
from unreal_import_real_linea140 import run as stage_desk,surface,verify_materials,close,vec
from prepare_real_office_bundle import BOOKS_SHA,SHELF_SHA
LEVEL='/Game/Sub01Home/ActualHome'


def run(root,dry_run=True,u=None):
 if u is None:import unreal as u
 root=Path(root);proof=json.loads((root/'office-bundle.json').read_text())
 if proof.get('schema')!='sub01.real-office-bundle.v1' or not proof.get('source_triangle_collision_proof',{}).get('ok') or not proof.get('whole_book_geometry_pbr_preserved') or proof.get('complete_original_book_glb_sha256')!=BOOKS_SHA or len(proof.get('books',[]))!=46 or proof.get('hide_only_source_actor_nodes')!=[181,182,190,191]:raise RuntimeError('Actual coherent whole office source proof unavailable')
 shelfpath=root/'shelves.glb';digest=hashlib.sha256(shelfpath.read_bytes()).hexdigest()
 if digest!=proof['shelf']['sha256'] or proof['shelf']['source_sha256']!=SHELF_SHA or not proof['shelf']['source_binary_unchanged']:raise RuntimeError('Actual complete shelf source identity differs')
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
 if not world or world.get_path_name().split('.',1)[0]!=LEVEL:raise RuntimeError('Already loaded ActualHome required; no new Editor or level load')
 original=list(eas.get_all_level_actors());before=fingerprint(u,original)
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
 if dry_run:return {'schema':'sub01.real-office-native-preflight.v1','desk':desk_preflight,'complete_native_books_verified':46,'old_shelf_paths':[a.get_path_name()for a in old_shelves],'mutations':0}
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
  cap,cc,_=ctx['by_node'][8];cap.set_actor_hidden_in_game(True);cc.set_visibility(False);cc.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
  mount=ctx['mount'];ctx['lamp'].set_actor_location(u.Vector(*mount['new_origin_ue_cm']),False,False);ctx['light'].set_actor_location(u.Vector(*[vec(ctx['light'].get_actor_location())[a]+mount['new_bulb_ue_cm'][a]-vec(ctx['lights'][0].get_world_location())[a]for a in range(3)]),False,False)
  if not close(vec(ctx['lights'][0].get_world_location()),mount['new_bulb_ue_cm']):raise RuntimeError('Actual paired light did not reach verified bulb')
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
  old_targets=ctx['old']+old_shelves
  for actor in old_targets:
   actor.set_actor_hidden_in_game(True)
   for c in actor.get_components_by_class(u.StaticMeshComponent):c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
  allowed={a.get_path_name()for a in old_targets+[ctx['lamp'],ctx['light']]+[a for a,c,p in books]}
  if fingerprint(u,[a for a in original if a.get_path_name()not in allowed])!={k:v for k,v in before.items()if k not in allowed}:raise RuntimeError('Office activation changed protected stairs/chair/devices/screens/controller geometry')
  if {c.get_path_name():c.get_editor_property('intensity')for a in original for c in a.get_components_by_class(u.LightComponent)}!=light_values:raise RuntimeError('Office placement changed existing lamp switch intensity state')
  for actor,transform,label,hidden,comps in states:
   expected=True if actor in old_targets else hidden
   if bool(actor.get_editor_property('hidden'))!=expected:raise RuntimeError('Office activation changed unplanned visibility')
  if not u.EditorAssetLibrary.save_directory(deskdest,only_if_is_dirty=False,recursive=True) or not u.EditorAssetLibrary.save_directory(dest,only_if_is_dirty=False,recursive=True) or not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Whole office save failed')
  result={'schema':'sub01.real-office-native-import.v1','source_bundle':proof,'desk':desk_result,'shelf_native_triangles':alltris,'shelf_materials':materials,'books':book_rows,'hidden_originals':[a.get_path_name()for a in old_targets],'native_protected_original_fingerprints_verified':len(before)-len(allowed),'native_visual_verified':False,'contact_limit':'Original device foot penetration is unchanged at actual baseline top; not described as perfect.'}
  (root/'native-office-bundle.json').write_text(json.dumps(result,indent=2)+'\n');return result
 except Exception:
  for actor,transform,label,hidden,comps in states:
   actor.set_actor_transform(transform,False,False);actor.set_actor_label(label);actor.set_actor_hidden_in_game(hidden)
   for c,world,mesh,mats,tags,visible,collision,profile in comps:
    c.set_static_mesh(mesh);c.set_world_transform(world,False,False);c.set_editor_property('component_tags',tags);c.set_visibility(visible);c.set_collision_profile_name(profile);c.set_collision_enabled(collision)
    for slot,mat in enumerate(mats):c.set_material(slot,mat)
  for actor in list(eas.get_all_level_actors()):
   if actor.get_path_name()not in before:eas.destroy_actor(actor)
  for owned in (dest,deskdest):
   if u.EditorAssetLibrary.does_directory_exist(owned):u.EditorAssetLibrary.delete_directory(owned)
  raise
