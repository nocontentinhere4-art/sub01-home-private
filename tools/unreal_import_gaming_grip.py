"""SERVER ONLY (root): import the DERIVED controller grip clip onto the EXISTING verified owner USkeleton
as /Game/Sub01Hands/Play/SUB01_GamingGrip (the clip tools/unreal_controller_play_runtime.py plays).

    UnrealEditor-Cmd <project>/Sub01HomeLab.uproject -ExecutePythonScript="<repo>/tools/unreal_import_gaming_grip.py" -unattended

Modelled on tools/unreal_import_life_fbx.py. Reads <project>/SourceAssets/ControllerFBX/gaming-grip-fbx-audit.json and
the FBX it names (tools/export_unreal_gaming_grip_fbx.py, from the owner skin merged with
docs/proposed/controller-play/SUB01_GamingGrip_derived.glb). Owner skeleton only: it never creates or replaces a
skeleton or mesh, edits bones, poses, binds config or claims grip/sofa/input readiness. It refuses (RuntimeError,
no receipt) when the audit is not the exact derived clip, the source FBX changed, the UE skeleton fails
tools/native_life_skeleton_parity.py, the imported clip is on another skeleton, its duration differs, or its
structural root moves. It never replaces or deletes an existing real asset: a pre-existing destination is
preserved when its import receipt names the same source/skeleton/duration and refused (without any mutation)
otherwise. A new import goes into a unique transaction-owned staging path, is verified there and only then renamed
to the absent final path; on failure only the paths this transaction created are deleted. On success it writes
<project>/unreal-gaming-grip-import.json, the IMPORT_REPORT for
`python tools/unreal_controller_play_runtime.py config <project> unreal-gaming-grip-import.json OUT.ini`.
"""
from __future__ import annotations

import hashlib
import json
import sys
import uuid
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import native_life_skeleton_parity as parity  # noqa: E402
import controller_clip_contract as controller  # noqa: E402

ROLE = controller.ROLE                                    # 'Gaming'
DEST = '/Game/Sub01Hands/Play'
ASSET_NAME = 'SUB01_GamingGrip'
FINAL_PACKAGE = f'{DEST}/{ASSET_NAME}'
STAGING_DIR = f'{DEST}/_Staging'
OBJECT_PATH = controller.CLIP_OBJECT_PATH                 # /Game/Sub01Hands/Play/SUB01_GamingGrip.SUB01_GamingGrip
OWNER_MESH = '/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner'
OWNER_TYPING = '/Game/Sub01Hands/FBX/SUB01_DeskTyping.SUB01_DeskTyping'
SOURCE_DIR = 'SourceAssets/ControllerFBX'
AUDIT_FILE = 'gaming-grip-fbx-audit.json'
AUDIT_SCHEMA = 'sub01.gaming-grip-fbx-audit.v1'
RECEIPT_FILE = 'unreal-gaming-grip-import.json'
RECEIPT_SCHEMA = 'sub01.unreal-gaming-grip-import.v1'
DERIVED_GLB = 'docs/proposed/controller-play/SUB01_GamingGrip_derived.glb'
DERIVED_GLB_SHA256 = 'bf31d64518d85f6eefd8150009a758ddddc95ca6afd63d5d83bdf29a2dcdaaf9'
FRAMES = controller.CLIP_FRAMES                           # 152 keys at 30 fps
NATIVE_DURATION_S = (FRAMES - 1) / 30                     # first glTF key is 1/30 s; native t = glTF t - 1/30
DURATION_TOLERANCE_S = 2 / 30


def check_audit(audit: dict) -> dict:
    """The conversion audit must describe exactly the derived grip clip on the unchanged 65-joint owner."""
    if audit.get('schema') != AUDIT_SCHEMA:
        raise RuntimeError('Not a Gaming grip FBX conversion audit')
    if len(audit.get('bone_names', [])) != 65 or audit.get('bone_edits') is not False or audit.get('fps') != 30:
        raise RuntimeError('Conversion source is not the verified unchanged 65-joint owner at 30 fps')
    clips = audit.get('clips', [])
    if len(clips) != 1 or clips[0].get('role') != ROLE:
        raise RuntimeError('Expected exactly one Gaming grip clip; nothing is substituted')
    row = clips[0]
    if row.get('derived_glb_sha256') != DERIVED_GLB_SHA256:
        raise RuntimeError('Source is not the committed derived grip GLB (bf31d645...)')
    if row.get('source_fbx_sha256') != controller.GAMING_FBX_SHA256:
        raise RuntimeError("Derived grip is not declared from the owner's captured Gaming.fbx")
    if row.get('frames') != FRAMES or abs(float(row.get('duration_s', -1)) - NATIVE_DURATION_S) > 1e-3:
        raise RuntimeError('Derived grip frame count or duration changed')
    return row


