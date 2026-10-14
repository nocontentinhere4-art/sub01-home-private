#pragma once
// Fail-closed seat transition for the native live home, with no engine types (tests
// compile it with a plain C++ compiler; the character feeds it real state each tick).
//
// The captured owner clips carry the travel to the seat in the hips: StandToSit moves the
// hips 37.86 cm back and 16.3 cm down over 2.233 s, SitToStand 35.11 cm forward over
// 2.067 s (tools/inventory_native_seating.py, room_mx_*.glb, unchanged 65-bone owner).
// So the capsule walks (CharacterMovement input only) to an approach point in front of
// the measured cushion, turns in place, and the clip carries the hips onto the seat; the
// capsule never moves while a sit clip plays and is never placed anywhere.
//
// Seat contact is never assumed: the seated phase reports contact only from a fresh
// receipt of the measured skin/cushion probe for the current command. PC focus, the
// "seated" feedback phase and NativeSeatVerified follow that receipt, nothing else.
#include <cmath>
#include <cstdint>

struct FSub01SeatClips {
 // Measured from the captured clips (tests compare these with the inventory).
 static constexpr double SitDownSeconds=2.2333333;
 static constexpr double GetUpSeconds=2.0666667;
 static constexpr double SitHipBackCm=37.857;
 static constexpr double GetUpHipForwardCm=35.113;
};

enum class ESub01SeatPhase:uint8_t{Standing,Aligning,SittingDown,Seated,StandingUp,Refused};
enum class ESub01SeatClip:uint8_t{None,StandToSit,Sitting,SitToStand};
enum class ESub01SeatRefusal:uint8_t{None,ChairUnmeasured,NotAtApproach,Private,Stale,Blocked,ClipUnavailable};

// Everything the state machine may know, gathered by the character each tick.
struct FSub01SeatInputs {
 uint64_t Command=0;         // current backend command identity (epoch/sequence/activity hash)
 double NowSeconds=0;        // monotonic time
 bool WantSeat=false;        // the command's target is a seat (desk) and its activity is seated
 bool Fresh=false;           // command received <=3 s ago
 bool Private=false;         // backend or local privacy
 bool Blocked=false;         // the route is blocked (LiveHomeBlocked)
 bool ChairMeasured=false;   // exactly one audited cushion with no errors (native-chair-surface.json)
 bool AtApproach=false;      // on ground within the arrival gate of the approach point
 double YawErrorDeg=180;     // facing error to the seated heading (signed or absolute)
 double ClipSeconds=0;       // actual playback time of the clip this machine requested
 bool ClipPlaying=false;     // the requested clip is the one the anim instance is playing
 // Latest seat contact receipt from the measured probe (buttocks and both posterior thighs in band).
 bool ReceiptInBand=false;uint64_t ReceiptCommand=0;double ReceiptAgeSeconds=1e9;
};

struct FSub01SeatOutputs {
 ESub01SeatPhase Phase=ESub01SeatPhase::Standing;
 ESub01SeatClip Clip=ESub01SeatClip::None;
 double ClipStartSeconds=0;  // where a newly requested clip must start
 bool MovementInput=true;    // CharacterMovement input allowed (walk/turn) this tick
 bool TurnInPlace=false;     // only yaw toward the seated heading, no translation
 bool ContactVerified=false; // fresh in-band receipt for this command while seated
 bool PCFocusAllowed=false;  // seated, verified, public, fresh
 ESub01SeatRefusal Refusal=ESub01SeatRefusal::None;
};

class FSub01SeatTransition {
public:
 static constexpr double AlignToleranceDeg=3;
 static constexpr double ReceiptMaxAgeSeconds=3;
 static constexpr double ClipStartTimeoutSeconds=.5;
 static constexpr double EndToleranceSeconds=1./120; // half a 60 Hz frame: a clip clamped at its end counts as finished

 ESub01SeatPhase Phase()const{return State;}

