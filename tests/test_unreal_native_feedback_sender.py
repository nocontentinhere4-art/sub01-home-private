"""Execute the native report decision; engine/network delivery still needs GPU acceptance."""
import shutil
import subprocess
from tools.unreal_native_feedback_sender import METHODS


def test_actual_native_phase_requires_binding_arrival_and_physical_seat(tmp_path):
    compiler = shutil.which('clang++') or shutil.which('g++')
    if not compiler:
        import pytest
        pytest.skip('C++ compiler unavailable')
    phase = METHODS.split('const TCHAR* ASub01HomeCharacter::NativeFeedbackPhase() const{', 1)[1].split('\nvoid ASub01HomeCharacter::UpdateNativeFeedback()', 1)[0]
    source = '''#include <string>
using TCHAR=char;
#define TEXT(x) x
bool LiveHomeBlocked=false,NativeFeedbackBound=false,NativeSeatVerified=false;
std::string LiveHomeNode="desk",LiveHomeTarget="desk";
struct Path{int size=0;int Num(){return size;}}LiveHomePath;
const TCHAR* phase(){
''' + phase + '''
int main(){
 if(std::string(phase())!="walking")return 1;
 NativeFeedbackBound=true;if(std::string(phase())!="arrived")return 2;
 NativeSeatVerified=true;if(std::string(phase())!="seated")return 3;
 LiveHomePath.size=1;if(std::string(phase())!="walking")return 4;
 LiveHomePath.size=0;LiveHomeNode="kitchen";LiveHomeTarget="kitchen";
 if(std::string(phase())!="arrived")return 5;
 LiveHomeNode="desk";if(std::string(phase())!="walking")return 6;
 LiveHomeBlocked=true;if(std::string(phase())!="blocked")return 7;
 return 0;
}
'''
    cpp = tmp_path/'phase.cpp'; cpp.write_text(source)
    exe = tmp_path/'phase'
    subprocess.run([compiler, '-std=c++17', str(cpp), '-o', str(exe)], check=True, capture_output=True)
    subprocess.run([str(exe)], check=True, capture_output=True)


def test_sender_is_installed_and_never_invents_physical_seating():
    from tools.unreal_live_home_runtime import FIELDS, METHODS as LIVE
    assert 'void UpdateNativeFeedback();' in FIELDS
    assert ' UpdateNativeFeedback();' in LIVE
    assert 'NativeSeatVerified=true' not in LIVE
    assert 'LiveHomeOrigin+TEXT("/home/native_state")' in METHODS
    assert 'LiveHomeEpoch!=Epoch||LiveHomeCommandSequence!=Sequence||LiveHomeActivity!=Activity' in METHODS
    assert 'Now<LiveHomeLastReceived||Now-LiveHomeLastReceived>3' in METHODS
    assert 'Bind?TEXT("walking")' in METHODS
    assert 'Request->SetTimeout(1.5)' in METHODS
