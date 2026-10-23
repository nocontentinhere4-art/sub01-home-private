"""Streamer supervisor: command lines, restart budget, start order and dependencies, kill switch, stop.

No service is launched and no signal reaches a real process: spawning, probing and signalling are
replaced by a fake world with a fake clock, and subprocess.Popen is monkeypatched where it is exercised.
"""

import importlib.util
import json
import os
import signal
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("streamer_up", ROOT / "scripts/streamer_up.py")
up = importlib.util.module_from_spec(spec)
spec.loader.exec_module(up)
TOKEN = "operator-credential-test"


def make_cfg(tmp_path, **kw):
    kw.setdefault("environ", {"PATH": "/usr/bin:/bin"})
    return up.Config(streamer_dir=tmp_path / "sd", token_file=tmp_path / "token", source=tmp_path / "src", **kw)


# ------------------------------------------------------------ the fake world

class FakeProc:
    def __init__(self, world, name, pid):
        self.world, self.name, self.pid, self.returncode, self.born = world, name, pid, None, world.t

    def poll(self):
        return self.returncode


class World:
    """Fake clock, fake processes. A service is healthy `up_delay` seconds after it was spawned."""

    def __init__(self):
        self.t, self.next_pid, self.stop = 1000.0, 100, False
        self.procs, self.spawned, self.signals, self.events = {}, [], [], []
        self.up_delay, self.unhealthy, self.stubborn, self.external = 2.0, set(), set(), set()
        self.statuses_at_spawn, self.sup = {}, None
        self.fail_check, self.spawn_pids = {}, {}

    def clock(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds

    def live(self, name):
        proc = self.procs.get(name)
        return proc if proc is not None and proc.returncode is None else None

    def spawn(self, spec):
        self.next_pid += 1
        proc = FakeProc(self, spec.name, self.next_pid)
        self.procs[spec.name] = proc
        self.spawned.append(spec.name)
        self.spawn_pids.setdefault(spec.name, []).append(proc.pid)
        self.statuses_at_spawn[len(self.spawned) - 1] = self.sup.statuses()
        return proc

    def probe(self, spec):
        if spec.name in self.external and self.live(spec.name) is None:
            return True, "external"
        proc = self.live(spec.name)
        ok = proc is not None and spec.name not in self.unhealthy and self.t - proc.born >= self.up_delay
        return ok, "fake"

    def signal(self, pid, sig):
        self.signals.append((pid, sig))
        for proc in self.procs.values():
            if proc.pid == pid and proc.returncode is None:
                if sig == signal.SIGKILL or (sig == signal.SIGTERM and proc.name not in self.stubborn):
                    proc.returncode = -int(sig)
                return True
        return False

    def crash(self, name, code=1):
        self.procs[name].returncode = code

    def check(self, spec):
        return self.fail_check.get(spec.name)


def supervisor(tmp_path, world=None, **cfg_kw):
    world = world or World()
    cfg = make_cfg(tmp_path, **cfg_kw)
    up.ensure_dirs(cfg)
    specs = up.build_specs(cfg, TOKEN)
    sup = up.Supervisor(cfg, specs, TOKEN, clock=world.clock, wall=world.clock, sleep=world.sleep,
                        spawn=world.spawn, adopt=lambda spec: None, probe=world.probe, check=world.check,
                        stop_present=lambda: world.stop, signal_fn=world.signal, remnants=lambda pid: None,
                        emit=world.events.append, log=lambda line: None, in_use=lambda port: False)
    world.sup = sup
    return sup, world


def ticks(sup, world, count, step=1.0):
    for _ in range(count):
        sup.tick()
        world.t += step


def kinds(world, kind=None, service=None):
    return [e for e in world.events if (kind is None or e["kind"] == kind) and (service is None or e.get("service") == service)]


# ------------------------------------------------------- defaults, commands

def test_defaults_follow_the_plan_and_the_brief():
    args = up.build_parser().parse_args(["start"])
    cfg = up.config_from_args(args)
    assert cfg.ports == {"desktop": 8832, "voice": 8835, "agent": 8836, "director": 8837}
    assert str(cfg.streamer_dir) == "/home/unreal/.sub01-private/streamer"
    assert str(cfg.source) == "/home/unreal/.sub01-private/latest-source-20261023"
    assert cfg.display == ":102" and cfg.stop_grace == 15.0 and (cfg.restart_max, cfg.restart_window) == (5, 600.0)
    assert cfg.pythons == {"desktop": "/home/unreal/.sub01-private/city-readonly-browser/venv/bin/python",
                           "voice": "/home/unreal/voice-rt-venv/bin/python", "agent": "/home/unreal/venv/bin/python",
                           "director": "/home/unreal/venv/bin/python"}
    assert cfg.library_path == "/workspace/sub01-home-private/claude-12h/libs/usr/lib/x86_64-linux-gnu"
    assert cfg.hf_home == "/home/unreal/hf-cache"
    assert up.DEFAULT_TOKEN_FILE == "/home/unreal/.sub01-private/operator-token"
    assert up.ORDER == ("xvfb", "desktop", "voice", "agent", "director")


def test_each_service_gets_the_command_line_and_environment_of_the_brief(tmp_path):
    cfg = make_cfg(tmp_path, environ={"PATH": "/usr/bin", "ANTHROPIC_API_KEY": "sk-secret", "SHELL": "/bin/zsh",
                                      "STREAMER_MODEL": "m", "LD_LIBRARY_PATH": "/old"})
    specs = up.build_specs(cfg, TOKEN)
    assert list(specs) == list(up.ORDER)
    src = str(tmp_path / "src")
    assert specs["xvfb"].argv[:6] == ["Xvfb", ":102", "-screen", "0", "1920x1080x24", "-nolisten"]
    desktop, voice, agent, director = (specs[n] for n in ("desktop", "voice", "agent", "director"))
    sd_dir = str(tmp_path / "sd")
    assert desktop.argv == ["/home/unreal/.sub01-private/city-readonly-browser/venv/bin/python",
                            src + "/scripts/streamer_desktop.py", "--data-dir", sd_dir + "/desktop", "--display", ":102",
                            "--home-origin", "http://127.0.0.1:8830"]
    assert desktop.env["DISPLAY"] == ":102" and desktop.env["LD_LIBRARY_PATH"] == cfg.library_path + ":/old"
    assert voice.argv == ["/home/unreal/voice-rt-venv/bin/python", src + "/scripts/voice_server.py", "--streamer-dir", sd_dir]
    assert voice.env["HF_HOME"] == "/home/unreal/hf-cache" and "DISPLAY" not in voice.env
    assert agent.argv == ["/home/unreal/venv/bin/python", src + "/streamer_agent.py", "--streamer-dir", sd_dir,
                          "--desktop-url", "http://127.0.0.1:8832", "--backend-url", "http://127.0.0.1:8830",
                          "--voice-url", "http://127.0.0.1:8835", "--director-url", "http://127.0.0.1:8837"]
    assert director.argv == ["/home/unreal/venv/bin/python", src + "/scripts/streamer_director.py", "--streamer-dir", sd_dir,
                             "--desktop-display", ":102.0", "--game-display", ":99.0", "--port", "8837"]
    assert [specs[n].health for n in ("desktop", "voice", "agent", "director")] == [
        ("http", 8832, "/healthz"), ("http", 8835, "/healthz"), ("http", 8836, "/healthz"), ("http", 8837, "/healthz")]
    assert specs["xvfb"].health == ("xsocket", "/tmp/.X11-unix/X102")
    assert all(specs[n].env["STREAMER_DIR"] == str(tmp_path / "sd") for n in ("desktop", "voice", "agent", "director"))


def test_the_token_never_appears_in_a_command_line_and_keys_reach_only_the_agent(tmp_path):
    cfg = make_cfg(tmp_path, environ={"PATH": "/usr/bin", "ANTHROPIC_API_KEY": "sk-secret", "OPENROUTER_API_KEY": "or-secret"})
    specs = up.build_specs(cfg, TOKEN)
    for spec in specs.values():
        assert TOKEN not in " ".join(spec.argv) and "sk-secret" not in " ".join(spec.argv)
    assert "SUB01_ADMIN_TOKEN" not in specs["xvfb"].env
    assert all(specs[n].env["SUB01_ADMIN_TOKEN"] == TOKEN for n in ("desktop", "voice", "agent", "director"))
    assert specs["agent"].env["ANTHROPIC_API_KEY"] == "sk-secret"
    for name in ("xvfb", "desktop", "voice", "director"):
        assert "ANTHROPIC_API_KEY" not in specs[name].env and "OPENROUTER_API_KEY" not in specs[name].env
    plan = up.describe_plan(cfg, specs)
    assert TOKEN not in plan and "sk-secret" not in plan and "***" in plan
    assert up.redacted_env({"SUB01_ADMIN_TOKEN": TOKEN, "X_API_KEY": "k", "HOME": "/h"}) == {
        "SUB01_ADMIN_TOKEN": "***", "X_API_KEY": "***", "HOME": "/h"}


def test_ports_paths_and_extras_are_configurable_by_flags(tmp_path):
    args = up.build_parser().parse_args([
        "start", "--streamer-dir", str(tmp_path / "x"), "--source", "/srv/repo", "--display", ":150",
        "--desktop-port", "9032", "--voice-port", "9035", "--agent-port", "9036", "--director-port", "9037",
        "--voice-python", "/opt/py", "--hf-home", "/hf", "--library-path", "/libs",
        "--child-arg", "voice=--engine mock --seed 3", "--child-env", "voice=FOO=bar",
        "--health-path", "agent=/state", "--restart-max", "2", "--stop-grace", "3"])
    cfg = up.config_from_args(args)
    specs = up.build_specs(cfg, TOKEN)
    assert specs["xvfb"].argv[1] == ":150" and specs["desktop"].env["DISPLAY"] == ":150"
    assert specs["voice"].argv == ["/opt/py", "/srv/repo/scripts/voice_server.py", "--streamer-dir", str(tmp_path / "x"),
                                   "--port", "9035", "--engine", "mock", "--seed", "3"]
    assert specs["voice"].env["FOO"] == "bar" and specs["voice"].env["HF_HOME"] == "/hf"
    assert specs["desktop"].argv[-2:] == ["--port", "9032"] and specs["desktop"].argv[specs["desktop"].argv.index("--display") + 1] == ":150"
    assert specs["agent"].argv[-2:] == ["--status-port", "9036"]           # the agent's own flag name
    assert specs["agent"].argv[specs["agent"].argv.index("--voice-url") + 1] == "http://127.0.0.1:9035"
    assert specs["director"].argv[-2:] == ["--port", "9037"]
    assert specs["agent"].health == ("http", 9036, "/state")
    assert specs["agent"].env["STREAMER_VOICE_URL"] == "http://127.0.0.1:9035"
    assert (cfg.restart_max, cfg.stop_grace) == (2, 3.0)
    for bad in (["--child-arg", "nobody=--x"], ["--child-env", "voice=NOVALUE"], ["--health-path", "voice=nope"]):
        with pytest.raises(ValueError):
            up.config_from_args(up.build_parser().parse_args(["start", *bad]))


def test_voice_config_is_passed_only_when_the_file_exists(tmp_path):
    cfg = make_cfg(tmp_path)
    assert "--voice-config" not in up.build_specs(cfg, TOKEN)["voice"].argv
    (tmp_path / "sd" / "voice").mkdir(parents=True)
    (tmp_path / "sd" / "voice" / "voice.json").write_text("{}")
    argv = up.build_specs(cfg, TOKEN)["voice"].argv
    assert argv[-2:] == ["--voice-config", str(tmp_path / "sd" / "voice" / "voice.json")]
    other = up.build_specs(make_cfg(tmp_path, voice_config=tmp_path / "elsewhere.json"), TOKEN)["voice"].argv
    assert "--voice-config" not in other


def test_token_comes_from_the_flag_then_the_environment_and_is_checked(tmp_path):
    (tmp_path / "token").write_text("file-credential-123\n")
    cfg = make_cfg(tmp_path, environ={"SUB01_ADMIN_TOKEN": "env-credential-123"})
    assert up.read_token(cfg) == "file-credential-123"
    no_flag = up.Config(streamer_dir=tmp_path, environ={"SUB01_ADMIN_TOKEN": "env-credential-123"})
    assert up.read_token(no_flag) == "env-credential-123"
    (tmp_path / "token").write_text("short")
    with pytest.raises(ValueError):
        up.read_token(cfg)


def test_preflight_names_a_missing_interpreter_or_script(tmp_path):
    cfg = make_cfg(tmp_path)
    spec = up.build_specs(cfg, TOKEN)["voice"]
    assert "python not found" in up.preflight(spec)
    py = tmp_path / "py"
    py.write_text("#!/bin/sh\n")
    py.chmod(0o755)
    spec.python = str(py)
    assert "script not found" in up.preflight(spec)
    (tmp_path / "src" / "scripts").mkdir(parents=True)
    (tmp_path / "src" / "scripts" / "voice_server.py").write_text("")
    assert up.preflight(spec) is None


# ---------------------------------------------------------- restart budget

def test_restart_budget_allows_five_per_ten_minutes():
    budget = up.RestartBudget(5, 600.0)
    for n in range(5):
        assert budget.allow(100.0 + n)
        budget.record(100.0 + n)
    assert not budget.allow(110.0)                    # a sixth restart inside the window is refused
    assert not budget.allow(100.0 + 599)
    assert budget.allow(100.0 + 600)                  # the first one has aged out
    assert budget.used(100.0 + 600) == 4
    budget.reset()
    assert budget.used(0) == 0 and budget.allow(0)


def test_restart_delay_doubles_then_caps():
    budget = up.RestartBudget(10, 600.0)
    delays = []
    for _ in range(7):
        delays.append(budget.delay(0.0))
        budget.record(0.0)
    assert delays == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0]


