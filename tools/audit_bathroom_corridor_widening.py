"""Bounded source-only full-house capsule path and exact sliding-leaf proof."""
import hashlib
import json
import time
from pathlib import Path


def run():
    import numpy as np
    from mathutils.bvhtree import BVHTree
    from mathutils import Vector
    from real_linea_lamp_mount import geometry
    from audit_upright_capsule_clearance import triangle_capsule_distances, tests
    from prepare_bathroom_corridor_widening import SOURCE_SHA, NODES
    begun=time.monotonic()
    source=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb')
    root=Path('/workspace/sub01-home-private/bathroom-corridor-source-r1')
    proof=json.loads((root/'bath-corridor.json').read_text())
    assert hashlib.sha256(source.read_bytes()).hexdigest()==SOURCE_SHA
    assert hashlib.sha256((root/'bath-corridor.glb').read_bytes()).hexdigest()==proof['export_sha256']
    tests()
    def rows(path):
        _,rs=geometry(path);out=[]
        for r in rs:
            p=np.asarray(r['points'],float)*100;p=p[:,[0,2,1]]
            t=p[np.asarray(r['triangles'],int)]
            positive=np.linalg.norm(np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]),axis=1)>0
            out.append((r['node'],t[positive]))
        return out
    original=rows(source)
    derived=rows(root/'bath-corridor.glb')
    node_map={i:p['source_node'] for i,p in enumerate(proof['parts'])}
    derived=[(node_map[n],t)for n,t in derived]
    # The existing proven panel track fit is independent of the room resize.
    def fit(rs):
        return [(n,t+np.asarray([11.2,0,0]) if n==118 else t)for n,t in rs]
    original=fit(original);derived=fit(derived)
    adjusted=[(n,t)for n,t in original if n not in NODES]+derived
    def prepare(rs):
        ts=[];nodes=[]
        for n,t in rs:
            lo=t.min(1);hi=t.max(1)
            near=(hi[:,0]>=-180)&(lo[:,0]<=0)&(hi[:,1]>=-60)&(lo[:,1]<=300)&(hi[:,2]>=300)&(lo[:,2]<=510)
            ts.extend(t[near]);nodes.extend([n]*int(near.sum()))
        t=np.asarray(ts);return t,np.asarray(nodes),t.min(1),t.max(1)
    old=prepare(original);new=prepare(adjusted)
    def query(scene,x,y,z,radius):
        t,nodes,lo,hi=scene;p=np.asarray([x,y,z-91+radius]);q=np.asarray([x,y,z+91-radius])
        mask=(lo[:,0]<=x+radius)&(hi[:,0]>=x-radius)&(lo[:,1]<=y+radius)&(hi[:,1]>=y-radius)&(lo[:,2]<=q[2]+radius)&(hi[:,2]>=p[2]-radius)
        selected=np.flatnonzero(mask)
        if not len(selected):return {'position_cm':[x,y,z],'clearance_cm':None,'clear':True}
        distances=triangle_capsule_distances(t[selected],p,q);j=int(distances.argmin());idx=int(selected[j]);gap=float(distances[j]-radius)
        return {'position_cm':[x,y,z],'clearance_cm':gap,'clear':gap>=-1e-6,'source_node':int(nodes[idx]),'triangle_cm':t[idx].tolist()}
    old16=[];old25=[];new25=[]
    for y in np.arange(-20,135.001,2.5):
        old16.append(query(old,-50,float(y),395.65,16))
        old25.append(query(old,-50,float(y),395.65,25))
        x=-60 if y<=90 else -60+(float(y)-90)/45*3.3
        new25.append(query(new,x,float(y),395.65,25))
    # Open the real leaf, then traverse the reviewed 95cm sliding opening.
    opened=[(n,t+np.asarray([0,95,0]) if n==118 else t)for n,t in adjusted]
    open_scene=prepare(opened)
    for x in np.arange(-56.7,-150.001,-2.5):
        # The existing 2.75cm tile step is not a new world-height change.
        new25.append(query(open_scene,float(x),135.,398.4 if x<-70 else 395.65,25))
    def summary(rs):
        finite=[r for r in rs if r['clearance_cm']is not None]
        return {'samples':len(rs),'clear':all(r['clear']for r in rs),'minimum':min(finite,key=lambda r:r['clearance_cm']) if finite else None,'failures':[r for r in rs if not r['clear']]}
    static=[];door=None
    for n,t in adjusted:
        if n==118:door=t;continue
        lo=t.min(1);hi=t.max(1)
        mask=(lo[:,0]<=-85)&(hi[:,0]>=-93)&(lo[:,1]<=275)&(hi[:,1]>=90)&(lo[:,2]<=506)&(hi[:,2]>=304)
        static.extend(t[mask])
    def bvh(tri):
        p=np.asarray(tri).reshape(-1,3)
        return BVHTree.FromPolygons([Vector(v)for v in p],[(i,i+1,i+2)for i in range(0,len(p),3)],all_triangles=True,epsilon=0)
    swept_min=door.min((0,1));swept_max=door.max((0,1))+np.asarray([0,95,0])
    continuous_candidates=0
    for n,t in adjusted:
        if n==118:continue
        lo=t.min(1);hi=t.max(1)
        continuous_candidates+=int(np.all((lo<=swept_max)&(hi>=swept_min),axis=1).sum())
    fixed=bvh(static) if static else None;sweep=[]
    for offset in range(96):
        hits=bvh(door+np.asarray([0,offset,0])).overlap(fixed) if fixed else []
        if hits:sweep.append({'slide_cm':offset,'actual_triangle_pairs':len(hits)})
        if time.monotonic()-begun>105:raise TimeoutError('Bounded source proof exceeded105s')
    report={'schema':'sub01.bathroom-corridor-source-clearance-proof.v1','source_sha256':SOURCE_SHA,'derived_sha256':proof['export_sha256'],
            'original_R16':summary(old16),'original_R25':summary(old25),'adjusted_R25':summary(new25),
            'full_source_positive_triangles':sum(len(t)for _,t in original),'unchanged_source_nodes':len(original)-len(NODES),
            'door_sweep_poses':96,'door_sweep_step_cm':1,'door_sweep_collisions':sweep,
            'continuous_full_door_swept_AABB_candidate_triangles':continuous_candidates,
            'continuous_full_source_door_sweep_clear':continuous_candidates==0,
            'door_sweep_scope':'Exact full300-triangle leaf, existing11.2cm track fit, all other actual955 source triangles and derived architecture retained.',
            'capsule_samples_step_cm':2.5,'continuous_capsule_path_verified':False,
            'limitations':['Sampled finite-triangle clearance; native collision hulls/continuous movement/privacy still require actual tests.','No architectural/world/native mutation in this proof.'],
            'elapsed_s':time.monotonic()-begun,'native_imported':False,'native_route_accepted':False}
    report['source_sampled_path_and_sweep_pass']=report['adjusted_R25']['clear'] and not sweep and continuous_candidates==0
    (root/'source-clearance-proof.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)
    if not report['source_sampled_path_and_sweep_pass']:raise RuntimeError('Source physical clearance refused; no native activation')
