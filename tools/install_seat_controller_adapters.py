"""Install ONLY the seat adapter, then the controller-play adapter, onto root's freshly staged sources (source only).

Minimal packet for CURRENT origin/main, whose tools/stage_unreal_home_runtime.py stages the renderer but never
installs tools/unreal_seat_transition_runtime.py (so NativeSeatVerified, and with it PC focus, cannot become true).

    python3 tools/install_seat_controller_adapters.py <project>/Source/Sub01HomeLab          # already staged module
    python3 tools/install_seat_controller_adapters.py --stage <project>                      # stage as root does, then install

Order: seat (tools/unreal_seat_transition_runtime.py as it is in THIS checkout -- on origin/main that is root's own
file, unchanged) -> controller (tools/unreal_controller_play_runtime.py). Both are applied in memory first; nothing is
written unless both succeed. Refuses when either is already installed or any anchor is missing/not unique.

Readiness stays false: this installer writes no Config, no evidence, no receipt and no ValidatedHandsPostures entry.
NativeSeatVerified follows only the live pose-matched receipt (seat adapter); ControllerPlayReady() needs the
measured sofa evidence, the controller asset receipt and root's native runtime proof (controller adapter). The
installer checks the installed defaults and that no staged Config validates the Gaming posture.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import unreal_seat_transition_runtime as seat  # noqa: E402
import unreal_controller_play_runtime as controller  # noqa: E402

FILES = {'header': 'Sub01HomeLab.h', 'cpp': 'Sub01HomeLab.cpp', 'hands_header': 'Sub01HomeHands.h', 'hands_cpp': 'Sub01HomeHands.cpp'}
DEFAULTS = {  # installed text that must be present: every readiness flag starts false
    'header': ('NativeSeatVerified=false', 'bool ControllerPlayEvidence=false,ControllerPlayRuntimeProof=false,ControllerPlayActive=false'),
    'cpp': ('ControllerPlayEvidence=false;ControllerPlayClip=nullptr;', 'ControllerPlayRuntimeProof=false;',
            'NativeSeatVerified=SeatOut.ContactVerified;',
            'bool ASub01HomeCharacter::ControllerPlayReady() const{return ControllerPlayEvidence&&ControllerPlayRuntimeProof&&'),
}


# origin/main 70930c8's seat adapter closes LoadSeatTransition one brace early (the cushion block ends with an extra
# '  }'), so the installed module cannot compile. Root's one-line fix (delete that line) is the only change this packet
# needs in a main file: docs/proposed/root-packet-seat-controller-minimal-20261015.seat-brace.patch.
EARLY_BRACE = 'Area,*Cushion.ToString());\n   }\n  }\n  }\n }\n // Contact evidence'


class Refused(Exception):
    pass


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def plan(module: Path) -> dict:
    module = Path(module)
    missing = [n for n in FILES.values() if not (module / n).is_file()]
    if missing:
        raise Refused(f'not a staged Sub01HomeLab module (missing {missing})')
    if EARLY_BRACE in getattr(seat, 'CHARACTER_METHODS', ''):
        raise Refused('seat adapter closes LoadSeatTransition early (extra brace after the cushion block); apply '
                      'docs/proposed/root-packet-seat-controller-minimal-20261015.seat-brace.patch to '
                      'tools/unreal_seat_transition_runtime.py first')
    sources = {k: (module / n).read_text() for k, n in FILES.items()}
    if 'LoadSeatTransition' in sources['cpp'] or 'Sub01SeatTransition.h' in sources['header']:
        raise Refused('seat adapter is already installed')
    if 'ControllerPlayActive' in sources['header'] or 'UpdateControllerPlay(' in sources['cpp']:
        raise Refused('controller adapter is already installed')
    try:
        after_seat = seat.install(sources)
    except ValueError as error:
        raise Refused(f'seat refused: {error}') from None
    try:
        after = controller.install(after_seat)
    except ValueError as error:
        raise Refused(f'controller refused: {error}') from None
    for key, needles in DEFAULTS.items():
        for needle in needles:
            if needle not in after[key]:
                raise Refused(f'readiness default not found after install in {FILES[key]}: {needle!r}')
    return {'sources': sources, 'after': after}


def validated_postures(project: Path) -> list:
    hits = []
    for ini in sorted((Path(project) / 'Config').glob('*.ini')):
        for n, line in enumerate(ini.read_text(errors='replace').splitlines(), 1):
            if 'ValidatedHandsPostures' in line and controller.ROLE in line:
                hits.append(f'{ini.name}:{n}: {line.strip()}')
    return hits


def install(module: Path) -> dict:
    module = Path(module)
    result = plan(module)
    for key, name in FILES.items():
        if result['after'][key] != result['sources'][key]:
            (module / name).write_text(result['after'][key])
    shutil.copy2(seat.HEADER_FILE, module / seat.HEADER_FILE.name)
    project = module.parent.parent
    gaming = validated_postures(project)
    return {'schema': 'sub01.seat-controller-install.v1', 'installed': ['seat', 'controller'],
            'adapters_sha256': {'tools/unreal_seat_transition_runtime.py': sha(TOOLS / 'unreal_seat_transition_runtime.py'),
                                'tools/native_seating/Sub01SeatTransition.h': sha(seat.HEADER_FILE),
                                'tools/unreal_controller_play_runtime.py': sha(TOOLS / 'unreal_controller_play_runtime.py'),
                                'tools/validate_unreal_seat_contact.py': sha(TOOLS / 'validate_unreal_seat_contact.py')},
            'readiness': {'NativeSeatVerified_default': False, 'ControllerPlayReady_without_proofs': False,
                          'validated_gaming_posture_in_config': gaming},
            'ok': not gaming,
            'note': 'Source install only; not compiled or running. No Config, evidence or receipt written.'}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('target', type=Path, help='staged <project>/Source/Sub01HomeLab, or the project with --stage')
    parser.add_argument('--stage', action='store_true', help='stage the project first (tools/stage_unreal_home_runtime.stage)')
    args = parser.parse_args(argv)
    module = args.target
    if args.stage:
        project = args.target
        (project / 'Config').mkdir(parents=True, exist_ok=True)
        if not (project / 'Sub01HomeLab.uproject').exists():
            (project / 'Sub01HomeLab.uproject').write_text('{}')
        from stage_unreal_home_runtime import stage
        stage(project)
        module = project / 'Source/Sub01HomeLab'
    try:
        report = install(module)
    except Refused as error:
        print(f'REFUSED: {error}', file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
