#!/usr/bin/env python3
"""Replace the TV/phone-only device proxy on 8832 with the real PC runner (v86 Linux guest + device proxy).

scripts/home_pc_runner.py serves /pc/* for the backend (HOME_COMPUTER_ORIGIN) and the native PCBridge, and
/devices/* for the native device bridge (TV, phone) through the same backend. Runs as uid 1001; detached.
"""
import argparse
import json
import os
import signal
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

PRIVATE = Path('/home/unreal/.sub01-private')
SOURCE = PRIVATE / 'latest-source-20261023'
NODE_DIR = '/workspace/sub01-home-private/streaming/node-v22.14.0-linux-x64/bin'
PYTHON = '/home/unreal/venv/bin/python'
DATA = PRIVATE / 'pc-runner-20261023'
PORT = 8832
ENV = {'PATH': NODE_DIR + ':/usr/local/bin:/usr/bin:/bin', 'HOME': '/home/unreal', 'USER': 'unreal', 'LANG': 'C.UTF-8',
       'PYTHONPATH': str(SOURCE), 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'}


def as_unreal():
    os.setgid(1001)
    os.initgroups('unreal', 1001)
    os.setuid(1001)


def port_busy():
    with socket.socket() as s:
        s.settimeout(.3)
        return s.connect_ex(('127.0.0.1', PORT)) == 0


def stop_device_proxy():
    stopped = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            argv = (proc / 'cmdline').read_bytes().split(b'\0')
        except OSError:
            continue
        if any(a.endswith(b'cinematic_actual_device_proxy.py') for a in argv):
            os.kill(int(proc.name), signal.SIGTERM)
            stopped.append(int(proc.name))
    return stopped


def get(path, token=None, timeout=4):
    request = urllib.request.Request(f'http://127.0.0.1:{PORT}{path}', headers={'X-Admin-Token': token} if token else {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as r:
            return r.status, r.read(2000).decode(errors='replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read(300).decode(errors='replace')
    except OSError as e:
        return None, str(e)[:120]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--token-file', default=str(PRIVATE / 'operator-token'))
    a = p.parse_args()
    token = Path(a.token_file).read_text().strip()
    DATA.mkdir(exist_ok=True)
    os.chown(DATA, 1001, 1001)
    DATA.chmod(0o700)
    stopped = stop_device_proxy()
    for _ in range(40):
        if not port_busy():
            break
        time.sleep(.25)
    assert not port_busy(), 'port 8832 still busy'
    log = (DATA / 'pc-runner.log').open('ab')
    child = subprocess.Popen([PYTHON, str(SOURCE / 'scripts' / 'home_pc_runner.py'), '--host', '127.0.0.1', '--port', str(PORT),
                              '--data-dir', str(DATA), '--home-origin', 'http://127.0.0.1:8830', '--token-file', a.token_file],
                             env=ENV, cwd=str(SOURCE), preexec_fn=as_unreal, stdin=subprocess.DEVNULL, stdout=log,
                             stderr=subprocess.STDOUT, start_new_session=True)
    health = None
    for _ in range(30):
        time.sleep(1)
        if child.poll() is not None:
            break
        health = get('/healthz')
        if health[0] == 200:
            break
    result = {'stopped_device_proxy': stopped, 'runner_pid': child.pid, 'exited': child.poll(), 'healthz': health,
              'pc_state': get('/pc/state', token), 'devices_state': get('/devices/state', token)}
    (DATA / 'start-receipt.json').write_text(json.dumps(result, indent=1))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
