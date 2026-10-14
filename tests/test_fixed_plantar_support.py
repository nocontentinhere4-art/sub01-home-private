import shutil,subprocess,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from unreal_fixed_plantar_support import POLICY_CPP


def test_actual_fixed_band_and_localized_support_geometry_execute(tmp_path):
    compiler=shutil.which('clang++')or shutil.which('g++')
    if not compiler:pytest.skip('No C++ compiler')
    source=tmp_path/'support.cpp';source.write_text('#include <cmath>\n'+POLICY_CPP+r'''
int main(){using namespace Sub01FixedPlantar;
 if(!Member(-87.8,-.8,-88.0354538,.95))return 1;
 if(Member(-86.8,-.8,-88.0354538,.95))return 2; // sock/cuff, irrespective of posed height
 if(Member(-87.8,.8,-88.0354538,.95))return 3;
 if(Member(-87.8,-.8,-88.0354538,.29))return 4;
 if(Member(NAN,-.8,-88.0354538,.95))return 5;
 Point A{0,0,2.55,-.53},B{2,0,2.75,-.53},C{0,2,3.2,-.53};
 if(std::fabs(SupportArea(A,B,C,2.5)-2)>1e-9)return 6; // tilted captured toe patch
 C.Z=24.5;if(SupportArea(A,B,C,2.5)!=0)return 7; // raised heel is not called support
 C.Z=2.4;if(SupportArea(A,B,C,2.5)!=0)return 8; // penetration cannot be support
 C.Z=3.0;C.NormalZ=.8;if(SupportArea(A,B,C,2.5)!=0)return 9;
 C.NormalZ=-.53;if(SupportArea(A,B,C,NAN)!=0)return 10;
 return 0;}
''')
    result=subprocess.run([compiler,'-std=c++17','-Wall','-Werror',str(source),'-o',str(tmp_path/'support')],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert subprocess.run([str(tmp_path/'support')]).returncode==0
