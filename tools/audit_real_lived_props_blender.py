"""Independent complete source triangle intersections and measured support for genuine lived props."""
import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,'/home/unreal/runtime-tools')
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from home_asset_audit import read_gltf
from structural_rail_source_patch import accessor,world_matrices,transformed
R=Path('/workspace/sub01-home-private/real-lived-props-r1/output')
def load(path):
 d,b=read_gltf(path);w=world_matrices(d);out=[]
 for i,n in enumerate(d['nodes']):
  if'mesh'not in n:continue
  p=[];f=[]
  for pr in d['meshes'][n['mesh']]['primitives']:
   off=len(p)
   for v in accessor(d,b,pr['attributes']['POSITION']):
    q=transformed(w[i],v);p.append(Vector((q[0]*100,q[2]*100,q[1]*100)))
   ix=[v[0]for v in accessor(d,b,pr['indices'])];f.extend(tuple(off+k for k in ix[j:j+3])for j in range(0,len(ix),3))
  out.append({'name':n.get('name',''),'node':i,'points':p,'faces':f,'bounds':[[min(v[k]for v in p)for k in range(3)],[max(v[k]for v in p)for k in range(3)]]})
 return out
def tree(a):
 if'tree'not in a:a['tree']=BVHTree.FromPolygons(a['points'],a['faces'],all_triangles=True,epsilon=0)
 return a['tree']
def broad(a,b):return all(a['bounds'][0][k]<=b['bounds'][1][k]and b['bounds'][0][k]<=a['bounds'][1][k]for k in range(3))
home=load(Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb'));k=load(R/'genuine-kitchen-lived-props.glb');plant=load(R/'genuine-around-plant.glb');around=load(Path('/workspace/sub01-home-private/manufacturer-around-large-r1/placed-dark-satin-r4/muuto-around-large-dark-satin.glb'));rows=[]
for a in k:
 for b in home:
  if broad(a,b):
   pairs=tree(a).overlap(tree(b))
   if pairs:rows.append({'new':a['name'],'oldNode':b['node'],'oldName':b['name'],'pairs':len(pairs)})
for a in plant:
 for b in around:
  if broad(a,b):
   pairs=tree(a).overlap(tree(b))
   if pairs:rows.append({'new':a['name'],'oldName':'Around:'+b['name'],'pairs':len(pairs)})
for i,a in enumerate(k):
 for b in k[i+1:]:
  if broad(a,b):
   pairs=tree(a).overlap(tree(b))
   if pairs:rows.append({'new':a['name'],'otherNew':b['name'],'pairs':len(pairs)})
supportAdjustments=[]
for a,under in [(x,around)for x in plant if x['name']=='LivePlant_003']+[(x,[v for v in k if v['name']=='LiveBoard_000'])for x in k if x['name']=='LiveApple_000']:
 low=min(v.z for v in a['points']);samples=[]
 for v in a['points']:
  if v.z>low+.5:continue
  for b in under:
   hit,n,fi,dist=tree(b).ray_cast(Vector((v.x,v.y,max(v.z,low)+10)),Vector((0,0,-1)),20)
   if hit is not None:samples.append(hit.z-v.z)
 supportAdjustments.append({'new':a['name'],'sampleCount':len(samples),'requiredVerticalLiftCm':max(samples)+.001 if samples else None,'maxSupportMinusActualSkinCm':max(samples)if samples else None})
worktop=next(a for a in home if a['node']==65);worktopFeet=[]
for a in k:
 if a['name']not in ['LiveBoard_000','LiveBowl_000']:continue
 low=min(v.z for v in a['points']);sample=[]
 for v in a['points']:
  if v.z>low+.001:continue
  hit,n,fi,dist=tree(worktop).ray_cast(v+Vector((0,0,1)),Vector((0,0,-1)),2)
  assert hit is not None and hit.z>92.2,(a['name'],v,hit)
  sample.append(v.z-hit.z)
 assert sample and min(sample)>=0
 worktopFeet.append({'new':a['name'],'lowestFootVerticesTested':len(sample),'minimumMeasuredGapCm':min(sample),'maximumMeasuredGapCm':max(sample)})
r={'actualCountertopFootSupport':worktopFeet,'supportAdjustments' :supportAdjustments,'schema' :'sub01.independent-real-lived-props-source.v1','sourceSHA':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in[R/'genuine-kitchen-lived-props.glb',R/'genuine-around-plant.glb']},'bounds':[{'name':a['name'],'bounds':a['bounds']}for a in k+plant],'triangleIntersectionFindings':rows,'nativeChanged':False,'accepted':not rows};(R/'independent-contacts.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
