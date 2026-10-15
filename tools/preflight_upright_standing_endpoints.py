"""Bounded endpoint feasibility before deriving physical walking steps."""
import json,sys,hashlib
from pathlib import Path


def run():
    root=Path('/workspace/sub01-home-private/upright-footrest-full-9cd');sys.path[:0]=[str(root/'tools'),'/home/unreal/runtime-tools','/workspace/sub01-home-private/upright-footrest-python/scipy-1.14.1-cp311']
    import numpy as np
    import life_gltf as G
    import export_seat_fit_source as E
    import fit_seat_pelvis_pitch as P
    import solve_seat_pose_anatomical as A
    idle=Path('/home/unreal/runtime-tools/standing-runtime-idle-source.glb');assert hashlib.sha256(idle.read_bytes()).hexdigest()=='3d9876d91a7d5829e112648184bad049c5d5e977f8d67c008db15b3f2a0ccc37'
    owner=Path('/workspace/sub01-home-private/owner-shoulder-derived-r3/owner-shoulder-derived.glb');assert hashlib.sha256(owner.read_bytes()).hexdigest()=='831790a62b81e7e2faa5a201e04740d0911c5bfebd49aa03b124808521e3a2b1'
    E.OWNER=owner;base=E.Source.load(root/'private-audit/seat-fit-source.npz');B=np.linalg.inv(base.ibm);g=G.Gltf(idle);W,_=E.joint_worlds(g,base.names,[0.]);angles=A.joint_angles(W,B,base.names);violations=[]
    for key,value in angles.items():
        simple=key.split('_',1)[1]if key.split('_',1)[0]in('left','right')else key
        if simple in A.ANATOMICAL_LIMITS_DEG:
            lo,hi=A.ANATOMICAL_LIMITS_DEG[simple]
            if value[0]<lo or value[0]>hi:violations.append({'angle':key,'actual_deg':float(value[0]),'limits_deg':[lo,hi]})
    skin=P.owner_skin(stride=1);pts=E.to_ue(P.skin_points(skin,base.ibm,W))[0];pts[:,:2]+=np.asarray([-3.875,32.5]);pi=int(pts[:,2].argmin())
    report={'schema':'sub01.upright-standing-endpoint-feasibility.v1','runtime_idle_object_path':'/Game/Sub01Hands/Life/SUB01_Idle.SUB01_Idle','idle_source_sha256':g.sha256,'angles_deg':{k:float(v[0])for k,v in angles.items()},'anatomical_violations':violations,'unchanged_strong_anatomical_limits':A.ANATOMICAL_LIMITS_DEG,'actual_complete_owner_floor_min_z_cm':float(pts[pi,2]),'floor_witness_ue_cm':pts[pi].tolist(),'floor_witness_joints':[{'joint':base.names[int(j)],'weight':float(w)}for j,w in zip(skin[1][pi],skin[2][pi])if w>0],'all_source_vertices_checked':len(pts),'start_actor_body_ue_cm':[200.025,-199.8,-.6],'source_ready':False,'native_ready':False,'pending':['Physicalstep candidate','Furniture collision and support','Actual native actor placement']}
    out=Path('/workspace/sub01-home-private/upright-standing-approach-r1');out.mkdir(exist_ok=False);(out/'endpoint-preflight.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)

if __name__=='__main__':run()
