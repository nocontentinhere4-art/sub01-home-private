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


def glb_bytes(doc):
    text = json.dumps(doc).encode()
    text += b' ' * (-len(text) % 4)
    body = struct.pack('<II', len(text), 0x4E4F534A) + text
    return struct.pack('<III', 0x46546C67, 2, 12 + len(body)) + body


def fixture_doc(name, shrink=.01, names=None, extra=None):
    """Tiny valid GLB: one node per declared mesh role, POSITION min/max just inside the envelope."""
    lo, hi = build.gltf_envelope(bath.FIXTURES[name]['parts'], 0)
    lo, hi = [v + shrink for v in lo], [v - shrink for v in hi]
    roles = names or sorted({p['mesh'] for p in bath.FIXTURES[name]['parts']})
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
    data = bath.sidecar(name, bath.FIXTURES[name])
    data['sha256'] = hashlib.sha256(glb.read_bytes()).hexdigest()
    data.update(sidecar_override)
    (directory / f'{name}.json').write_text(json.dumps(data))


def dry_run(argv):
    stream = io.StringIO()
    with redirect_stdout(stream):
        assert build.main(argv) == 0
    return stream.getvalue()


def test_dry_run_is_exact_and_deterministic(tmp_path):
    out = tmp_path / 'private'
    source = tmp_path / 'full-home.glb'
    argv = ['--output-dir', str(out), '--blender', '/opt/blender/blender', '--source', str(source),
            '--source-sha', 'abc']
    first, second = dry_run(argv), dry_run(argv)
    assert first == second
    report = json.loads(first)
    fixtures = str(out.resolve() / 'bath-fixtures')
    assert report['mode'] == 'dry-run' and report['output_dir'] == str(out.resolve())
    assert [s['id'] for s in report['steps']] == ['blender-version', 'build-bath-fixtures', 'verify-bath-fixtures',
                                                  'assemble-home', 'write-report']
    assert report['steps'][0]['argv'] == ['/opt/blender/blender', '--version']
    assert report['steps'][1]['argv'] == ['/opt/blender/blender', '--background', '--factory-startup', '--python',
                                          str(ROOT / 'tools/build_home_bath_fixtures.py'), '--', '--output-dir',
                                          fixtures]
    assert report['steps'][3]['argv'] == [
        '/opt/blender/blender', '--background', '--python', str(ROOT / 'tools/assemble_home_blender.py'), '--',
        '--source', str(source.resolve()), '--assets-root', str((ROOT / 'web/house/assets').resolve()),
        '--output-dir', str(out.resolve() / 'assembled'), '--bath-fixtures', fixtures, '--source-sha', 'abc']
    assert report['steps'][4]['path'] == str(out.resolve() / 'furniture-build-report.json')
    assert not out.exists(), 'dry run must not create anything'
    no_source = json.loads(dry_run(['--output-dir', str(out), '--blender', '/opt/blender/blender']))
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
    for name in bath.FIXTURES:
        write_fixture(tmp_path, name)
    assert build.verify_all(tmp_path) == {'toilet': [], 'vanity': []}


@pytest.mark.parametrize('kwargs,message', [
    ({'shrink': -.01}, 'outside declared'),
    ({'names': ['Vanity_oak', 'Vanity_ceramic', 'Mystery']}, 'mesh nodes'),
    ({'extra': {'materials': [{'name': 'baked'}]}}, 'embeds materials'),
    ({'sidecar': {'sha256': '0' * 64}}, 'sha256'),
    ({'sidecar': {'runtime_yaw_radians': 0}}, 'yaw'),
    ({'sidecar': {'runtime_origin_m': [-3.5, 3.0, 1.1]}}, 'runtime_origin_m'),
    ({'sidecar': {'existing_collider': {'x': 0}}}, 'collider'),
])
def test_contract_rejects_violations(tmp_path, kwargs, message):
    write_fixture(tmp_path, 'vanity', **kwargs)
    problems = build.verify_fixture(tmp_path, 'vanity')
    assert any(message in p for p in problems), problems


def test_missing_outputs_reported(tmp_path):
    assert 'missing' in build.verify_fixture(tmp_path, 'toilet')[0]


FAKE_BLENDER = r'''#!{python}
import sys, json, hashlib, importlib.util
from pathlib import Path
if '--version' in sys.argv:
    print('Blender 4.0.2\n\tbuild date: fake'); sys.exit(0)
args = sys.argv[sys.argv.index('--') + 1:]
out = Path(args[args.index('--output-dir') + 1])
spec = importlib.util.spec_from_file_location('t', {test!r})
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
for name in ('vanity', 'toilet'):
    t.write_fixture(out, name)
log = out.parent / 'fake-calls.txt'
log.write_text((log.read_text() if log.exists() else '') + 'build\n')
'''


def test_execute_with_fake_blender_writes_report_and_reuses_verified_build(tmp_path):
    fake = tmp_path / 'bin' / 'blender'
    fake.parent.mkdir()
    fake.write_text(FAKE_BLENDER.format(python=sys.executable, test=str(Path(__file__).resolve())))
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    out = tmp_path / 'private'
    argv = ['--output-dir', str(out), '--blender', str(fake), '--execute']
    with redirect_stdout(io.StringIO()):
        assert build.main(argv) == 0
        report = json.loads((out / 'furniture-build-report.json').read_text())
        assert report['status'] == 'ok' and report['build'] == 'built'
        assert report['blender_version'] == 'Blender 4.0.2' and report['rendered'] is False
        assert report['verification'] == {'toilet': [], 'vanity': []}
        assert set(report['outputs']) == {'toilet.glb', 'toilet.json', 'vanity.glb', 'vanity.json'}
        assert build.main(argv) == 0
        assert json.loads((out / 'furniture-build-report.json').read_text())['build'] == 'reused verified build'
        assert (out / 'fake-calls.txt').read_text() == 'build\n'
        assert build.main(argv + ['--force']) == 0
        assert (out / 'fake-calls.txt').read_text() == 'build\nbuild\n'
