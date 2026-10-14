#pragma once
// Fail-closed seat transition for the native live home, with no engine types (tests
// compile it with a plain C++ compiler; tools/unreal_seat_transition_runtime.py feeds it
// real character state each tick and applies its outputs).
//
// The captured owner clips carry the travel to the seat in the hips: StandToSit moves the
// hips 37.86 cm back and 16.3 cm down over 2.233 s, SitToStand 35.11 cm forward over
// 2.067 s, SitToType bridges to the desk in 1.2 s (tools/inventory_native_seating.py,
// room_mx_*.glb, unchanged 65-bone owner). The capsule walks (CharacterMovement input only)
// to its approach point and turns in place; while any seat clip plays it never moves, and
// nothing here places the actor.
//
// Contact is never assumed: ContactVerified needs a quantitative skin/cushion receipt
// (Sub01SeatReceipt) whose audited asset, clip family, pose time, 3D anchor, heading and
// scale match the live body, for the current command and chair measurement.
#include <cmath>
#include <cstdint>

struct FSub01SeatClips {
 // Measured from the captured clips (tests compare these with the inventory).
 static constexpr double SitDownSeconds=2.2333333;
 static constexpr double GetUpSeconds=2.0666667;
 static constexpr double SitToTypeSeconds=1.2;
 static constexpr double SitHipBackCm=37.857;
 static constexpr double GetUpHipForwardCm=35.113;
};

enum class ESub01SeatPhase:uint8_t{Standing,Aligning,SittingDown,SeatedIdle,ToTyping,Typing,StandingUp,Refused};
enum class ESub01SeatClip:uint8_t{None,StandToSit,Sitting,SitToType,DeskTyping,SitToStand};
enum class ESub01SeatRefusal:uint8_t{None,ChairUnmeasured,Private,Stale,Blocked,RoleMissing,ClipUnavailable,ChairChanged};
// Bit per role the character has actually bound to the owner skeleton.
enum ESub01SeatRole:uint32_t{SeatRoleStandToSit=1,SeatRoleSitting=2,SeatRoleSitToType=4,SeatRoleDeskTyping=8,SeatRoleSitToStand=16};
// Pose families a contact audit can be made for.
enum class ESub01SeatFamily:uint8_t{None,DeskTyping};

inline bool Sub01SeatFinite(double V){return std::isfinite(V);}
// FNV-1a over an asset path, identical to tools/unreal_seat_transition_runtime.py seat_id().
template<class C> inline uint64_t Sub01SeatId(const C* Text){
 uint64_t H=1469598103934665603ull;if(!Text)return 0;
 for(;*Text;++Text){H^=uint64_t(uint32_t(*Text)&0xFFu);H*=1099511628211ull;}
 return H;
}

// A measured, accepted seat contact report for one pose (tools/unreal_audit_seat_contact.py,
// validated by validate_unreal_seat_contact.py), reduced to the numbers that decide contact.
struct FSub01SeatEvidence {
 bool Loaded=false;
 uint64_t MeshId=0,ClipId=0,ChairRevision=0;ESub01SeatFamily Family=ESub01SeatFamily::None;
 double X=NAN,Y=NAN,Z=NAN,YawDeg=NAN,Scale=NAN;   // audited body (mesh component) world transform
 double T0=NAN,T1=NAN;                             // audited clip time range
 // buttocks, left/right posterior thigh, left/right sole: worst min gap, worst median, worst coverage.
 double MinGap[5]={NAN,NAN,NAN,NAN,NAN},MaxMedian[5]={NAN,NAN,NAN,NAN,NAN},MinCoverage[5]={NAN,NAN,NAN,NAN,NAN};
};
inline bool Sub01SeatEvidenceInBand(const FSub01SeatEvidence& E){
 if(!E.Loaded||!E.MeshId||!E.ClipId||!E.ChairRevision||E.Family==ESub01SeatFamily::None)return false;
 const double Pose[]={E.X,E.Y,E.Z,E.YawDeg,E.Scale,E.T0,E.T1};for(double V:Pose)if(!Sub01SeatFinite(V))return false;
 if(!(E.Scale>0)||!(E.T1>E.T0))return false;
 for(int I=0;I<5;++I){
  if(!Sub01SeatFinite(E.MinGap[I])||!Sub01SeatFinite(E.MaxMedian[I])||!Sub01SeatFinite(E.MinCoverage[I]))return false;
  const double Low=I<3?-2.5:0,High=I<3?.5:1;
  if(E.MinGap[I]<Low||E.MaxMedian[I]>High||E.MinCoverage[I]<.5)return false;
 }
 return true;
}
// The live body, as the character actually has it this tick.
struct FSub01SeatLivePose {
 uint64_t MeshId=0,ClipId=0,ChairRevision=0;ESub01SeatFamily Family=ESub01SeatFamily::None;
 double X=NAN,Y=NAN,Z=NAN,YawDeg=NAN,Scale=NAN,ClipSeconds=NAN;bool ClipPlaying=false;
};
// True only when the accepted measurement applies to exactly this body: same mesh, same
// playing clip and pose family, a pose time inside the audited range, the same chair
// measurement, and the same world transform (2 cm in 3D, 3 deg heading, 0.1% scale).
inline bool Sub01SeatReceipt(const FSub01SeatEvidence& E,const FSub01SeatLivePose& L){
 if(!Sub01SeatEvidenceInBand(E)||!L.ClipPlaying)return false;
 const double Pose[]={L.X,L.Y,L.Z,L.YawDeg,L.Scale,L.ClipSeconds};for(double V:Pose)if(!Sub01SeatFinite(V))return false;
 if(L.MeshId!=E.MeshId||L.ClipId!=E.ClipId||L.Family!=E.Family||L.ChairRevision!=E.ChairRevision)return false;
 if(L.ClipSeconds<E.T0||L.ClipSeconds>E.T1)return false;
 const double D=std::sqrt((L.X-E.X)*(L.X-E.X)+(L.Y-E.Y)*(L.Y-E.Y)+(L.Z-E.Z)*(L.Z-E.Z));
 double A=std::fmod(std::fabs(L.YawDeg-E.YawDeg),360.);if(A>180)A=360-A;
 return D<=2&&A<=3&&std::fabs(L.Scale/E.Scale-1)<=1e-3;
}

