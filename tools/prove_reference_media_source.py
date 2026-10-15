import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,'/home/unreal/runtime-tools')
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from home_asset_audit import read_gltf
from structural_rail_source_patch import accessor,world_matrices,transformed
root=Path('/workspace/sub01-home-private/real-media-console-source-r1/output');source=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb')
doc,blob=read_gltf(source);matrices=world_matrices(doc);protected=[]
def bounds(pts):return [[min(v[i]for v in pts)for i in range(3)],[max(v[i]for v in pts)for i in range(3)]]
def overlap(a,b):return all(a[0][i]<=b[1][i]and b[0][i]<=a[1][i]for i in range(3))
newrows=[]
export_doc,export_blob=read_gltf(root/'media-console-side-native.glb');export_matrices=world_matrices(export_doc)
for ni,node in enumerate(export_doc['nodes']):
 if 'mesh'not in node:continue
 pts=[];faces=[]
 for pr in export_doc['meshes'][node['mesh']]['primitives']:
  pv=[transformed(export_matrices[ni],v)for v in accessor(export_doc,export_blob,pr['attributes']['POSITION'])];pv=[Vector((v[0],-v[2],v[1]))for v in pv];ix=[v[0]for v in accessor(export_doc,export_blob,pr['indices'])];off=len(pts);pts+=pv;faces.extend(tuple(off+j for j in ix[i:i+3])for i in range(0,len(ix),3))
 newrows.append((node['name'],bounds(pts),BVHTree.FromPolygons(pts,faces,all_triangles=True,epsilon=0)))
for ni,node in enumerate(doc['nodes']):
 if'mesh'not in node:continue
 vertices=[];faces=[]
 for prim in doc['meshes'][node['mesh']]['primitives']:
  pts=[transformed(matrices[ni],v)for v in accessor(doc,blob,prim['attributes']['POSITION'])];pts=[Vector((v[0],-v[2],v[1]))for v in pts]
  pb=bounds(pts)
  if not any(overlap(pb,b)for name,b,tree in newrows):continue
  idx=[v[0]for v in accessor(doc,blob,prim['indices'])];off=len(vertices);vertices+=pts;faces.extend(tuple(off+j for j in idx[i:i+3])for i in range(0,len(idx),3))
 if not faces:continue
 row=(ni,bounds(vertices),BVHTree.FromPolygons(vertices,faces,all_triangles=True,epsilon=0))
 protected.append((*row,vertices,faces))
collisions=[]
for name,b,tree in newrows:
 for ni,pb,pt,vertices,faces in protected:
  if not overlap(b,pb):continue
  pairs=tree.overlap(pt)
  if pairs:
   bad=[]
   for ii,jj in pairs:
    tri=[vertices[k]for k in faces[jj]]
    floor=False
    if not floor:bad.append([ii,jj])
   collisions.append({'part':name,'source_node':ni,'pairs':len(pairs),'unresolved':len(bad),'examples':bad[:8]})
d={'schema':'sub01.reference-media-source-bvh.v1','native_changed':False,'sha256':hashlib.sha256((root/'media-console-side-native.glb').read_bytes()).hexdigest(),'parts':len(newrows),'epsilon_m':0,'ignored_collision_pairs':0,'retained_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'pairs':collisions,'ok':not any(x['unresolved']for x in collisions)}
(root/'side-source-collision-proof.json').write_text(json.dumps(d,indent=2));print(json.dumps(d),flush=True)
