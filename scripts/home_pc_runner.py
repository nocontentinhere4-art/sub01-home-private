#!/usr/bin/env python3
"""Private headless runner for SUB-01's real PC, without the full brain backend.

It runs the same `home_computer.Computer` the house uses: the pinned
v86/WebAssembly x86 machine (`computer/worker.cjs`, `libv86.cjs`, `v86.wasm`)
booting the pinned Buildroot Linux image, with its persistent `computer.bin`
state. The guest has no host mounts and no network; input goes to its serial
console only. This runner never executes anything on the host.

HTTP on 127.0.0.1 only, every route except /healthz needs the existing operator
credential in `X-Admin-Token` (from --token-file or SUB01_ADMIN_TOKEN; never
logged). Contract (JSON):

  GET  /healthz                         -> {"ok": true}
  GET  /pc/state[?since=REV&wait=S]     -> computer view; with `since`, waits up
                                           to S (<=25) seconds for a newer revision
                                           or a privacy change
  POST /pc/input   {"input": str, "raw": bool=false}
                                        -> {"ok": bool, "revision": int}; the text
                                           goes to the guest serial console (a
                                           newline is appended unless raw), <=2000
  POST /pc/session {"active": bool}     -> first-person use keeps the VM running;
                                           send active=true at least every 60 s
  POST /pc/privacy {"active": bool}     -> bathroom privacy: state is blanked and
                                           input is refused with 409, including an
                                           input that was in flight when privacy began

The VM pauses itself when no session or recent input keeps it running.
"""

import argparse
import asyncio
import hmac
import json
import os
import signal
import sys
import time
from pathlib import Path

from aiohttp import web

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from home_computer import Computer  # noqa: E402

LOOPBACK = {"127.0.0.1", "::1", "localhost"}
SESSION_SECONDS = 60
MAX_WAIT = 25
MIN_TOKEN = 12


class PCRunner:
    def __init__(self, computer, token, clock=time.monotonic):
        if not isinstance(token, str) or len(token) < MIN_TOKEN:
            raise ValueError("An operator credential of at least 12 characters is required")
        self.computer = computer
        self._token = token.encode()
        self.clock = clock
        self.privacy = False
        self.privacy_epoch = 0
        self.session_until = 0.0
        self.changed = asyncio.Event()

    def authorized(self, request):
        supplied = request.headers.get("X-Admin-Token", "").encode()
        return hmac.compare_digest(supplied, self._token)

    def view(self):
        view = self.computer.view()
        if self.privacy:
            return {"status": view.get("status"), "ready": view.get("ready"), "paused": True,
                    "output": "", "last_command": None, "revision": None, "privacy": True}
        return {**view, "privacy": False, "session": self.clock() < self.session_until}

    def notify(self):
        self.changed.set()
        self.changed = asyncio.Event()

    async def set_privacy(self, active):
        if bool(active) != self.privacy:
            self.privacy = bool(active)
            self.privacy_epoch += 1
            if self.privacy and self.computer.ready and not self.computer.paused:
                if await self.computer.send({"type": "pause"}):
                    self.computer.paused = True
            self.notify()

    async def set_session(self, active):
        self.session_until = self.clock() + SESSION_SECONDS if active else 0.0
        if active and not self.privacy and self.computer.ready and self.computer.paused:
            if await self.computer.send({"type": "resume"}):
                self.computer.paused = False
        self.notify()

    async def input(self, text):
        """Returns the response or None when privacy refuses it (also mid-flight)."""
        if self.privacy:
            return None
        epoch = self.privacy_epoch
        ok = await self.computer.input(text)
        if self.privacy or epoch != self.privacy_epoch:
            return None
        return {"ok": bool(ok), "revision": getattr(self.computer, "revision", None)}

    async def idle_step(self):
        c = self.computer
        busy = self.clock() < max(self.session_until, getattr(c, "input_until", 0.0))
        if c.ready and not c.paused and (self.privacy or not busy):
            if await c.send({"type": "pause"}):
                c.paused = True

    async def wait_for_change(self, since, wait):
        deadline = self.clock() + wait
        epoch = self.privacy_epoch
        while True:
            revision = getattr(self.computer, "revision", None)
            if self.privacy_epoch != epoch or (not self.privacy and revision != since):
                return
            remaining = deadline - self.clock()
            if remaining <= 0:
                return
            try:
                await asyncio.wait_for(self.changed.wait(), min(remaining, 0.25))
            except asyncio.TimeoutError:
                pass


