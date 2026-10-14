"""Remove one proven duplicate owned HDR sky, retaining a recoverable map copy."""
import json
import shutil
import time
from pathlib import Path

LABEL = 'SUB01_ActualHDR_Sky'
LEVEL = '/Game/Sub01Home/ActualHome'


def run():
    import unreal as u

    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    level = u.get_editor_subsystem(u.LevelEditorSubsystem)
    if not actors or not level or not level.load_level(LEVEL):
        raise RuntimeError('Real initialized editor required')
    skies = sorted([a for a in actors.get_all_level_actors() if a.get_actor_label() == LABEL],
                   key=lambda a: a.get_path_name())
    if len(skies) != 2 or any(not isinstance(a, u.SkyLight) for a in skies):
        raise RuntimeError('Expected exactly two measured owned SkyLights')
    def evidence(actor):
        c = actor.get_component_by_class(u.SkyLightComponent)
        if not c:
            raise RuntimeError('Actual SkyLightComponent absent')
        cube = c.get_editor_property('cubemap')
        if not cube or c.get_editor_property('source_type') != u.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP:
            raise RuntimeError('Actual authored HDR cubemap is required')
        location = actor.get_actor_location()
        rotation = actor.get_actor_rotation()
        scale = actor.get_actor_scale3d()
        color = c.get_editor_property('light_color')
        lower = c.get_editor_property('lower_hemisphere_color')
        return {'cubemap': cube.get_path_name(), 'source_type': str(c.get_editor_property('source_type')),
                'source_cubemap_angle': float(c.get_editor_property('source_cubemap_angle')),
                'intensity': float(c.get_editor_property('intensity')),
                'mobility': str(c.get_editor_property('mobility')),
                'visible': bool(c.is_visible()), 'cast_shadows': bool(c.get_editor_property('cast_shadows')),
                'real_time_capture': bool(c.get_editor_property('real_time_capture')),
                'lower_hemisphere_is_solid_color': bool(c.get_editor_property('lower_hemisphere_is_solid_color')),
                'light_color': [color.r, color.g, color.b, color.a],
                'lower_hemisphere_color': [lower.r, lower.g, lower.b, lower.a],
                'location': [location.x, location.y, location.z],
                'rotation': [rotation.pitch, rotation.yaw, rotation.roll],
                'scale': [scale.x, scale.y, scale.z]}
    measured = [evidence(a) for a in skies]
    if measured[0] != measured[1]:
        raise RuntimeError('Owned skies differ; inspect actual evidence rather than choosing blindly: ' + json.dumps(measured))
    root = Path(u.Paths.project_dir())
    map_file = root / 'Content/Sub01Home/ActualHome.umap'
    if not map_file.is_file():
        raise RuntimeError('Actual saved map missing; no recoverable deletion')
    backup = root / 'Saved/PrivateMapBackups' / str(time.time_ns())
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(map_file, backup / map_file.name)
    for folder in ('__ExternalActors__', '__ExternalObjects__'):
        path = root / 'Content' / folder / 'Sub01Home/ActualHome'
        if path.exists():
            shutil.copytree(path, backup / folder)
    retained, duplicate = skies
    removed_path = duplicate.get_path_name()
    if not actors.destroy_actor(duplicate):
        raise RuntimeError('Actual duplicate could not be removed')
    if evidence(retained) != measured[0]:
        raise RuntimeError('Retained light changed; map not saved')
    remaining = [a for a in actors.get_all_level_actors() if a.get_actor_label() == LABEL]
    if len(remaining) != 1 or remaining[0].get_path_name() != retained.get_path_name():
        raise RuntimeError('Actual retained sky is not unique; map not saved')
    if not level.save_current_level():
        raise RuntimeError('Corrected map failed to save; backup retained')
    report = {'schema': 'sub01.private-duplicate-sky-correction.v1', 'retained': retained.get_path_name(),
              'removed_duplicate': removed_path, 'matching_actual_properties': measured[0],
              'recoverable_backup': str(backup), 'native_daylight_verified': False}
    (root / 'private-sky-correction.json').write_text(json.dumps(report, indent=2) + '\n')
    u.log('SUB01_PRIVATE_SKY_DUPLICATE_CORRECTED ' + json.dumps(report))
    return report


if __name__ == '__main__':
    try:
        run()
    finally:
        import unreal
        unreal.SystemLibrary.quit_editor()
