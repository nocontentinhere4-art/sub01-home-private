"""Bed transition pipeline for the owner: lie down -> sleep loop -> get up (private; CPU only).

    python3 tools/bed_transition_pipeline.py OUT_DIR [--blend-frames 24] [--sleep sleep_side,sleep_back,sleep_back_idle]
        [--owner web/room/char_mixamo.glb] [--work DIR] [--write-glb] [--no-soles]

What it does, from repository files only (nothing is downloaded, posed, keyed or IK-solved):

1. Provenance. Every source file is hashed (sha256). The documented facts are QUOTED from the
   repository's own READMEs and CREDITS and each quote is checked to be present verbatim in the file
   it is attributed to; a missing quote fails the run. What is not documented is listed as such.
2. Retarget from the v5-rig ORIGINALS (web/room/mh_v5/room_bed_lie.glb, room_bed_wake.glb), not the
   mh_mx copies that carry a translation track on every bone. The retarget is the existing
   tools/retarget_first_person.mjs (unchanged), prepared by tools/retarget_life_clip.py's own
   mapping_for()/prepare_source() (v5 preset, rest re-basing; imported read-only). The owner's local
   translations are kept exactly (bone lengths exact); only captured rotations and the hips' captured
   world delta (scaled by the measured leg ratio) are used. Owner joints the source lacks (finger
   tips, HeadTop_End, Toe_End) hold the owner's rest: no finger pose is invented.
3. Root travel. The hips' horizontal trajectory is kept as captured (smooth, frame by frame). It is
   reported as a CharacterMovement path in the component frame (forward / right / up, cm), with
   speed, acceleration and a per-frame support class (floor / transitional / bed). The get-up is
   cropped where the measured standing capture begins (standing condition reached and held), before
   the later walk, so no 1.9 m walk is carried into the bed transition.
4. Sleep loops (Sova, PRIVATE, preview licence accepted by the owner): an exhaustive search over
   the lie-down's lying frames x the loop's phases x the get-up's lying frames for the minimal
   hips-relative joint distance, velocity mismatch and gravity-attitude difference. A standard
   captured-pose blend (slerp of captured local rotations, smoothstep weight, N frames) joins them;
   the loop is rigidly re-placed (yaw about vertical + translation, fitted by 2D Kabsch) so the root
   is continuous. Gaps are measured BEFORE (direct cut and best match) and AFTER (the composed
   sequence). A gap beyond a plausible blend (> 10 cm hips-relative, > 30 deg attitude, or a posture
   class change such as side <-> back) is REFUSED and the needed transition clip is named.
5. Reports: one JSON per clip plus a pipeline JSON. GLBs only with --write-glb.

Numbers here are measured on the clips; nothing is tuned to pass. Nothing here verifies the bed
(see tools/fit_bed_placement.py and tools/unreal_bed_surface_audit.py).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import life_gltf as G  # noqa: E402  (read-only import)
import verify_life_idle_candidate as V  # noqa: E402  (read-only import)
import retarget_life_clip as R  # noqa: E402  (read-only import)
import validate_unreal_seat_contact as C  # noqa: E402  (read-only import: the contact bands)

SCHEMA_CLIP = 'sub01.bed-transition-clip.v1'
SCHEMA_PIPELINE = 'sub01.bed-transition-pipeline.v1'
FPS = 30.0
OWNER = ROOT / 'web/room/char_mixamo.glb'
SOURCES = {
    'LieDown': ROOT / 'web/room/mh_v5/room_bed_lie.glb',
    'GetUp': ROOT / 'web/room/mh_v5/room_bed_wake.glb',
}
CARRIED_COPIES = {           # the drifted owner-skeleton copies, measured for comparison only
    'LieDown': ROOT / 'web/room/mh_mx/room_bed_lie.glb',
    'GetUp': ROOT / 'web/room/mh_mx/room_bed_wake.glb',
}
SLEEP_LOOPS = {
    'sleep_side': ROOT / 'web/room/desk_states/bed/sleep_side.glb',
    'sleep_back': ROOT / 'web/room/desk_states/bed/sleep_back.glb',
    'sleep_back_idle': ROOT / 'web/room/desk_states/bed/sleep_back_idle.glb',
}
# Stated criteria (not tuned to a result).
BLEND_FRAMES = 24                       # 0.8 s: the bed layer's existing crossfade (web/room/desk_states/README.md)
PLAUSIBLE_POSE_CM = 10.0                # hips-relative joint distance a blend may bridge
PLAUSIBLE_ATTITUDE_DEG = 30.0           # gravity direction in the hips frame (side vs back is ~90)
PLAUSIBLE_VELOCITY_CM_S = 50.0          # hips-relative joint velocity mismatch at the blend start
STANDING_EXTENSION_OF_REST = 0.95       # leg extension >= 0.95 x the owner's rest extension (rest ~1.07)
STANDING_MAX_TILT_DEG = V.STANDING_MAX_TILT_DEG
STANDING_HOLD_S = 0.3                   # standing must hold this long (or until a walk begins)
SETTLED_SPEED_CM_S = 10.0               # hips horizontal speed of a settled stance
WALK_SPEED_CM_S = 20.0                  # a walk: hips horizontal speed above this ...
WALK_HOLD_S = 0.5                       # ... as a mean over this window (a gait cycle's dips do not end it)
LYING_MIN_TILT_DEG = 60.0               # candidate blend frames: torso at least this far from vertical
TELEPORT_STEP_CM = 10.0                 # one-frame hips step at 30 fps = 3 m/s: a discontinuity
BED_SLIDE_SPEED_CM_S = 50.0             # horizontal hips speed while on the bed reported as implausible

# ------------------------------------------------------------------ provenance
# (file, exact text) pairs: each is checked to be present verbatim. Nothing beyond them is claimed.
DOCUMENTED = [
    ('web/room/mh_mx/README.md', "**v5's room clips carried over** by `room_build/kimodo/mx_convert.mjs` (no Mixamo capture of these yet):"),
    ('web/room/mh_mx/README.md', '`desk_mouse_ik`, `room_walk`, `room_window`, `room_bed_lie`, `room_bed_wake`, `room_bedtime`'),
    ('web/room/CREDITS.md', "| `mh_v5/*.glb` (the room clips retargeted onto v5, by G14; the same names as preview/room-mh's `mh/`) | preview/mh-motion's clips, retargeted | as their sources |"),
    ('web/room/mh_v5/README.md', "| room_window, room_walk, room_sit_down, room_stand_up, room_bed_lie, room_bed_wake, room_door, room_bedtime | G12 (to come). G10d's QA ran with local stand-ins (room-mh's clips through G14's `mh_retarget.mjs` cc57630, default options), not committed |"),
    ('docs/design/room-v5/README.md', '**The ones here now are placeholders**: room-mh\'s clips run through that script as it is at ef9c0e4.'),
    ('docs/design/room-v5/README.md', '- **His motion:** 16 mocap clips retargeted onto him (`web/room/mh_v5/`, G14 and G12)'),
    ('room_build/kimodo/mh_retarget.mjs', '// 3) zero-phase smoothing (Gaussian, sigma 1 frame limbs / 1.7 spine-neck-head), then two-bone IK: the wrists onto the'),
    ('room_build/kimodo/mixamo_clips.json', '"Sleeping_Idle": {'),
    ('room_build/kimodo/mixamo_clips.json', '"Laying_Sleeping": {'),
    ('docs/design/mixamo/README.md', '| Sleeping_Idle → `room_sleeping_idle.glb` | 17.6 s; curled on his side; turns over and back (head 85°, arms 100°)'),
    ('web/room/desk_states/README.md', 'SovaSims animations used with the author\'s permission (confirmed by the owner, 2026-10-08).'),
    ('web/room/desk_states/README.md', 'licence is pending, so they never go to main.'),
    ('web/room/desk_states/README.md', '- **Asleep:** `sleep_side`; after 40-90 s `sleep_roll_to_back` (once), then `sleep_back` and `sleep_back_idle` taking turns.'),
]
PROVENANCE = {
    'LieDown': {
        'source_used': 'web/room/mh_v5/room_bed_lie.glb (v5 rig, 80 nodes, one animation room_bed_lie)',
        'chain_documented': [
            'preview/mh-motion clip on the MakeHuman rig (CREDITS: "preview/mh-motion\'s clips, retargeted")',
            'retargeted onto v5 by room_build/kimodo/mh_retarget.mjs (G14; mh_v5/README: "room-mh\'s clips through G14\'s '
            '`mh_retarget.mjs` cc57630, default options"), which applies Gaussian smoothing and two-bone wrist/ankle IK',
            'carried onto the owner skeleton by room_build/kimodo/mx_convert.mjs as web/room/mh_mx/room_bed_lie.glb '
            '(the drifted copy, NOT used here)',
        ],
        'documented_as': 'docs/design/room-v5/README.md calls the v5 set "16 mocap clips" and, in the contract, "placeholders"',
        'not_documented': [
            'how the preview/mh-motion clip was made (motion capture, keyframed, or generated): no README, licence or '
            'generation script for it is in this repository; the branch is not in this repository\'s history',
            'the performer, capture system, or original file (BVH/FBX) and its hash',
            'any Mixamo capture of lying down: room_build/kimodo/mixamo_clips.json has no lie-down or get-up row '
            '(mh_mx/README: "no Mixamo capture of these yet")',
        ],
        'verdict': 'ProvenanceUnverified: a documented repository chain back to a v5-rig placeholder; the origin before '
                   'preview/mh-motion is undocumented. Not upgraded to "genuine capture".',
    },
    'GetUp': {
        'source_used': 'web/room/mh_v5/room_bed_wake.glb (v5 rig, 80 nodes, one animation room_bed_wake)',
        'chain_documented': [
            'as LieDown: preview/mh-motion -> mh_retarget.mjs (smoothing + IK) -> mh_v5; mx_convert.mjs -> mh_mx copy (not used)',
        ],
        'documented_as': 'as LieDown',
        'not_documented': ['as LieDown'],
        'verdict': 'ProvenanceUnverified (as LieDown).',
    },
    'SleepLoop': {
        'source_used': 'web/room/desk_states/bed/<loop>.glb (owner skeleton, exact rest)',
        'chain_documented': ["G23's Sova bed clips (preview/sova-phone-src docs/qa/sova/mattina/bed); "
                             "SovaSims animations used with the author's permission (confirmed by the owner, 2026-10-08)"],
        'licence': 'preview-only permission; desk_states/README: "licence is pending, so they never go to main". '
                   'PRIVATE use only; never public, never main.',
        'not_documented': ['the capture method', 'the original files and their hashes'],
        'verdict': 'Permissioned private preview clips; capture method undocumented.',
    },
    'related_genuine_mixamo_on_v5_not_transitions': {
        'files': ['web/room/mh_v5/room_sleeping_idle.glb (Mixamo Sleeping_Idle)',
                  'web/room/mh_v5/room_laying_sleeping.glb (Mixamo Laying_Sleeping)',
                  'web/room/mh_v5/room_laying_nodding.glb (Mixamo Laying_Nodding)'],
        'note': 'Genuine Mixamo captures per room_build/kimodo/mixamo_clips.json, but they are lying LOOPS / a rare '
                'event, fitted by kimodo_g12/bed_fit.py; none is a lie-down or a get-up, so none is a source for them.',
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rel(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def check_documented(root: Path = ROOT):
    rows = []
    for f, text in DOCUMENTED:
        p = root / f
        present = p.is_file() and text in p.read_text(errors='replace')
        rows.append({'file': f, 'quote': text, 'present_verbatim': present, 'file_sha256': sha256(p) if p.is_file() else None})
    return rows


REQUIRED_PROVENANCE_FIELDS = ('source_used', 'source_sha256', 'chain_documented', 'not_documented', 'verdict', 'quotes')


def validate_provenance(prov: dict):
    """A clip report without complete provenance is refused (fail closed)."""
    missing = [k for k in REQUIRED_PROVENANCE_FIELDS if not prov.get(k)]
    if missing:
        raise ValueError(f'provenance incomplete: missing {missing}')
    if not all(q.get('present_verbatim') for q in prov['quotes']):
        raise ValueError('provenance quote not found verbatim in its file: '
                         + ', '.join(q['file'] for q in prov['quotes'] if not q.get('present_verbatim')))
    if 'genuine' in prov['verdict'].lower() and 'not upgraded' not in prov['verdict'].lower():
        raise ValueError('provenance verdict may not claim a genuine capture without documentation')
    return True


# ------------------------------------------------------------------ numpy quaternions (x, y, z, w)
def qmul(a, b):
    ax, ay, az, aw = np.moveaxis(a, -1, 0)
    bx, by, bz, bw = np.moveaxis(b, -1, 0)
    return np.stack([aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz], axis=-1)


def qconj(q):
    return q * np.array([-1.0, -1.0, -1.0, 1.0])


def qrot(q, v):
    u = q[..., :3]
    w = q[..., 3:4]
    t = 2 * np.cross(u, v)
    return v + w * t + np.cross(u, t)


def qnormalize(q):
    return q / np.linalg.norm(q, axis=-1, keepdims=True)


def slerp(a, b, w):
    """Shortest-arc slerp, element-wise; w broadcasts over the leading axes."""
    a, b = qnormalize(a), qnormalize(b)
    d = np.sum(a * b, axis=-1, keepdims=True)
    b = np.where(d < 0, -b, b)
    d = np.abs(d)
    w = np.asarray(w, dtype=float)
    while w.ndim < a.ndim:
        w = w[..., None]
    theta = np.arccos(np.clip(d, -1.0, 1.0))
    s = np.sin(theta)
    small = s < 1e-6
    k0 = np.where(small, 1 - w, np.sin((1 - w) * theta) / np.where(small, 1, s))
    k1 = np.where(small, w, np.sin(w * theta) / np.where(small, 1, s))
    return qnormalize(k0 * a + k1 * b)


def qangle_deg(a, b):
    d = np.abs(np.sum(qnormalize(a) * qnormalize(b), axis=-1))
    return np.degrees(2 * np.arccos(np.clip(d, -1.0, 1.0)))


def yaw_quat(theta):
    return np.array([0.0, math.sin(theta / 2), 0.0, math.cos(theta / 2)])


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


# ------------------------------------------------------------------ owner skeleton and motions
class Skeleton:
    """The owner's 65 joints under the 0.01-scale `mixamo` node; positions in that node's units (cm)."""

    def __init__(self, owner_path: Path = OWNER):
        g = G.Gltf(owner_path)
        self.path, self.sha256 = Path(owner_path), g.sha256
        owner = V.Owner(g)
        self.names = R.topo(owner)
        self.index = {n: k for k, n in enumerate(self.names)}
        self.parent = np.array([self.index[owner.parent[n]] if owner.parent[n] else -1 for n in self.names])
        nodes = [owner.node[n] for n in self.names]
        self.rest_t = np.array([g.rest(i)[0] for i in nodes], dtype=float)
        self.rest_q = np.array([g.rest(i)[1] for i in nodes], dtype=float)
        root = g.parent[owner.node['Hips']]
        rt, rq, rs = g.rest(root)
        if max(abs(c) for c in rt) > 1e-9 or G.qangle_deg(rq, G.IDENTITY) > 1e-6:
            raise ValueError('owner structural root is translated or rotated; the cm frame assumes it is not')
        self.root_name = g.nodes[root].get('name')
        self.root_scale = sum(rs) / 3
        self.owner = owner
        rest = fk(self, self.rest_q[None], self.rest_t[self.index['Hips']][None])
        self.rest_pos = rest[0][0]
        self.leg_cm = (np.linalg.norm(self.rest_pos[self.index['LeftUpLeg']] - self.rest_pos[self.index['LeftLeg']])
                       + np.linalg.norm(self.rest_pos[self.index['LeftLeg']] - self.rest_pos[self.index['LeftFoot']]))
        feet = min(self.rest_pos[self.index['LeftFoot']][1], self.rest_pos[self.index['RightFoot']][1])
        self.rest_extension = (self.rest_pos[self.index['Hips']][1] - feet) / self.leg_cm
        right = self.rest_pos[self.index['RightUpLeg']] - self.rest_pos[self.index['LeftUpLeg']]
        right[1] = 0
        self.right = right / np.linalg.norm(right)
        self.up = np.array([0.0, 1.0, 0.0])
        self.forward = np.cross(self.up, self.right)

    def bone_lengths(self, pos):
        """(F, 65) parent-child distances (0 for the hips)."""
        p = self.parent.copy()
        p[p < 0] = 0
        d = np.linalg.norm(pos - pos[:, p], axis=-1)
        d[:, self.parent < 0] = 0
        return d


def fk(sk: Skeleton, local_q, hips_t, local_t=None):
    """World positions (cm, glTF axes) and rotations for local rotations (F,65,4) and hips translation (F,3).

    local_t (F,65,3), when given, replaces the owner's rest offsets (used only to MEASURE drifted copies)."""
    F = local_q.shape[0]
    pos = np.zeros((F, len(sk.names), 3))
    rot = np.zeros((F, len(sk.names), 4))
    for k, p in enumerate(sk.parent):
        t = hips_t if p < 0 else (local_t[:, k] if local_t is not None else np.broadcast_to(sk.rest_t[k], (F, 3)))
        if p < 0:
            pos[:, k] = t
            rot[:, k] = local_q[:, k]
        else:
            pos[:, k] = pos[:, p] + qrot(rot[:, p], t)
            rot[:, k] = qmul(rot[:, p], local_q[:, k])
    return pos, qnormalize(rot)


