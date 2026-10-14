import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from unreal_import_controller_prop import physical_slots

def test_only_actual_main_material_is_physical_never_baked_shadow_or_mixed_proxy():
 assert physical_slots(['controller'])
 assert not physical_slots([])
 assert not physical_slots(['controller_contact'])
 assert not physical_slots(['controller','controller_contact'])
 assert not physical_slots(['Unknown'])

def test_normalization_rejects_changed_shape_material_or_provenance():
 import copy,pytest
 from unreal_import_controller_prop import validate_normalization,SOURCE_SHA,NORMALIZED_SHA
 physical={'materials':['controller'],'polygons':13848,'triangle_positions_sha256':'a'*64,'world_min_m':[0,0,0],'world_max_m':[.15,.1,.05]}
 shadow={'materials':['controller_contact'],'polygons':2,'triangle_positions_sha256':'b'*64,'world_min_m':[0,0,0],'world_max_m':[.17,.12,0]}
 good={'original_sha256':SOURCE_SHA,'normalized_sha256':NORMALIZED_SHA,'floating_position_accessors':True,'before':[physical,shadow],'after':copy.deepcopy([physical,shadow])}
 validate_normalization(good)
 for kind in ('hash','material','polygon','source','float'):
  bad=copy.deepcopy(good)
  if kind=='hash':bad['after'][0]['triangle_positions_sha256']='c'*64
  if kind=='material':bad['after'][0]['materials']=['Unknown']
  if kind=='polygon':bad['after'][0]['polygons']=1
  if kind=='source':bad['original_sha256']='Wrong'
  if kind=='float':bad['floating_position_accessors']=False
  with pytest.raises(ValueError):validate_normalization(bad)
