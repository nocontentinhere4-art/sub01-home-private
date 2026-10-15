"""Bounded candidate-only diagnosis of existing owned275 audit clones; no rebuild."""
from pathlib import Path
import json,time,hashlib
PREFIX='/Game/Sub01Home/GenuineCoffeeTable/V_c05a5d343ff5/'
def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 from home_asset_audit import read_gltf
 from unreal_import_real_wc import expected_triangles
 from unreal_remove_frame_backings import native_triangles,same_triangles
 from unreal_import_reference_wall_console import positive_triangles
 assert active_candidate_guard();eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);old=[a for a in actors if a.get_name()=='full-home_node_275'];assert len(old)==1;cs=old[0].get_components_by_class(u.StaticMeshComponent);assert len(cs)==1;c=cs[0];mesh=c.get_editor_property('static_mesh');assert mesh.get_path_name()=='/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Cube_003.Cube_003'
 d,b=read_gltf(CANDIDATE/'SourceAssets/full-home.glb');rawexpected=expected_triangles(d,b,275);expected,zero=positive_triangles(rawexpected);paths=[p for p in u.EditorAssetLibrary.list_assets(PREFIX,recursive=True,include_folder=False)if'/OriginalAudit/'in p];clones=[u.load_asset(p)for p in paths];clones=[m for m in clones if isinstance(m,u.StaticMesh)];assert 1<=len(clones)<=4,'Expected bounded existing ownedclone from064';out=[]
 def bounds(ts):
  pts=[v for t in ts for v in t];return [[min(v[k]for v in pts)for k in range(3)],[max(v[k]for v in pts)for k in range(3)]]if pts else None
 for clone in clones:
  temp=None
  try:
   sub=u.get_editor_subsystem(u.StaticMeshEditorSubsystem);ns=sub.get_nanite_settings(clone);settings={k:str(ns.get_editor_property(k))for k in['enabled','fallback_target','fallback_relative_error','fallback_percent_triangles','keep_percent_triangles','trim_relative_error']};build=None
   try:
    bs=sub.get_lod_build_settings(clone,0);build={k:str(bs.get_editor_property(k))for k in['remove_degenerates','build_adjacency_buffer','use_full_precision_uvs','use_high_precision_tangent_basis']}
   except Exception as error:build={'error':str(error)}
   temp=eas.spawn_actor_from_class(u.StaticMeshActor,u.Vector(0,0,0));temp.set_actor_hidden_in_game(True);nc=temp.get_component_by_class(u.StaticMeshComponent);nc.set_static_mesh(clone);nc.set_collision_enabled(u.CollisionEnabled.NO_COLLISION);nc.set_world_transform(c.get_world_transform(),False,True);full=native_triangles(u,nc);positive,nativezero=positive_triangles(full);out.append({'mesh':clone.get_path_name(),'source_indexed':len(rawexpected),'source_positive':len(expected),'source_zero_indices':zero,'native_raw':len(full),'native_positive':len(positive),'native_zero_indices':nativezero,'source_bounds_cm':bounds(expected),'native_bounds_cm':bounds(full),'complete_positive_same_at_1micrometre':same_triangles(expected,positive,.0001),'nanite_settings':settings,'LOD0_build_settings':build,'available_description_methods':[n for n in dir(clone)if'description'in n.lower()],'actual_full_world_triangles_cm':full})
  finally:
   if temp:assert eas.destroy_actor(temp)
 assert snapshot(u,eas.get_all_level_actors())==before and active_candidate_guard();result={'schema':'sub01.actual-original275-full-source-diagnostic.v1','clones':out,'original_and_world_unchanged':True,'epoch':time.time()};(CANDIDATE/'private-audit/genuine-coffee-original-geometry-diagnostic.json').write_text(json.dumps(result,indent=2));return {**result,'clones':[{k:v for k,v in r.items()if k!='actual_full_world_triangles_cm'}for r in out]}
