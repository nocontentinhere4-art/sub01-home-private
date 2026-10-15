"""Source-only arm derivative: actual surfaces, fixed lengths, captured finger locals.

No seating/capsule/native contract is changed. This bounded trial is deliberately
not ready until whole-arm collisions and visual review also pass.
"""
import hashlib,json,sys,time
from pathlib import Path


def run():
    began=time.monotonic();root=Path('/workspace/sub01-home-private/upright-footrest-full-9cd')
    sys.path[:0]=[str(root/'tools'),'/home/unreal/runtime-tools','/workspace/sub01-home-private/upright-footrest-python/scipy-1.14.1-cp311']
    import numpy as np
    import life_gltf as G
    import export_seat_fit_source as E
    import fit_seat_pose_trial as T
    import fit_seat_pelvis_pitch as P
    import solve_seated_typing_arm_ik as S
    from home_asset_audit import read_gltf
    from structural_rail_source_patch import accessor,world_matrices,transformed
    owner=Path('/workspace/sub01-home-private/owner-shoulder-derived-r3/owner-shoulder-derived.glb');assert hashlib.sha256(owner.read_bytes()).hexdigest()=='831790a62b81e7e2faa5a201e04740d0911c5bfebd49aa03b124808521e3a2b1';E.OWNER=owner
    raw=G.Gltf('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/owner-with-clips-unreal.glb');assert raw.sha256=='45e917725f02836dee6d051d9b47dd2785208c78b503fa935ddb322fe69adea8';raw.doc['animations']=[a for a in raw.doc['animations']if a['name']=='typing'];times=np.asarray(raw.animation().key_times());base=E.Source.load(root/'private-audit/seat-fit-source.npz');original,_=E.joint_worlds(raw,base.names,times);sk=T.Skeleton(base)
    home=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb');assert hashlib.sha256(home.read_bytes()).hexdigest()=='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b';doc,binary=read_gltf(home);world=world_matrices(doc)
    def triangles(node):
        n=doc['nodes'][node];pr=doc['meshes'][n['mesh']]['primitives'][0];p=np.asarray([transformed(world[node],v)for v in accessor(doc,binary,pr['attributes']['POSITION'])])*100;p=p[:,[0,2,1]];idx=np.asarray(accessor(doc,binary,pr['indices']),int).reshape(-1,3);return p,idx,p[idx]
    kp,ki,kt=triangles(187);_,inverse=np.unique(np.round(kp,5),axis=0,return_inverse=True);parent=list(range(int(inverse.max())+1))
    def find(a):
        a=int(a)
        while parent[a]!=a:parent[a]=parent[parent[a]];a=parent[a]
        return a
    for face in inverse[ki]:
        a,b,c=map(find,face);parent[b]=a;parent[c]=a
    comp=np.asarray([find(i)for i in inverse]);top=np.full(len(parent),-np.inf);np.maximum.at(top,comp,kp[:,2]);normal=np.cross(kt[:,1]-kt[:,0],kt[:,2]-kt[:,0]);length=np.linalg.norm(normal,axis=1);flat=(length>0)&(np.abs(normal[:,2])/np.maximum(length,1e-30)>.9)&(kt.mean(1)[:,2]>=top[comp[ki[:,0]]]-.12);keys=T.Surface(kt[flat]);mp,mi,mt=triangles(237);mouse=T.Surface(mt)
    def gaps(surface,p):
        f,h=surface.height(p[...,:2].reshape(-1,2));f=f.reshape(p.shape[:2]);h=h.reshape(p.shape[:2]);return np.where(f,p[...,2]-h,np.inf),f
    last_clavicle={}
    def pose(side,target,pole,hand_world,limit):
        chain=S.ARM_BONES[side];a,b,c=[sk.j(n)for n in chain];start=original.copy();angle=np.zeros(len(times))
        if side=='right' and not limit:
            clavicle=sk.j('RightShoulder');C=start[:,clavicle,:3,3];A=start[:,a,:3,3];u=A-C;radius=np.linalg.norm(u,axis=1);u/=radius[:,None];v=target-C;distance=np.linalg.norm(v,axis=1);v/=distance[:,None];alpha=np.arccos(np.clip(np.sum(u*v,axis=1),-1,1));length=np.linalg.norm(start[:,b,:3,3]-A,axis=1)+np.linalg.norm(start[:,c,:3,3]-start[:,b,:3,3],axis=1)
            # Minimum circular clavicle motion giving 0.5% elbow-bend reserve; never stretch.
            bound=np.clip((distance**2+radius**2-(length*.995)**2)/(2*distance*radius),-1,1);need=np.maximum(0,alpha-np.arccos(bound));angle=np.minimum(need,np.radians(15))
            tangent=v-u*np.sum(u*v,axis=1)[:,None];tangent/=np.maximum(np.linalg.norm(tangent,axis=1)[:,None],1e-12);want=np.cos(angle)[:,None]*u+np.sin(angle)[:,None]*tangent;rotation=T.find_between(u,want);new=start[:,clavicle].copy();new[:,:3,:3]=rotation@new[:,:3,:3];start=sk.rebase(start,clavicle,new);pole=start[:,b,:3,3]
        last_clavicle[side]=np.degrees(angle)
        W,reach,length,dist=sk.two_bone_pose(start,chain,target,pole)
        bind=S.bind_worlds(base.ibm);D=S.unit_rot(bind[b][:3,:3])@np.swapaxes(S.unit_rot(W[:,b,:3,:3]),-1,-2)@S.unit_rot(hand_world)@S.unit_rot(bind[c][:3,:3]).T
        if limit:D,_=S.limit_wrist(D,base.names,base.ibm,side)
        desired=S.hand_world_rotation(W,base.names,base.ibm,side,D)
        # Orthogonal polar rotations preserve the ORIGINAL complete hand stretch tensor.
        # Scalar column normalization would alter tiny authored anisotropy and finger lengths.
        u,_,vt=np.linalg.svd(desired);rnew=u@vt;u,_,vt=np.linalg.svd(W[:,c,:3,:3]);rold=u@vt
        new=W[:,c].copy();new[:,:3,:3]=rnew@np.swapaxes(rold,-1,-2)@W[:,c,:3,:3];W=sk.rebase(W,c,new)
        return W,reach
    outW=original.copy();report={'schema':'sub01.fp-arms-contact-fit-trial.v1','derived':True,'keys':len(times),'duration_s':float(times[-1]),'source_body_world_cm':list(E.BODY_CM),'source_body_yaw':E.BODY_YAW,'wrist_strategy':'Captured wrist soft-neutral target at original elbow plane, then fixed per-frame world attitude during actual surface translation; report final wrist ranges rather than assuming comfort','keycap_node':187,'curved_mouse_node':237,'sides':{},'source_ready':False,'native_ready':False}
    modified=[]
    for side in ('left','right'):
        a,b,c=[sk.j(n)for n in S.ARM_BONES[side]];rawskin=E.to_ue(base.skin(side+'_fingers',original)[0]);center=rawskin.mean(1)[:,:2];selector=np.ones(rawskin.shape[1],bool);mouse_weight=np.zeros(len(times));mouse_target=None
        # Capture-derived target classification: only actual surface XY overlap defines contact.
        kg,kf=gaps(keys,rawskin);mg,mf=gaps(mouse,rawskin);key_phase=kf.sum(1)>=4;mouse_phase=(~key_phase)&(mf.sum(1)>=4)
        if side=='right':
            patch=base.patch('right_fingers');selector=np.sum(patch['weights']*(patch['joints']==sk.j('RightHandIndex3')),axis=1)>=.30;assert selector.sum()>=4
            center=rawskin[:,selector].mean(1)[:,:2];wrist_x=E.to_ue(original[:,c,:3,3])[:,0];centers=np.asarray([wrist_x.min(),wrist_x.max()])
            for _ in range(12):
                nearest=np.abs(wrist_x[:,None]-centers).argmin(1);centers=np.asarray([wrist_x[nearest==i].mean()for i in range(2)])
            t=np.clip((wrist_x-centers[0])/(centers[1]-centers[0]),0,1);mouse_weight=t*t*t*(t*(t*6-15)+10);core=mouse_weight>.98;assert core.sum()>10
            lo,hi=mp.min(0),mp.max(0);xy=mt.mean(1)[:,:2];n=np.cross(mt[:,1]-mt[:,0],mt[:,2]-mt[:,0]);n/=np.maximum(np.linalg.norm(n,axis=1)[:,None],1e-12);region=(xy[:,0]>lo[0]+.2*(hi[0]-lo[0]))&(xy[:,0]<lo[0]+.45*(hi[0]-lo[0]))&(xy[:,1]>lo[1]+.15*(hi[1]-lo[1]))&(xy[:,1]<lo[1]+.4*(hi[1]-lo[1]))&(np.abs(n[:,2])>.5)
            assert region.sum()>4;mouse_target=np.median(xy[region],axis=0);offset=mouse_target-np.median(center[core],axis=0);center=center+mouse_weight[:,None]*offset
            key_phase=(mouse_weight<.02)&(kf.sum(1)>=4);mouse_phase=core
            report['mouse_target']={'kind':'Measured front-left curved upper surface patch; no authored switch segmentation claim','point_xy_ue_cm':mouse_target.tolist(),'source_triangles':np.flatnonzero(region).tolist(),'right_index_patch_vertices':int(selector.sum()),'captured_wrist_cluster_x_cm':centers.tolist(),'rigid_xy_offset_at_mouse_core_cm':offset.tolist(),'continuous_capture_driven_mouse_weight':mouse_weight.tolist()}

        target=original[:,c,:3,3].copy();pole=original[:,b,:3,3];neutral,_=pose(side,target,pole,original[:,c,:3,:3],True);fixed_hand_world=neutral[:,c,:3,:3];dxy=np.zeros((len(times),2));dz=np.zeros(len(times));reach=None
        for iteration in range(12):
            W,reach=pose(side,target,pole,fixed_hand_world,False)
            pts=E.to_ue(base.skin(side+'_fingers',W)[0]);kg,kf=gaps(keys,pts);mg,mf=gaps(mouse,pts);lowest=np.minimum(kg.min(1),mg.min(1));res=np.where(np.isfinite(lowest),.08-lowest,0.)
            # Keep the genuine captured horizontal hand path while correcting wrist attitude/height.
            xy=center-pts[:,selector].mean(1)[:,:2];delta=np.c_[xy,res];target+=S.gltf_shift(delta);dz+=res;dxy+=xy
            if np.max(np.abs(delta))<.001:break
        W,reach=pose(side,target,pole,fixed_hand_world,False)
        changed=[a,b]+sk.subtree(c)+([sk.j('RightShoulder')]if side=='right'else[]);outW[:,changed]=W[:,changed];modified+=changed
        pts=E.to_ue(base.skin(side+'_fingers',outW)[0]);kg,kf=gaps(keys,pts);mg,mf=gaps(mouse,pts);move=np.linalg.norm((outW[:,c,:3,3]-original[:,c,:3,3])*100,axis=1);flex,dev,twist=S.wrist_angles(outW,base.names,base.ibm,side)
        report['sides'][side]={'key_phase_frames':np.flatnonzero(key_phase).tolist(),'mouse_phase_frames':np.flatnonzero(mouse_phase).tolist(),'maximum_clavicle_protraction_deg':float(last_clavicle[side].max()),'clavicle_angle_deg':last_clavicle[side].tolist(),'original_arm_root_ue_cm':E.to_ue(original[:,a,:3,3]).tolist(),'fitted_arm_root_ue_cm':E.to_ue(outW[:,a,:3,3]).tolist(),'maximum_wrist_displacement_cm':float(move.max()),'displacement_exceeds15cm_frames':np.flatnonzero(move>15).tolist(),'unreachable_frames':np.flatnonzero(~reach).tolist(),'final_key_lowest_gap_cm':[float(v)if np.isfinite(v)else None for v in kg.min(1)],'final_mouse_top_lowest_gap_cm':[float(v)if np.isfinite(v)else None for v in mg.min(1)],'key_penetration_over0_1cm_frames':np.flatnonzero(kg.min(1)<-.1).tolist(),'mouse_top_penetration_over0_1cm_frames':np.flatnonzero(mg.min(1)<-.1).tolist(),'wrist_flexion_range_deg':[float(flex.min()),float(flex.max())],'wrist_deviation_range_deg':[float(dev.min()),float(dev.max())],'wrist_twist_range_deg':[float(twist.min()),float(twist.max())],'iterations':iteration+1,'centroid_xy_residual_cm':float(np.abs(center-pts[:,selector].mean(1)[:,:2]).max())}
    # Explicit invariants, independent of the contact score.
    untouched=[i for i in range(len(base.names))if i not in modified];assert np.array_equal(outW[:,untouched],original[:,untouched])
    length_error=0.;finger_error=0.;invariant_rows=[]
    for i,parent_i in enumerate(base.parents):
        if parent_i<0:continue
        bone_error=float(np.abs(np.linalg.norm(outW[:,i,:3,3]-outW[:,parent_i,:3,3],axis=1)-np.linalg.norm(original[:,i,:3,3]-original[:,parent_i,:3,3],axis=1)).max()*100);length_error=max(length_error,bone_error);invariant_rows.append({'joint':base.names[i],'length_error_cm':bone_error})
        if 'Hand' in base.names[i]and base.names[i]not in ('LeftHand','RightHand'):
            finger_error=max(finger_error,float(np.abs(np.linalg.inv(outW[:,parent_i])@outW[:,i]-np.linalg.inv(original[:,parent_i])@original[:,i]).max()))
    invariant_path=Path('/workspace/sub01-home-private/fp-arms-contact-fit-r3-invariants.json');invariant_path.write_text(json.dumps({'length_error_cm':length_error,'finger_error':finger_error,'bones':invariant_rows,'sides':report['sides']},indent=2));print('ACTUAL_INVARIANTS',length_error,finger_error,flush=True)
    assert length_error<1e-8 and finger_error<1e-10
    out=Path('/workspace/sub01-home-private/fp-arms-contact-fit-r3');out.mkdir(exist_ok=False);candidate=G.Gltf('/workspace/sub01-home-private/fp-arms-candidate-r1/SUB01_FirstPersonArms_SourceCandidate.glb');candidate.doc['animations']=[a for a in candidate.doc['animations']if a['name']=='typing'];path=out/'SUB01_FirstPersonArms_ContactTrial.glb';sha,_=P.write_clip(candidate,sk,outW,list(map(float,times)),path,'SUB01_FirstPersonArms_ContactTrial',{'derived':True,'role':'FirstPersonPCArms','source_ready':False},{'derived':True,'source_ready':False});written_clip=G.Gltf(path);from fp_arms_clip_tracks import restore_unchanged_rotations;changed_names={'LeftArm','LeftForeArm','LeftHand','RightShoulder','RightArm','RightForeArm','RightHand'};data,restored=restore_unchanged_rotations(raw.doc,bytes(raw.buffers[0]),written_clip.doc,bytes(written_clip.buffers[0]),changed_names);G.write_glb(path,written_clip.doc,data);sha=hashlib.sha256(path.read_bytes()).hexdigest();written,_=E.joint_worlds(G.Gltf(path),base.names,times);report['unchanged_rotation_rows_float32_exact']=restored;report.update(output_glb=str(path),output_sha256=sha,animation_only=True,arms_mesh_sha256='a862cbd3457c2b25da227c0eea2e04dcd8fe1f637115da0ccc69fbcf888ad154',maximum_bone_length_error_cm=length_error,maximum_captured_finger_local_matrix_error=finger_error,untouched_joint_worlds_exact=True,written_world_error_cm=float(np.abs(written[:,:,:3,3]-outW[:,:,:3,3]).max()*100),elapsed_s=time.monotonic()-began,limitations=['Mouse upper surface height is measured, not closed-solid containment','Whole arm versus desk/keyboard/mouse collision and source views pending','Original capture finger locals retained; wrist/arm tracks explicitly derived','No seating/capsule or native readiness claims'])
    (out/'contact-fit-trial.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items()if k!='sides'}));print(json.dumps({s:{k:v for k,v in r.items()if not isinstance(v,list)or len(v)<4}for s,r in report['sides'].items()}))

if __name__=='__main__':run()
