"""Measured authentic C-clamp side mount; rigidly loosen only authored screw.

Source upper/lower contact faces are measured; no grommet removal, new hole,
mesh welding/deletion or global collision tolerance. Normals/UV/indices unchanged.
"""
import copy,hashlib,json,math,struct
from pathlib import Path
from real_linea_lamp_mount import geometry,rotated_ue
from structural_rail_source_patch import accessor
from home_asset_audit import read_gltf
from prepare_real_linea140_placement import SHA,SCALE,DESK_Y
LAMP_SHA='2ac8389afc1519449a9cfdf7efd9fa36780a2177bb47ab58f7a7dda7d247dc8c'
SCREW_IDS=list(range(16964,18064))
UPPER_IDS=(21348,21349,21350,21377,21378,21399,21400,21401,21402,21403)
UPPER_BOUNDARY_IDS=(20730,20731,20763,20764,20967,20968,20969,20970,21026,21027,21059,21060,21261,21262,21263,21264,21348,21349,21350,21355,21356,21377,21378,21399,21400,21401,21402,21403,21405,21406)


def source_mechanics(lamp):
 if hashlib.sha256(Path(lamp).read_bytes()).hexdigest()!=LAMP_SHA:raise ValueError('Unreviewed original lamp source')
 doc,rows=geometry(lamp);body=rows[0]
 if len(rows)!=2 or len(body['triangles'])!=22598:raise ValueError('Actual complete original clamp/body contract differs')
 selected={v for i in SCREW_IDS for v in body['triangles'][i]}
 other={v for i,t in enumerate(body['triangles'])if i not in set(SCREW_IDS)for v in t}
 if selected&other:raise ValueError('Rigid screw shares vertices with unchanged body')
 pts=[body['points'][i]for i in selected];lo=[min(p[a]for p in pts)for a in range(3)];hi=[max(p[a]for p in pts)for a in range(3)]
 if max(abs(x-y)for x,y in zip(lo,[-.008669286966323853,-.08799377083778381,-.006943501066416502]))>1e-7 or max(abs(x-y)for x,y in zip(hi,[.008669286035001278,-.020163340494036674,.010395070537924767]))>1e-7:raise ValueError('Exact authored threaded screw bounds differ')
 contact=[body['points'][v][1]for i in UPPER_IDS for v in body['triangles'][i]]
 if max(contact)-min(contact)>1e-7:raise ValueError('Authored upper clamp underside is not one flat contact surface')
 upper=sum(contact)/len(contact);cap_ids=[]
 for i in SCREW_IDS:
  p=[body['points'][v]for v in body['triangles'][i]]
  if max(abs(v[1]-hi[1])for v in p)<1e-7:cap_ids.append(i)
 if len(cap_ids)<20:raise ValueError('Actual opposing screw contact cap missing')
 return doc,rows,selected,upper,hi[1],cap_ids


def pose_source(lamp,output,delta):
 doc,rows,selected,upper,lower,caps=source_mechanics(lamp);path=Path(lamp);original=(path.parent/doc['buffers'][0]['uri']).read_bytes();blob=bytearray(original)
 primitive=doc['meshes'][0]['primitives'][0];index=primitive['attributes']['POSITION'];a=doc['accessors'][index];view=doc['bufferViews'][a['bufferView']]
 if a['componentType']!=5126 or a['type']!='VEC3' or view.get('byteStride',12)!=12:raise ValueError('Exact source float position layout differs')
 start=view.get('byteOffset',0)+a.get('byteOffset',0);allowed=set()
 for vertex in selected:
  offset=start+vertex*12+4;y=struct.unpack_from('<f',blob,offset)[0];struct.pack_into('<f',blob,offset,y+delta);allowed.update(range(offset,offset+4))
 if any(original[i]!=blob[i]and i not in allowed for i in range(len(original))):raise ValueError('Normal/UV/other source bytes changed')
 values=accessor(doc,blob,index);a['min']=[min(p[k]for p in values)for k in range(3)];a['max']=[max(p[k]for p in values)for k in range(3)]
 for image in doc['images']:
  data=(path.parent/image.pop('uri')).read_bytes();blob.extend(b'\0'*(-len(blob)%4));offset=len(blob);blob.extend(data);image['bufferView']=len(doc['bufferViews']);doc['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':len(data)})
 doc['buffers']=[{'byteLength':len(blob)}];doc['nodes'][0]['name']='SUB01_RealEdgeClamp_2ac8389_Complete';doc['meshes'][0]['name']='SUB01_RealEdgeClamp_2ac8389_CompleteMesh'
 encoded=json.dumps(doc,separators=(',',':')).encode();encoded+=b' '*(-len(encoded)%4);blob+=b'\0'*(-len(blob)%4)
 out=struct.pack('<4sII',b'glTF',2,28+len(encoded)+len(blob))+struct.pack('<II',len(encoded),0x4E4F534A)+encoded+struct.pack('<II',len(blob),0x004E4942)+blob;Path(output).write_bytes(out)
 return {'sha256':hashlib.sha256(out).hexdigest(),'original_source_sha256':LAMP_SHA,'triangle_count':24102,'rigid_screw_triangle_count':1100,'rigid_screw_triangle_ids':[16964,18063],'rigid_screw_delta_local_y_m':delta,'other_positions_normals_uv_indices_unchanged':True,'material_images_preserved':True,'screw_upper_contact_ids':caps,'upper_jaw_contact_ids':list(UPPER_IDS)}


