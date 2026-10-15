"""Source-only two physical steps between a corrected standing seam and passed entry.

Original runtime Idle and every passed seated clip stay unchanged. The standing
seam is explicitly derived, not claimed to equal the existing native Idle.
"""
import hashlib,json,math,sys,time
from pathlib import Path


def bounded_leg(worlds, sk, B, names, chain, point, matrix, side, reference_knee=None):
    import numpy as np
    import fit_seat_pelvis_pitch as P
    import solve_seat_pose_anatomical as A
    from scipy.spatial.transform import Rotation
    F=len(worlds);states=np.linspace(-25.,25.,21);poses=[];costs=[];reaches=[];edits=[]
    hip=worlds[:,sk.j(chain[0]),:3,3];knee=worlds[:,sk.j(chain[1]),:3,3]if reference_knee is None else reference_knee;axis=point-hip
    for swivel in states:
        pole=hip+np.einsum('fij,fj->fi',P.rodrigues(axis,np.full(F,math.radians(swivel))),knee-hip)
        candidate,reached,length,distance=sk.two_bone_pose(worlds.copy(),chain,point,pole,end_world_rot=matrix)
        uj,lj,fj=(sk.j(n)for n in chain);upper=candidate[:,lj,:3,3]-candidate[:,uj,:3,3];lower=candidate[:,fj,:3,3]-candidate[:,lj,:3,3];hinge=np.cross(upper,lower);upper_twist=np.zeros(F)
        for bone,ax in [(uj,upper),(lj,lower)]:
            ax=ax/np.linalg.norm(ax,axis=1,keepdims=True);current=np.einsum('fij,j->fi',A.unit(candidate[:,bone,:3,:3])@A.unit(B[bone,:3,:3]).T,np.asarray([1.,0.,0.]));current-=ax*np.sum(current*ax,axis=1)[:,None];desired=hinge.copy();bad=np.linalg.norm(desired,axis=1)<1e-10;desired[bad]=current[bad];current/=np.linalg.norm(current,axis=1,keepdims=True);desired/=np.linalg.norm(desired,axis=1,keepdims=True);twist=np.arctan2(np.sum(ax*np.cross(current,desired),axis=1),np.sum(current*desired,axis=1));candidate[:,bone,:3,:3]=P.rodrigues(ax,twist)@candidate[:,bone,:3,:3]
            if bone==uj:upper_twist=np.degrees(twist)
        relative=A.relative_anat(candidate,B,fj,lj);e=A.euler_xzy(relative);e[:,0]=np.clip(e[:,0],-19.95,49.95);e[:,1]=np.clip(e[:,1],-34.95,14.95)if side=='left'else np.clip(e[:,1],-14.95,34.95)
        rotation=A.unit(candidate[:,lj,:3,:3])@A.unit(B[lj,:3,:3]).T@Rotation.from_euler('XZY',e,degrees=True).as_matrix()@A.unit(B[fj,:3,:3]);old=candidate[:,fj].copy();candidate[:,fj,:3,:3]=rotation*np.linalg.norm(old[:,:3,:3],axis=1)[:,None,:];carry=candidate[:,fj]@np.linalg.inv(old)
        for child in sk.subtree(fj):
            if child!=fj:candidate[:,child]=carry@candidate[:,child]
        angles=A.joint_angles(candidate,B,names);ex=np.zeros(F)
        for key,value in angles.items():
            if not key.startswith(side+'_'):continue
            bounds=A.ANATOMICAL_LIMITS_DEG.get(key[len(side)+1:])
            if bounds:ex+=np.maximum(0,bounds[0]-value)+np.maximum(0,value-bounds[1])
        edit=abs(swivel)+np.abs(upper_twist);ex+=np.maximum(0,edit-25.)
        poses.append(candidate);costs.append(ex*1e5+1e-4*swivel**2);reaches.append(reached);edits.append(edit)
    costs=np.asarray(costs).T;transition=(states[:,None]-states[None,:])**2*.01;score=costs[0].copy();parents=[]
    for f in range(1,F):
        v=score[:,None]+transition;prev=v.argmin(0);parents.append(prev);score=costs[f]+v[prev,np.arange(len(states))]
    path=[int(score.argmin())]
    for prev in reversed(parents):path.append(int(prev[path[-1]]))
    path=np.asarray(path[::-1]);result=np.stack([poses[p][f]for f,p in enumerate(path)])
    return result,{'all_reached':bool(all(reaches[p][f]for f,p in enumerate(path))),'swivel_and_hinge_max_deg':float(max(edits[p][f]for f,p in enumerate(path))),'swivel_deg':states[path].tolist()}


