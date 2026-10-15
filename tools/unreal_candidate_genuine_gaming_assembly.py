"""Candidate-only whole genuine PS5 and two licensed DualSense displays.

Original artists' geometry/materials are immutable. Only external uniform units
and rigid placement change. Whole obsolete six-actor assembly is retired.
"""
from pathlib import Path
import json,time,hashlib,copy,shutil,uuid
PSROOT=Path('/workspace/sub01-home-private/ps5-datsketch-original-r1')
SUPSHA='4d489429c66d60520fc47d3d7eb042389317ac6a9d72182a0903d54b3185b8a4'

def rotate(p,yaw):
 import math
 a=math.radians(yaw);c,s=math.cos(a),math.sin(a);return [c*p[0]-s*p[1],s*p[0]+c*p[1],p[2]]
def qmul(a,b):
 x,y,z,w=a;X,Y,Z,W=b;return [w*X+x*W+y*Z-z*Y,w*Y-x*Z+y*W+z*X,w*Z+x*Y-y*X+z*W,w*W-x*X-y*Y-z*Z]
def pose(u,a,t,translation,yaw=0):
 import math
 r=rotate(t['translation'],yaw);q=qmul([0,0,math.sin(math.radians(yaw)/2),math.cos(math.radians(yaw)/2)],t['rotation']);tr=u.Transform();tr.translation=u.Vector(*[r[k]+translation[k]for k in range(3)]);tr.rotation=u.Quat(*q);tr.scale3d=u.Vector(*t['scale']);a.set_actor_transform(tr,False,True)

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 from home_asset_audit import read_gltf
 from unreal_import_real_wc import expected_triangles,owned_geometry
 from unreal_import_reference_wall_console import positive_triangles
 from unreal_remove_frame_backings import native_triangles,same_triangles
 from unreal_import_real_bathroom_pendant import verify_owned_material
 from unreal_owned_import_cleanup import detach_added
 from unreal_component_collision_state import capture,restore
 assert active_candidate_guard();audit=CANDIDATE/'private-audit';ps=json.loads((audit/'original-ps5-native-assets.json').read_text());ds=json.loads((audit/'genuine-dualsense-native-assets.json').read_text());oldreceipt=json.loads((audit/'reference-wall-console-native.json').read_text());shift=json.loads((audit/'tv-console-solid-pier.json').read_text());proof=json.loads((PSROOT/'review/independent-whole-wall-support.json').read_text());assert ps['saved_assets']and ds['saved_assets']and ps['world_restored_exact']and ds['world_restored_exact'];assert proof['unresolvedSourceIntersections']==[] and proof['sourceFitPassed'] is True and proof['supportSourceSha256']==SUPSHA
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);by={a.get_path_name():a for a in actors};old=[]
 for row in oldreceipt['parts']:
  a=by[row['actor']];assert before[a.get_path_name()]==shift['after'][a.get_path_name()];assert len(a.get_components_by_class(u.StaticMeshComponent))==1;assert before[a.get_path_name()]['components'][0]['mesh'].startswith(oldreceipt['owned_destination']+'/');old.append(a)
 collision_before={a.get_path_name():capture(u,a.get_components_by_class(u.StaticMeshComponent)[0])for a in old}
 assert len(old)==6 and len(ps['parts'])==24 and len(ds['parts'])==2
 mapfile=CANDIDATE/'Content/Sub01Home/ActualHome.umap';backup=CANDIDATE/'Saved/PrivateMapBackups'/('genuine-gaming-'+str(time.time_ns()));backup.mkdir(parents=True);shutil.copy2(mapfile,backup/'ActualHome.umap');parts=[];records=[];dest='/Game/Sub01Home/GenuineGamingSupport/A_'+uuid.uuid4().hex;saved=False
 def new_part(row,label,t,offset,yaw,material):
  a=eas.spawn_actor_from_class(u.StaticMeshActor,u.Vector(0,0,0),u.Rotator());parts.append(a);a.set_actor_label(label);c=a.get_components_by_class(u.StaticMeshComponent)[0];mesh=u.load_asset(row['mesh']);assert mesh;c.set_static_mesh(mesh);assert c.get_num_materials()==1;c.set_material(0,u.load_asset(material));assert c.get_material(0).get_path_name()==material;pose(u,a,t,offset,yaw);a.set_actor_enable_collision(False);c.set_collision_profile_name('NoCollision');c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION);return a,c
 try:
  # Exact owned steel revision, genuine source meshes and material kept intact.
  src=PSROOT/'support-r1/ps5-whole-base-support.glb';assert hashlib.sha256(src.read_bytes()).hexdigest()==SUPSHA;sd,sb=read_gltf(src);assert len(sd['meshes'])==1
  manager=u.InterchangeManager.get_interchange_manager_scripted();p=u.ImportAssetParameters();p.set_editor_property('is_automated',True);assert manager.import_scene(dest,manager.create_source_data(str(src)),p);manager.wait_until_all_tasks_done(False)
  added=[a for a in eas.get_all_level_actors()if a.get_path_name()not in before];steel=[];roots=[]
  for a in added:
   cs=a.get_components_by_class(u.StaticMeshComponent)
   if not cs:roots.append(a);continue
   assert len(cs)==1;c=cs[0];assert c.get_editor_property('static_mesh').get_path_name().startswith(dest+'/');steel.append((a,c));parts.append(a)
  assert len(steel)==1
  a,c=steel[0];owned_geometry(u,c.get_editor_property('static_mesh'),dest);assert u.Sub01HomeHandsInstance.finish_pending_static_compilation()==0;st,_=positive_triangles(expected_triangles(sd,sb,0));actual,_=positive_triangles(native_triangles(u,c));assert len(st)==1948 and same_triangles(st,actual,.0001,deadline_monotonic=time.monotonic()+20);verify_owned_material(u,c,sd['materials'][sd['meshes'][0]['primitives'][0]['material']],dest,source_primitive_verified=True)
  if a.get_attach_parent_actor():a.detach_from_actor(u.DetachmentRule.KEEP_WORLD,u.DetachmentRule.KEEP_WORLD,u.DetachmentRule.KEEP_WORLD)
  a.set_actor_label('SUB01_GenuinePS5_WholeBaseSupport');a.set_actor_enable_collision(False);c.set_collision_profile_name('NoCollision');c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
  for r in reversed(roots):assert not r.get_attached_actors();assert eas.destroy_actor(r)
  # canonical point = original point*UNIT + offset. Undo offset then rotate180.
  psdoc,psblob=read_gltf(PSROOT/'original-unmodified-console.glb');unit=ps['external_unit_conversion'];off=ps['external_canonical_offset_cm'];root=proof['externalNativeRootTranslationUEcm'];roff=rotate(off,180);delta=[root[k]-roff[k]for k in range(3)];allps=[]
  for row in ps['parts']:
   a,c=new_part(row,'SUB01_GenuinePS5_'+str(row['source_node_index']),row['canonical_actor_transform'],delta,180,row['actual_rendered_material']);expected,_=positive_triangles(expected_triangles(psdoc,psblob,row['source_node_index']));expected=[[[rotate([v*unit for v in point],180)[k]+root[k]for k in range(3)]for point in tri]for tri in expected];actual,_=positive_triangles(native_triangles(u,c));assert same_triangles(expected,actual,.0001,deadline_monotonic=time.monotonic()+15),'Original wholePS5 physical placement differs';allps.extend(p for tri in actual for p in tri);records.append({'role':'original-ps5','source_node':row['source_node_index'],'actor':a.get_path_name(),'mesh':row['mesh'],'material':row['actual_rendered_material'],'triangles':len(actual)})
  assert abs(min(p[2]for p in allps)-125.8)<.0001
  # One source-faithful flat display per actual supporting surface; no held assignment.
  table=[a for a in actors if a.get_actor_label()=='SUB01_OfficialMuutoAroundLarge'];assert len(table)==1;tc=table[0].get_components_by_class(u.StaticMeshComponent)[0];tt=native_triangles(u,tc);center=[-257.,-5.];tops=[]
  def plane_hit(tri,x,y):
   a,b,c=tri;den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
   if abs(den)<1e-12:return None
   A=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/den;B=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/den
   return A*a[2]+B*b[2]+(1-A-B)*c[2]if min(A,B,1-A-B)>=-1e-8 else None
  tops=[z for tri in tt if (z:=plane_hit(tri,*center))is not None];assert tops;top=max(tops);assert 35<top<42
  dd,db=read_gltf(Path('/workspace/sub01-home-private/real-dualsense-chizuko-r1/native-source-r1/real-dualsense-160mm.glb'))
  # Hardware's actual upper tray top105.5cm; controller bottom .005cm above.
  for role,offset,yaw in [('table',[-257,-5,top+.005],0),('dock',[-368.3,-119.5,105.505],90)]:
   for n,row in enumerate(ds['parts']):
    material=row['pbr']['pbr'][0]['actual_material'];a,c=new_part(row,'SUB01_GenuineDualSense_'+role+'_'+str(n),row['actor_transform'],offset,yaw,material);expected,_=positive_triangles(expected_triangles(dd,db,n));expected=[[[rotate(point,yaw)[k]+offset[k]for k in range(3)]for point in tri]for tri in expected];actual,_=positive_triangles(native_triangles(u,c));assert same_triangles(expected,actual,.0001,deadline_monotonic=time.monotonic()+25);records.append({'role':'dualsense-'+role,'actor':a.get_path_name(),'mesh':row['mesh'],'material':material,'triangles':len(actual),'offset_cm':offset,'yaw':yaw})
  assert snapshot(u,actors)==before
  for a in old:
   a.set_actor_hidden_in_game(True);a.set_is_temporarily_hidden_in_editor(True);c=a.get_components_by_class(u.StaticMeshComponent)[0];c.set_collision_profile_name('NoCollision');c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
  expected=copy.deepcopy(before)
  for a in old:
   r=expected[a.get_path_name()];r['hidden']=True;r['editor_hidden']=True;r['components'][0]['profile']='NoCollision';r['components'][0]['collision']=str(u.CollisionEnabled.NO_COLLISION)
  assert snapshot(u,actors)==expected and active_candidate_guard();assert u.EditorAssetLibrary.save_directory(dest,only_if_is_dirty=False,recursive=True);saved=True;assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
  result={'schema':'sub01.genuine-gaming-static-assembly.v1','saved':True,'parts':records,'new_parts':len(parts),'source_geometry_materials_unchanged':True,'table_surface_actual_z':top,'old_whole_assembly_retired':[a.get_path_name()for a in old],'originals_before':{a.get_path_name():before[a.get_path_name()]for a in old},'originals_after':{a.get_path_name():expected[a.get_path_name()]for a in old},'backup':str(backup),'protected_all_other_actors_exact':True,'tv_input_plane_unchanged':True,'game_changed':False,'held_contact_accepted':False,'pickup_implemented':False,'epoch':time.time()};(audit/'genuine-gaming-static-assembly.json').write_text(json.dumps(result,indent=2)+'\n');return result
 except Exception:
  for a in old:
   row=before[a.get_path_name()];a.set_actor_hidden_in_game(row['hidden']);a.set_is_temporarily_hidden_in_editor(row['editor_hidden']);c=a.get_components_by_class(u.StaticMeshComponent)[0];restore(u,c,collision_before[a.get_path_name()])
  detach_added(u,eas,before);assert snapshot(u,eas.get_all_level_actors())==before
  if saved:assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
  raise
