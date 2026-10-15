import json
import re
import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import stage_unreal_home_runtime as stage
import unreal_fp_keyboard_visual_review as review


def test_staged_warm_review_retains_physical_pawn_camera_and_normal_owner(tmp_path):
    (tmp_path/'Config').mkdir();(tmp_path/'Sub01HomeLab.uproject').write_text('{}')
    stage.stage(tmp_path)
    cpp=(tmp_path/'Source/Sub01HomeLab/Sub01HomeLab.cpp').read_text()
    header=(tmp_path/'Source/Sub01HomeLab/Sub01HomeLab.h').read_text()
    assert header.count('UFUNCTION(Exec) void ReviewFPSKeyboard(bool Play);')==1
    switch=cpp.split('bool ASub01HomeCharacter::SwitchNativeWalkView',1)[1].split('void ASub01HomeCharacter::UpdatePrivateNativeControl',1)[0]
    assert switch.index('FPSKeyboardVisualReview=false')<switch.index('SetHandsPosture(TEXT("Walk"))')
    assert 'FPSKeyboardReviewArms->SetSkeletalMeshAsset(nullptr)'in switch
    assert 'FirstPersonBody->SetVisibility(FPSKeyboardOwnerVisible)'in switch
    for forbidden in ('SetActorLocation','SetActorTransform','ViewCamera->Set','FirstPersonBody->SetSkeletalMesh','FirstPersonBody->SetWorld','NativeSeatVerified=','ValidatedHandsPostures.Add','SetOperatorFocus(true)'):
        assert forbidden not in review.METHODS
    assert 'FPSKeyboardReviewArms->SetAbsolute(true,true,true)'in review.METHODS
    assert 'NativePrivacyLast||Now-NativePrivacyPublishedAt>.5'in review.METHODS
    assert 'same exact unique source-pinned asset namespace required'in review.METHODS
    with pytest.raises(ValueError):review.install(header,cpp)


def test_declared_visual_placement_matches_actual_source_packet_not_camera():
    root=Path(__file__).resolve().parents[1]
    packet=json.loads((root/'docs/proposed/upright-footrest-source/fp-keyboard-private-review-packet.json').read_text())
    match=re.search(r'SetWorldTransform\(FTransform\(FRotator\(0,([\d.]+),0\),FVector\(([^)]+)\)',review.METHODS)
    assert float(match[1])==packet['source_world_placement']['body_component_yaw_deg']
    assert [float(x)for x in match[2].split(',')]==packet['source_world_placement']['body_component_translation_cm']
    for key in ('fbx_sha256','arms_mesh_glb_sha256','derived_clip_glb_sha256'):
        assert packet[key]in review.METHODS
    assert all(not packet[k]for k in ('source_ready','native_ready','activity_ready','visual_acceptance'))
    assert 'source camera NOT applied'in review.METHODS
