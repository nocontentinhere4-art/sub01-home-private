"""Exercise the v24 wrapper in a disposable project; never invoke Unreal or touch a pod."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def build(tmp_path):
    project = tmp_path / 'project'
    source = project / 'Sub01HomeLab/Source/Sub01HomeLab'
    binaries = project / 'Sub01HomeLab/Binaries/Linux'
    deploy = tmp_path / 'share/deploy/v24'
    commands = tmp_path / 'commands'
    for p in (source, binaries, deploy, commands):
        p.mkdir(parents=True)
    (source / 'scene.cpp').write_text('v23 source')
    so = binaries / 'libUnrealEditor-Sub01HomeLab.so'
    so.write_text('v23 binary')
    stop = tmp_path / 'STOP'
    stop.touch()
    (deploy / 'source-v23-manifest.json').write_text(json.dumps({'scene.cpp': hashlib.sha256(b'v23 source').hexdigest()}))
    after = hashlib.sha256(b'v24 source').hexdigest()
    report = {'status': 'planned', 'source': str(source), 'files': {'scene.cpp': {'after_sha256': after}}}
    (deploy / 'expected-dry-run.json').write_text(json.dumps(report))
    installer = deploy / 'install_v24.py'
    installer.write_text('import json,sys,os\nfrom pathlib import Path\np=Path(sys.argv[sys.argv.index("--source")+1])\n'
                         f'print(json.dumps({{"status":"planned" if "--dry-run" in sys.argv else "applied","source":str(p),"files":{{"scene.cpp":{{"after_sha256":"{after}"}}}}}}))\n'
                         'if "--dry-run" not in sys.argv: (p/"scene.cpp").write_text("wrong" if os.environ.get("TEST_APPLY_MODE")=="wrong" else "v24 source")\n')
    (deploy / 'installer.sha256').write_text(hashlib.sha256(installer.read_bytes()).hexdigest() + '  install_v24.py\n')
    (deploy / 'artifact-marker.txt').write_text('V24_TEST_MARKER\n')

    def executable(path, text):
        path.write_text(text)
        path.chmod(0o755)

    executable(commands / 'id', '#!/bin/sh\necho 0\n')
    executable(commands / 'runuser', '#!/bin/sh\nshift 3\nexec "$@"\n')
    executable(commands / 'df', '#!/bin/sh\necho "Filesystem blocks used available capacity mounted"\n'
               'echo "test 10000000000 0 ${TEST_AVAILABLE:-9000000000} 0% /"\n')
    executable(commands / 'stat', f'#!{sys.executable}\nimport os,sys\nprint(int(os.stat(sys.argv[-1]).st_mtime))\n')
    executable(commands / 'sha256sum', f'#!{sys.executable}\n' + '''import hashlib,sys
from pathlib import Path
if sys.argv[1] == '-c':
 for row in Path(sys.argv[2]).read_text().splitlines():
  sha,name=row.split(None,1)
  if hashlib.sha256(Path(name.strip()).read_bytes()).hexdigest()!=sha: sys.exit(1)
else:
 p=Path(sys.argv[1]); print(hashlib.sha256(p.read_bytes()).hexdigest(), str(p))
''')
    engine = tmp_path / 'fake-engine-command'
    executable(engine, f'#!{sys.executable}\n' + '''import os,sys
from pathlib import Path
if os.environ.get('TEST_BUILD_MODE') == 'success': Path(os.environ['TEST_SO']).write_text('new V24_TEST_MARKER binary')
if os.environ.get('TEST_FAIL_LOG') == '1':
 p=Path(os.environ['TEST_LOG']); p.unlink(); p.mkdir()
sys.exit(int(os.environ.get('TEST_BUILD_STATUS','0')))
''')
    wrapper = tmp_path / 'build.sh'
    script = (ROOT / 'tools/pod/onpod/build-v24.sh').read_text()
    script = script.replace('/home/unreal/.sub01-private/cinematic-source-v3-final', str(project))
    script = script.replace('/home/unreal/.sub01-private/streamer/STOP', str(stop))
    script = script.replace('/tmp/sub01-share', str(tmp_path / 'share'))
    script = script.replace('/workspace/sub01-private-recovered-engine/Engine/Build/BatchFiles/Linux/Build.sh', str(engine))
    wrapper.write_text(script)

    def run(mode='success', status=0, available=9000000000, apply_mode='normal', optimize=False, fail_log=False):
        env = dict(os.environ, PATH=str(commands)+os.pathsep+os.environ['PATH'], TEST_BUILD_MODE=mode,
                   TEST_BUILD_STATUS=str(status), TEST_AVAILABLE=str(available), TEST_SO=str(so), TEST_APPLY_MODE=apply_mode,
                   PYTHONOPTIMIZE='1' if optimize else '', TEST_FAIL_LOG='1' if fail_log else '',
                   TEST_LOG=str(project / 'build-v24.log'))
        return subprocess.run(['bash', str(wrapper)], capture_output=True, text=True, env=env, timeout=10)
    return run, project, source, tmp_path / 'share', deploy


def test_build_failure_preserves_status_and_backup(build):
    run, project, source, share, deploy = build
    result = run(status=7)
    assert result.returncode == 7, result.stdout + result.stderr
    assert (project / 'source-backup-before-v24/scene.cpp').read_text() == 'v23 source'
    assert 'BUILD_EXIT=7' in (share / 'pod-changes.log').read_text()
    assert not (deploy / 'artifact-receipt.txt').exists()


def test_verified_build_success(build):
    run, project, source, share, deploy = build
    result = run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'after_sha256=' in (deploy / 'artifact-receipt.txt').read_text()
    assert 'state=complete BUILD_EXIT=0' in (share / 'pod-changes.log').read_text()


def test_success_without_new_binary_is_failure(build):
    run, project, source, share, deploy = build
    assert run(mode='no_artifact').returncode == 8
    assert not (deploy / 'artifact-receipt.txt').exists()


def test_wrong_applied_source_stops_before_build(build):
    run, project, source, share, deploy = build
    result = run(apply_mode='wrong')
    assert result.returncode != 0
    assert not (project / 'build-v24.log').exists()
    assert (project / 'source-backup-before-v24/scene.cpp').read_text() == 'v23 source'


@pytest.mark.parametrize('condition', ['drift', 'apply'])
def test_validation_survives_python_optimization(build, condition):
    run, project, source, share, deploy = build
    if condition == 'drift': (source / 'extra.cpp').write_text('unexpected')
    result = run(optimize=True, apply_mode='wrong' if condition == 'apply' else 'normal')
    assert result.returncode != 0
    assert not (project / 'build-v24.log').exists()


@pytest.mark.parametrize('compiler_status,wrapper_status', [(7, 7), (0, 9)])
def test_failed_log_append_does_not_hide_compiler_status(build, compiler_status, wrapper_status):
    run, project, source, share, deploy = build
    result = run(status=compiler_status, fail_log=True)
    assert result.returncode == wrapper_status, result.stdout + result.stderr
    assert f'BUILD_EXIT={compiler_status}' in (share / 'pod-changes.log').read_text()
    assert not (deploy / 'artifact-receipt.txt').exists()


@pytest.mark.parametrize('condition,status', [('lease', 3), ('low_disk', 4), ('drift', 1), ('backup', 2), ('installer', 1)])
def test_preflight_refuses_before_source_changes(build, condition, status):
    run, project, source, share, deploy = build
    if condition == 'lease': (share / 'MEASURING').touch()
    if condition == 'drift': (source / 'extra.cpp').write_text('unexpected')
    if condition == 'backup': (project / 'source-backup-before-v24').mkdir()
    if condition == 'installer': (deploy / 'install_v24.py').write_text('unreviewed change')
    result = run(available=3758096384 if condition == 'low_disk' else 9000000000)
    assert result.returncode == status, result.stdout + result.stderr
    assert (source / 'scene.cpp').read_text() == 'v23 source'
    assert not (project / 'binaries-backup-before-v24').exists()
