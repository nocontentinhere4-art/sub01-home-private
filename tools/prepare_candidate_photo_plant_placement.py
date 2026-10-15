"""Blender CPU-only placement proof against the exact saved candidate inventory.

Only a new source GLB is written. Original home, native Editor, input and devices
are untouched. Broad original Nanite surfaces are read from their pinned source,
with exact actual world bounds checked before use; fresh owned surfaces come
from the real Editor's full CPU geometry.
"""
import copy,hashlib,json,struct,sys
from pathlib import Path
from mathutils.bvhtree import BVHTree
sys.path.insert(0,'/home/unreal/runtime-tools')
from home_asset_audit import read_gltf
from unreal_import_real_wc import expected_triangles

BASE=Path('/workspace/sub01-home-private/reference-plants-ph-r1/output-r3')
PROJECT=Path('/workspace/sub01-private-candidate-20261015/Sub01HomeLab')
OUT=Path('/workspace/sub01-home-private/reference-photo-plant-placement-r1/output')
HOME='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
# Actual original four-part plant ownership groups; no shared mesh is modified.
RETIRED=[*range(211,215),*range(221,225),*range(226,230),*range(231,235)]
PLACEMENTS=[(2,[-305.,350.,2.50013],211),(3,[262.,-315.,84.5],221),
            (0,[-345.,-50.,302.5],226),(1,[-334.,462.,302.5],231)]

def bounds(tris):
 points=[p for t in tris for p in t]
 return {'min':[min(p[i]for p in points)for i in range(3)],'max':[max(p[i]for p in points)for i in range(3)]}
def overlaps(a,b):return all(a['min'][i]<=b['max'][i]and b['min'][i]<=a['max'][i]for i in range(3))
def tree(tris):return BVHTree.FromPolygons([tuple(v/100 for v in p)for t in tris for p in t],[list(range(i,i+3))for i in range(0,len(tris)*3,3)],all_triangles=True,epsilon=0)
def height_at(tris,x,y,ceiling):
 heights=[]
 for a,b,c in tris:
  den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
  if abs(den)<1e-14:continue
  s=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/den;t=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/den
  if s>=0 and t>=0 and s+t<=1:
   z=s*a[2]+t*b[2]+(1-s-t)*c[2]
   if z<=ceiling:heights.append(z)
 assert heights,'Measured actual support surface required'
 return max(heights)
def write_glb(path,doc,blob):
 raw=json.dumps(doc,separators=(',',':')).encode();raw+=b' '*((-len(raw))%4);blob+=b'\0'*((-len(blob))%4)
 path.write_bytes(struct.pack('<III',0x46546c67,2,28+len(raw)+len(blob))+struct.pack('<II',len(raw),0x4e4f534a)+raw+struct.pack('<II',len(blob),0x004e4942)+blob)

