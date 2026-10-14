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
    'draped_throw': ((.30, 2.2), (.20, 2.0), (.02, .40)),
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


def test_draped_throw_dims_match_their_params(spec):
    for item in spec['items']:
        if item['kind'] != 'draped_throw':
            continue
        p = item['params']
        total = p['thickness'] * (1 + p.get('fold_layers', 0))
        assert item['dims_m'][1] == pytest.approx(p['top_width'] + 2 * p['radius'] + 2 * total, abs=1e-6)
        assert item['dims_m'][2] == pytest.approx(max(p['drop'], p['radius']) + total, abs=1e-6)
        assert item['origin_height_m'] == pytest.approx(max(p['drop'], p['radius']), abs=1e-6)


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
    assert report['mode'].startswith('dry-run') and report['placed'] and report['rejected']


# ---------------------------------------------------------------------------
# Evaluated-home placement, exercised with duck-typed fakes of bpy objects.
# Blender is NOT installed in this environment: these fakes mimic only the API
# the module calls (evaluated_get/to_mesh/matrix_world/material_slots/...).
# They prove the logic, not Blender's behaviour on the real house.blend.
# ---------------------------------------------------------------------------
class FakeMatrix:
    def __init__(self, t=(0.0, 0.0, 0.0)):
        self.t = tuple(t)

    def __matmul__(self, co):
        return tuple(co[i] + self.t[i] for i in range(3))

    def __iter__(self):
        return iter([(1, 0, 0, self.t[0]), (0, 1, 0, self.t[1]), (0, 0, 1, self.t[2]), (0, 0, 0, 1)])


class _V:
    def __init__(self, co):
        self.co = tuple(co)


class _T:
    def __init__(self, vertices):
        self.vertices = tuple(vertices)
        self.material_index = 0


class FakeMesh:
    def __init__(self, verts, tris):
        self.vertices = [_V(v) for v in verts]
        self.loop_triangles = [_T(t) for t in tris]

    def calc_loop_triangles(self):
        pass


class FakeEvaluated:
    def __init__(self, obj):
        self.obj = obj
        self.matrix_world = obj.matrix_world

    def to_mesh(self):
        grow = sum(m['grow'] for m in self.obj.modifiers)   # e.g. a Solidify/Displace result
        return FakeMesh(*blender_box(self.obj.box, grow))

    def to_mesh_clear(self):
        self.obj.cleared += 1


class FakeSocket:
    def __init__(self, name, value):
        self.name, self.default_value = name, value


class FakeNode:
    def __init__(self, name, inputs):
        self.name, self.bl_idname, self.inputs, self.image = name, 'ShaderNodeBsdfPrincipled', inputs, None


class FakeMaterial:
    def __init__(self, name, roughness=.8):
        self.name, self.use_nodes, self.diffuse_color = name, True, (1, 1, 1, 1)
        self.node_tree = type('Tree', (), {})()
        self.node_tree.nodes = [FakeNode('BSDF', [FakeSocket('Roughness', roughness)])]
        self.node_tree.links = []


class FakeCollection:
    def __init__(self, name):
        self.name = name


class FakeObject(dict):
    """box: runtime (lo, hi). Geometry is generated in Blender axes, as Blender stores it."""

    def __init__(self, name, box, bake=None, collections=('Scene',), material=None):
        super().__init__()
        if bake:
            self['bakeId'] = bake
        self.name, self.type, self.parent, self.box = name, 'MESH', None, box
        self.matrix_world = FakeMatrix()
        self.data = type('Data', (), {'name': name + '_mesh'})()
        self.material_slots = [type('Slot', (), {'material': material or FakeMaterial(name + '_mat')})()]
        self.users_collection = [FakeCollection(c) for c in collections]
        self.modifiers = []
        self.cleared = 0

    def evaluated_get(self, depsgraph):
        assert depsgraph == 'DEPSGRAPH'
        return FakeEvaluated(self)


