"""TRIAL controller grip solver and sofa controller-play adapter (verified: false everywhere).

Synthetic hands/controller check the support patch, collision, solver and drift; real-data checks run only
when the actual files exist; the native adapter installs against stage_unreal_home_runtime.stage().
"""
import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import fit_controller_grip as F  # noqa: E402
import unreal_controller_play_runtime as play  # noqa: E402
from stage_unreal_home_runtime import stage  # noqa: E402

GAMING = ROOT / 'docs/proposed/controller-capture/gaming-owner.glb'


# ---------------------------------------------------------------- synthetic controller and hands
def box(lo, hi):
    lo, hi = np.array(lo, float), np.array(hi, float)
    V = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    F_ = []
    for a, b, c, d in quads:
        F_ += [(a, b, c), (a, c, d)]
    m = F.Mesh(V, F_)
    # orient outward
    out = []
    for t in m.F:
        n = np.cross(V[t[1]] - V[t[0]], V[t[2]] - V[t[0]])
        out.append(t if n @ (V[t].mean(0) - (lo + hi) / 2) > 0 else t[::-1])
    return F.Mesh(V, out)


HX, HY, HZ = .075, .028, .05
LO, HI = (-HX, 0, -HZ), (HX, 2 * HY, HZ)


def features():
    grips = {}
    for side, s in (('left', -1), ('right', 1)):
        a, b = np.array([s * (HX - .012), .045, -.005]), np.array([s * (HX - .012), .012, .04])
        grips[side] = {'axis': (a, b), 'centre': (a + b) / 2}
    return {'sticks': {'left': np.array([-.033, 2 * HY, -.012]), 'right': np.array([.017, 2 * HY, .01])},
            'face_buttons': np.array([.033, 2 * HY, -.012]),
            'triggers': {'left': np.array([-.045, .03, -HZ]), 'right': np.array([.045, .03, -HZ])}, 'grips': grips}


def local_hands(gap=.001):
    """Hand point sets in the controller frame: palms on the side faces, thumbs over sticks, index on triggers."""
    yy, zz = np.meshgrid(np.linspace(.012, .044, 5), np.linspace(-.005, .04, 5))
    sets = {}
    feats = features()
    for side, s in (('left', -1), ('right', 1)):
        palm = np.stack([np.full(yy.size, s * (HX + gap)), yy.ravel(), zz.ravel()], 1)
        thumb_target = feats['sticks'][side] if side == 'left' else feats['face_buttons']
        thumb = thumb_target + np.array([[0, .004, 0], [.003, .005, 0], [-.003, .005, 0]])
        index = feats['triggers'][side] + np.array([[0, 0, -.004], [.003, 0, -.005], [-.003, 0, -.005]])
        back = palm + np.array([s * .025, 0, 0])
        sets[f'{side}_palm'], sets[f'{side}_thumb'], sets[f'{side}_index'] = palm, thumb, index
        sets[f'{side}_hand'] = np.concatenate([palm, thumb, index, back])
    return sets


def frames(n=4, seed=1):
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        m = F.pose(np.concatenate([rng.normal(0, .6, 3), rng.normal(0, .2, 3)]))
        out.append(m)
    return np.stack(out)


X_TRUE = F.pose(np.array([.3, -.2, .5, .02, .08, -.03]))


def world_sets(right, X=X_TRUE, drift=None):
    loc = local_hands()
    sets = {}
    for k, P in loc.items():
        rows = []
        for f in range(len(right)):
            Q = P + (drift[f] if (drift is not None and k.startswith('left')) else 0)
            rows.append(F.apply(right[f] @ X, Q))
        sets[k] = np.stack(rows)
    return sets


@pytest.fixture(scope='module')
def mesh():
    return box(LO, HI)


def test_exact_distance_and_winding_match_brute_force_and_box_geometry(mesh):
    P = np.random.default_rng(3).uniform(np.array(LO) - .02, np.array(HI) + .02, (400, 3))
    d, _ = mesh.distance(P)
    d0, _ = mesh.distance_brute(P)
    assert np.allclose(d, d0)
    inside = np.all((P > LO) & (P < HI), axis=1)
    assert np.array_equal(np.abs(mesh.winding(P)) > .5, inside)
    sd = mesh.signed_distance(P, margin=1)
    depth = np.minimum(P - LO, HI - P).min(1)
    assert np.allclose(sd[inside], -depth[inside], atol=1e-9)
    assert mesh.boundary_edges() == (0, 0)


def test_support_patch_and_clean_hands_at_the_true_grip(mesh):
    right = frames()
    prob = F.Problem(mesh, features(), right, world_sets(right))
    for f in range(len(right)):
        row = prob.metrics(right[f] @ X_TRUE, f)
        for side in ('left', 'right'):
            assert row[side]['palm_support_patch'] and row[side]['palm_band_vertices'] == 25
            assert row[side]['palm_min_gap_cm'] == pytest.approx(.1, abs=1e-6)
            assert row[side]['hand_vertices_penetrating'] == 0
            assert row[side]['index_to_trigger_cm'] < 1
        assert row['right']['thumb_to_target_cm']['face_buttons'] < 1 and row['left']['thumb_to_target_cm']['stick'] < 1
        assert row['grip']


