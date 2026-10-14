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


def region(name, low, median, over=200, band=150):
    return {'region': name, 'selectedVertices': 900, 'facingVertices': 300, 'overSurfaceVertices': over,
            'bandVertices': band, 'minGapCm': low, 'p10GapCm': low + .1, 'p50GapCm': median,
            'p90GapCm': median + .4, 'maxGapCm': median + 1}


def report(**override):
    regions = {'buttocks': (-1.2, -.6), 'left_posterior_thigh': (-.9, -.2), 'right_posterior_thigh': (-.8, -.1),
               'left_sole': (.1, .3), 'right_sole': (.1, .4)}
    regions.update(override)
    row = {'invalidInfluences': 0, 'floorCm': 0.0,
           'regions': [region(name, *values) for name, values in regions.items()]}
    return {'samples': [dict(copy.deepcopy(row), time=3 + i / 60) for i in range(301)]}


def test_in_band_patches_are_reported_as_probe_only():
    result = seat.validate(report())
    assert result['native_seat_verified'] is False and 'probe only' in result['acceptance']
    assert result['worst']['buttocks']['min_gap_cm'] == -1.2
    assert set(result['worst']) == set(seat.REGIONS)


def test_one_buttock_touching_while_the_thighs_float_is_refused():
    # docs/qa/contact.md rule 4: a lowest-point measure would accept this pose.
    data = report(left_posterior_thigh=(1.5, 2.2), right_posterior_thigh=(1.4, 2.0))
    with pytest.raises(ValueError, match='posterior_thigh: no support patch'):
        seat.validate(data)


@pytest.mark.parametrize('change,match', [
    (dict(buttocks=(-2.6, -.5)), 'penetration'),
    (dict(left_sole=(-.2, .2)), 'penetration'),
    (dict(right_sole=(1.2, 1.4)), 'no support patch'),
])
def test_band_edges_of_each_patch(change, match):
    with pytest.raises(ValueError, match=match):
        seat.validate(report(**change))


def test_genuine_toe_plant_with_raised_heel_is_a_support_patch():
    # Measured actual typing soles: lowest ~0 cm, median ~10.4 / 7.5 cm (toes planted, heel raised).
    data = report(left_sole=(.02, 10.4), right_sole=(.04, 7.5))
    for row in data['samples']:
        for r in row['regions']:
            if r['region'].endswith('sole'):
                r['bandVertices'] = 40                       # toe-edge support patch only
    assert seat.validate(data)['worst']['left_sole']['max_median_gap_cm'] == 10.4
    for row in data['samples']:
        for r in row['regions']:
            if r['region'] == 'right_sole':
                r['bandVertices'] = seat.MIN_SUPPORT_VERTICES - 1   # a point, not a patch
    with pytest.raises(ValueError, match='right_sole: no support patch'):
        seat.validate(data)
    # A curved buttock resting locally (median well above the cushion) is a support patch too...
    assert seat.validate(report(buttocks=(-1.0, 3.0)))['worst']['buttocks']['max_median_gap_cm'] == 3.0
    # ...but not one hovering above it.
    with pytest.raises(ValueError, match='buttocks: no support patch'):
        seat.validate(report(buttocks=(.7, 3.0)))


def test_coverage_and_patch_size_are_required_in_every_sample():
    data = report()
    data['samples'][150]['regions'][0]['bandVertices'] = 5             # a few points, not a support patch
    with pytest.raises(ValueError, match='buttocks: no support patch'):
        seat.validate(data)
    data = report()
    data['samples'][9]['regions'][2]['overSurfaceVertices'] = 3        # thigh barely over the cushion
    with pytest.raises(ValueError, match='downward-facing'):
        seat.validate(data)
    data = report()
    data['samples'][9]['regions'].pop()
    with pytest.raises(ValueError):
        seat.validate(data)


