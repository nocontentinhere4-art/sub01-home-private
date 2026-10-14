"""Bed corrections: slide hold, ease-in, settle, loop, derived label in the inventory, mesh root motion fragment."""
from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import bed_transition_corrections as C  # noqa: E402
import bed_transition_pipeline as B  # noqa: E402
import fit_bed_placement as F  # noqa: E402
import inventory_native_life_clips as inv  # noqa: E402
import unreal_bed_root_motion as RM  # noqa: E402
import unreal_bed_surface_audit as A  # noqa: E402
import unreal_life_clips_runtime as life  # noqa: E402
from stage_unreal_home_runtime import stage  # noqa: E402

OWNER = ROOT / 'web/room/char_mixamo.glb'
HAVE_OWNER = OWNER.is_file()
HAVE_NODE = shutil.which('node') is not None
HAVE_SOURCES = all(p.is_file() for p in [*B.SOURCES.values(), *C.ALTERNATIVE_LOOPS.values()])
COMMITTED = ROOT / 'docs/proposed/bed-transition'


@pytest.fixture(scope='module')
def sk():
    if not HAVE_OWNER:
        pytest.skip('owner skin absent')
    return B.Skeleton(OWNER)


def rest_motion(sk, frames, hips=None):
    q = np.broadcast_to(sk.rest_q, (frames,) + sk.rest_q.shape).copy()
    t = np.broadcast_to(sk.rest_t[sk.index['Hips']], (frames, 3)).copy() if hips is None else np.asarray(hips, float)
    return B.Motion(sk, q, t)


# ------------------------------------------------------------------ slide hold
def test_slide_hold_keeps_the_hips_still_inside_and_offsets_after(sk):
    n = 90
    hips = np.broadcast_to(sk.rest_t[sk.index['Hips']], (n, 3)).copy()
    x = np.zeros(n)
    x[30:60] = np.linspace(0, 79, 30)          # a 79 cm run in one second
    x[60:] = 79
    hips[:, 2] += x
    m = rest_motion(sk, n, hips)
    fixed, removed = C.remove_seated_slide(m, {'start_frame': 30, 'end_frame': 59})
    assert np.allclose(fixed.q, m.q)                                  # rotations untouched
    assert np.allclose(fixed.t[:, 1], m.t[:, 1])                      # vertical untouched
    assert abs(fixed.t[-1, 2] - fixed.t[0, 2]) < 0.5                  # the 79 cm are gone
    assert np.linalg.norm(removed[-1]) == pytest.approx(79, abs=0.5)
    step = np.abs(np.diff(fixed.t[:, 2]))
    assert step.max() < 1.5                                           # no step introduced (smoothed edges)


def test_detect_seated_slide_needs_a_fast_non_standing_run(sk):
    m = rest_motion(sk, 40)
    assert C.detect_seated_slide(m) is None                           # standing still: nothing to remove


# ------------------------------------------------------------------ ease-in
def test_ease_in_starts_from_rest_and_keeps_captured_poses(sk):
    n = 60
    hips = np.broadcast_to(sk.rest_t[sk.index['Hips']], (n, 3)).copy()
    hips[:, 2] += np.arange(n) * 2.0                                  # 60 cm/s walk
    m = rest_motion(sk, n, hips)
    e, src = C.ease_in(m, 10, 0.5)
    v = np.diff(e.t[:, 2]) * 30
    assert v[0] < 2.5 and v[-1] == pytest.approx(60, abs=1e-6)        # starts ~0, ends at the captured speed
    assert np.all(np.diff(src) >= 0) and src[0] == 10 and src[-1] <= n - 1
    assert np.allclose(e.t[0], m.t[10])


# ------------------------------------------------------------------ settle and loop
def test_settle_holds_both_ends_on_captured_poses(sk):
    lie = rest_motion(sk, 30)
    loop = rest_motion(sk, 21)
    loop.q = loop.q.copy()
    k = sk.index['RightArm']
    for f in range(21):
        loop.q[f, k] = B.qmul(sk.rest_q[k], B.yaw_quat(0.2 + 0.01 * f))
    q, t = C.settle(lie, 5, loop, 3, 30)
    assert np.allclose(q[0], lie.q[5]) and np.allclose(q[-1], loop.q[(3 + 30) % 20], atol=1e-9)
    w = C.smootherstep(np.array([0, 1 / 30, 29 / 30, 1]))
    assert w[1] < 1e-3 and 1 - w[2] < 1e-3                            # C2 ends: no velocity jump


