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
// Arrival: with an audited body anchor, Aligning also settles the rendered body to it (a
// bounded, swept, horizontal settle driven by the adapter, standing only) until it is within
// the audit tolerance; a blocked or timed-out settle still sits, but never as a precise arrival.
//
// Contact is never assumed: ContactVerified needs a quantitative skin/cushion receipt
// (Sub01SeatReceipt) whose audited asset, clip family, pose time and full body transform
// (location, pitch/yaw/roll, all three scale axes) match the live body to the audit's own
// precision, this tick, for the current command and chair measurement. Clip playback counts
// only from the animation proxy's evaluated sequence AND the serial it actually applied.
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
// TypingProfilePending: the keyboard arm profile is not bound, or the live body is not at the
// transform it was accepted at. The raw DeskTyping clip penetrates the keys (measured 4.7 cm
// left, 1.8 cm right), so he stays in the captured Sitting idle instead of typing.
enum class ESub01SeatRefusal:uint8_t{None,ChairUnmeasured,Private,Stale,Blocked,RoleMissing,ClipUnavailable,ChairChanged,TypingProfilePending};
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
 double X=NAN,Y=NAN,Z=NAN,PitchDeg=NAN,YawDeg=NAN,RollDeg=NAN,ScaleX=NAN,ScaleY=NAN,ScaleZ=NAN;   // audited body (mesh component) world transform
 double T0=NAN,T1=NAN;                             // audited clip time range
 // buttocks, left/right posterior thigh, left/right sole: worst min gap, worst median, worst coverage.
 double MinGap[5]={NAN,NAN,NAN,NAN,NAN},MaxMedian[5]={NAN,NAN,NAN,NAN,NAN},MinCoverage[5]={NAN,NAN,NAN,NAN,NAN};
};
// docs/qa/contact.md bands per patch: seat patches -2.5..+0.5 cm, soles 0..+1 cm, at least
// half of each patch's facing skin over the surface in band.
inline bool Sub01SeatPatchesInBand(const double* MinGap,const double* Median,const double* Coverage){
 for(int I=0;I<5;++I){
  if(!Sub01SeatFinite(MinGap[I])||!Sub01SeatFinite(Median[I])||!Sub01SeatFinite(Coverage[I]))return false;
  const double Low=I<3?-2.5:0,High=I<3?.5:1;
  if(MinGap[I]<Low||Median[I]>High||Coverage[I]<.5)return false;
 }
 return true;
}
// A finite transform with positive scale (any struct with these members).
template<class T> inline bool Sub01SeatTransformFinite(const T& P){
 const double V[]={P.X,P.Y,P.Z,P.PitchDeg,P.YawDeg,P.RollDeg,P.ScaleX,P.ScaleY,P.ScaleZ};for(double X:V)if(!Sub01SeatFinite(X))return false;
 return P.ScaleX>0&&P.ScaleY>0&&P.ScaleZ>0;
}
inline bool Sub01SeatEvidenceInBand(const FSub01SeatEvidence& E){
 if(!E.Loaded||!E.MeshId||!E.ClipId||!E.ChairRevision||E.Family==ESub01SeatFamily::None)return false;
 if(!Sub01SeatTransformFinite(E)||!Sub01SeatFinite(E.T0)||!Sub01SeatFinite(E.T1)||!(E.T1>E.T0))return false;
 return Sub01SeatPatchesInBand(E.MinGap,E.MaxMedian,E.MinCoverage);
}
// The live body, as the character actually has it this tick.
struct FSub01SeatLivePose {
 uint64_t MeshId=0,ClipId=0,ChairRevision=0;ESub01SeatFamily Family=ESub01SeatFamily::None;
 double X=NAN,Y=NAN,Z=NAN,PitchDeg=NAN,YawDeg=NAN,RollDeg=NAN,ScaleX=NAN,ScaleY=NAN,ScaleZ=NAN,ClipSeconds=NAN;bool ClipPlaying=false;
};
// The audit poses the skin at one exact transform; contact gates are 0..1 cm (soles) and
// -2.5..+0.5 cm (seat), so the receipt allows only numeric noise around that transform.
struct FSub01SeatPoseTolerance {
 static constexpr double Cm=.05,Deg=.05,ScaleRatio=1e-4;
};
inline double Sub01SeatAngleDelta(double A,double B){double D=std::fmod(std::fabs(A-B),360.);return D>180?360-D:D;}
// The same body transform, to measurement noise: 0.05 cm in 3D, 0.05 deg on pitch, yaw and
// roll, 0.01% on each scale axis. A measurement made at one transform says nothing about another.
template<class A,class B> inline bool Sub01SeatSameTransform(const A& Measured,const B& Live){
 using T=FSub01SeatPoseTolerance;
 if(!Sub01SeatTransformFinite(Measured)||!Sub01SeatTransformFinite(Live))return false;
 const double D=std::sqrt((Live.X-Measured.X)*(Live.X-Measured.X)+(Live.Y-Measured.Y)*(Live.Y-Measured.Y)+(Live.Z-Measured.Z)*(Live.Z-Measured.Z));
 if(!(D<=T::Cm))return false;
 if(!(Sub01SeatAngleDelta(Live.PitchDeg,Measured.PitchDeg)<=T::Deg&&Sub01SeatAngleDelta(Live.YawDeg,Measured.YawDeg)<=T::Deg&&Sub01SeatAngleDelta(Live.RollDeg,Measured.RollDeg)<=T::Deg))return false;
 return std::fabs(Live.ScaleX/Measured.ScaleX-1)<=T::ScaleRatio&&std::fabs(Live.ScaleY/Measured.ScaleY-1)<=T::ScaleRatio&&std::fabs(Live.ScaleZ/Measured.ScaleZ-1)<=T::ScaleRatio;
}
// True only when the accepted measurement applies to exactly this body: same mesh, same
// playing clip and pose family, a pose time inside the audited range, the same chair
// measurement, and the same world transform (FSub01SeatPoseTolerance: 0.05 cm in 3D,
// 0.05 deg on each of pitch, yaw and roll, 0.01% on each scale axis).
inline bool Sub01SeatReceipt(const FSub01SeatEvidence& E,const FSub01SeatLivePose& L){
 if(!Sub01SeatEvidenceInBand(E)||!L.ClipPlaying||!Sub01SeatFinite(L.ClipSeconds))return false;
 if(L.MeshId!=E.MeshId||L.ClipId!=E.ClipId||L.Family!=E.Family||L.ChairRevision!=E.ChairRevision)return false;
 if(L.ClipSeconds<E.T0||L.ClipSeconds>E.T1)return false;
 return Sub01SeatSameTransform(E,L);
}

