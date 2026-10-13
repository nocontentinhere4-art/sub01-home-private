#include "../tools/native_pc_bridge/Sub01GuestFrameLayout.h"
#include <cassert>
#include <vector>
#include <limits>
int main(){
 FSub01GuestFrameLayout l;
 assert(Sub01GuestFrameLayout(1024,768,1.7,l));
 assert(l.Width==1306&&l.Height==768&&l.X==141&&l.Y==0);
 assert(std::abs(double(l.Width)/l.Height-1.7)<1.0/l.Height);
 assert(Sub01GuestFrameLayout(1280,720,4.0/3,l));
 assert(l.Width==1280&&l.Height==960&&l.X==0&&l.Y==120);
 assert(!Sub01GuestFrameLayout(0,768,1.7,l));
 assert(!Sub01GuestFrameLayout(1281,768,1.7,l));
 assert(!Sub01GuestFrameLayout(1024,768,std::numeric_limits<double>::quiet_NaN(),l));
 assert(Sub01GuestFrameLayout(2,2,2,l));
 std::vector<std::uint8_t> src={1,2,3,255,4,5,6,255,7,8,9,255,10,11,12,255},out(32);
 assert(Sub01PadGuestBGRA(src.data(),src.size(),out.data(),out.size(),l));
 assert((out==std::vector<std::uint8_t>{0,0,0,255,1,2,3,255,4,5,6,255,0,0,0,255,0,0,0,255,7,8,9,255,10,11,12,255,0,0,0,255}));
 assert(!Sub01PadGuestBGRA(src.data(),src.size()-1,out.data(),out.size(),l));
}
