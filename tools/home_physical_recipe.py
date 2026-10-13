"""Reusable private Cycles scene preparation; never launches a bake or installs maps.

glTF light intensities remain photometric in the immutable source. Blender's
glTF importer converts them to radiometric energy; the measured 683 conversion
restores Three-compatible imported energy for SUN, POINT and SPOT. This is an
import-unit conversion, not a change to the runtime/source sunlight intensity.
"""
import hashlib
import json
import math
import struct
from pathlib import Path

RECIPE = 'home-physical-source-v1'
IMPORT_ENERGY_FACTOR = 683.0
RUNTIME_HDR_ROTATION = -math.pi / 2
CYCLES_HDR_LOOKUP_ROTATION = math.pi / 2

def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def glb_json(path):
    raw = Path(path).read_bytes()
    if len(raw) < 20 or raw[:4] != b'glTF' or struct.unpack_from('<II', raw, 4) != (2, len(raw)):
        raise ValueError('Invalid immutable glTF 2 binary')
    length, kind = struct.unpack_from('<II', raw, 12)
    if kind != 0x4E4F534A or 20 + length > len(raw):
        raise ValueError('Invalid glTF JSON chunk')
    return json.loads(raw[20:20 + length])

def fixture_strength(value, mode):
    return float(value) if mode == 'night' and not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value > 0 else 0.0

def validate_inputs(source, atlas, source_sha256, atlas_sha256, geometry_proof=None):
    """Refuse changed files before import; no source/atlas rewriting is permitted."""
    for path, expected in [(source, source_sha256), (atlas, atlas_sha256)]:
        if not isinstance(expected, str) or len(expected) != 64 or sha256(path) != expected:
            raise ValueError('Immutable source/atlas SHA mismatch: ' + str(path))
    source_doc, atlas_doc = glb_json(source), glb_json(atlas)
    forbidden = [node.get('name', str(i)) for i, node in enumerate(source_doc.get('nodes', [])) if node.get('extras', {}).get('excludeStaticBake')]
    if forbidden:
        raise ValueError('Excluded contact/device/dynamic nodes survived source export: ' + repr(forbidden))
    receivers = [node for node in atlas_doc.get('nodes', []) if 'mesh' in node]
    size = atlas_doc.get('extras', {})
    if not receivers or any(not isinstance(size.get(k), int) or size[k] <= 0 for k in ('width', 'height')):
        raise ValueError('Missing immutable receiver atlas dimensions')
    if geometry_proof is not None:
        proof = json.loads(Path(geometry_proof).read_text())
        if proof.get('source_sha256') != source_sha256 or proof.get('atlas_sha256') != atlas_sha256 or proof.get('receivers') != len(receivers) or proof.get('bad') != {}:
            raise ValueError('Geometry equivalence proof is not bound to these inputs')
        checks = proof.get('checks', {})
        if len(checks) != len(receivers) or not all(c.get('fresh_matches_atlas') is True for c in checks.values()):
            raise ValueError('Incomplete receiver geometry equivalence proof')
    return {'recipe': RECIPE, 'source_sha256': source_sha256, 'atlas_sha256': atlas_sha256,
            'receivers': len(receivers), 'width': size['width'], 'height': size['height'],
            'source_lights': source_doc.get('extensions', {}).get('KHR_lights_punctual', {}).get('lights', []),
            'tagged_fixtures': [{'material': i, 'strength': m['extras']['lampEmission']} for i, m in enumerate(source_doc.get('materials', [])) if fixture_strength(m.get('extras', {}).get('lampEmission'), 'night')],
            'unlit_materials': sum('KHR_materials_unlit' in m.get('extensions', {}) for m in source_doc.get('materials', [])),
            'tagged_excluded_nodes_present': len(forbidden),
            'scope': 'Input bytes unchanged; tagged bake exclusions checked. Optional indexed-world-geometry proof binds all receivers; no untagged-contact inference.'}

def _linear_hex(value):
    result = []
    for i in (0, 2, 4):
        channel = int(value[i:i + 2], 16) / 255
        result.append(channel / 12.92 if channel <= .04045 else ((channel + .055) / 1.055) ** 2.4)
    return result