async def read_json(request):
    if request.content_length is not None and request.content_length > 4096:
        raise web.HTTPRequestEntityTooLarge(max_size=4096, actual_size=request.content_length)
    raw = await request.content.read(4097)
    if len(raw) > 4096:
        raise web.HTTPRequestEntityTooLarge(max_size=4096, actual_size=len(raw))
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise web.HTTPBadRequest(text="Invalid JSON")
    if not isinstance(data, dict):
        raise web.HTTPBadRequest(text="Expected object")
    return data


def create_app(runner):
    no_store = {"Cache-Control": "no-store"}

    @web.middleware
    async def guard(request, handler):
        if request.path != "/healthz" and not runner.authorized(request):
            raise web.HTTPForbidden(text="Operator authentication required")
        return await handler(request)

    async def healthz(request):
        return web.json_response({"ok": True}, headers=no_store)

    async def state(request):
        since = request.query.get("since")
        if since is not None:
            try:
                since = int(since)
                wait = min(MAX_WAIT, max(0.0, float(request.query.get("wait", MAX_WAIT))))
            except ValueError:
                raise web.HTTPBadRequest(text="Invalid since/wait")
            await runner.wait_for_change(since, wait)
        return web.json_response(runner.view(), headers=no_store)  # privacy read after waiting

    async def command(request):
        data = await read_json(request)
        text, raw = data.get("input"), data.get("raw", False)
        if not isinstance(text, str) or not isinstance(raw, bool) or len(text) > 2000:
            raise web.HTTPBadRequest(text="Input must be text of at most 2000 characters")
        if runner.privacy:
            raise web.HTTPConflict(text="Bathroom privacy is active")
        result = await runner.input(text if raw else text + "\n")
        if result is None:
            raise web.HTTPConflict(text="Bathroom privacy is active")
        return web.json_response(result, headers=no_store)

    def flag(data):
        if not isinstance(data.get("active"), bool):
            raise web.HTTPBadRequest(text="Expected active boolean")
        return data["active"]

    async def session(request):
        active = flag(await read_json(request))
        if active and runner.privacy:
            raise web.HTTPConflict(text="Bathroom privacy is active")
        await runner.set_session(active)
        return web.json_response(runner.view(), headers=no_store)

    async def privacy(request):
        await runner.set_privacy(flag(await read_json(request)))
        return web.json_response(runner.view(), headers=no_store)

    app = web.Application(middlewares=[guard], client_max_size=4096)
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/pc/state", state)
    app.router.add_post("/pc/input", command)
    app.router.add_post("/pc/session", session)
    app.router.add_post("/pc/privacy", privacy)
    return app


def load_token(token_file):
    if token_file:
        return Path(token_file).read_text().strip()
    return os.environ.get("SUB01_ADMIN_TOKEN", "").strip()


async def serve(args):
    computer = Computer(Path(args.data_dir))
    runner = PCRunner(computer, load_token(args.token_file))
    vm = asyncio.create_task(computer.run())
    app = create_app(runner)
    site_runner = web.AppRunner(app, access_log=None)  # request lines are not logged
    await site_runner.setup()
    await web.TCPSite(site_runner, args.host, args.port).start()
    print(f"SUB-01 PC runner on http://{args.host}:{args.port} (v86 Buildroot guest, state in {args.data_dir})", flush=True)
    stop = asyncio.Event()
    for name in ("SIGINT", "SIGTERM"):
        try:
            asyncio.get_running_loop().add_signal_handler(getattr(signal, name), stop.set)
        except (NotImplementedError, AttributeError):
            pass
    revision = None
    try:
        while not vm.done() and not stop.is_set():
            await runner.idle_step()
            if getattr(computer, "revision", None) != revision:
                revision = computer.revision
                runner.notify()
            await asyncio.sleep(0.1)
        if vm.done():
            vm.result()
    finally:
        await site_runner.cleanup()
        if not vm.done():
            vm.cancel()  # Computer.run() then asks the worker to save its state and shut down
            try:
                await vm
            except asyncio.CancelledError:
                pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8810)
    parser.add_argument("--data-dir", required=True, help="private runtime directory (outside Git)")
    parser.add_argument("--token-file", help="file holding the existing operator credential")
    args = parser.parse_args(argv)
    if args.host not in LOOPBACK:
        parser.error("the PC runner binds only to loopback")
    if not load_token(args.token_file) or len(load_token(args.token_file)) < MIN_TOKEN:
        parser.error("set SUB01_ADMIN_TOKEN or --token-file (at least 12 characters)")
    data = Path(args.data_dir).resolve()
    if data == ROOT or ROOT in data.parents:
        parser.error("keep runtime data outside the repository")
    data.mkdir(parents=True, exist_ok=True)
    try:
        asyncio.run(serve(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
