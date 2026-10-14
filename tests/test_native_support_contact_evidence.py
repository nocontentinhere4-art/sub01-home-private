"""Native bed/sofa/controller contact evidence: written ONLY from native observations that pass; synthetic captures."""
import copy
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import native_support_contact_evidence as E  # noqa: E402
import unreal_native_support_capture as CAP  # noqa: E402
import unreal_controller_grip_contact_native as GRIP  # noqa: E402
import unreal_controller_play_runtime as play  # noqa: E402
import unreal_life_clips_runtime as life  # noqa: E402
import unreal_sofa_surface_audit as S  # noqa: E402
import validate_unreal_seat_contact as seat  # noqa: E402
import fit_controller_grip as F  # noqa: E402
from stage_unreal_home_runtime import stage  # noqa: E402

DURATIONS = {'LieDown': 2.0, 'SleepLoop': 3.0, 'GetUp': 2.0}


# ------------------------------------------------------------------ synthetic native reports and captures
def bed_report():
    v = [[-315, -335, 360], [-165, -335, 360], [-165, -135, 360], [-315, -135, 360]]
    return json.dumps({'schema': 'sub01.native-bed-surface.v1', 'errors': [],
                       'bed': {'component': 'Bed', 'sections': [{'vertices_world_cm': v, 'mattress_surface': {'triangle_indices': [[0, 1, 2], [0, 2, 3]]}}]}},
                      indent=2) + '\n'


def sofa_report():
    v = [[-221, -80, 50.3], [-155, -80, 50.3], [-155, 100, 50.3], [-221, 100, 50.3]]
    surface = S.seat_surface(v, [0, 1, 2, 0, 2, 3])
    return json.dumps({'schema': S.SCHEMA, 'errors': [], 'sofa': {'component': 'Haven_linen', 'component_world_bounds_cm':
                       {'min': [-226.25, -103.75, 0], 'max': [-133.75, 123.75, 91.7]},
                       'sections': [{'vertices_world_cm': v, 'seat_surface': surface}]}}, indent=2) + '\n'


def region(name, gap, band=30, over=40):
    return {'region': name, 'selectedVertices': 900, 'facingVertices': 300, 'overSurfaceVertices': over, 'bandVertices': band,
            'minGapCm': gap, 'p10GapCm': gap + .2, 'p50GapCm': gap + 1, 'p90GapCm': gap + 3, 'maxGapCm': gap + 5,
            'facingBoundsWorldCm': {'min': [0, 0, 0], 'max': [1, 1, 1]}}


def lying_regions(gap=-.4):
    rows = [region('buttocks', gap)]
    rows += [region(n, 3.0, band=0) for n in ('left_posterior_thigh', 'right_posterior_thigh')]   # knees up: reported only
    rows += [region(n, 40.0, band=0, over=60) for n in seat.SOLE_REGIONS]
    return rows


def bed_capture(text, **mutate):
    samples, clips = [], []
    for role, d in DURATIONS.items():
        clips.append({'role': role, 'object_path': life.clip_object_path(role), 'duration_s': d, 'rate_hz': 30})
        for t in CAP.sample_times(d):
            samples.append({'role': role, 'time': t, 'invalidInfluences': 0, 'floorCm': 2.5, 'regions': lying_regions()})
    cap = {'schema': E.CAPTURE_SCHEMA, 'kind': 'bed', 'observation': 'native_editor_clip_evaluation', 'analyzer': E.SEAT_ANALYZER,
           'surface_report': {'file': 'private-audit/native-bed-surface.json', 'revision': str(life.life_id(text))},
           'placement': {'approach_cm': [-140, -250], 'capsule_z_cm': 392, 'yaw_deg': 180, 'hands_base_offset_cm': [0, 0, -90],
                         'hands_mesh_rotation_deg': {'pitch': 0, 'yaw': -90, 'roll': 0}},
           'floor_cm': 302.5, 'floor_evidence': 'synthetic test', 'clips': clips, 'samples': samples, 'errors': []}
    cap.update(mutate)
    return cap


def seated_regions(gap=-.5):
    rows = [region(n, gap) for n in seat.SEAT_REGIONS]
    rows += [region(n, .2) for n in seat.SOLE_REGIONS]
    return rows


