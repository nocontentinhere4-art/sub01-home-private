"""Owned complete real door assemblies in sole warmActualHome Editor.
Leaves are independently tagged physical components for receipt-gated runtime;
this import never claims a running game or enables an activity gate.
"""
import copy,hashlib,json,shutil,time,uuid
from pathlib import Path
from home_asset_audit import read_gltf
from prepare_real_wc_bundle import node_geometry
from structural_rail_source_patch import world_matrices
from prepare_frame_backing_remainder import SOURCE_SHA
from unreal_import_real_wc import expected_triangles,owned_geometry
from unreal_remove_frame_backings import native_triangles,same_triangles
from unreal_import_real_linea140 import verify_materials
from unreal_import_reference_dressing import fingerprint
from unreal_component_collision_state import capture,restore
from unreal_owned_import_cleanup import detach_added
from unreal_import_real_home_windows import clear_glass
from unreal_import_authentic_bath_fixtures import prepare_import
ROOT=Path('/workspace/sub01-home-private/authentic-bath-doors-fit-r6/output')
SHA='5b8a2bb8b4bb8fe19af1d0c086fb78f3e7f9dff9e06170a06642a8f3d1761a0c'
OLD=tuple(range(41,49))+(53,54,55,56,58,59)
TAG='SUB01AuthenticDoors:'+SHA+':'

