"""SERVER ONLY official FBX animation import against EXISTING verified full owner.
Does not replace owner/skeleton, set poses, activate playback or publish seated feedback.
"""
import hashlib,json
from pathlib import Path
import unreal as u
root=Path(u.Paths.project_dir()).resolve();source=root/'SourceAssets/SeatingFBX';dest='/Game/Sub01Hands/Seating'
audit=json.loads((source/'seating-fbx-audit.json').read_text());owner=json.loads((root/'unreal-fbx-hands-import.json').read_text())
mesh=u.load_asset(owner['mesh']);skeleton=u.load_asset(owner['skeleton'])
if not isinstance(mesh,u.SkeletalMesh)or mesh.get_editor_property('skeleton')!=skeleton:raise RuntimeError('Existing verified owner USkeleton unavailable; do not create replacement')
if len(audit['bone_names'])!=65 or audit['bone_edits']:raise RuntimeError('Conversion source is not verified unchanged65joint owner')
u.Sub01HomeHandsInstance.finish_pending_skin_compilation()
if any(v<=0 for v in [mesh.get_bounds().box_extent.x,mesh.get_bounds().box_extent.y,mesh.get_bounds().box_extent.z]):raise RuntimeError('Actual owner geometry is empty')
world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world();u.SystemLibrary.execute_console_command(world,'Interchange.FeatureFlags.Import.FBX 0')
rows=[]
for row in audit['clips']:
 path=source/row['file']
 if hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:raise RuntimeError('Source FBX changed since conversion')
 options=u.FbxImportUI();options.set_editor_property('automated_import_should_detect_type',False);options.set_editor_property('import_as_skeletal',True);options.set_editor_property('import_mesh',False);options.set_editor_property('import_animations',True);options.set_editor_property('import_materials',False);options.set_editor_property('import_textures',False);options.set_editor_property('mesh_type_to_import',u.FBXImportType.FBXIT_ANIMATION);options.set_editor_property('skeleton',skeleton);options.get_editor_property('anim_sequence_import_data').set_editor_property('use_default_sample_rate',True)
 task=u.AssetImportTask();task.filename=str(path);task.destination_path=dest;task.destination_name='SUB01_'+row['role'];task.automated=True;task.replace_existing=True;task.save=True;task.options=options
 u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task]);clips=[u.load_asset(p)for p in task.imported_object_paths];clips=[c for c in clips if isinstance(c,u.AnimSequence)]
 if len(clips)!=1 or clips[0].get_editor_property('skeleton')!=skeleton:raise RuntimeError('Imported seating sequence differs from actual owner skeleton')
 clip=clips[0];duration=clip.get_editor_property('sequence_length')
 if abs(duration-row['duration_s'])>2/30:raise RuntimeError('Source seating capture duration changed in UE')
 rows.append({'role':row['role'],'object_path':clip.get_path_name(),'duration_s':duration,'same_existing_skeleton':True,'physical_contact_verified':False})
u.EditorAssetLibrary.save_directory(dest,only_if_is_dirty=False,recursive=True)
(root/'unreal-seating-import.json').write_text(json.dumps({'owner':mesh.get_path_name(),'skeleton':skeleton.get_path_name(),'clips':rows,'seat_collider_verified':False,'continuous_approach_sit_get_up_verified':False,'runtime_ready':False},indent=2)+'\n')