def sofa_capture(text, gap=-.5):
    d = 5.0333
    return {'schema': E.CAPTURE_SCHEMA, 'kind': 'sofa', 'observation': 'native_editor_clip_evaluation', 'analyzer': E.SEAT_ANALYZER,
            'surface_report': {'revision': str(play.play_id(text))},
            'placement': {'approach_cm': [-255, 10], 'capsule_z_cm': 92, 'yaw_deg': 180, 'body_offset_cm': [30, 0, -40], 'body_yaw_deg': 0,
                          'hands_mesh_rotation_deg': {'pitch': 0, 'yaw': -90, 'roll': 0}},
            'floor_cm': 2.5, 'floor_evidence': 'synthetic test', 'errors': [],
            'clips': [{'role': play.ROLE, 'object_path': play.CLIP_OBJECT_PATH, 'duration_s': d, 'rate_hz': 30}],
            'samples': [{'role': play.ROLE, 'time': t, 'invalidInfluences': 0, 'regions': seated_regions(gap)} for t in CAP.sample_times(d)]}


def hand(side, palm_gap=-.1, band=40, signed=-.2, pen=0):
    return {'side': side, 'palmVertices': 300, 'palmNearVertices': 120, 'palmBandVertices': band, 'palmMinGapCm': palm_gap,
            'handVertices': 4000, 'handNearVertices': 900, 'handPenetratingVertices': pen, 'handMinSignedCm': signed}


def grip_capture(evidence_text, frames=152, bad_frame=None):
    rows = []
    for k in range(frames):
        hands = [hand('left'), hand('right')]
        if k == bad_frame:
            hands[1] = hand('right', signed=-1.1, pen=37)
        rows.append({'frame': k, 'time': k / 30, 'invalidInfluences': 0, 'hands': hands})
    return {'schema': E.CAPTURE_SCHEMA, 'kind': 'controller_grip', 'observation': 'native_editor_clip_evaluation', 'analyzer': E.GRIP_ANALYZER,
            'evidence_revision': str(play.play_id(evidence_text)), 'errors': [],
            'clips': [{'role': play.ROLE, 'object_path': play.CLIP_OBJECT_PATH, 'duration_s': 151 / 30}], 'samples': rows}


def grip_report():
    import numpy as np
    frames = 152
    return {'schema': play.DERIVED_SCHEMA, 'label': play.DERIVED_LABEL, 'verified': False, 'source_clip': {'sha256': play.GAMING_OWNER_GLB_SHA256},
            'frames': frames, 'frames_passing': frames, 'all_frames_pass': True, 'per_frame': [{'frame': f, 'pass': True} for f in range(frames)],
            'fixed_offset': {'holds': True, 'controller_in_right_hand_gltf': np.eye(4).tolist()}, 'finger_deltas_deg': {'max_abs_deg': 12.},
            'controller': {'oversized': False}, 'output_glb_sha256': 'ab' * 32}


@pytest.fixture
def project(tmp_path):
    audit = tmp_path / 'private-audit'
    audit.mkdir()
    (audit / 'native-bed-surface.json').write_text(bed_report())
    (audit / play.SOFA_REPORT).write_text(sofa_report())
    return tmp_path


def put(tmp_path, name, doc):
    p = tmp_path / name
    p.write_text(json.dumps(doc))
    return p


def evaluation(project, kind):
    return json.loads((project / 'private-audit' / f'native-{kind}-contact-evaluation.json').read_text())


# ------------------------------------------------------------------ bed
def test_passing_native_bed_observations_write_evidence_the_life_adapter_accepts(project, tmp_path):
    text = (project / 'private-audit/native-bed-surface.json').read_text()
    result = E.write_bed(project, put(tmp_path, 'cap.json', bed_capture(text)))
    assert result['accepted'] is True
    ev = json.loads((project / 'private-audit' / E.BED_EVIDENCE).read_text())
    assert ev['schema'] == 'sub01.native-life-bed-evidence.v1' and ev['accepted'] is True
    assert ev['bed_revision'] == str(life.life_id(text)) and ev['approach_cm'] == [-140, -250] and ev['yaw_deg'] == 180
    assert ev['native_bed_verified'] is False and ev['capture_sha256']
    checked = life.check_bed(project)                       # the adapter's own Python mirror of the C++ loader
    assert checked['approach_cm'] == [-140, -250] and checked['area_cm2'] == pytest.approx(30000)
    assert evaluation(project, 'bed')['accepted'] is True


