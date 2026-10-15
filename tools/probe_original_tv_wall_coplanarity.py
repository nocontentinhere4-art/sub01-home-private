"""Actual source triangles on veneer front plane; no edits, tolerances are selection only."""
import sys,json,hashlib,math
from pathlib import Path
from home_asset_audit import read_gltf
from structural_rail_source_patch import accessor,world_matrices,transformed
H=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb');W=Path('/workspace/sub01-home-private/reference-living-tv-wall-r3/output/living-tv-wall.glb')
def triangles(path):
 d,b=read_gltf(path);wm=world_matrices(d)
 for i,n in enumerate(d['nodes']):
  if 'mesh'not in n:continue
  for pr in d['meshes'][n['mesh']]['primitives']:
   p=[transformed(wm[i],v)for v in accessor(d,b,pr['attributes']['POSITION'])];ix=[v[0]for v in accessor(d,b,pr['indices'])]
   for k in range(0,len(ix),3):yield {'node':i,'name':n.get('name',''),'material':d['materials'][pr['material']].get('name',''),'triangle':k//3,'points':[[100*v[0],100*v[2],100*v[1]]for v in[p[ix[k]],p[ix[k+1]],p[ix[k+2]]]]}
def area(poly):return abs(sum(poly[i][0]*poly[(i+1)%len(poly)][1]-poly[(i+1)%len(poly)][0]*poly[i][1]for i in range(len(poly)))/2)if len(poly)>2 else 0
def clip(subject,polygon):
 orient=sum(polygon[i][0]*polygon[(i+1)%3][1]-polygon[(i+1)%3][0]*polygon[i][1]for i in range(3));sign=1 if orient>=0 else-1
 for a,b in zip(polygon,polygon[1:]+polygon[:1]):
  incoming=subject;subject=[]
  def side(p):return sign*((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]))
  for p,q in zip(incoming,incoming[1:]+incoming[:1]):
   sp,sq=side(p),side(q)
   if sp>=0:subject.append(p)
   if(sp>=0)!=(sq>=0):u=sp/(sp-sq);subject.append([p[k]+u*(q[k]-p[k])for k in range(2)])
  if not subject:break
 return subject
def selected(t):
 p=t['points'];return max(abs(v[0]+377)for v in p)<.0001 and min(v[1]for v in p)<140 and max(v[1]for v in p)>-140 and min(v[2]for v in p)<285 and max(v[2]for v in p)>.025
original=[t for t in triangles(H)if selected(t)];new=[t for t in triangles(W)if selected(t)];rows=[]
for a in original:
 overlaps=[]
 for b in new:
  intersection=area(clip([p[1:]for p in a['points']],[p[1:]for p in b['points']]))
  if intersection>0:overlaps.append({'newPart':b['name'],'newTriangle':b['triangle'],'overlapCm2':intersection})
 if overlaps:rows.append({**a,'overlapWithCladding':overlaps,'totalTriangleOverlapCm2':sum(x['overlapCm2']for x in overlaps)})
r={'schema':'sub01.actual-original-tv-wall-coplanarity.v1','homeSha256':hashlib.sha256(H.read_bytes()).hexdigest(),'wallSha256':hashlib.sha256(W.read_bytes()).hexdigest(),'planeSelectionCentreXcm':-377,'planeSelectionMaxDistanceCm':.0001,'selectionDistanceIsNotPenetrationWaiver':True,'originalTrianglesOnPlane':len(original),'newCladdingTrianglesOnPlane':len(new),'overlappingOriginalTriangles':rows,'totalOverlapCm2':sum(x['totalTriangleOverlapCm2']for x in rows),'proposedWallAndMountRigidXDeltaCm':.5,'tvScreenAndInputUnchanged':True,'nativeChanged':False};Path(sys.argv[1]).write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items()if k!='overlappingOriginalTriangles'}));print(json.dumps([{'node':x['node'],'name':x['name'],'material':x['material'],'areaCm2':x['totalTriangleOverlapCm2'],'xValues':list(set(p[0]for p in x['points']))}for x in rows]))
