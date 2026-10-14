"""SERVER ONLY (root): import the captured life clips onto the EXISTING verified owner USkeleton
as /Game/Sub01Hands/Life/SUB01_<Role>.

    UnrealEditor-Cmd <project>/Sub01HomeLab.uproject -ExecutePythonScript="<repo>/tools/unreal_import_life_fbx.py" -unattended

Reads SourceAssets/LifeFBX/life-fbx-audit.json (tools/export_unreal_life_fbx.py for GLB sources,
or `unreal_life_clips_runtime.py audit-fbx` for an operator FBX) and private-audit/
native-life-clips-inventory.json (tools/inventory_native_life_clips.py). Imports only roles whose
exact bytes the inventory accepted. Does not replace the owner mesh or skeleton, edit bones, pose,
enable playback, bind config or claim bed contact. Writes unreal-life-import.json for
`unreal_life_clips_runtime.py config`.
"""
import hashlib
import json
from pathlib import Path

import unreal as u

ROLES = ('Idle', 'LieDown', 'SleepLoop', 'GetUp')
root = Path(u.Paths.project_dir()).resolve()
source = root / 'SourceAssets/LifeFBX'
dest = '/Game/Sub01Hands/Life'
audit = json.loads((source / 'life-fbx-audit.json').read_text())
inventory = json.loads((root / 'private-audit/native-life-clips-inventory.json').read_text())
owner = json.loads((root / 'unreal-fbx-hands-import.json').read_text())
mesh = u.load_asset(owner['mesh'])
skeleton = u.load_asset(owner['skeleton'])
if not isinstance(mesh, u.SkeletalMesh) or mesh.get_editor_property('skeleton') != skeleton:
    raise RuntimeError('Existing verified owner USkeleton unavailable; do not create a replacement')
if len(audit['bone_names']) != 65 or audit['bone_edits']:
    raise RuntimeError('Conversion source is not the verified unchanged 65-joint owner')
accepted = {(c['role'], c['sha256']) for c in inventory['candidates'] if c.get('verdict') == 'Candidate'}
u.Sub01HomeHandsInstance.finish_pending_skin_compilation()
world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
u.SystemLibrary.execute_console_command(world, 'Interchange.FeatureFlags.Import.FBX 0')
rows = []
for row in audit['clips']:
    if row['role'] not in ROLES:
        raise RuntimeError('Unknown life role ' + row['role'])
    if (row['role'], row['inventory_sha256']) not in accepted:
        raise RuntimeError(f'{row["role"]}: source is not an accepted inventory capture; nothing is substituted')
    path = source / row['file']
    if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
        raise RuntimeError('Source FBX changed since conversion')
    options = u.FbxImportUI()
    options.set_editor_property('automated_import_should_detect_type', False)
    options.set_editor_property('import_as_skeletal', True)
    options.set_editor_property('import_mesh', False)
    options.set_editor_property('import_animations', True)
    options.set_editor_property('import_materials', False)
    options.set_editor_property('import_textures', False)
    options.set_editor_property('mesh_type_to_import', u.FBXImportType.FBXIT_ANIMATION)
    options.set_editor_property('skeleton', skeleton)
    options.get_editor_property('anim_sequence_import_data').set_editor_property('use_default_sample_rate', True)
    task = u.AssetImportTask()
    task.filename = str(path)
    task.destination_path = dest
    task.destination_name = 'SUB01_' + row['role']
    task.automated = True
    task.replace_existing = True
    task.save = True
    task.options = options
    u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    clips = [c for c in (u.load_asset(p) for p in task.imported_object_paths) if isinstance(c, u.AnimSequence)]
    if len(clips) != 1 or clips[0].get_editor_property('skeleton') != skeleton:
        raise RuntimeError('Imported life sequence differs from the actual owner skeleton')
    clip = clips[0]
    duration = clip.get_editor_property('sequence_length')
    if abs(duration - row['duration_s']) > 2 / 30:
        raise RuntimeError('Source life capture duration changed in UE')
    rows.append({'role': row['role'], 'object_path': clip.get_path_name(), 'duration_s': duration,
                 'inventory_sha256': row['inventory_sha256'], 'same_existing_skeleton': True})
    u.log(f'SUB01_LIFE_IMPORTED role={row["role"]} path={clip.get_path_name()} duration={duration:.4f}')
u.EditorAssetLibrary.save_directory(dest, only_if_is_dirty=False, recursive=True)
(root / 'unreal-life-import.json').write_text(json.dumps({
    'owner': mesh.get_path_name(), 'skeleton': skeleton.get_path_name(), 'clips': rows,
    'bed_contact_verified': False, 'runtime_ready': False}, indent=2) + '\n')
