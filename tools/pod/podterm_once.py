"""Run a bash snippet on the pod through the Jupyter terminals websocket (fallback when kernels cannot start).
usage: podterm.py pods.json POD_ID 'bash commands' [timeout_s]   (output between sentinels, ANSI stripped)"""
import asyncio, json, re, ssl, sys, time, uuid
import aiohttp

pods = json.load(open(sys.argv[1])); pod = [p for p in pods if p["id"] == sys.argv[2]][0]
TOKEN = pod["env"]["JUPYTER_PASSWORD"]; BASE = f"https://{sys.argv[2]}-8888.proxy.runpod.net"
_p = sys.argv[3]; CMD = open(_p).read(); __import__("os").remove(_p); LIMIT = float(sys.argv[4])
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|\r")


async def main():
    ctx = ssl.create_default_context(cafile="/root/.ccr/ca-bundle.crt") if __import__("os").path.exists("/root/.ccr/ca-bundle.crt") else None
    headers = {"Authorization": f"token {TOKEN}"}
    async with aiohttp.ClientSession(headers=headers) as s:
        async with s.post(BASE + "/api/terminals", ssl=ctx) as r:
            name = (await r.json())["name"]
        tag = uuid.uuid4().hex[:10]
        script = f"echo BEGIN{tag}; ( {CMD} ) 2>&1; echo; echo END{tag} $?\n"
        out, t0 = "", time.time()
        try:
            async with s.ws_connect(f"{BASE}/terminals/websocket/{name}", ssl=ctx, max_msg_size=0) as ws:
                await ws.send_str(json.dumps(["stdin", "stty -echo; export HISTFILE=/dev/null\n"]))
                await asyncio.sleep(0.5)
                await ws.send_str(json.dumps(["stdin", script]))
                while time.time() - t0 < LIMIT:
                    try:
                        msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    except asyncio.TimeoutError:
                        continue
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        break
                    data = json.loads(msg.data)
                    if data[0] == "stdout":
                        out += data[1]
                        if re.search(rf"END{tag} \d+", ANSI.sub("", out)):
                            break
        finally:
            async with s.delete(f"{BASE}/api/terminals/{name}", ssl=ctx):
                pass
    clean = ANSI.sub("", out)
    m = re.search(rf"BEGIN{tag}\n(.*?)END{tag} (\d+)", clean, re.S)
    if not m:
        print(clean[-4000:].replace(TOKEN, "***"))
        sys.exit(124)
    print(m.group(1).rstrip("\n").replace(TOKEN, "***"))
    sys.exit(int(m.group(2)))

asyncio.run(main())
