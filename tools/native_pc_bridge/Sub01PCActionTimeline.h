#pragma once
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <deque>

// Read-only action history. It never dispatches, retries, or stores input payloads.
// IDs are supplied by the EXISTING GraphicalInputs ticket/generation owner.
// HTTP 200 alone is not an acknowledgement: parse {"ok":true} first. Current
// guest runner only confirms stdin drain; do not label that GuestKeyboardInjected/GuestMouseInjected.
class FSub01PCActionTimeline {
public:
 enum class EKind { KeyTap, MouseMove, MouseButtons, Release };
 enum class EState { Queued, Sent, Accepted, Released, Cancelled };
 enum class EAck { None, TransportAccepted, GuestKeyboardInjected, GuestMouseInjected };
 struct FReceipt {
  std::uint64_t Generation=0,InputId=0;
  EKind Kind=EKind::KeyTap; EState State=EState::Queued; EAck Ack=EAck::None;
  double QueuedAt=-1,SentAt=-1,AckAt=-1,ReleasedAt=-1,CancelledAt=-1;
 };
 struct FVisualSample {
  bool Active=false; std::uint64_t Generation=0,InputId=0;
  EKind Kind=EKind::KeyTap; EAck Ack=EAck::None; double SecondsSinceAck=0;
  // This is an event cue, not a calibrated finger/contact pose.
 };
private:
 std::deque<FReceipt> History;
 std::size_t Limit;
 std::uint64_t LastInputId=0,ActiveId=0,LastAckId=0;
 double LastTime=-1,LastQueuedTime=-1;
 bool ObserveTime(double Time){
  if(!std::isfinite(Time)||Time<0||Time<LastTime)return false;
  LastTime=Time;return true;
 }
 FReceipt* Find(std::uint64_t Generation,std::uint64_t Id){
  for(auto& R:History)if(R.Generation==Generation&&R.InputId==Id)return &R;
  return nullptr;
 }
 bool Terminal(const FReceipt& R)const{return R.State==EState::Cancelled||R.State==EState::Released;}
public:
 explicit FSub01PCActionTimeline(std::size_t Capacity=128):Limit(Capacity){}
 // The bridge must call only AFTER the existing queue accepted this real ID.
 // If Queue.Begin assigns IDs later, carry QueuedAt in the existing queue item,
 // then record Queued + Sent consecutively at dispatch; never invent a new queue.
 bool Queued(std::uint64_t Generation,std::uint64_t Id,EKind Kind,double Time){
  if(!Generation||!Id||Id<=LastInputId||!std::isfinite(Time)||Time<0||Time<LastQueuedTime)return false;
  while(History.size()>=Limit){
   if(History.empty()||!Terminal(History.front()))return false;
   History.pop_front();
  }
  if(!Limit)return false;
  FReceipt R;R.Generation=Generation;R.InputId=Id;R.Kind=Kind;R.QueuedAt=Time;
  History.push_back(R);LastInputId=Id;LastQueuedTime=Time;return true;
 }
 bool Sent(std::uint64_t Generation,std::uint64_t Id,double Time){
  auto* R=Find(Generation,Id);
  if(!R||R->State!=EState::Queued||Time<R->QueuedAt||!ObserveTime(Time))return false;
  R->State=EState::Sent;R->SentAt=Time;return true;
 }
 bool Acknowledged(std::uint64_t Generation,std::uint64_t Id,double Time,EAck Ack){
  auto* R=Find(Generation,Id);
  if(!R||R->State!=EState::Sent||Id<=LastAckId||Ack==EAck::None||!ObserveTime(Time))return false;
  LastAckId=Id;R->Ack=Ack;R->AckAt=Time;
  if(R->Kind==EKind::Release){
   for(auto& Old:History)if(Old.Generation==Generation&&Old.State==EState::Accepted){Old.State=EState::Released;Old.ReleasedAt=Time;}
   R->State=EState::Released;R->ReleasedAt=Time;ActiveId=0;
  }else{
   // One action cue owns the visual clock. An older ACK never starts later.
   if(Id>ActiveId){
    for(auto& Old:History)if(Old.State==EState::Accepted){Old.State=EState::Released;Old.ReleasedAt=Time;}
    R->State=EState::Accepted;ActiveId=Id;
   }else{R->State=EState::Cancelled;R->CancelledAt=Time;}
  }
  return true;
 }
 // Focus/privacy/Generation invalidation acts immediately, even while neutral
 // release is still queued behind an outstanding HTTP request. Late ACKs fail.
 bool CancelAll(double Time){
  if(!ObserveTime(Time))return false;
  for(auto& R:History)if(!Terminal(R)){R.State=EState::Cancelled;R.CancelledAt=Time;}
  ActiveId=0;return true;
 }
 FVisualSample Sample(std::uint64_t CurrentGeneration,double Time,bool Focused,bool Private,double MaxAge=.25){
  FVisualSample Out;
  if(!std::isfinite(MaxAge)||MaxAge<=0||MaxAge>.25)return Out;
  if(!ObserveTime(Time))return Out;
  if(!Focused||Private){CancelAll(Time);return Out;}
  for(const auto& R:History)if(!Terminal(R)&&R.Generation!=CurrentGeneration){CancelAll(Time);return Out;}
  for(auto& R:History)if(R.InputId==ActiveId&&R.State==EState::Accepted){
   if(R.Generation!=CurrentGeneration||Time-R.AckAt>MaxAge){CancelAll(Time);return Out;}
   Out.Active=true;Out.Generation=R.Generation;Out.InputId=R.InputId;Out.Kind=R.Kind;
   Out.Ack=R.Ack;Out.SecondsSinceAck=Time-R.AckAt;return Out;
  }
  return Out;
 }
 const std::deque<FReceipt>& Receipts()const{return History;}
};
