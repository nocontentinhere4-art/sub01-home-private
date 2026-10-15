"""Expose full source triangles only on newly owned native furniture assets.

Shared imported assets are forbidden. Official set_nanite_settings applies the
owned mesh rebuild; saving completes pending asset compilation. Existing caller
triangle/PBR/placement checks still decide whether the result is acceptable.
"""
OWNED = ('/Game/Sub01Home/RealLinea140/V_', '/Game/Sub01Home/RealEdgeClampLamp/V_',
         '/Game/Sub01Home/RealSteelShelves/V_', '/Game/Sub01Home/RealKitchen/V_')


def prepare(u, mesh, destination):
    if (not isinstance(destination, str) or not destination.startswith(OWNED)
            or not mesh or not mesh.get_path_name().startswith(destination+'/')):
        raise RuntimeError('Full geometry rebuild refused on unowned/shared mesh')
    sub = u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
    settings = sub.get_nanite_settings(mesh)
    if not settings.get_editor_property('enabled'):
        return {'mesh': mesh.get_path_name(), 'nanite_enabled': False, 'rebuilt': False}
    for prop, value in (('enabled', False), ('keep_percent_triangles', 1.),
                        ('trim_relative_error', 0.), ('fallback_percent_triangles', 1.),
                        ('fallback_relative_error', 0.)):
        settings.set_editor_property(prop, value)
    sub.set_nanite_settings(mesh, settings, True)
    if not u.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False):
        raise RuntimeError('Owned full-source mesh rebuild/save failed')
    if sub.get_nanite_settings(mesh).get_editor_property('enabled'):
        raise RuntimeError('Owned mesh still exposes Nanite fallback geometry')
    return {'mesh': mesh.get_path_name(), 'nanite_enabled': False, 'rebuilt': True}