def test_collision_is_reported_per_vertex_when_the_controller_is_pushed_into_a_hand(mesh):
    right = frames(2)
    prob = F.Problem(mesh, features(), right, world_sets(right))
    shifted = X_TRUE @ F.pose(np.array([0, 0, 0, .02, 0, 0]))       # 2 cm toward the right palm
    row = prob.metrics(right[0] @ shifted, 0)
    assert row['right']['hand_vertices_penetrating'] == 25 and row['right']['hand_min_signed_cm'] == pytest.approx(-1.9, abs=1e-6)
    assert not row['right']['palm_support_patch'] and not row['grip']
    assert not row['left']['palm_support_patch']                      # the left palm is now 2 cm off its grip


def test_fixed_solver_recovers_a_two_hand_grip_from_a_perturbed_start(mesh):
    right = frames(3)
    prob = F.Problem(mesh, features(), right, world_sets(right), sub=1)
    X0 = X_TRUE @ F.pose(np.array([.05, -.04, .03, .006, -.004, .005]))
    assert not all(prob.metrics(right[f] @ X0, f)['grip'] for f in range(3))
    X, _ = F.solve_fixed(prob, X0, [0, 1, 2], iters=500)
    rows = [prob.metrics(right[f] @ X, f) for f in range(3)]
    assert all(r['grip'] for r in rows), [(r['left']['palm_min_gap_cm'], r['right']['palm_min_gap_cm']) for r in rows]


def test_drift_between_the_hands_is_measured_and_a_fixed_controller_cannot_hold_it(mesh):
    right = frames(5)
    drift = [np.array([-.006 * f, 0, 0]) for f in range(5)]          # the left hand opens 0..2.4 cm away
    L = F.pose(np.array([0, 0, 0, -.1, .02, .01]))
    left = np.stack([right[f] @ X_TRUE @ F.pose(np.concatenate([[0, 0, 0], drift[f]])) @ L for f in range(5)])
    d = F.hand_drift(right, left)
    assert d['translation_from_mean_cm']['max'] == pytest.approx(1.2, abs=1e-6)
    assert d['rotation_from_mean_deg']['max'] < 1e-4
    prob = F.Problem(mesh, features(), right, world_sets(right, drift=drift))
    rows = [prob.metrics(right[f] @ X_TRUE, f) for f in range(5)]
    assert [r['left']['palm_support_patch'] for r in rows] == [True, False, False, False, False]
    s = F.summarise(rows)
    assert s['frames_full_grip'] == 1 and s['left']['palm_min_gap_cm'][1] == pytest.approx(2.5, abs=1e-6)


def test_two_bone_ik_keeps_lengths_and_reports_unreachable_residual():
    s, e, w = np.zeros(3), np.array([.28, -.05, 0]), np.array([.5, .05, .05])
    target = w + np.array([-.04, .02, .03])
    new_e, ok, dang, err = F.two_bone_ik(s, e, w, target)
    assert ok and err < 1e-9
    assert np.linalg.norm(new_e - s) == pytest.approx(np.linalg.norm(e - s))
    assert np.linalg.norm(target - new_e) == pytest.approx(np.linalg.norm(w - e))
    _, ok, _, err = F.two_bone_ik(s, e, w, np.array([2., 0, 0]))
    assert not ok and err > 1


def test_kabsch_and_rotvec_roundtrip():
    P = np.random.default_rng(0).normal(size=(6, 3))
    assert np.allclose(F.kabsch(P, F.apply(X_TRUE, P)), X_TRUE)
    assert np.allclose(F.pose(F.params_of(X_TRUE)), X_TRUE)


# ---------------------------------------------------------------- real data (skipped when absent)
needs_controller = pytest.mark.skipif(not F.CONTROLLER.exists(), reason='controller.glb absent')


@needs_controller
def test_actual_controller_mesh_bounds_licence_and_contact_shadow_excluded():
    r = F.controller_report()
    assert r['sha256'] == 'c034a1444711a44f0726e7264b1e2e2b47b1bbdba0e5dd615eef27001a4717e4'
    assert r['excluded_primitives'] == ['controller_contact'] and r['triangles'] == 13848 and r['vertices'] == 7297
    assert r['size_cm'] == pytest.approx([15.380, 5.586, 10.365], abs=.01)
    assert r['nonmanifold_edges'] == 0 and r['boundary_edges'] > 0 and r['closed'] is False
    assert 'CC0' in r['licence'] and r['verified'] is False
    assert r['stick_authoring_error_mm'] < .01
    assert r['sticks_m']['left'][1] == pytest.approx(r['sticks_m']['right'][1])


