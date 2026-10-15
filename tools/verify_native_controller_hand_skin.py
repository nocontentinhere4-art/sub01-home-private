"""Independent read-only4s native SKIN comparison, never controller acceptance.

Consumes InspectCapturedHandSkin JSON and pinned source geometry. Native vertex
IDs are mapped from bind positions AND actual normalized bone weights, never
from joint centres. Native/source wrist rotations are deliberately not equated.
Contact distances use only the actual physical prop mesh/TRS; open surfaces
receive unsigned distances, never an invented inside/outside verdict.
"""
import argparse,hashlib,heapq,itertools,json,math,re,sys,time
from pathlib import Path

OWNER_SHA='45e917725f02836dee6d051d9b47dd2785208c78b503fa935ddb322fe69adea8'
CLIP_SHA='bf31d64518d85f6eefd8150009a758ddddc95ca6afd63d5d83bdf29a2dcdaaf9'
CONTROLLER_SHA='c034a1444711a44f0726e7264b1e2e2b47b1bbdba0e5dd615eef27001a4717e4'
NORMALIZED_CONTROLLER_SHA='8134769e2680197a0b5a453e1fad11f1c82a5df54c1607b6c4c0a501721b0034'
DECODED_CONTROLLER_SHA='afe4b65092017fc7a0ea6991352ef0d738479ef10d45b980623cf6a00d02a132'
REPORT_SHA='a022ab5bff0ceb5d544c4e3e558ec5f9d2560b7f7b8f5356e31e21c157f76c02'
READER_SHA='d9d271e9dff76412448f340000014adfd85aceffcf2500e822055342793f32e5'
OWNER_ASSET='/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner'
CLIP_ASSET='/Game/Sub01Hands/Play/SUB01_GamingGrip.SUB01_GamingGrip'
BIND_TOL_CM=.02
SKIN_TOL_CM=.02


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canonical(n):return re.sub(r'^mixamorig[:_]?','',str(n),flags=re.I)
def add(a,b):return tuple(x+y for x,y in zip(a,b))
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def mul(a,t):return tuple(x*t for x in a)
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def distance(a,b):return math.sqrt(dot(sub(a,b),sub(a,b)))
def qrotate(q,p):
 v=q[:3];t=mul(cross(v,p),2);return add(p,add(mul(t,q[3]),cross(v,t)))
def basis_cm(p):return (p[0]*100,p[2]*100,p[1]*100)
def matrix_point(m,p):return tuple(sum(m[c*4+r]*p[c]for c in range(3))+m[12+r]for r in range(3))


def parse_transform(value):
 parts=value.split('|')
 if len(parts)!=3:raise ValueError('Exact native FTransform string required')
 rows=[tuple(float(v)for v in re.findall(r'[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?',part))for part in parts]
 if any(len(v)!=3 for v in rows)or not all(math.isfinite(x)for v in rows for x in v):raise ValueError('Finite native TRS required')
 p,(pitch,yaw,roll),s=rows
 if min(s)<=0:raise ValueError('Positive actual native scale required')
 sp,sy,sr=[math.sin(math.radians(v)/2)for v in (pitch,yaw,roll)];cp,cy,cr=[math.cos(math.radians(v)/2)for v in (pitch,yaw,roll)]
 q=(cr*sp*sy-sr*cp*cy,-cr*sp*cy-sr*cp*sy,cr*cp*sy-sr*sp*cy,cr*cp*cy+sr*sp*sy)
 return p,q,s


def transform(p,trs):
 t,q,s=trs;return add(t,qrotate(q,tuple(x*y for x,y in zip(p,s))))

def inverse_transform(p,trs):
 t,q,s=trs;v=qrotate((-q[0],-q[1],-q[2],q[3]),sub(p,t));return tuple(x/y for x,y in zip(v,s))


