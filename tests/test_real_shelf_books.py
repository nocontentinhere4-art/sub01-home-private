"""Pure-Python checks for the real shelf books builder and its Unreal import (fake bpy / unreal)."""
import copy
import hashlib
import json
import math
import struct
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_real_shelf_books as b  # noqa: E402
import unreal_import_real_shelf_books as ui  # noqa: E402


# ---------------------------------------------------------------- synthetic home pieces
def box_tris(lo, hi):
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    quads = [((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)),
             ((x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0)),
             ((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)),
             ((x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0)),
             ((x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)),
             ((x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1))]
    return [t for q in quads for t in ((q[0], q[1], q[2]), (q[0], q[2], q[3]))]


def shelf_tris():
    """tools/build_home_office_shelves.py geometry in Blender metres: boards 2.35 x .34 x .022 with
    tops .2675 + i*.45 at runtime (2.125, 0, -3.72), back cleats at x +-1.045."""
    tris = []
    for i in range(6):
        top = .2675 + i * .45
        tris += box_tris((2.125 - 1.175, 3.55, top - .022), (2.125 + 1.175, 3.89, top))
    for dx in (-1.045, 0, 1.045):
        x = 2.125 + dx
        tris += box_tris((x - .015, 3.858, .125), (x + .015, 3.884, 2.515))
    return tris


def cube_book_records():
    """The 30 home.js cube books as the native base carries them (Blender = (x, -z, y))."""
    recs, n = [], 500
    for bottom in b.ORIGINAL_BOTTOMS:
        for i in range(15):
            w, h = .035 + (i % 5) * .004, .16 + (i % 7) * .017
            cx = 1.2 + i * .054
            lo, hi = (cx - w / 2, 3.71 - .07, bottom), (cx + w / 2, 3.71 + .07, bottom + h)
            recs.append({'name': f'house-static-{n}', 'ident': f'house-static-{n}', 'aabb': (lo, hi),
                         'pivot': (cx, 3.71, bottom + h / 2), 'tris': box_tris(lo, hi)})
            n += 1
    return recs


BOOKS = {f'book{i:02d}': (.035 + .004 * i, .17 + .003 * i, .23 + .006 * i) for i in range(1, 9)}


def hosts_for(tris):
    boards = b.detect_boards(tris)
    hosts = []
    for z in (2.0675, 2.5175):
        board = min(boards, key=lambda x: abs(x['z'] - z))
        hosts.append({'board': board, 'frame': b.board_frame(board, '-Y'), 'u_range': (.21, 1.11),
                      'top_clearance': .40})
    return hosts


@pytest.fixture(scope='module')
def planned():
    tris = shelf_tris()
    hosts = hosts_for(tris)
    placements = b.plan_layout(hosts, BOOKS, seed=7)
    obstacles = [{'ident': 'house-office-shelves-Oak_shelves', 'aabb': b._aabb([p for t in tris for p in t]),
                  'tris': tris}]
    accepted, rejected = b.validate_placements(placements, obstacles, hosts, tris)
    return tris, hosts, placements, accepted, rejected


# ---------------------------------------------------------------- 1. cube-book identification
def _loft_and_shelf():
    loft_lo, loft_hi = (-3.32, -1.07, 3.035), (-3.28, -.93, 3.2)
    shelf = shelf_tris()
    return [{'name': 'house-static-9', 'ident': 'house-static-9', 'aabb': (loft_lo, loft_hi), 'tris': box_tris(loft_lo, loft_hi)},
            {'name': 'Oak_shelves', 'ident': 'house-office-shelves-Oak_shelves',
             'aabb': b._aabb([p for t in shelf for p in t]), 'tris': shelf}]


def test_identifies_exactly_the_thirty_shelf_cube_books():
    found = b.identify_original_books(cube_book_records() + _loft_and_shelf())
    books = found['books']
    assert len(books) == 30 and {f['row'] for f in books} == {0, 1}
    assert [f['index'] for f in books[:15]] == list(range(15))
    assert len(found['separate']) == 30 and found['batched'] == []
    assert found['separate'][0]['pivot_runtime'][2] == pytest.approx(-3.71)


