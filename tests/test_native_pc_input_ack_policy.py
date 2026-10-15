"""Execute receipt identity/timing validation against real queue ticket ownership."""
from pathlib import Path
import shutil,subprocess
import pytest
ROOT=Path(__file__).resolve().parents[1]
COMPILER=shutil.which('clang++') or shutil.which('g++')
@pytest.mark.skipif(not COMPILER,reason='C++ compiler required')
def test_replayed_wrong_epoch_wrong_operation_and_unbounded_acks_refuse(tmp_path):
 code=r'''
#include "Sub01PCInputAckPolicy.h"
#include "Sub01GuestInputQueue.h"
#include <cassert>
#include <limits>
using P=FSub01PCInputAckPolicy;
int main(){
 TSub01GuestInputQueue<int> Q;int Body=0;std::uint64_t Id=0;
 assert(Q.Push(1)&&Q.Begin(Body,Id)&&Id==1);
 auto Valid=[&](double ReceiptId,double Epoch,bool OK=true,bool Fields=true,bool Operation=true){return P::Correlated(OK,Fields,ReceiptId,Epoch,Id,7,Operation,1,1.1,1000,1001);};
 assert(Valid(1,7));assert(!Valid(2,7));assert(!Valid(1,8));assert(!Valid(1,7,false));assert(!Valid(1,7,true,false));assert(!Valid(1,7,true,true,false));
 assert(!Valid(1.1,7));assert(!Valid(std::numeric_limits<double>::quiet_NaN(),7));assert(!Valid(1,std::numeric_limits<double>::infinity()));
 assert(!P::BoundedIdentity(0)&&!P::BoundedIdentity(9007199254740992ULL));
 assert(!P::Correlated(true,true,1,7,1,7,true,1,5,1000,1001));
 assert(!P::Correlated(true,true,1,7,1,7,true,1,.9,1000,1001));
 assert(!P::Correlated(true,true,1,7,1,7,true,1,1.1,1002,1001));
 assert(!P::Correlated(true,true,1,7,1,7,true,1,1.1,1000,2501));
 assert(!P::Correlated(true,true,1,7,1,7,true,-1,1.1,1000,1001));
 assert(Q.Complete(Id));assert(!Q.Complete(Id)); // existing owner still rejects duplicate completion
 assert(Q.Push(2)&&Q.Begin(Body,Id)&&Id==2);assert(!Valid(1,7)); // delayed old receipt cannot accept next request
}
'''
 src=tmp_path/'policy.cpp';src.write_text(code);exe=tmp_path/'policy'
 subprocess.run([COMPILER,'-std=c++17','-Wall','-Wextra','-Werror','-I',str(ROOT/'tools/native_pc_bridge'),str(src),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)
