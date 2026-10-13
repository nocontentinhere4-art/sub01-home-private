#!/usr/bin/env python3
"""CPU-only finger rig/animation diagnostics for the first-person owner skin.

Question: why do the first-person fingers look contracted?  This compares, per
finger joint of both hands (each hand measured on its own geometry, never
mirrored):

* the captured clips' node reference (rest) pose: the staged first-person
  clips (web/house/assets/first-person/{typing,walking,texting}.glb) and the
  original baked capture they were retargeted from
  (web/room/mh_mx/room_mx_typing.glb);
* the target rig's node reference pose (web/room/char_mixamo.glb, byte-identical
  to first-person/owner.glb);
* the target skin's bind pose from its inverse bind matrices
  (jointBind = meshWorld * inverse(IBM)), and the bind-space skin vertices.

It measures captured flexion about each joint's bend axis, replays the exact
rotation math of tools/retarget_first_person.mjs (aligned world rest delta)
and evaluates the joint chain and the linear-blend-skinned mesh.

Two alternatives are evaluated against the data:

* "bind reference" (REJECTED by the data): the same world rest delta but with
  the skin bind pose as the target reference.  The autorig bind keeps the
  modelled finger curl at the knuckles, so this double-applies curl.
* "local frame" candidate (proposed for general use; identical to the current
  output on these assets): for finger joints only,
      local_tgt(j) = R_rest_tgt(j) * A(j) * [inv(R_rest_src(j)) * local_src(j)] * inv(A(j))
  with A(j) = F_tgt(j) * transpose(F_src(j)), F = orthonormal joint-local frame
  built from the rest bone direction (child translation) and the rest palm
  normal of that skeleton's own hand.  It preserves each joint's captured local
  flexion relative to each skeleton's own rest, independent of differences in
  hand/arm rest orientation, and uses rest transforms only (no captured motion,
  no hand-tuned offsets).

Joint data alone cannot prove the rendered appearance; native visual review
remains required.

Usage:
  python tools/animation_rig_audit.py report  [--output OUT.json] [--step N]
  python tools/animation_rig_audit.py candidate [--output OUT.json]
  python tools/animation_rig_audit.py segments [--output OUT.json]   (rank capture windows)
Default outputs go to the system temp directory, never into the repository.
"""

import argparse
import hashlib
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hand_contact_validation import frame, from_matrix, qangle, qinv, qmul, qnorm, qrot  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DUMP = ROOT / "tools" / "animation_rig_dump.mjs"
TARGET = ROOT / "web/room/char_mixamo.glb"
OWNER = ROOT / "web/house/assets/first-person/owner.glb"
CLIPS = {name: ROOT / f"web/house/assets/first-person/{name}.glb" for name in ("typing", "walking", "texting")}
ORIGINAL_TYPING = ROOT / "web/room/mh_mx/room_mx_typing.glb"
FINGERS = ("Thumb", "Index", "Middle", "Ring", "Pinky")
HANDS = ("Left", "Right")
PREFIX = "mixamorig:"
VERTEX_PATTERN = r"Hand(Thumb|Index|Middle|Ring|Pinky)|Hand$"
# Active flexion limits (degrees) by joint level: MCP / PIP / DIP (thumb: CMC / MCP / IP).
ANATOMY = {1: (-20.0, 90.0), 2: (-5.0, 110.0), 3: (-10.0, 80.0)}
# Loose relaxed-keyboard band (typing-posture literature): MCP 0-45, PIP 15-65, DIP 0-40.
TYPING_BAND = {1: (0.0, 45.0), 2: (15.0, 65.0), 3: (0.0, 40.0)}
IDENTITY = np.array([0.0, 0.0, 0.0, 1.0])


def canonical(name):
    name = name or ""
    return name[len(PREFIX):] if name.startswith(PREFIX) else name


# ---------------------------------------------------------------- loading
_CACHE = {}


def load(path, vertices=False):
    """Decode a GLB through tools/animation_rig_dump.mjs (meshopt aware) into a dict (cached)."""
    path = Path(path)
    if path.suffix == ".json":
        return json.loads(path.read_text())
    key = (str(path.resolve()), path.stat().st_mtime_ns, vertices)
    if key not in _CACHE:
        work = Path(tempfile.mkdtemp(prefix="sub01-rig-audit-"))
        out = work / (hashlib.sha256(repr(key).encode()).hexdigest()[:16] + ".json")
        cmd = ["node", str(DUMP), str(path), str(out)] + (["--vertices", VERTEX_PATTERN] if vertices else [])
        subprocess.run(cmd, check=True, cwd=ROOT, capture_output=True)
        _CACHE[key] = json.loads(out.read_text())
    return _CACHE[key]


