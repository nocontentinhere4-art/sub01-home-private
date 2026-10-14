"""Native life clips: real-file inventory, binding/bed gates, engine-free machine, staged install."""
import copy
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import inventory_native_life_clips as inv  # noqa: E402
import unreal_life_clips_runtime as life  # noqa: E402
from stage_unreal_home_runtime import stage  # noqa: E402

COMMITTED = ROOT / 'docs/proposed/native-life-clips-inventory.json'


# ---------------------------------------------------------------- inventory (actual files)
@pytest.fixture(scope='module')
def report():
    return inv.inventory()


def row(report, file, role=None):
    rows = [r for r in report['candidates'] if r['file'] == file and (role is None or r['role'] == role)]
    assert len(rows) == 1, file
    return rows[0]


def test_owner_is_the_65_bone_skeleton(report):
    assert report['owner']['joint_count'] == 65 and report['owner']['skin_joints_equal_bones'] is True
    assert report['owner']['native_asset'] == '/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner'


def test_no_standing_idle_exists_on_the_owner_skeleton(report):
    assert report['accepted_by_role']['Idle'] == [] and 'Idle' in report['missing_roles']
    idle = [r for r in report['candidates'] if r['role'] == 'Idle']
    assert idle and all(r['verdict'] == 'SkeletonMismatch' for r in idle)
    # The only idle-shaped owner clip is an activity (standing texting), never an idle substitute.
    assert report['idle_shaped_in_scan'] == ['web/house/assets/first-person/texting.glb']
    seated = [r for r in report['owner_skeleton_scan'] if r['file'] == 'web/room/mh_mx/room_seated_idle.glb']
    assert seated and seated[0]['postures'] == ['sitting_or_crouching']


def test_bed_transitions_are_measured_but_their_provenance_is_unverified(report):
    lie = row(report, 'web/room/mh_mx/room_bed_lie.glb')
    assert lie['skeleton']['same_owner_skeleton'] and lie['skeleton']['joint_count'] == 65
    assert lie['duration_s'] == pytest.approx(16.966667, abs=1e-5) and lie['frame_rate_hz'] == pytest.approx(30, abs=1e-3)
    assert (lie['posture']['first'], lie['posture']['last']) == ('standing', 'lying_supine')
    assert lie['loop']['loops'] is False and lie['verdict'] == 'ProvenanceUnverified'
    assert lie['max_bone_translation_drift_from_owner_rest_cm'] > 5     # carried-over joint positions, not bone-for-bone
    assert lie['posture_samples'][-1]['hips_height_m'] == pytest.approx(.69, abs=.01)
    wake = row(report, 'web/room/mh_mx/room_bed_wake.glb')
    assert (wake['posture']['first'], wake['posture']['last']) == ('lying_supine', 'standing')
    assert wake['verdict'] == 'ProvenanceUnverified'
    assert row(report, 'web/room/mh_mx/room_bedtime.glb')['verdict'] == 'ProvenanceUnverified'
    assert report['accepted_by_role']['LieDown'] == [] and report['accepted_by_role']['GetUp'] == []


def test_sleep_loops_on_the_owner_skeleton_and_their_lying_pose(report):
    for name, kind in (('sleep_side', 'lying_side'), ('sleep_back', 'lying_supine'), ('sleep_back_idle', 'lying_supine')):
        r = row(report, f'web/room/desk_states/bed/{name}.glb')
        assert r['skeleton']['same_owner_skeleton'] and r['skeleton']['max_rest_trs_error'] <= inv.REST_TOLERANCE
        assert r['posture']['all'] == [kind] and r['loop']['loops'] is True and r['verdict'] == 'Candidate'
        assert r['hips_local_cm']['max_horizontal_from_first'] < 1
        assert all(p['torso_tilt_from_vertical_deg'] > 60 for p in r['posture_samples'])
    assert row(report, 'web/room/desk_states/bed/sleep_back_idle.glb')['duration_s'] == pytest.approx(6.0, abs=1e-5)
    roll = row(report, 'web/room/desk_states/bed/sleep_roll_to_back.glb')
    assert roll['verdict'] == 'NotLooping' and (roll['posture']['first'], roll['posture']['last']) == ('lying_side', 'lying_supine')
    # Mixamo sleep captures exist only on the v5 rig: reported, never retargeted here.
    assert row(report, 'web/room/mh_v5/room_sleeping_idle.glb')['verdict'] == 'SkeletonMismatch'
    assert report['missing_roles'] == ['GetUp', 'Idle', 'LieDown']
    assert report['native_bed_surface_report'] is None


