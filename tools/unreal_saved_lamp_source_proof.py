"""Temporary full-source validation for the saved lamp; never bind its clone live."""
from uuid import uuid4

from real_office_plant import native_geometry_api_audit
from unreal_owned_mesh_source_geometry import prepare


def can_defer(u,c):
 audit=native_geometry_api_audit(u,c.get_editor_property('static_mesh'))
 settings=audit.get('nanite_settings',{});apis=audit.get('subsystem_apis',{})
 return bool(settings.get('enabled')is True and settings.get('keep_percent_triangles')==1.
             and settings.get('trim_relative_error')==0. and apis.get('get_nanite_settings')and apis.get('set_nanite_settings'))


def prove(u,eas,c,mount,dest,surface,close):
 if not dest.startswith('/Game/Sub01Home/RealEdgeClampLamp/V_')or not dest.endswith('_SavedSourceProof'):
  raise RuntimeError('Temporary saved lamp proof destination is not owned')
 if not can_defer(u,c):raise RuntimeError('Saved lamp source state is not the reviewed Nanite fallback')
 # Each proof owns a fresh namespace. Retained proof assets may still have active
 # compilation references; never force-delete or reuse them on a warm retry.
 dest=dest[:-len('_SavedSourceProof')]+'_'+uuid4().hex+'_SavedSourceProof'
 if u.EditorAssetLibrary.does_directory_exist(dest):raise RuntimeError('Temporary saved lamp proof version already exists')
 original=c.get_editor_property('static_mesh');before=native_geometry_api_audit(u,original)['nanite_settings'];temp=tc=clone=None
 try:
  clone=u.EditorAssetLibrary.duplicate_asset(original.get_path_name(),dest+'/Mesh')
  if not clone or not clone.get_path_name().startswith(dest+'/'):raise RuntimeError('Temporary full-source saved lamp duplication failed')
  prepare(u,clone,dest)
  temp=eas.spawn_actor_from_class(u.StaticMeshActor,u.Vector(0,0,0));temp.set_actor_label('SUB01_SavedLamp_FullSourceProof');temp.set_actor_hidden_in_game(True)
  tc=temp.get_component_by_class(u.StaticMeshComponent);tc.set_static_mesh(clone);tc.set_world_transform(c.get_world_transform(),False,False);tc.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
  for slot,component_material in enumerate(c.get_materials()):tc.set_material(slot,component_material)
  points,count=surface(u,tc);box=[[f(p[k]for p in points)for k in range(3)]for f in(min,max)]
  if count!=mount['lamp_source_triangle_count']or not all(close(a,b)for a,b in zip(box,mount['old_native_aabb_cm'])):raise RuntimeError('Full saved lamp geometry still differs exact measured source support model')
  if [m.get_path_name()if m else None for m in tc.get_materials()]!=[m.get_path_name()if m else None for m in c.get_materials()]:raise RuntimeError('Temporary saved lamp proof changed material bindings')
  if native_geometry_api_audit(u,original)['nanite_settings']!=before:raise RuntimeError('Shared saved lamp Nanite settings changed')
  return {'native_full_triangles':count,'native_full_world_bounds_cm':box,'original_mesh':original.get_path_name(),'original_component_unchanged':True,'temporary_clone_never_activated':True,'source_support_model_verified':True,'quarantined_proof_asset_directory':dest,'proof_assets_deleted':False}
 finally:
  try:
   # Release the component's strong mesh reference before destroying its actor.
   # If detachment fails, preserve the hidden, noncolliding proof actor instead
   # of force-deleting an asset still referenced by the level or compiler.
   if tc is not None:tc.set_static_mesh(None)
   if temp is not None and not eas.destroy_actor(temp):raise RuntimeError('Temporary saved lamp proof actor cleanup failed; proof assets quarantined at '+dest)
  finally:
   tc=clone=temp=None
  # Intentionally retain this owned namespace on both success and failure.
  # Asset deletion while compilation/UObject references survive can assert UE.
