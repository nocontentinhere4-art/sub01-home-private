import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('basis',Path(__file__).parents[1]/'tools/unreal_candidate_tv_sofa_basis.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def test_surface_center_is_actual_area_integral_not_bounds_center():
    result=m.surface_geometry([[[10,0,0],[10,2,0],[10,0,4]]])
    assert result['area_weighted_surface_centroid_cm']==pytest.approx([10,2/3,4/3])
    assert result['surface_area_cm2']==pytest.approx(4)
def test_nonplanar_geometry_is_refused():
    with pytest.raises(AssertionError):m.surface_geometry([[[10,0,0],[10,2,0],[10,0,4]],[[11,0,0],[11,2,0],[11,0,4]]])
