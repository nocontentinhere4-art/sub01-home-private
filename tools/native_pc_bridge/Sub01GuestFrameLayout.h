#pragma once
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>

struct FSub01GuestFrameLayout {int Width=0,Height=0,X=0,Y=0,SourceWidth=0,SourceHeight=0;};
inline bool Sub01GuestFrameLayout(int Width,int Height,double Aspect,FSub01GuestFrameLayout& Out){
 if(Width<1||Height<1||Width>1280||Height>1024||!std::isfinite(Aspect)||Aspect<.25||Aspect>4)return false;
 FSub01GuestFrameLayout L;L.SourceWidth=Width;L.SourceHeight=Height;L.Width=Width;L.Height=Height;
 if(double(Width)/Height<Aspect)L.Width=int(std::ceil(Height*Aspect));
 else L.Height=int(std::ceil(Width/Aspect));
 if(L.Width>2048||L.Height>2048)return false;
 L.X=(L.Width-Width)/2;L.Y=(L.Height-Height)/2;Out=L;return true;
}
inline bool Sub01PadGuestBGRA(const std::uint8_t* Source,std::size_t SourceBytes,std::uint8_t* Dest,std::size_t DestBytes,const FSub01GuestFrameLayout& L){
 if(!Source||!Dest||L.SourceWidth<1||L.SourceHeight<1||L.Width<L.SourceWidth||L.Height<L.SourceHeight||L.X<0||L.Y<0||L.X+L.SourceWidth>L.Width||L.Y+L.SourceHeight>L.Height)return false;
 const auto NeededSource=std::size_t(L.SourceWidth)*L.SourceHeight*4,NeededDest=std::size_t(L.Width)*L.Height*4;
 if(SourceBytes!=NeededSource||DestBytes!=NeededDest)return false;
 for(std::size_t i=0;i<NeededDest;i+=4){Dest[i]=Dest[i+1]=Dest[i+2]=0;Dest[i+3]=255;}
 for(int y=0;y<L.SourceHeight;++y)std::memcpy(Dest+(std::size_t(y+L.Y)*L.Width+L.X)*4,Source+std::size_t(y)*L.SourceWidth*4,std::size_t(L.SourceWidth)*4);
 return true;
}
