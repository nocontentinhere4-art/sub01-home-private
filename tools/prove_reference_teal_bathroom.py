"""Independent exported source proof for the private teal bathroom.

Run with Blender's Python on the leased server. Reads GLBs only; never native
Editor/Game/OS input. A real paint/hardware crossing is a refusal, never waived
as an attachment. Only independently measured zero-volume plane support can
qualify as a documented decorative attachment.
"""
import argparse,collections,hashlib,itertools,json,math,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
HOME_SHA='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
FIXTURE_SHA='b8d190b7d7cf274126b4be35cf2ccf447b25c742da037cc222c43fe57f437a92'
CORRIDOR_SHA='5ffac2406e668a327427e60bc75e3ee3ecf13a89381d0312b821277386cb9c91'
DOOR_SHA='5b8a2bb8b4bb8fe19af1d0c086fb78f3e7f9dff9e06170a06642a8f3d1761a0c'
CORNER_TOL_CM=.0001
CONTACT_EPS_CM=.001

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def signed_distances(t,plane):
 n=cross(sub(plane[1],plane[0]),sub(plane[2],plane[0]));length=math.sqrt(dot(n,n))
 return None if not length else [dot(sub(p,plane[0]),n)/length for p in t]
def segment_to_plane(triangle,plane):
 distances=signed_distances(triangle,plane)
 if distances is None:return []
 points=[]
 for p,q,dp,dq in zip(triangle,triangle[1:]+triangle[:1],distances,distances[1:]+distances[:1]):
  if abs(dp)<1e-9:points.append(tuple(p))
  if dp*dq<0:
   t=dp/(dp-dq);points.append(tuple(x+t*(y-x)for x,y in zip(p,q)))
 unique=[]
 for point in points:
  if not any(math.dist(point,q)<1e-8 for q in unique):unique.append(point)
 return unique

def point_edge_distance(p,a,b):
 d=sub(b,a);length=dot(d,d);t=0 if not length else max(0,min(1,dot(sub(p,a),d)/length));return math.dist(p,tuple(x+t*y for x,y in zip(a,d)))

def finite_intersection(a,b):
 aa,bb=segment_to_plane(a,b),segment_to_plane(b,a)
 if len(aa)<2 or len(bb)<2:return {'segment_length_cm':0,'minimum_interior_edge_clearance_cm':0}
 n1=cross(sub(a[1],a[0]),sub(a[2],a[0]));n2=cross(sub(b[1],b[0]),sub(b[2],b[0]));direction=cross(n1,n2);length=math.sqrt(dot(direction,direction))
 if not length:return {'segment_length_cm':0,'minimum_interior_edge_clearance_cm':0}
 direction=tuple(x/length for x in direction);av=[dot(p,direction)for p in aa];bv=[dot(p,direction)for p in bb];lo=max(min(av),min(bv));hi=min(max(av),max(bv))
 if hi<=lo:return {'segment_length_cm':0,'minimum_interior_edge_clearance_cm':0}
 i,j=min(range(len(av)),key=av.__getitem__),max(range(len(av)),key=av.__getitem__);fraction=((lo+hi)/2-av[i])/(av[j]-av[i]);point=tuple(x+fraction*(y-x)for x,y in zip(aa[i],aa[j]));clear=min(point_edge_distance(point,t[k],t[(k+1)%3])for t in(a,b)for k in range(3))
 return {'segment_length_cm':hi-lo,'minimum_interior_edge_clearance_cm':clear,'midpoint_cm':point}

def positive_crossing(a,b,eps=CONTACT_EPS_CM):
 aa=signed_distances(a,b);bb=signed_distances(b,a)
 if not(aa and bb and min(aa)<-eps and max(aa)>eps and min(bb)<-eps and max(bb)>eps):return False
 finite=finite_intersection(a,b)
 return finite['segment_length_cm']>eps and finite['minimum_interior_edge_clearance_cm']>eps
def box(tris):return [[f(p[k]for t in tris for p in t)for k in range(3)]for f in(min,max)]
def bounds_overlap(a,b):return all(a[1][k]>=b[0][k]and a[0][k]<=b[1][k]for k in range(3))
def clipping_area(subject,clip):
 # Convex 2D polygon clipping; no ray/contact proxy.
 points=[tuple(p)for p in subject];sign=1 if sum(p[0]*q[1]-p[1]*q[0]for p,q in zip(clip,clip[1:]+clip[:1]))>=0 else -1
 for a,b in zip(clip,clip[1:]+clip[:1]):
  def side(p):return sign*((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]))
  output=[]
  for p,q in zip(points,points[1:]+points[:1]):
   sp,sq=side(p),side(q)
   if sp>=0:output.append(p)
   if (sp>=0)!=(sq>=0):
    t=sp/(sp-sq);output.append(tuple(p[k]+t*(q[k]-p[k])for k in range(2)))
  points=output
  if not points:return 0.
 return abs(sum(p[0]*q[1]-p[1]*q[0]for p,q in zip(points,points[1:]+points[:1])))/2