def test_a_crashing_service_is_restarted_five_times_then_left_down_and_reported(tmp_path):
    sup, world = supervisor(tmp_path)
    ticks(sup, world, 12)
    assert sup.statuses()["voice"] == "up"
    for crash in range(6):
        world.crash("voice")
        ticks(sup, world, 40)                         # long enough for the backoff to expire
        if crash < 5:
            assert sup.statuses()["voice"] == "up", crash
    assert sup.statuses()["voice"] == "failed"
    assert world.spawned.count("voice") == 6          # one start plus exactly five restarts
    failed = kinds(world, "service_failed", "voice")
    assert len(failed) == 1 and "left down" in failed[0]["detail"]
    assert len(kinds(world, "service_crashed", "voice")) == 5
    spawns = world.spawned.count("voice")
    ticks(sup, world, 60)
    assert world.spawned.count("voice") == spawns     # nobody brings it back on its own
    snap = sup.snapshot()["services"]["voice"]
    assert snap["status"] == "failed" and snap["restarts_in_window"] == 5 and "left down" in snap["detail"]
    other = sup.snapshot()["services"]
    assert other["desktop"]["status"] == "up" and other["director"]["status"] == "up"      # the rest keeps running


def test_old_crashes_age_out_of_the_budget(tmp_path):
    sup, world = supervisor(tmp_path)
    ticks(sup, world, 12)
    for _ in range(5):
        world.crash("desktop")
        ticks(sup, world, 40)
    assert sup.statuses()["desktop"] == "up" and sup.svcs["desktop"].budget.used(world.t) == 5
    world.t += 601                                     # ten quiet minutes
    world.crash("desktop")
    ticks(sup, world, 10)
    assert sup.statuses()["desktop"] == "up" and sup.svcs["desktop"].budget.used(world.t) == 1


