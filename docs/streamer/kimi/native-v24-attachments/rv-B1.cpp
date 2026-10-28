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
