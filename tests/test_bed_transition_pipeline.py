"""Bed transition pipeline: retarget, crop, blend search, root path, provenance, bed surface and placement fitter.

Synthetic tests run anywhere with numpy; tests that need Node (retarget_first_person.mjs) or the repository's
clip files skip when they are absent.
"""
from __future__ import annotations

import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import bed_transition_pipeline as B  # noqa: E402
import fit_bed_placement as F  # noqa: E402
import life_gltf as G  # noqa: E402
import unreal_bed_surface_audit as A  # noqa: E402
import validate_unreal_seat_contact as C  # noqa: E402

OWNER = ROOT / 'web/room/char_mixamo.glb'
HAVE_OWNER = OWNER.is_file()
HAVE_NODE = shutil.which('node') is not None
needs_owner = pytest.mark.skipif(not HAVE_OWNER, reason='owner skin absent')
needs_node = pytest.mark.skipif(not (HAVE_OWNER and HAVE_NODE), reason='node or owner skin absent')
HAVE_SOURCES = all(p.is_file() for p in [*B.SOURCES.values(), *B.SLEEP_LOOPS.values(), *B.CARRIED_COPIES.values()])


@pytest.fixture(scope='module')
def sk():
    if not HAVE_OWNER:
        pytest.skip('owner skin absent')
    return B.Skeleton(OWNER)


def axis_q(axis, deg):
    a = np.asarray(axis, float) / np.linalg.norm(axis)
    s = math.sin(math.radians(deg) / 2)
    return np.array([a[0] * s, a[1] * s, a[2] * s, math.cos(math.radians(deg) / 2)])


def motion_with(sk, angles_deg, joint='Spine', axis=(1, 0, 0), hips=None):
    """Owner rest pose with one joint bent by the given angles (one per frame) about its local axis."""
    F_ = len(angles_deg)
    q = np.broadcast_to(sk.rest_q, (F_,) + sk.rest_q.shape).copy()
    k = sk.index[joint]
    for f, a in enumerate(angles_deg):
        q[f, k] = B.qmul(sk.rest_q[k], axis_q(axis, a))
    t = np.broadcast_to(sk.rest_t[sk.index['Hips']], (F_, 3)).copy() if hips is None else np.asarray(hips, float)
    return B.Motion(sk, q, t)


# ------------------------------------------------------------------ FK and retarget
@needs_owner
def test_numpy_fk_matches_life_gltf_on_a_real_owner_clip(sk):
    path = ROOT / 'web/room/desk_states/bed/sleep_back.glb'
    if not path.is_file():
        pytest.skip('sleep_back absent')
    m = B.Motion.from_glb(sk, path)
    pos, _ = m.world()
    g = G.Gltf(path)
    clip = g.animation()
    for f in (0, 100, len(m) - 1):
        w = G.world_pose(g, clip, clip.key_times()[f])
        for k, n in enumerate(sk.names):
            assert np.allclose(np.array(w[g.by_name['mixamorig:' + n]][0]) * 100, pos[f, k], atol=1e-6)


def write_source(path, sk, scale=1.1, frames=6):
    """A synthetic retarget SOURCE: the owner's joint names and parents, every bone 10 % longer, a few captured
    rotations and a moving hips; no skin."""
    names = sk.names
    children = {k: [] for k in range(len(names))}
    for k, p in enumerate(sk.parent):
        if p >= 0:
            children[p].append(k + 1)
    nodes = [{'name': 'mixamo', 'scale': [0.01, 0.01, 0.01], 'children': [1]}]
    for k, n in enumerate(names):
        node = {'name': 'mixamorig:' + n, 'translation': list(sk.rest_t[k] * (1 if n == 'Hips' else scale)),
                'rotation': list(sk.rest_q[k])}
        if children[k]:
            node['children'] = children[k]
        nodes.append(node)
    bw = G.BinWriter()
    times = [f / 30 for f in range(frames)]
    ti = bw.add(times, 'SCALAR', minmax=True)
    anim = {'name': 'synthetic', 'samplers': [], 'channels': []}
    for joint, axis in (('Spine', (1, 0, 0)), ('LeftArm', (0, 0, 1)), ('RightUpLeg', (1, 0, 0))):
        k = sk.index[joint]
        rows = [tuple(B.qmul(sk.rest_q[k], axis_q(axis, 8 * f))) for f in range(frames)]
        anim['samplers'].append({'input': ti, 'output': bw.add(rows, 'VEC4'), 'interpolation': 'LINEAR'})
        anim['channels'].append({'sampler': len(anim['samplers']) - 1, 'target': {'node': k + 1, 'path': 'rotation'}})
    h = sk.rest_t[sk.index['Hips']]
    rows = [(h[0] + 2 * f, h[1] * scale, h[2] + 3 * f) for f in range(frames)]
    anim['samplers'].append({'input': ti, 'output': bw.add(rows, 'VEC3'), 'interpolation': 'LINEAR'})
    anim['channels'].append({'sampler': len(anim['samplers']) - 1, 'target': {'node': 1, 'path': 'translation'}})
    doc = {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': [0]}], 'nodes': nodes, 'animations': [anim],
           'accessors': bw.accessors, 'bufferViews': bw.views, 'buffers': [{'byteLength': len(bw.data) + (-len(bw.data)) % 4}]}
    G.write_glb(path, doc, bytes(bw.data))


