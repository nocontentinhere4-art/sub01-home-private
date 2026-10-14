"""Opt-in bounded RightHand local post-rotation for the private phone grip review (never acceptance).

`tools/fit_phone_grip.py --wrist-correction` may report one constant correction C: the captured
RightHand local rotation becomes ``captured * C`` on every frame. Finger local rotations, bone
lengths, translations and every other bone stay exactly as captured. The phone mount is expressed
in the corrected RightHand frame, so the existing rigid five-part assembly code is unchanged.

Native path: the review runs the captured Phone clip through ``USub01HomeHandsInstance`` (the
same proxy whose ``Evaluate`` already replaces six arm locals for the typing contact profile),
frozen at the review time, and multiplies only the RightHand local rotation. Command line:

    -Sub01PhoneGripDiagnostic -Sub01HandsDiagnostic=Phone -Sub01PhoneWristCorrection="X=.. Y=.. Z=.. W=.."

Refused unless the quaternion is finite, unit within 1e-3 and at most ``MAX_DEGREES`` from identity.
"""
MAX_DEGREES = 35.0

HANDS_HEADER = r'''
 UPROPERTY(Transient) TObjectPtr<UAnimSequence> PhoneCorrectionSequence;
 UPROPERTY(Transient) FName PhoneCorrectionBone;
 UPROPERTY(Transient) FQuat PhoneCorrectionDelta=FQuat::Identity;
 UPROPERTY(Transient) float PhoneCorrectionTime=-1;
 UPROPERTY(Transient) float PhoneCorrectionEvaluatedTime=-1;
'''
PROXY_FIELDS = r'''
 TObjectPtr<UAnimSequence> PhoneCorrectionSequence;FName PhoneCorrectionBone;FQuat PhoneCorrectionDelta=FQuat::Identity;float PhoneCorrectionTime=-1,PhoneCorrectionEvaluated=-1;
'''
PREUPDATE = r'''
  PhoneCorrectionSequence=Hands->PhoneCorrectionSequence;PhoneCorrectionBone=Hands->PhoneCorrectionBone;PhoneCorrectionDelta=Hands->PhoneCorrectionDelta;PhoneCorrectionTime=Hands->PhoneCorrectionTime;Hands->PhoneCorrectionEvaluatedTime=PhoneCorrectionEvaluated;
'''
SEQUENCE_START = r'''
   if(PhoneCorrectionSequence&&Current.GetSequence()==PhoneCorrectionSequence&&PhoneCorrectionTime>=0){Current.SetLoopAnimation(false);Current.SetAccumulatedTime(PhoneCorrectionTime);}
'''
RATE = r'''
  if(PhoneCorrectionSequence&&Current.GetSequence()==PhoneCorrectionSequence&&PhoneCorrectionTime>=0)Current.SetPlayRate(0);
'''
EVALUATE = r'''
  if(PhoneCorrectionSequence&&Current.GetSequence()==PhoneCorrectionSequence&&!PhoneCorrectionBone.IsNone()){
   // Only the RightHand local rotation; captured fingers, lengths and translations untouched.
   const auto& Bones=Output.Pose.GetBoneContainer();const int32 MeshIndex=Bones.GetReferenceSkeleton().FindBoneIndex(PhoneCorrectionBone);
   const auto Compact=MeshIndex<0?FCompactPoseBoneIndex(INDEX_NONE):Bones.MakeCompactPoseIndex(FMeshPoseBoneIndex(MeshIndex));
   if(Compact.GetInt()>=0){FTransform& Local=Output.Pose[Compact];Local.SetRotation((Local.GetRotation()*PhoneCorrectionDelta).GetNormalized());PhoneCorrectionEvaluated=Current.GetAccumulatedTime();}
  }
'''
CHARACTER_FIELDS = r'''
 bool PhoneWristCorrected=false;
 bool PhoneGripPoseFrozen(float Time) const;
'''
CONFIGURE = r'''
 // Optional bounded RightHand correction from fit_phone_grip.py; refused outside the exact review.
 FString CorrectionText;
 if(FParse::Value(FCommandLine::Get(),TEXT("Sub01PhoneWristCorrection="),CorrectionText)){
  FQuat Delta;const bool Parsed=Delta.InitFromString(CorrectionText);
  const float Degrees=Parsed?FMath::RadiansToDegrees(Delta.GetNormalized().GetAngle()):999.f;
  if(!Parsed||Delta.ContainsNaN()||FMath::Abs(Delta.Size()-1.f)>1e-3f||Degrees>@@MAX_DEGREES@@f){UE_LOG(LogTemp,Error,TEXT("SUB01_PHONE_WRIST_CORRECTION_REFUSED parsed=%d degrees=%.3f"),Parsed?1:0,Degrees);return;}
  FirstPersonBody->SetAnimationMode(EAnimationMode::AnimationBlueprint);FirstPersonBody->SetAnimInstanceClass(USub01HomeHandsInstance::StaticClass());
  auto* Hands=Cast<USub01HomeHandsInstance>(FirstPersonBody->GetAnimInstance());
  if(!Hands){UE_LOG(LogTemp,Error,TEXT("SUB01_PHONE_WRIST_CORRECTION_REFUSED hands instance unavailable"));return;}
  Hands->PhoneCorrectionSequence=Clip;Hands->PhoneCorrectionBone=PhoneGripWrist;Hands->PhoneCorrectionDelta=Delta.GetNormalized();Hands->PhoneCorrectionTime=PhoneGripPoseTime;
  Hands->TargetSequence=Clip;Hands->TargetRate=0;PhoneWristCorrected=true;
  FirstPersonBody->TickAnimation(0.f,false);FirstPersonBody->RefreshBoneTransforms();FirstPersonBody->UpdateComponentToWorld();
  UE_LOG(LogTemp,Warning,TEXT("SUB01_UNACCEPTED_PHONE_WRIST_CORRECTION bone=%s delta=%s degrees=%.3f time=%.3f; fingers/lengths/other bones unchanged; NO activity acceptance"),*PhoneGripWrist.ToString(),*Delta.ToString(),Degrees,PhoneGripPoseTime);
 }
'''
FROZEN = r'''
bool ASub01HomeCharacter::PhoneGripPoseFrozen(float Time) const{
 if(!FirstPersonBody)return false;
 if(PhoneWristCorrected){const auto* Hands=Cast<USub01HomeHandsInstance>(FirstPersonBody->GetAnimInstance());
  return Hands&&Hands->PhoneCorrectionSequence==PhoneGripCapturedClip.Get()&&FMath::Abs(Hands->PhoneCorrectionEvaluatedTime-Time)<=.01f;}
 const auto* A=FirstPersonBody->GetSingleNodeInstance();
 return A&&A->GetCurrentAsset()==PhoneGripCapturedClip.Get()&&FMath::Abs(A->GetCurrentTime()-Time)<=.01f;
}
'''
WALK_CLEANUP = r'''
 if(PhoneWristCorrected&&FirstPersonBody){if(auto* Hands=Cast<USub01HomeHandsInstance>(FirstPersonBody->GetAnimInstance())){Hands->PhoneCorrectionSequence=nullptr;Hands->PhoneCorrectionBone=NAME_None;Hands->PhoneCorrectionDelta=FQuat::Identity;Hands->PhoneCorrectionTime=-1;}}
 PhoneWristCorrected=false;
'''
CONFIGURE_ANCHOR = ' PhoneGripCapturedClip=Clip;PhoneGripPoseTime=FMath::Clamp(Time,0.f,Clip->GetPlayLength());\n FirstPersonBody->PlayAnimation(Clip,false);FirstPersonBody->SetPosition(FMath::Clamp(Time,0.f,Clip->GetPlayLength()),false);FirstPersonBody->SetPlayRate(0);\n'
EYE_GUARD = '  auto* A=FirstPersonBody->GetSingleNodeInstance();\n  if(!A||A->GetCurrentAsset()!=PhoneGripCapturedClip.Get()||FMath::Abs(A->GetCurrentTime()-4.f)>.01f)return;\n'
CANDIDATE_GUARD = ' auto* Animation=FirstPersonBody->GetSingleNodeInstance();\n if(!Animation||Animation->GetCurrentAsset()!=PhoneGripCapturedClip.Get()||FMath::Abs(Animation->GetCurrentTime()-PhoneGripPoseTime)>.01f)return;\n'


