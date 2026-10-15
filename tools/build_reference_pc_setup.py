"""Private Blender source PC dressing against the owner's photograph.

Never opens or mutates the native home. Existing PC/keyboard/mouse/chair bindings
are context only, never exported in the dressing. Original authored furniture,
real source oak and genuine CC0 PolyHaven plant geometry; no fake plant planes.
"""
import argparse,hashlib,json,math,sys,struct,copy
from pathlib import Path
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
HOME_SHA='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'

def build(home,output):
 home=Path(home);out=Path(output);out.mkdir(parents=True,exist_ok=False)
 raw=home.read_bytes();assert hashlib.sha256(raw).hexdigest()==HOME_SHA,'Pinned actual source required'
 size=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+size]);rest=raw[20+size:]
 for i,n in enumerate(doc['nodes']):n['name']=f'PCSource_{i:04d}'
 for i,n in enumerate(doc.get('meshes',[])):n['name']=f'PCMesh_{i:04d}'
 js=json.dumps(doc,separators=(',',':')).encode();js+=b' '*(-len(js)%4)
 source=out/'context-original-legal.glb';source.write_bytes(struct.pack('<4sII',b'glTF',2,20+len(js)+len(rest))+struct.pack('<II',len(js),0x4e4f534a)+js+rest)
 bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(source),merge_vertices=False);bpy.context.view_layer.update()
 context_ids={73,74,75,181,182,184,185,186,187,188,236,237,238}
 plant_ids={201,202,203,204};context=[];templates=[]
 for obj in list(bpy.data.objects):
  try:idx=int(obj.name.split('_')[1])if obj.name.startswith('PCSource_')else -1
  except ValueError:idx=-1
  if obj.type=='MESH'and idx in context_ids|plant_ids:
   w=obj.matrix_world.copy();obj.parent=None;obj.matrix_world=w
   (templates if idx in plant_ids else context).append(obj)
  else:bpy.data.objects.remove(obj,do_unlink=True)
 bpy.context.view_layer.update()
 def signature(o):
  return hashlib.sha256(repr((tuple(tuple(o.matrix_world@v.co)for v in o.data.vertices),tuple(tuple(p.vertices)for p in o.data.polygons),tuple(tuple(x.uv)for l in o.data.uv_layers for x in l.data))).encode()).hexdigest()
 protected=[o for o in context if int(o.name.split('_')[1])not in(181,182,238)]
 assert {73,74,75,184,185,186,187,236,237} <= {int(o.name.split('_')[1])for o in protected},'Required fixed PC/device context absent'
 before={o.name:signature(o)for o in protected};new=[];desk=[]
 # Use the COMPLETE genuine licensed LINEA140 desk at its reviewed actual
 #84.5cm support height. Do not ship the old generated desk as replacement.
 old_desk=[o for o in context if int(o.name.split('_')[1])in(181,182)]
 for o in old_desk:context.remove(o);bpy.data.objects.remove(o,do_unlink=True)
 desk_source=Path('/workspace/sub01-home-private/source-candidates/linea140/source.glb')
 assert hashlib.sha256(desk_source.read_bytes()).hexdigest()=='99bdf3fd42eea5fc4cb2fadd52c8cae18c4459a94000b85f7df4c515234ba43d'
 existing=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(desk_source),merge_vertices=False);bpy.context.view_layer.update()
 imported=[o for o in bpy.data.objects if o not in existing];desk=[o for o in imported if o.type=='MESH'];scale=(.845-.025)/.755
 assert sum(len(o.data.polygons)for o in desk)==20024,'Complete genuine desk source required'
 original_world={o:o.matrix_world.copy()for o in desk};origin=Vector((2.1,3.02,.025))
 for i,o in enumerate(desk):
  o.parent=None;o.matrix_world=original_world[o];o.location=o.location*scale+origin;o.scale*=scale;o.name=f'SUB01_PCDesk_Part{i:04d}';o.data.name=o.name+'_Mesh'
 for o in imported:
  if o.type!='MESH':bpy.data.objects.remove(o,do_unlink=True)
 material_copies={}
 for o in desk:
  for j,m in enumerate(o.data.materials):
   if m not in material_copies:
    clone=m.copy();clone.name='PCDesk_'+m.name;material_copies[m]=clone
    if 'walnut'in m.name.lower():
     bs=clone.node_tree.nodes.get('Principled BSDF');socket=bs.inputs['Base Color']
     if socket.is_linked:
      old=socket.links[0].from_socket;mix=clone.node_tree.nodes.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs[0].default_value=1;mix.inputs[2].default_value=(.50,.46,.42,1);clone.node_tree.links.new(old,mix.inputs[1]);clone.node_tree.links.new(mix.outputs[0],socket)
   o.data.materials[j]=material_copies[m]
 bpy.context.view_layer.update()
 for o in context:
  if int(o.name.split('_')[1])==238:o.hide_render=True
 def mat(name,rgb,rough=.5,metal=0):
  m=bpy.data.materials.new(name);m.use_nodes=True;s=m.node_tree.nodes.get('Principled BSDF');s.inputs['Base Color'].default_value=(*rgb,1);s.inputs['Roughness'].default_value=rough;s.inputs['Metallic'].default_value=metal;return m
 black=mat('PCSetup_PowdercoatedCharcoal',(.011,.014,.015),.48,.3);rubber=mat('PCSetup_SoftRubber',(.009,.011,.012),.77);cone=mat('PCSetup_WovenSpeakerCone',(.035,.04,.042),.8);steel=mat('PCSetup_BlackSteelHardware',(.055,.06,.064),.3,.8);copper=mat('PCSetup_CopperDriverTrim',(.31,.16,.085),.32,.8)
 wood=next(m for m in material_copies.values()if 'longitudinal'in m.name.lower()).copy();wood.name='PCSetup_ActualSourceOakRiser'
 for node in wood.node_tree.nodes:
  if node.bl_idname=='ShaderNodeMixRGB'and node.blend_type=='MULTIPLY':node.inputs[2].default_value=(.8,.74,.67,1)
 # Subtle real scale weave, never an image of a keyboard or a fake screen.
 weave=mat('PCSetup_DeskmatWovenBlack',(.014,.018,.021),.88);bs=weave.node_tree.nodes.get('Principled BSDF');tex=weave.node_tree.nodes.new('ShaderNodeTexNoise');tex.inputs['Scale'].default_value=1250;tex.inputs['Roughness'].default_value=.7;bump=weave.node_tree.nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.15;bump.inputs['Distance'].default_value=.00018;weave.node_tree.links.new(tex.outputs['Fac'],bump.inputs['Height']);weave.node_tree.links.new(bump.outputs['Normal'],bs.inputs['Normal'])
 def finish(o,name,m):
  o.name='SUB01_PCSetup_'+name;o.data.name=o.name+'_Mesh';o.data.materials.append(m)
  for f in o.data.polygons:f.use_smooth=len(f.vertices)==4
  new.append(o);return o
 def box(name,pos,dims,m,bev=.001):
  bpy.ops.mesh.primitive_cube_add(size=1,location=pos);o=bpy.context.object;o.dimensions=dims;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
  if bev:
   mod=o.modifiers.new('Manufactured edge radius','BEVEL');mod.width=bev;mod.segments=4;bpy.ops.object.modifier_apply(modifier=mod.name)
  # Metric planar coordinates keep the original scan grain physical scale.
  uv=o.data.uv_layers.active or o.data.uv_layers.new(name='MetricSourceGrain')
  for f in o.data.polygons:
   for li in f.loop_indices:
    v=o.data.vertices[o.data.loops[li].vertex_index].co;uv.data[li].uv=(v.x/1.83,(v.y if abs(f.normal.z)>.7 else v.z)/1.83)
  return finish(o,name,m)
 def tube(name,points,radius,m,closed=False):
  c=bpy.data.curves.new(name,'CURVE');c.dimensions='3D';c.bevel_depth=radius;c.bevel_resolution=3;s=c.splines.new('POLY');s.points.add(len(points)-1)
  for p,v in zip(s.points,points):p.co=(*v,1)
  s.use_cyclic_u=closed;o=bpy.data.objects.new(name,c);bpy.context.collection.objects.link(o);bpy.context.view_layer.objects.active=o;o.select_set(True);bpy.ops.object.convert(target='MESH');o=bpy.context.object;o.select_set(False);return finish(o,name,m)
 def lathe(name,center,profile,m,segments=64):
  # Speaker faces point towards the user, Blender-Y. Profile=(radius,depth).
  vs=[];fs=[]
  for r,y in profile:
   for j in range(segments):
    a=2*math.pi*j/segments;vs.append((center[0]+r*math.cos(a),center[1]+y,center[2]+r*math.sin(a)))
  for i in range(len(profile)-1):
   for j in range(segments):
    a=i*segments+j;b=i*segments+(j+1)%segments
    fs.append((a,b+segments,a+segments)if profile[i][0]==0 else (a,b,b+segments)if profile[i+1][0]==0 else (a,b,b+segments,a+segments))
  mesh=bpy.data.meshes.new(name);mesh.from_pydata(vs,[],fs);mesh.update();o=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(o);return finish(o,name,m)
 # 0.7mm deskmat top stays0.3mm BELOW actual keyboard/mouse bottoms.
 box('BlackDeskmat',(2.145,2.95,.84535),(.95,.34,.0007),weave,.0003)
 # Real monitor stand is not raised: the riser is a fitted U around it.
 for name,x,w in [('Left',1.635,.57),('Right',2.365,.57)]:box('OakRiserWing'+name,(x,3.245,.924),(w,.25,.022),wood,.004)
 box('OakRiserRearBridge',(2.,3.36,.924),(.16,.020,.022),wood,.003)
 for x in(1.38,1.84,2.16,2.62):box('RiserLeg'+str(x),(x,3.245,.8835),(.018,.22,.077),black,.002)
 for side,x in[('Left',1.485),('Right',2.515)]:
  box(side+'SpeakerOakCabinet',(x,3.25,1.055),(.135,.17,.24),wood,.006)
  box(side+'SpeakerFrontBaffle',(x,3.161,1.055),(.125,.009,.225),black,.004)
  for role,z,r in[('Woofer',1.015,.046),('Tweeter',1.105,.021)]:
   lathe(side+role+'Surround',(x,3.152,z),[(r,-.001),(r*.97,-.003),(r*.9,-.005),(r*.82,-.003)],rubber)
   lathe(side+role+'Cone',(x,3.151,z),[(r*.82,0),(r*.65,.006),(r*.3,.018),(.0005,.022)],cone)
   lathe(side+role+'Trim',(x,3.153,z),[(r*1.08,.001),(r*1.08,-.001),(r,-.002)],copper)
  for dx in(-.046,.046):
   for z in(.966,1.144):lathe(side+'BaffleScrew'+str(dx)+str(z),(x+dx,3.153,z),[(0,0),(.002,0),(.002,.001)],steel,24)
  box(side+'SpeakerIsolationPad',(x,3.25,.9365),(.10,.14,.003),rubber,.001)
 # Perforated sheet with actual THROUGH holes and wall standoffs. No alpha decal.
 vs=[];fs=[];nx,nz=26,18;pitch=.05;radx=.004;rady=.012;cy=3.91
 for iz in range(nz):
  for ix in range(nx):
   x=1.45+(ix+.5)*pitch;z=1.57+(iz+.5)*pitch;start=len(vs)
   # Corresponding square-cell perimeter and ellipse are stitched into one sheet.
   for y in(cy-.002,cy+.002):
    for ring in(0,1):
     for j in range(16):
      a=2*math.pi*j/16;c,s=math.cos(a),math.sin(a)
      if ring==0:scale=.5*pitch/max(abs(c),abs(s));dx,dz=c*scale,s*scale
      else:dx,dz=radx*c,rady*s
      vs.append((x+dx,y,z+dz))
   for j in range(16):
    k=(j+1)%16;fs.extend([(start+j,start+k,start+16+k,start+16+j),(start+32+j,start+48+j,start+48+k,start+32+k),(start+16+j,start+16+k,start+48+k,start+48+j)])
 mesh=bpy.data.meshes.new('TrueSlottedPegboard');mesh.from_pydata(vs,[],fs);mesh.update();o=bpy.data.objects.new('Pegboard',mesh);bpy.context.collection.objects.link(o);finish(o,'TrueSlottedPegboard',black)
 for face in o.data.polygons:face.use_smooth=False
 for x in(1.43,2.77):box('PegboardFrame'+str(x),(x,3.91,2.02),(.015,.018,.93),black,.003)
 for z in(1.555,2.485):box('PegboardFrameZ'+str(z),(2.10,3.91,z),(1.355,.018,.015),black,.003)
 for x in(1.47,2.73):
  for z in(1.6,2.44):box('WallStandoff'+str(x)+str(z),(x,3.955,z),(.018,.086,.018),steel,.003)
 # Cable loops and manufactured hanging rail/trays mirror the real reference.
 for n,x in enumerate((1.98,2.20,2.40)):
  points=[(x+.055*math.cos(2*math.pi*j/80),3.865,2.18+.10*math.sin(2*math.pi*j/80))for j in range(80)];tube('CoiledCable'+str(n),points,.0027,rubber,True);box('CableHook'+str(n),(x,3.865,2.295),(.008,.08,.008),steel,.002)
 for n,(x,z,w)in enumerate([(1.58,1.63,.23),(2.54,2.08,.23),(2.15,1.65,.31)]):
  box('AccessoryTray'+str(n),(x,3.82,z),(w,.16,.014),black,.004)
  box('TrayLip'+str(n),(x,3.735,z+.022),(w,.008,.035),black,.002)
 # Reference-inspired real accessories: an articulated clamped microphone
 # and cushioned headphones, authored meshes rather than flat image cards.
 box('MicClampUpper',(1.39,3.31,.851),(.065,.08,.012),black,.003)
 box('MicClampLower',(1.39,3.31,.806),(.065,.08,.012),black,.003)
 box('MicClampBack',(1.36,3.31,.829),(.012,.08,.054),steel,.002)
 for n,pts in enumerate([[(1.39,3.31,.86),(1.31,3.33,1.28)],[(1.31,3.33,1.28),(1.38,3.30,1.67)],[(1.38,3.30,1.67),(1.52,3.20,1.64)]]):
  tube('MicrophoneBoomArm'+str(n),pts,.009,black)
  for q in pts:lathe('BoomHinge'+str(n)+str(q[2]),q,[(0,0),(.016,0),(.016,.008),(.013,.010)],steel,32)
 center=Vector((1.52,3.20,1.44));mic=lathe('MicrophoneBody',center,[(0,0),(.022,0),(.026,.012),(.026,.15),(.02,.175),(0,.18)],black)
 for v in mic.data.vertices:
  r=v.co-center;v.co=center+Vector((r.x,-r.z,r.y))
 for i in range(10):
  z=1.46+i*.012;points=[(1.52+.027*math.cos(2*math.pi*j/48),3.20+.027*math.sin(2*math.pi*j/48),z)for j in range(48)];tube('MicAcousticCageRing'+str(i),points,.0015,steel,True)
 tube('MicBalancedCable',[(1.52,3.20,1.44),(1.55,3.22,1.36),(1.50,3.28,1.31),(1.34,3.36,1.27),(1.40,3.37,.87)],.0023,rubber)
 for dx in(-.004,.004):
  points=[(1.81+(.086+dx)*math.cos(math.pi*j/64),3.79,2.04+(.105+dx)*math.sin(math.pi*j/64))for j in range(65)];tube('HeadphonePaddedBand'+str(dx),points,.005,rubber)
 for x in(1.724,1.896):
  box('HeadphoneYoke'+str(x),(x,3.79,2.025),(.012,.012,.08),steel,.004)
  box('HeadphoneOverEarCushion'+str(x),(x,3.79,1.985),(.036,.06,.085),rubber,.017)
 box('HeadphoneHook',(1.81,3.85,2.16),(.015,.13,.014),steel,.003)
 box('FloatingOakTopShelf',(2.1,3.84,2.405),(1.55,.24,.024),wood,.004)
 for x in(1.46,2.74):box('TopShelfWallBracket'+str(x),(x,3.94,2.36),(.025,.10,.09),black,.004)
 # Duplicate complete genuine CC0 photographed plant geometry with rigid/uniform
 # transformations. UV, source topology and all real leaf/pot materials retained.
 source_pts=[o.matrix_world@v.co for o in templates for v in o.data.vertices];lo=Vector([min(p[i]for p in source_pts)for i in range(3)]);hi=Vector([max(p[i]for p in source_pts)for i in range(3)]);plant_origin=Vector(((lo.x+hi.x)/2,(lo.y+hi.y)/2,lo.z));plant_proofs=[]
 for label,pos,width in [('TrayPlant',(1.58,3.80,1.637),.18),('UpperPlant',(2.54,3.79,2.087),.16),('FloorPlant',(3.60,3.4,.025),.42),('TopShelfPlant',(1.53,3.80,2.417),.19)]:
  scale=width/(hi.x-lo.x);parts=[]
  for src in templates:
   o=src.copy();o.data=src.data.copy();bpy.context.collection.objects.link(o);w=src.matrix_world.copy();o.parent=None;o.matrix_world.identity()
   for v in o.data.vertices:v.co=(w@v.co-plant_origin)*scale+Vector(pos)
   o.name='SUB01_PCSetup_'+label+'_'+src.name;new.append(o);parts.append(o)
  plant_proofs.append({'label':label,'genuine_source_nodes':sorted(plant_ids),'uniform_scale':scale,'source_topology_uv_materials_preserved':True,'source_width_m':hi.x-lo.x,'target_width_m':width})
 for o in templates:bpy.data.objects.remove(o,do_unlink=True)
 # Exposed filament practical: modeled glass envelope, socket, strain relief,
 # hanging cable and a warm physical light in the source review.
 lampx,lampy=2.90,3.72
 tube('LampCable',[(lampx,3.98,2.50),(lampx,3.79,2.48),(lampx,lampy,2.36),(lampx,lampy,1.88)],.003,rubber)
 box('LampWallBracket',(lampx,3.975,2.5),(.05,.045,.08),black,.006)
 glass=mat('PCSetup_BulbGlass',(.92,.90,.86),.12);g=glass.node_tree.nodes.get('Principled BSDF');g.inputs['Transmission Weight'].default_value=1;g.inputs['IOR'].default_value=1.46
 # Vertical lathe bulb envelope from UV sphere with pear-shaped profile.
 bpy.ops.mesh.primitive_uv_sphere_add(segments=48,ring_count=24,radius=1,location=(lampx,lampy,1.76));bulb=bpy.context.object
 for v in bulb.data.vertices:
  z=v.co.z;v.co.x*=.031*(.85-.2*z);v.co.y*=.031*(.85-.2*z);v.co.z*=.052
 finish(bulb,'PearGlassBulb',glass)
 box('BulbSocket',(lampx,lampy,1.83),(.033,.033,.064),black,.007)
 filament=mat('PCSetup_AmberFilament',(1,.31,.045),.4);bs=filament.node_tree.nodes.get('Principled BSDF');bs.inputs['Emission Color'].default_value=(1,.35,.055,1);bs.inputs['Emission Strength'].default_value=5
 points=[(lampx+.009*math.cos(2*math.pi*j/20),lampy+.009*math.sin(2*math.pi*j/20),1.725+.055*j/100)for j in range(101)];tube('CoiledWarmFilament',points,.00065,filament)
 bpy.context.view_layer.update()
 # Lower the complete wall composition to5cm over the unchanged monitor.
 for o in new:
  if any(k in o.name for k in ['Pegboard','WallStandoff','CoiledCable','CableHook','AccessoryTray','TrayLip','TrayPlant','UpperPlant']):o.location.z-=.14
 bpy.context.view_layer.update()
 # Protect existing device/contact source geometry/UV exactly.
 after={o.name:signature(o)for o in protected};assert before==after,'A functional source device changed'
 def world_geometry(o):
  pts=[o.matrix_world@v.co for v in o.data.vertices];faces=[tuple(p.vertices)for p in o.data.polygons];return pts,faces
 def bounds(o):
  pts,_=world_geometry(o);return [[fn(p[i]for p in pts)for i in range(3)]for fn in(min,max)]
 def bvh(o):p,f=world_geometry(o);return BVHTree.FromPolygons(p,f,all_triangles=False,epsilon=0)
 device_hits=[];pb={o.name:bvh(o)for o in protected};armbox=((1.74,2.72,.846),(2.58,3.10,1.05));arm_violations=[]
 for o in new:
  bb=bounds(o)
  if all(bb[1][i]>armbox[0][i]+1e-7 and bb[0][i]<armbox[1][i]-1e-7 for i in range(3)):arm_violations.append(o.name)
  for p in protected:
   other=bounds(p)
   if not all(bb[1][i]>=other[0][i]and bb[0][i]<=other[1][i]for i in range(3)):continue
   overlaps=bvh(o).overlap(pb[p.name])
   if overlaps:device_hits.append({'part':o.name,'device':p.name,'intersecting_triangle_pairs':len(overlaps)})
 proof={'schema':'sub01.reference-pc-dressing-source.v1','actual_native_imported':False,'functional_device_context_exported':False,'home_source_sha256':HOME_SHA,'protected_source_signatures':before,'protected_source_geometry_uv_unchanged':before==after,'protected_native_bindings_changed':False,'arm_clearance_box_blender_m':armbox,'arm_clearance_violations':arm_violations,'new_vs_protected_device_surface_intersections':device_hits,'genuine_desk_source_sha256':'99bdf3fd42eea5fc4cb2fadd52c8cae18c4459a94000b85f7df4c515234ba43d','complete_genuine_desk_source_triangles':20024,'desk_support_top_m':.845,'deskmat_top_m':.8457,'keyboard_mouse_bottom_m':.846,'unchanged_monitor_frame_native_cm':[[164,-331.75,94],[236,-328.25,138]],'real_source_plant_provenance':{'source':'https://polyhaven.com/a/potted_plant_01','license':'CC0','parts':plant_proofs},'furniture_authorship':'Original Blender objects modeled against owner photograph; not manufacturer CAD; existing source oak texture retained','retirement_plan_for_native_preflight':['Exact existing mousepad238 only when new mat verified','Existing behind-desk shelf only after current owner/path fingerprint','Complete genuine LINEA140 dark finish is separate source variant; verify current actual desk owner before applying'],'native_visual_physical_acceptance':False,'native_practical_light_plan':{'source':'reference warm filament pendant','native_position_cm':[290,-372,176],'intensity_lumens':60,'temperature_kelvin':2400,'radius_cm':160,'create_only_with_verified_imported_bulb_and_no_existing_matching_light':True}}
 assert not device_hits and not arm_violations,json.dumps({'device_hits':device_hits,'arm_violations':arm_violations})
 # Export only new source additions. Current functional screen UV/device tags
 # and accepted chair cannot be overwritten because they are absent here.
 proof['part_roles']={}
 for i,o in enumerate(new):
  proof['part_roles'][f'SUB01_PCSetup_Part{i:04d}']=o.name;o.name=f'SUB01_PCSetup_Part{i:04d}';o.data.name=o.name+'_Mesh'
 bpy.ops.object.select_all(action='DESELECT')
 for o in new:o.select_set(True)
 bpy.ops.export_scene.gltf(filepath=str(out/'pc-setup-dressing.glb'),export_format='GLB',use_selection=True,export_cameras=False,export_lights=False)
 bpy.ops.object.select_all(action='DESELECT')
 for o in desk:o.select_set(True)
 bpy.ops.export_scene.gltf(filepath=str(out/'pc-desk-dark-source-variant.glb'),export_format='GLB',use_selection=True,export_cameras=False,export_lights=False)
 # Context-only review photography. No fabricated application or gameplay.
 wall=mat('Review_WarmPlaster',(.25,.25,.22),.9);floor=mat('Review_WarmFloor',(.07,.055,.04),.7)
 def reviewbox(pos,dim,m):
  bpy.ops.mesh.primitive_cube_add(size=1,location=pos);o=bpy.context.object;o.dimensions=dim;o.data.materials.append(m)
 reviewbox((2.15,4.01,1.45),(3.8,.04,2.9),wall);reviewbox((2.15,3.,.0125),(3.8,3.,.025),floor)
 def area(name,pos,power,color,size,target):
  data=bpy.data.lights.new(name,'AREA');data.energy=power;data.color=color;data.shape='DISK';data.size=size;o=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(o);o.location=pos;o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler()
 area('Window daylight',(1,1.5,2.5),160,(.72,.83,1),2.5,(2,3.4,1.2));area('Warm practical',(lampx,lampy,1.76),12,(1,.48,.18),.10,(2.1,3.9,1.6));area('Camera soft fill',(4,1.4,2.2),90,(1,.9,.74),2,(2,3.4,1.1))
 scene=bpy.context.scene;scene.world=bpy.data.worlds.new('PCReviewWorld');scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=24;scene.cycles.use_denoising=True;scene.render.resolution_x=1280;scene.render.resolution_y=960;scene.render.resolution_percentage=100;scene.world.color=(.035,.035,.035);scene.view_settings.view_transform='AgX'
 cam=bpy.data.cameras.new('SourceReviewCamera');camera=bpy.data.objects.new('SourceReviewCamera',cam);bpy.context.collection.objects.link(camera);camera.location=(3.9,.85,1.85);camera.rotation_euler=(Vector((2.15,3.5,1.32))-camera.location).to_track_quat('-Z','Y').to_euler();cam.lens=35;scene.camera=camera
 bpy.ops.wm.save_as_mainfile(filepath=str(out/'pc-setup-source.blend'));scene.render.filepath=str(out/'pc-setup-lit-review.png');bpy.ops.render.render(write_still=True)
 camera.location=(3.9,0,1.8);camera.rotation_euler=(Vector((2.2,3.5,1.45))-camera.location).to_track_quat('-Z','Y').to_euler();cam.lens=28;scene.render.filepath=str(out/'pc-setup-full-review.png');bpy.ops.render.render(write_still=True)
 proof.update({'dressing_meshes':len(new),'dressing_triangles':sum(sum(len(p.vertices)-2 for p in o.data.polygons)for o in new),'files':{n:hashlib.sha256((out/n).read_bytes()).hexdigest()for n in ['pc-setup-dressing.glb','pc-desk-dark-source-variant.glb','pc-setup-source.blend','pc-setup-lit-review.png','pc-setup-full-review.png']}})
 (out/'source-proof.json').write_text(json.dumps(proof,indent=2)+'\n');print('PC_SOURCE_REVIEW_READY',json.dumps({'parts':len(new),'triangles':proof['dressing_triangles'],'device_hits':device_hits,'arm_violations':arm_violations}),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--home',required=True);p.add_argument('--output',required=True);a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);build(a.home,a.output)
