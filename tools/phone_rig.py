"""Exact owner rig for phone-grip derivation: glTF clip IO, forward kinematics and linear-blend skinning.

Matches three.js (the renderer used by tools/phone_grip_hand_export.mjs): owner node rest TRS, clip
tracks bound by node name, LINEAR rotation keys, skinned vertex = sum_i w_i (World_i @ InverseBind_i) @ v
(mesh world and bind matrices are identity for the owner; asserted). Units: scene metres in, cm out.
"""
import hashlib
import json
import struct
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


def read_glb(path):
    raw = Path(path).read_bytes()
    if raw[:4] != b'glTF' or struct.unpack_from('<I', raw, 4)[0] != 2:
        raise ValueError('glTF 2 binary required')
    chunks, at = {}, 12
    while at < len(raw):
        size, kind = struct.unpack_from('<II', raw, at)
        chunks[kind] = raw[at+8:at+8+size]
        at += 8+size
    return json.loads(chunks[0x4e4f534a]), bytes(chunks.get(0x004e4942, b'')), hashlib.sha256(raw).hexdigest()


def accessor(doc, binary, index):
    a = doc['accessors'][index]
    view = doc['bufferViews'][a['bufferView']]
    if a.get('sparse') or view.get('extensions'):
        raise ValueError('Plain accessor required')
    if a['componentType'] != 5126:
        raise ValueError('Float accessor required')
    width = COMPONENTS[a['type']]
    stride = view.get('byteStride', width*4)
    start = view.get('byteOffset', 0)+a.get('byteOffset', 0)
    out = np.empty((a['count'], width), np.float64)
    for i in range(a['count']):
        out[i] = struct.unpack_from('<'+'f'*width, binary, start+i*stride)
    return out


def qnorm(q):
    return q/np.linalg.norm(q, axis=-1, keepdims=True)


def q_to_m(q):
    q = np.asarray(q, float)
    x, y, z, w = (q[..., i] for i in range(4))
    return np.stack([np.stack([1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)], -1),
                     np.stack([2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)], -1),
                     np.stack([2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)], -1)], -2)


def q_mul(a, b):
    ax, ay, az, aw = (a[..., i] for i in range(4))
    bx, by, bz, bw = (b[..., i] for i in range(4))
    return np.stack([aw*bx+ax*bw+ay*bz-az*by, aw*by-ax*bz+ay*bw+az*bx,
                     aw*bz+ax*by-ay*bx+az*bw, aw*bw-ax*bx-ay*by-az*bz], -1)


def q_axis_angle(axis, rad):
    axis = np.asarray(axis, float)
    axis = axis/np.linalg.norm(axis, axis=-1, keepdims=True)
    rad = np.asarray(rad, float)[..., None]
    return np.concatenate([axis*np.sin(rad/2), np.cos(rad/2)], -1)


def q_angle_deg(a, b):
    d = np.abs(np.sum(qnorm(a)*qnorm(b), -1)).clip(0, 1)
    return np.degrees(2*np.arccos(d))


