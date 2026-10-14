"""Explicit distal-surface pose review is separate from key-contact acceptance."""
CPP = r'''
#include <cmath>
namespace Sub01TypingReview {
inline bool DistalGap(double Gap,double CapSpread,bool ExplicitPoseReview){
 return std::isfinite(Gap)&&std::isfinite(CapSpread)&&CapSpread>=0&&CapSpread<=.2&&Gap>=-.1&&Gap+CapSpread<=(ExplicitPoseReview?.5:.2)+1.e-9;
}
}
'''
