"""Server-only derived skin trial. Local geodesic smoothing; authored IBMs immutable."""
import hashlib
import json
import sys
from pathlib import Path


def run():
    import numpy as np
    sys.path[:0]=['/home/unreal/runtime-tools','/workspace/sub01-home-private/upright-footrest-python/scipy-1.14.1-cp311','/workspace/sub01-home-private/upright-footrest-full-9cd/tools']
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import dijkstra
    import export_seat_fit_source as E
    import fit_seat_pelvis_pitch as P
    import life_gltf as G
    from mathutils.bvhtree import BVHTree
    root=Path('/workspace/sub01-home-private/upright-footrest-full-9cd');owner=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/owner-with-clips-unreal.glb');g=G.Gltf(owner)
    assert g.sha256=='45e917725f02836dee6d051d9b47dd2785208c78b503fa935ddb322fe69adea8'
    out=Path('/workspace/sub01-home-private/owner-shoulder-derived-r3');out.mkdir(exist_ok=False)
    base=E.Source.load(root/'private-audit/seat-fit-source.npz');names=base.names;assert names==[E.short(g.doc['nodes'][i]['name'])for i in g.doc['skins'][0]['joints']]
    arm_ids=[i for i,n in enumerate(names)if n in ('LeftArm','RightArm','LeftForeArm','RightForeArm')];torso_ids=[i for i,n in enumerate(names)if n in ('Hips','Spine','Spine1','Spine2','LeftShoulder','RightShoulder')]
    poses={}
    for label,path,times in [('SitDown',root/'web/room/mh_mx/room_mx_stand_to_sit.glb',[0,20/30,40/30,67/30]),('Idle',Path('/workspace/sub01-home-private/upright-footrest-fit-r8/SUB01_SeatedIdle_upright_footrest.glb'),[0,2,125/30])]:
        if not path.exists():path=next(Path('/workspace/sub01-home-private/upright-footrest-fit-r8').rglob(path.name))
        W=E.joint_worlds(G.Gltf(path),names,times)[0]
        for t,w in zip(times,W):poses[f'{label}_{t:.5f}']=w[None]
    seen=set();work=[]
    for node in g.doc['nodes']:
        if node.get('skin')!=0 or'mesh'not in node or node['mesh']in seen:continue
        seen.add(node['mesh'])
        for pi,pr in enumerate(g.doc['meshes'][node['mesh']]['primitives']):
            mat=g.doc['materials'][pr['material']]['name']
            if not mat.startswith('tripo_material_'):continue
            a=pr['attributes'];v=E.accessor(g,a['POSITION']);j=E.accessor(g,a['JOINTS_0']).astype(int);w=E.accessor(g,a['WEIGHTS_0']);w/=w.sum(1,keepdims=True);tri=E.accessor(g,pr['indices']).astype(int).reshape(-1,3)
            edge=np.unique(np.sort(np.concatenate([tri[:,[0,1]],tri[:,[1,2]],tri[:,[2,0]]]),1),axis=0);length=np.linalg.norm(v[edge[:,0]]-v[edge[:,1]],axis=1)
            dense=np.zeros((len(v),65));np.add.at(dense,(np.arange(len(v))[:,None],j),w)
            arm=dense[:,arm_ids].sum(1);torso=dense[:,torso_ids].sum(1);boundary=(np.abs(arm[edge[:,0]]-arm[edge[:,1]])>.5)&(np.maximum(torso[edge[:,0]],torso[edge[:,1]])>.5)
            seeds=np.unique(edge[boundary].ravel());assert len(seeds)
            _,weld=np.unique(np.round(v,6),axis=0,return_inverse=True);order=np.argsort(weld,kind='stable');pairs=np.column_stack([order[:-1],order[1:]]);pairs=pairs[weld[pairs[:,0]]==weld[pairs[:,1]]]
            graph_edges=np.concatenate([edge,pairs]);dist=np.maximum(np.linalg.norm(v[graph_edges[:,0]]-v[graph_edges[:,1]],axis=1),1e-10);ii=np.r_[graph_edges[:,0],graph_edges[:,1]];jj=np.r_[graph_edges[:,1],graph_edges[:,0]]
            graph=csr_matrix((np.r_[dist,dist],(ii,jj)),shape=(len(v),len(v)));geo=dijkstra(graph,directed=False,indices=seeds,min_only=True,limit=.061)
            allowed=dense[:,arm_ids+torso_ids].sum(1)>.99999
            mask=(geo<.06)&allowed&(v[:,1]>.9)
            adj=csr_matrix((np.ones(len(ii)),(ii,jj)),shape=graph.shape);degree=np.asarray(adj.sum(1)).ravel();adj=adj.multiply((1/np.maximum(degree,1))[:,None]).tocsr()
            counts=np.bincount(weld);average=csr_matrix((1/counts[weld],(weld,np.arange(len(v)))),shape=(len(counts),len(v)));seam_equal=np.max(np.abs((average@dense)[weld]-dense),axis=1)<1e-8
            work.append((node['mesh'],pi,v,j,w,tri,edge,length,dense,mask,adj,weld,geo,average,seam_equal))
    trials=[];best=None
    for rounds in (12,40,100):
        changes=[];metrics=[];score=0
        for mi,pi,v,j,w,tri,edge,length,dense,mask,adj,weld,geo,average,seam_equal in work:
            d=dense.copy()
            for _ in range(rounds):
                d[mask]=(.2*d+.8*(adj@d))[mask]
                joined=(average@d)[weld];d[mask&seam_equal]=joined[mask&seam_equal]
            ids=np.argsort(d,axis=1)[:,-4:][:,::-1];ws=np.take_along_axis(d,ids,axis=1);ws/=ws.sum(1,keepdims=True)
            ids[~mask]=j[~mask];ws[~mask]=w[~mask]
            changed=np.flatnonzero(mask&((np.abs(ws-w).max(1)>1e-6)|(ids!=j).any(1)))
            touched=np.isin(tri,changed).any(1);active_edges=mask[edge].any(1)&(length>.002)
            row={'mesh':mi,'primitive':pi,'changed_vertices':len(changed),'source_geodesic_radius_cm':6.,'coincident_seams_preserve_equal_source_weights':True,'poses':[]}
            def intersections(p):
                ta=tri[touched];tb=tri[~touched];lo=p[ta.ravel()].min(0);hi=p[ta.ravel()].max(0);pbt=p[tb];tb=tb[((pbt.max(1)>=lo)&(pbt.min(1)<=hi)).all(1)]
                A=BVHTree.FromPolygons(p.tolist(),ta.tolist(),all_triangles=True,epsilon=0);B=BVHTree.FromPolygons(p.tolist(),tb.tolist(),all_triangles=True,epsilon=0)
                pairs=A.overlap(B);return sum(not set(weld[ta[a]]).intersection(weld[tb[b]])for a,b in pairs)
            for label,W in poses.items():
                original=P.skin_points((v,j,w),base.ibm,W)[0];posed=P.skin_points((v,ids,ws),base.ibm,W)[0]
                old=np.linalg.norm(original[edge[:,0]]-original[edge[:,1]],axis=1);new=np.linalg.norm(posed[edge[:,0]]-posed[edge[:,1]],axis=1)
                before=float((old-length)[active_edges].max()*100);after=float((new-length)[active_edges].max()*100);score+=after
                stat={'pose':label,'max_patch_edge_extension_before_cm':before,'after_cm':after,'max_changed_vertex_shift_cm':float(np.linalg.norm(posed-original,axis=1).max()*100)}
                if label in ('SitDown_0.66667','Idle_2.00000'):
                    stat['nonadjacent_patch_vs_rest_triangle_pairs_before']=intersections(original);stat['after']=intersections(posed)
                row['poses'].append(stat)
            changes.append((mi,pi,ids,ws,changed,j,w));metrics.append(row)
        trials.append({'rounds':rounds,'metrics':metrics,'strain_score':score});(out/'trial-progress.json').write_text(json.dumps(trials,indent=2))
        if best is None or score<best[0]:best=(score,rounds,changes)
        print('TRIAL',rounds,'SCORE',score,flush=True)
    _,rounds,changes=best;changed_report=[]
    for mi,pi,ids,ws,changed,oldj,oldw in changes:
        changed_report.append({'mesh':mi,'primitive':pi,'vertices':[{'id':int(i),'old_joints':oldj[i].tolist(),'old_weights':oldw[i].tolist(),'new_joints':ids[i].tolist(),'new_weights':ws[i].tolist()}for i in changed]})
    from write_local_skin_weight_clone import patch
    exact,byte_proof=patch(g.doc,g.buffers[0],changed_report);path=out/'owner-shoulder-derived.glb';G.write_glb(path,g.doc,exact)
    report={'schema':'sub01.local-owner-shoulder-weight-trial.v1','original_owner_sha256':g.sha256,'derived_owner_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'all_unlisted_attribute_bytes_exact':True,'sparse_byte_proof':byte_proof,'all_original65_nodes_ibms_uv_materials_positions_normals_unchanged':True,'hand_lower_body_weights_unchanged':True,'selected_rounds':rounds,'selection':'lowest summed patch maximum edge extension only; collision and appearance NOT acceptance','trials':trials,'changes':changed_report,'source_ready':False,'native_ready':False};(out/'repair-report.json').write_text(json.dumps(report,indent=2)+'\n');print('DERIVED_OWNER',report['derived_owner_sha256'],flush=True)

if __name__=='__main__':run()
