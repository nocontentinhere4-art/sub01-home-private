"""Launch the single private recovered Editor within its authenticated window."""
import configparser
import json
import os
import subprocess
import shutil
import stat
import time
from pathlib import Path

POD = 'dgtgepkz7h1zy5'
MAXIMUM_AUTHORIZED_DEADLINE = 1792117175
ENGINE = Path('/workspace/sub01-private-recovered-engine')
PROJECT = Path('/workspace/sub01-private-recovered-project/Sub01HomeLab')
PRIVATE = Path('/home/unreal/.sub01-private')
BOOTSTRAP = Path('/home/unreal/runtime-tools/persistent_recovered_editor_bootstrap.py')


def verified_window(guard):
    parent = guard.parent.lstat()
    assert stat.S_ISDIR(parent.st_mode) and parent.st_uid == 0 and not parent.st_mode & 0o022
    fd = os.open(guard, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(fd)
        assert stat.S_ISREG(metadata.st_mode) and metadata.st_uid == 0
        assert metadata.st_nlink == 1 and not metadata.st_mode & 0o022
        raw = os.read(fd, 4097)
        assert len(raw) <= 4096
    finally:
        os.close(fd)
    window = json.loads(raw)
    deadline = window['deadline_epoch']
    assert window['pod'] == POD and type(deadline) is int
    assert time.time() + 600 < deadline <= MAXIMUM_AUTHORIZED_DEADLINE
    assert window['stop_guards_authenticated'] is True and 0 < window['total_cap'] <= 100
    assert window['minimum_balance_reserve'] >= 10
    assert window['initial_actual_balance'] > window['minimum_balance_reserve']
    assert window['root_guard_authenticated'] is True
    for name in ('root_guard_pid', 'external_guard_pid', 'second_external_guard_pid'):
        assert type(window[name]) is int and window[name] > 0
    os.kill(window['root_guard_pid'], 0)
    return window


def verified_private_crash_preference(engine):
    # This exact active layer was independently read back through UE GetIni.
    # A user Saved/Config file was ignored by the recovered installed build.
    path = Path(engine) / 'Engine/Config/BaseEditorSettings.ini'
    config = configparser.ConfigParser(strict=False, interpolation=None)
    config.read(path)
    section = '/Script/UnrealEd.CrashReportsPrivacySettings'
    assert config.getboolean(section, 'bSendUnattendedBugReports', fallback=True) is False, (
        'Private target must explicitly disable unattended reports before Editor startup')
    return path


def run():
    window = verified_window(Path('/run/sub01-home-private/runtime-window.json'))
    deadline = window['deadline_epoch']
    verified_private_crash_preference(ENGINE)
    assert json.loads((ENGINE / 'private-plugin-descriptor-recovery-receipt.json').read_text())['all_selected_crc_verified']
    assert json.loads((PROJECT / 'private-original-source-project-sha-receipt.json').read_text())['all1038_source_original_sha_matched']
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            name = (process / 'comm').read_text().strip()
            state = (process / 'stat').read_text().rsplit(')', 1)[1].split()[0]
            assert not (name.startswith('UnrealEditor') and state != 'Z'), 'Another Unreal instance remains'
        except OSError:
            continue
    assert Path('/tmp/.X11-unix/X99').exists() and BOOTSTRAP.is_file()
    assert (ENGINE / 'Engine/DerivedDataCache/Compressed.ddp').stat().st_size == 1134102445, 'Verified baked shader cache is not yet transferred'
    # Preserve the already warm Zen store; all writable DDC remains on the volume.
    cache = Path('/workspace/sub01-private-derived-cache/ZenData')
    assert cache.is_dir()
    default_zen = Path('/home/unreal/.config/Epic/UnrealEngine/Common/Zen/Data')
    subprocess.run(['/usr/sbin/runuser', '-u', 'unreal', '--',
                    'mkdir', '-p', str(default_zen.parent)], check=True)
    if not default_zen.exists() and not default_zen.is_symlink():
        default_zen.symlink_to(cache, target_is_directory=True)
    assert default_zen.resolve() == cache.resolve()
    cpus = sorted(os.sched_getaffinity(0))[:10]
    assert len(cpus) >= 4
    affinity = ','.join(map(str, cpus))
    seconds = int(deadline - time.time())
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/home/unreal',
           'LANG': 'C.UTF-8', 'DISPLAY': ':99',
           'XAUTHORITY': str(PRIVATE / 'native-xauthority'),
           'XDG_RUNTIME_DIR': str(PRIVATE / 'xdg-runtime'),
           'OMP_NUM_THREADS': '6', 'OPENBLAS_NUM_THREADS': '1'}
    args = ['/usr/sbin/runuser', '-u', 'unreal', '--', 'timeout', '--kill-after=10',
            str(seconds), 'taskset', '-c', affinity, str(ENGINE / 'Engine/Binaries/Linux/UnrealEditor'),
            str(PROJECT / 'Sub01HomeLab.uproject'), '/Game/Sub01Home/ActualHome',
            '-NoSplash', '-Unattended', '-NoSound', '-NoLiveCoding', '-NoHotReloadFromIDE',
            '-corelimit=10', '-physicalcorelimit=10',
            '-ExecutePythonScript=' + str(BOOTSTRAP), '-log', '-stdout',
            '-FullStdOutLogOutput', '-ResX=1280', '-ResY=720', '-Windowed']
    log_path = PRIVATE / 'persistent-editor-launch.log'
    if log_path.exists():
        shutil.copy2(log_path, PRIVATE / f'previous-editor-launch-{time.time_ns()}.log')
    log = log_path.open('w')
    child = subprocess.Popen(args, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    receipt = {'wrapper_pid': child.pid, 'engine_root': str(ENGINE),
               'project_root': str(PROJECT), 'deadline_epoch': deadline,
               'cpu_affinity': cpus, 'persistent_zen_cache': str(cache),
               'started_epoch': time.time(), 'native_game_accepted': False,
               'descriptor_dependency_crc_pass': True,
               'python_keepalive_set_by_verified_bootstrap_api': True}
    (PRIVATE / 'persistent-editor-launch.json').write_text(json.dumps(receipt))
    print('DETACHED_VERIFIED_PERSISTENT_EDITOR_LAUNCHED', child.pid, seconds, flush=True)


if __name__ == '__main__':
    run()
