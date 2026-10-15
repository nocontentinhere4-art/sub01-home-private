"""Paired phone joint-frame audit only; never edits a mount, pose, skin or camera.

Consumes existing64089ca telemetry after an exact derived-review marker. Old
five-part AABB centres contain no wrist orientation and cannot establish a basis.
Missing LH telemetry is reported, never inferred from RH/controller similarity.
"""
import argparse,hashlib,json,math,re,sys
from pathlib import Path

SOURCE_SHA='81c1d4e10c0a71f46cb4aac36eafd605f92f2fa9397f8d444cc10775445823b2'
FBX_SHA='30ce52419d204f914bda05d1a73aefbd49affd0c3f3bfd62f2ccfeacdb82e9d4'
READER_SHA='d9d271e9dff76412448f340000014adfd85aceffcf2500e822055342793f32e5'
OBJECT='/Game/Sub01Hands/Phone/SUB01_PhoneGrip.SUB01_PhoneGrip'
MARKER='SUB01_PHONE_CAPTURED_BONE_FRAME'
NUMBER=r'[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?'
Q90=(math.sqrt(.5),0,0,math.sqrt(.5))


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def numbers(text):return [float(x)for x in re.findall(NUMBER,text)]
def finite_vector(value,width):
 v=numbers(value)
 if len(v)!=width or not all(math.isfinite(x)for x in v):raise ValueError('Exact finite logged vector required')
 return v


def body_transform(text):
 parts=text.split('|')
 if len(parts)!=3:raise ValueError('Actual native body TRS required')
 p,angles,scale=[finite_vector(part,3)for part in parts]
 if any(abs(x-1)>1e-6 for x in scale):raise ValueError('Unit body scale required for this fixed-frame comparison')
 pitch,yaw,roll=angles;sp,sy,sr=[math.sin(math.radians(v)/2)for v in angles];cp,cy,cr=[math.cos(math.radians(v)/2)for v in angles]
 return p,(cr*sp*sy-sr*cp*cy,-cr*sp*cy-sr*cp*sy,cr*cp*sy-sr*sp*cy,cr*cp*cy+sr*sp*sy)


def extract(text,key,next_key,width):
 m=re.search(r'\b'+key+r'=(.*?)\s+'+next_key+r'=',text)
 if not m:raise ValueError('Missing paired native field '+key)
 return finite_vector(m[1],width)


def parse_rows(text):
 active=False;rows=[];unpaired=0
 for line in text.splitlines():
  if 'SUB01_EXPLICIT_VIEW_MODE_SWITCH'in line and 'mode=manual'in line:active=False
  if 'SUB01_DERIVED_PHONE_VISUAL_REVIEW'in line:active='source=81c1d4e1'in line
  if MARKER not in line:continue
  if not active:unpaired+=1;continue
  m=re.search(r'\btime=('+NUMBER+r')\s+wrist=',line)
  if not m:raise ValueError('Phone telemetry has no exact native phase')
  phase=float(m[1])
  if not math.isfinite(phase)or not 0<=phase<=18.533334:raise ValueError('Phone phase outside exact clip')
  body=re.search(r'\bbody=(.*?);\s*read_only=true',line)
  if not body:raise ValueError('Paired actual body TRS/read-only marker required')
  p,q=body_transform(body[1]);joints={'RightHand':{'position':extract(line,'wrist','wristQ',3),'quaternion':extract(line,'wristQ','wristScale',4),'scale':extract(line,'wristScale','headAvailable',3)}}
  if re.search(r'\bheadAvailable=1\b',line):joints['Head']={'position':extract(line,'head','headQ',3),'quaternion':extract(line,'headQ','headScale',4),'scale':extract(line,'headScale','body',3)}
  for joint in joints.values():
   if sum(v*v for v in joint['quaternion'])<1e-12:raise ValueError('Nonzero actual quaternion required')
  # Current64089ca has no LH field; absence is part of the result.
  rows.append({'native_time_s':phase,'source_time_s':phase,'body_position_cm':p,'body_quaternion_xyzw':q,'joints':joints})
 return rows,unpaired