def plane_patch(part,support,axis,plane):
 axes=[k for k in range(3)if k!=axis]
 def faces(tris):return [[tuple(p[k]for k in axes)for p in t]for t in tris if all(abs(p[axis]-plane)<=CONTACT_EPS_CM for p in t)and math.sqrt(dot(cross(sub(t[1],t[0]),sub(t[2],t[0])),cross(sub(t[1],t[0]),sub(t[2],t[0]))))>0]
 aa,bb=faces(part),faces(support);wanted=sum(clipping_area(t,t)for t in aa);covered=sum(clipping_area(a,b)for a in aa for b in bb)
 return {'axis':axis,'plane_cm':plane,'part_plane_triangles':len(aa),'support_plane_triangles':len(bb),'part_backface_area_cm2':wanted,'support_intersection_area_cm2':covered,'positive_area_supported':wanted>0 and covered>0,'full_backface_supported':wanted>0 and abs(covered-wanted)<=max(.001,wanted*1e-6)}

def source_parts(path,nodes=None):
 from home_asset_audit import read_gltf
 from unreal_import_real_wc import expected_triangles
 d,b=read_gltf(Path(path));parts=[]
 for i,n in enumerate(d['nodes']):
  if'mesh'not in n or (nodes is not None and i not in nodes):continue
  ts=expected_triangles(d,b,i);parts.append({'node':i,'name':n.get('name',''),'triangles':ts,'bounds_cm':box(ts)})
 return d,b,parts

def fixture_parity(old,new):
 from unreal_import_real_kitchen import same_triangles
 unused=set(range(len(new)));rows=[];errors=[]
 for src in old:
  candidates=[j for j in unused if len(new[j]['triangles'])==len(src['triangles'])and max(abs(new[j]['bounds_cm'][0][k]-src['bounds_cm'][0][k])for k in range(3))<=CORNER_TOL_CM]
  matches=[j for j in candidates if same_triangles(src['triangles'],new[j]['triangles'],tolerance_cm=CORNER_TOL_CM)]
  if len(matches)!=1:errors.append({'source':src['name'],'matches':len(matches)});continue
  j=matches[0];unused.remove(j);rows.append({'source_node':src['node'],'source_name':src['name'],'styled_node':new[j]['node'],'styled_name':new[j]['name'],'all_world_triangle_corners_matched':True,'triangles':len(src['triangles'])})
 return {'source_parts':len(old),'styled_parts':len(new),'matched_parts':len(rows),'unmatched_styled_parts':len(unused),'tolerance_cm':CORNER_TOL_CM,'errors':errors,'rows':rows,'ok':len(old)==len(new)==len(rows)==90 and not errors and not unused}

def wood_uv_audit(doc,blob):
 from structural_rail_source_patch import accessor,world_matrices,transformed
 world=world_matrices(doc);rows=[]
 for ni,n in enumerate(doc['nodes']):
  if'mesh'not in n:continue
  for pi,p in enumerate(doc['meshes'][n['mesh']]['primitives']):
   m=doc['materials'][p['material']]
   if m['name']!='TB04':continue
   pts=[transformed(world[ni],v)for v in accessor(doc,blob,p['attributes']['POSITION'])];uv=accessor(doc,blob,p['attributes']['TEXCOORD_0']);ids=[v[0]for v in accessor(doc,blob,p['indices'])];positive=collapsed=0;ratios=[];front_errors=[]
   for ti in range(0,len(ids),3):
    js=ids[ti:ti+3];t=[pts[j]for j in js];norm=cross(sub(t[1],t[0]),sub(t[2],t[0]));a=math.sqrt(dot(norm,norm))
    if not a:continue
    positive+=1;u,v,w=[uv[j]for j in js];ua=abs((v[0]-u[0])*(w[1]-u[1])-(v[1]-u[1])*(w[0]-u[0]));collapsed+=ua==0
    ratios.append(ua*1.83**2/a)
    if abs(norm[0])/a>.999:
     for j in js:front_errors.append(max(abs(uv[j][0]-pts[j][1]/1.83),abs(uv[j][1]-(1-pts[j][2]/1.83))))
   rows.append({'part':n['name'],'node':ni,'primitive':pi,'positive_triangles':positive,'exact_collapsed_uv_positive_triangles':collapsed,'texture_coverage_metres':1.83,'minimum_projected_texel_area_ratio':min(ratios),'maximum_projected_texel_area_ratio':max(ratios),'front_metric_formula_max_uv_error':max(front_errors,default=None),'all_positive_faces_have_uv_area':collapsed==0})
 return rows

