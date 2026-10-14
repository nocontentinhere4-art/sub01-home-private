"""Retarget a measured standing-idle clip from another rig onto the owner skeleton (no IK, no posing).

    python3 tools/retarget_life_clip.py SOURCE.glb OUTPUT.glb --preset v5|ual_boy|mixamo [--mapping MAP.json] [--animation NAME]
        [--owner web/room/char_mixamo.glb] [--trim auto|none|I:J] [--work DIR] [--no-soles]

The retarget itself is the existing tools/retarget_first_person.mjs (run with Node, unchanged):
    Q_target_world(t) = C * Q_src_world(t) * inverse(Q_src_rest_world) * inverse(C) * Q_target_rest_world
    target local      = inverse(Q_target_parent_world(t)) * Q_target_world(t)
C is its anatomical basis alignment (hips lateral / chest up), the owner's local translations are
kept (bone lengths exact), and the hips translation is the source's world delta times the measured
leg-height ratio. Meshopt-compressed sources are decoded by tools/uncompress_unreal_glb.mjs (the
vendored official decoder). This file only adds the steps that .mjs needs around it:

1. Prepare (pure renaming and bookkeeping, motion unchanged; the report proves it):
   * the source's skeleton nodes and the ONE chosen animation, nodes renamed to the owner's
     mixamorig: names by an explicit table (PRESETS; Mixamo prefixes such as mixamorig1: are
     normalised); unmapped intermediate nodes (twist, pelvis, metacarpal) keep their motion;
   * an owner joint the source does not have (finger endpoints, HeadTop_End, Toe_End; every finger
     on a rig without fingers) becomes a STATIC leaf without keys, so that joint holds the owner's
     rest relative to its parent: nothing is invented;
   * rest re-basing: the .mjs delta assumes both rests are the same pose. An A-pose source rest
     against the owner's T-pose would put the arms out. So each mapped source joint's REST rotation
     is swung (shortest arc; the hands also by the index-pinky axis) until its bone points where the
     owner's does, after C. Its animation tracks are absolute local rotations, so the animated pose
     is unchanged; a re-based node without a rotation track gets a constant track holding its
     original rest. The report gives every correction angle and the max animated-joint difference
     between the prepared and the original source (should be ~0).
2. Retarget with the .mjs (its own audit: no-motion rest recovery, bone lengths).
3. In place: the hips track keeps its measured sway, minus the constant horizontal offset of the
   first frame (so he stands where the owner's rest stands) and the linear horizontal drift from
   the first to the last frame. Both removed amounts are reported. Vertical motion is untouched.
4. Loop window (--trim auto): if the whole clip does not pass the loop, feet and hips gates, the
   longest contiguous window of the measured frames that does is chosen by exhaustive search and
   reported; nothing is crossfaded, blended or posed. --trim none keeps the whole clip.
5. Residuals: tools/verify_life_idle_candidate.py on the output (bone lengths, rest parity, joint
   and sole foot planting, floor, loop, hips travel, symmetry, timing), written to
   OUTPUT.report.json next to the output. A failing check is reported, never hidden.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import life_gltf as G  # noqa: E402
import verify_life_idle_candidate as V  # noqa: E402

SCHEMA = 'sub01.life-clip-retarget.v1'
MJS = ROOT / 'tools/retarget_first_person.mjs'
FINGERS = ('Thumb', 'Index', 'Middle', 'Ring', 'Pinky')
SIDES = (('Left', 'L'), ('Right', 'R'))
MIN_LOOP_S = 2.0


def _v5():
    m = {'Hips': 'Hip', 'Spine': 'Waist', 'Spine1': 'Spine01', 'Spine2': 'Spine02', 'Neck': 'NeckTwist01',
         'Head': 'Head', 'HeadTop_End': None}
    for side, s in SIDES:
        m.update({side + 'Shoulder': s + '_Clavicle', side + 'Arm': s + '_Upperarm', side + 'ForeArm': s + '_Forearm',
                  side + 'Hand': s + '_Hand', side + 'UpLeg': s + '_Thigh', side + 'Leg': s + '_Calf',
                  side + 'Foot': s + '_Foot', side + 'ToeBase': s + '_ToeBase', side + 'Toe_End': None})
        for k, f in enumerate(FINGERS, 1):
            for seg in (1, 2, 3):
                m[f'{side}Hand{f}{seg}'] = f'finger{k}-{seg}.{s}'
            m[f'{side}Hand{f}4'] = None
    return m


def _ual_boy():
    m = {'Hips': 'Hips', 'Spine': 'Spine02', 'Spine1': 'Spine01', 'Spine2': 'Spine', 'Neck': 'neck', 'Head': 'Head',
         'HeadTop_End': 'head_end'}
    for side, _ in SIDES:
        for part in ('Shoulder', 'Arm', 'ForeArm', 'Hand', 'UpLeg', 'Leg', 'Foot', 'ToeBase'):
            m[side + part] = side + part
        m[side + 'Toe_End'] = None
        for f in FINGERS:
            for seg in (1, 2, 3, 4):
                m[f'{side}Hand{f}{seg}'] = None
    return m


# Explicit tables: owner joint (no prefix) -> source node name, or None = static leaf (owner rest).
PRESETS = {
    'v5': {'mapping': _v5, 'note': 'Tripo v5 rig (web/room/char_v5.glb): Hip/Waist/Spine01/Spine02/NeckTwist01, '
                                    'L_/R_ limbs, finger1..5-1..3 (thumb..pinky). Twist, Pelvis and metacarpal '
                                    'nodes are unmapped intermediates (their motion reaches the mapped joints).'},
    'ual_boy': {'mapping': _ual_boy, 'note': 'The first character\'s 24-bone rig (web/room/boy_moves.glb): no '
                                              'fingers, so the owner\'s fingers hold their rest relative to the hand.'},
    'mixamo': {'mapping': None, 'note': 'Any Mixamo skeleton (mixamorig:, mixamorig1:, ...), mapped by name.'},
}

BASIS_JOINTS = ('Hips', 'Spine', 'Spine1')
PRIMARY_CHILD = {'Spine': 'Spine1', 'Spine1': 'Spine2', 'Spine2': 'Neck', 'Neck': 'Head', 'Head': 'HeadTop_End'}
for _side, _ in SIDES:
    PRIMARY_CHILD.update({_side + 'Shoulder': _side + 'Arm', _side + 'Arm': _side + 'ForeArm',
                          _side + 'ForeArm': _side + 'Hand', _side + 'Hand': _side + 'HandMiddle1',
                          _side + 'UpLeg': _side + 'Leg', _side + 'Leg': _side + 'Foot', _side + 'Foot': _side + 'ToeBase',
                          _side + 'ToeBase': _side + 'Toe_End'})
    for _f in FINGERS:
        for _seg in (1, 2, 3):
            PRIMARY_CHILD[f'{_side}Hand{_f}{_seg}'] = f'{_side}Hand{_f}{_seg + 1}'


def mapping_for(preset, src: G.Gltf, owner: V.Owner, explicit=None):
    if explicit is not None:
        missing = sorted(set(owner.names) - set(explicit))
        if missing:
            raise ValueError(f'explicit mapping must name every owner joint (null = static leaf); missing {missing}')
        return {o: explicit[o] for o in owner.names}
    table = PRESETS[preset]['mapping']
    if table is None:
        by_canon = {}
        for n in src.nodes:
            if V.PREFIX.match(n.get('name', '')) and 'mesh' not in n:
                by_canon.setdefault(V.canonical(n['name']), n['name'])
        return {o: by_canon.get(o) for o in owner.names}
    m = table()
    missing = sorted(set(owner.names) - set(m))
    if missing:
        raise ValueError(f'mapping table lacks owner joints {missing}')
    return {o: m[o] for o in owner.names}


def topo(owner: V.Owner):
    out, seen = [], set()

    def visit(n):
        if n in seen:
            return
        if owner.parent[n]:
            visit(owner.parent[n])
        seen.add(n)
        out.append(n)
    for n in owner.names:
        visit(n)
    return out


# ------------------------------------------------------------------ a small editable rig for preparation
class Rig:
    def __init__(self):
        self.name, self.t, self.q, self.s, self.parent = [], [], [], [], []

    def add(self, name, t, q, s, parent):
        self.name.append(name)
        self.t.append(tuple(t))
        self.q.append(tuple(q))
        self.s.append(tuple(s))
        self.parent.append(parent)
        return len(self.name) - 1

    def world(self):
        w = []
        for i in range(len(self.name)):
            p = self.parent[i]
            sc = sum(self.s[i]) / 3
            if p is None:
                w.append((self.t[i], G.qnorm(self.q[i]), sc))
            else:
                pt, pq, ps = w[p]
                r = G.qrot(pq, self.t[i])
                w.append((G.vadd(pt, G.vscale(r, ps)), G.qnorm(G.qmul(pq, self.q[i])), ps * sc))
        return w


def anatomical_basis(pos):
    """retarget_first_person.mjs basis(): x = right - left hip, y = chest - hips (orthogonalised)."""
    x = G.vunit(G.vsub(pos['RightUpLeg'], pos['LeftUpLeg']))
    y = G.vsub(pos['Spine2'], pos['Hips'])
    y = G.vunit(G.vsub(y, G.vscale(x, G.vdot(y, x))))
    return G.frame_quat(x, y), y


def leg_height(pos, up):
    feet = G.vscale(G.vadd(pos['LeftFoot'], pos['RightFoot']), .5)
    return G.vdot(G.vsub(pos['Hips'], feet), up)


def prepare_source(src: G.Gltf, animation, mapping, owner: V.Owner, out_path: Path):
    clip = src.animation(animation)
    mapped = {o: src.by_name[s] for o, s in mapping.items() if s is not None}
    unknown = sorted(s for s in mapping.values() if s is not None and s not in src.by_name)
    if unknown:
        raise ValueError(f'source lacks mapped nodes {unknown}')
    keep = set()
    for i in mapped.values():
        while i is not None and i not in keep:
            keep.add(i)
            i = src.parent.get(i)
    order, seen = [], set()

    def visit(i):
        if i in seen:
            return
        if i in src.parent and src.parent[i] in keep:
            visit(src.parent[i])
        seen.add(i)
        order.append(i)
    for i in sorted(keep):
        visit(i)
    back = {v: k for k, v in mapped.items()}
    rig, new = Rig(), {}
    for i in order:
        t, q, s = src.rest(i)
        name = V.OWNER_PREFIX + back[i] if i in back else 'src:' + src.nodes[i].get('name', f'node{i}')
        new[i] = rig.add(name, t, q, s, new.get(src.parent.get(i)))
    joint = {o: new[i] for o, i in mapped.items()}
    real = set(joint)
    owner_pos = {o: owner.rest_world[o][0] for o in owner.names}
    basis_own, up_own = anatomical_basis(owner_pos)
    original_q = list(rig.q)
    original_world = rig.world()

    def alignment():
        pos = {o: w[j][0] for w in [rig.world()] for o, j in joint.items()}
        bs, _ = anatomical_basis(pos)
        return G.qmul(basis_own, G.qinv(bs))

    # Rest re-basing of the mapped joints, one top-down pass with the .mjs's own C (computed from the
    # source rest). Hips, Spine and Spine1 are NOT re-based: they place Spine2, which defines that
    # basis, so re-basing them would change C itself (it does not converge: each pass tilts the
    # frame further). Their residual is reported by the .mjs audit instead.
    C = alignment()
    Cinv = G.qinv(C)
    passes = 1
    for o in topo(owner):
        c = PRIMARY_CHILD.get(o)
        if o in BASIS_JOINTS or o not in real or c not in real:
            continue
        w = rig.world()
        j = joint[o]
        d_cur = G.vsub(w[joint[c]][0], w[j][0])
        d_tgt = G.qrot(Cinv, G.vsub(owner_pos[c], owner_pos[o]))
        lat = (o.replace('Hand', 'HandIndex1'), o.replace('Hand', 'HandPinky1')) if o.endswith('Hand') else (None, None)
        if lat[0] in real and lat[1] in real:
            l_cur = G.vsub(w[joint[lat[0]]][0], w[joint[lat[1]]][0])
            l_tgt = G.qrot(Cinv, G.vsub(owner_pos[lat[0]], owner_pos[lat[1]]))
            A = G.qmul(G.frame_quat(d_tgt, l_tgt), G.qinv(G.frame_quat(d_cur, l_cur)))
        else:
            A = G.arc(d_cur, d_tgt)
        parent_q = w[rig.parent[j]][1] if rig.parent[j] is not None else G.IDENTITY
        rig.q[j] = G.qnorm(G.qmul(G.qinv(parent_q), G.qmul(A, w[j][1])))
    if G.qangle_deg(alignment(), C) > 1e-6:
        raise RuntimeError('re-basing changed the anatomical basis')
    final_world = rig.world()
    corrections = {o: round(G.qangle_deg(final_world[j][1], original_world[j][1]), 4)
                   for o, j in joint.items() if G.qangle_deg(final_world[j][1], original_world[j][1]) > 1e-6}
    pos = {o: final_world[j][0] for o, j in joint.items()}
    ratio = leg_height(pos, G.qrot(Cinv, up_own)) / leg_height(owner_pos, up_own)
    # Static leaves for owner joints the source does not have: no keys, placed along the owner's own
    # rest direction (after C), so the joint above them keeps the owner's rest relation to them.
    added = []
    for o in topo(owner):
        if o in joint:
            continue
        p = owner.parent[o]
        if p is None or p not in joint:
            raise ValueError(f'cannot place static leaf {o}: parent {p} absent')
        w = rig.world()
        pj = joint[p]
        d = G.vunit(G.qrot(Cinv, G.vsub(owner_pos[o], owner_pos[p])))
        length = G.vlen(owner.offset_cm[o]) / 100 * ratio
        local = G.vscale(G.qrot(G.qinv(w[pj][1]), G.vscale(d, length)), 1 / w[pj][2])
        joint[o] = rig.add(V.OWNER_PREFIX + o, local, G.IDENTITY, (1.0, 1.0, 1.0), pj)
        added.append(o)
    undefined_direction = sorted(o for o in real if o != 'Hips' and PRIMARY_CHILD.get(o) in joint
                                 and PRIMARY_CHILD.get(o) not in real)
    # Animation of the chosen clip, on the kept nodes; constant tracks hold re-based untracked rests.
    tracks, dropped_scale = {}, 0.0
    for (node, path), (times, values, interp) in clip.tracks.items():
        if node not in new:
            continue
        if path == 'scale':
            rest_s = src.rest(node)[2]
            dev = max(max(abs(a - b) for a, b in zip(v, rest_s)) for v in values)
            if dev <= G.SCALE_ANISOTROPY_TOLERANCE:
                dropped_scale = max(dropped_scale, dev)     # float noise on exported scale keys
                continue
        tracks[(new[node], path)] = (times, values, interp)
    held = []
    for i, (q0, q1) in enumerate(zip(original_q, rig.q[:len(original_q)])):
        if G.qangle_deg(q0, q1) > 1e-9 and (i, 'rotation') not in tracks:
            tracks[(i, 'rotation')] = ([clip.start, clip.end], [q0, q0], 'LINEAR')
            held.append(rig.name[i])
    write_rig(out_path, rig, tracks, clip.name or 'clip')
    # Proof that the prepared source moves exactly as the original.
    prepared = G.Gltf(out_path)
    pclip = prepared.animation(clip.name or 'clip')
    worst = 0.0
    for t in clip.key_times():
        wo = G.world_pose(src, clip, t, list(mapped.values()))
        wp = G.world_pose(prepared, pclip, t)
        for o, i in mapped.items():
            worst = max(worst, G.vlen(G.vsub(wo[i][0], wp[prepared.by_name[V.OWNER_PREFIX + o]][0])) * 100)
    return {'prepared': str(out_path), 'mapped_joints': len(mapped), 'static_leaves_added': added,
            'rest_rebase_correction_deg': corrections, 'rest_rebase_passes': passes,
            'source_direction_undefined_child_is_static_leaf': undefined_direction, 'constant_tracks_holding_original_rest': held,
            'prepared_vs_original_max_joint_cm': round(worst, 8),
            'dropped_scale_track_noise_max': dropped_scale, 'source_leg_height_over_owner': round(ratio, 6),
            'kept_unmapped_nodes': sorted(n for n in rig.name if n.startswith('src:'))}


def write_rig(path, rig: Rig, tracks, name):
    bw = G.BinWriter()
    children = {i: [] for i in range(len(rig.name))}
    for i, p in enumerate(rig.parent):
        if p is not None:
            children[p].append(i)
    nodes = []
    for i in range(len(rig.name)):
        n = {'name': rig.name[i], 'translation': list(rig.t[i]), 'rotation': list(G.qnorm(rig.q[i])), 'scale': list(rig.s[i])}
        if children[i]:
            n['children'] = children[i]
        nodes.append(n)
    anim = {'name': name, 'samplers': [], 'channels': []}
    for (node, prop), (times, values, interp) in sorted(tracks.items()):
        ti = bw.add(list(times), 'SCALAR', minmax=True)
        vi = bw.add([tuple(v) for v in values], {'rotation': 'VEC4', 'translation': 'VEC3', 'scale': 'VEC3'}[prop])
        anim['samplers'].append({'input': ti, 'output': vi, 'interpolation': interp})
        anim['channels'].append({'sampler': len(anim['samplers']) - 1, 'target': {'node': node, 'path': prop}})
    doc = {'asset': {'version': '2.0', 'generator': 'SUB01 retarget_life_clip prepare (renamed, rest re-based; motion unchanged)'},
           'scene': 0, 'scenes': [{'nodes': [i for i, p in enumerate(rig.parent) if p is None]}], 'nodes': nodes,
           'animations': [anim], 'accessors': bw.accessors, 'bufferViews': bw.views,
           'buffers': [{'byteLength': len(bw.data) + (-len(bw.data)) % 4}]}
    return G.write_glb(path, doc, bytes(bw.data))


# ------------------------------------------------------------------ after the .mjs
def read_output(path: Path):
    g = G.Gltf(path)
    clip = g.animation()
    times = clip.key_times()
    return g, clip, times


def loop_search(g, clip, times, owner: V.Owner):
    """Exhaustive window search over the measured frames (numpy); nothing is blended."""
    import numpy as np
    cand = V.Candidate(g, owner)
    frames = [(t, G.world_pose(g, clip, t)) for t in times]
    names = list(cand.node)
    shapes = np.array([[V.hips_frame_positions(w, cand)[n] for n in names] for _, w in frames])     # cm
    hips = np.array([w[cand.node['Hips']][0] for _, w in frames]) * 100
    feet = np.array([[w[cand.node[f]][0] for f in V.FEET] for _, w in frames]) * 100
    fps = (len(times) - 1) / (times[-1] - times[0])
    n = len(times)
    min_len = int(round(MIN_LOOP_S * fps))
    best_cost, best_ok, best_planted = None, None, None
    vel = shapes[1:] - shapes[:-1]                                   # vel[k] = shape[k+1] - shape[k]
    for i in range(0, n - min_len):
        js = np.arange(i + min_len, n)
        pose = np.linalg.norm(shapes[js] - shapes[i], axis=2).max(axis=1)
        hw = np.linalg.norm(hips[js] - hips[i], axis=1)
        dv = np.linalg.norm(vel[js - 1] - vel[i], axis=2).max(axis=1) * fps
        h_slide = np.maximum.accumulate(np.linalg.norm((hips[i:, [0, 2]] - hips[i, [0, 2]]), axis=1))[js - i]
        f_disp = feet[i:] - feet[i]
        f_slide = np.maximum.accumulate(np.linalg.norm(f_disp[:, :, [0, 2]], axis=2).max(axis=1))[js - i]
        f_rise = np.maximum.accumulate(np.abs(f_disp[:, :, 1]).max(axis=1))[js - i]
        cost = np.maximum.reduce([pose / V.LOOP_MAX_POSE_CM, hw / V.LOOP_MAX_POSE_CM, dv / V.LOOP_MAX_VELOCITY_CM_S])
        k = int(np.argmin(cost))
        if best_cost is None or cost[k] < best_cost[0]:
            best_cost = (float(cost[k]), i, int(js[k]), float(pose[k]), float(hw[k]), float(dv[k]))
        planted = (h_slide <= V.HIPS_MAX_TRAVEL_CM) & (f_slide <= V.FOOT_MAX_SLIDE_CM) & (f_rise <= V.FOOT_MAX_HEIGHT_RANGE_CM)
        if planted.any():
            k = int(np.argmin(np.where(planted, cost, np.inf)))
            if best_planted is None or cost[k] < best_planted[0]:
                best_planted = (float(cost[k]), i, int(js[k]), float(pose[k]), float(hw[k]), float(dv[k]))
        ok = (pose <= V.LOOP_MAX_POSE_CM) & (hw <= V.LOOP_MAX_POSE_CM) & (dv <= V.LOOP_MAX_VELOCITY_CM_S) & planted
        if ok.any():
            k = int(np.nonzero(ok)[0][-1])
            if best_ok is None or js[k] - i > best_ok[2] - best_ok[1]:
                best_ok = (float(cost[k]), i, int(js[k]), float(pose[k]), float(hw[k]), float(dv[k]))

    def row(b):
        if b is None:
            return None
        return {'start_frame': b[1], 'end_frame': b[2], 'start_s': round(times[b[1]] - times[0], 6),
                'end_s': round(times[b[2]] - times[0], 6), 'duration_s': round(times[b[2]] - times[b[1]], 6),
                'pose_cm': round(b[3], 6), 'hips_world_cm': round(b[4], 6), 'velocity_cm_s': round(b[5], 6),
                'normalised_cost': round(b[0], 6)}
    return {'frames': n, 'min_window_s': MIN_LOOP_S,
            'best_loop_window': row(best_cost),
            'best_loop_among_planted_windows': row(best_planted),
            'longest_window_passing_loop_feet_and_hips': row(best_ok),
            'rule': 'normalised_cost = max(pose/0.5 cm, hips/0.5 cm, velocity/5 cm/s), passes at <= 1; loop: pose <= 0.5 cm, hips <= 0.5 cm, velocity <= 5 cm/s between window start/end frames; '
                    'feet joints slide <= 2 cm and rise <= 2 cm, hips travel <= 5 cm within the window'}


def finalize(g: G.Gltf, clip, times, window, in_place, out_path: Path):
    """Slice [i..j] of the measured frames, shift time to 0, remove the hips' horizontal offset and drift."""
    i, j = window
    sel = times[i:j + 1]
    hips = g.by_name[V.OWNER_PREFIX + 'Hips']
    parent = g.parent[hips]
    pw = G.world_pose(g, G.RestPose, 0, [parent])[parent]
    if G.qangle_deg(pw[1], G.IDENTITY) > 1e-6:
        raise ValueError('hips parent is rotated; the horizontal in-place step assumes a Y-up unrotated root')
    rest_t = g.rest(hips)[0]
    raw = [clip.sample(hips, 'translation', t, rest_t) for t in sel]
    t0, t1 = sel[0], sel[-1]
    off = (raw[0][0] - rest_t[0], raw[0][2] - rest_t[2])
    drift = (raw[-1][0] - raw[0][0], raw[-1][2] - raw[0][2])
    fixed = []
    for t, v in zip(sel, raw):
        a = (t - t0) / (t1 - t0) if in_place else 0
        dx = off[0] + drift[0] * a if in_place else 0
        dz = off[1] + drift[1] * a if in_place else 0
        fixed.append((v[0] - dx, v[1], v[2] - dz))
    to_cm = pw[2] * 100
    bw = G.BinWriter()
    ti = bw.add([t - t0 for t in sel], 'SCALAR', minmax=True)
    anim = {'name': 'Idle', 'samplers': [], 'channels': []}
    for (node, prop) in sorted(clip.tracks):
        if prop == 'translation' and node == hips:
            values = fixed
        else:
            values = [clip.sample(node, prop, t, None) for t in sel]
        vi = bw.add(values, 'VEC4' if prop == 'rotation' else 'VEC3')
        anim['samplers'].append({'input': ti, 'output': vi, 'interpolation': 'LINEAR'})
        anim['channels'].append({'sampler': len(anim['samplers']) - 1, 'target': {'node': node, 'path': prop}})
    doc = {'asset': {'version': '2.0', 'generator': 'SUB01 retarget_life_clip (retarget_first_person.mjs rest-delta; '
                                                    'measured window; hips in place)'},
           'scene': 0, 'scenes': g.doc['scenes'], 'nodes': g.doc['nodes'], 'animations': [anim],
           'accessors': bw.accessors, 'bufferViews': bw.views,
           'buffers': [{'byteLength': len(bw.data) + (-len(bw.data)) % 4}]}
    sha = G.write_glb(out_path, doc, bytes(bw.data))
    return {'window_frames': [i, j], 'window_source_s': [round(t0 - times[0], 6), round(t1 - times[0], 6)],
            'frames': len(sel), 'duration_s': round(t1 - t0, 6), 'in_place': in_place,
            'removed_start_offset_cm': [round(c * to_cm, 6) for c in off],
            'removed_linear_drift_cm': [round(c * to_cm, 6) for c in drift],
            'output_sha256': sha}


