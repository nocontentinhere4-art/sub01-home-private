"""Official legacy FBX format fallback for actual original skin/captured clips."""
import json
from pathlib import Path
import unreal as u
root=Path(u.Paths.project_dir()).resolve();source=root/'SourceAssets/FBX';dest='/Game/Sub01Hands/FBX'
# Explicit official FBX importer, avoiding the empty glTF skeletal result.
world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
u.SystemLibrary.execute_console_command(world,'Interchange.FeatureFlags.Import.FBX 0')
def options(animation=False,skeleton=None):
 o=u.FbxImportUI();o.set_editor_property('automated_import_should_detect_type',False)
 o.set_editor_property('import_as_skeletal',True);o.set_editor_property('import_mesh',not animation)
 o.set_editor_property('import_animations',animation);o.set_editor_property('import_materials',not animation);o.set_editor_property('import_textures',not animation)
 o.set_editor_property('mesh_type_to_import',u.FBXImportType.FBXIT_ANIMATION if animation else u.FBXImportType.FBXIT_SKELETAL_MESH)
 if skeleton:o.set_editor_property('skeleton',skeleton)
 if animation:o.get_editor_property('anim_sequence_import_data').set_editor_property('use_default_sample_rate',True)
 return o
def load(filename,name,o):
 t=u.AssetImportTask();t.filename=str(source/filename);t.destination_path=dest;t.destination_name=name;t.automated=True;t.replace_existing=True;t.save=True;t.options=o
 u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t]);return [u.load_asset(p)for p in t.imported_object_paths]
objects=load('owner.fbx','SUB01_OriginalOwner',options())
meshes=[obj for obj in objects if isinstance(obj,u.SkeletalMesh)]
u.Sub01HomeHandsInstance.finish_pending_skin_compilation()
if len(meshes)!=1:raise RuntimeError('Expected one actual complete combined owner, got '+str(len(meshes)))
mesh=meshes[0];bounds=mesh.get_bounds().box_extent;probe=u.Sub01HomeHandsInstance.describe_imported_skin_geometry(mesh)
if any(v<=0 for v in [bounds.x,bounds.y,bounds.z]):raise RuntimeError('FBX fallback still lacks actual bounds: '+probe)
skeleton=mesh.get_editor_property('skeleton');clips={}
for file,role in [('typing','DeskTyping'),('texting','Phone'),('walking','Walk')]:
 objs=load(file+'.fbx','SUB01_'+role,options(True,skeleton));animations=[obj for obj in objs if isinstance(obj,u.AnimSequence)]
 if len(animations)!=1:raise RuntimeError('Actual FBX clip count differs '+file)
 clip=animations[0]
 expected={'typing':16.46666717529297,'texting':18.53333282470703,'walking':1.0333333015441895}[file]
 if abs(clip.get_editor_property('sequence_length')-expected)>2/30:raise RuntimeError('Actual FBX duration changed '+file)
 if clip.get_editor_property('skeleton')!=skeleton:raise RuntimeError('Actual FBX clip skeleton mismatch '+file)
 clips[role]={'object_path':clip.get_path_name(),'duration':clip.get_editor_property('sequence_length'),'same_actual_skeleton_verified':True,'physical_contact_verified':False,'pov_placement_verified':False}
report={'mesh':mesh.get_path_name(),'skeleton':skeleton.get_path_name(),'bounds_extent_cm':[bounds.x,bounds.y,bounds.z],'actual_geometry_probe':probe,'clips':clips,'runtime_ready':False,'scope':'Actual official FBX imported full original body and real captures; first-person contact/retarget/skin/render acceptance still pending.'}
u.EditorAssetLibrary.save_directory(dest,only_if_is_dirty=False,recursive=True)
(root/'unreal-fbx-hands-import.json').write_text(json.dumps(report,indent=2)+'\n')
u.log('SUB01_ACTUAL_FBX_HANDS_IMPORTED '+json.dumps(report))
