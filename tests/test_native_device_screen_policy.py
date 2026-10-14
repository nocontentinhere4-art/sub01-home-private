"""Native phone/TV browser parity: the owned policy header and its proposed bridge patch."""
import itertools
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import native_device_screen_patch as patch  # noqa: E402
from home_world import HomeWorld  # noqa: E402

HEADER = ROOT / 'tools/native_pc_bridge/Sub01DeviceScreenPolicy.h'
FIELDS = ('PublicHome', 'PhoneActivity', 'PhoneFrame', 'MinecraftSelected', 'MinecraftEnabled', 'MinecraftFrame')


def test_policy_header_truth_table_compiled():
    compiler = shutil.which('clang++') or shutil.which('g++')
    if not compiler:
        pytest.skip('C++ compiler unavailable')
    rows = list(itertools.product((0, 1), repeat=len(FIELDS)))
    checks = []
    for row in rows:
        values = dict(zip(FIELDS, row))
        phone = values['PublicHome'] and values['PhoneActivity'] and values['PhoneFrame']
        tv = values['PublicHome'] and values['MinecraftSelected'] and values['MinecraftEnabled'] and values['MinecraftFrame']
        setup = ''.join(f'In.{name}={value};' for name, value in values.items())
        checks.append(f'{{FSub01DeviceScreenInputs In;{setup}if(Sub01PhoneShowsPage(In)!={int(phone)}||'
                      f'Sub01TVFetchesMinecraft(In)!={int(tv)})return 1;}}')
    source = f'#include "{HEADER}"\nint main(){{FSub01DeviceScreenInputs D;if(Sub01PhoneShowsPage(D)||Sub01TVFetchesMinecraft(D))return 2;\n' \
             + '\n'.join(checks) + '\nreturn 0;}\n'
    with tempfile.TemporaryDirectory() as tmp:
        cpp, exe = Path(tmp) / 'policy.cpp', Path(tmp) / 'policy'
        cpp.write_text(source)
        subprocess.run([compiler, '-std=c++17', '-Wall', '-Werror', str(cpp), '-o', str(exe)], check=True, capture_output=True)
        subprocess.run([str(exe)], check=True)
    assert len(rows) == 64


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


def test_proposed_patch_is_current_and_applies():
    assert patch.main(['--check']) == 0
    subprocess.run(['git', 'apply', '--check', str(patch.PATCH)], cwd=ROOT, check=True)


def test_patched_bridge_gates_fetches_and_stages_header():
    original = (ROOT / patch.BRIDGE).read_text()
    bridge = patch.apply_edits(original, patch.BRIDGE)
    poll = bridge.split('void USub01HomeDeviceBridge::Poll(){', 1)[1].split('\nvoid USub01HomeDeviceBridge::FetchFrame', 1)[0]
    assert '#include "Sub01DeviceScreenPolicy.h"' in bridge
    # Each fetch is behind the policy; nothing else in Poll requests a frame.
    assert poll.count('FetchFrame(') == 2
    assert 'if(Sub01PhoneShowsPage(Screen))FetchFrame(TEXT("phone"),Identity,Epoch);' in poll
    assert 'if(Sub01TVFetchesMinecraft(Screen))FetchFrame(TEXT("tv"),TEXT(""),Epoch);' in poll
    # Home is read once, before use; the blanking and Pong branches are unchanged.
    assert poll.count('State->TryGetObjectField(TEXT("home"),Home)') == 1
    assert poll.index('FString Game,Activity') < poll.index('Sub01TVFetchesMinecraft')
    for kept in ('else if(Materials.Contains(TEXT("phone")))', 'else if(Game==TEXT("pong"))',
                 'else if(Materials.Contains(TEXT("tv")))Materials[TEXT("tv")]->SetTextureParameterValue(TEXT("PCFrame"),BlankCanvas);'):
        assert poll.count(kept) == 1 and original.count(kept) == 1
    stage = patch.apply_edits((ROOT / patch.STAGE).read_text(), patch.STAGE)
    assert "'Sub01HomeDeviceBridge.cpp','Sub01DeviceScreenPolicy.h']" in stage
    # Native files stay untouched until their owner applies the patch.
    assert 'Sub01DeviceScreenPolicy.h' not in original
