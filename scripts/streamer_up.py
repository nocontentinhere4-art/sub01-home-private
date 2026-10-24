#!/usr/bin/env python3
"""SUB-01 streamer supervisor for the GPU pod: start, stop, status, kill, restart <name>.

Services, started in this order (each waits until the ones before it have settled,
and until the ones it requires are healthy):

  xvfb      Xvfb :102 1920x1080 (an X server already there is used and never killed)
  desktop   scripts/streamer_desktop.py       port 8832   DISPLAY=:102, LD_LIBRARY_PATH=<libs>
  voice     scripts/voice_server.py           port 8835   HF_HOME=<hf cache>, --voice-config if voice/voice.json exists
  agent     streamer_agent.py                 port 8836   (held down while the STOP file exists)
  director  scripts/streamer_director.py      port 8837   (records recordings/*.mp4)
  monitor   scripts/streamer_monitor_feed.py  port 8840   the desktop's X display -> monitor.mjpeg for the in-game
                                                          monitor, behind its privacy gate (layout.jsonl + /pc/state)
  hls       scripts/streamer_hls_serve.py     port 8839   serves --hls-dir (default <streamer-dir>/hls) on loopback

Every child runs as the user that runs this script (no root needed, `start` refuses
root unless --allow-root), in its own session, with a PID file in <streamer-dir>/pids,
a log in <streamer-dir>/logs/<name>.log and an HTTP health URL (Xvfb: its socket).
A child that dies is restarted with backoff, at most 5 times per 10 minutes; after
that it is left down and reported (`status`, events.jsonl). `restart <name>` clears
that budget. The operator token is read from the token file and handed to the
children that call the token-protected APIs in the SUB01_ADMIN_TOKEN environment
variable only (never to xvfb and hls), never in argv or logs.

  start [--foreground] [--dry-run]   start the supervisor (detached unless --foreground)
  stop                               SIGTERM in reverse order, SIGKILL a child after 15 s
  status [--json]                    supervisor, children, STOP file, director and monitor summaries
  kill                               kill switch: STOP file + voice /stop + agent taken down;
                                     desktop runner, director, voice server, monitor feed,
                                     HLS server, Xvfb stay up
  resume                             remove the STOP file; the agent is started again
  restart <name>                     restart one child and reset its restart budget

Exit codes: 0 ok, 1 something is not up, 2 usage or configuration error.
"""

import argparse
import fcntl
import http.client
import json
import os
import pwd
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_STREAMER_DIR = "/home/unreal/.sub01-private/streamer"
DEFAULT_TOKEN_FILE = "/home/unreal/.sub01-private/operator-token"
DEFAULT_SOURCE = "/home/unreal/.sub01-private/latest-source-20261023"
DEFAULT_PORTS = {"desktop": 8832, "voice": 8835, "agent": 8836, "director": 8837, "monitor": 8840, "hls": 8839}
DEFAULT_PYTHON = {
    "desktop": "/home/unreal/.sub01-private/city-readonly-browser/venv/bin/python",
    "voice": "/home/unreal/voice-rt-venv/bin/python",
    "agent": "/home/unreal/venv/bin/python",
    "director": "/home/unreal/venv/bin/python",
    "monitor": "/home/unreal/venv/bin/python",
    "hls": "/home/unreal/venv/bin/python",
}
DEFAULT_LIBRARY_PATH = "/workspace/sub01-home-private/claude-12h/libs/usr/lib/x86_64-linux-gnu"
DEFAULT_HF_HOME = "/home/unreal/hf-cache"
BACKEND_PORT = 8830
ORDER = ("xvfb", "desktop", "voice", "agent", "director", "monitor", "hls")
SCRIPTS = {"desktop": "scripts/streamer_desktop.py", "voice": "scripts/voice_server.py",
           "agent": "streamer_agent.py", "director": "scripts/streamer_director.py",
           "monitor": "scripts/streamer_monitor_feed.py", "hls": "scripts/streamer_hls_serve.py"}
PORT_FLAG = {"desktop": "--port", "voice": "--port", "agent": "--status-port", "director": "--port",
             "monitor": "--port", "hls": "--port"}
HEALTH_PATH = {"desktop": "/healthz", "voice": "/healthz", "agent": "/healthz", "director": "/healthz",
               "monitor": "/healthz", "hls": "/healthz"}
START_TIMEOUT = {"xvfb": 20.0, "desktop": 90.0, "voice": 240.0, "agent": 60.0, "director": 45.0, "monitor": 20.0,
                 "hls": 20.0}
REQUIRES = {"desktop": ("xvfb",), "agent": ("desktop",), "director": ("xvfb",), "monitor": ("xvfb",)}
RESTART_WITH = {"desktop": ("xvfb",)}          # Chromium cannot survive its X server restarting
NO_TOKEN = ("xvfb", "hls")                     # children that call no token-protected API get no operator token
AGENT_PASSTHROUGH = ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "MOONSHOT_API_KEY", "STREAMER_MODEL",
                     "STREAMER_CALLS_PER_HOUR", "STREAMER_PROVIDER", "STREAMER_FALLBACK_PROVIDER", "STREAMER_KIMI_MODEL",
                     "MIND", "SUB01_STREAMER")
BASE_ENV_KEYS = ("PATH", "LANG", "LC_ALL", "TZ", "TMPDIR", "XDG_RUNTIME_DIR")
MIN_TOKEN = 12
TICK = 1.0


