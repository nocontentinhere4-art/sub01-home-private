"""Read actual exported R3 geometry/PBR and source shells, never hand acceptance."""
import bpy,bmesh,sys,json,hashlib,math,struct
from pathlib import Path
sys.path.insert(0,'/home/unreal/runtime-tools')
from home_asset_audit import read_gltf
from structural_rail_source_patch import accessor,world_matrices,transformed
ROOT=Path('/workspace/sub01-home-private/reference-controller-r11/output');report=json.loads((ROOT/'source-report.json').read_text())
assert report['old_contact_proofs_invalidated']and report['new_grip_recheck_required']and report['hand_contact_accepted']is False
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'controller-r11.blend'))
source=[]
for name in('Deep dark central bridge and lower body','Curved white manufactured grip covers'):
 o=bpy.data.objects.get(name);assert o and o.type=='MESH';bm=bmesh.new();bm.from_mesh(o.data);source.append({'object':name,'vertices':len(bm.verts),'faces':len(bm.faces),'boundary_edges':sum(e.is_boundary for e in bm.edges),'nonmanifold_edges':sum(not e.is_manifold for e in bm.edges)});bm.free()
def inspect(path):
 d,b=read_gltf(path);m=world_matrices(d);nodes=[(i,n)for i,n in enumerate(d['nodes'])if'mesh'in n];assert len(nodes)==1;points=[];triangles=0
 for i,node in nodes:
  ps=d['meshes'][node['mesh']]['primitives'];assert len(ps)==6
  for pr in ps:
   assert {'POSITION','NORMAL','TEXCOORD_0'}<=set(pr['attributes']);p=[transformed(m[i],v)for v in accessor(d,b,pr['attributes']['POSITION'])];assert all(math.isfinite(x)for v in p for x in v);points+=p;ix=accessor(d,b,pr['indices']);assert len(ix)%3==0 and all(0<=int(v[0])<len(p)for v in ix);triangles+=len(ix)//3
 assert len(d['materials'])==6 and {m['name']for m in d['materials']}=={f'C3M{i:02}'for i in range(6)}
 for material in d['materials']:assert material.get('alphaMode','OPAQUE')=='OPAQUE'and'KHR_materials_unlit'not in material.get('extensions',{})
 sizes=[]
 for image in d['images']:
  v=d['bufferViews'][image['bufferView']];raw=b[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']];assert raw[:8]==b'\x89PNG\r\n\x1a\n';size=struct.unpack_from('>II',raw,16);assert max(size)<=256;sizes.append(list(size))
 return {'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'width_m':max(p[0]for p in points)-min(p[0]for p in points),'triangles':triangles,'material_primitives':6,'texture_dimensions':sizes}
held=inspect(ROOT/'controller-r11-held.glb');display=inspect(ROOT/'controller-r11-display.glb');result={'schema':'sub01.reference-controller-r11-exported-proof.v1','held':held,'display':display,'source_shell_topology':source,'actual_original_width_m':.15380217134952545,'old_contact_proofs_invalidated':True,'new_grip_recheck_required':True,'hand_contact_accepted':False,'native_imported':False,'activity_ready':False,'source_visual_accepted':False,'ok':abs(held['width_m']-.15380217134952545)<1e-7 and abs(display['width_m']-.16)<1e-7 and held['triangles']==display['triangles']and source[0]['nonmanifold_edges']==0}
(ROOT/'exported-source-proof.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
