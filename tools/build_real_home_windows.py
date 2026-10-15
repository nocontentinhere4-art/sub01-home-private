"""Original residential composite window assemblies fitted to measured exact955 apertures.
Server Blender only. No Unreal/world writes. Manufacturer references are construction
references, not licensed CAD. Closed-pose operating hardware is not functional readiness.
"""
import argparse,hashlib,json,math,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from real_home_window_plan import plan,SOURCE_SHA


def build(source,desk,output):
 import bpy,bmesh
 import numpy as np
 from mathutils import Vector
 from home_asset_audit import read_gltf
 from structural_rail_source_patch import accessor,world_matrices,transformed
 source,desk,output=map(Path,(source,desk,output))
 assert hashlib.sha256(source.read_bytes()).hexdigest()==SOURCE_SHA
 assert hashlib.sha256(desk.read_bytes()).hexdigest()=='99bdf3fd42eea5fc4cb2fadd52c8cae18c4459a94000b85f7df4c515234ba43d'
 output.mkdir(parents=True,exist_ok=False);p=plan();bpy.ops.wm.read_factory_settings(use_empty=True)
 bpy.ops.import_scene.gltf(filepath=str(desk));wood=bpy.data.materials.get('Satin walnut | longitudinal grain')
 if wood is None:raise ValueError('Genuine wood PBR unavailable')
 for o in list(bpy.data.objects):bpy.data.objects.remove(o,do_unlink=True)
 def material(name,color,rough,metal=0,transmission=0):
  m=bpy.data.materials.new(name);m.use_nodes=True;s=m.node_tree.nodes.get('Principled BSDF');s.inputs['Base Color'].default_value=(*color,1);s.inputs['Roughness'].default_value=rough;s.inputs['Metallic'].default_value=metal;s.inputs['Transmission Weight'].default_value=transmission;s.inputs['IOR'].default_value=1.52;return m
 paint=material('Window warm white factory coating',(.72,.70,.65),.4)
 clad=material('Window exterior bronze aluminium',(.10,.085,.067),.35,.7)
 epdm=material('Window EPDM weather seal',(.009,.010,.009),.85)
 metal=material('Window stainless hardware',(.43,.45,.46),.26,.95)
 glass=material('Window clear insulated glass',(.97,.99,1),.025,0,1)
 wall=material('Window pier matte mineral plaster',(.76,.745,.70),.89)
 # Recover provider's actual planar UV density; never invent wood texture tiling.
 dd,db=read_gltf(desk);wm=world_matrices(dd);samples=[]
 for prim in dd['meshes'][dd['nodes'][44]['mesh']]['primitives']:
  if prim['material']!=4:continue
  ps=[transformed(wm[44],v)for v in accessor(dd,db,prim['attributes']['POSITION'])];uv=accessor(dd,db,prim['attributes']['TEXCOORD_0']);idx=[v[0]for v in accessor(dd,db,prim['indices'])];top=max(v[1]for v in ps);ids=set()
  for i in range(0,len(idx),3):
   js=idx[i:i+3]
   if all(abs(ps[j][1]-top)<1e-7 for j in js) and (Vector(ps[js[1]])-Vector(ps[js[0]])).cross(Vector(ps[js[2]])-Vector(ps[js[0]])).length_squared>0:ids.update(js)
  samples.extend((ps[j],uv[j])for j in ids)
 a=np.asarray([[v[0],v[2],1.]for v,t in samples]);b=np.asarray([t for v,t in samples]);coeff=np.linalg.lstsq(a,b,rcond=None)[0];uv_error=float(np.max(np.abs(a@coeff-b)))
 if uv_error>1e-5:raise ValueError('Source wood UV density not affine')
 objects=[];records=[]
 def point(f,u,v,n):return (-4+n,-u,v)if f=='west'else(u,-4+n,v)
 def mesh(name,facade,verts,faces,mat,bevel=0):
  data=bpy.data.meshes.new(name);data.from_pydata([point(facade,*v)for v in verts],[],faces);data.update();bm=bmesh.new();bm.from_mesh(data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(data);bm.free()
  obj=bpy.data.objects.new('SUB01_RealWindow_'+name,data);bpy.context.collection.objects.link(obj);obj.data.materials.append(mat)
  if bevel:
   mod=obj.modifiers.new('Manufactured edge radius','BEVEL');mod.width=bevel;mod.segments=3;bpy.context.view_layer.objects.active=obj;bpy.ops.object.modifier_apply(modifier=mod.name)
  uv=obj.data.uv_layers.new(name='PhysicalScaleUV')
  for poly in obj.data.polygons:
   for li in poly.loop_indices:
    c=obj.data.vertices[obj.data.loops[li].vertex_index].co
    if mat==wood:uv.data[li].uv=tuple(np.asarray([c.y,c.x,1.])@coeff)
    else:uv.data[li].uv=(c.x+c.y,c.z)
  objects.append(obj);return obj
 def box(name,f,u0,u1,v0,v1,n0,n1,mat,bevel=0):
  vs=[(u,v,n)for n in(n0,n1)for v in(v0,v1)for u in(u0,u1)]
  return mesh(name,f,vs,[(0,2,3,1),(4,5,7,6),(0,1,5,4),(2,6,7,3),(0,4,6,2),(1,3,7,5)],mat,bevel)
 def ring(name,f,rect,layers,mat):
  # Each depth layer has distinct rebate width: real closed annular profile.
  u0,u1,v0,v1=rect;verts=[]
  for n,w in layers:
   verts.extend([(u0,v0,n),(u1,v0,n),(u1,v1,n),(u0,v1,n),(u0+w,v0+w,n),(u1-w,v0+w,n),(u1-w,v1-w,n),(u0+w,v1-w,n)])
  faces=[]
  for k in range(len(layers)-1):
   a=k*8;b=(k+1)*8
   for j in range(4):q=(j+1)%4;faces.extend([(a+j,a+q,b+q,b+j),(a+4+q,a+4+j,b+4+j,b+4+q)])
  for k in(0,len(layers)-1):
   a=k*8
   for j in range(4):q=(j+1)%4;faces.append((a+j,a+4+j,a+4+q,a+q))
  return mesh(name,f,verts,faces,mat)
 for unit in p['units']:
  name=unit['id'];f=unit['facade'];u0,u1=unit['unit_u'];v0,v1=unit['unit_v'];rect=(u0,u1,v0,v1)
  ring(name+'_TimberMainframe',f,rect,[(-.0395,.035),(-.028,.035),(-.028,.027),(.055,.027),(.055,.035),(.0745,.035)],paint)
  ring(name+'_ExteriorCladding',f,rect,[(-.0745,.035),(-.071,.035),(-.071,.023),(-.041,.023),(-.041,.035),(-.0395,.035)],clad)
  ring(name+'_FrameWeatherSeal',f,(u0+.027,u1-.027,v0+.027,v1-.027),[(-.038,.008),(-.034,.008)],epdm)
  # Frame-to-masonry compressible perimeter seal occupies the measured fitting gap.
  ring(name+'_PerimeterSeal',f,(u0-.019,u1+.019,v0-.019,v1+.019),[(-.055,.019),(-.050,.019)],epdm)
  clear0=u0+.035;clear1=u1-.035;lightw=(clear1-clear0)/unit['lights'];lightrows=[]
  for j in range(unit['lights']):
   # Mullions meet frame edges; no crossing fullwidth hidden bar.
   if j:
    c=clear0+j*lightw;box(name+'_Mullion_'+str(j),f,c-.0175,c+.0175,v0+.035,v1-.035,-.0395,.0745,paint,.001)
   l=clear0+j*lightw+(.0175 if j else 0)+.004;r=clear0+(j+1)*lightw-(.0175 if j+1<unit['lights']else 0)-.004;b0=v0+.039;t=v1-.039
   ring(name+'_Sash_'+str(j),f,(l,r,b0,t),[(-.032,.035),(-.022,.035),(-.022,.025),(.018,.025),(.018,.035),(.030,.035)],paint)
   # IGU is36mm:3x4mm glass /2x12mm sealed airspace, never a solidwindow box.
   for k,depth in enumerate((-.022,-.006,.010)):
    box(name+'_Glass_'+str(j)+'_'+str(k),f,l+.030,r-.030,b0+.030,t-.030,depth,depth+.004,glass)
   for k,(a0,a1)in enumerate(((-.018,-.006),(-.002,.010))):
    ring(name+'_IGUSpacer_'+str(j)+'_'+str(k),f,(l+.030,r-.030,b0+.030,t-.030),[(a0,.007),(a1,.007)],clad)
   for k,depth in enumerate((-.024,.014)):
    ring(name+'_GlazingGasket_'+str(j)+'_'+str(k),f,(l+.025,r-.025,b0+.025,t-.025),[(depth,.005),(depth+.002,.005)],epdm)
   if j==unit['operable_light']:
    for h in(.18,.78):box(name+'_Hinge_'+str(j)+'_'+str(h),f,l-.003,l+.010,b0+(t-b0)*h,b0+(t-b0)*h+.065,.031,.044,metal,.002)
    box(name+'_HandleEscutcheon_'+str(j),f,r-.027,r-.012,(b0+t)/2-.035,(b0+t)/2+.035,.031,.039,metal,.003)
    box(name+'_HandleLever_'+str(j),f,r-.024,r-.014,(b0+t)/2-.008,(b0+t)/2+.090,.039,.058,metal,.004)
   lightrows.append({'index':j,'opening_u_m':[l,r],'opening_v_m':[b0,t],'closed_operable_candidate':j==unit['operable_light']})
  # Folded clipped sill with genuine drip. Interior flush sill avoids kitchen and TVbacker.
  box(name+'_ExteriorSill',f,u0-.015,u1+.015,.7001,.7021,-.120,-.0745,clad)
  box(name+'_ExteriorDrip',f,u0-.015,u1+.015,.684,.7001,-.120,-.118,clad)
  # Explicit TV backer and kitchen clearance: no projecting board behind existingfurniture.
  spans=[(u0,u1)] if name not in('WestMiddleTV','WestSouth') else ([(u0,-1.126),(1.026,u1)]if name=='WestMiddleTV'else[])
  for j,(a0,a1)in enumerate(spans):
   if a1>a0:box(name+'_InteriorWalnutSill_'+str(j),f,a0,a1,.70,.72,.0745,.15,wood,.001)
  for j,u in enumerate((u0+.10,u1-.10)):box(name+'_SupportPacker_'+str(j),f,u-.025,u+.025,.700,.720,-.035,.035,epdm)
  records.append({'unit':name,'lights':lightrows,'rough_u_m':unit['rough_u'],'rough_v_m':unit['rough_v'],'frame_u_m':[u0,u1],'frame_v_m':[v0,v1],'normal_bounds_m':[-.0745,.0745],'sill_projection_omitted_for_kitchen':name=='WestSouth','tv_backer_projection_excluded':name=='WestMiddleTV'})
 for j,(u0,u1)in enumerate(p['new_front_wall_infill_piers_u_m']):box('FacadePier_'+str(j),'front',u0,u1,.70,2.575,-.09,.09,wall,.0005)
 # Save actual sourcegeometry/UV/manifold topology, not a construction-time assertion.
 for o in objects:
  bm=bmesh.new();bm.from_mesh(o.data);bad=sum(not e.is_manifold for e in bm.edges);bm.free()
  if bad:raise ValueError('Nonclosed manufactured part '+o.name+':'+str(bad))
 rows=[]
 for o in objects:
  o.data.calc_loop_triangles();pts=[o.matrix_world@v.co for v in o.data.vertices];rows.append({'name':o.name,'triangles':len(o.data.loop_triangles),'materials':[m.name for m in o.data.materials],'bounds_ue_cm':[[min(v[i]for v in pts)*100 for i in range(3)],[max(v[i]for v in pts)*100 for i in range(3)]],'closed_manifold':True})
 # Above BlenderY is negative UEY: persist explicitly correct world bounds.
 for row in rows:lo,hi=row['bounds_ue_cm'];lo[1],hi[1]=-hi[1],-lo[1]
 for o in bpy.context.selected_objects:o.select_set(False)
 for o in objects:o.select_set(True)
 bpy.ops.wm.save_as_mainfile(filepath=str(output/'real-home-windows.blend'))
 bpy.ops.export_scene.gltf(filepath=str(output/'real-home-windows.glb'),export_format='GLB',use_selection=True,export_yup=True,export_texcoords=True,export_normals=True,export_materials='EXPORT')
 report={'schema':'sub01.original-real-home-windows-source.v1','source_sha256':SOURCE_SHA,'plan':p,'units':records,'parts':rows,'part_count':len(rows),'triangles':sum(r['triangles']for r in rows),'wood_uv_affine_max_error':uv_error,'glb_sha256':hashlib.sha256((output/'real-home-windows.glb').read_bytes()).hexdigest(),'original_source_changed':False,'old_nodes_to_retire':p['exact_old_lower_frame_nodes'],'protected_wall_node':158,'all_parts_closed_manifold':True,'source_fit_policy':'149mm profile centered inside180mm actual wall;20mm perimeter installation gap; exact surveyed pier/opening intervals; kitchen no interior sill; TV backer exclusions','full_protected_triangle_bvh_proof':False,'source_ready':False,'native_ready':False,'windows_activity_ready':False,'caveats':['Source topology and measured aperture fit only; final native geometry/PBR and real glass parents require actual importer validation','No operational hinge/runtime claim','New front piers are original missing architectural infill, not furnitureboxes','Exterior panorama unchanged; finite photograph cannot provide balcony translation parallax']}
 (output/'source-report.json').write_text(json.dumps(report,indent=2)+'\n');print('WINDOW_SOURCE_EXPORTED',json.dumps({'parts':len(rows),'triangles':report['triangles'],'sha256':report['glb_sha256']}),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--desk',required=True);p.add_argument('--output',required=True);a=p.parse_args(sys.argv[sys.argv.index('--')+1:]if'--'in sys.argv else None);build(a.source,a.desk,a.output)
