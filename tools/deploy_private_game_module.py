"""Deploy the verified project-only binary after the sole Editor has exited."""
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from launch_private_normal_game import MODULE_SHA
from launch_private_persistent_editor import PROJECT, PRIVATE, verified_window

SIBLING = Path('/workspace/sub01-private-native-build/Sub01HomeLab')
HASHES = {
    'libUnrealEditor-Sub01HomeLab.so': MODULE_SHA,
    'libUnrealEditor-Sub01HomeLab.debug': 'ab5b05bb0f7f3b61ca587f89d2414565a2238688239d7b61660caa9bfda5b0f1',
    'libUnrealEditor-Sub01HomeLab.sym': '48d230de9b08e2f757298104157fa7fa6f7b3bf5a608e3e814e50fc5b8e11108',
    'UnrealEditor.modules': '9c051a8a7c90657a24e2718e9cd4f41e16dcbdf37374940848e092eaa79df653',
    'Sub01HomeLabEditor.target': '26948e7c25f9deb5bb45cf8cdf5ac3fec6cfeb96623d58e1b494c86287aa530a',
}


def deploy():
    verified_window(Path('/run/sub01-home-private/runtime-window.json'))
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            assert not ((proc / 'comm').read_text().startswith('UnrealEditor') and
                        (proc / 'stat').read_text().rsplit(')', 1)[1].split()[0] != 'Z'), 'Live Unreal module must never be overwritten'
        except OSError:
            continue
    proof = json.loads((SIBLING / 'final-controller-basis-phone-witness-b704640-artifact-proof.json').read_text())
    assert proof['actual_exit'] == 0 and proof['schema'] == 'sub01.actual-sibling-native-artifacts.v1'
    assert proof['target'] == 'dgtgepkz7h1zy5'
    assert proof['result']['exit'] == 0
    source, target = SIBLING / 'Binaries/Linux', PROJECT / 'Binaries/Linux'
    for name, expected in HASHES.items():
        assert proof['files'][name]['sha256'] == expected
        assert hashlib.sha256((source / name).read_bytes()).hexdigest() == expected
    assert json.loads((source / 'UnrealEditor.modules').read_text())['BuildId'] == '55116800'
    backup = PRIVATE / f'pre-game-binary-{time.time_ns()}'
    backup.mkdir(mode=0o700)
    before = {}
    for name in HASHES:
        existing = target / name
        if existing.exists():
            shutil.copy2(existing, backup / name)
            before[name] = hashlib.sha256(existing.read_bytes()).hexdigest()
    for name, expected in HASHES.items():
        pending = target / ('.' + name + '.verified-new')
        # The portable volume refuses root chown. Receive as its actual owner.
        if pending.exists():
            assert hashlib.sha256(pending.read_bytes()).hexdigest() == expected
            pending.unlink()
        script = ('import hashlib,os,shutil,sys;from pathlib import Path;'
                  'src,tmp,dst,digest=map(str,sys.argv[1:]);'
                  'shutil.copy2(src,tmp);'
                  'assert hashlib.sha256(Path(tmp).read_bytes()).hexdigest()==digest;'
                  'os.replace(tmp,dst)')
        subprocess.run(['/usr/sbin/runuser', '-u', 'unreal', '--', 'python3', '-c', script,
                        str(source / name), str(pending), str(target / name), expected], check=True)
    receipt = {'schema': 'sub01.private-game-binary-deployment.v1', 'deployed_epoch': time.time(),
               'backup': str(backup), 'before': before, 'after': HASHES,
               'build_id': '55116800', 'map_config_source_unchanged': True,
               'native_game_accepted': False}
    (PRIVATE / 'game-binary-deployment.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('PROJECT_BINARY_DEPLOYED', MODULE_SHA, flush=True)


if __name__ == '__main__':
    deploy()
