"""Independent official CAD base/outlet fit; exact retained sink/worktop source, no native input."""
exec(compile(open('/home/unreal/runtime-tools/audit_real_lived_props_blender.py').read().split('home=load(',1)[0],'geometry-only','exec'))
R=Path('/workspace/sub01-home-private/official-grohe-concetto-r1/output');P=R/'grohe-concetto-placed.glb';assert hashlib.sha256(P.read_bytes()).hexdigest()=='89c7ba8c7d303c9f2e65f9616337a9c3d3dfbcfaea20fbfc7d096457901bebfc';new=load(P);HOME=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb');old=load(HOME);assert len(new)==6 and sum(len(a['faces'])for a in new)==84500;findings=[]
for a in new:
 for b in old:
  if b['node']in[69,70,71]:continue
  if broad(a,b):
   pairs=tree(a).overlap(tree(b))
   if pairs:findings.append({'cadSolid':a['name'],'retained':b['name'],'retainedSourceNode':b['node'],'pairs':len(pairs)})
worktop=next(a for a in old if a['node']==65);sink=next(a for a in old if a['node']==164);low=min(v.z for a in new for v in a['points']);feet=[v for a in new for v in a['points']if v.z<=low+.001];gaps=[]
for p in feet:
 hit,n,face,dist=tree(worktop).ray_cast(p+Vector((0,0,1)),Vector((0,0,-1)),2);assert hit is not None and hit.z>92.2;gaps.append(p.z-hit.z)
assert feet and min(gaps)>=0
outlet=Vector((-270.000005,-357.5,130));hit,n,face,dist=tree(sink).ray_cast(outlet,Vector((0,0,-1)),80);assert hit is not None and hit.z<93.6
r={'schema':'sub01.official-grohe-concetto-independent-counter-fit.v1','source_sha256':hashlib.sha256(P.read_bytes()).hexdigest(),'protected_home_sha256':hashlib.sha256(HOME.read_bytes()).hexdigest(),'onlyRetiredSourceNodes':[69,70,71],'actualCADSolids':6,'completeCADTriangles':84500,'fullSourceIntersections':findings,'baseActualSkinVerticesSupported':len(feet),'baseSkinGapCm':{'min':min(gaps),'max':max(gaps)},'providedOutletCenterXYcm':list(outlet)[:2],'actualSinkBasinDropHitCm':list(hit),'outletDropInsideSinkGeometry':True,'staticHandleAndBodyNoRetainedGeometryIntersection':not findings,'dynamicLeverSweepVerified':False,'nativeChanged':False,'sourceFitPassed':not findings,'ok':not findings,'intersections':findings};(R/'independent-fit.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True);assert not findings,findings
