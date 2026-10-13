"""Follow-ups found by the native home-state bridge: /api/home without a browse
service, and the server's own route published in the home view."""

import asyncio

from home_world import HomeWorld
from tests.test_home_api import client


def test_home_state_answers_without_a_browse_service():
    async def run():
        http, live = await client()
        live.browser = None
        live.screen_status = lambda device: (_ for _ in ()).throw(AttributeError("browser is None"))
        try:
            response = await http.get("/api/home")
            assert response.status == 200
            data = await response.json()
            assert data["browser_screen"] is None and data["phone_browser_screen"] is None
        finally:
            await http.close()
    asyncio.run(run())


def test_view_publishes_the_server_route_and_masks_it_during_privacy():
    home = HomeWorld()
    life = {"activity": "sleep"}
    for _ in range(5):
        home.update(0.2, 0.2, life, {})
    assert home.path, "walking to bed has a planned route"
    assert home.view()["path"] == list(home.path)
    assert home.view(compact=True)["path"] == list(home.path)
    home.privacy = lambda: True
    assert home.view()["path"] == []
