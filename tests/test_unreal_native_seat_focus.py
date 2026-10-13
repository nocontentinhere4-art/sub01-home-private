"""Execute actual native live-PC focus guards, including diagnostic-mode separation."""
import shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from unreal_live_home_runtime import METHODS,FIELDS

class SeatFocus(unittest.TestCase):
 def test_actual_live_decision_branches_fail_closed(self):
  compiler=shutil.which('clang++')or shutil.which('g++')
  if not compiler:self.skipTest('C++ compiler unavailable')
  source=METHODS.split('void ASub01HomeCharacter::UpdateLiveHome(float Dt){',1)[1]
  decision=source.split(' const FString Next=',1)[0]
  pre='''#include <string>
#define TEXT(x) x
#define BIG_NUMBER 1e30
struct FPlatformTime{static double Seconds(){return 10;}};
struct Move{int stops=0;void StopMovementImmediately(){++stops;}}move;
Move* GetCharacterMovement(){return &move;}struct PC{bool focused=true;void SetOperatorFocus(bool v){focused=v;}}pc;
PC* PCBridge=&pc;struct Path{int size=0;int Num(){return size;}}LiveHomePath;
bool LiveHome=true,LiveHomeBindWaiting=false,LiveHomeFresh=true,LiveHomePrivate=false,LiveHomeBlocked=false,NativeSeatVerified=false;
double LiveHomePollAt=100,LiveHomeLastReceived=10,LiveHomeProgressAt=0,LiveHomeBest=0;
std::string LiveHomeNode="desk",LiveHomeActivity="use_computer";
void BeginLiveHome(){}void PollLiveHome(){}void UpdateNativeFeedback(){}
void update(float Dt){
'''
  cases='''}
void reset(){pc.focused=true;move.stops=0;LiveHome=true;LiveHomeFresh=true;LiveHomePrivate=false;LiveHomeBlocked=false;NativeSeatVerified=false;LiveHomeLastReceived=10;LiveHomePath.size=0;}
int main(){
reset();update(0);if(pc.focused)return 1;
reset();NativeSeatVerified=true;update(0);if(!pc.focused)return 2;
reset();NativeSeatVerified=true;LiveHomePrivate=true;update(0);if(pc.focused||NativeSeatVerified||!move.stops)return 3;
reset();NativeSeatVerified=true;LiveHomeFresh=false;update(0);if(pc.focused||NativeSeatVerified)return 4;
reset();NativeSeatVerified=true;LiveHomeLastReceived=0;update(0);if(pc.focused||NativeSeatVerified)return 5;
reset();NativeSeatVerified=true;LiveHomeBlocked=true;update(0);if(pc.focused||NativeSeatVerified)return 6;
reset();NativeSeatVerified=true;LiveHomePath.size=1;update(0);if(pc.focused)return 7;
reset();LiveHome=false;update(0);if(!pc.focused)return 8; // separate operator diagnostic stays untouched
return 0;}
'''
  with tempfile.TemporaryDirectory()as tmp:
   cpp=Path(tmp)/'focus.cpp';cpp.write_text(pre+decision+cases);exe=Path(tmp)/'focus'
   subprocess.run([compiler,'-std=c++17',str(cpp),'-o',str(exe)],check=True,capture_output=True)
   subprocess.run([str(exe)],check=True,capture_output=True)
 def test_interaction_cannot_bypass_live_seat_guard(self):
  import ast
  tree=ast.parse((ROOT/'tools/stage_unreal_home_runtime.py').read_text())
  replacements=[node.args[1].value for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='replace' and len(node.args)>1 and isinstance(node.args[1],ast.Constant) and isinstance(node.args[1].value,str)]
  interaction=next(s for s in replacements if 'Physical seating is not verified' in s)
  guard=interaction.index('if(LiveHome&&!NativeSeatVerified)')
  enable=interaction.index('PCBridge->SetOperatorFocus(true)')
  self.assertLess(guard,enable)
  self.assertIn('SetOperatorFocus(false)',interaction[guard:enable])
  self.assertIn('return;',interaction[guard:enable])
 def test_seat_flag_is_not_derived_from_backend_timer(self):
  self.assertIn('NativeSeatVerified=false',FIELDS)
  self.assertNotIn('NativeSeatVerified=true',METHODS)
  before_wait=METHODS.split('LiveHomeBindWaiting=true',1)[0]
  self.assertIn('PCBridge->SetOperatorFocus(false)',before_wait)
  self.assertNotIn('seated',METHODS.split('ApplyLiveHome(',2)[-1].split('void ASub01HomeCharacter::UpdateLiveHome',1)[0])

if __name__=='__main__':unittest.main()
