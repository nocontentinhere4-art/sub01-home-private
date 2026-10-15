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
    assert evidence['patches']['left_posterior_thigh'] == {'min_gap_cm': -.9, 'max_median_cm': -.2, 'min_coverage': .75, 'min_band_vertices': 150}
    # The native consumer accepts exactly this evidence for the matching live pose, and nothing near it.
    p = evidence['patches']
    fill = ''.join(f'E.MinGap[{i}]={p[n]["min_gap_cm"]};E.MaxMedian[{i}]={p[n]["max_median_cm"]};E.MinCoverage[{i}]={p[n]["min_coverage"]};E.MinBandVertices[{i}]={p[n]["min_band_vertices"]};'
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
    (seat_report(), CHAIR.replace('180, -210', '212.4, -210').replace('180, -170', '212.4, -170').replace('[180, -210, 50.5], ', '[212.4, -210, 50.5], ')
     .replace('"min": [180', '"min": [212.4'), 'not the broad seat cushion'),   # a 7.6 x 40 cm lumbar-sized patch
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
    for forbidden in ('SetActorLocation', 'Teleport', 'SetActorTransform', 'SetActorRotation'):
        assert forbidden not in methods
    # The only world placement is the eased eye camera (tests/test_seat_eye_camera.py); never the actor or body.
    assert methods.count('SetWorldLocation') == 1 and 'ViewCamera->SetWorldLocation(SeatEye);' in methods
    assert methods.count('NativeSeatVerified=') == 1 and 'NativeSeatVerified=SeatOut.ContactVerified;' in methods
    assert 'if(!SeatOut.PCFocusAllowed&&PCBridge)PCBridge->SetOperatorFocus(false);' in methods
    assert 'In.Receipt=Sub01SeatReceipt(SeatEvidence,L)||Sub01SeatMeasuredReceipt(SeatMeasurement,L,In.ClipSerial,Now);' in methods
    assert methods.count('In.Receipt=') == 1 and 'Sub01SeatEvidenceInBand(Loaded)' in methods
    assert 'AddMovementInput(' in methods and methods.count('AddMovementInput(') == 1   # the approach leg only
    # Playback comes from what the proxy evaluated, never the requested target or a wall clock.
    assert 'In.ClipPlaying=Requested&&Instance&&Instance->SeatEvaluatedSequence==Requested' in methods
    assert 'In.ClipSerial=Instance?uint32(Instance->SeatEvaluatedSerial):0;In.ClipSeconds=Instance?Instance->SeatEvaluatedTime:0;' in methods
    assert 'TargetSequence==Requested' not in methods and 'SeatClipStartedAt' not in methods
    assert 'Instance->SeatStartSerial=int32(SeatOut.ClipSerial);' in methods
    assert 'L.PitchDeg=R.Pitch;L.YawDeg=R.Yaw;L.RollDeg=R.Roll;L.ScaleX=S.X;L.ScaleY=S.Y;L.ScaleZ=S.Z;' in methods


def test_live_measurement_settle_and_profile_gate():
    methods = adapter.CHARACTER_METHODS
    body = methods.split('bool ASub01HomeCharacter::SeatLiveBody(FSub01SeatLivePose& L) const{', 1)[1].split('\n}\n', 1)[0]
    # Only the capsule-attached rendered body has a transform: no camera parent, no diagnostic placement.
    assert body.lstrip().startswith('if(!FirstPersonBody||!FirstPersonBody->GetSkeletalMeshAsset()||HandsDiagnosticSeat||FirstPersonBody->GetAttachParent()!=GetRootComponent())return false;')
    # The live skin is measured at the actual transform and evaluated pose against the audited
    # cushion; each sole against the surface traced under its own footprint, never the capsule floor.
    measure = methods.split('if(L.ClipPlaying&&SeatCushionTriangles.Num()&&Now-SeatMeasuredAt>=.2){', 1)[1].split('\n  In.Receipt=', 1)[0]
    assert 'CurrentFloor' not in methods
    assert 'M.SoleSupportVerified[Side]=SeatSoleSupport(Side,M.SoleFloorZ[Side],Surfaces[Side]);' in measure
    assert 'AnalyzeCapturedSeatSkin(FirstPersonBody->GetSkeletalMeshAsset(),FirstPersonBody->GetComponentSpaceTransforms(),FirstPersonBody->GetComponentTransform(),SeatCushionTriangles,M.SoleFloorZ[Side])' in measure
    assert 'if(I==3+(1-Side)||(Side==1&&I<3))continue;' in measure
    assert 'M.ClipSerial=In.ClipSerial;M.MeasuredAt=Now;' in measure and 'M.X=L.X;' in measure and 'Over<=0){Complete=false;break;}' in measure
    sole = methods.split('bool ASub01HomeCharacter::SeatSoleSupport(int32 Side,double& FloorZ,FString& Surface) const{', 1)[1].split('\n}\n', 1)[0]
    assert 'const FVector Points[3]={A,(A+B)/2,B};' in sole and 'FCollisionQueryParams Params(TEXT("Sub01SoleSupport"),true,this);' in sole
    assert 'Hit.bStartPenetrating||Hit.ImpactNormal.Z<.98)return false;' in sole and 'if(Component&&Hit.GetComponent()!=Component)return false;' in sole
    assert 'if(!Component||High-Low>.2)return false;' in sole
    # Only the broad connected cushion makes the chair measured (the lumbar patch is refused).
    assert 'SeatChairMeasured=SeatCushionTriangles.Num()>=3&&Area>=1000&&Cushion.IsValid;' in methods
    assert methods.count('SeatChairMeasured=true') == 0
    # The settle is bounded, horizontal, swept, and runs only in the standing turn-in-place phase.
    settle = methods.split('if(SeatOut.SettleMove&&HasBody){', 1)[1].split('\n  }\n', 1)[0]
    assert 'FMath::Min3(Distance,.25f,15.f*FMath::Min(Dt,.1f))' in settle and 'SeatSettleTravel+Step2<=15.f' in settle
    assert 'MoveUpdatedComponent(FVector(To.X/Distance*Step2,To.Y/Distance*Step2,0),GetActorQuat(),true,&Hit)' in settle
    assert 'if(Hit.bBlockingHit||Hit.bStartPenetrating)SeatSettleBlocked=true;' in settle
    turn = methods.split(' else if(SeatOut.TurnInPlace&&Controller){', 1)[1]
    assert methods.index('if(!SeatOut.MovementInput)GetCharacterMovement()->StopMovementImmediately();') < methods.index('if(SeatOut.SettleMove&&HasBody){')
    assert methods.count('MoveUpdatedComponent(') == 1 and 'MoveUpdatedComponent(' in turn
    assert 'In.SettleErrorCm=FVector2D(SeatEvidence.X-Live.X,SeatEvidence.Y-Live.Y).Size();In.YawErrorDeg=FMath::FindDeltaAngleDegrees(Live.YawDeg,SeatEvidence.YawDeg);' in methods
    # Typing (and so PC focus) only with the accepted profile bound and the live body at its transform.
    assert ('In.TypingProfileReady=Instance&&TypingClip&&Instance->ContactSequence==TypingClip&&Instance->ContactTimes.Num()==301'
            '&&Instance->ContactLocalTransforms.Num()==301*6\n  &&SeatProfilePoseLoaded&&HasBody&&Sub01SeatSameTransform(SeatProfilePose,Live);') in methods
    assert methods.index('In.TypingProfileReady=') < methods.index('SeatOut=SeatMachine.Tick(In);')
    # The renderer's posture gate is never bypassed.
    assert 'ValidatedHandsPostures.Contains(FName(Role.Key))' in methods
    assert 'In.RolesAvailable=PostureGate?SeatRoles:0;' in methods and 'const bool PostureGate=HandsFailure.IsEmpty()&&HandsPosture==TEXT("Walk");' in methods
    assert 'if(!Instance||SeatOut.Clip==ESub01SeatClip::None||!HandsFailure.IsEmpty()||HandsPosture!=TEXT("Walk"))return;' in methods



def test_no_raw_keyboard_fallback_in_the_staged_proxy(installed):
    before, after, _ = installed
    # The proxy's contact-profile path is untouched; raw typing is prevented by never requesting it.
    for name in ('Sub01HomeHands.cpp',):
        evaluate = after[name].split('virtual bool Evaluate(FPoseContext& Output) override {', 1)[1].split('\n }\n', 1)[0]
        original = before[name].split('virtual bool Evaluate(FPoseContext& Output) override {', 1)[1].split('\n }\n', 1)[0]
        assert 'ContactAllowed' not in after[name] and evaluate.replace(adapter.PROXY_EVALUATED, '') == original


def test_actual_imported_seating_assets_bind_to_semantic_roles(installed):
    # The editor imported these exact names; the transition's semantic names stay unchanged.
    cpp = installed[1]['Sub01HomeLab.cpp']
    bindings = cpp.split(' struct FSeatRoleBinding', 1)[1].split(' for(const auto& Role:Roles)', 1)[0]
    source = ('#include <cstdio>\n#include <cstdint>\n#include "Sub01SeatTransition.h"\n'
              'using TCHAR=char;using uint32=uint32_t;\n#define TEXT(x) x\nint main(){struct FSeatRoleBinding'
              + bindings + 'for(const auto& r:Roles)std::printf("%s:%s:%u\\n",r.Key,r.Asset,r.Value);return 0;}')
    assert run_cpp(source).splitlines() == ['StandToSit:SitDown:1', 'Sitting:Sitting:2',
                                           'SitToType:SitToType:4', 'SitToStand:GetUp:16']
    load = cpp.split('void ASub01HomeCharacter::LoadSeatTransition(){', 1)[1].split(' // Chair:', 1)[0]
    assert 'Role.Asset,Role.Asset' in load
    assert 'Clip->GetSkeleton()==Mesh->GetSkeleton()&&ValidatedHandsPostures.Contains(FName(Role.Key))' in load
    assert 'SeatClips.Add(FName(Role.Key),Clip)' in load


# ---------------------------------------------------------------- seated typing clip evidence
SEATED = adapter.seated_fit_object_path(adapter.SEATED_TYPING_ROLE)


def seated_receipt(**override):
    row = {'role': adapter.SEATED_TYPING_ROLE, 'object_path': SEATED, 'accepted': True, 'fit_pass': True, 'imported': True,
           'same_existing_skeleton': True, 'fps': 60, 'glb_sha256': 'a' * 64, 'fbx_sha256': 'f' * 64}
    row.update(override)
    return {'schema': adapter.SEATED_FIT_RECEIPT_SCHEMA, 'skeleton': adapter.OWNER_SKELETON, 'clips': [row]}


def seated_clip(**override):
    clip = {'role': adapter.SEATED_TYPING_ROLE, 'object_path': SEATED, 'glb_sha256': 'a' * 64, 'fbx_sha256': 'f' * 64, 'rate_hz': 60}
    clip.update(override)
    return clip


def seated_project(tmp_path, report, receipt=None):
    audit = tmp_path / 'private-audit'
    audit.mkdir(exist_ok=True)
    (audit / 'native-chair-surface.json').write_text(CHAIR)
    (audit / 'native-seat-contact.json').write_text(json.dumps(report))
    if receipt is not False:
        (tmp_path / adapter.SEATED_FIT_RECEIPT).write_text(json.dumps(receipt or seated_receipt()))
    return tmp_path


def test_seated_report_stamps_the_seated_clip_the_native_receipt_accepts(tmp_path):
    project = seated_project(tmp_path, {**seat_report(), 'clip': seated_clip()})
    evidence = json.loads(adapter.write_evidence(project).read_text())
    assert evidence['clip'] == SEATED and evidence['clip_id'] == str(adapter.seat_id(SEATED))
    assert evidence['clip_role'] == adapter.SEATED_TYPING_ROLE
    assert evidence['clip_glb_sha256'] == 'a' * 64 and evidence['clip_fbx_sha256'] == 'f' * 64
    receipt_raw = (project / adapter.SEATED_FIT_RECEIPT).read_bytes()
    assert evidence['seated_fit_receipt_sha256'] == __import__('hashlib').sha256(receipt_raw).hexdigest()
    assert evidence['native_seat_verified'] is False and evidence['time_range_s'] == [3.0, 8.0]
    # Sub01SeatReceipt: the live L.ClipId is Sub01SeatId(<clip bound in the DeskTyping slot>->GetPathName()).
    p = evidence['patches']
    fill = ''.join(f'E.MinGap[{i}]={p[n]["min_gap_cm"]};E.MaxMedian[{i}]={p[n]["max_median_cm"]};E.MinCoverage[{i}]={p[n]["min_coverage"]};E.MinBandVertices[{i}]={p[n]["min_band_vertices"]};'
                   for i, n in enumerate(adapter.PATCHES))
    x, y, z = evidence['body_cm']
    run_cpp(f'''#include "Sub01SeatTransition.h"
int main(){{FSub01SeatEvidence E;E.Loaded=true;E.Family=ESub01SeatFamily::DeskTyping;
 E.MeshId={evidence["mesh_id"]}ull;E.ClipId={evidence["clip_id"]}ull;E.ChairRevision={evidence["chair_revision"]}ull;
 E.X={x};E.Y={y};E.Z={z};E.PitchDeg=0;E.YawDeg=180;E.RollDeg=0;E.ScaleX=E.ScaleY=E.ScaleZ=1;E.T0=3;E.T1=8;{fill}
 FSub01SeatLivePose L;L.MeshId=Sub01SeatId("{adapter.OWNER_MESH}");L.ClipId=Sub01SeatId("{SEATED}");L.Family=ESub01SeatFamily::DeskTyping;
 L.ChairRevision={evidence["chair_revision"]}ull;L.X={x};L.Y={y};L.Z={z};L.PitchDeg=0;L.YawDeg=180;L.RollDeg=0;L.ScaleX=L.ScaleY=L.ScaleZ=1;L.ClipSeconds=6;L.ClipPlaying=true;
 if(!Sub01SeatReceipt(E,L))return 1;                                   // the seated clip bound in the slot
 L.ClipId=Sub01SeatId("{adapter.TYPING_CLIP}");if(Sub01SeatReceipt(E,L))return 2;   // the old clip is another clip
 return 0;}}''')


@pytest.mark.parametrize('clip,receipt,match', [
    (seated_clip(glb_sha256='b' * 64), None, 'glb_sha256'),
    (seated_clip(fbx_sha256='e' * 64), None, 'fbx_sha256'),
    (seated_clip(rate_hz=30), None, 'rate_hz'),
    (seated_clip(role='SeatedIdle'), None, 'role'),
    (seated_clip(object_path='/Game/Sub01Hands/Seating/SUB01_SeatedIdle.SUB01_SeatedIdle'), None, 'neither'),
    (SEATED, None, 'neither'),                                                       # a bare path carries no shas
    (seated_clip(), seated_receipt(accepted=False), 'accepted'),
    (seated_clip(), seated_receipt(fit_pass=False), 'fit_pass'),
    (seated_clip(), seated_receipt(same_existing_skeleton=False), 'same_existing_skeleton'),
    (seated_clip(), seated_receipt(object_path='/Game/Elsewhere/SUB01_DeskTypingSeated.SUB01_DeskTypingSeated'), 'object_path'),
    (seated_clip(), seated_receipt(fps=30), 'fps'),
    (seated_clip(), seated_receipt(fbx_sha256=None), 'fbx_sha256'),
    (seated_clip(), {**seated_receipt(), 'skeleton': '/Game/Other.Other'}, 'owner skeleton'),
    (seated_clip(), {**seated_receipt(), 'clips': seated_receipt()['clips'] * 2}, 'exactly one'),
])
def test_seated_report_refused_unless_it_matches_the_accepted_receipt_row(tmp_path, clip, receipt, match):
    project = seated_project(tmp_path, {**seat_report(), 'clip': clip}, receipt)
    with pytest.raises(ValueError, match=match):
        adapter.write_evidence(project)
    assert not (project / 'private-audit/native-seat-evidence.json').exists()


def test_seated_report_refused_without_a_receipt(tmp_path):
    project = seated_project(tmp_path, {**seat_report(), 'clip': seated_clip()}, receipt=False)
    with pytest.raises(FileNotFoundError):
        adapter.write_evidence(project)
    assert not (project / 'private-audit/native-seat-evidence.json').exists()


@pytest.mark.parametrize('clip', [None, adapter.TYPING_CLIP, {'object_path': adapter.TYPING_CLIP}])
def test_original_clip_reports_unchanged(tmp_path, clip):
    report = seat_report() if clip is None else {**seat_report(), 'clip': clip}
    project = seated_project(tmp_path, report, receipt=False)     # the old path never reads the receipt
    evidence = json.loads(adapter.write_evidence(project).read_text())
    assert evidence == json.loads(json.dumps(adapter.build_evidence(seat_report(), CHAIR)))
    assert evidence['clip'] == adapter.TYPING_CLIP and evidence['clip_id'] == str(adapter.seat_id(adapter.TYPING_CLIP))
    assert 'clip_glb_sha256' not in evidence


def test_failing_seated_contact_is_still_refused(tmp_path):
    project = seated_project(tmp_path, {**seat_report(left_posterior_thigh=(1.5, 2.2)), 'clip': seated_clip()})
    with pytest.raises(ValueError, match='posterior_thigh'):
        adapter.write_evidence(project)
    assert not (project / 'private-audit/native-seat-evidence.json').exists()


# ------------------------------------------------------------------ committed seated-fit verdicts (receipt alone never binds)
import unreal_import_seated_fit_fbx as seated_fit  # noqa: E402

PASSING = ('SeatedIdle', 'SitDownSeated', 'GetUpSeated')
FAILING = ('DeskTypingSeated', 'SitToTypeSeated', 'TypeToSitSeated')
SLOT_OF = {role: slot for role, (slot, _) in adapter.SEATED_FIT_SLOTS.items()}


def genuine_receipt():
    """Rows exactly as the importer writes them for the committed fit (failed fits: not imported, not accepted)."""
    rows = [{'role': r['role'], 'object_path': adapter.seated_fit_object_path(r['role']), 'glb_sha256': r['glb_sha256'],
             'fbx_sha256': 'f' * 64, 'fit_pass': r['fit_pass'], 'imported': r['fit_pass'], 'accepted': r['fit_pass'],
             'same_existing_skeleton': True} for r in seated_fit.plan_clips()]
    return {'schema': adapter.SEATED_FIT_RECEIPT_SCHEMA, 'skeleton': adapter.OWNER_SKELETON, 'clips': rows}


def forged(receipt, role, **change):
    out = copy.deepcopy(receipt)
    for row in out['clips']:
        if row['role'] == role:
            row.update(change)
    return out


def test_committed_verdicts_are_plan_clips_and_the_table_is_deterministic():
    verdicts = adapter.committed_seated_fit_verdicts()
    assert verdicts == {r['role']: {'glb_sha256': r['glb_sha256'], 'all_gates_pass': r['fit_pass']} for r in seated_fit.plan_clips()}
    assert sorted(r for r, v in verdicts.items() if v['all_gates_pass']) == sorted(PASSING)
    assert all(verdicts[r]['glb_sha256'] == seated_fit.GLB_SHA256[r] for r in verdicts)
    table = adapter.seated_fit_verdict_table_cpp(verdicts)
    assert table == adapter.seated_fit_verdict_table_cpp(dict(reversed(list(verdicts.items()))))   # order-independent
    assert table == adapter.seated_fit_verdict_table_cpp(adapter.committed_seated_fit_verdicts())
    assert table.startswith('{"DeskTypingSeated","%s",false},' % seated_fit.GLB_SHA256['DeskTypingSeated'])
    assert table.count('true') == 3 and table.count('false') == 3 and '@@' not in table


@pytest.mark.parametrize('bad', [
    lambda v: v.pop('SeatedIdle'),
    lambda v: v['GetUpSeated'].update(glb_sha256='A' * 64),
    lambda v: v['GetUpSeated'].update(glb_sha256='a' * 63),
    lambda v: v['GetUpSeated'].update(all_gates_pass=1),
    lambda v: v.update(Sitting={'glb_sha256': 'a' * 64, 'all_gates_pass': True}),
])
def test_table_generation_refuses_an_incomplete_or_malformed_verdict_set(bad):
    verdicts = copy.deepcopy(adapter.committed_seated_fit_verdicts())
    bad(verdicts)
    with pytest.raises(RuntimeError, match=adapter.SEATED_FIT_VERDICTS_UNAVAILABLE):
        adapter.seated_fit_verdict_table_cpp(verdicts)


def test_plan_clips_refusal_generates_nothing_installs_nothing_and_binds_nothing(monkeypatch):
    receipt = genuine_receipt()

    def refuse(*_):
        raise RuntimeError('SUB01_SeatedIdle.glb is not the committed fit GLB')
    monkeypatch.setattr(seated_fit, 'plan_clips', refuse)
    with pytest.raises(RuntimeError, match='committed seated-fit verdicts unavailable: SUB01_SeatedIdle.glb'):
        adapter.committed_seated_fit_verdicts()
    sources = {'header': '#include "Sub01HomeLab.generated.h"\n void Forward(float Value);\n',
               'cpp': ' BeginLiveHome();\n UpdateNativeFeedback();\n if(!LiveHomePath.Num()){if(PCBridge)PCBridge->SetOperatorFocus(\n '
                      + adapter.SEAT_RATE_ANCHOR,
               'hands_header': ' protected:\n', 'hands_cpp': ' float Progress=1;\n  Current.SetPlayRate(Hands->TargetRate);\n  Blend.Evaluate_AnyThread(Output);\n'}
    with pytest.raises(RuntimeError, match='verdicts unavailable'):
        adapter.install(sources)
    bound = adapter.seated_fit_bindings(receipt, set(adapter.SEATED_FIT_SLOTS))
    assert not any(v['bound'] for v in bound.values())
    assert {v['refusal'] for k, v in bound.items() if v['role'] in PASSING} == {adapter.SEATED_FIT_VERDICTS_UNAVAILABLE}


def test_genuine_rows_bind_only_the_passing_committed_fits():
    bound = adapter.seated_fit_bindings(genuine_receipt(), set(adapter.SEATED_FIT_SLOTS))
    for role in PASSING:
        assert bound[SLOT_OF[role]] == {'bound': True, 'role': role, 'object_path': adapter.seated_fit_object_path(role)}
    assert not bound['DeskTyping']['bound'] and not bound['SitToType']['bound']


@pytest.mark.parametrize('role', PASSING + FAILING[:2])
@pytest.mark.parametrize('change, passing_refusal', [
    ({'fit_pass': False}, 'fit gates failed or row not accepted'),
    ({'accepted': False}, 'fit gates failed or row not accepted'),
    ({'glb_sha256': 'b' * 64}, adapter.SEATED_FIT_UNCOMMITTED),
    ({'glb_sha256': None}, adapter.SEATED_FIT_UNCOMMITTED),
    ({'glb_sha256': ''}, adapter.SEATED_FIT_UNCOMMITTED),
])
def test_forged_receipt_rows_never_bind(role, change, passing_refusal):
    receipt = genuine_receipt()
    if role in FAILING:   # a failed fit relabelled as an accepted, passing import of the committed GLB
        receipt = forged(receipt, role, fit_pass=True, accepted=True, imported=True)
        refusal = adapter.SEATED_FIT_UNCOMMITTED
        assert adapter.seated_fit_bindings(receipt, {role})[SLOT_OF[role]]['refusal'] == refusal
        if change.get('fit_pass') is False or change.get('accepted') is False:
            refusal = 'fit gates failed or row not accepted'
    else:
        refusal = passing_refusal
    out = adapter.seated_fit_bindings(forged(receipt, role, **change), set(adapter.SEATED_FIT_SLOTS))[SLOT_OF[role]]
    assert out == {'bound': False, 'role': role, 'refusal': refusal}


@pytest.mark.parametrize('role', PASSING)
def test_missing_rows_and_forged_verdict_tables_never_bind(role):
    receipt = genuine_receipt()
    receipt['clips'] = [r for r in receipt['clips'] if r['role'] != role]
    assert adapter.seated_fit_bindings(receipt, {role})[SLOT_OF[role]]['refusal'] == 'role not in the import receipt'
    # a verdict table that lacks the role (or calls it failing) refuses a genuine row
    verdicts = copy.deepcopy(adapter.committed_seated_fit_verdicts())
    verdicts[role]['all_gates_pass'] = False
    assert adapter.seated_fit_bindings(genuine_receipt(), {role}, verdicts)[SLOT_OF[role]]['refusal'] == adapter.SEATED_FIT_UNCOMMITTED
    verdicts.pop(role)
    assert adapter.seated_fit_bindings(genuine_receipt(), {role}, verdicts)[SLOT_OF[role]]['refusal'] == adapter.SEATED_FIT_UNCOMMITTED


def test_compiled_verdict_check_mirrors_python_over_genuine_and_forged_rows():
    verdicts = adapter.committed_seated_fit_verdicts()
    table = adapter.seated_fit_verdict_table_cpp(verdicts)
    cases = []
    for role in list(verdicts) + ['Sitting', 'SeatedIdl', 'SeatedIdleX', '']:
        sha = verdicts.get(role, {}).get('glb_sha256', 'a' * 64)
        for accepted in (True, False):
            for fit_pass in (True, False):
                for glb in (sha, 'b' * 64, sha[:-1], sha.upper(), ''):
                    cases.append((role, accepted, fit_pass, glb))
    expected = [adapter.seated_fit_committed(verdicts, *c) for c in cases]
    assert sum(expected) == 3                     # exactly the three genuine passing rows
    rows = ','.join('{u"%s",%s,%s,u"%s"}' % (r, 'true' if a else 'false', 'true' if f else 'false', g) for r, a, f, g in cases)
    out = run_cpp('#include <cstdio>\n#include "Sub01SeatTransition.h"\n'
                  'static const FSub01SeatedFitVerdict Table[]={' + table + '};\n'
                  'struct Row{const char16_t* Role;bool A,F;const char16_t* Glb;};static const Row Rows[]={' + rows + '};\n'
                  'int main(){for(const Row& R:Rows)std::printf("%d",Sub01SeatedFitCommitted(Table,int(sizeof(Table)/sizeof(Table[0])),R.Role,R.A,R.F,R.Glb)?1:0);'
                  # duplicated, empty or malformed tables refuse even a genuine row
                  'const FSub01SeatedFitVerdict Dup[]={{"SeatedIdle","' + verdicts['SeatedIdle']['glb_sha256'] + '",true},{"SeatedIdle","'
                  + verdicts['SeatedIdle']['glb_sha256'] + '",true}};'
                  'const FSub01SeatedFitVerdict Short[]={{"SeatedIdle","abc",true}};'
                  'std::printf(" %d%d%d%d",Sub01SeatedFitCommitted(Dup,2,u"SeatedIdle",true,true,u"' + verdicts['SeatedIdle']['glb_sha256'] + '")?1:0,'
                  'Sub01SeatedFitCommitted(Table,0,u"SeatedIdle",true,true,u"' + verdicts['SeatedIdle']['glb_sha256'] + '")?1:0,'
                  'Sub01SeatedFitCommitted(Short,1,u"SeatedIdle",true,true,u"abc")?1:0,'
                  'Sub01SeatedFitCommitted(Table,6,"SeatedIdle",true,true,"' + verdicts['SeatedIdle']['glb_sha256'] + '")?1:0);return 0;}')
    flags, extra = out.split(' ')
    assert [c == '1' for c in flags] == expected
    assert extra == '0001'                        # plain char strings work too


def test_installed_binders_require_the_committed_verdict(installed):
    _, after, header = installed
    assert 'Sub01SeatedFitCommitted' in header
    load = after['Sub01HomeLab.cpp'].split('void ASub01HomeCharacter::LoadSeatTransition(){', 1)[1].split('\n}\n', 1)[0]
    table = adapter.seated_fit_verdict_table_cpp(adapter.committed_seated_fit_verdicts())
    assert load.count(' static const FSub01SeatedFitVerdict SeatedFitVerdicts[]={' + table + '};') == 1
    fit_block = load.split('struct FSeatFitSlot', 1)[1].split(' // Chair:', 1)[0]
    assert ('if((*Row)->TryGetStringField(TEXT("glb_sha256"),Glb)&&Sub01SeatedFitCommitted(SeatedFitVerdicts,SeatedFitVerdictCount,S.Role,A,P,*Glb))'
            'Accepted=true;') in fit_block
    assert fit_block.count('Accepted=true') == 1
    typing = load.split(' // Seated typing profile (tools/desk_typing_seated_contact_profile.py).', 1)[1]
    assert 'TypingCommitted=Sub01SeatedFitCommitted(SeatedFitVerdicts,SeatedFitVerdictCount,TEXT("DeskTypingSeated"),A,F,*TypingGlb);' in typing
    assert f'else if(!TypingCommitted)TypingWhy=TEXT("{adapter.SEATED_TYPING_UNCOMMITTED}");' in typing
    # the refusal precedes the only place a profile is bound
    assert typing.index('else if(!TypingCommitted)') < typing.index('TypingHands->ContactSequence=SeatedTyping;')
    assert '@@' not in after['Sub01HomeLab.cpp']
