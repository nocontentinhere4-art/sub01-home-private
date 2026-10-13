"""Actual imported local->component capture transforms, no pose modification."""
import unreal as u,json
from pathlib import Path
mesh=u.load_asset('/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner')
component=u.SkeletalMeshComponent();component.set_skeletal_mesh_asset(mesh)
names=[component.get_bone_name(i)for i in range(component.get_num_bones())]
parents={str(n):str(component.get_parent_bone(n))for n in names}
result=[]
for role in ['DeskTyping','Phone']:
 clip=u.load_asset('/Game/Sub01Hands/FBX/SUB01_'+role+'.SUB01_'+role)
 for time in [0,1,4]:
  poses=u.AnimationLibrary.get_bone_poses_for_time(clip,names,time,False,mesh)
  local={str(n):p for n,p in zip(names,poses)};world={}
  def resolve(name):
   if name in world:return world[name]
   parent=parents[name];world[name]=u.MathLibrary.compose_transforms(local[name],resolve(parent))if parent in local else local[name]
   return world[name]
  points={}
  for n in local:
   if n.lower().endswith(('hips','head','lefthand','righthand','lefthandindex3','righthandindex3')):
    p=resolve(n).translation;points[n]=[p.x,p.y,p.z]
  result.append({'role':role,'time':time,'component_pose_cm':points})
root=Path(u.Paths.project_dir()).resolve();(root/'unreal-captured-pose-audit.json').write_text(json.dumps(result,indent=2))
u.log('SUB01_ACTUAL_CAPTURED_POSE '+json.dumps(result))