class Motion:
    """Local rotations of the 65 owner joints plus the hips translation, uniformly sampled."""

    def __init__(self, sk: Skeleton, local_q, hips_t, fps=FPS, name='clip', source=None, local_t=None):
        self.sk, self.q, self.t = sk, np.asarray(local_q, float), np.asarray(hips_t, float)
        self.tl = local_t                       # only for measuring drifted copies; never written
        self.fps, self.name, self.source = fps, name, source
        self._pos = None

    @classmethod
    def from_glb(cls, sk: Skeleton, path: Path, animation=None, name=None, keep_bone_translations=False):
        g = G.Gltf(path)
        clip = g.animation(animation)
        times = clip.key_times()
        steps = np.diff(times)
        if len(times) < 2 or steps.max() - steps.min() > 1e-3:
            raise ValueError(f'{path}: keys are not uniform')
        fps = 1 / float(np.median(steps))
        node = {}
        for i, n in enumerate(g.nodes):
            if V.PREFIX.match(n.get('name', '')) and 'mesh' not in n and V.canonical(n['name']) in sk.index:
                node.setdefault(V.canonical(n['name']), i)
        missing = sorted(set(sk.names) - set(node))
        if missing:
            raise ValueError(f'{path}: lacks owner joints {missing}')
        q = np.zeros((len(times), len(sk.names), 4))
        for k, n in enumerate(sk.names):
            rest_q = g.rest(node[n])[1]
            for f, t in enumerate(times):
                q[f, k] = clip.sample(node[n], 'rotation', t, rest_q)
        hips = node['Hips']
        hips_t = np.array([clip.sample(hips, 'translation', t, g.rest(hips)[0]) for t in times])
        tl = None
        if keep_bone_translations:
            tl = np.array([[clip.sample(node[n], 'translation', t, g.rest(node[n])[0]) for n in sk.names] for t in times])
        m = cls(sk, qnormalize(q), hips_t, fps, name or clip.name, str(path), tl)
        m.times = np.array(times)
        m.translation_drift_cm = translation_drift(g, clip, node, sk, times)
        return m

    def __len__(self):
        return len(self.q)

    @property
    def duration(self):
        return (len(self) - 1) / self.fps

    def world(self):
        if self._pos is None:
            self._pos = fk(self.sk, self.q, self.t, self.tl)
        return self._pos

    def slice(self, a, b):
        return Motion(self.sk, self.q[a:b], self.t[a:b], self.fps, self.name, self.source,
                      None if self.tl is None else self.tl[a:b])

    def placed(self, theta, offset):
        """The same captured motion rigidly re-placed: yaw theta about vertical, then translation (cm)."""
        y = np.broadcast_to(yaw_quat(theta), (len(self), 4))
        q = self.q.copy()
        q[:, 0] = qmul(y, q[:, 0])
        t = qrot(y, self.t) + np.asarray(offset)
        return Motion(self.sk, q, t, self.fps, self.name, self.source)


