"""Whole original plant external fit versus actual retained kitchen and genuine props."""
exec(compile(open('/home/unreal/runtime-tools/audit_real_lived_props_blender.py').read().split('home=load(',1)[0],'geometry-only','exec'))
R=Path('/workspace/sub01-home-private/real-kitchen-syngonium-r1/indoor-output-r2');P=R/'genuine-kitchen-syngonium.glb';HOME=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb');PROPS=Path('/workspace/sub01-home-private/real-lived-props-r1/output/genuine-kitchen-lived-props.glb');new=load(P);old=load(HOME);props=load(PROPS);retire=[216,217,218,219];findings=[]
for a in new:
 for b in [b for b in old if b['node']not in retire]+props:
  if broad(a,b):
   pairs=tree(a).overlap(tree(b))
   if pairs:findings.append({'new':a['name'],'protected':b['name'],'node':b['node'],'pairs':len(pairs)})
pot=next(a for a in new if a['name']=='SKIndoorPot')
for a in new:
 if a is pot:continue
 if broad(a,pot):
  pairs=tree(a).overlap(tree(pot))
  if pairs:findings.append({'new':a['name'],'protected':'genuineWhitePot','pairs':len(pairs)})
worktop=next(a for a in old if a['node']==65);lowest=min(v.z for a in new for v in a['points']);feet=[v for a in new for v in a['points']if v.z<=lowest+.001];hits=[]
for v in feet:
 hit,n,face,dist=tree(worktop).ray_cast(v+Vector((0,0,1)),Vector((0,0,-1)),2);assert hit is not None and hit.z>92.2
 hits.append(v.z-hit.z)
assert feet and min(hits)>=0
pd,pb=read_gltf(P);materials=pd['materials'];leaf=[m for m in materials if m.get('alphaMode')=='MASK'];assert len(leaf)==1 and leaf[0]['doubleSided']is True and leaf[0].get('alphaCutoff',.5)==.5
r={'schema':'sub01.genuine-kitchen-syngonium-independent-fit.v1','source_sha256':hashlib.sha256(P.read_bytes()).hexdigest(),'protectedHome_sha256':hashlib.sha256(HOME.read_bytes()).hexdigest(),'protectedProps_sha256':hashlib.sha256(PROPS.read_bytes()).hexdigest(),'onlyRetiredOriginalNodes':retire,'newPartBoundsUEcm':[{'name':a['name'],'bounds':a['bounds']}for a in new],'fullSourceTriangleIntersections':findings,'lowestPotSkinVerticesSupported':len(feet),'actualLowestFootGapsCm':{'minimum':min(hits),'maximum':max(hits)},'leafMaterialActualDoubleSidedMasked':True,'actualMaskCutoff':.5,'nativeChanged':False,'sourceFitPassed':not findings};(R/'independent-fit.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True);assert not findings,findings