def test_no_observations_never_write_bed_evidence(project, tmp_path):
    text = (project / 'private-audit/native-bed-surface.json').read_text()
    for cap in (bed_capture(text, samples=[]), bed_capture(text, observation='source_measured'),
                bed_capture(text, analyzer='python'), bed_capture(text, errors=['editor crashed']), {'schema': 'x'}):
        result = E.write_bed(project, put(tmp_path, 'cap.json', cap))
        assert result['accepted'] is False and 'NoObservations' in result['error']
        assert not (project / 'private-audit' / E.BED_EVIDENCE).exists()
        assert evaluation(project, 'bed')['ready'] is False
    with pytest.raises(ValueError, match='BedPlacementMissing'):
        life.check_bed(project)


def test_failing_bed_contact_writes_no_evidence(project, tmp_path):
    text = (project / 'private-audit/native-bed-surface.json').read_text()
    pen = bed_capture(text)
    row = next(r for r in pen['samples'] if r['role'] == 'SleepLoop')
    row['regions'][0] = region('buttocks', -2.6)                 # one sample beyond the band's compression
    floating = bed_capture(text)
    for r in floating['samples']:
        if r['role'] == 'SleepLoop':
            r['regions'][0] = region('buttocks', 2.0, band=0)     # lying above the mattress: no support patch
    thigh_pen = bed_capture(text)
    thigh_pen['samples'][5]['regions'][1] = region('left_posterior_thigh', -3.0)
    sparse = bed_capture(text)
    sparse['samples'] = [r for i, r in enumerate(sparse['samples']) if i % 2 == 0]
    other_bed = bed_capture(text.replace('360', '361'))
    no_approach = bed_capture(text, placement={'yaw_deg': 0})
    bad_influence = bed_capture(text)
    bad_influence['samples'][0]['invalidInfluences'] = 3
    for cap, why in ((pen, 'penetrates'), (floating, 'no support patch'), (thigh_pen, 'left_posterior_thigh penetrates'),
                     (sparse, 'CoverageIncomplete'), (other_bed, 'BedRevisionMismatch'), (no_approach, 'BedPlacementMissing'),
                     (bad_influence, 'InvalidInfluences')):
        result = E.write_bed(project, put(tmp_path, 'cap.json', cap))
        assert result['accepted'] is False and why in result['error'], (why, result)
        assert not (project / 'private-audit' / E.BED_EVIDENCE).exists()


def test_bed_needs_a_measured_bed_report(project, tmp_path):
    text = (project / 'private-audit/native-bed-surface.json').read_text()
    cap = put(tmp_path, 'cap.json', bed_capture(text))
    (project / 'private-audit/native-bed-surface.json').unlink()
    assert 'BedUnmeasured' in E.write_bed(project, cap)['error']
    small = json.loads(text)
    small['bed']['sections'][0]['vertices_world_cm'] = [[0, 0, 60], [50, 0, 60], [50, 40, 60], [0, 40, 60]]
    small_text = json.dumps(small)
    (project / 'private-audit/native-bed-surface.json').write_text(small_text)
    assert 'BedUnmeasured' in E.write_bed(project, put(tmp_path, 'cap2.json', bed_capture(small_text)))['error']
    assert not (project / 'private-audit' / E.BED_EVIDENCE).exists()


# ------------------------------------------------------------------ sofa -> controller evidence
def test_passing_sofa_observations_feed_the_controller_evidence_builder(project, tmp_path):
    text = (project / 'private-audit' / play.SOFA_REPORT).read_text()
    grip = put(tmp_path, 'grip.json', grip_report())
    result = E.write_sofa(project, put(tmp_path, 'cap.json', sofa_capture(text)), grip)
    assert result['accepted'] is True and 'controller_evidence_refused' not in result
    contact = json.loads((project / 'private-audit' / E.SOFA_CONTACT).read_text())
    placement = json.loads((project / 'private-audit' / E.SOFA_PLACEMENT).read_text())
    assert play.validate_sofa_contact(contact)['passed'] is True
    assert placement['sofa_footprint_cm'] == {'min': [-226.25, -103.75], 'max': [-133.75, 123.75]}
    assert placement['capsule_clearance_cm'] == pytest.approx(11.75)
    ev = json.loads((project / 'private-audit' / play.EVIDENCE).read_text())
    assert ev['accepted'] is True and ev['sofa_revision'] == str(play.play_id(text)) and ev['seat_contact_passed'] is True
    text_cfg, refusals = play.config_fragment(project, {'clips': []})
    assert text_cfg == '' and 'clip' in refusals and 'evidence' not in refusals   # evidence now accepted; the import row is root's


