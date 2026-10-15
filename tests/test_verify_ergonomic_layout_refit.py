"""Synthetic cases for the independent ergonomic layout refit verifier (no repo geometry needed except where noted)."""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import verify_ergonomic_layout_refit as V  # noqa: E402


def test_box_sdf_outside_inside_and_min():
    lo, hi = np.zeros(3), np.ones(3)
    assert V.box_sdf([2., .5, .5], lo, hi) == pytest.approx(1.)
    assert V.box_sdf([.5, .5, .5], lo, hi) == pytest.approx(-.5)
    assert V.box_sdf([2., 2., .5], lo, hi) == pytest.approx(math.sqrt(2))
    boxes = np.array([[lo, hi], [lo + 5, hi + 5]])
    d, w = V.min_box_sdf(np.array([[5.5, 5.5, 7.]]), boxes)
    assert d[0] == pytest.approx(1.) and w[0] == 1
    d, w = V.min_box_sdf(np.array([[50., 50., 50.]]), boxes, reach=3.)
    assert d[0] == 3. and w[0] == -1          # beyond reach: capped, never a false small value


def test_closest_on_triangles_regions():
    a, b, c = np.array([[0., 0, 0]]), np.array([[1., 0, 0]]), np.array([[0., 1, 0]])
    for p, want in (([.2, .2, 1.], 1.), ([-1., -1, 0], math.sqrt(2)), ([2., 0, 0], 1.), ([.5, -1, 0], 1.),
                    ([1., 1, 0], math.sqrt(2) / 2)):
        assert V.closest_on_triangles(np.array([p]), a, b, c)[0] == pytest.approx(want)


def test_point_in_triangles_and_rect_gap():
    tris = np.array([[[0, 0, 0], [10, 0, 0], [0, 10, 0]], [[10, 0, 0], [10, 10, 0], [0, 10, 0]]], float)
    inside = V.point_in_triangles_2d(np.array([[5., 5.], [9.9, 9.9], [10.1, 5.], [-0.1, 0.]]), tris)
    assert inside.tolist() == [True, True, False, False]
    assert V.rect_gap([[0, 0], [1, 1]], [[3, 0], [4, 1]]) == pytest.approx(2.)
    assert V.rect_gap([[0, 0], [2, 2]], [[1, 1], [3, 3]]) == pytest.approx(-1.)


def test_arith_and_placement_constants():
    text = ("SCALE=(.845-.025)/.755\nDESK_Y=-3.02\n"
            "    doc['nodes'].append({'name':'X','children':children,'translation':[2.1,.025,DESK_Y],'scale':[SCALE]*3})\n"
            "    device_bounds={'monitor':[[1.64,-3.345],[2.36,-3.255]],'phone':[[2.661,-2.995001],[2.739001,-2.845]]}\n")
    c = V.placement_constants(text)
    assert c['scale'] == pytest.approx(.82 / .755)
    assert c['translation_m'] == pytest.approx([2.1, .025, -3.02])
    assert c['device_bounds_m']['monitor'] == [[1.64, -3.345], [2.36, -3.255]]
    with pytest.raises(ValueError):
        V.arith('__import__("os")')


def _desk(top=84.5):
    """A synthetic flat 100 x 60 cm worktop at x 100..200, y -330..-270, top `top`, with a 6 cm hole at x 150..156."""
    q = lambda x0, x1, y0, y1: [[[x0, y0, top], [x1, y0, top], [x1, y1, top]], [[x0, y0, top], [x1, y1, top], [x0, y1, top]]]
    flat = np.array(q(100, 150, -330, -270) + q(156, 200, -330, -270) + q(150, 156, -330, -310) + q(150, 156, -304, -270), float)
    wt = {'min': np.array([100., -330, top - 3]), 'max': np.array([200., -270, top]), 'node': 44, 'name': 'top'}
    return {'top_cm': top, 'flat_top_tris': flat, 'worktop': wt}


