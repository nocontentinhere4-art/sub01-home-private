"""Fixed private scene tasks on the existing Editor's Slate thread; no network API."""
import importlib
import json
import os
import stat
import time
from pathlib import Path

POD = 'dgtgepkz7h1zy5'  # Verified continuous RTX4090 target; never read from requests.
PRIVATE = Path('/home/unreal/.sub01-private')
GUARD = Path('/run/sub01-home-private/runtime-window.json')
TASKS = {
    'hide_generated': 'unreal_hide_rejected_generated_decor',
    'structural_lamp_union': 'unreal_import_structural_lamp_union',
    'real_lamps': 'unreal_import_real_lamps',
    'complete_books': 'unreal_import_real_shelf_books',
    'desk_preflight': 'unreal_real_desk_import_preflight',
    'real_office': 'unreal_import_real_office_bundle',
    'gaming_grip': 'unreal_import_gaming_grip',
    'real_kitchen': 'unreal_import_real_kitchen',
    'monitor_support': 'unreal_monitor_support_fix',
    'review_living': 'unreal_scene_review',
    'review_desk': 'unreal_scene_review',
    'review_kitchen': 'unreal_scene_review',
    'review_stairs': 'unreal_scene_review',
    'hands_inventory': 'unreal_hands_inventory',
    'walk_pose_audit': 'unreal_walk_pose_audit',
    'refresh_queue': 'unreal_editor_queue_refresh',
    'kitchen_partial_inventory': 'unreal_kitchen_partial_inventory',
    'private_crash_policy': 'unreal_private_crash_policy',
    'plant_clone_audit': 'unreal_loaded_plant_clone_audit',
    'book_clone_audit': 'unreal_loaded_book16_clone_audit',
    'recover_saved_home': 'unreal_recover_saved_home',
    'collision_state_audit': 'unreal_book_collision_audit',
    'collision_restore_proof': 'unreal_book_collision_restore_proof',
    'scene_visual_inventory': 'unreal_home_visual_inventory',
    'finish_editor_handoff': 'unreal_finish_editor_handoff',
    'nanite_materials': 'unreal_fix_private_nanite_materials',
    'nanite_materials_preflight': 'unreal_fix_private_nanite_materials',
    'phone_grip': 'unreal_import_phone_grip',
    'frame_backings': 'unreal_remove_frame_backings',
    'real_wc': 'unreal_import_real_wc',
    'architecture_lumen_audit': 'unreal_architecture_lumen_audit',
}
# Reviewed source export path must be frozen by the owner before this task is enabled.
DESK_EXPORT = None
OFFICE_EXPORT = Path('/workspace/sub01-home-private/out/real-office-bundle')
KITCHEN_EXPORT = Path('/workspace/sub01-private-kitchen-3eb5419-20261015/proof-output-r2/uid1001')


def owned(path, directory=False):
    meta = path.lstat()
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(meta.st_mode) or meta.st_uid != os.geteuid() or stat.S_IMODE(meta.st_mode) != (0o700 if directory else 0o600):
        raise PermissionError('Private queue ownership or mode differs')
    if not directory and meta.st_nlink != 1:
        raise PermissionError('Private queue file has multiple links')
    return meta