@needs_node
def test_retarget_keeps_owner_bone_lengths_and_writes_no_bone_translation(sk, tmp_path):
    src = tmp_path / 'longer_bones.glb'
    write_source(src, sk)
    raw, _, rep = B.retarget_v5(src, tmp_path / 'work', OWNER, preset='mixamo')
    m = B.Motion.from_glb(sk, raw)
    assert m.translation_drift_cm['non_hips_translation_tracks'] == 0
    assert B.owner_offsets_residual(m)['max_bone_length_deviation_cm'] < 1e-6
    assert rep['retarget_first_person_mjs']['checks']['sampledBoneLengthMaxError'] < 1e-5
    assert rep['retarget_first_person_mjs']['proceduralMotionAdded'] is False
    # the source's bones were 10 % longer: the output keeps the OWNER's, not the source's
    src_m = B.Motion.from_glb(sk, src, keep_bone_translations=True)
    assert B.owner_offsets_residual(src_m)['max_bone_length_deviation_cm'] > 0.5
    # a captured rotation survives: the spine bends in the output as in the source
    out_tilt = B.torso_tilt_deg(m)
    assert out_tilt[-1] - out_tilt[0] > 5


# ------------------------------------------------------------------ crop detection
def test_crop_detects_standing_onset_before_a_later_walk():
    n = 300
    standing = np.zeros(n, bool)
    standing[150:] = True                      # rises at frame 150 and stays up
    standing[60:64] = True                     # a brief false start (sits back down): must not count
    speed = np.zeros(n)
    speed[150:158] = 25.0                      # still moving as he comes up
    speed[200:] = 70.0                         # then walks away
    c = B.detect_standing_crop(standing, speed, 30.0)
    assert c['onset_frame'] == 150
    assert c['walk_onset_frame'] == 200
    assert c['crop_frame'] == 158 and c['settled']
    assert c['crop_frame'] < c['walk_onset_frame']


def test_crop_none_when_never_standing():
    assert B.detect_standing_crop(np.zeros(100, bool), np.zeros(100), 30.0) is None


@needs_owner
def test_crop_on_a_synthetic_get_up_followed_by_a_walk(sk):
    """A synthetic body: lying (torso flat), sitting up, standing, then walking 1.5 m. The crop is at standing."""
    n = 240
    ang = np.concatenate([np.full(60, -90.0), np.linspace(-90, 0, 60), np.zeros(120)])
    h = sk.rest_t[sk.index['Hips']]
    hips = np.tile(h, (n, 1))
    hips[:120, 1] -= 40                        # low while lying / rising
    hips[120:, 1] = h[1]
    hips[180:, 2] += np.linspace(0, 150, 60)   # walking forward after 6 s
    m = motion_with(sk, ang, 'Hips', (1, 0, 0), hips)
    c = B.detect_standing_crop(B.standing_mask(m), B.hips_speed(m), m.fps)
    assert c is not None
    assert 95 <= c['onset_frame'] <= 120                     # in the rise, not while lying
    assert c['walk_onset_frame'] is not None and c['crop_frame'] < c['walk_onset_frame'] <= 182
    cropped = m.slice(0, c['crop_frame'] + 1)
    assert B.root_path(cropped)['net_distance_cm'] < 5          # the 1.5 m walk is not carried


