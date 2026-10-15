"""Actual source digit-identity evidence, projected joint overlays, no mutation."""
import bpy,json,math
from pathlib import Path
from mathutils import Vector
R=Path('/workspace/sub01-home-private/human-base-hands-r1');out=R/'rig-r9/digit-identity-review-r1';out.mkdir(exist_ok=False);bpy.ops.wm.open_mainfile(filepath=str(R/'rig-r9/official-adult-hand-pair-rig.blend'));s=bpy.context.scene;rig=bpy.data.objects['CC0AnatomicalHandRig'];hands={side:bpy.data.objects['CC0Adult_'+side+'_ForearmHand_SOURCE_UNRIGGED']for side in['Left','Right']}
report={'read_only_source':True,'projected_marker_method':'Actual bone Y/Z retained, X lifted outside skin toward source review camera to reveal internal joint centres; not moved bones','sides':{},'source_body_groups':[],'source_body_attributes':[]}
source=R/'source/human-base-meshes-bundle-v1.4.1/human_base_meshes_bundle.blend'
with bpy.data.libraries.load(str(source),link=False)as(src,dst):dst.objects=['GEO-body_male_realistic']
original=dst.objects[0];report['source_body_groups']=[v.name for v in original.vertex_groups];report['source_body_attributes']=[{'name':a.name,'domain':a.domain,'type':a.data_type}for a in original.data.attributes]
for o in s.objects:o.hide_render=True
mat=bpy.data.materials.new('Actual anatomical surface neutral diagnostic');mat.diffuse_color=(.5,.37,.3,1);mat.use_nodes=True;mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(.5,.37,.3,1)
for h in hands.values():h.data.materials.clear();h.data.materials.append(mat)
world=bpy.data.worlds.new('Identity studio');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.1,.11,.12,1);world.node_tree.nodes['Background'].inputs[1].default_value=.4;s.world=world
bpy.ops.object.camera_add();cam=bpy.context.object;cam.data.type='ORTHO';cam.data.ortho_scale=.265;s.camera=cam
bpy.ops.object.light_add(type='AREA');light=bpy.context.object;light.data.energy=90;light.data.size=1
s.render.engine='CYCLES';s.cycles.device='CPU';s.cycles.samples=16;s.cycles.use_denoising=True;s.render.resolution_x=1000;s.render.resolution_y=1100;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG'
colors={'Thumb':(1,.05,.03,1),'Index':(.04,1,.05,1),'Middle':(.05,.3,1,1),'Ring':(1,.45,.02,1),'Pinky':(1,.03,.7,1)}
for side,h in hands.items():
 h.hide_render=False;points=[h.matrix_world@v.co for v in h.data.vertices];joints={f:{i:rig.matrix_world@rig.data.bones['mixamorig:'+side+'Hand'+f+str(i)].head_local for i in[1,2,3,4]}for f in colors};center=sum((p for f in joints.values()for p in f.values()),Vector())/20;report['sides'][side]={'joints':{f:{str(i):list(p)for i,p in js.items()}for f,js in joints.items()}}
 for sign in[1,-1]:
  overlay=[];plane=(max(p.x for p in points)+.004)if sign==1 else(min(p.x for p in points)-.004)
  for f,js in joints.items():
   m=bpy.data.materials.new(side+f+str(sign));m.diffuse_color=colors[f];m.use_nodes=True;pr=m.node_tree.nodes['Principled BSDF'];pr.inputs['Base Color'].default_value=colors[f];pr.inputs['Emission Color'].default_value=colors[f];pr.inputs['Emission Strength'].default_value=.5
   for i,p in js.items():
    q=Vector((plane,p.y,p.z));bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=6,radius=.0012,location=q);o=bpy.context.object;o.data.materials.append(m);overlay.append(o)
   p=js[4];bpy.ops.object.text_add(location=(plane,p.y-.002,p.z-.008));t=bpy.context.object;t.data.body=f;t.data.size=.006;t.data.align_x='CENTER';t.data.materials.append(m);t.rotation_euler=Vector((sign,0,0)).to_track_quat('Z','Y').to_euler();overlay.append(t)
  cam.location=center+Vector((sign,0,0));cam.rotation_euler=(center-cam.location).to_track_quat('-Z','Y').to_euler();light.location=center+Vector((sign*.7,-.2,.4));light.rotation_euler=(center-light.location).to_track_quat('-Z','Y').to_euler();s.render.filepath=str(out/f'{side.lower()}-digit-identity-x{sign:+}.png');bpy.ops.render.render(write_still=True)
  for o in overlay:bpy.data.objects.remove(o,do_unlink=True)
 h.hide_render=True
(out/'identity-source-report.json').write_text(json.dumps(report,indent=2)+'\n');print('ACTUAL_DIGIT_IDENTITY_REVIEW_COMPLETE',report['source_body_groups'],report['source_body_attributes'],flush=True)
