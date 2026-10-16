"""Read-only adapter for externally reviewed candidate scene probes."""
import hashlib,json,time

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 import device_motion_integration_probe
 assert active_candidate_guard()
 actors=u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors();before=snapshot(u,actors)
 mapfile=CANDIDATE/'Content/Sub01Home/ActualHome.umap';old=hashlib.sha256(mapfile.read_bytes()).hexdigest()
 result=device_motion_integration_probe.run()
 assert active_candidate_guard()and snapshot(u,u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors())==before
 assert hashlib.sha256(mapfile.read_bytes()).hexdigest()==old
 return result

def run_sofa():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 import impulse_sofa_seating_probe_ue58 as probe
 assert active_candidate_guard()
 assert hashlib.sha256(__import__('pathlib').Path(probe.__file__).read_bytes()).hexdigest()=='51d908fa1de23425c13200fc485d59e57af75cc132fb1bdfb576a78e71114e95'
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors)
 mapfile=CANDIDATE/'Content/Sub01Home/ActualHome.umap';old=hashlib.sha256(mapfile.read_bytes()).hexdigest()
 receiptpath=CANDIDATE/'private-audit/muuto-rest-native.json';receipt=json.loads(receiptpath.read_text())
 assert receipt['saved']and receipt['source_sha256']==probe.SOURCE_SHA256 and receipt['protected_others_exact']
 request={'source_sha256':probe.SOURCE_SHA256,'actors':{},'seat_triangle_indices':{},'floor_triangle_indices':{},'floor_components':[],'collision_samples':[]}
 for row in receipt['parts']:
  matches=[a for a in actors if a.get_path_name()==row['actor']];assert len(matches)==1
  actor=matches[0];request['actors'][actor.get_actor_label()]=row['actor']
 discovery={'start_cm':[-66.906241,271.915124,95.650083],'end_cm':[-66.906241,271.915124,-200.0], 'selection':'downward collision trace from explicitly public saved pawn position; no pose change'}
 try:
  world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
  hit=u.SystemLibrary.line_trace_single(world,u.Vector(*discovery['start_cm']),u.Vector(*discovery['end_cm']),u.TraceTypeQuery.TRACE_TYPE_QUERY1,True,[],u.DrawDebugTrace.NONE,False)
  if isinstance(hit,tuple):
   assert len(hit)==2 and hit[0];hit=hit[1]
  assert hit is not None,'No actual downward collision hit'
  values=u.SystemLibrary.break_hit_result(hit);actor,component=values[9],values[10]
  discovery.update(blocking_hit=bool(values[0]),hit_actor=actor.get_path_name()if actor else None,hit_component=component.get_path_name()if component else None,impact_point_cm=probe.vector(values[5]),impact_normal=probe.vector(values[7]))
  if actor and component and isinstance(component,u.StaticMeshComponent):
   mesh=component.get_editor_property('static_mesh');assert mesh is not None
   discovery.update(mesh=mesh.get_path_name(),collision_only_or_hidden=bool(actor.get_editor_property('hidden')or not component.is_visible()))
   if not discovery['collision_only_or_hidden']:
    request['floor_components']=[{'actor':actor.get_path_name(),'component':component.get_path_name(),'mesh':mesh.get_path_name()}]
   else:discovery['refusal']='Actual hit is hidden/collision-only; no rendered floor inferred'
  else:discovery['refusal']='Actual hit is not a StaticMeshComponent; no rendered floor inferred'
 except Exception as error:discovery['refusal']=str(error)
 discovery_path=CANDIDATE/'private-audit/muuto-floor-trace-discovery.json';discovery_path.write_text(json.dumps(discovery,indent=2)+'\n')
 try:
  inventorypath=CANDIDATE/'private-audit/device-motion-scene-inventory-1792113072090967669.json'
  inventory=json.loads(inventorypath.read_text());assert inventory['world_unchanged']and inventory['map_sha256']==old
  renderfloor=[r for r in inventory['components']if r['actor']=='/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.full-home_node_0'and r['component']=='/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.full-home_node_0.StaticMeshComponent0'and r['mesh']=='/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Mesh_0.Mesh_0'];assert len(renderfloor)==1
  request['floor_components']=[{k:renderfloor[0][k]for k in ('actor','component','mesh')}]
  discovery['render_floor_inventory_sha256']=hashlib.sha256(inventorypath.read_bytes()).hexdigest();discovery['render_floor_pin']=request['floor_components'][0]
  discovery['collision_hit_differs_from_render_floor']=(discovery['hit_component']!=renderfloor[0]['component'])if discovery.get('hit_component')else None
  requestfile=__import__('pathlib').Path('/home/unreal/runtime-tools/muuto-floor-firstpass-request.json');assert hashlib.sha256(requestfile.read_bytes()).hexdigest()=='60ae63fab1a49d59f97cf72e34ea384af92959e9332a88b6b0b071c5336fb97f'
  exactrequest=json.loads(requestfile.read_text());assert exactrequest['actors']==request['actors']and exactrequest['source_sha256']==request['source_sha256']
  assert hashlib.sha256(receiptpath.read_bytes()).hexdigest()=='427b8cb824e252882117b9c279e0a0a441357657f1e82bb44d18ee11b161760d'
  request=exactrequest
  result=probe.run(request)
  result['firstpass_request_sha256']='60ae63fab1a49d59f97cf72e34ea384af92959e9332a88b6b0b071c5336fb97f'
  result['source_probe_original_sha256']='a9a06d79f9e08ba9e8fac87326f2a4bbbfa1e987313b297bcdf0d263664ea9c7'
  result['source_probe_ue58_derivative_sha256']='51d908fa1de23425c13200fc485d59e57af75cc132fb1bdfb576a78e71114e95'
  result['compatibility_change']='Only two actor hidden getters use actual UE5.8 get_editor_property(hidden)'
 finally:
  assert active_candidate_guard()and snapshot(u,eas.get_all_level_actors())==before and hashlib.sha256(mapfile.read_bytes()).hexdigest()==old
 result.update(floor_discovery=discovery,request=request,source_receipt_sha256=hashlib.sha256(receiptpath.read_bytes()).hexdigest(),source_bytes_rehashed=False,all_geometry_unselected=True,fit_ready=False)
 assert active_candidate_guard()and snapshot(u,eas.get_all_level_actors())==before and hashlib.sha256(mapfile.read_bytes()).hexdigest()==old
 result.update(world_unchanged=True,map_unchanged=True,input_delivered=False,camera_changed=False)
 out=CANDIDATE/'private-audit'/('muuto-seat-floor-discovery-'+str(time.time_ns())+'.json');out.write_text(json.dumps(result,indent=2)+'\n')
 return {'inventory':str(out),'floor_discovery':discovery,'errors':result['errors'],'world_unchanged':True,'fit_ready':False}
