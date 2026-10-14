"""Seat transition adapter: evidence producer, native consumer parity, staged integration hooks."""
import copy
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import unreal_seat_transition_runtime as adapter  # noqa: E402
from stage_unreal_home_runtime import stage  # noqa: E402

CHAIR = json.dumps({'errors': [], 'chair': {'component': '/Game/Sub01Home/ActualHome.Chair:Cushion', 'sections': [{
    'vertices_world_cm': [[180, -210, 50.5], [220, -210, 50.5], [220, -170, 50.5], [180, -170, 50.5]],
    'triangles': [0, 1, 2, 0, 2, 3],
    'cushion_surface': {'triangle_indices': [[0, 1, 2], [0, 2, 3]],
                        'world_bounds_cm': {'min': [180, -210, 50.5], 'max': [220, -170, 50.5]}}}]}})


def seat_report(**override):
    regions = {'buttocks': (-1.2, -.6), 'left_posterior_thigh': (-.9, -.2), 'right_posterior_thigh': (-.8, -.1),
               'left_sole': (.1, .3), 'right_sole': (.1, .4)}
    regions.update(override)
    row = {'invalidInfluences': 0, 'floorCm': 0.0, 'regions': [
        {'region': n, 'selectedVertices': 900, 'facingVertices': 300, 'overSurfaceVertices': 200, 'bandVertices': 150,
         'minGapCm': lo, 'p10GapCm': lo + .1, 'p50GapCm': med, 'p90GapCm': med + .4, 'maxGapCm': med + 1}
        for n, (lo, med) in regions.items()]}
    return {'schema': 'sub01.native-seat-contact.v1', 'body_cm': [203.9, -232.3, -.6], 'body_yaw': 180, 'floor_cm': 0.0,
            'samples': [dict(copy.deepcopy(row), time=3 + i / 60) for i in range(301)]}


def compiler():
    found = shutil.which('clang++') or shutil.which('g++')
    if not found:
        pytest.skip('C++ compiler unavailable')
    return found


def run_cpp(source):
    with tempfile.TemporaryDirectory() as tmp:
        cpp, exe = Path(tmp) / 'a.cpp', Path(tmp) / 'a'
        cpp.write_text(source)
        built = subprocess.run([compiler(), '-std=c++17', '-Wall', '-Werror', f'-I{adapter.HEADER_FILE.parent}', str(cpp), '-o', str(exe)],
                               capture_output=True, text=True)
        assert built.returncode == 0, built.stderr[-3000:]
        ran = subprocess.run([str(exe)], capture_output=True, text=True)
        assert ran.returncode == 0, ran.stdout
        return ran.stdout


def test_seat_ids_match_the_native_hash():
    paths = [adapter.OWNER_MESH, adapter.TYPING_CLIP, CHAIR, 'é/ü', '']
    body = ''.join(f'std::printf("%llu\\n",(unsigned long long)Sub01SeatId({json.dumps(p)}));' for p in paths)
    out = run_cpp('#include <cstdio>\n#include "Sub01SeatTransition.h"\nint main(){' + body + 'return 0;}')
    # The C++ literal is UTF-8 bytes; the native side hashes ASCII asset paths and the exact chair file text.
    expected = [adapter.seat_id(p) for p in paths[:3]] + [adapter.seat_id('é/ü'.encode().decode('latin-1')), adapter.seat_id('')]
    assert [int(v) for v in out.split()] == expected


