"""Server-only editable assembly of the actual V4 home using home114 furniture.

Run on the GPU server (this script never renders):
  blender --background --python tools/assemble_home_blender.py -- \
    --source out/lighting-v23/unreal-home-lab/Sub01HomeLab/SourceAssets/full-home.glb \
    --assets-root web/house/assets --output-dir out/home114-assembled

Writes house.blend, house.glb and assembly.json. The functioning browser remains
home114; this authoring export is not a replacement for its brain/device logic.

Optional, off by default: --bath-fixtures DIR swaps the loft-bathroom placeholder
boxes for the original vanity/toilet built by tools/build_home_bath_fixtures.py
(DIR holds vanity/toilet .glb + .json). Without the flag the output is unchanged.
"""
import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path


OLD_PREFIXES = ('house-bed-frame-', 'house-bedding-', 'house-coffee-table-',
                'house-coffee-machine-')
BATH_FIXTURE_NAMES = ('vanity', 'toilet')
PLANE_TOLERANCE_M = .002
# role -> (sRGB tint, roughness, metallic, clearcoat); mirrors bath_fixture_materials.mjs
# and the house M.kitchenOak/M.brass/M.metal values.
BATH_ROLE_FINISH = {
    'oak': ('#e7dcc9', .92, 0, 0),
    'ceramic': ('#f2eee5', .18, 0, .55),
    'seat': ('#ebe6db', .42, 0, 0),
    'brass': ('#b19762', .40, .55, 0),
    'metal': ('#353a35', .38, 0, 0),
}


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--assets-root', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'web/house/assets')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--source-sha')
    parser.add_argument('--bath-fixtures', type=Path, default=None,
                        help='opt-in directory with original vanity/toilet GLB + sidecar JSON')
    return parser.parse_args(argv)


def runtime_to_blender(point):
    """Browser/three.js metres (Y up) -> Blender world after glTF import (Z up)."""
    x, y, z = point
    return (x, -z, y)


def placeholder_boxes(call):
    """Runtime AABB plus edge radius of one literal home.js box/cylinder/beam call."""
    def numbers(text):
        return [float(v) for v in re.findall(r'-?\d*\.?\d+', text)]
    if call.startswith(('box(', 'cylinder(')):
        args = [a.strip() for a in call[call.index('(') + 1:call.rindex(')')].split(',')]
    if call.startswith('box('):
        # home.js: box(w, h, d, x, y, z, m = M.wood, r = 0.012); r=0 is a sharp box.
        w, h, d, x, y, z = (float(a) for a in args[:6])
        radius = float(args[7]) if len(args) > 7 else .012
        return {'low': (x - w / 2, y - h / 2, z - d / 2), 'high': (x + w / 2, y + h / 2, z + d / 2),
                'radius': min(radius, w / 3, h / 3, d / 3)}
    if call.startswith('cylinder('):
        r, h, x, y, z = (float(a) for a in args[:5])
        return {'low': (x - r, y - h / 2, z - r), 'high': (x + r, y + h / 2, z + r), 'radius': r}
    if call.startswith('beam('):
        a, b, rest = re.match(r'beam\(\[([^\]]*)\],\s*\[([^\]]*)\],\s*([-\d.]+)', call).groups()
        a, b, r = numbers(a), numbers(b), float(rest)
        return {'low': tuple(min(a[i], b[i]) - r for i in range(3)),
                'high': tuple(max(a[i], b[i]) + r for i in range(3)), 'radius': r}
    raise ValueError('Unsupported placeholder call: ' + call)


def blender_box(box):
    a, b = runtime_to_blender(box['low']), runtime_to_blender(box['high'])
    return {'low': tuple(min(a[i], b[i]) for i in range(3)), 'high': tuple(max(a[i], b[i]) for i in range(3)),
            'radius': box['radius']}