def test_refuses_and_lists_when_count_or_signature_differs():
    recs = cube_book_records()
    with pytest.raises(b.RefusedError) as err:
        b.identify_original_books(recs[:-1])
    detail = json.loads(str(err.value))
    assert 'found 29' in detail['error'] and len(detail['matched']) == 29
    moved = copy.deepcopy(recs)
    lo, hi = moved[3]['aabb']
    lo, hi = (lo[0], lo[1], lo[2] + .05), (hi[0], hi[1], hi[2] + .05)
    moved[3].update(aabb=(lo, hi), tris=box_tris(lo, hi))
    with pytest.raises(b.RefusedError) as err:
        b.identify_original_books(moved)
    assert json.loads(str(err.value))['near_misses'][0]['reason'].startswith('bottom')


def _batch(records, extra_tris=(), name='house-static-163'):
    tris = [t for r in records for t in r['tris']] + list(extra_tris)
    return {'name': name, 'ident': name, 'aabb': b._aabb([p for t in tris for p in t]), 'tris': tris,
            'pivot': (0.0, 0.0, 0.0)}


def test_material_batched_books_with_other_geometry_get_triangle_excision_not_hide():
    recs = cube_book_records()
    stem = box_tris((1.0, 3.6, 2.3), (1.01, 3.61, 2.9))          # a lamp stem sharing the batch material
    batch = _batch(recs[:3], stem)
    found = b.identify_original_books([batch] + recs[3:] + _loft_and_shelf())
    assert len(found['books']) == 30 and len(found['separate']) == 27
    (x,) = found['batched']
    assert x['node'] == 'house-static-163' and x['never_hide_whole_node']
    assert len(x['excise']['components']) == 3 and x['components_total'] == 4
    assert x['excise']['triangle_ids'] == list(range(36))       # exactly the three books' triangles
    assert x['remainder']['triangle_count'] == 12 and x['remainder']['components'] == 1
    assert x['remainder']['aabb_blender'] == [list((1.0, 3.6, 2.3)), list((1.01, 3.61, 2.9))]
    m = b.hide_manifest(found, [], [])
    assert 'house-static-163' not in {o['name'] for o in m['originals']}
    assert len(m['originals']) == 27 and m['excisions'][0]['node'] == 'house-static-163'


def test_batch_of_books_only_is_still_never_hidden_whole():
    recs = cube_book_records()
    found = b.identify_original_books([_batch(recs[:2])] + recs[2:])
    assert len(found['batched']) == 1 and len(found['separate']) == 28
    assert found['batched'][0]['remainder']['triangle_count'] == 0


def test_no_blanket_hide_rule_is_enforced():
    recs = cube_book_records()
    found = b.identify_original_books([_batch(recs[:2])] + recs[2:])
    found['separate'].append(dict(found['separate'][0], name='house-static-163'))
    with pytest.raises(RuntimeError, match='batched node'):
        b.hide_manifest(found, [], [])


def test_book_welded_to_other_geometry_is_ambiguous_and_refused():
    recs = cube_book_records()
    lo, hi = recs[0]['aabb']
    stem = [((hi[0], hi[1], hi[2]), (hi[0] + .2, hi[1], hi[2]), (hi[0], hi[1], hi[2] + .3))]   # shares a corner
    with pytest.raises(b.RefusedError, match='found 29'):
        b.identify_original_books([_batch(recs[:1], stem)] + recs[1:])


def test_signature_constants_are_the_real_homejs_source():
    src = (ROOT / 'web/house/home.js').read_text()
    assert 'box(w, h, 0.14, x + i * 0.054, y + h / 2, z' in src
    assert 'if (y > 1.6) books(1.2, y + .02, -3.71, 15);' in src
    assert 'const id = "house-static-" + bakedObjects.size;' in src
    rows = []
    y = .25
    while y < 2.6:
        if y > 1.6:
            rows.append(round(y + .02, 6))
        y += .45
    assert tuple(rows) == b.ORIGINAL_BOTTOMS