def test_chain_gaps_are_reported(report):
    gaps = report['chain_continuity']
    assert gaps['room_bed_lie -> sleep_back_idle']['body_shape_max_delta_cm'] > 30
    assert gaps['room_bed_lie -> room_bed_wake']['body_shape_max_delta_cm'] > 10


def test_a_changed_rest_pose_or_name_is_a_skeleton_mismatch():
    owner = inv.owner_reference()
    doc, _, _ = inv.read_glb(ROOT / 'web/room/desk_states/bed/sleep_side.glb')
    assert inv.owner_skeleton_check(doc, owner)['same_owner_skeleton']
    moved = copy.deepcopy(doc)
    bone = next(n for n in moved['nodes'] if n.get('name') == 'mixamorig:LeftForeArm')
    bone['translation'][1] += .5
    check = inv.owner_skeleton_check(moved, owner)
    assert not check['same_owner_skeleton'] and 'rest pose differs' in check['errors'][0]
    renamed = copy.deepcopy(doc)
    next(n for n in renamed['nodes'] if n.get('name') == 'mixamorig:Head')['name'] = 'Head'
    assert not inv.owner_skeleton_check(renamed, owner)['same_owner_skeleton']


def test_an_operator_fbx_without_the_owner_skeleton_is_refused():
    report = inv.inventory([('Idle', 'docs/design/chair-tripo/chair_owner_raw.fbx')])
    r = row(report, 'docs/design/chair-tripo/chair_owner_raw.fbx')
    assert r['provenance'] == 'operator_declared_capture' and r['verdict'] == 'SkeletonMismatch'
    assert report['accepted_by_role']['Idle'] == []


def test_inventory_is_deterministic_and_matches_the_committed_copy(report):
    text = json.dumps(report, indent=1, sort_keys=True) + '\n'
    assert text == json.dumps(inv.inventory(), indent=1, sort_keys=True) + '\n'
    if COMMITTED.exists():
        assert COMMITTED.read_text() == text


# ---------------------------------------------------------------- binding gate (config fragment)
def idle_inventory(**override):
    """A gate test input: an Idle candidate record as the inventory would write one (not a clip)."""
    record = {'role': 'Idle', 'file': 'SourceAssets/Breathing_Idle.fbx', 'sha256': 'a' * 64, 'verdict': 'Candidate',
              'skeleton': {'same_owner_skeleton': True}, 'loop': {'loops': True}, 'duration_s': 4.0}
    record.update(override)
    return {'candidates': [record]}


def idle_import(**override):
    clip = {'role': 'Idle', 'object_path': life.clip_object_path('Idle'), 'inventory_sha256': 'a' * 64,
            'same_existing_skeleton': True, 'duration_s': 4.0}
    clip.update(override)
    return {'clips': [clip]}


def test_real_inventory_binds_nothing_and_says_why(report):
    text, refusals = life.config_fragment(report, {'clips': []})
    assert text == ''
    assert refusals['Idle']['refusal'] == 'SkeletonMismatch'
    assert refusals['LieDown']['refusal'] == 'ClipMissing' and refusals['GetUp']['refusal'] == 'ClipMissing'
    assert refusals['SleepLoop']['refusal'] == 'NotImported'


