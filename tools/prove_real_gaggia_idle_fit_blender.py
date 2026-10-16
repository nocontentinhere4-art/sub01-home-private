"""Independent complete genuine machine/cup source fit; no Game/native operations."""
exec(compile(open('/home/unreal/runtime-tools/audit_real_lived_props_blender.py').read().split('home=load(',1)[0],'source-geometry-only','exec'))
import math,collections
R=Path('/workspace/sub01-home-private/real-gaggia-gran-iraida-r1/placed-idle-r3');P=R/'gaggia-gran-idle-placed.glb';SHA='9ce39013852ae7ce44541f86eaa662cb0c50dbb1e31eb3f7885f703e8db78acd';assert hashlib.sha256(P.read_bytes()).hexdigest()==SHA
report=json.loads((R/'source-report.json').read_text());parts=load(P);assert len(parts)==36 and sum(len(a['faces'])for a in parts)==54529;names=report['names'];cup=next(a for a in parts if names[a['name']]=='polySurface69_Kruzhka_2_0');grate=next(a for a in parts if names[a['name']]=='polySurface44_Metallic_0');HOME=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb');old=load(HOME);counter=next(a for a in old if a['node']==65);currentplant=Path('/workspace/sub01-home-private/real-kitchen-syngonium-r1/indoor-output-r2/genuine-kitchen-syngonium.glb');currentprops=Path('/workspace/sub01-home-private/real-lived-props-r1/output/genuine-kitchen-lived-props.glb');extras=load(currentplant)+load(currentprops);external=[]
for a in parts:
 for b in [x for x in old if x['node']not in range(267,273)]+extras:
  if broad(a,b):
   pairs=tree(a).overlap(tree(b))
   if pairs:external.append({'new':a['name'],'protected':b['name'],'protectedNode':b['node'],'pairs':len(pairs)})
low=min(v.z for a in parts for v in a['points']);feet=[v for a in parts for v in a['points']if v.z<=low+.001];basegaps=[]
for v in feet:
 hit,n,f,d=tree(counter).ray_cast(v+Vector((0,0,1)),Vector((0,0,-1)),2);assert hit is not None and hit.z>92.2;basegaps.append(v.z-hit.z)
basepassed=bool(feet)and min(basegaps)>=0
cupPairs=[]
for b in parts:
 if b is cup:continue
 if broad(cup,b):
  pairs=tree(cup).overlap(tree(b))
  if pairs:cupPairs.append({'otherSource':names[b['name']],'pairs':len(pairs)})
clow=min(v.z for v in cup['points']);probes=[v for v in cup['points']if v.z<=clow+.05];hits=[];miss=0
for v in probes:
 hit,n,f,d=tree(grate).ray_cast(v+Vector((0,0,.01)),Vector((0,0,-1)),.51)
 if hit is None or abs(n.z)<.98:miss+=1;continue
 hits.append({'cupPointUEcm':list(v),'grateHitUEcm':list(hit),'gapCm':v.z-hit.z})
# Actual geometric contact is bounded50micrometres, not every perforation must carry load.
contacts=[x['grateHitUEcm'][:2]for x in hits if 0<=x['gapCm']<=.005]
def hull(points):
 points=sorted(set(tuple(p)for p in points))
 if len(points)<3:return points
 def cross(o,a,b):return(a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
 lo=[];hi=[]
 for p in points:
  while len(lo)>=2 and cross(lo[-2],lo[-1],p)<=0:lo.pop()
  lo.append(p)
 for p in reversed(points):
  while len(hi)>=2 and cross(hi[-2],hi[-1],p)<=0:hi.pop()
  hi.append(p)
 return lo[:-1]+hi[:-1]
contactHull=hull(contacts)
# Weld only identical source positions to audit the real ceramic shell topology.
keys=[tuple(round(float(x),5)for x in v)for v in cup['points']];edges=collections.Counter();origin=sum(cup['points'],Vector())/len(cup['points']);volume=0.;moment=Vector()
for face in cup['faces']:
 a,b,c=[cup['points'][i]-origin for i in face];v=float(a.dot(b.cross(c)))/6.;volume+=v;moment+=(a+b+c)*(v/4.)
 for i,j in zip(face,face[1:]+face[:1]):
  if keys[i]!=keys[j]:edges[tuple(sorted((keys[i],keys[j])))]+=1
boundary=sum(v==1 for v in edges.values());nonmanifold=sum(v>2 for v in edges.values());closed=boundary==0 and nonmanifold==0 and abs(volume)>1e-8;com=origin+moment/volume if abs(volume)>1e-8 else None
margins=[]
if com is not None and len(contactHull)>=3:
 for a,b in zip(contactHull,contactHull[1:]+contactHull[:1]):
  margins.append(((b[0]-a[0])*(com.y-a[1])-(b[1]-a[1])*(com.x-a[0]))/math.hypot(b[0]-a[0],b[1]-a[1]))
supportpassed=closed and bool(margins)and min(margins)>0 and not cupPairs and bool(hits)and min(x['gapCm']for x in hits)>=0
allp=[v for a in parts for v in a['points']];bounds=[[min(v[k]for v in allp)for k in range(3)],[max(v[k]for v in allp)for k in range(3)]]
r={'schema':'sub01.real-gaggia-idle-independent-fit.v1','source_sha256':SHA,'original_source_sha256':report['original_source_sha256'],'parts':36,'triangles':54529,'onlyRetiredOriginalSourceNodes':list(range(267,273)),'officialHeightCalibrationOnlyM':.3,'notManufacturerCAD':True,'actualCompleteBoundsUEcm':bounds,'sourceFrontDirectionUE':'+Y','externalFullSourceIntersections':external,'currentWhitePlantSourceSHA':hashlib.sha256(currentplant.read_bytes()).hexdigest(),'currentKitchenPropsSourceSHA':hashlib.sha256(currentprops.read_bytes()).hexdigest(),'base':{'actualLowestVertices':len(feet),'actualCounterGapCm':{'min':min(basegaps),'max':max(basegaps)},'passed':basepassed},'cup':{'sourceName':names[cup['name']],'sourceColor':'blue per root actual source review; not inferred from meshname','grateSourceName':names[grate['name']],'footRingProbeBandCm':.05,'ringProbes':len(probes),'actualGrateTopHits':len(hits),'perforationMisses':miss,'actualGrateGapCm':{'min':min(x['gapCm']for x in hits),'max':max(x['gapCm']for x in hits)}if hits else None,'sourceContactBandCm':.005,'contactPoints':len(contacts),'contactHullXYcm':contactHull,'cupCompleteSourceIntersectionFindings':cupPairs,'closedCeramicMesh':closed,'weldedBoundaryEdges':boundary,'weldedNonmanifoldEdges':nonmanifold,'signedCeramicVolumeCm3':volume,'uniformCeramicMassCOMcm':list(com)if com is not None else None,'gravityCOMInsideContactHull':bool(margins)and min(margins)>0,'minimumSupportPolygonMarginCm':min(margins)if margins else None,'sourceStaticSupportProven':supportpassed,'dynamicStabilityVerified':False},'passed':not external and basepassed and supportpassed,'nativeChanged':False,'nativeInteractionAccepted':False};(R/'independent-fit.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
