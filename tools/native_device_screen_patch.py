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
STAGE = 'tools/stage_unreal_home_runtime.py'
PATCH = ROOT / 'docs/proposed/native-device-screen-policy.patch'

EDITS = [
    (BRIDGE, 'include',
     '#include "Sub01HomeDeviceBridge.h"\n',
     '#include "Sub01HomeDeviceBridge.h"\n#include "Sub01DeviceScreenPolicy.h"\n'),
    (BRIDGE, 'phone gated on activity',
     '  const TSharedPtr<FJsonObject>* Phone=nullptr;FString Identity;'
     'if(State->TryGetObjectField(TEXT("phone_browser_screen"),Phone)&&Phone&&(*Phone)->TryGetStringField(TEXT("frame_id"),Identity)&&!Identity.IsEmpty())'
     'FetchFrame(TEXT("phone"),Identity,Epoch);\n',
     '  const TSharedPtr<FJsonObject>* Home=nullptr;State->TryGetObjectField(TEXT("home"),Home);FString Game,Activity;'
     '(*Home)->TryGetStringField(TEXT("console_game"),Game);(*Home)->TryGetStringField(TEXT("activity"),Activity);\n'
     '  FSub01DeviceScreenInputs Screen;Screen.PublicHome=true;Screen.PhoneActivity=Activity==TEXT("phone");Screen.MinecraftSelected=Game==TEXT("minecraft");\n'
     '  const TSharedPtr<FJsonObject>* Minecraft=nullptr;if(State->TryGetObjectField(TEXT("minecraft"),Minecraft)&&Minecraft)'
     '{(*Minecraft)->TryGetBoolField(TEXT("enabled"),Screen.MinecraftEnabled);(*Minecraft)->TryGetBoolField(TEXT("has_frame"),Screen.MinecraftFrame);}\n'
     '  const TSharedPtr<FJsonObject>* Phone=nullptr;FString Identity;'
     'Screen.PhoneFrame=State->TryGetObjectField(TEXT("phone_browser_screen"),Phone)&&Phone&&(*Phone)->TryGetStringField(TEXT("frame_id"),Identity)&&!Identity.IsEmpty();\n'
     '  // Browser parity (Sub01DeviceScreenPolicy.h): a page only while he is on the phone.\n'
     '  if(Sub01PhoneShowsPage(Screen))FetchFrame(TEXT("phone"),Identity,Epoch);\n'),
    (BRIDGE, 'home read once',
     '  const TSharedPtr<FJsonObject>* Home=nullptr;State->TryGetObjectField(TEXT("home"),Home);FString Game;'
     '(*Home)->TryGetStringField(TEXT("console_game"),Game);\n',
     ''),
    (BRIDGE, 'tv waits for a live frame',
     '  if(Game==TEXT("minecraft"))FetchFrame(TEXT("tv"),TEXT(""),Epoch);\n',
     '  // Minecraft only with a live frame; selected without one, the TV stays blank (below).\n'
     '  if(Sub01TVFetchesMinecraft(Screen))FetchFrame(TEXT("tv"),TEXT(""),Epoch);\n'),
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
    for path in (BRIDGE, STAGE):
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
