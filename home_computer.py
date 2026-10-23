"""Single persistent Linux/x86 computer for SUB-01, isolated inside v86/WebAssembly.

Every way the PC can fail is visible: `view()` carries `status`, `error`, a one-line `summary` for the monitor and the
panel, a `hint` naming the fix (e.g. the gitignored guest files are missing: run computer/bootstrap.py), and `guest`
(which assets, the worker's state, restarts, exit code). `run()` never gives up silently: a guest that cannot be
prepared or a worker that dies is logged once and retried with a bounded backoff.
"""

import asyncio
import base64
import json
import os
import random
import shutil
import time
from pathlib import Path
from computer.input_receipts import InputReceipts, native_receipt

COMMANDS = [
    ("uname -a", "attention"),
    ("ls /", "default"),
    ("date", "salience"),
    ("cat /proc/uptime", "somatomotor"),
    ("free", "attention"),
    ("ls /root", "reward"),
]

RETRY_S = (30, 60, 120, 300)     # a guest that cannot be prepared, or whose worker died, is retried at these intervals
BOOT_WARN_S = 120                # a boot that has not shown the shell prompt by then is logged (once per boot)
STDERR_LINES = 12                # the worker's last stderr lines, logged when it exits (it used to go to /dev/null)
OS_NAME = "Buildroot Linux / x86"


_MISSING = object()


def log(text):
    print("home computer: " + text, flush=True)