# ------------------------------------------------------------------ blend-window search, gap, root path
@needs_owner
def test_blend_window_search_finds_the_matching_frames_and_the_blend_closes_the_gap(sk):
    lie = motion_with(sk, np.linspace(0, 60, 91), 'Spine')                      # bends 0 -> 60 deg
    loop_ang = 30 + 5 * np.sin(np.linspace(0, 2 * np.pi, 61))                   # loops around 30 deg (last == first)
    loop = motion_with(sk, loop_ang, 'Spine')
    wake = motion_with(sk, np.linspace(32, 0, 81), 'Spine')
    n = 12
    res = B.search_chain(lie, loop, wake, n, lie_frames=range(len(lie) - n), wake_frames=range(len(wake) - n))
    c = res['chosen']
    lie_angle = 60 * c['lie_frame'] / 90
    assert abs(lie_angle - loop_ang[c['loop_phase_at_lie_blend_start']]) < 2.5
    assert c['lie']['pose_cm'] < 3 and c['wake']['pose_cm'] < 3
    direct = B.gap(lie, len(lie) - 1, loop, 0)
    assert direct['pose_cm'] > 10                                             # a direct cut is far off
    chain = B.build_chain(sk, lie, loop, wake, n, range(len(lie) - n), range(len(wake) - n))
    after = chain['after_blend']
    assert after['lie_down_end_vs_loop_start']['pose_cm'] < 1e-6             # seams exact after the blend
    assert after['loop_end_vs_get_up_start']['pose_cm'] < 1e-6
    assert chain['lie_to_loop']['plausible_blend'] and chain['loop_to_wake']['plausible_blend']
    whole = chain['_motions'][3]
    rp = B.root_path(whole, B.support_class(whole))
    assert not rp['discontinuity'] and rp['max_frame_step_cm'] < 1e-6


@needs_owner
def test_large_gap_and_posture_flip_are_refused_with_the_needed_transition(sk):
    supine = motion_with(sk, np.full(40, -90.0), 'Hips', (1, 0, 0))
    side = motion_with(sk, np.full(40, 90.0), 'Hips', (0, 0, 1))
    g = B.gap(supine, 39, side, 0)
    ok, why = B.verdict(g)
    assert not ok and any('posture' in r or 'attitude' in r for r in why)
    assert 'blend cannot bridge' in B.recommend('lie_to_loop', g)


@needs_owner
def test_root_path_flags_a_teleport(sk):
    h = sk.rest_t[sk.index['Hips']]
    hips = np.tile(h, (30, 1))
    hips[15:, 0] += 50                          # 50 cm in one frame
    rp = B.root_path(motion_with(sk, np.zeros(30), hips=hips))
    assert rp['discontinuity'] and rp['max_frame_step_cm'] >= 49.9


@needs_owner
def test_rigid_placement_recovers_yaw_and_offset(sk):
    m = motion_with(sk, np.linspace(0, 40, 10), 'Spine')
    placed = m.placed(math.radians(70), [12.0, -3.0, 40.0])
    th, off = B.fit_yaw_translation(placed.world()[0][5], m.world()[0][5], anchor=sk.index['Hips'])
    assert abs(math.degrees(th) - 70) < 1e-6
    assert np.allclose(off, [12.0, -3.0, 40.0], atol=1e-6)


# ------------------------------------------------------------------ provenance
def test_provenance_fields_are_required():
    good = {'source_used': 'x', 'source_sha256': {'x': 'ab'}, 'chain_documented': ['a'], 'not_documented': ['b'],
            'label': 'derived_library_asset', 'verdict': 'derived_library_asset: retargeted; capture method undocumented',
            'quotes': [{'file': 'f', 'present_verbatim': True}]}
    assert B.validate_provenance(good)
    for k in B.REQUIRED_PROVENANCE_FIELDS:
        bad = dict(good)
        bad.pop(k)
        with pytest.raises(ValueError):
            B.validate_provenance(bad)
    with pytest.raises(ValueError):
        B.validate_provenance({**good, 'quotes': [{'file': 'f', 'present_verbatim': False}]})
    with pytest.raises(ValueError):
        B.validate_provenance({**good, 'verdict': 'genuine Mixamo capture'})
    # The derived label is visible, never "mocap", never an unknown label.
    for verdict in ('derived_library_asset: mocap clip', 'derived_library_asset: motion capture of a performer',
                    'retargeted clip (derived_library_asset)'):
        with pytest.raises(ValueError):
            B.validate_provenance({**good, 'verdict': verdict})
    with pytest.raises(ValueError):
        B.validate_provenance({**good, 'label': 'mocap'})


