"""Viewer-facing live features (owner 10-28): self-chosen names, the video queue sent from the site, the free Hype button
and chat sound effects. Pure, clock-injected classes; the agent (streamer_agent.py) wires them to chat, its HTTP API,
the request runner and the audio sink. Designs reviewed by Kimi (docs/streamer/kimi/review-20261028-0210.md, feat1 and
feat2): names are unverified and only ever data; no queue, hype or sfx body is logged; suppressed events are dropped,
never queued for later."""
from __future__ import annotations

import asyncio
import collections
import json
import os
import re
import signal
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

# ---------------------------------------------------------------- names

NICK_RE = re.compile(r"[A-Za-z0-9_.-]{2,16}")
RESERVED_NICKS = frozenset("sub01 sub-01 sub_01 subzerone owner admin administrator mod moderator streamer system viewer "
                           "anon anonymous staff support official bot".split())


def clean_nick(raw):
    """The display name a viewer chose, or "" (anonymous): 2-16 ASCII letters, digits, _ . - only; reserved names and
    anything else become "". Names are unverified: never a permission, only a greeting."""
    nick = str(raw or "").strip()
    if not NICK_RE.fullmatch(nick) or nick.lower().strip("._-") in RESERVED_NICKS or nick.lower() in RESERVED_NICKS:
        return ""
    return nick


def nick_key(nick):
    return str(nick or "").strip().lower()


# ---------------------------------------------------------------- YouTube links

YT_ID = re.compile(r"[A-Za-z0-9_-]{11}")
YT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}


def youtube_id(raw):
    """The 11-character video id of a YouTube link (watch, shorts, live, embed, youtu.be), or None. Parsed with a URL
    parser: https only (a missing scheme is https), exact hosts, no user info, no port, exact path shapes."""
    text = str(raw or "").strip()
    if not text or len(text) > 300 or any(c.isspace() for c in text):
        return None
    if "://" not in text:
        text = "https://" + text
    try:
        u = urlsplit(text)
        port = u.port
    except ValueError:
        return None
    if u.scheme.lower() != "https" or u.username or u.password or port is not None:
        return None
    host, parts = (u.hostname or "").lower(), [p for p in u.path.split("/") if p]
    vid = None
    if host == "youtu.be" and len(parts) == 1:
        vid = parts[0]
    elif host in YT_HOSTS:
        if parts == ["watch"]:
            vid = (parse_qs(u.query).get("v") or [None])[0]
        elif len(parts) == 2 and parts[0] in ("shorts", "live", "embed"):
            vid = parts[1]
    return vid if vid and YT_ID.fullmatch(vid) else None


def youtube_url(vid):
    return f"https://www.youtube.com/watch?v={vid}"


# ---------------------------------------------------------------- video queue

