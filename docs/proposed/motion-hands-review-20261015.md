# First-person motion and hands review (origin/main 4eb8e90, 2026-10-15)

Source review only. Nothing was rendered, imported or run on the server. The numbers come from the
source constants and from offline checks: pure-Python FK over the repo GLBs with
`tools/animation_rig_audit.py`, `tools/animation_rig_dump.mjs` and `report --step 10`, plus small
numeric simulations of the shipped formulas. Items marked *geometric* still need a native capture to
confirm.

Code reviewed: `tools/unreal_first_person_motion.py` (662e102, b54ae82, f4d2de8),
`tools/unreal_home_hands_runtime.py`, `tools/stage_unreal_home_runtime.py`,
`tools/unreal_live_home_runtime.py`, `tools/unreal_seat_transition_runtime.py`,
`tools/unreal_contact_profile_runtime.py`, `tools/unreal_hands_diagnostic.py`,
`tools/unreal_controller_grip_diagnostic.py` and, on the Claude branch,
`tools/unreal_controller_play_runtime.py`.

## Ranked issues

| # | Severity | What the player sees | Evidence |
|---|---|---|---|
| 1 | **Blocker (PC typing)** | On main, the seat, sit, type and stand integration cannot be staged at all, so there is no desk typing. | 662e102 rewrote `FMath::Clamp(Speed/140.f,.1f,1.2f)` to `AuthoredWalkRate(Speed)`. `unreal_seat_transition_runtime.py:398` still anchors on the old text, so `install_module()` raises `Seat integration anchor not unique`. On origin/main, 4 seat tests error. The Claude branch already re-anchors (`SEAT_RATE_ANCHOR`, line 733) but is not merged. |
| 2 | High (desk, sofa) | Seated views (desk and controller) come from the Head joint, not the eyes. The monitor or TV is seen from mouth/chin height. | `SnapToTargetNotIncludingScale, Head` puts the camera on the joint: main seat `:326`, branch `:671`, controller play `:409`. In owner.glb the Head joint is at y=145.3, z=0.1 cm. The face front is at z≈14 and the eye line at ≈161–163 cm, so the camera is ~16–17 cm low and ~11 cm back. The natively measured iris midpoint is (0.12, −13.38, 12.63) cm in Head space, |18.4| cm (`unreal_controller_grip_diagnostic.py`). |
| 3 | High (desk, sofa) | The view teleports in one frame when sitting starts or play begins, and again when standing or play ends. | The camera jumps from the capsule eye (capsule-relative (0,0,74), 165 cm above the feet) to the Head joint. At the start of StandToSit the joint is ~141–145 cm, a ~20–24 cm drop in one frame. Controller play has no sit clip, so the body and camera drop all the way to the seated head in one frame. Ending sets `SetRelativeLocation(0,0,74)` immediately. |
| 4 | High (standing; depends on config) | Standing or walking, the camera can sit inside the owner's own head. | The camera is on the capsule axis at 165 cm. At that height the owner head spans z −8.2…+14.1 and x −8.6…+11.5 cm (60,118 head/neck bind vertices), so the camera is inside it. The face surface is 14 cm ahead, beyond the 10 cm default near plane. The `owner_head` material is **doubleSided**. Runtime hides only `HiddenHeadBones`, which is empty by default. Nothing in the repo sets it: `unreal_hands_bindings.native_config()` and `install_default_game_ini.py` never write it. Only the diagnostics hide `*Head`. Check the live `DefaultGame.ini`. |
| 5 | Medium-high (keyboard and controller play) | Strafing slides the feet; backpedalling moonwalks. | The body follows control yaw, and the only walk clip is forward-only and in place. The rate is `|v|/140`, whatever the direction. Foot slip vs ground: strafe 198 cm/s, 45° 107 cm/s, back 280 cm/s. |
| 6 | Medium (Live autopilot) | The body crab-walks through every route corner. | Movement input follows `Delta` immediately, while the body yaw (`bUseControllerRotationYaw`) follows `SmoothAngle` (exp 8/s, cap 180°/s). Simulated 90° corner: 0.77 s to settle within 1°, 52–55 cm of integrated foot slip, peak 187–196 cm/s. The same at 30/60/144/240 fps. |
| 7 | Medium | The pose pops when the Walk/Idle target changes again inside the 0.24 s blend (W tap, stop-start, brushing a wall). | In `FSub01HandsProxy::PreUpdate`, every target change sets `Previous=Current` and `Progress=0`. The rendered pose jumps from `(1-p)·A+p·B` to pure `B`, a pop of `(1-p)` of the A–B difference. |
| 8 | Medium (*geometric*) | Looking down shows a hollow neck stump. Forearms and hands pass through doorframes, walls and the desk edge. | Capsule radius 16 cm. In the walk clip, the forearms and hands reach x = ±31…34 cm sideways and up to z = 47 cm forward (fingertips 57 cm). Pitch is unlimited (UE default ±89.9°). With FOV 75 at 16:9 (vertical 46.7°), the hidden-head neck opening 20 cm below the camera enters the frame from about 38° of pitch down. |
| 9 | Low | Standing still with no bound Idle freezes the walk at a random stride. | `AuthoredWalkRate` has no floor (by design), so the rate reaches 0 mid-stride. `validate_bindings()` has no `Idle` role. Only the branch's `install_default_game_ini.py` binds Idle. |
| 10 | Low (CI) | — | 2 stale tests on main still assert the retired sway (`FirstPersonBody->GetAttachParent()==ViewCamera`, `if(Moving)WalkPhase+=`). |

