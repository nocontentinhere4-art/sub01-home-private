"""Rigid horizontal seat placement candidates (tools/fit_seat_rigid_placement.py).

The fixture is synthetic but built from root's ACTUAL DeskTyping measurements (2026-10-14):
body mesh at [203.9, -232.3, -0.6] cm, yaw 180; broad cushion bounds [173.661, -214.063, 44.357]
to [226.132, -166.341, 51.407] (~2228 cm2 projected); downward buttock skin bounds
[185.272, -246.152, 56.511] to [223.788, -218.797, 83.081]; posterior thighs Y -271..-219; sole
support 2.5 cm near Y=-270; right-hand reach 51.84344 cm requested vs 50.85667 cm arm at
t=6.8333 s, 8 frames over; key target 0.08 cm, right-hand max gap 0.3442 cm, cap spread 0.077485 cm.
Everything else (sample density, cushion edge roll, chair/desk collision boxes, shoulder and
target layout, sole height) is an ASSUMPTION stated next to it.
"""
import copy
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import fit_seat_rigid_placement as fit  # noqa: E402
import unreal_keyboard_contact_target as key_target  # noqa: E402
import unreal_skin_contact_native as native  # noqa: E402
import validate_unreal_contact_profile as contact_profile  # noqa: E402
import validate_unreal_seat_contact as seat_contact  # noqa: E402

# --- measured by root (Unreal, DeskTyping 3-8 s at 60 Hz)
BODY = [203.9, -232.3, -.6]
CUSHION_MIN, CUSHION_MAX = (173.661, -214.063, 44.357), (226.132, -166.341, 51.407)
CUSHION_AREA = 2228.0
BUTT_MIN, BUTT_MAX = (185.272, -246.152, 56.511), (223.788, -218.797, 83.081)
THIGH_Y = (-271., -219.)
SUPPORT_Z = 2.5
# Soles, root 2026-10-14 (source/UE parity at 3/6/8 s): a genuine seated typing foot plants its toes with
# the heel raised. Plantar gap to the world floor min/median/max and the downward plantar normal.
SOLE = {'left': (-.161, 10.397, 24.268, (.05861, .84598, -.52998)),
        'right': (-.360, 7.527, 14.820, (-.02862, .57003, -.82113))}
ARM = 50.85667
REQUESTED_WORST, WORST_TIME = 51.84344, 6.833333
KEY_TOP, KEY_TARGET, KEY_RIGHT_MAX, CAP_SPREAD = 87.38975858, .08, .3442, .077485
TIMES = [3 + i / 60 for i in range(301)]
REACH_FRAMES = list(range(227, 235))          # 8 consecutive frames, t=6.8333 s is frame 230
REACH_EXCESS = [.21, .45, .78, REQUESTED_WORST - ARM, .90, .66, .40, .12]

FAST = fit.SearchConfig(coarse_xy_step_cm=10., coarse_yaw_step_deg=5., refine_seeds=3,
                        min_xy_step_cm=.5, min_yaw_step_deg=.625, top_n=3)


