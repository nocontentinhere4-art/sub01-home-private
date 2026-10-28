#!/usr/bin/env python3
"""Launch the final private Game in LIVE mode (it follows the backend through the 8831 bridge) and bind it.

Runs detached as root. The game runs as uid 1001 (unreal) on Xvfb :99, side by side with the old manual-mode
game, which is left untouched here. Progress goes to live-game-20261023/status.json and launch.log.
"""
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

ENGINE = '/workspace/sub01-private-recovered-engine/Engine/Binaries/Linux/UnrealEditor-Cmd'
PROJECT = '/home/unreal/.sub01-private/cinematic-source-v3-final/Sub01HomeLab/Sub01HomeLab.uproject'
PRIVATE = Path('/home/unreal/.sub01-private')
OUT = PRIVATE / 'live-game-20261023'
CONTROL = PRIVATE / 'native-control.json'
UID = GID = 1001
STATUS = OUT / 'status.json'
LOG = open(OUT / 'launch.log', 'a', buffering=1)
state = {'started_utc': time.time()}


def log(*parts):
    print(time.strftime('%H:%M:%S'), *parts, file=LOG, flush=True)


def save():
    STATUS.write_text(json.dumps(state, indent=1))


def start_ticks(pid):
    return int((Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()[19])


def drop_privileges():
    os.setgid(GID)
    os.initgroups('unreal', GID)
    os.setuid(UID)


def write_control(doc):
    tmp = CONTROL.with_suffix('.tmp')
    tmp.write_text(json.dumps(doc))
    os.chown(tmp, UID, GID)
    tmp.chmod(0o600)
    os.replace(tmp, CONTROL)


def log_has(path, *markers):
    try:
        text = path.read_text(errors='replace')
    except OSError:
        return None
    for marker in markers:
        if marker in text:
            return marker
    return None


def api_home():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8830/api/home', timeout=3) as response:
            return json.load(response).get('home') or {}
    except (OSError, ValueError):
        return {}


def main():
    token = (PRIVATE / 'operator-token').read_text().strip()
    assert len(token) >= 16 and '\n' not in token
    xdg = PRIVATE / 'xdg-runtime'
    xdg.mkdir(exist_ok=True)
    os.chown(xdg, UID, GID)
    xdg.chmod(0o700)
    if not CONTROL.exists():
        write_control({'revision': 0})
    assert Path('/home/unreal/runtime-tools/BigBuckBunny-720p.webm').stat().st_size > 0
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/home/unreal', 'USER': 'unreal', 'LANG': 'C.UTF-8',
           'DISPLAY': ':99', 'SDL_VIDEODRIVER': 'x11', 'XDG_RUNTIME_DIR': str(xdg),
           'XAUTHORITY': str(PRIVATE / 'native-xauthority'),
           'SUB01_HOME_ORIGIN': 'http://127.0.0.1:8831', 'SUB01_PC_ORIGIN': 'http://127.0.0.1:8832',
           'SUB01_ADMIN_TOKEN': token,
           'LD_LIBRARY_PATH': '/workspace/sub01-home-private/claude-12h/libs/usr/lib/x86_64-linux-gnu',
           'OMP_NUM_THREADS': '4', 'OPENBLAS_NUM_THREADS': '1'}
    args = [ENGINE, PROJECT, '/Game/Sub01Home/ActualHome', '-game', '-Sub01CompletionSandbox', '-Sub01ManualView',
            '-Sub01LiveHome', '-Sub01NativeControl=' + str(CONTROL),
            '-vulkan', '-unattended', '-NoSound', '-NoSplash', '-NoLiveCoding', '-NoHotReloadFromIDE', '-corelimit=10',
            '-windowed', '-NoBorder', '-WinX=0', '-WinY=0', '-ResX=1920', '-ResY=1080', '-ForceRes',
            '-ExecCmds=t.MaxFPS 24,t.IdleWhenNotForeground 0,r.VSync 0,Slate.bAllowThrottling 0',
            '-stdout', '-FullStdOutLogOutput']
    game_log = OUT / 'game.log'
    with game_log.open('ab') as out:
        child = subprocess.Popen(args, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                                 start_new_session=True, preexec_fn=drop_privileges, cwd='/home/unreal')
    time.sleep(1)
    assert child.poll() is None, 'game exited immediately'
    state.update(pid=child.pid, start_ticks=start_ticks(child.pid), game_log=str(game_log), launched_utc=time.time(),
                 args=[a for a in args], phase='starting')
    save()
    log('game launched pid', child.pid, 'start_ticks', state['start_ticks'])

    # 1. wait for the first world tick (shader/PSO warm-up took ~13 min on 2026-10-22)
    deadline = time.time() + 45 * 60
    while time.time() < deadline:
        if child.poll() is not None:
            state.update(phase='exited', returncode=child.returncode)
            save()
            log('game exited early', child.returncode)
            return
        if log_has(game_log, 'SUB01_FIRST_GAME_WORLD_TICK'):
            break
        time.sleep(5)
    else:
        state['phase'] = 'no_first_tick'
        save()
        log('no first world tick within 45 min')
        return
    state.update(phase='ticking', first_tick_utc=time.time())
    save()
    log('first world tick seen')
    time.sleep(8)   # let the pawn land on its floor before the switch

    # 2. switch the view to live: the game then binds to the bridge (retrying itself while it waits for ground contact)
    revision = 1
    try:
        revision = int(json.loads(CONTROL.read_text()).get('revision', 0)) + 1
    except (OSError, ValueError, TypeError):
        pass
    write_control({'revision': revision, 'mode': 'live'})
    state.update(phase='switching', control_revision=revision)
    save()
    log('control written: live, revision', revision)
    deadline = time.time() + 5 * 60
    while time.time() < deadline:
        marker = log_has(game_log, 'SUB01_LIVE_HOME_BOUND', 'SUB01_LIVE_HOME_REFUSED', 'SUB01_VIEW_SWITCH_REFUSED', 'SUB01_VIEW_MODE_REFUSED')
        if marker:
            state['switch_marker'] = marker
            break
        if child.poll() is not None:
            state.update(phase='exited', returncode=child.returncode)
            save()
            return
        time.sleep(2)
    save()
    log('switch marker:', state.get('switch_marker'))

    # 3. confirm the backend sees the bound consumer
    deadline = time.time() + 3 * 60
    while time.time() < deadline:
        home = api_home()
        consumer = home.get('native_consumer') or {}
        state['native_consumer'] = consumer
        state['backend_place'] = home.get('place')
        state['backend_activity'] = home.get('activity')
        if consumer.get('bound'):
            state['phase'] = 'bound'
            save()
            log('backend reports native consumer bound', json.dumps(consumer))
            return
        time.sleep(3)
    state['phase'] = 'not_bound'
    save()
    log('backend did not report a bound consumer', json.dumps(state.get('native_consumer')))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:   # always leave a record
        state.update(phase='error', error=type(error).__name__, detail=str(error)[:300])
        save()
        log('error', type(error).__name__, str(error)[:300])
        raise