def compare_frame(G,row,source_world,index):
 results={};body_p=row['body_position_cm'];body_q=row['body_quaternion_xyzw']
 for name,native in row['joints'].items():
  p,q,scale=source_world[index[name]];component=(p[0]*100,p[2]*100,p[1]*100);rotated=G.qrot(body_q,component);expected_p=[x+y for x,y in zip(body_p,rotated)]
  # Reflection(x,z,y) maps quaternion vector part to(-x,-z,-y).
  expected_q=G.qnorm(G.qmul(body_q,(-q[0],-q[2],-q[1],q[3])));native_q=G.qnorm(native['quaternion']);correction=G.qnorm(G.qmul(G.qinv(native_q),expected_q))
  results[name]={'native_world_position_cm':native['position'],'source_world_position_cm':expected_p,'position_error_cm':math.dist(native['position'],expected_p),'native_world_quaternion_xyzw':native_q,'source_world_quaternion_xyzw':expected_q,'native_to_source_local_basis_xyzw':correction,'native_source_orientation_difference_deg':G.qangle_deg(expected_q,native_q),'distance_to_positive90X_deg':G.qangle_deg(correction,Q90),'native_logged_scale':native['scale'],'source_world_uniform_scale':scale}
 return results


def summarize(G,rows):
 result={}
 for name in ('RightHand','LeftHand','Head'):
  values=[(r['native_time_s'],r['comparison'][name])for r in rows if name in r['comparison']]
  if not values:result[name]={'actual_paired_samples':0,'basis_observed':False};continue
  first=values[0][1]['native_to_source_local_basis_xyzw'];phases=sorted(set(t for t,v in values));result[name]={'actual_paired_samples':len(values),'distinct_native_phases':phases,'basis_observed':True,'sampled_constancy_evaluable':len(phases)>=2,'reference_basis_xyzw':first,'maximum_position_error_cm':max(v['position_error_cm']for _,v in values),'maximum_basis_difference_from_first_deg':max(G.qangle_deg(first,v['native_to_source_local_basis_xyzw'])for _,v in values),'maximum_distance_to_positive90X_deg':max(v['distance_to_positive90X_deg']for _,v in values),'full557_key_constancy_proven':False}
 return result


def audit(args):
 reader=Path(args.helpers)/'life_gltf.py'
 if sha(reader)!=READER_SHA:raise ValueError('Exact independent source reader required')
 sys.path.insert(0,str(reader.parent));import life_gltf as G
 if sha(args.source)!=SOURCE_SHA:raise ValueError('Exact derived phone source required')
 receipt=json.loads(Path(args.import_receipt).read_text())
 if receipt.get('schema')!='sub01.unreal-phone-grip-import.v1'or receipt.get('derived_glb_sha256')!=SOURCE_SHA or receipt.get('fbx_sha256')!=FBX_SHA or receipt.get('object_path')!=OBJECT or receipt.get('sampled_keys')!=557:raise ValueError('Actual derived Phone import receipt differs')
 source=G.Gltf(args.source);animation=source.animation();keys=animation.key_times()
 if animation.start!=0 or len(keys)!=557 or abs(animation.end-18.53333282470703)>1e-6:raise ValueError('Phone source timebase differs; do not borrow controller+.033333 offset')
 text=Path(args.log).read_text();rows,unpaired=parse_rows(text);index={n.get('name','').split(':')[-1]:i for i,n in enumerate(source.nodes)}
 for row in rows:row['comparison']=compare_frame(G,row,G.world_pose(source,animation,min(row['source_time_s'],animation.end)),index)
 result={'schema':'sub01.phone-native-source-basis-audit.v1','log_sha256':sha(args.log),'derived_source_sha256':SOURCE_SHA,'actual_import_receipt_sha256':sha(args.import_receipt),'source_first_key_s':0,'source_last_key_s':animation.end,'source_keys':557,'native_time_mapping':'source_time=native_time; no controller first-key offset','available_legacy_geometry_groups':text.count('SUB01_PHONE_REVIEW_GEOMETRY'),'available_legacy_part_rows':text.count('SUB01_PHONE_REVIEW_PART'),'actual_paired_frame_count':len(rows),'unpaired_frame_lines_excluded':unpaired,'summary':summarize(G,rows),'samples':rows,'enough_existing_evidence_for_mount_change':False,'limitations':['Current64089ca readback includes RH/head, not LH','Old167five-part centre groups establish assembly rigidity only, not joint-frame orientation','Constant basis is measured only at captured phases; no unmeasured557key proof','Quaternion basis is not skin/contact/eye/phone-screen acceptance'],'mount_changed':False,'bones_head_camera_materials_changed':False,'contact_accepted':False,'activity_ready':False};Path(args.output).write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');return result


def main():
 p=argparse.ArgumentParser()
 for name in ('log','source','import-receipt','helpers','output'):p.add_argument('--'+name,required=True)
 args=p.parse_args();result=audit(args);print(json.dumps({k:v for k,v in result.items()if k!='samples'},indent=2))

if __name__=='__main__':main()
