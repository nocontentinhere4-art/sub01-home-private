"""Seated contact measurement: two-sided gate, actual surface geometry, analyzer contract.

The analyzer needs the server editor (imported soft vertices); here its geometry function is
compiled verbatim and the validator is exercised on complete and failing reports.
"""
import copy
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import validate_unreal_seat_contact as seat  # noqa: E402
import unreal_skin_contact_native as native  # noqa: E402


def report(seat_gap=-.8, left=.3, right=.4):
    def region(name, gap):
        return {'region': name, 'selectedVertices': 900, 'overSurfaceVertices': 400, 'bandVertices': 120,
                'minGapCm': gap, 'maxGapCm': gap + 12}
    row = {'invalidInfluences': 0, 'floorCm': 0.0,
           'regions': [region('seat', seat_gap), region('left_sole', left), region('right_sole', right)]}
    return {'samples': [dict(copy.deepcopy(row), time=3 + i / 60) for i in range(301)]}


def test_complete_seated_contact_is_accepted_and_reported():
    result = seat.validate(report())
    assert result['samples'] == 301
    assert result['min_gap_range_cm']['seat'] == (-.8, -.8)
    assert 'not a physical sit transition' in result['acceptance']


@pytest.mark.parametrize('region,gap,ok', [
    ('seat', -2.5, True), ('seat', .5, True), ('seat', .51, False), ('seat', 3.0, False), ('seat', -2.51, False),
    ('left_sole', 0, True), ('left_sole', 1.0, True), ('left_sole', -.01, False), ('left_sole', 1.2, False),
    ('right_sole', 4.0, False), ('right_sole', -1.0, False),
])
def test_gap_and_penetration_are_both_failures_in_any_sample(region, gap, ok):
    data = report()
    index = seat.REGIONS.index(region)
    data['samples'][237]['regions'][index]['minGapCm'] = gap
    if ok:
        seat.validate(data)
    else:
        with pytest.raises(ValueError, match='gap' if gap > 0 else 'penetration'):
            seat.validate(data)


@pytest.mark.parametrize('change', ['no_over', 'no_band', 'nan', 'missing_region', 'invalid_weights', 'short', 'time'])
def test_incomplete_evidence_is_refused(change):
    data = report()
    row = data['samples'][100]
    if change == 'no_over':
        row['regions'][0]['overSurfaceVertices'] = 0      # seat not over the cushion at all
    elif change == 'no_band':
        row['regions'][1]['bandVertices'] = 0
    elif change == 'nan':
        row['regions'][2]['minGapCm'] = float('nan')
    elif change == 'missing_region':
        row['regions'].pop()
    elif change == 'invalid_weights':
        row['invalidInfluences'] = 2
    elif change == 'short':
        data['samples'] = data['samples'][::2]            # 30 Hz is not accepted
    else:
        row['time'] += .01
    with pytest.raises(ValueError):
        seat.validate(data)


def test_cushion_triangles_come_from_the_actual_chair_audit_selection():
    chair = {'errors': [], 'chair': {'sections': [{
        'vertices_world_cm': [[180, -210, 50.5], [220, -210, 50.5], [220, -170, 50.5], [180, -170, 50.5], [0, 0, 90]],
        'triangles': [0, 1, 2, 0, 2, 3, 2, 3, 4],
        'cushion_surface': {'triangle_indices': [[0, 1, 2], [0, 2, 3]]}}]}}
    assert seat.cushion_triangles(chair) == [[180, -210, 50.5], [220, -210, 50.5], [220, -170, 50.5],
                                             [180, -210, 50.5], [220, -170, 50.5], [180, -170, 50.5]]
    with pytest.raises(ValueError):
        seat.cushion_triangles(dict(chair, errors=['ambiguous chair']))
    broken = copy.deepcopy(chair)
    broken['chair']['sections'][0]['cushion_surface']['triangle_indices'] = []
    with pytest.raises(ValueError):
        seat.cushion_triangles(broken)


