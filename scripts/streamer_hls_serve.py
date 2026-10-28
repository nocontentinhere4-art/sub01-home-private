#!/usr/bin/env python3
"""Serve the director's HLS directory (live.m3u8 + segments) on 127.0.0.1:8839, for local tests only.

Supervised by scripts/streamer_up.py as the `hls` service (or run by hand). Not public: it binds loopback only and is
never exposed without the owner's request (anything on the same machine, the agent's Chromium included, can read it
while it runs). The playlist goes out with no-cache headers, segments may be cached briefly; only playlist/segment names
in the directory itself are served, no listing. GET /healthz -> {"ok": true, "playlist": bool, "playlist_age_s"} (no
paths, no names): the supervisor's health check.
"""
import argparse
import re
import time
from pathlib import Path

from aiohttp import web

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.(m3u8|ts|m4s|mp4)$")
TYPES = {"m3u8": "application/vnd.apple.mpegurl", "ts": "video/mp2t", "m4s": "video/iso.segment", "mp4": "video/mp4"}
NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}
PLAYLIST = "live.m3u8"


def create_app(hls_dir, clock=time.time):
    root = Path(hls_dir).resolve()

    async def healthz(request):
        try:
            age = round(max(0.0, clock() - (root / PLAYLIST).stat().st_mtime), 1)
        except OSError:
            age = None
        return web.json_response({"ok": True, "playlist": age is not None, "playlist_age_s": age},
                                 headers={"Cache-Control": "no-store"})

    async def serve_file(request):
        name = request.match_info["name"]
        match = NAME.match(name)
        path = root / name
        if not match or path.resolve().parent != root or not path.is_file():
            raise web.HTTPNotFound()
        kind = match.group(1)
        if kind == "m3u8":                       # small, replaced atomically by the muxer: read it whole
            return web.Response(body=path.read_bytes(), headers={"Content-Type": TYPES[kind], **NO_CACHE})
        return web.FileResponse(path, headers={"Content-Type": TYPES[kind], "Cache-Control": "max-age=60"})

    app = web.Application()
    app.router.add_get("/healthz", healthz)      # before /{name}: a static route, never a file name (no extension)
    app.router.add_get("/{name}", serve_file)
    return app


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("hls_dir", help="the director's --hls-dir")
    p.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1", "::1", "localhost"))
    p.add_argument("--port", type=int, default=8839)
    args = p.parse_args(argv)
    web.run_app(create_app(args.hls_dir), host=args.host, port=args.port, access_log=None)


if __name__ == "__main__":
    main()
