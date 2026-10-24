"""Run one shell command on the pod through a short-lived Jupyter kernel (no terminal, no file written there).
usage: podrun.py pods.json POD_ID 'shell command'. The Jupyter token is masked from the output."""
import asyncio
import datetime
import json
import ssl
import sys
import uuid

import aiohttp

POD, COMMAND = sys.argv[2], sys.argv[3]
pods = json.load(open(sys.argv[1]))
TOKEN = [p for p in pods if p["id"] == POD][0]["env"]["JUPYTER_PASSWORD"]
BASE = f"https://{POD}-8888.proxy.runpod.net"
CODE = ("import subprocess\n"
        "r = subprocess.run(['bash', '-lc', %r], capture_output=True, text=True, timeout=240)\n"
        "print(r.stdout); print(r.stderr[-3000:])" % COMMAND)


async def main():
    ctx = ssl.create_default_context(cafile="/root/.ccr/ca-bundle.crt")
    async with aiohttp.ClientSession(trust_env=True, headers={"Authorization": "token " + TOKEN}) as s:
        async with s.post(BASE + "/api/kernels", json={"name": "python3"}, ssl=ctx) as r:
            kernel = await r.json()
        kid = kernel["id"]
        try:
            sid = uuid.uuid4().hex
            async with s.ws_connect(f"{BASE}/api/kernels/{kid}/channels?session_id={sid}", ssl=ctx, max_msg_size=0) as ws:
                mid = uuid.uuid4().hex
                await ws.send_str(json.dumps({
                    "header": {"msg_id": mid, "username": "probe", "session": sid, "msg_type": "execute_request",
                               "version": "5.3", "date": datetime.datetime.now(datetime.timezone.utc).isoformat()},
                    "parent_header": {}, "metadata": {}, "channel": "shell", "buffers": [],
                    "content": {"code": CODE, "silent": False, "store_history": False, "user_expressions": {},
                                "allow_stdin": False, "stop_on_error": True}}))
                out = []
                while True:
                    m = await asyncio.wait_for(ws.receive(), 300)
                    if m.type != aiohttp.WSMsgType.TEXT:
                        if m.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            out.append(f"\n[websocket {m.type}]")
                            break
                        continue
                    d = json.loads(m.data)
                    if d.get("parent_header", {}).get("msg_id") != mid:
                        continue
                    t = d["header"]["msg_type"]
                    if t == "stream":
                        out.append(d["content"]["text"])
                    elif t == "error":
                        out.append("\n".join(d["content"]["traceback"]))
                    elif t == "status" and d["content"]["execution_state"] == "idle":
                        break
                print("".join(out).replace(TOKEN, "<token>"))
        finally:
            async with s.delete(f"{BASE}/api/kernels/{kid}", ssl=ctx):
                pass


asyncio.run(main())
