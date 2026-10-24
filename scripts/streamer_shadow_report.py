#!/usr/bin/env python3
"""SUB-01 shadow trial report (plan step 5; docs/streamer/kimi/cutover.md, decision 2): the primary decision model and
the Kimi shadow compared on the same decisions, from the agent's append-only audit, for the 30-minute trial.

    python3 scripts/streamer_shadow_report.py --streamer-dir /home/unreal/.sub01-private/streamer --since-min 30 \\
        [--labels labels.jsonl] [--json]

Per provider and side (primary or shadow): decisions, latency p50/p95/max, errors and timeouts, JSON validity
(`parse_valid`: a JSON object came back; `valid`: nothing was dropped from its action), clicks, click_in_target
(labelled target boxes only), correct actions (labelled only), total cost and cost per correct action. Without labels
correctness, click_in_target and cost per correct action are null, never zero. Agreement as the agent logged it, with
both-null decisions counted apart; coverage: decisions with a shadow row or a logged skip. It reads events.jsonl and the
rotated events.*.jsonl files. It makes no promotion decision: a person reads it next to the labelled frames.

Decisions are keyed by (run, decision_id): decision ids restart at d1 in every run of the agent.

Labels, one JSON object per line, written by a person from the logged frames:
    {"run": "1a2b3c4d", "decision_id": "d12", "who": "primary" | "shadow", "correct": true | false,
     "target_box": [x, y, w, h]}
`target_box` (optional) is the correct click target in the pixels of the screenshot the models saw; a labelled click
whose point cannot be read counts as a miss (and is reported as unscorable). A label without `run` counts only when one
run of the window has that decision id; otherwise it is left out as ambiguous (reported).
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from streamer_agent_checks import Audit  # noqa: E402

POINT = re.compile(r"@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)|^\[(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)\]$")


def percentile(values, q):
    v = sorted(x for x in values if isinstance(x, (int, float)))
    if not v:
        return None
    return v[min(len(v) - 1, max(0, math.ceil(q / 100 * len(v)) - 1))]


def point_of(target, action=None):
    """A click's point from a logged target ("mark 3 @1100,125", "[640, 360]") or from the action itself."""
    if isinstance(action, dict) and action.get("action") == "click" and isinstance(action.get("point"), list):
        p = action["point"]
        if len(p) == 2 and all(isinstance(x, (int, float)) for x in p):
            return float(p[0]), float(p[1])
    m = POINT.search(str(target or ""))
    if not m:
        return None
    a, b = (m.group(1), m.group(2)) if m.group(1) is not None else (m.group(3), m.group(4))
    return float(a), float(b)


def inside(pt, box):
    return pt is not None and isinstance(box, list) and len(box) == 4 and \
        box[0] <= pt[0] <= box[0] + box[2] and box[1] <= pt[1] <= box[1] + box[3]


def dkey(r):
    """A decision's identity: (run, decision_id). Decision ids restart at d1 in every run of the agent (Kimi review); a
    skip row reconciled by a later run names the decision's own run in `decision_run`."""
    return (r.get("decision_run") or r.get("run"), r.get("decision_id"))


def read_labels(path):
    """-> the label rows (decision_id, who, optional run); report() resolves each one to a decision of the window."""
    out = []
    if not path:
        return out
    for ln in Path(path).read_text().splitlines():
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        if isinstance(d, dict) and d.get("who") in ("primary", "shadow") and isinstance(d.get("decision_id"), str):
            out.append(d)
    return out


def resolve_labels(raw, keys):
    """Each label -> (decision key, who). A label names its `run`; a legacy label without one counts only when exactly
    one run of the window has that decision id; otherwise it is ambiguous and left out (both reported, Kimi review)."""
    runs = collections.defaultdict(set)
    for run, did in keys:
        runs[did].add(run)
    out, left = {}, collections.Counter()
    for d in raw:
        did = d["decision_id"]
        if isinstance(d.get("run"), str) and d["run"]:
            k = (d["run"], did)
            if k not in keys:
                left["unknown"] += 1
                continue
        elif len(runs.get(did, ())) == 1:
            k = (next(iter(runs[did])), did)
        else:
            left["ambiguous" if runs.get(did) else "unknown"] += 1
            continue
        out[(k, d["who"])] = d
    return out, dict(left)


def side_stats(entries, labels, who):
    """entries: [{key, latency_ms, error, parse_valid, valid, kind, point, cost_usd}] of one provider on one side."""
    lat = [e["latency_ms"] for e in entries if isinstance(e["latency_ms"], (int, float))]   # an unparsable answer: none
    clicks = [e for e in entries if e["kind"] == "click"]
    lab = [(e, labels[(e["key"], who)]) for e in entries if (e["key"], who) in labels]
    boxed = [(e, lb) for e, lb in lab if e["kind"] == "click" and isinstance(lb.get("target_box"), list)]
    in_target = [inside(e["point"], lb["target_box"]) for e, lb in boxed]   # no point: a miss (Kimi review)
    correct = sum(1 for _, lb in lab if lb.get("correct") is True)
    cost_lab = sum(e["cost_usd"] or 0.0 for e, _ in lab)
    n = len(entries)
    return {"decisions": n, "latency_ms": {"p50": percentile(lat, 50), "p95": percentile(lat, 95), "max": max(lat) if lat else None},
            "errors": sum(1 for e in entries if e["error"] and e["error"] != "timeout"),
            "timeouts": sum(1 for e in entries if e["error"] == "timeout"),
            "parse_valid_rate": round(sum(1 for e in entries if e["parse_valid"]) / n, 3) if n else None,
            "valid_rate": round(sum(1 for e in entries if e["valid"]) / n, 3) if n else None,
            "clicks": len(clicks), "clicks_labelled": len(in_target),
            "clicks_unscorable": sum(1 for e, _ in boxed if e["point"] is None),
            "click_in_target_rate": round(sum(in_target) / len(in_target), 3) if in_target else None,
            "labelled": len(lab), "correct": correct if lab else None,
            "cost_usd": round(sum(e["cost_usd"] or 0.0 for e in entries), 6),
            "cost_per_correct_usd": round(cost_lab / correct, 6) if lab and correct else None}


