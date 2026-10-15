"""Independently match all final GLB triangles to original manufacturer OBJ faces.
No rendering: original4083 positions,4258 triangles+621quads, no added surfaces.
"""
import collections,hashlib,itertools,json,math
from pathlib import Path
from home_asset_audit import read_gltf
from unreal_import_real_wc import expected_triangles

def prove(obj,glb):
 raw=Path(obj).read_bytes();assert hashlib.sha256(raw).hexdigest()=='0d4a22c20014c5b699e60fd1b2452359272bbe4e41e5f9b81d825d802ca8c1ee'
 vertices=[];faces=[]
 for line in raw.decode().splitlines():
  if line.startswith('v '):vertices.append(tuple(map(float,line.split()[1:4])))
  if line.startswith('f '):faces.append([int(t.split('/')[0])-1 for t in line.split()[1:]])
 assert len(vertices)==4083 and len(faces)==4879
 # Separate source millimetre→world centimetre derivation; do not use builder matrices.
 zlo=min(p[2] for p in vertices);zhi=max(p[2] for p in vertices);ylo=min(p[1] for p in vertices)
 depth=(zhi-zlo)/10;cx=-179.5+depth/2;cy=-(zlo+zhi)/20
 source=[(-p[2]/10-cy+cx,p[0]/10+10,(p[1]-ylo)/10+2.505)for p in vertices]
 canonical={};ids=[];points=[]
 for p in source:
  key=tuple(round(v,8)for v in p)
  if key not in canonical:canonical[key]=len(points);points.append(p)
  ids.append(canonical[key])
 bins=collections.defaultdict(list)
 for i,p in enumerate(points):bins[tuple(math.floor(v/.01)for v in p)].append(i)
 maxerror=0
 def match(p):
  nonlocal maxerror
  cell=tuple(math.floor(v/.01)for v in p);best=None
  for delta in itertools.product((-1,0,1),repeat=3):
   for i in bins.get(tuple(cell[j]+delta[j]for j in range(3)),[]):
    d=math.dist(p,points[i])
    if best is None or d<best[0]:best=(d,i)
  assert best and best[0]<.00005,('Vertex differs original source',p,best)
  maxerror=max(maxerror,best[0]);return best[1]
 canonical_faces=[set(ids[i]for i in f)for f in faces];incident=collections.defaultdict(set)
 for i,f in enumerate(canonical_faces):
  for v in f:incident[v].add(i)
 capacity=[len(f)-2 for f in faces];assigned=[0]*len(faces);new_edges=collections.defaultdict(collections.Counter)
 doc,blob=read_gltf(Path(glb));triangles=[t for node in range(len(doc['nodes']))for t in expected_triangles(doc,blob,node)]
 assert len(triangles)==5500
 for tri in triangles:
  vertices3=[match(p)for p in tri];possible=set.intersection(*(incident[v]for v in vertices3))
  available=[i for i in possible if assigned[i]<capacity[i]];assert len(available)==1,('Source face identity ambiguous/missing',available,vertices3)
  i=available[0];assigned[i]+=1
  for a,b in zip(vertices3,vertices3[1:]+vertices3[:1]):new_edges[i][tuple(sorted((a,b)))]+=1
 assert assigned==capacity
 # Every original triangle/quad boundary must remain exact; quad split has
 # exactly one twice-used internal edge, no new corner or changed polygon.
 for i,face in enumerate(faces):
  f=[ids[j]for j in face];boundary=collections.Counter(tuple(sorted((a,b)))for a,b in zip(f,f[1:]+f[:1]));actual=new_edges[i]
  for edge,count in boundary.items():assert actual[edge]==count,(i,edge,count,actual[edge])
  extra={e:c for e,c in actual.items()if e not in boundary}
  assert len(extra)==len(face)-3 and all(c==2 for c in extra.values())
 return {'schema':'sub01.muuto-original-surface-proof.v1','original_obj_sha256':hashlib.sha256(raw).hexdigest(),'candidate_sha256':hashlib.sha256(Path(glb).read_bytes()).hexdigest(),'original_vertices':4083,'original_triangles':4258,'original_quads':621,'all4879originalfaces_complete':True,'all5500finaltriangles_have_exact_source_polygon':True,'max_original_position_error_cm':maxerror,'position_tolerance_cm':.00005,'all_original_polygon_boundaries_preserved':True,'native_or_contact_acceptance':False}
if __name__=='__main__':
 import sys
 result=prove(sys.argv[1],sys.argv[2]);Path(sys.argv[3]).write_text(json.dumps(result,indent=2));print(json.dumps(result))
