"""tools/install_default_game_ini.py: strict, append-only, idempotent DefaultGame.ini installer with backup/restore."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import install_default_game_ini as ini  # noqa: E402
import unreal_life_clips_runtime as life  # noqa: E402
import unreal_seat_transition_runtime as seat  # noqa: E402
from test_seated_fit_import import _receipt  # noqa: E402  (a seated-fit receipt from the fake-unreal importer)

ORIGINAL = ('[/Script/EngineSettings.GeneralProjectSettings]\nProjectID=ABC\n\n'
            '[/Script/Sub01HomeLab.Sub01HomeCharacter]\nWalkClipPath=/Game/Sub01Hands/FBX/SUB01_Walk.SUB01_Walk\n'
            '+ValidatedHandsPostures=Walk\n\n[/Script/Other.Thing]\nX=1\n')
SEAT_LINES = ['+ValidatedHandsPostures=StandToSit', '+ValidatedHandsPostures=Sitting',
              '+ValidatedHandsPostures=SitToType', '+ValidatedHandsPostures=SitToStand']
IDLE_LINES = ['IdleClipPath=/Game/Sub01Hands/Life/SUB01_Idle.SUB01_Idle', '+ValidatedHandsPostures=Idle']


def seating_receipt(**override):
    clips = [{'role': a, 'object_path': f'/Game/Sub01Hands/Seating/SUB01_{a}.SUB01_{a}', 'duration_s': 1.0,
              'same_existing_skeleton': True, 'physical_contact_verified': False} for a in ('SitDown', 'GetUp', 'Sitting', 'SitToType')]
    doc = {'owner': '/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner', 'skeleton': seat.OWNER_SKELETON,
           'original_bone_identities_preserved': True, 'clips': clips, 'runtime_ready': False}
    doc.update(override)
    return doc


def project(tmp_path, text=ORIGINAL, seating=True, idle=True):
    (tmp_path / 'Config').mkdir(parents=True, exist_ok=True)
    (tmp_path / ini.INI).write_text(text)
    if seating:
        (tmp_path / ini.SEATING_RECEIPT).write_text(json.dumps(seating_receipt()))
    if idle:
        (tmp_path / 'private-audit').mkdir(exist_ok=True)
        (tmp_path / ini.LIFE_INVENTORY).write_text(json.dumps({'candidates': [
            {'role': 'Idle', 'file': 'x.glb', 'sha256': 'a' * 64, 'verdict': 'Candidate', 'skeleton': {'same_owner_skeleton': True},
             'loop': {'loops': True}, 'duration_s': 4.0}]}))
        (tmp_path / ini.LIFE_RECEIPT).write_text(json.dumps({'clips': [
            {'role': 'Idle', 'object_path': life.clip_object_path('Idle'), 'inventory_sha256': 'a' * 64,
             'same_existing_skeleton': True, 'duration_s': 4.0}]}))
    return tmp_path


def section(text):
    return text.split(ini.SECTION, 1)[1].split('\n[', 1)[0].strip().splitlines()


def receipts(p):
    return sorted(f for f in (p / 'private-audit').glob(ini.RECEIPT_GLOB) if not f.name.endswith('.restored.json'))


def test_installs_seat_and_idle_lines_append_only_with_backup_and_receipt(tmp_path, capsys):
    p = project(tmp_path)
    assert ini.main([str(p), '--dry-run']) == 0
    assert 'dry run: nothing written' in capsys.readouterr().out and (p / ini.INI).read_text() == ORIGINAL and not receipts(p)
    assert ini.main([str(p)]) == 0
    after = (p / ini.INI).read_text()
    assert section(after) == ['WalkClipPath=/Game/Sub01Hands/FBX/SUB01_Walk.SUB01_Walk', '+ValidatedHandsPostures=Walk',
                              *SEAT_LINES, *IDLE_LINES]
    assert after.replace('\n'.join(SEAT_LINES + IDLE_LINES) + '\n', '') == ORIGINAL       # only insertions
    [receipt_path] = receipts(p)
    receipt = json.loads(receipt_path.read_text())
    assert receipt['readiness_claimed'] is False and receipt['lines_added'] == SEAT_LINES + IDLE_LINES
    assert receipt['before_sha256'] == hashlib.sha256(ORIGINAL.encode()).hexdigest()
    assert receipt['after_sha256'] == hashlib.sha256(after.encode()).hexdigest()
    assert Path(receipt['backup']).read_text() == ORIGINAL


def test_second_run_is_a_no_op(tmp_path, capsys):
    p = project(tmp_path)
    assert ini.main([str(p)]) == 0
    first = (p / ini.INI).read_bytes()
    capsys.readouterr()
    assert ini.main([str(p)]) == 0
    assert 'no-op' in capsys.readouterr().out and (p / ini.INI).read_bytes() == first and len(receipts(p)) == 1
    assert len(list((p / 'Config').glob('DefaultGame.ini.bak-*'))) == 1


def test_creates_the_section_when_absent(tmp_path):
    p = project(tmp_path, text='[/Script/Other.Thing]\nX=1\n')
    assert ini.main([str(p), '--only', 'seat']) == 0
    assert (p / ini.INI).read_text() == '[/Script/Other.Thing]\nX=1\n\n' + ini.SECTION + '\n' + '\n'.join(SEAT_LINES) + '\n'


@pytest.mark.parametrize('existing, why', [
    ('IdleClipPath=/Game/Other/Idle.Idle', 'IdleClipPath'),
    ('-ValidatedHandsPostures=Sitting', 'ValidatedHandsPostures'),
    ('!ValidatedHandsPostures=ClearArray', 'ValidatedHandsPostures'),
    ('ValidatedHandsPostures=Idle', 'ValidatedHandsPostures'),
])
def test_conflicting_value_refuses_and_writes_nothing(tmp_path, capsys, existing, why):
    text = ORIGINAL.replace('+ValidatedHandsPostures=Walk\n', f'+ValidatedHandsPostures=Walk\n{existing}\n')
    p = project(tmp_path, text=text)
    assert ini.main([str(p)]) == 2
    assert 'conflicting existing entry for ' + why in capsys.readouterr().err
    assert (p / ini.INI).read_text() == text and not receipts(p) and not list((p / 'Config').glob('*.bak-*'))


def test_duplicate_section_refuses(tmp_path, capsys):
    p = project(tmp_path, text=ORIGINAL + ini.SECTION + '\nY=2\n')
    assert ini.main([str(p)]) == 2 and 'ambiguous' in capsys.readouterr().err


@pytest.mark.parametrize('only, setup, why', [
    ('seat', dict(seating=False), 'seating import receipt missing'),
    ('idle', dict(idle=False), 'life inventory missing'),
    ('seated-fit', {}, 'seated-fit import receipt missing'),
])
def test_missing_receipt_refuses_even_in_dry_run(tmp_path, capsys, only, setup, why):
    p = project(tmp_path, **setup)
    assert ini.main([str(p), '--only', only, '--dry-run']) == 2
    assert why in capsys.readouterr().err and (p / ini.INI).read_text() == ORIGINAL


@pytest.mark.parametrize('override, why', [
    (dict(skeleton='/Game/Other/SK.SK'), 'skeleton'),
    (dict(clips=seating_receipt()['clips'][:3]), 'exactly the roles'),
    (dict(clips=[dict(c, same_existing_skeleton=False) for c in seating_receipt()['clips']]), 'existing owner skeleton'),
])
def test_seating_receipt_must_pass(tmp_path, capsys, override, why):
    p = project(tmp_path)
    (p / ini.SEATING_RECEIPT).write_text(json.dumps(seating_receipt(**override)))
    assert ini.main([str(p), '--only', 'seat']) == 2 and why in capsys.readouterr().err


def test_idle_receipt_must_bind(tmp_path, capsys):
    p = project(tmp_path)
    (p / ini.LIFE_RECEIPT).write_text(json.dumps({'clips': []}))
    assert ini.main([str(p), '--only', 'idle']) == 2 and 'Idle not bindable: NotImported' in capsys.readouterr().err


def test_seated_fit_lines_only_for_accepted_passing_fits(tmp_path):
    p = project(tmp_path / 'p')
    _receipt(p)                                                     # writes private-audit/unreal-seated-fit-import.json
    assert ini.main([str(p), '--only', 'seated-fit']) == 0
    lines = section((p / ini.INI).read_text())
    added = [l for l in lines if l.startswith('+ValidatedHandsPostures=') and l != '+ValidatedHandsPostures=Walk']
    assert added == ['+ValidatedHandsPostures=SeatedIdle', '+ValidatedHandsPostures=SitToTypeSeated',
                     '+ValidatedHandsPostures=DeskTypingSeated']
    assert not any('SitDownSeated' in l or 'GetUpSeated' in l for l in lines)


def test_forged_seated_fit_row_for_a_failed_fit_is_never_written(tmp_path):
    p = project(tmp_path / 'p')
    receipt = _receipt(p)
    for row in receipt['clips']:
        if row['role'] in ('SitDownSeated', 'GetUpSeated'):
            row.update(imported=True, accepted=True, fit_pass=True, same_existing_skeleton=True)
    (p / seat.SEATED_FIT_RECEIPT).write_text(json.dumps(receipt))
    assert ini.main([str(p), '--only', 'seated-fit']) == 0
    text = (p / ini.INI).read_text()
    assert 'SitDownSeated' not in text and 'GetUpSeated' not in text   # the committed reports still fail


def test_restore_puts_the_backup_back(tmp_path):
    p = project(tmp_path)
    assert ini.main([str(p)]) == 0
    assert ini.main([str(p), '--restore']) == 0
    assert (p / ini.INI).read_text() == ORIGINAL
    assert json.loads(receipts(p)[0].with_name(receipts(p)[0].stem + '.restored.json').read_text())['readiness_claimed'] is False


def test_restore_refuses_when_the_file_drifted(tmp_path, capsys):
    p = project(tmp_path)
    assert ini.main([str(p)]) == 0
    drifted = (p / ini.INI).read_text() + '; edited by hand\n'
    (p / ini.INI).write_text(drifted)
    capsys.readouterr()
    assert ini.main([str(p), '--restore', str(receipts(p)[0])]) == 2
    assert 'modified since the install' in capsys.readouterr().err and (p / ini.INI).read_text() == drifted


def test_restore_without_receipt_refuses(tmp_path, capsys):
    p = project(tmp_path)
    assert ini.main([str(p), '--restore']) == 2 and 'no install receipt' in capsys.readouterr().err
