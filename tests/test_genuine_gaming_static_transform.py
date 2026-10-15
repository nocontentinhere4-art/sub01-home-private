import importlib.util
from pathlib import Path
import math
p=Path(__file__).parents[1]/'tools/unreal_candidate_genuine_gaming_assembly.py'
spec=importlib.util.spec_from_file_location('gaming_transform',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def test_ps5_canonical_offset_cancels_before_external_root():
 unit=.001200652897522776;offset=[-.1751616022,2.5083943944,.0106206000];root=[-367.3836744485,-122.6447615420,125.8106160224]
 delta=[root[i]-m.rotate(offset,180)[i]for i in range(3)]
 for point in [[0,0,0],[123,-90,329],[-100,200,-5]]:
  canonical=[point[i]*unit+offset[i]for i in range(3)]
  actual=[m.rotate(canonical,180)[i]+delta[i]for i in range(3)]
  expected=[m.rotate([v*unit for v in point],180)[i]+root[i]for i in range(3)]
  assert max(abs(a-b)for a,b in zip(actual,expected))<1e-12
def test_rigid_rotation_preserves_controller_16cm_width():
 a=m.rotate([-8,0,0],90);b=m.rotate([8,0,0],90)
 assert math.dist(a,b)==16 and abs(a[0])<1e-12 and abs(b[0])<1e-12

def test_quaternion_composition_preserves_normalization():
 q=m.qmul([0,0,1,0],[2**-.5,0,0,2**-.5]);assert abs(sum(v*v for v in q)-1)<1e-12
