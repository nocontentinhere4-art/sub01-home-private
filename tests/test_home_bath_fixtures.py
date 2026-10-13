"""CPU contract for tools/build_home_bath_fixtures.py (no Blender required).

The declared part envelopes must replace the exact placeholder boxes still in
home.js while fitting the unchanged bathroom colliders, floor and walls.
"""
import importlib.util
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bath_fixtures', ROOT / 'tools/build_home_bath_fixtures.py')
bath = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bath)
HOME_JS = (ROOT / 'web/house/home.js').read_text()
MATERIALS_JS = (ROOT / 'web/house/bath_fixture_materials.mjs').read_text()


def obstacle(call):
    m = re.match(r'obstacle\(([-\d.]+), ([-\d.]+), ([-\d.]+), ([-\d.]+), (\d+)\);', call)
    x, z, w, d = (float(v) for v in m.groups()[:4])
    return {'x': x, 'z': z, 'width': w, 'depth': d, 'level': int(m.group(5))}


@pytest.mark.parametrize('name', sorted(bath.FIXTURES))
def test_replaced_placeholders_and_colliders_are_current(name):
    fixture = bath.FIXTURES[name]
    for line in fixture['replaces_home_js'] + fixture['keeps_home_js']:
        assert line in HOME_JS, f'home.js changed; re-derive {name} from: {line}'
    assert obstacle(fixture['keeps_home_js'][0]) == fixture['collider']


def test_floor_and_wall_constants_come_from_home_js():
    assert 'box(3.05, 0.035, 2.2, -2.325, 3.035, 1.6, tiles, 0);' in HOME_JS
    assert bath.FLOOR_Y == pytest.approx(3.0525)
    assert 'box(0.18, 0.7, 8, -4, 0.35, 0, M.wall, 0);' in HOME_JS
    assert bath.WEST_WALL_INNER_X == pytest.approx(-3.91)
    assert 'for (const z of [0.5, 2.7]) {' in HOME_JS and 'box(3.1, 2.85, 0.1, -2.325, 4.46, z, M.wall, 0);' in HOME_JS
    assert bath.NORTH_BATH_WALL_INNER_Z == pytest.approx(2.65)


@pytest.mark.parametrize('name', sorted(bath.FIXTURES))
def test_declared_bounds_fit_collider_floor_and_walls(name):
    fixture = bath.FIXTURES[name]
    assert bath.footprint_violations(fixture) == []
    (x0, y0, z0), (x1, y1, z1) = bath.runtime_bounds(fixture)
    assert y0 >= bath.FLOOR_Y - 1e-9 and y1 < bath.FLOOR_Y + 1.1
    assert x0 >= bath.WEST_WALL_INNER_X - 1e-9
    assert .55 - 1e-9 <= z0 and z1 <= bath.NORTH_BATH_WALL_INNER_Z + 1e-9  # between bathroom walls
    for part in fixture['parts']:
        assert all(v > 0 for v in part['dims']), part['name']
        assert part['mesh'].split('_')[0].lower() == name


def test_believable_scale():
    vanity = {p['name']: p for p in bath.VANITY_PARTS}
    counter = bath.part_bounds(vanity['Solid oak counter'])[1][2]
    rim = bath.part_bounds(vanity['Vessel basin'])[1][2]
    assert .70 <= counter <= .76 and .82 <= rim <= .88
    assert bath.part_bounds(vanity['Carcass'])[0][2] >= .25, 'wall-hung shadow gap above tiles'
    toilet = {p['name']: p for p in bath.TOILET_PARTS}
    seat_top = bath.part_bounds(toilet['Seat ring'])[1][2]
    assert .40 <= seat_top <= .45
    bowl = toilet['Ceramic bowl']
    well_bottom = bath.part_bounds(bowl)[1][2] - bowl['opening'][2]
    assert bath.part_bounds(toilet['Ceramic foot'])[1][2] < well_bottom, 'foot must not show inside the bowl'
    lo, hi = bath.local_bounds(bath.TOILET_PARTS)
    assert .36 <= hi[0] - lo[0] <= .45 and .60 <= hi[1] - lo[1] <= .72 and .75 <= hi[2] <= .82


