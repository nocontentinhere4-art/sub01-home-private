"""Minecraft TV frames carry an identity so an unchanged (paused) picture costs an empty 304."""

import asyncio
from types import SimpleNamespace
from tests.test_home_api import client


def test_unchanged_frame_returns_empty_304_and_new_frame_downloads():
    async def run():
        http, live = await client()
        live.minecraft = SimpleNamespace(enabled=True, frame=b"frame-one", view=lambda: {"enabled": True})
        try:
            first = await http.get("/api/home/minecraft/frame.jpg")
            tag = first.headers["ETag"]
            assert first.status == 200 and await first.read() == b"frame-one"
            assert first.headers["Cache-Control"] == "no-store"
            same = await http.get("/api/home/minecraft/frame.jpg", headers={"If-None-Match": tag})
            assert same.status == 304 and await same.read() == b""
            live.minecraft.frame = b"frame-two"
            changed = await http.get("/api/home/minecraft/frame.jpg", headers={"If-None-Match": tag})
            assert changed.status == 200 and await changed.read() == b"frame-two"
            assert changed.headers["ETag"] != tag
            live.home.view = (lambda original: lambda *a, **k: {**original(*a, **k), "privacy": True})(live.home.view)
            hidden = await http.get("/api/home/minecraft/frame.jpg", headers={"If-None-Match": changed.headers["ETag"]})
            assert hidden.status == 409, "privacy wins over a matching validator"
        finally:
            await http.close()
    asyncio.run(run())
