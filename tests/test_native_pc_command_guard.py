"""Execute the actual generated Exec command against a minimal bridge adapter."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]
COMPILER = shutil.which('clang++') or shutil.which('g++')

@pytest.mark.skipif(not COMPILER, reason='C++ compiler required for executable native command check')
def test_live_command_cannot_bypass_physical_seat_or_stale_private_state(tmp_path):
    spec = importlib.util.spec_from_file_location('pc_runtime', ROOT / 'tools/unreal_pc_runtime.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    code = module.METHODS.split('void ASub01HomeCharacter::NativePCCommand(', 1)[1]
    code = 'void ASub01HomeCharacter::NativePCCommand(' + code.split('\n}\n', 1)[0] + '\n}\n'
    source = r'''
#include <cassert>
#include <string>
#define TEXT(s) s
#define UE_LOG(...) do {} while(false)
using FString=std::string;
struct FPlatformTime { static double Seconds(){return 100.;} };
struct Path {int Count=0; int Num()const{return Count;}};
struct Bridge {
 bool Focus=false,Private=false; int FocusCalls=0,Typed=0,Submitted=0;
 void SetOperatorFocus(bool Value){++FocusCalls;Focus=Value&&!Private;}
 void SetTypedLine(const FString&){if(Focus&&!Private)++Typed;}
 void SubmitTypedLine(){if(Focus&&!Private)++Submitted;}
 const char* GetPCStatus()const{return "real adapter";}
};
struct ASub01HomeCharacter {
 Bridge Instance; Bridge* PCBridge=&Instance;
 bool LiveHome=true,NativeSeatVerified=true,LiveHomeFresh=true,LiveHomePrivate=false,LiveHomeBlocked=false;
 bool Bathroom=false; int PrivacyChecks=0;
 double LiveHomeLastReceived=100.; Path LiveHomePath;
 FString LiveHomeNode="desk",LiveHomeTarget="desk",LiveHomeActivity="research";
 void UpdateNativePCPrivacy(){++PrivacyChecks;Instance.Private=Bathroom||LiveHomePrivate;}
 void NativePCCommand(const FString& Line);
};
''' + code + r'''
void rejected(ASub01HomeCharacter& C){
 C.Instance.Focus=true;
 C.NativePCCommand("actual operator command");
 assert(C.PrivacyChecks==1);assert(!C.Instance.Focus);
 assert(C.Instance.Typed==0&&C.Instance.Submitted==0);
}
int main(){
 {ASub01HomeCharacter C;C.NativeSeatVerified=false;rejected(C);}
 {ASub01HomeCharacter C;C.LiveHomeFresh=false;rejected(C);}
 {ASub01HomeCharacter C;C.LiveHomePrivate=true;rejected(C);}
 {ASub01HomeCharacter C;C.LiveHomeBlocked=true;rejected(C);}
 {ASub01HomeCharacter C;C.LiveHomeLastReceived=96.99;rejected(C);}
 {ASub01HomeCharacter C;C.LiveHomeLastReceived=101.;rejected(C);}
 {ASub01HomeCharacter C;C.LiveHomePath.Count=1;rejected(C);}
 {ASub01HomeCharacter C;C.LiveHomeNode="aisle";rejected(C);}
 {ASub01HomeCharacter C;C.LiveHomeTarget="bed";rejected(C);}
 {ASub01HomeCharacter C;C.LiveHomeActivity="phone";rejected(C);}
 {ASub01HomeCharacter C;C.Bathroom=true;rejected(C);}
 for(const auto& Activity:{"research","use_computer","chart"}){
  ASub01HomeCharacter C;C.LiveHomeActivity=Activity;C.NativePCCommand("uname");
  assert(C.Instance.Focus&&C.Instance.Typed==1&&C.Instance.Submitted==1);
 }
 {ASub01HomeCharacter C;C.LiveHomeLastReceived=97.;C.NativePCCommand("uname");assert(C.Instance.Submitted==1);}
 // Explicit separate diagnostic mode keeps administrative operator commands.
 {ASub01HomeCharacter C;C.LiveHome=false;C.NativeSeatVerified=false;C.LiveHomeFresh=false;
  C.NativePCCommand("uname");assert(C.Instance.Submitted==1);}
 {ASub01HomeCharacter C;C.PCBridge=nullptr;C.NativePCCommand("uname");assert(C.PrivacyChecks==0);}
}
'''
    cpp = tmp_path / 'command-guard.cpp'; cpp.write_text(source)
    exe = tmp_path / 'command-guard'
    subprocess.run([COMPILER, '-std=c++17', '-Wall', '-Wextra', '-Werror', str(cpp), '-o', str(exe)], check=True, capture_output=True)
    subprocess.run([str(exe)], check=True, capture_output=True)