def test_restart_by_name_clears_a_failed_service_and_its_budget(tmp_path):
    sup, world = supervisor(tmp_path, restart_max=1)
    ticks(sup, world, 12)
    world.crash("agent")
    ticks(sup, world, 5)
    world.crash("agent")
    ticks(sup, world, 5)
    assert sup.statuses()["agent"] == "failed"
    sup.restart("agent")
    assert sup.svcs["agent"].budget.used(world.t) == 0
    ticks(sup, world, 8)
    assert sup.statuses()["agent"] == "up"


def test_restart_of_a_running_service_terminates_and_starts_it_again_without_using_budget(tmp_path):
    sup, world = supervisor(tmp_path)
    ticks(sup, world, 12)
    first = world.procs["voice"].pid
    cfg = sup.cfg
    (cfg.ctl_dir / "restart-voice").write_text("x")
    (cfg.ctl_dir / "restart-nonsense").write_text("x")
    ticks(sup, world, 8)
    assert not (cfg.ctl_dir / "restart-voice").exists() and not (cfg.ctl_dir / "restart-nonsense").exists()
    assert (first, signal.SIGTERM) in world.signals
    assert sup.statuses()["voice"] == "up" and world.procs["voice"].pid != first
    assert sup.svcs["voice"].budget.used(world.t) == 0 and world.spawned.count("voice") == 2


