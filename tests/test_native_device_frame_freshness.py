"""The native bridge's final paint check, compiled from the actual source.

Sub01PhoneIdentity, Sub01ScreenInputs and Sub01FrameStillCurrent are extracted
verbatim from Sub01HomeDeviceBridge.cpp and compiled with Sub01DeviceScreenPolicy.h
against a small JSON stand-in. Each case is a transition: the state Poll used to
request a frame, then the fresh state read after the bytes arrived.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / 'tools/native_pc_bridge'
CPP = (BRIDGE / 'Sub01HomeDeviceBridge.cpp').read_text()


def function(name, returns):
    start = CPP.index(f'static {returns} {name}(')
    return CPP[start:CPP.index('\n}\n', start) + 3]


STUBS = r'''
#include <map>
#include <memory>
#include <string>
#define TEXT(x) x
struct FString : std::string { using std::string::string; FString() {} FString(const std::string& s) : std::string(s) {}
  bool IsEmpty() const { return empty(); } int Len() const { return (int)size(); } };
template <class T> struct TSharedPtr { std::shared_ptr<T> P; bool IsValid() const { return (bool)P; } T* operator->() const { return P.get(); } };
struct FJsonObject {
  std::map<std::string, TSharedPtr<FJsonObject>> Objects; std::map<std::string, std::string> Strings; std::map<std::string, bool> Bools;
  bool TryGetObjectField(const char* K, const TSharedPtr<FJsonObject>*& Out) const { auto I = Objects.find(K); if (I == Objects.end()) return false; Out = &I->second; return true; }
  bool TryGetStringField(const char* K, FString& Out) const { auto I = Strings.find(K); if (I == Strings.end()) return false; Out = I->second; return true; }
  bool TryGetBoolField(const char* K, bool& Out) const { auto I = Bools.find(K); if (I == Bools.end()) return false; Out = I->second; return true; }
};
TSharedPtr<FJsonObject> Obj() { TSharedPtr<FJsonObject> O; O.P = std::make_shared<FJsonObject>(); return O; }
#include "Sub01DeviceScreenPolicy.h"
'''

CASES = r'''
struct Doc {
  const char* Activity = "research"; const char* Game = "pong";
  const char* Kind = nullptr; const char* Id = nullptr; bool Available = true; const char* Browser = nullptr;
  bool Minecraft = false; bool Enabled = false; bool HasFrame = false;
};
TSharedPtr<FJsonObject> Make(const Doc& D) {
  auto S = Obj(); auto H = Obj(); H->Strings["activity"] = D.Activity; H->Strings["console_game"] = D.Game; H->Bools["privacy"] = false;
  S->Objects["home"] = H;
  if (D.Kind) { auto P = Obj(); P->Strings["kind"] = D.Kind; P->Bools["available"] = D.Available; if (D.Id) P->Strings["frame_id"] = D.Id; S->Objects["phone_screen"] = P; }
  if (D.Browser) { auto B = Obj(); B->Strings["frame_id"] = D.Browser; S->Objects["phone_browser_screen"] = B; }
  if (D.Minecraft) { auto M = Obj(); M->Bools["enabled"] = D.Enabled; M->Bools["has_frame"] = D.HasFrame; S->Objects["minecraft"] = M; }
  return S;
}
// What Poll requests from a state (same helper and policy as the bridge's Poll).
bool PollFetchesPhone(const Doc& D, FString& Id) { const auto In = Sub01ScreenInputs(Make(D), &Id); return Sub01PhoneFrame(In) != ESub01PhoneFrame::None; }
bool PollFetchesTV(const Doc& D) { return Sub01TVFetchesMinecraft(Sub01ScreenInputs(Make(D))); }
#define CHECK(c, n) if (!(c)) return n;
int main() {
  FString Id;
  // Browser page on the phone, then he puts the phone down: same frame id, activity changed.
  Doc Browsing; Browsing.Activity = "phone"; Browsing.Kind = "browser"; Browsing.Id = "web-1";
  CHECK(PollFetchesPhone(Browsing, Id) && Id == "web-1", 1)
  Doc PutDown = Browsing; PutDown.Activity = "sleep";
  CHECK(Sub01FrameStillCurrent(true, Id, Make(Browsing)), 2)        // unchanged: paint
  CHECK(!Sub01FrameStillCurrent(true, Id, Make(PutDown)), 3)        // same id, not on the phone: refuse
  // The older browser-only status behaves the same way.
  Doc Legacy; Legacy.Activity = "phone"; Legacy.Browser = "web-2"; Doc LegacyDown = Legacy; LegacyDown.Activity = "eat";
  CHECK(PollFetchesPhone(Legacy, Id) && Id == "web-2" && !Sub01FrameStillCurrent(true, Id, Make(LegacyDown)), 4)
  // Owned app frames stay showable when he is not on the phone (while public).
  Doc Notes; Notes.Kind = "owned_app"; Notes.Id = "app-7";
  CHECK(PollFetchesPhone(Notes, Id) && Id == "app-7", 5)
  Doc NotesLater = Notes; NotesLater.Activity = "sleep";
  CHECK(Sub01FrameStillCurrent(true, Id, Make(NotesLater)), 6)
  // The frame moved on, became unavailable, or turned into a browser page while he is away.
  Doc Moved = Notes; Moved.Id = "app-8"; CHECK(!Sub01FrameStillCurrent(true, Id, Make(Moved)), 7)
  Doc Gone = Notes; Gone.Available = false; CHECK(!Sub01FrameStillCurrent(true, Id, Make(Gone)), 8)
  Doc Turned = Notes; Turned.Kind = "browser"; CHECK(!Sub01FrameStillCurrent(true, Id, Make(Turned)), 9)
  CHECK(!Sub01FrameStillCurrent(true, FString(), Make(Notes)), 10)   // an empty identity never paints
  // Minecraft on the TV: requested with a frame, then disabled / frame lost / game changed.
  Doc Playing; Playing.Game = "minecraft"; Playing.Minecraft = true; Playing.Enabled = true; Playing.HasFrame = true;
  CHECK(PollFetchesTV(Playing) && Sub01FrameStillCurrent(false, FString(), Make(Playing)), 11)
  Doc Disabled = Playing; Disabled.Enabled = false; CHECK(!Sub01FrameStillCurrent(false, FString(), Make(Disabled)), 12)
  Doc Lost = Playing; Lost.HasFrame = false; CHECK(!Sub01FrameStillCurrent(false, FString(), Make(Lost)), 13)
  Doc Switched = Playing; Switched.Game = "pong"; CHECK(!Sub01FrameStillCurrent(false, FString(), Make(Switched)), 14)
  Doc NoConsole = Playing; NoConsole.Minecraft = false; CHECK(!Sub01FrameStillCurrent(false, FString(), Make(NoConsole)), 15)
  CHECK(!PollFetchesTV(Lost) && !PollFetchesTV(Disabled), 16)        // Poll would not have asked either
  CHECK(!Sub01FrameStillCurrent(false, FString(), TSharedPtr<FJsonObject>()), 17)
  CHECK(!Sub01FrameStillCurrent(true, "web-1", TSharedPtr<FJsonObject>()), 18)
  // Actual local physical focus allows a real page without forging brain activity.
  CHECK(Sub01FrameStillCurrent(true,"web-1",Make(PutDown),true),19)
  CHECK(!Sub01FrameStillCurrent(true,"web-1",Make(PutDown),false),20) // focus lost during image download
  CHECK(!Sub01FrameStillCurrent(true,"stale",Make(PutDown),true),21)
  CHECK(!Sub01FrameStillCurrent(true,"web-1",TSharedPtr<FJsonObject>(),true),22)
  return 0;
}
'''


def test_final_paint_check_transitions_compiled_from_actual_bridge():
    compiler = shutil.which('clang++') or shutil.which('g++')
    if not compiler:
        pytest.skip('C++ compiler unavailable')
    source = (STUBS + function('Sub01PhoneIdentity', 'FString') + function('Sub01ScreenInputs', 'FSub01DeviceScreenInputs')
              + function('Sub01FrameStillCurrent', 'bool') + CASES)
    with tempfile.TemporaryDirectory() as tmp:
        cpp, exe = Path(tmp) / 'fresh.cpp', Path(tmp) / 'fresh'
        cpp.write_text(source)
        built = subprocess.run([compiler, '-std=c++17', '-Wall', '-Werror', f'-I{BRIDGE}', str(cpp), '-o', str(exe)], capture_output=True, text=True)
        assert built.returncode == 0, built.stderr[-3000:]
        ran = subprocess.run([str(exe)])
        assert ran.returncode == 0, f'transition case {ran.returncode} failed'


def test_poll_and_final_paint_share_one_parser_and_policy():
    poll = CPP.split('void USub01HomeDeviceBridge::Poll(){', 1)[1].split('\nvoid USub01HomeDeviceBridge::FetchFrame', 1)[0]
    fetch = CPP.split('void USub01HomeDeviceBridge::FetchFrame(', 1)[1].split('\nvoid USub01HomeDeviceBridge::Action', 1)[0]
    assert 'const FSub01DeviceScreenInputs Screen=Sub01ScreenInputs(State,&Identity,&Game);' in poll
    assert 'if(Sub01PhoneFrame(Screen,FocusedDevice==TEXT("phone"))!=ESub01PhoneFrame::None)FetchFrame(TEXT("phone"),Identity,Epoch);' in poll
    assert 'if(Sub01TVFetchesMinecraft(Screen))FetchFrame(TEXT("tv"),TEXT(""),Epoch);' in poll
    # The fresh After state is rechecked by the same policy before any texture is created or bound.
    after = fetch.split('ReadHome([this,Device,Identity,Epoch,Pixels,Tag](TSharedPtr<FJsonObject> After){', 1)[1]
    check = after.index('if(!Sub01FrameStillCurrent(Device==TEXT("phone"),Identity,After,FocusedDevice==TEXT("phone")))return;')
    assert after.index('if(!PublicHome(After)){Clear();return;}') < check
    assert check < after.index('SetTextureParameterValue(TEXT("PCFrame"),Images[Device])')
    assert check < after.index('FImageUtils::ImportBufferAsTexture2D(Pixels)')
    # No second, divergent recheck remains.
    assert 'Sub01PhoneIdentity(After)' not in fetch and 'Game!=TEXT("minecraft")' not in fetch
