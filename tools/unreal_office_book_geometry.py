"""Private full-source book meshes; original shared books remain untouched until activation."""
from uuid import uuid4
from unreal_owned_import_cleanup import release_temporary
import hashlib
import json
from pathlib import Path
from home_asset_audit import read_gltf
from real_office_plant import native_geometry_api_audit
import importlib,unreal_owned_mesh_source_geometry
prepare=importlib.reload(unreal_owned_mesh_source_geometry).prepare

SHA='611a3d84885876f5417a4e6b283a940bee24e793bc68b4d9e47e9ed53f62f459'
SOURCE=Path('/workspace/sub01-home-private/out/real-books-complete/real-shelf-books.glb')
DEST='/Game/Sub01Home/RealOfficeBooks/V_611a3d848858_FullSource'


def preflight(u,c,plan,surface,close):
 points,count=surface(u,c);bounds=[[f(p[k]for p in points)for k in range(3)]for f in(min,max)]
 wanted=[[v*100 for v in b]for b in plan['old_bounds_ue_m']]
 if count==plan['actual_source_triangle_count']and all(close(a,b)for a,b in zip(bounds,wanted)):return False
 mesh=c.get_editor_property('static_mesh');audit=native_geometry_api_audit(u,mesh)
 details={'book':plan['id'],'mesh':mesh.get_path_name(),'actual_triangle_count':count,'expected_source_triangle_count':plan['actual_source_triangle_count'],'actual_bounds_cm':bounds,'expected_bounds_cm':wanted,'geometry_api_audit':audit}
 target=Path(u.Paths.project_dir())/'private-audit'/'office-book-native-refusal.json';target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(details,indent=2)+'\n')
 settings=audit.get('nanite_settings',{});apis=audit.get('subsystem_apis',{})
 if settings.get('enabled')is True and settings.get('keep_percent_triangles')==1. and settings.get('trim_relative_error')==0. and apis.get('get_nanite_settings')and apis.get('set_nanite_settings'):return True
 raise RuntimeError('Actual complete book geometry differs source '+plan['id']+'; unreviewed fallback/source state')


def stage(u,books,eas,needed):
 if not needed:return {'destination':None,'replacements':{},'proof':[]}
 from unreal_monitor_support_fix import triangles,native_triangles
 from unreal_import_real_kitchen import same_triangles
 if hashlib.sha256(SOURCE.read_bytes()).hexdigest()!=SHA:raise RuntimeError('Exact complete611 book source required for private rebuild')
 doc,binary=read_gltf(SOURCE);nodes={}
 for i,n in enumerate(doc['nodes']):
  if 'mesh'in n:
   if n.get('name')in nodes:raise RuntimeError('Ambiguous complete source book identity')
   nodes[n.get('name')]=i
 if set(nodes)!={p['id']for a,c,p in books}or len(books)!=46:raise RuntimeError('Exact complete46 source book assembly required')
 dest=DEST+'_'+uuid4().hex
 if u.EditorAssetLibrary.does_directory_exist(dest):raise RuntimeError('Private full-source book version already exists')
 temporary=[];clones={};replacements={};proof=[]
 try:
  for actor,c,p in books:
   original=c.get_editor_property('static_mesh');key=original.get_path_name()
   if key not in clones:
    if len(clones)>=20:raise RuntimeError('Complete provider set exceeds exact20 shared source book meshes')
    name=dest+'/Mesh_'+hashlib.sha256(key.encode()).hexdigest()[:12]
    clone=u.EditorAssetLibrary.duplicate_asset(key,name)
    if not clone or clone.get_path_name().split('.',1)[0]!=name:raise RuntimeError('Exact owned complete book duplication failed')
    prepare(u,clone,dest);clones[key]=clone
   clone=clones[key]
   temp=eas.spawn_actor_from_class(u.StaticMeshActor,u.Vector(0,0,0));temporary.append((temp,None))
   temp.set_actor_label('SUB01_OfficeBook_SourceProof_'+p['id']);temp.set_actor_hidden_in_game(True)
   tc=temp.get_component_by_class(u.StaticMeshComponent);temporary[-1]=(temp,tc);tc.set_static_mesh(clone);tc.set_world_transform(c.get_world_transform(),False,False);tc.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
   for slot,material in enumerate(c.get_materials()):tc.set_material(slot,material)
   wanted=triangles(doc,binary,nodes[p['id']]);actual=native_triangles(u,tc)
   if len(wanted)!=p['actual_source_triangle_count']or not same_triangles(wanted,actual):raise RuntimeError('Owned complete book full source triangles differ '+p['id'])
   if [m.get_path_name()if m else None for m in tc.get_materials()]!=[m.get_path_name()if m else None for m in c.get_materials()]:raise RuntimeError('Owned full-source book material bindings changed')
   replacements[c.get_path_name()]=clone
   proof.append({'book':p['id'],'original_mesh':key,'owned_full_mesh':clone.get_path_name(),'source_triangles':len(wanted),'native_full_triangles':len(actual),'full_world_triangle_tolerance_cm':.02,'nanite_enabled':False})
   release_temporary(eas,temp,tc);temporary.pop();temp=tc=clone=None
  return {'destination':dest,'replacements':replacements,'proof':proof}
 finally:
  try:
   for temp,tc in reversed(temporary):release_temporary(eas,temp,tc)
  finally:
   temporary.clear();temp=tc=clone=None
  # No force-deletion while asynchronous compilation or UObject refs survive.
