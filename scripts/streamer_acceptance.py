#!/usr/bin/env python3
"""SUB-01 acceptance check (plan step 7): read the real logs and recordings of a time window and say, criterion by
criterion, whether the 30-minute acceptance recording shows what the owner asked for. Read-only: it opens the sources,
runs `ffprobe -count_packets` (demux, no decode) on the recording and HLS segments of the window, and writes two files.

    python3 scripts/streamer_acceptance.py --streamer-dir /home/unreal/.sub01-private/streamer \\
        --game-log /tmp/sub01-share/game.log [--minutes 30 | --since T --until T | --last-rehearsal] --out-dir DIR

T is unix seconds or ISO UTC. Default window: the last 30 minutes. Output: DIR/<name>.md (the report) and
DIR/<name>.json (schema sub01.streamer-acceptance.v1: per criterion status, why, metrics, thresholds, evidence lines
with timestamps, highlight timestamps with the recording segment and the offset into it).

Statuses (decided with Kimi, docs/streamer/kimi/acceptance-criteria.md):
  pass     the evidence meets the criterion;
  fail     the sources cover the window and the required content is absent or below the bar (no chat request, no
           fault, an fps window under 59.5, ...);
  missing  "missing evidence": the window cannot be assessed (a log absent or not covering the window, a logging gap,
           no source that measures it, a recovery still pending at the window end).
Verdict: pass only when every criterion passes; any fail gives fail; otherwise inconclusive. Exit 0 on pass, else 1.

Criteria (thresholds in TH):
  activity_change   browse <-> game with >= 60 s of elapsed activity on each side (quiet/held/privacy excluded),
                    carried in from before the window; video and site changes are reported as weak, not counted
  chat_executed     a desktop request: chat_request{executed}, an action bound to it (req-<seq>) or its game routine
                    verified, chat_request_end why=done, an answer spoken, on air
  chat_refused      a policy refusal (operational ones apart) spoken within 60 s, never executed, on air
  error_recovered   fault incidents and their fault-specific recoveries within a deadline; any unrecovered one fails,
                    a pending one leaves it inconclusive
  two_cameras       `room` (cam2 full frame + webcam PiP) on air >= 60 s in all, one stretch >= 30 s, cam2 delivering
  voice_k07         utterances by chatterbox with the k07 prompt (voice.log replayed from a known start), no fallback
  voice_recorded    every utterance while the director recorded with voice
  head_motion       POSE head pitch/yaw varying during speech (>= 1 degree) and a talking state during an utterance
  mouth_motion      the game's mouth rig moving with the voice: a head_only rig (no jaw, no morphs) does not meet it
  pc_control        keyboard and mouse inputs changed the connected Vagon desktop, on air
  fps_game, fps_cam2, fps_monitor_feed   every complete measured window >= 59.5 fps, no logging gap
  fps_director, fps_recordings, fps_hls_spot   output pace >= 59.9 fps (director dup/drop 0); HLS keeps ~24 s, so
                    its check is a spot check at the window end
A 60 fps output pace does not prove 60 distinct source frames (the graph repeats what a source did not deliver):
that is what the source criteria are for.

Sources: <streamer-dir>/events.jsonl and events.1.jsonl (agent, director, supervisor rows), speech/timeline.jsonl,
logs/voice.log, rehearsal.jsonl, watchdog.jsonl, recordings/*.mp4, hls/live.m3u8 + .ts, the desktop runners'
events.jsonl (desktop-vagon/, desktop/), the game log (SUB01_* lines, UTC). Evidence lines are masked (token-like
strings, keys, query strings). Reuses scripts/streamer_highlights.py (speech and induced-fault windows, the reel
command) and the induced-fault names of scripts/streamer_rehearsal.py.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import streamer_highlights  # noqa: E402  (stdlib only)

try:                                    # needs aiohttp; only its schedule of induced faults is used here
    import streamer_rehearsal           # noqa: E402
    INDUCED = tuple(sorted(set(streamer_rehearsal.EVENTS.values())))
except Exception:                       # pragma: no cover - plain python3 without aiohttp
    INDUCED = ("kill_browser", "provider_error")

SCHEMA = "sub01.streamer-acceptance.v1"
DEFAULT_DIR = "/home/unreal/.sub01-private/streamer"
DEFAULT_GAME_LOG = "/tmp/sub01-share/game.log"
PASS, FAIL, MISSING, INCONCLUSIVE = "pass", "fail", "missing", "inconclusive"
STATUS_TEXT = {PASS: "PASS", FAIL: "FAIL", MISSING: "MISSING EVIDENCE", INCONCLUSIVE: "INCONCLUSIVE"}
SEGMENT_S = 600.0

TH = {                                  # one table, so a review changes numbers in one place
    "dwell_s": 60.0,                    # activity: elapsed activity on each side of a change
    "carry_s": 300.0,                   # activity: a label is carried in from agent activity this close to the start
    "chat_voice_s": 60.0,               # a request's answer / a refusal spoken within this long
    "room_s": 60.0,                     # two cameras: seconds of `room` with cam2, in all ...
    "room_continuous_s": 30.0,          # ... and in one stretch
    "utterances": 3, "speech_s": 20.0,  # voice: at least this many K07 utterances / seconds of speech
    "talk_slack_s": 2.0,                # a STATE -> talking line this close to an utterance counts for it
    "head_range_deg": 1.0,              # head motion: POSE head pitch or yaw range during speech
    "source_min_fps": 59.5,             # every complete PERF / CAM2 / monitor window
    "gap_factor": 1.5,                  # a logging gap: lines further apart than 1.5 periods
    "output_fps": 59.9,                 # director rows, recording and HLS packets per second
    "partial_min_s": 60.0,              # a partial director row is judged when it spans this long
    "recording_gap_s": 2.0,             # recordings: a gap between segments longer than this fails
    "incident_merge_s": 60.0,           # faults of one kind this close together are one incident
    "log_fresh_s": 900.0,               # events.jsonl must have rows within this of both window ends
    "deadline": {"director": 120.0, "cam2": 300.0, "supervisor": 300.0, "agent": 300.0, "runner": 60.0,
                 "vagon": 300.0, "watchdog": 900.0},
}
OPERATIONAL_REFUSALS = ("pc_offline", "hands_off", "no_model", "games_off")
NON_DESKTOP_REQUESTS = ("face", "hush")
VIDEO_HOSTS = ("youtube.com", "youtu.be", "twitch.tv", "vimeo.com", "dailymotion.com")
OK_VERDICTS = ("changed", "moved", "done")
ROUTINE_OK = ("started", "steam_open", "stopped")      # streamer_agent.end_routine: a game routine that succeeded
KEYBOARD, MOUSE = ("key", "type", "navigate", "search"), ("click", "scroll")   # on Vagon navigate/search are typed
VAGON_DOWN = ("disconnected", "ended", "login_required", "blank", "dashboard", "starting", "connecting", "blocked",
              "open", "adopted", "start_held")
EVIDENCE_MAX = 30

# ------------------------------------------------------------------ helpers

SENSITIVE = r"(?:token|secret|password|passwd|api[_-]?key|apikey|authorization|cookie|credential)"
SENSITIVE_KEY = re.compile(rf"(?i)[A-Za-z0-9_\-]*{SENSITIVE}[A-Za-z0-9_\-]*")
_MASKS = (
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"), "sk-[MASKED]"),
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=\-]+"), r"\1 [MASKED]"),
    # key=value / "key": "value" for any key name holding a sensitive word (refresh_token, client_secret, X-Admin-Token)
    (re.compile(rf"(?i)([A-Za-z0-9_\-]*{SENSITIVE}[A-Za-z0-9_\-]*)([\"']?\s*[:=]\s*[\"']?)"
                r"(?!\[MASKED\]|(?:true|false|null)\b)[^\s\"'&,}]+"), r"\1\2[MASKED]"),
    (re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://)[^/\s\"'@]+@"), r"\1[MASKED]@"),          # URL userinfo
    (re.compile(r"(https?://[^\s\"'?#]+)\?[^\s\"']*"), r"\1?[query masked]"),
    # long token-like runs; the game's SUB01_* log tags (SUB01_STREAMER_VISUAL_MOUTH_READY) are names, not secrets
    (re.compile(r"[A-Za-z0-9_]{32,}"), lambda m: m.group(0) if re.fullmatch(r"SUB01_[A-Z0-9_]+", m.group(0))
     else "[MASKED]"),
)


def mask(text, limit=400):
    """A line as it may appear in a report: token-like strings, keys, credentials in URLs and query strings masked,
    cut at `limit`."""
    text = str(text).replace("\r", " ").replace("\n", " ")
    for pattern, repl in _MASKS:
        text = pattern.sub(repl, text)
    return text if len(text) <= limit else text[:limit - 1] + "…"


def scrub(obj):
    """A row with the value of every sensitive key (at any depth) replaced, before it is dumped and masked."""
    if isinstance(obj, dict):
        return {k: "[MASKED]" if isinstance(k, str) and SENSITIVE_KEY.fullmatch(k) and not isinstance(v, (bool, type(None)))
                else scrub(v) for k, v in obj.items() if not (isinstance(k, str) and k.startswith("_"))}
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    return obj


def to_unix(value):
    """Unix seconds from a number, a numeric string or an ISO time (Z, +00:00, +0000, naive = UTC); else None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    s = str(value).strip()
    try:
        number = float(s)
        return number if math.isfinite(number) else None
    except ValueError:
        pass
    s = re.sub(r"([+-]\d\d)(\d\d)$", r"\1:\2", s.replace("Z", "+00:00"))
    s = re.sub(r"\.(\d{3})\d*(?=[+-]|$)", r".\1", s)
    try:
        moment = datetime.fromisoformat(s)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if t is not None else None


