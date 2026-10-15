"""Read only the exact imported physical controller before a scoped shader fix."""
import hashlib
import json
import time
from pathlib import Path

MESH='/Game/Sub01Home/Devices/Controller/V_8134769e2680/controller-normalized-source/StaticMeshes/controller.controller'
MATERIAL='/Game/Sub01Home/Devices/Controller/V_8134769e2680/controller-normalized-source/Materials/controller.controller'


def run():
    import unreal as u
    from unreal_import_reference_dressing import fingerprint
    project=Path(u.Paths.project_dir());audit=project/'private-audit';audit.mkdir(exist_ok=True)
    world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if not world or world.get_path_name().split('.',1)[0]!='/Game/Sub01Home/ActualHome':raise RuntimeError('Actual private Editor world required')
    actors=list(u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors());before=fingerprint(u,actors)
    receipt=json.loads((audit/'native-controller-asset.json').read_text())
    if receipt['physical_assembly']['mesh']!=MESH:raise RuntimeError('Exact physical controller receipt differs')
    mesh=u.load_asset(MESH)
    if not mesh or mesh.get_path_name()!=MESH:raise RuntimeError('Exact owned controller asset unavailable')
    sub=u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
    settings=sub.get_nanite_settings(mesh)
    nanite={k:settings.get_editor_property(k)for k in ('enabled','keep_percent_triangles','trim_relative_error','fallback_percent_triangles','fallback_relative_error')}
    materials=[]
    for slot in mesh.get_editor_property('static_materials'):
        mat=slot.get_editor_property('material_interface');chain=[];seen=set()
        while mat:
            path=mat.get_path_name()
            if path in seen:raise RuntimeError('Material parent cycle')
            seen.add(path);row={'path':path,'class':mat.get_class().get_name()}
            for key in ('used_with_nanite','two_sided','blend_mode'):
                try:row[key]=str(mat.get_editor_property(key))
                except Exception:pass
            chain.append(row)
            try:mat=mat.get_editor_property('parent')
            except Exception:break
        materials.append({'slot':str(slot.get_editor_property('material_slot_name')),'chain':chain})
    sections=[];points=[];uv_channels=[]
    for i in range(mesh.get_num_sections(0)):
        v,ids,normals,uv,tangents=u.ProceduralMeshLibrary.get_section_from_static_mesh(mesh,0,i)
        if len(ids)%3:raise RuntimeError('Partial controller render triangle')
        points.extend([[float(p.x),float(p.y),float(p.z)]for p in v])
        sections.append({'section':i,'vertices':len(v),'triangles':len(ids)//3,'uv0_values':len(uv),'uv0_sha256':hashlib.sha256(json.dumps([[float(p.x),float(p.y)]for p in uv],separators=(',',':')).encode()).hexdigest()})
    builds={}
    try:
        b=sub.get_lod_build_settings(mesh,0)
        for k in ('remove_degenerates','recompute_normals','recompute_tangents','use_full_precision_u_vs'):builds[k]=b.get_editor_property(k)
    except Exception as error:builds={'error':str(error)}
    if fingerprint(u,actors)!=before:raise RuntimeError('Read-only controller audit changed protected actors')
    result={'schema':'sub01.actual-controller-material-audit.v1','captured_epoch':time.time(),'mesh':MESH,'source_receipt':receipt['physical_assembly'],'nanite':nanite,'materials':materials,'sections':sections,'native_cpu_triangles':sum(s['triangles']for s in sections),'native_local_bounds_cm':[[fn(p[k]for p in points)for k in range(3)]for fn in (min,max)]if points else None,'lod_build_settings':builds,'actors_unchanged':True,'asset_or_world_setters_used':False,'visual_accepted':False}
    (audit/'controller-material-native-audit.json').write_text(json.dumps(result,indent=2)+'\n');return result