def test_loop_closes_exactly(sk):
    n = 50
    m = rest_motion(sk, n)
    m.q = m.q.copy()
    k = sk.index['Spine']
    for f in range(n):
        m.q[f, k] = B.qmul(sk.rest_q[k], B.yaw_quat(0.05 * np.sin(f / 7)))
    loop, src = C.make_loop(m, 45, 12)
    assert np.allclose(loop.q[0], loop.q[-1], atol=1e-6) and np.allclose(loop.t[0], loop.t[-1])
    assert len(loop) == 45 - 12 + 1 and 'partner' in src[-1]


# ------------------------------------------------------------------ derived label in the inventory
def labelled_copy(src: Path, dst: Path, label='derived_library_asset'):
    doc, binary, _ = inv.read_glb(src)
    if label:
        doc.setdefault('asset', {}).setdefault('extras', {})['sub01_provenance'] = {'label': label, 'text': 'test'}
    import life_gltf as G
    G.write_glb(dst, doc, binary)
    return dst


@pytest.mark.skipif(not HAVE_OWNER, reason='owner skin absent')
def test_derived_library_asset_is_a_candidate_only_with_its_label_visible(tmp_path):
    src = ROOT / 'web/room/desk_states/bed/sleep_back.glb'
    good = labelled_copy(src, tmp_path / 'labelled.glb')
    bare = labelled_copy(src, tmp_path / 'bare.glb', label=None)
    wrong = labelled_copy(src, tmp_path / 'wrong.glb', label='mocap')
    report = inv.inventory(derived=[('SleepLoop', str(good)), ('SleepLoop', str(bare)), ('SleepLoop', str(wrong))])
    rows = {Path(r['file']).name: r for r in report['candidates'] if r['provenance'] == 'derived_library_asset'}
    assert rows['labelled.glb']['verdict'] == 'Candidate'
    assert rows['labelled.glb']['verdict_reason'].startswith('derived_library_asset (label visible; not a capture)')
    assert rows['labelled.glb']['provenance_label']['label'] == 'derived_library_asset'
    assert rows['bare.glb']['verdict'] == 'ProvenanceLabelMissing'
    assert rows['wrong.glb']['verdict'] == 'ProvenanceLabelMissing'
    assert 'derived_library_asset' not in report['accepted_provenance']    # never a "capture" class
    # The default inventory is unchanged by the additive option.
    plain = inv.inventory()
    assert all(r['provenance'] != 'derived_library_asset' for r in plain['candidates'])


def test_config_shows_the_derived_label_and_refuses_a_hidden_one():
    rows, clips = [], []
    for role, loops in (('LieDown', False), ('SleepLoop', True), ('GetUp', False)):
        sha = role[0].lower() * 64
        rows.append({'role': role, 'file': f'docs/proposed/bed-transition/SUB01_{role}.corrected.in_place.glb', 'sha256': sha,
                     'verdict': 'Candidate', 'provenance': 'derived_library_asset',
                     'provenance_label': {'label': 'derived_library_asset'}, 'skeleton': {'same_owner_skeleton': True},
                     'loop': {'loops': loops}, 'duration_s': 4.0})
        clips.append({'role': role, 'object_path': life.clip_object_path(role), 'inventory_sha256': sha,
                      'same_existing_skeleton': True, 'duration_s': 4.0})
    text, refusals = RM.config_with_labels({'candidates': rows}, {'clips': clips})
    assert '+ValidatedHandsPostures=LieDown' in text and '+ValidatedHandsPostures=GetUp' in text
    assert text.count('; SUB01 provenance ') == 3 and 'derived_library_asset' in text and 'mocap' not in text
    rows[0]['provenance_label'] = None
    with pytest.raises(ValueError, match='visible label'):
        RM.config_with_labels({'candidates': rows}, {'clips': clips})


