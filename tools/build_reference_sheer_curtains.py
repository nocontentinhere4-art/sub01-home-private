"""Runpod Blender cloth/pinned-heading sheer pair fitted to the actual patio unit.

Primary reference: viewed official embedded video0s/7s. Actual photographed CC0
linen weave, normal and roughness; deliberately bleached cream and made sheer
using its genuine mask. No reference photograph becomes a production texture.
This is a source candidate; native lit translucency/shadows are separate gates.
"""
import bpy,sys,json,math,hashlib
from pathlib import Path
from mathutils import Vector
import numpy as np
ROOT=Path('/workspace/sub01-home-private/reference-curtain-source-r1');OUT=ROOT/'output';OUT.mkdir(parents=True,exist_ok=True);MAPS=ROOT/'maps'
bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene;scene.frame_start=1;scene.frame_end=28;scene.render.fps=24
# Preserve photographed physical weave scale: one texture tile is270.7x271.3mm.
diff=bpy.data.images.load(str(MAPS/'diff.jpg'));mask=bpy.data.images.load(str(MAPS/'mask.png'));mask.colorspace_settings.name='Non-Color'
w,h=diff.size;rgb=np.array(diff.pixels[:],dtype=np.float32).reshape(h,w,4);alpha=np.array(mask.pixels[:],dtype=np.float32).reshape(h,w,4)[:,:,0]
lum=rgb[:,:,0]*.2126+rgb[:,:,1]*.7152+rgb[:,:,2]*.0722;variation=(lum-lum.min())/(lum.max()-lum.min())
rgba=np.empty_like(rgb);rgba[:,:,:3]=np.array((.94,.91,.83),dtype=np.float32)[None,None,:]*(.82+.18*variation[:,:,None]);rgba[:,:,3]=.045+.70*alpha
cream=bpy.data.images.new('CC0 photographed linen bleached cream with genuine weave mask',width=w,height=h,alpha=True);cream.pixels.foreach_set(rgba.ravel());cream.filepath_raw=str(OUT/'cream-sheer-weave.png');cream.file_format='PNG';cream.save();cream.pack()
cloth=bpy.data.materials.new('SUB01 Cream photographed linen sheer');cloth.use_nodes=True;cloth.diffuse_color=(.94,.91,.83,.5);cloth.use_backface_culling=False
if hasattr(cloth,'surface_render_method'):cloth.surface_render_method='DITHERED'
if hasattr(cloth,'use_transparent_shadow'):cloth.use_transparent_shadow=True
nodes=cloth.node_tree.nodes;links=cloth.node_tree.links;p=nodes.get('Principled BSDF');p.inputs['Metallic'].default_value=0;p.inputs['Roughness'].default_value=.9;p.inputs['IOR'].default_value=1.38;p.inputs['Subsurface Weight'].default_value=.1;p.inputs['Transmission Weight'].default_value=.12
tex=nodes.new('ShaderNodeTexImage');tex.image=cream;links.new(tex.outputs['Color'],p.inputs['Base Color']);links.new(tex.outputs['Alpha'],p.inputs['Alpha'])
rough=bpy.data.images.load(str(MAPS/'rough.jpg'));rough.colorspace_settings.name='Non-Color';rough.pack();r=nodes.new('ShaderNodeTexImage');r.image=rough;links.new(r.outputs['Color'],p.inputs['Roughness'])
normal=bpy.data.images.load(str(MAPS/'normal.jpg'));normal.colorspace_settings.name='Non-Color';normal.pack();n=nodes.new('ShaderNodeTexImage');n.image=normal;nm=nodes.new('ShaderNodeNormalMap');nm.inputs['Strength'].default_value=.25;links.new(n.outputs['Color'],nm.inputs['Color']);links.new(nm.outputs['Normal'],p.inputs['Normal'])
metal=bpy.data.materials.new('SUB01 curtain rail satin champagne aluminium');metal.use_nodes=True;bs=metal.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(.36,.32,.24,1);bs.inputs['Metallic'].default_value=.8;bs.inputs['Roughness'].default_value=.32
panels=[];rail=[]
NX,NY=64,48
for label,outer,direction in [('Left',-3.79,1),('Right',-.21,-1)]:
 verts=[];faces=[]
 for j in range(NY+1):
  v=j/NY;z=5.35-2.31*v
  for i in range(NX+1):
   u=i/NX;wave=2*math.pi*8*u+.09*math.sin(u*17)*v
   # Regular sewn heading, increasingly irregular natural lower pleats.
   y=-3.74+.032*math.sin(wave)*(1+.15*v)+.002*math.sin(u*11+v*13)*v
   verts.append((outer+direction*.49*u,y,z-.004*math.sin(math.pi*u)*v**6))
 for j in range(NY):
  for i in range(NX):
   q=j*(NX+1)+i;faces.append((q,q+NX+1,q+NX+2,q+1)if direction>0 else(q+1,q+NX+2,q+NX+1,q))
 mesh=bpy.data.meshes.new('Actual continuous sewn sheer cloth');mesh.from_pydata(verts,[],faces);mesh.update();o=bpy.data.objects.new('SUB01ReferenceSheer_'+label,mesh);scene.collection.objects.link(o);o.data.materials.append(cloth)
 uv=mesh.uv_layers.new(name='Photographed weave physical metres')
 # Arc-length UVs preserve actual photographed thread scale across the pleats.
 arc=[0]
 for i in range(1,NX+1):arc.append(arc[-1]+(Vector(verts[i])-Vector(verts[i-1])).length)
 for polygon in mesh.polygons:
  polygon.use_smooth=True
  for li in polygon.loop_indices:
   vi=mesh.loops[li].vertex_index;j,i=divmod(vi,NX+1);uv.data[li].uv=(arc[i]/.2707081392676629,2.31*j/NY/.27129998803138733)
 pins=o.vertex_groups.new(name='Actually pinned sewn heading');pins.add(list(range(NX+1)),1.,'REPLACE')
 c=o.modifiers.new('Physical linen drape under gravity','CLOTH');c.settings.quality=5;c.settings.mass=.12;c.settings.tension_stiffness=35;c.settings.compression_stiffness=35;c.settings.shear_stiffness=20;c.settings.bending_stiffness=.6;c.settings.vertex_group_mass=pins.name;c.settings.air_damping=3;c.collision_settings.use_self_collision=True;c.collision_settings.self_distance_min=.001;c.point_cache.frame_start=1;c.point_cache.frame_end=28
 panels.append(o)