def resolve_owner(u, root: Path):
    """The existing owner mesh and USkeleton; never a replacement (same rule as the life/seating importers)."""
    receipt = root / 'unreal-fbx-hands-import.json'
    if receipt.is_file():
        owner = json.loads(receipt.read_text())
        mesh, skeleton = u.load_asset(owner['mesh']), u.load_asset(owner['skeleton'])
        basis = 'Existing import receipt plus actual owner/clip skeleton equality'
    else:
        mesh = u.load_asset(OWNER_MESH)
        typing = u.load_asset(OWNER_TYPING)
        if not isinstance(typing, u.AnimSequence):
            raise RuntimeError('Actual captured DeskTyping unavailable; no reconstructed historic receipt')
        skeleton = typing.get_editor_property('skeleton')
        basis = 'Actual current owner and captured DeskTyping USkeleton equality; historic receipt unavailable'
    if not isinstance(mesh, u.SkeletalMesh) or skeleton is None or mesh.get_editor_property('skeleton') != skeleton:
        raise RuntimeError('Existing verified owner USkeleton unavailable; do not create a replacement')
    return mesh, skeleton, basis


def owner_parents_default(root: Path | None = None):
    if root is not None:
        from verified_owner_skeleton import read_project_owner_parents
        return read_project_owner_parents(root)
    import inventory_native_life_clips as inventory_tool
    ref = inventory_tool.owner_reference()
    return {n: (p if p in ref['skin_joints'] else None)
            for n, p in ((n, ref['parents'].get(n)) for n in ref['skin_joints'])}


def package_of(path: str) -> str:
    return str(path).split('.', 1)[0]


def preserve_existing(u, root: Path, row: dict, skeleton) -> dict:
    """An existing final asset is never replaced or deleted. It is kept only when its own import receipt names this
    exact source and the asset still matches it; otherwise refuse without touching anything."""
    receipt_path = root / RECEIPT_FILE
    refusal = f'{FINAL_PACKAGE} already exists'
    if not receipt_path.is_file():
        raise RuntimeError(refusal + ' without an import receipt; left untouched, nothing imported')
    receipt = json.loads(receipt_path.read_text())
    clips = receipt.get('clips') or [{}]
    entry = clips[0]
    expected = {'object_path': OBJECT_PATH, 'role': ROLE, 'fbx_sha256': row['sha256'],
                'source_fbx_sha256': row['source_fbx_sha256'], 'derived_glb_sha256': row['derived_glb_sha256']}
    if receipt.get('schema') != RECEIPT_SCHEMA or len(clips) != 1 or any(entry.get(k) != v for k, v in expected.items()):
        raise RuntimeError(refusal + ' but its receipt names another source; left untouched, nothing imported')
    clip = u.load_asset(OBJECT_PATH)
    if not isinstance(clip, u.AnimSequence) or clip.get_editor_property('skeleton') != skeleton:
        raise RuntimeError(refusal + ' but is not on the owner skeleton; left untouched, nothing imported')
    duration = clip.get_editor_property('sequence_length')
    if (abs(duration - NATIVE_DURATION_S) > DURATION_TOLERANCE_S
            or abs(duration - float(entry.get('duration_s', -1))) > 1e-4):
        raise RuntimeError(refusal + ' but its duration differs from its receipt; left untouched, nothing imported')
    u.log(f'SUB01_GAMING_GRIP_PRESERVED path={OBJECT_PATH} duration={duration:.4f}')
    return dict(receipt, preserved_existing=True)


