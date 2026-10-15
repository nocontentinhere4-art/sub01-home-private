"""Canonical-space genuine hands/cuffs. No body/skeleton serialization replacement."""
import bpy,bmesh,json,hashlib,sys
from pathlib import Path
from mathutils import Vector,Matrix
sys.path.insert(0,str(Path(__file__).parent));from build_anatomical_hoodie_cuffs_blender import fitted_cuff
R=Path('/workspace/sub01-home-private/human-base-hands-r1');out=R/'canonical-hand-cuffs-r1';out.mkdir(exist_ok=False);data=json.loads(Path('/home/unreal/runtime-tools/canonical-original-cuff-reference.json').read_text());bpy.ops.wm.open_mainfile(filepath=str(R/'rig-r9/uv-skin-source-r1/official-hand-uv-material-source.blend'));rig=bpy.data.objects['CC0AnatomicalHandRig'];hands={side:bpy.data.objects['CC0Adult_'+side+'_ForearmHand_SOURCE_UNRIGGED']for side in['Left','Right']};newrest={b.name:rig.matrix_world@b.matrix_local for b in rig.data.bones};oldrest={name:Matrix([values[i:i+4]for i in range(0,16,4)]).transposed()for name,values in data['binds'].items()}
before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath='/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/owner-with-clips-unreal.glb');created=set(bpy.data.objects)-before;imported=next(o for o in created if o.type=='MESH'and o.name.startswith('tripo'));source_materials=list(imported.data.materials)
mesh=bpy.data.meshes.new('EXACT_SERIALIZED_ORIGINAL_BODY_BIND_REFERENCE');mesh.from_pydata(data['positions'],[],data['faces']);mesh.update();cloth=bpy.data.objects.new(mesh.name,mesh);bpy.context.scene.collection.objects.link(cloth);uv=mesh.uv_layers.new(name='ExactOriginalBodyUV')
for p in mesh.polygons:
 for loop in p.loop_indices:uv.data[loop].uv=data['uvs'][mesh.loops[loop].vertex_index]
# Original material order is reconstructed by actual original glTF material names.
original=json.loads(Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/owner-with-clips-unreal.glb').read_bytes()[20:20+int.from_bytes(Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/owner-with-clips-unreal.glb').read_bytes()[12:16],'little')]);mapping={}
for mi in sorted(set(data['materials'])):
 name=original['materials'][mi]['name'];matches=[m for m in source_materials if m.name==name or m.name.startswith(name+'.')];assert len(matches)==1,(name,[m.name for m in source_materials]);mapping[mi]=len(mesh.materials);mesh.materials.append(matches[0])
for p,mi in zip(mesh.polygons,data['materials']):p.material_index=mapping[mi]
for o in created:bpy.data.objects.remove(o,do_unlink=True)
def frame(rest,side):
 p=rest['mixamorig:'+side+'Hand'].translation;y=(p-rest['mixamorig:'+side+'ForeArm'].translation).normalized();x=rest['mixamorig:'+side+'HandIndex1'].translation-rest['mixamorig:'+side+'HandPinky1'].translation;x=(x-y*x.dot(y)).normalized();z=x.cross(y).normalized();return Matrix(((x.x,y.x,z.x,p.x),(x.y,y.y,z.y,p.y),(x.z,y.z,z.z,p.z),(0,0,0,1)))
