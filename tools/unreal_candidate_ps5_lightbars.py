"""Only the genuine model's dedicated inner lightband emits; no white shell glow."""
from pathlib import Path
import json,time

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 from home_asset_audit import read_gltf
 assert active_candidate_guard();root=CANDIDATE/'private-audit';ps=json.loads((root/'original-ps5-native-assets.json').read_text());assembly=json.loads((root/'genuine-gaming-static-assembly.json').read_text());assert assembly['saved'];doc,_=read_gltf(Path('/workspace/sub01-home-private/ps5-datsketch-original-r1/original-unmodified-console.glb'));mel=u.MaterialEditingLibrary;eas=u.get_editor_subsystem(u.EditorActorSubsystem);before=snapshot(u,eas.get_all_level_actors());rows=[];done={}
 try:
  for part in ps['parts']:
   index=part['source_material_index'];path=part['actual_rendered_material']
   if index in done:assert done[index]==path;continue
   done[index]=path;mat=u.load_asset(path);assert isinstance(mat,u.MaterialInstanceConstant)and path.startswith(ps['owned_destination']+'/');names={str(n)for n in mel.get_vector_parameter_names(mat)};assert 'EmissiveFactor'in names,'Actual source emission parameter unavailable';v=mel.get_material_instance_vector_parameter_value(mat,'EmissiveFactor');prior=[v.r,v.g,v.b,v.a];expected=doc['materials'][index]['emissiveFactor'];assert max(abs(prior[k]-expected[k])for k in range(3))<1e-6
   target=[0,.0855460535,.25]if index==4 else[0,0,0];mel.set_material_instance_vector_parameter_value(mat,'EmissiveFactor',u.LinearColor(*target,prior[3]));actual=mel.get_material_instance_vector_parameter_value(mat,'EmissiveFactor');assert max(abs([actual.r,actual.g,actual.b][k]-target[k])for k in range(3))<1e-7;rows.append({'index':index,'name':doc['materials'][index]['name'],'material':path,'before':prior,'after':target,'only_inner_band_emits':index==4})
  assert len(rows)==13 and snapshot(u,eas.get_all_level_actors())==before and active_candidate_guard();assert u.EditorAssetLibrary.save_directory(ps['owned_destination'],only_if_is_dirty=False,recursive=True);result={'schema':'sub01.genuine-ps5-inner-lightbar-only.v1','saved':True,'materials':rows,'white_shell_emission_exact_zero':True,'only_original280triangle_lightband_emits':True,'all_geometry_and_nonemission_PBR_unchanged':True,'game_changed':False,'epoch':time.time()};(root/'genuine-ps5-inner-lightbar-only.json').write_text(json.dumps(result,indent=2)+'\n');return result
 except Exception:
  for r in rows:mel.set_material_instance_vector_parameter_value(u.load_asset(r['material']),'EmissiveFactor',u.LinearColor(*r['before']))
  raise