def _dev(x0, x1, y0, y1, bottom, top=None, name='keyboard'):
    feet = np.array([[x, y, bottom] for x in (x0, x1) for y in (y0, y1)], float)
    return {'name': name, 'feet': feet, 'footprint_cm': [np.array([x0, y0]), np.array([x1, y1])], 'bottom_cm': bottom,
            'top_cm': top if top is not None else bottom + 3.}


def test_device_support_pass_float_hole_edge_and_item():
    desk = _desk()
    stand = {'monitor_stand': {'min_cm': np.array([160., -328, 84.5]), 'max_cm': np.array([172., -319, 96.5]),
                               'on_slab': True, 'provenance': 'synthetic'},
             'monitor_frame': {'min_cm': np.array([130., -326, 96.5]), 'max_cm': np.array([200., -322, 140.5]),
                               'on_slab': False, 'provenance': 'synthetic'}}
    ok = V.device_support(_dev(110, 140, -300, -285, 84.5), desk, stand)
    assert ok['pass'], ok
    assert not V.device_support(_dev(110, 140, -300, -285, 84.6), desk, stand)['pass']       # floats 0.1 cm
    assert not V.device_support(_dev(110, 140, -300, -285, 84.4), desk, stand)['pass']       # sunk in the top
    assert not V.device_support(_dev(140, 170, -309, -300, 84.5), desk, stand)['pass']       # over the grommet hole
    assert not V.device_support(_dev(170, 199.5, -300, -285, 84.5), desk, stand)['pass']     # inside the edge margin
    hit = V.device_support(_dev(150, 170, -318.5, -300, 84.5), desk, stand)
    assert hit['items']['monitor_stand']['collides'] and not hit['pass']                       # too close to the stand
    # the monitor frame floats above: footprint overlap without vertical overlap is not a collision
    assert not V.device_support(_dev(110, 140, -300, -285, 84.5), desk, stand)['items']['monitor_frame']['collides']


def test_chair_rule_paths_reversible():
    roll = np.array([3.875, -30., 0.])
    a, _ = V.chair_path_for_clip('SitToType_seated', 31, roll)
    b, _ = V.chair_path_for_clip('TypeToSit_seated', 31, roll)
    d, _ = V.chair_path_for_clip('DeskTyping_seated', 5, roll)
    s, _ = V.chair_path_for_clip('SeatedIdle', 5, roll)
    assert np.array_equal(a[0], np.zeros(3)) and np.allclose(a[-1], roll)
    assert np.array_equal(b[-1], np.zeros(3)) and np.allclose(b[0], roll)
    assert np.abs(a - b[::-1]).max() < 1e-12
    assert np.allclose(d, roll[None]) and not s.any()
    v = np.gradient(a[:, 1])
    assert abs(v[0]) < 2e-2 and abs(v[-1]) < 2e-2            # quintic: starts and ends at rest


def test_chair_path_check_synthetic_desk():
    tri = np.array([[[0., 0, 2.5], [10, 0, 2.5], [0, 10, 2.5]], [[0., 0, 2.5], [0, 10, 2.5], [0, 0, 60]]])
    chair = {'tris': tri + [0, 50, 0], 'material': np.array(['chair_base', 'chair_plastic'])}
    leg = {'node': 40, 'name': 'leg', 'kind': 'leg', 'min': np.array([-5., 20, 2.5]), 'max': np.array([5., 25, 80])}
    desk = {'parts': [leg], 'bounds': [leg['min'], leg['max']]}
    clear = V.chair_path_check(chair, desk, (0., -20.), samples=11)
    assert clear['desk_clear'] and clear['floor_ok'] and clear['worst_desk']['desk_min_cm'] == pytest.approx(5., abs=1e-6)
    hit = V.chair_path_check(chair, desk, (0., -30.), samples=11)
    assert not hit['desk_clear'] and hit['worst_desk']['desk_min_cm'] < 0
    sunk = dict(chair, tris=chair['tris'] - [0, 0, .5])
    assert not V.chair_path_check(sunk, desk, (0., 0.), samples=3)['floor_ok']