def report(rows, labels=None):
    """labels: the rows of read_labels()."""
    decisions = {dkey(r): r for r in rows if r.get("kind") == "decision" and r.get("decision_id")}
    raws = [r for r in rows if r.get("kind") == "decision_raw"]
    shadows = {dkey(r): r for r in rows if r.get("kind") == "shadow_decision" and r.get("decision_id")}
    skipped = collections.Counter(r.get("why") for r in rows if r.get("kind") == "shadow_skipped")
    skipped_keys = {dkey(r) for r in rows if r.get("kind") == "shadow_skipped"}
    labels, left_out = resolve_labels(labels or [], set(decisions) | set(shadows) | {dkey(r) for r in raws})
    sides = collections.defaultdict(list)
    for k, d in decisions.items():
        a, s = d.get("action") if isinstance(d.get("action"), dict) else None, shadows.get(k) or {}
        sides[("primary", d.get("provider") or "?")].append({
            "key": k, "latency_ms": d.get("latency_ms"), "error": None, "parse_valid": True,
            "valid": not any(str(x).startswith("action:") for x in d.get("dropped") or []),
            "kind": (a or {}).get("action"), "point": point_of(s.get("primary_target"), a), "cost_usd": d.get("cost_usd")})
    for r in raws:                                            # an answer without a JSON object: a decision that failed
        sides[("primary", r.get("provider") or "?")].append({
            "key": dkey(r), "latency_ms": None, "error": "unparsable", "parse_valid": False,
            "valid": False, "kind": None, "point": None, "cost_usd": None})
    for k, s in shadows.items():
        sides[("shadow", s.get("provider") or "?")].append({
            "key": k, "latency_ms": s.get("latency_ms"), "error": s.get("error"),
            "parse_valid": bool(s.get("parse_valid")), "valid": bool(s.get("valid")), "kind": s.get("shadow_kind"),
            "point": point_of(s.get("target")), "cost_usd": s.get("cost_usd")})
    compared = [s for s in shadows.values() if s.get("agree_kind") is not None]
    both_null = sum(1 for s in compared if s.get("both_null"))
    agree = sum(1 for s in compared if s.get("agree"))
    covered = sum(1 for k in decisions if k in shadows or k in skipped_keys)
    return {"schema": "sub01.shadow-report.v1", "labels": len(labels), "labels_left_out": left_out,
            "runs": len({k[0] for k in decisions}),
            "sides": [{"side": side, "provider": prov, **side_stats(es, labels, side)} for (side, prov), es in sorted(sides.items())],
            "agreement": {"compared": len(compared), "agree": agree, "both_null": both_null,
                          "agree_rate": round(agree / len(compared), 3) if compared else None,
                          "agree_rate_acting": (round((agree - both_null) / (len(compared) - both_null), 3)
                                                if len(compared) > both_null else None)},
            "coverage": {"decisions": len(decisions), "with_shadow_row": sum(1 for k in decisions if k in shadows),
                         "with_skip_row": sum(1 for k in decisions if k in skipped_keys and k not in shadows),
                         "accounted_rate": round(covered / len(decisions), 3) if decisions else None,
                         "skipped": dict(skipped)}}


def text(doc):
    lines = [f"shadow trial report ({doc['labels']} labels, left out {doc['labels_left_out'] or 'none'}; {doc['runs']} "
             "agent runs; null = not labelled / not measurable)"]
    for s in doc["sides"]:
        lines.append(f"  {s['side']:7} {s['provider']:10} decisions {s['decisions']:4}  latency p50/p95/max "
                     f"{s['latency_ms']['p50']}/{s['latency_ms']['p95']}/{s['latency_ms']['max']} ms  errors {s['errors']} "
                     f"timeouts {s['timeouts']}  parse_valid {s['parse_valid_rate']} valid {s['valid_rate']}  clicks "
                     f"{s['clicks']} in_target {s['click_in_target_rate']}  correct {s['correct']}/{s['labelled']}  cost "
                     f"${s['cost_usd']} per correct {s['cost_per_correct_usd']}")
    a, c = doc["agreement"], doc["coverage"]
    lines.append(f"  agreement: {a['agree']}/{a['compared']} (rate {a['agree_rate']}, acting {a['agree_rate_acting']}, "
                 f"both null {a['both_null']})")
    lines.append(f"  coverage: {c['with_shadow_row']} shadow rows + {c['with_skip_row']} logged skips of {c['decisions']} "
                 f"decisions (accounted {c['accounted_rate']}), skips {c['skipped']}")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--streamer-dir", default="/home/unreal/.sub01-private/streamer")
    p.add_argument("--since-min", type=float, default=30.0, help="the window: the last N minutes")
    p.add_argument("--since", type=float, default=None, help="the window's start as a unix time (wins over --since-min)")
    p.add_argument("--labels", default=None, help="JSONL labels written by a person")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    since = a.since if a.since is not None else time.time() - a.since_min * 60
    doc = report(Audit(a.streamer_dir).rows(since), read_labels(a.labels))
    print(json.dumps(doc, indent=1) if a.json else text(doc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
