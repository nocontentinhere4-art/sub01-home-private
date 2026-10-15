"""Separate small display-only derivative; never updates the frozen held WIP."""
import bpy,json,hashlib,sys
from pathlib import Path
ROOT=Path('/workspace/sub01-home-private/reference-controller-r11/output')
source=ROOT/'controller-r11-display.glb';assert hashlib.sha256(source.read_bytes()).hexdigest()=='70a509ae1bc7be500904f9514758088368f663f1f8bb7f6fb1b4518d7c6d9bd5'
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(source));parts=[o for o in bpy.context.scene.objects if o.type=='MESH'];assert len(parts)==1;o=parts[0];bpy.context.view_layer.objects.active=o
mod=o.modifiers.new('Separate display-only triangle budget','DECIMATE');mod.ratio=.155;mod.delimit={'MATERIAL'};mod.use_collapse_triangulate=True;bpy.ops.object.modifier_apply(modifier=mod.name)
lo=min(v.co.x for v in o.data.vertices);hi=max(v.co.x for v in o.data.vertices);scale=.16/(hi-lo)
for v in o.data.vertices:v.co.x*=scale
for p in o.data.polygons:p.use_smooth=True
o.name='C11DLOD';o.data.name='C11DLOD';bpy.ops.object.select_all(action='DESELECT');o.select_set(True)
path=ROOT/'controller-r11-display-lod.glb';bpy.ops.export_scene.gltf(filepath=str(path),export_format='GLB',use_selection=True,export_cameras=False,export_lights=False)
sys.path.insert(0,'/home/unreal/runtime-tools');from home_asset_audit import read_gltf
from structural_rail_source_patch import accessor,world_matrices,transformed
d,b=read_gltf(path);matrices=world_matrices(d);positions=[];triangles=0
for ni,n in enumerate(d['nodes']):
 if'mesh'not in n:continue
 for p in d['meshes'][n['mesh']]['primitives']:
  positions.extend(transformed(matrices[ni],v)for v in accessor(d,b,p['attributes']['POSITION']));triangles+=len(accessor(d,b,p['indices']))//3
width=max(p[0]for p in positions)-min(p[0]for p in positions);assert abs(width-.16)<1e-7;assert 0<triangles<45000;assert len(d['materials'])==6
r={'schema':'sub01.reference-controller-r11-display-lod.v1','base_display_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'triangles':triangles,'width_m':width,'material_count':6,'held_geometry_unchanged':True,'display_only':True,'native_imported':False,'hand_contact_accepted':False,'activity_ready':False};(ROOT/'display-lod-proof.json').write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True)
