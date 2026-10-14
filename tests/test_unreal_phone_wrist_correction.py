import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import unreal_phone_wrist_correction as corr  # noqa: E402


def fresh():
    import unreal_home_hands_runtime as hands
    import unreal_phone_grip_diagnostic as phone
    return importlib.reload(hands), importlib.reload(phone)


def test_installs_on_actual_hands_proxy_and_phone_review():
    hands, phone = fresh()
    original_methods = phone.METHODS
    corr.apply_to_modules(hands, phone)
    assert hands.CPP.count('PhoneCorrectionDelta')>=3 and 'Local.GetRotation()*PhoneCorrectionDelta' in hands.CPP
    # Correction runs after the existing blend/contact-profile evaluation, on one named bone only.
    ev = hands.CPP.index('Blend.Evaluate_AnyThread(Output);')
    assert hands.CPP.index('PhoneCorrectionBone.IsNone()') > ev
    assert 'SetBone' not in corr.EVALUATE and 'Finger' not in corr.EVALUATE
    # Both single-node freeze guards now route through one helper that also accepts the corrected path.
    assert phone.METHODS.count('PhoneGripPoseFrozen(') == 3
    assert 'GetSingleNodeInstance();\n  if(!A' not in phone.METHODS
    assert 'Sub01PhoneWristCorrection=' in phone.METHODS and 'SUB01_PHONE_WRIST_CORRECTION_REFUSED' in phone.METHODS
    assert 'Degrees>35.0f' in phone.METHODS and 'FMath::Abs(Delta.Size()-1.f)>1e-3f' in phone.METHODS
    assert 'NO activity acceptance' in phone.METHODS
    assert 'Hands->PhoneCorrectionSequence=nullptr' in phone.WALK_CLEANUP
    # Original diagnostic gates kept.
    for gate in ('SUB01_PHONE_GRIP_REFUSED requires original captured Phone diagnostic', 'PrivateViewMode=EPrivateViewMode::Diagnostic;',
                 'SUB01_PHONE_EYE_CAMERA_REFUSED exact original owner/Phone4s witness required'):
        assert gate in original_methods and gate in phone.METHODS
    fresh()


def test_character_install_still_composes_with_diagnostic_install():
    hands, phone = fresh()
    corr.apply_to_modules(hands, phone)
    from unreal_native_control import METHODS as control
    h = 'class Character{GENERATED_BODY()\n void ConfigureActualPC();};'
    c = 'void Begin(){ ConfigureActualPC();}\nvoid Tick(){ Super::Tick(DeltaSeconds);}'+control
    header, cpp = phone.install(h, c)
    assert 'bool PhoneGripPoseFrozen(float Time) const;' in header
    assert 'bool ASub01HomeCharacter::PhoneGripPoseFrozen(float Time) const{' in cpp
    assert cpp.index('PhoneWristCorrected=false;') < cpp.index('HandsDiagnosticSeat=false;HandsClips.Add(TEXT("Walk"),Walk);')
    fresh()


def test_ambiguous_anchors_refused():
    with pytest.raises(ValueError):
        corr.install_hands(' protected:'*2, '')
