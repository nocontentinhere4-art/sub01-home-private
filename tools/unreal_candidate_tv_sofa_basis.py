"""Bounded read-only TV surface basis and source-derived sofa approach proposal."""
from pathlib import Path
import hashlib,json,math,time

def sub(a,b):return [a[i]-b[i]for i in range(3)]
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def norm(v):return math.sqrt(dot(v,v))
def unit(v):
 n=norm(v);assert n>1e-9;return [x/n for x in v]
def surface_geometry(triangles):
 weighted=[0.,0.,0.];area=0.;normals=[]
 for tri in triangles:
  c=cross(sub(tri[1],tri[0]),sub(tri[2],tri[0]));a=norm(c)/2
  if not a:continue
  for i in range(3):weighted[i]+=a*sum(p[i]for p in tri)/3
  area+=a;normals.append(unit(c))
 assert area>0
 center=[x/area for x in weighted];normal=normals[0]
 assert all(abs(dot(n,normal))>1-1e-6 for n in normals),'TV source is not one planar face'
 assert all(abs(dot(sub(p,center),normal))<.0001 for tri in triangles for p in tri),'TV world geometry is not planar'
 return {'area_weighted_surface_centroid_cm':center,'surface_area_cm2':area,'triangle_winding_normals':normals,'plane_normal_unsigned':normal,'world_triangles_cm':triangles}
def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 from unreal_import_real_wc import expected_triangles
 from unreal_remove_frame_backings import native_triangles,same_triangles
 from home_asset_audit import read_gltf
 started=time.monotonic();deadline=started+55
 assert active_candidate_guard();eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors)
 sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();mapfile=CANDIDATE/'Content/Sub01Home/ActualHome.umap';mapsha=sha(mapfile)
 source=CANDIDATE/'SourceAssets/full-home.glb';assert sha(source)=='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
 doc,blob=read_gltf(source);matches=[a for a in actors if a.get_name()=='full-home_node_131'];assert len(matches)==1;actor=matches[0]
 assert actor.get_path_name()=='/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.full-home_node_131'
 cs=actor.get_components_by_class(u.StaticMeshComponent);assert len(cs)==1;c=cs[0]
 expected=expected_triangles(doc,blob,131);actual=native_triangles(u,c);assert len(expected)==len(actual)==2 and same_triangles(expected,actual,.0001,deadline_monotonic=deadline)
 previewpath=CANDIDATE/'private-audit/editor-tv-preview-exposure.json';preview=json.loads(previewpath.read_text());assert preview['saved']and preview['texture_and_uv_parameters_preserved']and preview['protected_all_actors_exact_except_tv_material']
 material=c.get_material(0);assert material.get_path_name()==preview['owned_preview_material']and preview['original_material']=='/Game/Sub01Home/ImportedScene/full-home/Materials/Material_64.Material_64'
 tv=surface_geometry(actual);tv.update(actor=actor.get_path_name(),label=actor.get_actor_label(),component=c.get_path_name(),mesh=c.get_editor_property('static_mesh').get_path_name(),actual_material=material.get_path_name(),original_source_material=preview['original_material'],material_receipt_sha256=sha(previewpath),source_node=131,source_geometry_exact=True,component_transform=before[actor.get_path_name()]['components'][0]['transform'])
 world=c.get_world_transform();origin=world.transform_location(u.Vector(0,0,0));pvec=lambda p:[float(getattr(p,a))for a in('x','y','z')]
 tv['component_local_axes_in_world']=[unit(sub(pvec(world.transform_location(u.Vector(*axis))),pvec(origin)))for axis in((1,0,0),(0,1,0),(0,0,1))]
 discoverypath=CANDIDATE/'private-audit/muuto-seat-floor-discovery-1792113357535309167.json';d=json.loads(discoverypath.read_text());assert d['world_unchanged']and d['map_unchanged']and d['source_receipt_sha256']=='427b8cb824e252882117b9c279e0a0a441357657f1e82bb44d18ee11b161760d'
 receiptpath=CANDIDATE/'private-audit/muuto-rest-native.json';receipt=json.loads(receiptpath.read_text());assert receipt['saved']and sha(receiptpath)==d['source_receipt_sha256']
 for row in receipt['parts']:
  found=[a for a in actors if a.get_path_name()==row['actor']];assert len(found)==1
  prior=next(r for r in d['actors']if r['actor']==row['actor']);component=found[0].get_components_by_class(u.StaticMeshComponent);assert len(component)==1 and component[0].get_path_name()==row['component'];assert before[row['actor']]['components'][0]['mesh']==prior['mesh']
  assert before[row['actor']]['components'][0]['transform']['translation']==prior['component_transform']['translation']
 points=[p for section in d['sofa']['sections']for p in section['vertices_world_cm']];front=min(p[0]for p in points);assert abs(front+179.5)<.01
 meta=json.loads(Path('/home/unreal/.sub01-private/native-visual-metrics.json').read_text());assert(meta['native_pid'],meta['native_start_ticks'])==(225250,980289227)
 radius=meta['actual_capsule_radius_cm'];height=meta['actual_capsule_half_height_cm'];assert 0<radius<50 and 50<height<120
 y=10.;approach=[front-radius-3.,y];center=tv['area_weighted_surface_centroid_cm'];delta=[center[0]-approach[0],center[1]-approach[1]];yaw=math.degrees(math.atan2(delta[1],delta[0]))
 normal=tv['plane_normal_unsigned'];to_sofa=sub([front,y,center[2]],center);tv['plane_normal_oriented_toward_sofa']=[x*(1 if dot(normal,to_sofa)>0 else -1)for x in normal]
 assert active_candidate_guard()and snapshot(u,eas.get_all_level_actors())==before and sha(mapfile)==mapsha and time.monotonic()<deadline
 r={'schema':'sub01.actual-tv-muuto-basis-readonly.v1','map_sha256':mapsha,'tv':tv,'muuto_discovery_sha256':sha(discoverypath),'muuto_saved_receipt_sha256':sha(receiptpath),'muuto_source_front_axis_ue':[-1,0,0],'muuto_front_basis':'genuine rigid-source placement front -179.5cm, independently corroborated by full actual sofa vertices; not a seat anchor','proposal':{'capsule_radius_cm':radius,'capsule_half_height_cm':height,'approach_xy_cm':approach,'approach_rule':'frontmost genuine geometry minus actual capsule radius and 3cm clearance, source centerlineY10; candidate only','yaw_degrees_toward_actual_tv_surface_centroid':yaw,'look_target_world_cm':center,'seated_eye_height_or_pitch':None,'vertical_anchor':None,'actual_route_or_collision_checked':False,'seated_body_anchor':None},'world_unchanged':True,'map_unchanged':True,'game_input_delivered':False,'camera_changed':False,'native_seat_ready':False,'contact_ready':False,'elapsed_seconds':time.monotonic()-started,'epoch':time.time()}
 p=CANDIDATE/'private-audit'/('tv-muuto-actual-basis-'+str(time.time_ns())+'.json');p.write_text(json.dumps(r,indent=2)+'\n');return {'report':str(p),'sha256':sha(p),'tv_surface_center_cm':center,'proposal':r['proposal'],'world_unchanged':True,'readiness':False}