def test_idle_binds_only_with_a_proven_owner_loop():
    text, refusals = life.config_fragment(idle_inventory(), idle_import())
    assert text == ('[/Script/Sub01HomeLab.Sub01HomeCharacter]\nIdleClipPath=/Game/Sub01Hands/Life/SUB01_Idle.SUB01_Idle\n'
                    '+ValidatedHandsPostures=Idle\n')
    assert 'Idle' not in refusals and 'WalkClipPath' not in text and 'HandsMeshPath' not in text


@pytest.mark.parametrize('inventory,imported,refusal', [
    (idle_inventory(loop={'loops': False}), idle_import(), 'NotLooping'),
    (idle_inventory(), idle_import(same_existing_skeleton=False), 'SkeletonMismatch'),
    (idle_inventory(skeleton={'same_owner_skeleton': False}), idle_import(), 'SkeletonMismatch'),
    (idle_inventory(), idle_import(inventory_sha256='b' * 64), 'ClipMissing'),
    (idle_inventory(), idle_import(object_path='/Game/Other/Idle.Idle'), 'ClipMissing'),
    (idle_inventory(), idle_import(duration_s=6.0), 'ClipMissing'),
    (idle_inventory(verdict='ProvenanceUnverified'), idle_import(), 'ClipMissing'),
    (idle_inventory(), {'clips': []}, 'NotImported'),
])
def test_idle_refusals(inventory, imported, refusal):
    text, refusals = life.config_fragment(inventory, imported)
    assert text == '' and refusals['Idle']['refusal'] == refusal


def test_bed_binds_all_three_or_nothing(report):
    sleep = row(report, 'web/room/desk_states/bed/sleep_back_idle.glb')
    imported = {'clips': [{'role': 'SleepLoop', 'object_path': life.clip_object_path('SleepLoop'), 'inventory_sha256': sleep['sha256'],
                           'same_existing_skeleton': True, 'duration_s': sleep['duration_s']}]}
    text, refusals = life.config_fragment(report, imported)
    assert text == '' and refusals['SleepLoop']['refusal'] == 'ClipMissing' and 'LieDown' in refusals['SleepLoop']['reason']
    # With accepted LieDown/GetUp records (gate input only) all three bind together.
    full = copy.deepcopy(report)
    for role in ('LieDown', 'GetUp'):
        full['candidates'].append({'role': role, 'file': f'{role}.fbx', 'sha256': role[0] * 64, 'verdict': 'Candidate',
                                   'skeleton': {'same_owner_skeleton': True}, 'loop': {'loops': False}, 'duration_s': 10.0})
        imported['clips'].append({'role': role, 'object_path': life.clip_object_path(role), 'inventory_sha256': role[0] * 64,
                                  'same_existing_skeleton': True, 'duration_s': 10.0})
    text, refusals = life.config_fragment(full, imported)
    assert text.splitlines()[1:] == ['+ValidatedHandsPostures=LieDown', '+ValidatedHandsPostures=SleepLoop', '+ValidatedHandsPostures=GetUp']
    assert set(refusals) == {'Idle'}


# ---------------------------------------------------------------- bed evidence gate
def bed_text(width=150, length=200):
    return json.dumps({'errors': [], 'bed': {'component': '/Game/Sub01Home/ActualHome.QueenBed:Mattress', 'sections': [{
        'vertices_world_cm': [[-200, -300, 55], [-200 + width, -300, 55], [-200 + width, -300 + length, 55], [-200, -300 + length, 55]],
        'mattress_surface': {'triangle_indices': [[0, 1, 2], [0, 2, 3]]}}]}})


def placement(text, **override):
    doc = {'schema': 'sub01.native-life-bed-evidence.v1', 'bed_revision': str(life.life_id(text)),
           'approach_cm': [-120.0, -330.0], 'yaw_deg': 90.0, 'accepted': True}
    doc.update(override)
    return doc


