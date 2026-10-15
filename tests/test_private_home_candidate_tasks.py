import importlib.util,sys
from pathlib import Path
from types import SimpleNamespace
import pytest
ROOT=Path(__file__).parents[1];sys.path.insert(0,str(ROOT/'tools'))
spec=importlib.util.spec_from_file_location('candidate_tasks',ROOT/'tools/private_home_candidate_tasks.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def test_no_arbitrary_execution():
 with pytest.raises(RuntimeError):m.dispatch('os.system',{})
def test_probe_does_not_import_or_mutate(monkeypatch):
 monkeypatch.setattr(m.importlib,'import_module',lambda name:(_ for _ in ()).throw(AssertionError('must not import')))
 value={'native_read_only':True};assert m.dispatch('probe',value)is value
@pytest.mark.parametrize('task,dry',[('wall_console_preflight',True),('wall_console',False)])
def test_wall_scope_is_fixed_and_preflight_dry(monkeypatch,task,dry):
 seen=[];module=SimpleNamespace(run=lambda **kwargs:seen.append(kwargs)or{'saved':not kwargs['dry_run']})
 monkeypatch.setattr(m.importlib,'import_module',lambda name:module if name=='unreal_import_reference_wall_console'else None);monkeypatch.setattr(m.importlib,'reload',lambda mod:mod)
 m.dispatch(task,{});assert seen==[{'dry_run':dry}]
@pytest.mark.parametrize('task,dry',[('teal_bath_preflight',True),('teal_bath',False)])
def test_teal_uses_only_frozen_source_proof(monkeypatch,task,dry):
 seen=[];module=SimpleNamespace(run=lambda *a,**kw:seen.append((a,kw))or{})
 monkeypatch.setattr(m.importlib,'import_module',lambda name:module if name=='unreal_import_reference_teal_bathroom'else None);monkeypatch.setattr(m.importlib,'reload',lambda mod:mod)
 m.dispatch(task,{});assert seen==[((m.STYLE,m.PROOF),{'dry_run':dry})]

def test_interchange_slate_reentry_cannot_start_second_task(monkeypatch):
 calls=[]
 def work(seen,probe):
  calls.append('outer');m.poll(seen,probe);calls.append('finished')
 monkeypatch.setattr(m,'_poll_once',work);m._busy=False;m.poll(set(),{});assert calls==['outer','finished']and m._busy is False

def test_busy_latch_releases_after_exception(monkeypatch):
 monkeypatch.setattr(m,'_poll_once',lambda *_:(_ for _ in()).throw(RuntimeError('failed task')));m._busy=False
 with pytest.raises(RuntimeError):m.poll(set(),{})
 assert m._busy is False

def test_hot_reload_source_preserves_in_progress_latch():
 m._busy=True
 try:
  exec(compile((ROOT/'tools/private_home_candidate_tasks.py').read_text(),str(ROOT/'tools/private_home_candidate_tasks.py'),'exec'),m.__dict__)
  assert m._busy is True
 finally:m._busy=False

def test_pending_asset_task_waits_for_exact_capture_lease(monkeypatch,tmp_path):
 import os,json
 scope=tmp_path/'scope.json';requests=tmp_path/'candidate-requests';requests.mkdir();audit=tmp_path/'private-audit';audit.mkdir();request=requests/'020-photo_plants.json';request.touch()
 body={'schema':'sub01.private-next-home-task.v1','task':'photo_plants','candidate_editor_pid':os.getpid(),'world_mutations_authorized':True}
 monkeypatch.setattr(m,'SCOPE',scope);monkeypatch.setattr(m,'CANDIDATE',tmp_path);monkeypatch.setattr(m,'active_candidate_guard',lambda _:True);monkeypatch.setattr(m,'trusted_json',lambda p:{'allowed_tasks':['photo_plants']}if p==scope else body)
 review=SimpleNamespace(_handle=object());monkeypatch.setitem(sys.modules,'unreal_candidate_visual_review',review);calls=[];monkeypatch.setattr(m,'dispatch',lambda *args:calls.append(args)or{'saved':True})
 seen=set();m._poll_once(seen,{})
 assert not calls and not seen and not list(audit.iterdir())
 review._handle=None;m._poll_once(seen,{})
 assert len(calls)==1 and request.name in seen
 assert json.loads((audit/'020-photo_plants-result.json').read_text())['ok']is True