def face_on_placeholder_surface(points, normal, box, tolerance=PLANE_TOLERANCE_M):
    """True when a face (Blender world points) belongs to the placeholder's own
    surface: every vertex inside the box, and either an axis-aligned face lying
    on one of its six planes or a rounded-edge face within its edge radius.
    Interior objects (e.g. books hidden inside the old vanity) stay untouched."""
    low, high = box['low'], box['high']
    if not all(low[i] - tolerance <= p[i] <= high[i] + tolerance for p in points for i in range(3)):
        return False
    centre = [sum(p[i] for p in points) / len(points) for i in range(3)]
    length = math.sqrt(sum(n * n for n in normal)) or 1
    unit = [n / length for n in normal]
    axis = max(range(3), key=lambda i: abs(unit[i]))
    if abs(unit[axis]) > .999:
        plane = high[axis] if unit[axis] > 0 else low[axis]
        return abs(centre[axis] - plane) <= tolerance
    # Rounded edges/corners lie within the radius of at least two planes; a
    # bevelled object resting just inside one plane (a book's lower edge) does not.
    near = sum(min(centre[i] - low[i], high[i] - centre[i]) <= box['radius'] + tolerance for i in range(3))
    return near >= 2


def bath_fixture_plan(directory):
    """Validated import plan for the optional original bath fixtures."""
    plan = []
    for name in BATH_FIXTURE_NAMES:
        glb, sidecar = Path(directory) / f'{name}.glb', Path(directory) / f'{name}.json'
        data = json.loads(sidecar.read_text())
        if data.get('sha256') != sha256(glb):
            raise ValueError(f'{glb} does not match the sha256 recorded in {sidecar.name}')
        origin, yaw = data.get('runtime_origin_m'), data.get('runtime_yaw_radians')
        if not (isinstance(origin, list) and len(origin) == 3 and all(map(math.isfinite, origin))
                and isinstance(yaw, (int, float)) and math.isfinite(yaw)):
            raise ValueError(f'{sidecar} lacks a finite runtime origin/yaw')
        calls = data.get('replaces_home_js') or []
        if not calls:
            raise ValueError(f'{sidecar} names no placeholder to replace')
        plan.append({'name': name, 'glb': glb, 'identifier': f'house-original-bath-{name}',
                     'location': runtime_to_blender(origin), 'yaw': yaw,
                     'remove': [blender_box(placeholder_boxes(call)) for call in calls], 'calls': calls})
    return plan


def glb_metadata(path):
    import struct
    with Path(path).open('rb') as stream:
        header = stream.read(20)
        if header[:4] != b'glTF' or struct.unpack_from('<I', header, 4)[0] != 2:
            raise ValueError('Expected a glTF 2 binary source')
        return json.loads(stream.read(struct.unpack_from('<I', header, 12)[0]))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(part)
    return digest.hexdigest()


