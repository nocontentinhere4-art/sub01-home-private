"""Material frequency only, exact R2 source binary/152 geometry and eight hinges.
Three material carriers are genuine existing source parts, never invented planes.
"""
from pathlib import Path
import json,struct,hashlib,copy,math
SOURCE=Path('/workspace/sub01-home-private/reference-kitchen-finish-r2/output/kitchen-finish-152.glb')
EXPECTED='d2fca368e7bff558736f912c904749ea4f3e6ece23748c54895083c6d9fbb4b3'
OUT=Path('/workspace/sub01-home-private/reference-kitchen-grain-r3/output');OUT.mkdir(parents=True,exist_ok=True)
def read(p):
 b=p.read_bytes();assert b[:4]==b'glTF';n=struct.unpack_from('<I',b,12)[0];d=json.loads(b[20:20+n]);a=20+n;length,kind=struct.unpack_from('<II',b,a);assert kind==0x004e4942;return d,b[a+8:a+8+length]
def write(p,d,b):
 j=json.dumps(d,separators=(',',':')).encode();j+=b' '*(-len(j)%4);assert len(b)%4==0;p.write_bytes(struct.pack('<IIIII',0x46546c67,2,28+len(j)+len(b),len(j),0x4e4f534a)+j+struct.pack('<II',len(b),0x004e4942)+b)
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert h(SOURCE)==EXPECTED;original,binary=read(SOURCE);d=copy.deepcopy(original);oak=d['materials'][0];assert oak['name']=='KFOak00'
texture_infos=[]
for key in ['baseColorTexture','metallicRoughnessTexture']:
 if key in oak.get('pbrMetallicRoughness',{}):texture_infos.append((key,oak['pbrMetallicRoughness'][key]))
for key in ['normalTexture','occlusionTexture','emissiveTexture']:
 if key in oak:texture_infos.append((key,oak[key]))
assert {'baseColorTexture','metallicRoughnessTexture','normalTexture'}.issubset({k for k,_ in texture_infos})
for key,info in texture_infos:
 assert not info.get('extensions',{}).get('KHR_texture_transform');info.setdefault('extensions',{})['KHR_texture_transform']={'scale':[3,3]}
d.setdefault('extensionsUsed',[])
if 'KHR_texture_transform'not in d['extensionsUsed']:d['extensionsUsed'].append('KHR_texture_transform')
variant=OUT/'kitchen-grain-152.glb';write(variant,d,binary);check,bb=read(variant);restored=copy.deepcopy(check);restored['materials']=copy.deepcopy(original['materials']);
if 'extensionsUsed'in original:restored['extensionsUsed']=original['extensionsUsed']
else:restored.pop('extensionsUsed',None)
assert restored==original and bb==binary
I=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]
def mul(a,b):return[sum(a[k*4+r]*b[c*4+k]for k in range(4))for c in range(4)for r in range(4)]
def local(n):
 if 'matrix'in n:return n['matrix']
 x,y,z,w=n.get('rotation',[0,0,0,1]);sx,sy,sz=n.get('scale',[1,1,1]);tx,ty,tz=n.get('translation',[0,0,0]);return[(1-2*y*y-2*z*z)*sx,(2*x*y+2*z*w)*sx,(2*x*z-2*y*w)*sx,0,(2*x*y-2*z*w)*sy,(1-2*x*x-2*z*z)*sy,(2*y*z+2*x*w)*sy,0,(2*x*z+2*y*w)*sz,(2*y*z-2*x*w)*sz,(1-2*x*x-2*y*y)*sz,0,tx,ty,tz,1]
parents={c:i for i,n in enumerate(d['nodes'])for c in n.get('children',[])};cache={}
def world(i):
 if i not in cache:cache[i]=mul(world(parents[i]),local(d['nodes'][i]))if i in parents else local(d['nodes'][i])
 return cache[i]
chosen=[]
for m in range(3):
 matches=[(i,n)for i,n in enumerate(d['nodes'])if 'mesh'in n and len(d['meshes'][n['mesh']]['primitives'])==1 and d['meshes'][n['mesh']]['primitives'][0].get('material')==m];assert matches
 i,n=matches[0];chosen.append((i,n))
