"""Original loft-bathroom vanity and toilet for the private SUB-01 home.

Replaces the literal placeholder boxes that tools/home_asset_audit.py ranks
weakest in home.js: an oak box/white slab/cylinder vanity and a three-box
toilet. Direction (written notes only): calm Japanese/modern apartment with
light oak, glazed white ceramic and small brass accents, believable metric
scale. Original procedural geometry; no manufacturer CAD, photos or textures.

The part list below is pure data so CPU tests can verify the declared bounds
against the unchanged home.js colliders without Blender. Run in Blender on
the private server only (never on the owner's Mac):

    blender -b --python tools/build_home_bath_fixtures.py [-- --output-dir DIR]

tools/runpod_furniture_build.py wraps this with a private output directory
outside Git and verifies the result against the declared contract.

Output: web/house/assets/bath-fixtures-original/{vanity,toilet}.glb, their
JSON sidecars and one editable bath-fixtures.blend. GLBs carry geometry and
metric UVs only; the runtime shares existing house materials by mesh name
(see web/house/bath_fixture_materials.mjs). Front = Blender -Y = glTF +Z.
"""
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'web/house/assets/bath-fixtures-original'
OAK_SCAN_METRES = 1.83  # home_oak_veneer physical scan coverage, shared with desk/kitchen
# Top of the loft bathroom tile slab: box(3.05, 0.035, 2.2, -2.325, 3.035, 1.6, tiles, 0).
FLOOR_Y = 3.035 + 0.035 / 2
WEST_WALL_INNER_X = -4 + 0.18 / 2   # box(0.18, ..., -4, ...) west facade
NORTH_BATH_WALL_INNER_Z = 2.7 - 0.1 / 2  # box(3.1, 2.85, 0.1, -2.325, 4.46, 2.7)
BOUNDS_TOLERANCE_M = .002

# Each part: name, mesh (runtime material role), shape, dims (Blender X width,
# Y depth, Z height), centre, and optional shaping. Units are metres; the
# local origin is the footprint centre on the finished floor.
VANITY_W, VANITY_D = .50, .52
VANITY_PARTS = [
    # Wall-hung carcass: 31 cm shadow gap above the tiles keeps it light.
    dict(name='Carcass', mesh='Vanity_oak', shape='box', dims=(.50, .50, .40), centre=(0, .01, .51), bevel=.002),
    dict(name='Lower drawer front', mesh='Vanity_oak', shape='box', dims=(.494, .018, .194),
         centre=(0, -.249, .410), bevel=.0015),
    dict(name='Upper drawer front', mesh='Vanity_oak', shape='box', dims=(.494, .018, .194),
         centre=(0, -.249, .610), bevel=.0015),
    dict(name='Solid oak counter', mesh='Vanity_oak', shape='box', dims=(.50, .52, .024), centre=(0, 0, .722),
         bevel=.003),
    dict(name='Lower drawer pull', mesh='Vanity_brass', shape='box', dims=(.16, .010, .010),
         centre=(0, -.263, .490), bevel=.002),
    dict(name='Upper drawer pull', mesh='Vanity_brass', shape='box', dims=(.16, .010, .010),
         centre=(0, -.263, .690), bevel=.002),
    # Thin-walled glazed vessel basin with a curved inner bowl.
    dict(name='Vessel basin', mesh='Vanity_ceramic', shape='vessel', dims=(.38, .38, .115),
         centre=(0, -.03, .734 + .0575), wall=.009, floor=.012),
    dict(name='Basin waste', mesh='Vanity_brass', shape='cylinder', dims=(.04, .04, .004),
         centre=(0, -.03, .734 + .012 + .002)),
    dict(name='Tap column', mesh='Vanity_brass', shape='cylinder', dims=(.028, .028, .22),
         centre=(0, .205, .734 + .11)),
    dict(name='Tap spout', mesh='Vanity_brass', shape='cylinder_y', dims=(.022, .15, .022),
         centre=(0, .14, .734 + .205)),
    # Side lever keeps the tap clear of the wall face.
    dict(name='Tap lever', mesh='Vanity_brass', shape='box', dims=(.06, .010, .010),
         centre=(.044, .205, .734 + .19), bevel=.003),
]
TOILET_PARTS = [
    # Foot top (.27) stays below the bowl's solid floor (.25-.28), never inside the well.
    dict(name='Ceramic foot', mesh='Toilet_ceramic', shape='rounded', dims=(.22, .32, .27),
         centre=(0, .05, .135), radius=.05, taper_front=.12),
    dict(name='Ceramic bowl', mesh='Toilet_ceramic', shape='bowl', dims=(.36, .50, .15),
         centre=(0, -.03, .325), radius=.06, taper_front=.22, opening=(.27, .34, .12)),
    dict(name='Cistern neck', mesh='Toilet_ceramic', shape='rounded', dims=(.30, .10, .12),
         centre=(0, .19, .36), radius=.03),
    dict(name='Cistern', mesh='Toilet_ceramic', shape='rounded', dims=(.40, .17, .37),
         centre=(0, .265, .575), radius=.04),
    dict(name='Cistern lid', mesh='Toilet_ceramic', shape='rounded', dims=(.41, .18, .025),
         centre=(0, .265, .7725), radius=.012),
    dict(name='Seat ring', mesh='Toilet_seat', shape='seat', dims=(.37, .46, .022),
         centre=(0, -.05, .411), radius=.08, taper_front=.25, opening=(.24, .30)),
    dict(name='Closed lid', mesh='Toilet_seat', shape='rounded', dims=(.37, .44, .018),
         centre=(0, -.04, .431), radius=.08, taper_front=.25),
    dict(name='Left hinge', mesh='Toilet_metal', shape='cylinder_x', dims=(.04, .022, .022),
         centre=(-.11, .165, .424)),
    dict(name='Right hinge', mesh='Toilet_metal', shape='cylinder_x', dims=(.04, .022, .022),
         centre=(.11, .165, .424)),
    dict(name='Dual flush button', mesh='Toilet_metal', shape='cylinder', dims=(.05, .05, .008),
         centre=(0, .265, .789)),
]

