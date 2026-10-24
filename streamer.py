"""Streamer mode for SUB-01's backend (live_server, only with env SUB01_STREAMER=1).

While the mode is active he stays at his desk (life activity `use_computer`, home node `desk`) and is reported AWAKE.
His body keeps running: hunger, bladder, boredom and the sleep engine are not touched and their clocks do not stop. What
changes is that the *switches* they would cause are held back, and each one is written once to the events list (kind
"deferred"). The phone, the walks, the bed, the TV, the errands outside and the day plan's steps are paused, not
deleted: nothing is reset, so `stop()` hands him back to life.py's normal choice with every counter where it was.

How, without editing life.py: while active, `Life.start`, `request_impulse`, `apply_vote`, `hungry_now` and `wish_now`
are shadowed on the one Life instance by the guards below (removed again by `stop()`), and `update()` (which the brain
tick calls instead of `Life.update`) keeps the end of the pinned activity out of reach and tells Life he is awake.

Chat is input, never a command over the rules. The ring buffer below stores a filtered message as plain text with a
kind (question / link / request / other); nothing here evaluates, parses for commands or forwards it. The agent that
reads the ring decides alone what to do (streamer_agent.py: a doable request is carried out, one at a time; the rest is
answered by voice). While the mode is active the room shows no canned reaction for a chat line (`room_reaction`: the
old "Not doing that one...", "Good question...", AT_DESK_LINE are dropped; the voice is the reply); the one line still
shown at once is STREAMING_LINE, the honest refusal of a request that would move him away from the desk
(`life.request_impulse` while shadowed).

Routes (add_routes): admin token (`admin_ok`) and a direct loopback connection, otherwise 403.
    GET  /api/home/streamer              the view
    POST /api/home/streamer              {"operation": "start" | "stop" | "kill"}; kill also writes STREAMER_DIR/STOP
    GET  /api/home/streamer/chat?since=N {"messages": [{seq, t, nick, text, kind, said}], "next": N}
    POST /api/home/streamer/said         {"seqs": [...], "text": "what he said"}: answered by voice, so the inbox skips them
Public: `GET /api/home` gets {"streamer": {"active": bool}} (home_payload_middleware), and while active its "stage" is
AWAKE. Nothing else of the mode is public.

State: <data-dir>/streamer_state.json (active, since, chat counter, events, the chat request set aside at start), so a
restart resumes an active session. The chat ring itself is memory only. The kill file is STREAMER_DIR/STOP, with
STREAMER_DIR from the environment, else <data-dir>/streamer. `start` removes a STOP file (the operator asks for it);
`kill` writes it first, then stops the mode.
"""
import ipaddress
import json
import os
import time
from collections import deque
from pathlib import Path

from aiohttp import web

import impulse as impulse_mod
from chat import clean_nick
from life import ACTIVITIES, FOOD_ACTS
from state_io import load_json, save_json

ENV = "SUB01_STREAMER"
PIN = "use_computer"                  # the pinned life activity: at the desk, on the PC (home_world.DESTINATIONS: "desk")
PC_ACTIVITIES = ("use_computer", "research", "chat")   # asked for in chat: already true at the desk, nothing moves
PAUSED = ("phone", "walk", "bed", "tv", "outside", "day_plan")
STREAMING_LINE = "Not now, I'm streaming at my desk."   # at most 60 characters, like life.py's honest lines
AT_DESK_LINE = "I'm at the computer already."
HOLD_S = 3600.0                       # simulated seconds the pinned activity is kept ahead of the clock on every tick
BLADDER_AT = 0.45                     # home bladder level where life.scores starts to want the bathroom
DEFER_CLEAR_S = 300.0                 # a deferral is "over" after this long unseen; seen again, it is logged again
CHAT_RING = 200
TEXT_MAX = 280                        # chat.MAX_LEN
EVENTS_KEPT = 100
EVENTS_SAVED = 50
SEQ_GAP = 1000                        # after a restart the chat counter jumps, so a reader's `since` never outruns it
SAVE_EVERY = 50                       # the state file is written every this many chat messages as well (and on every operation)
SAID_MAX = 100                        # seqs per /said call
BODY_MAX = 8192
NO_STORE = {"Cache-Control": "no-store"}
SHADOWED = ("start", "request_impulse", "apply_vote", "hungry_now", "wish_now")
_MISSING = object()


class StreamerError(Exception):
    """An operation that did not complete (the kill file could not be written or removed)."""


def enabled(environ=None):
    return (os.environ if environ is None else environ).get(ENV) == "1"


