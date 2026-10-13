#!/usr/bin/env python3
"""Private Runpod furniture build: bath fixtures, contract check, optional assembly.

Meant to be run by the owner's agent ON the already-authorized private Runpod
server. Dry run is the default: it prints the exact commands and checks it
would run, and executes nothing. `--execute` runs Blender in background mode
only. No rendering, no network, no pod management, no deployment.

    python tools/runpod_furniture_build.py --output-dir /workspace/private/furniture
    python tools/runpod_furniture_build.py --output-dir /workspace/private/furniture --execute \
        [--source /workspace/.../full-home.glb [--source-sha SHA]] [--blender /opt/blender/blender]

Outputs (never inside this Git checkout):
    DIR/bath-fixtures/{vanity,toilet}.glb + .json + bath-fixtures.blend
    DIR/assembled/{house.blend,house.glb,assembly.json}   (only with --source)
    DIR/furniture-build-report.json
Idempotent: an existing build whose generator hash, Blender version and
contract still match is reused unless --force is given.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import build_home_bath_fixtures as bath  # noqa: E402  (pure data; no bpy at import)
from home_asset_audit import read_gltf, world_bounds  # noqa: E402

GENERATOR = TOOLS / 'build_home_bath_fixtures.py'
ASSEMBLER = TOOLS / 'assemble_home_blender.py'
REPORT_NAME = 'furniture-build-report.json'
STATE_NAME = 'build-state.json'
MAX_BLENDER_SECONDS = 1800


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def inside(path: Path, parent: Path) -> bool:
    try:
        Path(path).resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--output-dir', type=Path, required=True, help='private directory outside Git')
    parser.add_argument('--blender', default='blender', help='Blender executable (name or path)')
    parser.add_argument('--source', type=Path, help='V4 full-home GLB; enables the assembly step')
    parser.add_argument('--source-sha')
    parser.add_argument('--assets-root', type=Path, default=ROOT / 'web/house/assets')
    parser.add_argument('--execute', action='store_true', help='actually run Blender (default: dry run)')
    parser.add_argument('--force', action='store_true', help='rebuild even if a verified build exists')
    args = parser.parse_args(argv)
    if inside(args.output_dir, ROOT):
        parser.error(f'--output-dir {args.output_dir} is inside the Git checkout {ROOT}; use a private path outside it')
    if args.source_sha and not args.source:
        parser.error('--source-sha requires --source')
    return args


def plan(args):
    """Deterministic list of steps (commands are argv lists, never shell strings)."""
    out = args.output_dir.resolve()
    fixtures = out / 'bath-fixtures'
    steps = [
        {'id': 'blender-version', 'argv': [args.blender, '--version']},
        {'id': 'build-bath-fixtures',
         'argv': [args.blender, '--background', '--factory-startup', '--python', str(GENERATOR),
                  '--', '--output-dir', str(fixtures)],
         'skip_if_verified': True},
        {'id': 'verify-bath-fixtures', 'internal': True, 'checks': [
            f'{name}: sidecar sha256, mesh names {sorted({p["mesh"] for p in spec["parts"]})}, '
            f'GLB bounds inside declared envelope +{bath.BOUNDS_TOLERANCE_M} m, sidecar origin/yaw/collider '
            f'match generator, runtime footprint inside collider, no embedded materials/images'
            for name, spec in sorted(bath.FIXTURES.items())]},
    ]
    if args.source:
        assemble = [args.blender, '--background', '--python', str(ASSEMBLER), '--',
                    '--source', str(args.source.resolve()), '--assets-root', str(args.assets_root.resolve()),
                    '--output-dir', str(out / 'assembled'), '--bath-fixtures', str(fixtures)]
        if args.source_sha:
            assemble += ['--source-sha', args.source_sha]
        steps.append({'id': 'assemble-home', 'argv': assemble})
    steps.append({'id': 'write-report', 'internal': True, 'path': str(out / REPORT_NAME)})
    return steps


# ------------------------------------------------------------------ contract

def gltf_envelope(parts, tol):
    """Declared Blender-local envelope expressed in glTF axes (x, z-up -> y, -y -> z)."""
    lo, hi = bath.local_bounds(parts)
    return ([lo[0] - tol, lo[2] - tol, -hi[1] - tol], [hi[0] + tol, hi[2] + tol, -lo[1] + tol])


def verify_fixture(directory: Path, name: str):
    """Return a list of contract violations for one built fixture (empty = ok)."""
    spec = bath.FIXTURES[name]
    glb, side = Path(directory) / f'{name}.glb', Path(directory) / f'{name}.json'
    if not glb.is_file() or not side.is_file():
        return [f'{name}: missing {glb.name} or {side.name}']
    problems = []
    data = json.loads(side.read_text())
    if data.get('sha256') != sha256(glb):
        problems.append(f'{name}: GLB sha256 differs from sidecar')
    doc, _ = read_gltf(glb)
    expected = sorted({p['mesh'] for p in spec['parts']})
    names = sorted(n.get('name', '') for n in doc.get('nodes', []) if 'mesh' in n)
    if names != expected:
        problems.append(f'{name}: mesh nodes {names} != {expected}')
    if data.get('mesh_roles') != expected:
        problems.append(f'{name}: sidecar mesh_roles {data.get("mesh_roles")} != {expected}')
    if doc.get('materials') or doc.get('images') or doc.get('textures'):
        problems.append(f'{name}: GLB embeds materials/images; runtime expects geometry only')
    bounds = world_bounds(doc)
    if not bounds:
        problems.append(f'{name}: GLB has no bounded geometry')
    else:
        lo, hi = gltf_envelope(spec['parts'], bath.BOUNDS_TOLERANCE_M)
        for axis in range(3):
            if bounds[0][axis] < lo[axis] or bounds[1][axis] > hi[axis]:
                problems.append(f'{name}: glTF axis {axis} bounds {bounds[0][axis]:.4f}..{bounds[1][axis]:.4f} '
                                f'outside declared {lo[axis]:.4f}..{hi[axis]:.4f}')
    origin, yaw = data.get('runtime_origin_m'), data.get('runtime_yaw_radians')
    if not (isinstance(origin, list) and len(origin) == 3
            and all(math.isclose(a, b, abs_tol=1e-9) for a, b in zip(origin, spec['runtime_origin_m']))):
        problems.append(f'{name}: sidecar runtime_origin_m {origin} != generator {spec["runtime_origin_m"]}')
    if not (isinstance(yaw, (int, float)) and math.isclose(yaw, spec['runtime_yaw_radians'], abs_tol=1e-9)):
        problems.append(f'{name}: sidecar yaw {yaw} != generator {spec["runtime_yaw_radians"]}')
    if data.get('existing_collider') != spec['collider']:
        problems.append(f'{name}: sidecar collider differs from generator')
    problems += [f'{name}: {v}' for v in bath.footprint_violations(spec)]
    return problems


def verify_all(directory: Path):
    return {name: verify_fixture(directory, name) for name in sorted(bath.FIXTURES)}

# ------------------------------------------------------------------ execution

def run(argv, log):
    log.append({'argv': argv})
    result = subprocess.run(argv, capture_output=True, text=True, timeout=MAX_BLENDER_SECONDS, check=False)
    log[-1].update(returncode=result.returncode, stdout_tail=result.stdout[-4000:], stderr_tail=result.stderr[-4000:])
    if result.returncode:
        raise RuntimeError(f'{argv[0]} exited {result.returncode}; see report')
    return result.stdout


def blender_version(stdout: str) -> str:
    first = next((line.strip() for line in stdout.splitlines() if line.strip().startswith('Blender')), '')
    if not first:
        raise RuntimeError('Could not read Blender version')
    return first


def execute(args, steps):
    out = args.output_dir.resolve()
    fixtures = out / 'bath-fixtures'
    report = {'schema': 'sub01-runpod-furniture-build/1', 'private_only': True, 'rendered': False,
              'generator_sha256': sha256(GENERATOR), 'commands': []}
    exe = shutil.which(args.blender)
    if not exe:
        raise SystemExit(f'Blender executable not found: {args.blender}')
    report['blender_path'] = exe
    report['blender_version'] = blender_version(run(steps[0]['argv'], report['commands']))
    print('Blender:', report['blender_version'], flush=True)
    state_path = fixtures / STATE_NAME
    state = json.loads(state_path.read_text()) if state_path.is_file() else {}
    reusable = (not args.force and state.get('generator_sha256') == report['generator_sha256']
                and state.get('blender_version') == report['blender_version']
                and not any(verify_all(fixtures).values()))
    if reusable:
        report['build'] = 'reused verified build'
    else:
        out.mkdir(parents=True, exist_ok=True)
        run(steps[1]['argv'], report['commands'])
        report['build'] = 'built'
    verification = verify_all(fixtures)
    report['verification'] = verification
    report['outputs'] = {p.name: sha256(p) for p in sorted(fixtures.glob('*')) if p.is_file() and p.name != STATE_NAME}
    if any(verification.values()):
        report['status'] = 'contract-failed'
    else:
        state_path.write_text(json.dumps({'generator_sha256': report['generator_sha256'],
                                          'blender_version': report['blender_version']}, indent=2) + '\n')
        assemble = next((s for s in steps if s['id'] == 'assemble-home'), None)
        if assemble:
            run(assemble['argv'], report['commands'])
            assembly = out / 'assembled' / 'assembly.json'
            report['assembly'] = json.loads(assembly.read_text()) if assembly.is_file() else None
        report['status'] = 'ok'
    (out / REPORT_NAME).write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': report['status'], 'report': str(out / REPORT_NAME)}), flush=True)
    return 0 if report['status'] == 'ok' else 1


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    steps = plan(args)
    if not args.execute:
        print(json.dumps({'mode': 'dry-run', 'output_dir': str(args.output_dir.resolve()), 'steps': steps},
                         indent=2, sort_keys=True))
        return 0
    return execute(args, steps)


if __name__ == '__main__':
    sys.exit(main())
