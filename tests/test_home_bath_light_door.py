"""CPU contracts for the loft bathroom ceiling light and oak door leaf generators,
checked against the unchanged home.js / bathroom_access.mjs literals."""
import importlib.util
import math
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


light = load('build_home_bath_light')
door = load('build_home_bath_door')
bath = load('build_home_bath_fixtures')
HOME_JS = (ROOT / 'web/house/home.js').read_text()
ACCESS_JS = (ROOT / 'web/house/bathroom_access.mjs').read_text()
MATERIALS_JS = (ROOT / 'web/house/bath_fixture_materials.mjs').read_text()


def access(name):
    return float(re.search(rf'\b{name}:\s*(-?[\d.]+)', ACCESS_JS).group(1))


# ---------------------------------------------------------------- light

def test_light_mounts_flush_under_existing_roof_slab():
    assert 'box(8, 0.2, 8, 0, 6.05, 0, M.wall, 0);' in HOME_JS
    assert light.CEILING_Y == pytest.approx(5.95)
    assert light.placement_problems() == []
    (x0, y0, z0), (x1, y1, z1) = bath.runtime_bounds(light.FIXTURES['bath-light'])
    assert y1 == pytest.approx(5.95) and .08 <= y1 - y0 <= .12
    assert 'const bathroomBounds = { x0: -3.78, x1: -0.85, z0: 0.5, z1: 2.7 };' in HOME_JS
    assert -3.78 < x0 and x1 < -1.98 and .55 < z0 and z1 < 2.65


def test_light_clears_vanity_toilet_and_door_volumes():
    (lx0, ly0, lz0), _ = bath.runtime_bounds(light.FIXTURES['bath-light'])
    for name in ('vanity', 'toilet'):
        _, (_, top, _) = bath.runtime_bounds(bath.FIXTURES[name])
        assert top < ly0 - 1.5
    assert door.leaf_runtime_bounds()[1][1] < ly0


def test_light_declaration_and_switched_role():
    spec = light.LIGHT
    assert spec['room'] == 'bathroom'
    assert re.search(r'LIGHT_ROOMS = \(.*"bathroom".*\)', (ROOT / 'home_interactions.py').read_text())
    assert spec['type'] == 'PointLight' and spec['decay'] == 2 and 0 < spec['intensity'] <= 10
    assert spec['position'][1] < bath.runtime_bounds(light.FIXTURES['bath-light'])[0][1]
    assert spec['switched_material_role'] in light.MESH_ROLES == ['BathLight_diffuser', 'BathLight_oak']
    emission = float(re.search(r'BATH_LIGHT_DIFFUSER = .*lampEmission: ([\d.]+)', MATERIALS_JS).group(1))
    assert emission == spec['lampEmission']
    data = light.sidecar('bath-light', light.FIXTURES['bath-light'])
    assert data['light'] == spec and data['generator'] == 'tools/build_home_bath_light.py'
    assert data['existing_collider'] is None


# ---------------------------------------------------------------- door

def test_door_reads_existing_slab_and_access_literals():
    assert door.SLAB_CALL in HOME_JS
    args = [float(v) for v in re.match(r'const bathDoor = box\(([^)]*), M\.darkwood', door.SLAB_CALL).group(1).split(',')]
    assert args == [door.THICKNESS, door.HEIGHT, door.WIDTH, *door.SLAB_CENTRE]
    assert access('leafWidth') == door.WIDTH and access('thickness') == door.THICKNESS
    assert access('plane') == door.SLAB_CENTRE[0] and access('closed') == door.SLAB_CENTRE[2]
    assert 'Math.abs(bathDoor.position.z - (doorOpen ? 2.3 : 1.35)) > .001' in HOME_JS
    assert access('open') == 2.3


def test_door_envelope_equals_slab_so_collision_and_animation_are_unchanged():
    assert door.envelope_problems() == []
    lo, hi = bath.runtime_bounds(door.FIXTURES['bath-door'])
    assert [hi[i] - lo[i] for i in range(3)] == pytest.approx([door.THICKNESS, door.HEIGHT, door.WIDTH])
    for z in (access('closed'), access('open')):
        (x0, y0, z0), (x1, y1, z1) = door.leaf_runtime_bounds((door.SLAB_CENTRE[0], door.SLAB_CENTRE[1], z))
        assert (x0, x1) == pytest.approx((-.8825, -.8175)) and (y0, y1) == pytest.approx((3.05, 5.05))
        assert (z0, z1) == pytest.approx((z - .445, z + .445))
    # The pocket wall the leaf slides into is 0.1 m thick on the same plane.
    assert 'box(0.1, 2.85, d, -0.85, 4.46, z, M.wall, 0);' in HOME_JS and '[2.25, 0.9],' in HOME_JS
    (x0, _, _), (x1, _, _) = door.leaf_runtime_bounds()
    assert -0.9 < x0 and x1 < -0.8


def test_door_faces_slats_and_recessed_pulls():
    parts = door.PARTS
    slats = [p for p in parts if p['name'] == 'Vertical slat']
    assert len(slats) == 2 * door.SLATS and door.SLAT_W > .05
    pulls = [p for p in parts if p['name'] == 'Hikite pull']
    assert len(pulls) == 2 and {math.copysign(1, p['centre'][1]) for p in pulls} == {-1.0, 1.0}
    for pull in pulls:
        outer = abs(pull['centre'][1]) + pull['dims'][1] / 2
        assert outer <= door.THICKNESS / 2 - .001, 'recessed below the slat face'
        cut = [s for s in slats if s.get('cuts') and math.copysign(1, s['centre'][1]) == math.copysign(1, pull['centre'][1])]
        assert cut, 'a slat is bored for the recessed pull'
    # Leading (closing, -z) edge: Blender -X maps to runtime -z with yaw -pi/2.
    rt = bath.blender_to_runtime(pulls[0]['centre'], [0, 0, 0], door.FIXTURES['bath-door']['runtime_yaw_radians'])
    assert rt[2] < 0 and rt[1] == pytest.approx(door.HANDLE_HEIGHT_ABOVE_FLOOR - door.HEIGHT / 2)
    assert door.MESH_ROLES == ['Door_brass', 'Door_oak']
    data = door.sidecar('bath-door', door.FIXTURES['bath-door'])
    assert data['runtime_parent'] == 'bathDoor' and data['replaces_home_js'] == [door.SLAB_CALL]


# ---------------------------------------------------------------- shared

def test_runtime_helper_covers_every_generator_role():
    roles = dict(re.findall(r"(\w+): '(\w+)'", MATERIALS_JS.split('});')[0]))
    assert sorted(roles) == sorted(set(bath.MESH_ROLES) | set(light.MESH_ROLES) | set(door.MESH_ROLES))
    assert roles['BathLight_diffuser'] == 'diffuser' and roles['Door_oak'] == 'oak'


@pytest.mark.parametrize('module,key', [('build_home_bath_light.py', 'placement_problems'),
                                        ('build_home_bath_door.py', 'envelope_problems')])
def test_generators_outside_blender_only_print_contract(module, key):
    result = subprocess.run([sys.executable, str(ROOT / 'tools' / module)], capture_output=True, text=True, check=True)
    assert f"'{key}': []" in result.stdout
