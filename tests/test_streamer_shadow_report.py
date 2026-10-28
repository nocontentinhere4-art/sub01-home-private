"""The shadow trial report (scripts/streamer_shadow_report.py): primary and shadow compared from the agent's audit.

    python -m pytest tests/test_streamer_shadow_report.py -q
Synthetic audit rows only. Kimi (plan step 5, F6): exact token and cost joins by decision, labelled click containment,
correctness and cost per correct action null without labels (never zero), null-vs-null counted only when labelled,
rotated files aggregated, and no promotion output.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import streamer_shadow_report as SR  # noqa: E402

T0 = 1_800_000_000.0


def rows():
    def dec(i, action, cost, latency, dropped=()):
        return {"t": T0 + i, "kind": "decision", "run": "r1", "decision_id": f"d{i}", "provider": "anthropic", "action": action,
                "latency_ms": latency, "cost_usd": cost, "dropped": list(dropped)}

    def sh(i, kind, target, latency, cost, error=None, parse_valid=True, valid=True, primary_target=None, agree=None):
        return {"t": T0 + i + 0.5, "kind": "shadow_decision", "run": "r1", "decision_id": f"d{i}", "provider": "kimi",
                "shadow_kind": kind, "target": target, "primary_target": primary_target, "latency_ms": latency,
                "cost_usd": cost, "error": error, "parse_valid": parse_valid, "valid": valid,
                "agree_kind": None if agree is None else agree[0], "agree": None if agree is None else agree[1],
                "both_null": agree == (True, True) and kind is None}
    return [
        dec(1, {"action": "click", "mark": 3}, 0.004, 900),
        sh(1, "click", "[105, 98]", 4000, 0.002, primary_target="mark 3 @100,100", agree=(True, True)),
        dec(2, {"action": "scroll", "direction": "down", "amount": 300}, 0.002, 1100, dropped=["say: too long"]),
        sh(2, None, None, 60000, 0.0, error="timeout", parse_valid=False, valid=False),
        dec(3, None, 0.001, 700),
        sh(3, None, None, 3000, 0.001, agree=(True, True)),
        dec(4, {"action": "click", "point": [500, 500]}, 0.003, 800, dropped=["action: mark not on the page"]),
        {"t": T0 + 5, "kind": "shadow_skipped", "run": "r1", "decision_id": "d4", "why": "busy"},
        {"t": T0 + 6, "kind": "decision_raw", "run": "r1", "decision_id": "d5", "provider": "anthropic"},
    ]


def side(doc, name, provider):
    return next(s for s in doc["sides"] if s["side"] == name and s["provider"] == provider)


def test_without_labels_correctness_and_cost_per_correct_action_are_null_never_zero():
    doc = SR.report(rows())
    p, s = side(doc, "primary", "anthropic"), side(doc, "shadow", "kimi")
    assert p["decisions"] == 5 and p["parse_valid_rate"] == 0.8 and p["valid_rate"] == 0.6 and p["errors"] == 1
    assert p["latency_ms"] == {"p50": 800, "p95": 1100, "max": 1100} and p["cost_usd"] == 0.01 and p["clicks"] == 2
    assert (p["correct"], p["cost_per_correct_usd"], p["click_in_target_rate"]) == (None, None, None)
    assert s["decisions"] == 3 and s["timeouts"] == 1 and s["parse_valid_rate"] == 0.667 and s["cost_usd"] == 0.003
    assert (s["correct"], s["cost_per_correct_usd"], s["click_in_target_rate"]) == (None, None, None)
    a, c = doc["agreement"], doc["coverage"]
    assert (a["compared"], a["agree"], a["both_null"], a["agree_rate_acting"]) == (2, 2, 1, 1.0)
    assert (c["decisions"], c["with_shadow_row"], c["with_skip_row"], c["accounted_rate"]) == (4, 3, 1, 1.0)
    assert "promot" not in json.dumps(doc)                                 # no promotion decision in it


def label(did, who, run=None, **kw):
    return dict({"decision_id": did, "who": who}, **({"run": run} if run else {}), **kw)


def test_labels_give_click_containment_correctness_and_cost_per_correct_action():
    labels = [label("d1", "primary", correct=True, target_box=[90, 90, 20, 20]),
              label("d1", "shadow", "r1", correct=False, target_box=[90, 90, 20, 20]),
              label("d3", "primary", correct=True),                       # nothing to do, and rightly nothing done
              label("d4", "primary", correct=False, target_box=[0, 0, 10, 10])]
    doc = SR.report(rows(), labels)
    p, s = side(doc, "primary", "anthropic"), side(doc, "shadow", "kimi")
    assert (p["labelled"], p["correct"], p["clicks_labelled"], p["click_in_target_rate"]) == (3, 2, 2, 0.5)
    assert p["cost_per_correct_usd"] == round((0.004 + 0.001 + 0.003) / 2, 6)
    assert (s["labelled"], s["correct"], s["click_in_target_rate"], s["cost_per_correct_usd"]) == (1, 0, 1.0, None)
    assert SR.point_of("mark 3 @1100,125") == (1100.0, 125.0) and SR.point_of("[640, 360]") == (640.0, 360.0)
    assert SR.inside((5, 5), [0, 0, 10, 10]) and not SR.inside((11, 5), [0, 0, 10, 10]) and not SR.inside(None, [0, 0, 1, 1])


def test_two_runs_with_the_same_decision_ids_are_kept_apart_and_legacy_labels_are_never_guessed():
    """Kimi (pre-commit review): ids restart at d1 in every run; rows are joined by (run, decision_id), a label without
    a run is used only when one run has that id, and a labelled click without a readable point is a miss."""
    r2 = [dict(r, run="r2", t=r["t"] + 1000) for r in rows()[:4]]       # d1, d2 again in a second run
    r2[1] = dict(r2[1], target="no point here", shadow_kind="click", primary_target=None)
    lost = {"t": T0 + 2000, "kind": "shadow_skipped", "run": "r3", "decision_run": "r1", "decision_id": "d5",
            "why": "lost_at_shutdown"}
    doc = SR.report(rows() + r2 + [lost], [
        label("d1", "primary", correct=True),                             # d1 exists in r1 and r2: ambiguous
        label("d1", "shadow", "r2", correct=True, target_box=[0, 0, 5, 5]),   # r2's shadow click has no point: a miss
        label("d9", "primary", correct=True),                             # no such decision
        label("d1", "primary", "r9", correct=True)])                      # no such run
    p, s = side(doc, "primary", "anthropic"), side(doc, "shadow", "kimi")
    assert doc["runs"] == 2 and doc["labels"] == 1 and doc["labels_left_out"] == {"ambiguous": 1, "unknown": 2}
    assert p["decisions"] == 7 and s["decisions"] == 5                    # nothing collapsed by a repeated id
    assert (s["labelled"], s["clicks_labelled"], s["clicks_unscorable"], s["click_in_target_rate"]) == (1, 1, 1, 0.0)
    c = doc["coverage"]
    assert (c["decisions"], c["with_shadow_row"], c["with_skip_row"]) == (6, 5, 1)   # r1's d4 skip; r2's d1, d2 rows
    one = SR.report(rows(), [label("d1", "primary", correct=True)])       # a single run: the legacy label is used
    assert one["labels"] == 1 and one["labels_left_out"] == {}


def test_the_command_reads_rotated_files_and_labels_and_prints_json(tmp_path, capsys):
    d = tmp_path / "streamer"
    d.mkdir()
    r = rows()
    rotated = d / "events.20261024T100000.000001Z-1.jsonl"
    rotated.write_text("".join(json.dumps(x) + "\n" for x in r[:4]))
    os.utime(rotated, (T0 + 4, T0 + 4))                                    # last written inside the window
    (d / "events.jsonl").write_text("".join(json.dumps(x) + "\n" for x in r[4:]) + "not json\n")
    (tmp_path / "labels.jsonl").write_text(json.dumps({"decision_id": "d1", "who": "primary", "correct": True}) + "\n"
                                           + json.dumps({"decision_id": "d2", "who": "nobody", "correct": True}) + "\n")
    assert SR.main(["--streamer-dir", str(d), "--since", str(T0 - 1), "--labels", str(tmp_path / "labels.jsonl"), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["labels"] == 1 and side(doc, "primary", "anthropic")["decisions"] == 5 and doc["coverage"]["decisions"] == 4
    assert SR.main(["--streamer-dir", str(d), "--since", str(T0 - 1)]) == 0
    out = capsys.readouterr().out
    assert "shadow trial report (0 labels" in out and "primary anthropic" in out and "coverage: 3 shadow rows + 1 logged skips" in out
