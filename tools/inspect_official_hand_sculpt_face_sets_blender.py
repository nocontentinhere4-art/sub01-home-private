"""Read genuine official sculpt labels; no inferred digit names or source edits."""
import bpy,json,collections
from pathlib import Path
R=Path('/workspace/sub01-home-private/human-base-hands-r1');source=R/'source/human-base-meshes-bundle-v1.4.1/human_base_meshes_bundle.blend';bpy.ops.wm.read_factory_settings(use_empty=True)
with bpy.data.libraries.load(str(source),link=False)as(src,dst):dst.objects=['GEO-body_male_realistic']
o=dst.objects[0];bpy.context.scene.collection.objects.link(o);bpy.context.view_layer.update();attr=o.data.attributes['.sculpt_face_set'];points=[o.matrix_world@v.co for v in o.data.vertices];report={'actual_source_body':o.name,'face_set_count':len(set(v.value for v in attr.data)),'sides':{}}
for side,sign in [('Left',1),('Right',-1)]:
 sets=collections.defaultdict(list)
 for p in o.data.polygons:
  vs=[points[i]for i in p.vertices];center=sum(vs,vs[0]*0)/len(vs)
  if sign*(center.x-o.matrix_world.translation.x)>.28 and .65<center.z<1.0:sets[attr.data[p.index].value].append(p)
 summary=[]
 for label,faces in sets.items():
  indices=sorted({i for p in faces for i in p.vertices});ps=[points[i]for i in indices];summary.append({'source_face_set_id':label,'faces':len(faces),'vertices':len(indices),'bounds':[[min(p[k]for p in ps)for k in range(3)],[max(p[k]for p in ps)for k in range(3)]],'centroid':[sum(p[k]for p in ps)/len(ps)for k in range(3)],'source_vertices':indices})
 report['sides'][side]=summary
out=R/'rig-r8/official-source-hand-face-sets.json';out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({**report,'sides':{s:[{k:v for k,v in row.items()if k!='source_vertices'}for row in rows]for s,rows in report['sides'].items()}},indent=2),flush=True)
