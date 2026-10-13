#pragma once
#include <cstddef>
#include <cstdint>
#include <deque>
#include <utility>

// HTTP requests must be dispatched one at a time: completion order cannot
// otherwise preserve a user's press, drag and release. No engine dependency.
template<class Item> class TSub01GuestInputQueue {
 std::deque<Item> Pending;
 std::size_t Limit;
 std::uint64_t LastTicket=0, ActiveTicket=0;
public:
 explicit TSub01GuestInputQueue(std::size_t Capacity=128):Limit(Capacity){}
 bool Push(Item Value){if(Pending.size()>=Limit)return false;Pending.push_back(std::move(Value));return true;}
 bool Begin(Item& Value,std::uint64_t& Ticket){
  if(ActiveTicket||Pending.empty())return false;
  Value=std::move(Pending.front());Pending.pop_front();
  Ticket=ActiveTicket=++LastTicket;return true;
 }
 bool Complete(std::uint64_t Ticket){
  if(!Ticket||Ticket!=ActiveTicket)return false;
  ActiveTicket=0;return true;
 }
 // Focus loss drops unsent input, then queues a release behind the active
 // request. Privacy cancels everything; a stale HTTP completion cannot pump.
 void ClearPending(){Pending.clear();}
 void Cancel(){Pending.clear();ActiveTicket=0;}
};