def translation_drift(g, clip, node, sk, times):
    """Max deviation (cm) of any NON-hips bone's local translation from the owner's rest offset, over the clip."""
    worst, who, length, tracks = 0.0, None, 0.0, 0
    for k, n in enumerate(sk.names):
        if n == 'Hips' or (node[n], 'translation') not in clip.tracks:
            continue
        tracks += 1
        tr = np.array(clip.tracks[(node[n], 'translation')][1])
        dev = float(np.max(np.linalg.norm(tr - sk.rest_t[k], axis=1)))
        length = max(length, float(np.max(np.abs(np.linalg.norm(tr, axis=1) - np.linalg.norm(sk.rest_t[k])))))
        if dev > worst:
            worst, who = dev, n
    return {'max_cm': round(worst, 4), 'bone': who, 'max_bone_length_change_cm': round(length, 4),
            'non_hips_translation_tracks': tracks,
            'unit': 'cm (the 0.01-scale mixamo node\'s units), local offset vs the owner\'s rest offset'}


# ------------------------------------------------------------------ pose features
def hips_relative(m: Motion):
    pos, rot = m.world()
    h = m.sk.index['Hips']
    inv = qconj(rot[:, h])[:, None, :]
    return qrot(np.broadcast_to(inv, pos.shape[:2] + (4,)), pos - pos[:, h:h + 1])


def velocities(x, fps, cyclic=False):
    """Central differences per frame (one-sided at the ends unless cyclic)."""
    if cyclic:
        return (np.roll(x, -1, axis=0) - np.roll(x, 1, axis=0)) * fps / 2
    v = np.gradient(x, axis=0) * fps
    return v


def body_axes(m: Motion):
    pos, _ = m.world()
    ix = m.sk.index
    x = pos[:, ix['RightUpLeg']] - pos[:, ix['LeftUpLeg']]
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    y = pos[:, ix['Spine2']] - pos[:, ix['Hips']]
    y -= x * np.sum(y * x, axis=1, keepdims=True)
    y /= np.linalg.norm(y, axis=1, keepdims=True)
    f = np.cross(y, x)
    return x, y, f


def posture(m: Motion):
    """Per frame: supine (belly up) / prone / side_left (lying on the left side) / side_right / upright / oblique."""
    x, y, f = body_axes(m)
    out = []
    for xr, yr, fr in zip(x[:, 1], y[:, 1], f[:, 1]):
        if yr > .6:
            out.append('upright')
        elif fr > .6:
            out.append('supine')
        elif fr < -.6:
            out.append('prone')
        elif xr > .6:
            out.append('side_left')
        elif xr < -.6:
            out.append('side_right')
        else:
            out.append('oblique')
    return out


def gravity_in_body(m: Motion):
    """Unit gravity direction in the anatomical body frame (lateral, long axis, front) per frame."""
    x, y, f = body_axes(m)
    g = np.array([0.0, -1.0, 0.0])
    return np.stack([x @ g, y @ g, f @ g], axis=1)


def torso_tilt_deg(m: Motion):
    pos, _ = m.world()
    ix = m.sk.index
    a = pos[:, ix['Head']] - pos[:, ix['Hips']]
    return np.degrees(np.arccos(np.clip(a[:, 1] / np.linalg.norm(a, axis=1), -1, 1)))


def leg_extension(m: Motion):
    pos, _ = m.world()
    ix = m.sk.index
    feet = np.minimum(pos[:, ix['LeftFoot'], 1], pos[:, ix['RightFoot'], 1])
    return (pos[:, ix['Hips'], 1] - feet) / m.sk.leg_cm


def standing_mask(m: Motion):
    return (torso_tilt_deg(m) <= STANDING_MAX_TILT_DEG) & (leg_extension(m) >= STANDING_EXTENSION_OF_REST * m.sk.rest_extension)


def hips_horizontal(m: Motion):
    pos, _ = m.world()
    return pos[:, m.sk.index['Hips']][:, [0, 2]]


def hips_speed(m: Motion):
    return np.linalg.norm(velocities(hips_horizontal(m), m.fps), axis=1)


# ------------------------------------------------------------------ crop detection
def detect_standing_crop(standing, speed, fps, hold_s=STANDING_HOLD_S, walk_speed=WALK_SPEED_CM_S,
                         walk_hold_s=WALK_HOLD_S, settled=SETTLED_SPEED_CM_S):
    """Where the measured standing capture begins, before any later walk.

    standing: bool per frame; speed: hips horizontal speed (cm/s) per frame.
    onset = first frame from which standing holds for hold_s (or until the clip ends / a walk begins).
    walk  = first frame at or after onset where speed > walk_speed for walk_hold_s.
    crop  = the first settled frame (speed <= settled) in [onset, walk), else onset.
    """
    standing = np.asarray(standing, bool)
    speed = np.asarray(speed, float)
    n = len(standing)
    hold = max(1, int(round(hold_s * fps)))
    whold = max(1, int(round(walk_hold_s * fps)))
    def walk_from(i):
        for k in range(i, n - whold + 1):
            if speed[k:k + whold].mean() > walk_speed and speed[k] > walk_speed:
                return k
        return None

    for i in range(n):
        if not standing[i]:
            continue
        w = walk_from(i)
        end = min(n, i + hold) if w is None else min(n, i + hold, w)
        if end - i < 1 or not standing[i:end].all():
            continue
        if w is not None and w - i < 1:
            continue
        if end - i < hold and end != n and (w is None or end != w):
            continue
        stop = w if w is not None else n
        settled_idx = next((k for k in range(i, stop) if standing[k] and speed[k] <= settled), None)
        crop = settled_idx if settled_idx is not None else i
        return {'onset_frame': i, 'walk_onset_frame': w, 'crop_frame': crop,
                'settled': settled_idx is not None,
                'rule': f'standing = torso tilt <= {STANDING_MAX_TILT_DEG} deg and leg extension >= '
                        f'{STANDING_EXTENSION_OF_REST} x owner rest; held >= {hold_s} s (or until a walk); walk = hips '
                        f'horizontal speed > {walk_speed} cm/s, and its mean over the next {walk_hold_s} s too; crop = first settled frame '
                        f'(<= {settled} cm/s) in [onset, walk), else the onset'}
    return None


