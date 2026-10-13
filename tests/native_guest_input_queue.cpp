#include "../tools/native_pc_bridge/Sub01GuestInputQueue.h"
#include <cassert>
#include <string>
#include <cstdint>
int main(){
 TSub01GuestInputQueue<std::string> q;
 std::string value;std::uint64_t ticket=0,other=0;
 assert(q.Push("press")&&q.Push("drag")&&q.Push("release"));
 assert(q.Begin(value,ticket)&&value=="press");
 assert(!q.Begin(value,other)); // no overlapping HTTP dispatch
 assert(q.Complete(ticket));assert(!q.Complete(ticket));
 assert(q.Begin(value,ticket)&&value=="drag");
 // Focus loss must release after the active drag, dropping unsent input.
 q.ClearPending();assert(q.Push("focus-release"));
 assert(!q.Begin(value,other));assert(q.Complete(ticket));
 assert(q.Begin(value,ticket)&&value=="focus-release");
 // Privacy cancellation plus refocus must ignore an old request callback.
 q.Cancel();assert(q.Push("new-session-key"));
 assert(q.Begin(value,other)&&value=="new-session-key");
 assert(!q.Complete(ticket));assert(!q.Begin(value,ticket));
 assert(q.Complete(other));
 TSub01GuestInputQueue<int> bounded(2);
 assert(bounded.Push(1)&&bounded.Push(2)&&!bounded.Push(3));
 int n=0;assert(bounded.Begin(n,ticket)&&n==1);
 assert(bounded.Complete(ticket));assert(bounded.Begin(n,ticket)&&n==2);
}
