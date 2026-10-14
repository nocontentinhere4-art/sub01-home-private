"""tools/leg_ik_life_clip.py: leg IK support, root support and seam blend on synthetic owner-like clips."""
import math
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import leg_ik_life_clip as K  # noqa: E402
import life_clip_synth as S  # noqa: E402
import life_gltf as G  # noqa: E402

BEND = math.radians(15)
LEG_CM = 40 + 42
DROP = LEG_CM * (1 - math.cos(BEND))          # hips drop that keeps bent legs on the floor


def bent_clip(hips_y, kink=False):
    clip = S.idle_clip()
    n = len(clip['times'])
    for side in ('Left', 'Right'):
        clip['rot'][side + 'UpLeg'] = [G.qaxis((1, 0, 0), BEND)] * n
        clip['rot'][side + 'Leg'] = [G.qaxis((1, 0, 0), -2 * BEND)] * n
        clip['rot'][side + 'Foot'] = [G.qaxis((1, 0, 0), BEND)] * n
    clip['trans']['Hips'] = [(0.0, hips_y, 0.0)] * n
    if kink:   # same start and end pose, opposite velocity: a seam tick
        T = clip['times'][-1]
        clip['rot']['LeftArm'] = [G.qaxis((0, 0, 1), math.radians(6) * math.sin(math.pi * t / T)) for t in clip['times']]
    return clip


def run(tmp_path, name, clip, blend='auto'):
    owner = tmp_path / 'owner.glb'
    if not owner.exists():
        S.build(owner)
    src = S.build(tmp_path / name, clip)
    out = tmp_path / ('ik_' + name)
    return src, out, K.run(src, out, owner, blend, work=tmp_path / 'w')


def frames_of(path):
    g = G.Gltf(path)
    return K.read_clip(g)[2]


def test_feet_already_on_the_floor_leave_the_clip_unchanged(tmp_path):
    src, out, r = run(tmp_path, 'on_floor.glb', bent_clip(92 - DROP + 0.01))
    assert r['labels'] == ['retargeted']
    a, b = frames_of(src), frames_of(out)
    assert len(a) == len(b) and all(fa == fb for fa, fb in zip(a, b))
    assert r['verification']['pass'] and r['support_patch']['pass']


def test_floating_feet_are_planted_without_stretch_or_upper_body_change(tmp_path):
    src, out, r = run(tmp_path, 'float.glb', bent_clip(92 - DROP / 2))
    assert 'leg_ik_support' in r['labels'] and 'root_support' not in r['labels']
    for side in ('Left', 'Right'):
        lo, hi = r['support_patch']['feet'][side]['lowest_cm']
        assert 0 <= lo and hi <= 0.002
    inv = r['verification']['invariants']
    assert inv['bone_length_constancy']['max_dev_from_owner_lengths_cm'] <= 1e-4
    assert r['upper_body']['upper_body_values_differing_outside_blend'] == 0
    assert r['upper_body']['world_hand_orientation_max_change_deg_outside_blend'] < 1e-6
    assert r['leg_ik']['foot_world_orientation_max_change_deg'] < 1e-3
    assert r['leg_ik']['knee_plane_max_change_deg'] < 1e-3          # the target moved straight down in the knee plane
    assert r['verification']['pass']


def test_penetrating_feet_are_raised_above_the_floor(tmp_path):
    _, _, r = run(tmp_path, 'sink.glb', bent_clip(92 - DROP - 1.0))
    assert 'leg_ik_support' in r['labels']
    assert r['leg_ik']['captured_lowest_plantar_cm']['Left'][0] == pytest.approx(-1.0, abs=0.01)
    soles = r['verification']['invariants']['soles']['feet']
    assert soles['left']['penetration_below_floor_cm'] == 0 and soles['right']['penetration_below_floor_cm'] == 0