records=[];cuffs=[];new_bind_worlds={};retire_masks=[]
for side,hand in hands.items():
 align=frame(oldrest,side)@frame(newrest,side).inverted();wrist=oldrest['mixamorig:'+side+'Hand'].translation;axis=(wrist-oldrest['mixamorig:'+side+'ForeArm'].translation).normalized();roll=frame(oldrest,side).to_3x3().col[0]
 selected=[]
 for fi,face in enumerate(data['faces']):
  points=[Vector(data['positions'][i])for i in face];center=sum(points,Vector())/3;offset=center-wrist;axial=offset.dot(axis);radial=(offset-axis*axial).length
  if -.08<axial<.24 and radial<.13 and any((point-(wrist-axis*.055)).dot(axis)>0 for point in points):selected.append(data['face_origins'][fi])
 retire_masks.append({'side':side,'original_main_mesh_triangles_touched':selected,'clip_plane_point_m':list(wrist-axis*.055),'clip_plane_normal':list(axis),'retire_positive_halfspace':True,'note':'For crossing original triangles, preserve negative-halfspace clipped source remainder and its interpolated original UV/weights; do not drop whole crossing triangle or mutate unrelated body attributes'})
 for digit in ['Thumb','Index','Middle','Ring','Pinky']:
  for k in range(1,5):
   name=f'mixamorig:{side}Hand{digit}{k}';m=align@newrest[name];m=Matrix.LocRotScale(m.translation,m.to_quaternion(),Vector((.01,.01,.01)));new_bind_worlds[name]=[list(row)for row in m]
 cuff,receipt=fitted_cuff(cloth,rig,hand,align,side,wrist,axis,roll);cuffs.append(cuff)
 # Crop surplus source forearm only; cuff surrounds the genuine wrist seam.
 plane=align.inverted()@(wrist-axis*.03);normal=(align.to_3x3().transposed()@axis).normalized();labels=hand.data.attributes['OriginalSculptFaceSet'];digit_ids=set(range(64,84))if side=='Left'else set(range(84,104));digit_vertices={i for p in hand.data.polygons if labels.data[p.index].value in digit_ids for i in p.vertices};assert all((hand.data.vertices[i].co-plane).dot(normal)>1e-5 for i in digit_vertices),'Trim would cut genuine authored digits';bm=bmesh.new();bm.from_mesh(hand.data);bmesh.ops.bisect_plane(bm,geom=list(bm.verts)+list(bm.edges)+list(bm.faces),plane_co=plane,plane_no=normal,dist=1e-7,clear_inner=True,clear_outer=False);bm.to_mesh(hand.data);bm.free()
 for vertex in hand.data.vertices:vertex.co=align@vertex.co
 for p in hand.data.polygons:p.use_smooth=True
 hand.data.update();records.append({'side':side,'canonical_wrist':list(wrist),'canonical_rigid_fit_matrix':[list(row)for row in align],'geometry_scale':1,'cuff':receipt})
for o in bpy.context.scene.objects:
 if o.type=='MESH'and o not in list(hands.values())+cuffs:o.hide_render=True
bpy.ops.object.select_all(action='DESELECT')
for o in [rig,*hands.values(),*cuffs]:o.hide_set(False);o.select_set(True)
bpy.context.view_layer.objects.active=rig;bpy.ops.wm.save_as_mainfile(filepath=str(out/'canonical-anatomical-hand-cuffs.blend'));bpy.ops.export_scene.gltf(filepath=str(out/'canonical-anatomical-hand-cuffs.glb'),export_format='GLB',use_selection=True,export_animations=False,export_skins=True,export_all_influences=True)
report={'schema':'sub01.canonical-anatomical-hand-cuffs.v1','body_reference':'Exact original raw serialized POSITION/index/UV in original mesh bind metres; no Blender recentering','original_body_sha256':'45e917725f02836dee6d051d9b47dd2785208c78b503fa935ddb322fe69adea8','report_coordinate_space':'Blender Z-up; positions/planes in physical metres; bind-world linear scale0.01. Convert report matrices by left-multiplying Blender-to-glTF basis for assembly; exported GLB geometry is already glTF Y-up.','records':records,'new_finger_bind_worlds_original_scale_0p01':new_bind_worlds,'original_triangle_retirement_masks':retire_masks,'source_to_target_joints':'Exact mixamorig:Left/RightHand{Thumb,Index,Middle,Ring,Pinky}{1..4}, ForeArm and Hand names map onto original65; no renamed or mirrored joints','note':'Joint names/weights only for final serialized original65 assembly; this44 source armature is not native integration skeleton','geometry_sha256':hashlib.sha256((out/'canonical-anatomical-hand-cuffs.glb').read_bytes()).hexdigest(),'contact_accepted':False,'native_imported':False};(out/'canonical-source-report.json').write_text(json.dumps(report,indent=2));print('CANONICAL_REAL_HAND_CUFF_SOURCE_BUILT',report['geometry_sha256'],flush=True)
