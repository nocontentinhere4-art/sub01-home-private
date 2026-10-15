import copy
import json
from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import prepare_real_kitchen_bundle as b


def source():
 return json.loads((ROOT/'docs/proposed/actual-kitchen-source-proof-20261014.json').read_text())['source_report']['source']


def test_actual_old_four_lower_leafs_do_not_cover_real_carcasses():
 # Actual packet values reproduce the user's rightmost182mm uncovered opening.
 bay=b.LOWER_BAYS[3];old_center=b.LOWER_CENTERS[3]
 assert bay[1]-(old_center+.325)==pytest.approx(.182)
 assert b.LOWER_CENTERS[0]-.325-b.LOWER_BAYS[0][0]==pytest.approx(.082)


@pytest.mark.parametrize('index',range(4))
def test_corrected_source_fit_has_authored_2mm_reveal_on_every_edge(index):
 r=source();contacts={'floor_m':.025,'counter_underside_m':.8675};f=b.lower_door_fit(r,contacts,index)
 panel=f['expected_panel_bounds_browser_m'];carcass=f['carcass_bounds_xy_m']
 for k in (0,1):
  assert panel[0][k]-carcass[0][k]==pytest.approx(.002)
  assert carcass[1][k]-panel[1][k]==pytest.approx(.002)
 assert f['hinge_browser_m'][0]==panel[0][0]
 assert f['hinge_browser_m'][2]==-3.192
 assert panel[0][1]==pytest.approx(.127)and panel[1][1]==pytest.approx(.8655)


def test_actual_plan_changes_only_lower_leaf_fit_not_real_bays_or_upper_hinges():
 r=source();contacts={'floor_m':.025,'counter_underside_m':.8675};p=b.plan(r,contacts)
 for i in range(4):
  body=next(x for x in p['assemblies']if x['name']=='Lower_cabinet_body_'+str(i+1))
  door=next(x for x in p['assemblies']if x['name']=='Lower_cabinet_hinge_'+str(i+1))
  upper=next(x for x in p['assemblies']if x['name']=='Cabinet hinge '+str(i+1))
  assert body['target_dimensions_m'][0]==pytest.approx(b.LOWER_BAYS[i][1]-b.LOWER_BAYS[i][0])
  assert door['rigid_parts']==['mesh-2','mesh-3','mesh-4']
  assert upper['hinge_browser_m']==[b.UPPER_CENTERS[i]-.771/2,2.05,-3.531]
 assert p['native_ready']is False and p['lower_door_fit_profile']==b.LOWER_FIT_PROFILE


def test_wrong_source_door_dimensions_or_contacts_refuse():
 r=copy.deepcopy(source());r['door']['parts'][1]['bounds_m'][1][0]+=.02
 with pytest.raises(ValueError):b.lower_door_fit(r,{'floor_m':.025,'counter_underside_m':.8675},3)
 with pytest.raises(ValueError):b.lower_door_fit(source(),{'floor_m':float('nan'),'counter_underside_m':.8675},3)


def test_native_manifest_rechecks_new_lower_hinge_and_actual_closed_panel_bounds():
 import prepare_real_kitchen_native_bundle as native
 import test_real_kitchen_native as old
 proof=old.fixture();report=proof['source_report'];report['lower_door_fit_profile']=b.LOWER_FIT_PROFILE
 report['lower_closed_fit_proof']={'passed':True,'profile':b.LOWER_FIT_PROFILE,'doors':[{}]*4}
 for hinge in proof['hinges'][4:]:
  f=b.lower_door_fit(report['source'],report['actual_home_contacts'],hinge['index']-4)
  hinge['hinge_ue_cm']=[100*f['hinge_browser_m'][k]for k in(0,2,1)]
  frame=next(x for x in proof['parts']if x['assembly']==hinge['assembly']and x['source_part']=='mesh-1')
  frame['bounds_browser_m']=f['expected_panel_bounds_browser_m']
 native.validate_manifest(proof)
 for change in ('hinge','frame','missing_actual_proof'):
  bad=copy.deepcopy(proof)
  if change=='hinge':bad['hinges'][7]['hinge_ue_cm'][0]+=.1
  elif change=='frame':next(x for x in bad['parts']if x['assembly']=='Lower_cabinet_hinge_4'and x['source_part']=='mesh-1')['bounds_browser_m'][1][0]-=.182
  else:bad['source_report'].pop('lower_closed_fit_proof')
  with pytest.raises(ValueError):native.validate_manifest(bad)
