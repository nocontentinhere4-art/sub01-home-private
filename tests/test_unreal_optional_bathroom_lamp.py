from pathlib import Path
import json
import pytest
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
