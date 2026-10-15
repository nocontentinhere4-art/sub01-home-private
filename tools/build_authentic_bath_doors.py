"""Measured CC0 fixture and door source assembly. Blender server only; never native writes."""
import argparse,hashlib,json,math,sys
from pathlib import Path
HASHES={'vanity':'637357db5437087725b99993ca2682811ef01b38e8a7e1dd621b838fef4e1d5a','entry-door':'353b872e5b0dd352c9b8e29cc7caf021203aed4244e6bf160ba2b4a0c1afe50b','patio-door':'21cbdec583c798ac5aa94822e3f7275492e637887981d248620516fc0f226d84','pocket-door':'52cfbedd202e2259d23a9e78c3a3eabc3c782cb5dab62d3c63a2bf7ea1e25d9e','wallhung-wc':'11ceb10fcded6ca14c18bdc6a8b71bca371f40ab126d847148e6d7979b665401','shower-screen':'1f821d9e4fa6107dd0250fc675df8633d60fda95b05140b79a000bcbae84880d','shower-mixer':'1c0cc1d06113eedffbe624b844d987faabf5159ff98226b5d6e6d8854f4dc7f4','shower-head':'22dbe36180d61054a86f835dcad0777601e8c3978eafdb0428aeb78b738d3691'}
def build(source,output):
 import bpy,bmesh
 from mathutils import Matrix,Vector
 source,output=Path(source),Path(output);output.mkdir(parents=True,exist_ok=False);bpy.ops.wm.read_factory_settings(use_empty=True)
 groups={};provenance=[];changes=[]
 def load(key,xyz,yaw=0):
  file=source/(key+'.glb');assert hashlib.sha256(file.read_bytes()).hexdigest()==HASHES[key],key
  before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(file));added=[o for o in bpy.data.objects if o not in before];meshes=[o for o in added if o.type=='MESH']
  transform=Matrix.Translation(Vector((xyz[0]/100,-xyz[1]/100,xyz[2]/100)))@Matrix.Rotation(math.radians(-yaw),4,'Z')
  # Flatten imported hierarchy once, retaining evaluated source world placement exactly.
  for o in meshes:
   world=o.matrix_world.copy();o.parent=None;o.matrix_world=world
  for o in added:
   if o.type!='MESH':bpy.data.objects.remove(o,do_unlink=True)
  for i,o in enumerate(meshes):o['source_part_name']=o.name;o['source_key']=key;o.name='SUB01_'+key.replace('-','_')+'_'+str(i).zfill(3)
  groups[key]=meshes;provenance.append({'key':key,'sha256':HASHES[key],'placement_ue_cm':xyz,'yaw_degrees':yaw,'parts':len(meshes)})
  return meshes,transform
 def place(objects,matrix):
  for o in objects:o.matrix_world=matrix@o.matrix_world
 def mat(name,color,rough,metal=0,glass=0):
  m=bpy.data.materials.new(name);m.use_nodes=True;s=m.node_tree.nodes['Principled BSDF'];s.inputs['Base Color'].default_value=(*color,1);s.inputs['Roughness'].default_value=rough;s.inputs['Metallic'].default_value=metal;s.inputs['Transmission Weight'].default_value=glass;return m
 plaster=mat('Bathroom lime mineral finish',(.72,.70,.65),.88);steel=mat('Bathroom brushed stainless construction',(.48,.50,.51),.24,.95);rubber=mat('Door perimeter EPDM seal',(.012,.012,.011),.8);glass=mat('Door clear glazing',(.97,.99,1),.03,0,1)
 extras=[]
 def box(name,lo,hi,material,bevel=.001):
  # Public input is native centimetres, mesh is baked in Blender metres.
  a=Vector((lo[0]/100,-hi[1]/100,lo[2]/100));b=Vector((hi[0]/100,-lo[1]/100,hi[2]/100));bpy.ops.mesh.primitive_cube_add(size=1,location=(a+b)/2);o=bpy.context.object;o.name='SUB01_'+name;o.dimensions=b-a;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(material)
  if bevel:
   mod=o.modifiers.new('Physical manufactured edge','BEVEL');mod.width=bevel;mod.segments=3;bpy.ops.object.modifier_apply(modifier=mod.name)
  uv=o.data.uv_layers.active
  if uv is None:uv=o.data.uv_layers.new()
  extras.append(o);return o
 def tube(name,a,b,r,material):
  av=Vector((a[0]/100,-a[1]/100,a[2]/100));bv=Vector((b[0]/100,-b[1]/100,b[2]/100));d=bv-av;bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=r/100,depth=d.length,location=(av+bv)/2);o=bpy.context.object;o.name='SUB01_'+name;o.rotation_euler=d.to_track_quat('Z','Y').to_euler();o.data.materials.append(material);extras.append(o);return o
 objs,t=load('vanity',(-358.5,120,305.25),-90);place(objs,t)
 objs,t=load('wallhung-wc',(-290,217.7,315.75),180)
 # Preserve source bowl/seat and rotate the actual raised lid around its back
 # edge. The glTF hierarchy baked the original rotation into its mesh; resetting
 # the object quaternion alone leaves it vertical.
 place(objs,t)
 lid=next(o for o in objs if 'raised lid' in o['source_part_name'].lower())
 seat=next(o for o in objs if 'separate seat ring' in o['source_part_name'].lower())
 points=[lid.matrix_world@v.co for v in lid.data.vertices]
 lo=Vector(tuple(min(v[i] for v in points) for i in range(3)));hi=Vector(tuple(max(v[i] for v in points) for i in range(3)))
 hinge=Vector(((lo.x+hi.x)/2,(lo.y+hi.y)/2,lo.z))
 rotated=Matrix.Translation(hinge)@Matrix.Rotation(math.radians(-90),4,'X')@Matrix.Translation(-hinge)@lid.matrix_world
 closed=[rotated@v.co for v in lid.data.vertices]
 seat_top=max((seat.matrix_world@v.co).z for v in seat.data.vertices)
 dz=seat_top+.001-min(v.z for v in closed)
 lid.matrix_world=Matrix.Translation(Vector((0,0,dz)))@rotated
 changes.append({'part':lid['source_part_name'],'operation':'actual world hinge rotation -90 X then 1mm seat separation','seat_top_blender_m':seat_top,'lid_bottom_blender_m':seat_top+.001,'source_geometry_and_uv_retained':True})
 # Concealed cistern is a framed service cavity, not a box intersecting the pan.
 for name,lo,hi in [('WCServiceLeft',(-325,245,305.25),(-310,265,425.25)),('WCServiceRight',(-270,245,305.25),(-255,265,425.25)),('WCServiceAboveMount',(-310,245,350),(-270,247,425.25)),('WCServiceBelowMount',(-310,245,305.25),(-270,247,315.25)),('WCServiceTop',(-325,245,425.25),(-255,265,427.25))]:box(name,lo,hi,plaster)
 box('WCFlushPlate',(-301,244.3,402.75),(-279,244.9,417.75),steel,.003)
 for x0,x1 in [(-299.5,-291),(-290,-280.5)]:box('WCFlushButton', (x0,243.9,405),(x1,244.3,415.5),steel,.002)
 objs,t=load('shower-screen',(-198,219.5,305.25),-90)
 # Reflect depth toward the real east return wall; extend only the actual brace axis.
 for o in objs:
  o.matrix_world=Matrix.Diagonal((1,-1,1,1))@o.matrix_world
  if any(s in o['source_part_name'].lower()for s in ('brace','rosette')):
   o.matrix_world=Matrix.Diagonal((1,.93/.7225,1,1))@o.matrix_world
 place(objs,t)
 # Source channel is centered on wallface; mount its back flush instead of
 # burying half the whole198cm channel in the protected real wall.
 for o in objs:
  if 'wall-side channel' in o['source_part_name'].lower():
   o.matrix_world=Matrix.Translation(Vector((0,.0145,0)))@o.matrix_world
   changes.append({'part':o['source_part_name'],'operation':'flush northwall channel mounting','native_y_translation_cm':-1.45})
 objs,t=load('shower-mixer',(-150,252.8,405.25),180);place(objs,t)
 objs,t=load('shower-head',(-150,230,515.25));place(objs,t)
 tube('ShowerWallArm',(-150,264.8,526),(-150,230,526),1,steel);tube('ShowerHeadDrop',(-150,230,526),(-150,230,523.6),1,steel)
 tube('ShowerSupplyCap',(-150,252.8,405.25),(-150,252.8,404),.9,steel)
 # Entry source is a complete real leaf/frame/latch/hinge assembly under measured257.5cm head.
 objs,t=load('entry-door',(199.5,400,2.5));place(objs,t)
 for label,lo,hi in [('EntryLeftReveal',(145,391,2.5),(148.1,409,214)),('EntryRightReveal',(250.9,391,2.5),(255,409,214)),('EntryTransomHead',(145,391,253.5),(255,409,257.5)),('EntryTransomBottom',(148.1,391,214),(250.9,409,218))]:box(label,lo,hi,plaster)
 box('EntryTransomGlass',(148.1,399.7,218),(250.9,400.3,253.5),glass,0)
 # Bathroom exposed-track sliding system: retain real timber leaf/pull/track and frame;
 # omit concealed pocket studs explicitly because the measured wall has no pocket cavity.
 objs,t=load('pocket-door',(-88.8,130,305.25),-90);retained=[];omitted=[]
 for o in objs:
  name=o['source_part_name'].lower()
  if 'steel stud'in name or'horizontal stiffener'in name:omitted.append(o['source_part_name']);bpy.data.objects.remove(o,do_unlink=True);continue
  if 'continuous head track' in name:
   o.matrix_world=Matrix.Translation(Vector((-.9225,0,0)))@o.matrix_world
  if any(s in name for s in ('sliding timber leaf','dark pull well','recessed pull rim')):
   o.matrix_world=Matrix.Translation(Vector((-.224,0,0)))@o.matrix_world
  retained.append(o)
 groups['pocket-door']=retained;place(retained,t);changes.append({'assembly':'bathroom door','explicit_omitted_concealed_pocket_parts':omitted,'leaf_closed_translation_source_x_m':-.224,'track_translation_source_x_m':-.9225,'operational_native_ready':False})
 # Real patio unit fits beneath measured545cm upper lintel; fixed sidelights fill aperture.
 objs,t=load('patio-door',(-220,400,302.5));place(objs,t)
 for name,lo,hi in [('BalconyLeftJamb',(-385,391,302.5),(-380,409,545)),('BalconyRightJamb',(-20,391,302.5),(-15,409,545)),('BalconyHead',(-385,391,540),(-15,409,545)),('BalconyUnitHead',(-322.1,391,523),(-117.9,409,527))]:box(name,lo,hi,plaster)
 for name,lo,hi in [('BalconyLeftLight',(-380,399.7,307.5),(-322.1,400.3,540)),('BalconyRightLight',(-117.9,399.7,307.5),(-20,400.3,540)),('BalconyTransom',(-322.1,399.7,527),(-117.9,400.3,540))]:box(name,lo,hi,glass,0)
 groups['construction']=extras;rows=[]
 for key,objects in groups.items():
  for o in objects:
   # Bake world TRS including reflection, recalculate outward normals, keep source UVs.
   matrix=o.matrix_world.copy();o.data.transform(matrix);o.matrix_world=Matrix.Identity(4);bm=bmesh.new();bm.from_mesh(o.data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(o.data);bm.free();o.data.calc_loop_triangles();p=[v.co for v in o.data.vertices];ue=[(v.x*100,-v.y*100,v.z*100)for v in p]
   rows.append({'name':o.name,'group':key,'source_part':o.get('source_part_name'),'triangles':len(o.data.loop_triangles),'bounds_ue_cm':[[min(v[i]for v in ue)for i in range(3)],[max(v[i]for v in ue)for i in range(3)]],'materials':[m.name for m in o.data.materials]})
  bpy.ops.object.select_all(action='DESELECT')
  for o in objects:o.select_set(True)
  bpy.ops.export_scene.gltf(filepath=str(output/(key+'.glb')),export_format='GLB',use_selection=True,export_yup=True,export_texcoords=True,export_normals=True,export_materials='EXPORT')
 fixtures=[o for k,objects in groups.items() for o in objects if k in ('vanity','wallhung-wc','shower-screen','shower-mixer','shower-head') or (k=='construction' and (o.name.startswith('SUB01_WC') or o.name.startswith('SUB01_Shower')))]
 bpy.ops.object.select_all(action='DESELECT')
 for o in fixtures:o.select_set(True)
 bpy.ops.export_scene.gltf(filepath=str(output/'bath-fixtures.glb'),export_format='GLB',use_selection=True,export_yup=True,export_texcoords=True,export_normals=True,export_materials='EXPORT')
 doorparts=[o for k,objects in groups.items() for o in objects if k in ('entry-door','pocket-door','patio-door') or (k=='construction' and not(o.name.startswith('SUB01_WC')or o.name.startswith('SUB01_Shower')))]
 bpy.ops.object.select_all(action='DESELECT')
 for o in doorparts:o.select_set(True)
 bpy.ops.export_scene.gltf(filepath=str(output/'door-assemblies.glb'),export_format='GLB',use_selection=True,export_yup=True,export_texcoords=True,export_normals=True,export_materials='EXPORT')
 bpy.ops.wm.save_as_mainfile(filepath=str(output/'editable-bath-doors.blend'))
 roles={'bathroom':{'moving_parts':[o.name for o in groups['pocket-door']if any(s in o.get('source_part_name','').lower()for s in ('sliding timber leaf','dark pull well','recessed pull rim'))],'motion':'native Y +95cm','closed_leaf_bounds_ue_cm':next(r['bounds_ue_cm']for r in rows if r['source_part']=='Pocket | sliding timber leaf'),'native_runtime_binding_ready':False},'entry':{'moving_parts':[o.name for o in groups['entry-door']if not o.get('source_part_name','').startswith('Frame |')],'hinge_ue_cm':[154.3,402.2,2.5],'native_runtime_binding_ready':False},'balcony':{'moving_parts':['SUB01_patio_door_'+str(i).zfill(3)for i in (6,7,10,12,13,19,21,22)],'motion':'native X +91cm','native_runtime_binding_ready':False}}
 report={'schema':'sub01.authentic-bath-door-fit-source.v1','sources':provenance,'changes':changes,'parts':rows,'exports':{k:hashlib.sha256((output/(k+'.glb')).read_bytes()).hexdigest()for k in groups},'door_bundle_sha256':hashlib.sha256((output/'door-assemblies.glb').read_bytes()).hexdigest(),'door_parts':[o.name for o in doorparts],'door_roles':roles,'fixture_parts':[o.name for o in fixtures],'fixture_sha256':hashlib.sha256((output/'bath-fixtures.glb').read_bytes()).hexdigest(),'native_imported':False,'runtime_doors_ready':False,'source_collision_proof_complete':False,'visual_review_complete':False,'protected_stairs_and_chair_unchanged':True}
 (output/'source-report.json').write_text(json.dumps(report,indent=2)+'\n');print('BATH_DOOR_FITTED_SOURCE_EXPORTED',len(rows),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True);a=p.parse_args(sys.argv[sys.argv.index('--')+1:]if'--'in sys.argv else None);build(a.source,a.output)