# ---------------------------------------------------------------- 2. support detection
def test_boards_come_from_evaluated_upward_faces():
    boards = b.detect_boards(shelf_tris())
    assert [round(x['z'], 4) for x in boards] == [round(.2675 + i * .45, 4) for i in range(6)]
    assert boards[4]['clearance'] == pytest.approx(.45 - .022)
    assert boards[5]['clearance'] is None
    assert boards[0]['lo'] == pytest.approx([.95, 3.55]) and boards[0]['hi'] == pytest.approx([3.3, 3.89])


def test_no_board_without_real_geometry():
    assert b.detect_boards(box_tris((0, 0, 0), (.1, .1, .1))) == []


# ---------------------------------------------------------------- 3. asset measurement
def _book_points(t, d, h, x0, yaw_deg=0.0):
    pts = [(x, y, z) for x in (-t / 2, t / 2) for y in (-d / 2, d / 2) for z in (0, h)]
    pts += [(x * .5, y * .5, z * .5 + h * .25) for x, y, z in pts]
    c, s = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    return [(x0 + c * x - s * y, s * x + c * y, z) for x, y, z in pts]


def test_book_frame_measures_real_dimensions_rigidly():
    f = b.book_frame(_book_points(.05, .18, .26, 1.0, yaw_deg=4))
    assert f['dims'] == pytest.approx((.05, .18, .26), abs=1e-6)
    assert f['origin'] == pytest.approx((1.0, 0.0, 0.0), abs=1e-6)
    det = (f['rot'][0][0] * (f['rot'][1][1] * f['rot'][2][2] - f['rot'][1][2] * f['rot'][2][1])
           - f['rot'][0][1] * (f['rot'][1][0] * f['rot'][2][2] - f['rot'][1][2] * f['rot'][2][0])
           + f['rot'][0][2] * (f['rot'][1][0] * f['rot'][2][1] - f['rot'][1][1] * f['rot'][2][0]))
    assert det == pytest.approx(1.0)          # proper rotation: no mirror, no scale
    assert b.check_book_dims(f['dims']) is None
    assert b.check_book_dims((5, 18, 26)) is not None   # centimetre asset is refused without --uniform-scale


def test_islands_and_part_clustering_split_books_not_covers():
    assert len(b.islands(6, [(0, 1, 2), (3, 4, 5)])) == 2
    cover = {'points': _book_points(.05, .18, .26, 0)}
    pages = {'points': _book_points(.04, .17, .25, 0)}
    other = {'points': _book_points(.05, .18, .26, .0505)}
    assert b.cluster_parts([cover, pages, other]) == [[0, 1], [2]]


# ---------------------------------------------------------------- 4. layout
def test_layout_is_deterministic_and_varied(planned):
    tris, hosts, placements, accepted, rejected = planned
    again = b.plan_layout(hosts_for(tris), BOOKS, seed=7)
    assert [p['world'] for p in again] == [p['world'] for p in placements]
    assert [p['world'] for p in b.plan_layout(hosts_for(tris), BOOKS, seed=8)] != [p['world'] for p in placements]
    modes = {p['mode'] for p in accepted}
    assert modes == {'upright', 'lean', 'stack'}
    assert rejected == [] and len(accepted) >= 16
    assert {p['board'] for p in accepted} == {0, 1}


def test_no_interpenetration_and_every_book_supported(planned):
    _, _, _, accepted, _ = planned
    for i, p in enumerate(accepted):
        for q in accepted[i + 1:]:
            assert not b.obb_overlap(b.obb(p, b.COLLISION_SHRINK), b.obb(q, b.COLLISION_SHRINK))
        if p['rests_on'] == 'board':
            hit, total = p['checks']['support_rays_hit'].split('/')
            assert hit == total and 0 <= p['checks']['bottom_gap_m'] <= b.CONTACT_TOL
        else:
            assert 0 <= p['checks']['stack_gap_m'] <= b.CONTACT_TOL


def test_leaning_books_have_two_checked_contacts(planned):
    _, _, _, accepted, _ = planned
    leans = [p for p in accepted if p['mode'] == 'lean']
    assert leans
    for p in leans:
        assert 5 < p['lean_deg'] < 35
        assert p['checks']['contacts'][0] == 'board'
        c = p['checks']['lean_contact']
        assert 0 <= c['gap_m'] <= b.CONTACT_TOL and c['contact_height_m'] <= c['neighbour_top_m']


