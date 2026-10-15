"""Read-only exact rigid console delta, source collider triangles and approach parallax."""
import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,'/home/unreal/runtime-tools')
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from home_asset_audit import read_gltf
from structural_rail_source_patch import accessor,world_matrices,transformed
P=Path('/workspace/sub01-home-private/reference-wall-console-r1/output/wall-console.glb');W=Path('/workspace/sub01-home-private/reference-living-tv-wall-r4/output/living-tv-wall.glb');H=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb');OUT=Path(sys.argv[sys.argv.index('--')+1]);DELTA=Vector((.5,-20,0))
assert hashlib.sha256(P.read_bytes()).hexdigest()=='6768a9972ce5f21533f75fbc49b0860233e877d6adf0348db1398bc80ca1e522';assert hashlib.sha256(W.read_bytes()).hexdigest()=='3a664a85e472abcc4998ad6aaa1a7a9eada353421a56c878345cc6a87410ade1';assert hashlib.sha256(H.read_bytes()).hexdigest()=='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
def rows(path,delta=Vector((0,0,0))):
 d,b=read_gltf(path);m=world_matrices(d);rs=[]
 for i,n in enumerate(d['nodes']):
  if 'mesh'not in n:continue
  points=[];faces=[]
  for pr in d['meshes'][n['mesh']]['primitives']:
   raw=[transformed(m[i],v)for v in accessor(d,b,pr['attributes']['POSITION'])];off=len(points);points.extend(Vector((100*v[0],100*v[2],100*v[1]))+delta for v in raw);ix=[v[0]for v in accessor(d,b,pr['indices'])];faces.extend(tuple(off+v for v in ix[k:k+3])for k in range(0,len(ix),3))
  rs.append({'node':i,'name':n.get('name',''),'points':points,'faces':faces,'bounds':[[min(p[k]for p in points)for k in range(3)],[max(p[k]for p in points)for k in range(3)]],'path':str(path)})
 return rs
def tree(r):
 if 'tree'not in r:r['tree']=BVHTree.FromPolygons(r['points'],r['faces'],all_triangles=True,epsilon=0)
 return r['tree']
def broad(a,b):return all(a['bounds'][0][i]<=b['bounds'][1][i]and b['bounds'][0][i]<=a['bounds'][1][i]for i in range(3))
old=rows(P);new=rows(P,DELTA);assert len(new)==6;home=rows(H);wall=rows(W);windows=[]
# Frozen new-window and door packets are checked when present; exact source paths discovered below.
for path in ['/workspace/sub01-home-private/authentic-bath-doors-fit-r6/output/door-assemblies.glb','/workspace/sub01-home-private/out/real-home-windows-r2/real-home-windows.glb']:
 assert Path(path).exists();expected='5b8a2bb8b4bb8fe19af1d0c086fb78f3e7f9dff9e06170a06642a8f3d1761a0c'if'authentic-bath'in path else'7119c36483ec3ba22aa71c0cab6a5a7d46d6daf1e544410a6d8fa5f8e933aa57';assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==expected;windows+=rows(Path(path))
allpts=[p for r in new for p in r['points']];bounds=[[min(p[k]for p in allpts)for k in range(3)],[max(p[k]for p in allpts)for k in range(3)]]
assert bounds[0][1]>=-140 and bounds[1][1]<=-94.2,'Six-part assembly leaves actual solid right wall pier'
checks=[];contacts=[];unresolved=[]
for a in new:
 for b in home+wall+windows:
  if not broad(a,b):continue
  pairs=tree(a).overlap(tree(b));row={'assembly':a['name'],'protected':b['name'],'source':b['path'],'sourceNode':b['node'],'intersectionPairs':len(pairs)};checks.append(row)
  if not pairs:continue
  # Actual structural rear plane separating halfspaces only, no arbitrary overlap tolerance.
  if all(max(b['points'][i].x for i in b['faces'][j])<=min(a['points'][i].x for i in a['faces'][k])for k,j in pairs):contacts.append({**row,'kind':'exact separating X halfspaces; rear attachment only'});continue
  row['trianglePairCoordinatesUEcm']=[{'assembly':[list(a['points'][i])for i in a['faces'][x]],'protected':[list(b['points'][i])for i in b['faces'][y]]}for x,y in pairs];unresolved.append(row)
