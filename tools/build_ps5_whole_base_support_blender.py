"""Our support only: four-mm retention above tray; original complete artist PS5 untouched."""
import bpy,json,hashlib
from pathlib import Path
from mathutils import Vector
SRC=Path('/workspace/sub01-home-private/reference-wall-console-r1/output/wall-console.blend');OUT=Path('/workspace/sub01-home-private/ps5-datsketch-original-r1/support-r1');OUT.mkdir(parents=True,exist_ok=True);bpy.ops.wm.open_mainfile(filepath=str(SRC));hardware=[o for o in bpy.context.scene.objects if o.type=='MESH'and len(o.data.materials)==1 and o.data.materials[0].name=='Wall mount powder coated steel'];assert len(hardware)>10;lips=[o for o in hardware if o.name.startswith('Console tray retention side lip')];assert len(lips)==2
before={o.name:([tuple(v.co)for v in o.data.vertices],o.matrix_world.copy())for o in hardware};changes=[]
for o in hardware:
 w=o.matrix_world.copy();w.translation+=Vector((.005,.16,0));o.matrix_world=w
 if o in lips:
  points=[o.matrix_world@v.co for v in o.data.vertices];oldlo=min(v.z for v in points);oldhi=max(v.z for v in points);assert abs(oldlo-1.25)<1e-6 and abs(oldhi-1.28)<1e-6
  # Hardware-only exact height revision: bottom125cm, top126.2cm; traytop125.8cm.
  w=o.matrix_world.copy();w.translation.z=1.256;w[2][2]*=.4;o.matrix_world=w
  points=[o.matrix_world@v.co for v in o.data.vertices];changes.append({'name':o.name,'oldBottomTopBlenderM':[oldlo,oldhi],'newBottomTopBlenderM':[min(v.z for v in points),max(v.z for v in points)],'retentionAboveTrayM':max(v.z for v in points)-1.258})
 else:assert [tuple(v.co)for v in o.data.vertices]==before[o.name][0],'Unrelated hardware vertices changed'
for o in list(bpy.context.scene.objects):
 if o not in hardware:bpy.data.objects.remove(o,do_unlink=True)
# New source keeps every anchor/dock/connection, and one actual retained steel PBR.
material=hardware[0].data.materials[0];shader=material.node_tree.nodes.get('Principled BSDF');pbr={'baseColor':list(shader.inputs['Base Color'].default_value),'roughness':shader.inputs['Roughness'].default_value,'metallic':shader.inputs['Metallic'].default_value};material.name='PSMSteel00'
bpy.ops.object.select_all(action='DESELECT')
for o in hardware:o.select_set(True)
bpy.context.view_layer.objects.active=hardware[0];bpy.ops.object.join();o=bpy.context.object;o.name='PS5WholeBaseMount';o.data.name=o.name;o.data.calc_loop_triangles();tris=len(o.data.loop_triangles);bpy.ops.export_scene.gltf(filepath=str(OUT/'ps5-whole-base-support.glb'),export_format='GLB',use_selection=True,export_cameras=False,export_lights=False);bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'ps5-whole-base-support.blend'));r={'schema':'sub01.owned-ps5-whole-base-support.v1','originalSourceBlend':str(SRC),'originalSourceBlendSha256':hashlib.sha256(SRC.read_bytes()).hexdigest(),'original6768HardwareOnly':True,'artistPS5OrControllerModified':False,'retainedHardwareObjects':len(hardware),'changedOnlyTwoManufacturedLips':changes,'allOtherLocalVerticesExact':True,'allHardwareDeltaUEcmFromOriginal6768':[.5,-16,0],'additionalDeltaFromCurrentCandidateUEcm':[0,4,0],'originalPBR':pbr,'triangles':tris,'nativeChanged':False,'files':{n:hashlib.sha256((OUT/n).read_bytes()).hexdigest()for n in['ps5-whole-base-support.glb','ps5-whole-base-support.blend']}};(OUT/'source-report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