def test_real_dimensions_preserved_no_scale(planned):
    _, _, _, accepted, _ = planned
    for p in accepted:
        m = p['world']
        cols = [math.sqrt(sum(m[r][k] ** 2 for r in range(3))) for k in range(3)]
        assert cols == pytest.approx([1, 1, 1])
        assert tuple(p['dims']) == BOOKS[p['source']]
        corners = b.world_corners(p)
        t, d, h = p['dims']
        assert max(math.dist(corners[0], c) for c in corners) == pytest.approx(math.sqrt(t * t + d * d + h * h))


def test_spines_face_the_room(planned):
    _, _, _, accepted, _ = planned
    for p in accepted:
        spine = tuple(-p['world'][r][1] for r in range(3))   # local -y in world
        assert spine == pytest.approx((0, -1, 0), abs=1e-9)  # Blender -Y = runtime +z = toward the room


def test_collisions_and_unsupported_placements_are_rejected(planned):
    tris, hosts, placements, _, _ = planned
    wall = box_tris((.9, 3.60, 2.0675), (3.4, 3.62, 2.9))          # an obstacle through the books
    accepted, rejected = b.validate_placements(copy.deepcopy(placements),
                                               [{'ident': 'wall', 'aabb': b._aabb([p for t in wall for p in t]), 'tris': wall}],
                                               hosts, tris)
    assert not accepted and all(any(r.startswith('collides:wall') or r.startswith('support_lost')
                                    or r.startswith('lean_neighbour_lost') for r in x['reasons']) for x in rejected)
    floating = copy.deepcopy(placements)
    floating[0]['world'][2][3] += .03
    accepted, rejected = b.validate_placements(floating, [], hosts, tris)
    assert rejected[0]['id'] == floating[0]['id'] and 'not_on_board' in rejected[0]['reasons'][0]
    no_support = b.validate_placements(copy.deepcopy(placements), [], hosts, [])[1]
    assert any('unsupported' in r for x in no_support for r in x['reasons'])


# ---------------------------------------------------------------- 5. manifest, fingerprint, GLB, materials
def test_hide_manifest_lists_exact_originals():
    found = b.identify_original_books(cube_book_records())
    m = b.hide_manifest(found, [{'name': 'Oak_shelves'}], [], 'abc')
    assert m['expected_count'] == 30 and len(m['originals']) == 30 and m['excisions'] == []
    assert m['originals'][0]['canonical'] == 'housestatic500'
    assert 'never destroy' in m['policy'] and 'collision unchanged' in m['policy'] and 'never hidden whole' in m['policy']


def test_fingerprint_change_is_detected():
    rows = {'house-static-1': {'matrix': [[1, 0], [0, 1]]}, 'Oak_shelves': {'matrix': [[1]]}}
    before = b.fingerprint_rows(rows)
    assert b.fingerprint_changes(before, b.fingerprint_rows(rows)) == []
    moved = copy.deepcopy(rows)
    moved['Oak_shelves']['matrix'] = [[1.0001]]
    assert b.fingerprint_changes(before, b.fingerprint_rows(moved)) == ['Oak_shelves']
    del moved['house-static-1']
    assert 'house-static-1' in b.fingerprint_changes(before, b.fingerprint_rows(moved))


def _doc(emissive=False):
    mat = {'name': 'SUB01_RealBook_book_encyclopedia_set_01',
           'pbrMetallicRoughness': {'baseColorTexture': {'index': 0}, 'metallicRoughnessTexture': {'index': 2}},
           'normalTexture': {'index': 1}}
    if emissive:
        mat['emissiveFactor'] = [1, 1, 1]
    return {'nodes': [{'name': 'SUB01_RealBook_01'}], 'materials': [mat],
            'textures': [{'source': 0}, {'source': 1}, {'source': 2}],
            'images': [{'name': 'book_encyclopedia_set_01_diff_1k'}, {'name': 'book_encyclopedia_set_01_nor_gl_1k'},
                       {'name': 'book_encyclopedia_set_01_rough_1k'}]}


