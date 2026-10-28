"""Walk metrics for the room's walk clips: the reference foot speed, cycle time and stride length a clip is played at,
measured from the clip itself, and the contact, slide and loop-seam checks.

The exporters (ardy_to_boy.mjs, boy_post.mjs) run this module on the GLB they write, and qa.py (--glb, or the Kimodo
path) runs it too: one implementation for the sidecars and for the check. The definitions:
  planted joint   a foot's ankle (Foot) or ball (ToeBase) joint.
  floor           the lowest height of that joint over the clip (the clip's own floor: no rig convention is assumed).
  contact         a joint is planted while it is within CONTACT_ON_M of its floor (released above CONTACT_OFF_M:
                  hysteresis, circular over the loop) and moving backward along the walk. Backward is the stance direction,
                  found from the swinging joints, so a swinging foot that passes the stance height is not planted. Gaps of
                  up to MAX_GAP frames close, and contacts shorter than MIN_RUN frames are dropped. A foot is planted while
                  its ankle or its ball is.
  reference foot speed (m/s)  the mean horizontal speed of a planted joint over the frame pairs (k, k+1) in which it stays
                  planted, pooled over both feet and both joints. An in-place clip (its hips travel less than 5 cm over the
                  loop) is read in its own frame; a travelling clip is read relative to its hips.
  loop (s)        the clip's loop as a player wraps it: its last key time to its first. The wrap takes no time.
  cycle time (s)  the loop over the touchdowns per foot per loop (onsets of foot contact, circular; the smaller count of
                  the two feet).
  stride length (m)  reference foot speed x cycle time: the distance the body travels in one gait cycle.
  slide (m)       the largest drift of a planted joint from where its contact began, in the page's frame. An in-place clip
                  is played with the body moving forward at the reference speed, so under a planted foot the joint moves
                  backward at exactly that speed in the clip; a travelling clip is judged in world coordinates. A contact
                  crossing the loop's wrap is unwrapped: the wrap's jump is the seam, reported separately.
  seamFeetM (m)   the largest jump of a planted joint between the loop's last and first frames: the foot's pop at the wrap.
  seam_pop (m)    (qa.py, the whole body) the largest joint displacement between a loop's last and first pose, with the
                  hips' travel taken out.
"""
import json
import struct
from pathlib import Path

import numpy as np

CONTACT_ON_M = 0.01      # a joint is planted within 1 cm of its floor (the contact tolerance)
CONTACT_OFF_M = 0.02     # released only above 2 cm (hysteresis)
SLIDE_MAX_M = 0.01       # a planted joint drifts at most 1 cm from its straight contact path
SEAM_POP_MAX_M = 0.01    # the last pose of a loop is within 1 cm of its first pose
REF_TOL = 0.05           # sidecar values agree with the clip within 5%

# the joints of the three rigs the walk clips are on: boy.glb (ARDY, UAL), v5 (room_walk), the Mixamo rig (room_walk)
RIGS = {
    "boy": {"L": ("LeftFoot", "LeftToeBase"), "R": ("RightFoot", "RightToeBase"), "hips": "Hips"},
    "v5": {"L": ("L_Foot", "L_ToeBase"), "R": ("R_Foot", "R_ToeBase"), "hips": "Hip"},
    "mixamo": {"L": ("mixamorig:LeftFoot", "mixamorig:LeftToeBase"), "R": ("mixamorig:RightFoot", "mixamorig:RightToeBase"),
               "hips": "mixamorig:Hips"},
}


def _hysteresis(h, on, off):
    """Hysteresis on a height above the floor, circular over one loop. h: (F,) metres."""
    h = np.asarray(h, float)
    n = len(h)
    if np.all(h <= on):
        return np.ones(n, bool)
    state = False
    out = np.zeros(n, bool)
    k0 = int(np.argmax(h))                  # the highest frame is off; start the scan there
    for j in range(n):
        k = (k0 + j) % n
        state = bool(h[k] <= off) if state else bool(h[k] <= on)
        out[k] = state
    return out


MIN_RUN = 3          # a contact shorter than 3 frames is noise
MAX_GAP = 2         # a gap of at most 2 frames inside one contact is the same contact (no fragmenting at the threshold)


