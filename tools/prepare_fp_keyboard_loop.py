"""Explicit keyboard-only source activity, preserving the failed full-take trial."""
import hashlib,json,sys,time,struct
from pathlib import Path


def run():
    began=time.monotonic();root=Path('/workspace/sub01-home-private/upright-footrest-full-9cd');sys.path[:0]=[str(root/'tools'),'/home/unreal/runtime-tools','/workspace/sub01-home-private/upright-footrest-python/scipy-1.14.1-cp311']
    import numpy as np
    import life_gltf as G
    import export_seat_fit_source as E
    import fit_seat_pose_trial as T
    import fit_seat_pelvis_pitch as P
    import solve_seated_typing_arm_ik as S
    from derive_fp_keyboard_loop import derive
    from home_asset_audit import read_gltf
    from structural_rail_source_patch import accessor,world_matrices,transformed
    source=G.Gltf('/workspace/sub01-home-private/fp-arms-contact-fit-r3/SUB01_FirstPersonArms_ContactTrial.glb');assert source.sha256=='bf87abeb7bcdc1a992c1e388b867f18f9d970f9966d0ebe11ef1d9b2524899e6';out=Path('/workspace/sub01-home-private/fp-keyboard-loop-r1');out.mkdir(exist_ok=False);doc,binary,proof=derive(source.doc,bytes(source.buffers[0]),105,210,12,.4);path=out/'SUB01_FirstPersonKeyboard_LoopCandidate.glb';G.write_glb(path,doc,binary);clip=G.Gltf(path);times=np.asarray(clip.animation().key_times());base=E.Source.load(root/'private-audit/seat-fit-source.npz');sk=T.Skeleton(base);W,_=E.joint_worlds(clip,base.names,times);before=W.copy();core=proof['captured_keys_exact_rows'];bridge=np.arange(core,len(times));d=dict(base.d);d['joint_world']=W;d['times']=times;sk=T.Skeleton(E.Source(d))
    home=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb');assert hashlib.sha256(home.read_bytes()).hexdigest()=='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b';hd,hb=read_gltf(home);hw=world_matrices(hd);pr=hd['meshes'][hd['nodes'][187]['mesh']]['primitives'][0];kp=np.asarray([transformed(hw[187],v)for v in accessor(hd,hb,pr['attributes']['POSITION'])])*100;kp=kp[:,[0,2,1]];ki=np.asarray(accessor(hd,hb,pr['indices']),int).reshape(-1,3);kt=kp[ki];_,inv=np.unique(np.round(kp,5),axis=0,return_inverse=True);parent=list(range(int(inv.max())+1))
    def find(a):
        a=int(a)
        while parent[a]!=a:parent[a]=parent[parent[a]];a=parent[a]
        return a
    for face in inv[ki]:
        a,b,c=map(find,face);parent[b]=a;parent[c]=a
    comp=np.asarray([find(i)for i in inv]);top=np.full(len(parent),-np.inf);np.maximum.at(top,comp,kp[:,2]);n=np.cross(kt[:,1]-kt[:,0],kt[:,2]-kt[:,0]);length=np.linalg.norm(n,axis=1);flat=(length>0)&(np.abs(n[:,2])/np.maximum(length,1e-30)>.9)&(kt.mean(1)[:,2]>=top[comp[ki[:,0]]]-.12);surface=T.Surface(kt[flat])
    def contact(side,world):
        p=E.to_ue(base.skin(side+'_fingers',world)[0]);found,height=surface.height(p[...,:2].reshape(-1,2));found=found.reshape(p.shape[:2]);height=height.reshape(p.shape[:2]);gap=np.where(found,p[...,2]-height,np.inf);return gap.min(1),found.sum(1)
    for side,chain in S.ARM_BONES.items():
        a,b,c=[sk.j(n)for n in chain];target=before[bridge,c,:3,3].copy();pole=before[bridge,b,:3,3];hand=before[bridge,c].copy();initial=before[bridge].copy()
        for _ in range(6):
            candidate,reach,_,_=sk.two_bone_pose(initial.copy(),chain,target,pole,end_world_rot=hand.copy());gap,count=contact(side,candidate);res=np.where(np.isfinite(gap),.08-gap,0.);target+=S.gltf_shift(np.c_[np.zeros((len(bridge),2)),res])
            if np.abs(res).max()<1e-5:break
        candidate,reach,_,_=sk.two_bone_pose(initial.copy(),chain,target,pole,end_world_rot=hand.copy());changed=[a,b]+sk.subtree(c);W[np.ix_(bridge,changed)]=candidate[:,changed];assert reach.all()
    # Only the six arm rotation tracks in the explicit bridge are replaced.
    hips=next(i for i,n in enumerate(clip.nodes)if E.short(n.get('name',''))=='Hips');local=P.joint_locals(sk,W,P.armature_world(clip,hips));quats=P.quat_from_matrix(local[...,:3,:3]);data=bytearray(binary);changed_names=set(sum((list(c)for c in S.ARM_BONES.values()),[]));patch_rows=0
    for channel in doc['animations'][0]['channels']:
        name=E.short(doc['nodes'][channel['target']['node']]['name'])
        if channel['target']['path']!='rotation'or name not in changed_names:continue
        sampler=doc['animations'][0]['samplers'][channel['sampler']];ai=doc['accessors'][sampler['output']];view=doc['bufferViews'][ai['bufferView']];offset=view.get('byteOffset',0)+ai.get('byteOffset',0);stride=view.get('byteStride',16);j=sk.j(name)
        for frame in bridge:
            if frame==len(times)-1:data[offset+int(frame)*stride:offset+int(frame)*stride+16]=data[offset:offset+16]
            else:struct.pack_into('<4f',data,offset+int(frame)*stride,*quats[frame,j])
            patch_rows+=1
    assert bytes(data[:len(source.buffers[0])])==bytes(source.buffers[0]);G.write_glb(path,doc,bytes(data));sha=hashlib.sha256(path.read_bytes()).hexdigest();written=G.Gltf(path);sample=np.sort(np.r_[times,(times[:-1]+times[1:])/2]);read,_=E.joint_worlds(written,base.names,sample);hands={}
    for side in ('left','right'):
        gap,count=contact(side,read);flex,dev,twist=S.wrist_angles(read,base.names,base.ibm,side);hands[side]={'minimum_key_gap_cm':float(gap.min()),'maximum_key_gap_cm':float(gap.max()),'minimum_over_key_distal_vertices':int(count.min()),'gap_over0_2cm_samples':np.flatnonzero(gap>.2).tolist(),'penetration_over0_1cm_samples':np.flatnonzero(gap<-.1).tolist(),'wrist_flexion_deg':[float(flex.min()),float(flex.max())],'wrist_deviation_deg':[float(dev.min()),float(dev.max())],'wrist_twist_deg':[float(twist.min()),float(twist.max())]}
    written_keys,_=E.joint_worlds(written,base.names,times);maxlen=0.;finger_local_error=0.
    for i,par in enumerate(base.parents):
        if par<0:continue
        maxlen=max(maxlen,float(np.abs(np.linalg.norm(written_keys[:,i,:3,3]-written_keys[:,par,:3,3],axis=1)-np.linalg.norm(before[:,i,:3,3]-before[:,par,:3,3],axis=1)).max()*100))
        if 'Hand'in base.names[i]and base.names[i]not in ('LeftHand','RightHand'):finger_local_error=max(finger_local_error,float(np.abs(np.linalg.inv(written_keys[:,par])@written_keys[:,i]-np.linalg.inv(before[:,par])@before[:,i]).max()))
    proof.update(source_clip_sha256=source.sha256,output_glb=str(path),output_sha256=sha,animation_only=True,output_sha_source_original_window_bytes=True,bridge_corrected_local_arms=sorted(changed_names),bridge_arm_rows_updated=patch_rows,maximum_written_bone_length_delta_cm=maxlen,maximum_finger_local_matrix_delta_from_declared_loop=finger_local_error,source_samples=len(sample),hands=hands,loop_world_endpoint_error_cm=float(np.abs(written_keys[0,:,:3,3]-written_keys[-1,:,:3,3]).max()*100),whole_arm_collision_accepted=False,elapsed_s=time.monotonic()-began,native_ready=False)
    (out/'keyboard-loop-source.json').write_text(json.dumps(proof,indent=2)+'\n');(out/'contact-fit-trial.json').write_text(json.dumps({'output_glb':str(path),'output_sha256':sha,'source_ready':False,'native_ready':False},indent=2)+'\n');print(json.dumps({k:v for k,v in proof.items()if k!='bridge_tracks'}),flush=True)

if __name__=='__main__':run()
