"""Separate source derivative: exact official loop UV and nail-region materials.
Never edits the frozen rig, pose, weights or production home. No scan texture claim.
"""
import bpy,json,hashlib,collections,gzip
from pathlib import Path
R=Path('/workspace/sub01-home-private/human-base-hands-r1');source=R/'rig-r9/official-adult-hand-pair-rig.blend';out=R/'rig-r9/uv-skin-source-r1';out.mkdir(exist_ok=False);bpy.ops.wm.open_mainfile(filepath=str(source));body=bpy.data.objects['GEO-body_male_realistic'];body.hide_set(False)
for modifier in body.modifiers:assert modifier.type=='MULTIRES';modifier.levels=3;modifier.render_levels=3
bpy.context.view_layer.update();ev=body.evaluated_get(bpy.context.evaluated_depsgraph_get());full=ev.to_mesh();full.calc_loop_triangles();uv=full.uv_layers.get('UVMap');assert uv,'Original official UVMap missing';regions=full.attributes['.sculpt_face_set'];world=[body.matrix_world@v.co for v in full.vertices]
def key(p):return tuple(round(v*1e7)for v in p)
lookup=collections.defaultdict(list)
for i,p in enumerate(world):lookup[key(p)].append(i)
hands={side:bpy.data.objects['CC0Adult_'+side+'_ForearmHand_SOURCE_UNRIGGED']for side in['Left','Right']};maps={};needed=set()
for side,o in hands.items():
 ids=[]
 for v in o.data.vertices:
  found=lookup[key(o.matrix_world@v.co)];assert len(found)==1,'Original source vertex match ambiguous';ids.append(found[0]);needed.add(found[0])
 maps[side]=ids
triangle_source={}
for tri in full.loop_triangles:
 if all(i in needed for i in tri.vertices):
  k=tuple(sorted(tri.vertices));assert k not in triangle_source,'Original source triangle identity duplicated';triangle_source[k]=({'vertices':list(tri.vertices),'uv':[list(uv.data[l].uv)for l in tri.loops],'region':regions.data[tri.polygon_index].value})
materials=[]
for name,color,roughness,coat in [('OfficialAnatomicalSkin_SourceReview',(.43,.255,.18,1),.48,0),('OfficialAnatomicalNails_SourceReview',(.48,.29,.235,1),.24,.12)]:
 m=bpy.data.materials.new(name);m.use_nodes=True;p=m.node_tree.nodes['Principled BSDF'];p.inputs['Base Color'].default_value=color;p.inputs['Roughness'].default_value=roughness;p.inputs['Subsurface Weight'].default_value=.08;p.inputs['Subsurface Scale'].default_value=.0008;p.inputs['Coat Weight'].default_value=coat;materials.append(m)
report={'schema':'sub01.official-original-hand-loop-uv.v1','source_rig':str(source),'source_rig_sha256':hashlib.sha256((R/'rig-r9/official-adult-hand-pair-rig.glb').read_bytes()).hexdigest(),'source_authority':'Original official Multires3 UVMap, exact original evaluated triangle/loop incidence','mesh_geometry_normals_rig_weights_modified':False,'scan_textures_included':False,'source_material_review_only':True,'native_imported':False,'sides':{}};corner_packet={}
for side,o in hands.items():
 original_geometry=[tuple(v.co)for v in o.data.vertices];original_weights=[tuple((g.group,g.weight)for g in v.groups)for v in o.data.vertices];original_normals=[tuple(v.normal)for v in o.data.vertices];layer=o.data.uv_layers.new(name='OriginalOfficialHumanUV');attribute=o.data.attributes.new('OriginalSculptFaceSet','INT','FACE');o.data.materials.clear()
 for material in materials:o.data.materials.append(material)
 nails={67,71,75,79,83}if side=='Left'else{87,91,95,99,103};rows=[];zero=[];nail_faces=0
 for p in o.data.polygons:
  ids=[maps[side][i]for i in p.vertices];record=triangle_source[tuple(sorted(ids))];u={i:v for i,v in zip(record['vertices'],record['uv'])};values=[u[i]for i in ids]
  for loop,i in zip(p.loop_indices,ids):layer.data[loop].uv=u[i]
  attribute.data[p.index].value=record['region'];p.material_index=int(record['region']in nails);nail_faces+=p.material_index
  a,b,c=values;area=abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))*.5
  if area==0:zero.append(p.index)
  rows.append({'rig_blend_face':p.index,'source_vertices':ids,'source_region':record['region'],'uv':values})
 assert not zero,('Original source UV has exact zero triangle areas',side,len(zero))
 assert original_geometry==[tuple(v.co)for v in o.data.vertices]and original_weights==[tuple((g.group,g.weight)for g in v.groups)for v in o.data.vertices]and original_normals==[tuple(v.normal)for v in o.data.vertices]
 report['sides'][side]={'vertices':len(o.data.vertices),'triangles':len(o.data.polygons),'exact_source_corner_uv_count':len(rows)*3,'exact_zero_uv_area_triangles':len(zero),'nail_triangles_from_actual_source_ids':nail_faces,'nail_source_face_sets':sorted(nails),'uv_bounds':[[min(v.uv[k]for v in layer.data)for k in[0,1]],[max(v.uv[k]for v in layer.data)for k in[0,1]]]};corner_packet[side]=rows
body.hide_set(True);ev.to_mesh_clear();rig=bpy.data.objects['CC0AnatomicalHandRig'];bpy.ops.object.select_all(action='DESELECT');rig.select_set(True)
for o in hands.values():o.select_set(True)
bpy.context.view_layer.objects.active=rig;bpy.ops.wm.save_as_mainfile(filepath=str(out/'official-hand-uv-material-source.blend'));bpy.ops.export_scene.gltf(filepath=str(out/'official-hand-uv-material-source.glb'),export_format='GLB',use_selection=True,export_animations=False,export_skins=True,export_all_influences=True)
with gzip.open(out/'exact-source-loop-uv.json.gz','wt')as f:json.dump(corner_packet,f,separators=(',',':'))
report['output_glb_sha256']=hashlib.sha256((out/'official-hand-uv-material-source.glb').read_bytes()).hexdigest();(out/'uv-source-report.json').write_text(json.dumps(report,indent=2)+'\n');print('OFFICIAL_SOURCE_LOOP_UV_RECOVERED',json.dumps(report),flush=True)