@needs_controller
def test_actual_controller_grouped_distance_equals_brute_force():
    m, _ = F.load_controller()
    P = np.random.default_rng(5).uniform(m.lo - .01, m.hi + .01, (150, 3))
    assert np.allclose(m.distance(P)[0], m.distance_brute(P)[0])
    assert np.array_equal(np.abs(m.winding(P)) > .5, np.abs(m.winding_brute(P)) > .5)


@pytest.mark.skipif(not F.SOFA.exists(), reason='sofa source absent')
def test_authored_sofa_seat_and_capsule_clearance_are_source_only():
    r = F.sofa_seat()
    assert r['native_measurement'] is None and r['verified'] is False
    assert len(r['seat_cushions']) == 2 and all(c['top_cm'] == pytest.approx(50.3, abs=.01) for c in r['seat_cushions'])
    assert r['standing_capsule_at_sofa_node']['horizontal_clearance_cm'] == pytest.approx(11.75, abs=.01)


@pytest.mark.skipif(not GAMING.exists(), reason='private retargeted Gaming clip absent')
def test_actual_gaming_capture_is_seated_and_its_wrists_are_wider_than_the_controller():
    hands = F.Hands.from_owner()
    worlds, times, info = F.clip_worlds(GAMING, hands.names, rate=None)
    assert info['frames_sampled'] == 152 and info['audit']['output_sha256_matches_clip']
    assert info['duration_s'] == pytest.approx(5.0333, abs=1e-3)
    assert F.seated_metrics(worlds, hands.names)['seated'] is True
    J = {n: k for k, n in enumerate(hands.names)}
    gap = np.linalg.norm(worlds[:, J['LeftHand'], :3, 3] - worlds[:, J['RightHand'], :3, 3], axis=1) * 100
    assert 27 < gap.min() and gap.max() < 31          # measured 28.3..29.1 cm; the controller is 15.38 cm wide
    # Parity with root's FK of the same GLB at t = 4 s (glTF cm), within 0.01 cm.
    parity = F.fk_parity(GAMING, hands.names)
    assert parity['within_0_01_cm'], parity
    w4, _, _ = F.clip_worlds(GAMING, hands.names, times=[4.0])
    assert np.allclose(100 * w4[0, J['LeftHand'], :3, 3], [20.1514, 88.0128, 50.2592], atol=.01)
    amp = F.finger_motion(GAMING, hands.names, times)
    assert any(v > 1 for k, v in amp.items() if 'Thumb' in k)


# ---------------------------------------------------------------- adapter gates
def sofa_text():
    v = [[-220, -80, 50], [-155, -80, 50], [-155, 100, 50], [-220, 100, 50]]
    return json.dumps({'errors': [], 'sofa': {'sections': [{'vertices_world_cm': v, 'seat_surface': {'triangle_indices': [[0, 1, 2], [0, 2, 3]]}}]}})


def grip_report(ok=True, **override):
    """A derived grip clip report (what native play needs)."""
    frames = 152
    rows = [{'frame': f, 'pass': ok or f > 3} for f in range(frames)]
    r = {'schema': play.DERIVED_SCHEMA, 'label': play.DERIVED_LABEL, 'verified': False,
         'source_clip': {'sha256': play.GAMING_OWNER_GLB_SHA256}, 'frames': frames, 'frames_passing': frames if ok else frames - 4,
         'all_frames_pass': ok, 'per_frame': rows, 'fixed_offset': {'holds': True, 'controller_in_right_hand_gltf': np.eye(4).tolist()},
         'finger_deltas_deg': {'max_abs_deg': 12.}, 'controller': {'oversized': False}, 'output_glb_sha256': 'ab' * 32}
    r.update(override)
    return r


def raw_fit_report():
    frames = 152
    side = {'palm_support_patch_frames': frames, 'frames_with_penetration': 0}
    return {'schema': 'sub01.controller-grip-trial.v1', 'clip': {'source_fbx_sha256': play.GAMING_FBX_SHA256}, 'seated': {'seated': True},
            'fixed': {'summary': {'frames': frames, 'frames_full_grip': frames, 'left': side, 'right': side},
                      'controller_in_right_hand': np.eye(4).tolist()}}


def contact(ok=True):
    regions = [{'region': r, 'minGapCm': -.5 if ok else -4, 'bandVertices': 30, 'overSurfaceVertices': 40} for r in play.SOFA_REGIONS]
    for r in regions:
        if 'sole' in r['region']:
            r['minGapCm'] = .2
    return {'clip_duration_s': 5.0333, 'samples': [{'time': i / 30, 'invalidInfluences': 0, 'regions': regions} for i in range(152)]}


PLACEMENT = {'approach_cm': [-255, 10], 'yaw_deg': 180, 'body_offset_cm': [30, 0, -40], 'body_yaw_deg': 0,
             'sofa_footprint_cm': {'min': [-226.25, -103.75], 'max': [-133.75, 123.75]}}


