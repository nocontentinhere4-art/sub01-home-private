"""Read-only exact local triangle/capsule grid; no native/collider changes."""
import hashlib,json,sys,time
from pathlib import Path


def triangle_capsule_distances(tri, start, end):
    import numpy as np
    tri=np.asarray(tri,float);start=np.asarray(start,float);end=np.asarray(end,float)
    a,b,c=tri[:,0],tri[:,1],tri[:,2];ab=b-a;ac=c-a;n=np.cross(ab,ac);nn=np.sum(n*n,axis=1)
    def inside(q):
        return ((np.sum(np.cross(b-a,q-a)*n,axis=1)>=0)&(np.sum(np.cross(c-b,q-b)*n,axis=1)>=0)&(np.sum(np.cross(a-c,q-c)*n,axis=1)>=0))
    def point_distance(p):
        v=p-a;h=np.sum(v*n,axis=1)/nn;q=p-h[:,None]*n;result=np.where(inside(q),h*h*nn,np.inf)
        for x,y in [(a,b),(b,c),(c,a)]:
            edge=y-x;t=np.clip(np.sum((p-x)*edge,axis=1)/np.sum(edge*edge,axis=1),0,1);delta=p-(x+t[:,None]*edge);result=np.minimum(result,np.sum(delta*delta,axis=1))
        return result
    result=np.minimum(point_distance(start),point_distance(end));u=end-start;aa=np.dot(u,u)
    for x,y in [(a,b),(b,c),(c,a)]:
        v=y-x;r=start-x;ee=np.sum(v*v,axis=1);bb=v@u;cc=r@u;ff=np.sum(v*r,axis=1);den=aa*ee-bb*bb
        s=np.zeros(len(tri));good=den>np.finfo(float).eps*aa*ee;s[good]=np.clip((bb[good]*ff[good]-cc[good]*ee[good])/den[good],0,1);t=(bb*s+ff)/ee
        low=t<0;high=t>1;s[low]=np.clip(-cc[low]/aa,0,1);s[high]=np.clip((bb[high]-cc[high])/aa,0,1);t=np.clip(t,0,1);delta=(start+s[:,None]*u)-(x+t[:,None]*v);result=np.minimum(result,np.sum(delta*delta,axis=1))
    den=n@u;good=np.abs(den)>np.finfo(float).eps*np.sqrt(nn*aa);t=np.full(len(tri),np.inf);t[good]=np.sum(n[good]*(a[good]-start),axis=1)/den[good];q=np.zeros_like(a);q[good]=start+t[good,None]*u;hit=good&(t>=0)&(t<=1)&inside(q);result[hit]=0
    return np.sqrt(np.maximum(result,0))


def tests():
    import numpy as np
    tri=np.asarray([[[0,0,0],[1,0,0],[0,1,0]]],float)
    assert abs(triangle_capsule_distances(tri,[.2,.2,1],[.2,.2,2])[0]-1)<1e-12
    assert triangle_capsule_distances(tri,[.2,.2,-1],[.2,.2,1])[0]==0
    assert abs(triangle_capsule_distances(tri,[.2,.2,.5],[.8,.2,.5])[0]-.5)<1e-12
    assert abs(triangle_capsule_distances(tri,[2,0,-1],[2,0,1])[0]-1)<1e-12