def blender_box(box, grow=0.0):
    (x0, y0, z0), (x1, y1, z1) = box
    lo = (x0 - grow, -z1 - grow, y0 - grow)       # runtime -> Blender (x, -z, y)
    hi = (x1 + grow, -z0 + grow, y1 + grow)
    verts = [(x, y, z) for z in (lo[2], hi[2]) for y in (lo[1], hi[1]) for x in (lo[0], hi[0])]
    quads = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    tris = [t for a, b, c, d in quads for t in ((a, b, c), (a, c, d))]
    return verts, tris


def geometry_of(*objects):
    return rd.fingerprint_and_geometry(objects, 'DEPSGRAPH')


def table_item(**extra):
    return {'id': 'book', 'room': 'lounge', 'kind': 'book_stack', 'dims_m': [.30, .24, .05],
            'position_runtime_m': [-3.2, .455, -.2], 'yaw_deg': 0, 'tilt_deg': 0, 'rigid': True,
            'support': 'coffee_table_top', 'source': 't', 'placement_rule': 't', **extra}


TABLE = ((-3.55, 0.0, -.6), (-2.85, .455, .8))


def test_resting_item_without_support_raises():
    _, geometry = geometry_of(FakeObject('table', TABLE, 'house-cc0-coffee-table-top'))
    floating = table_item(position_runtime_m=[-1.0, .455, 2.5])        # nothing underneath
    with pytest.raises(rd.UnsupportedPlacementError, match='no supporting surface'):
        rd.resolve_support(floating, geometry)
    _, empty = geometry_of()
    with pytest.raises(rd.UnsupportedPlacementError):
        rd.resolve_support(table_item(support='kitchen_counter'), empty)
    with pytest.raises(rd.UnsupportedPlacementError, match='anchor coffee_table not found'):
        rd.resolve_support(table_item(), empty)


def test_support_must_be_the_declared_anchor_not_any_surface():
    # A real surface exists under the item, but it belongs to some other object.
    _, geometry = geometry_of(FakeObject('shelf', TABLE, 'house-office-shelves-Oak_shelves'))
    with pytest.raises(rd.UnsupportedPlacementError):
        rd.resolve_support(table_item(), geometry)


def test_partial_support_is_refused_for_rigid_items():
    half = ((-3.55, 0.0, -.6), (-3.2, .455, .8))       # table ends under the item's centre line
    _, geometry = geometry_of(FakeObject('table', half, 'house-cc0-coffee-table-top'))
    with pytest.raises(rd.UnsupportedPlacementError):
        rd.resolve_support(table_item(), geometry)


def test_placement_uses_evaluated_mesh_not_the_estimate():
    table = FakeObject('table', TABLE, 'house-cc0-coffee-table-top')
    table.modifiers.append({'grow': .015})          # modifier raises the real top to 0.470
    _, geometry = geometry_of(table)
    placed = rd.resolve_support(table_item(), geometry)
    assert placed['position_runtime_m'][1] == pytest.approx(.470)
    assert placed['support_evidence']['surfaces'] == ['house-cc0-coffee-table-top']
    assert table.cleared >= 1                       # evaluated meshes are released
    # The same modifier makes a neighbouring mesh reach into the item: refused,
    # although the unmodified (estimated) box would have been clear.
    vase = FakeObject('vase', ((-3.04, .455, -.2), (-2.96, .7, -.12)), 'house-vase')
    clear_item = dict(placed)
    _, base = geometry_of(vase)
    assert base.collisions(clear_item) == {}
    vase.modifiers.append({'grow': .02})
    _, grown = geometry_of(vase)
    assert 'house-vase' in grown.collisions(clear_item)


