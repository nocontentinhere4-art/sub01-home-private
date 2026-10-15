"""Bounded read-only source edge witnesses; never edits weights, IBMs or poses."""
import hashlib
import json
import sys
from pathlib import Path


def run():
    import numpy as np
    root=Path('/workspace/sub01-home-private/upright-footrest-full-9cd')
    sys.path.insert(0,str(root/'tools'))
    import export_seat_fit_source as E
    import fit_seat_pelvis_pitch as P
    import life_gltf as G
    from structural_rail_source_patch import world_matrices
    owner=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/owner-with-clips-unreal.glb')
    assert hashlib.sha256(owner.read_bytes()).hexdigest()=='45e917725f02836dee6d051d9b47dd2785208c78b503fa935ddb322fe69adea8'
    g=G.Gltf(owner);base=E.Source.load(root/'private-audit/seat-fit-source.npz')
    names=[E.short(g.doc['nodes'][i]['name'])for i in g.doc['skins'][0]['joints']]
    assert names==base.names
    worlds=world_matrices(g.doc)
    poses={'document_reference':np.asarray([worlds[i]for i in g.doc['skins'][0]['joints']])[None]}
    clips={'repo_fitted_SitDown_frame20':(root/'web/room/mh_mx/room_mx_stand_to_sit.glb',20/30), 'upright_Idle_frame60':(Path('/workspace/sub01-home-private/upright-footrest-fit-r8/SUB01_SeatedIdle_upright_footrest.glb'),2.)}
    for label,(path,t)in clips.items():
        if not path.is_file():
            matches=list(Path('/workspace/sub01-home-private/upright-footrest-fit-r8').rglob(path.name));assert len(matches)==1;path=matches[0]
        poses[label]=E.joint_worlds(G.Gltf(path),names,[t])[0]
    rows=[];seen=set()
    for ni,node in enumerate(g.doc['nodes']):
        if node.get('skin')!=0 or 'mesh'not in node or node['mesh']in seen:continue
        seen.add(node['mesh'])
        for pi,pr in enumerate(g.doc['meshes'][node['mesh']]['primitives']):
            a=pr['attributes'];v=E.accessor(g,a['POSITION']);j=E.accessor(g,a['JOINTS_0']).astype(int);w=E.accessor(g,a['WEIGHTS_0']);w=w/np.maximum(w.sum(1,keepdims=True),1e-30)
            tri=E.accessor(g,pr['indices']).reshape(-1,3).astype(int);edges=np.unique(np.sort(np.concatenate([tri[:,[0,1]],tri[:,[1,2]],tri[:,[2,0]]]),axis=1),axis=0)
            dom=j[np.arange(len(j)),w.argmax(1)];upper=np.asarray([any(s in names[x]for s in ('Spine','Shoulder','Arm','Neck'))for x in dom]);length=np.linalg.norm(v[edges[:,0]]-v[edges[:,1]],axis=1);mask=(length>.002)&upper[edges].all(1);edges=edges[mask];length=length[mask]
            if not len(edges):continue
            def describe(idx):return {'vertex':int(idx),'as_modelled_m':v[idx].tolist(),'weights':{names[int(k)]:float(x)for k,x in zip(j[idx],w[idx])if x>1e-5}}
            arm=np.asarray([('Arm'in names[x]or'Hand'in names[x])for x in dom]);torso=np.asarray([x in ('Hips','Spine','Spine1','Spine2','Neck','Head','LeftShoulder','RightShoulder')for x in [names[d]for d in dom]])
            cross=(arm[edges[:,0]]&torso[edges[:,1]])|(torso[edges[:,0]]&arm[edges[:,1]])
            for label,W in poses.items():
                p=P.skin_points((v,j,w),base.ibm,W)[0];posed=np.linalg.norm(p[edges[:,0]]-p[edges[:,1]],axis=1);ratio=posed/length;order=np.argsort(posed-length)[-15:][::-1]
                rows.append({'node':ni,'primitive':pi,'material':g.doc['materials'][pr['material']]['name'],'pose':label,'upper_edges_longer_than_2mm':len(edges),'median_ratio':float(np.median(ratio)),'p95_ratio':float(np.percentile(ratio,95)),'max_extension_cm':float((posed-length).max()*100),'top_extension_edges':[{'as_modelled_length_cm':float(length[k]*100),'posed_length_cm':float(posed[k]*100),'dominant_arm_torso_boundary':bool(cross[k]),'vertices':[describe(i)for i in edges[k]]}for k in order]})
    report={'schema':'sub01.owner-shoulder-strain-source-audit.v1','owner_sha256':hashlib.sha256(owner.read_bytes()).hexdigest(),'repo_SitDown_is_previously_fitted_not_provider_raw':True,'all_original_ibms_weights_positions_unchanged':True,'length_reference':'as-modelled POSITION edges; document_reference is authored Mixamo T-pose and intentionally differs','rows':rows,'native_readiness':False}
    out=Path('/workspace/sub01-home-private/upright-raw-sit-preview-r1/uid1001/output/shoulder-strain-source-audit.json');out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'output':str(out),'rows':len(rows),'summary':[{k:r[k]for k in ('material','pose','p95_ratio','max_extension_cm')}for r in rows]}),flush=True)

if __name__=='__main__':run()
