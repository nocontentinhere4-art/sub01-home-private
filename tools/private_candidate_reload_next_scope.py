"""Refresh only the existing candidate callback's guard after root scope transition."""
from pathlib import Path
import gc,importlib,json,os,time,types
import unreal
assert os.getpid()==203351
import private_home_candidate_scope as scope
scope=importlib.reload(scope)
assert scope.active_candidate_guard(unreal.Paths.project_dir())
callbacks=[x for x in gc.get_objects()if isinstance(x,types.FunctionType)and x.__name__=='tick'and Path(x.__code__.co_filename).name=='private_home_candidate_bootstrap.py']
assert len(callbacks)==1,'One existing candidate callback required; never register another'
callback=callbacks[0]
assert callback.__globals__.get('CANDIDATE')==scope.CANDIDATE
callback.__globals__['active_candidate_guard']=scope.active_candidate_guard
(scope.CANDIDATE/'private-audit/next-generation-scope-refresh.json').write_text(json.dumps({'schema':'sub01.exact-candidate-scope-refresh.v1','editor_pid':os.getpid(),'game_pid':209503,'game_start_ticks':979714171,'existing_callback_retained':True,'new_callback_registered':False,'world_changed':False,'input_changed':False,'epoch':time.time()},indent=2)+'\n')
