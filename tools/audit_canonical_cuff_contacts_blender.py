"""Actual triangle surface check, canonical static source only."""
import bpy,json
from pathlib import Path
from mathutils.bvhtree import BVHTree
from mathutils import Vector
R=Path('/workspace/sub01-home-private/human-base-hands-r1/canonical-hand-cuffs-r1');bpy.ops.wm.open_mainfile(filepath=str(R/'canonical-anatomical-hand-cuffs.blend'))
def tree(o):
 o.data.calc_loop_triangles();return BVHTree.FromPolygons([o.matrix_world@v.co for v in o.data.vertices],[tuple(t.vertices)for t in o.data.loop_triangles],all_triangles=True,epsilon=0)
packet=json.loads((R/'canonical-source-report.json').read_text())
body=bpy.data.objects['EXACT_SERIALIZED_ORIGINAL_BODY_BIND_REFERENCE'];tb=tree(body);records=[]
for side in ['Left','Right']:
 hand=bpy.data.objects['CC0Adult_'+side+'_ForearmHand_SOURCE_UNRIGGED'];cuff=bpy.data.objects['AnatomicalFittedHoodieCuff'+side];th=tree(hand);tc=tree(cuff);ch=tc.overlap(th);bh=tb.overlap(th);cb=tc.overlap(tb);side_packet=next(x for x in packet['records']if x['side']==side);axis=Vector(next(x for x in packet['original_triangle_retirement_masks']if x['side']==side)['clip_plane_normal']);wrist=Vector(side_packet['canonical_wrist']);depths=[((cuff.matrix_world@cuff.data.vertices[vi].co)-wrist).dot(axis)for ti,_ in cb for vi in cuff.data.loop_triangles[ti].vertices];body_depths=[((body.matrix_world@body.data.vertices[vi].co)-wrist).dot(axis)for _,ti in cb for vi in body.data.loop_triangles[ti].vertices];records.append({'side':side,'cuff_hand_surface_triangle_pairs':len(ch),'body_hand_surface_triangle_pairs':len(bh),'cuff_body_surface_triangle_pairs':len(cb),'cuff_body_candidate_depth_range_from_wrist_m':([min(depths),max(depths)]if depths else None),'overlapping_body_triangle_depth_range_from_wrist_m':([min(body_depths),max(body_depths)]if body_depths else None),'cuff_body_overlap_note':'Original1mm garment-seam overlap is intentional; still reported, not waived as full-contact acceptance.','first_cuff_hand_pairs':ch[:20],'first_body_hand_pairs':bh[:20]})
r={'schema':'sub01.canonical-cuff-source-contact.v1','geometry_scope':'Actual source bind surfaces, no pose/skin/native contact claim','sides':records,'motion_contact_accepted':False,'native_accepted':False};(R/'independent-static-cuff-contact.json').write_text(json.dumps(r,indent=2));print('CANONICAL_CUFF_ACTUAL_CONTACT',json.dumps(r),flush=True)