def test_bed_gate():
    text = bed_text()
    assert life.validate_bed(text, placement(text))['area_cm2'] == pytest.approx(30000)
    with pytest.raises(ValueError, match='BedUnmeasured'):
        life.validate_bed(json.dumps({**json.loads(text), 'errors': ['two mattresses']}), placement(text))
    with pytest.raises(ValueError, match='BedUnmeasured'):
        life.validate_bed(bed_text(40, 60), None)                      # a pillow-sized patch is not a bed
    with pytest.raises(ValueError, match='BedPlacementMissing'):
        life.validate_bed(text, None)
    with pytest.raises(ValueError, match='BedPlacementMissing'):
        life.validate_bed(text, placement(bed_text(151)))              # measured against another report
    with pytest.raises(ValueError, match='BedPlacementMissing'):
        life.validate_bed(text, placement(text, accepted=False))
    with pytest.raises(ValueError, match='BedPlacementMissing'):
        life.validate_bed(text, placement(text, yaw_deg=float('nan')))


def test_check_bed_without_a_report_is_unmeasured(tmp_path):
    with pytest.raises(ValueError, match='BedUnmeasured'):
        life.check_bed(tmp_path)


def test_audit_fbx_refuses_a_file_the_inventory_did_not_accept(tmp_path, report):
    source = tmp_path / 'Idle.fbx'
    source.write_bytes(b'not a capture')
    with pytest.raises(ValueError, match='not an accepted inventory candidate'):
        life.audit_fbx(report, tmp_path / 'LifeFBX', {'Idle': source})


# ---------------------------------------------------------------- engine-free machine (compiled)
def compiler():
    found = shutil.which('clang++') or shutil.which('g++')
    if not found:
        pytest.skip('C++ compiler unavailable')
    return found


def run_cpp(body):
    source = '#include <cstdio>\n#include "Sub01LifeClips.h"\n' + PRELUDE + 'int main(){' + body + '\nreturn 0;}\n'
    with tempfile.TemporaryDirectory() as tmp:
        cpp, exe = Path(tmp) / 'a.cpp', Path(tmp) / 'a'
        cpp.write_text(source)
        built = subprocess.run([compiler(), '-std=c++17', '-Wall', '-Werror', f'-I{life.HEADER_FILE.parent}', str(cpp), '-o', str(exe)],
                               capture_output=True, text=True)
        assert built.returncode == 0, built.stderr[-3000:]
        ran = subprocess.run([str(exe)], capture_output=True, text=True)
        assert ran.returncode == 0, ran.stdout + ran.stderr
        return ran.stdout


PRELUDE = r'''
#define CHECK(c) do{if(!(c)){std::printf("FAILED line %d: %s\n",__LINE__,#c);return 1;}}while(0)
static const uint32_t All=Sub01LifeBit(ESub01LifeRole::Idle)|Sub01LifeBedRoles;
[[maybe_unused]] static FSub01LifeInputs Ready(){FSub01LifeInputs I;I.PostureGate=true;I.IdleBound=true;I.Roles.Loaded=I.Roles.SameSkeleton=I.Roles.Validated=All;
 I.Fresh=true;I.BedMeasured=true;I.BedPlacementValid=true;I.LieDownSeconds=16.966667;I.GetUpSeconds=15.433333;return I;}
'''


def test_idle_when_still_walk_when_moving_never_a_frozen_walk_frame():
    run_cpp(r'''
 FSub01LifeMachine M;FSub01LifeInputs I=Ready();
 for(int K=0;K<3;++K){
  I.NowSeconds+=.1;I.Moving=false;auto O=M.Tick(I);
  CHECK(O.Clip==ESub01LifeClip::Idle&&O.OverrideRate&&O.Loop&&O.MovementAllowed&&O.IdleRefusal==ESub01LifeRefusal::None);
  I.NowSeconds+=.1;I.Moving=true;O=M.Tick(I);
  CHECK(O.Clip==ESub01LifeClip::Walk&&!O.OverrideRate&&O.MovementAllowed&&O.Phase==ESub01LifePhase::Standing);
 }''')