class Rig:
    """Owner hierarchy driven by a captured clip; ``q`` (frames, nodes, 4) is the editable local rotation."""

    def __init__(self, skin_json, clip_path):
        self.skin_meta = json.loads(Path(skin_json).read_text())
        self.nodes = self.skin_meta['nodes']
        self.n = len(self.nodes)
        self.parent = {c: n['index'] for n in self.nodes for c in n['children']}
        self.name_index = {n['name']: n['index'] for n in self.nodes}
        order, seen = [], set()

        def visit(i):
            if i in seen:
                return
            if i in self.parent:
                visit(self.parent[i])
            seen.add(i)
            order.append(i)
        for i in range(self.n):
            visit(i)
        self.order = order
        self.clip_doc, self.clip_bin, self.clip_sha = read_glb(clip_path)
        self.clip_path = str(clip_path)
        anim = self.clip_doc['animations'][0]
        inputs = {anim['samplers'][c['sampler']]['input'] for c in anim['channels']}
        if len(inputs) != 1 or any(anim['samplers'][c['sampler']].get('interpolation', 'LINEAR') != 'LINEAR' for c in anim['channels']):
            raise ValueError('One shared LINEAR key input required')
        self.times = accessor(self.clip_doc, self.clip_bin, inputs.pop())[:, 0]
        F = len(self.times)
        self.t = np.tile(np.array([n['translation'] for n in self.nodes], float), (F, 1, 1))
        self.q = np.tile(np.array([n['rotation'] for n in self.nodes], float), (F, 1, 1))
        self.s = np.tile(np.array([n['scale'] for n in self.nodes], float), (F, 1, 1))
        self.channels = {}
        for c in anim['channels']:
            name = self.clip_doc['nodes'][c['target']['node']]['name']
            if name not in self.name_index:
                raise ValueError(f'Clip channel {name} has no owner node')
            i, path = self.name_index[name], c['target']['path']
            values = accessor(self.clip_doc, self.clip_bin, anim['samplers'][c['sampler']]['output'])
            {'rotation': self.q, 'translation': self.t, 'scale': self.s}[path][:, i] = values
            self.channels[(i, path)] = c
        self.q = qnorm(self.q)
        self.q0 = self.q.copy()

    def index(self, short):
        return self.name_index['mixamorig:'+short]

    def worlds(self, q=None, frames=None):
        q = self.q if q is None else q
        fr = slice(None) if frames is None else frames
        Q, Tt, S = q[fr], self.t[fr], self.s[fr]
        L = np.zeros(Q.shape[:2]+(4, 4))
        L[..., :3, :3] = q_to_m(Q)*S[..., None, :]
        L[..., :3, 3] = Tt
        L[..., 3, 3] = 1
        W = np.zeros_like(L)
        for i in self.order:
            W[:, i] = W[:, self.parent[i]]@L[:, i] if i in self.parent else L[:, i]
        return W


class Skin:
    def __init__(self, stem):
        stem = Path(stem)
        meta = json.loads(stem.with_suffix('.json').read_text())
        if any(not np.allclose(m, np.eye(4).ravel()) for m in meta['meshWorld']+meta['bindMatrix']):
            raise ValueError('Identity owner mesh/bind matrices expected')
        v, t = meta['vertices'], meta['triangles']
        raw = np.fromfile(stem.with_suffix('.bin'), np.uint8)
        o = 0
        self.bind = np.frombuffer(raw[o:o+v*12], np.float32).reshape(v, 3).astype(float); o += v*12
        self.joint = np.frombuffer(raw[o:o+v*8], np.uint16).reshape(v, 4).astype(int); o += v*8
        self.weight = np.frombuffer(raw[o:o+v*16], np.float32).reshape(v, 4).astype(float); o += v*16
        self.triangles = np.frombuffer(raw[o:o+t*12], np.uint32).reshape(t, 3).astype(np.int64); o += t*12
        self.mesh = np.frombuffer(raw[o:o+v], np.uint8)
        self.joint_nodes = np.array(meta['jointNodes'])
        self.joint_names = meta['joints']
        self.ibm = np.array([np.array(m).reshape(4, 4).T for m in meta['boneInverses']])
        self.owner_sha = meta['sha256']
        self.dominant = self.joint[np.arange(v), np.argmax(self.weight, 1)]

    def deform(self, W, vertices=None):
        """W: (nodes,4,4) one frame. Returns skinned positions in cm for ``vertices`` (default all)."""
        sel = slice(None) if vertices is None else vertices
        M = W[self.joint_nodes]@self.ibm                     # (joints,4,4)
        j, w, p = self.joint[sel], self.weight[sel], self.bind[sel]
        out = np.zeros((len(p), 3))
        for k in range(4):
            Mk = M[j[:, k]]
            out += w[:, k:k+1]*(np.einsum('nij,nj->ni', Mk[:, :3, :3], p)+Mk[:, :3, 3])
        return out*100
