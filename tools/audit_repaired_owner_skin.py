"""Read-back proof of the written local skin clone, all seated/entry source frames."""
import json
import sys
from pathlib import Path


def run():
    import numpy as np
    sys.path.insert(0,'/workspace/sub01-home-private/upright-footrest-full-9cd/tools')
    import export_seat_fit_source as E
    import fit_seat_pelvis_pitch as P
    import life_gltf as G
    from structural_rail_source_patch import world_matrices
    root=Path('/workspace/sub01-home-private/upright-footrest-full-9cd');out=Path('/workspace/sub01-home-private/owner-shoulder-derived-r3');source=G.Gltf('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/owner-with-clips-unreal.glb');derived=G.Gltf(out/'owner-shoulder-derived.glb');report=json.loads((out/'repair-report.json').read_text());assert source.doc==derived.doc
    base=E.Source.load(root/'private-audit/seat-fit-source.npz');names=base.names
    worlds=world_matrices(source.doc);poses={'document_reference':np.asarray([worlds[i]for i in source.doc['skins'][0]['joints']])[None]}
    for label,path,n in [('SitDown',root/'web/room/mh_mx/room_mx_stand_to_sit.glb',68),('Idle',next(Path('/workspace/sub01-home-private/upright-footrest-fit-r8').rglob('SUB01_SeatedIdle_upright_footrest.glb')),126)]:poses[label]=E.joint_worlds(G.Gltf(path),names,np.arange(n)/30)[0]
    rows=[]
    for row in report['changes']:
        pr=source.doc['meshes'][row['mesh']]['primitives'][row['primitive']];a=pr['attributes'];v=E.accessor(source,a['POSITION']);j=E.accessor(source,a['JOINTS_0']).astype(int);w=E.accessor(source,a['WEIGHTS_0']);nj=E.accessor(derived,a['JOINTS_0']).astype(int);nw=E.accessor(derived,a['WEIGHTS_0']);changed=np.asarray([r['id']for r in row['vertices']]);unchanged=np.ones(len(v),bool);unchanged[changed]=False;assert np.array_equal(j[unchanged],nj[unchanged])and np.array_equal(w[unchanged],nw[unchanged]);w/=w.sum(1,keepdims=True);nw/=nw.sum(1,keepdims=True)
        tri=E.accessor(source,pr['indices']).astype(int).reshape(-1,3);edges=np.unique(np.sort(np.concatenate([tri[:,[0,1]],tri[:,[1,2]],tri[:,[2,0]]]),1),axis=0);edges=edges[np.isin(edges,changed).any(1)];length=np.linalg.norm(v[edges[:,0]]-v[edges[:,1]],axis=1);edges=edges[length>.002];length=length[length>.002];ids=np.unique(edges);mapped=np.searchsorted(ids,edges)
        _,weld=np.unique(np.round(v,6),axis=0,return_inverse=True);order=np.argsort(weld,kind='stable');seams=np.column_stack([order[:-1],order[1:]]);seams=seams[(weld[seams[:,0]]==weld[seams[:,1]])&np.isin(seams,changed).any(1)]
        dense=np.zeros((len(v),65));np.add.at(dense,(np.arange(len(v))[:,None],j),w);newdense=np.zeros_like(dense);np.add.at(newdense,(np.arange(len(v))[:,None],nj),nw)
        originally_equal=np.max(np.abs(dense[seams[:,0]]-dense[seams[:,1]]),1)<1e-8;seam_error=float(np.max(np.abs(newdense[seams[originally_equal,0]]-newdense[seams[originally_equal,1]]),initial=0))
        metrics=[]
        for label,W in poses.items():
            values=[]
            for frame,ww in enumerate(W):
                old=P.skin_points((v[ids],j[ids],w[ids]),base.ibm,ww[None])[0];new=P.skin_points((v[ids],nj[ids],nw[ids]),base.ibm,ww[None])[0];before=np.linalg.norm(old[mapped[:,0]]-old[mapped[:,1]],axis=1)-length;after=np.linalg.norm(new[mapped[:,0]]-new[mapped[:,1]],axis=1)-length
                values.append({'frame':frame,'maximum_extension_before_cm':float(before.max()*100),'after_cm':float(after.max()*100),'p95_absolute_strain_before':float(np.percentile(np.abs(before/length),95)),'after':float(np.percentile(np.abs(after/length),95))})
            metrics.append({'pose':label,'frame_count':len(W),'frames':values})
        rows.append({'mesh':row['mesh'],'primitive':row['primitive'],'declared_changed_vertices':len(changed),'all_unlisted_joint_weight_values_identical':True,'original_equal_coincident_seam_pairs':int(originally_equal.sum()),'max_seam_weight_difference_after':seam_error,'metrics':metrics})
    result={'schema':'sub01.repaired-owner-written-skin-audit.v1','original_sha256':source.sha256,'derived_sha256':derived.sha256,'document_identical_including65nodes_ibms_and_all_material_texture_refs':True,'rows':rows,'garment_collision_clear':False,'source_ready':False,'native_ready':False};(out/'written-skin-readback-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'derived_sha256':derived.sha256,'summary':[{'seam_error':r['max_seam_weight_difference_after'],'poses':[{'pose':m['pose'],'frames':m['frame_count'],'maximum_before_cm':max(f['maximum_extension_before_cm']for f in m['frames']),'after_cm':max(f['after_cm']for f in m['frames'])}for m in r['metrics']]}for r in rows]}),flush=True)

if __name__=='__main__':run()
