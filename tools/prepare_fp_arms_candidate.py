"""Bounded source arms packet with real eye/frustum boundary audit; no native writes."""
import hashlib,json,sys,gzip,math,time
from pathlib import Path


def segment_visible(a,b,tan_h,tan_v,near):
    import numpy as np
    low=np.zeros(a.shape[:-1]);high=np.ones_like(low);valid=np.ones_like(low,dtype=bool)
    # Camera coordinates right/up/forward. Each plane is f(point)>=0.
    for axis,sgn,k,offset in [(2,1,0,-near),(0,1,tan_h,0),(0,-1,tan_h,0),(1,1,tan_v,0),(1,-1,tan_v,0)]:
        f0=sgn*a[...,axis]+k*a[...,2]+offset;f1=sgn*b[...,axis]+k*b[...,2]+offset;delta=f1-f0
        valid&=~((delta==0)&(f0<0));u=np.divide(-f0,delta,out=np.zeros_like(delta),where=delta!=0);low=np.where(delta>0,np.maximum(low,u),low);high=np.where(delta<0,np.minimum(high,u),high)
    return valid&(low<=high)


def run():
    start=time.monotonic();root=Path('/workspace/sub01-home-private/upright-footrest-full-9cd');sys.path[:0]=[str(root/'tools'),'/home/unreal/runtime-tools','/workspace/sub01-home-private/upright-footrest-python/scipy-1.14.1-cp311']
    import numpy as np
    import life_gltf as G
    import export_seat_fit_source as E
    import fit_seat_pelvis_pitch as P
    from derive_fp_arms_mesh import derive,OWNER_SHA
    from audit_fp_arms_source import mask_triangles,new_cut_edges
    # Meaningful geometry tests: protect a hand triangle crossing the mask; distinguish original open edges/new cut.
    j=np.asarray([[2,0,0,0],[0,0,0,0],[0,0,0,0],[1,0,0,0]]);w=np.asarray([[1.,0,0,0]]*4);idx=np.asarray([[0,1,2],[1,2,3]]);keep,must,_=mask_triangles(j,w,idx,[1,2],[2],.75);assert keep.tolist()==[True,False]and must.tolist()==[True,False]
    square=np.asarray([[0,0,0],[1,0,0],[1,1,0],[0,1,0]],float);edges,_=new_cut_edges(square,np.asarray([[0,1,2],[0,2,3]]),np.asarray([True,False]));assert {tuple(sorted(e))for e in edges}=={(0,2)}
    assert segment_visible(np.asarray([[-2.,0,1]]),np.asarray([[2.,0,1]]),1.,1.,.01)[0]
    assert not segment_visible(np.asarray([[0.,0,-1]]),np.asarray([[0.,0,-2]]),1.,1.,.01)[0]
    owner=G.Gltf('/workspace/sub01-home-private/owner-shoulder-derived-r3/owner-shoulder-derived.glb');assert owner.sha256==OWNER_SHA
    raw=G.Gltf('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/owner-with-clips-unreal.glb');assert raw.sha256=='45e917725f02836dee6d051d9b47dd2785208c78b503fa935ddb322fe69adea8';raw.doc['animations']=[a for a in raw.doc['animations']if a['name']=='typing']
    audit=json.loads(gzip.decompress(Path('/workspace/sub01-home-private/fp-arms-source-audit-r1/arms-mask-phase-audit.json.gz').read_bytes()));assert audit['owner_sha256']==OWNER_SHA
    base=E.Source.load(root/'private-audit/seat-fit-source.npz');assert list(base.names)==[E.short(owner.nodes[i]['name'])for i in owner.doc['skins'][0]['joints']];times=np.asarray(raw.animation().key_times());W,_=E.joint_worlds(raw,base.names,times);ibm=np.asarray(base.ibm);prim=owner.doc['meshes'][0]['primitives'][0];attrs=prim['attributes'];pos=E.accessor(owner,attrs['POSITION']);joints=E.accessor(owner,attrs['JOINTS_0']).astype(int);weights=E.accessor(owner,attrs['WEIGHTS_0']);weights/=weights.sum(1,keepdims=True)
    eye_doc=json.loads(Path('/home/unreal/runtime-tools/fp-arms-iris-witness.json').read_text());assert eye_doc['source_sha256']==raw.sha256
    head=owner.doc['meshes'][0]['primitives'][1];hp=E.accessor(owner,head['attributes']['POSITION']);hj=E.accessor(owner,head['attributes']['JOINTS_0']).astype(int);hw=E.accessor(owner,head['attributes']['WEIGHTS_0']);hw/=hw.sum(1,keepdims=True)
    # These selected eye vertices are unchanged by the garment-only repair.
    for field in ['POSITION','JOINTS_0','WEIGHTS_0','TEXCOORD_0']:
        assert np.array_equal(E.accessor(owner,head['attributes'][field]),E.accessor(raw,raw.doc['meshes'][0]['primitives'][1]['attributes'][field]))
    eye=[]
    for point in eye_doc['points']:
        ids=np.asarray(point['vertices'],int);skin=(hp[ids],hj[ids],hw[ids]);eye.append(np.einsum('fvi,v->fi',P.skin_points(skin,ibm,W),np.asarray(point['weights'])))
    camera=E.to_ue(np.mean(eye,axis=0));head_j=base.names.index('Head');M=W[:,head_j]@ibm[head_j];forward=E.to_ue_dir(M[:,:3,2]);up=E.to_ue_dir(M[:,:3,1]);forward/=np.linalg.norm(forward,axis=1,keepdims=True);up-=forward*np.sum(up*forward,axis=1)[:,None];up/=np.linalg.norm(up,axis=1,keepdims=True);right=np.cross(forward,up);tan_h=math.tan(math.radians(75/2));tan_v=tan_h/(16/9)
    results=[]
    for row in audit['variants']:
        if not row['kept_triangles']:continue
        pairs=np.asarray(row['new_cut_source_vertex_pairs'],int);ids,inv=np.unique(pairs,return_inverse=True);boundary=E.to_ue(P.skin_points((pos[ids],joints[ids],weights[ids]),ibm,W));boundary=boundary[:,inv.reshape(-1,2)]
        delta=boundary-camera[:,None,None,:];pitches=[]
        for angle in [0,20,35,50,65]:
            a=math.radians(angle);f=math.cos(a)*forward-math.sin(a)*up;u=math.cos(a)*up+math.sin(a)*forward
            c=np.stack([np.einsum('fevi,fi->fev',delta,right),np.einsum('fevi,fi->fev',delta,u),np.einsum('fevi,fi->fev',delta,f)],axis=-1);visible=segment_visible(c[:,:,0],c[:,:,1],tan_h,tan_v,1.);frames=np.flatnonzero(visible.any(1));witness=None
            if len(frames):
                frame=int(frames[0]);edge=int(np.flatnonzero(visible[frame])[0]);witness={'frame':frame,'time_s':float(times[frame]),'source_vertex_edge':pairs[edge].tolist(),'camera_world_ue_cm':camera[frame].tolist(),'edge_world_ue_cm':boundary[frame,edge].tolist()}
            pitches.append({'additional_down_pitch_deg':angle,'frames_with_visible_new_cut':len(frames),'maximum_visible_new_cut_edges':int(visible.sum(1).max()),'first_witness':witness})
        results.append({'scope':row['scope'],'threshold':row['threshold'],'triangles':row['kept_triangles'],'new_cut_edges':len(pairs),'pitches':pitches})
    # Preserve the most complete original arm/sleeve geometry as a clearly unready source variant.
    chosen=[r for r in audit['variants']if r['scope']=='full_arm'and r['threshold']==.5]
    doc,binary,proof=derive(owner.doc,bytes(owner.buffers[0]),chosen);out=Path('/workspace/sub01-home-private/fp-arms-candidate-r1');out.mkdir(exist_ok=False);path=out/'SUB01_FirstPersonArms_SourceCandidate.glb';G.write_glb(path,doc,binary)
    report=proof|{'schema':'sub01.fp-arms-source-packet.v1','owner_sha256':OWNER_SHA,'original_canonical_owner_sha256':raw.sha256,'output_glb':str(path),'output_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'selected_scope':'full_arm','selected_arm_weight_threshold':.5,'hand_triangles_protected':True,'geometry_tests_pass':True,'boundary_frustum':results,'frustum_assumptions':{'horizontal_fov_deg':75,'aspect':16/9,'near_cm':1,'orientation':'captured actual Head skin transform + specified additional downlook; not native camera input'},'captured_iris_camera_path_ue_cm':camera.tolist(),'captured_duration_s':float(times[-1]),'captured_keys':len(times),'native_ready':False,'skin_contact_accepted':False,'pending':['New sleeve boundary visual inspection','Real keycap/curved mouse full hand contact and penetration','Native first-person camera placement and hands-only visual/input acceptance'],'elapsed_s':time.monotonic()-start};(out/'arms-source-packet.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'output_sha256':report['output_sha256'],'elapsed_s':report['elapsed_s'],'tests':True,'frustum':results}),flush=True)

if __name__=='__main__':run()
