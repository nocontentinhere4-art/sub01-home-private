"""Source-only index mask and captured typing phase audit; no native readiness."""
from pathlib import Path
import hashlib,json,sys,time,gzip


def mask_triangles(joints,weights,indices,arm_ids,hand_ids,threshold):
    import numpy as np
    arm_weight=np.where(np.isin(joints,arm_ids),weights,0).sum(1)
    protected=(np.isin(joints,hand_ids)&(weights>0)).any(1)
    must_keep=protected[indices].any(1)
    keep=(arm_weight[indices]>=threshold).all(1)|must_keep
    return keep,must_keep,arm_weight


def new_cut_edges(positions,indices,kept):
    import numpy as np
    _,representative,weld=np.unique(np.round(positions,7),axis=0,return_index=True,return_inverse=True)
    n=len(representative)
    def edgekeys(faces):
        f=weld[faces];edges=np.concatenate((f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]));edges.sort(1);return edges[:,0].astype(np.int64)*n+edges[:,1]
    original,count=np.unique(edgekeys(indices),return_counts=True);retained,rcount=np.unique(edgekeys(indices[kept]),return_counts=True);lookup=np.searchsorted(original,retained);cut=retained[(rcount==1)&(count[lookup]>1)]
    pairs=np.column_stack((cut//n,cut%n));ids=representative[pairs]
    return ids,{'new_cut_edges':len(ids),'original_mesh_position_weld_for_audit_only_m':1e-7,'original_open_edges':int((count==1).sum()),'kept_faces':int(kept.sum())}


def run():
    start=time.monotonic();root=Path('/workspace/sub01-home-private/upright-footrest-full-9cd');sys.path[:0]=[str(root/'tools'),'/home/unreal/runtime-tools','/workspace/sub01-home-private/upright-footrest-python/scipy-1.14.1-cp311']
    import numpy as np
    import life_gltf as G
    import export_seat_fit_source as E
    import fit_seat_pelvis_pitch as P
    import solve_seated_typing_arm_ik as S
    owner=G.Gltf('/workspace/sub01-home-private/owner-shoulder-derived-r3/owner-shoulder-derived.glb');assert owner.sha256=='831790a62b81e7e2faa5a201e04740d0911c5bfebd49aa03b124808521e3a2b1'
    raw=G.Gltf('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/owner-with-clips-unreal.glb');assert raw.sha256=='45e917725f02836dee6d051d9b47dd2785208c78b503fa935ddb322fe69adea8';raw.doc['animations']=[a for a in raw.doc['animations']if a['name']=='typing'];assert len(raw.doc['animations'])==1
    names=[E.short(owner.nodes[i]['name'])for i in owner.doc['skins'][0]['joints']];assert len(names)==65
    sets=S.arm_joint_sets(names);hands=[j for side in sets.values()for group,ids in side.items()if group in ('hand','fingers')for j in ids];variants=[];primitives=[]
    for node_index,node in enumerate(owner.nodes):
        if 'mesh'not in node or node.get('skin')!=0:continue
        for pi,prim in enumerate(owner.doc['meshes'][node['mesh']]['primitives']):
            p=E.accessor(owner,prim['attributes']['POSITION']);j=E.accessor(owner,prim['attributes']['JOINTS_0']).astype(int);w=E.accessor(owner,prim['attributes']['WEIGHTS_0']);w=np.divide(w,w.sum(1,keepdims=True),out=np.zeros_like(w),where=w.sum(1,keepdims=True)>0);idx=E.accessor(owner,prim['indices']).astype(int).reshape(-1,3)
            row={'mesh':node['mesh'],'node':node_index,'primitive':pi,'material':owner.doc['materials'][prim['material']]['name'],'source_vertices':len(p),'source_triangles':len(idx)};primitives.append(row)
            for scope in ('full_arm','forearm_hand'):
                arms=[i for side in sets.values()for group,ids in side.items()if scope=='full_arm'or group!='upper_arm'for i in ids]
                for threshold in (.5,.75,.95):
                    keep,must,aw=mask_triangles(j,w,idx,arms,hands,threshold);cut,topo=new_cut_edges(p,idx,keep);vertices=np.unique(idx[keep]);leaks=vertices[aw[vertices]<.5]
                    variants.append(row|{'scope':scope,'threshold':threshold,'kept_triangles':int(keep.sum()),'kept_vertices':len(vertices),'protected_hand_triangles':int(must.sum()),'protected_hand_triangles_retained':bool(keep[must].all()),'non_arm_majority_retained_vertices':len(leaks),'non_arm_majority_retained_vertex_ids':leaks.tolist(),'cut':topo,'new_cut_source_vertex_pairs':cut.tolist(),'kept_source_triangle_ids':np.flatnonzero(keep).tolist()})
    # Exact local captured finger activity. This labels motion, never proves skin contact.
    times=np.asarray(raw.animation().key_times());W,_=E.joint_worlds(raw,names,times);clip=raw.animation();channels={}
    for c in raw.doc['animations'][0]['channels']:
        if c['target']['path']=='rotation':channels[E.short(raw.nodes[c['target']['node']]['name'])]=c
    phase=[]
    for sec in range(int(np.ceil(times[-1]))):
        choose=np.flatnonzero((times>=sec)&(times<sec+1));entry={'start_s':sec,'end_s':min(float(times[-1]),sec+1),'hands':{}}
        if len(choose)<2:continue
        for side,prefix in [('left','Left'),('right','Right')]:
            fingers=[n for n in names if n.startswith(prefix+'Hand')and any(f in n for f in ('Thumb','Index','Middle','Ring','Pinky'))and n[-1:]in('1','2','3')];activity={}
            for name in fingers:
                node=raw.by_name['mixamorig:'+name];q=[clip.sample(node,'rotation',float(times[f]),raw.rest(node)[1])for f in choose];activity[name]=sum(G.qangle_deg(q[i-1],q[i])for i in range(1,len(q)))
            wrist=W[choose,names.index(prefix+'Hand'),:3,3];palm_centers=E.to_ue(wrist);entry['hands'][side]={'active_finger_joints_above2deg':sum(v>2 for v in activity.values()),'total_captured_finger_angular_path_deg':sum(activity.values()),'finger_activity_deg':activity,'wrist_raw_world_mean_ue_cm':palm_centers.mean(0).tolist(),'wrist_raw_world_minmax_ue_cm':[palm_centers.min(0).tolist(),palm_centers.max(0).tolist()]}
        phase.append(entry)
    report={'schema':'sub01.fp-arms-source-mask-phase-audit.v1','owner_sha256':owner.sha256,'original_owner_unchanged':True,'captured_owner_sha256':raw.sha256,'captured_action':'typing','duration_s':float(times[-1]),'frames':len(times),'bone_names':names,'arm_labels_reused_from':'solve_seated_typing_arm_ik.arm_joint_sets, pinned9cd2tools','source_primitives':primitives,'variants':variants,'captured_activity_bins':phase,'camera_or_contact_accepted':False,'contact_note':'Wrist positions use historical source BODY_CM only; these are NOT skin/key/mouse contacts or a new first-person camera placement. No old perch solver was applied.','pending':['Select visible sleeve cut using captured eye/frustum and real mask boundary','Exact complete hand pad vs real keycap and curved mouse triangles','First-person camera/source placement and rigidbone handshape proof','Source preview then native import/review'],'elapsed_s':time.monotonic()-start,'source_ready':False,'native_ready':False,'new_mesh_written':False}
    out=Path('/workspace/sub01-home-private/fp-arms-source-audit-r1');out.mkdir(exist_ok=False);(out/'arms-mask-phase-audit.json.gz').write_bytes(gzip.compress((json.dumps(report,indent=2)+'\n').encode(),mtime=0));print(json.dumps({'elapsed_s':report['elapsed_s'],'frames':len(times),'variant_counts':[{'material':v['material'],'scope':v['scope'],'threshold':v['threshold'],'tris':v['kept_triangles'],'cutedges':v['cut']['new_cut_edges'],'leaks':v['non_arm_majority_retained_vertices']}for v in variants if v['kept_triangles']]}),flush=True)

if __name__=='__main__':run()