# ------------------------------------------------------------------ root path
def root_path(m: Motion, support=None):
    """The hips' horizontal trajectory in the component frame (forward/right, cm, from frame 0) and its kinematics."""
    sk = m.sk
    pos, _ = m.world()
    h = pos[:, sk.index['Hips']]
    d = h - h[0]
    fwd = d @ sk.forward
    right = d @ sk.right
    xy = np.stack([fwd, right], axis=1)
    vel = velocities(xy, m.fps)
    acc = velocities(vel, m.fps)
    step = np.linalg.norm(np.diff(xy, axis=0), axis=1) if len(xy) > 1 else np.zeros(0)
    speed = np.linalg.norm(vel, axis=1)
    accn = np.linalg.norm(acc, axis=1)
    out = {
        'frame': 'component frame: forward = owner rest facing (+Z glTF), right = owner rest right (-X glTF), '
                 'up = +Y glTF; cm, relative to frame 0. UE character-local axes are X forward, Y right, Z up.',
        'frames': len(m), 'fps': m.fps,
        'path_length_cm': round(float(step.sum()), 3),
        'net_displacement_cm': [round(float(fwd[-1]), 3), round(float(right[-1]), 3)],
        'net_distance_cm': round(float(np.hypot(fwd[-1], right[-1])), 3),
        'max_speed_cm_s': round(float(speed.max()), 3), 'max_speed_at_s': round(float(np.argmax(speed) / m.fps), 4),
        'max_acceleration_cm_s2': round(float(accn.max()), 3), 'max_acceleration_at_s': round(float(np.argmax(accn) / m.fps), 4),
        'max_frame_step_cm': round(float(step.max()) if len(step) else 0.0, 4),
        'teleport_step_threshold_cm': TELEPORT_STEP_CM,
        'discontinuity': bool(len(step) and step.max() > TELEPORT_STEP_CM),
        'hips_height_cm': [round(float(h[:, 1].min()), 3), round(float(h[:, 1].max()), 3)],
    }
    if support is not None:
        segs, cur = [], None
        for k, s in enumerate(support):
            if cur is None or cur['support'] != s:
                cur = {'support': s, 'from_s': round(k / m.fps, 4), 'frames': 0, 'travel_cm': 0.0, 'max_speed_cm_s': 0.0}
                segs.append(cur)
            cur['frames'] += 1
            if k:
                cur['travel_cm'] += float(step[k - 1])
            cur['max_speed_cm_s'] = max(cur['max_speed_cm_s'], float(speed[k]))
        for s in segs:
            s['travel_cm'] = round(s['travel_cm'], 3)
            s['max_speed_cm_s'] = round(s['max_speed_cm_s'], 3)
            s['to_s'] = round(s['from_s'] + (s['frames'] - 1) / m.fps, 4)
        out['support_segments'] = segs
        bed = [s for s in segs if s['support'] == 'bed' and s['max_speed_cm_s'] > BED_SLIDE_SPEED_CM_S]
        out['implausible_bed_slides'] = bed
        out['floor_travel_cm'] = round(sum(s['travel_cm'] for s in segs if s['support'] == 'floor'), 3)
        out['non_floor_travel_cm'] = round(sum(s['travel_cm'] for s in segs if s['support'] != 'floor'), 3)
    out['_per_frame'] = {'t': [round(k / m.fps, 5) for k in range(len(m))],
                         'forward_cm': [round(float(v), 4) for v in fwd], 'right_cm': [round(float(v), 4) for v in right],
                         'hips_up_cm': [round(float(v), 4) for v in h[:, 1]],
                         'speed_cm_s': [round(float(v), 3) for v in speed],
                         'support': list(support) if support is not None else None}
    return out


def support_class(m: Motion):
    tilt, ext = torso_tilt_deg(m), leg_extension(m)
    standing = standing_mask(m)
    return ['floor' if s else ('bed' if (t > LYING_MIN_TILT_DEG or e < 0.6 * m.sk.rest_extension) else 'transitional')
            for s, t, e in zip(standing, tilt, ext)]


# ------------------------------------------------------------------ rigid re-placement (yaw + translation)
def fit_yaw_translation(a_pos, b_pos, anchor=None):
    """Yaw about vertical and translation taking joint positions b onto a (2D Kabsch on xz).

    Translation: the centroids (vertical by mean), or, with anchor=k, joint k of b onto joint k of a."""
    a, b = np.asarray(a_pos), np.asarray(b_pos)
    ac, bc = a.mean(0), b.mean(0)
    ax, az = a[:, 0] - ac[0], a[:, 2] - ac[2]
    bx, bz = b[:, 0] - bc[0], b[:, 2] - bc[2]
    theta = math.atan2(float(np.sum(ax * bz - az * bx)), float(np.sum(ax * bx + az * bz)))
    if anchor is not None:
        ac, bc = a[anchor], b[anchor]
    rb = qrot(np.broadcast_to(yaw_quat(theta), (1, 4)), bc[None])[0]
    return theta, ac - rb


# ------------------------------------------------------------------ blend-window search
def pair_costs(fa, va, ga, fb, vb, gb):
    """Matrices (len a x len b): hips-relative max joint distance (cm), velocity mismatch (cm/s), attitude (deg)."""
    pose = np.zeros((len(fa), len(fb)))
    vel = np.zeros_like(pose)
    for i in range(len(fa)):
        pose[i] = np.linalg.norm(fb - fa[i], axis=2).max(axis=1)
        vel[i] = np.linalg.norm(vb - va[i], axis=2).max(axis=1)
    att = np.degrees(np.arccos(np.clip(ga @ gb.T, -1, 1)))
    return pose, vel, att


def normalised(pose, vel, att):
    return np.maximum.reduce([pose / PLAUSIBLE_POSE_CM, vel / PLAUSIBLE_VELOCITY_CM_S, att / PLAUSIBLE_ATTITUDE_DEG])


def search_chain(lie: Motion, loop: Motion, wake: Motion, n_blend=BLEND_FRAMES, lie_frames=None, wake_frames=None):
    """Joint exhaustive search: lie frame i, loop phase p, wake frame m.

    LieDown blends lie[i..i+N] into loop[p..p+N]; the loop is re-phased to start at s=(p+N) mod L;
    GetUp blends loop[s..s+N] into wake[m..m+N]. p minimises max(cost_lie(i*,p), cost_wake(m*,s)).
    """
    L = len(loop) - 1                                             # unique frames (last == first)
    fl, fo, fw = hips_relative(lie), hips_relative(loop)[:L], hips_relative(wake)
    vl, vo, vw = velocities(fl, lie.fps), velocities(fo, loop.fps, cyclic=True), velocities(fw, wake.fps)
    gl, go, gw = gravity_in_body(lie), gravity_in_body(loop)[:L], gravity_in_body(wake)
    li = np.array(lie_frames if lie_frames is not None else range(len(lie) - n_blend))
    wi = np.array(wake_frames if wake_frames is not None else range(len(wake) - n_blend))
    if not len(li) or not len(wi):
        raise ValueError('no candidate frames for the blend search')
    pl, vel_l, al = pair_costs(fl[li], vl[li], gl[li], fo, vo, go)
    pw, vel_w, aw = pair_costs(fo, vo, go, fw[wi], vw[wi], gw[wi])     # rows: loop phase s, cols: wake frame
    cl = normalised(pl, vel_l, al)                                 # (|li|, L)
    cw = normalised(pw, vel_w, aw)                                 # (L, |wi|)
    best_i = cl.argmin(axis=0)                                     # per loop phase p
    best_m = cw.argmin(axis=1)                                     # per loop start s
    lie_cost = cl[best_i, np.arange(L)]
    wake_cost = cw[np.arange(L), best_m]
    s_of_p = (np.arange(L) + n_blend) % L
    joint = np.maximum(lie_cost, wake_cost[s_of_p])
    p = int(np.argmin(joint))
    s = int(s_of_p[p])
    i, m = int(li[best_i[p]]), int(wi[best_m[s]])

    def row(pose, vel, att, a, b):
        return {'pose_cm': round(float(pose[a, b]), 4), 'velocity_mismatch_cm_s': round(float(vel[a, b]), 4),
                'attitude_deg': round(float(att[a, b]), 4)}
    ui = np.unravel_index(np.argmin(cl), cl.shape)
    uw = np.unravel_index(np.argmin(cw), cw.shape)
    return {
        'n_blend': n_blend, 'loop_unique_frames': L,
        'chosen': {'lie_frame': i, 'loop_phase_at_lie_blend_start': p, 'loop_start_phase': s, 'wake_frame': m,
                   'lie': row(pl, vel_l, al, int(best_i[p]), p), 'wake': row(pw, vel_w, aw, s, int(best_m[s])),
                   'joint_normalised_cost': round(float(joint[p]), 4)},
        'unconstrained_best_lie': {'lie_frame': int(li[ui[0]]), 'loop_phase': int(ui[1]), **row(pl, vel_l, al, *ui)},
        'unconstrained_best_wake': {'loop_phase': int(uw[0]), 'wake_frame': int(wi[uw[1]]), **row(pw, vel_w, aw, *uw)},
        'candidates': {'lie_frames': [int(li[0]), int(li[-1])], 'wake_frames': [int(wi[0]), int(wi[-1])],
                       'loop_phases': [0, L - 1]},
        'criteria': {'pose_cm': PLAUSIBLE_POSE_CM, 'velocity_mismatch_cm_s': PLAUSIBLE_VELOCITY_CM_S,
                     'attitude_deg': PLAUSIBLE_ATTITUDE_DEG,
                     'normalised_cost': 'max(pose/10 cm, velocity/50 cm/s, attitude/30 deg); <= 1 is a plausible blend'},
    }


