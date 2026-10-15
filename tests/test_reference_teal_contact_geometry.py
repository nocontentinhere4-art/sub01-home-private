import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('tealproof',Path(__file__).resolve().parents[1]/'tools/prove_reference_teal_bathroom.py');M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)
def test_genuine_transverse_intersection_needs_finite_interior():
 a=[(-2,-2,0),(2,-2,0),(0,2,0)];b=[(0,-1,-1),(0,1,-1),(0,0,1)]
 assert M.positive_crossing(a,b)
 assert M.finite_intersection(a,b)['minimum_interior_edge_clearance_cm']>.001

def test_plane_straddling_beyond_finite_triangle_is_not_collision():
 a=[(-2,-2,0),(2,-2,0),(0,2,0)];b=[(0,10,-1),(0,12,-1),(0,11,1)]
 assert not M.positive_crossing(a,b)

def test_shared_edge_is_contact_not_positive_penetration():
 a=[(0,0,0),(1,0,0),(0,1,0)];b=[(0,0,0),(1,0,0),(.5,0,1)]
 assert not M.positive_crossing(a,b)

def test_below_existing_contact_epsilon_grazing_does_not_inflate():
 a=[(-2,-2,0),(2,-2,0),(0,2,0)];b=[(0,-1,-.00002),(0,1,-.00002),(0,0,1)]
 assert not M.positive_crossing(a,b)

def test_positive_area_support_uses_finite_overlap():
 assert M.clipping_area([(0,0),(2,0),(0,2)],[(0,0),(2,0),(0,2)])==2
 assert M.clipping_area([(0,0),(1,0),(0,1)],[(2,2),(3,2),(2,3)])==0
