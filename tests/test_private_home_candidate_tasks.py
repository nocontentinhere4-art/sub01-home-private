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
