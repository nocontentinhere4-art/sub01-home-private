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
  self.assertEqual(c.count(' ConfigureActualExitDoor();'),1)
  with self.assertRaises(ValueError):door.install(h,c)
  with self.assertRaises(ValueError):door.install('bad',c)
 @unittest.skipUnless(shutil.which('c++'),'C++ compiler required for native policy execution')
 def test_real_native_policy_clear_open_blocked_close_arc_and_bad_time(self):
  source=door.POLICY+r'''
#include <cassert>
#include <limits>
int main(){
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

PRIVATE_HOUSE=ROOT/'out/lighting-v23/unreal-home-lab/Sub01HomeLab/SourceAssets/full-home.glb'
@unittest.skipUnless(PRIVATE_HOUSE.is_file(),'Private imported-house asset integration check; absent in fresh checkout')
class PrivateAuthoredDoorGeometryTest(unittest.TestCase):
 def test_exact_source_leaf_and_knob_world_bounds(self):
  import json,struct,itertools
  raw=PRIVATE_HOUSE.read_bytes();size=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+size]);parents={c:i for i,n in enumerate(doc['nodes'])for c in n.get('children',[])}
  def mul(a,b):return [sum(a[k*4+r]*b[c*4+k]for k in range(4))for c in range(4)for r in range(4)]
  def world(i):
   n=doc['nodes'][i];self.assertNotIn('rotation',n);scale=n.get('scale',[1]*3);translation=n.get('translation',[0]*3)
   m=n.get('matrix',[scale[0],0,0,0,0,scale[1],0,0,0,0,scale[2],0,*translation,1])
   return mul(world(parents[i]),m)if i in parents else m
  for label in ['leaf','knob']:
   expected=door.GEOMETRY[label];node=doc['nodes'][expected['node']];self.assertEqual(node['mesh'],expected['mesh']);m=world(expected['node']);points=[]
   for primitive in doc['meshes'][node['mesh']]['primitives']:
    a=doc['accessors'][primitive['attributes']['POSITION']]
    for corner in itertools.product(*zip(a['min'],a['max'])):
     p=[sum(m[k*4+r]*corner[k]for k in range(3))+m[12+r]for r in range(3)];points.append([100*p[0],100*p[2],100*p[1]])
   for axis in range(3):
    lo=min(p[axis]for p in points);hi=max(p[axis]for p in points)
    self.assertAlmostEqual((lo+hi)/2,expected['center_cm'][axis],places=3)
    self.assertAlmostEqual((hi-lo)/2,expected['extent_cm'][axis],places=3)
