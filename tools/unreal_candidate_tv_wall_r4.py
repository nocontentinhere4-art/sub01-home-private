"""Candidate-only genuine veneer-front correction: keep original architecture intact."""
import copy,json,hashlib,time,shutil,uuid
from pathlib import Path
ROOT=Path('/workspace/sub01-home-private/reference-living-tv-wall-r4/output')

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot,assigned_material_binding
 from unreal_import_reference_living_tv_zone import prepare
 from unreal_import_real_wc import expected_triangles,owned_geometry
 from unreal_remove_frame_backings import same_triangles,native_triangles
 from unreal_import_reference_wall_console import positive_triangles
 from unreal_import_real_bathroom_pendant import verify_owned_material
 from unreal_owned_import_cleanup import detach_added
 assert active_candidate_guard();receipt=json.loads((CANDIDATE/'private-audit/reference-living-tv-zone-native.json').read_text());assert receipt['saved']and receipt['wall_sha256']=='828d7078120975c830db7016152936378617295c86a54cde5b6888b79940bc0a'
 source=ROOT/'living-tv-wall.glb';report=json.loads((ROOT/'source-report.json').read_text());sha=hashlib.sha256(source.read_bytes()).hexdigest();assert sha=='3a664a85e472abcc4998ad6aaa1a7a9eada353421a56c878345cc6a87410ade1'and sha==report['files']['living-tv-wall.glb']and report['cladding_front_clearance_from_retained_white_wall_cm']==.5
 proof=json.loads((ROOT/'independent-front-clearance.json').read_text());assert proof['source_sha256']==sha and proof['ok']is True and proof['tv_case_screen_unchanged']is True and proof['niche_rear_unchanged']is True and proof['retained_original_white_wall_unchanged']is True
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);by={a.get_path_name():a for a in actors};old=[]
 for p in receipt['parts']:
  if p['role']!='wall':continue
  a=by[p['actor']];cs=a.get_components_by_class(u.StaticMeshComponent);assert len(cs)==1;c=cs[0];assert c.get_path_name()==p['component']and c.get_editor_property('static_mesh').get_path_name()==p['mesh']and not a.get_editor_property('hidden');old.append((a,c))
 assert len(old)==9
 dest='/Game/Sub01Home/LivingTVWallR4/V_'+sha[:12]+'/Attempt_'+uuid.uuid4().hex;backup=CANDIDATE/'Saved/PrivateMapBackups'/('living-wall-r4-'+str(time.time_ns()));backup.mkdir(parents=True);mapfile=CANDIDATE/'Content/Sub01Home/ActualHome.umap';shutil.copy2(mapfile,backup/'ActualHome.umap');saved=False
 try:
  target=CANDIDATE/'Saved/PrivateImportInputs'/('wall-r4-'+uuid.uuid4().hex+'.glb');doc,blob=prepare(source,target,'R4W');names={n['name']for n in doc['nodes']};manager=u.InterchangeManager.get_interchange_manager_scripted();params=u.ImportAssetParameters();params.set_editor_property('is_automated',True);assert manager.import_scene(dest,manager.create_source_data(str(target)),params);manager.wait_until_all_tasks_done(False)
  matches={};parts=[]
  for a in eas.get_all_level_actors():
   if a.get_path_name()in before:continue
   a.set_actor_hidden_in_game(True)
   for c in a.get_components_by_class(u.StaticMeshComponent):
    mesh=c.get_editor_property('static_mesh')
    if mesh and mesh.get_path_name().startswith(dest+'/'):
     for key in{a.get_actor_label(),mesh.get_name()}:
      if key in names:matches.setdefault(key,{})[c.get_path_name()]=(a,c)
  for i,node in enumerate(doc['nodes']):
   pairs=list(matches.get(node['name'],{}).values());assert len(pairs)==1;a,c=pairs[0];assert len(a.get_components_by_class(u.StaticMeshComponent))==1;owned_geometry(u,c.get_editor_property('static_mesh'),dest);expected,zero=positive_triangles(expected_triangles(doc,blob,i));actual,nativezero=positive_triangles(native_triangles(u,c));assert same_triangles(expected,actual,.0001),'Full R4 source geometry differs '+node['name'];material=doc['materials'][doc['meshes'][node['mesh']]['primitives'][0]['material']];assigned_material_binding(c,material,dest);pbr=verify_owned_material(u,c,material,dest,source_primitive_verified=True);c.set_collision_profile_name('BlockAll');c.set_collision_enabled(u.CollisionEnabled.QUERY_AND_PHYSICS);a.set_actor_enable_collision(True);c.set_cast_shadow(True);a.set_actor_label(node['name']);parts.append((a,c,{'actor':a.get_path_name(),'component':c.get_path_name(),'mesh':c.get_editor_property('static_mesh').get_path_name(),'source_node':node['name'],'positive_triangles':len(actual),'source_exact_zero_indices':zero,'native_exact_zero_indices':nativezero,'pbr':pbr}))
  assert len(parts)==9 and snapshot(u,actors)==before
  assert u.EditorAssetLibrary.save_directory(dest,only_if_is_dirty=False,recursive=True);expected=copy.deepcopy(before)
  for a,c in old:
   a.set_actor_hidden_in_game(True);a.set_is_temporarily_hidden_in_editor(True);c.set_collision_profile_name('NoCollision');c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION);r=expected[a.get_path_name()];r['hidden']=True;r['editor_hidden']=True;r['components'][0]['profile']='NoCollision';r['components'][0]['collision']=str(u.CollisionEnabled.NO_COLLISION)
  for a,c,p in parts:a.set_actor_hidden_in_game(False);c.set_visibility(True)
  assert snapshot(u,actors)==expected and active_candidate_guard();saved=True;assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
  r={'schema':'sub01.candidate-real-veneer-front-r4.v1','saved':True,'source_sha256':sha,'owned_destination':dest,'parts':[p for a,c,p in parts],'only_retired_actors':[a.get_path_name()for a,c in old],'backup':str(backup),'protected_originals_exact':True,'original_white_wall_unchanged':True,'tv_screen_case_and_input_unchanged':True,'live_game_changed':False,'front_separation_cm':.5,'native_visual_accepted':False,'map_sha256':hashlib.sha256(mapfile.read_bytes()).hexdigest(),'epoch':time.time()};(CANDIDATE/'private-audit/living-tv-wall-r4-native.json').write_text(json.dumps(r,indent=2)+'\n');return r
 except Exception:
  for a,c in old:
   p=before[a.get_path_name()];a.set_actor_hidden_in_game(p['hidden']);a.set_is_temporarily_hidden_in_editor(p['editor_hidden']);c.set_collision_profile_name(p['components'][0]['profile']);key=p['components'][0]['collision'].split('CollisionEnabled.',1)[1].split(':',1)[0];c.set_collision_enabled(getattr(u.CollisionEnabled,key))
  detach_added(u,eas,before);assert snapshot(u,eas.get_all_level_actors())==before
  if saved:assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
  raise
