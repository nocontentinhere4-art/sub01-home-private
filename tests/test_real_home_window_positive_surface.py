import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from unreal_import_real_home_windows import positive_area_triangles


def test_only_exact_zero_surface_is_removed_and_indices_preserved():
    zero=[[1.,2.,3.],[1.,2.,3.],[4.,5.,6.]]
    collinear=[[0.,0.,0.],[1.,1.,1.],[2.,2.,2.]]
    positive=[[0.,0.,0.],[1.,0.,0.],[0.,1e-20,0.]]
    kept,removed=positive_area_triangles([zero,positive,collinear])
    assert removed==[0,2]
    assert kept==[positive]
    assert kept[0]is positive
