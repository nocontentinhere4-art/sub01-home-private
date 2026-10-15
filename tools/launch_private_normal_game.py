"""Start the normal private walking game after the saved Editor handoff.

This launcher never stops an Editor, changes a map, or enables a posture gate.
"""
import hashlib
import json
import os
import stat
import subprocess
import time
from pathlib import Path

from launch_private_persistent_editor import (
    ENGINE, PROJECT, PRIVATE, verified_private_crash_preference, verified_window,
)

MODULE_SHA = '07f505ae570dd465246e60717ece728e30c9b9a285297b5d59612f03f9bee144'


def launch():
    window = verified_window(Path('/run/sub01-home-private/runtime-window.json'))
    verified_private_crash_preference(ENGINE)
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            name = (proc / 'comm').read_text().strip()
            state = (proc / 'stat').read_text().rsplit(')', 1)[1].split()[0]
            assert not (name.startswith('UnrealEditor') and state != 'Z'), 'Save and close the sole Editor before Game handoff'
        except OSError:
            continue
    module = PROJECT / 'Binaries/Linux/libUnrealEditor-Sub01HomeLab.so'
    assert hashlib.sha256(module.read_bytes()).hexdigest() == MODULE_SHA
    assert json.loads((PROJECT / 'Binaries/Linux/UnrealEditor.modules').read_text())['BuildId'] == '55116800'
    assert Path('/tmp/.X11-unix/X99').exists()
    token_path = PRIVATE / 'operator-token'
    metadata = token_path.lstat()
    assert stat.S_ISREG(metadata.st_mode) and metadata.st_uid == 1001 and stat.S_IMODE(metadata.st_mode) == 0o600
    token = token_path.read_text().strip()
    assert token
    control = PRIVATE / 'native-control.json'
    control.write_text(json.dumps({'revision': 0}))
    os.chown(control, 1001, 1001)
    control.chmod(0o600)
    stamp = time.time_ns()
    capture = PROJECT / 'evidence' / f'normal-game-first-{stamp}.png'
    capture.parent.mkdir(exist_ok=True)
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/home/unreal',
           'LANG': 'C.UTF-8', 'DISPLAY': ':99', 'SDL_VIDEODRIVER': 'x11',
           'XAUTHORITY': str(PRIVATE / 'native-xauthority'),
           'XDG_RUNTIME_DIR': str(PRIVATE / 'xdg-runtime'),
           'SUB01_HOME_ORIGIN': 'http://127.0.0.1:8821',
           'SUB01_PC_ORIGIN': 'http://127.0.0.1:8811', 'SUB01_ADMIN_TOKEN': token,
           'SUB01_KITCHEN_RUNTIME': '1',
           'OMP_NUM_THREADS': '6', 'OPENBLAS_NUM_THREADS': '1'}
    remaining = max(1, int(window['deadline_epoch'] - time.time()))
    cpus = sorted(os.sched_getaffinity(0))[:10]
    args = ['/usr/sbin/runuser', '-u', 'unreal', '--', 'timeout', '--kill-after=10',
            str(remaining), 'taskset', '-c', ','.join(map(str, cpus)),
            str(ENGINE / 'Engine/Binaries/Linux/UnrealEditor-Cmd'),
            str(PROJECT / 'Sub01HomeLab.uproject'), '/Game/Sub01Home/ActualHome',
            '-game', '-vulkan', '-unattended', '-NoSound', '-NoSplash',
            '-NoLiveCoding', '-NoHotReloadFromIDE', '-corelimit=10', '-physicalcorelimit=10',
            '-windowed', '-NoBorder', '-WinX=0', '-WinY=0', '-ResX=1280', '-ResY=720',
            '-ExecCmds=t.MaxFPS 60,t.IdleWhenNotForeground 0,r.VSync 0,Slate.bAllowThrottling 0,r.DefaultFeature.MotionBlur 0',
            '-Sub01LiveHome', '-Sub01ManualView', '-Sub01NativeControl=' + str(control),
            '-Sub01CaptureAfter=4', '-Sub01CaptureViewport', '-Sub01CapturePath=' + str(capture),
            '-log', '-stdout', '-FullStdOutLogOutput']
    log_path = PRIVATE / f'normal-game-{stamp}.log'
    with log_path.open('w') as log:
        child = subprocess.Popen(args, env=env, stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    receipt = {'schema': 'sub01.normal-private-game-launch.v1',
               'wrapper_pid': child.pid, 'started_epoch': time.time(),
               'deadline_epoch': window['deadline_epoch'], 'module_sha256': MODULE_SHA,
               'engine_root': str(ENGINE), 'project_root': str(PROJECT),
               'log': str(log_path), 'requested_capture': str(capture),
               'normal_walk_idle_config_is_candidate': True,
               'diagnostic_pose_flags': False, 'native_game_accepted': False}
    (PRIVATE / 'normal-game-launch.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('NORMAL_GAME_LAUNCHED', child.pid, str(log_path), str(capture), flush=True)


if __name__ == '__main__':
    launch()
