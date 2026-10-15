"""Execute the shipped perspective maths, including shifted/infinite-far views."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import unreal_native_projection_metrics as projection
import unreal_native_visual_metrics as metrics

class NativeProjection(unittest.TestCase):
 def test_actual_cpp_policy_reconstructs_frustum_rays_and_rejects_invalid_inputs(self):
  compiler=shutil.which('clang++')or shutil.which('g++')
  if not compiler:self.skipTest('C++ compiler unavailable')
  source='''#include <cmath>
#include <initializer_list>
#include <cassert>
#include <limits>
'''+projection.POLICY+r'''
int main(){
 using namespace Sub01ProjectionMetrics;
 const double PI=std::acos(-1.);const double X=1./std::tan(37.5*PI/180.);
 // A75deg horizontal lens at16:9 must stay75h, not75v.
 const auto Symmetric=FromPerspective(X,X*16./9.,0,0,1,0);
 assert(Symmetric.Valid&&std::fabs(Symmetric.Horizontal-75.)<1.e-10);
 assert(std::fabs(Symmetric.Vertical-46.69212571046592)<1.e-9);
 assert(std::fabs(Symmetric.Left+37.5)<1.e-10);
 // Independent projection roundtrip: each reported edge ray must land on
 // its own NDC border. A shift must not be mistaken for a symmetric lens.
 const auto Shifted=FromPerspective(2,3,.25,-.1,1,0);assert(Shifted.Valid);
 const auto NDC=[PI](double Angle,double Scale,double Offset){return std::tan(Angle*PI/180.)*Scale+Offset;};
 assert(std::fabs(NDC(Shifted.Left,2,.25)+1)<1.e-12);
 assert(std::fabs(NDC(Shifted.Right,2,.25)-1)<1.e-12);
 assert(std::fabs(NDC(Shifted.Bottom,3,-.1)+1)<1.e-12);
 assert(std::fabs(NDC(Shifted.Top,3,-.1)-1)<1.e-12);
 assert(std::fabs(Shifted.Left+Shifted.Right)>1.);
 // Reversed-Z infinite-far perspective hasM23=1,M33=0; depth terms do not
 // enter angular spans. Orthographic/invalid projective structures refuse.
 assert(FromPerspective(1,1,0,0,1,0).Valid);
 assert(!FromPerspective(1,1,0,0,0,1).Valid);
 assert(!FromPerspective(0,1,0,0,1,0).Valid);
 assert(!FromPerspective(-1,1,0,0,1,0).Valid);
 assert(!FromPerspective(1,-1,0,0,1,0).Valid);
 for(double Bad:{std::numeric_limits<double>::infinity(),-std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN()}){
  assert(!FromPerspective(Bad,1,0,0,1,0).Valid);
  assert(!FromPerspective(1,Bad,0,0,1,0).Valid);
  assert(!FromPerspective(1,1,Bad,0,1,0).Valid);
  assert(!FromPerspective(1,1,0,Bad,1,0).Valid);
  assert(!FromPerspective(1,1,0,0,Bad,0).Valid);
  assert(!FromPerspective(1,1,0,0,1,Bad).Valid);
 }
}
'''
  with tempfile.TemporaryDirectory()as folder:
   root=Path(folder);(root/'test.cpp').write_text(source)
   subprocess.run([compiler,'-std=c++17','-Wall','-Wextra','-Werror',str(root/'test.cpp'),'-o',str(root/'test')],check=True,capture_output=True)
   subprocess.run([str(root/'test')],check=True,capture_output=True)
 def test_installer_preserves_existing_metrics_and_publication(self):
  cpp='#include "Sub01HomeLab.h"\n'+metrics.METHODS+'\n// protected suffix\n'
  result=projection.install(cpp)
  # Removing precisely the inserted additions recovers every byte of the old
  # identity, rate limit, privacy/camera witness and atomic publication logic.
  restored=result.replace(projection.BLOCK,'',1).replace(projection.POLICY,'',1)
  for line in projection.INCLUDES.splitlines():
   if line.startswith('#include'):restored=restored.replace(line+'\n','',1)
  restored=restored.replace('#include "Sub01HomeLab.h"\n\n','#include "Sub01HomeLab.h"\n',1)
  self.assertEqual(restored,cpp)
  with self.assertRaises(ValueError):projection.install(result)
  with self.assertRaises(ValueError):projection.install(cpp.replace(' auto* Player=Cast<APlayerController>(GetController());',''))

if __name__=='__main__':unittest.main()
