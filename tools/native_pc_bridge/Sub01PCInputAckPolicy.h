#pragma once
#include <cmath>
#include <cstdint>
#include <initializer_list>

// Validates a receipt from the existing serialized request. No guest-app or
// rendered-screen consumption is inferred from a v86 input API acknowledgement.
struct FSub01PCInputAckPolicy {
 static constexpr std::uint64_t MaxIdentity=9007199254740991ULL;
 static bool BoundedIdentity(std::uint64_t Value){return Value>0&&Value<=MaxIdentity;}
 static bool SameNumber(double Value,std::uint64_t Expected){
  return BoundedIdentity(Expected)&&std::isfinite(Value)&&Value>=1&&Value<=static_cast<double>(MaxIdentity)&&std::floor(Value)==Value&&Value==static_cast<double>(Expected);
 }
 static bool Correlated(bool OK,bool ExactReceiptFields,double InputId,double Generation,std::uint64_t ExpectedId,std::uint64_t ExpectedGeneration,bool OperationLevelMatches,double QueuedAt,double AckAt,double WorkerStarted,double WorkerFinished){
  if(!OK||!ExactReceiptFields||!OperationLevelMatches||!SameNumber(InputId,ExpectedId)||!SameNumber(Generation,ExpectedGeneration))return false;
  for(double Value:{QueuedAt,AckAt,WorkerStarted,WorkerFinished})if(!std::isfinite(Value)||Value<0)return false;
  return AckAt>=QueuedAt&&AckAt-QueuedAt<=3.5&&WorkerFinished>=WorkerStarted&&WorkerFinished-WorkerStarted<=1500;
 }
};
