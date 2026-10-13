#!/usr/bin/env python3
"""Independent CPU-only reference checks for desk hand contact (no renderer).

A second, independent implementation of the math the native renderer's
contact IK must satisfy, so its output can be validated against data rather
than against itself:

* a non-stretching two-bone (upper arm -> forearm -> wrist) solver that keeps
  the original bone lengths, keeps the elbow on the side of its original bend
  plane (pole from the captured elbow), keeps the captured hand orientation in
  world space and never touches finger joints;
* a validator for any solved pose (ours or the renderer's) against the
  captured pose: lengths, finger local quaternions, hand world orientation,
  wrist error / reach, bend-plane continuity, finiteness;
* clip analysis of the captured typing clip: per-hand finger activity, wrist
  path, segment endpoint gaps (is it loopable?) and joint-only index-tip
  footprint / keytop statistics.

It reads the captured glTF animation (uncompressed accessors) in armature
space (centimetres, the root node's scale excluded). Joint positions alone
cannot prove skin contact: finger-pad penetration needs the renderer's skinned
vertices; this module reports joint-only numbers and labels them as such.

Usage:
  python tools/hand_contact_validation.py analyze CLIP.glb [--start 3 --end 8]
        [--keytop-y 87.38976] [--keyboard X0,X1,Z0,Z1]
  python tools/hand_contact_validation.py self-test CLIP.glb [--start 3 --end 8]
  python tools/hand_contact_validation.py validate CLIP.glb SOLVED.json
SOLVED.json: {"hand": "Left"|"Right", "frames": [{"time": s, "target": [x,y,z]|null,
  "local_rotations": {"mixamorig:LeftArm": [x,y,z,w], ...}}]}  (armature space, cm;
  bones not listed keep their captured rotation).
"""

import argparse
import json
import math
import struct
import sys
from pathlib import Path

import numpy as np

PREFIX = "mixamorig:"
FINGERS = ("Thumb", "Index", "Middle", "Ring", "Pinky")
EPS = 1e-9


# ---------------------------------------------------------------- quaternions (x, y, z, w)
def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return np.array([aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw,
                     aw * bw - ax * bx - ay * by - az * bz])


def qinv(q):
    return np.array([-q[0], -q[1], -q[2], q[3]]) / max(np.dot(q, q), EPS)


def qnorm(q):
    return q / max(np.linalg.norm(q), EPS)


def qrot(q, v):
    return qmul(qmul(q, np.array([v[0], v[1], v[2], 0.0])), qinv(q))[:3]


def slerp(a, b, t):
    d = float(np.dot(a, b))
    if d < 0:
        b, d = -b, -d
    if d > 0.9995:
        return qnorm(a + t * (b - a))
    theta = math.acos(min(1.0, d))
    return (math.sin((1 - t) * theta) * a + math.sin(t * theta) * b) / math.sin(theta)


def qangle(a, b):
    """Angle in degrees between two orientations (sign-insensitive)."""
    return math.degrees(2 * math.acos(min(1.0, abs(float(np.dot(qnorm(a), qnorm(b)))))))


