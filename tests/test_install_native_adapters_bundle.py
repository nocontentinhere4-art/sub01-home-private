"""One-command install of the seat, life (+bed) and controller adapters onto freshly staged sources."""
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import install_native_adapters_bundle as bundle  # noqa: E402
from stage_unreal_home_runtime import stage  # noqa: E402

NAMES = tuple(bundle.SOURCE_FILES.values())
RATE = ' Instance->TargetRate=HandsPosture==TEXT("Walk")?(Moving?float(Sub01FirstPersonMotion::AuthoredWalkRate(Speed)):(PlayingIdle?1.f:0.f)):1.f;'


@pytest.fixture(scope='module')
def template(tmp_path_factory):
    project = tmp_path_factory.mktemp('staged')
    (project / 'Config').mkdir()
    (project / 'Sub01HomeLab.uproject').write_text('{}')
    stage(project)
    return project


@pytest.fixture
def module(template, tmp_path):
    project = tmp_path / 'project'
    shutil.copytree(template, project)
    return project / 'Source/Sub01HomeLab'


def snapshot(module):
    return {p.name: p.read_bytes() for p in module.iterdir() if p.is_file()}


def test_fresh_stage_carries_roots_walk_rate_line(module):
    # Root main (fb7253a) stages exactly this line; the fixture below simulates other forms of it.
    assert (module / 'Sub01HomeLab.cpp').read_text().split('\n').count(RATE) == 1


def test_dry_run_writes_nothing_and_summarises(module, capsys):
    before = snapshot(module)
    assert bundle.main([str(module), '--dry-run']) == 0
    out = capsys.readouterr().out
    assert snapshot(module) == before and not (module.parents[1] / 'private-audit').exists()
    assert 'seat -> life -> bed -> controller' in out and '0 removed' in out and 'dry run: nothing written' in out
    assert 'copy Sub01SeatTransition.h' in out and 'copy Sub01LifeClips.h' in out
    assert 'readiness: unchanged' in out


def test_install_is_additive_keeps_gates_and_writes_a_receipt(module):
    before = snapshot(module)
    assert bundle.main([str(module)]) == 0
    after = snapshot(module)
    # Only the four generated sources change; exactly the two adapter headers are added.
    assert set(after) - set(before) == {'Sub01SeatTransition.h', 'Sub01LifeClips.h'}
    for name in set(before) - set(NAMES):
        assert after[name] == before[name], name
    assert after['Sub01SeatTransition.h'] == bundle.seat.HEADER_FILE.read_bytes()
    assert after['Sub01LifeClips.h'] == bundle.life.HEADER_FILE.read_bytes()
    old = {k: before[n].decode() for k, n in bundle.SOURCE_FILES.items()}
    new = {k: after[n].decode() for k, n in bundle.SOURCE_FILES.items()}
    bundle.check_additive(old, new)
    snap = bundle.gate_snapshot(old)
    assert bundle.check_gates(new, snap) == {n: e['sha256'] for n, e in snap['lines'].items()}
    assert new['cpp'].split('\n').count(RATE) == 1
    receipt = json.loads((module.parents[1] / 'private-audit/native-adapters-install-receipt.json').read_text())
    assert receipt['schema'] == bundle.RECEIPT_SCHEMA and receipt['order'] == ['seat', 'life', 'bed', 'controller']
    assert receipt['readiness_claimed'] is False and receipt['compiled'] is False and receipt['additive_only'] is True
    assert receipt['adapters']['seat']['python_sha256'] == bundle.sha(Path(bundle.seat.__file__).read_bytes())
    assert receipt['adapters']['life']['header_sha256'] == bundle.sha(bundle.life.HEADER_FILE.read_bytes())
    assert set(receipt['gate_lines_sha256']) == {n for n, _, _ in bundle.GATE_LINES}
    assert receipt['gate_lines_sha256']['walk_rate'] == bundle.sha(RATE)
    assert len(receipt['gate_bodies_sha256']) == len(bundle.GATE_BODIES)
    assert receipt['sources_after_sha256']['Sub01HomeLab.cpp'] == bundle.sha(after['Sub01HomeLab.cpp'])
    for step in receipt['steps']:
        assert all(a['count'] == 1 for a in step['anchors']), step
    assert 'commit' in receipt['source']
    # Nothing was written that could flip readiness.
    audit = sorted(p.name for p in (module.parents[1] / 'private-audit').iterdir())
    assert audit == ['native-adapters-install-receipt.json']


def test_runtime_hook_order_after_the_renderer_rate_choice(module):
    bundle.main([str(module)])
    cpp = (module / 'Sub01HomeLab.cpp').read_text()
    tick = cpp.split('void ASub01HomeCharacter::Tick(float DeltaSeconds) {', 1)[1].split('\n}\n', 1)[0]
    assert tick.split('\n')[-4:] == [RATE, ' UpdateControllerPlay(Instance,DeltaSeconds);',
                                     ' UpdateLifeClips(Instance,DeltaSeconds);', ' ApplySeatAnimation(Instance);']
    live = cpp.split('void ASub01HomeCharacter::UpdateLiveHome(float Dt){', 1)[1].split('\n}\n', 1)[0]
    stale = live.index('if(!LiveHomeFresh||Now<LiveHomeLastReceived')
    focus = live.index('if(!LiveHomePath.Num()){if(PCBridge)PCBridge->SetOperatorFocus(')
    for gate in ('if(!SeatOut.MovementInput&&LiveHomePath.Num())', 'LifeMovementLocked', 'if(ControllerPlayActive&&LiveHomePath.Num())'):
        assert stale < live.index(gate) < focus, gate
    # The privacy revoke still runs first and still drops seat verification.
    assert live.index('if(LiveHomePrivate){NativeSeatVerified=false;') < stale