def test_surface_height_geometry_compiled_from_actual_analyzer():
    compiler = shutil.which('clang++') or shutil.which('g++')
    if not compiler:
        pytest.skip('C++ compiler unavailable')
    function = re.search(r'static bool Sub01SurfaceHeightAt\(.*?\n}\n', native.CPP, re.S).group(0)
    source = '#include <cmath>\nusing int32=int;struct FVector{double X,Y,Z;};\n' + function + r'''
#define CHECK(c,n) if(!(c))return n;
int main(){
 const FVector Flat[]={{180,-210,50.5},{220,-210,50.5},{220,-170,50.5},{180,-210,50.5},{220,-170,50.5},{180,-170,50.5}};
 double Z=0;
 CHECK(Sub01SurfaceHeightAt(Flat,6,200,-190,Z)&&std::fabs(Z-50.5)<1e-9,1)     // inside
 CHECK(Sub01SurfaceHeightAt(Flat,6,180,-210,Z),2)                              // on a corner
 CHECK(!Sub01SurfaceHeightAt(Flat,6,230,-190,Z)&&!Sub01SurfaceHeightAt(Flat,6,200,-160,Z),3)  // outside
 const FVector Slope[]={{0,0,40},{10,0,50},{0,10,40}};                       // rises 1 cm per cm in X
 CHECK(Sub01SurfaceHeightAt(Slope,3,2.5,2.5,Z)&&std::fabs(Z-42.5)<1e-9,4)   // interpolated, not a max/min
 const FVector Stack[]={{0,0,40},{10,0,40},{0,10,40},{0,0,47},{10,0,47},{0,10,47}};
 CHECK(Sub01SurfaceHeightAt(Stack,6,1,1,Z)&&std::fabs(Z-47)<1e-9,5)         // highest surface under the point
 const FVector Degenerate[]={{0,0,0},{5,5,0},{10,10,0}};
 CHECK(!Sub01SurfaceHeightAt(Degenerate,3,5,5,Z),6)
 CHECK(!Sub01SurfaceHeightAt(Flat,2,200,-190,Z),7)                           // incomplete triangle ignored
 return 0;}
'''
    with tempfile.TemporaryDirectory() as tmp:
        cpp, exe = Path(tmp) / 'surface.cpp', Path(tmp) / 'surface'
        cpp.write_text(source)
        built = subprocess.run([compiler, '-std=c++17', '-Wall', '-Werror', str(cpp), '-o', str(exe)], capture_output=True, text=True)
        assert built.returncode == 0, built.stderr[-2000:]
        assert subprocess.run([str(exe)]).returncode == 0


def test_analyzer_contract_matches_the_validator():
    cpp = native.CPP.split('FString USub01HomeHandsInstance::AnalyzeCapturedSeatSkin(', 1)[1]
    assert 'AnalyzeCapturedSeatSkin' in native.HEADER and 'UFUNCTION(BlueprintCallable' in native.HEADER
    assert cpp.index('#if WITH_EDITOR') < cpp.index('GetImportedModel()')      # editor-only diagnostic
    # Region by skin weight (>=30%), never by the body's lowest point.
    for bone in ('Hips', 'LeftUpLeg', 'RightUpLeg', 'LeftFoot', 'LeftToeBase', 'RightFoot', 'RightToeBase'):
        assert f'Name.EndsWith(TEXT("{bone}"))' in cpp
    assert 'SeatW>=.30*Sum' in cpp
    # Same bands as the validator, counted for both signs.
    assert 'if(Gap>=-2.5&&Gap<=.5)++Seat.Band;' in cpp and seat.SEAT_BAND_CM == (-2.5, .5)
    assert 'if(Gap>=0&&Gap<=1)++S.Band;' in cpp and seat.SOLE_BAND_CM == (0., 1.)
    for field in ('selectedVertices', 'overSurfaceVertices', 'bandVertices', 'minGapCm', 'maxGapCm'):
        assert f'\\"{field}\\"' in cpp
    # No pose, actor or collision mutation in the analyzer or the server audit.
    audit = (ROOT / 'tools/unreal_audit_seat_contact.py').read_text()
    for forbidden in ('SetWorldLocation', 'SetActorLocation', 'set_actor_location', 'teleport', 'set_editor_property'):
        assert forbidden not in cpp and forbidden not in audit
    assert 'frame in range(180, 481)' in audit and 'frame / 60' in audit
    # Staged with the hands runtime like the typing analyzer.
    hands = (ROOT / 'tools/unreal_home_hands_runtime.py').read_text()
    assert 'HEADER.replace(\' protected:\', SKIN_CONTACT_HEADER' in hands and 'CPP += SKIN_CONTACT_CPP' in hands
