"""Independent read-only world-space source rig audit. Never accepts hand contact."""
import bpy,bmesh,json,math
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree
def dominant_bones(obj,indices):
 from collections import Counter
 weights=Counter()
 for i in indices:
  for group in obj.data.vertices[i].groups:weights[obj.vertex_groups[group.group].name]+=group.weight/len(indices)
 return weights.most_common(4)

def audit_motion():
 import sys,hashlib,numpy as np,argparse
 parser=argparse.ArgumentParser();parser.add_argument('--motion',action='store_true');parser.add_argument('--source',type=Path,default=Path('/home/unreal/runtime-tools/official-hands-walk-candidate-r8.glb'));parser.add_argument('--sha256',default='3b1660eacf58203f3e87dfa2fa00799c27d104306bf5370c9fce2fa82fee3862');parser.add_argument('--output',type=Path,default=Path('/workspace/sub01-home-private/human-base-hands-r1/rig-r8-motion-independent-audit.json'))
 argv=sys.argv[sys.argv.index('--')+1:] if '--'in sys.argv else sys.argv[1:];args=parser.parse_args(argv);source,out=args.source,args.output
 assert hashlib.sha256(source.read_bytes()).hexdigest()==args.sha256
 bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene;scene.render.fps=30;bpy.ops.import_scene.gltf(filepath=str(source));arm=next(o for o in scene.objects if o.type=='ARMATURE');assert len(arm.data.bones)==44
 arm.animation_data_create();arm.animation_data.action=list(bpy.data.actions)[0]
 for track in arm.animation_data.nla_tracks:track.mute=True
 meshes=[o for o in scene.objects if o.type=='MESH'and o.name.startswith('CC0Adult_')];assert len(meshes)==2
 glyphs={p.custom_shape for p in arm.pose.bones if p.custom_shape};assert all(o in glyphs for o in scene.objects if o.type=='MESH'and o not in meshes)
 base={};depsgraph=bpy.context.evaluated_depsgraph_get()
 for o in meshes:
  o.data.calc_loop_triangles();triangles=[tuple(t.vertices)for t in o.data.loop_triangles];edge=np.array([tuple(e.vertices)for e in o.data.edges],dtype=np.int64);pts=np.array([list(o.matrix_world@v.co)for v in o.data.vertices]);lengths=np.linalg.norm(pts[edge[:,1]]-pts[edge[:,0]],axis=1);base[o.name]={'triangles':triangles,'triangle_sets':[set(t)for t in triangles],'edges':edge,'edge_lengths':lengths}
 result={'schema':'sub01.actual-captured-hand-motion-independent-audit.v1','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'source_animations_used':True,'action_frame_range':list(arm.animation_data.action.frame_range),'fps':30,'samples':32,'frame_records':[],'self_overlap_method':'Complete evaluated triangle BVH overlap, excluding only identical/shared-vertex topology pairs; remaining pairs are conservative candidates, not silently waived','native_imported':False,'visual_accepted':False,'self_contact_accepted':False,'prop_contact_verified':False,'prop_contact_limitation':'No actual keyboard/controller/phone prop in this captured walk source'}
 for frame in range(32):
  scene.frame_set(frame);bpy.context.view_layer.update();trees=[];record={'frame':frame,'time_s':frame/30,'hands':[]}
  for o in meshes:
   evaluated=o.evaluated_get(depsgraph);mesh=evaluated.to_mesh();assert len(mesh.vertices)==len(o.data.vertices);points=[evaluated.matrix_world@v.co for v in mesh.vertices];assert all(math.isfinite(x)for v in points for x in v);d=base[o.name];tree=BVHTree.FromPolygons(points,d['triangles'],all_triangles=True,epsilon=0);raw=tree.overlap(tree);nonadj=[];excluded=0
   for a,b in raw:
    if a>=b:continue
    if d['triangle_sets'][a].intersection(d['triangle_sets'][b]):excluded+=1;continue
    nonadj.append((a,b))
   positions=np.array([list(p)for p in points]);edge=d['edges'];valid=d['edge_lengths']>1e-6;ratios=np.linalg.norm(positions[edge[:,1]]-positions[edge[:,0]],axis=1)[valid]/d['edge_lengths'][valid]
   record['hands'].append({'mesh':o.name,'vertices':len(points),'triangles':len(d['triangles']),'raw_self_bvh_pairs':len(raw),'topologically_adjacent_pairs_excluded':excluded,'nonadjacent_self_overlap_candidates':len(nonadj),'first_nonadjacent_triangle_pairs':nonadj[:40],'first_overlap_regions':[{'triangles':[a,b],'dominant_bones':dominant_bones(o,d['triangles'][a]+d['triangles'][b]),'centroids_world':[[float(x)for x in sum((points[i]for i in d['triangles'][j]),Vector())/3]for j in(a,b)]}for a,b in nonadj[:40]],'edge_stretch_ratio_median':float(np.median(ratios)),'edge_stretch_ratio_p99':float(np.quantile(ratios,.99)),'edge_stretch_ratio_max':float(max(ratios)),'source_edges_under_1um_excluded_from_ratio':int(sum(~valid)),'bounds_world':[[min(p[k]for p in points)for k in range(3)],[max(p[k]for p in points)for k in range(3)]]});trees.append(tree);evaluated.to_mesh_clear()
  record['between_hands_surface_overlap_candidates']=len(trees[0].overlap(trees[1]));result['frame_records'].append(record);out.write_text(json.dumps(result,indent=2)+'\n');print('ACTUAL_MOTION_AUDIT_FRAME',frame,[h['nonadjacent_self_overlap_candidates']for h in record['hands']],record['between_hands_surface_overlap_candidates'],flush=True)
 result['complete_all_source_integer_frames']=len(result['frame_records'])==32;result['any_surface_overlap_candidates']=any(f['between_hands_surface_overlap_candidates']or any(h['nonadjacent_self_overlap_candidates']for h in f['hands'])for f in result['frame_records']);out.write_text(json.dumps(result,indent=2)+'\n');print('ACTUAL_MOTION_AUDIT_COMPLETE',result['any_surface_overlap_candidates'],flush=True)
import sys
if '--motion'in sys.argv:
 audit_motion();raise SystemExit(0)
ROOT=Path('/workspace/sub01-home-private/human-base-hands-r1')
INPUT=ROOT/'rig-r8/official-adult-hand-pair-rig.blend'
OUT=ROOT/'rig-r8-independent-audit.json'
bpy.ops.wm.open_mainfile(filepath=str(INPUT))
rig=bpy.data.objects['CC0AnatomicalHandRig'];result={'schema':'sub01.official-hand-independent-rig-audit.v1','source_blend':str(INPUT),'read_only':True,'accepted':False,'sides':{}}
directions=[Vector((1,.179,.317)).normalized(),Vector((.237,1,.119)).normalized(),Vector((.131,.229,1)).normalized()]
for side in('Left','Right'):
 o=bpy.data.objects['CC0Adult_'+side+'_ForearmHand_SOURCE_UNRIGGED'];bm=bmesh.new();bm.from_mesh(o.data);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=1e-7);boundary=[e for e in bm.edges if e.is_boundary];n_boundary=len(boundary);bmesh.ops.holes_fill(bm,edges=boundary,sides=0);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.verts.ensure_lookup_table();verts=[o.matrix_world@v.co for v in bm.verts];faces=[[v.index for v in f.verts]for f in bm.faces];closed=not any(not e.is_manifold for e in bm.edges);tree=BVHTree.FromPolygons(verts,faces,all_triangles=False,epsilon=0);volume=bm.calc_volume(signed=True);bm.free()
 def inside(p):
  votes=[];dist=tree.find_nearest(p)[3]
  for direction in directions:
   start=p.copy();hits=0
   for _ in range(100):
    hit,normal,index,length=tree.ray_cast(start,direction,2)
    if hit is None:break
    hits+=1;start=hit+direction*1e-5
   votes.append(bool(hits%2))
  return {'inside_majority':sum(votes)>=2,'ray_inside_votes':votes,'nearest_skin_m':dist}
 bones=[]
 for b in rig.data.bones:
  if not b.name.startswith('mixamorig:'+side)or b.name.endswith('4'):continue
  head=rig.matrix_world@b.head_local;tail=rig.matrix_world@b.tail_local
  probes=[{'t':t,'position':list(head.lerp(tail,t)),**inside(head.lerp(tail,t))}for t in(0,.05,.25,.5,.75,.95,1)]
  bones.append({'name':b.name,'head_world':list(head),'tail_world':list(tail),'length_m':(tail-head).length,'deform':b.use_deform,'probes':probes,'interior_fraction':sum(p['inside_majority']for p in probes)/len(probes)})
 weights=[];wrong_side=0
 for v in o.data.vertices:
  assignments=[(o.vertex_groups[g.group].name,g.weight)for g in v.groups if g.weight>1e-8];weights.append(sum(w for _,w in assignments));wrong_side+=int(any(not name.startswith('mixamorig:'+side)for name,weight in assignments))
 # Independent finger identity from actual disconnected skin branches below palm.
 active={v.index for v in o.data.vertices if (o.matrix_world@v.co).z<.79};adj={i:set()for i in active}
 for edge in o.data.edges:
  a,b=edge.vertices
  if a in active and b in active:adj[a].add(b);adj[b].add(a)
 components=[]
 while active:
  first=active.pop();stack=[first];found=[first]
  while stack:
   for j in adj[stack.pop()]:
    if j in active:active.remove(j);stack.append(j);found.append(j)
  if len(found)<40:continue
  points=[o.matrix_world@o.data.vertices[i].co for i in found];slices=[]
  for z in(.78,.76,.74,.72):
   band=[p for p in points if abs(p.z-z)<.0015]
   if band:slices.append({'z_m':z,'surface_samples':len(band),'x_mid_extent_m':(min(p.x for p in band)+max(p.x for p in band))/2,'y_mid_extent_m':(min(p.y for p in band)+max(p.y for p in band))/2})
  components.append({'vertices':len(found),'bounds_world':[[min(p[k]for p in points)for k in range(3)],[max(p[k]for p in points)for k in range(3)]],'mean_y_m':sum(p.y for p in points)/len(points),'crosssection_extent_centers':slices})
 components.sort(key=lambda c:c['mean_y_m'])
 if len(components)==4:
  for c,label in zip(components,('Index','Middle','Ring','Pinky')):c['tentative_identity_from_actual_skin_y_order']=label
 else:
  for c in components:c['identity_unresolved_wrong_branch_count']=True
 result['sides'][side]={'mesh_world_matrix':[list(r)for r in o.matrix_world],'rig_world_matrix':[list(r)for r in rig.matrix_world],'bounds_world':[[min(p[k]for p in verts)for k in range(3)],[max(p[k]for p in verts)for k in range(3)]],'mesh_vertices':len(o.data.vertices),'temporary_analysis_cuff_boundary_edges_closed':n_boundary,'analysis_domain_closed':closed,'analysis_signed_volume_local':volume,'bone_probes':bones,'actual_skin_finger_branches_below_z079':components,'vertices_with_positive_weight':sum(w>0 for w in weights),'zero_weight_vertices':sum(w<=0 for w in weights),'wrong_side_weight_vertices':wrong_side,'max_positive_weight_sum_error':max((abs(w-1)for w in weights if w>0),default=None)}
OUT.write_text(json.dumps(result,indent=2)+'\n')
for side,row in result['sides'].items():
 print('INDEPENDENT_ANATOMY_AUDIT',side,'closed',row['analysis_domain_closed'],'weighted',row['vertices_with_positive_weight'],'/',row['mesh_vertices'],flush=True)
 for b in row['bone_probes']:
  print(b['name'],'inside',b['interior_fraction'],'head/tail_skin_mm',[round(b['probes'][i]['nearest_skin_m']*1000,3)for i in(0,-1)],'outside_t',[p['t']for p in b['probes']if not p['inside_majority']],flush=True)
