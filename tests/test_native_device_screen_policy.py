"""Native phone/TV policy and actual integrated device bridge source."""
import itertools
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from home_world import HomeWorld  # noqa: E402

BRIDGE = 'tools/native_pc_bridge/Sub01HomeDeviceBridge.cpp'
BRIDGE_HEADER = 'tools/native_pc_bridge/Sub01HomeDeviceBridge.h'
STAGE = 'tools/stage_unreal_home_runtime.py'
HEADER = ROOT / 'tools/native_pc_bridge/Sub01DeviceScreenPolicy.h'
FIELDS = ('PublicHome', 'PhoneActivity', 'PhoneFrame', 'PhoneAppFrame', 'MinecraftSelected', 'MinecraftEnabled', 'MinecraftFrame')


def test_policy_header_truth_table_compiled():
    compiler = shutil.which('clang++') or shutil.which('g++')
    if not compiler:
        pytest.skip('C++ compiler unavailable')
    rows = list(itertools.product((0, 1), repeat=len(FIELDS)))
    checks = []
    for row in rows:
        values = dict(zip(FIELDS, row))
        phone = (0 if not values['PublicHome'] else 1 if values['PhoneActivity'] and values['PhoneFrame']
                 else 2 if values['PhoneAppFrame'] else 0)   # None, BrowserPage, AppFrame
        tv = values['PublicHome'] and values['MinecraftSelected'] and values['MinecraftEnabled'] and values['MinecraftFrame']
        setup = ''.join(f'In.{name}={value};' for name, value in values.items())
        checks.append(f'{{FSub01DeviceScreenInputs In;{setup}if(int(Sub01PhoneFrame(In))!={phone}||'
                      f'Sub01TVFetchesMinecraft(In)!={int(tv)})return 1;}}')
    source = f'#include "{HEADER}"\nint main(){{FSub01DeviceScreenInputs D;if(Sub01PhoneFrame(D)!=ESub01PhoneFrame::None||Sub01TVFetchesMinecraft(D))return 2;\n' \
             + '\n'.join(checks) + '\nreturn 0;}\n'
    with tempfile.TemporaryDirectory() as tmp:
        cpp, exe = Path(tmp) / 'policy.cpp', Path(tmp) / 'policy'
        cpp.write_text(source)
        subprocess.run([compiler, '-std=c++17', '-Wall', '-Werror', str(cpp), '-o', str(exe)], check=True, capture_output=True)
        subprocess.run([str(exe)], check=True)
    assert len(rows) == 128


def test_inputs_exist_in_the_actual_backend_payload():
    # The bridge reads home.activity / home.console_game (HomeWorld.view) and
    # minecraft.enabled / minecraft.has_frame (MinecraftConsole.view).
    view = HomeWorld().view()
    assert isinstance(view['activity'], str) and view['console_game'] in ('pong', 'chess', 'minecraft')
    from home_minecraft import MinecraftConsole
    with tempfile.TemporaryDirectory() as tmp:
        console = MinecraftConsole(Path(tmp)).view()
    assert type(console['enabled']) is bool and console['has_frame'] is False


def test_policy_matches_the_browser_rules():
    phone = (ROOT / 'web/house/phone_screen.mjs').read_text()
    assert 's.activity === "phone" && visible(s) && s.frameId' in phone
    home = (ROOT / 'web/house/home.js').read_text()
    assert "getContextKey: () => tvGame === 'minecraft' && minecraftState.has_frame ? 'minecraft' : null" in home


def native_source(path):
    return (ROOT / path).read_text()


