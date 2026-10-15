"""Read already-loaded architecture settings; never build/save/change the world.

A low card budget on a complex batch is a hypothesis, not proof of missing
runtime Surface Cache coverage. This audit deliberately keeps those distinct.
"""
import json
from pathlib import Path


def run():
    import unreal as u
    from unreal_import_reference_dressing import fingerprint

    project=Path(u.Paths.project_dir())
    if project.resolve()!=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab'):
        raise RuntimeError('Actual private project required')
    world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if not world or '/Game/Sub01Home/ActualHome.' not in world.get_path_name():
        raise RuntimeError('Already-loaded actual private home required')
    actors=list(u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors())
    before=fingerprint(u,actors)
    found=[a for a in actors if a.get_name()=='full-home_node_158']
    if len(found)!=1:raise RuntimeError('Exact architecture158 must be unique')
    components=found[0].get_components_by_class(u.StaticMeshComponent)
    if len(components)!=1:raise RuntimeError('Exact architecture component required')
    mesh=components[0].get_editor_property('static_mesh')
    if not mesh or not mesh.get_path_name().startswith('/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/'):
        raise RuntimeError('Original loaded architecture mesh required')
    report={'schema':'sub01.architecture-lumen-source-audit.v1','read_only':True,
            'actor':found[0].get_path_name(),'mesh':mesh.get_path_name(),
            'editor_world':world.get_path_name(),'build_settings':{},'mesh_settings':{},
            'unavailable':{},'users':[],'surface_cache_coverage_visualized':False,
            'missing_runtime_cards_confirmed':False,'scene_mutations':0}
    sub=u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
    try:
        settings=sub.get_lod_build_settings(mesh,0)
        for key in ('max_lumen_mesh_cards','generate_distance_field_as_if_two_sided',
                    'distance_field_resolution_scale','distance_field_replacement_mesh'):
            try:
                value=settings.get_editor_property(key)
                report['build_settings'][key]=value.get_path_name()if hasattr(value,'get_path_name')else value
            except Exception as exc:report['unavailable']['build.'+key]=str(exc)
    except Exception as exc:report['unavailable']['build_settings']=str(exc)
    for key in ('support_ray_tracing','allow_cpu_access','generate_mesh_distance_field'):
        try:report['mesh_settings'][key]=mesh.get_editor_property(key)
        except Exception as exc:report['unavailable']['mesh.'+key]=str(exc)
    try:report['mesh_settings']['nanite_enabled']=mesh.get_editor_property('nanite_settings').get_editor_property('enabled')
    except Exception as exc:report['unavailable']['nanite_enabled']=str(exc)
    for actor in actors:
        for component in actor.get_components_by_class(u.StaticMeshComponent):
            if component.get_editor_property('static_mesh')!=mesh:continue
            centre,extent,radius=u.SystemLibrary.get_component_bounds(component)
            report['users'].append({'actor':actor.get_path_name(),'component':component.get_path_name(),
                'world_centre_cm':[centre.x,centre.y,centre.z],
                'world_extent_cm':[extent.x,extent.y,extent.z],
                'materials':[m.get_path_name()if m else None for m in component.get_materials()],
                'visible':bool(component.is_visible())})
    after=fingerprint(u,list(u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()))
    if after!=before:raise RuntimeError('Read-only architecture audit observed changed scene fingerprints')
    report['original_actor_fingerprints_unchanged']=True
    output=project/'private-audit/architecture158-lumen-source-audit.json'
    output.parent.mkdir(exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n')
    u.log('SUB01_ARCHITECTURE_LUMEN_READ_ONLY '+json.dumps(report))
    return report