def hms(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%H:%M:%S") if t is not None else "-"


def mmss(seconds):
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def percentile(values, q):
    """Nearest-rank percentile (q in 0..100) of a non-empty list."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q / 100.0 * len(ordered)) - 1)]


def median(values):
    ordered, n = sorted(values), len(values)
    return ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2.0


def host_of(url):
    try:
        host = (urlsplit(str(url)).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def is_video(host):
    return any(host == h or host.endswith("." + h) for h in VIDEO_HOSTS)


def clip(t0, t1, since, until):
    """Seconds of [t0, t1] inside [since, until]."""
    return max(0.0, min(t1, until) - max(t0, since))


def overlap(t0, t1, intervals):
    return sum(max(0.0, min(t1, b) - max(t0, a)) for a, b in intervals)


def union(intervals):
    out = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def ev(t, source, line):
    """One evidence item: time, source and the masked line (a dict row is dumped without the private keys)."""
    if isinstance(line, dict):
        line = json.dumps(scrub(line), ensure_ascii=False, default=str)
    return {"t": None if t is None else round(t, 3), "utc": iso(t), "source": source, "line": mask(line)}


def result(cid, title, status, why, *, evidence=(), highlights=(), metrics=None, thresholds=None, notes=()):
    seen, unique = set(), []
    for e in evidence:                                  # the same row can back two findings: list it once
        if (e["t"], e["line"]) not in seen:
            seen.add((e["t"], e["line"]))
            unique.append(e)
    evidence = sorted(unique, key=lambda e: (e["t"] is None, e["t"] or 0))
    return {"id": cid, "title": title, "status": status, "why": why, "metrics": metrics or {},
            "thresholds": thresholds or {}, "evidence": evidence[:EVIDENCE_MAX], "evidence_total": len(evidence),
            "highlights": sorted(highlights, key=lambda h: h["t"]), "notes": list(notes)}


def mark(t, label):
    return {"t": round(t, 3), "utc": iso(t), "label": label}


# ------------------------------------------------------------------ sources

def read_jsonl(paths, stats=None):
    """Dict rows of JSON-lines files, in file order; bad or half-written lines are skipped (counted in stats)."""
    rows = []
    for path in paths:
        try:
            with open(path, "rb") as handle:
                for raw in handle:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        row = json.loads(raw)
                    except ValueError:
                        row = None
                    if isinstance(row, dict):
                        rows.append(row)
                    elif stats is not None:
                        stats["bad_lines"] = stats.get("bad_lines", 0) + 1
        except OSError:
            continue
    return rows


def component(row):
    """Who wrote an events.jsonl row, from its shape: the director and the supervisor name themselves; the agent's rows
    have a numeric `t` and `utc` (its own `source` field means something else: model/chat/routine, http/file)."""
    src = row.get("source")
    if src == "director":
        return "director"
    if src == "streamer_up":
        return "supervisor"
    t = row.get("t")
    if isinstance(t, (int, float)) and not isinstance(t, bool) and "utc" in row:
        return "agent"
    return "other"


def timed(rows, *keys):
    """Rows with `_t` (unix seconds from the first key that parses), sorted by it; rows without a time dropped."""
    out = []
    for row in rows:
        for key in keys or ("t", "utc"):
            t = to_unix(row.get(key))
            if t is not None:
                row["_t"] = t
                out.append(row)
                break
    out.sort(key=lambda r: r["_t"])
    return out


GAME_LINE = re.compile(rb"^\[(\d{4})\.(\d\d)\.(\d\d)-(\d\d)\.(\d\d)\.(\d\d):(\d{3})\]\[\s*\d+\]\w+: (?:\w+: )?"
                       rb"(SUB01_[A-Z0-9_]+)(.*)$")
KV = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(\S+)")


def kv(text):
    out = {}
    for key, value in KV.findall(text):
        try:
            out[key] = float(value)
        except ValueError:
            out[key] = value
    return out


def read_game_log(path, since, until):
    """The game's SUB01 lines: periodic PERF / CAM2 / MONITOR* / POSE and STATE (in the window), and the one-off lines
    a later check needs from before it (game starts, MOUTH_READY, MOUTH_FILE_REJECTED). UE stamps are UTC."""
    out = {"perf": [], "cam2": [], "monitor": [], "pose": [], "state": [], "mouth_ready": [], "mouth_rejected": [],
           "init": [], "exists": False}
    try:
        handle = open(path, "rb")
    except OSError:
        return out
    out["exists"] = True
    with handle:
        for raw in handle:
            if b"SUB01_" not in raw:
                continue
            m = GAME_LINE.match(raw.rstrip(b"\r\n"))
            if not m:
                continue
            y, mo, d, hh, mi, ss, ms = (int(x) for x in m.groups()[:7])
            t = datetime(y, mo, d, hh, mi, ss, tzinfo=timezone.utc).timestamp() + ms / 1000.0
            if t > until:
                continue
            tag, rest = m.group(8).decode(), m.group(9).decode("utf-8", "replace").strip()
            item = {"t": t, "tag": tag, "line": raw.decode("utf-8", "replace").strip()}
            if tag == "SUB01_NATIVE_INIT_BEGIN":
                out["init"].append(item)
            elif tag == "SUB01_STREAMER_VISUAL_MOUTH_READY":
                out["mouth_ready"].append(dict(item, rig=(re.search(r"rig=(\S+)", rest) or [None, "?"])[1]))
            elif tag == "SUB01_STREAMER_VISUAL_MOUTH_FILE_REJECTED":
                out["mouth_rejected"].append(item)
            elif t < since:
                continue
            elif tag == "SUB01_STREAMER_VISUAL_PERF":
                out["perf"].append(dict(item, **kv(rest)))
            elif tag == "SUB01_STREAMER_VISUAL_CAM2":
                out["cam2"].append(dict(item, **kv(rest)))
            elif tag == "SUB01_STREAMER_VISUAL_POSE":
                out["pose"].append(dict(item, **kv(rest)))
            elif tag.startswith("SUB01_STREAMER_VISUAL_MONITOR") and "fps" in rest:
                out["monitor"].append(dict(item, **kv(rest)))
            elif tag == "SUB01_STREAMER_VISUAL_STATE":
                parts = rest.split("->")
                out["state"].append(dict(item, frm=parts[0].strip(), to=parts[-1].strip()))
    return out


LISTEN = re.compile(r"voice: listening on \S+ engine=(\S+) voice=(\S+)")
FALLBACK = re.compile(r"voice: (\S+) unavailable \((.*)\); falling back to (\S+)")
SPOKEN = re.compile(r"voice: spoken id=(\d{8}T\d{6}-\d+) tag=(\S+) ([\d.]+)s cut=(\w+)")


def read_voice_log(path):
    """voice.log has no timestamps but is in order: replay it. -> {utterance id: {engine, voice, fallback, known}}.
    A `listening on` line starts a server (engine and prompt: the state is known from there); a `falling back` line
    holds until the next start. An utterance before any start line has an unknown engine."""
    state, out = {"engine": None, "voice": None, "fallback": None, "started": None, "known": False}, {}
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in re.split(r"[\r\n]+", text):
        m = LISTEN.search(line)
        if m:
            state = {"engine": m.group(1), "voice": m.group(2), "fallback": None, "started": line[m.start():],
                     "known": True}
            continue
        m = FALLBACK.search(line)
        if m:
            state = dict(state, fallback=m.group(3), fallback_line=line[m.start():])
            continue
        for m in SPOKEN.finditer(line):
            out[m.group(1)] = dict(state, line=line[m.start():m.end()])
    return out


SEGMENT_RE = re.compile(r"^(sub01-(\d{8}-\d{6}))-(\d{3})\.mp4$")


def list_recordings(directory):
    out = []
    try:
        entries = list(os.scandir(directory))
    except OSError:
        return out
    for entry in entries:
        m = SEGMENT_RE.match(entry.name)
        if not m or not entry.is_file():
            continue
        run_t = datetime.strptime(m.group(2), "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc).timestamp()
        st = entry.stat()
        index = int(m.group(3))
        out.append({"name": entry.name, "path": entry.path, "run": m.group(1), "index": index, "bytes": st.st_size,
                    "mtime": st.st_mtime, "start": run_t + index * SEGMENT_S, "end": st.st_mtime, "probed": False})
    out.sort(key=lambda s: (s["run"], s["index"]))
    return out


def read_hls(hls_dir):
    """live.m3u8 -> [{uri, path, extinf, start}] (start from EXT-X-PROGRAM-DATE-TIME), or None without a playlist."""
    try:
        text = (Path(hls_dir) / "live.m3u8").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    out, extinf, pdt, carried = [], None, None, None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#EXTINF:"):
            try:
                extinf = float(line[8:].split(",")[0])
            except ValueError:
                extinf = None
        elif line.startswith("#EXT-X-PROGRAM-DATE-TIME:"):
            pdt = to_unix(line.split(":", 1)[1])
        elif line.startswith("#EXT-X-DISCONTINUITY"):
            carried = None                                # a new run: only a new PDT dates what follows
        elif line and not line.startswith("#"):
            start = pdt if pdt is not None else carried   # a PDT dates its segment; the next ones follow on
            out.append({"uri": line, "path": str(Path(hls_dir) / line), "extinf": extinf, "start": start})
            carried = start + extinf if start is not None and extinf else None
            extinf, pdt = None, None
    return out


def ffprobe_count(path, ffprobe="ffprobe", timeout=180.0):
    """Packets of the first video stream counted by the demuxer (no decode) over the video stream's duration (the
    container's when the stream has none). -> {packets, duration, fps, r_frame_rate (metadata only)} or {error}."""
    cmd = [ffprobe, "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
           "stream=nb_read_packets,r_frame_rate,duration:format=duration", "-of", "json", str(path)]

    def stat():
        try:
            st = os.stat(path)
            return st.st_size, st.st_mtime
        except OSError:
            return None
    before = stat()
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"error": f"{type(error).__name__}: {error}"[:200]}
    tail = (done.stderr or "").strip().splitlines()[-1:]
    if done.returncode != 0:
        return {"error": mask(f"ffprobe exited {done.returncode}: " + (tail[0] if tail else ""))}
    try:
        data = json.loads(done.stdout or "{}")
        stream = (data.get("streams") or [{}])[0]
        packets = int(stream.get("nb_read_packets"))
    except (ValueError, TypeError, IndexError):
        return {"error": mask(tail[0] if tail else "no video stream")}
    duration = to_unix(stream.get("duration")) or to_unix((data.get("format") or {}).get("duration")) or 0.0
    out = {"packets": packets, "duration": round(duration, 3), "r_frame_rate": stream.get("r_frame_rate"),
           "fps": round(packets / duration, 3) if duration > 0 else None}
    if stat() != before:                 # still being written: the count covers the fragments written so far
        out["growing"] = True
    return out


