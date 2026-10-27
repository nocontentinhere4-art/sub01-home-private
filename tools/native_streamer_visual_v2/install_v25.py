"""v25 ON TOP of v24: the native character follows the agent's motion object (lean, head tilt, breathing rate, gestures)
and honours its nods (owner 2026-10-27: "migliora la cazzo di animazione"; designed and written with Kimi).

    python tools/native_streamer_visual_v2/install_v25.py --source <Source/Sub01HomeLab dir> [--dry-run]

The edits live in `v25_edits.json` next to this file: [{"file", "anchor", "replacement"}, ...]. Every anchor must occur
exactly once in its file before ANY write (all or nothing); refused when `// SUB01_STREAMER_VISUAL_V2_V25` is already present
in any edited file or v24 (`// SUB01_STREAMER_VISUAL_V2_V24`) is missing. Line endings are kept (CRLF/LF), writes are atomic
(tmp + rename), and a JSON report with the before/after sha256 of every file is printed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

MARKER = '// SUB01_STREAMER_VISUAL_V2_V25'
REQUIRES = '// SUB01_STREAMER_VISUAL_V2_V24'
EDITS_FILE = Path(__file__).with_name('v25_edits.json')


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def plan(source: Path, edits: list) -> dict:
    """{file: (original bytes, new text, newline)}; raises ValueError naming the first anchor or file that fails."""
    out = {}
    for name in sorted({e['file'] for e in edits}):
        raw = (source / name).read_bytes()
        newline = '\r\n' if b'\r\n' in raw else '\n'
        text = raw.decode('utf-8').replace('\r\n', '\n')
        if MARKER in text:
            raise ValueError(f'{name}: v25 already installed')
        out[name] = [raw, text, newline]
    if not any(REQUIRES in t for _, t, _ in out.values()):
        raise ValueError('v24 marker not found: install v24 first')
    for i, e in enumerate(edits):
        text = out[e['file']][1]
        anchor = e['anchor'].replace('\r\n', '\n')
        n = text.count(anchor)
        if n != 1:
            raise ValueError(f'edit {i} ({e["file"]}): anchor found {n} times: {anchor[:90]!r}')
        if MARKER not in e['replacement']:
            raise ValueError(f'edit {i} ({e["file"]}): replacement carries no {MARKER} marker')
        out[e['file']][1] = text.replace(anchor, e['replacement'].replace('\r\n', '\n'), 1)
    return out


def run(source: Path, dry_run: bool) -> dict:
    edits = json.loads(EDITS_FILE.read_text())
    planned = plan(source, edits)
    report = {'source': str(source), 'dry_run': dry_run, 'edits': len(edits), 'files': {}}
    for name, (raw, text, newline) in planned.items():
        data = text.replace('\n', newline).encode('utf-8')
        report['files'][name] = {'before': sha(raw), 'after': sha(data)}
        if not dry_run:
            path = source / name
            tmp = path.with_name(path.name + '.v25tmp')
            tmp.write_bytes(data)
            os.chmod(tmp, path.stat().st_mode & 0o7777)
            os.replace(tmp, path)
    return report


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--source', required=True, type=Path)
    p.add_argument('--dry-run', action='store_true')
    a = p.parse_args(argv)
    try:
        print(json.dumps(run(a.source, a.dry_run), indent=1))
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
