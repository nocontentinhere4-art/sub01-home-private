"""Compact ACTUAL seated-typing source for the seat pose fit: fixed vertex sets + per-frame joints.

Reads the owner skin (web/room/char_mixamo.glb, meshopt: decoded once by the existing
tools/uncompress_unreal_glb.mjs with the vendored MeshoptDecoder) and the DeskTyping capture
(web/room/mh_mx/room_mx_typing.glb, the SourceAssets/room_mx_typing.glb that UE imported as
SUB01_DeskTyping). Instead of 301 frames of posed vertices it stores only:

* fixed vertex index sets, chosen ONCE in bind space by the renderer's own rules:
  - buttocks / left / right posterior thigh: AnalyzeCapturedSeatSkin's region rule (Hips /
    LeftUpLeg / RightUpLeg weight >= 0.30 of the vertex and the largest of the five regions);
  - left / right plantar soles: root's fixed rest-mesh rule (material "feet", rest Y <= 0.004 m,
    bind normal Y < -0.7), split by dominant joint side; never a per-pose minimum;
  - left / right distal finger skin: AnalyzeCapturedFingerSkin's rule (Index/Middle/Ring/Pinky/
    Thumb "3" joints >= 0.30 of the vertex weight, left first);
* bind positions, bind normals and 4 skin influences for only those vertices;
* inverse bind matrices and the captured joint WORLD matrices for the 301 audit frames
  (t = 3 + i/60 s, glTF LINEAR sampling, the clip's own node reference pose);

and skins on demand with numpy. Coordinates: glTF world metres, Y up. The UE mesh component
space is 100 * (x, z, y) cm (the same contract as tools/extract_keyboard_keycaps.py), placed by
the audited body transform [203.9, -232.3, -0.6] cm, yaw 180 (tools/unreal_audit_seat_contact.py).

    python tools/export_seat_fit_source.py --out private-audit/seat-fit-source.npz

Proof of parity with root's UE measurements is in `parity()` (left/right sole at 3 s).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import life_gltf as G  # noqa: E402

OWNER = ROOT / 'web/room/char_mixamo.glb'
CLIP = ROOT / 'web/room/mh_mx/room_mx_typing.glb'
SCHEMA = 'sub01.seat-fit-source.v1'
BODY_CM = (203.9, -232.3, -.6)          # unreal_audit_seat_contact.py BODY_CM, yaw 180, scale 1
BODY_YAW = 180
TIMES = tuple(3 + i / 60 for i in range(301))
PATCHES = ('buttocks', 'left_posterior_thigh', 'right_posterior_thigh', 'left_sole', 'right_sole',
           'left_fingers', 'right_fingers')
SOLE_MATERIAL, SOLE_MAX_REST_Y_M, SOLE_MAX_NORMAL_Y = 'feet', .004, -.7     # root's plantar rule
REGION_MIN_SHARE = .30                                                      # native region rule
# Root's UE measurements at 3 s (lowest / median / highest plantar gap to z = 0, cm).
ROOT_SOLES_3S = {'left': (-.161045, 10.39739, 24.26818), 'right': (-.360148, 7.52677, 14.81967)}


# ---------------------------------------------------------------- glTF reading
def decoded(path: Path, cache: Path) -> Path:
    """The GLB itself, or its meshopt-decoded copy made by tools/uncompress_unreal_glb.mjs (cached)."""
    path = Path(path)
    if not G.is_compressed(path):
        return path
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    out = Path(cache) / f'{path.stem}.{digest}.decoded.glb'
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['node', str(ROOT / 'tools/uncompress_unreal_glb.mjs'), str(path), str(out)], check=True,
                       stdout=subprocess.DEVNULL)
    return out


def accessor(gltf: G.Gltf, index: int) -> np.ndarray:
    a = gltf.doc['accessors'][index]
    if 'sparse' in a:
        raise ValueError('sparse accessor unsupported')
    dt = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5122: np.int16, 5121: np.uint8, 5120: np.int8}[a['componentType']]
    width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[a['type']]
    view = gltf.doc['bufferViews'][a['bufferView']]
    item = np.dtype(dt).itemsize
    raw = gltf.view_bytes(a['bufferView'])
    arr = np.ndarray((a['count'], width), dtype=dt, buffer=raw, offset=a.get('byteOffset', 0),
                     strides=(view.get('byteStride', width * item), item)).astype(np.float64)
    if a.get('normalized'):
        arr = np.maximum(arr / {np.uint8: 255, np.uint16: 65535, np.int16: 32767, np.int8: 127}[dt], -1.)
    return arr


def trs(t, q, s):
    x, y, z, w = q
    m = np.eye(4)
    m[:3, :3] = s * np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                              [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                              [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    m[:3, 3] = t
    return m


def short(name):
    return name.split(':')[-1]


# ---------------------------------------------------------------- selection (bind space, once)
def select(owner: G.Gltf):
    doc = owner.doc
    skin = doc['skins'][0]
    names = [short(doc['nodes'][j]['name']) for j in skin['joints']]
    mats = [m.get('name') for m in doc.get('materials', [])]
    region_of = {}
    for k, n in enumerate(names):
        region_of[k] = {'Hips': 0, 'LeftUpLeg': 1, 'RightUpLeg': 2, 'LeftFoot': 3, 'LeftToeBase': 3,
                        'RightFoot': 4, 'RightToeBase': 4}.get(n, -1)
    def distal_side(n):
        if not n.endswith('3') or not any(f in n for f in ('Index', 'Middle', 'Ring', 'Pinky', 'Thumb')):
            return 2
        return 0 if n.startswith('LeftHand') else 1 if n.startswith('RightHand') else 2
    distal = np.array([distal_side(n) for n in names])
    region_lut = np.array([region_of[k] for k in range(len(names))])
    out = {p: {'prim': [], 'vertex': [], 'pos': [], 'nrm': [], 'joints': [], 'weights': []} for p in PATCHES}
    seen = set()
    prim_id = 0
    for node in doc['nodes']:
        if 'mesh' not in node or node.get('skin') != 0 or node['mesh'] in seen:
            continue
        seen.add(node['mesh'])
        for prim in doc['meshes'][node['mesh']]['primitives']:
            a = prim['attributes']
            pos, nrm = accessor(owner, a['POSITION']), accessor(owner, a['NORMAL'])
            jts, wts = accessor(owner, a['JOINTS_0']).astype(int), accessor(owner, a['WEIGHTS_0'])
            total = wts.sum(axis=1)
            # Seat regions: share per region, argmax among those >= 0.30 (ties to the later region, as native).
            share = np.zeros((len(pos), 5))
            for k in range(4):
                r = region_lut[jts[:, k]]
                for reg in range(5):
                    share[:, reg] += np.where(r == reg, wts[:, k], 0.)
            ok = share >= REGION_MIN_SHARE * total[:, None]
            masked = np.where(ok, share, -1.)
            best = 4 - np.argmax(masked[:, ::-1], axis=1)
            which = np.where(ok.any(axis=1), best, -1)
            groups = {'buttocks': which == 0, 'left_posterior_thigh': which == 1, 'right_posterior_thigh': which == 2}
            # Plantar soles: root's fixed rest-mesh rule on the "feet" material.
            if prim.get('material') is not None and mats[prim['material']] == SOLE_MATERIAL:
                plantar = (pos[:, 1] <= SOLE_MAX_REST_Y_M) & (nrm[:, 1] < SOLE_MAX_NORMAL_Y)
                dominant = jts[np.arange(len(jts)), np.argmax(wts, axis=1)]
                is_left = np.array([names[j].startswith('Left') for j in dominant])
                groups['left_sole'], groups['right_sole'] = plantar & is_left, plantar & ~is_left
            # Distal finger skin: native AnalyzeCapturedFingerSkin side rule (left checked first).
            dshare = np.zeros((len(pos), 3))
            for k in range(4):
                for side in range(3):
                    dshare[:, side] += np.where(distal[jts[:, k]] == side, wts[:, k], 0.)
            left = dshare[:, 0] >= REGION_MIN_SHARE * total
            right = ~left & (dshare[:, 1] >= REGION_MIN_SHARE * total)
            groups['left_fingers'], groups['right_fingers'] = left, right
            for name, mask in groups.items():
                idx = np.nonzero(mask & (total > 0))[0]
                o = out[name]
                o['prim'].append(np.full(len(idx), prim_id))
                o['vertex'].append(idx)
                o['pos'].append(pos[idx])
                o['nrm'].append(nrm[idx])
                o['joints'].append(jts[idx])
                o['weights'].append(wts[idx] / total[idx, None])
            prim_id += 1
    return names, {p: {k: np.concatenate(v) for k, v in d.items()} for p, d in out.items()}


# ---------------------------------------------------------------- per-frame joints
def joint_worlds(clip: G.Gltf, names, times=TIMES):
    """(F, 65, 4, 4) captured joint world matrices (glTF metres) at the audit times, plus parents."""
    animation = clip.animation()
    index = {short(n.get('name', '')): i for i, n in enumerate(clip.nodes) if n.get('name', '').startswith('mixamorig')}
    missing = [n for n in names if n not in index]
    if missing:
        raise ValueError(f'capture lacks skin joints {missing}')
    nodes = [index[n] for n in names]
    out = np.zeros((len(times), len(names), 4, 4))
    for f, t in enumerate(times):
        world = G.world_pose(clip, animation, t)
        for k, i in enumerate(nodes):
            out[f, k] = trs(*world[i])
    by_node = {i: k for k, i in enumerate(nodes)}
    parents = np.array([by_node.get(clip.parent.get(i), -1) for i in nodes])
    return out, parents


def build(owner=OWNER, clip=CLIP, cache=None):
    cache = Path(cache or ROOT / 'out/seat-fit-cache')
    owner_g = G.Gltf(decoded(owner, cache))
    clip_g = G.Gltf(clip)
    names, patches = select(owner_g)
    skin = owner_g.doc['skins'][0]
    ibm = accessor(owner_g, skin['inverseBindMatrices']).reshape(-1, 4, 4).transpose(0, 2, 1)
    worlds, parents = joint_worlds(clip_g, names)
    meta = {'schema': SCHEMA, 'owner': str(Path(owner).relative_to(ROOT)) if Path(owner).is_relative_to(ROOT) else str(owner),
            'owner_sha256': hashlib.sha256(Path(owner).read_bytes()).hexdigest(),
            'clip': str(Path(clip).relative_to(ROOT)) if Path(clip).is_relative_to(ROOT) else str(clip),
            'clip_sha256': hashlib.sha256(Path(clip).read_bytes()).hexdigest(),
            'times': {'start_s': 3, 'end_s': 8, 'rate_hz': 60, 'count': len(TIMES)}, 'body_cm': list(BODY_CM), 'body_yaw': BODY_YAW,
            'ue_component_from_gltf': 'UE cm = 100 * (x, z, y); world = BodyWorld(yaw 180) * component',
            'rules': {'seat_regions': 'AnalyzeCapturedSeatSkin: region weight >= 0.30 and largest of 5',
                      'soles': 'material "feet", rest Y <= 0.004 m, bind normal Y < -0.7 (fixed set)',
                      'fingers': 'AnalyzeCapturedFingerSkin: distal "3" joint weight >= 0.30, left first'},
            'counts': {p: int(len(patches[p]['vertex'])) for p in PATCHES}}
    data = {'meta': np.array(json.dumps(meta)), 'names': np.array(names), 'parents': parents,
            'ibm': ibm, 'joint_world': worlds, 'times': np.array(TIMES)}
    for p, d in patches.items():
        data[f'{p}.prim'] = d['prim'].astype(np.int16)
        data[f'{p}.vertex'] = d['vertex'].astype(np.int32)
        data[f'{p}.pos'] = d['pos'].astype(np.float32)
        data[f'{p}.nrm'] = d['nrm'].astype(np.float32)
        data[f'{p}.joints'] = d['joints'].astype(np.int16)
        data[f'{p}.weights'] = d['weights'].astype(np.float32)
    return data


def save(data, out):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, **data)
    return out


class Source:
    """Loaded compact source with on-demand skinning (glTF metres) and UE world conversion (cm)."""

    def __init__(self, data):
        self.d = dict(data)
        self.meta = json.loads(str(self.d['meta']))
        self.names = [str(n) for n in self.d['names']]
        self.parents = np.asarray(self.d['parents'])
        self.ibm = np.asarray(self.d['ibm'])
        self.joint_world = np.asarray(self.d['joint_world'])
        self.times = np.asarray(self.d['times']) if 'times' in self.d else np.array(TIMES)

    def subset(self, frames):
        """The same source restricted to some audit frames (tests / quick looks; reports use all 301)."""
        d = dict(self.d)
        d['joint_world'] = self.joint_world[frames]
        d['times'] = self.times[frames]
        return Source(d)

    @classmethod
    def load(cls, path):
        with np.load(path, allow_pickle=False) as z:
            return cls({k: z[k] for k in z.files})

    def joint(self, name):
        return self.names.index(name)

    def patch(self, name):
        return {k: np.asarray(self.d[f'{name}.{k}']) for k in ('pos', 'nrm', 'joints', 'weights')}

    def _blend(self, name):
        """Dense linear-blend operators: pos = [M_j(3x4)]_j @ S, normal = [R_j(3x3)]_j @ Sn (exact LBS)."""
        cache = self.__dict__.setdefault('_blend_cache', {})
        if name not in cache:
            p = self.patch(name)
            J, n = len(self.names), len(p['pos'])
            hom = np.hstack([p['pos'], np.ones((n, 1))]).astype(np.float64)
            S, Sn = np.zeros((J * 4, n)), np.zeros((J * 3, n))
            cols = np.arange(n)
            for k in range(4):
                j, w = p['joints'][:, k].astype(int), p['weights'][:, k].astype(np.float64)
                for c in range(4):
                    np.add.at(S, (j * 4 + c, cols), w * hom[:, c])
                for c in range(3):
                    np.add.at(Sn, (j * 3 + c, cols), w * p['nrm'][:, c].astype(np.float64))
            cache[name] = (S, Sn)
        return cache[name]

    def skin(self, name, worlds=None, frames=None):
        """Posed (F, N, 3) positions and unit normals in glTF world metres."""
        worlds = self.joint_world if worlds is None else worlds
        if frames is not None:
            worlds = worlds[frames]
        S, Sn = self._blend(name)
        J = len(self.names)
        mats = (worlds @ self.ibm[None])[..., :3, :]                             # (F, J, 3, 4)
        lin = mats.transpose(0, 2, 1, 3).reshape(len(worlds), 3, J * 4)           # rows: x, y, z
        pos = (lin @ S).transpose(0, 2, 1)                                        # (F, N, 3)
        rot = mats[..., :3].transpose(0, 2, 1, 3).reshape(len(worlds), 3, J * 3)
        nrm = (rot @ Sn).transpose(0, 2, 1)
        nrm /= np.maximum(np.linalg.norm(nrm, axis=-1, keepdims=True), 1e-12)
        return pos, nrm


def to_ue(p, body=BODY_CM, yaw=BODY_YAW):
    """glTF world metres -> UE world cm at the audited body transform (yaw about Z)."""
    p = np.asarray(p, dtype=float)
    comp = np.stack([p[..., 0], p[..., 2], p[..., 1]], axis=-1) * 100.
    a = np.radians(yaw)
    c, s = np.cos(a), np.sin(a)
    return np.stack([c * comp[..., 0] - s * comp[..., 1] + body[0], s * comp[..., 0] + c * comp[..., 1] + body[1],
                     comp[..., 2] + body[2]], axis=-1)


def to_ue_dir(v, yaw=BODY_YAW):
    v = np.asarray(v, dtype=float)
    comp = np.stack([v[..., 0], v[..., 2], v[..., 1]], axis=-1)
    a = np.radians(yaw)
    c, s = np.cos(a), np.sin(a)
    return np.stack([c * comp[..., 0] - s * comp[..., 1], s * comp[..., 0] + c * comp[..., 1], comp[..., 2]], axis=-1)


def native_quantile(values, q):
    """AnalyzeCapturedSeatSkin's quantile: sorted[clamp(int(q*(n-1)+.5))]."""
    v = np.sort(np.asarray(values))
    return float(v[min(max(int(q * (len(v) - 1) + .5), 0), len(v) - 1)])


