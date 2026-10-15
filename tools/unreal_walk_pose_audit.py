"""Read every imported Walk/Idle key before considering regular posture binding."""
import json
import math
import os
import time
from pathlib import Path


def run(u=None):
    if u is None:
        import unreal as u
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if not world or world.get_path_name().split('.', 1)[0] != '/Game/Sub01Home/ActualHome':
        raise RuntimeError('Actual private Editor world required')
    mesh = u.load_asset('/Game/Sub01Hands/FBX/SUB01_OriginalOwner')
    if not isinstance(mesh, u.SkeletalMesh):
        raise RuntimeError('Actual imported owner missing')
    component = u.SkeletalMeshComponent()
    component.set_skeletal_mesh_asset(mesh)
    names = [component.get_bone_name(i) for i in range(component.get_num_bones())]
    parents = {str(n): str(component.get_parent_bone(n)) for n in names}
    structural = [str(n) for n in names if parents[str(n)] not in parents]
    if len(structural) != 1:
        raise RuntimeError('One actual structural root required')
    tracked = structural + [str(n) for n in names if str(n).endswith(('Hips', 'Head', 'LeftHand', 'RightHand', 'LeftFoot', 'RightFoot', 'LeftToeBase', 'RightToeBase'))]
    results = []
    for role, path in (('Walk', '/Game/Sub01Hands/FBX/SUB01_Walk'),
                       ('Idle', '/Game/Sub01Hands/Life/SUB01_Idle')):
        clip = u.load_asset(path)
        if not isinstance(clip, u.AnimSequence) or clip.get_editor_property('skeleton') != mesh.get_editor_property('skeleton'):
            raise RuntimeError('Actual same-skeleton '+role+' required')
        duration = float(clip.get_editor_property('sequence_length'))
        count = int(round(duration*30))+1
        rows = []
        for frame in range(count):
            t = duration*frame/(count-1)
            values = u.AnimationLibrary.get_bone_poses_for_time(clip, names, t, False, mesh)
            if len(values) != len(names):
                raise RuntimeError('Incomplete actual bone pose')
            local, resolved = dict(zip(map(str, names), values)), {}
            def pose(name):
                if name not in resolved:
                    parent = parents[name]
                    resolved[name] = u.MathLibrary.compose_transforms(local[name], pose(parent)) if parent in local else local[name]
                return resolved[name]
            positions = {}
            for name in tracked:
                p = pose(name).translation
                point = [float(p.x), float(p.y), float(p.z)]
                if not all(map(math.isfinite, point)):
                    raise RuntimeError('Nonfinite actual pose')
                positions[name] = point
            forward = {}
            for side in ('Left', 'Right'):
                foot = next((n for n in tracked if n.endswith(side+'Foot')), None)
                toe = next((n for n in tracked if n.endswith(side+'ToeBase')), None)
                if foot and toe:
                    forward[side] = [positions[toe][k]-positions[foot][k] for k in range(3)]
            rows.append({'time_s': t, 'component_space_cm': positions,
                         'ankle_to_toe_vector_cm': forward})
        movement = {}
        for name in tracked:
            points = [r['component_space_cm'][name] for r in rows]
            movement[name] = {'first_to_last_cm': [points[-1][k]-points[0][k] for k in range(3)],
                              'range_cm': [max(p[k] for p in points)-min(p[k] for p in points) for k in range(3)]}
        results.append({'role': role, 'path': clip.get_path_name(), 'duration_s': duration,
                        'root_motion_enabled': bool(clip.get_editor_property('enable_root_motion')),
                        'sample_count': count, 'movement': movement, 'samples': rows})
    result = {'schema': 'sub01.native-walk-idle-pose-audit.v1', 'editor_pid': os.getpid(),
              'captured_epoch': time.time(), 'owner': mesh.get_path_name(),
              'structural_root': structural[0], 'clips': results,
              'postures_verified': False, 'native_game_accepted': False,
              'scope': 'Actual imported component-space poses only; no scene-floor, POV or gameplay acceptance.'}
    out = Path(u.Paths.project_dir())/'private-audit/native-walk-idle-pose-audit.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2)+'\n')
    return result
