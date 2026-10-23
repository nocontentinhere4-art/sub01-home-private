from pathlib import Path
import json
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import stage_unreal_home_runtime as runtime
from unreal_import_real_bathroom_pendant import validate
from tools.pixel_streaming.native_live_viewer import validate_settings

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'docs/proposed/real-bathroom-pendant-source/split-v3/bathroom-pendant.glb'


def test_actual_frozen_fixture_has_three_independent_real_material_roles():
    proof,doc,blob=validate(SOURCE)
    assert proof['standing_headroom_m']>2.25
    assert {n['name'] for n in doc['nodes']}=={'SUB01_RealBathroomPendant_Glass','SUB01_RealBathroomPendant_Metal','SUB01_RealBathroomPendant_Globe'}
    assert sum(doc['accessors'][p['indices']]['count']//3 for m in doc['meshes'] for p in m['primitives'])==5602


def test_partial_source_proof_is_refused(tmp_path):
    p=tmp_path/SOURCE.name;p.write_bytes(SOURCE.read_bytes())
    proof=json.loads(SOURCE.with_suffix('.json').read_text());proof['native_material_parts']=2
    p.with_suffix('.json').write_text(json.dumps(proof))
    with pytest.raises(RuntimeError,match='complete three-part'):validate(p)


def test_old_map_does_not_gain_unavailable_bathroom_control():
    request={'lamps':{'BathroomCeiling':True}}
    with pytest.raises(ValueError):validate_settings(request,{'lamps':['DeskLamp']})
    assert validate_settings(request,{'lamps':['BathroomCeiling']})==request
    assert validate_settings({'lamps':{'DeskLamp':False}},{'lamps':['DeskLamp']})=={'lamps':{'DeskLamp':False}}


def test_full_stage_requires_actual_optional_globe_and_preserves_original_lamps(tmp_path):
    (tmp_path/'Sub01HomeLab.uproject').write_text('{}');(tmp_path/'Config').mkdir();runtime.stage(tmp_path)
    cpp=(tmp_path/'Source/Sub01HomeLab/Sub01HomeLab.cpp').read_text()
    assert 'if(!LightActor)return true;' in cpp
    assert cpp.count('{TEXT("BathroomCeiling"),5.5f}')==2
    assert 'Globe->SetMaterial(0,Prepared);BathroomLampMID=Prepared;' in cpp
    assert 'V_c953ce762552/Attempt_' in cpp
    assert 'ApplyNativeFixtureEmission(LampName,Enabled);' in cpp
    assert 'if(LampName==TEXT("BathroomCeiling"))ApplyNativeBathroomLamp(Enabled);' in cpp


def test_prepared_native_mesh_identities_change_no_payload_or_world_geometry(tmp_path):
    from unreal_import_real_bathroom_pendant import prepare_native_input
    from home_asset_audit import read_gltf
    proof=prepare_native_input(SOURCE,tmp_path/'native.glb')
    original,old=read_gltf(SOURCE);actual,new=read_gltf(tmp_path/'native.glb')
    assert bytes(old)==bytes(new)
    assert proof['source_document_except_mesh_names_and_all_binary_exact'] is True
    assert {m['name'] for m in actual['meshes']}=={n['name'] for n in original['nodes']}
    for index,mesh in enumerate(original['meshes']):actual['meshes'][index]['name']=mesh['name']
    assert original==actual


def test_actual_source_slot_survives_unreal_truncated_material_asset_names():
    from types import SimpleNamespace
    from unreal_import_real_bathroom_pendant import source_slot_binding
    _,doc,_=validate(SOURCE);source=next(m for m in doc['materials'] if m['name']=='modern_ceiling_globe')
    dest='/Game/Sub01Home/RealBathroomPendant/V_c953ce762552/Attempt_test'
    # Exact observed native failure: source slot is modern_ceiling_globe but
    # UE shortened its long generated asset basename to mode_lobe.
    material=SimpleNamespace(get_path_name=lambda:dest+'/source/Materials/mode_lobe.mode_lobe')
    values={'material_slot_name':'modern_ceiling_globe','material_interface':material}
    slot=SimpleNamespace(get_editor_property=lambda key:values[key])
    mesh=SimpleNamespace(get_editor_property=lambda key:[slot])
    component=SimpleNamespace(get_editor_property=lambda key:mesh,get_material=lambda index:material)
    assert source_slot_binding(component,source,dest)=={source['name']:material.get_path_name()}
    for wrong in ['modern_ceiling_lamp_01','modern_ceiling_lamp_01_glass','mode_lobe']:
        values['material_slot_name']=wrong
        with pytest.raises(RuntimeError,match='Exact original material slot'):source_slot_binding(component,source,dest)
    values['material_slot_name']=source['name'];values['material_interface']=object()
    with pytest.raises(RuntimeError):source_slot_binding(component,source,dest)
    values['material_interface']=material
    with pytest.raises(RuntimeError):source_slot_binding(component,source,'/Game/AnotherNamespace')


def test_source_slot_refuses_non_material_and_empty_interfaces_with_runtime_error():
    from types import SimpleNamespace
    from unreal_import_real_bathroom_pendant import source_slot_binding
    _,doc,_=validate(SOURCE);source=next(m for m in doc['materials'] if m['name']=='modern_ceiling_globe')
    dest='/Game/Sub01Home/RealBathroomPendant/V_c953ce762552/Attempt_test'
    material=SimpleNamespace(get_path_name=lambda:dest+'/source/Materials/mode_lobe.mode_lobe');foreign=object()
    values={'material_slot_name':source['name'],'material_interface':None}
    slot=SimpleNamespace(get_editor_property=lambda key:values[key])
    mesh=SimpleNamespace(get_editor_property=lambda key:[slot])
    component=SimpleNamespace(get_editor_property=lambda key:mesh,get_material=lambda index:material)
    with pytest.raises(RuntimeError,match='Exact original material slot')as error:source_slot_binding(component,source,dest)
    assert 'slot_material=[None]' in str(error.value)
    values['material_interface']=foreign
    with pytest.raises(RuntimeError,match='Exact original material slot')as error:source_slot_binding(component,source,dest)
    assert repr(type(foreign)) in str(error.value)
    component.get_material=lambda index:foreign
    with pytest.raises(RuntimeError,match='Exact original material slot')as error:source_slot_binding(component,source,dest)
    assert repr(type(foreign)) in str(error.value)
    values['material_interface']=None;component.get_material=lambda index:None
    with pytest.raises(RuntimeError,match='Exact original material slot'):source_slot_binding(component,source,dest)
    with pytest.raises(RuntimeError,match='Exact original material slot'):source_slot_binding(SimpleNamespace(get_editor_property=lambda key:None,get_material=lambda index:material),source,dest)


def test_explicit_slot_binding_still_runs_every_original_pbr_factor_gate():
    from types import SimpleNamespace
    from unreal_import_real_linea140 import verify_materials
    class Mat:
        def get_path_name(self):return '/Game/Owned/Materials/mode_lobe.mode_lobe'
        def get_name(self):return 'mode_lobe'
    mat=Mat();value=[1.,1.,1.,1.]
    mel=SimpleNamespace(get_vector_parameter_names=lambda m:['BaseColorFactor','EmissiveFactor'],
        get_scalar_parameter_names=lambda m:['MetallicFactor','RoughnessFactor'],get_texture_parameter_names=lambda m:[],
        get_material_instance_vector_parameter_value=lambda m,p:SimpleNamespace(**dict(zip(['r','g','b','a'],value if p=='BaseColorFactor' else [0.,0.,0.,0.]))),
        get_material_instance_scalar_parameter_value=lambda m,p:1.)
    u=SimpleNamespace(MaterialEditingLibrary=mel,MaterialInstanceConstant=Mat,TextureCompressionSettings=SimpleNamespace(TC_DEFAULT=0,TC_MASKS=1,TC_NORMALMAP=2))
    c=SimpleNamespace(get_materials=lambda:[mat]);doc={'materials':[{'name':'modern_ceiling_globe'}]}
    binding={'modern_ceiling_globe':mat.get_path_name()}
    assert verify_materials(u,[c],doc,'/Game/Owned',material_bindings=binding)[0]['source_material']=='modern_ceiling_globe'
    value[0]=.5
    with pytest.raises(RuntimeError,match='base factor'):verify_materials(u,[c],doc,'/Game/Owned',material_bindings=binding)
    value[0]=1.
    for bad in [{},{'modern_ceiling_globe':'/Game/Other.Other'},{'wrong':mat.get_path_name()}]:
        with pytest.raises(RuntimeError,match='Explicit source material bindings'):verify_materials(u,[c],doc,'/Game/Owned',material_bindings=bad)


def test_native_fixture_uses_preserved_source_slot_not_shortened_asset_basename(tmp_path):
    (tmp_path/'Sub01HomeLab.uproject').write_text('{}');(tmp_path/'Config').mkdir();runtime.stage(tmp_path)
    cpp=(tmp_path/'Source/Sub01HomeLab/Sub01HomeLab.cpp').read_text()
    method=cpp.split('bool ASub01HomeCharacter::PrepareNativeBathroomLamp(){',1)[1].split('void ASub01HomeCharacter::ApplyNativeBathroomLamp',1)[0]
    assert 'SourceSlots.Num()!=1||SourceSlots[0].MaterialSlotName!=FName(TEXT("modern_ceiling_globe"))' in method
    assert 'SourceSlots[0].MaterialInterface.Get()!=Original' in method
    assert 'Original->GetName().Contains' not in method
    assert 'Original->GetPathName().StartsWith(Prefix)' in method
    assert 'FMath::IsNearlyEqual(Factor.R,.6229580641f,.00001f)' in method
    assert 'FMath::IsNearlyEqual(Factor.G,.5416215658f,.00001f)' in method
    assert 'FMath::IsNearlyEqual(Factor.B,.4745504856f,.00001f)' in method