class VideoQueue:
    """Videos viewers send from the site. States: waiting -> now_playing -> done | skipped. At most MAX_WAITING waiting,
    PER_NICK per name, no id twice (waiting, playing, or played in the last RECENT_S); a waiting entry expires after
    EXPIRE_S. The next one is the oldest entry of the name served least recently (round robin, so one person cannot
    hold the queue). Saved atomically after every change; a malformed file is ignored at startup."""
    MAX_WAITING, PER_NICK, EXPIRE_S, RECENT_S = 20, 2, 5400.0, 1800.0

    def __init__(self, path, wall):
        self.path, self.wall = Path(path), wall
        self.waiting, self.now_playing, self.recent, self.served = [], None, collections.OrderedDict(), {}
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            data = {}
        for e in data.get("waiting", []) if isinstance(data, dict) else []:
            if isinstance(e, dict) and YT_ID.fullmatch(str(e.get("id", ""))) and isinstance(e.get("t"), (int, float)):
                self.waiting.append({"id": e["id"], "nick": clean_nick(e.get("nick")), "t": float(e["t"])})
        # an entry playing when the agent stopped is not replayed (Kimi: no double play after a restart)

    def save(self):
        tmp = self.path.with_name(self.path.name + f".tmp-{os.getpid()}")
        try:
            tmp.write_text(json.dumps({"schema": "sub01.video-queue.v1", "waiting": self.waiting}))
            os.replace(tmp, self.path)
        except OSError:
            pass

    def expire(self):
        now = self.wall()
        before = len(self.waiting)
        self.waiting = [e for e in self.waiting if now - e["t"] < self.EXPIRE_S]
        for vid in [v for v, t in self.recent.items() if now - t > self.RECENT_S]:
            del self.recent[vid]
        if len(self.waiting) != before:
            self.save()

    def add(self, nick, url):
        """-> (ok, reason, position). reason: added | bad_link | duplicate | full | per_name."""
        self.expire()
        vid = youtube_id(url)
        if vid is None:
            return False, "bad_link", None
        if vid in self.recent or any(e["id"] == vid for e in self.waiting) or \
                (self.now_playing and self.now_playing["id"] == vid):
            return False, "duplicate", None
        if len(self.waiting) >= self.MAX_WAITING:
            return False, "full", None
        nick = clean_nick(nick)
        if nick and sum(1 for e in self.waiting if nick_key(e["nick"]) == nick_key(nick)) >= self.PER_NICK:
            return False, "per_name", None
        self.waiting.append({"id": vid, "nick": nick, "t": self.wall()})
        self.save()
        return True, "added", len(self.waiting)

    def take(self):
        """The next entry (now playing), or None."""
        self.expire()
        if not self.waiting or self.now_playing is not None:
            return None
        e = min(self.waiting, key=lambda x: (self.served.get(nick_key(x["nick"]) or "?", 0.0), x["t"]))
        self.waiting.remove(e)
        self.now_playing = dict(e, started=self.wall())
        self.served[nick_key(e["nick"]) or "?"] = self.wall()
        while len(self.served) > 500:
            self.served.pop(next(iter(self.served)))
        self.save()
        return self.now_playing

    def finish(self, state="done"):
        e, self.now_playing = self.now_playing, None
        if e:
            self.recent[e["id"]] = self.wall()
            e["state"] = state
        return e

    def public(self):
        """The site's view: names and ids only (no times, no counts per name)."""
        self.expire()
        now = self.now_playing
        return {"now": {"nick": now["nick"], "id": now["id"]} if now else None,
                "waiting": [{"nick": e["nick"], "id": e["id"]} for e in self.waiting]}


# ---------------------------------------------------------------- hype

class HypeMeter:
    """The free Hype button: presses in a sliding WINDOW_S, one per name per DEDUPE_S. level = distinct names / TRAIN_AT
    (at most 1). press() -> "train" when the level reaches 1 and no train ran in TRAIN_COOLDOWN_S, "shout" when a spoken
    shout-out is due (at most one per SHOUT_GAP_S), else None. A blocked moment is never deferred: the caller drops it."""
    WINDOW_S, DEDUPE_S, TRAIN_AT, TRAIN_COOLDOWN_S, SHOUT_GAP_S, TRAIN_SHOW_S = 60.0, 30.0, 5, 600.0, 50.0, 20.0

    def __init__(self, clock):
        self.clock = clock
        self.presses = collections.deque()                    # (t, key) of counted presses
        self.last_by_key = collections.OrderedDict()
        self.last_train, self.last_shout, self.train_until = -1e9, -1e9, -1e9

    def _prune(self, now):
        while self.presses and now - self.presses[0][0] > self.WINDOW_S:
            self.presses.popleft()
        for k in [k for k, t in self.last_by_key.items() if now - t > self.DEDUPE_S]:
            del self.last_by_key[k]

    def level(self):
        now = self.clock()
        self._prune(now)
        return min(1.0, len({k for _, k in self.presses}) / self.TRAIN_AT)

    def press(self, nick):
        now = self.clock()
        self._prune(now)
        key = nick_key(nick) or f"anon-{len(self.presses)}"
        if nick and key in self.last_by_key:
            return None
        self.last_by_key[key] = now
        while len(self.last_by_key) > 1000:
            self.last_by_key.popitem(last=False)
        self.presses.append((now, key))
        if self.level() >= 1.0 and now - self.last_train >= self.TRAIN_COOLDOWN_S:
            self.last_train = self.last_shout = now           # a train line replaces the shout-out
            return "train"
        if now - self.last_shout >= self.SHOUT_GAP_S:
            self.last_shout = now
            return "shout"
        return None

    def show_train(self):
        self.train_until = self.clock() + self.TRAIN_SHOW_S

    def end_train(self):
        self.train_until = -1e9

    def public(self):
        return {"level": round(self.level(), 2), "train": self.clock() < self.train_until}


HYPE_SHOUT_LINES = ("{nick} with the hype! Let's go!", "Hype from {nick}! I see you!", "{nick} pressing the hype button, "
                    "respect.", "Yo {nick}, the hype is felt!")
