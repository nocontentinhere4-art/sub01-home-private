"""Actual source arm triangles versus real desk/device surfaces, no native changes."""
import argparse,hashlib,json,sys,time
from pathlib import Path


def run(clip_path,output,samples_per_key=1,key_indices=None):
    import numpy as np
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    root=Path('/workspace/sub01-home-private/upright-footrest-full-9cd');sys.path[:0]=[str(root/'tools'),'/home/unreal/runtime-tools','/workspace/sub01-home-private/upright-footrest-python/scipy-1.14.1-cp311']
    import life_gltf as G
    import export_seat_fit_source as E
    import fit_seat_pelvis_pitch as P
    from home_asset_audit import read_gltf
    from structural_rail_source_patch import accessor,world_matrices,transformed
    began=time.monotonic();base=E.Source.load(root/'private-audit/seat-fit-source.npz');clip=G.Gltf(clip_path);times=np.asarray(clip.animation().key_times());assert samples_per_key in (1,2)
    if key_indices is not None:times=times[np.asarray(key_indices,int)]
    elif samples_per_key==2:times=np.sort(np.r_[times,(times[:-1]+times[1:])/2])
    mesh_source=G.Gltf('/workspace/sub01-home-private/fp-arms-candidate-r1/SUB01_FirstPersonArms_SourceCandidate.glb');assert mesh_source.sha256=='a862cbd3457c2b25da227c0eea2e04dcd8fe1f637115da0ccc69fbcf888ad154';p=mesh_source.doc['meshes'][0]['primitives'][0];a=p['attributes'];indices=E.accessor(mesh_source,p['indices']).astype(int).reshape(-1,3);ids,inverse=np.unique(indices,return_inverse=True);faces=inverse.reshape(-1,3);pos=E.accessor(mesh_source,a['POSITION'])[ids];joints=E.accessor(mesh_source,a['JOINTS_0'])[ids].astype(int);weights=E.accessor(mesh_source,a['WEIGHTS_0'])[ids];weights/=weights.sum(1,keepdims=True)
    objects=[]
    def add(path,select,label):
        doc,binary=read_gltf(Path(path));world=world_matrices(doc)
        for ni,node in enumerate(doc['nodes']):
            if 'mesh'not in node or not select(ni,node):continue
            for pi,primitive in enumerate(doc['meshes'][node['mesh']]['primitives']):
                vertices=np.asarray([transformed(world[ni],v)for v in accessor(doc,binary,primitive['attributes']['POSITION'])])*100;vertices=vertices[:,[0,2,1]];idx=np.asarray(accessor(doc,binary,primitive['indices']),int).reshape(-1,3);tri=vertices[idx];nonzero=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)>0;idx=idx[nonzero];tri=tri[nonzero]
                if not len(idx):continue
                objects.append({'label':label,'node':ni,'name':node.get('name'),'primitive':pi,'source_triangle_ids':np.flatnonzero(nonzero),'lo':tri.min((0,1)),'hi':tri.max((0,1)),'bvh':BVHTree.FromPolygons([Vector(v)for v in vertices],idx.tolist(),all_triangles=True,epsilon=0),'triangles':len(idx),'discarded_exact_zero_area_triangles':int((~nonzero).sum())})
    desk='/workspace/sub01-home-private/out/real-office-bundle/desk.glb';add(desk,lambda i,n:True,'genuine_LINEA_desk')
    home='/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb';assert hashlib.sha256(Path(home).read_bytes()).hexdigest()=='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b';add(home,lambda i,n:i in (184,185,186,187,237,238),'actual_keyboard_mouse_pad')
    issues=[];tested=0;pair_count=0
    out=Path(output);out.mkdir(exist_ok=False)
    for start in range(0,len(times),12):
        sample=times[start:start+12];W,_=E.joint_worlds(clip,base.names,sample);points=E.to_ue(P.skin_points((pos,joints,weights),base.ibm,W))
        for offset,vertices in enumerate(points):
            frame=start+offset;triangle=vertices[faces];low=triangle.min(1);high=triangle.max(1)
            for obj in objects:
                selected=np.flatnonzero(np.all(high>=obj['lo'],axis=1)&np.all(low<=obj['hi'],axis=1))
                if not len(selected):continue
                # Broadphase selects triangles, never excuses a triangle intersection.
                vi,remap=np.unique(faces[selected],return_inverse=True);bvh=BVHTree.FromPolygons([Vector(v)for v in vertices[vi]],remap.reshape(-1,3).tolist(),all_triangles=True,epsilon=0);pairs=bvh.overlap(obj['bvh']);tested+=1
                if pairs:
                    pair_count+=len(pairs);ai,bi=pairs[0];triangle_id=int(selected[ai]);issues.append({'sample':frame,'time_s':float(times[frame]),'source_arm_selected_triangle':triangle_id,'arm_world_triangle_ue_cm':triangle[triangle_id].tolist(),'object':obj['label'],'node':obj['node'],'name':obj['name'],'primitive':obj['primitive'],'object_source_triangle':int(obj['source_triangle_ids'][bi]),'triangle_intersection_pairs':len(pairs),'conservative_keycap_top_penetration_cm':max(0.,float(obj['hi'][2]-triangle[selected[np.unique([pair[0]for pair in pairs])],:,2].min()))if obj['label']=='actual_keyboard_mouse_pad'and obj['node']==187 else None})
        progress={'schema':'sub01.fp-arms-collision-progress.v1','samples_completed':min(start+12,len(times)),'samples_total':len(times),'elapsed_s':time.monotonic()-began,'collision_samples':len({i['sample']for i in issues})};(out/'progress.json').write_text(json.dumps(progress));(out/'partial-collision-witnesses.json').write_text(json.dumps(issues,indent=2));print(json.dumps(progress),flush=True)
    for issue in issues:issue['intentional_key_contact_within_existing0_1cm_rule']=issue['conservative_keycap_top_penetration_cm']is not None and issue['conservative_keycap_top_penetration_cm']<=.1
    report={'schema':'sub01.fp-arms-real-mesh-collision.v1','clip_sha256':clip.sha256,'arms_mesh_sha256':mesh_source.sha256,'samples':len(times),'samples_per_original_key':samples_per_key,'explicit_probe_keys':key_indices,'original_arm_triangles':len(faces),'actual_protected_objects':[{k:v for k,v in o.items()if k not in ('bvh','lo','hi','source_triangle_ids')}for o in objects],'bvh_broadphase_tests':tested,'triangle_intersection_pairs':pair_count,'issues':issues,'all_tested_source_triangle_surfaces_disjoint':not issues,'nonkey_or_excessive_key_contact_issues':[i for i in issues if not i['intentional_key_contact_within_existing0_1cm_rule']],'keyboard_contact_rule':'Existing fit_seat_pose_trial.KEY_PENETRATION_MAX_CM=.1; exact intersections retained/reported, not asserted absent','elapsed_s':time.monotonic()-began,'contact_accepted':False,'native_ready':False,'limitations':['Triangle intersection audit does not alone establish anatomical comfort, camera readiness or working PC input','Actual positive-area geometry used; exact zero-area source padding counted separately','Finite original keys plus requested midpoints, not mathematical continuous-time proof']};(out/'arms-mesh-collision.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items()if k not in ('issues','actual_protected_objects')}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--clip',required=True);p.add_argument('--output',required=True);p.add_argument('--samples-per-key',type=int,default=1);p.add_argument('--key-indices');a=p.parse_args(sys.argv[sys.argv.index('--')+1:]if '--'in sys.argv else None);run(a.clip,a.output,a.samples_per_key,[int(i)for i in a.key_indices.split(',')]if a.key_indices else None)
