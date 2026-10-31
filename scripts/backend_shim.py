#!/usr/bin/env python3
"""The minimum of SUB-01's home backend the streamer still calls (owner 10-30 Simli plan: no Unreal home, no life sim).

The agent reads the backend's chat inbox and marks lines it answered; the public relay falls back to the backend's
websocket when the agent refuses a chat line. Viewer chat now goes straight to the agent (relay -> agent /chat), so
this answers those calls with an empty inbox and an "offline" chat ack, on loopback only:

  GET  /api/home/streamer/chat?since=N   -> {"messages": [], "next": N}
  POST /api/home/streamer/said           -> {"ok": true}
  GET  /ws                               -> each {"type": "chat"} gets {"type": "chat_ack", "ok": false, "reason": "offline"}
  GET  /healthz                          -> {"ok": true}"""
import argparse

from aiohttp import web

LOOPBACK = {"127.0.0.1", "::1"}


def create_app():
    async def guard(request, handler):
        if request.remote not in LOOPBACK:
            raise web.HTTPForbidden()
        return await handler(request)

    async def chat(request):
        try:
            since = max(0, int(request.query.get("since", "0")))
        except ValueError:
            since = 0
        return web.json_response({"messages": [], "next": since})

    async def said(request):
        return web.json_response({"ok": True})

    async def ws(request):
        sock = web.WebSocketResponse(heartbeat=20)
        await sock.prepare(request)
        async for msg in sock:
            if msg.type == web.WSMsgType.TEXT and '"chat"' in msg.data:
                await sock.send_json({"type": "chat_ack", "ok": False, "reason": "offline"})
        return sock

    async def healthz(request):
        return web.json_response({"ok": True})

    app = web.Application(middlewares=[web.middleware(guard)])
    app.router.add_get("/api/home/streamer/chat", chat)
    app.router.add_post("/api/home/streamer/said", said)
    app.router.add_get("/ws", ws)
    app.router.add_get("/healthz", healthz)
    return app


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--port", type=int, default=8830)
    a = p.parse_args()
    web.run_app(create_app(), host="127.0.0.1", port=a.port, print=None)
