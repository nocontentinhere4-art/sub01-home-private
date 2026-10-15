"""Read-only actual candidate bounds and immutable ownership for plant fitting."""
from pathlib import Path
import json,time,math,hashlib

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 from unreal_extend_private_entry import world_bounds
 assert active_candidate_guard(u.Paths.project_dir())
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);rows=[]
 for a in actors:
  for c in a.get_components_by_class(u.StaticMeshComponent):
   mesh=c.get_editor_property('static_mesh')
   if not mesh:continue
   physical=bool(a.get_actor_enable_collision())and c.get_collision_enabled()!=u.CollisionEnabled.NO_COLLISION
   rendered=not bool(a.get_editor_property('hidden'))and bool(c.get_editor_property('visible'))and not bool(c.get_editor_property('hidden_in_game'))
   if not(physical or rendered):continue
   bounds=world_bounds(u,c);assert all(math.isfinite(x)for p in bounds.values()for x in p)
   rows.append({'actor':a.get_path_name(),'name':a.get_name(),'label':a.get_actor_label(),'component':c.get_path_name(),'mesh':mesh.get_path_name(),'bounds_cm':bounds,'physically_active':physical,'rendered_in_game':rendered,'transform':before[a.get_path_name()]['components'][next(i for i,x in enumerate(before[a.get_path_name()]['components'])if x['path']==c.get_path_name())]['transform'],'collision':str(c.get_collision_enabled()),'tags':[str(t)for t in c.get_editor_property('component_tags')]})
 assert snapshot(u,list(eas.get_all_level_actors()))==before
 # Broad shared wall/rail/sky AABBs need their actual source surface; finer
 # components can be conservatively rejected by AABB without triangle reads.
 from unreal_remove_frame_backings import native_triangles
 sub=u.get_editor_subsystem(u.StaticMeshEditorSubsystem);components={c.get_path_name():c for a in actors for c in a.get_components_by_class(u.StaticMeshComponent)}
 for row in rows:
  b=row['bounds_cm'];span=[b['max'][i]-b['min'][i]for i in range(3)]
  if(max(span[:2])>200 and min(span[:2])>3)or row['name']=='desk_node_44':
   c=components[row['component']];mesh=c.get_editor_property('static_mesh');nanite=bool(sub.get_nanite_settings(mesh).get_editor_property('enabled'));row['actual_nanite_enabled']=nanite
   if not nanite:row['actual_native_triangles_cm']=native_triangles(u,c)
 assert snapshot(u,list(eas.get_all_level_actors()))==before
 report={'schema':'sub01.actual-candidate-plant-placement-inventory.v1','read_only':True,'world_snapshot_unchanged':True,'candidate_map_sha256':hashlib.sha256((CANDIDATE/'Content/Sub01Home/ActualHome.umap').read_bytes()).hexdigest(),'epoch':time.time(),'components':rows};p=CANDIDATE/'private-audit/plant-placement-inventory.json';p.write_text(json.dumps(report,indent=2)+'\n');return {'read_only':True,'visible_components':len(rows),'report':str(p),'world_snapshot_unchanged':True}
