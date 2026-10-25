// SUB01_STREAMER_VISUAL_V2_V24 BEGIN (tools/native_streamer_visual_v2/install_v24.py)
// ---- the main view to the director without an X11 present: the Slate back buffer (offscreen: a texture) -> a GPU readback ring (render thread)
// ---- -> 2 encoder threads (BGRA8, JPEG, one COM "seq=<n>") -> in-order output queue -> ONE writer thread -> <streamer-dir>/main.mjpeg
namespace Sub01MainTap{
enum EKind:int32{KindUnknown=0,KindBgra8=1,KindRgba8=2,KindRgb10A2=3};
inline int32 Classify(EPixelFormat Format){return Format==PF_B8G8R8A8?KindBgra8:Format==PF_R8G8B8A8?KindRgba8:Format==PF_A2B10G10R10?KindRgb10A2:KindUnknown;}
inline const TCHAR* KindName(int32 Kind){return Kind==KindBgra8?TEXT("B8G8R8A8"):Kind==KindRgba8?TEXT("R8G8B8A8"):Kind==KindRgb10A2?TEXT("A2B10G10R10"):TEXT("unknown");}
inline void ToBgra8(uint8* P,int64 Pixels,int32 Kind){ // in place, 4 bytes per pixel in and out
 if(Kind==KindRgba8){for(int64 I=0;I<Pixels;++I){uint8* Q=P+I*4;const uint8 R=Q[0];Q[0]=Q[2];Q[2]=R;}}
 else if(Kind==KindRgb10A2){for(int64 I=0;I<Pixels;++I){uint8* Q=P+I*4;uint32 V=0;FMemory::Memcpy(&V,Q,4); // R 9:0, G 19:10, B 29:20, A 31:30 (VK_FORMAT_A2B10G10R10_UNORM_PACK32)
  Q[0]=uint8((V>>22)&0xFF);Q[1]=uint8((V>>12)&0xFF);Q[2]=uint8((V>>2)&0xFF);Q[3]=255;}}
}
inline uint64 Checksum(const uint8* Bgra,int32 Width,int32 Height,int32& MaxChannel){ // FNV-1a over B,G,R of an 8x8 grid of pixels
 uint64 Hash=14695981039346656037ull;MaxChannel=0;
 for(int32 GY=0;GY<8;++GY)for(int32 GX=0;GX<8;++GX){const int64 X=(int64(GX)*2+1)*Width/16,Y=(int64(GY)*2+1)*Height/16;const uint8* Q=Bgra+(Y*Width+X)*4;
  for(int32 C=0;C<3;++C){Hash=(Hash^uint64(Q[C]))*1099511628211ull;if(int32(Q[C])>MaxChannel)MaxChannel=int32(Q[C]);}}
 return Hash;
}
inline bool Stamp(const uint8* In,int64 N,uint64 Seq,TArray64<uint8>& Out,int32& Width,int32& Height){
 // The baseline contract: SOI, the JFIF APP0 (when it comes first), ONE COM "seq=<n>", the other header segments (DQT, SOF0, DHT, DRI) in their order,
 // then SOS..EOI verbatim. APP1..APP15 and COM payloads are dropped (an FF D9 can then only be the EOI); any other marker (progressive, arithmetic,
 // fill bytes, a truncated segment) refuses the frame.
 Width=Height=0;if(N<8||In[0]!=0xFF||In[1]!=0xD8||In[N-2]!=0xFF||In[N-1]!=0xD9)return false;
 int64 P=2,App0=-1,App0End=-1,Sos=-1,Keep[32][2];int32 Kept=0;bool Sof=false;
 while(P+4<=N){
  if(In[P]!=0xFF)return false;const uint8 Marker=In[P+1];
  const int64 Length=(int64(In[P+2])<<8)|int64(In[P+3]);if(Length<2||P+2+Length>N)return false;
  if(Marker==0xDA){ // the SOS header must be whole and consistent (Ls = 6 + 2 Ns) with scan data and the EOI after it
   const int64 Components=P+4<N?int64(In[P+4]):0;if(Components<1||Components>4||Length!=6+2*Components||P+2+Length>N-2)return false;Sos=P;break;}
  if(Marker==0xE0&&App0<0&&Kept==0){App0=P;App0End=P+2+Length;}
  else if((Marker>=0xE0&&Marker<=0xEF)||Marker==0xFE){} // dropped
  else if(Marker==0xDB||Marker==0xC4||Marker==0xDD||Marker==0xC0){
   if(Marker==0xC0){if(Sof||Length<8)return false;Sof=true;Height=(int32(In[P+5])<<8)|int32(In[P+6]);Width=(int32(In[P+7])<<8)|int32(In[P+8]);}
   if(Kept>=32)return false;Keep[Kept][0]=P;Keep[Kept][1]=P+2+Length;++Kept;}
  else return false;
  P+=2+Length;
 }
 if(Sos<0||!Sof||Width<=0||Height<=0)return false;
 char Com[40];const int32 ComLength=std::snprintf(Com,sizeof(Com),"seq=%llu",static_cast<unsigned long long>(Seq));if(ComLength<=0||ComLength>=int32(sizeof(Com)))return false;
 const uint8 ComHead[4]={0xFF,0xFE,uint8((ComLength+2)>>8),uint8((ComLength+2)&0xFF)};
 Out.Reset();Out.Append(In,2);if(App0>=0)Out.Append(In+App0,App0End-App0);Out.Append(ComHead,4);Out.Append(reinterpret_cast<const uint8*>(Com),ComLength);
 for(int32 K=0;K<Kept;++K)Out.Append(In+Keep[K][0],Keep[K][1]-Keep[K][0]);
 Out.Append(In+Sos,N-Sos);return true;
}
inline int32 PipeMaxSize(){ // /proc/sys/fs/pipe-max-size (best effort)
 const int Fd=::open("/proc/sys/fs/pipe-max-size",O_RDONLY|O_CLOEXEC);if(Fd<0)return 1048576;char Text[32]={0};const ssize_t Got=::read(Fd,Text,sizeof(Text)-1);::close(Fd);
 const long Value=Got>0?std::strtol(Text,nullptr,10):0;return Value>=4096&&Value<=16777216?int32(Value):1048576;
}
inline void ConsumeSigpipe(){ // a SIGPIPE raised by our write stays pending in the writer thread (blocked there): take it
 sigset_t Block,Waiting;sigemptyset(&Block);sigaddset(&Block,SIGPIPE);
 if(sigpending(&Waiting)==0&&sigismember(&Waiting,SIGPIPE)){const timespec Zero{0,0};sigtimedwait(&Block,nullptr,&Zero);}
}
}
struct FSub01MainJob{uint64 Seq=0;uint32 Session=0;bool Probe=false;int32 Kind=0,Width=0,Height=0;double CapturedAt=0;TArray64<uint8> Pixels;};
struct FSub01MainFrame{uint64 Seq=0;uint32 Session=0;TArray64<uint8> Jpeg;};
