"""CPU-only finger rig/animation diagnostics on the real first-person assets
(tools/animation_rig_audit.py): rest/bind data, axis conventions, the current
retarget's effect, the rejected bind-referenced variant and the rest-only
local-frame candidate.  No renderer; joint/skin data only."""

import copy
import json
import math
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import animation_rig_audit as audit  # noqa: E402
from hand_contact_validation import qinv, qmul, qnorm  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node decodes the meshopt-compressed skin")
NON_THUMB = ("Index", "Middle", "Ring", "Pinky")


@pytest.fixture(scope="module")
def report():
    return audit.build_report(step=10)


@pytest.fixture(scope="module")
def rigs():
    target = audit.Rig(audit.load(audit.TARGET))
    typing = audit.load_clip(audit.CLIPS["typing"])
    return target, typing


def axis_angle(axis, degrees):
    axis = np.asarray(axis, float) / np.linalg.norm(axis)
    h = math.radians(degrees) / 2
    return np.append(axis * math.sin(h), math.cos(h))


def test_owner_is_target_and_capture_rest_equals_target_rest(report):
    assert report["owner_identical_to_target"] is True
    for name, row in report["source_rest_vs_target_rest"].items():
        assert row["max_rotation_deg"] < 1e-6 and row["max_translation_cm"] < 1e-6, name
        assert row["alignment_deg"] < 1e-4, name
    original = report["original_capture_vs_staged_typing"]
    assert original["max_rest_rotation_deg"] < 1e-6
    assert original["max_finger_local_diff_deg"] < 1e-3, "staged typing fingers are the original capture"


def test_skin_bind_differs_from_reference_only_by_knuckle_flexion(report):
    assert report["ibm_min_determinant"] > 0, "no mirrored inverse bind matrix"
    for name, j in report["finger_joints"].items():
        assert j["bind_translation_diff_cm"] < 1e-3, name
        level = int(name[-1])
        if "Thumb" in name:
            assert j["bind_vs_rest_deg"] < 5.0, name
        elif level == 1:
            assert 40.0 < j["bind_vs_rest_deg"] < 66.0, name
            assert j["bind_flexion_deg"] > 0.9 * j["bind_vs_rest_deg"], "bind delta is flexion toward the palm"
            assert abs(j["bind_roll_about_bone_deg"]) < 2.5, name
        else:
            assert j["bind_vs_rest_deg"] < 0.1, name
    assert report["rest_vs_bind_nonfinger_deg"]["LeftArm"] > 60, "skin bind is the modelled arms-down pose"


def test_finger_axis_conventions(report):
    for name, j in report["finger_joints"].items():
        assert j["bone_axis_vs_plus_y_deg"] < 10.0, name
        if not any(f in name for f in NON_THUMB):
            continue
        assert abs(j["bend_axis_local"][0]) > 0.89, name
        assert j["bend_axis_local"][0] > 0, "positive local X rotation flexes toward the palm"
        assert j["bend_axis_explained"] > 0.85, name


def test_current_retarget_adds_no_contraction(report):
    for clip, fingers in report["contraction"].items():
        for finger, m in fingers.items():
            src = m["source_joints"]["curl_deg_mean"]
            assert abs(m["current_joints"]["curl_deg_mean"] - src) < 1e-4, (clip, finger)
            assert abs(m["current_skinned"]["curl_deg_mean"] - src) < 1e-3, (clip, finger)  # float32 IBMs
            assert abs(m["current_skinned"]["tip_reach_ratio_mean"] - m["source_joints"]["tip_reach_ratio_mean"]) < 1e-5


def test_bind_referenced_variant_double_applies_knuckle_curl(report):
    for finger in NON_THUMB:
        for hand in audit.HANDS:
            m = report["contraction"]["typing"][hand + finger]
            assert m["bind_reference_skinned"]["curl_deg_mean"] - m["source_joints"]["curl_deg_mean"] > 40.0, hand + finger


def test_left_typing_capture_is_clawed_not_retarget_induced(report):
    joints = report["finger_joints"]
    for finger in NON_THUMB:
        mcp = joints[f"LeftHand{finger}1"]["typing_3_8s"]["mean"]
        interphalangeal = joints[f"LeftHand{finger}2"]["typing_3_8s"]["mean"] + joints[f"LeftHand{finger}3"]["typing_3_8s"]["mean"]
        assert mcp < 12.0, finger
        assert interphalangeal > 50.0, finger
        assert interphalangeal > 4 * mcp, "hooked fingers from almost straight knuckles"
        assert joints[f"LeftHand{finger}2"]["typing_3_8s"]["fraction_outside_anatomy"] == 0.0
    right_mcp = [joints[f"RightHand{f}1"]["typing_3_8s"]["mean"] for f in NON_THUMB]
    assert min(right_mcp) > 15.0, "right hand keeps knuckle flexion; hands differ in the capture itself"


def test_candidate_is_identity_on_real_assets_and_preserves_capture(report, rigs):
    target, typing = rigs
    frames = audit.frame_alignments(typing.rig, target)
    assert len(frames) == 30
    assert max(audit.qangle(a, audit.IDENTITY) for a in frames.values()) < 1e-4
    for finger, m in report["contraction"]["typing"].items():
        assert abs(m["candidate_skinned"]["curl_deg_mean"] - m["source_joints"]["curl_deg_mean"]) < 1e-3, finger


def perturbed(target, rolls):
    """Target whose hand reference poses are rolled about each hand's own bone axis (per hand)."""
    rig = copy.copy(target)
    rig.r = [q.copy() for q in target.r]
    for hand, degrees in rolls.items():
        i = rig.idx(hand + "Hand")
        axis = rig.t[rig.idx(hand + "HandMiddle1")]
        rig.r[i] = qnorm(qmul(rig.r[i], axis_angle(axis, degrees)))
    rig.rest = rig.world(rig.r)
    return rig


