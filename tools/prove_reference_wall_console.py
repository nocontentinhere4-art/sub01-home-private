"""Runpod Blender: exact source BVH against home955 plus preserved media cabinet."""
import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,'/home/unreal/runtime-tools')
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from home_asset_audit import read_gltf
from structural_rail_source_patch import accessor,world_matrices,transformed
ROOT=Path('/workspace/sub01-home-private/reference-wall-console-r1/output')
HOME=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb')
MEDIA=Path('/workspace/sub01-home-private/real-media-console-source-r1/output/media-console-side-native.glb')
def bounds(vs):return [[min(v[i]for v in vs)for i in range(3)],[max(v[i]for v in vs)for i in range(3)]]
def overlap(a,b):return all(a[0][i]<=b[1][i]and b[0][i]<=a[1][i]for i in range(3))
def rows(path,filter_cabinet=False):
 d,b=read_gltf(path);m=world_matrices(d);out=[]
 for ni,n in enumerate(d['nodes']):
  if 'mesh'not in n:continue
  mesh=d['meshes'][n['mesh']]
  if filter_cabinet:
   names=[d['materials'][p['material']]['name']for p in mesh['primitives']]
   if any(s.startswith('Console ')or s=='controller'for s in names):continue
  pts=[];faces=[]
  for pr in mesh['primitives']:
   pv=[transformed(m[ni],v)for v in accessor(d,b,pr['attributes']['POSITION'])];pv=[Vector((v[0],-v[2],v[1]))for v in pv];ix=[v[0]for v in accessor(d,b,pr['indices'])];off=len(pts);pts+=pv;faces.extend(tuple(off+j for j in ix[i:i+3])for i in range(0,len(ix),3))
  out.append((n['name'],bounds(pts),BVHTree.FromPolygons(pts,faces,all_triangles=True,epsilon=0),pts,faces))
 return out
WINDOWS=Path('/workspace/sub01-home-private/out/real-home-windows-r2/real-home-windows.glb')
DOORS=Path('/workspace/sub01-home-private/authentic-bath-doors-fit-r6/output/door-assemblies.glb')
new=rows(ROOT/'wall-console.glb');old=rows(HOME)+rows(MEDIA,True)+rows(WINDOWS)+rows(DOORS);collisions=[];contacts=[]
for name,b,tree,vs,fs in new:
 for on,ob,ot,ovs,ofs in old:
  if not overlap(b,ob):continue
  pairs=tree.overlap(ot)
  if pairs:
   # Exact coplanar rear face contact is the manufactured wall attachment.
   # No penetration tolerance: use the identical GLB float32 wall coordinate.
   plane=-3.7699999809265137;contact=[];bad=[]
   for ii,jj in pairs:
    wall_face=[ovs[k]for k in ofs[jj]];new_face=[vs[k]for k in fs[ii]]
    if name=='WCPart04'and on=='house-static-67'and all(v.x==plane for v in wall_face)and all(v.x>=plane for v in new_face):contact.append((ii,jj))
    else:bad.append((ii,jj))
   if contact:contacts.append({'part':name,'protected_part':on,'pairs':len(contact),'classification':'exact rear surface attachment, no vertex behind actual float32 wall plane','actual_wall_plane_x_m':plane})
   if bad:collisions.append({'part':name,'protected_part':on,'pairs':len(bad),'examples':bad[:5]})
r={'schema':'sub01.reference-wall-console-bvh.v1','sha256':hashlib.sha256((ROOT/'wall-console.glb').read_bytes()).hexdigest(),'protected_home_sha256':hashlib.sha256(HOME.read_bytes()).hexdigest(),'protected_cabinet_source_sha256':hashlib.sha256(MEDIA.read_bytes()).hexdigest(),'actual_window_source_sha256':hashlib.sha256(WINDOWS.read_bytes()).hexdigest(),'actual_door_source_sha256':hashlib.sha256(DOORS.read_bytes()).hexdigest(),'protected_parts':len(old),'parts':len(new),'epsilon_m':0,'ignored_pairs':0,'measured_attachment_contacts':contacts,'unresolved':collisions,'ok':not collisions,'native_changed':False}
# Independently compare all per-material triangle edge lengths after rigid motion.
# Source and current export float32 corners are read afresh; stand is deliberately retired.
import math
report=json.loads((ROOT/'source-report.json').read_text())
def edges_by_material(path):
 d,b=read_gltf(path);ms=world_matrices(d);out={}
 for ni,n in enumerate(d['nodes']):
  if'mesh'not in n:continue
  for pr in d['meshes'][n['mesh']]['primitives']:
   name=d['materials'][pr['material']]['name'];pts=[transformed(ms[ni],v)for v in accessor(d,b,pr['attributes']['POSITION'])];ix=[v[0]for v in accessor(d,b,pr['indices'])];dest=out.setdefault(name,[])
   for k in range(0,len(ix),3):
    t=[pts[ix[k+j]]for j in range(3)];dest.append(tuple(sorted(math.dist(t[i],t[(i+1)%3])for i in range(3))))
 return {name:sorted(values)for name,values in out.items()}
original_edges=edges_by_material(MEDIA);new_edges=edges_by_material(ROOT/'wall-console.glb');congruency=[]
for part in report['parts']:
 name=part['source_material']
 if name=='Wall mount powder coated steel':continue
 old_edges=original_edges[name];current_edges=new_edges[part['material']]
 from mathutils.kdtree import KDTree
 def nearest_error(reference,other):
  tree=KDTree(len(reference))
  for index,v in enumerate(reference):tree.insert(Vector(v),index)
  tree.balance()
  return max((tree.find(Vector(v))[2]for v in other),default=0.)
 error=max(nearest_error(old_edges,current_edges),nearest_error(current_edges,old_edges))if len(old_edges)==len(current_edges)else None
 congruency.append({'source_material':name,'original_triangles':len(old_edges),'current_triangles':len(current_edges),'maximum_bidirectional_triangle_edge_shape_distance_m':error,'ok':error is not None and error<.000002})
r['rigid_reuse_congruency']=congruency;r['ok']=r['ok']and all(x['ok']for x in congruency)
(ROOT/'source-collision-proof.json').write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True)