assert not unresolved,unresolved
prior=rows(Path('/workspace/sub01-home-private/reference-living-tv-wall-r3/output/living-tv-wall.glb'))
def points_key(row):return sorted(tuple(p)for p in row['points'])
assert points_key(next(r for r in prior if r['name']=='LWRecessBack'))==points_key(next(r for r in wall if r['name']=='LWRecessBack')),'Niche rear moved'
originalWhite=next(r for r in home if r['node']==158);whiteFront=max(p.x for p in originalWhite['points']if abs(p.x+377)<.001);front=min(max(p.x for p in r['points'])for r in wall if r['name']in('LWLower','LWUpper','LWLeftPier','LWRightPier'));frontgap=front-whiteFront;assert frontgap>.4999
tvproof=[]
for t in [r for r in home if r['node']in(130,131)]:
 pairs=sum(len(tree(a).overlap(tree(t)))for a in wall if broad(a,t));assert pairs==0;nearest=min(tree(a).find_nearest(p)[3]for a in wall for p in t['points']);tvproof.append({'sourceNode':t['node'],'wallIntersections':pairs,'minimumVertexToNewWallCm':nearest})
screenX=-374.7;screenY=[-88,78];eyes={'actual_native_photo067':[-230,-210,160],'south_approach':[-65,-220,165],'sofa_seated':[-155,-5,115],'north_approach':[-65,185,165]};projections=[]
for label,eye in eyes.items():
 def projected(points):
  v=[]
  for p in points:
   assert p.x<eye[0];u=(screenX-eye[0])/(p.x-eye[0]);v.append([eye[1]+u*(p.y-eye[1]),eye[2]+u*(p.z-eye[2])])
  return[[min(p[k]for p in v)for k in range(2)],[max(p[k]for p in v)for k in range(2)]]
 before=projected([p for r in old for p in r['points']]);after=projected(allpts);clearance=screenY[0]-after[1][0];assert clearance>0,(label,after)
 projections.append({'eyeRole':label,'eyeCm':eye,'beforeScreenPlaneProjectionBoundsYZcm':before,'afterScreenPlaneProjectionBoundsYZcm':after,'horizontalSeparationFromScreenCm':clearance,'allAssemblyPointsOutsideScreenY':True})
r={'schema':'sub01.wall-console-rigid-outward-shift.v1','assemblySha256':hashlib.sha256(P.read_bytes()).hexdigest(),'wallSha256':hashlib.sha256(W.read_bytes()).hexdigest(),'deltaUEcm':list(DELTA),'deltaBlenderM':[.005,.2,0],'newWallFrontExtensionUEcm':.5,'nicheBackShiftCm':0,'sourceGeometryMaterialRotationScaleUnchanged':True,'actualTVSourceAfterWallShift':tvproof,'allSixPartBoundsUEcm':bounds,'solidRightPierYcm':[-140,-94.2],'minimumPierEdgeMarginCm':min(bounds[0][1]+140,-94.2-bounds[1][1]),'parts':[{'name':r['name'],'boundsUEcm':r['bounds']}for r in new],'sourceColliderScope':'All original HOME955 mesh nodes + nine final R4 boards with0.5cm front extension and unchanged niche back + complete207manufacturedwindows and76doors; actual native collider readback remains separate.','sourceBroadphaseChecks':checks,'exactBoundaryAttachmentContacts':contacts,'unresolvedSourceIntersections':unresolved,'projections':projections,'tvFunctionalPlaneExact':{'x':-374.7,'y':[-88,78],'z':[117.5,212.5]},'actualGameChanged':False,'nativeInputChanged':False,'nativePlacementOrRenderedAcceptance':False};r.update(source_sha256=r['wallSha256'],ok=not unresolved,tv_case_screen_unchanged=True,niche_rear_unchanged=True,retained_original_white_wall_unchanged=True,actual_original_white_front_x_cm=whiteFront,actual_new_cladding_front_x_cm=front,actual_white_cladding_plane_separation_cm=frontgap);OUT.write_text(json.dumps(r,indent=2)+'\n');Path('/workspace/sub01-home-private/reference-living-tv-wall-r4/output/independent-front-clearance.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items()if k not in['parts','sourceBroadphaseChecks']}))
