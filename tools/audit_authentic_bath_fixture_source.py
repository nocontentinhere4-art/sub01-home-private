"""Blender CPU-only actual fixture meshes versus actual architectural triangles."""
import argparse,json,sys,hashlib
from pathlib import Path

def audit(root,home):
 import bpy
 sys.path.insert(0,'/home/unreal/runtime-tools')
 from mathutils import Vector
 from mathutils.bvhtree import BVHTree
 from home_asset_audit import read_gltf
 from prepare_real_wc_bundle import node_geometry
 from structural_rail_source_patch import world_matrices
 root,home=Path(root),Path(home);bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(root/'bath-fixtures.glb'));fixtures=[]
 for o in bpy.data.objects:
  if o.type!='MESH':continue
  ps=[o.matrix_world@v.co for v in o.data.vertices];o.data.calc_loop_triangles();faces=[tuple(t.vertices)for t in o.data.loop_triangles];fixtures.append((o.name,ps,faces,BVHTree.FromPolygons(ps,faces,all_triangles=True,epsilon=0)))
 corridor=Path('/workspace/sub01-home-private/bathroom-corridor-source-r1/bath-corridor.glb')
 if hashlib.sha256(corridor.read_bytes()).hexdigest()!='5ffac2406e668a327427e60bc75e3ee3ecf13a89381d0312b821277386cb9c91':raise ValueError('Exact target corridor geometry required')
 hd,hb=read_gltf(corridor);hm=world_matrices(hd);architecture=[]
 for ni in (117,158):
  found=[i for i,n in enumerate(hd['nodes'])if n.get('name')=='SUB01_BathCorridor_SourceNode_'+str(ni)]
  if len(found)!=1:raise ValueError('Exact target source node required')
  ps=[];fs=[]
  for row in node_geometry(hd,hb,found[0],hm):
   offset=len(ps);ps.extend(Vector((v[0],-v[2],v[1]))for v in row['points']);fs.extend(tuple(i+offset for i in f)for f in row['faces'])
  architecture.append((str(ni),ps,fs,BVHTree.FromPolygons(ps,fs,all_triangles=True,epsilon=0)))
 pairs=[]
 for name,ps,fs,bvh in fixtures:
  for target,op,of,other in architecture:
   hits=bvh.overlap(other)
   if hits:
    crossings=[];contact=[]
    for fi,oi in hits:
     a,b,c=(op[k]for k in of[oi]);normal=(b-a).cross(c-a)
     if normal.length<1e-14:raise ValueError('Degenerate protected triangle')
     normal.normalize();dist=[normal.dot(ps[k]-a)for k in fs[fi]];penetration=min(max(dist),-min(dist))
     (crossings if penetration>1e-5 else contact).append({'fixture_triangle':fi,'protected_triangle':oi,'signed_plane_distances_m':dist,'crossing_depth_m':max(0,penetration)})
    pairs.append({'fixture':name,'protected_node':int(target),'surface_triangle_pairs':len(hits),'crossing_pairs_over_0_001cm':len(crossings),'contact_pairs_within_0_001cm':len(contact),'max_crossing_depth_cm':max([v['crossing_depth_m']*100 for v in crossings]or[0]),'crossing_samples':crossings[:6]})
 result={'schema':'sub01.authentic-bath-actual-source-bvh.v1','fixture_sha256':hashlib.sha256((root/'bath-fixtures.glb').read_bytes()).hexdigest(),'fixture_meshes':len(fixtures),'target_corridor_sha256':hashlib.sha256(corridor.read_bytes()).hexdigest(),'protected_nodes':[117,158],'actual_source_triangle_intersections':pairs,'triangle_pair_count':sum(r['surface_triangle_pairs']for r in pairs),'unresolved_positive_crossings':sum(r['crossing_pairs_over_0_001cm']for r in pairs),'surface_contact_epsilon_cm':.001,'native_or_walk_verified':False}
 (root/'actual-architecture-bvh.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--home',required=True);a=p.parse_args(sys.argv[sys.argv.index('--')+1:]if'--'in sys.argv else None);audit(a.root,a.home)
