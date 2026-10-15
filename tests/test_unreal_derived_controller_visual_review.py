import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import stage_unreal_home_runtime as stage
import unreal_derived_controller_visual_review as review
from unreal_controller_play_runtime import ue_grip


def test_staged_review_is_reversible_and_does_not_enable_play(tmp_path):
    (tmp_path/'Config').mkdir()
    (tmp_path/'Sub01HomeLab.uproject').write_text('{}')
    stage.stage(tmp_path)
    cpp=(tmp_path/'Source/Sub01HomeLab/Sub01HomeLab.cpp').read_text()
    header=(tmp_path/'Source/Sub01HomeLab/Sub01HomeLab.h').read_text()
    assert header.count('UFUNCTION(Exec) void ReviewDerivedController(bool Play);')==1
    switch=cpp.split('bool ASub01HomeCharacter::SwitchNativeWalkView',1)[1].split('void ASub01HomeCharacter::UpdatePrivateNativeControl',1)[0]
    assert switch.index('DerivedControllerVisualReview=false')<switch.index('ControllerGripReview=false')<switch.index('SetHandsPosture(TEXT("Walk"))')
    assert 'ControllerPlayProp->SetVisibility(false)' in switch
    # Existing diagnostic teardown restores the real animation proxy and eye;
    # the new review never certifies that a sofa or controller input worked.
    assert 'SetAnimInstanceClass(USub01HomeHandsInstance::StaticClass())' in switch
    for forbidden in ('SetActorLocation','SetBone','ControllerPlayEvidence=','ControllerPlayRuntimeProof=','NativeSeatVerified=','MinecraftFocused=','ValidatedHandsPostures.Add'):
        assert forbidden not in review.METHODS
    with pytest.raises(ValueError):review.install(header,cpp)


def test_mounted_rigid_transform_matches_actual_derived_packet():
    root=Path(__file__).resolve().parents[1]
    packet=json.loads((root/'docs/proposed/controller-play/SUB01_GamingGrip_derived.report.json').read_text())
    expected_t,expected_q=ue_grip(packet['fixed_offset']['controller_in_right_hand_gltf'])
    t=re.search(r'Q.RotateVector\(FVector\(([^)]+)\)\)',review.METHODS)
    q=re.search(r'const FQuat R=Q\*FQuat\(([^)]+)\)',review.METHODS)
    assert [float(x)for x in t[1].split(',')]==pytest.approx(expected_t,abs=1e-12)
    assert [float(x)for x in q[1].split(',')]==pytest.approx(expected_q,abs=1e-12)
    assert packet['output_glb_sha256'] in review.METHODS