def run():
    begun=time.monotonic();root=Path('/workspace/sub01-home-private/upright-footrest-full-9cd');sys.path[:0]=[str(root/'tools'),'/home/unreal/runtime-tools','/workspace/sub01-home-private/upright-footrest-python/scipy-1.14.1-cp311']
    import numpy as np
    from home_asset_audit import read_gltf
    from structural_rail_source_patch import accessor,world_matrices,transformed
    import solve_seated_typing_arm_ik as S
    tests();rows=[]
    def load(path,dy=0):
        d,b=read_gltf(path);m=world_matrices(d);tri=[]
        for ni,node in enumerate(d['nodes']):
            if 'mesh'not in node:continue
            for prim in d['meshes'][node['mesh']]['primitives']:
                p=np.asarray([transformed(m[ni],v)for v in accessor(d,b,prim['attributes']['POSITION'])])*100;p=p[:,[0,2,1]];p[:,1]+=dy;ids=np.asarray(accessor(d,b,prim['indices']),int).reshape(-1,3);tri.extend(p[ids])
        return np.asarray(tri)
    chair=S.load_complete_chair(S.load_chair());ct=chair['triangles_cm'].copy();ct[...,2]+=2.5001
    parts={'chair':ct,'desk':load(Path('/workspace/sub01-home-private/out/real-office-bundle/desk.glb')),'footrest':load(Path('/workspace/sub01-home-private/reference-footrest-source-r5/reference-footrest.glb'),8.692038729505747)}
    prepared={}
    for name,t in parts.items():
        positive=np.linalg.norm(np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]),axis=1)>0;t=t[positive];prepared[name]=(t,t.min(1),t.max(1));rows.append({'name':name,'physical_triangles':len(t),'bounds_ue_cm':[t.min((0,1)).tolist(),t.max((0,1)).tolist()]})
    def query(x,y,r):
        z=95.65;half=91.;p=np.asarray([x,y,z-half+r]);q=np.asarray([x,y,z+half-r]);best=None
        for name,(t,lo,hi)in prepared.items():
            near=(lo[:,0]<=x+r)&(hi[:,0]>=x-r)&(lo[:,1]<=y+r)&(hi[:,1]>=y-r)&(lo[:,2]<=q[2]+r)&(hi[:,2]>=p[2]-r);idx=np.flatnonzero(near)
            if not len(idx):continue
            dist=triangle_capsule_distances(t[idx],p,q);i=int(dist.argmin());w={'obstacle':name,'triangle':int(idx[i]),'distance_to_axis_cm':float(dist[i]),'clearance_cm':float(dist[i]-r),'actual_triangle_ue_cm':t[idx[i]].tolist()}
            if best is None or w['clearance_cm']<best['clearance_cm']:best=w
        return {'center_ue_cm':[x,y,z],'radius_cm':r,'halfheight_cm':half,'minimum':best,'locally_surface_clear':best is None or best['clearance_cm']>=0}
    report={'schema':'sub01.upright-standing-capsule-clearance-grid.v1','source_only':True,'read_only':True,'native_collision_query':False,'original_R16_and_review_R25_kept_distinct':True,'tests_pass':True,'scene':rows,'proposed_normalized_anchor':[query(200.025,-232.3,r)for r in (16.,25.)],'grid':[],'limitations':['Local chair/desk/footrest only; architecture and reachable route still require proof','Exact distance to physical triangles; no solid-containment classification for a whole capsule entirely enclosed in a solid','No full source body/skin acceptance from capsule clearance']}
    out=Path('/workspace/sub01-home-private/upright-capsule-clearance-r1');out.mkdir(exist_ok=False)
    for r in (16.,25.):
        entries=[query(float(x),float(y),r)for x in np.arange(140,261,10)for y in np.arange(-280,-179,10)]
        clear=[e for e in entries if e['locally_surface_clear']];clear.sort(key=lambda e:(e['center_ue_cm'][0]-200.025)**2+(e['center_ue_cm'][1]+232.3)**2)
        report['grid'].append({'radius_cm':r,'queried':len(entries),'free_count':len(clear),'closest_free_anchors':clear[:12],'all_entries':entries})
        if time.monotonic()-begun>100:break
    report['elapsed_s']=time.monotonic()-begun;(out/'capsule-clearance-grid.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'elapsed_s':report['elapsed_s'],'proposed':report['proposed_normalized_anchor'],'grid':[{'radius':e['radius_cm'],'free':e['free_count'],'closest':e['closest_free_anchors'][:2]}for e in report['grid']]}),flush=True)

if __name__=='__main__':run()