def test_glb_roles_additive_only_and_no_emission():
    assert b.glb_texture_roles(_doc()) == {'book_encyclopedia_set_01_diff_1k': 'base_color',
                                           'book_encyclopedia_set_01_nor_gl_1k': 'normal',
                                           'book_encyclopedia_set_01_rough_1k': 'metallic_roughness'}
    with pytest.raises(RuntimeError, match='emissive'):
        b.glb_texture_roles(_doc(emissive=True))
    assert b.verify_additive_glb(_doc(), ['SUB01_RealBook_01'])
    leaking = _doc()
    leaking['nodes'].append({'name': 'house-static-12'})
    with pytest.raises(RuntimeError, match='not additive-only'):
        b.verify_additive_glb(leaking, ['SUB01_RealBook_01'])


class _N:
    def __init__(self, name, idname, image=None):
        self.name, self.bl_idname, self.image = name, idname, image


class _L:
    def __init__(self, a, b_, sock):
        self.from_node, self.to_node, self.to_socket = a, b_, types.SimpleNamespace(name=sock)


def _material(extra_link=None):
    img = lambda n: types.SimpleNamespace(name=n)
    diff, nor, rough = (_N('d', 'ShaderNodeTexImage', img('diff')), _N('n', 'ShaderNodeTexImage', img('nor')),
                        _N('r', 'ShaderNodeTexImage', img('rough')))
    nmap, bsdf = _N('nm', 'ShaderNodeNormalMap'), _N('p', 'ShaderNodeBsdfPrincipled')
    links = [_L(diff, bsdf, 'Base Color'), _L(nor, nmap, 'Color'), _L(nmap, bsdf, 'Normal'), _L(rough, bsdf, 'Roughness')]
    if extra_link:
        links.append(extra_link(diff, bsdf))
    return types.SimpleNamespace(name='m', node_tree=types.SimpleNamespace(nodes=[diff, nor, rough, nmap, bsdf], links=links))


def test_blender_material_colour_space_roles():
    assert b.image_roles(_material()) == {'diff': 'sRGB', 'nor': 'Non-Color', 'rough': 'Non-Color'}
    with pytest.raises(RuntimeError, match='emission'):
        b.image_roles(_material(lambda d, p: _L(d, p, 'Emission Color')))
    with pytest.raises(RuntimeError, match='both'):
        b.image_roles(_material(lambda d, p: _L(d, p, 'Roughness')))


# ---------------------------------------------------------------- 6. Unreal import (fake unreal)
class V:
    def __init__(self, x, y, z, w=1.0):
        self.x, self.y, self.z, self.w = x, y, z, w


class FakeTexture:
    def __init__(self, srgb, comp):
        self.p = {'srgb': srgb, 'compression_settings': comp}

    def get_editor_property(self, k):
        return self.p[k]

    def set_editor_property(self, k, v):
        self.p[k] = v


class FakeMesh:
    def __init__(self, path):
        self.path = path

    def get_path_name(self):
        return self.path


class FakeComp:
    def __init__(self, name, loc, mesh):
        self.name, self.loc, self.mesh, self.visible, self.collision = name, loc, FakeMesh(mesh), True, 'QUERY_AND_PHYSICS'

    def get_name(self):
        return self.name

    def get_editor_property(self, k):
        return {'static_mesh': self.mesh, 'visible': self.visible}[k]

    def get_world_location(self):
        return V(*self.loc)

    def get_world_transform(self):
        return types.SimpleNamespace(translation=V(*self.loc), rotation=V(0, 0, 0, 1), scale3d=V(1, 1, 1))

    def get_path_name(self):
        return '/Level/' + self.name

    def get_collision_enabled(self):
        return self.collision

    def set_collision_enabled(self, v):
        self.collision = v

    def get_collision_profile_name(self):
        return 'BlockAll'

    def get_materials(self):
        return []

    def set_visibility(self, v, propagate=False):
        self.visible = v

    def set_mobility(self, m):
        pass


