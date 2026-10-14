"""Read-only source-tagged fixture audit in the already-loaded ActualHome.

Sole editor owner calls run(output, glb, expected_sha256). Requires the actual
full-home GLB and its independently recorded full SHA256. Never creates MID,
sets material values, loads a level or changes light state. Only positive finite
material extras.lampEmission qualify; screen emissives do not qualify by glow.
Reports real enumerated parameters and all shared users before any native toggle
implementation. Explicit lamp-name-to-fixture grouping still needs review.
"""
import hashlib
import json
import math
import re
import struct
from pathlib import Path

LEVEL = '/Game/Sub01Home/ActualHome'
NODE = re.compile(r':PersistentLevel\.full-home_node_(\d+)\.StaticMeshComponent\d+$')
MATERIAL_ROOT = '/Game/Sub01Home/ImportedScene/full-home/Materials/'
# Root's exact source-position review against authored light table, 2026-10-14.
# Shared Material_63 is deliberately split by source node, never a global write.
FIXTURE_CONTROLS = {
    66: ('KitchenWork', 13, 'Material_13'),
    126: ('DeskLamp', 63, 'Material_63'),
    127: ('LowerPendant', 63, 'Material_63'),
    129: ('UpperPendant', 63, 'Material_63'),
    198: ('BedLamp', 63, 'Material_63'),
    199: ('BedLamp', 79, 'Material_91'),
}


def source_fixtures(glb, expected_sha256):
    raw = Path(glb).read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if not re.fullmatch('[0-9a-f]{64}', expected_sha256) or actual != expected_sha256:
        raise ValueError('Actual full-home GLB SHA256 does not match explicit expected identity')
    if raw[:4] != b'glTF' or struct.unpack_from('<I', raw, 4)[0] != 2 or struct.unpack_from('<I', raw, 8)[0] != len(raw):
        raise ValueError('Not a complete GLB v2')
    length, kind = struct.unpack_from('<II', raw, 12)
    if kind != 0x4E4F534A:
        raise ValueError('GLB first chunk is not JSON')
    doc = json.loads(raw[20:20+length])
    tagged = {}
    for index, material in enumerate(doc.get('materials', [])):
        strength = material.get('extras', {}).get('lampEmission')
        if isinstance(strength, bool) or not isinstance(strength, (int, float)) or not math.isfinite(strength) or strength <= 0:
            continue
        tagged[index] = {'source_material_index': index, 'source_material_name': material.get('name'),
                         'lampEmission': strength, 'source_emissive_factor': material.get('emissiveFactor', [0, 0, 0]),
                         'source_emissive_strength': material.get('extensions', {}).get('KHR_materials_emissive_strength', {}).get('emissiveStrength', 1)}
    fixtures = []
    for index, node in enumerate(doc.get('nodes', [])):
        if 'mesh' not in node:
            continue
        for slot, primitive in enumerate(doc['meshes'][node['mesh']].get('primitives', [])):
            if primitive.get('material') in tagged:
                fixtures.append(dict(tagged[primitive['material']], source_node_index=index,
                                     source_node_name=node.get('name'), source_primitive_slot=slot,
                                     source_local_translation=node.get('translation', [0, 0, 0]),
                                     source_parent_node_indices=[p for p, candidate in enumerate(doc['nodes']) if index in candidate.get('children', [])]))
    return {'sha256': actual, 'tagged_material_count': len(tagged), 'fixtures': fixtures}


