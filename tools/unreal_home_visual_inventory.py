"""Read-only inventory of the actual private home's material and lighting bindings.

Execute through the sole editor owner; no save, import, shader edits or poses.
The report contains asset paths and settings only, never credentials.
"""
import json
from pathlib import Path

LEVEL = '/Game/Sub01Home/ActualHome'


def run(output):
    import unreal as u
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if world is None or LEVEL not in world.get_path_name():
        raise RuntimeError('Actual private home must already be loaded by editor owner')
    actors = u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()
    library = u.MaterialEditingLibrary
    materials = {}
    bindings, lights, post = [], [], []
    for actor in actors:
        label = actor.get_actor_label()
        for component in actor.get_components_by_class(u.StaticMeshComponent):
            mesh = component.get_editor_property('static_mesh')
            for slot, material in enumerate(component.get_materials()):
                if material is None:
                    continue
                path = material.get_path_name()
                bindings.append({'actor': label, 'component': component.get_path_name(),
                                 'mesh': mesh.get_path_name() if mesh else None,
                                 'slot': slot, 'material': path})
                if path in materials:
                    continue
                row = {'class': material.get_class().get_name(), 'parameters': {}, 'errors': []}
                if isinstance(material, u.MaterialInstanceConstant):
                    parent = material.get_editor_property('parent')
                    row['parent'] = parent.get_path_name() if parent else None
                    for kind in ('texture', 'scalar', 'vector'):
                        try:
                            names = getattr(library, 'get_' + kind + '_parameter_names')(material)
                            values = {}
                            for name in names:
                                value = getattr(library, 'get_material_instance_' + kind + '_parameter_value')(material, name)
                                if kind == 'texture':
                                    value = value.get_path_name() if value else None
                                elif kind == 'vector':
                                    value = [float(getattr(value, channel)) for channel in ('r', 'g', 'b', 'a')]
                                else:
                                    value = float(value)
                                values[str(name)] = value
                            row['parameters'][kind] = values
                        except Exception as error:
                            row['errors'].append(kind + ':' + type(error).__name__)
                materials[path] = row
        for component in actor.get_components_by_class(u.LightComponent):
            row = {'actor': label, 'class': component.get_class().get_name()}
            for name in ('intensity', 'light_color', 'temperature', 'use_temperature', 'intensity_units'):
                try:
                    value = component.get_editor_property(name)
                    row[name] = value if isinstance(value, (bool, int, float, str)) else str(value)
                except Exception:
                    pass
            lights.append(row)
        if isinstance(actor, u.PostProcessVolume):
            settings = actor.get_editor_property('settings')
            row = {'actor': label}
            for name in ('auto_exposure_method', 'auto_exposure_min_brightness', 'auto_exposure_max_brightness',
                         'auto_exposure_bias', 'white_temp', 'white_tint', 'color_saturation'):
                try:
                    value = settings.get_editor_property(name)
                    row[name] = value if isinstance(value, (bool, int, float, str)) else str(value)
                    row['override_' + name] = settings.get_editor_property('override_' + name)
                except Exception:
                    pass
            post.append(row)
    report = {'schema': 'sub01-private-actual-visual-inventory-v1', 'level': world.get_path_name(),
              'read_only': True, 'bindings': bindings, 'materials': materials,
              'lights': lights, 'post_processing': post}
    Path(output).write_text(json.dumps(report, indent=2) + '\n')
    u.log('SUB01_VISUAL_INVENTORY bindings=%d materials=%d lights=%d' % (len(bindings), len(materials), len(lights)))
    return report