// Everything the state machine may know, gathered by the character each tick.
struct FSub01SeatInputs {
 uint64_t Command=0;         // current backend command identity (epoch/sequence/activity)
 double NowSeconds=0;        // monotonic time
 bool WantSeat=false;        // the command's target is the desk seat
 bool WantTyping=false;      // and its activity uses the PC
 bool Fresh=false,Private=false,Blocked=false;
 bool ChairMeasured=false;uint64_t ChairRevision=0;  // one audited cushion, no errors, and its identity
 uint32_t RolesAvailable=0;  // ESub01SeatRole bits actually bound
 bool AtApproach=false;      // on ground within the arrival gate of the approach point
 double YawErrorDeg=180;     // to the seated heading
 double ClipSeconds=0;bool ClipPlaying=false;   // playback of the clip this machine requested
 bool Receipt=false;         // Sub01SeatReceipt(evidence, live pose) this tick
};

struct FSub01SeatOutputs {
 ESub01SeatPhase Phase=ESub01SeatPhase::Standing;
 ESub01SeatClip Clip=ESub01SeatClip::None;
 uint32_t ClipSerial=0;      // changes only when a new clip must start; restart playback only then
 double ClipStartSeconds=0;  // where that clip must start
 bool MovementInput=true;    // CharacterMovement input allowed this tick
 bool TurnInPlace=false;     // only yaw toward the seated heading, no translation
 bool ContactVerified=false; // fresh quantitative receipt for this command and chair while typing
 bool PCFocusAllowed=false;  // verified, typing wanted, public, fresh, not blocked
 ESub01SeatRefusal Refusal=ESub01SeatRefusal::None;
};

class FSub01SeatTransition {
public:
 static constexpr double AlignToleranceDeg=3,ClipStartTimeoutSeconds=.5,ReceiptHoldSeconds=3;
 static constexpr double EndToleranceSeconds=1./120; // a clip clamped at its end counts as finished
 static constexpr uint32_t SitRoles=SeatRoleStandToSit|SeatRoleSitting|SeatRoleSitToStand;
 static constexpr uint32_t TypeRoles=SeatRoleSitToType|SeatRoleDeskTyping;

 ESub01SeatPhase Phase()const{return State;}

