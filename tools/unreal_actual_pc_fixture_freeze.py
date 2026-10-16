"""Read-only freeze of native visible office surfaces and effective R9 bindings."""
from pathlib import Path
import hashlib,json,time

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE,trusted_json,SCOPE
 from unreal_import_reference_entry import snapshot
 from impulse_sofa_seating_probe_ue58 import transform,vector
 started=time.monotonic();limit=started+170
 assert active_candidate_guard();eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors)
 sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();mapfile=CANDIDATE/'Content/Sub01Home/ActualHome.umap';mapsha=sha(mapfile);assert mapsha==sha(Path('/workspace/sub01-private-playable-kitchen-r1-20261016/Sub01HomeLab/Content/Sub01Home/ActualHome.umap'))=='5efc164c7bf8e11a49cec3d8c18bf9d8cb9ba19cb4fb1cd202043641b7657976'
 target=CANDIDATE/'private-audit'/('actual-pc-fixture-'+str(time.time_ns()));target.mkdir()
 selected=[];excluded=[];geometry=[];errors=[];assetfiles={};sourcefiles={}
 wanted_nodes={181,182,184,185,186,187,236,237,238,*range(246,253)}
 for a in actors:
  name=a.get_name();label=a.get_actor_label();node=int(name.rsplit('_',1)[1])if name.startswith('full-home_node_')else None
  if not(node in wanted_nodes or 'RealLinea140' in label or any(k in label.lower()for k in['keyboard','keycap'])):continue
  for c in a.get_components_by_class(u.StaticMeshComponent):
   assert time.monotonic()<limit,'170 second bounded extraction expired'
   mesh=c.get_editor_property('static_mesh')
   if mesh is None:continue
   hidden=bool(a.get_editor_property('hidden'));visible=bool(c.get_editor_property('visible'));hidden_component=bool(c.get_editor_property('hidden_in_game'));editor_hidden=bool(a.is_temporarily_hidden_in_editor())
   row={'actor':a.get_path_name(),'label':label,'component':c.get_path_name(),'mesh':mesh.get_path_name(),'actor_world_transform':transform(a.get_actor_transform()),'component_world_transform':transform(c.get_world_transform()),'actor_hidden_in_game':hidden,'component_visible':visible,'component_hidden_in_game':hidden_component,'editor_temporarily_hidden':editor_hidden,'render_visible_in_game':not hidden and visible and not hidden_component,'collision_profile':str(c.get_collision_profile_name()),'collision_enabled':str(c.get_collision_enabled()),'collision_object_type':str(c.get_collision_object_type()),'materials':[c.get_material(i).get_path_name()if c.get_material(i)else None for i in range(c.get_num_materials())],'source_full_geometry_verified':False}
   try:row['nanite_enabled']=bool(mesh.get_editor_property('nanite_settings').enabled)
   except Exception as exc:row['nanite_read_error']=str(exc)
   try:
    row['asset_import_sources']=list(mesh.get_editor_property('asset_import_data').extract_filenames())
    for filename in row['asset_import_sources']:
     p=Path(filename)
     if p.is_file()and str(p)not in sourcefiles:sourcefiles[str(p)]=sha(p)
   except Exception as exc:row['import_source_read_error']=str(exc)
   package=mesh.get_path_name().split('.',1)[0];file=CANDIDATE/'Content'/(package.removeprefix('/Game/')+'.uasset')
   if file.is_file():assetfiles[str(file)]={'sha256':sha(file),'bytes':file.stat().st_size}
   if not row['render_visible_in_game']:excluded.append(row);continue
   selected.append(row)
   sections=[]
   for section in range(mesh.get_num_sections(0)):
    vertices,indices,normals,*_=u.ProceduralMeshLibrary.get_section_from_static_mesh(mesh,0,section)
    world=c.get_world_transform();sections.append({'section':section,'vertices_world_cm':[vector(world.transform_location(v))for v in vertices],'vertices_local_cm':[vector(v)for v in vertices],'normals_local':[vector(n)for n in normals],'triangle_indices':[list(indices[i:i+3])for i in range(0,len(indices),3)]})
   geometry.append({'component':c.get_path_name(),'mesh':mesh.get_path_name(),'lod':0,'representation':'actual native StaticMesh section LOD0; Nanite source parity not asserted','sections':sections})
 for name,value in [('visible-components.json',selected),('excluded-hidden-components.json',excluded),('native-section-geometry.json',geometry)]:
  (target/name).write_text(json.dumps(value,separators=(',',':')))
 # A transient, unregistered UObject reads mesh bone identities; no actor or camera exists.
 config=CANDIDATE/'Config/DefaultGame.ini';live=Path('/workspace/sub01-private-playable-kitchen-r1-20261016/Sub01HomeLab');liveconfig=live/'Config/DefaultGame.ini';assert sha(liveconfig)=='a46b973bc17d64a11743ef5fc04b12e0ee8b0a65feb0a2ec72944964f3fc40eb'
 values={};validated=[]
 for raw in liveconfig.read_text().splitlines():
  line=raw.strip()
  if line.startswith('!ValidatedHandsPostures='):validated=[]
  elif line.startswith('+ValidatedHandsPostures='):validated.append(line.split('=',1)[1])
  elif'='in line and not line.startswith((';','#','[')):
   k,v=line.split('=',1);values[k]=v
 ownerpath=values['HandsMeshPath'];mesh=u.load_asset(ownerpath);assert mesh is not None
 temp=u.SkeletalMeshComponent();temp.set_skeletal_mesh_asset(mesh);names=[str(temp.get_bone_name(i))for i in range(temp.get_num_bones())];parents={n:str(temp.get_parent_bone(n))for n in names};temp.set_skeletal_mesh_asset(None)
 fingers=[n for n in names if 'Hand'in n and not n.endswith('Hand')];assert len(names)==66 and len(fingers)==40
 skeleton=mesh.get_editor_property('skeleton').get_path_name();clips=[]
 for role,key in [('Walk','WalkClipPath'),('Idle','IdleClipPath')]:
  clip=u.load_asset(values[key]);assert clip and clip.get_editor_property('skeleton')==mesh.get_editor_property('skeleton');count=32 if role=='Walk'else 76;duration=(count-1)/30;samples=[]
  for i in range(count):
   assert time.monotonic()<limit,'170 second bounded extraction expired'
   t=duration*i/(count-1)if count>1 else 0;poses=u.AnimationLibrary.get_bone_poses_for_time(clip,[u.Name(n)for n in names],t,False,mesh);samples.append({'sample_index':i,'time_seconds':t,'local_transforms':[transform(p)for p in poses]})
  clips.append({'role':role,'clip':clip.get_path_name(),'sample_count':count,'duration_seconds':duration,'samples':samples})
  file=live/'Content'/(clip.get_path_name().split('.',1)[0].removeprefix('/Game/')+'.uasset');assert sha(file)==sha(CANDIDATE/file.relative_to(live));assetfiles[str(file)]={'sha256':sha(file),'bytes':file.stat().st_size}
 for obj in[ownerpath,skeleton]:
  file=live/'Content'/(obj.split('.',1)[0].removeprefix('/Game/')+'.uasset');assetfiles[str(file)]={'sha256':sha(file),'bytes':file.stat().st_size}
 baseline={'mesh':ownerpath,'skeleton':skeleton,'bones':names,'parents':parents,'finger_bones':fingers,'clips':clips,'validated_config_roles':validated,'typing_clip_config_value':values.get('TypingClipPath',''),'typing_role_validated':'DeskTyping'in validated,'compatible_approved_typing_baseline_exists':False,'live_current_role_not_queried':True,'configuration_binding_conclusion':'No DeskTyping binding can pass current validated role list. Walk and Idle are supplied as their real roles, not relabelled Typing.','source_basis_reference':'approved anatomical owner import receipt and immutable serialized source; no native reference-pose export fabricated'}
 for obj in[selected,excluded,geometry,baseline]:assert obj is not None
 assert active_candidate_guard()and snapshot(u,eas.get_all_level_actors())==before and sha(mapfile)==mapsha
 payloads={'visible-components.json':selected,'excluded-hidden-components.json':excluded,'native-section-geometry.json':geometry,'approved-r9-current-bindings.json':baseline}
 files={}
 for name,value in payloads.items():
  p=target/name;p.write_text(json.dumps(value,separators=(',',':')));files[name]={'sha256':sha(p),'bytes':p.stat().st_size}
 report={'schema':'sub01.actual-visible-pc-fixture-freeze.v1','live_game_identity':[239638,980813701],'visibility_scope':'actual saved candidate world with exactly same UMAP bytes as live; no live actor queries or input','source_receipts':{n:{'path':str(CANDIDATE/'private-audit'/n),'sha256':sha(CANDIDATE/'private-audit'/n)}for n in ['anatomical-owner-fbx-candidate.json','anatomical-body-pose-audit.json','anatomical-source-material-binding.json','anatomical-idle-candidate.json']},'authoritative_r9_source':{'path':'/home/unreal/runtime-tools/bath-owner65-Walk-final-pbr.glb','sha256':sha('/home/unreal/runtime-tools/bath-owner65-Walk-final-pbr.glb'),'role':'source Walk and serialized anatomical rest/skin basis; not Typing','native_reference_pose_exported':False},'output':str(target),'files':files,'asset_files':assetfiles,'import_source_files':sourcefiles,'selected_visible_components':len(selected),'excluded_hidden_components':len(excluded),'map_sha256':mapsha,'world_unchanged':True,'input_delivered':False,'camera_changed':False,'map_saved':False,'elapsed_seconds':time.monotonic()-started,'actual_colliders_identified_by_component_settings':True,'collision_triangle_mesh_equals_render_sections_not_asserted':True,'source_full_geometry_verified':False,'contact_ready':False,'typing_ready':False}
 p=target/'freeze-report.json';p.write_text(json.dumps(report,indent=2));return {'output':str(target),'report_sha256':sha(p),'visible_components':len(selected),'typing_baseline_exists':False,'world_unchanged':True,'contact_ready':False}