// A seat contact measurement of the live skin (AnalyzeCapturedSeatSkin on the body's actually
// evaluated component pose, its actual world transform, the audited cushion triangles and the
// surface actually traced under each sole). It applies only to the transform it was measured at,
// the clip serial then evaluated, and for a short time: never to a later displaced arrival.
struct FSub01SeatMeasurement {
 bool Valid=false;uint64_t MeshId=0,ChairRevision=0;uint32_t ClipSerial=0;double MeasuredAt=NAN;
 double X=NAN,Y=NAN,Z=NAN,PitchDeg=NAN,YawDeg=NAN,RollDeg=NAN,ScaleX=NAN,ScaleY=NAN,ScaleZ=NAN;
 int InvalidInfluences=-1;int Facing[5]={0,0,0,0,0};
 // Each sole's own support: the actual surface traced under its footprint (heel, mid, toe on one
 // flat component), not the floor under the capsule. A sole gap is measured to its own surface.
 bool SoleSupportVerified[2]={false,false};double SoleFloorZ[2]={NAN,NAN};
 double MinGap[5]={NAN,NAN,NAN,NAN,NAN},Median[5]={NAN,NAN,NAN,NAN,NAN},Coverage[5]={NAN,NAN,NAN,NAN,NAN};
};
struct FSub01SeatMeasurementRules {static constexpr double MaxAgeSeconds=.25;};
inline bool Sub01SeatMeasuredReceipt(const FSub01SeatMeasurement& M,const FSub01SeatLivePose& L,uint32_t EvaluatedSerial,double Now){
 if(!M.Valid||M.InvalidInfluences!=0||!M.MeshId||!M.ChairRevision||!M.ClipSerial)return false;
 if(L.Family!=ESub01SeatFamily::DeskTyping||!L.ClipPlaying||M.MeshId!=L.MeshId||M.ChairRevision!=L.ChairRevision||M.ClipSerial!=EvaluatedSerial)return false;
 if(!Sub01SeatFinite(M.MeasuredAt)||!(Now>=M.MeasuredAt)||Now-M.MeasuredAt>FSub01SeatMeasurementRules::MaxAgeSeconds)return false;
 for(int I=0;I<5;++I)if(M.Facing[I]<=0)return false;
 for(int I=0;I<2;++I)if(!M.SoleSupportVerified[I]||!Sub01SeatFinite(M.SoleFloorZ[I]))return false;
 return Sub01SeatSameTransform(M,L)&&Sub01SeatPatchesInBand(M.MinGap,M.Median,M.Coverage);
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
 // Precise settle: horizontal distance of the live body from the audited body anchor (NaN when
 // there is no audited anchor), and whether the bounded swept settle hit something.
 double SettleErrorCm=NAN;bool SettleBlocked=false;
 // What the animation proxy actually evaluated last: the requested sequence is playing,
 // under this serial (the start it applied), at this time. Same clip, older serial: not started.
 double ClipSeconds=0;bool ClipPlaying=false;uint32_t ClipSerial=0;
 bool Receipt=false;         // Sub01SeatReceipt(evidence, live pose) this tick
 bool TypingProfileReady=false;  // accepted keyboard profile bound AND the live body at its audited transform
};

