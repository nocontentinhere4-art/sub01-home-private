"""Server UE audit: actual imported soft vertices + captured poses, no edits."""
import unreal as u, json, math
from pathlib import Path
mesh=u.load_asset('/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner')
clip=u.load_asset('/Game/Sub01Hands/FBX/SUB01_DeskTyping.SUB01_DeskTyping')
assert mesh and clip
u.Sub01HomeHandsInstance.finish_pending_skin_compilation()
c=u.SkeletalMeshComponent();c.set_skeletal_mesh_asset(mesh)
names=[c.get_bone_name(i) for i in range(c.get_num_bones())]
parents={str(n):str(c.get_parent_bone(n)) for n in names}
body=u.Transform(location=u.Vector(203.9,-232.3,-.6),rotation=u.Rotator(yaw=180))
# Exact keycap top; XY must be checked against actual imported key geometry.
caps=json.loads((Path(u.Paths.project_dir()).parent.parent/'keyboard-keycaps-world.json').read_text())
key_min=u.Vector(*caps['geometryBoundsUECm']['minCm']);key_max=u.Vector(*caps['geometryBoundsUECm']['maxCm'])
key_triangles=[u.Vector(*p) for cap in caps['keycaps'] for tri in cap['topTrianglesUECm'] for p in tri]
rows=[]
for frame in range(90,241):
 time=frame/30
 poses=u.AnimationLibrary.get_bone_poses_for_time(clip,names,time,False,mesh)
 local={str(n):p for n,p in zip(names,poses)};resolved={}
 def component(n):
  if n not in resolved:
   par=parents[n];resolved[n]=u.MathLibrary.compose_transforms(local[n],component(par)) if par in local else local[n]
  return resolved[n]
 component_pose=[component(str(n)) for n in names]
 report=json.loads(u.Sub01HomeHandsInstance.analyze_captured_finger_skin(mesh,component_pose,body,key_min,key_max,key_triangles))
 corrected=u.Sub01HomeHandsInstance.solve_captured_keyboard_arm_contact(mesh,component_pose,body,key_min,key_max,key_triangles)
 after=json.loads(u.Sub01HomeHandsInstance.analyze_captured_finger_skin(mesh,corrected,body,key_min,key_max,key_triangles))
 corrected_by_name={str(n):t for n,t in zip(names,corrected)}
 finger_error=0.;length_error=0.
 for name,t in corrected_by_name.items():
  parent=parents[name]
  if parent not in corrected_by_name:continue
  old_length=(resolved[name].translation-resolved[parent].translation).length()
  new_length=(t.translation-corrected_by_name[parent].translation).length()
  length_error=max(length_error,abs(old_length-new_length))
  if any('Hand'+finger in name for finger in ['Thumb','Index','Middle','Ring','Pinky']):
   relative=u.MathLibrary.compose_transforms(t,u.MathLibrary.invert_transform(corrected_by_name[parent]))
   a=relative.rotation;b=local[name].rotation
   dot=abs(a.x*b.x+a.y*b.y+a.z*b.z+a.w*b.w)
   finger_error=max(finger_error,math.degrees(2*math.acos(min(1.,dot))))
 arm_local={}
 for side in ['Left','Right']:
  hand=next(n for n in corrected_by_name if n.endswith(side+'Hand'))
  for name in [hand,parents[hand],parents[parents[hand]]]:
   parent=parents[name];t=u.MathLibrary.compose_transforms(corrected_by_name[name],u.MathLibrary.invert_transform(corrected_by_name[parent]))if parent in corrected_by_name else corrected_by_name[name]
   q=t.rotation;p=t.translation;scale=t.scale3d
   arm_local[name]={'translation':[p.x,p.y,p.z],'rotation':[q.x,q.y,q.z,q.w],'scale':[scale.x,scale.y,scale.z]}
 report['corrected_local_arms']=arm_local
 report['corrected']=after;report['arm_world_offsets_cm']={side:[corrected_by_name[next(n for n in corrected_by_name if n.endswith(side+'Hand'))].translation.z-resolved[next(n for n in corrected_by_name if n.endswith(side+'Hand'))].translation.z]for side in ['Left','Right']};report['finger_local_max_error_degrees']=finger_error;report['bone_length_max_error_cm']=length_error
 assert 'error' not in report,report
 assert report['invalidInfluences']==0,report
 assert all(h['selectedVertices']>0 for h in report['hands']),report
 rows.append({'time':time,**report})
assert all(sum(row['hands'][i]['overKeyVertices']for row in rows)>0 for i in [0,1]),'No actual key overlap: orientation/mapping invalid'
result={'kind':'actual imported distal-influenced skinned surface; not joint estimate','source_interval_seconds':[3,8],'selected_threshold':.30,'key_xy_status':'actual87keycaps toptriangle narrowphase; sourceSHA '+caps['sourceSHA256'],'body_cm':[203.9,-232.3,-.6],'body_yaw':180,'samples':rows}
p=Path(u.Paths.project_dir())/'unreal-skinned-contact-audit.json';p.write_text(json.dumps(result,indent=2))
u.log('SUB01_SKIN_CONTACT_AUDIT_WRITTEN '+str(p))