def now_iso(unix=None):
    return datetime.fromtimestamp(time.time() if unix is None else unix, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ config

class Config:
    """Everything configurable by flags. `ports`, `pythons` and `health` are keyed by service name."""

    def __init__(self, streamer_dir=DEFAULT_STREAMER_DIR, token_file=None, source=DEFAULT_SOURCE, display=":102",
                 game_display=":99.0", ports=None, pythons=None, library_path=DEFAULT_LIBRARY_PATH,
                 hf_home=DEFAULT_HF_HOME, voice_config=None, xvfb="Xvfb", xvfb_screen="1920x1080x24", health=None, child_args=None,
                 child_env=None, stop_grace=15.0, restart_max=5, restart_window=600.0, unhealthy_after=120.0,
                 backend_port=BACKEND_PORT, hls_dir=None, environ=None):
        self.streamer_dir = Path(streamer_dir)
        self.hls_dir = Path(hls_dir) if hls_dir else self.streamer_dir / "hls"
        self.token_file = Path(token_file) if token_file else None
        self.source = Path(source)
        self.display = display
        self.game_display = game_display
        self.ports = {**DEFAULT_PORTS, **(ports or {})}
        self.pythons = {**DEFAULT_PYTHON, **(pythons or {})}
        self.library_path = library_path
        self.hf_home = hf_home
        self.voice_config = Path(voice_config) if voice_config else self.streamer_dir / "voice" / "voice.json"
        self.xvfb = xvfb
        self.xvfb_screen = xvfb_screen
        self.health = {**HEALTH_PATH, **(health or {})}
        self.child_args = child_args or {}
        self.child_env = child_env or {}
        self.stop_grace = stop_grace
        self.restart_max = restart_max
        self.restart_window = restart_window
        self.unhealthy_after = unhealthy_after
        self.backend_port = backend_port
        self.environ = dict(os.environ if environ is None else environ)

    @property
    def pids_dir(self):
        return self.streamer_dir / "pids"

    @property
    def logs_dir(self):
        return self.streamer_dir / "logs"

    @property
    def ctl_dir(self):
        return self.streamer_dir / "ctl"

    @property
    def stop_file(self):
        return self.streamer_dir / "STOP"

    @property
    def snapshot_file(self):
        return self.streamer_dir / "supervisor.json"

    def pid_file(self, name):
        return self.pids_dir / f"{name}.pid"

    def log_file(self, name):
        return self.logs_dir / f"{name}.log"

    def x_socket(self):
        return "/tmp/.X11-unix/X" + self.display.lstrip(":").split(".")[0]


def read_token(cfg):
    """Operator token: --token-file, else SUB01_ADMIN_TOKEN, else the default file. Never printed."""
    if cfg.token_file:
        text = cfg.token_file.read_text().strip()
    elif cfg.environ.get("SUB01_ADMIN_TOKEN", "").strip():
        text = cfg.environ["SUB01_ADMIN_TOKEN"].strip()
    else:
        text = Path(DEFAULT_TOKEN_FILE).read_text().strip()
    if len(text) < MIN_TOKEN:
        raise ValueError(f"operator token must have at least {MIN_TOKEN} characters")
    return text


# ----------------------------------------------------------------- specs

class ServiceSpec:
    def __init__(self, name, argv, env, cwd, health, needle, requires=(), restart_with=(), start_timeout=60.0,
                 hold_on_stop=False, adopt_existing=False, port=None, python=None, script=None):
        self.name, self.argv, self.env, self.cwd = name, list(argv), dict(env), str(cwd)
        self.health, self.needle = health, needle
        self.requires, self.restart_with = tuple(requires), tuple(restart_with)
        self.start_timeout, self.hold_on_stop, self.adopt_existing = start_timeout, hold_on_stop, adopt_existing
        self.port, self.python, self.script = port, python, script


def home_dir():
    try:
        return pwd.getpwuid(os.getuid()).pw_dir
    except KeyError:
        return os.environ.get("HOME", "/tmp")


def base_env(cfg):
    env = {k: cfg.environ[k] for k in BASE_ENV_KEYS if k in cfg.environ}
    env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    env["HOME"] = home_dir()
    return env


def service_env(cfg, token, extra=None):
    """The environment of a Python child; `token` None leaves SUB01_ADMIN_TOKEN out (children in NO_TOKEN)."""
    env = base_env(cfg)
    env.update({
        "PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "STREAMER_DIR": str(cfg.streamer_dir),
        "STREAMER_BACKEND_URL": f"http://127.0.0.1:{cfg.backend_port}",
        "STREAMER_DESKTOP_URL": f"http://127.0.0.1:{cfg.ports['desktop']}",
        "STREAMER_VOICE_URL": f"http://127.0.0.1:{cfg.ports['voice']}",
        "STREAMER_DIRECTOR_URL": f"http://127.0.0.1:{cfg.ports['director']}",
        "STREAMER_AGENT_URL": f"http://127.0.0.1:{cfg.ports['agent']}",
    })
    if token is not None:
        env["SUB01_ADMIN_TOKEN"] = token
    env.update(extra or {})
    return env


def build_specs(cfg, token):
    """{name: ServiceSpec} in start order. Pure: nothing is launched or read from the machine."""
    specs = {}
    screen = cfg.display if "." in cfg.display else cfg.display + ".0"
    specs["xvfb"] = ServiceSpec(
        "xvfb", [cfg.xvfb, cfg.display.split(".")[0], "-screen", "0", cfg.xvfb_screen, "-nolisten", "tcp", "-noreset"]
        + cfg.child_args.get("xvfb", []), {**base_env(cfg), **cfg.child_env.get("xvfb", {})}, cfg.streamer_dir,
        ("xsocket", cfg.x_socket()), "Xvfb", start_timeout=START_TIMEOUT["xvfb"], adopt_existing=True)
    urls = {n: f"http://127.0.0.1:{cfg.ports[n]}" for n in DEFAULT_PORTS}
    x_display = cfg.display.split(".")[0]           # the desktop runner's display; the monitor feed captures the same
    for name in ORDER[1:]:
        port, python = cfg.ports[name], cfg.pythons[name]
        script = str(cfg.source / SCRIPTS[name])
        argv = [python, script]
        if name == "desktop":
            argv += ["--data-dir", str(cfg.streamer_dir / "desktop"), "--display", x_display,
                     "--home-origin", f"http://127.0.0.1:{cfg.backend_port}"]
        elif name == "voice":
            argv += ["--streamer-dir", str(cfg.streamer_dir)]
            if cfg.voice_config.is_file():
                argv += ["--voice-config", str(cfg.voice_config)]
        elif name == "agent":
            argv += ["--streamer-dir", str(cfg.streamer_dir), "--desktop-url", urls["desktop"],
                     "--backend-url", f"http://127.0.0.1:{cfg.backend_port}", "--voice-url", urls["voice"],
                     "--director-url", urls["director"]]
        elif name == "director":
            argv += ["--streamer-dir", str(cfg.streamer_dir), "--desktop-display", screen, "--game-display", cfg.game_display]
        elif name == "monitor":
            argv += ["--streamer-dir", str(cfg.streamer_dir), "--display", x_display, "--desktop-url", urls["desktop"]]
        else:                                           # hls: the directory is its one positional argument
            argv += [str(cfg.hls_dir)]
        if name == "director" or port != DEFAULT_PORTS[name]:      # the others already default to the plan's ports
            argv += [PORT_FLAG[name], str(port)]
        argv += cfg.child_args.get(name, [])
        extra = {}
        if name == "desktop":
            ld = cfg.library_path + (":" + cfg.environ["LD_LIBRARY_PATH"] if cfg.environ.get("LD_LIBRARY_PATH") else "")
            extra = {"DISPLAY": x_display, "LD_LIBRARY_PATH": ld}
        elif name == "voice":
            extra = {"HF_HOME": cfg.hf_home}
        elif name == "agent":
            extra = {k: cfg.environ[k] for k in AGENT_PASSTHROUGH if k in cfg.environ}
        extra.update(cfg.child_env.get(name, {}))
        specs[name] = ServiceSpec(
            name, argv, service_env(cfg, None if name in NO_TOKEN else token, extra), cfg.source,
            ("http", port, cfg.health[name]),
            os.path.basename(SCRIPTS[name]), requires=REQUIRES.get(name, ()), restart_with=RESTART_WITH.get(name, ()),
            start_timeout=START_TIMEOUT[name], hold_on_stop=(name == "agent"), port=port, python=python, script=script)
    return specs


def redacted_env(env):
    return {k: ("***" if k == "SUB01_ADMIN_TOKEN" or k.endswith("_API_KEY") else v) for k, v in env.items()}


def preflight(spec):
    """None if the child can be launched, else the reason it cannot."""
    if spec.name == "xvfb":
        return None if shutil.which(spec.argv[0]) else f"{spec.argv[0]} not found in PATH"
    if not (spec.python and os.access(spec.python, os.X_OK)):
        return f"python not found or not executable: {spec.python}"
    if not os.path.isfile(spec.script):
        return f"script not found: {spec.script}"
    return None


def director_hls_dir(cfg):
    """The --hls-dir the director gets through --child-arg (the last one wins, like argparse), or None (no HLS)."""
    found, args = None, cfg.child_args.get("director", [])
    for index, arg in enumerate(args):
        if arg == "--hls-dir" and index + 1 < len(args):
            found = args[index + 1]
        elif arg.startswith("--hls-dir="):
            found = arg.split("=", 1)[1]
    return found


def environment_warnings(cfg):
    notes = []
    if not shutil.which("ffmpeg"):
        notes.append("ffmpeg not found in PATH: the director cannot record, the monitor feed cannot capture")
    if not shutil.which("xdotool"):
        notes.append("xdotool not found in PATH: the director records all of :99 instead of the game window")
    hls = director_hls_dir(cfg)
    if hls is None:
        notes.append(f"the director writes no HLS (no --hls-dir in --child-arg director=...): the hls service serves "
                     f"{cfg.hls_dir}, which stays empty")
    elif os.path.normpath(hls) != os.path.normpath(str(cfg.hls_dir)):
        notes.append(f"the director writes HLS to {hls} but the hls service serves {cfg.hls_dir}: pass --hls-dir {hls}")
    return notes


# -------------------------------------------------- restart budget, gating

class RestartBudget:
    """At most `limit` restarts per `window` seconds."""

    def __init__(self, limit=5, window=600.0):
        self.limit, self.window, self.times = limit, window, deque()

    def used(self, now):
        while self.times and now - self.times[0] >= self.window:
            self.times.popleft()
        return len(self.times)

    def allow(self, now):
        return self.used(now) < self.limit

    def record(self, now):
        self.times.append(now)

    def delay(self, now):
        """Backoff before the next restart: 1, 2, 4, 8, 16 s, at most 30."""
        return min(30.0, 2.0 ** self.used(now))

    def reset(self):
        self.times.clear()


SETTLED = {"up", "unhealthy", "backoff", "failed", "blocked", "held", "stopped"}


def start_gate(name, statuses, specs, first_start):
    """Decide whether `name` may be launched now -> ("go"|"wait"|"blocked", reason).

    Start order: on the first start a service waits until every service before it in ORDER has settled
    (is up, or has failed or been blocked), so desktop, voice and agent come up one after the other.
    Requirements: a service never starts while one it requires is not healthy."""
    if first_start:
        for earlier in ORDER[:ORDER.index(name)]:
            if statuses.get(earlier) not in SETTLED:
                return "wait", f"waiting for {earlier}"
    for dep in specs[name].requires:
        status = statuses.get(dep)
        if status != "up":
            return "blocked", f"{dep} {'failed' if status == 'failed' else 'is not up'}"
    return "go", ""


# ------------------------------------------------------- processes, probes

def pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        with open(f"/proc/{pid}/stat") as handle:
            return handle.read().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        return True


def pid_matches(pid, needle, proc_root="/proc"):
    try:
        raw = Path(proc_root, str(pid), "cmdline").read_bytes()
    except OSError:
        return False
    return needle.encode() in raw


def read_pid(path):
    try:
        return int(Path(path).read_text().strip())
    except (OSError, ValueError):
        return None


def signal_group(pid, sig):
    """Signal the child's process group (each child leads its own session); False if it is gone."""
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return False
    except OSError:
        pgid = None
    try:
        if pgid == pid:
            os.killpg(pid, sig)
        else:
            os.kill(pid, sig)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def kill_remnants(pid):
    """After a child exited: SIGKILL anything left in its process group (Chromium helpers, ffmpeg)."""
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


class AdoptedProc:
    """A child of an earlier supervisor, found through its PID file. Alive means the pid exists."""

    def __init__(self, pid, alive=pid_alive):
        self.pid, self._alive = pid, alive
        self.returncode = None

    def poll(self):
        if self.returncode is None and not self._alive(self.pid):
            self.returncode = -1
        return self.returncode


def spawn_process(spec, log_path):
    """Launch one child in its own session, stdout and stderr appended to its log."""
    log_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    rotate_log(log_path)
    fd = os.open(log_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, f"\n=== {now_iso()} start: {shlex.join(spec.argv)}\n".encode())
        return subprocess.Popen(spec.argv, env=spec.env, cwd=spec.cwd if os.path.isdir(spec.cwd) else None,
                                stdin=subprocess.DEVNULL, stdout=fd, stderr=subprocess.STDOUT,
                                start_new_session=True, close_fds=True)
    finally:
        os.close(fd)


def rotate_log(path, limit=20 * 1024 * 1024):
    try:
        if path.stat().st_size > limit:
            path.replace(path.with_suffix(".log.1"))
    except OSError:
        pass


def find_adoptable(cfg, spec):
    pid = read_pid(cfg.pid_file(spec.name))
    if pid and pid_alive(pid) and pid_matches(pid, spec.needle):
        return AdoptedProc(pid)
    return None


def http_request(method, port, path, token, body=None, timeout=1.5, host="127.0.0.1"):
    """-> (status, text). Raises OSError/http.client.HTTPException when nothing answers."""
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        headers = {"X-Admin-Token": token} if token else {}
        data = None
        if body is not None:
            data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
        conn.request(method, path, body=data, headers=headers)
        response = conn.getresponse()
        return response.status, response.read(65536).decode("utf-8", "replace")
    finally:
        conn.close()


def health_ok(status):
    """A child that answers HTTP with anything below 500 is serving (401 and 404 are reported, not fatal)."""
    return 200 <= status < 500


def xsocket_ok(path):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(1.0)
    try:
        sock.connect(path)
        return True
    except OSError:
        return False
    finally:
        sock.close()


def port_in_use(port, host="127.0.0.1"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def probe_service(spec, token):
    """-> (healthy, detail). The token header goes only to a child that holds the token already (not hls)."""
    kind = spec.health[0]
    if kind == "xsocket":
        return (True, "X socket ok") if xsocket_ok(spec.health[1]) else (False, "X socket not answering")
    try:
        status, _ = http_request("GET", spec.health[1], spec.health[2],
                                 token if "SUB01_ADMIN_TOKEN" in spec.env else None)
    except (OSError, http.client.HTTPException) as exc:
        return False, f"no answer on port {spec.health[1]}: {type(exc).__name__}"
    return health_ok(status), f"http {status}"


def terminate_group(pid, grace, *, alive=pid_alive, signal_fn=signal_group, clock=time.monotonic, sleep=time.sleep):
    """SIGTERM the group, wait `grace` seconds, then SIGKILL. -> "gone" | "exited" | "killed"."""
    if not alive(pid):
        return "gone"
    signal_fn(pid, signal.SIGTERM)
    deadline = clock() + grace
    while clock() < deadline:
        if not alive(pid):
            return "exited"
        sleep(0.2)
    signal_fn(pid, signal.SIGKILL)
    for _ in range(25):
        if not alive(pid):
            break
        sleep(0.2)
    return "killed"


# ------------------------------------------------------------- supervisor

class Svc:
    def __init__(self, spec, cfg):
        self.spec = spec
        self.budget = RestartBudget(cfg.restart_max, cfg.restart_window)
        self.status = "pending"
        self.proc = None
        self.external = False
        self.starts = 0
        self.restarts_total = 0
        self.started_at = self.up_since = self.unhealthy_since = None
        self.next_attempt = 0.0
        self.last_probe = -1e9
        self.terminating = None            # (since, then, reason) while a SIGTERM is outstanding
        self.killed = False
        self.last_exit = None
        self.last_error = None
        self.detail = ""
        self.since_wall = None

    @property
    def pid(self):
        return self.proc.pid if self.proc is not None else None


class Supervisor:
    def __init__(self, cfg, specs, token="", *, clock=time.monotonic, wall=time.time, sleep=time.sleep,
                 spawn=None, adopt=None, probe=None, check=None, stop_present=None, signal_fn=signal_group,
                 remnants=kill_remnants, emit=None, log=None, in_use=port_in_use):
        self.cfg, self.specs, self.token = cfg, specs, token
        self.clock, self.wall, self.sleep = clock, wall, sleep
        self._spawn = spawn or (lambda spec: spawn_process(spec, cfg.log_file(spec.name)))
        self._adopt = adopt or (lambda spec: find_adoptable(cfg, spec))
        self._probe = probe or (lambda spec: probe_service(spec, token))
        self._check = check or preflight
        self._stop_present = stop_present or cfg.stop_file.exists
        self._signal, self._remnants, self._in_use = signal_fn, remnants, in_use
        self._emit_hook, self._log = emit, log or (lambda line: print(line, flush=True))
        self.svcs = {name: Svc(specs[name], cfg) for name in ORDER}
        self.stop_requested = False
        self.started_wall = wall()
        self._snapshot_at = -1e9

    # -- reporting
    def emit(self, kind, **fields):
        record = {"t": now_iso(self.wall()), "source": "streamer_up", "kind": kind, **fields}
        self._log(json.dumps(record))
        if self._emit_hook:
            self._emit_hook(record)
        else:
            try:
                fd = os.open(self.cfg.streamer_dir / "events.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
                try:
                    os.write(fd, (json.dumps(record, separators=(",", ":")) + "\n").encode())
                finally:
                    os.close(fd)
            except OSError:
                pass

    def statuses(self):
        return {name: svc.status for name, svc in self.svcs.items()}

    def snapshot(self):
        now = self.clock()
        services = {}
        for name, svc in self.svcs.items():
            services[name] = {
                "status": svc.status, "pid": svc.pid, "external": svc.external, "starts": svc.starts,
                "restarts_in_window": svc.budget.used(now), "restart_limit": svc.budget.limit,
                "restarts_total": svc.restarts_total, "last_exit": svc.last_exit, "last_error": svc.last_error,
                "detail": svc.detail, "since": svc.since_wall,
                "health": self._health_label(svc.spec)}
        return {"pid": os.getpid(), "started": now_iso(self.started_wall), "updated": now_iso(self.wall()),
                "stop": self._stop_present(), "stopping": self.stop_requested, "services": services}

    @staticmethod
    def _health_label(spec):
        return spec.health[1] if spec.health[0] == "xsocket" else f"http://127.0.0.1:{spec.health[1]}{spec.health[2]}"

    def write_snapshot(self, force=False):
        now = self.clock()
        if not force and now - self._snapshot_at < 2.0:
            return
        self._snapshot_at = now
        atomic_write(self.cfg.snapshot_file, json.dumps(self.snapshot(), indent=1))

    # -- one supervision step
    def tick(self):
        now = self.clock()
        self._control(now)
        stop = self._stop_present()
        before = self.statuses()
        for name in ORDER:
            self._step(self.svcs[name], now, stop)
        self.write_snapshot(force=self.statuses() != before)

    def _step(self, svc, now, stop):
        spec = svc.spec
        if spec.hold_on_stop:
            if stop and svc.proc is None:
                svc.status, svc.detail = "held", "held down by the STOP file"
                return
            if stop and svc.terminating is None:
                svc.terminating = (now, "held", "STOP file present")
                self._signal(svc.proc.pid, signal.SIGTERM)
            if not stop and svc.status == "held":
                svc.status, svc.detail = "pending", ""
        if svc.external:
            self._watch_external(svc, now)
            return
        if svc.proc is not None:
            code = svc.proc.poll()
            if code is None:
                self._running(svc, now)
                return
            self._exited(svc, code, now)
        if svc.status in ("pending", "backoff", "blocked") and now >= svc.next_attempt:
            verdict, why = start_gate(spec.name, self.statuses(), self.specs, first_start=svc.starts == 0)
            if verdict == "go":
                self._start(svc, now)
            elif verdict == "blocked":
                svc.status, svc.detail = "blocked", why
            else:
                svc.detail = why

    def _watch_external(self, svc, now):
        if now - svc.last_probe < 5.0:
            return
        svc.last_probe = now
        ok, _ = self._probe(svc.spec)
        if not ok:
            self.emit("external_lost", service=svc.spec.name)
            svc.external, svc.status, svc.detail, svc.next_attempt = False, "pending", "external X server went away", now

    def _running(self, svc, now):
        spec = svc.spec
        if svc.terminating:
            since, _, _ = svc.terminating
            if now - since > self.cfg.stop_grace and not svc.killed:
                svc.killed = True
                self._signal(svc.proc.pid, signal.SIGKILL)
            return
        interval = 1.0 if svc.status == "starting" else 5.0
        if now - svc.last_probe < interval:
            return
        svc.last_probe = now
        ok, svc.detail = self._probe(spec)
        if ok:
            if svc.status != "up":
                svc.status, svc.up_since, svc.since_wall = "up", now, self.wall()
                svc.last_error = None
                self.emit("service_up", service=spec.name, pid=svc.pid)
            svc.unhealthy_since = None
        elif svc.status == "starting":
            if now - svc.started_at > spec.start_timeout:
                self._begin_terminate(svc, now, "crash", f"not healthy {spec.start_timeout:.0f}s after start ({svc.detail})")
        elif svc.status == "up":
            svc.status, svc.unhealthy_since = "unhealthy", now
            self.emit("service_unhealthy", service=spec.name, detail=svc.detail)
        elif svc.status == "unhealthy" and now - svc.unhealthy_since > self.cfg.unhealthy_after:
            self._begin_terminate(svc, now, "crash", f"unhealthy for {self.cfg.unhealthy_after:.0f}s ({svc.detail})")

    def _begin_terminate(self, svc, now, then, reason):
        svc.terminating, svc.killed = (now, then, reason), False
        self.emit("service_terminating", service=svc.spec.name, reason=reason)
        self._signal(svc.proc.pid, signal.SIGTERM)

    def _exited(self, svc, code, now):
        spec = svc.spec
        pid = svc.proc.pid
        was_ours = not isinstance(svc.proc, AdoptedProc)
        svc.proc = None
        remove_quiet(self.cfg.pid_file(spec.name))
        if was_ours:
            self._remnants(pid)
        svc.last_exit = {"code": code, "t": now_iso(self.wall()), "pid": pid}
        svc.unhealthy_since = svc.up_since = None
        terminating, svc.terminating = svc.terminating, None
        # Whatever ran on this service's X server or ports dies with it.
        for other in self.svcs.values():
            if spec.name in other.spec.restart_with and other.proc is not None and other.terminating is None:
                self._begin_terminate(other, now, "pending", f"{spec.name} exited")
        if terminating and terminating[1] != "crash":
            svc.status = terminating[1]
            svc.detail = terminating[2]
            svc.next_attempt = now + 0.5
            self.emit("service_stopped", service=spec.name, code=code, then=terminating[1], reason=terminating[2])
            return
        self._register_failure(svc, now, terminating[2] if terminating else f"exited with code {code}")

    def _register_failure(self, svc, now, reason):
        spec = svc.spec
        svc.last_error = reason
        if svc.budget.allow(now):
            delay = svc.budget.delay(now)
            svc.budget.record(now)
            svc.restarts_total += 1
            svc.status, svc.next_attempt = "backoff", now + delay
            svc.detail = f"restart in {delay:.0f}s"
            self.emit("service_crashed", service=spec.name, reason=reason, restart_in=delay,
                      restarts_in_window=svc.budget.used(now))
        else:
            svc.status = "failed"
            svc.detail = f"left down: {svc.budget.limit} restarts in {svc.budget.window:.0f}s used up"
            self.emit("service_failed", service=spec.name, reason=reason, detail=svc.detail)

    def _start(self, svc, now):
        spec = svc.spec
        problem = self._check(spec)
        if problem:
            return self._register_failure(svc, now, problem)
        adopted = self._adopt(spec)
        if adopted is not None:
            svc.proc = adopted
            self.emit("service_adopted", service=spec.name, pid=adopted.pid)
        elif spec.adopt_existing and self._probe(spec)[0]:
            svc.external, svc.status, svc.detail, svc.starts = True, "up", "existing X server, not ours", svc.starts + 1
            svc.since_wall, svc.last_probe = self.wall(), now
            self.emit("service_external", service=spec.name)
            return
        elif spec.port and self._in_use(spec.port):
            return self._register_failure(svc, now, f"port {spec.port} is already in use by another process")
        else:
            try:
                svc.proc = self._spawn(spec)
            except OSError as exc:
                return self._register_failure(svc, now, f"cannot launch: {exc}")
            atomic_write(self.cfg.pid_file(spec.name), str(svc.proc.pid))
            self.emit("service_started", service=spec.name, pid=svc.proc.pid, argv=spec.argv)
        svc.status, svc.started_at, svc.last_probe, svc.since_wall = "starting", now, -1e9, self.wall()
        svc.starts += 1
        svc.detail, svc.killed = "starting", False

    # -- control files (restart <name>)
    def _control(self, now):
        try:
            names = sorted(os.listdir(self.cfg.ctl_dir))
        except OSError:
            return
        for entry in names:
            if not entry.startswith("restart-"):
                continue
            remove_quiet(self.cfg.ctl_dir / entry)
            name = entry[len("restart-"):]
            if name in self.svcs:
                self.restart(name, now)

    def restart(self, name, now=None):
        now = self.clock() if now is None else now
        svc = self.svcs[name]
        svc.budget.reset()
        svc.last_error = None
        self.emit("service_restart_requested", service=name)
        if svc.external:
            return
        if svc.proc is not None:
            if svc.terminating is None:
                self._begin_terminate(svc, now, "pending", "restart requested")
            else:
                svc.terminating = (svc.terminating[0], "pending", "restart requested")
        else:
            svc.status, svc.next_attempt, svc.detail = "pending", now, "restart requested"

    # -- life cycle
    def run(self):
        for name in ("SIGTERM", "SIGINT"):
            signal.signal(getattr(signal, name), lambda *_: setattr(self, "stop_requested", True))
        self.emit("supervisor_started", pid=os.getpid())
        self.write_snapshot(force=True)
        try:
            while not self.stop_requested:
                self.tick()
                self.sleep(TICK)
        finally:
            self.stop_all()

    def stop_all(self):
        """Reverse start order: SIGTERM, wait up to stop_grace for it, SIGKILL, next."""
        self.stop_requested = True
        self.emit("supervisor_stopping")
        for name in reversed(ORDER):
            svc = self.svcs[name]
            if svc.proc is not None:
                pid = svc.proc.pid
                alive = (lambda _pid, proc=svc.proc: proc.poll() is None)
                outcome = terminate_group(pid, self.cfg.stop_grace, alive=alive, signal_fn=self._signal,
                                          clock=self.clock, sleep=self.sleep)
                if not isinstance(svc.proc, AdoptedProc):
                    self._remnants(pid)
                self.emit("service_stopped", service=name, pid=pid, how=outcome)
                svc.proc = None
                remove_quiet(self.cfg.pid_file(name))
            svc.status = "stopped"
            svc.detail = "stopped by supervisor" if not svc.external else "external X server left running"
            svc.terminating = None
        self.write_snapshot(force=True)
        remove_quiet(self.cfg.pids_dir / "supervisor.pid")


# --------------------------------------------------------------- files

def atomic_write(path, text, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        os.write(fd, text.encode())
    finally:
        os.close(fd)
    os.replace(tmp, path)


def remove_quiet(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def ensure_dirs(cfg):
    for directory in (cfg.streamer_dir, cfg.pids_dir, cfg.logs_dir, cfg.ctl_dir):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)


def supervisor_pid(cfg):
    pid = read_pid(cfg.pids_dir / "supervisor.pid")
    return pid if pid and pid_alive(pid) and pid_matches(pid, "streamer_up") else None


def load_snapshot(cfg):
    try:
        return json.loads(cfg.snapshot_file.read_text())
    except (OSError, ValueError):
        return None


# ----------------------------------------------------------------- commands

def do_kill(cfg, token, *, post=http_request, signal_fn=signal_group, alive=pid_alive, wall=time.time,
            clock=time.monotonic, sleep=time.sleep):
    """The kill switch. Writes STOP, cuts speech through the voice server, takes the agent down.
    The desktop runner, the director, the voice server, the monitor feed, the HLS server and Xvfb are left
    running so the scene stays presentable (a monitor feed killed here could not cover the game's last
    texture with its neutral frame). Returns a result dict (never raises for a failing voice server)."""
    result = {"stop_file": None, "voice_stop": None, "agent": None}
    atomic_write(cfg.stop_file, json.dumps({"t": now_iso(wall()), "by": "streamer_up kill"}) + "\n")
    result["stop_file"] = str(cfg.stop_file)
    if not token:
        result["voice_stop"] = "skipped: no operator token"
    else:
        try:
            status, _ = post("POST", cfg.ports["voice"], "/stop", token, body={})
            result["voice_stop"] = f"http {status}"
        except (OSError, http.client.HTTPException) as exc:
            result["voice_stop"] = f"failed: {type(exc).__name__}"
    pid = read_pid(cfg.pid_file("agent"))
    if pid and alive(pid) and pid_matches(pid, "streamer_agent"):
        result["agent"] = terminate_group(pid, 5.0, alive=alive, signal_fn=signal_fn, clock=clock, sleep=sleep)
    else:
        result["agent"] = "not running"
    return result


def cmd_kill(cfg, args):
    ensure_dirs(cfg)
    try:
        token = read_token(cfg)
    except (OSError, ValueError):
        token = None            # the kill switch must work without it: only the voice /stop call needs it
    result = do_kill(cfg, token)
    print(f"STOP file written: {result['stop_file']}")
    print(f"voice /stop: {result['voice_stop']}")
    print(f"agent: {result['agent']} (held down while STOP exists)")
    print("desktop runner, director, voice server, monitor feed, HLS server and Xvfb are still running. "
          "`streamer_up.py resume` clears STOP.")
    return 0


def cmd_resume(cfg, args):
    existed = cfg.stop_file.exists()
    remove_quiet(cfg.stop_file)
    print("STOP file removed; the supervisor starts the agent again" if existed else "no STOP file")
    return 0


def check_root(args):
    if os.geteuid() == 0 and not args.allow_root:
        print("refusing to run as root: files would belong to root. Use: runuser -u unreal -- "
              "python3 scripts/streamer_up.py start ... (or --allow-root)", file=sys.stderr)
        return False
    return True


def describe_plan(cfg, specs):
    lines = []
    for name in ORDER:
        spec = specs[name]
        lines.append(f"[{name}] requires={list(spec.requires) or '-'} health={Supervisor._health_label(spec)}")
        lines.append(f"    cwd  {spec.cwd}")
        lines.append(f"    cmd  {shlex.join(spec.argv)}")
        lines.append(f"    env  {json.dumps(redacted_env(spec.env), sort_keys=True)}")
        lines.append(f"    log  {cfg.log_file(name)}   pid {cfg.pid_file(name)}")
    return "\n".join(lines)


def cmd_start(cfg, args, raw_argv):
    try:
        token = read_token(cfg)
    except (OSError, ValueError) as exc:
        if not args.dry_run:
            raise
        token = "x" * MIN_TOKEN
        print(f"WARNING token not readable ({exc}); the plan below uses a placeholder")
    specs = build_specs(cfg, token)
    if args.dry_run:
        print(describe_plan(cfg, specs))
        for spec in specs.values():
            problem = preflight(spec)
            if problem:
                print(f"PROBLEM [{spec.name}] {problem}")
        for note in environment_warnings(cfg):
            print("WARNING", note)
        return 0
    if not check_root(args):
        return 2
    ensure_dirs(cfg)
    pid = supervisor_pid(cfg)
    if pid:
        print(f"supervisor already running (pid {pid}); `status` shows the services")
        return cmd_status(cfg, args)
    if not args.foreground:
        log = os.open(cfg.logs_dir / "supervisor.log", os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        child = subprocess.Popen([sys.executable, os.path.abspath(__file__)] + raw_argv + ["--foreground"],
                                 stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                 start_new_session=True, close_fds=True)
        os.close(log)
        print(f"supervisor started (pid {child.pid}), log {cfg.logs_dir / 'supervisor.log'}")
        return wait_settled(cfg, args, child)
    lock = open(cfg.pids_dir / "supervisor.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("another supervisor holds the lock", file=sys.stderr)
        return 1
    atomic_write(cfg.pids_dir / "supervisor.pid", str(os.getpid()))
    if cfg.stop_file.exists():
        print(f"WARNING STOP file present ({cfg.stop_file}): the agent stays down until `resume`", flush=True)
    for note in environment_warnings(cfg):
        print("WARNING", note, flush=True)
    Supervisor(cfg, specs, token).run()
    return 0


def wait_settled(cfg, args, child):
    """Wait for the detached supervisor to publish a snapshot and for every service to settle, then show status."""
    deadline = time.monotonic() + max(0.0, args.wait)
    time.sleep(0.5)
    while time.monotonic() < deadline:
        if child.poll() is not None:
            print(f"supervisor exited with code {child.returncode}; see {cfg.logs_dir / 'supervisor.log'}", file=sys.stderr)
            return 1
        snap = load_snapshot(cfg)
        if snap and snap.get("pid") == child.pid and all(
                s["status"] in SETTLED for s in snap["services"].values()):
            break
        time.sleep(1.0)
    return cmd_status(cfg, args)


def cmd_stop(cfg, args):
    pid = supervisor_pid(cfg)
    code = 0
    if pid:
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + cfg.stop_grace * len(ORDER) + 15
        while pid_alive(pid) and time.monotonic() < deadline:
            time.sleep(0.5)
        if pid_alive(pid):
            print(f"supervisor {pid} did not exit; sending SIGKILL", file=sys.stderr)
            os.kill(pid, signal.SIGKILL)
            code = 1
        else:
            print(f"supervisor {pid} stopped")
    else:
        print("no supervisor running")
    needles = {name: spec.needle for name, spec in build_specs(cfg, "x" * MIN_TOKEN).items()}
    for name in reversed(ORDER):
        orphan = read_pid(cfg.pid_file(name))
        if orphan and pid_alive(orphan) and pid_matches(orphan, needles[name]):
            outcome = terminate_group(orphan, cfg.stop_grace)
            print(f"{name}: orphan pid {orphan} {outcome}")
        remove_quiet(cfg.pid_file(name))
    remove_quiet(cfg.pids_dir / "supervisor.pid")
    return code


def collect_status(cfg):
    token = None
    try:
        token = read_token(cfg)
    except (OSError, ValueError):
        pass
    snap = load_snapshot(cfg)
    sup = supervisor_pid(cfg)
    specs = build_specs(cfg, token or "x" * MIN_TOKEN)
    services = {}
    for name in ORDER:
        spec, pid = specs[name], read_pid(cfg.pid_file(name))
        info = dict((snap or {}).get("services", {}).get(name, {}))
        running = bool(pid and pid_alive(pid) and pid_matches(pid, spec.needle))
        healthy, detail = (probe_service(spec, token) if token and (running or info.get("external")) else (False, "not running"))
        info.update({"pid": pid if running else info.get("pid") if info.get("external") else None,
                     "running": running or bool(info.get("external")), "healthy": healthy, "probe": detail})
        if not sup:
            info["status"] = "orphan" if running else "down"
        services[name] = info
    director = None
    if token and services["director"]["healthy"]:
        try:
            status, text = http_request("GET", cfg.ports["director"], "/director/state", token, timeout=2.0)
            data = json.loads(text) if status == 200 else {}
            director = {k: data.get(k) for k in ("recording", "voice", "game_source", "restarts", "last_error",
                                                 "segments_total", "layout", "live_layout", "encoder", "cam2",
                                                 "privacy", "desktop_hidden")}
            director["latest_segment"] = (data.get("segments") or [{}])[-1].get("name")
            director["fps_measured"] = (data.get("output") or {}).get("fps_measured")
        except (OSError, ValueError, http.client.HTTPException, AttributeError):
            pass
    return {"supervisor": sup, "stop": cfg.stop_file.exists(), "token": bool(token), "services": services,
            "director": director, "monitor": monitor_summary(cfg) if services["monitor"]["running"] else None,
            "snapshot_at": (snap or {}).get("updated")}


def monitor_summary(cfg, request=None):
    """What the in-game monitor shows now, from the feed's /healthz (no token needed): showing screen | neutral |
    pending, the privacy reasons. Also for a 503 (the feed has no neutral frame: `ok` false)."""
    try:
        status, text = (request or http_request)("GET", cfg.ports["monitor"], "/healthz", None, timeout=2.0)
        data = json.loads(text) if status in (200, 503) else {}
        privacy = data.get("privacy") or {}
        return {"ok": data.get("ok"), "showing": data.get("showing"), "private": privacy.get("private"),
                "reasons": privacy.get("reasons"), "since": privacy.get("since"), "display": data.get("display"),
                "reader": data.get("reader"), "ffmpeg": data.get("ffmpeg"), "fps_in": data.get("fps_in")}
    except (OSError, ValueError, http.client.HTTPException, AttributeError):
        return None


def cmd_status(cfg, args):
    report = collect_status(cfg)
    if args.json:
        print(json.dumps(report, indent=1))
    else:
        print(f"supervisor: {'pid ' + str(report['supervisor']) if report['supervisor'] else 'NOT RUNNING'}"
              f"   STOP file: {'PRESENT (kill switch active)' if report['stop'] else 'absent'}")
        if not report["token"]:
            print("WARNING operator token unreadable: health probes skipped")
        print(f"{'service':9} {'state':10} {'pid':>7}  {'restarts':8} {'health':12} note")
        for name in ORDER:
            s = report["services"][name]
            used = f"{s.get('restarts_in_window', 0)}/{s.get('restart_limit', cfg.restart_max)}"
            note = s.get("last_error") or s.get("detail") or ""
            print(f"{name:9} {s.get('status', '-'):10} {s.get('pid') or '-':>7}  {used:8} {s['probe'][:12]:12} {note[:90]}")
        if report["director"]:
            print("director:", json.dumps(report["director"]))
        if report["monitor"]:
            print("monitor:", json.dumps(report["monitor"]))
    ok = bool(report["supervisor"]) and all(s.get("status") == "up" and s["healthy"] for s in report["services"].values())
    return 0 if ok else 1


def cmd_restart(cfg, args):
    if args.name not in ORDER:
        print(f"unknown service {args.name!r}; choose from {', '.join(ORDER)}", file=sys.stderr)
        return 2
    if not supervisor_pid(cfg):
        print("no supervisor running; start it with `start`", file=sys.stderr)
        return 1
    if args.name == "agent" and cfg.stop_file.exists():
        print("STOP file present: run `resume` first (the kill switch holds the agent down)", file=sys.stderr)
        return 1

    def current():
        return (load_snapshot(cfg) or {}).get("services", {}).get(args.name, {}) or {}

    starts_before = current().get("starts", 0)
    request = cfg.ctl_dir / f"restart-{args.name}"
    atomic_write(request, now_iso() + "\n")
    deadline = time.monotonic() + args.wait
    info = {}
    while time.monotonic() < deadline:
        time.sleep(1.0)
        info = current()
        if request.exists():
            continue                      # the supervisor has not picked the request up yet
        if info.get("status") == "up" and (info.get("starts", 0) > starts_before or info.get("external")):
            print(f"{args.name}: up, pid {info.get('pid')}")
            return 0
    print(f"{args.name}: not up after {args.wait:.0f}s ({info.get('status')}: {info.get('last_error') or info.get('detail')})",
          file=sys.stderr)
    return 1


# --------------------------------------------------------------------- cli

def parse_kv(items, what, split_args=False):
    out = {}
    for item in items or []:
        name, sep, value = item.partition("=")
        if not sep or name not in ORDER:
            raise ValueError(f"{what} expects NAME=VALUE with NAME in {', '.join(ORDER)}: {item!r}")
        out.setdefault(name, [] if split_args else {})
        if split_args:
            out[name] += shlex.split(value)
        else:
            key, sep2, val = value.partition("=")
            if not sep2:
                raise ValueError(f"{what} expects NAME=KEY=VALUE: {item!r}")
            out[name][key] = val
    return out


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--streamer-dir", default=os.environ.get("STREAMER_DIR", DEFAULT_STREAMER_DIR))
    common.add_argument("--token-file", help=f"operator token file (else SUB01_ADMIN_TOKEN, else {DEFAULT_TOKEN_FILE})")
    common.add_argument("--source", default=DEFAULT_SOURCE, help="repository root on the pod")
    common.add_argument("--display", default=":102", help="desktop X display")
    common.add_argument("--game-display", default=":99.0", help="game X display the director records")
    for name, port in DEFAULT_PORTS.items():
        common.add_argument(f"--{name}-port", type=int, default=port)
        common.add_argument(f"--{name}-python", default=DEFAULT_PYTHON[name])
    common.add_argument("--backend-port", type=int, default=BACKEND_PORT)
    common.add_argument("--hls-dir", help="directory the hls service serves (default <streamer-dir>/hls); keep it the "
                                          "director's --hls-dir (start --dry-run warns when they differ)")
    common.add_argument("--library-path", default=DEFAULT_LIBRARY_PATH, help="LD_LIBRARY_PATH of the desktop runner")
    common.add_argument("--hf-home", default=DEFAULT_HF_HOME, help="HF_HOME of the voice server")
    common.add_argument("--voice-config", help="voice server settings JSON (default <streamer-dir>/voice/voice.json, "
                                                "passed only if the file exists)")
    common.add_argument("--xvfb", default="Xvfb")
    common.add_argument("--xvfb-screen", default="1920x1080x24")
    common.add_argument("--health-path", action="append", default=[], metavar="NAME=/path")
    common.add_argument("--child-arg", action="append", default=[], metavar="NAME='--flag value'",
                        help="extra command-line arguments for one child (repeatable)")
    common.add_argument("--child-env", action="append", default=[], metavar="NAME=KEY=VALUE")
    common.add_argument("--stop-grace", type=float, default=15.0, help="seconds before SIGKILL")
    common.add_argument("--restart-max", type=int, default=5)
    common.add_argument("--restart-window", type=float, default=600.0, help="seconds")
    common.add_argument("--unhealthy-after", type=float, default=120.0,
                        help="restart a child whose health URL has failed this long after it was up")
    common.add_argument("--json", action="store_true")
    common.add_argument("--wait", type=float, default=60.0, help="seconds start/restart wait for the result")
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=__doc__.split("\n", 2)[2])
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start", parents=[common], help="start the supervisor and the services")
    start.add_argument("--foreground", action="store_true", help="stay attached (systemd, tmux, debugging)")
    start.add_argument("--dry-run", action="store_true", help="print the exact command lines and checks, launch nothing")
    start.add_argument("--allow-root", action="store_true")
    for name, text in (("stop", "stop everything in reverse order"), ("status", "show supervisor and services"),
                       ("kill", "kill switch: STOP file, voice /stop, agent down"), ("resume", "remove the STOP file")):
        sub.add_parser(name, parents=[common], help=text)
    restart = sub.add_parser("restart", parents=[common], help="restart one service and reset its restart budget")
    restart.add_argument("name", help="one of " + ", ".join(ORDER))
    return parser


def config_from_args(args):
    ports = {n: getattr(args, f"{n}_port") for n in DEFAULT_PORTS}
    pythons = {n: getattr(args, f"{n}_python") for n in DEFAULT_PORTS}
    health = {}
    for item in args.health_path:
        name, _, path = item.partition("=")
        if name not in HEALTH_PATH or not path.startswith("/"):
            raise ValueError(f"--health-path expects NAME=/path with NAME in {', '.join(HEALTH_PATH)}: {item!r}")
        health[name] = path
    return Config(streamer_dir=args.streamer_dir, token_file=args.token_file, source=args.source, display=args.display,
                  game_display=args.game_display, ports=ports, pythons=pythons, library_path=args.library_path,
                  hf_home=args.hf_home, voice_config=args.voice_config, xvfb=args.xvfb, xvfb_screen=args.xvfb_screen, health=health,
                  child_args=parse_kv(args.child_arg, "--child-arg", split_args=True),
                  child_env=parse_kv(args.child_env, "--child-env"), stop_grace=args.stop_grace,
                  restart_max=args.restart_max, restart_window=args.restart_window,
                  unhealthy_after=args.unhealthy_after, backend_port=args.backend_port, hls_dir=args.hls_dir)


def main(argv=None):
    raw = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(raw)
    try:
        cfg = config_from_args(args)
        handlers = {"start": lambda: cmd_start(cfg, args, raw), "stop": lambda: cmd_stop(cfg, args),
                    "status": lambda: cmd_status(cfg, args), "kill": lambda: cmd_kill(cfg, args),
                    "resume": lambda: cmd_resume(cfg, args), "restart": lambda: cmd_restart(cfg, args)}
        return handlers[args.command]()
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