def blend(a: Motion, ia, b: Motion, ib, n, b_cyclic=False):
    """n+1 frames: slerp of captured local rotations a[ia+k] -> b[ib+k] (smoothstep weight), hips lerp."""
    ka = np.arange(ia, ia + n + 1)
    kb = np.arange(ib, ib + n + 1)
    if b_cyclic:
        kb = kb % (len(b) - 1)
    if ka[-1] >= len(a) or (not b_cyclic and kb[-1] >= len(b)):
        raise ValueError('blend window runs past captured frames')
    w = smoothstep(np.arange(n + 1) / n)
    q = slerp(a.q[ka], b.q[kb], w[:, None])
    t = a.t[ka] * (1 - w[:, None]) + b.t[kb] * w[:, None]
    return q, t


def cyclic_frames(loop: Motion, start, count):
    idx = (np.arange(start, start + count)) % (len(loop) - 1)
    return loop.q[idx], loop.t[idx]


def concat(sk, parts, fps, name):
    q = np.concatenate([p[0] for p in parts])
    t = np.concatenate([p[1] for p in parts])
    return Motion(sk, q, t, fps, name)


def seam_metrics(m: Motion, ranges):
    """Continuity of a composed clip: per-frame hips-relative joint step and its change, root step."""
    f = hips_relative(m)
    step = np.linalg.norm(np.diff(f, axis=0), axis=2).max(axis=1) * m.fps          # cm/s, max joint
    jerk = np.linalg.norm(np.diff(f, n=2, axis=0), axis=2).max(axis=1) * m.fps ** 2  # cm/s^2
    pos, _ = m.world()
    root = np.linalg.norm(np.diff(pos[:, m.sk.index['Hips']], axis=0), axis=1)
    out = {}
    for label, (a, b) in ranges.items():
        a2, b2 = max(a, 0), min(b, len(m) - 1)
        if b2 - a2 < 1:
            continue
        out[label] = {'frames': [a2, b2],
                      'max_joint_speed_cm_s': round(float(step[a2:b2].max()), 3),
                      'max_joint_acceleration_cm_s2': round(float(jerk[max(a2 - 1, 0):max(b2 - 1, a2)].max()) if b2 - 1 > a2 else 0.0, 3),
                      'max_root_step_cm': round(float(root[a2:b2].max()), 4)}
    out['whole_clip'] = {'max_joint_speed_cm_s': round(float(step.max()), 3),
                         'max_joint_acceleration_cm_s2': round(float(jerk.max()), 3),
                         'max_root_step_cm': round(float(root.max()), 4)}
    return out


def gap(a: Motion, ia, b: Motion, ib):
    """Gap between frame ia of a and frame ib of b (both already in the same world)."""
    fa, fb = hips_relative(a), hips_relative(b)
    va, vb = velocities(fa, a.fps), velocities(fb, b.fps)
    pa, _ = a.world()
    pb, _ = b.world()
    h = a.sk.index['Hips']
    ga, gb = gravity_in_body(a)[ia], gravity_in_body(b)[ib]
    return {'pose_cm': round(float(np.linalg.norm(fb[ib] - fa[ia], axis=1).max()), 4),
            'pose_rms_cm': round(float(np.sqrt((np.linalg.norm(fb[ib] - fa[ia], axis=1) ** 2).mean())), 4),
            'velocity_mismatch_cm_s': round(float(np.linalg.norm(vb[ib] - va[ia], axis=1).max()), 4),
            'attitude_deg': round(float(np.degrees(np.arccos(np.clip(ga @ gb, -1, 1)))), 4),
            'hips_world_offset_cm': [round(float(c), 4) for c in pb[ib, h] - pa[ia, h]],
            'hips_world_distance_cm': round(float(np.linalg.norm(pb[ib, h] - pa[ia, h])), 4),
            'world_max_joint_cm': round(float(np.linalg.norm(pb[ib] - pa[ia], axis=1).max()), 4),
            'posture': [posture(a)[ia], posture(b)[ib]]}


def verdict(g):
    flip = g['posture'][0] != g['posture'][1]
    ok = g['pose_cm'] <= PLAUSIBLE_POSE_CM and g['attitude_deg'] <= PLAUSIBLE_ATTITUDE_DEG \
        and g['velocity_mismatch_cm_s'] <= PLAUSIBLE_VELOCITY_CM_S and not flip
    reasons = []
    if g['pose_cm'] > PLAUSIBLE_POSE_CM:
        reasons.append(f"hips-relative pose gap {g['pose_cm']:.1f} cm > {PLAUSIBLE_POSE_CM} cm")
    if g['attitude_deg'] > PLAUSIBLE_ATTITUDE_DEG:
        reasons.append(f"attitude {g['attitude_deg']:.1f} deg > {PLAUSIBLE_ATTITUDE_DEG} deg")
    if g['velocity_mismatch_cm_s'] > PLAUSIBLE_VELOCITY_CM_S:
        reasons.append(f"velocity mismatch {g['velocity_mismatch_cm_s']:.1f} cm/s > {PLAUSIBLE_VELOCITY_CM_S} cm/s")
    if flip:
        reasons.append(f"posture class change {g['posture'][0]} -> {g['posture'][1]}")
    return ok, reasons


def recommend(kind, g):
    a, b = g['posture']
    if a == b:
        same = (f"same posture class ({a}) but a {g['pose_cm']:.0f} cm limb/torso configuration gap: ")
        if kind == 'lie_to_loop':
            return same + ('a captured settle on the owner skeleton from the lie-down\'s end pose into the loop\'s pose, '
                           'or a lie-down that ends in the loop\'s pose, or a sleep loop captured in the lie-down\'s end pose. '
                           'A blend cannot bridge this.')
        return same + ('a captured transition from the loop\'s pose into the get-up\'s lying start, or a get-up captured '
                       'from the loop\'s pose. A blend cannot bridge this.')
    if kind == 'lie_to_loop':
        what = f'a captured settle from the lie-down\'s end pose ({a}) into the loop\'s pose ({b})'
        if a != b:
            what += f', i.e. a {a} -> {b} roll on the mattress'
        return (what + ', on the owner skeleton, or a lie-down capture that ends in the loop\'s pose (or a sleep loop '
                'captured in the lie-down\'s end pose). A blend cannot bridge this.')
    what = f'a captured transition from the loop\'s pose ({a}) to the get-up\'s lying start ({b})'
    if a != b:
        what += f', i.e. a {a} -> {b} roll'
    return (what + ', or a get-up captured from the loop\'s pose. A blend cannot bridge this.')


# ------------------------------------------------------------------ retarget (thin wrapper)
def retarget_v5(source: Path, work: Path, owner_path: Path = OWNER, preset='v5'):
    """mapping_for/prepare_source (retarget_life_clip.py, read-only) -> retarget_first_person.mjs (unchanged)."""
    work.mkdir(parents=True, exist_ok=True)
    src_path = V.decoded(source, work)
    src = G.Gltf(src_path)
    owner = V.Owner(G.Gltf(owner_path))
    mapping = R.mapping_for(preset, src, owner)
    prepared = work / 'prepared_source.glb'
    prep = R.prepare_source(src, None, mapping, owner, prepared)
    clip_name = src.animation().name or 'clip'
    raw = work / 'retarget_first_person_output.glb'
    proc = subprocess.run(['node', str(R.MJS), str(prepared), str(owner_path), str(raw), '--clip', clip_name],
                          capture_output=True, text=True)
    if proc.returncode:
        raise RuntimeError('retarget_first_person.mjs refused: ' + (proc.stderr or proc.stdout)[-2000:])
    audit = json.loads(Path(str(raw) + '.audit.json').read_text())
    report = {
        'preset': preset, 'mapping': mapping, 'prepare': prep,
        'retarget_first_person_mjs': {k: audit.get(k) for k in ('algorithm', 'alignmentQuaternion', 'legHeightScale',
                                                                  'sourceLegHeight', 'targetLegHeight', 'checks', 'frames',
                                                                  'duration', 'proceduralMotionAdded', 'sourceSHA256',
                                                                  'targetSHA256', 'outputSHA256')},
        'rest_axis_residual_deg': {a['name']: round(a['anatomicalChildDirection']['alignedDifferenceDegrees'], 4)
                                   for a in audit.get('anatomyAxes', []) if a.get('anatomicalChildDirection')},
        'mjs_sha256': sha256(R.MJS), 'wrapper_sha256': sha256(Path(R.__file__)),
    }
    return raw, clip_name, report