FIXTURES = {
    'vanity': {
        'title': 'Original wall-hung oak vanity with glazed vessel basin and brass tap',
        'parts': VANITY_PARTS,
        # Back of the carcass sits 5 mm off the west wall's inner face.
        'runtime_origin_m': [WEST_WALL_INNER_X + .005 + VANITY_D / 2, FLOOR_Y, 1.1],
        'runtime_yaw_radians': math.pi / 2,   # front (glTF +Z) faces the room (+X)
        'collider': {'x': -3.5, 'z': 1.1, 'width': .68, 'depth': .5, 'level': 1},
        'wall_side': {'axis': 'x', 'min': WEST_WALL_INNER_X},
        'replaces_home_js': [
            'box(0.62, 0.66, 0.48, -3.5, 3.36, 1.1, M.wood, 0.02);',
            'box(0.68, 0.1, 0.5, -3.5, 3.73, 1.1, M.white, 0.04);',
            'cylinder(0.12, 0.05, -3.5, 3.81, 1.1, M.white);',
            'beam([-3.5, 3.8, 0.92], [-3.5, 4.01, 0.92], 0.017, M.brass);',
            'beam([-3.5, 4.01, 0.92], [-3.5, 4.01, 1.04], 0.017, M.brass);',
        ],
        'keeps_home_js': ['obstacle(-3.5, 1.1, 0.68, 0.5, 1);'],
    },
    'toilet': {
        'title': 'Original close-coupled glazed toilet with soft rounded bowl, satin seat and cistern',
        'parts': TOILET_PARTS,
        'runtime_origin_m': [-2.9, FLOOR_Y, 2.23],
        'runtime_yaw_radians': math.pi,       # front faces the bathroom (-Z); cistern to north wall
        'collider': {'x': -2.9, 'z': 2.23, 'width': .45, 'depth': .72, 'level': 1},
        'wall_side': {'axis': 'z', 'max': NORTH_BATH_WALL_INNER_Z},
        'replaces_home_js': [
            'box(0.42, 0.42, 0.6, -2.9, 3.24, 2.23, M.white, 0.11);',
            'box(0.43, 0.64, 0.18, -2.9, 3.47, 2.49, M.white, 0.07);',
            'box(0.36, 0.04, 0.46, -2.9, 3.48, 2.18, M.cream, 0.08);',
        ],
        'keeps_home_js': ['obstacle(-2.9, 2.23, 0.45, 0.72, 1);'],
    },
}
MESH_ROLES = sorted({p['mesh'] for f in FIXTURES.values() for p in f['parts']})