carrier=copy.deepcopy(d);carrier['nodes']=[{'name':'KG3'+str(j),'mesh':j,'matrix':world(i)}for j,(i,n)in enumerate(chosen)];carrier['meshes']=[copy.deepcopy(d['meshes'][n['mesh']])for i,n in chosen];
for j,m in enumerate(carrier['meshes']):m['name']='KG3'+str(j)
for j,m in enumerate(carrier['materials']):m['name']='KG3Mat'+str(j)
carrier['scenes']=[{'nodes':[0,1,2]}];carrier['scene']=0
for k in ['animations','skins']:assert k not in carrier
carrier_path=OUT/'kitchen-grain-real-source-carrier.glb';write(carrier_path,carrier,binary)
# Measure actual UV metres/repeat from the unchanged source door surfaces.
def access(i):
 a=original['accessors'][i];v=original['bufferViews'][a['bufferView']];width={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']];fmt={5121:'B',5123:'H',5125:'I',5126:'f'}[a['componentType']];size=struct.calcsize('<'+fmt);start=v.get('byteOffset',0)+a.get('byteOffset',0);stride=v.get('byteStride',width*size);values=[]
 for j in range(a['count']):
  row=list(struct.unpack_from('<'+fmt*width,binary,start+j*stride))
  if a.get('normalized'):row=[x/(255 if size==1 else 65535)for x in row]
  values.append(row)
 return values
def length(a):return math.sqrt(sum(x*x for x in a))
periods=[];front_periods=[]
for ni,n in enumerate(original['nodes']):
 if 'mesh'not in n:continue
 for p in original['meshes'][n['mesh']]['primitives']:
  if p.get('material')!=0:continue
  xyz=access(p['attributes']['POSITION']);uv=access(p['attributes']['TEXCOORD_0']);ids=[r[0]for r in access(p['indices'])]if 'indices'in p else list(range(len(xyz)));wm=world(ni)
  for at in range(0,len(ids),3):
   i,j,k=ids[at:at+3];a=[xyz[j][c]-xyz[i][c]for c in range(3)];b=[xyz[k][c]-xyz[i][c]for c in range(3)];du,dv=uv[j][0]-uv[i][0],uv[j][1]-uv[i][1];eu,ev=uv[k][0]-uv[i][0],uv[k][1]-uv[i][1];det=du*ev-dv*eu
   if abs(det)<1e-12:continue
   pu=[(a[c]*ev-b[c]*dv)/det for c in range(3)];pv=[(b[c]*du-a[c]*eu)/det for c in range(3)];pu=[sum(wm[q*4+r]*pu[q]for q in range(3))for r in range(3)];pv=[sum(wm[q*4+r]*pv[q]for q in range(3))for r in range(3)];periods.append([length(pu),length(pv)]);wa=[sum(wm[q*4+r]*a[q]for q in range(3))for r in range(3)];wb=[sum(wm[q*4+r]*b[q]for q in range(3))for r in range(3)];cross=[wa[1]*wb[2]-wa[2]*wb[1],wa[2]*wb[0]-wa[0]*wb[2],wa[0]*wb[1]-wa[1]*wb[0]];area=length(cross)/2
   if area>1e-6 and abs(cross[2])/(2*area)>.98:front_periods.append([length(pu),length(pv),area])
assert periods,'Actual oak cabinetwork UV metric unavailable'
import statistics
def area_median(axis):
 rows=sorted(front_periods,key=lambda p:p[axis]);half=sum(p[2]for p in rows)/2;total=0
 for row in rows:
  total+=row[2]
  if total>=half:return row[axis]
assert front_periods
physical_period={'front_facing_planar_area_m2':sum(p[2]for p in front_periods),'front_area_weighted_original_metres_per_repeat':[area_median(i)for i in(0,1)],'front_area_weighted_new_metres_per_repeat':[area_median(i)/3 for i in(0,1)],'all_face_unweighted_derivative_caveat':'Curved bevel UV derivatives are high and not a claim of uniform physical texel density','oak_cabinetwork_triangle_samples':len(periods),'original_median_metres_per_uv_repeat':[statistics.median(p[i]for p in periods)for i in(0,1)],'new_median_metres_per_uv_repeat':[statistics.median(p[i]for p in periods)/3 for i in(0,1)],'original_minmax_metres_per_uv_repeat':[[min(p[i]for p in periods),max(p[i]for p in periods)]for i in(0,1)],'method':'Unchanged actual oak cabinetwork triangle world-space dP/dUV, KHR uniform3x frequency; no new UV unwrap'}
proof={'schema':'sub01.kitchen-grain-source-r3.v1','source_sha256':EXPECTED,'variant_sha256':h(variant),'carrier_sha256':h(carrier_path),'source_binary_exact':True,'source_nodes_meshes_uv_hinges_exact':True,'texture_uv_frequency_multiplier':[3,3],'physical_texel_period_ratio':1/3,'physical_uv_metric':physical_period,'changed_texture_slots':[k for k,_ in texture_infos],'all_oak_factors_and_non_oak_materials_exact':True,'carrier_existing_source_parts':[{'source_node':i,'carrier_label':'KG3'+str(j),'source_name':n['name'],'source_mesh':n['mesh'],'material':j,'flattened_world_matrix':world(i)}for j,(i,n)in enumerate(chosen)],'source_materials':d['materials'],'native_imported':False,'native_material_frequency_verified':False,'actual_visual_accepted':False}
(OUT/'source-proof.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof),flush=True)