def planted_mask(h, back, on=CONTACT_ON_M, off=CONTACT_OFF_M):
    """A joint is planted while it is low (hysteresis on its height above the floor) AND moving backward (back: (F,)
    bool, the stance direction). The second test keeps a swinging foot that passes through the stance height from
    counting as planted. Gaps of up to MAX_GAP frames are closed and runs shorter than MIN_RUN dropped."""
    m = _hysteresis(h, on, off) & np.asarray(back, bool)
    n = len(m)
    if not m.any() or m.all():
        return m
    s = int(np.nonzero(m & ~np.roll(m, 1))[0][0])     # an onset: rotate so that the sequence starts on a planted frame
    r = np.roll(m, -s)
    out = r.copy()
    j = 0
    while j < n:                                      # close the off-gaps of at most MAX_GAP frames (r[0] is planted,
        if not r[j]:                                  # so a gap at the end of r is circularly inside the contact too)
            k = j
            while k < n and not r[k]:
                k += 1
            if k - j <= MAX_GAP:
                out[j:k] = True
            j = k
        else:
            j += 1
    keep = np.zeros(n, bool)
    for run in _runs(out):                            # drop the contacts shorter than MIN_RUN frames
        if len(run) >= MIN_RUN:
            keep[run] = True
    return np.roll(keep, s)


def _dt(times):
    """Time from frame k to k+1 of the loop. The wrap from the last frame to the first takes no time: a player jumps
    there (the closing frame repeats the first pose), so the wrap adds nothing to any run's clock."""
    n = len(times)
    dtc = np.empty(n)
    dtc[:-1] = np.diff(times)
    dtc[-1] = 0.0
    return dtc


def _pair_speed(times, rel, planted):
    """Speeds of a joint relative to the hips over the frame pairs (k, k+1) of the loop in which it stays planted. The
    pairs do not wrap: the closing frame of a loop repeats its first, and the wrap is not a step of the walk."""
    times = np.asarray(times, float)
    v = np.linalg.norm(rel[1:] - rel[:-1], axis=1) / np.diff(times)
    both = planted[1:] & planted[:-1]
    return v[both]


def _runs(mask):
    """Contiguous runs of True in a circular mask as lists of frame indices (the run that wraps is joined)."""
    n = len(mask)
    if not mask.any():
        return []
    if mask.all():
        return [list(range(n))]
    start = int(np.nonzero(mask & ~np.roll(mask, 1))[0][0])
    runs, cur = [], []
    for j in range(n):
        k = (start + j) % n
        if mask[k]:
            cur.append(k)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    return runs


def measure_walk(times, joints, hips):
    """times (F,) uniform seconds over one loop; joints: {"L": {"Foot": (F,3), "ToeBase": (F,3)}, "R": {...}} metres;
    hips (F,3) metres. The clips walk along +z. Returns the measured metrics (see the module doc). A clip whose hips
    travel less than 5 cm over its loop is in place: the page moves the body, so its planted joints are judged at the
    measured reference speed; otherwise they are judged in world coordinates."""
    times = np.asarray(times, float)
    hips = np.asarray(hips, float)
    F = len(times)
    loop = float(times[-1] - times[0])             # the loop as a player wraps it: the last key to the first (see the doc)
    dtc = _dt(times)                               # time from frame k to k+1 (the wrap takes none)
    dtcent = np.roll(dtc, 1) + dtc                 # the centred difference spans frames k-1 .. k+1
    travel = float(np.linalg.norm(hips[-1, [0, 2]] - hips[0, [0, 2]]))
    in_place = travel < 0.05
    # the walk's direction in the clip's frame: the swinging joints go forward, so their mean horizontal velocity
    # (joints more than 3 cm off the floor) gives it; the rigs' facing differs (v5's root turns it onto x)
    parts = {}
    for side in ("L", "R"):
        for part in ("Foot", "ToeBase"):
            p = np.asarray(joints[side][part], float)
            parts[(side, part)] = (p, p[:, 1] - p[:, 1].min())
    swing = np.zeros(2)
    for p, h in parts.values():
        v = (np.roll(p[:, [0, 2]], -1, axis=0) - np.roll(p[:, [0, 2]], 1, axis=0)) / dtcent[:, None]
        swing += v[h > 0.03].sum(axis=0)
    fwd = swing / np.linalg.norm(swing) if np.linalg.norm(swing) > 1e-9 else np.array([0.0, 1.0])
    speeds, foot_planted, tracks = [], {}, []
    for side in ("L", "R"):
        foot_planted[side] = np.zeros(F, bool)
        for part in ("Foot", "ToeBase"):
            p, h = parts[(side, part)]
            # in place the clip's own frame is the body's: the planted joint moves backward in it at the walk's pace;
            # a travelling clip is read from its hips, whose travel is in its positions
            basis = p[:, [0, 2]] if in_place else p[:, [0, 2]] - hips[:, [0, 2]]
            vf = ((np.roll(basis, -1, axis=0) - np.roll(basis, 1, axis=0)) / dtcent[:, None]) @ fwd
            c = planted_mask(h, vf < 0)
            speeds.extend(_pair_speed(times, basis, c).tolist())
            foot_planted[side] |= c
            tracks.append((p, c))
    ref = float(np.mean(speeds)) if speeds else float("nan")
    # slide: the drift of a planted joint from where its contact began, in the page's frame (see the module doc)
    slide = 0.0
    seam = 0.0
    for p, c in tracks:
        seam = max(seam, float(np.linalg.norm(p[0] - p[-1])))
        for run in _runs(c):
            if len(run) < 5:
                continue
            run = run[1:-1]                      # the frames where the joint crosses the threshold are not the contact
            pos = p[run][:, [0, 2]].copy()
            if 0 in run and (len(run) > 1) and run.index(0) > 0:
                # a contact across the loop seam: take the seam's jump out, it is reported as the seam pop
                j = run.index(0)
                pos[j:] -= (p[0, [0, 2]] - p[-1, [0, 2]])
            if in_place:
                tt = np.r_[0.0, np.cumsum(dtc[run])[:-1]]   # the clock at each frame of the run (the step that reaches it)
                traj = pos + np.outer(tt * ref, fwd)     # the body moves forward at the walk's pace under a planted foot
            else:
                traj = pos
            slide = max(slide, float(np.linalg.norm(traj - traj[0], axis=1).max()))
    touch = {}
    for side in ("L", "R"):
        f = foot_planted[side]
        touch[side] = int((f & ~np.roll(f, 1)).sum())
    n_cycle = min(touch.values())
    cycle = loop / n_cycle if n_cycle else float("nan")
    return {"refFootSpeed": round(ref, 4), "cycleTime": round(cycle, 4), "strideLength": round(ref * cycle, 4),
            "touchdowns": touch, "slideM": round(slide, 4), "seamFeetM": round(seam, 4), "inPlace": bool(in_place),
            "frames": F, "loopS": round(loop, 4)}