class Sources:
    """Everything read for one window. Paths are arguments so tests can point them at fixtures."""

    def __init__(self, streamer_dir, game_log, since, until, desktop_dirs=None, ffprobe="ffprobe", probe=True,
                 probe_timeout=180.0):
        self.dir, self.since, self.until = Path(streamer_dir), since, until
        self.read, self.missing = {}, {}
        stats = {}
        rows = timed(read_jsonl([self.dir / "events.1.jsonl", self.dir / "events.jsonl"], stats), "t", "utc")
        by = {"agent": [], "director": [], "supervisor": [], "other": []}
        for row in rows:
            by[component(row)].append(row)
        self.agent, self.director, self.supervisor = by["agent"], by["director"], by["supervisor"]
        self._note("events.jsonl", self.dir / "events.jsonl", len(rows), stats)
        stats = {}
        self.timeline = timed(read_jsonl([self.dir / "speech" / "timeline.jsonl"], stats), "start_utc")
        self._note("speech/timeline.jsonl", self.dir / "speech" / "timeline.jsonl", len(self.timeline), stats)
        self.voice = read_voice_log(self.dir / "logs" / "voice.log")
        self._note("logs/voice.log", self.dir / "logs" / "voice.log", None if self.voice is None else len(self.voice))
        self.rehearsal = timed(read_jsonl([self.dir / "rehearsal.jsonl"]), "t")
        self._note("rehearsal.jsonl", self.dir / "rehearsal.jsonl", len(self.rehearsal))
        self.watchdog = timed(read_jsonl([self.dir / "watchdog.jsonl"]), "t")
        self._note("watchdog.jsonl", self.dir / "watchdog.jsonl", len(self.watchdog))
        self.runners = {}
        for d in [Path(x) for x in (desktop_dirs or [self.dir / "desktop-vagon", self.dir / "desktop"])]:
            stats = {}
            rows = timed(read_jsonl([d / "events.jsonl.1", d / "events.jsonl"], stats), "t")
            self._note(f"{d.name}/events.jsonl", d / "events.jsonl", len(rows), stats)
            if (d / "events.jsonl").exists():
                self.runners[d.name] = {"rows": rows, "vagon": any(r.get("kind") == "vagon" for r in rows)}
        self.game = read_game_log(game_log, since, until)
        self._note("game log", Path(game_log), sum(len(v) for v in self.game.values() if isinstance(v, list))
                   if self.game["exists"] else None)
        self.stop_file = self._stop()
        self.supervisor_state = self._json(self.dir / "supervisor.json")
        self.recordings = list_recordings(self.dir / "recordings")
        self.hls = read_hls(self.dir / "hls")
        self._note("hls/live.m3u8", self.dir / "hls" / "live.m3u8", None if self.hls is None else len(self.hls))
        self.probe_enabled, self.ffprobe, self.probe_timeout = probe, ffprobe, probe_timeout
        self.probes, self._air = {}, None
        if probe:
            self._probe_window()

    def _note(self, name, path, count, stats=None):
        if count is None or not Path(path).exists():
            self.missing[name] = str(path)
        else:
            self.read[name] = {"path": str(path), "rows": count, **(stats or {})}

    def _json(self, path):
        try:
            return json.loads(Path(path).read_text())
        except (OSError, ValueError):
            return None

    def _stop(self):
        path = self.dir / "STOP"
        try:
            st, text = path.stat(), path.read_text(errors="replace")
        except OSError:
            return None
        try:                                    # the watchdog writes {"by", "why", "t"}; an operator's touch is empty
            since = to_unix(json.loads(text).get("t")) or st.st_mtime
        except (ValueError, AttributeError):
            since = st.st_mtime
        return {"since": since, "text": mask(text, 160)}

    def window_recordings(self):
        return [s for s in self.recordings if s["end"] >= self.since and s["start"] <= self.until + 5]

    def window_hls(self):
        out = []
        for seg in self.hls or []:
            start = seg["start"]
            if start is not None and start + (seg["extinf"] or 4.0) >= self.since and start <= self.until:
                out.append(seg)
        return out

    def _probe_window(self):
        # HLS first: the muxer deletes a segment ~4 s after it leaves the playlist, so the playlist is read again and
        # probed at once; a segment gone meanwhile is skipped (rotated), not counted as a failure
        self.hls = read_hls(self.dir / "hls") if self.hls is not None else None
        for seg in self.window_hls():
            if os.path.exists(seg["path"]):
                self.probes[seg["path"]] = ffprobe_count(seg["path"], self.ffprobe, self.probe_timeout)
        for seg in self.window_recordings():
            res = ffprobe_count(seg["path"], self.ffprobe, self.probe_timeout)
            self.probes[seg["path"]] = res
            if res.get("duration"):
                seg.update(start=seg["mtime"] - res["duration"], probed=True)   # as streamer_highlights.segments()

    def locate(self, t):
        """The recording segment holding moment t and the offset into its media timeline, or None. Neighbouring
        segments overlap by up to a second (mtime precision): the one that starts last wins."""
        holding = [s for s in self.recordings if s["start"] - 0.05 <= t < s["end"] + 0.5]
        if not holding:
            return None
        seg = max(holding, key=lambda s: s["start"])
        return {"segment": seg["name"], "offset_s": round(max(0.0, t - seg["start"]), 1),
                "offset": mmss(t - seg["start"]), "approx": not seg["probed"]}

    def in_window(self, rows):
        return [r for r in rows if self.since <= r["_t"] <= self.until]

    def air(self):
        if self._air is None:
            self._air = on_air(self)
        return self._air

    def recorded(self, t):
        """The director was recording at moment t (an ffmpeg run on air)."""
        return any(s["start"] <= t <= s["end"] for s in self.air())

    def events_gap(self):
        """None when events.jsonl covers the window (rows within log_fresh_s of both ends), else why not."""
        rows = self.agent + self.director + self.supervisor
        if "events.jsonl" in self.missing or not rows:
            return "no events.jsonl rows"
        fresh = TH["log_fresh_s"]
        if not any(abs(r["_t"] - self.since) <= fresh for r in rows):
            first = min(r["_t"] for r in rows)
            return (f"events.jsonl starts at {iso(first)}, after the window start (rotated?)" if first > self.since else
                    f"events.jsonl has no row within {fresh / 60:.0f} min of the window start")
        if not any(abs(r["_t"] - self.until) <= fresh for r in rows):
            before = [r["_t"] for r in rows if r["_t"] <= self.until]
            return (f"events.jsonl has no row after {iso(max(before))}: its coverage of the window is unknown" if before
                    else "events.jsonl has no row near the window end")
        return None

    def agent_context(self):
        """Why the agent may have nothing in the window."""
        bits = []
        if self.stop_file:
            bits.append(f"the agent is held by the STOP file (since {iso(self.stop_file['since'])})")
        svc = ((self.supervisor_state or {}).get("services") or {}).get("agent") or {}
        if svc.get("status"):
            bits.append(f"supervisor: agent {svc['status']}" + (f" ({svc.get('detail')})" if svc.get("detail") else ""))
        last = [r for r in self.agent if r["_t"] < self.since]
        if last:
            bits.append(f"last agent row {iso(last[-1]['_t'])} ({last[-1].get('kind')})")
        return "; ".join(bits)

    def vagon_context(self):
        for name, runner in self.runners.items():
            if runner["vagon"]:
                rows = [r for r in runner["rows"] if r.get("kind") == "vagon" and r["_t"] <= self.until]
                if rows:
                    return f"Vagon runner ({name}) last state {rows[-1].get('state')} at {iso(rows[-1]['_t'])}"
        return "no Vagon runner rows"


# ------------------------------------------------------------------ criteria

def agent_window(src):
    return src.in_window(src.agent)


def absent(src, cid, title, what, th, extra=""):
    """The window's content lacks something: FAIL when events.jsonl covers the window, else MISSING."""
    gap = src.events_gap()
    if gap:
        return result(cid, title, MISSING, f"{gap}: cannot assess ({what})", thresholds=th)
    ctx = src.agent_context()
    return result(cid, title, FAIL, f"no {what} in the window" + (f": {extra}" if extra else "")
                  + (f" ({ctx})" if ctx and not agent_window(src) else ""), thresholds=th)


def inactive_intervals(src):
    """Agent intervals that are not activity: quiet mode, held after failures or a frozen stream, a privacy cut."""
    out, open_ = [], {}
    ends = {"quiet_end": "quiet", "resume": "held", "resume_latches": "stream_frozen"}   # each state has its own end
    for r in src.agent:
        k = r.get("kind")
        if k in ("quiet", "held", "stream_frozen"):
            open_.setdefault(k, r["_t"])
        elif k in ends and ends[k] in open_:
            out.append((open_.pop(ends[k]), r["_t"]))
        elif k == "privacy":
            if r.get("on"):
                open_.setdefault("privacy", r["_t"])
            elif "privacy" in open_:
                out.append((open_.pop("privacy"), r["_t"]))
    out += [(t, src.until) for t in open_.values()]
    return union(out)


def eval_activity(src):
    title, th = "A change of activity", {"dwell_s": TH["dwell_s"], "strong": "browse <-> game",
                                         "weak": "video (inferred from the host), a site change inside browsing"}
    rows = [r for r in src.agent if r["_t"] <= src.until]
    win = agent_window(src)
    if not any(r.get("kind") == "action" for r in win):
        return absent(src, "activity_change", title, "agent activity", th)
    game, host, label, label_t, points, weak = False, "", None, None, [], []
    for r in rows:
        kind, inside = r.get("kind"), r["_t"] >= src.since
        new = None
        if kind == "routine_end" and r.get("why") in ROUTINE_OK:
            game = r.get("name") == "launch_game"
            new = "game" if game else "browse"
        elif kind == "outcome" and r.get("url") and "vagon.io" not in str(r.get("url")):
            host = host_of(r["url"]) or host
        elif kind == "action" and r.get("source") != "routine":
            act = r.get("action") if isinstance(r.get("action"), dict) else {"action": r.get("action")}
            if act.get("action") in ("wait", "zoom"):
                continue
            target = host_of(act["url"]) if act.get("action") == "navigate" and act.get("url") else \
                ("search" if act.get("action") == "search" else None)
            if target and target != host and inside and r.get("source") in ("model", "chat"):
                weak.append((r, f"site change to {target}"))
            host = target or host
            new = "game" if game else "video" if is_video(host) else "browse"
        if new is None:
            continue
        if not inside:
            label, label_t = new, r["_t"]                 # carried in from before the window ...
            continue
        if not points and label is not None and src.since - label_t <= TH["carry_s"]:
            points.append((src.since, label, None))       # ... when the agent was active just before it
        points.append((r["_t"], new, r))
        label = new
    spans = []
    for t, lab, r in points:
        if spans and spans[-1]["label"] == lab:
            spans[-1]["n"] += 1
        else:
            spans.append({"label": lab, "start": t, "n": 1, "row": r})
    last_t = min(src.until, max(r["_t"] for r in win))
    idle = inactive_intervals(src)
    air = union([(s["start"], s["end"]) for s in src.air()])
    for i, span in enumerate(spans):
        last = i + 1 == len(spans)
        span["end"] = last_t if last else spans[i + 1]["start"]
        span["dwell"] = max(0.0, span["end"] - span["start"] - overlap(span["start"], span["end"], idle))
        span["recorded"] = sum(max(0.0, (b - a) - overlap(a, b, idle)) for a, b in   # active AND on air
                               ((max(x, span["start"]), min(y, span["end"])) for x, y in air) if b > a)
        # half-open [start, end): the row that opens the next span (a routine_end) verifies that span only
        span["ok"] = sum(1 for r in win if span["start"] <= r["_t"] and (r["_t"] < span["end"] or
                                                                          (last and r["_t"] <= span["end"])) and (
            (r.get("kind") == "outcome" and r.get("verdict") in OK_VERDICTS)
            or (r.get("kind") == "routine_end" and r.get("why") in ROUTINE_OK)))
    evidence = [ev(s["start"], "agent", s["row"] or f"carried in: {s['label']}") for s in spans]
    strong, soft = [], []
    for a, b in zip(spans, spans[1:]):
        good = all(s["dwell"] >= TH["dwell_s"] and s["recorded"] >= TH["dwell_s"] and s["ok"] for s in (a, b))
        (strong if good and {a["label"], b["label"]} == {"browse", "game"} and src.recorded(b["start"]) else
         soft).append((a, b))
    for r, what in weak[:10]:
        evidence.append(ev(r["_t"], "agent", r))
    metrics = {"spans": [{"label": s["label"], "start_utc": iso(s["start"]), "end_utc": iso(s["end"]),
                          "points": s["n"], "dwell_s": round(s["dwell"], 1), "recorded_s": round(s["recorded"], 1),
                          "verified": s["ok"]} for s in spans],
               "weak_site_changes": len(weak), "inactive_s": round(overlap(src.since, src.until, idle), 1)}
    highlights = [mark(b["start"], f"activity {a['label']} -> {b['label']}") for a, b in strong + soft]
    highlights += [mark(r["_t"], f"{what} (weak)") for r, what in weak[:5]]
    if strong:
        a, b = strong[0]
        return result("activity_change", title, PASS, f"{a['label']} ({a['dwell']:.0f} s) -> {b['label']} "
                      f"({b['dwell']:.0f} s) at {hms(b['start'])}Z", evidence=evidence, highlights=highlights,
                      metrics=metrics, thresholds=th)
    labels = sorted({s["label"] for s in spans})
    why = (f"one activity only ({', '.join(labels)})" if len(labels) == 1 else
           "no browse <-> game change with 60 s of verified, recorded activity on both sides")
    if weak or soft:
        why += f"; weak changes only ({len(soft)} label change(s), {len(weak)} site change(s))"
    return result("activity_change", title, FAIL, why, evidence=evidence, highlights=highlights, metrics=metrics,
                  thresholds=th)


