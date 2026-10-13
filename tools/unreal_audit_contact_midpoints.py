"""Actual UE compressed capture + arm-profile interpolation contact regression."""
import unreal as u,json,math
from pathlib import Path
root=Path(u.Paths.project_dir()).resolve();data=json.loads((root/'unreal-skinned-contact-audit.json').read_text());caps=json.loads((root.parent.parent/'keyboard-keycaps-world.json').read_text())
mesh=u.load_asset('/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner');clip=u.load_asset('/Game/Sub01Hands/FBX/SUB01_DeskTyping.SUB01_DeskTyping')
u.Sub01HomeHandsInstance.finish_pending_skin_compilation()
c=u.SkeletalMeshComponent();c.set_skeletal_mesh_asset(mesh);names=[c.get_bone_name(i)for i in range(c.get_num_bones())];parents={str(n):str(c.get_parent_bone(n))for n in names}
body=u.Transform(location=u.Vector(203.9,-232.3,-.6),rotation=u.Rotator(yaw=180));lo=u.Vector(*caps['geometryBoundsUECm']['minCm']);hi=u.Vector(*caps['geometryBoundsUECm']['maxCm']);triangles=[u.Vector(*p)for cap in caps['keycaps']for tri in cap['topTrianglesUECm']for p in tri]
def angular(a,b):return math.degrees(2*math.acos(min(1.,abs(a.x*b.x+a.y*b.y+a.z*b.z+a.w*b.w))))
def blend(a,b,w):
 qa=a['rotation'];qb=b['rotation'];sign=1 if sum(x*y for x,y in zip(qa,qb))>=0 else -1;q=[(1-w)*x+w*sign*y for x,y in zip(qa,qb)];norm=math.sqrt(sum(x*x for x in q));q=[x/norm for x in q]
 t=u.Transform();t.translation=u.Vector(*[(1-w)*x+w*y for x,y in zip(a['translation'],b['translation'])]);t.rotation=u.Quat(*q);t.scale3d=u.Vector(*[(1-w)*x+w*y for x,y in zip(a['scale'],b['scale'])]);return t
rows=[]
for j in range(301):
 i=min(j//2,149);w=(j/2)-i
 a=data['samples'][i];b=data['samples'][i+1];time=3+j/60
 local={str(n):p for n,p in zip(names,u.AnimationLibrary.get_bone_poses_for_time(clip,names,time,False,mesh))}
 def compose(poses):
  out={}
  def resolve(n):
   if n not in out:out[n]=u.MathLibrary.compose_transforms(poses[n],resolve(parents[n]))if parents[n]in poses else poses[n]
   return out[n]
  return {n:resolve(n)for n in poses}
 original=compose(local)
 for n in a['corrected_local_arms']:local[n]=blend(a['corrected_local_arms'][n],b['corrected_local_arms'][n],w)
 corrected=compose(local)
 wrist=max(angular(original[n].rotation,corrected[n].rotation)for n in corrected if n.endswith(('LeftHand','RightHand')))
 result=json.loads(u.Sub01HomeHandsInstance.analyze_captured_finger_skin(mesh,[corrected[str(n)]for n in names],body,lo,hi,triangles))
 rows.append({'time':time,'wrist_world_rotation_max_error_degrees':wrist,**result})
out={'kind':'actualUE compressed capture60Hz midpoint with runtime FTransform.Blend-equivalent NLerp6arm locals','samples_60hz':rows,'max_penetration_cm':max(h['penetrationCm']for r in rows for h in r['hands']),'wrist_world_max_error_deg':max(r['wrist_world_rotation_max_error_degrees']for r in rows)}
(root/'unreal-contact-midpoint-audit.json').write_text(json.dumps(out,indent=2));u.log('SUB01_MIDPOINT_SURFACE_WRITTEN')
