import importlib.util,os
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('scope',Path(__file__).parents[1]/'tools/private_home_candidate_scope.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def scope():return {'schema':'sub01.private-next-home-candidate-scope.v1','candidate_project':str(m.CANDIDATE),'source_project':str(m.SOURCE),'original_map_sha256':m.MAP_SHA,'module_sha256':m.MODULE_SHA,'deadline_epoch':1792117175,'no_live_promotion':True,'game_pid':159171,'game_start_ticks':976840968,'editor_pid':os.getpid(),'editor_start_ticks':321}
def contexts():return ((976840968,'S',[str(m.SOURCE/'Sub01HomeLab.uproject').encode(),b'-game']),(321,'S',[str(m.CANDIDATE/'Sub01HomeLab.uproject').encode(),b'-nullrhi']))
def test_valid_isolated_scope():assert m.validate_scope(scope(),m.CANDIDATE,*contexts(),1792082700)
@pytest.mark.parametrize('field,value',[('editor_pid',123),('game_start_ticks',0),('original_map_sha256','bad'),('module_sha256','bad'),('no_live_promotion',False),('deadline_epoch',1792117176)])
def test_reject_forged_or_overbroad_scope(field,value):
 s=scope();s[field]=value
 with pytest.raises(AssertionError):m.validate_scope(s,m.CANDIDATE,*contexts(),1792082700)
def test_never_authorize_active_project_with_candidate_scope():
 with pytest.raises(AssertionError):m.validate_scope(scope(),m.SOURCE,*contexts(),1792082700)
def test_candidate_must_not_be_game():
 game,editor=contexts();editor[2].append(b'-game')
 with pytest.raises(AssertionError):m.validate_scope(scope(),m.CANDIDATE,game,editor,1792082700)
def test_deadline_expired():
 with pytest.raises(AssertionError):m.validate_scope(scope(),m.CANDIDATE,*contexts(),1792117175)

def promoted_scope():
 s=scope();s.update(live_generation='playable-14acd9d355c6-e571937b708c',game_pid=193148,game_start_ticks=978377926,live_playable_project=str(m.PLAYABLE),live_map_sha256=m.PLAYABLE_MAP_SHA,live_module_sha256=m.PLAYABLE_MODULE_SHA);return s
def promoted_contexts():
 return ((978377926,'S',[str(m.PLAYABLE/'Sub01HomeLab.uproject').encode(),b'-game']),contexts()[1])
def test_exact_promoted_live_game_still_only_authorizes_candidate():
 assert m.validate_scope(promoted_scope(),m.CANDIDATE,*promoted_contexts(),1792094100)
 for p in (m.SOURCE,m.PLAYABLE):
  with pytest.raises(AssertionError):m.validate_scope(promoted_scope(),p,*promoted_contexts(),1792094100)
@pytest.mark.parametrize('field,value',[('live_generation','arbitrary'),('game_pid',193149),('game_start_ticks',978377927),('live_playable_project',str(m.SOURCE)),('live_map_sha256','bad'),('live_module_sha256','bad')])
def test_promoted_generation_cannot_adopt_other_game_or_assets(field,value):
 s=promoted_scope();s[field]=value
 with pytest.raises(AssertionError):m.validate_scope(s,m.CANDIDATE,*promoted_contexts(),1792094100)
def test_promoted_scope_does_not_accept_departed_original_game():
 with pytest.raises(AssertionError):m.validate_scope(promoted_scope(),m.CANDIDATE,*contexts(),1792094100)