def seqs_of(row):
    return {s for s in (row.get("seqs") or []) if isinstance(s, int)}


def spoken(src, seq, t0, t1):
    """The first `speech` row (voiced, not a caption) for chat seq `seq` between t0 and t1, or None."""
    for r in src.agent:
        if t0 <= r["_t"] <= t1 and r.get("kind") == "speech" and seq in seqs_of(r):
            return r
    return None


def seq_limit(src, seq, t):
    """Where chat seq `seq` (seen at t) stops identifying one request: the window end, the agent's next start (the
    supervisor's service_started row) or the next chat row with the same seq (a restarted agent counts from 1)."""
    later = [r["_t"] for r in src.agent if r["_t"] > t and r.get("kind") == "chat" and r.get("seq") == seq]
    later += [r["_t"] for r in src.supervisor if r["_t"] > t and r.get("kind") == "service_started"
              and r.get("service") == "agent"]
    return min([src.until] + later)


def bound_outcomes(src, seq, t0, t1):
    """Verified results bound to request `seq` between t0 and t1: the outcomes after an action with decision_id
    req-<seq> (until the next action row), and the routine_end of a game routine started for it."""
    out, bound, routine = [], False, False
    for r in src.agent:
        if r["_t"] < t0 or r["_t"] > t1:
            continue
        kind = r.get("kind")
        if kind == "action":
            bound = r.get("decision_id") == f"req-{seq}"
        elif kind == "outcome" and bound and r.get("verdict") in OK_VERDICTS:
            out.append(r)
        elif kind == "routine_start":
            routine = r.get("seq") == seq
        elif kind == "routine_end" and routine:
            routine = False
            if r.get("why") in ROUTINE_OK:
                out.append(r)
    return out


def eval_chat_executed(src):
    title = "A chat request carried out"
    th = {"end_why": "done", "bound": "action decision_id req-<seq> or its game routine", "verdicts": list(OK_VERDICTS),
          "spoken_within_s": TH["chat_voice_s"]}
    reqs = [r for r in agent_window(src) if r.get("kind") == "chat_request" and r.get("decision") == "executed"]
    if not reqs:
        return absent(src, "chat_executed", title, "executed chat request", th)
    evidence, highlights, good, bad = [], [], [], []
    for req in reqs:                                     # everything judged lies inside the window and before the seq
        seq, kind = req.get("seq"), req.get("reason")    # can be reused by a restarted agent
        limit = seq_limit(src, seq, req["_t"])
        end = next((r for r in src.agent if r.get("kind") == "chat_request_end" and r.get("seq") == seq
                    and req["_t"] <= r["_t"] <= limit), None)
        t1 = end["_t"] if end else limit
        results = bound_outcomes(src, seq, req["_t"], min(t1 + 30, limit))
        line = spoken(src, seq, req["_t"], min(t1 + TH["chat_voice_s"], limit))
        evidence += [ev(r["_t"], "agent", r) for r in [req] + results[:3] + [x for x in (end, line) if x]]
        problems = []
        if kind in NON_DESKTOP_REQUESTS:
            problems.append(f"not a desktop request ({kind})")
        if not end:
            problems.append("no chat_request_end")
        elif end.get("why") != "done":
            problems.append(f"ended {end.get('why')}")
        if not results:
            problems.append("no verified result bound to it" + (" (model-picked: unproven)" if kind == "look" else ""))
        if not line:
            problems.append("no spoken answer")
        if not src.recorded(req["_t"]) or (line and not src.recorded(line["_t"])):
            problems.append("not recorded")              # the request and its spoken answer both on air
        (bad if problems else good).append((req, problems))
        highlights.append(mark(req["_t"], f"chat request #{seq} {kind}: " + (", ".join(problems) or "carried out")))
    metrics = {"executed": len(reqs), "carried_out": len(good), "problems": {str(r.get("seq")): p for r, p in bad}}
    if good:
        req = good[0][0]
        return result("chat_executed", title, PASS, f"request #{req.get('seq')} ({req.get('reason')}) carried out, "
                      f"verified and answered at {hms(req['_t'])}Z" + (f" (+{len(good) - 1} more)" if len(good) > 1 else ""),
                      evidence=evidence, highlights=highlights, metrics=metrics, thresholds=th)
    return result("chat_executed", title, FAIL, "; ".join(f"#{r.get('seq')}: {', '.join(p)}" for r, p in bad[:4]),
                  evidence=evidence, highlights=highlights, metrics=metrics, thresholds=th)


def eval_chat_refused(src):
    title = "A chat request refused"
    th = {"operational_reasons_apart": list(OPERATIONAL_REFUSALS), "spoken_within_s": TH["chat_voice_s"],
          "executed": "never (no action bound to it)", "redirects": "listed apart (executed, then undone)"}
    refusals, redirects = [], []
    for r in agent_window(src):
        if r.get("kind") == "chat_request" and r.get("decision") == "refused":
            refusals.append((r, r.get("seq"), str(r.get("reason"))))
        elif r.get("kind") == "chat" and r.get("cls") in ("human", "inject", "finance"):
            refusals.append((r, r.get("seq"), f"class {r.get('cls')}"))
        elif r.get("kind") == "request_redirect":      # the request ran, landed somewhere refused and was undone
            redirects.append(r)
    if not refusals:
        res = absent(src, "chat_refused", title, "refused chat request", th)
        res["metrics"]["redirects"] = len(redirects)
        return res
    evidence, highlights, good, executed = [], [], [], []
    for row, seq, reason in refusals:
        operational = reason in OPERATIONAL_REFUSALS
        t_end = seq_limit(src, seq, row["_t"])           # a restarted agent numbers its chat from 1 again
        line = spoken(src, seq, row["_t"], min(row["_t"] + TH["chat_voice_s"], t_end))
        caption = next((r for r in src.agent if row["_t"] <= r["_t"] <= min(row["_t"] + TH["chat_voice_s"], t_end)
                        and r.get("kind") == "caption" and seq in seqs_of(r)), None)
        acted = [r for r in src.agent if r.get("kind") == "action" and r.get("decision_id") == f"req-{seq}"
                 and row["_t"] <= r["_t"] <= t_end]
        evidence += [ev(r["_t"], "agent", r) for r in [row] + [x for x in (line, caption) if x] + acted]
        mode = "spoken" if line else "caption only (not on air)" if caption else "not delivered"
        state = "operational, apart" if operational else "EXECUTED" if acted else mode
        highlights.append(mark(row["_t"], f"refusal #{seq} {reason}: {state}"))
        if acted:
            executed.append(seq)
        elif not operational and line and src.recorded(row["_t"]) and src.recorded(line["_t"]):
            good.append((row, seq, reason))              # the refusal and its spoken line both on air
    for r in redirects:
        evidence.append(ev(r["_t"], "agent", r))
        highlights.append(mark(r["_t"], f"request #{r.get('seq')} redirected ({r.get('why')}): undone, not counted"))
    metrics = {"refusals": len(refusals), "policy_spoken_recorded": len(good),
               "operational": sum(1 for _, _, why in refusals if why in OPERATIONAL_REFUSALS),
               "redirects": len(redirects)}
    if executed:
        return result("chat_refused", title, FAIL, "refused but executed: " + ", ".join(f"#{s}" for s in executed),
                      evidence=evidence, highlights=highlights, metrics=metrics, thresholds=th)
    if good:
        row, seq, reason = good[0]
        return result("chat_refused", title, PASS, f"#{seq} refused ({reason}) and spoken at {hms(row['_t'])}Z",
                      evidence=evidence, highlights=highlights, metrics=metrics, thresholds=th)
    why = ("only operational refusals" if metrics["operational"] == len(refusals)
           else "no policy refusal was spoken while recording")
    return result("chat_refused", title, FAIL, why, evidence=evidence, highlights=highlights, metrics=metrics,
                  thresholds=th)


def output_healthy(src, run, after):
    """A recording run's output after `after`, measured inside the window: True (a segment row or a probed segment of
    the run at >= 59.9 fps with no dup/drop), False (one below), None (nothing measured in the window)."""
    rows = [r for r in src.director if r.get("kind") == "segment_fps" and r.get("run") == run
            and after < r["_t"] <= src.until and float(r.get("wall_s") or 0) >= 10]
    for r in rows:
        return float(r.get("fps_media") or 0) >= TH["output_fps"] and not (r.get("dup_frames") or r.get("drop_frames"))
    for seg in src.recordings:                           # only segments of the window are probed
        res = src.probes.get(seg["path"]) or {}
        if seg["run"] == run and res.get("fps") and seg["end"] > after:
            return res["fps"] >= TH["output_fps"]
    return None


def recovery_rules(src):
    """[(fault row, source, label, rows to search, predicate, deadline key, needs_health)] before the window end."""
    out = []
    for r in src.director:
        k = r.get("kind")
        if k in ("ffmpeg_exited", "watchdog_restart", "speed_restart", "ffmpeg_spawn_failed"):
            out.append((r, "director", f"director {k}", src.director,
                        lambda x: x.get("kind") == "ffmpeg_started", "director", True))
        elif k == "layout_switch_failed":
            want = r.get("layout")
            out.append((r, "director", f"director layout_switch_failed ({want})", src.director,
                        lambda x, w=want: x.get("kind") in ("layout_switched", "ffmpeg_started") and x.get("layout") == w,
                        "director", False))
        elif k == "cam2_changed" and r.get("cam2") is False:
            off = [c for c in src.game["cam2"] if abs(c["t"] - r["_t"]) <= 60 and c.get("on") == 0]
            if off:                                       # the game switched cam2 off: intended, not a fault
                continue
            rows = sorted(src.director + [dict(c, _t=c["t"], _game=True) for c in src.game["cam2"]], key=lambda x: x["_t"])
            out.append((r, "director", f"cam2 lost ({r.get('reason')})", rows,
                        lambda x: (x.get("_game") and x.get("on") == 1 and (x.get("fps") or 0) > 0)
                        or (x.get("kind") == "cam2_changed" and x.get("cam2") is True)
                        or (x.get("kind") == "ffmpeg_started" and x.get("cam2") is True), "cam2", False))
    for r in src.supervisor:
        if r.get("kind") in ("service_crashed", "service_unhealthy", "service_failed"):
            svc = r.get("service")
            out.append((r, "supervisor", f"supervisor {r.get('kind')} {svc}", src.supervisor,
                        lambda x, s=svc: x.get("kind") == "service_up" and x.get("service") == s, "supervisor", False))
    verified = lambda x: x.get("kind") == "outcome" and x.get("verdict") in OK_VERDICTS        # noqa: E731
    for r in src.agent:
        k = r.get("kind")
        if k == "quiet" and r.get("mode") == "error":
            out.append((r, "agent", "agent quiet mode (model error)", src.agent,
                        lambda x: x.get("kind") == "quiet_end", "agent", False))
        elif k in ("error", "action_timeout"):
            out.append((r, "agent", f"agent {k} ({mask(r.get('where') or r.get('why') or '', 40)})", src.agent,
                        verified, "agent", False))
        elif k == "held":
            out.append((r, "agent", "agent held after failures", src.agent,
                        lambda x: x.get("kind") == "resume", "agent", False))
        elif k == "stream_frozen":
            out.append((r, "agent", "agent saw a frozen stream", src.agent,
                        lambda x: x.get("kind") == "resume_latches", "agent", False))
        elif k == "provider_switch" and not r.get("back"):
            to = r.get("to")
            out.append((r, "agent", f"agent provider failed, switched to {to}", src.agent,
                        lambda x, p=to: x.get("kind") == "decision" and x.get("provider") == p, "agent", False))
    for name, runner in src.runners.items():
        for r in runner["rows"]:
            if r.get("kind") == "relaunch":
                out.append((r, "runner", f"runner {name}: browser relaunch ({r.get('why')})", runner["rows"],
                            lambda x: x.get("kind") == "browser" and x.get("state") == "ready", "runner", False))
            elif r.get("kind") == "vagon" and r.get("state") == "disconnected":
                out.append((r, "runner", f"Vagon disconnected ({r.get('phase')})", runner["rows"],
                            lambda x: x.get("kind") == "vagon" and x.get("state") == "connected", "vagon", False))
    resumes = sorted(src.agent + src.supervisor, key=lambda x: x["_t"])
    for r in src.watchdog:
        if r.get("kind") == "trip":
            out.append((r, "watchdog", f"watchdog trip ({mask(r.get('why') or '', 50)})", resumes,
                        lambda x: x.get("kind") == "resume", "watchdog", False))
    return out


