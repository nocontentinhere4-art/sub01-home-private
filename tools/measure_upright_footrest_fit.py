"""Bounded geometry-first seated candidate; no native or source-clip mutations.

Use isolated Claude9cd2ec7 tools. Tests reach and rigid bone/finger invariance
against the real finite footrest before any full skinned-support optimization.
This phase cannot declare a chair/sole/anatomical/native acceptance verdict.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

FOOTREST_SHA='0ca7c626dcca1b658da783b944d85db7e1247ed580d33022b5499ee2df5167b2'
STRONG_SHA='dd95f1b1a8c3fc9a7d08b6d599985b86440c84752d85ae9f12fa8d480397a18f'


def measure(tools,clip,clip_report,chair,footrest,validator,output):
    import numpy as np
    sys.path.insert(0,str(Path(tools)))
    import life_gltf as G
    import export_seat_fit_source as E
    import fit_seat_pose_trial as T
    import fit_seat_pelvis_pitch as P
    from structural_rail_source_patch import accessor,world_matrices,transformed
    from home_asset_audit import read_gltf
    if hashlib.sha256(Path(footrest).read_bytes()).hexdigest()!=FOOTREST_SHA:raise ValueError('Exact actual footrest required')
    if hashlib.sha256(Path(validator).read_bytes()).hexdigest()!=STRONG_SHA:raise ValueError('Unchanged main strong support rule required')
    g=G.Gltf(Path(clip));names=[E.short(n['name'])for n in g.nodes if n.get('name','').startswith('mixamorig')]
    if len(names)!=65 or len(set(names))!=65:raise ValueError('Actual original65 bone identities required')
    times=np.asarray(g.animation().key_times());sample=np.unique(np.linspace(0,len(times)-1,13).astype(int));W,parents=E.joint_worlds(g,names,times[sample])
    class Source:pass
    source=Source();source.names=names;source.parents=parents;sk=T.Skeleton(source)
    rep=json.loads(Path(clip_report).read_text());offset=rep['actual_chair']['body_offset_from_audited_transform_cm']
    lift=float(rep['actual_chair']['chair_lift_cm'])
    if abs(lift-2.5001)>1e-6:raise ValueError('Reviewed whole-chair caster lift required')
    def world(points):
        result=E.to_ue(points);result[...,0]+=offset[0];result[...,1]+=offset[1];return result
    fd,fb=read_gltf(Path(footrest));fm=world_matrices(fd);support=[];allpoints=[]
    for ni,node in enumerate(fd['nodes']):
        if 'mesh'not in node:continue
        for p in fd['meshes'][node['mesh']]['primitives']:
            ps=np.asarray([transformed(fm[ni],v)for v in accessor(fd,fb,p['attributes']['POSITION'])])*100
            ps=ps[:,[0,2,1]];allpoints.extend(ps)
            ids=np.asarray(accessor(fd,fb,p['indices']),int).reshape(-1,3)
            for f in ids:
                tri=ps[f];cross=np.cross(tri[1]-tri[0],tri[2]-tri[0]);length=np.linalg.norm(cross)
                # glTF->UE mirror reverses winding. Determine horizontal actual
                # load surfaces by known physical heights, not floor relabelling.
                if length>0 and cross[2]/length<-.99 and np.ptp(tri[:,2])<1e-5 and min(abs(tri[0,2]-14.5),abs(tri[0,2]-14.7))<1e-5:
                    support.append(tri)
    support=np.asarray(support);surface=T.Surface(support)
    if len(support)==0:raise ValueError('Actual wood AND rubber top geometry required')
    extra_pelvis_tilt=float(rep['labels']['params']['pelvis_tilt_deg'])
    proposal=P.pelvis_pitch(sk,W,-extra_pelvis_tilt,0.,P.hips_lateral_local(sk,W))
    support_center=np.mean([support[...,:2].min(axis=(0,1)),support[...,:2].max(axis=(0,1))],axis=0)
    reaches={};baseline={};candidate={};passive={}
    def inverse_world(points):
        relative=np.asarray(points,float)-np.asarray(E.BODY_CM)-np.asarray([offset[0],offset[1],0.])
        relative/=100;angle=math.radians(E.BODY_YAW);c,si=math.cos(angle),math.sin(angle)
        comp=np.stack([c*relative[...,0]+si*relative[...,1],-si*relative[...,0]+c*relative[...,1],relative[...,2]],axis=-1)
        return comp[...,[0,2,1]]
    for side,pre in [('left','Left'),('right','Right')]:
        h,k,f=[sk.j(pre+n)for n in('UpLeg','Leg','Foot')]
        old=world(W[:,:,:3,3][:,[h,k,f]]);baseline[side]={'hip_cm':old[:,0].tolist(),'knee_cm':old[:,1].tolist(),'ankle_cm':old[:,2].tolist()}
        # Existing derived packet has flat feet on2.5cm floor. The unchanged foot
        # rotation lifted12.2cm places its soles on actual14.7cm rubber tops.
        old_ankle=old[:,2].copy();passive_found,_=surface.height(old_ankle[:,:2]);passive[side]=passive_found.tolist()
        target_ue=old_ankle.copy();target_ue[:,0]=world(proposal[:,h,:3,3])[:,0];target_ue[:,1]=support_center[1];target_ue[:,2]+=.122*100
        target=inverse_world(target_ue)
        pole=proposal[:,h,:3,3]+np.asarray([0.,-.05,.35])
        proposal,reachable,length,distance=sk.two_bone_pose(proposal,(pre+'UpLeg',pre+'Leg',pre+'Foot'),target,pole,end_world_rot=W[:,f].copy())
        reaches[side]={'all_reachable':bool(reachable.all()),'minimum_chain_reach_margin_cm':float(np.min(length-distance)*100)}
        positions=world(proposal[:,:,:3,3][:,[h,k,f]]);found,heights=surface.height(positions[:,2,:2])
        candidate[side]={'hip_cm':positions[:,0].tolist(),'knee_cm':positions[:,1].tolist(),'ankle_cm':positions[:,2].tolist(),
                         'ankle_delta_from_existing_derived_cm':(positions[:,2]-old_ankle).tolist(),'ankle_projection_over_actual_finite_top':found.tolist(),'actual_top_below_ankle_cm':np.where(found,heights,np.nan).tolist()}
    spine,neck=sk.j('Spine'),sk.j('Neck')
    def torso_pitch(pose):
        delta=world(pose[:,neck,:3,3])-world(pose[:,spine,:3,3]);return np.degrees(np.arctan2(-delta[:,1],delta[:,2]))
    before_pitch=torso_pitch(proposal)
    vector=proposal[:,neck,:3,3]-proposal[:,spine,:3,3];angle=-np.arctan2(vector[:,2],vector[:,1])
    rotation=P.rodrigues(np.tile([1.,0.,0.],(len(W),1)),angle);new_spine=proposal[:,spine].copy();new_spine[:,:3,:3]=rotation@new_spine[:,:3,:3]
    proposal=sk.rebase(proposal,spine,new_spine)
    local_error=0.;bone_error=0.;finger_error=0.
    for j,parent in enumerate(parents):
        if parent<0:continue
        a=np.linalg.inv(W[:,parent])@W[:,j];b=np.linalg.inv(proposal[:,parent])@proposal[:,j]
        local_error=max(local_error,float(np.max(np.abs(a[:,:3,3]-b[:,:3,3])))*100)
        bone_error=max(bone_error,float(np.max(np.abs(np.linalg.norm(a[:,:3,3],axis=1)-np.linalg.norm(b[:,:3,3],axis=1))))*100)
        if any(token in names[j]for token in ('Thumb','Index','Middle','Ring','Pinky')):finger_error=max(finger_error,float(np.max(np.abs(a-b))))
    if local_error>1e-6 or bone_error>1e-6 or finger_error>1e-8:raise ValueError('Candidate changed nonroot local lengths/finger poses')
    chair_report=json.loads(Path(chair).read_text());cushion=np.asarray(T.cushion_from_report(chair_report)[0]);cushion[...,2]+=lift
    result={'schema':'sub01.upright-footrest-geometric-probe.v1','phase':'bounded geometric probe, not skinned-support acceptance',
            'source_clip_sha256':hashlib.sha256(Path(clip).read_bytes()).hexdigest(),'footrest_sha256':FOOTREST_SHA,'unchanged_strong_rule_sha256':STRONG_SHA,
            'pelvis_extra_fit_pitch_undone_deg':extra_pelvis_tilt,'passive_ankle_projection_on_provisional_footrest':passive,'frames_sampled':sample.tolist(),'whole_chair_rigid_lift_cm':lift,'chair_cushion_max_cm':float(cushion[...,2].max()),'actual_desk_top_cm':84.5,
            'actual_wood_and_rubber_support_triangles':len(support),'baseline':baseline,'candidate':candidate,'leg_reach':reaches,
            'torso_forward_pitch_before_deg':before_pitch.tolist(),'torso_forward_pitch_candidate_deg':torso_pitch(proposal).tolist(),
            'bone_length_error_cm':bone_error,'nonroot_local_translation_error_cm':local_error,'finger_local_matrix_error':finger_error,
            'missing_checks':['full actual plantar and posterior skin contact with unchanged main rule','actual chair/desk/footrest full skin collision','anatomical joint ranges','allframes/transition continuity'],
            'source_ready':False,'native_imported':False,'runtime_ready':False}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2)+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in('tools','clip','clip-report','chair','footrest','validator','output'):p.add_argument('--'+name,required=True)
    argv=sys.argv[sys.argv.index('--')+1:]if '--'in sys.argv else sys.argv[1:]
    a=p.parse_args(argv);r=measure(a.tools,a.clip,a.clip_report,a.chair,a.footrest,a.validator,a.output);print('ACTUAL_UPRIGHT_GEOMETRIC_PROBE',r['leg_reach'],flush=True)