def _grid_mesh(x0, x1, y0, y1, nx, ny, height, keep=lambda x, y: True):
    xs, ys = np.linspace(x0, x1, nx + 1), np.linspace(y0, y1, ny + 1)
    vertices = [[float(x), float(y), float(height(x, y))] for x in xs for y in ys]
    faces = []
    for i in range(nx):
        for j in range(ny):
            if not keep((xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2):
                continue
            a, b, c, d = i * (ny + 1) + j, (i + 1) * (ny + 1) + j, (i + 1) * (ny + 1) + j + 1, i * (ny + 1) + j + 1
            faces += [[a, b, c], [a, c, d]]
    return {'vertices_world_cm': vertices, 'triangle_indices': faces}


def chair_report():
    """Broad cushion: plateau at the measured top, edges rolling to the measured low over 4 cm
    (assumption), corners chamfered 11.75 cm so the projected area is the measured ~2228 cm2."""
    (x0, y0, z0), (x1, y1, z1) = CUSHION_MIN, CUSHION_MAX
    cx, cy, hx, hy = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2

    def height(x, y):
        edge = min(hx - abs(x - cx), hy - abs(y - cy))
        return z1 - (z1 - z0) * max(0., 1 - edge / 4.) ** 2

    def keep(x, y):
        return (hx - abs(x - cx)) + (hy - abs(y - cy)) >= 11.75

    mesh = _grid_mesh(x0, x1, y0, y1, 26, 24, height, keep)
    return {'errors': [], 'chair': {
        'component': '/Game/Sub01Home/ActualHome.Chair:Cushion',
        'transform': {'translation_cm': [cx, cy, 0.], 'rotation_xyzw': [0, 0, 0, 1], 'scale': [1, 1, 1]},
        'sections': [{'vertices_world_cm': mesh['vertices_world_cm'],
                      'cushion_surface': {'triangle_indices': mesh['triangle_indices']}}]}}


def _frames(points, normals, sway=.15):
    """Same fixed vertex set every frame, with a small deterministic lateral sway (assumption)."""
    pos, nrm = [], []
    for t in TIMES:
        dx = sway * math.sin(2 * math.pi * t / 2.5)
        pos.append([[p[0] + dx, p[1], p[2]] for p in points])
        nrm.append([list(n) for n in normals])
    return {'positions_cm': pos, 'normals': nrm}


def skin_export():
    patches = {}
    # Buttocks: measured downward bounds; most skin low, rising to 83.081 at the rim; 4 non-facing.
    pts, nrm = [], []
    for x in np.linspace(BUTT_MIN[0], BUTT_MAX[0], 8):
        for y in np.linspace(BUTT_MIN[1], BUTT_MAX[1], 6):
            r = max(abs(2 * (x - BUTT_MIN[0]) / (BUTT_MAX[0] - BUTT_MIN[0]) - 1),
                    abs(2 * (y - BUTT_MIN[1]) / (BUTT_MAX[1] - BUTT_MIN[1]) - 1))
            pts.append([x, y, BUTT_MIN[2] + (BUTT_MAX[2] - BUTT_MIN[2]) * r ** 6])
            nrm.append([0., .3 * r, -.95 + .4 * r * r])
    pts.append([(BUTT_MIN[0] + BUTT_MAX[0]) / 2, (BUTT_MIN[1] + BUTT_MAX[1]) / 2, BUTT_MIN[2]])   # lowest skin
    nrm.append([0., 0., -1.])
    for x in (196., 200., 206., 212.):
        pts.append([x, -219.5, 78.])
        nrm.append([0., .97, -.2])                   # side-facing: must be ignored like the native audit
    patches['buttocks'] = _frames(pts, nrm)
    # Posterior thighs: Y -271..-219 measured; underside height 57.2..58.8 (assumption).
    for name, (xa, xb) in (('left_posterior_thigh', (207., 221.)), ('right_posterior_thigh', (187., 201.))):
        pts = [[x, y, 57.2 + .03 * (-219 - y)] for x in np.linspace(xa, xb, 5) for y in np.linspace(*THIGH_Y, 8)]
        patches[name] = _frames(pts, [[0., 0., -.9]] * len(pts))
    # Soles: a FIXED plantar index set (root's rule; 144 per foot here, 4171 in the actual mesh), toe edge
    # at Y=-280 planted, heel at Y=-256 raised; heights from root's measured min/median/max (profile shape
    # z = min + range * s**p is an assumption), the same indices scored every frame, never re-picked.
    for k, (side, (xa, xb)) in enumerate((('left', (209., 219.)), ('right', (189., 199.)))):
        lo, med, hi, normal = SOLE[side]
        power = math.log((med - lo) / (hi - lo)) / math.log(.5)
        pts = [[x, -280. + 24. * u, lo + (hi - lo) * u ** power]
               for u in np.linspace(0., 1., 24) for x in np.linspace(xa, xb, 6)]
        name = f'{side}_sole'
        patches[name] = _frames(pts, [list(normal)] * len(pts), sway=0.)
        patches[name]['vertex_indices'] = [9000 + 1000 * k + i for i in range(len(pts))]
    # Extra body points for collision: lower back, foot tops, shins (assumption).
    extra = [[x, -214.5, z] for x in np.linspace(190, 218, 5) for z in np.linspace(62, 110, 6)]
    extra += [[x, y, 8.] for x in (192., 196., 212., 216.) for y in (-276., -268., -260.)]
    extra += [[x, -268., z] for x in (194., 214.) for z in np.linspace(15, 50, 5)]
    legs = [None] * 30 + ['right' if x < 204 else 'left' for x in (192., 196., 212., 216.) for _ in range(3)]
    legs += ['right' if x < 204 else 'left' for x in (194., 214.) for _ in range(5)]
    return {'schema': fit.SCHEMA_SKIN, 'clip': 'DeskTyping',
            'body': {'location_cm': BODY, 'yaw_deg': 180, 'rotation_pyr': [0, 180, 0], 'scale_xyz': [1, 1, 1]},
            'times_s': TIMES, 'patches': patches,
            'sole_membership': {'rule': 'slides material, rest Y <= 0.004 m, bind normal Y < -0.7 (fixture)',
                                'expected_vertex_count': 288}, 'collision_samples': {**_frames(extra, [[0, 0, 1]] * len(extra)), 'leg': legs}}


def _rect(name, x0, x1, y0, y1, z):
    return {'name': name, **_grid_mesh(x0, x1, y0, y1, 1, 1, lambda x, y: z)}


def scene_export(chair_height=None):
    cx, cy = (CUSHION_MIN[0] + CUSHION_MAX[0]) / 2, (CUSHION_MIN[1] + CUSHION_MAX[1]) / 2
    out = {'schema': fit.SCHEMA_SCENE,
           'floor_support': [_rect('floor', 0, 500, -500, 0, 0.),
                             {**_rect('office_rug', 150, 260, -300, -240, SUPPORT_Z), 'adjustable': True}],
           'support_alternatives': [{'name': 'remove_rug', 'delta_cm': -SUPPORT_Z, 'source': 'fixture assumption'}],
           # Chair rigid parts (assumption): star base, gas column, backrest. The cushion is NOT a collider.
           'chair_collision': {'boxes': [
               {'name': 'base', 'center_cm': [cx, cy, 5], 'half_extents_cm': [30, 30, 5]},
               {'name': 'column', 'center_cm': [cx, cy, 25], 'half_extents_cm': [3, 3, 15]},
               {'name': 'backrest', 'center_cm': [cx, -161, 76], 'half_extents_cm': [24, 3, 22]}]},
           # Desk moves with the keyboard as one unit (assumption).
           'keyboard_collision': {'boxes': [
               {'name': 'desk_top', 'center_cm': [205, -315, 82], 'half_extents_cm': [55, 30, 2]},
               {'name': 'keyboard_case', 'center_cm': [204, -292, 85.5], 'half_extents_cm': [24, 8, 1.5]}]}}
    if chair_height is not None:
        out['chair_height_adjustment_cm'] = {'range_cm': chair_height, 'source': 'synthetic test range'}
    return out


def keyboard_export(vertical_only=False):
    caps = _grid_mesh(181, 227, -300, -284, 23, 8, lambda x, y: KEY_TOP - CAP_SPREAD * ((int(x) * 7 + int(y) * 3) % 11) / 10)
    frames = []
    for i, t in enumerate(TIMES):
        hands = []
        for side, sx, dxs in (('left', 221.9, -8.), ('right', 185.9, 8.)):
            sway = .3 * math.sin(2 * math.pi * t / 1.7)
            shoulder = np.array([sx + sway, -252., 123.2])
            direction = np.array([dxs, -35., -35.])
            dist = 50.14 + .3 * math.sin(2 * math.pi * t / 2.3)
            if side == 'right' and i in REACH_FRAMES:
                dist = ARM + REACH_EXCESS[REACH_FRAMES.index(i)]
                if vertical_only:                     # the arm would have to reach straight down
                    direction = np.array([0., 0., -1.])
            target = shoulder + direction / np.linalg.norm(direction) * dist
            gap = KEY_TARGET
            if side == 'right' and 200 <= i <= 210:
                gap = KEY_TARGET + (KEY_RIGHT_MAX - KEY_TARGET) * (1 - abs(i - 205) / 5)
            hands.append({'side': side, 'shoulder_cm': shoulder.tolist(), 'target_cm': target.tolist(),
                          'key_top_cm': KEY_TOP, 'corrected_over_key_min_cm': KEY_TOP + gap})
        frames.append({'time_s': t, 'hands': hands})
    return {'schema': fit.SCHEMA_KEYBOARD, 'keycap_tops': caps, 'keycap_top_spread_cm': CAP_SPREAD,
            'key_contact_target_cm': KEY_TARGET, 'arm_length_cm': {'left': ARM, 'right': ARM}, 'frames': frames}


def problem(**kw):
    return fit.build_problem(skin_export(), chair_report(), scene_export(kw.get('chair_height')),
                             keyboard_export(kw.get('vertical_only', False)))


@pytest.fixture(scope='module')
def solved():
    p = problem()
    return p, fit.solve(p, FAST)


def gates_of(candidate, gate=None, subject=None):
    return [g for g in candidate['failing_gates']
            if (gate is None or g['gate'] == gate) and (subject is None or g['subject'] == subject)]


def all_candidates(result):
    out = [result['baseline']]
    for entry in result['families'].values():
        out += entry['candidates'] + ([entry['reach_best']] if 'reach_best' in entry else [])
    if 'combined_chair_and_keyboard' in result:
        out.append(result['combined_chair_and_keyboard'])
    return out + result['support_surface']['alternatives_evaluated']


# ---------------------------------------------------------------- fixture fidelity
def test_fixture_matches_measured_geometry():
    p = problem()
    lo, hi = p.cushion.bounds()
    assert np.allclose(lo, CUSHION_MIN, atol=1e-6) and np.allclose(hi, CUSHION_MAX, atol=1e-6)
    assert abs(p.cushion_area_cm2 - CUSHION_AREA) / CUSHION_AREA < .03
    butt = p.patch_pos['buttocks'][0][p.patch_nrm['buttocks'][0][:, 2] <= -.5]
    assert butt[:, 2].min() == pytest.approx(BUTT_MIN[2]) and butt[:, 2].max() == pytest.approx(BUTT_MAX[2])
    assert butt[:, 1].max() < CUSHION_MIN[1]                         # zero horizontal overlap, as measured
    d = np.linalg.norm(p.targets - p.shoulders, axis=2)
    over = np.nonzero(d[:, 1] > ARM)[0]
    assert over.tolist() == REACH_FRAMES and d[230, 1] == pytest.approx(REQUESTED_WORST)
    assert p.times[230] == pytest.approx(WORST_TIME, abs=1e-6)
    for side, (lo, med, hi, _) in SOLE.items():
        z = np.sort(p.patch_pos[f'{side}_sole'][0][:, 2])
        assert z[0] == pytest.approx(lo) and z[-1] == pytest.approx(hi)
        assert z[int(.5 * (len(z) - 1) + .5)] == pytest.approx(med, abs=.6)       # native median rule


def test_surface_lookup_matches_native_sub01_surface_height_at(tmp_path):
    compiler = shutil.which('c++')
    if not compiler:
        pytest.skip('C++ compiler unavailable')
    source = re.search(r'static bool Sub01SurfaceHeightAt.*?\n}\n', native.SEAT_CPP, re.S).group(0)
    p = problem()
    tri = p.cushion.tri.reshape(-1, 3)
    rng = np.random.default_rng(7)
    pts = np.column_stack([rng.uniform(170, 230, 400), rng.uniform(-218, -162, 400)])
    pts = np.vstack([pts, tri[:40, :2]])                              # exact vertices / shared edges
    prog = ('#include <cstdio>\ntypedef int int32;struct FVector{double X,Y,Z;};\n' + source +
            'int main(){static const FVector T[]={' + ','.join('{%.17g,%.17g,%.17g}' % tuple(v) for v in tri) + '};'
            'double X,Y;while(scanf("%lf %lf",&X,&Y)==2){double Z=0;bool F=Sub01SurfaceHeightAt(T,COUNT,X,Y,Z);'
            'printf("%d %.12f\\n",F?1:0,F?Z:0.);}}').replace('COUNT', str(len(tri)))
    (tmp_path / 'h.cpp').write_text(prog)
    subprocess.run([compiler, '-std=c++17', '-O1', str(tmp_path / 'h.cpp'), '-o', str(tmp_path / 'h')], check=True,
                   capture_output=True)
    out = subprocess.run([str(tmp_path / 'h')], input='\n'.join('%.17g %.17g' % tuple(q) for q in pts),
                         capture_output=True, text=True, check=True).stdout.split('\n')
    found, z = p.cushion.height(pts)
    for k, line in enumerate(filter(None, out)):
        f, h = line.split()
        assert bool(int(f)) == bool(found[k])
        if found[k]:
            assert float(h) == pytest.approx(z[k], abs=1e-9)


# ---------------------------------------------------------------- required behaviour
def test_current_placement_has_zero_cushion_overlap_and_fails(solved):
    _, result = solved
    base = result['baseline']
    assert base['passing'] is False and base['transforms'] == {}
    for name in fit.SEAT_PATCHES:
        assert base['metrics']['patches'][name]['min_horizontal_overlap_fraction'] == 0
        assert base['metrics']['patches'][name]['mean_horizontal_overlap_fraction'] == 0
        g = gates_of(base, 'patch_not_over_surface', name)
        assert g and g[0]['failing_frames'] == 301 and g[0]['worst_amount'] == fit.MIN_PATCH_VERTICES


def test_translated_chair_candidate_restores_overlap(solved):
    _, result = solved
    best = result['families']['chair']['candidates'][0]
    t = best['transforms']['chair']
    assert t['dy_cm'] <= -32.09                  # cushion front must pass the buttocks' -246.152 edge
    assert abs(t['dx_cm']) <= 40 and abs(t['dy_cm']) <= 40 and abs(t['yaw_deg']) <= 10
    m = best['metrics']['patches']
    assert m['buttocks']['min_horizontal_overlap_fraction'] >= .9
    for name in ('left_posterior_thigh', 'right_posterior_thigh'):
        assert m[name]['min_horizontal_overlap_fraction'] > .3
        assert m[name]['min_over_surface_vertices'] >= fit.MIN_PATCH_VERTICES
    assert not gates_of(best, 'patch_not_over_surface', 'buttocks')
    assert best['moved_world_transforms']['chair']['location_cm'][1] < CUSHION_MIN[1] + 10
    # Overlap is restored, but the cushion top is 5.104 cm under the lowest buttock skin: the seat gap
    # gate still fails, a chair lift is reported as needed, and no body lift is ever used.
    low = gates_of(best, 'lowest_above_band', 'buttocks')[0]           # local support patch rule (9ff9880)
    assert low['worst_amount'] == pytest.approx(BUTT_MIN[2] - CUSHION_MAX[2] - .5, abs=1e-3)
    assert not any(g['gate'] in ('gap', 'coverage') for c in all_candidates(result) for g in c['failing_gates'])
    need = result['families']['chair']['chair_dz_needed_for_seat_band_cm']
    # Lowest-point rule: the thighs' lowest skin (57.2, fixture assumption) binds: 57.2 - 51.407 - 0.5.
    assert need[0] == pytest.approx(57.2 - CUSHION_MAX[2] - .5, abs=1e-3) and need[0] >= low['worst_amount']
    residual = [r for r in result['irreducible_residuals'] if r['residual'] == 'seat_vertical_gap']
    assert residual and residual[0]['allowed_chair_dz_cm'] == [0.0, 0.0]


def test_chair_height_only_within_real_adjustment_and_reported():
    p = problem(chair_height=[-4., 3.])
    result = fit.solve(p, fit.SearchConfig(coarse_xy_step_cm=10., coarse_yaw_step_deg=10., refine_seeds=1,
                                           min_xy_step_cm=1., min_yaw_step_deg=2.5, top_n=2, families=('chair',)))
    for c in result['families']['chair']['candidates']:
        assert -4. <= c['transforms']['chair']['dz_cm'] <= 3.
    best = result['families']['chair']['candidates'][0]
    assert best['transforms']['chair']['dz_cm'] == pytest.approx(3.)   # the full real range, still short
    assert result['inputs']['chair_height_adjustment_source'] == 'synthetic test range'
    with pytest.raises(ValueError):
        fit.build_problem(skin_export(), chair_report(), scene_export([1., 3.]), keyboard_export())


def test_reach_residuals_reported_never_hidden(solved):
    _, result = solved
    for c in result['families']['chair']['candidates']:
        g = gates_of(c, 'reach_exceeds_arm', 'right_hand')
        assert len(g) == 1 and g[0]['failing_frames'] == 8
        assert g[0]['worst_amount'] == pytest.approx(REQUESTED_WORST - ARM, abs=1e-6)
        assert g[0]['worst_time_s'] == pytest.approx(WORST_TIME, abs=1e-4)
        assert g[0]['requested_cm'] == pytest.approx(REQUESTED_WORST) and g[0]['arm_length_cm'] == ARM
        assert g[0]['failing_times_s'] == [round(TIMES[i], 4) for i in REACH_FRAMES]
        assert c['passing'] is False
    chair_res = [r for r in result['irreducible_residuals']
                 if r['residual'] == 'reach_exceeds_arm' and r['scope'].startswith('chair')]
    assert chair_res and chair_res[0]['gates'][0]['failing_frames'] == 8
    # The key gap is also carried unchanged: 0.3442 cm against the fixed 0.08 target and 0.2 band.
    key = [r for r in result['irreducible_residuals'] if r['residual'] == 'key_contact']
    assert key and key[0]['gates'][0]['worst_amount'] == pytest.approx(KEY_RIGHT_MAX - .2)
    assert key[0]['keycap_top_spread_cm'] == CAP_SPREAD
    assert not any(c['passing'] for c in all_candidates(result))


def test_reach_trade_off_between_body_seat_and_keyboard(solved):
    _, result = solved
    body = result['families']['body']
    path = body['trade_off']['path']
    seat_end, reach_end = path[0], path[-1]
    assert reach_end['reach_frames_over_arm']['right'] == 0             # this fixture's targets are reachable...
    assert seat_end['reach_frames_over_arm']['right'] > 8               # ...but moving him onto the cushion breaks more
    assert seat_end['seat_min_overlap_fraction']['buttocks'] > .3
    assert reach_end['seat_min_overlap_fraction']['buttocks'] == 0
    kb = result['families']['keyboard']['reach_best']
    assert not gates_of(kb, 'reach_exceeds_arm')
    assert 1. < abs(kb['transforms']['keyboard']['dy_cm']) < 4.         # ~1.4 cm toward him fixes 0.987 cm over
    combo = result['combined_chair_and_keyboard']
    assert not gates_of(combo, 'reach_exceeds_arm')
    assert set(combo['transforms']) == {'chair', 'keyboard'}
    assert combo['metrics']['patches']['buttocks']['min_horizontal_overlap_fraction'] >= .9
    assert combo['passing'] is False                                    # seat gap and key gap remain


def test_vertical_reach_deficit_is_irreducible_by_any_horizontal_placement():
    p = problem(vertical_only=True)
    result = fit.solve(p, fit.SearchConfig(coarse_xy_step_cm=10., coarse_yaw_step_deg=10., refine_seeds=1,
                                           min_xy_step_cm=1., min_yaw_step_deg=2.5, top_n=1))
    kinds = {(r['residual'], r['scope']) for r in result['irreducible_residuals']}
    assert ('reach_vertical_component_exceeds_arm', 'any horizontal placement, any bounds') in kinds
    assert ('reach_exceeds_arm', 'every single rigid horizontal family searched') in kinds
    v = [r for r in result['irreducible_residuals'] if r['residual'] == 'reach_vertical_component_exceeds_arm'][0]
    assert v['frames'] == 8 and v['worst_excess_cm'] == pytest.approx(REQUESTED_WORST - ARM, abs=1e-6)
    for fam in ('body', 'keyboard'):
        g = gates_of(result['families'][fam]['reach_best'], 'reach_exceeds_arm', 'right_hand')
        assert g and g[0]['failing_frames'] == 8


def test_no_candidate_changes_body_z_or_scale(solved):
    p, result = solved
    before = {n: p.patch_pos[n].copy() for n in fit.PATCHES}
    fit.evaluate(p, {'body': fit.Rigid(5., -3., 0., 4., (BODY[0], BODY[1]))})
    for n in fit.PATCHES:
        assert np.array_equal(before[n], p.patch_pos[n])
    for c in all_candidates(result):
        assert c['body'] == {'dz_cm': 0.0, 'scaled': False, 'per_bone_changes': False,
                             'moved_horizontally': c['body']['moved_horizontally']}
        assert c['transforms'].get('body', {}).get('dz_cm', 0.0) == 0.0
        for t in c['transforms'].values():
            assert set(t) == {'dx_cm', 'dy_cm', 'dz_cm', 'yaw_deg', 'pivot_cm'}     # no scale, no bones
            assert abs(t['dx_cm']) <= 40 and abs(t['dy_cm']) <= 40 and abs(t['yaw_deg']) <= 10
    with pytest.raises(ValueError):
        fit.evaluate(p, {'body': fit.Rigid(0., 0., 1., 0., (0., 0.))})
    bad = skin_export()
    bad['body']['scale_xyz'] = [1., 1., 1.02]
    with pytest.raises(ValueError):
        fit.build_problem(bad, chair_report(), scene_export(), keyboard_export())


def test_thresholds_are_the_documented_constants(solved):
    assert fit.SEAT_BAND_CM is seat_contact.SEAT_BAND_CM and fit.SEAT_BAND_CM == (-2.5, .5)
    assert fit.SOLE_BAND_CM is seat_contact.SOLE_BAND_CM and fit.SOLE_BAND_CM == (0., 1.)
    assert fit.MIN_PATCH_VERTICES == seat_contact.MIN_PATCH_VERTICES == 12
    assert fit.MIN_BAND_COVERAGE == seat_contact.MIN_BAND_COVERAGE == .5
    assert fit.MIN_SUPPORT_VERTICES == seat_contact.MIN_SUPPORT_VERTICES == 12
    assert fit.KEY_GAP_MAX_CM == contact_profile.KEY_GAP_MAX_CM == .2
    assert fit.KEY_PENETRATION_MAX_CM == .1 and "h['penetrationCm']>.1" in Path(contact_profile.__file__).read_text()
    assert fit.KEY_CONTACT_TARGET_CM == .08 and 'KeyTop+.08' in key_target.CPP
    assert fit.FACING_DOWN_MAX_NZ == -.5 and 'if(N.Z>-.5)continue' in native.SEAT_CPP
    assert fit.REACH_TOLERANCE_CM == 0 and fit.BODY_COLLISION_ALLOWED_CM == 0
    _, result = solved
    assert result['constants']['seat_band_cm'] == [-2.5, .5] and result['constants']['key_contact_target_cm'] == .08
    bad = keyboard_export()
    bad['key_contact_target_cm'] = .3
    with pytest.raises(ValueError):
        fit.build_problem(skin_export(), chair_report(), scene_export(), bad)


def test_output_is_deterministic():
    cheap = fit.SearchConfig(coarse_xy_step_cm=20., coarse_yaw_step_deg=10., refine_seeds=2, min_xy_step_cm=1.,
                             min_yaw_step_deg=2.5, top_n=2)
    first, second = fit.solve(problem(), cheap), fit.solve(problem(), cheap)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_collisions_are_scored(solved):
    p, result = solved
    pivot = p.chair_pivot
    # Chair base pushed under his feet: the foot-top samples at Y=-260 go inside the base box.
    gates, metrics, _ = fit.evaluate(p, {'chair': fit.Rigid(0., -40.5, 0., 0., pivot)})
    hit = [g for g in gates if g['gate'] == 'body_collision' and g['subject'] == 'chair:base']
    assert hit and hit[0]['failing_frames'] == 301 and hit[0]['worst_amount'] > 0 and hit[0]['vertices_inside'] >= 1
    # Chair driven into the desk: furniture overlap, exact box SAT.
    gates, _, _ = fit.evaluate(p, {'chair': fit.Rigid(0., -130., 0., 0., pivot)})
    over = [g for g in gates if g['gate'] == 'furniture_overlap']
    assert over and any('keyboard:desk_top' in g['subject'] for g in over)
    assert over[0]['method'] == 'exact box SAT'
    # The ranked chair candidates keep his feet out of the base.
    for c in result['families']['chair']['candidates']:
        assert not gates_of(c, 'body_collision')
    # Without collision primitives nothing can pass: collision is "not measured", never assumed clear.
    scene = scene_export()
    scene.pop('chair_collision')
    scene.pop('keyboard_collision')
    bare = fit.build_problem(skin_export(), chair_report(), scene, keyboard_export())
    gates, _, _ = fit.evaluate(bare, {})
    assert {'collision_not_measured', 'inputs_incomplete'} <= {g['gate'] for g in gates}


def test_hull_primitives_score_penetration():
    hull = fit.hull_primitive({'name': 'arm_pad', **_box_mesh((200., -200., 60.), (5., 5., 2.))}, 'chair')
    assert hull.depth([[200., -200., 60.]])[0] == pytest.approx(2.)
    assert hull.depth([[200., -200., 63.]])[0] < 0


def _box_mesh(c, h):
    v = [[c[0] + sx * h[0], c[1] + sy * h[1], c[2] + sz * h[2]] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    faces = [[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6],
             [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]]
    return {'vertices_world_cm': v, 'triangle_indices': faces}


def test_solver_never_reports_verified(solved, tmp_path):
    _, result = solved
    assert result['verified'] is False and result['requires_server_reaudit'] is True
    for c in all_candidates(result):
        assert c['verified'] is False and c['requires_server_reaudit'] is True
    text = json.dumps(result)
    for word in ('NativeSeatVerified', 'native_seat_verified', 'ContactVerified', '"verified": true'):
        assert word not in text
    source = Path(fit.__file__).read_text()
    assert 'NativeSeatVerified' not in source.replace('never claims', '')
    # CLI end to end on files, same guarantees.
    paths = {}
    for name, data in (('skin', skin_export()), ('chair', chair_report()), ('scene', scene_export()),
                       ('keyboard', keyboard_export())):
        paths[name] = tmp_path / f'{name}.json'
        paths[name].write_text(json.dumps(data))
    out = tmp_path / 'out.json'
    fit.main(['--skin', str(paths['skin']), '--chair', str(paths['chair']), '--scene', str(paths['scene']),
              '--keyboard', str(paths['keyboard']), '--out', str(out), '--families', 'chair', '--top', '1',
              '--xy-step', '20', '--yaw-step', '10'])
    written = json.loads(out.read_text())
    assert written['verified'] is False and written['requires_server_reaudit'] is True
    assert set(written['inputs']['digests']) == {'skin', 'chair', 'scene', 'keyboard'}


def test_rejects_incomplete_or_unnamed_inputs():
    skin = skin_export()
    del skin['sole_membership']
    with pytest.raises(ValueError):
        fit.build_problem(skin, chair_report(), scene_export(), keyboard_export())
    for mutate in (lambda s: s['patches']['left_sole'].pop('vertex_indices'),
                   lambda s: s['patches']['left_sole']['vertex_indices'].pop(),
                   lambda s: s['patches']['right_sole'].__setitem__('vertex_indices', s['patches']['left_sole']['vertex_indices']),
                   lambda s: s['sole_membership'].__setitem__('expected_vertex_count', 4177)):
        skin = skin_export()
        mutate(skin)
        with pytest.raises(ValueError):
            fit.build_problem(skin, chair_report(), scene_export(), keyboard_export())
    skin = skin_export()
    skin['times_s'] = TIMES[:-1]
    for name in fit.PATCHES:
        for k in ('positions_cm', 'normals'):
            skin['patches'][name][k] = skin['patches'][name][k][:-1]
    skin['collision_samples']['positions_cm'] = skin['collision_samples']['positions_cm'][:-1]
    kb = keyboard_export()
    kb['frames'] = kb['frames'][:-1]
    p = fit.build_problem(skin, chair_report(), scene_export(), kb)
    gates, _, _ = fit.evaluate(p, {})
    assert any(g['gate'] == 'inputs_incomplete' for g in gates)
    lumbar = copy.deepcopy(chair_report())
    sec = lumbar['chair']['sections'][0]
    sec['cushion_surface']['triangle_indices'] = sec['cushion_surface']['triangle_indices'][:12]
    with pytest.raises(ValueError):                          # a small patch (the 58 cm2 lumbar) is not a seat
        fit.build_problem(skin_export(), lumbar, scene_export(), keyboard_export())


def test_soles_score_the_fixed_index_set_as_a_support_patch(solved):
    p, result = solved
    assert p.sole_membership['vertex_counts'] == {'left_sole': 144, 'right_sole': 144}
    base = result['baseline']
    for side, (lo, med, hi, _) in SOLE.items():
        name = f'{side}_sole'
        m = base['metrics']['patches'][name]
        assert m['min_over_surface_vertices'] == 144                 # every fixed plantar vertex, every frame
        assert m['worst_min_gap_cm'] == pytest.approx(lo - SUPPORT_Z)  # toe edge inside the 2.5 cm rug
        pen = gates_of(base, 'penetration', name)
        assert pen and pen[0]['failing_frames'] == 301 and pen[0]['worst_amount'] == pytest.approx(SUPPORT_Z - lo)
        # A raised heel is genuine motion: no whole-sole median or coverage gate for soles.
        assert not gates_of(base, 'gap', name) and not gates_of(base, 'coverage', name)
        assert m['max_median_gap_cm'] > 4


def test_leg_support_family_is_measured_bounded_and_flags_the_hip(solved):
    p, result = solved
    leg = result['leg_support']
    for side, (lo, _, _, _) in SOLE.items():
        d = leg['legs'][side]
        need = SUPPORT_Z - lo                       # 2.661 / 2.860 here; root estimated 2.74 / 2.94 on the real mesh
        assert d['translation_cm'] == [0.0, 0.0, pytest.approx(need)]
        assert d['hip_joint_discontinuity_cm'] == pytest.approx(need) and d['bone_lengths_preserved'] is True
        assert d['feasible_within_bounds'] is True
        name = f'{side}_sole'
        assert not [g for g in leg['failing_gates'] if g['subject'] == name]   # support patch met after the shift
        assert leg['metrics']['patches'][name]['min_band_vertices'] >= fit.MIN_SUPPORT_VERTICES
        hip = gates_of(leg, 'hip_joint_discontinuity', f'{side}_leg')
        assert hip and hip[0]['worst_amount'] == pytest.approx(need)
    assert leg['pure_rigid_placement'] is False and leg['requires_pose_solution'] is True
    assert leg['passing'] is False and leg['verified'] is False
    assert leg['body']['dz_cm'] == 0.0 and leg['body']['scaled'] is False and leg['body']['per_bone_changes'] is True
    # The thighs ride up with the legs: their cushion gap grows (shown, not hidden).
    chair = result['families']['chair']['candidates'][0]
    assert (leg['metrics']['patches']['left_posterior_thigh']['max_median_gap_cm'] >
            chair['metrics']['patches']['left_posterior_thigh']['max_median_gap_cm'])
    residual = [r for r in result['irreducible_residuals'] if r['residual'] == 'sole_support']
    assert residual and residual[0]['leg_support_requires_pose_solution'] is True


def test_support_surface_family(solved):
    _, result = solved
    sup = result['support_surface']
    for side, (lo, _, _, _) in SOLE.items():
        f = sup['feet'][side]
        assert f['needed_support_top_z_cm'] == [pytest.approx(lo - 1), pytest.approx(lo)]
        assert f['fixed_floor_under_sole_z_cm'] == 0.0
        assert f['feasible'] is False and 'below the fixed floor' in f['reason']   # toes reach under the real floor
    assert sup['one_surface_for_both_feet_feasible'] is False
    removed = sup['alternatives_evaluated'][0]
    assert removed['support_change']['name'] == 'remove_rug'
    for side, (lo, _, _, _) in SOLE.items():
        pen = gates_of(removed, 'penetration', f'{side}_sole')
        assert pen and pen[0]['worst_amount'] == pytest.approx(-lo)      # 0.161 / 0.360 cm left after removing it
    assert removed['body']['moved_horizontally'] is False and 'legs' not in removed


# ---------------------------------------------------------------- actual repo data, when present
AUDIT = ROOT / 'private-audit'


def test_actual_repo_data_if_present():
    chair_path = AUDIT / 'native-chair-surface.json'
    inputs = AUDIT / 'native-seat-fit'
    if not chair_path.exists():
        pytest.skip('private-audit/native-chair-surface.json is not in git; root runs this on the server')
    chair = json.loads(chair_path.read_text())
    surface = fit.Surface(np.asarray(seat_contact.cushion_triangles(chair), dtype=float))
    assert surface.projected_area_cm2() >= 1000
    if not all((inputs / f'{n}.json').exists() for n in ('skin', 'scene', 'keyboard')):
        pytest.skip('private-audit/native-seat-fit/{skin,scene,keyboard}.json not exported yet')
    p = fit.build_problem(json.loads((inputs / 'skin.json').read_text()), chair,
                          json.loads((inputs / 'scene.json').read_text()),
                          json.loads((inputs / 'keyboard.json').read_text()))
    gates, metrics, _ = fit.evaluate(p, {})
    assert p.body_yaw == 180 and np.allclose(p.body_location, BODY)
    result = fit.solve(p, FAST)
    assert result['verified'] is False and result['requires_server_reaudit'] is True
