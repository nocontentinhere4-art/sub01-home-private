"""Recover actual authored sculpt-region incidence onto unchanged highres hands.
No nearest-finger heuristics, geometry or weight edits. Exact source coordinates.
"""
import bpy,json,collections,hashlib
from pathlib import Path
R=Path('/workspace/sub01-home-private/human-base-hands-r1');source=R/'rig-r9/official-adult-hand-pair-rig.blend';bpy.ops.wm.open_mainfile(filepath=str(source));body=bpy.data.objects['GEO-body_male_realistic'];body.hide_set(False)
for m in body.modifiers:
 assert m.type=='MULTIRES';m.levels=3;m.render_levels=3
bpy.context.view_layer.update();evaluated=body.evaluated_get(bpy.context.evaluated_depsgraph_get());full=evaluated.to_mesh();label=full.attributes.get('.sculpt_face_set');assert label and label.domain=='FACE'and label.data_type=='INT','Original sculpt regions did not survive evaluation; refuse inferred ancestry'
world=[body.matrix_world@v.co for v in full.vertices]
def key(p):return tuple(round(x*1e7)for x in p)
lookup=collections.defaultdict(list)
for i,p in enumerate(world):lookup[key(p)].append(i)
needed=set();hands={};output={'schema':'sub01.exact-authored-highres-hand-regions.v1','rig_source':str(source),'position_quantum_m':1e-7,'method':'Actual Multires-evaluated original FACE .sculpt_face_set incidence, matched by exact source-world coordinate key; no nearest digit classification','source_region_attribute_propagated':True,'sides':{},'weights_or_geometry_modified':False}
for side in ['Left','Right']:
 o=bpy.data.objects['CC0Adult_'+side+'_ForearmHand_SOURCE_UNRIGGED'];rows=[]
 for v in o.data.vertices:
  coordinate=o.matrix_world@v.co;ids=lookup[key(coordinate)];assert len(ids)==1,('Original source vertex identity ambiguous',side,v.index,ids);needed.add(ids[0]);rows.append({'rig_blend_vertex':v.index,'source_evaluated_vertex':ids[0],'source_world_coordinate_key':list(key(coordinate))})
 hands[side]=rows
incidence={i:set()for i in needed}
for p in full.polygons:
 value=label.data[p.index].value
 for i in p.vertices:
  if i in incidence:incidence[i].add(value)
for side,rows in hands.items():
 for row in rows:
  row['source_face_set_ids']=sorted(incidence[row['source_evaluated_vertex']]);assert row['source_face_set_ids']
 output['sides'][side]={'vertices':len(rows),'regions':dict(collections.Counter(v for row in rows for v in row['source_face_set_ids'])),'rows':rows}
out=R/'rig-r9/exact-authored-highres-regions.json';out.write_text(json.dumps(output,separators=(',',':'))+'\n');evaluated.to_mesh_clear();print('EXACT_AUTHORED_REGION_MAP_COMPLETE',out.stat().st_size,{side:{k:v for k,v in data.items()if k!='rows'}for side,data in output['sides'].items()},flush=True)