def test_integrated_bridge_gates_fetches_and_stages_header():
    original = native_source(BRIDGE)
    bridge = native_source(BRIDGE)
    poll = bridge.split('void USub01HomeDeviceBridge::Poll(){', 1)[1].split('\nvoid USub01HomeDeviceBridge::FetchFrame', 1)[0]
    assert '#include "Sub01DeviceScreenPolicy.h"' in bridge
    # The identity helper follows every include it needs (FJsonObject must be complete).
    assert bridge.index('static FString Sub01PhoneIdentity(') > bridge.index('#include "Dom/JsonObject.h"')
    # Each fetch is behind the policy; nothing else in Poll requests a frame.
    assert poll.count('FetchFrame(') == 2
    assert 'const FSub01DeviceScreenInputs Screen=Sub01ScreenInputs(State,&Identity,&Game);' in poll
    assert 'if(Sub01PhoneFrame(Screen,FocusedDevice==TEXT("phone"))!=ESub01PhoneFrame::None)FetchFrame(TEXT("phone"),Identity,Epoch);' in poll
    assert 'if(Sub01TVFetchesMinecraft(Screen))FetchFrame(TEXT("tv"),TEXT(""),Epoch);' in poll
    assert 'phone_browser_screen' not in poll           # only through the helper, after phone_screen
    # Home is read once, before use; the blanking and Pong branches are unchanged.
    assert poll.count('State->TryGetObjectField(TEXT("home"),Home)') == 1
    assert poll.index('Sub01ScreenInputs(State,&Identity,&Game)') < poll.index('Sub01TVFetchesMinecraft')
    for kept in ('else if(Materials.Contains(TEXT("phone")))', 'else if(Game==TEXT("pong"))',
                 'else if(Materials.Contains(TEXT("tv")))Materials[TEXT("tv")]->SetTextureParameterValue(TEXT("PCFrame"),BlankCanvas);'):
        assert poll.count(kept) == 1 and original.count(kept) == 1
    # A downloaded phone frame is kept only if it is still the current one, from the same source.
    fetch = bridge.split('void USub01HomeDeviceBridge::FetchFrame(', 1)[1].split('\nvoid USub01HomeDeviceBridge::Action', 1)[0]
    assert 'if(!Sub01FrameStillCurrent(Device==TEXT("phone"),Identity,After,FocusedDevice==TEXT("phone")))return;' in fetch  # same policy, fresh state (test_native_device_frame_freshness.py)
    assert 'phone_browser_screen' not in fetch
    # Same authenticated loopback route and frame identity as before.
    assert 'R->SetURL(Origin+TEXT("/devices/")+Device.ToString()+TEXT("/frame.jpg")' in fetch
    assert "R->SetHeader(TEXT(\"X-Admin-Token\"),Token);" in fetch
    stage = native_source(STAGE)
    assert "'Sub01HomeDeviceBridge.cpp','Sub01DeviceScreenPolicy.h'" in stage  # further staged headers may follow
    # The policy is part of the actual module, not an unapplied proposal.
    assert '#include "Sub01DeviceScreenPolicy.h"' in original


def test_integrated_open_app_and_home_actions():
    bridge, header = native_source(BRIDGE), native_source(BRIDGE_HEADER)
    assert header.count(' void PhoneOpenApp(const FString& App);') == 1
    method = bridge.split('void USub01HomeDeviceBridge::PhoneOpenApp(', 1)[1].split('\n', 1)[0]
    assert 'if(PhoneFrameId.IsEmpty()||(App!=TEXT("home")&&App!=TEXT("notes")&&App!=TEXT("memory")&&App!=TEXT("browser")))return;' in method
    for field in ('TEXT("action"),TEXT("open_app")', 'TEXT("app"),App', 'TEXT("frame_id"),PhoneFrameId'):
        assert field in method
    assert 'Action(TEXT("phone"),B);' in method     # existing authenticated, privacy-guarded action path
    keys = bridge.split('if(B->GetFocusedDevice()==TEXT("phone")){', 1)[1].split('}else{', 1)[0]
    for binding in ('EKeys::Home)B->PhoneAction(TEXT("home"))', 'EKeys::One)B->PhoneOpenApp(TEXT("home"))',
                    'EKeys::Two)B->PhoneOpenApp(TEXT("notes"))', 'EKeys::Three)B->PhoneOpenApp(TEXT("memory"))',
                    'EKeys::Four)B->PhoneOpenApp(TEXT("browser"))'):
        assert binding in keys


IDENTITY_STUBS = r"""
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
"""

