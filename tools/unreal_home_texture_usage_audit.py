"""Read-only texture role/settings audit in the already-loaded actual home.

Sole editor owner calls ``run('/absolute/path/report.json')``. This never loads a
map, changes assets, saves packages or quits the editor. Only effective
BaseColorTexture/NormalTexture parameters on bound MaterialInstances are audited.
An albedo using TC_NORMALMAP is a definite *binding/settings* mismatch, not proof
that its source pixels are albedo. Linear albedo alone needs source parity before
any repair. Shared albedo/normal roles are ambiguous and require inspection.
"""
import argparse
import datetime
import json
from pathlib import Path

LEVEL = '/Game/Sub01Home/ActualHome'
ROLES = {'BaseColorTexture': 'albedo', 'NormalTexture': 'normal'}


def enum_name(value):
    return str(value).strip('<>').split(':', 1)[0].rsplit('.', 1)[-1].strip()


def classify(usages, srgb, compression):
    """Classify observed settings without inferring source pixel semantics."""
    roles = {usage['role'] for usage in usages}
    mismatches, warnings = [], []
    compression = enum_name(compression)
    if 'albedo' in roles and compression == 'TC_NORMALMAP':
        mismatches.append('normalmap_compression_used_as_albedo')
    if roles == {'albedo', 'normal'}:
        warnings.append('ambiguous_albedo_normal_role_conflict')
    if 'albedo' in roles and srgb is False:
        warnings.append('linear_albedo_requires_source_parity')
    if 'normal' in roles and srgb is True:
        warnings.append('normal_binding_uses_srgb_requires_source_inspection')
    return {'definite_binding_settings_mismatches': mismatches, 'warnings': warnings}


def run(output, *, u=None):
    if u is None:
        import unreal as u
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if world is None or world.get_path_name().split('.', 1)[0] != LEVEL:
        raise RuntimeError('Actual private home must already be loaded by editor owner')
    materials, textures, errors, skipped = {}, {}, [], set()
    bindings = {}
    actors = u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()
    for actor in actors:
        for component in actor.get_components_by_class(u.MeshComponent):
            for slot, material in enumerate(component.get_materials()):
                if material is None:
                    continue
                path = material.get_path_name()
                if not isinstance(material, u.MaterialInstance):
                    skipped.add(path)
                    continue
                materials[path] = material
                binding = {'actor': actor.get_actor_label(), 'component': component.get_path_name(), 'slot': slot}
                bindings.setdefault(path, []).append(binding)
    library = u.MaterialEditingLibrary
    for path, material in sorted(materials.items()):
        try:
            names = {str(name): name for name in library.get_texture_parameter_names(material)}
        except Exception as error:
            errors.append({'material': path, 'operation': 'parameter_names', 'error': str(error)})
            continue
        for parameter, role in ROLES.items():
            if parameter not in names:
                continue
            try:
                texture = library.get_material_instance_texture_parameter_value(material, names[parameter])
                if texture is None:
                    continue
                texture_path = texture.get_path_name()
                if not isinstance(texture, u.Texture2D):
                    errors.append({'material': path, 'parameter': parameter, 'texture': texture_path,
                                   'error': 'Effective texture is not Texture2D'})
                    continue
                if texture_path not in textures:
                    row = {'asset_path': texture_path, 'usages': [], 'settings_errors': []}
                    for prop in ('srgb', 'compression_settings'):
                        try:
                            value = texture.get_editor_property(prop)
                            row[prop] = bool(value) if prop == 'srgb' else enum_name(value)
                        except Exception as error:
                            row[prop] = None
                            row['settings_errors'].append({'property': prop, 'error': str(error)})
                    textures[texture_path] = row
                textures[texture_path]['usages'].append({'material': path, 'parameter': parameter,
                                                       'role': role, 'bindings': bindings[path]})
            except Exception as error:
                errors.append({'material': path, 'parameter': parameter, 'error': str(error)})
    rows = [textures[path] for path in sorted(textures)]
    for row in rows:
        row.update(classify(row['usages'], row['srgb'], row['compression_settings']))
    report = {'schema': 'sub01-private-texture-usage-audit-v1', 'read_only': True,
              'generated_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'level': world.get_path_name(), 'parameters_audited': ROLES,
              'material_instance_count': len(materials), 'textures': rows,
              'skipped_non_instance_materials': sorted(skipped), 'errors': errors,
              'complete_for_declared_scope': not errors and all(not row['settings_errors'] for row in rows),
              'summary': {'texture_count': len(rows),
                          'definite_mismatch_texture_count': sum(bool(row['definite_binding_settings_mismatches']) for row in rows),
                          'warning_texture_count': sum(bool(row['warnings']) for row in rows)}}
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + '\n')
    u.log('SUB01_TEXTURE_USAGE_AUDIT ' + json.dumps(report['summary']))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    run(parser.parse_args().output)
