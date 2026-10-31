#!/usr/bin/env python3
"""SUB-01's Simli stage (owner 10-30: "usiamo simli per ricreare sub-01 e teniamo il PC"): the talking face that replaces
the Unreal body. A Chrome window on the stage display (:99, title SUB01-STAGE) opens this page; the director grabs that
window as its main view (`--game-source x11 --window-prefix SUB01-STAGE`) and shows it as the picture-in-picture over
the PC (layout `desktop`).

Audio path: voice_server.py speaks as before (its FIFO, delayed by --simli-lead-s, is still the stream's voice) and
sends the same audio, at real-time pace, to POST /pcm here (PCM16 mono 16 kHz, continuous: silence too). This server
hands it to the page over /ws and the page feeds it to the Simli client, so the lips move with what is heard. The page's
own Simli audio is muted. When the Simli session ends (length or idle limit, a network drop) the page asks /token for a
new one and reconnects; until it is live it shows the still face (/face.jpg).

Loopback only:
  GET  /            the stage page                  GET /face.jpg, /bg.jpg   the still face and the room behind it
  POST /token       -> {"session_token"}            a Simli Compose token for the configured face (the key never leaves)
  GET  /ws          the page's audio feed (binary: 1 byte face 0 SUB-01 / 1 guest, then PCM)
  POST /pcm[?face=V] body: PCM16 mono 16 kHz        from voice_server.py, broadcast to the pages (V = a guest's voice)
  GET  /config      {"guest", "guest_name"}         guest mode: a second Simli face beside SUB-01 while --guest-switch
                                                    exists (owner 10-31: Kimchi as his AI avatar on the Halloween show)
  POST /state       {"state", "detail"}             the page reports connecting / live / error
  GET  /healthz     {"ok", "page", "state", "pcm_age_s", "sessions"}

The Simli key is read from --key-file and never logged or sent to the page."""
import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

import aiohttp
from aiohttp import web