def from_matrix(m):
    t = np.trace(m)
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        q = [(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, 0.25 * s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = [0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s, (m[2, 1] - m[1, 2]) / s]
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = [(m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s, (m[0, 2] - m[2, 0]) / s]
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = [(m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s, (m[1, 0] - m[0, 1]) / s]
    return qnorm(np.array(q))


def frame(direction, normal):
    """Orthonormal basis (columns) from a bone direction and its bend-plane normal."""
    u = direction / np.linalg.norm(direction)
    n = normal - np.dot(normal, u) * u
    n /= np.linalg.norm(n)
    return np.column_stack([u, n, np.cross(u, n)])


# ---------------------------------------------------------------- captured clip
class Clip:
    def __init__(self, path):
        raw = Path(path).read_bytes()
        if raw[:4] != b"glTF" or struct.unpack_from("<I", raw, 4)[0] != 2:
            raise ValueError("Not a glTF 2 binary")
        doc = binary = None
        offset = 12
        while offset < len(raw):
            size, kind = struct.unpack_from("<II", raw, offset)
            chunk = raw[offset + 8: offset + 8 + size]
            if kind == 0x4E4F534A:
                doc = json.loads(chunk)
            elif kind == 0x004E4942:
                binary = chunk
            offset += 8 + size
        if "EXT_meshopt_compression" in (doc.get("extensionsUsed") or []):
            raise ValueError("Compressed clip: decode it first (tools/uncompress_unreal_glb.mjs)")
        self.doc, self.bin = doc, binary
        self.nodes = doc["nodes"]
        self.names = {n.get("name"): i for i, n in enumerate(self.nodes)}
        self.parent = {c: i for i, n in enumerate(self.nodes) for c in n.get("children", [])}
        self.rest_t = [np.array(n.get("translation", [0, 0, 0]), float) for n in self.nodes]
        self.rest_r = [qnorm(np.array(n.get("rotation", [0, 0, 0, 1]), float)) for n in self.nodes]
        root = doc["scenes"][doc.get("scene", 0)]["nodes"][0]
        self.root = root  # armature node; its scale (0.01) is excluded: armature space is cm
        animation = doc["animations"][0]
        self.channels = {}
        for channel in animation["channels"]:
            sampler = animation["samplers"][channel["sampler"]]
            if sampler.get("interpolation", "LINEAR") != "LINEAR":
                raise ValueError("Only LINEAR captured channels are supported")
            times = self._accessor(sampler["input"])[:, 0]
            self.channels[(channel["target"]["node"], channel["target"]["path"])] = (times, self._accessor(sampler["output"]))
        self.duration = max(times[-1] for times, _ in self.channels.values())
        self.frame_times = sorted({float(t) for times, _ in self.channels.values() for t in times})

    def _accessor(self, index):
        a = self.doc["accessors"][index]
        view = self.doc["bufferViews"][a["bufferView"]]
        width = {"SCALAR": 1, "VEC3": 3, "VEC4": 4}[a["type"]]
        if a["componentType"] != 5126:
            raise ValueError("Float accessors required")
        stride = view.get("byteStride", width * 4)
        start = view.get("byteOffset", 0) + a.get("byteOffset", 0)
        out = np.array([struct.unpack_from("<" + "f" * width, self.bin, start + i * stride) for i in range(a["count"])], float)
        if not np.all(np.isfinite(out)):
            raise ValueError("Non-finite captured data")
        return out

    def index(self, bone):
        name = bone if bone in self.names else PREFIX + bone
        return self.names[name]

    def local(self, time):
        """Captured local (translation, rotation) of every node at `time`."""
        t_out = [v.copy() for v in self.rest_t]
        r_out = [v.copy() for v in self.rest_r]
        for (node, path), (times, values) in self.channels.items():
            k = int(np.searchsorted(times, time, side="right"))
            if k <= 0:
                value = values[0]
            elif k >= len(times):
                value = values[-1]
            else:
                f = (time - times[k - 1]) / max(times[k] - times[k - 1], EPS)
                value = slerp(qnorm(values[k - 1]), qnorm(values[k]), f) if path == "rotation" \
                    else values[k - 1] + f * (values[k] - values[k - 1])
            if path == "rotation":
                r_out[node] = qnorm(np.array(value))
            elif path == "translation":
                t_out[node] = np.array(value)
        return t_out, r_out

    def pose(self, time, rotations=None):
        """Armature-space world positions/orientations (cm); optional local rotation overrides."""
        t, r = self.local(time)
        for name, q in (rotations or {}).items():
            r[self.index(name)] = qnorm(np.array(q, float))
        return Pose(self, t, r)


class Pose:
    def __init__(self, clip, local_t, local_r):
        self.clip, self.local_t, self.local_r = clip, local_t, local_r
        self.world_p, self.world_q = {}, {}

    def _world(self, i):
        if i in self.world_p:
            return self.world_p[i], self.world_q[i]
        parent = self.clip.parent.get(i)
        if parent is None or i == self.clip.root:
            p, q = np.zeros(3), np.array([0.0, 0, 0, 1])  # armature space: root transform excluded
        else:
            pp, pq = self._world(parent)
            if parent == self.clip.root:
                pp, pq = np.zeros(3), np.array([0.0, 0, 0, 1])
            p, q = pp + qrot(pq, self.local_t[i]), qnorm(qmul(pq, self.local_r[i]))
        self.world_p[i], self.world_q[i] = p, q
        return p, q

    def p(self, bone):
        return self._world(self.clip.index(bone))[0]

    def q(self, bone):
        return self._world(self.clip.index(bone))[1]


def chain(hand):
    if hand not in ("Left", "Right"):
        raise ValueError("hand must be Left or Right")
    return f"{hand}Arm", f"{hand}ForeArm", f"{hand}Hand"


def finger_bones(clip, hand):
    return [n for n in clip.names if n and n.startswith(PREFIX + hand + "Hand") and any(f in n for f in FINGERS)]


# ---------------------------------------------------------------- reference solver
def solve_two_bone(pose, hand, target, pole_hint=None):
    """Non-stretch two-bone IK for one arm of a captured pose.

    Returns {"rotations": local quaternions for Arm/ForeArm/Hand, "reachable",
    "wrist", "elbow", "normal"}. The hand keeps its captured world orientation;
    fingers are never modified; the elbow stays on the side of the captured bend
    (or of `pole_hint`, e.g. the previous frame's bend normal, when the captured
    arm is straight)."""
    arm, fore, wrist_bone = chain(hand)
    S, E, W = pose.p(arm), pose.p(fore), pose.p(wrist_bone)
    target = np.asarray(target, float)
    if not np.all(np.isfinite(target)):
        raise ValueError("non-finite target")
    a, b = np.linalg.norm(E - S), np.linalg.norm(W - E)
    normal = np.cross(E - S, W - E)
    if np.linalg.norm(normal) < 1e-6 * a * b:
        if pole_hint is None:
            raise ValueError("straight captured arm needs a pole_hint")
        normal = np.asarray(pole_hint, float)
    normal = normal / np.linalg.norm(normal)
    d = target - S
    distance = np.linalg.norm(d)
    lo, hi = abs(a - b), a + b
    reachable = lo - 1e-9 <= distance <= hi + 1e-9
    direction = d / distance if distance > 1e-9 else (W - S) / np.linalg.norm(W - S)
    # Keep a hair inside the limits: no stretch, no fully locked/folded singularity.
    margin = 1e-6 * hi
    reach = min(max(distance, lo + margin), hi - margin)
    # Elbow side: the captured bend plane, made perpendicular to the new reach direction.
    side = np.cross(direction, normal)
    if np.linalg.norm(side) < 1e-9:
        side = (E - S) - np.dot(E - S, direction) * direction
    side /= np.linalg.norm(side)
    cos_a = (a * a + reach * reach - b * b) / (2 * a * reach)
    sin_a = math.sqrt(max(0.0, 1 - cos_a * cos_a))
    E2 = S + a * (cos_a * direction + sin_a * side)
    W2 = S + reach * direction
    new_normal = np.cross(E2 - S, W2 - E2)
    new_normal /= np.linalg.norm(new_normal)
    # Rotate each bone as a rigid frame (direction + bend normal): twist follows the plane.
    r_arm = from_matrix(frame(E2 - S, new_normal) @ frame(E - S, normal).T)
    r_fore = from_matrix(frame(W2 - E2, new_normal) @ frame(W - E, normal).T)
    q_arm_w = qnorm(qmul(r_arm, pose.q(arm)))
    q_fore_w = qnorm(qmul(r_fore, pose.q(fore)))
    q_hand_w = pose.q(wrist_bone)  # captured hand orientation kept in world space
    parent = pose.clip.parent[pose.clip.index(arm)]
    q_parent = pose._world(parent)[1]
    rotations = {
        PREFIX + arm: qnorm(qmul(qinv(q_parent), q_arm_w)),
        PREFIX + fore: qnorm(qmul(qinv(q_arm_w), q_fore_w)),
        PREFIX + wrist_bone: qnorm(qmul(qinv(q_fore_w), q_hand_w)),
    }
    return {"rotations": rotations, "reachable": bool(reachable), "wrist": W2, "elbow": E2, "normal": new_normal}


# ---------------------------------------------------------------- validation of any solved pose
def validate(clip, time, hand, rotations, target=None, previous_normal=None,
             length_tol=1e-3, orient_tol_deg=0.05, wrist_tol=0.05, finger_tol_deg=1e-3, max_plane_step_deg=30.0):
    """Checks a solved pose (local rotation overrides) against the captured pose at `time`.

    Units: cm and degrees. Returns (ok, report)."""
    captured = clip.pose(time)
    solved = clip.pose(time, rotations)
    arm, fore, wrist_bone = chain(hand)
    report, ok = {}, True

    def check(name, passed, value):
        nonlocal ok
        report[name] = {"ok": bool(passed), "value": value}
        ok = ok and bool(passed)

    values = [np.asarray(q, float) for q in rotations.values()]
    check("finite", all(np.all(np.isfinite(q)) for q in values) and all(abs(np.linalg.norm(q) - 1) < 1e-3 for q in values), None)
    for upper, lower in ((arm, fore), (fore, wrist_bone)):
        before = np.linalg.norm(captured.p(lower) - captured.p(upper))
        after = np.linalg.norm(solved.p(lower) - solved.p(upper))
        check(f"length_{upper}", abs(after - before) <= length_tol, round(after - before, 6))
    check("shoulder_fixed", np.linalg.norm(solved.p(arm) - captured.p(arm)) <= length_tol,
          round(float(np.linalg.norm(solved.p(arm) - captured.p(arm))), 6))
    check("hand_world_orientation", qangle(solved.q(wrist_bone), captured.q(wrist_bone)) <= orient_tol_deg,
          round(qangle(solved.q(wrist_bone), captured.q(wrist_bone)), 6))
    changed = [n for n in rotations if any(f in n for f in FINGERS)]
    check("finger_rotations_not_overridden", not changed, changed)
    worst = 0.0
    for bone in finger_bones(clip, hand):
        worst = max(worst, qangle(solved.local_r[clip.index(bone)], captured.local_r[clip.index(bone)]))
    check("finger_local_quaternions_retained", worst <= finger_tol_deg, round(worst, 6))
    S, E, W = solved.p(arm), solved.p(fore), solved.p(wrist_bone)
    normal = np.cross(E - S, W - E)
    normal = normal / max(np.linalg.norm(normal), EPS)
    c_normal = np.cross(captured.p(fore) - captured.p(arm), captured.p(wrist_bone) - captured.p(fore))
    c_normal /= max(np.linalg.norm(c_normal), EPS)
    check("elbow_side_of_captured_bend", float(np.dot(normal, c_normal)) > 0, round(float(np.dot(normal, c_normal)), 6))
    if previous_normal is not None:
        step = math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(normal, previous_normal))))))
        check("bend_plane_continuity", step <= max_plane_step_deg, round(step, 4))
    if target is not None:
        target = np.asarray(target, float)
        a = np.linalg.norm(captured.p(fore) - captured.p(arm))
        b = np.linalg.norm(captured.p(wrist_bone) - captured.p(fore))
        distance = np.linalg.norm(target - S)
        if abs(a - b) <= distance <= a + b:
            check("wrist_reaches_target", np.linalg.norm(W - target) <= wrist_tol, round(float(np.linalg.norm(W - target)), 6))
        else:  # unreachable: no stretch; wrist on the reach limit, aimed at the target
            aim = (W - S) / np.linalg.norm(W - S)
            want = (target - S) / max(distance, EPS)
            check("unreachable_aims_at_target", float(np.dot(aim, want)) >= 0.9999, round(float(np.dot(aim, want)), 6))
            limit = a + b if distance > a + b else abs(a - b)
            check("unreachable_no_stretch", abs(np.linalg.norm(W - S) - limit) <= length_tol * 10,
                  round(float(np.linalg.norm(W - S) - limit), 6))
    return ok, report, normal


