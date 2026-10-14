"""Actual source-vertex grommet mount plan; Blender collision proof runs only on pod."""
import hashlib,json,math
from pathlib import Path
from home_asset_audit import read_gltf
from structural_rail_source_patch import accessor,world_matrices,transformed
from prepare_real_linea140_placement import SHA,SCALE,DESK_Y


def geometry(path):
 path=Path(path);doc,binary=read_gltf(path)
 if binary is None:binary=(path.parent/doc['buffers'][0]['uri']).read_bytes()
 matrices=world_matrices(doc);rows=[]
 for ni,node in enumerate(doc['nodes']):
  if 'mesh' not in node:continue
  for pi,p in enumerate(doc['meshes'][node['mesh']]['primitives']):
   pts=[transformed(matrices[ni],x)for x in accessor(doc,binary,p['attributes']['POSITION'])]
   ids=[x[0]for x in accessor(doc,binary,p['indices'])]
   rows.append({'node':ni,'primitive':pi,'material':doc['materials'][p['material']]['name'],'points':pts,'triangles':[ids[i:i+3]for i in range(0,len(ids),3)]})
 return doc,rows


def rotated_ue(p):return (-p[2],p[0],p[1]) # actual saved UE yaw90 and glTF(x,z,y) basis


def mount_plan(desk_path,lamp_path,saved_receipt):
 if hashlib.sha256(Path(desk_path).read_bytes()).hexdigest()!=SHA:raise ValueError('Unreviewed real desk source')
 _,desk=geometry(desk_path);_,lamp=geometry(lamp_path)
 body=[p for r in lamp if 'light' not in r['material'].lower() for p in r['points']]
 pin=[p for p in body if -.031<=p[1]<-.0001]
 if not pin:raise ValueError('Actual through-top pin absent')
 pmin=[min(p[a]for p in pin)for a in range(3)];pmax=[max(p[a]for p in pin)for a in range(3)]
 centre=[(pmin[a]+pmax[a])/2 for a in range(3)]
 actual=saved_receipt['planned']['DeskLamp']
 if abs(actual['yaw_deg']-90)>1e-6:raise ValueError('Actual lamp yaw differs reviewed90')
 hole=[2.1-.47*SCALE,DESK_Y-.22*SCALE];rot=rotated_ue(centre)
 rim=[p for r in desk if r['node']==35 for p in r['points']]
 rest=.025+max(p[1]for p in rim)*SCALE
 origin=[hole[0]-rot[0],hole[1]-rot[1],rest]
 old=[v/100 for v in actual['location_cm']]
 newpoints=[tuple(origin[a]+rotated_ue(p)[a] for a in range(3))for r in lamp for p in r['points']]
 through_radius=max(math.hypot(p[0]-centre[0],p[2]-centre[2])for p in pin)
 radius_min=min(math.hypot(p[0]+.47,p[2]+.22)for p in rim)*SCALE
 clearance=radius_min-through_radius
 if clearance<.002:raise ValueError('Actual lamp pin has less than2mm actual grommet radial clearance')
 bulb_old=actual['bulb_cm'];delta=[origin[a]*100-actual['location_cm'][a]for a in range(3)]
 bulb=[bulb_old[a]+delta[a]for a in range(3)]
 light_delta=[bulb[a]-actual['light_cm'][a]for a in range(3)]
 return {'schema':'sub01.real-linea-grommet-lamp-mount.v1','desk_source_sha256':SHA,'lamp_source_sha256':hashlib.sha256(Path(lamp_path).read_bytes()).hexdigest(),'actual_saved_lamp_actor':actual['actor'],'actual_saved_material_paths':[m['material']for m in actual['materials']],'actual_saved_origin_cm':actual['location_cm'],'actual_saved_yaw_deg':90,'new_origin_ue_cm':[x*100 for x in origin],'geometry_delta_ue_cm':delta,'new_bulb_ue_cm':bulb,'light_delta_ue_cm':light_delta,'actual_old_light_ue_cm':actual['light_cm'],'light_actor_label_for_exact_component_preflight':'SUB01_AuthoredLight_DeskLamp','opened_cap_source_node':8,'worktop_source_node':44,'grommet_rim_source_node':35,'radial_pin_clearance_m':clearance,'lamp_world_aabb_m':[[min(p[a]for p in newpoints)for a in range(3)],[max(p[a]for p in newpoints)for a in range(3)]],'contact_tolerance_m':.002,'collision_proof_required':True,'lamp_source_triangle_count':sum(len(r['triangles'])for r in lamp),'old_native_aabb_cm':[[min(rotated_ue(p)[a]+old[a] for r in lamp for p in r['points'])*100 for a in range(3)],[max(rotated_ue(p)[a]+old[a] for r in lamp for p in r['points'])*100 for a in range(3)]],'native_ready':False}


def blender_collision_proof(desk_path,lamp_path,plan,home_path):
 from mathutils.bvhtree import BVHTree
 from mathutils import Vector
 if hashlib.sha256(Path(home_path).read_bytes()).hexdigest()!='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b':raise ValueError('Unreviewed full home source')
 _,desk=geometry(desk_path);_,lamp=geometry(lamp_path);_,home=geometry(home_path)
 origin=[x/100 for x in plan['new_origin_ue_cm']]
 def bvh(points,faces):return BVHTree.FromPolygons([Vector(p)for p in points],faces,all_triangles=True,epsilon=0)
 issues=[];contact_pairs=0
 for lr in lamp:
  lpts=[tuple(origin[a]+rotated_ue(p)[a]for a in range(3))for p in lr['points']];lb=bvh(lpts,lr['triangles'])
  for dr in desk:
   if dr['node']==8:continue # exact physically opened removable grommet lid, retained source asset
   dpts=[(2.1+p[0]*SCALE,DESK_Y+p[2]*SCALE,.025+p[1]*SCALE)for p in dr['points']]
   for li,di in lb.overlap(bvh(dpts,dr['triangles'])):
    local=[lr['points'][k][1]for k in lr['triangles'][li]]
    if dr['node']==35 and min(local)>=-.002 and max(local)<=.03:contact_pairs+=1
    else:issues.append({'lamp_triangle':li,'desk_node':dr['node'],'desk_triangle':di})
  for hr in home:
   if hr['node'] in (181,182,255,256,126):continue # exact retired original desks/lamps only
   hpts=[(p[0],p[2],p[1])for p in hr['points']]
   hits=lb.overlap(bvh(hpts,hr['triangles']))
   if hits:issues.append({'home_node':hr['node'],'triangle_pairs':len(hits)})
 return {'ok':not issues,'issues':issues[:100],'allowed_measured_flange_rim_contact_pairs':contact_pairs,'opened_exact_source_cap':8,'radial_pin_clearance_m':plan['radial_pin_clearance_m'],'proof':'Actual source triangle BVH, every other full-home node preserved; only exact retired desk and lamp nodes exempt'}