def main():
    import bpy
    import bmesh
    from mathutils import Vector

    args = parse_args(sys.argv[sys.argv.index('--') + 1:])
    # Validate the optional fixtures before any expensive import work.
    bath_plan = bath_fixture_plan(args.bath_fixtures) if args.bath_fixtures else []
    source_hash = sha256(args.source)
    if args.source_sha and source_hash != args.source_sha:
        raise ValueError('Source checksum does not match the requested V4 source')
    source = glb_metadata(args.source)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(args.source.resolve()))
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1
    bpy.context.view_layer.update()

    def bake_id(obj):
        return str(obj.get('bakeId', obj.name))

    def find_id(identifier):
        return next((obj for obj in scene.objects if bake_id(obj) == identifier), None)

    def bsdf(material):
        return next(node for node in material.node_tree.nodes
                    if node.type == 'BSDF_PRINCIPLED')

    def color(hex_color):
        values = [int(hex_color[index:index+2], 16) / 255 for index in (1, 3, 5)]
        return tuple(v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4
                     for v in values) + (1,)

    def base_image(material):
        visited = set()
        def walk(socket):
            for link in socket.links:
                node = link.from_node
                if node in visited:
                    continue
                visited.add(node)
                if node.type == 'TEX_IMAGE' and node.image:
                    return node.image
                for input_socket in node.inputs:
                    result = walk(input_socket)
                    if result:
                        return result
            return None
        return walk(bsdf(material).inputs['Base Color'])

    # Resolve source material owners before old furniture is removed. V4 has
    # anonymous image/material names; bakeId is the reliable exported identity.
    architecture = find_id('house-static-2')
    pillow = find_id('house-bedding-Pillow_1')
    if not architecture or not pillow:
        raise RuntimeError('V4 architecture oak or linen material owner not found')
    oak_image = base_image(architecture.data.materials[0])
    linen_image = base_image(pillow.data.materials[0])
    white_owner = find_id('house-static-72')
    cup_material = white_owner.data.materials[0] if white_owner else None
    if not oak_image or not linen_image:
        raise RuntimeError('Missing embedded V4 oak/linen albedo textures')

    def set_base(material, tint, image=None, repeat=1):
        shader = bsdf(material)
        socket = shader.inputs['Base Color']
        for link in list(socket.links):
            material.node_tree.links.remove(link)
        socket.default_value = color(tint)
        material.diffuse_color = color(tint)
        if image:
            nodes, links = material.node_tree.nodes, material.node_tree.links
            texture = nodes.new('ShaderNodeTexImage')
            texture.image = image
            texture.extension = 'REPEAT'
            coordinates = nodes.new('ShaderNodeTexCoord')
            mapping = nodes.new('ShaderNodeMapping')
            mapping.inputs['Scale'].default_value = (repeat, repeat, 1)
            multiply = nodes.new('ShaderNodeMixRGB')
            multiply.blend_type = 'MULTIPLY'
            multiply.inputs[0].default_value = 1
            multiply.inputs[2].default_value = color(tint)
            links.new(coordinates.outputs['UV'], mapping.inputs['Vector'])
            links.new(mapping.outputs['Vector'], texture.inputs['Vector'])
            links.new(texture.outputs['Color'], multiply.inputs[1])
            links.new(multiply.outputs['Color'], socket)

    def set_roughness(material, factor, source_factor=1):
        socket = bsdf(material).inputs['Roughness']
        if socket.is_linked:
            previous = socket.links[0].from_socket
            multiply = material.node_tree.nodes.new('ShaderNodeMath')
            multiply.operation = 'MULTIPLY'
            multiply.inputs[1].default_value = factor / source_factor
            material.node_tree.links.new(previous, multiply.inputs[0])
            material.node_tree.links.new(multiply.outputs[0], socket)
        else:
            socket.default_value = factor

    # Find the merged wall receiver from V4 source bounds, not a material index.
    wall_ids = []
    for node in source['nodes']:
        if 'mesh' not in node:
            continue
        primitive = source['meshes'][node['mesh']]['primitives'][0]
        accessor = source['accessors'][primitive['attributes']['POSITION']]
        low, high = accessor.get('min', []), accessor.get('max', [])
        if len(low) == 3 and low[0] < -4.08 and high[0] > 4.08 and high[1] > 6.14:
            wall_ids.append(node.get('extras', {}).get('bakeId', node.get('name')))
    wall_materials = set()
    for identifier in wall_ids:
        obj = find_id(identifier)
        if obj:
            wall_materials.update(material for material in obj.data.materials if material)
    if not wall_materials:
        raise RuntimeError('No merged structural wall receiver found in V4')
    for material in wall_materials:
        set_base(material, '#f2f0e9')
        shader = bsdf(material)
        set_roughness(material, .95)
        # home114 keeps subtle scanned relief but removes clouded albedo.
        for node in material.node_tree.nodes:
            if node.type == 'NORMAL_MAP':
                node.inputs['Strength'].default_value = .035
        material['home114PaintedIvory'] = True

    removed = []
    for obj in list(scene.objects):
        if bake_id(obj).startswith(OLD_PREFIXES):
            removed.append(bake_id(obj))
            bpy.data.objects.remove(obj, do_unlink=True)
    for prefix in OLD_PREFIXES:
        if not any(identifier.startswith(prefix) for identifier in removed):
            raise RuntimeError('Missing old furniture removal group: ' + prefix)

    # The old mattress is part of a merged white-material mesh, alongside
    # bathroom fittings. Remove only faces inside its measured world bounds.
    low = Vector((-3.201, 1.284, 3.369))
    high = Vector((-1.599, 3.416, 3.571))
    mattress_faces = 0
    art_vertices = 0
    for obj in list(scene.objects):
        if obj.type != 'MESH':
            continue
        world = obj.matrix_world
        def in_mattress(vertex):
            point = world @ vertex.co
            return all(low[index] <= point[index] <= high[index] for index in range(3))
        selected = {vertex.index for vertex in obj.data.vertices if in_mattress(vertex)}
        if selected:
            mesh = bmesh.new()
            mesh.from_mesh(obj.data)
            mesh.verts.ensure_lookup_table()
            faces = [face for face in mesh.faces
                     if all(vertex.index in selected for vertex in face.verts)]
            mattress_faces += len(faces)
            bmesh.ops.delete(mesh, geom=faces, context='FACES')
            orphaned = [vertex for vertex in mesh.verts if not vertex.link_faces]
            if orphaned:
                bmesh.ops.delete(mesh, geom=orphaned, context='VERTS')
            mesh.to_mesh(obj.data)
            mesh.free()
        # Old art center 4.65 -> 4.95. Its framed slab is separately batched;
        # this thin front-of-wall selection leaves all wall geometry unchanged.
        inverse = world.inverted()
        for vertex in obj.data.vertices:
            point = world @ vertex.co
            if (-2.681 <= point.x <= -1.719 and 3.850 <= point.y <= 3.900
                    and 4.029 <= point.z <= 5.271):
                point.z += .30
                vertex.co = inverse @ point
                art_vertices += 1
        obj.data.update()
    if not mattress_faces:
        raise RuntimeError('Old merged mattress was not removed; aborting duplicate bed export')

    imported_assets = []
    def asset_path(relative):
        path = args.assets_root / relative
        if path.is_file():
            return path
        # stage_unreal_home.py flattens the two prepared GLBs in SourceAssets.
        flattened = {
            'cc0-queen-bed/queen-bed.glb': 'cc0-queen-bed-queen-bed.glb',
            'cc0-porta-espresso/porta-espresso.glb': 'cc0-porta-espresso-porta-espresso.glb',
        }
        alternate = args.assets_root / flattened.get(relative, relative)
        if alternate.is_file():
            return alternate
        raise FileNotFoundError(path)

    def import_asset(relative, identifier, anchor, width=None, yaw=0.0):
        path = relative if isinstance(relative, Path) else asset_path(relative)
        previous = set(scene.objects)
        bpy.ops.import_scene.gltf(filepath=str(path.resolve()))
        objects = set(scene.objects) - previous
        roots = [obj for obj in objects if obj.parent not in objects]
        group = bpy.data.objects.new(identifier, None)
        scene.collection.objects.link(group)
        for obj in roots:
            obj.parent = group  # preserve imported local Y-up -> Z-up transform
        bpy.context.view_layer.update()
        meshes = [obj for obj in objects if obj.type == 'MESH']
        points = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
        minimum = Vector([min(point[index] for point in points) for index in range(3)])
        maximum = Vector([max(point[index] for point in points) for index in range(3)])
        dimensions = maximum - minimum
        if width:
            scale = width / dimensions.x
            group.scale = (scale,) * 3
            # Match loadFurnished centering and bottom alignment exactly.
            center = (minimum + maximum) / 2
            group.location = Vector(anchor) - Vector((center.x, center.y, minimum.z)) * scale
        else:
            group.location = anchor
        if yaw:
            # three.js rotation.y about runtime +Y equals Blender rotation about +Z.
            group.rotation_euler[2] = yaw
        for obj in meshes:
            obj['bakeId'] = identifier + '-' + obj.name
            obj['home114Replacement'] = True
        imported_assets.append({'path': str(path), 'sha256': sha256(path),
                                'dimensions_blender': list(dimensions),
                                'anchor_blender': list(group.location),
                                'scale': list(group.scale), 'mesh_groups': len(meshes)})
        return meshes

    bed = import_asset('cc0-queen-bed/queen-bed.glb', 'house-cc0-queen-bed', (-2.4, 2.35, 3))
    if len(bed) != 6:
        raise RuntimeError('Expected six prepared queen-bed material groups')
    bed_metadata = glb_metadata(asset_path('cc0-queen-bed/queen-bed.glb'))
    original_roughness = {entry['name']: entry.get('pbrMetallicRoughness', {}).get('roughnessFactor', 1)
                          for entry in bed_metadata['materials']}
    for obj in bed:
        material = obj.data.materials[0].copy()
        obj.data.materials[0] = material
        upholstery = 'upholstery' in material.name
        tint = '#b99845' if 'teal' in material.name else '#f7f4eb'
        set_base(material, tint if upholstery else '#e7dcc9',
                 linen_image if upholstery else oak_image, 2 if upholstery else 1)
        old_factor = next(factor for name, factor in original_roughness.items()
                          if material.name.startswith(name))
        set_roughness(material, .92 if upholstery else .82, old_factor)
    import_asset('cc0-porta-espresso/porta-espresso.glb', 'house-cc0-porta-espresso', (-1.25, 3.5, .925))
    # home114 retains the separate 24-sided porcelain cup after replacing the appliance.
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=.06, depth=.08,
                                        location=(-1.24, 3.27, .98))
    cup = bpy.context.object
    cup.name = 'home114-retained-porcelain-cup'
    if cup_material:
        cup.data.materials.append(cup_material)
    cup['home114RuntimeCup'] = True
    import_asset('modern_coffee_table_01/modern_coffee_table_01.gltf',
                 'house-cc0-coffee-table', (-3.2, -.1, 0), width=.70)
    for obj in scene.objects:
        if obj.type == 'MESH' and obj.name.startswith(('Haven_linen', 'Haven_seams')):
            material = obj.data.materials[0]
            image = base_image(material)
            set_base(material, '#737e87' if obj.name.startswith('Haven_linen') else '#58616a', image)
    bath_report = []
    for fixture in bath_plan:
        # Placeholder boxes are merged into static batches: delete only faces
        # lying on each placeholder's own surface, then import the original.
        removed_faces = 0
        for obj in list(scene.objects):
            if obj.type != 'MESH' or obj.get('home114Replacement'):
                continue
            world = obj.matrix_world
            normal_matrix = world.to_3x3()
            mesh = bmesh.new()
            mesh.from_mesh(obj.data)
            doomed = [face for face in mesh.faces
                      if any(face_on_placeholder_surface([tuple(world @ v.co) for v in face.verts],
                                                         tuple(normal_matrix @ face.normal), box)
                             for box in fixture['remove'])]
            if doomed:
                removed_faces += len(doomed)
                bmesh.ops.delete(mesh, geom=doomed, context='FACES')
                orphaned = [vertex for vertex in mesh.verts if not vertex.link_faces]
                if orphaned:
                    bmesh.ops.delete(mesh, geom=orphaned, context='VERTS')
                mesh.to_mesh(obj.data)
                obj.data.update()
            mesh.free()
        if not removed_faces:
            raise RuntimeError('No placeholder faces found for bath ' + fixture['name'])
        meshes = import_asset(fixture['glb'], fixture['identifier'], fixture['location'], yaw=fixture['yaw'])
        for obj in meshes:
            role = obj.name.split('.')[0].split('_')[-1]
            if role not in BATH_ROLE_FINISH:
                raise RuntimeError('Unexpected bath fixture mesh ' + obj.name)
            tint, roughness, metallic, coat = BATH_ROLE_FINISH[role]
            material = bpy.data.materials.new('bath-' + fixture['name'] + '-' + role)
            material.use_nodes = True
            # Same values as web/house/bath_fixture_materials.mjs; oak shares the V4 scan.
            set_base(material, tint, oak_image if role == 'oak' else None)
            shader = bsdf(material)
            shader.inputs['Roughness'].default_value = roughness
            shader.inputs['Metallic'].default_value = metallic
            for socket in ('Coat Weight', 'Clearcoat'):
                if coat and socket in shader.inputs:
                    shader.inputs[socket].default_value = coat
            obj.data.materials.clear()
            obj.data.materials.append(material)
        bath_report.append({'name': fixture['name'], 'removed_placeholder_faces': removed_faces,
                            'replaced_calls': fixture['calls'], 'mesh_groups': [m.name for m in meshes]})
    bpy.context.view_layer.update()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    scene['homeVersion'] = 114
    scene['privateOnly'] = True
    scene['sourceSHA256'] = source_hash
    scene['oldFurnitureBakeInvalidated'] = True
    bpy.ops.file.pack_all()
    blend = args.output_dir / 'house.blend'
    glb = args.output_dir / 'house.glb'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend.resolve()))
    bpy.ops.export_scene.gltf(filepath=str(glb.resolve()), export_format='GLB',
                              export_yup=True, export_extras=True)
    report = {'home_version': 114, 'source_sha256': source_hash,
              'private_only': True, 'rendered': False, 'removed_bake_ids': removed,
              'removed_merged_mattress_faces': mattress_faces,
              'raised_art_vertices': art_vertices, 'ivory_wall_materials': len(wall_materials),
              'assets': imported_assets, 'blend': str(blend), 'glb': str(glb),
              'output_glb_sha256': sha256(glb),
              'scope': 'Editable server authoring assembly; browser devices/brain remain authoritative.'}
    if bath_report:
        report['bath_fixtures'] = bath_report
    (args.output_dir / 'assembly.json').write_text(json.dumps(report, indent=2) + '\n')
    print('HOME114_ASSEMBLED', json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
