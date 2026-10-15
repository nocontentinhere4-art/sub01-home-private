"""Isolated source-only upright SeatedIdle fit against actual finite footrest.

Requires Claude9cd2ec7 tools + actual plantar NPZ in a private server packet.
Never edits those tools, original captures, world, native gates, or global floor.
"""
import argparse
import hashlib
import json
import math
import struct
import sys
import time
from pathlib import Path

FOOTREST_SHA='d805f7bcc58b919734a966e084d16aa509655f3d7df8c5088efbd6a17d425c50'
PREVIOUS_FOOTREST_SHA='0ca7c626dcca1b658da783b944d85db7e1247ed580d33022b5499ee2df5167b2'
OWNER_SHA='45e917725f02836dee6d051d9b47dd2785208c78b503fa935ddb322fe69adea8'
STRONG_SHA='dd95f1b1a8c3fc9a7d08b6d599985b86440c84752d85ae9f12fa8d480397a18f'


def run(root,owner,footrest,desk,output,seconds=105,resume=None,left_inward_cm=0.,right_inward_cm=0.):
    start=time.monotonic();root=Path(root);output=Path(output);output.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    sys.path.insert(0,'/workspace/sub01-home-private/upright-footrest-python/scipy-1.14.1-cp311')
    sys.path.insert(0,str(root/'tools'))
    import numpy as np
    from scipy.optimize import minimize
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
    if hashlib.sha256(Path(owner).read_bytes()).hexdigest()!=OWNER_SHA:raise ValueError('Exact preserved owner required')
    if hashlib.sha256(Path(footrest).read_bytes()).hexdigest()!=FOOTREST_SHA:raise ValueError('Actual physical footrest required')
    vb=(root/'strong-validator.py').read_bytes()
    if hashlib.sha256(vb).hexdigest()!=STRONG_SHA:raise ValueError('Unchanged strong main validator required')
    V=R.load_main_validator(vb);E.OWNER=Path(owner)
    base=E.Source.load(root/'private-audit/seat-fit-source.npz')
    if base.meta['owner_sha256']!=OWNER_SHA:raise ValueError('NPZ owner differs actual preserved owner')
    report={'schema':'sub01.upright-footrest-skinned-fit.v1','source_branch':'9cd2ec7','strong_rule_sha256':STRONG_SHA,'owner_sha256':OWNER_SHA,
            'footrest_sha256':FOOTREST_SHA,'global_floor_cm':2.5,'whole_chair_lift_cm':2.5001,'actual_desk_top_cm':84.5,
            'source_ready':False,'native_imported':False,'runtime_ready':False,'transitions_solved':False,'typing_solved':False,
            'plantar_source_metadata':base.meta.get('plantar_witness'),'original_capture_unchanged':True,'history':[]}
    def checkpoint(phase):
        report.update(phase=phase,elapsed_s=time.monotonic()-start)
        (output/'upright-fit-report.json').write_text(json.dumps(report,indent=2,default=lambda v:v.tolist()if hasattr(v,'tolist')else str(v))+'\n')
    checkpoint('loading actual source geometry')
    times=np.asarray(G.Gltf(root/'web/room/mh_mx/room_seated_idle.glb').animation().key_times())
    src,g=P.clip_source(base,root/'web/room/mh_mx/room_seated_idle.glb',times)
    if len(times)!=126 or len(src.names)!=65:raise ValueError('Exact126-key/65-bone captured idle required')
    original_hash=hashlib.sha256(g.path.read_bytes()).hexdigest()
    old=json.loads((root/'docs/proposed/seat-pose-anatomical/chair-lift-proposal/SUB01_SeatedIdle.report.json').read_text())
    offset=np.asarray(old['actual_chair']['body_offset_from_audited_transform_cm'],float)
    tri,_=P.load_cushion();tri=np.asarray(tri,float);tri[...,2]+=2.5001
    keys=T.keycaps_from_glb();fit=P.SeatFit(src,tri,keys,tuple(-offset),support_z=14.7)
    measure=A.FastMeasure(fit.trial);A.fast_trial(fit.trial,measure)
    W0=src.joint_world;B=np.linalg.inv(base.ibm);capture_angles=A.joint_angles(W0,B,src.names)

    geometry_labels={}
    def gltf_triangles(path):
        doc,blob=read_gltf(Path(path));matrices=world_matrices(doc);triangles=[];materials=[];labels=[];zeros=0
        for ni,n in enumerate(doc['nodes']):
            if 'mesh'not in n:continue
            matrix=np.asarray(matrices[ni]);normal_matrix=np.linalg.inv(matrix[:3,:3]).T
            for p in doc['meshes'][n['mesh']]['primitives']:
                points=np.asarray([transformed(matrices[ni],v)for v in accessor(doc,blob,p['attributes']['POSITION'])])*100
                points=points[:,[0,2,1]]
                normals=np.asarray(accessor(doc,blob,p['attributes']['NORMAL']))@normal_matrix.T;normals=normals[:,[0,2,1]]
                ids=np.asarray(accessor(doc,blob,p['indices']),int).reshape(-1,3)
                for indices in ids:
                    t=points[indices].copy();normal=np.cross(t[1]-t[0],t[2]-t[0])
                    if np.dot(normal,normal)==0:zeros+=1;continue
                    if np.dot(normal,normals[indices].sum(0))<0:t=t[[0,2,1]]
                    triangles.append(t);materials.append(doc['materials'][p['material']]['name']);labels.append({'node':ni,'name':n.get('name'),'material':doc['materials'][p['material']]['name']})
        geometry_labels[str(path)]=labels
        return np.asarray(triangles),np.asarray(materials),zeros
    foot_tri,foot_mat,foot_zero=gltf_triangles(footrest)
    norm=np.cross(foot_tri[:,1]-foot_tri[:,0],foot_tri[:,2]-foot_tri[:,0]);norm/=np.linalg.norm(norm,axis=1,keepdims=True)
    top=(norm[:,2]>.99)&(np.ptp(foot_tri[...,2],axis=1)<1e-5)&(np.min(np.abs(foot_tri[:,0,2,None]-np.array([14.5,14.7])),axis=1)<1e-5)
    support=foot_tri[top];report['finite_support_source_triangles']=len(support);report['discarded_exact_zero_area_footrest_triangles']=foot_zero
    current_dy=None
    def set_support(dy):
        nonlocal current_dy
        if current_dy==float(dy):return
        moved=support.copy();moved[...,0]-=offset[0];moved[...,1]+=dy-offset[1]
        fit.trial.support_height=T.Surface(moved).height;current_dy=float(dy)
    class Model(A.PoseModel):
        def apply(self,worlds,parameters,sole_iterations=2):
            set_support(parameters[10]);pose=super().apply(worlds,parameters[:9],sole_iterations)
            spine,neck=self.sk.j('Spine'),self.sk.j('Neck');v=pose[:,neck,:3,3]-pose[:,spine,:3,3]
            angle=math.radians(parameters[9])-np.arctan2(v[:,2],v[:,1])
            rotation=P.rodrigues(np.tile([1.,0.,0.],(len(pose),1)),angle)
            joint=pose[:,spine].copy();joint[:,:3,:3]=rotation@joint[:,:3,:3]
            return self.sk.rebase(pose,spine,joint)
    model=Model(fit,measure)
    frames=np.unique(np.r_[np.arange(0,len(W0),12),len(W0)-1]);evaluations=0;best=None
    def evaluate(x,fi):
        pose=model.apply(W0[fi],x);metrics=measure.metrics(pose);margins=A.main_margins(V,metrics);worst=A.worst_margin(margins)
        angles=A.joint_angles(pose,B,src.names);excess=A.limit_excess(angles,{k:v[fi]for k,v in capture_angles.items()})
        fractions={n:metrics[n]['over']/np.maximum(metrics[n]['facing'],1)for n in T.SOLE_PATCHES}
        return pose,metrics,worst,angles,excess,fractions
    class EndSearch(Exception):pass
    def cost(x):
        nonlocal best,evaluations
        if time.monotonic()-start>min(seconds*.50,48):raise EndSearch()
        evaluations+=1
        pose,metrics,worst,angles,excess,fractions=evaluate(x,frames)
        finite_short=max(max(0,.8-f.min())for f in fractions.values())
        bounds=A.param_bounds_excess(x[:9])+max(-x[9],0)+max(x[9]-12,0)+max(-x[10],0)+max(x[10]-12,0)
        comfort=max(0,float(np.max(angles['pelvis_posterior_tilt']))-18)
        value=-float(np.minimum(worst,.20).min())-.1*float(np.minimum(worst,.20).mean())+20*float(excess.max())+20*finite_short+5*bounds+.025*comfort+.002*(x[9]-4)**2+.0001*(x[10]-4)**2
        if best is None or value<best[0]:best=(value,np.asarray(x).copy())
        if evaluations%30==0:
            report['history'].append({'evaluations':evaluations,'cost':best[0],'params':best[1].tolist()});checkpoint('bounded finite-support search')
        return value
    seed=np.asarray([0.,10.7546,-11.7619,15.,-8.,15.,-9.7,0.,0.,4.,4.])
    previous=None
    if resume:
        previous=json.loads((Path(resume)/'upright-fit-report.json').read_text())
        candidate=Path(previous['written_glb'])
        if previous.get('strong_rule_sha256')!=STRONG_SHA or previous.get('footrest_sha256')not in(FOOTREST_SHA,PREVIOUS_FOOTREST_SHA) or not previous.get('readback_all126_main_rule_pass') or hashlib.sha256(candidate.read_bytes()).hexdigest()!=previous['written_glb_sha256']:
            raise ValueError('Exact previous written main-rule-passing candidate required')
        if previous['footrest_sha256']==PREVIOUS_FOOTREST_SHA:
            actual=json.loads(Path(footrest).with_name('footrest-source-proof.json').read_text())
            old_path=Path('/workspace/sub01-home-private/reference-footrest-source-r4/reference-footrest.glb')
            if hashlib.sha256(old_path.read_bytes()).hexdigest()!=PREVIOUS_FOOTREST_SHA or actual.get('glb_sha256')!=FOOTREST_SHA or len(actual.get('closed_component_topology',[]))!=19 or any(v['boundary_or_nonmanifold_edges']for v in actual['closed_component_topology']):raise ValueError('Exact closed topology repair receipt required')
            old_doc,old_bin=read_gltf(old_path);new_doc,new_bin=read_gltf(Path(footrest))
            def image_payloads(doc,blob):
                return [bytes(blob[doc['bufferViews'][im['bufferView']].get('byteOffset',0):doc['bufferViews'][im['bufferView']].get('byteOffset',0)+doc['bufferViews'][im['bufferView']]['byteLength']])for im in doc['images']]
            if old_doc['materials']!=new_doc['materials']or image_payloads(old_doc,old_bin)!=image_payloads(new_doc,new_bin):raise ValueError('Topology repair changed authored PBR')
            report['footrest_topology_repair']={'previous_sha256':PREVIOUS_FOOTREST_SHA,'new_sha256':FOOTREST_SHA,'all19_closed':True,'pbr_and_embedded_images_identical':True,'change':'Deduplicate coincident capsule endpoints before bevel; original shape and physical top heights retained'}
        best=(0.,np.asarray(previous['params'],float));report['resumed_exact_candidate_sha256']=previous['written_glb_sha256']
        if left_inward_cm:
            if not 0<left_inward_cm<=3:raise ValueError('Measured inward correction must be at most3cm within original anatomical parameter bounds')
            best[1][4]-=left_inward_cm
            report['measured_left_ankle_inward_correction_cm']=left_inward_cm
            report['previous_failure_witness']=previous.get('collision',{}).get('footrest',{}).get('worst_witness')
        if right_inward_cm:
            if not 0<right_inward_cm<=4:raise ValueError('Measured right correction must remain within4cm and original anatomical bounds')
            best[1][6]-=right_inward_cm
            report['measured_right_ankle_inward_correction_cm']=right_inward_cm
    else:
        try:
            cost(seed)
            simplex=np.vstack([seed]+[seed+np.eye(len(seed))[i]*step for i,step in enumerate([5.,1.5,2.,-2.,2.,-2.,2.,5.,5.,2.,2.])])
            minimize(cost,seed,method='Nelder-Mead',options={'initial_simplex':simplex,'maxfev':420,'xatol':.002,'fatol':.0005})
        except EndSearch:pass
    if best is None:raise RuntimeError('No actual finite-support candidate evaluated')
    x=best[1];report.update(params=x.tolist(),parameter_names=list(A.PARAMS)+['torso_forward_lean_deg','footrest_rigid_delta_y_cm'],evaluations=evaluations)
    pose,metrics,worst,angles,excess,fractions=evaluate(x,np.arange(len(W0)))
    report.update(all126_support_worst_margin_cm=float(worst.min()),all126_support_failing_frames=np.flatnonzero(worst<0).tolist(),anatomy=A.angle_summary(angles,capture_angles),anatomical_max_excess_deg=float(excess.max()),finite_sole_coverage={n:[float(f.min()),float(f.max())]for n,f in fractions.items()},unchanged_edit_bounds_excess=A.param_bounds_excess(x[:9]))
    checkpoint('all126 full plantar and posterior skin measured')
    labels={'label':'source candidate','verified':False,'native_ready':False,'source_capture_sha256':original_hash,'finite_real_footrest':FOOTREST_SHA}
    path=output/'SUB01_SeatedIdle_upright_footrest.glb'
    if previous and not(left_inward_cm or right_inward_cm):path.write_bytes(Path(previous['written_glb']).read_bytes())
    else:P.write_clip(g,fit.sk,pose,times,path,'SUB01_SeatedIdle_upright_footrest',labels,{})
    # Preserve raw finger local rotation and all nonroot translation/scale bytes.
    od,ob=read_gltf(path);sd,sb=read_gltf(g.path);ob=bytearray(ob)
    def rows(doc,blob,ai):
        a=doc['accessors'][ai];v=doc['bufferViews'][a['bufferView']];width={'VEC3':12,'VEC4':16}[a['type']]
        if a['componentType']!=5126:raise ValueError('Original float32 motion tracks required')
        start=v.get('byteOffset',0)+a.get('byteOffset',0);stride=v.get('byteStride',width)
        return [bytes(blob[start+i*stride:start+i*stride+width])for i in range(a['count'])],start,stride,width
    def channel_map(doc):return{(doc['nodes'][c['target']['node']]['name'],c['target']['path']):doc['animations'][0]['samplers'][c['sampler']]['output']for c in doc['animations'][0]['channels']}
    sm,om=channel_map(sd),channel_map(od);preserved=[]
    for key,ai in sm.items():
        name,prop=key;finger=any(t in name for t in('Thumb','Index','Middle','Ring','Pinky'))
        required=(finger and prop=='rotation')or prop=='scale'or(prop=='translation'and not name.endswith('Hips'))
        if not required:continue
        before,*_=rows(sd,sb,ai);after,start_b,stride,width=rows(od,ob,om[key])
        if len(before)!=len(after):raise ValueError('Captured untouched track key count changed')
        if finger and prop=='rotation':
            for i,value in enumerate(before):ob[start_b+i*stride:start_b+i*stride+width]=value
        elif before!=after:raise ValueError('Nonroot translation/scale bytes changed')
        preserved.append(key)
    encoded=json.dumps(od,separators=(',',':')).encode();encoded+=b' '*(-len(encoded)%4);blob=bytes(ob);blob+=b'\0'*(-len(blob)%4)
    path.write_bytes(struct.pack('<III',0x46546c67,2,28+len(encoded)+len(blob))+struct.pack('<II',len(encoded),0x4e4f534a)+encoded+struct.pack('<II',len(blob),0x004e4942)+blob)
    readback,_=E.joint_worlds(G.Gltf(path),src.names,times-times[0]);set_support(x[10]);metrics=measure.metrics(readback)
    verdicts=[R.judge_frame(V,R.frame_regions(metrics,i))for i in range(len(readback))]
    read_angles=A.joint_angles(readback,B,src.names);read_excess=A.limit_excess(read_angles,capture_angles)
    report.update(written_glb_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),written_glb=str(path),readback_world_error_cm=float(np.max(np.abs(readback[:,:,:3,3]-pose[:,:,:3,3]))*100),readback_all126_main_rule_pass=all(v is None for v in verdicts),readback_main_rule_failures=[{'frame':i,'reason':v}for i,v in enumerate(verdicts)if v is not None],readback_anatomical_max_excess_deg=float(read_excess.max()),finger_and_nonroot_tracks_preserved=preserved,bone_length_error_cm=A.bone_length_error_cm(fit.sk,W0,readback))
    checkpoint('written clip read back through unchanged main support validator')
    if time.monotonic()-start>seconds-8:checkpoint('collision audit deferred: bounded time exhausted');return report
    # Actual whole-chair source placement and every triangle of real desk/footrest.
    measured=S.load_chair();complete=S.load_complete_chair(measured)
    def make_bvh(triangles):
        points=triangles.reshape(-1,3);return BVHTree.FromPolygons([Vector(p)for p in points],[(3*i,3*i+1,3*i+2)for i in range(len(triangles))],all_triangles=True,epsilon=0)
    chair_tri=complete['triangles_cm'].copy();chair_tri[...,2]+=2.5001
    norms=np.cross(chair_tri[:,1]-chair_tri[:,0],chair_tri[:,2]-chair_tri[:,0]);flip=np.sum(norms*complete['face_normals'],axis=1)<0;chair_tri[flip]=chair_tri[flip][:,[0,2,1]]
    moved_foot=foot_tri.copy();moved_foot[...,1]+=x[10];desk_tri,desk_mat,desk_zeros=gltf_triangles(desk)
    from closed_footrest_contact import ClosedFootrest
    closed_foot=ClosedFootrest(moved_foot,[v['node']for v in geometry_labels[str(footrest)]])
    witness=np.asarray([220.299530820484,-254.18425456045236,17.47490146937627])
    if closed_foot.contains(witness):raise ValueError('Known exterior knob-rim witness classified inside')
    checks={'known_exterior_knob_rim':True}
    for node,part,lo,hi in closed_foot.parts:
        label=next(v['name']for v in geometry_labels[str(footrest)]if v['node']==node)
        if 'AdjustmentKnob'in label:
            if not closed_foot.contains_part((lo+hi)*.5,node):raise ValueError('Known knob interior not inside')
            checks[label+'_interior']=True
        if 'PiercedSidePlate'in label:
            hole=[(lo[0]+hi[0])*.5,-270.+x[10],13.7]
            solid=[(lo[0]+hi[0])*.5,-260.+x[10],7.]
            if closed_foot.contains_part(hole,node)or not closed_foot.contains_part(solid,node):raise ValueError('Real carry hole/sideplate containment differs')
            checks[label+'_carry_hole_and_solid']=True
    report['closed_footrest_component_proof']=closed_foot.proof;report['closed_footrest_known_point_tests']=checks
    checkpoint('all19 footrest parts closed and interior/exterior/through-hole tests pass')
    bvhs={name:(make_bvh(tris),mats,tris.min(axis=(0,1)),tris.max(axis=(0,1)))for name,tris,mats in [('chair',chair_tri,complete['material']),('footrest',moved_foot,foot_mat),('desk',desk_tri,desk_mat)]}
    skin=P.owner_skin(stride=6);collisions={name:{'minimum_margin_cm':float('inf'),'frames_with_penetration':[],'frames_checked':0}for name in bvhs};minimum_floor=float('inf')
    for f in range(len(readback)):
        if time.monotonic()-start>seconds-2:break
        points=E.to_ue(P.skin_points(skin,base.ibm,readback[f:f+1]))[0];points[:,:2]+=offset;minimum_floor=min(minimum_floor,float(points[:,2].min()))
        for name,(tree,materials,lo,hi)in bvhs.items():
            minimum=3.
            near=np.all((points>=lo-3)&(points<=hi+3),axis=1)
            for sample_index in np.flatnonzero(near):
                p=points[sample_index]
                location,normal,index,distance=tree.find_nearest(Vector(p))
                signed=closed_foot.signed_distance(p,float(distance))if name=='footrest'else distance*(-1 if (Vector(p)-location).dot(normal)<0 else 1)
                allowed=-2.5 if name=='chair'and materials[index]=='chair_fabric'else 0.
                if signed-allowed<minimum:
                    minimum=signed-allowed
                    if minimum<0 and minimum<collisions[name]['minimum_margin_cm']:
                        label={'material':str(materials[index])}
                        if name=='footrest':label.update(geometry_labels[str(footrest)][index])
                        elif name=='desk':label.update(geometry_labels[str(desk)][index])
                        collisions[name]['worst_witness']={'frame':f,'sample_index':int(sample_index),'body_point_ue_cm':p.tolist(),'nearest_surface_ue_cm':list(location),'outward_normal':list(normal),'distance_cm':float(distance),'signed_margin_cm':float(minimum),'triangle_index':int(index),'part':label}
            result=collisions[name];result['minimum_margin_cm']=min(result['minimum_margin_cm'],minimum);result['frames_checked']+=1
            if minimum<0:result['frames_with_penetration'].append(f)
        if f%20==0:report['collision']=collisions;checkpoint('actual source mesh collision audit '+str(f))
    report.update(collision=collisions,collision_skin_sampling='every6th source skinned vertex, ALL126frames required; exact nearest BVH triangle normals; no mesh geometry omitted',actual_floor_clearance_cm=minimum_floor-2.5,footrest_rigid_delta_ue_cm=[0.,float(x[10]),0.],original_capture_unchanged=hashlib.sha256(g.path.read_bytes()).hexdigest()==original_hash)
    report['source_idle_candidate_pass']=bool(report['readback_all126_main_rule_pass']and read_excess.max()==0 and A.param_bounds_excess(x[:9])==0 and min(f.min()for f in fractions.values())>=.8 and all(c['frames_checked']==126 and not c['frames_with_penetration']for c in collisions.values())and minimum_floor>=2.5)
    checkpoint('bounded source candidate complete');return report


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in('root','owner','footrest','desk','output'):p.add_argument('--'+name,required=True)
    p.add_argument('--seconds',type=float,default=105.);p.add_argument('--resume');p.add_argument('--left-inward-cm',type=float,default=0.);p.add_argument('--right-inward-cm',type=float,default=0.)
    argv=sys.argv[sys.argv.index('--')+1:]if '--'in sys.argv else sys.argv[1:];a=p.parse_args(argv)
    result=run(a.root,a.owner,a.footrest,a.desk,a.output,a.seconds,a.resume,a.left_inward_cm,a.right_inward_cm);print('ACTUAL_UPRIGHT_SOURCE_RESULT',result.get('source_idle_candidate_pass',False),result.get('phase'),flush=True)
