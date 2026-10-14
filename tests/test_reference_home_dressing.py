"""Pure-Python checks for tools/reference_home_dressing.py (no Blender, no rendering)."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import reference_home_dressing as rd  # noqa: E402


@pytest.fixture(scope='module')
def context():
    return rd.build_context()


@pytest.fixture(scope='module')
def spec():
    return rd.load_spec()


def probe(position, dims=(.30, .30, .30), support='sofa_seat', **extra):
    return {'id': 'probe', 'room': 'test', 'kind': 'throw_pillow', 'dims_m': list(dims),
            'position_runtime_m': list(position), 'yaw_deg': 0, 'tilt_deg': 0,
            'support': support, 'source': 'test', 'placement_rule': 'test', **extra}


def test_module_imports_without_bpy():
    code = ('import sys; sys.path.insert(0, %r); import reference_home_dressing as m; '
            'assert m.bpy is None and "bpy" not in sys.modules; print(m.COLLECTION)') % str(ROOT / 'tools')
    out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == 'SUB01_ReferenceDressing'


def test_graph_parsed_from_home_world():
    nodes, edges = rd.load_graph()
    assert nodes['desk'] == (2.0, 1.65, -0.75) and nodes['stair_top'][1] == 4.65
    assert ('desk', 'aisle') in edges and len(edges) >= 20


def test_ue_monitor_conversion_matches_documented_pivot():
    assert tuple(round(v, 4) for v in rd.ue_cm_to_runtime((200, -327.6, 116))) == (2.0, 1.16, -3.276)
    monitor = next(s for s in rd.default_screens() if s['name'] == 'pc_monitor')
    assert (monitor['u_half'], monitor['v_half']) == (.34, .20)


def test_item_across_walk_edge_is_refused(context):
    # Midpoint of the desk-aisle edge on the ground floor; a floor item straddling it.
    item = probe((1.65, 0.0, -0.75), support='coffee_table_top')
    reasons = rd.validate_item(item, context)
    assert 'walk_graph:edge:desk-aisle' in reasons


def test_walk_capsule_respects_floor_levels(context):
    # Same x/z as the ground-floor 'back' node but up on the loft floor height:
    # the ground capsule must not fire; only floor-matching capsules may.
    box = rd.item_aabb(probe((1.3, 3.0, -2.2)))
    back = next(c for c in context['capsules'] if c['name'] == 'node:back')
    assert not rd.capsule_hits(box, back)
    assert rd.capsule_hits(rd.item_aabb(probe((1.3, 0.0, -2.2))), back)


def test_item_in_front_of_tv_is_refused(context):
    # A tall item on the coffee table rises into the TV sightlines from the sofa.
    item = probe((-3.2, .455, 0.1), dims=(.15, .15, 1.0), support='coffee_table_top')
    reasons = rd.validate_item(item, context)
    assert any(r.startswith(('screen_sightline:tv', 'screen_prism:tv')) for r in reasons)


def test_items_over_monitor_and_phone_are_refused(context):
    on_desk = probe((2.0, .85, -3.05), dims=(.2, .1, .4), support='coffee_table_top')
    assert any(r.endswith('pc_monitor') for r in rd.validate_item(on_desk, context))
    over_phone = probe((2.7, .87, -2.92), dims=(.05, .05, .05), support='coffee_table_top')
    reasons = rd.validate_item(over_phone, context)
    assert 'screen_prism:phone_display' in reasons


def test_clear_zones_and_doors_refuse(context):
    keyboard = probe((2.0, .85, -2.94), dims=(.1, .1, .1), support='coffee_table_top')
    assert 'clear:desk_chair_keyboard_mouse' in rd.validate_item(keyboard, context)
    prep = probe((-1.9, .9225, -3.5), dims=(.2, .2, .1), support='kitchen_counter')
    assert 'clear:kitchen_prep_worktop' in rd.validate_item(prep, context)
    bath = probe((-0.85, 3.6, 2.2), dims=(.1, .1, .2), support='bed_top')
    assert 'door:bathroom_slide' in rd.validate_item(bath, context)


def test_valid_placement_is_accepted(context):
    item = probe((-3.22, .455, -0.22), dims=(.25, .2, .05), support='coffee_table_top')
    assert rd.validate_item(item, context) == []


def test_floating_or_overhanging_item_is_refused(context):
    floating = probe((-3.22, .70, -0.22), dims=(.25, .2, .05), support='coffee_table_top')
    assert any(r.startswith('support:not_resting') for r in rd.validate_item(floating, context))
    edge = probe((-2.90, .455, -0.22), dims=(.40, .2, .05), support='coffee_table_top')
    assert 'support:footprint_overhangs_surface' in rd.validate_item(edge, context)


def test_full_spec_places_every_item_and_skips_duplicates(spec, context):
    report = rd.plan_dressing(spec, context)
    placed = {p['id'] for p in report['placed']}
    assert placed == {i['id'] for i in spec['items']}
    skips = [r for r in report['rejected'] if r['kind'] == 'skip']
    assert {'lounge_rug', 'curtains', 'bed_duvet'} <= {r['id'] for r in skips}
    assert all(r['reasons'][0].startswith('duplicate:existing:') for r in skips)
    assert not [r for r in report['rejected'] if r['kind'] != 'skip']


def test_moved_spec_item_is_refused_with_reason(spec, context):
    bad = copy.deepcopy(spec)
    throw = next(i for i in bad['items'] if i['id'] == 'sofa_arm_throw_folded')
    throw['position_runtime_m'][0] = -1.95   # 5 cm toward the sofa approach path
    report = rd.plan_dressing(bad, context)
    rejected = {r['id']: r['reasons'] for r in report['rejected']}
    assert 'walk_graph:edge:sofa_front_approach-sofa' in rejected['sofa_arm_throw_folded']


PLAUSIBLE = {  # kind -> (min, max) metres for each of width, depth, height
    'throw_pillow': ((.28, .70), (.08, .25), (.25, .70)),
    'draped_throw': ((.30, 2.2), (.20, 2.0), (.05, .40)),
    'book_stack': ((.12, .45), (.10, .35), (.01, .25)),
    'vase_with_stems': ((.06, .40), (.06, .40), (.10, .90)),
    'canister': ((.06, .20), (.06, .20), (.06, .35)),
}


def test_spec_dimensions_are_calibrated(spec):
    for item in spec['items']:
        ranges = PLAUSIBLE[item['kind']]
        for value, (low, high) in zip(item['dims_m'], ranges):
            assert low <= value <= high, (item['id'], item['dims_m'])
        assert item['source'].strip() and item['placement_rule'].strip()
        assert item['material'] in spec['materials']
        assert item['support'] in rd.SUPPORTS
    for finish in spec['materials'].values():
        if 'texture' in finish:
            assert (ROOT / 'web/house/assets' / finish['texture'] / 'diff.jpg').is_file()
    assert 'NOT viewed' in spec['reference_access']


def test_names_are_deterministic_and_unique(spec, context):
    first = rd.plan_dressing(spec, context)
    shuffled = copy.deepcopy(spec)
    shuffled['items'].reverse()
    second = rd.plan_dressing(shuffled, rd.build_context())
    assert json.dumps(first['placed']) == json.dumps(second['placed'])
    names = [p['name'] for p in first['placed']]
    assert len(names) == len(set(names)) and all(n.startswith(rd.NAME_PREFIX) for n in names)
    assert rd.object_name({'room': 'lounge', 'id': 'x'}) == 'SUB01_RefDress_lounge_x'


def test_mesh_builders_are_well_formed():
    v, f, uv, seam = rd.pillow_mesh(.45, .15, .45)
    assert rd.mesh_is_closed(f) and len(uv) == len(f) and len(seam) == 64
    zs = [p[2] for p in v]
    assert min(zs) >= -1e-9 and max(zs) <= .45 + 1e-9
    v, f, uv = rd.lathe_mesh(rd.VASE_PROFILE)
    assert rd.mesh_is_closed(f)
    v, f, uv = rd.lathe_mesh(rd.canister_profile(.05, .12))
    assert rd.mesh_is_closed(f)
    v, f, uv = rd.draped_strip_mesh(.5, .24, .2, .02)
    tops = [rd._face_normal([v[i] for i in face]) for face in f
            if all(abs(v[i][2]) < 1e-9 and abs(v[i][1]) < .1 for i in face)]
    assert tops and all(n[2] > .99 for n in tops)
    assert min(p[2] for p in v) == pytest.approx(-.2)


def test_dry_run_cli_reports_json():
    out = subprocess.run([sys.executable, str(ROOT / 'tools/reference_home_dressing.py'), '--dry-run'],
                         capture_output=True, text=True, check=True)
    line = next(l for l in out.stdout.splitlines() if l.startswith('SUB01_REFERENCE_DRESSING '))
    report = json.loads(line.split(' ', 1)[1])
    assert report['mode'] == 'dry-run' and report['placed'] and report['rejected']