def test_a_service_that_never_gets_healthy_is_restarted_as_a_crash(tmp_path):
    world = World()
    world.unhealthy.add("voice")
    sup, world = supervisor(tmp_path, world)
    sup.specs["voice"].start_timeout = 10.0
    ticks(sup, world, 40)
    assert (world.spawn_pids["voice"][0], signal.SIGTERM) in world.signals
    assert kinds(world, "service_crashed", "voice") and "not healthy 10s after start" in kinds(world, "service_crashed", "voice")[0]["reason"]


def test_a_service_unhealthy_for_too_long_after_being_up_is_restarted(tmp_path):
    sup, world = supervisor(tmp_path, unhealthy_after=30.0)
    ticks(sup, world, 12)
    world.unhealthy.add("desktop")
    ticks(sup, world, 10)
    assert sup.statuses()["desktop"] == "unhealthy"
    pid = world.procs["desktop"].pid
    ticks(sup, world, 30)
    assert (pid, signal.SIGTERM) in world.signals
    world.unhealthy.clear()
    ticks(sup, world, 12)
    assert sup.statuses()["desktop"] == "up" and world.procs["desktop"].pid != pid


# ------------------------------------------------------ order, dependencies

def test_services_start_in_order_each_after_the_one_before_is_up(tmp_path):
    sup, world = supervisor(tmp_path)
    ticks(sup, world, 30)
    assert world.spawned == ["xvfb", "desktop", "voice", "agent", "director"]
    for index, name in enumerate(world.spawned):
        before = world.statuses_at_spawn[index]
        assert all(before[earlier] == "up" for earlier in up.ORDER[:index]), (name, before)
    assert set(sup.statuses().values()) == {"up"}