def test_out_of_reach_gets_bounded_vertical_root_support_only(tmp_path):
    src, out, r = run(tmp_path, 'reach.glb', bent_clip(92.0))
    assert 'root_support' in r['labels']
    rs = r['leg_ik']['root_support_cm']
    assert 0 < rs['max'] <= K.MAX_ROOT_SUPPORT_CM and rs['vertical_only']
    g = G.Gltf(out)
    hips = g.by_name[S.P + 'Hips']
    for fa, fb in zip(frames_of(src), frames_of(out)):
        a, b = fa[(hips, 'translation')], fb[(hips, 'translation')]
        assert a[0] == b[0] and a[2] == b[2] and b[1] < a[1]          # never a horizontal move
    assert r['verification']['pass']


def test_seam_blend_makes_the_loop_continuous(tmp_path):
    _, out, r = run(tmp_path, 'kink.glb', bent_clip(92 - DROP + 0.01, kink=True))
    assert 'seam_blend' in r['labels']
    b = r['seam']['blend']
    assert not b['raw_seam']['passes'] and b['raw_seam']['velocity_cm_s'] > 5
    assert r['seam']['final']['passes'] and r['seam']['final']['pose_cm'] < 1e-4
    assert r['frames_out'] == r['frames_in'] - b['frames'] and b['frames'] == 12
    assert r['upper_body']['upper_body_values_differing_outside_blend'] == 0
    assert r['verification']['invariants']['loop']['pass']


def test_labels_are_in_the_glb_and_report(tmp_path):
    _, out, r = run(tmp_path, 'label.glb', bent_clip(92 - DROP / 2, kink=True))
    doc = G.Gltf(out).doc
    assert doc['asset']['extras']['sub01_labels'] == r['labels'] == doc['animations'][0]['extras']['sub01_labels']
    assert r['labels'][0] == 'retargeted' and {'seam_blend', 'leg_ik_support'} <= set(r['labels'])
    assert Path(str(out) + '.report.json').is_file()


def test_two_bone_keeps_lengths_and_plane():
    H, K0, A0 = (0.0, 1.0, 0.0), (0.0, 0.6, 0.1), (0.0, 0.2, 0.0)
    a, b = G.vlen(G.vsub(K0, H)), G.vlen(G.vsub(A0, K0))
    T = (0.0, 0.25, 0.0)
    knee = K.two_bone(H, K0, A0, T, a, b)
    assert G.vlen(G.vsub(knee, H)) == pytest.approx(a) and G.vlen(G.vsub(T, knee)) == pytest.approx(b)
    assert knee[0] == pytest.approx(0) and knee[2] > 0                   # same plane, same side
    with pytest.raises(ValueError):
        K.two_bone(H, K0, A0, (0.0, -1.0, 0.0), a, b)


def test_real_ual_retarget_is_corrected(tmp_path):
    owner = ROOT / 'web/room/char_mixamo.glb'
    if not (owner.is_file() and (ROOT / 'web/room/boy_moves.glb').is_file() and shutil.which('node')):
        pytest.skip('repository files or node absent')
    import retarget_life_clip as R
    raw = tmp_path / 'ual.glb'
    R.retarget(ROOT / 'web/room/boy_moves.glb', raw, 'ual_boy', animation='stand_idle', owner_path=owner, work=tmp_path / 'w')
    r = K.run(raw, tmp_path / 'ual_ik.glb', owner, work=tmp_path / 'w', raw_report=Path(str(raw) + '.report.json'))
    assert r['labels'] == ['retargeted', 'seam_blend', 'leg_ik_support', 'root_support']
    assert r['verification']['pass'] and r['support_patch']['pass']
    assert r['raw_vs_corrected']['failed']['raw'] == ['feet_joints', 'loop', 'soles']
    assert r['upper_body']['upper_body_values_differing_outside_blend'] == 0
    assert r['leg_ik']['root_support_cm']['max'] <= K.MAX_ROOT_SUPPORT_CM
