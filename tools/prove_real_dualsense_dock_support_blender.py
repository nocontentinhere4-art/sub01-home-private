"""Read-only actual source contact proof for the genuine flat controller and owned steel dock."""
import sys,json,hashlib,math
from pathlib import Path
sys.path.insert(0,'/home/unreal/runtime-tools')
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from home_asset_audit import read_gltf
from structural_rail_source_patch import accessor,world_matrices,transformed
R=Path('/workspace/sub01-home-private/real-dualsense-chizuko-r1/native-source-r1');P=R/'real-dualsense-160mm.glb';S=Path('/workspace/sub01-home-private/ps5-datsketch-original-r1/support-r1/ps5-whole-base-support.glb')
def load(path,controller=False):
 d,b=read_gltf(path);w=world_matrices(d);points=[];faces=[]
 for n,node in enumerate(d['nodes']):
  if'mesh'not in node:continue
  for pr in d['meshes'][node['mesh']]['primitives']:
   off=len(points)
   for v in accessor(d,b,pr['attributes']['POSITION']):
    q=transformed(w[n],v);p=Vector((100*q[0],100*q[2],100*q[1]))
    if controller:p=Vector((-p.y-368.3,p.x-119.5,p.z+105.505))
    points.append(p)
   ix=[x[0]for x in accessor(d,b,pr['indices'])];faces.extend(tuple(off+j for j in ix[i:i+3])for i in range(0,len(ix),3))
 return points,faces
p,f=load(P,True);s,t=load(S);bt=BVHTree.FromPolygons(s,t,all_triangles=True,epsilon=0);ct=BVHTree.FromPolygons(p,f,all_triangles=True,epsilon=0);pairs=ct.overlap(bt);assert not pairs,len(pairs)
lo=[min(v[k]for v in p)for k in range(3)];hi=[max(v[k]for v in p)for k in range(3)];bottom=min(v.z for v in p);feet=[v for v in p if v.z<bottom+.001];hits=[]
for v in feet:
 hit,normal,face,distance=bt.ray_cast(v+Vector((0,0,1)),Vector((0,0,-1)),2)
 assert hit is not None and abs(hit.z-105.5)<.0001,(list(v),hit)
 hits.append({'controllerPointUEcm':list(v),'actualSupportPointUEcm':list(hit),'verticalGapCm':v.z-hit.z})
assert feet and min(x['verticalGapCm']for x in hits)>0
r={'schema':'sub01.genuine-dualsense-owned-dock-support.v1','source_sha256':hashlib.sha256(P.read_bytes()).hexdigest(),'support_sha256':hashlib.sha256(S.read_bytes()).hexdigest(),'rootTranslationUEcm':[-368.3,-119.5,105.505],'yawUEdegrees':90,'sourceCanonicalBottomZ':0,'actualControllerBoundsUEcm':[lo,hi],'actualTrayTopUEcm':105.5,'actualTrayBoundsXYcm':[[-376,-128.5],[-359.5,-110.5]],'actualLowestSourceVertices':hits,'completeControllerSteelIntersectionPairs':len(pairs),'ok':True,'nativeChanged':False,'nativePhysicalContactAccepted':False,'placementGapCm':.005};(R/'independent-dock-support.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items()if k!='actualLowestSourceVertices'}),flush=True)
