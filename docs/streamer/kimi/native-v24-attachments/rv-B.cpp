class FSub01MainTapRunnable final:public FRunnable{
public:
 TFunction<void()> Body;
 explicit FSub01MainTapRunnable(TFunction<void()>&& InBody):Body(MoveTemp(InBody)){}
 virtual uint32 Run() override{Body();return 0;}
};
class FSub01MainTap{
 // Render thread: the back buffer -> readback ring -> pooled pixel buffers. Encoder threads: BGRA8 + JPEG + stamp, released in sequence order.
 // Writer thread: the lock, the FIFO, whole frames with a deadline. The game thread sets the knobs, reads the counters, writes the status.
public:
 static constexpr int32 Slots=3,Encoders=2,ReorderMax=2,QueueMax=2,PoolMax=4,Width=1920,Height=1080;
 FString FifoPath,LockPath;std::string FifoUtf8,LockUtf8;IImageWrapperModule* Images=nullptr;FDelegateHandle Handle;bool Bound=false,Started=false;int32 PipeWanted=1048576;
 // knobs (game thread -> others)
 std::atomic<int32> On{0},Source{0},Quality{85};std::atomic<int64> PeriodUs{16667};std::atomic<const void*> GameWindow{nullptr};std::atomic<bool> FifoOk{false},Stop{false};
 // counters and diagnostics
 std::atomic<int64> Calls{0},OtherWindows{0},WrongThread{0},NoTexture{0},Captured{0},Copied{0},Encoded{0},Written{0},Bytes{0},Probes{0},ProbeJpegs{0},
  DroppedSlots{0},DroppedEncode{0},DroppedQueue{0},DroppedNoReader{0},DroppedFormat{0},DroppedStalled{0},DiscardedMidwrite{0},RateSkipped{0},
  ReadbackUs{0},CopyUs{0},EncodeUs{0},EncodeMaxUs{0},LastWriteMs{0},DupCalls{0},MissedFrames{0},FrameSpan{0},Opens{0},Cuts{0};
 std::atomic<uint64> LastSeq{0},LastChecksum{0};
 std::atomic<int32> PipeSize{0},PipeSet{0},OpenErrno{0},LockState{0},LastKind{-1},LastFormat{-1},LastWidth{0},LastHeight{0},LastPitch{0},LastRows{0},MaxChannel{-1},LastJpegWidth{0},LastJpegHeight{0},EncodeInFlight{0};
 std::atomic<bool> Reader{false},NonBlack{false},JpegOk{false};
 std::atomic<uint32> Session{0}; // the writer's output session: changes at every open and close; a frame captured for another session is never written
 // render thread only
 TUniquePtr<FRHIGPUTextureReadback> Readback[Slots];bool Pending[Slots]={false,false,false},SlotProbe[Slots]={false,false,false};uint64 SlotSeq[Slots]={0,0,0},SlotOrder[Slots]={0,0,0};uint32 SlotSession[Slots]={0,0,0};
 double SlotAt[Slots]={0,0,0};uint64 NextOrder=1,NextSeq=0;int32 RingKind=-1;double NextAt=0,ProbeAt=0,LastCallAt=0;uint32 LastFrameNumber=0;bool HaveFrame=false;
 // shared under Mutex
 std::mutex Mutex;std::condition_variable JobCv,OutCv;std::deque<FSub01MainJob> Jobs;std::deque<uint64> Outstanding;std::deque<FSub01MainFrame> Done,Out;std::vector<TArray64<uint8>> Pool;
 // writer thread only
 int Fd=-1,LockFd=-1;double NextProbeAt=0,NextLockAt=0,CutLogAt=0;int64 CutsSuppressed=0;
 FRunnableThread* Threads[Encoders+1]={};FSub01MainTapRunnable* Runnables[Encoders+1]={};
 ~FSub01MainTap(){
  StopThreads();
  if(Fd>=0)::close(Fd);if(LockFd>=0)::close(LockFd); // closing the lock's descriptor releases the flock
  if(Bound&&IsInGameThread()&&!IsEngineExitRequested()&&FSlateApplication::IsInitialized())if(FSlateRenderer* Renderer=FSlateApplication::Get().GetRenderer())Renderer->OnBackBufferReadyToPresent().Remove(Handle);
 }
 void StartThreads(){
  if(Started)return;Started=true;
  for(int32 K=0;K<=Encoders;++K){
   const bool Writer=K==Encoders;Runnables[K]=new FSub01MainTapRunnable(Writer?TFunction<void()>([this](){WriterLoop();}):TFunction<void()>([this](){EncodeLoop();}));
   Threads[K]=FRunnableThread::Create(Runnables[K],Writer?TEXT("Sub01MainTapWriter"):K==0?TEXT("Sub01MainTapEncode0"):TEXT("Sub01MainTapEncode1"),0,TPri_Normal);
  }
 }
 void StopThreads(){ // intake stops, the queues are cleared, the threads are woken and joined (the time is logged: an encode in progress finishes first)
  const double T0=FPlatformTime::Seconds();Stop.store(true);
  {std::lock_guard<std::mutex> Lock(Mutex);Jobs.clear();Out.clear();Done.clear();Outstanding.clear();}JobCv.notify_all();OutCv.notify_all();
  int32 Joined=0;
  for(int32 K=0;K<=Encoders;++K){if(Threads[K]){Threads[K]->WaitForCompletion();delete Threads[K];Threads[K]=nullptr;++Joined;}delete Runnables[K];Runnables[K]=nullptr;}
  if(Joined>0)UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_MAIN_TAP_STOPPED threads=%d join_ms=%.1f written=%lld cuts=%lld"),Joined,(FPlatformTime::Seconds()-T0)*1000.,
   static_cast<long long>(Written.load()),static_cast<long long>(Cuts.load()));
 }
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