def read_owned(path):
    owned(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        meta = os.fstat(fd)
        if meta.st_uid != os.geteuid() or stat.S_IMODE(meta.st_mode) != 0o600 or not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1:
            raise PermissionError('Private queue file changed')
        data = os.read(fd, 4097)
        if len(data) > 4096:
            raise ValueError('Private request is too large')
        return json.loads(data)
    finally:
        os.close(fd)


def guard_valid(path=GUARD, now=None, trusted_uid=0):
    try:
        parent = path.parent.lstat()
        if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != trusted_uid or parent.st_mode & 0o022:
            return False
        if not stat.S_ISREG(path.lstat().st_mode):
            return False
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            meta = os.fstat(fd)
            if not stat.S_ISREG(meta.st_mode) or meta.st_uid != trusted_uid or meta.st_mode & 0o022 or meta.st_nlink != 1:
                return False
            raw = os.read(fd, 4097).decode('utf-8')
        finally:
            os.close(fd)
        if len(raw) > 4096:
            return False
        g = json.loads(raw)
        if not isinstance(g, dict):
            return False
        current = time.time() if now is None else now
        return (g.get('pod') == POD and type(g.get('total_cap')) in (int, float)
                and 0 < g['total_cap'] <= 100
                and type(g.get('deadline_epoch')) is int and current < g['deadline_epoch']
                and g.get('stop_guards_authenticated') is True
                and all(type(g.get(k)) is int and g[k] > 0 for k in ('root_guard_pid', 'external_guard_pid'))
                and ('second_external_guard_pid' not in g or
                     (type(g['second_external_guard_pid']) is int and g['second_external_guard_pid'] > 0)))
    except (OSError, ValueError, TypeError):
        return False


def dispatch(task):
    if task == 'real_office':
        # Fixed reviewed dependencies allow corrected contact/import code to be
        # retried in the same Editor. Requests cannot supply modules or paths.
        for name in ('real_linea_edge_clamp', 'prepare_real_linea140_placement',
                     'prepare_real_office_bundle', 'unreal_import_real_linea140'):
            importlib.reload(importlib.import_module(name))
    module = importlib.reload(importlib.import_module(TASKS[task]))
    if task == 'scene_visual_inventory':
        return module.run(Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/private-audit/current-editor-visual-inventory.json'))
    if task == 'nanite_materials':
        return module.run(dry_run=False)
    if task == 'real_wc':
        # The importer owns its frozen, proved source path and preserves shared
        # vanity/balcony geometry. Queue requests cannot override that packet.
        return module.run(dry_run=False)
    if task == 'nanite_materials_preflight':
        report = module.run(dry_run=True)
        audit = Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/private-audit/nanite-material-preflight.json')
        audit.parent.mkdir(exist_ok=True)
        audit.write_text(json.dumps(report, indent=2)+'\n')
        return report
    if task == 'refresh_queue':
        return {'refreshed_existing_queue': module.refresh(), 'native_game_accepted': False}
    if task in ('review_living', 'review_desk', 'review_kitchen', 'review_stairs'):
        return module.run(task.removeprefix('review_'))
    if task == 'monitor_support':
        return module.run(OFFICE_EXPORT, dry_run=False)
    if task == 'real_kitchen':
        return module.run(KITCHEN_EXPORT, dry_run=False)
    if task == 'gaming_grip':
        # Import verified source on the existing skeleton; this does not bind gameplay.
        return module.main(importlib.import_module('unreal'))
    if task == 'real_office':
        return module.run(OFFICE_EXPORT, dry_run=False)
    if task == 'real_lamps':
        return module.run(Path('/workspace/sub01-home-private/out/real-lamps'))
    if task == 'complete_books':
        return module.run(['--root', '/workspace/sub01-home-private/out/real-books-complete', '--excision-applied', '--keep-loaded-level'])
    if task == 'desk_preflight':
        if DESK_EXPORT is None:
            raise RuntimeError('Desk export constant not reviewed; read-only task unavailable')
        return module.audit(DESK_EXPORT)
    return module.run()


class EditorTaskQueue:
    def __init__(self, private=PRIVATE, guard=GUARD, execute=dispatch, clock=time.time, guard_uid=0):
        self.private, self.guard, self.execute, self.clock = Path(private), Path(guard), execute, clock
        owned(self.private, directory=True)
        self.request = self.private / 'editor-task-request.json'
        self.result = self.private / 'editor-task-result.json'
        self.guard_uid = guard_uid
        self.pending_result = None
        self.receipt_error_type = None
        self.last_revision = 0
        self.stopped = False
        if self.result.exists():
            previous = read_owned(self.result)
            revision = previous.get('revision')
            if type(revision) is not int or revision < 1:
                raise ValueError('Previous task receipt revision differs')
            self.last_revision = revision

    def write_result(self, receipt):
        owned(self.private, directory=True)
        temporary = self.private / ('.editor-task-result-' + str(os.getpid()))
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(receipt, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.result)
        finally:
            temporary.unlink(missing_ok=True)

    def poll(self):
        if self.stopped:
            return
        if not guard_valid(self.guard, self.clock(), self.guard_uid):
            self.stopped = True
            return
        if self.pending_result is not None:
            try:
                self.write_result(self.pending_result)
                self.pending_result = None
                self.receipt_error_type = None
            except OSError as error:
                self.receipt_error_type = type(error).__name__
                return
        try:
            owned(self.private, directory=True)
            request = read_owned(self.request)
        except FileNotFoundError:
            return
        except (OSError, ValueError, TypeError):
            return  # Untrusted requests are never executed or reflected into a receipt.
        if not isinstance(request, dict) or set(request) != {'revision', 'task'}:
            return
        revision, task = request['revision'], request['task']
        if type(revision) is not int or not self.last_revision < revision <= 2**53 - 1:
            return
        if type(task) is not str or task not in TASKS:
            return
        if not guard_valid(self.guard, self.clock(), self.guard_uid):
            self.stopped = True
            return
        self.last_revision = revision  # Failed tasks require a NEW explicit revision.
        receipt = {'revision': revision, 'task': task, 'ok': False,
                   'native_ready': False, 'finished_epoch': None}
        try:
            self.execute(task)
            receipt['ok'] = True
        except BaseException as error:
            # Includes importer SystemExit, so a task refusal cannot quit the Editor.
            receipt['error_type'] = type(error).__name__
            receipt['error'] = str(error)[:500]
        receipt['finished_epoch'] = self.clock()
        try:
            self.write_result(receipt)
        except OSError as error:
            self.pending_result = receipt
            self.receipt_error_type = type(error).__name__


def install():
    """Owner invokes once after Editor ready; all mutations run on Slate's thread."""
    import unreal
    queue = EditorTaskQueue()
    handle = None
    last_poll = 0.0

    def tick(delta):
        nonlocal last_poll
        now = time.monotonic()
        if now - last_poll < .25:
            return
        last_poll = now
        queue.poll()
        if queue.stopped:
            unreal.unregister_slate_post_tick_callback(handle)

    handle = unreal.register_slate_post_tick_callback(tick)
    return queue, handle
