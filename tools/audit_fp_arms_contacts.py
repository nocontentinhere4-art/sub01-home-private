"""Actual source keycap/curved-mouse proximity; never source/native acceptance."""
import hashlib,json,sys,time,gzip
from pathlib import Path


def run():
    began=time.monotonic();root=Path('/workspace/sub01-home-private/upright-footrest-full-9cd');sys.path[:0]=[str(root/'tools'),'/home/unreal/runtime-tools','/workspace/sub01-home-private/upright-footrest-python/scipy-1.14.1-cp311']
    import numpy as np
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    import life_gltf as G
    import export_seat_fit_source as E
    import fit_seat_pose_trial as T
    import solve_seated_typing_arm_ik as S
    from home_asset_audit import read_gltf
    from structural_rail_source_patch import accessor,world_matrices,transformed
    owner=Path('/workspace/sub01-home-private/owner-shoulder-derived-r3/owner-shoulder-derived.glb');assert hashlib.sha256(owner.read_bytes()).hexdigest()=='831790a62b81e7e2faa5a201e04740d0911c5bfebd49aa03b124808521e3a2b1';E.OWNER=owner
    raw=G.Gltf('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/owner-with-clips-unreal.glb');assert raw.sha256=='45e917725f02836dee6d051d9b47dd2785208c78b503fa935ddb322fe69adea8';raw.doc['animations']=[a for a in raw.doc['animations']if a['name']=='typing'];times=np.asarray(raw.animation().key_times());base=E.Source.load(root/'private-audit/seat-fit-source.npz');W,_=E.joint_worlds(raw,base.names,times)
    home=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb');assert hashlib.sha256(home.read_bytes()).hexdigest()=='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b';doc,binary=read_gltf(home);world=world_matrices(doc)
    def geometry(node):
        n=doc['nodes'][node];prims=doc['meshes'][n['mesh']]['primitives'];assert len(prims)==1;pr=prims[0];p=np.asarray([transformed(world[node],v)for v in accessor(doc,binary,pr['attributes']['POSITION'])])*100;p=p[:,[0,2,1]];idx=np.asarray(accessor(doc,binary,pr['indices']),int).reshape(-1,3);tri=p[idx];return p,idx,tri,doc['materials'][pr['material']]['name']
    kp,ki,kt,km=geometry(187);assert doc['nodes'][187]['name']=='mesh_3'and km=='keycap'
    # Connected keycaps, welded only for analysis; every returned top triangle is original source geometry.
    _,inverse=np.unique(np.round(kp,5),axis=0,return_inverse=True);parent=list(range(int(inverse.max())+1))
    def find(a):
        a=int(a)
        while parent[a]!=a:parent[a]=parent[parent[a]];a=parent[a]
        return a
    for face in inverse[ki]:
        a,b,c=map(find,face);parent[b]=a;parent[c]=a
    comp=np.asarray([find(i)for i in inverse]);top=np.full(len(parent),-np.inf);np.maximum.at(top,comp,kp[:,2]);normal=np.cross(kt[:,1]-kt[:,0],kt[:,2]-kt[:,0]);length=np.linalg.norm(normal,axis=1);flat=(length>0)&(np.abs(normal[:,2])/np.maximum(length,1e-30)>.9)&(kt.mean(1)[:,2]>=top[comp[ki[:,0]]]-.12);tops=kt[flat];surface=T.Surface(tops)
    mp,mi,mt,mm=geometry(237);assert doc['nodes'][237]['name']=='mouse'and mm=='mouse';mouse=BVHTree.FromPolygons([Vector(p)for p in mp],mi.tolist(),all_triangles=True,epsilon=0);mlo,mhi=mp.min(0),mp.max(0)
    _,mweld=np.unique(np.round(mp,5),axis=0,return_inverse=True);edges=np.concatenate((mweld[mi][:,[0,1]],mweld[mi][:,[1,2]],mweld[mi][:,[2,0]]));edges.sort(1);_,count=np.unique(edges,axis=0,return_counts=True)
    result={'schema':'sub01.fp-arms-real-surface-contact-audit.v1','owner_sha256':hashlib.sha256(owner.read_bytes()).hexdigest(),'captured_owner_sha256':raw.sha256,'action':'typing','keys':len(times),'duration_s':float(times[-1]),'source_body_world_cm':list(E.BODY_CM),'source_body_yaw':E.BODY_YAW,'no_pose_or_finger_edits':True,'keycap_source_node':187,'keycap_top_triangles':len(tops),'keycap_components':len(np.unique(comp[ki[:,0]])),'keycap_top_bounds_ue_cm':[tops.min((0,1)).tolist(),tops.max((0,1)).tolist()],'mouse_source_node':237,'mouse_bounds_ue_cm':[mlo.tolist(),mhi.tolist()],'mouse_boundary_or_nonmanifold_edges':int((count!=2).sum()),'mouse_contact_not_a_flat_plane':True,'hands':{},'native_ready':False,'source_ready':False,'contact_accepted':False}
    for side in ('left','right'):
        points,_=base.skin(side+'_fingers',W);p=E.to_ue(points);found,height=surface.height(p[...,:2].reshape(-1,2));found=found.reshape(p.shape[:2]);height=height.reshape(p.shape[:2]);gap=np.where(found,p[...,2]-height,np.inf);minimum=gap.min(1);over=found.sum(1);nearest_mouse=[];nearest_witness=[]
        for f,pts in enumerate(p):
            choose=np.flatnonzero(np.all((pts[:,:2]>=mlo[:2]-.5)&(pts[:,:2]<=mhi[:2]+.5),axis=1));best=None
            for vi in choose:
                location,normal,tri,distance=mouse.find_nearest(Vector(pts[vi]));row={'distance_cm':float(distance),'point_ue_cm':pts[vi].tolist(),'nearest_surface_ue_cm':list(location),'triangle':int(tri),'distal_region_vertex':int(vi)}
                if best is None or distance<best['distance_cm']:best=row
            nearest_mouse.append(None if best is None else best['distance_cm']);nearest_witness.append(best)
        flex,dev,twist=S.wrist_angles(W,base.names,base.ibm,side);bins=[]
        for sec in range(int(np.ceil(times[-1]))):
            mask=(times>=sec)&(times<sec+1);values=minimum[mask];values=values[np.isfinite(values)];md=[x for x,m in zip(nearest_mouse,mask)if m and x is not None]
            bins.append({'second':sec,'key_overlap_frames':int((over[mask]>0).sum()),'minimum_key_gap_cm':None if not len(values)else float(values.min()),'maximum_nearest_key_gap_cm':None if not len(values)else float(values.max()),'key_penetration_over_0_1cm_frames':int((minimum[mask]<-.1).sum()),'key_nearest_pad_0_to_0_2cm_frames':int(((minimum[mask]>=0)&(minimum[mask]<=.2)).sum()),'mouse_nearest_distance_min_cm':min(md)if md else None})
        worst=int(minimum.argmin());vi=int(gap[worst].argmin());result['hands'][side]={'distal_surface_vertices':p.shape[1],'key_overlap_vertices_by_frame':over.tolist(),'nearest_key_gap_cm':[float(x)if np.isfinite(x)else None for x in minimum],'key_penetration_over0_1cm_frames':np.flatnonzero(minimum<-.1).tolist(),'worst_key_witness':{'frame':worst,'time_s':float(times[worst]),'skin_point_ue_cm':p[worst,vi].tolist(),'real_key_top_z_cm':float(height[worst,vi]),'gap_cm':float(minimum[worst])},'mouse_unsigned_nearest_cm':nearest_mouse,'mouse_closest_witness':min((v for v in nearest_witness if v is not None),key=lambda v:v['distance_cm'],default=None),'wrist_flexion_range_deg':[float(flex.min()),float(flex.max())],'wrist_deviation_range_deg':[float(dev.min()),float(dev.max())],'wrist_twist_range_deg':[float(twist.min()),float(twist.max())],'bins':bins}
    result.update(elapsed_s=time.monotonic()-began,limitations=['Raw captured source placement is being measured, not the obsolete perch solve','Mouse unsigned proximity does not prove no penetration or accepted grip','Source finger-pad selector is original native distaljoint3weight>=0.30; all finger local rotations unchanged','Full hand/forearm versus genuine desk board collision, camera cut and native pixels/input remain pending'])
    out=Path('/workspace/sub01-home-private/fp-arms-contact-audit-r1');out.mkdir(exist_ok=False);(out/'arms-real-surface-contact.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'elapsed_s':result['elapsed_s'],'hands':{s:{'keypenetrationframes':len(v['key_penetration_over0_1cm_frames']),'worstkey':v['worst_key_witness'],'mouseclosest':v['mouse_closest_witness'],'bins':v['bins']}for s,v in result['hands'].items()}}),flush=True)

if __name__=='__main__':run()