def run():
 OUT.mkdir(parents=True,exist_ok=True)
 inv_path=PROJECT/'private-audit/plant-placement-inventory.json';inv_bytes=inv_path.read_bytes();inventory=json.loads(inv_bytes)
 assert inventory['read_only']and inventory['world_snapshot_unchanged']
 source=PROJECT/'SourceAssets/full-home.glb';assert hashlib.sha256(source.read_bytes()).hexdigest()==HOME
 home,home_blob=read_gltf(source);manifest=json.loads((BASE/'photo-plants-source.json').read_text());home_cache={};native_cache={};rows=[];prepared=[]
 # Individual files avoid any texture/accessor rewrites. Each exact old group
 # is replaced by one authored variety, with all source leaf/PBR bytes retained.
 for variant,position,old in PLACEMENTS:
  item=manifest['plants'][variant];source=BASE/(item['name']+'.glb');doc,blob=read_gltf(source)
  assert hashlib.sha256(source.read_bytes()).hexdigest()==item['prepared_sha256']
  placed=copy.deepcopy(doc);roots=list(placed['scenes'][placed.get('scene',0)]['nodes']);root_index=len(placed['nodes']);placed['nodes'].append({'name':'PPPlacement%d'%variant,'translation':[position[0]/100,position[2]/100,position[1]/100],'children':roots});placed['scenes'][placed.get('scene',0)]['nodes']=[root_index]
  for mi,mat in enumerate(placed.get('materials',[])):mat['name']='PP%dM%02d'%(variant,mi)
  for ni,n in enumerate(placed['nodes']):
   if 'mesh'in n:n['name']='PP%d_%02d'%(variant,ni);placed['meshes'][n['mesh']]['name']=n['name']
  path=OUT/('placed-photo-plant-%d.glb'%variant);write_glb(path,placed,blob)
  part_tri=[]
  for ni,n in enumerate(placed['nodes']):
   if'mesh'in n:part_tri.extend(expected_triangles(placed,blob,ni))
  pb=bounds(part_tri);plant_tree=tree(part_tri);contacts=[];unresolved=[];tested=[]
  for row in inventory['components']:
   if row['name']in {'full-home_node_'+str(n)for n in RETIRED}:continue
   if not overlaps(pb,row['bounds_cm']):continue
   geometry=row.get('actual_native_triangles_cm');origin='actual_full_native'
   if geometry is None and row['name'].startswith('full-home_node_'):
    index=int(row['name'].rsplit('_',1)[1]);geometry=home_cache.setdefault(index,expected_triangles(home,home_blob,index));gb=bounds(geometry)
    assert max(abs(gb[k][i]-row['bounds_cm'][k][i])for k in ('min','max')for i in range(3))<.0001,('Original source/world bounds changed',row['name'],gb,row['bounds_cm'])
    origin='pinned_original_source_with_actual_world_bounds'
   if geometry is None:
    unresolved.append({'component':row['component'],'reason':'conservative overlap requires exact native surface'});continue
   if not geometry:continue
   key=row['component'];other_tree=native_cache.setdefault(key,tree(geometry));pairs=plant_tree.overlap(other_tree);tested.append({'component':key,'surface':origin,'polygon_pairs':len(pairs)})
   if pairs:
    # An exact horizontal support plane is a measured contact, never a
    # blanket floor exclusion. Any other crossed surface remains a failure.
    touched=[geometry[b]for a,b in pairs]
    support=all(max(abs(p[2]-position[2])for p in t)<.0001 for t in touched)and abs(pb['min'][2]-position[2])<.0001
    record={'component':key,'pairs':len(pairs),'support_z_cm':position[2],'touched_surface_z_cm':[min(p[2]for t in touched for p in t),max(p[2]for t in touched for p in t)],'plant_bottom_z_cm':pb['min'][2]}
    (contacts if support else unresolved).append(record)
  support_index={2:0,0:2,1:4}.get(variant)
  if support_index is None:
   support_row=next(r for r in inventory['components']if r['name']=='desk_node_44');support_geometry=support_row['actual_native_triangles_cm'];support_name=support_row['component']
  else:
   support_geometry=expected_triangles(home,home_blob,support_index);support_name='full-home_node_'+str(support_index)
  support_z=height_at(support_geometry,position[0],position[1],position[2]+.001);gap=pb['min'][2]-support_z
  assert -.0001<=gap<=.001,('Actual planter support gap',variant,gap)
  # Canonical native route remains conservative with the actual R16/H91 body.
  route=[(200,310,96),(130,320,96),(30,320,96),(30,255,96),(30,-170,396),(30,-210,396),(-50,-210,396),(-120,-290,396),(-50,-210,396),(30,-210,396),(30,-170,396),(30,255,96),(30,320,96),(130,320,96),(200,310,96),(130,320,96),(130,-75,96),(200,-75,96)]
  route_gaps=[]
  for a,b in zip(route,route[1:]):
   if min(a[2],b[2])-91>pb['max'][2]or max(a[2],b[2])+91<pb['min'][2]:continue
   # Segment AABB is a superset of every route centre, so this lower bound
   # cannot overestimate the true segment-to-plant clearance.
   gap_xy=sum(max(pb['min'][i]-max(a[i],b[i]),min(a[i],b[i])-pb['max'][i],0)**2 for i in range(2))**.5-16
   route_gaps.append(gap_xy)
  assert not route_gaps or min(route_gaps)>0,('Canonical native route obstructed',variant,route_gaps)
  rows.append({'variant':variant,'position_cm':position,'retired_original_nodes':list(range(old,old+4)),'source_sha256':item['prepared_sha256'],'placed_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bounds_cm':pb,'triangles':len(part_tri),'tested_surfaces':tested,'support_contacts':contacts,'support_witness':{'component':support_name,'measured_surface_z_cm':support_z,'base_gap_cm':gap,'maximum_numerical_gap_cm':.001,'physical_contact_accepted':False},'canonical_R16_H91_route_conservative_min_clearance_cm':min(route_gaps)if route_gaps else None,'unresolved':unresolved})
  prepared.append({'path':str(path),**rows[-1]})
 result={'schema':'sub01.actual-candidate-photo-plant-placement.v1','inventory_sha256':hashlib.sha256(inv_bytes).hexdigest(),'candidate_map_sha256':inventory['candidate_map_sha256'],'protected_home_sha256':HOME,'retired_original_nodes':RETIRED,'plants':rows,'epsilon_m':0,'ignored_home_pairs':0,'ok':not any(r['unresolved']for r in rows),'native_changes':False,'visual_acceptance':False}
 (OUT/'placement-proof.json').write_text(json.dumps(result,indent=2)+'\n');print('PLANT_PLACEMENT_PROOF',json.dumps(result),flush=True)
 assert result['ok'],'Source placement still intersects an actual protected surface'

if __name__=='__main__':run()