def normalized_weights(rows):
 weights={}
 for row in rows:
  name=canonical(row['bone']);raw=row['raw']
  if not isinstance(raw,(int,float))or not math.isfinite(raw)or raw<0:raise ValueError('Invalid native influence')
  weights[name]=weights.get(name,0)+raw
 total=sum(weights.values())
 if total<=0:raise ValueError('Zero native skin weight')
 return {n:v/total for n,v in weights.items()if v},total


def validate_capture(doc,asset):
 if doc.get('schema')!='sub01.actual-hand-skin-witness.v1' or doc.get('owner_asset')!=OWNER_ASSET or doc.get('capture_asset')!=CLIP_ASSET:raise ValueError('Exact actual derived controller skin witness required')
 if abs(doc.get('capture_time',-1)-4)>1e-4 or any(doc.get(k)is not False for k in ('contact_accepted','activity_ready')):raise ValueError('Frozen4s diagnostic only, no readiness claim')
 if not isinstance(doc.get('native_pid'),int)or doc['native_pid']<=0 or doc.get('native_start_ticks',0)<=0:raise ValueError('Actual native process identity required')
 skin=doc['skin'];vertices=skin['vertices']
 if skin.get('invalidInfluences')!=0 or not 1<=len(vertices)<=20000 or len({v['globalVertex']for v in vertices})!=len(vertices):raise ValueError('Actual bounded valid imported vertex identity required')
 if asset.get('schema')!='sub01.native-controller-asset.v1'or asset.get('source_sha256')!=CONTROLLER_SHA or asset.get('import_source_sha256')!=NORMALIZED_CONTROLLER_SHA:raise ValueError('Actual physical controller receipt required')
 props=doc.get('actual_props',[]);physical=asset['physical_assembly']
 if len(props)!=1 or props[0]['mesh']!=physical['mesh'] or props[0]['component']!=physical['component'] or 'contact'in props[0]['mesh'].lower():raise ValueError('Only exact actual physical prop, never baked contact plane')
 return vertices,props[0]


class BindLookup:
 """No fitted registration: fixed glTF(x,z,y)*100 native bind convention."""
 def __init__(self,rows,tolerance=BIND_TOL_CM):
  self.rows=rows;self.tol=tolerance;self.buckets={}
  for i,r in enumerate(rows):self.buckets.setdefault(self.key(r['bind_cm']),[]).append(i)
 def key(self,p):return tuple(math.floor(x/self.tol)for x in p)
 def match(self,vertex):
  p=vertex['bindPositionCm'];weights,total=normalized_weights(vertex['weights']);key=self.key(p);candidates=[];wtol=1/max(total,255)+1e-6
  for delta in itertools.product((-1,0,1),repeat=3):
   for i in self.buckets.get(tuple(x+y for x,y in zip(key,delta)),[]):
    row=self.rows[i];error=distance(p,row['bind_cm']);werror=max(abs(weights.get(n,0)-row['weights'].get(n,0))for n in weights.keys()|row['weights'].keys())
    if error<=self.tol and werror<=wtol:candidates.append((error,werror,i))
  if not candidates:raise ValueError('No actual source vertex matches native bind+weights '+str(vertex['globalVertex']))
  candidates.sort();best=candidates[0];return self.rows[best[2]],{'bind_error_cm':best[0],'max_weight_error':best[1],'weight_quantization_tolerance':wtol,'equivalent_source_candidates':[self.rows[i]['source_id']for _,_,i in candidates]}


