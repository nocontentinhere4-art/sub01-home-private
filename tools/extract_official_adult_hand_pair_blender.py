"""CC0 source geometry extraction only; no pose edits, invented skin or mirroring."""
import bpy,hashlib,json
from pathlib import Path
from mathutils import Vector
root=Path('/workspace/sub01-home-private/human-base-hands-r1');path=root/'source/human-base-meshes-bundle-v1.4.1/human_base_meshes_bundle.blend';assert hashlib.sha256(path.read_bytes()).hexdigest()=='3c121505651140ceb4d69fd1d8923f7788ffadd81672f5be14845a5f2c75c137';out=root/'adult-hand-pair-source-r1';out.mkdir(exist_ok=False)
bpy.ops.wm.read_factory_settings(use_empty=True)
with bpy.data.libraries.load(str(path),link=False)as(src,dst):dst.objects=['GEO-body_male_realistic']
body=dst.objects[0];bpy.context.scene.collection.objects.link(body);body.hide_render=False;body.hide_viewport=False;body.hide_set(False)
for m in body.modifiers:
 assert m.type=='MULTIRES'and m.total_levels==3;m.levels=3;m.render_levels=3
bpy.context.view_layer.update();evaluated=body.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=evaluated.to_mesh();mesh.calc_loop_triangles();world=[body.matrix_world@v.co for v in mesh.vertices]
# Exact authored original triangles: only complete triangles outside the body,
# below the elbow. No clipping interpolation, filling, smoothing or cap shape.
center=(min(v.x for v in world)+max(v.x for v in world))*.5;floor=min(v.z for v in world);objects=[];rows=[]
for side,sign in [('Left',1),('Right',-1)]:
 eligible={i for i,v in enumerate(world)if sign*(v.x-center)>.28 and floor+.5<v.z<floor+1.2};triangles=[list(t.vertices)for t in mesh.loop_triangles if all(i in eligible for i in t.vertices)];used=sorted({i for t in triangles for i in t});assert len(used)>1000;indices={i:j for j,i in enumerate(used)};coords=[world[i]for i in used];data=bpy.data.meshes.new('CC0Adult'+side+'OriginalSurface');data.from_pydata(coords,[],[[indices[i]for i in t]for t in triangles]);data.update();o=bpy.data.objects.new('CC0Adult_'+side+'_ForearmHand_SOURCE_UNRIGGED',data);bpy.context.scene.collection.objects.link(o)
 for p in data.polygons:p.use_smooth=True
 lo=[min(v[k]for v in coords)for k in range(3)];hi=[max(v[k]for v in coords)for k in range(3)]
 row={'side':side,'source_side_native_x_sign':sign,'vertices':len(used),'triangles':len(triangles),'bounds_source_world_m':[lo,hi],'source_vertices':used,'source_triangles':triangles,'all_exported_surface_corners_exact_source_world':all((data.vertices[indices[i]].co-world[i]).length<1e-7 for t in triangles for i in t),'cut_boundary':'Uncapped exact complete-triangle source selection at Xoffset28cm and floorZ50..120cm; open end must be fitted beneath cuff, not accepted runtime attachment','mirrored':False,'new_armature_or_weights':False};rows.append(row);objects.append(o)
evaluated.to_mesh_clear();body.hide_render=True;body.hide_set(True);bpy.ops.object.select_all(action='DESELECT')
for o in objects:o.select_set(True)
bpy.context.view_layer.objects.active=objects[0];bpy.ops.export_scene.gltf(filepath=str(out/'official-adult-hand-pair-unrigged.glb'),export_format='GLB',use_selection=True,export_apply=False,export_materials='NONE')
report={'source_blend_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'source_object':'GEO-body_male_realistic','license':'CC0','official_url':'https://www.blender.org/download/demo-files/','source_original_multires_level':3,'mesh_sha256':hashlib.sha256((out/'official-adult-hand-pair-unrigged.glb').read_bytes()).hexdigest(),'rows':rows,'pose_edits':False,'procedural_hand_geometry':False,'rigging_ready':False,'native_imported':False,'visual_accepted':False};(out/'exact-source-extraction-proof.json').write_text(json.dumps(report,indent=2)+'\n');print('CC0_ADULT_HAND_PAIR_EXTRACTED',json.dumps({**report,'rows':[{k:v for k,v in r.items()if k not in['source_vertices','source_triangles']}for r in rows]}),flush=True)
