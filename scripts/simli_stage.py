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
/* owner 10-31 "il corpo si muova in modo piu naturale": a slow breath and sway while idle, a livelier small nod while
   the face is speaking (individual scale/rotate/translate compose with the layout's transform) */
@keyframes breathe{0%,100%{scale:1;translate:0 0;rotate:0deg}30%{scale:1.012;translate:2px -3px;rotate:.35deg}
  65%{scale:1.006;translate:-2px -1px;rotate:-.3deg}}
@keyframes talk{0%,100%{rotate:0deg;translate:0 0}25%{rotate:.7deg;translate:1px -2px}50%{rotate:-.4deg;translate:-1px 1px}
  75%{rotate:.5deg;translate:0 -3px}}
video{animation:breathe 7s ease-in-out infinite}
#v1{animation-delay:-2.5s}
video.talking{animation:talk 1.6s ease-in-out infinite}
/* owner 10-31 "circondato in stile halloween": a glowing pumpkin-orange frame, a cobweb, pumpkins and a bat around the
   face (drawn big: the director shows this window at about a third of its size). Off with --frame none. */
#hw{position:fixed;inset:0;pointer-events:none;display:none}
body.hw #hw{display:block}
#hw .edge{position:absolute;inset:0;border:16px solid #ff7a1a;border-radius:26px;
  box-shadow:inset 0 0 0 6px #2a0f3d,inset 0 0 38px 10px #ff7a1a88,0 0 0 4px #8b5cf6}
#hw svg{position:absolute}
#hw .web{top:6px;left:6px;width:190px;opacity:.85}
#hw .web2{top:6px;right:6px;width:150px;opacity:.7;transform:scaleX(-1)}
#hw .pk1{bottom:4px;left:14px;width:120px}
#hw .pk2{bottom:4px;right:16px;width:96px}
#hw .bat{top:30px;right:150px;width:120px;animation:hwbat 5s ease-in-out infinite}
@keyframes hwbat{50%{translate:-30px 12px}}
.tag{position:fixed;bottom:4%;font:700 26px/1 system-ui,sans-serif;color:#fff;text-shadow:0 2px 6px #000;display:none}
body.duo .tag{display:block}
#t0{left:6%}#t1{right:6%}
</style></head><body><div id="bg"></div>
<video id="v0" autoplay playsinline muted poster="/face.jpg"></video><audio id="a0" autoplay muted></audio>
<video id="v1" autoplay playsinline muted poster="/guest.jpg"></video><audio id="a1" autoplay muted></audio>
<div id="hw"><div class="edge"></div><svg viewBox="0 0 100 100" class="web" fill="none" stroke="#e9e4ff" stroke-width="1.6"><path d="M0 0l100 100M0 0l100 40M0 0l40 100M0 0l100 70M0 0l70 100"/><path d="M0 18q9 4 13 13 5-1 12 3 4-6 15-6"/><path d="M0 36q17 6 25 25 8-3 21 4 8-12 27-12"/><path d="M0 56q26 9 38 38 12-5 30 6 12-18 32-18"/></svg><svg viewBox="0 0 100 100" class="web2" fill="none" stroke="#e9e4ff" stroke-width="1.6"><path d="M0 0l100 100M0 0l100 40M0 0l40 100M0 0l100 70M0 0l70 100"/><path d="M0 18q9 4 13 13 5-1 12 3 4-6 15-6"/><path d="M0 36q17 6 25 25 8-3 21 4 8-12 27-12"/><path d="M0 56q26 9 38 38 12-5 30 6 12-18 32-18"/></svg><svg viewBox="0 0 64 28" class="bat"><path d="M32 8c2-3 3-4 4-7 1 3 1 5 0 7 6-1 10-5 13-8 0 6 5 9 11 9-4 2-7 6-8 11-3-3-7-4-11-2-2-3-6-4-9-4s-7 1-9 4c-4-2-8-1-11 2-1-5-4-9-8-11 6 0 11-3 11-9 3 3 7 7 13 8-1-2-1-4 0-7 1 3 2 4 4 7z" fill="#120b1c" stroke="#8b5cf6" stroke-width="1"/></svg><svg viewBox="0 0 64 56" class="pk1"><path d="M30 9c0-5 3-8 7-8l1 3c-3 0-4 2-4 5z" fill="#3f6212"/><ellipse cx="18" cy="32" rx="14" ry="20" fill="#e2580b"/><ellipse cx="46" cy="32" rx="14" ry="20" fill="#e2580b"/><ellipse cx="32" cy="32" rx="15" ry="22" fill="#ff7a1a"/><path d="M18 27l6-6 6 6zM34 27l6-6 6 6z" fill="#ffd166"/><path d="M17 37c5 7 25 7 30 0l-4 1-3 3-3-3-4 3-4-3-3 3-3-3z" fill="#ffd166"/></svg><svg viewBox="0 0 64 56" class="pk2"><path d="M30 9c0-5 3-8 7-8l1 3c-3 0-4 2-4 5z" fill="#3f6212"/><ellipse cx="18" cy="32" rx="14" ry="20" fill="#e2580b"/><ellipse cx="46" cy="32" rx="14" ry="20" fill="#e2580b"/><ellipse cx="32" cy="32" rx="15" ry="22" fill="#ff7a1a"/><path d="M18 27l6-6 6 6zM34 27l6-6 6 6z" fill="#ffd166"/><path d="M17 37c5 7 25 7 30 0l-4 1-3 3-3-3-4 3-4-3-3 3-3-3z" fill="#ffd166"/></svg></div>
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
    const s16 = new Int16Array(pcm.buffer, pcm.byteOffset, pcm.length >> 1);   // speaking: a nod, else the idle breath
    let sum = 0; for (let i = 0; i < s16.length; i += 4) sum += Math.abs(s16[i]);
    const loud = s16.length && sum / (s16.length / 4) > 600, f = faces[who] || faces[0];
    if (loud) { f.video.classList.add("talking"); clearTimeout(f.quiet);
      f.quiet = setTimeout(() => f.video.classList.remove("talking"), 700); }
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
      document.body.classList.toggle("hw", c.frame === "halloween");
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
        return web.json_response({"guest": on, "guest_name": args.guest_name if on else "", "frame": args.frame},
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
    p.add_argument("--frame", default="none", choices=("none", "halloween"), help="decoration around the face")
    p.add_argument("--session-s", type=int, default=3600, help="Simli maxSessionLength; the page reconnects after it")
    p.add_argument("--idle-s", type=int, default=600, help="Simli maxIdleTime (the audio feed is continuous anyway)")
    args = p.parse_args(argv)
    if args.host not in LOOPBACK:
        p.error("the stage binds only to loopback")
    web.run_app(create_app(args), host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
