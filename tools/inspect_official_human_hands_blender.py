"""Read-only official CC0 anatomical library inspection, no live project imports."""
import bpy,json,sys,hashlib
from pathlib import Path
root=Path('/workspace/sub01-home-private/human-base-hands-r1');source=root/'source/human-base-meshes-bundle-v1.4.1/human_base_meshes_bundle.blend'
bpy.ops.wm.read_factory_settings(use_empty=True)
with bpy.data.libraries.load(str(source),link=False)as(src,dst):
 names=list(src.objects);dst.objects=[n for n in names if n in ['Hand  - Realistic','GEO-body_male_realistic']]
rows=[]
for o in dst.objects:
 if o is None:continue
 bpy.context.scene.collection.objects.link(o);rows.append({'name':o.name,'type':o.type,'vertices':len(o.data.vertices)if o.type=='MESH'else None,'faces':len(o.data.polygons)if o.type=='MESH'else None,'dimensions_m':list(o.dimensions),'modifiers':[(m.name,m.type,getattr(m,'levels',None),getattr(m,'total_levels',None))for m in o.modifiers],'vertex_groups':[v.name for v in o.vertex_groups],'asset':{'description':o.asset_data.description,'author':o.asset_data.author,'license':o.asset_data.license}if o.asset_data else None})
(root/'source-inspection.json').write_text(json.dumps({'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'objects':names,'selected':rows,'native_imported':False},indent=2)+'\n');print('OFFICIAL_HAND_SELECTION',json.dumps(rows),flush=True)
