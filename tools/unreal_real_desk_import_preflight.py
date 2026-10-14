"""Read-only native prerequisites for genuine LINEA140 import; no runtime edits.

Sole Editor owner may run audit(export_path). Activation is deliberately refused
until actual completed Blender export and exact paired lamp binding are reviewed.
No Interchange import, actor hide, transform change, material write or level load.
"""
import hashlib,json,math
from pathlib import Path
from unreal_import_reference_dressing import fingerprint
SOURCE_SHA='99bdf3fd42eea5fc4cb2fadd52c8cae18c4459a94000b85f7df4c515234ba43d'
DEVICES=(73,74,75,132,133,134,135,136,184,185,186,187,236,237,238)


def validate_export(source,report):
    if report.get('schema')!='sub01.real-linea140-placement-export.v1':raise ValueError('Actual Blender desk export receipt missing')
    if report.get('source_sha256')!=SOURCE_SHA or hashlib.sha256(Path(source).read_bytes()).hexdigest()!=report.get('output_sha256'):raise ValueError('Actual completed export bytes differ')
    if report.get('source_triangle_count')!=20024 or not all(report.get(k) is True for k in ('all60_source_primitives_preserved','all7_materials_6_embedded_images_binary_exact','source_binary_unchanged')):raise ValueError('Complete original geometry/PBR proof unavailable')
    if report.get('hide_only_source_actor_nodes')!=[181,182] or report.get('lamp_delta_ue_cm')!=[45,0,0]:raise ValueError('Unreviewed scope or lamp delta')
    margins=report.get('device_xy_support_margins_m',{})
    if set(margins)!={'monitor','keyboard','mouse','phone'} or not all(isinstance(v,(int,float)) and math.isfinite(v) and v>0 for v in margins.values()):raise ValueError('Actual exported device support proof unavailable')
    return True


def audit(export_path,output_path=None,u=None):
    if u is None:import unreal as u
    export_path=Path(export_path);gaps=[]
    try:report=json.loads(export_path.with_suffix('.json').read_text());validate_export(export_path,report)
    except (OSError,ValueError,KeyError) as exc:gaps.append('Completed source export unavailable: '+str(exc))
    world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if not world or world.get_path_name().split('.',1)[0]!='/Game/Sub01Home/ActualHome':raise RuntimeError('Sole owner must already have actual ActualHome loaded; no level load allowed')
    actors=list(u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors());targets=[]
    for node in (181,182,*DEVICES):
        found=[a for a in actors if a.get_name()==f'full-home_node_{node}']
        if len(found)!=1:gaps.append(f'Actual source actor {node} not uniquely present')
        else:targets.extend(found)
    # Labels select diagnostic candidates only. They are not trusted mutation identity.
    lamps=[a for a in actors if a.get_actor_label() in ('SUB01_RealLamp_DeskLamp','SUB01_AuthoredLight_DeskLamp')]
    rows=[]
    for actor in targets+lamps:
        centre,extent=actor.get_actor_bounds(False)
        row={'actor_path':actor.get_path_name(),'label':actor.get_actor_label(),'bounds_center_cm':[centre.x,centre.y,centre.z],'bounds_extent_cm':[extent.x,extent.y,extent.z],'light_components':[]}
        for c in actor.get_components_by_class(u.LightComponent):
            row['light_components'].append({'path':c.get_path_name(),'intensity':c.get_editor_property('intensity'),'world_location_cm':[c.get_world_location().x,c.get_world_location().y,c.get_world_location().z]})
        rows.append(row)
    gaps.extend(['Reviewed exact DeskLamp actor/component mesh asset identity, authored light component path and saved original transforms are unavailable; label matches are diagnostic only.','Actual new lamp foot vertices, shade extrema, bulb/light pairing and support margin after +45cm X must be measured and reviewed.','Actual native top84.5cm at floor2.5cm and all device foot contacts, source/native screen bindings, approved chair knee clearance must be measured.','Candidate material-instance actual parameters/parents and complete seven-material texture role/sRGB/compression receipts must be reviewed before hiding old desk.','New Interchange scene node/mesh UID names must ALL be unique to this desk version; a unique asset destination or root node alone is insufficient.'])
    result={'schema':'sub01.real-desk-import-prerequisite-audit.v1','source_sha256':SOURCE_SHA,'read_only':True,'import_ready':False,'activation_allowed':False,'prerequisite_gaps':gaps,'actual_bindings':fingerprint(u,targets+lamps),'actual_bounds_and_lights':rows,'protected_source_device_nodes':list(DEVICES),'proposed_old_desk_hide_nodes':[181,182],'lamp_delta_ue_cm':[45,0,0],'native_mutations_performed':0}
    if output_path:Path(output_path).write_text(json.dumps(result,indent=2)+'\n')
    return result


def activate(*args,**kwargs):
    raise RuntimeError('REFUSED: real desk activation has no reviewed actual lamp pairing, PBR, device contact and completed source export proof. Read-only audit only.')