def test_failing_or_absent_sofa_observations_write_nothing(project, tmp_path):
    text = (project / 'private-audit' / play.SOFA_REPORT).read_text()
    short = sofa_capture(text)
    short['samples'] = short['samples'][:100]
    wrong_clip = sofa_capture(text)
    wrong_clip['clips'][0]['object_path'] = '/Game/Sub01Hands/Controller/SUB01_Gaming.SUB01_Gaming'
    inside = sofa_capture(text)
    inside['placement']['approach_cm'] = [-200, 10]
    empty = sofa_capture(text)
    empty['samples'] = []
    for cap, why in ((sofa_capture(text, gap=-4), 'SofaContactFailed'), (short, 'CoverageIncomplete'), (wrong_clip, 'ClipMismatch'),
                     (inside, 'CapsuleInsideSofa'), (empty, 'NoObservations'),
                     (sofa_capture(text.replace('50.3', '50.4')), 'SofaRevisionMismatch')):
        result = E.write_sofa(project, put(tmp_path, 'cap.json', cap))
        assert result['accepted'] is False and why in result['error'], (why, result)
        for name in (E.SOFA_CONTACT, E.SOFA_PLACEMENT, play.EVIDENCE):
            assert not (project / 'private-audit' / name).exists()


# ------------------------------------------------------------------ controller runtime proof
def accepted_evidence(project, tmp_path):
    text = (project / 'private-audit' / play.SOFA_REPORT).read_text()
    assert E.write_sofa(project, put(tmp_path, 'sofa-cap.json', sofa_capture(text)), put(tmp_path, 'grip.json', grip_report()))['accepted']
    return (project / 'private-audit' / play.EVIDENCE).read_text()


def test_passing_native_grip_frames_write_the_runtime_proof_the_adapter_reads(project, tmp_path):
    ev_text = accepted_evidence(project, tmp_path)
    cap_path = project / 'private-audit/native-controller_grip-capture.json'
    cap_path.write_text(json.dumps(grip_capture(ev_text)))
    result = E.write_grip(project, cap_path)
    assert result['accepted'] is True
    proof_text = (project / 'private-audit' / play.RUNTIME_PROOF).read_text()
    proof = json.loads(proof_text)
    assert play.validate_runtime_proof(proof_text, ev_text)['frames'] == 152
    assert proof['max_penetration_cm'] == pytest.approx(-0.2) and proof['native_capture']['path'] == 'private-audit/native-controller_grip-capture.json'
    assert proof['verified'] is False and 'thumb/index feature gates of the derived-clip report' in proof['not_measured_natively']


def test_grip_proof_refused_on_a_failing_frame_too_few_frames_or_another_evidence(project, tmp_path):
    ev_text = accepted_evidence(project, tmp_path)
    for cap, why in ((grip_capture(ev_text, bad_frame=40), 'GripContactFailed: 151/152'), (grip_capture(ev_text, frames=150), 'CoverageIncomplete'),
                     (grip_capture(ev_text + ' '), 'EvidenceRevisionMismatch')):
        result = E.write_grip(project, put(tmp_path, 'g.json', cap))
        assert result['accepted'] is False and why in result['error'], (why, result)
        assert not (project / 'private-audit' / play.RUNTIME_PROOF).exists()
    loose = grip_capture(ev_text)
    loose['samples'][3]['hands'][0] = hand('left', palm_gap=.8, band=0)
    assert 'left palm' in E.write_grip(project, put(tmp_path, 'g.json', loose))['error']


def test_grip_proof_needs_accepted_evidence(project, tmp_path):
    result = E.write_grip(project, put(tmp_path, 'g.json', grip_capture('{}')))
    assert result['accepted'] is False and 'EvidenceMissing' in result['error']


def test_check_cli_reports_coverage_and_refusals(project, tmp_path, capsys):
    text = (project / 'private-audit/native-bed-surface.json').read_text()
    assert E.main(['check', str(put(tmp_path, 'c.json', bed_capture(text)))]) == 0
    assert json.loads(capsys.readouterr().out)['coverage'] == {'LieDown': 61, 'SleepLoop': 91, 'GetUp': 61}
    assert E.main(['check', str(put(tmp_path, 'c.json', bed_capture(text, samples=[])))]) == 3


# ------------------------------------------------------------------ capture helpers (the editor script's pure parts)
def test_capture_times_cover_the_clip_at_30_hz_and_both_ends():
    t = CAP.sample_times(5.0333)
    assert t[0] == 0 and t[-1] == pytest.approx(5.0333) and len(t) >= int(5.0333 * 30)
    assert all(b > a for a, b in zip(t, t[1:]))
    with pytest.raises(ValueError):
        CAP.sample_times(0)


