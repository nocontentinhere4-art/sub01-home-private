"""Server-only Blender import of licensed real-scale compact espresso model.
Blender --background --python tools/import_home_cc0_espresso.py -- --asset PATH --output PATH
Does not render or change the running home. Server scene assembly may append this .blend.
"""
import argparse,json,sys
from pathlib import Path
import bpy
from mathutils import Vector
p=argparse.ArgumentParser();p.add_argument('--asset',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--in-place',action='store_true');o=p.parse_args(sys.argv[sys.argv.index('--')+1:]);bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(o.asset));meshes=[x for x in bpy.context.scene.objects if x.type=='MESH'];assert len(meshes)==6
points=[x.matrix_world@v.co for x in meshes for v in x.data.vertices];low=Vector([min(v[i]for v in points)for i in range(3)]);high=Vector([max(v[i]for v in points)for i in range(3)]);assert abs(high.x-low.x-.299)<.001;assert abs(high.z-low.z-.349)<.001
# Imported glTF Y-up maps to Blender Z-up; runtime(-1.25,.925,-3.5) maps to Blender(-1.25,3.5,.925).
if o.in_place:
 anchor=bpy.data.objects.new('SUB01_CC0_PortaEspresso',None);bpy.context.scene.collection.objects.link(anchor);anchor.location=(-1.25,3.5,.925)
 for mesh in meshes:mesh.parent=anchor
for mesh in meshes:mesh['sourceAuthor']='Innerscene';mesh['sourceLicense']='CC0-1.0';mesh['sourceURL']='https://www.innerscene.com/tools/library/3d-parts/porta-espresso-small-appliance-1ca7fb5d'
bpy.ops.file.pack_all();o.output.parent.mkdir(parents=True,exist_ok=True);bpy.ops.wm.save_as_mainfile(filepath=str(o.output));print('ESPRESSO_IMPORTED',json.dumps({'groups':len(meshes),'boundsBlender':[list(low),list(high)],'output':str(o.output),'placed':o.in_place}),flush=True)