def test_idle_refusals_leave_the_renderer_alone():
    run_cpp(r'''
 FSub01LifeMachine M;FSub01LifeInputs I=Ready();I.IdleBound=false;
 I.Roles.Loaded&=~Sub01LifeBit(ESub01LifeRole::Idle);auto O=M.Tick(I);
 CHECK(O.Clip==ESub01LifeClip::None&&!O.OverrideRate&&O.IdleRefusal==ESub01LifeRefusal::ClipMissing);
 I.Roles.Loaded=All;I.Roles.SameSkeleton&=~Sub01LifeBit(ESub01LifeRole::Idle);O=M.Tick(I);
 CHECK(O.IdleRefusal==ESub01LifeRefusal::SkeletonMismatch&&O.Clip==ESub01LifeClip::None);
 I.Roles.SameSkeleton=All;I.Roles.Validated&=~Sub01LifeBit(ESub01LifeRole::Idle);O=M.Tick(I);
 CHECK(O.IdleRefusal==ESub01LifeRefusal::NotValidated);
 I=Ready();I.PostureGate=false;O=M.Tick(I);
 CHECK(O.IdleRefusal==ESub01LifeRefusal::PostureGate&&O.Clip==ESub01LifeClip::None);''')


@pytest.mark.parametrize('setup,refusal', [
    ('I.Roles.Loaded&=~Sub01LifeBit(ESub01LifeRole::LieDown);', 'ClipMissing'),
    ('I.Roles.Loaded&=~Sub01LifeBit(ESub01LifeRole::GetUp);', 'ClipMissing'),
    ('I.Roles.SameSkeleton&=~Sub01LifeBit(ESub01LifeRole::SleepLoop);', 'SkeletonMismatch'),
    ('I.Roles.Validated&=~Sub01LifeBit(ESub01LifeRole::SleepLoop);', 'NotValidated'),
    ('I.BedMeasured=false;', 'BedUnmeasured'),
    ('I.BedPlacementValid=false;', 'BedPlacementMissing'),
    ('I.Private=true;', 'Private'),
    ('I.Blocked=true;', 'Blocked'),
    ('I.PostureGate=false;', 'PostureGate'),
])
def test_bed_refusals_never_lie_down(setup, refusal):
    run_cpp(r'''
 FSub01LifeMachine M;FSub01LifeInputs I=Ready();I.WantSleep=true;I.AtBedApproach=true;''' + setup + r'''
 for(int K=0;K<50;++K){I.NowSeconds+=.1;auto O=M.Tick(I);
  CHECK(O.Phase==ESub01LifePhase::Refused&&O.Refusal==ESub01LifeRefusal::''' + refusal + r''');
  CHECK(O.MovementAllowed&&O.Clip!=ESub01LifeClip::LieDown&&O.Clip!=ESub01LifeClip::SleepLoop&&O.ClipSerial==0);}
 I.WantSleep=false;auto O=M.Tick(I);CHECK(O.Phase==ESub01LifePhase::Standing&&O.Refusal==ESub01LifeRefusal::None);''')