def test_start_gate_rules():
    specs = up.build_specs(make_cfg(Path("/nonexistent")), TOKEN)
    gate = up.start_gate
    assert gate("xvfb", {}, specs, True) == ("go", "")
    assert gate("desktop", {"xvfb": "starting"}, specs, True) == ("wait", "waiting for xvfb")
    assert gate("desktop", {"xvfb": "up"}, specs, True) == ("go", "")
    # on the first start a service waits for EVERY earlier one to settle, requirement or not
    assert gate("agent", {"xvfb": "up", "desktop": "up", "voice": "starting"}, specs, True)[0] == "wait"
    assert gate("agent", {"xvfb": "up", "desktop": "up", "voice": "backoff"}, specs, True) == ("go", "")
    assert gate("agent", {"xvfb": "up", "desktop": "up", "voice": "failed"}, specs, True) == ("go", "")
    # a requirement must be up, whatever the order
    assert gate("agent", {"xvfb": "up", "desktop": "backoff", "voice": "up"}, specs, True) == ("blocked", "desktop is not up")
    assert gate("agent", {"xvfb": "up", "desktop": "failed", "voice": "up"}, specs, False) == ("blocked", "desktop failed")
    assert gate("director", {"xvfb": "failed"}, specs, False) == ("blocked", "xvfb failed")
    # after the first start only requirements count: a restarting director does not wait for the agent
    assert gate("director", {"xvfb": "up", "agent": "starting"}, specs, False) == ("go", "")
    assert specs["desktop"].requires == ("xvfb",) and specs["agent"].requires == ("desktop",)
    assert specs["director"].requires == ("xvfb",) and specs["voice"].requires == ()


def test_a_failed_requirement_blocks_dependents_but_not_independent_services(tmp_path):
    world = World()
    world.fail_check["xvfb"] = "Xvfb not found in PATH"
    sup, world = supervisor(tmp_path, world, restart_max=2)
    ticks(sup, world, 60)
    status = sup.statuses()
    assert status["xvfb"] == "failed" and status["desktop"] == "blocked" and status["director"] == "blocked"
    assert status["voice"] == "up" and status["agent"] == "blocked"        # voice needs no X server; agent needs the desktop
    assert "xvfb failed" in sup.svcs["desktop"].detail
    assert "desktop" not in world.spawned and "director" not in world.spawned
    assert "Xvfb not found" in sup.svcs["xvfb"].last_error


def test_the_desktop_follows_its_x_server_when_that_restarts_without_spending_budget(tmp_path):
    sup, world = supervisor(tmp_path)
    ticks(sup, world, 14)
    desktop_pid = world.procs["desktop"].pid
    world.crash("xvfb")
    ticks(sup, world, 20)
    assert (desktop_pid, signal.SIGTERM) in world.signals
    assert sup.statuses()["xvfb"] == "up" and sup.statuses()["desktop"] == "up"
    assert world.procs["desktop"].pid != desktop_pid
    assert sup.svcs["desktop"].budget.used(world.t) == 0 and sup.svcs["xvfb"].budget.used(world.t) == 1
    assert world.spawned.count("director") == 1                            # unrelated services are left alone


def test_an_x_server_that_is_already_there_is_used_and_never_stopped(tmp_path):
    world = World()
    world.external.add("xvfb")
    sup, world = supervisor(tmp_path, world)
    ticks(sup, world, 20)
    assert "xvfb" not in world.spawned and sup.svcs["xvfb"].external and sup.statuses()["xvfb"] == "up"
    assert sup.statuses()["desktop"] == "up"
    sup.stop_all()
    assert all(pid_sig[1] != signal.SIGKILL for pid_sig in world.signals)
    assert not any(name == "xvfb" for name in [p.name for p in world.procs.values()])
    assert sup.statuses()["xvfb"] == "stopped" and "left running" in sup.svcs["xvfb"].detail