def part_bounds(part):
    c, d = part['centre'], part['dims']
    return [c[i] - d[i] / 2 for i in range(3)], [c[i] + d[i] / 2 for i in range(3)]


def local_bounds(parts):
    """Blender-space (X width, Y depth, Z up) AABB of the declared parts."""
    boxes = [part_bounds(p) for p in parts]
    return ([min(b[0][i] for b in boxes) for i in range(3)], [max(b[1][i] for b in boxes) for i in range(3)])


def blender_to_runtime(point, origin, yaw):
    """Blender local -> glTF (x, z, -y) -> three.js rotation.y = yaw -> runtime metres."""
    gx, gy, gz = point[0], point[2], -point[1]
    c, s = math.cos(yaw), math.sin(yaw)
    return [origin[0] + gx * c + gz * s, origin[1] + gy, origin[2] - gx * s + gz * c]


def runtime_bounds(fixture):
    lo, hi = local_bounds(fixture['parts'])
    corners = [blender_to_runtime((x, y, z), fixture['runtime_origin_m'], fixture['runtime_yaw_radians'])
               for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
    return ([min(p[i] for p in corners) for i in range(3)], [max(p[i] for p in corners) for i in range(3)])


def collider_rect(collider):
    return (collider['x'] - collider['width'] / 2, collider['x'] + collider['width'] / 2,
            collider['z'] - collider['depth'] / 2, collider['z'] + collider['depth'] / 2)


def footprint_violations(fixture, tol=1e-6):
    """Runtime footprint must stay inside the unchanged collider, except that the
    wall side may extend into the non-walkable strip up to the wall face."""
    (x0, _, z0), (x1, _, z1) = runtime_bounds(fixture)
    cx0, cx1, cz0, cz1 = collider_rect(fixture['collider'])
    wall = fixture.get('wall_side', {})
    if wall.get('axis') == 'x' and 'min' in wall:
        cx0 = min(cx0, wall['min'])
    if wall.get('axis') == 'z' and 'max' in wall:
        cz1 = max(cz1, wall['max'])
    problems = []
    if x0 < cx0 - tol or x1 > cx1 + tol:
        problems.append(f'x {x0:.4f}..{x1:.4f} outside {cx0:.4f}..{cx1:.4f}')
    if z0 < cz0 - tol or z1 > cz1 + tol:
        problems.append(f'z {z0:.4f}..{z1:.4f} outside {cz0:.4f}..{cz1:.4f}')
    return problems


def sidecar(name, fixture, actual_local_bounds=None, glb=None, triangles=None, vertices=None):
    lo, hi = local_bounds(fixture['parts'])
    data = {
        'geometry': fixture['title'] + '; original procedural Blender construction, no manufacturer CAD.',
        'direction': 'SimbasJungles written direction: warm Japanese/modern apartment, light oak, glazed ceramic, '
                     'brass accents. Not visually compared with the reference.',
        'generator': 'tools/build_home_bath_fixtures.py',
        'declared_blender_bounds_m': [lo, hi],
        'blender_bounds_m': actual_local_bounds or [lo, hi],
        'runtime_origin_m': fixture['runtime_origin_m'],
        'runtime_yaw_radians': fixture['runtime_yaw_radians'],
        'runtime_world_bounds_m': [list(v) for v in runtime_bounds(fixture)],
        'existing_collider': fixture['collider'],
        'mesh_roles': sorted({p['mesh'] for p in fixture['parts']}),
        'runtime_materials': 'Shared house materials by mesh name via web/house/bath_fixture_materials.mjs: '
                             '*_oak -> M.kitchenOak (CC0 home_oak_veneer, metric 1.83 m UVs), '
                             '*_ceramic -> glazed clone of M.white, *_seat -> satin, *_brass -> M.brass, '
                             '*_metal -> M.metal. No embedded textures.',
        'replaces_home_js': fixture['replaces_home_js'],
        'keeps_home_js': fixture['keeps_home_js'],
        'texture_source': 'https://polyhaven.com/a/oak_veneer_01',
        'embedded_textures': False,
    }
    if glb is not None:
        data.update(vertices=vertices, triangles=triangles, glb_bytes=glb.stat().st_size,
                    sha256=hashlib.sha256(glb.read_bytes()).hexdigest())
    return data


# ------------------------------------------------------------------ Blender

def _build_in_blender(out=OUT):  # pragma: no cover - requires Blender on the private server
    import bpy
    import bmesh
    from mathutils import Vector

    bpy.ops.wm.read_factory_settings(use_empty=True)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    preview = {}
    for role in MESH_ROLES:
        m = bpy.data.materials.new(role)
        m.use_nodes = True
        preview[role] = m

    def apply(o, mod):
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier=mod.name)

    def cube(part):
        bpy.ops.mesh.primitive_cube_add(size=1, location=part['centre'])
        o = bpy.context.object
        o.dimensions = part['dims']
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        return o

    def taper(o, part):
        k = part.get('taper_front')
        if not k:
            return
        half = part['dims'][1] / 2
        for v in o.data.vertices:  # mesh-local: the cube is centred on its object origin
            t = max(0.0, min(1.0, -v.co.y / half)) if half else 0
            v.co.x *= 1 - k * t

    def bevel(o, width, segments):
        if width:
            mod = o.modifiers.new('Tactile edge', 'BEVEL')
            mod.width, mod.segments, mod.limit_method = width, segments, 'ANGLE'
            apply(o, mod)

    def cut(o, location, scale, shape='sphere'):
        if shape == 'sphere':
            bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=1, location=location)
        else:
            bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=1, depth=1, location=location)
        cutter = bpy.context.object
        cutter.scale = scale
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        mod = o.modifiers.new('Opening', 'BOOLEAN')
        mod.operation, mod.solver, mod.object = 'DIFFERENCE', 'EXACT', cutter
        apply(o, mod)
        bpy.data.objects.remove(cutter, do_unlink=True)

    def make(part):
        shape, (w, d, h), (x, y, z) = part['shape'], part['dims'], part['centre']
        if shape == 'box':
            o = cube(part)
            bevel(o, part.get('bevel', 0), 3)
        elif shape in ('rounded', 'bowl', 'seat'):
            o = cube(part)
            taper(o, part)
            bevel(o, min(part.get('radius', .01), w / 2.01, d / 2.01, h / 2.01), 8)
            if shape == 'bowl':
                ow, od, oh = part['opening']
                # Glazed bowl: ellipsoidal well opening at the rim.
                cut(o, (x, y - .02, z + h / 2), (ow / 2, od / 2, oh))
            if shape == 'seat':
                ow, od = part['opening']
                cut(o, (x, y - .01, z), (ow / 2, od / 2, h * 2), 'cylinder')
        elif shape == 'vessel':
            bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=w / 2, depth=h, location=(x, y, z))
            o = bpy.context.object
            # Slight foot taper reads as a thrown ceramic bowl rather than a tube.
            for v in o.data.vertices:
                if v.co.z < 0:
                    v.co.x *= .82
                    v.co.y *= .82
            cut(o, (x, y, z + h / 2), (w / 2 - part['wall'], d / 2 - part['wall'], h - part['floor']))
            bevel(o, .004, 4)
        elif shape.startswith('cylinder'):
            axis = shape[-1] if shape != 'cylinder' else 'z'
            radius = {'z': w / 2, 'y': w / 2, 'x': d / 2}[axis]
            depth = {'z': h, 'y': d, 'x': w}[axis]
            rot = {'z': (0, 0, 0), 'y': (math.pi / 2, 0, 0), 'x': (0, math.pi / 2, 0)}[axis]
            bpy.ops.mesh.primitive_cylinder_add(vertices=40, radius=radius, depth=depth, location=(x, y, z),
                                                rotation=rot)
            o = bpy.context.object
            bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
            bevel(o, min(.0015, radius / 3), 2)
        else:
            raise ValueError(shape)
        if part['mesh'].endswith('_ceramic') or part['mesh'].endswith('_seat'):
            sub = o.modifiers.new('Soft glaze', 'SUBSURF')
            sub.levels = sub.render_levels = 1
            apply(o, sub)
        n = o.modifiers.new('Face normals', 'WEIGHTED_NORMAL')
        n.keep_sharp = True
        apply(o, n)
        o.name = part['name']
        o.data.materials.append(preview[part['mesh']])
        layer = o.data.uv_layers.active or o.data.uv_layers.new(name='Metric UV')
        for p in o.data.polygons:
            for li in p.loop_indices:
                v = o.matrix_world @ o.data.vertices[o.data.loops[li].vertex_index].co
                # Oak: horizontal grain along the counter width, vertical faces horizontal
                # grain across drawer fronts; real 1.83 m scan density.
                if abs(p.normal.z) > .5:
                    uv = (v.x, v.y)
                elif abs(p.normal.x) > .5:
                    uv = (v.y, v.z)
                else:
                    uv = (v.x, v.z)
                layer.data[li].uv = (uv[0] / OAK_SCAN_METRES, uv[1] / OAK_SCAN_METRES)
        return o

    results = {}
    for name, fixture in FIXTURES.items():
        groups = {}
        for part in fixture['parts']:
            groups.setdefault(part['mesh'], []).append(make(part))
        joined = []
        for role, objects in groups.items():
            bpy.ops.object.select_all(action='DESELECT')
            for o in objects:
                o.select_set(True)
            bpy.context.view_layer.objects.active = objects[0]
            if len(objects) > 1:
                bpy.ops.object.join()
            o = bpy.context.object
            o.name = o.data.name = role
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
            joined.append(o)
        points = [v.co for o in joined for v in o.data.vertices]
        lo = [min(p[i] for p in points) for i in range(3)]
        hi = [max(p[i] for p in points) for i in range(3)]
        dlo, dhi = local_bounds(fixture['parts'])
        for i in range(3):
            # Subdivision and booleans may only shrink inside the declared envelope.
            assert lo[i] >= dlo[i] - BOUNDS_TOLERANCE_M and hi[i] <= dhi[i] + BOUNDS_TOLERANCE_M, (name, i, lo, hi)
        assert not footprint_violations(fixture), footprint_violations(fixture)
        collection = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(collection)
        for o in joined:
            for c in list(o.users_collection):
                c.objects.unlink(o)
            collection.objects.link(o)
        bpy.ops.object.select_all(action='DESELECT')
        for o in joined:
            o.select_set(True)
        glb = out / f'{name}.glb'
        bpy.ops.export_scene.gltf(filepath=str(glb), export_format='GLB', use_selection=True,
                                  export_materials='NONE', export_cameras=False, export_lights=False)
        triangles = 0
        for o in joined:
            mesh = o.data
            mesh.calc_loop_triangles()
            triangles += len(mesh.loop_triangles)
        data = sidecar(name, fixture, [lo, hi], glb, triangles, sum(len(o.data.vertices) for o in joined))
        (out / f'{name}.json').write_text(json.dumps(data, indent=2))
        results[name] = {'bounds': [lo, hi], 'triangles': triangles, 'bytes': glb.stat().st_size}
    bpy.ops.wm.save_as_mainfile(filepath=str(out / 'bath-fixtures.blend'))
    print('BATH_FIXTURES_BUILT', json.dumps(results), flush=True)


def output_dir_from_argv(argv):
    """Optional `-- --output-dir DIR` (Blender passes script args after `--`)."""
    args = argv[argv.index('--') + 1:] if '--' in argv else []
    if '--output-dir' in args:
        return Path(args[args.index('--output-dir') + 1])
    return OUT


if __name__ == '__main__':
    import sys
    try:
        import bpy  # noqa: F401
    except ImportError:
        # Outside Blender: print the declared contract only, never fake an asset.
        for fixture_name, fixture_spec in FIXTURES.items():
            print(fixture_name, json.dumps({'runtime_world_bounds_m': runtime_bounds(fixture_spec),
                                            'footprint_violations': footprint_violations(fixture_spec)}))
    else:
        _build_in_blender(output_dir_from_argv(sys.argv))
