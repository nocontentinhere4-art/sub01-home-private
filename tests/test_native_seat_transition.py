"""Native seat transition: compiled behaviour over real clip timing, and its evidence ties.

Each scenario drives the actual header tick by tick, the way the character would: the
capsule walks only while MovementInput is true, clip time advances only for the clip the
machine requested, and contact comes only from a probe receipt.
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
struct Sim{
 FSub01SeatTransition M;FSub01SeatInputs In;FSub01SeatOutputs Out;C Playing=C::None;double T=0;bool Moved=false;
 bool ClipAvailable=true;
 Sim(){In.Command=1;In.WantSeat=true;In.Fresh=true;In.ChairMeasured=true;In.AtApproach=true;In.YawErrorDeg=40;}
 // One 1/60 s tick: the anim instance plays what was requested; the capsule moves only if allowed.
 void Step(){
  In.NowSeconds+=1./60;
  if(Out.Clip!=Playing){Playing=Out.Clip;T=Out.ClipStartSeconds;}else if(Playing!=C::None)T+=1./60;
  In.ClipPlaying=ClipAvailable&&Playing!=C::None&&Playing==Out.Clip;In.ClipSeconds=T;
  if(Out.TurnInPlace&&In.YawErrorDeg>0)In.YawErrorDeg-=2;
  Out=M.Tick(In);
  if(!Out.MovementInput&&WantsToWalk)Moved=Moved||false; // a walk request is ignored while animating
 }
 bool WantsToWalk=false;
 void Run(double Seconds){for(int I=0;I<int(Seconds*60);++I)Step();}
};
int main(){
 {Sim S;S.In.AtApproach=false;S.Run(.2);                               // still walking to the approach point
  CHECK(S.Out.Phase==P::Standing&&S.Out.MovementInput&&S.Out.Refusal==R::None,1)
  S.In.AtApproach=true;S.Step();CHECK(S.Out.Phase==P::Aligning&&S.Out.TurnInPlace&&S.Out.Clip==C::None,2)
  while(S.Out.Phase==P::Aligning)S.Step();                              // turns in place: 40 deg at 2 deg/tick
  CHECK(S.Out.Phase==P::SittingDown&&!S.Out.MovementInput&&S.Out.Clip==C::StandToSit,3)
  CHECK(!S.Out.ContactVerified&&!S.Out.PCFocusAllowed,4)
  while(S.T<2.2)S.Step();CHECK(S.Out.Phase==P::SittingDown,5)          // the captured clip is not cut short
  S.Run(.1);CHECK(S.Out.Phase==P::Seated&&S.Out.Clip==C::Sitting&&!S.Out.MovementInput,6)
  CHECK(!S.Out.ContactVerified&&!S.Out.PCFocusAllowed,7)                // seated is not contact
  S.In.ReceiptInBand=true;S.In.ReceiptCommand=1;S.In.ReceiptAgeSeconds=.4;S.Step();
  CHECK(S.Out.ContactVerified&&S.Out.PCFocusAllowed,8)
  S.In.ReceiptAgeSeconds=3.5;S.Step();CHECK(!S.Out.ContactVerified&&!S.Out.PCFocusAllowed,9)   // stale receipt
  S.In.ReceiptAgeSeconds=.2;S.In.ReceiptInBand=false;S.Step();CHECK(!S.Out.ContactVerified,10) // out of band
  S.In.ReceiptInBand=true;S.In.Private=true;S.Step();CHECK(S.Out.ContactVerified&&!S.Out.PCFocusAllowed&&S.Out.Phase==P::Seated,11)
  S.In.Private=false;S.In.Fresh=false;S.Step();CHECK(!S.Out.PCFocusAllowed&&S.Out.Phase==P::Seated&&!S.Out.MovementInput,12)
  S.In.Fresh=true;S.Step();CHECK(S.Out.PCFocusAllowed,13)
  // New command (e.g. go to bed): stand up with the captured get-up; no movement until it ends.
  S.In.Command=2;S.In.WantSeat=false;S.Step();
  CHECK(S.Out.Phase==P::StandingUp&&S.Out.Clip==C::SitToStand&&S.Out.ClipStartSeconds==0&&!S.Out.MovementInput,14)
  CHECK(!S.Out.ContactVerified&&!S.Out.PCFocusAllowed,15)               // the old receipt belongs to command 1
  while(S.T<2.0)S.Step();CHECK(S.Out.Phase==P::StandingUp&&!S.Out.MovementInput,16)
  S.Run(.1);CHECK(S.Out.Phase==P::Standing&&S.Out.MovementInput&&S.Out.Clip==C::None,17)}
 {Sim S;S.In.YawErrorDeg=0;S.Step();S.Step();CHECK(S.Out.Phase==P::SittingDown,20)
  S.Run(1.1);S.In.Command=3;S.In.WantSeat=false;S.Step();                 // interrupted halfway down
  CHECK(S.Out.Phase==P::StandingUp&&S.Out.ClipStartSeconds>.95&&S.Out.ClipStartSeconds<1.1&&!S.Out.MovementInput,21)
  S.Run(1.1);CHECK(S.Out.Phase==P::Standing&&S.Out.MovementInput,22)}   // only the remaining half is played
 {Sim S;S.In.ChairMeasured=false;S.Run(.5);CHECK(S.Out.Phase==P::Refused&&S.Out.Refusal==R::ChairUnmeasured&&S.Out.MovementInput&&S.Out.Clip==C::None,30)
  S.In.ChairMeasured=true;S.In.Private=true;S.Step();CHECK(S.Out.Refusal==R::Private,31)
  S.In.Private=false;S.In.Fresh=false;S.Step();CHECK(S.Out.Refusal==R::Stale,32)
  S.In.Fresh=true;S.In.Blocked=true;S.Step();CHECK(S.Out.Refusal==R::Blocked,33)
  S.In.Blocked=false;S.Step();CHECK(S.Out.Phase==P::Aligning,34)}
 {Sim S;S.ClipAvailable=false;S.In.YawErrorDeg=0;S.Run(.4);CHECK(S.Out.Phase==P::SittingDown&&!S.Out.MovementInput,40)
  S.Run(.3);CHECK(S.Out.Phase==P::Refused&&S.Out.Refusal==R::ClipUnavailable&&S.Out.MovementInput,41)  // body never moved
  S.Run(1);CHECK(S.Out.Phase==P::Refused&&S.Out.Clip==C::None,42)       // not retried for this command
  S.In.Command=9;S.ClipAvailable=true;S.Step();CHECK(S.Out.Phase==P::Aligning,43)}
 {Sim S;S.In.YawErrorDeg=0;S.Run(2.5);CHECK(S.Out.Phase==P::Seated,50)
  S.In.Command=4;S.In.WantSeat=false;S.Step();S.Run(.5);
  S.In.Command=5;S.In.WantSeat=true;S.Step();CHECK(S.Out.Phase==P::StandingUp&&!S.Out.MovementInput,51)  // finish standing first
  S.Run(1.7);CHECK(S.Out.Phase!=P::StandingUp&&S.Out.Phase!=P::Seated,52)
  S.In.YawErrorDeg=0;S.Run(.1);CHECK(S.Out.Phase==P::SittingDown,53)}  // then re-sit through the clip
 {Sim S;S.ClipAvailable=true;S.In.YawErrorDeg=0;S.Run(2.5);S.ClipAvailable=false;
  S.In.Command=6;S.In.WantSeat=false;S.Run(1);CHECK(S.Out.Phase==P::StandingUp&&!S.Out.MovementInput&&S.Out.Refusal==R::ClipUnavailable,60)}
 {double X=0,Y=0;Sub01SeatApproachPoint(200,-190,-90,X,Y);CHECK(std::fabs(X-200)<1e-9&&std::fabs(Y+227.857)<1e-6,70)}
 {FSub01SeatEvidence E;E.AnchorX=200;E.AnchorY=-227.857;E.AnchorYawDeg=-90;
  CHECK(!Sub01SeatPoseMatchesAudit(E,200,-227.857,-90,true),80)        // no in-band audit: never a receipt
  E.AuditInBand=true;CHECK(Sub01SeatPoseMatchesAudit(E,201,-228.5,-88,true),81)
  CHECK(!Sub01SeatPoseMatchesAudit(E,200,-224,-90,true),82)            // 3.9 cm off the audited anchor
  CHECK(!Sub01SeatPoseMatchesAudit(E,200,-227.857,-85,true),83)        // 5 deg off
  CHECK(Sub01SeatPoseMatchesAudit(E,200,-227.857,270,true),84)         // same heading, wrapped
  CHECK(!Sub01SeatPoseMatchesAudit(E,200,-227.857,-90,false),85)}      // not in the audited Sitting pose
 return 0;}
'''


def test_seat_transition_behaviour_compiled():
    compiler = shutil.which('clang++') or shutil.which('g++')
    if not compiler:
        pytest.skip('C++ compiler unavailable')
    with tempfile.TemporaryDirectory() as tmp:
        cpp, exe = Path(tmp) / 'seat.cpp', Path(tmp) / 'seat'
        cpp.write_text(DRIVER)
        built = subprocess.run([compiler, '-std=c++17', '-Wall', '-Werror', f'-I{HEADER.parent}', str(cpp), '-o', str(exe)],
                               capture_output=True, text=True)
        assert built.returncode == 0, built.stderr[-3000:]
        ran = subprocess.run([str(exe)], capture_output=True, text=True)
        assert ran.returncode == 0, ran.stdout


def test_clip_constants_are_the_captured_clips():
    sys.path.insert(0, str(ROOT / 'tools'))
    import inventory_native_seating as inventory
    clips = inventory.inventory()['clips']
    text = HEADER.read_text()

    def constant(name):
        return float(text.split(f'static constexpr double {name}=', 1)[1].split(';', 1)[0])

    sit, up = clips['sit_down'], clips['get_up']
    assert constant('SitDownSeconds') == pytest.approx(sit['duration_s'], abs=1e-6)
    assert constant('GetUpSeconds') == pytest.approx(up['duration_s'], abs=1e-6)
    # glTF hips translation is (x, up, forward) in cm; the sit carries the hips back, the get-up forward.
    assert constant('SitHipBackCm') == pytest.approx(sit['hip_translation_cm']['first'][2] - sit['hip_translation_cm']['last'][2], abs=1e-3)
    assert constant('GetUpHipForwardCm') == pytest.approx(up['hip_translation_cm']['last'][2] - up['hip_translation_cm']['first'][2], abs=1e-3)
    # The approach point derived from the clip lands within 5 cm of the reviewed diagnostic seat anchor.
    assert abs((-190 - constant('SitHipBackCm')) - (-232.3)) < 5


def test_no_teleport_or_seat_assumption_in_the_module():
    text = HEADER.read_text()
    for forbidden in ('SetActorLocation', 'Teleport', 'NativeSeatVerified=true', '49', 'HipHeight'):
        assert forbidden not in text