def owner_offsets_residual(m: Motion):
    """Retarget residuals against the owner: bone lengths every frame vs owner rest, and the local offsets."""
    pos, _ = m.world()
    L = m.sk.bone_lengths(pos)
    L0 = m.sk.bone_lengths(m.sk.rest_pos[None])[0]
    return {'max_bone_length_deviation_cm': round(float(np.abs(L - L0).max()), 6),
            'local_translation_policy': 'owner rest offsets for every non-hips joint (no translation track is written)'}


# ------------------------------------------------------------------ GLB writer
def write_motion(m: Motion, template: Path, out: Path, name: str, generator: str):
    """Rotation tracks for all 65 joints and the hips translation, LINEAR, uniform keys; nodes from template."""
    g = G.Gltf(template)
    node = {V.canonical(n.get('name', '')): i for i, n in enumerate(g.nodes) if V.PREFIX.match(n.get('name', ''))}
    bw = G.BinWriter()
    times = [k / m.fps for k in range(len(m))]
    ti = bw.add(times, 'SCALAR', minmax=True)
    anim = {'name': name, 'samplers': [], 'channels': []}
    q = m.q.copy()
    for f in range(1, len(q)):                                        # hemisphere continuity
        flip = np.sum(q[f] * q[f - 1], axis=1) < 0
        q[f, flip] *= -1
    for k, n in enumerate(m.sk.names):
        vi = bw.add([tuple(map(float, v)) for v in q[:, k]], 'VEC4')
        anim['samplers'].append({'input': ti, 'output': vi, 'interpolation': 'LINEAR'})
        anim['channels'].append({'sampler': len(anim['samplers']) - 1, 'target': {'node': node[n], 'path': 'rotation'}})
        if n == 'Hips':
            vt = bw.add([tuple(map(float, v)) for v in m.t], 'VEC3')
            anim['samplers'].append({'input': ti, 'output': vt, 'interpolation': 'LINEAR'})
            anim['channels'].append({'sampler': len(anim['samplers']) - 1, 'target': {'node': node[n], 'path': 'translation'}})
    doc = {'asset': {'version': '2.0', 'generator': generator}, 'scene': 0, 'scenes': g.doc['scenes'],
           'nodes': g.doc['nodes'], 'animations': [anim], 'accessors': bw.accessors, 'bufferViews': bw.views,
           'buffers': [{'byteLength': len(bw.data) + (-len(bw.data)) % 4}]}
    return G.write_glb(out, doc, bytes(bw.data))


def in_place(m: Motion):
    """The hips' horizontal path removed (vertical kept); the path itself goes to CharacterMovement."""
    t = m.t.copy()
    t[:, 0] = t[0, 0]
    t[:, 2] = t[0, 2]
    return Motion(m.sk, m.q, t, m.fps, m.name)


# ------------------------------------------------------------------ standing / plantar checks
def plantar_contact(soles_report):
    """The seat-contact rule for soles (validate_unreal_seat_contact.SOLE_BAND_CM): each sole's lowest plantar
    vertex must stay within the band over the floor (y = 0) on every frame, and the constant vertical shift
    that would satisfy both soles is reported (an empty interval means the legs, not a translation, must change)."""
    low, high = C.SOLE_BAND_CM
    feet = soles_report.get('feet', {})
    out, lo, hi = {}, -math.inf, math.inf
    for side in ('left', 'right'):
        f = feet.get(side)
        if not f:
            return {'pass': False, 'reason': f'no {side} sole measurement'}
        mn, mx = f['lowest_vertex_min_cm'], f['lowest_vertex_max_cm']
        ok = mn >= low - 1e-9 and mx <= high + 1e-9
        out[side] = {'lowest_vertex_cm': [mn, mx], 'pass': ok}
        lo, hi = max(lo, low - mn), min(hi, high - mx)
    ok = all(v['pass'] for v in out.values())
    shift = None if lo > hi else (0.0 if lo <= 0 <= hi else (lo if lo > 0 else hi))
    return {'pass': ok, 'band_cm': [low, high], 'source': 'tools/validate_unreal_seat_contact.py SOLE_BAND_CM',
            'feet': out, 'common_vertical_shift_interval_cm': [round(lo, 4), round(hi, 4)],
            'vertical_shift_cm_that_would_satisfy_both': None if shift is None else round(shift, 4),
            'diagnosis': ('within the band' if ok else 'no single vertical shift puts both soles in the band: the legs '
                          '(captured pose) disagree; not fixed here (no IK)' if shift is None else
                          f'a constant vertical shift of {shift:+.2f} cm would put both soles in the band '
                          '(reported only; nothing is shifted)')}


def standing_end_checks(glb: Path, owner_path: Path, last_s=0.2, soles=True, work=None):
    """The verifier's own standing, feet-joint and plantar-sole checks on the last last_s of a clip."""
    owner = V.Owner(G.Gltf(owner_path))
    g = G.Gltf(glb)
    cand = V.Candidate(g, owner)
    times = cand.times()
    keep = [t for t in times if t >= times[-1] - last_s - 1e-9]
    frames = [(t, G.world_pose(g, cand.clip, t)) for t in keep]
    out = {'window_s': [round(keep[0], 5), round(keep[-1], 5)], 'frames': len(keep),
           'standing': V.check_standing(frames, cand, owner), 'feet_joints': V.check_feet_joints(frames, cand, owner)}
    if soles:
        work = Path(work or glb.parent)
        out['soles'] = V.check_soles(frames, cand, V.sole_selection(G.Gltf(V.decoded(owner_path, work))))
        out['plantar_contact'] = plantar_contact(out['soles'])
    return out


# ------------------------------------------------------------------ the pipeline
def chain_rank(c):
    """Prefer chains without a posture-class flip, then the lower joint normalised cost."""
    flips = sum(bool(any('posture class change' in r for r in c[k]['refusal_reasons'])) for k in ('lie_to_loop', 'loop_to_wake'))
    return (flips, c['search']['chosen']['joint_normalised_cost'])


