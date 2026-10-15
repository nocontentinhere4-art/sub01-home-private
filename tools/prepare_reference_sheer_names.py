"""Names-only unique short identities for native cloth/material/texture assets."""
import copy,hashlib,json,struct
from pathlib import Path
SOURCE_SHA='32de9fcc3c6ddd548fed66f8cd0e48971268f3252beb7b9968200f26ecf88414'
NAMES={'SUB01ReferenceSheer_Left':'SCLeft','SUB01ReferenceSheer_Right':'SCRight','SUB01ReferenceSheer_Hardware':'SCHardware'}

def prepare(source,target):
 from home_asset_audit import read_gltf
 source,target=Path(source),Path(target)
 if hashlib.sha256(source.read_bytes()).hexdigest()!=SOURCE_SHA:raise RuntimeError('Exact actually simulated cloth source required')
 doc,blob=read_gltf(source);before=copy.deepcopy(doc)
 if {n.get('name')for n in doc['nodes']}!=set(NAMES):raise RuntimeError('Exact three original cloth/hardware nodes required')
 for node in doc['nodes']:node['name']=NAMES[node['name']];doc['meshes'][node['mesh']]['name']=node['name']
 for i,material in enumerate(doc['materials']):material['name']='SCM'+str(i).zfill(2)
 for i,image in enumerate(doc.get('images',[])):image['name']='SCT'+str(i).zfill(2)
 encoded=json.dumps(doc,separators=(',',':')).encode();encoded+=b' '*(-len(encoded)%4);data=bytes(blob);data+=b'\0'*(-len(data)%4)
 if target.exists():raise RuntimeError('New prepared short-name source path required')
 target.write_bytes(struct.pack('<III',0x46546c67,2,28+len(encoded)+len(data))+struct.pack('<II',len(encoded),0x4e4f534a)+encoded+struct.pack('<II',len(data),0x004e4942)+data)
 after,actual_blob=read_gltf(target);restored=copy.deepcopy(after)
 for group in('nodes','meshes','materials','images'):
  for i,row in enumerate(before.get(group,[])):
   if'name'in row:restored[group][i]['name']=row['name']
   else:restored[group][i].pop('name',None)
 if restored!=before or bytes(actual_blob)!=bytes(blob):raise RuntimeError('Names-only cloth preparation changed geometry/PBR/image bytes')
 return {'schema':'sub01.reference-sheer-short-native-names.v1','source_sha256':SOURCE_SHA,'prepared_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'geometry_PBR_image_binary_unchanged':True,'node_names':[n['name']for n in after['nodes']],'material_names':[n['name']for n in after['materials']],'image_names':[n['name']for n in after.get('images',[])]}
