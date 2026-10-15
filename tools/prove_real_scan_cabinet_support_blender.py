"""Independent real scan whole-mesh support and cabinet/screen clearance; no asset edits."""
import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,'/home/unreal/runtime-tools')
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from home_asset_audit import read_gltf
from structural_rail_source_patch import accessor,world_matrices,transformed
R=Path('/workspace/sub01-home-private/real-scanned-pikachu-r1');P=R/'source/modelpika_updated.glb';C=Path('/workspace/sub01-home-private/reference-living-tv-wall-r3/output/living-cabinet.glb')
def load(path):
 d,b=read_gltf(path);w=world_matrices(d);p=[];f=[]
 for i,n in enumerate(d['nodes']):
  if'mesh'not in n:continue
  for pr in d['meshes'][n['mesh']]['primitives']:
   off=len(p)
   for v in accessor(d,b,pr['attributes']['POSITION']):
    q=transformed(w[i],v);p.append(Vector((q[0]*100,q[2]*100,q[1]*100)))
   ix=[x[0]for x in accessor(d,b,pr['indices'])];f.extend(tuple(off+j for j in ix[k:k+3])for k in range(0,len(ix),3))
 return p,f
p,f=load(P);c,g=load(C);lo=Vector([min(v[k]for v in p)for k in range(3)]);hi=Vector([max(v[k]for v in p)for k in range(3)]);scale=20/(hi.z-lo.z);xy=Vector((-351,60,0));shift=Vector((-351-(lo.x+hi.x)*scale/2,60-(lo.y+hi.y)*scale/2,0));p=[v*scale+shift for v in p];bt=BVHTree.FromPolygons(c,g,all_triangles=True,epsilon=0);lowest=min(v.z for v in p);feet=[v for v in p if v.z<=lowest+.01];hits=[]
for v in feet:
 hit,n,face,dist=bt.ray_cast(Vector((v.x,v.y,60)),Vector((0,0,-1)),10);assert hit is not None and hit.z>56
 hits.append(hit.z-v.z)
lift=max(hits)+.001;p=[v+Vector((0,0,lift))for v in p];pairs=BVHTree.FromPolygons(p,f,all_triangles=True,epsilon=0).overlap(bt);assert not pairs,len(pairs);bounds=[[min(v[k]for v in p)for k in range(3)],[max(v[k]for v in p)for k in range(3)]];assert bounds[1][2]<117.5
r={'schema':'sub01.real-scan-miniature-cabinet-support.v1','source_sha256':hashlib.sha256(P.read_bytes()).hexdigest(),'cabinet_sha256':hashlib.sha256(C.read_bytes()).hexdigest(),'uniformExternalScale':scale,'rootTranslationUEcm':[shift.x,shift.y,lift],'heightCm':20,'boundsUEcm':bounds,'lowestSourceFootVerticesSupported':len(feet),'minimumFootGapCm':.001,'completeSourceTriangleIntersectionPairs':len(pairs),'screenBottomHeightCm':117.5,'verticalScreenClearanceCm':117.5-bounds[1][2],'sourceMeshMaterialsUnchanged':True,'ok':True,'nativeInstalled':False};(R/'review/independent-cabinet-support.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))
