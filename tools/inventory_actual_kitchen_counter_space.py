"""Read-only full152part installed-source footprint/surface inventory, UE cm."""
import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,'/home/unreal/runtime-tools')
from home_asset_audit import read_gltf
from structural_rail_source_patch import world_matrices,accessor,transformed
P=Path('/workspace/sub01-home-private/kitchen-lowerfit-source-20261015/output/native-kitchen.glb');SHA='accd954c120a60f4eb68bd869fe2f1b578517880d71b82e673af5834c32fb79d';assert hashlib.sha256(P.read_bytes()).hexdigest()==SHA;d,b=read_gltf(P);wm=world_matrices(d);rows=[]
for i,n in enumerate(d['nodes']):
 if'mesh'not in n:continue
 pts=[];materials=[];triangles=0;flats=[]
 for pr in d['meshes'][n['mesh']]['primitives']:
  raw=[transformed(wm[i],v)for v in accessor(d,b,pr['attributes']['POSITION'])];pp=[[100*v[0],100*v[2],100*v[1]]for v in raw];pts+=pp;materials.append(d['materials'][pr['material']].get('name',''));ix=[v[0]for v in accessor(d,b,pr['indices'])];triangles+=len(ix)//3
  for k in range(0,len(ix),3):
   q=[pp[ix[k+j]]for j in range(3)];a=[q[1][j]-q[0][j]for j in range(3)];c=[q[2][j]-q[0][j]for j in range(3)];v=[a[1]*c[2]-a[2]*c[1],a[2]*c[0]-a[0]*c[2],a[0]*c[1]-a[1]*c[0]];length=sum(x*x for x in v)**.5
   if length>100 and v[2]/length>.99999:flats.append({'triangle':k//3,'areaCm2':length/2,'zRangeCm':[min(v[2]for v in q),max(v[2]for v in q)],'pointsUEcm':q})
 low=[min(q[k]for q in pts)for k in range(3)];hi=[max(q[k]for q in pts)for k in range(3)];rows.append({'node':i,'name':n.get('name',''),'mesh':n['mesh'],'materials':materials,'boundsUEcm':[low,hi],'triangles':triangles,'topHorizontalLargeFaces':flats})
assert len(rows)==152;out=P.parent/'actual-counter-space-inventory.json';out.write_text(json.dumps({'schema':'sub01.actual152-kitchen-counter-space.v1','sourcePath':str(P),'sourceSha256':SHA,'parts':rows,'nativeChanged':False},indent=2)+'\n')
