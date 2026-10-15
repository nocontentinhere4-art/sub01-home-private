"""Compare full actual source corners and semantic PBR after material separation."""
from pathlib import Path
import json,hashlib
from home_asset_audit import read_gltf
from structural_rail_source_patch import world_matrices,accessor,transformed
def corners(p):
 d,b=read_gltf(p);m=world_matrices(d);rows=[]
 for ni,n in enumerate(d['nodes']):
  if 'mesh' not in n:continue
  for prim in d['meshes'][n['mesh']]['primitives']:
   attrs=prim['attributes'];points=[tuple(transformed(m[ni],v)) for v in accessor(d,b,attrs['POSITION'])];uv=[tuple(v) for v in accessor(d,b,attrs['TEXCOORD_0'])];normals=[tuple(v) for v in accessor(d,b,attrs['NORMAL'])];ids=[int(v[0] if isinstance(v,(tuple,list)) else v) for v in accessor(d,b,prim['indices'])]
   material=d['materials'][prim['material']]['name']
   for k in range(0,len(ids),3):
    row=tuple((points[i],uv[i],normals[i]) for i in ids[k:k+3]);row=min(row,row[1:]+row[:1],row[2:]+row[:2]);rows.append((material,row))
 return sorted(rows),{m['name']:m for m in d['materials']},d
def semantic_materials(path):
 import copy
 d,b=read_gltf(path);out=copy.deepcopy(d['materials'])
 def walk(x):
  if isinstance(x,dict):
   for key,value in x.items():
    if key.endswith('Texture') and isinstance(value,dict) and 'index' in value:
     tex=d['textures'][value['index']];im=d['images'][tex['source']];view=d['bufferViews'][im['bufferView']];start=view.get('byteOffset',0);raw=b[start:start+view['byteLength']]
     value['index']={'image_sha256':hashlib.sha256(raw).hexdigest(),'mimeType':im.get('mimeType'),'sampler':d.get('samplers',[])[tex['sampler']] if 'sampler' in tex else None}
    else:walk(value)
  elif isinstance(x,list):
   for value in x:walk(value)
 for material in out:walk(material)
 return {m['name']:m for m in out}
def verify(root):
 root=Path(root)
 one,_,d1=corners(root/'bathroom-pendant.glb');three,_,d3=corners(root/'split-v3/bathroom-pendant.glb')
 sa=semantic_materials(root/'bathroom-pendant.glb');sb=semantic_materials(root/'split-v3/bathroom-pendant.glb')
 if one!=three or len(one)!=5602 or sa!=sb or len(d3['nodes'])!=3:
  raise ValueError('Full geometry/corner UV/normal/PBR-image assignment parity required')
 return {'schema':'sub01.bathroom-pendant-material-split-parity.v1','one_component_sha256':hashlib.sha256((root/'bathroom-pendant.glb').read_bytes()).hexdigest(),'three_component_sha256':hashlib.sha256((root/'split-v3/bathroom-pendant.glb').read_bytes()).hexdigest(),'all5602_world_triangle_corners_uvs_normals_exact':True,'all_material_pbr_definitions_image_bytes_sampler_assignments_exact':True,'native_component_roles':{n['name']:d3['materials'][d3['meshes'][n['mesh']]['primitives'][0]['material']]['name'] for n in d3['nodes']},'source_surface_collision_geometry_same_as_proven_r2':True,'native_imported':False,'runtime_ready':False}

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args();r=verify(a.root)
 (a.root/'split-v3/world-source-parity.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
