"""Real local Minecraft console: official server, Mineflayer, cortical control and live frames."""
import asyncio
import hashlib
import json
import math
import os
import random
import shutil
import time
from pathlib import Path

from home_minecraft_controller import BrainController

ROOT = Path(__file__).parent

def eula_accepted(directory):
    try:
        return any(line.strip() == "eula=true" for line in (Path(directory) / "eula.txt").read_text().splitlines())
    except OSError:
        return False

def frame_tag(frame):
    """Identity of a JPEG frame (also its HTTP ETag body), computed once per frame."""
    return hashlib.blake2b(frame, digest_size=12).hexdigest() if frame else None


def minecraft_browser_launch_options():
    """Opt-in measured NVIDIA/Xorg path; never share a browser profile/cookies."""
    if os.environ.get("SUB01_MC_HARDWARE_WEBGL", "0") != "1":
        return {"headless": True}
    authority = Path(os.environ.get("SUB01_MC_XAUTHORITY", "/home/unreal/.sub01-private/native-xauthority"))
    display = os.environ.get("SUB01_MC_DISPLAY", ":99")
    if display != ":99" or not authority.is_absolute():
        raise ValueError("Minecraft GPU rendering requires the private local X display")
    info = authority.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077 or not authority.is_file():
        raise ValueError("Minecraft GPU rendering requires the protected same-owner X authority")
    return {"headless": True,
            "args": ["--enable-gpu", "--use-gl=angle", "--use-angle=gl", "--ozone-platform=x11"],
            "ignore_default_args": ["--enable-unsafe-swiftshader"],
            "env": {**os.environ, "DISPLAY": display, "XAUTHORITY": str(authority)}}