for frame in range(1,29):scene.frame_set(frame)
for o in panels:
 bpy.context.view_layer.objects.active=o;bpy.ops.object.modifier_apply(modifier='Physical linen drape under gravity')
 for polygon in o.data.polygons:polygon.use_smooth=True

def box(name,loc,size):
 bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=bpy.context.object;o.name=name;o.dimensions=size;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);b=o.modifiers.new('Manufactured edge radius','BEVEL');b.width=.0007;b.segments=2;bpy.ops.object.modifier_apply(modifier=b.name);o.data.materials.append(metal);rail.append(o);return o
# Wall-mounted brackets on the measured new transom head. Existing frame starts
# nativeY391cm; backplates end390.95cm, a0.5mm assembly clearance, not a fake wall.
for x in(-3.75,-.25):
 box('Wall plate',(x,-3.907,5.425),(.025,.005,.045));box('Rail support arm',(x,-3.825,5.42),(.012,.164,.012));box('Rail drop',(x,-3.745,5.395),(.012,.012,.05))
bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=.006,depth=3.66,location=(-2,-3.74,5.39),rotation=(0,math.pi/2,0));rod=bpy.context.object;rod.data.materials.append(metal);rail.append(rod)
for outer,direction in[(-3.79,1),(-.21,-1)]:
 for i in range(9):
  x=outer+direction*.49*i/8
  bpy.ops.mesh.primitive_torus_add(major_segments=12,minor_segments=6,location=(x,-3.74,5.371),rotation=(math.pi/2,0,0),major_radius=.012,minor_radius=.0015);o=bpy.context.object;o.data.materials.append(metal);rail.append(o)
bpy.ops.object.select_all(action='DESELECT')
for o in rail:o.select_set(True)
bpy.context.view_layer.objects.active=rail[0];bpy.ops.object.join();hardware=bpy.context.object;hardware.name='SUB01ReferenceSheer_Hardware';hardware.data.name=hardware.name
outputs=panels+[hardware];rows=[]
for o in outputs:
 pts=[o.matrix_world@v.co for v in o.data.vertices];ue=[(v.x*100,-v.y*100,v.z*100)for v in pts];lo=[min(v[i]for v in ue)for i in range(3)];hi=[max(v[i]for v in ue)for i in range(3)];o.data.calc_loop_triangles();rows.append({'name':o.name,'bounds_ue_cm':[lo,hi],'triangles':len(o.data.loop_triangles)})
for row in rows[:2]:
 lo,hi=row['bounds_ue_cm'];assert lo[2]>=302.5 and hi[2]<540 and hi[1]<390.65,'Cloth must clear actual floor and complete hardware depth'
 assert hi[0]<=-325 or lo[0]>=-75,'Cloth must stay out of full−314.95..−125.05cm door sweep and real passage'
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'reference-sheer.blend'));bpy.ops.object.select_all(action='DESELECT')
for o in outputs:o.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(OUT/'reference-sheer.glb'),export_format='GLB',use_selection=True,export_cameras=False,export_lights=False)
report={'schema':'sub01.reference-sheer-source.v1','sha256':hashlib.sha256((OUT/'reference-sheer.glb').read_bytes()).hexdigest(),'reference':'https://platform.twitter.com/embed/Tweet.html?id=2109095401273938072','actual_reference_frames_viewed_s':[0,7],'source_linen':'https://polyhaven.com/a/rough_linen','source_license':'CC0','source_weave_physical_mm':[270.7081392676629,271.29998803138733],'derived_texture':'Original photographed linen recoloured bleached cream; genuine photographed weave mask controls alpha. No X screenshot used as texture.','cloth_frames_simulated':28,'cloth_pinned_heading':True,'cloth_source_geometry':'Actual Blender Cloth modifier gravity drape applied after28frames;2continuous single surfaces, no stacked strips/boxes','texture_max_dimension':1026,'panels':2,'hardware_groups':1,'alpha_surfaces':2,'materials_lit':True,'source_transmission_weight':.12,'native_lit_translucency_verified':False,'native_shadows_verified':False,'native_imported':False,'door_source_sha256':'5b8a2bb8b4bb8fe19af1d0c086fb78f3e7f9dff9e06170a06642a8f3d1761a0c','full_door_sweep_x_cm':[-314.95,-125.05],'actual_door_hardware_min_y_cm':390.65,'actual_upper_floor_cm':302.5,'parts':rows}
(OUT/'source-report.json').write_text(json.dumps(report,indent=2));print('ACTUAL_SHEER_SOURCE',json.dumps(report),flush=True)