def test_bed_sources_are_labelled_derived_library_assets_not_refused():
    for role in ('LieDown', 'GetUp'):
        assert B.PROVENANCE[role]['label'] == 'derived_library_asset'
        assert B.PROVENANCE[role]['verdict'].startswith('derived_library_asset')
        assert 'ProvenanceUnverified' not in B.PROVENANCE[role]['verdict']


def test_documented_quotes_are_verbatim_in_the_repository():
    rows = B.check_documented()
    missing = [r['file'] for r in rows if (ROOT / r['file']).is_file() and not r['present_verbatim']]
    assert not missing


# ------------------------------------------------------------------ bed surface audit helpers
def box_mattress(x0, x1, y0, y1, z0, z1):
    v = [[x, y, z] for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
    # 0..3 bottom, 4..7 top (x0y0, x1y0, x0y1, x1y1)
    tri = [4, 5, 7, 4, 7, 6,          # top (CCW from above: +z normal)
           0, 2, 3, 0, 3, 1,          # bottom (-z)
           0, 1, 5, 0, 5, 4, 2, 6, 7, 2, 7, 3, 0, 4, 6, 0, 6, 2, 1, 3, 7, 1, 7, 5]
    return v, tri


def test_mattress_top_selects_only_the_top_and_measures_area_and_axis():
    v, tri = box_mattress(0, 200, 0, 150, 38, 60)
    top = A.mattress_top(v, tri)
    assert len(top['triangle_indices']) == 2
    assert abs(top['area_cm2'] - 30000) < 1e-6
    assert abs(abs(top['long_axis_xy'][0]) - 1) < 1e-6 and top['length_cm'] == 200 and top['width_cm'] == 150
    assert A.head_end_direction(top, [[190, 75, 65]])[0] > 0.99


def test_mattress_top_refuses_a_pillow_sized_surface():
    v, tri = box_mattress(0, 70, 0, 50, 55, 70)
    with pytest.raises(ValueError, match='not a bed'):
        A.mattress_top(v, tri)


# ------------------------------------------------------------------ placement fitter
def flat_mattress(z=60.0, length=200.0, width=150.0, yaw_deg=0.0, cx=300.0, cy=-120.0):
    c, s = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    corners = [(-length / 2, -width / 2), (length / 2, -width / 2), (length / 2, width / 2), (-length / 2, width / 2)]
    w = [[cx + c * x - s * y, cy + s * x + c * y, z] for x, y in corners]
    return [w[0], w[1], w[2], w[0], w[2], w[3]]


def synthetic_lying_body():
    """A supine body in the component frame: lying along +right (Y), head at +Y, back at z = 0..2 cm."""
    gx, gy = np.meshgrid(np.linspace(-18, 18, 10), np.linspace(-10, 50, 16))
    torso = np.stack([gx.ravel(), gy.ravel(), 0.3 * np.abs(gx.ravel()) / 18], axis=1)
    lx, ly = np.meshgrid(np.linspace(-15, 15, 8), np.linspace(-95, -15, 20))
    legs = np.stack([lx.ravel(), ly.ravel(), 1.0 + 0.0 * lx.ravel()], axis=1)
    top = np.stack([gx.ravel(), gy.ravel(), 20 + 0 * gx.ravel()], axis=1)       # the front of the body
    body = np.concatenate([torso, legs, top])
    return body, {'torso_back': torso, 'posterior_legs': legs}, np.array([0.0, 80.0, 8.0]), np.array([0.0, 0.0, 10.0])


def test_fitter_places_the_back_patch_on_a_synthetic_mattress():
    body, patches, head, hips = synthetic_lying_body()
    tris = flat_mattress(yaw_deg=30.0)
    head_dir = [math.cos(math.radians(30)), math.sin(math.radians(30))]
    r = F.fit(body, patches, head, hips, tris, head_dir, start_hips=np.array([0.0, -40.0, 95.0]) + [100.0, 0, 0])
    assert r['accepted'] is False and r['native_bed_verified'] is False
    tr = r['transform']
    # the body long axis (+Y in the component frame) turned onto the mattress long axis (30 deg): yaw = -60 deg
    assert abs(((tr['yaw_deg'] + 60 + 180) % 360) - 180) < 1e-6
    for name, row in r['patches'].items():
        assert C.SEAT_BAND_CM[0] - 1e-9 <= row['min_gap_cm'] <= C.SEAT_BAND_CM[1] + 1e-9
        assert row['band_vertices'] >= C.MIN_SUPPORT_VERTICES
    assert r['body_min_gap_over_mattress_cm'] >= C.SEAT_BAND_CM[0] - 1e-9
    # the head top lands head_margin inside the head edge
    Rz = F.rotz(math.radians(tr['yaw_deg']))
    hw = Rz @ head + np.array(tr['translation_cm'])
    along = (hw[:2] - np.array(r['mattress']['centroid_cm'])) @ np.array(r['mattress']['long_axis_toward_head'])
    assert abs(along - (r["mattress"]["head_edge_cm"] - F.HEAD_MARGIN_CM)) < 1e-3
    assert r['proposal_ok'] and r['approach']['side'] in ('left', 'right')


def test_fitter_refuses_small_mattress_bump_and_overhang():
    body, patches, head, hips = synthetic_lying_body()
    small = flat_mattress(length=100, width=100)
    assert any('BedUnmeasured' in x for x in F.fit(body, patches, head, hips, small, [1, 0])['refusals'])
    # a 15 cm bump under the legs: the torso cannot touch while the legs rest -> the vertical range is empty
    tris = flat_mattress(cx=0, cy=0, yaw_deg=0)
    bump = [[-100, -75, 75.0], [-30, -75, 75.0], [-30, 75, 75.0], [-100, -75, 75.0], [-30, 75, 75.0], [-100, 75, 75.0]]
    r = F.fit(body, patches, head, hips, tris + bump, [1, 0])
    assert any('patches disagree' in x for x in r['refusals'])
    assert not r['proposal_ok'] and r['refusals']
    # a mattress shorter than the body: the legs overhang, reported
    r = F.fit(body, patches, head, hips, flat_mattress(length=120, width=130, cx=0, cy=0), [1, 0])
    assert r['overhang']['past_foot_edge_cm'] > 0 or r['overhang']['vertices_not_over_mattress'] > 0
    assert not r['proposal_ok']


def test_fitter_requires_a_head_end():
    body, patches, head, hips = synthetic_lying_body()
    r = F.fit(body, patches, head, hips, flat_mattress(), None)
    assert not r['proposal_ok'] and 'head end' in r['refusals'][0]


# ------------------------------------------------------------------ real data (skips when absent)
@pytest.mark.skipif(not (HAVE_NODE and HAVE_OWNER and HAVE_SOURCES), reason='node or repository clips absent')
def test_real_pipeline_on_repository_clips(tmp_path):
    pipe = B.run(tmp_path / 'out', tmp_path / 'work', OWNER, soles=True)
    for role in ('LieDown', 'GetUp'):
        rt = pipe['retarget'][role]
        assert rt['owner_residuals']['max_bone_length_deviation_cm'] < 1e-4
        assert rt['this_retarget_non_hips_translation_tracks']['non_hips_translation_tracks'] == 0
        assert rt['vs_drifted_mh_mx_copy']['copy_non_hips_translation_drift']['max_cm'] > 4.0
        assert rt['retarget_first_person_mjs']['checks']['sampledBoneLengthMaxError'] < 1e-5
        assert pipe['root_paths'][role]['discontinuity'] is False
    crop = pipe['crop']
    assert 11.5 <= crop['crop_s'] <= 13.0 and crop['walk_onset_s'] > crop['crop_s']
    assert pipe['get_up_end_checks']['standing']['pass']
    assert pipe['accepted'] is False
    assert all(q['present_verbatim'] for q in pipe['documented_quotes'])
    best = pipe['blend']['chains'][pipe['blend']['chosen_sleep_loop']]
    before = best['before_blend']['best_match_lie_to_loop_placed']['pose_cm']
    assert before > B.PLAUSIBLE_POSE_CM and not best['lie_to_loop']['plausible_blend']   # the measured gap is NOT hidden
    for role in ('LieDown', 'SleepLoop', 'GetUp'):
        rep = json.loads((tmp_path / 'out' / f'SUB01_{role}.report.json').read_text())
        assert rep['accepted_for_binding'] is False and rep['provenance']['quotes']