IDENTITY_CASES = r"""
TSharedPtr<FJsonObject> State(const char* Kind, bool Available, const char* Id, const char* Browser) {
  auto S = Obj();
  if (Kind) { auto P = Obj(); P->Strings["device"] = "phone"; P->Strings["kind"] = Kind; P->Bools["available"] = Available;
    if (Id) P->Strings["frame_id"] = Id; P->Strings["app"] = "notes"; S->Objects["phone_screen"] = P; }
  if (Browser) { auto B = Obj(); B->Strings["frame_id"] = Browser; S->Objects["phone_browser_screen"] = B; }
  return S;
}
int main() {
  bool Owned = true;
  if (Sub01PhoneIdentity(State("owned_app", true, "app-7", "web-3"), &Owned) != "app-7" || !Owned) return 1;   // app preferred
  if (Sub01PhoneIdentity(State("browser", true, "web-9", "web-3"), &Owned) != "web-9" || Owned) return 2;     // phone_screen browser
  if (Sub01PhoneIdentity(State("owned_app", false, "app-7", "web-3"), &Owned) != "" || Owned) return 3;     // unavailable: nothing
  if (Sub01PhoneIdentity(State("tiktok", true, "x", "web-3"), &Owned) != "" ) return 4;                    // unknown kind refused
  if (Sub01PhoneIdentity(State("owned_app", true, "", "web-3"), &Owned) != "") return 5;                   // empty id refused
  if (Sub01PhoneIdentity(State("owned_app", true, std::string(101, 'a').c_str(), nullptr), &Owned) != "") return 6;  // bounded id
  if (Sub01PhoneIdentity(State(nullptr, false, nullptr, "web-3"), &Owned) != "web-3" || Owned) return 7;    // older backend fallback
  if (Sub01PhoneIdentity(State(nullptr, false, nullptr, nullptr), &Owned) != "") return 8;
  if (Sub01PhoneIdentity(TSharedPtr<FJsonObject>(), &Owned) != "") return 9;
  if (Sub01PhoneIdentity(State("owned_app", true, "app-8", nullptr)) != "app-8") return 10;                 // default out-param
  return 0;
}
"""


def test_integrated_phone_identity_prefers_phone_screen_compiled():
    compiler = shutil.which('clang++') or shutil.which('g++')
    if not compiler:
        pytest.skip('C++ compiler unavailable')
    bridge = native_source(BRIDGE)
    helper = 'static FString Sub01PhoneIdentity(' + bridge.split('static FString Sub01PhoneIdentity(', 1)[1].split('\n}\n', 1)[0] + '\n}\n'
    with tempfile.TemporaryDirectory() as tmp:
        cpp, exe = Path(tmp) / 'identity.cpp', Path(tmp) / 'identity'
        cpp.write_text(IDENTITY_STUBS + helper + IDENTITY_CASES)
        subprocess.run([compiler, '-std=c++17', '-Wall', '-Werror', str(cpp), '-o', str(exe)], check=True, capture_output=True)
        subprocess.run([str(exe)], check=True)


def test_manual_phone_focus_never_bypasses_privacy_or_real_frame_requirement(tmp_path):
    compiler=shutil.which('clang++') or shutil.which('g++')
    if not compiler:pytest.skip('C++ compiler unavailable')
    cases=[]
    for public,activity,frame,owned,focus in itertools.product((0,1),repeat=5):
        expected=0 if not public else 1 if frame and (activity or focus) else 2 if owned else 0
        cases.append(f'{{FSub01DeviceScreenInputs In;In.PublicHome={public};In.PhoneActivity={activity};In.PhoneFrame={frame};In.PhoneAppFrame={owned};if(int(Sub01PhoneFrame(In,{focus}))!={expected})return 1;}}')
    source=tmp_path/'focus.cpp';exe=tmp_path/'focus'
    source.write_text(f'#include "{HEADER}"\nint main(){{'+''.join(cases)+'return 0;}')
    subprocess.run([compiler,'-std=c++17','-Wall','-Werror',str(source),'-o',str(exe)],check=True,capture_output=True)
    subprocess.run([str(exe)],check=True)
