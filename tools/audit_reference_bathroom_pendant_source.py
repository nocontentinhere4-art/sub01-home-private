"""Server Blender surface-collision audit of the frozen real pendant candidate.

Tests original955 full source and authentic WC. Native owned assets/solid
containment remain separate acceptance requirements. No world or asset changes.
"""
from pathlib import Path
import sys,json,math,hashlib,argparse
sys.path.insert(0,str(Path(__file__).resolve().parent))
from home_asset_audit import read_gltf
from structural_rail_source_patch import world_matrices
from prepare_real_wc_bundle import node_geometry
from mathutils.bvhtree import BVHTree
from mathutils import Vector
parser=argparse.ArgumentParser();parser.add_argument('--folder',type=Path,required=True);parser.add_argument('--home',type=Path,required=True);parser.add_argument('--wc',type=Path,required=True)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]);folder=args.folder
p=folder/'bathroom-pendant.glb';d,b=read_gltf(p)
assert hashlib.sha256(p.read_bytes()).hexdigest()=='0ec188ac44e20e72fb936d2623c6c0ea5fd2d1a615170696ff565b1d0e4a5c82'
rows=node_geometry(d,b,0,world_matrices(d));verts=[];faces=[]
for row in rows:
 n=len(verts);verts.extend([tuple(v) for v in row['points']]);faces.extend([tuple(n+i for i in f) for f in row['faces']])
tree=BVHTree.FromPolygons([Vector(v) for v in verts],faces,all_triangles=True,epsilon=0.)
bounds=[[fun(p[k] for p in verts) for k in range(3)] for fun in (min,max)]
checks=[];contacts=[];failures=[]
for label,source in [('original955',args.home),('actual-genuine-WC',args.wc)]:
 expected_sha={'original955':'9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b','actual-genuine-WC':'ec3df0b92b0734f2705318e7c1c57a58164ef08926c0bde1240af4e4137067c3'}[label]
 assert hashlib.sha256(source.read_bytes()).hexdigest()==expected_sha
 doc,blob=read_gltf(source);matrices=world_matrices(doc)
 for node,n in enumerate(doc['nodes']):
  if 'mesh' not in n:continue
  for pi,row in enumerate(node_geometry(doc,blob,node,matrices)):
   points=[tuple(v) for v in row['points']]
   lo=[min(v[k] for v in points) for k in range(3)];hi=[max(v[k] for v in points) for k in range(3)]
   if any(hi[k]<bounds[0][k]-1e-6 or lo[k]>bounds[1][k]+1e-6 for k in range(3)):continue
   tris=[tuple(int(i) for i in f) for f in row['faces']]
   other=BVHTree.FromPolygons([Vector(v) for v in points],tris,all_triangles=True,epsilon=0.)
   pairs=tree.overlap(other);checks.append({'source':label,'node':node,'primitive':pi,'tested_triangles':len(tris),'surface_overlap_pairs':len(pairs)})
   for a,c in pairs:
    own=[verts[i] for i in faces[a]];external=[points[i] for i in tris[c]]
    canopy=(label=='original955' and node==158 and all(abs(v[1]-5.949999809265137)<2e-6 for v in external) and all(v[1]<=5.949999809265137+2e-6 for v in own) and any(abs(v[1]-5.949999809265137)<2e-6 for v in own))
    row={'source':label,'node':node,'primitive':pi,'fixture_triangle':a,'source_triangle':c}
    (contacts if canopy else failures).append(row)
report={'schema':'sub01.bathroom-pendant-source-surface-collision.v1','fixture_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'fixture_full_triangles':len(faces),'fixture_world_bounds_gltf_m':bounds,'source_meshes_tested_after_aabb_filter':checks,'actual_roof_canopy_boundary_contacts':contacts,'forbidden_surface_overlaps':failures,'source_surface_collision_pass':not failures,'scope':'Exact original955 full geometry and genuine WC source; remaining native owned assets and containment require independent native verification','native_imported':False,'runtime_ready':False}
(folder/'source-surface-collision-r2.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
