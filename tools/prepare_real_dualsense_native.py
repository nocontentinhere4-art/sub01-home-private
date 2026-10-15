"""Pack licensed source bytes unchanged; uniform160mm units, preserve original PBR."""
from pathlib import Path
import json,hashlib,struct,copy,sys
sys.path.insert(0,'/home/unreal/runtime-tools')
from structural_rail_source_patch import world_matrices,accessor,transformed
from home_asset_audit import matmul
ROOT=Path('/workspace/sub01-home-private/real-dualsense-chizuko-r1');SOURCE=ROOT/'source';OUT=ROOT/'native-source-r1';OUT.mkdir(exist_ok=True)
p=SOURCE/'dualsense.gltf';assert hashlib.sha256(p.read_bytes()).hexdigest()=='efb6114ec711cd3a697a8ce11c401e18b47449c026e82005ffde6047ef7a1df6';original=json.loads(p.read_text());d=copy.deepcopy(original);assert len(d['buffers'])==1;raw=(SOURCE/d['buffers'][0]['uri']).read_bytes();binary=bytearray(raw);world=world_matrices(original);nodes=[(i,n)for i,n in enumerate(original['nodes'])if'mesh'in n];assert len(nodes)==2
points=[]
for i,n in nodes:
 for prim in original['meshes'][n['mesh']]['primitives']:points.extend(transformed(world[i],v)for v in accessor(original,raw,prim['attributes']['POSITION']))
lo=[min(p[k]for p in points)for k in range(3)];hi=[max(p[k]for p in points)for k in range(3)];scale=.16/(hi[0]-lo[0]);normalization=[[scale,0,0,-(lo[0]+hi[0])*scale/2],[0,scale,0,-lo[1]*scale],[0,0,scale,-(lo[2]+hi[2])*scale/2],[0,0,0,1]]
d['nodes']=[]
for index,(i,n)in enumerate(nodes):
 m=matmul(normalization,world[i]);d['nodes'].append({'name':f'RDS{index:02}','mesh':n['mesh'],'matrix':[m[r][c]for c in range(4)for r in range(4)]});d['meshes'][n['mesh']]['name']=f'RDS{index:02}'
d['scenes']=[{'name':'Licensed original DualSense physical units only','nodes':[0,1]}];d['scene']=0
images=[]
for i,img in enumerate(d['images']):
 image=(SOURCE/img['uri']).read_bytes();binary.extend(b'\0'*(-len(binary)%4));offset=len(binary);binary.extend(image);view=len(d['bufferViews']);d['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':len(image)});img.pop('uri');img.update(bufferView=view,mimeType='image/png',name=f'RDST{i:02}');images.append({'sha256':hashlib.sha256(image).hexdigest(),'bytes':len(image)})
d['buffers']=[{'byteLength':len(binary)}];assert bytes(binary[:len(raw)])==raw and d['materials']==original['materials']
j=json.dumps(d,separators=(',',':')).encode();j+=b' '*(-len(j)%4);binary.extend(b'\0'*(-len(binary)%4));out=OUT/'real-dualsense-160mm.glb';out.write_bytes(struct.pack('<III',0x46546c67,2,28+len(j)+len(binary))+struct.pack('<II',len(j),0x4e4f534a)+j+struct.pack('<II',len(binary),0x004e4942)+binary)
report={'schema':'sub01.licensed-dualsense-exact-source-packed.v1','source_gltf_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'source_bin_sha256':hashlib.sha256(raw).hexdigest(),'packed_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'source_binary_prefix_exact':True,'materials_exact':True,'original_image_bytes_exact':images,'source_attribution':original['asset']['extras'],'uniform_unit_scale_only':scale,'canonical_width_m':.16,'canonical_dimensions_m':[(hi[k]-lo[k])*scale for k in range(3)],'source_node_indices':[i for i,n in nodes],'nodes':2,'triangles':sum(d['accessors'][pr['indices']]['count']//3 for m in d['meshes']for pr in m['primitives']),'source_geometry_modified':False,'native_imported':False,'hand_contact_accepted':False};(OUT/'packet.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
