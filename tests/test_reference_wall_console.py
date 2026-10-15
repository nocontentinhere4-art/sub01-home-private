"""Actual wall-fit witness and geometry filtering regressions, without Unreal."""
import copy,importlib.util,json
from pathlib import Path
import pytest
BASE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('wall_console_import',BASE/'tools/unreal_import_reference_wall_console.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def witnesses():
 evidence=json.loads((BASE/'docs/proposed/actual-reference-wall-console-source-20261015.json').read_text())
 return evidence['source'],evidence['actual_bvh_proof']

def test_actual_measured_full_room_source_witness():
 report,proof=witnesses();module.validate_contract(report,proof)
 assert proof['protected_parts']==521
 assert len(proof['rigid_reuse_congruency'])==5
 assert report['controller_display_width_m']==.16

@pytest.mark.parametrize('field,value',[('unresolved',[{'part':'WCPart03','protected_part':'TV','pairs':1}]),('epsilon_m',.001),('ignored_pairs',1),('actual_window_source_sha256','wrong-source'),('protected_parts',238)])
def test_partial_or_collision_filtered_source_cannot_activate(field,value):
 report,proof=witnesses();proof[field]=value
 with pytest.raises(RuntimeError):module.validate_contract(report,proof)

def test_backplate_attachment_cannot_authorize_general_penetration():
 report,proof=witnesses();proof['measured_attachment_contacts'][0]['protected_part']='TV frame'
 with pytest.raises(RuntimeError):module.validate_contract(report,proof)

def test_existing_device_shape_and_scale_must_be_preserved():
 report,proof=witnesses();proof['rigid_reuse_congruency'][0]['maximum_bidirectional_triangle_edge_shape_distance_m']=.001
 with pytest.raises(RuntimeError):module.validate_contract(report,proof)

def test_only_exact_zero_area_triangles_are_removed():
 zero=[(0.,0.,0.),(1.,0.,0.),(2.,0.,0.)]
 tiny=[(0.,0.,0.),(1.,0.,0.),(1.,1e-15,0.)]
 regular=[(0.,0.,0.),(1.,0.,0.),(0.,1.,0.)]
 kept,indices=module.positive_triangles([zero,tiny,regular])
 assert kept==[tiny,regular]and indices==[0]
