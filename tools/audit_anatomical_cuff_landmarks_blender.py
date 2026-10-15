"""Read-only anatomical seam evidence. No production mutation or inferred fit."""
import bpy,json
from pathlib import Path
from mathutils import Vector
source=Path('/workspace/sub01-home-private/human-base-hands-r1/rig-r8/official-adult-hand-pair-rig.blend');out=source.parent/'actual-cuff-anatomical-landmarks.json'
bpy.ops.wm.open_mainfile(filepath=str(source));rig=bpy.data.objects['CC0AnatomicalHandRig'];rows={}
for side in ['Left','Right']:
 o=bpy.data.objects['CC0Adult_'+side+'_ForearmHand_SOURCE_UNRIGGED'];w=rig.data.bones['mixamorig:'+side+'Hand'].head_local;m=rig.data.bones['mixamorig:'+side+'HandMiddle1'].head_local;axis=(m-w).normalized();selected=[]
 for v in o.data.vertices:
  fw=sum(g.weight for g in v.groups if 'Hand'in o.vertex_groups[g.group].name and not o.vertex_groups[g.group].name.endswith('Hand'))
  if fw>.5:selected.append(((v.co-w).dot(axis),v.index,list(v.co),fw,sorted([(o.vertex_groups[g.group].name,g.weight)for g in v.groups],key=lambda x:-x[1])[:5]))
 joints={b.name:{'head_axial_m':(b.head_local-w).dot(axis),'tail_axial_m':(b.tail_local-w).dot(axis),'head':list(b.head_local),'tail':list(b.tail_local)}for b in rig.data.bones if b.name.startswith('mixamorig:'+side+'Hand')}
 sections=[]
 for k in range(-20,25):
  depth=k*.0025;vs=[v for v in o.data.vertices if abs((v.co-w).dot(axis)-depth)<.00125];rad=[((v.co-w)-axis*(v.co-w).dot(axis)).length for v in vs]
  if rad:sections.append({'axial_m':depth,'vertices':len(vs),'radius_min_m':min(rad),'radius_max_m':max(rad)})
 rows[side]={'wrist':list(w),'palm_axis':list(axis),'closest_phalange_weighted_vertices':sorted(selected)[:10],'joint_axial_positions':joints,'actual_skin_crosssections':sections}
out.write_text(json.dumps({'source':str(source),'read_only':True,'sides':rows,'native_or_contact_accepted':False},indent=2)+'\n');print(json.dumps(rows,default=list)[:1500],flush=True)