def test_full_bed_cycle_keeps_movement_off_while_lying():
    run_cpp(r'''
 FSub01LifeMachine M;FSub01LifeInputs I=Ready();I.WantSleep=true;auto O=M.Tick(I);
 CHECK(O.Phase==ESub01LifePhase::Aligning&&O.WalkToBed&&O.MovementAllowed);
 I.AtBedApproach=true;I.YawErrorDeg=20;I.NowSeconds+=.1;O=M.Tick(I);CHECK(O.TurnInPlace&&!O.WalkToBed&&O.Phase==ESub01LifePhase::Aligning);
 I.YawErrorDeg=1;I.Moving=true;I.NowSeconds+=.1;O=M.Tick(I);CHECK(O.Phase==ESub01LifePhase::Aligning);   // still moving: settle first
 I.Moving=false;I.NowSeconds+=.1;O=M.Tick(I);
 CHECK(O.Phase==ESub01LifePhase::LyingDown&&O.Clip==ESub01LifeClip::LieDown&&!O.Loop&&!O.MovementAllowed&&O.ClipSerial==1);
 auto Lying=[&](const FSub01LifeOutputs& X){return !X.MovementAllowed&&!X.WalkToBed&&!X.TurnInPlace;};
 // Playback counts only from what the proxy evaluated under this serial.
 I.ClipPlaying=true;I.ClipSerial=0;I.ClipSeconds=16.9;I.NowSeconds+=.1;O=M.Tick(I);CHECK(O.Phase==ESub01LifePhase::LyingDown&&Lying(O));
 for(double T=0;T<16.9;T+=.5){I.ClipSerial=1;I.ClipSeconds=T;I.NowSeconds+=.5;O=M.Tick(I);CHECK(O.Phase==ESub01LifePhase::LyingDown&&Lying(O)&&O.OverrideRate);}
 I.ClipSeconds=16.966667;I.NowSeconds+=.1;O=M.Tick(I);
 CHECK(O.Phase==ESub01LifePhase::Asleep&&O.Clip==ESub01LifeClip::SleepLoop&&O.Loop&&O.ClipSerial==2&&Lying(O));
 // A stale feed or privacy never wakes or moves a sleeper.
 I.WantSleep=false;I.Fresh=false;for(int K=0;K<20;++K){I.NowSeconds+=1;O=M.Tick(I);CHECK(O.Phase==ESub01LifePhase::Asleep&&Lying(O));}
 I.Fresh=true;I.Private=true;I.NowSeconds+=1;O=M.Tick(I);CHECK(O.Phase==ESub01LifePhase::Asleep&&Lying(O));
 I.Private=false;I.NowSeconds+=1;O=M.Tick(I);
 CHECK(O.Phase==ESub01LifePhase::GettingUp&&O.Clip==ESub01LifeClip::GetUp&&!O.Loop&&O.ClipSerial==3&&Lying(O));
 // A get-up that never starts keeps movement off (fail closed).
 I.ClipSerial=2;for(int K=0;K<30;++K){I.NowSeconds+=.1;O=M.Tick(I);CHECK(O.Phase==ESub01LifePhase::GettingUp&&Lying(O));}
 CHECK(O.Refusal==ESub01LifeRefusal::ClipUnavailable);
 I.ClipSerial=3;I.ClipSeconds=1;I.NowSeconds+=.1;O=M.Tick(I);CHECK(O.Phase==ESub01LifePhase::GettingUp&&Lying(O));
 I.ClipSeconds=15.433333;I.NowSeconds+=.1;O=M.Tick(I);
 CHECK(O.Phase==ESub01LifePhase::Standing&&O.MovementAllowed&&O.Clip==ESub01LifeClip::Idle&&O.Refusal==ESub01LifeRefusal::None);''')


def test_lie_down_that_never_starts_refuses_and_restores_standing():
    run_cpp(r'''
 FSub01LifeMachine M;FSub01LifeInputs I=Ready();I.WantSleep=true;I.AtBedApproach=true;auto O=M.Tick(I);
 CHECK(O.Phase==ESub01LifePhase::LyingDown&&!O.MovementAllowed);
 for(int K=0;K<11;++K){I.NowSeconds+=.1;O=M.Tick(I);}
 CHECK(O.Phase==ESub01LifePhase::Refused&&O.Refusal==ESub01LifeRefusal::ClipUnavailable&&O.MovementAllowed);''')


def test_wake_command_while_lying_down_finishes_then_gets_up():
    run_cpp(r'''
 FSub01LifeMachine M;FSub01LifeInputs I=Ready();I.WantSleep=true;I.AtBedApproach=true;auto O=M.Tick(I);
 I.ClipPlaying=true;I.ClipSerial=1;I.ClipSeconds=2;I.NowSeconds+=.1;O=M.Tick(I);
 I.WantSleep=false;I.NowSeconds+=.1;O=M.Tick(I);CHECK(O.Phase==ESub01LifePhase::LyingDown&&!O.MovementAllowed);
 I.ClipSeconds=16.966667;I.NowSeconds+=.1;O=M.Tick(I);CHECK(O.Phase==ESub01LifePhase::GettingUp&&!O.MovementAllowed);''')


