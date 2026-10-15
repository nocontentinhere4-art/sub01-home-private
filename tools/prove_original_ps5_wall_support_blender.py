"""Whole original PS5 external unit/root fit; actual existing shelf support and source BVH."""
import sys,json,hashlib,math
from pathlib import Path
sys.path.insert(0,'/home/unreal/runtime-tools')
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from home_asset_audit import read_gltf
from structural_rail_source_patch import accessor,world_matrices,transformed
R=Path('/workspace/sub01-home-private/ps5-datsketch-original-r1');proof=json.loads((R/'review/independent-body-base-unit-audit.json').read_text());scale=proof['externalUniformMetersPerSourceUnit'];body=proof['bodyBoundsM'];allb=proof['completeBoundsM'];rootBlender=[-3.755+allb[1][0],1.197+(body[0][1]+body[1][1])/2,0];assert hashlib.sha256((R/'scene.gltf').read_bytes()).hexdigest()==proof['sourceGltfSha256'];assert hashlib.sha256((R/'scene.bin').read_bytes()).hexdigest()==proof['sourceBinSha256']
WC=Path('/workspace/sub01-home-private/reference-wall-console-r1/output/wall-console.glb');WALL=Path('/workspace/sub01-home-private/reference-living-tv-wall-r4/output/living-tv-wall.glb');HOME=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb')
def load(path,unit=1,translation=(0,0,0),deltaUE=(0,0,0),yaw180=False):
 d,b=read_gltf(path);b=(path.parent/d['buffers'][0]['uri']).read_bytes()if b is None else b;wm=world_matrices(d);out=[]
 for i,n in enumerate(d['nodes']):
  if'mesh'not in n:continue
  pts=[];faces=[]
  for pr in d['meshes'][n['mesh']]['primitives']:
   offset=len(pts)
   for v in accessor(d,b,pr['attributes']['POSITION']):
    q=transformed(wm[i],v);bl=[(-1 if yaw180 else 1)*unit*q[0]+translation[0],(1 if yaw180 else -1)*unit*q[2]+translation[1],unit*q[1]+translation[2]];pts.append(Vector((100*bl[0]+deltaUE[0],-100*bl[1]+deltaUE[1],100*bl[2]+deltaUE[2])))
   ix=[a[0]for a in accessor(d,b,pr['indices'])];faces.extend(tuple(offset+j for j in ix[k:k+3])for k in range(0,len(ix),3))
  out.append({'name':n.get('name',''),'node':i,'mesh':n['mesh'],'points':pts,'faces':faces,'path':str(path),'bounds':[[min(p[k]for p in pts)for k in range(3)],[max(p[k]for p in pts)for k in range(3)]]})
 return out
def tree(r):
 if'tree'not in r:r['tree']=BVHTree.FromPolygons(r['points'],r['faces'],all_triangles=True,epsilon=0)
 return r['tree']
def broad(a,b):return all(a['bounds'][0][k]<=b['bounds'][1][k]and b['bounds'][0][k]<=a['bounds'][1][k]for k in range(3))
SUPPORT=R/'support-r1/ps5-whole-base-support.glb';assert hashlib.sha256(SUPPORT.read_bytes()).hexdigest()=='4d489429c66d60520fc47d3d7eb042389317ac6a9d72182a0903d54b3185b8a4';wc=load(WC,deltaUE=(.5,-16,0));mount=load(SUPPORT)[0];display=next(x for x in wc if x['name']=='WCPart05');flat=[]
for face in mount['faces']:
 p=[mount['points'][i]for i in face];normal=(p[1]-p[0]).cross(p[2]-p[0])
 if normal.length and normal.normalized().z>.999999 and min(q.z for q in p)>125 and max(q.z for q in p)<126:flat.append(p)
assert flat,'No actual existing main load-bearing tray top found';top=max(p.z for tri in flat for p in tri);rootBlender[2]=top/100-allb[0][2]
source=load(R/'scene.gltf',unit=scale,translation=rootBlender,yaw180=True);assert len(source)==24 and sum(len(x['faces'])for x in source)==37707;stand=next(x for x in source if x['mesh']==8);home=load(HOME);wall=load(WALL);window=load(Path('/workspace/sub01-home-private/out/real-home-windows-r2/real-home-windows.glb'));doors=load(Path('/workspace/sub01-home-private/authentic-bath-doors-fit-r6/output/door-assemblies.glb'));protected=home+wall+window+doors+[mount,display];assert len(window)==207 and len(doors)==76
contacts=[];unresolved=[];checks=[]
for a in source:
 for b in protected:
  if not broad(a,b):continue
  pairs=tree(a).overlap(tree(b));row={'newPS5Mesh':a['mesh'],'newPS5Name':a['name'],'protectedSource':b['path'],'protectedName':b['name'],'protectedNode':b['node'],'intersectionPairs':len(pairs)};checks.append(row)
  if not pairs:continue
  if b is mount and all(min(a['points'][i].z for i in a['faces'][x])>=max(b['points'][j].z for j in b['faces'][y])for x,y in pairs):contacts.append({**row,'classification':'Exact separated vertical halfspaces; complete original base seated on actual tray top'});continue
  unresolved.append(row)
