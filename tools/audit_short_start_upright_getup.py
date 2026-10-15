"""Bounded source-only written bridge proof, with unchanged main physical rules."""
from pathlib import Path
import hashlib,json,sys,time


def run():
    start=time.monotonic();root=Path('/workspace/sub01-home-private/upright-footrest-full-9cd')
    sys.path[:0]=[str(root/'tools'),'/home/unreal/runtime-tools','/workspace/sub01-home-private/upright-footrest-python/scipy-1.14.1-cp311']
    import numpy as np
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    import life_gltf as G
    import export_seat_fit_source as E
    import fit_seat_pose_trial as T
    import fit_seat_pelvis_pitch as P
    import solve_seat_pose_anatomical as A
    import solve_seated_typing_arm_ik as S
    import recheck_seat_fit_main_rule as R
    from shorten_upright_getup_start import derive,SOURCE_SHA
    from solve_upright_footrest_transitions import OWNER_SHA,FOOT_SHA
    from home_asset_audit import read_gltf
    from structural_rail_source_patch import accessor,world_matrices,transformed
    from closed_footrest_contact import ClosedFootrest
    source=Path('/workspace/sub01-home-private/upright-transition-getup-derived-reverse-r2/SUB01_GetUp_upright_footrest_DerivedReverse.glb')
    owner=Path('/workspace/sub01-home-private/owner-shoulder-derived-r3/owner-shoulder-derived.glb')
    footrest=Path('/workspace/sub01-home-private/reference-footrest-source-r5/reference-footrest.glb')
    desk=Path('/workspace/sub01-home-private/out/real-office-bundle/desk.glb')
    for path,sha in [(source,SOURCE_SHA),(owner,OWNER_SHA),(footrest,FOOT_SHA)]:assert hashlib.sha256(path.read_bytes()).hexdigest()==sha
    strong=(root/'strong-validator.py').read_bytes();assert hashlib.sha256(strong).hexdigest()=='dd95f1b1a8c3fc9a7d08b6d599985b86440c84752d85ae9f12fa8d480397a18f'
    out=Path('/workspace/sub01-home-private/upright-getup-short-start-r1');out.mkdir(exist_ok=False)
    old=G.Gltf(source);doc,binary,report=derive(old.doc,bytes(old.buffers[0]));path=out/'SUB01_GetUp_upright_footrest_ShortStart.glb';G.write_glb(path,doc,binary)
    def checkpoint(phase):
        report.update(phase=phase,elapsed_s=time.monotonic()-start);(out/'short-start-proof.json').write_text(json.dumps(report,indent=2,default=lambda x:x.tolist()if hasattr(x,'tolist')else str(x))+'\n')
    report.update(written_glb=str(path),written_glb_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),owner_sha256=OWNER_SHA)
    E.OWNER=owner;base=E.Source.load(root/'private-audit/seat-fit-source.npz');g=G.Gltf(path)
    key_times=np.asarray(g.animation().key_times());dense=np.linspace(0,.2,25);times=np.unique(np.concatenate((key_times,dense)))
    W,_=E.joint_worlds(g,base.names,times);oldW,_=E.joint_worlds(old,base.names,np.asarray(old.animation().key_times()));B=np.linalg.inv(base.ibm)
    # Only bridge poses are new. Every retained active key must equal its mapped original.
    written_keys,_=E.joint_worlds(g,base.names,key_times)
    mapping=report['retained_active_key_mapping'];identity=max(float(np.max(np.abs(written_keys[r['new_key']]-oldW[r['original_key']])))for r in mapping)
    assert identity<1e-12
    src,_=P.clip_source(base,path,times);offset=np.asarray([-3.875,32.5]);cushion,_=P.load_cushion();cushion=np.asarray(cushion);cushion[...,2]+=2.5001
    fit=P.SeatFit(src,cushion,T.keycaps_from_glb(),tuple(-offset),support_z=2.5);measure=A.FastMeasure(fit.trial);A.fast_trial(fit.trial,measure)
    angle=A.joint_angles(W,B,base.names)
    old_times=np.asarray(old.animation().key_times());u=np.arange(7)/6;u=u*u*u*(u*(u*6-15)+10)
    mapped_old=np.concatenate((u*old_times[27],old_times[28:]))
    original_times=(old_times[-1]-np.interp(times,key_times,mapped_old))/1.3
    raw=G.Gltf(root/'web/room/mh_mx/room_mx_stand_to_sit.glb');captureW,_=E.joint_worlds(raw,base.names,original_times)
    excess=A.limit_excess(angle,A.joint_angles(captureW,B,base.names));bone=A.bone_length_error_cm(fit.sk,oldW[:1],W)
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
    foot,fmat=geometry(footrest);foot[...,1]+=8.692038729505747;closed=ClosedFootrest(foot,labels[str(footrest)])
    n=np.cross(foot[:,1]-foot[:,0],foot[:,2]-foot[:,0]);n/=np.linalg.norm(n,axis=1,keepdims=True)
    top=foot[(n[:,2]>.99)&(np.ptp(foot[...,2],axis=1)<1e-5)&(np.min(np.abs(foot[:,0,2,None]-np.array([14.5,14.7])),axis=1)<1e-5)].copy();top[...,:2]-=offset;finite=T.Surface(top)
    def support(xy):
        over,z=finite.height(xy);return np.ones(len(xy),bool),np.where(over,z,2.5)
    fit.trial.support_height=support;metrics=measure.metrics(W);V=R.load_main_validator(strong);seated=np.flatnonzero(times<=.200001)
    verdicts=[R.judge_frame(V,R.frame_regions(metrics,int(i)))for i in seated]
    chair=S.load_complete_chair(S.load_chair());ct=chair['triangles_cm'].copy();ct[...,2]+=2.5001;cn=np.cross(ct[:,1]-ct[:,0],ct[:,2]-ct[:,0]);flip=np.sum(cn*chair['face_normals'],axis=1)<0;ct[flip]=ct[flip][:,[0,2,1]]
    dt,dmat=geometry(desk)
    def tree(tri):return BVHTree.FromPolygons([Vector(p)for p in tri.reshape(-1,3)],[(3*i,3*i+1,3*i+2)for i in range(len(tri))],all_triangles=True,epsilon=0)
    scenes={name:(tree(t),mat,t.min((0,1)),t.max((0,1)))for name,t,mat in [('chair',ct,chair['material']),('footrest',foot,fmat),('desk',dt,dmat)]}
    collisions={name:{'minimum_margin_cm':3.,'frames_checked':0,'failing_frames':[]}for name in scenes};skin=P.owner_skin(stride=6);floor_min=float('inf')
    report.update(checked_times_s=times.tolist(),bridge_dense_hz=120,retained_active_written_matrix_max_error=identity,bone_length_error_cm=bone,anatomical_excess_max_deg=float(excess.max()),strong_seated_all_pass=all(v is None for v in verdicts),strong_seated_failures=[{'sample':int(i),'reason':v}for i,v in zip(seated,verdicts)if v is not None],collision_sampling='Every6th owner vertex, all written keys plus120Hz bridge; original strict zero penetration, chair fabric2.5cm allowance unchanged')
    checkpoint('Written anatomy and finite support checked')
    for f,world in enumerate(W):
        if time.monotonic()-start>103:break
        pts=E.to_ue(P.skin_points(skin,base.ibm,world[None]))[0];pts[:,:2]+=offset;floor_min=min(floor_min,float(pts[:,2].min()))
        for name,(bvh,mats,lo,hi)in scenes.items():
            row=collisions[name];minimum=3.
            for pi in np.flatnonzero(np.all((pts>=lo-3)&(pts<=hi+3),axis=1)):
                p=pts[pi];loc,normal,index,distance=bvh.find_nearest(Vector(p));signed=closed.signed_distance(p,float(distance))if name=='footrest'else distance*(-1 if(Vector(p)-loc).dot(normal)<0 else 1);allowed=-2.5 if name=='chair'and mats[index]=='chair_fabric'else 0.;margin=signed-allowed
                if margin<minimum:minimum=margin
                if margin<row['minimum_margin_cm']:
                    row['witness']={'sample':f,'time_s':float(times[f]),'body_point_ue_cm':p.tolist(),'nearest_ue_cm':list(loc),'triangle':int(index),'material':str(mats[index])}
            row['frames_checked']+=1;row['minimum_margin_cm']=min(row['minimum_margin_cm'],minimum)
            if minimum<0:row['failing_frames'].append(f)
        if f%15==0:report['collision']=collisions;checkpoint('Collision sample'+str(f))
    report.update(collision=collisions,actual_floor_min_z_cm=floor_min,geometry_and_main_support_pass=bool(report['strong_seated_all_pass']and excess.max()==0 and bone<1e-5 and floor_min>=2.5 and all(r['frames_checked']==len(W)and not r['failing_frames']for r in collisions.values())),pending=['Standing runtime Idle seam','Velocity/naturalness and explicit handshape/selfcontact','Coherent typing chain and native verification'])
    checkpoint('Bounded written short-start source proof complete');print('ACTUAL_SHORT_START_SOURCE_RESULT',report['geometry_and_main_support_pass'],flush=True)

if __name__=='__main__':run()
