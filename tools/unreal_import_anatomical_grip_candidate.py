"""Import the frozen matching-family Grip animation, never its transport meshes."""
from pathlib import Path
import hashlib,json,math,time,uuid
ROOT=Path('/workspace/sub01-home-private/serialized-owner-aux-final-r1/GamingGrip-bind-transport-fbx-r2')
FBX=ROOT/'captured-animation-only.fbx'
SHA='49c01512d4b6c192374c441ad710fdacfa9b78b138265ee050d0d0a4d121fa47'
SOURCE='7e74f67fca8af0e93d55e7023809f7d7ec84f70f15fbfeb3d659e545dea2a212'
FAMILY='fd2f3b8e521b99f8c02d142d1b80f9df0fe3d37bd762b2ca587e0408d53c9f0e'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def contract(proof):
 assert proof['schema']=='sub01.serialized-owner-animation-only-fbx-roundtrip.v1'
 assert proof['source_sha256']==SOURCE and proof['fbx_sha256']==SHA and proof['source_new_owner_family_sha256']==FAMILY
 assert proof['samples']==152 and proof['fps']==30 and proof['all65_joint_pose_samples']==9880 and proof['FBX_curve_key_counts']==[152]
 assert proof['same_axis_flags_as_validated_final_owner']is True
 for key,limit in [('maximum_world_joint_head_error_m',.00002),('maximum_pose_matrix_component_error',.00001),('maximum_bind_matrix_component_error',.00001)]:
  assert math.isfinite(proof[key])and 0<=proof[key]<=limit
 assert abs(proof['duration_seconds']-151/30)<1e-9
 return True

def run(dry_run=True):
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 assert active_candidate_guard();assert sha(FBX)==SHA;proof=json.loads((ROOT/'animation-conversion-proof.json').read_text());assert contract(proof)
 prior=json.loads((CANDIDATE/'private-audit/anatomical-owner-fbx-candidate.json').read_text());assert prior['initial_inventory_passed']and prior['source_sha256']==FAMILY
 mesh=u.load_asset(prior['meshes'][0]['path']);assert isinstance(mesh,u.SkeletalMesh);skeleton=mesh.get_editor_property('skeleton')
 package=skeleton.get_path_name().split('.')[0];skeletonfile=CANDIDATE/'Content'/Path(package.removeprefix('/Game/')).with_suffix('.uasset');skeletonsha=sha(skeletonfile)
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);before=snapshot(u,eas.get_all_level_actors());mapfile=CANDIDATE/'Content/Sub01Home/ActualHome.umap';mapsha=sha(mapfile)
 result={'schema':'sub01.anatomical-grip-candidate.v1','dry_run':dry_run,'source_sha256':SOURCE,'fbx_sha256':SHA,'skeleton':skeleton.get_path_name(),'owner_mesh':mesh.get_path_name(),'world_changed':False,'active_owner_changed':False,'contact_accepted':False,'native_ready':False}
 if dry_run:return result
 dest='/Game/Sub01Hands/AnatomicalCandidate/Grip_V_'+SHA[:12]+'/Attempt_'+uuid.uuid4().hex;lib=u.EditorAssetLibrary;assert not lib.does_directory_exist(dest);result['destination']=dest
 try:
  world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world();u.SystemLibrary.execute_console_command(world,'Interchange.FeatureFlags.Import.FBX 0')
  options=u.FbxImportUI()
  for key,value in [('automated_import_should_detect_type',False),('mesh_type_to_import',u.FBXImportType.FBXIT_ANIMATION),('import_as_skeletal',True),('import_mesh',False),('import_animations',True),('import_materials',False),('import_textures',False),('create_physics_asset',False),('skeleton',skeleton)]:options.set_editor_property(key,value)
  skin=options.get_editor_property('skeletal_mesh_import_data');skin.set_editor_property('update_skeleton_reference_pose',False);skin.set_editor_property('use_t0_as_ref_pose',False)
  anim=options.get_editor_property('anim_sequence_import_data');anim.set_editor_property('use_default_sample_rate',False);anim.set_editor_property('custom_sample_rate',30)
  task=u.AssetImportTask();task.filename=str(FBX);task.destination_path=dest;task.destination_name='AnatomicalGamingGrip';task.automated=True;task.replace_existing=False;task.save=False;task.options=options
  u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task]);paths=list(map(str,lib.list_assets(dest,recursive=True,include_folder=False)));assert paths and all(p.startswith(dest+'/')for p in paths)
  assets=[u.load_asset(p)for p in paths];clips=[a for a in assets if isinstance(a,u.AnimSequence)];assert len(clips)==1 and all(isinstance(a,u.AnimSequence)for a in assets),'Animation-only import must create exactly one clip and no meshes/materials/skeleton'
  clip=clips[0];assert clip.get_editor_property('skeleton')==skeleton;keys=int(u.AnimationLibrary.get_num_keys(clip));duration=float(clip.get_editor_property('sequence_length'));assert keys==152 and abs(duration-151/30)<.0001
  assert sha(skeletonfile)==skeletonsha and mesh.get_editor_property('skeleton')==skeleton
  assert snapshot(u,eas.get_all_level_actors())==before and sha(mapfile)==mapsha and active_candidate_guard()
  assert lib.save_asset(clip.get_path_name(),only_if_is_dirty=False)
  result.update(assets_saved=True,clip=clip.get_path_name(),keys=keys,duration_s=duration,matching_existing_new_skeleton=True,no_transport_mesh_imported=True,skeleton_file_unchanged=True,pose_and_visual_audit_pending=True)
 except Exception as error:
  result.update(assets_saved=False,error=type(error).__name__,message=str(error));raise
 finally:
  result['world_snapshot_unchanged']=snapshot(u,eas.get_all_level_actors())==before;result['map_unchanged']=sha(mapfile)==mapsha;result['finished_epoch']=time.time();(CANDIDATE/'private-audit/anatomical-grip-candidate.json').write_text(json.dumps(result,indent=2)+'\n');assert result['world_snapshot_unchanged']and result['map_unchanged']and sha(skeletonfile)==skeletonsha
 return result
