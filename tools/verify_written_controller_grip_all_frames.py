"""Bounded read-only verification of a written derived clip, never optimisation.

Run on the authorized server with the exact fc34246 helper sources. Explicit
file paths prevent accidental use of another owner/controller. Source metrics
do not prove native mounting, seating, input, or physical button contact.
"""
import argparse
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare_metric_rows(actual, expected, frame, side):
    """Only the inside-zero counter is a non-gate diagnostic discrepancy."""
    discrepancies = []
    for key, value in actual.items():
        if key.endswith('_local_m'):
            continue
        if key == 'hand_vertices_inside':
            assert isinstance(value, int) and not isinstance(value, bool)
            assert isinstance(expected[key], int) and not isinstance(expected[key], bool)
            if value != expected[key]:
                discrepancies.append({'frame': frame, 'side': side, 'field': key,
                                      'actual': value, 'reported': expected[key],
                                      'delta': value-expected[key], 'cause': 'unexplained',
                                      'geometric_gate': False, 'quantization_proven': False})
        elif isinstance(value, dict):
            assert set(value) == set(expected[key])
            assert all(abs(v-expected[key][k]) <= .002 for k, v in value.items()), (frame, side, key)
        elif isinstance(value, (bool, int)):
            assert value == expected[key], (frame, side, key, value, expected[key])
        else:
            assert abs(value-expected[key]) <= .002, (frame, side, key, value, expected[key])
    return discrepancies


def strict_written_frame_gate(metrics, wrists, gates):
    """Direct measured gates, with no added threshold tolerance or count waiver."""
    lo, hi = gates['palm_band_cm']
    for side in ('left', 'right'):
        m, w = metrics[side], wrists[side]
        values = [m['palm_min_gap_cm'], m['hand_min_signed_cm'], m['index_to_trigger_cm'],
                  w['displacement_cm'], w['rotation_deg'], *m['thumb_to_target_cm'].values()]
        if not all(math.isfinite(v) for v in values):
            return False
        if not (lo <= m['palm_min_gap_cm'] <= hi and m['palm_support_patch'] is True
                and m['palm_band_vertices'] >= gates['min_support_vertices']
                and m['hand_min_signed_cm'] >= gates['penetration_limit_cm']
                and m['hand_vertices_penetrating'] == 0
                and min(m['thumb_to_target_cm'].values()) <= gates['thumb_cm']
                and m['index_to_trigger_cm'] <= gates['index_cm']
                and w['displacement_cm'] <= gates['wrist_displacement_cm']
                and w['rotation_deg'] <= gates['wrist_rotation_deg']):
            return False
    return metrics['grip'] is True