def _once(text, anchor, replacement, what):
    if text.count(anchor) != 1:
        raise ValueError(f'Unique anchor required: {what}')
    return text.replace(anchor, replacement, 1)


def install_hands(header, cpp):
    """Add the correction to USub01HomeHandsInstance (after any contact-profile install)."""
    header = _once(header, ' protected:', HANDS_HEADER+'\n protected:', 'hands header protected section')
    cpp = _once(cpp, ' float Progress=1;', PROXY_FIELDS+' float Progress=1;', 'proxy fields')
    cpp = _once(cpp, '  if(Current.GetSequence()!=Hands->TargetSequence)', PREUPDATE+'  if(Current.GetSequence()!=Hands->TargetSequence)', 'proxy pre-update')
    cpp = _once(cpp, '   Progress=Hands->PreviousSequence?0:1;', SEQUENCE_START+'   Progress=Hands->PreviousSequence?0:1;', 'sequence start')
    cpp = _once(cpp, '  Current.SetPlayRate(Hands->TargetRate);\n', '  Current.SetPlayRate(Hands->TargetRate);\n'+RATE, 'play rate')
    cpp = _once(cpp, '  Blend.Evaluate_AnyThread(Output);\n', '  Blend.Evaluate_AnyThread(Output);\n'+EVALUATE, 'evaluate (expanded form)')
    return header, cpp


def install_character(header, methods, walk_cleanup):
    """Extend the phone grip diagnostic FIELDS/METHODS/WALK_CLEANUP before its own install()."""
    header = _once(header, ' void UpdatePrivatePhoneGripReview();', ' void UpdatePrivatePhoneGripReview();'+CHARACTER_FIELDS, 'phone review header')
    methods = _once(methods, CONFIGURE_ANCHOR, CONFIGURE_ANCHOR+CONFIGURE.replace('@@MAX_DEGREES@@', repr(MAX_DEGREES)), 'captured clip freeze')
    methods = _once(methods, EYE_GUARD, '  if(!PhoneGripPoseFrozen(4.f))return;\n', 'eye camera freeze guard')
    methods = _once(methods, CANDIDATE_GUARD, ' if(!PhoneGripPoseFrozen(PhoneGripPoseTime))return;\n', 'candidate freeze guard')
    walk_cleanup = _once(walk_cleanup, ' PhoneGripReview=false;PhoneGripMounted=false;', WALK_CLEANUP+' PhoneGripReview=false;PhoneGripMounted=false;', 'walk cleanup')
    return header, methods+FROZEN, walk_cleanup


def apply_to_modules(hands_module, phone_module):
    """Staging hook: call once, after the contact-profile install, before stage/diagnostic install."""
    hands_module.HEADER, hands_module.CPP = install_hands(hands_module.HEADER, hands_module.CPP)
    phone_module.FIELDS, phone_module.METHODS, phone_module.WALK_CLEANUP = install_character(
        phone_module.FIELDS, phone_module.METHODS, phone_module.WALK_CLEANUP)
