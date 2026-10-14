#pragma once
// Fail-closed native "life" clips for the owner's full body, with no engine types (tests compile
// it with a plain C++ compiler; tools/unreal_life_clips_runtime.py feeds it the character's real
// state each tick and applies its outputs).
//
// Standing: moving -> the renderer's own Walk clip; stationary -> the captured Idle clip, looping
// at rate 1 (never a Walk frame held at rate 0). Without a bound, validated Idle on the owner
// skeleton it refuses (IdleRefusal) and leaves the renderer's choice untouched: nothing is posed,
// synthesized or substituted.
//
// Bed: only with a measured bed surface, an accepted placement for it, and all three captured bed
// clips (LieDown, SleepLoop, GetUp) bound on the owner skeleton and validated by the renderer's
// posture gate. The capsule walks to the measured approach (movement input only) and turns in
// place; from the first frame of LieDown until GetUp has played out, movement is off. Nothing here
// places the actor: the captured clips carry the body onto and off the mattress.
#include <cmath>
#include <cstdint>

enum class ESub01LifeRole : uint8_t { Idle = 0, LieDown = 1, SleepLoop = 2, GetUp = 3 };
constexpr uint32_t Sub01LifeBit(ESub01LifeRole Role) { return 1u << uint32_t(Role); }
constexpr uint32_t Sub01LifeBedRoles = Sub01LifeBit(ESub01LifeRole::LieDown) | Sub01LifeBit(ESub01LifeRole::SleepLoop) | Sub01LifeBit(ESub01LifeRole::GetUp);

enum class ESub01LifeClip : uint8_t { None, Walk, Idle, LieDown, SleepLoop, GetUp };
enum class ESub01LifePhase : uint8_t { Standing, Aligning, LyingDown, Asleep, GettingUp, Refused };
enum class ESub01LifeRefusal : uint8_t {
 None, ClipMissing, SkeletonMismatch, NotValidated, BedUnmeasured, BedPlacementMissing,
 PostureGate, ClipUnavailable, ApproachTimeout, Private, Blocked
};

inline const char* Sub01LifeRefusalName(ESub01LifeRefusal R) {
 switch (R) {
  case ESub01LifeRefusal::None: return "None";
  case ESub01LifeRefusal::ClipMissing: return "ClipMissing";
  case ESub01LifeRefusal::SkeletonMismatch: return "SkeletonMismatch";
  case ESub01LifeRefusal::NotValidated: return "NotValidated";
  case ESub01LifeRefusal::BedUnmeasured: return "BedUnmeasured";
  case ESub01LifeRefusal::BedPlacementMissing: return "BedPlacementMissing";
  case ESub01LifeRefusal::PostureGate: return "PostureGate";
  case ESub01LifeRefusal::ClipUnavailable: return "ClipUnavailable";
  case ESub01LifeRefusal::ApproachTimeout: return "ApproachTimeout";
  case ESub01LifeRefusal::Private: return "Private";
  case ESub01LifeRefusal::Blocked: return "Blocked";
 }
 return "Unknown";
}

// What the character actually found for each role (bit per ESub01LifeRole).
struct FSub01LifeRoleState {
 uint32_t Loaded = 0;       // the asset exists at its path
 uint32_t SameSkeleton = 0; // its USkeleton is the owner mesh's USkeleton
 uint32_t Validated = 0;    // the renderer lists it in ValidatedHandsPostures
};

// The first reason a set of roles cannot play, in the order an operator has to fix them.
inline ESub01LifeRefusal Sub01LifeRoleRefusal(const FSub01LifeRoleState& S, uint32_t Need) {
 if ((S.Loaded & Need) != Need) return ESub01LifeRefusal::ClipMissing;
 if ((S.SameSkeleton & Need) != Need) return ESub01LifeRefusal::SkeletonMismatch;
 if ((S.Validated & Need) != Need) return ESub01LifeRefusal::NotValidated;
 return ESub01LifeRefusal::None;
}

// FNV-1a over the low byte of each character (the exact bed report text is its revision).
template <typename CharT>
inline uint64_t Sub01LifeId(const CharT* Text) {
 uint64_t Value = 1469598103934665603ull;
 for (; Text && *Text; ++Text) { Value ^= uint64_t(uint8_t(*Text)); Value *= 1099511628211ull; }
 return Value;
}

