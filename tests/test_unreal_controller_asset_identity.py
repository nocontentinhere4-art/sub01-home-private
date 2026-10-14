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