def attach(live, environ=None):
    """The StreamerMode of a Live, or None when SUB01_STREAMER is not 1 (nothing is shadowed, no route, no state file)."""
    env = os.environ if environ is None else environ
    if not enabled(env):
        return None
    return StreamerMode(live.life, live.data_dir, home=getattr(live, "home", None), inbox=getattr(live, "chat_inbox", None),
                        votes=getattr(live, "votes", None), sim_clock=live.clock.now, environ=env)


def kind_of(text, imp=None):
    """question | link | request | other, from impulse.parse (its categories). A link anywhere is a link; an activity word
    is a request; a question about him, or any '?', is a question."""
    imp = imp or impulse_mod.parse(text)
    if imp.kind == "open_url" or impulse_mod.URL_RE.search(text) or impulse_mod.BARE_DOMAIN_RE.search(text):
        return "link"
    if imp.kind == "activity":
        return "request"
    if imp.why == "a question, no action" or "?" in text:
        return "question"
    return "other"


def plain(text, limit=TEXT_MAX):
    """Chat text for the ring: one line of printable characters, at most `limit`. It is data from then on."""
    return " ".join("".join(c if c.isprintable() else " " for c in str(text or "")).split())[:limit]


def reason_of(act):
    """Which timer an activity switch that was held back belongs to."""
    if act == "sleep":
        return "sleep"
    if act == "get_delivery":
        return "delivery"
    if act in FOOD_ACTS:
        return "hunger"
    if act == "use_bathroom":
        return "bladder"
    return "routine"


