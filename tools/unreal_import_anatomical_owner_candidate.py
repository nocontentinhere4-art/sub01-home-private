"""Import only the frozen serialized anatomical source into fresh candidate assets.

No owner assignment, map save, config write, contact grant or active Game changes.
Nonempty imported geometry is an initial diagnostic, never equivalence acceptance.
"""
from pathlib import Path
import hashlib,json,math,re,struct,time,uuid
SOURCE=Path('/home/unreal/runtime-tools/bath-owner65-Walk-final-pbr.glb')
SHA='fd2f3b8e521b99f8c02d142d1b80f9df0fe3d37bd762b2ca587e0408d53c9f0e'
DEST='/Game/Sub01Hands/AnatomicalCandidate/V_fd2f3b8e521b'
FBX=Path('/workspace/sub01-home-private/serialized-owner-fbx-final-r1/serialized-owner-diagnostic.fbx')
FBX_SHA='8027a9849bcfe37b24cab270b5ae972a5639b5bb524d41bcd527fe2d10361109'

def fbx_contract():
 assert hashlib.sha256(FBX.read_bytes()).hexdigest()==FBX_SHA
 d=json.loads((FBX.parent/'conversion-proof.json').read_text());assert d['source_sha256']==SHA and d['fbx_sha256']==FBX_SHA and d['no_bone_alignment_or_pose_as_rest']is True
 frames=d['source_GLTF_to_FBX_reimport'];assert set(frames)==set(map(str,range(32)))
 for rows in frames.values():
  assert len(rows)==9
  for r in rows:assert r['same_triangles']is True and math.isfinite(r['max_ordered_triangle_corner_error_m'])and 0<=r['max_ordered_triangle_corner_error_m']<=.00002
 assert d['only_exact_opposite_winding_doubleSided_duplicates_compacted']is True
 assert len(d['FBX_reimport_material_slots'])==9 and all(r['triangle_material_assignment_mismatches']==0 for r in d['FBX_reimport_material_slots'])
 return {'fbx_sha256':FBX_SHA,'all32_source_pose_geometry_proved':True,'source_native_PBR_and_TwoSided_still_pending':True}