struct FSub01LifeInputs {
 double NowSeconds = 0;
 // The renderer's gate and motion, exactly as its Tick computes them.
 bool PostureGate = false;  // HandsFailure empty and HandsPosture == Walk
 bool Moving = false;       // Walk posture, on ground, horizontal speed > 1 cm/s
 bool IdleBound = false;    // the renderer bound HandsClips["Idle"] (path, same skeleton, validated)
 FSub01LifeRoleState Roles;
 // The live command.
 bool WantSleep = false;    // activity sleep, at the bed node, empty path
 bool Fresh = false;
 bool Private = false;
 bool Blocked = false;
 // The bed: a measured surface and an accepted placement for it (approach point and heading).
 bool BedMeasured = false;
 bool BedPlacementValid = false;
 bool AtBedApproach = false;
 double YawErrorDeg = 0;
 // Playback as the animation proxy evaluated it (never the requested target, never a wall clock).
 bool ClipPlaying = false;
 uint32_t ClipSerial = 0;
 double ClipSeconds = 0;
 double LieDownSeconds = 0;  // the imported assets' own play length
 double GetUpSeconds = 0;
};

struct FSub01LifeOutputs {
 ESub01LifePhase Phase = ESub01LifePhase::Standing;
 ESub01LifeClip Clip = ESub01LifeClip::None;  // None: leave the renderer's own choice
 uint32_t ClipSerial = 0;                     // a new serial starts the clip from 0 once
 bool Loop = true;
 bool OverrideRate = false;                   // true: play at rate 1 (Idle and bed clips)
 bool MovementAllowed = true;                 // false from LieDown's first frame until GetUp has played
 bool WalkToBed = false;                      // movement input toward the measured approach only
 bool TurnInPlace = false;
 ESub01LifeRefusal Refusal = ESub01LifeRefusal::None;      // bed
 ESub01LifeRefusal IdleRefusal = ESub01LifeRefusal::None;  // standing idle
};

struct FSub01LifeMachine {
 static constexpr double StartTimeoutSeconds = 1.0;
 static constexpr double ApproachTimeoutSeconds = 30.0;
 static constexpr double YawToleranceDeg = 3.0;
 static constexpr double EndToleranceSeconds = 1.0 / 30.0;

 FSub01LifeOutputs Out;
 double PhaseStartedAt = 0;
 bool ClipStarted = false;
 bool WakeAfterLyingDown = false;

 FSub01LifeOutputs Tick(const FSub01LifeInputs& In) {
  Out.OverrideRate = false; Out.WalkToBed = false; Out.TurnInPlace = false;
  Out.IdleRefusal = ESub01LifeRefusal::None;
  switch (Out.Phase) {
   case ESub01LifePhase::Standing: Standing(In); break;
   case ESub01LifePhase::Aligning: Aligning(In); break;
   case ESub01LifePhase::LyingDown: LyingDown(In); break;
   case ESub01LifePhase::Asleep: Asleep(In); break;
   case ESub01LifePhase::GettingUp: GettingUp(In); break;
   case ESub01LifePhase::Refused: if (!In.WantSleep || !In.Fresh) Enter(ESub01LifePhase::Standing, In); else StandingClip(In); break;
  }
  return Out;
 }

 private:
 void Enter(ESub01LifePhase Phase, const FSub01LifeInputs& In, ESub01LifeRefusal Refusal = ESub01LifeRefusal::None) {
  Out.Phase = Phase; Out.Refusal = Refusal; PhaseStartedAt = In.NowSeconds; ClipStarted = false;
  Out.MovementAllowed = Phase == ESub01LifePhase::Standing || Phase == ESub01LifePhase::Aligning || Phase == ESub01LifePhase::Refused;
  ESub01LifeClip Clip = ESub01LifeClip::None;
  if (Phase == ESub01LifePhase::LyingDown) Clip = ESub01LifeClip::LieDown;
  if (Phase == ESub01LifePhase::Asleep) Clip = ESub01LifeClip::SleepLoop;
  if (Phase == ESub01LifePhase::GettingUp) Clip = ESub01LifeClip::GetUp;
  if (Clip != ESub01LifeClip::None) { Out.Clip = Clip; Out.Loop = Clip == ESub01LifeClip::SleepLoop; ++Out.ClipSerial; }
  if (Phase == ESub01LifePhase::Standing || Phase == ESub01LifePhase::Aligning || Phase == ESub01LifePhase::Refused) StandingClip(In);
 }

 // Standing (also while walking to the bed or refused): Walk while moving, the captured Idle
 // while still, or the renderer's own choice with an explicit refusal.
 void StandingClip(const FSub01LifeInputs& In) {
  Out.Loop = true;
  if (!In.PostureGate) { Out.Clip = ESub01LifeClip::None; Out.IdleRefusal = ESub01LifeRefusal::PostureGate; return; }
  if (In.Moving) { Out.Clip = ESub01LifeClip::Walk; return; }  // the renderer's rate, untouched
  if (!In.IdleBound) {
   const ESub01LifeRefusal Why = Sub01LifeRoleRefusal(In.Roles, Sub01LifeBit(ESub01LifeRole::Idle));
   Out.Clip = ESub01LifeClip::None;
   Out.IdleRefusal = Why != ESub01LifeRefusal::None ? Why : ESub01LifeRefusal::ClipMissing;
   return;
  }
  Out.Clip = ESub01LifeClip::Idle; Out.OverrideRate = true;
 }

