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
using Sub01FirstPersonMotion::AuthoredWalkRate;
using Sub01FirstPersonMotion::HeadingWalkScale;
int main(){
 assert(HeadingWalkScale(0,0)==1);
 assert(HeadingWalkScale(0,90)==0&&HeadingWalkScale(0,180)==0);
 assert(HeadingWalkScale(0,-90)==0&&HeadingWalkScale(0,-180)==0);
 assert(std::abs(HeadingWalkScale(0,45)-.25)<1e-12);
 assert(std::abs(HeadingWalkScale(179,-179)-HeadingWalkScale(0,2))<1e-12);
 assert(HeadingWalkScale(0,std::numeric_limits<double>::quiet_NaN())==0);
 // A right-angle corridor turn used to request full sideways travel while
 // yaw eased. Integrate the actual production policy, without teleporting
 // the pawn or changing its collision route: transverse input demand falls >70%.
 for(double fps: {30.,60.,144.}){
  double yaw=0,original=0,aligned=0;
  for(int i=0;i<int(2*fps);++i){
   yaw=SmoothAngle(yaw,90,1./fps,180);
   double side=std::sin((90-yaw)*3.14159265358979323846/180.);
   original+=140*side/fps;
   aligned+=140*side*HeadingWalkScale(yaw,90)/fps;
  }
  assert(original>15&&aligned<original*.30);
 }
 // Braking below 14 cm/s must slow the authored clip, not retain a .1 floor.
 assert(std::abs(AuthoredWalkRate(7)-.05)<1e-12);
 assert(std::abs(AuthoredWalkRate(1.01)-1.01/140.)<1e-12);
 assert(AuthoredWalkRate(140)==1&&AuthoredWalkRate(280)==1.2);
 assert(AuthoredWalkRate(0)==0&&AuthoredWalkRate(-2)==0);
 assert(AuthoredWalkRate(10,0)==0);
 assert(AuthoredWalkRate(std::numeric_limits<double>::infinity())==0);
 assert(AuthoredWalkRate(std::numeric_limits<double>::quiet_NaN())==0);
 double previous=AuthoredWalkRate(140);
 for(int i=139;i>=0;--i){double rate=AuthoredWalkRate(i);assert(rate<=previous&&rate>=0);previous=rate;}
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
 from tools.unreal_native_route import METHODS as route
 cpp=base.CPP+live+hands+route
 header,result=motion.install(base.HEADER,cpp)
 assert header==base.HEADER
 assert result.count(motion.ALIGNED_MOVE)==1
 assert result.count(motion.SNAP)==1 and motion.SWAY not in result
 assert route in result # Route diagnostic remains unchanged; only Live mode is smoothed.
 assert motion.WALK_RATE not in result and result.count(motion.MEASURED_WALK_RATE)==1
 for unchanged in ['GetCharacterMovement()->IsMovingOnGround()&&Speed>1;',
                   'HandsClips.Contains(TEXT("Idle"))',
                   '(PlayingIdle?1.f:0.f)',
                   'Instance->TargetSequence=Clip;']:
  assert unchanged in result
 for unchanged in ['Movement->MaxWalkSpeed=140; Movement->MaxAcceleration=450;',
                   'Movement->BrakingDecelerationWalking=700; Movement->MaxStepHeight=22;',
                   'Input->BindAxis("Turn",this,&APawn::AddControllerYawInput);',
                   'Input->BindAxis("LookUp",this,&APawn::AddControllerPitchInput);',
                   'AddMovementInput(Delta/Distance,FMath::Clamp(Distance/45.f,.15f,1.f));',
                   'Instance->TargetSequence=Clip;']:
  assert unchanged in result
 assert 'SetActorLocation' not in motion.SMOOTH and 'SetBone' not in motion.AUTHORED_ONLY
 with pytest.raises(ValueError):motion.install(header,result)
