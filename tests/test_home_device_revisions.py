"""Optional WebSocket device revisions: change detection, cached frame identity, privacy masking."""

import asyncio
from types import SimpleNamespace

import home_api
from home_api import device_revisions
from home_computer import Computer
from home_minecraft import MinecraftConsole, frame_tag
from tests.test_home_api import client


def test_computer_revision_counts_equal_length_changes_not_repeats(tmp_path):
    c = Computer(tmp_path)
    c.output = "ls /\nbin"
    r = c.revision
    c.output = "ls /\nbin"
    assert c.revision == r, "assigning the same value is not a change"
    c.output = "ls /\nusr"
    assert c.revision == r + 1, "an equal-length replacement must register"
    c.paused = not c.paused
    c.last_command = "date"
    assert c.revision == r + 3 and c.view()["revision"] == c.revision


def test_minecraft_frame_tag_is_cached_at_assignment():
    console = object.__new__(MinecraftConsole)
    console.frame = b"jpeg-one"
    assert console.frame_tag == frame_tag(b"jpeg-one")
    console.frame = b"jpeg-one"
    assert console.frame_tag == frame_tag(b"jpeg-one")
    console.frame = b"jpeg-two"
    assert console.frame_tag == frame_tag(b"jpeg-two") != frame_tag(b"jpeg-one")
    console.frame = None
    assert console.frame_tag is None


def live_fixture():
    screens = {"desk": {"frame_id": "D:1"}, "phone": {"frame_id": "P:1"}}
    return SimpleNamespace(
        home=SimpleNamespace(console_game="minecraft"),
        computer=SimpleNamespace(revision=7),
        minecraft=SimpleNamespace(frame_tag="abc"),
        browser=object(),
        screen_status=lambda device: screens[device],
    ), screens


def test_device_revisions_unchanged_changed_and_restarting():
    live, screens = live_fixture()
    first = device_revisions(live, False)
    assert first == {"computer": 7, "desk": "D:1", "phone": "P:1", "minecraft": "abc", "console_game": "minecraft"}
    assert device_revisions(live, False) == first, "unchanged devices give an identical object"
    live.minecraft.frame_tag = "def"
    assert device_revisions(live, False)["minecraft"] == "def"
    screens["phone"] = {"device": "phone", "restarting": True, "frame_id": "hidden"}
    assert device_revisions(live, False)["phone"] is None
    live.browser = None
    assert device_revisions(live, False)["desk"] is None


def test_privacy_emits_only_the_flag():
    live, _ = live_fixture()
    assert device_revisions(live, True) == {"privacy": True}


def test_frame_etag_uses_cached_tag_and_privacy_masks_computer_revision():
    async def run():
        http, live = await client()
        live.minecraft = SimpleNamespace(enabled=True, frame=b"bytes", frame_tag="cached-tag", view=lambda: {})
        original = home_api.frame_tag
        home_api.frame_tag = lambda frame: (_ for _ in ()).throw(AssertionError("hashed per request"))
        try:
            response = await http.get("/api/home/minecraft/frame.jpg")
            assert response.headers["ETag"] == '"cached-tag"'
            live.computer.view = lambda: {"output": "secret", "revision": 9}
            view = live.home.view
            live.home.view = lambda *a, **k: {**view(*a, **k), "privacy": True}
            data = await (await http.get("/api/home/computer")).json()
            assert data["revision"] is None and data["output"] == ""
        finally:
            home_api.frame_tag = original
            await http.close()
    asyncio.run(run())
