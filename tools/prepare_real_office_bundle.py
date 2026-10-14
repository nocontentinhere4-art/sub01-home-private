"""One bounded Blender source job: authentic desk, side-edge clamp lamp, shelves and46 books.

Pure planners are testable without Blender. All heavy/source collision execution
belongs to renderer on the authorized server. No UE or runtime mutation.
"""
import argparse,copy,hashlib,json,math,struct,sys
from pathlib import Path
from real_linea_lamp_mount import geometry
from prepare_real_linea140_placement import run as prepare_desk,DESK_Y
from home_asset_audit import read_gltf
from unreal_import_real_shelf_books import validate_provider_coverage
SHELF_SHA='bbc7db5777547fcaa82314324a5be0ec1961d6d7f15aa062fe2fdbd1d1e7ee6c'
BOOKS_SHA='611a3d84885876f5417a4e6b283a940bee24e793bc68b4d9e47e9ed53f62f459'
HOME_SHA='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
CENTRES=((1.5,-3.66),(2.7,-3.66));UNIT=.1


def board_surfaces(parts):
 faces=[]
 for row in parts:
  for indices in row['triangles']:
   pts=[[v*UNIT for v in row['points'][i]]for i in indices];a,b,c=pts;v=[b[i]-a[i]for i in range(3)];w=[c[i]-a[i]for i in range(3)];n=[v[1]*w[2]-v[2]*w[1],v[2]*w[0]-v[0]*w[2],v[0]*w[1]-v[1]*w[0]];length=math.sqrt(sum(x*x for x in n))
   if length and n[1]/length>.98 and length/2>.015:faces.append((sum(p[1]for p in pts)/3,pts,length/2))
 groups=[]
 for y,pts,area in sorted(faces):
  if not groups or abs(y-groups[-1]['height'])>.001:groups.append({'height':y,'triangles':[],'area':0})
  groups[-1]['triangles'].append(pts);groups[-1]['area']+=area
 if len(groups)!=5 or any(g['area']<.45 for g in groups):raise ValueError('Actual five full wood board tops not unambiguously measured')
 for group in groups:
  pts=[p for t in group['triangles']for p in t];group['bounds_xz']=[[min(p[a]for p in pts)for a in (0,2)],[max(p[a]for p in pts)for a in (0,2)]]
 return groups


def measured_shelf_depth_plan(depth,baseboard_front,desk_back):
 """Exact genuine shelf depth fits measured baseboard/desk interval, unchanged."""
 if not all(math.isfinite(v)for v in [*depth,baseboard_front,desk_back])or depth[1]<=depth[0]:raise ValueError('Invalid actual furniture/architecture bounds')
 centre=baseboard_front+.0051-depth[0];front=centre+depth[1];front_gap=desk_back-front
 if front_gap<.002:raise ValueError('Full genuine shelf cannot fit with5mm baseboard and2mm desk clearances')
 return {'centre_ue_y_m':centre,'actual_baseboard137138_front_ue_y_m':baseboard_front,'actual_desk_back_ue_y_m':desk_back,'actual_shelf_back_ue_y_m':centre+depth[0],'actual_shelf_front_ue_y_m':front,'back_baseboard_gap_m':.0051,'precision_clearance_forward_delta_m':.0001,'actual160_precision_touch_witness':{'source160_front_ue_y_m':-3.877500057220459,'previous_signed_gap_m':7.648020972084169e-08,'diagnostic_sha256':'0a026144131f29882aebacd9f1728b64fe72650ecb19583a9d1a53f31e7b9f6a'},'front_desk_gap_m':front_gap,'unchanged_source_shape_scale':True,'full_triangle_bvh_required':True}


