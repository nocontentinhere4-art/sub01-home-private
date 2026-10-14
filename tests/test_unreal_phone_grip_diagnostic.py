from tools import unreal_phone_grip_diagnostic as phone

def test_install_is_explicit_diagnostic_only_and_preserves_five_parts():
 h='class World{GENERATED_BODY()};class Character{GENERATED_BODY()\n void ConfigureActualPC();};'
 c='void Begin(){ ConfigureActualPC();}\nvoid Tick(){ Super::Tick(DeltaSeconds);}'
 header,cpp=phone.install(h,c)
 assert header.index('PhoneGripReview')>header.index('class Character')
 assert cpp.count(' ConfigurePrivatePhoneGripReview();')==1
 assert cpp.count(' UpdatePrivatePhoneGripReview();')==1
 assert 'PrivateViewMode=EPrivateViewMode::Diagnostic;' in cpp
 assert 'Sub01PhoneGripDiagnostic' in cpp and 'Role!=TEXT("Phone")' in cpp
 assert 'Sub01PhoneMountCm=' in cpp and 'Sub01PhoneMountEuler=' in cpp
 assert 'PlayAnimation(Clip,false)' in cpp and 'SetPosition' in cpp
 assert len(phone.PARTS)==5 and phone.PARTS[0][1]==(3.75,7.5,.75)
 # No finger/bone pose replacement, altered readiness, added static phone image, or duplicate prop.
 assert 'SetBone' not in cpp and 'NativeSeatVerified=' not in cpp
 assert 'NewObject<UStaticMeshComponent>' not in cpp and 'SetMaterial' not in cpp
 assert 'PhoneGripOriginalTransforms[I]*FromOriginal*Rigid' in cpp


def test_rejects_ambiguous_header_and_setup_hooks():
 import pytest
 with pytest.raises(ValueError):phone.install(' void ConfigureActualPC();'*2,' ConfigureActualPC(); Super::Tick(DeltaSeconds);')
