"""Seated desk camera: the measured eye (not the Head joint), eased both ways like controller play."""
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import unreal_seat_transition_runtime as seat  # noqa: E402
import unreal_controller_play_runtime as play  # noqa: E402
from stage_unreal_home_runtime import stage  # noqa: E402


def staged(*adapters):
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        (project / 'Config').mkdir()
        (project / 'Sub01HomeLab.uproject').write_text('{}')
        stage(project)
        module = project / 'Source/Sub01HomeLab'
        for adapter in adapters:
            adapter.install_module(module)
        return (module / 'Sub01HomeLab.cpp').read_text(), (module / 'Sub01HomeLab.h').read_text()


@pytest.fixture(scope='module')
def installed():
    return staged(seat)


def test_seat_reuses_the_controller_play_eye_and_easing():
    assert seat.EYE_OFFSET_HEAD_CM is play.EYE_OFFSET_HEAD_CM and seat.EYE_EASE_RATE == play.EYE_EASE_RATE
    assert seat.OWNER_MESH == play.OWNER_MESH_OBJECT_PATH
    assert seat.SEAT_EYE_ALPHA_CPP == play.EYE_ALPHA_CPP.replace('Sub01ControllerPlayEyeAlpha', 'Sub01SeatEyeAlpha')
    assert 18.0 < math.hypot(*seat.EYE_OFFSET_HEAD_CM) < 19.0


def test_seated_camera_is_never_snapped_to_the_head_joint_and_eases_both_ways(installed):
    cpp, header = installed
    update = cpp.split('void ASub01HomeCharacter::UpdateSeatTransition(float Dt){', 1)[1].split('\n}\n', 1)[0]
    assert 'SnapToTargetNotIncludingScale' not in update
    sit = update.split('if(Seated&&!SeatBodyAttached&&', 1)[1].split('}else if(!Seated&&SeatBodyAttached){', 1)[0]
    assert 'if(!SeatCameraEasing)SeatEye=ViewCamera->GetComponentLocation();' in sit
    assert 'SetUsingAbsoluteLocation(true)' in sit and 'AttachToComponent' not in sit
    stand = update.split('}else if(!Seated&&SeatBodyAttached){', 1)[1].split('UpdateSeatCamera(Dt);', 1)[0]
    # Standing up no longer jumps the view back to the capsule eye in one frame.
    assert 'SetRelativeLocation(FVector(0,0,74))' not in stand and 'AttachToComponent' not in stand
    assert update.count('UpdateSeatCamera(Dt);') == 1
    camera = cpp.split('void ASub01HomeCharacter::UpdateSeatCamera(float Dt){', 1)[1].split('\n}\n', 1)[0]
    assert 'GetSocketTransform(SeatHead,RTS_World)' in camera and 'GetRotation().GetNormalized().RotateVector(SeatEyeOffset)' in camera
    assert 'Sub01SeatEyeAlpha(Dt)' in camera and 'SetRelativeLocation(FVector(0,0,74))' in camera
    # Hand-back to the capsule only once the eased eye is within 0.5 cm of the standing eye.
    assert 'if(!SeatBodyAttached&&FVector::Dist(SeatEye,Standing)<.5f){' in camera
    for forbidden in ('SetActorLocation', 'SetBoneTransform', 'AddMovementInput', 'Teleport'):
        assert forbidden not in camera
    assert 'void UpdateSeatCamera(float Dt);' in header and 'bool SeatCameraEasing=false;' in header


def test_measured_eye_offset_is_bound_to_the_original_owner_only(installed):
    cpp, _ = installed
    offset = ','.join(repr(v) for v in play.EYE_OFFSET_HEAD_CM)
    assert cpp.count(f'GetPathName()==TEXT("{play.OWNER_MESH_OBJECT_PATH}")?FVector({offset}):FVector::ZeroVector') == 1
    assert f'SeatEyeOffset=FirstPersonBody->GetSkeletalMeshAsset()->GetPathName()==TEXT("{seat.OWNER_MESH}")?FVector({offset}):FVector::ZeroVector;' in cpp
    assert '@@' not in cpp