def flexion_error(src, tgt, src_r, tgt_r, frames):
    """Max angle between each finger joint's local delta from its own rest and the frame-mapped source delta."""
    worst = 0.0
    for name, a in frames.items():
        si, ti = src.idx(name), tgt.idx(name)
        expected = qmul(qmul(a, qmul(qinv(src.r[si]), src_r[si])), qinv(a))
        worst = max(worst, audit.qangle(qmul(qinv(tgt.r[ti]), tgt_r[ti]), expected))
    return worst


def test_candidate_preserves_local_flexion_where_world_delta_does_not(rigs):
    target, typing = rigs
    tgt = perturbed(target, {"Left": 25.0, "Right": -15.0})
    frames = audit.frame_alignments(typing.rig, tgt)
    assert max(audit.qangle(a, audit.IDENTITY) for a in frames.values()) < 1e-4, "rolled hand carries its fingers"
    world_errors, candidate_errors = [], []
    for k in range(60, len(typing.times), 60):
        r, t = typing.local(k)
        cand_r, cand_w = audit.retarget_local_candidate(typing.rig, tgt, r, t, frames=frames)
        cur_r, _ = audit.retarget_world_delta(typing.rig, tgt, r, t)
        candidate_errors.append(flexion_error(typing.rig, tgt, r, cand_r, frames))
        world_errors.append(flexion_error(typing.rig, tgt, r, cur_r, frames))
        assert all(np.all(np.isfinite(m)) for m in cand_w.values())
    assert max(candidate_errors) < 1e-4
    assert max(world_errors) > 5.0, "world delta bends fingers about the source's world axis, off the rolled palm"


def test_hands_are_independent_and_not_mirrored(rigs):
    target, typing = rigs
    r, t = typing.local(150)
    base_r, _ = audit.retarget_local_candidate(typing.rig, target, r, t)
    left_only = perturbed(target, {"Left": 30.0})
    left_r, _ = audit.retarget_local_candidate(typing.rig, left_only, r, t)
    for name in audit.finger_joint_names("Right"):
        i = target.idx(name)
        assert audit.qangle(base_r[i], left_r[i]) < 1e-9, "changing the left hand must not touch the right"
    # each hand keeps its own captured motion: left and right local rotations are not mirror copies
    diffs = [audit.qangle(base_r[target.idx(f"LeftHand{f}2")], base_r[target.idx(f"RightHand{f}2")]) for f in NON_THUMB]
    assert max(diffs) > 5.0


def test_candidate_cli_writes_finite_json_outside_repository():
    with tempfile.TemporaryDirectory() as tmp:
        out = audit.main(["candidate", "--output", str(Path(tmp) / "candidate.json")])
        data = json.loads(Path(out).read_text())
    assert ROOT not in Path(out).resolve().parents
    assert len(data["joints"]) == 30 and set(data["joints"]["LeftHandIndex1"]) == {"typing", "walking", "texting"}
    for row in data["joints"].values():
        for entry in row.values():
            assert all(math.isfinite(x) for x in entry["A_xyzw"])
    default = Path(tempfile.gettempdir())
    assert ROOT not in default.resolve().parents


# ---------------------------------------------------------------- capture window search
@pytest.fixture(scope="module")
def segments():
    return audit.scan_segments()


def test_segment_scan_inputs_and_duplicates(segments):
    inputs = segments["inputs"]
    assert inputs["room_mx_typing"]["duplicate_of"] == "typing", "staged typing is the original capture's motion"
    assert "skipped" in inputs["room_mx_sit_to_type"] and "skipped" in inputs["room_mx_type_to_sit"]
    assert segments["windows_scored"] == 1440


def finite(x):
    if isinstance(x, dict):
        return all(finite(v) for v in x.values())
    if isinstance(x, list):
        return all(finite(v) for v in x)
    return not isinstance(x, float) or math.isfinite(x)


def test_segment_scores_are_finite_bounded_and_deterministic(segments):
    again = audit.scan_segments()
    assert json.dumps(audit.to_jsonable(again["top"])) == json.dumps(audit.to_jsonable(segments["top"]))
    for w in segments["top"]:
        assert finite(w) and 0.0 <= w["score"] <= 1.0
    scores = [w["score"] for w in segments["top"]]
    assert scores == sorted(scores, reverse=True)


def test_three_to_eight_seconds_is_flagged_for_left_hook_and_locked_elbow(segments):
    ref = segments["reference_3_8s"]["typing"]
    left = ref["hands"]["Left"]
    assert "Left hook" in ref["flags"] and "left elbow nearly straight-locked" in ref["flags"]
    assert left["ip_to_l1_ratio"] > audit.HOOK_RATIO
    assert left["elbow_bend_range_deg"] < 1.0 and left["elbow_bend_mean_deg"] < 5.0
    assert ref["hands"]["Right"]["moving_finger_joints_gt_2deg"] == 15 == left["moving_finger_joints_gt_2deg"]
    assert ref["rank"] > ref["of"] // 2, "3-8 s is in the worse half of the captured windows"
    assert segments["top"][0]["score"] > ref["score"]


def test_no_typing_window_is_free_of_a_left_hook_with_a_bending_elbow(segments):
    """Fact of the existing capture: better windows exist, but none removes the left hook."""
    assert segments["windows_without_flags"] == 0
    for w in segments["least_left_hook_with_bending_elbow"]:
        assert w["hands"]["Left"]["elbow_bend_range_deg"] >= audit.ELBOW_MIN_RANGE
        assert w["hands"]["Left"]["hooked"]