def closest_triangle(p,a,b,c):
 """Ericson region tests, including exact degenerate segment fallback."""
 ab,ac,ap=sub(b,a),sub(c,a),sub(p,a)
 if dot(cross(ab,ac),cross(ab,ac))==0:
  points=[]
  for x,y in ((a,b),(b,c),(c,a)):
   d=sub(y,x);length=dot(d,d);t=0 if not length else max(0,min(1,dot(sub(p,x),d)/length));points.append(add(x,mul(d,t)))
  return min(points,key=lambda x:distance(p,x))
 d1,d2=dot(ab,ap),dot(ac,ap)
 if d1<=0 and d2<=0:return a
 bp=sub(p,b);d3,d4=dot(ab,bp),dot(ac,bp)
 if d3>=0 and d4<=d3:return b
 vc=d1*d4-d3*d2
 if vc<=0 and d1>=0 and d3<=0:return add(a,mul(ab,d1/(d1-d3)))
 cp=sub(p,c);d5,d6=dot(ab,cp),dot(ac,cp)
 if d6>=0 and d5<=d6:return c
 vb=d5*d2-d1*d6
 if vb<=0 and d2>=0 and d6<=0:return add(a,mul(ac,d2/(d2-d6)))
 va=d3*d6-d5*d4
 if va<=0 and d4-d3>=0 and d5-d6>=0:return add(b,mul(sub(c,b),(d4-d3)/((d4-d3)+(d5-d6))))
 return add(a,add(mul(ab,vb/(va+vb+vc)),mul(ac,vc/(va+vb+vc))))


class Surface:
 def __init__(self,triangles):
  self.triangles=triangles;self.nodes=[]
  def build(ids):
   lo=tuple(min(triangles[i][j][k]for i in ids for j in range(3))for k in range(3));hi=tuple(max(triangles[i][j][k]for i in ids for j in range(3))for k in range(3));index=len(self.nodes);self.nodes.append(None)
   if len(ids)<=12:self.nodes[index]=(lo,hi,ids,None)
   else:
    axis=max(range(3),key=lambda k:hi[k]-lo[k]);ids.sort(key=lambda i:sum(v[axis]for v in triangles[i]));middle=len(ids)//2;children=(build(ids[:middle]),build(ids[middle:]));self.nodes[index]=(lo,hi,None,children)
   return index
  if not triangles:raise ValueError('Actual physical triangles required')
  build(list(range(len(triangles))))
 def nearest(self,p):
  def bound(i):
   lo,hi,_,_=self.nodes[i];return sum(max(lo[k]-p[k],0,p[k]-hi[k])**2 for k in range(3))
  queue=[(bound(0),0)];best=float('inf');witness=None
  while queue:
   lower,index=heapq.heappop(queue)
   if lower>best:continue
   _,_,ids,children=self.nodes[index]
   if ids is None:
    for child in children:heapq.heappush(queue,(bound(child),child))
   else:
    for i in ids:
     q=closest_triangle(p,*self.triangles[i]);sq=dot(sub(p,q),sub(p,q))
     if sq<best:best=sq;witness=(i,q)
  return math.sqrt(best),witness


def source_vertices(G,owner,clip,source_time,body):
 skin=owner.doc['skins'][0];joints=skin['joints'];names=[canonical(owner.nodes[i]['name'])for i in joints];ibms=owner.accessor(skin['inverseBindMatrices']);world=G.world_pose(clip,clip.animation(),source_time);index={canonical(n.get('name','')):i for i,n in enumerate(clip.nodes)};rows=[]
 for ni,node in enumerate(owner.nodes):
  if node.get('skin')!=0 or 'mesh'not in node:continue
  if any(k in node for k in ('matrix','translation','rotation','scale')):raise ValueError('Unsupported source mesh-node bind TRS; no guessed bake')
  for pi,primitive in enumerate(owner.doc['meshes'][node['mesh']]['primitives']):
   a=primitive['attributes'];positions=owner.accessor(a['POSITION']);ids=owner.accessor(a['JOINTS_0']);weights=owner.accessor(a['WEIGHTS_0'])
   for vi,(p,js,ws)in enumerate(zip(positions,ids,weights)):
    total=sum(ws)
    if total<=0 or not any(w>0 and 'Hand'in names[int(j)]for j,w in zip(js,ws)):continue
    normalized={};posed=(0,0,0)
    for j,w in zip(js,ws):
     if not w:continue
     j=int(j);name=names[j];normalized[name]=normalized.get(name,0)+w/total;t,q,s=world[index[name]];point=add(t,qrotate(q,mul(matrix_point(ibms[j],p),s)));posed=add(posed,mul(point,w/total))
    rows.append({'source_id':[ni,pi,vi],'bind_cm':basis_cm(p),'weights':normalized,'world_cm':transform(basis_cm(posed),body)})
 return rows,world,index