 ESub01LifeRefusal BedRefusal(const FSub01LifeInputs& In) const {
  if (In.Private) return ESub01LifeRefusal::Private;
  if (In.Blocked) return ESub01LifeRefusal::Blocked;
  if (!In.PostureGate) return ESub01LifeRefusal::PostureGate;
  const ESub01LifeRefusal Roles = Sub01LifeRoleRefusal(In.Roles, Sub01LifeBedRoles);
  if (Roles != ESub01LifeRefusal::None) return Roles;
  if (!In.BedMeasured) return ESub01LifeRefusal::BedUnmeasured;
  if (!In.BedPlacementValid) return ESub01LifeRefusal::BedPlacementMissing;
  return ESub01LifeRefusal::None;
 }

 void Standing(const FSub01LifeInputs& In) {
  StandingClip(In);
  if (!(In.WantSleep && In.Fresh)) { Out.Refusal = ESub01LifeRefusal::None; return; }
  const ESub01LifeRefusal Why = BedRefusal(In);
  if (Why != ESub01LifeRefusal::None) { Enter(ESub01LifePhase::Refused, In, Why); return; }
  Enter(ESub01LifePhase::Aligning, In);
  Aligning(In);
 }

 void Aligning(const FSub01LifeInputs& In) {
  if (!(In.WantSleep && In.Fresh)) { Enter(ESub01LifePhase::Standing, In); return; }
  const ESub01LifeRefusal Why = BedRefusal(In);
  if (Why != ESub01LifeRefusal::None) { Enter(ESub01LifePhase::Refused, In, Why); return; }
  if (In.NowSeconds - PhaseStartedAt > ApproachTimeoutSeconds) { Enter(ESub01LifePhase::Refused, In, ESub01LifeRefusal::ApproachTimeout); return; }
  StandingClip(In);
  if (!In.AtBedApproach) { Out.WalkToBed = true; return; }
  if (std::fabs(In.YawErrorDeg) > YawToleranceDeg) { Out.TurnInPlace = true; return; }
  if (In.Moving) return;  // settle: the capsule must be still before the clip takes the body
  WakeAfterLyingDown = false;
  Enter(ESub01LifePhase::LyingDown, In);
 }

 bool Started(const FSub01LifeInputs& In) {
  if (In.ClipPlaying && In.ClipSerial == Out.ClipSerial) ClipStarted = true;
  return ClipStarted;
 }

 void LyingDown(const FSub01LifeInputs& In) {
  Out.OverrideRate = true;
  if (In.Fresh && !In.WantSleep && !In.Private) WakeAfterLyingDown = true;  // finish lying down, then get up
  if (!Started(In)) {
   // The clip never took the body: it is still standing, so standing (and movement) come back.
   if (In.NowSeconds - PhaseStartedAt > StartTimeoutSeconds) Enter(ESub01LifePhase::Refused, In, ESub01LifeRefusal::ClipUnavailable);
   return;
  }
  if (In.ClipSerial == Out.ClipSerial && In.ClipSeconds >= In.LieDownSeconds - EndToleranceSeconds && In.LieDownSeconds > 0) {
   if (WakeAfterLyingDown) Enter(ESub01LifePhase::GettingUp, In); else Enter(ESub01LifePhase::Asleep, In);
  }
 }

 void Asleep(const FSub01LifeInputs& In) {
  Out.OverrideRate = true;
  Started(In);
  // Only a fresh, different command gets him up; a stale feed or privacy never moves a sleeper.
  if (In.Fresh && !In.WantSleep && !In.Private) Enter(ESub01LifePhase::GettingUp, In);
 }

 void GettingUp(const FSub01LifeInputs& In) {
  Out.OverrideRate = true;
  if (!Started(In)) {
   // Fail closed: lying, so movement stays off until the captured get-up actually plays.
   if (In.NowSeconds - PhaseStartedAt > StartTimeoutSeconds) Out.Refusal = ESub01LifeRefusal::ClipUnavailable;
   return;
  }
  if (In.ClipSerial == Out.ClipSerial && In.ClipSeconds >= In.GetUpSeconds - EndToleranceSeconds && In.GetUpSeconds > 0) {
   Enter(ESub01LifePhase::Standing, In);
  }
 }
};
