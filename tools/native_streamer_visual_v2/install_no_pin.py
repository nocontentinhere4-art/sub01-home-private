"""No-pin ON TOP of v2 + face + pin fix: the drift guard measures and never moves a bone.

    python tools/native_streamer_visual_v2/install_no_pin.py --source <dir> [--dry-run]

Field result (builds v11 and v13): with the R9 pin and with the per-clip drift guard alike the body left the chair
(seated in the air beside it, turned towards the kitchen), while v2 alone (builds v10/v12, no pin) sits correctly on
the authored transform with the clip's own root. The face camera itself framed the chair from above the monitor as
intended. This patch keeps everything of v2 + face + pin fix (face camera, audit log, mouse -> sitting loop) and turns
`PinStreamerV2` into a measurement: `desk_offset_before_pin_cm` in the receipt still reports the pelvis distance from
the clip's own reference, but the pose is left exactly as the clips author it. One file changes (Sub01HomeHands.cpp,
three anchors found exactly once). Refused when the pin fix is absent or `// SUB01_STREAMER_VISUAL_V2_NOPIN` is present.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location('sub01_streamer_visual_v2_pinfix', Path(__file__).resolve().parent / 'install_pin_fix.py')
pinfix = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(pinfix)
face, v2, Refused = pinfix.face, pinfix.v2, pinfix.Refused

MARKER = '// SUB01_STREAMER_VISUAL_V2_NOPIN'
FILES = dict(v2.FILES)
PATCHED = ('hands_cpp',)


def _line(text: str, start: str) -> str:
    """The one line of `text` starting with `start`, newline included."""
    hits = [line for line in text.splitlines(keepends=True) if line.startswith(start)]
    if len(hits) != 1:
        raise RuntimeError(f'expected one line starting with {start!r} in the pin fix, found {len(hits)}')
    return hits[0]


CONSTANTS = _line(pinfix.NEW_PROXY, ' static constexpr double StreamerV2PinRadiusCm=')
RECORD = _line(pinfix.NEW_PROXY, '  if(Record){FTransform Pelvis=FTransform::Identity;if(StreamerV2Pelvis(Composed,Pelvis))')
GUARD_LOG_TAIL = f'maxDeg={face.PIN_MAX_DEG:g}"),PelvisBone,StreamerV2PinChain.Num(),StreamerV2ReferenceSeconds);'

EDITS = [
    ('hands_cpp', CONSTANTS, CONSTANTS +
     f' static constexpr bool StreamerV2PinEnabled=false; {MARKER} (tools/native_streamer_visual_v2/install_no_pin.py): the guard measures, the pose keeps each clip\'s own placement\n'),
    ('hands_cpp', RECORD, RECORD +
     f'  if(!StreamerV2PinEnabled)return; {MARKER}: measured above for the receipt, nothing moved\n'),
    ('hands_cpp', GUARD_LOG_TAIL,
     f'maxDeg={face.PIN_MAX_DEG:g} applied=0 (measure only)"),PelvisBone,StreamerV2PinChain.Num(),StreamerV2ReferenceSeconds); {MARKER}'),
]


def plan(sources: dict) -> dict:
    """Pure transformation of the four LF texts; only 'hands_cpp' changes. Raises Refused, never partial."""
    problems = [f'{FILES[key]} already carries {MARKER} (no-pin already installed)' for key in PATCHED if MARKER in sources[key]]
    if problems:
        raise Refused('; '.join(problems))
    problems = [f'{FILES[key]} lacks the pin fix ({pinfix.MARKER}); run install.py, install_face_camera.py and install_pin_fix.py first'
                for key in PATCHED if pinfix.MARKER not in sources[key]]
    if problems:
        raise Refused('; '.join(problems))
    out, edits = dict(sources), []
    for key, anchor, replacement in EDITS:
        count = out[key].count(anchor)
        edits.append({'file': FILES[key], 'anchor': anchor.strip()[:96], 'anchor_sha256': v2.sha256(anchor), 'count': count})
        if count != 1:
            problems.append(f'anchor {"missing" if count == 0 else f"found {count}x"} in {FILES[key]}: {anchor.strip()[:96]!r}')
            continue
        out[key] = out[key].replace(anchor, replacement, 1)
    if problems:
        raise Refused('; '.join(problems))
    for key in PATCHED:
        if v2.balance(sources[key]) != v2.balance(out[key]):
            raise Refused(f'{FILES[key]}: bracket balance changed by the install')
        if MARKER not in out[key]:
            raise Refused(f'{FILES[key]}: marker missing after install')
    return {'sources': out, 'edits': edits}


def run(source: Path, dry_run: bool) -> dict:
    source = Path(source).resolve()
    missing = [n for n in FILES.values() if not (source / n).is_file()]
    if missing:
        raise Refused(f'missing in {source}: {", ".join(missing)}')
    raw = {key: v2.read_raw(source / name) for key, name in FILES.items()}
    eol = {key: v2.line_ending(FILES[key], raw[key]) for key in FILES}
    result = plan({key: text.replace('\r\n', '\n') for key, text in raw.items()})
    after = {key: result['sources'][key].replace('\n', eol[key]) for key in PATCHED}
    report = {'schema': 'sub01.native-streamer-visual-v2-nopin-install.v1', 'source': str(source), 'dry_run': dry_run,
              'marker': MARKER, 'requires': pinfix.MARKER,
              'pin': {'applied': False, 'measured': 'desk_offset_before_pin_cm = pelvis distance from the clip\'s own reference'},
              'edits': result['edits'],
              'files': {FILES[key]: {'before_sha256': v2.sha256(raw[key]), 'after_sha256': v2.sha256(after[key]),
                                     'bytes_before': len(raw[key].encode()), 'bytes_after': len(after[key].encode()),
                                     'line_ending': 'CRLF' if eol[key] == '\r\n' else 'LF',
                                     'edits': sum(1 for k, _, _ in EDITS if k == key)} for key in PATCHED},
              'read_only': {FILES[key]: v2.sha256(raw[key]) for key in FILES if key not in PATCHED}}
    if not dry_run:
        v2.write_atomically({source / FILES[key]: after[key] for key in PATCHED})
        for key in PATCHED:
            if v2.sha256(v2.read_raw(source / FILES[key])) != report['files'][FILES[key]]['after_sha256']:
                raise Refused(f'{FILES[key]}: written bytes differ from the plan')
    report['status'] = 'planned' if dry_run else 'applied'
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True, help='directory with the v2+face+pinfix pod files (patched in place)')
    parser.add_argument('--dry-run', action='store_true', help='check every anchor and print the report; write nothing')
    args = parser.parse_args(argv)
    try:
        report = run(args.source, args.dry_run)
    except Refused as error:
        print(json.dumps({'schema': 'sub01.native-streamer-visual-v2-nopin-install.v1', 'source': str(args.source),
                          'dry_run': args.dry_run, 'status': 'refused', 'reason': str(error)}, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
