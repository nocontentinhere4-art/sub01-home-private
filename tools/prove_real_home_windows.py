"""Server-only exact source BVH candidates and same-camera construction preview.
Reports all source intersections; never converts a candidate pair into acceptance.
"""
import argparse,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))

def supported_boundary_contact(name,node,triangle,bounds):
 # The BVH has already proved contact. Permit only opposite closed halfspaces
 # at these measured masonry boundaries; vertical-face top edges are valid too.
 planes=[(2,.70),(2,2.575)]
 if 'FacadePier_3'in name:planes.append((0,3.91))
 role=any(s in name for s in('SupportPacker','InteriorWalnutSill','FacadePier'))
 return node==158 and role and any(
  (max(v[axis]for v in triangle)<=value+1e-6 and bounds[0][axis]>=value-1e-6)
  or(min(v[axis]for v in triangle)>=value-1e-6 and bounds[1][axis]<=value+1e-6)
  for axis,value in planes)

def run(root,source,skip_preview=False):
 import bpy
 from mathutils import Vector
 from mathutils.bvhtree import BVHTree
 from home_asset_audit import read_gltf
 from structural_rail_source_patch import accessor,world_matrices,transformed
 from real_home_window_plan import SOURCE_SHA
 root,source=Path(root),Path(source);report=json.loads((root/'source-report.json').read_text());assert hashlib.sha256(source.read_bytes()).hexdigest()==SOURCE_SHA
 bpy.ops.wm.open_mainfile(filepath=str(root/'real-home-windows.blend'))
 window=[o for o in bpy.data.objects if o.type=='MESH'];doc,blob=read_gltf(source);matrices=world_matrices(doc);old=set(report['old_nodes_to_retire']);protected=[];before=[]
 def bounds(pts):return [[min(v[i]for v in pts)for i in range(3)],[max(v[i]for v in pts)for i in range(3)]]
 def overlap(a,b):return all(a[0][i]<=b[1][i]and b[0][i]<=a[1][i]for i in range(3))
 newrows=[]
 export_doc,export_blob=read_gltf(root/'real-home-windows.glb');export_matrices=world_matrices(export_doc)
 for ni,node in enumerate(export_doc['nodes']):
  if 'mesh'not in node:continue
  pts=[];faces=[]
  for pr in export_doc['meshes'][node['mesh']]['primitives']:
   pv=[transformed(export_matrices[ni],v)for v in accessor(export_doc,export_blob,pr['attributes']['POSITION'])];pv=[Vector((v[0],-v[2],v[1]))for v in pv];ix=[v[0]for v in accessor(export_doc,export_blob,pr['indices'])];off=len(pts);pts+=pv;faces.extend(tuple(off+j for j in ix[i:i+3])for i in range(0,len(ix),3))
  newrows.append((node['name'],bounds(pts),BVHTree.FromPolygons(pts,faces,all_triangles=True,epsilon=0)))
 for ni,node in enumerate(doc['nodes']):
  if'mesh'not in node:continue
  vertices=[];faces=[]
  for prim in doc['meshes'][node['mesh']]['primitives']:
   pts=[transformed(matrices[ni],v)for v in accessor(doc,blob,prim['attributes']['POSITION'])];pts=[Vector((v[0],-v[2],v[1]))for v in pts]
   pb=bounds(pts)
   if not any(overlap(pb,b)for name,b,tree in newrows)and ni!=158 and ni not in old:continue
   idx=[v[0]for v in accessor(doc,blob,prim['indices'])];off=len(vertices);vertices+=pts;faces.extend(tuple(off+j for j in idx[i:i+3])for i in range(0,len(idx),3))
  if not faces:continue
  row=(ni,bounds(vertices),BVHTree.FromPolygons(vertices,faces,all_triangles=True,epsilon=0))
  if ni not in old:protected.append((*row,vertices,faces))
  if ni==158 or ni in old:
   data=bpy.data.meshes.new('OriginalSource_'+str(ni));data.from_pydata(vertices,[],faces);data.update();o=bpy.data.objects.new(data.name,data);bpy.context.collection.objects.link(o);o.hide_render=ni in old;before.append(o)
 collisions=[]
 for name,b,tree in newrows:
  for ni,pb,pt,vertices,faces in protected:
   if overlap(b,pb):
    pairs=tree.overlap(pt)
    if pairs:
     allowed=[];bad=[]
     for ii,jj in pairs:
      tri=[vertices[k]for k in faces[jj]]
      contact=supported_boundary_contact(name,ni,tri,b)
      (allowed if contact else bad).append((ii,jj))
     collisions.append({'part':name,'protected_source_node':ni,'pairs':len(pairs),'exact_measured_boundary_contact_pairs':len(allowed),'unresolved_pairs':len(bad),'first_unresolved_pairs':[list(v)for v in bad[:8]],'first_pairs':[list(v)for v in pairs[:8]]})
 (root/'protected-source-bvh-candidates.json').write_text(json.dumps({'schema':'sub01.window-protected-source-bvh-candidates.v1','source_sha256':SOURCE_SHA,'actual_export_glb_sha256':hashlib.sha256((root/'real-home-windows.glb').read_bytes()).hexdigest(),'tested_export_meshes':len(newrows),'pairs':collisions,'ok':not any(r['unresolved_pairs']for r in collisions),'unresolved_pair_count':sum(r['unresolved_pairs']for r in collisions),'contact_epsilon_m':1e-6,'contact_planes':'Only source158 actual topbase Z.70/header2.575 and rightjambX3.91; only named supported sill/packer/pier parts, one-sided, never frame/glass/furniture','note':'Exact BVH surface candidates include boundary/coplanar contact; every noncontact must be resolved before native installation','native_changed':False},indent=2)+'\n')
 print('WINDOW_PROTECTED_BVH',json.dumps(collisions),flush=True)
 if skip_preview:return
 # Small CPU construction views only, same lighting/camera before/after.
 scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=8;scene.render.resolution_x=1000;scene.render.resolution_y=700;scene.render.resolution_percentage=100
 scene.world=bpy.data.worlds.new('SourcePreviewWorld');scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.75,.8,.9,1);scene.world.node_tree.nodes['Background'].inputs[1].default_value=.8
 wall=bpy.data.materials.new('Preview original mineral wall');wall.diffuse_color=(.76,.74,.70,1)
 for o in before:o.data.materials.append(wall)
 camdata=bpy.data.cameras.new('SourceConstructionCamera');cam=bpy.data.objects.new('SourceConstructionCamera',camdata);scene.collection.objects.link(cam);scene.camera=cam;camdata.lens=22
 for label,eye,target in [('front',(.5,-1.8,1.65),(-1.6,-4,1.6)),('west',(-1.65,1.,1.65),(-4,1.8,1.6))]:
  cam.location=eye;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler()
  for state in('before','after'):
   for o in window:o.hide_render=state=='before'
   for o in before:o.hide_render=False if o.name=='OriginalSource_158'else state=='after'
   scene.render.filepath=str(root/(label+'-'+state+'.png'));bpy.ops.render.render(write_still=True)
 print('WINDOW_CONSTRUCTION_PREVIEWS_COMPLETE',flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--source',required=True);p.add_argument('--skip-preview',action='store_true');a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);run(a.root,a.source,a.skip_preview)
