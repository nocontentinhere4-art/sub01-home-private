"""CPU-only exact authored keycap geometry and disconnected surface extraction."""
import pathlib,json,struct,math,hashlib,argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source',type=pathlib.Path,default=pathlib.Path('out/lighting-v23/unreal-home-lab/Sub01HomeLab/SourceAssets/full-home.glb'))
parser.add_argument('--output',type=pathlib.Path,default=pathlib.Path('out/first-person-assets/ReferenceT/keyboard-keycaps-world.json'))
args=parser.parse_args();source=args.source
raw=source.read_bytes();n=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+n]);offset=20+n;binary=raw[offset+8:]
parents={c:i for i,node in enumerate(doc['nodes'])for c in node.get('children',[])}
def mul(a,b):return [sum(a[k*4+r]*b[c*4+k]for k in range(4))for c in range(4)for r in range(4)]
identity=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]
def local(node):
 if 'matrix'in node:return node['matrix']
 assert not node.get('rotation'),'Unexpected quaternion node; explicit conversion required'
 s=node.get('scale',[1,1,1]);p=node.get('translation',[0,0,0]);return[s[0],0,0,0,0,s[1],0,0,0,0,s[2],0,*p,1]
def world(i):return mul(world(parents[i]),local(doc['nodes'][i]))if i in parents else local(doc['nodes'][i])
def accessor(i):
 a=doc['accessors'][i];v=doc['bufferViews'][a['bufferView']];assert not v.get('extensions')and not a.get('sparse')
 fmt,size={5126:('f',4),5123:('H',2),5125:('I',4),5121:('B',1)}[a['componentType']];count={'VEC3':3,'SCALAR':1}[a['type']];stride=v.get('byteStride',size*count);start=v.get('byteOffset',0)+a.get('byteOffset',0)
 return [list(struct.unpack_from('<'+fmt*count,binary,start+j*stride))for j in range(a['count'])]
ni=next(i for i,node in enumerate(doc['nodes'])if node.get('name','').lower()=='mesh_3');m=world(ni);prim=doc['meshes'][doc['nodes'][ni]['mesh']]['primitives'][0]
points=accessor(prim['attributes']['POSITION']);indices=[x[0]for x in accessor(prim['indices'])]
def apply(p):return[sum(m[c*4+r]*p[c]for c in range(3))+m[12+r]for r in range(3)]
source_points=[apply(p)for p in points];ue_points=[[p[0]*100,p[2]*100,p[1]*100]for p in source_points]
# Weld duplicate vertices along face/UV/normal seams; do not bridge spaces between keys.
parent=list(range(len(points)))
def find(a):
 while parent[a]!=a:parent[a]=parent[parent[a]];a=parent[a]
 return a
def union(a,b):parent[find(a)]=find(b)
weld={}
for i,p in enumerate(source_points):
 key=tuple(round(c,7)for c in p)
 if key in weld:union(i,weld[key])
 else:weld[key]=i
for t in range(0,len(indices),3):union(indices[t],indices[t+1]);union(indices[t],indices[t+2])
groups={}
for i in set(indices):groups.setdefault(find(i),[]).append(i)
triangle_groups={}
for t in range(0,len(indices),3):triangle_groups.setdefault(find(indices[t]),[]).append(indices[t:t+3])
def bounds(ids):return {'minCm':[min(ue_points[i][a]for i in ids)for a in range(3)],'maxCm':[max(ue_points[i][a]for i in ids)for a in range(3)]}
keys=[];triangles=[]
for key,ids in groups.items():
 b=bounds(ids);tops=[]
 for tri in triangle_groups[key]:
  a,bp,c=[ue_points[i]for i in tri];ab=[bp[k]-a[k]for k in range(3)];ac=[c[k]-a[k]for k in range(3)];normal=[ab[1]*ac[2]-ab[2]*ac[1],ab[2]*ac[0]-ab[0]*ac[2],ab[0]*ac[1]-ab[1]*ac[0]];length=math.sqrt(sum(v*v for v in normal))
  # Positive up is robust to glTF-to-UE horizontal orientation determinant.
  if length>1e-9 and abs(normal[2])/length>.9:
   topz=sum(p[2]for p in [a,bp,c])/3
   if topz>=b['maxCm'][2]-.12:tops.append([a,bp,c])
 keys.append({'vertexIds':ids,'trianglesUEVertexIds':[[tri[0],tri[2],tri[1]]for tri in triangle_groups[key]],'componentId':len(keys),'vertexCount':len(ids),'triangleCount':len(triangle_groups[key]),**b,'topCm':b['maxCm'][2],'topTriangleCount':len(tops),'topTrianglesUECm':tops})
keys.sort(key=lambda k:(-round(k['maxCm'][1],1),k['minCm'][0]))
for i,k in enumerate(keys):k['keycapId']=i
out={'privateOnly':True,'source':str(source),'sourceSHA256':hashlib.sha256(raw).hexdigest(),'nodeIndex':ni,'nodeName':doc['nodes'][ni]['name'],'worldNodeMatrixColumnMajor':m,'coordinateContract':'UE cm = 100 * (source glTF x, source glTF z, source glTF y); compare against native import pivot audit before use','weldToleranceMeters':1e-7,'geometryBoundsUECm':bounds(range(len(points))),'vertexCount':len(points),'indexCount':len(indices),'disconnectedComponentCount':len(keys),'verticesUECm':ue_points,'keycaps':keys,'windingNote':'Source glTF x,z,y conversion swaps horizontal/up axes; component triangles reverse winding to preserve outward normals','reviewStatus':'Actual source geometry extraction; native skin collision/contact review pending'}
dest=args.output;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k not in ('keycaps','verticesUECm')},indent=2));print('component vertex/triangle count histogram', {str((k['vertexCount'],k['triangleCount'])):sum((x['vertexCount'],x['triangleCount'])==(k['vertexCount'],k['triangleCount'])for x in keys)for k in keys});print('top heights cm',sorted(set(round(k['topCm'],5)for k in keys)));print('output',dest)
