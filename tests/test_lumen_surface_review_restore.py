import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest


def load():
    spec=importlib.util.spec_from_file_location('surface_review_under_test',Path(__file__).parents[1]/'tools/unreal_lumen_surface_review.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


@pytest.mark.parametrize('fail_diagnostic',[False,True])
def test_async_capture_restores_exact_prior_after_png_or_error(tmp_path,monkeypatch,fail_diagnostic):
    m=load();(tmp_path/'evidence/scene-review').mkdir(parents=True)
    real_path=Path
    monkeypatch.setattr(m,'Path',lambda p:tmp_path if str(p)=='/workspace/sub01-private-recovered-project/Sub01HomeLab'else real_path(p))
    state={'value':8,'callback':None,'unregistered':False,'captures':[]}
    def execute(world,command):state['value']=int(command.rsplit(' ',1)[1])
    def capture(w,h,path,delay):
        state['captures'].append((state['value'],path))
        if state['value']==5 and fail_diagnostic:raise RuntimeError('actual screenshot error')
        f=real_path(path);f.write_bytes(b'\x89PNG\r\n\x1a\n'+b'x'*101+b'\0\0\0\0IEND\xaeB`\x82')
        import os,time
        os.utime(f,(time.time()+1,time.time()+1));return object()
    def register(callback):state['callback']=callback;return 77
    u=SimpleNamespace(Paths=SimpleNamespace(project_dir=lambda:str(tmp_path)),
       UnrealEditorSubsystem=object,get_editor_subsystem=lambda c:SimpleNamespace(get_editor_world=lambda:SimpleNamespace(get_path_name=lambda:'/Game/Sub01Home/ActualHome.ActualHome')),
       SystemLibrary=SimpleNamespace(get_console_variable_int_value=lambda n:state['value'],execute_console_command=execute),
       AutomationLibrary=SimpleNamespace(take_high_res_screenshot=capture),
       EditorLevelLibrary=SimpleNamespace(set_level_viewport_camera_info=lambda *a:None,editor_set_game_view=lambda v:None),
       Vector=lambda *a:a,Rotator=lambda **a:a,register_slate_post_tick_callback=register,
       unregister_slate_post_tick_callback=lambda h:state.update(unregistered=True))
    monkeypatch.setitem(sys.modules,'unreal',u);monkeypatch.setitem(sys.modules,'unreal_editor_task_queue',SimpleNamespace(guard_valid=lambda:True))
    result=m.run();assert state['value']==8 and not state['unregistered']
    for _ in range(3):
        if state['unregistered']:break
        state['callback'](.1)
    import json
    receipt=json.loads(real_path(result['receipt']).read_text())
    assert state['value']==8 and state['unregistered'] and receipt['restored_prior_verified']
    assert receipt['phase']==('failed'if fail_diagnostic else'complete')
    if not fail_diagnostic:assert [v for v,p in state['captures']]==[8,5,8]
