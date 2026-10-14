"""Read actual external desk GLB vertices/materials/textures; never change geometry."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from home_asset_audit import read_gltf,image_size
from structural_rail_source_patch import accessor,world_matrices,transformed


def inventory(path):
    path=Path(path);doc,binary=read_gltf(path)
    if binary is None:
        buffers=doc.get('buffers',[])
        if len(buffers)!=1 or 'uri' not in buffers[0] or buffers[0]['uri'].startswith('data:'):raise ValueError('Require single external binary or GLB buffer')
        binary=(path.parent/buffers[0]['uri']).read_bytes()
    matrices=world_matrices(doc);parts=[];all_points=[]
    for ni,node in enumerate(doc.get('nodes',[])):
        if 'mesh' not in node:continue
        for pi,primitive in enumerate(doc['meshes'][node['mesh']]['primitives']):
            if primitive.get('mode',4)!=4:raise ValueError('Require actual triangle geometry')
            if primitive.get('extensions',{}).get('KHR_draco_mesh_compression'):raise ValueError('Compressed vertices need source decoder')
            points=[transformed(matrices[ni],p) for p in accessor(doc,binary,primitive['attributes']['POSITION'])]
            if not points or not all(math.isfinite(v) for p in points for v in p):raise ValueError('Invalid source positions')
            indices=[x[0] for x in accessor(doc,binary,primitive['indices'])] if 'indices' in primitive else list(range(len(points)))
            if len(indices)%3:raise ValueError('Incomplete triangle stream')
            used=[points[i] for i in indices];all_points.extend(used)
            lo=[min(p[a] for p in used) for a in range(3)];hi=[max(p[a] for p in used) for a in range(3)]
            horizontal=[]
            for j in range(0,len(indices),3):
                triangle=[points[i] for i in indices[j:j+3]]
                if max(p[1] for p in triangle)-min(p[1] for p in triangle)<.0001:
                    area=abs((triangle[1][0]-triangle[0][0])*(triangle[2][2]-triangle[0][2])-(triangle[2][0]-triangle[0][0])*(triangle[1][2]-triangle[0][2]))/2
                    if area>.001:horizontal.append({'y':sum(p[1] for p in triangle)/3,'area_m2':area,'bounds_xz':[[min(p[a] for p in triangle) for a in (0,2)],[max(p[a] for p in triangle) for a in (0,2)]]})
            parts.append({'node':ni,'name':node.get('name'),'mesh':node['mesh'],'primitive':pi,'material':primitive.get('material'),'vertex_count':len(points),'triangle_count':len(indices)//3,'bounds_m':[lo,hi],'attributes':list(primitive['attributes']),'large_horizontal_triangles':horizontal})
    if not all_points:raise ValueError('No actual mesh geometry')
    lo=[min(p[a] for p in all_points) for a in range(3)];hi=[max(p[a] for p in all_points) for a in range(3)]
    images=[]
    for i,img in enumerate(doc.get('images',[])):
        if 'bufferView' in img:
            view=doc['bufferViews'][img['bufferView']];start=view.get('byteOffset',0);data=binary[start:start+view['byteLength']]
        elif 'uri' in img and not img['uri'].startswith('data:'):data=(path.parent/img['uri']).read_bytes()
        else:raise ValueError('Image identity unsupported')
        images.append({'index':i,'name':img.get('name'),'mimeType':img.get('mimeType'),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'dimensions':image_size(data)})
    return {'schema':'sub01.actual-cc0-desk-source-inventory.v1','source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'source_bytes':path.stat().st_size,'bounds_m':[lo,hi],'dimensions_m':[hi[a]-lo[a] for a in range(3)],'parts':parts,'materials':doc.get('materials',[]),'textures':doc.get('textures',[]),'images':images,'geometry_mutated':False,'placement_requires_actual_top_surface_review':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source');parser.add_argument('output');args=parser.parse_args()
    result=inventory(args.source);Path(args.output).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('parts','materials','textures','images')}))
