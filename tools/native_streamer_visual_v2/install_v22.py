"""v22 ON TOP of v21: the in-game PC monitor fed at up to 60 fps from the monitor feed sidecar, no per-frame UTexture2D in the bridges,
and live exposure controls for camera 2.

    python tools/native_streamer_visual_v2/install_v22.py --source <dir> [--dry-run]

Requires v21 (install_v21_fixes.py) in Sub01HomeLab.h/.cpp; edits those two files, Sub01PCBridge.h/.cpp and
Sub01HomeDeviceBridge.h/.cpp, and creates Sub01PersistentTexture.h next to them. Refused when `// SUB01_STREAMER_VISUAL_V2_V22`
is already present in any of them, when the new header already exists with other content, or when any anchor is not found
exactly once (all or nothing; the same atomic writes, line endings and JSON report as the other layers). Decided with Kimi
(docs/streamer/kimi/native-v22-design.md); code reviewed by Kimi (docs/streamer/kimi/native-v22-review.md).

1. In-game monitor feed. scripts/streamer_monitor_feed.py (the supervised `monitor` service, with its own privacy gate and
   neutral grey frames during a cut: ordinary frames here) writes whole JPEGs (x11grab of the Vagon desktop, 1280x720, up to
   60 fps) back to back into FIFO_NAME in the streamer directory. In streamer mode the character reads it with ONE background
   task at a time (the cam2 pattern): the task opens the FIFO O_RDONLY|O_NONBLOCK|O_NOFOLLOW (only this user's FIFO with no
   group/other bits: lstat before, fstat after the open), reads what is there (at most PUMP_BYTES per pump), cuts complete JPEGs
   by walking their markers (segments by length, entropy data up to a real marker, EOI; garbage, a cut frame, a reserved marker
   or a frame over MAX_FRAME_BYTES = resync on the next SOI), queues the newest complete frame of each read (a ring of at most
   RING_FRAMES / RING_BYTES compressed frames) and plays out at most ONE per pump: the newest frame read at least
   `monitor_delay_s` (PLAYOUT_SECONDS) ago AND before the start of the bridge's newest validating public confirmation (Kimi:
   a frame read after the runner locked cannot be shown while the lock lasts, even before the game notices it), decoded with
   IImageWrapper JPEG -> BGRA (the size checked from the header first): never more than one decode in flight, nothing parsed
   or decoded on the game thread. The game thread takes the decoded frame (a pointer swap; an untaken one is dropped), uploads
   it into ONE persistent texture (Sub01PersistentTexture: created once per size, B8G8R8A8 sRGB, never streamed, one mip,
   cleared opaque black; UpdateTextureRegions of the 1280x720 rect at the bridge's own layout offset, cleared again when that
   rect changes, the heap copy freed in the cleanup callback; skipped while MAX_PENDING_UPLOADS are not yet copied) and binds
   it through the PC bridge (USub01PCBridge::SetMonitorFeedFrame). Progress (a new upload < `monitor_stale_s` ago, default
   STALE_SECONDS) = the feed; none (a dead feed), `monitor_feed` 0 or a closed gate = the bridge's own picture again and the
   texture blanked (`monitor_feed` 0 also closes the FIFO, so the sidecar stops ffmpeg). Pumps run at `monitor_fps`.
2. Privacy gate (fail closed, enforced by the bridge AND by the character every tick): the bridge allows the feed only while it
   is public (no Private, LocalPrivacy, PrivacyDesired, not the read-only cinematic browser), the runner's last public state
   read said pc_mode "vagon", vagon.connected AND vagon.phase "connected" (the sidecar's rule) and an available graphical
   display (the runner shows only a neutral picture
   before the remote desktop is connected: the owner's login/account pages; a raw x11grab would bypass that), and that read
   STARTED less than CONFIRM_SECONDS ago. Every "PCFrame" binding of the bridge goes through ShowFrame -> SelectMonitorFrame
   (the MID is touched only on a change, so its 0.5 s poll never fights the feed); ClearPrivateState drops the feed at once,
   the poll timer re-selects even while a poll hangs, and a feed frame the character stops renewing for RENEW_SECONDS is
   dropped. On the character side every gate change or bridge privacy generation change starts a new epoch (logged
   `..._MONITOR_FEED_GATE`): bytes read while closed are discarded, queued and decoded frames of another epoch are never
   uploaded, and after a reopen the first GUARD_SECONDS of FIFO data are discarded (the pipe and ffmpeg hold older frames).
3. No per-frame UTexture2D in the bridges: the PC bridge's FImageUtils::CreateTexture2DFromImage (one texture per VGA frame)
   and the device bridge's FImageUtils::ImportBufferAsTexture2D (one per phone/TV frame) become one persistent texture per
   screen and size, updated in place (the device bridge decodes with FImageUtils::DecompressImage + FImage::CopyTo BGRA8 sRGB).
   The existing meaning of GraphicalFrame / Images (what is shown; emptied on privacy) is unchanged.
4. cam2 exposure (it copied the webcam's post process at start; the house's histogram volume is EV100 -3..+3 with the default
   bias 1, and the cam2 view of the white walls clipped): `cam2_exposure` 0 = as copied (v21), 1 = automatic (histogram,
   forced) with `cam2_ev_bias` (+ the EV100 range `cam2_ev_min`..`cam2_ev_max` while min <= max), 2 = manual (fixed, physical
   camera exposure off: the bias is then the absolute log2 scale, +4 matches the webcam pinned at the house's EV100 -3 floor
   with bias 1) at `cam2_ev_bias`; modes 1/2 force the capture's post-process weight to 1; mode 0 restores exactly what was
   copied. Default mode 1, bias -1: two stops below the house's compensation (Kimi proposed manual -3, which is ~7 stops
   darker than the webcam; Kimi agreed in the review). Applied on change, logged `SUB01_STREAMER_VISUAL_CAM2_EXPOSURE`. The
   main camera is not touched.
Teardown: the PC bridge's EndPlay releases the feed (the MID leaves its texture at once). Streamer mode lives for the whole
process (StreamerVisualStarted is set once); the reader's FIFO descriptor closes when the character's feed object is
destroyed (after a pump in flight, on its worker), at the latest at the character's destruction.
Logs: `SUB01_STREAMER_VISUAL_MONITOR_FEED started ...` once, then `fps= decoded= dropped= stale= ...` every LOG_SECONDS;
`..._MONITOR_FEED_BOUND` / `..._MONITOR_FEED_FALLBACK` on changes. Receipt: monitor_feed_* and cam2_exposure/cam2_ev_* fields.
Tuning keys (the private tuning file, their own V22 line): monitor_feed, monitor_fps, monitor_delay_s, monitor_stale_s,
cam2_exposure, cam2_ev_bias, cam2_ev_min, cam2_ev_max.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, _HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


v21 = _load('sub01_streamer_visual_v2_v21', 'install_v21_fixes.py')
cam2, posefix, streampass = v21.cam2, v21.posefix, v21.streampass
seatfix, v2, Refused = streampass.seatfix, streampass.v2, streampass.Refused
_f = streampass._f

MARKER = '// SUB01_STREAMER_VISUAL_V2_V22'
FILES = {'header': 'Sub01HomeLab.h', 'cpp': 'Sub01HomeLab.cpp', 'pc_header': 'Sub01PCBridge.h', 'pc_cpp': 'Sub01PCBridge.cpp',
         'dev_header': 'Sub01HomeDeviceBridge.h', 'dev_cpp': 'Sub01HomeDeviceBridge.cpp'}
NEW_HEADER = 'Sub01PersistentTexture.h'
LAYOUT_HEADER = 'Sub01GuestFrameLayout.h'          # the PC bridge's own layout (pod source); the character includes it too
CINEMATIC_PC_INC = 'native_cinematic_pc.inc'       # included at the end of Sub01PCBridge.cpp; must not bind "PCFrame" itself

FIFO_NAME = 'monitor.mjpeg'                         # scripts/streamer_monitor_feed.py, in the cam2 streamer directory
MONITOR_FEED, MONITOR_FPS = 1, 60.0                 # owner: 60 fps on everything (a cap; the pod fallback is 30 if the render thread suffers)
PLAYOUT_SECONDS = 0.75                              # privacy playout: a frame is shown >= this long after it was read, and only once a
                                                    # public confirmation that STARTED after its read has completed (Kimi's design review)
STALE_SECONDS = 2.0                                 # `monitor_stale_s`: no new upload for this long (no progress: a dead feed) = the bridge's
                                                    # own picture again and the texture blanked; above the sidecar's 0.5 s neutral-frame repeat
CONFIRM_SECONDS = 1.5                               # the bridge's last public, connected state read must have started this recently
RENEW_SECONDS = 1.0                                 # a feed frame the character stops renewing is dropped by the bridge
GUARD_SECONDS = 0.25                                # FIFO data read in the first GUARD_SECONDS after the gate reopens is discarded
REOPEN_SECONDS = 1.0                                # FIFO open retried at most this often
CHUNK_BYTES, PUMP_BYTES = 256 << 10, 8 << 20        # read() size; at most this much read per pump
MAX_FRAME_BYTES = 4 << 20                           # a "frame" longer than this is garbage: resync
RING_FRAMES, RING_BYTES = 64, 16 << 20              # compressed frames waiting for their playout (newest kept; oldest dropped beyond)
MAX_PENDING_UPLOADS = 3                             # texture uploads the RHI has not copied yet: a newer frame waits (dropped) beyond
MAX_W, MAX_H = 1280, 1024                           # Sub01GuestFrameLayout's limits (checked from the JPEG header before decoding)
LOG_SECONDS, GATE_LOG_SECONDS = 5.0, 1.0            # the periodic line; gate transitions at once, at most one line per GATE_LOG_SECONDS
CAM2_EXPOSURE, CAM2_EV_BIAS = 1, -1.0               # auto exposure, bias 1 -> -1: 2 EV below the house's default compensation in every
                                                    # eye-adaptation state (Kimi proposed manual at -3; see native-v22-design.md for why not)
CAM2_EV_MIN, CAM2_EV_MAX = 0.0, -1.0                # min > max: the EV100 range is NOT overridden (the house volume's -3..+3 stays)

TUNING_LIMITS = {'monitor_feed': (0, 1), 'monitor_fps': (1, 60), 'monitor_delay_s': (0.5, 3), 'monitor_stale_s': (0.5, 10), 'cam2_exposure': (0, 2),
                 'cam2_ev_bias': (-8, 8), 'cam2_ev_min': (-10, 20), 'cam2_ev_max': (-10, 20)}
TUNING_FIELDS = {'monitor_feed': 'StreamerVisualMonitorFeedOn', 'monitor_fps': 'StreamerVisualMonitorFps', 'monitor_delay_s': 'StreamerVisualMonitorDelaySeconds',
                 'monitor_stale_s': 'StreamerVisualMonitorStaleSeconds',
                 'cam2_exposure': 'StreamerVisualCam2Exposure', 'cam2_ev_bias': 'StreamerVisualCam2EvBias', 'cam2_ev_min': 'StreamerVisualCam2EvMin',
                 'cam2_ev_max': 'StreamerVisualCam2EvMax'}
assert set(TUNING_FIELDS) == set(TUNING_LIMITS)


def _fill(text: str, **values) -> str:
    """C++ blocks carry @@NAME@@ placeholders (no f-string brace doubling); every placeholder must be filled."""
    for key, value in values.items():
        text = text.replace(f'@@{key}@@', value if isinstance(value, str) else _num(value))
    assert '@@' not in text, text[text.index('@@') - 40:text.index('@@') + 40]
    return text


def _num(value) -> str:
    return str(int(value)) if float(value).is_integer() and isinstance(value, int) else repr(float(value))


COMMON = dict(FIFO=FIFO_NAME, STALE=STALE_SECONDS, CONFIRM=CONFIRM_SECONDS, RENEW=RENEW_SECONDS, GUARD=GUARD_SECONDS, REOPEN=REOPEN_SECONDS,
              CHUNK=CHUNK_BYTES, PUMP_BYTES=PUMP_BYTES, MAX_FRAME=MAX_FRAME_BYTES, MAX_W=MAX_W, MAX_H=MAX_H, LOG=LOG_SECONDS,
              RING_FRAMES=RING_FRAMES, RING_BYTES=RING_BYTES, MAX_PENDING=MAX_PENDING_UPLOADS, GATE_LOG=GATE_LOG_SECONDS)

# ------------------------------------------------------------------------------------------------ Sub01PersistentTexture.h (new)
PERSISTENT_HEADER = '''#pragma once
// SUB01_STREAMER_VISUAL_V2_V22 (tools/native_streamer_visual_v2/install_v22.py): one persistent B8G8R8A8 sRGB texture per screen (and size),
// updated in place with UpdateTextureRegions, instead of a new UTexture2D for every picture (PC bridge, device bridge, monitor feed).
#include "CoreMinimal.h"
#include "Engine/Texture2D.h"
#include "RHI.h"
#include <atomic>
namespace Sub01PersistentTexture{
// Uploads enqueued and not yet copied by the RHI (all callers): a caller that streams frames checks it so a stalled render thread
// cannot pile up pixel buffers.
inline std::atomic<int32>& PendingUploads(){static std::atomic<int32> Count{0};return Count;}
// Copies Width x Height tightly packed BGRA8 rows (moved in) into the texture's region at (X,Y). The pixels and the region live on the heap
// until the RHI has copied them (freed in the cleanup callback, never on the game thread). False (nothing enqueued, the caller keeps the
// pixels) when the texture has no resource, the region leaves the texture or the buffer has the wrong size. Game thread only.
inline bool Update(UTexture2D* Texture,int32 X,int32 Y,int32 Width,int32 Height,TArray64<uint8>&& Pixels){
 if(!Texture||!Texture->GetResource()||X<0||Y<0||Width<1||Height<1||X+Width>Texture->GetSizeX()||Y+Height>Texture->GetSizeY()||Pixels.Num()!=int64(Width)*Height*4)return false;
 TArray64<uint8>* Owned=new TArray64<uint8>(MoveTemp(Pixels));
 FUpdateTextureRegion2D* Region=new FUpdateTextureRegion2D(uint32(X),uint32(Y),0,0,uint32(Width),uint32(Height));
 ++PendingUploads();
 Texture->UpdateTextureRegions(0,1,Region,uint32(Width)*4,4,Owned->GetData(),[Owned](uint8*,const FUpdateTextureRegion2D* Done){delete Owned;delete Done;--PendingUploads();});
 return true;
}
// The whole texture opaque black (B,G,R 0, A 255; zeroes alone would be transparent): at creation, and before a new source rectangle.
inline bool Clear(UTexture2D* Texture){
 if(!Texture)return false;TArray64<uint8> Black;Black.SetNumZeroed(int64(Texture->GetSizeX())*Texture->GetSizeY()*4);for(int64 I=3;I<Black.Num();I+=4)Black[I]=255;
 return Update(Texture,0,0,Texture->GetSizeX(),Texture->GetSizeY(),MoveTemp(Black));
}
// The texture to update: Texture itself when it already has this size, else a new transient one (B8G8R8A8, sRGB, one mip, never streamed,
// clamped, bilinear, all set before its resource exists) cleared once (CreateTransient leaves its mip uninitialised). Texture must be a
// UPROPERTY slot of the caller (the GC owner); the old texture is left to the garbage collector once the caller binds the new one.
// Created counts the textures made. Game thread only.
inline UTexture2D* Ensure(TObjectPtr<UTexture2D>& Texture,int32 Width,int32 Height,int32* Created=nullptr){
 if(Width<1||Height<1||Width>4096||Height>4096)return nullptr;
 if(Texture&&Texture->GetSizeX()==Width&&Texture->GetSizeY()==Height&&Texture->GetResource())return Texture;
 UTexture2D* Made=UTexture2D::CreateTransient(Width,Height,PF_B8G8R8A8);if(!Made)return nullptr;
 Made->SRGB=true;Made->NeverStream=true;Made->Filter=TF_Bilinear;Made->AddressX=TA_Clamp;Made->AddressY=TA_Clamp;Made->UpdateResource();
 if(!Clear(Made))return nullptr;
 Texture=Made;if(Created)++*Created;return Made;
}
}
'''

# ------------------------------------------------------------------------------------------------ Sub01PCBridge.h
PC_FORWARD = 'class UTexture2D;\n'
PC_FORWARD_V22 = PC_FORWARD + 'class UTexture; // SUB01_STREAMER_VISUAL_V2_V22\n'
PC_PUBLIC_ANCHOR = ' bool HasOperatorFocus() const { return Focused; }\n'
PC_PUBLIC = PC_PUBLIC_ANCHOR + _fill(''' // SUB01_STREAMER_VISUAL_V2_V22 BEGIN (tools/native_streamer_visual_v2/install_v22.py): the game-side monitor feed may stand in for
 // this bridge's picture, only while the bridge itself would show the PC (public, the Vagon desktop connected, confirmed < @@CONFIRM@@ s ago).
 bool IsMonitorFeedAllowed(double Now) const;
 FString MonitorFeedGateReason(double Now) const; // "open" or the first closed condition (logs, receipt)
 bool SetMonitorFeedFrame(UTexture* Frame); // renewed every tick by the character; null = the bridge's own picture; false while closed
 double GetMonitorConfirmedAt() const { return FeedSourceConnected?PublicConfirmedAt:-1.; } // start of the newest validating public read
 uint64 GetMonitorPrivacyGeneration() const { return Generation; }
 double GetMonitorScreenAspect() const { return ScreenAspect; }
 int32 GetMonitorTexturesCreated() const { return FramesCreated; }
 // SUB01_STREAMER_VISUAL_V2_V22 END
''', **COMMON)
PC_PRIVATE_ANCHOR = ' UPROPERTY() TObjectPtr<UTexture2D> GraphicalFrame;\n'
PC_PRIVATE = PC_PRIVATE_ANCHOR + ''' // SUB01_STREAMER_VISUAL_V2_V22 BEGIN (private): one persistent texture for the VGA frames; the feed's texture, the bridge's own wanted
 // picture and what the MID shows (bound only on a change)
 UPROPERTY() TObjectPtr<UTexture2D> PersistentFrame;
 UPROPERTY() TObjectPtr<UTexture> FeedFrame;
 UPROPERTY() TObjectPtr<UTexture> OwnFrame;
 UPROPERTY() TObjectPtr<UTexture> BoundFrame;
 double PublicConfirmedAt=-1,FeedFrameAt=-1;bool FeedSourceConnected=false;int32 FramesCreated=0;
 void ShowFrame(UTexture* Own);void SelectMonitorFrame();void ReleaseMonitorFeed();void NoteMonitorFeedSource(const TSharedPtr<FJsonObject>& State,double AskedAt);
 // SUB01_STREAMER_VISUAL_V2_V22 END (private)
'''

# ------------------------------------------------------------------------------------------------ Sub01PCBridge.cpp
PC_INCLUDE = '#include "Sub01GuestFrameLayout.h"\n'
PC_INCLUDE_V22 = PC_INCLUDE + '#include "Sub01PersistentTexture.h" // SUB01_STREAMER_VISUAL_V2_V22\n'
PC_BIND = 'MonitorMaterial->SetTextureParameterValue(TEXT("PCFrame"),'
PC_BIND_SITES = 6                                   # Configure, ClearPrivateState, ApplyTerminal x2, FetchGraphicalFrame x2
PC_CLEAR = 'void USub01PCBridge::ClearPrivateState(const FString& Reason){\n'
PC_CLEAR_V22 = PC_CLEAR + ' FeedFrame=nullptr;PublicConfirmedAt=-1;FeedSourceConnected=false; // SUB01_STREAMER_VISUAL_V2_V22: the feed is never shown during privacy\n'
PC_ENDPLAY = 'void USub01PCBridge::EndPlay(const EEndPlayReason::Type Reason){\n'
PC_ENDPLAY_V22 = PC_ENDPLAY + ' ReleaseMonitorFeed(); // SUB01_STREAMER_VISUAL_V2_V22: the gate closes and the MID leaves the feed\'s texture now (Kimi\'s review)\n'
PC_POLL_TOP = 'void USub01PCBridge::Poll(){\n'
PC_POLL_TOP_V22 = PC_POLL_TOP + (' SelectMonitorFrame(); // SUB01_STREAMER_VISUAL_V2_V22: a feed whose gate expired (a hung backend) or that nobody renews goes on this\n'
                                 ' // 0.5 s timer even while the poll below still waits\n')
PC_POLL = '  ReadState([this,Epoch](TSharedPtr<FJsonObject> After){\n'
PC_POLL_V22 = ('  const double AskedAt=FPlatformTime::Seconds(); // SUB01_STREAMER_VISUAL_V2_V22: when the confirming read started\n'
               '  ReadState([this,Epoch,AskedAt](TSharedPtr<FJsonObject> After){\n')
PC_APPLY = '   ApplyTerminal(After);\n   FetchGraphicalFrame(After);\n'
PC_APPLY_V22 = '   NoteMonitorFeedSource(After,AskedAt); // SUB01_STREAMER_VISUAL_V2_V22\n' + PC_APPLY
PC_TEXTURE = ('   UTexture2D* Texture=FImageUtils::CreateTexture2DFromImage(Padded);\n'
              '   if(!Texture)return;\n'
              '   Texture->SRGB=true;Texture->UpdateResource();GraphicalFrame=Texture;FrameRevision=Wanted;\n')
PC_TEXTURE_V22 = ('   // SUB01_STREAMER_VISUAL_V2_V22: one persistent texture per size, updated in place (it was a new UTexture2D for every frame)\n'
                  '   UTexture2D* Texture=Sub01PersistentTexture::Ensure(PersistentFrame,Layout.Width,Layout.Height,&FramesCreated);\n'
                  '   if(!Texture||!Sub01PersistentTexture::Update(Texture,0,0,Layout.Width,Layout.Height,MoveTemp(Padded.RawData)))return;\n'
                  '   GraphicalFrame=Texture;FrameRevision=Wanted;\n')
PC_TAIL = '\n#include "native_cinematic_pc.inc"\n'
PC_METHODS = _fill('''
// SUB01_STREAMER_VISUAL_V2_V22 BEGIN (tools/native_streamer_visual_v2/install_v22.py): the game-side monitor feed stands in for this
// bridge's picture only while this bridge would show the PC itself.
void USub01PCBridge::ShowFrame(UTexture* Own){OwnFrame=Own;SelectMonitorFrame();} // every "PCFrame" binding of this bridge comes here
void USub01PCBridge::SelectMonitorFrame(){
 // The one selection: the feed's texture while it is set, renewed (< @@RENEW@@ s) and allowed, else the bridge's own latest picture. Gate
 // closures through ClearPrivateState are immediate; time-based ones (a confirmation that grew old) are caught here by the next renewal or by
 // the poll timer. The MID is touched only when the choice changes: every texture here is updated in place.
 if(!MonitorMaterial)return;const double Now=FPlatformTime::Seconds();
 if(FeedFrame&&!(IsMonitorFeedAllowed(Now)&&Now-FeedFrameAt<=@@RENEW@@))FeedFrame=nullptr;
 UTexture* Wanted=FeedFrame?FeedFrame.Get():OwnFrame?OwnFrame.Get():static_cast<UTexture*>(TerminalCanvas.Get());
 if(BoundFrame&&BoundFrame.Get()==Wanted)return;
 BoundFrame=Wanted;MonitorMaterial->SetTextureParameterValue(TEXT("PCFrame"),Wanted);
}
bool USub01PCBridge::IsMonitorFeedAllowed(double Now)const{
 // Fail closed: public (no Private, local or desired privacy), not the read-only cinematic browser, the Vagon remote desktop CONNECTED with a
 // graphical display (before that the runner itself shows only a neutral picture: the owner's login and account pages), confirmed by a public
 // state read that STARTED less than @@CONFIRM@@ s ago (the poll runs every 0.5 s; a hung backend closes the gate instead of keeping "public").
 return MonitorMaterial&&!ReadOnlyBrowser&&!Private&&!LocalPrivacy&&!PrivacyDesired&&FeedSourceConnected&&PublicConfirmedAt>=0&&Now>=PublicConfirmedAt&&Now-PublicConfirmedAt<=@@CONFIRM@@;
}
FString USub01PCBridge::MonitorFeedGateReason(double Now)const{
 if(!MonitorMaterial)return TEXT("no monitor material");if(ReadOnlyBrowser)return TEXT("read-only cinematic browser");
 if(LocalPrivacy||PrivacyDesired)return TEXT("local privacy");if(Private)return TEXT("PC private or backend unavailable");
 if(!FeedSourceConnected)return TEXT("source mismatch (not the public, connected Vagon desktop)");
 if(PublicConfirmedAt<0||Now<PublicConfirmedAt||Now-PublicConfirmedAt>@@CONFIRM@@)return TEXT("no recent public confirmation");
 return TEXT("open");
}
bool USub01PCBridge::SetMonitorFeedFrame(UTexture* Frame){
 const double Now=FPlatformTime::Seconds();if(Frame&&!IsMonitorFeedAllowed(Now))Frame=nullptr; // refused while closed: the bridge's own picture stays
 FeedFrame=Frame;if(Frame)FeedFrameAt=Now;SelectMonitorFrame();
 return Frame!=nullptr&&BoundFrame.Get()==Frame;
}
void USub01PCBridge::ReleaseMonitorFeed(){
 // EndPlay: the gate closes AND the MID leaves the feed's texture now (no timer or character will select again), then nothing is held.
 FeedFrame=nullptr;PublicConfirmedAt=-1;FeedSourceConnected=false;OwnFrame=TerminalCanvas.Get();SelectMonitorFrame();OwnFrame=nullptr;BoundFrame=nullptr;
}
void USub01PCBridge::NoteMonitorFeedSource(const TSharedPtr<FJsonObject>& State,double AskedAt){
 // The poll's confirming read (timestamped with its START): the feed shows the Vagon desktop raw, so it needs pc_mode "vagon", vagon.connected
 // AND vagon.phase "connected" (the monitor feed sidecar's own rule: the host page's login/dashboard can come with connected still true) and
 // an available graphical display in a public state; anything else (missing fields included) closes the gate. Stricter than the sidecar:
 // chromium mode is refused, and so is a Vagon "streams" runner unless it reports connected + phase "connected", because this bridge's
 // origin need not be the runner whose display is captured.
 FString Mode,Phase,Kind;bool Connected=false,Available=false;const TSharedPtr<FJsonObject>* Vagon=nullptr;const TSharedPtr<FJsonObject>* Screen=nullptr;
 FeedSourceConnected=IsPublicState(State)&&State->TryGetStringField(TEXT("pc_mode"),Mode)&&Mode==TEXT("vagon")&&State->TryGetObjectField(TEXT("vagon"),Vagon)&&Vagon&&(*Vagon).IsValid()
  &&(*Vagon)->TryGetBoolField(TEXT("connected"),Connected)&&Connected&&(*Vagon)->TryGetStringField(TEXT("phase"),Phase)&&Phase==TEXT("connected")
  &&State->TryGetObjectField(TEXT("display"),Screen)&&Screen&&(*Screen).IsValid()
  &&(*Screen)->TryGetBoolField(TEXT("available"),Available)&&Available&&(*Screen)->TryGetStringField(TEXT("kind"),Kind)&&Kind==TEXT("graphical");
 PublicConfirmedAt=FeedSourceConnected?AskedAt:-1.;SelectMonitorFrame();
}
// SUB01_STREAMER_VISUAL_V2_V22 END
''', **COMMON) + PC_TAIL[1:]

# ------------------------------------------------------------------------------------------------ Sub01HomeDeviceBridge.h/.cpp
DEV_FIELD = ' UPROPERTY()TMap<FName,TObjectPtr<UTexture2D>> Images;\n'
DEV_FIELD_V22 = DEV_FIELD + (' UPROPERTY()TMap<FName,TObjectPtr<UTexture2D>> PersistentImages; // SUB01_STREAMER_VISUAL_V2_V22: one texture per device (and size), updated in place\n'
                             ' int32 PersistentImagesCreated=0; // SUB01_STREAMER_VISUAL_V2_V22\n')
DEV_INCLUDE = '#include "ImageUtils.h"\n'
DEV_INCLUDE_V22 = DEV_INCLUDE + '#include "ImageCore.h" // SUB01_STREAMER_VISUAL_V2_V22\n#include "Sub01PersistentTexture.h"\n'
DEV_TEXTURE = ('   auto* Texture=FImageUtils::ImportBufferAsTexture2D(Pixels);if(!Texture||Texture->GetSizeX()>2048||Texture->GetSizeY()>2048)return;'
               'Texture->SRGB=true;Texture->UpdateResource();')
DEV_TEXTURE_V22 = ('   // SUB01_STREAMER_VISUAL_V2_V22: decoded here, then one persistent texture per device (and size) updated in place (it was a new UTexture2D per frame)\n'
                   '   FImage Decoded,BGRA;if(!FImageUtils::DecompressImage(Pixels.GetData(),Pixels.Num(),Decoded)||Decoded.NumSlices!=1||Decoded.SizeX<1||Decoded.SizeY<1||Decoded.SizeX>2048||Decoded.SizeY>2048)return;'
                   'Decoded.CopyTo(BGRA,ERawImageFormat::BGRA8,EGammaSpace::sRGB);\n'
                   '   UTexture2D* Texture=Sub01PersistentTexture::Ensure(PersistentImages.FindOrAdd(Device),BGRA.SizeX,BGRA.SizeY,&PersistentImagesCreated);'
                   'if(!Texture||!Sub01PersistentTexture::Update(Texture,0,0,BGRA.SizeX,BGRA.SizeY,MoveTemp(BGRA.RawData)))return;\n   ')

# ------------------------------------------------------------------------------------------------ Sub01HomeLab.h
HEADER_V21_END = ' // SUB01_STREAMER_VISUAL_V2_V21 END\n'
HEADER_FIELDS = _fill(''' // SUB01_STREAMER_VISUAL_V2_V22 BEGIN (tools/native_streamer_visual_v2/install_v22.py): the in-game monitor fed from @@FIFO@@ (gated by the
 // PC bridge, one persistent texture) and camera 2's exposure.
 void StartStreamerVisualMonitorFeed();void UpdateStreamerVisualMonitorFeed(double Now,float Dt);bool UploadStreamerVisualMonitorFrame(TArray64<uint8>& Pixels,int32 Width,int32 Height);
 void LogStreamerVisualMonitorFeed(double Now);FString StreamerVisualMonitorFeedReason() const;void ApplyStreamerVisualCam2Exposure();
 TSharedPtr<class FSub01MonitorFeed> StreamerVisualMonitorFeed; // shared with the reader task
 UPROPERTY() TObjectPtr<class UTexture2D> StreamerVisualMonitorTexture;
 float StreamerVisualMonitorFeedOn=@@ON@@,StreamerVisualMonitorFps=@@FPS@@,StreamerVisualMonitorDelaySeconds=@@DELAY@@,StreamerVisualMonitorStaleSeconds=@@STALE@@;
 float StreamerVisualMonitorFeedFpsShown=0,StreamerVisualMonitorFeedFpsIn=0;FString StreamerVisualMonitorFeedGateReason=TEXT("not started");
 bool StreamerVisualMonitorFeedGate=false,StreamerVisualMonitorFeedBound=false;uint64 StreamerVisualMonitorFeedGeneration=0;int32 StreamerVisualMonitorFeedEpoch=0,StreamerVisualMonitorFeedShownEpoch=-1,StreamerVisualMonitorTexturesCreated=0;
 double StreamerVisualMonitorFeedGateAt=0,StreamerVisualMonitorFeedShownReadAt=-1,StreamerVisualMonitorFeedUploadAt=-1,StreamerVisualMonitorFeedNextAt=0,StreamerVisualMonitorFeedLogAt=0,StreamerVisualMonitorFeedWindowAt=0,StreamerVisualMonitorFeedGateLogAt=0;
 double StreamerVisualMonitorFeedReasonAt=0;
 int64 StreamerVisualMonitorFeedShown=0,StreamerVisualMonitorFeedRejected=0,StreamerVisualMonitorFeedUploadBusy=0,StreamerVisualMonitorFeedUploadBytes=0,StreamerVisualMonitorFeedStale=0,StreamerVisualMonitorFeedWindowBase[5]={0,0,0,0,0};
 int32 StreamerVisualMonitorFeedGateLogSuppressed=0,StreamerVisualMonitorRect[4]={-1,-1,-1,-1};
 float StreamerVisualCam2Exposure=@@EXPOSURE@@,StreamerVisualCam2EvBias=@@BIAS@@,StreamerVisualCam2EvMin=@@EVMIN@@,StreamerVisualCam2EvMax=@@EVMAX@@,StreamerVisualCam2ExposureState[4]={-1e9f,-1e9f,-1e9f,-1e9f};
 bool StreamerVisualCam2BaseSaved=false,StreamerVisualCam2BaseBiasSet=false,StreamerVisualCam2BaseMethodSet=false,StreamerVisualCam2BaseMinSet=false,StreamerVisualCam2BaseMaxSet=false,StreamerVisualCam2BasePhysicalSet=false,StreamerVisualCam2BasePhysical=false;
 float StreamerVisualCam2BaseBias=1,StreamerVisualCam2BaseMin=0,StreamerVisualCam2BaseMax=0,StreamerVisualCam2BaseWeight=1;uint8 StreamerVisualCam2BaseMethod=0;
 // SUB01_STREAMER_VISUAL_V2_V22 END
''', FIFO=FIFO_NAME, ON=_f(MONITOR_FEED), FPS=_f(MONITOR_FPS), DELAY=_f(PLAYOUT_SECONDS), STALE=_f(STALE_SECONDS), EXPOSURE=_f(CAM2_EXPOSURE), BIAS=_f(CAM2_EV_BIAS),
   EVMIN=_f(CAM2_EV_MIN), EVMAX=_f(CAM2_EV_MAX))

# ------------------------------------------------------------------------------------------------ Sub01HomeLab.cpp
INCLUDE_ANCHOR = '#include "HAL/IConsoleManager.h" // SUB01_STREAMER_VISUAL_V2_V21\n'
INCLUDE_V22 = INCLUDE_ANCHOR + ('#include "Sub01PersistentTexture.h" // SUB01_STREAMER_VISUAL_V2_V22: the monitor feed\'s persistent texture\n'
                                '#include "Sub01GuestFrameLayout.h" // SUB01_STREAMER_VISUAL_V2_V22: the PC bridge\'s own layout\n'
                                '#include "Sub01PCBridge.h"\n#include "IImageWrapper.h"\n#include <vector>\n#include <deque>\n#include <cstring>\n')
FACE_BEGIN = v21.FACE_BEGIN
CPP_METHODS = _fill('''// SUB01_STREAMER_VISUAL_V2_V22 BEGIN (tools/native_streamer_visual_v2/install_v22.py)
// ---- the in-game monitor fed from <streamer-dir>/@@FIFO@@ (scripts/streamer_monitor_feed.py: x11grab of the Vagon desktop, whole JPEGs back to back)
struct FSub01JpegScan{int64 Start=-1,End=-1,Consumed=0,Skipped=0;int32 Frames=0,Resyncs=0;};
static FSub01JpegScan Sub01ScanJpegs(const uint8* B,int64 N,int64 MaxFrame){
 // Complete JPEGs in B[0..N): SOI (FF D8 FF), marker segments skipped by their length (fill FFs, standalone 01/RST0-7), the entropy data after
 // each SOS scanned for an FF that is neither stuffing (FF 00) nor a restart marker, up to EOI (FF D9); an FF D9 inside a segment never ends a
 // frame. Garbage, a byte or a reserved marker (02..BF) where a marker must be, an SOI inside a frame (the frame before it was cut) or a frame
 // over MaxFrame bytes = resync at
 // the next SOI. Out: the newest complete frame [Start,End), how many were complete, and Consumed = the bytes that can go (all but an
 // unfinished frame or a possibly split SOI at the end).
 FSub01JpegScan Out;int64 Pos=0;
 auto FindSoi=[B,N](int64 From)->int64{for(int64 I=From;I+2<N;){const void* Hit=memchr(B+I,0xFF,size_t(N-2-I));if(!Hit)return -1;I=static_cast<const uint8*>(Hit)-B;if(B[I+1]==0xD8&&B[I+2]==0xFF)return I;++I;}return -1;};
 for(;;){
  const int64 S=FindSoi(Pos);
  if(S<0){int64 Keep=0;if(N-Pos>=1&&B[N-1]==0xFF)Keep=1;if(N-Pos>=2&&B[N-2]==0xFF&&B[N-1]==0xD8)Keep=2;if(N-Keep>Pos){Out.Skipped+=N-Keep-Pos;++Out.Resyncs;}Out.Consumed=N-Keep;return Out;}
  if(S>Pos){Out.Skipped+=S-Pos;++Out.Resyncs;}
  int64 P=S+2;int32 State=0; // 0 walking, 1 complete, 2 unfinished, 3 bad
  while(State==0){
   if(P-S>MaxFrame){State=3;break;}
   if(P+1>=N){State=2;break;}
   if(B[P]!=0xFF){State=3;break;}
   while(P+1<N&&B[P+1]==0xFF)++P; // fill bytes before a marker
   if(P+1>=N){State=2;break;}
   const uint8 Marker=B[P+1];
   if(Marker==0xD9){P+=2;State=1;break;}
   if(Marker==0xD8||Marker==0x00){State=3;break;}
   if(Marker==0x01||(Marker>=0xD0&&Marker<=0xD7)){P+=2;continue;}
   if(Marker<0xC0){State=3;break;} // a reserved marker: not a JPEG (a stray FF D8 FF in garbage), resync now instead of trusting its length
   if(P+3>=N){State=2;break;}
   const int64 Length=(int64(B[P+2])<<8)|int64(B[P+3]);if(Length<2){State=3;break;}
   P+=2+Length;
   if(Marker!=0xDA)continue;
   for(;;){ // entropy-coded data after SOS
    if(P-S>MaxFrame){State=3;break;}
    if(P>=N){State=2;break;}
    const void* Hit=memchr(B+P,0xFF,size_t(N-P));if(!Hit){State=N-S>MaxFrame?3:2;break;}
    P=static_cast<const uint8*>(Hit)-B;
    if(P+1>=N){State=2;break;}
    const uint8 Next=B[P+1];
    if(Next==0x00||(Next>=0xD0&&Next<=0xD7)){P+=2;continue;}
    break; // a real marker (or fill bytes before one): back to the walk
   }
  }
  if(State==1){++Out.Frames;Out.Start=S;Out.End=P;Pos=P;continue;}
  if(State==2){Out.Consumed=S;return Out;}
  ++Out.Skipped;Pos=S+1; // bad: resync on the next SOI (an SOI inside this frame is found again from here)
 }
}
struct FSub01MonitorQueued{std::vector<uint8> Bytes;double ReadAt=0;}; // a whole JPEG waiting for its playout
struct FSub01MonitorFrame{TArray64<uint8> Pixels;int32 Width=0,Height=0,Epoch=0;double ReadAt=0;};
class FSub01MonitorFeed{
 // ONE background task at a time (Busy) owns the FIFO descriptor, the parse buffer, the playout ring and the decoder; the game thread launches
 // it, takes the decoded frame (Ready: a pointer swap), uploads it and binds it through the PC bridge, which enforces the privacy gate too.
public:
 FString FifoPath;IImageWrapperModule* Images=nullptr;
 std::atomic<int32> Busy{0},OpenErrno{0},Refused{0},Queued{0};std::atomic<bool> Open{false};std::atomic<FSub01MonitorFrame*> Ready{nullptr};
 std::atomic<int64> Bytes{0},Frames{0},DroppedOlder{0},DroppedEpoch{0},DroppedOverflow{0},DroppedUntaken{0},Decoded{0},DecodeFailed{0},Resyncs{0},Discarded{0};
 std::atomic<int64> DecodeUs{0},DecodeMaxUs{0},QueuedBytes{0};
 // the task only
 int Fd=-1;double NextOpenAt=0;int32 BufferEpoch=-1;std::vector<uint8> Buffer,Chunk;std::deque<FSub01MonitorQueued> Ring;int64 RingBytes=0;
 ~FSub01MonitorFeed(){if(Fd>=0)::close(Fd);delete Ready.exchange(nullptr);}
 void ClearRing(){Ring.clear();RingBytes=0;Queued.store(0);QueuedBytes.store(0);}
 void Close(){if(Fd>=0){::close(Fd);Fd=-1;}Open.store(false);Buffer.clear();ClearRing();}
 bool OpenFifo(double Now){ // non-blocking, never through a link; only this user's FIFO without group/other bits (checked before and after the open)
  if(Now<NextOpenAt)return false;NextOpenAt=Now+@@REOPEN@@;struct stat Info;
  if(::lstat(TCHAR_TO_UTF8(*FifoPath),&Info)!=0){OpenErrno.store(errno);return false;}
  if(!S_ISFIFO(Info.st_mode)||Info.st_uid!=getuid()||(Info.st_mode&0077)){Refused.store(1);OpenErrno.store(0);return false;}
  const int Opened=::open(TCHAR_TO_UTF8(*FifoPath),O_RDONLY|O_NONBLOCK|O_CLOEXEC|O_NOFOLLOW);
  if(Opened<0){OpenErrno.store(errno);return false;}
  if(::fstat(Opened,&Info)!=0||!S_ISFIFO(Info.st_mode)||Info.st_uid!=getuid()||(Info.st_mode&0077)){::close(Opened);Refused.store(1);return false;}
  Fd=Opened;Refused.store(0);OpenErrno.store(0);Open.store(true);Buffer.clear();ClearRing();return true;
 }
 bool Decode(const uint8* Data,int64 Size,FSub01MonitorFrame& Out)const{ // JPEG -> BGRA8; the size is checked from the header before any pixel buffer exists
  if(!Images||Size<=0)return false;const TSharedPtr<IImageWrapper> Wrapper=Images->CreateImageWrapper(EImageFormat::JPEG);
  if(!Wrapper.IsValid()||!Wrapper->SetCompressed(Data,Size))return false;
  const int64 W=Wrapper->GetWidth(),H=Wrapper->GetHeight();if(W<1||H<1||W>@@MAX_W@@||H>@@MAX_H@@)return false; // <= 1280x1024: W*H*4 cannot overflow
  if(!Wrapper->GetRaw(ERGBFormat::BGRA,8,Out.Pixels)||Out.Pixels.Num()!=W*H*4)return false;
  Out.Width=int32(W);Out.Height=int32(H);return true;
 }
 void Pump(int32 Epoch,bool On,bool Accept,double ConfirmedAt,double Delay){
  // The task: read what is there, queue the newest complete JPEG of each read, then play out (decode) at most ONE: the newest frame that was
  // read at least Delay s ago AND before the start of the newest completed public confirmation of the connected desktop (so a frame read
  // after the runner locked cannot be shown while the lock lasts, even before the game notices it).
  if(!On){Close();return;} // monitor_feed 0: the descriptor goes, so the sidecar stops ffmpeg
  if(Fd<0&&!OpenFifo(FPlatformTime::Seconds()))return;
  if(Epoch!=BufferEpoch){DroppedEpoch+=int64(Ring.size());Buffer.clear();ClearRing();BufferEpoch=Epoch;} // nothing read in an earlier epoch survives
  if(Chunk.size()!=size_t(@@CHUNK@@))Chunk.resize(size_t(@@CHUNK@@));
  int64 Got=0;
  while(Got<@@PUMP_BYTES@@){
   ssize_t N;do N=::read(Fd,Chunk.data(),Chunk.size());while(N<0&&errno==EINTR);
   if(N<0){if(errno!=EAGAIN&&errno!=EWOULDBLOCK){OpenErrno.store(errno);Close();return;}break;} // EAGAIN: drained; any other error: closed, reopened later
   if(N==0)break; // no writer at the moment (the sidecar restarts ffmpeg): the descriptor stays open
   Got+=N;Bytes+=N;
   if(!Accept){Discarded+=N;Buffer.clear();DroppedEpoch+=int64(Ring.size());ClearRing();continue;} // gate closed or just reopened: never shown
   Buffer.insert(Buffer.end(),Chunk.data(),Chunk.data()+N);
   const FSub01JpegScan Scan=Sub01ScanJpegs(Buffer.data(),int64(Buffer.size()),@@MAX_FRAME@@);
   Frames+=Scan.Frames;Resyncs+=Scan.Resyncs;
   if(Scan.Frames>0){DroppedOlder+=Scan.Frames-1;FSub01MonitorQueued Item;Item.Bytes.assign(Buffer.begin()+ptrdiff_t(Scan.Start),Buffer.begin()+ptrdiff_t(Scan.End));
    Item.ReadAt=FPlatformTime::Seconds();RingBytes+=int64(Item.Bytes.size());Ring.push_back(MoveTemp(Item));
    while(int64(Ring.size())>@@RING_FRAMES@@||RingBytes>@@RING_BYTES@@){RingBytes-=int64(Ring.front().Bytes.size());Ring.pop_front();++DroppedOverflow;}}
   if(Scan.Consumed>0)Buffer.erase(Buffer.begin(),Buffer.begin()+ptrdiff_t(Scan.Consumed));
  }
  Queued.store(int32(Ring.size()));QueuedBytes.store(RingBytes);
  if(!Accept||Ring.empty())return;
  const double Now=FPlatformTime::Seconds();int64 Pick=-1;
  for(int64 I=int64(Ring.size())-1;I>=0&&Pick<0;--I){const double At=Ring[size_t(I)].ReadAt;if(At<=Now-Delay&&At<ConfirmedAt)Pick=I;}
  if(Pick<0)return;
  for(int64 I=0;I<Pick;++I){RingBytes-=int64(Ring.front().Bytes.size());Ring.pop_front();++DroppedOlder;} // older than an eligible newer one
  FSub01MonitorQueued Chosen=MoveTemp(Ring.front());Ring.pop_front();RingBytes-=int64(Chosen.Bytes.size());Queued.store(int32(Ring.size()));QueuedBytes.store(RingBytes);
  const double T0=FPlatformTime::Seconds();FSub01MonitorFrame* Frame=new FSub01MonitorFrame();
  if(!Decode(Chosen.Bytes.data(),int64(Chosen.Bytes.size()),*Frame)){delete Frame;++DecodeFailed;return;}
  const int64 Us=int64((FPlatformTime::Seconds()-T0)*1e6);++Decoded;DecodeUs+=Us;if(Us>DecodeMaxUs.load())DecodeMaxUs.store(Us);
  Frame->Epoch=Epoch;Frame->ReadAt=Chosen.ReadAt;
  if(FSub01MonitorFrame* Old=Ready.exchange(Frame)){delete Old;++DroppedUntaken;} // the game thread had not taken the previous one: replaced
 }
};
void ASub01HomeCharacter::StartStreamerVisualMonitorFeed(){
 // Once per process at v2 start (next to cam2's FIFO); the reader opens the sidecar's FIFO itself (never creates or replaces it).
 if(StreamerVisualMonitorFeed)return;
 StreamerVisualMonitorFeed=MakeShared<FSub01MonitorFeed>();FSub01MonitorFeed& Feed=*StreamerVisualMonitorFeed;
 Feed.FifoPath=StreamerVisualCam2Dir+TEXT("/@@FIFO@@");Feed.Images=&FModuleManager::LoadModuleChecked<IImageWrapperModule>(FName(TEXT("ImageWrapper")));
 const double Now=FPlatformTime::Seconds();StreamerVisualMonitorFeedLogAt=Now+@@LOG@@;StreamerVisualMonitorFeedWindowAt=Now;StreamerVisualMonitorFeedNextAt=0;
 UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_MONITOR_FEED started fifo=%s on=%d targetFps=%.0f delayS=%.2f staleS=%.2f confirmS=@@CONFIRM@@ guardS=@@GUARD@@ (shown only while the PC bridge's privacy gate is open, after the playout delay; else the bridge's own picture)"),
  *Feed.FifoPath,StreamerVisualMonitorFeedOn>0?1:0,StreamerVisualMonitorFps,StreamerVisualMonitorDelaySeconds,StreamerVisualMonitorStaleSeconds);
}
bool ASub01HomeCharacter::UploadStreamerVisualMonitorFrame(TArray64<uint8>& Pixels,int32 Width,int32 Height){
 // The bridge's own layout (Sub01GuestFrameLayout with its screen aspect: centred, black borders), so the picture never jumps between the two.
 FSub01GuestFrameLayout Layout;if(!PCBridge||!Sub01GuestFrameLayout(Width,Height,PCBridge->GetMonitorScreenAspect(),Layout))return false;
 const int32 CreatedBefore=StreamerVisualMonitorTexturesCreated;
 UTexture2D* Texture=Sub01PersistentTexture::Ensure(StreamerVisualMonitorTexture,Layout.Width,Layout.Height,&StreamerVisualMonitorTexturesCreated);if(!Texture)return false;
 const int32 Rect[4]={Layout.X,Layout.Y,Width,Height};bool SameRect=true;for(int32 K=0;K<4;++K)SameRect=SameRect&&Rect[K]==StreamerVisualMonitorRect[K];
 if(!SameRect&&CreatedBefore==StreamerVisualMonitorTexturesCreated&&!Sub01PersistentTexture::Clear(Texture))return false; // a new source rect in the same texture: black first
 for(int32 K=0;K<4;++K)StreamerVisualMonitorRect[K]=Rect[K];
 return Sub01PersistentTexture::Update(Texture,Layout.X,Layout.Y,Width,Height,MoveTemp(Pixels));
}
FString ASub01HomeCharacter::StreamerVisualMonitorFeedReason()const{
 if(!StreamerVisualMonitorFeed)return TEXT("not started");const FSub01MonitorFeed& Feed=*StreamerVisualMonitorFeed;
 if(StreamerVisualMonitorFeedOn<=0)return TEXT("off (monitor_feed 0)");
 if(Feed.Refused.load())return TEXT("refused: the path is not this user's private FIFO");
 if(!Feed.Open.load())return Feed.OpenErrno.load()==ENOENT?TEXT("no FIFO yet (sidecar not running)"):TEXT("FIFO not open");
 if(!StreamerVisualMonitorFeedGate)return TEXT("gate closed: ")+StreamerVisualMonitorFeedGateReason;
 if(!StreamerVisualMonitorFeedBound)return TEXT("no progress (quarantine, playout or a dead feed): the bridge's own picture");
 return TEXT("-");
}
void ASub01HomeCharacter::UpdateStreamerVisualMonitorFeed(double Now,float Dt){
 if(!StreamerVisualMonitorFeed)return;FSub01MonitorFeed& Feed=*StreamerVisualMonitorFeed;
 // 1. the PC bridge's gate, every tick: a change of it (or of the bridge's privacy generation) starts a new epoch (logged at once, at most once per
 //    @@GATE_LOG@@ s); after a reopen the first @@GUARD@@ s of FIFO data are discarded (the pipe and ffmpeg still hold frames captured while it was closed)
 const bool On=StreamerVisualMonitorFeedOn>0;const bool Gate=On&&PCBridge&&PCBridge->IsMonitorFeedAllowed(Now);
 const uint64 PrivacyGeneration=PCBridge?PCBridge->GetMonitorPrivacyGeneration():0;const double ConfirmedAt=PCBridge?PCBridge->GetMonitorConfirmedAt():-1.;
 const bool Changed=Gate!=StreamerVisualMonitorFeedGate||PrivacyGeneration!=StreamerVisualMonitorFeedGeneration;
 if(Changed){++StreamerVisualMonitorFeedEpoch;StreamerVisualMonitorFeedGate=Gate;StreamerVisualMonitorFeedGeneration=PrivacyGeneration;StreamerVisualMonitorFeedGateAt=Now;}
 if(Changed||(!Gate&&Now>=StreamerVisualMonitorFeedReasonAt)){StreamerVisualMonitorFeedReasonAt=Now+.5; // while closed the reason is refreshed (and logged when it changes)
  const FString Why=!On?FString(TEXT("monitor_feed 0")):PCBridge?PCBridge->MonitorFeedGateReason(Now):FString(TEXT("no PC bridge"));
  if(Changed||Why!=StreamerVisualMonitorFeedGateReason){StreamerVisualMonitorFeedGateReason=Why;
   if(Now>=StreamerVisualMonitorFeedGateLogAt){StreamerVisualMonitorFeedGateLogAt=Now+@@GATE_LOG@@;
    UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_MONITOR_FEED_GATE open=%d epoch=%d reason=%s suppressed=%d"),Gate?1:0,StreamerVisualMonitorFeedEpoch,*StreamerVisualMonitorFeedGateReason,StreamerVisualMonitorFeedGateLogSuppressed);
    StreamerVisualMonitorFeedGateLogSuppressed=0;}
   else ++StreamerVisualMonitorFeedGateLogSuppressed;}}
 const bool Accept=Gate&&Now>=StreamerVisualMonitorFeedGateAt+@@GUARD@@;
 // 2. the decoded frame: uploaded into the persistent texture only in the epoch it was read in, read after the quarantine and before the newest
 //    public confirmation, while accepted, and while the RHI has fewer than @@MAX_PENDING@@ uploads still to copy
 if(FSub01MonitorFrame* Taken=Feed.Ready.exchange(nullptr)){
  if(!Accept||Taken->Epoch!=StreamerVisualMonitorFeedEpoch||Taken->ReadAt<StreamerVisualMonitorFeedGateAt+@@GUARD@@||Taken->ReadAt>=ConfirmedAt)++StreamerVisualMonitorFeedRejected;
  else if(Sub01PersistentTexture::PendingUploads().load()>=@@MAX_PENDING@@)++StreamerVisualMonitorFeedUploadBusy;
  else if(UploadStreamerVisualMonitorFrame(Taken->Pixels,Taken->Width,Taken->Height)){StreamerVisualMonitorFeedShownEpoch=StreamerVisualMonitorFeedEpoch;
   StreamerVisualMonitorFeedShownReadAt=Taken->ReadAt;StreamerVisualMonitorFeedUploadAt=Now;++StreamerVisualMonitorFeedShown;StreamerVisualMonitorFeedUploadBytes+=int64(Taken->Width)*Taken->Height*4;}
  else ++StreamerVisualMonitorFeedRejected;
  delete Taken;}
 // 3. progress (a new upload of this epoch < monitor_stale_s ago) = the feed stands in for the bridge's picture; none (a dead feed) = the bridge's
 //    own picture again and the texture blanked, so it never keeps an old screen
 const bool Fresh=Accept&&StreamerVisualMonitorTexture&&StreamerVisualMonitorFeedShownEpoch==StreamerVisualMonitorFeedEpoch&&Now-StreamerVisualMonitorFeedUploadAt<=double(StreamerVisualMonitorStaleSeconds);
 const bool Bound=PCBridge&&PCBridge->SetMonitorFeedFrame(Fresh?StreamerVisualMonitorTexture.Get():nullptr);
 if(Bound!=StreamerVisualMonitorFeedBound){StreamerVisualMonitorFeedBound=Bound; // first, so the log's reason describes the new state
  if(!Bound){++StreamerVisualMonitorFeedStale;StreamerVisualMonitorFeedShownEpoch=-1;if(StreamerVisualMonitorTexture)Sub01PersistentTexture::Clear(StreamerVisualMonitorTexture);}
  UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_MONITOR_FEED_%s uploadAgoMs=%.0f contentAgeMs=%.0f gate=%d epoch=%d reason=%s"),Bound?TEXT("BOUND"):TEXT("FALLBACK"),
   StreamerVisualMonitorFeedUploadAt>=0?(Now-StreamerVisualMonitorFeedUploadAt)*1000.:-1.,StreamerVisualMonitorFeedShownReadAt>=0?(Now-StreamerVisualMonitorFeedShownReadAt)*1000.:-1.,Gate?1:0,StreamerVisualMonitorFeedEpoch,
   Bound?TEXT("-"):*StreamerVisualMonitorFeedReason());}
 StreamerVisualMonitorFeedBound=Bound;
 // 4. the next pump when due (monitor_fps), never two at once; with the feed off one more pump closes the descriptor
 if((On||Feed.Open.load())&&Now+.5*Dt>=StreamerVisualMonitorFeedNextAt&&Feed.Busy.load()==0){
  const double Period=1./FMath::Clamp(double(StreamerVisualMonitorFps),1.,60.);StreamerVisualMonitorFeedNextAt+=Period;if(StreamerVisualMonitorFeedNextAt<Now)StreamerVisualMonitorFeedNextAt=Now+Period;
  Feed.Busy.store(1);const double Delay=FMath::Clamp(double(StreamerVisualMonitorDelaySeconds),.5,3.);
  AsyncTask(ENamedThreads::AnyBackgroundThreadNormalTask,[Self=StreamerVisualMonitorFeed,Epoch=StreamerVisualMonitorFeedEpoch,On,Accept,ConfirmedAt,Delay](){Self->Pump(Epoch,On,Accept,ConfirmedAt,Delay);Self->Busy.store(0);});
 }
 if(Now>=StreamerVisualMonitorFeedLogAt)LogStreamerVisualMonitorFeed(Now);
}
void ASub01HomeCharacter::LogStreamerVisualMonitorFeed(double Now){
 FSub01MonitorFeed& Feed=*StreamerVisualMonitorFeed;const double Span=FMath::Max(1e-3,Now-StreamerVisualMonitorFeedWindowAt);
 const int64 Totals[5]={StreamerVisualMonitorFeedShown,Feed.Frames.load(),Feed.Decoded.load(),Feed.DecodeUs.load(),StreamerVisualMonitorFeedUploadBytes};int64 D[5];for(int32 K=0;K<5;++K)D[K]=Totals[K]-StreamerVisualMonitorFeedWindowBase[K];
 StreamerVisualMonitorFeedFpsShown=float(double(D[0])/Span);StreamerVisualMonitorFeedFpsIn=float(double(D[1])/Span);
 const int64 Older=Feed.DroppedOlder.load(),Epoch=Feed.DroppedEpoch.load(),Overflow=Feed.DroppedOverflow.load(),Untaken=Feed.DroppedUntaken.load(),Failed=Feed.DecodeFailed.load();
 const double ConfirmedAt=PCBridge?PCBridge->GetMonitorConfirmedAt():-1.;
 UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_MONITOR_FEED fps=%.1f decoded=%d dropped=%d stale=%d in_fps=%.1f shown=%d bound=%d allowed=%d open=%d epoch=%d confirm_age_ms=%.0f content_age_ms=%.0f queued=%d queued_kb=%.0f pending=%d dropped_older=%d dropped_epoch=%d dropped_overflow=%d dropped_untaken=%d rejected=%d upload_busy=%d decode_failed=%d resyncs=%d discarded_kb=%.0f decode_ms=%.2f decode_max_ms=%.2f upload_mib_s=%.1f textures=%d bridge_textures=%d target_fps=%.0f delay_s=%.2f stale_s=%.2f reason=%s window_s=%.0f"),
  StreamerVisualMonitorFeedFpsShown,int32(Totals[2]),int32(Older+Epoch+Overflow+Untaken+Failed+StreamerVisualMonitorFeedRejected+StreamerVisualMonitorFeedUploadBusy),int32(StreamerVisualMonitorFeedStale),StreamerVisualMonitorFeedFpsIn,int32(Totals[0]),
  StreamerVisualMonitorFeedBound?1:0,StreamerVisualMonitorFeedGate?1:0,Feed.Open.load()?1:0,StreamerVisualMonitorFeedEpoch,ConfirmedAt>=0?(Now-ConfirmedAt)*1000.:-1.,StreamerVisualMonitorFeedShownReadAt>=0?(Now-StreamerVisualMonitorFeedShownReadAt)*1000.:-1.,
  Feed.Queued.load(),double(Feed.QueuedBytes.load())/1024.,Sub01PersistentTexture::PendingUploads().load(),int32(Older),int32(Epoch),int32(Overflow),int32(Untaken),int32(StreamerVisualMonitorFeedRejected),int32(StreamerVisualMonitorFeedUploadBusy),int32(Failed),
  int32(Feed.Resyncs.load()),double(Feed.Discarded.load())/1024.,D[2]>0?double(D[3])/1000./double(D[2]):0.,double(Feed.DecodeMaxUs.exchange(0))/1000.,double(D[4])/1048576./Span,
  StreamerVisualMonitorTexturesCreated,PCBridge?PCBridge->GetMonitorTexturesCreated():0,StreamerVisualMonitorFps,StreamerVisualMonitorDelaySeconds,StreamerVisualMonitorStaleSeconds,*StreamerVisualMonitorFeedReason(),Span);
 for(int32 K=0;K<5;++K)StreamerVisualMonitorFeedWindowBase[K]=Totals[K];StreamerVisualMonitorFeedWindowAt=Now;StreamerVisualMonitorFeedLogAt=Now+@@LOG@@;
}
// ---- camera 2's exposure (it copied the webcam's post process at start); only the exposure fields, applied on change
void ASub01HomeCharacter::ApplyStreamerVisualCam2Exposure(){
 if(!StreamerVisualCam2)return;
 const float Want[4]={StreamerVisualCam2Exposure,StreamerVisualCam2EvBias,StreamerVisualCam2EvMin,StreamerVisualCam2EvMax};bool Same=true;
 for(int32 K=0;K<4;++K)Same=Same&&Want[K]==StreamerVisualCam2ExposureState[K];if(Same)return;for(int32 K=0;K<4;++K)StreamerVisualCam2ExposureState[K]=Want[K];
 FPostProcessSettings& Settings=StreamerVisualCam2->PostProcessSettings;
 if(!StreamerVisualCam2BaseSaved){StreamerVisualCam2BaseSaved=true; // what cam2 copied from the webcam: mode 0 restores exactly this
  StreamerVisualCam2BaseBiasSet=Settings.bOverride_AutoExposureBias;StreamerVisualCam2BaseBias=Settings.AutoExposureBias;StreamerVisualCam2BaseMethodSet=Settings.bOverride_AutoExposureMethod;StreamerVisualCam2BaseMethod=uint8(Settings.AutoExposureMethod.GetValue());
  StreamerVisualCam2BaseMinSet=Settings.bOverride_AutoExposureMinBrightness;StreamerVisualCam2BaseMin=Settings.AutoExposureMinBrightness;StreamerVisualCam2BaseMaxSet=Settings.bOverride_AutoExposureMaxBrightness;StreamerVisualCam2BaseMax=Settings.AutoExposureMaxBrightness;
  StreamerVisualCam2BasePhysicalSet=Settings.bOverride_AutoExposureApplyPhysicalCameraExposure;StreamerVisualCam2BasePhysical=Settings.AutoExposureApplyPhysicalCameraExposure;StreamerVisualCam2BaseWeight=StreamerVisualCam2->PostProcessBlendWeight;}
 Settings.bOverride_AutoExposureBias=StreamerVisualCam2BaseBiasSet;Settings.AutoExposureBias=StreamerVisualCam2BaseBias;Settings.bOverride_AutoExposureMethod=StreamerVisualCam2BaseMethodSet;Settings.AutoExposureMethod=EAutoExposureMethod(StreamerVisualCam2BaseMethod);
 Settings.bOverride_AutoExposureMinBrightness=StreamerVisualCam2BaseMinSet;Settings.AutoExposureMinBrightness=StreamerVisualCam2BaseMin;Settings.bOverride_AutoExposureMaxBrightness=StreamerVisualCam2BaseMaxSet;Settings.AutoExposureMaxBrightness=StreamerVisualCam2BaseMax;
 Settings.bOverride_AutoExposureApplyPhysicalCameraExposure=StreamerVisualCam2BasePhysicalSet;Settings.AutoExposureApplyPhysicalCameraExposure=StreamerVisualCam2BasePhysical;StreamerVisualCam2->PostProcessBlendWeight=StreamerVisualCam2BaseWeight;
 const int32 Mode=FMath::Clamp(int32(StreamerVisualCam2Exposure+.5f),0,2);const bool Range=Mode==1&&StreamerVisualCam2EvMin<=StreamerVisualCam2EvMax;
 if(Mode>=1){Settings.bOverride_AutoExposureBias=true;Settings.AutoExposureBias=StreamerVisualCam2EvBias;StreamerVisualCam2->PostProcessBlendWeight=1.f;} // weight 1: the override is not diluted
 if(Mode==1){Settings.bOverride_AutoExposureMethod=true;Settings.AutoExposureMethod=AEM_Histogram;} // really automatic (the house volume's method), even if a copied setting were manual
 if(Range){Settings.bOverride_AutoExposureMinBrightness=true;Settings.AutoExposureMinBrightness=StreamerVisualCam2EvMin;Settings.bOverride_AutoExposureMaxBrightness=true;Settings.AutoExposureMaxBrightness=StreamerVisualCam2EvMax;}
 if(Mode==2){Settings.bOverride_AutoExposureMethod=true;Settings.AutoExposureMethod=AEM_Manual;Settings.bOverride_AutoExposureApplyPhysicalCameraExposure=true;Settings.AutoExposureApplyPhysicalCameraExposure=false;}
 UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_CAM2_EXPOSURE mode=%d bias=%.2f range=%d min=%.2f max=%.2f weight=%.2f copied: biasSet=%d bias=%.2f methodSet=%d method=%d minSet=%d maxSet=%d weight=%.2f (0 copied, 1 auto+bias, 2 manual)"),
  Mode,Mode>=1?StreamerVisualCam2EvBias:StreamerVisualCam2BaseBias,Range?1:0,StreamerVisualCam2EvMin,StreamerVisualCam2EvMax,StreamerVisualCam2->PostProcessBlendWeight,StreamerVisualCam2BaseBiasSet?1:0,StreamerVisualCam2BaseBias,
  StreamerVisualCam2BaseMethodSet?1:0,int32(StreamerVisualCam2BaseMethod),StreamerVisualCam2BaseMinSet?1:0,StreamerVisualCam2BaseMaxSet?1:0,StreamerVisualCam2BaseWeight);
}
// SUB01_STREAMER_VISUAL_V2_V22 END
''', **COMMON)

START_ANCHOR = ' StartStreamerVisualCam2(); // SUB01_STREAMER_VISUAL_V2_CAM2: the second camera, created once (streamer mode only)\n'
START_V22 = START_ANCHOR + ' StartStreamerVisualMonitorFeed(); // SUB01_STREAMER_VISUAL_V2_V22: the in-game monitor feed reader, created once\n'
TICK_ANCHOR = '  UpdateStreamerVisualCam2(Now,Dt); // SUB01_STREAMER_VISUAL_V2_CAM2: timer capture, readback pump, status, log\n'
TICK_V22 = TICK_ANCHOR + '  UpdateStreamerVisualMonitorFeed(Now,Dt); // SUB01_STREAMER_VISUAL_V2_V22: the monitor feed (gate, upload, bind, pump, log)\n'
CAM2_GATE = v21.CAM2_GATE_V21
assert CAM2_GATE.startswith(' ApplyStreamerVisualCam2Lite(); // SUB01_STREAMER_VISUAL_V2_V21\n')
CAM2_GATE_V22 = ' ApplyStreamerVisualCam2Exposure(); // SUB01_STREAMER_VISUAL_V2_V22: cam2_exposure / cam2_ev_* on change\n' + CAM2_GATE
TUNING_V21 = v21.TUNING_LINE_V21[len(v21.TUNING_LINE):]
assert TUNING_V21.startswith(' Field(TEXT("perf_window_s")') and TUNING_V21.endswith(' // SUB01_STREAMER_VISUAL_V2_V21\n')
TUNING_V22 = TUNING_V21 + (' ' + ''.join(f'Field(TEXT("{k}"),{TUNING_FIELDS[k]},{lo},{hi});' for k, (lo, hi) in TUNING_LIMITS.items())
                           + ' // SUB01_STREAMER_VISUAL_V2_V22: the monitor feed and cam2 exposure keys (this line only)\n')
RECEIPT_ANCHOR = 'Receipt->SetBoolField(TEXT("cam2_lite"),StreamerVisualCam2Lite>0);\n'
RECEIPT_V22 = RECEIPT_ANCHOR + (
    '   if(StreamerVisualMonitorFeed){const FSub01MonitorFeed& MonitorFeed=*StreamerVisualMonitorFeed; // SUB01_STREAMER_VISUAL_V2_V22\n'
    '    Receipt->SetBoolField(TEXT("monitor_feed_on"),StreamerVisualMonitorFeedOn>0);Receipt->SetBoolField(TEXT("monitor_feed_bound"),StreamerVisualMonitorFeedBound);Receipt->SetBoolField(TEXT("monitor_feed_allowed"),StreamerVisualMonitorFeedGate);'
    'Receipt->SetBoolField(TEXT("monitor_feed_open"),MonitorFeed.Open.load());Receipt->SetNumberField(TEXT("monitor_feed_fps"),StreamerVisualMonitorFeedFpsShown);Receipt->SetNumberField(TEXT("monitor_feed_in_fps"),StreamerVisualMonitorFeedFpsIn);'
    'Receipt->SetNumberField(TEXT("monitor_feed_target_fps"),StreamerVisualMonitorFps);Receipt->SetNumberField(TEXT("monitor_feed_delay_s"),StreamerVisualMonitorDelaySeconds);Receipt->SetNumberField(TEXT("monitor_feed_stale_s"),StreamerVisualMonitorStaleSeconds);\n'
    '    Receipt->SetNumberField(TEXT("monitor_feed_shown"),double(StreamerVisualMonitorFeedShown));Receipt->SetNumberField(TEXT("monitor_feed_decoded"),double(MonitorFeed.Decoded.load()));'
    'Receipt->SetNumberField(TEXT("monitor_feed_dropped"),double(MonitorFeed.DroppedOlder.load()+MonitorFeed.DroppedEpoch.load()+MonitorFeed.DroppedOverflow.load()+MonitorFeed.DroppedUntaken.load()+MonitorFeed.DecodeFailed.load()+StreamerVisualMonitorFeedRejected+StreamerVisualMonitorFeedUploadBusy));'
    'Receipt->SetNumberField(TEXT("monitor_feed_upload_busy"),double(StreamerVisualMonitorFeedUploadBusy));Receipt->SetNumberField(TEXT("monitor_feed_stale"),double(StreamerVisualMonitorFeedStale));Receipt->SetNumberField(TEXT("monitor_feed_resyncs"),double(MonitorFeed.Resyncs.load()));\n'
    '    Receipt->SetNumberField(TEXT("monitor_feed_epoch"),StreamerVisualMonitorFeedEpoch);Receipt->SetNumberField(TEXT("monitor_feed_queued"),MonitorFeed.Queued.load());Receipt->SetStringField(TEXT("monitor_feed_gate_reason"),StreamerVisualMonitorFeedGateReason);'
    'Receipt->SetNumberField(TEXT("monitor_feed_age_ms"),StreamerVisualMonitorFeedShownReadAt>=0?(FPlatformTime::Seconds()-StreamerVisualMonitorFeedShownReadAt)*1000.:-1.);Receipt->SetNumberField(TEXT("monitor_feed_textures"),StreamerVisualMonitorTexturesCreated);'
    'Receipt->SetNumberField(TEXT("pc_bridge_textures"),PCBridge?PCBridge->GetMonitorTexturesCreated():0);Receipt->SetStringField(TEXT("monitor_feed_reason"),StreamerVisualMonitorFeedReason());}\n'
    '   Receipt->SetNumberField(TEXT("cam2_exposure"),StreamerVisualCam2Exposure);Receipt->SetNumberField(TEXT("cam2_ev_bias"),StreamerVisualCam2EvBias);Receipt->SetNumberField(TEXT("cam2_ev_min"),StreamerVisualCam2EvMin);'
    'Receipt->SetNumberField(TEXT("cam2_ev_max"),StreamerVisualCam2EvMax); // SUB01_STREAMER_VISUAL_V2_V22\n')

EDITS = [
    ('header', HEADER_V21_END, HEADER_V21_END + HEADER_FIELDS),
    ('cpp', INCLUDE_ANCHOR, INCLUDE_V22),
    ('cpp', FACE_BEGIN, CPP_METHODS + FACE_BEGIN),
    ('cpp', START_ANCHOR, START_V22),
    ('cpp', TICK_ANCHOR, TICK_V22),
    ('cpp', CAM2_GATE, CAM2_GATE_V22),
    ('cpp', TUNING_V21, TUNING_V22),
    ('cpp', RECEIPT_ANCHOR, RECEIPT_V22),
    ('pc_header', PC_FORWARD, PC_FORWARD_V22),
    ('pc_header', PC_PUBLIC_ANCHOR, PC_PUBLIC),
    ('pc_header', PC_PRIVATE_ANCHOR, PC_PRIVATE),
    ('pc_cpp', PC_INCLUDE, PC_INCLUDE_V22),
    ('pc_cpp', PC_CLEAR, PC_CLEAR_V22),
    ('pc_cpp', PC_ENDPLAY, PC_ENDPLAY_V22),
    ('pc_cpp', PC_POLL_TOP, PC_POLL_TOP_V22),
    ('pc_cpp', PC_POLL, PC_POLL_V22),
    ('pc_cpp', PC_APPLY, PC_APPLY_V22),
    ('pc_cpp', PC_TEXTURE, PC_TEXTURE_V22),
    ('dev_header', DEV_FIELD, DEV_FIELD_V22),
    ('dev_cpp', DEV_INCLUDE, DEV_INCLUDE_V22),
    ('dev_cpp', DEV_TEXTURE, DEV_TEXTURE_V22),
]
# applied after EDITS: every remaining "PCFrame" binding of the PC bridge goes through ShowFrame (exactly PC_BIND_SITES of them), then the methods
PC_TAIL_EDIT = ('pc_cpp', PC_TAIL, PC_METHODS)


# The one "PCFrame" use the pod's native_cinematic_pc.inc may keep: a read-back that checks the bridge's own verified frame is
# on screen before it records a website observation (still correct under ShowFrame: with the feed on screen it skips).
INC_READBACK = re.compile(r'GetTextureParameterValue\(\s*FName\(\s*TEXT\(\s*"PCFrame"\s*\)\s*\)\s*,')


def inc_binds_pc_frame(inc: str) -> bool:
    """Fail closed: any "PCFrame" left after removing the allowlisted read-back counts as a binding (a setter may name it
    through a variable in another statement)."""
    return 'PCFrame' in INC_READBACK.sub('', inc)


def describe_inc(inc: str | None) -> str:
    if inc is None:
        return 'absent'
    return 'present, reads PCFrame only' if INC_READBACK.search(inc) else 'present, no PCFrame binding'


def plan(sources: dict, inc: str | None = None) -> dict:
    """Pure transformation of the six LF texts (`inc` = native_cinematic_pc.inc when present); raises Refused, never partial."""
    problems = [f'{FILES[key]} already carries {MARKER} (v22 already installed)' for key in FILES if MARKER in sources[key]]
    if problems:
        raise Refused('; '.join(problems))
    problems = [f'{FILES[key]} lacks v21 ({v21.MARKER}); run the stack up to install_v21_fixes.py first'
                for key in ('header', 'cpp') if v21.MARKER + ' BEGIN' not in sources[key]]
    if inc is not None and inc_binds_pc_frame(inc):
        problems.append(f'{CINEMATIC_PC_INC} binds "PCFrame" itself: it would bypass ShowFrame (the feed routing); route it first')
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
    count = out['pc_cpp'].count(PC_BIND)
    edits.append({'file': FILES['pc_cpp'], 'anchor': PC_BIND, 'anchor_sha256': v2.sha256(PC_BIND), 'count': count})
    if count != PC_BIND_SITES:
        problems.append(f'{FILES["pc_cpp"]}: expected {PC_BIND_SITES} "PCFrame" bindings to route through ShowFrame, found {count}')
    else:
        out['pc_cpp'] = out['pc_cpp'].replace(PC_BIND, 'ShowFrame(')
    key, anchor, replacement = PC_TAIL_EDIT
    count = out[key].count(anchor)
    edits.append({'file': FILES[key], 'anchor': anchor.strip()[:96], 'anchor_sha256': v2.sha256(anchor), 'count': count})
    if count != 1:
        problems.append(f'anchor {"missing" if count == 0 else f"found {count}x"} in {FILES[key]}: {anchor.strip()[:96]!r}')
    else:
        out[key] = out[key].replace(anchor, replacement, 1)
    if problems:
        raise Refused('; '.join(problems))
    for key in FILES:
        if v2.balance(sources[key]) != v2.balance(out[key]):
            raise Refused(f'{FILES[key]}: bracket balance changed by the install')
        if MARKER not in out[key]:
            raise Refused(f'{FILES[key]}: marker missing after install')
    v22_block = out['pc_cpp'][out['pc_cpp'].index(MARKER + ' BEGIN'):out['pc_cpp'].index(MARKER + ' END')]
    if out['pc_cpp'].count(PC_BIND) != v22_block.count(PC_BIND):
        raise Refused(f'{FILES["pc_cpp"]}: a "PCFrame" binding outside ShowFrame/SetMonitorFeedFrame remains')
    return {'sources': out, 'edits': edits}


def _write_all(existing: dict, new: dict, mode_from: Path) -> None:
    """Like v2.write_atomically, plus files that do not exist yet (mode of `mode_from`): every file staged first, then all renamed."""
    staged = []
    try:
        for path, text in {**existing, **new}.items():
            fd, tmp = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.v2tmp', dir=path.parent)
            with os.fdopen(fd, 'w', encoding='utf-8', newline='') as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp, (path if path in existing else mode_from).stat().st_mode & 0o7777)
            staged.append((tmp, path))
        for tmp, path in staged:
            os.replace(tmp, path)
        staged = []
    finally:
        for tmp, _ in staged:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def run(source: Path, dry_run: bool) -> dict:
    source = Path(source).resolve()
    missing = [n for n in FILES.values() if not (source / n).is_file()]
    if missing:
        raise Refused(f'missing in {source}: {", ".join(missing)}')
    raw = {key: v2.read_raw(source / name) for key, name in FILES.items()}
    eol = {key: v2.line_ending(FILES[key], raw[key]) for key in FILES}
    inc_path = source / CINEMATIC_PC_INC
    inc = v2.read_raw(inc_path) if inc_path.is_file() else None
    result = plan({key: text.replace('\r\n', '\n') for key, text in raw.items()}, inc)
    after = {key: result['sources'][key].replace('\n', eol[key]) for key in FILES}
    header_text = PERSISTENT_HEADER.replace('\n', eol['pc_header'])
    header_path = source / NEW_HEADER
    if header_path.exists() and v2.read_raw(header_path) != header_text:
        raise Refused(f'{NEW_HEADER} already exists with other content (left untouched)')
    report = {'schema': 'sub01.native-streamer-visual-v2-v22-install.v1', 'source': str(source), 'dry_run': dry_run, 'marker': MARKER,
              'requires': [v21.MARKER, posefix.MARKER, cam2.MARKER, streampass.MARKER, seatfix.MARKER, v2.MARKER],
              'monitor_feed': {'fifo': f'{cam2.STREAM_DIR}/{FIFO_NAME}', 'on': MONITOR_FEED, 'fps': MONITOR_FPS, 'delay_s': PLAYOUT_SECONDS,
                               'stale_s': STALE_SECONDS, 'confirm_s': CONFIRM_SECONDS, 'renew_s': RENEW_SECONDS, 'guard_s': GUARD_SECONDS,
                               'reopen_s': REOPEN_SECONDS, 'chunk_bytes': CHUNK_BYTES, 'pump_bytes': PUMP_BYTES, 'max_frame_bytes': MAX_FRAME_BYTES,
                               'ring': [RING_FRAMES, RING_BYTES], 'max_pending_uploads': MAX_PENDING_UPLOADS, 'max_size': [MAX_W, MAX_H],
                               'log_seconds': LOG_SECONDS, 'gate_log_seconds': GATE_LOG_SECONDS,
                               'path': 'one background task: non-blocking FIFO read -> JPEG marker walk (resync on SOI) -> newest frame of each read queued -> '
                                       'playout: the newest frame read >= delay_s ago and before the newest public confirmation, one decode -> game thread: '
                                       'one persistent texture, UpdateTextureRegions -> PC bridge SetMonitorFeedFrame (gated)'},
              'cam2_exposure': {'mode': CAM2_EXPOSURE, 'ev_bias': CAM2_EV_BIAS, 'ev_min': CAM2_EV_MIN, 'ev_max': CAM2_EV_MAX},
              'pc_bridge_bind_sites': PC_BIND_SITES, 'new_header': NEW_HEADER,
              'layout_header_present': (source / LAYOUT_HEADER).is_file(),
              'cinematic_pc_inc': describe_inc(inc),
              'tuning_limits': TUNING_LIMITS, 'edits': result['edits'],
              'files': {FILES[key]: {'before_sha256': v2.sha256(raw[key]), 'after_sha256': v2.sha256(after[key]),
                                     'bytes_before': len(raw[key].encode()), 'bytes_after': len(after[key].encode()),
                                     'line_ending': 'CRLF' if eol[key] == '\r\n' else 'LF',
                                     'edits': sum(1 for k, _, _ in EDITS if k == key) + (2 if key == 'pc_cpp' else 0)} for key in FILES}}
    report['files'][NEW_HEADER] = {'before_sha256': None, 'after_sha256': v2.sha256(header_text), 'bytes_after': len(header_text.encode()),
                                   'line_ending': 'CRLF' if eol['pc_header'] == '\r\n' else 'LF', 'created': True}
    if not dry_run:
        _write_all({source / FILES[key]: after[key] for key in FILES}, {} if header_path.exists() else {header_path: header_text},
                   source / FILES['pc_header'])
        for key in FILES:
            if v2.sha256(v2.read_raw(source / FILES[key])) != report['files'][FILES[key]]['after_sha256']:
                raise Refused(f'{FILES[key]}: written bytes differ from the plan')
        if v2.sha256(v2.read_raw(header_path)) != report['files'][NEW_HEADER]['after_sha256']:
            raise Refused(f'{NEW_HEADER}: written bytes differ from the plan')
    report['status'] = 'planned' if dry_run else 'applied'
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True, help='directory with the v21 pod files (patched in place)')
    parser.add_argument('--dry-run', action='store_true', help='check every anchor and print the report; write nothing')
    args = parser.parse_args(argv)
    try:
        report = run(args.source, args.dry_run)
    except Refused as error:
        print(json.dumps({'schema': 'sub01.native-streamer-visual-v2-v22-install.v1', 'source': str(args.source),
                          'dry_run': args.dry_run, 'status': 'refused', 'reason': str(error)}, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