def seam_pop(first, last, hips_first, hips_last):
    """first, last: (J,3) poses of one loop's first and last frames; hips_*: (3,). The largest joint displacement of
    the pose across the seam, the travel of the hips taken out."""
    a = np.asarray(first, float) - np.asarray(hips_first, float) * np.array([1, 0, 1])
    b = np.asarray(last, float) - np.asarray(hips_last, float) * np.array([1, 0, 1])
    return round(float(np.linalg.norm(b - a, axis=1).max()), 4)


def compare_meta(measured, meta, tol=REF_TOL):
    """The sidecar's fields against the measured clip: relative error above tol is a failure. Returns a list of text."""
    bad = []
    for key in ("refFootSpeed", "cycleTime", "strideLength"):
        if key not in meta:
            bad.append(f"{key}: missing from the sidecar")
            continue
        m, s = measured[key], float(meta[key])
        err = abs(s - m) / m if m else float("inf")
        if err > tol:
            bad.append(f"{key}: sidecar {s:.4f} vs clip {m:.4f} ({err * 100:.1f}% > {tol * 100:.0f}%)")
    return bad


# ---------- reading a GLB clip (no meshopt: the room's walk GLBs written by glTF-Transform without it)
_CT = {5120: ("b", 127.0), 5121: ("B", 255.0), 5122: ("h", 32767.0), 5123: ("H", 65535.0), 5125: ("I", None), 5126: ("f", None)}
_NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def _qmul(a, b):
    """Hamilton product of xyzw quaternions (the same as rt.py's)."""
    ax, ay, az, aw = np.moveaxis(a, -1, 0)
    bx, by, bz, bw = np.moveaxis(b, -1, 0)
    return np.stack([aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz], -1)


def _qrot(q, v):
    u = q[..., :3]
    w = q[..., 3:4]
    t = 2 * np.cross(u, v)
    return v + w * t + np.cross(u, t)


def _glb(path):
    raw = Path(path).read_bytes()
    if raw[:4] != b"glTF":
        raise ValueError(f"{path}: not a GLB")
    n, _ = struct.unpack_from("<I4s", raw, 12)
    doc = json.loads(raw[20:20 + n])
    bn, bk = struct.unpack_from("<I4s", raw, 20 + n)
    if bk != b"BIN\x00":
        raise ValueError(f"{path}: no BIN chunk")
    return doc, raw[28 + n:28 + n + bn]


def _accessor(doc, binc, idx):
    a = doc["accessors"][idx]
    if "EXT_meshopt_compression" in doc["bufferViews"][a["bufferView"]].get("extensions", {}):
        raise ValueError("meshopt-compressed clip: measure the walk before compression (boy_post.mjs writes an "
                         "uncompressed copy for it), or decode the buffers first")
    bv = doc["bufferViews"][a["bufferView"]]
    fmt, scale = _CT[a["componentType"]]
    nc = _NC[a["type"]]
    itemsize = struct.calcsize("<" + fmt)
    stride = bv.get("byteStride") or itemsize * nc
    base = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    out = np.empty((a["count"], nc))
    for i in range(a["count"]):
        out[i] = struct.unpack_from("<" + fmt * nc, binc, base + i * stride)
    if a.get("normalized") and scale:
        out = np.maximum(out / scale, -1.0)
    return out