# ---------------------------------------------------------------- clip analysis
def analyze(clip, start, end, keytop_y=None, keyboard=None, step=None):
    times = [t for t in clip.frame_times if start - 1e-6 <= t <= end + 1e-6]
    if step:
        times = list(np.arange(start, end + 1e-9, step))
    report = {"duration_s": round(clip.duration, 5), "segment_s": [start, end], "frames": len(times), "hands": {}}
    poses = [clip.pose(t) for t in times]
    for hand in ("Left", "Right"):
        fingers = finger_bones(clip, hand)
        ranges = {}
        for bone in fingers:
            i = clip.index(bone)
            base = poses[0].local_r[i]
            ranges[bone] = max(qangle(p.local_r[i], base) for p in poses)
        wrist = [p.p(f"{hand}Hand") for p in poses]
        tip = [p.p(f"{hand}HandIndex4") for p in poses]
        path = float(sum(np.linalg.norm(b - a) for a, b in zip(wrist, wrist[1:])))
        entry = {
            "moving_finger_joints_gt_2deg": sum(r > 2 for r in ranges.values()),
            "finger_joints": len(fingers),
            "max_finger_joint_range_deg": round(max(ranges.values()), 2),
            "wrist_path_cm": round(path, 3),
            "endpoint_gap_cm": {
                "wrist": round(float(np.linalg.norm(wrist[-1] - wrist[0])), 3),
                "index_tip": round(float(np.linalg.norm(tip[-1] - tip[0])), 3),
            },
            "index_tip_y_cm_joint_only": [round(float(min(t[1] for t in tip)), 3), round(float(max(t[1] for t in tip)), 3)],
        }
        if keytop_y is not None:
            entry["index_tip_below_keytop_frames_joint_only"] = sum(t[1] < keytop_y for t in tip)
        if keyboard is not None:
            x0, x1, z0, z1 = keyboard
            entry["index_tip_inside_footprint_fraction"] = round(
                sum(x0 <= t[0] <= x1 and z0 <= t[2] <= z1 for t in tip) / len(tip), 4)
        report["hands"][hand] = entry
    gaps = [max(h["endpoint_gap_cm"].values()) for h in report["hands"].values()]
    report["seamless_loop"] = max(gaps) < 0.5
    report["note"] = "Joint centres only: finger-pad contact/penetration needs the renderer's skinned vertices."
    return report


