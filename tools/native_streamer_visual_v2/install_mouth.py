"""Mouth layer ON TOP of `-Sub01StreamerVisual` v2 (alone, or with the face / pin fix / no-pin layers): the voice moves the mouth.

    python tools/native_streamer_visual_v2/install_mouth.py --source <dir> [--dry-run]

<dir> holds the v2-patched pod files (install.py applied; install_face_camera.py, install_pin_fix.py and install_no_pin.py
may or may not be, in any order). Every anchor is a line install.py itself wrote and no other installer edits, found
exactly once. Refused (exit 2, nothing written) when v2 is absent from any of the four files, when the marker
`// SUB01_STREAMER_VISUAL_V2_MOUTH` is already present or when an anchor is not found exactly once. Same atomic writes,
line-ending handling and JSON report (before/after sha256) as install.py.

What it does. The voice server (scripts/voice_server.py) replaces <streamer-dir>/mouth.json at 25 Hz while it speaks:
`sub01.streamer-mouth.v1` {schema, utc, open 0..1, energy 0..1, speaking, id}, `open` from the short-window RMS of the
audio being played right now (normalised per utterance, 20 ms attack / 80 ms release, zero when silent or cut). The
character polls that file at most 30 Hz next to the event poll (a regular file of the game's uid, not group/other
writable, <= 512 bytes, `utc` within 0.5 s; anything else = closed), bridges the 25 Hz samples to the frame rate and
hands `open` to the anim proxy every tick. Name-table scan of the body assets on the pod (AnatomicalOwner_Skeleton.uasset,
AnatomicalOwner.uasset, 2026-10-23): 65 Mixamo bones (Hips ... Spine2, Neck, Head, HeadTop_End, arms, hands with
fingers, legs), no jaw, mouth or facial bone, no morph target. So the proxy adds HEAD_PITCH_DEG * open of Head pitch as
emphasis, composed with the gaze/nod offset; a skeleton that has a jaw bone (`Jaw`, `jaw`, `JawRoot`, or a bone whose
name ends in Jaw) would get JAW_PITCH_DEG * open on that bone instead. This is not lip sync: real mouth movement needs a
face rig (jaw bone or visemes) on the body mesh; the receipt keeps `facial_animation_or_lipsync` false and adds
`mouth_open`, `mouth_energy`, `mouth_file_fresh`, `mouth_id`, `mouth_rig` (head_only | jaw_bone | none).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location('sub01_streamer_visual_v2_install', Path(__file__).resolve().parent / 'install.py')
v2 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v2)
Refused = v2.Refused

MARKER = '// SUB01_STREAMER_VISUAL_V2_MOUTH'
V2_BEGIN, V2_END = v2.MARKER + ' BEGIN', v2.MARKER + ' END'
FILES = dict(v2.FILES)  # header, cpp, hands_header, hands_cpp
OTHER_LAYERS = {'face': '// SUB01_STREAMER_VISUAL_V2_FACE', 'pin_fix': '// SUB01_STREAMER_VISUAL_V2_PINFIX',
                'no_pin': '// SUB01_STREAMER_VISUAL_V2_NOPIN'}

MOUTH_FILE = '/home/unreal/.sub01-private/streamer/mouth.json'
MOUTH_SCHEMA = 'sub01.streamer-mouth.v1'
POLL_HZ = 30
FRESH_SECONDS = 0.5
MAX_BYTES = 512
SMOOTH_PER_SECOND = 30.0  # game-thread bridge from the 25 Hz samples to the frame rate
HEAD_PITCH_DEG = 2.0      # no face rig: emphasis on the Head (same local-pitch convention as the gaze and the nod)
JAW_PITCH_DEG = 12.0      # a skeleton with a jaw bone: the jaw opens by this much at open = 1
JAW_BONE_NAMES = ('Jaw', 'jaw', 'JawRoot')
RIG_FOUND = 'none: AnatomicalOwner_Skeleton has 65 Mixamo bones (no jaw/mouth/facial bone), AnatomicalOwner has no morph target'


def _line(text: str, start: str) -> str:
    """The one line of `text` starting with `start`, newline included."""
    hits = [line for line in text.splitlines(keepends=True) if line.startswith(start)]
    if len(hits) != 1:
        raise RuntimeError(f'expected one line starting with {start!r} in install.py, found {len(hits)}')
    return hits[0]


# ------------------------------------------------------------------------------------------------ Sub01HomeLab.h
HEADER_FIELDS = r''' // SUB01_STREAMER_VISUAL_V2_MOUTH BEGIN (tools/native_streamer_visual_v2/install_mouth.py): <streamer-dir>/mouth.json -> mouth / head emphasis.
 void ApplyStreamerVisualMouth(double Now,double Epoch,float Dt);
 double StreamerVisualMouthPollAt=0;
 float StreamerVisualMouthTarget=0,StreamerVisualMouthOpen=0,StreamerVisualMouthEnergy=0;
 bool StreamerVisualMouthFresh=false,StreamerVisualMouthLogged=false,StreamerVisualMouthRejectLogged=false;
 FString StreamerVisualMouthId;
 // SUB01_STREAMER_VISUAL_V2_MOUTH END
'''

# ------------------------------------------------------------------------------------------------ Sub01HomeLab.cpp
CPP_METHODS = r'''// SUB01_STREAMER_VISUAL_V2_MOUTH BEGIN (tools/native_streamer_visual_v2/install_mouth.py). The voice moves the mouth: the voice server
// replaces @@FILE@@ at 25 Hz while speaking (@@SCHEMA@@: utc, open 0..1 from the RMS of the audio being
// played, energy, speaking, id). Polled at most @@HZ@@ Hz; a missing, foreign, invalid or stale (> @@FRESH@@ s) file closes the mouth. The
// AnatomicalOwner skeleton has no jaw/facial bone and the mesh no morph target (name-table scan 2026-10-23), so the proxy adds
// @@HEAD@@ deg * open of Head pitch as emphasis (a skeleton with a jaw bone gets @@JAW@@ deg * open on it). Not lip sync: that needs a face rig.
void ASub01HomeCharacter::ApplyStreamerVisualMouth(double Now,double Epoch,float Dt){
 static const char* const MouthPath="@@FILE@@";
 if(Now>=StreamerVisualMouthPollAt){
  StreamerVisualMouthPollAt=Now+1./@@HZ@@;struct stat S;FString Raw,Schema,Id;TSharedPtr<FJsonObject> J;double Utc=0,Open=0,Energy=-1;bool Fresh=false;
  const bool Present=lstat(MouthPath,&S)==0&&S_ISREG(S.st_mode);
  if(Present&&S.st_uid==getuid()&&!(S.st_mode&0022)&&S.st_size>0&&S.st_size<=@@BYTES@@&&
   FFileHelper::LoadFileToString(Raw,UTF8_TO_TCHAR(MouthPath))&&FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Raw),J)&&J.IsValid()&&
   J->TryGetStringField(TEXT("schema"),Schema)&&Schema==TEXT("@@SCHEMA@@")&&
   J->TryGetNumberField(TEXT("utc"),Utc)&&FMath::IsFinite(Utc)&&FMath::Abs(Epoch-Utc)<=@@FRESH@@&&
   J->TryGetNumberField(TEXT("open"),Open)&&FMath::IsFinite(Open)&&Open>=0&&Open<=1){
   Fresh=true;if(!(J->TryGetNumberField(TEXT("energy"),Energy)&&FMath::IsFinite(Energy)&&Energy>=0&&Energy<=1))Energy=Open;
   if(!J->TryGetStringField(TEXT("id"),Id))Id.Empty();
  }else if(Present&&!StreamerVisualMouthRejectLogged&&(S.st_uid!=getuid()||(S.st_mode&0022)||S.st_size>@@BYTES@@)){
   StreamerVisualMouthRejectLogged=true;
   UE_LOG(LogTemp,Warning,TEXT("SUB01_STREAMER_VISUAL_MOUTH_FILE_REJECTED uid=%u mode=%x size=%lld (wanted the game's uid %u, no group/other write, <= @@BYTES@@ bytes); the mouth stays closed"),uint32(S.st_uid),uint32(S.st_mode&0777),(long long)S.st_size,uint32(getuid()));
  }
  StreamerVisualMouthFresh=Fresh;StreamerVisualMouthTarget=Fresh?float(Open):0.f;StreamerVisualMouthEnergy=Fresh?float(Energy):0.f;StreamerVisualMouthId=Fresh?Id:FString();
 }
 // The voice side shapes the envelope (20 ms attack, 80 ms release); this only bridges its 25 Hz samples to the frame rate.
 StreamerVisualMouthOpen+=(StreamerVisualMouthTarget-StreamerVisualMouthOpen)*FMath::Min(1.f,Dt*@@RATE@@);
 if(StreamerVisualMouthTarget<=0&&StreamerVisualMouthOpen<.002f)StreamerVisualMouthOpen=0;
 auto* Anim=FirstPersonBody?Cast<USub01HomeHandsInstance>(FirstPersonBody->GetAnimInstance()):nullptr;if(!Anim)return;
 Anim->StreamerVisualMouthOpen=StreamerVisualMouthOpen;
 if(Anim->StreamerVisualMouthRig>0&&!StreamerVisualMouthLogged){
  StreamerVisualMouthLogged=true;
  UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_MOUTH_READY rig=%s file=%s pollHz=@@HZ@@ headPitchDeg=@@HEAD@@ jawPitchDeg=@@JAW@@"),Anim->StreamerVisualMouthRig==2?TEXT("jaw_bone"):TEXT("head_only (no jaw bone, no morph targets: emphasis, not lip sync)"),UTF8_TO_TCHAR(MouthPath));
 }
}
// SUB01_STREAMER_VISUAL_V2_MOUTH END
'''

RECEIPT_LINE = ('   Receipt->SetNumberField(TEXT("mouth_open"),StreamerVisualMouthOpen);Receipt->SetNumberField(TEXT("mouth_energy"),StreamerVisualMouthEnergy);'
                'Receipt->SetBoolField(TEXT("mouth_file_fresh"),StreamerVisualMouthFresh);Receipt->SetStringField(TEXT("mouth_id"),StreamerVisualMouthId);'
                'Receipt->SetStringField(TEXT("mouth_rig"),V2Anim&&V2Anim->StreamerVisualMouthRig==2?TEXT("jaw_bone"):V2Anim&&V2Anim->StreamerVisualMouthRig==1?TEXT("head_only"):TEXT("none")); // SUB01_STREAMER_VISUAL_V2_MOUTH\n')

# ------------------------------------------------------------------------------------------------ Sub01HomeHands.h
HANDS_FIELDS = r''' // SUB01_STREAMER_VISUAL_V2_MOUTH BEGIN (tools/native_streamer_visual_v2/install_mouth.py): live mouth, written by the character every tick.
 UPROPERTY(Transient) float StreamerVisualMouthOpen=0; // 0..1 from <streamer-dir>/mouth.json, smoothed
 UPROPERTY(Transient) int32 StreamerVisualMouthRig=0; // published by the proxy: 0 unresolved, 1 Head emphasis (no face rig), 2 jaw bone
 // SUB01_STREAMER_VISUAL_V2_MOUTH END
'''

# ------------------------------------------------------------------------------------------------ Sub01HomeHands.cpp
PROXY_MEMBERS = r''' // SUB01_STREAMER_VISUAL_V2_MOUTH BEGIN (tools/native_streamer_visual_v2/install_mouth.py): the live mouth (0..1) from the instance.
 // A jaw bone (exact Jaw / jaw / JawRoot, else a name ending in Jaw) opens by @@JAW@@ deg * open; without one (AnatomicalOwner: Mixamo
 // skeleton, no facial bone, no morph target) the Head gets @@HEAD@@ deg * open as emphasis, composed with the gaze offset applied
 // below (small angles: the order is immaterial). Bones are resolved once per skeleton, like the Spine bones. Runs for v1 and v2 events.
 float StreamerV2Mouth=0;int32 StreamerV2MouthBoneCount=-1,StreamerV2JawBone=INDEX_NONE,StreamerV2MouthHead=INDEX_NONE,StreamerV2MouthRig=0;
 void EvaluateStreamerV2Mouth(FPoseContext& Output){
  const auto& Bones=Output.Pose.GetBoneContainer();const auto& Ref=Bones.GetReferenceSkeleton();
  if(StreamerV2MouthBoneCount!=Ref.GetNum()){
   StreamerV2MouthBoneCount=Ref.GetNum();StreamerV2JawBone=INDEX_NONE;StreamerV2MouthHead=Ref.FindBoneIndex(FName(TEXT("Head")));
   static const TCHAR* const Jaws[3]={TEXT("Jaw"),TEXT("jaw"),TEXT("JawRoot")};
   for(const TCHAR* Name:Jaws)if(StreamerV2JawBone==INDEX_NONE)StreamerV2JawBone=Ref.FindBoneIndex(FName(Name));
   for(int32 B=0;StreamerV2JawBone==INDEX_NONE&&B<Ref.GetNum();++B){const FString Name=Ref.GetBoneName(B).ToString();if(Name.EndsWith(TEXT("Jaw"))||Name.EndsWith(TEXT("jaw")))StreamerV2JawBone=B;}
   StreamerV2MouthRig=StreamerV2JawBone!=INDEX_NONE?2:StreamerV2MouthHead!=INDEX_NONE?1:0;
  }
  const int32 Bone=StreamerV2JawBone!=INDEX_NONE?StreamerV2JawBone:StreamerV2MouthHead;const double Deg=StreamerV2JawBone!=INDEX_NONE?@@JAW@@.:@@HEAD@@.;
  if(Bone==INDEX_NONE||!(StreamerV2Mouth>0))return;
  const auto Compact=Bones.MakeCompactPoseIndex(FMeshPoseBoneIndex(Bone));if(Compact.GetInt()<0)return;
  auto& T=Output.Pose[Compact];T.SetRotation((T.GetRotation()*FRotator(Deg*FMath::Clamp(StreamerV2Mouth,0.f,1.f),0,0).Quaternion()).GetNormalized());
 }
 // SUB01_STREAMER_VISUAL_V2_MOUTH END
'''

_SUBST = {'@@FILE@@': MOUTH_FILE, '@@SCHEMA@@': MOUTH_SCHEMA, '@@HZ@@': f'{POLL_HZ:d}', '@@FRESH@@': f'{FRESH_SECONDS:g}',
          '@@BYTES@@': f'{MAX_BYTES:d}', '@@RATE@@': f'{SMOOTH_PER_SECOND:g}.f', '@@HEAD@@': f'{HEAD_PITCH_DEG:g}', '@@JAW@@': f'{JAW_PITCH_DEG:g}'}


def _fill(text: str) -> str:
    for key, value in _SUBST.items():
        text = text.replace(key, value)
    return text


CPP_METHODS, PROXY_MEMBERS = _fill(CPP_METHODS), _fill(PROXY_MEMBERS)

# v2 lines that no other installer edits (install_face_camera.py and install_pin_fix.py append after some of them, which keeps them intact)
APPLY_LINE = ' ApplyStreamerVisualV2(Now,Dt); // SUB01_STREAMER_VISUAL_V2: state clip, breathing, camera (v1: frozen R9, spectator)\n'
RECEIPT_ANCHOR = _line(v2.RECEIPT_V2, '   Receipt->SetNumberField(TEXT("clip_time"),')
PROXY_COPY = ('  StreamerV2=Hands->StreamerVisualV2;StreamerV2Spine[0]=Hands->StreamerVisualSpine1Offset;'
              'StreamerV2Spine[1]=Hands->StreamerVisualSpine2Offset; // SUB01_STREAMER_VISUAL_V2\n')
PROXY_EVAL = '   if(StreamerV2)EvaluateStreamerV2(Output); // SUB01_STREAMER_VISUAL_V2: reference hands (pre-additive), then breathing; head below\n'
PUBLISH = (' StreamerVisualEvaluatedTime=Proxy.StreamerV2?Proxy.Current.GetAccumulatedTime():-1.f;'
           'StreamerVisualMatchedSeconds=Proxy.StreamerV2MatchedSeconds; // SUB01_STREAMER_VISUAL_V2\n')

EDITS = [
    ('header', ' ' + V2_END + '\n', ' ' + V2_END + '\n' + HEADER_FIELDS),
    ('cpp', V2_END + '\n', V2_END + '\n' + CPP_METHODS),
    ('cpp', APPLY_LINE, APPLY_LINE +
     ' ApplyStreamerVisualMouth(Now,Epoch,Dt); // SUB01_STREAMER_VISUAL_V2_MOUTH: live mouth / head emphasis from <streamer-dir>/mouth.json\n'),
    ('cpp', RECEIPT_ANCHOR, RECEIPT_ANCHOR + RECEIPT_LINE),
    ('hands_header', ' ' + V2_END + '\n', ' ' + V2_END + '\n' + HANDS_FIELDS),
    ('hands_cpp', ' ' + V2_END + '\n', ' ' + V2_END + '\n' + PROXY_MEMBERS),
    ('hands_cpp', PROXY_COPY, PROXY_COPY + '  StreamerV2Mouth=Hands->StreamerVisualMouthOpen; // SUB01_STREAMER_VISUAL_V2_MOUTH\n'),
    ('hands_cpp', PROXY_EVAL, PROXY_EVAL +
     '   EvaluateStreamerV2Mouth(Output); // SUB01_STREAMER_VISUAL_V2_MOUTH: jaw bone if the skeleton has one, else Head emphasis (v1 and v2 events)\n'),
    ('hands_cpp', PUBLISH, PUBLISH + ' StreamerVisualMouthRig=Proxy.StreamerV2MouthRig; // SUB01_STREAMER_VISUAL_V2_MOUTH\n'),
]


def plan(sources: dict) -> dict:
    """Pure transformation of the four LF texts {'header','cpp','hands_header','hands_cpp'}; raises Refused, never partial."""
    problems = [f'{FILES[key]} already carries {MARKER} (mouth layer already installed)' for key in FILES if MARKER in sources[key]]
    if problems:
        raise Refused('; '.join(problems))
    problems = [f'{FILES[key]} lacks the v2 install ({V2_BEGIN} ... {V2_END}); run install.py first'
                for key in FILES if V2_BEGIN not in sources[key] or V2_END not in sources[key]]
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
    for key in FILES:
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
    lf = {key: text.replace('\r\n', '\n') for key, text in raw.items()}
    result = plan(lf)
    after = {key: result['sources'][key].replace('\n', eol[key]) for key in FILES}
    report = {'schema': 'sub01.native-streamer-visual-v2-mouth-install.v1', 'source': str(source), 'dry_run': dry_run,
              'marker': MARKER, 'requires': v2.MARKER,
              'layers_present': {name: any(marker in text for text in lf.values()) for name, marker in OTHER_LAYERS.items()},
              'mouth': {'file': MOUTH_FILE, 'schema': MOUTH_SCHEMA, 'poll_hz_max': POLL_HZ, 'fresh_seconds': FRESH_SECONDS,
                        'max_bytes': MAX_BYTES, 'file_checks': 'regular file, the game\'s uid, not group/other writable',
                        'smoothing_per_second': SMOOTH_PER_SECOND},
              'rig': {'found': RIG_FOUND, 'head_pitch_deg': HEAD_PITCH_DEG, 'jaw_pitch_deg': JAW_PITCH_DEG,
                      'jaw_bone_names': list(JAW_BONE_NAMES) + ['*Jaw', '*jaw'], 'lip_sync': False},
              'receipt_fields': ['mouth_open', 'mouth_energy', 'mouth_file_fresh', 'mouth_id', 'mouth_rig'],
              'edits': result['edits'],
              'files': {FILES[key]: {'before_sha256': v2.sha256(raw[key]), 'after_sha256': v2.sha256(after[key]),
                                     'bytes_before': len(raw[key].encode()), 'bytes_after': len(after[key].encode()),
                                     'line_ending': 'CRLF' if eol[key] == '\r\n' else 'LF',
                                     'edits': sum(1 for k, _, _ in EDITS if k == key)} for key in FILES}}
    if not dry_run:
        v2.write_atomically({source / FILES[key]: after[key] for key in FILES})
        for key in FILES:
            if v2.sha256(v2.read_raw(source / FILES[key])) != report['files'][FILES[key]]['after_sha256']:
                raise Refused(f'{FILES[key]}: written bytes differ from the plan')
    report['status'] = 'planned' if dry_run else 'applied'
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True, help='directory with the v2-patched pod files (patched in place)')
    parser.add_argument('--dry-run', action='store_true', help='check every anchor and print the report; write nothing')
    args = parser.parse_args(argv)
    try:
        report = run(args.source, args.dry_run)
    except Refused as error:
        print(json.dumps({'schema': 'sub01.native-streamer-visual-v2-mouth-install.v1', 'source': str(args.source),
                          'dry_run': args.dry_run, 'status': 'refused', 'reason': str(error)}, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