class StreamerMode:
    def __init__(self, life, data_dir, *, home=None, inbox=None, votes=None, clock=time.time, sim_clock=None,
                 streamer_dir=None, environ=None):
        env = os.environ if environ is None else environ
        self.life, self.home, self.inbox, self.votes = life, home, inbox, votes
        self.clock = clock                                 # wall time: since, events
        self.sim_clock = sim_clock or clock                # the world's clock: life.start, the chat messages' t
        self.state_path = Path(data_dir) / "streamer_state.json"
        self.dir = Path(streamer_dir or env.get("STREAMER_DIR") or Path(data_dir) / "streamer")
        self.stop_path = self.dir / "STOP"
        self.active, self.since = False, None
        self.events = deque(maxlen=EVENTS_KEPT)
        self.deferred = {}                                 # reason -> sim time last seen (a held-back switch)
        self._seen = {}                                    # reason -> what, in the tick being run
        self.ring = deque(maxlen=CHAT_RING)
        self.seq, self.spoken = 0, 0
        self.stash = {}                                    # what start() set aside: {"impulse": [...]}
        self._prev = None                                  # {name: previous instance attribute | _MISSING} while shadowed
        self._orig = {}
        saved = load_json(self.state_path, {})
        if saved:
            self.seq = _int(saved.get("seq")) + SEQ_GAP
            self.spoken = _int(saved.get("spoken"))
            if isinstance(saved.get("events"), list):
                self.events.extend(e for e in saved["events"] if isinstance(e, dict))
            imp = saved["stash"].get("impulse") if isinstance(saved.get("stash"), dict) else None
            if _valid_impulse(imp):
                self.stash["impulse"] = list(imp)
            if saved.get("active") is True:                # a restart resumes the session; update() pins him again
                self.active = True
                self.since = saved["since"] if isinstance(saved.get("since"), (int, float)) else self.clock()
                self._install()
                self._log("resume", "the backend restarted; the session goes on")

    # --- the operations ----------------------------------------------------------------------------------------
    def start(self, t=None):
        t = self.sim_clock() if t is None else t
        if self.stop_path.exists():                        # the operator starts again after a kill
            try:
                self.stop_path.unlink()
            except OSError as e:
                raise StreamerError(f"the kill file {self.stop_path} is present and cannot be removed: {e.strerror or e}")
            self._log("start", "the kill file was removed")
        if not self.active:
            self.active, self.since = True, self.clock()
            self.deferred.clear()
            imp = self.life.impulse
            self.stash = {"impulse": list(imp)} if imp else {}      # a request made earlier waits, it is not lost
            self.life.impulse = None
            self._install()
            self._log("start", "streaming at the desk; the house routines are paused")
        self._pin(t)
        self._drop_votes()
        self.save()
        return self.view()

    def stop(self, t=None):
        t = self.sim_clock() if t is None else t
        if self.active:
            self._uninstall()
            self.active, self.since = False, None
            self.deferred.clear()
            self.life.end_activity(t)                      # the desk is done: the next tick chooses as usual
            imp = self.stash.pop("impulse", None)
            if _valid_impulse(imp) and not self.life.impulse:
                self.life.impulse = (imp[0], imp[1], float(imp[2]))   # life.update drops it if it went stale meanwhile
            self._log("stop", "back to normal life; nothing was reset")
        self.save()
        return self.view()

    def kill(self, t=None):
        """The kill switch: STOP first (the agent stops within a second), then the mode ends. A STOP that cannot be
        written is an error, but the mode ends anyway."""
        failed = None
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp = self.dir / "STOP.tmp"
            tmp.write_text(json.dumps({"t": self.clock(), "by": "live_server"}) + "\n", encoding="utf-8")
            os.replace(tmp, self.stop_path)
        except OSError as e:
            failed = e
        self._log("kill", "the kill file was written" if failed is None
                  else f"the kill file failed: {failed.strerror or failed}")
        self.stop(t)
        if failed is not None:
            raise StreamerError(f"the kill file {self.stop_path} could not be written: {failed.strerror or failed}")
        return self.view()

    # --- the brain tick ------------------------------------------------------------------------------------------
    def update(self, t, dt_real, dt_sim, stage, rel, hot=0.0, pressure=0.0):
        """Life.update with the pin: what the brain tick calls instead of it (live_server)."""
        life = self.life
        if not self.active:
            return life.update(t, dt_real, dt_sim, stage, rel, hot, pressure)
        if self._prev is None:
            self._install()
        self._seen = {}
        if stage != "AWAKE":
            self._note("sleep", f"the {stage} stage is due")
        bladder = float(getattr(life, "home_bladder", 0.0) or 0.0)
        if bladder > BLADDER_AT:
            self._note("bladder", f"bladder at {bladder:.2f}")
        if life.activity != PIN:
            self._pin(t)
        life.impulse = None
        if not life.path:
            life.until = max(life.until, t + HOLD_S)       # the activity's own timer cannot end the desk
        self._drop_votes()
        out = life.update(t, dt_real, dt_sim, "AWAKE", rel, hot, pressure)
        self._settle(t)
        return out

    def _pin(self, t):
        if self.life.activity != PIN:
            self._orig["start"](PIN, t, "streaming: sits down at the desk")
        self.life.until = max(self.life.until, t + HOLD_S)

    def _note(self, reason, what):
        self._seen.setdefault(reason, what)

    def _settle(self, t):
        """Write each held-back switch once; a reason unseen for DEFER_CLEAR_S counts as over (and is written again
        if it comes back)."""
        for reason, what in self._seen.items():
            if reason not in self.deferred or t - self.deferred[reason] > DEFER_CLEAR_S:
                self._log("deferred", what, reason=reason)
            self.deferred[reason] = t
        for reason in [r for r, last in self.deferred.items() if t - last > DEFER_CLEAR_S]:
            del self.deferred[reason]

    def _drop_votes(self):
        votes = self.votes
        if votes is not None and getattr(votes, "pending", None):
            self._log("refused", "the viewers' vote result is not applied while streaming", source="vote")
            votes.pending = None

    # --- shadowing Life ------------------------------------------------------------------------------------------
    def _install(self):
        if self._prev is not None:
            return
        life = self.life
        self._prev = {n: vars(life).get(n, _MISSING) for n in SHADOWED}
        self._orig = {n: getattr(life, n) for n in SHADOWED}
        life.start, life.request_impulse, life.apply_vote = self._start, self._request_impulse, self._apply_vote
        life.hungry_now, life.wish_now = self._hungry_now, self._wish_now

    def _uninstall(self):
        if self._prev is None:
            return
        for name, was in self._prev.items():
            if was is _MISSING:
                vars(self.life).pop(name, None)
            else:
                setattr(self.life, name, was)
        self._prev, self._orig = None, {}

    def _start(self, act, t, why):
        if act == PIN:
            return self._orig["start"](act, t, why)
        reason = reason_of(act)
        self._note(reason, f"would start {act}: held back" if reason == "routine" else f"{reason}: would start {act}")
        return None

    def _hungry_now(self, t, rel, hot=0.0, pressure=0.0):
        got = self._orig["hungry_now"](t, rel, hot, pressure)
        if got:
            self._note("hunger", f"hunger: would start {got}")
        return False

    def _wish_now(self, t, rel, hot=0.0, pressure=0.0):
        got = self._orig["wish_now"](t, rel, hot, pressure)
        if got:
            self._note("wish", f"a wish from the chat or a vote: would start {got}")
        return False

    def _request_impulse(self, imp, t):
        """The reaction path's honest line. No request is kept (life.impulse stays empty); a request to sleep or a
        non-activity (life.py answers None for those, no side effect) goes to life.py as before."""
        act = getattr(imp, "activity", None)
        if getattr(imp, "kind", None) != "activity" or act not in ACTIVITIES or act == "sleep":
            return self._orig["request_impulse"](imp, t)
        if act in PC_ACTIVITIES:
            return AT_DESK_LINE
        self._log("refused", f"asked in chat: {act}", source="chat", activity=act)
        return STREAMING_LINE

    def _apply_vote(self, act, t):
        if act in ACTIVITIES and act != "sleep" and act not in PC_ACTIVITIES:
            self._log("refused", f"voted: {act}", source="vote", activity=act)
        return False

    def room_reaction(self, imp, reaction):
        """The line the room shows for an accepted chat message (live_server.handle_chat). Off the mode: `reaction`
        as it is. While streaming: only STREAMING_LINE (a request that would move him: refused at once, honestly); the
        canned reactions of impulse.py ("Not doing that one...", "Good question...", the activity lines), AT_DESK_LINE
        and the link lines are dropped, because the streamer agent answers by voice and carries out what can be done at
        the desk (owner, 2026-10-23). The ack keeps its "reaction" key, as "" (API shape unchanged)."""
        if not self.active or reaction == STREAMING_LINE:
            return reaction
        return ""

    # --- chat: the ring --------------------------------------------------------------------------------------------
    def record_chat(self, text, key="", nick="", t=None, imp=None):
        """An accepted chat message (live_server.handle_chat, after chat.check) goes into the ring. -> its record."""
        raw = str(text or "").strip()
        clean = plain(raw)
        if not clean:
            return None
        t = float(self.sim_clock() if t is None else t)
        self.seq += 1
        rec = {"seq": self.seq, "t": round(t, 3), "nick": clean_nick(nick)[0], "text": clean, "kind": kind_of(clean, imp),
               "said": False,
               "_vkey": self.inbox.viewer_of(key) if self.inbox is not None else None, "_raw": raw, "_t": t}
        self.ring.append(rec)
        if self.seq % SAVE_EVERY == 0:
            self.save()
        return _public(rec)

    def messages(self, since=0, limit=CHAT_RING):
        """-> {"messages": [...], "next": last seq}: the ring's messages after `since`, oldest first."""
        out = [_public(r) for r in self.ring if r["seq"] > since]
        return {"messages": out[-max(1, min(CHAT_RING, limit)):], "next": self.seq}

    def mark_said(self, seqs, text=""):
        """He answered these by voice: they are marked, and leave the inbox so mind.py does not answer them again.
        -> (marked, dropped from the inbox, unknown seqs)."""
        wanted = set(seqs)
        marked = dropped = 0
        for rec in self.ring:
            if rec["seq"] not in wanted:
                continue
            wanted.discard(rec["seq"])
            if not rec["said"]:
                rec["said"] = True
                marked += 1
                self.spoken += 1
            if self.inbox is not None:
                for item in list(self.inbox):
                    if item["vkey"] == rec["_vkey"] and item["text"] == rec["_raw"] and item["t"] == float(rec["_t"]):
                        self.inbox.answered(item)
                        dropped += 1
        self._log("said", plain(text, 160) or "(voice)", seqs=sorted(set(seqs) - wanted)[:SAID_MAX])
        return marked, dropped, len(wanted)

    # --- views and state -------------------------------------------------------------------------------------------
    def view(self):
        pending = sum(1 for r in self.ring if not r["said"])
        return {"active": self.active, "since": self.since, "activity": self.life.activity,
                "node": getattr(self.home, "node", None), "stage": "AWAKE" if self.active else getattr(self.life, "stage", None),
                "paused": list(PAUSED) if self.active else [], "deferred": sorted(self.deferred),
                "chat": {"pending": pending, "spoken": self.spoken}, "kill": self.stop_path.exists(),
                "events": list(self.events)[-20:]}

    def public(self):
        return {"active": self.active}

    def to_dict(self):
        return {"version": 1, "active": self.active, "since": self.since, "seq": self.seq, "spoken": self.spoken,
                "stash": self.stash, "events": list(self.events)[-EVENTS_SAVED:]}

    def save(self):
        save_json(self.state_path, self.to_dict())

    def _log(self, kind, what, **extra):
        self.events.append({"t": round(self.clock(), 3), "kind": kind, "what": what, **extra})


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else 0