 FSub01SeatOutputs Tick(const FSub01SeatInputs& In){
  FSub01SeatOutputs Out;
  const bool CommandChanged=In.Command!=Command;Command=In.Command;
  switch(State){
  case ESub01SeatPhase::Standing:
  case ESub01SeatPhase::Refused:{
   if(CommandChanged)HasClipFailure=false;
   const ESub01SeatRefusal Why=!In.WantSeat?ESub01SeatRefusal::None:!In.ChairMeasured?ESub01SeatRefusal::ChairUnmeasured
    :In.Private?ESub01SeatRefusal::Private:!In.Fresh?ESub01SeatRefusal::Stale:In.Blocked?ESub01SeatRefusal::Blocked
    :!In.AtApproach?ESub01SeatRefusal::NotAtApproach:ESub01SeatRefusal::None;
   if(In.WantSeat&&Why==ESub01SeatRefusal::None&&ClipFailedCommand==In.Command&&HasClipFailure){State=ESub01SeatPhase::Refused;Out.Refusal=ESub01SeatRefusal::ClipUnavailable;break;}
   if(In.WantSeat&&Why==ESub01SeatRefusal::None)State=ESub01SeatPhase::Aligning;
   else State=(In.WantSeat&&Why!=ESub01SeatRefusal::NotAtApproach)?ESub01SeatPhase::Refused:ESub01SeatPhase::Standing;
   Out.Refusal=State==ESub01SeatPhase::Refused?Why:ESub01SeatRefusal::None;
   break;}
  case ESub01SeatPhase::Aligning:
   if(!In.WantSeat||CommandChanged||In.Private||!In.Fresh||!In.AtApproach){State=ESub01SeatPhase::Standing;break;}
   if(std::fabs(In.YawErrorDeg)<=AlignToleranceDeg){State=ESub01SeatPhase::SittingDown;Start=0;Requested=ESub01SeatClip::StandToSit;RequestedAt=In.NowSeconds;}
   break;
  case ESub01SeatPhase::SittingDown:
   // Interrupted mid-sit: stand back up from the matching point of the captured get-up.
   // The captured sit never started: the body never moved, so return to standing and refuse this command.
   if(!In.ClipPlaying&&In.NowSeconds-RequestedAt>ClipStartTimeoutSeconds){State=ESub01SeatPhase::Refused;Requested=ESub01SeatClip::None;HasClipFailure=true;ClipFailedCommand=In.Command;Out.Refusal=ESub01SeatRefusal::ClipUnavailable;break;}
   if(!In.WantSeat||CommandChanged){BeginStandUp(1-Progress(In,FSub01SeatClips::SitDownSeconds),In.NowSeconds);break;}
   if(In.ClipPlaying&&In.ClipSeconds>=FSub01SeatClips::SitDownSeconds-EndToleranceSeconds){State=ESub01SeatPhase::Seated;Start=0;Requested=ESub01SeatClip::Sitting;}
   break;
  case ESub01SeatPhase::Seated:
   if(!In.WantSeat||CommandChanged){BeginStandUp(0,In.NowSeconds);break;}
   break;
  case ESub01SeatPhase::StandingUp:
   // Always finish standing (no teleport, no snap); a new seat command re-sits afterwards.
   // A get-up that never starts keeps movement blocked: a seated body must not glide.
   if(!In.ClipPlaying&&In.NowSeconds-RequestedAt>ClipStartTimeoutSeconds)Out.Refusal=ESub01SeatRefusal::ClipUnavailable;
   if(In.ClipPlaying&&In.ClipSeconds>=FSub01SeatClips::GetUpSeconds-EndToleranceSeconds){State=ESub01SeatPhase::Standing;Requested=ESub01SeatClip::None;Start=0;}
   break;
  }
  Out.Phase=State;Out.Clip=Requested;Out.ClipStartSeconds=Start;
  const bool Animating=State==ESub01SeatPhase::SittingDown||State==ESub01SeatPhase::Seated||State==ESub01SeatPhase::StandingUp;
  Out.MovementInput=!Animating;Out.TurnInPlace=State==ESub01SeatPhase::Aligning;
  Out.ContactVerified=State==ESub01SeatPhase::Seated&&In.ReceiptInBand&&In.ReceiptCommand==Command
   &&In.ReceiptAgeSeconds>=0&&In.ReceiptAgeSeconds<=ReceiptMaxAgeSeconds;
  Out.PCFocusAllowed=Out.ContactVerified&&!In.Private&&In.Fresh;
  return Out;
 }

private:
 ESub01SeatPhase State=ESub01SeatPhase::Standing;
 ESub01SeatClip Requested=ESub01SeatClip::None;
 uint64_t Command=0,ClipFailedCommand=0;bool HasClipFailure=false;double Start=0,RequestedAt=0;
 static double Progress(const FSub01SeatInputs& In,double Duration){
  if(!In.ClipPlaying||!(Duration>0))return 0;const double P=In.ClipSeconds/Duration;return P<0?0:P>1?1:P;
 }
 void BeginStandUp(double FromFraction,double Now){
  State=ESub01SeatPhase::StandingUp;Requested=ESub01SeatClip::SitToStand;RequestedAt=Now;
  Start=(FromFraction<0?0:FromFraction>1?1:FromFraction)*FSub01SeatClips::GetUpSeconds;
 }
};

// Where the capsule must stand, so the captured StandToSit carries the hips onto the cushion:
// the measured cushion centre plus the clip's backward hip travel, along the seated facing.
// FacingYawDeg is the direction the seated body faces (UE yaw, degrees).
inline void Sub01SeatApproachPoint(double CushionX,double CushionY,double FacingYawDeg,double& OutX,double& OutY){
 const double R=FacingYawDeg*3.14159265358979323846/180;
 OutX=CushionX+std::cos(R)*FSub01SeatClips::SitHipBackCm;OutY=CushionY+std::sin(R)*FSub01SeatClips::SitHipBackCm;
}

// What may count as a contact receipt at runtime. The skin/cushion probe runs in the editor
// on the captured Sitting pose at one body anchor (tools/unreal_audit_seat_contact.py). Its
// in-band result applies to the live body only while the live body is that audited pose:
// the same anchor (2 cm) and heading (3 deg), with the Sitting clip actually playing.
struct FSub01SeatEvidence {
 bool AuditInBand=false;            // validate_unreal_seat_contact.validate() passed for this anchor
 double AnchorX=0,AnchorY=0,AnchorYawDeg=0;
};
inline bool Sub01SeatPoseMatchesAudit(const FSub01SeatEvidence& E,double X,double Y,double YawDeg,bool SittingPlaying){
 if(!E.AuditInBand||!SittingPlaying)return false;
 const double D=std::hypot(X-E.AnchorX,Y-E.AnchorY);double A=std::fmod(std::fabs(YawDeg-E.AnchorYawDeg),360.);if(A>180)A=360-A;
 return D<=2&&A<=3;
}