def verify(args):
    sys.path.insert(0, str(Path(args.helpers).resolve()))
    import numpy as np
    import derive_controller_grip_clip as D
    import fit_controller_grip as F
    import life_gltf as G
    from export_seat_fit_source import decoded

    started = time.monotonic()
    r = json.loads(Path(args.report).read_text())
    assert r['verified'] is False and r['label'] == 'derived_from_capture'
    assert sha(args.derived) == r['output_glb_sha256']
    assert sha(args.source) == r['source_clip']['sha256']
    assert sha(args.controller) == r['controller']['sha256']
    assert sha(args.owner) == '7609eccbe81631c00d123e69c54241597e28861d1dc947999425cd6c3257adbb'
    clip, source = D.Clip(args.derived), D.Clip(args.source)
    assert clip.index == source.index
    assert len(clip.index) == 65, 'Expected actual owner 65-joint hierarchy; empty/partial parsing refused'
    assert clip.g.parent == source.g.parent
    assert len(clip.times) == len(source.times) == r['frames'] == 152
    assert np.allclose(clip.times, source.times, atol=1e-7, rtol=0)
    assert np.allclose(clip.t, source.t, atol=1e-7, rtol=0)
    assert np.allclose(clip.s, source.s, atol=1e-7, rtol=0)
    decoded_identities = {}
    for label in ('owner', 'controller'):
        original = Path(getattr(args, label))
        expanded = decoded(original, Path(args.cache))
        if expanded != original:
            audit = json.loads(Path(str(expanded)+'.audit.json').read_text())
            assert audit['source_sha256'] == sha(original)
            assert audit['output_sha256'] == sha(expanded)
            assert audit['all_accessor_values_unchanged'] is True
            assert audit['node_skin_animation_mesh_graphs_unchanged'] is True
        decoded_identities[label] = sha(expanded)
    hands = F.Hands.from_owner(Path(args.owner), Path(args.cache))
    mesh, info = F.load_controller(Path(args.controller), Path(args.cache))
    assert info['sha256'] == r['controller']['sha256']
    assert 'controller_contact' in info['excluded_primitives']
    features = F.controller_features(mesh)  # Geometry and distance acceleration reused for all 152 frames.
    W, W0 = clip.worlds(), source.worlds()
    maximum_bone_error = 0.
    measured_bones = 0
    joint_indices = set(clip.index.values())
    for name, i in clip.index.items():
        p = clip.g.parent.get(i)
        if p not in joint_indices:
            assert name == 'Hips', 'Only measured Hips may have an external armature parent'
            continue
        measured_bones += 1
        error = np.abs(np.linalg.norm(W[:, i, :3, 3] - W[:, p, :3, 3], axis=1)
                       - np.linalg.norm(W0[:, i, :3, 3] - W0[:, p, :3, 3], axis=1)).max()*100
        maximum_bone_error = max(maximum_bone_error, float(error))
    assert measured_bones == 64, 'All 64 actual joint-parent bone lengths must be measured'
    assert maximum_bone_error <= 1e-4, maximum_bone_error
    upper = ['Hips', 'Spine', 'Spine1', 'Spine2', 'Neck', 'Head', 'HeadTop_End',
             'LeftShoulder', 'RightShoulder']
    upper_error = float(np.abs(W[:, [clip.index[n] for n in upper]]
                              - W0[:, [source.index[n] for n in upper]]).max())
    assert upper_error <= 2e-6, upper_error
    expected_q, _ = D.apply_finger_deltas(source.q, source, D.finger_axes(source, hands),
                                         D.deltas_from_report(r))
    finger_error = max(G.qangle_deg(tuple(expected_q[f, clip.index[n]]),
                                   tuple(clip.q[f, clip.index[n]]))
                       for n in r['finger_deltas_deg']['per_joint_per_frame'] for f in range(152))
    assert finger_error <= .003, finger_error
    X = np.array(r['fixed_offset']['controller_in_right_hand_gltf'], dtype=float)
    assert X.shape == (4, 4) and np.isfinite(X).all()
    assert np.allclose(X[3], [0, 0, 0, 1], atol=1e-8)
    assert np.allclose(X[:3, :3].T @ X[:3, :3], np.eye(3), atol=1e-6)
    assert abs(np.linalg.det(X[:3, :3])-1) <= 1e-6
    J, J0 = clip.joint_worlds(hands.names, W), source.joint_worlds(hands.names, W0)
    checkpoint = Path(args.output+'.checkpoint.json')
    identity = {k: sha(getattr(args, k)) for k in ('derived', 'source', 'owner', 'controller', 'report')}
    identity['verifier_sha256'] = sha(__file__)
    identity['helper_sha256'] = {Path(m.__file__).name: sha(m.__file__) for m in (D, F, G)}
    identity['helper_sha256']['export_seat_fit_source.py'] = sha(sys.modules['export_seat_fit_source'].__file__)
    rows = []
    if checkpoint.exists():
        saved = json.loads(checkpoint.read_text())
        assert saved['identity'] == identity, 'Checkpoint belongs to different actual files or verifier'
        rows = saved['per_frame']
        assert [v['frame'] for v in rows] == list(range(len(rows))) and len(rows) <= 152
        assert all(v['pass'] == r['per_frame'][v['frame']]['pass'] for v in rows)
    for f in range(152):
        if f < len(rows):
            continue
        if time.monotonic()-started > args.max_seconds:
            raise TimeoutError('Bounded verification expired; incomplete is not acceptance')
        jf = J[f:f+1]
        H = F.rigid(jf[0, hands.names.index('RightHand')])
        C = H @ X
        sets = {k: hands.skin(k, jf) for k in hands.sets}
        metrics = F.Problem(mesh, features, None, sets).metrics(C, 0)
        report_frame = r['per_frame'][f]
        assert report_frame['frame'] == f
        assert abs(report_frame['gltf_t']-clip.times[f]) <= 1e-7
        wrists, discrepancies = {}, []
        for side in ('left', 'right'):
            n = hands.names.index(side.capitalize()+'Hand')
            hand, old = F.rigid(J[f, n]), F.rigid(J0[f, n])
            displacement = float(np.linalg.norm(hand[:3, 3]-old[:3, 3])*100)
            rotation = float(F.angle_deg(hand[:3, :3], old[:3, :3]))
            wrists[side] = {'displacement_cm': displacement, 'rotation_deg': rotation}
            actual, expected = metrics[side], report_frame[side]
            discrepancies.extend(compare_metric_rows(actual, expected, f, side))
            assert abs(displacement-expected['wrist_displacement_cm']) <= .002
            assert abs(rotation-expected['wrist_rotation_deg']) <= .002
        passed = strict_written_frame_gate(metrics, wrists, {
            'palm_band_cm': F.PALM_BAND_CM, 'min_support_vertices': F.MIN_SUPPORT_VERTICES,
            'penetration_limit_cm': F.PENETRATION_LIMIT_CM, 'thumb_cm': F.THUMB_GATE_CM,
            'index_cm': F.INDEX_GATE_CM, 'wrist_displacement_cm': F.IK_BOUND_CM,
            'wrist_rotation_deg': F.IK_BOUND_DEG})
        assert passed == report_frame['pass'], (f, 'report pass differs')
        rows.append({'frame': f, 'pass': passed, 'metrics': metrics, 'wrists': wrists,
                     'source_report_mismatches': discrepancies})
        temporary = checkpoint.with_suffix('.tmp')
        temporary.write_text(json.dumps({'identity': identity, 'per_frame': rows})+'\n')
        os.replace(temporary, checkpoint)
        print(json.dumps({'frame_complete': f, 'pass': passed,
                          'elapsed_seconds': time.monotonic()-started}), flush=True)
    discrepancies = [d for row in rows for d in row['source_report_mismatches']]
    result = {'schema': 'sub01.independent-written-controller-grip-v1',
              'derived_sha256': sha(args.derived), 'source_sha256': sha(args.source),
              'owner_sha256': sha(args.owner), 'controller_sha256': sha(args.controller),
              'verified_decoded_cache_sha256': decoded_identities,
              'frames_checked': len(rows), 'frames_passing': sum(x['pass'] for x in rows),
              'all_frames_pass': all(x['pass'] for x in rows), 'verified': False,
              'sourceReportMismatch': bool(discrepancies), 'source_report_mismatches': discrepancies,
              'native_ready': False, 'seated_verified': False, 'input_verified': False,
              'fixed_offset_basis': 'One supplied report matrix applied unchanged at every written-GLB right-hand socket; no native prop witness',
              'bone_length_max_error_cm': maximum_bone_error, 'upper_body_max_world_change': upper_error,
              'bone_parent_pairs_checked': measured_bones,
              'finger_report_quaternion_max_error_deg': finger_error,
              'elapsed_seconds': time.monotonic()-started, 'per_frame': rows}
    Path(args.output).write_text(json.dumps(result, indent=2)+'\n')
    assert result['all_frames_pass'], 'Measured source gates do not all pass'
    print(json.dumps({k: v for k, v in result.items() if k != 'per_frame'}), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('helpers', 'derived', 'report', 'source', 'owner', 'controller', 'cache', 'output'):
        p.add_argument('--'+name, required=True)
    p.add_argument('--max-seconds', type=int, default=300)
    a = p.parse_args()
    if not 1 <= a.max_seconds <= 300:
        p.error('max-seconds must be bounded to 1..300')
    for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ[key] = '1'
    verify(a)
