"""Execute the real native arrival expression against captured stair coordinates."""
import re,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from unreal_live_home_runtime import METHODS

class SolidFloorArrival(unittest.TestCase):
    def test_actual_cpp_uses_contact_surface_not_capsule_hover_air(self):
        compiler=shutil.which('clang++')or shutil.which('g++')
        if not compiler:self.skipTest('C++ compiler unavailable')
        code=METHODS.split('const FFindFloorResult& ActualFloor=',1)[1].split('if(Distance<12',1)[0]
        predicate=re.search(r'if\((Distance<12[^\n]+?)\)\{',METHODS).group(1)
        pre='''#include <cmath>
struct Point{float Z;};struct Hit{Point ImpactPoint;};struct FFindFloorResult{bool bBlockingHit;Hit HitResult;};
struct Move{FFindFloorResult CurrentFloor;bool ground;bool IsMovingOnGround(){return ground;}} move;
Move* GetCharacterMovement(){return &move;}struct Cap{float GetScaledCapsuleHalfHeight(){return 91;}}cap;
Cap* GetCapsuleComponent(){return &cap;}namespace FMath{float Abs(float x){return std::abs(x);}}
struct DeltaT{float Size(){return 8;}}Delta;
bool arrival(float centre,float solid,float expected,bool blocking=true,bool ground=true){move={{blocking,{{solid}}},ground};Point Here{centre},Floor{expected};
'''
        body='const FFindFloorResult& ActualFloor='+code+'return '+predicate+';}\n'
        cases='''int main(){
// Real roundtrip stair_bottom-return centre=113.151cm, capsulehalf=91cm.
// A first 18cm tread is within the original20cm floor tolerance; hover air is not solid.
if(!arrival(113.151f,18.f,0.f))return 1;
if(arrival(113.151f,18.f,0.f,false))return 2;
if(arrival(113.151f,18.f,0.f,true,false))return 3;
if(!arrival(395.65f,304.65f,300.f))return 4;
if(arrival(395.65f,404.65f,300.f))return 5;
return 0;}
'''
        with tempfile.TemporaryDirectory()as tmp:
            source=Path(tmp)/'check.cpp';source.write_text(pre+body+cases);binary=Path(tmp)/'check'
            subprocess.run([compiler,'-std=c++17',str(source),'-o',str(binary)],check=True,capture_output=True)
            subprocess.run([str(binary)],check=True,capture_output=True)
        self.assertIn('IsMovingOnGround()',predicate)

if __name__=='__main__':unittest.main()
