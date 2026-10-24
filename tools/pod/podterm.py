"""Run a bash snippet on the pod through the Jupyter terminals websocket (fallback when kernels cannot start).
usage: podterm.py pods.json POD_ID 'bash commands' [timeout_s]   (output between sentinels, ANSI stripped)"""
import asyncio, json, re, ssl, sys, time, uuid
import aiohttp

pods = json.load(open(sys.argv[1])); pod = [p for p in pods if p["id"] == sys.argv[2]][0]
TOKEN = pod["env"]["JUPYTER_PASSWORD"]; BASE = f"https://{sys.argv[2]}-8888.proxy.runpod.net"
CMD, LIMIT = sys.argv[3], float(sys.argv[4]) if len(sys.argv) > 4 else 230.0
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|\r")


async def main():
    ctx = ssl.create_default_context(cafile="/root/.ccr/ca-bundle.crt") if __import__("os").path.exists("/root/.ccr/ca-bundle.crt") else None
    headers = {"Authorization": f"token {TOKEN}"}
    async with aiohttp.ClientSession(headers=headers) as s:
        async with s.post(BASE + "/api/terminals", ssl=ctx) as r:
            r.raise_for_status()
            name = (await r.json())["name"]
        tag = uuid.uuid4().hex[:10]
        # '$' also matches a partial receive buffer: require the actual newline after the status digits.
        end_pattern = re.compile(rf"^END{tag} ([0-9]+)\n", re.M)
        # Capture the command's status before printf (and keep here-doc terminators on their own line).
        script = (f"printf '\\nBEGIN{tag}\\n'; (\n{CMD}\n) 2>&1\n"
                  f"__sub01_rc=$?; printf '\\nEND{tag} %s\\n' \"$__sub01_rc\"\n")
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
                        if end_pattern.search(ANSI.sub("", out)):
                            break
        finally:
            async with s.delete(f"{BASE}/api/terminals/{name}", ssl=ctx) as r:
                r.raise_for_status()
    clean = ANSI.sub("", out)
    begin = re.search(rf"^BEGIN{tag}\n", clean, re.M)
    ends = list(end_pattern.finditer(clean))
    end = ends[0] if len(ends) == 1 else None
    if not begin or not end or begin.end() > end.start() or int(end.group(1)) > 255:
        print(clean[-4000:].replace(TOKEN, "***"))
        sys.exit(124)
    print(clean[begin.end():end.start()].rstrip("\n").replace(TOKEN, "***"))
    sys.exit(int(end.group(1)))

asyncio.run(main())
