import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import unreal_walking_collision_envelope as envelope
import stage_unreal_home_runtime as stage


def test_measured_eye_capsule_and_near_plane_math_executes(tmp_path):
    compiler=shutil.which('clang++')or shutil.which('g++')
    if not compiler:pytest.skip('No C++ compiler')
    cpp=tmp_path/'policy.cpp'
    (tmp_path/'Policy.h').write_text(envelope.POLICY)
    cpp.write_text('''#include "Policy.h"
int main(){using Sub01WalkingEnvelope::ContainsEye;
const double x=22.208150954150312,y=3.5805613130220593,z=64.61018215994386;
if(!ContainsEye(x,y,z,25,91,1))return 1;
if(ContainsEye(x,y,z,16,91,1))return 2;
if(ContainsEye(x,y,z,25,91,10))return 3;
if(ContainsEye(x,y,90,25,91,1))return 4;
if(ContainsEye(NAN,y,z,25,91,1)||ContainsEye(x,y,z,25,91,NAN))return 5;
if(ContainsEye(x,y,z,25,20,1)||ContainsEye(x,y,z,25,91,0))return 6;
if(ContainsEye(x,y,z,25,91,1,1))return 7;
return 0;}
''')
    result=subprocess.run([compiler,'-std=c++17','-Wall','-Werror',str(cpp),'-o',str(tmp_path/'policy')],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert subprocess.run([str(tmp_path/'policy')]).returncode==0


def test_installed_review_checks_real_overlap_without_enabling_it_at_startup(tmp_path):
    (tmp_path/'Config').mkdir();(tmp_path/'Sub01HomeLab.uproject').write_text('{}')
    stage.stage(tmp_path)
    cpp=(tmp_path/'Source/Sub01HomeLab/Sub01HomeLab.cpp').read_text()
    header=(tmp_path/'Source/Sub01HomeLab/Sub01HomeLab.h').read_text()
    assert header.count('UFUNCTION(Exec) void ReviewWalkingEnvelope();')==1
    assert 'Sub01WalkingEnvelopePolicy.h' in cpp
    assert 'ReviewWalkingEnvelope();' not in cpp
    body=cpp.split('void ASub01HomeCharacter::ReviewWalkingEnvelope(){',1)[1].split('\n}',1)[0]
    assert body.index('OverlapBlockingTestByChannel')<body.index('C->SetCapsuleSize(25.f,91.f,true)')<body.index('SetNearClipPlaneGlobals(1.f)')
    assert 'SetActorLocation' not in body and 'SetCollisionEnabled' not in body
    assert 'native_ready' not in body and 'NativeSeatVerified=true' not in body
