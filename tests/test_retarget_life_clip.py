"""tools/retarget_life_clip.py: the existing retarget_first_person.mjs driven onto the owner skeleton,
with measured residuals. Needs Node (the .mjs and the vendored meshopt decoder); skipped without it."""
import json
import math
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import life_clip_synth as S  # noqa: E402
import life_gltf as G  # noqa: E402
import retarget_life_clip as R  # noqa: E402
import verify_life_idle_candidate as V  # noqa: E402

pytestmark = pytest.mark.skipif(not shutil.which('node'), reason='node is required for retarget_first_person.mjs')
OWNER = ROOT / 'web/room/char_mixamo.glb'


def local_rotations(path):
    g = G.Gltf(path)
    clip = g.animation()
    times = clip.key_times()
    out = {}
    for i, n in enumerate(g.nodes):
        if n.get('name', '').startswith(S.P):
            out[V.canonical(n['name'])] = [clip.sample(i, 'rotation', t, g.rest(i)[1]) for t in times]
    return out, times


def max_quat_diff(a, b):
    return max(min(max(abs(x - y) for x, y in zip(p, q)), max(abs(x + y) for x, y in zip(p, q))) for p, q in zip(a, b))


def test_owner_clip_onto_owner_is_identity(tmp_path):
    owner = S.build(tmp_path / 'owner.glb')
    src = S.build(tmp_path / 'idle.glb', S.idle_clip())
    out = tmp_path / 'out.glb'
    rep = R.retarget(src, out, 'mixamo', owner_path=owner, trim='none', in_place=False, work=tmp_path / 'w')
    a, ta = local_rotations(src)
    b, tb = local_rotations(out)
    assert len(ta) == len(tb)
    assert max(max_quat_diff(a[n], b[n]) for n in a) < 1e-4
    assert rep['prepare']['rest_rebase_correction_deg'] == {}
    assert rep['verification']['pass'], rep['verification']['failed']