def test_evidence_is_computed_from_measured_gates_and_refuses_each_failure():
    ev = play.build_evidence(sofa_text(), grip_report(), contact(), PLACEMENT)
    assert ev['accepted'] and ev['verified'] is False and ev['sofa_revision'] == str(play.play_id(sofa_text()))
    assert ev['capsule_clearance_cm'] == pytest.approx(11.75) and ev['grip_offset_cm'] == [0, 0, 0] and ev['grip_rotation_xyzw'] == [0, 0, 0, 1]
    with pytest.raises(ValueError, match='GripFailed'):
        play.build_evidence(sofa_text(), grip_report(False), contact(), PLACEMENT)
    with pytest.raises(ValueError, match='GripFailed'):
        play.build_evidence(sofa_text(), grip_report(all_frames_pass=True, frames_passing=151), contact(), PLACEMENT)
    with pytest.raises(ValueError, match='penetration'):
        play.build_evidence(sofa_text(), grip_report(), contact(False), PLACEMENT)
    with pytest.raises(ValueError, match='CapsuleInsideSofa'):
        play.build_evidence(sofa_text(), grip_report(), contact(), dict(PLACEMENT, approach_cm=[-220, 10]))
    with pytest.raises(ValueError, match='SofaUnmeasured'):
        play.build_evidence(json.dumps({'errors': ['x']}), grip_report(), contact(), PLACEMENT)
    with pytest.raises(ValueError, match='Gaming'):
        play.build_evidence(sofa_text(), grip_report(source_clip={'sha256': '0' * 64}), contact(), PLACEMENT)
    with pytest.raises(ValueError, match='derived_from_capture'):
        play.build_evidence(sofa_text(), grip_report(label='raw'), contact(), PLACEMENT)
    with pytest.raises(ValueError, match='fixed'):
        play.build_evidence(sofa_text(), grip_report(fixed_offset={'holds': False}), contact(), PLACEMENT)
    with pytest.raises(ValueError, match='finger deltas'):
        play.build_evidence(sofa_text(), grip_report(finger_deltas_deg={'max_abs_deg': 16.}), contact(), PLACEMENT)
    # A raw-capture fit (even a passing one) never feeds native play: the raw clip does not hold the controller.
    with pytest.raises(ValueError, match='derived grip clip'):
        play.build_evidence(sofa_text(), raw_fit_report(), contact(), PLACEMENT)
    assert ev['clip_object_path'] == play.CLIP_OBJECT_PATH and ev['grip_clip_sha256'] == 'ab' * 32 and ev['label'] == 'derived_from_capture'


