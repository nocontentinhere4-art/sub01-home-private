"""Private Blender source: real oak service-wall joinery and re-levelled CC0 cabinet.

Keeps the functional TV case/screen at their exact existing coordinates. The
recess is sized against the measured native case; nothing is applied to Game.
"""
import bpy,sys,json,hashlib,math,struct,copy
from pathlib import Path
from mathutils import Vector
sys.path.insert(0,'/home/unreal/runtime-tools')
from home_asset_audit import read_gltf
ROOT=Path('/workspace/sub01-home-private');OUT=ROOT/'reference-living-tv-wall-r4/output';OUT.mkdir(parents=True,exist_ok=True)
MEDIA=ROOT/'real-media-console-source-r1/output'
bpy.ops.wm.open_mainfile(filepath=str(MEDIA/'media-console-side.blend'))
MATNAMES={'Oak | natural satin finish','Elastomer | feet and drawer stops','Graphite | fine powder-coated steel','Bronze | brushed satin hardware','Nickel | brushed steel hardware'}
cabinet=[o for o in bpy.context.scene.objects if o.type=='MESH'and len(o.data.materials)==1 and o.data.materials[0].name in MATNAMES]
assert len(cabinet)>30 and {o.data.materials[0].name for o in cabinet}==MATNAMES
for o in list(bpy.context.scene.objects):
 if o.type=='MESH'and o not in cabinet:bpy.data.objects.remove(o,do_unlink=True)
anchor=bpy.data.objects['SUB01_MediaCabinetPlacement'];assert (anchor.location-Vector((-3.66,-2.05,.0328))).length<1e-6
anchor.location=(-3.54,.05,.0328);bpy.context.view_layer.update()
# The previous placement authored two root-level spindles after the cabinet
# anchor existed. They must receive the same rigid delta explicitly.
old_stems=[o for o in cabinet if o.name.startswith('Floor side adjustable steel foot spindle')];assert len(old_stems)==2
for o in old_stems:
 world=o.matrix_world.copy();world.translation+=Vector((.12,2.10,0));o.matrix_world=world
bpy.context.view_layer.update()
# All four adjustable glides now rest on the same measured 25mm floor. The
# earlier side placement straddled a 7.75mm support difference; do not float feet.
feet=[];new_stems=[]
for o in cabinet:
 if not o.name.startswith('Leg | felt glide'):continue
 points=[o.matrix_world@Vector(v)for v in o.bound_box];bottom=min(v.z for v in points);extension=bottom-.02505
 assert -.000002<extension<.008
 if extension>.00001:
  world=o.matrix_world.copy();world.translation.z-=extension;o.matrix_world=world;bpy.context.view_layer.update();pts=[o.matrix_world@Vector(v)for v in o.bound_box];center=sum(pts,Vector())/8;top=max(v.z for v in pts)
  bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=.0055,depth=.0398-(top-.001),location=(center.x,center.y,(.0398+top-.001)/2));stem=bpy.context.object;stem.name='LW_AdjustableFootSpindle';stem.data.materials.append(next(x.data.materials[0]for x in cabinet if x.name.startswith('Leg | tapered graphite steel')));new_stems.append(stem)
  for f in stem.data.polygons:f.use_smooth=True
 points=[o.matrix_world@Vector(v)for v in o.bound_box];feet.append({'part':o.name,'extension_m':max(0,extension),'actual_bottom_m':min(v.z for v in points)})
assert len(feet)==4 and len(new_stems)==2
cabinet+=new_stems
islands=[]
for o in cabinet:
 pts=[o.matrix_world@Vector(v)for v in o.bound_box];lo=[min(v[i]for v in pts)for i in range(3)];hi=[max(v[i]for v in pts)for i in range(3)];assert lo[0]>=-3.761 and hi[0]<=-3.277 and lo[1]>=-.866 and hi[1]<=.966,(o.name,lo,hi);islands.append({'name':o.name,'bounds_blender_m':[lo,hi]})
allpts=[o.matrix_world@Vector(v)for o in cabinet for v in o.bound_box];cabinet_bounds=[[min(v[i]for v in allpts)for i in range(3)],[max(v[i]for v in allpts)for i in range(3)]];assert 1.829<cabinet_bounds[1][1]-cabinet_bounds[0][1]<1.832
# Detach exactly at the current world pose; the original manufacturer geometry
# remains untouched except the two newly extended real levelling pads/spindles.
for o in cabinet:w=o.matrix_world.copy();o.parent=None;o.matrix_world=w
bpy.ops.object.select_all(action='DESELECT')
for o in cabinet:o.select_set(True)
bpy.ops.object.join();cabinet_joined=bpy.context.object;cabinet_joined.name='LW_OriginalChannel183';bpy.ops.export_scene.gltf(filepath=str(OUT/'living-cabinet.glb'),export_format='GLB',use_selection=True,export_cameras=False,export_lights=False)
# Photographic CC0 oak veneer, explicit real-world 0.61m UV repeat. The reference
# photo is visual guidance; it is never used as a surface texture.
wood=bpy.data.materials.new('LWOak');wood.use_nodes=True;n=wood.node_tree.nodes;l=wood.node_tree.links;bs=n.get('Principled BSDF');bs.inputs['Roughness'].default_value=.67
texroot=Path('/workspace/sub01-private-kitchen-3eb5419-20261015/assets-r2/web/house/assets/home_oak_veneer')
for filename,role in [('diff.jpg','Base Color'),('rough.jpg','Roughness'),('normal.jpg','Normal')]:
 im=bpy.data.images.load(str(texroot/filename));im.colorspace_settings.name='sRGB'if role=='Base Color'else'Non-Color';im.pack();t=n.new('ShaderNodeTexImage');t.image=im
 if role=='Normal':nm=n.new('ShaderNodeNormalMap');nm.inputs['Strength'].default_value=.23;l.new(t.outputs['Color'],nm.inputs['Color']);l.new(nm.outputs['Normal'],bs.inputs[role])
 else:l.new(t.outputs['Color'],bs.inputs[role])
