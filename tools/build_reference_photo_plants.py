"""Prepare four distinct CC0 plants with genuine PBR maps and ceramic planters.

Source-only server Blender work. Authored Poly Haven variants stay at real scale;
only catalogue translations are normalized and stem bases seated in real pots.
"""
import bpy,json,hashlib,math
from pathlib import Path
from mathutils import Vector
ROOT=Path('/workspace/sub01-home-private');SRC=ROOT/'reference-plants-ph-r1/source';OUT=ROOT/'reference-plants-ph-r1/output-r3';OUT.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True);records=[]
def bounds(objects):
 bpy.context.view_layer.update()
 pts=[o.matrix_world@v.co for o in objects for v in o.data.vertices];return [[min(p[i]for p in pts)for i in range(3)],[max(p[i]for p in pts)for i in range(3)]]
def tris(objects):return sum(sum(len(p.vertices)-2 for p in o.data.polygons)for o in objects)
all_review=[]
for number,(species,variant)in enumerate([('pachira_aquatica_01','b'),('calathea_orbifolia_01','a'),('pachira_aquatica_01','c'),('calathea_orbifolia_01','b')]):
 source=SRC/species/(species+'_1k.gltf');before=set(bpy.context.scene.objects);bpy.ops.import_scene.gltf(filepath=str(source));imported=[o for o in bpy.context.scene.objects if o not in before];plants=[o for o in imported if o.type=='MESH'and o.name.split('.')[0].endswith('_'+variant)]
 assert len(plants)==(2 if species.startswith('pachira')else 1),[o.name for o in imported]
 for o in imported:
  if o not in plants:bpy.data.objects.remove(o,do_unlink=True)
 # Remove only the catalogue's common X/Y offset, retaining worldscale1.
 lo,hi=bounds(plants);anchor=plants[0].location.copy();translation=Vector((-anchor.x,-anchor.y,.30-lo[2]));original_count=tris(plants)
 for o in plants:o.location+=translation
 # The real CC0 model supplies a500mm/430mm tapered ceramic pot and soil,
 # preserving their actual meshes. Foliage from this donor is never exported.
 before=set(bpy.context.scene.objects);pot_source=ROOT/'reference-plants-r1/source/potted-areca-palm-aee9b13e.glb';assert hashlib.sha256(pot_source.read_bytes()).hexdigest()=='518be187a8a3aeeb50b77b7da728486b10782e9cde6410ffb6fde66fe4a3044e';bpy.ops.import_scene.gltf(filepath=str(pot_source));donors=[o for o in bpy.context.scene.objects if o not in before];pots=[o for o in donors if o.type=='MESH'and any(m and ('plant pot'in m.name.lower()or'potting soil'in m.name.lower())for m in o.data.materials)]
 assert len(pots)==3,[o.name for o in donors]
 for o in donors:
  if o not in pots:bpy.data.objects.remove(o,do_unlink=True)
 # Measured ceramic sizes: small calatheas280mm diameter, bush330mm, tree420mm.
 pot_scale=[.66,.56,.84,.56][number]
 for o in pots:o.scale*=pot_scale;o.location*=pot_scale
 soil=[o for o in pots if any(m and 'potting soil'in m.name.lower()for m in o.data.materials)]
 assert len(soil)==1
 soil_top=bounds(soil)[1][2];extra=soil_top-.012-bounds(plants)[0][2]
 for o in plants:o.location.z+=extra
 translation.z+=extra
 meshes=plants+pots
 for i,o in enumerate(meshes):o.name='PP%d_%02d'%(number,i)
 # Each species keeps the complete original foliage geometry/UV/PBR; no leaf
 # decimation, procedural leaf substitution, recolouring or texture upscaling.
 assert tris(plants)==original_count
 bpy.ops.object.select_all(action='DESELECT')
 for o in meshes:o.select_set(True)
 bpy.context.view_layer.objects.active=meshes[0];out=OUT/('photo-plant-%d.glb'%number);bpy.ops.export_scene.gltf(filepath=str(out),export_format='GLB',use_selection=True,export_cameras=False,export_lights=False)
 record={'name':'photo-plant-%d'%number,'species':species,'authored_variant':variant,'source_license':'CC0-1.0 Poly Haven plus original CC0 Innerscene planter','plant_triangles':original_count,'pot_uniform_scale':pot_scale,'soil_top_m':soil_top,'root_burial_depth_m':.012,'pot_triangles':tris(pots),'total_triangles':tris(meshes),'source_geometry_decimation':False,'worldscale_preserved':True,'source_translation_only_m':list(translation),'bounds_m':bounds(meshes),'pot_bounds_m':bounds(pots),'plant_root_min_z_m':bounds(plants)[0][2],'prepared_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'prepared_bytes':out.stat().st_size,'native_placement_accepted':False};records.append(record)
 for o in meshes:o.location.x+=(number-1.5)*1.9
 all_review.extend(meshes)
mat=bpy.data.materials.new('Review warm neutral ground');mat.use_nodes=True;mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(.52,.49,.43,1);mat.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=.85
bpy.ops.mesh.primitive_plane_add(size=200);bpy.context.object.data.materials.append(mat)
world=bpy.data.worlds.new('Photo plant source daylight');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.72,.76,.8,1);world.node_tree.nodes['Background'].inputs[1].default_value=.28;bpy.context.scene.world=world
for loc,power,size in[((-3,-4,5),900,5),((4,1,5),550,4)]:
 bpy.ops.object.light_add(type='AREA',location=loc);l=bpy.context.object;l.data.energy=power;l.data.size=size;l.rotation_euler=(Vector((0,0,1))-l.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(4,-11,5));cam=bpy.context.object;cam.rotation_euler=(Vector((0,0,.8))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='ORTHO';cam.data.ortho_scale=8.6;bpy.context.scene.camera=cam
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=24;scene.cycles.use_denoising=True;scene.render.threads_mode='FIXED';scene.render.threads=3;scene.render.resolution_x=1600;scene.render.resolution_y=900;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG';scene.view_settings.view_transform='AgX'
report={'schema':'sub01.reference-photo-plants-source.v1','plants':records,'total_triangles':sum(x['total_triangles']for x in records),'native_changes':False,'native_ready':False,'source_visual_review_pending':True};(OUT/'photo-plants-source.json').write_text(json.dumps(report,indent=2)+'\n');bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'photo-plants-review.blend'));scene.render.filepath=str(OUT/'photo-plants-source-review.png');bpy.ops.render.render(write_still=True);print('PHOTO_PLANTS_SOURCE_COMPLETE',json.dumps(report),flush=True)
