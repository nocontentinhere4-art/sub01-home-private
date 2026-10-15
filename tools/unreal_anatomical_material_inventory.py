"""Read-only exact fresh-owner material inventory; no assignment or shader edits."""
from pathlib import Path
import json,time

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_anatomical_owner_candidate import SHA
 from unreal_import_candidate_photo_plants import actual_material_property
 assert active_candidate_guard()
 out={'schema':'sub01.anatomical-owned-material-inventory.v1','source_sha256':SHA,'read_only':True,'rows':[],'epoch':time.time()};mel=u.MaterialEditingLibrary
 for kind in ['gltf','fbx']:
  p=CANDIDATE/('private-audit/anatomical-owner-'+kind+'-candidate.json')
  if not p.exists():continue
  d=json.loads(p.read_text());assert d['source_sha256']==SHA
  dest=d['destination'];assert dest.startswith('/Game/Sub01Hands/AnatomicalCandidate/')
  paths=d.get('owned_paths',[])
  for path in paths:
   assert path.startswith(dest+'/');mesh=u.load_asset(path)
   if not isinstance(mesh,u.SkeletalMesh):continue
   row={'format':kind,'mesh':path,'slots':[]}
   for i,slot in enumerate(mesh.get_editor_property('materials')):
    m=slot.get_editor_property('material_interface');r={'index':i,'slot':str(slot.get_editor_property('material_slot_name')),'material':m.get_path_name()if m else None}
    if isinstance(m,u.MaterialInstanceConstant):
     r.update(parent=m.get_editor_property('parent').get_path_name(),vectors={str(n):[float(getattr(mel.get_material_instance_vector_parameter_value(m,n),c))for c in('r','g','b','a')]for n in mel.get_vector_parameter_names(m)},scalars={str(n):float(mel.get_material_instance_scalar_parameter_value(m,n))for n in mel.get_scalar_parameter_names(m)},textures={str(n):(lambda t:t.get_path_name()if t else None)(mel.get_material_instance_texture_parameter_value(m,n))for n in mel.get_texture_parameter_names(m)})
    if m:
     r['actual_two_sided']=bool(actual_material_property(m,'two_sided','override_two_sided'));r['actual_blend_mode']=str(actual_material_property(m,'blend_mode','override_blend_mode'))
    row['slots'].append(r)
   out['rows'].append(row)
 assert active_candidate_guard();p=CANDIDATE/'private-audit/anatomical-owned-material-inventory.json';p.write_text(json.dumps(out,indent=2)+'\n');return {'receipt':str(p),'mesh_count':len(out['rows']),'changed':False}