def test_a_port_held_by_a_stranger_is_a_failure_not_an_adopted_service(tmp_path):
    sup, world = supervisor(tmp_path)
    sup._in_use = lambda port: port == 8832
    ticks(sup, world, 3)
    assert "desktop" not in world.spawned
    assert "port 8832 is already in use" in sup.svcs["desktop"].last_error and sup.statuses()["desktop"] == "backoff"


def test_children_of_an_earlier_supervisor_are_adopted_not_duplicated(tmp_path):
    sup, world = supervisor(tmp_path)
    adopted = up.AdoptedProc(4242, alive=lambda pid: True)
    sup._adopt = lambda spec: adopted if spec.name == "voice" else None
    ticks(sup, world, 30)
    assert "voice" not in world.spawned and sup.svcs["voice"].proc is adopted
    assert kinds(world, "service_adopted", "voice") and sup.statuses()["voice"] == "starting"
    world.t += 5
    sup.tick()
    assert adopted.poll() is None


def test_adopted_process_reports_exit_when_the_pid_is_gone():
    alive = [True]
    proc = up.AdoptedProc(77, alive=lambda pid: alive[0])
    assert proc.poll() is None
    alive[0] = False
    assert proc.poll() == -1 and proc.poll() == -1


# --------------------------------------------------------------- kill switch

def test_kill_writes_stop_cuts_speech_and_takes_only_the_agent_down(tmp_path):
    cfg = make_cfg(tmp_path)
    up.ensure_dirs(cfg)
    for name, pid in (("agent", 301), ("desktop", 302), ("director", 303), ("voice", 304)):
        cfg.pid_file(name).write_text(str(pid))
    posts, signals, alive_pids = [], [], {301, 302, 303, 304}

    def post(method, port, path, token, body=None, timeout=1.5):
        posts.append((method, port, path, token, body))
        return 200, "{}"

    def signal_fn(pid, sig):
        signals.append((pid, sig))
        if sig == signal.SIGTERM:
            alive_pids.discard(pid)
        return True

    original = up.pid_matches
    up.pid_matches = lambda pid, needle, proc_root="/proc": needle in ("streamer_agent",)
    try:
        result = up.do_kill(cfg, TOKEN, post=post, signal_fn=signal_fn, alive=lambda pid: pid in alive_pids,
                            wall=lambda: 1792768000.0, clock=lambda: 0.0, sleep=lambda s: None)
    finally:
        up.pid_matches = original
    assert json.loads(cfg.stop_file.read_text()) == {"t": "2026-10-23T15:06:40Z", "by": "streamer_up kill"}
    assert posts == [("POST", 8835, "/stop", TOKEN, {})]
    assert signals == [(301, signal.SIGTERM)] and result["agent"] == "exited"
    assert alive_pids == {302, 303, 304}                         # desktop runner, director and voice server stay up
    assert result["voice_stop"] == "http 200" and result["stop_file"] == str(cfg.stop_file)


def test_kill_survives_a_dead_voice_server_and_a_missing_token(tmp_path):
    cfg = make_cfg(tmp_path)
    up.ensure_dirs(cfg)

    def refuse(*args, **kwargs):
        raise ConnectionRefusedError("voice server is down")

    result = up.do_kill(cfg, TOKEN, post=refuse, alive=lambda pid: False)
    assert cfg.stop_file.exists() and result["voice_stop"] == "failed: ConnectionRefusedError" and result["agent"] == "not running"
    cfg.stop_file.unlink()
    result = up.do_kill(cfg, None, post=refuse, alive=lambda pid: False)
    assert cfg.stop_file.exists() and result["voice_stop"] == "skipped: no operator token"


def test_a_stop_file_keeps_the_agent_down_and_everything_else_up(tmp_path):
    sup, world = supervisor(tmp_path)
    ticks(sup, world, 30)
    assert sup.statuses()["agent"] == "up"
    agent_pid = world.procs["agent"].pid
    world.stop = True
    ticks(sup, world, 5)
    assert (agent_pid, signal.SIGTERM) in world.signals
    assert sup.statuses() == {"xvfb": "up", "desktop": "up", "voice": "up", "agent": "held", "director": "up"}
    assert sup.svcs["agent"].budget.used(world.t) == 0 and not kinds(world, "service_crashed", "agent")
    assert world.spawned.count("agent") == 1
    assert sup.snapshot()["stop"] is True
    ticks(sup, world, 30)
    assert world.spawned.count("agent") == 1                       # held, however long
    world.stop = False
    ticks(sup, world, 8)
    assert sup.statuses()["agent"] == "up" and world.spawned.count("agent") == 2


