"""Read-only actual serialized table shader, world-top UV and corner normal evidence."""
import bpy,json,sys,math
from pathlib import Path
from mathutils import Vector
bpy.ops.wm.read_factory_settings(use_empty=True);p=Path('/workspace/sub01-home-private/manufacturer-around-large-r1/placed-dark-r3/muuto-around-large-dark.glb');bpy.ops.import_scene.gltf(filepath=str(p));rows=[]
for o in bpy.context.scene.objects:
 if o.type!='MESH':continue
 o.data.calc_loop_triangles();norm=o.matrix_world.to_3x3().inverted().transposed();uv=o.data.uv_layers.active;ma=o.data.materials[0];bs=ma.node_tree.nodes.get('Principled BSDF');image=next(n.image for n in ma.node_tree.nodes if n.type=='TEX_IMAGE');pix=list(image.pixels);width,height=image.size;tops=[]
 for tri in o.data.loop_triangles:
  pts=[o.matrix_world@o.data.vertices[i].co for i in tri.vertices];geometric=(pts[1]-pts[0]).cross(pts[2]-pts[0]);area=geometric.length/2
  if not area or geometric.normalized().z<.98 or min(v.z for v in pts)<.36:continue
  UV=[uv.data[i].uv for i in tri.loops];col=[]
  for q in UV:
   x=int((q.x%1)*width)%width;y=int((q.y%1)*height)%height;i=4*(y*width+x);col.append(pix[i:i+3])
  normals=[(norm@o.data.corner_normals[i].vector).normalized()for i in tri.loops];tops.append({'triangle':tri.index,'areaM2':area,'zM':[min(v.z for v in pts),max(v.z for v in pts)],'cornerNormalDotUp':[n.z for n in normals],'textureSampleRGB':col,'uv':[list(x)for x in UV]})
 rows.append({'object':o.name,'material':ma.name,'image':image.name,'imageSize':[width,height],'colorSpace':image.colorspace_settings.name,'shaderLinks':[(l.from_node.name,l.from_socket.name,l.to_node.name,l.to_socket.name)for l in ma.node_tree.links],'shaderUnlinkedInputs':{s.name:list(s.default_value)if hasattr(s.default_value,'__len__')else s.default_value for s in bs.inputs if not s.is_linked},'actualWorldTopTriangles':tops})
r={'schema':'sub01.manufacturer-around-top-shader-diagnostic.v1','source':str(p),'rows':rows,'nativeChanged':False};Path('/workspace/sub01-home-private/manufacturer-around-large-r1/placed-dark-r3/top-shader-diagnostic.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps([{**x,'actualWorldTopTriangles':x['actualWorldTopTriangles'][:2]}for x in rows]),flush=True)