struct FSub01SeatOutputs {
 ESub01SeatPhase Phase=ESub01SeatPhase::Standing;
 ESub01SeatClip Clip=ESub01SeatClip::None;
 uint32_t ClipSerial=0;      // changes only when a new clip must start; restart playback only then
 double ClipStartSeconds=0;  // where that clip must start
 bool MovementInput=true;    // CharacterMovement input allowed this tick
 bool TurnInPlace=false;     // only yaw toward the seated heading, no translation
 bool SettleMove=false;      // a bounded swept horizontal settle toward the audited anchor (standing only)
 bool PreciseArrival=false;  // this sit began within the audit tolerance of the audited anchor
 bool ContactVerified=false; // this tick's quantitative receipt, for this command and chair, while typing
 bool PCFocusAllowed=false;  // verified, typing wanted, public, fresh, not blocked
 bool TypingPending=false;   // typing wanted, seated in the Sitting idle until the keyboard profile applies
 ESub01SeatRefusal Refusal=ESub01SeatRefusal::None;
};

class FSub01SeatTransition {
public:
 static constexpr double AlignToleranceDeg=3,ClipStartTimeoutSeconds=.5,SettleTimeoutSeconds=3;
 static constexpr double EndToleranceSeconds=1./120; // a clip clamped at its end counts as finished
 static constexpr uint32_t SitRoles=SeatRoleStandToSit|SeatRoleSitting|SeatRoleSitToStand;
 static constexpr uint32_t TypeRoles=SeatRoleSitToType|SeatRoleDeskTyping;

 ESub01SeatPhase Phase()const{return State;}