def mount_plan(desk_path,lamp_path,saved,posed_output,placement_y_cm=None):
 if hashlib.sha256(Path(desk_path).read_bytes()).hexdigest()!=SHA:raise ValueError('Actual desk source differs')
 doc,rows,selected,upper,lower,cap_ids=source_mechanics(lamp_path);actual=saved['planned']['DeskLamp']
 if abs(actual['yaw_deg']-90)>1e-6:raise ValueError('Actual native lamp yaw changed')
 _,desk=geometry(desk_path);work=[p for r in desk if r['node']==44 for p in r['points']];top=.025+max(p[1]for p in work)*SCALE;bottom=.025+min(p[1]for p in work)*SCALE;thickness=top-bottom
 screw_delta=upper-thickness-.00002-lower # measured underscrew contact,20micrometre no-penetration gap
 pose=pose_source(lamp_path,posed_output,screw_delta);edge_x=2.1+min(p[0]for p in work)*SCALE;edge_source_z=.0175
 origin=[edge_x+edge_source_z,(actual['location_cm'][1]if placement_y_cm is None else placement_y_cm)/100,top-upper]
 old=[x/100 for x in actual['location_cm']];delta=[(origin[a]-old[a])*100 for a in range(3)];bulb=[actual['bulb_cm'][a]+delta[a]for a in range(3)]
 newrows=geometry(posed_output)[1];newpts=[tuple(origin[a]+rotated_ue(p)[a]for a in range(3))for r in newrows for p in r['points']]
 oldpts=[tuple(old[a]+rotated_ue(p)[a]for a in range(3))for r in rows for p in r['points']]
 jaw=[rows[0]['points'][v]for i in UPPER_IDS for v in rows[0]['triangles'][i]]
 if sum(origin[0]-p[2]for p in jaw)/len(jaw)<edge_x+.005:raise ValueError('Actual jaw centre is not supported inside desk edge')
 support=contact_coverage(rows[0],desk,origin,top)
 if support['actual_flat_wood_contact_fraction']<.85:raise ValueError('Actual upper jaw has less than85% flat wood contact')
 return {'schema':'sub01.real-linea-edge-clamp-mount.v1','mount_mechanism':'C-clamp-side-edge','desk_source_sha256':SHA,'lamp_source_sha256':LAMP_SHA,'posed_lamp_glb':str(posed_output),'posed_lamp':pose,'actual_saved_lamp_actor':actual['actor'],'actual_saved_material_paths':[m['material']for m in actual['materials']],'actual_saved_origin_cm':actual['location_cm'],'actual_saved_yaw_deg':90,'new_origin_ue_cm':[v*100 for v in origin],'geometry_delta_ue_cm':delta,'new_bulb_ue_cm':bulb,'actual_old_light_ue_cm':actual['light_cm'],'light_delta_ue_cm':[bulb[a]-actual['light_cm'][a]for a in range(3)],'light_actor_label_for_exact_component_preflight':'SUB01_AuthoredLight_DeskLamp','opened_hardware_source_nodes':[],'preserved_grommet_source_nodes':[7,8,35],'wood_top_world_m':top,'wood_bottom_world_m':bottom,'wood_thickness_m':thickness,'upper_jaw_contact_local_y_m':upper,'original_screw_top_y_m':lower,'actual_closed_opening_m':upper-lower,'screw_contact_gap_m':.00002,'upper_jaw_contact_triangle_ids':list(UPPER_IDS),'upper_jaw_nonpenetrating_boundary_ids':list(UPPER_BOUNDARY_IDS),'actual_jaw_support':support,'screw_contact_triangle_ids':cap_ids,'old_native_aabb_cm':[[min(p[a]for p in oldpts)*100 for a in range(3)],[max(p[a]for p in oldpts)*100 for a in range(3)]],'lamp_world_aabb_m':[[min(p[a]for p in newpts)for a in range(3)],[max(p[a]for p in newpts)for a in range(3)]],'lamp_source_triangle_count':24102,'collision_proof_required':True,'native_ready':False}


