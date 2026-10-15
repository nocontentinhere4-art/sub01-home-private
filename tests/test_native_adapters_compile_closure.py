"""Compiler closure of the native adapters bundle (seat -> life -> bed -> controller + grip analyzer) on fresh stages."""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import check_native_adapters_compile_closure as closure  # noqa: E402
import install_native_adapters_bundle as bundle  # noqa: E402
import unreal_bed_root_motion as bed  # noqa: E402
import unreal_controller_grip_contact_native as grip  # noqa: E402
import unreal_controller_play_runtime as controller  # noqa: E402
import unreal_life_clips_runtime as life  # noqa: E402
import unreal_seat_transition_runtime as seat  # noqa: E402

needs_compiler = pytest.mark.skipif(not closure.compilers(), reason='no C++ compiler')
ADAPTER_FUNCTIONS = (
    'Sub01SeatEyeAlpha', 'ASub01HomeCharacter::LoadSeatTransition', 'ASub01HomeCharacter::SeatLiveBody',
    'ASub01HomeCharacter::SeatSoleSupport', 'ASub01HomeCharacter::UpdateSeatTransition', 'ASub01HomeCharacter::UpdateSeatCamera',
    'ASub01HomeCharacter::ApplySeatAnimation', 'ASub01HomeCharacter::LoadLifeClips', 'ASub01HomeCharacter::LifeMovementLocked',
    'ASub01HomeCharacter::UpdateLifeClips', 'ASub01HomeCharacter::LoadLifeRootPath', 'ASub01HomeCharacter::SampleLifeRootPath',
    'ASub01HomeCharacter::UpdateLifeRootMotion', 'Sub01ControllerPlayEyeAlpha', 'Sub01ControllerPlayId',
    'ASub01HomeCharacter::ControllerPlayReady', 'ASub01HomeCharacter::LoadControllerPlay', 'ASub01HomeCharacter::UpdateControllerPlay',
    'ASub01HomeCharacter::UpdateControllerPlayCamera', 'Sub01SolidAngle', 'USub01HomeHandsInstance::AnalyzeCapturedControllerGrip')


@pytest.fixture(scope='module')
def report(tmp_path_factory):
    return closure.check(tmp_path_factory.mktemp('closure'))


def failing(result):
    return {(r['compiler'], r['unit'], ' '.join(r['defines'])): r['diagnostics'] for r in result['compiles'] if not r['ok']}


# ------------------------------------------------------------------------------------------- the real bundle
@needs_compiler
def test_the_installed_bundle_closes_statically_and_compiles(report):
    assert report['static']['problems'] == []
    assert failing(report) == {}
    assert report['ok'] and report['installed'] == ['seat', 'life', 'bed', 'controller', 'grip']
    assert {r['unit'] for r in report['compiles']} == {'engine_free_headers', 'character', 'hands'}
    assert all(a['count'] == 1 for a in report['anchors'])


@needs_compiler
def test_every_added_function_and_insertion_is_compiled(report):
    compiled = [c['part'] for c in report['coverage'] if c['unit']]
    for name in ADAPTER_FUNCTIONS:
        assert any(part.endswith(' ' + name) for part in compiled), name
    # Every block inserted into a root function is compiled as a probe or inside the whole proxy struct.
    assert [c for c in report['coverage'] if not c['unit']] == []
    probes = [p for p in compiled if '(probe;' in p]
    assert {p.split(' inserted into ')[1].split(' ')[0] for p in probes} == {
        'ASub01HomeCharacter::BeginPlay', 'ASub01HomeCharacter::Tick', 'ASub01HomeCharacter::UpdateLiveHome'}
    assert any('Tick (probe; host params/locals: float DeltaSeconds,USub01HomeHandsInstance* Instance)' in p for p in probes)
    assert sum('inside FSub01HandsProxy' in p for p in compiled) == 4
    assert any(p.startswith('Sub01SeatTransition.h') for p in compiled) and any(p.startswith('Sub01LifeClips.h') for p in compiled)


def test_includes_resolve_to_staged_files_or_the_derived_ue_allowlist(report):
    assert {i['include'] for i in report['static']['includes']} >= {'Sub01SeatTransition.h', 'Sub01LifeClips.h', 'Misc/FileHelper.h',
                                                                     'Engine/StaticMesh.h', 'cmath'}
    assert all(i['resolved'] for i in report['static']['includes'])
    # The allowlist is what the freshly staged module already includes, nothing hand-written.
    assert 'Misc/FileHelper.h' in report['static']['ue_allowlist'] and 'Sub01HomeLab.h' not in report['static']['ue_allowlist']


@pytest.mark.skipif(subprocess.run(['git', '-C', str(closure.REPO), 'rev-parse', '--verify', '-q', 'origin/main'],
                                   capture_output=True).returncode != 0, reason='origin/main not fetched')
@needs_compiler
def test_roots_main_staging_inputs_also_close(tmp_path):
    result = closure.check(tmp_path, 'origin/main')
    assert result['staging']['staging_commit'] and 'identical_to_checkout_staging' in result['staging']
    assert result['static']['problems'] == [] and failing(result) == {}


# ------------------------------------------------------------------------------------------- fixed regressions
@pytest.mark.parametrize('module,name', [(seat, 'CHARACTER_METHODS'), (life, 'CHARACTER_METHODS'), (bed, 'METHODS'),
                                         (controller, 'CHARACTER_METHODS'), (grip, 'CPP')])