def test_evidence_is_built_only_from_an_accepted_report_and_matches_the_native_receipt():
    evidence = adapter.build_evidence(seat_report(), CHAIR)
    assert evidence['native_seat_verified'] is False and evidence['family'] == 'DeskTyping'
    assert evidence['time_range_s'] == [3.0, 8.0] and evidence['chair_revision'] == str(adapter.seat_id(CHAIR))
    assert evidence['patches']['left_posterior_thigh'] == {'min_gap_cm': -.9, 'max_median_cm': -.2, 'min_coverage': .75}
    # The native consumer accepts exactly this evidence for the matching live pose, and nothing near it.
    p = evidence['patches']
    fill = ''.join(f'E.MinGap[{i}]={p[n]["min_gap_cm"]};E.MaxMedian[{i}]={p[n]["max_median_cm"]};E.MinCoverage[{i}]={p[n]["min_coverage"]};'
                   for i, n in enumerate(adapter.PATCHES))
    x, y, z = evidence['body_cm']
    pitch, yaw, roll = evidence['body_rotation_pyr']
    sx, sy, sz = evidence['body_scale_xyz']
    assert (pitch, yaw, roll, sx, sy, sz) == (0, 180, 0, 1, 1, 1)
    source = f'''#include "Sub01SeatTransition.h"
int main(){{FSub01SeatEvidence E;E.Loaded=true;E.Family=ESub01SeatFamily::DeskTyping;
 E.MeshId={evidence["mesh_id"]}ull;E.ClipId={evidence["clip_id"]}ull;E.ChairRevision={evidence["chair_revision"]}ull;
 E.X={x};E.Y={y};E.Z={z};E.PitchDeg={pitch};E.YawDeg={yaw};E.RollDeg={roll};E.ScaleX={sx};E.ScaleY={sy};E.ScaleZ={sz};E.T0={evidence["time_range_s"][0]};E.T1={evidence["time_range_s"][1]};{fill}
 if(!Sub01SeatEvidenceInBand(E))return 1;
 FSub01SeatLivePose L;L.MeshId=Sub01SeatId("{adapter.OWNER_MESH}");L.ClipId=Sub01SeatId("{adapter.TYPING_CLIP}");L.Family=ESub01SeatFamily::DeskTyping;
 L.ChairRevision={evidence["chair_revision"]}ull;L.X={x};L.Y={y};L.Z={z}+.03;L.PitchDeg=0;L.YawDeg=-179.98;L.RollDeg=0;L.ScaleX=L.ScaleY=L.ScaleZ=1;L.ClipSeconds=6;L.ClipPlaying=true;
 if(!Sub01SeatReceipt(E,L))return 2;
 L.Z={z}+.1;if(Sub01SeatReceipt(E,L))return 3;                 // a moved body is not the audited one
 L.Z={z};L.RollDeg=.5;if(Sub01SeatReceipt(E,L))return 4;
 return 0;}}'''
    run_cpp(source)


@pytest.mark.parametrize('report,chair,match', [
    (seat_report(left_posterior_thigh=(1.5, 2.2)), CHAIR, 'posterior_thigh'),       # thighs floating: no evidence
    (seat_report(buttocks=(-2.7, -1.0)), CHAIR, 'penetration'),
    (seat_report(), json.dumps({**json.loads(CHAIR), 'errors': ['two cushions']}), 'errors'),
])
def test_out_of_band_reports_never_become_evidence(report, chair, match):
    with pytest.raises(ValueError, match=match):
        adapter.build_evidence(report, chair)


@pytest.mark.parametrize('override,match', [
    ({'body_rotation_pyr': [0.0, 170.0, 0.0]}, 'yaw disagrees'),
    ({'body_scale_xyz': [1.0, 0.0, 1.0]}, '3-axis scale'),
    ({'body_scale_xyz': [1.0, 1.0]}, '3-axis scale'),
    ({'body_rotation_pyr': [float('nan'), 180, 0.0]}, 'pitch/yaw/roll'),
])
def test_evidence_needs_the_full_audited_transform(override, match):
    with pytest.raises(ValueError, match=match):
        adapter.build_evidence({**seat_report(), **override}, CHAIR)
    stated = adapter.build_evidence({**seat_report(), 'body_rotation_pyr': [0.0, 180, 0.0], 'body_scale_xyz': [1, 1, 1.0]}, CHAIR)
    assert stated['body_rotation_pyr'] == [0.0, 180, 0.0] and stated['body_scale_xyz'] == [1, 1, 1.0]


def test_write_evidence_from_server_reports(tmp_path):
    audit = tmp_path / 'private-audit'
    audit.mkdir()
    (audit / 'native-chair-surface.json').write_text(CHAIR)
    (audit / 'native-seat-contact.json').write_text(json.dumps(seat_report()))
    out = adapter.write_evidence(tmp_path)
    assert json.loads(out.read_text())['chair_revision'] == str(adapter.seat_id(CHAIR))


@pytest.fixture(scope='module')
def installed():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        (project / 'Config').mkdir()
        (project / 'Sub01HomeLab.uproject').write_text('{}')
        stage(project)
        module = project / 'Source/Sub01HomeLab'
        before = {n: (module / n).read_text() for n in ('Sub01HomeLab.h', 'Sub01HomeLab.cpp', 'Sub01HomeHands.h', 'Sub01HomeHands.cpp')}
        adapter.install_module(module)
        after = {n: (module / n).read_text() for n in before}
        yield before, after, (module / 'Sub01SeatTransition.h').read_text()