 FSub01SeatOutputs Tick(const FSub01SeatInputs& In){
  FSub01SeatOutputs Out;
  const bool CommandChanged=In.Command!=Command;Command=In.Command;
  if(CommandChanged){ClipFailed=false;TypingFailed=false;LastReceipt=-1e9;}
  const bool ChairChanged=SeatedChair&&(!In.ChairMeasured||In.ChairRevision!=SeatedChair);
  switch(State){
  case ESub01SeatPhase::Standing:
  case ESub01SeatPhase::Refused:{
   ESub01SeatRefusal Why=!In.WantSeat?ESub01SeatRefusal::None:!In.ChairMeasured||!In.ChairRevision?ESub01SeatRefusal::ChairUnmeasured
    :In.Private?ESub01SeatRefusal::Private:!In.Fresh?ESub01SeatRefusal::Stale:In.Blocked?ESub01SeatRefusal::Blocked
    :(In.RolesAvailable&SitRoles)!=SitRoles?ESub01SeatRefusal::RoleMissing:ClipFailed?ESub01SeatRefusal::ClipUnavailable:ESub01SeatRefusal::None;
   if(In.WantSeat&&Why==ESub01SeatRefusal::None){State=In.AtApproach?ESub01SeatPhase::Aligning:ESub01SeatPhase::Standing;if(In.AtApproach)SeatedChair=In.ChairRevision;}
   else State=In.WantSeat?ESub01SeatPhase::Refused:ESub01SeatPhase::Standing;
   Out.Refusal=State==ESub01SeatPhase::Refused?Why:ESub01SeatRefusal::None;
   break;}
  case ESub01SeatPhase::Aligning:
   // Nothing has moved yet: any doubt returns to standing (and is re-evaluated next tick).
   if(!In.WantSeat||CommandChanged||In.Private||!In.Fresh||In.Blocked||!In.AtApproach||ChairChanged){
    State=ESub01SeatPhase::Standing;SeatedChair=0;Out.Refusal=In.Blocked?ESub01SeatRefusal::Blocked:ChairChanged?ESub01SeatRefusal::ChairChanged:ESub01SeatRefusal::None;break;}
   if(std::fabs(In.YawErrorDeg)<=AlignToleranceDeg){State=ESub01SeatPhase::SittingDown;Request(ESub01SeatClip::StandToSit,0,In.NowSeconds);}
   break;
  case ESub01SeatPhase::SittingDown:
   // The captured sit never started: the body never moved, so refuse this command and stand.
   if(!Started(In)&&In.NowSeconds-RequestedAt>ClipStartTimeoutSeconds){State=ESub01SeatPhase::Refused;Clip=ESub01SeatClip::None;ClipFailed=true;SeatedChair=0;Out.Refusal=ESub01SeatRefusal::ClipUnavailable;break;}
   // Interrupted mid-sit: stand back up from the matching point of the captured get-up.
   if(!In.WantSeat||CommandChanged||ChairChanged){BeginStandUp(1-Progress(In,FSub01SeatClips::SitDownSeconds),In.NowSeconds);break;}
   if(Finished(In,FSub01SeatClips::SitDownSeconds)){State=ESub01SeatPhase::SeatedIdle;Request(ESub01SeatClip::Sitting,0,In.NowSeconds);}
   break;
  case ESub01SeatPhase::SeatedIdle:
   if(!In.WantSeat||CommandChanged){BeginStandUp(0,In.NowSeconds);break;}
   if(In.WantTyping&&!TypingFailed&&(In.RolesAvailable&TypeRoles)==TypeRoles){State=ESub01SeatPhase::ToTyping;Request(ESub01SeatClip::SitToType,0,In.NowSeconds);}
   else if(In.WantTyping&&(In.RolesAvailable&TypeRoles)!=TypeRoles)Out.Refusal=ESub01SeatRefusal::RoleMissing;
   break;
  case ESub01SeatPhase::ToTyping:
   if(!In.WantSeat||CommandChanged){BeginStandUp(0,In.NowSeconds);break;}
   if(!Started(In)&&In.NowSeconds-RequestedAt>ClipStartTimeoutSeconds){State=ESub01SeatPhase::SeatedIdle;TypingFailed=true;Request(ESub01SeatClip::Sitting,0,In.NowSeconds);Out.Refusal=ESub01SeatRefusal::ClipUnavailable;break;}
   if(!In.WantTyping){State=ESub01SeatPhase::SeatedIdle;Request(ESub01SeatClip::Sitting,0,In.NowSeconds);break;}
   if(Finished(In,FSub01SeatClips::SitToTypeSeconds)){State=ESub01SeatPhase::Typing;Request(ESub01SeatClip::DeskTyping,0,In.NowSeconds);}
   break;
  case ESub01SeatPhase::Typing:
   if(!In.WantSeat||CommandChanged){BeginStandUp(0,In.NowSeconds);break;}
   if(!In.WantTyping){State=ESub01SeatPhase::SeatedIdle;Request(ESub01SeatClip::Sitting,0,In.NowSeconds);break;}
   if(!Started(In)&&In.NowSeconds-RequestedAt>ClipStartTimeoutSeconds)Out.Refusal=ESub01SeatRefusal::ClipUnavailable;
   break;
  case ESub01SeatPhase::StandingUp:
   // Always finish standing (no snap); a get-up that never starts keeps movement off,
   // because a seated body must not glide. A new seat command re-sits afterwards.
   if(!Started(In)&&In.NowSeconds-RequestedAt>ClipStartTimeoutSeconds)Out.Refusal=ESub01SeatRefusal::ClipUnavailable;
   if(Finished(In,FSub01SeatClips::GetUpSeconds)){State=ESub01SeatPhase::Standing;Clip=ESub01SeatClip::None;SeatedChair=0;++Serial;}
   break;
  }
  // Contact: only while typing, from a receipt for this command and chair; a receipt holds
  // for at most 3 s after the last passing check (no stale contact).
  if(State==ESub01SeatPhase::Typing&&In.Receipt&&!ChairChanged&&In.ChairRevision==SeatedChair)LastReceipt=In.NowSeconds;
  if(State!=ESub01SeatPhase::Typing||ChairChanged)LastReceipt=-1e9;
  Out.Phase=State;Out.Clip=Clip;Out.ClipSerial=Serial;Out.ClipStartSeconds=Start;
  const bool Animating=State==ESub01SeatPhase::SittingDown||State==ESub01SeatPhase::SeatedIdle||State==ESub01SeatPhase::ToTyping
   ||State==ESub01SeatPhase::Typing||State==ESub01SeatPhase::StandingUp;
  Out.MovementInput=!Animating;Out.TurnInPlace=State==ESub01SeatPhase::Aligning;
  Out.ContactVerified=State==ESub01SeatPhase::Typing&&In.NowSeconds-LastReceipt<=ReceiptHoldSeconds&&In.NowSeconds>=LastReceipt;
  Out.PCFocusAllowed=Out.ContactVerified&&In.WantTyping&&!In.Private&&In.Fresh&&!In.Blocked;
  if(ChairChanged&&Animating&&Out.Refusal==ESub01SeatRefusal::None)Out.Refusal=ESub01SeatRefusal::ChairChanged;
  return Out;
 }

private:
 ESub01SeatPhase State=ESub01SeatPhase::Standing;ESub01SeatClip Clip=ESub01SeatClip::None;
 uint64_t Command=0,SeatedChair=0;uint32_t Serial=0;
 bool ClipFailed=false,TypingFailed=false;double Start=0,RequestedAt=0,LastReceipt=-1e9;
 void Request(ESub01SeatClip Next,double From,double Now){Clip=Next;Start=From;RequestedAt=Now;++Serial;}
 static bool Started(const FSub01SeatInputs& In){return In.ClipPlaying;}
 static bool Finished(const FSub01SeatInputs& In,double Duration){return In.ClipPlaying&&In.ClipSeconds>=Duration-EndToleranceSeconds;}
 static double Progress(const FSub01SeatInputs& In,double Duration){
  if(!In.ClipPlaying||!(Duration>0))return 0;const double P=In.ClipSeconds/Duration;return P<0?0:P>1?1:P;
 }
 void BeginStandUp(double FromFraction,double Now){
  State=ESub01SeatPhase::StandingUp;Request(ESub01SeatClip::SitToStand,(FromFraction<0?0:FromFraction>1?1:FromFraction)*FSub01SeatClips::GetUpSeconds,Now);
 }
};

// Where the capsule must stand for the measured pose: the audited body anchor minus the
// mesh's offset from the capsule (rotated by the capsule yaw). Without an audit, the cushion
// centre plus the captured sit's backward hip travel along the seated heading.
inline void Sub01SeatApproachFromAnchor(double AnchorX,double AnchorY,double CapsuleYawDeg,double MeshOffsetX,double MeshOffsetY,double& OutX,double& OutY){
 const double R=CapsuleYawDeg*3.14159265358979323846/180,C=std::cos(R),S=std::sin(R);
 OutX=AnchorX-(C*MeshOffsetX-S*MeshOffsetY);OutY=AnchorY-(S*MeshOffsetX+C*MeshOffsetY);
}
inline void Sub01SeatApproachFromCushion(double CushionX,double CushionY,double FacingYawDeg,double& OutX,double& OutY){
 const double R=FacingYawDeg*3.14159265358979323846/180;
 OutX=CushionX+std::cos(R)*FSub01SeatClips::SitHipBackCm;OutY=CushionY+std::sin(R)*FSub01SeatClips::SitHipBackCm;
}