def test_reinstall_and_partial_install_are_refused(module, capsys):
    assert bundle.main([str(module), '--only', 'seat']) == 0
    before = snapshot(module)
    capsys.readouterr()
    assert bundle.main([str(module)]) == 2
    assert 'already' in capsys.readouterr().err
    assert snapshot(module) == before
    # Even without its header, installed source text is detected.
    (module / 'Sub01SeatTransition.h').unlink()
    assert bundle.main([str(module), '--only', 'seat']) == 2
    assert 'seat is already (partly) installed' in capsys.readouterr().err
    (module / 'Sub01SeatTransition.h').write_bytes(before['Sub01SeatTransition.h'])
    # The others can still be added on top, in the fixed order, keeping seat untouched.
    assert bundle.main([str(module), '--only', 'controller,life,bed']) == 0
    cpp = (module / 'Sub01HomeLab.cpp').read_text()
    assert cpp.count('ApplySeatAnimation(Instance);\n') == 1 and cpp.count('UpdateLifeClips(Instance,DeltaSeconds);\n') == 1


@pytest.mark.parametrize('only', ['seat', 'life', 'controller', 'life,bed', 'seat,controller', 'life,controller'])
def test_each_subset_installs(module, only):
    assert bundle.main([str(module), '--only', only]) == 0


def test_bed_without_life_is_refused(module, capsys):
    before = snapshot(module)
    assert bundle.main([str(module), '--only', 'bed']) == 2
    assert 'bed needs life' in capsys.readouterr().err
    assert snapshot(module) == before


def test_unknown_adapter_is_refused(module):
    assert bundle.main([str(module), '--only', 'seat,sofa']) == 2


@pytest.mark.parametrize('line', [
    # Simulated forms of root's walk-rate line (the anchor resolves by its unique prefix).
    ' Instance->TargetRate=HandsPosture==TEXT("Walk")?(Moving?float(Sub01FirstPersonMotion::AuthoredWalkRate(Speed)):0.f):1.f;',
    ' Instance->TargetRate=HandsPosture==TEXT("Walk")?(Moving?FMath::Clamp(Speed/140.f,.45f,1.15f):(PlayingIdle?1.f:0.f)):1.f;',
])
def test_a_changed_walk_rate_line_is_hooked_and_kept_byte_identical(module, line):
    path = module / 'Sub01HomeLab.cpp'
    path.write_text(path.read_text().replace(RATE, line, 1))
    assert bundle.main([str(module)]) == 0
    cpp = path.read_text()
    assert cpp.split('\n').count(line) == 1 and RATE not in cpp
    assert cpp.split(line + '\n', 1)[1].startswith(' UpdateControllerPlay(Instance,DeltaSeconds);\n')
    receipt = json.loads((module.parents[1] / 'private-audit/native-adapters-install-receipt.json').read_text())
    assert receipt['gate_lines_sha256']['walk_rate'] == bundle.sha(line)


def test_a_duplicated_walk_rate_line_is_refused(module, capsys):
    path = module / 'Sub01HomeLab.cpp'
    path.write_text(path.read_text().replace(RATE, RATE + '\n' + RATE, 1))
    before = snapshot(module)
    assert bundle.main([str(module)]) == 2
    assert snapshot(module) == before


def test_a_missing_anchor_is_refused_before_anything_is_written(module, capsys):
    path = module / 'Sub01HomeLab.cpp'
    path.write_text(path.read_text().replace(' BeginLiveHome();\n', ' BeginLiveHomeRenamed();\n', 1))
    before = snapshot(module)
    assert bundle.main([str(module)]) == 2
    assert 'seat' in capsys.readouterr().err
    assert snapshot(module) == before


def test_an_existing_adapter_header_is_refused(module):
    (module / 'Sub01LifeClips.h').write_text('// stale')
    assert bundle.main([str(module), '--only', 'life']) == 2


def test_a_missing_staged_source_is_refused(module):
    (module / 'Sub01HomeHands.cpp').unlink()
    assert bundle.main([str(module), '--dry-run']) == 2


def test_an_adapter_that_edits_a_gate_is_refused(module, monkeypatch):
    original = bundle.controller.install

    def tampering(sources):
        out = original(sources)
        out['cpp'] = out['cpp'].replace('Sub01FirstPersonMotion::SmoothAngle(CurrentLook.Yaw,Delta.Rotation().Yaw,Dt,180)',
                                        'Sub01FirstPersonMotion::SmoothAngle(CurrentLook.Yaw,Delta.Rotation().Yaw,Dt,360)')
        return out
    monkeypatch.setattr(bundle.controller, 'install', tampering)
    with pytest.raises(bundle.Refused, match='edited, moved or removed'):
        bundle.plan(module)


def test_an_adapter_that_inserts_into_a_gate_body_is_refused(module, monkeypatch):
    original = bundle.controller.install

    def inserting(sources):
        out = original(sources)
        anchor = 'void ASub01HomeCharacter::UpdateNativePCPrivacy(){\n'
        out['cpp'] = out['cpp'].replace(anchor, anchor + ' return;\n', 1)
        return out
    monkeypatch.setattr(bundle.controller, 'install', inserting)
    with pytest.raises(bundle.Refused, match='UpdateNativePCPrivacy'):
        bundle.plan(module)
