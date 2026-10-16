import importlib.util,copy
from pathlib import Path
import pytest
s=importlib.util.spec_from_file_location('f',Path(__file__).parents[1]/'tools/finalize_kitchen_spawn_map.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def receipt():return {'map_sha256':'a'*64,'all_file_hashes_verified':True,'independent_writable_copies':True,'files':[{'path':m.MAP,'sha256':'a'*64,'bytes':10},{'path':'Content/ApprovedHands.uasset','sha256':'c'*64,'bytes':30}],'protected_live_assets':['Content/ApprovedHands.uasset']}
def test_only_map_row_changes_and_protected_hands_remain_exact():
 old=receipt();before=copy.deepcopy(old);new=m.updated_receipt(old,'a'*64,'b'*64,14,'d'*64)
 assert old==before and new['files'][1]==old['files'][1]and new['protected_live_assets']==old['protected_live_assets']and new['bytes']==44
@pytest.mark.parametrize('change',[lambda d:d.update(map_sha256='e'*64),lambda d:d['files'].append(copy.deepcopy(d['files'][0])),lambda d:d['files'][0].update(sha256='e'*64),lambda d:d.update(all_file_hashes_verified=False)])
def test_tampered_or_ambiguous_preseal_refused(change):
 old=receipt();change(old)
 with pytest.raises(AssertionError):m.updated_receipt(old,'a'*64,'b'*64,14,'d'*64)
