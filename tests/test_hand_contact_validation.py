"""Independent CPU-only checks for desk hand contact: reference two-bone solver,
validator of solved poses, and facts of the captured typing clip."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import hand_contact_validation as h  # noqa: E402

CLIP_PATH = ROOT / "web/house/assets/first-person/typing.glb"


@pytest.fixture(scope="module")
def clip():
    return h.Clip(CLIP_PATH)


def arm_points(pose, hand):
    return [pose.p(b) for b in h.chain(hand)]


def test_captured_clip_facts(clip):
    assert abs(clip.duration - 16.46667) < 1e-4
    whole = h.analyze(clip, 0.0, clip.duration)
    for hand in ("Left", "Right"):
        assert whole["hands"][hand]["moving_finger_joints_gt_2deg"] == 15, "genuine activity in both hands"
    ratio = whole["hands"]["Right"]["wrist_path_cm"] / whole["hands"]["Left"]["wrist_path_cm"]
    assert 6.4 < ratio < 6.9, ratio
    segment = h.analyze(clip, 3.0, 8.0, keytop_y=87.38976)
    assert segment["seamless_loop"] is False, "3-8 s must be played once, not looped naively"
    assert 11.0 < segment["hands"]["Right"]["endpoint_gap_cm"]["index_tip"] < 13.0
    for hand in ("Left", "Right"):
        assert segment["hands"][hand]["moving_finger_joints_gt_2deg"] == 15


def test_left_elbow_is_nearly_straight_while_typing(clip):
    """Finding: during 3-8 s the captured left elbow stays at ~3.6 deg of bend with
    ~0.26 mm of reach slack, so a non-stretch IK cannot lower that wrist at all."""
    for t in np.arange(3.0, 8.0, 0.25):
        S, E, W = arm_points(clip.pose(t), "Left")
        bend = np.degrees(np.arccos(np.dot(E - S, W - E) / np.linalg.norm(E - S) / np.linalg.norm(W - E)))
        assert bend < 4.0
        assert np.linalg.norm(E - S) + np.linalg.norm(W - E) - np.linalg.norm(W - S) < 0.05
    pose = clip.pose(5.0)
    lowered = h.solve_two_bone(pose, "Left", pose.p("LeftHand") + np.array([0, -2.0, 0]))
    assert lowered["reachable"] is False


@pytest.mark.parametrize("hand", ["Left", "Right"])
@pytest.mark.parametrize("time", [3.0, 4.7, 6.2, 8.0])
def test_identity_target_reproduces_the_captured_pose(clip, hand, time):
    pose = clip.pose(time)
    result = h.solve_two_bone(pose, hand, pose.p(f"{hand}Hand"))
    assert result["reachable"]
    for name, q in result["rotations"].items():
        assert h.qangle(q, pose.local_r[clip.index(name)]) < 0.01, name
    ok, report, _ = h.validate(clip, time, hand, result["rotations"], pose.p(f"{hand}Hand"))
    assert ok, report


@pytest.mark.parametrize("hand", ["Left", "Right"])
def test_reachable_targets_keep_lengths_orientation_fingers_and_elbow_side(clip, hand):
    for time in (3.0, 5.5, 8.0):
        pose = clip.pose(time)
        S, E, W = arm_points(pose, hand)
        inward = (S - W) / np.linalg.norm(S - W)
        for target in (W + inward * 3.0, W + inward * 8.0 + np.array([0, -3.0, 1.0])):
            result = h.solve_two_bone(pose, hand, target)
            assert result["reachable"]
            assert all(np.all(np.isfinite(q)) for q in result["rotations"].values())
            ok, report, _ = h.validate(clip, time, hand, result["rotations"], target)
            assert ok, report
            assert report["wrist_reaches_target"]["value"] < 1e-3
            assert report["hand_world_orientation"]["value"] < 1e-3
            assert report["finger_local_quaternions_retained"]["value"] == 0


@pytest.mark.parametrize("hand", ["Left", "Right"])
def test_unreachable_targets_never_stretch_and_stay_finite(clip, hand):
    pose = clip.pose(6.0)
    S, E, W = arm_points(pose, hand)
    for target in (S + (W - S) * 3.0, S + np.array([0, 0, 0.001])):
        result = h.solve_two_bone(pose, hand, target)
        assert result["reachable"] is False
        ok, report, _ = h.validate(clip, 6.0, hand, result["rotations"], target)
        assert ok, report
    with pytest.raises(ValueError):
        h.solve_two_bone(pose, hand, [np.nan, 0, 0])


def test_bend_plane_is_continuous_over_the_segment(clip):
    for hand in ("Left", "Right"):
        previous = None
        for time in [t for t in clip.frame_times if 3.0 <= t <= 8.0]:
            pose = clip.pose(time)
            S, E, W = arm_points(pose, hand)
            target = W + (S - W) / np.linalg.norm(S - W) * 4.0
            result = h.solve_two_bone(pose, hand, target, pole_hint=previous)
            ok, report, normal = h.validate(clip, time, hand, result["rotations"], target, previous_normal=previous)
            assert ok, (time, report)
            if previous is not None:
                assert np.dot(normal, previous) > 0, "no elbow flip between frames"
            previous = normal


def test_validator_rejects_wrong_solutions(clip):
    time, hand = 5.0, "Right"
    pose = clip.pose(time)
    S, E, W = arm_points(pose, hand)
    target = W + (S - W) / np.linalg.norm(S - W) * 5.0
    good = h.solve_two_bone(pose, hand, target)["rotations"]

    finger = dict(good, **{"mixamorig:RightHandIndex2": [0.0, 0.0, 0.2588, 0.9659]})
    ok, report, _ = h.validate(clip, time, hand, finger, target)
    assert not ok and not report["finger_rotations_not_overridden"]["ok"]

    stale_hand = dict(good, **{"mixamorig:RightHand": pose.local_r[clip.index("RightHand")].tolist()})
    ok, report, _ = h.validate(clip, time, hand, stale_hand, target)
    assert not ok and not report["hand_world_orientation"]["ok"], "hand orientation must stay in world space"

    untouched = {n: pose.local_r[clip.index(n)].tolist() for n in good}
    ok, report, _ = h.validate(clip, time, hand, untouched, target)
    assert not ok and not report["wrist_reaches_target"]["ok"]

    # Mirror the elbow to the other side of the shoulder-target axis.
    axis = (target - S) / np.linalg.norm(target - S)
    flipped = h.qnorm(np.append(axis * np.sin(np.pi / 2), np.cos(np.pi / 2)))
    parent_q = clip.pose(time)._world(clip.parent[clip.index("RightArm")])[1]
    arm_world = h.qmul(parent_q, np.array(good["mixamorig:RightArm"]))
    mirrored = dict(good, **{"mixamorig:RightArm": h.qmul(h.qinv(parent_q), h.qmul(flipped, arm_world)).tolist()})
    ok, report, _ = h.validate(clip, time, hand, mirrored, target)
    assert not ok and not report["elbow_side_of_captured_bend"]["ok"]

    ok, report, _ = h.validate(clip, time, hand, dict(good, **{"mixamorig:RightForeArm": [np.nan, 0, 0, 1]}), target)
    assert not ok and not report["finite"]["ok"]


def test_cli_validates_a_renderer_json_contract(clip, tmp_path, capsys):
    frames = []
    for time in (3.0, 3.5, 4.0):
        pose = clip.pose(time)
        S, E, W = arm_points(pose, "Left")
        target = W + (S - W) / np.linalg.norm(S - W) * 3.0
        rotations = h.solve_two_bone(pose, "Left", target)["rotations"]
        frames.append({"time": time, "target": target.tolist(),
                       "local_rotations": {k: v.tolist() for k, v in rotations.items()}})
    path = tmp_path / "solved.json"
    path.write_text(json.dumps({"hand": "Left", "frames": frames}))
    assert h.main(["validate", str(CLIP_PATH), str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    frames[1]["local_rotations"]["mixamorig:LeftHandIndex1"] = [0, 0, 0, 1]
    path.write_text(json.dumps({"hand": "Left", "frames": frames}))
    assert h.main(["validate", str(CLIP_PATH), str(path)]) == 1