def test_root_path_sampling_matches_the_cpp_rule():
    path = [(0, 0), (10, 0), (20, 5)]
    assert CAP.sample_root_path(path, 30, 1 / 60, False) == pytest.approx((5, 0))
    assert CAP.sample_root_path(path, 30, 10, False) == pytest.approx((20, 5))           # clamped
    assert CAP.sample_root_path(path, 30, 2.5 / 30, True) == pytest.approx((5, 0))       # fmod(2.5, 2) = .5
    fps, paths = CAP.load_root_paths({'schema': 'sub01.bed-mesh-root-path.v1', 'fps': 30,
                                      'roles': {r: {'forward_cm': [0, 1], 'right_cm': [0, 0]} for r in life.BED_ROLES}})
    assert fps == 30 and set(paths) == set(life.BED_ROLES)
    with pytest.raises(ValueError):
        CAP.load_root_paths({'schema': 'other'})


def test_capture_requires_measured_placement_and_floor():
    with pytest.raises(ValueError, match='missing yaw_deg'):
        CAP.require_placement({'placement': {'approach_cm': [0, 0]}, 'floor_cm': 2.5, 'floor_evidence': 'x'}, ('approach_cm', 'yaw_deg'))
    with pytest.raises(ValueError, match='floor'):
        CAP.require_placement({'placement': {'approach_cm': [0, 0]}}, ('approach_cm',))


def test_capture_and_analyzer_bands_are_the_grip_fitters():
    assert CAP.PALM_BAND_CM == F.PALM_BAND_CM and F.PENETRATION_LIMIT_CM == F.PALM_BAND_CM[0]


# ------------------------------------------------------------------ the additive native grip analyzer install
@pytest.fixture(scope='module')
def staged(tmp_path_factory):
    project = tmp_path_factory.mktemp('staged')
    (project / 'Config').mkdir()
    (project / 'Sub01HomeLab.uproject').write_text('{}')
    stage(project)
    return project / 'Source/Sub01HomeLab'


def test_grip_analyzer_install_is_additive_unique_and_refuses_reinstall(staged, tmp_path):
    module = tmp_path / 'm'
    shutil.copytree(staged, module)
    before = {k: (module / n).read_text() for k, n in GRIP.SOURCE_FILES.items()}
    others = {p.name: p.read_bytes() for p in module.iterdir() if p.name not in GRIP.SOURCE_FILES.values()}
    GRIP.install_module(module, dry_run=True)
    assert {k: (module / n).read_text() for k, n in GRIP.SOURCE_FILES.items()} == before
    GRIP.install_module(module)
    after = {k: (module / n).read_text() for k, n in GRIP.SOURCE_FILES.items()}
    assert after['hands_header'].count('static FString AnalyzeCapturedControllerGrip(') == 1
    assert after['hands_cpp'].count('FString USub01HomeHandsInstance::AnalyzeCapturedControllerGrip(') == 1
    for key in GRIP.SOURCE_FILES:
        GRIP.assert_additive(before[key], after[key])
    assert {p.name: p.read_bytes() for p in module.iterdir() if p.name not in GRIP.SOURCE_FILES.values()} == others
    with pytest.raises(ValueError, match='already installed'):
        GRIP.install_module(module)
    bare = {'hands_header': before['hands_header'], 'hands_cpp': '// nothing'}
    with pytest.raises(ValueError, match='AnalyzeCapturedSeatSkin'):
        GRIP.install(bare)
    twice = dict(before, hands_header=before['hands_header'] + '\n static FString AnalyzeCapturedSeatSkin(x);\n')
    with pytest.raises(ValueError, match='not unique'):
        GRIP.install(twice)


def test_grip_analyzer_places_the_controller_like_the_adapter_and_is_probe_only():
    cpp = GRIP.CPP
    assert 'ComponentPose[Grip]*BodyWorld' in cpp and 'GetRotation().GetNormalized()' in cpp and 'R.RotateVector(GripOffset)' in cpp
    assert '"ControllerPlayProp->SetWorldLocationAndRotation(W.GetLocation()+R.RotateVector(ControllerPlayGripOffset),R*ControllerPlayGripRotation)' \
        .strip('"') in play.CHARACTER_METHODS
    for forbidden in ('SetActorLocation', 'SetWorldLocation', 'NativeSeatVerified', 'ValidatedHandsPostures'):
        assert forbidden not in cpp