def _rot(axis, deg):
    a = np.radians(deg)
    axis = np.asarray(axis, float) / np.linalg.norm(axis)
    K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + math.sin(a) * K + (1 - math.cos(a)) * K @ K


def test_wrist_angles_decompose_flexion_and_deviation():
    # bind: forearm and hand frames identity; hand long axis +x, palm normal -z, radial +y
    I = np.eye(3)
    a_long, a_palm, a_rad = np.array([1., 0, 0]), np.array([0., 0, -1]), np.array([0., 1, 0])
    # a pure flexion of 30 deg: the long axis turns toward the palm (-z): rotation about +y by +30 deg
    Rh = _rot([0, 1, 0], 30.)
    f, d = V.wrist_angles(I[None], Rh[None], I, I, a_long, a_palm, a_rad)
    assert f[0] == pytest.approx(30., abs=1e-9) and d[0] == pytest.approx(0., abs=1e-9)
    # radial deviation 12 deg: about +z toward +y
    f, d = V.wrist_angles(I[None], _rot([0, 0, 1], 12.)[None], I, I, a_long, a_palm, a_rad)
    assert d[0] == pytest.approx(12., abs=1e-9) and f[0] == pytest.approx(0., abs=1e-9)
    # a forearm rotation carried rigidly by the hand changes nothing (relative measure)
    Rf = _rot([1, 2, 3], 40.)
    f, d = V.wrist_angles(Rf[None], (Rf @ Rh)[None], I, I, a_long, a_palm, a_rad)
    assert f[0] == pytest.approx(30., abs=1e-9) and d[0] == pytest.approx(0., abs=1e-9)
    # pronation/supination about the long axis is neither flexion nor deviation
    f, d = V.wrist_angles(I[None], _rot([1, 0, 0], 50.)[None], I, I, a_long, a_palm, a_rad)
    assert abs(f[0]) < 1e-9 and abs(d[0]) < 1e-9


def test_accel_and_seam_detection_on_synthetic_tracks():
    dt = 1 / 60
    t = np.arange(61) * dt
    x = np.stack([10 * np.sin(t), np.zeros_like(t), np.zeros_like(t)], -1)
    a = V.accel(x, dt)
    assert a.max() == pytest.approx(10 * np.sin(1.), rel=.02)
    # a 1 cm jump is a large acceleration compared with the smooth peak
    y = x.copy()
    y[30:, 0] += 1.
    assert V.accel(y, dt).max() > 100 * a.max()


def test_device_delta_from_proposal_entries():
    orig = {'three_m': [2.0, .846, -2.94], 'width_m': .371}
    d, how = V.device_delta(orig, {'three_m': [2.0, .845, -2.84], 'width_m': .371}, 'keyboard')
    assert d == pytest.approx([0., 10., -.1]) and 'three_m' in how
    d, _ = V.device_delta(orig, {'delta_ue_cm': [0, 7, 0]}, 'keyboard')
    assert d.tolist() == [0, 7, 0]
    with pytest.raises(ValueError):
        V.device_delta(orig, {'three_m': [2, .846, -2.9], 'width_m': .4}, 'keyboard')
    d, how = V.device_delta(orig, None, 'mouse')
    assert not d.any() and 'unchanged' in how


