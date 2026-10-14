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
import sys
from pathlib import Path

import unreal as u

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inventory_native_life_clips as inventory_tool  # noqa: E402
import native_life_skeleton_parity as parity  # noqa: E402

ROLES = ('Idle', 'LieDown', 'SleepLoop', 'GetUp')
root = Path(u.Paths.project_dir()).resolve()
source = root / 'SourceAssets/LifeFBX'
dest = '/Game/Sub01Hands/Life'
audit = json.loads((source / 'life-fbx-audit.json').read_text())
inventory = json.loads((root / 'private-audit/native-life-clips-inventory.json').read_text())
receipt = root / 'unreal-fbx-hands-import.json'
if receipt.is_file():
    owner = json.loads(receipt.read_text())
    mesh = u.load_asset(owner['mesh'])
    skeleton = u.load_asset(owner['skeleton'])
    identity_basis = 'Existing import receipt plus actual owner/clip skeleton equality'
else:
    mesh = u.load_asset('/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner')
    typing = u.load_asset('/Game/Sub01Hands/FBX/SUB01_DeskTyping.SUB01_DeskTyping')
    if not isinstance(typing, u.AnimSequence):
        raise RuntimeError('Actual captured DeskTyping unavailable; no reconstructed historic receipt')
    skeleton = typing.get_editor_property('skeleton')
    identity_basis = 'Actual current owner and captured DeskTyping USkeleton equality; historic receipt unavailable'

if not isinstance(mesh, u.SkeletalMesh) or mesh.get_editor_property('skeleton') != skeleton:
    raise RuntimeError('Existing verified owner USkeleton unavailable; do not create a replacement')
if len(audit['bone_names']) != 65 or audit['bone_edits']:
    raise RuntimeError('Conversion source is not the verified unchanged 65-joint owner')
# The UE skeleton (66 bones: 65 skin joints + one structural parentless Mixamo node) against the
# owner's 65 skin joints and their parents; a raw count is never the test.
owner_ref = inventory_tool.owner_reference()
owner_parents = {n: (p if p in owner_ref['skin_joints'] else None)
                 for n, p in ((n, owner_ref['parents'].get(n)) for n in owner_ref['skin_joints'])}
u.Sub01HomeHandsInstance.finish_pending_skin_compilation()
probe = u.SkeletalMeshComponent()
probe.set_skeletal_mesh_asset(mesh)
ue_names = [str(probe.get_bone_name(i)) for i in range(probe.get_num_bones())]
ue_parents = {n: (None if str(probe.get_parent_bone(n)) in ('None', '') else str(probe.get_parent_bone(n))) for n in ue_names}
owner_parents = parity.map_owner_parents_to_ue(owner_parents, ue_names)
# Structure only here (names, parents, one parentless root); root motion is checked per clip below.
skeleton_parity = parity.structural_root_parity(ue_names, ue_parents, owner_parents,
                                                structure_only=True)
if not skeleton_parity['pass']:
    raise RuntimeError('UE skeleton is not the owner skeleton: ' + '; '.join(skeleton_parity['failures']))
u.log('SUB01_LIFE_SKELETON_PARITY ' + json.dumps({k: skeleton_parity[k] for k in ('ue_bone_count', 'owner_joint_count', 'structural_root')}))
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
    # The structural root must carry no motion in this clip: constant at 0, 3 and 8 s (clamped).
    samples = []
    if skeleton_parity['structural_root']:
        for t in parity.sample_times(duration):
            pose = u.AnimationLibrary.get_bone_poses_for_time(clip, [skeleton_parity['structural_root']], t, False, mesh)[0]
            loc, rot, scale = pose.translation, pose.rotation, pose.scale3d
            samples.append((t, (loc.x, loc.y, loc.z), (rot.x, rot.y, rot.z, rot.w), (scale.x, scale.y, scale.z)))
    clip_parity = parity.structural_root_parity(ue_names, ue_parents, owner_parents, samples)
    if not clip_parity['pass']:
        raise RuntimeError(f'{row["role"]}: owner skeleton parity failed: ' + '; '.join(clip_parity['failures']))
    rows.append({'role': row['role'], 'object_path': clip.get_path_name(), 'duration_s': duration,
                 'inventory_sha256': row['inventory_sha256'], 'same_existing_skeleton': True,
                 'skeleton_parity': clip_parity})
    u.log(f'SUB01_LIFE_IMPORTED role={row["role"]} path={clip.get_path_name()} duration={duration:.4f}')
u.EditorAssetLibrary.save_directory(dest, only_if_is_dirty=False, recursive=True)
(root / 'unreal-life-import.json').write_text(json.dumps({
    'owner': mesh.get_path_name(), 'skeleton': skeleton.get_path_name(), 'clips': rows,
    'bed_contact_verified': False, 'runtime_ready': False}, indent=2) + '\n')
