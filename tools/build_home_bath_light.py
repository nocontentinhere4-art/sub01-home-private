"""Original flush ceiling light for the private SUB-01 loft bathroom.

The server already reports `lights.rooms.bathroom` (home_interactions.py), but
the page has no bathroom fixture or light. This is a small Japanese-style
flush fixture: a thin light-oak ring around a soft opal diffuser, mounted to
the underside of the house roof slab over the bathroom's dry zone. Original
procedural geometry, no manufacturer CAD/photos/textures.

The diffuser mesh is the switched-light role (`BathLight_diffuser`): the page
gives it an emissive material whose `lampEmission` follows the bathroom room
light, and adds one point light at the declared position below it.

    blender -b --python tools/build_home_bath_light.py [-- --output-dir DIR]

Pure data below is CPU-tested against the home.js roof slab, bathroom walls,
shower and door. Front/back is irrelevant (round fixture); Z up in Blender.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_home_bath_fixtures as base  # noqa: E402

ROOT = base.ROOT
OUT = ROOT / 'web/house/assets/bath-light-original'
# House roof slab: box(8, 0.2, 8, 0, 6.05, 0, M.wall, 0) -> underside y = 5.95.
CEILING_Y = 6.05 - 0.2 / 2
# Bathroom interior: walls at z .5/2.7 (0.1 thick), west facade inner face, aisle wall x -0.85.
BATH_INTERIOR = {'x0': base.WEST_WALL_INNER_X, 'x1': -0.85 - 0.1 / 2, 'z0': 0.5 + 0.1 / 2, 'z1': 2.7 - 0.1 / 2}
# Dry-zone centre between vanity (x<-3.38), toilet (z>1.95) and the shower glass at x -1.98.
LIGHT_XZ = (-2.6, 1.55)

RING_R, RING_H = .175, .022
DIFFUSER_R, DIFFUSER_H = .155, .068
PARTS = [
    # Mounting canopy hidden above the ring, against the slab.
    dict(name='Ceiling canopy', mesh='BathLight_oak', shape='cylinder', dims=(.26, .26, .012),
         centre=(0, 0, -.006)),
    dict(name='Oak trim ring', mesh='BathLight_oak', shape='cylinder', dims=(RING_R * 2, RING_R * 2, RING_H),
         centre=(0, 0, -.012 - RING_H / 2)),
    # Opal diffuser: slightly domed soft cylinder (subdivided in Blender).
    dict(name='Opal diffuser', mesh='BathLight_diffuser', shape='rounded',
         dims=(DIFFUSER_R * 2, DIFFUSER_R * 2, DIFFUSER_H), centre=(0, 0, -.012 - RING_H - DIFFUSER_H / 2 + .006),
         radius=.03),
]
FIXTURE_DROP = -min(base.part_bounds(p)[0][2] for p in PARTS)
LIGHT_POSITION = [LIGHT_XZ[0], round(CEILING_Y - FIXTURE_DROP - .03, 4), LIGHT_XZ[1]]
LIGHT = {
    # Matches the house's other room lights (PointLight colour/intensity/decay family).
    'type': 'PointLight', 'position': LIGHT_POSITION, 'color': '#ffe6c2', 'intensity': 5.5,
    'distance': 4.0, 'decay': 2, 'castShadow': False, 'room': 'bathroom',
    'switched_material_role': 'BathLight_diffuser', 'lampEmission': 1.1,
}
FIXTURES = {
    'bath-light': {
        'title': 'Original flush oak-ring ceiling light with opal diffuser',
        'parts': PARTS,
        # Local origin = top centre of the canopy, flush with the slab underside.
        'runtime_origin_m': [LIGHT_XZ[0], CEILING_Y, LIGHT_XZ[1]],
        'runtime_yaw_radians': 0.0,
        'sidecar_extra': {'light': LIGHT, 'switched_role': 'BathLight_diffuser', 'room_light': 'bathroom',
                          'bake_note': 'Add LIGHT to the bake/Unreal light recipe as the bathroom fixture.'},
    },
}
MESH_ROLES = sorted({p['mesh'] for f in FIXTURES.values() for p in f['parts']})


def sidecar(name, fixture, *args, **kwargs):
    return base.sidecar(name, fixture, *args, generator='tools/build_home_bath_light.py', **kwargs)


def placement_problems():
    """Contract: flush to the slab, inside the bathroom away from walls/shower glass, headroom kept."""
    (x0, y0, z0), (x1, y1, z1) = base.runtime_bounds(FIXTURES['bath-light'])
    problems = []
    if abs(y1 - CEILING_Y) > 1e-9:
        problems.append(f'top {y1:.4f} not flush with ceiling {CEILING_Y}')
    if y0 - base.FLOOR_Y < 2.6:
        problems.append(f'headroom {y0 - base.FLOOR_Y:.3f} m below 2.6 m')
    margin = .15
    if x0 < BATH_INTERIOR['x0'] + margin or x1 > -1.98 - margin:
        problems.append(f'x {x0:.3f}..{x1:.3f} too close to west wall or shower glass (x -1.98)')
    if z0 < BATH_INTERIOR['z0'] + margin or z1 > BATH_INTERIOR['z1'] - margin:
        problems.append(f'z {z0:.3f}..{z1:.3f} too close to bathroom walls')
    lx, ly, lz = LIGHT['position']
    if not (x0 <= lx <= x1 and z0 <= lz <= z1 and ly < y0):
        problems.append('light position must sit just below the diffuser')
    return problems


if __name__ == '__main__':
    try:
        import bpy  # noqa: F401
    except ImportError:
        print('bath-light', {'runtime_world_bounds_m': base.runtime_bounds(FIXTURES['bath-light']),
                             'light': LIGHT, 'placement_problems': placement_problems()})
    else:
        assert not placement_problems(), placement_problems()
        base._build_in_blender(base.output_dir_from_argv(sys.argv) if '--output-dir' in sys.argv else OUT,
                               FIXTURES, 'bath-light.blend', 'tools/build_home_bath_light.py')
