import sys,tempfile,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from unreal_typing_review_policy import CPP
class Review(unittest.TestCase):
 def test_actual_cpp_distinguishes_pose_hover_from_key_contact(self):
  source=CPP+r'''
#include <cassert>
#include <limits>
int main(){using Sub01TypingReview::DistalGap;
 assert(!DistalGap(.3442092,.0774852,false));
 assert(DistalGap(.3442092,.0774852,true));
 assert(DistalGap(.08,.0774852,false));
 assert(!DistalGap(2.781324,.0774852,true));
 assert(!DistalGap(3.805223,.0774852,true));
 assert(!DistalGap(-.11,.0774852,true));
 assert(!DistalGap(.1,std::numeric_limits<double>::quiet_NaN(),true));
 assert(!DistalGap(std::numeric_limits<double>::infinity(),.01,true));
 assert(!DistalGap(.1,-.01,true));
}
'''
  with tempfile.TemporaryDirectory()as d:
   p=Path(d);(p/'case.cpp').write_text(source);subprocess.run(['c++','-std=c++17',str(p/'case.cpp'),'-o',str(p/'case')],check=True,capture_output=True);subprocess.run([str(p/'case')],check=True)
 def test_refused_real_load_hides_raw_pose(self):
  from unreal_contact_profile_runtime import LOAD
  self.assertIn('FirstPersonBody->SetVisibility(false,true)',LOAD)
  self.assertIn('HoverFlag&&HandsDiagnostic&&FParse::Param',LOAD)
  self.assertIn('NO physical seating, full-palm or key-press acceptance',LOAD)
if __name__=='__main__':unittest.main()
