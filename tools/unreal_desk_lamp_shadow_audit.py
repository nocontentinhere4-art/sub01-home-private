"""Read only the actual saved desk fixture and paired light; no lighting edits."""
import json
from pathlib import Path


def run():
    import unreal as u
    from unreal_import_reference_dressing import fingerprint
    project=Path(u.Paths.project_dir())
    if project.resolve()!=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab'):
        raise RuntimeError('Exact actual private project required')
    world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if not world or world.get_path_name().split('.',1)[0]!='/Game/Sub01Home/ActualHome':
        raise RuntimeError('Already-loaded ActualHome required')
    mount=json.loads(Path('/workspace/sub01-home-private/out/real-office-bundle/desk.json').read_text())['lamp_mount']
    actors=list(u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors())
    before=fingerprint(u,actors)
    lamps=[a for a in actors if a.get_path_name()==mount['actual_saved_lamp_actor']]
    lights=[a for a in actors if a.get_actor_label()==mount['light_actor_label_for_exact_component_preflight']]
    if len(lamps)!=1 or len(lights)!=1:raise RuntimeError('Exact saved fixture/light pair required')
    report={'schema':'sub01.actual-desk-lamp-shadow-audit.v1','read_only':True,'scene_mutations':0,
            'fixture':lamps[0].get_path_name(),'light':lights[0].get_path_name(),
            'physical_shielding_verified':False,'components':[],'unavailable':{}}
    def properties(obj,keys):
        values={}
        for key in keys:
            try:
                v=obj.get_editor_property(key)
                if hasattr(v,'get_path_name'):v=v.get_path_name()
                elif not isinstance(v,(str,bool,int,float,type(None))):v=str(v)
                values[key]=v
            except Exception as exc:report['unavailable'][(obj.get_path_name()if hasattr(obj,'get_path_name')else type(obj).__name__)+':'+key]=str(exc)
        return values
    for actor,kind,cls in ((lamps[0],'fixture',u.StaticMeshComponent),(lights[0],'light',u.LightComponent)):
        for c in actor.get_components_by_class(cls):
            p=c.get_world_location()
            row={'kind':kind,'component':c.get_path_name(),'world_location_cm':[p.x,p.y,p.z],
                 'properties':properties(c,('cast_shadow','cast_dynamic_shadow','cast_static_shadow','cast_shadow_as_two_sided',
                   'cast_shadows','cast_dynamic_shadows','cast_static_shadows',
                   'affect_dynamic_indirect_lighting','affect_distance_field_lighting','visible_in_ray_tracing',
                   'intensity','intensity_units','attenuation_radius','use_inverse_squared_falloff',
                   'source_radius','soft_source_radius','source_length','indirect_lighting_intensity'))}
            if kind=='fixture':
                row['mesh']=c.get_editor_property('static_mesh').get_path_name();row['materials']=[]
                for m in c.get_materials():
                    chain=[];seen=set()
                    while m and m.get_path_name()not in seen:
                        seen.add(m.get_path_name());entry={'path':m.get_path_name(),
                          'properties':properties(m,('two_sided','blend_mode','shading_model','cast_ray_traced_shadows'))}
                        if isinstance(m,u.MaterialInstanceConstant):
                            try:entry['base_property_overrides']=properties(m.get_editor_property('base_property_overrides'),('override_two_sided','two_sided','override_blend_mode','blend_mode'))
                            except Exception as exc:entry['base_property_override_unavailable']=str(exc)
                        chain.append(entry)
                        try:m=m.get_editor_property('parent')
                        except Exception:break
                    row['materials'].append(chain)
            report['components'].append(row)
    if fingerprint(u,list(u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()))!=before:
        raise RuntimeError('Read-only lamp audit observed changed scene fingerprints')
    report['original_actor_fingerprints_unchanged']=True
    out=project/'private-audit/actual-desk-lamp-shadow-audit.json';out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report,indent=2)+'\n')
    return report