def trs(t, q, s=1.0):
    x, y, z, w = qnorm(np.asarray(q, float))
    m = np.eye(4)
    m[:3, :3] = s * np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                              [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                              [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    m[:3, 3] = t
    return m


def decompose(m):
    if np.linalg.det(m[:3, :3]) <= 0:
        raise ValueError("Mirrored/singular transform")
    s = np.linalg.norm(m[:3, :3], axis=0)
    return m[:3, 3].copy(), from_matrix(m[:3, :3] / s), s


def world_q(m):
    return from_matrix(m[:3, :3] / np.linalg.norm(m[:3, 0]))


class Rig:
    """Node hierarchy in armature space: the armature root (scale 0.01) is excluded, units are cm."""

    def __init__(self, dump):
        self.dump = dump
        self.nodes = dump["nodes"]
        self.parent = {i: n["parent"] for i, n in enumerate(self.nodes)}
        self.names = {canonical(n["name"]): i for i, n in enumerate(self.nodes) if n["name"].startswith(PREFIX)}
        self.root = self.parent[self.names["Hips"]]
        self.t, self.r, self.s = [], [], []
        for n in self.nodes:
            if n["matrix"] is not None:
                t, q, s = decompose(np.array(n["matrix"], float).reshape(4, 4).T)
            else:
                t = np.array(n["translation"] or [0, 0, 0], float)
                q = qnorm(np.array(n["rotation"] or [0, 0, 0, 1], float))
                s = np.array(n["scale"] or [1, 1, 1], float)
            if np.ptp(s) > 1e-6 or s[0] <= 0:
                raise ValueError("Non-uniform or mirrored scale in rig")
            self.t.append(t)
            self.r.append(q)
            self.s.append(float(s[0]))
        self.order, seen = [], set()

        def visit(i):
            if i not in seen:
                if self.parent[i] is not None:
                    visit(self.parent[i])
                seen.add(i)
                self.order.append(i)
        for i in range(len(self.nodes)):
            visit(i)
        self.rest = self.world(self.r)

    def idx(self, bone):
        return self.names[bone]

    def scene_world(self, i):
        m = np.eye(4)
        while i is not None:
            m = trs(self.t[i], self.r[i], self.s[i]) @ m
            i = self.parent[i]
        return m

    def world(self, local_r, local_t=None):
        local_t = self.t if local_t is None else local_t
        out = {}
        for i in self.order:
            p = self.parent[i]
            if i == self.root or p is None:
                continue
            m = trs(local_t[i], local_r[i], self.s[i])
            out[i] = m if p == self.root else out[p] @ m
        return out

    def ibm_determinants(self):
        skin = self.dump["skins"][0]
        return [float(np.linalg.det(np.array(m, float).reshape(4, 4).T[:3, :3])) for m in skin["inverseBindMatrices"]]

    def bind(self):
        """Armature-space joint bind matrices from the skin's inverse bind matrices."""
        skin = self.dump["skins"][0]
        mesh = next(i for i, n in enumerate(self.nodes) if n["skin"] == 0)
        to_armature = np.linalg.inv(self.scene_world(self.root)) @ self.scene_world(mesh)
        return {j: to_armature @ np.linalg.inv(np.array(m, float).reshape(4, 4).T)
                for j, m in zip(skin["joints"], skin["inverseBindMatrices"])}

    def local_from_world(self, world):
        r, t = list(self.r), list(self.t)
        for i, m in world.items():
            p = self.parent[i]
            pm = np.eye(4) if p == self.root else world.get(p, self.rest[p])
            t[i], r[i], _ = decompose(np.linalg.inv(pm) @ m)
        return r, t

    def bind_vertices(self):
        """Bind-space hand/finger vertices (armature space) with their joint indices and weights."""
        verts = self.dump.get("skinVertices")
        if not verts:
            raise ValueError("Dump has no skin vertices; load(..., vertices=True)")
        to_armature = np.linalg.inv(self.scene_world(self.root))
        p = np.array([(to_armature @ self.scene_world(v["mesh"]) @ np.append(v["p"], 1.0))[:3] for v in verts])
        return p, np.array([v["j"] for v in verts]), np.array([v["w"] for v in verts], float)


class Clip:
    def __init__(self, dump, rig):
        self.rig = rig
        self.channels = {}
        for c in dump["animations"][0]["channels"]:
            if c["interpolation"] != "LINEAR":
                raise ValueError("Only LINEAR channels supported")
            self.channels[(c["node"], c["path"])] = (np.array(c["times"]), np.array(c["values"], float))
        self.times = sorted({float(t) for times, _ in self.channels.values() for t in times})

    def local(self, k):
        time = self.times[k]
        r, t = [q.copy() for q in self.rig.r], [v.copy() for v in self.rig.t]
        for (node, path), (times, values) in self.channels.items():
            j = min(int(np.searchsorted(times, time - 1e-9)), len(times) - 1)
            if path == "rotation":
                r[node] = qnorm(values[j])
            elif path == "translation":
                t[node] = values[j]
        return r, t

    def frames(self, step=1, start=None, end=None):
        for k, time in enumerate(self.times):
            if k % step == 0 and (start is None or time >= start) and (end is None or time <= end):
                yield self.local(k)


def load_clip(path):
    dump = load(path)
    return Clip(dump, Rig(dump))


# ---------------------------------------------------------------- finger geometry
def finger_chain(rig, hand, finger):
    return [rig.idx(f"{hand}Hand")] + [rig.idx(f"{hand}Hand{finger}{n}") for n in (1, 2, 3, 4)]


def finger_joint_names(hand=None, levels=(1, 2, 3)):
    hands = HANDS if hand is None else (hand,)
    return [f"{h}Hand{f}{n}" for h in hands for f in FINGERS for n in levels]


def rotvec(q):
    q = qnorm(q)
    q = -q if q[3] < 0 else q
    s = np.linalg.norm(q[:3])
    return np.zeros(3) if s < 1e-12 else q[:3] / s * 2 * math.atan2(s, q[3])


def twist_angle(q, axis):
    """Signed twist (degrees) of q about a unit axis (swing-twist decomposition)."""
    q = qnorm(q)
    q = -q if q[3] < 0 else q
    return math.degrees(2 * math.atan2(float(np.dot(q[:3], axis)), q[3]))


def palm_normal(world, rig, hand):
    """Unit palm normal (out of the palm = flexion side) from this hand's own joints.

    Mixamo T-pose, palms down: left mid=+X, index-pinky=+Z -> cross(mid, lateral) = -Y;
    right mid=-X, lateral=+Z -> cross(lateral, mid) = -Y."""
    h = world[rig.idx(f"{hand}Hand")][:3, 3]
    mid = world[rig.idx(f"{hand}HandMiddle1")][:3, 3] - h
    lateral = world[rig.idx(f"{hand}HandIndex1")][:3, 3] - world[rig.idx(f"{hand}HandPinky1")][:3, 3]
    n = np.cross(lateral, mid) if hand == "Right" else np.cross(mid, lateral)
    return n / np.linalg.norm(n)


def rest_frame(rig, name):
    """Joint-local orthonormal frame (columns: bone, palm normal, side) from the rig's rest only."""
    hand = "Left" if name.startswith("Left") else "Right"
    i = rig.idx(name)
    child = rig.idx(name[:-1] + str(int(name[-1]) + 1))
    normal_local = qrot(qinv(world_q(rig.rest[i])), palm_normal(rig.rest, rig, hand))
    return frame(rig.t[child], normal_local)


def bend_axes(rig, clips, hand, step=2):
    """Per joint: local bend axis = principal axis of the captured local rotation deltas from rest,
    signed so that a positive rotation moves the child bone toward this hand's palm."""
    normal = palm_normal(rig.rest, rig, hand)
    axes = {}
    for finger in FINGERS:
        for level in (1, 2, 3):
            j = rig.idx(f"{hand}Hand{finger}{level}")
            bone = rig.t[rig.idx(f"{hand}Hand{finger}{level + 1}")]
            bone = bone / np.linalg.norm(bone)
            vecs = np.array([rotvec(qmul(qinv(rig.r[j]), r[j])) for clip in clips for r, _ in clip.frames(step)])
            _, sv, vt = np.linalg.svd(vecs, full_matrices=False)
            axis = vt[0]
            if float(np.dot(qrot(world_q(rig.rest[j]), np.cross(axis, bone)), normal)) < 0:
                axis = -axis
            energy = sv ** 2
            axes[(finger, level)] = {"axis": axis, "explained": float(energy[0] / max(energy.sum(), 1e-12)),
                                     "bone": bone}
    return axes


def chain_metrics(points):
    """Hand, F1..F4 positions -> curl (metacarpal vs distal direction), per-joint bends and reach."""
    seg = [points[i + 1] - points[i] for i in range(4)]
    unit = [s / np.linalg.norm(s) for s in seg]
    bends = [math.degrees(math.acos(np.clip(np.dot(unit[i], unit[i + 1]), -1, 1))) for i in range(3)]
    curl = math.degrees(math.acos(np.clip(np.dot(unit[0], unit[3]), -1, 1)))
    length = sum(np.linalg.norm(s) for s in seg[1:])
    return {"curl_deg": curl, "segment_bends_deg": bends,
            "tip_reach_ratio": float(np.linalg.norm(points[4] - points[1]) / length),
            "tip_to_hand_cm": float(np.linalg.norm(points[4] - points[0]))}


def joint_points(world, chain):
    return [world[i][:3, 3] for i in chain]


def skinned_points(world, bind, chain, rig):
    """Where the skin carries each joint's bind location: S_parent * bindPosition, S = world * inv(bind)."""
    pts = [world[chain[0]][:3, 3]]
    for k in chain[1:]:
        p = rig.parent[k]
        pts.append((world[p] @ np.linalg.inv(bind[p]) @ np.append(bind[k][:3, 3], 1.0))[:3])
    return pts


def skin_vertices(world, bind, positions, joints, weights):
    """Linear blend skinning of bind-space vertices (armature space)."""
    mats = {j: world[j] @ np.linalg.inv(bind[j]) for j in bind}
    out = np.zeros_like(positions)
    for k in range(joints.shape[1]):
        m = np.array([mats[j] for j in joints[:, k]])
        out += weights[:, k:k + 1] * (np.einsum("nij,nj->ni", m[:, :3, :3], positions) + m[:, :3, 3])
    return out


def mesh_phalanx_deviation(rig, world, bind, positions, joints, weights, hand, finger):
    """Per phalanx: angle between the bone and joint->centroid of the vertices it dominates, and its
    palmar component (positive = mesh lies more toward the palm than the bone, i.e. extra curl)."""
    mesh = skin_vertices(world, bind, positions, joints, weights)
    dom = joints[np.arange(len(joints)), weights.argmax(1)]
    strong = weights.max(1) > 0.5
    chain = finger_chain(rig, hand, finger)
    normal = palm_normal(world, rig, hand)
    out = []
    for level in (1, 2, 3):
        sel = (dom == chain[level]) & strong
        if sel.sum() < 4:
            out.append(None)
            continue
        start = world[chain[level]][:3, 3]
        bone = world[chain[level + 1]][:3, 3] - start
        d = mesh[sel].mean(0) - start
        total = math.degrees(math.acos(np.clip(np.dot(d, bone) / np.linalg.norm(d) / np.linalg.norm(bone), -1, 1)))
        u = bone / np.linalg.norm(bone)
        n = normal - np.dot(normal, u) * u
        palmar = math.degrees(math.atan2(np.dot(d, n / np.linalg.norm(n)), np.dot(d, u)))
        out.append({"deviation_deg": total, "palmar_deg": palmar, "vertices": int(sel.sum())})
    return out


# ---------------------------------------------------------------- retarget math
def basis(rig):
    """Anatomical basis of tools/retarget_first_person.mjs basis(): x hips lateral, y hips->Spine2."""
    p = {b: rig.rest[rig.idx(b)][:3, 3] for b in ("Hips", "Spine2", "LeftUpLeg", "RightUpLeg")}
    x = p["RightUpLeg"] - p["LeftUpLeg"]
    x /= np.linalg.norm(x)
    y = p["Spine2"] - p["Hips"]
    y -= np.dot(y, x) * x
    y /= np.linalg.norm(y)
    return from_matrix(np.column_stack([x, y, np.cross(x, y)]))


def alignment(src, tgt):
    return qmul(basis(tgt), qinv(basis(src)))


def retarget_world_delta(src, tgt, src_local_r, src_local_t=None, reference=None, align=None):
    """Exact rotation math of retarget_first_person.mjs retargetPose():
    desired_world(j) = C * Qsrc_world(j) * inv(Qsrc_restworld(j)) * inv(C) * Qtgt_reference_world(j);
    local(j) = inv(parent_world) * desired_world(j), parents first.  `reference` maps target joint ->
    world matrix (default: target node rest, as in the .mjs).  Returns (local rotations, world)."""
    reference = tgt.rest if reference is None else reference
    c = alignment(src, tgt) if align is None else align
    src_world = src.world(src_local_r, src_local_t)
    r, world = list(tgt.r), {}
    for ti in tgt.order:
        p = tgt.parent[ti]
        if ti == tgt.root or p is None:
            continue
        name = canonical(tgt.nodes[ti]["name"])
        pw = np.eye(4) if p == tgt.root else world[p]
        if name in tgt.names and name in src.names:
            si = src.idx(name)
            delta = qmul(qmul(qmul(c, world_q(src_world[si])), qinv(world_q(src.rest[si]))), qinv(c))
            r[ti] = qnorm(qmul(qinv(world_q(pw)), qmul(delta, world_q(reference[ti]))))
        world[ti] = pw @ trs(tgt.t[ti], r[ti], tgt.s[ti])
    return r, world


def frame_alignments(src, tgt):
    """A(j) = F_tgt(j) * F_src(j)^T per finger joint (levels 1-3, both hands), rest transforms only."""
    out = {}
    for name in finger_joint_names():
        m = rest_frame(tgt, name) @ rest_frame(src, name).T
        out[name] = from_matrix(m)
    return out


def retarget_local_candidate(src, tgt, src_local_r, src_local_t=None, align=None, frames=None):
    """Candidate: non-finger joints exactly as the current world rest delta; finger joints
    local_tgt = R_rest_tgt * A * (inv(R_rest_src) * local_src) * inv(A)."""
    frames = frame_alignments(src, tgt) if frames is None else frames
    r, _ = retarget_world_delta(src, tgt, src_local_r, src_local_t, align=align)
    for name, a in frames.items():
        si, ti = src.idx(name), tgt.idx(name)
        delta = qmul(qinv(src.r[si]), src_local_r[si])
        r[ti] = qnorm(qmul(tgt.r[ti], qmul(qmul(a, delta), qinv(a))))
    return r, tgt.world(r)


def bind_reference(tgt, bind):
    """Target reference for the rejected variant: skin bind orientation for finger joints."""
    ref = dict(tgt.rest)
    fingers = set(finger_joint_names(levels=(1, 2, 3, 4)))
    ref.update({i: m for i, m in bind.items() if canonical(tgt.nodes[i]["name"]) in fingers})
    return ref


# ---------------------------------------------------------------- report
def flexion_samples(rig, clip, axes, hand, start=None, end=None, step=1):
    samples = {k: [] for k in axes}
    for r, _ in clip.frames(step, start, end):
        for (finger, level), a in axes.items():
            j = rig.idx(f"{hand}Hand{finger}{level}")
            samples[(finger, level)].append(twist_angle(qmul(qinv(rig.r[j]), r[j]), a["axis"]))
    return {k: np.array(v) for k, v in samples.items()}


def summarize(values):
    return {"min": float(values.min()), "mean": float(values.mean()), "max": float(values.max())}


def build_report(step=5, target=TARGET, clips=None, original=ORIGINAL_TYPING):
    clips = CLIPS if clips is None else clips
    tdump = load(target, vertices=True)
    tgt = Rig(tdump)
    bind = tgt.bind()
    bind_r, bind_t = tgt.local_from_world(bind)
    loaded = {name: load_clip(path) for name, path in clips.items()}
    report = {"target": str(Path(target).relative_to(ROOT)) if Path(target).is_relative_to(ROOT) else str(target),
              "target_sha256": tdump["sha256"],
              "owner_identical_to_target": OWNER.exists() and load(OWNER)["sha256"] == tdump["sha256"],
              "clips": {n: {"sha256": c.rig.dump["sha256"], "frames": len(c.times), "duration": c.times[-1]}
                        for n, c in loaded.items()}}

    # rest equality of every source with the target, and of the staged typing clip with its original capture
    report["source_rest_vs_target_rest"] = {}
    for name, clip in loaded.items():
        common = [b for b in tgt.names if b in clip.rig.names]
        report["source_rest_vs_target_rest"][name] = {
            "max_rotation_deg": max(qangle(clip.rig.r[clip.rig.idx(b)], tgt.r[tgt.idx(b)]) for b in common),
            "max_translation_cm": max(float(np.linalg.norm(clip.rig.t[clip.rig.idx(b)] - tgt.t[tgt.idx(b)])) for b in common),
            "alignment_deg": qangle(alignment(clip.rig, tgt), IDENTITY)}
    if original is not None and "typing" in loaded:
        orig = load_clip(original)
        staged = loaded["typing"]
        worst = 0.0
        for k in range(0, min(len(orig.times), len(staged.times)), step):
            a_r, _ = orig.local(k)
            b_r, _ = staged.local(k)
            worst = max(worst, max(qangle(a_r[orig.rig.idx(b)], b_r[staged.rig.idx(b)]) for b in finger_joint_names()))
        report["original_capture_vs_staged_typing"] = {
            "original": str(Path(original).relative_to(ROOT)), "frames": len(orig.times),
            "max_rest_rotation_deg": max(qangle(orig.rig.r[orig.rig.idx(b)], tgt.r[tgt.idx(b)]) for b in tgt.names if b in orig.rig.names),
            "max_finger_local_diff_deg": worst}

    # bind pose versus node reference
    report["ibm_min_determinant"] = min(tgt.ibm_determinants())
    report["rest_vs_bind_nonfinger_deg"] = {b: qangle(tgt.r[i], bind_r[i]) for b, i in tgt.names.items()
                                            if i in bind and not any(f in b for f in FINGERS)
                                            and qangle(tgt.r[i], bind_r[i]) > 1.0}
    clips_list = list(loaded.values())
    src = clips_list[0].rig
    joints = {}
    for hand in HANDS:
        axes = bend_axes(src, clips_list, hand)
        for (finger, level), a in axes.items():
            name = f"{hand}Hand{finger}{level}"
            i, child = tgt.idx(name), tgt.idx(f"{hand}Hand{finger}{level + 1}")
            delta = qmul(qinv(tgt.r[i]), bind_r[i])
            bone = tgt.t[child] / np.linalg.norm(tgt.t[child])
            joints[name] = {
                "rest_local_xyzw": tgt.r[i], "bind_local_xyzw": bind_r[i],
                "bind_vs_rest_deg": qangle(tgt.r[i], bind_r[i]),
                "bind_flexion_deg": twist_angle(delta, a["axis"]),
                "bind_roll_about_bone_deg": twist_angle(delta, bone),
                "bone_axis_local": bone, "bone_axis_vs_plus_y_deg": math.degrees(math.acos(np.clip(bone[1], -1, 1))),
                "bend_axis_local": a["axis"], "bend_axis_explained": a["explained"],
                "bone_length_cm": float(np.linalg.norm(tgt.t[child])),
                "bind_translation_diff_cm": float(np.linalg.norm(bind_t[child] - tgt.t[child])),
                "flexion_vs_rest": {}, "typing_3_8s": None,
            }
        for cname, clip in loaded.items():
            for (finger, level), v in flexion_samples(src, clip, axes, hand).items():
                joints[f"{hand}Hand{finger}{level}"]["flexion_vs_rest"][cname] = summarize(v)
        if "typing" in loaded:
            for (finger, level), v in flexion_samples(src, loaded["typing"], axes, hand, 3.0, 8.0).items():
                lo, hi = TYPING_BAND[level]
                joints[f"{hand}Hand{finger}{level}"]["typing_3_8s"] = {
                    **summarize(v), "fraction_above_typing_band": float(np.mean(v > hi)),
                    "fraction_outside_anatomy": float(np.mean((v < ANATOMY[level][0]) | (v > ANATOMY[level][1])))}
    report["finger_joints"] = joints

    # mesh vs bones (bind and rest)
    positions, vjoints, weights = tgt.bind_vertices()
    report["mesh_phalanx_vs_bone"] = {
        f"{hand}{finger}": {pose: mesh_phalanx_deviation(tgt, w, bind, positions, vjoints, weights, hand, finger)
                            for pose, w in (("bind", bind), ("rest", tgt.rest))}
        for hand in HANDS for finger in FINGERS}
    report["finger_chain_rest_vs_bind"] = {
        f"{hand}{finger}": {"rest": chain_metrics(joint_points(tgt.rest, finger_chain(tgt, hand, finger))),
                            "bind": chain_metrics(joint_points(bind, finger_chain(tgt, hand, finger)))}
        for hand in HANDS for finger in FINGERS}

    # contraction: source joints vs current retarget (joints and skinned) vs bind-reference vs candidate
    ref = bind_reference(tgt, bind)
    contraction = {}
    for cname, clip in loaded.items():
        acc = {}
        for r, t in clip.frames(step):
            sw = clip.rig.world(r, t)
            cur_r, cur_w = retarget_world_delta(clip.rig, tgt, r, t)
            _, bind_w = retarget_world_delta(clip.rig, tgt, r, t, reference=ref)
            _, cand_w = retarget_local_candidate(clip.rig, tgt, r, t)
            for hand in HANDS:
                for finger in FINGERS:
                    chain = finger_chain(tgt, hand, finger)
                    a = acc.setdefault(f"{hand}{finger}", {k: [] for k in (
                        "source_joints", "current_joints", "current_skinned", "bind_reference_skinned", "candidate_skinned")})
                    a["source_joints"].append(chain_metrics(joint_points(sw, finger_chain(clip.rig, hand, finger))))
                    a["current_joints"].append(chain_metrics(joint_points(cur_w, chain)))
                    a["current_skinned"].append(chain_metrics(skinned_points(cur_w, bind, chain, tgt)))
                    a["bind_reference_skinned"].append(chain_metrics(skinned_points(bind_w, bind, chain, tgt)))
                    a["candidate_skinned"].append(chain_metrics(skinned_points(cand_w, bind, chain, tgt)))
        contraction[cname] = {k: {m: {"curl_deg_mean": float(np.mean([x["curl_deg"] for x in v])),
                                      "curl_deg_max": float(np.max([x["curl_deg"] for x in v])),
                                      "tip_reach_ratio_mean": float(np.mean([x["tip_reach_ratio"] for x in v]))}
                                  for m, v in a.items()} for k, a in acc.items()}
    report["contraction"] = contraction
    return report


def candidate_data(step=10, target=TARGET, clips=None):
    clips = CLIPS if clips is None else clips
    tdump = load(target)
    tgt = Rig(tdump)
    rows = {}
    for cname, path in clips.items():
        src = load_clip(path).rig
        for name, a in frame_alignments(src, tgt).items():
            rows.setdefault(name, {})[cname] = {"A_xyzw": a, "A_deg": qangle(a, IDENTITY)}
    return {
        "status": "candidate for native validation; not runtime-accepted",
        "formula": "finger joints j (levels 1-3, each hand independently): local_tgt(j) = R_rest_tgt(j) * A(j) * "
                   "[inv(R_rest_src(j)) * local_src(j)] * inv(A(j)); A(j) = F_tgt(j) * F_src(j)^T, "
                   "F = frame(rest child translation, rest palm normal in joint-local coordinates). "
                   "All other joints: unchanged aligned world rest delta (retarget_first_person.mjs).",
        "derived_from": "rest transforms only; no captured motion, no hand-tuned offsets, no mirroring",
        "rejected_variant": "world rest delta referenced to the skin bind pose (double-applies the 43-64 deg "
                            "modelled knuckle curl kept in the inverse bind matrices)",
        "target": str(target), "target_sha256": tdump["sha256"],
        "joints": rows,
    }


# ---------------------------------------------------------------- capture window search
# Existing genuine typing/desk captures (Mixamo captures baked onto the owner skeleton, plus the staged clip).
TYPING_CAPTURES = {
    "typing": ROOT / "web/house/assets/first-person/typing.glb",
    "room_mx_typing": ROOT / "web/room/mh_mx/room_mx_typing.glb",
    "room_mx_sit_to_type": ROOT / "web/room/mh_mx/room_mx_sit_to_type.glb",
    "room_mx_type_to_sit": ROOT / "web/room/mh_mx/room_mx_type_to_sit.glb",
}
NON_THUMB = ("Index", "Middle", "Ring", "Pinky")
HOOK_RATIO = 4.0          # interphalangeal (L2+L3) flexion more than 4x the knuckle (L1) flexion: hooked
ELBOW_MIN_RANGE = 10.0    # degrees of genuine elbow bend change inside a window
WRIST_P95_SPEED = 60.0    # cm/s; typing wrists drift, they do not fling
WRIST_MAX_SPEED = 150.0   # cm/s; anything above is a capture pop


def rest_bend_axis(rig, name):
    """Joint-local flexion axis from rest only: bone x palm normal (positive = toward this hand's palm)."""
    hand = "Left" if name.startswith("Left") else "Right"
    i = rig.idx(name)
    bone = rig.t[rig.idx(name[:-1] + str(int(name[-1]) + 1))]
    normal = qrot(qinv(world_q(rig.rest[i])), palm_normal(rig.rest, rig, hand))
    axis = np.cross(bone, normal)
    return axis / np.linalg.norm(axis)


def frame_series(clip):
    """Per frame and hand: knuckle/interphalangeal flexion, elbow bend, wrist and index-tip positions,
    and the 15 finger local rotations (levels 1-3) used for the activity count."""
    rig = clip.rig
    axes = {n: rest_bend_axis(rig, n) for n in finger_joint_names(levels=(1, 2, 3))}
    out = {h: {"l1": [], "ip": [], "elbow": [], "wrist": [], "tip": [], "quats": []} for h in HANDS}
    for r, t in clip.frames():
        world = rig.world(r, t)
        for hand in HANDS:
            s = out[hand]
            flex = {n: twist_angle(qmul(qinv(rig.r[rig.idx(n)]), r[rig.idx(n)]), axes[n])
                    for n in finger_joint_names(hand)}
            s["l1"].append(np.mean([flex[f"{hand}Hand{f}1"] for f in NON_THUMB]))
            s["ip"].append(np.mean([flex[f"{hand}Hand{f}2"] + flex[f"{hand}Hand{f}3"] for f in NON_THUMB]))
            arm, fore, wrist = (world[rig.idx(hand + b)][:3, 3] for b in ("Arm", "ForeArm", "Hand"))
            u, v = fore - arm, wrist - fore
            s["elbow"].append(math.degrees(math.acos(np.clip(np.dot(u, v) / np.linalg.norm(u) / np.linalg.norm(v), -1, 1))))
            s["wrist"].append(wrist)
            s["tip"].append(world[rig.idx(hand + "HandIndex4")][:3, 3])
            s["quats"].append([r[rig.idx(n)] for n in finger_joint_names(hand)])
    return {h: {k: np.array(v, float) for k, v in s.items()} for h, s in out.items()}, np.array(clip.times)


def score_window(series, times, a, b):
    """Metrics and score for frames [a, b] (inclusive).  Score = mean of per-hand balance and activity,
    per-hand wrist plausibility, left elbow genuineness and loop closure, each in [0, 1]."""
    hands, parts = {}, []
    dt = np.diff(times[a:b + 1])
    for hand in HANDS:
        s = series[hand]
        l1, ip = float(s["l1"][a:b + 1].mean()), float(s["ip"][a:b + 1].mean())
        q = s["quats"][a:b + 1]
        moving = int(np.sum(np.max(2 * np.degrees(np.arccos(np.clip(np.abs(np.sum(q * q[0], axis=2)), 0, 1))), axis=0) > 2.0))
        w = s["wrist"][a:b + 1]
        speed = np.linalg.norm(np.diff(w, axis=0), axis=1) / np.maximum(dt, 1e-6)
        elbow = s["elbow"][a:b + 1]
        gap = max(float(np.linalg.norm(w[-1] - w[0])), float(np.linalg.norm(s["tip"][b] - s["tip"][a])))
        ratio = ip / max(l1, 1.0)
        m = {"l1_flexion_mean_deg": l1, "l2_l3_flexion_mean_deg": ip, "ip_to_l1_ratio": ratio,
             "hooked": bool(ratio > HOOK_RATIO), "moving_finger_joints_gt_2deg": moving,
             "wrist_path_cm": float(np.sum(speed * dt)), "wrist_speed_p95_cm_s": float(np.percentile(speed, 95)),
             "wrist_speed_max_cm_s": float(speed.max()), "elbow_bend_mean_deg": float(elbow.mean()),
             "elbow_bend_range_deg": float(elbow.max() - elbow.min()), "endpoint_gap_cm": gap}
        m["wrist_plausible"] = bool(m["wrist_speed_p95_cm_s"] < WRIST_P95_SPEED and m["wrist_speed_max_cm_s"] < WRIST_MAX_SPEED)
        hands[hand] = m
        parts += [min(1.0, (l1 / max(ip, 1e-6)) / 0.5) if l1 > 0 else 0.0, moving / 15.0, float(m["wrist_plausible"])]
    left_elbow = hands["Left"]["elbow_bend_range_deg"]
    gap = max(h["endpoint_gap_cm"] for h in hands.values())
    parts += [min(1.0, left_elbow / ELBOW_MIN_RANGE), 1.0 / (1.0 + gap / 2.0)]
    flags = [f"{h} hook" for h, m in hands.items() if m["hooked"]]
    flags += [f"{h} <15 moving finger joints" for h, m in hands.items() if m["moving_finger_joints_gt_2deg"] < 15]
    flags += [f"{h} implausible wrist" for h, m in hands.items() if not m["wrist_plausible"]]
    if left_elbow < ELBOW_MIN_RANGE:
        flags.append("left elbow nearly straight-locked")
    return {"start": float(times[a]), "end": float(times[b]), "score": float(np.mean(parts)),
            "loop_gap_cm": gap, "flags": flags, "hands": hands}


def scan_segments(captures=None, lengths=(3.0, 4.0, 5.0, 6.0), stride=1, top=8):
    """Slide windows over every capture (stride in frames; the captures are 30 fps) and rank them.
    Top windows are de-duplicated: a window overlapping a better one by more than half is skipped."""
    captures = TYPING_CAPTURES if captures is None else captures
    windows, inputs, seen = [], {}, {}
    for name, path in captures.items():
        clip = load_clip(path)
        series, times = frame_series(clip)
        inputs[name] = {"path": str(Path(path).relative_to(ROOT)) if Path(path).is_relative_to(ROOT) else str(path),
                        "sha256": clip.rig.dump["sha256"], "duration": float(times[-1]), "frames": len(times)}
        twin = next((other for other, (s2, t2) in seen.items() if len(t2) == len(times) and np.allclose(t2, times)
                     and all(np.allclose(series[h][k], s2[h][k], atol=1e-4) for h in HANDS for k in ("l1", "ip", "elbow", "wrist"))), None)
        seen[name] = (series, times)
        if twin is not None:
            inputs[name]["duplicate_of"] = twin  # same motion (e.g. the staged clip is a rest-identical retarget)
            continue
        if times[-1] < min(lengths):
            inputs[name]["skipped"] = "shorter than the shortest window"
            continue
        for length in lengths:
            for a in range(0, len(times), stride):
                b = int(np.searchsorted(times, times[a] + length - 1e-6))
                if b >= len(times):
                    break
                w = score_window(series, times, a, b)
                w.update(capture=name, length=length)
                windows.append(w)
    windows.sort(key=lambda w: (-w["score"], w["capture"], w["start"], w["length"]))
    best = []
    for w in windows:
        if all(o["capture"] != w["capture"] or
               min(o["end"], w["end"]) - max(o["start"], w["start"]) <= 0.5 * min(o["length"], w["length"]) for o in best):
            best.append(w)
        if len(best) >= top:
            break
    reference = {}
    for i, w in enumerate(windows):
        if w["capture"] in ("typing", "room_mx_typing") and w["length"] == 5.0 and abs(w["start"] - 3.0) < 1e-3:
            reference[w["capture"]] = {**w, "rank": i + 1, "of": len(windows)}
    # the least hooked left hand among windows whose left elbow genuinely bends
    bending = [w for w in windows if w["hands"]["Left"]["elbow_bend_range_deg"] >= ELBOW_MIN_RANGE]
    least_hook = sorted(bending, key=lambda w: (w["hands"]["Left"]["ip_to_l1_ratio"], w["start"]))[:3]
    return {"inputs": inputs, "windows_scored": len(windows), "lengths_s": list(lengths), "stride_frames": stride,
            "thresholds": {"hook_ratio": HOOK_RATIO, "left_elbow_min_range_deg": ELBOW_MIN_RANGE,
                           "wrist_p95_cm_s": WRIST_P95_SPEED, "wrist_max_cm_s": WRIST_MAX_SPEED},
            "top": best, "reference_3_8s": reference, "least_left_hook_with_bending_elbow": least_hook,
            "windows_without_flags": sum(not w["flags"] for w in windows),
            "note": "Joint data only; candidates need native first-person visual and contact review."}


def to_jsonable(x):
    if isinstance(x, dict):
        return {str(k): to_jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [to_jsonable(v) for v in x]
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, (np.floating, np.integer, np.bool_)):
        return x.item()
    return x


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("report", "candidate", "segments"))
    ap.add_argument("--output")
    ap.add_argument("--step", type=int, default=5)
    args = ap.parse_args(argv)
    default = Path(tempfile.gettempdir()) / f"sub01-finger-{args.command}.json"
    output = Path(args.output) if args.output else default
    if args.command == "report":
        data = build_report(args.step)
    elif args.command == "segments":
        data = scan_segments()
    else:
        data = candidate_data()
    output.write_text(json.dumps(to_jsonable(data), indent=1) + "\n")
    print(json.dumps({"output": str(output)}))
    return output


if __name__ == "__main__":
    main()