def source_contract(raw):
 assert hashlib.sha256(raw).hexdigest()==SHA,'Frozen source bytes required'
 assert raw[:4]==b'glTF'and struct.unpack_from('<II',raw,4)==(2,len(raw))
 length,kind=struct.unpack_from('<I4s',raw,12);assert kind==b'JSON'
 j=json.loads(raw[20:20+length]);assert len(j['skins'])==1 and len(j['skins'][0]['joints'])==65
 assert all('uri'not in row for row in j.get('buffers',[])+j.get('images',[])),'Embedded source only'
 names=[j['nodes'][i]['name']for i in j['skins'][0]['joints']];assert len(set(names))==65
 parents={child:i for i,n in enumerate(j['nodes'])for child in n.get('children',[])}
 ancestry={j['nodes'][i]['name']:(j['nodes'][parents[i]]['name']if parents.get(i)in j['skins'][0]['joints']else None)for i in j['skins'][0]['joints']}
 nodes=[n for n in j['nodes']if 'mesh'in n];assert len(nodes)==9 and all(n.get('skin')==0 for n in nodes)
 assert len(j['animations'])==1 and j['animations'][0]['name']=='SUB01_Anatomical_Walk'and len(j['animations'][0]['channels'])==56
 return {'source_joint_names':names,'source_parents':ancestry,'source_skinned_nodes':len(nodes),'source_primitives':sum(len(j['meshes'][n['mesh']]['primitives'])for n in nodes),'source_position_vertices':sum(j['accessors'][p['attributes']['POSITION']]['count']for n in nodes for p in j['meshes'][n['mesh']]['primitives']),'source_triangles':sum(j['accessors'][p['indices']]['count']//3 for n in nodes for p in j['meshes'][n['mesh']]['primitives'])}

def run(dry_run=True,fbx=False):
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 import native_life_skeleton_parity as parity
 assert active_candidate_guard();contract=source_contract(SOURCE.read_bytes())
 if fbx:contract['fbx']=fbx_contract()
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);before=snapshot(u,eas.get_all_level_actors());mapfile=CANDIDATE/'Content/Sub01Home/ActualHome.umap';mapsha=hashlib.sha256(mapfile.read_bytes()).hexdigest()
 report={'schema':'sub01.anatomical-owner-candidate-import.v1','source_sha256':SHA,'contract':contract,'dry_run':dry_run,'owner_assigned':False,'world_changed':False,'map_saved':False,'config_changed':False,'native_ready':False,'contact_accepted':False,'geometry_equivalence_verified':False,'pose_equivalence_verified':False,'render_accepted':False,'started_epoch':time.time()}
 if dry_run:return report
 dest=(DEST if not fbx else '/Game/Sub01Hands/AnatomicalCandidate/FBX_V_'+FBX_SHA[:12])+'/Attempt_'+uuid.uuid4().hex;lib=u.EditorAssetLibrary
 assert not lib.does_directory_exist(dest)
 report['destination']=dest;report['format']='fbx'if fbx else'gltf';receipt=CANDIDATE/('private-audit/anatomical-owner-fbx-candidate.json'if fbx else'private-audit/anatomical-owner-gltf-candidate.json')
 try:
  task=u.AssetImportTask();task.filename=str(FBX if fbx else SOURCE);task.destination_path=dest;task.destination_name='AnatomicalOwner';task.automated=True;task.replace_existing=False;task.save=False
  if fbx:
   world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world();u.SystemLibrary.execute_console_command(world,'Interchange.FeatureFlags.Import.FBX 0')
   options=u.FbxImportUI()
   for k,v in [('automated_import_should_detect_type',False),('import_as_skeletal',True),('import_mesh',True),('import_animations',True),('import_materials',True),('import_textures',True),('create_physics_asset',False),('mesh_type_to_import',u.FBXImportType.FBXIT_SKELETAL_MESH)]:options.set_editor_property(k,v)
   skin=options.get_editor_property('skeletal_mesh_import_data');skin.set_editor_property('update_skeleton_reference_pose',False);skin.set_editor_property('use_t0_as_ref_pose',False)
   anim=options.get_editor_property('anim_sequence_import_data');anim.set_editor_property('use_default_sample_rate',False);anim.set_editor_property('custom_sample_rate',30)
   task.options=options
  u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task]);report['task_imported_paths']=list(map(str,task.imported_object_paths))
  assert all(p.startswith(dest+'/')for p in report['task_imported_paths'])
  remaining=u.Sub01HomeHandsInstance.finish_pending_skin_compilation();assert remaining==0
  paths=list(map(str,lib.list_assets(dest,recursive=True,include_folder=False)));assert paths and all(p.startswith(dest+'/')for p in paths)
  objects=[u.load_asset(p)for p in paths];meshes=[o for o in objects if isinstance(o,u.SkeletalMesh)];clips=[o for o in objects if isinstance(o,u.AnimSequence)]
  report.update(owned_paths=paths,mesh_count=len(meshes),clip_count=len(clips),meshes=[],clips=[])
  for mesh in meshes:
   probe=str(u.Sub01HomeHandsInstance.describe_imported_skin_geometry(mesh));bounds=mesh.get_bounds().box_extent
   row={'path':mesh.get_path_name(),'geometry_probe':probe,'bounds_extent_cm':[bounds.x,bounds.y,bounds.z],'skeleton':mesh.get_editor_property('skeleton').get_path_name()};report['meshes'].append(row)
   match=re.match(r'importedVertices=(\d+) lods=(\d+) softVertices=(\d+) ',probe)
   assert match and all(int(v)>0 for v in match.groups()),'Actual imported CPU geometry absent: '+probe
   assert all(math.isfinite(v)and v>0 for v in row['bounds_extent_cm'])
   c=u.SkeletalMeshComponent();c.set_skeletal_mesh_asset(mesh);names=[str(c.get_bone_name(i))for i in range(c.get_num_bones())];parents={n:(None if str(c.get_parent_bone(n))in('None','')else str(c.get_parent_bone(n)))for n in names};c.set_skeletal_mesh_asset(None)
   mapped=parity.map_owner_parents_to_ue(contract['source_parents'],names);structure=parity.structural_root_parity(names,parents,mapped,structure_only=True);row['skeleton_structure']=structure;assert structure['pass']
   row['material_slots']=[{'slot':str(m.get_editor_property('material_slot_name')),'material':m.get_editor_property('material_interface').get_path_name()if m.get_editor_property('material_interface')else None}for m in mesh.get_editor_property('materials')]
   if fbx:assert 100<2*max(row['bounds_extent_cm'])<300,'Actual imported full body must have physical centimeter dimensions'
  assert len(meshes)==1 and len(clips)==1,'One combined owner and captured Walk required; no active selection of split assets'
  mesh=meshes[0];skeleton=mesh.get_editor_property('skeleton')
  for clip in clips:
   assert clip.get_editor_property('skeleton')==skeleton
   report['clips'].append({'path':clip.get_path_name(),'duration_s':float(clip.get_editor_property('sequence_length')),'keys':int(u.AnimationLibrary.get_num_keys(clip)),'same_new_skeleton':True})
   assert abs(report['clips'][-1]['duration_s']-31/30)<1/30+.0001
  assert snapshot(u,eas.get_all_level_actors())==before and hashlib.sha256(mapfile.read_bytes()).hexdigest()==mapsha and active_candidate_guard()
  lib.save_directory(dest,only_if_is_dirty=False,recursive=True);report.update(assets_saved=True,initial_inventory_passed=True)
 except Exception as error:
  report.update(error=type(error).__name__,message=str(error),assets_saved=False,initial_inventory_passed=False)
  # Keep failed newly owned assets quarantined; never delete asynchronous imports.
  raise
 finally:
  report['candidate_world_snapshot_unchanged']=snapshot(u,eas.get_all_level_actors())==before
  report['candidate_map_unchanged']=hashlib.sha256(mapfile.read_bytes()).hexdigest()==mapsha
  report['finished_epoch']=time.time();receipt.write_text(json.dumps(report,indent=2)+'\n')
  assert report['candidate_world_snapshot_unchanged']and report['candidate_map_unchanged']
 return report