def read_glb(path, rig="boy", anim_name=None):
    """(times, joints, hips) of one animation of a GLB (the first, or the one named anim_name) on its node tree, on one
    uniform grid, for a RIGS preset."""
    qmul, qrot = _qmul, _qrot
    doc, binc = _glb(path)
    nodes = doc["nodes"]
    names = [n.get("name", f"node{i}") for i, n in enumerate(nodes)]
    idx = {n: i for i, n in enumerate(names)}
    parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}
    anims = [a for a in doc["animations"] if anim_name is None or a.get("name") == anim_name]
    if not anims:
        raise ValueError(f"{path}: no animation named {anim_name!r}")
    anim = anims[0]
    tracks = {}
    for ch in anim["channels"]:
        s = anim["samplers"][ch["sampler"]]
        tin = _accessor(doc, binc, s["input"])[:, 0]
        vout = _accessor(doc, binc, s["output"])
        if s.get("interpolation", "LINEAR") == "CUBICSPLINE":
            vout = vout.reshape(len(tin), 3, -1)[:, 1]
        tracks.setdefault(ch["target"]["node"], {})[ch["target"]["path"]] = (tin, vout)
    union = np.unique(np.round(np.concatenate([tv[0] for d in tracks.values() for tv in d.values()]), 7))
    step = float(np.median(np.diff(union)))
    F = int(round((union[-1] - union[0]) / step)) + 1
    grid = union[0] + step * np.arange(F)
    for nd in tracks:
        for p, (tin, vout) in list(tracks[nd].items()):
            v = np.stack([np.interp(grid, tin, vout[:, c]) for c in range(vout.shape[1])], 1)
            if p == "rotation":
                v = v / np.linalg.norm(v, axis=1, keepdims=True)
            tracks[nd][p] = v

    cache = {}

    def world(i):
        if i in cache:
            return cache[i]
        n = nodes[i]
        tr = tracks.get(i, {})
        T = tr.get("translation", np.tile(np.array(n.get("translation", [0, 0, 0]), float), (F, 1)))
        R = tr.get("rotation", np.tile(np.array(n.get("rotation", [0, 0, 0, 1]), float), (F, 1)))
        S = tr.get("scale", np.tile(np.array(n.get("scale", [1, 1, 1]), float), (F, 1)))
        R = R / np.linalg.norm(R, axis=1, keepdims=True)
        if i in parent:
            pT, pR, ps = world(parent[i])
            cache[i] = (pT + qrot(pR, ps[:, None] * T), qmul(pR, R), ps * S[:, 0])
        else:
            cache[i] = (T, R, S[:, 0])
        return cache[i]

    preset = RIGS[rig]
    joints = {side: {part: world(idx[preset[side][k]])[0] for k, part in enumerate(("Foot", "ToeBase"))} for side in ("L", "R")}
    hips = world(idx[preset["hips"]])[0]
    return grid, joints, hips


SIDECAR_VERSION = 1


def sidecar_from_measure(m, file_name, clip, rig):
    """The walk block of a clip's sidecar from measure_walk's result m (see the module doc for each field)."""
    return {"version": SIDECAR_VERSION, "file": file_name, "clip": clip, "rig": rig,
            "refFootSpeed": m["refFootSpeed"], "cycleTime": m["cycleTime"], "strideLength": m["strideLength"],
            "checks": {"slideM": m["slideM"], "seamFeetM": m["seamFeetM"], "inPlace": m["inPlace"],
                       "touchdowns": m["touchdowns"], "loopS": m["loopS"], "frames": m["frames"],
                       "contactOnM": CONTACT_ON_M, "contactOffM": CONTACT_OFF_M}}


def sidecar(path, rig="boy", anim_name=None):
    """The walk block of a clip's sidecar, measured from the GLB itself."""
    t, j, h = read_glb(path, rig, anim_name)
    return sidecar_from_measure(measure_walk(t, j, h), Path(path).name, anim_name, rig)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Measure a walk GLB (no meshopt): the reference foot speed, cycle time and "
                                             "stride length, and the slide and seam checks; optionally write the sidecar.")
    ap.add_argument("glb")
    ap.add_argument("--rig", default="boy", choices=sorted(RIGS))
    ap.add_argument("--anim", default=None, help="the animation's name (default: the first one)")
    ap.add_argument("--sidecar", default=None, help="write the walk block to this JSON file")
    a = ap.parse_args()
    out = sidecar(a.glb, a.rig, a.anim)
    if a.sidecar:
        Path(a.sidecar).write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out))