def build_chain(sk, lie: Motion, loop: Motion, wake: Motion, n_blend, lie_frames, wake_frames):
    L = len(loop) - 1
    seam = gap(loop, len(loop) - 1, loop, 0)
    res = search_chain(lie, loop, wake, n_blend, lie_frames, wake_frames)
    c = res['chosen']
    i, p, s, mw = c['lie_frame'], c['loop_phase_at_lie_blend_start'], c['loop_start_phase'], c['wake_frame']
    hip = sk.index['Hips']
    # rigid placement: yaw by 2D Kabsch on all joints, translation so the hips coincide at the blend start
    th1, off1 = fit_yaw_translation(lie.world()[0][i], loop.world()[0][p], anchor=hip)
    loop_p = loop.placed(th1, off1)
    th2, off2 = fit_yaw_translation(loop_p.world()[0][s], wake.world()[0][mw], anchor=hip)
    wake_p = wake.placed(th2, off2)
    before = {'direct_cut_lie_end_to_loop_start_unplaced': gap(lie, len(lie) - 1, loop, 0),
              'direct_cut_loop_end_to_wake_start_unplaced': gap(loop, L, wake, 0),
              'best_match_lie_to_loop_placed': gap(lie, i, loop_p, p),
              'best_match_loop_to_wake_placed': gap(loop_p, s, wake_p, mw)}
    placement = {
        'loop_onto_lie': {'yaw_deg': round(math.degrees(th1), 4), 'offset_cm': [round(float(v), 3) for v in off1],
                          'vertical_shift_cm': round(float(off1[1]), 3)},
        'wake_onto_loop': {'yaw_deg': round(math.degrees(th2), 4), 'offset_cm': [round(float(v), 3) for v in off2],
                           'vertical_shift_cm': round(float(off2[1]), 3)},
        'rule': 'one constant rigid placement per clip: yaw about vertical fitted by 2D Kabsch on all 65 joints, then the '
                'translation that puts the hips on the previous clip\'s hips at the blend start; never per frame. The '
                'vertical shift moves the loop to the lie-down\'s bed height, which is NOT the native mattress: the bed '
                'fit (tools/fit_bed_placement.py) decides the final height.'}
    bq, bt = blend(lie, i, loop_p, p, n_blend, b_cyclic=True)
    lie_down = concat(sk, [(lie.q[:i], lie.t[:i]), (bq, bt)], lie.fps, 'LieDown')
    lq, lt = cyclic_frames(loop_p, s, L + 1)
    sleep_loop = Motion(sk, lq, lt, loop.fps, 'SleepLoop')
    gq, gt = blend_from_loop(loop_p, s, wake_p, mw, n_blend)
    get_up = concat(sk, [(gq, gt), (wake_p.q[mw + n_blend + 1:], wake_p.t[mw + n_blend + 1:])], wake.fps, 'GetUp')
    whole = concat(sk, [(lie_down.q, lie_down.t), (sleep_loop.q[1:], sleep_loop.t[1:]), (get_up.q[1:], get_up.t[1:])],
                   lie.fps, 'chain')
    a1 = i + n_blend
    b0 = len(lie_down) - 1 + L
    after = {'seams': seam_metrics(whole, {'lie_blend': (i - 3, a1 + 3), 'lie_down_into_loop': (a1 - 2, a1 + 3),
                                           'loop_into_get_up': (b0 - 2, b0 + 3), 'wake_blend': (b0 - 3, b0 + n_blend + 3)}),
             'lie_down_end_vs_loop_start': gap(lie_down, len(lie_down) - 1, sleep_loop, 0),
             'loop_end_vs_get_up_start': gap(sleep_loop, len(sleep_loop) - 1, get_up, 0),
             'captured_reference_whole_clip': {'lie_down_source': seam_metrics(lie, {})['whole_clip'],
                                               'loop_source': seam_metrics(loop, {})['whole_clip'],
                                               'get_up_source': seam_metrics(wake, {})['whole_clip']},
             'note': 'after the blend the seams are exact by construction (pose 0); what remains is the blend itself: '
                     'the pose gap is crossed in n_blend frames, so the joint speeds inside the blend window are the cost'}
    ok_l, why_l = verdict(before['best_match_lie_to_loop_placed'])
    ok_w, why_w = verdict(before['best_match_loop_to_wake_placed'])
    return {
        'loop': rel(loop.source) if loop.source else None, 'loop_sha256': sha256(loop.source) if loop.source else None,
        'loop_frames': len(loop),
        'loop_seam_own': {k: seam[k] for k in ('pose_cm', 'velocity_mismatch_cm_s')},
        'loop_posture': max(set(posture(loop)), key=posture(loop).count),
        'search': res, 'placement': placement, 'before_blend': before, 'after_blend': after,
        'discarded_captured_frames': {
            'lie_down_tail_after_blend_s': round((len(lie) - 1 - (i + n_blend)) / lie.fps, 4),
            'get_up_head_before_blend_s': round(mw / wake.fps, 4)},
        'lie_to_loop': {'plausible_blend': ok_l, 'refusal_reasons': why_l,
                        'needed': None if ok_l else recommend('lie_to_loop', before['best_match_lie_to_loop_placed'])},
        'loop_to_wake': {'plausible_blend': ok_w, 'refusal_reasons': why_w,
                         'needed': None if ok_w else recommend('loop_to_wake', before['best_match_loop_to_wake_placed'])},
        'accepted_within_blend_criteria': bool(ok_l and ok_w),
        '_motions': (lie_down, sleep_loop, get_up, whole),
    }


def strip(d):
    return {k: v for k, v in d.items() if not k.startswith('_')}


def dump(obj, work: Path, **kw):
    """JSON text with the scratch work directory written as <work> (reports are committed; scratch is not)."""
    text = json.dumps(obj, sort_keys=True, **kw) + '\n'
    for w in {str(Path(work)), str(Path(work).resolve())}:
        text = text.replace(w, '<work>')
    return text


def run(out_dir: Path, work: Path, owner_path: Path = OWNER, n_blend=BLEND_FRAMES, loops=None, write_glb=False,
        soles=True):
    out_dir.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    sk = Skeleton(owner_path)
    quotes = check_documented()
    files = [owner_path, *SOURCES.values(), *CARRIED_COPIES.values(), *SLEEP_LOOPS.values(), R.MJS, Path(R.__file__),
             Path(V.__file__), Path(G.__file__), ROOT / 'tools/native_life_skeleton_parity.py', Path(__file__),
             ROOT / 'room_build/kimodo/mh_retarget.mjs', ROOT / 'room_build/kimodo/mx_convert.mjs']
    hashes = {rel(p): sha256(p) for p in files}
    for f, _ in DOCUMENTED:
        hashes[f] = sha256(ROOT / f)

    # 2. retarget the v5 originals onto the owner's exact offsets
    motions, rt, templates = {}, {}, {}
    for role, src in SOURCES.items():
        raw, _, rep = retarget_v5(src, work / role, owner_path)
        mine = Motion.from_glb(sk, raw, name=role)
        motions[role], templates[role] = mine, raw
        rep['source'] = rel(src)
        rep['source_sha256'] = sha256(src)
        rep['raw_output_sha256'] = sha256(raw)
        rep['owner_residuals'] = owner_offsets_residual(mine)
        rep['this_retarget_non_hips_translation_tracks'] = mine.translation_drift_cm
        copy = Motion.from_glb(sk, CARRIED_COPIES[role], keep_bone_translations=True)
        n = min(len(copy), len(mine))
        dp = np.linalg.norm(copy.world()[0][:n] - mine.world()[0][:n], axis=2)
        rep['vs_drifted_mh_mx_copy'] = {
            'file': rel(CARRIED_COPIES[role]), 'sha256': sha256(CARRIED_COPIES[role]),
            'copy_non_hips_translation_drift': copy.translation_drift_cm,
            'copy_max_bone_length_deviation_cm': owner_offsets_residual(copy)['max_bone_length_deviation_cm'],
            'world_joint_difference_cm': {'max': round(float(dp.max()), 3), 'median': round(float(np.median(dp)), 3),
                                          'note': 'frame by frame, each in its own clip frame'}}
        rt[role] = rep
    lie, wake_full = motions['LieDown'], motions['GetUp']

    # 3. the get-up cropped where the measured standing capture begins
    crop = detect_standing_crop(standing_mask(wake_full), hips_speed(wake_full), wake_full.fps)
    if crop is None:
        raise RuntimeError('the get-up never reaches a held standing pose')
    wake = wake_full.slice(0, crop['crop_frame'] + 1)
    after_crop = root_path(wake_full.slice(crop['crop_frame'], len(wake_full)))
    crop_report = {**crop, 'crop_s': round(crop['crop_frame'] / wake_full.fps, 4),
                   'onset_s': round(crop['onset_frame'] / wake_full.fps, 4),
                   'walk_onset_s': None if crop['walk_onset_frame'] is None else round(crop['walk_onset_frame'] / wake_full.fps, 4),
                   'full_duration_s': round(wake_full.duration, 4), 'cropped_duration_s': round(wake.duration, 4),
                   'speed_at_crop_cm_s': round(float(hips_speed(wake_full)[crop['crop_frame']]), 3),
                   'discarded_tail': {k: after_crop[k] for k in ('path_length_cm', 'net_distance_cm', 'max_speed_cm_s')},
                   'full_clip_root': {k: root_path(wake_full)[k] for k in ('path_length_cm', 'net_distance_cm', 'max_speed_cm_s')}}

    corrected = {'LieDown': lie, 'GetUp': wake}
    paths = {role: root_path(m, support_class(m)) for role, m in corrected.items()}
    paths['GetUp_uncropped'] = root_path(wake_full, support_class(wake_full))
    outputs = {}
    glb_dir = out_dir if write_glb else work
    for role, m in corrected.items():
        outputs[role] = {}
        for var, mm in (('travel_in_hips', m), ('in_place', in_place(m))):
            glb = glb_dir / f'SUB01_{role}.{var}.glb'
            sha = write_motion(mm, templates['LieDown'], glb, role, f'SUB01 bed_transition_pipeline {role} ({var}); '
                               'retarget_first_person.mjs rest-delta from the mh_v5 original; PRIVATE')
            outputs[role][var] = {'path': rel(glb), 'sha256': sha, 'bytes': glb.stat().st_size,
                                  'frames': len(mm), 'duration_s': round(mm.duration, 4)}
    end_checks = standing_end_checks(glb_dir / 'SUB01_GetUp.travel_in_hips.glb', owner_path, soles=soles, work=work)
    start_checks = standing_end_checks_first(glb_dir / 'SUB01_LieDown.travel_in_hips.glb', owner_path, soles, work)

    # 4. the Sova sleep loops: search, blend, measure
    loops = loops or list(SLEEP_LOOPS)
    sleep = {k: Motion.from_glb(sk, SLEEP_LOOPS[k], name=k) for k in loops}
    lie_tilt, wake_tilt = torso_tilt_deg(lie), torso_tilt_deg(wake)
    lie_frames = [i for i in range(len(lie) - n_blend) if lie_tilt[i] > LYING_MIN_TILT_DEG]
    wake_frames = [i for i in range(len(wake) - n_blend) if wake_tilt[i] > LYING_MIN_TILT_DEG]
    chains = {k: build_chain(sk, lie, loop, wake, n_blend, lie_frames, wake_frames) for k, loop in sleep.items()}
    best = min(chains, key=lambda k: chain_rank(chains[k]))
    within = chains[best]['accepted_within_blend_criteria']
    lie_down_c, sleep_loop_c, get_up_c, whole_c = chains[best]['_motions']
    composed = {}
    composed_dir = out_dir if (write_glb and within) else work
    for role, m in (('LieDown', lie_down_c), ('SleepLoop', sleep_loop_c), ('GetUp', get_up_c)):
        glb = composed_dir / f'SUB01_{role}.chain_{best}.glb'
        composed[role] = {'path': rel(glb), 'sha256': write_motion(m, templates['LieDown'], glb, role,
                                                                     f'SUB01 bed chain {role} via {best}; PRIVATE'),
                          'frames': len(m), 'duration_s': round(m.duration, 4),
                          'committed': bool(write_glb and within)}
    chain_paths = {'chain_' + k: strip(root_path(m, support_class(m))) for k, m in
                   (('LieDown', lie_down_c), ('SleepLoop', sleep_loop_c), ('GetUp', get_up_c), ('whole', whole_c))}

    def prov(role, src):
        p = dict(PROVENANCE[role])
        p['source_sha256'] = {rel(src): sha256(src)}
        p['quotes'] = quotes
        validate_provenance(p)
        return p

    blend_view = {'blend_frames': n_blend, 'blend_rule': BLEND_RULE.format(n=n_blend, s=n_blend / FPS),
                  'chosen_sleep_loop': best, 'within_blend_criteria': within, 'chains': {k: strip(v) for k, v in chains.items()},
                  'composed_outputs': composed, 'composed_root_paths': chain_paths}
    verdict_text = ('REFUSED for binding: provenance unverified (mh_v5 placeholder origin), and the sleep-loop blends exceed a '
                    'plausible blend (blend.chains.*.lie_to_loop / loop_to_wake). The bed is unmeasured.') if not within else \
        ('Blend gaps within the stated criteria; still NOT accepted: provenance unverified, bed unmeasured, no server '
         'import or native capture.')
    reports = {}
    for role in ('LieDown', 'SleepLoop', 'GetUp'):
        if role == 'SleepLoop':
            src = SLEEP_LOOPS[best]
            rep = {'schema': SCHEMA_CLIP, 'role': role, 'private': True, 'provenance': prov(role, src),
                   'retarget': {'note': 'already on the owner skeleton (exact rest, non-hips translation tracks: '
                                        f"{sleep[best].translation_drift_cm['non_hips_translation_tracks']}); sampled, not retargeted",
                                'owner_residuals': owner_offsets_residual(sleep[best])},
                   'loops_evaluated': {k: {'loop_posture': v['loop_posture'], 'loop_seam_own': v['loop_seam_own'],
                                           'sha256': v['loop_sha256']} for k, v in chains.items()}}
        else:
            rep = {'schema': SCHEMA_CLIP, 'role': role, 'private': True, 'provenance': prov(role, SOURCES[role]),
                   'retarget': rt[role], 'outputs': outputs[role],
                   'root_path': strip(paths[role]),
                   'root_motion_export': ROOT_EXPORT_NOTE}
        if role == 'GetUp':
            rep['crop'] = crop_report
            rep['root_path_uncropped_source'] = strip(paths['GetUp_uncropped'])
            rep['standing_end_checks'] = end_checks
        if role == 'LieDown':
            rep['standing_start_checks'] = start_checks
        rep['blend'] = {'chosen_sleep_loop': best, 'blend_frames': n_blend,
                        'lie_to_loop': chains[best]['lie_to_loop'], 'loop_to_wake': chains[best]['loop_to_wake'],
                        'search_chosen': chains[best]['search']['chosen'], 'before_blend': chains[best]['before_blend'],
                        'after_blend_seams': chains[best]['after_blend']['seams'], 'placement': chains[best]['placement'],
                        'composed_output': composed[role]}
        rep['accepted_for_binding'] = False
        rep['verdict'] = verdict_text
        rep['licence_note'] = LICENCE_NOTE
        reports[role] = rep
        (out_dir / f'SUB01_{role}.report.json').write_text(dump(rep, work, indent=1))
        if role in paths:
            (out_dir / f'SUB01_{role}.root_path.json').write_text(dump(
                {'schema': 'sub01.bed-transition-root-path.v1', 'role': role, 'source_clip': outputs[role]['travel_in_hips'],
                 **paths[role]}, work))
    pipe = {'schema': SCHEMA_PIPELINE, 'owner': rel(owner_path), 'owner_sha256': sk.sha256, 'hashes': hashes,
            'provenance': PROVENANCE, 'documented_quotes': quotes, 'retarget': {k: {kk: vv for kk, vv in v.items() if kk != 'mapping'}
                                                                                for k, v in rt.items()},
            'crop': crop_report, 'root_paths': {k: strip(v) for k, v in paths.items()}, 'corrected_outputs': outputs,
            'get_up_end_checks': end_checks, 'lie_down_start_checks': start_checks, 'blend': blend_view,
            'accepted': False, 'verdict': verdict_text, 'licence_note': LICENCE_NOTE,
            'never': 'no IK, no keyed or invented poses, no finger poses, no foot locking; only captured rotations, the '
                     'captured hips path, one rigid placement per clip and a standard slerp blend'}
    (out_dir / 'bed-transition-pipeline.report.json').write_text(dump(pipe, work, indent=1))
    return pipe


