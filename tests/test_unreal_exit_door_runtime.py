"""Execute the same bounded hinge policy used by the native actor, without GPU."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('door',ROOT/'tools/unreal_exit_door_runtime.py');door=importlib.util.module_from_spec(spec);spec.loader.exec_module(door)
class DoorAdapterTest(unittest.TestCase):
 def test_exact_hit_install_and_missing_hooks_fail(self):
  h=' void Forward(float Value);';c=' ConfigureActualPC();\n Super::Tick(DeltaSeconds);\n FString Device;\n'
  h,c=door.install(h,c)
  self.assertIn('if(TryNativeExitDoor(Hit.GetComponent()))return;',c)
  self.assertIn('UpdateActualExitDoor(DeltaSeconds)',c)
  self.assertIn('if(TryNativeBathroomDoor(Hit.GetComponent()))return;',c)
  self.assertIn('UpdateActualBathroomDoor(DeltaSeconds)',c)
  self.assertEqual(c.count(' ConfigureActualExitDoor();'),1)
  with self.assertRaises(ValueError):door.install(h,c)
  with self.assertRaises(ValueError):door.install('bad',c)
 @unittest.skipUnless(shutil.which('c++'),'C++ compiler required for native policy execution')
 def test_real_native_policy_clear_open_blocked_close_arc_and_bad_time(self):
  source=door.POLICY+r'''
#include <cassert>
#include <limits>
int main(){
 auto linearClear=[](double,double){return false;};double slide=0;
 for(int i=0;i<40;++i)slide=Sub01ExitDoor::AdvanceSlide(slide,95,.05,linearClear);assert(slide==95);
 auto sweptObstacle=[](double a,double b){return std::fmin(a,b)<=50&&std::fmax(a,b)>=50;};
 for(int i=0;i<40;++i)slide=Sub01ExitDoor::AdvanceSlide(slide,0,.05,sweptObstacle);assert(slide>50);
 assert(Sub01ExitDoor::AdvanceSlide(49,95,.05,sweptObstacle)==49);
 assert(Sub01ExitDoor::AdvanceSlide(0,95,100,linearClear)==4.5);
 assert(Sub01ExitDoor::AdvanceSlide(0,95,-1,linearClear)==0);
 assert(Sub01ExitDoor::InsideBathroom(-150,135,305));
 assert(!Sub01ExitDoor::InsideBathroom(-50,135,305));
 assert(!Sub01ExitDoor::InsideBathroom(-150,135,0));
 assert(!Sub01ExitDoor::InsideBathroom(-150,-150,305));
 auto clear=[](double){return false;};double a=0;
 for(int i=0;i<100;++i)a=Sub01ExitDoor::Advance(a,86.4,1.0/60,clear);
 assert(a==86.4);
 // A capsule blocks an intermediate pose even when the requested endpoint is clear.
 int checks=0;auto capsule=[&](double p){++checks;return p>41&&p<42;};
 a=43;double blocked=Sub01ExitDoor::Advance(a,0,.05,capsule);assert(blocked==a&&checks>=1);
 // Both opening and closing stop rather than pushing/teleporting the capsule.
 assert(Sub01ExitDoor::Advance(39,86.4,.05,capsule)==39);
 assert(Sub01ExitDoor::Advance(43,0,.05,clear)<43);
 assert(Sub01ExitDoor::Advance(0,86.4,100,clear)==3.5);
 assert(Sub01ExitDoor::Advance(20,0,0,clear)==20);
 assert(Sub01ExitDoor::Advance(20,0,-1,clear)==20);
 assert(Sub01ExitDoor::Advance(20,0,std::numeric_limits<double>::quiet_NaN(),clear)==20);
 // Actual leaf dimensions and a capsule standing in the doorway: closing
 // cannot pass through the capsule, but succeeds once the capsule is clear.
 auto doorway=[](double angle){double r=angle*3.141592653589793/180.0;
  double dx=200-147,dy=400-390,x=std::cos(r)*dx+std::sin(r)*dy,y=-std::sin(r)*dx+std::cos(r)*dy;
  double nx=std::fmax(0.0,std::fmin(105.0,x)),ny=std::fmax(-3.75,std::fmin(3.75,y));
  return std::hypot(x-nx,y-ny)<=16.0;};
 a=86.4;for(int i=0;i<100;++i)a=Sub01ExitDoor::Advance(a,0,1.0/60,doorway);assert(a>0);
 a=86.4;for(int i=0;i<100;++i)a=Sub01ExitDoor::Advance(a,0,1.0/60,clear);assert(a==0);
}
'''
  with tempfile.TemporaryDirectory()as t:
   p=Path(t);(p/'door.cpp').write_text(source)
   subprocess.run(['c++','-std=c++17',str(p/'door.cpp'),'-o',str(p/'door')],check=True,capture_output=True)
   subprocess.run([str(p/'door')],check=True,capture_output=True)


PRIVATE_RECEIPT=ROOT/'out/migration-device-restore/current-authored-door-source.json'
@unittest.skipUnless(PRIVATE_RECEIPT.is_file(),'Private current-source integration receipt; absent in fresh checkout')
class CurrentAuthoredDoorGeometryTest(unittest.TestCase):
 def test_exact_current_source_identity_and_bounds(self):
  import json
  receipt=json.loads(PRIVATE_RECEIPT.read_text());self.assertEqual(receipt['source_sha256'],door.CURRENT_SOURCE_SHA256)
  nodes={n['node']:n for n in receipt['nodes']}
  for key in ['leaf','knob']:
   expected=door.GEOMETRY[key];actual=nodes[expected['node']];self.assertEqual(actual['mesh'],expected['mesh'])
   for a in range(3):
    self.assertAlmostEqual((actual['min_cm'][a]+actual['max_cm'][a])/2,expected['center_cm'][a],places=3)
    self.assertAlmostEqual((actual['max_cm'][a]-actual['min_cm'][a])/2,expected['extent_cm'][a],places=3)
  f=door.FITTED_GEOMETRY;c=f['leaf_center_cm'];e=f['leaf_extent_cm']
  self.assertGreater(c[2]-e[2],door.GEOMETRY['verified_entry_floor_cm'])
  self.assertGreater(nodes[54]['min_cm'][2],c[2]+e[2])
  self.assertGreater(c[0]-e[0],nodes[55]['max_cm'][0])
  self.assertLess(c[0]+e[0],nodes[56]['min_cm'][0])

class FittedDoorStructuralClearanceTest(unittest.TestCase):
 def test_full_leaf_rotation_clears_both_jambs_and_detects_bad_latch_fit(self):
  import math
  def overlaps(poly,rect):
   axes=[(1,0),(0,1)]+[(poly[(i+1)%4][1]-poly[i][1],poly[i][0]-poly[(i+1)%4][0])for i in range(4)]
   for a in axes:
    p=[v[0]*a[0]+v[1]*a[1]for v in poly];q=[v[0]*a[0]+v[1]*a[1]for v in rect]
    if max(p)<min(q)or max(q)<min(p):return False
   return True
  def collides(shift):
   frames=[[(lo,384),(hi,384),(hi,390),(lo,390)]for lo,hi in [(142.75,147.25),(252.75,257.25)]]
   for i in range(865):
    a=math.radians(i*.1);c=math.cos(a);s=math.sin(a);h=(147+shift,394)
    poly=[(h[0]+c*x-s*y,h[1]+s*x+c*y)for x,y in [(0,-7.75),(105,-7.75),(105,-.25),(0,-.25)]]
    if any(overlaps(poly,f)for f in frames):return True
   return False
  self.assertFalse(collides(door.FITTED_GEOMETRY['hinge_cm'][0]-147))
  self.assertTrue(collides(.6),'Small closed-pose clearance alone misses latch/frame collision during opening')
