"""Synthetic owner-like rigs and clips for the life-clip tests (written as real GLB files).

The owner-like skeleton has the Mixamo Standard Skeleton's 65 joints (mixamorig: names and
parents) under a structural 0.01-scale "mixamo" node, a T-pose rest, and a tiny skinned "feet"
mesh whose plantar vertices follow the owner's sole rule (rest Y <= 0.004 m, normal Y < -0.7),
plus a sock vertex (too high) and an upward-facing one, both of which the rule must exclude.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import life_gltf as G  # noqa: E402

P = 'mixamorig:'
FINGERS = {'Thumb': (2.0, 0.0, 3.5), 'Index': (8.0, 0.0, 2.0), 'Middle': (8.0, 0.0, 0.5),
           'Ring': (8.0, 0.0, -1.0), 'Pinky': (7.5, 0.0, -2.5)}


def skeleton_spec():
    """[(name, parent, local translation cm)] in parent-first order; left is +x, facing +z."""
    s = [('Hips', None, (0.0, 92.0, 0.0)), ('Spine', 'Hips', (0.0, 10.0, 0.0)), ('Spine1', 'Spine', (0.0, 10.0, 0.0)),
         ('Spine2', 'Spine1', (0.0, 10.0, 0.0)), ('Neck', 'Spine2', (0.0, 15.0, 0.0)), ('Head', 'Neck', (0.0, 8.0, 0.0)),
         ('HeadTop_End', 'Head', (0.0, 20.0, 0.0))]
    for side, k in (('Left', 1.0), ('Right', -1.0)):
        s += [(side + 'Shoulder', 'Spine2', (6.0 * k, 12.0, 0.0)), (side + 'Arm', side + 'Shoulder', (12.0 * k, 0.0, 0.0)),
              (side + 'ForeArm', side + 'Arm', (27.0 * k, 0.0, 0.0)), (side + 'Hand', side + 'ForeArm', (23.0 * k, 0.0, 0.0))]
        for f, (x, y, z) in FINGERS.items():
            s.append((f'{side}Hand{f}1', side + 'Hand', (x * k, y, z)))
            for seg, ln in ((2, 3.0), (3, 2.5), (4, 2.0)):
                s.append((f'{side}Hand{f}{seg}', f'{side}Hand{f}{seg - 1}', (ln * k, 0.0, 0.0)))
    for side, k in (('Left', 1.0), ('Right', -1.0)):
        s += [(side + 'UpLeg', 'Hips', (9.0 * k, -6.0, 0.0)), (side + 'Leg', side + 'UpLeg', (0.0, -40.0, 0.0)),
              (side + 'Foot', side + 'Leg', (0.0, -42.0, 0.0)), (side + 'ToeBase', side + 'Foot', (0.0, -3.0, 10.0)),
              (side + 'Toe_End', side + 'ToeBase', (0.0, 0.0, 8.0))]
    assert len(s) == 65
    return s


def world_rest_cm(spec):
    pos = {}
    for name, parent, t in spec:
        pos[name] = t if parent is None else G.vadd(pos[parent], t)
    return pos


def mat_inverse_translation(p, scale=0.01):
    """Column-major glTF inverse bind matrix of a joint at world p (metres) under the 0.01 armature."""
    k = 1 / scale
    return [k, 0, 0, 0, 0, k, 0, 0, 0, 0, k, 0, -p[0] * k, -p[1] * k, -p[2] * k, 1]


def build(path, clip=None, *, drop=(), reparent=None, root_track=None, prefix=P, mesh=True, extra_nodes=None):
    """Write an owner-like GLB. clip: {'times': [...], 'rot': {joint: [q...]}, 'trans': {joint: [t cm...]}}."""
    spec = [row for row in skeleton_spec() if row[0] not in drop]
    if reparent:
        spec = [(n, reparent.get(n, p), t) for n, p, t in spec]
    bw = G.BinWriter()
    nodes = [{'name': 'mixamo', 'scale': [0.01, 0.01, 0.01], 'children': []}]
    index = {}
    for name, parent, t in spec:
        index[name] = len(nodes)
        nodes.append({'name': prefix + name, 'translation': list(t), 'rotation': [0.0, 0.0, 0.0, 1.0]})
    for name, parent, _ in spec:
        holder = nodes[index[parent]] if parent else nodes[0]
        holder.setdefault('children', []).append(index[name])
    scene_roots = [0]
    doc = {'asset': {'version': '2.0', 'generator': 'life_clip_synth'}, 'scene': 0, 'nodes': nodes}
    if mesh:
        pos = world_rest_cm(skeleton_spec())
        joints = [index[n] for n, _, _ in spec]
        ibm = [mat_inverse_translation(tuple(c * 0.01 for c in pos[n])) for n, _, _ in spec]
        verts, normals, jidx = [], [], []
        for side in ('Left', 'Right'):
            if side + 'Foot' not in index:
                continue
            fx = pos[side + 'Foot'][0] * 0.01
            grid = [(-0.03 + 0.02 * a, -0.04 + 0.04 * b, 0.001 * ((a + b) % 4)) for a in range(4) for b in range(4)]
            for dx, dz, y in grid:                   # 16 plantar vertices per foot, rest Y 0..0.003 m
                verts.append((fx + dx, y, dz))
                normals.append((0.0, -1.0, 0.0))
                jidx.append(joints.index(index[side + 'Foot']))
            verts.append((fx, 0.03, 0.0))            # sock: too high, excluded
            normals.append((0.0, -1.0, 0.0))
            jidx.append(joints.index(index[side + 'Foot']))
            verts.append((fx, 0.001, 0.02))          # faces up, excluded
            normals.append((0.0, 1.0, 0.0))
            jidx.append(joints.index(index[side + 'Foot']))
        a_pos = bw.add(verts, 'VEC3', minmax=True)
        a_nrm = bw.add(normals, 'VEC3')
        a_w = bw.add([(1.0, 0.0, 0.0, 0.0)] * len(verts), 'VEC4')
        a_ibm = len(bw.accessors)
        off = len(bw.data)
        import struct
        for m in ibm:
            bw.data += struct.pack('<16f', *m)
        bw.views.append({'buffer': 0, 'byteOffset': off, 'byteLength': len(bw.data) - off})
        bw.accessors.append({'bufferView': len(bw.views) - 1, 'componentType': 5126, 'count': len(ibm), 'type': 'MAT4'})
        off = len(bw.data)
        for j in jidx:
            bw.data += struct.pack('<4H', j, 0, 0, 0)
        bw.views.append({'buffer': 0, 'byteOffset': off, 'byteLength': len(bw.data) - off})
        bw.accessors.append({'bufferView': len(bw.views) - 1, 'componentType': 5123, 'count': len(jidx), 'type': 'VEC4'})
        a_j = len(bw.accessors) - 1
        doc['materials'] = [{'name': 'feet'}]
        doc['meshes'] = [{'primitives': [{'attributes': {'POSITION': a_pos, 'NORMAL': a_nrm, 'JOINTS_0': a_j,
                                                          'WEIGHTS_0': a_w}, 'material': 0, 'mode': 0}]}]
        doc['skins'] = [{'joints': joints, 'inverseBindMatrices': a_ibm, 'skeleton': index['Hips']}]
        nodes.append({'name': 'slides', 'mesh': 0, 'skin': 0})
        scene_roots.append(len(nodes) - 1)
    doc['scenes'] = [{'nodes': scene_roots}]
    if clip:
        ti = bw.add(clip['times'], 'SCALAR', minmax=True)
        anim = {'name': clip.get('name', 'Idle'), 'samplers': [], 'channels': []}
        for kind, prop, width in (('rot', 'rotation', 'VEC4'), ('trans', 'translation', 'VEC3')):
            for joint, values in clip.get(kind, {}).items():
                if joint not in index:
                    continue
                vi = bw.add(values, width)
                anim['samplers'].append({'input': ti, 'output': vi, 'interpolation': 'LINEAR'})
                anim['channels'].append({'sampler': len(anim['samplers']) - 1, 'target': {'node': index[joint], 'path': prop}})
        if root_track:
            vi = bw.add(root_track, 'VEC3')
            anim['samplers'].append({'input': ti, 'output': vi, 'interpolation': 'LINEAR'})
            anim['channels'].append({'sampler': len(anim['samplers']) - 1, 'target': {'node': 0, 'path': 'translation'}})
        doc['animations'] = [anim]
    doc.update({'accessors': bw.accessors, 'bufferViews': bw.views,
                'buffers': [{'byteLength': len(bw.data) + (-len(bw.data)) % 4}]})
    G.write_glb(path, doc, bytes(bw.data))
    return path


def idle_clip(seconds=2.0, fps=30, *, stretch=False, ramp=False, drift_cm=0.0, slide_cm=0.0):
    """A breathing-like idle: spine and arms sway with one period over the clip (so it loops)."""
    n = int(round(seconds * fps)) + 1
    times = [k / fps for k in range(n)]
    rot, trans = {}, {}
    for joint, axis, amp in (('Spine', (1, 0, 0), 2.0), ('Spine2', (0, 0, 1), 1.5), ('Neck', (0, 1, 0), 3.0),
                             ('LeftArm', (0, 0, 1), -4.0), ('RightArm', (0, 0, 1), 4.0), ('LeftForeArm', (0, 1, 0), 3.0)):
        vals = []
        for t in times:
            phase = math.sin(2 * math.pi * t / seconds)
            angle = math.radians(amp * phase + (25.0 * t / seconds if ramp and joint == 'Spine' else 0.0))
            vals.append(G.qaxis(axis, angle))
        rot[joint] = vals
    trans['Hips'] = [(drift_cm * t / seconds + slide_cm * math.sin(2 * math.pi * t / seconds), 92.0, 0.0) for t in times]
    if stretch:
        trans['LeftForeArm'] = [(27.0 + 0.5 * math.sin(2 * math.pi * t / seconds), 0.0, 0.0) for t in times]
    return {'times': times, 'rot': rot, 'trans': trans}
