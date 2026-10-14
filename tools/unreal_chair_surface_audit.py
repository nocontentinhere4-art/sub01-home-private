"""Read-only SERVER UE editor audit of actual owner chair material triangles.
Official API: ProceduralMeshLibrary.get_section_from_static_mesh, StaticMeshEditorSubsystem.get_lod_material_slot.
Writes project/private-audit/native-chair-surface.json. No mesh/collision/actor edits or contact acceptance.
"""
from __future__ import annotations
import json,math,re
from pathlib import Path

EXPECTED_SEAT_CM=50.5
EXPECTED_ORIGIN=[200,-190,0]

def cushion_top(vertices,indices):
 if not vertices or len(indices)%3:raise ValueError('Missing/invalid real section triangles')
 if any(len(v)!=3 or not all(math.isfinite(x) for x in v)for v in vertices):raise ValueError('Nonfinite world geometry')
 if any(isinstance(i,bool)or not isinstance(i,int)or i<0 or i>=len(vertices)for i in indices):raise ValueError('Invalid actual section index')
 selected=[]
 for j in range(0,len(indices),3):
  ids=indices[j:j+3];a,b,c=[vertices[i]for i in ids];u=[b[i]-a[i]for i in range(3)];v=[c[i]-a[i]for i in range(3)];n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]];length=math.sqrt(sum(x*x for x in n))
  centre=[(a[i]+b[i]+c[i])/3 for i in range(3)]
  if length and n[2]/length>.65 and abs(centre[2]-EXPECTED_SEAT_CM)<8 and abs(centre[0]-200)<40 and abs(centre[1]+190)<40:selected.append(ids)
 if not selected:raise ValueError('No real upward cushion surface near authored chair')
 pts=[vertices[i]for ids in selected for i in ids];bounds={'min':[min(v[i]for v in pts)for i in range(3)],'max':[max(v[i]for v in pts)for i in range(3)]}
 if abs(bounds['max'][2]-EXPECTED_SEAT_CM)>3:raise ValueError('Imported cushion top differs from authored50.5cm; require coordinate audit')
 if bounds['max'][0]-bounds['min'][0]<20 or bounds['max'][1]-bounds['min'][1]<20:raise ValueError('Cushion footprint too small/ambiguous')
 return {'triangle_indices':selected,'world_bounds_cm':bounds,'selection':'Actual chair_fabric upward triangles near authored cushion, not a replacement box','collision_trace_verified':False}

def material_identity(names):
 return any(re.search(r'(^|[^a-z0-9])chair_fabric([^a-z0-9]|$)',str(name).lower())for name in names)