def test_wall_mount_requires_a_verified_wall():
    frame = {'id': 'print', 'room': 'lounge', 'kind': 'book_stack', 'dims_m': [.5, .02, .7],
             'position_runtime_m': [-3.70, 1.5, 1.5], 'mount': 'wall', 'source': 't', 'placement_rule': 't',
             'attach': {'surface': 'west wall', 'direction_runtime': [-1, 0, 0], 'max_gap_m': .02}}
    _, nothing = geometry_of()
    with pytest.raises(rd.UnsupportedPlacementError, match='found no west wall'):
        rd.resolve_support(frame, nothing)
    _, far = geometry_of(FakeObject('wall', ((-3.9, 0, -4), (-3.8, 3, 4)), 'house-static-wall'))
    with pytest.raises(rd.UnsupportedPlacementError):
        rd.resolve_support(frame, far)                   # wall is 0.10 m away, gap allows 0.02
    _, near = geometry_of(FakeObject('wall', ((-3.8, 0, -4), (-3.71, 3, 4)), 'house-static-wall'))
    assert rd.resolve_support(frame, near)['support_evidence']['surface'] == 'house-static-wall'
    undeclared = {k: v for k, v in frame.items() if k != 'attach'}
    with pytest.raises(rd.UnsupportedPlacementError, match='declares no attach'):
        rd.resolve_support(undeclared, near)


def test_fingerprint_detects_any_change_to_existing_objects():
    objs = [FakeObject('desk', ((.8, 0, -3.5), (3.2, .84, -2.7)), 'house-office-desk-Oak_desk'),
            FakeObject('sofa', ((-2.26, 0, -1.04), (-1.34, .92, 1.24)), 'house-sofa-Haven_linen')]
    before, _ = geometry_of(*objs)
    assert rd.fingerprint_changes(before, geometry_of(*objs)[0]) == {'changed_or_removed': [], 'unexpected_new': []}
    objs[0].modifiers.append({'grow': 1e-6})                    # evaluated geometry moved by 1 micron
    assert rd.fingerprint_changes(before, geometry_of(*objs)[0])['changed_or_removed'] == ['desk']
    objs[0].modifiers.clear()
    objs[1].material_slots[0].material.node_tree.nodes[0].inputs[0].default_value = .81
    assert rd.fingerprint_changes(before, geometry_of(*objs)[0])['changed_or_removed'] == ['sofa']
    objs[1].material_slots[0].material.node_tree.nodes[0].inputs[0].default_value = .8
    objs[1].matrix_world = FakeMatrix((0, 0, .001))
    assert rd.fingerprint_changes(before, geometry_of(*objs)[0])['changed_or_removed'] == ['sofa']
    objs[1].matrix_world = FakeMatrix()
    assert rd.fingerprint_changes(before, geometry_of(objs[0])[0])['changed_or_removed'] == ['sofa']
    ours = FakeObject('SUB01_RefDress_x', TABLE, collections=(rd.COLLECTION,))
    ours[rd.TAG] = True
    stray = FakeObject('stray', TABLE)
    diff = rd.fingerprint_changes(before, geometry_of(*objs, ours, stray)[0])
    assert diff == {'changed_or_removed': [], 'unexpected_new': ['stray']}


def test_additive_export_contains_only_new_objects():
    existing = FakeObject('house-static-2', TABLE)
    ours = FakeObject('SUB01_RefDress_lounge_a', TABLE, collections=(rd.COLLECTION,))
    ours[rd.TAG] = True
    tagged_elsewhere = FakeObject('SUB01_RefDress_loose', TABLE, collections=('Scene',))
    tagged_elsewhere[rd.TAG] = True
    in_collection_untagged = FakeObject('intruder', TABLE, collections=(rd.COLLECTION,))
    picked = rd.additive_export_objects([existing, ours, tagged_elsewhere, in_collection_untagged])
    assert [o.name for o in picked] == ['SUB01_RefDress_lounge_a']


