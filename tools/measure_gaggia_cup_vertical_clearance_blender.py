"""One bounded actual triangle-projection vertical clearance solve; no source mutation."""
exec(compile(open('/home/unreal/runtime-tools/audit_real_lived_props_blender.py').read().split('home=load(',1)[0],'geometry-only','exec'))
import math,time
R=Path('/workspace/sub01-home-private/real-gaggia-gran-iraida-r1/placed-idle-r3');P=R/'gaggia-gran-idle-placed.glb';parts=load(P);cup=next(a for a in parts if a['name']=='GaggiaIdle_033');grate=next(a for a in parts if a['name']=='GaggiaIdle_025');started=time.monotonic();CELL=.5
cross=lambda a,b:a[0]*b[1]-a[1]*b[0]
def area(t):return cross((t[1].x-t[0].x,t[1].y-t[0].y),(t[2].x-t[0].x,t[2].y-t[0].y))
def box(t):return[min(v.x for v in t),min(v.y for v in t),max(v.x for v in t),max(v.y for v in t)]
def bins(b):
 for x in range(math.floor(b[0]/CELL),math.floor(b[2]/CELL)+1):
  for y in range(math.floor(b[1]/CELL),math.floor(b[3]/CELL)+1):yield(x,y)
def clip(subject,tri):
 sign=1 if area(tri)>0 else-1;out=subject
 for a,b in zip(tri,tri[1:]+tri[:1]):
  prev=out;out=[]
  if not prev:break
  def side(p):return sign*((b.x-a.x)*(p[1]-a.y)-(b.y-a.y)*(p[0]-a.x))
  for p,q in zip(prev,prev[1:]+prev[:1]):
   sp,sq=side(p),side(q);ip,iq=sp>=0,sq>=0
   if ip:out.append(p)
   if ip!=iq:
    f=sp/(sp-sq);out.append((p[0]+f*(q[0]-p[0]),p[1]+f*(q[1]-p[1])))
 return out
def zplane(t,p):
 a,b,c=t;den=area(t);u=((p[0]-a.x)*(c.y-a.y)-(p[1]-a.y)*(c.x-a.x))/den;v=((b.x-a.x)*(p[1]-a.y)-(b.y-a.y)*(p[0]-a.x))/den;return a.z+u*(b.z-a.z)+v*(c.z-a.z)
grid={};gt={};verticalG=0
for i,f in enumerate(grate['faces']):
 t=[grate['points'][j]for j in f]
 if abs(area(t))<=1e-12:verticalG+=1;continue
 gt[i]=t
 for cell in bins(box(t)):grid.setdefault(cell,[]).append(i)
maxZ=max(v.z for v in grate['points']);best=-float('inf');witness=None;pairs=0;overlap=0;verticalC=0
for ci,f in enumerate(cup['faces']):
 assert time.monotonic()-started<52,'Bounded one-pass solve expired'
 ct=[cup['points'][j]for j in f]
 if min(v.z for v in ct)>maxZ:continue
 if abs(area(ct))<=1e-12:verticalC+=1;continue
 candidates={i for cell in bins(box(ct))for i in grid.get(cell,[])}
 for gi in candidates:
  t=gt[gi];polygon=clip([(v.x,v.y)for v in ct],t);pairs+=1
  if not polygon:continue
  overlap+=1
  for p in polygon:
   delta=zplane(t,p)-zplane(ct,p)
   if delta>best:best=delta;witness={'cupFace':ci,'grateFace':gi,'XYcm':list(p),'cupSurfaceZcm':zplane(ct,p),'grateSurfaceZcm':zplane(t,p)}
assert math.isfinite(best);lift=max(0,best)+.001;cupshift=[v+Vector((0,0,lift))for v in cup['points']];remaining=BVHTree.FromPolygons(cupshift,cup['faces'],all_triangles=True,epsilon=0).overlap(tree(grate));r={'schema':'sub01.gaggia-cup-one-pass-actual-triangle-clearance.v1','source_sha256':hashlib.sha256(P.read_bytes()).hexdigest(),'beforeFullBVHIntersectionPairs':312,'projectedCandidateTrianglePairs':pairs,'overlappingProjectionPairs':overlap,'maxActualGrateMinusCupSurfaceCm':best,'minimumRigidCupLiftWith10MicrometreSeparationCm':lift,'extremalActualSurfaceWitness':witness,'exactVerticalProjectedFacesExcludedFromPlaneFit':{'cup':verticalC,'grate':verticalG},'afterWholeCupGrateFullBVHPairs':len(remaining),'runtimeSeconds':time.monotonic()-started,'sourceChanged':False,'staticSupportAfterLiftVerified':False};(R/'cup-exact-vertical-clearance.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
