"""Execute the observer-only native helper with actual queue tickets."""
from pathlib import Path
import shutil
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]
COMPILER = shutil.which('clang++') or shutil.which('g++')

@pytest.mark.skipif(not COMPILER, reason='C++ compiler required')
def test_pc_receipt_clock_only_follows_matched_acceptance_and_releases(tmp_path):
    code = r'''
#include "Sub01PCActionTimeline.h"
#include "Sub01GuestInputQueue.h"
#include <cassert>
#include <limits>
using T=FSub01PCActionTimeline;
int main(){
 T A(3); TSub01GuestInputQueue<int> Q; int Body=0; std::uint64_t Id=0;
 assert(Q.Push(30));assert(Q.Begin(Body,Id));assert(Body==30&&Id==1);
 assert(A.Queued(7,Id,T::EKind::KeyTap,1));
 assert(!A.Sample(7,1,true,false).Active); // a queued key is not a visual press
 assert(A.Sent(7,Id,1.1));
 assert(!A.Sample(7,1.2,true,false).Active); // request in flight is not accepted
 assert(!A.Acknowledged(8,Id,1.21,T::EAck::TransportAccepted));
 assert(!A.Acknowledged(7,999,1.21,T::EAck::TransportAccepted));
 assert(!A.Acknowledged(7,Id,1.21,T::EAck::None));
 assert(Q.Complete(Id));assert(A.Acknowledged(7,Id,1.22,T::EAck::TransportAccepted));
 auto S=A.Sample(7,1.23,true,false);assert(S.Active&&S.InputId==Id&&S.Ack==T::EAck::TransportAccepted);
 assert(S.SecondsSinceAck>.009&&S.SecondsSinceAck<.011);
 assert(!A.Acknowledged(7,Id,1.24,T::EAck::GuestConsumed)); // cannot replay/upgrade an ACK
 assert(!A.Sample(7,1.48,true,false).Active); // bounded, never free-running clip
 assert(A.Receipts()[0].CancelledAt==1.48);
 assert(!A.Queued(7,Id,T::EKind::KeyTap,1.5)); // replay ID refused
 assert(A.Queued(7,2,T::EKind::MouseButtons,2));assert(A.Sent(7,2,2));
 assert(A.Acknowledged(7,2,2.1,T::EAck::TransportAccepted));
 assert(A.Queued(7,3,T::EKind::Release,2.11));assert(A.Sent(7,3,2.12));
 assert(A.Acknowledged(7,3,2.13,T::EAck::TransportAccepted));
 assert(!A.Sample(7,2.14,true,false).Active);
 assert(A.Receipts()[1].ReleasedAt==2.13&&A.Receipts()[2].ReleasedAt==2.13);
 // Capacity only evicts terminal history; no overwrite of a pending real input.
 assert(A.Queued(8,4,T::EKind::KeyTap,3));assert(A.Receipts().size()==3);
 assert(A.Sent(8,4,3.1));assert(A.CancelAll(3.2));
 assert(!A.Acknowledged(8,4,3.3,T::EAck::TransportAccepted)); // stale focus/privacy completion
 assert(A.Queued(9,5,T::EKind::KeyTap,4));assert(A.Sent(9,5,4));
 assert(A.Acknowledged(9,5,4.1,T::EAck::TransportAccepted));
 assert(!A.Sample(10,4.11,true,false).Active); // generation mismatch cancels immediately
 assert(A.Queued(10,6,T::EKind::KeyTap,5));assert(A.Sent(10,6,5));
 assert(A.Acknowledged(10,6,5.1,T::EAck::TransportAccepted));
 assert(!A.Sample(10,5.11,true,true).Active); // privacy cancels even accepted cue
 assert(!A.Sample(10,5.12,true,false).Active); // clearing privacy cannot resurrect it
 assert(!A.Queued(10,7,T::EKind::KeyTap,std::numeric_limits<double>::infinity()));
 assert(!A.Queued(10,7,T::EKind::KeyTap,4)); // monotonic time
 T B(1);assert(B.Queued(1,1,T::EKind::KeyTap,0));assert(!B.Queued(1,2,T::EKind::KeyTap,0));
 assert(B.CancelAll(0));assert(B.Queued(1,2,T::EKind::KeyTap,0));
 T E;assert(E.Queued(1,1,T::EKind::KeyTap,0));assert(E.Sent(1,1,0));
 assert(!E.Sample(2,.1,true,false).Active); // pending old epoch is cancelled too
 assert(!E.Acknowledged(1,1,.2,T::EAck::TransportAccepted));
 T O;assert(O.Queued(1,1,T::EKind::KeyTap,0));assert(O.Sent(1,1,0));
 assert(O.Queued(1,2,T::EKind::Release,0));assert(O.Sent(1,2,0));
 assert(O.Acknowledged(1,2,.1,T::EAck::TransportAccepted));
 assert(!O.Acknowledged(1,1,.2,T::EAck::TransportAccepted)); // old ACK after neutral never revives it
 T Z(0);assert(!Z.Queued(1,1,T::EKind::KeyTap,0));
 // Queue.Begin generates a ticket only after a preceding ACK: enqueue time
 // remains the ORIGINAL historical timestamp, not the later dispatch clock.
 T H;assert(H.Queued(1,1,T::EKind::KeyTap,1));assert(H.Sent(1,1,1));
 assert(H.Acknowledged(1,1,2,T::EAck::TransportAccepted));
 assert(H.Queued(1,2,T::EKind::KeyTap,1.2));assert(!H.Sent(1,2,1.9));
 assert(H.Sent(1,2,2.1));assert(H.Acknowledged(1,2,2.2,T::EAck::TransportAccepted));
 assert(H.Receipts()[1].QueuedAt==1.2&&H.Receipts()[1].SentAt==2.1);

}
'''
    source = tmp_path / 'timeline.cpp'; source.write_text(code)
    exe = tmp_path / 'timeline'
    subprocess.run([COMPILER, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT/'tools/native_pc_bridge'), str(source), '-o', str(exe)], check=True, capture_output=True)
    subprocess.run([str(exe)], check=True, capture_output=True)
