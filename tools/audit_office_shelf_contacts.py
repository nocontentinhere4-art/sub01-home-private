"""Read actual exported shelf/home triangles for a narrow collision diagnosis."""
import argparse,hashlib,json,sys
from pathlib import Path
from real_linea_lamp_mount import geometry

def run(shelves,home,output):
 from mathutils import Vector
 from mathutils.bvhtree import BVHTree
 if hashlib.sha256(Path(home).read_bytes()).hexdigest()!='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b':raise ValueError('Original source identity differs')
 _,sp=geometry(shelves);_,hp=geometry(home);rows=[]
 def bvh(p,t):return BVHTree.FromPolygons([Vector(v)for v in p],t,all_triangles=True,epsilon=0)
 for h in hp:
  if h['node']!=160:continue
  hv=[(p[0],p[2],p[1])for p in h['points']];hb=bvh(hv,h['triangles'])
  for s in sp:
   sv=[(p[0],p[2],p[1])for p in s['points']]
   for si,hi in bvh(sv,s['triangles']).overlap(hb):
    a=[sv[v]for v in s['triangles'][si]];b=[hv[v]for v in h['triangles'][hi]]
    rows.append({'shelf_node':s['node'],'shelf_triangle':si,'source160_triangle':hi,'shelf_vertices_ue_m':a,'source160_vertices_ue_m':b,'shelf_back_y_m':min(p[1]for p in a),'source160_front_y_m':max(p[1]for p in b),'signed_back_gap_m':min(p[1]for p in a)-max(p[1]for p in b)})
 receipt={'read_only':True,'epsilon':0,'source_sha256':hashlib.sha256(Path(home).read_bytes()).hexdigest(),'shelves_sha256':hashlib.sha256(Path(shelves).read_bytes()).hexdigest(),'actual_pairs':rows}
 Path(output).write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt));return receipt
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--shelves',required=True);p.add_argument('--home',required=True);p.add_argument('--output',required=True);a=p.parse_args(sys.argv[sys.argv.index('--')+1:]if '--'in sys.argv else None);run(a.shelves,a.home,a.output)