def retarget(source: Path, output: Path, preset: str, animation=None, owner_path: Path = V.OWNER,
             trim='auto', work: Path | None = None, soles=True, in_place=True, provenance=None, mapping=None):
    work = Path(work or output.parent / (output.stem + '.work'))
    work.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    src_path = V.decoded(source, work)
    src = G.Gltf(src_path)
    owner = V.Owner(G.Gltf(owner_path))
    explicit_note = None if mapping is None else 'explicit mapping table supplied by the caller'
    mapping = mapping_for(preset, src, owner, mapping)
    prepared = work / 'prepared_source.glb'
    prep = prepare_source(src, animation, mapping, owner, prepared)
    clip_name = src.animation(animation).name or 'clip'
    raw_out = work / 'retarget_first_person_output.glb'
    proc = subprocess.run(['node', str(MJS), str(prepared), str(owner_path), str(raw_out), '--clip', clip_name],
                          capture_output=True, text=True)
    if proc.returncode:
        raise RuntimeError('retarget_first_person.mjs refused: ' + (proc.stderr or proc.stdout)[-2000:])
    audit = json.loads(Path(str(raw_out) + '.audit.json').read_text())
    g, clip, times = read_output(raw_out)
    search = loop_search(g, clip, times, owner)
    whole = (0, len(times) - 1)
    if trim == 'none':
        window, why = whole, 'whole clip (--trim none)'
    elif trim == 'auto':
        full = search['longest_window_passing_loop_feet_and_hips']
        if full and full['start_frame'] == 0 and full['end_frame'] == len(times) - 1:
            window, why = whole, 'whole clip passes'
        elif full:
            window, why = (full['start_frame'], full['end_frame']), 'longest measured window passing loop, feet and hips'
        else:
            window, why = whole, 'no window passes; whole clip kept and reported as failing'
    else:
        a, b = trim.split(':')
        window, why = (int(a), int(b)), 'explicit window'
    fin = finalize(g, clip, times, window, in_place, output)
    report = V.verify(output, owner_path, soles=soles, workdir=work)
    out = {
        'schema': SCHEMA, 'source': str(source), 'source_sha256': G.Gltf(source).sha256, 'animation': clip_name,
        'preset': preset if explicit_note is None else 'explicit-mapping',
        'preset_note': PRESETS[preset]['note'] if explicit_note is None else explicit_note, 'provenance': provenance,
        'owner': str(owner_path), 'output': str(output), 'output_sha256': fin['output_sha256'],
        'mapping': mapping, 'prepare': prep,
        'retarget_first_person': {k: audit.get(k) for k in ('algorithm', 'alignmentQuaternion', 'legHeightScale',
                                                              'sourceLegHeight', 'targetLegHeight', 'checks', 'frames',
                                                              'duration', 'proceduralMotionAdded')},
        'retarget_first_person_rest_axis_residual_deg': {
            a['name']: round(a['anatomicalChildDirection']['alignedDifferenceDegrees'], 4)
            for a in audit.get('anatomyAxes', []) if a.get('anatomicalChildDirection')},
        'loop_search': search, 'window_choice': why, 'finalize': fin,
        'verification': report,
        'never': 'no IK, no hand posing, no crossfade, no invented keys; static leaves hold owner rest',
    }
    Path(str(output) + '.report.json').write_text(json.dumps(out, indent=1, sort_keys=True) + '\n')
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('source', type=Path)
    ap.add_argument('output', type=Path)
    ap.add_argument('--preset', default='mixamo', choices=sorted(PRESETS))
    ap.add_argument('--mapping', type=Path, help='JSON {owner joint (no prefix): source node | null}; overrides --preset')
    ap.add_argument('--animation')
    ap.add_argument('--owner', type=Path, default=V.OWNER)
    ap.add_argument('--trim', default='auto', help='auto | none | START:END (frame indices)')
    ap.add_argument('--work', type=Path)
    ap.add_argument('--no-soles', action='store_true')
    ap.add_argument('--keep-root-motion', action='store_true')
    ap.add_argument('--provenance', help='free text recorded in the report (where the source came from)')
    args = ap.parse_args(argv)
    out = retarget(args.source, args.output, args.preset, args.animation, args.owner, args.trim, args.work,
                   not args.no_soles, not args.keep_root_motion, args.provenance,
                   json.loads(args.mapping.read_text()) if args.mapping else None)
    v = out['verification']
    print(json.dumps({'output': out['output'], 'pass': v['pass'], 'failed': v['failed'],
                      'window': out['finalize']['window_source_s'], 'duration_s': out['finalize']['duration_s']}))
    return 0 if v['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
