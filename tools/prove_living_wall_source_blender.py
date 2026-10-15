"""Independent exact GLB triangle checks for manufactured living wall/cabinet.
Read-only Runpod Blender; no imports or native state changes.
"""
import sys,json,hashlib,math
from pathlib import Path
sys.path.insert(0,'/home/unreal/runtime-tools')
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from home_asset_audit import read_gltf
from structural_rail_source_patch import accessor,world_matrices,transformed
root=Path(sys.argv[sys.argv.index('--')+1]);output=Path(sys.argv[sys.argv.index('--')+2]);HOME=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb');PS5=Path('/workspace/sub01-home-private/reference-wall-console-r1/output/wall-console.glb')
def rows(path,indices=None):
 d,b=read_gltf(path);m=world_matrices(d);out=[]
 for ni,n in enumerate(d['nodes']):
  if 'mesh'not in n or(indices is not None and ni not in indices):continue
  pts=[];faces=[]
  for pr in d['meshes'][n['mesh']]['primitives']:
   pv=[Vector((v[0],-v[2],v[1]))for v in [transformed(m[ni],v)for v in accessor(d,b,pr['attributes']['POSITION'])]];ix=[v[0]for v in accessor(d,b,pr['indices'])];off=len(pts);pts+=pv;faces.extend(tuple(off+j for j in ix[k:k+3])for k in range(0,len(ix),3))
  out.append({'index':ni,'name':n.get('name',''),'points':pts,'faces':faces,'bounds':[[min(v[k]for v in pts)for k in range(3)],[max(v[k]for v in pts)for k in range(3)]],'tree':BVHTree.FromPolygons(pts,faces,all_triangles=True,epsilon=0)})
 return out
prior=Path('/workspace/sub01-home-private/reference-living-tv-wall-r1/output/living-tv-wall.glb');parity=None
if root.parent.name!='reference-living-tv-wall-r1':
 def triangle_keys(rs):
  result=[]
  for r in rs:
   for f in r['faces']:
    t=[tuple(r['points'][i])for i in f];result.append(min(tuple(t[k:]+t[:k])for k in range(3)))
  return sorted(result)
 assert triangle_keys(rows(prior))==triangle_keys(rows(root/'living-tv-wall.glb')),'UV revision changed actual triangle coordinates'
 parity={'priorSha256':hashlib.sha256(prior.read_bytes()).hexdigest(),'actualOrientedTriangleCoordinatesExact':True}
wall=rows(root/'living-tv-wall.glb');cabinet=rows(root/'living-cabinet.glb');protected=rows(HOME,{0,61,130,131})+rows(PS5);assert len(wall)==9;assert len([r for r in protected if r['index']in[130,131]])==2
for r in protected:
 if r['index']==130 and 'WCPart'not in r['name']:assert abs(r['bounds'][0][0]+3.8425)<1e-5,'Actual original TV source node mismatch'
def overlaps(a,b):return all(a['bounds'][0][k]<=b['bounds'][1][k]and b['bounds'][0][k]<=a['bounds'][1][k]for k in range(3))
closed=[]
for r in wall:
 edges={};zero=0
 for f in r['faces']:
  a,b,c=[r['points'][i]for i in f]
  if (b-a).cross(c-a).length_squared==0:zero+=1;continue
  pts=[tuple(r['points'][i])for i in f]
  for k in range(3):
   edge=tuple(sorted([pts[k],pts[(k+1)%3]]));edges[edge]=edges.get(edge,0)+1
 bad=sum(v!=2 for v in edges.values());closed.append({'part':r['name'],'positiveTriangles':len(r['faces'])-zero,'zeroAreaTriangles':zero,'exactPositionWeldNonTwoManifoldEdges':bad});assert bad==0 and zero==0,'Manufactured wall board not closed at exact positional weld'
walltree=BVHTree.FromPolygons([v for r in wall for v in r['points']],[(sum(len(x['points'])for x in wall[:ri])+i,sum(len(x['points'])for x in wall[:ri])+j,sum(len(x['points'])for x in wall[:ri])+k)for ri,r in enumerate(wall)for i,j,k in r['faces']],all_triangles=True,epsilon=0)
clearance=[]
for r in protected:
 if r['index']not in[130,131]:continue
 ds=[walltree.find_nearest(v)[3]for v in r['points']];clearance.append({'originalTVNode':r['index'],'minimumActualVertexToWallDistanceM':min(ds),'maximumActualVertexToWallDistanceM':max(ds),'surfaceIntersectionPairs':sum(len(a['tree'].overlap(r['tree']))for a in wall)})
checks=[];contacts=[];unresolved=[]
for a in wall+cabinet:
 for b in protected+(cabinet if a in wall else[]):
  if not overlaps(a,b):continue
  pairs=a['tree'].overlap(b['tree']);row={'new':a['name'],'protected':b['name'],'protectedNode':b['index'],'pairs':len(pairs),'examples':pairs[:5]};checks.append(row)
  if not pairs:continue
  # Exact rear attachment only: every backplate point is on/in front of new wall plane.
  if b['name']=='WCPart04':
   front=-3.7699999809265137;face=[a['points'][i]for i in a['faces'][pairs[0][0]]]
   if max(v.x for v in a['points'])<=min(v.x for v in b['points']):contacts.append({**row,'kind':'exact separating X halfspaces; boundary-only manufactured wall attachment','maximumWallX_m':max(v.x for v in a['points']),'minimumPlateX_m':min(v.x for v in b['points'])});continue
  unresolved.append(row)
