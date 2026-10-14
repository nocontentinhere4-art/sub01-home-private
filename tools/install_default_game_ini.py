"""Strict, idempotent installer for the seat / seated-fit / Idle lines in <project>/Config/DefaultGame.ini.

Replaces the hand-appended config steps of docs/proposed/native-adapters-import-plan-2c61c93.md (step 6). Private,
source-side only: nothing is compiled, imported, run or deployed, and no readiness is claimed.

    python3 tools/install_default_game_ini.py <project> --dry-run [--only seat,seated-fit,idle]
    python3 tools/install_default_game_ini.py <project> [--only seat,idle]          (default: seat,idle)
    python3 tools/install_default_game_ini.py <project> --restore [RECEIPT]

Components and the receipt each one requires before any line is written (all under the renderer's
[/Script/Sub01HomeLab.Sub01HomeCharacter]):
  seat        <project>/unreal-seating-import.json (root's tools/unreal_import_seating_fbx.py): the four captured roles
              on SUB01_OriginalOwner_Skeleton at their exact paths
              -> +ValidatedHandsPostures=StandToSit / Sitting / SitToType / SitToStand
  seated-fit  <project>/private-audit/unreal-seated-fit-import.json (tools/unreal_import_seated_fit_fbx.py): only rows the
              receipt ACCEPTED whose committed per-clip fit report still passes; a failed fit is never written
              -> +ValidatedHandsPostures=<SeatedIdle | DeskTypingSeated | SitToTypeSeated | ...>
  idle        <project>/private-audit/native-life-clips-inventory.json + <project>/unreal-life-import.json, through
              tools/unreal_life_clips_runtime.py config_fragment() (Idle only; bed roles have their own tool)
              -> IdleClipPath=/Game/Sub01Hands/Life/SUB01_Idle.SUB01_Idle, +ValidatedHandsPostures=Idle

Rules: exact lines, inserted at the end of the one target section (created at the end of the file if absent); never
edits, moves or removes an existing line. An identical line already present is a no-op. A conflicting existing value
for the same key (another IdleClipPath, a -/!/plain ValidatedHandsPostures entry for a role being added, a
duplicated section) refuses with exit 2 and nothing written. On a write: timestamped backup next to the file plus a
receipt private-audit/default-game-ini-install-<UTC>.json with sha256 before/after and readiness_claimed: false.
--restore puts the backup back only when the current file's sha256 equals the receipt's after-hash.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import unreal_life_clips_runtime as life  # noqa: E402
import unreal_seat_transition_runtime as seat  # noqa: E402

SECTION = life.CHARACTER_SECTION                       # [/Script/Sub01HomeLab.Sub01HomeCharacter]
INI = 'Config/DefaultGame.ini'
SCHEMA = 'sub01.default-game-ini-install.v1'
RESTORE_SCHEMA = 'sub01.default-game-ini-restore.v1'
RECEIPT_GLOB = 'default-game-ini-install-*.json'
COMPONENTS = ('seat', 'seated-fit', 'idle')
DEFAULT = ('seat', 'idle')
SEATING_RECEIPT = 'unreal-seating-import.json'
LIFE_INVENTORY = 'private-audit/native-life-clips-inventory.json'
LIFE_RECEIPT = 'unreal-life-import.json'


class Refused(Exception):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load(path: Path, what: str) -> dict:
    if not path.is_file():
        raise Refused(f'{what} missing: {path}')
    try:
        return json.loads(path.read_text())
    except ValueError as error:
        raise Refused(f'{what} is not JSON: {path} ({error})') from None


# ------------------------------------------------------------------ required lines per component
def seat_lines(project: Path) -> tuple[list, dict]:
    path = project / SEATING_RECEIPT
    receipt = _load(path, 'seating import receipt')
    if receipt.get('skeleton') != seat.OWNER_SKELETON:
        raise Refused(f'seating receipt skeleton {receipt.get("skeleton")!r} is not {seat.OWNER_SKELETON}')
    rows = {r.get('role'): r for r in receipt.get('clips', []) if isinstance(r, dict)}
    if set(rows) != set(seat.SEAT_ROLE_ASSETS.values()) or len(receipt.get('clips', [])) != 4:
        raise Refused(f'seating receipt must hold exactly the roles {sorted(seat.SEAT_ROLE_ASSETS.values())}')
    for role, asset in seat.SEAT_ROLE_ASSETS.items():
        row, want = rows[asset], f'{seat.SEAT_CLIP_DIR}/SUB01_{asset}.SUB01_{asset}'
        if row.get('object_path') != want or row.get('same_existing_skeleton') is not True:
            raise Refused(f'seating row {asset} is not {want} on the existing owner skeleton')
    if receipt.get('original_bone_identities_preserved') is not True:
        raise Refused('seating receipt does not preserve the owner bone identities')
    return [f'+ValidatedHandsPostures={role}' for role in seat.SEAT_ROLES], {'path': str(path), 'sha256': sha(path.read_bytes())}


def seated_fit_lines(project: Path) -> tuple[list, dict]:
    import unreal_import_seated_fit_fbx as fit
    path = project / seat.SEATED_FIT_RECEIPT
    receipt = _load(path, 'seated-fit import receipt')
    committed = {r['role']: r['fit_pass'] for r in fit.plan_clips()}
    bound = seat.seated_fit_bindings(receipt, validated=set(seat.SEATED_FIT_SLOTS))
    roles = [v['role'] for v in bound.values() if v['bound'] and committed.get(v['role']) is True]
    if not roles:
        raise Refused('seated-fit receipt accepts no role: ' + '; '.join(f'{v["role"]}: {v.get("refusal")}' for v in bound.values()))
    order = list(seat.SEATED_FIT_SLOTS)
    return [f'+ValidatedHandsPostures={r}' for r in sorted(roles, key=order.index)], {'path': str(path), 'sha256': sha(path.read_bytes())}


def idle_lines(project: Path) -> tuple[list, dict]:
    inventory_path, import_path = project / LIFE_INVENTORY, project / LIFE_RECEIPT
    inventory, report = _load(inventory_path, 'life inventory'), _load(import_path, 'life import receipt')
    roles = life.role_bindings(inventory, report)
    if not roles['Idle']['bound']:
        raise Refused(f'Idle not bindable: {roles["Idle"].get("refusal")} ({roles["Idle"].get("reason")})')
    text, _ = life.config_fragment(inventory, report)
    want = [f'IdleClipPath={roles["Idle"]["object_path"]}', '+ValidatedHandsPostures=Idle']
    if any(line not in text.splitlines() for line in want):
        raise Refused('life config_fragment disagrees with its own Idle binding')
    return want, {'path': [str(inventory_path), str(import_path)],
                  'sha256': [sha(inventory_path.read_bytes()), sha(import_path.read_bytes())]}


PRODUCERS = {'seat': seat_lines, 'seated-fit': seated_fit_lines, 'idle': idle_lines}


# ------------------------------------------------------------------ ini editing
def _key(line: str):
    """(op, key, value) of an ini assignment, or None for blanks/comments/sections."""
    s = line.strip()
    if not s or s.startswith((';', '#', '[')) or '=' not in s:
        return None
    left, value = s.split('=', 1)
    op = left[0] if left[:1] in '+-!.' else ''
    return op, left[len(op):].strip(), value.strip()


def plan(project: Path, only=DEFAULT) -> dict:
    project = Path(project)
    unknown = [c for c in only if c not in COMPONENTS]
    if unknown or not only:
        raise Refused(f'choose components from {COMPONENTS} (got {list(only)})')
    ini = project / INI
    if not ini.is_file():
        raise Refused(f'{ini} missing; refusing to create the renderer config')
    data = ini.read_bytes()
    text = data.decode('utf-8')
    newline = '\r\n' if '\r\n' in text else '\n'
    lines = text.splitlines()
    want, sources = [], {}
    for name in [c for c in COMPONENTS if c in only]:
        got, source = PRODUCERS[name](project)
        sources[name] = source
        want.extend(l for l in got if l not in want)
    headers = [i for i, l in enumerate(lines) if l.strip() == SECTION]
    if len(headers) > 1:
        raise Refused(f'{SECTION} appears {len(headers)} times; ambiguous')
    if headers:
        start = headers[0] + 1
        end = next((i for i in range(start, len(lines)) if lines[i].strip().startswith('[')), len(lines))
    else:
        start = end = len(lines)
    body = [l.strip() for l in lines[start:end]]
    entries = [k for k in map(_key, body) if k]
    present, add = [], []
    for line in want:
        op, key, value = _key(line)
        if line in body:
            present.append(line)
            continue
        if op == '+':
            clash = [e for e in entries if e[1] == key and e[2] == value and e[0] != '+'] + [e for e in entries if e[1] == key and e[0] == '!']
        else:
            clash = [e for e in entries if e[1] == key]
        if clash:
            raise Refused(f'conflicting existing entry for {key}: {["".join((e[0], e[1], "=", e[2])) for e in clash]} vs {line!r}')
        add.append(line)
    if not add:
        return {'ini': ini, 'before': data, 'after': data, 'add': [], 'present': present, 'sources': sources, 'components': list(only)}
    if headers:
        insert = end
        while insert > start and not lines[insert - 1].strip():
            insert -= 1
        new = lines[:insert] + add + lines[insert:]
    else:
        new = lines + ([''] if lines and lines[-1].strip() else []) + [SECTION] + add
    out = newline.join(new) + (newline if text.endswith(('\n', '\r\n')) or not headers else '')
    after = out.encode('utf-8')
    # Append-only proof: every original line survives, in order.
    position = 0
    for line in lines:
        try:
            position = new.index(line, position) + 1
        except ValueError:
            raise Refused(f'internal: original line lost: {line!r}') from None
    return {'ini': ini, 'before': data, 'after': after, 'add': add, 'present': present, 'sources': sources, 'components': list(only)}


def apply(result: dict, project: Path, now=None) -> dict | None:
    if not result['add']:
        return None
    ini = result['ini']
    if ini.read_bytes() != result['before']:
        raise Refused(f'{ini} changed while planning; nothing written')
    stamp = (now or datetime.now(timezone.utc)).strftime('%Y%m%dT%H%M%S%fZ')
    backup = ini.with_name(f'{ini.name}.bak-{stamp}')
    if backup.exists():
        raise Refused(f'backup {backup} already exists')
    backup.write_bytes(result['before'])
    temp = ini.with_name(f'.{ini.name}.install-tmp')
    temp.write_bytes(result['after'])
    os.replace(temp, ini)
    receipt = {'schema': SCHEMA, 'created_utc': stamp, 'ini': str(ini), 'section': SECTION, 'components': result['components'],
               'lines_added': result['add'], 'lines_already_present': result['present'], 'sources': result['sources'],
               'before_sha256': sha(result['before']), 'after_sha256': sha(result['after']), 'backup': str(backup),
               'backup_sha256': sha(backup.read_bytes()), 'append_only': True, 'readiness_claimed': False,
               'note': 'Config only. Every native readiness gate stays false until live seat/contact/life proofs exist.'}
    path = Path(project) / 'private-audit' / f'default-game-ini-install-{stamp}.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2) + '\n')
    receipt['receipt'] = str(path)
    return receipt


def latest_receipt(project: Path) -> Path:
    found = sorted(f for f in (Path(project) / 'private-audit').glob(RECEIPT_GLOB) if not f.name.endswith('.restored.json'))
    if not found:
        raise Refused('no install receipt to restore from')
    return found[-1]


def restore(project: Path, receipt_path: Path | None = None) -> dict:
    receipt_path = Path(receipt_path) if receipt_path else latest_receipt(project)
    receipt = _load(receipt_path, 'install receipt')
    if receipt.get('schema') != SCHEMA:
        raise Refused(f'{receipt_path} is not an install receipt')
    ini, backup = Path(receipt['ini']), Path(receipt['backup'])
    if ini.resolve() != (Path(project) / INI).resolve():
        raise Refused('receipt names another project config')
    current = ini.read_bytes() if ini.is_file() else b''
    if sha(current) != receipt['after_sha256']:
        raise Refused(f'{ini} was modified since the install (sha256 {sha(current)[:16]} != receipt after {receipt["after_sha256"][:16]}); '
                      'nothing restored')
    if not backup.is_file() or sha(backup.read_bytes()) != receipt['before_sha256']:
        raise Refused(f'backup {backup} is missing or not the recorded pre-install file')
    temp = ini.with_name(f'.{ini.name}.restore-tmp')
    temp.write_bytes(backup.read_bytes())
    os.replace(temp, ini)
    doc = {'schema': RESTORE_SCHEMA, 'install_receipt': str(receipt_path), 'restored_sha256': receipt['before_sha256'],
           'replaced_sha256': receipt['after_sha256'], 'readiness_claimed': False}
    out = receipt_path.with_name(receipt_path.stem + '.restored.json')
    out.write_text(json.dumps(doc, indent=2) + '\n')
    return doc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('project', type=Path, help='UE project directory (contains Config/DefaultGame.ini)')
    parser.add_argument('--only', default=','.join(DEFAULT), help=f'comma list from {",".join(COMPONENTS)}')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--restore', nargs='?', const='', default=None, metavar='RECEIPT')
    args = parser.parse_args(argv)
    try:
        if args.restore is not None:
            doc = restore(args.project, Path(args.restore) if args.restore else None)
            print(f'restored {INI} to sha256 {doc["restored_sha256"]}')
            return 0
        result = plan(args.project, tuple(c.strip() for c in args.only.split(',') if c.strip()))
        print(f'{SECTION} in {result["ini"]}')
        for line in result['present']:
            print(f'  present  {line}')
        for line in result['add']:
            print(f'  add      {line}')
        if not result['add']:
            print('no-op: every line already present; nothing written')
            return 0
        if args.dry_run:
            print('dry run: nothing written')
            return 0
        receipt = apply(result, args.project)
        print(f'written; backup {receipt["backup"]}; receipt {receipt["receipt"]}; readiness_claimed false')
        return 0
    except Refused as error:
        print(f'REFUSED: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