def test_approach_timeout_refuses():
    run_cpp(r'''
 FSub01LifeMachine M;FSub01LifeInputs I=Ready();I.WantSleep=true;auto O=M.Tick(I);
 for(int K=0;K<31;++K){I.NowSeconds+=1;O=M.Tick(I);}
 CHECK(O.Phase==ESub01LifePhase::Refused&&O.Refusal==ESub01LifeRefusal::ApproachTimeout&&O.MovementAllowed&&!O.WalkToBed);''')


def test_life_ids_match_the_native_hash():
    texts = [bed_text(), life.clip_object_path('Idle'), '']
    out = run_cpp(''.join(f'std::printf("%llu\\n",(unsigned long long)Sub01LifeId({json.dumps(t)}));' for t in texts))
    assert [int(v) for v in out.split()] == [life.life_id(t) for t in texts]


# ---------------------------------------------------------------- staged install
NAMES = ('Sub01HomeLab.h', 'Sub01HomeLab.cpp', 'Sub01HomeHands.h', 'Sub01HomeHands.cpp')


def staged(order=('life',)):
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
        else:
            life.install_module(module)
    return tmp, module, before, {n: (module / n).read_text() for n in NAMES}


@pytest.fixture(scope='module')
def installed():
    tmp, module, before, after = staged()
    yield module, before, after
    tmp.cleanup()


def assert_additive(before, after):
    for name, text in before.items():
        position = 0
        for line in (l for l in text.splitlines() if l.strip()):
            position = after[name].index(line, position) + len(line)


def test_install_is_additive_and_hooks_the_right_places(installed):
    module, before, after = installed
    assert (module / 'Sub01LifeClips.h').read_text() == life.HEADER_FILE.read_text()
    assert_additive(before, after)
    h, cpp, hands_h, hands_cpp = (after[n] for n in NAMES)
    assert h.index('#include "Sub01LifeClips.h"') < h.index('#include "Sub01HomeLab.generated.h"')
    assert 'FSub01LifeMachine LifeMachine;' in h and 'UPROPERTY(Transient) int32 LifeStartSerial=0;' in hands_h
    begin = cpp.split('void ASub01HomeCharacter::BeginPlay() {', 1)[1].split('\n}', 1)[0]
    assert begin.index('LoadHandsAssets();') < begin.index('LoadLifeClips();')
    tick = cpp.split('void ASub01HomeCharacter::Tick(float DeltaSeconds) {', 1)[1].split('\n}\n', 1)[0]
    assert tick.rstrip().endswith(life.RATE_ANCHOR.strip() + '\n UpdateLifeClips(Instance,DeltaSeconds);')
    live = cpp.split('void ASub01HomeCharacter::UpdateLiveHome(float Dt){', 1)[1].split('\n}\n', 1)[0]
    assert live.index('if(LifeMovementLocked()){') < live.index('if(!LiveHomePath.Num()){if(PCBridge)') < live.index('AddMovementInput(')
    pre = hands_cpp.split('virtual void PreUpdate(', 1)[1].split('virtual void CacheBones()', 1)[0]
    switch = pre.split('if(Current.GetSequence()!=Hands->TargetSequence) {', 1)[1].split('\n  }\n', 1)
    assert 'LifeStartSerial' not in switch[0] and 'if(LifeSerial!=Hands->LifeStartSerial' in switch[1]
    evaluate = hands_cpp.split('virtual bool Evaluate(FPoseContext& Output) override {', 1)[1].split('\n }\n', 1)[0]
    assert evaluate.index('Blend.Evaluate_AnyThread(Output);') < evaluate.index('LifeEvaluatedSerial=LifeSerial;')


def added_code():
    return '\n'.join([life.CHARACTER_FIELDS, life.CHARACTER_METHODS, life.HANDS_FIELDS, life.PROXY_FIELDS,
                      life.PROXY_APPLY, life.PROXY_EVALUATED, life.LIVE_GATE])


