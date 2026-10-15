"""An existing callback keeps its queue, revisions and pending receipt on reload."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from tools import unreal_editor_queue_refresh as R


def fixture():
    class OldQueue:
        pass
    class NewQueue:
        pass
    old_dispatch, new_dispatch = lambda task: None, lambda task: task
    old = SimpleNamespace(EditorTaskQueue=OldQueue, PRIVATE=Path('/private'),
                          GUARD=Path('/guard'), POD='same-authorized-pod',
                          dispatch=old_dispatch, guard_valid=lambda: True,
                          owned=lambda path, directory: None)
    new = SimpleNamespace(EditorTaskQueue=NewQueue, POD=old.POD,
                          dispatch=new_dispatch, guard_valid=lambda: True)
    q = OldQueue()
    q.private, q.guard, q.stopped = old.PRIVATE, old.GUARD, False
    q.execute, q.last_revision = old_dispatch, 7
    q.pending_result, q.receipt_error_type = {'revision': 7}, 'OSError'
    return old, new, q


def test_refresh_preserves_same_callback_object_and_pending_state():
    old, new, q = fixture()
    pending = q.pending_result
    captured_by_callback = lambda: q
    with patch.dict(R.sys.modules, {'unreal_editor_task_queue': old}), \
            patch.object(R.gc, 'get_objects', return_value=[q]), \
            patch.object(R.importlib, 'reload', return_value=new) as reload:
        assert R.refresh() is True
    assert captured_by_callback() is q and type(q) is new.EditorTaskQueue
    assert q.execute is new.dispatch and q.last_revision == 7
    assert q.pending_result is pending and q.receipt_error_type == 'OSError'
    reload.assert_called_once_with(old)


def test_duplicate_queue_refused_before_reload():
    old, new, q = fixture()
    duplicate = type(q)()
    duplicate.__dict__.update(q.__dict__)
    with patch.dict(R.sys.modules, {'unreal_editor_task_queue': old}), \
            patch.object(R.gc, 'get_objects', return_value=[q, duplicate]), \
            patch.object(R.importlib, 'reload', return_value=new) as reload:
        with pytest.raises(RuntimeError, match='Exactly one'):
            R.refresh()
        reload.assert_not_called()


def test_expired_or_missing_guard_never_searches_or_reloads():
    old, _, _ = fixture()
    old.guard_valid = lambda: False
    with patch.dict(R.sys.modules, {'unreal_editor_task_queue': old}), \
            patch.object(R.gc, 'get_objects') as objects:
        assert R.refresh() is False
        objects.assert_not_called()
