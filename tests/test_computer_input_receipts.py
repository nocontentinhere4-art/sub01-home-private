"""Correlated existing-worker receipts, including spoof/cancel/timeout failure."""
import asyncio
import json
from types import SimpleNamespace
from computer.input_receipts import InputReceipts, native_receipt
from home_computer import Computer
import pytest

NATIVE = {"input_id": 17, "generation": 4}

def run(f):
    return asyncio.run(f())


def test_ack_correlates_server_nonce_exact_worker_generation_and_level():
    async def body():
        p = object(); other = object(); receipts = InputReceipts(capacity=1)
        identifier, wire, future = receipts.begin(p, NATIVE, 'GuestKeyboardInjected')
        assert identifier != str(NATIVE['input_id']) and len(identifier) == 32
        assert receipts.begin(p, NATIVE, 'GuestKeyboardInjected') is None
        ack = {'type': 'graphical-input-ack', 'id': identifier, 'generation': wire['generation'],
               'ok': True, 'level': 'GuestKeyboardInjected', 'started_ms': 10, 'finished_ms': 50}
        assert not receipts.complete({**ack, 'id': '0'*32}, p)
        assert not receipts.complete(ack, other)
        assert not receipts.complete({**ack, 'generation': wire['generation']+1}, p)
        assert not receipts.complete({**ack, 'started_ms': float('nan')}, p)
        assert not receipts.complete({**ack, 'finished_ms': 9}, p)
        assert not future.done()
        assert receipts.complete(ack, p)
        result = await future
        assert result['ok'] and result['ack_level'] == 'GuestKeyboardInjected'
        assert result['native_receipt'] == NATIVE
        assert not receipts.complete(ack, p)  # exact ACK cannot be replayed
        identifier, wire, future = receipts.begin(p, NATIVE, 'GuestKeyboardInjected')
        assert receipts.complete({**ack, 'id': identifier, 'generation': wire['generation'], 'level': 'GuestMouseInjected'}, p)
        assert not (await future)['ok']  # wrong operation never becomes a key ACK
    run(body)


def test_cancel_generation_invalidates_waiter_and_late_ack_without_other_input():
    async def body():
        p = object(); receipts = InputReceipts()
        identifier, wire, future = receipts.begin(p, NATIVE, 'GuestKeyboardInjected')
        cancel = receipts.cancel_all()
        assert cancel == [{'type': 'graphical-input-cancel', 'id': identifier, 'generation': wire['generation']}]
        assert not (await future)['ok']
        assert not receipts.complete({'type': 'graphical-input-ack', **wire, 'ok': True,
                                     'level': 'GuestKeyboardInjected', 'started_ms': 1, 'finished_ms': 2}, p)
        assert not receipts.pending
        _, next_wire, _ = receipts.begin(p, NATIVE, 'GuestKeyboardInjected')
        assert next_wire['generation'] != wire['generation']
        receipts.cancel_all()
    run(body)


@pytest.mark.parametrize('value', [{}, {'input_id': True, 'generation': 1}, {'input_id': 0, 'generation': 1},
    {'input_id': 2**53, 'generation': 1}, {'input_id': 1, 'generation': 1, 'ack': True}])
def test_native_metadata_is_identity_only_not_authority(value):
    with pytest.raises(ValueError):
        native_receipt(value)


def test_computer_waits_for_actual_stdio_ack_not_pipe_drain(tmp_path, monkeypatch):
    monkeypatch.delenv('HOME_COMPUTER_ORIGIN', raising=False)
    async def body():
        c = Computer(tmp_path); c.display = {'available': True}; sent = []
        class Pipe:
            def write(self, payload):
                sent.append(json.loads(payload))
            async def drain(self):
                pass
        p = SimpleNamespace(returncode=None, stdin=Pipe()); c.process = p
        task = asyncio.create_task(c.graphical_input_receipt({'type': 'vga-keyboard', 'scancodes': [30,158]}, NATIVE))
        await asyncio.sleep(.01)
        assert not task.done()  # stdin drain is deliberately insufficient
        wire = sent[0]['_receipt']
        ack = {'type':'graphical-input-ack','id':wire['id'],'generation':wire['generation'],
               'ok':True,'level':'GuestKeyboardInjected','started_ms':10,'finished_ms':50}
        c.input_receipts.complete(ack, p)
        result = await task
        assert result['ok'] and result['native_receipt'] == NATIVE
        assert len(sent) == 1 and not c.input_receipts.pending
        # Focus loss cancels only this correlated request, not a broad key release.
        task = asyncio.create_task(c.graphical_input_receipt({'type':'vga-keyboard','scancodes':[48,176]}, NATIVE))
        await asyncio.sleep(.01); await c.cancel_graphical_receipts()
        assert not (await task)['ok']
        assert sent[-1]['type'] == 'graphical-input-cancel'
        assert 'scancodes' not in sent[-1] and 'pause' not in [x['type'] for x in sent]
    run(body)


def test_computer_timeout_is_bounded_and_cancels_only_exact_correlation(tmp_path, monkeypatch):
    monkeypatch.delenv('HOME_COMPUTER_ORIGIN', raising=False)
    async def body():
        c=Computer(tmp_path);c.display={'available': True};sent=[]
        class Pipe:
            def write(self, payload):sent.append(json.loads(payload))
            async def drain(self):pass
        c.process=SimpleNamespace(returncode=None,stdin=Pipe())
        result=await c.graphical_input_receipt({'type':'vga-keyboard','scancodes':[30,158]},NATIVE)
        assert result == {'ok': False} and len(sent)==2
        assert sent[1] == {'type':'graphical-input-cancel','id':sent[0]['_receipt']['id'],
                          'generation':sent[0]['_receipt']['generation']}
        assert not c.input_receipts.pending
    run(body)


def test_broken_pipe_before_drain_refuses_receipt_and_clears_stale_pixels(tmp_path, monkeypatch):
    monkeypatch.delenv('HOME_COMPUTER_ORIGIN', raising=False)
    async def body():
        c=Computer(tmp_path);c.display={'available': True};c.framebuffer_png=b'old pixels'
        class Pipe:
            def write(self, payload):raise BrokenPipeError()
        c.process=SimpleNamespace(returncode=None,stdin=Pipe())
        assert await c.graphical_input_receipt({'type':'vga-keyboard','scancodes':[30,158]},NATIVE)=={'ok': False}
        assert not c.input_receipts.pending and c.framebuffer_png is None
    run(body)
