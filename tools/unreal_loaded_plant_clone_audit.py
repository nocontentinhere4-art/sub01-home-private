"""Read-only audit of the exact failed rev26 plant222 clone; never load assets."""
import gzip
import hashlib
import json
import math
from pathlib import Path

from home_asset_audit import read_gltf
from real_office_plant import native_geometry_api_audit
from unreal_import_real_kitchen import same_triangles
from unreal_monitor_support_fix import triangles

SHA = '9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
CLONE = '/Game/Sub01Home/RealOfficePlant/V_9556495fa816_d0c423ec33f54fa8bcd3d96e6ece451a_FullSource/SourceNode222.SourceNode222'
ORIGINAL = '/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Mesh_163.Mesh_163'


def summary(rows):
    points = [p for t in rows for p in t]
    if any(len(t) != 3 for t in rows) or any(len(p) != 3 or not all(math.isfinite(v) for v in p) for p in points):
        raise RuntimeError('Nonfinite/incomplete diagnostic triangles')
    degenerate, minimum = [], None
    for i, t in enumerate(rows):
        a, b = [[t[n][k]-t[0][k] for k in range(3)] for n in (1, 2)]
        cross = [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
        area_squared = sum(v*v for v in cross)/4
        minimum = area_squared if minimum is None else min(minimum, area_squared)
        if area_squared == 0:
            degenerate.append(i)
    return {'triangles': len(rows), 'world_bounds_cm': [[f(p[k] for p in points) for k in range(3)] for f in (min,max)] if points else None,
            'exact_zero_area_triangle_count': len(degenerate), 'first_zero_area_triangle_indices': degenerate[:16],
            'minimum_area_squared_cm4': minimum}


def extract(u, mesh, world):
    rows, sections = [], []
    for section in range(mesh.get_num_sections(0)):
        verts, ids, *_ = u.ProceduralMeshLibrary.get_section_from_static_mesh(mesh, 0, section)
        if len(ids) % 3:
            raise RuntimeError('Partial native diagnostic triangle')
        pts = [world.transform_location(p) for p in verts]
        pts = [[float(p.x),float(p.y),float(p.z)] for p in pts]
        rows.extend([[pts[k] for k in ids[i:i+3]] for i in range(0,len(ids),3)])
        sections.append({'section':section,'vertices':len(verts),'triangles':len(ids)//3})
    return rows, sections


def build_settings(u, mesh):
    result = {}
    sub = u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
    if not hasattr(sub,'get_lod_build_settings'):
        return {'available':False}
    try:
        settings = sub.get_lod_build_settings(mesh,0)
        for prop in ('remove_degenerates','build_reversed_index_buffer','recompute_normals','recompute_tangents','use_full_precision_u_vs'):
            try:result[prop] = settings.get_editor_property(prop)
            except Exception as error:result[prop+'_unavailable'] = str(error)
    except Exception as error:result['unavailable'] = str(error)
    return result


def run(u=None):
    if u is None:
        import unreal as u
    project=Path(u.Paths.project_dir());out=project/'private-audit';out.mkdir(parents=True,exist_ok=True)
    report={'schema':'sub01.loaded-plant-clone-audit.v1','read_only':True,'source_sha256':SHA,'source_node':222,
            'exact_clone':CLONE,'assets_loaded':False,'scene_mutations':0}
    target=out/'office-plant222-clone-audit.json'
    clone=u.find_object(None,CLONE)
    if clone is None:
        report.update({'available':False,'reason':'Exact quarantined clone is not loaded; no load attempted'})
        target.write_text(json.dumps(report,indent=2)+'\n')
        raise RuntimeError(report['reason'])
    if clone.get_path_name()!=CLONE:
        raise RuntimeError('Loaded clone identity differs')
    actors=list(u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors())
    found=[a for a in actors if a.get_name()=='full-home_node_222']
    if len(found)!=1:raise RuntimeError('Exact original222 actor is not unique')
    cs=found[0].get_components_by_class(u.StaticMeshComponent)
    if len(cs)!=1 or cs[0].get_editor_property('static_mesh').get_path_name()!=ORIGINAL:
        raise RuntimeError('Original222 source binding changed')
    c=cs[0];source=project/'SourceAssets/full-home.glb'
    if hashlib.sha256(source.read_bytes()).hexdigest()!=SHA:raise RuntimeError('Source955 bytes differ')
    doc,binary=read_gltf(source);wanted=triangles(doc,binary,222)
    actual,sections=extract(u,clone,c.get_world_transform())
    original,original_sections=extract(u,c.get_editor_property('static_mesh'),c.get_world_transform())
    report.update({'available':True,'source':summary(wanted),'actual_full_clone':summary(actual),'original_cpu':summary(original),
                   'same_world_triangles':same_triangles(wanted,actual),'full_world_triangle_tolerance_cm':.02,
                   'clone_sections':sections,'original_sections':original_sections,'component_world_transform':str(c.get_world_transform()),
                   'original_geometry_api_audit':native_geometry_api_audit(u,c.get_editor_property('static_mesh')),
                   'clone_geometry_api_audit':native_geometry_api_audit(u,clone),'clone_build_settings':build_settings(u,clone),
                   'original_build_settings':build_settings(u,c.get_editor_property('static_mesh')),
                   'original_material_bindings':[m.get_path_name()if m else None for m in c.get_materials()]})
    # Preserve exact world data for diagnosis without another native import.
    payload=json.dumps({'source_world_triangles_cm':wanted,'clone_world_triangles_cm':actual},separators=(',',':')).encode()
    blob=out/'office-plant222-world-triangles.json.gz'
    blob.write_bytes(gzip.compress(payload,compresslevel=1))
    report['exact_triangle_data']={'path':str(blob),'sha256':hashlib.sha256(blob.read_bytes()).hexdigest(),'bytes':blob.stat().st_size}
    target.write_text(json.dumps(report,indent=2)+'\n')
    return report