def contact_coverage(lamp,desk,origin,top):
 # Exact projected triangle intersection measures the real flat support area.
 def signed(poly):return sum(poly[i][0]*poly[(i+1)%len(poly)][1]-poly[(i+1)%len(poly)][0]*poly[i][1]for i in range(len(poly)))/2
 def clip(subject,border):
  if signed(border)<0:border=list(reversed(border))
  for a,b in zip(border,border[1:]+border[:1]):
   old=subject;subject=[]
   if not old:break
   def side(p):return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
   for prev,cur in zip(old[-1:]+old[:-1],old):
    sp,sc=side(prev),side(cur)
    if (sp>=0)!=(sc>=0):
     t=sp/(sp-sc);subject.append((prev[0]+t*(cur[0]-prev[0]),prev[1]+t*(cur[1]-prev[1])))
    if sc>=0:subject.append(cur)
  return abs(signed(subject))if len(subject)>=3 else 0
 wood=[]
 for r in desk:
  if r['node']!=44:continue
  pts=[(2.1+p[0]*SCALE,DESK_Y+p[2]*SCALE,.025+p[1]*SCALE)for p in r['points']]
  for t in r['triangles']:
   if all(abs(pts[v][2]-top)<1e-8 for v in t):wood.append([pts[v][:2]for v in t])
 total=covered=0
 for i in UPPER_IDS:
  triangle=[tuple(origin[a]+rotated_ue(lamp['points'][v])[a]for a in range(2))for v in lamp['triangles'][i]]
  total+=abs(signed(triangle));covered+=sum(clip(triangle,w)for w in wood)
 if not total or covered>total*1.000001:raise ValueError('Actual flat jaw/wood support area invalid')
 return {'actual_flat_wood_contact_fraction':covered/total,'jaw_area_m2':total,'supported_area_m2':covered,'unsupported_edge_area_m2':total-covered,'method':'Exact source contact triangles clipped against actual node44 flat top triangles; unsupported rounded edge reported'}


def blender_collision_proof(desk_path,posed_lamp,plan,home_path):
 from mathutils.bvhtree import BVHTree
 from mathutils import Vector
 if hashlib.sha256(Path(home_path).read_bytes()).hexdigest()!='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b':raise ValueError('Actual home source differs')
 _,desk=geometry(desk_path);_,lamp=geometry(posed_lamp);_,home=geometry(home_path);origin=[v/100 for v in plan['new_origin_ue_cm']]
 def bvh(points,faces):return BVHTree.FromPolygons([Vector(p)for p in points],faces,all_triangles=True,epsilon=0)
 cached_home=[]
 for r in home:
  if r['node']in(162,181,182,126,255,256):continue
  faces=r['triangles']
  if r['node']==163:
   if len(faces)!=1840:raise ValueError('Exact retired rail/stem union source count differs')
   faces=faces[1640:1800] # reviewed exact160 preserved triangles; never ignore broad batch
  cached_home.append((r['node'],bvh([(p[0],p[2],p[1])for p in r['points']],faces)))
 issues=[];contacts=0
 for lr in lamp:
  lpts=[tuple(origin[a]+rotated_ue(p)[a]for a in range(3))for p in lr['points']];lb=bvh(lpts,lr['triangles'])
  for dr in desk:
   dpts=[(2.1+p[0]*SCALE,DESK_Y+p[2]*SCALE,.025+p[1]*SCALE)for p in dr['points']]
   for li,di in lb.overlap(bvh(dpts,dr['triangles'])):
    lp=[lpts[k]for k in lr['triangles'][li]];dp=[dpts[k]for k in dr['triangles'][di]]
    top_ok=lr['primitive']==0 and li in plan['upper_jaw_nonpenetrating_boundary_ids'] and min(p[2]for p in lp)>=plan['wood_top_world_m']-1e-8 and all(abs(p[2]-plan['wood_top_world_m'])<=1e-8 for p in dp)
    screw_ok=lr['primitive']==0 and li in plan['screw_contact_triangle_ids'] and all(abs(p[2]-plan['wood_bottom_world_m'])<=.00003 for p in lp+dp)
    if dr['node']==44 and (top_ok or screw_ok):contacts+=1
    else:issues.append({'lamp_triangle':li,'desk_node':dr['node'],'desk_triangle':di})
  for node,hb in cached_home:
   hits=lb.overlap(hb)
   if hits:issues.append({'home_node':node,'triangle_pairs':len(hits)})
 return {'ok':not issues,'issues':issues[:100],'allowed_exact_measured_jaw_screw_contact_pairs':contacts,'epsilon':0,'proof':'Whole source triangle BVH. Only explicitly measured upper-jaw/screw-cap faces coplanar with actual wood surfaces accepted; no face band exemption.'}
