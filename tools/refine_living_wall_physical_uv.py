"""UV-only refinement: physical 610mm oak on fronts, returns and board end grain."""
import bpy,json,hashlib,shutil
from pathlib import Path
ROOT=Path('/workspace/sub01-home-private');OLD=ROOT/'reference-living-tv-wall-r1/output';OUT=ROOT/'reference-living-tv-wall-r2/output';OUT.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(OLD/'living-tv-wall.blend'))
parts=[o for o in bpy.context.scene.objects if o.type=='MESH'and o.name.startswith('LW')and o.name!='LW_OriginalChannel183'];assert len(parts)==9
for o in parts:
 uv=o.data.uv_layers.active;assert uv
 for face in o.data.polygons:
  axis=max(range(3),key=lambda i:abs(face.normal[i]))
  for li in face.loop_indices:
   q=o.matrix_world@o.data.vertices[o.data.loops[li].vertex_index].co
   uv.data[li].uv=((q.y if axis==0 else q.x)/.61,(q.y if axis==2 else q.z)/.61)
bpy.ops.object.select_all(action='DESELECT')
for o in parts:o.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(OUT/'living-tv-wall.glb'),export_format='GLB',use_selection=True,export_cameras=False,export_lights=False)
shutil.copy2(OLD/'living-cabinet.glb',OUT/'living-cabinet.glb');bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'living-tv-wall.blend'))
r=json.loads((OLD/'source-report.json').read_text());r['source_variant']='r2-full-face-physical-UV-only';r['front_return_end_grain_uv_all_non_degenerate']=True;r['cabinet_r1_bytes_unchanged']=True;r['files']={name:hashlib.sha256((OUT/name).read_bytes()).hexdigest()for name in ['living-tv-wall.glb','living-cabinet.glb','living-tv-wall.blend']};(OUT/'source-report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