def run(output, glb, expected_sha256, *, u=None):
    source = source_fixtures(glb, expected_sha256)
    if u is None:
        import unreal as u
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if world is None or world.get_path_name().split('.', 1)[0] != LEVEL:
        raise RuntimeError('ActualHome must already be loaded by sole editor owner')
    nodes, users = {}, {}
    for actor in u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors():
        for component in actor.get_components_by_class(u.MeshComponent):
            path = component.get_path_name()
            match = NODE.search(path)
            if match:
                nodes.setdefault(int(match.group(1)), []).append((actor, component))
            for slot, material in enumerate(component.get_materials()):
                if material:
                    users.setdefault(material.get_path_name(), []).append({'actor': actor.get_actor_label(), 'component': path, 'slot': slot})
    results = []
    manifest_errors = []
    if {f['source_node_index'] for f in source['fixtures']} != set(FIXTURE_CONTROLS) or len(source['fixtures']) != 6:
        manifest_errors.append('Source tagged fixture set differs from reviewed exact six-node control manifest')
    for fixture in source['fixtures']:
        row = dict(fixture, errors=[], parameters={}, native_toggle_available=False)
        control = FIXTURE_CONTROLS.get(fixture['source_node_index'])
        if control and (fixture['source_material_index'], fixture['source_material_name']) == control[1:]:
            row['reviewed_native_lamp_control'] = control[0]
        else:
            row['errors'].append('Source fixture/material identity differs from reviewed native control manifest')
        matches = nodes.get(fixture['source_node_index'], [])
        if len(matches) != 1:
            row['errors'].append('Source node must match exactly one actual imported component')
            results.append(row)
            continue
        actor, component = matches[0]
        row.update(actor=actor.get_actor_label(), component=component.get_path_name())
        if actor.get_actor_label() != fixture['source_node_name']:
            row['errors'].append('Actual actor label differs from exact source node name')
        slot = fixture['source_primitive_slot']
        materials = component.get_materials()
        material = materials[slot] if slot < len(materials) else None
        if material is None:
            row['errors'].append('Actual primitive material slot is missing')
            results.append(row)
            continue
        path = material.get_path_name()
        row.update(actual_material=path, all_material_users=users[path])
        name = fixture['source_material_name']
        expected = MATERIAL_ROOT + name + '.' + name if isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_]+', name) else None
        row['expected_original_material'] = expected
        if expected is None or path != expected:
            row['errors'].append('Actual saved binding is not exact imported source material identity')
        if len(users[path]) != 1:
            row['errors'].append('Shared material: every source user must be explicitly reviewed before toggle')
        if not isinstance(material, u.MaterialInstance):
            row['errors'].append('Actual binding is not a MaterialInstance')
        else:
            for kind in ('scalar', 'vector', 'texture'):
                try:
                    values = {}
                    for parameter in getattr(u.MaterialEditingLibrary, 'get_'+kind+'_parameter_names')(material):
                        if 'emiss' not in str(parameter).lower():
                            continue
                        value = getattr(u.MaterialEditingLibrary, 'get_material_instance_'+kind+'_parameter_value')(material, parameter)
                        values[str(parameter)] = ([float(getattr(value, c)) for c in 'rgba'] if kind == 'vector' and value is not None
                                                  else value.get_path_name() if kind == 'texture' and value is not None
                                                  else float(value) if kind == 'scalar' and value is not None else None)
                    row['parameters'][kind] = values
                except Exception as error:
                    row['errors'].append(kind+' enumeration: '+str(error))
            scalar, vector = row['parameters'].get('scalar', {}), row['parameters'].get('vector', {})
            row['exact_zero_override_parameters_present'] = [p for p in ('EmissiveFactor', 'EmissiveStrength') if (p in vector and vector[p] is not None) or (p in scalar and scalar[p] is not None)]
            if not row['exact_zero_override_parameters_present']:
                row['errors'].append('No enumerated effective EmissiveFactor/EmissiveStrength: native toggle unavailable')
        row['errors'].append('Actual parent graph emissive semantics required; audit cannot authorize an override')
        results.append(row)
    report = {'schema': 'sub01-private-fixture-emission-audit-v1', 'read_only': True, 'level': world.get_path_name(),
              'source': source, 'fixtures': results, 'manifest_errors': manifest_errors,
              'screen_policy': 'PC/TV/phone and untagged materials excluded; no emission inferred from image',
              'native_toggle_available': False}
    Path(output).write_text(json.dumps(report, indent=2)+'\n')
    u.log('SUB01_FIXTURE_EMISSION_AUDIT fixtures=%d read_only=true' % len(results))
    return report