def shelf_export(source,output,centres=CENTRES):
 raw=Path(source).read_bytes()
 if hashlib.sha256(raw).hexdigest()!=SHELF_SHA:raise ValueError('Actual shelf source bytes differ')
 length=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+length]);rest=raw[20+length:]
 if len(doc['nodes'])!=1 or len(doc['meshes'])!=1 or doc['scenes'][doc.get('scene',0)]['nodes']!=[0]:raise ValueError('Verified one complete authored shelf node differs')
 _,parts=geometry(source);boards=board_surfaces(parts);low=min(p[1]for r in parts for p in r['points'])*UNIT;origin=.025+.00001-low
 node=doc['nodes'][0];node['name']='SUB01_RealSteel_bbc7db57_A';other=copy.deepcopy(node);other['name']='SUB01_RealSteel_bbc7db57_B'
 doc['nodes']=[node,other];doc['meshes'][0]['name']='SUB01_RealSteel_bbc7db57_FullOriginalMesh'
 for i,(x,z)in enumerate(centres):doc['nodes'].append({'name':f'SUB01_RealSteel_bbc7db57_Root{i}','children':[i],'translation':[x,origin,z],'scale':[UNIT]*3})
 doc['scenes']=[{'name':'SUB01_RealSteel_bbc7db57_TwoAuthenticCopies','nodes':[2,3]}];doc['scene']=0
 encoded=json.dumps(doc,separators=(',',':')).encode();encoded+=b' '*(-len(encoded)%4)
 out=struct.pack('<4sII',b'glTF',2,20+len(encoded)+len(rest))+struct.pack('<II',len(encoded),0x4E4F534A)+encoded+rest
 Path(output).write_bytes(out)
 if out[20+len(encoded):]!=rest:raise ValueError('Shelf original attribute/texture binary changed')
 shelves=[]
 for i,(x,z)in enumerate(centres):
  for k,board in enumerate(boards):
   lo,hi=board['bounds_xz'];shelves.append({'instance':i,'board':k,'top_ue_m':origin+board['height'],'xy_bounds_m':[[x+lo[0],z+lo[1]],[x+hi[0],z+hi[1]]],'actual_support_triangles_source_m':board['triangles']})
 return {'sha256':hashlib.sha256(out).hexdigest(),'source_sha256':SHELF_SHA,'source_binary_unchanged':True,'triangles_per_authentic_shelf':sum(len(r['triangles'])for r in parts),'shelf_origin_height_m':origin,'actual_centres_ue_m':[list(v)for v in centres],'boards':shelves,'native_actor_labels':['SUB01_RealSteel_bbc7db57_A','SUB01_RealSteel_bbc7db57_B']}


def pack_books(books,boards):
 bins=[dict(board,used_width=0,books=[])for board in boards];placed=[];margin=.02;gap=.012
 for book in sorted(books,key=lambda b:(-(b['old_bounds_ue_m'][1][0]-b['old_bounds_ue_m'][0][0]),b['id'])):
  lo,hi=book['old_bounds_ue_m'];width=hi[0]-lo[0];depth=hi[1]-lo[1];height=hi[2]-lo[2]
  if not all(math.isfinite(v)and v>0 for v in (width,depth,height)):raise ValueError('Invalid whole-book geometry bounds')
  candidates=[]
  for index,board in enumerate(bins):
   a,b=board['xy_bounds_m'];available=b[0]-a[0]-2*margin-board['used_width']
   if available>=width and depth<=b[1]-a[1]-2*margin and height<.44:candidates.append((len(board['books']),board['used_width'],index))
  if not candidates:raise ValueError('A whole source book does not fit actual wood boards '+book['id'])
  _,_,index=min(candidates);board=bins[index];a,b=board['xy_bounds_m'];newlo=[a[0]+margin+board['used_width'],(a[1]+b[1]-depth)/2,board['top_ue_m']+.0005];delta=[newlo[i]-lo[i]for i in range(3)]
  item=dict(book,delta_ue_cm=[v*100 for v in delta],new_bounds_ue_m=[newlo,[newlo[i]+hi[i]-lo[i]for i in range(3)]],shelf_instance=board['instance'],board=board['board'],support_gap_m=.0005)
  board['books'].append(item);board['used_width']+=width+gap;placed.append(item)
 if len(placed)!=46 or len({b['id']for b in placed})!=46:raise ValueError('All46 complete physical books must survive')
 return sorted(placed,key=lambda b:b['id'])