def test_fixtures_do_not_overlap_each_other_or_shower():
    (vx0, _, vz0), (vx1, _, vz1) = bath.runtime_bounds(bath.FIXTURES['vanity'])
    (tx0, _, tz0), (tx1, _, tz1) = bath.runtime_bounds(bath.FIXTURES['toilet'])
    assert vx1 < tx0 or tx1 < vx0 or vz1 < tz0 or tz1 < vz0
    assert 'box(0.9, 0.1, 1, -1.5, 3.08, 2.15, tiles, 0.015);' in HOME_JS  # shower tray x -1.95..-1.05
    assert tx1 < -1.98 - .1 and vx1 < -1.98 - .1


def test_vanity_clears_existing_bathroom_books():
    # books(-3.3, 3.035, 1, 5) currently sits partly inside the placeholder box;
    # widest book is .055 m, so the row starts at x >= -3.3275.
    assert 'books(-3.3, 3.035, 1, 5);' in HOME_JS
    (_, _, _), (vx1, _, _) = bath.runtime_bounds(bath.FIXTURES['vanity'])
    assert vx1 < -3.3 - .055 / 2


def test_runtime_convention_matches_js_check():
    vanity = bath.FIXTURES['vanity']
    back = bath.blender_to_runtime((0, bath.VANITY_D / 2, 0), vanity['runtime_origin_m'], vanity['runtime_yaw_radians'])
    assert back == pytest.approx([-3.905, 3.0525, 1.1])
    toilet = bath.FIXTURES['toilet']
    cistern = bath.blender_to_runtime((0, .355, 0), toilet['runtime_origin_m'], toilet['runtime_yaw_radians'])
    assert cistern[2] == pytest.approx(2.585) and math.isclose(cistern[0], -2.9, abs_tol=1e-12)


def test_mesh_roles_match_runtime_material_helper():
    roles = dict(re.findall(r"(\w+): '(\w+)'", MATERIALS_JS.split('});')[0]))
    assert sorted(roles) == bath.MESH_ROLES
    for name, fixture in bath.FIXTURES.items():
        data = bath.sidecar(name, fixture)
        assert data['mesh_roles'] == sorted({p['mesh'] for p in fixture['parts']})
        assert data['generator'] == 'tools/build_home_bath_fixtures.py' and data['embedded_textures'] is False
        json.dumps(data)


def test_outside_blender_prints_contract_without_writing_assets():
    before = bath.OUT.exists() and sorted(p.name for p in bath.OUT.iterdir())
    result = subprocess.run([sys.executable, str(ROOT / 'tools/build_home_bath_fixtures.py')],
                            capture_output=True, text=True, check=True)
    assert '"footprint_violations": []' in result.stdout
    after = bath.OUT.exists() and sorted(p.name for p in bath.OUT.iterdir())
    assert before == after


@pytest.mark.parametrize('name', sorted(bath.FIXTURES))
def test_built_assets_if_present_match_contract(name):
    glb, side = bath.OUT / f'{name}.glb', bath.OUT / f'{name}.json'
    if not glb.exists():
        pytest.skip('GLB is built later in Blender on the private server')
    import hashlib
    data = json.loads(side.read_text())
    assert data['sha256'] == hashlib.sha256(glb.read_bytes()).hexdigest()
    lo, hi = data['blender_bounds_m']
    dlo, dhi = bath.local_bounds(bath.FIXTURES[name]['parts'])
    for i in range(3):
        assert lo[i] >= dlo[i] - bath.BOUNDS_TOLERANCE_M and hi[i] <= dhi[i] + bath.BOUNDS_TOLERANCE_M