def eval_errors(src):
    title = "An error that was recovered"
    th = {"deadline_s": TH["deadline"], "incident_merge_s": TH["incident_merge_s"], "induced": list(INDUCED),
          "recording_faults": f"a restart plus output >= {TH['output_fps']} fps afterwards"}
    injects = [r for r in src.rehearsal if r.get("kind") == "inject"] + \
              [r for r in src.agent if r.get("kind") == "inject" and r.get("consumed")]
    faults = []
    for row, source, label, rows, pred, dkey, health in recovery_rules(src):
        t = row["_t"]
        if not src.since <= t <= src.until:
            continue
        deadline = TH["deadline"][dkey]
        cutoff = min(src.until, t + deadline)            # nothing after the window counts
        rec = next((x for x in rows if t < x["_t"] <= cutoff and pred(x)), None)
        state = "recovered" if rec else ("pending" if t + deadline > src.until else "unrecovered")
        if rec and health:                               # a restart is a recovery once its output is measured at 60
            ok = output_healthy(src, rec.get("run"), rec["_t"])
            due = rec["_t"] + SEGMENT_S + 60             # its first segment row is due by then
            state = "recovered" if ok else "unrecovered" if ok is False or due <= src.until else "pending"
        induced = next((i.get("event") or i.get("inject") for i in injects if 0 <= t - i["_t"] <= 30), None)
        faults.append({"t": t, "source": source, "label": label + (f" [induced: {induced}]" if induced else ""),
                       "kind": label.split(" (")[0], "state": state, "row": row, "rec": rec})
    incidents, rank = [], {"recovered": 0, "pending": 1, "unrecovered": 2}
    for f in sorted(faults, key=lambda f: f["t"]):       # one incident per burst of the same fault, judged by its worst
        same = [i for i in incidents if i["kind"] == f["kind"] and f["t"] - i["last"] <= TH["incident_merge_s"]]
        if same:
            inc = same[-1]
            inc.update(last=f["t"], n=inc["n"] + 1, state=max(inc["state"], f["state"], key=rank.get),
                       rec=f["rec"] if f["state"] == "recovered" else None)
        else:
            incidents.append(dict(f, first=f["t"], last=f["t"], n=1))
    evidence, highlights = [], []
    for inc in incidents:
        evidence.append(ev(inc["first"], inc["source"], inc["row"]))
        if inc["rec"]:
            evidence.append(ev(inc["rec"]["_t"], inc["source"], {k: v for k, v in inc["rec"].items() if k != "_game"}
                               if not inc["rec"].get("_game") else inc["rec"].get("line")))
        outage = inc["rec"]["_t"] - inc["first"] if inc["rec"] else None
        inc["outage"] = outage
        tail = {"recovered": f"recovered, outage {outage:.0f} s" if outage is not None else "recovered",
                "pending": "recovery pending at the window end", "unrecovered": "NOT recovered"}[inc["state"]]
        highlights.append(mark(inc["first"], f"{inc['label']}" + (f" x{inc['n']}" if inc["n"] > 1 else "") + f": {tail}"))
    by = {s: [i for i in incidents if i["state"] == s] for s in ("recovered", "pending", "unrecovered")}
    metrics = {"faults": len(faults), "incidents": len(incidents), **{k: len(v) for k, v in by.items()},
               "outage_s": [round(i["outage"], 1) for i in by["recovered"] if i["outage"] is not None]}
    if by["unrecovered"]:
        return result("error_recovered", title, FAIL, "not recovered: " + "; ".join(
            f"{hms(i['first'])}Z {i['label']}" for i in by["unrecovered"][:3]), evidence=evidence,
            highlights=highlights, metrics=metrics, thresholds=th)
    if by["pending"]:
        return result("error_recovered", title, MISSING, "recovery still pending at the window end (extend the window): "
                      + "; ".join(i["label"] for i in by["pending"][:3]), evidence=evidence, highlights=highlights,
                      metrics=metrics, thresholds=th)
    if by["recovered"]:
        i = by["recovered"][0]
        return result("error_recovered", title, PASS, f"{i['label']} at {hms(i['first'])}Z, recovered in "
                      f"{i['outage']:.0f} s" + (f" (+{len(by['recovered']) - 1} more)" if len(by["recovered"]) > 1 else ""),
                      evidence=evidence, highlights=highlights, metrics=metrics, thresholds=th)
    return absent(src, "error_recovered", title, "fault (director, supervisor, agent, runner, Vagon, watchdog)", th,
                  "induce one with scripts/streamer_rehearsal.py")


def on_air(src):
    """The director's on-air timeline replayed from all its rows: [{start, end, layout, cam2, voice, run}]."""
    out, cur = [], None

    def close(t):
        if cur is not None and t > cur["start"]:
            out.append(dict(cur, end=t))

    for r in src.director:
        if r["_t"] > src.until:
            break
        k, t = r.get("kind"), r["_t"]
        if k == "ffmpeg_started":
            close(t)
            cur = {"start": t, "layout": r.get("layout"), "cam2": bool(r.get("cam2")), "voice": r.get("voice"),
                   "run": r.get("run")}
        elif cur is None or r.get("run") not in (None, cur["run"]):
            continue
        elif k == "layout_switched":
            close(t)
            cur = dict(cur, start=t, layout=r.get("layout"))
        elif k == "layout_switch_failed":
            close(t)
            cur = dict(cur, start=t, layout=None)
        elif k == "voice_changed":
            close(t)
            cur = dict(cur, start=t, voice=r.get("voice"))
        elif k == "cam2_changed":                         # cam2 lost (or back) while the run still goes on
            close(t)
            cur = dict(cur, start=t, cam2=bool(r.get("cam2")))
        elif k in ("ffmpeg_stopped", "ffmpeg_exited"):
            close(t)
            cur = None
    close(src.until)
    return out


def eval_two_cameras(src):
    title = "Both cameras composed simultaneously"
    th = {"room_s": TH["room_s"], "continuous_s": TH["room_continuous_s"],
          "layout": "room (cam2 full frame + webcam PiP)", "cam2_lines": "on=1 reader=1 fps>0"}
    if src.events_gap():                                 # the on-air timeline is replayed from events.jsonl
        return absent(src, "two_cameras", title, "director recording", th)
    spans = [s for s in src.air() if clip(s["start"], s["end"], src.since, src.until) > 0]
    if not spans:
        return absent(src, "two_cameras", title, "director recording", th)
    by_layout = {}
    for s in spans:
        key = str(s["layout"] or "unknown") + (" (cam2 in the graph)" if s["cam2"] else "")
        by_layout[key] = by_layout.get(key, 0.0) + clip(s["start"], s["end"], src.since, src.until)
    room = []                                            # clipped to the window; touching spans of one run merged
    for s in spans:                                      # (a voice change splits a span, not the composition)
        if s["layout"] == "room" and s["cam2"]:
            a, b = max(s["start"], src.since), min(s["end"], src.until)
            if b <= a:                                   # outside the window (spans are filtered already; kept safe)
                continue
            if room and room[-1]["run"] == s["run"] and a - room[-1]["end"] <= 0.5:
                room[-1]["end"] = b
            else:
                room.append({"start": a, "end": b, "run": s["run"]})
    room_s = sum(s["end"] - s["start"] for s in room)
    longest = max([s["end"] - s["start"] for s in room] or [0.0])
    cam2 = [c for c in src.game["cam2"] if any(s["start"] <= c["t"] <= s["end"] for s in room)]
    bad = [c for c in cam2 if not (c.get("on") == 1 and c.get("reader") == 1 and (c.get("fps") or 0) > 0)]
    evidence = [ev(s["start"], "director", f"on air {s['layout']} cam2={s['cam2']} run={s['run']} from {iso(s['start'])}"
                   f" to {iso(s['end'])}") for s in spans]
    evidence += [ev(c["t"], "game", c["line"]) for c in (bad or cam2)[:5]]
    metrics = {"seconds_by_layout": {k: round(v, 1) for k, v in by_layout.items()}, "room_s": round(room_s, 1),
               "room_longest_s": round(longest, 1), "cam2_lines_in_room": len(cam2), "cam2_lines_bad": len(bad)}
    highlights = [mark(s["start"], f"room layout on air ({s['end'] - s['start']:.0f} s)") for s in room]
    if room_s >= TH["room_s"] and longest >= TH["room_continuous_s"] and cam2 and not bad:
        return result("two_cameras", title, PASS, f"room with cam2 on air {room_s:.0f} s (longest {longest:.0f} s); "
                      f"{len(cam2)} CAM2 lines delivering", evidence=evidence, highlights=highlights, metrics=metrics,
                      thresholds=th)
    if room_s >= TH["room_s"] and longest >= TH["room_continuous_s"] and not cam2:
        if not src.game["exists"]:
            return result("two_cameras", title, MISSING, "no game log: cam2 delivery cannot be checked",
                          evidence=evidence, highlights=highlights, metrics=metrics, thresholds=th)
        why = f"room on air {room_s:.0f} s but no game CAM2 line in that time"
    elif bad:
        why = f"room on air {room_s:.0f} s but cam2 not delivering in {len(bad)} CAM2 line(s)"
    else:
        main = max(by_layout.items(), key=lambda x: x[1])
        why = f"room with cam2 {room_s:.0f} s in all, longest {longest:.0f} s; on air mostly {main[0]} ({main[1]:.0f} s)"
    return result("two_cameras", title, FAIL, why, evidence=evidence, highlights=highlights, metrics=metrics,
                  thresholds=th)


def utterances(src):
    return [u for u in src.in_window(src.timeline) if not u.get("error")]


def u_end(u):
    return to_unix(u.get("end_utc")) or u["_t"]


def no_speech(src, cid, title, th):
    if "speech/timeline.jsonl" in src.missing:
        return result(cid, title, MISSING, "no speech/timeline.jsonl", thresholds=th)
    return absent(src, cid, title, "speech", th)


