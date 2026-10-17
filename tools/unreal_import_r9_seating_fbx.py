"""SERVER ONLY: import the authored R9 planted seat chain onto the ACTIVE anatomical owner.

unreal_import_seating_fbx.py targets the retired SUB01_OriginalOwner; the Game now
binds AnatomicalOwner and loads /Game/Sub01Hands/Seating/SUB01_{SitDown,Sitting,
SitToType,GetUp}. Same official FbxImportUI path, onto the existing skeleton only;
refuses if the skeleton, bone identities or source clocks differ. Writes
private-audit/r9-seat-import.json. Does not touch config, contact or PC readiness.
"""
import hashlib, json
from pathlib import Path
import unreal as u

OWNER = ('/Game/Sub01Hands/AnatomicalCandidate/FBX_V_8027a9849bcf/'
         'Attempt_ee925b3f11c64fee8690b28bce56b66f/AnatomicalOwner.AnatomicalOwner')
SOURCE = Path('/workspace/sub01-home-private/device-motion-source-r2/r9-planted-seat-chain-r2/fbx-1792138465170389820')
DEST = '/Game/Sub01Hands/Seating'
ASSETS = {'StandToSit': 'SitDown', 'Sitting': 'Sitting', 'SitToType': 'SitToType', 'SitToStand': 'GetUp'}

root = Path(u.Paths.project_dir()).resolve()
batch = {row['role']: row for row in json.loads((SOURCE / 'batch.json').read_text())['clips']}
mesh = u.load_asset(OWNER)
if not isinstance(mesh, u.SkeletalMesh):
    raise RuntimeError('Active anatomical owner unavailable')
skeleton = mesh.get_editor_property('skeleton')
u.Sub01HomeHandsInstance.finish_pending_skin_compilation()
component = u.SkeletalMeshComponent(); component.set_skeletal_mesh_asset(mesh)
bones = lambda: [str(component.get_bone_name(i)) for i in range(component.get_num_bones())]
original = bones()
world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
u.SystemLibrary.execute_console_command(world, 'Interchange.FeatureFlags.Import.FBX 0')
for asset in ASSETS.values():
    # Older Seating clips are bound to the retired OriginalOwner skeleton; a
    # replace_existing reimport keeps that skeleton, so remove them in this copy.
    existing_path = DEST + '/SUB01_' + asset
    if u.EditorAssetLibrary.does_asset_exist(existing_path):
        existing = u.load_asset(existing_path)
        if existing.get_editor_property('skeleton').get_path_name() != skeleton.get_path_name():
            if not u.EditorAssetLibrary.delete_asset(existing_path):
                raise RuntimeError('Could not remove retired-skeleton clip ' + existing_path)
            u.log('SUB01_R9_SEAT_RETIRED_CLIP_REMOVED ' + existing_path)
rows = []
for role, asset in ASSETS.items():
    path = SOURCE / role / 'captured-animation-only.fbx'
    proof = json.loads((SOURCE / role / 'animation-conversion-proof.json').read_text())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != proof['fbx_sha256']:
        raise RuntimeError(role + ' FBX changed since its conversion proof')
    options = u.FbxImportUI()
    for key, value in (('automated_import_should_detect_type', False), ('import_as_skeletal', True),
                       ('import_mesh', False), ('import_animations', True), ('import_materials', False),
                       ('import_textures', False), ('mesh_type_to_import', u.FBXImportType.FBXIT_ANIMATION),
                       ('skeleton', skeleton)):
        options.set_editor_property(key, value)
    options.get_editor_property('anim_sequence_import_data').set_editor_property('use_default_sample_rate', True)
    task = u.AssetImportTask(); task.filename = str(path); task.destination_path = DEST
    task.destination_name = 'SUB01_' + asset; task.automated = True; task.replace_existing = True
    task.save = True; task.options = options
    u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    # imported_object_paths can be empty for legacy FBX animation imports; the saved asset is authoritative.
    clip = u.load_asset(DEST + '/SUB01_' + asset)
    clip_skeleton = clip.get_editor_property('skeleton') if isinstance(clip, u.AnimSequence) else None
    u.log('SUB01_R9_SEAT_IMPORTED %s class=%s skeleton=%s expected=%s paths=%s' % (role, type(clip).__name__,
          clip_skeleton.get_path_name() if clip_skeleton else None, skeleton.get_path_name(), list(task.imported_object_paths)))
    if clip_skeleton is None or clip_skeleton.get_path_name() != skeleton.get_path_name():
        raise RuntimeError(role + ' did not import onto the active owner skeleton')
    clips = [clip]
    if bones() != original:
        raise RuntimeError('Import changed the active owner bone identities')
    duration = clips[0].get_editor_property('sequence_length')
    if abs(duration - batch[role]['duration_seconds']) > 2 / 30:
        raise RuntimeError(role + ' duration differs from its source clock')
    rows.append({'role': role, 'asset': clips[0].get_path_name(), 'fbx_sha256': digest,
                 'duration_s': duration, 'source_duration_s': batch[role]['duration_seconds']})
u.EditorAssetLibrary.save_directory(DEST, only_if_is_dirty=False, recursive=True)
(root / 'private-audit').mkdir(exist_ok=True)
(root / 'private-audit/r9-seat-import.json').write_text(json.dumps(
    {'schema': 'sub01.r9-seat-import.v1', 'owner': OWNER, 'skeleton': skeleton.get_path_name(),
     'owner_bones_preserved': True, 'clips': rows, 'contact_verified': False, 'runtime_ready': False}, indent=2) + '\n')
u.log('SUB01_R9_SEAT_IMPORT_DONE ' + json.dumps([r['asset'] for r in rows]))
