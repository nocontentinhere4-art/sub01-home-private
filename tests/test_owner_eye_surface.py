import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from audit_owner_eye_surface import surface_point


def test_inverse_texture_mapping_preserves_actual_triangle_coordinates():
    hit=surface_point([.25,.5],[[1,2,3],[3,2,3],[1,6,5]],[[0,0],[1,0],[0,1]],[0,1,2])
    assert hit['point']==[1.5,4,4]
    assert hit['weights']==[.25,.25,.5]


def test_shared_seam_same_surface_allowed_but_uv_overlap_other_surface_rejected():
    uv=[[0,0],[1,0],[0,1],[0,0],[1,0],[0,1]]
    pos=[[0,0,0],[1,0,0],[0,1,0]]*2
    assert surface_point([.2,.3],pos,uv,[0,1,2,3,4,5])['point']==[.2,.3,0]
    pos[-1]=[0,1,1]
    with pytest.raises(ValueError,match='ambiguous'):
        surface_point([.2,.3],pos,uv,[0,1,2,3,4,5])


def test_absent_nonfinite_or_off_texture_annotations_fail_closed():
    for point in ([.8,.8],[float('nan'),.1],[1.1,.1]):
        with pytest.raises(ValueError):surface_point(point,[[0,0,0]]*3,[[0,0],[1,0],[0,1]],[0,1,2])