class Computer:
    # Any change to what view() shows bumps a monotonic revision, so the page
    # refreshes on an equal-length output replacement too (never by length).
    REVISED = frozenset({"output", "ready", "paused", "status", "last_command", "commands", "error", "display",
                         "instruction_counter", "hint"})

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
        self.hint = ""
        # What is behind the status: the assets in use ("bundled" / "cache"), the worker ("starting", "running",
        # "exited"), how often it was restarted and its last exit code. Shown by /api/home and the panel.
        self.guest = {"assets": None, "worker": None, "restarts": 0, "exit_code": None}
        self._stderr = []
        self._running = False
        self.input_until = 0.0
        self.input_receipts = InputReceipts()

    @property
    def os_name(self):
        return "v86 x86 CD-ROM guest" if self.guest_cdrom else OS_NAME

    def summary(self):
        """One honest line for the monitor and the panel: what the computer is doing, or why it is not."""
        if self.status == "ready":
            return self.os_name + (" · paused while he is away from the desk" if self.paused else " · running")
        if self.status == "booting":
            return "Linux is booting…"
        if self.status == "preparing":
            return "Checking the pinned Linux guest files…"
        if self.status == "starting":
            return "Starting his computer…"
        if self.status == "offline":
            return self.error or "The Linux guest worker is not running"
        if self.status == "unavailable":
            return self.error or "His computer is unavailable"
        return self.status

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
            "os": self.os_name,
            "error": self.error,
            "hint": self.hint,
            "summary": self.summary(),
            "guest": dict(self.guest),
        }

    def clear_unavailable_guest(self):
        self.input_receipts.cancel_all()
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
        if message.get("type") in {"pause", "shutdown"}:
            # Existing privacy/idle pause invalidates ACKs before its pipe drains.
            self.input_receipts.cancel_all()
        if not self.process or self.process.returncode is not None:
            self.clear_unavailable_guest()
            return False
        try:
            self.process.stdin.write((json.dumps(message) + "\n").encode())
            await asyncio.wait_for(self.process.stdin.drain(), 0.05)
            return True
        except (asyncio.TimeoutError, BrokenPipeError, ConnectionResetError) as error:
            if self.status != "offline":
                log(f"the guest worker stopped taking input ({type(error).__name__}); it will be restarted")
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

    async def cancel_graphical_receipts(self):
        # Only correlated requests are cancelled; legacy input and other held
        # keys are untouched. The worker releases keys owned by these requests.
        for packet in self.input_receipts.cancel_all():
            await self.send(packet)

    async def graphical_input_receipt(self, data, native):
        native = native_receipt(native)
        kind = data.get("type")
        level = {"vga-keyboard": "GuestKeyboardInjected", "vga-mouse": "GuestMouseInjected"}.get(kind)
        if not level or not (self.display.get("available") or self.display.get("keyboard_available")):
            return {"ok": False}
        process = self.process
        if not process or process.returncode is not None:
            self.clear_unavailable_guest()
            return {"ok": False}
        pending = self.input_receipts.begin(process, native, level)
        if pending is None:
            return {"ok": False}
        identifier, receipt, future = pending
        self.input_until = time.monotonic() + 5
        self.paused = False
        try:
            if not await self.send({**data, "_receipt": receipt}):
                return {"ok": False}
            # One bounded future observes the existing stdin/stdout operation;
            # no extra dispatch queue, worker, endpoint or retry is introduced.
            result = await asyncio.wait_for(asyncio.shield(future), 1.5)
            if self.process is not process or process.returncode is not None:
                return {"ok": False}
            return result
        except asyncio.TimeoutError:
            return {"ok": False}
        finally:
            packet = self.input_receipts.discard(identifier)
            if packet and self.process is process and process.returncode is None:
                await self.send(packet)

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

    # --- the worker process ------------------------------------------------------------------------
    async def _drain_stderr(self, worker):
        """Keep the worker's last stderr lines (a Node.js crash, a missing module) for the exit log line."""
        try:
            async for raw in worker.stderr:
                text = raw.decode("utf-8", "replace").rstrip()
                if text:
                    self._stderr = (self._stderr + [text[:200]])[-STDERR_LINES:]
        except ValueError:                                     # a line over the pipe limit: stop reading
            pass

    def _handle(self, m, worker, boot):
        """One JSON line from the worker. `boot`: {"started", "ready", "warned"} of this worker (for the log)."""
        kind = m.get("type")
        if kind == "graphical-input-ack":
            self.input_receipts.complete(m, worker)
        elif kind == "terminal":
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
            if self.ready and not boot["ready"]:
                boot["ready"] = True
                self.error, self.hint = "", ""
                log(f"Linux guest ready after {time.monotonic() - boot['started']:.0f} s "
                    f"({self.guest['assets']} assets); it pauses while he is away from the desk")
            elif not self.ready and not boot["warned"] and time.monotonic() - boot["started"] > BOOT_WARN_S:
                boot["warned"] = True
                log(f"the guest has not shown its shell prompt after {BOOT_WARN_S} s (still booting; "
                    f"a stale data/computer.bin snapshot can be deleted to boot fresh)")
        elif kind == "display":
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
        elif kind == "restored":
            log("Linux restored from its saved state (data/computer.bin)")
        elif kind == "error":
            self.error = str(m.get("message", ""))[:160]
            log("the guest worker reports: " + self.error)

    def _exit_reason(self, worker):
        code = worker.returncode
        why = (f"killed by signal {-code}" + (" (out of memory?)" if code == -9 else "")
               if code is not None and code < 0 else f"exited with code {code}")
        tail = " | ".join(self._stderr[-4:])
        return why + (f"; stderr: {tail}" if tail else "")

    async def _worker(self, node, assets):
        """One life of the worker: spawn, read its lines until it exits. Returns when the worker died on its own;
        a cancel (server shutdown) asks it to save its state first."""
        env = {k: os.environ[k] for k in ("PATH", "LANG", "TZ") if k in os.environ}
        env["SUB01_VM_ASSETS"] = str(assets)
        state = self.data_dir / ("computer-graphical.bin" if self.guest_cdrom else "computer.bin")
        env["SUB01_VM_STATE"] = str(state)
        if self.guest_cdrom:
            env["SUB01_VM_CDROM"] = str(self.guest_cdrom)
        self._stderr = []
        self.process = await asyncio.create_subprocess_exec(
            node,
            "--max-old-space-size=192",
            str(Path(__file__).parent / "computer/worker.cjs"),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=8 * 1024 * 1024,
            env=env,
        )
        self._running = True
        worker = self.process  # ACK authority is the stdout producer, not a mutable current pointer.
        self.guest.update(worker="starting", exit_code=None)
        self.status, self.error, self.hint = "booting", "", ""
        log(f"guest worker started (pid {worker.pid}, {self.guest['assets']} assets, "
            f"state {'restored from ' if state.exists() else 'new at '}{state})")
        stderr = asyncio.create_task(self._drain_stderr(worker))
        boot = {"started": time.monotonic(), "ready": False, "warned": False}
        try:
            async for line in worker.stdout:
                try:
                    m = json.loads(line)
                except ValueError:
                    continue
                if self.guest["worker"] == "starting":
                    self.guest["worker"] = "running"
                self._handle(m, worker, boot)
            await worker.wait()
            try:
                await asyncio.wait_for(stderr, 1)
            except asyncio.TimeoutError:
                pass
            self.clear_unavailable_guest()
            self.guest.update(worker="exited", exit_code=worker.returncode)
            self.error = ("Linux guest worker " + self._exit_reason(worker))[:300]
            self.hint = "It restarts by itself (see the server log for the worker's last lines)"
            log(self.error)
        finally:
            self._running = False
            stderr.cancel()
            if worker.returncode is None:
                await self.send({"type": "shutdown"})
                try:
                    await asyncio.wait_for(worker.wait(), 5)
                except asyncio.TimeoutError:
                    worker.kill()
                    await worker.wait()

    async def run(self):
        node = shutil.which("node")
        if not node:
            self.status = "unavailable"
            self.error = "Node.js is not installed"
            self.hint = "Install Node.js (the guest runs in computer/worker.cjs) and restart the server"
            log(self.error + ": his computer stays off")
            return
        from computer import bootstrap

        cache = self.data_dir / "computer-assets"
        said, failures = None, 0
        while True:
            self.status, self.hint = "preparing", ""
            try:
                assets = await asyncio.to_thread(bootstrap.ensure, cache)
            except Exception as error:
                failures += 1
                st = bootstrap.status(cache)
                self.status = "unavailable"
                self.error = (bootstrap.describe(st) + ("" if st["installed"] else f"; {error}"))[:300]
                self.hint = ("The computer is off until the guest files are there: " + bootstrap.RUN_HINT
                             + "; the server retries by itself")
                wait = RETRY_S[min(failures, len(RETRY_S)) - 1]
                if self.error != said:
                    said = self.error
                    log(f"{self.error}. {self.hint} (next try in {wait} s, then up to every {RETRY_S[-1]} s)")
                await asyncio.sleep(wait)
                continue
            failures, said = 0, None
            self.guest["assets"] = "bundled" if Path(assets) == bootstrap.ROOT else "cache"
            try:
                await self._worker(node, assets)
            except OSError as error:                           # node could not be started at all
                self.clear_unavailable_guest()
                self.error = f"The guest worker could not start: {str(error)[:120]}"
                self.hint = "Check the Node.js installation; the server retries by itself"
                log(self.error)
            self.guest["restarts"] += 1
            wait = RETRY_S[min(self.guest["restarts"], len(RETRY_S)) - 1]
            log(f"restarting the guest worker in {wait} s (restart {self.guest['restarts']})")
            await asyncio.sleep(wait)
