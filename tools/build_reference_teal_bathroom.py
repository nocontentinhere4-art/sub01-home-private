"""Private Blender authoring against the owner's three teal bathroom photos.

The saved native home is never edited here. Fixtures retain their measured
placement; the new paint film, joinery profiles and finish changes are exported
separately for a later verified Editor integration.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path


def main():
 import bpy
 from mathutils import Vector
 parser=argparse.ArgumentParser()
 parser.add_argument('--fixtures',type=Path,required=True)
 parser.add_argument('--maps',type=Path,required=True)
 parser.add_argument('--output',type=Path,required=True)
 args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
 expected='b8d190b7d7cf274126b4be35cf2ccf447b25c742da037cc222c43fe57f437a92'
 assert hashlib.sha256(args.fixtures.read_bytes()).hexdigest()==expected
 args.output.mkdir(parents=True,exist_ok=False)
 bpy.ops.wm.read_factory_settings(use_empty=True)
 bpy.ops.import_scene.gltf(filepath=str(args.fixtures))
 fixtures=[o for o in bpy.context.scene.objects if o.type=='MESH']
 assert len(fixtures)==90
 def fingerprint(o):
  import struct
  return hashlib.sha256(b''.join(struct.pack('<3d',*(o.matrix_world@v.co))for v in o.data.vertices)).hexdigest()
 originals={o.name:fingerprint(o)for o in fixtures}
 def linear(v):
  v=v/255.;return v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4
 def material(name,rgb,rough=.5,metal=0):
  m=bpy.data.materials.new(name);m.use_nodes=True
  s=m.node_tree.nodes.get('Principled BSDF');s.inputs['Base Color'].default_value=(*[linear(v)for v in rgb],1)
  s.inputs['Roughness'].default_value=rough;s.inputs['Metallic'].default_value=metal
  return m
 teal=material('TB00',(66,94,101),.48)
 trim=material('TB01',(70,98,105),.4)
 brass=material('TB02',(173,132,73),.29,.82)
 white=material('TB03',(237,234,225),.34)
 wood=material('TB04',(255,255,255),.43)
 nodes=wood.node_tree.nodes;links=wood.node_tree.links;s=nodes.get('Principled BSDF')
 images={}
 for role,file in [('diff','diff.jpg'),('rough','rough.jpg'),('normal','normal.jpg')]:
  path=args.maps/file;image=bpy.data.images.load(str(path),check_existing=True);image.pack();images[role]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
  if role!='diff':image.colorspace_settings.name='Non-Color'
  n=nodes.new('ShaderNodeTexImage');n.image=image
  if role=='diff':
   grade=nodes.new('ShaderNodeMixRGB');grade.blend_type='MULTIPLY';grade.inputs[0].default_value=1;grade.inputs[2].default_value=(.46,.32,.23,1);links.new(n.outputs['Color'],grade.inputs[1]);links.new(grade.outputs['Color'],s.inputs['Base Color'])
  elif role=='rough':links.new(n.outputs['Color'],s.inputs['Roughness'])
  else:
   normal=nodes.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=.22;links.new(n.outputs['Color'],normal.inputs['Color']);links.new(normal.outputs['Normal'],s.inputs['Normal'])
 def wood_uv(o):
  """Metric face-tangent projection; no collapsed side/bevel UV surfaces."""
  uv=o.data.uv_layers.active or o.data.uv_layers.new()
  transform=o.matrix_world.to_3x3().inverted().transposed()
  for face in o.data.polygons:
   normal=transform@face.normal;axis=max(range(3),key=lambda i:abs(normal[i]))
   for li in face.loop_indices:
    p=o.matrix_world@o.data.vertices[o.data.loops[li].vertex_index].co
    uv.data[li].uv=((p.z,-p.y)if axis==0 else(p.z,p.x)if axis==1 else(p.x,-p.y))
    uv.data[li].uv/=1.83
 changed=[]
 for o in fixtures:
  name=o.name
  if name in ('SUB01_vanity_004','SUB01_vanity_017','SUB01_vanity_018','SUB01_vanity_016'):
   o.data.materials.clear();o.data.materials.append(wood)
   wood_uv(o)
   changed.append({'part':name,'finish':'photographed CC0 oak veneer, warm walnut tint, metric 1.83m UVs'})
  elif name=='SUB01_vanity_005':
   o.data.materials.clear();o.data.materials.append(white);changed.append({'part':name,'finish':'quiet warm white solid surface'})
  elif name in ('SUB01_vanity_001','SUB01_vanity_014') or any('steel' in m.name.lower() or 'brass' in m.name.lower() for m in o.data.materials if m):
   if 'shower_screen'not in name:
    o.data.materials.clear();o.data.materials.append(brass);changed.append({'part':name,'finish':'satin brass hardware'})
  elif name.startswith('SUB01_WCService'):
   o.data.materials.clear();o.data.materials.append(teal);changed.append({'part':name,'finish':'teal concealed cistern joinery'})
 assert {o.name:fingerprint(o)for o in fixtures}==originals,'Fixture surfaces or placement changed'
 dressing=[]
 def box(name,lo,hi,mat,bevel=.0005):
  a=Vector((lo[0]/100,-hi[1]/100,lo[2]/100));b=Vector((hi[0]/100,-lo[1]/100,hi[2]/100))
  bpy.ops.mesh.primitive_cube_add(size=1,location=(a+b)/2);o=bpy.context.object;o.name=name;o.dimensions=b-a;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(mat)
  if bevel:
   m=o.modifiers.new('Rounded painted joinery edge','BEVEL');m.width=min(bevel,min(o.dimensions)*.2);m.segments=3;bpy.ops.object.modifier_apply(modifier=m.name)
  dressing.append(o);return o
 # A real paint film, not a new obstacle or a thick box through the fixtures.
 box('TB_WestPaintFilm',(-391,55.1,305.3),(-390.95,264.9,588.3),teal,0)
 box('TB_SouthPaintFilm',(-391,55,305.3),(-106,55.05,588.3),teal,0)
 # Cistern occupies the rear wall below 427.25cm: leave that service cavity clear.
 northpaint=box('TB_NorthUpperPaint',(-391,264.95,427.3),(-106,265,588.3),teal,0)
 box('TB_NorthLeftPaint',(-391,264.95,305.3),(-325.05,265,427.3),teal,0)
 # Close the measured3.5cm end gaps. End-face source vertices show actual
 # corridor wall z303.5..588.5cm; these SOLIDS join the existing wall end and
 # exterior-wall inner face, rather than a floating paint strip hiding a hole.
 for label,y0,y1 in [('North',265,275),('South',45,55)]:
  box('TB_CornerWallEnd_'+label,(-391,y0,303.5),(-387.5,y1,588.5),teal,0)
 def clearance_cutter(source,margin_m,solid_envelope=False):
  import bmesh
  clone=source.copy();clone.data=source.data.copy();bpy.context.collection.objects.link(clone);world=source.matrix_world.copy();clone.parent=None;clone.matrix_world.identity()
  for v in clone.data.vertices:v.co=world@v.co
  bm=bmesh.new()
  if solid_envelope:
   for vertex in clone.data.vertices:bm.verts.new(vertex.co)
   result=bmesh.ops.convex_hull(bm,input=list(bm.verts),use_existing_faces=False)
   unused=[v for v in result.get('geom_interior',[])+result.get('geom_unused',[])if isinstance(v,bmesh.types.BMVert)]
   if unused:bmesh.ops.delete(bm,geom=list(set(unused)),context='VERTS')
  else:bm.from_mesh(clone.data)
  bmesh.ops.recalc_face_normals(bm,faces=bm.faces)
  signed=bm.calc_volume(signed=True)
  if signed<0:bmesh.ops.reverse_faces(bm,faces=bm.faces)
  bm.normal_update()
  for v in bm.verts:v.co+=v.normal*margin_m
  bm.to_mesh(clone.data);bm.free();clone.data.update()
  return clone
 def subtract(target,source,margin_m,solid_envelope=False):
  cutter=clearance_cutter(source,margin_m,solid_envelope);bpy.context.view_layer.update();bpy.context.view_layer.objects.active=target
  mod=target.modifiers.new('Measured source clearance cut','BOOLEAN');mod.operation='DIFFERENCE';mod.solver='EXACT';mod.object=cutter
  bpy.ops.object.modifier_apply(modifier=mod.name);bpy.data.objects.remove(cutter,do_unlink=True);target.data.materials.clear();target.data.materials.append(teal)
  for f in target.data.polygons:f.material_index=0
 # Paint cannot occupy fixed metal. Mask the ACTUAL rear-channel geometry,
 # including its moulded edge profile, with0.02mm source cutter clearance.
 rear=bpy.data.objects.get('SUB01_shower_screen_005');assert rear
 subtract(northpaint,rear,.00002)
 # The existing service frame has a real40x34.75cm opening at y245..247.
 # Add a2cm flush solid panel and carve around the ACTUAL ceramic/outlet/seat
 # geometry. The original90 fixture meshes remain completely untouched.
 cover=box('TB_WCFlushServiceCover',(-310,245,315.25),(-270,247,350),teal,0)
 cutters=[o for o in fixtures if o.name in ('SUB01_wallhung_wc_000','SUB01_wallhung_wc_002','SUB01_wallhung_wc_005')]
 assert len(cutters)==3
 for source in cutters:subtract(cover,source,.001,solid_envelope=True)
 assert len(cover.data.polygons)>0,'Measured service cover was completely removed'
 assert {o.name:fingerprint(o)for o in fixtures}==originals,'Clearance authoring changed original fixtures'
 # The shower stays a separate wet zone; the exposed vanity/WC side gets trim.
 def west_frame(name,y0,y1,z0,z1,width=1.8):
  for suffix,a,b in [('L',(y0,z0),(y0+width,z1)),('R',(y1-width,z0),(y1,z1)),('B',(y0+width,z0),(y1-width,z0+width)),('T',(y0+width,z1-width),(y1-width,z1))]:
   box(name+suffix,(-390.95,a[0],a[1]),(-390.2,b[0],b[1]),trim,.001)
 west_frame('TB_WestLowerLeft_',57,178,308,379)
 west_frame('TB_WestUpper_',60,180,402,526)
 west_frame('TB_WestSide_',187,258,311,526)
 # Picture-frame joinery around the existing real mirror, with mitred corners.
 def profile_frame():
  y0,y1,z0,z1=65,175,403.25,497.25;w=5
  polygons=[[(y0,z0),(y1,z0),(y1-w,z0+w),(y0+w,z0+w)],[(y1,z0),(y1,z1),(y1-w,z1-w),(y1-w,z0+w)],[(y1,z1),(y0,z1),(y0+w,z1-w),(y1-w,z1-w)],[(y0,z1),(y0,z0),(y0+w,z0+w),(y0+w,z1-w)]]
  for i,poly in enumerate(polygons):
   verts=[(x/100,-y/100,z/100)for x in(-386.75,-385.9)for y,z in poly];faces=[(3,2,1,0),(4,5,6,7)]+[(j,(j+1)%4,(j+1)%4+4,j+4)for j in range(4)]
   mesh=bpy.data.meshes.new('Mitred mirror moulding');mesh.from_pydata(verts,[],faces);mesh.update();o=bpy.data.objects.new('TB_MirrorMitre_'+str(i),mesh);bpy.context.collection.objects.link(o);o.data.materials.append(wood)
   bpy.context.view_layer.objects.active=o;m=o.modifiers.new('Manufactured edge radius','BEVEL');m.width=.001;m.segments=3;bpy.ops.object.modifier_apply(modifier=m.name)
   wood_uv(o)
   dressing.append(o)
 profile_frame()
 for n,objects in [('bath-style-fixtures',fixtures),('bath-style-dressing',dressing)]:
  bpy.ops.object.select_all(action='DESELECT')
  for o in objects:o.select_set(True)
  bpy.ops.export_scene.gltf(filepath=str(args.output/(n+'.glb')),export_format='GLB',use_selection=True,export_cameras=False,export_lights=False)
 bpy.ops.wm.save_as_mainfile(filepath=str(args.output/'teal-bathroom.blend'))
 report={'schema':'sub01.reference-teal-bathroom-source.v1','source_sha256':expected,'native_imported':False,'native_visual_verified':False,'human_walk_untouched':True,'fixture_parts':len(fixtures),'all_original_fixture_vertices_and_placement_unchanged':True,'fixture_geometry_fingerprints':originals,'finish_changes':changed,'dressing_parts':len(dressing),'new_dressing_collision_policy':'Paint/trim NoCollision; new measured corner wall-end solids and WC cover require BlockAll only after independent complete contact/sweep proof. Existing actual wall, door, privacy and fixture collision states remain unchanged.', 'new_solid_parts':['TB_CornerWallEnd_North','TB_CornerWallEnd_South','TB_WCFlushServiceCover'],'clearance_authoring':{'service_cover_native_bounds_cm':[[-310,245,315.25],[-270,247,350]],'WC_cutter_parts':[o.name for o in cutters],'WC_outward_vertex_normal_cutter_offset_cm':.1,'minimum_actual_clearance_must_be_independently_measured_cm':.05,'WC_cutter_geometry':'Conservative CLOSED convex envelopes of each real physical source part separately; original UV-split/compound accessory topology is never treated as an unbounded subtractor. Measured final clearance required.','shower_channel_mask_part':'SUB01_shower_screen_005','shower_cutter_offset_cm':.002,'corner_wall_end_z_cm':[303.5,588.5]},'texture_source':'https://polyhaven.com/a/oak_veneer_01','texture_license':'CC0-1.0','texture_images':images,'reference':'Owner supplied three teal bathroom photographs on 2026-10-15; no photos copied into assets','files':{n:hashlib.sha256((args.output/n).read_bytes()).hexdigest()for n in('bath-style-fixtures.glb','bath-style-dressing.glb')}}
 (args.output/'source-report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items()if k!='fixture_geometry_fingerprints'}),flush=True)


if __name__=='__main__':main()
