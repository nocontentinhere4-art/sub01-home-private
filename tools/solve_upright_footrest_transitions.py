"""Bounded DERIVED captured transitions onto the proven finite footrest Idle.

Source-only. Original repository-fitted source clips/Claude tools/native gates remain untouched. Finger
rotations blend authentic capture endpoints (not byte-identical); bone lengths,
nonroot translations and scale remain fixed. Every candidate is a proposal until
all written-source contact/anatomy/collision checks have passed.
"""
import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

IDLE_SHA='5354462f74fe3d4e417fc5c8975144e9c3bd69daa2a08c08757ef7929c38a0da'
OWNER_SHA='831790a62b81e7e2faa5a201e04740d0911c5bfebd49aa03b124808521e3a2b1'
FOOT_SHA='d805f7bcc58b919734a966e084d16aa509655f3d7df8c5088efbd6a17d425c50'


def rotation_with_preserved_scale(rotation, reference):
    """A world orientation is not a world scale: preserve every source column norm."""
    scales=[math.sqrt(sum(reference[r][c]**2 for r in range(3)))for c in range(3)]
    return [[rotation[r][c]*scales[c]for c in range(3)]for r in range(3)]


def run(root,owner,idle,footrest,desk,output,role,seconds=105):
    start=time.monotonic();root=Path(root);output=Path(output);output.mkdir(exist_ok=False)
    sys.path[:0]=[str(root/'tools'),str(Path(__file__).resolve().parent),'/workspace/sub01-home-private/upright-footrest-python/scipy-1.14.1-cp311']
    import numpy as np
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    import export_seat_fit_source as E
    import fit_seat_pose_trial as T
    import fit_seat_pelvis_pitch as P
    import solve_seat_pose_anatomical as A
    import solve_seated_typing_arm_ik as S
    import recheck_seat_fit_main_rule as R
    import life_gltf as G
    from home_asset_audit import read_gltf
    from structural_rail_source_patch import accessor,world_matrices,transformed
    from closed_footrest_contact import ClosedFootrest
    for path,sha in [(owner,OWNER_SHA),(idle,IDLE_SHA),(footrest,FOOT_SHA)]:
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError('Pinned source differs '+str(path))
    strong=(root/'strong-validator.py').read_bytes()
    if hashlib.sha256(strong).hexdigest()!='dd95f1b1a8c3fc9a7d08b6d599985b86440c84752d85ae9f12fa8d480397a18f':raise ValueError('Strong main rule differs')
    V=R.load_main_validator(strong);E.OWNER=Path(owner);base=E.Source.load(root/'private-audit/seat-fit-source.npz')
    filename,source_sha,end,leg_windows={'SitDown':('room_mx_stand_to_sit.glb','68086a284360c59f03479346f06375ad3ed8d4b16647388f078e5e54a4909cb0','end',{'left':(0,20),'right':(20,40)}),'GetUp':('room_mx_sit_to_stand.glb','b8d9c1803116cf06b779a0e7db7898a9e8512d6e29054a953de66f0750713470','start',{'left':(8,28),'right':(28,48)})}[role]
    path=root/'web/room/mh_mx'/filename
    if hashlib.sha256(path.read_bytes()).hexdigest()!=source_sha:raise ValueError('Exact authentic captured transition required')
    src,g=P.clip_source(base,path);W0=src.joint_world;source_times=np.asarray(src.times);times=(source_times-source_times[0])*1.3;F=len(W0);B=np.linalg.inv(base.ibm);capture_angles=A.joint_angles(W0,B,src.names)
    report={'schema':'sub01.upright-footrest-transition.v1','role':role,'source_sha256':source_sha,'idle_sha256':IDLE_SHA,'owner_sha256':OWNER_SHA,'footrest_sha256':FOOT_SHA,'frames':F,'source_ready':False,'native_imported':False,'runtime_ready':False,'derived':True,'source_is_existing_repo_fitted_clip_not_provider_raw':True,'capture_finger_bytes_unchanged':False,'finger_edit':'Existing source local-quaternion seam blend between authentic transition and Idle only; no new finger pose/scale','leg_windows':leg_windows,'source_duration_s':float(source_times[-1]-source_times[0]),'derived_duration_s':float(times[-1]),'uniform_capture_time_scale':1.3,'retime_reason':'Functional two-foot step onto actual14.7cm support; slows authentic captured body/hand motion uniformly','global_floor_z_cm':2.5,'actual_chair_lift_cm':2.5001,'actual_desk_top_cm':84.5}
    def checkpoint(phase):
        report.update(phase=phase,elapsed_s=time.monotonic()-start);(output/'transition-report.json').write_text(json.dumps(report,indent=2,default=lambda v:v.tolist()if hasattr(v,'tolist')else str(v))+'\n')
    checkpoint('loading exact physical source surfaces')
    offset=np.asarray([-3.875,32.5]);cushion,_=P.load_cushion();cushion=np.asarray(cushion);cushion[...,2]+=2.5001;keys=T.keycaps_from_glb();fit=P.SeatFit(src,cushion,keys,tuple(-offset),support_z=2.5);measure=A.FastMeasure(fit.trial);A.fast_trial(fit.trial,measure)
    model=A.PoseModel(fit,measure)
    # Raw captured standing feet would intersect the actual footrest. This bounded
    # approach keeps them behind its rear edge; full collision/anatomy below decides
    # whether it is acceptable. Every original parameter bound stays unchanged.
    standing_params=np.asarray([16.,4.,0.,0.,9.5,-13.,4.,0.,0.])
    if A.param_bounds_excess(standing_params):raise ValueError('Original pose edit bounds exceeded')
    floor_pose=model.apply(W0,standing_params)
    floor_pose[:,:,2,3]-=.02 # measured staggered approach: whole body only2cm behind original
    standing_delta={side:(E.to_ue(floor_pose[:,fit.sk.j(chain[2]),:3,3])-E.to_ue(W0[:,fit.sk.j(chain[2]),:3,3]))[:,:2]for side,chain in T.LEGS.items()};report['standing_total_world_ankle_xy_max_abs_delta_cm']={side:float(np.abs(d).max())for side,d in standing_delta.items()}
    if any(np.abs(d).max()>15.+1e-8 for d in standing_delta.values()):raise ValueError('Standing total world ankle edit exceeds original15cm bound')
    idle_g=G.Gltf(Path(idle));period=float(idle_g.animation().key_times()[-1]);sample_times=np.mod(times-times[-1]if end=='end'else times,period);target,_=E.joint_worlds(idle_g,src.names,sample_times)
    hips=P.hips_track(g,source_times);captured_weight=P.seated_weight(hips,float(hips[:,1].min()),float(hips[:,1].max()))
    weight=np.clip((captured_weight-.005)/.99,0,1)
    armature=P.armature_world(g,g.by_name['mixamorig:Hips']);pose=P.seam_blend_pose(fit.sk,armature,floor_pose,target,weight)
    def smooth(x):return P.smootherstep(np.clip(x,0,1))
    # A physically constrained step: lift before crossing the measured hardware,
    # move above it, then lower onto the actual support. No cosmetic sine/wobble.
    # Windows retain the capture's left-first/right-later motion order.
    step_top_cm=17.3
    foot_progress={};reach={};anchors={};swivel_paths={};leg_pose_edit={};complete_skin=P.owner_skin(stride=1);shoe_skins={}
    for side,prefix in [('left','Left'),('right','Right')]:
        ids=[i for i,n in enumerate(src.names)if n in (prefix+'Foot',prefix+'ToeBase',prefix+'Toe_End')];mask=(np.isin(complete_skin[1],ids)&(complete_skin[2]>0)).any(1);mask|=(complete_skin[0][:,1]<.25)&(complete_skin[0][:,0]*(1 if side=='left'else -1)>0);shoe_skins[side]=tuple(v[mask]for v in complete_skin)
    def bounded_leg(worlds,side,chain,point,matrix):
        # Preserve the captured/blended bend plane; search ONLY the original
        # +/-25deg bounded swivel. Dynamic programming avoids per-frame pole jumps.
        states=np.linspace(-25.,25.,21);poses=[];costs=[];raw_reach=[];raw_margin=[];raw_edit=[];raw_twist=[]
        hip=worlds[:,fit.sk.j(chain[0]),:3,3];knee=worlds[:,fit.sk.j(chain[1]),:3,3];axis=point-hip
        for swivel in states:
            pole=hip+np.einsum('fij,fj->fi',P.rodrigues(axis,np.full(F,math.radians(swivel))),knee-hip)
            candidate,reached,length,distance=fit.sk.two_bone_pose(worlds.copy(),chain,point,pole,end_world_rot=matrix)
            # Orient the leg about its solved axes from the actual knee plane.
            # The inherited minimum-vector rotation retained bad captured twist.
            uj,lj,fj=(fit.sk.j(n)for n in chain);u=candidate[:,lj,:3,3]-candidate[:,uj,:3,3];l=candidate[:,fj,:3,3]-candidate[:,lj,:3,3];hinge=np.cross(u,l);upper_twist=np.zeros(F)
            for bone,axis in [(uj,u),(lj,l)]:
                axis=axis/np.linalg.norm(axis,axis=1,keepdims=True);current=np.einsum('fij,j->fi',A.unit(candidate[:,bone,:3,:3])@A.unit(B[bone,:3,:3]).T,np.asarray([1.,0.,0.]));current-=axis*np.sum(current*axis,axis=1)[:,None];desired=hinge.copy();desired[np.linalg.norm(desired,axis=1)<1e-10]=current[np.linalg.norm(desired,axis=1)<1e-10];current/=np.linalg.norm(current,axis=1,keepdims=True);desired/=np.linalg.norm(desired,axis=1,keepdims=True);twist=np.arctan2(np.sum(axis*np.cross(current,desired),axis=1),np.sum(current*desired,axis=1));candidate[:,bone,:3,:3]=P.rodrigues(axis,twist)@candidate[:,bone,:3,:3]
                if bone==uj:upper_twist=np.degrees(twist)
            # Functional heel/toe roll: nearest rotation inside unchanged ankle ROM.
            # Every sole height is remeasured below; no floor relabelling.
            from scipy.spatial.transform import Rotation
            fj,kj=fit.sk.j(chain[2]),fit.sk.j(chain[1]);relative=A.relative_anat(candidate,B,fj,kj);e=A.euler_xzy(relative);e[:,0]=np.clip(e[:,0],-19.95,49.95);e[:,1]=np.clip(e[:,1],-34.95,14.95)if side=='left'else np.clip(e[:,1],-14.95,34.95)
            rotation=A.unit(candidate[:,kj,:3,:3])@A.unit(B[kj,:3,:3]).T@Rotation.from_euler('XZY',e,degrees=True).as_matrix()@A.unit(B[fj,:3,:3]);old=candidate[:,fj].copy();candidate[:,fj,:3,:3]=rotation*np.linalg.norm(old[:,:3,:3],axis=1)[:,None,:];carry=candidate[:,fj]@np.linalg.inv(old)
            for child in fit.sk.subtree(fj):
                if child!=fj:candidate[:,child]=carry@candidate[:,child]
            ang=A.joint_angles(candidate,B,src.names);ex=np.zeros(F)
            for key,value in ang.items():
                if not key.startswith(side+'_'):continue
                bounds=A.ANATOMICAL_LIMITS_DEG.get(key[len(side)+1:])
                if bounds:ex+=np.maximum(0,bounds[0]-value)+np.maximum(0,value-bounds[1])
            base_swivel=weight*(6.9911210063332225 if side=='left'else -17.483631339666253)
            edit=np.abs(base_swivel+swivel)+np.abs(upper_twist);ex+=np.maximum(0,edit-25.);raw_edit.append(edit);raw_twist.append(upper_twist)
            poses.append(candidate);costs.append(ex*1e5+1e-4*swivel**2);raw_reach.append(reached);raw_margin.append((length-distance)*100)
        costs=np.asarray(costs).T;transition=(states[:,None]-states[None,:])**2*.01;score=costs[0].copy();parents=[]
        for f in range(1,F):
            v=score[:,None]+transition;prev=v.argmin(axis=0);parents.append(prev);score=costs[f]+v[prev,np.arange(len(states))]
        path=[int(score.argmin())]
        for prev in reversed(parents):path.append(int(prev[path[-1]]))
        path=np.asarray(path[::-1]);result=np.stack([poses[p][f]for f,p in enumerate(path)])
        reached=np.asarray([raw_reach[p][f]for f,p in enumerate(path)]);margin=np.asarray([raw_margin[p][f]for f,p in enumerate(path)]);swivel_paths[side]=states[path].tolist();leg_pose_edit[side]={'total_swivel_and_hinge_correction_deg':[float(raw_edit[p][f])for f,p in enumerate(path)],'additional_hinge_correction_deg':[float(raw_twist[p][f])for f,p in enumerate(path)]}
        return result,reached,margin

    for side,chain in T.LEGS.items():
        a,b=leg_windows[side];u=np.clip((np.arange(F)-a)/(b-a),0,1);move=smooth((u-.2)/.6);up=smooth(u/.2);down=smooth((u-.8)/.2);foot_progress[side]=u
        j=fit.sk.j(chain[2]);standing=floor_pose[:,j];seated=target[:,j]
        planted_standing=np.broadcast_to(standing[0 if end=='end'else -1],standing.shape).copy()
        first,last=(planted_standing,seated)if end=='end'else(seated,planted_standing)
        point=first[:,:3,3]+(last[:,:3,3]-first[:,:3,3])*move[:,None]
        high=np.maximum(first[:,1,3],last[:,1,3])+(step_top_cm-14.7)/100
        point[:,1]=np.where(u<=.2,first[:,1,3]+(high-first[:,1,3])*up,np.where(u>=.8,high+(last[:,1,3]-high)*down,high))
        qa=P.quat_from_matrix(first[:,:3,:3]);qb=P.quat_from_matrix(last[:,:3,:3]);q=P.slerp_arrays(qa[:,None],qb[:,None],move)[:,0]
        from scipy.spatial.transform import Rotation
        matrix=np.tile(np.eye(4),(F,1,1));matrix[:,:3,:3]=np.asarray([rotation_with_preserved_scale(r,ref)for r,ref in zip(Rotation.from_quat(q).as_matrix(),first[:,:3,:3])])
        anchors[side]=(point,matrix)
        pose,reached,reach_margin=bounded_leg(pose,side,chain,point,matrix)
        # Both endpoint foot poses use unchanged bind-local toe articulation.
        toe=fit.sk.j(T.LEGS[side][2].replace('Foot','ToeBase'));toe_end=fit.sk.j(T.LEGS[side][2].replace('Foot','Toe_End'))
        pose[:,toe]=pose[:,j]@(np.linalg.inv(B[j])@B[toe]);pose[:,toe_end]=pose[:,toe]@(np.linalg.inv(B[toe])@B[toe_end])
        # Restore actual plantar clearance after heel roll, then re-solve same leg.
        for sole_iteration in range(16):
            pp=P.skin_points(shoe_skins[side],base.ibm,pose);low=E.to_ue(pp)[...,2].min(1);start_sole,end_sole=(2.55,14.75)if end=='end'else(14.75,2.55);desired=np.where(u<=.2,start_sole+(step_top_cm+.05-start_sole)*up,np.where(u>=.8,step_top_cm+.05+(end_sole-step_top_cm-.05)*down,step_top_cm+.05));lift=np.maximum(0.,desired-low)
            if lift.max()<1e-6:break
            point[:,1]+=lift/100;pose,reached,reach_margin=bounded_leg(pose,side,chain,point,matrix);pose[:,toe]=pose[:,j]@(np.linalg.inv(B[j])@B[toe]);pose[:,toe_end]=pose[:,toe]@(np.linalg.inv(B[toe])@B[toe_end])
        anchors[side]=(point,pose[:,j].copy())
        reach[side]={'all_reached':bool(reached.all()),'minimum_reach_margin_cm':float(reach_margin.min())}
    # Existing9cd geometric nonseated lift: actual skin below cushion clearance
    # is raised smoothly, then legs are re-solved to the SAME fixed foot anchors.
    total_lift=np.zeros(F)
    for iteration in range(2):
        m=measure.metrics(pose);low=np.min([np.where(m[n]['over']>0,np.nan_to_num(m[n]['lowest'],nan=np.inf),np.inf)for n in T.SEAT_PATCHES],axis=0)
        need=np.where(weight>=1,0.,np.maximum(0.,T.SEAT_BAND_CM[0]+P.SEAM_SEAT_CLEAR_CM-low));lift=P.smooth_lift(need,weight>=1)
        if not(lift>0).any():break
        total_lift+=lift;pose[:,:,1,3]+=lift[:,None]/100
        for side,chain in T.LEGS.items():
            point,matrix=anchors[side];pose,reached,reach_margin=bounded_leg(pose,side,chain,point,matrix)
            j=fit.sk.j(chain[2]);tj=fit.sk.j(chain[2].replace('Foot','ToeBase'));ej=fit.sk.j(chain[2].replace('Foot','Toe_End'));pose[:,tj]=pose[:,j]@(np.linalg.inv(B[j])@B[tj]);pose[:,ej]=pose[:,tj]@(np.linalg.inv(B[tj])@B[ej])
            reach[side]={'all_reached':bool(reached.all()),'minimum_reach_margin_cm':float(reach_margin.min()),'actual_target_error_max_cm':float(np.linalg.norm(pose[:,j,:3,3]-point,axis=1).max()*100)}
    stationary_idle=(weight>=1)&np.logical_and.reduce([u>=1 if end=='end'else u<=0 for u in foot_progress.values()]);pose[stationary_idle]=target[stationary_idle]
    for side,edit in leg_pose_edit.items():
        for i in np.flatnonzero(stationary_idle):edit['total_swivel_and_hinge_correction_deg'][i]=abs(6.9911210063332225 if side=='left'else -17.483631339666253);edit['additional_hinge_correction_deg'][i]=0.
    report['actual_cushion_derived_nonseated_lift_cm']=total_lift.tolist();report['bounded_leg_pose_edit']=leg_pose_edit;report['leg_edit_excess_deg']=max(max(v['total_swivel_and_hinge_correction_deg'])for v in leg_pose_edit.values())-25.;report['bounded_derived_hip_swivel_deg']=swivel_paths
    report.update(standing_parameters=dict(zip(A.PARAMS,standing_params)),standing_whole_body_delta_ue_cm=[0.,2.,0.],derived_foot_clearance_sole_height_cm=step_top_cm,functional_heel_roll_uses_same_anatomical_limits=True,leg_reach=reach,quaternion_seam_window_frames=np.flatnonzero((weight>0)&(weight<1)).tolist(),captured_body_weight=captured_weight.tolist())
    labels={}
    def geometry(path):
        d,b=read_gltf(Path(path));m=world_matrices(d);tris=[];materials=[];parts=[]
        for ni,n in enumerate(d['nodes']):
            if 'mesh'not in n:continue
            mat=np.asarray(m[ni]);normal_mat=np.linalg.inv(mat[:3,:3]).T
            for p in d['meshes'][n['mesh']]['primitives']:
                pos=np.asarray([transformed(m[ni],v)for v in accessor(d,b,p['attributes']['POSITION'])])*100;pos=pos[:,[0,2,1]]
                normals=np.asarray(accessor(d,b,p['attributes']['NORMAL']))@normal_mat.T;normals=normals[:,[0,2,1]]
                for ids in np.asarray(accessor(d,b,p['indices']),int).reshape(-1,3):
                    tri=pos[ids].copy();normal=np.cross(tri[1]-tri[0],tri[2]-tri[0])
                    if np.dot(normal,normal)==0:continue
                    if np.dot(normal,normals[ids].sum(0))<0:tri=tri[[0,2,1]]
                    tris.append(tri);materials.append(d['materials'][p['material']]['name']);parts.append({'node':ni,'name':n.get('name')})
        labels[str(path)]=parts;return np.asarray(tris),np.asarray(materials)
    # Prefer minimal retraction around real solid geometry to dragging hanging
    # fingers upward through the tabletop. Captured wrist/finger rotations stay.
    desk_tri,desk_material=geometry(desk);desk_bvh=BVHTree.FromPolygons([Vector(p)for p in desk_tri.reshape(-1,3)],[(3*i,3*i+1,3*i+2)for i in range(len(desk_tri))],all_triangles=True,epsilon=0)
    part_nodes=np.asarray([r['node']for r in labels[str(desk)]]);part_boxes=[(desk_tri[part_nodes==n].min((0,1)),desk_tri[part_nodes==n].max((0,1)))for n in np.unique(part_nodes)];hand_adjustments={}
    def hand_margins(hs,world):
        points=E.to_ue(P.skin_points(hs,base.ibm,world));points[...,:2]+=offset;result=[]
        for pts in points:
            possible=np.zeros(len(pts),bool)
            for lo,hi in part_boxes:possible|=np.all((pts>=lo)&(pts<=hi),axis=1)
            minimum=3.
            for p in pts[possible]:
                loc,normal,index,distance=desk_bvh.find_nearest(Vector(p));signed=distance*(-1 if(Vector(p)-loc).dot(normal)<0 else 1);minimum=min(minimum,signed)
            result.append(minimum)
        return np.asarray(result)
    for side,prefix in [('left','Left'),('right','Right')]:
        hand_ids=[i for i,n in enumerate(src.names)if n.startswith(prefix+'Hand')];mask=(np.isin(complete_skin[1],hand_ids)&(complete_skin[2]>0)).any(1);hs=tuple(v[mask]for v in complete_skin);baseline=hand_margins(hs,pose)
        if baseline.min()>=0:hand_adjustments[side]={'unchanged':True,'minimum_margin_cm':float(baseline.min())};continue
        gate=P.smooth_lift(np.maximum(0.,.05-baseline),stationary_idle);gate/=gate.max();hand=fit.sk.j(prefix+'Hand');elbow=fit.sk.j(prefix+'ForeArm');point0=pose[:,hand,:3,3].copy();pole=pose[:,elbow,:3,3].copy();matrix=pose[:,hand].copy();attempts=[];selected=None
        options=sorted([(back,up)for back in range(0,11,2)for up in range(0,7,2)if back or up],key=lambda v:(v[0]**2+v[1]**2,v[1]))
        for back,up in options:
            point=point0.copy();point[:,2]-=back*gate/100;point[:,1]+=up*gate/100;candidate,ok,_,_=fit.sk.two_bone_pose(pose.copy(),(prefix+'Arm',prefix+'ForeArm',prefix+'Hand'),point,pole,end_world_rot=matrix);margin=hand_margins(hs,candidate);attempts.append({'back_cm':back,'up_cm':up,'minimum_margin_cm':float(margin.min()),'all_reached':bool(ok.all())})
            if ok.all()and margin.min()>=.05:selected=(candidate,back,up,margin);break
        report['hand_support_preflight']={'side':side,'full_hand_vertices':int(mask.sum()),'attempts':attempts};checkpoint('actual complete hand desk-clearance search')
        if selected is None:raise ValueError('No bounded captured-wrist placement clears actual desk')
        pose,back,up,margin=selected;hand_adjustments[side]={'toward_body_cm':back,'up_cm':up,'per_frame_weight':gate.tolist(),'minimum_margin_cm':float(margin.min()),'captured_wrist_world_rotation_preserved':True,'finger_local_rotations_preserved':True}
    report['actual_desk_derived_wrist_adjustments']=hand_adjustments
    checkpoint('captured body and finite-clearance foot trajectory derived')
    out=output/('SUB01_'+role+'_upright_footrest.glb');P.write_clip(g,fit.sk,pose,times,out,'SUB01_'+role+'_upright_footrest',{'derived':True,'native_ready':False,'source_capture_sha256':source_sha,'physical_idle_sha256':IDLE_SHA},{})
    W,_=E.joint_worlds(G.Gltf(out),src.names,times-times[0]);angles=A.joint_angles(W,B,src.names);excess=A.limit_excess(angles,capture_angles)
    fps=(F-1)/(times[-1]-times[0]);raw_kin=P.pelvis_kinematics(fit.sk,W0,(F-1)/(source_times[-1]-source_times[0]));derived_kin=P.pelvis_kinematics(fit.sk,W,fps)
    kin_ratio=max(float(derived_kin['acc_cm_s2'].max()/raw_kin['acc_cm_s2'].max()),float(derived_kin['ang_acc_deg_s2'].max()/raw_kin['ang_acc_deg_s2'].max()))
    report['pelvis_peak_acceleration_ratio_to_authentic_capture']=kin_ratio
    report.update(written_glb=str(out),written_glb_sha256=hashlib.sha256(out.read_bytes()).hexdigest(),written_world_max_error_cm=float(np.max(np.abs(W[:,:,:3,3]-pose[:,:,:3,3]))*100),bone_length_error_cm=A.bone_length_error_cm(fit.sk,W0,W),anatomy=A.angle_summary(angles,capture_angles),anatomical_excess_max_deg=float(excess.max()),anatomical_failing_frames=np.flatnonzero(excess>0).tolist(),measured_joint_angles_deg={k:v.tolist()for k,v in angles.items()})
    foot,foot_material=geometry(footrest);foot[...,1]+=8.692038729505747;closed=ClosedFootrest(foot,[r['node']for r in labels[str(footrest)]])
    n=np.cross(foot[:,1]-foot[:,0],foot[:,2]-foot[:,0]);n/=np.linalg.norm(n,axis=1,keepdims=True);top=foot[(n[:,2]>.99)&(np.ptp(foot[...,2],axis=1)<1e-5)&(np.min(np.abs(foot[:,0,2,None]-np.array([14.5,14.7])),axis=1)<1e-5)].copy();top[...,:2]-=offset
    finite=T.Surface(top)
    def support(xy):
        over,z=finite.height(xy);return np.ones(len(xy),bool),np.where(over,z,2.5)
    fit.trial.support_height=support;metrics=measure.metrics(W)
    feet_on_target=np.logical_and.reduce([u>=1 if end=='end'else u<=0 for u in foot_progress.values()]);seated_mask=(weight>=1)&feet_on_target
    verdicts=[R.judge_frame(V,R.frame_regions(metrics,i))for i in np.flatnonzero(seated_mask)]
    report.update(strong_seated_mask_frames=np.flatnonzero(seated_mask).tolist(),strong_seated_all_pass=bool(seated_mask.any()and all(v is None for v in verdicts)),strong_seated_failures=[{'frame':int(f),'reason':v}for f,v in zip(np.flatnonzero(seated_mask),verdicts)if v is not None],support_mask_reason='Exact Idle endpoint phase: captured body blend complete AND both feet planted, no airborne frame claimed stationary seated contact')
    chair=S.load_complete_chair(S.load_chair());chair_tri=chair['triangles_cm'].copy();chair_tri[...,2]+=2.5001;cn=np.cross(chair_tri[:,1]-chair_tri[:,0],chair_tri[:,2]-chair_tri[:,0]);flip=np.sum(cn*chair['face_normals'],axis=1)<0;chair_tri[flip]=chair_tri[flip][:,[0,2,1]]
    desk_tri,desk_material=geometry(desk)
    def tree(tri):return BVHTree.FromPolygons([Vector(p)for p in tri.reshape(-1,3)],[(3*i,3*i+1,3*i+2)for i in range(len(tri))],all_triangles=True,epsilon=0)
    if report['written_world_max_error_cm']>.02:
        checkpoint('REFUSED: intermediate solver worlds differ written source');raise ValueError('Written65-bone worlds differ solver; no collision/acceptance inferred')
    scenes={name:(tree(t),materials,t.min(axis=(0,1)),t.max(axis=(0,1)))for name,t,materials in [('chair',chair_tri,chair['material']),('footrest',foot,foot_material),('desk',desk_tri,desk_material)]}
    collisions={name:{'minimum_margin_cm':float('inf'),'frames_checked':0,'failing_frames':[]}for name in scenes};skin=P.owner_skin(stride=6);floor_min=float('inf')
    checkpoint('written source contact and anatomy measured; auditing actual full furniture')
    for f in range(F):
        if time.monotonic()-start>seconds-2:break
        pts=E.to_ue(P.skin_points(skin,base.ibm,W[f:f+1]))[0];pts[:,:2]+=offset;lowest=int(pts[:,2].argmin())
        if pts[lowest,2]<floor_min:floor_min=float(pts[lowest,2]);report['lowest_floor_witness']={'frame':f,'point_ue_cm':pts[lowest].tolist(),'sample':lowest,'joint_weights':[{ 'joint':src.names[int(j)],'weight':float(w)}for j,w in zip(skin[1][lowest],skin[2][lowest])if w>0]}
        for name,(bvh,mats,lo,hi)in scenes.items():
            row=collisions[name];minimum=3.
            for pi in np.flatnonzero(np.all((pts>=lo-3)&(pts<=hi+3),axis=1)):
                p=pts[pi];loc,normal,index,distance=bvh.find_nearest(Vector(p));signed=closed.signed_distance(p,float(distance))if name=='footrest'else distance*(-1 if(Vector(p)-loc).dot(normal)<0 else 1);allowed=-2.5 if name=='chair'and mats[index]=='chair_fabric'else 0.;margin=signed-allowed
                if margin<minimum:
                    minimum=margin
                    if margin<row['minimum_margin_cm']and margin<0:row['witness']={'frame':f,'sample_index':int(pi),'body_point_ue_cm':p.tolist(),'nearest_ue_cm':list(loc),'triangle':int(index),'material':str(mats[index]),'part':labels[str(footrest)][index]if name=='footrest'else None,'normal':list(normal),'body_joint_weights':[{ 'joint':src.names[int(j)],'weight':float(w)}for j,w in zip(skin[1][pi],skin[2][pi])if w>0]}
            row['frames_checked']+=1;row['minimum_margin_cm']=min(row['minimum_margin_cm'],minimum)
            if minimum<0:row['failing_frames'].append(f)
        if f%15==0:report['collision']=collisions;checkpoint('physical collision frame'+str(f))
    report.update(collision=collisions,actual_floor_min_z_cm=floor_min,source_transition_candidate_pass=False,geometry_and_main_support_pass=bool(report['strong_seated_all_pass']and report['leg_edit_excess_deg']<=0 and excess.max()==0 and report['bone_length_error_cm']<1e-5 and all(r['all_reached']for r in reach.values())and all(r['frames_checked']==F and not r['failing_frames']for r in collisions.values())and floor_min>=2.5),pending=['Native endpoint/standing approach integration and original walking seam','Exact handshape/selfcontact and source pelvis acceleration comparison','Other transition and typing clips; coherent set not ready'])
    checkpoint('bounded DERIVED transition source proposal complete');print('ACTUAL_TRANSITION_SOURCE_RESULT',report['geometry_and_main_support_pass'],flush=True)
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in('root','owner','idle','footrest','desk','output'):p.add_argument('--'+n,required=True)
    p.add_argument('--role',choices=('SitDown','GetUp'),required=True);p.add_argument('--seconds',type=float,default=105)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]if '--'in sys.argv else None);run(a.root,a.owner,a.idle,a.footrest,a.desk,a.output,a.role,a.seconds)
