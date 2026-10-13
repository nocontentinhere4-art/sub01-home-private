"""Actual captured full-clip distal-joint contact audit, no authored pose edits.
Distal-joint volumes are NOT a full skinned-surface/contact acceptance proof.
"""
import unreal as u,json,math
from pathlib import Path
mesh=u.load_asset('/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner');clip=u.load_asset('/Game/Sub01Hands/FBX/SUB01_DeskTyping.SUB01_DeskTyping')
comp=u.SkeletalMeshComponent();comp.set_skeletal_mesh_asset(mesh)
names=[comp.get_bone_name(i)for i in range(comp.get_num_bones())];parents={str(n):str(comp.get_parent_bone(n))for n in names}
fingers=[str(n)for n in names if any(str(n).lower().endswith(side+'hand'+finger+'3')for side in ['left','right']for finger in ['thumb','index','middle','ring','pinky'])]
rows=[];duration=clip.get_editor_property('sequence_length')
for frame in range(round(duration*30)+1):
 poses=u.AnimationLibrary.get_bone_poses_for_time(clip,names,min(frame/30,duration),False,mesh)
 local={str(n):p for n,p in zip(names,poses)};world={}
 def resolve(n):
  if n not in world:world[n]=u.MathLibrary.compose_transforms(local[n],resolve(parents[n]))if parents[n]in local else local[n]
  return world[n]
 points={}
 for n in fingers:
  p=resolve(n).translation;points[n]=[203.9-p.x,-232.3-p.y,-.6+p.z]
 rows.append({'frame':frame,'time':frame/30,'joints_world_cm':points})
summary={}
for side in ['Left','Right']:
 samples=[(r['frame'],n,p)for r in rows for n,p in r['joints_world_cm'].items()if n.startswith(side)]
 # Physical sourcekeyboard centre200,-294,85.6; broad35x20cm footprint.
 inside=[(f,n,p)for f,n,p in samples if 182.5<=p[0]<=217.5 and -304<=p[1]<=-284]
 under=[(f,n,p)for f,n,p in inside if p[2]<87.38976]
 paths={n:sum(math.dist(rows[i-1]['joints_world_cm'][n],rows[i]['joints_world_cm'][n])for i in range(1,len(rows)))for n in fingers if n.startswith(side)}
 summary[side]={'inside_keyboard_joint_samples':len(inside),'below_key_top_joint_samples':len(under),'minimum_joint_z_cm':min((p[2]for f,n,p in inside),default=None),'maximum_required_uniform_lift_cm':max((87.38976-p[2]for f,n,p in inside),default=0),'distal_joint_path_length_cm':paths}
report={'duration':duration,'samples':len(rows),'keyboard_source_top_cm':87.38976,'body_anchor_cm':[203.9,-232.3,-.6],'summary':summary,'frames':rows,'scope':'Full actualUE animation sampled30Hz; joint-based penetration evidence, not full mesh skin audit. Left finger motion not equivalent to visible two-hand typing.'}
root=Path(u.Paths.project_dir()).resolve();(root/'unreal-typing-contact-audit.json').write_text(json.dumps(report));u.log('SUB01_FULL_TYPING_CONTACT '+json.dumps(summary))