def test_added_code_never_places_the_actor_poses_bones_or_rides_the_camera():
    code = added_code()
    for forbidden in ('SetActorLocation', 'Teleport', 'SetWorldLocation', 'SetActorTransform', 'SetActorRotation',
                      'AttachToComponent(ViewCamera', 'FirstPersonBody->AttachToComponent', 'MoveUpdatedComponent',
                      'SetRelativeLocation(HandsBaseOffset', 'TwoBoneIK', 'FABRIK', 'IKRig', 'Output.Pose[',
                      'SetBoneLocation', 'SetBoneRotation', 'SetBoneTransform', 'HandsClips.Add', 'SetHandsPosture(',
                      'FMath::Sin', 'ValidatedHandsPostures.Add'):
        assert forbidden not in code, forbidden
    assert not re.search(r'\bIK\b', code)
    methods = life.CHARACTER_METHODS
    # Movement: input toward the measured approach only, off (not just stopped) while in bed.
    assert methods.count('AddMovementInput(') == 1 and 'if(LifeOut.WalkToBed&&Controller)' in methods
    assert 'GetCharacterMovement()->DisableMovement();' in methods
    assert methods.index('DisableMovement();') < methods.index('SetMovementMode(MOVE_Walking)')
    assert 'else if(LifeOut.MovementAllowed&&LifeMovementDisabled){GetCharacterMovement()->SetMovementMode(MOVE_Walking);' in methods
    # The renderer's gate and bindings are respected: Idle comes only from its own HandsClips binding.
    assert 'In.PostureGate=HandsFailure.IsEmpty()&&HandsPosture==TEXT("Walk");' in methods
    assert 'In.IdleBound=HandsClips.Contains(FName(TEXT("Idle")));' in methods
    assert 'if(Clip&&(LifeRoles.SameSkeleton&Bit)&&(LifeRoles.Validated&Bit))LifeClips.Add(FName(Role.Key),Clip);' in methods
    assert 'ValidatedHandsPostures.Contains(FName(Role.Key))' in methods
    # Idle only gets its rate when the renderer itself chose it (a seat clip is never overridden).
    assert 'if(Idle&&Instance->TargetSequence==Idle)Instance->TargetRate=1.f;' in methods
    # Playback is what the proxy evaluated under the serial, never the requested target.
    assert 'In.ClipPlaying=Requested&&Instance->LifeEvaluatedSequence==Requested&&Instance->LifeEvaluatedTime>=0;' in methods
    assert 'TargetSequence==Requested' not in methods
    # The camera follows the captured head in bed only while the body is on the capsule.
    assert 'FirstPersonBody->GetAttachParent()==GetRootComponent()' in methods


def test_install_refuses_missing_anchors_and_reinstall(installed):
    _, before, after = installed
    sources = {'header': before['Sub01HomeLab.h'], 'cpp': before['Sub01HomeLab.cpp'],
               'hands_header': before['Sub01HomeHands.h'], 'hands_cpp': before['Sub01HomeHands.cpp']}
    for key, anchor, _ in life.EDITS:
        broken = dict(sources)
        broken[key] = broken[key].replace(anchor, '')
        with pytest.raises(ValueError, match='anchor not unique'):
            life.install(broken)
    again = {'header': after['Sub01HomeLab.h'], 'cpp': after['Sub01HomeLab.cpp'],
             'hands_header': after['Sub01HomeHands.h'], 'hands_cpp': after['Sub01HomeHands.cpp']}
    with pytest.raises(ValueError, match='already installed'):
        life.install(again)


@pytest.mark.parametrize('order', [('seat', 'life'), ('life', 'seat')])
def test_coexists_with_the_seat_adapter_in_either_order(order):
    tmp, module, before, after = staged(order)
    try:
        assert_additive(before, after)
        cpp = after['Sub01HomeLab.cpp']
        assert cpp.count('UpdateLifeClips(Instance,DeltaSeconds);') == 1 and cpp.count('ApplySeatAnimation(Instance);') == 1
        assert (module / 'Sub01LifeClips.h').exists() and (module / 'Sub01SeatTransition.h').exists()
    finally:
        tmp.cleanup()
