"""scripts/streamer_acceptance.py against fixtures cut from the real formats: `today` holds excerpts of the pod's
sources of 2026-10-24 (agent held, Vagon PC off, game at 48 fps, cam2 at 40), `pass` a 30-minute scenario written in
the same line formats (tests/fixtures/streamer_acceptance/). Media files are placeholders with a fake probe, plus two
tests of the real ffprobe on tiny clips when ffmpeg is installed."""
import importlib.util
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("streamer_acceptance", ROOT / "scripts/streamer_acceptance.py")
sa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sa)
FIX = ROOT / "tests/fixtures/streamer_acceptance"
ALL = ("activity_change", "chat_executed", "chat_refused", "error_recovered", "two_cameras", "voice_k07",
       "voice_recorded", "head_motion", "mouth_motion", "pc_control", "fps_game", "fps_cam2", "fps_monitor_feed",
       "fps_director", "fps_recordings", "fps_hls_spot")


def utc(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


def by_id(report):
    return {c["id"]: c for c in report["criteria"]}


def copy_fixture(name, tmp_path):
    dst = tmp_path / name
    shutil.copytree(FIX / name, dst)
    return dst


def append(path, *rows):
    with open(path, "a") as handle:
        for row in rows:
            handle.write((row if isinstance(row, str) else json.dumps(row)) + "\n")


def agent_row(when, kind, **fields):
    return {"t": utc(when), "utc": when.replace("Z", ".000Z"), "kind": kind, **fields}


def director_row(when, kind, **fields):
    return {"t": when, "source": "director", "kind": kind, **fields}


def rewrite_jsonl(path, keep):
    rows = [json.loads(x) for x in Path(path).read_text().splitlines()]
    Path(path).write_text("".join(json.dumps(r) + "\n" for r in rows if keep(r)))


# ------------------------------------------------------------------ helpers

def test_mask_hides_tokens_keeps_log_tags_and_keys():
    line = ('{"token": "abc123", "url": "https://x.example/cb?code=s3cret&state=1", "key": "Escape", '
            'auth=Bearer abc.def.ghi sk-proj-0123456789abcdef '
            'SUB01_STREAMER_VISUAL_MOUTH_READY a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8')
    out = sa.mask(line)
    assert "abc123" not in out and "s3cret" not in out and "abc.def.ghi" not in out and "0123456789abcdef" not in out
    assert "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8" not in out
    assert "SUB01_STREAMER_VISUAL_MOUTH_READY" in out and '"key": "Escape"' in out
    assert "https://x.example/cb?[query masked]" in out
    assert len(sa.mask("x " * 500, 50)) == 50 and sa.mask("x" * 1000) == "[MASKED]"


def test_mask_review_cases_and_scrubbed_rows():
    out = sa.mask("client_secret=abc1 refresh_token=abc2 X-Admin-Token: abc3 Authorization: Basic dXNlcjpwYXNz "
                  "https://user:pa55@host.example/x?a=b ABCDEFGHIJKLMNOPQRSTUVWXYZ012345678 "
                  "SUB01_STREAMER_VISUAL_MOUTH_FILE_REJECTED")
    for leak in ("abc1", "abc2", "abc3", "dXNlcjpwYXNz", "pa55", "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345678"):
        assert leak not in out, leak
    assert "SUB01_STREAMER_VISUAL_MOUTH_FILE_REJECTED" in out and "https://[MASKED]@host.example/x?[query masked]" in out
    row = {"kind": "x", "_t": 1.0, "nested": {"api_key": "k1", "list": [{"session_token": "k2"}]}, "key": "Escape",
           "credential": True, "text": "fine"}
    line = sa.ev(1.0, "agent", row)["line"]
    assert "k1" not in line and "k2" not in line and '"key": "Escape"' in line and '"credential": true' in line
    assert '"_t"' not in line


@pytest.mark.parametrize("value,expected", [
    (1792797118.441, 1792797118.441),
    ("2026-10-24T15:35:50Z", utc("2026-10-24T15:35:50Z")),
    ("2026-10-23T23:11:58.441Z", utc("2026-10-23T23:11:58.441Z")),
    ("2026-10-23T22:45:58.468+00:00", utc("2026-10-23T22:45:58.468Z")),
    ("2026-10-24T15:42:35.013+0000", utc("2026-10-24T15:42:35.013Z")),
    ("2026-10-24T15:42:35", utc("2026-10-24T15:42:35Z")),
    ("1792797118", 1792797118.0),
    ("not a time", None), (None, None), (True, None), (float("nan"), None), ("inf", None), ("NaN", None)])
def test_to_unix_reads_every_time_format_of_the_sources(value, expected):
    got = sa.to_unix(value)
    assert got == pytest.approx(expected) if expected is not None else got is None


def test_rows_are_told_apart_by_shape():
    assert sa.component({"t": 1.0, "utc": "x", "kind": "action", "source": "model"}) == "agent"
    assert sa.component({"t": 1.0, "utc": "x", "kind": "inject", "source": "http"}) == "agent"
    assert sa.component({"t": "2026-10-24T14:05:45Z", "source": "director", "kind": "ffmpeg_started"}) == "director"
    assert sa.component({"t": "2026-10-24T14:05:45Z", "source": "streamer_up", "kind": "service_up"}) == "supervisor"
    assert sa.component({"t": "2026-10-24T14:05:45Z", "kind": "act"}) == "other"


def test_percentiles_median_union():
    values = [48.8] + [60.0] * 19
    assert sa.percentile(values, 5) == 48.8 and sa.median(values) == 60.0 and sa.median([1.0, 3.0]) == 2.0
    assert sa.union([(5, 9), (0, 2), (1, 3), (9, 10)]) == [(0, 3), (5, 10)]


def test_voice_log_replay_follows_restarts_and_the_sticky_fallback(tmp_path):
    log = tmp_path / "voice.log"
    log.write_text(
        "voice: spoken id=20261025T095900-0000 tag='comment' 3.00s cut=False text='before any start line'\n"
        "voice: listening on http://127.0.0.1:8835 engine=chatterbox voice=sub01-voice-reference-k07.wav fallback=kokoro\n"
        "voice: spoken id=20261025T100000-0001 tag='comment' 3.00s cut=False text='a'\n"
        "voice: chatterbox unavailable (OutOfMemoryError: CUDA out of memory); falling back to kokoro\n"
        "Sampling: 5%|  | 1/20 [00:00<?]\rvoice: spoken id=20261025T100100-0002 tag='comment' 2.00s cut=False text='b'\n"
        "voice: listening on http://127.0.0.1:8835 engine=chatterbox voice=sub01-voice-reference-k07.wav fallback=kokoro\n"
        "voice: spoken id=20261025T100200-0003 tag='chat' 2.00s cut=True (stop requested) text='c'\n")
    out = sa.read_voice_log(log)
    assert out["20261025T095900-0000"]["known"] is False
    assert out["20261025T100000-0001"]["fallback"] is None and out["20261025T100000-0001"]["known"]
    assert out["20261025T100100-0002"]["fallback"] == "kokoro"
    assert out["20261025T100200-0003"]["fallback"] is None and out["20261025T100200-0003"]["engine"] == "chatterbox"
    assert sa.read_voice_log(tmp_path / "missing.log") is None


def test_game_log_parser_survives_binary_bytes_and_keeps_one_off_lines(tmp_path):
    src = (FIX / "today/game.log").read_bytes()
    log = tmp_path / "game.log"
    log.write_bytes(b"Using musl\n\x00\x00binary junk\x00\n" + src + b"[2026.10.24-15.40.00:000][  1]garbage\n")
    since, until = utc("2026-10-24T15:30:00Z"), utc("2026-10-24T15:35:00Z")
    g = sa.read_game_log(log, since, until)
    assert len(g["perf"]) == 30 and 44 < g["perf"][0]["fps"] < 50 and len(g["pose"]) == 30
    assert len(g["cam2"]) == 10 and all(c["on"] == 1 and c["reader"] == 1 for c in g["cam2"])
    assert g["mouth_ready"][-1]["rig"] == "head_only" and g["init"]       # from 14:04, before the window
    assert g["state"] == []                                               # STATE lines at 14:08 are outside it
    assert not sa.read_game_log(tmp_path / "none.log", since, until)["exists"]


def test_hls_playlist_parser(tmp_path):
    (tmp_path / "live.m3u8").write_text((FIX / "today/hls/live.m3u8").read_text())
    segs = sa.read_hls(tmp_path)
    assert len(segs) == 6 and all(s["extinf"] == 4.0 for s in segs)
    assert segs[0]["start"] == pytest.approx(utc("2026-10-24T15:42:35.013Z"))
    assert sa.read_hls(tmp_path / "nothing") is None
    (tmp_path / "live.m3u8").write_text("#EXTM3U\n#EXTINF:4.0,\n#EXT-X-PROGRAM-DATE-TIME:2026-10-25T10:00:00.000+0000\n"
                                        "a.ts\n#EXTINF:4.0,\nb.ts\n#EXTINF:2.0,\nc.ts\n#EXT-X-DISCONTINUITY\n"
                                        "#EXTINF:4.0,\nd.ts\n")
    assert [s["start"] for s in sa.read_hls(tmp_path)] == [utc("2026-10-25T10:00:00Z"), utc("2026-10-25T10:00:04Z"),
                                                            utc("2026-10-25T10:00:08Z"), None]


def test_ffprobe_failure_exit_and_a_growing_file(tmp_path):
    seg = tmp_path / "s.mp4"
    seg.write_bytes(b"x")
    body = '{"streams": [{"nb_read_packets": "600", "r_frame_rate": "60/1", "duration": "10.0"}]}'
    bad = tmp_path / "bad-ffprobe"
    bad.write_text(f"#!/bin/sh\necho '{body}'\necho 'moov atom not found' >&2\nexit 1\n")
    grow = tmp_path / "grow-ffprobe"
    grow.write_text(f"#!/bin/sh\nfor last; do :; done\nprintf y >> \"$last\"\necho '{body}'\n")
    for script in (bad, grow):
        script.chmod(0o755)
    res = sa.ffprobe_count(seg, ffprobe=str(bad))
    assert res["error"].startswith("ffprobe exited 1") and "moov atom" in res["error"]
    res = sa.ffprobe_count(seg, ffprobe=str(grow))
    assert res["fps"] == 60.0 and res["growing"] is True


# ------------------------------------------------------------------ today's real excerpts

def run_today(tmp_path, since, until, name="today"):
    fx = copy_fixture("today", tmp_path)
    out = tmp_path / "out"
    code = sa.main(["--streamer-dir", str(fx), "--game-log", str(fx / "game.log"), "--since", since, "--until", until,
                    "--out-dir", str(out), "--no-probe", "--name", name])
    return code, json.loads((out / f"{name}.json").read_text()), (out / f"{name}.md").read_text()


def test_today_says_why_each_criterion_fails_or_lacks_evidence(tmp_path):
    code, report, md = run_today(tmp_path, "2026-10-24T15:30:00Z", "2026-10-24T15:35:00Z")
    c = by_id(report)
    assert code == 1 and report["schema"] == sa.SCHEMA and report["verdict"] == sa.FAIL
    assert tuple(c) == ALL
    for cid in ("activity_change", "chat_executed", "chat_refused", "error_recovered", "voice_k07", "voice_recorded",
                "head_motion"):                          # the logs cover the window: the content is absent -> fail
        assert c[cid]["status"] == sa.FAIL, cid
        assert "STOP" in c[cid]["why"] and "2026-10-24T10:40:01Z" in c[cid]["why"], cid   # the watchdog's own time
    assert c["pc_control"]["status"] == sa.FAIL and "login_required" in c["pc_control"]["why"]
    assert c["mouth_motion"]["status"] == sa.FAIL and "head_only" in c["mouth_motion"]["why"]
    assert c["two_cameras"]["status"] == sa.FAIL and "webcam_only" in c["two_cameras"]["why"]
    assert c["two_cameras"]["metrics"]["room_s"] == 0
    assert c["fps_game"]["status"] == sa.FAIL and c["fps_game"]["metrics"]["below"] == 30
    assert c["fps_cam2"]["status"] == sa.FAIL and c["fps_cam2"]["metrics"]["median"] == 40.0
    assert c["fps_monitor_feed"]["status"] == sa.MISSING and "no source logs" in c["fps_monitor_feed"]["why"]
    assert c["fps_director"]["status"] == sa.PASS                         # the output pace is 60 even so
    assert c["fps_recordings"]["status"] == sa.MISSING and c["fps_hls_spot"]["status"] == sa.MISSING
    assert "MISSING EVIDENCE" in md and "## Both cameras composed simultaneously: FAIL" in md
    assert "SUB01_STREAMER_VISUAL_PERF fps=" in md and "Verdict: **FAIL**" in md


def test_today_window_with_the_supervisor_blip_is_a_recovered_error(tmp_path):
    code, report, _ = run_today(tmp_path, "2026-10-24T14:00:00Z", "2026-10-24T14:30:00Z")
    c = by_id(report)
    assert code == 1
    assert c["error_recovered"]["status"] == sa.PASS and "service_unhealthy director" in c["error_recovered"]["why"]
    assert c["error_recovered"]["metrics"]["outage_s"] == [4.0]
    assert c["two_cameras"]["status"] == sa.FAIL                          # room for 15 s and 16 s only
    assert c["two_cameras"]["metrics"]["room_s"] == pytest.approx(31, abs=1)
    assert c["two_cameras"]["metrics"]["room_longest_s"] == pytest.approx(16, abs=1)


def test_an_events_log_that_does_not_cover_the_window_is_missing_evidence(tmp_path):
    code, report, _ = run_today(tmp_path, "2026-10-24T17:00:00Z", "2026-10-24T17:30:00Z")
    c = by_id(report)
    assert report["verdict"] == sa.FAIL                                   # mouth_motion fails on the rig anyway
    for cid in ("activity_change", "chat_executed", "chat_refused", "error_recovered", "two_cameras"):
        assert c[cid]["status"] == sa.MISSING and "events.jsonl has no row" in c[cid]["why"], cid


# ------------------------------------------------------------------ the pass scenario

PASS_SINCE, PASS_UNTIL = "2026-10-25T10:00:00Z", "2026-10-25T10:30:00Z"


def media(fx, hls_ok=True):
    """Placeholder segments with the mtimes the director would leave, and a fake probe with their packet counts."""
    rec = fx / "recordings"
    rec.mkdir(exist_ok=True)
    table = {}
    for idx, (end, seconds) in enumerate(((utc("2026-10-25T10:09:00Z"), 600.0), (utc("2026-10-25T10:19:00Z"), 600.0),
                                          (utc("2026-10-25T10:29:00Z"), 600.0), (utc("2026-10-25T10:30:00Z"), 60.0))):
        path = rec / f"sub01-20261025-095900-{idx:03d}.mp4"
        path.write_bytes(b"\0")
        os.utime(path, (end, end))
        table[str(path)] = {"packets": int(seconds * 60), "duration": seconds, "r_frame_rate": "60/1", "fps": 60.0}
    for seg in sa.read_hls(fx / "hls"):
        Path(seg["path"]).write_bytes(b"\0")
        table[seg["path"]] = {"packets": 240 if hls_ok else 120, "duration": 4.0, "r_frame_rate": "60/1",
                              "fps": 60.0 if hls_ok else 30.0}
    return table


def jaw_rig(fx):
    log = fx / "game.log"
    log.write_text(log.read_text().replace("rig=head_only (no jaw bone, no morph targets: emphasis, not lip sync)",
                                           "rig=jaw_bone"))


def run_pass(tmp_path, monkeypatch, mutate=None, hls_ok=True, rig=jaw_rig, extra=()):
    fx = copy_fixture("pass", tmp_path)
    table = media(fx, hls_ok)
    calls = []

    def fake_probe(path, ffprobe="ffprobe", timeout=180.0):
        calls.append(path)
        return dict(table.get(str(path)) or {"error": "unknown file"})

    monkeypatch.setattr(sa, "ffprobe_count", fake_probe)
    for change in (rig, mutate):
        if change:
            change(fx)
    out = tmp_path / "out"
    code = sa.main(["--streamer-dir", str(fx), "--game-log", str(fx / "game.log"), "--since", PASS_SINCE, "--until",
                    PASS_UNTIL, "--out-dir", str(out), "--name", "r", *extra])
    report = json.loads((out / "r.json").read_text())
    return code, report, (out / "r.md").read_text(), calls, by_id(report)


def test_pass_scenario_passes_every_criterion_with_highlights(tmp_path, monkeypatch):
    code, report, md, calls, c = run_pass(tmp_path, monkeypatch)
    assert {k: v["status"] for k, v in c.items()} == {k: sa.PASS for k in ALL}, {k: v["why"] for k, v in c.items()}
    assert code == 0 and report["verdict"] == sa.PASS and report["counts"]["pass"] == len(ALL) - 1   # mouth: waived
    assert report["counts"]["waived"] == 1 and c["mouth_motion"]["waived"]
    assert len(calls) == 6 + 4                                              # 6 HLS segments, 4 recording segments
    assert [s["label"] for s in c["activity_change"]["metrics"]["spans"]] == ["browse", "game", "browse"]
    assert c["chat_executed"]["metrics"]["carried_out"] == 2               # the search and the game launch
    assert c["chat_refused"]["metrics"] == {"refusals": 2, "policy_spoken_recorded": 1, "operational": 1,
                                            "redirects": 0}
    assert c["error_recovered"]["metrics"]["recovered"] == 4
    assert any("induced: kill_browser" in h["label"] for h in c["error_recovered"]["highlights"])
    assert c["two_cameras"]["metrics"]["room_longest_s"] == 900.0
    assert c["fps_recordings"]["metrics"]["coverage"] == 1.0 and not c["fps_recordings"]["metrics"]["gaps"]
    hl = c["chat_executed"]["highlights"][0]
    assert hl["utc"] == "2026-10-25T10:05:00Z" and hl["segment"] == "sub01-20261025-095900-000.mp4"
    assert hl["offset"] == "06:00" and hl["approx"] is False
    starts = {h["label"]: (h.get("segment"), h.get("offset")) for h in c["fps_recordings"]["highlights"]}
    assert starts["segment sub01-20261025-095900-002.mp4"] == ("sub01-20261025-095900-002.mp4", "00:00")
    assert report["highlights_reel"]["windows"] and "streamer_highlights.py" in report["highlights_reel"]["command"]
    assert "Verdict: **PASS**" in md and "## Highlights reel" in md


def test_the_real_head_only_rig_does_not_meet_mouth_motion(tmp_path, monkeypatch):
    code, report, _, _, c = run_pass(tmp_path, monkeypatch, rig=None, extra=("--no-waivers",))
    assert code == 1 and report["verdict"] == sa.FAIL and report["counts"]["waived"] == 0
    assert [k for k, v in c.items() if v["status"] != sa.PASS] == ["mouth_motion"]
    assert "not met" in c["mouth_motion"]["why"] and not c["mouth_motion"]["waived"]


def test_the_owners_mouth_waiver_keeps_the_result_but_not_in_the_verdict(tmp_path, monkeypatch):
    code, report, md, _, c = run_pass(tmp_path, monkeypatch, rig=None)
    assert code == 0 and report["verdict"] == sa.PASS                     # owner, 2026-10-24: no mouth for now
    assert c["mouth_motion"]["status"] == sa.FAIL and "not met" in c["mouth_motion"]["why"]
    assert "owner" in c["mouth_motion"]["waived"] and report["counts"] == {"pass": 15, "fail": 0, "missing": 0, "waived": 1}
    assert "FAIL (waived)" in md and "Waiver: waived by the owner" in md and "1 waived by the owner" in md
    assert set(sa.OWNER_WAIVERS) == {"mouth_motion"}                      # head motion stays required


def test_voice_on_the_kokoro_fallback_fails(tmp_path, monkeypatch):
    def mutate(fx):
        log = fx / "logs/voice.log"
        lines = log.read_text().splitlines()
        lines.insert(3, "voice: chatterbox unavailable (OutOfMemoryError: CUDA out of memory); falling back to kokoro")
        log.write_text("\n".join(lines) + "\n")
    c = run_pass(tmp_path, monkeypatch, mutate)[4]
    assert c["voice_k07"]["status"] == sa.FAIL and "not on chatterbox" in c["voice_k07"]["why"]


def test_one_slow_window_a_speed_restart_and_dup_frames_fail_the_fps_criteria(tmp_path, monkeypatch):
    def mutate(fx):
        log = fx / "game.log"
        text = log.read_text()
        log.write_text(text.replace("PERF fps=59.6", "PERF fps=57.9", 1))
        append(fx / "events.jsonl", director_row("2026-10-25T10:20:00Z", "speed_restart", run="sub01-20261025-095900",
                                                 speed=0.72))
        rewrite_jsonl(fx / "events.jsonl", lambda r: True)
        path = fx / "events.jsonl"
        path.write_text(path.read_text().replace('"dup_frames": 0, "drop_frames": 0, "partial": false}',
                                                 '"dup_frames": 3, "drop_frames": 0, "partial": false}', 1))
    c = run_pass(tmp_path, monkeypatch, mutate)[4]
    assert c["fps_game"]["status"] == sa.FAIL and "1 window(s) below 59.5" in c["fps_game"]["why"]
    assert c["fps_director"]["status"] == sa.FAIL
    assert "speed_restart" in c["fps_director"]["why"] and "dup 3" in c["fps_director"]["why"]
    assert c["error_recovered"]["status"] == sa.FAIL                      # no ffmpeg_started after it within 120 s


def test_a_logging_gap_is_missing_evidence_not_a_pass(tmp_path, monkeypatch):
    def mutate(fx):
        log = fx / "game.log"
        log.write_text("".join(x for x in log.read_text().splitlines(True)
                               if not ("PERF" in x and "2026.10.25-10.11" in x)))
    c = run_pass(tmp_path, monkeypatch, mutate)[4]
    assert c["fps_game"]["status"] == sa.MISSING and "logging gap" in c["fps_game"]["why"]
    assert c["fps_game"]["metrics"]["gaps"][0]["s"] == 70.0


def test_steps_is_not_done_and_an_unbound_request_is_unproven(tmp_path, monkeypatch):
    def mutate(fx):
        path = fx / "events.jsonl"
        path.write_text(path.read_text().replace('"request": "search", "steps": 1, "why": "done"',
                                                 '"request": "search", "steps": 1, "why": "steps"')
                        .replace('"decision_id": "req-1"', '"decision_id": "d9999"'))
        rewrite_jsonl(path, lambda r: not (r.get("kind") == "routine_end" and r.get("name") == "launch_game"))
    c = run_pass(tmp_path, monkeypatch, mutate)[4]
    assert c["chat_executed"]["status"] == sa.FAIL
    assert "ended steps" in c["chat_executed"]["why"] and "no verified result bound" in c["chat_executed"]["why"]


def test_a_request_finished_after_the_window_does_not_count(tmp_path, monkeypatch):
    fx = copy_fixture("pass", tmp_path)                  # request #1 ends at 10:05:26: cut the window at 10:05:20
    src = sa.Sources(fx, fx / "game.log", utc("2026-10-25T09:50:00Z"), utc("2026-10-25T10:05:20Z"), probe=False)
    res = sa.eval_chat_executed(src)
    assert res["status"] == sa.FAIL and "no chat_request_end" in res["why"]


def test_a_restarted_agents_reused_seq_does_not_complete_an_old_request(tmp_path, monkeypatch):
    def mutate(fx):                                      # request #1 never ends; the restarted agent's #1 does
        rewrite_jsonl(fx / "events.jsonl", lambda r: not (r.get("seq") == 1 and r.get("kind") == "chat_request_end")
                      and not (r.get("kind") == "speech" and r.get("seqs") == [1]))
        append(fx / "events.jsonl",
               {"t": "2026-10-25T10:06:00Z", "source": "streamer_up", "kind": "service_started", "service": "agent"},
               agent_row("2026-10-25T10:07:00Z", "chat", seq=1, cls="request", direct=True, text="open the weather"),
               agent_row("2026-10-25T10:07:30Z", "chat_request_end", seq=1, request="navigate", steps=1, why="done"),
               agent_row("2026-10-25T10:07:31Z", "speech", text="Here it is.", tag="request", seqs=[1]))
    c = run_pass(tmp_path, monkeypatch, mutate)[4]["chat_executed"]
    assert "no chat_request_end" in c["metrics"]["problems"]["1"] and "no spoken answer" in c["metrics"]["problems"]["1"]
    assert c["metrics"]["carried_out"] == 1                # the game request still counts


def test_activity_needs_recorded_time_on_both_sides(tmp_path, monkeypatch):
    def mutate(fx):                                      # the director is off air 10:12-10:25: the game is not on air
        append(fx / "events.jsonl",
               director_row("2026-10-25T10:12:00Z", "ffmpeg_stopped", run="sub01-20261025-095900", reason="stop"),
               director_row("2026-10-25T10:25:00Z", "ffmpeg_started", run="sub01-20261025-102500", layout="room",
                            cam2=True, voice=True))
    c = run_pass(tmp_path, monkeypatch, mutate)[4]["activity_change"]
    spans = c["metrics"]["spans"]
    assert c["status"] == sa.FAIL and spans[1]["label"] == "game" and spans[1]["recorded_s"] == 0


def test_a_refusal_spoken_off_air_does_not_count(tmp_path, monkeypatch):
    def mutate(fx):
        append(fx / "events.jsonl",
               director_row("2026-10-25T10:08:01Z", "ffmpeg_stopped", run="sub01-20261025-095900", reason="stop"),
               director_row("2026-10-25T10:08:30Z", "ffmpeg_started", run="sub01-20261025-100830", layout="room",
                            cam2=True, voice=True))
    c = run_pass(tmp_path, monkeypatch, mutate)[4]["chat_refused"]
    assert c["status"] == sa.FAIL and "no policy refusal was spoken while recording" in c["why"]


def test_a_routine_end_at_the_boundary_does_not_verify_the_browse_span(tmp_path, monkeypatch):
    def mutate(fx):                                      # no verified browse outcome before the game starts
        rewrite_jsonl(fx / "events.jsonl", lambda r: not (r.get("kind") == "outcome" and r.get("t", 0) < utc("2026-10-25T10:13:30Z")
                                                          and isinstance(r.get("t"), float)))
    c = run_pass(tmp_path, monkeypatch, mutate)[4]["activity_change"]
    spans = c["metrics"]["spans"]
    assert spans[0]["label"] == "browse" and spans[0]["verified"] == 0 and spans[1]["verified"] >= 1
    assert c["status"] == sa.PASS and "game (" in c["why"] and c["why"].startswith("game")   # game -> browse remains


def test_a_redirect_is_listed_but_not_counted_as_the_refusal(tmp_path, monkeypatch):
    def mutate(fx):
        rewrite_jsonl(fx / "events.jsonl", lambda r: not (r.get("kind") == "chat_request" and r.get("seq") == 3))
        append(fx / "events.jsonl", agent_row("2026-10-25T10:08:00Z", "request_redirect", seq=3,
                                              url="https://login.example.com/", why="login"))
    c = run_pass(tmp_path, monkeypatch, mutate)[4]["chat_refused"]
    assert c["status"] == sa.FAIL and c["metrics"]["redirects"] == 1 and c["why"] == "only operational refusals"
    assert any("redirected (login): undone" in h["label"] for h in c["highlights"])


def test_held_and_frozen_end_separately(tmp_path):
    fx = tmp_path / "s"
    fx.mkdir()
    append(fx / "events.jsonl", agent_row("2026-10-25T10:00:00Z", "held", why="3 failures"),
           agent_row("2026-10-25T10:01:00Z", "stream_frozen", why="black"),
           agent_row("2026-10-25T10:02:00Z", "resume_latches", cleared=["frozen"]),
           agent_row("2026-10-25T10:05:00Z", "resume"))
    src = sa.Sources(fx, fx / "none.log", utc("2026-10-25T09:55:00Z"), utc("2026-10-25T10:10:00Z"), probe=False)
    assert sa.inactive_intervals(src) == [(utc("2026-10-25T10:00:00Z"), utc("2026-10-25T10:05:00Z"))]


def test_a_refused_request_that_got_an_action_fails(tmp_path, monkeypatch):
    def mutate(fx):
        append(fx / "events.jsonl", agent_row("2026-10-25T10:08:05Z", "action", source="chat", decision_id="req-3",
                                              action={"action": "navigate", "url": "https://example.org/"}))
    c = run_pass(tmp_path, monkeypatch, mutate)[4]
    assert c["chat_refused"]["status"] == sa.FAIL and "#3" in c["chat_refused"]["why"]


def test_a_refusal_shown_only_as_a_caption_is_not_delivered(tmp_path, monkeypatch):
    def mutate(fx):
        path = fx / "events.jsonl"
        rows = [json.loads(x) for x in path.read_text().splitlines()]
        for r in rows:
            if r.get("kind") == "speech" and r.get("seqs") == [3]:
                r["kind"] = "caption"
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    c = run_pass(tmp_path, monkeypatch, mutate)[4]
    assert c["chat_refused"]["status"] == sa.FAIL and "no policy refusal was spoken" in c["chat_refused"]["why"]
    assert any("caption only" in h["label"] for h in c["chat_refused"]["highlights"])


def test_webcam_layout_all_along_fails_two_cameras_and_a_short_room_flash_too(tmp_path, monkeypatch):
    def mutate(fx):
        append(fx / "events.jsonl", director_row("2026-10-25T09:59:30Z", "layout_switched", layout="webcam_only",
                                                 previous="room", run="sub01-20261025-095900"))
        rewrite_jsonl(fx / "events.jsonl", lambda r: not (r.get("kind") == "layout_switched" and r.get("layout") == "room"))
    c = run_pass(tmp_path, monkeypatch, mutate)[4]["two_cameras"]
    assert c["status"] == sa.FAIL and c["metrics"]["room_s"] == 0
    flashes = [director_row(f"2026-10-25T10:{m:02d}:00Z", "layout_switched", layout="room", run="sub01-20261025-095900")
               for m in (1, 3, 5)] + [director_row(f"2026-10-25T10:{m:02d}:25Z", "layout_switched", layout="webcam",
                                                   run="sub01-20261025-095900") for m in (1, 3, 5)]

    def mutate2(fx):
        mutate(fx)
        append(fx / "events.jsonl", *flashes)
        rows = sa.timed(sa.read_jsonl([fx / "events.jsonl"]), "t", "utc")
        (fx / "events.jsonl").write_text("".join(json.dumps({k: v for k, v in r.items() if k != "_t"}) + "\n" for r in rows))
    c = run_pass(tmp_path / "b", monkeypatch, mutate2)[4]["two_cameras"]
    assert c["status"] == sa.FAIL and c["metrics"]["room_s"] == 75.0 and c["metrics"]["room_longest_s"] == 25.0


def test_pc_inputs_while_not_connected_fail(tmp_path, monkeypatch):
    def mutate(fx):
        path = fx / "desktop-vagon/events.jsonl"
        rewrite_jsonl(path, lambda r: r.get("state") != "connected")
    c = run_pass(tmp_path, monkeypatch, mutate)[4]["pc_control"]
    assert c["status"] == sa.FAIL and c["metrics"]["while_connected"] == 0


def test_flat_head_pose_during_speech_fails_head_motion(tmp_path, monkeypatch):
    import re

    def mutate(fx):
        log = fx / "game.log"
        log.write_text(re.sub(r"headPitch=[\d.]+ headYaw=[-\d.]+", "headPitch=14.5 headYaw=0.1", log.read_text()))
    c = run_pass(tmp_path, monkeypatch, mutate)[4]["head_motion"]
    assert c["status"] == sa.FAIL and "below 1.0 deg" in c["why"]


def test_unrecovered_pending_and_healthy_recording_faults(tmp_path, monkeypatch):
    def pending(fx):                                     # deadline runs past the window end
        append(fx / "events.jsonl", director_row("2026-10-25T10:29:30Z", "ffmpeg_exited", run="sub01-20261025-095900",
                                                 code=1))
    c = run_pass(tmp_path, monkeypatch, pending)[4]["error_recovered"]
    assert c["status"] == sa.MISSING and "pending" in c["why"]

    def restarted(fx):                                   # restart, then the new run's output measured at 60
        append(fx / "events.jsonl",
               director_row("2026-10-25T10:20:00Z", "ffmpeg_exited", run="sub01-20261025-095900", code=1),
               director_row("2026-10-25T10:20:02Z", "ffmpeg_started", run="sub01-20261025-102002", layout="room",
                            cam2=True, voice=True),
               director_row("2026-10-25T10:25:00Z", "segment_fps", run="sub01-20261025-102002",
                            segment="sub01-20261025-102002-000.mp4", frames=17880, wall_s=298.0, media_s=298.0,
                            fps=60.0, fps_media=60.0, dup_frames=0, drop_frames=0, partial=True))
    c = run_pass(tmp_path / "b", monkeypatch, restarted)[4]["error_recovered"]
    assert c["status"] == sa.PASS and c["metrics"]["recovered"] == 5

    def restarted_slow(fx):
        restarted(fx)
        path = fx / "events.jsonl"
        path.write_text(path.read_text().replace('"fps_media": 60.0, "dup_frames": 0, "drop_frames": 0, "partial": true',
                                                 '"fps_media": 41.0, "dup_frames": 0, "drop_frames": 0, "partial": true'))
    c = run_pass(tmp_path / "c", monkeypatch, restarted_slow)[4]["error_recovered"]
    assert c["status"] == sa.FAIL and "ffmpeg_exited" in c["why"]


def test_a_recovery_after_the_window_end_does_not_count(tmp_path, monkeypatch):
    def mutate(fx):
        append(fx / "events.jsonl",
               director_row("2026-10-25T10:29:00Z", "ffmpeg_exited", run="sub01-20261025-095900", code=1),
               director_row("2026-10-25T10:30:30Z", "ffmpeg_started", run="sub01-20261025-103030", layout="room",
                            cam2=True, voice=True))
    c = run_pass(tmp_path, monkeypatch, mutate)[4]["error_recovered"]
    assert c["status"] == sa.MISSING and c["metrics"]["pending"] == 1 and c["metrics"]["recovered"] == 4


def test_an_unrecovered_fault_is_not_hidden_by_a_recovered_one_of_the_same_kind(tmp_path, monkeypatch):
    def mutate(fx):                                      # A at 10:20:00 has no ready within 60 s; B at 10:20:55 has one
        append(fx / "desktop-vagon/events.jsonl",
               {"t": "2026-10-25T10:20:00.000+00:00", "kind": "relaunch", "number": 2, "why": "browser exited"},
               {"t": "2026-10-25T10:20:55.000+00:00", "kind": "relaunch", "number": 3, "why": "browser exited"},
               {"t": "2026-10-25T10:21:02.000+00:00", "kind": "browser", "state": "ready", "restarts": 3})
    c = run_pass(tmp_path, monkeypatch, mutate)[4]["error_recovered"]
    assert c["status"] == sa.FAIL and c["metrics"]["unrecovered"] == 1
    assert any(" x2: NOT recovered" in h["label"] for h in c["highlights"])


def test_cam2_lost_mid_run_ends_the_room_composition(tmp_path, monkeypatch):
    def mutate(fx):
        append(fx / "events.jsonl", director_row("2026-10-25T10:22:00Z", "cam2_changed", cam2=False,
                                                 reason="cam2 last frame 3.2s ago", run="sub01-20261025-095900"))
    c = run_pass(tmp_path, monkeypatch, mutate)[4]
    assert c["two_cameras"]["metrics"]["room_s"] == 900.0 + 120.0
    assert c["error_recovered"]["status"] == sa.PASS                      # cam2 healthy again in the next CAM2 line


def test_voice_changes_do_not_split_the_room_stretch(tmp_path, monkeypatch):
    def mutate(fx):
        append(fx / "events.jsonl", *[director_row(f"2026-10-25T10:{m:02d}:00Z", "voice_changed", voice=True,
                                                   reason="voice reconnected") for m in (4, 8, 12)])
        rows = sa.timed(sa.read_jsonl([fx / "events.jsonl"]), "t", "utc")
        (fx / "events.jsonl").write_text("".join(json.dumps({k: v for k, v in r.items() if k != "_t"}) + "\n" for r in rows))
    c = run_pass(tmp_path, monkeypatch, mutate)[4]["two_cameras"]
    assert c["status"] == sa.PASS and c["metrics"]["room_longest_s"] == 900.0


def test_an_utterance_before_the_restarted_games_mouth_ready_is_missing(tmp_path, monkeypatch):
    def mutate(fx):
        log = fx / "game.log"
        log.write_text(log.read_text() + "[2026.10.25-10.11.00:000][  0]LogTemp: Display: SUB01_NATIVE_INIT_BEGIN\n"
                       "[2026.10.25-10.13.00:000][  3]LogTemp: Display: SUB01_STREAMER_VISUAL_MOUTH_READY rig=jaw_bone "
                       "file=/home/unreal/.sub01-private/streamer/mouth.json pollHz=30 headPitchDeg=2 jawPitchDeg=12\n")
    c = run_pass(tmp_path, monkeypatch, mutate)[4]["mouth_motion"]
    assert c["status"] == sa.MISSING and c["metrics"]["utterances_without_ready"] == 1


def test_an_utterance_with_an_unknown_engine_makes_k07_missing(tmp_path, monkeypatch):
    def mutate(fx):
        log = fx / "logs/voice.log"
        lines = log.read_text().splitlines()
        drop = next(i for i, x in enumerate(lines) if "voice: spoken id=" in x)
        log.write_text("\n".join(lines[:drop] + lines[drop + 1:]) + "\n")
    c = run_pass(tmp_path, monkeypatch, mutate)[4]["voice_k07"]
    assert c["status"] == sa.MISSING and "1 of 11" in c["why"]


def test_head_motion_uses_each_axis_on_its_own(tmp_path, monkeypatch):
    import re

    def yaw_unusable(fx):
        log = fx / "game.log"
        log.write_text(re.sub(r"headYaw=[-\d.]+", "headYaw=n/a", log.read_text()))
    c = run_pass(tmp_path, monkeypatch, yaw_unusable)[4]["head_motion"]
    assert c["status"] == sa.PASS and set(c["metrics"]["range_deg"]) == {"headPitch"}

    def both_unusable(fx):
        log = fx / "game.log"
        log.write_text(re.sub(r"head(Pitch|Yaw)=[-\d.]+", r"head\1=n/a", log.read_text()))
    c = run_pass(tmp_path / "b", monkeypatch, both_unusable)[4]["head_motion"]
    assert c["status"] == sa.MISSING


def test_an_intended_cam2_off_is_not_a_fault_but_a_lost_cam2_is(tmp_path, monkeypatch):
    lost = director_row("2026-10-25T10:20:00Z", "cam2_changed", cam2=False, reason="cam2 last frame 3.4s ago",
                        run="sub01-20261025-095900")

    def intended(fx):
        append(fx / "events.jsonl", lost)
        log = fx / "game.log"
        log.write_text(log.read_text().replace("on=1 window_s=30\n[2026.10.25-10.20.04", "on=0 window_s=30\n"
                                               "[2026.10.25-10.20.04", 1).replace(
            "[2026.10.25-10.20.04:000][240]LogTemp: Display: SUB01_STREAMER_VISUAL_CAM2 fps=59.8",
            "[2026.10.25-10.20.04:000][240]LogTemp: Display: SUB01_STREAMER_VISUAL_CAM2 fps=0.0"))
        text = log.read_text()
        log.write_text(text.replace("frames=216162 reader=1", "frames=216162 reader=0").replace(
            "dropped_slots=0 on=1 window_s=30\n[2026.10.25-10.20.10", "dropped_slots=0 on=0 window_s=30\n[2026.10.25-10.20.10"))
    res = run_pass(tmp_path, monkeypatch, intended)[4]
    assert res["error_recovered"]["metrics"]["faults"] == 4                 # the cam2 drop is not counted

    def unintended(fx):
        append(fx / "events.jsonl", lost)
    res = run_pass(tmp_path / "b", monkeypatch, unintended)[4]
    assert res["error_recovered"]["metrics"]["faults"] == 5
    assert any(h["label"].startswith("cam2 lost") and "recovered" in h["label"] for h in res["error_recovered"]["highlights"])


def test_single_activity_with_site_changes_fails(tmp_path, monkeypatch):
    def mutate(fx):
        rewrite_jsonl(fx / "events.jsonl", lambda r: r.get("kind") != "routine_end")
        append(fx / "events.jsonl", agent_row("2026-10-25T10:02:00Z", "action", source="model",
                                              action={"action": "navigate", "url": "https://en.wikipedia.org/wiki/Amphipoda"}))
    c = run_pass(tmp_path, monkeypatch, mutate)[4]["activity_change"]
    assert c["status"] == sa.FAIL and "one activity only (browse)" in c["why"] and "site change" in c["why"]


def test_the_activity_running_at_the_window_start_is_carried_in(tmp_path, monkeypatch):
    fx = copy_fixture("pass", tmp_path)
    src = sa.Sources(fx, fx / "game.log", utc("2026-10-25T10:14:00Z"), utc(PASS_UNTIL), probe=False)
    res = sa.eval_activity(src)
    spans = res["metrics"]["spans"]
    assert spans[0]["label"] == "game" and spans[0]["start_utc"] == "2026-10-25T10:14:00Z"
    assert res["status"] == sa.PASS and "game" in res["why"] and "-> browse" in res["why"]
    src = sa.Sources(fx, fx / "game.log", utc("2026-10-25T10:40:00Z"), utc("2026-10-25T10:50:00Z"), probe=False)
    assert sa.eval_activity(src)["status"] == sa.MISSING                  # no agent row after 10:29:50: not covered


def test_quiet_time_does_not_count_as_activity(tmp_path, monkeypatch):
    def mutate(fx):                                      # quiet from 10:13:40 to 10:24:00: the game span is not 60 s
        append(fx / "events.jsonl", agent_row("2026-10-25T10:13:40Z", "quiet", mode="error", reason="x"),
               agent_row("2026-10-25T10:24:00Z", "quiet_end", after_s=620))
    c = run_pass(tmp_path, monkeypatch, mutate)[4]["activity_change"]
    assert c["status"] == sa.FAIL and c["metrics"]["inactive_s"] == 620.0


def test_a_probe_timeout_is_missing_evidence_and_a_measured_gap_fails(tmp_path, monkeypatch):
    fx = copy_fixture("pass", tmp_path)
    table = media(fx)
    seg1 = str(fx / "recordings/sub01-20261025-095900-001.mp4")
    table[seg1] = {"error": "TimeoutExpired: ffprobe timed out"}
    hls0 = sa.read_hls(fx / "hls")[0]["path"]
    table[hls0] = {"error": "TimeoutExpired: ffprobe timed out"}
    monkeypatch.setattr(sa, "ffprobe_count", lambda path, *a, **k: dict(table[str(path)]))
    src = sa.Sources(fx, fx / "game.log", utc(PASS_SINCE), utc(PASS_UNTIL))
    rec, hls = sa.eval_fps_recordings(src), sa.eval_fps_hls(src)
    assert rec["status"] == sa.MISSING and "cannot measure" in rec["why"] and not any(
        g["certain"] for g in rec["metrics"]["gaps"])
    assert hls["status"] == sa.MISSING and "cannot measure" in hls["why"]
    os.remove(seg1)                                      # segment 001 is gone: 10:09-10:19 between two measured ones
    src = sa.Sources(fx, fx / "game.log", utc(PASS_SINCE), utc(PASS_UNTIL))
    rec = sa.eval_fps_recordings(src)
    assert rec["status"] == sa.FAIL and "not recording 10:09:00-10:19:00Z (600 s)" in rec["why"]


def test_hls_below_60_fails(tmp_path, monkeypatch):
    c = run_pass(tmp_path, monkeypatch, hls_ok=False)[4]
    assert c["fps_hls_spot"]["status"] == sa.FAIL and "30.0 fps" in c["fps_hls_spot"]["why"]


def test_hls_segments_outside_the_window_and_rotated_ones_are_missing_evidence(tmp_path, monkeypatch):
    fx = copy_fixture("pass", tmp_path)
    monkeypatch.setattr(sa, "ffprobe_count", lambda *a, **k: {"packets": 240, "duration": 4.0, "fps": 60.0})
    src = sa.Sources(fx, fx / "game.log", utc("2026-10-25T10:00:00Z"), utc("2026-10-25T10:20:00Z"))
    res = sa.eval_fps_hls(src)
    assert res["status"] == sa.MISSING and "within ~20 s" in res["why"]
    src = sa.Sources(fx, fx / "game.log", utc(PASS_SINCE), utc(PASS_UNTIL))   # the .ts files do not exist: rotated
    res = sa.eval_fps_hls(src)
    assert res["status"] == sa.MISSING and "rotated away" in res["why"]


def test_last_rehearsal_window(tmp_path):
    fx = copy_fixture("pass", tmp_path)
    args = type("A", (), {"last_rehearsal": True, "since": None, "until": None, "minutes": 30.0})()
    assert sa.parse_window(args, fx) == (utc(PASS_SINCE), utc(PASS_UNTIL))
    args = type("A", (), {"last_rehearsal": False, "since": None, "until": "2026-10-25T10:30:00Z", "minutes": 10.0})()
    assert sa.parse_window(args, fx) == (utc("2026-10-25T10:20:00Z"), utc(PASS_UNTIL))
    with pytest.raises(SystemExit):
        sa.parse_window(type("A", (), {"last_rehearsal": False, "since": "2026-10-25T11:00:00Z",
                                       "until": PASS_UNTIL, "minutes": 30.0})(), fx)


def test_on_air_timeline_handles_stops_and_relaunches(tmp_path):
    fx = tmp_path / "s"
    fx.mkdir()
    rows = [("09:00:00", "ffmpeg_started", {"run": "r1", "layout": "room", "cam2": True, "voice": True}),
            ("09:10:00", "layout_switched", {"run": "r1", "layout": "webcam"}),
            ("09:20:00", "ffmpeg_stopped", {"run": "r1", "reason": "cam2 dropped"}),
            ("09:20:02", "ffmpeg_started", {"run": "r2", "layout": "webcam", "cam2": False, "voice": True}),
            ("09:25:00", "layout_switched", {"run": "r1", "layout": "room"})]      # a stale run's row is ignored
    append(fx / "events.jsonl", *[director_row(f"2026-10-25T{t}Z", k, **f) for t, k, f in rows])
    src = sa.Sources(fx, fx / "none.log", utc("2026-10-25T09:05:00Z"), utc("2026-10-25T09:30:00Z"), probe=False)
    spans = src.air()
    assert [(s["layout"], s["cam2"], s["run"]) for s in spans] == [("room", True, "r1"), ("webcam", True, "r1"),
                                                                   ("webcam", False, "r2")]
    assert spans[-1]["end"] == utc("2026-10-25T09:30:00Z")
    assert src.recorded(utc("2026-10-25T09:20:01Z")) is False and src.recorded(utc("2026-10-25T09:21:00Z"))
    assert sa.eval_two_cameras(src)["metrics"]["room_s"] == 300.0


# ------------------------------------------------------------------ the real ffprobe, on tiny clips

needs_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="no ffmpeg")


