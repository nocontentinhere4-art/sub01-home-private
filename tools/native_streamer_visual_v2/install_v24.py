"""v24 ON TOP of v23: the main view handed to the director without an X11 present (offscreen game, -RenderOffScreen).

    python tools/native_streamer_visual_v2/install_v24.py --source <dir> [--dry-run]

Requires v23 (and so v22/v21) in Sub01HomeLab.h/.cpp, the only two files this layer edits; refused when
`// SUB01_STREAMER_VISUAL_V2_V24` is already present or any anchor is not found exactly once (all or nothing; the same atomic
writes, line endings and JSON report as the other layers). Spec: docs/streamer/SAWTOOTH-20261024.md "Structural fix" steps 1-3
and 6. Decided with Kimi (docs/streamer/kimi/native-v24-design.md); code reviewed by Kimi (docs/streamer/kimi/native-v24-review*.md).

Engine facts this layer relies on (UE 5.8.3 source, read on the pod): `FSlateRenderer::OnBackBufferReadyToPresent()` is a
thread-safe multicast delegate `(SWindow&, ISlateViewportProvider&)` broadcast first thing in
`FSlateRHIRenderer::PresentWindow_RenderThread` (render thread, after the Slate RDG graph ran, before any present) for every
drawn window. With -RenderOffScreen the Linux application is the NULL platform application, `FNullWindow::IsRenderingOffScreen()`
is true and the window's "back buffer" is a plain texture (`SlateOffScreenViewportTexture`, format `r.DefaultBackBufferPixelFormat`,
4 = PF_A2B10G10R10 by default) that the scene viewport renders into and Slate composites onto; nothing is presented. The spec's
fallback (OnEndFrameRT + the FSceneViewport render target) is null in game mode (EnqueueEndRenderFrame releases it), so the
fallback here (`main_source` 1) is a render command per game tick that reads the same back buffer through
`FSlateRenderer::GetViewportProvider` (the previous frame's final picture).

1. The tap (`main_tap` 1; compiled default "auto" = 1 when Slate renders offscreen, else 0): on the render thread, for the game
   window only (other windows counted), the back buffer is held (FTextureRHIRef) until its copy is enqueued: extent WIDTH x HEIGHT
   and a known format (B8G8R8A8, R8G8B8A8, A2B10G10R10) or the frame is dropped (dropped_format); Unknown -> CopySrc transition
   (PixelCapture's pattern), FRHIGPUTextureReadback::EnqueueCopy into a ring of SLOTS (none free = dropped_slots; the ring is rebuilt
   when the format changes). Finished copies are taken OLDEST first (never a newer before an older one), every one of them (cam2
   keeps only the newest): with fewer than ENCODERS sequences unreleased (a place frees when its frame is RELEASED in order, not when
   its encode ends, so nothing overtakes a stalled encode) it is locked (the fence is ready: no RHI flush; the pitch is in pixels),
   its rows copied (pitch-aware) into a pooled buffer and queued; with no place free it stays pending in its slot, so a slow encoder
   backs up into the ring and a full ring drops the newest capture (dropped_slots). `main_fps` caps the rate (half a
   frame of tolerance). The render-thread cost (the ~8.3 MB copy) is logged as copy_ms and must pass the frame-time gates.
2. ENCODERS dedicated encoder threads (FRunnableThread, not the task pool): BGRA8 conversion (A2B10G10R10 -> 8 bit per channel by
   >>2: the SDR back buffer is display-encoded, no tone mapping; R8G8B8A8 swizzled), a checksum of 64 sampled pixels with their max
   channel, IImageWrapperModule::CompressImage(JPEG, `main_quality`) = a new TurboJPEG wrapper per call, baseline 4:2:0 JFIF,
   full-range YCbCr like cam2; the header is rebuilt (bounds-checked) as SOI, the JFIF APP0, ONE COM `seq=<n>`, then every other
   header segment except APP1..APP15 and COM; SOF0 WIDTH x HEIGHT and the final EOI are checked (else dropped_encode). A reorder
   buffer releases frames strictly in sequence order into an output queue of QUEUE_MAX (full: the oldest is dropped, dropped_queue).
   The sequence is assigned when a capture is accepted (after the reader and rate gates) and every accepted sequence ends exactly
   once (written, or one drop counter), so the gaps the director counts are the post-acceptance drops; frames skipped by the gates
   never get a sequence.
3. ONE writer thread: an flock(LOCK_EX|LOCK_NB) on LOCK_NAME while the tap is on (another writer holds it: no output, retried every
   LOCK_RETRY_S s), the FIFO FIFO_NAME created by the game (mkfifo 0600; an existing path that is not this uid's FIFO without
   group/other bits is refused, never replaced), probed with open(O_WRONLY|O_NONBLOCK|O_NOFOLLOW) every PROBE_S s (ENXIO = no reader),
   F_SETPIPE_SZ to /proc/sys/fs/pipe-max-size (best effort, result and F_GETPIPE_SZ logged). SIGPIPE is blocked in the writer thread's
   own mask (a broken pipe gives EPIPE; the process-wide disposition is untouched). Each frame: write in a loop, EAGAIN ->
   poll(POLLOUT) in slices of at most SLICE_MS ms (stop flag between slices), EINTR retried, partial writes resumed, a DEADLINE_S
   deadline; EPIPE, any other error, POLLERR/POLLHUP or the deadline close the fd and discard the WHOLE frame
   (frames_discarded_midwrite when bytes went out, else dropped_noreader / dropped_stalled): a tail is never resumed on a new fd, the
   reader resyncs on the next SOI. Every open and close starts a new output session; a frame captured for another session is
   dropped (dropped_noreader), so nothing stale crosses a reconnect.
4. Without a reader nothing is read back or encoded, except one diagnostic readback per DIAG_S s (converted, checksummed, JPEG-encoded
   and discarded) so the go/no-go and STATUS_NAME stay informative without the director. `main_tap` 0 closes the FIFO and releases
   the lock.
5. STATUS_NAME every STATUS_S s from the game thread (tmp + rename), only while this process holds the writer lock (a second game
   never overwrites the active writer's status; with the tap off it goes stale, which the director treats as "no main view"): the
   spec's fields and diagnostics. `sequence` = the seq of the last frame written whole, `fps` = frames written per second over the
   last status window, `last_write_utc` = when that frame's last byte went in; every counter is cumulative since the game started;
   `go` = PENDING | GO | NO-GO of the current go/no-go window.
6. Go/no-go, logged once per window (`SUB01_STREAMER_VISUAL_MAIN_TAP_GONOGO verdict=GO|NO-GO reason=...`); a window opens when the
   tap is switched on and again when the source, the format or the extent changes, and is judged after GONOGO_FRAMES render frames
   (a black picture waits up to GONOGO_TIMEOUT_S s; no call at all is judged after NO_CALLS_S s). GO needs: the delegate bound,
   every call on the render thread, raw game-window calls per render frame within FIRE_TOLERANCE (counted before the reader and
   rate gates), duplicate calls <= DUP_MAX and missed render frames <= MISS_MAX of the window (independent criteria), extent
   WIDTH x HEIGHT, a known pixel format, a readback whose pitch/rows cover the image, a non-black picture (a sampled 8-bit channel
   > NONBLACK_MIN) and a valid stamped JPEG, all within the window; the held reference is structural. `SUB01_STREAMER_VISUAL_MAIN_TAP
   fps=...` every LOG_S s; `..._MAIN_TAP_STOPPED join_ms=` at teardown.
7. cam2 evidence (the 52-53 of 60 written fps, docs/streamer/kimi/native-v24-design.md): cam2.json gains `pipe_size` and
   `full_queued_max_kb` (FIONREAD seen at the drops for a full pipe since the last status); cam2's writer is unchanged.
Tuning keys (the private tuning file, their own V24 block): main_tap, main_fps, main_quality, main_source.
Teardown: the character has no EndPlay in the files this layer owns, so (like the monitor feed) the tap stops when it is destroyed:
the delegate holds it weakly (AddSP; the broadcast pins it during a call); its destructor stops and joins its threads, closes the
FIFO and the lock and removes the delegate binding when it runs on the game thread outside engine exit.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, _HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


v23 = _load('sub01_streamer_visual_v2_v23', 'install_v23.py')
v22 = _load('sub01_streamer_visual_v2_v22', 'install_v22.py')
v21, cam2, streampass = v23.v21, v23.cam2, v23.streampass
seatfix, v2, Refused = streampass.seatfix, streampass.v2, streampass.Refused
_f = streampass._f

MARKER = '// SUB01_STREAMER_VISUAL_V2_V24'
FILES = {'header': 'Sub01HomeLab.h', 'cpp': 'Sub01HomeLab.cpp'}
SCHEMA = 'sub01.native-streamer-visual-v2-v24-install.v1'

FIFO_NAME, LOCK_NAME, STATUS_NAME = 'main.mjpeg', 'main.mjpeg.lock', 'main.json'   # the contract with the director (spec step 3)
STATUS_SCHEMA = 'sub01.streamer-main-status.v1'
COM_PREFIX = 'seq='                                  # the one COM segment of every frame: `seq=<n>` in ASCII
WIDTH, HEIGHT = 1920, 1080
SLOTS, ENCODERS, REORDER_MAX, QUEUE_MAX = 3, 2, 2, 2   # spec: readback slots 3, encodes in flight 2, reorder buffer 2, output queue 2
POOL_MAX = 4                                          # pooled 8.3 MB pixel buffers (no page faults per frame)
DEADLINE_S, SLICE_MS = 0.5, 20                        # per-frame write deadline; poll slices (the stop flag is checked between them)
PROBE_S, LOCK_RETRY_S, IDLE_MS = 1.0, 5.0, 100        # reader probe; lock retry; the writer's idle wait
PIPE_FALLBACK = 1 << 20                               # F_SETPIPE_SZ request when /proc/sys/fs/pipe-max-size cannot be read
PIPE_CAP = 16 << 20
STATUS_S, LOG_S, DIAG_S = 1.0, 10.0, 1.0
MAIN_TAP_AUTO, MAIN_FPS, MAIN_QUALITY, MAIN_SOURCE = -1, 60.0, 85.0, 0
GONOGO_FRAMES, GONOGO_TIMEOUT_S, NO_CALLS_S = 600, 120.0, 30.0
FIRE_TOLERANCE = (0.95, 1.05)
DUP_MAX, MISS_MAX = 0.01, 0.05                         # independent go/no-go limits: duplicate calls <= 1 %, missed render frames <= 5 % of the window
NONBLACK_MIN = 16                                     # a sampled 8-bit channel above this = not black
CUT_LOG_S = 5.0                                       # at most one cut line per this many seconds (the rest counted)
TUNING_LIMITS = {'main_tap': (0, 1), 'main_fps': (1, 60), 'main_quality': (40, 95), 'main_source': (0, 1)}
TUNING_FIELDS = {'main_tap': 'StreamerVisualMainTapOn', 'main_fps': 'StreamerVisualMainFps', 'main_quality': 'StreamerVisualMainQuality',
                 'main_source': 'StreamerVisualMainSource'}
assert set(TUNING_FIELDS) == set(TUNING_LIMITS) and SLOTS == 3 and REORDER_MAX >= ENCODERS
STATUS_FIELDS = ('sequence', 'fps', 'written', 'dropped_slots', 'dropped_encode', 'dropped_queue', 'dropped_noreader',
                 'frames_discarded_midwrite', 'pipe_size', 'last_write_utc')   # spec step 3, verbatim


def _fill(text: str, **values) -> str:
    """C++ blocks carry @@NAME@@ placeholders (no f-string brace doubling); every placeholder must be filled."""
    for key, value in values.items():
        text = text.replace(f'@@{key}@@', value if isinstance(value, str) else _num(value))
    assert '@@' not in text, text[text.index('@@') - 60:text.index('@@') + 60]
    return text


def _num(value) -> str:
    return str(value) if isinstance(value, int) else repr(float(value))


COMMON = dict(FIFO=FIFO_NAME, LOCK=LOCK_NAME, STATUS=STATUS_NAME, STATUS_SCHEMA=STATUS_SCHEMA, COM=COM_PREFIX, W=WIDTH, H=HEIGHT,
              SLOTS=SLOTS, ENCODERS=ENCODERS, REORDER=REORDER_MAX, QUEUE=QUEUE_MAX, POOL=POOL_MAX, DEADLINE=DEADLINE_S, SLICE=SLICE_MS,
              PROBE=PROBE_S, LOCK_RETRY=LOCK_RETRY_S, IDLE=IDLE_MS, PIPE_FALLBACK=PIPE_FALLBACK, PIPE_CAP=PIPE_CAP, STATUS_S=STATUS_S,
              LOG=LOG_S, DIAG=DIAG_S, GONOGO_FRAMES=GONOGO_FRAMES, GONOGO_TIMEOUT=GONOGO_TIMEOUT_S, NO_CALLS=NO_CALLS_S,
              FIRE_LO=FIRE_TOLERANCE[0], FIRE_HI=FIRE_TOLERANCE[1], NONBLACK=NONBLACK_MIN, CUT_LOG=CUT_LOG_S, DUP_DIV=round(1 / DUP_MAX),
              MISS_DIV=round(1 / MISS_MAX))

# ------------------------------------------------------------------------------------------------ Sub01HomeLab.h
HEADER_V22_END = ' // SUB01_STREAMER_VISUAL_V2_V22 END\n'
HEADER_FIELDS = _fill(''' // SUB01_STREAMER_VISUAL_V2_V24 BEGIN (tools/native_streamer_visual_v2/install_v24.py): the main view (the Slate back buffer; offscreen: a
 // texture, no present) to <streamer-dir>/@@FIFO@@ for the director, @@STATUS@@ every second, the go/no-go line.
 void StartStreamerVisualMainTap();void UpdateStreamerVisualMainTap(double Now,float Dt);void WriteStreamerVisualMainStatus(double Now);void LogStreamerVisualMainTap(double Now);
 void JudgeStreamerVisualMainTap(double Now);void ArmStreamerVisualMainTap(double Now);
 TSharedPtr<class FSub01MainTap> StreamerVisualMainTap; // shared with the render thread (the back-buffer delegate) and the tap's own threads
 FString StreamerVisualMainReason,StreamerVisualMainVerdict=TEXT("PENDING"),StreamerVisualMainWhy=TEXT("not armed");int64 StreamerVisualMainShape=-1;
 float StreamerVisualMainTapOn=@@AUTO@@,StreamerVisualMainFps=@@FPS@@,StreamerVisualMainQuality=@@QUALITY@@,StreamerVisualMainSource=@@SOURCE@@; // main_tap -1 = auto, resolved at start
 bool StreamerVisualMainOffscreen=false,StreamerVisualMainArmed=false,StreamerVisualMainJudged=false;int32 StreamerVisualMainArmedSource=-1;
 double StreamerVisualMainStatusAt=0,StreamerVisualMainStatusWindowAt=0,StreamerVisualMainLogAt=0,StreamerVisualMainLogWindowAt=0,StreamerVisualMainArmedAt=0;
 int64 StreamerVisualMainStatusBase[2]={0,0},StreamerVisualMainLogBase[4]={0,0,0,0},StreamerVisualMainGoBase[5]={0,0,0,0,0};float StreamerVisualMainFpsWritten=0,StreamerVisualMainFpsCaptured=0;
 // SUB01_STREAMER_VISUAL_V2_V24 END
''', AUTO=_f(MAIN_TAP_AUTO), FPS=_f(MAIN_FPS), QUALITY=_f(MAIN_QUALITY), SOURCE=_f(MAIN_SOURCE), **COMMON)

# ------------------------------------------------------------------------------------------------ Sub01HomeLab.cpp
INCLUDE_ANCHOR = '#include "IImageWrapper.h"\n#include <vector>\n#include <deque>\n#include <cstring>\n'
INCLUDE_V24 = INCLUDE_ANCHOR + ('#include "Framework/Application/SlateApplication.h" // SUB01_STREAMER_VISUAL_V2_V24: the main-view tap (the Slate back buffer)\n'
                                '#include "Rendering/SlateRenderer.h"\n#include "Slate/SlateViewportProvider.h"\n#include "Widgets/SWindow.h"\n'
                                '#include "Engine/GameViewportClient.h"\n#include "HAL/Runnable.h"\n#include "HAL/RunnableThread.h"\n'
                                '#include <mutex>\n#include <condition_variable>\n#include <chrono>\n#include <string>\n#include <poll.h>\n#include <sys/file.h>\n')
CPP_V22_END = '\n// SUB01_STREAMER_VISUAL_V2_V22 END\n'
CPP_METHODS = _fill(r'''// SUB01_STREAMER_VISUAL_V2_V24 BEGIN (tools/native_streamer_visual_v2/install_v24.py)
// ---- the main view to the director without an X11 present: the Slate back buffer (offscreen: a texture) -> a GPU readback ring (render thread)
// ---- -> @@ENCODERS@@ encoder threads (BGRA8, JPEG, one COM "@@COM@@<n>") -> in-order output queue -> ONE writer thread -> <streamer-dir>/@@FIFO@@
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
 // The baseline contract: SOI, the JFIF APP0 (when it comes first), ONE COM "@@COM@@<n>", the other header segments (DQT, SOF0, DHT, DRI) in their order,
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
 char Com[40];const int32 ComLength=std::snprintf(Com,sizeof(Com),"@@COM@@%llu",static_cast<unsigned long long>(Seq));if(ComLength<=0||ComLength>=int32(sizeof(Com)))return false;
 const uint8 ComHead[4]={0xFF,0xFE,uint8((ComLength+2)>>8),uint8((ComLength+2)&0xFF)};
 Out.Reset();Out.Append(In,2);if(App0>=0)Out.Append(In+App0,App0End-App0);Out.Append(ComHead,4);Out.Append(reinterpret_cast<const uint8*>(Com),ComLength);
 for(int32 K=0;K<Kept;++K)Out.Append(In+Keep[K][0],Keep[K][1]-Keep[K][0]);
 Out.Append(In+Sos,N-Sos);return true;
}
inline int32 PipeMaxSize(){ // /proc/sys/fs/pipe-max-size (best effort)
 const int Fd=::open("/proc/sys/fs/pipe-max-size",O_RDONLY|O_CLOEXEC);if(Fd<0)return @@PIPE_FALLBACK@@;char Text[32]={0};const ssize_t Got=::read(Fd,Text,sizeof(Text)-1);::close(Fd);
 const long Value=Got>0?std::strtol(Text,nullptr,10):0;return Value>=4096&&Value<=@@PIPE_CAP@@?int32(Value):@@PIPE_FALLBACK@@;
}
inline void ConsumeSigpipe(){ // a SIGPIPE raised by our write stays pending in the writer thread (blocked there): take it
 sigset_t Block,Waiting;sigemptyset(&Block);sigaddset(&Block,SIGPIPE);
 if(sigpending(&Waiting)==0&&sigismember(&Waiting,SIGPIPE)){const timespec Zero{0,0};sigtimedwait(&Block,nullptr,&Zero);}
}
}
struct FSub01MainJob{uint64 Seq=0;uint32 Session=0;bool Probe=false;int32 Kind=0,Width=0,Height=0;double CapturedAt=0;TArray64<uint8> Pixels;};
struct FSub01MainFrame{uint64 Seq=0;uint32 Session=0;TArray64<uint8> Jpeg;};
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
 static constexpr int32 Slots=@@SLOTS@@,Encoders=@@ENCODERS@@,ReorderMax=@@REORDER@@,QueueMax=@@QUEUE@@,PoolMax=@@POOL@@,Width=@@W@@,Height=@@H@@;
 FString FifoPath,LockPath;std::string FifoUtf8,LockUtf8;IImageWrapperModule* Images=nullptr;FDelegateHandle Handle;bool Bound=false,Started=false;int32 PipeWanted=@@PIPE_FALLBACK@@;
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
  // Never concurrent with OnBackBuffer/Pump: the delegate's SP binding pins the tap for each call (TBaseSPMethodDelegateInstance::
  // ExecuteIfSafe) and the main_source 1 command holds a reference, so this may run on the render thread when that was the last one; a
  // binding left behind (engine exit) only finds an expired weak pointer. One-shot: StopThreads runs here only, the threads never restart.
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
  if(!Reader.load()){if(T0<ProbeAt)return;ProbeAt=T0+@@DIAG@@;Probe=true;} // no reader: one diagnostic readback per @@DIAG@@ s
  else{const double Period=double(PeriodUs.load())*1e-6;
   if(T0+.5*(Interval>0?Interval:Period)<NextAt){++RateSkipped;return;} // main_fps (half a frame of tolerance)
   NextAt+=Period;if(NextAt<T0)NextAt=T0+Period;}
  int32 Free=-1;for(int32 S=0;S<Slots&&Free<0;++S)if(!Pending[S])Free=S;
  if(Free<0){if(!Probe)++DroppedSlots;return;} // the GPU is @@SLOTS@@ copies behind
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
   const bool Live=Reader.load(); // read once: the in-flight bound below must hold for every job queued
   if(!SlotProbe[S]&&Live&&EncodeInFlight.load()>=Encoders)return; // no place free: it stays pending (in order); a full ring drops the NEWEST capture
   Pending[S]=false;
   if(SlotProbe[S]){if(EncodeInFlight.load()>0)continue;} // a diagnostic copy never delays the stream
   else if(!Live){++DroppedNoReader;continue;} // the reader left during the copy
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
 // ---- encoder threads
 void EncodeLoop(){
  for(;;){
   FSub01MainJob Job;
   {std::unique_lock<std::mutex> Lock(Mutex);JobCv.wait(Lock,[this](){return Stop.load()||!Jobs.empty();});if(Stop.load())return;Job=MoveTemp(Jobs.front());Jobs.pop_front();}
   const double T0=FPlatformTime::Seconds();uint8* Pixels=Job.Pixels.GetData();
   Sub01MainTap::ToBgra8(Pixels,int64(Job.Width)*Job.Height,Job.Kind);
   int32 Max=0;const uint64 Sum=Sub01MainTap::Checksum(Pixels,Job.Width,Job.Height,Max);LastChecksum.store(Sum);MaxChannel.store(Max);if(Max>@@NONBLACK@@)NonBlack.store(true);
   TArray64<uint8> Jpeg,Stamped;int32 JpegWidth=0,JpegHeight=0;
   const bool Ok=Images&&Images->CompressImage(Jpeg,EImageFormat::JPEG,FImageView(reinterpret_cast<const FColor*>(Pixels),Job.Width,Job.Height),Quality.load())&&Jpeg.Num()>0
    &&Sub01MainTap::Stamp(Jpeg.GetData(),Jpeg.Num(),Job.Seq,Stamped,JpegWidth,JpegHeight)&&JpegWidth==Width&&JpegHeight==Height;
   LastJpegWidth.store(JpegWidth);LastJpegHeight.store(JpegHeight);if(Ok)JpegOk.store(true);
   const int64 Us=int64((FPlatformTime::Seconds()-T0)*1e6);if(!Job.Probe){EncodeUs+=Us;if(Us>EncodeMaxUs.load())EncodeMaxUs.store(Us);}
   std::lock_guard<std::mutex> Lock(Mutex);
   if(int32(Pool.size())<PoolMax)Pool.push_back(MoveTemp(Job.Pixels));
   if(Job.Probe){if(Ok)++ProbeJpegs;continue;}
   if(Ok){++Encoded;}else ++DroppedEncode;
   FSub01MainFrame Frame;Frame.Seq=Job.Seq;Frame.Session=Job.Session;if(Ok)Frame.Jpeg=MoveTemp(Stamped);Done.push_back(MoveTemp(Frame));
   // the reorder buffer: release in sequence order (a failed encode releases its place with an empty frame). A sequence's place in
   // EncodeInFlight frees only at its RELEASE, so an early finisher never lets more work overtake a stalled encode: at most
   // Encoders sequences are unreleased, Done never holds more than Encoders-1 frames, and no frame is ever dropped from it.
   while(!Outstanding.empty()){
    int32 Found=-1;for(int32 K=0;K<int32(Done.size());++K)if(Done[size_t(K)].Seq==Outstanding.front()){Found=K;break;}
    if(Found<0)break;
    FSub01MainFrame Next=MoveTemp(Done[size_t(Found)]);Done.erase(Done.begin()+Found);Outstanding.pop_front();EncodeInFlight.fetch_sub(1);
    if(Next.Jpeg.Num()<=0)continue;
    if(int32(Out.size())>=QueueMax){Out.pop_front();++DroppedQueue;} // full: the OLDEST goes (latency stays bounded)
    Out.push_back(MoveTemp(Next));OutCv.notify_one();
   }
  }
 }
 static_assert(ReorderMax>=Encoders,"the reorder buffer holds every unreleased sequence");
 // ---- the writer thread
 void WriterLoop(){
  {sigset_t Block;sigemptyset(&Block);sigaddset(&Block,SIGPIPE);pthread_sigmask(SIG_BLOCK,&Block,nullptr);} // this thread only: a broken pipe gives EPIPE
  while(!Stop.load()){
   const double Now=FPlatformTime::Seconds();const bool Want=On.load()!=0&&FifoOk.load();
   if(!Want){CloseFifo();ReleaseLock();DropQueued();NextLockAt=NextProbeAt=0;WaitIdle();continue;} // main_tap 0: the director sees EOF, another game may take the lock (switched on again: both are tried at once)
   if(LockState.load()!=1){if(Now>=NextLockAt){NextLockAt=Now+@@LOCK_RETRY@@;TakeLock();}if(LockState.load()!=1){DropQueued();WaitIdle();continue;}}
   if(Fd<0){if(Now>=NextProbeAt){NextProbeAt=Now+@@PROBE@@;OpenFifo();}if(Fd<0){DropQueued();WaitIdle();continue;}}
   FSub01MainFrame Frame;bool Have=false;
   {std::unique_lock<std::mutex> Lock(Mutex);OutCv.wait_for(Lock,std::chrono::milliseconds(@@IDLE@@),[this](){return Stop.load()||!Out.empty();});
    if(!Out.empty()){Frame=MoveTemp(Out.front());Out.pop_front();Have=true;}}
   if(!Have){if(ReaderGone())CloseFifo();continue;} // idle: notice a reader that left without writing
   if(Frame.Session!=Session.load()){++DroppedNoReader;continue;} // captured for an earlier output session: never crosses a reconnect
   WriteWhole(Frame);
  }
  CloseFifo();
 }
 void WaitIdle(){std::unique_lock<std::mutex> Lock(Mutex);OutCv.wait_for(Lock,std::chrono::milliseconds(@@IDLE@@),[this](){return Stop.load();});}
 void DropQueued(){std::lock_guard<std::mutex> Lock(Mutex);DroppedNoReader+=int64(Out.size());Out.clear();}
 void TakeLock(){
  if(LockFd<0){LockFd=::open(LockUtf8.c_str(),O_RDWR|O_CREAT|O_CLOEXEC|O_NOFOLLOW,0600);if(LockFd<0){SetLockState(3,errno);return;}}
  struct stat Info;if(::fstat(LockFd,&Info)!=0||!S_ISREG(Info.st_mode)||Info.st_uid!=getuid()){::close(LockFd);LockFd=-1;SetLockState(3,0);return;}
  if(::flock(LockFd,LOCK_EX|LOCK_NB)==0)SetLockState(1,0);else SetLockState(errno==EWOULDBLOCK?2:3,errno);
 }
 void ReleaseLock(){if(LockFd>=0){::close(LockFd);LockFd=-1;}if(LockState.load()!=0)SetLockState(0,0);}
 void SetLockState(int32 State,int Error){
  if(LockState.exchange(State)==State)return;
  UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_MAIN_TAP_LOCK state=%s errno=%d lock=%s"),State==1?TEXT("held"):State==2?TEXT("busy (another writer holds it)"):State==3?TEXT("error"):TEXT("released"),Error,*LockPath);
 }
 void OpenFifo(){
  struct stat Info;
  if(::lstat(FifoUtf8.c_str(),&Info)!=0||!S_ISFIFO(Info.st_mode)||Info.st_uid!=getuid()||(Info.st_mode&0077)){OpenErrno.store(errno);return;}
  const int Opened=::open(FifoUtf8.c_str(),O_WRONLY|O_NONBLOCK|O_CLOEXEC|O_NOFOLLOW);
  if(Opened<0){OpenErrno.store(errno==ENXIO?0:errno);return;} // ENXIO: nobody reads it yet
  if(::fstat(Opened,&Info)!=0||!S_ISFIFO(Info.st_mode)||Info.st_uid!=getuid()||(Info.st_mode&0077)){::close(Opened);return;}
  const int Set=::fcntl(Opened,F_SETPIPE_SZ,PipeWanted),SetErrno=Set<0?errno:0;const int Size=::fcntl(Opened,F_GETPIPE_SZ); // best effort; never assumed
  Fd=Opened;PipeSet.store(Set);PipeSize.store(Size);OpenErrno.store(0);++Opens;Session.fetch_add(1);Reader.store(true); // a new session, then captures may start
  UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_MAIN_TAP_FIFO reader=1 opens=%d pipe_requested=%d set=%d set_errno=%d pipe_size=%d fifo=%s"),int32(Opens.load()),PipeWanted,Set,SetErrno,Size,*FifoPath);
 }
 void CloseFifo(){if(Fd>=0){::close(Fd);Fd=-1;Session.fetch_add(1);}Reader.store(false);}
 bool ReaderGone(){ // a pipe's write end reports POLLERR once no reader is left
  if(Fd<0)return true;struct pollfd P;P.fd=Fd;P.events=POLLOUT;P.revents=0;return ::poll(&P,1,0)>0&&(P.revents&(POLLERR|POLLHUP|POLLNVAL))!=0;
 }
 bool WriteWhole(const FSub01MainFrame& Frame){
  const uint8* Data=Frame.Jpeg.GetData();const int64 Size=Frame.Jpeg.Num();int64 Sent=0;int32 Why=0; // 1 no reader, 2 error, 3 deadline, 4 stop
  const double Deadline=FPlatformTime::Seconds()+@@DEADLINE@@;
  while(Sent<Size){
   if(Stop.load()){Why=4;break;}
   double Left=Deadline-FPlatformTime::Seconds();if(Left<=0){Why=3;break;} // the deadline bounds the whole frame, a slow trickle of partial writes too
   const ssize_t N=::write(Fd,Data+Sent,size_t(Size-Sent));
   if(N>0){Sent+=int64(N);continue;}
   if(N<0&&errno==EINTR)continue;
   if(N<0&&(errno==EAGAIN||errno==EWOULDBLOCK)){
    Left=Deadline-FPlatformTime::Seconds();if(Left<=0){Why=3;break;}
    struct pollfd P;P.fd=Fd;P.events=POLLOUT;P.revents=0;
    const int Ready=::poll(&P,1,int(FMath::Clamp(Left*1000.,1.,double(@@SLICE@@))));
    if(Ready<0&&errno!=EINTR){Why=2;break;}
    if(Ready>0&&(P.revents&(POLLERR|POLLHUP|POLLNVAL))){Why=1;break;}
    continue;
   }
   Why=N<0&&errno==EPIPE?1:2;break;
  }
  if(Sent>=Size){++Written;Bytes+=Size;LastSeq.store(Frame.Seq);const FDateTime Utc=FDateTime::UtcNow();LastWriteMs.store(Utc.ToUnixTimestamp()*1000+Utc.GetMillisecond());return true;}
  // the WHOLE frame is discarded and the descriptor closed: its tail is never resumed on a new fd; the reader resyncs on the next SOI
  if(Sent>0)++DiscardedMidwrite;else if(Why==3)++DroppedStalled;else ++DroppedNoReader;
  ++Cuts;CloseFifo();Sub01MainTap::ConsumeSigpipe();
  const double Now=FPlatformTime::Seconds();
  if(Now>=CutLogAt){CutLogAt=Now+@@CUT_LOG@@;
   UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_MAIN_TAP_CUT why=%s seq=%llu sent=%lld of=%lld cuts=%lld suppressed=%lld"),Why==1?TEXT("no reader"):Why==3?TEXT("deadline"):Why==4?TEXT("stop"):TEXT("write error"),
    static_cast<unsigned long long>(Frame.Seq),static_cast<long long>(Sent),static_cast<long long>(Size),static_cast<long long>(Cuts.load()),static_cast<long long>(CutsSuppressed));CutsSuppressed=0;}
  else ++CutsSuppressed;
  return false;
 }
};
void ASub01HomeCharacter::StartStreamerVisualMainTap(){
 // Once per process at v2 start (next to cam2): the FIFO (mkfifo 0600 when absent; never replaced), the tap and its back-buffer delegate. Its
 // threads start when the tap is first switched on (main_tap; auto = on when Slate renders offscreen).
 if(StreamerVisualMainTap)return;
 StreamerVisualMainOffscreen=FSlateApplication::IsInitialized()&&FSlateApplication::Get().IsRenderingOffScreen();
 if(StreamerVisualMainTapOn<0)StreamerVisualMainTapOn=StreamerVisualMainOffscreen?1.f:0.f; // main_tap auto (a value from the tuning file wins)
 StreamerVisualMainTap=MakeShared<FSub01MainTap>();FSub01MainTap& Tap=*StreamerVisualMainTap;
 Tap.FifoPath=StreamerVisualCam2Dir+TEXT("/@@FIFO@@");Tap.LockPath=StreamerVisualCam2Dir+TEXT("/@@LOCK@@");Tap.FifoUtf8=TCHAR_TO_UTF8(*Tap.FifoPath);Tap.LockUtf8=TCHAR_TO_UTF8(*Tap.LockPath);
 Tap.Images=&FModuleManager::LoadModuleChecked<IImageWrapperModule>(FName(TEXT("ImageWrapper")));Tap.PipeWanted=Sub01MainTap::PipeMaxSize();
 ::mkdir(TCHAR_TO_UTF8(*StreamerVisualCam2Dir),0700);struct stat S;StreamerVisualMainReason.Empty();
 if(::lstat(Tap.FifoUtf8.c_str(),&S)!=0){if(::mkfifo(Tap.FifoUtf8.c_str(),0600)!=0)StreamerVisualMainReason=FString::Printf(TEXT("mkfifo failed errno=%d"),errno);}
 else if(!S_ISFIFO(S.st_mode)||S.st_uid!=getuid()||(S.st_mode&0077))StreamerVisualMainReason=TEXT("path exists and is not this user's private FIFO (left untouched)");
 Tap.FifoOk.store(StreamerVisualMainReason.IsEmpty());
 if(FSlateApplication::IsInitialized())if(FSlateRenderer* Renderer=FSlateApplication::Get().GetRenderer()){
  Tap.Handle=Renderer->OnBackBufferReadyToPresent().AddSP(StreamerVisualMainTap.ToSharedRef(),&FSub01MainTap::OnBackBuffer);Tap.Bound=true;}
 const double Now=FPlatformTime::Seconds();StreamerVisualMainLogAt=Now+@@LOG@@;StreamerVisualMainLogWindowAt=StreamerVisualMainStatusWindowAt=Now;StreamerVisualMainStatusAt=0;
 UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_MAIN_TAP started=%d fifo=%s offscreen=%d on=%d source=%d bound=%d size=@@W@@x@@H@@ targetFps=%.0f quality=%d pipeWanted=%d slots=@@SLOTS@@ encoders=@@ENCODERS@@ queue=@@QUEUE@@ deadlineS=@@DEADLINE@@ reason=%s"),
  StreamerVisualMainReason.IsEmpty()?1:0,*Tap.FifoPath,StreamerVisualMainOffscreen?1:0,StreamerVisualMainTapOn>0?1:0,StreamerVisualMainSource>0?1:0,Tap.Bound?1:0,StreamerVisualMainFps,int32(StreamerVisualMainQuality),Tap.PipeWanted,
  StreamerVisualMainReason.IsEmpty()?TEXT("-"):*StreamerVisualMainReason);
}
void ASub01HomeCharacter::UpdateStreamerVisualMainTap(double Now,float Dt){
 if(!StreamerVisualMainTap)return;FSub01MainTap& Tap=*StreamerVisualMainTap;
 const bool On=StreamerVisualMainTapOn>0&&Tap.FifoOk.load();const int32 Source=StreamerVisualMainSource>0?1:0;
 if(On&&!Tap.Started)Tap.StartThreads();
 Tap.Source.store(Source);Tap.Quality.store(int32(StreamerVisualMainQuality));Tap.PeriodUs.store(int64(1e6/FMath::Clamp(double(StreamerVisualMainFps),1.,60.)));
 SWindow* Window=GEngine&&GEngine->GameViewport?GEngine->GameViewport->GetWindow().Get():nullptr;Tap.GameWindow.store(Window);Tap.On.store(On?1:0);
 if(On&&Source==1&&Window&&FSlateApplication::IsInitialized()) // main_source 1: the same back buffer, read by a render command each tick (the previous frame's picture)
  if(FSlateRenderer* Renderer=FSlateApplication::Get().GetRenderer())if(ISlateViewportProvider* Provider=Renderer->GetViewportProvider(*Window)){
   ENQUEUE_RENDER_COMMAND(Sub01StreamerMainTapFallback)([Self=StreamerVisualMainTap,Provider](FRHICommandListImmediate& RHICmdList){if(Self->Source.load()!=1)return;FTextureRHIRef Held=Provider->GetBackBufferResource();Self->Pump(RHICmdList,Held.GetReference());});}
 const int64 Shape=(int64(Tap.LastKind.load()+1)<<40)|(int64(Tap.LastWidth.load()&0xFFFFF)<<20)|int64(Tap.LastHeight.load()&0xFFFFF);
 const bool Reshaped=Shape!=StreamerVisualMainShape;StreamerVisualMainShape=Shape;
 if(On&&(!StreamerVisualMainArmed||StreamerVisualMainArmedSource!=Source||Reshaped))ArmStreamerVisualMainTap(Now); // a new go/no-go window per switch-on, source, format or extent
 if(!On)StreamerVisualMainArmed=false;
 if(StreamerVisualMainArmed&&!StreamerVisualMainJudged)JudgeStreamerVisualMainTap(Now);
 if(Now>=StreamerVisualMainStatusAt&&Tap.LockState.load()==1)WriteStreamerVisualMainStatus(Now); // only the lock holder writes the status (never a second game)
 if(Now>=StreamerVisualMainLogAt)LogStreamerVisualMainTap(Now);
}
void ASub01HomeCharacter::ArmStreamerVisualMainTap(double Now){
 FSub01MainTap& Tap=*StreamerVisualMainTap;StreamerVisualMainArmed=true;StreamerVisualMainJudged=false;StreamerVisualMainArmedSource=Tap.Source.load();StreamerVisualMainArmedAt=Now;
 const int64 Base[5]={Tap.Calls.load(),Tap.FrameSpan.load(),Tap.DupCalls.load(),Tap.MissedFrames.load(),Tap.WrongThread.load()};for(int32 K=0;K<5;++K)StreamerVisualMainGoBase[K]=Base[K];
 Tap.NonBlack.store(false);Tap.JpegOk.store(false); // judged on this window's pictures only
 StreamerVisualMainVerdict=TEXT("PENDING");StreamerVisualMainWhy=TEXT("measuring");
}
void ASub01HomeCharacter::JudgeStreamerVisualMainTap(double Now){
 // The go/no-go of the hand-off path (spec step 2): once per arming, after @@GONOGO_FRAMES@@ render frames (or @@GONOGO_TIMEOUT@@ s; @@NO_CALLS@@ s without a single call).
 FSub01MainTap& Tap=*StreamerVisualMainTap;const double Age=Now-StreamerVisualMainArmedAt;
 const int64 Calls=Tap.Calls.load()-StreamerVisualMainGoBase[0],Frames=Tap.FrameSpan.load()-StreamerVisualMainGoBase[1],Dup=Tap.DupCalls.load()-StreamerVisualMainGoBase[2],Missed=Tap.MissedFrames.load()-StreamerVisualMainGoBase[3],Wrong=Tap.WrongThread.load()-StreamerVisualMainGoBase[4];
 const bool Black=!Tap.NonBlack.load();const int32 Kind=Tap.LastKind.load();
 const bool Readable=Kind!=Sub01MainTap::KindUnknown&&Tap.LastWidth.load()==FSub01MainTap::Width&&Tap.LastHeight.load()==FSub01MainTap::Height; // else no picture can ever come
 if(!(Frames>=@@GONOGO_FRAMES@@&&(!Black||!Readable||Age>=@@GONOGO_TIMEOUT@@))&&!((Calls<=1||Wrong>0)&&Age>=@@NO_CALLS@@)&&Age<@@GONOGO_TIMEOUT@@)return;
 const double Fires=Frames>0?double(Calls-1)/double(Frames):0.;
 const TCHAR* Why=nullptr;
 if(StreamerVisualMainArmedSource==0&&!Tap.Bound)Why=TEXT("the back-buffer delegate is not bound");
 else if(Wrong>0)Why=TEXT("called off the render thread");
 else if(Calls<=1)Why=StreamerVisualMainArmedSource==0?TEXT("the delegate never fired for the game window"):TEXT("the fallback command never ran");
 else if(Fires<@@FIRE_LO@@||Fires>@@FIRE_HI@@)Why=TEXT("not once per render frame");
 else if(Dup*@@DUP_DIV@@>Frames)Why=TEXT("duplicate calls in one render frame"); // independent criteria: a net ratio can hide duplicates cancelling misses
 else if(Missed*@@MISS_DIV@@>Frames)Why=TEXT("missed render frames");
 else if(Tap.LastWidth.load()!=FSub01MainTap::Width||Tap.LastHeight.load()!=FSub01MainTap::Height)Why=TEXT("back buffer extent");
 else if(Kind==Sub01MainTap::KindUnknown)Why=TEXT("unhandled pixel format");
 else if(Tap.Copied.load()<=0)Why=TEXT("no readback completed");
 else if(Tap.LastPitch.load()<FSub01MainTap::Width||Tap.LastRows.load()<FSub01MainTap::Height)Why=TEXT("readback pitch/rows");
 else if(Black)Why=TEXT("black picture (checksum)");
 else if(!Tap.JpegOk.load())Why=TEXT("no valid stamped JPEG");
 StreamerVisualMainJudged=true;StreamerVisualMainVerdict=Why?TEXT("NO-GO"):TEXT("GO");StreamerVisualMainWhy=Why?FString(Why):FString(TEXT("-"));
 UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_MAIN_TAP_GONOGO verdict=%s reason=%s source=%s fires_per_frame=%.3f calls=%lld frames=%lld dup_calls=%lld missed_frames=%lld other_windows=%lld wrong_thread=%lld extent=%dx%d format=%s(%d) pitch_px=%d rows=%d checksum=%llx max_channel=%d nonblack=%d jpeg_ok=%d jpeg=%dx%d held_ref=1 offscreen=%d window_s=%.1f"),
  *StreamerVisualMainVerdict,*StreamerVisualMainWhy,StreamerVisualMainArmedSource==0?TEXT("backbuffer-delegate"):TEXT("viewport-provider-command"),Fires,static_cast<long long>(Calls),static_cast<long long>(Frames),static_cast<long long>(Dup),
  static_cast<long long>(Missed),static_cast<long long>(Tap.OtherWindows.load()),static_cast<long long>(Wrong),Tap.LastWidth.load(),Tap.LastHeight.load(),Sub01MainTap::KindName(Kind),Tap.LastFormat.load(),Tap.LastPitch.load(),Tap.LastRows.load(),
  static_cast<unsigned long long>(Tap.LastChecksum.load()),Tap.MaxChannel.load(),Black?0:1,Tap.JpegOk.load()?1:0,Tap.LastJpegWidth.load(),Tap.LastJpegHeight.load(),StreamerVisualMainOffscreen?1:0,Age);
}
void ASub01HomeCharacter::WriteStreamerVisualMainStatus(double Now){
 // @@STATUS@@ next to the FIFO every @@STATUS_S@@ s (tmp + rename): the spec's fields first, then diagnostics.
 FSub01MainTap& Tap=*StreamerVisualMainTap;const int64 Written=Tap.Written.load(),Captured=Tap.Captured.load();
 if(StreamerVisualMainStatusWindowAt>0&&Now>StreamerVisualMainStatusWindowAt){const double Span=Now-StreamerVisualMainStatusWindowAt;
  StreamerVisualMainFpsWritten=float(double(Written-StreamerVisualMainStatusBase[0])/Span);StreamerVisualMainFpsCaptured=float(double(Captured-StreamerVisualMainStatusBase[1])/Span);}
 StreamerVisualMainStatusWindowAt=Now;StreamerVisualMainStatusBase[0]=Written;StreamerVisualMainStatusBase[1]=Captured;StreamerVisualMainStatusAt=Now+@@STATUS_S@@;
 auto Status=MakeShared<FJsonObject>();const FDateTime Utc=FDateTime::UtcNow();const int64 Last=Tap.LastWriteMs.load();
 Status->SetNumberField(TEXT("sequence"),double(Tap.LastSeq.load()));Status->SetNumberField(TEXT("fps"),StreamerVisualMainFpsWritten);Status->SetNumberField(TEXT("written"),double(Written));
 Status->SetNumberField(TEXT("dropped_slots"),double(Tap.DroppedSlots.load()));Status->SetNumberField(TEXT("dropped_encode"),double(Tap.DroppedEncode.load()));Status->SetNumberField(TEXT("dropped_queue"),double(Tap.DroppedQueue.load()));
 Status->SetNumberField(TEXT("dropped_noreader"),double(Tap.DroppedNoReader.load()));Status->SetNumberField(TEXT("frames_discarded_midwrite"),double(Tap.DiscardedMidwrite.load()));
 Status->SetNumberField(TEXT("pipe_size"),Tap.PipeSize.load());Status->SetNumberField(TEXT("last_write_utc"),Last>0?double(Last)/1000.:0.);
 Status->SetStringField(TEXT("schema"),TEXT("@@STATUS_SCHEMA@@"));Status->SetNumberField(TEXT("native_pid"),FPlatformProcess::GetCurrentProcessId());
 Status->SetNumberField(TEXT("updated_utc"),double(Utc.ToUnixTimestamp())+Utc.GetMillisecond()/1000.);Status->SetStringField(TEXT("fifo"),Tap.FifoPath);
 Status->SetStringField(TEXT("format"),TEXT("mjpeg: whole baseline JPEGs back to back, one COM \"@@COM@@<n>\" each"));Status->SetBoolField(TEXT("on"),Tap.On.load()!=0);Status->SetStringField(TEXT("reason"),StreamerVisualMainReason);
 Status->SetBoolField(TEXT("reader"),Tap.Reader.load());Status->SetStringField(TEXT("source"),Tap.Source.load()==0?TEXT("backbuffer-delegate"):TEXT("viewport-provider-command"));Status->SetBoolField(TEXT("offscreen"),StreamerVisualMainOffscreen);
 Status->SetNumberField(TEXT("width"),FSub01MainTap::Width);Status->SetNumberField(TEXT("height"),FSub01MainTap::Height);Status->SetStringField(TEXT("pixel_format"),Sub01MainTap::KindName(Tap.LastKind.load()));
 Status->SetNumberField(TEXT("quality"),Tap.Quality.load());Status->SetNumberField(TEXT("target_fps"),StreamerVisualMainFps);Status->SetNumberField(TEXT("capture_fps"),StreamerVisualMainFpsCaptured);
 Status->SetNumberField(TEXT("captured"),double(Captured));Status->SetNumberField(TEXT("encoded"),double(Tap.Encoded.load()));Status->SetNumberField(TEXT("dropped_format"),double(Tap.DroppedFormat.load()));
 Status->SetNumberField(TEXT("dropped_stalled"),double(Tap.DroppedStalled.load()));Status->SetNumberField(TEXT("rate_skipped"),double(Tap.RateSkipped.load()));Status->SetNumberField(TEXT("pipe_set"),Tap.PipeSet.load());
 Status->SetNumberField(TEXT("open_errno"),Tap.OpenErrno.load());Status->SetStringField(TEXT("lock"),Tap.LockState.load()==1?TEXT("held"):Tap.LockState.load()==2?TEXT("busy"):Tap.LockState.load()==3?TEXT("error"):TEXT("released"));
 const int64 Encoded=Tap.Encoded.load(),Copied=Tap.Copied.load();
 Status->SetNumberField(TEXT("encode_ms"),Encoded?double(Tap.EncodeUs.load())/1000./double(Encoded):0.);Status->SetNumberField(TEXT("encode_max_ms"),double(Tap.EncodeMaxUs.load())/1000.);
 Status->SetNumberField(TEXT("copy_ms"),Copied?double(Tap.CopyUs.load())/1000./double(Copied):0.);Status->SetNumberField(TEXT("kb_per_frame"),Written?double(Tap.Bytes.load())/1024./double(Written):0.);
 Status->SetStringField(TEXT("go"),StreamerVisualMainVerdict);Status->SetStringField(TEXT("go_reason"),StreamerVisualMainWhy);
 FString Result;FJsonSerializer::Serialize(Status,TJsonWriterFactory<>::Create(&Result));const FString Final=StreamerVisualCam2Dir+TEXT("/@@STATUS@@"),Tmp=Final+TEXT(".tmp");
 if(FFileHelper::SaveStringToFile(Result,*Tmp))std::rename(TCHAR_TO_UTF8(*Tmp),TCHAR_TO_UTF8(*Final));
}
void ASub01HomeCharacter::LogStreamerVisualMainTap(double Now){
 FSub01MainTap& Tap=*StreamerVisualMainTap;const double Span=FMath::Max(1e-3,Now-StreamerVisualMainLogWindowAt);
 const int64 Totals[4]={Tap.Written.load(),Tap.Captured.load(),Tap.Calls.load(),Tap.FrameSpan.load()};int64 D[4];for(int32 K=0;K<4;++K)D[K]=Totals[K]-StreamerVisualMainLogBase[K];
 const int64 Encoded=Tap.Encoded.load(),Copied=Tap.Copied.load(),Calls=Tap.Calls.load();
 UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_MAIN_TAP fps=%.1f capture_fps=%.1f written=%lld seq=%llu reader=%d on=%d source=%d lock=%d pipe=%d dropped_slots=%lld dropped_encode=%lld dropped_queue=%lld dropped_noreader=%lld dropped_stalled=%lld discarded_midwrite=%lld dropped_format=%lld rate_skipped=%lld encode_ms=%.2f encode_max_ms=%.2f copy_ms=%.2f readback_ms=%.3f calls_per_frame=%.3f other_windows=%lld format=%s pitch=%d checksum=%llx max_channel=%d go=%s window_s=%.0f"),
  double(D[0])/Span,double(D[1])/Span,static_cast<long long>(Totals[0]),static_cast<unsigned long long>(Tap.LastSeq.load()),Tap.Reader.load()?1:0,Tap.On.load(),Tap.Source.load(),Tap.LockState.load(),Tap.PipeSize.load(),
  static_cast<long long>(Tap.DroppedSlots.load()),static_cast<long long>(Tap.DroppedEncode.load()),static_cast<long long>(Tap.DroppedQueue.load()),static_cast<long long>(Tap.DroppedNoReader.load()),static_cast<long long>(Tap.DroppedStalled.load()),
  static_cast<long long>(Tap.DiscardedMidwrite.load()),static_cast<long long>(Tap.DroppedFormat.load()),static_cast<long long>(Tap.RateSkipped.load()),Encoded?double(Tap.EncodeUs.load())/1000./double(Encoded):0.,double(Tap.EncodeMaxUs.exchange(0))/1000.,
  Copied?double(Tap.CopyUs.load())/1000./double(Copied):0.,Calls?double(Tap.ReadbackUs.load())/1000./double(Calls):0.,D[3]>0?double(D[2])/double(D[3]):0.,static_cast<long long>(Tap.OtherWindows.load()),Sub01MainTap::KindName(Tap.LastKind.load()),Tap.LastPitch.load(),
  static_cast<unsigned long long>(Tap.LastChecksum.load()),Tap.MaxChannel.load(),*StreamerVisualMainVerdict,Span);
 for(int32 K=0;K<4;++K)StreamerVisualMainLogBase[K]=Totals[K];StreamerVisualMainLogWindowAt=Now;StreamerVisualMainLogAt=Now+@@LOG@@;
}
// SUB01_STREAMER_VISUAL_V2_V24 END
''', **COMMON)

START_ANCHOR = ' StartStreamerVisualMonitorFeed(); // SUB01_STREAMER_VISUAL_V2_V22: the in-game monitor feed reader, created once\n'
START_V24 = START_ANCHOR + ' StartStreamerVisualMainTap(); // SUB01_STREAMER_VISUAL_V2_V24: the main-view tap (FIFO, back-buffer delegate), created once\n'
TICK_ANCHOR = '  UpdateStreamerVisualMonitorFeed(Now,Dt); // SUB01_STREAMER_VISUAL_V2_V22: the monitor feed (gate, upload, bind, pump, log)\n'
TICK_V24 = TICK_ANCHOR + '  UpdateStreamerVisualMainTap(Now,Dt); // SUB01_STREAMER_VISUAL_V2_V24: the main-view tap (knobs, fallback command, go/no-go, status, log)\n'
TUNING_ANCHOR = ' // SUB01_STREAMER_VISUAL_V2_V23 TUNING END\n'
TUNING_BLOCK = (TUNING_ANCHOR
                + ' // SUB01_STREAMER_VISUAL_V2_V24 TUNING (tools/native_streamer_visual_v2/install_v24.py): the main-view tap keys, in their own lines for merges\n'
                + ' ' + ' '.join(f'Field(TEXT("{k}"),{TUNING_FIELDS[k]},{lo},{hi});' for k, (lo, hi) in TUNING_LIMITS.items()) + '\n'
                + ' // SUB01_STREAMER_VISUAL_V2_V24 TUNING END\n')
RECEIPT_ANCHOR = ('Receipt->SetNumberField(TEXT("cam2_ev_max"),StreamerVisualCam2EvMax); // SUB01_STREAMER_VISUAL_V2_V22\n')
RECEIPT_V24 = RECEIPT_ANCHOR + (
    '   if(StreamerVisualMainTap){const FSub01MainTap& MainTap=*StreamerVisualMainTap; // SUB01_STREAMER_VISUAL_V2_V24\n'
    '    Receipt->SetBoolField(TEXT("main_tap_on"),MainTap.On.load()!=0);Receipt->SetBoolField(TEXT("main_tap_reader"),MainTap.Reader.load());Receipt->SetNumberField(TEXT("main_tap_fps"),StreamerVisualMainFpsWritten);'
    'Receipt->SetNumberField(TEXT("main_tap_written"),double(MainTap.Written.load()));Receipt->SetNumberField(TEXT("main_tap_seq"),double(MainTap.LastSeq.load()));Receipt->SetNumberField(TEXT("main_tap_source"),MainTap.Source.load());\n'
    '    Receipt->SetBoolField(TEXT("main_tap_offscreen"),StreamerVisualMainOffscreen);Receipt->SetStringField(TEXT("main_tap_go"),StreamerVisualMainVerdict);Receipt->SetStringField(TEXT("main_tap_go_reason"),StreamerVisualMainWhy);'
    'Receipt->SetStringField(TEXT("main_tap_reason"),StreamerVisualMainReason);}\n')

# cam2 evidence (spec step 3: "find that loss first"): the FIONREAD level seen at the full-pipe drops, and the pipe size, in cam2.json
CAM2_ATOMICS = v21.CAM2_ATOMICS_V21
assert CAM2_ATOMICS.endswith('\n') and '//' in CAM2_ATOMICS  # its line ends in a comment: the new members get their own line
CAM2_ATOMICS_V24 = CAM2_ATOMICS + (' std::atomic<int64> FullQueuedMax{0};std::atomic<int32> PipeSizeSeen{0}; // SUB01_STREAMER_VISUAL_V2_V24: FIONREAD at the'
                                   ' full-pipe drops (max since the last status), F_GETPIPE_SZ for the status\n')
CAM2_OPENED = '   ::fcntl(Fd,F_SETPIPE_SZ,1048576);PipeBytes=::fcntl(Fd,F_GETPIPE_SZ);Rest.Reset();RestAt=0;OpenErrno.store(0);}\n'
assert v21.CAM2_OPEN_V21.endswith(CAM2_OPENED)
CAM2_OPENED_V24 = ('   ::fcntl(Fd,F_SETPIPE_SZ,1048576);PipeBytes=::fcntl(Fd,F_GETPIPE_SZ);PipeSizeSeen.store(PipeBytes);Rest.Reset();RestAt=0;OpenErrno.store(0);}'
                   ' // + SUB01_STREAMER_VISUAL_V2_V24: the pipe size for cam2.json\n')
CAM2_FULL = '   if(!Room)++DroppedFull; // the reader is behind: this whole frame is dropped\n'
CAM2_FULL_V24 = ('   if(!Room){++DroppedFull;if(Known&&int64(Queued)>FullQueuedMax.load())FullQueuedMax.store(int64(Queued));} // the reader is behind: this whole frame is dropped;'
                 ' SUB01_STREAMER_VISUAL_V2_V24: the pipe level seen\n')
CAM2_STATUS = v21.CAM2_STATUS_V21
CAM2_STATUS_V24 = CAM2_STATUS + (' Status->SetNumberField(TEXT("pipe_size"),Pipe.PipeSizeSeen.load());Status->SetNumberField(TEXT("full_queued_max_kb"),double(Pipe.FullQueuedMax.exchange(0))/1024.);'
                                 ' // SUB01_STREAMER_VISUAL_V2_V24: the cam2 loss evidence (reader back-pressure)\n')

EDITS = [
    ('header', HEADER_V22_END, HEADER_V22_END + HEADER_FIELDS),
    ('cpp', INCLUDE_ANCHOR, INCLUDE_V24),
    ('cpp', CPP_V22_END, CPP_V22_END + CPP_METHODS),
    ('cpp', START_ANCHOR, START_V24),
    ('cpp', TICK_ANCHOR, TICK_V24),
    ('cpp', TUNING_ANCHOR, TUNING_BLOCK),
    ('cpp', RECEIPT_ANCHOR, RECEIPT_V24),
    ('cpp', CAM2_ATOMICS, CAM2_ATOMICS_V24),
    ('cpp', CAM2_OPENED, CAM2_OPENED_V24),
    ('cpp', CAM2_FULL, CAM2_FULL_V24),
    ('cpp', CAM2_STATUS, CAM2_STATUS_V24),
]
REQUIRES = (('header', v23.MARKER, 'v23'), ('cpp', v23.MARKER, 'v23'), ('header', v22.MARKER, 'v22'), ('cpp', v22.MARKER, 'v22'),
            ('header', v21.MARKER, 'v21'), ('cpp', v21.MARKER, 'v21'), ('cpp', cam2.MARKER, 'cam2'))


def plan(sources: dict) -> dict:
    """Pure transformation of the two LF texts; raises Refused, never partial."""
    problems = [f'{FILES[key]} already carries {MARKER} (v24 already installed)' for key in FILES if MARKER in sources[key]]
    if problems:
        raise Refused('; '.join(problems))
    problems = [f'{FILES[key]} lacks {name} ({marker}); run the stack up to install_v23.py first' for key, marker, name in REQUIRES
                if marker + ' BEGIN' not in sources[key]]
    if problems:
        raise Refused('; '.join(problems))
    out, edits = dict(sources), []
    for key, anchor, replacement in EDITS:
        count = out[key].count(anchor)
        edits.append({'file': FILES[key], 'anchor': anchor.strip()[:96], 'anchor_sha256': v2.sha256(anchor), 'count': count})
        if count != 1:
            problems.append(f'anchor {"missing" if count == 0 else f"found {count}x"} in {FILES[key]}: {anchor.strip()[:96]!r}')
            continue
        out[key] = out[key].replace(anchor, replacement, 1)
    if problems:
        raise Refused('; '.join(problems))
    for key in FILES:
        if v2.balance(sources[key]) != v2.balance(out[key]):
            raise Refused(f'{FILES[key]}: bracket balance changed by the install')
        if MARKER not in out[key]:
            raise Refused(f'{FILES[key]}: marker missing after install')
    return {'sources': out, 'edits': edits}


def run(source: Path, dry_run: bool) -> dict:
    source = Path(source).resolve()
    missing = [n for n in FILES.values() if not (source / n).is_file()]
    if missing:
        raise Refused(f'missing in {source}: {", ".join(missing)}')
    raw = {key: v2.read_raw(source / name) for key, name in FILES.items()}
    eol = {key: v2.line_ending(FILES[key], raw[key]) for key in FILES}
    result = plan({key: text.replace('\r\n', '\n') for key, text in raw.items()})
    after = {key: result['sources'][key].replace('\n', eol[key]) for key in FILES}
    report = {'schema': SCHEMA, 'source': str(source), 'dry_run': dry_run, 'marker': MARKER,
              'requires': [v23.MARKER, v22.MARKER, v21.MARKER, cam2.MARKER, streampass.MARKER, seatfix.MARKER, v2.MARKER],
              'main_tap': {'fifo': f'{cam2.STREAM_DIR}/{FIFO_NAME}', 'lock': f'{cam2.STREAM_DIR}/{LOCK_NAME}', 'status': f'{cam2.STREAM_DIR}/{STATUS_NAME}',
                           'status_schema': STATUS_SCHEMA, 'status_fields': list(STATUS_FIELDS), 'com': f'{COM_PREFIX}<n>', 'size': [WIDTH, HEIGHT],
                           'slots': SLOTS, 'encoders': ENCODERS, 'reorder': REORDER_MAX, 'queue': QUEUE_MAX, 'deadline_s': DEADLINE_S, 'poll_slice_ms': SLICE_MS,
                           'probe_s': PROBE_S, 'lock_retry_s': LOCK_RETRY_S, 'diag_s': DIAG_S, 'status_s': STATUS_S, 'log_s': LOG_S,
                           'defaults': {'main_tap': 'auto (offscreen)', 'main_fps': MAIN_FPS, 'main_quality': MAIN_QUALITY, 'main_source': MAIN_SOURCE},
                           'gonogo': {'frames': GONOGO_FRAMES, 'timeout_s': GONOGO_TIMEOUT_S, 'no_calls_s': NO_CALLS_S, 'fires_per_frame': list(FIRE_TOLERANCE),
                                      'nonblack_min': NONBLACK_MIN},
                           'path': 'OnBackBufferReadyToPresent (render thread, game window) -> Unknown->CopySrc -> FRHIGPUTextureReadback ring (oldest first, '
                                   'every ready copy) -> 2 encoder threads (BGRA8, TurboJPEG, COM seq) -> in-order queue -> writer thread (flock, poll, '
                                   'deadline, whole frames) -> main.mjpeg'},
              'cam2_evidence': ['pipe_size', 'full_queued_max_kb'], 'tuning_limits': TUNING_LIMITS, 'edits': result['edits'],
              'files': {FILES[key]: {'before_sha256': v2.sha256(raw[key]), 'after_sha256': v2.sha256(after[key]),
                                     'bytes_before': len(raw[key].encode()), 'bytes_after': len(after[key].encode()),
                                     'line_ending': 'CRLF' if eol[key] == '\r\n' else 'LF',
                                     'edits': sum(1 for k, _, _ in EDITS if k == key)} for key in FILES}}
    if not dry_run:
        v2.write_atomically({source / FILES[key]: after[key] for key in FILES})
        for key in FILES:
            if v2.sha256(v2.read_raw(source / FILES[key])) != report['files'][FILES[key]]['after_sha256']:
                raise Refused(f'{FILES[key]}: written bytes differ from the plan')
    report['status'] = 'planned' if dry_run else 'applied'
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True, help='directory with the v23 pod files (patched in place)')
    parser.add_argument('--dry-run', action='store_true', help='check every anchor and print the report; write nothing')
    args = parser.parse_args(argv)
    try:
        report = run(args.source, args.dry_run)
    except Refused as error:
        print(json.dumps({'schema': SCHEMA, 'source': str(args.source), 'dry_run': args.dry_run, 'status': 'refused', 'reason': str(error)}, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
