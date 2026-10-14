"""Proposed native phone/TV browser-parity patch (generated, not applied).

The native device bridge and the staging list are owned elsewhere; this tool
only writes docs/proposed/native-device-screen-policy.patch from exact, unique
anchors, using the owned header tools/native_pc_bridge/Sub01DeviceScreenPolicy.h.

    python tools/native_device_screen_patch.py            # write the patch
    python tools/native_device_screen_patch.py --check    # patch up to date?
"""

import argparse
import difflib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = 'tools/native_pc_bridge/Sub01HomeDeviceBridge.cpp'
HEADER = 'tools/native_pc_bridge/Sub01HomeDeviceBridge.h'
STAGE = 'tools/stage_unreal_home_runtime.py'
PATCH = ROOT / 'docs/proposed/native-device-screen-policy.patch'

EDITS = [
    (BRIDGE, 'include',
     '#include "Sub01HomeDeviceBridge.h"\n',
     '#include "Sub01HomeDeviceBridge.h"\n#include "Sub01DeviceScreenPolicy.h"\n'),
    (BRIDGE, 'phone identity helper',
     '#include "InputCoreTypes.h"\n',
     '#include "InputCoreTypes.h"\n'
     '// Current phone frame: GET /api/home phone_screen {kind:"owned_app"|"browser",available,frame_id}\n'
     '// first, else the older phone_browser_screen.frame_id. Empty when no frame is available.\n'
     'static FString Sub01PhoneIdentity(const TSharedPtr<FJsonObject>& State,bool* OwnedApp=nullptr){\n'
     ' const TSharedPtr<FJsonObject>* Screen=nullptr;FString Id,Kind;bool Available=false;if(OwnedApp)*OwnedApp=false;\n'
     ' if(State.IsValid()&&State->TryGetObjectField(TEXT("phone_screen"),Screen)&&Screen&&(*Screen).IsValid()){\n'
     '  if(!(*Screen)->TryGetBoolField(TEXT("available"),Available)||!Available||!(*Screen)->TryGetStringField(TEXT("kind"),Kind)||(Kind!=TEXT("owned_app")&&Kind!=TEXT("browser"))\n'
     '   ||!(*Screen)->TryGetStringField(TEXT("frame_id"),Id)||Id.IsEmpty()||Id.Len()>100)return FString();\n'
     '  if(OwnedApp)*OwnedApp=Kind==TEXT("owned_app");return Id;\n'
     ' }\n'
     ' if(State.IsValid()&&State->TryGetObjectField(TEXT("phone_browser_screen"),Screen)&&Screen&&(*Screen).IsValid()&&(*Screen)->TryGetStringField(TEXT("frame_id"),Id)&&!Id.IsEmpty()&&Id.Len()<=100)return Id;\n'
     ' return FString();\n'
     '}\n'),
    (BRIDGE, 'phone app keys',
     'if(K==EKeys::Enter)B->PhoneAction(TEXT("close_notice"));\n',
     'if(K==EKeys::Enter)B->PhoneAction(TEXT("close_notice"));\n'
     '   if(K==EKeys::Home)B->PhoneAction(TEXT("home"));if(K==EKeys::One)B->PhoneOpenApp(TEXT("home"));if(K==EKeys::Two)B->PhoneOpenApp(TEXT("notes"));'
     'if(K==EKeys::Three)B->PhoneOpenApp(TEXT("memory"));if(K==EKeys::Four)B->PhoneOpenApp(TEXT("browser"));\n'),
    (BRIDGE, 'phone frame source and gating',
     '  const TSharedPtr<FJsonObject>* Phone=nullptr;FString Identity;'
     'if(State->TryGetObjectField(TEXT("phone_browser_screen"),Phone)&&Phone&&(*Phone)->TryGetStringField(TEXT("frame_id"),Identity)&&!Identity.IsEmpty())'
     'FetchFrame(TEXT("phone"),Identity,Epoch);\n',
     '  const TSharedPtr<FJsonObject>* Home=nullptr;State->TryGetObjectField(TEXT("home"),Home);FString Game,Activity;'
     '(*Home)->TryGetStringField(TEXT("console_game"),Game);(*Home)->TryGetStringField(TEXT("activity"),Activity);\n'
     '  FSub01DeviceScreenInputs Screen;Screen.PublicHome=true;Screen.PhoneActivity=Activity==TEXT("phone");Screen.MinecraftSelected=Game==TEXT("minecraft");\n'
     '  const TSharedPtr<FJsonObject>* Minecraft=nullptr;if(State->TryGetObjectField(TEXT("minecraft"),Minecraft)&&Minecraft)'
     '{(*Minecraft)->TryGetBoolField(TEXT("enabled"),Screen.MinecraftEnabled);(*Minecraft)->TryGetBoolField(TEXT("has_frame"),Screen.MinecraftFrame);}\n'
     '  bool OwnedApp=false;const FString Identity=Sub01PhoneIdentity(State,&OwnedApp);Screen.PhoneAppFrame=OwnedApp;Screen.PhoneFrame=!OwnedApp&&!Identity.IsEmpty();\n'
     '  // Browser parity (Sub01DeviceScreenPolicy.h): a browser page only while he is on the\n'
     '  // phone; an owned app frame whenever the home is public. Same authenticated route.\n'
     '  if(Sub01PhoneFrame(Screen)!=ESub01PhoneFrame::None)FetchFrame(TEXT("phone"),Identity,Epoch);\n'),
    (BRIDGE, 'home read once',
     '  const TSharedPtr<FJsonObject>* Home=nullptr;State->TryGetObjectField(TEXT("home"),Home);FString Game;'
     '(*Home)->TryGetStringField(TEXT("console_game"),Game);\n',
     ''),
    (BRIDGE, 'tv waits for a live frame',
     '  if(Game==TEXT("minecraft"))FetchFrame(TEXT("tv"),TEXT(""),Epoch);\n',
     '  // Minecraft only with a live frame; selected without one, the TV stays blank (below).\n'
     '  if(Sub01TVFetchesMinecraft(Screen))FetchFrame(TEXT("tv"),TEXT(""),Epoch);\n'),
    (BRIDGE, 'downloaded phone frame still current',
     'if(!PublicHome(After)){Clear();return;}const TSharedPtr<FJsonObject>* Current=nullptr;FString Id;\n'
     '   if(Device==TEXT("phone")&&(!After->TryGetObjectField(TEXT("phone_browser_screen"),Current)||!Current||!(*Current)->TryGetStringField(TEXT("frame_id"),Id)||Id!=Identity))return;\n',
     'if(!PublicHome(After)){Clear();return;}\n'
     '   if(Device==TEXT("phone")&&Sub01PhoneIdentity(After)!=Identity)return;\n'),
    (BRIDGE, 'open app action',
     'void USub01HomeDeviceBridge::PhoneNavigate(',
     'void USub01HomeDeviceBridge::PhoneOpenApp(const FString& App){if(PhoneFrameId.IsEmpty()||(App!=TEXT("home")&&App!=TEXT("notes")&&App!=TEXT("memory")&&App!=TEXT("browser")))return;'
     'auto B=MakeShared<FJsonObject>();B->SetStringField(TEXT("action"),TEXT("open_app"));B->SetStringField(TEXT("app"),App);B->SetStringField(TEXT("frame_id"),PhoneFrameId);Action(TEXT("phone"),B);}\n'
     'void USub01HomeDeviceBridge::PhoneNavigate('),
    (HEADER, 'open app declaration',
     ' void PhoneNavigate(const FString& URL);\n',
     ' void PhoneNavigate(const FString& URL);\n void PhoneOpenApp(const FString& App);\n'),
    (STAGE, 'stage header',
     "'Sub01HomeDeviceBridge.h','Sub01HomeDeviceBridge.cpp']",
     "'Sub01HomeDeviceBridge.h','Sub01HomeDeviceBridge.cpp','Sub01DeviceScreenPolicy.h']"),
]


def apply_edits(text, path):
    for file, name, anchor, replacement in EDITS:
        if file != path:
            continue
        if text.count(anchor) != 1:
            raise ValueError(f'anchor {name!r} found {text.count(anchor)} times in {path}')
        text = text.replace(anchor, replacement)
    return text


def build_patch():
    out = []
    for path in (BRIDGE, HEADER, STAGE):
        original = (ROOT / path).read_text()
        out += difflib.unified_diff(original.splitlines(True), apply_edits(original, path).splitlines(True),
                                    f'a/{path}', f'b/{path}')
    return ''.join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    patch = build_patch()
    if args.check:
        ok = PATCH.exists() and PATCH.read_text() == patch
        print('up to date' if ok else 'stale: run python tools/native_device_screen_patch.py')
        return 0 if ok else 1
    PATCH.write_text(patch)
    print(f'wrote {PATCH.relative_to(ROOT)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