def other_rig(path, seconds=2.0, fps=30):
    """Different bone lengths, A-pose arms, arbitrary local rest frames, facing +x, an extra unmapped
    pelvis node; metres, names 'o_<joint>'. Returns the mapping and the rig-to-world root rotation."""
    spec = S.skeleton_spec()
    factor = {n: 0.8 + 0.4 * ((k * 37) % 11) / 10 for k, (n, _, _) in enumerate(spec)}
    pos, branch = {}, {}
    for name, parent, t in spec:
        if parent is None:
            pos[name] = tuple(c * 0.01 * 0.95 for c in t)
            branch[name] = G.IDENTITY
            continue
        b = branch[parent]
        if name in ('LeftArm', 'RightArm'):
            b = G.qaxis((0, 0, 1), math.radians(-45 if name.startswith('Left') else 45))
        branch[name] = b
        pos[name] = G.vadd(pos[parent], G.qrot(b, tuple(c * 0.01 * factor[name] for c in t)))
    world_q = {n: G.qnorm(G.qaxis(((k % 3) - 1, 1, (k % 5) - 2), 0.3 + 0.17 * k)) for k, (n, _, _) in enumerate(spec)}
    parent_of = {n: p for n, p, _ in spec}
    pelvis_q = G.qaxis((1, 0, 0), 0.4)
    nodes = [{'name': 'Rig', 'rotation': list(G.qaxis((0, 1, 0), math.pi / 2)), 'children': []}]
    index = {}
    for name, _, _ in spec:
        index[name] = len(nodes)
        nodes.append({'name': 'o_' + name})
    nodes.append({'name': 'o_Pelvis', 'children': []})
    pelvis = len(nodes) - 1
    rest_local = {}
    for name, parent, _ in spec:
        if parent is None:
            pq, pp = G.IDENTITY, (0.0, 0.0, 0.0)
            nodes[0]['children'].append(index[name])
        elif name.endswith('UpLeg'):
            pq, pp = G.qmul(world_q['Hips'], pelvis_q), pos['Hips']
            nodes[pelvis]['children'].append(index[name])
        else:
            pq, pp = world_q[parent], pos[parent]
            nodes[index[parent]].setdefault('children', []).append(index[name])
        q = G.qnorm(G.qmul(G.qinv(pq), world_q[name]))
        t = G.qrot(G.qinv(pq), G.vsub(pos[name], pp))
        nodes[index[name]].update({'translation': list(t), 'rotation': list(q)})
        rest_local[name] = q
    nodes[pelvis].update({'translation': [0.0, 0.0, 0.0], 'rotation': list(pelvis_q)})
    nodes[index['Hips']].setdefault('children', []).append(pelvis)
    n = int(round(seconds * fps)) + 1
    times = [k / fps for k in range(n)]
    bw = G.BinWriter()
    ti = bw.add(times, 'SCALAR', minmax=True)
    anim = {'name': 'Idle', 'samplers': [], 'channels': []}
    for k, joint in enumerate(('Spine', 'Spine2', 'Neck', 'LeftArm', 'RightArm', 'LeftForeArm', 'LeftHand',
                                'LeftHandIndex2', 'RightUpLeg', 'LeftLeg')):
        axis = ((k % 3) - 1 + 0.3, 1.0, 0.5 - (k % 2))
        vals = [G.qmul(rest_local[joint], G.qaxis(axis, math.radians(8) * math.sin(2 * math.pi * t / seconds)))
                for t in times]
        vi = bw.add(vals, 'VEC4')
        anim['samplers'].append({'input': ti, 'output': vi, 'interpolation': 'LINEAR'})
        anim['channels'].append({'sampler': len(anim['samplers']) - 1, 'target': {'node': index[joint], 'path': 'rotation'}})
    hips_t = nodes[index['Hips']]['translation']
    vi = bw.add([(hips_t[0] + 0.01 * math.sin(2 * math.pi * t / seconds), hips_t[1], hips_t[2]) for t in times], 'VEC3')
    anim['samplers'].append({'input': ti, 'output': vi, 'interpolation': 'LINEAR'})
    anim['channels'].append({'sampler': len(anim['samplers']) - 1, 'target': {'node': index['Hips'], 'path': 'translation'}})
    doc = {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': [0]}], 'nodes': nodes, 'animations': [anim],
           'accessors': bw.accessors, 'bufferViews': bw.views, 'buffers': [{'byteLength': len(bw.data) + (-len(bw.data)) % 4}]}
    G.write_glb(path, doc, bytes(bw.data))
    return {name: 'o_' + name for name, _, _ in spec}


def test_other_rig_keeps_owner_lengths_and_reproduces_world_directions(tmp_path):
    owner = S.build(tmp_path / 'owner.glb')
    src = tmp_path / 'other.glb'
    mapping = other_rig(src)
    out = tmp_path / 'out.glb'
    rep = R.retarget(src, out, 'mixamo', owner_path=owner, trim='none', work=tmp_path / 'w', mapping=mapping)
    assert rep['prepare']['prepared_vs_original_max_joint_cm'] < 1e-4          # preparation never moves the source
    assert max(rep['prepare']['rest_rebase_correction_deg'].values()) > 30     # A-pose and odd frames really re-based
    lengths = rep['verification']['invariants']['bone_length_constancy']
    assert lengths['pass'] and lengths['max_dev_from_owner_lengths_cm'] < 1e-4
    C = tuple(rep['retarget_first_person']['alignmentQuaternion'])
    sg, og = G.Gltf(src), G.Gltf(out)
    sc, oc = sg.animation(), og.animation()
    worst = 0.0
    for t in sc.key_times():
        ws, wo = G.world_pose(sg, sc, t), G.world_pose(og, oc, t)
        for joint, child in R.PRIMARY_CHILD.items():
            if joint in R.BASIS_JOINTS:
                continue
            ds = G.vunit(G.qrot(C, G.vsub(ws[sg.by_name[mapping[child]]][0], ws[sg.by_name[mapping[joint]]][0])))
            do = G.vunit(G.vsub(wo[og.by_name[S.P + child]][0], wo[og.by_name[S.P + joint]][0]))
            worst = max(worst, math.degrees(math.acos(max(-1.0, min(1.0, G.vdot(ds, do))))))
    assert worst < 0.01


