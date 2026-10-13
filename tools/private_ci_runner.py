"""One-job, unprivileged GitHub runner on the authorized private home server.

No account PAT is accepted or transmitted: use a short-lived repo registration
token file. Each runner removes its registration automatically after one job.
The dedicated Unix user has no access to the private server/operator files.
"""
import argparse
import fcntl
import hashlib
import os
import pwd
import shutil
import subprocess
import tarfile
import time
import urllib.request
from pathlib import Path

POD = '80lf8giw6ft61v'
REPO = 'https://github.com/nocontentinhere4-art/sub01-home-private'
DEADLINE = 1791927900
VERSION = '2.338.0'
SHA256 = 'af4b794c1bc41d73d40535e3fe092a39f9679cd8d965954c2aca25a05ca41d32'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--token-file', type=Path, required=True)
    parser.add_argument('--slot', type=int, choices=(1, 2), required=True)
    args = parser.parse_args()
    if os.environ.get('RUNPOD_POD_ID') != POD or os.geteuid() != 0:
        raise RuntimeError('Only the authorized home server root may provision this runner')
    remaining = int(DEADLINE - time.time())
    if remaining < 120:
        raise RuntimeError('Authorized compute window is ending')
    if args.token_file.stat().st_mode & 0o077:
        raise RuntimeError('Registration token file must be owner-only')
    token = args.token_file.read_text().strip()
    if len(token) < 12:
        raise RuntimeError('Missing short-lived registration token')
    name = f'sub01-ci-{args.slot}'
    uid = 2100 + args.slot
    try:
        user = pwd.getpwnam(name)
    except KeyError:
        subprocess.run(['useradd', '--create-home', '--uid', str(uid),
                        '--shell', '/bin/bash', name], check=True)
        user = pwd.getpwnam(name)
    if user.pw_uid != uid:
        raise RuntimeError('Unexpected CI user identity')
    root = Path(user.pw_dir) / 'runner'
    root.mkdir(mode=0o700, exist_ok=True)
    archive = Path('/tmp') / f'actions-runner-{VERSION}.tar.gz'
    with archive.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        valid = False
        if archive.is_file():
            with archive.open('rb') as source:
                valid = hashlib.file_digest(source, 'sha256').hexdigest() == SHA256
        if not valid:
            url = f'https://github.com/actions/runner/releases/download/v{VERSION}/actions-runner-linux-x64-{VERSION}.tar.gz'
            partial = archive.with_suffix('.part')
            with urllib.request.urlopen(url, timeout=60) as response, partial.open('wb') as output:
                shutil.copyfileobj(response, output, 1024 * 1024)
            with partial.open('rb') as source:
                valid = hashlib.file_digest(source, 'sha256').hexdigest() == SHA256
            if not valid:
                raise RuntimeError('Official runner release checksum mismatch')
            partial.replace(archive)
    with tarfile.open(archive) as packed:
        packed.extractall(root, filter='data')
    for directory, children, files in os.walk(user.pw_dir):
        os.chown(directory, uid, user.pw_gid)
        for item in children + files:
            os.chown(Path(directory) / item, uid, user.pw_gid, follow_symlinks=False)
    os.chmod(user.pw_dir, 0o700)
    # Official CommandSettings supports this input environment variable and
    # removes it immediately. It never appears in the process argument list.
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8',
           'ACTIONS_RUNNER_INPUT_TOKEN': token}
    sandbox = ['/usr/sbin/runuser', '-u', name, '--', '/usr/bin/python3',
               '/usr/local/bin/sub01-ci-landlock', '--']
    command = sandbox + ['/bin/bash', str(root / 'config.sh'),
               '--unattended', '--url', REPO, '--name', name,
               '--labels', 'sub01-home-private-ci', '--ephemeral',
               '--disableupdate', '--work', '_work']
    configured = subprocess.run(command, cwd=root, env=env, capture_output=True)
    env.pop('ACTIONS_RUNNER_INPUT_TOKEN')
    args.token_file.unlink(missing_ok=True)
    if configured.returncode:
        # Do not print configuration output: it may contain credential details.
        raise RuntimeError('Ephemeral runner configuration failed')
    print('PRIVATE_EPHEMERAL_RUNNER_READY', name, flush=True)
    # One job only; timeout stays inside the independently enforced pod stop.
    remaining = max(1, int(DEADLINE - time.time()) - 20)
    result = subprocess.run(sandbox + ['/usr/bin/timeout',
                             '--signal=TERM', '--kill-after=5', str(remaining),
                             '/bin/bash', str(root / 'run.sh'), '--once'], cwd=root, env=env)
    print('PRIVATE_EPHEMERAL_RUNNER_EXIT', name, result.returncode, flush=True)


if __name__ == '__main__':
    main()
