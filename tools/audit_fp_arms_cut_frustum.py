"""Recheck the unchanged source mask against a newly derived arm animation."""
import gzip,json,math,sys
from pathlib import Path


def audit(clip_path):
    import numpy as np
    root=Path('/workspace/sub01-home-private/upright-footrest-full-9cd');sys.path[:0]=[str(root/'tools'),'/home/unreal/runtime-tools','/workspace/sub01-home-private/upright-footrest-python/scipy-1.14.1-cp311']
    import life_gltf as G
    import export_seat_fit_source as E
    import fit_seat_pelvis_pitch as P
    from prepare_fp_arms_candidate import segment_visible
    clip=G.Gltf(clip_path);owner=G.Gltf('/workspace/sub01-home-private/owner-shoulder-derived-r3/owner-shoulder-derived.glb');assert owner.sha256=='831790a62b81e7e2faa5a201e04740d0911c5bfebd49aa03b124808521e3a2b1';base=E.Source.load(root/'private-audit/seat-fit-source.npz');times=np.asarray(clip.animation().key_times());W,_=E.joint_worlds(clip,base.names,times)
    mask=json.loads(gzip.decompress(Path('/workspace/sub01-home-private/fp-arms-source-audit-r1/arms-mask-phase-audit.json.gz').read_bytes()));row=next(r for r in mask['variants']if r['scope']=='full_arm'and r['threshold']==.5);pairs=np.asarray(row['new_cut_source_vertex_pairs'],int);ids,inv=np.unique(pairs,return_inverse=True);attrs=owner.doc['meshes'][0]['primitives'][0]['attributes'];pos=E.accessor(owner,attrs['POSITION'])[ids];j=E.accessor(owner,attrs['JOINTS_0'])[ids].astype(int);w=E.accessor(owner,attrs['WEIGHTS_0'])[ids];w/=w.sum(1,keepdims=True);boundary=E.to_ue(P.skin_points((pos,j,w),base.ibm,W))[:,inv.reshape(-1,2)]
    eye_doc=json.loads(Path('/home/unreal/runtime-tools/fp-arms-iris-witness.json').read_text());head_attrs=owner.doc['meshes'][0]['primitives'][1]['attributes'];hp=E.accessor(owner,head_attrs['POSITION']);hj=E.accessor(owner,head_attrs['JOINTS_0']).astype(int);hw=E.accessor(owner,head_attrs['WEIGHTS_0']);hw/=hw.sum(1,keepdims=True);eye=[]
    for point in eye_doc['points']:
        ix=np.asarray(point['vertices'],int);eye.append(np.einsum('fvi,v->fi',P.skin_points((hp[ix],hj[ix],hw[ix]),base.ibm,W),np.asarray(point['weights'])))
    camera=E.to_ue(np.mean(eye,axis=0));head=base.names.index('Head');M=W[:,head]@base.ibm[head];f=E.to_ue_dir(M[:,:3,2]);f/=np.linalg.norm(f,axis=1,keepdims=True);up=E.to_ue_dir(M[:,:3,1]);up-=f*np.sum(up*f,axis=1)[:,None];up/=np.linalg.norm(up,axis=1,keepdims=True);right=np.cross(f,up);delta=boundary-camera[:,None,None,:];rows=[];tan_h=math.tan(math.radians(37.5));tan_v=tan_h/(16/9)
    for degrees in (0,20,35,50,65):
        a=math.radians(degrees);forward=math.cos(a)*f-math.sin(a)*up;vertical=math.cos(a)*up+math.sin(a)*f;coords=np.stack([np.einsum('fevi,fi->fev',delta,right),np.einsum('fevi,fi->fev',delta,vertical),np.einsum('fevi,fi->fev',delta,forward)],axis=-1);visible=segment_visible(coords[:,:,0],coords[:,:,1],tan_h,tan_v,1.);frames=np.flatnonzero(visible.any(1));rows.append({'additional_down_pitch_deg':degrees,'frames_with_visible_new_cut':len(frames),'maximum_visible_new_cut_edges':int(visible.sum(1).max()),'first_visible_key':int(frames[0])if len(frames)else None})
    return {'schema':'sub01.fp-arms-derived-frustum.v1','clip_sha256':clip.sha256,'original_mask_scope':'full_arm','arm_weight_threshold':.5,'keys':len(times),'original_cut_edges':len(pairs),'horizontal_fov_deg':75,'aspect':16/9,'near_cm':1,'actual_iris_source_camera':True,'pitches':rows,'native_ready':False}