def main(u, root: Path | None = None, owner_parents: dict | None = None) -> dict:
    root = Path(root or u.Paths.project_dir()).resolve()
    source = root / SOURCE_DIR
    row = check_audit(json.loads((source / AUDIT_FILE).read_text()))
    path = source / row['file']
    if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
        raise RuntimeError('Source FBX changed since conversion')
    mesh, skeleton, basis = resolve_owner(u, root)
    u.Sub01HomeHandsInstance.finish_pending_skin_compilation()
    probe = u.SkeletalMeshComponent()
    probe.set_skeletal_mesh_asset(mesh)
    ue_names = [str(probe.get_bone_name(i)) for i in range(probe.get_num_bones())]
    ue_parents = {n: (None if str(probe.get_parent_bone(n)) in ('None', '') else str(probe.get_parent_bone(n))) for n in ue_names}
    owner = parity.map_owner_parents_to_ue(owner_parents or owner_parents_default(root), ue_names)
    skeleton_parity = parity.structural_root_parity(ue_names, ue_parents, owner, structure_only=True)
    if not skeleton_parity['pass']:
        raise RuntimeError('UE skeleton is not the owner skeleton: ' + '; '.join(skeleton_parity['failures']))
    lib = u.EditorAssetLibrary
    if lib.does_asset_exist(FINAL_PACKAGE):
        return preserve_existing(u, root, row, skeleton)
    txid = uuid.uuid4().hex[:12]
    staged_name = f'{ASSET_NAME}_{txid}'
    staged_package = f'{STAGING_DIR}/{staged_name}'
    staged_object = f'{staged_package}.{staged_name}'
    if lib.does_asset_exist(staged_package):
        raise RuntimeError(f'Staging path {staged_package} already exists; nothing imported')
    before = {package_of(p) for p in (lib.list_assets(STAGING_DIR, recursive=True, include_folder=False)
                                      if lib.does_directory_exist(STAGING_DIR) else [])}
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    u.SystemLibrary.execute_console_command(world, 'Interchange.FeatureFlags.Import.FBX 0')
    options = u.FbxImportUI()
    for key, value in (('automated_import_should_detect_type', False), ('import_as_skeletal', True), ('import_mesh', False),
                       ('import_animations', True), ('import_materials', False), ('import_textures', False),
                       ('mesh_type_to_import', u.FBXImportType.FBXIT_ANIMATION), ('skeleton', skeleton)):
        options.set_editor_property(key, value)
    options.get_editor_property('anim_sequence_import_data').set_editor_property('use_default_sample_rate', True)
    task = u.AssetImportTask()
    task.filename, task.destination_path, task.destination_name = str(path), STAGING_DIR, staged_name
    task.automated, task.replace_existing, task.save, task.options = True, False, False, options
    u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    after = {package_of(p) for p in lib.list_assets(STAGING_DIR, recursive=True, include_folder=False)}
    owned = sorted(after - before)                    # created by this transaction; nothing else is ever deleted
    stray = sorted({package_of(p) for p in task.imported_object_paths} - set(owned))

    def refuse(why):
        for p in owned:
            if lib.does_asset_exist(p):
                lib.delete_asset(p)
        raise RuntimeError(why + (f' (untouched non-staging import output: {stray})' if stray else ''))

    if stray:
        refuse('Import wrote outside its transaction staging path')
    clips = [c for c in (u.load_asset(p) for p in task.imported_object_paths) if isinstance(c, u.AnimSequence)]
    if len(clips) != 1 or clips[0].get_editor_property('skeleton') != skeleton:
        refuse('Imported grip sequence differs from the actual owner skeleton')
    clip = clips[0]
    if clip.get_path_name() != staged_object:
        refuse(f'Imported grip is {clip.get_path_name()}, expected staging {staged_object}')
    duration = clip.get_editor_property('sequence_length')
    if abs(duration - NATIVE_DURATION_S) > DURATION_TOLERANCE_S:
        refuse(f'Grip duration {duration:.4f} s differs from {NATIVE_DURATION_S:.4f} s')
    samples = []
    if skeleton_parity['structural_root']:
        for t in parity.sample_times(duration):
            pose = u.AnimationLibrary.get_bone_poses_for_time(clip, [skeleton_parity['structural_root']], t, False, mesh)[0]
            loc, rot, scale = pose.translation, pose.rotation, pose.scale3d
            samples.append((t, (loc.x, loc.y, loc.z), (rot.x, rot.y, rot.z, rot.w), (scale.x, scale.y, scale.z)))
    clip_parity = parity.structural_root_parity(ue_names, ue_parents, owner, samples)
    if not clip_parity['pass']:
        refuse('Owner skeleton parity failed: ' + '; '.join(clip_parity['failures']))
    if lib.does_asset_exist(FINAL_PACKAGE):
        refuse(f'{FINAL_PACKAGE} appeared during import; existing asset left untouched')
    if not lib.rename_asset(staged_package, FINAL_PACKAGE):
        refuse(f'Could not move verified staging clip to {FINAL_PACKAGE}')
    owned.append(FINAL_PACKAGE)                       # created by this transaction's rename
    clip = u.load_asset(OBJECT_PATH)
    if not isinstance(clip, u.AnimSequence) or clip.get_editor_property('skeleton') != skeleton:
        refuse('Renamed grip clip did not load on the owner skeleton')
    for p in owned[:-1]:                              # leftover redirectors/side outputs in staging
        if lib.does_asset_exist(p):
            lib.delete_asset(p)
    if not lib.save_asset(FINAL_PACKAGE, only_if_is_dirty=False):
        refuse(f'Could not save {FINAL_PACKAGE}; this run\'s clip removed, earlier receipt untouched')
    receipt = {'schema': RECEIPT_SCHEMA, 'owner': mesh.get_path_name(), 'skeleton': skeleton.get_path_name(),
               'identity_basis': basis, 'transaction_id': txid, 'staging_path': staged_package,
               'clips': [{'role': ROLE, 'object_path': clip.get_path_name(), 'duration_s': duration, 'frames': FRAMES,
                          'same_existing_skeleton': True, 'skeleton_parity': clip_parity,
                          'source_fbx_sha256': row['source_fbx_sha256'], 'derived_glb_sha256': row['derived_glb_sha256'],
                          'fbx_sha256': row['sha256']}],
               'controller_grip_verified': False, 'sofa_contact_verified': False, 'runtime_ready': False}
    tmp = root / (RECEIPT_FILE + f'.{txid}.tmp')
    tmp.write_text(json.dumps(receipt, indent=2) + '\n')
    tmp.replace(root / RECEIPT_FILE)
    u.log(f'SUB01_GAMING_GRIP_IMPORTED path={clip.get_path_name()} duration={duration:.4f}')
    return receipt


if __name__ == '__main__':
    import unreal
    main(unreal)
