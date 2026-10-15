"""Runpod Blender BVH proof against actual retained house/new patio hardware."""
import sys,json,hashlib
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree
sys.path.insert(0,'/home/unreal/runtime-tools')
from home_asset_audit import read_gltf
from structural_rail_source_patch import accessor,world_matrices,transformed
ROOT=Path('/workspace/sub01-home-private/reference-curtain-source-r1/output')
HOME=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb')
DOORS=Path('/workspace/sub01-home-private/authentic-bath-doors-fit-r6/output/door-assemblies.glb')
assert hashlib.sha256(HOME.read_bytes()).hexdigest()=='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
assert hashlib.sha256(DOORS.read_bytes()).hexdigest()=='5b8a2bb8b4bb8fe19af1d0c086fb78f3e7f9dff9e06170a06642a8f3d1761a0c'

def box(p):return [[min(v[k]for v in p)for k in range(3)],[max(v[k]for v in p)for k in range(3)]]
def overlap(a,b):return all(a[0][k]<=b[1][k]and b[0][k]<=a[1][k]for k in range(3))
def geometries(path,skip=()):
 d,b=read_gltf(path);matrices=world_matrices(d)
 for i,n in enumerate(d['nodes']):
  if'mesh'not in n or i in skip:continue
  pts=[];faces=[]
  for p in d['meshes'][n['mesh']]['primitives']:
   vs=[transformed(matrices[i],v)for v in accessor(d,b,p['attributes']['POSITION'])];vs=[Vector((v[0]*100,v[2]*100,v[1]*100))for v in vs];ix=[v[0]for v in accessor(d,b,p['indices'])];off=len(pts);pts+=vs;faces.extend(tuple(off+j for j in ix[k:k+3])for k in range(0,len(ix),3))
  yield i,n.get('name'),pts,faces
source=ROOT/'reference-sheer-native.glb';new=[]
for i,n,pts,faces in geometries(source):new.append((n,box(pts),BVHTree.FromPolygons(pts,faces,all_triangles=True,epsilon=0)))
hits=[];tested=0
for label,path,skip in[('retained-home',HOME,tuple(range(41,49))),('current-exact-doors',DOORS,())]:
 for ni,name,pts,faces in geometries(path,skip):
  tested+=1;b=box(pts)
  if not any(overlap(b,row[1])for row in new):continue
  tree=BVHTree.FromPolygons(pts,faces,all_triangles=True,epsilon=0)
  for newname,nb,nt in new:
   if not overlap(nb,b):continue
   pairs=nt.overlap(tree)
   if pairs:hits.append({'new':newname,'protected_packet':label,'source_node':ni,'source_name':name,'triangle_pairs':len(pairs),'examples':pairs[:4]})
# Full continuous91cm horizontal motion is separated from both cloth surfaces
# by more than12cm depth. Hardware is above the complete moving door envelope.
left=next(r for r in new if r[0]=='SCLeft');right=next(r for r in new if r[0]=='SCRight');hardware=next(r for r in new if r[0]=='SCHardware')
sweep_clear=left[1][1][1]<400.55 and right[1][1][1]<400.55 and hardware[1][0][2]>515.05
r={'schema':'sub01.reference-sheer-actual-source-bvh.v1','native_changed':False,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'epsilon_cm':0,'unresolved':hits,'ok':not hits and sweep_clear,'retired_old_balcony_nodes_excluded':list(range(41,49)),'retirement_owner':'actual saved authentic-door packet5b8a2bb8','current_door_source_sha256':hashlib.sha256(DOORS.read_bytes()).hexdigest(),'retained_home_source_sha256':hashlib.sha256(HOME.read_bytes()).hexdigest(),'protected_nodes_tested':tested,'full91cm_door_sweep_separated':sweep_clear,'native_material_translucency_verified':False,'native_shadows_verified':False}
(ROOT/'source-bvh-proof.json').write_text(json.dumps(r,indent=2));print('ACTUAL_SHEER_BVH',json.dumps(r),flush=True)
