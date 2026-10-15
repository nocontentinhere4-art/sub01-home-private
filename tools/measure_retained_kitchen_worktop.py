"""Exact retained top65/sink164/faucet69–71/espresso267–272, no native writes."""
import sys,json,hashlib,math
from pathlib import Path
sys.path.insert(0,'/home/unreal/runtime-tools')
from home_asset_audit import read_gltf
from structural_rail_source_patch import world_matrices,accessor,transformed
P=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb');assert hashlib.sha256(P.read_bytes()).hexdigest()=='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b';d,b=read_gltf(P);wm=world_matrices(d);indices=[65,69,70,71,72,164,*range(216,220),*range(267,273)];rows=[]
for i in indices:
 n=d['nodes'][i];pts=[];faces=[];materials=[]
 for pr in d['meshes'][n['mesh']]['primitives']:
  off=len(pts);p=[transformed(wm[i],v)for v in accessor(d,b,pr['attributes']['POSITION'])];pts.extend([[100*v[0],100*v[2],100*v[1]]for v in p]);ix=[v[0]for v in accessor(d,b,pr['indices'])];faces.extend(tuple(off+j for j in ix[k:k+3])for k in range(0,len(ix),3));materials.append(d['materials'][pr['material']].get('name',''))
 low=[min(p[k]for p in pts)for k in range(3)];high=[max(p[k]for p in pts)for k in range(3)];top=[]
 if i==65:
  for k,f in enumerate(faces):
   q=[pts[j]for j in f];a=[q[1][j]-q[0][j]for j in range(3)];c=[q[2][j]-q[0][j]for j in range(3)];v=[a[1]*c[2]-a[2]*c[1],a[2]*c[0]-a[0]*c[2],a[0]*c[1]-a[1]*c[0]];length=sum(x*x for x in v)**.5
   if length and abs(v[2])/length>.99999 and min(p[2]for p in q)>high[2]-.01:top.append({'triangle':k,'pointsUEcm':q,'areaCm2':length/2})
 rows.append({'originalSourceNode':i,'name':n.get('name',''),'materials':materials,'boundsUEcm':[low,high],'triangles':len(faces),'actualTopFaces':top})
top=rows[0];assert top['originalSourceNode']==65 and top['actualTopFaces'];machine=[x for x in rows if 267<=x['originalSourceNode']<=272];mb=[[min(x['boundsUEcm'][0][k]for x in machine)for k in range(3)],[max(x['boundsUEcm'][1][k]for x in machine)for k in range(3)]];r={'schema':'sub01.retained-real-kitchen-worktop-placement-frame.v1','originalSourcePath':str(P),'originalSourceSha256':hashlib.sha256(P.read_bytes()).hexdigest(),'cabinet152SourceSha256':'accd954c120a60f4eb68bd869fe2f1b578517880d71b82e673af5834c32fb79d','counterNode':65,'retainedSinkNode':164,'retainedFaucetNodes':[69,70,71],'retainedMachineNodes':list(range(267,273)),'actualMachineBoundsUEcm':mb,'parts':rows,'proposedUsableMiddleRectangleXYcm':[-231,-145,-380,-323],'proposedPropAnchorsUEcm':{'cuttingBoard':[-204,-350],'cup':[-157,-337],'foldedClothOrAccessory':[-165,-367]},'actualPropBoundsAndBVHNotYetVerified':True,'allExistingKitchenGeometryAndRuntimeUnchanged':True};out=Path('/workspace/sub01-home-private/kitchen-lowerfit-source-20261015/output/retained-worktop-placement-frame.json');out.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'topBoundsUEcm':top['boundsUEcm'],'topSurfaceFaces':len(top['actualTopFaces']),'topSurfaceAreaCm2':sum(x['areaCm2']for x in top['actualTopFaces']),'actualMachineBoundsUEcm':mb,'retainedParts':[{'node':x['originalSourceNode'],'name':x['name'],'boundsUEcm':x['boundsUEcm']}for x in rows]}))