def test_layout_from_proposal_skeleton(tmp_path):
    doc = {'schema': 'sub01.ergonomic-layout-refit.v1', 'status': 'in_progress',
           'original': {'keyboard': {'three_m': [2.0, .846, -2.94], 'width_m': .371},
                        'mouse': {'three_m': [2.4, .846, -2.91], 'width_m': .22},
                        'chair_initial_translation_cm': [200.02, -186.69, 63.19], 'chair_roll_cm': [3.875, -21.279, 0.]},
           'proposed': {'keyboard': {'three_m': [2.0, .845, -2.86], 'width_m': .371}, 'chair_roll_cm': [3.875, -30., 0.],
                        'clips': {'DeskTyping_seated': {'glb': 'x.glb', 'sha256': 'ab'}}}}
    p = tmp_path / 'p.json'
    p.write_text(json.dumps(doc))
    L = V.layout_from_proposal(p)
    assert L['keyboard_delta_cm'] == pytest.approx([0., 8., -.1])
    assert L['chair_roll_cm'].tolist() == [3.875, -30., 0.]
    assert L['clips']['DeskTyping_seated']['source'] == 'proposal'
    assert L['clips']['SeatedIdle']['source'].startswith('BASELINE')
    assert L['r0'].tolist() == list(V.R0_DEFAULT)


def test_main_rule_frames_uses_main_validator_shape():
    """main's validate() decides; a frame with every patch in band passes, a hovering buttock patch fails."""
    try:
        Vm = V.main_validator()
    except Exception as e:      # needs origin/main in the local clone
        pytest.skip(f'origin/main unavailable: {e}')
    good = {n: {'facing': np.array([40]), 'over': np.array([40]), 'band': np.array([40]),
                'lowest': np.array([-.5 if 'sole' not in n else .1]), 'median': np.array([0. if 'sole' not in n else .3])}
            for n in Vm.REGIONS}
    assert V.main_rule_frames(Vm, good, [0]) == {}
    bad = {n: dict(m) for n, m in good.items()}
    bad['buttocks'] = dict(good['buttocks'], lowest=np.array([1.5]), median=np.array([2.]), band=np.array([0]))
    assert 0 in V.main_rule_frames(Vm, bad, [0])


def test_real_desk_geometry_from_main_bytes():
    """The LINEA mapping parsed from main reproduces root's numbers: top 84.5, floor 2.5, worktop centre (210, -302)."""
    try:
        desk = V.desk_geometry()
    except Exception as e:
        pytest.skip(f'origin/main unavailable: {e}')
    assert desk['top_cm'] == pytest.approx(84.5, abs=1e-4)
    assert desk['floor_cm'] == pytest.approx(2.5, abs=1e-4)
    wt = desk['worktop']
    assert ((wt['min'][:2] + wt['max'][:2]) / 2) == pytest.approx([210., -302.], abs=1e-3)
    assert len(desk['flat_top_tris']) > 0
    items, meta = V.desk_items(desk)
    assert meta['lift_cm'] == pytest.approx(2.5, abs=1e-3)
    assert items['monitor_stand']['min_cm'][2] == pytest.approx(84.5, abs=1e-3)
    assert items['monitor_frame']['screen_centre_check']['z_matches']
    kb = V.device_geometry('keyboard')
    assert kb['footprint_cm'][0] == pytest.approx([181.45, -302.046], abs=2e-3)
    assert kb['bottom_cm'] == pytest.approx(84.6, abs=1e-4)          # home.js: 0.1 cm above the 84.5 top


def test_wrist_angles_joint_line():
    elbow, wrist = np.array([[0., 0, 0]]), np.array([[25., 0, 0]])
    palm, radial = np.array([[0., 0, -1]]), np.array([[0., 1, 0]])
    a = np.radians(30.)
    mid = wrist + 8 * np.array([[math.cos(a), 0, -math.sin(a)]])            # bent 30 deg toward the palm
    f, d = V.wrist_angles_anatomical(elbow, wrist, mid, palm, radial)
    assert f[0] == pytest.approx(30., abs=1e-6) and d[0] == pytest.approx(0., abs=1e-6)
    mid = wrist + 8 * np.array([[math.cos(a), -math.sin(a), 0]])            # ulnar deviation 30 deg
    f, d = V.wrist_angles_anatomical(elbow, wrist, mid, palm, radial)
    assert d[0] == pytest.approx(-30., abs=1e-6) and f[0] == pytest.approx(0., abs=1e-6)