back=bpy.data.materials.new('LWCharcoalNiche');back.diffuse_color=(.028,.031,.036,1);back.use_nodes=True;p=back.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=back.diffuse_color;p.inputs['Roughness'].default_value=.82
parts=[]
def board(name,bounds,material):
 lo,hi=bounds;assert all(a<b for a,b in zip(lo,hi));loc=[(a+b)/2 for a,b in zip(lo,hi)];dim=[b-a for a,b in zip(lo,hi)]
 # All dimensions supplied in physical Unreal cm, converted exactly to Blender m.
 bpy.ops.mesh.primitive_cube_add(size=1,location=(loc[0]/100,-loc[1]/100,loc[2]/100));o=bpy.context.object;o.name=name;o.dimensions=Vector(dim)/100;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
 bevel=o.modifiers.new('Real 2mm eased veneer edge','BEVEL');bevel.width=.002;bevel.segments=3;bpy.ops.object.modifier_apply(modifier=bevel.name);normal=o.modifiers.new('Manufactured planar face normals','WEIGHTED_NORMAL');normal.keep_sharp=True;bpy.ops.object.modifier_apply(modifier=normal.name)
 o.data.materials.append(material);uv=o.data.uv_layers.active or o.data.uv_layers.new(name='Physical_610mm_veneer')
 for face in o.data.polygons:
  for li in face.loop_indices:
   q=o.matrix_world@o.data.vertices[o.data.loops[li].vertex_index].co;axis=max(range(3),key=lambda i:abs(face.normal[i]));uv.data[li].uv=((q.y if axis==0 else q.x)/.61,(q.y if axis==2 else q.z)/.61)
 parts.append(o);return o
# Discrete plywood panels with 2mm expansion reveals; recess rear stays 7.5mm
# behind the measured TV rear (-384.25cm). Screen plane X=-374.7cm is unchanged.
board('LWLower',([-389,-140,2.505],[-376.5,140,111.8]),wood)
board('LWUpper',([-389,-140,218.2],[-376.5,140,285]),wood)
board('LWLeftPier',([-389,-140,112],[-376.5,-94.2,218]),wood)
board('LWRightPier',([-389,84.2,112],[-376.5,140,218]),wood)
board('LWRecessBack',([-389,-94,112],[-385,84,218]),back)
# Four thin reveal returns conceal the wall cavity without entering the real TV
# case box Y[-92,82],Z[114,216],X[-384.25,-375.75].
board('LWRecessLeft',([-385,-94,112],[-376.5,-93,218]),back)
board('LWRecessRight',([-385,83,112],[-376.5,84,218]),back)
board('LWRecessLower',([-385,-93,112],[-376.5,83,113]),back)
board('LWRecessUpper',([-385,-93,217],[-376.5,83,218]),back)
bpy.ops.object.select_all(action='DESELECT')
for o in parts:o.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(OUT/'living-tv-wall.glb'),export_format='GLB',use_selection=True,export_cameras=False,export_lights=False)
bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'living-tv-wall.blend'))
r={'schema':'sub01.reference-living-tv-wall-source.v1','native_imported':False,'live_game_changed':False,'tv_screen_plane_x_cm':-374.7,'tv_geometry_changed':False,'tv_case_bounds_cm':[[-384.25,-92,114],[-375.75,82,216]],'recess_clear_bounds_cm':[[-385,-93,113],[-377,83,217]],'rear_tv_clearance_cm':.75,'wall_bounds_cm':[[-389,-140,2.505],[-376.5,140,285]],'cladding_front_clearance_from_retained_white_wall_cm':.5,'retained_white_wall_plane_x_cm':-377,'wall_parts':len(parts),'wood_uv_repeat_m':.61,'cabinet_source':'Existing CC0 Innerscene CHANNEL183 original Blender manufacturer model','cabinet_delta_UE_cm':[12,-210,0],'cabinet_modified_only_real_leveling_glides':True,'cabinet_feet':feet,'cabinet_new_spindles':len(new_stems),'existing_root_spindles_rigid_delta_applied':len(old_stems),'cabinet_bounds_blender_m':cabinet_bounds,'cabinet_component_bounds':islands,'old_central_west_windows_visual_retirement_proposed':list(range(38,74)),'window_affordance_retirement_required':True,'source_photos_are_not_textures':True,'source_reference':'Owner warm wood gaming room with navy upholstery','files':{name:hashlib.sha256((OUT/name).read_bytes()).hexdigest()for name in ['living-tv-wall.glb','living-cabinet.glb','living-tv-wall.blend']}}
(OUT/'source-report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
