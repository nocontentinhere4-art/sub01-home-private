"""Source-mesh support surfaces (bed, sofa) and the native sofa audit's pure rule: synthetic meshes + the real GLBs."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import measure_source_support_surface as M  # noqa: E402
import unreal_bed_surface_audit as B  # noqa: E402
import unreal_sofa_surface_audit as S  # noqa: E402
import unreal_controller_play_runtime as C  # noqa: E402

REPORTS = ROOT / 'docs/proposed/source-support-surfaces'


def quad(x0, y0, x1, y1, z, base=0, up=True):
    v = [[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]]
    f = [base, base + 1, base + 2, base, base + 2, base + 3]
    if not up:
        f = [base, base + 2, base + 1, base, base + 3, base + 2]
    return v, f


def box_top_and_bottom(x0, y0, x1, y1, z_top, z_bottom, base):
    """A cushion slab: its top (upward) and its underside (downward), so it covers whatever lies below it."""
    vt, ft = quad(x0, y0, x1, y1, z_top, base)
    vb, fb = quad(x0, y0, x1, y1, z_bottom, base + 4, up=False)
    return vt + vb, ft + fb


# ------------------------------------------------------------------ frames
def test_gltf_to_ue_is_x_z_y_times_100_and_rewinding_keeps_the_outward_normal():
    assert M.gltf_to_ue_cm([[1.0, 2.0, 3.0]]).tolist() == [[100.0, 300.0, 200.0]]
    # an upward (+Y glTF) counter-clockwise triangle
    tri = np.array([[0, 0, 0], [1, 0, 0], [0, 0, -1]], float)
    n_gltf = np.cross(tri[1] - tri[0], tri[2] - tri[0])
    assert n_gltf[1] > 0
    ue = M.gltf_to_ue_cm(tri)
    swapped = np.cross(ue[1] - ue[0], ue[2] - ue[0])
    assert swapped[2] < 0                     # the axis swap is a reflection: raw winding now points down
    f = M.rewind([[0, 1, 2]])[0]
    fixed = np.cross(ue[f[1]] - ue[f[0]], ue[f[2]] - ue[f[0]])
    assert fixed[2] > 0


def test_three_js_yaw_and_position_placement():
    p = M.place_web([[1.0, 0.5, 0.0]], (-1.8, 0.0, 0.1), -np.pi / 2)
    # three.js rotation.y = -90 deg turns +x into +z
    assert p[0] == pytest.approx([-1.8, 0.5, 0.1 + 1.0])


# ------------------------------------------------------------------ sofa rule (shared native/source)
def sofa_like():
    """Seat deck (covered by two cushions), two cushions, an arm top and a back top: real geometry, no box stand-in."""
    v, f = [], []
    for part in (quad(-100, -40, 100, 40, 36, 0),                                 # deck
                 ):
        v += part[0]
        f += part[1]
    for x0, x1 in ((-90, -2), (2, 90)):                                          # two loose seat cushions 88 x 70
        pv, pf = box_top_and_bottom(x0, -30, x1, 40, 50, 38, len(v))
        v += pv
        f += pf
    for x0, x1 in ((-112, -94), (94, 112)):                                       # arm tops 18 x 88
        pv, pf = quad(x0, -44, x1, 44, 70, len(v))
        v += pv
        f += pf
    return v, f


def test_seat_surface_keeps_exposed_broad_cushions_and_rejects_deck_and_arms():
    v, f = sofa_like()
    s = S.seat_surface(v, f)
    assert len(s['cushions']) == 2
    assert all(c['exposed_projected_area_cm2'] == pytest.approx(88 * 70) for c in s['cushions'])
    assert s['top_z_cm'] == [50, 50]
    deck = [p for p in s['patches'] if p['top_z_cm'] == 36][0]
    assert deck['projected_area_cm2'] == pytest.approx(200 * 80)
    assert deck['exposed_projected_area_cm2'] < S.DEFAULT_CONFIG['min_cushion_area_cm2']    # covered by the cushions
    arms = [p for p in s['patches'] if p['top_z_cm'] == 70]
    assert len(arms) == 2 and all(p['exposed_projected_area_cm2'] == pytest.approx(18 * 88) for p in arms)
    # the consumer's own reader accepts the shape and recomputes >= 4000 cm2
    report = {'errors': [], 'sofa': {'sections': [{'vertices_world_cm': v, 'seat_surface': {'triangle_indices': s['triangle_indices']}}]}}
    tris, area = C.sofa_seat_triangles(report)
    assert area == pytest.approx(s['area_cm2']) and area >= C.MIN_SEAT_AREA_CM2


def test_upward_clustering_is_by_shared_edges_not_shared_corners():
    a, fa = quad(0, 0, 10, 10, 50, 0)
    b, fb = quad(10, 10, 20, 20, 50, 4)                 # touches the first one at a corner only
    c, fc = quad(-10, 0, 0, 10, 50, 8)                  # shares an edge with the first
    rows, patches = S.upward_patches(a + b + c, fa + fb + fc)
    assert sorted(len(p) for p in patches) == [2, 4]


def test_vertex_normals_decide_upward_for_clockwise_imported_faces():
    v, f = quad(0, 0, 80, 80, 50, 0, up=False)          # clockwise as UE imports it
    with pytest.raises(S.SurfaceRefused):
        S.seat_surface(v, f)                             # cross product says downward
    s = S.seat_surface(v, f, [[0, 0, 1]] * 4)
    assert s['projected_area_cm2'] == pytest.approx(6400)
    with pytest.raises(S.SurfaceRefused):
        S.seat_surface(v, f, [[0, 0, -1]] * 4)


def test_area_threshold_refuses_an_arm_and_records_what_was_measured():
    v, f = quad(0, 0, 18, 88, 70, 0)
    with pytest.raises(S.SurfaceRefused) as error:
        S.seat_surface(v, f)
    assert error.value.measured_surface['patches'][0]['projected_area_cm2'] == pytest.approx(18 * 88)
    with pytest.raises(ValueError):
        S.seat_surface([[np.nan, 0, 0]] * 3, [0, 1, 2])
    with pytest.raises(ValueError):
        S.seat_surface(v, [0, 1])


def test_component_identity_needs_one_upholstery_component_and_optionally_the_tag():
    one = [{'tags': [], 'seat_sections': 1, 'component': 'linen'}, {'tags': [], 'seat_sections': 0, 'component': 'legs'}]
    chosen, basis = S.choose_component(one)
    assert chosen['component'] == 'linen' and basis.startswith('seat material')
    with pytest.raises(ValueError, match='ONE'):
        S.choose_component([{'tags': [], 'seat_sections': 1}, {'tags': [], 'seat_sections': 2}])
    with pytest.raises(ValueError, match='ONE'):
        S.choose_component([])
    tagged = [{'tags': ['SUB01Device:Sofa'], 'seat_sections': 1, 'component': 'tagged'}, {'tags': [], 'seat_sections': 1}]
    assert S.choose_component(tagged)[0]['component'] == 'tagged'
    with pytest.raises(ValueError, match='tagged SUB01Device:Sofa'):
        S.choose_component(one, {**S.DEFAULT_CONFIG, 'require_tag': True})
    assert S.material_identity(['Material_Haven_linen'], S.DEFAULT_CONFIG['seat_material_regex'])
    assert not S.material_identity(['Material_Haven_seams', 'Haven_legs'], S.DEFAULT_CONFIG['seat_material_regex'])


# ------------------------------------------------------------------ bed rule (native audit) with imported normals
def test_bed_mattress_top_uses_imported_normals_when_given():
    v, f = quad(0, 0, 150, 200, 60, 0, up=False)        # clockwise (UE import)
    with pytest.raises(ValueError):
        B.mattress_top(v, f)
    top = B.mattress_top(v, f, normals=[[0, 0, 1]] * 4)
    assert top['area_cm2'] == pytest.approx(30000)
    small, fs = quad(0, 0, 60, 40, 70, 0)
    with pytest.raises(ValueError, match='not a bed'):
        B.mattress_top(small, fs)                        # a pillow is not a mattress (MIN_MATTRESS_AREA_CM2)
    with pytest.raises(ValueError, match='normals'):
        B.mattress_top(v, f, normals=[[0, 0, 1]])


# ------------------------------------------------------------------ the real source GLBs
def test_real_bed_source_measurement():
    r = M.measure_bed()
    assert r['label'] == 'source_measured' and r['native_verified'] is False and r['errors'] == []
    assert r['source']['glb_sha256'] == '57cc312cca389e9ac113be44c77f1c445e92eee056ef092460fe20a78d5ba07c'
    m = r['mattress']
    assert m['material'] == 'Original cream upholstery'
    assert m['area_cm2'] == pytest.approx(30004.07, abs=0.01) and m['area_cm2'] >= M.MIN_MATTRESS_AREA_CM2
    assert m['top_z_cm'][1] == pytest.approx(360.0, abs=1e-3)              # 0.60 m local + 3 m authored floor
    assert m['head_end_direction_xy'] == [0.0, -1.0]                        # pillows at glTF -Z -> UE -Y
    assert all(g['normal_agreement'] == 1.0 for g in r['groups'])


def test_real_sofa_source_measurement():
    r = M.measure_sofa()
    assert r['errors'] == [] and r['native_verified'] is False
    assert r['source']['glb_sha256'] == '92b7db30f9fbf169f49e75547d0d2964ce21bf410a733b963761dc0eaed2398d'
    s = r['seat']
    assert len(s['cushions']) == 2
    for c in s['cushions']:
        assert c['projected_area_cm2'] == pytest.approx(5806.41, abs=0.01)    # the doc's ~5,808 cm2 per cushion
        assert c['top_z_cm'] == pytest.approx(50.3, abs=1e-3)
        assert c['exposed_projected_area_cm2'] < c['projected_area_cm2']      # the back cushions overhang the rear
    assert s['meets_controller_min_seat_area']
    assert r['footprint_world_bounds_cm']['min'][:2] == pytest.approx([-226.25, -103.7451], abs=1e-3)
    deck = max(s['patches'], key=lambda p: p['projected_area_cm2'])
    assert deck['top_z_cm'] == pytest.approx(38.0, abs=1e-3) and deck['exposed_projected_area_cm2'] < M.MIN_SEAT_AREA_CM2


def test_committed_reports_equal_a_fresh_measurement():
    for kind, fn in (('bed', M.measure_bed), ('sofa', M.measure_sofa)):
        committed = json.loads((REPORTS / f'20261014-source-{kind}-surface.json').read_text())
        assert committed == json.loads(json.dumps(fn()))


# ------------------------------------------------------------------ source vs native comparison (deltas, never gated)
def test_compare_reports_deltas_without_gating_and_refuses_unmeasured_native():
    src = M.measure_sofa()
    v, f = sofa_like()
    native = {'errors': [], 'sofa': {'sections': [{'vertices_world_cm': v, 'seat_surface': S.seat_surface(v, f)}]}}
    out = M.compare(src, native)
    assert out['gated'] is False and out['comparable'] is True and out['native_verified'] is False
    assert out['deltas']['top_z_cm'][1] == pytest.approx(50 - 50.3, abs=1e-3)
    assert out['both_meet_existing_area_minimum'] is True
    assert M.compare(src, {'errors': ['no sofa']})['comparable'] is False
    bed = M.measure_bed()
    bv, bf = quad(-315, -335, -165, -135, 360, 0)
    nbed = {'errors': [], 'bed': {'sections': [{'mattress_surface': {**B.mattress_top(bv, bf), 'head_end_direction_xy': [0, -1]}}]}}
    d = M.compare(bed, nbed)['deltas']
    assert d['head_end_angle_deg'] == 0 and d['area_cm2'] == pytest.approx(30000 - 30004.07, abs=0.01)
    with pytest.raises(ValueError):
        M.compare({'schema': 'x'}, nbed)
