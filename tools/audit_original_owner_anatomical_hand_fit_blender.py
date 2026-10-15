"""Read-only feasibility of preserving original65 finger rests in real R9 skin."""
import bpy,json,math
from pathlib import Path
from mathutils import Vector,Matrix
from mathutils.bvhtree import BVHTree
R=Path('/workspace/sub01-home-private/human-base-hands-r1');bpy.ops.wm.open_mainfile(filepath=str(R/'rig-r9/uv-skin-source-r1/official-hand-uv-material-source.blend'));new=bpy.data.objects['CC0AnatomicalHandRig'];before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath='/home/unreal/runtime-tools/canonical-walk-owner.glb');old=next(o for o in set(bpy.data.objects)-before if o.type=='ARMATURE');assert len(old.data.bones)==65;old.animation_data_clear()
for p in old.pose.bones:p.matrix_basis=Matrix.Identity(4)
rest_old={b.name:old.matrix_world@b.matrix_local for b in old.data.bones};rest_new={b.name:new.matrix_world@b.matrix_local for b in new.data.bones}
def frame(rest,side):
 p=rest['mixamorig:'+side+'Hand'].translation;y=(p-rest['mixamorig:'+side+'ForeArm'].translation).normalized();x=(rest['mixamorig:'+side+'HandIndex1'].translation-rest['mixamorig:'+side+'HandPinky1'].translation).normalized();x=(x-y*x.dot(y)).normalized();z=x.cross(y).normalized();return Matrix(((x.x,y.x,z.x,p.x),(x.y,y.y,z.y,p.y),(x.z,y.z,z.z,p.z),(0,0,0,1)))
directions=[Vector((1,.179,.317)).normalized(),Vector((.237,1,.119)).normalized(),Vector((.131,.229,1)).normalized()];result={'schema':'sub01.original65-rest-anatomical-fit.v1','read_only':True,'anatomy_scaled_or_distorted':False,'sides':{}}
for side in ['Left','Right']:
 o=bpy.data.objects['CC0Adult_'+side+'_ForearmHand_SOURCE_UNRIGGED'];align=frame(rest_old,side)@frame(rest_new,side).inverted();o.data.calc_loop_triangles();vertices=[align@o.matrix_world@v.co for v in o.data.vertices];triangles=[tuple(t.vertices)for t in o.data.loop_triangles];labels=[o.data.attributes['OriginalSculptFaceSet'].data[t.polygon_index].value for t in o.data.loop_triangles];tree=BVHTree.FromPolygons(vertices,triangles,all_triangles=True,epsilon=0);records=[]
 for finger in ['Thumb','Index','Middle','Ring','Pinky']:
  for k in range(1,5):
   name='mixamorig:'+side+'Hand'+finger+str(k);p=rest_old[name].translation;new_point=(align@rest_new[name]).translation;near,normal,ti,distance=tree.find_nearest(p);votes=[]
   for direction in directions:
    start=p.copy();hits=0
    for _ in range(100):
     hit,normal,idx,d=tree.ray_cast(start,direction,2)
     if hit is None:break
     hits+=1;start=hit+direction*1e-5
    votes.append(bool(hits%2))
   records.append({'bone':name,'original_rest_point':list(p),'new_anatomical_rest_point':list(new_point),'joint_rest_displacement_m':(p-new_point).length,'old_joint_inside_votes':votes,'nearest_actual_source_face_set':labels[ti],'nearest_skin_distance_m':distance})
 result['sides'][side]={'rigid_fit_matrix_rows':[list(row)for row in align],'joint_records':records,'old_joints_outside_skin_count':sum(sum(r['old_joint_inside_votes'])<2 for r in records),'maximum_joint_rest_displacement_m':max(r['joint_rest_displacement_m']for r in records)}
out=R/'rig-r9/original65-anatomical-fit-audit.json';out.write_text(json.dumps(result,indent=2)+'\n');print('ACTUAL_ORIGINAL65_FIT',json.dumps({side:{k:v for k,v in row.items()if k!='joint_records'and k!='rigid_fit_matrix_rows'}for side,row in result['sides'].items()}),flush=True)
