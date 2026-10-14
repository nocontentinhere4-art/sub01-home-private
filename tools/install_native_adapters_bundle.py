"""Install the seat, life (+bed root motion) and controller native adapters onto root's CURRENT staged sources.

One command for the renderer (private; source only; nothing is compiled, run or deployed here):

    python3 tools/install_native_adapters_bundle.py <project>/Source/Sub01HomeLab --dry-run
    python3 tools/install_native_adapters_bundle.py <project>/Source/Sub01HomeLab [--only seat,life,bed,controller]
                                                    [--receipt PATH] [--show-diff]

The module must have been freshly staged by root's tools/stage_unreal_home_runtime.stage() (and nothing else
installed on top). The bundle then, entirely in memory:
  1. checks preconditions: the module and its four generated sources exist; each adapter's Python and header exist;
     no selected adapter is (even partly) installed; every adapter anchor is unique at its turn in the chain;
  2. installs in the fixed order seat -> life -> bed -> controller (bed = tools/unreal_bed_root_motion.py, which
     extends the life adapter's bed phases and therefore needs life);
  3. verifies the result is ADDITIVE ONLY (every original line of every generated file survives, in order) and
     that root's gates are byte-identical: the exact gate lines (walk rate, gaze smoothing, PC operator focus,
     privacy, Minecraft TV input) and the whole bodies of the gate functions (posture whitelist, PC privacy, TV
     input, fixture emission guards, privacy blackout receipt, Desk interact). Every other module file
     (policies, PC/device bridges, Build.cs) must stay byte-identical;
  4. only then writes the four sources and copies the two adapter headers, and writes a receipt JSON
     (default <project>/private-audit/native-adapters-install-receipt.json) with adapter sha256s, the branch
     commit, the anchors used, gate-line hashes and before/after file hashes.
It refuses (exit 2, nothing written) on anything unexpected. It never writes evidence, config or proof files, so
every readiness gate (NativeSeatVerified, LifeReady, ControllerPlayReady) stays false until the real seat/contact/
input proofs exist; see docs/proposed/native-adapters-install-runbook.md. Rollback = re-stage from root's main.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import unreal_seat_transition_runtime as seat  # noqa: E402
import unreal_life_clips_runtime as life  # noqa: E402
import unreal_bed_root_motion as bed  # noqa: E402
import unreal_controller_play_runtime as controller  # noqa: E402

RECEIPT_SCHEMA = 'sub01.native-adapters-install-receipt.v1'
ORDER = ('seat', 'life', 'bed', 'controller')
SOURCE_FILES = {'header': 'Sub01HomeLab.h', 'cpp': 'Sub01HomeLab.cpp', 'hands_header': 'Sub01HomeHands.h', 'hands_cpp': 'Sub01HomeHands.cpp'}

# name -> (module, adapter python, header to copy or None, installed markers (file key, text), requires)
ADAPTERS = {
    'seat': (seat, TOOLS / 'unreal_seat_transition_runtime.py', seat.HEADER_FILE,
             (('header', 'FSub01SeatTransition SeatMachine;'), ('cpp', 'UpdateSeatTransition(Dt);'),
              ('header', '#include "Sub01SeatTransition.h"')), ()),
    'life': (life, TOOLS / 'unreal_life_clips_runtime.py', life.HEADER_FILE,
             (('header', 'FSub01LifeMachine LifeMachine;'), ('cpp', 'UpdateLifeClips(Instance,DeltaSeconds);'),
              ('header', '#include "Sub01LifeClips.h"')), ()),
    'bed': (bed, TOOLS / 'unreal_bed_root_motion.py', None,
            (('header', 'LoadLifeRootPath();'), ('cpp', 'LoadLifeRootPath();')), ('life',)),
    'controller': (controller, TOOLS / 'unreal_controller_play_runtime.py', None,
                   (('header', 'ControllerPlayActive'), ('cpp', 'UpdateControllerPlay(')), ()),
}

# Root's gates. A marker starting with '= ' names a whole line (' ' + rest, may occur several times); any other
# marker is a substring that must match exactly ONE line of the freshly staged sources. The matched whole line
# must occur in the installed sources exactly as often as before (byte-identical, never edited or duplicated).
GATE_LINES = (
    ('walk_rate', 'cpp', ' Instance->TargetRate=HandsPosture==TEXT("Walk")?'),
    ('walk_moving', 'cpp', ' const bool Moving=HandsPosture==TEXT("Walk")&&GetCharacterMovement()->IsMovingOnGround()'),
    ('walk_idle_choice', 'cpp', ' const bool PlayingIdle=HandsPosture==TEXT("Walk")&&!Moving'),
    ('gaze_pitch', 'cpp', 'Sub01FirstPersonMotion::SmoothAngle(CurrentLook.Pitch'),
    ('gaze_yaw', 'cpp', 'Sub01FirstPersonMotion::SmoothAngle(CurrentLook.Yaw'),
    ('gaze_roll_walk_input', 'cpp', 'Sub01FirstPersonMotion::SmoothAngle(CurrentLook.Roll'),
    ('live_privacy_revoke', 'cpp', ' if(LiveHomePrivate){NativeSeatVerified=false;if(PCBridge)PCBridge->SetOperatorFocus(false);}'),
    ('live_stale_stop', 'cpp', ' if(!LiveHomeFresh||Now<LiveHomeLastReceived||Now-LiveHomeLastReceived>3||LiveHomeBlocked){'),
    ('pc_operator_focus', 'cpp', ' if(!LiveHomePath.Num()){if(PCBridge)PCBridge->SetOperatorFocus(NativeSeatVerified&&NativeFeedbackSeatReady()'),
    ('desk_interact_seat_gate', 'cpp', ' if(Device==TEXT("Desk")&&PCBridge){if(LiveHome&&!NativeSeatVerified){'),
    ('tick_minecraft_tv_input', 'cpp', '= TickMinecraftTVInput();'),
    ('tick_pc_privacy', 'cpp', '= UpdateNativePCPrivacy();'),
    ('poll_privacy_field', 'cpp', 'LiveHomePrivate=Private;if(PCBridge)PCBridge->SetLocalPrivacy(Private);'),
    ('first_person_motion_include', 'cpp', '#include "Sub01FirstPersonMotionPolicy.h"'),
    ('fixture_emission_include', 'cpp', '#include "Sub01NativeFixtureEmissionPolicy.h"'),
    ('validated_postures_config', 'header', 'TArray<FName> ValidatedHandsPostures;'),
)
# Whole function/class bodies (from the signature line to the first line that is exactly '}' or '};').
GATE_BODIES = (
    ('cpp', 'void ASub01HomeCharacter::Forward(float Value) {'),
    ('cpp', 'void ASub01HomeCharacter::Right(float Value) {'),
    ('cpp', 'void ASub01HomeCharacter::Interact() {'),
    ('cpp', 'bool ASub01HomeCharacter::SetHandsPosture(FName Posture) {'),
    ('cpp', 'void ASub01HomeCharacter::UpdateNativePCPrivacy(){'),
    ('cpp', 'bool ASub01HomeCharacter::TryNativeHomeDevice(UActorComponent* Component){'),
    ('cpp', 'void ASub01HomeCharacter::PollLiveHome(){'),
    ('cpp', 'bool ASub01HomeCharacter::NativeFeedbackSeatReady() const{'),
    ('cpp', 'void ASub01HomeCharacter::PublishPrivateNativeCameraPrivacy(bool Hidden){'),
    ('cpp', 'bool ASub01HomeCharacter::PrepareNativeFixtureEmission(){'),
    ('cpp', 'void ASub01HomeCharacter::ApplyNativeFixtureEmission(const FString& Lamp,bool Enabled){'),
    ('cpp', 'class FSub01MinecraftTVInput:public IInputProcessor{'),
    ('cpp', 'void ASub01HomeCharacter::FocusMinecraftTV(const FHitResult& Hit){'),
    ('cpp', 'bool ASub01HomeCharacter::PublishMinecraftTVReceipt(bool Clear){'),
    ('cpp', 'void ASub01HomeCharacter::SendMinecraftTVInput(const FString& Operation){'),
    ('cpp', 'void ASub01HomeCharacter::TickMinecraftTVInput(){'),
    ('cpp', 'void ASub01HomeCharacter::ReleaseMinecraftTVInput(){'),
)


class Refused(Exception):
    pass


def sha(data) -> str:
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()


def body(text: str, signature: str) -> str:
    lines = text.split('\n')
    starts = [i for i, line in enumerate(lines) if line.startswith(signature)]
    if len(starts) != 1:
        raise Refused(f'gate body {signature!r} found {len(starts)} times (expected exactly 1)')
    for end in range(starts[0], len(lines)):
        if lines[end] in ('}', '};'):
            return '\n'.join(lines[starts[0]:end + 1])
    raise Refused(f'gate body {signature!r} has no closing line')


def gate_snapshot(sources: dict) -> dict:
    lines = {}
    for name, key, marker in GATE_LINES:
        text = sources[key].split('\n')
        hits = [l for l in text if l == ' ' + marker[2:]] if marker.startswith('= ') else [l for l in text if marker in l]
        if not hits or (not marker.startswith('= ') and len(hits) != 1):
            raise Refused(f'gate line {name} matches {len(hits)} lines in {key} (root changed it? update GATE_LINES)')
        lines[name] = {'file': SOURCE_FILES[key], 'key': key, 'line': hits[0], 'count': len(hits),
                       'sha256': sha('\n'.join(hits))}
    bodies = {}
    for key, signature in GATE_BODIES:
        text = body(sources[key], signature)
        bodies[signature] = {'file': SOURCE_FILES[key], 'sha256': sha(text), 'lines': text.count('\n') + 1}
    return {'lines': lines, 'bodies': bodies}


def check_gates(after: dict, snapshot: dict) -> dict:
    for name, entry in snapshot['lines'].items():
        if after[entry['key']].split('\n').count(entry['line']) != entry['count']:
            raise Refused(f'gate line {name} changed, vanished or was duplicated')
    for key, signature in GATE_BODIES:
        if sha(body(after[key], signature)) != snapshot['bodies'][signature]['sha256']:
            raise Refused(f'gate body {signature!r} is not byte-identical after install')
    return {name: entry['sha256'] for name, entry in snapshot['lines'].items()}


def check_additive(before: dict, after: dict) -> None:
    """Every original line survives unchanged and in order (the install only inserts whole lines)."""
    for key, text in before.items():
        new = after[key].split('\n')
        position = 0
        for number, line in enumerate(text.split('\n'), 1):
            try:
                position = new.index(line, position) + 1
            except ValueError:
                raise Refused(f'{SOURCE_FILES[key]} line {number} was edited, moved or removed: {line[:80]!r}') from None


def installed(name: str, sources: dict) -> list:
    return [text for key, text in ADAPTERS[name][3] if text in sources[key]]


def anchors_of(name: str, sources: dict) -> list:
    module = ADAPTERS[name][0]
    report = []
    for key, anchor, _ in module.EDITS:
        if name in ('seat', 'life') and anchor == getattr(module, 'SEAT_RATE_ANCHOR', getattr(module, 'RATE_ANCHOR', None)):
            report.append({'file': SOURCE_FILES[key], 'anchor': 'unique line starting ' + module.RATE_PREFIX.strip(),
                           'count': sum(1 for l in sources[key].split('\n') if l.strip().startswith(module.RATE_PREFIX))})
            continue
        report.append({'file': SOURCE_FILES[key], 'anchor': anchor.strip()[:100], 'count': sources[key].count(anchor)})
    if name == 'controller':
        report.append({'file': SOURCE_FILES['cpp'], 'anchor': 'unique line starting ' + controller.RATE_PREFIX.strip(),
                       'count': sum(1 for l in sources['cpp'].split('\n') if l.startswith(controller.RATE_PREFIX))})
    return report


def plan(module_dir: Path, only=ORDER) -> dict:
    module_dir = Path(module_dir)
    unknown = [n for n in only if n not in ORDER]
    if unknown:
        raise Refused(f'unknown adapter(s): {unknown}; choose from {ORDER}')
    selected = [n for n in ORDER if n in only]
    if not selected:
        raise Refused('nothing selected')
    if not module_dir.is_dir():
        raise Refused(f'{module_dir} is not a staged Source/Sub01HomeLab directory')
    for name in SOURCE_FILES.values():
        if not (module_dir / name).is_file():
            raise Refused(f'staged source missing: {module_dir / name}')
    for name in selected:
        _, py, header, _, _ = ADAPTERS[name]
        for path in (py, header):
            if path is not None and not path.is_file():
                raise Refused(f'adapter file missing: {path}')
        if header is not None and (module_dir / header.name).exists():
            raise Refused(f'{header.name} already exists in the module (already installed? re-stage from main)')
    before = {key: (module_dir / name).read_text() for key, name in SOURCE_FILES.items()}
    for name in ORDER:
        found = installed(name, before)
        if found and name in selected:
            raise Refused(f'{name} is already (partly) installed: {found}; re-stage from main first')
    snapshot = gate_snapshot(before)
    current, steps = dict(before), []
    for name in selected:
        for need in ADAPTERS[name][4]:
            if need not in selected and not installed(need, current):
                raise Refused(f'{name} needs {need} (select it or install it first)')
        anchors = anchors_of(name, current)
        bad = [a for a in anchors if a['count'] != 1]
        if bad:
            raise Refused(f'{name}: anchor not unique on these sources: {bad}')
        try:
            current = ADAPTERS[name][0].install(current)
        except ValueError as error:
            raise Refused(f'{name}: {error}') from None
        steps.append({'adapter': name, 'anchors': anchors})
    check_additive(before, current)
    gate_hashes = check_gates(current, snapshot)
    others = sorted(p.name for p in module_dir.iterdir() if p.is_file() and p.name not in SOURCE_FILES.values())
    return {'module': module_dir, 'selected': selected, 'before': before, 'after': current, 'steps': steps,
            'snapshot': snapshot, 'gate_hashes': gate_hashes, 'other_files': {n: sha((module_dir / n).read_bytes()) for n in others}}


def branch_commit() -> dict:
    def git(*args):
        try:
            return subprocess.run(['git', '-C', str(TOOLS), *args], capture_output=True, text=True, timeout=20).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ''
    files = [str(ADAPTERS[n][1].relative_to(TOOLS.parent)) for n in ORDER] + ['tools/native_seating/Sub01SeatTransition.h',
             'tools/native_life/Sub01LifeClips.h', 'tools/install_native_adapters_bundle.py', 'tools/validate_unreal_seat_contact.py']
    return {'commit': git('rev-parse', 'HEAD'), 'branch': git('rev-parse', '--abbrev-ref', 'HEAD'),
            'adapter_files_dirty': bool(git('status', '--porcelain', '--', *files))}


def summary(result: dict, show_diff=False) -> str:
    out = [f'native adapters bundle: {" -> ".join(result["selected"])} into {result["module"]}']
    for key, name in SOURCE_FILES.items():
        old, new = result['before'][key].split('\n'), result['after'][key].split('\n')
        matcher = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
        hunks = [op for op in matcher.get_opcodes() if op[0] != 'equal']
        out.append(f'  {name}: +{len(new) - len(old)} lines in {len(hunks)} insertion(s), 0 removed')
        for tag, i1, _, j1, j2 in hunks:
            after_line = old[i1 - 1].strip()[:90] if i1 else '<start of file>'
            out.append(f'    {tag} +{j2 - j1} after original line {i1}: {after_line}')
        if show_diff:
            out.extend(difflib.unified_diff(old, new, f'a/{name}', f'b/{name}', n=1, lineterm=''))
    for name in result['selected']:
        header = ADAPTERS[name][2]
        if header is not None:
            out.append(f'  copy {header.name} ({sha(header.read_bytes())[:16]})')
    out.append(f'  gates byte-identical: {len(result["gate_hashes"])} lines, {len(GATE_BODIES)} bodies; '
               f'{len(result["other_files"])} other module files untouched')
    out.append('  readiness: unchanged (no evidence/config/proof written; every Ready gate stays false)')
    return '\n'.join(out)


def receipt(result: dict) -> dict:
    adapters = {}
    for name in result['selected']:
        _, py, header, _, _ = ADAPTERS[name]
        adapters[name] = {'python': py.name, 'python_sha256': sha(py.read_bytes())}
        if header is not None:
            adapters[name].update(header=header.name, header_sha256=sha(header.read_bytes()))
    return {
        'schema': RECEIPT_SCHEMA, 'order': result['selected'], 'source': branch_commit(),
        'bundle_sha256': sha(Path(__file__).read_bytes()),
        'support_sha256': {'validate_unreal_seat_contact.py': sha((TOOLS / 'validate_unreal_seat_contact.py').read_bytes())},
        'adapters': adapters, 'steps': result['steps'],
        'gate_lines_sha256': result['gate_hashes'],
        'gate_bodies_sha256': {sig: e['sha256'] for sig, e in result['snapshot']['bodies'].items()},
        'sources_before_sha256': {SOURCE_FILES[k]: sha(v) for k, v in result['before'].items()},
        'sources_after_sha256': {SOURCE_FILES[k]: sha(v) for k, v in result['after'].items()},
        'other_module_files_sha256': result['other_files'],
        'additive_only': True, 'compiled': False, 'readiness_claimed': False,
        'note': 'Source install only. Seat/life/controller readiness stays false until the measured seat/contact/input proofs exist.',
    }


def apply(result: dict, receipt_path: Path) -> dict:
    module_dir = result['module']
    # Re-read right before writing: refuse if anything changed since the plan.
    for key, name in SOURCE_FILES.items():
        if (module_dir / name).read_text() != result['before'][key]:
            raise Refused(f'{name} changed while planning; nothing written')
    doc = receipt(result)
    for key, name in SOURCE_FILES.items():
        temp = module_dir / f'.{name}.bundle-tmp'
        temp.write_text(result['after'][key])
        os.replace(temp, module_dir / name)
    for name in result['selected']:
        header = ADAPTERS[name][2]
        if header is not None:
            (module_dir / header.name).write_bytes(header.read_bytes())
    for name, digest in result['other_files'].items():
        if sha((module_dir / name).read_bytes()) != digest:
            raise Refused(f'{name} changed during install')
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(doc, indent=2) + '\n')
    return doc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('module', type=Path, help='<project>/Source/Sub01HomeLab, freshly staged from root main')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--only', default=','.join(ORDER), help='comma list from seat,life,bed,controller (installed in that fixed order)')
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--show-diff', action='store_true')
    args = parser.parse_args(argv)
    try:
        result = plan(args.module, tuple(n.strip() for n in args.only.split(',') if n.strip()))
        print(summary(result, args.show_diff))
        if args.dry_run:
            print('dry run: nothing written')
            return 0
        path = args.receipt or args.module.resolve().parents[1] / 'private-audit' / 'native-adapters-install-receipt.json'
        apply(result, path)
        print(f'installed; receipt {path}; not compiled')
        return 0
    except Refused as error:
        print(f'REFUSED: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
