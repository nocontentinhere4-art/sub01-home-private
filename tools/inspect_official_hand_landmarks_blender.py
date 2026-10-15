"""Inspect real anatomical source bone geometry; never edits live world."""
import bpy,json
from pathlib import Path
from mathutils import Vector
root=Path('/workspace/sub01-home-private/human-base-hands-r1');path=root/'source/human-base-meshes-bundle-v1.4.1/human_base_meshes_bundle.blend'
bpy.ops.wm.read_factory_settings(use_empty=True)
with bpy.data.libraries.load(str(path),link=False)as(src,dst):dst.objects=[n for n in src.objects if n.startswith('GEO-skeletion.')and any(k in n for k in['metacarpal','proximal.','middle.','distal.','radius','ulna','skull'])]+['GEO-body_male_realistic']
rows=[]
for o in dst.objects:
 bpy.context.scene.collection.objects.link(o);bpy.context.view_layer.update()
 if o.type!='MESH':continue
 p=[o.matrix_world@v.co for v in o.data.vertices];rows.append({'name':o.name,'position':list(o.matrix_world.translation),'bounds':[[min(v[i]for v in p)for i in range(3)],[max(v[i]for v in p)for i in range(3)]],'vertices':len(p),'mean':list(sum(p,Vector())/len(p))})
(root/'anatomical-bone-geometry-landmarks.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(rows),flush=True)
