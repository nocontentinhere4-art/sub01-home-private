"""Home APIs: shared devices, bounded public Pong input, authenticated editing."""

import json
import math
import time
from collections import OrderedDict
from pathlib import Path
from aiohttp import web
from life import ACTIVITIES
from home_minecraft import frame_tag
import home_interactions as hi

HERE = Path(__file__).parent


DEVICE_KEYS = ("computer", "desk", "phone", "minecraft", "console_game")


def device_revisions(live, privacy):
    """Optional `devices` object for the private WebSocket home message: one
    identity per device so the page refreshes only on change. Older pages
    ignore it and keep polling. During privacy nothing but the flag is sent."""
    if privacy:
        return {"privacy": True}

    def screen(device):
        if not getattr(live, "browser", None) or not getattr(live, "screen_status", None):
            return None
        status = live.screen_status(device) or {}
        return None if status.get("restarting") else status.get("frame_id")

    console = getattr(live, "minecraft", None)
    return {
        "computer": getattr(getattr(live, "computer", None), "revision", None),
        "desk": screen("desk"),
        "phone": screen("phone"),
        "minecraft": getattr(console, "frame_tag", None) if console else None,
        "console_game": getattr(live.home, "console_game", None),
    }


def add_home_routes(app, live, admin_ok):
    inputs = OrderedDict()

    def enabled():
        if not live.home:
            raise web.HTTPNotFound(text="Home is not enabled")

    def private():
        # Bathroom privacy is enforced by the server too, not only by the
        # page: no screen pixels, terminal text or guest input while active.
        return bool(live.home.view().get("privacy"))

    def computer_view():
        view = live.computer.view()
        if private():
            view = {**view, "output": "", "last_command": None, "revision": None, "privacy": True}
        return view

    def operator(request):
        if not admin_ok(request):
            raise web.HTTPForbidden(text="Operator authentication required")

    async def body(request):
        if request.content_length is not None and request.content_length > 4096:
            raise web.HTTPRequestEntityTooLarge(
                max_size=4096, actual_size=request.content_length
            )
        chunks = []
        size = 0
        async for chunk in request.content.iter_chunked(4096):
            size += len(chunk)
            if size > 4096:
                raise web.HTTPRequestEntityTooLarge(max_size=4096, actual_size=size)
            chunks.append(chunk)
        try:
            b = json.loads(b"".join(chunks))
        except (ValueError, UnicodeDecodeError):
            raise web.HTTPBadRequest(text="Invalid JSON")
        if not isinstance(b, dict):
            raise web.HTTPBadRequest(text="Expected object")
        return b

    async def state(request):
        enabled()
        home = live.home.view()
        hidden = bool(home.get("privacy"))

        def screen(device):
            # No browse service (e.g. a local run without BROWSE): no screen,
            # instead of Live.screen_status failing on a missing browser.
            if not getattr(live, 'screen_status', None):
                return None
            # Same rule as the devices object: during privacy no frame id,
            # title or address of a screen, only the device and the flag.
            if hidden:
                return {"device": device, "privacy": True}
            return live.screen_status(device) if getattr(live, 'browser', None) else None

        minecraft = live.minecraft.view() if getattr(live, "minecraft", None) else {"enabled": False, "status": "disabled"}
        if hidden and getattr(live, "minecraft", None):
            minecraft = {**minecraft, "has_frame": False, "observation": None,
                         "events": [], "last_action": None, "privacy": True}
        return web.json_response(
            {
                "home": home,
                "computer": computer_view(),
                "browser": live.screens.public()["browser"] if getattr(live, "screens", None) else None,
                "browser_screen": screen('desk'),
                "phone_browser_screen": screen('phone'),
                "minecraft": minecraft,
                "life": live.life.snapshot(),
                "stage": live.engine.stage,
                "time": live.clock.now(),
            },
            headers={"Cache-Control": "no-store"},
        )

    async def computer(request):
        enabled()
        return web.json_response(
            computer_view(), headers={"Cache-Control": "no-store"}
        )

    async def command(request):
        enabled()
        operator(request)
        b = await body(request)
        text = b.get("input")
        if not isinstance(text, str) or len(text) > 2000:
            raise web.HTTPBadRequest(text="Input too long")
        if private():
            raise web.HTTPConflict(text="Bathroom privacy is active")
        return web.json_response({"ok": await live.computer.input(text + "\n")})

    async def navigate(request):
        enabled()
        operator(request)
        from browse import url_ok
        data = await body(request)
        url = data.get('url')
        device = data.get('device', 'desk')
        if not isinstance(url, str) or len(url) > 2048 or not url_ok(url) or device not in ('desk', 'phone'):
            raise web.HTTPBadRequest(text='Use a public web page address')
        if live.home.view()['privacy']:
            raise web.HTTPConflict(text='Bathroom privacy is active')
        if not getattr(live, 'browser', None):
            raise web.HTTPConflict(text='The browser is unavailable')
        status = await live.browser.navigate(device, url)
        if not status:
            raise web.HTTPConflict(text='Page unavailable or refused by the browser checks')
        await live.on_screen(status)
        if getattr(live, 'reader', None):
            live.reader.saw(status, live.clock.now())
        return web.json_response({'ok': True})

    async def note(request):
        enabled()
        operator(request)
        b = await body(request)
        if not isinstance(b.get("text"), str):
            raise web.HTTPBadRequest(text="Text required")
        ok = live.home.add_note(b["text"])
        await live.save_state()
        return web.json_response({"ok": ok})

    async def browser_action(request):
        enabled()
        operator(request)
        b = await body(request)
        if (b.get('device') not in ('desk', 'phone') or
                b.get('action') not in ('scroll_up', 'scroll_down', 'close_notice', 'back') or
                not isinstance(b.get('frame_id'), str) or not 1 <= len(b['frame_id']) <= 100):
            raise web.HTTPBadRequest(text='Invalid browser action')
        if live.home.view()['privacy']:
            raise web.HTTPConflict(text='Bathroom privacy is active')
        if not getattr(live, 'browser', None):
            raise web.HTTPConflict(text='The browser is unavailable')
        result = await live.browser.operator_action(b['device'], b['action'], b['frame_id'])
        if live.home.view()['privacy']:
            raise web.HTTPConflict(text='Bathroom privacy is active')
        if result.get('status'):
            await live.on_screen(result['status'])
        return web.json_response(result, status=400 if result.get('error') == 'invalid'
                                 else 409 if result.get('error') else 200,
                                 headers={'Cache-Control': 'no-store'})

    async def pong(request):
        enabled()
        key = live.client_ip(request)
        now = time.monotonic()
        if now - inputs.get(key, 0) < 0.08:
            raise web.HTTPTooManyRequests()
        inputs[key] = now
        inputs.move_to_end(key)
        if len(inputs) > 1024:
            inputs.popitem(last=False)
        b = await body(request)
        direction = b.get("direction")
        if (
            isinstance(direction, bool)
            or not isinstance(direction, (float, int))
            or not math.isfinite(direction)
            or abs(direction) > 1
        ):
            raise web.HTTPBadRequest(text="Direction must be -1 to 1")
        live.home.pong.input(direction)
        return web.json_response({"ok": True})

    async def intent(request):
        enabled()
        operator(request)
        b = await body(request)
        act = b.get("activity")
        if act not in ACTIVITIES or act == "sleep":
            raise web.HTTPBadRequest(text="Unknown activity")
        live.life.apply_vote(act, live.clock.now())
        return web.json_response(
            {
                "ok": True,
                "activity": act,
                "meaning": "A nudge, not a forced action; needs and sleep still decide",
            }
        )

    async def settings(request):
        enabled()
        operator(request)
        b = await body(request)
        for k in ("lamp", "curtain"):
            if k in b:
                if not isinstance(b[k], bool):
                    raise web.HTTPBadRequest(text="Expected boolean")
        for key in ("cabinets", "lowerCabinets"):
            if key in b:
                doors = b[key]
                if (not isinstance(doors, list) or len(doors) != 4
                        or any(not isinstance(v, bool) for v in doors)):
                    raise web.HTTPBadRequest(text="Expected four cabinet door booleans")
        # Additive, optional: partial per-door / per-room operator modes.
        modes = {}
        for key, names, allowed, label in (
                ("doors", hi.DOOR_NAMES, hi.DOOR_MODES, "door"),
                ("lights", hi.LIGHT_ROOMS, hi.LIGHT_MODES, "light room")):
            if key in b:
                try:
                    modes[key] = hi.validate_modes(b[key], names, allowed, label)
                except ValueError as error:
                    raise web.HTTPBadRequest(text=str(error))
        for k in ("lamp", "curtain"):
            if k in b:
                live.home.settings[k] = b[k]
        for key in ("cabinets", "lowerCabinets"):
            if key in b:
                live.home.settings[key] = list(b[key])
        for key, patch in modes.items():
            live.home.settings[key] = {**live.home.settings.get(key, {}), **patch}
        if modes or "lamp" in b:
            # Apply now, so the response and the next feed agree; a door
            # cannot be opened onto an occupied bathroom by this request.
            live.home.interactions.update(0, live.home._actor(), live.home.settings, live.home.now)
        await live.save_state()
        return web.json_response(live.home.settings_view())

    async def game(request):
        enabled()
        operator(request)
        data = await body(request)
        chosen = data.get("game")
        if chosen not in ("pong", "chess", "minecraft"):
            raise web.HTTPBadRequest(text="Unknown console game")
        if chosen == "minecraft" and not (getattr(live, "minecraft", None) and live.minecraft.enabled):
            raise web.HTTPConflict(text="Minecraft is not configured")
        live.home.console_game = chosen
        if getattr(live, 'life', None):
            live.life.console_wish = None
            live.life.console_choice = None
        await live.save_state()
        return web.json_response({"game": chosen})

    async def minecraft_frame(request):
        enabled()
        if private():
            raise web.HTTPConflict(text="Bathroom privacy is active")
        console = getattr(live, "minecraft", None)
        frame = console.frame if console else None
        if not frame:
            raise web.HTTPNotFound(text="Minecraft has no live frame yet")
        # Frame identity: the page polls during live play, but an unchanged
        # picture (a paused game) costs an empty 304 instead of the JPEG.
        tag = '"' + (getattr(console, "frame_tag", None) or frame_tag(frame)) + '"'
        headers = {"Cache-Control": "no-store", "ETag": tag}
        if request.headers.get("If-None-Match") == tag:
            return web.Response(status=304, headers=headers)
        return web.Response(body=frame, content_type="image/jpeg", headers=headers)

    async def house(request):
        enabled()
        return web.FileResponse(
            HERE / "web/house/index.html", headers={"Cache-Control": "no-cache"}
        )

    app.router.add_get("/house", house)
    app.router.add_get("/api/home", state)
    app.router.add_get("/api/home/computer", computer)
    app.router.add_post("/api/home/computer", command)
    app.router.add_post("/api/home/notes", note)
    app.router.add_post("/api/home/pong", pong)
    app.router.add_post("/api/home/settings", settings)
    app.router.add_post("/api/home/intent", intent)
    app.router.add_post('/api/home/browser', navigate)
    app.router.add_post('/api/home/browser/action', browser_action)
    app.router.add_post("/api/home/game", game)
    app.router.add_get("/api/home/minecraft/frame.jpg", minecraft_frame)
