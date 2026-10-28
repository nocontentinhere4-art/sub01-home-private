 // ---- render thread
 void OnBackBuffer(SWindow& Window,ISlateViewportProvider& Provider){ // FSlateRenderer::OnBackBufferReadyToPresent: render thread, before any present
  if(Source.load()!=0)return;
  const void* Want=GameWindow.load();if(!Want||static_cast<const void*>(&Window)!=Want){++OtherWindows;return;}
  if(!IsInRenderingThread()){++WrongThread;return;}
  FTextureRHIRef Held=Provider.GetBackBufferResource(); // held until its copy is enqueued
  Pump(FRHICommandListImmediate::Get(),Held.GetReference());
 }
 void Pump(FRHICommandListImmediate& RHICmdList,FRHITexture* Texture){
  const double T0=FPlatformTime::Seconds();++Calls;
  const uint32 Frame=GFrameNumberRenderThread; // one call per render frame expected
  if(HaveFrame){if(Frame==LastFrameNumber)++DupCalls;else{const uint32 Gap=Frame-LastFrameNumber;FrameSpan+=int64(Gap);if(Gap>1)MissedFrames+=int64(Gap-1);}}
  LastFrameNumber=Frame;HaveFrame=true;const double Interval=LastCallAt>0?FMath::Min(T0-LastCallAt,.1):0.;LastCallAt=T0;
  Collect();
  if(On.load()==0||!FifoOk.load()){ReadbackUs+=int64((FPlatformTime::Seconds()-T0)*1e6);return;}
  if(!Texture){++NoTexture;return;}
  const FRHITextureDesc& Desc=Texture->GetDesc();const int32 Kind=Sub01MainTap::Classify(Desc.Format);
  LastFormat.store(int32(Desc.Format));LastKind.store(Kind);LastWidth.store(Desc.Extent.X);LastHeight.store(Desc.Extent.Y);
  if(Kind==Sub01MainTap::KindUnknown||Desc.Extent.X!=Width||Desc.Extent.Y!=Height){++DroppedFormat;return;}
  if(Kind!=RingKind){ResetRing();RingKind=Kind;} // the staging textures take the source's format when they are created
  bool Probe=false;
  if(!Reader.load()){if(T0<ProbeAt)return;ProbeAt=T0+1.0;Probe=true;} // no reader: one diagnostic readback per 1.0 s
  else{const double Period=double(PeriodUs.load())*1e-6;
   if(T0+.5*(Interval>0?Interval:Period)<NextAt){++RateSkipped;return;} // main_fps (half a frame of tolerance)
   NextAt+=Period;if(NextAt<T0)NextAt=T0+Period;}
  int32 Free=-1;for(int32 S=0;S<Slots&&Free<0;++S)if(!Pending[S])Free=S;
  if(Free<0){if(!Probe)++DroppedSlots;return;} // the GPU is 3 copies behind
  if(!Readback[Free])Readback[Free]=MakeUnique<FRHIGPUTextureReadback>(TEXT("Sub01StreamerMainTap"));
  RHICmdList.Transition(FRHITransitionInfo(Texture,ERHIAccess::Unknown,ERHIAccess::CopySrc)); // PixelCapture's pattern; Slate's present transitions it again
  Readback[Free]->EnqueueCopy(RHICmdList,Texture);
  Pending[Free]=true;SlotProbe[Free]=Probe;SlotOrder[Free]=NextOrder++;SlotSeq[Free]=Probe?0:++NextSeq;SlotAt[Free]=T0;SlotSession[Free]=Session.load(); // the sequence at acceptance
  if(Probe)++Probes;else ++Captured;
  ReadbackUs+=int64((FPlatformTime::Seconds()-T0)*1e6);
 }
 void ResetRing(){for(int32 S=0;S<Slots;++S){if(Pending[S]&&!SlotProbe[S])++DroppedFormat;Pending[S]=false;Readback[S].Reset();}}
 void Collect(){
  // finished copies, OLDEST first (a newer one never overtakes an older one), every one of them; the fence is polled, never waited on
  for(;;){
   int32 S=-1;for(int32 K=0;K<Slots;++K)if(Pending[K]&&(S<0||SlotOrder[K]<SlotOrder[S]))S=K;
   if(S<0||!Readback[S]->IsReady())return;
   if(!SlotProbe[S]&&Reader.load()&&EncodeInFlight.load()>=Encoders)return; // no encoder free: it stays pending (in order); a full ring drops the NEWEST capture
   Pending[S]=false;
   if(SlotProbe[S]){if(EncodeInFlight.load()>0)continue;} // a diagnostic copy never delays the stream
   else if(!Reader.load()){++DroppedNoReader;continue;} // the reader left during the copy
   const double C0=FPlatformTime::Seconds();int32 Pitch=0,Rows=0; // Lock: the row pitch in PIXELS
   const uint8* Mapped=static_cast<const uint8*>(Readback[S]->Lock(Pitch,&Rows));LastPitch.store(Pitch);LastRows.store(Rows);
   if(!Mapped||Pitch<Width||Rows<Height){if(Mapped)Readback[S]->Unlock();if(!SlotProbe[S])++DroppedFormat;continue;}
   FSub01MainJob Job;Job.Seq=SlotSeq[S];Job.Session=SlotSession[S];Job.Probe=SlotProbe[S];Job.Kind=RingKind;Job.Width=Width;Job.Height=Height;Job.CapturedAt=SlotAt[S];Job.Pixels=TakeBuffer();
   Job.Pixels.SetNumUninitialized(int64(Width)*Height*4);
   for(int32 Y=0;Y<Height;++Y)FMemory::Memcpy(Job.Pixels.GetData()+int64(Y)*Width*4,Mapped+int64(Y)*Pitch*4,size_t(Width)*4);
   Readback[S]->Unlock();++Copied;CopyUs+=int64((FPlatformTime::Seconds()-C0)*1e6);
   {std::lock_guard<std::mutex> Lock(Mutex);if(!Job.Probe){EncodeInFlight.fetch_add(1);Outstanding.push_back(Job.Seq);}Jobs.push_back(MoveTemp(Job));}
   JobCv.notify_one();
  }
 }
 TArray64<uint8> TakeBuffer(){std::lock_guard<std::mutex> Lock(Mutex);if(Pool.empty())return TArray64<uint8>();TArray64<uint8> Buffer=MoveTemp(Pool.back());Pool.pop_back();return Buffer;}
