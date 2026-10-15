"""Time viewport captures from real active ticks, not slow startup asset loading.

Staged for the next coherent native build. This changes capture timing only;
no camera, exposure, geometry, movement, activity or readiness values change.
"""
from pathlib import Path

POLICY = r'''#pragma once
#include <cmath>
#include <cstdint>
namespace Sub01CaptureWarmup {
struct Window {
 double Request=-1., FirstTick=-1.;
 uint32_t Ticks=0;
 bool Ready(double RequestedAt,double Now,double Delay){
  if(!std::isfinite(RequestedAt)||!std::isfinite(Now)||!std::isfinite(Delay)||RequestedAt<0||Now<RequestedAt||Delay<1||Delay>180)return false;
  if(Request!=RequestedAt){Request=RequestedAt;FirstTick=Now;Ticks=0;}
  if(Now<FirstTick)return false;
  if(Ticks<UINT32_MAX)++Ticks;
  return Ticks>=120&&Now-FirstTick>=Delay;
 }
};
}
'''


def stage(module):
    (Path(module)/'Sub01CaptureWarmupPolicy.h').write_text(POLICY)


def install(header, cpp):
    field = ' void UpdateNativeCapture();'
    include = '#include "Sub01HomeLab.h"'
    condition = ' if(!CaptureRequested&&Now-CaptureStarted>=CaptureAfter){'
    log = '  CaptureRequested=true;CaptureRequestedAt=Now;'
    if any(text.count(hook)!=1 for text,hook in ((header,field),(cpp,include),(cpp,condition),(cpp,log))):
        raise ValueError('Exact single existing timed-capture hooks required')
    if 'CaptureWarmupWindow' in header+cpp:
        raise ValueError('Capture warmup already installed')
    # Header needs the complete value type before the UCLASS declaration.
    generated = '#include "Sub01HomeLab.generated.h"'
    if header.count(generated)!=1:
        raise ValueError('Generated header boundary required')
    header = header.replace(generated,'#include "Sub01CaptureWarmupPolicy.h"\n'+generated,1)
    header = header.replace(field,field+'\n Sub01CaptureWarmup::Window CaptureWarmupWindow;',1)
    cpp = cpp.replace(condition,' if(!CaptureRequested&&CaptureWarmupWindow.Ready(CaptureStarted,Now,CaptureAfter)){',1)
    cpp = cpp.replace(log,log+'\n  UE_LOG(LogTemp,Display,TEXT("SUB01_CAPTURE_ACTUAL_TICK_WARMUP ticks=%u activeSeconds=%.6f requestedDelay=%.6f; startup load time excluded"),CaptureWarmupWindow.Ticks,Now-CaptureWarmupWindow.FirstTick,double(CaptureAfter));',1)
    return header,cpp
