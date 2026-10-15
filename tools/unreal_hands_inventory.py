"""Read actual native skin/clip/config state; never bind or approve a posture."""
import hashlib
import json
import os
import time
from pathlib import Path


def run(u=None):
    if u is None:
        import unreal as u
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if not world or world.get_path_name().split('.', 1)[0] != '/Game/Sub01Home/ActualHome':
        raise RuntimeError('Loaded actual private Editor home required')
    root = Path(u.Paths.project_dir())
    result = {'schema': 'sub01.native-hands-inventory.v1', 'editor_pid': os.getpid(),
              'captured_epoch': time.time(), 'world': world.get_path_name(),
              'native_game_accepted': False, 'postures_verified': False}
    owner = u.load_asset('/Game/Sub01Hands/FBX/SUB01_OriginalOwner')
    if not isinstance(owner, u.SkeletalMesh):
        raise RuntimeError('Actual original owner SkeletalMesh missing')
    skeleton = owner.get_editor_property('skeleton')
    component = u.SkeletalMeshComponent()
    component.set_skeletal_mesh_asset(owner)
    bones = [str(component.get_bone_name(i)) for i in range(component.get_num_bones())]
    extent = owner.get_bounds().box_extent
    result['owner'] = {'mesh': owner.get_path_name(), 'skeleton': skeleton.get_path_name(),
                       'bounds_extent_cm': [extent.x, extent.y, extent.z],
                       'bone_count': len(bones), 'bone_names': bones,
                       'head_candidates': [n for n in bones if n.endswith('Head')]}
    clips = []
    for path in u.EditorAssetLibrary.list_assets('/Game/Sub01Hands', recursive=True, include_folder=False):
        if not any(name in path.rsplit('/', 1)[-1] for name in ('Walk', 'Idle')):
            continue
        asset = u.load_asset(path)
        if not isinstance(asset, u.AnimSequence):
            continue
        actual_skeleton = asset.get_editor_property('skeleton')
        clips.append({'path': asset.get_path_name(),
                      'duration_s': asset.get_editor_property('sequence_length'),
                      'skeleton': actual_skeleton.get_path_name() if actual_skeleton else None,
                      'same_owner_skeleton': actual_skeleton == skeleton})
    result['clips'] = clips
    default = u.get_default_object(u.Sub01HomeCharacter)
    effective = {}
    for name in ('hands_mesh_path', 'walk_clip_path', 'idle_clip_path', 'typing_clip_path',
                 'phone_clip_path', 'validated_hands_postures', 'hidden_head_bones',
                 'walk_mesh_offset', 'hands_mesh_rotation'):
        try:
            value = default.get_editor_property(name)
            effective[name] = list(map(str, value)) if name in ('validated_hands_postures', 'hidden_head_bones') else str(value)
        except Exception as error:
            effective[name] = {'unavailable': type(error).__name__}
    result['class_defaults'] = effective
    keys = ('HandsMeshPath', 'WalkClipPath', 'IdleClipPath', 'ValidatedHandsPostures', 'HiddenHeadBones', 'WalkMeshOffset', 'HandsMeshRotation')
    result['config'] = {}
    for relative in ('Config/DefaultGame.ini', 'Saved/Config/Linux/Game.ini', 'Saved/Config/LinuxEditor/Game.ini'):
        path = root/relative
        result['config'][relative] = [line for line in path.read_text().splitlines()
            if line.lstrip('+!-').split('=', 1)[0].strip() in keys] if path.is_file() else None
    result['existing_receipts'] = []
    for directory in (root, root/'private-audit'):
        for path in directory.glob('*.json'):
            if any(word in path.name.lower() for word in ('hands', 'walking', 'binding', 'skin', 'eye')):
                result['existing_receipts'].append({'path': str(path), 'bytes': path.stat().st_size,
                    'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    output = root/'private-audit/native-hands-inventory.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)+'\n')
    return result