BLEND_RULE = ('slerp of captured local rotations (shortest arc) and lerp of the hips translation over {n} frames '
              '({s:.2f} s, the bed layer\'s existing 0.8 s crossfade), smoothstep weight; captured frames continue on '
              'both sides of the window')
LICENCE_NOTE = ('PRIVATE. SleepLoop frames are Sova (author permission for the preview, confirmed by the owner '
                '2026-10-08; licence pending, never public, never main). LieDown/GetUp derive from mh_v5 clips '
                '("as their sources"; origin before preview/mh-motion undocumented). Never deploy.')
ROOT_EXPORT_NOTE = ('Two variants. travel_in_hips: the captured horizontal hips path stays in the hips track (what the '
                    '67af5f8 adapter would play with movement disabled; the body ends offset from the capsule). '
                    'in_place: the horizontal hips path is removed (vertical kept) and SUB01_<role>.root_path.json gives '
                    'it per frame (forward/right cm, component frame) for the native side to drive as smooth movement; '
                    'never a teleport. The owner skeleton has no animated root bone (structural root constant), so UE '
                    'root motion from a root bone is not available without changing the skeleton.')


def blend_from_loop(loop: Motion, s, wake: Motion, mw, n):
    """GetUp head: the loop from phase s (cyclic) slerped into the wake from frame mw over n frames."""
    lq, lt = cyclic_frames(loop, s, n + 1)
    kw = np.arange(mw, mw + n + 1)
    if kw[-1] >= len(wake):
        raise ValueError('get-up blend runs past captured frames')
    w = smoothstep(np.arange(n + 1) / n)
    return slerp(lq, wake.q[kw], w[:, None]), lt * (1 - w[:, None]) + wake.t[kw] * w[:, None]


def standing_end_checks_first(glb: Path, owner_path: Path, soles=True, work=None, first_s=0.2):
    owner = V.Owner(G.Gltf(owner_path))
    g = G.Gltf(glb)
    cand = V.Candidate(g, owner)
    times = cand.times()
    keep = [t for t in times if t <= times[0] + first_s + 1e-9]
    frames = [(t, G.world_pose(g, cand.clip, t)) for t in keep]
    out = {'window_s': [round(keep[0], 5), round(keep[-1], 5)], 'frames': len(keep),
           'standing': V.check_standing(frames, cand, owner), 'feet_joints': V.check_feet_joints(frames, cand, owner)}
    if soles:
        out['soles'] = V.check_soles(frames, cand, V.sole_selection(G.Gltf(V.decoded(owner_path, Path(work or glb.parent)))))
        out['plantar_contact'] = plantar_contact(out['soles'])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('out_dir', type=Path)
    ap.add_argument('--work', type=Path)
    ap.add_argument('--owner', type=Path, default=OWNER)
    ap.add_argument('--blend-frames', type=int, default=BLEND_FRAMES)
    ap.add_argument('--sleep', default=','.join(SLEEP_LOOPS))
    ap.add_argument('--write-glb', action='store_true', help='write the GLBs into OUT_DIR (otherwise into --work)')
    ap.add_argument('--no-soles', action='store_true')
    args = ap.parse_args(argv)
    work = args.work or args.out_dir / 'work'
    pipe = run(args.out_dir, work, args.owner, args.blend_frames, args.sleep.split(','), args.write_glb, not args.no_soles)
    b = pipe['blend']
    best = b['chains'][b['chosen_sleep_loop']]
    print(json.dumps({'chosen_sleep_loop': b['chosen_sleep_loop'], 'within_blend_criteria': b['within_blend_criteria'],
                      'lie_to_loop': best['lie_to_loop'], 'loop_to_wake': best['loop_to_wake'],
                      'crop_s': pipe['crop']['crop_s'], 'accepted': pipe['accepted']}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