def run():
    start=time.monotonic();root=Path('/workspace/sub01-home-private/upright-footrest-full-9cd');sys.path[:0]=[str(root/'tools'),'/home/unreal/runtime-tools','/workspace/sub01-home-private/upright-footrest-python/scipy-1.14.1-cp311']
    import numpy as np
    import life_gltf as G
    import export_seat_fit_source as E
    import fit_seat_pose_trial as T
    import fit_seat_pelvis_pitch as P
    import solve_seat_pose_anatomical as A
    owner=Path('/workspace/sub01-home-private/owner-shoulder-derived-r3/owner-shoulder-derived.glb');E.OWNER=owner
    assert hashlib.sha256(owner.read_bytes()).hexdigest()=='831790a62b81e7e2faa5a201e04740d0911c5bfebd49aa03b124808521e3a2b1'
    idle=G.Gltf('/home/unreal/runtime-tools/standing-runtime-idle-source.glb');assert idle.sha256=='3d9876d91a7d5829e112648184bad049c5d5e977f8d67c008db15b3f2a0ccc37'
    sit=G.Gltf('/workspace/sub01-home-private/upright-transition-sit-r12/SUB01_SitDown_upright_footrest.glb');assert sit.sha256=='3da7b1f46a7e503f1bea8c3f33a07cdbcf8d931924dbe3a39c1be5123d9700ea'
    walk=G.Gltf('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/owner-with-clips-unreal.glb');assert walk.sha256=='45e917725f02836dee6d051d9b47dd2785208c78b503fa935ddb322fe69adea8';walk.doc['animations']=[a for a in walk.doc['animations']if a['name']=='walking'];assert len(walk.doc['animations'])==1
    out=Path('/workspace/sub01-home-private/upright-standing-approach-r4');out.mkdir(exist_ok=False)
    base=E.Source.load(root/'private-audit/seat-fit-source.npz');sk=T.Skeleton(base);B=np.linalg.inv(base.ibm);I,_=E.joint_worlds(idle,base.names,[0.]);end,_=E.joint_worlds(sit,base.names,[0.]);I[:,:,1,3]+=.0525 # actual configured Walk body4.65 vs seated sourcebody-.6, no actor motion
    report={'schema':'sub01.upright-two-step-approach.v1','runtime_walk_body_z_cm':4.65,'source_evaluation_body_z_cm':-.6,'walk_origin_conversion_hips_y_cm':5.25,'original_Idle_immutable':True,'standing_seam_derived':True,'native_ready':False,'source_ready':False,'geometry_and_main_support_pass':False,'steps':{'left':[3,19],'right':[19,35]},'captured_walk_source_sha256':walk.sha256,'captured_walk_action':'walking','walk_usage':'Actual captured knee bend-plane prior only; full physical endpoints/root/foot paths explicitly derived','limits_changed':False}
    def checkpoint(phase):
        report.update(phase=phase,elapsed_s=time.monotonic()-start);(out/'approach-proof.json').write_text(json.dumps(report,indent=2,default=lambda x:x.tolist()if hasattr(x,'tolist')else str(x))+'\n')
    # Small explicit seam correction: existing source Idle itself violates2 anatomy limits.
    axis=P.hips_lateral_local(sk,I);standing=P.pelvis_pitch(sk,I,np.asarray([2.]),np.asarray([0.]),axis)
    complete=P.owner_skin(stride=1);shoes={}
    for side,prefix in [('left','Left'),('right','Right')]:
        ids=[sk.j(prefix+n)for n in ['Foot','ToeBase','Toe_End']];mask=(np.isin(complete[1],ids)&(complete[2]>0)).any(1);mask|=(complete[0][:,1]<.25)&(complete[0][:,0]*(1 if side=='left'else -1)>0);shoes[side]=tuple(v[mask]for v in complete)
    from scipy.spatial.transform import Rotation
    for side,chain in T.LEGS.items():
        fj=sk.j(chain[2]);rel=A.unit(I[:,fj,:3,:3])@A.unit(B[fj,:3,:3]).T;psi=A.twist_about_y(rel);matrix=np.tile(np.eye(4),(1,1,1));matrix[:,:3,:3]=A.yaw_matrix(psi)@B[fj,:3,:3];point=I[:,fj,:3,3].copy();toe=sk.j(chain[2].replace('Foot','ToeBase'));tip=sk.j(chain[2].replace('Foot','Toe_End'))
        for it in range(5):
            standing,info=bounded_leg(standing,sk,B,base.names,chain,point,matrix,side);standing[:,toe]=standing[:,fj]@(np.linalg.inv(B[fj])@B[toe]);standing[:,tip]=standing[:,toe]@(np.linalg.inv(B[toe])@B[tip]);low=E.to_ue(P.skin_points(shoes[side],base.ibm,standing))[...,2].min(1);point[:,1]+=(2.55-low)/100
        report[side+'_standing_leg']=info
    stance_angles=A.joint_angles(standing,B,base.names);report['derived_stance_anatomical_excess_deg']=float(A.limit_excess(stance_angles,A.joint_angles(I,B,base.names)).max());checkpoint('Measured derived standing seam')
    F=39;times=np.arange(F)/30;progress={};lift={}
    def smooth(x):return P.smootherstep(np.clip(x,0,1))
    for side,(a,b)in report['steps'].items():
        u=np.clip((np.arange(F)-a)/(b-a),0,1);progress[side]=smooth((u-.2)/.6);lift[side]=smooth(u/.2)*(1-smooth((u-.8)/.2))*.06
    root_weight=.25*progress['left']+.75*progress['right'];Aroot=P.armature_world(sit,sit.by_name['mixamorig:Hips']);L0=P.joint_locals(sk,standing,Aroot);L1=P.joint_locals(sk,end,Aroot);q0=np.broadcast_to(P.quat_from_matrix(L0[:,:,:3,:3]),(F,len(base.names),4));q1=np.broadcast_to(P.quat_from_matrix(L1[:,:,:3,:3]),q0.shape);q=P.slerp_arrays(q0,q1,root_weight);hips=(1-root_weight[:,None])*L0[0,0,:3,3]+root_weight[:,None]*L1[0,0,:3,3]
    pose=P.fk_from_locals(sk,np.broadcast_to(standing,(F,)+standing.shape[1:]),Aroot,q,hips,L0);reference=pose.copy();Wwalk,_=E.joint_worlds(walk,base.names,np.linspace(0,float(walk.animation().key_times()[-1]),F));reaches={}
    for side,chain in T.LEGS.items():
        fj,kj=sk.j(chain[2]),sk.j(chain[1]);u=progress[side];first,last=standing[0,fj],end[0,fj];point=(1-u[:,None])*first[:3,3]+u[:,None]*last[:3,3];point[:,1]+=lift[side]
        qa=np.broadcast_to(P.quat_from_matrix(first[None,:3,:3]),(F,4));qb=np.broadcast_to(P.quat_from_matrix(last[None,:3,:3]),(F,4));qr=P.slerp_arrays(qa[:,None],qb[:,None],u)[:,0];matrix=np.tile(np.eye(4),(F,1,1));matrix[:,:3,:3]=Rotation.from_quat(qr).as_matrix()*np.linalg.norm(first[:3,:3],axis=0)[None,None,:]
        correction=(point-reference[:,fj,:3,3])*100;report[side+'_IK_world_horizontal_edit_max_cm']=float(np.abs(correction[:,[0,2]]).max())
        if np.abs(correction[:,[0,2]]).max()>15.:
            f,axis_index=np.unravel_index(np.abs(correction[:,[0,2]]).argmax(),(F,2));axis_index=[0,2][axis_index];report['horizontal_IK_bound_witness']={'side':side,'frame':int(f),'time_s':float(times[f]),'gltf_axis':['x','y','z'][axis_index],'signed_edit_cm':float(correction[f,axis_index]),'point_target_gltf_m':point[f].tolist(),'point_reference_gltf_m':reference[f,fj,:3,3].tolist(),'root_and_pose_blend_weight':float(root_weight[f]),'foot_progress':float(u[f]),'bound_cm':15.};checkpoint('REFUSED original15cm horizontal IK bound');return
        # Authentic Walk supplies the knee-plane direction, rigidly translated to each pelvis.
        pole=pose[:,sk.j(chain[0]),:3,3]+(Wwalk[:,kj,:3,3]-Wwalk[:,sk.j(chain[0]),:3,3])
        for it in range(8):
            pose,info=bounded_leg(pose,sk,B,base.names,chain,point,matrix,side,reference_knee=pole);low=E.to_ue(P.skin_points(shoes[side],base.ibm,pose))[...,2].min(1);target=2.55+100*lift[side];need=np.maximum(0.,target-low)
            if need.max()<1e-6:break
            point[:,1]+=need/100
        reaches[side]=info
    pose[0]=standing[0];pose[-1]=end[0]
    path=out/'SUB01_StandingApproach_upright_footrest_Derived.glb';P.write_clip(sit,sk,pose,times,path,'SUB01_StandingApproach_upright_footrest_Derived',{'derived':True,'source_ready':False},{});W,_=E.joint_worlds(G.Gltf(path),base.names,times);angles=A.joint_angles(W,B,base.names);excess=A.limit_excess(angles,angles)
    report.update(root_and_local_pose_synchronized_to_step_progress=True,written_glb=str(path),written_glb_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),frames=F,duration_s=float(times[-1]),written_world_error_cm=float(np.abs(W-pose).max()*100),bone_length_error_cm=A.bone_length_error_cm(sk,end,W),anatomical_excess_max_deg=float(excess.max()),anatomical_failing_frames=np.flatnonzero(excess>0).tolist(),angles={k:v.tolist()for k,v in angles.items()},leg_reach=reaches,initial_derived_stance_matrix_error=float(np.abs(W[0]-standing[0]).max()),final_passed_SitDown_endpoint_matrix_error=float(np.abs(W[-1]-end[0]).max()),continuous_hips_root_trajectory_gltf_m=W[:,sk.j('Hips'),:3,3].tolist(),pending=['Actual chair/desk/footrest full body collision','Full physical floor support/swing contacts','Explicit handshape/wrist path and native integration'])
    checkpoint('Written two-step candidate, physical collision pending')
    audit_physical(root,base,sk,W,times,path,report,progress,out,start)
    print('ACTUAL_APPROACH_SOURCE_RESULT',report['geometry_and_main_support_pass'],flush=True)


