"""Keep one verified private Editor alive for reviewed filesystem queue tasks."""
import json
import os
import sys
import time
from pathlib import Path

import unreal

# Actual UE5.8 EditorPythonScriptingLibrary.h declares ScriptName="EditorPythonScripting".
# EditorPythonExecuter closes ExecutePythonScript sessions unless this API is set.
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
assert unreal.EditorPythonScripting.get_keep_python_script_alive()
unreal.log('SUB01_ACTUAL_PYTHON_KEEPALIVE_TRUE')
sys.path.insert(0, '/home/unreal/runtime-tools')
sys.path.insert(1, '/workspace/sub01-home-private/tools')
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
assert world and world.get_path_name().startswith('/Game/Sub01Home/ActualHome.'), 'ActualHome not loaded'
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
missing = []
for actor in actors:
    for component in actor.get_components_by_class(unreal.StaticMeshComponent):
        if not component.get_editor_property('static_mesh'):
            missing.append(component.get_path_name())
import unreal_editor_task_queue
_sub01_persistent_queue, _sub01_persistent_handle = unreal_editor_task_queue.install()
if missing:
    unreal.log_warning('SUB01_EDITOR_MISSING_MESHES ' + str(missing[:20]))
if hasattr(unreal.EditorLevelLibrary, 'editor_set_game_view'):
    unreal.EditorLevelLibrary.editor_set_game_view(True)
unreal.EditorLevelLibrary.set_level_viewport_camera_info(
    unreal.Vector(200, 310, 165), unreal.Rotator(-5, -90, 0))
Path('/home/unreal/.sub01-private/persistent-editor-ready.json').write_text(json.dumps({
    'editor_pid': os.getpid(), 'project_path': unreal.Paths.project_dir(),
    'engine_path': unreal.Paths.engine_dir(), 'world': world.get_path_name(),
    'actor_count': len(actors), 'missing_mesh_components': missing,
    'queue_installed': True, 'python_keepalive_verified': True,
    'native_game_accepted': False, 'ready_epoch': time.time()}))
unreal.log('SUB01_PERSISTENT_EDITOR_READY ' + str(len(actors)))