class FakeActor:
    def __init__(self, label, loc, mesh='/Game/Sub01Home/ImportedScene/m'):
        self.label, self.comps, self.tags, self.hidden = label, [FakeComp(label, loc, mesh)], [], False
        self.folder = None

    def get_actor_label(self):
        return self.label

    def set_actor_label(self, v):
        self.label = v

    def get_components_by_class(self, cls):
        return self.comps

    def get_editor_property(self, k):
        return {'tags': self.tags, 'hidden': self.hidden}[k]

    def set_actor_hidden_in_game(self, v):
        self.hidden = v

    def get_path_name(self):
        return '/Level/Actor_' + str(id(self))

    def get_actor_transform(self):
        return self.comps[0].get_world_transform()

    def get_actor_scale3d(self):
        return V(1, 1, 1)

    def set_folder_path(self, p):
        self.folder = p


def ue(p):  # runtime metres -> UE cm used by the fake import (axes x, z, y)
    return (100 * p[0] + 10, 100 * p[2] - 5, 100 * p[1] + 2)


def _fake_unreal(world, glb_books, textures):
    u = types.ModuleType('unreal')
    u.StaticMeshComponent = object
    u.CollisionEnabled = types.SimpleNamespace(NO_COLLISION='NO_COLLISION')
    u.ComponentMobility = types.SimpleNamespace(STATIC='STATIC')
    u.TextureCompressionSettings = types.SimpleNamespace(TC_DEFAULT='TC_DEFAULT', TC_NORMALMAP='TC_NORMALMAP')
    assets = set()

    class Lib:
        @staticmethod
        def does_directory_exist(p):
            return any(a.startswith(p) for a in assets)

        @staticmethod
        def delete_directory(p):
            for a in [a for a in assets if a.startswith(p)]:
                assets.discard(a)

        @staticmethod
        def save_directory(*a, **k):
            return True

        @staticmethod
        def load_asset(name):
            return textures[name]
    u.EditorAssetLibrary = Lib

    class Manager:
        def create_source_data(self, path):
            return path

        def can_translate_source_data(self, data, flag):
            return True

        def import_scene(self, dest, data, params):
            for book in glb_books:
                world.append(FakeActor(book['id'], ue(book['pivot_runtime_m']), dest + '/SM_' + book['id']))
                assets.add(dest + '/SM_' + book['id'])
            for name in textures:
                assets.add(dest + '/' + name)
            u._dest = dest
            return True

        def wait_until_all_tasks_done(self, flag):
            pass
    u.InterchangeManager = types.SimpleNamespace(get_interchange_manager_scripted=lambda: Manager())

    class Params:
        def set_editor_property(self, k, v):
            pass
    u.ImportAssetParameters = Params
    registry = types.SimpleNamespace(get_assets_by_path=lambda p, recursive=True: [
        types.SimpleNamespace(asset_name=n, package_name=n, asset_class_path=types.SimpleNamespace(asset_name='Texture2D'))
        for n in textures if any(a.startswith(p) for a in assets)])
    u.AssetRegistryHelpers = types.SimpleNamespace(get_asset_registry=lambda: registry)
    u.log = lambda *a: None
    level = types.SimpleNamespace(save_current_level=lambda: True)
    actor_sub = types.SimpleNamespace(get_all_level_actors=lambda: list(world),
                                      destroy_actor=lambda a: world.remove(a))
    return u, level, actor_sub


