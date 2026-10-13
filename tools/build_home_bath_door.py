"""Original light-oak sliding leaf for the private SUB-01 loft bathroom.

Replaces only the look of the darkwood slab `bathDoor` in home.js
(box(0.065, 2, 0.89, -0.85, 4.05, 1.35, M.darkwood, 0.012)). The leaf keeps
the exact slab envelope so collision (bathroom_access.mjs bathroomAllows),
the sliding animation (closed z 1.35 -> open z 2.3 along the x -0.85 wall
plane) and the pocket wall it slides into are unchanged. Every part stays
inside the 65 mm leaf thickness: nothing can poke through the pocket wall.

Design: Japanese-modern flush oak leaf, vertical slat faces between top and
bottom rails, recessed round brass hikite pulls on both faces near the leading
(-z) edge and a flush brass edge pull. Original geometry, no CAD/photos.

    blender -b --python tools/build_home_bath_door.py [-- --output-dir DIR]

Runtime: add the GLB root as a child of the existing bathDoor mesh at local
origin with yaw -pi/2 (Blender X width -> runtime Z, Blender Y thickness ->
runtime X) and hide the slab material; bathDoor keeps moving as before.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_home_bath_fixtures as base  # noqa: E402

ROOT = base.ROOT
OUT = ROOT / 'web/house/assets/bath-door-original'
SLAB_CALL = 'const bathDoor = box(0.065, 2, 0.89, -0.85, 4.05, 1.35, M.darkwood, 0.012);'
THICKNESS, HEIGHT, WIDTH = .065, 2.0, .89          # runtime x, y, z of the slab
SLAB_CENTRE = (-0.85, 4.05, 1.35)
HANDLE_HEIGHT_ABOVE_FLOOR = .95
FACE = .010           # slat/rail layer on each face
CORE = THICKNESS - 2 * FACE
TOP_RAIL, BOTTOM_RAIL, SLATS, SLAT_GAP = .12, .18, 13, .006
SLAT_W = (WIDTH - (SLATS - 1) * SLAT_GAP) / SLATS
SLAT_H = HEIGHT - TOP_RAIL - BOTTOM_RAIL
HIKITE_R, HIKITE_INSET = .028, .07                 # pull radius and distance from leading edge
_handle_z = HANDLE_HEIGHT_ABOVE_FLOOR - HEIGHT / 2  # Blender local Z (leaf centred on origin)
_hikite_x = -WIDTH / 2 + HIKITE_INSET              # leading (-runtime z) edge


def _faces():
    parts = [dict(name='Oak core', mesh='Door_oak', shape='box', dims=(WIDTH, CORE, HEIGHT), centre=(0, 0, 0),
                  bevel=.0015)]
    for side in (-1, 1):
        y = side * (CORE / 2 + FACE / 2)
        hole = [{'centre': (_hikite_x, y, _handle_z), 'radius': HIKITE_R, 'depth': FACE * 2.2}]
        parts.append(dict(name='Top rail', mesh='Door_oak', shape='box', dims=(WIDTH, FACE, TOP_RAIL),
                          centre=(0, y, HEIGHT / 2 - TOP_RAIL / 2), bevel=.001))
        parts.append(dict(name='Bottom rail', mesh='Door_oak', shape='box', dims=(WIDTH, FACE, BOTTOM_RAIL),
                          centre=(0, y, -HEIGHT / 2 + BOTTOM_RAIL / 2), bevel=.001))
        for i in range(SLATS):
            x = -WIDTH / 2 + SLAT_W / 2 + i * (SLAT_W + SLAT_GAP)
            slat = dict(name='Vertical slat', mesh='Door_oak', shape='box', dims=(SLAT_W, FACE, SLAT_H),
                        centre=(x, y, -HEIGHT / 2 + BOTTOM_RAIL + SLAT_H / 2), bevel=.001)
            if abs(x - _hikite_x) < SLAT_W / 2 + HIKITE_R:
                slat['cuts'] = hole
            parts.append(slat)
        # Recessed brass cup, 1.5 mm below the slat face.
        parts.append(dict(name='Hikite pull', mesh='Door_brass', shape='cylinder_y',
                          dims=(HIKITE_R * 2 - .002, .004, HIKITE_R * 2 - .002),
                          centre=(_hikite_x, side * (THICKNESS / 2 - .0015 - .002), _handle_z)))
    parts.append(dict(name='Edge pull', mesh='Door_brass', shape='box', dims=(.003, .030, .14),
                      centre=(-WIDTH / 2 + .0015, 0, _handle_z), bevel=.0008))
    return parts


PARTS = _faces()
FIXTURES = {
    'bath-door': {
        'title': 'Original light-oak slatted sliding bathroom leaf with recessed brass pulls',
        'parts': PARTS,
        # Relative to the existing bathDoor mesh (its centre), which keeps sliding.
        'runtime_origin_m': [0.0, 0.0, 0.0],
        'runtime_yaw_radians': -math.pi / 2,
        'replaces_home_js': [SLAB_CALL],
        'sidecar_extra': {'runtime_parent': 'bathDoor', 'slab_centre_m': list(SLAB_CENTRE),
                          'slab_dims_m': [THICKNESS, HEIGHT, WIDTH],
                          'leading_edge': '-z (closing direction); pulls at %.2f m above floor' % HANDLE_HEIGHT_ABOVE_FLOOR},
    },
}
MESH_ROLES = sorted({p['mesh'] for f in FIXTURES.values() for p in f['parts']})


def sidecar(name, fixture, *args, **kwargs):
    return base.sidecar(name, fixture, *args, generator='tools/build_home_bath_door.py', **kwargs)


def leaf_runtime_bounds(centre=SLAB_CENTRE):
    """Runtime bounds of the leaf when attached to bathDoor at `centre`."""
    lo, hi = base.runtime_bounds(FIXTURES['bath-door'])
    return [[lo[i] + centre[i] for i in range(3)], [hi[i] + centre[i] for i in range(3)]]


def envelope_problems(tol=1e-9):
    lo, hi = base.runtime_bounds(FIXTURES['bath-door'])
    half = (THICKNESS / 2, HEIGHT / 2, WIDTH / 2)
    return [f'axis {i}: {lo[i]:.4f}..{hi[i]:.4f} exceeds slab half-size {half[i]}'
            for i in range(3) if lo[i] < -half[i] - tol or hi[i] > half[i] + tol]


if __name__ == '__main__':
    try:
        import bpy  # noqa: F401
    except ImportError:
        print('bath-door', {'leaf_runtime_bounds_closed': leaf_runtime_bounds(),
                            'envelope_problems': envelope_problems()})
    else:
        assert not envelope_problems(), envelope_problems()
        base._build_in_blender(base.output_dir_from_argv(sys.argv) if '--output-dir' in sys.argv else OUT,
                               FIXTURES, 'bath-door.blend', 'tools/build_home_bath_door.py')
