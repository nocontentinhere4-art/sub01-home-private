"""Save the actual accepted home and close only its sole Editor for Game."""
import hashlib
import json
import os
import shutil
import time
from pathlib import Path

_handle = None


def run(u=None):
    global _handle
    if u is None:
        import unreal as u
    project = Path(u.Paths.project_dir()).resolve()
    if project != Path('/workspace/sub01-private-recovered-project/Sub01HomeLab'):
        raise RuntimeError('Exact recovered project required')
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    level = '/Game/Sub01Home/ActualHome'
    if not world or world.get_path_name().split('.', 1)[0] != level:
        raise RuntimeError('Actual saved home Editor required')
    if not callable(getattr(u.SystemLibrary, 'quit_editor', None)):
        raise RuntimeError('Actual graceful Editor quit API unavailable')
    office_root = Path('/workspace/sub01-home-private/out/real-office-bundle')
    office = json.loads((office_root / 'native-office-bundle.json').read_text())
    if office.get('schema') != 'sub01.real-office-native-import.v1' or not office.get('native_protected_original_fingerprints_verified'):
        raise RuntimeError('Accepted real office receipt required')
    kitchen = json.loads(Path('/workspace/sub01-private-kitchen-3eb5419-20261015/proof-output-r2/uid1001/native-kitchen-import.json').read_text())
    if kitchen.get('schema') != 'sub01.real-kitchen-native-import.v1':
        raise RuntimeError('Accepted real kitchen receipt required')
    map_path = project / 'Content/Sub01Home/ActualHome.umap'
    audit = project / 'private-audit'
    audit.mkdir(exist_ok=True)
    stamp = time.time_ns()
    backup = audit / f'pre-game-handoff-{stamp}.umap'
    shutil.copy2(map_path, backup)
    if not u.EditorLoadingAndSavingUtils.save_map(world, level):
        raise RuntimeError('Actual map save refused; keep Editor warm')
    receipt = {'schema': 'sub01.saved-editor-game-handoff.v1', 'editor_pid': os.getpid(),
               'saved_epoch': time.time(), 'map': str(map_path),
               'map_sha256': hashlib.sha256(map_path.read_bytes()).hexdigest(),
               'backup': str(backup), 'native_game_accepted': False,
               'gpu_display_devices_remain_running': True}
    (audit / 'saved-editor-game-handoff.json').write_text(json.dumps(receipt, indent=2) + '\n')
    ready_at = time.monotonic() + 2

    def finish(_delta):
        global _handle
        if time.monotonic() < ready_at:
            return
        u.unregister_slate_post_tick_callback(_handle)
        _handle = None
        u.SystemLibrary.quit_editor()

    _handle = u.register_slate_post_tick_callback(finish)
    return receipt
