"""Read-only SERVER UE editor audit of actual owner chair material triangles.
Official API: ProceduralMeshLibrary.get_section_from_static_mesh, StaticMeshEditorSubsystem.get_lod_material_slot.
Writes project/private-audit/native-chair-surface.json. No mesh/collision/actor edits or contact acceptance.
"""
from __future__ import annotations
import json,math,re,struct
from pathlib import Path

EXPECTED_SEAT_CM=50.5
EXPECTED_ORIGIN=[200,-190,0]

def cushion_top(vertices,indices,normals=None):
 if not vertices or len(indices)%3:raise ValueError('Missing/invalid real section triangles')
 if any(len(v)!=3 or not all(math.isfinite(x) for x in v)for v in vertices):raise ValueError('Nonfinite world geometry')
 if any(isinstance(i,bool)or not isinstance(i,int)or i<0 or i>=len(vertices)for i in indices):raise ValueError('Invalid actual section index')
 if normals is not None and (len(normals)!=len(vertices) or any(len(n)!=3 or not all(math.isfinite(x)for x in n)for n in normals)):raise ValueError('Invalid actual section normals')
 selected=[]
 for j in range(0,len(indices),3):
  ids=indices[j:j+3];a,b,c=[vertices[i]for i in ids];u=[b[i]-a[i]for i in range(3)];v=[c[i]-a[i]for i in range(3)];cross=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]];length=math.sqrt(sum(x*x for x in cross))
  up=sum(normals[i][2]for i in ids)/3 if normals is not None else (cross[2]/length if length else 0)
  if length and up>.65:selected.append((ids,abs(cross[2])/2,length/2,up))
 if not selected:raise ValueError('No actual upward-facing chair fabric triangles')
 # Weld only coincident seam vertices; then connect triangles by complete
 # shared edges. Merely touching a corner cannot join cushion and lumbar.
 welded=[tuple(round(x,5)for x in p)for p in vertices];parent=list(range(len(selected)));edges={}
 def find(i):
  while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
  return i
 for i,(ids,*_)in enumerate(selected):
  for a,b in zip(ids,ids[1:]+ids[:1]):
   key=tuple(sorted((welded[a],welded[b])))
   if key in edges:parent[find(i)]=find(edges[key])
   else:edges[key]=i
 groups={}
 for i in range(len(selected)):groups.setdefault(find(i),[]).append(i)
 patches=[]
 for members in groups.values():
  triangles=[selected[i][0]for i in members];points=[vertices[i]for t in triangles for i in t];bounds={'min':[min(p[i]for p in points)for i in range(3)],'max':[max(p[i]for p in points)for i in range(3)]}
  patches.append({'triangle_indices':triangles,'world_bounds_cm':bounds,'projected_area_cm2':sum(selected[i][1]for i in members),'surface_area_cm2':sum(selected[i][2]for i in members),'mean_up_normal':sum(selected[i][3]for i in members)/len(members)})
 patches.sort(key=lambda p:p['projected_area_cm2'],reverse=True)
 candidates=[]
 for patch in patches:
  lo=patch['world_bounds_cm']['min'];hi=patch['world_bounds_cm']['max']
  if hi[0]-lo[0]>=20 and hi[1]-lo[1]>=20 and patch['projected_area_cm2']>=200 and 25<=lo[2]<=hi[2]<=80 and abs((lo[0]+hi[0])/2-200)<40 and abs((lo[1]+hi[1])/2+190)<40:candidates.append(patch)
 if not candidates or (len(candidates)>1 and candidates[1]['projected_area_cm2']>=.5*candidates[0]['projected_area_cm2']):
  error=ValueError('No unambiguous broad load-bearing seat patch among actual fabric surfaces');error.measured_surface={'patches':patches};raise error
 seat=candidates[0];bounds=seat['world_bounds_cm']
 return {**seat,'patches':patches,'authored_top_delta_cm':bounds['max'][2]-EXPECTED_SEAT_CM,'selection':'Largest unambiguous edge-connected upward chair_fabric patch with real depth/width; authored height discrepancy recorded separately','collision_trace_verified':False}