def run():
 import unreal as u
 root=Path(u.Paths.project_dir()).resolve();out=root/'private-audit/native-chair-surface.json';out.parent.mkdir(parents=True,exist_ok=True)
 report={'schema':'sub01.native-chair-surface.v1','level':'/Game/Sub01Home/ActualHome','authored_seat_top_cm':EXPECTED_SEAT_CM,'runtime_ready':False,'physical_seating_verified':False,'errors':[]}
 try:
  level=u.get_editor_subsystem(u.LevelEditorSubsystem)
  if not level.load_level(report['level']):raise RuntimeError('Existing ActualHome map unavailable')
  if not hasattr(u,'ProceduralMeshLibrary'):raise RuntimeError('Official ProceduralMeshComponent editor API not loaded; no bounds-only fallback is accepted')
  editor=u.get_editor_subsystem(u.StaticMeshEditorSubsystem);actors=u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors();matches=[]
  for actor in actors:
   for component in actor.get_components_by_class(u.StaticMeshComponent):
    mesh=component.get_editor_property('static_mesh')
    if not mesh:continue
    slots=list(mesh.get_editor_property('static_materials'));sections=[]
    for section in range(mesh.get_num_sections(0)):
     slot=editor.get_lod_material_slot(mesh,0,section);material=component.get_material(slot);names=[str(slots[slot].material_slot_name),str(slots[slot].imported_material_slot_name),material.get_name()if material else'',material.get_path_name()if material else'']
     if not material_identity(names):continue
     if material is None:raise RuntimeError('Chair fabric section has no actual assigned material')
     local,indices,*_=u.ProceduralMeshLibrary.get_section_from_static_mesh(mesh,0,section);transform=component.get_world_transform();points=[]
     for p in local:
      q=transform.transform_location(p);points.append([float(q.x),float(q.y),float(q.z)])
     # A shared upholstery material includes the lumbar too: preserve full triangles but select exact upward cushion subset.
     try:surface=cushion_top(points,list(indices))
     except ValueError:continue
     sections.append({'lod':0,'section':section,'material_slot':slot,'material_identity':names,'vertices_world_cm':points,'triangles':list(indices),'cushion_surface':surface})
    if sections:
     body=mesh.get_editor_property('body_setup')
     if body is None:raise RuntimeError('Real chair has no BodySetup')
     if component.get_collision_enabled()==u.CollisionEnabled.NO_COLLISION:raise RuntimeError('Real cushion component collision disabled')
     if component.get_collision_response_to_channel(u.CollisionChannel.ECC_PAWN)!=u.CollisionResponseType.ECR_BLOCK:raise RuntimeError('Chair does not block actual pawn')
     t=component.get_world_transform();loc=t.translation;scale=t.scale3d;rot=t.rotation
     lo,hi=component.get_local_bounds();corners=[t.transform_location(u.Vector(x,y,z))for x in (lo.x,hi.x)for y in (lo.y,hi.y)for z in (lo.z,hi.z)];world_bounds={'min':[min(getattr(v,k)for v in corners)for k in ('x','y','z')],'max':[max(getattr(v,k)for v in corners)for k in ('x','y','z')]}
     matches.append({'actor':actor.get_path_name(),'component':component.get_path_name(),'mesh':mesh.get_path_name(),'transform':{'translation_cm':[loc.x,loc.y,loc.z],'rotation_xyzw':[rot.x,rot.y,rot.z,rot.w],'scale':[scale.x,scale.y,scale.z]},'component_world_bounds_cm':world_bounds,'collision_enabled':str(component.get_collision_enabled()),'collision_profile':str(component.get_collision_profile_name()),'collision_trace_flag':str(body.get_editor_property('collision_trace_flag')),'sections':sections})
  if len(matches)!=1:raise RuntimeError('Expected ONE real cushion component, got '+str(len(matches))+'; no ambiguous/name-only chair acceptance')
  owner=json.loads((root/'unreal-fbx-hands-import.json').read_text());mesh=u.load_asset(owner['mesh']);skeleton=u.load_asset(owner['skeleton'])
  if not isinstance(mesh,u.SkeletalMesh)or mesh.get_editor_property('skeleton')!=skeleton:raise RuntimeError('Actual existing body skeleton differs from accepted import manifest')
  u.Sub01HomeHandsInstance.finish_pending_skin_compilation();probe=u.Sub01HomeHandsInstance.describe_imported_skin_geometry(mesh)
  match=re.search(r'softVertices=(\d+)',probe)
  if not match or int(match.group(1))<=0:raise RuntimeError('Actual owner skin geometry missing: '+probe)
  report.update({'chair':matches[0],'body':{'mesh':mesh.get_path_name(),'skeleton':skeleton.get_path_name(),'geometry_probe':probe},'geometry_identity_verified':True,'trace_face_material_verified':False,'continuous_skin_cushion_contact_verified':False})
 except Exception as exc:
  report['errors'].append(str(exc));out.write_text(json.dumps(report,indent=2)+'\n');raise
 out.write_text(json.dumps(report,indent=2)+'\n');u.log('SUB01_CHAIR_SURFACE_AUDIT '+str(out))

if __name__=='__main__':run()
