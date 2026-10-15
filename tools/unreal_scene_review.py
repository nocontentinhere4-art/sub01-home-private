"""Fixed real Editor viewpoints; no scene edits, arbitrary paths or gameplay claims."""
import json
import os
import time
from pathlib import Path

VIEWS = {
    'living': ((200, 310, 165), (-5, -90, 0)),
    'desk': ((200, -195, 165), (-18, -90, 0)),
    'kitchen': ((-125, -190, 165), (-8, -134, 0)),
    'stairs': ((140, -120, 165), (18, -169, 0)),
    # Actual tile top305.25cm; source-bounded eye west of shower partition.
    'bathroom': ((-230, 120, 465), (-43.5, 121.2, 0)),
}


def run(view, u=None):
    if view not in VIEWS:
        raise ValueError('Fixed private scene viewpoint required')
    if u is None:
        import unreal as u
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if not world or world.get_path_name().split('.', 1)[0] != '/Game/Sub01Home/ActualHome':
        raise RuntimeError('Actual loaded private Editor home required')
    capture = getattr(u.AutomationLibrary, 'take_high_res_screenshot', None)
    if capture is None:
        raise RuntimeError('Actual Editor viewport screenshot API unavailable')
    output = Path(u.Paths.project_dir())/'evidence/scene-review'
    output.mkdir(parents=True, exist_ok=True)
    stamp = time.time_ns()
    path = output/(view+'-'+str(stamp)+'.png')
    position, angles = VIEWS[view]
    u.EditorLevelLibrary.set_level_viewport_camera_info(
        u.Vector(*position), u.Rotator(pitch=angles[0], yaw=angles[1], roll=angles[2]))
    if hasattr(u.EditorLevelLibrary, 'editor_set_game_view'):
        u.EditorLevelLibrary.editor_set_game_view(True)
    task = capture(1280, 720, str(path), delay=2.0)
    if task is None:
        raise RuntimeError('Editor did not return an actual screenshot task')
    receipt = {'schema': 'sub01.private-editor-scene-review.v1', 'view': view,
               'editor_pid': os.getpid(), 'requested_epoch': time.time(),
               'world': world.get_path_name(), 'position_ue_cm': list(position),
               'rotation_pitch_yaw_roll_deg': list(angles), 'image': str(path),
               'viewport_fov_verified': False, 'capture_requested': True,
               'image_written_verified': False, 'native_game_accepted': False,
               'native_visual_verified': False}
    (output/(view+'-'+str(stamp)+'.request.json')).write_text(json.dumps(receipt, indent=2)+'\n')
    return receipt