def speech_highlights(utter):
    return [mark(u["_t"], f"speech [{u.get('tag')}] {mask(u.get('text') or '', 60)}") for u in utter[:10]]


def eval_voice_k07(src):
    title = "K07 voice"
    th = {"utterances": TH["utterances"], "speech_s": TH["speech_s"], "engine": "chatterbox", "prompt": "*k07*",
          "fallback": "none", "replay": "voice.log from a known `listening on` line"}
    utter = utterances(src)
    if not utter:
        return no_speech(src, "voice_k07", title, th)
    if src.voice is None:
        return result("voice_k07", title, MISSING, "no logs/voice.log: the engine cannot be checked", thresholds=th)
    known = [u for u in utter if (src.voice.get(u.get("id")) or {}).get("known")]
    k07 = [u for u in known if src.voice[u["id"]].get("engine") == "chatterbox" and not src.voice[u["id"]].get("fallback")
           and "k07" in str(src.voice[u["id"]].get("voice")).lower()]
    other = [u for u in known if u not in k07]
    speech_s = sum(max(0.0, u_end(u) - u["_t"]) for u in k07)
    evidence = []
    for u in utter[:8]:
        evidence.append(ev(u["_t"], "voice", u))
        if u.get("id") in src.voice:
            evidence.append(ev(u["_t"], "voice", src.voice[u["id"]].get("line")))
    for line in sorted({src.voice[u["id"]].get("started") for u in known if src.voice[u["id"]].get("started")}):
        evidence.append(ev(None, "voice", line))
    for u in other[:3]:
        evidence.append(ev(u["_t"], "voice", src.voice[u["id"]].get("fallback_line") or src.voice[u["id"]].get("started")))
    metrics = {"utterances": len(utter), "k07": len(k07), "not_k07": len(other), "engine_unknown": len(utter) - len(known),
               "k07_speech_s": round(speech_s, 1)}
    notes = [f"{len(utter) - len(known)} utterance(s) with an unknown engine (not in voice.log, or before its first "
             "start line)"] if len(known) < len(utter) else []
    if other:
        return result("voice_k07", title, FAIL, f"{len(other)} utterance(s) not on chatterbox + k07 (fallback or other "
                      "engine)", evidence=evidence, highlights=speech_highlights(other), metrics=metrics, thresholds=th,
                      notes=notes)
    if len(known) < len(utter):                          # some voice could have been a fallback nobody can see
        return result("voice_k07", title, MISSING, f"the engine of {len(utter) - len(known)} of {len(utter)} "
                      "utterance(s) is unknown", evidence=evidence, highlights=speech_highlights(utter),
                      metrics=metrics, thresholds=th, notes=notes)
    if len(k07) < TH["utterances"] or speech_s < TH["speech_s"]:
        return result("voice_k07", title, FAIL, f"{len(k07)} K07 utterance(s), {speech_s:.0f} s of speech",
                      evidence=evidence, highlights=speech_highlights(k07), metrics=metrics, thresholds=th, notes=notes)
    return result("voice_k07", title, PASS, f"{len(k07)} K07 utterances, {speech_s:.0f} s (chatterbox, k07 prompt, "
                  "no fallback)", evidence=evidence, highlights=speech_highlights(k07), metrics=metrics, thresholds=th,
                  notes=notes)


def eval_voice_recorded(src):
    title = "Voice in the recording"
    th = {"each_utterance": "director on air with voice=true"}
    utter = utterances(src)
    if not utter:
        return no_speech(src, "voice_recorded", title, th)
    if src.events_gap():
        return result("voice_recorded", title, MISSING, f"{src.events_gap()}: the director's runs cannot be replayed",
                      thresholds=th)
    air = src.air()
    voiced = union([(s["start"], s["end"]) for s in air if s.get("voice")])   # across layout switches
    lost = [u for u in utter if not any(a <= u["_t"] and u_end(u) <= b + 1 for a, b in voiced)]
    evidence = [ev(s["start"], "director", f"on air run={s['run']} voice={s.get('voice')} from {iso(s['start'])} to "
                   f"{iso(s['end'])}") for s in air if clip(s["start"], s["end"], src.since, src.until) > 0]
    evidence += [ev(u["_t"], "voice", u) for u in (lost or utter)[:6]]
    metrics = {"utterances": len(utter), "not_recorded_with_voice": len(lost)}
    if lost:
        return result("voice_recorded", title, FAIL, f"{len(lost)} utterance(s) while the director was not recording "
                      "with voice", evidence=evidence, highlights=speech_highlights(lost), metrics=metrics, thresholds=th)
    return result("voice_recorded", title, PASS, f"all {len(utter)} utterances recorded with voice", evidence=evidence,
                  highlights=speech_highlights(utter), metrics=metrics, thresholds=th)


def eval_head_motion(src):
    title = "Head motion with the voice"
    th = {"head_range_deg": TH["head_range_deg"], "talking_state": "a STATE -> talking line during an utterance",
          "pose": "SUB01_STREAMER_VISUAL_POSE headPitch/headYaw samples during speech"}
    utter = utterances(src)
    if not utter:
        return no_speech(src, "head_motion", title, th)
    if not src.game["exists"]:
        return result("head_motion", title, MISSING, "no game log", thresholds=th)
    slack = TH["talk_slack_s"]
    talking = [s for s in src.game["state"] if s.get("to") == "talking"
               and any(u["_t"] - slack <= s["t"] <= u_end(u) + slack for u in utter)]
    pose = [p for p in src.game["pose"] if any(u["_t"] - slack <= p["t"] <= u_end(u) + slack for u in utter)]
    axes = {k: [p[k] for p in pose if isinstance(p.get(k), (int, float)) and math.isfinite(p[k])]
            for k in ("headPitch", "headYaw")}                       # each axis on its own usable samples
    ranges = {k: round(max(v) - min(v), 2) for k, v in axes.items() if len(v) >= 2}
    moved = any(v >= TH["head_range_deg"] for v in ranges.values())
    evidence = [ev(s["t"], "game", s["line"]) for s in talking[:5]] + [ev(p["t"], "game", p["line"]) for p in pose[:6]]
    metrics = {"talking_lines": len(talking), "pose_samples_in_speech": len(pose), "range_deg": ranges}
    highlights = speech_highlights(utter)
    notes = ["POSE is logged every 10 s: this shows the head moved while he spoke, not that the voice drove it; "
             "check the highlights"]
    if not ranges:
        return result("head_motion", title, MISSING, f"{len(pose)} POSE sample(s) during speech: too few usable head "
                      "pitch/yaw values to measure", evidence=evidence, highlights=highlights, metrics=metrics,
                      thresholds=th, notes=notes)
    if not talking or not moved:
        why = "; ".join(x for x in ("no talking state during an utterance" if not talking else "",
                                    f"head range {ranges} below {TH['head_range_deg']} deg" if not moved else "") if x)
        return result("head_motion", title, FAIL, why, evidence=evidence, highlights=highlights, metrics=metrics,
                      thresholds=th, notes=notes)
    return result("head_motion", title, PASS, f"head pitch/yaw range {ranges} deg over {len(pose)} samples during "
                  f"speech; {len(talking)} talking state line(s)", evidence=evidence, highlights=highlights,
                  metrics=metrics, thresholds=th, notes=notes)


def eval_mouth_motion(src):
    title = "Mouth motion with the voice"
    th = {"rig": "a jaw bone or morph targets driven by mouth.json", "ready": "MOUTH_READY for the live game run",
          "rejected": "no MOUTH_FILE_REJECTED in the window"}
    utter = utterances(src)
    if not src.game["exists"]:
        return result("mouth_motion", title, MISSING, "no game log", thresholds=th)

    def ready_at(t):                                     # MOUTH_READY of the game run live at t (started before t)
        start = max([i["t"] for i in src.game["init"] if i["t"] <= t] or [float("-inf")])
        lines = [m for m in src.game["mouth_ready"] if start <= m["t"] <= t]
        return lines[-1] if lines else None
    rejected = [m for m in src.game["mouth_rejected"] if src.since <= m["t"] <= src.until]
    rigs = [ready_at(u["_t"]) for u in utter] if utter else [ready_at(src.until)]
    seen = [m for m in rigs if m]
    evidence = [ev(m["t"], "game", m["line"]) for m in {id(m): m for m in seen}.values()] + \
        [ev(m["t"], "game", m["line"]) for m in rejected[:3]]
    metrics = {"rigs": sorted({m.get("rig") for m in seen}), "rejected": len(rejected), "utterances": len(utter),
               "utterances_without_ready": sum(1 for m in rigs if m is None) if utter else None}
    if rejected:
        return result("mouth_motion", title, FAIL, f"{len(rejected)} MOUTH_FILE_REJECTED line(s): the mouth stayed closed",
                      evidence=evidence, metrics=metrics, thresholds=th)
    if any(m.get("rig") == "head_only" for m in seen):
        return result("mouth_motion", title, FAIL, "not met: the rig has no jaw bone and no morph targets (rig=head_only),"
                      " so mouth.json drives head emphasis only; it needs a jaw/morph rig or the owner redefining it",
                      evidence=evidence, metrics=metrics, thresholds=th)
    if None in rigs:
        return result("mouth_motion", title, MISSING, "no MOUTH_READY line for the game run live at "
                      + ("the window end" if not utter else f"{sum(1 for m in rigs if m is None)} utterance(s)"),
                      evidence=evidence, metrics=metrics, thresholds=th)
    if not utter:
        return no_speech(src, "mouth_motion", title, th)
    return result("mouth_motion", title, PASS, f"rig {', '.join(metrics['rigs'])} reads mouth.json during {len(utter)} "
                  "utterances", evidence=evidence, highlights=speech_highlights(utter), metrics=metrics, thresholds=th,
                  notes=["the rig is wired; inspect the highlights for the visible mouth"])


def eval_pc_control(src):
    title = "Control of the PC (keyboard and mouse on the Vagon desktop)"
    th = {"keyboard": list(KEYBOARD), "mouse": list(MOUSE), "need": "ok and outcome.changed while connected, on air"}
    vagon = [r for runner in src.runners.values() if runner["vagon"] for r in runner["rows"]]
    if not any(runner["vagon"] for runner in src.runners.values()):
        return result("pc_control", title, MISSING, "no Vagon runner events.jsonl found", thresholds=th)
    connected, acts = False, []
    for r in sorted(vagon, key=lambda x: x["_t"]):
        if r["_t"] > src.until:
            break
        if r.get("kind") == "vagon":
            state = r.get("state")
            connected = True if state == "connected" else False if state in VAGON_DOWN else connected
        elif r.get("kind") == "act" and r["_t"] >= src.since:
            acts.append((r, connected))
    if not acts:
        return result("pc_control", title, FAIL, "no input to the Vagon desktop in the window; " + src.vagon_context(),
                      thresholds=th)
    good, evidence, highlights = {"keyboard": [], "mouse": []}, [], []
    for r, conn in acts:
        name = (r.get("action") or {}).get("action")
        evidence.append(ev(r["_t"], "runner", r))
        if r.get("ok") and (r.get("outcome") or {}).get("changed") and conn and src.recorded(r["_t"]):
            group = "keyboard" if name in KEYBOARD else "mouse" if name in MOUSE else None
            if group:
                good[group].append(r)
    for group, rows in good.items():
        if rows:
            highlights.append(mark(rows[0]["_t"], f"{group} input changed the Vagon desktop ({rows[0]['action'].get('action')})"))
    confirm = [r for r in agent_window(src) if r.get("kind") == "outcome" and r.get("pixel_diff") is not None]
    evidence += [ev(r["_t"], "agent", r) for r in confirm[:5]]
    metrics = {"acts": len(acts), "while_connected": sum(1 for _, c in acts if c), "keyboard_ok": len(good["keyboard"]),
               "mouse_ok": len(good["mouse"]), "agent_pixel_checks": len(confirm)}
    if good["keyboard"] and good["mouse"]:
        return result("pc_control", title, PASS, f"{len(good['keyboard'])} keyboard and {len(good['mouse'])} mouse "
                      "inputs changed the connected Vagon desktop", evidence=evidence, highlights=highlights,
                      metrics=metrics, thresholds=th)
    missing = [g for g in ("keyboard", "mouse") if not good[g]]
    return result("pc_control", title, FAIL, f"no successful recorded {' or '.join(missing)} input while connected "
                  f"({metrics['while_connected']}/{len(acts)} inputs while connected)", evidence=evidence,
                  highlights=highlights, metrics=metrics, thresholds=th)


