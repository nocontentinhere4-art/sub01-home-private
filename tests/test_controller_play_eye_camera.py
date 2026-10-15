"""Controller play camera: measured eye (not the Head joint) and frame-rate independent easing both ways."""
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import unreal_controller_play_runtime as play  # noqa: E402
from stage_unreal_home_runtime import stage  # noqa: E402


def test_camera_is_never_snapped_to_the_head_joint_and_eases_both_ways():
    m = play.methods()
    assert 'SnapToTargetNotIncludingScale,ControllerPlayHead' not in m
    begin = m.split('ControllerPlayActive=true;', 1)[1].split('UE_LOG', 1)[0]
    assert 'SetUsingAbsoluteLocation(true)' in begin and 'ControllerPlayEye=ViewCamera->GetComponentLocation()' in begin
    end = m.split('if(!Play&&ControllerPlayActive){', 1)[1].split('if(!ControllerPlayActive)return;', 1)[0]
    # Ending play no longer jumps the view back to the capsule eye in one frame.
    assert 'SetRelativeLocation(FVector(0,0,74))' not in end and 'UpdateControllerPlayCamera(Dt)' in end
    active = m.split('ControllerPlayProp->SetVisibility(true);', 1)[1].split('\n}', 1)[0]
    assert 'UpdateControllerPlayCamera(Dt);' in active
    camera = m.split('void ASub01HomeCharacter::UpdateControllerPlayCamera(float Dt){', 1)[1].split('\n}\n', 1)[0]
    assert 'GetSocketTransform(ControllerPlayHead,RTS_World)' in camera and 'GetRotation().GetNormalized().RotateVector(ControllerPlayEyeOffset)' in camera
    assert 'Sub01ControllerPlayEyeAlpha(Dt)' in camera and 'SetRelativeLocation(FVector(0,0,74))' in camera
    # Hand-back to the capsule only once the eased eye is within 0.5 cm of the standing eye.
    assert 'FVector::Dist(ControllerPlayEye,Standing)<.5f' in camera
    for forbidden in ('SetActorLocation', 'SetBoneTransform', 'AddMovementInput', 'Teleport'):
        assert forbidden not in camera


def test_measured_eye_offset_is_bound_to_the_original_owner_only():
    m = play.methods()
    assert f'Mesh->GetPathName()==TEXT("{play.OWNER_MESH_OBJECT_PATH}")?FVector({",".join(repr(v) for v in play.EYE_OFFSET_HEAD_CM)}):FVector::ZeroVector' in m
    # ~18 cm from the joint: what the old Head-joint camera was off by (below and behind the eyes).
    assert 18.0 < math.hypot(*play.EYE_OFFSET_HEAD_CM) < 19.0


def compiler():
    found = shutil.which('g++') or shutil.which('clang++')
    if not found:
        pytest.skip('C++ compiler unavailable')
    return found


def test_eye_easing_is_frame_rate_independent_monotonic_and_safe():
    source = '#include <cstdio>\n#include <cmath>\n' + play.EYE_ALPHA_CPP + r'''
int main(){
 const int Fps[]={30,60,144,240};
 for(int F:Fps){double Dt=1.0/F,Z=165,Target=105,T=0,First=-1;bool Monotonic=true;double Prev=Z;
  while(std::fabs(Z-Target)>.05*60){Z+=(Target-Z)*Sub01ControllerPlayEyeAlpha(Dt);T+=Dt;if(First<0)First=165-Z;if(Z>Prev||Z<Target)Monotonic=false;Prev=Z;}
  std::printf("%d %.4f %.4f %d\n",F,T,First,Monotonic?1:0);}
 std::printf("guards %.6f %.6f %.6f %.6f\n",Sub01ControllerPlayEyeAlpha(0),Sub01ControllerPlayEyeAlpha(-1),Sub01ControllerPlayEyeAlpha(NAN),Sub01ControllerPlayEyeAlpha(5));
}
'''
    with tempfile.TemporaryDirectory() as tmp:
        cpp, exe = Path(tmp) / 'a.cpp', Path(tmp) / 'a'
        cpp.write_text(source)
        built = subprocess.run([compiler(), '-std=c++17', '-Wall', '-Werror', str(cpp), '-o', str(exe)], capture_output=True, text=True)
        assert built.returncode == 0, built.stderr[-2000:]
        rows = subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout.split('\n')
    settle = {}
    for row in rows[:4]:
        fps, seconds, first, monotonic = row.split()
        settle[int(fps)] = float(seconds)
        assert monotonic == '1'
        # The old adapter moved the full 60 cm in one frame; the eased view moves at most 29% of it in a 30 fps frame.
        assert float(first) <= .29 * 60
    # 95% settle ~0.30 s at every frame rate (within one 30 fps frame).
    assert all(abs(s - .30) <= 1 / 30 for s in settle.values()), settle
    guards = [float(v) for v in rows[4].split()[1:]]
    assert guards[:3] == [0.0, 0.0, 0.0] and abs(guards[3] - (1 - math.exp(-1.0))) < 1e-6


def test_staged_install_defines_the_camera_update_once():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        (project / 'Config').mkdir()
        (project / 'Sub01HomeLab.uproject').write_text('{}')
        stage(project)
        module = project / 'Source/Sub01HomeLab'
        play.install_module(module)
        cpp, header = (module / 'Sub01HomeLab.cpp').read_text(), (module / 'Sub01HomeLab.h').read_text()
    assert cpp.count('void ASub01HomeCharacter::UpdateControllerPlayCamera(float Dt){') == 1
    assert cpp.count('static double Sub01ControllerPlayEyeAlpha(double Dt)') == 1
    assert header.count('void UpdateControllerPlayCamera(float Dt);') == 1 and 'bool ControllerPlayCameraEasing=false;' in header
