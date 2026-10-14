import json
import os
from pathlib import Path

import pytest
from tools.unreal_editor_task_queue import EditorTaskQueue, POD, guard_valid


@pytest.fixture
def setup(tmp_path):
    private = tmp_path / 'private'
    private.mkdir(mode=0o700)
    guard = tmp_path / 'guard.json'
    guard.write_text(json.dumps(dict(pod=POD, deadline_epoch=200, total_cap=100,
                                   root_guard_pid=1, external_guard_pid=2,
                                   second_external_guard_pid=3, stop_guards_authenticated=True)))
    calls = []
    queue = EditorTaskQueue(private, guard, calls.append, lambda: 100)
    def request(revision=1, task='hide_generated', **extra):
        p = private / 'editor-task-request.json'
        p.write_text(json.dumps(dict(revision=revision, task=task, **extra)))
        p.chmod(0o600)
        return p
    return queue, calls, request, guard


def test_fixed_task_duplicate_and_monotonic_revision(setup):
    q, calls, request, _ = setup
    request(); q.poll(); q.poll()
    request(0); q.poll()
    request(2, 'real_lamps'); q.poll()
    assert calls == ['hide_generated', 'real_lamps']
    assert json.loads(q.result.read_text())['native_ready'] is False
    assert q.result.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('task,extra', [('os', {}), ('hide_generated', {'module': 'os'}), ('hide_generated', {'path': '/tmp/anything'})])
def test_no_arbitrary_modules_or_paths(setup, task, extra):
    q, calls, request, _ = setup
    request(task=task, **extra); q.poll()
    assert not calls


def test_error_receipt_and_new_revision_retry_preserve_editor(setup):
    q, calls, request, _ = setup
    def failing(task):
        calls.append(task)
        if len(calls) == 1: raise SystemExit('Importer refused')
    q.execute = failing
    request(); q.poll()
    assert json.loads(q.result.read_text())['error_type'] == 'SystemExit'
    assert not q.stopped
    q.poll(); assert len(calls) == 1
    request(2); q.poll()
    assert json.loads(q.result.read_text())['ok'] is True


def test_expiry_unregister_signal_no_task_or_save(setup):
    q, calls, request, guard = setup
    request(); q.clock = lambda: 200
    q.poll()
    assert q.stopped and not calls and not q.result.exists()
    assert not guard_valid(guard, 200)


@pytest.mark.parametrize('mode', [0o644, 0o666])
def test_unsafe_request_permissions_refused(setup, mode):
    q, calls, request, _ = setup
    request().chmod(mode); q.poll()
    assert not calls


def test_symlink_request_refused(setup, tmp_path):
    q, calls, request, _ = setup
    p = request(); target = tmp_path / 'other.json'; p.rename(target); p.symlink_to(target)
    q.poll(); assert not calls


def test_private_directory_permissions_required(setup):
    q, _, _, _ = setup
    q.private.chmod(0o755)
    with pytest.raises(PermissionError): EditorTaskQueue(q.private, q.guard)


@pytest.mark.parametrize('field,value', [('pod', 'brain'), ('total_cap', 101), ('stop_guards_authenticated', False), ('root_guard_pid', 0), ('external_guard_pid', True)])
def test_guard_identity_and_authenticated_budget_required(setup, field, value):
    q, calls, request, guard = setup
    doc=json.loads(guard.read_text()); doc[field]=value; guard.write_text(json.dumps(doc))
    request(); q.poll()
    assert q.stopped and not calls


def test_receipt_survives_queue_reload_without_reexecuting(setup):
    q, calls, request, _ = setup
    request(); q.poll()
    replacement=EditorTaskQueue(q.private, q.guard, calls.append, lambda:100)
    replacement.poll(); assert len(calls)==1


def test_slate_poll_is_bounded_and_unregisters_at_expiry(setup, monkeypatch):
    import sys
    from types import SimpleNamespace
    import tools.unreal_editor_task_queue as module
    q, calls, request, _ = setup
    request()
    callbacks=[]; removed=[]
    fake=SimpleNamespace(register_slate_post_tick_callback=lambda cb: callbacks.append(cb) or 17,
                         unregister_slate_post_tick_callback=removed.append)
    monkeypatch.setitem(sys.modules, 'unreal', fake)
    monkeypatch.setattr(module, 'EditorTaskQueue', lambda:q)
    now=[1.0]; monkeypatch.setattr(module.time, 'monotonic', lambda:now[0])
    actual, handle=module.install()
    callbacks[0](.01); assert calls == ['hide_generated']
    request(2); now[0]=1.1; callbacks[0](.01); assert len(calls)==1
    q.clock=lambda:200; now[0]=1.3; callbacks[0](.01)
    assert actual is q and handle==17 and removed == [17] and len(calls)==1