def test_install_applies_to_the_actual_staged_sources(installed):
    before, after, header = installed
    assert header == adapter.HEADER_FILE.read_text()
    h, cpp, hands_h, hands_cpp = (after[n] for n in ('Sub01HomeLab.h', 'Sub01HomeLab.cpp', 'Sub01HomeHands.h', 'Sub01HomeHands.cpp'))
    assert h.index('#include "Sub01SeatTransition.h"') < h.index('#include "Sub01HomeLab.generated.h"')
    assert 'FSub01SeatTransition SeatMachine;' in h and 'UPROPERTY(Transient) int32 SeatStartSerial=0;' in hands_h
    begin = cpp.split('void ASub01HomeCharacter::BeginPlay() {', 1)[1].split('\n}', 1)[0]
    assert begin.index('LoadHandsAssets();') < begin.index('BeginLiveHome();') < begin.index('LoadSeatTransition();')
    live = cpp.split('void ASub01HomeCharacter::UpdateLiveHome(float Dt){', 1)[1].split('\n}\n', 1)[0]
    assert live.index('UpdateNativeFeedback();') < live.index('UpdateSeatTransition(Dt);')
    gate = live.index('if(!SeatOut.MovementInput&&LiveHomePath.Num()){GetCharacterMovement()->StopMovementImmediately();')
    assert live.index('UpdateSeatTransition(Dt);') < gate < live.index('if(!LiveHomePath.Num()){if(PCBridge)PCBridge->SetOperatorFocus(')
    assert gate < live.index('AddMovementInput(')                       # a seated body cannot walk off
    tick = cpp.split('void ASub01HomeCharacter::Tick(float DeltaSeconds) {', 1)[1].split('\n}\n', 1)[0]
    assert tick.rstrip().endswith('ApplySeatAnimation(Instance);')       # after the posture's own clip choice
    # The serial start is applied after the target switch, outside it: also for an unchanged sequence.
    pre = hands_cpp.split('virtual void PreUpdate(', 1)[1].split('virtual void CacheBones()', 1)[0]
    switch = pre.split('if(Current.GetSequence()!=Hands->TargetSequence) {', 1)[1].split('\n  }\n', 1)
    assert 'SeatStartSerial' not in switch[0]
    applied = switch[1].index('if(SeatSerial!=Hands->SeatStartSerial&&Current.GetSequence()==Hands->SeatStartSequence.Get()){')
    assert applied < switch[1].index('Current.SetAccumulatedTime(Hands->SeatStartSeconds);Current.SetLoopAnimation(!Hands->SeatNoLoop);')
    assert pre.index('Hands->SeatEvaluatedSerial=SeatEvaluatedSerial;') < pre.index('SeatSerial=Hands->SeatStartSerial;')
    evaluate = hands_cpp.split('virtual bool Evaluate(FPoseContext& Output) override {', 1)[1].split('\n }\n', 1)[0]
    assert evaluate.index('Blend.Evaluate_AnyThread(Output);') < evaluate.index('SeatEvaluatedSerial=SeatSerial;') < evaluate.index('return true;')
    assert 'UPROPERTY(Transient) TObjectPtr<UAnimSequence> SeatEvaluatedSequence;' in hands_h
    # Only additions: every original line is still present, in order.
    for name, text in before.items():
        lines = [l for l in text.splitlines() if l.strip()]
        merged = after[name]
        position = 0
        for line in lines:
            position = merged.index(line, position) + len(line)


def test_added_code_never_places_the_actor_and_owns_seat_verification(installed):
    methods = adapter.CHARACTER_METHODS
    for forbidden in ('SetActorLocation', 'Teleport', 'SetWorldLocation', 'SetActorTransform', 'SetActorRotation'):
        assert forbidden not in methods
    assert methods.count('NativeSeatVerified=') == 1 and 'NativeSeatVerified=SeatOut.ContactVerified;' in methods
    assert 'if(!SeatOut.PCFocusAllowed&&PCBridge)PCBridge->SetOperatorFocus(false);' in methods
    assert 'In.Receipt=Sub01SeatReceipt(SeatEvidence,L);' in methods and 'Sub01SeatEvidenceInBand(Loaded)' in methods
    assert 'AddMovementInput(' in methods and methods.count('AddMovementInput(') == 1   # the approach leg only
    # Playback comes from what the proxy evaluated, never the requested target or a wall clock.
    assert 'In.ClipPlaying=Requested&&Instance&&Instance->SeatEvaluatedSequence==Requested' in methods
    assert 'In.ClipSerial=Instance?uint32(Instance->SeatEvaluatedSerial):0;In.ClipSeconds=Instance?Instance->SeatEvaluatedTime:0;' in methods
    assert 'TargetSequence==Requested' not in methods and 'SeatClipStartedAt' not in methods
    assert 'Instance->SeatStartSerial=int32(SeatOut.ClipSerial);' in methods
    assert 'L.PitchDeg=R.Pitch;L.YawDeg=R.Yaw;L.RollDeg=R.Roll;L.ScaleX=S.X;L.ScaleY=S.Y;L.ScaleZ=S.Z;' in methods
    # A missing install anchor refuses instead of half-applying.
    _, after, _ = installed
    with pytest.raises(ValueError):
        adapter.install({'header': after['Sub01HomeLab.h'], 'cpp': after['Sub01HomeLab.cpp'],
                         'hands_header': after['Sub01HomeHands.h'], 'hands_cpp': after['Sub01HomeHands.cpp']})