HYPE_SHOUT_ANON = ("Somebody hit the hype! Let's go!", "Hype button going off, I see you chat!", "The hype is real, chat!")
HYPE_TRAIN_LINES = ("HYPE TRAIN! Chat is going crazy, let's go!", "We got a hype train, chat! This is insane!",
                    "Hype train pulling up! Chat, you are different!")


# ---------------------------------------------------------------- sound effects

SFX = {"airhorn": 2.2, "drumroll": 3.0, "rimshot": 1.6, "sad": 2.8, "boom": 2.0, "applause": 3.0, "crickets": 3.0,
       "win": 2.6}                                            # name -> seconds (the files are made by tools/pod/onpod/make_sfx.sh)
SFX_COMMAND = re.compile(r"!(" + "|".join(SFX) + r")")


def sfx_command(text):
    """The effect a whole chat line asks for ("!rimshot", any case, spaces around), or None."""
    m = SFX_COMMAND.fullmatch(str(text or "").strip().lower())
    return m.group(1) if m else None


class SfxPlayer:
    """Plays one effect at a time into the stream's desktop audio sink with paplay (argv, no shell, its own process
    group, output to DEVNULL, killed after its length + 2 s, on privacy or on stop). Cooldowns: GLOBAL_S between
    effects, PER_NICK_S per name, PER_EFFECT_S per effect (AIRHORN_S for the airhorn); a busy or cooling command is
    dropped, never queued."""
    GLOBAL_S, PER_NICK_S, PER_EFFECT_S, AIRHORN_S = 12.0, 45.0, 60.0, 90.0

    def __init__(self, sfx_dir, pulse_server, clock, spawn=None):
        self.dir, self.server, self.clock = Path(sfx_dir), str(pulse_server), clock
        self.spawn = spawn or asyncio.create_subprocess_exec
        self.proc, self.last, self.by_nick, self.by_effect = None, -1e9, {}, {}
        self.played = None                                    # (t, name, nick) of the last effect that really started

    def ready(self, name, nick="", force=False):
        """-> None when it may play now, else why not (busy | cooldown | missing)."""
        now = self.clock()
        if name not in SFX or not (self.dir / f"{name}.wav").is_file():
            return "missing"
        if self.proc is not None and self.proc.returncode is None:
            return "busy"
        if force:
            return None
        gap = self.AIRHORN_S if name == "airhorn" else self.PER_EFFECT_S
        if now - self.last < self.GLOBAL_S or now - self.by_effect.get(name, -1e9) < gap or \
                (nick and now - self.by_nick.get(nick_key(nick), -1e9) < self.PER_NICK_S):
            return "cooldown"
        return None

    async def play(self, name, nick="", force=False):
        """-> True when the effect started (and was not cut). force: the hype train's airhorn (only the busy test)."""
        why = self.ready(name, nick, force)
        if why:
            return False
        now = self.clock()
        self.last, self.by_effect[name] = now, now
        if nick:
            self.by_nick[nick_key(nick)] = now
            while len(self.by_nick) > 1000:
                self.by_nick.pop(next(iter(self.by_nick)))
        env = {"PULSE_SERVER": f"unix:{self.server}", "PATH": "/usr/bin:/bin", "HOME": os.environ.get("HOME", "/tmp")}
        try:
            self.proc = await self.spawn("paplay", "--device=sub01_apps", str(self.dir / f"{name}.wav"),
                                         stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
                                         stderr=asyncio.subprocess.DEVNULL, env=env, start_new_session=True)
        except (OSError, ValueError):
            self.proc = None
            return False
        self.played = (now, name, nick)
        asyncio.get_running_loop().create_task(self._reap(self.proc, SFX[name] + 2.0))
        return True

    async def _reap(self, proc, limit):
        try:
            await asyncio.wait_for(proc.wait(), limit)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self.kill(proc)
        finally:
            if self.proc is proc:
                self.proc = None

    def kill(self, proc=None):
        proc = proc or self.proc
        if proc is None or proc.returncode is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            try:
                proc.kill()
            except (OSError, ProcessLookupError):
                pass

    def cancel(self):
        """A privacy cut or a quiet minute: the effect playing now stops, and is not reported to the model."""
        if self.proc is not None and self.proc.returncode is None:
            self.kill()
            self.played = None

    def note(self, within=10.0):
        """The model's state note for an effect that started in the last `within` s, or None."""
        p = self.played
        if p and self.clock() - p[0] <= within:
            return f"{p[1]}" + (f" (by {p[2]})" if p[2] else "")
        return None
