"""Delayed asset startup must not masquerade as a warmed first Game frame."""
import shutil
import subprocess
from pathlib import Path
import pytest
import unreal_native_capture_warmup as warm
import stage_unreal_home_runtime as runtime


def test_actual_tick_clock_and_frame_count_both_required(tmp_path):
    compiler=shutil.which('c++')
    if not compiler:pytest.skip('C++ compiler unavailable')
    warm.stage(tmp_path)
    cpp=tmp_path/'warm.cpp';exe=tmp_path/'warm'
    cpp.write_text('''#include "Sub01CaptureWarmupPolicy.h"
#include <cassert>
#include <limits>
int main(){using Sub01CaptureWarmup::Window;
Window startup;
// Constructor request at0; assets block300s. Frame1 must remain uncapturable.
assert(!startup.Ready(0,300,4));
for(int i=1;i<240;i++)assert(!startup.Ready(0,300+i/60.,4));
assert(startup.Ready(0,304,4));
Window noTime;
for(int i=0;i<1000;i++)assert(!noTime.Ready(0,300,4));
assert(noTime.Ready(0,304,4));
Window slow;
assert(!slow.Ready(0,300,4));
for(int i=0;i<118;i++)assert(!slow.Ready(0,310,4));
assert(slow.Ready(0,310,4));
// A later route capture starts a new warm window; no stale ready state.
assert(!startup.Ready(500,900,4));assert(startup.Ticks==1);
assert(startup.FirstTick==900);
for(int i=0;i<118;i++)assert(!startup.Ready(500,904,4));
assert(startup.Ready(500,904,4));
assert(!startup.Ready(500,899,4));
const auto ticks=startup.Ticks;
assert(!startup.Ready(500,std::numeric_limits<double>::quiet_NaN(),4));
assert(!startup.Ready(500,905,0));assert(!startup.Ready(500,905,181));
assert(startup.Ticks==ticks);
}
''')
    subprocess.run([compiler,'-std=c++17',str(cpp),'-o',str(exe)],check=True,capture_output=True)
    subprocess.run([str(exe)],check=True,capture_output=True)


def test_real_stage_uses_active_tick_window_and_preserves_view_capture(tmp_path):
    (tmp_path/'Sub01HomeLab.uproject').write_text('{}');(tmp_path/'Config').mkdir()
    runtime.stage(tmp_path)
    module=tmp_path/'Source/Sub01HomeLab'
    header=(module/'Sub01HomeLab.h').read_text();cpp=(module/'Sub01HomeLab.cpp').read_text()
    assert header.index('"Sub01CaptureWarmupPolicy.h"') < header.index('"Sub01HomeLab.generated.h"')
    assert cpp.count('CaptureWarmupWindow.Ready(CaptureStarted,Now,CaptureAfter)')==1
    assert 'FScreenshotRequest::RequestScreenshot(CapturePath,false,false);' in cpp
    assert 'Sub01CaptureWarmup::Window CaptureWarmupWindow;' in header
    assert (module/'Sub01CaptureWarmupPolicy.h').read_text()==warm.POLICY
    with pytest.raises(ValueError):warm.install(header,cpp)
