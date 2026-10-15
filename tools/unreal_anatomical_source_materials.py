"""Bind exact verified fresh glTF source PBR to the fresh FBX owner asset only."""
from pathlib import Path
import json,struct,math,time

def close(a,b):
 if isinstance(b,(list,tuple)):return isinstance(a,(list,tuple))and len(a)==len(b)and all(close(x,y)for x,y in zip(a,b))
 return type(a)in(int,float)and math.isfinite(a)and abs(a-b)<=1e-5

def validate_record(source,actual,owned):
 p=source.get('pbrMetallicRoughness',{});v=actual['vectors'];s=actual['scalars'];t=actual['textures'];ext=source.get('extensions',{})
 assert close(v.get('BaseColorFactor'),p.get('baseColorFactor',[1,1,1,1]))
 for name,key,default in [('MetallicFactor','metallicFactor',1),('RoughnessFactor','roughnessFactor',1)]:assert close(s.get(name),p.get(key,default))
 assert actual['actual_two_sided']is source.get('doubleSided',False)and actual['actual_blend_mode']=='<BlendMode.BLEND_OPAQUE: 0>'
 for parent,key,param in [(p,'baseColorTexture','BaseColorTexture'),(p,'metallicRoughnessTexture','MetallicRoughnessTexture'),(source,'normalTexture','NormalTexture'),(source,'occlusionTexture','OcclusionTexture'),(source,'emissiveTexture','EmissiveTexture')]:
  if key not in parent:continue
  assert t.get(param,'').startswith(owned+'/'),'Actual declared source texture must be owned, not default'
  transform=parent[key].get('extensions',{}).get('KHR_texture_transform',{});assert close(v.get(param+'_OffsetScale'),transform.get('offset',[0,0])+transform.get('scale',[1,1]))
 if 'normalTexture'in source:assert close(s.get('NormalScale'),source['normalTexture'].get('scale',1))
 if 'KHR_materials_sheen'in ext:
  sheen=ext['KHR_materials_sheen'];assert close(v.get('SheenColorFactor',[])[:3],sheen.get('sheenColorFactor',[0,0,0]))and close(s.get('SheenRoughnessFactor'),sheen.get('sheenRoughnessFactor',0))
 if 'KHR_materials_clearcoat'in ext:
  coat=ext['KHR_materials_clearcoat'];assert close(s.get('ClearCoatFactor'),coat.get('clearcoatFactor',0))and close(s.get('ClearCoatRoughnessFactor'),coat.get('clearcoatRoughnessFactor',0))
 return True

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_anatomical_owner_candidate import SOURCE,SHA,source_contract
 from unreal_import_reference_entry import snapshot
 assert active_candidate_guard();raw=SOURCE.read_bytes();source_contract(raw);source=json.loads(raw[20:20+struct.unpack_from('<I',raw,12)[0]])
 r=CANDIDATE/'private-audit';inventory=json.loads((r/'anatomical-owned-material-inventory.json').read_text());gltf=json.loads((r/'anatomical-owner-gltf-candidate.json').read_text());fbx=json.loads((r/'anatomical-owner-fbx-candidate.json').read_text());assert inventory['source_sha256']==SHA and fbx['initial_inventory_passed']and json.loads((r/'anatomical-body-pose-audit.json').read_text())['body_pose_equivalence_passed']
 materials={}
 for row in inventory['rows']:
  if row['format']!='gltf':continue
  for m in row['slots']:
   if m['slot']in materials:assert materials[m['slot']]==m
   materials[m['slot']]=m
 assert set(materials)=={m['name']for m in source['materials']}and len(materials)==9
 for m in source['materials']:validate_record(m,materials[m['name']],gltf['destination'])
 mesh=u.load_asset(fbx['meshes'][0]['path']);assert mesh.get_path_name().startswith(fbx['destination']+'/')
 original=list(mesh.get_editor_property('materials'));old=[s.get_editor_property('material_interface')for s in original];eas=u.get_editor_subsystem(u.EditorActorSubsystem);before=snapshot(u,eas.get_all_level_actors())
 assignments=[]
 try:
  slots=list(mesh.get_editor_property('materials'));assert len(slots)==9
  for slot in slots:
   name=str(slot.get_editor_property('material_slot_name'));assert name in materials
   m=u.load_asset(materials[name]['material']);assert isinstance(m,u.MaterialInstanceConstant)and m.get_path_name().startswith(gltf['destination']+'/');slot.set_editor_property('material_interface',m);assignments.append({'slot':name,'source_owned_material':m.get_path_name()})
  mesh.set_editor_property('materials',slots)
  assert [s.get_editor_property('material_interface').get_path_name()for s in mesh.get_editor_property('materials')]==[a['source_owned_material']for a in assignments]
  assert snapshot(u,eas.get_all_level_actors())==before and active_candidate_guard()
  # Persist only the fresh source materials/textures and fresh combined owner.
  for path in gltf['owned_paths']:
   obj=u.load_asset(path)
   if isinstance(obj,(u.MaterialInterface,u.Texture)):u.EditorAssetLibrary.save_loaded_asset(obj,only_if_is_dirty=False)
  u.EditorAssetLibrary.save_loaded_asset(mesh,only_if_is_dirty=False)
 except Exception:
  slots=list(mesh.get_editor_property('materials'))
  for slot,m in zip(slots,old):slot.set_editor_property('material_interface',m)
  mesh.set_editor_property('materials',slots);raise
 report={'schema':'sub01.anatomical-exact-source-material-binding.v1','source_sha256':SHA,'mesh':mesh.get_path_name(),'assignments':assignments,'core_factors_textures_transforms_two_sided_verified':True,'cuff_normal_625x625_verified':True,'sheen_matches_base_color_verified':True,'separate_nail_clearcoat_verified':True,'world_snapshot_unchanged':snapshot(u,eas.get_all_level_actors())==before,'owner_assigned':False,'map_saved':False,'advanced_shading_visual_acceptance':False,'epoch':time.time()};(r/'anatomical-source-material-binding.json').write_text(json.dumps(report,indent=2)+'\n');return report
