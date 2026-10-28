"""Second camera ("cam 2") ON TOP of the stream pass: a view from behind him, at the same time as the webcam, to an MJPEG FIFO.

    python tools/native_streamer_visual_v2/install_cam2.py --source <dir> [--dry-run]

Requires the stream pass (install_stream_pass.py) in Sub01HomeLab.h/.cpp (the only two files this layer edits); refused
when `// SUB01_STREAMER_VISUAL_V2_CAM2` is already present or any anchor is not found exactly once. Same atomic writes,
line endings and JSON report as the other layers.

At v2 start the character creates a USceneCaptureComponent2D (final colour LDR, persistent view state for TSR/exposure,
the view camera's post-process settings, no motion blur) and a WIDTH x HEIGHT BGRA8 render target. Every tick the game
thread captures when the cam2 timer is due (`cam2_fps`, default 60 (owner: 60 fps everywhere; a lower achieved rate is logged, never hidden); never more than one capture per tick) with
CaptureSceneDeferred() (`cam2_deferred` 1, default: rendered with the frame's main view, so each tick's readback reads the
PREVIOUS capture; 0 = CaptureScene() and its own capture) and enqueues one render command; nothing on the game thread waits:
- render thread: a ring of READBACK_SLOTS FRHIGPUTextureReadback copies. Each command first polls the ring (the fence,
  never a wait): the newest finished copy is locked, its rows copied into a FColor array, unlocked, and handed to ONE
  background encode task at a time (older finished copies and frames arriving while an encode runs are dropped); then
  this capture's copy is enqueued into a free slot (none free = the GPU is behind: dropped);
- background task: JPEG (IImageWrapperModule::CompressImage, `cam2_quality`, default 85) and a write to the FIFO
  FIFO_NAME in STREAM_DIR (created with mkfifo 0600 when absent; an existing path that is not this uid's FIFO disables
  cam2, it is never replaced). The FIFO is opened O_WRONLY|O_NONBLOCK (ENXIO = no reader: the frame is dropped, the open
  retried after 1 s), the pipe buffer raised to 1 MiB, SIGPIPE blocked for the write (a reader that leaves gives EPIPE:
  the fd is closed and reopened later). Frames are whole JPEGs back to back (ffmpeg `-f mjpeg -i cam2.mjpeg`): a frame
  is written only when the pipe has room for all of it (a frame larger than the pipe only on an empty pipe), a short
  write keeps its rest to finish before any newer frame (a frame counts as written with its last byte), EINTR is retried:
  while a reader stays connected the byte stream is ordered whole JPEGs, never interleaved; a reader that leaves mid-frame
  loses that frame's rest (the next reader starts on a frame boundary); copies taken before a pause (`cam2` 0) are dropped;
- status `cam2.json` (tmp + rename, every second): fps (frames written per second), capture_fps, frames, captured,
  encoded, drops by reason, reader, last_frame_utc, sizes, costs, placement;
- log `SUB01_STREAMER_VISUAL_CAM2` at start and every LOG_SECONDS: achieved fps, capture fps, game-thread ms per capture
  and per frame (the frame-time cost on the game thread), render-thread readback ms, encode ms, KB/frame, drops. The GPU
  cost of the extra view shows in the stream pass's `SUB01_STREAMER_VISUAL_PERF gpu_ms` (compare with `cam2` 0).
Tunable live from the seat fix's private tuning file: `cam2` 0/1, `cam2_x/y/z`, `cam2_yaw/pitch`, `cam2_fov`, `cam2_fps`,
`cam2_quality`. Default placement: CAM2_LOCATION (the authored spectator point, behind him and to his right, raised to
1.6 m) aimed at CAM2_AIM (his back, the keyboard and the monitor), FOV CAM2_FOV: his back at the PC, the desk, the
monitor and part of the room. Receipt: `cam2_on`, `cam2_fps`, `cam2_capture_fps`, `cam2_frames`, `cam2_reader`,
`cam2_reason`.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location('sub01_streamer_visual_v2_streampass', Path(__file__).resolve().parent / 'install_stream_pass.py')
streampass = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(streampass)
seatfix, v2, Refused = streampass.seatfix, streampass.v2, streampass.Refused

MARKER = '// SUB01_STREAMER_VISUAL_V2_CAM2'
FILES = {key: v2.FILES[key] for key in ('header', 'cpp')}
WIDTH, HEIGHT, READBACK_SLOTS = 1280, 720, 3
CAM2_FPS, CAM2_QUALITY, CAM2_FOV, CAM2_ON = 60.0, 85.0, 70.0, 1  # owner: 60 fps on everything; the log reports the achieved rate
CAM2_DEFERRED = 1  # 1: CaptureSceneDeferred (rendered with the main view, no mid-tick render-state flush; the copy reads the previous capture), 0: CaptureScene
CAM2_LOCATION = (334.0, -209.0, 160.0)    # the authored spectator camera (334,-209,151) raised to 1.6 m: behind him, to his right
CAM2_AIM = (214.0, -340.0, 95.0)          # between the keyboard and the monitor: his back, the desk and the screen in frame
STREAM_DIR = '/home/unreal/.sub01-private/streamer'
FIFO_NAME, STATUS_NAME = 'cam2.mjpeg', 'cam2.json'
PIPE_BYTES = 1 << 20
LOG_SECONDS, STATUS_SECONDS, REOPEN_SECONDS = 30.0, 1.0, 1.0
STATUS_SCHEMA = 'sub01.streamer-cam2-status.v1'


def _look(origin, aim) -> tuple:
    dx, dy, dz = (a - o for a, o in zip(aim, origin))
    return round(math.degrees(math.atan2(dy, dx)), 2), round(math.degrees(math.atan2(dz, math.hypot(dx, dy))), 2)


CAM2_YAW, CAM2_PITCH = _look(CAM2_LOCATION, CAM2_AIM)
TUNING_LIMITS = {'cam2': (0, 1), 'cam2_deferred': (0, 1), 'cam2_x': (-5000, 5000), 'cam2_y': (-5000, 5000), 'cam2_z': (-1000, 2000), 'cam2_yaw': (-360, 360),
                 'cam2_pitch': (-89, 89), 'cam2_fov': (20, 120), 'cam2_fps': (1, 60), 'cam2_quality': (40, 95)}
TUNING_FIELDS = {'cam2': 'StreamerVisualCam2On', 'cam2_deferred': 'StreamerVisualCam2Deferred', 'cam2_x': 'StreamerVisualCam2X', 'cam2_y': 'StreamerVisualCam2Y', 'cam2_z': 'StreamerVisualCam2Z',
                 'cam2_yaw': 'StreamerVisualCam2Yaw', 'cam2_pitch': 'StreamerVisualCam2Pitch', 'cam2_fov': 'StreamerVisualCam2Fov',
                 'cam2_fps': 'StreamerVisualCam2Fps', 'cam2_quality': 'StreamerVisualCam2Quality'}
assert set(TUNING_FIELDS) == set(TUNING_LIMITS)
_f = streampass._f

# ------------------------------------------------------------------------------------------------ Sub01HomeLab.h
HEADER_STREAM_END = ' // SUB01_STREAMER_VISUAL_V2_STREAMPASS END\n'
HEADER_FIELDS = f''' // SUB01_STREAMER_VISUAL_V2_CAM2 BEGIN (tools/native_streamer_visual_v2/install_cam2.py): the second camera (behind him) to an MJPEG FIFO.
 void StartStreamerVisualCam2();void UpdateStreamerVisualCam2(double Now,float Dt);void WriteStreamerVisualCam2Status(double Now);
 UPROPERTY() TObjectPtr<class USceneCaptureComponent2D> StreamerVisualCam2;
 UPROPERTY() TObjectPtr<class UTextureRenderTarget2D> StreamerVisualCam2Target;
 TSharedPtr<class FSub01StreamerCam2> StreamerVisualCam2Pipe; // shared with the render thread and the encode task
 FString StreamerVisualCam2Dir=TEXT("{STREAM_DIR}"),StreamerVisualCam2Reason;
 float StreamerVisualCam2On={_f(CAM2_ON)},StreamerVisualCam2X={_f(CAM2_LOCATION[0])},StreamerVisualCam2Y={_f(CAM2_LOCATION[1])},StreamerVisualCam2Z={_f(CAM2_LOCATION[2])};
 float StreamerVisualCam2Yaw={_f(CAM2_YAW)},StreamerVisualCam2Pitch={_f(CAM2_PITCH)},StreamerVisualCam2Fov={_f(CAM2_FOV)},StreamerVisualCam2Fps={_f(CAM2_FPS)},StreamerVisualCam2Quality={_f(CAM2_QUALITY)};
 float StreamerVisualCam2Deferred={_f(CAM2_DEFERRED)};bool StreamerVisualCam2HasPrevious=false,StreamerVisualCam2WasOn=false;int32 StreamerVisualCam2Epoch=0;
 FVector StreamerVisualCam2Placed=FVector::ZeroVector;FRotator StreamerVisualCam2PlacedRotation=FRotator::ZeroRotator;float StreamerVisualCam2PlacedFov=-1;
 double StreamerVisualCam2NextAt=0,StreamerVisualCam2StatusAt=0,StreamerVisualCam2StatusWindowAt=0,StreamerVisualCam2LogAt=0,StreamerVisualCam2LogWindowAt=0,StreamerVisualCam2GameMs=0;
 int64 StreamerVisualCam2StatusBase[2]={{0,0}},StreamerVisualCam2LogBase[9]={{0,0,0,0,0,0,0,0,0}};int32 StreamerVisualCam2LogFrames=0,StreamerVisualCam2LogCaptures=0;
 float StreamerVisualCam2FpsAchieved=0,StreamerVisualCam2CaptureFps=0;
 // SUB01_STREAMER_VISUAL_V2_CAM2 END
'''

# ------------------------------------------------------------------------------------------------ Sub01HomeLab.cpp
CPP_INCLUDES = streampass.CPP_TOP_INCLUDES
CPP_INCLUDES_CAM2 = (CPP_INCLUDES +
                     '#include "Components/SceneCaptureComponent2D.h" // SUB01_STREAMER_VISUAL_V2_CAM2: capture, readback ring, JPEG, FIFO\n'
                     '#include "Engine/TextureRenderTarget2D.h"\n#include "TextureResource.h"\n#include "RenderingThread.h"\n#include "RHICommandList.h"\n#include "RHIGPUReadback.h"\n'
                     '#include "IImageWrapperModule.h"\n#include "ImageCore.h"\n#include "Modules/ModuleManager.h"\n#include "Async/Async.h"\n#include "Dom/JsonObject.h"\n'
                     '#include <atomic>\n#include <cerrno>\n#include <signal.h>\n#include <pthread.h>\n#include <sys/ioctl.h>\n')
STREAM_METHODS_BEGIN = '// SUB01_STREAMER_VISUAL_V2_STREAMPASS BEGIN (tools/native_streamer_visual_v2/install_stream_pass.py)\n'
CPP_METHODS = f'''// SUB01_STREAMER_VISUAL_V2_CAM2 BEGIN (tools/native_streamer_visual_v2/install_cam2.py)
#ifndef F_SETPIPE_SZ
#define F_SETPIPE_SZ 1031
#endif
#ifndef F_GETPIPE_SZ
#define F_GETPIPE_SZ 1032
#endif
class FSub01StreamerCam2{{
 // Render-thread readback ring -> one background JPEG encode at a time -> non-blocking FIFO writer. The game thread only captures
 // (timer) and reads the counters; no reader or a full pipe drops WHOLE frames, never blocks a thread, never splits a JPEG.
public:
 static constexpr int32 Width={WIDTH},Height={HEIGHT},Slots={READBACK_SLOTS};
 FString FifoPath;IImageWrapperModule* Images=nullptr;std::atomic<int32> Quality{{{int(CAM2_QUALITY)}}};
 std::atomic<int64> Captured{{0}},Copied{{0}},Encoded{{0}},Written{{0}},DroppedNoReader{{0}},DroppedBusy{{0}},DroppedFull{{0}},DroppedSlots{{0}},Bytes{{0}},ReadbackUs{{0}},EncodeUs{{0}},LastWrittenMs{{0}};
 std::atomic<int32> EncodeBusy{{0}},OpenErrno{{0}};std::atomic<bool> Reader{{false}};std::atomic<int64> DroppedStale{{0}};
 // render thread only
 TUniquePtr<FRHIGPUTextureReadback> Readback[Slots];bool Pending[Slots]={{false,false,false}};uint64 Sequence[Slots]={{0,0,0}},NextSequence=1;int32 SlotEpoch[Slots]={{0,0,0}};
 // the encode task only (at most one in flight)
 int Fd=-1,PipeBytes=0;double NextOpenAt=0;TArray64<uint8> Rest;int64 RestAt=0;
 ~FSub01StreamerCam2(){{if(Fd>=0)::close(Fd);}}
 void Pump(FRHICommandListImmediate& RHICmdList,FRHITexture* Texture,const TSharedPtr<FSub01StreamerCam2>& Self,int32 Epoch){{
  const double T0=FPlatformTime::Seconds();
  // 1. the newest finished copy goes to the encoder; older finished ones are stale (dropped); the fence is polled, never waited on
  int32 Best=-1;bool Ready[Slots]={{false,false,false}};
  for(int32 S=0;S<Slots;++S){{Ready[S]=Pending[S]&&Readback[S]&&Readback[S]->IsReady();
   if(Ready[S]&&SlotEpoch[S]!=Epoch){{Pending[S]=false;Ready[S]=false;++DroppedStale;continue;}} // copied before a pause: never shown after it
   if(Ready[S]&&(Best<0||Sequence[S]>Sequence[Best]))Best=S;}}
  for(int32 S=0;S<Slots;++S)if(Ready[S]&&S!=Best){{Pending[S]=false;++DroppedBusy;}}
  if(Best>=0){{Pending[Best]=false;
   if(EncodeBusy.exchange(1)!=0)++DroppedBusy; // the previous frame is still being encoded/written
   else{{int32 Pitch=0,Rows=0;const uint8* Source=static_cast<const uint8*>(Readback[Best]->Lock(Pitch,&Rows));
    if(Source&&Pitch>=Width&&Rows>=Height){{TArray<FColor> Pixels;Pixels.SetNumUninitialized(Width*Height);
     for(int32 Y=0;Y<Height;++Y)FMemory::Memcpy(Pixels.GetData()+int64(Y)*Width,Source+int64(Y)*Pitch*4,size_t(Width)*4);
     Readback[Best]->Unlock();++Copied;
     AsyncTask(ENamedThreads::AnyBackgroundThreadNormalTask,[Self,Pixels=MoveTemp(Pixels)]() mutable {{Self->EncodeAndWrite(Pixels);Self->EncodeBusy.store(0);}});}}
    else{{if(Source)Readback[Best]->Unlock();EncodeBusy.store(0);}}}}
  }}
  // 2. this capture's copy into a free slot (none free: the GPU is {READBACK_SLOTS} captures behind, the frame is dropped)
  if(Texture){{int32 Free=-1;for(int32 S=0;S<Slots&&Free<0;++S)if(!Pending[S])Free=S;
   if(Free<0)++DroppedSlots;
   else{{if(!Readback[Free])Readback[Free]=MakeUnique<FRHIGPUTextureReadback>(TEXT("Sub01StreamerCam2"));Readback[Free]->EnqueueCopy(RHICmdList,Texture);Pending[Free]=true;Sequence[Free]=NextSequence++;SlotEpoch[Free]=Epoch;}}}}
  ReadbackUs+=int64((FPlatformTime::Seconds()-T0)*1e6);
 }}
 void EncodeAndWrite(TArray<FColor>& Pixels){{ // background task
  const double T0=FPlatformTime::Seconds();TArray64<uint8> Jpeg;
  if(!Images||!Images->CompressImage(Jpeg,EImageFormat::JPEG,FImageView(Pixels.GetData(),Width,Height),Quality.load())||Jpeg.Num()<=0)return;
  ++Encoded;Bytes+=Jpeg.Num();EncodeUs+=int64((FPlatformTime::Seconds()-T0)*1e6);WriteFrame(Jpeg.GetData(),Jpeg.Num());
 }}
 void Finished(){{++Written;const FDateTime Utc=FDateTime::UtcNow();LastWrittenMs.store(Utc.ToUnixTimestamp()*1000+Utc.GetMillisecond());}} // a frame's last byte is in the pipe
 void WriteFrame(const uint8* Data,int64 Size){{ // background task: whole frames only, never blocking
  const double Now=FPlatformTime::Seconds();
  if(Fd<0){{if(Now<NextOpenAt){{++DroppedNoReader;return;}}NextOpenAt=Now+{REOPEN_SECONDS:g};
   Fd=::open(TCHAR_TO_UTF8(*FifoPath),O_WRONLY|O_NONBLOCK|O_CLOEXEC); // ENXIO: nobody reads the FIFO yet
   if(Fd<0){{OpenErrno.store(errno==ENXIO?0:errno);Reader.store(false);++DroppedNoReader;return;}} // ENXIO = no reader yet; any other errno is reported (status open_errno)
   ::fcntl(Fd,F_SETPIPE_SZ,{PIPE_BYTES});PipeBytes=::fcntl(Fd,F_GETPIPE_SZ);Rest.Reset();RestAt=0;Reader.store(true);OpenErrno.store(0);}}
  sigset_t Block,Old;sigemptyset(&Block);sigaddset(&Block,SIGPIPE);pthread_sigmask(SIG_BLOCK,&Block,&Old); // a reader that left: EPIPE, not a process-wide SIGPIPE
  bool Broken=false;
  auto Send=[this,&Broken](const uint8* Out,int64 Count)->int64{{ssize_t N;do N=::write(Fd,Out,size_t(Count));while(N<0&&errno==EINTR);if(N<0){{if(errno!=EAGAIN)Broken=true;return 0;}}return int64(N);}};
  if(RestAt<Rest.Num()){{RestAt+=Send(Rest.GetData()+RestAt,Rest.Num()-RestAt);if(!Broken&&RestAt>=Rest.Num()){{Rest.Reset();RestAt=0;Finished();}}}} // the rest of a short write first: frames stay whole
  if(!Broken){{
   // room for the WHOLE frame (FIONREAD is a heuristic; write/EAGAIN stays authoritative); a frame larger than the pipe starts only on
   // an empty pipe and streams through Rest
   int Queued=0;const bool Known=PipeBytes>0&&::ioctl(Fd,FIONREAD,&Queued)==0;
   const bool Room=RestAt>=Rest.Num()&&(!Known||(Size<=PipeBytes?int64(PipeBytes)-Queued>=Size:Queued==0));
   if(!Room)++DroppedFull; // the reader is behind: this whole frame is dropped
   else{{const int64 N=Send(Data,Size);if(!Broken){{if(N<=0)++DroppedFull;else if(N<Size){{Rest.Reset();Rest.Append(Data+N,Size-N);RestAt=0;}}else Finished();}}}}
  }}
  if(Broken){{::close(Fd);Fd=-1;Rest.Reset();RestAt=0;Reader.store(false);++DroppedNoReader;}}
  {{sigset_t Waiting;if(sigpending(&Waiting)==0&&sigismember(&Waiting,SIGPIPE)){{const timespec Zero{{0,0}};sigtimedwait(&Block,nullptr,&Zero);}}}} // never restore the mask with our SIGPIPE pending
  pthread_sigmask(SIG_SETMASK,&Old,nullptr);
 }}
}};
void ASub01HomeCharacter::StartStreamerVisualCam2(){{
 // Once per process at v2 start: the FIFO (mkfifo 0600 when absent; a path that is not this uid's FIFO disables cam2), the render
 // target, the capture component (manual captures only) and the shared pipe state.
 if(StreamerVisualCam2)return;
 StreamerVisualCam2Pipe=MakeShared<FSub01StreamerCam2>();FSub01StreamerCam2& Pipe=*StreamerVisualCam2Pipe;
 Pipe.FifoPath=StreamerVisualCam2Dir+TEXT("/{FIFO_NAME}");Pipe.Quality.store(int32(StreamerVisualCam2Quality));
 Pipe.Images=&FModuleManager::LoadModuleChecked<IImageWrapperModule>(FName(TEXT("ImageWrapper")));
 ::mkdir(TCHAR_TO_UTF8(*StreamerVisualCam2Dir),0700);struct stat S;StreamerVisualCam2Reason.Empty();
 if(::lstat(TCHAR_TO_UTF8(*Pipe.FifoPath),&S)!=0){{if(::mkfifo(TCHAR_TO_UTF8(*Pipe.FifoPath),0600)!=0)StreamerVisualCam2Reason=FString::Printf(TEXT("mkfifo failed errno=%d"),errno);}}
 else if(!S_ISFIFO(S.st_mode)||S.st_uid!=getuid())StreamerVisualCam2Reason=TEXT("path exists and is not this user's FIFO (left untouched)");
 StreamerVisualCam2Target=NewObject<UTextureRenderTarget2D>(this,TEXT("StreamerVisualCam2Target"));StreamerVisualCam2Target->InitCustomFormat({WIDTH},{HEIGHT},PF_B8G8R8A8,false);StreamerVisualCam2Target->UpdateResourceImmediate(true);
 StreamerVisualCam2=NewObject<USceneCaptureComponent2D>(this,TEXT("StreamerVisualCam2"));StreamerVisualCam2->TextureTarget=StreamerVisualCam2Target;
 StreamerVisualCam2->CaptureSource=ESceneCaptureSource::SCS_FinalColorLDR;StreamerVisualCam2->bCaptureEveryFrame=false;StreamerVisualCam2->bCaptureOnMovement=false;StreamerVisualCam2->bAlwaysPersistRenderingState=true;
 if(ViewCamera){{StreamerVisualCam2->PostProcessSettings=ViewCamera->PostProcessSettings;StreamerVisualCam2->PostProcessBlendWeight=ViewCamera->PostProcessBlendWeight;}}
 StreamerVisualCam2->ShowFlags.SetMotionBlur(false);StreamerVisualCam2->ShowFlags.SetDepthOfField(false);StreamerVisualCam2->RegisterComponent();
 StreamerVisualCam2PlacedFov=-1;StreamerVisualCam2NextAt=0;StreamerVisualCam2LogAt=FPlatformTime::Seconds()+{LOG_SECONDS:g};StreamerVisualCam2LogWindowAt=FPlatformTime::Seconds();
 UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_CAM2 started=%d fifo=%s size={WIDTH}x{HEIGHT} targetFps=%.0f quality=%d location=(%.1f,%.1f,%.1f) yaw=%.1f pitch=%.1f fov=%.1f on=%d reason=%s"),StreamerVisualCam2Reason.IsEmpty()?1:0,*Pipe.FifoPath,
  StreamerVisualCam2Fps,int32(StreamerVisualCam2Quality),StreamerVisualCam2X,StreamerVisualCam2Y,StreamerVisualCam2Z,StreamerVisualCam2Yaw,StreamerVisualCam2Pitch,StreamerVisualCam2Fov,StreamerVisualCam2On>0?1:0,StreamerVisualCam2Reason.IsEmpty()?TEXT("-"):*StreamerVisualCam2Reason);
}}
void ASub01HomeCharacter::UpdateStreamerVisualCam2(double Now,float Dt){{
 if(!StreamerVisualCam2||!StreamerVisualCam2Target||!StreamerVisualCam2Pipe)return;FSub01StreamerCam2& Pipe=*StreamerVisualCam2Pipe;
 const FVector Location(StreamerVisualCam2X,StreamerVisualCam2Y,StreamerVisualCam2Z);const FRotator Rotation(StreamerVisualCam2Pitch,StreamerVisualCam2Yaw,0);
 if(!Location.Equals(StreamerVisualCam2Placed,.01)||!Rotation.Equals(StreamerVisualCam2PlacedRotation,.01)||StreamerVisualCam2Fov!=StreamerVisualCam2PlacedFov){{ // placement from the tuning file, on change
  StreamerVisualCam2Placed=Location;StreamerVisualCam2PlacedRotation=Rotation;StreamerVisualCam2PlacedFov=StreamerVisualCam2Fov;
  StreamerVisualCam2->SetWorldLocationAndRotation(Location,Rotation);StreamerVisualCam2->FOVAngle=StreamerVisualCam2Fov;
  UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_CAM2_PLACED location=%s rotation=%s fov=%.1f"),*Location.ToString(),*Rotation.ToString(),StreamerVisualCam2Fov);
 }}
 Pipe.Quality.store(int32(StreamerVisualCam2Quality));
 const bool On=StreamerVisualCam2On>0&&StreamerVisualCam2Reason.IsEmpty();
 if(On&&Now+.5*Dt>=StreamerVisualCam2NextAt){{ // due (half a frame of tolerance keeps 30 of 60 ticks); at most one capture per tick
  const double Period=1./FMath::Clamp(double(StreamerVisualCam2Fps),1.,60.);StreamerVisualCam2NextAt+=Period;if(StreamerVisualCam2NextAt<Now)StreamerVisualCam2NextAt=Now+Period;
  const double T0=FPlatformTime::Seconds();const bool Deferred=StreamerVisualCam2Deferred>0;
  // deferred (default): the capture renders with this frame's main view (same pose, no mid-tick render-state flush), so this tick's
  // command copies the PREVIOUS capture (one capture behind) and is enqueued before the next request; immediate: CaptureScene()'s
  // commands precede the copy of this capture
  FTextureRenderTargetResource* Resource=StreamerVisualCam2Target->GameThread_GetRenderTargetResource();
  if(!Deferred)StreamerVisualCam2->CaptureScene();
  const bool Copy=!Deferred||StreamerVisualCam2HasPrevious;StreamerVisualCam2HasPrevious=Deferred;
  ENQUEUE_RENDER_COMMAND(Sub01StreamerCam2Readback)([Self=StreamerVisualCam2Pipe,Resource,Copy,Epoch=StreamerVisualCam2Epoch](FRHICommandListImmediate& RHICmdList){{Self->Pump(RHICmdList,Copy&&Resource?Resource->GetRenderTargetTexture().GetReference():nullptr,Self,Epoch);}});
  if(Deferred)StreamerVisualCam2->CaptureSceneDeferred();
  ++Pipe.Captured;
  StreamerVisualCam2GameMs+=(FPlatformTime::Seconds()-T0)*1000.;++StreamerVisualCam2LogCaptures;
 }}
 if(!On){{StreamerVisualCam2HasPrevious=false;if(StreamerVisualCam2WasOn)++StreamerVisualCam2Epoch;}}StreamerVisualCam2WasOn=On; // a pause: neither the stale target nor copies still in the ring are shown after it
 ++StreamerVisualCam2LogFrames;
 if(Now>=StreamerVisualCam2StatusAt)WriteStreamerVisualCam2Status(Now);
 if(Now>=StreamerVisualCam2LogAt){{ // the window's achieved rate and costs
  const double Span=FMath::Max(1e-3,Now-StreamerVisualCam2LogWindowAt);
  const int64 Now9[9]={{Pipe.Written.load(),Pipe.Captured.load(),Pipe.Encoded.load(),Pipe.Bytes.load(),Pipe.ReadbackUs.load(),Pipe.EncodeUs.load(),Pipe.DroppedNoReader.load()+Pipe.DroppedFull.load(),Pipe.DroppedBusy.load(),Pipe.DroppedSlots.load()}};
  int64 D[9];for(int32 K=0;K<9;++K)D[K]=Now9[K]-StreamerVisualCam2LogBase[K];
  UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_CAM2 fps=%.1f capture_fps=%.1f target_fps=%.0f frames=%d reader=%d game_ms_per_capture=%.2f game_ms_per_frame=%.3f readback_ms=%.2f encode_ms=%.1f kb=%.0f dropped_no_reader_or_full=%d dropped_busy=%d dropped_slots=%d on=%d window_s=%.0f"),
   double(D[0])/Span,double(D[1])/Span,StreamerVisualCam2Fps,int32(Now9[0]),Pipe.Reader.load()?1:0,StreamerVisualCam2LogCaptures?StreamerVisualCam2GameMs/StreamerVisualCam2LogCaptures:0.,StreamerVisualCam2LogFrames?StreamerVisualCam2GameMs/StreamerVisualCam2LogFrames:0.,
   D[1]?double(D[4])/1000./double(D[1]):0.,D[2]?double(D[5])/1000./double(D[2]):0.,D[2]?double(D[3])/1024./double(D[2]):0.,int32(D[6]),int32(D[7]),int32(D[8]),On?1:0,Span);
  for(int32 K=0;K<9;++K)StreamerVisualCam2LogBase[K]=Now9[K];StreamerVisualCam2LogWindowAt=Now;StreamerVisualCam2LogAt=Now+{LOG_SECONDS:g};StreamerVisualCam2GameMs=0;StreamerVisualCam2LogFrames=StreamerVisualCam2LogCaptures=0;
 }}
}}
void ASub01HomeCharacter::WriteStreamerVisualCam2Status(double Now){{
 // {STATUS_NAME} next to the FIFO, every {STATUS_SECONDS:g} s (tmp + rename): what a consumer needs to trust the stream.
 FSub01StreamerCam2& Pipe=*StreamerVisualCam2Pipe;const int64 Written=Pipe.Written.load(),Captured=Pipe.Captured.load();
 if(StreamerVisualCam2StatusWindowAt>0&&Now>StreamerVisualCam2StatusWindowAt){{const double Span=Now-StreamerVisualCam2StatusWindowAt;
  StreamerVisualCam2FpsAchieved=float(double(Written-StreamerVisualCam2StatusBase[0])/Span);StreamerVisualCam2CaptureFps=float(double(Captured-StreamerVisualCam2StatusBase[1])/Span);}}
 StreamerVisualCam2StatusWindowAt=Now;StreamerVisualCam2StatusBase[0]=Written;StreamerVisualCam2StatusBase[1]=Captured;StreamerVisualCam2StatusAt=Now+{STATUS_SECONDS:g};
 auto Status=MakeShared<FJsonObject>();Status->SetStringField(TEXT("schema"),TEXT("{STATUS_SCHEMA}"));Status->SetNumberField(TEXT("native_pid"),FPlatformProcess::GetCurrentProcessId());
 const FDateTime Utc=FDateTime::UtcNow();Status->SetNumberField(TEXT("updated_utc"),double(Utc.ToUnixTimestamp())+Utc.GetMillisecond()/1000.);Status->SetStringField(TEXT("fifo"),Pipe.FifoPath);Status->SetStringField(TEXT("format"),TEXT("mjpeg (whole JPEG frames back to back)"));
 Status->SetBoolField(TEXT("on"),StreamerVisualCam2On>0&&StreamerVisualCam2Reason.IsEmpty());Status->SetStringField(TEXT("reason"),StreamerVisualCam2Reason);Status->SetBoolField(TEXT("reader"),Pipe.Reader.load());
 Status->SetNumberField(TEXT("fps"),StreamerVisualCam2FpsAchieved);Status->SetNumberField(TEXT("capture_fps"),StreamerVisualCam2CaptureFps);Status->SetNumberField(TEXT("target_fps"),StreamerVisualCam2Fps);
 Status->SetNumberField(TEXT("frames"),double(Written));Status->SetNumberField(TEXT("captured"),double(Captured));Status->SetNumberField(TEXT("encoded"),double(Pipe.Encoded.load()));
 Status->SetNumberField(TEXT("dropped_no_reader"),double(Pipe.DroppedNoReader.load()));Status->SetNumberField(TEXT("dropped_full"),double(Pipe.DroppedFull.load()));Status->SetNumberField(TEXT("dropped_busy"),double(Pipe.DroppedBusy.load()));Status->SetNumberField(TEXT("dropped_slots"),double(Pipe.DroppedSlots.load()));Status->SetNumberField(TEXT("dropped_stale"),double(Pipe.DroppedStale.load()));Status->SetNumberField(TEXT("open_errno"),Pipe.OpenErrno.load());
 const int64 Last=Pipe.LastWrittenMs.load();Status->SetNumberField(TEXT("last_frame_utc"),Last>0?double(Last)/1000.:0.);
 Status->SetNumberField(TEXT("width"),{WIDTH});Status->SetNumberField(TEXT("height"),{HEIGHT});Status->SetNumberField(TEXT("quality"),Pipe.Quality.load());Status->SetNumberField(TEXT("fov"),StreamerVisualCam2Fov);
 Status->SetStringField(TEXT("location"),StreamerVisualCam2Placed.ToString());Status->SetStringField(TEXT("rotation"),StreamerVisualCam2PlacedRotation.ToString());
 const int64 Encoded=Pipe.Encoded.load();Status->SetNumberField(TEXT("encode_ms"),Encoded?double(Pipe.EncodeUs.load())/1000./double(Encoded):0.);Status->SetNumberField(TEXT("kb_per_frame"),Encoded?double(Pipe.Bytes.load())/1024./double(Encoded):0.);
 FString Result;FJsonSerializer::Serialize(Status,TJsonWriterFactory<>::Create(&Result));const FString Final=StreamerVisualCam2Dir+TEXT("/{STATUS_NAME}"),Tmp=Final+TEXT(".tmp");
 if(FFileHelper::SaveStringToFile(Result,*Tmp))std::rename(TCHAR_TO_UTF8(*Tmp),TCHAR_TO_UTF8(*Final));
}}
// SUB01_STREAMER_VISUAL_V2_CAM2 END
'''


def _fields(keys) -> str:
    return ''.join(f'Field(TEXT("{k}"),{TUNING_FIELDS[k]},{TUNING_LIMITS[k][0]},{TUNING_LIMITS[k][1]});' for k in keys)


TUNING_STREAM_LAST = [line for line in streampass.TUNING_STREAM.splitlines(keepends=True) if 'Field(TEXT("hide_slot")' in line]
assert len(TUNING_STREAM_LAST) == 1
TUNING_STREAM_LAST = TUNING_STREAM_LAST[0]
TUNING_CAM2 = TUNING_STREAM_LAST + ' ' + _fields(TUNING_LIMITS) + ' // SUB01_STREAMER_VISUAL_V2_CAM2\n'
START_ANCHOR = streampass.SEAT_READY_LOG
START_CAM2 = ' StartStreamerVisualCam2(); // SUB01_STREAMER_VISUAL_V2_CAM2: the second camera, created once (streamer mode only)\n' + START_ANCHOR
TICK_ANCHOR = streampass.TICK_STREAM
TICK_CAM2 = TICK_ANCHOR + '  UpdateStreamerVisualCam2(Now,Dt); // SUB01_STREAMER_VISUAL_V2_CAM2: timer capture, readback pump, status, log\n'
RECEIPT_ANCHOR = streampass.RECEIPT_STREAM_TAIL
assert RECEIPT_ANCHOR.endswith('} // SUB01_STREAMER_VISUAL_V2_STREAMPASS\n')
RECEIPT_CAM2 = (RECEIPT_ANCHOR[:-len('} // SUB01_STREAMER_VISUAL_V2_STREAMPASS\n')] + ' // SUB01_STREAMER_VISUAL_V2_STREAMPASS\n'
                '   Receipt->SetBoolField(TEXT("cam2_on"),StreamerVisualCam2!=nullptr&&StreamerVisualCam2On>0&&StreamerVisualCam2Reason.IsEmpty());Receipt->SetNumberField(TEXT("cam2_fps"),StreamerVisualCam2FpsAchieved);Receipt->SetNumberField(TEXT("cam2_capture_fps"),StreamerVisualCam2CaptureFps);'
                'Receipt->SetNumberField(TEXT("cam2_frames"),StreamerVisualCam2Pipe?double(StreamerVisualCam2Pipe->Written.load()):0.);Receipt->SetBoolField(TEXT("cam2_reader"),StreamerVisualCam2Pipe&&StreamerVisualCam2Pipe->Reader.load());'
                'Receipt->SetStringField(TEXT("cam2_reason"),StreamerVisualCam2Reason);} // SUB01_STREAMER_VISUAL_V2_CAM2\n')

EDITS = [
    ('header', HEADER_STREAM_END, HEADER_STREAM_END + HEADER_FIELDS),
    ('cpp', CPP_INCLUDES, CPP_INCLUDES_CAM2),
    ('cpp', STREAM_METHODS_BEGIN, CPP_METHODS + STREAM_METHODS_BEGIN),
    ('cpp', TUNING_STREAM_LAST, TUNING_CAM2),
    ('cpp', START_ANCHOR, START_CAM2),
    ('cpp', TICK_ANCHOR, TICK_CAM2),
    ('cpp', RECEIPT_ANCHOR, RECEIPT_CAM2),
]


def plan(sources: dict) -> dict:
    """Pure transformation of the two LF texts; raises Refused, never partial."""
    problems = [f'{FILES[key]} already carries {MARKER} (cam2 already installed)' for key in FILES if MARKER in sources[key]]
    if problems:
        raise Refused('; '.join(problems))
    problems = [f'{FILES[key]} lacks the stream pass ({streampass.MARKER}); run the stack up to install_stream_pass.py first'
                for key in FILES if streampass.MARKER + ' BEGIN' not in sources[key]]
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
    report = {'schema': 'sub01.native-streamer-visual-v2-cam2-install.v1', 'source': str(source), 'dry_run': dry_run,
              'marker': MARKER, 'requires': [streampass.MARKER, seatfix.MARKER, v2.MARKER],
              'cam2': {'size': [WIDTH, HEIGHT], 'fps': CAM2_FPS, 'quality': CAM2_QUALITY, 'fov': CAM2_FOV, 'on': CAM2_ON,
                       'location': list(CAM2_LOCATION), 'aim': list(CAM2_AIM), 'yaw': CAM2_YAW, 'pitch': CAM2_PITCH,
                       'fifo': f'{STREAM_DIR}/{FIFO_NAME}', 'status': f'{STREAM_DIR}/{STATUS_NAME}', 'status_schema': STATUS_SCHEMA,
                       'readback_slots': READBACK_SLOTS, 'pipe_bytes': PIPE_BYTES, 'log_seconds': LOG_SECONDS,
                       'deferred': CAM2_DEFERRED,
              'path': 'CaptureSceneDeferred on a timer (readback of the previous capture) -> render-thread FRHIGPUTextureReadback ring (polled) -> one background JPEG encode -> O_NONBLOCK FIFO, whole frames only'},
              'tuning_limits': TUNING_LIMITS, 'edits': result['edits'],
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
    parser.add_argument('--source', type=Path, required=True, help='directory with the stream-passed pod files (patched in place)')
    parser.add_argument('--dry-run', action='store_true', help='check every anchor and print the report; write nothing')
    args = parser.parse_args(argv)
    try:
        report = run(args.source, args.dry_run)
    except Refused as error:
        print(json.dumps({'schema': 'sub01.native-streamer-visual-v2-cam2-install.v1', 'source': str(args.source),
                          'dry_run': args.dry_run, 'status': 'refused', 'reason': str(error)}, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