@pytest.mark.parametrize('override,delta,diagnosis', [
    ({}, 0.0, 'within bands'),
    # Whole body hovering (lowest seat skin 1.0 cm, soles 1.2 cm): lowering 0.5 cm makes every
    # local support patch touch (diagnostic only; the fitter decides how, never a hidden lift).
    (dict(buttocks=(1.0, 1.5), left_posterior_thigh=(1.0, 1.5), right_posterior_thigh=(1.0, 1.5),
          left_sole=(1.2, 1.5), right_sole=(1.2, 1.5)), -0.5, 'translate the whole seated body by -0.500 cm'),
    # Seated correctly but feet hanging 3 cm: no translation can fix both.
    (dict(left_sole=(3.0, 3.2), right_sole=(3.0, 3.3)), None, 'knee/ankle pose'),
    # Buttocks deep while thighs float: pelvis/thigh pose, not a translation.
    (dict(buttocks=(-2.0, -1.5), left_posterior_thigh=(1.8, 2.0)), None, 'pelvis/thigh pose'),
    (dict(right_posterior_thigh=(.0, .2)), 0.0, 'within bands'),
])
def test_vertical_anchor_proposal(override, delta, diagnosis):
    proposal = seat.propose_vertical_anchor(report(**override))
    assert proposal['native_seat_verified'] is False
    assert diagnosis in proposal['diagnosis']
    if delta is None:
        assert proposal['recommended_delta_cm'] is None
    else:
        assert proposal['recommended_delta_cm'] == pytest.approx(delta)
        if delta:
            shifted = report(**{k: (v[0] + delta, v[1] + delta) for k, v in {**{
                'buttocks': (1.0, 1.5), 'left_posterior_thigh': (1.0, 1.5), 'right_posterior_thigh': (1.0, 1.5),
                'left_sole': (1.2, 1.5), 'right_sole': (1.2, 1.5)}, **override}.items()})
            seat.validate(shifted)                                       # the proposed translation is in band


def test_patch_off_its_surface_needs_horizontal_correction_first():
    data = report()
    for row in data['samples']:
        row['regions'][1]['overSurfaceVertices'] = 0
    proposal = seat.propose_vertical_anchor(data)
    assert proposal['recommended_delta_cm'] is None and 'left_posterior_thigh' in proposal['diagnosis']


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
    assert cpp.index('#if WITH_EDITOR') < cpp.index('GetImportedModel()')      # editor-only probe
    for name in seat.REGIONS:
        assert f'TEXT("{name}")' in cpp
    # Separate patches by dominant skin weight (>=30%), downward-facing skin only (posed normal).
    for bone in ('Hips', 'LeftUpLeg', 'RightUpLeg', 'LeftFoot', 'LeftToeBase', 'RightFoot', 'RightToeBase'):
        assert f'Name.EndsWith(TEXT("{bone}"))' in cpp
    assert 'double Best=.30*Sum;' in cpp and 'if(N.Z>-.5)continue;' in cpp
    assert 'TransformVectorNoScale(FVector(Inv[B].TransformVector(BindNormal)))' in cpp
    # Same bands as the validator; quantiles reported, not a single lowest vertex.
    assert 'if(Gap>=-2.5&&Gap<=.5)++Region.Band;' in cpp and seat.SEAT_BAND_CM == (-2.5, .5)
    assert 'if(Gap>=0&&Gap<=1)++Region.Band;' in cpp and seat.SOLE_BAND_CM == (0., 1.)
    for field in ('facingVertices', 'overSurfaceVertices', 'bandVertices', 'minGapCm', 'p50GapCm', 'p90GapCm'):
        assert f'\\"{field}\\"' in cpp
    assert 'NativeSeatVerified=true' not in cpp
    audit = (ROOT / 'tools/unreal_audit_seat_contact.py').read_text()
    for forbidden in ('SetWorldLocation', 'SetActorLocation', 'set_actor_location', 'teleport', 'set_editor_property', 'NativeSeatVerified='):
        assert forbidden not in cpp and forbidden not in audit
    assert 'propose_vertical_anchor(result)' in audit and 'SUB01_SEAT_CONTACT_PROBE_' in audit
    assert 'frame in range(180, 481)' in audit and 'frame / 60' in audit
