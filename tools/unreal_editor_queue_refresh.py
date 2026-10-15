"""Refresh the sole authenticated private queue without another Slate callback."""
import gc
import importlib
import sys


def refresh():
    module = sys.modules.get('unreal_editor_task_queue')
    if module is None or not module.guard_valid():
        return False
    matches = [obj for obj in gc.get_objects()
               if type(obj) is module.EditorTaskQueue and not obj.stopped
               and obj.private == module.PRIVATE and obj.guard == module.GUARD]
    if len(matches) != 1:
        raise RuntimeError('Exactly one authenticated private Editor queue required for refresh')
    queue = matches[0]
    if queue.execute is not module.dispatch:
        raise RuntimeError('Private queue has an unrecognized dispatcher')
    module.owned(queue.private, directory=True)
    old_pod, old_class, before = module.POD, type(queue), dict(queue.__dict__)
    refreshed = importlib.reload(module)
    if refreshed.POD != old_pod or not refreshed.guard_valid():
        raise RuntimeError('Authenticated private queue identity changed during refresh')
    # Keep the very same object captured by the existing Slate callback, with
    # every revision, pending receipt and throttle unchanged. No install() call.
    try:
        queue.__class__ = refreshed.EditorTaskQueue
        queue.execute = refreshed.dispatch
        if {k: v for k, v in queue.__dict__.items() if k != 'execute'} != {
                k: v for k, v in before.items() if k != 'execute'}:
            raise RuntimeError('Private queue state changed during refresh')
    except Exception:
        queue.__class__ = old_class
        queue.__dict__.clear()
        queue.__dict__.update(before)
        raise
    return True
