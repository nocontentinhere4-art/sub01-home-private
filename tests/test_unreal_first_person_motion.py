"""Execute angular policy and install against real templates, without Unreal/GPU."""
import shutil,subprocess,sys
from pathlib import Path
import pytest
from tools import unreal_first_person_motion as motion

def test_angles_take_shortest_path_have_bounded_rate_and_frame_independent_decay(tmp_path):
 compiler=shutil.which('c++')
 if not compiler:pytest.skip('C++ compiler unavailable')
 motion.stage(tmp_path);source=tmp_path/'motion.cpp';binary=tmp_path/'motion'
 source.write_text(r'''
#include "Sub01FirstPersonMotionPolicy.h"
#include <cassert>
#include <limits>
using Sub01FirstPersonMotion::SmoothAngle;
int main(){
 assert(SmoothAngle(179,-179,1./60,180)>179); // Cross seam by2 degrees, not358.
 assert(SmoothAngle(-179,179,1./60,180)<-179);
 double current=0;
 for(int i=0;i<60;i++){double next=SmoothAngle(current,90,1./60,180);assert(std::abs(next-current)<=3.000001);current=next;}
 assert(current>89&&current<=90);
 double a=0,b=0,c=0;
 for(int i=0;i<30;i++)a=SmoothAngle(a,20,1./30,180);
 for(int i=0;i<60;i++)b=SmoothAngle(b,20,1./60,180);
 for(int i=0;i<144;i++)c=SmoothAngle(c,20,1./144,180);
 assert(std::abs(a-b)<1e-8&&std::abs(b-c)<1e-8);
 assert(std::abs(SmoothAngle(0,180,10,180))<=18); // No large hitch snap.
 assert(SmoothAngle(12,90,0,180)==12&&SmoothAngle(12,90,-1,180)==12);
 assert(SmoothAngle(12,std::numeric_limits<double>::quiet_NaN(),.01,180)==12);
}
''')
 subprocess.run([compiler,'-std=c++17',str(source),'-o',str(binary)],check=True,capture_output=True)
 subprocess.run([str(binary)],check=True,capture_output=True)

def test_install_keeps_real_physics_manual_input_and_original_authored_clips():
 sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
 from tools import stage_unreal_home_runtime as base
 from tools.unreal_live_home_runtime import METHODS as live
 from tools.unreal_home_hands_runtime import CHARACTER_METHODS as hands
 cpp=base.CPP+live+hands
 header,result=motion.install(base.HEADER,cpp)
 assert header==base.HEADER
 assert motion.SNAP not in result and motion.SWAY not in result
 for unchanged in ['Movement->MaxWalkSpeed=140; Movement->MaxAcceleration=450;',
                   'Movement->BrakingDecelerationWalking=700; Movement->MaxStepHeight=22;',
                   'Input->BindAxis("Turn",this,&APawn::AddControllerYawInput);',
                   'Input->BindAxis("LookUp",this,&APawn::AddControllerPitchInput);',
                   'AddMovementInput(Delta/Distance,FMath::Clamp(Distance/45.f,.15f,1.f));',
                   'Instance->TargetSequence=Clip;']:
  assert unchanged in result
 assert 'SetActorLocation' not in motion.SMOOTH and 'SetBone' not in motion.AUTHORED_ONLY
 with pytest.raises(ValueError):motion.install(header,result)
