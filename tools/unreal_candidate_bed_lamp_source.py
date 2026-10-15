"""Measure full actual bedside bulb source via an independent owned clone only."""
import json,time
from uuid import uuid4

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 from unreal_import_real_wc import owned_geometry
 assert active_candidate_guard(u.Paths.project_dir());eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);found=[a for a in actors if a.get_actor_label()=='SUB01_RealLamp_BedLamp'];assert len(found)==1;cs=found[0].get_components_by_class(u.StaticMeshComponent);assert len(cs)==1;c=cs[0];mesh=c.get_editor_property('static_mesh');expected='/Game/Sub01Home/RealLamps/BedLamp/SUB01_RealLamp_BedLamp/StaticMeshes/SUB01_RealLamp_BedLamp.SUB01_RealLamp_BedLamp';assert mesh.get_path_name()==expected
 sub=u.get_editor_subsystem(u.StaticMeshEditorSubsystem);keys=['enabled','keep_percent_triangles','fallback_percent_triangles','trim_relative_error','fallback_relative_error'];settings={k:str(sub.get_nanite_settings(mesh).get_editor_property(k))for k in keys};dest='/Game/Sub01Home/BedLampSource/A_'+uuid4().hex;clone=u.EditorAssetLibrary.duplicate_asset(expected.split('.',1)[0],dest+'/Source');actor=None
 try:
  owned_geometry(u,clone,dest)
  if u.Sub01HomeHandsInstance.finish_pending_static_compilation()!=0:raise RuntimeError('Owned lamp source compile incomplete')
  actor=eas.spawn_actor_from_class(u.StaticMeshActor,u.Vector(0,0,0));actor.set_actor_hidden_in_game(True);actor.set_is_temporarily_hidden_in_editor(True);cc=actor.get_component_by_class(u.StaticMeshComponent);cc.set_static_mesh(clone);cc.set_collision_enabled(u.CollisionEnabled.NO_COLLISION);cc.set_world_transform(c.get_world_transform(),False,True);rows=[]
  for si in range(clone.get_num_sections(0)):
   vertices,indices,*_=u.ProceduralMeshLibrary.get_section_from_static_mesh(clone,0,si);coords=[[float(getattr(cc.get_world_transform().transform_location(v),k))for k in('x','y','z')]for v in vertices];lo=[min(p[i]for p in coords)for i in range(3)];hi=[max(p[i]for p in coords)for i in range(3)];rows.append({'section':si,'source_material':c.get_material(si).get_path_name(),'vertices':len(vertices),'triangles':len(indices)//3,'bounds_cm':{'min':lo,'max':hi},'bbox_center_cm':[(lo[i]+hi[i])/2 for i in range(3)],'half_shortest_glass_extent_cm':min(hi[i]-lo[i]for i in range(3))/2,'full_world_triangles_cm':[[coords[j]for j in indices[k:k+3]]for k in range(0,len(indices),3)]})
 finally:
  if actor and not eas.destroy_actor(actor):raise RuntimeError('Temporary owned lamp source actor cleanup failed')
 if snapshot(u,list(eas.get_all_level_actors()))!=before or c.get_editor_property('static_mesh')!=mesh or {k:str(sub.get_nanite_settings(mesh).get_editor_property(k))for k in keys}!=settings:raise RuntimeError('Original lamp and complete candidate world must remain exact')
 result={'schema':'sub01.actual-candidate-bedside-fullsource-probe.v1','original_mesh':expected,'owned_clone':clone.get_path_name(),'source_geometry':'full retained imported asset source; Nanite disabled only on independent clone','original_untouched':True,'world_unchanged':True,'sections':rows};p=CANDIDATE/'private-audit/bed-lamp-fullsource.json';p.write_text(json.dumps(result,indent=2)+'\n');return {'report':str(p),'sections':len(rows),'world_unchanged':True}