floor=next(r for r in protected if r['index']==0 and not r['name'].startswith('WCPart'));support=[]
# Measure actual source cabinet vertices against actual authored floor, not assumed flat Z.
for r in cabinet:
 zmin=r['bounds'][0][2]
 if zmin>.03:continue
 bottom=[v for v in r['points']if v.z==zmin];gaps=[]
 for v in bottom:
  hit,normal,index,distance=floor['tree'].ray_cast(Vector((v.x,v.y,v.z+.1)),Vector((0,0,-1)),.3)
  assert hit is not None,'Actual cabinet foot has no source floor below';gaps.append(v.z-hit.z)
 remaining=set(range(len(bottom)));groups=[]
 while remaining:
  seed=remaining.pop();group={seed};todo=[seed]
  while todo:
   i=todo.pop();near={j for j in remaining if math.hypot(bottom[i].x-bottom[j].x,bottom[i].y-bottom[j].y)<.04};remaining-=near;group|=near;todo+=list(near)
  groups.append({'vertices':len(group),'centroidXY_m':[sum(bottom[i][k]for i in group)/len(group)for k in[0,1]],'floorGapRangeM':[min(gaps[i]for i in group),max(gaps[i]for i in group)]})
 assert len(groups)==4,('Actual lowest source feet are not four separate supports',groups)
 support.append({'part':r['name'],'bottomVertices':len(bottom),'actualBottomZ_m':zmin,'actualFloorGapRangeM':[min(gaps),max(gaps)],'independentFourFootGroups':groups})
assert support,'No actual foot geometry measured'
rugretirement=None;retired_source_pairs=[]
extra=sys.argv[sys.argv.index('--')+3:]
if extra:
 from verify_living_rug_readback import verify
 readback=Path(extra[0]);original=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/private-audit/rejected-generated-decor-hidden.json');rugretirement=verify(readback.read_bytes(),original.read_bytes());mapfile=Path(rugretirement['candidateProject'])/'Content/Sub01Home/ActualHome.umap';assert hashlib.sha256(mapfile.read_bytes()).hexdigest()==rugretirement['candidateMapSha256'],'Native candidate map changed after retirement readback'
 retired_source_pairs=[r for r in unresolved if r['protectedNode']==61 and r['protected']=='house-static-8'];unresolved=[r for r in unresolved if r not in retired_source_pairs]
allcab=[v for r in cabinet for v in r['points']];cbounds=[[min(v[k]for v in allcab)for k in range(3)],[max(v[k]for v in allcab)for k in range(3)]];cspan=[cbounds[1][k]-cbounds[0][k]for k in range(3)];footprint={'bounds_m':cbounds,'spans_m':cspan,'expectedGenuineWidthM':1.83,'widthAtMost183p001Cm':cspan[1]<=1.83001,'depthAtMost48p3Cm':cspan[0]<=.483,'allActualOutlyingGeometryIncluded':True}

report={'schema':'sub01.independent-living-wall-source-bvh.v1','wallSha256':hashlib.sha256((root/'living-tv-wall.glb').read_bytes()).hexdigest(),'cabinetSha256':hashlib.sha256((root/'living-cabinet.glb').read_bytes()).hexdigest(),'protectedHomeSha256':hashlib.sha256(HOME.read_bytes()).hexdigest(),'protectedPS5Sha256':hashlib.sha256(PS5.read_bytes()).hexdigest(),'protectedBounds':[{'name':r['name'],'sourceNode':r['index'],'bounds':r['bounds']}for r in protected],'newBounds':[{'name':r['name'],'bounds':r['bounds']}for r in wall+cabinet],'protectedScope':'Exact original TV130/131, source floor0, rug61, retained mounted console/controller6768, new cabinet-vs-wall','coordinateFrame':'metres Blender X,-gltfZ,gltfY; UEcm=(100X,-100Y,100Z)','wallClosedSurfaceProof':closed,'actualRetainedTVClearance':clearance,'R1ToR2GeometryParity':parity,'epsilonM':0,'wallParts':len(wall),'cabinetParts':len(cabinet),'checks':checks,'exactMountContacts':contacts,'unresolved':unresolved,'actualFloorSupport':support,'actualCabinetFootprint':footprint,'actualRugRetirementProof':rugretirement,'excludedOnlyPreciselyRetiredSourcePairs':retired_source_pairs,'sourceGeometryAccepted':footprint['widthAtMost183p001Cm']and footprint['depthAtMost48p3Cm']and not unresolved and all(r['actualFloorGapRangeM'][0]>=0 for r in support),'originalRugNativeVisibilityCollisionBindingPending':rugretirement is None,'sourceRugCollisionIsNotYetConfirmedNativeCollision':True,'fullHouseFurniturePending':True,'nativeChanged':False}
report['native_import_permitted']=bool(report['sourceGeometryAccepted']and rugretirement is not None);report['wall_sha256']=report['wallSha256'];report['cabinet_sha256']=report['cabinetSha256'];report['rug_retirement_receipt_sha256']=rugretirement['retirementReceiptSha256']if rugretirement else None
output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