def test_ue_grip_conjugates_the_axis_swap():
    X = F.pose(np.array([.2, -.4, .7, .01, .02, .03]))
    t, q = play.ue_grip(X.tolist())
    assert t == pytest.approx([1, 3, 2])
    P = np.array([[1, 0, 0], [0, 0, 1], [0, 1, 0]])
    R = P @ X[:3, :3] @ P
    x, y, z, w = q
    Rq = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                   [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                   [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    assert np.allclose(Rq, R, atol=1e-9) and abs(np.linalg.det(R) - 1) < 1e-9


def test_config_fragment_only_with_accepted_evidence_and_exact_import(tmp_path):
    (tmp_path / 'private-audit').mkdir()
    row = {'role': 'Gaming', 'object_path': play.CLIP_OBJECT_PATH, 'same_existing_skeleton': True, 'source_fbx_sha256': play.GAMING_FBX_SHA256,
           'derived_glb_sha256': 'ab' * 32}
    text, refusals = play.config_fragment(tmp_path, {'clips': [row]})
    assert text == '' and 'evidence' in refusals
    (tmp_path / 'private-audit' / play.SOFA_REPORT).write_text(sofa_text())
    (tmp_path / 'private-audit' / play.EVIDENCE).write_text(json.dumps(play.build_evidence(sofa_text(), grip_report(), contact(), PLACEMENT)))
    text, refusals = play.config_fragment(tmp_path, {'clips': [row]})
    assert refusals == {} and text.endswith('+ValidatedHandsPostures=Gaming\n')
    assert play.config_fragment(tmp_path, {'clips': [dict(row, same_existing_skeleton=False)]})[0] == ''
    assert play.config_fragment(tmp_path, {'clips': [dict(row, derived_glb_sha256='cd' * 32)]})[0] == ''
    (tmp_path / 'private-audit' / play.SOFA_REPORT).write_text(sofa_text() + ' ')   # another sofa report revision
    assert 'evidence' in play.config_fragment(tmp_path, {'clips': [row]})[1]


@pytest.mark.skipif(not (ROOT / 'docs/proposed/controller-play/controller-grip-gaming.summary.json').exists(), reason='real run summary absent')
def test_real_gaming_fit_is_refused_by_the_grip_gate():
    s = json.loads((ROOT / 'docs/proposed/controller-play/controller-grip-gaming.summary.json').read_text())
    assert s['verified'] is False
    with pytest.raises(ValueError):
        play.validate_grip(s)


# ---------------------------------------------------------------- staged install
NAMES = ('Sub01HomeLab.h', 'Sub01HomeLab.cpp', 'Sub01HomeHands.h', 'Sub01HomeHands.cpp')


def staged(order=('play',)):
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
            import unreal_life_clips_runtime as life
            life.install_module(module)
        else:
            play.install_module(module)
    return tmp, module, before, {n: (module / n).read_text() for n in NAMES}


def assert_additive(before, after):
    for name, text in before.items():
        position = 0
        for line in (l for l in text.splitlines() if l.strip()):
            position = after[name].index(line, position) + len(line)


@pytest.fixture(scope='module')
def installed():
    tmp, module, before, after = staged()
    yield before, after
    tmp.cleanup()


def test_install_is_additive_and_hooks_the_right_places(installed):
    before, after = installed
    assert_additive(before, after)
    h, cpp = after['Sub01HomeLab.h'], after['Sub01HomeLab.cpp']
    assert 'bool ControllerPlayActive' not in before['Sub01HomeLab.h'] and 'ControllerPlayActive=false' in h
    begin = cpp.split('void ASub01HomeCharacter::BeginPlay() {', 1)[1].split('\n}', 1)[0]
    assert begin.index('LoadHandsAssets();') < begin.index('LoadControllerPlay();')
    tick = cpp.split('void ASub01HomeCharacter::Tick(float DeltaSeconds) {', 1)[1].split('\n}\n', 1)[0]
    assert tick.index('TickMinecraftTVInput();') < tick.index(play.RATE_ANCHOR.strip()) < tick.index('UpdateControllerPlay(Instance,DeltaSeconds);')
    live = cpp.split('void ASub01HomeCharacter::UpdateLiveHome(float Dt){', 1)[1].split('\n}\n', 1)[0]
    assert live.index('if(ControllerPlayActive&&LiveHomePath.Num())') < live.index('if(!LiveHomePath.Num()){if(PCBridge)')
    assert after['Sub01HomeHands.h'] == before['Sub01HomeHands.h'] and after['Sub01HomeHands.cpp'] == before['Sub01HomeHands.cpp']


def test_added_code_respects_the_posture_gate_input_path_and_never_moves_the_actor():
    code = play.CHARACTER_FIELDS + play.methods() + play.LIVE_GATE
    for forbidden in ('SetActorLocation', 'Teleport', 'SetActorTransform', 'SetActorRotation', 'MoveUpdatedComponent', 'AddMovementInput',
                      'SendMinecraftTVInput', 'ReleaseMinecraftTVInput', 'MinecraftKeys', 'ValidatedHandsPostures.Add', 'HandsClips.Add',
                      'SetBoneLocation', 'SetBoneRotation', 'SetBoneTransform', 'TwoBoneIK', 'FABRIK', 'Output.Pose[', 'NativeSeatVerified='):
        assert forbidden not in code, forbidden
    m = play.methods()
    assert 'ValidatedHandsPostures.Contains(FName(TEXT("Gaming")))' in m and 'Clip->GetSkeleton()!=Mesh->GetSkeleton()' in m
    assert m.index('if(!SetHandsPosture(TEXT("Walk"))||!HandsFailure.IsEmpty())') < m.index('ControllerPlayActive=true;')
    assert 'LiveHomeActivity==TEXT("play_console")&&LiveHomeNode==TEXT("sofa")&&LiveHomePath.Num()==0' in m
    assert 'ControllerPlayProp->SetVisibility(false)' in m and m.count('ControllerPlayProp->SetVisibility(true)') == 1
    assert m.index('if(!ControllerPlayActive)return;') < m.index('ControllerPlayProp->SetVisibility(true)')
    assert 'SetCollisionEnabled(ECollisionEnabled::NoCollision)' in m
    # The mesh comes from root's import receipt (physical assembly, original source sha), never the contact shadow.
    assert 'native-controller-asset.json' in m and 'sub01.native-controller-asset.v1' in m and play.CONTROLLER_SOURCE_SHA256 in m
    assert '!MeshPath.Contains(TEXT("contact"),ESearchCase::IgnoreCase)' in m
    assert 'GetSocketTransform(ControllerPlayHand,RTS_World)' in m and 'W.GetRotation().GetNormalized()' in m
    assert 'Schema!=TEXT("sub01.native-controller-play-evidence.v1")' in m and 'Sub01ControllerPlayId(SofaText)' in m
    assert 'bool ASub01HomeCharacter::ControllerPlayReady() const{return ControllerPlayEvidence&&ControllerPlayRuntimeProof&&ControllerPlayClip&&ControllerPlayProp' in m
    assert 'native-controller-play-runtime-proof.json' in m and 'Sub01ControllerPlayId(EvidenceText)' in m and 'Passing==Measured' in m
    assert 'TEXT("/Game/Sub01Hands/Play/SUB01_GamingGrip.SUB01_GamingGrip")' in m


def test_install_refuses_missing_anchors_requirements_and_reinstall(installed):
    before, after = installed
    src = {'header': before['Sub01HomeLab.h'], 'cpp': before['Sub01HomeLab.cpp']}
    for key, anchor, _ in play.EDITS:
        broken = dict(src)
        broken[key] = broken[key].replace(anchor, '')
        with pytest.raises(ValueError):
            play.install(broken)
    broken = dict(src, header=src['header'].replace(' bool MinecraftFocused', ' bool OtherFocused'))
    with pytest.raises(ValueError, match='requires'):
        play.install(broken)
    with pytest.raises(ValueError, match='already installed'):
        play.install({'header': after['Sub01HomeLab.h'], 'cpp': after['Sub01HomeLab.cpp']})


@pytest.mark.parametrize('order', [('seat', 'life', 'play'), ('play', 'life', 'seat'), ('life', 'play')])
def test_coexists_with_the_seat_and_life_adapters(order):
    tmp, module, before, after = staged(order)
    try:
        assert_additive(before, after)
        cpp = after['Sub01HomeLab.cpp']
        assert cpp.count('UpdateControllerPlay(Instance,DeltaSeconds);') == 1 and cpp.count('LoadControllerPlay();') == 1
    finally:
        tmp.cleanup()


def test_play_id_is_the_same_fnv_as_the_life_and_seat_adapters():
    import unreal_life_clips_runtime as life
    for text in ('', sofa_text(), 'sofa'):
        assert play.play_id(text) == life.life_id(text)
    assert math.isfinite(play.APPROACH_TOLERANCE_CM)


# ---------------------------------------------------------------- option 1 search, time mapping, controller source
def test_time_mapping_native_four_seconds_is_gltf_4_033333():
    assert F.gltf_time(4.0) == pytest.approx(4.0 + 1 / 30) and F.native_time(F.gltf_time(4.0)) == pytest.approx(4.0)
    assert play.gltf_time(4.0) == pytest.approx(F.gltf_time(4.0)) and play.native_time(1 / 30) == pytest.approx(0)


@pytest.mark.skipif(not GAMING.exists(), reason='private retargeted Gaming clip absent')
def test_root_fk_values_are_gltf_4_000_not_native_4():
    hands = F.Hands.from_owner()
    both = F.fk_parity_both(GAMING, hands.names)
    g4, n4 = both['gltf_4.000000_native_3.966667'], both['gltf_4.033333_native_4.000000']
    assert max(g4['max_abs_error_vs_root_cm'].values()) < .01
    assert n4['native_t'] == pytest.approx(4.0) and max(n4['max_abs_error_vs_root_cm'].values()) > .3
    assert n4['fk_cm']['LeftHand'] == pytest.approx([20.2004, 88.1431, 50.7127], abs=.01)


@needs_controller
def test_controller_source_prefers_normalized_and_records_which_was_used():
    path, info = F.controller_source()
    if info['used'] == 'normalized':
        assert F.sha256(path) == F.NORMALIZED_CONTROLLER_SHA
    else:
        assert info == dict(info, used='original', sha256=F.ORIGINAL_CONTROLLER_SHA, normalized_present=False)


def test_grip_cost_prefers_the_true_grip_over_a_penetrating_one(mesh):
    right = frames(1)
    sets = world_sets(right)
    sdf = mesh.signed_distance
    tg = F.targets(features())
    for side in ('left', 'right'):
        loc = F._local_sets(sets, right[0], side, 0)
        ok = F.grip_cost(sdf, tg, side, {k: F.apply(X_TRUE, v) for k, v in F._local_sets(sets, right[0] @ X_TRUE, side, 0).items()}, X_TRUE, sub=1)
        bad = F.grip_cost(sdf, tg, side, {k: F.apply(X_TRUE, v) for k, v in F._local_sets(sets, right[0] @ X_TRUE, side, 0).items()},
                          X_TRUE @ F.pose(np.array([0, 0, 0, (1 if side == 'right' else -1) * .015, 0, 0])), sub=1)
        assert ok < 1 and bad > 50 * max(ok, 1e-3), (side, ok, bad)
        assert loc['hand'].shape[1] == 3


def search_report(passing=152, vary=0., baked=True):
    G = np.eye(4)
    rows = []
    for f in range(152):
        g = G.copy()
        g[0, 3] = vary * (f % 2) / 100
        rows.append({'right': {'controller_in_hand': g.tolist()}, 'left': {'controller_in_hand': G.tolist()}})
    return {'schema': 'sub01.controller-grip-trial.v1', 'mode': 'penetration_aware_joint_search',
            'clip': {'source_fbx_sha256': play.GAMING_FBX_SHA256, 'ik_baked': baked},
            'summary': {'frames': 152, 'frames_passing': passing, 'right_grip_variation': F.grip_variation(rows)}, 'per_frame': rows}


def test_search_gate_needs_every_frame_one_socket_offset_and_a_baked_ik_clip():
    assert play.validate_grip(search_report())['frames'] == 152
    with pytest.raises(ValueError, match='GripFailed'):
        play.validate_grip(search_report(passing=151))
    with pytest.raises(ValueError, match='varies'):
        play.validate_grip(search_report(vary=1.))
    with pytest.raises(ValueError, match='baked'):
        play.validate_grip(search_report(baked=False))
    v = F.grip_variation(search_report(vary=1.)['per_frame'])
    assert v['max_translation_cm'] == pytest.approx(.5) and v['max_rotation_deg'] < 1e-6


SEARCH_SUMMARIES = sorted((ROOT / 'docs/proposed/controller-play').glob('controller-search-*.summary.json'))


@pytest.mark.skipif(not SEARCH_SUMMARIES, reason='real option-1 search summaries absent')
def test_real_option1_search_reports_are_trial_and_gated():
    for path in SEARCH_SUMMARIES:
        r = json.loads(path.read_text())
        assert r['verified'] is False and r['mode'] == 'penetration_aware_joint_search' and r['summary']['frames'] == 152
        assert r['controller']['sha256'] in (F.ORIGINAL_CONTROLLER_SHA, F.NORMALIZED_CONTROLLER_SHA)
        with pytest.raises(ValueError):
            play.validate_grip(r)       # no IK-baked derived clip exists yet, whatever the pass count


# ---------------------------------------------------------------- derived grip clip and runtime proof
def proof(evidence_text, **override):
    p = {'schema': play.RUNTIME_PROOF_SCHEMA, 'accepted': True, 'clip_object_path': play.CLIP_OBJECT_PATH,
         'evidence_revision': str(play.play_id(evidence_text)), 'frames_measured': 152, 'frames_passing': 152,
         'max_penetration_cm': -.2, 'native_capture': {'path': 'x.png', 'sha256': 'ef' * 32}}
    p.update(override)
    return json.dumps(p)


def test_not_ready_without_roots_runtime_proof():
    ev = json.dumps(play.build_evidence(sofa_text(), grip_report(), contact(), PLACEMENT))
    assert play.validate_runtime_proof(proof(ev), ev)['frames'] == 152
    for bad in (dict(accepted=False), dict(frames_passing=151), dict(frames_measured=100, frames_passing=100),
                dict(evidence_revision='1'), dict(clip_object_path='/Game/Other'), dict(max_penetration_cm=-.4), dict(native_capture={})):
        with pytest.raises(ValueError):
            play.validate_runtime_proof(proof(ev, **bad), ev)
    # The native loader computes readiness only with the proof field set (see the C++ gate test above).
    m = play.methods()
    assert m.index('ControllerPlayRuntimeProof=false;') < m.index('ControllerPlayRuntimeProof=Proof->TryGetStringField')
    assert 'RuntimeProofMissing' in m


import derive_controller_grip_clip as DG  # noqa: E402

DERIVED_REPORT = ROOT / 'docs/proposed/controller-play/SUB01_GamingGrip_derived.report.json'
DERIVED_GLB = ROOT / 'docs/proposed/controller-play/SUB01_GamingGrip_derived.glb'


@pytest.fixture(scope='module')
def gaming_clip():
    if not GAMING.exists():
        pytest.skip('private retargeted Gaming clip absent')
    return DG.Clip(GAMING)


def test_two_bone_ik_on_the_real_arm_reaches_keeps_lengths_and_leaves_the_rest(gaming_clip):
    c = gaming_clip
    W0 = c.worlds()
    H = c.index['LeftHand']
    target = np.stack([F.rigid(m) for m in W0[:, H]])
    target[:, :3, 3] += np.array([-.05, .01, .02])                      # 5.5 cm toward the controller
    target[:, :3, :3] = target[:, :3, :3] @ F.rotvec_to_matrix([0, .2, 0])
    q, reach = DG.solve_arm(c, c.q, W0, 'Left', target)
    W = c.worlds(q)
    assert reach.all()
    assert np.allclose(W[:, H, :3, 3], target[:, :3, 3], atol=1e-9)
    assert np.allclose(DG.unit_rot(W[:, H]), target[:, :3, :3], atol=1e-9)
    for child in ('LeftForeArm', 'LeftHand', 'LeftHandIndex1', 'LeftHandIndex3'):
        i, p = c.index[child], c.g.parent[c.index[child]]
        assert np.allclose(np.linalg.norm(W[:, i, :3, 3] - W[:, p, :3, 3], axis=1), np.linalg.norm(W0[:, i, :3, 3] - W0[:, p, :3, 3], axis=1), atol=1e-12)
    for n in ('Head', 'Neck', 'Spine2', 'LeftShoulder', 'RightHand', 'RightHandThumb2'):
        assert np.allclose(W[:, c.index[n]], W0[:, c.index[n]])
    # finger locals are untouched by the arm IK
    for n in ('LeftHandThumb2', 'LeftHandIndex2'):
        assert np.allclose(q[:, c.index[n]], c.q[:, c.index[n]])


def test_finger_deltas_are_added_constant_and_keep_the_captured_variation(gaming_clip):
    c = gaming_clip
    hands = F.Hands.from_owner()
    axes = DG.finger_axes(c, hands)
    q, per = DG.apply_finger_deltas(c.q, c, axes, {'Right': {'Thumb': (10., -6.), 'Index': (-8., 0.)}})
    assert np.allclose(per['RightHandThumb1']['curl_deg'], 10.) and np.allclose(per['RightHandThumb1']['spread_deg'], -6.)
    assert np.allclose(per['RightHandThumb3']['spread_deg'], 0)
    for n, expect in (('RightHandThumb2', 10.), ('RightHandIndex3', 8.)):
        i = c.index[n]
        # delta is the same every frame: relative rotation captured->derived is constant (smooth by construction)
        rel = [G_angle(c.q[f, i], q[f, i]) for f in range(len(c.times))]
        assert np.allclose(rel, expect, atol=1e-6)
        # captured temporal variation preserved: frame-to-frame changes are identical
        d0 = [G_angle(c.q[f, i], c.q[f + 1, i]) for f in range(len(c.times) - 1)]
        d1 = [G_angle(q[f, i], q[f + 1, i]) for f in range(len(c.times) - 1)]
        assert np.allclose(d0, d1, atol=1e-6)
    untouched = c.index['LeftHandThumb2']
    assert np.allclose(q[:, untouched], c.q[:, untouched])
    # curl sign: positive curl moves the distal joint toward the palm side
    W0, W1 = c.worlds(), c.worlds(DG.apply_finger_deltas(c.q, c, axes, {'Right': {'Index': (10., 0.)}})[0])
    tip = c.index['RightHandIndex4']
    assert np.linalg.norm(W1[:, tip, :3, 3] - W0[:, tip, :3, 3], axis=1).min() > 1e-3


def G_angle(a, b):
    import life_gltf as LG
    return LG.qangle_deg(tuple(a), tuple(b))


@pytest.mark.skipif(not DERIVED_REPORT.exists(), reason='derived grip clip report absent (python tools/derive_controller_grip_clip.py)')
def test_committed_derived_clip_report_is_consistent_and_honest():
    r = json.loads(DERIVED_REPORT.read_text())
    assert r['label'] == 'derived_from_capture' and r['verified'] is False and r['frames'] == 152 and len(r['per_frame']) == 152
    assert r['all_frames_pass'] == (r['frames_passing'] == 152) == all(p['pass'] for p in r['per_frame'])
    assert r['failing_frames'] == [p['frame'] for p in r['per_frame'] if not p['pass']]
    assert r['bone_length_max_error_cm'] < 1e-6 and r['upper_body_max_world_change'] == 0
    assert r['finger_deltas_deg']['max_abs_deg'] <= 15 + 1e-9 and r['controller']['oversized'] is False
    assert r['finger_deltas_deg'].get('max_rate_deg_per_frame', 0) <= DG.MAX_DELTA_RATE_DEG_PER_FRAME
    assert r['loop_seam_max_jump_deg']['derived'] <= r['loop_seam_max_jump_deg']['captured'] + 1.0
    per = r['finger_deltas_deg'].get('per_joint_per_frame')
    if per:
        for v in per.values():
            for k in ('curl_deg', 'spread_deg'):
                a = np.array(v[k])
                assert len(a) == 152 and np.abs(a).max() <= 15 + 1e-9 and np.abs(np.diff(a)).max() <= DG.MAX_DELTA_RATE_DEG_PER_FRAME
    assert r['controller']['width_cm'] == pytest.approx(15.38, abs=.01) and r['gates']['compression_allowance_beyond_band_cm'] == 0
    assert r['source_clip']['sha256'] == play.GAMING_OWNER_GLB_SHA256
    for p in r['per_frame']:
        if p['pass']:
            for s in ('left', 'right'):
                assert p[s]['hand_min_signed_cm'] >= -.3 and p[s]['palm_support_patch'] and p[s]['within_bound']
    if DERIVED_GLB.exists():
        assert F.sha256(DERIVED_GLB) == r['output_glb_sha256'] and DERIVED_GLB.stat().st_size < 2_000_000
    if not r['all_frames_pass']:
        with pytest.raises(ValueError):
            play.validate_grip(r)


def test_delta_smoothing_is_periodic_and_bounded():
    x = np.zeros(40)
    x[5] = 10
    y = DG.gaussian_smooth(x, DG.SMOOTH_SIGMA_FRAMES)
    assert y.sum() == pytest.approx(10) and y.max() < 10 and np.abs(np.diff(y)).max() < 2.5
    assert np.allclose(DG.gaussian_smooth(np.full(30, 3.), 2.), 3.)
    z = np.zeros(40)
    z[0] = 10                                    # mass near the seam wraps to the end, keeping the loop continuous
    w = DG.gaussian_smooth(z, 2.)
    assert w[-1] == pytest.approx(w[1]) and w[-1] > 0
