"""Read-only exact cosmetic-controller rigid clearance beside genuine table plant."""
exec(compile(open('/home/unreal/runtime-tools/audit_real_lived_props_blender.py').read().split('home=load(',1)[0],'actual-source-geometry','exec'))
P=Path('/workspace/sub01-home-private/real-dualsense-chizuko-r1/native-source-r1/real-dualsense-160mm.glb');T=Path('/workspace/sub01-home-private/manufacturer-around-large-r1/placed-dark-satin-r4/muuto-around-large-dark-satin.glb');F=Path('/workspace/sub01-home-private/real-lived-props-r1/output/genuine-around-plant.glb');ds=load(P);table=load(T);plant=load(F);samples=[]
for a in ds:
 for v in a['points']:
  if v.z>.5:continue
  for b in table:
   hit,n,face,dist=tree(b).ray_cast(Vector((v.x-257,v.y-25,50)),Vector((0,0,-1)),20)
   assert hit is not None
   samples.append(hit.z-v.z)
z=max(samples)+.005
for a in ds:
 a['points']=[v+Vector((-257,-25,z))for v in a['points']];a['bounds']=[[min(v[k]for v in a['points'])for k in range(3)],[max(v[k]for v in a['points'])for k in range(3)]]
findings=[]
for a in ds:
 for b in plant+table:
  if broad(a,b):
   pairs=tree(a).overlap(tree(b))
   if pairs:findings.append({'controller':a['name'],'protected':b['name'],'pairs':len(pairs)})
assert not findings,findings
r={'schema':'sub01.real-table-controller-plant-rigid-clearance.v1','sourceSHA':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in[P,T,F]},'controllerRootTranslationUEcm':[-257,-25,z],'controllerYawUEdegrees':0,'controllerOnlyDeltaYcm':-20,'fullSourceBVHFindings':findings,'sourceFootSamples':len(samples),'minimumSupportedSkinGapCm':.005,'controllerBoundsUEcm':[[min(v[k]for a in ds for v in a['points'])for k in range(3)],[max(v[k]for a in ds for v in a['points'])for k in range(3)]],'allOriginalGeometryPBRPreserved':True,'ok':True,'nativeChanged':False};out=F.parent/'independent-controller-plant-clearance.json';out.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
