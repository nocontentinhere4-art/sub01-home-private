"""Native seat transition: compiled behaviour over real clip timing, and its evidence ties.

Each scenario drives the actual header tick by tick, the way the adapter does: the
capsule walks only while MovementInput is true, playback restarts only when ClipSerial
changes, clip time advances only for the requested clip, and contact comes only from
a quantitative receipt (Sub01SeatReceipt) against an accepted measurement.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / 'tools/native_seating/Sub01SeatTransition.h'

DRIVER = r'''
#include <cstdio>
#include "Sub01SeatTransition.h"
#define CHECK(c,n) if(!(c)){std::printf("failed %d\n",n);return n;}
using P=ESub01SeatPhase;using C=ESub01SeatClip;using R=ESub01SeatRefusal;
const uint32_t AllRoles=SeatRoleStandToSit|SeatRoleSitting|SeatRoleSitToType|SeatRoleDeskTyping|SeatRoleSitToStand;
FSub01SeatEvidence Evidence(){
 FSub01SeatEvidence E;E.Loaded=true;E.MeshId=Sub01SeatId("/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner");
 E.ClipId=Sub01SeatId("/Game/Sub01Hands/FBX/SUB01_DeskTyping.SUB01_DeskTyping");E.ChairRevision=77;E.Family=ESub01SeatFamily::DeskTyping;
 E.X=203.9;E.Y=-232.3;E.Z=-.6;E.PitchDeg=0;E.YawDeg=180;E.RollDeg=0;E.ScaleX=E.ScaleY=E.ScaleZ=1;E.T0=3;E.T1=8;
 for(int I=0;I<5;++I){E.MinGap[I]=I<3?-1.2:.1;E.MaxMedian[I]=I<3?-.3:.4;E.MinCoverage[I]=.7;E.MinBandVertices[I]=120;}
 return E;}
FSub01SeatLivePose Live(const FSub01SeatEvidence& E){
 FSub01SeatLivePose L;L.MeshId=E.MeshId;L.ClipId=E.ClipId;L.ChairRevision=77;L.Family=ESub01SeatFamily::DeskTyping;
 L.X=E.X+.02;L.Y=E.Y-.02;L.Z=E.Z+.02;L.PitchDeg=.01;L.YawDeg=180.04;L.RollDeg=-.01;L.ScaleX=1;L.ScaleY=1.00005;L.ScaleZ=1;
 L.ClipSeconds=5;L.ClipPlaying=true;return L;}   // float noise of the same transform
struct Sim{
 FSub01SeatTransition M;FSub01SeatInputs In;FSub01SeatOutputs Out;uint32_t Serial=0;C Playing=C::None;double T=0;int Restarts=0;
 uint32_t Missing=0;   // roles whose clip never actually plays
 bool Stale=false;     // the proxy keeps evaluating under the previous serial (start never applied)
 bool SettleStuck=false,TurnStuck=false;   // a swept settle / turn that makes no progress
 Sim(){In.Command=1;In.WantSeat=true;In.WantTyping=true;In.Fresh=true;In.ChairMeasured=true;In.ChairRevision=77;
       In.RolesAvailable=AllRoles;In.AtApproach=true;In.YawErrorDeg=40;In.TypingProfileReady=true;}
 static uint32_t Role(C Clip){switch(Clip){case C::StandToSit:return SeatRoleStandToSit;case C::Sitting:return SeatRoleSitting;
   case C::SitToType:return SeatRoleSitToType;case C::DeskTyping:return SeatRoleDeskTyping;case C::SitToStand:return SeatRoleSitToStand;default:return 0;}}
 void Step(){
  In.NowSeconds+=1./60;
  if(Out.ClipSerial!=Serial&&!Stale){Serial=Out.ClipSerial;Playing=Out.Clip;T=Out.ClipStartSeconds;++Restarts;}else if(Playing!=C::None)T+=1./60;
  In.ClipPlaying=Playing!=C::None&&!(Missing&Role(Playing));In.ClipSeconds=T;In.ClipSerial=Serial;
  if(Out.TurnInPlace&&In.YawErrorDeg>0&&!TurnStuck)In.YawErrorDeg-=In.YawErrorDeg>2?2:In.YawErrorDeg;
  if(Out.SettleMove&&!SettleStuck)In.SettleErrorCm-=In.SettleErrorCm>.25?.25:In.SettleErrorCm;   // <= 0.25 cm per tick
  Out=M.Tick(In);
 }
 void Run(double Seconds){for(int I=0;I<int(Seconds*60+.5);++I)Step();}
 void Until(P Phase,int Limit=2000){for(int I=0;I<Limit&&Out.Phase!=Phase;++I)Step();}
};
int main(){
 const FSub01SeatEvidence E=Evidence();
 // Quantitative receipt: every dimension must match the accepted measurement.
 {FSub01SeatLivePose L=Live(E);CHECK(Sub01SeatEvidenceInBand(E)&&Sub01SeatReceipt(E,L),1)
  FSub01SeatEvidence B=E;B.Loaded=false;CHECK(!Sub01SeatReceipt(B,L),2)                    // no report, no receipt
  B=E;B.MinGap[1]=.6;CHECK(!Sub01SeatReceipt(B,L),3)                                       // a floating thigh in the report
  B=E;B.MinBandVertices[0]=5;CHECK(!Sub01SeatReceipt(B,L),4)                                // a point is not a support patch
  B=E;B.MaxMedian[1]=3.5;B.MinCoverage[1]=.2;CHECK(Sub01SeatReceipt(B,L),154)               // curved thigh resting locally
  B=E;B.MinGap[3]=-.1;CHECK(!Sub01SeatReceipt(B,L),5)                                      // a sole through the floor
  // Genuine toe plant, raised heel: a high sole median/low coverage still passes with a support patch.
  B=E;B.MaxMedian[3]=10.4;B.MinCoverage[3]=.04;B.MaxMedian[4]=7.5;B.MinCoverage[4]=.06;CHECK(Sub01SeatReceipt(B,L),150)
  B.MinBandVertices[4]=11;CHECK(!Sub01SeatReceipt(B,L),151)                                 // a single point is not a support patch
  B=E;B.MinGap[4]=1.2;CHECK(!Sub01SeatReceipt(B,L),152)                                      // the whole foot hovering
  B=E;B.MinGap[0]=-2.6;CHECK(!Sub01SeatReceipt(B,L),153)                                     // deeper than the cushion compresses
  B=E;B.Z=NAN;CHECK(!Sub01SeatReceipt(B,L),6)
  FSub01SeatLivePose X=L;X.Z+=.1;CHECK(!Sub01SeatReceipt(E,X),7)                           // 1 mm off the audited transform
  X=L;X.X=E.X+.04;X.Y=E.Y+.04;CHECK(!Sub01SeatReceipt(E,X),16)                            // 0.057 cm in 3D
  X=L;X.ScaleY=1.001;CHECK(!Sub01SeatReceipt(E,X),8)                                       // every scale axis
  X=L;X.ScaleZ=.999;CHECK(!Sub01SeatReceipt(E,X),17)
  X=L;X.ScaleX=NAN;CHECK(!Sub01SeatReceipt(E,X),18)
  X=L;X.PitchDeg=.2;CHECK(!Sub01SeatReceipt(E,X),19)                                       // a tilted body is not the audited pose
  X=L;X.RollDeg=-.2;CHECK(!Sub01SeatReceipt(E,X),90)
  X=L;X.ClipId=Sub01SeatId("/Game/Sub01Hands/Seating/SUB01_Sitting");X.Family=ESub01SeatFamily::None;CHECK(!Sub01SeatReceipt(E,X),9)  // Sitting is not the audited DeskTyping
  X=L;X.ClipSeconds=8.5;CHECK(!Sub01SeatReceipt(E,X),10)                                   // outside the audited pose time
  X=L;X.MeshId^=1;CHECK(!Sub01SeatReceipt(E,X),11)
  X=L;X.ChairRevision=78;CHECK(!Sub01SeatReceipt(E,X),12)
  X=L;X.YawDeg=-179.97;CHECK(Sub01SeatReceipt(E,X),13)                                     // heading wraps
  X=L;X.YawDeg=180.1;CHECK(!Sub01SeatReceipt(E,X),14)
  B=E;B.YawDeg=-180;B.RollDeg=359.98;X=L;CHECK(Sub01SeatReceipt(B,X),91)
  X=L;X.ClipPlaying=false;CHECK(!Sub01SeatReceipt(E,X),15)}
 // Full sit, type, focus, stand.
 {Sim S;S.In.AtApproach=false;S.Run(.2);CHECK(S.Out.Phase==P::Standing&&S.Out.MovementInput,20)
  S.In.AtApproach=true;S.Step();CHECK(S.Out.Phase==P::Aligning&&S.Out.TurnInPlace,21)
  S.Until(P::SittingDown);CHECK(!S.Out.MovementInput&&S.Out.Clip==C::StandToSit&&S.Out.ClipStartSeconds==0,22)
  S.Step();int Before=S.Restarts;while(S.T<2.2)S.Step();CHECK(S.Out.Phase==P::SittingDown&&S.Restarts==Before,23)   // no per-tick restarts
  S.Until(P::Typing);CHECK(S.Out.Clip==C::DeskTyping&&!S.Out.MovementInput,24)
  CHECK(!S.Out.ContactVerified&&!S.Out.PCFocusAllowed,25)                                  // typing is not contact
  S.In.Receipt=true;S.Step();CHECK(S.Out.ContactVerified&&S.Out.PCFocusAllowed,26)
  S.In.Receipt=false;S.Step();CHECK(!S.Out.ContactVerified&&!S.Out.PCFocusAllowed,27)      // nothing held over
  // A body moved off the audited transform cannot reuse the contact it had.
  FSub01SeatLivePose L=Live(E);S.In.Receipt=Sub01SeatReceipt(E,L);S.Step();CHECK(S.Out.ContactVerified,28)
  L.X+=.1;S.In.Receipt=Sub01SeatReceipt(E,L);S.Step();CHECK(!S.Out.ContactVerified&&!S.Out.PCFocusAllowed,36)
  L.X-=.1;L.YawDeg+=.2;S.In.Receipt=Sub01SeatReceipt(E,L);S.Step();CHECK(!S.Out.ContactVerified,37)
  S.In.Receipt=true;S.Step();S.In.Blocked=true;S.Step();CHECK(S.Out.ContactVerified&&!S.Out.PCFocusAllowed,29)
  S.In.Blocked=false;S.In.Private=true;S.Step();CHECK(!S.Out.PCFocusAllowed,30)
  S.In.Private=false;S.In.Fresh=false;S.Step();CHECK(!S.Out.PCFocusAllowed&&S.Out.Phase==P::Typing,31)
  S.In.Fresh=true;S.In.ChairRevision=78;S.Step();CHECK(!S.Out.ContactVerified&&S.Out.Refusal==R::ChairChanged,32)   // remeasured chair
  S.In.ChairRevision=77;S.In.WantTyping=false;S.Step();CHECK(S.Out.Phase==P::SeatedIdle&&S.Out.Clip==C::Sitting&&!S.Out.ContactVerified,33)
  S.In.Command=2;S.In.WantSeat=false;S.In.WantTyping=false;S.Step();
  CHECK(S.Out.Phase==P::StandingUp&&S.Out.Clip==C::SitToStand&&!S.Out.MovementInput,34)
  S.Until(P::Standing);CHECK(S.Out.MovementInput&&S.Out.Clip==C::None,35)}
 // Mid-sit interrupt plays only the rest of the get-up.
 {Sim S;S.In.YawErrorDeg=0;S.Until(P::SittingDown);S.Run(1.1);S.In.Command=3;S.In.WantSeat=false;S.Step();
  CHECK(S.Out.Phase==P::StandingUp&&S.Out.ClipStartSeconds>.95&&S.Out.ClipStartSeconds<1.1,40)
  S.Run(1.1);CHECK(S.Out.Phase==P::Standing&&S.Out.MovementInput,41)}
 // Refusals before anything moves.
 {Sim S;S.In.ChairMeasured=false;S.Run(.3);CHECK(S.Out.Phase==P::Refused&&S.Out.Refusal==R::ChairUnmeasured&&S.Out.MovementInput,50)
  S.In.ChairMeasured=true;S.In.Blocked=true;S.Step();CHECK(S.Out.Refusal==R::Blocked,51)
  S.In.Blocked=false;S.In.RolesAvailable=AllRoles&~SeatRoleSitToStand;S.Step();CHECK(S.Out.Refusal==R::RoleMissing,52)  // no way back up: never sit
  S.In.RolesAvailable=AllRoles;S.Step();CHECK(S.Out.Phase==P::Aligning,53)
  S.In.Blocked=true;S.Step();CHECK(S.Out.Phase==P::Standing&&S.Out.Refusal==R::Blocked,54)            // alignment refuses Blocked
  S.In.Blocked=false;S.Step();CHECK(S.Out.Phase==P::Aligning,55)
  S.In.ChairRevision=99;S.Step();CHECK(S.Out.Phase==P::Standing&&S.Out.Refusal==R::ChairChanged,56)}  // and a changed chair
 // Missing clips fail closed.
 {Sim S;S.Missing=SeatRoleStandToSit;S.In.YawErrorDeg=0;S.Until(P::SittingDown);S.Run(.7);
  CHECK(S.Out.Phase==P::Refused&&S.Out.Refusal==R::ClipUnavailable&&S.Out.MovementInput,60)
  S.Run(1);CHECK(S.Out.Phase==P::Refused,61)S.In.Command=4;S.Missing=0;S.Step();CHECK(S.Out.Phase==P::Aligning,62)}
 {Sim S;S.In.RolesAvailable=AllRoles&~SeatRoleDeskTyping;S.In.YawErrorDeg=0;S.Until(P::SeatedIdle);S.Run(1);
  CHECK(S.Out.Phase==P::SeatedIdle&&S.Out.Refusal==R::RoleMissing&&!S.Out.PCFocusAllowed,63)}   // seated, no PC without typing
 {Sim S;S.Missing=SeatRoleSitToType;S.In.YawErrorDeg=0;S.Until(P::ToTyping);S.Run(.7);
  CHECK(S.Out.Phase==P::SeatedIdle&&S.Out.Clip==C::Sitting,64)S.Run(1);CHECK(S.Out.Phase==P::SeatedIdle,65)}  // not retried
 {Sim S;S.In.YawErrorDeg=0;S.Until(P::Typing);S.Missing=SeatRoleSitToStand;S.In.Command=5;S.In.WantSeat=false;S.Run(1);
  CHECK(S.Out.Phase==P::StandingUp&&!S.Out.MovementInput&&S.Out.Refusal==R::ClipUnavailable,66)}  // never glides out of the chair
 // The same clip still evaluating under an older serial is not the requested start.
 {Sim S;S.In.YawErrorDeg=0;S.In.WantTyping=false;S.Until(P::SeatedIdle);S.Run(.2);CHECK(S.Playing==C::Sitting,92)
  S.Stale=true;S.In.WantTyping=true;S.Step();CHECK(S.Out.Phase==P::ToTyping,93)
  S.Run(.7);   // the bridge start was never applied: back to Sitting under a NEW serial
  CHECK(S.Out.Phase==P::SeatedIdle&&S.Out.Clip==C::Sitting&&S.Out.Refusal==R::None&&S.Playing==C::Sitting,94)
  CHECK(S.In.ClipSerial!=S.Out.ClipSerial,95)
  S.Stale=false;S.Step();CHECK(S.In.ClipSerial==S.Out.ClipSerial&&S.T==0,96)}                // re-applied from its start
 {Sim S;S.Stale=true;S.In.YawErrorDeg=0;S.Until(P::SittingDown);S.Run(.7);
  CHECK(S.Out.Phase==P::Refused&&S.Out.Refusal==R::ClipUnavailable&&S.Out.MovementInput,97)}  // a start never applied refuses
 // Precise arrival: a bounded settle to the audited anchor before any seat clip.
 {Sim S;S.In.YawErrorDeg=0;S.In.SettleErrorCm=10;S.Step();CHECK(S.Out.Phase==P::Aligning&&S.Out.SettleMove&&S.Out.Clip==C::None,100)
  int Ticks=0;while(S.Out.Phase==P::Aligning&&Ticks<400){S.Step();++Ticks;}
  CHECK(S.Out.Phase==P::SittingDown&&S.Out.PreciseArrival&&S.In.SettleErrorCm<=.05&&Ticks>=40,101)
  CHECK(!S.Out.SettleMove,102)S.Until(P::Typing);CHECK(S.Out.PreciseArrival,103)
  S.In.Command=9;S.In.WantSeat=false;S.Until(P::Standing);CHECK(!S.Out.PreciseArrival,104)}
 {Sim S;S.In.YawErrorDeg=0;S.In.SettleErrorCm=10;S.Run(.1);S.In.SettleBlocked=true;S.Step();   // a swept settle that hits something
  CHECK(S.Out.Phase==P::SittingDown&&!S.Out.PreciseArrival&&!S.Out.SettleMove,105)}
 {Sim S;S.In.YawErrorDeg=0;S.In.SettleErrorCm=10;S.SettleStuck=true;S.Run(2.9);CHECK(S.Out.Phase==P::Aligning&&S.Out.SettleMove,106)
  S.Run(.2);CHECK(S.Out.Phase==P::SittingDown&&!S.Out.PreciseArrival,107)}                    // bounded in time
 {Sim S;S.In.YawErrorDeg=1;S.TurnStuck=true;S.In.SettleErrorCm=0;S.Run(1);
  CHECK(S.Out.Phase==P::Aligning&&S.Out.TurnInPlace&&!S.Out.SettleMove,108)                    // 1 deg is not the audited heading
  S.TurnStuck=false;S.Step();CHECK(S.Out.Phase==P::SittingDown&&S.Out.PreciseArrival,109)}
 {Sim S;S.In.YawErrorDeg=0;S.Until(P::SittingDown,3);CHECK(S.Out.Phase==P::SittingDown&&!S.Out.PreciseArrival,110)}  // cushion fallback: no anchor, never precise
 // A live skin measurement applies only to the transform, serial and moment it was made at.
 {FSub01SeatLivePose L=Live(E);FSub01SeatMeasurement M;M.Valid=true;M.MeshId=L.MeshId;M.ChairRevision=77;M.ClipSerial=5;M.MeasuredAt=10;
  M.X=L.X;M.Y=L.Y;M.Z=L.Z;M.PitchDeg=L.PitchDeg;M.YawDeg=L.YawDeg;M.RollDeg=L.RollDeg;M.ScaleX=L.ScaleX;M.ScaleY=L.ScaleY;M.ScaleZ=L.ScaleZ;M.InvalidInfluences=0;
  M.SoleSupportVerified[0]=M.SoleSupportVerified[1]=true;M.SoleFloorZ[0]=3;M.SoleFloorZ[1]=2.5;
  for(int I=0;I<5;++I){M.Facing[I]=200;M.MinGap[I]=I<3?-1.1:.05;M.Median[I]=I<3?-.4:.3;M.Coverage[I]=.8;M.BandCount[I]=160;}
  CHECK(Sub01SeatMeasuredReceipt(M,L,5,10.1),120)
  FSub01SeatLivePose X=L;X.Y+=.1;CHECK(!Sub01SeatMeasuredReceipt(M,X,5,10.1),121)              // a displaced body
  X=L;X.YawDeg+=.2;CHECK(!Sub01SeatMeasuredReceipt(M,X,5,10.1),122)
  CHECK(!Sub01SeatMeasuredReceipt(M,L,5,10.3),123)CHECK(!Sub01SeatMeasuredReceipt(M,L,5,9.9),124)   // stale, or from the future
  CHECK(!Sub01SeatMeasuredReceipt(M,L,6,10.1),125)                                               // another clip start
  FSub01SeatMeasurement B=M;B.InvalidInfluences=1;CHECK(!Sub01SeatMeasuredReceipt(B,L,5,10.1),126)
  B=M;B.Facing[2]=0;CHECK(!Sub01SeatMeasuredReceipt(B,L,5,10.1),127)
  B=M;B.MinGap[4]=1.2;CHECK(!Sub01SeatMeasuredReceipt(B,L,5,10.1),128)                           // a hovering sole
  B=M;B.Median[3]=10.4;B.Coverage[3]=.04;CHECK(Sub01SeatMeasuredReceipt(B,L,5,10.1),136)          // toe plant, heel raised
  B.BandCount[3]=3;CHECK(!Sub01SeatMeasuredReceipt(B,L,5,10.1),137)
  B=M;B.MinGap[0]=-2.6;CHECK(!Sub01SeatMeasuredReceipt(B,L,5,10.1),129)
  X=L;X.Family=ESub01SeatFamily::None;CHECK(!Sub01SeatMeasuredReceipt(M,X,5,10.1),130)
  X=L;X.ChairRevision=78;CHECK(!Sub01SeatMeasuredReceipt(M,X,5,10.1),131)
  X=L;X.ClipPlaying=false;CHECK(!Sub01SeatMeasuredReceipt(M,X,5,10.1),132)
  B=M;B.ScaleZ=NAN;CHECK(!Sub01SeatMeasuredReceipt(B,L,5,10.1),133)
  B=M;B.SoleSupportVerified[1]=false;CHECK(!Sub01SeatMeasuredReceipt(B,L,5,10.1),134)          // capsule floor is not sole support
  B=M;B.SoleFloorZ[0]=NAN;CHECK(!Sub01SeatMeasuredReceipt(B,L,5,10.1),135)}
 // No raw keyboard hands: without the accepted profile at the live pose he stays in the Sitting idle.
 {Sim S;S.In.YawErrorDeg=0;S.In.TypingProfileReady=false;S.Until(P::SeatedIdle);S.Run(1);
  CHECK(S.Out.Phase==P::SeatedIdle&&S.Out.Clip==C::Sitting&&S.Out.TypingPending&&S.Out.Refusal==R::TypingProfilePending,140)
  S.In.Receipt=true;S.Step();CHECK(!S.Out.ContactVerified&&!S.Out.PCFocusAllowed,141)
  S.In.TypingProfileReady=true;S.Step();CHECK(S.Out.Phase==P::ToTyping&&!S.Out.TypingPending,142)
  S.Run(.3);S.In.TypingProfileReady=false;S.Step();                                             // pose mismatch mid-bridge
  CHECK(S.Out.Phase==P::SeatedIdle&&S.Out.Clip==C::Sitting&&S.Out.TypingPending,143)
  S.In.TypingProfileReady=true;S.Until(P::Typing);S.In.Receipt=true;S.Step();CHECK(S.Out.ContactVerified&&S.Out.PCFocusAllowed,144)
  S.In.TypingProfileReady=false;S.Step();                                                        // profile stops applying while typing
  CHECK(S.Out.Phase==P::SeatedIdle&&S.Out.Clip==C::Sitting&&!S.Out.ContactVerified&&!S.Out.PCFocusAllowed&&S.Out.Refusal==R::TypingProfilePending,145)}
 // Re-sit after a get-up requested mid-way.
 {Sim S;S.In.YawErrorDeg=0;S.Until(P::Typing);S.In.Command=6;S.In.WantSeat=false;S.Run(.5);
  S.In.Command=7;S.In.WantSeat=true;S.Step();CHECK(S.Out.Phase==P::StandingUp,70)
  S.Until(P::Standing,400);S.In.YawErrorDeg=0;S.Run(.1);CHECK(S.Out.Phase==P::SittingDown,71)}
 {double X=0,Y=0;Sub01SeatApproachFromCushion(200,-190,-90,X,Y);CHECK(std::fabs(X-200)<1e-9&&std::fabs(Y+227.857)<1e-6,80)
  Sub01SeatApproachFromAnchor(203.9,-232.3,-90,0,-10,X,Y);CHECK(std::fabs(X-(203.9+10))<1e-9&&std::fabs(Y+232.3)<1e-9,81)}  // local (0,-10) at yaw -90 is world (-10,0)
 CHECK(Sub01SeatId("abc")==Sub01SeatId(u"abc")&&Sub01SeatId("abc")!=Sub01SeatId("abd"),82)
 return 0;}
'''


def compile_and_run(source):
    compiler = shutil.which('clang++') or shutil.which('g++')
    if not compiler:
        pytest.skip('C++ compiler unavailable')
    with tempfile.TemporaryDirectory() as tmp:
        cpp, exe = Path(tmp) / 'seat.cpp', Path(tmp) / 'seat'
        cpp.write_text(source)
        built = subprocess.run([compiler, '-std=c++17', '-Wall', '-Werror', f'-I{HEADER.parent}', str(cpp), '-o', str(exe)],
                               capture_output=True, text=True)
        assert built.returncode == 0, built.stderr[-3000:]
        ran = subprocess.run([str(exe)], capture_output=True, text=True)
        assert ran.returncode == 0, ran.stdout


def test_seat_transition_behaviour_compiled():
    compile_and_run(DRIVER)


def test_clip_constants_are_the_captured_clips():
    sys.path.insert(0, str(ROOT / 'tools'))
    import inventory_native_seating as inventory
    clips = inventory.inventory()['clips']
    text = HEADER.read_text()

    def constant(name):
        return float(text.split(f'static constexpr double {name}=', 1)[1].split(';', 1)[0])

    sit, up, to_type = clips['sit_down'], clips['get_up'], clips['sit_to_type']
    assert constant('SitDownSeconds') == pytest.approx(sit['duration_s'], abs=1e-6)
    assert constant('GetUpSeconds') == pytest.approx(up['duration_s'], abs=1e-6)
    assert constant('SitToTypeSeconds') == pytest.approx(to_type['duration_s'], abs=1e-6)
    # glTF hips translation is (x, up, forward) in cm; the sit carries the hips back, the get-up forward.
    assert constant('SitHipBackCm') == pytest.approx(sit['hip_translation_cm']['first'][2] - sit['hip_translation_cm']['last'][2], abs=1e-3)
    assert constant('GetUpHipForwardCm') == pytest.approx(up['hip_translation_cm']['last'][2] - up['hip_translation_cm']['first'][2], abs=1e-3)


def test_no_teleport_or_seat_assumption_in_the_module():
    text = HEADER.read_text()
    for forbidden in ('SetActorLocation', 'Teleport', 'NativeSeatVerified', 'HipHeight', '49.'):
        assert forbidden not in text


def test_committed_verdict_table_compiled_refuses_forged_receipt_rows():
    """The generated FSub01SeatedFitVerdict table (plan_clips()) with the header's check, as LoadSeatTransition uses them."""
    sys.path.insert(0, str(ROOT / 'tools'))
    import unreal_seat_transition_runtime as seat
    verdicts = seat.committed_seated_fit_verdicts()
    table = seat.seated_fit_verdict_table_cpp(verdicts)
    sha = {role: v['glb_sha256'] for role, v in verdicts.items()}
    checks = []
    for n, role in enumerate(sorted(verdicts)):
        genuine = verdicts[role]['all_gates_pass']
        checks += [(f'u"{role}",true,true,u"{sha[role]}"', genuine, 300 + n),   # genuine row: binds iff the committed fit passed
                   (f'u"{role}",true,false,u"{sha[role]}"', False, 310 + n),    # fit_pass flipped off
                   (f'u"{role}",false,true,u"{sha[role]}"', False, 320 + n),    # not accepted
                   (f'u"{role}",true,true,u"{"0" * 64}"', False, 330 + n),      # another GLB
                   (f'u"{role}",true,true,u""', False, 340 + n)]                # no GLB
    checks.append(('u"Sitting",true,true,u"%s"' % sha['SeatedIdle'], False, 350))  # a role the table does not hold
    body = ''.join('CHECK(Sub01SeatedFitCommitted(Table,N,%s)==%s,%d)\n' % (args, 'true' if want else 'false', code)
                   for args, want, code in checks)
    assert sum(want for _, want, _ in checks) == 3
    compile_and_run('#include <cstdio>\n#include "Sub01SeatTransition.h"\n#define CHECK(c,n) if(!(c)){std::printf("failed %d\\n",n);return n;}\n'
                    'static const FSub01SeatedFitVerdict Table[]={' + table + '};\n'
                    'int main(){const int N=int(sizeof(Table)/sizeof(Table[0]));CHECK(N==6,299)\n' + body + 'return 0;}')