def test_root_path_staging_refuses_unbound_or_other_clips():
    rows, clips = [], []
    for role, loops in (('LieDown', False), ('SleepLoop', True), ('GetUp', False)):
        sha = role[0].lower() * 64
        rows.append({'role': role, 'file': role, 'sha256': sha, 'verdict': 'Candidate', 'skeleton': {'same_owner_skeleton': True},
                     'loop': {'loops': loops}, 'duration_s': 4.0})
        clips.append({'role': role, 'object_path': life.clip_object_path(role), 'inventory_sha256': sha,
                      'same_existing_skeleton': True, 'duration_s': 4.0})
    paths = {'schema': RM.ROOT_PATH_SCHEMA, 'fps': 30.0,
             'roles': {r: {'clip_sha256_in_place': r[0].lower() * 64, 'forward_cm': [0, 1], 'right_cm': [0, 0]}
                       for r in life.BED_ROLES}}
    ok = RM.validate_paths(paths, {'candidates': rows}, {'clips': clips})
    assert set(ok['roles']) == set(life.BED_ROLES)
    other = json.loads(json.dumps(paths))
    other['roles']['GetUp']['clip_sha256_in_place'] = 'f' * 64
    with pytest.raises(ValueError, match='another clip'):
        RM.validate_paths(other, {'candidates': rows}, {'clips': clips})
    with pytest.raises(ValueError, match='not bound'):
        RM.validate_paths(paths, {'candidates': rows}, {'clips': clips[:2]})


# ------------------------------------------------------------------ duvet support
def test_duvet_top_is_measured_or_reasoned_and_the_fitter_can_use_it():
    verts = [[0, 0, 65], [150, 0, 66], [150, 200, 67], [0, 200, 66]]
    top, why = A.duvet_top(verts, [0, 1, 2, 0, 2, 3])
    assert why is None and top['area_cm2'] == pytest.approx(30000, rel=0.01)
    none, why = A.duvet_top([[0, 0, 0], [0, 1, 0], [0, 0, 1]], [0, 1, 2])
    assert none is None and why
    bed = {'errors': [], 'bed': {'sections': []},
           'duvet_sections': [{'vertices_world_cm': verts, 'triangles': [0, 1, 2, 0, 2, 3], 'top_surface': top}]}
    assert len(F.support_triangles(bed, 'duvet')) == 6
    with pytest.raises(ValueError, match='BedUnmeasured'):
        F.support_triangles({'errors': [], 'bed': {'sections': []}, 'duvet_sections': []}, 'duvet')


# ------------------------------------------------------------------ mesh root motion fragment on staged sources
NAMES = ('Sub01HomeLab.h', 'Sub01HomeLab.cpp', 'Sub01HomeHands.h', 'Sub01HomeHands.cpp')


def staged(order=('life', 'root')):
    tmp = tempfile.TemporaryDirectory()
    project = Path(tmp.name)
    (project / 'Config').mkdir()
    (project / 'Sub01HomeLab.uproject').write_text('{}')
    stage(project)
    module = project / 'Source/Sub01HomeLab'
    before = {n: (module / n).read_text() for n in NAMES}
    for name in order:
        if name == 'seat':
            import unreal_seat_transition_runtime as seat
            seat.install_module(module)
        elif name == 'life':
            life.install_module(module)
        else:
            RM.install_module(module)
    return tmp, module, before, {n: (module / n).read_text() for n in NAMES}


@pytest.fixture(scope='module')
def installed():
    tmp, module, before, after = staged(('life',))
    life_only = dict(after)
    RM.install_module(module)
    yield module, life_only, {n: (module / n).read_text() for n in NAMES}
    tmp.cleanup()


def test_root_motion_needs_the_life_adapter_and_installs_once(installed):
    module, life_only, after = installed
    tmp, _, before, _ = staged(())
    try:
        plain = {k: before[n] for k, n in life.SOURCE_FILES.items()}
        with pytest.raises(ValueError, match='life_clips_runtime first'):
            RM.install(plain)
    finally:
        tmp.cleanup()
    with pytest.raises(ValueError, match='already installed'):
        RM.install({k: after[n] for k, n in life.SOURCE_FILES.items()})
    for key, anchor, _ in RM.EDITS:
        broken = {k: life_only[n] for k, n in life.SOURCE_FILES.items()}
        broken[key] = broken[key].replace(anchor, '')
        with pytest.raises(ValueError, match='anchor not unique|life_clips_runtime first'):
            RM.install(broken)


