import json
import os
import pytest
from tools.pixel_streaming.native_live_viewer import authorized_viewer_window, AUTHORIZED_POD, PRIVATE_VIEWER_ORIGIN


@pytest.fixture
def window(tmp_path):
    path=tmp_path/'runtime-window.json'
    doc=dict(pod=AUTHORIZED_POD, deadline_epoch=200, total_cap=100,
             root_guard_pid=143, external_guard_pid=97214, second_external_guard_pid=97215,
             stop_guards_authenticated=True)
    path.write_text(json.dumps(doc)); path.chmod(0o644)
    return path,doc


def test_exact_migrated_private_target_and_bounded_window(window):
    path,_=window
    assert PRIVATE_VIEWER_ORIGIN=='https://kjsxms1gk4rmv6-8888.proxy.runpod.net'
    assert authorized_viewer_window(200,path,100,os.geteuid())
    assert not authorized_viewer_window(201,path,100,os.geteuid())
    assert not authorized_viewer_window(200,path,200,os.geteuid())


@pytest.mark.parametrize('key,value', [('pod','5ldnm4vax9kelh'),('pod','brain'),
    ('total_cap',101),('stop_guards_authenticated',False),('second_external_guard_pid',0)])
def test_previous_pod_and_unverified_window_refused(window,key,value):
    path,doc=window;doc[key]=value;path.write_text(json.dumps(doc))
    assert not authorized_viewer_window(200,path,100,os.geteuid())


@pytest.mark.parametrize('bad',['file_write','parent_write','owner','symlink'])
def test_actual_guard_file_trust_required(window,bad):
    path,_=window;uid=os.geteuid()
    if bad=='file_write':path.chmod(0o666)
    elif bad=='parent_write':path.parent.chmod(0o777)
    elif bad=='owner':uid+=1
    else:
        source=path.with_name('real.json');path.rename(source);path.symlink_to(source)
    assert not authorized_viewer_window(200,path,100,uid)


def test_only_exact_recovered_game_executable_is_eligible():
    from tools.pixel_streaming.native_live_viewer import authorized_native_args, AUTHORIZED_NATIVE_EXECUTABLE
    assert authorized_native_args([AUTHORIZED_NATIVE_EXECUTABLE,b'-game'])
    assert not authorized_native_args([AUTHORIZED_NATIVE_EXECUTABLE])  # Editor/PIE is not accepted game capture.
    assert not authorized_native_args([b'/workspace/sub01-unreal/UE/Engine/Binaries/Linux/UnrealEditor-Cmd',b'-game'])
    assert not authorized_native_args([AUTHORIZED_NATIVE_EXECUTABLE+b'-other',b'-game'])
    assert not authorized_native_args([])
