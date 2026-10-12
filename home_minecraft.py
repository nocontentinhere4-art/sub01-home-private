"""Real local Minecraft console: official server, Mineflayer, cortical control and live frames."""
import asyncio
import json
import math
import os
import random
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).parent

def eula_accepted(directory):
    try:
        return any(line.strip() == "eula=true" for line in (Path(directory) / "eula.txt").read_text().splitlines())
    except OSError:
        return False

class MinecraftConsole:
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
        self.worker = self.server = None
        self.active = False
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
                "perception": "structured game observations from Mineflayer"}

    async def send(self, message):
        if not self.worker or self.worker.returncode is not None:
            return False
        try:
            self.worker.stdin.write((json.dumps(message) + "\n").encode())
            await asyncio.wait_for(self.worker.stdin.drain(), .1)
            return True
        except (OSError, asyncio.TimeoutError):
            return False

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
        wants = home.activity == "play_console" and not home.path and home.console_game == "minecraft"
        if wants != self.active:
            if await self.send({"type": "active", "value": wants}):
                self.active = wants
        if not wants or not self.state.get("connected") or self.state.get("busy"):
            return
        if time.monotonic() - self.last_decision < 2:
            return
        action = self.choose(rel)
        if await self.send({"type": "action", "action": action, "turn": self.rng.uniform(-1.2, 1.2)}):
            self.last_decision = time.monotonic()
            self.last_action = action

    async def read_worker(self):
        while line := await self.worker.stdout.readline():
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if message.get("type") == "state":
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
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 640, "height": 360}, device_scale_factor=1)
            showing = False
            try:
                while True:
                    if not self.state.get("connected"):
                        showing = False
                        await asyncio.sleep(.5)
                        continue
                    if not showing:
                        await page.goto(f"http://127.0.0.1:{self.viewer_port}", wait_until="domcontentloaded")
                        await page.wait_for_selector("canvas")
                        showing = True
                    self.frame = await page.screenshot(type="jpeg", quality=75)
                    await asyncio.sleep(.125)
            finally:
                await browser.close()

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
                     asyncio.create_task(self.render_frames())]
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
