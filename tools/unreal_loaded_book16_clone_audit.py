"""Read-only exact failed office38 book16 clone audit; no asset loads or actors."""
import gzip
import hashlib
import json
from pathlib import Path

from home_asset_audit import read_gltf
from real_office_plant import native_geometry_api_audit
from unreal_import_real_kitchen import same_triangles
from unreal_monitor_support_fix import triangles
from unreal_loaded_plant_clone_audit import summary,extract,build_settings

SHA='611a3d84885876f5417a4e6b283a940bee24e793bc68b4d9e47e9ed53f62f459'
DEST='/Game/Sub01Home/RealOfficeBooks/V_611a3d848858_FullSource_465b2897eded4594a1e524a9697b138b'


def run(u=None):
    if u is None:
        import unreal as u
    project=Path(u.Paths.project_dir());out=project/'private-audit';out.mkdir(parents=True,exist_ok=True)
    report={'schema':'sub01.loaded-book16-clone-audit.v1','read_only':True,'source_sha256':SHA,
            'book':'SUB01_RealBook_16','assets_loaded':False,'scene_mutations':0}
    target=out/'office-book16-clone-audit.json'
    actors=list(u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors())
    found=[a for a in actors if a.get_actor_label()=='SUB01_RealBook_16']
    if len(found)!=1:raise RuntimeError('Exact original book16 actor is not unique')
    cs=found[0].get_components_by_class(u.StaticMeshComponent)
    if len(cs)!=1:raise RuntimeError('Original book16 component count differs')
    c=cs[0];original=c.get_editor_property('static_mesh');key=original.get_path_name()
    if not key.startswith('/Game/Sub01Home/RealBooks/V_611a3d848858/'):
        raise RuntimeError('Original complete611 book16 binding differs')
    name='Mesh_'+hashlib.sha256(key.encode()).hexdigest()[:12]
    exact=DEST+'/'+name+'.'+name;report['exact_clone']=exact
    clone=u.find_object(None,exact)
    if clone is None:
        report.update({'available':False,'reason':'Exact quarantined book clone is not loaded; no load attempted'})
        target.write_text(json.dumps(report,indent=2)+'\n');raise RuntimeError(report['reason'])
    if clone.get_path_name()!=exact:raise RuntimeError('Loaded book clone identity differs')
    source=Path('/workspace/sub01-home-private/out/real-books-complete/real-shelf-books.glb')
    if hashlib.sha256(source.read_bytes()).hexdigest()!=SHA:raise RuntimeError('Complete source611 bytes differ')
    doc,binary=read_gltf(source)
    nodes=[i for i,n in enumerate(doc['nodes'])if n.get('name')=='SUB01_RealBook_16'and 'mesh'in n]
    if len(nodes)!=1:raise RuntimeError('Complete source book16 is not unique')
    wanted=triangles(doc,binary,nodes[0]);actual,sections=extract(u,clone,c.get_world_transform())
    old,old_sections=extract(u,original,c.get_world_transform())
    report.update({'available':True,'source_node':nodes[0],'source':summary(wanted),'actual_full_clone':summary(actual),
                   'original_cpu':summary(old),'same_world_triangles':same_triangles(wanted,actual),
                   'full_world_triangle_tolerance_cm':.02,'clone_sections':sections,'original_sections':old_sections,
                   'component_world_transform':str(c.get_world_transform()),'original_mesh':key,
                   'original_geometry_api_audit':native_geometry_api_audit(u,original),
                   'clone_geometry_api_audit':native_geometry_api_audit(u,clone),'clone_build_settings':build_settings(u,clone),
                   'original_build_settings':build_settings(u,original),
                   'original_material_bindings':[m.get_path_name()if m else None for m in c.get_materials()]})
    payload=json.dumps({'source_world_triangles_cm':wanted,'clone_world_triangles_cm':actual},separators=(',',':')).encode()
    blob=out/'office-book16-world-triangles.json.gz';blob.write_bytes(gzip.compress(payload,compresslevel=1))
    report['exact_triangle_data']={'path':str(blob),'sha256':hashlib.sha256(blob.read_bytes()).hexdigest(),'bytes':blob.stat().st_size}
    target.write_text(json.dumps(report,indent=2)+'\n');return report
