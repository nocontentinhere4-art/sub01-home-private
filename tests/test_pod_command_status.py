"""Run the actual CLI helpers against a fake Jupyter transport and real local child commands.

No pod, credentials, network, engine or GPU are needed. The transport executes the submitted shell/Python payload,
so these tests catch status loss in the wire payload as well as in the local wrapper.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
FAKE_TRANSPORT = r'''
import asyncio, json, os, re, subprocess, sys
from types import SimpleNamespace
class WSMsgType:
    TEXT, CLOSE, CLOSED, ERROR = 1, 2, 3, 4
class Response:
    def raise_for_status(self):
        if os.environ.get("POD_TEST_MODE") == "http_error": raise RuntimeError("HTTP failure")
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def json(self): return {"name": "test-terminal", "id": "test-kernel"}
class Socket(Response):
    def __init__(self): self.messages = []
    async def send_str(self, raw):
        data = json.loads(raw)
        mode = os.environ.get("POD_TEST_MODE", "normal")
        if isinstance(data, list):
            if "stty -echo" in data[1]: return
            if mode == "closed": return
            result = subprocess.run(["bash", "-c", data[1]], capture_output=True, text=True, timeout=3)
            text = result.stdout + result.stderr
            if mode == "out_of_range": text = re.sub(r"(END[0-9a-f]+) \d+", r"\1 256", text)
            if mode == "duplicate": text += text
            # Terminal websocket output may arrive split in the middle of a marker.
            self.messages = [json.dumps(["stdout", text[:len(text)//2]]),
                             json.dumps(["stdout", text[len(text)//2:]])]
            if mode == "duplicate": self.messages = [json.dumps(["stdout", text])]
            if mode == "fragmented_status":
                split = re.search(r"END[0-9a-f]+ 4", text).end()
                self.messages = [json.dumps(["stdout", text[:split]]), json.dumps(["stdout", text[split:]])]
        else:
            if mode == "closed": return
            mid = data["header"]["msg_id"]
            code = data["content"]["code"]
            if mode == "timeout": code = code.replace("timeout=240", "timeout=0.05")
            result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=3)
            output = result.stdout
            if mode == "missing": output = re.sub(r"END[0-9a-f]+ \d+", "", output)
            if mode == "out_of_range": output = re.sub(r"(END[0-9a-f]+) \d+", r"\1 256", output)
            if mode == "duplicate": output += output
            def msg(kind, content, parent=mid):
                return json.dumps({"parent_header":{"msg_id":parent}, "header":{"msg_type":kind},
                                   "content":content})
            messages = [msg("stream", {"text":"unrelated request"}, "foreign"),
                        msg("stream", {"text":output})]
            if result.returncode or mode == "kernel_error":
                messages.append(msg("error", {"traceback":[result.stderr or "kernel error"]}))
            reply = msg("execute_reply", {"status":"error" if result.returncode or mode == "reply_error" else "ok"})
            idle = msg("status", {"execution_state":"idle"})
            messages.extend([idle, reply] if mode == "idle_first" else [reply, idle])
            self.messages = messages
    async def receive(self):
        if self.messages: return SimpleNamespace(type=WSMsgType.TEXT, data=self.messages.pop(0))
        return SimpleNamespace(type=WSMsgType.CLOSED, data="")
class ClientSession(Response):
    def __init__(self, **kwargs): pass
    def post(self, *args, **kwargs): return Response()
    def delete(self, *args, **kwargs): return Response()
    def ws_connect(self, *args, **kwargs): return Socket()
'''


@pytest.fixture
def cli(tmp_path):
    (tmp_path / 'aiohttp.py').write_text(FAKE_TRANSPORT)
    pods = tmp_path / 'pods.json'
    pods.write_text(json.dumps([{'id': 'test-pod', 'env': {'JUPYTER_PASSWORD': 'secret-test-token'}}]))

    def run(helper, command, mode='normal'):
        env = dict(os.environ, PYTHONPATH=str(tmp_path), POD_TEST_MODE=mode)
        return subprocess.run([sys.executable, str(ROOT / 'tools/pod' / helper), str(pods), 'test-pod', command],
                              env=env, capture_output=True, text=True, timeout=6)
    return run


@pytest.mark.parametrize('helper', ['podterm.py', 'podrun.py'])
@pytest.mark.parametrize('command,status', [('true', 0), ('false', 1), ('exit 7', 7), ('exit 42', 42)])
def test_child_status_survives_transport(cli, helper, command, status):
    result = cli(helper, command)
    assert result.returncode == status, result.stderr + result.stdout


@pytest.mark.parametrize('helper', ['podterm.py', 'podrun.py'])
def test_output_and_secret_redaction(cli, helper):
    result = cli(helper, "printf 'stdout secret-test-token'; printf 'stderr' >&2; exit 7")
    assert result.returncode == 7
    assert 'stdout' in result.stdout and 'stderr' in result.stdout
    assert 'secret-test-token' not in result.stdout + result.stderr


def test_terminal_multiline_here_document(cli):
    result = cli('podterm.py', "cat <<'TEXT'\nhello\nTEXT\nexit 7")
    assert result.returncode == 7
    assert 'hello' in result.stdout


def test_terminal_waits_for_all_status_digits_and_newline(cli):
    assert cli('podterm.py', 'exit 42', 'fragmented_status').returncode == 42


@pytest.mark.parametrize('helper', ['podterm.py', 'podrun.py'])
def test_disconnect_is_not_success(cli, helper):
    assert cli(helper, 'true', 'closed').returncode == 124


@pytest.mark.parametrize('helper', ['podterm.py', 'podrun.py'])
@pytest.mark.parametrize('mode', ['duplicate', 'out_of_range', 'http_error'])
def test_invalid_completion_or_http_failure_is_not_success(cli, helper, mode):
    assert cli(helper, 'true', mode).returncode != 0


def test_kernel_signal_maps_to_shell_status(cli):
    assert cli('podrun.py', 'kill -TERM $$').returncode == 143


@pytest.mark.parametrize('mode,status', [('missing', 124), ('kernel_error', 1), ('reply_error', 1),
                                        ('idle_first', 0), ('timeout', 1)])
def test_kernel_completion_protocol(cli, mode, status):
    result = cli('podrun.py', 'sleep 1' if mode == 'timeout' else 'true', mode)
    assert result.returncode == status, result.stderr + result.stdout
    assert 'unrelated request' not in result.stdout