SIMLI_TOKEN_URL = "https://api.simli.ai/compose/token"
LOOPBACK = {"127.0.0.1", "::1"}
PCM_MAX = 64_000                       # one POST carries ~0.1 s (3200 bytes); anything this big is a mistake
FACE_RE = re.compile(r"[A-Za-z0-9-]{8,64}")

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>SUB01-STAGE</title>
<style>
html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#0b0d10}
#bg{position:fixed;inset:-40px;background:url(/bg.jpg) center/cover;filter:blur(22px) brightness(.8)}
video{position:fixed;top:0;height:100%;aspect-ratio:1/1;object-fit:cover;transition:left .4s,height .4s,top .4s;
  -webkit-mask-image:linear-gradient(90deg,transparent 0,#000 10%,#000 90%,transparent 100%)}
#v0{left:50%;transform:translateX(-50%)}
body.duo video{top:10%;height:80%;transform:none}
body.duo #v0{left:2%}
#v1{display:none;right:2%}
body.duo #v1{display:block}
.tag{position:fixed;bottom:4%;font:700 26px/1 system-ui,sans-serif;color:#fff;text-shadow:0 2px 6px #000;display:none}
body.duo .tag{display:block}
#t0{left:6%}#t1{right:6%}
</style></head><body><div id="bg"></div>
<video id="v0" autoplay playsinline muted poster="/face.jpg"></video><audio id="a0" autoplay muted></audio>
<video id="v1" autoplay playsinline muted poster="/guest.jpg"></video><audio id="a1" autoplay muted></audio>
<span class="tag" id="t0">SUB-01</span><span class="tag" id="t1"></span>
<script type="module">
import { SimliClient } from "https://cdn.jsdelivr.net/npm/simli-client@3.2.0/+esm";
const faces = [{id: 0, key: "", video: v0, audio: a0, client: null, live: false},
               {id: 1, key: "guest", video: v1, audio: a1, client: null, live: false, wanted: false}];
const report = (state, detail) => fetch("/state", {method: "POST", headers: {"Content-Type": "application/json"},
  body: JSON.stringify({state, detail: String(detail || "").slice(0, 200)})}).catch(() => {});
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
function send(f, data) { if (f.live && f.client) { try { f.client.sendAudioData(data); } catch (_) {} } }
function feed() {          // the voice server's audio; first byte = whose face (0 SUB-01, 1 the guest), the other gets silence
  const ws = new WebSocket(`ws://${location.host}/ws`); ws.binaryType = "arraybuffer";
  ws.onmessage = (e) => {
    const all = new Uint8Array(e.data), who = all[0], pcm = all.subarray(1);
    for (const f of faces) send(f, f.id === who ? pcm : new Uint8Array(pcm.length));
  };
  ws.onclose = () => setTimeout(feed, 1000);
}
async function session(f) {
  report((f.key || "main") + ":connecting");
  const r = await fetch("/token" + (f.key ? "?face=" + f.key : ""), {method: "POST"});
  const d = await r.json().catch(() => ({}));
  if (!r.ok || !d.session_token) throw new Error(d.why || ("token " + r.status));
  const c = new SimliClient(d.session_token, f.video, f.audio, null);
  const ended = new Promise(res => c.on("stop", res));
  await Promise.race([c.start(), sleep(30000).then(() => { throw new Error("start timeout"); })]);
  f.client = c; f.live = true; f.audio.muted = true; report((f.key || "main") + ":live");
  await Promise.race([ended, (async () => { while (f.key === "" || f.wanted) await sleep(1000); try { c.close ? c.close() : c.stop(); } catch (_) {} })()]);
  f.live = false; f.client = null; report((f.key || "main") + ":ended");
}
async function loop(f) {
  let backoff = 2000;
  for (;;) {
    if (f.key && !f.wanted) { await sleep(1000); continue; }
    const t0 = Date.now();
    try { await session(f); } catch (e) { f.live = false; f.client = null; report((f.key || "main") + ":error", e && e.message); }
    if (Date.now() - t0 > 60000) backoff = 2000;
    if (f.key && !f.wanted) continue;
    await sleep(backoff); backoff = Math.min(backoff * 2, 60000);
  }
}
async function config() {               // the guest is on while the server says so (<streamer-dir>/guest-on)
  for (;;) {
    try { const c = await (await fetch("/config")).json();
      faces[1].wanted = !!c.guest; document.body.classList.toggle("duo", !!c.guest); t1.textContent = c.guest_name || "";
    } catch (_) {}
    await sleep(3000);
  }
}
feed(); config(); loop(faces[0]); loop(faces[1]);
</script></body></html>"""


def loopback_only(handler):
    async def wrapped(request):
        if request.remote not in LOOPBACK:
            raise web.HTTPForbidden()
        return await handler(request)
    return wrapped


def create_app(args):
    state = {"page": None, "detail": "", "page_at": 0.0, "pcm_at": 0.0, "sessions": 0, "tokens": 0}
    pages = set()
    face_id = args.face_id
    if not FACE_RE.fullmatch(face_id or ""):
        raise SystemExit("bad --face-id (copy it from app.simli.com)")

    def read_key():
        try:
            return Path(args.key_file).read_text().strip()
        except OSError:
            return ""

    def guest_on():
        return bool(args.guest_switch) and Path(args.guest_switch).exists()

    def guest_face():
        try:
            fid = Path(args.guest_face_file).read_text().strip() if args.guest_face_file else ""
        except OSError:
            return ""
        return fid if FACE_RE.fullmatch(fid) else ""

    async def config(request):
        on = guest_on() and bool(guest_face())
        return web.json_response({"guest": on, "guest_name": args.guest_name if on else ""},
                                 headers={"Cache-Control": "no-store"})

    async def index(request):
        return web.Response(text=PAGE, content_type="text/html", headers={"Cache-Control": "no-store"})

    def image(path):
        async def handler(request):
            if not path or not Path(path).is_file():
                raise web.HTTPNotFound()
            return web.FileResponse(path, headers={"Cache-Control": "no-store"})
        return handler

    async def token(request):
        key = read_key()
        if not key:
            return web.json_response({"why": "no Simli key"}, status=503)
        guest = request.query.get("face") == "guest"
        fid = guest_face() if guest else face_id
        if not fid:
            return web.json_response({"why": "no guest face"}, status=503)
        body = {"faceId": fid, "maxSessionLength": args.session_s, "maxIdleTime": args.idle_s}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
                async with s.post(SIMLI_TOKEN_URL, json=body, headers={"x-simli-api-key": key}) as r:
                    data = await r.json(content_type=None)
                    status = r.status
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            log(f"token request failed: {type(exc).__name__}")
            return web.json_response({"why": "Simli unreachable"}, status=502)
        tok = data.get("session_token") if isinstance(data, dict) else None
        if status != 200 or not tok:
            detail = str(data.get("detail") or data.get("error") or "")[:160] if isinstance(data, dict) else ""
            log(f"token refused: HTTP {status} {detail}")
            return web.json_response({"why": f"Simli HTTP {status}"}, status=502)
        state["tokens"] += 1
        return web.json_response({"session_token": tok})

    async def page_ws(request):
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        pages.add(ws)
        try:
            async for _ in ws:
                pass
        finally:
            pages.discard(ws)
        return ws

    async def pcm(request):
        data = await request.read()
        if not data or len(data) > PCM_MAX or len(data) % 2:
            raise web.HTTPBadRequest()
        state["pcm_at"] = time.time()
        frame = bytes([1 if request.query.get("face") == args.guest_voice else 0]) + data
        for ws in list(pages):
            try:
                await ws.send_bytes(frame)
            except (ConnectionError, RuntimeError):
                pages.discard(ws)
        return web.Response(status=204)

    async def page_state(request):
        try:
            d = await request.json()
        except ValueError:
            raise web.HTTPBadRequest()
        new = str(d.get("state") or "")[:20]
        if new == "live":
            state["sessions"] += 1
        if new != state["page"] or new == "error":
            log(f"page {new} {str(d.get('detail') or '')[:200]}".rstrip())
        state.update(page=new, detail=str(d.get("detail") or "")[:200], page_at=time.time())
        return web.json_response({"ok": True})

    async def healthz(request):
        now = time.time()
        return web.json_response({"ok": True, "page": len(pages), "state": state["page"], "detail": state["detail"],
                                  "pcm_age_s": round(now - state["pcm_at"], 1) if state["pcm_at"] else None,
                                  "sessions": state["sessions"], "tokens": state["tokens"]})

    app = web.Application(client_max_size=PCM_MAX + 1024)
    app.router.add_get("/", loopback_only(index))
    app.router.add_get("/face.jpg", loopback_only(image(args.face_image)))
    app.router.add_get("/bg.jpg", loopback_only(image(args.bg_image or args.face_image)))
    app.router.add_get("/guest.jpg", loopback_only(image(args.guest_image)))
    app.router.add_get("/config", loopback_only(config))
    app.router.add_post("/token", loopback_only(token))
    app.router.add_get("/ws", loopback_only(page_ws))
    app.router.add_post("/pcm", loopback_only(pcm))
    app.router.add_post("/state", loopback_only(page_state))
    app.router.add_get("/healthz", healthz)
    return app


def log(message):
    print(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "simli stage:", message, file=sys.stderr, flush=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8842)
    p.add_argument("--key-file", required=True, help="file holding the Simli API key")
    p.add_argument("--face-id", required=True, help="the Simli face (app.simli.com)")
    p.add_argument("--face-image", help="the still face shown until the session is live")
    p.add_argument("--bg-image", help="the room behind the face (default: the face image, blurred)")
    p.add_argument("--guest-switch", help="the guest's face is on while this file exists (owner 10-31: Kimchi as guest)")
    p.add_argument("--guest-face-file", help="file holding the guest's Simli face id")
    p.add_argument("--guest-voice", default="kimchi", help="the voice name whose audio goes to the guest's face")
    p.add_argument("--guest-name", default="KIMCHI")
    p.add_argument("--guest-image", help="the guest's still face, shown until its session is live")
    p.add_argument("--session-s", type=int, default=3600, help="Simli maxSessionLength; the page reconnects after it")
    p.add_argument("--idle-s", type=int, default=600, help="Simli maxIdleTime (the audio feed is continuous anyway)")
    args = p.parse_args(argv)
    if args.host not in LOOPBACK:
        p.error("the stage binds only to loopback")
    web.run_app(create_app(args), host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
