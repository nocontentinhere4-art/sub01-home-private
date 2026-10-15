"""Read frozen genuine source vertices; conservative local furniture clearance only."""
from pathlib import Path
import hashlib,json,sys
from home_asset_audit import read_gltf
from structural_rail_source_patch import world_matrices,accessor,transformed
from prove_reference_living_layout import prove
SOURCES={
 'sofa':('/workspace/sub01-home-private/reference-gaming-lounge-r1/haven-output-r2/genuine-navy-haven-with-pillows.glb','b69d4cbcf53ad4603bcc852a3dc158b1424d2969bbf688d7ce4b39ae108e24f3'),
 'coffeeTable':('/workspace/sub01-home-private/reference-gaming-lounge-r1/table-output/genuine-coffee-table.glb','c05a5d343ff55dd9e486f62626374e4879cab24e456fa14b8da58605ff88abb9'),
 'console':('/workspace/sub01-home-private/reference-living-tv-wall-r3/output/living-cabinet.glb','63e025252dfaa4d0db66800d5b1b36de54d46b61af2bff64e878a39287985979')}
def main():
 c=json.loads(Path(sys.argv[1]).read_text());evidence={}
 for role,(path,sha)in SOURCES.items():
  p=Path(path);assert hashlib.sha256(p.read_bytes()).hexdigest()==sha;d,b=read_gltf(p);m=world_matrices(d);points=[]
  for i,n in enumerate(d['nodes']):
   if 'mesh'not in n:continue
   for pr in d['meshes'][n['mesh']]['primitives']:
    for q in accessor(d,b,pr['attributes']['POSITION']):
     v=transformed(m[i],q);points.append([100*v[0],100*v[2],100*v[1]])
  low=[min(v[a]for v in points)for a in range(3)];high=[max(v[a]for v in points)for a in range(3)]
  c['furniture'][role]=[low[0],high[0],low[1],high[1]];c['maximumFurnitureHeightCm'][role]=high[2]
  evidence[role]={'path':path,'sha256':sha,'actualPositionAccessorVertices':len(points),'minimumCm':low,'maximumCm':high}
 r=prove(c);r['schema']='sub01.actual-frozen-living-footprints.v1';r['frozenSourceVertexEvidence']=evidence;r['sourceConfiguration']=c;r['actualSourceGeometryOnly']=True
 Path(sys.argv[2]).write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'gaps':r['gaps'],'sources':evidence}))
if __name__=='__main__':main()
