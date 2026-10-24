"""Pin fix ON TOP of v2 + face (install.py, then install_face_camera.py): per-clip drift guard instead of an R9 pin.

    python tools/native_streamer_visual_v2/install_pin_fix.py --source <dir> [--dry-run]

Field result (build v11): the pelvis-vs-R9 audit put SupportedWebsite/SupportedDeskTyping at 116 cm / 25.6 deg from R9
in component space, yet the Website loop sat correctly in the chair without any pin (authored body transform + the
clip's own root). R9 is therefore not a reference for these clips. This patch:
1. removes the audit-driven fallback: the R9 audit is a log line only (`SUB01_STREAMER_VISUAL_CLIP_AUDIT ... log only`);
2. turns the pin into a per-clip drift guard: reference = the clip's own chain (pelvis and the bones above it) at its
   reference time (0 s; the frozen R9 at its freeze time, so the statue is unchanged); bones above the pelvis take that
   reference exactly and the pelvis stays within 8 cm / 25 deg of the clip's own reference pelvis; during a crossfade the
   two players' references blend with the crossfade weight; never R9 for another clip;
3. maps `mouse` to the sitting loop outright (AuthoredReach excluded, logged once);
4. leaves the face camera, the spectator/monitor cameras and the rest of v2 untouched.
Only Sub01HomeLab.cpp and Sub01HomeHands.cpp change (two whole-block replacements and one call site, each anchor found
exactly once). Refused when the face patch is absent or `// SUB01_STREAMER_VISUAL_V2_PINFIX` is already present.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location('sub01_streamer_visual_v2_face', Path(__file__).resolve().parent / 'install_face_camera.py')
face = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(face)
v2, Refused = face.v2, face.Refused

MARKER = '// SUB01_STREAMER_VISUAL_V2_PINFIX'
FILES = dict(v2.FILES)
PATCHED = ('cpp', 'hands_cpp')

OLD_PROXY = face.PROXY_MEMBERS
_start = face.CPP_METHODS.index('int32 ASub01HomeCharacter::StreamerVisualDeskSlot(')
OLD_DESK_SLOT = face.CPP_METHODS[_start:face.CPP_METHODS.index(face.MARKER + ' END')]

NEW_DESK_SLOT = r'''int32 ASub01HomeCharacter::StreamerVisualDeskSlot(USub01HomeHandsInstance* Anim,int32 Slot){
 // SUB01_STREAMER_VISUAL_V2_PINFIX (tools/native_streamer_visual_v2/install_pin_fix.py): the proxy's per-clip drift guard keeps
 // every clip on its own authored placement, so the pelvis-vs-R9 audit is a log line only (the Desk7 loops sit ~116 cm from
 // R9 in component space and land in the chair). "mouse" plays the sitting loop: AuthoredReach is excluded. A missing clip
 // keeps the v2 rule (frozen R9).
 static bool MouseLogged=false;
 if(Anim&&Anim->StreamerVisualAuditClips.Num()!=StreamerVisualV2Clips.Num())Anim->StreamerVisualAuditClips=StreamerVisualV2Clips;
 if(Anim&&Anim->StreamerVisualAuditDone&&!StreamerVisualAuditLogged){
  StreamerVisualAuditLogged=true;const FByteProperty* RootModeProperty=FindFProperty<FByteProperty>(UAnimInstance::StaticClass(),TEXT("RootMotionMode"));const int32 RootMode=RootModeProperty?int32(RootModeProperty->GetPropertyValue_InContainer(Anim)):-1;
  for(int32 S=0;S<StreamerVisualV2Clips.Num();++S){const UAnimSequence* C=StreamerVisualV2Clips[S].Get();
   UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_CLIP_AUDIT slot=%d clip=%s pelvisOffsetFromR9Cm=%.1f pelvisAngleFromR9Deg=%.1f enableRootMotion=%d forceRootLock=%d rootLock=%d instanceRootMotionMode=%d played=%d (log only; per-clip drift guard)"),
    S,C?*C->GetPathName():TEXT("missing"),Anim->StreamerVisualClipOffsetCm.IsValidIndex(S)?Anim->StreamerVisualClipOffsetCm[S]:-1.f,Anim->StreamerVisualClipAngleDeg.IsValidIndex(S)?Anim->StreamerVisualClipAngleDeg[S]:-1.f,
    C&&C->bEnableRootMotion?1:0,C&&C->bForceRootLock?1:0,C?int32(C->RootMotionRootLock.GetValue()):-1,RootMode,S!=2?1:0);
  }
 }
 if(Slot==2){if(!MouseLogged){MouseLogged=true;UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_MOUSE_AS_SITTING_LOOP AuthoredReach excluded; state mouse plays the sitting loop"));}return 0;}
 return Slot;
}
'''

NEW_PROXY = r''' // SUB01_STREAMER_VISUAL_V2_FACE BEGIN (tools/native_streamer_visual_v2/install_face_camera.py): drift guard + clip audit.
 // SUB01_STREAMER_VISUAL_V2_PINFIX (tools/native_streamer_visual_v2/install_pin_fix.py): these players never extract root motion,
 // so a clip's root track is applied to the pose. Each clip keeps its OWN authored placement (the Desk7 loops sit ~116 cm from R9
 // in component space and land in the chair): bones above the pelvis take the clip's locals at its reference time (0 s; the
 // frozen R9 at its freeze time) and the pelvis stays within @@PIN_CM@@ cm / @@PIN_DEG@@ deg of the clip's own reference pelvis; in a
 // crossfade the two references blend with the players' weight. R9 is only the audit yardstick (log line).
 // Raw sequence pointers here are kept alive by UPROPERTYs on the instance; reference keys are compared only.
 UAnimSequenceBase* StreamerV2Reference=nullptr;float StreamerV2ReferenceSeconds=.7f;TArray<UAnimSequenceBase*> StreamerV2AuditClips;
 bool StreamerV2PinReady=false,StreamerV2PinTried=false,StreamerV2Audited=false;int32 StreamerV2PinCount=-1;float StreamerV2LastPinCm=-1;
 TArray<int32> StreamerV2PinChain;TArray<FTransform> StreamerV2PinLocals;FTransform StreamerV2PinPelvis=FTransform::Identity;
 TArray<float> StreamerV2AuditOffsetCm,StreamerV2AuditAngleDeg;
 struct FStreamerV2ClipRef{const UAnimSequenceBase* Key=nullptr;TArray<FTransform> Locals;};FStreamerV2ClipRef StreamerV2ClipRefs[6];int32 StreamerV2ClipRefNext=0;
 static constexpr double StreamerV2PinRadiusCm=@@PIN_CM@@,StreamerV2PinMaxRadians=@@PIN_RAD@@;
 bool StreamerV2Pelvis(const FCompactPose& Source,FTransform& Pelvis) const { // component space: pelvis local * parents (chain pelvis -> root)
  const auto& Bones=Source.GetBoneContainer();Pelvis=FTransform::Identity;
  for(const int32 B:StreamerV2PinChain){const auto Compact=Bones.MakeCompactPoseIndex(FMeshPoseBoneIndex(B));if(Compact.GetInt()<0)return false;Pelvis=Pelvis*Source[Compact];}
  return !Pelvis.ContainsNaN();
 }
 bool ResolveStreamerV2Pin(FPoseContext& Output){ // pelvis chain once per skeleton; R9's pelvis only for the audit log
  const auto& Ref=Output.Pose.GetBoneContainer().GetReferenceSkeleton();
  StreamerV2PinTried=true;StreamerV2PinChain.Reset();StreamerV2PinLocals.Reset();
  int32 PelvisBone=Ref.FindBoneIndex(FName(TEXT("Hips")));for(int32 B=0;PelvisBone==INDEX_NONE&&B<Ref.GetNum();++B)if(Ref.GetBoneName(B).ToString().EndsWith(TEXT("Hips")))PelvisBone=B;if(PelvisBone==INDEX_NONE)PelvisBone=0;
  for(int32 B=PelvisBone;B!=INDEX_NONE&&StreamerV2PinChain.Num()<=8;B=Ref.GetParentIndex(B))StreamerV2PinChain.Add(B);
  if(Ref.GetNum()<1||StreamerV2PinChain.Num()>8)return false;
  StreamerV2Probe.SetSequence(StreamerV2Reference);StreamerV2Probe.SetLoopAnimation(false);StreamerV2Probe.SetPlayRate(0);StreamerV2Probe.SetAccumulatedTime(StreamerV2ReferenceSeconds);
  FPoseContext Probe(Output.AnimInstanceProxy);StreamerV2Probe.Evaluate_AnyThread(Probe);const auto& Bones=Probe.Pose.GetBoneContainer();
  for(const int32 B:StreamerV2PinChain){const auto Compact=Bones.MakeCompactPoseIndex(FMeshPoseBoneIndex(B));if(Compact.GetInt()<0){StreamerV2PinLocals.Reset();return false;}StreamerV2PinLocals.Add(Probe.Pose[Compact]);}
  if(!StreamerV2Pelvis(Probe.Pose,StreamerV2PinPelvis))return false;
  UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_DRIFT_GUARD pelvisBone=%d chain=%d perClipReference=0s (frozen R9 %.2fs) radiusCm=@@PIN_CM@@ maxDeg=@@PIN_DEG@@"),PelvisBone,StreamerV2PinChain.Num(),StreamerV2ReferenceSeconds);
  return true;
 }
 bool PrepareStreamerV2Pin(FPoseContext& Output){
  const auto& Ref=Output.Pose.GetBoneContainer().GetReferenceSkeleton();
  if(StreamerV2PinCount!=Ref.GetNum()){StreamerV2PinCount=Ref.GetNum();StreamerV2PinReady=StreamerV2PinTried=false;for(auto& Entry:StreamerV2ClipRefs){Entry.Key=nullptr;Entry.Locals.Reset();}}
  if(!StreamerV2PinReady&&!StreamerV2PinTried&&StreamerV2Reference)StreamerV2PinReady=ResolveStreamerV2Pin(Output);
  if(StreamerV2PinReady){CacheStreamerV2ClipRef(Output,Current.GetSequence());CacheStreamerV2ClipRef(Output,Previous.GetSequence());}
  return StreamerV2PinReady;
 }
 const FStreamerV2ClipRef* StreamerV2ClipRef(const UAnimSequenceBase* Seq) const {
  if(!Seq)return nullptr;for(const auto& Entry:StreamerV2ClipRefs)if(Entry.Key==Seq&&Entry.Locals.Num()==StreamerV2PinChain.Num())return &Entry;return nullptr;
 }
 void CacheStreamerV2ClipRef(FPoseContext& Output,UAnimSequenceBase* Seq){ // once per clip (a failed one stays unpinned, never retried)
  if(!Seq)return;for(const auto& Entry:StreamerV2ClipRefs)if(Entry.Key==Seq)return;
  auto& Entry=StreamerV2ClipRefs[StreamerV2ClipRefNext];StreamerV2ClipRefNext=(StreamerV2ClipRefNext+1)%6;Entry.Key=Seq;Entry.Locals.Reset();
  const float At=Seq==StreamerV2Reference?StreamerV2ReferenceSeconds:0.f;
  StreamerV2Probe.SetSequence(Seq);StreamerV2Probe.SetLoopAnimation(false);StreamerV2Probe.SetPlayRate(0);StreamerV2Probe.SetAccumulatedTime(At);
  FPoseContext Probe(Output.AnimInstanceProxy);StreamerV2Probe.Evaluate_AnyThread(Probe);const auto& Bones=Probe.Pose.GetBoneContainer();
  for(const int32 B:StreamerV2PinChain){const auto Compact=Bones.MakeCompactPoseIndex(FMeshPoseBoneIndex(B));if(Compact.GetInt()<0){Entry.Locals.Reset();return;}Entry.Locals.Add(Probe.Pose[Compact]);}
  FTransform Pelvis=FTransform::Identity;StreamerV2Pelvis(Probe.Pose,Pelvis);
  UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_DRIFT_REFERENCE at=%.2fs pelvis=%s"),At,*Pelvis.GetTranslation().ToString());
 }
 void AuditStreamerV2Clips(FPoseContext& Output){ // once, log only: each clip's pelvis vs R9 at 0, 1/4, 1/2, 3/4, 1 of its length
  StreamerV2Audited=true;StreamerV2AuditOffsetCm.Reset();StreamerV2AuditAngleDeg.Reset();
  for(UAnimSequenceBase* Clip:StreamerV2AuditClips){
   float MaxCm=-1,MaxDeg=-1;const float Length=Clip?float(Clip->GetPlayLength()):0.f;
   for(int32 K=0;Clip&&Length>0&&K<=4;++K){
    StreamerV2Probe.SetSequence(Clip);StreamerV2Probe.SetLoopAnimation(false);StreamerV2Probe.SetPlayRate(0);StreamerV2Probe.SetAccumulatedTime(Length*K/4);
    FPoseContext Probe(Output.AnimInstanceProxy);StreamerV2Probe.Evaluate_AnyThread(Probe);FTransform Pelvis=FTransform::Identity;
    if(!StreamerV2Pelvis(Probe.Pose,Pelvis)){MaxCm=MaxDeg=1e6f;break;}
    MaxCm=FMath::Max(MaxCm,float(FVector::Dist(Pelvis.GetTranslation(),StreamerV2PinPelvis.GetTranslation())));
    MaxDeg=FMath::Max(MaxDeg,float(FMath::RadiansToDegrees(StreamerV2PinPelvis.GetRotation().AngularDistance(Pelvis.GetRotation()))));
   }
   StreamerV2AuditOffsetCm.Add(MaxCm);StreamerV2AuditAngleDeg.Add(MaxDeg);
  }
 }
 void PinStreamerV2(FCompactPose& Composed,bool Record,const UAnimSequenceBase* Only=nullptr){ // Only: a single clip's pose (phase probe)
  if(Record)StreamerV2LastPinCm=-1;
  const int32 N=StreamerV2PinChain.Num();if(!StreamerV2PinReady||N<1||N>8)return;
  const FStreamerV2ClipRef* To=StreamerV2ClipRef(Only?Only:Current.GetSequence());if(!To)return;
  const FStreamerV2ClipRef* From=Only||Progress>=1?nullptr:StreamerV2ClipRef(Previous.GetSequence());
  FTransform Reference[8];FTransform ReferencePelvis=FTransform::Identity;
  for(int32 I=0;I<N;++I){Reference[I]=To->Locals[I];if(From)Reference[I].Blend(From->Locals[I],To->Locals[I],Progress);ReferencePelvis=ReferencePelvis*Reference[I];}
  if(Record){FTransform Pelvis=FTransform::Identity;if(StreamerV2Pelvis(Composed,Pelvis))StreamerV2LastPinCm=float(FVector::Dist(Pelvis.GetTranslation(),ReferencePelvis.GetTranslation()));}
  const auto& Bones=Composed.GetBoneContainer();
  for(int32 I=0;I<N;++I){const auto Compact=Bones.MakeCompactPoseIndex(FMeshPoseBoneIndex(StreamerV2PinChain[I]));if(Compact.GetInt()<0)continue;
   auto& T=Composed[Compact];
   if(I>0){T=Reference[I];continue;} // bones above the pelvis: the clip's own reference, so no root travel survives
   const FVector Delta=T.GetTranslation()-Reference[0].GetTranslation();const double Cm=Delta.Size();
   if(Cm>StreamerV2PinRadiusCm)T.SetTranslation(Reference[0].GetTranslation()+Delta*(StreamerV2PinRadiusCm/Cm));
   const double Angle=Reference[0].GetRotation().AngularDistance(T.GetRotation());
   if(Angle>StreamerV2PinMaxRadians)T.SetRotation(FQuat::Slerp(Reference[0].GetRotation(),T.GetRotation(),StreamerV2PinMaxRadians/Angle));
  }
 }
 // SUB01_STREAMER_VISUAL_V2_FACE END
'''
for _key, _value in {'@@PIN_CM@@': f'{face.PIN_RADIUS_CM:g}', '@@PIN_DEG@@': f'{face.PIN_MAX_DEG:g}',
                     '@@PIN_RAD@@': repr(face.PIN_MAX_DEG * 3.141592653589793 / 180)}.items():
    NEW_PROXY = NEW_PROXY.replace(_key, _value)

EDITS = [
    ('cpp', OLD_DESK_SLOT, NEW_DESK_SLOT),
    ('hands_cpp', OLD_PROXY, NEW_PROXY),
    ('hands_cpp', 'PinStreamerV2(Probe.Pose,false); // SUB01_STREAMER_VISUAL_V2_FACE: phases of the pinned clip\n',
     'PinStreamerV2(Probe.Pose,false,Seq); // SUB01_STREAMER_VISUAL_V2_FACE: phases of the pinned clip; SUB01_STREAMER_VISUAL_V2_PINFIX: its own reference\n'),
]


def plan(sources: dict) -> dict:
    """Pure transformation of the four LF texts; only 'cpp' and 'hands_cpp' change. Raises Refused, never partial."""
    problems = [f'{FILES[key]} already carries {MARKER} (pin fix already installed)' for key in PATCHED if MARKER in sources[key]]
    if problems:
        raise Refused('; '.join(problems))
    problems = [f'{FILES[key]} lacks the face patch ({face.MARKER}); run install.py and install_face_camera.py first'
                for key in FILES if face.MARKER + ' BEGIN' not in sources[key]]
    if problems:
        raise Refused('; '.join(problems))
    out, edits = dict(sources), []
    for key, anchor, replacement in EDITS:
        count = out[key].count(anchor)
        edits.append({'file': FILES[key], 'anchor': anchor.strip()[:96], 'anchor_sha256': v2.sha256(anchor), 'count': count})
        if count != 1:
            problems.append(f'anchor {"missing" if count == 0 else f"found {count}x"} in {FILES[key]}: {anchor.strip()[:96]!r}')
            continue
        out[key] = out[key].replace(anchor, replacement, 1)
    if problems:
        raise Refused('; '.join(problems))
    for key in PATCHED:
        if v2.balance(sources[key]) != v2.balance(out[key]):
            raise Refused(f'{FILES[key]}: bracket balance changed by the install')
        if MARKER not in out[key]:
            raise Refused(f'{FILES[key]}: marker missing after install')
    return {'sources': out, 'edits': edits}


def run(source: Path, dry_run: bool) -> dict:
    source = Path(source).resolve()
    missing = [n for n in FILES.values() if not (source / n).is_file()]
    if missing:
        raise Refused(f'missing in {source}: {", ".join(missing)}')
    raw = {key: v2.read_raw(source / name) for key, name in FILES.items()}
    eol = {key: v2.line_ending(FILES[key], raw[key]) for key in FILES}
    result = plan({key: text.replace('\r\n', '\n') for key, text in raw.items()})
    after = {key: result['sources'][key].replace('\n', eol[key]) for key in PATCHED}
    report = {'schema': 'sub01.native-streamer-visual-v2-pinfix-install.v1', 'source': str(source), 'dry_run': dry_run,
              'marker': MARKER, 'requires': face.MARKER,
              'drift_guard': {'reference': "each clip's own pelvis chain at 0 s (frozen R9 at its freeze time)",
                              'above_pelvis': "pinned to the clip's reference", 'pelvis_radius_cm': face.PIN_RADIUS_CM,
                              'pelvis_max_deg': face.PIN_MAX_DEG, 'crossfade': 'references blended with the players weight'},
              'audit': 'log only', 'mouse': 'sitting loop (AuthoredReach excluded)', 'edits': result['edits'],
              'files': {FILES[key]: {'before_sha256': v2.sha256(raw[key]), 'after_sha256': v2.sha256(after[key]),
                                     'bytes_before': len(raw[key].encode()), 'bytes_after': len(after[key].encode()),
                                     'line_ending': 'CRLF' if eol[key] == '\r\n' else 'LF',
                                     'edits': sum(1 for k, _, _ in EDITS if k == key)} for key in PATCHED},
              'read_only': {FILES[key]: v2.sha256(raw[key]) for key in FILES if key not in PATCHED}}
    if not dry_run:
        v2.write_atomically({source / FILES[key]: after[key] for key in PATCHED})
        for key in PATCHED:
            if v2.sha256(v2.read_raw(source / FILES[key])) != report['files'][FILES[key]]['after_sha256']:
                raise Refused(f'{FILES[key]}: written bytes differ from the plan')
    report['status'] = 'planned' if dry_run else 'applied'
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True, help='directory with the v2+face pod files (patched in place)')
    parser.add_argument('--dry-run', action='store_true', help='check every anchor and print the report; write nothing')
    args = parser.parse_args(argv)
    try:
        report = run(args.source, args.dry_run)
    except Refused as error:
        print(json.dumps({'schema': 'sub01.native-streamer-visual-v2-pinfix-install.v1', 'source': str(args.source),
                          'dry_run': args.dry_run, 'status': 'refused', 'reason': str(error)}, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