def self_test(clip, start, end, offsets_cm=(2.0, -2.0)):
    """Solve every captured frame of the segment for both hands: identity (captured
    wrist), reachable offsets, and an unreachable far target; validate each."""
    failures, counts = [], {"solved": 0, "reachable": 0, "unreachable": 0}
    times = [t for t in clip.frame_times if start - 1e-6 <= t <= end + 1e-6]
    for hand in ("Left", "Right"):
        previous = None
        for t in times:
            pose = clip.pose(t)
            arm, fore, wrist_bone = chain(hand)
            W = pose.p(wrist_bone)
            reach = np.linalg.norm(pose.p(fore) - pose.p(arm)) + np.linalg.norm(W - pose.p(fore))
            far = pose.p(arm) + (W - pose.p(arm)) / np.linalg.norm(W - pose.p(arm)) * reach * 1.5
            inward = (pose.p(arm) - W) / np.linalg.norm(pose.p(arm) - W)
            # Captured wrist, upward/downward offsets (often beyond a near-straight
            # captured arm: they exercise the no-stretch path), offsets that need
            # elbow bend (toward the shoulder), and a far unreachable point.
            targets = [W] + [W + np.array([0, dy, 0]) for dy in offsets_cm] + \
                [W + inward * 3.0, W + inward * 6.0 + np.array([0, -2.0, 0]), far]
            for k, target in enumerate(targets):
                result = solve_two_bone(pose, hand, target, pole_hint=previous)
                ok, report, normal = validate(clip, t, hand, result["rotations"], target,
                                              previous_normal=previous if k == 0 else None)
                counts["solved"] += 1
                counts["reachable" if result["reachable"] else "unreachable"] += 1
                if not ok:
                    failures.append({"hand": hand, "time": round(t, 4), "target": k,
                                     "failed": {n: r for n, r in report.items() if not r["ok"]}})
                if k == 0:
                    previous = normal
    return {"ok": not failures, **counts, "failures": failures[:20]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Independent hand-contact math/data validation (CPU only)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("analyze", "self-test", "validate"):
        p = sub.add_parser(name)
        p.add_argument("clip")
        if name == "validate":
            p.add_argument("solved")
        p.add_argument("--start", type=float, default=3.0)
        p.add_argument("--end", type=float, default=8.0)
        p.add_argument("--keytop-y", type=float, default=87.38976)
        p.add_argument("--keyboard", help="X0,X1,Z0,Z1 keyboard footprint in armature cm")
    args = parser.parse_args(argv)
    clip = Clip(args.clip)
    if args.command == "analyze":
        keyboard = [float(v) for v in args.keyboard.split(",")] if args.keyboard else None
        result = analyze(clip, args.start, args.end, args.keytop_y, keyboard)
    elif args.command == "self-test":
        result = self_test(clip, args.start, args.end)
    else:
        data = json.loads(Path(args.solved).read_text())
        previous, frames = None, []
        for f in data["frames"]:
            ok, report, previous = validate(clip, f["time"], data["hand"], f["local_rotations"], f.get("target"), previous)
            frames.append({"time": f["time"], "ok": ok, "failed": {k: v for k, v in report.items() if not v["ok"]}})
        result = {"ok": all(f["ok"] for f in frames), "frames": frames}
    print(json.dumps(result, indent=2, default=lambda v: v.tolist() if hasattr(v, "tolist") else str(v)))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