def material_identity(names):
 return any(re.search(r'(^|[^a-z0-9])chair_fabric([^a-z0-9]|$)',str(name).lower())for name in names)

def run():
 import unreal as u
 root=Path(u.Paths.project_dir()).resolve();out=root/'private-audit/native-chair-surface.json';out.parent.mkdir(parents=True,exist_ok=True)
 report={'schema':'sub01.native-chair-surface.v1','level':'/Game/Sub01Home/ActualHome','authored_seat_top_cm':EXPECTED_SEAT_CM,'runtime_ready':False,'physical_seating_verified':False,'errors':[],'candidate_sections':[]}
 try:
  level=u.get_editor_subsystem(u.LevelEditorSubsystem)
  if not level.load_level(report['level']):raise RuntimeError('Existing ActualHome map unavailable')
  if not hasattr(u,'ProceduralMeshLibrary'):raise RuntimeError('Official ProceduralMeshComponent editor API not loaded; no bounds-only fallback is accepted')
  # GetLODMaterialSlot is an actual read-only section-info lookup. Commandlets
  # do not initialize the editor subsystem collection; use the same reflected
  # UObject method, never assume that section number equals material slot.
  editor=u.get_editor_subsystem(u.StaticMeshEditorSubsystem) or u.StaticMeshEditorSubsystem()
  if editor is None:raise RuntimeError('Actual section material lookup unavailable; no inferred material slot')
  actors=u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors();matches=[]
  for actor in actors:
   for component in actor.get_components_by_class(u.StaticMeshComponent):
    mesh=component.get_editor_property('static_mesh')
    if not mesh:continue
    slots=list(mesh.get_editor_property('static_materials'));sections=[]
    for section in range(mesh.get_num_sections(0)):
     slot=editor.get_lod_material_slot(mesh,0,section);material=component.get_material(slot)
     # ImportedMaterialSlotName is not reflected by every installed UE build.
     # The assigned material object and actual slot name remain authoritative.
     imported=str(getattr(slots[slot],'imported_material_slot_name',''))
     names=[str(slots[slot].material_slot_name),imported,material.get_name()if material else'',material.get_path_name()if material else'']
     if not material_identity(names):continue
     if material is None:raise RuntimeError('Chair fabric section has no actual assigned material')
     local,indices,local_normals,*_=u.ProceduralMeshLibrary.get_section_from_static_mesh(mesh,0,section);transform=component.get_world_transform();points=[];normals=[]
     for p in local:
      q=transform.transform_location(p);points.append([float(q.x),float(q.y),float(q.z)])
     for n in local_normals:
      q=u.MathLibrary.transform_direction(transform,n);normals.append([float(q.x),float(q.y),float(q.z)])
     # A shared upholstery material includes the lumbar too: preserve full triangles but select exact upward cushion subset.
     try:surface=cushion_top(points,list(indices),normals)
     except ValueError as error:
      report['candidate_sections'].append({'mesh':mesh.get_path_name(),'material_identity':names,'world_bounds_cm':{'min':[min(p[i]for p in points)for i in range(3)],'max':[max(p[i]for p in points)for i in range(3)]},'vertices_world_cm':points,'normals_world':normals,'triangles':list(indices),'measured_surface':getattr(error,'measured_surface',None),'upward_vertex_normals':sum(n[2]>.65 for n in normals),'surface_rejection':str(error)})
      continue
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
  receipt=root/'unreal-fbx-hands-import.json'
  if receipt.is_file():
   owner=json.loads(receipt.read_text());mesh=u.load_asset(owner['mesh']);skeleton=u.load_asset(owner['skeleton']);identity_basis='Actual owner and skeleton match historic import receipt'
  else:
   mesh=u.load_asset('/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner')
   clip=u.load_asset('/Game/Sub01Hands/FBX/SUB01_DeskTyping.SUB01_DeskTyping')
   if not isinstance(mesh,u.SkeletalMesh)or not isinstance(clip,u.AnimSequence):raise RuntimeError('Actual owner/DeskTyping assets unavailable; no name-only fallback')
   skeleton=clip.get_editor_property('skeleton');identity_basis='Actual existing owner and DeskTyping USkeleton equality; historic import receipt absent after migration'
  if not isinstance(mesh,u.SkeletalMesh)or mesh.get_editor_property('skeleton')!=skeleton:raise RuntimeError('Actual existing body and captured clip skeleton differ')
  clip=u.load_asset('/Game/Sub01Hands/FBX/SUB01_DeskTyping.SUB01_DeskTyping')
  if not isinstance(clip,u.AnimSequence)or clip.get_editor_property('skeleton')!=skeleton:raise RuntimeError('Actual captured DeskTyping skeleton unavailable')
  u.Sub01HomeHandsInstance.finish_pending_skin_compilation()
  component=u.SkeletalMeshComponent();component.set_skeletal_mesh_asset(mesh)
  rig_source=root/'SourceAssets/SeatingSource/web/room/char_mixamo.glb'
  raw=rig_source.read_bytes();doc=json.loads(raw[20:20+struct.unpack_from('<I',raw,12)[0]])
  # Official FBX import removes the source Mixamo namespace. Compare exact
  # joint identities after that declared namespace normalization only.
  canonical=lambda value:re.sub('^mixamorig[0-9]*','',re.sub('[^a-z0-9]','',str(value).lower()))
  expected={canonical(doc['nodes'][i]['name'])for i in doc['skins'][0]['joints']}
  actual_names=[component.get_bone_name(i)for i in range(component.get_num_bones())]
  actual={canonical(n):n for n in actual_names};extra=set(actual)-expected
  if len(expected)!=65 or expected-set(actual) or len(extra)>1:raise RuntimeError('Actual owner joints differ from original65-joint source: missing '+str(expected-set(actual))+' extra '+str(extra))
  root_proof=[]
  for name in extra:
   bone=actual[name]
   if str(component.get_parent_bone(bone))!='None':raise RuntimeError('Extra imported bone is not a structural root')
   poses=[u.AnimationLibrary.get_bone_poses_for_time(clip,[bone],time,False,mesh)[0]for time in (0,3,8)]
   def values(t):return[t.translation.x,t.translation.y,t.translation.z,t.rotation.x,t.rotation.y,t.rotation.z,t.rotation.w,t.scale3d.x,t.scale3d.y,t.scale3d.z]
   first=values(poses[0])
   if any(max(abs(a-b)for a,b in zip(first,values(p)))>1.e-5 for p in poses[1:]):raise RuntimeError('Extra imported root changes during capture')
   root_proof.append({'name':str(bone),'captured_times':[0,3,8],'constant_local_transform':first})
  probe=u.Sub01HomeHandsInstance.describe_imported_skin_geometry(mesh)
  match=re.search(r'softVertices=(\d+)',probe)
  if not match or int(match.group(1))<=0:raise RuntimeError('Actual owner skin geometry missing: '+probe)
  report.update({'chair':matches[0],'body':{'mesh':mesh.get_path_name(),'skeleton':skeleton.get_path_name(),'geometry_probe':probe,'identity_basis':identity_basis,'source_joints_verified':65,'actual_imported_bones':len(actual_names),'extra_structural_root_proof':root_proof},'geometry_identity_verified':True,'trace_face_material_verified':False,'continuous_skin_cushion_contact_verified':False})
 except Exception as exc:
  report['errors'].append(str(exc));out.write_text(json.dumps(report,indent=2)+'\n');raise
 out.write_text(json.dumps(report,indent=2)+'\n');u.log('SUB01_CHAIR_SURFACE_AUDIT '+str(out))

if __name__=='__main__':run()
