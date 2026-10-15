"""Restore exact retained sink geometry on an owned copy within kitchen activation."""
import hashlib
from pathlib import Path
from home_asset_audit import read_gltf
from unreal_owned_mesh_source_geometry import prepare

DEST='/Game/Sub01Home/RealKitchen/V_9556495fa816_RetainedSink164'


def stage(u,actors,retained,source,eas):
 pending=[r for r in retained if not r.get('source_geometry_verified',True)]
 if not pending:return {'destination':None,'replacements':[],'proof':[]}
 if [r['node']for r in pending]!=[164]:raise RuntimeError('Only actually audited source164 Nanite fallback may rebuild')
 if hashlib.sha256(Path(source).read_bytes()).hexdigest()!='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b':raise RuntimeError('Exact source955 required for retained sink rebuild')
 from unreal_monitor_support_fix import triangles,native_triangles
 from unreal_import_real_kitchen import same_triangles
 if u.EditorAssetLibrary.does_directory_exist(DEST):raise RuntimeError('Owned retained sink version exists; inspect prior transaction')
 row=pending[0];a=[a for a in actors if a.get_name()=='full-home_node_164']
 if len(a)!=1:raise RuntimeError('Exact retained source164 actor unavailable')
 actor=a[0];cs=actor.get_components_by_class(u.StaticMeshComponent)
 if len(cs)!=1 or cs[0].get_path_name()!=row['component']:raise RuntimeError('Exact retained sink component changed')
 c=cs[0];original=c.get_editor_property('static_mesh');temporary=None
 try:
  clone=u.EditorAssetLibrary.duplicate_asset(original.get_path_name(),DEST+'/Mesh')
  if not clone or not clone.get_path_name().startswith(DEST+'/'):raise RuntimeError('Exact private retained sink duplication failed')
  prepare(u,clone,DEST)
  temporary=eas.spawn_actor_from_class(u.StaticMeshActor,u.Vector(0,0,0));temporary.set_actor_label('SUB01_RetainedSink_SourceProof164');temporary.set_actor_hidden_in_game(True)
  tc=temporary.get_component_by_class(u.StaticMeshComponent);tc.set_static_mesh(clone);tc.set_world_transform(c.get_world_transform(),False,False);tc.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
  materials=list(c.get_materials())
  for slot,m in enumerate(materials):tc.set_material(slot,m)
  doc,binary=read_gltf(source);wanted=triangles(doc,binary,164);actual=native_triangles(u,tc)
  if len(wanted)!=2700 or not same_triangles(wanted,actual):raise RuntimeError('Private retained sink does not match every source2700 triangle')
  if [m.get_path_name()if m else None for m in tc.get_materials()]!=[m.get_path_name()if m else None for m in materials]:raise RuntimeError('Private retained sink material bindings changed')
  return {'destination':DEST,'replacements':[(actor,c,clone,materials)],'proof':[{'node':164,'source_triangles':2700,'native_full_triangles':len(actual),'owned_mesh':clone.get_path_name(),'original_mesh':original.get_path_name(),'full_world_triangle_tolerance_cm':.02,'nanite_enabled':False}]}
 except Exception:
  if temporary:eas.destroy_actor(temporary);temporary=None
  if u.EditorAssetLibrary.does_directory_exist(DEST):u.EditorAssetLibrary.delete_directory(DEST)
  raise
 finally:
  if temporary:eas.destroy_actor(temporary)
