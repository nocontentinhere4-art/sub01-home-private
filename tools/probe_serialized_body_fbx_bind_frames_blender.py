"""Read-only physical bind-frame comparison, not Blender REST shape acceptance."""
import bpy,json,sys,hashlib
from pathlib import Path
original,candidate,fbx,output=sys.argv[sys.argv.index('--')+1:]
import re
finger=lambda n:bool(re.search(r'Hand(?:Thumb|Index|Middle|Ring|Pinky)[1-4]$',n))
def snapshot(path,fmt):
 bpy.ops.wm.read_factory_settings(use_empty=True)
 if fmt=='glb':bpy.ops.import_scene.gltf(filepath=path)
 else:bpy.ops.import_scene.fbx(filepath=path,use_anim=False,automatic_bone_orientation=False)
 arm=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE');assert len(arm.data.bones)==65
 return {b.name:{'world_bind_frame':[list(r)for r in arm.matrix_world@b.matrix_local],'parent':b.parent.name if b.parent else None}for b in arm.data.bones if not finger(b.name)}
a=snapshot(original,'glb');b=snapshot(candidate,'glb');c=snapshot(fbx,'fbx');assert len(a)==len(b)==len(c)==25
rows=[]
for name,base in a.items():
 assert b[name]['parent']==c[name]['parent']==base['parent']
 def error(other):return max(abs(x-y)for ar,br in zip(base['world_bind_frame'],other['world_bind_frame'])for x,y in zip(ar,br))
 rows.append({'bone':name,'original_GLTF_vs_anatomical_GLTF_bind_frame_max_error':error(b[name]),'original_GLTF_vs_anatomical_FBX_bind_frame_max_error':error(c[name])})
report={'schema':'sub01.original25-fbx-blender-bind-frame-probe.v1','original_sha256':hashlib.sha256(Path(original).read_bytes()).hexdigest(),'candidate_sha256':hashlib.sha256(Path(candidate).read_bytes()).hexdigest(),'fbx_sha256':hashlib.sha256(Path(fbx).read_bytes()).hexdigest(),'bones':rows,'maximum_anatomical_GLTF_difference':max(r['original_GLTF_vs_anatomical_GLTF_bind_frame_max_error']for r in rows),'maximum_anatomical_FBX_difference':max(r['original_GLTF_vs_anatomical_FBX_bind_frame_max_error']for r in rows),'definition':'Armature object world times edit-bone matrix_local; compare original and anatomical source through same Blender glTF convention, then exported/reimported FBX. This is a frame-coordinate probe, not a claim that Blender REST equals original serialized glTF posed skin.','native_imported':False,'native_or_contact_accepted':False}
Path(output).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
