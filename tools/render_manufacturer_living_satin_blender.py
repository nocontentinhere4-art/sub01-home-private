"""One unchanged-camera combined review of the two actual manufacturer GLBs."""
import bpy,hashlib
from pathlib import Path
from mathutils import Vector
ROOT=Path('/workspace/sub01-home-private/manufacturer-around-large-r1');OUT=ROOT/'review-satin-r4';OUT.mkdir(exist_ok=True);bpy.ops.wm.read_factory_settings(use_empty=True)
for path,sha in [('/workspace/sub01-home-private/manufacturer-muuto-rest-r1/candidate-r3/muuto-rest-3-candidate.glb','286115af3c6dc71f679f34bca3d639d2689df7cd377053893189ae1651dc0b4e'),(str(ROOT/'placed-dark-satin-r4/muuto-around-large-dark-satin.glb'),'8796c519e5a4d6acaffe6a77dcf7393ab1f703de75a3de05b3e148a84eb772b4')]:
 p=Path(path);assert hashlib.sha256(p.read_bytes()).hexdigest()==sha;bpy.ops.import_scene.gltf(filepath=str(p))
scene=bpy.context.scene
bpy.ops.mesh.primitive_plane_add(size=10,location=(-1.7,0,.025));plane=bpy.context.object;m=bpy.data.materials.new('source floor');m.diffuse_color=(.12,.12,.12,1);plane.data.materials.append(m)
worldlight=bpy.data.worlds.new('Muuto source light');worldlight.use_nodes=True;worldlight.node_tree.nodes['Background'].inputs[1].default_value=.35;scene.world=worldlight
for loc,power in [((-3.2,-2.4,3),420),((.2,2.8,2.6),250)]:
 bpy.ops.object.light_add(type='AREA',location=loc);light=bpy.context.object;light.data.energy=power;light.data.size=2.6;light.rotation_euler=(Vector((-1.6,0,.4))-light.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(-4.5,-3.1,2));camera=bpy.context.object;camera.rotation_euler=(Vector((-1.7,0,.35))-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.type='ORTHO';camera.data.ortho_scale=3.5;scene.camera=camera
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.render.threads_mode='FIXED';scene.render.threads=2;scene.cycles.samples=16;scene.cycles.use_denoising=True;scene.render.resolution_x=960;scene.render.resolution_y=720;scene.render.resolution_percentage=100;scene.render.filepath=str(OUT/'muuto-rest-around-satin-review.png');bpy.ops.render.render(write_still=True)
