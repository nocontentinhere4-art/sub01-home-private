"""The public relay (tools/pod/onpod/live_relay.py), owner 10-28: names in chat, the video queue and the Hype button
forwarded to the agent with the operator token, the queue and hype level in /status."""
import asyncio
import socket
import sys
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "pod" / "onpod"))
import live_relay as R  # noqa: E402

ORIGIN = {"Origin": R.ORIGIN, "Content-Type": "text/plain"}


def port_free(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def test_clean_nick_and_body_json():
    assert R.clean_nick(" Marco ") == "Marco" and R.clean_nick("SUB-01") == "" and R.clean_nick("a b") == ""
    assert R.body_json('{"nick":"Marco","text":"hi"}') == {"nick": "Marco", "text": "hi"}
    assert R.body_json("hello {there}") is None and R.body_json("{broken") is None and R.body_json("[1]") is None


@pytest.mark.skipif(not port_free(8836), reason="port 8836 busy (the agent's port)")
def test_chat_queue_hype_and_status_reach_the_fake_agent(tmp_path):
    seen = []

    async def agent_chat(request):
        seen.append(("chat", request.headers.get("X-Admin-Token"), await request.json()))
        return web.json_response({"ok": True})

    async def agent_queue(request):
        body = await request.json()
        seen.append(("queue", request.headers.get("X-Admin-Token"), body))
        ok = "youtu" in body["url"]
        return web.json_response({"ok": ok, "reason": "added" if ok else "bad_link", "position": 1 if ok else None},
                                 status=200 if ok else 409)

    async def agent_hype(request):
        seen.append(("hype", request.headers.get("X-Admin-Token"), await request.json()))
        return web.json_response({"ok": True, "event": "shout", "level": 0.2, "train": False})

    async def agent_state(request):
        return web.json_response({"queue": {"now": None, "waiting": [{"nick": "Marco", "id": "dQw4w9WgXcQ"}]},
                                  "hype": {"level": 0.2, "train": False}})

    async def body():
        fake = web.Application()
        fake.router.add_post("/chat", agent_chat)
        fake.router.add_post("/queue", agent_queue)
        fake.router.add_post("/hype", agent_hype)
        fake.router.add_get("/viewer_state", agent_state)
        runner = web.AppRunner(fake)
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", 8836).start()
        token = tmp_path / "token"
        token.write_text("operator-secret-123\n")
        (tmp_path / "hls").mkdir()
        app = R.create_app(tmp_path / "hls", tmp_path / "STOP", token)
        async with TestClient(TestServer(app)) as client:
            r = await client.post("/chat", data='{"nick":"Marco","text":"yo SUB-01"}', headers=ORIGIN)
            assert r.status == 200 and seen[-1][:2] == ("chat", "operator-secret-123") and {k: v for k, v in seen[-1][2].items() if k != "voter"} == {"text": "yo SUB-01", "nick": "Marco"}
            assert len(seen[-1][2]["voter"]) == 16                                # a salted hash of the connection, never the IP
            r = await client.post("/chat", data='{"nick":"admin","text":"hi"}', headers=dict(ORIGIN, **{"CF-Connecting-IP": "2"}))
            assert seen[-1][2]["nick"] == "viewer"                                    # a reserved name: anonymous
            r = await client.post("/queue", data='{"nick":"Marco","url":"https://youtu.be/dQw4w9WgXcQ"}', headers=ORIGIN)
            assert r.status == 200 and (await r.json())["code"] == "added" and seen[-1][0] == "queue"
            r = await client.post("/queue", data='{"nick":"Marco","url":"https://youtu.be/dQw4w9WgXcQ"}', headers=ORIGIN)
            assert r.status == 429                                                     # one per 30 s per IP
            r = await client.post("/queue", data='{"url":"https://example.org"}', headers=dict(ORIGIN, **{"CF-Connecting-IP": "9"}))
            assert r.status == 409 and "YouTube" in (await r.json())["why"]
            r = await client.post("/hype", data='{"nick":"Marco"}', headers=ORIGIN)
            assert r.status == 200 and (await r.json())["level"] == 0.2
            r = await client.post("/hype", data='{"nick":"Marco"}', headers={"Origin": "https://evil.example", "Content-Type": "text/plain"})
            assert r.status == 403
            r = await client.get("/status", headers={"Origin": R.ORIGIN})
            st = await r.json()
            assert st["queue"]["waiting"][0]["nick"] == "Marco" and st["hype"]["level"] == 0.2 and st["watching"] == 1
            r = await client.get("/status", headers={"Origin": R.ORIGIN, "CF-Connecting-IP": "7"})
            assert (await r.json())["watching"] == 2                                   # two connections polling
            assert "operator-secret-123" not in await r.text()
        await runner.cleanup()
    asyncio.run(body())