def prepare_books(glb,report_path,boards):
 if hashlib.sha256(Path(glb).read_bytes()).hexdigest()!=BOOKS_SHA:raise ValueError('Actual COMPLETE46-book GLB differs')
 report=json.loads(Path(report_path).read_text());validate_provider_coverage(report)
 if report['additive_glb']['sha256']!=BOOKS_SHA or len(report['built'])!=46:raise ValueError('Actual COMPLETE book receipt differs')
 doc,parts=geometry(glb);lookup={b['id']:b for b in report['built']};groups={}
 for row in parts:
  name=doc['nodes'][row['node']]['name']
  if name not in lookup:raise ValueError('Unowned source book node '+str(name))
  groups.setdefault(name,[]).append(row)
 if set(groups)!=set(lookup):raise ValueError('Complete46 source books missing')
 books=[]
 for name,rows in groups.items():
  points=[(p[0],p[2],p[1])for r in rows for p in r['points']];old=[[min(p[a]for p in points)for a in range(3)],[max(p[a]for p in points)for a in range(3)]]
  pivot=lookup[name]['pivot_runtime_m'];books.append({'id':name,'old_bounds_ue_m':old,'actual_source_triangle_count':sum(len(r['triangles'])for r in rows),'source_book':lookup[name]['source_book'],'old_pivot_ue_cm':[pivot[0]*100,pivot[2]*100,pivot[1]*100],'geometry_uv_materials_unchanged':True})
 return pack_books(books,boards),groups


