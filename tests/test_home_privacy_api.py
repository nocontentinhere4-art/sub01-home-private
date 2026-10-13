"""Bathroom privacy is enforced by the home API, not only by the page."""

import asyncio
from types import SimpleNamespace
from tests.test_home_api import client


def test_privacy_withholds_screen_pixels_terminal_text_and_guest_input():
    async def run():
        http, live = await client()
        live.minecraft = SimpleNamespace(enabled=True, frame=b"real-frame-bytes")
        original = live.home.view
        private = {"on": False}
        live.home.view = lambda *a, **k: {**original(*a, **k), "privacy": private["on"]}
        headers = {"X-Admin-Token": "test"}
        try:
            assert (await http.get("/api/home/minecraft/frame.jpg")).status == 200
            assert (await (await http.get("/api/home/computer")).json())["output"] == "guest only"
            private["on"] = True
            frame = await http.get("/api/home/minecraft/frame.jpg")
            assert frame.status == 409 and await frame.text() == "Bathroom privacy is active"
            for path in ("/api/home/computer", "/api/home"):
                data = await (await http.get(path)).json()
                view = data if path.endswith("computer") else data["computer"]
                assert view["output"] == "" and view["privacy"] is True
            blocked = await http.post("/api/home/computer", json={"input": "ls"}, headers=headers)
            assert blocked.status == 409 and live.computer.inputs == []
            private["on"] = False
            assert (await http.get("/api/home/minecraft/frame.jpg")).status == 200
            assert (await http.post("/api/home/computer", json={"input": "ls"}, headers=headers)).status == 200
            assert live.computer.inputs == ["ls\n"]
        finally:
            await http.close()
    asyncio.run(run())
