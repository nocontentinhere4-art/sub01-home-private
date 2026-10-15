"""Exact optional-map identity and complete native/backend geometry alignment."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from stage_unreal_home_runtime import stage
from unreal_bathroom_corridor_runtime import (
    CONTRACT_SHA, EXPORT_SHA, NODES, PREFIX, RECEIPT, SOURCE_SHA, TAG, install,
)


def receipt():
    return {'schema': 'sub01.bathroom-corridor-native-import.v1',
            'source_sha256': SOURCE_SHA, 'export_sha256': EXPORT_SHA,
            'source_contract_sha256': CONTRACT_SHA, 'source_nodes': NODES,
            'saved': True, 'originals_preserved': True}


def generated(project, row=None):
    (project / 'Config').mkdir()
    (project / 'Sub01HomeLab.uproject').write_text('{}')
    if row is not None:
        path = project / RECEIPT
        path.parent.mkdir()
        path.write_text(json.dumps(row))
    stage(project)
    return (project / 'Source/Sub01HomeLab/Sub01HomeLab.cpp').read_text()


def test_absent_receipt_preserves_legacy_generated_runtime():
    with tempfile.TemporaryDirectory() as folder:
        cpp = generated(Path(folder))
    assert 'Eye.X<-85' in cpp and 'FVector(-73.8f,135+' in cpp
    assert TAG not in cpp
    assert install('h', 'unrelated', Path(folder)) == ('h', 'unrelated')


def test_actual_owned_map_updates_all_camera_and_door_hooks_together():
    with tempfile.TemporaryDirectory() as folder:
        cpp = generated(Path(folder), receipt())
    assert 'Eye.X<-85' not in cpp and 'x<-85&&' not in cpp
    assert cpp.count('Eye.X<-100') == 6
    assert 'x<-100&&x>-378' in cpp
    assert 'FVector(-88.8f,135+(From+To)*.5f,405)' in cpp
    assert 'FVector(-100,135,405)' in cpp
    assert TAG in cpp and PREFIX in cpp
    assert 'C->IsVisible()&&C->GetCollisionEnabled()!=ECollisionEnabled::NoCollision' in cpp
    assert 'BathDoorClosed.AddToTranslation(FVector(11.2f,0,0))' in cpp
    assert 'if(P.X>-56.7||LiveHome)BathDoorEgressRequested=false;' in cpp
    assert 'LiveHomeNodes.Add(TEXT("bath_aisle"),FVector(-60.000000,-20.000000,300.000000));' in cpp
    assert 'LiveHomeNodes.Add(TEXT("bath_door"),FVector(-56.700000,135.000000,300.000000));' in cpp
    apply = cpp.split('void ASub01HomeCharacter::ApplyLiveHome(', 1)[1]
    assert apply.index('GeometryProfile!=TEXT("5ffac2406e66")') < apply.index('LiveHomeFresh=true')
    assert 'FCollisionShape::MakeBox(FVector(3.25f,44.5f+' in cpp
    assert 'GetCapsuleComponent()->InitCapsuleSize(16.f,91.f)' in cpp


@pytest.mark.parametrize('key,value', [
    ('saved', False), ('originals_preserved', False), ('export_sha256', 'wrong'),
    ('source_contract_sha256', 'wrong'), ('source_nodes', NODES[:-1]),
])
def test_present_incomplete_or_different_import_refuses_staging(key, value):
    row = {**receipt(), key: value}
    with tempfile.TemporaryDirectory() as folder:
        with pytest.raises(ValueError, match='receipt required'):
            generated(Path(folder), row)


def test_backend_and_bridge_import_the_matching_physical_graph_only_when_selected():
    code = '''
import json, home_world as w, home_interactions as i
from tools import unreal_home_state_bridge as bridge
assert bridge.NODES is w.NODES
world=w.HomeWorld(); view=world.view(); model=bridge.HomeStateModel()
model.apply_rest({'home':view}); model.set_connected(True)
matching_profile=model.document().get('native_geometry_profile')
view.pop('native_geometry_profile',None)
model.apply_rest({'home':view})
assert model.document().get('native_geometry_profile') is None
print(json.dumps({'aisle':w.NODES['bath_aisle'],'door':w.NODES['bath_door'],
 'inside':w.NODES['bathroom'],'bounds':i.BATHROOM_BOUNDS,'close':i.BATHROOM_CLOSE_X,
 'mask':i.PRIVATE_ACTOR['position'],'door_center':i.DOORS['bathroom']['centre'],
 'old_strip_private':i.in_bathroom([-.95,4.65,1.35]),
 'new_inside_private':i.in_bathroom([-1.1,4.65,1.35]),'matching_profile':matching_profile}))
'''
    env = dict(os.environ)
    env.pop('HOME_NATIVE_BATHROOM_CORRIDOR_PROFILE', None)
    legacy = json.loads(subprocess.check_output([sys.executable, '-c', code], cwd=ROOT, env=env))
    env['HOME_NATIVE_BATHROOM_CORRIDOR_PROFILE'] = '5ffac2406e66'
    new = json.loads(subprocess.check_output([sys.executable, '-c', code], cwd=ROOT, env=env))
    assert legacy['aisle'] == [-.5,4.65,-.2] and legacy['old_strip_private'] is True
    assert new['aisle'] == [-.6,4.65,-.2] and new['door'] == [-.567,4.65,1.35]
    assert new['inside'] == [-1.5,4.65,1.35] and new['bounds'] == [-3.78,-1.,.5,2.7]
    assert new['close'] == -1.35 and new['mask'] == new['door']
    assert new['door_center'] == [-1.,1.35]
    assert new['old_strip_private'] is False and new['new_inside_private'] is True
    assert legacy['matching_profile'] is None and new['matching_profile'] == '5ffac2406e66'
    env['HOME_NATIVE_BATHROOM_CORRIDOR_PROFILE'] = 'guess'
    failed = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env, capture_output=True)
    assert failed.returncode != 0 and b'Unknown private bathroom' in failed.stderr