@pytest.fixture
def ue_setup(tmp_path, monkeypatch):
    found = b.identify_original_books(cube_book_records())
    refs = [{'name': 'Haven_linen', 'ident': 'house-sofa-Haven_linen', 'canonical': 'havenlinen',
             'canonical_ident': 'housesofahavenlinen', 'pivot_runtime_m': [-1.0, .4, 1.5]},
            {'name': 'Oak_desk', 'ident': 'house-office-desk-Oak_desk', 'canonical': 'oakdesk',
             'canonical_ident': 'houseofficedeskoakdesk', 'pivot_runtime_m': [2.0, .75, -3.0]}]
    shelf = [{'name': 'Oak_shelves', 'ident': 'house-office-shelves-Oak_shelves', 'canonical': 'oakshelves',
              'canonical_ident': 'houseofficeshelvesoakshelves', 'pivot_runtime_m': [2.125, 0, -3.72]}]
    glb = tmp_path / 'real-shelf-books.glb'
    glb.write_bytes(b'glb-fixture')
    digest = hashlib.sha256(glb.read_bytes()).hexdigest()
    built = [{'id': f'SUB01_RealBook_{i:02d}', 'pivot_runtime_m': [1.2 + .05 * i, 2.07, -3.7]} for i in range(1, 4)]
    report = {'mode': 'blender', 'basis': 'evaluated-geometry', 'existing_objects_verified_unchanged': 233,
              'built': built, 'additive_glb': {'objects': [x['id'] for x in built], 'sha256': digest,
                                               'verified_additive_only': True,
                                               'texture_roles': {'book_encyclopedia_set_01_diff_1k': 'base_color',
                                                                 'book_encyclopedia_set_01_nor_gl_1k': 'normal',
                                                                 'book_encyclopedia_set_01_rough_1k': 'metallic_roughness'}}}
    manifest = b.hide_manifest(found, shelf, refs, digest)
    world = [FakeActor(o['name'], ue(o['pivot_runtime_m'])) for o in manifest['originals']]
    world += [FakeActor(r['name'], ue(r['pivot_runtime_m'])) for r in refs + shelf]
    textures = {'T_book_encyclopedia_set_01_diff_1k': FakeTexture(True, 'TC_DEFAULT'),
                'T_book_encyclopedia_set_01_nor_gl_1k': FakeTexture(True, 'TC_DEFAULT'),
                'T_book_encyclopedia_set_01_rough_1k': FakeTexture(True, 'TC_DEFAULT')}
    u, level, actor_sub = _fake_unreal(world, built, textures)
    monkeypatch.setitem(sys.modules, 'unreal', u)
    return dict(u=u, level=level, actor_sub=actor_sub, world=world, report=report, manifest=manifest,
                glb=glb, digest=digest, project=tmp_path, textures=textures, shelf=shelf)


def _apply(s):
    return ui.apply(s['u'], s['level'], s['actor_sub'], s['project'], s['report'], s['manifest'], s['glb'], s['digest'])


def test_import_hides_originals_places_books_and_fixes_texture_spaces(ue_setup):
    s = ue_setup
    assert ui.validate_receipt(s['report'], s['manifest'], s['glb']) == s['digest']
    result = _apply(s)
    assert len(result['placed']) == 3 and result['originals_hidden'] == 30
    originals = {o['name'] for o in s['manifest']['originals']}
    for a in s['world']:
        if a.label in originals:
            assert a.hidden and not a.comps[0].visible and a.comps[0].collision == 'QUERY_AND_PHYSICS'
        elif a.label.startswith('SUB01_RealBook_'):
            assert ui.ACTOR_TAG in a.tags and a.comps[0].collision == 'NO_COLLISION' and not a.hidden
    tex = s['textures']
    assert tex['T_book_encyclopedia_set_01_diff_1k'].p == {'srgb': True, 'compression_settings': 'TC_DEFAULT'}
    assert tex['T_book_encyclopedia_set_01_nor_gl_1k'].p == {'srgb': False, 'compression_settings': 'TC_NORMALMAP'}
    assert tex['T_book_encyclopedia_set_01_rough_1k'].p['srgb'] is False
    # idempotent second run: nothing new imported
    count = len(s['world'])
    assert _apply(s) == {'already_applied': True, 'source_sha256': s['digest']}
    assert len(s['world']) == count
    # a different version refuses until restore
    with pytest.raises(RuntimeError, match='restore'):
        ui.apply(s['u'], s['level'], s['actor_sub'], s['project'], s['report'], s['manifest'], s['glb'], 'other')
    ui.restore(s['u'], s['level'], s['actor_sub'], s['project'], s['manifest'])
    assert not any(a.label.startswith('SUB01_RealBook_') for a in s['world'])
    assert all(not a.hidden and a.comps[0].visible for a in s['world'])
    assert len(s['world']) == 30 + 3


def test_import_refuses_on_shelf_mismatch_and_ambiguous_originals(ue_setup):
    s = ue_setup
    shelf_actor = next(a for a in s['world'] if a.label == 'Oak_shelves')
    shelf_actor.comps[0].loc = tuple(v + (1.0 if i == 0 else 0) for i, v in enumerate(shelf_actor.comps[0].loc))
    with pytest.raises(RuntimeError, match='Shelf actor'):
        _apply(s)
    shelf_actor.comps[0].loc = ue(s['shelf'][0]['pivot_runtime_m'])
    dup = s['manifest']['originals'][0]['name']
    s['world'].append(FakeActor(dup, (0, 0, 0)))
    with pytest.raises(RuntimeError, match='exactly one'):
        _apply(s)
    assert not any(a.label.startswith('SUB01_RealBook_') for a in s['world'])