def controller_triangles(G,g,actual,original):
 world=G.world_pose(g,G.RestPose(),0);triangles=[];faces=[];physical_source=[]
 for ni,node in enumerate(g.nodes):
  if 'mesh'not in node:continue
  t,q,s=world[ni]
  for pi,p in enumerate(g.doc['meshes'][node['mesh']]['primitives']):
   material=g.doc['materials'][p['material']]['name']
   if material=='controller_contact':continue
   if material!='controller':raise ValueError('Unexpected controller source material')
   if p.get('mode',4)!=4:raise ValueError('Physical triangle primitive required')
   pts=[add(t,qrotate(q,mul(v,s)))for v in g.accessor(p['attributes']['POSITION'])];indices=[int(v[0])for v in g.accessor(p['indices'])]
   transformed=[transform(inverse_transform(basis_cm(v),original),actual)for v in pts]
   for i in range(0,len(indices),3):
    ids=indices[i:i+3];triangles.append(tuple(transformed[j]for j in ids));physical_source.append(tuple(pts[j]for j in ids));faces.append([ni,pi,i//3])
 return triangles,faces,physical_source


def verify(args):
 started=time.monotonic();helper=Path(args.helpers)/'life_gltf.py'
 if sha(helper)!=READER_SHA:raise ValueError('Pinned independent pure source reader required')
 sys.path.insert(0,str(helper.parent));import life_gltf as G
 for path,expected in ((args.owner,OWNER_SHA),(args.clip,CLIP_SHA),(args.controller,DECODED_CONTROLLER_SHA),(args.grip_report,REPORT_SHA)):
  if sha(path)!=expected:raise ValueError('Actual source hash differs '+str(path))
 doc=json.loads(Path(args.native).read_text());asset=json.loads(Path(args.asset_receipt).read_text());vertices,prop=validate_capture(doc,asset);body=parse_transform(doc['body_world']);actual=parse_transform(prop['world']);original_row=asset['physical_assembly']['original_source_transform'];original=(original_row['translation'],original_row['quaternion'],original_row['scale'])
 owner,clip,controller=[G.Gltf(p)for p in (args.owner,args.clip,args.controller)];animation=clip.animation();source_time=doc['capture_time']+animation.start
 if abs(animation.start-.03333333507180214)>1e-8:raise ValueError('Actual152key source timebase changed')
 source_rows,world,index=source_vertices(G,owner,clip,source_time,body);lookup=BindLookup(source_rows);triangles,face_ids,source_triangles=controller_triangles(G,controller,actual,original);surface=Surface(triangles);result_rows=[]
 report=json.loads(Path(args.grip_report).read_text());offset=report['fixed_offset']['controller_in_right_hand_gltf'];hand=world[index['RightHand']];mount_errors=[]
 for native_tri,source_tri in zip(triangles,source_triangles):
  for measured,p in zip(native_tri,source_tri):
   expected=transform(basis_cm(add(hand[0],qrotate(hand[1],tuple(sum(offset[r][c]*p[c]for c in range(3))+offset[r][3]for r in range(3))))),body);mount_errors.append(distance(expected,measured))
 for i,v in enumerate(vertices):
  if i%64==0 and time.monotonic()-started>args.max_seconds:raise TimeoutError('Bounded skin verifier incomplete, no acceptance')
  source,mapping=lookup.match(v);point=v['worldPositionCm'];skin_error=distance(point,source['world_cm']);unsigned,(ti,nearest)=surface.nearest(point);normal=cross(sub(triangles[ti][1],triangles[ti][0]),sub(triangles[ti][2],triangles[ti][0]));length=math.sqrt(dot(normal,normal));plane=None if length==0 else dot(sub(point,nearest),normal)/length
  result_rows.append({'native_global_vertex':v['globalVertex'],'native_section':v['section'],'native_vertex_in_section':v['vertex'],'source_vertex':source['source_id'],'native_side':v['side'],'skin_world_error_cm':skin_error,'native_world_cm':point,'source_world_cm':source['world_cm'],'bind_mapping':mapping,'actual_prop_nearest_unsigned_cm':unsigned,'actual_prop_triangle':face_ids[ti],'actual_prop_nearest_world_cm':nearest,'nearest_world_triangle_winding_plane_gap_cm':plane,'plane_gap_is_not_inside_outside':True})
 used={v['globalVertex']for v in vertices};native_triangles=doc['skin'].get('fullySelectedTrianglesGlobalIds',[])
 if any(len(t)!=3 or any(i not in used for i in t)for t in native_triangles):raise ValueError('Native selected skin triangle references absent identity')
 errors=[r['skin_world_error_cm']for r in result_rows];out={'schema':'sub01.native-controller-hand-skin-comparison.v1','native_input_sha256':sha(args.native),'native_pid':doc['native_pid'],'native_start_ticks':doc['native_start_ticks'],'capture_time_s':doc['capture_time'],'source_time_s':source_time,'source_first_key_s':animation.start,'owner_sha256':OWNER_SHA,'clip_sha256':CLIP_SHA,'source_controller_sha256':CONTROLLER_SHA,'decoded_controller_sha256':DECODED_CONTROLLER_SHA,'grip_report_sha256':REPORT_SHA,'actual_prop':prop,'prop_geometry_basis':'Pinned full physical controller triangles, transformed by actual component TRS times inverse receipt original-source TRS; native physics collider/contact not inferred','actual_prop_full_source_corner_mount_error_cm':max(mount_errors),'imported_vertices':len(vertices),'fully_selected_native_skin_triangles':len(native_triangles),'source_mapping_tolerance_cm':BIND_TOL_CM,'skin_comparison_tolerance_cm':SKIN_TOL_CM,'maximum_actual_skin_world_error_cm':max(errors),'source_native_skin_positions_within_tolerance':max(errors)<=SKIN_TOL_CM,'rows':result_rows,'elapsed_s':time.monotonic()-started,'source_native_wrist_basis_not_equated':True,'surface_caveats':['30% broad imported hand selection is not a palm/distal contact set','Only fully selected skin triangles exported; hand/forearm boundary triangles absent','Actual controller surface unsigned distances only; open seams/throughholes do not define a certified solid','World triangle-winding plane gap is only a local signed plane observation; reflection/winding conventions are not an authored outward-normal or penetration proof','No palm support/trigger/thumb/activity verdict from proximity or joint centres'],'contact_accepted':False,'activity_ready':False,'native_ready':False,'world_or_source_changed':False};Path(args.output).write_text(json.dumps(out,indent=2,allow_nan=False)+'\n');return out


def main():
 parser=argparse.ArgumentParser()
 for name in ('native','owner','clip','controller','grip-report','asset-receipt','helpers','output'):parser.add_argument('--'+name,required=True)
 parser.add_argument('--max-seconds',type=float,default=60);args=parser.parse_args()
 try:out=verify(args)
 except Exception as error:
  Path(args.output).write_text(json.dumps({'schema':'sub01.native-controller-hand-skin-comparison.v1','incomplete':True,'error':str(error),'native_input_sha256':sha(args.native),'contact_accepted':False,'activity_ready':False,'native_ready':False,'world_or_source_changed':False},indent=2)+'\n');raise
 print(json.dumps({k:v for k,v in out.items()if k!='rows'},indent=2))

if __name__=='__main__':main()
