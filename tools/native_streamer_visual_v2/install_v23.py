"""v23: live-tunable look corrections ON TOP of v21 (and after v22), for "he has to look real".

    python tools/native_streamer_visual_v2/install_v23.py --source <dir> [--dry-run]

Requires the v21 layer in Sub01HomeLab.h/.cpp and the pose fix in Sub01HomeHands.h/.cpp; refused when
`// SUB01_STREAMER_VISUAL_V2_V23` is already present or any anchor is not found exactly once. Same atomic writes, line
endings and JSON report as the other layers. Never touches Sub01PCBridge.*, Sub01HomeDeviceBridge.*, the monitor feed or the
cam2 code (v22's files and keys). The tuning reader gets ONE clearly delimited block of v23 keys (`// ..._V23 TUNING`), right
after the `Field` lambda, so a merge with another layer's keys never touches the same line.

Every correction is a key of the private tuning file (`/home/unreal/tune.py key=value`, polled every 0.5 s). Every compiled
default skips its code path (no light created, nothing scanned or moved, no extra transform), so the v21 look is bit-identical
until the tuning file says otherwise. Starting values and the session order: RECOMMENDED (Kimi, docs/streamer/kimi/native-v23-design.md).
Defects (docs/streamer/STATUS-20261024.md, docs/streamer/kimi/photos-20261024.md) and their levers:
1. Neck skin / hood ring seam: `neck_share` (the Neck's share of the head channel, v21 0.4; 0 keeps the neck skin with the
   torso-weighted hood ring), `neck_back_deg` (chin tuck: the neck back, the head forward by the same angle, the face keeps its
   angle), `neck_girth` (an experiment: radial scale of the Neck bone across its Neck->child axis, every child given the exact
   inverse scale and translation; skipped unless that offset lies along one local axis, alignment >= NECK_AXIS_MIN, published).
   Existing diagnostic first: `hide_slot` 4 / 5 (hood_lining / hood_patches).
2. Elbow stretch on cam2 (elbow interior 64-80 deg, recipe 85-100): reach first (`hand_back_cm`), the pole (`elbow_pole_back` /
   `elbow_pole_out`, v20 0.5 / 0.3: the elbow beside the torso instead of behind it), and `elbow_min_deg` as a GUARD: the wrist
   target slides forward along the KEYBOARD axis, at the same height, until the elbow opens to the minimum (0..SLIDE_MAX_CM); a
   target behind the shoulder along that axis is declined (slide published as -1) instead of jumping forward, and within
   SLIDE_RAMP_CM ahead of the shoulder the slide fades in, so a target crossing the shoulder line moves continuously.
3. Hunched posture: `pelvis_pitch_deg` (hip hinge: Hips about his lateral axis, FORWARD degrees like the lean, negative = sit up;
   each thigh turned back about its own pivot so its component orientation is kept), `shoulder_drop_deg` / `shoulder_back_deg`
   (clavicles down / retracted), `neck_back_deg`, with the existing spine lean (`typing_lean_deg`, `posture_lean_deg`). All
   before the IK, which re-plants the hands.
4. Fused hands, no contact: `hand_orient` turns each hand about the wrist so the fingers (Hand->Middle1) follow the KEYBOARD's
   forward axis (the body frame only without a keyboard), yawed in by `hand_yaw_in_deg`, pitched down by `hand_pitch_deg`, the
   knuckle line (Index1->Pinky1) level with the pinky outward (palm down follows from handedness): bone POSITIONS, no local-axis
   guess. `finger_bend_deg` (additive on the clip) bends index..pinky (phalanges 1/2/3 by FINGER_SHARE) towards the palm side.
   Mouse: `mouse_scan` 1 adopts the RGB mouse only if exactly ONE primitive component is plausible (a registered, visible
   static-mesh leaf in the mouse zone that does not simulate physics, small, not of the desk packs), makes it Movable and glides
   it (MOUSE_MOVE_CM_S) by the recorded keyboard pull-back; `mouse_scan` 0 glides it back, restores its mobility and releases it;
   a vanished component allows a new scan. `hand_on_mouse` 1 puts the right hand on a found mouse in `idle` and `reading` (the
   agent's `mouse` state keeps its own path).
5. Flat face light: the key moves off the webcam axis (`key_side_cm`, `key_up_extra_cm`; `key_specular` only if highlights clip),
   a FILL (`fill_cd`, `fill_front_cm`, `fill_side_cm`, `fill_up_cm`, `fill_temp_k`) and a RIM (`rim_cd`, `rim_back_cm`,
   `rim_side_cm`, `rim_up_cm`, `rim_temp_k`; its own placement, positive side = his right) spot created on first use, on the key's
   lighting channel, with its softness and radius. Offsets and positions glide (LIGHT_MOVE_CM_S), fill/rim candelas too (LIGHT_CD_RATE).
6. Chair through the hoodie: `chair_scale` widens the chair laterally about the seated pelvis (positions and the actor scale on
   the local axis closest to his side), `chair_back_extra_cm` moves it away from his back after the fit (the fit measures the
   backrest WITHOUT it), `chair_side_cm` only for a measured asymmetric overlap; all eased.
Mouth: no jaw bone and no morph target on this body; nothing here drives a mouth (MOUTH_NOTE).
Logs: `SUB01_STREAMER_VISUAL_V23 ...` (state, clip time, effective values, measurements) at once on a tuning change and every 10 s
while any v23 key is off its default; `..._V23_LIGHTS` (positions, cd) on a tuning change; `..._V23_MOUSE_CANDIDATE` /
`..._V23_MOUSE`. Receipt: `v23_<key>` for every key, `v23_changed`, measurements (incline, head ahead, slide, residual, elbow
behind the shoulder, fingertips above the key plane, orientation error, neck axis alignment), `v23_mouse`, `v23_chair_extra`.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, _HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


v21 = _load('sub01_streamer_visual_v2_v21', 'install_v21_fixes.py')
posefix, cam2, streampass = v21.posefix, v21.cam2, v21.streampass
seatfix, v2, Refused = streampass.seatfix, streampass.v2, streampass.Refused
_f, _d, _line = streampass._f, posefix._d, streampass._line

MARKER = '// SUB01_STREAMER_VISUAL_V2_V23'
FILES = dict(v2.FILES)
SCHEMA = 'sub01.native-streamer-visual-v2-v23-install.v1'

# (key, character field, lo, hi, compiled default = today's look). Every default skips its code path.
TUNING = [
    ('pelvis_pitch_deg', 'StreamerVisualV23PelvisPitchDeg', -20, 20, 0.0),
    ('shoulder_drop_deg', 'StreamerVisualV23ShoulderDropDeg', -10, 20, 0.0),
    ('shoulder_back_deg', 'StreamerVisualV23ShoulderBackDeg', -10, 20, 0.0),
    ('neck_back_deg', 'StreamerVisualV23NeckBackDeg', -15, 20, 0.0),
    ('neck_share', 'StreamerVisualV23NeckShare', 0, 1, 0.4),
    ('neck_girth', 'StreamerVisualV23NeckGirth', 0.9, 1.2, 1.0),
    ('elbow_min_deg', 'StreamerVisualV23ElbowMinDeg', 0, 150, 0.0),
    ('elbow_pole_back', 'StreamerVisualV23ElbowPoleBack', -0.5, 1.5, 0.5),
    ('elbow_pole_out', 'StreamerVisualV23ElbowPoleOut', -0.5, 1.5, 0.3),
    ('hand_orient', 'StreamerVisualV23HandOrient', 0, 1, 0.0),
    ('hand_yaw_in_deg', 'StreamerVisualV23HandYawInDeg', -30, 45, 12.0),
    ('hand_pitch_deg', 'StreamerVisualV23HandPitchDeg', -30, 60, 10.0),
    ('finger_bend_deg', 'StreamerVisualV23FingerBendDeg', 0, 60, 0.0),
    ('mouse_scan', 'StreamerVisualV23MouseScan', 0, 1, 0.0),
    ('hand_on_mouse', 'StreamerVisualV23HandOnMouse', 0, 1, 0.0),
    ('key_side_cm', 'StreamerVisualV23KeySideCm', -80, 80, 0.0),
    ('key_up_extra_cm', 'StreamerVisualV23KeyUpCm', -40, 60, 0.0),
    ('key_specular', 'StreamerVisualV23KeySpecular', 0, 1, 1.0),
    ('fill_cd', 'StreamerVisualV23FillCd', 0, 2, 0.0),
    ('fill_front_cm', 'StreamerVisualV23FillFrontCm', 0, 120, 40.0),
    ('fill_side_cm', 'StreamerVisualV23FillSideCm', -100, 100, 45.0),
    ('fill_up_cm', 'StreamerVisualV23FillUpCm', -40, 80, 0.0),
    ('fill_temp_k', 'StreamerVisualV23FillTempK', 2500, 8000, 5000.0),
    ('rim_cd', 'StreamerVisualV23RimCd', 0, 2, 0.0),
    ('rim_back_cm', 'StreamerVisualV23RimBackCm', 20, 150, 60.0),
    ('rim_side_cm', 'StreamerVisualV23RimSideCm', -100, 100, 30.0),
    ('rim_up_cm', 'StreamerVisualV23RimUpCm', -20, 120, 40.0),
    ('rim_temp_k', 'StreamerVisualV23RimTempK', 2500, 10000, 6500.0),
    ('chair_scale', 'StreamerVisualV23ChairScale', 1, 1.3, 1.0),
    ('chair_back_extra_cm', 'StreamerVisualV23ChairBackCm', -10, 30, 0.0),
    ('chair_side_cm', 'StreamerVisualV23ChairSideCm', -15, 15, 0.0),
]
TUNING_LIMITS = {key: (lo, hi) for key, _, lo, hi, _ in TUNING}
TUNING_FIELDS = {key: field for key, field, _, _, _ in TUNING}
DEFAULTS = {key: default for key, _, _, _, default in TUNING}
assert len(TUNING_FIELDS) == len(TUNING) and all(lo <= DEFAULTS[k] <= hi for k, (lo, hi) in TUNING_LIMITS.items())
# The live session (Kimi, docs/streamer/kimi/native-v23-design.md): ordered steps, each a set of tuning keys (v23 and earlier layers).
# Lock the cam2/webcam exposure (v22) first; judge each step on frames and the receipt before the next. Not compiled in.
RECOMMENDED = [
    ('baseline', {}),
    ('pole test (elbow fan: upper-arm placement?)', {'elbow_pole_back': 0.0, 'elbow_pole_out': 0.45}),
    ('reach test (elbow fan: flexion?), old pole', {'elbow_pole_back': 0.5, 'elbow_pole_out': 0.3, 'hand_back_cm': 5.0}),
    ('elbow combined', {'hand_back_cm': 5.0, 'elbow_min_deg': 90.0, 'elbow_pole_back': 0.0, 'elbow_pole_out': 0.45}),
    ('posture (measured incline; then -12/-16 if still high)', {'pelvis_pitch_deg': -10.0, 'typing_lean_deg': -14.0, 'shoulder_drop_deg': 3.0,
                                                               'shoulder_back_deg': 2.0, 'neck_back_deg': 5.0}),
    ('hands (then hand_height_cm in 0.25 steps; hand_span_cm 24 if they still overlap)', {'hand_orient': 1.0, 'hand_yaw_in_deg': 12.0,
                                                                                          'hand_pitch_deg': 10.0, 'finger_bend_deg': 8.0, 'finger_curl_deg': 0.0}),
    ('neck seam (hide_slot 4 / 5 diagnostics first; 0.10-0.15 if yaw looks rigid; girth 1.05, at most 1.10)', {'neck_share': 0.0}),
    ('chair (then 1.12; back extra 4)', {'chair_scale': 1.08, 'chair_back_extra_cm': 2.0}),
    ('key and fill', {'key_side_cm': -55.0, 'key_up_extra_cm': 10.0, 'fill_cd': 0.010, 'fill_side_cm': 45.0, 'fill_up_cm': 0.0, 'fill_temp_k': 5000.0}),
    ('rim (optional; keep it off if cam2 suffers)', {'rim_cd': 0.006, 'rim_back_cm': 60.0, 'rim_side_cm': 30.0, 'rim_up_cm': 40.0, 'rim_temp_k': 6500.0}),
    ('mouse (scan alone first; the hand only once the mouse and the target coincide)', {'mouse_scan': 1.0, 'hand_on_mouse': 0.0}),
    ('mouse hand', {'hand_on_mouse': 1.0}),
]

POSTURE_RATE, HAND_RATE, WEIGHT_RATE, GIRTH_RATE, CHAIR_RATE_CM_S, CHAIR_SCALE_RATE = 12.0, 30.0, 1.0, 0.2, 60.0, 0.2  # eases (per second)
FINGER_SHARE = (1.0, 1.2, 0.6)        # finger_bend_deg on phalanges 1/2/3 (knuckle, middle, tip joint), additive on the clip
TIP_EXTEND = 0.7                      # fingertip estimate past the last joint when the skeleton has no *4 end bone
SLIDE_MAX_CM = 15.0                   # elbow_min_deg never slides a wrist target further than this
SLIDE_RAMP_CM = 5.0                   # ... and only by Bq/ramp of it while the target is less than this ahead of the shoulder (0 at the shoulder line)
LIGHT_MOVE_CM_S, LIGHT_CD_RATE, MOUSE_MOVE_CM_S = 30.0, 0.02, 30.0  # live changes glide: light/key offsets cm/s, fill/rim candelas per s, the mouse cm/s
NECK_AXIS_MIN = 0.95                  # neck_girth only when the Neck->child offset lies along one local axis (else skipped, logged)
V22_MARKER = '// SUB01_STREAMER_VISUAL_V2_V22'
NECK_SHARE_V21 = (0.4, 0.6)           # the pose fix's Neck/Head split of the head channel
POLE_V20 = (-1.0, 0.5, 0.3)           # the stream pass's pole (up, back, out): down, back, out
MOUSE_ZONE, MOUSE_MAX_EXTENT = streampass.MOUSE_ZONE, streampass.MOUSE_MAX_EXTENT
FILL_CONES, RIM_CONES = (30.0, 55.0), (20.0, 40.0)
LOG_SECONDS = 10.0
MOUTH_NOTE = ('No jaw bone, no facial bone (66 bones: Neck, Head, HeadTop_End) and 0 morph targets. Later, in descending quality (Kimi): '
              'viseme/expression morph targets on the head driven by phoneme timestamps from the voice; a jaw bone plus a small lip/corner '
              'rig with re-skinning (the mouth layer already drives a Jaw bone by 12 deg x open) or a rigged head; procedural lower-face '
              'deformation; texture visemes (stylised only). An opening mouth also needs inner-mouth, teeth and tongue geometry. Not built in v23.')
assert POLE_V20 == streampass.ELBOW_POLE_VECTOR and NECK_SHARE_V21 == posefix.HEAD_WEIGHTS


def _off(key: str) -> str:
    """C++ condition: the key is off its compiled default."""
    return f'{TUNING_FIELDS[key]}!={_f(DEFAULTS[key])}'


# ------------------------------------------------------------------------------------------------ Sub01HomeLab.h
HEADER_V21_END = ' // SUB01_STREAMER_VISUAL_V2_V21 END\n'
_FIELD_DECLS = ''.join(f'{field}={_f(default)},' for _, field, _, _, default in TUNING).rstrip(',')
HEADER_FIELDS = f''' // SUB01_STREAMER_VISUAL_V2_V23 BEGIN (tools/native_streamer_visual_v2/install_v23.py): live look corrections (posture, neck/hood, elbow,
 // hands, mouse, face fill/rim light, chair). Every compiled default skips its code path: the v21 look until the tuning file says otherwise.
 void UpdateStreamerVisualV23(double Now,float Dt,class USub01HomeHandsInstance* Anim);void UpdateStreamerVisualV23Lights(float Dt);void ScanStreamerVisualV23Mouse();bool StreamerVisualV23Changed() const;
 bool StreamerVisualV23MouseCandidate(class UPrimitiveComponent* Prim,const FString& Mesh,bool HasMesh);void AdoptStreamerVisualV23Mouse(class UPrimitiveComponent* Prim);FVector StreamerVisualV23MouseGoal(const FVector& Toward) const;
 class USpotLightComponent* MakeStreamerVisualV23Light(const TCHAR* LightName);FVector StreamerVisualV23ChairWiden(const FVector& Offset) const;void StreamerVisualV23ScaleChairPart(AActor* Part);
 float {_FIELD_DECLS};
 float StreamerVisualV23Shown[11]={{0,0,0,0,{_f(NECK_SHARE_V21[0])},1,0,0,{_f(DEFAULTS['hand_yaw_in_deg'])},{_f(DEFAULTS['hand_pitch_deg'])},0}},StreamerVisualV23PoleShown[2]={{{_f(POLE_V20[1])},{_f(POLE_V20[2])}}},StreamerVisualV23SpecularApplied=1;
 float StreamerVisualV23ChairScaleShown=1,StreamerVisualV23ChairScaleApplied=1;TArray<TWeakObjectPtr<AActor>> StreamerVisualV23ScaledParts;TArray<FVector> StreamerVisualV23PartScales;
 UPROPERTY() TObjectPtr<class USpotLightComponent> StreamerVisualV23Fill;
 UPROPERTY() TObjectPtr<class USpotLightComponent> StreamerVisualV23Rim;
 TWeakObjectPtr<class UPrimitiveComponent> StreamerVisualV23MouseComp;FVector StreamerVisualV23MouseOrigin=FVector::ZeroVector,StreamerVisualV23MouseCentreOffset=FVector::ZeroVector,StreamerVisualV23MouseExtent=FVector::ZeroVector;
 FString StreamerVisualV23MouseName=TEXT("-");bool StreamerVisualV23MouseScanned=false,StreamerVisualV23MouseAdopted=false;int32 StreamerVisualV23MouseCandidates=0;uint8 StreamerVisualV23MouseMobility=0;FVector StreamerVisualV23MouseShown=FVector::ZeroVector;
 float StreamerVisualV23KeyShown[2]={{0,0}},StreamerVisualV23LightCdShown[2]={{0,0}};FVector StreamerVisualV23LightAt[2]={{FVector::ZeroVector,FVector::ZeroVector}};bool StreamerVisualV23LightPlaced[2]={{false,false}};
 FVector StreamerVisualV23ChairShown=FVector::ZeroVector;double StreamerVisualV23LogAt=0,StreamerVisualV23LoggedSequence=-1,StreamerVisualV23LightsLoggedSequence=-1;
 // SUB01_STREAMER_VISUAL_V2_V23 END
'''

# ------------------------------------------------------------------------------------------------ Sub01HomeLab.cpp
CPP_V21_END = '\n// SUB01_STREAMER_VISUAL_V2_V21 END\n'
_SHOWN = [  # Shown[i]: (key, ease rate, neutral when the event is not v2)
    ('pelvis_pitch_deg', POSTURE_RATE, 0.0), ('shoulder_drop_deg', POSTURE_RATE, 0.0), ('shoulder_back_deg', POSTURE_RATE, 0.0),
    ('neck_back_deg', POSTURE_RATE, 0.0), ('neck_share', WEIGHT_RATE, NECK_SHARE_V21[0]), ('neck_girth', GIRTH_RATE, 1.0),
    ('elbow_min_deg', HAND_RATE, 0.0), ('hand_orient', WEIGHT_RATE, 0.0), ('hand_yaw_in_deg', HAND_RATE, DEFAULTS['hand_yaw_in_deg']),
    ('hand_pitch_deg', HAND_RATE, DEFAULTS['hand_pitch_deg']), ('finger_bend_deg', HAND_RATE, 0.0)]
_ANIM_FIELDS = ['StreamerVisualV23PelvisPitchDeg', 'StreamerVisualV23ShoulderDropDeg', 'StreamerVisualV23ShoulderBackDeg', 'StreamerVisualV23NeckBackDeg',
                'StreamerVisualV23NeckShare', 'StreamerVisualV23NeckGirth', 'StreamerVisualV23ElbowMinDeg', 'StreamerVisualV23HandOrient',
                'StreamerVisualV23HandYawInDeg', 'StreamerVisualV23HandPitchDeg', 'StreamerVisualV23FingerBendDeg']
assert len(_SHOWN) == len(_ANIM_FIELDS) == 11
_EASES = '\n'.join(f'  Ease(StreamerVisualV23Shown[{i}],V2?{TUNING_FIELDS[key]}:{_f(neutral)},{_f(rate)});Anim->{_ANIM_FIELDS[i]}=StreamerVisualV23Shown[{i}];'
                   for i, (key, rate, neutral) in enumerate(_SHOWN))
_CHANGED = '||'.join(_off(key) for key, *_ in TUNING)
_LIGHT_KEYS = ('key_side_cm', 'key_up_extra_cm', 'key_specular', 'fill_cd', 'rim_cd')
_LIGHTS_CHANGED = '||'.join(_off(k) for k in _LIGHT_KEYS)
_MZ = MOUSE_ZONE
CPP_METHODS = f'''// SUB01_STREAMER_VISUAL_V2_V23 BEGIN (tools/native_streamer_visual_v2/install_v23.py)
bool ASub01HomeCharacter::StreamerVisualV23Changed() const{{ // any v23 key off its compiled default (= today's look)
 return {_CHANGED};
}}
void ASub01HomeCharacter::UpdateStreamerVisualV23(double Now,float Dt,USub01HomeHandsInstance* Anim){{
 // The live look corrections, after this tick's hands, key light and chair fit. Angles and weights are eased (posture {POSTURE_RATE:g} deg/s like the v15
 // posture layer, hands {HAND_RATE:g} deg/s, weights {WEIGHT_RATE:g}/s) and handed to the proxy, which skips every step at its default; v1 events get the defaults.
 if(!Anim)return;const bool V2=StreamerVisualSchemaVersion==2;
 auto Ease=[Dt](float& Shown,float Goal,float Rate){{const float Step=Rate*FMath::Max(Dt,0.f);Shown=FMath::Abs(Goal-Shown)<=Step?Goal:Shown+(Goal>Shown?Step:-Step);}};
{_EASES}
 // the keyboard frame for the hands (the body faces ~17 deg off the monitor axis; the keys are axis-aligned): its forward axis in component space, and the key plane
 AActor* Keys=StreamerVisualKeyboardActor.Get();Anim->StreamerVisualV23KeyPlaneValid=Keys!=nullptr&&FirstPersonBody!=nullptr;Anim->StreamerVisualV23DeskForward=FVector::ZeroVector;
 if(Keys&&FirstPersonBody){{const FVector DeskFacing=StreamerVisualBodyAuthoredWorld.GetRotation().RotateVector(StreamerVisualFacingLocal);const FTransform BodyNow=FirstPersonBody->GetComponentTransform();
  const FVector TowardHim=FMath::Abs(DeskFacing.Y)>=FMath::Abs(DeskFacing.X)?FVector(0,DeskFacing.Y>0?-1:1,0):FVector(DeskFacing.X>0?-1:1,0,0); // as the hands' targets
  Anim->StreamerVisualV23DeskForward=BodyNow.GetRotation().Inverse().RotateVector(TowardHim*-1.);
  Anim->StreamerVisualV23KeyPlaneZ=float(BodyNow.InverseTransformPosition(Keys->GetActorLocation()+StreamerVisualKeyboardCentreOffset+FVector(0,0,StreamerVisualKeyboardExtent.Z)).Z);}}
 // elbow pole (up, back, out) in his frame: the stream pass's -1 / {POLE_V20[1]:g} / {POLE_V20[2]:g} unless elbow_pole_back / elbow_pole_out say otherwise (eased {WEIGHT_RATE:g}/s)
 Ease(StreamerVisualV23PoleShown[0],V2?StreamerVisualV23ElbowPoleBack:{_f(POLE_V20[1])},{_f(WEIGHT_RATE)});Ease(StreamerVisualV23PoleShown[1],V2?StreamerVisualV23ElbowPoleOut:{_f(POLE_V20[2])},{_f(WEIGHT_RATE)});
 if((StreamerVisualV23PoleShown[0]!={_f(POLE_V20[1])}||StreamerVisualV23PoleShown[1]!={_f(POLE_V20[2])})&&FirstPersonBody){{
  const FVector PoleFacing=StreamerVisualBodyAuthoredWorld.GetRotation().RotateVector(StreamerVisualFacingLocal);const FVector PoleFlat=FVector(PoleFacing.X,PoleFacing.Y,0).GetSafeNormal(),PoleRight=FVector::CrossProduct(FVector::UpVector,PoleFlat);
  const FQuat ToComponent=FirstPersonBody->GetComponentTransform().GetRotation().Inverse();const double PoleBack=StreamerVisualV23PoleShown[0],PoleOut=StreamerVisualV23PoleShown[1];
  Anim->StreamerVisualHandPoleLeft=ToComponent.RotateVector(FVector::UpVector*{_d(POLE_V20[0])}-PoleFlat*PoleBack-PoleRight*PoleOut);
  Anim->StreamerVisualHandPoleRight=ToComponent.RotateVector(FVector::UpVector*{_d(POLE_V20[0])}-PoleFlat*PoleBack+PoleRight*PoleOut);
 }}
 // the RGB mouse as a component: adopted once when mouse_scan turns 1 (only a unique visible, registered static-mesh leaf that does not simulate physics),
 // then it glides ({MOUSE_MOVE_CM_S:g} cm/s) by the keyboard pull-back; mouse_scan 0 glides it back, restores its mobility and releases it; a vanished component allows a new scan
 if(V2&&StreamerVisualV23MouseScan>0&&!StreamerVisualV23MouseScanned)ScanStreamerVisualV23Mouse();
 if(StreamerVisualV23MouseAdopted&&!StreamerVisualV23MouseComp.IsValid()){{StreamerVisualV23MouseAdopted=false;StreamerVisualV23MouseScanned=false;StreamerVisualV23MouseShown=FVector::ZeroVector;StreamerVisualV23MouseName=TEXT("-");}}
 if(UPrimitiveComponent* MouseComp=StreamerVisualV23MouseComp.Get()){{
  const FVector MouseGoal=V2&&StreamerVisualV23MouseScan>0?StreamerVisualDeskPropDelta:FVector::ZeroVector;const FVector MouseStep=MouseGoal-StreamerVisualV23MouseShown;const double MouseMax={_d(MOUSE_MOVE_CM_S)}*double(FMath::Max(Dt,0.f));
  StreamerVisualV23MouseShown=MouseStep.Size()<=MouseMax?MouseGoal:StreamerVisualV23MouseShown+MouseStep.GetSafeNormal()*MouseMax;
  const FVector Want=StreamerVisualV23MouseOrigin+StreamerVisualV23MouseShown;if(!MouseComp->GetComponentLocation().Equals(Want,.01))MouseComp->SetWorldLocation(Want);
  if(StreamerVisualV23MouseScan<=0&&StreamerVisualV23MouseShown.IsNearlyZero(1e-6)){{ // home again (exactly): its own mobility back, released
   MouseComp->SetWorldLocation(StreamerVisualV23MouseOrigin);if(MouseComp->GetMobility()!=EComponentMobility::Type(StreamerVisualV23MouseMobility))MouseComp->SetMobility(EComponentMobility::Type(StreamerVisualV23MouseMobility));
   StreamerVisualV23MouseComp=nullptr;StreamerVisualV23MouseAdopted=false;StreamerVisualV23MouseScanned=false;StreamerVisualV23MouseName=TEXT("-");}}
 }}else if(StreamerVisualV23MouseScan<=0)StreamerVisualV23MouseScanned=false;
 // chair extras along his (seat-yaw-turned) facing and side, and the lateral scale, eased; ApplyStreamerVisualV2 adds the offset to the chair delta (the fit leaves it out)
 {{const FQuat ChairTurn(FVector::UpVector,FMath::DegreesToRadians(double(StreamerVisualSeatYawDeg)));
  const FVector ChairFacing=ChairTurn.RotateVector(StreamerVisualBodyAuthoredWorld.GetRotation().RotateVector(StreamerVisualFacingLocal)*FVector(1,1,0)).GetSafeNormal(),ChairSide=FVector::CrossProduct(FVector::UpVector,ChairFacing);
  const FVector ChairGoal=V2&&StreamerVisualDeskPropsEnabled>0&&(StreamerVisualV23ChairBackCm!=0||StreamerVisualV23ChairSideCm!=0)?ChairFacing*double(-StreamerVisualV23ChairBackCm)+ChairSide*double(StreamerVisualV23ChairSideCm):FVector::ZeroVector;
  const FVector ChairStep=ChairGoal-StreamerVisualV23ChairShown;const double ChairMax={_d(CHAIR_RATE_CM_S)}*double(FMath::Max(Dt,0.f));
  StreamerVisualV23ChairShown=ChairStep.Size()<=ChairMax?ChairGoal:StreamerVisualV23ChairShown+ChairStep.GetSafeNormal()*ChairMax;
  Ease(StreamerVisualV23ChairScaleShown,V2&&StreamerVisualDeskPropsEnabled>0?StreamerVisualV23ChairScale:1.f,{_f(CHAIR_SCALE_RATE)});}}
 UpdateStreamerVisualV23Lights(Dt);
 if(!V2||!(StreamerVisualV23Changed()||StreamerVisualV23LoggedSequence>=0))return;
 if(Now<StreamerVisualV23LogAt&&StreamerVisualV23LoggedSequence==StreamerVisualFaceTuningSequence)return; // at once on a tuning change, else every {LOG_SECONDS:g} s
 StreamerVisualV23LogAt=Now+{_d(LOG_SECONDS)};StreamerVisualV23LoggedSequence=StreamerVisualV23Changed()?StreamerVisualFaceTuningSequence:-1;
 UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_V23 state=%s clipTime=%.2f tuningSequence=%.0f pelvisPitch=%.1f shoulderDrop=%.1f shoulderBack=%.1f neckBack=%.1f neckShare=%.2f neckGirth=%.2f neckAxisAlign=%.2f incline=%.1f headAheadCm=%.1f elbowMin=%.0f pole=%.2f/%.2f elbow=L%.0f/R%.0f slideCm=L%.1f/R%.1f residualCm=L%.1f/R%.1f elbowBackCm=L%.1f/R%.1f orient=%.2f yawIn=%.0f pitch=%.0f orientErr=L%.1f/R%.1f fingerBend=%.0f fingers=L%.0f/%.0f R%.0f/%.0f tipsAboveKeysCm=L%.1f(min %.1f)/R%.1f(min %.1f) mouse=%s handOnMouse=%d chairScale=%.2f chair=%s"),
  *StreamerVisualState,Anim->StreamerVisualEvaluatedTime,StreamerVisualFaceTuningSequence,StreamerVisualV23Shown[0],StreamerVisualV23Shown[1],StreamerVisualV23Shown[2],StreamerVisualV23Shown[3],StreamerVisualV23Shown[4],StreamerVisualV23Shown[5],
  Anim->StreamerVisualV23NeckAxisAlign,Anim->StreamerVisualV23InclineDeg,Anim->StreamerVisualV23HeadAheadCm,StreamerVisualV23Shown[6],StreamerVisualV23PoleShown[0],StreamerVisualV23PoleShown[1],StreamerVisualElbowDeg[0],StreamerVisualElbowDeg[1],
  Anim->StreamerVisualV23SlideLeftCm,Anim->StreamerVisualV23SlideRightCm,Anim->StreamerVisualV23ResidualLeftCm,Anim->StreamerVisualV23ResidualRightCm,Anim->StreamerVisualV23ElbowBackLeftCm,Anim->StreamerVisualV23ElbowBackRightCm,
  StreamerVisualV23Shown[7],StreamerVisualV23Shown[8],StreamerVisualV23Shown[9],Anim->StreamerVisualV23OrientErrLeftDeg,Anim->StreamerVisualV23OrientErrRightDeg,StreamerVisualV23Shown[10],
  StreamerVisualFingerCurlMeasured[0],StreamerVisualFingerCurlMeasured[1],StreamerVisualFingerCurlMeasured[2],StreamerVisualFingerCurlMeasured[3],Anim->StreamerVisualV23TipMeanLeftCm,Anim->StreamerVisualV23TipMinLeftCm,
  Anim->StreamerVisualV23TipMeanRightCm,Anim->StreamerVisualV23TipMinRightCm,*StreamerVisualV23MouseName,StreamerVisualV23HandOnMouse>0?1:0,StreamerVisualV23ChairScaleShown,*StreamerVisualV23ChairShown.ToString());
}}
USpotLightComponent* ASub01HomeCharacter::MakeStreamerVisualV23Light(const TCHAR* LightName){{ // a soft spot like the key: movable, candelas, no shadows, dark until placed
 USpotLightComponent* Made=NewObject<USpotLightComponent>(this,LightName);Made->SetMobility(EComponentMobility::Movable);Made->SetIntensityUnits(ELightUnits::Candelas);
 Made->SetCastShadows(false);Made->bUseTemperature=true;Made->SetIntensity(0.f);Made->SetVisibility(false);Made->RegisterComponent();return Made;
}}
void ASub01HomeCharacter::UpdateStreamerVisualV23Lights(float Dt){{
 // After UpdateStreamerVisualKeyLight (same tick): its aim (the face camera's head mean, else the Head bone) and its monitor frame. key_side_cm / key_up_extra_cm
 // move the key off the webcam axis; the fill sits between him and the monitor, the rim behind him (rim_side_cm is its own placement, positive = his right);
 // both on the key's lighting channel, with its softness and radius. Live changes glide: offsets and positions {LIGHT_MOVE_CM_S:g} cm/s, fill/rim {LIGHT_CD_RATE:g} cd/s.
 // The engine's light setters return early on an unchanged value, so re-applying them every tick costs nothing.
 if(!StreamerVisualKeyLight)return;const bool V2=StreamerVisualSchemaVersion==2;const FVector LightAim=StreamerVisualKeyLightAim;const double Move={_d(LIGHT_MOVE_CM_S)}*double(FMath::Max(Dt,0.f));
 const FVector Monitor({seatfix.MONITOR[0]},{seatfix.MONITOR[1]},{seatfix.MONITOR[2]});FVector Towards(LightAim.X-Monitor.X,LightAim.Y-Monitor.Y,0); // from the monitor towards him
 Towards=Towards.Size()>10?Towards.GetSafeNormal():FVector(0,1,0);const FVector LightSide=FVector::CrossProduct(FVector::UpVector,-Towards); // his right
 auto Glide=[](float& Value,float Goal,float Step){{Value=FMath::Abs(Goal-Value)<=Step?Goal:Value+(Goal>Value?Step:-Step);}};
 Glide(StreamerVisualV23KeyShown[0],V2?StreamerVisualV23KeySideCm:0.f,float(Move));Glide(StreamerVisualV23KeyShown[1],V2?StreamerVisualV23KeyUpCm:0.f,float(Move));
 if(StreamerVisualV23KeyShown[0]!=0||StreamerVisualV23KeyShown[1]!=0){{ // back at 0 / 0 the key light's own update has placed it this tick
  const FVector KeyAt=Monitor+Towards*6.+LightSide*double(StreamerVisualFaceSideCm+StreamerVisualV23KeyShown[0])+FVector(0,0,StreamerVisualKeyLightUpCm+StreamerVisualV23KeyShown[1]);
  StreamerVisualKeyLight->SetWorldLocationAndRotation(KeyAt,(LightAim-KeyAt).Rotation());}}
 const bool BodyOnly=StreamerVisualKeyLightBodyOnly>0;
 for(int32 K=0;K<2;++K){{Glide(StreamerVisualV23LightCdShown[K],V2?(K?StreamerVisualV23RimCd:StreamerVisualV23FillCd):0.f,{_f(LIGHT_CD_RATE)}*FMath::Max(Dt,0.f));const float Cd=StreamerVisualV23LightCdShown[K];
  TObjectPtr<USpotLightComponent>& Extra=K?StreamerVisualV23Rim:StreamerVisualV23Fill;
  if(Cd<=0){{if(Extra){{Extra->SetIntensity(0.f);Extra->SetVisibility(false);}}StreamerVisualV23LightPlaced[K]=false;continue;}}
  if(!Extra)Extra=MakeStreamerVisualV23Light(K?TEXT("StreamerVisualV23Rim"):TEXT("StreamerVisualV23Fill"));
  const FVector Target=K?LightAim+Towards*double(StreamerVisualV23RimBackCm)+LightSide*double(StreamerVisualV23RimSideCm)+FVector(0,0,StreamerVisualV23RimUpCm)
                        :LightAim-Towards*double(StreamerVisualV23FillFrontCm)+LightSide*double(StreamerVisualV23FillSideCm)+FVector(0,0,StreamerVisualV23FillUpCm);
  FVector& At=StreamerVisualV23LightAt[K];if(!StreamerVisualV23LightPlaced[K]){{At=Target;StreamerVisualV23LightPlaced[K]=true;}} // it appears where it belongs (its intensity rises from 0)
  else{{const FVector Step=Target-At;At=Step.Size()<=Move?Target:At+Step.GetSafeNormal()*Move;}}
  Extra->SetWorldLocationAndRotation(At,(LightAim-At).Rotation());Extra->SetIntensity(Cd);Extra->SetTemperature(K?StreamerVisualV23RimTempK:StreamerVisualV23FillTempK);
  Extra->SetAttenuationRadius(StreamerVisualKeyLightRadiusCm);Extra->SetSourceRadius(StreamerVisualKeyLightSoftCm*.5f);Extra->SetSoftSourceRadius(StreamerVisualKeyLightSoftCm);
  Extra->SetInnerConeAngle(K?{_f(RIM_CONES[0])}:{_f(FILL_CONES[0])});Extra->SetOuterConeAngle(K?{_f(RIM_CONES[1])}:{_f(FILL_CONES[1])});Extra->SetLightingChannels(!BodyOnly,BodyOnly,false);Extra->SetVisibility(true);
 }}
 const float Specular=V2?StreamerVisualV23KeySpecular:1.f; // the key's (and fill/rim) specular; on change for the key, every tick for lights created later
 if(Specular!=StreamerVisualV23SpecularApplied){{StreamerVisualV23SpecularApplied=Specular;StreamerVisualKeyLight->SetSpecularScale(Specular);}}
 if(StreamerVisualV23Fill)StreamerVisualV23Fill->SetSpecularScale(Specular);if(StreamerVisualV23Rim)StreamerVisualV23Rim->SetSpecularScale(Specular);
 if(V2&&StreamerVisualV23LightsLoggedSequence!=StreamerVisualFaceTuningSequence&&({_LIGHTS_CHANGED})){{StreamerVisualV23LightsLoggedSequence=StreamerVisualFaceTuningSequence;
  UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_V23_LIGHTS key=%s keyCd=%.3f fill=%s fillCd=%.3f rim=%s rimCd=%.3f aim=%s specular=%.2f bodyOnly=%d (offsets and intensities glide to these targets)"),
   *StreamerVisualKeyLight->GetComponentLocation().ToString(),StreamerVisualKeyLightCd,StreamerVisualV23Fill?*StreamerVisualV23Fill->GetComponentLocation().ToString():TEXT("-"),StreamerVisualV23FillCd,
   StreamerVisualV23Rim?*StreamerVisualV23Rim->GetComponentLocation().ToString():TEXT("-"),StreamerVisualV23RimCd,*LightAim.ToString(),Specular,BodyOnly?1:0);}}
}}
bool ASub01HomeCharacter::StreamerVisualV23MouseCandidate(UPrimitiveComponent* Prim,const FString& Mesh,bool HasMesh){{
 // Plausible mouse: a registered, visible static-mesh LEAF that does not simulate physics, bounds centre in the mouse zone, small, not of the keyboard/desk packs.
 if(!Prim)return false;const FVector Origin=Prim->Bounds.Origin,Extent=Prim->Bounds.BoxExtent;
 if(Origin.X<{_MZ['x'][0]}||Origin.X>{_MZ['x'][1]}||Origin.Y<{_MZ['y'][0]}||Origin.Y>{_MZ['y'][1]}||Origin.Z<{_MZ['z'][0]}||Origin.Z>{_MZ['z'][1]})return false;
 const bool Small=Extent.X<={MOUSE_MAX_EXTENT[0]}&&Extent.Y<={MOUSE_MAX_EXTENT[1]}&&Extent.Z<={MOUSE_MAX_EXTENT[2]},Pack=Mesh.StartsWith(TEXT("{seatfix.DESK_PROP_MESH_PREFIX}"))||Mesh.StartsWith(TEXT("{seatfix.DESK_MESH_PREFIX}"));
 const bool Leaf=Prim->GetNumChildrenComponents()==0,Visible=Prim->IsRegistered()&&Prim->IsVisible(),Simulating=Prim->IsSimulatingPhysics();
 const bool Plausible=Small&&!Pack&&Leaf&&Visible&&!Simulating&&HasMesh;++StreamerVisualV23MouseCandidates;
 UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_V23_MOUSE_CANDIDATE path=%s mesh=%s origin=%s extent=%s transform=%s leaf=%d visible=%d simulating=%d staticMesh=%d plausible=%d"),*Prim->GetPathName(),*Mesh,
  *Origin.ToString(),*Extent.ToString(),*Prim->GetComponentTransform().ToString(),Leaf?1:0,Visible?1:0,Simulating?1:0,HasMesh?1:0,Plausible?1:0);
 return Plausible;
}}
void ASub01HomeCharacter::AdoptStreamerVisualV23Mouse(UPrimitiveComponent* Prim){{ // the unique plausible candidate: its place and mobility are kept for the release
 StreamerVisualV23MouseComp=Prim;StreamerVisualV23MouseAdopted=Prim!=nullptr;StreamerVisualV23MouseShown=FVector::ZeroVector;if(!Prim)return;
 StreamerVisualV23MouseOrigin=Prim->GetComponentLocation();StreamerVisualV23MouseCentreOffset=Prim->Bounds.Origin-StreamerVisualV23MouseOrigin;StreamerVisualV23MouseExtent=Prim->Bounds.BoxExtent;
 StreamerVisualV23MouseName=Prim->GetPathName();StreamerVisualV23MouseMobility=uint8(Prim->GetMobility());if(Prim->GetMobility()!=EComponentMobility::Movable)Prim->SetMobility(EComponentMobility::Movable);
}}
void ASub01HomeCharacter::ScanStreamerVisualV23Mouse(){{
 // mouse_scan 1: the v20 scan looked at ACTOR locations and found no mouse (the RGB mouse is part of a bigger actor). Every primitive COMPONENT of every
 // actor but his own and the desk props is considered; exactly ONE plausible candidate is adopted, otherwise nothing moves ("no unique candidate").
 StreamerVisualV23MouseScanned=true;StreamerVisualV23MouseComp=nullptr;StreamerVisualV23MouseAdopted=false;StreamerVisualV23MouseCandidates=0;StreamerVisualV23MouseName=TEXT("none");
 if(StreamerVisualMouseActor.IsValid()){{StreamerVisualV23MouseName=TEXT("actor");return;}}if(!GetWorld())return;int32 Plausible=0;UPrimitiveComponent* Pick=nullptr;
 for(TActorIterator<AActor> It(GetWorld());It;++It){{AActor* A=*It;if(!A||A==this)continue;bool Prop=false;for(const TWeakObjectPtr<AActor>& Known:StreamerVisualDeskProps)Prop=Prop||Known.Get()==A;if(Prop)continue;
  TArray<UPrimitiveComponent*> Prims;A->GetComponents(Prims);
  for(UPrimitiveComponent* Prim:Prims){{const UStaticMeshComponent* MeshComp=Cast<UStaticMeshComponent>(Prim);const bool HasMesh=MeshComp&&MeshComp->GetStaticMesh();
   if(StreamerVisualV23MouseCandidate(Prim,HasMesh?MeshComp->GetStaticMesh()->GetName():FString(TEXT("none")),HasMesh)){{++Plausible;Pick=Prim;}}}}
 }}
 if(Plausible==1)AdoptStreamerVisualV23Mouse(Pick);else StreamerVisualV23MouseName=Plausible?TEXT("no unique candidate"):TEXT("none");
 UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_V23_MOUSE found=%d component=%s plausible=%d candidates=%d (adopted only when exactly one is plausible; hand_on_mouse needs it)"),StreamerVisualV23MouseComp.IsValid()?1:0,
  *StreamerVisualV23MouseName,Plausible,StreamerVisualV23MouseCandidates);
}}
FVector ASub01HomeCharacter::StreamerVisualV23MouseGoal(const FVector& Toward) const{{ // the right wrist behind the adopted mouse component, else the tuning point
 if(UPrimitiveComponent* MouseComp=StreamerVisualV23MouseComp.Get())return MouseComp->GetComponentLocation()+StreamerVisualV23MouseCentreOffset+Toward*double(StreamerVisualMouseBackCm)+FVector(0,0,-StreamerVisualV23MouseExtent.Z+StreamerVisualHandHeightCm);
 return FVector(StreamerVisualMouseX,StreamerVisualMouseY,StreamerVisualMouseZ);
}}
FVector ASub01HomeCharacter::StreamerVisualV23ChairWiden(const FVector& Offset) const{{ // chair_scale: a chair part's offset from the seated pelvis, widened along his side only
 if(StreamerVisualV23ChairScaleShown==1.f)return Offset;
 const FVector WidenFacing=StreamerVisualBodyAuthoredWorld.GetRotation().RotateVector(StreamerVisualFacingLocal)*FVector(1,1,0);const FVector WidenSide=FVector::CrossProduct(FVector::UpVector,WidenFacing.GetSafeNormal());
 return Offset+WidenSide*(FVector::DotProduct(Offset,WidenSide)*(double(StreamerVisualV23ChairScaleShown)-1.));
}}
void ASub01HomeCharacter::StreamerVisualV23ScaleChairPart(AActor* Part){{ // chair_scale on the part's local axis closest to his side; the authored scale kept per part
 if(!Part||(StreamerVisualV23ChairScaleShown==1.f&&StreamerVisualV23ScaledParts.Num()==0))return; // never scaled: untouched
 int32 Slot=-1;for(int32 I=0;I<StreamerVisualV23ScaledParts.Num();++I)if(StreamerVisualV23ScaledParts[I].Get()==Part)Slot=I;
 if(Slot<0){{Slot=StreamerVisualV23ScaledParts.Add(Part);StreamerVisualV23PartScales.Add(Part->GetActorScale3D());}}
 const FVector ScaleFacing=StreamerVisualBodyAuthoredWorld.GetRotation().RotateVector(StreamerVisualFacingLocal)*FVector(1,1,0);const FVector ScaleSide=FVector::CrossProduct(FVector::UpVector,ScaleFacing.GetSafeNormal());
 const FQuat PartQuat=Part->GetActorQuat();const double OnX=FMath::Abs(FVector::DotProduct(PartQuat.RotateVector(FVector(1,0,0)),ScaleSide)),OnY=FMath::Abs(FVector::DotProduct(PartQuat.RotateVector(FVector(0,1,0)),ScaleSide)),
  OnZ=FMath::Abs(FVector::DotProduct(PartQuat.RotateVector(FVector(0,0,1)),ScaleSide));const double Widen=double(StreamerVisualV23ChairScaleShown);const FVector Authored=StreamerVisualV23PartScales[Slot];
 Part->SetActorScale3D(OnX>=OnY&&OnX>=OnZ?FVector(Authored.X*Widen,Authored.Y,Authored.Z):(OnY>=OnZ?FVector(Authored.X,Authored.Y*Widen,Authored.Z):FVector(Authored.X,Authored.Y,Authored.Z*Widen)));
}}
// SUB01_STREAMER_VISUAL_V2_V23 END
'''

TUNING_LAMBDA = (' auto Field=[&J](const TCHAR* Key,float& Out,double Lo,double Hi){double V=0;if(J->TryGetNumberField(Key,V)&&FMath::IsFinite(V))'
                 'Out=float(FMath::Clamp(V,Lo,Hi));};\n')
TUNING_BLOCK = (TUNING_LAMBDA
                + ' // SUB01_STREAMER_VISUAL_V2_V23 TUNING (tools/native_streamer_visual_v2/install_v23.py): the v23 keys, in their own lines for merges\n'
                + ''.join(f' Field(TEXT("{key}"),{field},{lo},{hi});' + ('\n' if i % 6 == 5 or i == len(TUNING) - 1 else '')
                          for i, (key, field, lo, hi, _) in enumerate(TUNING))
                + ' // SUB01_STREAMER_VISUAL_V2_V23 TUNING END\n')
TICK_POSE = '  FitStreamerVisualChair(Now,Dt,Anim);LogStreamerVisualPose(Now,Anim); // SUB01_STREAMER_VISUAL_V2_POSEFIX\n'
TICK_V23 = TICK_POSE + '  UpdateStreamerVisualV23(Now,Dt,Anim); // SUB01_STREAMER_VISUAL_V2_V23: the live look corrections (after hands, key light and chair fit)\n'
CHAIR_DELTA = '+StreamerVisualChairFitShown:FVector::ZeroVector; // + SUB01_STREAMER_VISUAL_V2_POSEFIX: the chair fit (eased)\n'
CHAIR_DELTA_V23 = ('+StreamerVisualChairFitShown+StreamerVisualV23ChairShown:FVector::ZeroVector; // + SUB01_STREAMER_VISUAL_V2_POSEFIX: the chair fit (eased);'
                   ' + SUB01_STREAMER_VISUAL_V2_V23: chair_back_extra_cm / chair_side_cm (eased)\n')
FIT_GAP = ' const double Gap=FVector::DotProduct(Sacrum,Facing)-Front,Move=Gap-double(StreamerVisualBackrestGapCm);'
FIT_GAP_V23 = (' const double Gap=FVector::DotProduct(Sacrum,Facing)-Front+FVector::DotProduct(StreamerVisualV23ChairShown,Facing),Move=Gap-double(StreamerVisualBackrestGapCm);'
               ' /* SUB01_STREAMER_VISUAL_V2_V23: measured without the v23 chair extra */')
MOVE_CHAIR = ('A->SetActorLocationAndRotation(StreamerVisualChairPivotWorld+Yaw.RotateVector(StreamerVisualDeskPropOrigins[I]-StreamerVisualChairPivotWorld)+StreamerVisualChairDelta,'
              'Yaw*StreamerVisualDeskPropRotations[I],false,nullptr,ETeleportType::TeleportPhysics);}\n')
MOVE_CHAIR_V23 = ('A->SetActorLocationAndRotation(StreamerVisualChairPivotWorld+Yaw.RotateVector(StreamerVisualV23ChairWiden(StreamerVisualDeskPropOrigins[I]-StreamerVisualChairPivotWorld))+StreamerVisualChairDelta,'
                  'Yaw*StreamerVisualDeskPropRotations[I],false,nullptr,ETeleportType::TeleportPhysics);StreamerVisualV23ScaleChairPart(A);} // SUB01_STREAMER_VISUAL_V2_V23: chair_scale\n')
GATE_CHAIR = ('&&StreamerVisualChairYaw==StreamerVisualChairYawApplied)return;StreamerVisualChairDeltaApplied=StreamerVisualChairDelta;'
              'StreamerVisualChairYawApplied=StreamerVisualChairYaw;')
GATE_CHAIR_V23 = ('&&StreamerVisualChairYaw==StreamerVisualChairYawApplied&&StreamerVisualV23ChairScaleShown==StreamerVisualV23ChairScaleApplied)return;'
                  'StreamerVisualChairDeltaApplied=StreamerVisualChairDelta;StreamerVisualChairYawApplied=StreamerVisualChairYaw;StreamerVisualV23ChairScaleApplied=StreamerVisualV23ChairScaleShown;'
                  ' /* SUB01_STREAMER_VISUAL_V2_V23: chair_scale */')
HANDS_STATE = '  if(StreamerVisualState==TEXT("mouse")){AActor* M=StreamerVisualMouseActor.Get(); // the left hand stays planted on the keys\n'
HANDS_STATE_V23 = ('  if(StreamerVisualState==TEXT("mouse")||(StreamerVisualV23HandOnMouse>0&&(StreamerVisualState==TEXT("reading")||StreamerVisualState==TEXT("idle"))'
                   '&&(StreamerVisualMouseActor.IsValid()||StreamerVisualV23MouseComp.IsValid()))){AActor* M=StreamerVisualMouseActor.Get();'
                   ' // the left hand stays planted on the keys; SUB01_STREAMER_VISUAL_V2_V23: hand_on_mouse 1 in idle/reading, with a mouse found\n')
HANDS_GOAL_TAIL = ':FVector(StreamerVisualMouseX,StreamerVisualMouseY,StreamerVisualMouseZ);\n'
HANDS_GOAL_TAIL_V23 = ':StreamerVisualV23MouseGoal(Toward); // SUB01_STREAMER_VISUAL_V2_V23: the adopted mouse component, else mouse_x/y/z\n'
HANDS_NAME = '   Name[1]=M?TEXT("mouse_prop"):TEXT("mouse_point");}\n'
HANDS_NAME_V23 = '   Name[1]=M?TEXT("mouse_prop"):StreamerVisualV23MouseComp.IsValid()?TEXT("mouse_component"):TEXT("mouse_point");} // SUB01_STREAMER_VISUAL_V2_V23\n'
RECEIPT_ANCHOR = 'Receipt->SetNumberField(TEXT("face_aim_mean_s"),StreamerVisualFaceMeanSeconds);\n'
_RECEIPT_KEYS = ''.join(f'Receipt->SetNumberField(TEXT("v23_{key}"),{TUNING_FIELDS[key]});' for key, *_ in TUNING)
_RECEIPT_MEASURED = (('incline_deg', 'InclineDeg'), ('head_ahead_cm', 'HeadAheadCm'), ('slide_left_cm', 'SlideLeftCm'), ('slide_right_cm', 'SlideRightCm'),
                     ('residual_left_cm', 'ResidualLeftCm'), ('residual_right_cm', 'ResidualRightCm'), ('elbow_back_left_cm', 'ElbowBackLeftCm'),
                     ('elbow_back_right_cm', 'ElbowBackRightCm'), ('orient_err_left_deg', 'OrientErrLeftDeg'), ('orient_err_right_deg', 'OrientErrRightDeg'),
                     ('tips_above_keys_left_cm', 'TipMeanLeftCm'), ('tips_above_keys_right_cm', 'TipMeanRightCm'),
                     ('tips_min_above_keys_left_cm', 'TipMinLeftCm'), ('tips_min_above_keys_right_cm', 'TipMinRightCm'), ('neck_axis_align', 'NeckAxisAlign'))
RECEIPT_V23 = (RECEIPT_ANCHOR
               + '   // SUB01_STREAMER_VISUAL_V2_V23: the tuning values, what the proxy measured, the adopted mouse, the chair extra\n'
               + '   ' + _RECEIPT_KEYS + '\n'
               + '   Receipt->SetBoolField(TEXT("v23_changed"),StreamerVisualV23Changed());Receipt->SetStringField(TEXT("v23_mouse"),StreamerVisualV23MouseName);'
               'Receipt->SetStringField(TEXT("v23_chair_extra"),StreamerVisualV23ChairShown.ToString());Receipt->SetNumberField(TEXT("v23_chair_scale_applied"),StreamerVisualV23ChairScaleShown);\n'
               '   if(V2Anim){' + ''.join(f'Receipt->SetNumberField(TEXT("v23_{name}"),V2Anim->StreamerVisualV23{field});' for name, field in _RECEIPT_MEASURED) + '}\n')

# ------------------------------------------------------------------------------------------------ Sub01HomeHands.h
HANDS_POSE_END = ' // SUB01_STREAMER_VISUAL_V2_POSEFIX END\n'
_PUBLISHED = [('InclineDeg', '0', 'Hips->Head line from vertical, forward positive'), ('HeadAheadCm', '0', 'Head ahead of the mid-shoulder (arm roots) along his facing'),
              ('SlideLeftCm', '0', 'wrist target slide for elbow_min_deg (-1 = declined: the target is behind the shoulder)'), ('SlideRightCm', '0', ''),
              ('ResidualLeftCm', '-1', 'wrist to the (slid) target after the solve'), ('ResidualRightCm', '-1', ''),
              ('ElbowBackLeftCm', '0', 'elbow behind the shoulder along the keyboard axis (negative = in front)'), ('ElbowBackRightCm', '0', ''),
              ('OrientErrLeftDeg', '-1', 'finger direction vs the wanted one after hand_orient (-1 = off)'), ('OrientErrRightDeg', '-1', ''),
              ('TipMeanLeftCm', '-99', 'index..pinky fingertips above the key plane, mean (-99 = no key plane)'), ('TipMeanRightCm', '-99', ''),
              ('TipMinLeftCm', '-99', 'the lowest fingertip above the key plane (negative = into the keys)'), ('TipMinRightCm', '-99', ''),
              ('NeckAxisAlign', '-1', 'neck_girth: the Neck->child offset on its long local axis / its length (-1 = girth off; below NECK_AXIS_MIN it is skipped)')]
HANDS_FIELDS = (f''' // SUB01_STREAMER_VISUAL_V2_V23 BEGIN (tools/native_streamer_visual_v2/install_v23.py): look corrections, set by the character every tick (eased).
 UPROPERTY(Transient) float StreamerVisualV23PelvisPitchDeg=0; // hip hinge, FORWARD degrees (negative = sit up); the thighs keep their orientation
 UPROPERTY(Transient) float StreamerVisualV23ShoulderDropDeg=0; // clavicles down (positive)
 UPROPERTY(Transient) float StreamerVisualV23ShoulderBackDeg=0; // clavicles retracted (positive)
 UPROPERTY(Transient) float StreamerVisualV23NeckBackDeg=0; // chin tuck: Neck back, Head forward by the same angle
 UPROPERTY(Transient) float StreamerVisualV23NeckShare={_f(NECK_SHARE_V21[0])}; // the Neck's share of the head channel (the rest on Head)
 UPROPERTY(Transient) float StreamerVisualV23NeckGirth=1; // radial scale of the Neck bone (its children compensated)
 UPROPERTY(Transient) float StreamerVisualV23ElbowMinDeg=0; // the wrist target slides forward until the elbow interior angle reaches this
 UPROPERTY(Transient) float StreamerVisualV23HandOrient=0; // 0..1 hand orientation blend (fingers along the keyboard axis, palm down)
 UPROPERTY(Transient) float StreamerVisualV23HandYawInDeg={_f(DEFAULTS['hand_yaw_in_deg'])};
 UPROPERTY(Transient) float StreamerVisualV23HandPitchDeg={_f(DEFAULTS['hand_pitch_deg'])};
 UPROPERTY(Transient) float StreamerVisualV23FingerBendDeg=0; // index..pinky bend towards the palm (x{FINGER_SHARE[0]:g}/{FINGER_SHARE[1]:g}/{FINGER_SHARE[2]:g}), additive on the clip
 UPROPERTY(Transient) FVector StreamerVisualV23DeskForward=FVector::ZeroVector; // the keyboard's forward axis, component space (zero = none: his own facing)
 UPROPERTY(Transient) float StreamerVisualV23KeyPlaneZ=0; // the keyboard top, component Z
 UPROPERTY(Transient) bool StreamerVisualV23KeyPlaneValid=false;
'''
                + ''.join(f' UPROPERTY(Transient) float StreamerVisualV23{name}={value};' + (f' // published: {note}' if note else '') + '\n' for name, value, note in _PUBLISHED)
                + ' // SUB01_STREAMER_VISUAL_V2_V23 END\n')

# ------------------------------------------------------------------------------------------------ Sub01HomeHands.cpp
PROXY_STREAM_END = ' // SUB01_STREAMER_VISUAL_V2_STREAMPASS END\n'
_TIP_NAMES = ','.join('{' + ','.join(f'TEXT("{side}Hand{finger}4")' for finger in streampass.FINGERS) + '}' for side in ('Left', 'Right'))
PROXY_MEMBERS = f''' // SUB01_STREAMER_VISUAL_V2_V23 BEGIN (tools/native_streamer_visual_v2/install_v23.py): live look corrections. Every step returns at once at its
 // default (the v21 pose, bit-identical); the measurements only read the pose. His frame as the pose fix: Right from the thighs, Up = component Z,
 // Forward = Right x Up; the hands use the KEYBOARD's forward axis when the character sends one. Every turn is a component-space rotation about the
 // bone's own pivot (StreamerV2Turn), never a guessed local axis.
 float StreamerV23Pelvis=0,StreamerV23ShoulderDrop=0,StreamerV23ShoulderBack=0,StreamerV23NeckBack=0,StreamerV23NeckShare={_f(NECK_SHARE_V21[0])},StreamerV23NeckGirth=1;
 float StreamerV23ElbowMin=0,StreamerV23HandOrient=0,StreamerV23HandYawIn={_f(DEFAULTS['hand_yaw_in_deg'])},StreamerV23HandPitch={_f(DEFAULTS['hand_pitch_deg'])},StreamerV23FingerBend=0,StreamerV23KeyPlaneZ=0;
 FVector StreamerV23DeskForward=FVector::ZeroVector,StreamerV23Effective[2]={{FVector::ZeroVector,FVector::ZeroVector}};bool StreamerV23KeyPlaneValid=false;
 float StreamerV23Slide[2]={{0,0}},StreamerV23Residual[2]={{-1,-1}},StreamerV23ElbowBack[2]={{0,0}},StreamerV23OrientErr[2]={{-1,-1}},StreamerV23TipMean[2]={{-99,-99}},StreamerV23TipMin[2]={{-99,-99}},StreamerV23Incline=0,StreamerV23HeadAhead=0,StreamerV23NeckAlign=-1;
 int32 StreamerV23Clavicles[2]={{INDEX_NONE,INDEX_NONE}},StreamerV23Tips[2][4]={{{{INDEX_NONE,INDEX_NONE,INDEX_NONE,INDEX_NONE}},{{INDEX_NONE,INDEX_NONE,INDEX_NONE,INDEX_NONE}}}},StreamerV23BoneCount=-1;const FReferenceSkeleton* StreamerV23Ref=nullptr;
 void ResolveStreamerV23(const FReferenceSkeleton& Ref){{ // clavicles and fingertip end bones, once per skeleton (exact name, else a name ending with it)
  if(StreamerV23Ref==&Ref&&StreamerV23BoneCount==Ref.GetNum())return;StreamerV23Ref=&Ref;StreamerV23BoneCount=Ref.GetNum();
  auto Find=[&Ref](const TCHAR* Name){{int32 Index=Ref.FindBoneIndex(FName(Name));for(int32 B=0;Index==INDEX_NONE&&B<Ref.GetNum();++B)if(Ref.GetBoneName(B).ToString().EndsWith(Name))Index=B;return Index;}};
  static const TCHAR* const Clavicles[2]={{TEXT("LeftShoulder"),TEXT("RightShoulder")}};static const TCHAR* const Tips[2][4]={{{_TIP_NAMES}}};
  for(int32 S=0;S<2;++S){{StreamerV23Clavicles[S]=Find(Clavicles[S]);for(int32 G=0;G<4;++G)StreamerV23Tips[S][G]=Find(Tips[S][G]);}}
 }}
 FVector StreamerV23Ahead() const {{ // the keyboard's forward axis (level), else his own facing; zero when neither is known yet
  FVector Ahead=StreamerV23DeskForward;Ahead.Z=0;if(Ahead.Size()<.5){{Ahead=FVector::CrossProduct(StreamerV2BodyRight,FVector::UpVector);Ahead.Z=0;}}return Ahead.GetSafeNormal();
 }}
 void ApplyStreamerV23Pelvis(FPoseContext& Output){{ // hip hinge before the lean: Hips about his lateral axis (+ = forward, like the lean), each thigh turned back about its own pivot
  if(FMath::Abs(StreamerV23Pelvis)<1e-3f)return;auto& Pose=Output.Pose;ResolveStreamerV2Pose(Pose.GetBoneContainer().GetReferenceSkeleton());
  const FQuat Hinge(StreamerV2Right(Pose),FMath::DegreesToRadians(double(StreamerV23Pelvis)));
  StreamerV2Turn(Pose,StreamerV2PoseBones[0],Hinge);StreamerV2Turn(Pose,StreamerV2PoseBones[6],Hinge.Inverse());StreamerV2Turn(Pose,StreamerV2PoseBones[7],Hinge.Inverse());
 }}
 void ApplyStreamerV23Shoulders(FPoseContext& Output){{ // after the lean, before the IK: each clavicle turned down (about his forward axis) and back (about the vertical)
  if(FMath::Abs(StreamerV23ShoulderDrop)<1e-3f&&FMath::Abs(StreamerV23ShoulderBack)<1e-3f)return;auto& Pose=Output.Pose;ResolveStreamerV23(Pose.GetBoneContainer().GetReferenceSkeleton());
  const FVector Right=StreamerV2Right(Pose),Forward=FVector::CrossProduct(Right,FVector::UpVector);
  for(int32 S=0;S<2;++S){{const FVector Outward=S?Right:Right*-1.; // the clavicle points outwards: a turn about Outward x -Up lowers it, about Outward x -Forward retracts it
   const FQuat Drop(FVector::CrossProduct(Outward,FVector::UpVector*-1.),FMath::DegreesToRadians(double(StreamerV23ShoulderDrop))),Retract(FVector::CrossProduct(Outward,Forward*-1.),FMath::DegreesToRadians(double(StreamerV23ShoulderBack)));
   StreamerV2Turn(Pose,StreamerV23Clavicles[S],(Retract*Drop).GetNormalized());}}
 }}
 FVector StreamerV23Target(int32 S,const FVector& A,const FVector& B,const FVector& C){{
  // elbow_min_deg (a guard): if the wrist target would close the elbow tighter than the minimum, it slides FORWARD along the keyboard axis at the same height
  // until the shoulder-to-target distance gives that interior angle (law of cosines), at most {SLIDE_MAX_CM:g} cm; never down into the desk. Off (0): the target as sent.
  // A target BEHIND the shoulder along the keyboard axis is declined (published -1): the forward root would start at 2|Bq| at once, a visible jump.
  // Within {SLIDE_RAMP_CM:g} cm ahead of the shoulder the slide is scaled by Bq/{SLIDE_RAMP_CM:g}, so a target crossing the shoulder line moves continuously.
  StreamerV23Slide[S]=0;StreamerV23Effective[S]=StreamerV2HandTarget[S];if(StreamerV23ElbowMin<=0)return StreamerV23Effective[S];
  const double L1=(B-A).Size(),L2=(C-B).Size(),CosMin=FMath::Cos(FMath::DegreesToRadians(double(FMath::Min(StreamerV23ElbowMin,179.f))));
  const double Reach=FMath::Sqrt(FMath::Max(0.,L1*L1+L2*L2-2*L1*L2*CosMin));const FVector Ahead=StreamerV23Ahead();
  if(Ahead.IsNearlyZero())return StreamerV23Effective[S];const FVector V=StreamerV2HandTarget[S]-A;const double Cq=FVector::DotProduct(V,V)-Reach*Reach;if(Cq>=0)return StreamerV23Effective[S];
  const double Bq=FVector::DotProduct(Ahead,V);if(Bq<0){{StreamerV23Slide[S]=-1;return StreamerV23Effective[S];}}
  const double Slide=FMath::Clamp(-Bq+FMath::Sqrt(FMath::Max(0.,Bq*Bq-Cq)),0.,{_d(SLIDE_MAX_CM)})*FMath::Min(1.,Bq/{_d(SLIDE_RAMP_CM)});
  StreamerV23Slide[S]=float(Slide);StreamerV23Effective[S]=StreamerV2HandTarget[S]+Ahead*Slide;return StreamerV23Effective[S];
 }}
 bool StreamerV23HandFrame(const FCompactPose& Pose,int32 S,int32 H,FVector& Fingers,FVector& Across) const {{ // Hand->Middle1 and Index1->Pinky1 (orthogonalised)
  FTransform Th,Ti,Tm,Tp;if(!StreamerV2ComponentTransform(Pose,H,Th)||!StreamerV2ComponentTransform(Pose,StreamerV2FingerBones[S][0][0],Ti)||!StreamerV2ComponentTransform(Pose,StreamerV2FingerBones[S][1][0],Tm)
   ||!StreamerV2ComponentTransform(Pose,StreamerV2FingerBones[S][3][0],Tp))return false;
  Fingers=(Tm.GetTranslation()-Th.GetTranslation()).GetSafeNormal();Across=Tp.GetTranslation()-Ti.GetTranslation();Across=(Across-Fingers*FVector::DotProduct(Across,Fingers)).GetSafeNormal();
  return !Fingers.IsNearlyZero()&&!Across.IsNearlyZero();
 }}
 void ApplyStreamerV23Hand(FCompactPose& Pose,int32 S,int32 H){{
  // hand_orient: the hand turned about the wrist so the fingers follow the keyboard axis (yawed in, pitched down) with the knuckle line level and the pinky
  // outward (palm down by handedness); finger_bend_deg: index..pinky towards the palm side found from the same geometry. Positions only, no local axes.
  StreamerV23OrientErr[S]=-1;if(StreamerV23HandOrient<=0&&StreamerV23FingerBend<=0)return;const FVector Forward=StreamerV23Ahead();if(Forward.IsNearlyZero())return;
  FVector Fingers,Across;if(!StreamerV23HandFrame(Pose,S,H,Fingers,Across))return;
  const FVector Right=FVector::CrossProduct(FVector::UpVector,Forward),Outward=S?Right:Right*-1.; // Up x Forward = his right (Forward = Right x Up)
  const double Yaw=FMath::DegreesToRadians(double(StreamerV23HandYawIn)),Pitch=FMath::DegreesToRadians(double(StreamerV23HandPitch));
  const FVector Flat=Forward*FMath::Cos(Yaw)-Outward*FMath::Sin(Yaw),WantAcross=Outward*FMath::Cos(Yaw)+Forward*FMath::Sin(Yaw);
  const FVector WantFingers=(Flat*FMath::Cos(Pitch)-FVector::UpVector*FMath::Sin(Pitch)).GetSafeNormal();
  if(StreamerV23HandOrient>0){{
   const FQuat Aim=FQuat::FindBetweenNormals(Fingers,WantFingers);const FVector Turned=Aim.RotateVector(Across);
   const FVector Have=(Turned-WantFingers*FVector::DotProduct(Turned,WantFingers)).GetSafeNormal(),Want=(WantAcross-WantFingers*FVector::DotProduct(WantAcross,WantFingers)).GetSafeNormal();
   const FQuat Roll=FVector::DotProduct(Have,Want)<-.9999?FQuat(WantFingers,FMath::DegreesToRadians(180.)):FQuat::FindBetweenNormals(Have,Want);
   StreamerV2Turn(Pose,H,FQuat::Slerp(FQuat::Identity,(Roll*Aim).GetNormalized(),FMath::Clamp(double(StreamerV23HandOrient)*double(StreamerV2HandAlpha),0.,1.)));
   if(StreamerV23HandFrame(Pose,S,H,Fingers,Across))StreamerV23OrientErr[S]=float(StreamerV2AngleDeg(Fingers,WantFingers));
  }}
  if(StreamerV23FingerBend>0){{
   const FVector Normal=FVector::CrossProduct(Fingers,Across),Palm=(S?Normal*-1.:Normal).GetSafeNormal(),Axis=FVector::CrossProduct(Fingers,Palm).GetSafeNormal(); // +turn about Axis: fingers towards the palm
   static const double Share[3]={{{FINGER_SHARE[0]:g},{FINGER_SHARE[1]:g},{FINGER_SHARE[2]:g}}};
   if(!Axis.IsNearlyZero())for(int32 G=0;G<4;++G)for(int32 K=0;K<3;++K)StreamerV2Turn(Pose,StreamerV2FingerBones[S][G][K],FQuat(Axis,FMath::DegreesToRadians(double(StreamerV23FingerBend)*Share[K]*double(StreamerV2HandAlpha))));
  }}
 }}
 void MeasureStreamerV23Hand(const FCompactPose& Pose,int32 S,int32 U,int32 F,int32 H){{ // published only: residual to the (slid) target, elbow behind the shoulder, fingertips above the keys
  FTransform Tu,Tf,Th;if(!StreamerV2ComponentTransform(Pose,U,Tu)||!StreamerV2ComponentTransform(Pose,F,Tf)||!StreamerV2ComponentTransform(Pose,H,Th))return;
  StreamerV23Residual[S]=float(FVector::Dist(Th.GetTranslation(),StreamerV23Effective[S]));const FVector Ahead=StreamerV23Ahead();
  StreamerV23ElbowBack[S]=Ahead.IsNearlyZero()?0.f:float(-FVector::DotProduct(Tf.GetTranslation()-Tu.GetTranslation(),Ahead));
  if(!StreamerV23KeyPlaneValid)return;ResolveStreamerV23(Pose.GetBoneContainer().GetReferenceSkeleton());double Sum=0,Low=1e9;int32 Count=0;
  for(int32 G=0;G<4;++G){{FTransform Tip,T2,T3;FVector At;
   if(StreamerV23Tips[S][G]!=INDEX_NONE&&StreamerV2ComponentTransform(Pose,StreamerV23Tips[S][G],Tip))At=Tip.GetTranslation(); // the *4 end bone
   else if(StreamerV2ComponentTransform(Pose,StreamerV2FingerBones[S][G][1],T2)&&StreamerV2ComponentTransform(Pose,StreamerV2FingerBones[S][G][2],T3))At=T3.GetTranslation()+(T3.GetTranslation()-T2.GetTranslation())*{TIP_EXTEND:g};
   else continue;
   const double Above=At.Z-double(StreamerV23KeyPlaneZ);Sum+=Above;Low=FMath::Min(Low,Above);++Count;}}
  if(Count){{StreamerV23TipMean[S]=float(Sum/Count);StreamerV23TipMin[S]=float(Low);}}
 }}
 void ApplyStreamerV23Head(FPoseContext& Output){{ // after the head channel: chin tuck, neck girth, then the posture measurements (measure only)
  auto& Pose=Output.Pose;const auto& Bones=Pose.GetBoneContainer();const auto& Ref=Bones.GetReferenceSkeleton();ResolveStreamerV2Pose(Ref);
  const int32 NeckBone=StreamerV2PoseBones[4],HeadBone=StreamerV2PoseBones[5];
  if(FMath::Abs(StreamerV23NeckBack)>=1e-3f&&NeckBone!=INDEX_NONE&&HeadBone!=INDEX_NONE){{ // the neck back (nose-up sense), the head forward: the head moves back, the face keeps its angle
   const FQuat Tuck(StreamerV2Right(Pose),FMath::DegreesToRadians(-double(StreamerV23NeckBack)));StreamerV2Turn(Pose,NeckBone,Tuck);StreamerV2Turn(Pose,HeadBone,Tuck.Inverse());}}
  if(StreamerV23NeckGirth!=1.f&&NeckBone!=INDEX_NONE){{const auto CN=Bones.MakeCompactPoseIndex(FMeshPoseBoneIndex(NeckBone));
   FVector Along=FVector::ZeroVector;for(int32 B=0;B<Ref.GetNum()&&Along.IsNearlyZero();++B)if(Ref.GetParentIndex(B)==NeckBone){{const auto CB=Bones.MakeCompactPoseIndex(FMeshPoseBoneIndex(B));if(CB.GetInt()>=0)Along=Pose[CB].GetTranslation();}}
   if(CN.GetInt()>=0&&!Along.IsNearlyZero()){{ // the long axis = the child's offset in the Neck frame; the other two scaled, every child given the exact inverse
    const int32 Long=FMath::Abs(Along.X)>=FMath::Abs(Along.Y)&&FMath::Abs(Along.X)>=FMath::Abs(Along.Z)?0:(FMath::Abs(Along.Y)>=FMath::Abs(Along.Z)?1:2);const double Girth=double(StreamerV23NeckGirth);
    StreamerV23NeckAlign=float(FMath::Abs(Long==0?Along.X:(Long==1?Along.Y:Along.Z))/Along.Size()); // 1 = the offset lies on one local axis; a diagonal offset would shear
    if(StreamerV23NeckAlign>={_f(NECK_AXIS_MIN)}){{const FVector Swell(Long==0?1.:Girth,Long==1?1.:Girth,Long==2?1.:Girth),Undo(1./Swell.X,1./Swell.Y,1./Swell.Z);Pose[CN].SetScale3D(Pose[CN].GetScale3D()*Swell);
     for(int32 B=0;B<Ref.GetNum();++B)if(Ref.GetParentIndex(B)==NeckBone){{const auto CB=Bones.MakeCompactPoseIndex(FMeshPoseBoneIndex(B));if(CB.GetInt()<0)continue;
      Pose[CB].SetScale3D(Pose[CB].GetScale3D()*Undo);Pose[CB].SetTranslation(Pose[CB].GetTranslation()*Undo);}}}}}}}}
  FTransform Hp,Hd,La,Ra;const FVector Forward=FVector::CrossProduct(StreamerV2BodyRight,FVector::UpVector);
  if(StreamerV2ComponentTransform(Pose,StreamerV2PoseBones[0],Hp)&&StreamerV2ComponentTransform(Pose,HeadBone,Hd)){{StreamerV23Incline=float(StreamerV2Incline(Hd.GetTranslation()-Hp.GetTranslation(),Forward));
   if(StreamerV2ComponentTransform(Pose,StreamerV2ArmBones[0][0],La)&&StreamerV2ComponentTransform(Pose,StreamerV2ArmBones[1][0],Ra))StreamerV23HeadAhead=float(FVector::DotProduct(Hd.GetTranslation()-(La.GetTranslation()+Ra.GetTranslation())*.5,Forward));}}
 }}
 // SUB01_STREAMER_VISUAL_V2_V23 END
'''
_COPY_FIELDS = ['StreamerV23Pelvis', 'StreamerV23ShoulderDrop', 'StreamerV23ShoulderBack', 'StreamerV23NeckBack', 'StreamerV23NeckShare', 'StreamerV23NeckGirth',
                'StreamerV23ElbowMin', 'StreamerV23HandOrient', 'StreamerV23HandYawIn', 'StreamerV23HandPitch', 'StreamerV23FingerBend']
PROXY_COPY = '  StreamerV2LeanCmd=Hands->StreamerVisualLeanDeg;StreamerV2LoopFadeSeconds=Hands->StreamerVisualLoopFadeSeconds; // SUB01_STREAMER_VISUAL_V2_POSEFIX\n'
PROXY_COPY_V23 = (PROXY_COPY + '  ' + ''.join(f'{p}=Hands->{a};' for p, a in zip(_COPY_FIELDS, _ANIM_FIELDS)) + ' // SUB01_STREAMER_VISUAL_V2_V23\n'
                  '  StreamerV23DeskForward=Hands->StreamerVisualV23DeskForward;StreamerV23KeyPlaneZ=Hands->StreamerVisualV23KeyPlaneZ;StreamerV23KeyPlaneValid=Hands->StreamerVisualV23KeyPlaneValid;'
                  'for(int32 S=0;S<2;++S){StreamerV23Residual[S]=StreamerV23OrientErr[S]=-1;StreamerV23TipMean[S]=StreamerV23TipMin[S]=-99;StreamerV23ElbowBack[S]=StreamerV23Slide[S]=0;}StreamerV23NeckAlign=-1;\n')
PROXY_BODY = '  ApplyStreamerV2Body(Output); // SUB01_STREAMER_VISUAL_V2_POSEFIX: lean + breathing about his lateral axis (FRotator pitch twisted these bones)\n'
PROXY_BODY_V23 = ('  ApplyStreamerV23Pelvis(Output); // SUB01_STREAMER_VISUAL_V2_V23: the hip hinge first (the lean then measures only its own turn)\n'
                  + PROXY_BODY + '  ApplyStreamerV23Shoulders(Output); // SUB01_STREAMER_VISUAL_V2_V23: clavicles, before the IK re-plants the hands\n')
PROXY_WEIGHTS = '  const bool Neck=StreamerV2PoseBones[4]!=INDEX_NONE;static const double Weights[2]={0.4,0.6};\n'
PROXY_WEIGHTS_V23 = (f'  const bool Neck=StreamerV2PoseBones[4]!=INDEX_NONE;const bool Shared=StreamerV23NeckShare!={_f(NECK_SHARE_V21[0])}; // SUB01_STREAMER_VISUAL_V2_V23: neck_share\n'
                     f'  const double Weights[2]={{Shared?double(StreamerV23NeckShare):{NECK_SHARE_V21[0]:g},Shared?1.-double(StreamerV23NeckShare):{NECK_SHARE_V21[1]:g}}};\n')
PROXY_HEAD = '   ApplyStreamerV2Head(Output); // SUB01_STREAMER_VISUAL_V2_POSEFIX: gaze/nod/posture pitch and yaw about his axes, over Neck and Head\n'
PROXY_HEAD_V23 = PROXY_HEAD + '   if(StreamerV2)ApplyStreamerV23Head(Output); // SUB01_STREAMER_VISUAL_V2_V23: chin tuck, neck girth, posture measurements\n'
PROXY_SOLVE = ('   if(!StreamerV2SolveTwoBone(A,B,C,StreamerV2HandTarget[S],NB,NC,StreamerV2HandPole[S],FMath::Clamp(double(StreamerV2ElbowPole),0.,1.),'
               '&StreamerV2LastBend[S]))continue;\n')
PROXY_SOLVE_V23 = ('   const FVector Reached=StreamerV23Target(S,A,B,C); // SUB01_STREAMER_VISUAL_V2_V23: elbow_min_deg slides the target forward\n'
                   '   if(!StreamerV2SolveTwoBone(A,B,C,Reached,NB,NC,StreamerV2HandPole[S],FMath::Clamp(double(StreamerV2ElbowPole),0.,1.),&StreamerV2LastBend[S]))continue;\n')
PROXY_CURL = '   // finger curl (optional, additive on the clip) about the local axis, then the measured flexion (mean of the fingers found)\n'
PROXY_CURL_V23 = '   ApplyStreamerV23Hand(Output.Pose,S,H); // SUB01_STREAMER_VISUAL_V2_V23: hand orientation and finger bend from bone positions\n' + PROXY_CURL
PROXY_FLEX = '   StreamerV2FingerFlex[S][0]=Count?float(Mcp/Count):-1.f;StreamerV2FingerFlex[S][1]=Count?float(Pip/Count):-1.f;\n'
PROXY_FLEX_V23 = PROXY_FLEX + '   MeasureStreamerV23Hand(Output.Pose,S,U,F,H); // SUB01_STREAMER_VISUAL_V2_V23: residual, elbow behind the shoulder, fingertips above the keys\n'
PROXY_PUBLISH = (' StreamerVisualSeatPivot=Proxy.StreamerV2PinPelvis.GetTranslation();StreamerVisualLeanMeasuredDeg=Proxy.StreamerV2LeanMeasured;StreamerVisualLeanGain=Proxy.StreamerV2LeanGain;'
                 'StreamerVisualLoopSeams=Proxy.StreamerV2Seams;StreamerVisualBodyRight=Proxy.StreamerV2BodyRight; // SUB01_STREAMER_VISUAL_V2_POSEFIX\n')
_PUBLISH_FROM = {'InclineDeg': 'StreamerV23Incline', 'HeadAheadCm': 'StreamerV23HeadAhead', 'SlideLeftCm': 'StreamerV23Slide[0]', 'SlideRightCm': 'StreamerV23Slide[1]',
                 'ResidualLeftCm': 'StreamerV23Residual[0]', 'ResidualRightCm': 'StreamerV23Residual[1]', 'ElbowBackLeftCm': 'StreamerV23ElbowBack[0]',
                 'ElbowBackRightCm': 'StreamerV23ElbowBack[1]', 'OrientErrLeftDeg': 'StreamerV23OrientErr[0]', 'OrientErrRightDeg': 'StreamerV23OrientErr[1]',
                 'TipMeanLeftCm': 'StreamerV23TipMean[0]', 'TipMeanRightCm': 'StreamerV23TipMean[1]', 'TipMinLeftCm': 'StreamerV23TipMin[0]', 'TipMinRightCm': 'StreamerV23TipMin[1]',
                 'NeckAxisAlign': 'StreamerV23NeckAlign'}
assert set(_PUBLISH_FROM) == {name for name, _, _ in _PUBLISHED}
PROXY_PUBLISH_V23 = PROXY_PUBLISH + (' ' + ''.join(f'StreamerVisualV23{name}=Proxy.{_PUBLISH_FROM[name]};' for name, _, _ in _PUBLISHED) + ' // SUB01_STREAMER_VISUAL_V2_V23\n')

EDITS = [
    ('header', HEADER_V21_END, HEADER_V21_END + HEADER_FIELDS),
    ('cpp', CPP_V21_END, CPP_V21_END + CPP_METHODS),
    ('cpp', TUNING_LAMBDA, TUNING_BLOCK),
    ('cpp', TICK_POSE, TICK_V23),
    ('cpp', CHAIR_DELTA, CHAIR_DELTA_V23),
    ('cpp', FIT_GAP, FIT_GAP_V23),
    ('cpp', MOVE_CHAIR, MOVE_CHAIR_V23),
    ('cpp', GATE_CHAIR, GATE_CHAIR_V23),
    ('cpp', HANDS_STATE, HANDS_STATE_V23),
    ('cpp', HANDS_GOAL_TAIL, HANDS_GOAL_TAIL_V23),
    ('cpp', HANDS_NAME, HANDS_NAME_V23),
    ('cpp', RECEIPT_ANCHOR, RECEIPT_V23),
    ('hands_header', HANDS_POSE_END, HANDS_POSE_END + HANDS_FIELDS),
    ('hands_cpp', PROXY_STREAM_END, PROXY_STREAM_END + PROXY_MEMBERS),
    ('hands_cpp', PROXY_COPY, PROXY_COPY_V23),
    ('hands_cpp', PROXY_BODY, PROXY_BODY_V23),
    ('hands_cpp', PROXY_WEIGHTS, PROXY_WEIGHTS_V23),
    ('hands_cpp', PROXY_HEAD, PROXY_HEAD_V23),
    ('hands_cpp', PROXY_SOLVE, PROXY_SOLVE_V23),
    ('hands_cpp', PROXY_CURL, PROXY_CURL_V23),
    ('hands_cpp', PROXY_FLEX, PROXY_FLEX_V23),
    ('hands_cpp', PROXY_PUBLISH, PROXY_PUBLISH_V23),
]
# Anchors another layer could also edit (reported for the merge with v22): the shared tuning reader's lambda line, the receipt line and the
# header/methods insertion points right after v21's END markers (v22 may insert there too; the anchors survive such an insertion).
SHARED_ANCHORS = {'tuning_reader': TUNING_LAMBDA.strip(), 'receipt': RECEIPT_ANCHOR.strip(), 'header_after': HEADER_V21_END.strip(), 'methods_after': CPP_V21_END.strip()}
V22_FILES = ('Sub01PCBridge.h', 'Sub01PCBridge.cpp', 'Sub01HomeDeviceBridge.h', 'Sub01HomeDeviceBridge.cpp', 'Sub01PersistentTexture.h')
assert not set(V22_FILES) & set(FILES.values())


def plan(sources: dict) -> dict:
    """Pure transformation of the four LF texts; raises Refused, never partial."""
    problems = [f'{FILES[key]} already carries {MARKER} (v23 already installed)' for key in FILES if MARKER in sources[key]]
    if problems:
        raise Refused('; '.join(problems))
    needs = (('header', v21.MARKER, 'v21'), ('cpp', v21.MARKER, 'v21'), ('header', V22_MARKER, 'v22'), ('cpp', V22_MARKER, 'v22'), ('hands_header', posefix.MARKER, 'the pose fix'), ('hands_cpp', posefix.MARKER, 'the pose fix'),
             ('hands_cpp', streampass.MARKER, 'the stream pass'))
    problems = [f'{FILES[key]} lacks {name} ({marker}); run the stack up to v22 first' for key, marker, name in needs if marker + ' BEGIN' not in sources[key]]
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
    result = plan({key: text.replace('\r\n', '\n') for key, text in raw.items()})
    after = {key: result['sources'][key].replace('\n', eol[key]) for key in FILES}
    report = {'schema': SCHEMA, 'source': str(source), 'dry_run': dry_run, 'marker': MARKER,
              'requires': [V22_MARKER, v21.MARKER, posefix.MARKER, cam2.MARKER, streampass.MARKER, seatfix.MARKER, v2.MARKER],
              'tuning': {key: {'field': field, 'min': lo, 'max': hi, 'default': default} for key, field, lo, hi, default in TUNING},
              'session': [{'step': step, 'set': values} for step, values in RECOMMENDED],
              'eases': {'posture_deg_s': POSTURE_RATE, 'hands_deg_s': HAND_RATE, 'weights_per_s': WEIGHT_RATE, 'girth_per_s': GIRTH_RATE,
                        'chair_cm_s': CHAIR_RATE_CM_S, 'chair_scale_per_s': CHAIR_SCALE_RATE, 'light_cm_s': LIGHT_MOVE_CM_S, 'light_cd_per_s': LIGHT_CD_RATE,
                        'mouse_cm_s': MOUSE_MOVE_CM_S},
              'neck_axis_min': NECK_AXIS_MIN,
              'finger_share': list(FINGER_SHARE), 'slide_max_cm': SLIDE_MAX_CM, 'slide_ramp_cm': SLIDE_RAMP_CM,'fill_cones_deg': list(FILL_CONES), 'rim_cones_deg': list(RIM_CONES),
              'mouth': MOUTH_NOTE, 'shared_anchors': SHARED_ANCHORS, 'untouched': list(V22_FILES), 'edits': result['edits'],
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
    parser.add_argument('--source', type=Path, required=True, help='directory with the v21 (or v22) pod files (patched in place)')
    parser.add_argument('--dry-run', action='store_true', help='check every anchor and print the report; write nothing')
    args = parser.parse_args(argv)
    try:
        report = run(args.source, args.dry_run)
    except Refused as error:
        print(json.dumps({'schema': SCHEMA, 'source': str(args.source), 'dry_run': args.dry_run, 'status': 'refused', 'reason': str(error)}, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