def audit_physical(root,base,sk,W,times,path,report,progress,out,start):
    import numpy as np
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    import export_seat_fit_source as E
    import fit_seat_pose_trial as T
    import fit_seat_pelvis_pitch as P
    import solve_seat_pose_anatomical as A
    import solve_seated_typing_arm_ik as S
    from home_asset_audit import read_gltf
    from structural_rail_source_patch import accessor,world_matrices,transformed
    from closed_footrest_contact import ClosedFootrest
    import recheck_seat_fit_main_rule as R
    strong=(root/'strong-validator.py').read_bytes();assert hashlib.sha256(strong).hexdigest()=='dd95f1b1a8c3fc9a7d08b6d599985b86440c84752d85ae9f12fa8d480397a18f';V=R.load_main_validator(strong)
    def checkpoint(phase):
        report.update(phase=phase,elapsed_s=time.monotonic()-start);(out/'approach-proof.json').write_text(json.dumps(report,indent=2,default=lambda x:x.tolist()if hasattr(x,'tolist')else str(x))+'\n')
    offset=np.asarray([-3.875,32.5]);src,_=P.clip_source(base,path,times);cushion,_=P.load_cushion();cushion=np.asarray(cushion);cushion[...,2]+=2.5001;fit=P.SeatFit(src,cushion,T.keycaps_from_glb(),tuple(-offset),support_z=2.5);measure=A.FastMeasure(fit.trial);A.fast_trial(fit.trial,measure);metrics=measure.metrics(W);supports={}
    for side in ('left','right'):
        name=side+'_sole';m=metrics[name];a,b=report['steps'][side];planted=(np.arange(len(W))<=a)|(np.arange(len(W))>=b);conditions=[R.decompose(V,name,R.region_row(name,m,f))for f in range(len(W))];passed=np.asarray([r['over_ok']and r['min_gap_ok']and r['median_ok']and r['coverage_ok']for r in conditions])
        supports[side]={'required_frames':np.flatnonzero(planted).tolist(),'all_pass':bool(passed[planted].all()),'failing_frames':np.flatnonzero(planted&~passed).tolist(),'lowest_gap_cm':m['lowest'].tolist(),'support_band_vertices':m['band'].tolist(),'main_conditions':conditions,'main_validator_sha256':V.SOURCE_SHA256,'minimum_coverage_rule':V.MIN_BAND_COVERAGE}
    report['unchanged_strong_floor_sole_support']=supports
    labels={}
    def geometry(p):
        d,b=read_gltf(p);m=world_matrices(d);tri=[];materials=[];parts=[]
        for ni,node in enumerate(d['nodes']):
            if 'mesh'not in node:continue
            nm=np.linalg.inv(np.asarray(m[ni])[:3,:3]).T
            for prim in d['meshes'][node['mesh']]['primitives']:
                pos=np.asarray([transformed(m[ni],v)for v in accessor(d,b,prim['attributes']['POSITION'])])*100;pos=pos[:,[0,2,1]]
                normals=np.asarray(accessor(d,b,prim['attributes']['NORMAL']))@nm.T;normals=normals[:,[0,2,1]]
                for ids in np.asarray(accessor(d,b,prim['indices']),int).reshape(-1,3):
                    t=pos[ids].copy();n=np.cross(t[1]-t[0],t[2]-t[0])
                    if np.dot(n,n)==0:continue
                    if np.dot(n,normals[ids].sum(0))<0:t=t[[0,2,1]]
                    tri.append(t);materials.append(d['materials'][prim['material']]['name']);parts.append(ni)
        labels[str(p)]=parts;return np.asarray(tri),np.asarray(materials)
    footrest=Path('/workspace/sub01-home-private/reference-footrest-source-r5/reference-footrest.glb');desk=Path('/workspace/sub01-home-private/out/real-office-bundle/desk.glb')
    foot,fmat=geometry(footrest);foot[...,1]+=8.692038729505747;closed=ClosedFootrest(foot,labels[str(footrest)])
    chair=S.load_complete_chair(S.load_chair());ct=chair['triangles_cm'].copy();ct[...,2]+=2.5001;cn=np.cross(ct[:,1]-ct[:,0],ct[:,2]-ct[:,0]);flip=np.sum(cn*chair['face_normals'],axis=1)<0;ct[flip]=ct[flip][:,[0,2,1]];dt,dmat=geometry(desk)
    def tree(tri):return BVHTree.FromPolygons([Vector(p)for p in tri.reshape(-1,3)],[(3*i,3*i+1,3*i+2)for i in range(len(tri))],all_triangles=True,epsilon=0)
    scenes={name:(tree(t),mat,t.min((0,1)),t.max((0,1)))for name,t,mat in [('chair',ct,chair['material']),('footrest',foot,fmat),('desk',dt,dmat)]}
    collisions={name:{'minimum_margin_cm':3.,'frames_checked':0,'failing_frames':[]}for name in scenes};skin=P.owner_skin(stride=6);floor_min=float('inf')
    for f,world in enumerate(W):
        if time.monotonic()-start>104:break
        pts=E.to_ue(P.skin_points(skin,base.ibm,world[None]))[0];pts[:,:2]+=offset;floor_min=min(floor_min,float(pts[:,2].min()))
        for name,(bvh,mats,lo,hi)in scenes.items():
            row=collisions[name];minimum=3.
            for pi in np.flatnonzero(np.all((pts>=lo-3)&(pts<=hi+3),axis=1)):
                point=pts[pi];loc,normal,index,distance=bvh.find_nearest(Vector(point));signed=closed.signed_distance(point,float(distance))if name=='footrest'else distance*(-1 if(Vector(point)-loc).dot(normal)<0 else 1);allowed=-2.5 if name=='chair'and mats[index]=='chair_fabric'else 0.;margin=signed-allowed
                minimum=min(minimum,margin)
                if margin<row['minimum_margin_cm']:row['witness']={'frame':f,'time_s':float(times[f]),'body_point_ue_cm':point.tolist(),'nearest_ue_cm':list(loc),'triangle':int(index),'material':str(mats[index]),'joint_weights':[{'joint':base.names[int(j)],'weight':float(w)}for j,w in zip(skin[1][pi],skin[2][pi])if w>0]}
            row['frames_checked']+=1;row['minimum_margin_cm']=min(row['minimum_margin_cm'],minimum)
            if minimum<0:row['failing_frames'].append(f)
        if f%10==0:report['collision']=collisions;checkpoint('Actual physical source frame'+str(f))
    report.update(collision=collisions,actual_floor_min_z_cm=floor_min,geometry_and_main_support_pass=bool(report['anatomical_excess_max_deg']==0 and report['bone_length_error_cm']<1e-5 and all(x['all_pass']for x in supports.values())and all(x['all_reached']and x['swivel_and_hinge_max_deg']<=25 for x in report['leg_reach'].values())and floor_min>=2.5 and all(r['frames_checked']==len(W)and not r['failing_frames']for r in collisions.values())))
    checkpoint('Bounded two-step source physical audit complete')

if __name__=='__main__':run()