def clip_file(path, rate, seconds=2, fmt=None):
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size=64x36:rate={rate}", "-t", str(seconds),
           "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-g", str(rate * 2)]
    subprocess.run(cmd + (["-f", fmt] if fmt else []) + [str(path)], check=True, timeout=60)


@needs_ffmpeg
def test_ffprobe_count_packets_measures_the_real_rate(tmp_path):
    clip_file(tmp_path / "a.mp4", 60)
    clip_file(tmp_path / "b.mp4", 30)
    a, b = sa.ffprobe_count(tmp_path / "a.mp4"), sa.ffprobe_count(tmp_path / "b.mp4")
    assert a["packets"] == 120 and a["fps"] == pytest.approx(60, abs=0.5) and a["r_frame_rate"] == "60/1"
    assert b["packets"] == 60 and b["fps"] == pytest.approx(30, abs=0.5)
    (tmp_path / "bad.mp4").write_bytes(b"not a video")
    assert "error" in sa.ffprobe_count(tmp_path / "bad.mp4")
    assert "error" in sa.ffprobe_count(tmp_path / "a.mp4", ffprobe=str(tmp_path / "no-ffprobe"))


@needs_ffmpeg
def test_hls_check_on_real_ts_segments(tmp_path):
    hls = tmp_path / "s" / "hls"
    hls.mkdir(parents=True)
    t0 = utc("2026-10-25T10:29:50Z")
    lines = ["#EXTM3U", "#EXT-X-VERSION:6", "#EXT-X-TARGETDURATION:2"]
    for k, rate in enumerate((60, 60, 30)):
        clip_file(hls / f"seg-{k}.ts", rate, fmt="mpegts")
        stamp = datetime.fromtimestamp(t0 + 2 * k, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")
        lines += ["#EXTINF:2.000000,", f"#EXT-X-PROGRAM-DATE-TIME:{stamp}", f"seg-{k}.ts"]
    (hls / "live.m3u8").write_text("\n".join(lines) + "\n")
    src = sa.Sources(tmp_path / "s", tmp_path / "none.log", t0 - 60, t0 + 10)
    res = sa.eval_fps_hls(src)
    assert res["status"] == sa.FAIL and [p["fps"] for p in res["metrics"]["segments"]] == [60.0, 60.0, 30.0]


# ------------------------------------------------------------------ the director's fifo mode (offscreen game)

def fifo_mode(main_fps=60.0, tap_ok=True):
    """The pass scenario recorded with `--game-source fifo`: every run reads main.mjpeg and every segment row has the
    seq tap's count of unique main-view frames."""
    def mutate(fx):
        path = fx / "events.jsonl"
        rows = [json.loads(x) for x in path.read_text().splitlines()]
        for r in rows:
            if r.get("source") == "director" and r.get("kind") == "ffmpeg_started":
                r.update(main="fifo", seq_tap=True, game="fifo:main.mjpeg")
            elif r.get("source") == "director" and r.get("kind") == "segment_fps":
                unique = int(round(main_fps * r["wall_s"]))
                r.update(main_source="fifo", main_frames=unique, main_unique=unique, main_fps=main_fps,
                         main_repeated=0, main_gaps=0, main_noseq=0, main_bad=0, main_overflows=0, main_tap_ok=tap_ok,
                         game_written=unique, game_fps=main_fps, game_dropped=0, main_max_gap_ms=21)
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return mutate


def main_view_lost_and_back(main_fps=60.0, back=True):
    """At 10:23 the main view goes stale: a placeholder run, then (with `back`) a run on the FIFO again."""
    def mutate(fx):
        fifo_mode()(fx)
        rows = [director_row("2026-10-25T10:23:00Z", "main_changed", main="placeholder", previous="fifo",
                             reason="main view last written 2.3s ago", run="sub01-20261025-095900", failures=1),
                director_row("2026-10-25T10:23:01Z", "ffmpeg_stopped", run="sub01-20261025-095900",
                             reason="main view stale: main view last written 2.3s ago", code=-9),
                director_row("2026-10-25T10:23:02Z", "ffmpeg_started", run="sub01-20261025-102302", layout="room",
                             cam2=True, voice=True, main="placeholder", seq_tap=False, game="placeholder")]
        if back:
            unique = int(main_fps * 258)
            rows += [director_row("2026-10-25T10:23:40Z", "main_changed", main="fifo", previous="placeholder",
                                  reason="main view last written 0.1s ago, writer present", run="sub01-20261025-102302"),
                     director_row("2026-10-25T10:23:41Z", "ffmpeg_stopped", run="sub01-20261025-102302",
                                  reason="main view back", code=255),
                     director_row("2026-10-25T10:23:42Z", "ffmpeg_started", run="sub01-20261025-102342", layout="room",
                                  cam2=True, voice=True, main="fifo", seq_tap=True, game="fifo:main.mjpeg"),
                     director_row("2026-10-25T10:28:00Z", "segment_fps", run="sub01-20261025-102342",
                                  segment="sub01-20261025-102342-000.mp4", frames=15480, wall_s=258.0, media_s=258.0,
                                  fps=60.0, fps_media=60.0, dup_frames=0, drop_frames=0, partial=True,
                                  main_source="fifo", main_frames=unique, main_unique=unique, main_fps=main_fps,
                                  main_tap_ok=True, game_written=unique, game_fps=main_fps, game_dropped=0,
                                  main_max_gap_ms=19)]
        append(fx / "events.jsonl", *rows)
    return mutate


def test_fifo_mode_pass_scenario_reports_the_unique_main_view_frames(tmp_path, monkeypatch):
    code, report, md, _, c = run_pass(tmp_path, monkeypatch, fifo_mode())
    assert {k: v["status"] for k, v in c.items()} == {k: sa.PASS for k in ALL}, {k: v["why"] for k, v in c.items()}
    assert code == 0 and report["verdict"] == sa.PASS
    fps = c["fps_director"]
    assert fps["metrics"]["main_fps_weighted"] == 60.0 and fps["metrics"]["main_rows"] == 3
    assert "60.0 unique main-view fps (fifo mode)" in fps["why"] and "main_fps" in fps["thresholds"]


def test_x11_rows_are_judged_as_before(tmp_path, monkeypatch):
    c = run_pass(tmp_path, monkeypatch)[4]["fps_director"]
    assert c["status"] == sa.PASS and "main_fps_weighted" not in c["metrics"] and "main_fps" not in c["thresholds"]


def test_fifo_rows_below_59_5_fail_and_an_invalid_count_is_missing_evidence(tmp_path, monkeypatch):
    c = run_pass(tmp_path, monkeypatch, fifo_mode(main_fps=58.0))[4]["fps_director"]
    assert c["status"] == sa.FAIL and "unique main-view frames 57.999 fps over 3 FIFO row(s)" in c["why"]
    c = run_pass(tmp_path / "b", monkeypatch, fifo_mode(tap_ok=False))[4]["fps_director"]
    assert c["status"] == sa.MISSING and "not valid in 3 row(s)" in c["why"]


def test_the_placeholder_card_is_not_the_webcam_and_its_rows_fail(tmp_path, monkeypatch):
    def card(fx):
        fifo_mode()(fx)
        path = fx / "events.jsonl"
        path.write_text(path.read_text().replace('"main": "fifo"', '"main": "placeholder"')
                        .replace('"main_source": "fifo"', '"main_source": "placeholder"'))
    c = run_pass(tmp_path, monkeypatch, card)[4]
    assert c["two_cameras"]["status"] == sa.FAIL and c["two_cameras"]["metrics"]["room_s"] == 0.0
    assert any("placeholder main view" in k for k in c["two_cameras"]["metrics"]["seconds_by_layout"])
    assert c["fps_director"]["status"] == sa.FAIL and "placeholder card" in c["fps_director"]["why"]


def fifo_row(when, run, wall, unique, partial=False, source="fifo", **extra):
    return director_row(when, "segment_fps", run=run, segment=f"{run}-000.mp4", frames=int(wall * 60), wall_s=wall,
                        media_s=wall, fps=60.0, fps_media=60.0, dup_frames=0, drop_frames=0, partial=partial,
                        main_source=source, main_unique=unique, main_frames=unique,
                        main_fps=round(unique / wall, 2), **({"main_tap_ok": True} if source == "fifo" else {}),
                        **extra)


def fifo_src(tmp_path, *rows, since="2026-10-25T09:00:00Z", until="2026-10-25T10:00:00Z"):
    fx = tmp_path / "s"
    fx.mkdir(parents=True, exist_ok=True)
    append(fx / "events.jsonl", *rows)
    return sa.Sources(fx, fx / "none.log", utc(since), utc(until), probe=False)


def test_the_weighted_main_view_gate_is_unrounded_and_weighted_by_wall_time(tmp_path):
    exact = sa.eval_fps_director(fifo_src(tmp_path / "a", fifo_row("2026-10-25T09:20:00Z", "r1", 600.0, 35700)))
    assert exact["status"] == sa.PASS and exact["metrics"]["main_fps_weighted"] == 59.5            # 59.5 is enough
    below = sa.eval_fps_director(fifo_src(tmp_path / "b", fifo_row("2026-10-25T09:20:00Z", "r1", 600.0, 35698)))
    assert below["status"] == sa.FAIL and "59.497" in below["why"]                 # 59.4967 would round to 59.5
    mixed = sa.eval_fps_director(fifo_src(tmp_path / "c", fifo_row("2026-10-25T09:20:00Z", "r1", 600.0, 35760),
                                          fifo_row("2026-10-25T09:30:00Z", "r2", 60.0, 3540, partial=True)))
    assert mixed["status"] == sa.PASS and mixed["metrics"]["main_fps_weighted"] == 59.545   # a row average: 59.3


def test_a_short_placeholder_row_fails_too(tmp_path):
    res = sa.eval_fps_director(fifo_src(tmp_path, fifo_row("2026-10-25T09:20:00Z", "r1", 600.0, 36000),
                                        fifo_row("2026-10-25T09:20:40Z", "r2", 39.0, 0, partial=True,
                                                 source="placeholder")))
    assert res["status"] == sa.FAIL and "r2-000.mp4: main view on the placeholder card (39.0 s)" in res["why"]
    alone = sa.eval_fps_director(fifo_src(tmp_path / "b", fifo_row("2026-10-25T09:20:40Z", "r2", 39.0, 0, partial=True,
                                                                   source="placeholder")))
    assert alone["status"] == sa.FAIL                                              # not "no row overlaps the window"


@pytest.mark.parametrize("tap_ok", [False, None, "missing"])
def test_the_main_view_recovery_skips_rows_without_a_valid_count(tmp_path, tap_ok):
    bad = fifo_row("2026-10-25T09:25:00Z", "r9", 300.0, 18000, partial=True)
    if tap_ok == "missing":
        del bad["main_tap_ok"]
    else:
        bad["main_tap_ok"] = tap_ok
    src = fifo_src(tmp_path, bad)
    assert sa.output_healthy(src, "r9", utc("2026-10-25T09:20:00Z"), main=True) is None          # pending, not judged
    later = fifo_src(tmp_path / "b", bad, fifo_row("2026-10-25T09:35:00Z", "r9", 600.0, 36000))
    assert sa.output_healthy(later, "r9", utc("2026-10-25T09:20:00Z"), main=True) is True
    slow = fifo_src(tmp_path / "c", bad, fifo_row("2026-10-25T09:35:00Z", "r9", 600.0, 30000))
    assert sa.output_healthy(slow, "r9", utc("2026-10-25T09:20:00Z"), main=True) is False


def test_a_main_view_recovery_without_a_valid_row_is_pending_until_660_s(tmp_path):
    rows = [director_row("2026-10-25T09:20:00Z", "main_changed", main="placeholder", previous="fifo", reason="stale"),
            director_row("2026-10-25T09:20:40Z", "ffmpeg_started", run="r9", layout="webcam", main="fifo"),
            dict(fifo_row("2026-10-25T09:25:00Z", "r9", 260.0, 15600, partial=True), main_tap_ok=False)]
    pending = sa.eval_errors(fifo_src(tmp_path / "a", *rows, until="2026-10-25T09:30:00Z"))
    assert pending["status"] == sa.MISSING and pending["metrics"]["pending"] == 1
    late = sa.eval_errors(fifo_src(tmp_path / "b", *rows, until="2026-10-25T09:32:00Z"))
    assert late["status"] == sa.FAIL and late["metrics"]["unrecovered"] == 1             # 09:20:40 + 660 s passed


def test_main_view_lost_and_back_is_a_recovered_error(tmp_path, monkeypatch):
    c = run_pass(tmp_path, monkeypatch, main_view_lost_and_back())[4]
    err = c["error_recovered"]
    assert err["status"] == sa.PASS and err["metrics"]["recovered"] == 5, err["why"]
    assert any(h["label"].startswith("main view lost (main view last written 2.3s ago): recovered, outage 42 s")
               for h in err["highlights"]), err["highlights"]
    assert c["two_cameras"]["status"] == sa.PASS                           # the card's 40 s are not room time
    assert c["two_cameras"]["metrics"]["seconds_by_layout"]["room (cam2 in the graph) (placeholder main view)"] == 39.0
    c = run_pass(tmp_path / "b", monkeypatch, main_view_lost_and_back(main_fps=50.0))[4]["error_recovered"]
    assert c["status"] == sa.FAIL and "main view lost" in c["why"]
    c = run_pass(tmp_path / "c", monkeypatch, main_view_lost_and_back(back=False))[4]
    assert c["error_recovered"]["status"] == sa.FAIL and c["error_recovered"]["metrics"]["unrecovered"] == 1
    assert "main view lost" in c["error_recovered"]["why"]                  # 10:23 + 300 s passed inside the window
    assert c["two_cameras"]["status"] == sa.PASS and c["two_cameras"]["metrics"]["room_longest_s"] == 900.0