def test_import_rolls_back_when_a_book_lands_off_its_pivot(ue_setup):
    s = ue_setup
    s['report']['built'][1]['pivot_runtime_m'] = [9, 9, 9]
    u, level, actor_sub = _fake_unreal(s['world'], [dict(x, pivot_runtime_m=[1.25, 2.07, -3.7]) if i == 1 else x
                                                    for i, x in enumerate(s['report']['built'])], s['textures'])
    s.update(u=u, level=level, actor_sub=actor_sub)
    with pytest.raises(RuntimeError, match='rolled back'):
        _apply(s)
    assert not any(a.label.startswith('SUB01_RealBook_') for a in s['world'])
    assert not any(a.hidden for a in s['world'])


def test_receipt_refusals(ue_setup):
    s = ue_setup
    with pytest.raises(ValueError, match='successful real'):
        ui.validate_receipt(dict(s['report'], mode='dry-run'), s['manifest'], s['glb'])
    s['glb'].write_bytes(b'changed')
    with pytest.raises(ValueError, match='differs'):
        ui.validate_receipt(s['report'], s['manifest'], s['glb'])
    s['glb'].write_bytes(b'glb-fixture')
    short = dict(s['manifest'], originals=s['manifest']['originals'][:-1])
    with pytest.raises(ValueError, match='exact expected'):
        ui.validate_receipt(s['report'], short, s['glb'])


def test_import_refuses_batched_books_until_excision_and_never_hides_the_batch(ue_setup):
    s = ue_setup
    recs = cube_book_records()
    stem = box_tris((1.0, 3.6, 2.3), (1.01, 3.61, 2.9))
    found = b.identify_original_books([_batch(recs[:3], stem)] + recs[3:])
    manifest = b.hide_manifest(found, s['shelf'], s['manifest']['reference_pivots'], s['digest'])
    with pytest.raises(ValueError, match='material-batched'):
        ui.validate_receipt(s['report'], manifest, s['glb'])
    assert ui.validate_receipt(s['report'], manifest, s['glb'], excision_applied=True) == s['digest']
    bad = copy.deepcopy(manifest)
    bad['originals'].append(dict(bad['originals'][0], name='house-static-163', canonical='housestatic163'))
    bad['excisions'][0]['excise']['components'].pop()
    with pytest.raises(ValueError, match='never hide'):
        ui.validate_receipt(s['report'], bad, s['glb'], excision_applied=True)
    # with the excision applied, the batch actor stays visible and untouched
    s['world'][:3] = [FakeActor('house-static-163', (0, 0, 0))]
    s['manifest'] = manifest
    _apply(s)
    batch_actor = next(a for a in s['world'] if a.label == 'house-static-163')
    assert not batch_actor.hidden and batch_actor.comps[0].visible
    assert sum(1 for a in s['world'] if a.hidden) == 27


def test_texture_contract_refuses_unknown_or_unfixable(monkeypatch):
    monkeypatch.delitem(sys.modules, 'unreal', raising=False)
    roles = {'book_diff_1k': 'base_color', 'book_nor_gl_1k': 'normal'}
    ok = ui.check_textures([('T_book_diff_1k', FakeTexture(True, 'TC_DEFAULT')),
                            ('T_book_nor_gl_1k', FakeTexture(False, 'TC_NORMALMAP'))], roles, fix=False)
    assert [r['role'] for r in ok] == ['base_color', 'normal']
    with pytest.raises(RuntimeError, match='colour-space'):
        ui.check_textures([('T_book_nor_gl_1k', FakeTexture(True, 'TC_DEFAULT'))], roles, fix=False)
    with pytest.raises(RuntimeError, match='unknown role'):
        ui.check_textures([('T_mystery', FakeTexture(True, 'TC_DEFAULT'))], roles, fix=False)