def audit(args):
 from mathutils import Vector
 from mathutils.bvhtree import BVHTree
 started=time.monotonic();base=Path(args.style_root);root=Path(args.output);root.mkdir(parents=True,exist_ok=False)
 for path,wanted in [(args.original,FIXTURE_SHA),(args.corridor,CORRIDOR_SHA),(args.doors,DOOR_SHA),(args.home,HOME_SHA)]:assert sha(path)==wanted,'Frozen actual source differs'
 od,ob,old=source_parts(args.original);fd,fb,fixtures=source_parts(base/'bath-style-fixtures.glb');dd,db,dressing=source_parts(base/'bath-style-dressing.glb');cd,cb,architecture=source_parts(args.corridor);hd,hb,home=source_parts(args.home,{0,1,2,3,116});rd,rb,doors=source_parts(args.doors)
 parity=fixture_parity(old,fixtures)
 architecture=[p for p in architecture if p['name'].endswith('_117')or p['name'].endswith('_158')];walls=next(p for p in architecture if p['name'].endswith('_158'))
 # Actual saved source architecture already includes all replacement walls;
 # retained house floor/ceiling surfaces are added without old117/158/118.
 retained=[p for p in home if p['node']in(0,1,2,3,116)]
 obstacles=[dict(p,category='fixture')for p in fixtures]+[dict(p,category='architecture')for p in architecture+retained]+[dict(p,category='real_door')for p in doors]
 def tree(p):
  ts=p['triangles'];points=[Vector(v)for t in ts for v in t];return BVHTree.FromPolygons(points,[tuple(range(i,i+3))for i in range(0,len(points),3)],all_triangles=True,epsilon=0)
 trees={id(p):tree(p)for p in obstacles};intersections=[];positive=[]
 for part in dressing:
  pt=tree(part)
  for other in obstacles:
   if not bounds_overlap(part['bounds_cm'],other['bounds_cm']):continue
   hits=pt.overlap(trees[id(other)])
   if not hits:continue
   crossings=[(a,b)for a,b in hits if positive_crossing(part['triangles'][a],other['triangles'][b])]
   row={'dressing':part['name'],'obstacle':other['name'],'category':other['category'],'surface_contact_pairs':len(hits),'positive_crossing_pairs':len(crossings),'examples':[{'dressing_triangle':a,'obstacle_triangle':b,'finite_intersection':finite_intersection(part['triangles'][a],other['triangles'][b])}for a,b in crossings[:6]]};intersections.append(row)
   if crossings:positive.append(row)
 attachments=[];byname={p['name']:p for p in dressing};fbyname={p['name']:p for p in fixtures}
 plans=[('TB_WestPaintFilm',walls,0,-391),('TB_SouthPaintFilm',walls,1,55),('TB_NorthUpperPaint',walls,1,265),('TB_NorthLeftPaint',walls,1,265)]
 for name,support,axis,plane in plans:attachments.append(dict(part=name,support=support['name'],kind='paint_to_exact_architecture',**plane_patch(byname[name]['triangles'],support['triangles'],axis,plane)))
 for part in dressing:
  if part['name'].startswith('TB_West')and part['name']!='TB_WestPaintFilm':attachments.append(dict(part=part['name'],support='TB_WestPaintFilm',kind='trim_to_paint_front',**plane_patch(part['triangles'],byname['TB_WestPaintFilm']['triangles'],0,-390.95)))
  if part['name'].startswith('TB_MirrorMitre_'):attachments.append(dict(part=part['name'],support='SUB01_vanity_016',kind='moulding_to_actual_existing_backplate_front',**plane_patch(part['triangles'],fbyname['SUB01_vanity_016']['triangles'],0,-386.75)))
 wood=wood_uv_audit(fd,fb)+wood_uv_audit(dd,db)
 report={'schema':'sub01.reference-teal-bathroom-independent-source.v1','inputs':{str(p):sha(p)for p in [args.original,args.corridor,args.doors,args.home,base/'bath-style-fixtures.glb',base/'bath-style-dressing.glb']},'fixture_corner_parity':parity,'dressing_parts':len(dressing),'contact_epsilon_cm':CONTACT_EPS_CM,'all_dressing_obstacle_surface_contacts':intersections,'unresolved_positive_crossings':positive,'attachments':attachments,'wood_uv':wood,'wood_positive_triangles_with_collapsed_uvs':sum(p['exact_collapsed_uv_positive_triangles']for p in wood),'source_ready':parity['ok']and not positive and all(p['full_backface_supported']for p in attachments)and all(p['all_positive_faces_have_uv_area']for p in wood),'source_motion_witness':'Current real-door static geometry checked; dressing never enters actual moving-group AABBs/sweeps to be certified separately before native activation','native_imported':False,'native_visual_physical_accepted':False,'privacy_or_collision_or_activity_gates_changed':False,'elapsed_s':time.monotonic()-started}
 (root/'independent-source-proof.json').write_text(json.dumps(report,indent=2)+'\n');print('TEAL_INDEPENDENT_SOURCE_PROOF',json.dumps({'fixture_parity':parity['ok'],'positive_crossings':positive,'attachments_without_full_support':[p for p in attachments if not p['full_backface_supported']],'collapsed_wood_uv_triangles':report['wood_positive_triangles_with_collapsed_uvs'],'source_ready':report['source_ready']}),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--style-root',required=True);p.add_argument('--original',required=True);p.add_argument('--corridor',required=True);p.add_argument('--doors',required=True);p.add_argument('--home',required=True);p.add_argument('--output',required=True);a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);audit(a)