def apply_physical_recipe(bpy, scene, *, mode, hdr_path, hdr_sha256, world_only=False):
    """Prepare an already-imported scene once, retaining source meshes/UVs.

    Day indirect: actual SUN + HDR/positive hemidome, no practical emitters.
    Night indirect: actual POINT/SPOT + explicit lampEmission tags, world off.
    World-direct component: world only, all fixtures/emission off. Caller owns
    receiver selection and DIFFUSE pass flags; this helper never starts a bake.
    """
    if mode not in ('day', 'night') or world_only and mode != 'day':
        raise ValueError('Physical recipe requires day/night; world-direct is day only')
    if scene.get('homePhysicalRecipe'):
        raise ValueError('Physical import energies have already been converted')
    if sha256(hdr_path) != hdr_sha256:
        raise ValueError('HDR source SHA mismatch')
    energies = []
    for obj in list(scene.objects):
        if obj.type != 'LIGHT':
            continue
        keep = not world_only and ((mode == 'day' and obj.data.type == 'SUN') or (mode == 'night' and obj.data.type in ('POINT', 'SPOT')))
        if not keep:
            bpy.data.objects.remove(obj, do_unlink=True)
            continue
        before = obj.data.energy
        obj.data.energy = before * IMPORT_ENERGY_FACTOR
        energies.append({'name': obj.name, 'type': obj.data.type, 'imported_energy': before, 'cycles_energy': obj.data.energy, 'factor': IMPORT_ENERGY_FACTOR})
    converted_unlit, enabled_fixtures = 0, []
    for material in bpy.data.materials:
        if not material.use_nodes:
            continue
        strength = 0 if world_only else fixture_strength(material.get('lampEmission'), mode)
        if strength:
            enabled_fixtures.append({'name': material.name, 'lampEmission': strength})
        nodes, links = material.node_tree.nodes, material.node_tree.links
        for node in list(nodes):
            if node.type == 'EMISSION' and not strength:
                # glTF unlit screens import as Emission. Make them passive
                # reflectors, preserving color texture links and Alpha Mix.
                diffuse = nodes.new('ShaderNodeBsdfDiffuse')
                diffuse.inputs['Color'].default_value = node.inputs['Color'].default_value
                for link in list(node.inputs['Color'].links):
                    links.new(link.from_socket, diffuse.inputs['Color'])
                for link in list(node.outputs[0].links):
                    links.new(diffuse.outputs[0], link.to_socket)
                nodes.remove(node)
                converted_unlit += 1
            elif node.type in ('BSDF_PRINCIPLED', 'EMISSION'):
                socket = node.inputs.get('Emission Strength' if node.type == 'BSDF_PRINCIPLED' else 'Strength')
                if socket is not None:
                    for link in list(socket.links):
                        links.remove(link)
                    socket.default_value = strength
    world = bpy.data.worlds.new('Private matched physical environment')
    scene.world = world
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    background = nodes['Background']
    hdr = nodes.new('ShaderNodeTexEnvironment')
    hdr.image = bpy.data.images.load(str(hdr_path), check_existing=True)
    coordinates, mapping = nodes.new('ShaderNodeTexCoord'), nodes.new('ShaderNodeMapping')
    mapping.inputs['Rotation'].default_value[2] = CYCLES_HDR_LOOKUP_ROTATION
    links.new(coordinates.outputs['Generated'], mapping.inputs['Vector'])
    links.new(mapping.outputs['Vector'], hdr.inputs['Vector'])
    links.new(hdr.outputs['Color'], background.inputs['Color'])
    background.inputs['Strength'].default_value = .4225 if mode == 'day' else 0
    hemi = bpy.data.images.new('Physical positive hemidome', 32, 16, alpha=False, float_buffer=True)
    hemi.colorspace_settings.name = 'Non-Color'
    pixels = []
    for row in range(16):
        rgb = _linear_hex('8f7965' if row < 8 else 'e4eced')
        pixels.extend([*(c * .22 / math.pi for c in rgb), 1] * 32)
    hemi.pixels.foreach_set(pixels)
    hemi.update()
    hemi_texture, hemi_background = nodes.new('ShaderNodeTexEnvironment'), nodes.new('ShaderNodeBackground')
    hemi_texture.image, hemi_texture.interpolation = hemi, 'Closest'
    links.new(hemi_texture.outputs['Color'], hemi_background.inputs['Color'])
    hemi_background.inputs['Strength'].default_value = 1 if mode == 'day' else 0
    summed = nodes.new('ShaderNodeAddShader')
    links.new(background.outputs['Background'], summed.inputs[0])
    links.new(hemi_background.outputs['Background'], summed.inputs[1])
    links.new(summed.outputs[0], nodes['World Output'].inputs['Surface'])
    scene['homePhysicalRecipe'] = RECIPE
    return {'recipe': RECIPE, 'mode': mode, 'world_only': world_only,
            'source_runtime_photometric_intensities_changed': False,
            'import_energy_factor': IMPORT_ENERGY_FACTOR, 'lights': energies,
            'fixture_emission_policy': 'positive finite lampEmission metadata only, night only',
            'enabled_fixtures': enabled_fixtures, 'unlit_emission_nodes_to_passive_diffuse': converted_unlit,
            'hdr_sha256': hdr_sha256, 'runtime_hdr_rotation_y': RUNTIME_HDR_ROTATION,
            'cycles_hdr_lookup_rotation_z': CYCLES_HDR_LOOKUP_ROTATION,
            'hdr_strength': .4225 if mode == 'day' else 0, 'positive_hemidome_strength': 1 if mode == 'day' else 0,
            'hemisphere_intensity': .22, 'hemisphere_radiance_divisor': math.pi,
            'direct': bool(world_only), 'indirect': not world_only, 'surface_albedo': False,
            'scope': 'Scene preparation only; no bake, map installation, source rewrite or live-device emission capture.'}
