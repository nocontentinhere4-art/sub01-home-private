"""Capture local brain network activity at 4 Hz for an offline forecasting check."""
import asyncio
import json
import time
from pathlib import Path
import aiohttp
import numpy as np

ROOT = Path(__file__).resolve().parents[1]

async def main():
    destination = ROOT / 'data/timesfm/live_trace.npz'
    destination.parent.mkdir(exist_ok=True)
    interval, duration = .25, 150
    rows, timestamps, names, last, origin, due = [], [], None, None, None, 0
    async with aiohttp.ClientSession() as http:
        async with http.ws_connect('http://127.0.0.1:8798/ws?feed=brain', heartbeat=20) as ws:
            async for message in ws:
                if message.type != aiohttp.WSMsgType.TEXT:
                    continue
                data = json.loads(message.data)
                if data.get('type') != 'tick' or not data.get('groups'):
                    continue
                now = time.monotonic()
                if origin is None:
                    origin = now; names = sorted(data['groups'])
                # Fill missed sample bins with the previous observation only.
                if now - origin - due > 1:
                    raise RuntimeError('Brain feed gap exceeds one second; retry the capture')
                while due <= now - origin:
                    values = last if last is not None else data['groups']
                    rows.append([values[n] for n in names]); timestamps.append(due)
                    due += interval
                last = data['groups']
                if due >= duration:
                    break
    np.savez_compressed(destination, ts=np.asarray(rows,dtype=np.float32),
        time=np.asarray(timestamps), names=np.asarray(names), tr=interval)
    print('Live brain captured:',len(rows),'samples;',len(names),'networks;',duration,'seconds',flush=True)

asyncio.run(main())