 FSub01SeatOutputs Tick(const FSub01SeatInputs& In){
  FSub01SeatOutputs Out;
  const bool CommandChanged=In.Command!=Command;Command=In.Command;
  if(CommandChanged){ClipFailed=false;TypingFailed=false;}
  const bool ChairChanged=SeatedChair&&(!In.ChairMeasured||In.ChairRevision!=SeatedChair);
  switch(State){
  case ESub01SeatPhase::Standing:
  case ESub01SeatPhase::Refused:{
   ESub01SeatRefusal Why=!In.WantSeat?ESub01SeatRefusal::None:!In.ChairMeasured||!In.ChairRevision?ESub01SeatRefusal::ChairUnmeasured
    :In.Private?ESub01SeatRefusal::Private:!In.Fresh?ESub01SeatRefusal::Stale:In.Blocked?ESub01SeatRefusal::Blocked
    :(In.RolesAvailable&SitRoles)!=SitRoles?ESub01SeatRefusal::RoleMissing:ClipFailed?ESub01SeatRefusal::ClipUnavailable:ESub01SeatRefusal::None;
   if(In.WantSeat&&Why==ESub01SeatRefusal::None){State=In.AtApproach?ESub01SeatPhase::Aligning:ESub01SeatPhase::Standing;if(In.AtApproach){SeatedChair=In.ChairRevision;AlignedAt=In.NowSeconds;Precise=false;}}
   else State=In.WantSeat?ESub01SeatPhase::Refused:ESub01SeatPhase::Standing;
   Out.Refusal=State==ESub01SeatPhase::Refused?Why:ESub01SeatRefusal::None;
   break;}
  case ESub01SeatPhase::Aligning:
   // Nothing has moved yet: any doubt returns to standing (and is re-evaluated next tick).
   if(!In.WantSeat||CommandChanged||In.Private||!In.Fresh||In.Blocked||!In.AtApproach||ChairChanged){
    State=ESub01SeatPhase::Standing;SeatedChair=0;Out.Refusal=In.Blocked?ESub01SeatRefusal::Blocked:ChairChanged?ESub01SeatRefusal::ChairChanged:ESub01SeatRefusal::None;break;}
   if(std::fabs(In.YawErrorDeg)<=AlignToleranceDeg){
    // With an audited anchor, settle to its tolerance first; a blocked or timed-out settle
    // still sits, but not as a precise arrival (only a live measurement can then verify).
    const bool HasAnchor=Sub01SeatFinite(In.SettleErrorCm);
    Precise=HasAnchor&&In.SettleErrorCm<=FSub01SeatPoseTolerance::Cm&&std::fabs(In.YawErrorDeg)<=FSub01SeatPoseTolerance::Deg;
    if(!HasAnchor||Precise||In.SettleBlocked||In.NowSeconds-AlignedAt>SettleTimeoutSeconds){State=ESub01SeatPhase::SittingDown;Request(ESub01SeatClip::StandToSit,0,In.NowSeconds);}
   }
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
   if(In.WantTyping&&!TypingFailed&&(In.RolesAvailable&TypeRoles)==TypeRoles){
    if(In.TypingProfileReady){State=ESub01SeatPhase::ToTyping;Request(ESub01SeatClip::SitToType,0,In.NowSeconds);}
    else{Out.TypingPending=true;Out.Refusal=ESub01SeatRefusal::TypingProfilePending;}
   }
   else if(In.WantTyping&&(In.RolesAvailable&TypeRoles)!=TypeRoles)Out.Refusal=ESub01SeatRefusal::RoleMissing;
   break;
  case ESub01SeatPhase::ToTyping:
   if(!In.WantSeat||CommandChanged){BeginStandUp(0,In.NowSeconds);break;}
   if(!Started(In)&&In.NowSeconds-RequestedAt>ClipStartTimeoutSeconds){State=ESub01SeatPhase::SeatedIdle;TypingFailed=true;Request(ESub01SeatClip::Sitting,0,In.NowSeconds);Out.Refusal=ESub01SeatRefusal::ClipUnavailable;break;}
   if(!In.WantTyping){State=ESub01SeatPhase::SeatedIdle;Request(ESub01SeatClip::Sitting,0,In.NowSeconds);break;}
   if(!In.TypingProfileReady){State=ESub01SeatPhase::SeatedIdle;Request(ESub01SeatClip::Sitting,0,In.NowSeconds);Out.TypingPending=true;Out.Refusal=ESub01SeatRefusal::TypingProfilePending;break;}
   if(Finished(In,FSub01SeatClips::SitToTypeSeconds)){State=ESub01SeatPhase::Typing;Request(ESub01SeatClip::DeskTyping,0,In.NowSeconds);}
   break;
  case ESub01SeatPhase::Typing:
   if(!In.WantSeat||CommandChanged){BeginStandUp(0,In.NowSeconds);break;}
   if(!In.WantTyping){State=ESub01SeatPhase::SeatedIdle;Request(ESub01SeatClip::Sitting,0,In.NowSeconds);break;}
   // Never the raw keyboard hands: a profile that stops applying returns to the Sitting idle.
   if(!In.TypingProfileReady){State=ESub01SeatPhase::SeatedIdle;Request(ESub01SeatClip::Sitting,0,In.NowSeconds);Out.TypingPending=true;Out.Refusal=ESub01SeatRefusal::TypingProfilePending;break;}
   if(!Started(In)&&In.NowSeconds-RequestedAt>ClipStartTimeoutSeconds)Out.Refusal=ESub01SeatRefusal::ClipUnavailable;
   break;
  case ESub01SeatPhase::StandingUp:
   // Always finish standing (no snap); a get-up that never starts keeps movement off,
   // because a seated body must not glide. A new seat command re-sits afterwards.
   if(!Started(In)&&In.NowSeconds-RequestedAt>ClipStartTimeoutSeconds)Out.Refusal=ESub01SeatRefusal::ClipUnavailable;
   if(Finished(In,FSub01SeatClips::GetUpSeconds)){State=ESub01SeatPhase::Standing;Clip=ESub01SeatClip::None;SeatedChair=0;++Serial;}
   break;
  }
  // Contact: only while typing the evaluated DeskTyping start, from this tick's receipt for
  // this command and chair. Nothing is held over: a moved body loses contact immediately.
  Out.Phase=State;Out.Clip=Clip;Out.ClipSerial=Serial;Out.ClipStartSeconds=Start;
  const bool Animating=State==ESub01SeatPhase::SittingDown||State==ESub01SeatPhase::SeatedIdle||State==ESub01SeatPhase::ToTyping
   ||State==ESub01SeatPhase::Typing||State==ESub01SeatPhase::StandingUp;
  Out.MovementInput=!Animating;Out.TurnInPlace=State==ESub01SeatPhase::Aligning;
  Out.SettleMove=State==ESub01SeatPhase::Aligning&&Sub01SeatFinite(In.SettleErrorCm)&&In.SettleErrorCm>FSub01SeatPoseTolerance::Cm&&!In.SettleBlocked
   &&In.NowSeconds-AlignedAt<=SettleTimeoutSeconds;
  Out.PreciseArrival=Animating&&Precise;
  Out.ContactVerified=State==ESub01SeatPhase::Typing&&In.TypingProfileReady&&Started(In)&&In.Receipt&&!ChairChanged&&In.ChairRevision==SeatedChair&&!CommandChanged;
  Out.PCFocusAllowed=Out.ContactVerified&&In.WantTyping&&!In.Private&&In.Fresh&&!In.Blocked;
  if(ChairChanged&&Animating&&Out.Refusal==ESub01SeatRefusal::None)Out.Refusal=ESub01SeatRefusal::ChairChanged;
  return Out;
 }

private:
 ESub01SeatPhase State=ESub01SeatPhase::Standing;ESub01SeatClip Clip=ESub01SeatClip::None;
 uint64_t Command=0,SeatedChair=0;uint32_t Serial=0;
 bool ClipFailed=false,TypingFailed=false,Precise=false;double Start=0,RequestedAt=0,AlignedAt=0;
 void Request(ESub01SeatClip Next,double From,double Now){Clip=Next;Start=From;RequestedAt=Now;++Serial;}
 bool Started(const FSub01SeatInputs& In)const{return In.ClipPlaying&&In.ClipSerial==Serial&&Serial!=0;}
 bool Finished(const FSub01SeatInputs& In,double Duration)const{return Started(In)&&In.ClipSeconds>=Duration-EndToleranceSeconds;}
 double Progress(const FSub01SeatInputs& In,double Duration)const{
  if(!Started(In)||!(Duration>0))return 0;const double P=In.ClipSeconds/Duration;return P<0?0:P>1?1:P;
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
