"""CPU checks for the optional, backward-compatible bath-fixture path of
tools/assemble_home_blender.py (Blender itself only runs on the private server)."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


assemble = load('assemble_home_blender', 'tools/assemble_home_blender.py')
bath = load('bath_fixtures_for_assembly', 'tools/build_home_bath_fixtures.py')


def test_default_arguments_are_unchanged():
    args = assemble.parse_args(['--source', 'a.glb', '--output-dir', 'out/x'])
    assert args.bath_fixtures is None and args.source_sha is None
    assert args.assets_root == ROOT / 'web/house/assets'
    with pytest.raises(SystemExit):
        assemble.parse_args(['--output-dir', 'out/x'])


def test_runtime_to_blender_matches_existing_mattress_convention():
    # The mattress removal bounds use Blender y = -runtime z (bed at runtime z -2.35).
    assert assemble.runtime_to_blender((-2.4, 3.47, -2.35)) == (-2.4, 2.35, 3.47)


def test_placeholder_call_parsing():
    vanity = assemble.placeholder_boxes('box(0.62, 0.66, 0.48, -3.5, 3.36, 1.1, M.wood, 0.02);')
    assert vanity['low'] == pytest.approx((-3.81, 3.03, .86)) and vanity['radius'] == .02
    sharp = assemble.placeholder_boxes('box(1, 1, 1, 0, 0, 0, M.wall, 0);')
    assert sharp['radius'] == 0
    default = assemble.placeholder_boxes('box(1, 1, 1, 0, 0, 0);')
    assert default['radius'] == .012
    basin = assemble.placeholder_boxes('cylinder(0.12, 0.05, -3.5, 3.81, 1.1, M.white);')
    assert basin['low'] == pytest.approx((-3.62, 3.785, .98)) and basin['high'] == pytest.approx((-3.38, 3.835, 1.22))
    tap = assemble.placeholder_boxes('beam([-3.5, 4.01, 0.92], [-3.5, 4.01, 1.04], 0.017, M.brass);')
    assert tap['low'] == pytest.approx((-3.517, 3.993, .903)) and tap['high'] == pytest.approx((-3.483, 4.027, 1.057))
    with pytest.raises(ValueError):
        assemble.placeholder_boxes('plant(-3.4, 3, 4.65, 1.1);')
    for fixture in bath.FIXTURES.values():
        for call in fixture['replaces_home_js']:
            assemble.placeholder_boxes(call)


def test_face_selection_keeps_interior_books_and_architecture():
    box = assemble.blender_box(assemble.placeholder_boxes('box(0.62, 0.66, 0.48, -3.5, 3.36, 1.1, M.wood, 0.02);'))
    # Front face (+X in runtime and Blender) of the placeholder is removed.
    front = [(-3.19, -1.0, 3.2), (-3.19, -1.2, 3.2), (-3.19, -1.1, 3.5)]
    assert assemble.face_on_placeholder_surface(front, (1, 0, 0), box)
    # A rounded-edge face within the 2 cm radius is removed.
    edge = [(-3.195, -1.0, 3.685), (-3.2, -1.2, 3.69), (-3.195, -1.1, 3.685)]
    assert assemble.face_on_placeholder_surface(edge, (.7, 0, .7), box)
    # books(-3.3, 3.035, 1, 5): bottom of a book hidden inside the old vanity stays.
    book_bottom = [(-3.32, -0.93, 3.035), (-3.28, -0.93, 3.035), (-3.30, -1.07, 3.035)]
    assert not assemble.face_on_placeholder_surface(book_bottom, (0, 0, -1), box)
    book_side = [(-3.32, -0.93, 3.04), (-3.32, -1.07, 3.04), (-3.32, -1.0, 3.25)]
    assert not assemble.face_on_placeholder_surface(book_side, (-1, 0, 0), box)
    book_rounded_edge = [(-3.321, -0.93, 3.036), (-3.321, -1.07, 3.036), (-3.32, -1.0, 3.035)]
    assert not assemble.face_on_placeholder_surface(book_rounded_edge, (-.7, 0, -.7), box)
    basin = assemble.blender_box(assemble.placeholder_boxes('cylinder(0.12, 0.05, -3.5, 3.81, 1.1, M.white);'))
    side = [(-3.38, -1.1, 3.79), (-3.38, -1.13, 3.79), (-3.381, -1.115, 3.83)]
    assert assemble.face_on_placeholder_surface(side, (1, -.1, 0), basin)
    # Tile floor/wall triangles extend beyond the box and are never removed.
    tile = [(-3.85, -0.5, 3.0525), (-0.8, -0.5, 3.0525), (-0.8, -2.7, 3.0525)]
    assert not assemble.face_on_placeholder_surface(tile, (0, 0, 1), box)


def write_fixture(directory, name, **override):
    glb = directory / f'{name}.glb'
    glb.write_bytes(b'glTF' + name.encode())
    data = bath.sidecar(name, bath.FIXTURES[name])
    data['sha256'] = hashlib.sha256(glb.read_bytes()).hexdigest()
    data.update(override)
    (directory / f'{name}.json').write_text(json.dumps(data))


def test_bath_fixture_plan_validates_sidecars(tmp_path):
    for name in assemble.BATH_FIXTURE_NAMES:
        write_fixture(tmp_path, name)
    plan = {item['name']: item for item in assemble.bath_fixture_plan(tmp_path)}
    vanity = plan['vanity']
    origin = bath.FIXTURES['vanity']['runtime_origin_m']
    assert vanity['location'] == (origin[0], -origin[2], origin[1])
    assert vanity['yaw'] == pytest.approx(math.pi / 2) and len(vanity['remove']) == 5
    assert plan['toilet']['identifier'] == 'house-original-bath-toilet'
    write_fixture(tmp_path, 'toilet', sha256='0' * 64)
    with pytest.raises(ValueError, match='sha256'):
        assemble.bath_fixture_plan(tmp_path)
    write_fixture(tmp_path, 'toilet', runtime_yaw_radians=float('nan'))
    with pytest.raises(ValueError, match='finite'):
        assemble.bath_fixture_plan(tmp_path)
    write_fixture(tmp_path, 'toilet', replaces_home_js=[])
    with pytest.raises(ValueError, match='placeholder'):
        assemble.bath_fixture_plan(tmp_path)
    (tmp_path / 'toilet.glb').unlink()
    with pytest.raises(FileNotFoundError):
        assemble.bath_fixture_plan(tmp_path)


def test_bath_finishes_cover_roles_and_mirror_runtime_helper():
    roles = {name.split('_')[-1] for name in bath.MESH_ROLES}
    assert roles == set(assemble.BATH_ROLE_FINISH)
    helper = (ROOT / 'web/house/bath_fixture_materials.mjs').read_text()
    tint, roughness, _, coat = assemble.BATH_ROLE_FINISH['ceramic']
    assert f"color: '{tint}', roughness: {str(roughness).lstrip('0')}, clearcoat: {str(coat).lstrip('0')}" in helper
    tint, roughness, _, _ = assemble.BATH_ROLE_FINISH['seat']
    assert f"color: '{tint}', roughness: {str(roughness).lstrip('0')}" in helper
