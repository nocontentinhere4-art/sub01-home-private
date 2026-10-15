"""Private Runpod Blender courtyard based on viewed LIXIL Fence AB reference.

Original authored geometry, no manufacturer image used as texture/CAD.
Existing floor/barrier collision remains authoritative until native acceptance.
"""
import argparse,sys,json,math,hashlib
from pathlib import Path
import bpy
p=argparse.ArgumentParser();p.add_argument('--maps',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);a.output.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True);objects=[]
def mat(name,color,rough,metal=0):
 m=bpy.data.materials.new(name);m.use_nodes=True;m.diffuse_color=(*color,1);s=m.node_tree.nodes.get('Principled BSDF');s.inputs['Base Color'].default_value=(*color,1);s.inputs['Roughness'].default_value=rough;s.inputs['Metallic'].default_value=metal;return m
aluminium=mat('Courtyard dark bronze powdercoat',(.045,.039,.032),.42,.55)
stone=mat('Courtyard genuine concrete pavement',(.5,.5,.5),.84)
grout=mat('Courtyard recessed grey grout',(.16,.16,.15),.95)
steel=mat('Courtyard stainless fasteners',(.36,.38,.38),.28,.85)
for role,file in [('Base Color','diff.jpg'),('Roughness','rough.jpg'),('Normal','normal.jpg')]:
 image=bpy.data.images.load(str(a.maps/file),check_existing=True);image.colorspace_settings.name='sRGB'if role=='Base Color'else'Non-Color';image.pack();nodes=stone.node_tree.nodes;t=nodes.new('ShaderNodeTexImage');t.image=image
 if role=='Normal':
  n=nodes.new('ShaderNodeNormalMap');n.inputs['Strength'].default_value=.4;stone.node_tree.links.new(t.outputs['Color'],n.inputs['Color']);stone.node_tree.links.new(n.outputs['Normal'],nodes.get('Principled BSDF').inputs['Normal'])
 else:stone.node_tree.links.new(t.outputs['Color'],nodes.get('Principled BSDF').inputs[role])
def block(name,location,dimensions,material,radius=.001):
 bpy.ops.mesh.primitive_cube_add(size=1,location=location);o=bpy.context.object;o.name=name;o.dimensions=dimensions;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
 if radius:
  b=o.modifiers.new('Real manufactured edge radius','BEVEL');b.width=radius;b.segments=2;bpy.ops.object.modifier_apply(modifier=b.name)
 o.data.materials.append(material)
 for f in o.data.polygons:f.use_smooth=False
 # Coordinates expressed in real metres;1.8m photographed pavement repeat.
 for polygon in o.data.polygons:
  for k in polygon.loop_indices:
   v=o.matrix_world@o.data.vertices[o.data.loops[k].vertex_index].co;o.data.uv_layers.active.data[k].uv=(v.x/1.8,-v.y/1.8)
 objects.append(o);return o
# Existing landing+support top is2.5cm. Visual paver face is0.2mm above it;
# no walking floor height or support/barrier collision is changed by this source.
block('Grout bed',(2,-6.35,.0201),(2.5,4.7,.010),grout,0)
for row in range(8):
 for col in range(4):
  block('Concrete paver',( .75+(col+.5)*.625,-4-(row+.5)*4.7/8,.0177),(.622,4.7/8-.003,.015),stone,.001)
# Real Fence AB reference uses60mm groundgap; posts within1m centres.
# Preserve exact oldcourtyard boundary volumes atx.75/3.25 andy8.7.
segments=[((.775,5.825),(.775,8.675)),((3.225,5.825),(3.225,8.675)),((.775,8.675),(3.225,8.675))]
seen_posts=set()
for section,(start,end)in enumerate(segments):
 dx,dy=end[0]-start[0],end[1]-start[1];length=math.hypot(dx,dy);bays=math.ceil(length/1.0);horizontal=abs(dx)>abs(dy)
 for index in range(bays+1):
  t=index/bays;x=start[0]+t*dx;y=start[1]+t*dy
  key=(round(x,8),round(y,8))
  if key in seen_posts:continue
  seen_posts.add(key)
  block('Metal post',(x,-y,.575),(.05,.05,1.10),aluminium,.0015)
  block('Post cap',(x,-y,1.128),(.052,.052,.006),aluminium,.0015)
  block('Post base plate',(x,-y,.028),(.065,.065,.006),steel,.0008)
  for ox,oy in [(-.022,-.022),(.022,.022)]:
   bpy.ops.mesh.primitive_cylinder_add(vertices=12,radius=.004,depth=.004,location=(x+ox,-y+oy,.033));o=bpy.context.object;o.data.materials.append(steel);objects.append(o)
 for bay in range(bays):
  t=(bay+.5)/bays;x=start[0]+t*dx;y=start[1]+t*dy;span=length/bays-.05
  for row in range(10):
   z=.085+.050+row*.103
   size=(span,.018,.100)if horizontal else(.018,span,.100)
   block('Louvered aluminium panel',(x,-y,z),size,aluminium,.0012)
  for z in [.10,1.10]:
   size=(span,.028,.018)if horizontal else(.028,span,.018)
   block('Panel carrier',(x,-y,z),size,aluminium,.001)
# Merge only same-material static parts; editableoriginal construction is saved first.
bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(a.output/'reference-entry.blend'));groups={}
for o in objects:groups.setdefault(o.data.materials[0].name,[]).append(o)
parts=[]
for i,(name,group)in enumerate(sorted(groups.items())):
 bpy.ops.object.select_all(action='DESELECT')
 for o in group:o.select_set(True)
 bpy.context.view_layer.objects.active=group[0];bpy.ops.object.join();o=bpy.context.object;o.name='SUB01ReferenceEntry_'+str(i);o.data.name=o.name;parts.append(o)
bpy.ops.object.select_all(action='DESELECT')
for o in parts:o.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(a.output/'reference-entry.glb'),export_format='GLB',use_selection=True,export_cameras=False,export_lights=False)
report={'schema':'sub01.reference-entry-courtyard-source.v1','source_photo':'https://www.lixil.co.jp/lineup/gate_fence/fence_ab/pic/fence_ab_img_10.png','reference_page':'https://www.lixil.co.jp/lineup/gate_fence/fence_ab/','reference_scope':'Viewed real manufacturer photograph and60mm groundgap/<=1m postspacing. Originalapproximate Blenderdesign, notlicensedmanufacturerCAD. No referenceimage copied as texture.','pavement_source':'https://polyhaven.com/a/concrete_pavement','pavement_license':'CC0','new_paver_top_cm':2.52,'existing_collision_floor_top_cm':2.5,'ground_gap_cm':6.,'retire_visual_only_labels':['SUB01_PrivateEntry_LeftWall','SUB01_PrivateEntry_RightWall','SUB01_PrivateEntry_FarWall','SUB01_PrivateEntry_Support'],'existing_floor_and_barrier_collisions_must_remain':True,'native_imported':False,'panorama_scale_fixed':False,'sha256':hashlib.sha256((a.output/'reference-entry.glb').read_bytes()).hexdigest(),'triangles':sum(sum(len(f.vertices)-2 for f in o.data.polygons)for o in parts),'material_groups':len(parts)}
(a.output/'source-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
