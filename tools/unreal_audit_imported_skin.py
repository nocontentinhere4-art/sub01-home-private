"""Already-imported actual UE skin: finish native build and verify actual bounds.
No source retargeting, animation modification or runtime readiness flag."""
import json
from pathlib import Path
import unreal as u
root=Path(u.Paths.project_dir()).resolve()
paths=u.EditorAssetLibrary.list_assets('/Game/Sub01Hands/Canonical',recursive=True,include_folder=False)
meshes=[u.load_asset(path)for path in paths];meshes=[m for m in meshes if isinstance(m,u.SkeletalMesh)]
if not meshes:raise RuntimeError('Actual imported SkeletalMesh assets absent')
# Explicit editor native bridge; no unverified Python compiler reflection.
remaining=u.Sub01HomeHandsInstance.finish_pending_skin_compilation()
rows=[]
for mesh in meshes:
 b=mesh.get_bounds().box_extent;i=mesh.get_imported_bounds().box_extent
 rows.append({'imported_geometry_probe':u.Sub01HomeHandsInstance.describe_imported_skin_geometry(mesh),'object_path':mesh.get_path_name(),'bounds_extent_cm':[b.x,b.y,b.z],
 'imported_bounds_extent_cm':[i.x,i.y,i.z],'skeleton_path':mesh.get_editor_property('skeleton').get_path_name(),
 'built_geometry_bounds_nonzero':all(v>0 for v in [b.x,b.y,b.z])})
valid=[r for r in rows if r['built_geometry_bounds_nonzero']]
primary=max(valid,key=lambda r:__import__('math').prod(r['bounds_extent_cm']))if valid else None
report={'engine':u.SystemLibrary.get_engine_version(),'remaining_skin_build_jobs':remaining,'parts':rows,'primary':primary,'runtime_ready':False,'contact_accepted':False,'scope':'Actual saved skin bounds after native compilation; rendering/contacts not yet accepted.'}
(root/'unreal-skin-build-audit.json').write_text(json.dumps(report,indent=2)+'\n')
u.log('SUB01_SKIN_BUILD_AUDIT '+json.dumps(report))
if remaining or not primary:raise RuntimeError('Actual built skeletal geometry still absent; refusing false primary')
u.EditorAssetLibrary.save_directory('/Game/Sub01Hands/Canonical',only_if_is_dirty=False,recursive=True)
