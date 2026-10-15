"""Light65-joint source comparison; no skin evaluation or native mutation."""
import sys,copy,json,math,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from home_asset_audit import read_gltf
from structural_rail_source_patch import accessor,world_matrices
base=Path('docs/proposed/upright-footrest-source')
def pose(path,last):
 d,b=read_gltf(path);d=copy.deepcopy(d);a=d['animations'][0]
 for c in a['channels']:
  s=a['samplers'][c['sampler']];r=accessor(d,b,s['output']);d['nodes'][c['target']['node']][c['target']['path']]=r[-1 if last else 0]
 W=world_matrices(d);return {n['name']:W[i] for i,n in enumerate(d['nodes'])if n.get('name','').startswith('mixamorig:')}
def diff(a,b):
 rows=[]
 for n in sorted(a):
  A,B=a[n],b[n];delta=[100*(A[i][3]-B[i][3])for i in range(3)];error=math.sqrt(sum(x*x for x in delta));an=[math.sqrt(sum(A[r][c]**2 for r in range(3)))for c in range(3)];bn=[math.sqrt(sum(B[r][c]**2 for r in range(3)))for c in range(3)];trace=sum(A[r][c]/an[c]*B[r][c]/bn[c] for r in range(3)for c in range(3));angle=math.degrees(math.acos(max(-1,min(1,(trace-1)/2))))
  rows.append({'joint':n,'joint_head_difference_cm':error,'position_delta_gltf_cm':delta,'world_rotation_difference_deg':angle})
 return sorted(rows,key=lambda r:r['joint_head_difference_cm'],reverse=True)
idle=Path('out/first-person-assets/ReferenceT/idle-source-review.glb');getup=base/'SUB01_GetUp_upright_footrest_ShortStart.glb';sit=base/'SUB01_SitDown_upright_footrest.glb'
a=pose(getup,True);b=pose(idle,False);assert len(a)==len(b)==65 and set(a)==set(b)
rep={'schema':'sub01.upright-standing-idle-source-seam.v1','runtime_idle_object_path':'/Game/Sub01Hands/Life/SUB01_Idle.SUB01_Idle','declared_idle_source':str(idle),'declared_idle_source_sha256':hashlib.sha256(idle.read_bytes()).hexdigest(),'getup_source_sha256':hashlib.sha256(getup.read_bytes()).hexdigest(),'getup_end_vs_Idle_start':diff(a,b),'sit_start_vs_Idle_start':diff(pose(sit,False),b),'native_ready':False,'note':'65 direct glTF joint matrices only; no skin simulation/native action. Runtime FBX/source relationship declared by renderer existing audit; not independently reimported here.'}
d0,_=read_gltf(idle);d1,_=read_gltf(getup);w0=world_matrices(d0);w1=world_matrices(d1);by0={n.get('name'):w0[i]for i,n in enumerate(d0['nodes'])};rest_max=max(abs(by0[n['name']][r][c]-w1[i][r][c])for i,n in enumerate(d1['nodes'])if n.get('name','').startswith('mixamorig:')for r in range(4)for c in range(4))
rep['all65_rest_world_matrix_max_difference']=rest_max
for key in ['getup_end_vs_Idle_start','sit_start_vs_Idle_start']:
 rows=rep[key];hip=next(r['position_delta_gltf_cm']for r in rows if r['joint']=='mixamorig:Hips')
 for row in rows:row['joint_head_difference_after_hips_translation_alignment_cm']=math.sqrt(sum((a-b)**2 for a,b in zip(row['position_delta_gltf_cm'],hip)))
rep['interpretation']='The65source rest-world bases match. Hips translation alignment removes only constant placement; substantial remaining pose differences require captured approach/exit integration. Native actor transforms/actual framebuffer not measured here.'
(base/'standing-idle-source-seam.json').write_text(json.dumps(rep,indent=2)+'\n');print(json.dumps({k:rep[k][:3]for k in ['getup_end_vs_Idle_start','sit_start_vs_Idle_start']},indent=2))
