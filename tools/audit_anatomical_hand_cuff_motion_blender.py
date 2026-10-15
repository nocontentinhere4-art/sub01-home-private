"""Independent evaluated-surface audit of saved actual anatomical cuff candidate.
Read-only source scene; no native input and no collision/contact acceptance waiver.
"""
import bpy,json,sys,math,hashlib
from pathlib import Path
from mathutils.bvhtree import BVHTree
source,out=map(Path,sys.argv[sys.argv.index('--')+1:]);bpy.ops.wm.open_mainfile(filepath=str(source));scene=bpy.context.scene;assert scene.render.fps==30
body=next(o for o in scene.objects if o.type=='ARMATURE'and len(o.data.bones)==65);hands={side:bpy.data.objects['CC0Adult_'+side+'_ForearmHand_SOURCE_UNRIGGED']for side in ['Left','Right']};cuffs={side:bpy.data.objects['AnatomicalFittedHoodieCuff'+side]for side in hands};depsgraph=bpy.context.evaluated_depsgraph_get()
result={'schema':'sub01.actual-anatomical-cuff-motion-audit.v1','source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'actual_saved_scene_constraints_used':True,'frames':[],'contact_accepted':False,'native_imported':False,'device_contact_verified':False,'method':'All evaluated surface triangle BVH overlaps; no intersecting pairs silently ignored. Vertex-to-opposite-surface distance is sampled and does not prove continuous clearance.'}
def actual_surface(o):
 evaluated=o.evaluated_get(depsgraph);mesh=evaluated.to_mesh();mesh.calc_loop_triangles();points=[evaluated.matrix_world@v.co for v in mesh.vertices];triangles=[tuple(t.vertices)for t in mesh.loop_triangles];assert all(math.isfinite(x)for p in points for x in p);tree=BVHTree.FromPolygons(points,triangles,all_triangles=True,epsilon=0);evaluated.to_mesh_clear();return tree,points,triangles
for frame in range(32):
 scene.frame_set(frame);bpy.context.view_layer.update();record={'frame':frame,'sides':{}};skin={side:actual_surface(o)for side,o in hands.items()};garments={side:actual_surface(o)for side,o in cuffs.items()}
 for side in hands:
  sk,sp,st=skin[side];cl,cp,ct=garments[side];overlaps=sk.overlap(cl);distances=[sk.find_nearest(p)[3]for p in cp];assert all(d is not None and math.isfinite(d)for d in distances)
  rig=hands[side].parent;constraint=rig.constraints.get('ActualCapturedOwnerHandMount'+side);assert constraint and constraint.target==body and constraint.subtarget=='mixamorig:'+side+'Hand'
  record['sides'][side]={'skin_triangles':len(st),'garment_triangles':len(ct),'surface_intersection_candidate_pairs':len(overlaps),'first_candidate_pairs':overlaps[:24],'minimum_garment_vertex_to_skin_distance_m':min(distances),'maximum_garment_vertex_to_skin_distance_m':max(distances),'exact_live_bone_attachment_present':True}
 record['opposite_skin_cuff_pairs']={side:len(skin[side][0].overlap(garments['Right'if side=='Left'else'Left'][0]))for side in hands};result['frames'].append(record);out.write_text(json.dumps(result,indent=2)+'\n');print('ACTUAL_CUFF_FRAME',frame,{side:record['sides'][side]['surface_intersection_candidate_pairs']for side in hands},flush=True)
result['all32_source_frames_completed']=True;result['any_skin_cuff_intersection_candidates']=any(s['surface_intersection_candidate_pairs']for f in result['frames']for s in f['sides'].values());result['body_or_sewn_seam_collision_verified']=False;result['continuous_motion_clearance_verified']=False;out.write_text(json.dumps(result,indent=2)+'\n');print('ACTUAL_CUFF_AUDIT_COMPLETE',result['any_skin_cuff_intersection_candidates'],flush=True)