def test_root_motion_hooks_the_bed_phases_in_order(installed):
    _, life_only, after = installed
    h, cpp = after['Sub01HomeLab.h'], after['Sub01HomeLab.cpp']
    assert h.index('void LoadLifeRootPath();') < h.index('FSub01LifeMachine LifeMachine;')
    load = cpp.split('void ASub01HomeCharacter::LoadLifeClips(){', 1)[1].split('\n}\n', 1)[0]
    assert load.index('LoadLifeRootPath();') < load.index('SUB01_LIFE_READY')
    update = cpp.split('void ASub01HomeCharacter::UpdateLifeClips(', 1)[1].split('\n}\n', 1)[0]
    assert update.index('DisableMovement();LifeMovementDisabled=true;') < update.index('UpdateLifeRootMotion(Instance);') \
        < update.index('// In bed the eye follows the captured Head bone;')
    assert RM.LOCK_NEW in cpp and RM.LOCK_OLD not in cpp
    assert RM.GATE_NEW in cpp and RM.GATE_OLD not in cpp
    # Everything else the life adapter added is still there, line for line.
    for name, text in life_only.items():
        for line in (l for l in text.splitlines() if l.strip()):
            if line.strip() in (RM.LOCK_OLD.strip(),) or RM.GATE_OLD.strip() in line:
                continue
            assert line in after[name], line


def test_root_motion_moves_the_mesh_never_the_actor():
    code = RM.FIELDS + RM.methods()
    for forbidden in ('SetActorLocation', 'Teleport', 'SetWorldLocation', 'SetActorTransform', 'SetActorRotation',
                      'MoveUpdatedComponent', 'SetBoneLocation', 'SetBoneRotation', 'SetBoneTransform', 'AttachToComponent',
                      'SetRelativeRotation', 'HandsClips.Add', 'ValidatedHandsPostures.Add', 'SetControlRotation'):
        assert forbidden not in code, forbidden
    methods = RM.methods()
    # The mesh offset is the only placement: root path relative to the capsule, on top of the renderer's offset.
    assert re.findall(r'FirstPersonBody->SetRelativeLocation\(([^;]*)\);', methods) == ['HandsBaseOffset+LifeRootAbsorbOffset*Keep',
                                                                                         'HandsBaseOffset+Offset', 'HandsBaseOffset']
    # The capsule moves only by CharacterMovement input, toward the get-up's measured end, while he is asleep or after.
    assert methods.count('AddMovementInput(') == 1
    assert 'const bool MayReturn=LifeOut.Phase==ESub01LifePhase::Asleep||LifeOut.Phase==ESub01LifePhase::GettingUp||!InBed;' in methods
    # Time is what the proxy evaluated, not the requested time; the body must sit on the capsule.
    assert 'Instance->LifeEvaluatedSequence==Clip&&Instance->LifeEvaluatedTime>=0' in methods
    assert 'FirstPersonBody->GetAttachParent()==GetRootComponent()' in methods
    # A blocked return is logged and never snapped.
    assert 'SUB01_LIFE_ROOT_RETURN_BLOCKED' in methods and 'the body stays where it is' in methods
    # A short residual (capsule stopped by the bed) decays only with distance actually walked, bounded.
    assert f'ToTarget.Size()<={RM.RESIDUAL_MAX_CM:.1f}f' in methods
    assert f'1.f-LifeRootWalked/{RM.ABSORB_CM:.1f}f' in methods and '@@' not in methods
    # The path must match the imported clips' lengths.
    assert 'Clip->GetPlayLength()-(Path.Num()-1)/LifeRootFps' in methods


@pytest.mark.parametrize('order', [('seat', 'life', 'root'), ('life', 'root', 'seat'), ('life', 'seat', 'root')])
def test_root_motion_coexists_with_the_seat_adapter(order):
    tmp, module, before, after = staged(order)
    try:
        cpp = after['Sub01HomeLab.cpp']
        assert cpp.count('UpdateLifeRootMotion(Instance);') == 1 and cpp.count('UpdateLifeClips(Instance,DeltaSeconds);') == 1
        assert cpp.count('ApplySeatAnimation(Instance);') == 1
    finally:
        tmp.cleanup()


