"""Rigidly place unchanged official archived AroundLarge beside genuine Rest sofa."""
import bpy,sys,json,hashlib
from pathlib import Path
from mathutils import Vector
ROOT=Path('/workspace/sub01-home-private/manufacturer-around-large-r1/output');OUT=ROOT.parent/'placed-r2';OUT.mkdir(parents=True,exist_ok=True)
assert hashlib.sha256((ROOT/'muuto-around-large.blend').read_bytes()).hexdigest()=='748b6c4a3a13fc1ec9dfb289e945e1269c5df4627178cf078dfb5bb5c12d90b8';bpy.ops.wm.open_mainfile(filepath=str(ROOT/'muuto-around-large.blend'));parts=[o for o in bpy.context.scene.objects if o.type=='MESH'];assert len(parts)==1;before={o.name:{'vertices':[tuple(v.co)for v in o.data.vertices],'uv':[tuple(v.uv)for v in o.data.uv_layers.active.data]}for o in parts}
for o in parts:w=o.matrix_world.copy();w.translation.x+=.052;o.matrix_world=w
for o in parts:assert before[o.name]=={'vertices':[tuple(v.co)for v in o.data.vertices],'uv':[tuple(v.uv)for v in o.data.uv_layers.active.data]}
pts=[o.matrix_world@v.co for o in parts for v in o.data.vertices];low=[min(p[k]for p in pts)for k in range(3)];high=[max(p[k]for p in pts)for k in range(3)];assert abs((low[0]+high[0])/2+2.538)<1e-6 and abs(low[2]-.02505)<1e-7
# Independently measure the four authored foot patches, rather than one global minimum.
feet=[p for p in pts if p.z<low[2]+.002];todo=set(range(len(feet)));groups=[]
while todo:
 seed=todo.pop();g={seed};queue=[seed]
 while queue:
  i=queue.pop();near={j for j in todo if (Vector((feet[i].x,feet[i].y))-Vector((feet[j].x,feet[j].y))).length<.06};todo-=near;g|=near;queue+=list(near)
 groups.append({'bottomPatchVertices':len(g),'minZM':min(feet[i].z for i in g),'maxZM':max(feet[i].z for i in g),'centroidXYM':[sum(feet[i][k]for i in g)/len(g)for k in range(2)]})
assert len(groups)==4,groups
for g in groups:g['lowestVertexGapFromSourceFloorM']=g['minZM']-.02505
bpy.ops.object.select_all(action='DESELECT')
for o in parts:o.select_set(True)
bpy.context.view_layer.objects.active=parts[0];bpy.ops.export_scene.gltf(filepath=str(OUT/'muuto-around-large.glb'),export_format='GLB',use_selection=True,export_cameras=False,export_lights=False);bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'muuto-around-large.blend'));report=json.loads((ROOT/'source-report.json').read_text());report.update(schema='sub01.manufacturer-around-large-rigid-placement.v1',parentSourceGlbSha256='1a7c531c5ddc58a55a965daa2f1e0f5932e1b76ed67811375ca65c46548a99e3',rigidDeltaUEcm=[5.2,0,0],centreUEcm=[-253.8,-5],boundsBlenderM=[low,high],boundsUEcm=[[100*low[0],-100*high[1],100*low[2]],[100*high[0],-100*low[1],100*high[2]]],actualFourFootPatchSupport=groups,originalLocalVertexAndUVArraysExactlyUnchanged=True,currentSKUExactMatchClaimed=False,archivedOfficialVariantRetained=True,nativeImportPermitted=False,placementAndRoutesAccepted=False,files={name:hashlib.sha256((OUT/name).read_bytes()).hexdigest()for name in['muuto-around-large.glb','muuto-around-large.blend']});(OUT/'source-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