def source_windows(cid, title, rows, field, src, label, off=()):
    """Periodic measured windows (PERF 10 s, CAM2 30 s, monitor): every complete window >= source_min_fps, no logging
    gap (consecutive lines, and the window's ends, at most gap_factor periods apart). -> result or None (no rows)."""
    th = {"every_window_min": TH["source_min_fps"], "gap": f"> {TH['gap_factor']} x the window period"}
    if not rows:
        return None
    period = median([float(r.get("window_s") or 10.0) for r in rows])
    values = [float(r.get(field) or 0.0) for r in rows]
    times = [src.since] + [r["t"] for r in rows] + [src.until]
    gaps = [(a, b) for a, b in zip(times, times[1:]) if b - a > TH["gap_factor"] * period]
    below = [r for r in rows if float(r.get(field) or 0.0) < TH["source_min_fps"]]
    metrics = {"windows": len(rows), "period_s": period, "min": round(min(values), 2), "p05": round(percentile(values, 5), 2),
               "median": round(median(values), 2), "max": round(max(values), 2),
               "below": len(below), "gaps": [{"from": iso(a), "to": iso(b), "s": round(b - a, 1)} for a, b in gaps]}
    worst = min(rows, key=lambda r: float(r.get(field) or 0.0))
    evidence = [ev(r["t"], "game", r["line"]) for r in sorted(below, key=lambda r: float(r.get(field) or 0))[:6]]
    evidence += [ev(r["t"], "game", r["line"]) for r in rows[:: max(1, len(rows) // 6)][:6]]
    highlights = [mark(worst["t"], f"{label} lowest window {float(worst.get(field) or 0):.1f} fps")]
    stats = f"min {metrics['min']}, p05 {metrics['p05']}, median {metrics['median']} fps over {len(rows)} windows"
    problems = ([f"{len(below)} window(s) below {TH['source_min_fps']}"] if below else []) + list(off)
    if problems:
        return result(cid, title, FAIL, f"{'; '.join(problems)} ({stats})", evidence=evidence, highlights=highlights,
                      metrics=metrics, thresholds=th)
    if gaps:
        return result(cid, title, MISSING, f"logging gap(s) of {', '.join(str(round(b - a)) for a, b in gaps[:3])} s: "
                      f"unmeasured time is not a pass ({stats})", evidence=evidence, highlights=highlights,
                      metrics=metrics, thresholds=th)
    return result(cid, title, PASS, stats, evidence=evidence, highlights=highlights, metrics=metrics, thresholds=th)


def eval_fps_game(src):
    title = "60 fps: game render (PERF)"
    res = source_windows("fps_game", title, src.game["perf"], "fps", src, "PERF")
    if res:
        return res
    why = "no game log" if not src.game["exists"] else "no SUB01_STREAMER_VISUAL_PERF line in the window"
    return result("fps_game", title, MISSING, why, thresholds={"every_window_min": TH["source_min_fps"]})


def eval_fps_cam2(src):
    title = "60 fps: cam2 delivered (game CAM2 status)"
    rows = src.game["cam2"]
    off = [r for r in rows if r.get("on") != 1 or r.get("reader") != 1]
    res = source_windows("fps_cam2", title, rows, "fps", src, "CAM2",
                         [f"{len(off)} window(s) with cam2 off or no reader"] if off else [])
    if res:
        res["metrics"]["capture_fps_median"] = round(median([float(r.get("capture_fps") or 0) for r in rows]), 2)
        res["metrics"]["target_fps"] = rows[-1].get("target_fps")
        return res
    why = "no game log" if not src.game["exists"] else "no SUB01_STREAMER_VISUAL_CAM2 line in the window"
    return result("fps_cam2", title, MISSING, why, thresholds={"every_window_min": TH["source_min_fps"]})


def eval_fps_monitor(src):
    title = "60 fps: in-game monitor feed"
    rows = [dict(r, fps=r.get("fps_applied", r.get("fps"))) for r in src.game["monitor"]]
    res = source_windows("fps_monitor_feed", title, rows, "fps", src, "monitor feed")
    if res:
        return res
    why = ("no source logs the in-game monitor feed's fps: the game has no SUB01_STREAMER_VISUAL_MONITOR* line (wanted: "
           "fps_in / fps_applied per 10 s window from the native polling path) and the monitor feed sidecar reports "
           "its input fps only on a live health endpoint, which neither covers a past window nor proves presentation")
    return result("fps_monitor_feed", title, MISSING, why, thresholds={"every_window_min": TH["source_min_fps"]})


def eval_fps_director(src):
    title = "60 fps: director per segment (segment_fps)"
    th = {"fps": TH["output_fps"], "fps_media": TH["output_fps"], "dup_drop": 0, "speed_restart": "none",
          "partial_rows": f">= {TH['partial_min_s']} s, judged on fps_media (wall time includes the run's start/stop)"}
    rows = [r for r in src.director if r.get("kind") == "segment_fps"
            and clip(r["_t"] - float(r.get("wall_s") or 0), r["_t"], src.since, src.until) > 0
            and (not r.get("partial") or float(r.get("wall_s") or 0) >= TH["partial_min_s"])]
    slow = [r for r in src.in_window(src.director) if r.get("kind") == "speed_restart"]
    if not rows and not slow:
        return result("fps_director", title, MISSING, "no segment_fps row overlaps the window (a row is written when "
                      "its segment closes, every 10 minutes)", thresholds=th)
    bad, evidence, highlights = [], [], []
    for r in rows:
        checks = [(f"fps_media {r.get('fps_media')}", float(r.get("fps_media") or 0) < TH["output_fps"]),
                  (f"dup {r.get('dup_frames')} drop {r.get('drop_frames')}", bool(r.get("dup_frames") or r.get("drop_frames")))]
        if not r.get("partial"):
            checks.append((f"fps {r.get('fps')}", float(r.get("fps") or 0) < TH["output_fps"]))
        problems = [p for p, cond in checks if cond]
        evidence.append(ev(r["_t"], "director", r))
        if problems:
            bad.append(f"{r.get('segment')}: {', '.join(problems)}")
            highlights.append(mark(r["_t"] - float(r.get("wall_s") or 0), f"segment {r.get('segment')} below 60"))
    for r in slow:
        evidence.append(ev(r["_t"], "director", r))
        bad.append(f"speed_restart at {hms(r['_t'])}Z (speed {r.get('speed')})")
        highlights.append(mark(r["_t"], f"director speed_restart {r.get('speed')}x"))
    covered = sum(clip(a, b, src.since, src.until) for a, b in
                  union([(r["_t"] - float(r.get("wall_s") or 0), r["_t"]) for r in rows]))
    metrics = {"rows": len(rows), "fps": [r.get("fps") for r in rows], "fps_media": [r.get("fps_media") for r in rows],
               "speed_restarts": len(slow), "coverage": round(covered / (src.until - src.since), 3)}
    if bad:
        return result("fps_director", title, FAIL, "; ".join(bad[:4]), evidence=evidence, highlights=highlights,
                      metrics=metrics, thresholds=th)
    return result("fps_director", title, PASS, f"{len(rows)} row(s) at {', '.join(str(r.get('fps_media')) for r in rows)} "
                  f"fps (media), dup/drop 0, covering {metrics['coverage']:.0%} of the window (the open segment's row "
                  "comes when it closes; fps_recordings measures it)", evidence=evidence, highlights=highlights,
                  metrics=metrics, thresholds=th)


def eval_fps_recordings(src):
    title = "60 fps: recordings (ffprobe packets / video duration)"
    th = {"fps": TH["output_fps"], "coverage": f"the whole window, gaps <= {TH['recording_gap_s']} s",
          "r_frame_rate": "reported (metadata, not a measurement)"}
    segs = src.window_recordings()
    if not src.probe_enabled:
        return result("fps_recordings", title, MISSING, "ffprobe disabled (--no-probe)", thresholds=th)
    if not segs:
        return absent(src, "fps_recordings", title, "recording segment", th)
    bad, unassessable, evidence, per = [], [], [], []   # measured below 60 / not measurable (timeout, not probed)
    for seg in segs:
        res = src.probes.get(seg["path"]) or {"error": "not probed"}
        evidence.append(ev(seg["end"], "ffprobe", f"{seg['name']} {json.dumps(res)}"))
        if res.get("error"):
            unassessable.append(f"{seg['name']}: {res['error']}")
            continue
        per.append({"segment": seg["name"], "start_utc": iso(seg["start"]), "end_utc": iso(seg["end"]), **res})
        if (res.get("fps") or 0) < TH["output_fps"]:
            bad.append(f"{seg['name']}: {res.get('fps')} fps ({res.get('packets')} packets / {res.get('duration')} s)")
    # the recording timeline from every segment (an unprobed one by its name and mtime); a gap fails only between
    # measured edges, one next to an unprobed segment cannot be placed exactly
    spans = []                                           # [start, end, start measured, end measured]
    for a, b, ok in sorted((max(s["start"], src.since), min(s["end"], src.until), s["probed"]) for s in segs
                           if s["end"] > src.since and s["start"] < src.until):
        if spans and a <= spans[-1][1]:
            if b > spans[-1][1]:
                spans[-1][1], spans[-1][3] = b, ok
        else:
            spans.append([a, b, ok, ok])
    edges = [(src.since, True)] + [x for a, b, oka, okb in spans for x in ((a, oka), (b, okb))] + [(src.until, True)]
    gaps = [(a, b, oka and okb) for (a, oka), (b, okb) in zip(edges[::2], edges[1::2]) if b - a > TH["recording_gap_s"]]
    sure = [(a, b) for a, b, ok in gaps if ok]
    if sure:
        bad.append("not recording " + ", ".join(f"{hms(a)}-{hms(b)}Z ({b - a:.0f} s)" for a, b in sure[:3]))
    unassessable += [f"possible gap {hms(a)}-{hms(b)}Z next to an unprobed segment" for a, b, ok in gaps if not ok]
    metrics = {"segments": per, "gaps": [{"from": iso(a), "to": iso(b), "s": round(b - a, 1), "certain": ok}
                                         for a, b, ok in gaps],
               "coverage": round(sum(s[1] - s[0] for s in spans) / (src.until - src.since), 3),
               "unassessable": unassessable}
    highlights = [mark(max(s["start"], src.since), f"segment {s['name']}") for s in segs]
    notes = [f"{p['segment']} was still being written: measured over the fragments written when it was probed"
             for p in per if p.get("growing")]
    if bad:
        return result("fps_recordings", title, FAIL, "; ".join(bad[:4]), evidence=evidence, highlights=highlights,
                      metrics=metrics, thresholds=th, notes=notes)
    if unassessable:
        return result("fps_recordings", title, MISSING, "cannot measure: " + "; ".join(unassessable[:3]),
                      evidence=evidence, highlights=highlights, metrics=metrics, thresholds=th, notes=notes)
    return result("fps_recordings", title, PASS, f"{len(per)} segment(s) at " + ", ".join(str(p["fps"]) for p in per)
                  + f" fps, covering {metrics['coverage']:.0%}", evidence=evidence, highlights=highlights,
                  metrics=metrics, thresholds=th, notes=notes)


def eval_fps_hls(src):
    title = "60 fps: HLS output (spot check at the window end)"
    th = {"fps": TH["output_fps"], "scope": "the segments still listed (~24 s): not a 30-minute proof"}
    if src.hls is None:
        return result("fps_hls_spot", title, MISSING, "no hls/live.m3u8", thresholds=th)
    if not src.probe_enabled:
        return result("fps_hls_spot", title, MISSING, "ffprobe disabled (--no-probe)", thresholds=th)
    segs = src.window_hls()
    if not segs:
        newest = max([s["start"] for s in src.hls if s["start"]] or [0]) or None
        return result("fps_hls_spot", title, MISSING, f"no HLS segment of the window is left (the playlist keeps "
                      f"~{4 * len(src.hls)} s; newest {iso(newest)}): run the check within ~20 s of the window end",
                      thresholds=th)
    bad, unassessable, evidence, per, rotated = [], [], [], [], 0
    for seg in segs:
        res = src.probes.get(seg["path"])
        name = Path(seg["path"]).name
        if res is None:                                  # deleted by the muxer before it could be probed
            rotated += 1
            continue
        evidence.append(ev(seg["start"], "ffprobe", f"{name} EXTINF {seg['extinf']} {json.dumps(res)}"))
        if res.get("error"):                             # not measurable: not a measured failure
            unassessable.append(f"{name}: {res['error']}")
            continue
        fps = round(res["packets"] / seg["extinf"], 2) if seg["extinf"] else res.get("fps")
        per.append({"segment": name, "packets": res["packets"], "extinf": seg["extinf"], "fps": fps})
        if (fps or 0) < TH["output_fps"]:
            bad.append(f"{name}: {fps} fps ({res['packets']} packets / {seg['extinf']} s)")
    metrics = {"segments": per, "rotated_before_probe": rotated, "unassessable": unassessable}
    highlights = [mark(segs[0]["start"], "HLS segments measured")]
    if bad:
        return result("fps_hls_spot", title, FAIL, "; ".join(bad[:4]), evidence=evidence, highlights=highlights,
                      metrics=metrics, thresholds=th)
    if unassessable or not per:
        why = ("cannot measure: " + "; ".join(unassessable[:3])) if unassessable else \
            "every HLS segment of the window was rotated away before it could be probed"
        return result("fps_hls_spot", title, MISSING, why, evidence=evidence, metrics=metrics, thresholds=th)
    return result("fps_hls_spot", title, PASS, f"{len(per)} segment(s) at " + ", ".join(str(p["fps"]) for p in per)
                  + " fps", evidence=evidence, highlights=highlights, metrics=metrics, thresholds=th)


CRITERIA = (eval_activity, eval_chat_executed, eval_chat_refused, eval_errors, eval_two_cameras, eval_voice_k07,
            eval_voice_recorded, eval_head_motion, eval_mouth_motion, eval_pc_control, eval_fps_game, eval_fps_cam2,
            eval_fps_monitor, eval_fps_director, eval_fps_recordings, eval_fps_hls)


# ------------------------------------------------------------------ report

def evaluate(src):
    results = [fn(src) for fn in CRITERIA]
    for res in results:
        for h in res["highlights"]:
            where = src.locate(h["t"])
            if where:
                h.update(where)
    counts = {s: sum(1 for r in results if r["status"] == s) for s in (PASS, FAIL, MISSING)}
    verdict = PASS if counts[PASS] == len(results) else FAIL if counts[FAIL] else INCONCLUSIVE
    reel = streamer_highlights.windows(src.dir, src.since, src.until)
    stamp = datetime.fromtimestamp(src.until, timezone.utc).strftime("%Y%m%d-%H%M")
    return {
        "schema": SCHEMA, "generated_utc": iso(time.time()),
        "window": {"since": round(src.since, 3), "until": round(src.until, 3), "since_utc": iso(src.since),
                   "until_utc": iso(src.until), "minutes": round((src.until - src.since) / 60.0, 1)},
        "verdict": verdict, "counts": counts, "criteria": results,
        "context": {"stop_file": src.stop_file, "agent": src.agent_context(), "vagon": src.vagon_context(),
                    "events_coverage": src.events_gap() or "covers the window",
                    "recordings_in_window": [s["name"] for s in src.window_recordings()],
                    "clock": "every source is written on the pod's UTC clock; voice.log lines carry none (matched by "
                             "utterance id)"},
        "sources": {"read": src.read, "missing": src.missing},
        "highlights_reel": {"windows": [{"start_utc": iso(a), "end_utc": iso(b), "label": label} for a, b, label in reel],
                            "command": f"python3 scripts/streamer_highlights.py --streamer-dir {src.dir} --since "
                                       f"{src.since:.0f} --until {src.until:.0f} --max-seconds 300 --out "
                                       f"highlights-{stamp}.mp4"},
    }


def render_markdown(report):
    w = report["window"]
    out = [f"# SUB-01 acceptance report: {w['since_utc']} to {w['until_utc']} ({w['minutes']} min)", "",
           f"Verdict: **{STATUS_TEXT[report['verdict']]}** ({report['counts'][PASS]} pass, {report['counts'][FAIL]} fail, "
           f"{report['counts'][MISSING]} missing evidence). Generated {report['generated_utc']} by "
           "`scripts/streamer_acceptance.py` (read-only; fps from measured values only). FAIL: the sources cover the "
           "window and the content is absent or below the bar; MISSING EVIDENCE: the window cannot be assessed.", "",
           "| Criterion | Status | Why |", "|---|---|---|"]
    for r in report["criteria"]:
        out.append(f"| {r['title']} (`{r['id']}`) | {STATUS_TEXT[r['status']]} | {r['why'].replace('|', '/')} |")
    ctx = report["context"]
    out += ["", "## Context", f"- Agent: {ctx['agent'] or 'rows in the window'}", f"- {ctx['vagon']}",
            f"- events.jsonl: {ctx['events_coverage']}; clock: {ctx['clock']}",
            f"- Recording segments in the window: {', '.join(ctx['recordings_in_window']) or 'none'}",
            "- Sources read: " + ", ".join(f"{k} ({v['rows']}" + (f", {v['bad_lines']} bad lines" if v.get("bad_lines")
                                                                  else "") + ")" for k, v in report["sources"]["read"].items()),
            "- Sources missing: " + (", ".join(f"{k} ({v})" for k, v in report["sources"]["missing"].items()) or "none")]
    for r in report["criteria"]:
        out += ["", f"## {r['title']}: {STATUS_TEXT[r['status']]}", "", f"Why: {r['why']}", "",
                "Thresholds: " + ", ".join(f"{k} {json.dumps(v)}" for k, v in r["thresholds"].items())]
        if r["metrics"]:
            out.append("Metrics: " + mask(json.dumps(r["metrics"]), 900))
        for note in r["notes"]:
            out.append(f"Note: {note}")
        if r["highlights"]:
            out += ["", "Highlights:"]
            for h in r["highlights"][:12]:
                where = f" ({h['segment']} at {h['offset']}{', approx.' if h.get('approx') else ''})" if h.get("segment") else ""
                out.append(f"- {h['utc']} {h['label']}{where}")
        if r["evidence"]:
            out += ["", f"Evidence ({len(r['evidence'])} of {r['evidence_total']}):", "```"]
            out += [f"{e['utc'] or '(no time)'} {e['source']}: {e['line']}" for e in r["evidence"]]
            out.append("```")
    reel = report["highlights_reel"]
    out += ["", "## Highlights reel", f"{len(reel['windows'])} speech/induced-fault window(s) in the window. Cut it with:",
            "```", reel["command"], "```", ""]
    return "\n".join(out)


def parse_window(args, streamer_dir, now=None):
    now = time.time() if now is None else now
    if args.last_rehearsal:
        rows = timed(read_jsonl([Path(streamer_dir) / "rehearsal.jsonl"]), "t")
        starts = [r for r in rows if r.get("kind") == "start"]
        if not starts:
            raise SystemExit("no rehearsal start row in rehearsal.jsonl")
        since = starts[-1]["_t"]
        ends = [r for r in rows if r.get("kind") == "end" and r["_t"] >= since]
        return since, ends[0]["_t"] if ends else now
    until = to_unix(args.until) if args.until else now
    since = to_unix(args.since) if args.since else (until - args.minutes * 60.0 if until is not None else None)
    if until is None or since is None or since >= until:
        raise SystemExit("bad window: --since must be before --until (unix seconds or ISO UTC)")
    return since, until


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--streamer-dir", default=DEFAULT_DIR)
    p.add_argument("--game-log", default=DEFAULT_GAME_LOG)
    p.add_argument("--desktop-data-dir", action="append", default=None,
                   help="a desktop runner's data dir (repeatable; default <dir>/desktop-vagon and <dir>/desktop)")
    p.add_argument("--minutes", type=float, default=30.0)
    p.add_argument("--since", default=None, help="unix seconds or ISO UTC")
    p.add_argument("--until", default=None, help="unix seconds or ISO UTC (default now)")
    p.add_argument("--last-rehearsal", action="store_true", help="the window of the last run in rehearsal.jsonl")
    p.add_argument("--out-dir", default=".")
    p.add_argument("--name", default=None, help="file name stem (default acceptance-<until UTC>)")
    p.add_argument("--ffprobe", default="ffprobe")
    p.add_argument("--probe-timeout", type=float, default=180.0)
    p.add_argument("--no-probe", action="store_true", help="skip ffprobe (recordings and HLS become missing evidence)")
    args = p.parse_args(argv)
    since, until = parse_window(args, args.streamer_dir)
    src = Sources(args.streamer_dir, args.game_log, since, until, args.desktop_data_dir, args.ffprobe,
                  not args.no_probe, args.probe_timeout)
    report = evaluate(src)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.name or f"acceptance-{datetime.fromtimestamp(until, timezone.utc):%Y%m%d-%H%M%S}"
    (out_dir / f"{stem}.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    (out_dir / f"{stem}.md").write_text(render_markdown(report))
    print(f"acceptance {report['window']['since_utc']} .. {report['window']['until_utc']}: "
          f"{STATUS_TEXT[report['verdict']]} {json.dumps(report['counts'])}")
    for r in report["criteria"]:
        print(f"  {STATUS_TEXT[r['status']]:<16} {r['id']:<17} {r['why']}")
    print(f"  report: {out_dir / (stem + '.md')}  json: {out_dir / (stem + '.json')}")
    return 0 if report["verdict"] == PASS else 1


if __name__ == "__main__":
    sys.exit(main())
