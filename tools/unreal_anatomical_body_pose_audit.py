"""Compare actual old/new imported non-finger body curves without moving actors."""
from pathlib import Path
import json,math,time

def semantic(n):
 for prefix in ('mixamorig:','mixamorig_'):
  if n.startswith(prefix):return n[len(prefix):]
 return n

def run(grip=False):
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 assert active_candidate_guard();d=json.loads((CANDIDATE/'private-audit/anatomical-owner-fbx-candidate.json').read_text());assert d['initial_inventory_passed']and d['assets_saved']and d['owner_assigned']is False
 new=u.load_asset(d['meshes'][0]['path']);clip=u.load_asset(d['clips'][0]['path']);old=u.load_asset('/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner');oldclip=u.load_asset('/Game/Sub01Hands/FBX/SUB01_Walk.SUB01_Walk')
 if grip:
  receipt=json.loads((CANDIDATE/'private-audit/anatomical-grip-candidate.json').read_text());assert receipt['assets_saved']and receipt['matching_existing_new_skeleton'];clip=u.load_asset(receipt['clip']);oldclip=u.load_asset('/Game/Sub01Hands/Play/SUB01_GamingGrip.SUB01_GamingGrip')
 assert clip.get_editor_property('skeleton')==new.get_editor_property('skeleton')and oldclip.get_editor_property('skeleton')==old.get_editor_property('skeleton')
 u.Sub01HomeHandsInstance.finish_pending_skin_compilation()
 def structure(mesh):
  c=u.SkeletalMeshComponent();c.set_skeletal_mesh_asset(mesh);names=[str(c.get_bone_name(i))for i in range(c.get_num_bones())];parents={n:str(c.get_parent_bone(n))for n in names};c.set_skeletal_mesh_asset(None);mapping={semantic(n):n for n in names};assert len(mapping)==len(names);return names,parents,mapping
 a=structure(old);b=structure(new);body=[n for n in a[2]if n not in('mixamo',)and ('Hand'not in n or n.endswith('Hand'))];assert len(body)==25 and all(n in b[2]for n in body)
 def poses(mesh,anim,st,t):
  names,parents,_=st;local=dict(zip(names,u.AnimationLibrary.get_bone_poses_for_time(anim,[u.Name(n)for n in names],t,False,mesh)));resolved={}
  def get(n):
   if n not in resolved:resolved[n]=u.MathLibrary.compose_transforms(local[n],get(parents[n]))if parents[n]in local else local[n]
   return resolved[n]
  return {semantic(n):get(n)for n in names}
 rows=[];maxpos=maxrot=maxscale=0.
 for i in range(152 if grip else 32):
  t=i/30;pa=poses(old,oldclip,a,t);pb=poses(new,clip,b,t);samples=[]
  for n in body:
   x,y=pa[n],pb[n];error=(x.translation-y.translation).length();q=x.rotation;r=y.rotation;dot=abs(q.x*r.x+q.y*r.y+q.z*r.z+q.w*r.w);angle=math.degrees(2*math.acos(min(1.,dot)));scale=(x.scale3d-y.scale3d).length();maxpos=max(maxpos,error);maxrot=max(maxrot,angle);maxscale=max(maxscale,scale);samples.append({'bone':n,'position_error_cm':error,'rotation_error_degrees':angle,'scale_error':scale})
  rows.append({'time_s':t,'body':samples})
 report={'schema':'sub01.actual-native-anatomical-body-pose-audit.v1','read_only':True,'old_mesh':old.get_path_name(),'old_clip':oldclip.get_path_name(),'new_mesh':new.get_path_name(),'new_clip':clip.get_path_name(),'samples':rows,'nonfinger_bones':len(body),'max_position_error_cm':maxpos,'max_rotation_error_degrees':maxrot,'max_scale_error':maxscale,'body_pose_equivalence_passed':maxpos<=.02 and maxrot<=.05 and maxscale<=.0001,'hand_pose_equivalence_verified':False,'world_changed':False,'owner_assigned':False,'epoch':time.time()}
 assert active_candidate_guard();p=CANDIDATE/('private-audit/anatomical-grip-body-pose-audit.json'if grip else'private-audit/anatomical-body-pose-audit.json');p.write_text(json.dumps(report,indent=2)+'\n');return {k:v for k,v in report.items()if k!='samples'}
