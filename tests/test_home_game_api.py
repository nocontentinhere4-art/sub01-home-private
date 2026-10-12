import asyncio
from types import SimpleNamespace
from tests.test_home_api import client

def test_game_selection_is_authenticated_and_frames_are_real_only():
    async def run():
        http, live = await client()
        try:
            response = await http.post("/api/home/game", json={"game": "minecraft"})
            assert response.status == 403
            headers = {"X-Admin-Token": "test"}
            response = await http.post("/api/home/game", json={"game": "minecraft"}, headers=headers)
            assert response.status == 409
            assert (await http.get("/api/home/minecraft/frame.jpg")).status == 404
            live.minecraft = SimpleNamespace(enabled=True, frame=b"real-frame-bytes")
            response = await http.post("/api/home/game", json={"game": "minecraft"}, headers=headers)
            assert response.status == 200 and live.home.console_game == "minecraft"
            response = await http.get("/api/home/minecraft/frame.jpg")
            assert response.status == 200 and await response.read() == b"real-frame-bytes"
            assert response.headers["Cache-Control"] == "no-store"
        finally:
            await http.close()
    asyncio.run(run())