## Checked and not a problem

- **Walk rate against the stride matches.** `walking.glb` is in place: hips peak-to-peak 5.6/7.0/5.3 cm, cycle 0.93–1.03 s at 30 fps. The stance foot moves relative to the hips at 141.6 cm/s (left) and 131.1 cm/s (right) at rate 1. That matches the 140 cm/s reference and `MaxWalkSpeed=140`, with no forward foot sliding. Rate follows braking, and `AuthoredWalkRate` clamps [0, 1.2].
- **`SmoothAngle` is frame-rate independent.** It uses `1-exp(-8·dt)` with a 180°/s cap. A 90° turn settles in 0.767 s at 30 fps and 0.771 s at 144 fps. There is no overshoot even at dt = 0.5 s. Pitch and roll wrap correctly through `remainder`.
- **Hands blend is linear in time** (`dt/0.24`, dt capped at 0.1 s), so it is frame-rate independent.
- **Loop flag after non-looping seat clips is fine.** It is reset on every sequence change (`SEQUENCE_START` in the contact profile runtime).
- **Fingers.** `animation_rig_audit report`: with `typing.glb` (3–8 s), no finger flexes past the anatomical limits. The exceptions are the thumbs: right thumb MCP −18.6° and IP −13.4° (100% of frames past the audit's −5°/−10°), and left IP −15° (91%). That is mild thumb hyperextension, which is within passive range, so not gross. Index MCP briefly reaches −26° (4%). Texting PIP is 94–107° in the phone-grip fist, under 110°.
- **Typing head motion.** In the profile window the head moves 4.7 cm sideways and 7.2 cm fore-aft (p95 15 cm/s). That is natural.

## Fixes

### Applied (Claude-owned): controller play eye camera (#2, #3 for the sofa)

Changes in `tools/unreal_controller_play_runtime.py`; tests in `tests/test_controller_play_eye_camera.py`.

- The camera is no longer snapped to the Head joint. Each tick it targets the Head socket plus the measured iris offset, applied only for `SUB01_OriginalOwner`; any other skin falls back to the joint.
- The camera position is world-absolute and eases with `1-exp(-10·min(dt,.1))`. It reaches 95% in 0.30 s at 30, 60, 144 and 240 fps, with no overshoot. The first 30 fps frame moves at most 29% of the old one-frame drop.
- On end, the camera eases back to the standing eye and is handed back to the capsule (0,0,74) once within 0.5 cm.

### Root patches (not applied; the files are CN-owned)

**P1 (#1)** `tools/unreal_seat_transition_runtime.py` on main. Verified: all seat, first-person and idle tests pass in a main worktree.

```diff
-    ('cpp', 'Instance->TargetRate=HandsPosture==TEXT("Walk")?(Moving?FMath::Clamp(Speed/140.f,.1f,1.2f):(PlayingIdle?1.f:0.f)):1.f;\n',
-     'Instance->TargetRate=HandsPosture==TEXT("Walk")?(Moving?FMath::Clamp(Speed/140.f,.1f,1.2f):(PlayingIdle?1.f:0.f)):1.f;\n ApplySeatAnimation(Instance);\n'),
+    # Anchor on the rate statement's stable tail: the Moving branch is rewritten by
+    # unreal_first_person_motion (AuthoredWalkRate) before this adapter runs.
+    ('cpp', ':(PlayingIdle?1.f:0.f)):1.f;\n',
+     ':(PlayingIdle?1.f:0.f)):1.f;\n ApplySeatAnimation(Instance);\n'),
```

Alternatively, merge the branch's `SEAT_RATE_ANCHOR`.

**P2 (#10)** Stale tests. Verified: 28 passed.

```diff
# tests/test_unreal_fullbody_attachment.py
-  self.assertIn('FirstPersonBody->GetAttachParent()==ViewCamera',cpp)
-  self.assertIn(':FVector::ZeroVector',cpp)
+  self.assertIn('if(!HandsDiagnosticSeat)FirstPersonBody->SetRelativeLocation(HandsBaseOffset);',cpp)
+  self.assertIn('Sub01FirstPersonMotion::AuthoredWalkRate(Speed)',cpp)
# tests/test_unreal_hands_bindings.py
-            self.assertIn('if(Moving)WalkPhase+=',cpp)
+            self.assertIn('Sub01FirstPersonMotion::AuthoredWalkRate(Speed)',cpp)
+            self.assertNotIn('WalkPhase+=',cpp)
```

**P3 (#2, #3 at the desk)** `tools/unreal_seat_transition_runtime.py` `UpdateSeatTransition`: the same eased eye as the controller adapter. A camera attached to a hidden (zero-scale) Head bone collapses any relative offset, so the patch uses world location.

Add these fields to `CHARACTER_FIELDS`:

```cpp
FVector SeatEye=FVector::ZeroVector;bool SeatCameraEasing=false;FName SeatHead;
```

Replace the attach and detach block:

```diff
-  if(!Head.IsNone()){ViewCamera->AttachToComponent(FirstPersonBody,FAttachmentTransformRules::SnapToTargetNotIncludingScale,Head);ViewCamera->SetUsingAbsoluteRotation(true);}
+  if(!Head.IsNone()){SeatHead=Head;if(!SeatCameraEasing)SeatEye=ViewCamera->GetComponentLocation();SeatCameraEasing=true;ViewCamera->SetUsingAbsoluteLocation(true);ViewCamera->SetUsingAbsoluteRotation(true);}
   SeatBodyAttached=true;
  }else if(!Seated&&SeatBodyAttached){
-  ViewCamera->AttachToComponent(GetRootComponent(),FAttachmentTransformRules::KeepWorldTransform);ViewCamera->SetUsingAbsoluteRotation(false);
-  ViewCamera->SetRelativeLocation(FVector(0,0,74));ViewCamera->SetRelativeRotation(FRotator::ZeroRotator);SeatBodyAttached=false;
+  SeatBodyAttached=false; // eased back below, then handed to the capsule
  }
+ if(SeatCameraEasing){
+  const FVector Standing=GetRootComponent()->GetComponentTransform().TransformPosition(FVector(0,0,74));FVector Target=Standing;
+  if(SeatBodyAttached&&!SeatHead.IsNone()){const FTransform H=FirstPersonBody->GetSocketTransform(SeatHead,RTS_World);
+   const FVector Eye(.11885198390986161,-13.382490930007885,12.634526097714183); // measured iris midpoint, original owner
+   Target=H.GetLocation()+H.GetRotation().GetNormalized().RotateVector(FirstPersonBody->GetSkeletalMeshAsset()->GetPathName()==TEXT("/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner")?Eye:FVector::ZeroVector);}
+  if(!Target.ContainsNaN()){SeatEye=FMath::Lerp(SeatEye,Target,1.f-FMath::Exp(-10.f*FMath::Min(Dt,.1f)));ViewCamera->SetWorldLocation(SeatEye);}
+  if(!SeatBodyAttached&&FVector::Dist(SeatEye,Standing)<.5f){ViewCamera->SetUsingAbsoluteLocation(false);ViewCamera->SetUsingAbsoluteRotation(false);
+   ViewCamera->AttachToComponent(GetRootComponent(),FAttachmentTransformRules::KeepWorldTransform);ViewCamera->SetRelativeLocation(FVector(0,0,74));ViewCamera->SetRelativeRotation(FRotator::ZeroRotator);SeatCameraEasing=false;}
+ }
```

**P4 (#4, #8)** In `tools/unreal_home_hands_runtime.py` `LoadHandsAssets`, hide the head by default, as both diagnostics already do. In `tools/stage_unreal_home_runtime.py` `BeginPlay`, bound the pitch.

```diff
- for(const FName& Bone:HiddenHeadBones)if(Mesh->GetRefSkeleton().FindBoneIndex(Bone)!=INDEX_NONE)
+ TArray<FName> HeadBones=HiddenHeadBones;
+ // The eye camera (0,0,74) is inside the owner's double-sided head; hide it unless config names bones.
+ if(HeadBones.IsEmpty())for(int32 I=0;I<Mesh->GetRefSkeleton().GetNum();++I)if(Mesh->GetRefSkeleton().GetBoneName(I).ToString().EndsWith(TEXT("Head")))HeadBones.Add(Mesh->GetRefSkeleton().GetBoneName(I));
+ for(const FName& Bone:HeadBones)if(Mesh->GetRefSkeleton().FindBoneIndex(Bone)!=INDEX_NONE)
   FirstPersonBody->HideBoneByName(Bone,EPhysBodyOp::PBO_None);
```

```diff
   Player->SetInputMode(FInputModeGameOnly()); Player->bShowMouseCursor=false;
+  if(Player->PlayerCameraManager){Player->PlayerCameraManager->ViewPitchMin=-70.f;Player->PlayerCameraManager->ViewPitchMax=75.f;}
```

Also confirm the live ini has `HandsMeshRotation=(Pitch=0,Yaw=-90,Roll=0)`. The diagnostics default to −90 because the imported mesh faces local +Y, while the C++ default is 0 and no generator writes it. For the clipping in #8, a capsule radius of about 22 cm would match the measured arm span. It needs a nav and doorway recheck, so it is not included as a patch.

**P5 (#5)** `tools/unreal_first_person_motion.py`. Compiled and checked offline. Add to `POLICY`:

```cpp
struct WalkPlayback{double Rate,BodyYawDeg;};
inline WalkPlayback DirectionalWalk(double Forward,double Right,double ReferenceSpeed=140.,double MaxBodyYaw=60.){
 const double Speed=std::hypot(Forward,Right);
 if(!std::isfinite(Speed)||Speed<=0||!std::isfinite(ReferenceSpeed)||ReferenceSpeed<=0)return{0,0};
 const double Pi=3.14159265358979323846;double Angle=std::atan2(Right,Forward)*180/Pi;const bool Back=std::fabs(Angle)>90;
 if(Back)Angle=std::remainder(Angle+180.,360.);
 const double Yaw=std::clamp(Angle,-MaxBodyYaw,MaxBodyYaw);
 const double Along=Speed*std::cos((Angle-Yaw)*Pi/180);
 return{(Back?-1.:1.)*std::clamp(Along/ReferenceSpeed,0.,1.2),Yaw};
}
```

Use it in `Tick`. Add a `float WalkBodyYaw=0;` field, and use this as the `MEASURED_WALK_RATE` replacement plus the rotation:

```cpp
const FVector LocalV=GetActorQuat().UnrotateVector(GetVelocity());
const auto Dir=Sub01FirstPersonMotion::DirectionalWalk(Moving?LocalV.X:0,Moving?LocalV.Y:0);
WalkBodyYaw+=(float(Dir.BodyYawDeg)-WalkBodyYaw)*(1.f-FMath::Exp(-10.f*FMath::Min(DeltaSeconds,.1f)));if(FMath::Abs(WalkBodyYaw)<.01f)WalkBodyYaw=0;
if(HandsPosture==TEXT("Walk")&&FirstPersonBody->GetAttachParent()==GetRootComponent()&&!HandsDiagnosticSeat)FirstPersonBody->SetRelativeRotation(HandsMeshRotation+FRotator(0,WalkBodyYaw,0));
// rate expression Moving branch: float(Dir.Rate)
```

Foot slip: strafe 198 → 70 cm/s, 45° 107 → 0, 135° 259 → 0, back 280 → 0. When stopped, the yaw decays to exactly 0 before the seat's 0.05° alignment check (~0.7 s from 60°). The seat and controller adapters set their own body rotation afterwards.

**P6 (#6)** `tools/unreal_first_person_motion.py`. Add to `POLICY`:

```cpp
inline double HeadingSpeedScale(double ViewYaw,double PathYaw,double Floor=.2){
 if(!std::isfinite(ViewYaw)||!std::isfinite(PathYaw))return 1;
 return std::clamp(std::cos(std::remainder(PathYaw-ViewYaw,360.)*3.14159265358979323846/180.),Floor,1.);
}
```

In `install()`, apply this replacement inside the `live` slice only: `unreal_native_route.py` has the same `AddMovementInput` text.

```diff
-AddMovementInput(Delta/Distance,FMath::Clamp(Distance/45.f,.15f,1.f));}
+AddMovementInput(Delta/Distance,FMath::Clamp(Distance/45.f,.15f,1.f)*float(Sub01FirstPersonMotion::HeadingSpeedScale(Controller->GetControlRotation().Yaw,Delta.Rotation().Yaw)));}
```

Result for a 90° corner: foot slip 52–55 → 28–29 cm, peak 196 → 76 cm/s. Path covered in 1.5 s goes from 210 to 188 cm. The 4 s progress watchdog is unaffected (minimum 28 cm/s).

**P7 (#7)** `tools/unreal_home_hands_runtime.py` `FSub01HandsProxy::PreUpdate`: reverse an unfinished blend instead of restarting it. Note that `SEQUENCE_START` (contact runtime) anchors on `   Progress=Hands->PreviousSequence?0:1;`; keep that line unique.

```diff
   if(Current.GetSequence()!=Hands->TargetSequence) {
+   if(Progress<1&&Hands->TargetSequence&&Previous.GetSequence()==Hands->TargetSequence.Get()){
+    UAnimSequenceBase* Out=Current.GetSequence();const float OutTime=Current.GetAccumulatedTime();
+    Current.SetSequence(Previous.GetSequence());Current.SetAccumulatedTime(Previous.GetAccumulatedTime());
+    Previous.SetSequence(Out);Previous.SetAccumulatedTime(OutTime);Previous.SetPlayRate(0);
+    Hands->PreviousSequence=Cast<UAnimSequence>(Out);Progress=1-Progress;
+   }else{
    Hands->PreviousSequence=Cast<UAnimSequence>(Current.GetSequence());
    ...existing lines through Progress=Hands->PreviousSequence?0:1;...
+   }
   }
```

The blend output is unchanged at the switch, so there is no pop. A switch to a third clip still restarts the blend, as today.
