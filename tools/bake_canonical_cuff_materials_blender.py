"""Portable photographed source palette + baked metric knit normal; geometry unchanged."""
import bpy,json,math,hashlib
from pathlib import Path
R=Path('/workspace/sub01-home-private/human-base-hands-r1/canonical-hand-cuffs-r1');out=R/'portable-materials-r4';out.mkdir(exist_ok=False);bpy.ops.wm.open_mainfile(filepath=str(R/'canonical-anatomical-hand-cuffs.blend'));rig=bpy.data.objects['CC0AnatomicalHandRig'];meshes=[o for o in bpy.context.scene.objects if o.type=='MESH'and(o.name.startswith('CC0Adult_')or o.name.startswith('AnatomicalFittedHoodieCuff'))];assert len(meshes)==4
# Correct diagnostic body-reference UVs from original normalized uint16 decoding.
cloth=bpy.data.objects['EXACT_SERIALIZED_ORIGINAL_BODY_BIND_REFERENCE']
for loop in cloth.data.uv_layers.active.data:loop.uv=(loop.uv.x/65535,1+(loop.uv.y-1)/65535)
before={o.name:([tuple(v.co)for v in o.data.vertices],[tuple(p.vertices)for p in o.data.polygons])for o in meshes};receipts=[]
for side in ['Left','Right']:
 o=bpy.data.objects['AnatomicalFittedHoodieCuff'+side];old=o.data.materials[0];palette=next(n for n in old.node_tree.nodes if n.type=='COMBXYZ');uv=(palette.inputs['X'].default_value/65535,1+(palette.inputs['Y'].default_value-1)/65535);principled=old.node_tree.nodes.get('Principled BSDF');link=principled.inputs['Base Color'].links[0];tex=link.from_node;assert tex.type=='TEX_IMAGE';image=tex.image;assert image and image.size[0]>0
 # Bilinear sample in the original image's actual wrap and pixel space.
 w,h=image.size;x=(uv[0]%1)*w-.5;y=(uv[1]%1)*h-.5;x0=math.floor(x);y0=math.floor(y);a=x-x0;b=y-y0;raw=[]
 for k in range(3):
  value=0
  for dx,wx in [(0,1-a),(1,a)]:
   for dy,wy in [(0,1-b),(1,b)]:value+=image.pixels[4*(((y0+dy)%h)*w+(x0+dx)%w)+k]*wx*wy
  raw.append(value)
 srgb=image.colorspace_settings.name=='sRGB';linear=[v/12.92 if v<=.04045 else((v+.055)/1.055)**2.4 for v in raw]if srgb else raw
 mat=bpy.data.materials.new('PortableOriginalHoodiePalette_Knit'+side);mat.use_nodes=True;nodes=mat.node_tree.nodes;links=mat.node_tree.links;p=nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(*linear,1);p.inputs['Roughness'].default_value=.82;p.inputs['Sheen Weight'].default_value=.2
 N=128;normal=bpy.data.images.new('Metric1p6mmKnitNormal'+side,width=N,height=N);normal.colorspace_settings.name='Non-Color';pixels=[]
 for yv in range(N):
  for xv in range(N):
   u=(xv+.5)/N;nx=-.00016*.65*2*math.pi/.0016*math.cos(2*math.pi*u);den=math.sqrt(1+nx*nx);pixels.extend((nx/den*.5+.5,.5,1/den*.5+.5,1))
 normal.pixels=pixels;normal.filepath_raw=str(out/(normal.name+'.png'));normal.file_format='PNG';normal.save();normal.pack();coord=nodes.new('ShaderNodeTexCoord');mapping=nodes.new('ShaderNodeMapping');mapping.inputs['Scale'].default_value=(625,625,1);links.new(coord.outputs['UV'],mapping.inputs['Vector']);texture=nodes.new('ShaderNodeTexImage');texture.image=normal;links.new(mapping.outputs['Vector'],texture.inputs['Vector']);nm=nodes.new('ShaderNodeNormalMap');links.new(texture.outputs['Color'],nm.inputs['Color']);links.new(nm.outputs['Normal'],p.inputs['Normal']);o.data.materials[0]=mat
 receipts.append({'side':side,'original_source_image':image.name,'original_photo_palette_uv':list(uv),'sampled_encoded_rgb':raw,'sampled_linear_rgb':linear,'source_color_space':image.colorspace_settings.name,'physical_wale_period_m':.0016,'physical_relief_m':.00016,'normal_texture_dimension':N,'normal_uv_metric_scale':625,'note':'Original source photographed hoodie palette; analytically baked physical knit normal, not scanned fabric claim'})
assert all(before[o.name]==([tuple(v.co)for v in o.data.vertices],[tuple(p.vertices)for p in o.data.polygons])for o in meshes)
bpy.ops.object.select_all(action='DESELECT')
for o in [rig,*meshes]:o.hide_set(False);o.select_set(True)
bpy.context.view_layer.objects.active=rig;bpy.ops.wm.save_as_mainfile(filepath=str(out/'canonical-anatomical-hand-cuffs-portable.blend'));bpy.ops.export_scene.gltf(filepath=str(out/'canonical-anatomical-hand-cuffs-portable.glb'),export_format='GLB',use_selection=True,export_animations=False,export_skins=True,export_all_influences=True)
r={'schema':'sub01.portable-canonical-cuff-materials.v1','geometry_source_sha256':'3aece8b34eebede7296ae83543c49d283e4a27018ec4a7aa625a0747cd3bedd0','output_sha256':hashlib.sha256((out/'canonical-anatomical-hand-cuffs-portable.glb').read_bytes()).hexdigest(),'all_source_geometry_and_topology_unchanged':True,'records':receipts,'native_imported':False,'native_material_accepted':False};(out/'portable-material-report.json').write_text(json.dumps(r,indent=2));print('PORTABLE_CANONICAL_MATERIALS',json.dumps(r),flush=True)
