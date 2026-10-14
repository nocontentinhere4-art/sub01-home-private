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
  self.assertEqual(h.count(' void ConfigureActualBathroomDoor();'),1)
  self.assertNotIn('\n ConfigureActualBathroomDoor();',h)
  with self.assertRaises(ValueError):door.install(h,c)
  with self.assertRaises(ValueError):door.install('bad',c)
 @unittest.skipUnless(shutil.which('c++'),'C++ compiler required for native policy execution')
 def test_real_native_policy_clear_open_blocked_close_arc_and_bad_time(self):
  source=r'''
#define UPROPERTY(...)
class UStaticMeshComponent;class UActorComponent;
struct FTransform {};struct FString {};template<class T> using TObjectPtr=T*;
struct ActualInstalledFields {
'''+door.FIELDS+'\n};\n'+door.POLICY+r'''
#include <cassert>
#include <limits>
int main(){
 static_assert(Sub01ExitDoor::MaxArcDegrees==.25);
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
 def test_full_swept_hull_subdivision_clears_latch(self):
  import math
  frames=[[(lo,384),(hi,384),(hi,390),(lo,390)]for lo,hi in [(142.75,147.25),(252.75,257.25)]]
  def blocked(step):
   for i in range(math.ceil(86.4/step)):
    start=i*step;end=min((i+1)*step,86.4);mid=math.radians((start+end)/2);points=[]
    for angle in [start,end]:
     a=math.radians(angle)-mid
     for x,y in [(0,-7.75),(105,-7.75),(105,-.25),(0,-.25)]:points.append((math.cos(a)*x-math.sin(a)*y,math.sin(a)*x+math.cos(a)*y))
    sag=math.hypot(105,7.75)*(1-math.cos(math.radians((end-start)/2)));lo=[min(p[a]for p in points)-sag for a in[0,1]];hi=[max(p[a]for p in points)+sag for a in[0,1]]
    poly=[(147.45+math.cos(mid)*x-math.sin(mid)*y,394+math.sin(mid)*x+math.cos(mid)*y)for x,y in [(lo[0],lo[1]),(hi[0],lo[1]),(hi[0],hi[1]),(lo[0],hi[1])]]
    axes=[(1,0),(0,1)]+[(poly[(n+1)%4][1]-poly[n][1],poly[n][0]-poly[(n+1)%4][0])for n in range(4)]
    for frame in frames:
     separated=False
     for a in axes:
      p=[v[0]*a[0]+v[1]*a[1]for v in poly];q=[v[0]*a[0]+v[1]*a[1]for v in frame]
      if max(p)<min(q)or max(q)<min(p):separated=True;break
     if not separated:return True
   return False
  self.assertTrue(blocked(1.0),'A coarse conservative hull can falsely overlap a clear latch path')
  self.assertFalse(blocked(.25))
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

PRIVATE_BATH=ROOT/'out/migration-device-restore/current-authored-bath-door-source.json'
PRIVATE_HEADER=ROOT/'out/migration-device-restore/current-bath-structural-header.json'
PRIVATE_FLOOR=ROOT/'out/migration-device-restore/current-bath-floor-source.json'
PRIVATE_BACK=ROOT/'out/migration-device-restore/current-bath-backwall-source.json'
@unittest.skipUnless(all(p.is_file()for p in [PRIVATE_BATH,PRIVATE_HEADER,PRIVATE_FLOOR,PRIVATE_BACK]),'Private source triangle integration receipts absent in fresh checkout')
class CurrentBathroomSweptGeometryTest(unittest.TestCase):
 def test_full_source_panel_and_fitted_sweep_clear_real_structural_triangles(self):
  import json
  inputs=[json.loads(p.read_text())for p in [PRIVATE_BATH,PRIVATE_HEADER,PRIVATE_FLOOR,PRIVATE_BACK]]
  for d in inputs:self.assertEqual(d['source_sha256'],door.CURRENT_SOURCE_SHA256)
  b=door.BATH_GEOMETRY;nodes={n['node']:n for n in inputs[0]['nodes']};panel=nodes[b['node']];self.assertEqual(panel['mesh'],b['mesh'])
  for a in range(3):
   self.assertAlmostEqual((panel['min_cm'][a]+panel['max_cm'][a])/2,b['center_cm'][a],places=3)
   self.assertAlmostEqual((panel['max_cm'][a]-panel['min_cm'][a])/2,b['extent_cm'][a],places=3)
  def intersects(box,t):return all(box[0][a]<t['max_cm'][a]and box[1][a]>t['min_cm'][a]for a in range(3))
  def swept(c):return ([c[a]-b['extent_cm'][a]for a in range(3)],[c[a]+b['extent_cm'][a]+(b['slide_cm']if a==1 else 0)for a in range(3)])
  original=swept(b['center_cm']);fitted=swept(b['fitted_center_cm'])
  structures=inputs[1]['triangles']+inputs[2]['triangles']+[t for t in inputs[3]['triangles']if t['mesh']==117]
  self.assertTrue(any(intersects(original,t)for t in structures),'The original imported panel has real structural overlap')
  self.assertFalse(any(intersects(fitted,t)for t in structures),'The whole fitted panel sweep must clear measured structures without exclusions')
  self.assertAlmostEqual(fitted[0][2]-b['floor_top_cm'],b['floor_clearance_cm'],places=4)
  self.assertGreater(fitted[0][0]-nodes[156]['max_cm'][0],.1999)

class FrontThresholdRegressionTest(unittest.TestCase):
 def test_real_threshold_requires_clearance_not_just_main_floor(self):
  threshold=door.GEOMETRY['threshold'];top=threshold['center_cm'][2]+threshold['extent_cm'][2]
  self.assertGreater(top,door.GEOMETRY['verified_entry_floor_cm'])
  self.assertLess(2.6,top,'The previous fit physically penetrated the separate threshold')
  f=door.FITTED_GEOMETRY;c=f['leaf_center_cm'];e=f['leaf_extent_cm']
  self.assertAlmostEqual(c[2]-e[2],3.)
  self.assertAlmostEqual(c[2]+e[2],221.)
  self.assertAlmostEqual(c[2]-e[2]-top,.25)

PRIVATE_THRESHOLD=ROOT/'out/migration-device-restore/current-front-threshold-triangles.json'
@unittest.skipUnless(PRIVATE_THRESHOLD.is_file(),'Private current-source threshold triangle integration receipt absent')
class ActualFrontThresholdTrianglesTest(unittest.TestCase):
 def test_whole_swept_leaf_clears_actual_threshold_triangles(self):
  import json,math
  d=json.loads(PRIVATE_THRESHOLD.read_text());self.assertEqual(d['source_sha256'],door.CURRENT_SOURCE_SHA256)
  self.assertEqual(d['node'],53);self.assertEqual(len(d['triangles']),12)
  self.assertAlmostEqual(max(t['max_cm'][2]for t in d['triangles']),2.75,places=4)
  def intersects(lo,hi,t):return all(lo[a]<t['max_cm'][a]and hi[a]>t['min_cm'][a]for a in range(3))
  self.assertTrue(any(intersects([147.45,386.25,2.6],[252.45,393.75,221.1],t)for t in d['triangles']))
  f=door.FITTED_GEOMETRY;c=f['leaf_center_cm'];e=f['leaf_extent_cm'];hinge=f['hinge_cm']
  for i in range(math.ceil(86.4/.25)):
   a,b=i*.25,min((i+1)*.25,86.4);points=[]
   for angle in[a,b]:
    r=math.radians(angle)
    for x in[-1,1]:
     for y in[-1,1]:
      for z in[-1,1]:
       dx,dy=c[0]+x*e[0]-hinge[0],c[1]+y*e[1]-hinge[1]
       points.append([hinge[0]+math.cos(r)*dx-math.sin(r)*dy,hinge[1]+math.sin(r)*dx+math.cos(r)*dy,c[2]+z*e[2]])
   lo=[min(p[j]for p in points)for j in range(3)];hi=[max(p[j]for p in points)for j in range(3)]
   # The continuous rotation's sagitta inflates horizontal extents only; its
   # complete vertical interval remains3..221, above every real threshold face.
   self.assertFalse(any(intersects(lo,hi,t)for t in d['triangles']))