class MinecraftConsole:
    def __setattr__(self, name, value):
        # Cache the frame identity when a frame is assigned, not per request/tick.
        if name == "frame":
            object.__setattr__(self, "frame_tag", frame_tag(value))
        object.__setattr__(self, name, value)

    def __init__(self, data_dir):
        self.directory = Path(data_dir) / "minecraft"
        self.server_port = int(os.environ.get("SUB01_MC_SERVER_PORT", "25569"))
        self.viewer_port = int(os.environ.get("SUB01_MC_VIEW_PORT", "8803"))
        if not (1024 <= self.server_port <= 65535 and 1024 <= self.viewer_port <= 65535) or self.server_port == self.viewer_port:
            raise ValueError("Use distinct private Minecraft ports between 1024 and 65535")
        self.enabled = os.environ.get("SUB01_MINECRAFT", "0") == "1"
        self.status = "preparing" if self.enabled else "disabled"
        self.state = {}
        self.error = ""
        self.frame = None
        self.frame_kind = None
        self.worker = self.server = None
        self.active = False
        self.native_input = None
        self.controller = BrainController()
        self._input_pending = {}
        self._render_generation = 0
        self.last_action = ""
        self.last_decision = 0
        self.feedback = 0
        self.events = []
        self.gains = {}
        self.rng = random.Random(17)
        try:
            self.gains = json.loads((self.directory / "learning.json").read_text())
        except (OSError, ValueError):
            pass

    def view(self):
        return {"enabled": self.enabled, "status": self.status, "error": self.error,
                "active": self.active, "last_action": self.last_action,
                "observation": self.state, "events": self.events[-8:], "has_frame": bool(self.frame),
                "frame_kind": self.frame_kind, "frame_id": self.frame_tag,
                "perception": "structured game observations from Mineflayer", "controller": self.controller.view()}

    async def send(self, message):
        if not self.worker or self.worker.returncode is not None:
            return False
        try:
            self.worker.stdin.write((json.dumps(message) + "\n").encode())
            await asyncio.wait_for(self.worker.stdin.drain(), .1)
            return True
        except (OSError, asyncio.TimeoutError):
            return False

    async def operator_input(self, packet):
        key = (packet["consumer_id"], packet["focus_event_id"], packet["input_id"])
        future = asyncio.get_running_loop().create_future()
        self._input_pending[key] = future
        try:
            if not await self.send(packet):return None
            return await asyncio.wait_for(future, 7)
        except asyncio.TimeoutError:
            return None
        finally:
            self._input_pending.pop(key, None)

    def choose(self, rel):
        inventory = self.state.get("inventory", [])
        blocks = sum(i["count"] for i in inventory if i["name"].endswith(("_log", "_planks")) or i["name"] == "dirt")
        food = any(i["name"] in ("apple", "bread", "carrot", "cooked_beef") for i in inventory)
        # Action scores use actual cortical activation, available resources, and saved outcomes.
        scores = {"explore": .4 * rel.get("default", 1), "gather_soil": .12 * rel.get("somatomotor", 1)}
        if self.state.get("wood"):
            scores["mine_wood"] = 1.2 * rel.get("attention", 1)
        if blocks >= 6:
            scores["place_block"] = .5 * rel.get("somatomotor", 1)
        if food and self.state.get("food", 20) < 16:
            scores["eat"] = 5
        if self.state.get("threats"):
            scores["escape"] = 3 * rel.get("fear", 1)
        actions = list(scores)
        weights = [max(.01, scores[a]) * math.exp(max(-1, min(1, self.gains.get(a, 0)))) for a in actions]
        return self.rng.choices(actions, weights=weights)[0]

    async def agent_step(self, home, rel):
        if not self.enabled:
            return
        manual = bool(self.native_input and self.native_input.active(home.privacy()) and home.console_game == "minecraft")
        self.controller.home = home
        self.controller.current_frame = self.frame_tag
        autonomous = home.activity == "play_console" and home.activity_ready("play_console") and home.console_game == "minecraft"
        if self.controller.enabled:
            autonomous = autonomous and bool(self.controller.ready(home, self.frame_tag))
        wants = manual or autonomous
        if wants != self.active:
            if await self.send({"type": "active", "value": wants}):
                self.active = wants
                self._render_generation += 1
        if manual or not wants or not self.state.get("connected") or self.state.get("busy"):
            return
        if time.monotonic() - self.last_decision < 2:
            return
        action = self.choose(rel)
        turn = self.rng.uniform(-1.2, 1.2)
        if self.controller.enabled:
            self.controller.plan(home, action, turn)
            self.last_decision = time.monotonic()
            self.last_action = action
            return
        if await self.send({"type": "action", "action": action, "turn": turn}):
            self.last_decision = time.monotonic()
            self.last_action = action

    async def read_worker(self):
        while line := await self.worker.stdout.readline():
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if message.get("type") == "input_receipt":
                key = (message.get("consumer_id"), message.get("focus_event_id"), message.get("input_id"))
                future = self._input_pending.get(key)
                if future is not None and not future.done():future.set_result(message)
            elif message.get("type") == "state":
                if (bool(message.get("connected")), bool(message.get("active"))) != (bool(self.state.get("connected")), bool(self.state.get("active"))):
                    self._render_generation += 1
                self.state = message
                if message.get("connected"):
                    self.status = "playing" if message.get("active") else "paused"
                else:
                    self.status = "connecting" if message.get("active") else "paused"
            elif message.get("type") == "feedback":
                reward = max(-1, min(1, float(message.get("reward", 0))))
                self.feedback = max(-1, min(1, self.feedback + reward))
                action = message.get("action")
                if action:
                    self.gains[action] = .9 * self.gains.get(action, 0) + .1 * reward
                    (self.directory / "learning.json").write_text(json.dumps(self.gains))
                event = {"at": time.time(), **message}
                self.events.append(event); self.events = self.events[-100:]
                with (self.directory / "events.jsonl").open("a") as stream:
                    stream.write(json.dumps(event) + "\n")
            elif message.get("type") == "error":
                self.error = message.get("message", "Minecraft client error")

    async def render_frames(self):
        from playwright.async_api import async_playwright
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(**minecraft_browser_launch_options())
            try:
                page = await browser.new_page(viewport={"width": 640, "height": 360}, device_scale_factor=1)
                await self._render_frame_loop(page)
            finally:
                await browser.close()

    def _render_owner(self):
        return (self._render_generation, bool(self.state.get("connected")), self.active,
                bool(self.state.get("active", self.active)))

    async def _render_frame_loop(self, page, sleep=asyncio.sleep):
        """Release the WebGL viewer while idle, retaining the real last JPEG.

        The Mineflayer process and Minecraft world keep running independently.
        A single initial connected-frame bootstrap supplies the TV before play;
        subsequent paused periods never render or repeatedly reload that viewer.
        """
        showing = False
        bootstrapped = bool(self.frame)
        while True:
            owner = self._render_owner()
            connected = owner[1]
            active = connected and owner[2] and owner[3]
            bootstrap = connected and not bootstrapped
            try:
                if not active and not bootstrap:
                    if showing:
                        await page.goto('about:blank', wait_until='domcontentloaded', timeout=10000)
                        showing = False
                    await sleep(.5)
                    continue
                if not showing:
                    # Mark potential viewer ownership before navigation, so a
                    # failed/obsolete load is also blanked on the idle path.
                    showing = True
                    await page.goto(f"http://127.0.0.1:{self.viewer_port}", wait_until='domcontentloaded', timeout=10000)
                    if self._render_owner() != owner:
                        continue
                    await page.wait_for_selector('canvas', timeout=10000)
                    await page.wait_for_function('() => globalThis.sub01TerrainReady?.() === true', timeout=15000)
                    if self._render_owner() != owner:
                        continue
                # Read-only product-renderer receipt: actual protocol item identities
                # and decoded texture status, never fabricated entities or pixels.
                receipts = renderer = None
                if callable(getattr(page, 'evaluate', None)):
                    observed = await page.evaluate('() => ({entities: Object.values(globalThis.sub01ItemRenderReceipts || {}).slice(0, 100), renderer: globalThis.sub01RendererDiagnostics?.() || null})')
                    if isinstance(observed, dict):
                        receipts = observed.get('entities')
                        renderer = observed.get('renderer')
                    else:
                        receipts = observed  # Older pinned viewer/test adapter has entities only.
                snapshot_started = time.perf_counter()
                frame = await page.screenshot(type='jpeg', quality=75, timeout=10000)
                snapshot_ms = max(0, (time.perf_counter() - snapshot_started) * 1000)
                if self._render_owner() == owner:
                    self.frame = frame
                    if receipts is not None:
                        (self.directory / 'frame-rendering.json').write_text(json.dumps(
                            {'frame_tag': self.frame_tag, 'entities': receipts, 'renderer': renderer,
                             'snapshot': {'duration_ms': round(snapshot_ms, 3), 'bytes': len(frame),
                                          'width': 640, 'height': 360}}, sort_keys=True))
                    self.frame_kind = 'active' if active else 'initial_idle'
                    bootstrapped = True
                    if not active:
                        await self.send({'type': 'viewer_release'})
                    if self.error.startswith('Minecraft viewer: '):
                        self.error = ''
                # Immediately unload after the one inactive bootstrap rather
                # than leaving its 60fps requestAnimationFrame loop running.
                current = self._render_owner()
                if not (current[1] and current[2] and current[3]) and showing:
                    await page.goto('about:blank', wait_until='domcontentloaded', timeout=10000)
                    showing = False
                await sleep(.125 if current[1] and current[2] and current[3] else .5)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self.error = 'Minecraft viewer: ' + str(error)[:160]
                # Retry from a blank viewer, not a broken navigation/canvas.
                # If blank itself fails, retain showing so the next idle
                # iteration retries releasing that potentially live renderer.
                if showing:
                    try:
                        await page.goto('about:blank', wait_until='domcontentloaded', timeout=10000)
                        showing = False
                    except Exception:
                        pass
                await sleep(.5)

    async def run(self):
        try:
            await self._run()
        except Exception as error:
            self.status = "error"
            self.error = str(error)[:200]
            raise

    async def _run(self):
        while not eula_accepted(self.directory):
            self.status = "needs_eula"
            await asyncio.sleep(2)
        config = json.loads((self.directory / "downloads.json").read_text())
        # Never start a game server configured to bind outside the private loopback.
        properties = (self.directory / "server.properties").read_text().splitlines()
        if "server-ip=127.0.0.1" not in properties or f"server-port={self.server_port}" not in properties:
            raise ValueError(f"Minecraft must bind only to 127.0.0.1:{self.server_port}")
        self.status = "starting_server"
        self.error = ""
        self.state = {}
        self.frame = None
        self.frame_kind = None
        self.server = await asyncio.create_subprocess_exec(config["java"], "-Xms256M", "-Xmx1024M",
            "-jar", str(self.directory / "server.jar"), "nogui", cwd=self.directory,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        tasks = []
        try:
            with (self.directory / "server.log").open("a") as log:
                while line := await self.server.stdout.readline():
                    log.write(line.decode(errors="replace")); log.flush()
                    if b"Done (" in line:
                        break
                else:
                    raise RuntimeError("Minecraft server ended before the world was ready")
            async def drain_server():
                with (self.directory / "server.log").open("a") as log:
                    while line := await self.server.stdout.readline():
                        log.write(line.decode(errors="replace")); log.flush()
            with (self.directory / "worker.log").open("ab") as worker_log:
                self.worker = await asyncio.create_subprocess_exec(shutil.which("node") or "node",
                    str(ROOT / "games/minecraft/worker.cjs"), cwd=ROOT / "games/minecraft",
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=worker_log, env={**os.environ, "SUB01_MC_SERVER_PORT": str(self.server_port), "SUB01_MC_VIEW_PORT": str(self.viewer_port)})
            self.status = "ready"
            tasks = [asyncio.create_task(drain_server()), asyncio.create_task(self.read_worker()),
                     asyncio.create_task(self.render_frames()), asyncio.create_task(self.controller.run(self))]
            await self.send({'type': 'viewer_bootstrap'})
            while self.server.returncode is None and self.worker.returncode is None:
                for task in tasks:
                    if task.done() and task.exception():
                        raise task.exception()
                await asyncio.sleep(1)
            raise RuntimeError(f"Minecraft process ended (server={self.server.returncode}, player={self.worker.returncode}); see local logs")
        finally:
            self.active = False
            for task in tasks: task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if self.worker and self.worker.returncode is None:
                self.worker.stdin.close()
                try: await asyncio.wait_for(self.worker.wait(), 5)
                except asyncio.TimeoutError: self.worker.kill(); await self.worker.wait()
            if self.server and self.server.returncode is None:
                try:
                    self.server.stdin.write(b"stop\n"); await self.server.stdin.drain()
                    await asyncio.wait_for(self.server.wait(), 20)
                except (OSError, asyncio.TimeoutError): self.server.kill(); await self.server.wait()
