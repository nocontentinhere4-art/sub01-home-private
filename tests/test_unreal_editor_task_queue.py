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
    queue = EditorTaskQueue(private, guard, calls.append, lambda: 100, guard_uid=os.geteuid())
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
    assert not guard_valid(guard, 200, trusted_uid=os.geteuid())


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


@pytest.mark.parametrize('field,value', [('pod', 'brain'), ('pod', 'kjsxms1gk4rmv6'), ('total_cap', 101), ('stop_guards_authenticated', False), ('root_guard_pid', 0), ('external_guard_pid', True)])
def test_guard_identity_and_authenticated_budget_required(setup, field, value):
    q, calls, request, guard = setup
    doc=json.loads(guard.read_text()); doc[field]=value; guard.write_text(json.dumps(doc))
    request(); q.poll()
    assert q.stopped and not calls


def test_receipt_survives_queue_reload_without_reexecuting(setup):
    q, calls, request, _ = setup
    request(); q.poll()
    replacement=EditorTaskQueue(q.private, q.guard, calls.append, lambda:100, guard_uid=os.geteuid())
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


def test_complete_books_dispatch_uses_only_complete_packet(monkeypatch):
    import tools.unreal_editor_task_queue as module
    from types import SimpleNamespace
    called=[]; imports=[]
    fake=SimpleNamespace(run=lambda argv: called.append(argv))
    monkeypatch.setattr(module.importlib, 'import_module', lambda name: imports.append(name) or fake)
    monkeypatch.setattr(module.importlib, 'reload', lambda value:value)
    module.dispatch('complete_books')
    assert imports == ['unreal_import_real_shelf_books']
    assert called == [['--root', '/workspace/sub01-home-private/out/real-books-complete', '--excision-applied', '--keep-loaded-level']]
    assert '/workspace/sub01-home-private/out/real-books' not in called[0]


def test_office_dispatch_fixed_packet_and_reviewed_dependency_reload(monkeypatch):
    import tools.unreal_editor_task_queue as module
    from types import SimpleNamespace
    called=[]; imports=[]
    fake=SimpleNamespace(run=lambda root, **kwargs: called.append((str(root), kwargs)))
    monkeypatch.setattr(module.importlib, 'import_module', lambda name: imports.append(name) or fake)
    monkeypatch.setattr(module.importlib, 'reload', lambda value:value)
    module.dispatch('real_office')
    assert imports == ['real_linea_edge_clamp', 'prepare_real_linea140_placement',
                       'prepare_real_office_bundle', 'unreal_import_real_linea140',
                       'unreal_import_real_office_bundle']
    assert called == [('/workspace/sub01-home-private/out/real-office-bundle', {'dry_run':False})]


@pytest.mark.parametrize('change', ['file_write', 'parent_write', 'wrong_owner', 'symlink'])
def test_guard_filesystem_trust(setup, change, tmp_path):
    q, calls, request, guard=setup
    if change=='file_write':guard.chmod(0o666)
    elif change=='parent_write':guard.parent.chmod(0o777)
    elif change=='wrong_owner':q.guard_uid=os.geteuid()+1
    else:
        actual=tmp_path/'actual'; guard.rename(actual); guard.symlink_to(actual)
    request(); q.poll()
    assert q.stopped and not calls


def test_receipt_write_failure_retries_without_reexecuting_task(setup, monkeypatch):
    q, calls, request, _=setup
    original=q.write_result; attempts=[]
    def temporary_failure(receipt):
        attempts.append(receipt)
        if len(attempts)<3:raise PermissionError('Receipt unavailable')
        original(receipt)
    monkeypatch.setattr(q,'write_result',temporary_failure)
    request(); q.poll(); q.poll()
    assert calls==['hide_generated'] and q.pending_result is not None and not q.stopped
    q.poll()
    assert q.pending_result is None and q.receipt_error_type is None
    assert json.loads(q.result.read_text())['ok'] is True
    assert len(calls)==1


def test_grip_dispatch_uses_loaded_editor_and_no_request_supplied_path(monkeypatch):
    import tools.unreal_editor_task_queue as module
    from types import SimpleNamespace
    calls=[]; native=object()
    importer=SimpleNamespace(main=lambda editor:calls.append(editor))
    modules={'unreal_import_gaming_grip':importer,'unreal':native}
    monkeypatch.setattr(module.importlib,'import_module',modules.__getitem__)
    monkeypatch.setattr(module.importlib,'reload',lambda value:value)
    module.dispatch('gaming_grip')
    assert calls==[native]


def test_kitchen_dispatch_uses_frozen_proven_export_and_no_runtime_enable(monkeypatch):
    import tools.unreal_editor_task_queue as module
    from types import SimpleNamespace
    calls=[]
    importer=SimpleNamespace(run=lambda root,**kw:calls.append((str(root),kw)))
    monkeypatch.setattr(module.importlib,'import_module',lambda name:importer)
    monkeypatch.setattr(module.importlib,'reload',lambda value:value)
    module.dispatch('real_kitchen')
    assert calls==[('/workspace/sub01-private-kitchen-3eb5419-20261015/proof-output-r2/uid1001',{'dry_run':False})]


def test_bathroom_pendant_dispatch_uses_only_fixed_source(monkeypatch):
    import tools.unreal_editor_task_queue as module
    from types import SimpleNamespace
    calls=[]
    importer=SimpleNamespace(run=lambda source,**kw:calls.append((str(source),kw)))
    monkeypatch.setattr(module.importlib,'import_module',lambda name:importer)
    monkeypatch.setattr(module.importlib,'reload',lambda value:value)
    module.dispatch('real_bathroom_pendant')
    assert calls==[('/workspace/sub01-home-private/real-bathroom-pendant-source/split-v3/bathroom-pendant.glb',{'dry_run':False})]
