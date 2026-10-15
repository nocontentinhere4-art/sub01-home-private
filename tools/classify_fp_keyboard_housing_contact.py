"""Read-only exact housing witnesses; signed local normals are not solid containment."""
import hashlib,json,sys,time
from pathlib import Path


def run():
    import numpy as np
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    root=Path('/workspace/sub01-home-private/upright-footrest-full-9cd');sys.path[:0]=[str(root/'tools'),'/home/unreal/runtime-tools','/workspace/sub01-home-private/upright-footrest-python/scipy-1.14.1-cp311']
    import life_gltf as G
    import export_seat_fit_source as E
    import fit_seat_pelvis_pitch as P
    from home_asset_audit import read_gltf
    from structural_rail_source_patch import accessor,world_matrices,transformed
    began=time.monotonic();base=E.Source.load(root/'private-audit/seat-fit-source.npz');clip=G.Gltf('/workspace/sub01-home-private/fp-keyboard-loop-r3/SUB01_FirstPersonKeyboard_LoopCandidate.glb');assert clip.sha256=='0cd1395b0b1d8187c928aeb93950df69abc67f7eeefa91ed1df58c1ea761f5db';mask=G.Gltf('/workspace/sub01-home-private/fp-arms-candidate-r1/SUB01_FirstPersonArms_SourceCandidate.glb');pr=mask.doc['meshes'][0]['primitives'][0];attrs=pr['attributes'];faces=E.accessor(mask,pr['indices']).astype(int).reshape(-1,3);pos=E.accessor(mask,attrs['POSITION']);joints=E.accessor(mask,attrs['JOINTS_0']).astype(int);weights=E.accessor(mask,attrs['WEIGHTS_0']);weights/=weights.sum(1,keepdims=True)
    path=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb');assert hashlib.sha256(path.read_bytes()).hexdigest()=='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b';doc,binary=read_gltf(path);world=world_matrices(doc);p=doc['meshes'][doc['nodes'][185]['mesh']]['primitives'][0];hp=np.asarray([transformed(world[185],v)for v in accessor(doc,binary,p['attributes']['POSITION'])])*100;hp=hp[:,[0,2,1]];hi=np.asarray(accessor(doc,binary,p['indices']),int).reshape(-1,3);area=np.linalg.norm(np.cross(hp[hi[:,1]]-hp[hi[:,0]],hp[hi[:,2]]-hp[hi[:,0]]),axis=1);valid=np.flatnonzero(area>0);housing=BVHTree.FromPolygons([Vector(v)for v in hp],hi[valid].tolist(),all_triangles=True,epsilon=0);norm=np.asarray(accessor(doc,binary,p['attributes']['NORMAL']))
    # Authored source world transforms are handled with transformed(), also for normal directions.
    origin=np.asarray(transformed(world[185],[0,0,0]));linear=np.stack([np.asarray(transformed(world[185],v))-origin for v in np.eye(3)],axis=1);hn=norm@np.linalg.inv(linear);hn=hn[:,[0,2,1]];hn/=np.maximum(np.linalg.norm(hn,axis=1,keepdims=True),1e-30)
    _,weld=np.unique(np.round(hp,5),axis=0,return_inverse=True);edge=np.concatenate((weld[hi][:,[0,1]],weld[hi][:,[1,2]],weld[hi][:,[2,0]]));edge.sort(1);_,counts=np.unique(edge,axis=0,return_counts=True)
    receipt=json.loads(Path('/workspace/sub01-home-private/fp-keyboard-loop-r3/collision/arms-mesh-collision.json').read_text());issues=[r for r in receipt['issues']if r['node']==185 and r['object']=='actual_keyboard_mouse_pad'];rows=[]
    for issue in issues:
        frame_time=issue['time_s'];ids=faces[issue['source_arm_selected_triangle']];W,_=E.joint_worlds(clip,base.names,[frame_time]);tri=E.to_ue(P.skin_points((pos[ids],joints[ids],weights[ids]),base.ibm,W))[0];points=np.r_[tri,tri.mean(0)[None],(tri+np.roll(tri,-1,axis=0))/2];nearest=[]
        for point in points:
            location,bvh_normal,ti,distance=housing.find_nearest(Vector(point));ti=int(valid[ti]);face=hp[hi[ti]];geometric=np.cross(face[1]-face[0],face[2]-face[0]);geometric/=np.linalg.norm(geometric);authored=hn[hi[ti]].mean(0)
            if np.dot(geometric,authored)<0:geometric=-geometric
            nearest.append({'skin_point_ue_cm':point.tolist(),'housing_point_ue_cm':list(location),'housing_triangle':int(ti),'unsigned_nearest_cm':float(distance),'authored_oriented_local_signed_plane_cm':float(np.dot(point-np.asarray(location),geometric))})
        influence=[]
        for vertex in ids:
            influence.append({'source_body_vertex':int(vertex),'weights':{base.names[int(j)]:float(w)for j,w in zip(joints[vertex],weights[vertex])if w>1e-6}})
        rows.append({'time_s':frame_time,'source_selected_triangle':issue['source_arm_selected_triangle'],'source_influences':influence,'actual_skin_triangle_ue_cm':tri.tolist(),'nearest_surface_samples':nearest,'minimum_local_signed_plane_cm':min(n['authored_oriented_local_signed_plane_cm']for n in nearest),'maximum_unsigned_distance_cm':max(n['unsigned_nearest_cm']for n in nearest)})
    report={'schema':'sub01.fp-keyboard-housing-contact-classification.v1','clip_sha256':clip.sha256,'exact_source_node':185,'source_node_name':doc['nodes'][185]['name'],'source_material':doc['materials'][p['material']]['name'],'source_housing_bounds_ue_cm':[hp.min(0).tolist(),hp.max(0).tolist()],'housing_exact_zero_area_source_triangles':int((area==0).sum()),'housing_positive_area_triangles':len(valid),'housing_open_or_nonmanifold_edges':int((counts!=2).sum()),'housing_collision_samples':len(rows),'witnesses':rows,'inside_volume_certified':False,'limitations':['Local signed nearest-plane distance uses the authored outward normal; it is not certified closed-solid penetration depth','All original triangle intersections are retained; no collision exemption or contact gate changed','Source/native/activity acceptance remain false; this is a private visual-review candidate'],'elapsed_s':time.monotonic()-began,'source_ready':False,'native_ready':False};out=Path('/workspace/sub01-home-private/fp-keyboard-loop-r3/housing-contact-classification-r2.json');out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)

if __name__=='__main__':run()