def source_contract(root=ROOT):
 raw=(root/'source-report.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!='9dd9c1033dc37feef0ef28b1c6af8fe5378f720e44fd8d696f826fd46f4bda7d':raise RuntimeError('Frozen measured door source-report required')
 report=json.loads(raw)
 if report['door_bundle_sha256']!=SHA or hashlib.sha256((root/'door-assemblies.glb').read_bytes()).hexdigest()!=SHA or len(report['door_parts'])!=76:raise RuntimeError('Complete frozen76part realdoors required')
 roles=report['door_roles']
 if {k:len(r['moving_parts'])for k,r in roles.items()}!={'bathroom':3,'entry':23,'balcony':8}or roles['entry']['hinge_ue_cm']!=[154.3,402.2,2.5]:raise RuntimeError('Exact complete multipart realdoor groups required')
 witness=json.loads((root/'door-source-motion-witnesses.json').read_text())
 if witness.get('source_sha256')!=SHA or witness.get('unresolved_positive_crossings')!=0 or witness.get('surface_contact_epsilon_cm')!=.001 or len(witness.get('sampled_positions',[]))!=59:raise RuntimeError('Actual59source-pose architecture witnesses required')
 return report

def audit_original_source(u,eas,c,expected,ni,project,allow_clone,hd):
 mesh=c.get_editor_property('static_mesh');sn=hd['meshes'][hd['nodes'][ni]['mesh']]['name'];want='/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/'+sn+'.'+sn
 if ni not in OLD or not mesh or mesh.get_path_name()!=want:raise RuntimeError('Exact originaldoor source binding required')
 sub=u.get_editor_subsystem(u.StaticMeshEditorSubsystem);keys=('enabled','fallback_target','fallback_relative_error','fallback_percent_triangles','keep_percent_triangles','trim_relative_error');settings={k:str(sub.get_nanite_settings(mesh).get_editor_property(k))for k in keys};actual=native_triangles(u,c)
 diagnostic={'source_node':ni,'original_mesh':want,'source_triangles':len(expected),'original_render_fallback_triangles':len(actual),'original_nanite':settings,'original_changed':False};(project/'private-audit'/('original-door-'+str(ni)+'-diagnostic.json')).write_text(json.dumps(diagnostic,indent=2)+'\n')
 if not sub.get_nanite_settings(mesh).get_editor_property('enabled')or not allow_clone:raise RuntimeError('Originaldoor fallback differs; execute requires ownedfullsource cloneaudit')
 dest='/Game/Sub01Home/AuthenticDoors/OriginalSourceAudit/Attempt_'+uuid.uuid4().hex;clone=u.EditorAssetLibrary.duplicate_asset(want.split('.',1)[0],dest+'/'+sn)
 if not clone:raise RuntimeError('Originaldoor ownedfullsource clonefailed')
 actor=None
 try:
  owned_geometry(u,clone,dest)
  if u.Sub01HomeHandsInstance.finish_pending_static_compilation()!=0:raise RuntimeError('Originaldoor clonecompilation pending')
  actor=eas.spawn_actor_from_class(u.StaticMeshActor,u.Vector(0,0,0));actor.set_actor_label('SUB01_TemporaryOriginalDoorAudit_'+str(ni));actor.set_actor_hidden_in_game(True);cc=actor.get_component_by_class(u.StaticMeshComponent);cc.set_static_mesh(clone);cc.set_collision_enabled(u.CollisionEnabled.NO_COLLISION);cc.set_world_transform(c.get_world_transform(),False,True);full=native_triangles(u,cc)
  if not same_triangles(expected,full,tolerance=.0001):raise RuntimeError('Full originaldoor source differs source='+str(len(expected))+' clone='+str(len(full)))
  diagnostic.update(clone_mesh=clone.get_path_name(),full_source_clone_triangles=len(full),all_source_world_triangles_exact=True,tolerance_cm=.0001);return diagnostic
 finally:
  if actor and not eas.destroy_actor(actor):raise RuntimeError('Originaldoor temporarysourceaudit actorcleanupfailed')
  if settings!={k:str(sub.get_nanite_settings(mesh).get_editor_property(k))for k in keys}or c.get_editor_property('static_mesh')!=mesh:raise RuntimeError('Originaldoor bindingsettingschanged duringsourceaudit')

def run(dry_run=True):
 import unreal as u
 report=source_contract();project=Path(u.Paths.project_dir());audit=project/'private-audit';home=project/'SourceAssets/full-home.glb';doc,blob=read_gltf(home)
 if hashlib.sha256(home.read_bytes()).hexdigest()!=SOURCE_SHA:raise RuntimeError('Immutable actual home required')
 world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
 if not world or world.get_path_name()!='/Game/Sub01Home/ActualHome.ActualHome':raise RuntimeError('Exact loaded actualhome required')
 if(audit/'authentic-doors-native.json').exists():raise RuntimeError('Inspect existing savedrealdoors receipt; no duplicates')
 corridor=json.loads((audit/'bathroom-corridor-native-import.json').read_text())
 if corridor['export_sha256']!='5ffac2406e668a327427e60bc75e3ee3ecf13a89381d0312b821277386cb9c91'or not corridor['saved']:raise RuntimeError('Exact actual savedcorridor required')
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);original=list(eas.get_all_level_actors());before=fingerprint(u,original);retired=[];original_source_proofs=[]
 def take(actor,expected,source_node=None):
  cs=actor.get_components_by_class(u.StaticMeshComponent)
  if len(cs)!=1 or bool(actor.get_editor_property('hidden'))or not cs[0].get_editor_property('visible'):raise RuntimeError('Exact olddoor component notactive')
  c=cs[0]
  if not same_triangles(expected,native_triangles(u,c),tolerance=.0001):
   if source_node is None:raise RuntimeError('Ownedcorridor door source differs')
   original_source_proofs.append(audit_original_source(u,eas,c,expected,source_node,project,not dry_run,doc))
  retired.append((actor,c,bool(actor.get_editor_property('hidden')),bool(c.get_editor_property('visible')),actor.is_temporarily_hidden_in_editor(),capture(u,c)))
 for ni in OLD:
  found=[a for a in original if a.get_name()==f'full-home_node_{ni}']
  if len(found)!=1:raise RuntimeError('Exact oldarchitectural doorowner missing '+str(ni))
  take(found[0],expected_triangles(doc,blob,ni),ni)
 row=next(r for r in corridor['parts']if r['source_node']==118);found=[a for a in original if a.get_path_name()==row['actor']]
 if len(found)!=1:raise RuntimeError('Exact saved corridor bathroomdoor owner missing')
 cd,cb=read_gltf(Path('/workspace/sub01-home-private/bathroom-corridor-source-r1/bath-corridor.glb'));ci=next(i for i,n in enumerate(cd['nodes'])if n.get('name')=='SUB01_BathCorridor_SourceNode_118');take(found[0],expected_triangles(cd,cb,ci))
 result={'schema':'sub01.authentic-doors-native.v1','source_sha256':SHA,'dry_run':dry_run,'native_visual_verified':False,'native_door_motion_verified':False,'runtime_ready':False,'privacy_changed':False,'original_source_proofs':original_source_proofs}
 if dry_run:return result
 backup=project/'Saved/PrivateMapBackups'/('authentic-doors-'+str(time.time_ns()));backup.mkdir(parents=True);shutil.copy2(project/'Content/Sub01Home/ActualHome.umap',backup/'ActualHome.umap')
 for name in ('__ExternalActors__','__ExternalObjects__'):
  folder=project/'Content'/name/'Sub01Home/ActualHome'
  if folder.exists():shutil.copytree(folder,backup/name)
 dest='/Game/Sub01Home/AuthenticDoors/V_'+SHA[:12]+'/Attempt_'+uuid.uuid4().hex;parts=[];active=False
 try:
  prepared=project/'Saved/PrivateImportInputs'/('authentic-doors-'+uuid.uuid4().hex+'.glb');d,b,preparation=prepare_import(ROOT/'door-assemblies.glb',prepared,'SUB01_AuthenticDoor_');manager=u.InterchangeManager.get_interchange_manager_scripted();params=u.ImportAssetParameters();params.set_editor_property('is_automated',True)
  if not manager.import_scene(dest,manager.create_source_data(str(prepared)),params):raise RuntimeError('Complete authenticdoors scene refused')
  manager.wait_until_all_tasks_done(False);added=[a for a in eas.get_all_level_actors()if a.get_path_name()not in before]
  for a in added:a.set_actor_hidden_in_game(True)
  by_original={legal:old for old,legal in preparation['names'].items()};moving={name:role for role,row in report['door_roles'].items()for name in row['moving_parts']};source_rows={r['name']:r for r in report['parts']};glass=[];opaque=[];bindings={};rows=[]
  for ni,n in enumerate(d['nodes']):
   if'mesh'not in n:continue
   found=[a for a in added if a.get_actor_label()==n['name']]
   if len(found)!=1:raise RuntimeError('One actualrealdoor part required '+n['name'])
   a=found[0];cs=a.get_components_by_class(u.StaticMeshComponent)
   if len(cs)!=1:raise RuntimeError('One staticmesh perdoorpart required')
   c=cs[0];owned_geometry(u,c.get_editor_property('static_mesh'),dest)
   if not same_triangles(expected_triangles(d,b,ni),native_triangles(u,c)):raise RuntimeError('Realdoor actualsurface differs '+n['name'])
   ps=d['meshes'][n['mesh']]['primitives']
   material_diag={'node':ni,'name':n['name'],'mesh':c.get_editor_property('static_mesh').get_path_name(),'source_primitives':[{'material_index':p['material'],'material_name':d['materials'][p['material']]['name'],'triangle_count':d['accessors'][p['indices']]['count']//3}for p in ps],'native_sections':c.get_editor_property('static_mesh').get_num_sections(0),'native_slot_count':c.get_num_materials(),'native_materials':[m.get_path_name()if m else None for m in c.get_materials()]}
   if len(ps)!=c.get_num_materials()or len(ps)!=c.get_editor_property('static_mesh').get_num_sections(0):
    (audit/'authentic-door-material-section-diagnostic.json').write_text(json.dumps(material_diag,indent=2)+'\n');raise RuntimeError('Exact sourceprimitive/native section andslot count differ '+n['name'])
   expected_sections=node_geometry(d,b,ni,world_matrices(d));world=c.get_world_transform();isglass_flags=[]
   for slot,(primitive,section)in enumerate(zip(ps,expected_sections)):
    vs,ids,*_=u.ProceduralMeshLibrary.get_section_from_static_mesh(c.get_editor_property('static_mesh'),0,slot);vv=[world.transform_location(p)for p in vs];native=[[[float(vv[k].x),float(vv[k].y),float(vv[k].z)]for k in ids[j:j+3]]for j in range(0,len(ids),3)];source=[[[float(section['points'][k][0])*100,float(section['points'][k][2])*100,float(section['points'][k][1])*100]for k in face]for face in section['faces']]
    if not same_triangles(source,native,tolerance=.0001):
     material_diag.update(failed_slot=slot,source_section_triangles=len(source),actual_section_triangles=len(native));(audit/'authentic-door-material-section-diagnostic.json').write_text(json.dumps(material_diag,indent=2)+'\n');raise RuntimeError('Per-material exact door physicalsurface differs '+n['name'])
    material=d['materials'][primitive['material']];isglass=material.get('extensions',{}).get('KHR_materials_transmission',{}).get('transmissionFactor',0)>.5;isglass_flags.append(isglass)
    if not isglass:
     path=c.get_material(slot).get_path_name();prior=bindings.setdefault(material['name'],path)
     if path!=prior:raise RuntimeError('One originaldoor material became separateinstances')
   if any(isglass_flags)and not all(isglass_flags):raise RuntimeError('Mixedopaque/glass source component requires per-slot glass handling')
   (glass if all(isglass_flags)else opaque).append(c)
   oldname=by_original[n['name']];role=moving.get(oldname);group=source_rows[oldname]['group'];assembly={'pocket-door':'bathroom','entry-door':'entry','patio-door':'balcony'}.get(group)
   if not assembly:assembly='entry'if oldname.startswith('SUB01_Entry')else'balcony'
   c.set_mobility(u.ComponentMobility.MOVABLE if role else u.ComponentMobility.STATIC);c.set_collision_profile_name('BlockAll');c.set_collision_enabled(u.CollisionEnabled.QUERY_AND_PHYSICS);c.set_editor_property('component_tags',[u.Name(TAG+('moving:'+role if role else'fixed:'+assembly))]);parts.append((a,c));origin,extent=a.get_actor_bounds(False)
   rows.append({'source_part':oldname,'name':n['name'],'actor':a.get_path_name(),'component':c.get_path_name(),'mesh':c.get_editor_property('static_mesh').get_path_name(),'moving_group':role,'assembly':assembly,'world_center_cm':[float(origin.x),float(origin.y),float(origin.z)],'world_extent_cm':[float(extent.x),float(extent.y),float(extent.z)],'full_source_geometry_verified':True})
  if len(parts)!=76:raise RuntimeError('Complete76actualdoorparts required')
  od=copy.deepcopy(d);glass_names={d['materials'][p['material']]['name']for m in d['meshes']for p in m['primitives']if d['materials'][p['material']].get('extensions',{}).get('KHR_materials_transmission',{}).get('transmissionFactor',0)>.5};od['materials']=[m for m in od['materials']if m['name']not in glass_names];pbr=verify_materials(u,opaque,od,dest,bindings);gm=clear_glass(u,dest)
  for c in glass:c.set_material(0,gm);c.set_editor_property('cast_shadow',False)
  if fingerprint(u,original)!=before:raise RuntimeError('Realdoor staging changed protectedhome')
  if not u.EditorAssetLibrary.save_directory(dest,only_if_is_dirty=False,recursive=True):raise RuntimeError('Realdoor asset save refused')
  active=True
  for a,c,*_ in retired:a.set_actor_hidden_in_game(True);a.set_is_temporarily_hidden_in_editor(True);c.set_visibility(False);c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
  for a,c in parts:a.set_actor_hidden_in_game(False);c.set_visibility(True)
  excluded={a.get_path_name()for a,c,*_ in retired};retained=[a for a in original if a.get_path_name()not in excluded]
  if fingerprint(u,retained)!={k:v for k,v in before.items()if k not in excluded}:raise RuntimeError('Door activation changed unrelatedhome')
  if not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Realdoor actualmap save refused')
  result.update(saved=True,parts=rows,retired=[a.get_path_name()for a,c,*_ in retired],preparation=preparation,owned_destination=dest,map_backup=str(backup),materials=pbr,originals_preserved=True,protected_originals_unchanged=True,source_roles=report['door_roles']);(audit/'authentic-doors-native.json').write_text(json.dumps(result,indent=2)+'\n');return result
 except Exception as error:
  for a,c,h,v,t,state in retired:a.set_actor_hidden_in_game(h);a.set_is_temporarily_hidden_in_editor(t);c.set_visibility(v);restore(u,c,state)
  cleanup=detach_added(u,eas,before);equal=fingerprint(u,original)==before;(audit/'authentic-doors-native-refusal.json').write_text(json.dumps({'error':str(error),'rollback_verified':equal,'quarantined_destination':dest,'backup':str(backup),'cleanup':cleanup},indent=2)+'\n')
  if not equal:raise RuntimeError('Realdoor rollback failed; retain backup andstop')from error
  if active and not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Realdoor rollbackmap save refused')from error
  raise
