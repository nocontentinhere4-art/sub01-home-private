"""Rigid placement of the exact genuine office plant; preserve all other plants."""
import hashlib
from real_linea_lamp_mount import geometry
from pathlib import Path
NODES=(221,222,223,224);ROOT_NODE=225;DELTA=(-.4,0.,-.01)
MESHES={221:165,222:163,223:164,224:162}

def source_plan(home):
 if hashlib.sha256(Path(home).read_bytes()).hexdigest()!='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b':raise ValueError('Actual source identity differs')
 doc,rows=geometry(home);children=doc['nodes'][ROOT_NODE].get('children',[])
 if set(children)!=set(NODES):raise ValueError('Exact office225 parent/221..224 child identities differ; never move kitchen220')
 members=[r for r in rows if r['node']in NODES]
 if len(members)!=4 or any(not doc['nodes'][r['node']].get('name','').endswith('.004')for r in members):raise ValueError('Exact four genuine office plant mesh identities differ')
 plans=[];contacts=[];boundary=[];allpoints=[]
 for row in members:
  old=[(p[0],p[2],p[1])for p in row['points']];new=[tuple(p[a]+DELTA[a]for a in range(3))for p in old];allpoints+=new
  bounds=lambda ps:[[min(p[a]for p in ps)for a in range(3)],[max(p[a]for p in ps)for a in range(3)]]
  for i,t in enumerate(row['triangles']):
   if min(new[v][2]for v in t)>=.845-1e-8 and any(abs(new[v][2]-.845)<=1e-7 for v in t):boundary.append({'node':row['node'],'triangle':i})
   if all(abs(new[v][2]-.845)<=1e-7 for v in t):contacts.append({'node':row['node'],'triangle':i,'points_ue_m':[new[v]for v in t]})
  plans.append({'node':row['node'],'old_bounds_ue_m':bounds(old),'new_bounds_ue_m':bounds(new),'source_triangle_count':len(row['triangles'])})
 if abs(min(p[2]for p in allpoints)-.845)>1e-7 or not contacts:raise ValueError('Actual authored plant base lacks exact tabletop contact faces')
 return {'root_source_node':225,'mesh_source_nodes':list(NODES),'rigid_delta_ue_cm':[v*100 for v in DELTA],'members':plans,'exact_base_contact_faces':contacts,'exact_nonpenetrating_base_boundary_faces':boundary,'geometry_uv_pbr_unchanged':True,'watering_anchor_status':'No watering implementation/coordinate anchor found in local native source; actual interaction acceptance remains unverified'},members


def native_preflight(u,actors,plan,surface,close):
 rows=[]
 for p in plan['members']:
  found=[a for a in actors if a.get_name()=='full-home_node_'+str(p['node'])]
  if len(found)!=1:raise RuntimeError('Exact genuine office plant actor missing')
  actor=found[0];comps=actor.get_components_by_class(u.StaticMeshComponent)
  expected=f'/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Mesh_{MESHES[p["node"]]}.Mesh_{MESHES[p["node"]]}'
  if len(comps)!=1 or comps[0].get_editor_property('static_mesh').get_path_name()!=expected:raise RuntimeError('Exact actual saved office plant mesh identity differs')
  pts,count=surface(u,comps[0]);box=[[min(v[a]for v in pts)for a in range(3)],[max(v[a]for v in pts)for a in range(3)]]
  if count!=p['source_triangle_count']or not all(close(a,[v*100 for v in b])for a,b in zip(box,p['old_bounds_ue_m'])):raise RuntimeError('Actual genuine plant geometry/world bounds differ')
  rows.append((actor,comps[0],p))
 root=[a for a in actors if a.get_name()=='full-home_node_225']
 if len(root)!=1 or root[0].get_components_by_class(u.StaticMeshComponent):raise RuntimeError('Exact empty office parent225 identity differs')
 parents=[a.get_attach_parent_actor()for a,c,p in rows]
 if all(a==root[0]for a in parents):move=[root[0]]
 elif all(a!=root[0]for a in parents):
  if any(a in [r[0]for r in rows]for a in parents):raise RuntimeError('Ambiguous office plant child hierarchy; no double translation')
  move=[root[0]]+[r[0]for r in rows]
 else:raise RuntimeError('Mixed office plant225 attachment; no guessed double translation')
 return {'rows':rows,'move':move,'root':root[0],'plan':plan}