def _valid_impulse(imp):
    return (isinstance(imp, (list, tuple)) and len(imp) == 3 and isinstance(imp[0], str) and imp[0] in ACTIVITIES
            and imp[0] != "sleep" and isinstance(imp[1], str) and isinstance(imp[2], (int, float))
            and not isinstance(imp[2], bool))


def _public(rec):
    return {k: v for k, v in rec.items() if not k.startswith("_")}


# --- http ------------------------------------------------------------------------------------------------------------
def is_local(request):
    """A direct loopback connection: not through a proxy (any forwarding header says it was one)."""
    if any(h in request.headers for h in ("X-Forwarded-For", "X-Real-IP", "Forwarded")):
        return False
    try:
        ip = ipaddress.ip_address(request.remote or "")
    except ValueError:
        return False
    return (getattr(ip, "ipv4_mapped", None) or ip).is_loopback


async def read_body(request):
    if request.content_length is not None and request.content_length > BODY_MAX:
        raise web.HTTPRequestEntityTooLarge(max_size=BODY_MAX, actual_size=request.content_length)
    chunks, size = [], 0
    async for chunk in request.content.iter_chunked(4096):
        size += len(chunk)
        if size > BODY_MAX:
            raise web.HTTPRequestEntityTooLarge(max_size=BODY_MAX, actual_size=size)
        chunks.append(chunk)
    try:
        body = json.loads(b"".join(chunks))
    except (ValueError, UnicodeDecodeError):
        raise web.HTTPBadRequest(text="Invalid JSON")
    if not isinstance(body, dict):
        raise web.HTTPBadRequest(text="Expected object")
    return body


