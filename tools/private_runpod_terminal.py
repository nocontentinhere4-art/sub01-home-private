"""Administer the already authorized private home server through Jupyter's API.

No credentials are embedded or printed. This client never starts pods or changes
their budget. Use the small local server-api-client environment for websocket.
"""
import argparse
import json
import shlex
import time
import urllib.request
import urllib.error
import uuid
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--command-file', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=45)
    args = parser.parse_args()
    import websocket
    config = json.loads(args.config.read_text())
    base = config['base_url'].rstrip('/')
    if base not in {'https://713u6mnmxu4y1a-8888.proxy.runpod.net', 'https://80lf8giw6ft61v-8888.proxy.runpod.net', 'https://5ldnm4vax9kelh-8888.proxy.runpod.net', 'https://kjsxms1gk4rmv6-8888.proxy.runpod.net'}:
        raise RuntimeError('This client is restricted to the authorized home pods')
    token = next(iter(config['tokens'].values()))
    headers = {'Authorization': 'token ' + token, 'User-Agent': 'Mozilla/5.0'}
    req = urllib.request.Request(base + '/api/terminals', data=b'{}',
                                 headers={**headers, 'Content-Type': 'application/json'})
    terminal = json.load(urllib.request.urlopen(req, timeout=20))['name']
    endpoint = base.replace('https://', 'wss://', 1) + '/terminals/websocket/' + terminal
    sock = None
    try:
        sock = websocket.create_connection(endpoint, header=headers,
                                           origin=base, timeout=10)
        marker = 'SUB01_DONE_' + uuid.uuid4().hex
        command = args.command_file.read_text()
        begin = 'SUB01_BEGIN_' + uuid.uuid4().hex
        payload = "stty -echo; printf '\\n" + begin + "\\n'; bash -c " + shlex.quote(command) + "; printf '\\n" + marker + "=%s\\n' \"$?\"\n"
        sock.send(json.dumps(['stdin', payload]))
        stop = time.monotonic() + args.timeout
        output = ''
        while time.monotonic() < stop:
            try:
                message = json.loads(sock.recv())
            except websocket.WebSocketTimeoutException:
                continue
            if message[0] == 'stdout':
                output += message[1]
                # The command can appear in initial terminal echo before stty.
                if '\r\n' + marker + '=' in output or '\n' + marker + '=' in output:
                    break
        else:
            raise TimeoutError('Remote command exceeded the bounded wait')
        output = output.replace('\r', '')
        output = output.split('\n' + begin + '\n', 1)[-1]
        lines = output.splitlines()
        for line in lines:
            if token in line or 'stty -echo; bash -c ' in line:
                continue
            if line.startswith(marker + '='):
                print('REMOTE_EXIT=' + line.split('=', 1)[1])
            elif line and not line.startswith('root@'):
                print(line)
    finally:
        if sock:
            sock.close()
        request = urllib.request.Request(base + '/api/terminals/' + terminal,
                                          method='DELETE', headers=headers)
        try:
            urllib.request.urlopen(request, timeout=10).close()
        except Exception:
            pass


if __name__ == '__main__':
    try:
        main()
    except urllib.error.HTTPError as error:
        print('PRIVATE_SERVER_HTTP_STATUS=' + str(error.code))
        raise SystemExit(1)
    except Exception as error:
        # Network exceptions may contain private request URLs: report type only.
        print('PRIVATE_SERVER_ERROR=' + type(error).__name__)
        raise SystemExit(1)