def compiler():
    found = shutil.which('g++') or shutil.which('clang++')
    if not found:
        pytest.skip('C++ compiler unavailable')
    return found


def run(source):
    with tempfile.TemporaryDirectory() as tmp:
        cpp, exe = Path(tmp) / 'a.cpp', Path(tmp) / 'a'
        cpp.write_text(source)
        built = subprocess.run([compiler(), '-std=c++17', '-Wall', '-Werror', str(cpp), '-o', str(exe)], capture_output=True, text=True)
        assert built.returncode == 0, built.stderr[-2000:]
        return subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout.split('\n')


def test_sit_and_stand_easing_is_frame_rate_independent_with_no_boundary_jump():
    # Mirrors UpdateSeatCamera on one axis: standing eye 165 cm, seated eye 105 cm. Sit for 2 s, then stand
    # (target back to standing) until the < 0.5 cm hand-back, which then sets exactly the standing eye.
    source = '#include <cstdio>\n#include <cmath>\n' + seat.SEAT_EYE_ALPHA_CPP + r'''
int main(){
 const int Fps[]={30,60,144,240};const double Standing=165,Seated=105;
 for(int F:Fps){double Dt=1.0/F,Eye=Standing,T=0,Sit95=-1,MaxStep=0,Prev=Eye;bool Monotonic=true;
  for(;T<2;T+=Dt){Eye+=(Seated-Eye)*Sub01SeatEyeAlpha(Dt);MaxStep=std::fmax(MaxStep,Prev-Eye);if(Eye>Prev||Eye<Seated)Monotonic=false;Prev=Eye;
   if(Sit95<0&&std::fabs(Eye-Seated)<=.05*60)Sit95=T+Dt;}
  double Up=0,Stand95=-1;bool Easing=true;double HandBack=0;
  while(Easing){Eye+=(Standing-Eye)*Sub01SeatEyeAlpha(Dt);Up+=Dt;MaxStep=std::fmax(MaxStep,Eye-Prev);if(Eye<Prev||Eye>Standing)Monotonic=false;Prev=Eye;
   if(Stand95<0&&std::fabs(Eye-Standing)<=.05*60)Stand95=Up;
   if(std::fabs(Eye-Standing)<.5){HandBack=Standing-Eye;Eye=Standing;Easing=false;}}
  std::printf("%d %.4f %.4f %.4f %.4f %d\n",F,Sit95,Stand95,MaxStep,HandBack,Monotonic?1:0);}
 std::printf("guards %.6f %.6f %.6f %.6f\n",Sub01SeatEyeAlpha(0),Sub01SeatEyeAlpha(-1),Sub01SeatEyeAlpha(NAN),Sub01SeatEyeAlpha(5));
}
'''
    rows = run(source)
    for row in rows[:4]:
        fps, sit95, stand95, max_step, hand_back, monotonic = row.split()
        assert monotonic == '1', row
        # 95% within 0.30 s (+- one 30 fps frame) both ways, at every frame rate.
        assert abs(float(sit95) - .30) <= 1 / 30 and abs(float(stand95) - .30) <= 1 / 30, row
        # The old adapter moved the full 60 cm in one frame at sit start and stand end; now at most 29% of it.
        assert float(max_step) <= .29 * 60, row
        # The hand-back to the capsule's (0,0,74) closes under half a centimetre.
        assert 0 <= float(hand_back) < .5, row
    guards = [float(v) for v in rows[4].split()[1:]]
    assert guards[:3] == [0.0, 0.0, 0.0] and abs(guards[3] - (1 - math.exp(-1.0))) < 1e-6


def test_seat_and_controller_adapters_share_one_module_without_clashes():
    cpp, header = staged(seat, play)
    assert cpp.count('static double Sub01SeatEyeAlpha(double Dt)') == 1
    assert cpp.count('static double Sub01ControllerPlayEyeAlpha(double Dt)') == 1
    assert cpp.count('void ASub01HomeCharacter::UpdateSeatCamera(float Dt){') == 1
    assert cpp.count('void ASub01HomeCharacter::UpdateControllerPlayCamera(float Dt){') == 1
    assert header.count('void UpdateSeatCamera(float Dt);') == 1