def test_residual_report_flags_slide_and_non_loop(tmp_path):
    owner = S.build(tmp_path / 'owner.glb')
    src = S.build(tmp_path / 'bad.glb', S.idle_clip(ramp=True, slide_cm=4.0))
    out = tmp_path / 'out.glb'
    rep = R.retarget(src, out, 'mixamo', owner_path=owner, trim='auto', work=tmp_path / 'w')
    failed = set(rep['verification']['failed'])
    assert {'loop', 'feet_joints', 'soles'} <= failed
    assert rep['loop_search']['longest_window_passing_loop_feet_and_hips'] is None
    assert rep['window_choice'].startswith('no window passes')
    on_disk = json.loads(Path(str(out) + '.report.json').read_text())
    assert on_disk['verification']['failed'] == rep['verification']['failed']


def test_auto_trim_picks_a_measured_loop_window(tmp_path):
    owner = S.build(tmp_path / 'owner.glb')
    clip = S.idle_clip(seconds=2.0)
    # Append one extra second of a different motion: the whole clip no longer loops, its first 2 s do.
    extra = S.idle_clip(seconds=3.0, ramp=True)
    clip = {'times': extra['times'], 'trans': {'Hips': extra['trans']['Hips']},
            'rot': {j: v + extra['rot'][j][len(v):] for j, v in clip['rot'].items()}}
    src = S.build(tmp_path / 'long.glb', clip)
    out = tmp_path / 'out.glb'
    rep = R.retarget(src, out, 'mixamo', owner_path=owner, trim='auto', work=tmp_path / 'w')
    win = rep['loop_search']['longest_window_passing_loop_feet_and_hips']
    assert win and win['start_frame'] == 0 and win['end_frame'] == 60
    assert rep['finalize']['frames'] == 61 and rep['verification']['pass']


def test_real_mixamo_capture_onto_real_owner_is_identity(tmp_path):
    src = ROOT / 'web/room/mh_mx/room_mx_standing_clap.glb'
    if not (src.is_file() and OWNER.is_file()):
        pytest.skip('repository clips absent')
    out = tmp_path / 'clap.glb'
    rep = R.retarget(src, out, 'mixamo', owner_path=OWNER, trim='none', in_place=False, soles=False, work=tmp_path / 'w')
    a, _ = local_rotations(src)
    b, _ = local_rotations(out)
    assert max(max_quat_diff(a[n], b[n]) for n in a) < 1e-4
    assert rep['verification']['invariants']['rest_offsets']['max_deviation_cm'] == 0


def test_real_best_repository_source_reports_residuals(tmp_path):
    src = ROOT / 'web/room/boy_moves.glb'
    if not (src.is_file() and OWNER.is_file()):
        pytest.skip('repository clips absent')
    out = tmp_path / 'stand_idle.glb'
    rep = R.retarget(src, out, 'ual_boy', animation='stand_idle', owner_path=OWNER, work=tmp_path / 'w')
    inv = rep['verification']['invariants']
    for key in ('skeleton', 'rest_offsets', 'bone_length_constancy', 'root_in_place', 'loop', 'feet_joints', 'soles',
                'standing', 'symmetry', 'timing'):
        assert key in inv and 'pass' in inv[key]
    assert inv['skeleton']['pass'] and inv['rest_offsets']['max_deviation_cm'] == 0
    assert inv['bone_length_constancy']['max_dev_from_owner_lengths_cm'] < 1e-3
    assert inv['soles']['selected_vertices'] == 4177
    assert rep['retarget_first_person']['checks']['sampledBoneLengthMaxError'] < 1e-9
    assert Path(str(out) + '.report.json').is_file()
