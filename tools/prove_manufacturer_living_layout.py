"""Exact actual manufacturer POSITION bounds and conservative private living routes."""
import sys,json,hashlib
from pathlib import Path
from home_asset_audit import read_gltf
from structural_rail_source_patch import world_matrices,accessor,transformed
from prove_reference_living_layout import prove

def bounds(path,expected):
 path=Path(path);assert hashlib.sha256(path.read_bytes()).hexdigest()==expected;doc,blob=read_gltf(path);wm=world_matrices(doc);points=[]
 for i,n in enumerate(doc['nodes']):
  if'mesh'not in n:continue
  for p in doc['meshes'][n['mesh']]['primitives']:
   for v in accessor(doc,blob,p['attributes']['POSITION']):
    q=transformed(wm[i],v);points.append([100*q[0],100*q[2],100*q[1]])
 low=[min(p[i]for p in points)for i in range(3)];high=[max(p[i]for p in points)for i in range(3)];return {'path':str(path),'sha256':expected,'actualPositionAccessorVertices':len(points),'minimumCm':low,'maximumCm':high}
def main():
 source,out=map(Path,sys.argv[1:]);request=json.loads(source.read_text());assert set(request['sources'])=={'sofa','coffeeTable','console'};evidence={role:bounds(row['path'],row['sha256'])for role,row in request['sources'].items()};f={role:[r['minimumCm'][0],r['maximumCm'][0],r['minimumCm'][1],r['maximumCm'][1]]for role,r in evidence.items()};channel=(f['coffeeTable'][1]+f['sofa'][0])/2
 c={'capsuleRadiusCm':16,'capsuleHalfHeightCm':91,'requiredSurfaceMarginCm':3,'tvFunctionalPlane':{'x':-374.7,'y':[-88,78],'z':[117.5,212.5]},'furniture':f,'stairs':[-21,81,-171,256],'maximumFurnitureHeightCm':{role:r['maximumCm'][2]for role,r in evidence.items()},'proposedSeatedEyeCm':[-145,-5,115],'wallTVOpeningYZ':[-93,83,113,217],'actualTVCaseYZ':[-92,82,114,216],'nicheBackFrontXcm':-385,'minimumTVCaseOpeningMarginCm':1,'proposedLocalRoutes':[{'name':'south approach to seating','points':[[-60,-220],[-60,-180],[channel,-180],[channel,-5]]},{'name':'seating to north stair-side route','points':[[channel,-5],[channel,185],[-60,185],[-60,330]]}]}
 r=prove(c);r.update(schema='sub01.actual-manufacturer-living-local-layout.v1',frozenSourceVertexEvidence=evidence,sourceConfiguration=c,sourceLayoutClearancePassed=True,nativeImportPermitted=False,actualNativeCollisionStateVerified=False,sourcePhysicalDimensionsNotRescaled=True,manufacturerArchiveNotClaimedCurrentSKUExact=True,requiresRetiredRugStillHiddenNoCollision=True,fullHouseOrDoorSweepAccepted=False);out.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'gaps':r['gaps'],'sourceEvidence':evidence,'TVSightline':{k:v for k,v in r['TVSightline'].items()if k!='cornerRayVerticalClearances'}}))
if __name__=='__main__':main()
