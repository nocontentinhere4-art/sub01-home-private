"""Reversible fitted garment cuff, derived from original hoodie surface and skin.
No hand geometry, weights or animation edits. Called from the source compositor.
"""
import bpy,bmesh,math
from mathutils import Vector,Matrix
from mathutils.bvhtree import BVHTree

def fitted_cuff(cloth,rig,hand,align,side,wrist,axis,roll):
 cloth.data.calc_loop_triangles();triangles=[tuple(t.vertices)for t in cloth.data.loop_triangles];points=[cloth.matrix_world@v.co for v in cloth.data.vertices];tree=BVHTree.FromPolygons(points,triangles,all_triangles=True,epsilon=0)
 hand.data.calc_loop_triangles();skin=BVHTree.FromPolygons([align@v.co for v in hand.data.vertices],[tuple(t.vertices)for t in hand.data.loop_triangles],all_triangles=True,epsilon=0)
 x=(roll-axis*roll.dot(axis)).normalized();z=x.cross(axis).normalized();N=64;depths=[-.056,-.05,-.04,-.025,-.01,.003];clearance=.002;thickness=.0012
 rays=[];seam_uv=[];uv=cloth.data.uv_layers.active;assert uv,'Actual garment UV source required'
 for j in range(N):
  direction=x*math.cos(j*2*math.pi/N)+z*math.sin(j*2*math.pi/N);center=wrist-axis*.055;hit,normal,ti,distance=tree.ray_cast(center,direction,.12)
  assert hit is not None and .012<distance<.1,'Actual original sleeve boundary ray missing'
  tri=cloth.data.loop_triangles[ti];a,b,c=[points[i]for i in tri.vertices];v0=b-a;v1=c-a;v2=hit-a;den=v0.dot(v0)*v1.dot(v1)-v0.dot(v1)**2;assert abs(den)>1e-18,'Degenerate garment source UV triangle'
  beta=(v1.dot(v1)*v2.dot(v0)-v0.dot(v1)*v2.dot(v1))/den;gamma=(v0.dot(v0)*v2.dot(v1)-v0.dot(v1)*v2.dot(v0))/den;weights=[1-beta-gamma,beta,gamma];source_uv=sum((uv.data[k].uv*w for k,w in zip(tri.loops,weights)),Vector((0,0)))
  beta_gradient=(v1.dot(v1)*axis.dot(v0)-v0.dot(v1)*axis.dot(v1))/den;gamma_gradient=(v0.dot(v0)*axis.dot(v1)-v0.dot(v1)*axis.dot(v0))/den;source_gradient=(uv.data[tri.loops[1]].uv-uv.data[tri.loops[0]].uv)*beta_gradient+(uv.data[tri.loops[2]].uv-uv.data[tri.loops[0]].uv)*gamma_gradient
  rays.append((direction,distance));seam_uv.append((source_uv,source_gradient))
 vertices=[];uvs=[];proof=[]
 for k,depth in enumerate(depths):
  t=k/(len(depths)-1);center=wrist+axis*depth
  for j,(direction,seam_radius)in enumerate(rays):
   hit,normal,ti,distance=skin.ray_cast(center,direction,.12)
   # Source hand's retained proximal cut is intentionally covered by this garment.
   required=distance+clearance+thickness if hit is not None else 0
   end_radius=required if hit is not None else seam_radius;radius=max(seam_radius*(1-t)+end_radius*t,required)
   assert math.isfinite(radius) and thickness<radius<.1,('Measured fitted cuff radius invalid',side,k,j,radius,seam_radius,required)
   vertices.append(center+direction*radius);uvs.append(Vector((j/N*2*math.pi*radius,depth)));proof.append({'ring':k,'ray':j,'depth_m':depth,'skin_radius_m':distance if hit is not None else None,'outer_radius_m':radius,'clearance_plus_thickness_m':clearance+thickness})
 ring_circumferences=[]
 for k in range(len(depths)):
  circumference=0
  for j in range(N):
   uvs[k*N+j]=Vector((circumference,depths[k]));circumference+=(vertices[k*N+(j+1)%N]-vertices[k*N+j]).length
  ring_circumferences.append(circumference)
 faces=[]
 for k in range(len(depths)-1):
  for j in range(N):faces.append((k*N+j,(k+1)*N+j,(k+1)*N+(j+1)%N,k*N+(j+1)%N))
 # Retire the unsuitable original cuff and old hand remnants only in this copy.
 # Bisect the actual garment surface, rather than cutting through new anatomy.
 bm=bmesh.new();bm.from_mesh(cloth.data);selected=[]
 for f in bm.faces:
  center=cloth.matrix_world@f.calc_center_median();offset=center-wrist;axial=offset.dot(axis);radial=(offset-axis*axial).length
  if axial>-.08 and axial<.24 and radial<.13:selected.append(f)
 geom=set(selected)
 for f in selected:geom.update(f.edges);geom.update(f.verts)
 plane=cloth.matrix_world.inverted()@(wrist-axis*.055);normal=(cloth.matrix_world.to_3x3().transposed()@axis).normalized();bmesh.ops.bisect_plane(bm,geom=list(geom),plane_co=plane,plane_no=normal,dist=1e-7,clear_outer=True,clear_inner=False);bm.to_mesh(cloth.data);bm.free()
 mesh=bpy.data.meshes.new('AnatomicalFittedHoodieCuff'+side);mesh.from_pydata(vertices,[],faces);mesh.update();layer=mesh.uv_layers.new(name='OriginalGarmentSourceUV')
 for p in mesh.polygons:
  wrap=any(mesh.loops[i].vertex_index%N==N-1 for i in p.loop_indices)and any(mesh.loops[i].vertex_index%N==0 for i in p.loop_indices)
  for loop in p.loop_indices:
   vertex=mesh.loops[loop].vertex_index;value=uvs[vertex].copy()
   if wrap and vertex%N==0:value.x=ring_circumferences[vertex//N]
   layer.data[loop].uv=value
 cuff=bpy.data.objects.new('AnatomicalFittedHoodieCuff'+side,mesh);bpy.context.scene.collection.objects.link(cuff);assert cloth.data.materials;material=cloth.data.materials[0].copy();material.name='OriginalHoodiePalette_MetricKnitCuff'+side;material.use_nodes=True;nodes=material.node_tree.nodes;links=material.node_tree.links;p=nodes.get('Principled BSDF');assert p
 # Keep original source photographic colour/PBR lookup, on a real sleeve texel.
 palette=nodes.new('ShaderNodeCombineXYZ');palette.inputs['X'].default_value=seam_uv[N//2][0].x;palette.inputs['Y'].default_value=seam_uv[N//2][0].y
 for node in list(nodes):
  if node.type=='TEX_IMAGE':
   for link in list(node.inputs['Vector'].links):links.remove(link)
   links.new(palette.outputs['Vector'],node.inputs['Vector'])
 for link in list(p.inputs['Normal'].links):links.remove(link)
 tex=nodes.new('ShaderNodeTexCoord');separate=nodes.new('ShaderNodeSeparateXYZ');links.new(tex.outputs['UV'],separate.inputs['Vector']);frequency=nodes.new('ShaderNodeMath');frequency.operation='MULTIPLY';frequency.inputs[1].default_value=2*math.pi/.0016;links.new(separate.outputs['X'],frequency.inputs[0]);sine=nodes.new('ShaderNodeMath');sine.operation='SINE';links.new(frequency.outputs[0],sine.inputs[0]);bump=nodes.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.00016;bump.inputs['Strength'].default_value=.65;links.new(sine.outputs[0],bump.inputs['Height']);links.new(bump.outputs['Normal'],p.inputs['Normal']);p.inputs['Roughness'].default_value=.82;p.inputs['Sheen Weight'].default_value=.2
 mesh.materials.append(material);cuff.parent=rig;cuff.matrix_parent_inverse=rig.matrix_world.inverted();cuff.matrix_basis=Matrix.Identity(4)
 fore=cuff.vertex_groups.new(name='mixamorig:'+side+'ForeArm');wrist_group=cuff.vertex_groups.new(name='mixamorig:'+side+'Hand')
 for k in range(len(depths)):
  weight=k/(len(depths)-1);indices=list(range(k*N,(k+1)*N))
  if weight<1:fore.add(indices,1-weight,'REPLACE')
  if weight>0:wrist_group.add(indices,weight,'REPLACE')
 bpy.ops.object.select_all(action='DESELECT');cuff.select_set(True);bpy.context.view_layer.objects.active=cuff
 solid=cuff.modifiers.new('Measured knit fabric thickness1p2mm','SOLIDIFY');solid.thickness=thickness;solid.offset=-1;solid.use_even_offset=True;bpy.ops.object.modifier_apply(modifier=solid.name)
 arm=cuff.modifiers.new('Existing captured owner armature','ARMATURE');arm.object=rig
 for p in cuff.data.polygons:p.use_smooth=True
 return cuff,{'side':side,'original_garment_boundary_depth_m':-.055,'proximal_overlap_m':.001,'fabric_thickness_m':thickness,'required_rest_skin_clearance_m':clearance,'source_material':cloth.data.materials[0].name,'source_uv':'Actual original sleeve radial-ray barycentric photo-palette texel; new metric knit UV in metres, 1.6mm wales/0.16mm relief; no scanned-knit claim','radial_samples':N,'axial_rings':depths,'actual_surface_rays':proof,'source_and_body_files_modified':False,'original_cuff_recoverable':True,'motion_collision_verified':False}
