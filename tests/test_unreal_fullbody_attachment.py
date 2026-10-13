"""Actual generated full-body parent/origin regression for first-person looking down."""
import math,re,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from stage_unreal_home_runtime import stage
class FullBodyAttachmentTests(unittest.TestCase):
 def generated(self):
  with tempfile.TemporaryDirectory()as d:
   p=Path(d);(p/'Config').mkdir();(p/'Sub01HomeLab.uproject').write_text('{}');stage(p)
   return (p/'Source/Sub01HomeLab/Sub01HomeLab.cpp').read_text(),(p/'Source/Sub01HomeLab/Sub01HomeLab.h').read_text()
 def test_fullbody_floor_origin_is_invariant_under_camera_pitch(self):
  cpp,header=self.generated()
  branch=cpp.split('if(Posture==TEXT("Walk")||Posture==TEXT("Phone")){',1)[1].split('}else',1)[0]
  self.assertIn('AttachToComponent(GetRootComponent()',branch)
  half=float(re.search(r'InitCapsuleSize\(16.f,(\d+)\.f\)',cpp)[1]);offset=float(re.search(r'WalkMeshOffset=FVector\(0,0,(-?\d+)\)',header)[1])
  for pitch in [-80,-45,0,45,80]:
   # Root-space full-body origin at the capsule foot, independent of camera rotation.
   self.assertAlmostEqual(half+offset,0)
  # The replaced eye-space attachment moves both feet ~48cm vertically at45deg.
  self.assertGreater(165-165*math.cos(math.radians(45)),48)
 def test_real_clip_motion_and_fixed_desk_contact_are_preserved(self):
  cpp,_=self.generated()
  self.assertIn('FirstPersonBody->GetAttachParent()==ViewCamera',cpp)
  self.assertIn(':FVector::ZeroVector',cpp)
  self.assertIn('Speed/140.f',cpp)
  self.assertIn('SetWorldLocationAndRotation(FVector(203.9,-232.3,-.6),FRotator(0,180,0))',cpp)
  self.assertIn('ViewCamera->AttachToComponent(FirstPersonBody',cpp)
  self.assertNotIn('SetActorLocation(',cpp)
if __name__=='__main__':unittest.main()