# ------------------------------------------------------------------ committed outputs
def test_committed_outputs_carry_the_label_and_stay_small():
    if not (COMMITTED / 'SUB01_LieDown.corrected.report.json').is_file():
        pytest.skip('outputs not committed')
    for role in ('LieDown', 'SleepLoop', 'GetUp'):
        rep = json.loads((COMMITTED / f'SUB01_{role}.corrected.report.json').read_text())
        assert rep['provenance_label'] == 'derived_library_asset' and rep['accepted_for_binding'] is False
        assert rep['native_bed_verified'] is False and rep['documented_quotes']
        for var in ('in_place', 'travel_in_hips'):
            path = ROOT / rep['outputs'][var]['path']
            assert path.stat().st_size < 2_000_000
            doc, _, sha = inv.read_glb(path)
            assert sha == rep['outputs'][var]['sha256']
            assert doc['asset']['extras']['sub01_provenance']['label'] == 'derived_library_asset'
            assert 'mocap' not in json.dumps(doc['asset']['extras']).lower()


# ------------------------------------------------------------------ real data (skips when absent)
@pytest.fixture(scope='module')
def real(tmp_path_factory):
    if not (HAVE_NODE and HAVE_OWNER and HAVE_SOURCES):
        pytest.skip('node or repository clips absent')
    out = tmp_path_factory.mktemp('bed')
    reports, summary = C.run(out / 'out', out / 'work')
    return out / 'out', reports, summary


def test_real_get_up_slide_is_removed(real):
    _, reports, _ = real
    slide = reports['GetUp']['seated_slide']
    assert slide['root_path_to_crop']['raw']['max_speed_cm_s'] > 150
    assert slide['root_path_to_crop']['corrected']['max_speed_cm_s'] < 70
    assert slide['root_path_to_crop']['corrected']['max_acceleration_cm_s2'] < 400
    assert slide['root_path_to_crop']['corrected']['max_frame_step_cm'] < 2.5
    g = slide['geometry_check']
    assert abs(g['get_up_lying_start_to_seat_cm_corrected'] - g['lie_down_seat_to_lying_end_cm']) < 10


def test_real_contact_handoff_and_settle(real):
    _, reports, summary = real
    assert all(summary['contact'][k] for k in ('LieDown_corrected', 'GetUp_corrected'))
    assert not summary['contact']['GetUp_raw_end'] and not summary['contact']['LieDown_raw']
    for role in ('LieDown', 'GetUp'):
        c = reports[role]['foot_contact']['corrected']
        for side in ('Left', 'Right'):
            assert c[side]['lowest_cm'][0] >= 0 and c[side]['lowest_cm'][1] <= 1 and c[side]['min_band_vertices'] >= 12
        assert reports[role]['foot_contact']['leg_ik']['root_support_cm']['max'] <= 3.0
    h = reports['LieDown']['walk_in_handoff']
    assert h['raw_start_hips_speed_cm_s'] > 15 and h['corrected_start_hips_speed_cm_s'] < 5
    s = summary['continuity']
    assert s['settle']['peak_joint_speed_hips_relative_cm_s'] < C.TARGET_JOINT_SPEED_CM_S
    assert s['lie_down_end_vs_loop_start']['pose_cm'] < 1e-6 and s['loop_end_vs_get_up_start']['pose_cm'] < 1e-6
    alt = reports['SleepLoop']['alternatives_measured']['sova_sleep_back']
    assert alt['lie_side_2.5s']['peak_joint_speed_hips_relative_cm_s'] > s['settle']['peak_joint_speed_hips_relative_cm_s']


def test_real_outputs_become_labelled_inventory_candidates(real):
    out, reports, _ = real
    derived = [(role, str(ROOT / reports[role]['outputs']['in_place']['path']) if not Path(reports[role]['outputs']['in_place']['path']).is_absolute()
                else reports[role]['outputs']['in_place']['path']) for role in ('LieDown', 'SleepLoop', 'GetUp')]
    report = inv.inventory(derived=derived)
    rows = [r for r in report['candidates'] if r['provenance'] == 'derived_library_asset']
    assert len(rows) == 3
    for r in rows:
        assert r['verdict'] == 'Candidate', (r['role'], r['verdict'], r.get('verdict_reason'))
        assert r['verdict_reason'].startswith('derived_library_asset (label visible')