def test_clearances_are_derived_from_evaluated_anchor_bounds(spec):
    desk = FakeObject('desk', ((.8, 0, -3.5), (3.2, .84, -2.7)), 'house-office-desk-Oak_desk')
    sofa = FakeObject('sofa', ((-2.26, 0, -1.04), (-1.34, .92, 1.24)), 'house-sofa-Haven_linen')
    bed = FakeObject('bed', ((-3.25, 3.0, -3.46), (-1.55, 3.68, -1.24)), 'house-cc0-queen-bed-duvet')
    counter = FakeObject('counter', ((-3.78, .87, -3.88), (-.62, .9225, -3.18)), 'house-static-6')
    _, geometry = geometry_of(desk, sofa, bed, counter)
    zones, missing = rd.derived_zones(geometry)
    names = {z['name']: z['box'] for z in zones}
    assert names['clear:desk_chair_approach'][0][2] == pytest.approx(-2.7)    # starts at desk front
    assert names['clear:bed_access_side'][0][0] == pytest.approx(-1.55)       # toward the 'bed' node
    assert names['clear:kitchen_work_zone'][0][1] == pytest.approx(.9225 - .02)
    assert set(missing) == {'coffee_table', 'upper_cabinet', 'lower_cabinet'}
    context = rd.evaluated_context(geometry)
    by_id = {i['id']: i for i in spec['items']}
    accepted, rejected = rd.place_on_evaluated_home(spec, geometry, context=context)
    reasons = {r['id']: r['reasons'] for r in rejected}
    # Rooms whose clearance anchors are missing are refused, never guessed.
    assert reasons['coffee_table_book_stack'] == ['clearance_unverified:coffee_table']
    assert reasons['kitchen_canister_large'] == ['clearance_unverified:lower_cabinet',
                                                 'clearance_unverified:upper_cabinet']
    # A chair-approach intruder is refused by the zone computed from the real desk.
    intruder = dict(by_id['coffee_table_book_stack'], position_runtime_m=[2.0, 0.0, -2.2])
    assert 'clear:desk_chair_approach' in rd.validate_item(intruder, context)


def test_legacy_duplicate_in_the_real_home_is_refused(spec):
    legacy = FakeObject('foot', ((-3.28, 3.42, -1.82), (-1.52, 3.63, -1.27)), 'house-bedding-Foot_throw')
    bed = FakeObject('bed', ((-3.25, 3.0, -3.46), (-1.55, 3.68, -1.24)), 'house-cc0-queen-bed-duvet')
    _, geometry = geometry_of(legacy, bed)
    blanket = [i for i in spec['items'] if i['id'] == 'bed_foot_blanket_folded']
    _, rejected = rd.place_on_evaluated_home({'items': blanket}, geometry)
    assert rejected[0]['reasons'] == ['duplicate:existing:house-bedding-Foot_throw']


def test_draped_throw_collides_only_through_its_slabs():
    throw = {'id': 'throw', 'room': 'lounge', 'kind': 'draped_throw', 'dims_m': [.55, .328, .224],
             'origin_height_m': .2, 'position_runtime_m': [-1.9, .71, 1.12], 'yaw_deg': 0, 'tilt_deg': 0,
             'params': {'top_width': .24, 'radius': .02, 'drop': .2, 'thickness': .012, 'fold_layers': 1},
             'contact_allowance_m': .005}
    _, arm = geometry_of(FakeObject('arm', ((-2.26, .2, 1.0), (-1.34, .71, 1.237)), 'house-sofa-arm'))
    assert arm.collisions(throw) == {}                     # the arm sits inside the drape
    _, post = geometry_of(FakeObject('post', ((-1.95, .3, 1.25), (-1.85, .9, 1.30)), 'house-post'))
    assert 'house-post' in post.collisions(throw)          # something through the outer drop


def test_tri_box_overlap_basics():
    tri = ((-1, 0, -1), (1, 0, -1), (0, 0, 1))
    assert rd.tri_box_overlap((0, 0, 0), (.1, .1, .1), tri)
    assert not rd.tri_box_overlap((0, .5, 0), (.1, .1, .1), tri)
    assert not rd.tri_box_overlap((5, 0, 0), (.1, .1, .1), tri)