def test_the_agent_is_not_started_at_all_while_the_stop_file_exists(tmp_path):
    world = World()
    world.stop = True
    sup, world = supervisor(tmp_path, world)
    ticks(sup, world, 30)
    assert world.spawned == ["xvfb", "desktop", "voice", "director"]
    assert sup.statuses()["agent"] == "held" and sup.statuses()["director"] == "up"


def test_an_agent_that_ignores_sigterm_is_killed_after_the_grace(tmp_path):
    world = World()
    world.stubborn.add("agent")
    sup, world = supervisor(tmp_path, world, stop_grace=4.0)
    ticks(sup, world, 30)
    pid = world.procs["agent"].pid
    world.stop = True
    ticks(sup, world, 10)
    assert (pid, signal.SIGTERM) in world.signals and (pid, signal.SIGKILL) in world.signals
    assert sup.statuses()["agent"] == "held"


# ----------------------------------------------------------------- stop

def test_stop_terminates_in_reverse_order_and_escalates_to_sigkill_after_the_grace(tmp_path):
    world = World()
    world.stubborn.add("desktop")
    sup, world = supervisor(tmp_path, world)
    ticks(sup, world, 30)
    pids = {name: world.procs[name].pid for name in up.ORDER}
    start = world.t
    world.signals.clear()
    sup.stop_all()
    terms = [pid for pid, sig in world.signals if sig == signal.SIGTERM]
    assert terms == [pids[n] for n in reversed(up.ORDER)]
    kills = [(pid, sig) for pid, sig in world.signals if sig == signal.SIGKILL]
    assert kills == [(pids["desktop"], signal.SIGKILL)]
    assert 15.0 <= world.t - start < 20.0                          # one stubborn child cost the full 15 s
    assert set(sup.statuses().values()) == {"stopped"}
    assert not list(sup.cfg.pids_dir.glob("*.pid"))
    assert json.loads(sup.cfg.snapshot_file.read_text())["services"]["desktop"]["status"] == "stopped"


def test_terminate_group_escalates_only_when_needed():
    clock = [0.0]
    state = {"alive": True}
    signals = []

    def signal_fn(pid, sig):
        signals.append(sig)
        if sig == signal.SIGTERM and state["polite"]:
            state["alive"] = False

    def sleep(seconds):
        clock[0] += seconds

    common = dict(alive=lambda pid: state["alive"], signal_fn=signal_fn, clock=lambda: clock[0], sleep=sleep)
    state["polite"] = True
    assert up.terminate_group(5, 15.0, **common) == "exited" and signals == [signal.SIGTERM] and clock[0] < 1
    state.update(alive=True, polite=False)
    signals.clear()
    clock[0] = 0.0
    original = signal_fn

    def killer(pid, sig):
        original(pid, sig)
        if sig == signal.SIGKILL:
            state["alive"] = False
    common["signal_fn"] = killer
    assert up.terminate_group(5, 15.0, **common) == "killed" and signals == [signal.SIGTERM, signal.SIGKILL]
    assert 15.0 <= clock[0] < 16.0
    state["alive"] = False
    assert up.terminate_group(5, 15.0, **common) == "gone"


# -------------------------------------------------- processes, files, CLI

def test_spawn_gives_each_child_its_own_session_log_and_environment(tmp_path, monkeypatch):
    seen = {}

    class FakePopen:
        pid = 999

        def __init__(self, argv, **kwargs):
            seen["argv"], seen["kwargs"] = argv, kwargs

    monkeypatch.setattr(up.subprocess, "Popen", FakePopen)
    cfg = make_cfg(tmp_path, environ={"PATH": "/usr/bin"})
    spec = up.build_specs(cfg, TOKEN)["voice"]
    proc = up.spawn_process(spec, cfg.log_file("voice"))
    kw = seen["kwargs"]
    assert proc.pid == 999 and seen["argv"] == spec.argv
    assert kw["start_new_session"] is True and kw["stdin"] == subprocess.DEVNULL and kw["stderr"] == subprocess.STDOUT
    assert kw["env"]["SUB01_ADMIN_TOKEN"] == TOKEN and kw["env"]["HF_HOME"] == "/home/unreal/hf-cache"
    log = cfg.log_file("voice")
    assert log.read_text().startswith("\n=== ") and "voice_server.py" in log.read_text()
    assert TOKEN not in log.read_text() and oct(log.stat().st_mode & 0o777) == "0o600"


