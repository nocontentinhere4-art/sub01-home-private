"""Runpod furniture orchestrator: dry run, repo-path refusal, contract checks and
an end-to-end execute path driven by a fake Blender (no real Blender here)."""
import hashlib
import importlib.util
import io
import json
import stat
import struct
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('runpod_furniture_build', ROOT / 'tools/runpod_furniture_build.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)
bath = build.bath
ALL = ['bath-door', 'bath-light', 'toilet', 'vanity']
GROUP_OF = {name: build.SPECS[name][0] for name in ALL}


def module_of(name):
    return build.SPECS[name][2]


def glb_bytes(doc):
    text = json.dumps(doc).encode()
    text += b' ' * (-len(text) % 4)
    body = struct.pack('<II', len(text), 0x4E4F534A) + text
    return struct.pack('<III', 0x46546C67, 2, 12 + len(body)) + body


def fixture_doc(name, shrink=.001, names=None, extra=None):
    """Tiny valid GLB: one node per declared mesh role, POSITION min/max just inside the envelope."""
    parts = module_of(name).FIXTURES[name]['parts']
    lo, hi = build.gltf_envelope(parts, 0)
    lo, hi = [v + shrink for v in lo], [v - shrink for v in hi]
    roles = names or sorted({p['mesh'] for p in parts})
    doc = {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': list(range(len(roles)))}],
           'nodes': [{'name': role, 'mesh': i} for i, role in enumerate(roles)],
           'meshes': [{'primitives': [{'attributes': {'POSITION': 0}}]} for _ in roles],
           'accessors': [{'count': 3, 'type': 'VEC3', 'componentType': 5126, 'min': lo, 'max': hi}]}
    doc.update(extra or {})
    return doc


def write_fixture(directory, name, **kwargs):
    directory.mkdir(parents=True, exist_ok=True)
    sidecar_override = kwargs.pop('sidecar', {})
    glb = directory / f'{name}.glb'
    glb.write_bytes(glb_bytes(fixture_doc(name, **kwargs)))
    module = module_of(name)
    data = json.loads(json.dumps(module.sidecar(name, module.FIXTURES[name])))
    data['sha256'] = hashlib.sha256(glb.read_bytes()).hexdigest()
    data.update(sidecar_override)
    (directory / f'{name}.json').write_text(json.dumps(data))


def write_all(out):
    for name in ALL:
        write_fixture(Path(out) / GROUP_OF[name], name)


def dry_run(argv):
    stream = io.StringIO()
    with redirect_stdout(stream):
        assert build.main(argv) == 0
    return stream.getvalue()


def test_dry_run_is_exact_and_deterministic(tmp_path):
    out = tmp_path / 'private'
    source = tmp_path / 'full-home.glb'
    blender = '/opt/blender/blender'
    argv = ['--output-dir', str(out), '--blender', blender, '--source', str(source), '--source-sha', 'abc']
    first, second = dry_run(argv), dry_run(argv)
    assert first == second
    report = json.loads(first)
    root = out.resolve()
    assert report['mode'] == 'dry-run' and report['output_dir'] == str(root)
    assert [s['id'] for s in report['steps']] == [
        'blender-version', 'build-bath-fixtures', 'build-bath-light', 'build-bath-door', 'verify-all',
        'assemble-home', 'write-report']
    assert report['steps'][0]['argv'] == [blender, '--version']
    for step, script in zip(report['steps'][1:4], ['build_home_bath_fixtures.py', 'build_home_bath_light.py',
                                                   'build_home_bath_door.py']):
        assert step['argv'] == [blender, '--background', '--factory-startup', '--python',
                                str(ROOT / 'tools' / script), '--', '--output-dir', str(root / step['group'])]
    checks = report['steps'][4]['checks']
    assert [c.split(':')[0] for c in checks] == ALL
    assert 'sidecar bake_note/light/room_light/switched_role' in checks[1]
    assert 'runtime_parent' in checks[0]
    assert report['steps'][5]['argv'] == [
        blender, '--background', '--python', str(ROOT / 'tools/assemble_home_blender.py'), '--',
        '--source', str(source.resolve()), '--assets-root', str((ROOT / 'web/house/assets').resolve()),
        '--output-dir', str(root / 'assembled'), '--bath-fixtures', str(root / 'bath-fixtures'),
        '--source-sha', 'abc']
    assert report['steps'][6]['path'] == str(root / 'furniture-build-report.json')
    assert not out.exists(), 'dry run must not create anything'
    no_source = json.loads(dry_run(['--output-dir', str(out), '--blender', blender]))
    assert 'assemble-home' not in [s['id'] for s in no_source['steps']]


@pytest.mark.parametrize('inside', ['web/house/assets/bath-fixtures-original', 'out/furniture', '.'])
def test_refuses_output_inside_repository(inside, capsys):
    with pytest.raises(SystemExit) as error:
        build.parse_args(['--output-dir', str(ROOT / inside)])
    assert error.value.code == 2 and 'inside the Git checkout' in capsys.readouterr().err


def test_source_sha_requires_source(tmp_path):
    with pytest.raises(SystemExit):
        build.parse_args(['--output-dir', str(tmp_path), '--source-sha', 'abc'])


def test_contract_accepts_valid_synthetic_fixtures(tmp_path):
    write_all(tmp_path)
    assert build.verify_all(tmp_path) == {name: [] for name in ALL}


@pytest.mark.parametrize('name,kwargs,message', [
    ('vanity', {'shrink': -.01}, 'outside declared'),
    ('vanity', {'names': ['Vanity_oak', 'Vanity_ceramic', 'Mystery']}, 'mesh nodes'),
    ('vanity', {'extra': {'materials': [{'name': 'baked'}]}}, 'embeds materials'),
    ('vanity', {'sidecar': {'sha256': '0' * 64}}, 'sha256'),
    ('vanity', {'sidecar': {'runtime_yaw_radians': 0}}, 'yaw'),
    ('vanity', {'sidecar': {'runtime_origin_m': [-3.5, 3.0, 1.1]}}, 'runtime_origin_m'),
    ('vanity', {'sidecar': {'existing_collider': {'x': 0}}}, 'collider'),
    ('vanity', {'sidecar': {'generator': 'tools/build_home_bath_door.py'}}, 'generator'),
    ('bath-light', {'sidecar': {'light': {'position': [0, 0, 0]}}}, 'sidecar light'),
    ('bath-door', {'sidecar': {'runtime_parent': 'frontDoor'}}, 'sidecar runtime_parent'),
    ('bath-door', {'shrink': -.005}, 'outside declared'),
])
def test_contract_rejects_violations(tmp_path, name, kwargs, message):
    write_fixture(tmp_path, name, **kwargs)
    problems = build.verify_fixture(tmp_path, name)
    assert any(message in p for p in problems), problems


def test_missing_outputs_reported(tmp_path):
    assert 'missing' in build.verify_fixture(tmp_path, 'toilet')[0]


FAKE_BLENDER = r'''#!{python}
import sys, importlib.util
from pathlib import Path
if '--version' in sys.argv:
    print('Blender 4.0.2\n\tbuild date: fake'); sys.exit(0)
script = Path(sys.argv[sys.argv.index('--python') + 1]).name
args = sys.argv[sys.argv.index('--') + 1:]
out = Path(args[args.index('--output-dir') + 1])
spec = importlib.util.spec_from_file_location('t', {test!r})
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
import os
for name in t.ALL:
    if t.build.SPECS[name][1].name == script:
        broken = os.environ.get('FAKE_BROKEN_FIXTURE') == name
        t.write_fixture(out, name, **({{'sidecar': {{'sha256': '0' * 64}}}} if broken else {{}}))
log = out.parent / 'fake-calls.txt'
log.write_text((log.read_text() if log.exists() else '') + script + '\n')
'''


def test_execute_with_fake_blender_writes_report_and_reuses_verified_build(tmp_path, monkeypatch):
    fake = tmp_path / 'bin' / 'blender'
    fake.parent.mkdir()
    fake.write_text(FAKE_BLENDER.format(python=sys.executable, test=str(Path(__file__).resolve())))
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    out = tmp_path / 'private'
    argv = ['--output-dir', str(out), '--blender', str(fake), '--execute']
    scripts = 'build_home_bath_fixtures.py\nbuild_home_bath_light.py\nbuild_home_bath_door.py\n'
    with redirect_stdout(io.StringIO()):
        assert build.main(argv) == 0
        report = json.loads((out / 'furniture-build-report.json').read_text())
        assert report['status'] == 'ok' and report['blender_version'] == 'Blender 4.0.2'
        assert report['rendered'] is False and set(report['groups']) == {'bath-fixtures', 'bath-light', 'bath-door'}
        assert all(g['build'] == 'built' for g in report['groups'].values())
        assert report['groups']['bath-light']['verification'] == {'bath-light': []}
        assert set(report['groups']['bath-fixtures']['outputs']) == {'toilet.glb', 'toilet.json', 'vanity.glb',
                                                                     'vanity.json'}
        assert (out / 'fake-calls.txt').read_text() == scripts
        assert build.main(argv) == 0
        again = json.loads((out / 'furniture-build-report.json').read_text())
        assert all(g['build'] == 'reused verified build' for g in again['groups'].values())
        assert (out / 'fake-calls.txt').read_text() == scripts
        assert build.main(argv + ['--force']) == 0
        assert (out / 'fake-calls.txt').read_text() == scripts * 2
        # A corrupted output is not reused: that group alone is rebuilt.
        (out / 'bath-door' / 'bath-door.json').write_text('{}')
        assert build.main(argv) == 0
        assert (out / 'fake-calls.txt').read_text() == scripts * 2 + 'build_home_bath_door.py\n'
        # A build that violates the contract fails the run and blocks assembly.
        monkeypatch.setenv('FAKE_BROKEN_FIXTURE', 'bath-door')
        source = tmp_path / 'full-home.glb'
        source.write_bytes(b'glTF')
        assert build.main(argv + ['--force', '--source', str(source)]) == 1
        failed = json.loads((out / 'furniture-build-report.json').read_text())
        assert failed['status'] == 'contract-failed' and 'assembly' not in failed
        assert any('sha256' in p for p in failed['groups']['bath-door']['verification']['bath-door'])
        assert failed['groups']['bath-door']['build'] == 'built'
