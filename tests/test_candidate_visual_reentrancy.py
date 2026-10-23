"""Unreal screenshot loading can pump Slate before its native call returns."""
import importlib,sys,types
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))

def test_screenshot_loading_cannot_advance_camera_reentrantly(monkeypatch,tmp_path):
 module=importlib.import_module('unreal_candidate_visual_review');monkeypatch.setattr(module,'_handle',None)
 (tmp_path/'Content/Sub01Home').mkdir(parents=True);(tmp_path/'Content/Sub01Home/ActualHome.umap').write_bytes(b'actual saved candidate map')
 guard=types.SimpleNamespace(active_candidate_guard=lambda _:True,CANDIDATE=tmp_path,SCOPE=tmp_path/'scope.json',trusted_json=lambda _:{'nullrhi':False,'game_pid':159171,'game_start_ticks':976840968})
 monkeypatch.setitem(sys.modules,'private_home_candidate_scope',guard)
 real_path=Path
 monkeypatch.setattr(module,'Path',lambda p:types.SimpleNamespace(read_bytes=lambda:b'UnrealEditor\0-vulkan\0')if str(p)=='/proc/self/cmdline'else real_path(p))
 clock=[0.];monkeypatch.setattr(module.time,'monotonic',lambda:clock[0]);monkeypatch.setattr(module,'complete',lambda *args:False)
 callbacks={};captures=[];cameras=[]
 def capture(*args,**kwargs):
  captures.append((args,kwargs));clock[0]+=10
  # Exactly the synchronous reentry observed in the actual engine.
  if len(captures)==1:callbacks['tick'](0.)
  return object()
 u=types.SimpleNamespace(Paths=types.SimpleNamespace(project_dir=lambda:str(tmp_path)),UnrealEditorSubsystem=object(),get_editor_subsystem=lambda _:types.SimpleNamespace(get_editor_world=lambda:types.SimpleNamespace(get_path_name=lambda:'/Game/Sub01Home/ActualHome.ActualHome')),EditorLevelLibrary=types.SimpleNamespace(set_level_viewport_camera_info=lambda *v:cameras.append(v),editor_set_game_view=lambda _:None),Vector=lambda *v:v,Rotator=lambda **v:v,AutomationLibrary=types.SimpleNamespace(take_high_res_screenshot=capture),register_slate_post_tick_callback=lambda f:callbacks.setdefault('tick',f),unregister_slate_post_tick_callback=lambda _:None)
 monkeypatch.setitem(sys.modules,'unreal',u)
 result=module.run();assert result['review_started'];clock[0]=100;callbacks['tick'](0.)
 assert len(captures)==1 and len(cameras)==1
 # An incomplete file must also prevent advancing on the next ordinary tick.
 clock[0]+=10;callbacks['tick'](0.)
 assert len(captures)==1 and len(cameras)==1
