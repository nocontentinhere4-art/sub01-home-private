"""Single persistent Linux/x86 computer for SUB-01, isolated inside v86/WebAssembly."""

import asyncio
import base64
import json
import os
import random
import shutil
import time
from pathlib import Path

COMMANDS = [
    ("uname -a", "attention"),
    ("ls /", "default"),
    ("date", "salience"),
    ("cat /proc/uptime", "somatomotor"),
    ("free", "attention"),
    ("ls /root", "reward"),
]


_MISSING = object()


class Computer:
    # Any change to what view() shows bumps a monotonic revision, so the page
    # refreshes on an equal-length output replacement too (never by length).
    REVISED = frozenset({"output", "ready", "paused", "status", "last_command", "commands", "error", "display", "instruction_counter"})

    def __setattr__(self, name, value):
        if name in self.REVISED and getattr(self, name, _MISSING) != value:
            object.__setattr__(self, "revision", getattr(self, "revision", 0) + 1)
        object.__setattr__(self, name, value)

    def __new__(cls, data_dir):
        origin = os.environ.get("HOME_COMPUTER_ORIGIN")
        if origin:
            from home_remote_computer import RemoteComputer
            return RemoteComputer(data_dir, origin, os.environ.get(
                "HOME_COMPUTER_TOKEN_FILE", "/home/unreal/.sub01-private/operator-token"))
        return super().__new__(cls)

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.guest_cdrom = None
        self.display = {"kind": "serial", "available": False, "reason": "Graphical guest framebuffer is not active"}
        self.framebuffer_png = None
        self.instruction_counter = None
        self.mouse_state = None
        self.process = None
        self.output = ""
        self.ready = False
        self.paused = False
        self.status = "starting"
        self.last_command = ""
        self.commands = 0
        self.last_agent = 0
        self.error = ""
        self._running = False
        self.input_until = 0.0

    def view(self):
        return {
            "status": self.status,
            "instruction_counter": self.instruction_counter,
            "mouse_state": dict(self.mouse_state) if self.mouse_state is not None else None,
            "display": dict(self.display),
            "ready": self.ready,
            "output": self.output[-10000:],
            "paused": self.paused,
            "last_command": self.last_command,
            "commands": self.commands,
            "revision": self.revision,
            "os": "v86 x86 CD-ROM guest" if self.guest_cdrom else "Buildroot Linux / x86",
            "error": self.error,
        }

    def clear_unavailable_guest(self):
        self.ready = False
        self.status = "offline"
        self.output = ""
        self.last_command = ""
        self.framebuffer_png = None
        self.instruction_counter = None
        self.mouse_state = None
        self.display = {"kind": "unavailable", "available": False,
                        "reason": "Actual guest worker is unavailable"}

    async def send(self, message):
        if not self.process or self.process.returncode is not None:
            self.clear_unavailable_guest()
            return False
        self.process.stdin.write((json.dumps(message) + "\n").encode())
        try:
            await asyncio.wait_for(self.process.stdin.drain(), 0.05)
            return True
        except (asyncio.TimeoutError, BrokenPipeError, ConnectionResetError):
            self.clear_unavailable_guest()
            return False

    async def input(self, text):
        if not self.ready:
            return False
        self.input_until = time.monotonic() + 5
        self.paused = False
        return await self.send({"type": "input", "text": text})

    async def graphical_input(self, data):
        if not (self.display.get("available") or self.display.get("keyboard_available")):
            return False
        self.input_until = time.monotonic() + 5
        self.paused = False
        return await self.send(data)

    async def agent_step(self, home, rel):
        using = home.activity == "use_computer" and home.activity_ready("use_computer")
        if (
            not using
            and self.ready
            and not self.paused
            and time.monotonic() > self.input_until
        ):
            if await self.send({"type": "pause"}):
                self.paused = True
        if using and self.ready:
            if self.paused:
                await self.send({"type": "resume"})
                self.paused = False
            if time.monotonic() - self.last_agent > 18:
                weights = [max(0.05, float(rel.get(group, 1))) for _, group in COMMANDS]
                command = random.choices(COMMANDS, weights=weights)[0][0]
                if await self.input(command + "\n"):
                    self.last_command = command
                    self.commands += 1
                    self.last_agent = time.monotonic()
                    home.memories.append(
                        {
                            "at": round(home.time, 1),
                            "activity": "use_computer",
                            "command": command,
                        }
                    )
                    home.memories = home.memories[-100:]

    async def run(self):
        node = shutil.which("node")
        if not node:
            self.status = "unavailable"
            self.error = "Node.js is not installed"
            return
        from computer.bootstrap import ensure

        self.status = "preparing"
        try:
            assets = await asyncio.to_thread(ensure, self.data_dir / "computer-assets")
        except Exception:
            self.status = "unavailable"
            self.error = "Pinned Linux guest could not be prepared"
            raise
        env = {k: os.environ[k] for k in ("PATH", "LANG", "TZ") if k in os.environ}
        env["SUB01_VM_ASSETS"] = str(assets)
        env["SUB01_VM_STATE"] = str(self.data_dir / ("computer-graphical.bin" if self.guest_cdrom else "computer.bin"))
        if self.guest_cdrom:
            env["SUB01_VM_CDROM"] = str(self.guest_cdrom)
        self.process = await asyncio.create_subprocess_exec(
            node,
            "--max-old-space-size=192",
            str(Path(__file__).parent / "computer/worker.cjs"),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            limit=8 * 1024 * 1024,
            env=env,
        )
        self._running = True
        try:
            async for line in self.process.stdout:
                try:
                    m = json.loads(line)
                except ValueError:
                    continue
                if m.get("type") == "terminal":
                    self.output = str(m.get("output", ""))[-12000:]
                    self.ready = bool(m.get("ready"))
                    self.paused = bool(m.get("paused"))
                    count = m.get("instruction_counter")
                    self.instruction_counter = count if isinstance(count, int) and not isinstance(count, bool) and 0 <= count <= 0xffffffff else None
                    mouse = m.get("mouse_state")
                    self.mouse_state = None
                    if isinstance(mouse, dict):
                        self.mouse_state = {}
                        for key in ("absolute_pointer_enabled", "ps2_use_mouse", "ps2_stream_enabled", "ps2_stream_active", "vmware_enabled", "vmware_absolute", "vmware_host_pointer_locked"):
                            value = mouse.get(key)
                            self.mouse_state[key] = value if isinstance(value, bool) else None
                        for key in ("ps2_mouse_id", "ps2_command_register"):
                            value = mouse.get(key)
                            valid = isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 255
                            self.mouse_state[key] = value if valid else None
                    self.status = "ready" if self.ready else "booting"
                elif m.get("type") == "display":
                    display = m.get("display") or {}
                    self.framebuffer_png = None
                    if display.get("kind") == "graphical" and display.get("available"):
                        try:
                            pixels = base64.b64decode(m.get("png", ""), validate=True)
                            if 0 < len(pixels) <= 6 * 1024 * 1024 and pixels.startswith(b"\x89PNG\r\n\x1a\n"):
                                self.framebuffer_png = pixels
                        except (ValueError, TypeError):
                            pass
                    self.display = dict(display, available=bool(self.framebuffer_png))
                elif m.get("type") == "error":
                    self.error = str(m.get("message", ""))[:160]
            self.clear_unavailable_guest()
        finally:
            self._running = False
            if self.process.returncode is None:
                await self.send({"type": "shutdown"})
                try:
                    await asyncio.wait_for(self.process.wait(), 5)
                except asyncio.TimeoutError:
                    self.process.kill()
                    await self.process.wait()