def run(args):
 import bpy
 from mathutils.bvhtree import BVHTree
 from mathutils import Vector
 output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
 if hashlib.sha256(Path(args.home_source).read_bytes()).hexdigest()!=HOME_SHA:raise ValueError('Actual original home source differs')
 desk=prepare_desk(args.desk_source,output/'desk.glb',args.lamp_source,args.lamp_receipt,args.home_source)
 _,shelf_geometry=geometry(args.shelf_source);_,home_geometry=geometry(args.home_source)
 depth=[min(p[2]for r in shelf_geometry for p in r['points'])*UNIT,max(p[2]for r in shelf_geometry for p in r['points'])*UNIT]
 baseboard_front=max(p[2]for r in home_geometry if r['node']in(137,138)for p in r['points'])
 depth_plan=measured_shelf_depth_plan(depth,baseboard_front,desk['actual_export_bounds_m'][0][2])
 centres=tuple((x,depth_plan['centre_ue_y_m'])for x,_ in CENTRES)
 shelf=shelf_export(args.shelf_source,output/'shelves.glb',centres);shelf['actual_architecture_clearance']=depth_plan;books,groups=prepare_books(args.books_glb,args.books_report,shelf['boards'])
 from real_office_plant import source_plan,DELTA
 plant,plant_members=source_plan(args.home_source)
 _,shelf_parts=geometry(args.shelf_source);_,home=geometry(args.home_source)
 def bvh(points,faces):return BVHTree.FromPolygons([Vector(p)for p in points],faces,all_triangles=True,epsilon=0)
 retired={162,181,182,190,191,126,255,256,221,222,223,224}
 hide=json.loads(Path(args.books_hide_manifest).read_text());old_cube_names={r['name']for r in hide['originals']};home_doc,_=read_gltf(Path(args.home_source));retired|={i for i,n in enumerate(home_doc['nodes'])if n.get('name')in old_cube_names}
 def bounds(points):return [[min(p[a]for p in points)for a in range(3)],[max(p[a]for p in points)for a in range(3)]]
 def intersects(a,b):return all(a[0][i]<=b[1][i]and b[0][i]<=a[1][i]for i in range(3))
 cached_home=[]
 for hr in home:
  if hr['node']in retired:continue
  faces=hr['triangles']
  if hr['node']==163:
   if len(faces)!=1840:raise ValueError('Exact rail/stem union source count changed')
   faces=faces[1640:1800]
  hp=[(p[0],p[2],p[1])for p in hr['points']];cached_home.append((hr['node'],bounds(hp),bvh(hp,faces)))
 issues=[];shelf_bvhs=[]
 for instance,(x,z)in enumerate(centres):
  for row in shelf_parts:
   pts=[(x+p[0]*UNIT,z+p[2]*UNIT,shelf['shelf_origin_height_m']+p[1]*UNIT)for p in row['points']];sb=bvh(pts,row['triangles']);shelf_bvhs.append(sb)
   for node,hbox,hb in cached_home:
    if not intersects(bounds(pts),hbox):continue
    hits=sb.overlap(hb)
    if hits:issues.append({'shelf':instance,'home_node':node,'pairs':len(hits)})
 desk_doc,deskparts=geometry(output/'desk.glb');desk_bvhs=[]
 for row in deskparts:
  dp=[(p[0],p[2],p[1])for p in row['points']];db=bvh(dp,row['triangles']);desk_bvhs.append((row,dp,db))
  for sb in shelf_bvhs:
   if db.overlap(sb):issues.append({'desk_node':row['node'],'shelf_overlap':True})
 plant_bvhs=[];plant_contacts=0;allowed={(r['node'],r['triangle'])for r in plant['exact_nonpenetrating_base_boundary_faces']}
 for row in plant_members:
  points=[(p[0]+DELTA[0],p[2]+DELTA[1],p[1]+DELTA[2])for p in row['points']];pb=bvh(points,row['triangles']);plant_bvhs.append(pb)
  for dr,dp,db in desk_bvhs:
   for pi,di in pb.overlap(db):
    pp=[points[v]for v in row['triangles'][pi]];dd=[dp[v]for v in dr['triangles'][di]]
    if dr['node']==44 and (row['node'],pi)in allowed and min(p[2]for p in pp)>=.845-1e-8 and all(abs(p[2]-.845)<1e-7 for p in dd):plant_contacts+=1
    else:issues.append({'plant_node':row['node'],'plant_triangle':pi,'desk_node':dr['node'],'desk_triangle':di})
  if any(pb.overlap(sb)for sb in shelf_bvhs):issues.append({'plant_node':row['node'],'real_shelf_penetration':True})
  for node,hbox,hb in cached_home:
   if intersects(bounds(points),hbox)and pb.overlap(hb):issues.append({'plant_node':row['node'],'protected_home_node':node})
 plant['source_collision_proof']={'ok':not issues,'exact_nonpenetrating_table_contact_pairs':plant_contacts,'epsilon':0}
 for book in books:
  delta=[v/100 for v in book['delta_ue_cm']]
  for row in groups[book['id']]:
   pts=[(p[0]+delta[0],p[2]+delta[1],p[1]+delta[2])for p in row['points']];bb=bvh(pts,row['triangles'])
   if any(bb.overlap(pb)for pb in plant_bvhs):issues.append({'book':book['id'],'real_plant_penetration':True})
   if any(bb.overlap(sb)for sb in shelf_bvhs):issues.append({'book':book['id'],'real_shelf_penetration':True})
   for node,hbox,hb in cached_home:
    if not intersects(bounds(pts),hbox):continue
    hits=bb.overlap(hb)
    if hits:issues.append({'book':book['id'],'home_node':node,'pairs':len(hits)})
 if issues:raise ValueError('Actual whole office collision proof failed '+json.dumps(issues[:100]))
 receipt={'schema':'sub01.real-office-bundle.v1','desk':desk,'shelf':shelf,'books':books,'plant':plant,'complete_original_book_glb_sha256':BOOKS_SHA,'whole_book_geometry_pbr_preserved':True,'books_native_retarget_only':True,'hide_only_source_actor_nodes':[181,182,190,191],'home_source_sha256':HOME_SHA,'desk_forward_delta_y_cm':8,'original_devices_chair_stairs_unchanged':True,'source_triangle_collision_proof':{'ok':True,'issues':[],'retired_exact_source_nodes':sorted(retired)},'native_visual_verified':False}
 (output/'office-bundle.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'schema':receipt['schema'],'books':len(books),'boards':len(shelf['boards']),'source_collision_proof':True}));return receipt

if __name__=='__main__':
 parser=argparse.ArgumentParser()
 for name in ('desk-source','shelf-source','lamp-source','lamp-receipt','home-source','books-glb','books-report','books-hide-manifest','output'):parser.add_argument('--'+name,required=True)
 args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]if '--'in sys.argv else None);run(args)