def add_routes(app, mode, admin_ok):
    """Register the streamer routes. mode None (SUB01_STREAMER off): nothing is registered."""
    if mode is None:
        return

    def guard(request):
        if not admin_ok(request) or not is_local(request):
            raise web.HTTPForbidden(text="Operator authentication from the loopback is required")

    async def get_view(request):
        guard(request)
        return web.json_response(mode.view(), headers=NO_STORE)

    async def post_operation(request):
        guard(request)
        op = (await read_body(request)).get("operation")
        if op not in ("start", "stop", "kill"):
            raise web.HTTPBadRequest(text='operation must be "start", "stop" or "kill"')
        try:
            getattr(mode, op)()
        except StreamerError as e:
            return web.json_response({"ok": False, "operation": op, "error": str(e), **mode.view()}, status=500,
                                     headers=NO_STORE)
        return web.json_response({"ok": True, "operation": op, **mode.view()}, headers=NO_STORE)

    async def get_chat(request):
        guard(request)
        try:
            since = int(request.query.get("since", "0"))
            limit = int(request.query.get("limit", str(CHAT_RING)))
        except ValueError:
            raise web.HTTPBadRequest(text="since and limit are integers")
        if since < 0:
            raise web.HTTPBadRequest(text="since is not negative")
        return web.json_response(mode.messages(since, limit), headers=NO_STORE)

    async def post_said(request):
        guard(request)
        body = await read_body(request)
        seqs, text = body.get("seqs"), body.get("text", "")
        if (not isinstance(seqs, list) or len(seqs) > SAID_MAX or not isinstance(text, str)
                or any(not isinstance(s, int) or isinstance(s, bool) for s in seqs)):
            raise web.HTTPBadRequest(text='Expected {"seqs": [integers], "text": string}')
        marked, dropped, unknown = mode.mark_said(seqs, text)
        return web.json_response({"ok": True, "marked": marked, "dropped": dropped, "unknown": unknown}, headers=NO_STORE)

    app.router.add_get("/api/home/streamer", get_view)
    app.router.add_post("/api/home/streamer", post_operation)
    app.router.add_get("/api/home/streamer/chat", get_chat)
    app.router.add_post("/api/home/streamer/said", post_said)


def home_payload_middleware(mode):
    """GET /api/home also says {"streamer": {"active": bool}}, and reports the stage AWAKE while the mode is active.
    (home_api.py builds that payload and is not touched: this adds to its JSON on the way out.)"""
    @web.middleware
    async def middleware(request, handler):
        resp = await handler(request)
        if (request.method == "GET" and request.path == "/api/home" and isinstance(resp, web.Response)
                and resp.status == 200 and not resp.prepared and resp.content_type == "application/json"):
            try:
                data = json.loads(resp.body)
            except (TypeError, ValueError):
                return resp
            if isinstance(data, dict):
                data["streamer"] = mode.public()
                if mode.active and data.get("stage") is not None:
                    data["stage"] = "AWAKE"
                resp.body = json.dumps(data).encode("utf-8")
        return resp
    return middleware
