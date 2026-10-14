import sys,re,tempfile,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from unreal_home_hands_runtime import CHARACTER_METHODS
class IdlePlayback(unittest.TestCase):
 def test_actual_rate_branch_only_plays_bound_idle_without_motion(self):
  m=re.search(r' const bool PlayingIdle=.*?\n Instance->TargetRate=.*?;',CHARACTER_METHODS,re.S);self.assertIsNotNone(m)
  cpp=r'''
#include <cassert>
#include <algorithm>
#include <string>
#define TEXT(x) x
namespace FMath{float Clamp(float x,float lo,float hi){return std::max(lo,std::min(x,hi));}}
struct Animation{} walk,idle,phone;
struct ObjectPtr{Animation*value=nullptr;Animation*Get(){return value;}};
struct Clips{Animation*Idle=nullptr;ObjectPtr FindRef(const char*){return{Idle};}}HandsClips;
struct InstanceType{float TargetRate=0;}instance;InstanceType*Instance=&instance;
std::string HandsPosture="Walk";bool Moving=false;float Speed=0;Animation*Clip=&walk;
void update(){
'''+m.group()+r'''
}
int main(){update();assert(Instance->TargetRate==0); // no idle asset: frozen walk, no phantom motion
HandsClips.Idle=&idle;Clip=&idle;update();assert(Instance->TargetRate==1);
Clip=&walk;update();assert(Instance->TargetRate==0); // a different sequence cannot impersonate bound idle
Moving=true;Speed=140;update();assert(Instance->TargetRate==1);
Speed=70;update();assert(Instance->TargetRate==.5f);
HandsPosture="Phone";Moving=false;Clip=&phone;update();assert(Instance->TargetRate==1);
}
'''
  with tempfile.TemporaryDirectory()as d:
   p=Path(d);(p/'case.cpp').write_text(cpp);subprocess.run(['c++','-std=c++17',str(p/'case.cpp'),'-o',str(p/'case')],check=True,capture_output=True);subprocess.run([str(p/'case')],check=True)
if __name__=='__main__':unittest.main()
