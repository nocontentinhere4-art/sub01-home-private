"""Blender CPU-only actual source-pose witnesses; native continuous sweep remains separate."""
import json,hashlib,sys,math
from pathlib import Path
sys.path.insert(0,'/home/unreal/runtime-tools')
def audit(root,home):
 import bpy
 from mathutils import Matrix,Vector
 from mathutils.bvhtree import BVHTree
 from home_asset_audit import read_gltf
 from prepare_real_wc_bundle import node_geometry
 from structural_rail_source_patch import world_matrices
 root,home=Path(root),Path(home);bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(root/'door-assemblies.glb'));report=json.loads((root/'source-report.json').read_text());by={o.name:o for o in bpy.data.objects if o.type=='MESH'};architect=[]
 for path,nodes in [(home,[0,1,2,52]),(Path('/workspace/sub01-home-private/bathroom-corridor-source-r1/bath-corridor.glb'),None)]:
  d,b=read_gltf(path);wm=world_matrices(d)
  if nodes is None:nodes=[i for i,n in enumerate(d['nodes'])if n.get('name')in ['SUB01_BathCorridor_SourceNode_117','SUB01_BathCorridor_SourceNode_158']]
  for ni in nodes:
   if'mesh'not in d['nodes'][ni]:continue
   ps=[];fs=[]
   for row in node_geometry(d,b,ni,wm):
    off=len(ps);ps.extend(Vector((v[0],-v[2],v[1]))for v in row['points']);fs.extend(tuple(j+off for j in f)for f in row['faces'])
   architect.append((str(path.name)+':'+str(ni),ps,fs,BVHTree.FromPolygons(ps,fs,all_triangles=True,epsilon=0)))
 witnesses=[];fail=[];total=0
 for role,contract in report['door_roles'].items():
  ps=[];fs=[]
  for name in contract['moving_parts']:
   o=by[name];off=len(ps);ps.extend(o.matrix_world@v.co for v in o.data.vertices);o.data.calc_loop_triangles();fs.extend(tuple(j+off for j in t.vertices)for t in o.data.loop_triangles)
  values=[i*5. for i in range(18)]+[86.4]if role=='entry'else [i*5. for i in range(19)]+([95.]if role=='bathroom'else[91.])
  for value in values:
   if role=='entry':
    pivot=Vector((1.543,-4.022,.025));transform=Matrix.Translation(pivot)@Matrix.Rotation(math.radians(-value),4,'Z')@Matrix.Translation(-pivot)
   else:transform=Matrix.Translation(Vector((0,-value/100,0)if role=='bathroom'else(value/100,0,0)))
   points=[transform@p for p in ps];bvh=BVHTree.FromPolygons(points,fs,all_triangles=True,epsilon=0);crossings=[];contacts=0
   for target,op,of,other in architect:
    hits=bvh.overlap(other)
    for fi,oi in hits:
     a,b,c=(op[k]for k in of[oi]);normal=(b-a).cross(c-a)
     if normal.length<1e-14:raise ValueError('Degenerate protectedsource face')
     normal.normalize();dist=[normal.dot(points[k]-a)for k in fs[fi]];depth=min(max(dist),-min(dist))
     if depth>1e-5:crossings.append({'target':target,'face':fi,'protected_face':oi,'depth_cm':depth*100})
     else:contacts+=1
   witnesses.append({'role':role,'position_degrees_or_cm':value,'positive_crossings':len(crossings),'contacts':contacts});total+=len(crossings)
   if crossings:fail.append({'role':role,'position':value,'samples':crossings[:8]})
 result={'schema':'sub01.authentic-door-source-pose-witnesses.v1','source_sha256':hashlib.sha256((root/'door-assemblies.glb').read_bytes()).hexdigest(),'sampled_positions':witnesses,'unresolved_positive_crossings':total,'failures':fail,'surface_contact_epsilon_cm':.001,'continuous_native_sweep_proved':False,'native_physical_or_visual_verified':False};(root/'door-source-motion-witnesses.json').write_text(json.dumps(result,indent=2)+'\n');print('DOOR_POSE_WITNESSES',len(witnesses),'POSITIVE_CROSSINGS',total,flush=True)
if __name__=='__main__':audit('/workspace/sub01-home-private/authentic-bath-doors-fit-r6/output','/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb')
