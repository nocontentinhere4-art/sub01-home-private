import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import derive_phone_grip_clip as D  # noqa: E402
import phone_rig as PR  # noqa: E402

CLIP = ROOT/'docs/proposed/phone-capture/texting.glb'
CACHE = ROOT/'out/phone-grip/owner-skin.json'
DERIVED = ROOT/'docs/proposed/phone-grip-derived'


def test_quaternion_helpers():
    q = PR.q_axis_angle([1, 0, 0], math.pi/2)
    assert np.allclose(PR.q_to_m(q)@[0, 1, 0], [0, 0, 1])          # flexion about +X curls +Y toward +Z (palm)
    a = PR.q_axis_angle([0, 0, 1], .3)
    assert PR.q_angle_deg(PR.q_mul(a, PR.q_axis_angle([0, 0, 1], .2)), PR.q_axis_angle([0, 0, 1], .5)) == pytest.approx(0, abs=1e-6)


def test_clip_reader_matches_capture_layout():
    doc, binary, sha = PR.read_glb(CLIP)
    assert sha == '8a6dfc041cd4768016c6348dfb90f1275cab4c09cfe6083537fb88ba6d11ae75'
    anim = doc['animations'][0]
    times = PR.accessor(doc, binary, anim['samplers'][0]['input'])[:, 0]
    assert len(times) == 557 and np.allclose(np.diff(times), 1/30, atol=1e-5)


def test_clamp_params_enforces_anatomy():
    p = np.zeros(D.NP)
    p[9:25] = [100, 130, 90, 30]*4
    p[6:9] = [1.0, 0, 0]
    c = D.clamp_params(p)
    th = c[9:25].reshape(4, 4)
    assert (th[:, 0] == 85).all() and (th[:, 1] == 105).all() and (th[:, 2] == 75).all() and (th[:, 3] == 15).all()
    assert math.degrees(np.linalg.norm(c[6:9])) == pytest.approx(D.HAND_CORR_MAX)
    p[9:25] = [-30, -10, -5, -40]*4                                   # no hyperextension / knuckle inversion
    th = D.clamp_params(p)[9:25].reshape(4, 4)
    assert (th[:, 0] == -5).all() and (th[:, 1] == 0).all() and (th[:, 2] == 0).all() and (th[:, 3] == -15).all()


def test_tap_events_come_from_contact_rows_only():
    rows = [{'time': i/30, 'touch': i in (3, 4, 5, 9), 'thumb_pad_uv': [.5, .4], 'thumb_stop_deg': float(i)} for i in range(12)]
    ev = D.tap_events(rows)
    assert [(e['down_time'], e['frames']) for e in ev] == [(3/30, 3), (9/30, 1)]
    assert D.tap_events([dict(r, touch=False) for r in rows]) == []


@pytest.mark.skipif(not CACHE.exists(), reason='private owner skin cache absent (out/ is git-ignored)')
def test_rig_skin_and_glb_round_trip(tmp_path):
    rig = PR.Rig(CACHE, CLIP)
    skin = PR.Skin(CACHE.with_suffix(''))
    d = D.Derivation(rig, skin, view_frames=[120])
    # Subtree FK equals full FK when nothing is edited.
    assert np.abs(d.worlds(120, rig.q[120])-d.Wcap[120]).max() < 1e-12
    q = rig.q.copy()
    i = rig.index('RightHandIndex2')
    q[:, i] = PR.q_mul(q[:, i], PR.q_axis_angle([1, 0, 0], .2))
    out = tmp_path/'derived.glb'
    sha, src = D.write_glb(rig, q, [i], out, {'label': D.LABEL})
    back = PR.Rig(CACHE, out)
    assert np.abs(back.q[:, i]-PR.qnorm(q[:, i])).max() < 1e-6
    others = np.setdiff1d(np.arange(rig.n), [i])
    assert np.abs(back.q[:, others]-rig.q[:, others]).max() < 1e-7 and np.allclose(back.t, rig.t)
    assert PR.read_glb(out)[0]['asset']['extras']['label'] == 'derived_from_capture'


def test_committed_derived_report_never_claims_capture_or_acceptance():
    report = DERIVED/'SUB01_PhoneGrip_derived.report.json'
    if not report.exists():
        pytest.skip('No committed derived candidate')
    r = json.loads(report.read_text())
    assert r['label'] == 'derived_from_capture' and r['verified'] is False and r['visual_accepted'] is False
    assert r['original_capture_invariance'].startswith('NOT APPLICABLE')
    assert not any(r['gates'].values())
    assert r['bone_length_max_error_cm'] < 1e-6 and r['untouched_joints_max_quaternion_component_change'] < 1e-9
    assert r['edits']['finger_cradle_within_anatomical_limits'] is True
    glb = ROOT/r['output']['glb']
    assert PR.read_glb(glb)[2] == r['output']['sha256']
    assert PR.read_glb(glb)[0]['asset']['extras']['label'] == 'derived_from_capture'
    audit = DERIVED/'SUB01_PhoneGrip_derived.audit.json'
    if audit.exists():
        a = json.loads(audit.read_text())
        assert a['verified'] is False and not any(a['native_gates'].values()) and a['clip']['sha256'] == r['output']['sha256']
        assert a['summary']['all_frames']['frames'] == 556


def test_active_set_adds_worst_separated_frames(tmp_path):
    def row(depth):
        g = {'max_depth_cm': depth, 'triangle_overlaps': {'case': 0, 'screen': 0, 'volume': 0, 'power': 0, 'speaker': 0}}
        return {'fingers_palm': g, 'thumb': dict(g, max_depth_cm=0.0), 'body': dict(g, max_depth_cm=0.0), 'forearm': dict(g, max_depth_cm=0.0)}
    depths = [0.0]*20
    depths[5], depths[6], depths[12] = 0.5, 0.45, 0.3
    audit = {'clip': {'sha256': 'x'}, 'frames': [row(d) for d in depths]}
    (tmp_path/'a.json').write_text(json.dumps(audit))
    frames = D.update_active_set(tmp_path/'set.json', tmp_path/'a.json', k=8)
    assert frames == [5, 12]                               # 6 is too close to 5; within-compression frames ignored
    assert D.update_active_set(tmp_path/'set.json') == [5, 12]