assert not unresolved,unresolved
lowest=min(p.z for p in stand['points']);bottom=[p for p in stand['points']if p.z<=lowest+.0001];support=[]
for p in bottom:
 hit,n,f,distance=tree(mount).ray_cast(Vector((p.x,p.y,p.z+1)),Vector((0,0,-1)),2);assert hit is not None and abs(hit.z-top)<.0001,'Original stand foot leaves actual load-bearing tray';support.append({'pointUEcm':list(p),'actualTrayHitUEcm':list(hit),'verticalGapCm':p.z-hit.z})
assert bottom;assert min(x['verticalGapCm']for x in support)>=0,'Original base penetrates actual shelf'
pts=[p for a in source for p in a['points']];bounds=[[min(p[k]for p in pts)for k in range(3)],[max(p[k]for p in pts)for k in range(3)]];assert bounds[0][1]>=-140 and bounds[1][1]<=-94.2
projections=[]
for name,e in [('actual_native_photo067',[-230,-210,160]),('south_approach',[-65,-220,165]),('seated',[-145,-5,115]),('north_approach',[-65,185,165])]:
 v=[]
 for p in pts:
  assert p.x<e[0];alpha=(-374.7-e[0])/(p.x-e[0]);v.append([e[1]+alpha*(p.y-e[1]),e[2]+alpha*(p.z-e[2])])
 q=[[min(x[k]for x in v)for k in range(2)],[max(x[k]for x in v)for k in range(2)]];gap=-88-q[1][0];assert gap>0,(name,gap);projections.append({'eyeRole':name,'eyeUEcm':e,'projectedAtUnchangedTVPlaneYZcm':q,'screenSeparationCm':gap})
r={'schema':'sub01.original-whole-ps5-wall-support.v1','supportSourcePath':str(SUPPORT),'supportSourceSha256':hashlib.sha256(SUPPORT.read_bytes()).hexdigest(),'supportLipRevisionOnly':'Two own manufactured retention lips4mm above tray; all other hardware/artistmodel retained','sourceGltfSha256':proof['sourceGltfSha256'],'sourceBinSha256':proof['sourceBinSha256'],'allOriginal24Meshes13Materials37707TrianglesRetained':True,'uniformUnitScaleMPerOriginalUnit':scale,'newExternalRootYawBlenderDegrees':180,'newExternalRootYawUEDegrees':180,'newExternalRootTranslationBlenderM':rootBlender,'externalOriginalGLTFRootMatrixColumnMajor':[-scale,0,0,0,0,scale,0,0,0,0,-scale,0,rootBlender[0],rootBlender[2],-rootBlender[1],1], 'frontOrientation':'Original front−BlenderY turned180deg to face actual approach camera; wholebody/base unchanged','externalNativeRootTranslationUEcm':[100*rootBlender[0],-100*rootBlender[1],100*rootBlender[2]],'mountDockAndDisplayDeltaFromOriginal6768UEcm':[.5,-16,0],'additionalMountDockDisplayDeltaFromCurrentCandidateUEcm':[0,4,0],'bodyCentreYUEcm':-119.7,'actualShelfTopUEcm':top,'wholePS5BoundsUEcm':bounds,'solidPierYcm':[-140,-94.2],'pierMinimumSideMarginCm':min(bounds[0][1]+140,-94.2-bounds[1][1]),'sourceColliderScope':'All HOME955 original geometry,9R4wallboards,207newwindows,76doors,only retained steelmount+controllerdisplay. Four obsolete consoleplasticgroups intentionally replaced whole, not cut fromoriginalartistasset.','sourceBroadphaseChecks':checks,'exactTrayContacts':contacts,'unresolvedSourceIntersections':unresolved,'actualOriginalStandFootSupport':support,'projections':projections,'sourceOriginalFilesUnchanged':True,'sourceArtistBodyNotExactSonyCAD':True,'modelCutReshapedOrRetextured':False,'TVFunctionalPlaneUnchanged':{'x':-374.7,'y':[-88,78],'z':[117.5,212.5]},'nativeChanged':False,'nativeInputChanged':False,'sourceFitPassed':True,'nativeVisualAndSupportAccepted':False};(R/'review/independent-whole-wall-support.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items()if k not in['actualOriginalStandFootSupport','sourceBroadphaseChecks']}),flush=True)
