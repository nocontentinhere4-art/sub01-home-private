"""Read only exact955 window/wall sections; no scene/editor/geometry mutation."""
import argparse,hashlib,json,math
from pathlib import Path
from home_asset_audit import read_gltf
from structural_rail_source_patch import accessor,world_matrices,transformed

SOURCE_SHA='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
FRAME_GROUPS={'west_south':[5,6,7,8,9],'west_middle':[11,12,13,14,15],'west_north':[17,18,19,20,21],'front_west':[23,24,25,26,27],'front_middle':[29,30,31,32,33],'front_east':[35,36,37,38,39]}


def merge_intervals(rows,tolerance=1e-5):
 result=[]
 for a,b in sorted(rows):
  if b-a<=tolerance:continue
  if result and a<=result[-1][1]+tolerance:result[-1][1]=max(result[-1][1],b)
  else:result.append([a,b])
 return result


def triangle_slice(triangle,constant_axis,value,result_axis):
 hits=[]
 for a,b in zip(triangle,triangle[1:]+triangle[:1]):
  da,db=a[constant_axis]-value,b[constant_axis]-value
  if abs(da)<=1e-7:hits.append(a[result_axis])
  if da*db<0:hits.append(a[result_axis]+(b[result_axis]-a[result_axis])*(-da)/(db-da))
 return None if len(hits)<2 else [min(hits),max(hits)]


def run(source,output):
 if hashlib.sha256(Path(source).read_bytes()).hexdigest()!=SOURCE_SHA:raise ValueError('Exact original955source required')
 doc,binary=read_gltf(Path(source));matrices=world_matrices(doc)
 def geometry(ni):
  node=doc['nodes'][ni];primitives=doc['meshes'][node['mesh']]['primitives'];triangles=[];materials=[]
  for pi,p in enumerate(primitives):
   if p.get('mode',4)!=4:raise ValueError('Actual source triangles required')
   pts=[transformed(matrices[ni],v)for v in accessor(doc,binary,p['attributes']['POSITION'])];pts=[(p[0]*100,p[2]*100,p[1]*100)for p in pts];indices=[int(v[0])for v in accessor(doc,binary,p['indices'])]
   triangles.extend(tuple(pts[j]for j in indices[i:i+3])for i in range(0,len(indices),3));materials.append({'primitive':pi,'material_index':p.get('material'),'material_name':doc['materials'][p['material']].get('name'),'triangles':len(indices)//3})
  return triangles,materials
 wall,wall_materials=geometry(158);frames={}
 for name,nodes in FRAME_GROUPS.items():
  rows=[]
  for ni in nodes:
   triangles,materials=geometry(ni);points=[p for t in triangles for p in t];lo=[min(p[i]for p in points)for i in range(3)];hi=[max(p[i]for p in points)for i in range(3)];rows.append({'node':ni,'mesh':doc['nodes'][ni]['mesh'],'name':doc['nodes'][ni].get('name'),'materials':materials,'bounds_ue_cm':[lo,hi]})
  frames[name]=rows
 profiles={}
 for facade,axis,inner,outer,along,centres in [('west',0,-391.,-409.,1,[-260.,0.,260.]),('front',1,391.,409.,0,[-320.,-200.,65.,200.,325.])]:
  profiles[facade]={}
  for face,plane in [('inner',inner),('outer',outer)]:
   selected=[t for t in wall if all(abs(p[axis]-plane)<.01 for p in t)];horizontal={};vertical={}
   for z in [67.5,70.1,170.,250.,257.4,257.6,270.,310.,320.,445.,544.9,545.1,570.]:
    horizontal[str(z)]=merge_intervals([s for t in selected if(s:=triangle_slice(t,2,z,along))is not None])
   for c in centres:
    vertical[str(c)]=merge_intervals([s for t in selected if(s:=triangle_slice(t,along,c,2))is not None])
   profiles[facade][face]={'plane_ue_cm':plane,'plane_query_tolerance_cm':.01,'coplanar_wall_triangles':len(selected),'horizontal_solid_face_intervals_by_height_cm':horizontal,'vertical_solid_face_intervals_by_along_cm':vertical}
 upper=[]
 for ni in range(41,49):
  tris,mats=geometry(ni);pts=[p for t in tris for p in t];upper.append({'node':ni,'mesh':doc['nodes'][ni]['mesh'],'bounds_ue_cm':[[min(p[i]for p in pts)for i in range(3)],[max(p[i]for p in pts)for i in range(3)]],'materials':mats})
 result={'schema':'sub01.actual-window-aperture-source-survey.v1','source_sha256':SOURCE_SHA,'protected_wall_node':158,'wall_materials':wall_materials,'wall_triangles':len(wall),'lower_frame_groups':frames,'upper_door_owner_boundary_nodes':upper,'exact_wall_face_sections':profiles,'caveats':['Coplanar surface intervals are exact face sections, not a complete volume containment proof','Frame/door fit and unchanged protected geometry require later fullsource BVH before export acceptance','Existing source glass may be runtime-only; fullsource material inventory and currentnative material state are separate'],'source_changed':False,'native_changed':False,'source_ready':False,'native_ready':False};Path(output).write_text(json.dumps(result,indent=2)+'\n');return result

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True);a=p.parse_args();r=run(a.source,a.output);print(json.dumps({'source_sha256':r['source_sha256'],'wall_triangles':r['wall_triangles'],'frames':len(r['lower_frame_groups']),'native_changed':False}))
