"""Read actual owned chair/transition assets; never import, alter a pose or enable seating."""
from __future__ import annotations
import hashlib,json,struct,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CLIPS={'sit_down':'room_mx_stand_to_sit.glb','get_up':'room_mx_sit_to_stand.glb','sitting':'room_mx_sitting.glb','sit_to_type':'room_mx_sit_to_type.glb'}

def glb_json(path):
 data=path.read_bytes()
 if data[:4]!=b'glTF':raise ValueError('Not a GLB')
 size,kind=struct.unpack_from('<II',data,12)
 if kind!=0x4e4f534a:raise ValueError('Missing first JSON chunk')
 return json.loads(data[20:20+size]),hashlib.sha256(data).hexdigest()

def dump(path):
 with tempfile.TemporaryDirectory()as td:
  out=Path(td)/'rig.json'
  subprocess.run(['node',str(ROOT/'tools/animation_rig_dump.mjs'),str(path),str(out)],check=True,capture_output=True)
  return json.loads(out.read_text())

def clip_record(owner,clip):
 bones=[n['name']for n in owner['nodes']if n['name'].startswith('mixamorig:')]
 refs={n['name']:n for n in owner['nodes']if n['name']in bones}
 same=True;max_error=0.0
 for n in clip['nodes']:
  if n['name'] not in refs:continue
  ref=refs[n['name']]
  for key,default in [('translation',[0,0,0]),('rotation',[0,0,0,1]),('scale',[1,1,1])]:
   err=max(abs(a-b)for a,b in zip(n[key]or default,ref[key]or default));max_error=max(max_error,err);same &=err<1e-5
 hip=next(i for i,n in enumerate(clip['nodes'])if n['name']=='mixamorig:Hips')
 anim=clip['animations'][0]
 channel=next(c for c in anim['channels']if c['node']==hip and c['path']=='translation')
 root=clip['nodes'][clip['nodes'][hip]['parent']]
 if root['scale']!=[.01,.01,.01] or root['translation'] or root['rotation'] or root['matrix']:raise ValueError('Unexpected armature transform; do not silently reinterpret units')
 values=channel['values'];times=channel['times']
 return {'sha256':clip['sha256'],'bone_names_match':set(bones)=={n['name']for n in clip['nodes']if n['name'].startswith('mixamorig:')},'bone_count':len(bones),'reference_trs_match':bool(same),'max_reference_trs_error':max_error,'duration_s':max(c['times'][-1]for c in anim['channels']),'hip_translation_cm':{'first':values[0],'last':values[-1],'min':[min(v[i]for v in values)for i in range(3)],'max':[max(v[i]for v in values)for i in range(3)],'samples':len(times)},'native_object_path':None,'native_same_skeleton_verified':False,'physical_contact_verified':False}

def inventory():
 owner=dump(ROOT/'web/room/char_mixamo.glb');chair,chair_sha=glb_json(ROOT/'web/room/chair_owner.glb')
 chair_node=chair['nodes'][0];seat=chair_node['extras']['seatTop']
 return {'schema':'sub01.native-seating-inventory.v1','source_only':True,'owner_sha256':owner['sha256'],'clips':{key:clip_record(owner,dump(ROOT/'web/room/mh_mx'/file))for key,file in CLIPS.items()},'chair':{'sha256':chair_sha,'authored_seat_top_cm':seat*100,'house_origin_ue_cm':[200,-190,0],'seat_surface_ue_z_cm':seat*100,'source':'Tripo(owner), repaired, own materials','native_unique_component':None,'native_collider_contact_verified':False},'provenance':{'clip_recipe':'room_build/kimodo/mixamo_clips.json','pipeline':'room_build/kimodo/mixamo_build.sh','status':'Mixamo-derived captures retargeted/fitted to owned character; not raw unchanged FBX','raw_sit_fbx_present':False},'missing_acceptance':['Import these clips on the actual owner USkeleton, preserving the authored reference pose','Identify unique chair cushion collider from actual imported bounds/material; fallback box is not actual geometry','Validate pelvis/thigh skin, feet and continuous approach-to-sit contact; hip joint is anatomically above the cushion','Verify native get-up and collision-safe departure without actor-position assignment'],'ready':False}

if __name__=='__main__':print(json.dumps(inventory(),indent=2))