def test_adapter_method_blocks_are_brace_balanced(module, name):
    # LoadSeatTransition carried an extra '}' since abb00cd: it closed the function before the evidence block.
    assert closure.brace_walk(closure.strip(getattr(module, name))) == (0, 0)
    items = closure.top_level_items(getattr(module, name))
    assert all(it['kind'] in ('definition', 'declaration', 'preprocessor') for it in items), [it['head'] for it in items]


def test_seated_typing_locals_do_not_shadow_character_fields():
    load = seat.CHARACTER_METHODS.split('void ASub01HomeCharacter::LoadSeatTransition(){', 1)[1].split('\n}\n', 1)[0]
    # TypingClipPath is the renderer's UPROPERTY; a local of that name is a shadowing error in UE.
    assert not re.search(r'\bFString\b[^;]*\bTypingClipPath\b', load)
    assert 'TypingProfileClip!=SeatedTyping->GetPathName()' in load


# ------------------------------------------------------------------------------------------- the check detects
def inject(monkeypatch, cpp_tail='', header_line='', live_line='', hands_tail=''):
    original = bundle.controller.install

    def install(sources):
        out = original(sources)
        out['cpp'] += cpp_tail
        if header_line:
            out['header'] = out['header'].replace('\n void Forward(float Value);', '\n' + header_line + '\n void Forward(float Value);', 1)
        if live_line:
            out['cpp'] = out['cpp'].replace(' UpdateSeatTransition(Dt);\n', ' UpdateSeatTransition(Dt);\n' + live_line + '\n', 1)
        out['hands_cpp'] += hands_tail
        return out
    monkeypatch.setattr(bundle.controller, 'install', install)


def test_static_faults_are_reported(monkeypatch, tmp_path):
    inject(monkeypatch,
           cpp_tail='#include "Engine/NotStaged.h"\nvoid ASub01HomeCharacter::LoadControllerPlayTwice(){ if(true){ }}}\n'
                    'static int Sub01Orphan(){ return Sub01NeverDefined(); }\n',
           header_line=' void DeclaredOnly(); void LoadControllerPlayTwice();',
           hands_tail='\nstatic double Sub01SeatEyeAlpha(double Dt){return Dt;}\n')
    problems = '\n'.join(closure.check(tmp_path)['static']['problems'])
    assert 'Engine/NotStaged.h resolves to nothing staged' in problems
    assert 'not brace-balanced' in problems
    assert 'ASub01HomeCharacter::DeclaredOnly is declared by an adapter but defined 0 times' in problems
    assert 'Sub01NeverDefined is used but not defined' in problems
    # A file-static helper repeated in another .cpp collides in a unity build.
    assert re.search(r'Sub01SeatEyeAlpha\(double\) defined 2x: Sub01HomeHands\.cpp:\d+, Sub01HomeLab\.cpp:\d+', problems)


@needs_compiler
def test_compile_faults_fail_with_staged_line_numbers(monkeypatch, tmp_path):
    inject(monkeypatch,
           cpp_tail='void ASub01HomeCharacter::LoadControllerPlayExtra(){\n'
                    ' FString HandsFailure;\n'                                       # shadows the renderer's field
                    ' UE_LOG(LogTemp,Display,TEXT("%s"),ControllerPlayRefusal);\n'  # FString, not *FString
                    '}\n',
           header_line=' void LoadControllerPlayExtra();',
           live_line=' NotAMember(Dt);')
    result = closure.check(tmp_path)
    assert not result['ok']
    errors = failing(result)
    assert {key[1] for key in errors} == {'character'}
    cpp = (tmp_path / 'project/Source/Sub01HomeLab/Sub01HomeLab.cpp').read_text().split('\n')
    shadow = cpp.index(' FString HandsFailure;') + 1
    log = shadow + 1
    probe = cpp.index(' NotAMember(Dt);') + 1
    for (compiler, _, _), text in errors.items():
        assert f'Sub01HomeLab.cpp:{shadow}:' in text and 'shadow' in text, compiler
        assert f'Sub01HomeLab.cpp:{log}:' in text, compiler
        assert f'Sub01HomeLab.cpp:{probe}:' in text and 'NotAMember' in text, compiler


def test_inserted_lines_that_redeclare_a_host_local_are_reported(monkeypatch, tmp_path):
    inject(monkeypatch, live_line=' const double Now=0;')
    problems = '\n'.join(closure.check(tmp_path)['static']['problems'])
    assert "redeclare ['Now'] already declared in ASub01HomeCharacter::UpdateLiveHome" in problems


def test_a_refused_bundle_exits_2(monkeypatch, tmp_path, capsys):
    def refuse(sources):
        raise ValueError('anchor gone')
    monkeypatch.setattr(bundle.controller, 'install', refuse)
    assert closure.main(['--keep', str(tmp_path / 'keep')]) == 2
    assert 'controller: anchor gone' in capsys.readouterr().err


def test_strip_and_items_handle_literals_and_comments():
    text = 'static int A(){ return 1; } // }\nvoid B(){ auto S=TEXT("}{"); char C=\'}\'; /* { */ }\nstruct F { int X; };\n'
    items = closure.top_level_items(text)
    assert [(it['kind'], it['name']) for it in items] == [('definition', 'A'), ('definition', 'B'), ('definition', 'F')]
    assert closure.brace_walk(closure.strip(text)) == (0, 0)
    assert shutil.which('git')