def test_pid_files_are_checked_against_the_command_line(tmp_path):
    proc = tmp_path / "proc"
    (proc / "12").mkdir(parents=True)
    (proc / "12" / "cmdline").write_bytes(b"/venv/bin/python\0/src/scripts/voice_server.py\0--port\0" b"8835\0")
    assert up.pid_matches(12, "voice_server.py", str(proc)) is True
    assert up.pid_matches(12, "streamer_agent.py", str(proc)) is False
    assert up.pid_matches(13, "voice_server.py", str(proc)) is False


def test_health_judgement_and_helpers():
    assert [up.health_ok(c) for c in (200, 204, 401, 404, 500, 503)] == [True, True, True, True, False, False]
    assert up.pid_alive(os.getpid()) is True and up.pid_alive(2 ** 22 + 12345) is False
    assert up.parse_kv(["voice=--a 1", "voice=--b"], "x", split_args=True) == {"voice": ["--a", "1", "--b"]}


def test_atomic_write_is_private_and_replaces_the_file(tmp_path):
    target = tmp_path / "deep" / "state.json"
    up.atomic_write(target, "one")
    up.atomic_write(target, "two")
    assert target.read_text() == "two" and oct(target.stat().st_mode & 0o777) == "0o600"
    assert not list(target.parent.glob("*.tmp"))


def test_start_refuses_to_run_as_root_and_dry_run_prints_the_plan(tmp_path, monkeypatch, capsys):
    (tmp_path / "token").write_text(TOKEN)
    base = ["--streamer-dir", str(tmp_path / "sd"), "--token-file", str(tmp_path / "token"), "--source", str(tmp_path / "src")]
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("must not launch anything"))
    assert up.main(["start", "--dry-run", *base]) == 0
    plan = capsys.readouterr().out
    assert "[xvfb]" in plan and "[director]" in plan and "streamer_director.py --streamer-dir" in plan and TOKEN not in plan
    assert not (tmp_path / "sd").exists()                         # a dry run touches nothing
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    assert up.main(["start", *base]) == 2
    assert "refusing to run as root" in capsys.readouterr().err
    assert not (tmp_path / "sd").exists()


def test_cli_kill_resume_and_restart_checks(tmp_path, monkeypatch, capsys):
    base = ["--streamer-dir", str(tmp_path / "sd"), "--token-file", str(tmp_path / "missing-token")]
    posted = []
    monkeypatch.setattr(up, "http_request", lambda *a, **k: posted.append(a) or (200, "{}"))
    assert up.main(["kill", *base]) == 0                          # the kill switch works without a readable token
    assert (tmp_path / "sd" / "STOP").exists() and posted == []
    assert "voice /stop: skipped" in capsys.readouterr().out
    assert up.main(["restart", "bogus", *base]) == 2
    assert up.main(["restart", "voice", *base]) == 1              # no supervisor running
    assert "no supervisor running" in capsys.readouterr().err
    assert up.main(["resume", *base]) == 0 and not (tmp_path / "sd" / "STOP").exists()
    assert "STOP file removed" in capsys.readouterr().out
    assert up.main(["resume", *base]) == 0 and "no STOP file" in capsys.readouterr().out


def test_restart_agent_is_refused_while_the_kill_switch_is_on(tmp_path, monkeypatch, capsys):
    base = ["--streamer-dir", str(tmp_path / "sd")]
    up.ensure_dirs(up.Config(streamer_dir=tmp_path / "sd"))
    (tmp_path / "sd" / "STOP").write_text("{}")
    monkeypatch.setattr(up, "supervisor_pid", lambda cfg: 123)
    assert up.main(["restart", "agent", *base]) == 1
    assert "run `resume` first" in capsys.readouterr().err
    assert not list((tmp_path / "sd" / "ctl").iterdir())


def test_status_reports_down_services_without_a_supervisor(tmp_path, monkeypatch, capsys):
    (tmp_path / "token").write_text(TOKEN)
    monkeypatch.setattr(up, "probe_service", lambda spec, token: (False, "not running"))
    base = ["--streamer-dir", str(tmp_path / "sd"), "--token-file", str(tmp_path / "token")]
    assert up.main(["status", *base]) == 1
    out = capsys.readouterr().out
    assert "supervisor: NOT RUNNING" in out and out.count(" down ") == 5
    assert up.main(["status", "--json", *base]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["supervisor"] is None and report["stop"] is False and list(report["services"]) == list(up.ORDER)