def parity(source: Source):
    """Sole lowest/median/highest gap (to z = 0) at 3 s vs root's UE numbers, and the error."""
    out = {}
    for side, expected in ROOT_SOLES_3S.items():
        pos, _ = source.skin(f'{side}_sole', frames=[0])
        z = to_ue(pos[0])[:, 2]
        got = (float(z.min()), native_quantile(z, .5), float(z.max()))
        out[side] = {'source_cm': [round(v, 6) for v in got], 'root_ue_cm': list(expected),
                     'abs_error_cm': [round(abs(a - b), 6) for a, b in zip(got, expected)], 'vertices': int(len(z))}
    out['max_abs_error_cm'] = max(max(v['abs_error_cm']) for k, v in out.items() if k != 'max_abs_error_cm')
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--owner', default=str(OWNER))
    ap.add_argument('--clip', default=str(CLIP))
    ap.add_argument('--cache', default=str(ROOT / 'out/seat-fit-cache'))
    ap.add_argument('--out', default=str(ROOT / 'private-audit/seat-fit-source.npz'))
    args = ap.parse_args(argv)
    out = save(build(args.owner, args.clip, args.cache), args.out)
    source = Source.load(out)
    print(json.dumps({'out': str(out), 'bytes': out.stat().st_size, 'counts': source.meta['counts'],
                      'parity_3s': parity(source)}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
