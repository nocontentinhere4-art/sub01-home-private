"""Review is explicit/manual and returning Walk restores the real phone assembly."""
import tempfile
from pathlib import Path
import pytest
from tools import stage_unreal_home_runtime as stage
from tools import unreal_derived_phone_visual_review as review


def test_real_staged_runtime_contains_review_and_restoration_in_order():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp)/"Sub01HomeLab.uproject").write_text("{}")
        (Path(tmp)/"Config").mkdir()
        stage.stage(Path(tmp))
        cpp=(Path(tmp)/'Source/Sub01HomeLab/Sub01HomeLab.cpp').read_text()
        header=(Path(tmp)/'Source/Sub01HomeLab/Sub01HomeLab.h').read_text()
    assert header.count('UFUNCTION(Exec) void ReviewDerivedPhone(bool Play);')==1
    walk=cpp[cpp.index('bool ASub01HomeCharacter::SwitchNativeWalkView'):cpp.index('void ASub01HomeCharacter::UpdatePrivateNativeControl')]
    assert walk.index('ApplyPrivatePhoneAssemblyTransforms(PhoneGripOriginalTransforms)') < walk.index('SetMobility(DerivedPhoneOriginalMobility[I])')
    assert walk.index('HandsDiagnostic=false') < walk.index('HandsDiagnosticSeat=false')
    method=review.METHODS
    assert method.index('if(Count!=1){') < method.index('return;}Found.Add(Match)') < method.index('C->SetMobility(EComponentMobility::Movable)')
    assert method.index('Owner->GetSkeleton()->GetPathName()!=Skeleton') < method.index('PlayAnimation(Clip,Play)')
    assert 'NativeSeatVerified=true' not in method
    assert 'SaveStringToFile' not in method and 'SetActorLocation' not in method


def test_reinstall_or_missing_original_phone_hooks_refuses():
    for h,c in [('', ''),(review.FIELDS,review.METHODS)]:
        with pytest.raises(ValueError):review.install(h,c)
