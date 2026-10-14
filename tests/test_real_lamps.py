"""CPU tests for tools/build_real_lamps.py and tools/unreal_import_real_lamps.py.

No Blender/Unreal here: synthetic GLB documents, fake support probes and a fake
``unreal`` module exercise identification, exact component excision, the rail
union, placement, the hide manifest and the import/restore flow."""
import base64
import hashlib
import importlib.util
import json
import math
import struct
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B = load('build_real_lamps', 'tools/build_real_lamps.py')
U = load('unreal_import_real_lamps', 'tools/unreal_import_real_lamps.py')


# --------------------------------------------------------------- synthetic geometry
def cylinder_mesh(r, y0, y1, x, z, seg):
    """three.js CylinderGeometry layout: torso grid + separate top/bottom caps (indexed)."""
    verts, idx = [], []
    for row, y in enumerate((y1, y0)):
        for k in range(seg + 1):
            t = 2 * math.pi * k / seg
            verts.append((x + r * math.sin(t), y, z + r * math.cos(t)))
    for k in range(seg):
        a, b, c, d = k, k + seg + 1, k + seg + 2, k + 1
        idx += [a, b, d, b, c, d]
    for y in (y1, y0):
        centre = len(verts)
        verts.append((x, y, z))
        ring = len(verts)
        for k in range(seg + 1):
            t = 2 * math.pi * k / seg
            verts.append((x + r * math.sin(t), y, z + r * math.cos(t)))
        for k in range(seg):
            idx += [centre, ring + k, ring + k + 1]
    return verts, idx


def merge(parts):
    verts, idx, spans = [], [], []
    for v, i in parts:
        base, t0 = len(verts), len(idx) // 3
        verts += v
        idx += [j + base for j in i]
        spans.append(list(range(t0, len(idx) // 3)))
    return verts, idx, spans


class Doc:
    """Tiny GLB-like document builder (single binary buffer)."""

    def __init__(self):
        self.doc = {'asset': {'version': '2.0'}, 'nodes': [], 'meshes': [], 'accessors': [], 'bufferViews': [],
                    'materials': [], 'buffers': []}
        self.bin = bytearray()
        self.mats = {}

    def material(self, name, emissive=False):
        if name not in self.mats:
            self.mats[name] = len(self.doc['materials'])
            m = {'name': name}
            if emissive:
                m['emissiveFactor'] = [1, 1, 1]
            self.doc['materials'].append(m)
        return self.mats[name]

    def _acc(self, data, fmt, count, kind, ctype, mn=None, mx=None):
        off = len(self.bin)
        self.bin += struct.pack('<' + fmt * len(data), *data)
        while len(self.bin) % 4:
            self.bin += b'\0'
        self.doc['bufferViews'].append({'buffer': 0, 'byteOffset': off, 'byteLength': len(data) * struct.calcsize(fmt)})
        a = {'bufferView': len(self.doc['bufferViews']) - 1, 'componentType': ctype, 'count': count, 'type': kind}
        if mn is not None:
            a['min'], a['max'] = mn, mx
        self.doc['accessors'].append(a)
        return len(self.doc['accessors']) - 1

    def mesh_node(self, verts, idx, material, name=None, translation=None, emissive=False):
        flat = [c for v in verts for c in v]
        mn = [min(v[i] for v in verts) for i in range(3)]
        mx = [max(v[i] for v in verts) for i in range(3)]
        pos = self._acc(flat, 'f', len(verts), 'VEC3', 5126, mn, mx)
        ind = self._acc(idx, 'I', len(idx), 'SCALAR', 5125)
        self.doc['meshes'].append({'primitives': [{'attributes': {'POSITION': pos}, 'indices': ind,
                                                   'material': self.material(material, emissive)}]})
        node = {'mesh': len(self.doc['meshes']) - 1}
        if name:
            node['name'] = name
        if translation:
            node['translation'] = translation
        self.doc['nodes'].append(node)
        return len(self.doc['nodes']) - 1

    def filler(self, upto):
        while len(self.doc['nodes']) < upto:
            self.doc['nodes'].append({'name': f'empty_{len(self.doc["nodes"])}'})

    def node_at(self, index, *args, **kw):
        self.filler(index)
        assert len(self.doc['nodes']) == index
        return self.mesh_node(*args, **kw)

    def buffers(self):
        return [bytes(self.bin)]


def local_cyl(r, h, seg=24):
    return cylinder_mesh(r, -h / 2, h / 2, 0, 0, seg)


def test_rotated_lamp_bounds_use_actual_vertices_not_local_box_corners():
    d = Doc()
    index = d.mesh_node([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [0, 1, 2], 'lamp')
    d.doc['nodes'][index]['rotation'] = [0, 0, math.sin(math.pi / 8), math.cos(math.pi / 8)]
    exact = B.glb_mesh_nodes(d.doc, d.buffers())[0]['aabb']
    conservative = B.glb_mesh_nodes(d.doc)[0]['aabb']
    assert exact[1][1] == pytest.approx(math.sqrt(.5))
    assert conservative[1][1] == pytest.approx(math.sqrt(2))


def test_pipe_lamp_bulb_identity_ignores_shared_body_emission_atlas(tmp_path):
    d = Doc()
    d.mesh_node([(0, 0, 0), (.1, 0, 0), (0, .3, .1)], [0, 1, 2], 'body',
                name='industrial_pipe_lamp', emissive=True)
    d.mesh_node([(0, .29, 0), (.01, .3, 0), (0, .31, .01)], [0, 1, 2], 'glass',
                name='industrial_pipe_lamp_bulb', emissive=True)
    d.doc['buffers'] = [{'uri': 'asset.bin', 'byteLength': len(d.bin)}]
    (tmp_path / 'asset.bin').write_bytes(bytes(d.bin))
    path = tmp_path / 'asset.gltf'
    path.write_text(json.dumps(d.doc))
    rows = B.primitive_vertices(path, bulb_node_only=True)
    assert [em for _, em, _ in rows] == [False, True]
    measured = B.measure_table_lamp(rows)
    assert measured['rest_plane_y'] == 0 and measured['bulb_center'][1] > .29


def build_home(stem_copies=1, stem_radius=.014, rail_conflict=False):
    d = Doc()
    # shared metal batch node 163: 3 rail balusters + the white desk-lamp stem (home.js:1114)
    rails = [cylinder_mesh(.022, 3.0, 4.0, .85, -2.0 - .3 * k, 10) for k in range(3)]
    stems = [cylinder_mesh(stem_radius, .85, 1.3, 1.1 + .5 * k, -3.15, 10) for k in range(stem_copies)]
    verts, idx, spans = merge(rails + stems)
    d.node_at(126, *local_cyl(.14, .035), 'Material_63', name='Mesh_106', translation=[1.1, 1.3, -3.15])
    d.node_at(127, *local_cyl(.18, .013), 'Material_63', name='house-static-64', translation=[-2, 2.473, .5])
    d.node_at(128, *local_cyl(.23, .15), 'white', name='house-static-x1', translation=[-2, 2.55, .5])
    d.node_at(129, *local_cyl(.18, .013), 'Material_63', name='house-static-65', translation=[2, 5.023, -.2])
    d.node_at(130, *local_cyl(.23, .15), 'white', name='house-static-x2', translation=[2, 5.1, -.2])
    d.node_at(131, *cylinder_mesh(.006, 2.65, 6, -2, .5, 10), 'black', name='cable-lower')
    d.node_at(132, *cylinder_mesh(.006, 5.2, 6, 2, -.2, 10), 'black', name='cable-upper')
    d.node_at(150, *cylinder_mesh(.1, .87, 1.6, 2.65, -3.18, 8), 'desk_lamp_arm_01', name='desk_lamp_arm_01')
    d.node_at(151, *cylinder_mesh(.02, 1.4, 1.5, 2.6, -3.2, 8), 'desk_lamp_arm_01_light', name='desk_lamp_arm_01_l')
    d.node_at(163, verts, idx, 'Material_8', name='house-static-batch-163')
    for i, name in enumerate(('Brass_base', 'Brass_socket', 'Brass_stem', 'Bulb', 'Linen_shade')):
        d.node_at(195 + i, *local_cyl(.05 + .02 * i, .05), 'Material_91' if name == 'Linen_shade' else
                  ('Material_63' if name == 'Bulb' else 'brass'), name=name, translation=[-3.55, 3.55 + .06 * i, -3.1])
    d.node_at(220, *local_cyl(.3, .02), 'monitor_screen', name='Monitor_screen', translation=[2, 1.16, -3.3])
    rail_spec = {'excisions': [{'node': 163, 'primitive': 0, 'triangle_ids': sorted(t for s in spans[:3] for t in s)}]}
    if rail_conflict:
        rail_spec['excisions'][0]['triangle_ids'].append(spans[3][0])
    return d, spans, rail_spec


def identify(d):
    nodes = B.glb_mesh_nodes(d.doc)
    bufs = d.buffers()
    return nodes, B.identify_originals(nodes, lambda i: B.primitive_components(d.doc, bufs, i))


# --------------------------------------------------------------- coordinates
def test_desk_lamp_light_conversion():
    p = (1.1, 1.35, -3.15)
    assert B.source_to_blender(p) == pytest.approx((1.1, 3.15, 1.35))
    assert B.blender_to_source(B.source_to_blender(p)) == pytest.approx(p)
    assert B.source_to_ue_cm(p) == pytest.approx((110.0, -315.0, 135.0))
    assert B.LIGHT_SOURCE['DeskLamp'] == p
    assert abs(B.ue_yaw_from_source(180.0)) == pytest.approx(180.0)
    assert B.ue_yaw_from_source(30.0) == pytest.approx(-30.0)  # mirrored (x, z, y) contract
    assert U.ue_yaw(30.0, {'axes': (0, 2, 1), 'signs': (1, 1, 1)}) == pytest.approx(-30.0)


# --------------------------------------------------------------- exact component excision
def test_exact_stem_components_selected_from_shared_batch():
    d, spans, _ = build_home()
    nodes, parts = identify(d)
    stem = parts['DeskLamp']['white_lamp_stem']
    assert stem['status'] == 'excise-components'
    sel = stem['selection']
    assert sel['node'] == 163 and sel['primitive'] == 0
    assert sel['triangle_ids'] == spans[3]  # exactly the stem, no rail triangle
    lo, hi = sel['aabb_m']
    assert lo[1] == pytest.approx(.85) and hi[1] == pytest.approx(1.3)
    assert max(hi[2] - (-3.15), -3.15 - lo[2]) == pytest.approx(.014, abs=1e-6)


def test_stem_refuses_when_ambiguous_or_missing():
    d, _, _ = build_home(stem_copies=2)
    # second identical stem shifted 0.5 m does not fit the signature: still exactly one
    identify(d)
    nodes = B.glb_mesh_nodes(d.doc)
    comps = B.primitive_components(d.doc, d.buffers(), 163)
    stem_comp = [c for c in comps if B.fits_cylinder(c['vertices'], B.ORIGINAL_SIGNATURES['DeskLamp']['white_lamp_stem'][0])]
    twin = [dict(c, node=164) for c in stem_comp]
    with pytest.raises(B.RefuseError, match='ambiguous'):
        B.select_cylinder_components(B.ORIGINAL_SIGNATURES['DeskLamp']['white_lamp_stem'][0], comps + twin)
    d2, _, _ = build_home(stem_radius=.02)  # wrong radius: no exact match
    with pytest.raises(B.RefuseError, match='no exact connected-component match'):
        identify(d2)
    assert nodes


def test_union_with_rail_is_one_remainder_without_double_removal():
    d, spans, rail = build_home()
    nodes, parts = identify(d)
    manifest = B.build_hide_manifest(parts, B.identify_red_lamp(nodes), B.ROLES, B.identify_bedside(nodes))
    lamp = B.lamp_excision_manifest(manifest['excisions'])
    counts = B.triangle_counts(d.doc)
    combined = B.combine_remainder(lamp, rail, counts)
    rows = [r for r in combined['remainders'] if r['node'] == 163]
    assert len(rows) == 1
    row = rows[0]
    assert row['remove_triangle_ids'] == sorted(t for s in spans for t in s)
    assert row['lamp_triangles'] == len(spans[3]) and row['rail_triangles'] == sum(len(s) for s in spans[:3])
    assert row['remaining_triangles'] == counts[(163, 0)] - len(row['remove_triangle_ids'])
    _, _, bad = build_home(rail_conflict=True)
    with pytest.raises(B.RefuseError, match='double-removal'):
        B.combine_remainder(lamp, bad, counts)
    # nested-dict rail format is accepted too
    nested = {'nodes': {'163': {'primitives': {'0': {'triangle_ids': rail['excisions'][0]['triangle_ids']}}}}}
    assert B.combine_remainder(lamp, nested, counts)['remainders'] == combined['remainders']


def test_emitters_hidden_not_excised_and_no_blanket_batch_hide():
    d, _, _ = build_home()
    nodes, parts = identify(d)
    manifest = B.build_hide_manifest(parts, B.identify_red_lamp(nodes), B.ROLES, B.identify_bedside(nodes))
    hidden = {e['source_node_index'] for e in manifest['entries']}
    excised = {x['node'] for x in manifest['excisions']}
    assert {126, 127, 129, 198, 199} <= hidden
    assert 126 not in excised and 163 not in hidden and excised == {163}
    assert 66 not in hidden and 220 not in hidden  # kitchen strip and the screen stay
    desk = next(e for e in manifest['entries'] if e['source_node_index'] == 126)
    assert desk['ue_actor_name'] == 'full-home_node_126' and desk['action'] == 'hide-not-destroy'
    assert desk['citation'] == 'web/house/home.js:1113'


def test_emitter_must_be_standalone():
    nodes = [{'index': 126, 'name': 'batch', 'materials': ['x'], 'translation': [0, 0, 0],
              'aabb': [[0, 0, -4], [3, 2, -2]]}]
    with pytest.raises(B.RefuseError, match='hidden, never excised'):
        B.identify_originals(nodes, lambda i: [])


def test_screens_and_kitchen_strip_protected():
    screen = {'index': 220, 'name': 'Monitor_screen', 'materials': ['monitor_screen'], 'translation': [0, 0, 0],
              'aabb': [[0, 0, 0], [1, 1, 1]]}
    with pytest.raises(B.RefuseError, match='protected'):
        B._protect(screen)
    with pytest.raises(B.RefuseError):
        B._protect(dict(screen, index=66, name='house-static-11', materials=['Material_13']))


def test_no_second_red_lamp():
    d, _, _ = build_home()
    nodes, parts = identify(d)
    red = B.identify_red_lamp(nodes)
    assert {n['index'] for n in red} == {150, 151}
    manifest = B.build_hide_manifest(parts, red, B.ROLES, B.identify_bedside(nodes))
    placed = [{'asset': 'desk_lamp_arm_01'}]
    assert B.check_no_second_red_lamp(manifest, placed)
    manifest['entries'] = [e for e in manifest['entries'] if e['part'] != 'relocated_red_desk_lamp_arm_01']
    with pytest.raises(B.RefuseError, match='second red'):
        B.check_no_second_red_lamp(manifest, placed)
    moved = [dict(n, aabb=[[0.5, .9, -3.3], [0.7, 1.5, -3.0]]) for n in red]
    with pytest.raises(B.RefuseError, match='second instance'):
        B.identify_red_lamp(moved)


# --------------------------------------------------------------- placement
DESK = {'x': (.8, 3.2), 'z': (-3.5, -2.7), 'top': .845}


def desk_probe(x, z):
    if DESK['x'][0] <= x <= DESK['x'][1] and DESK['z'][0] <= z <= DESK['z'][1]:
        return (DESK['top'], 'Oak_desk', 1.0)
    return None


def desk_asset():
    return B.measure_desk_lamp(B.primitive_vertices(ROOT / 'web/house/assets/desk_lamp_arm_01/desk_lamp_arm_01.gltf'))


def test_desk_lamp_left_support_and_edges():
    asset = desk_asset()
    assert asset['height_above_rest'] == pytest.approx(.8046, abs=1e-3)  # real size, uniform scale 1
    plan = B.plan_desk_lamp(asset, desk_probe)
    assert plan['support_object'] == 'Oak_desk' and plan['uniform_scale'] == 1.0
    assert plan['origin_source_m'][1] == pytest.approx(.845)
    assert plan['bulb_source_m'][0] == pytest.approx(1.1) and plan['bulb_source_m'][2] == pytest.approx(-3.15)
    assert plan['origin_source_m'][0] < 2.0  # left of the monitor (x 2.0), right lamp hidden
    rel = B.light_relation(plan)
    assert rel['status'] == 'outside-shade' and rel['proposal']['light'] == 'SUB01_AuthoredLight_DeskLamp'
    with pytest.raises(B.RefuseError, match='off the desk edge'):
        B.plan_desk_lamp(asset, desk_probe, anchor=(.82, 1.35, -3.15))
    with pytest.raises(B.RefuseError, match='not one flat'):
        B.plan_desk_lamp(asset, lambda x, z: (.845 + (0.01 if x > 1.1 else 0), 'Oak_desk', 1.0))
    with pytest.raises(B.RefuseError, match='several supports'):
        B.plan_desk_lamp(asset, lambda x, z: (.845, 'Oak_desk' if x > 1.1 else 'Keyboard', 1.0))


def pendant_asset():
    # globe y .22-.53 (r .2), bulb .38-.46, rod .66-1.10 (r .005), canopy 1.11-1.17 (r .06)
    globe = cylinder_mesh(.2, .22, .53, 0, 0, 16)[0]
    bulb = cylinder_mesh(.035, .38, .46, 0, 0, 12)[0]
    rod = [v for y in [.66 + .04 * k for k in range(12)] for v in cylinder_mesh(.005, y, y + .02, 0, 0, 6)[0]]
    canopy = cylinder_mesh(.06, 1.11, 1.17, 0, 0, 16)[0]
    return B.measure_pendant([('glass', False, globe), ('globe', True, bulb), ('metal', False, rod + canopy)])


def test_pendant_canopy_on_ceiling_and_bulb_at_light():
    asset = pendant_asset()
    plan = B.plan_pendant('UpperPendant', asset, lambda x, y, z: (6.0, 'roof', -1.0))
    assert plan['origin_source_m'][1] + asset['canopy_top_y'] == pytest.approx(6.0)  # canopy touches
    assert plan['bulb_source_m'][1] == pytest.approx(4.98, abs=1e-6)
    assert B.light_relation(plan)['status'] == 'at-bulb'
    assert not plan['cable_clamped_to_minimum']
    assert B.cable_remap(1.15, asset['cable_band_y'], 0.5) == 1.15  # canopy untouched
    low = B.plan_pendant('LowerPendant', asset, lambda x, y, z: (2.85, 'ceiling', -1.0))
    assert low['cable_length_m'] >= 0.03
    with pytest.raises(B.RefuseError, match='flush'):
        B.plan_pendant('LowerPendant', asset, lambda x, y, z: (2.85 + (0.01 if x > -2 else 0), 'ceiling', -1.0))
    with pytest.raises(B.RefuseError, match='ceiling underside'):
        B.plan_pendant('LowerPendant', asset, lambda x, y, z: (2.85, 'ceiling', 1.0))


def pipe_lamp_prims():
    # native 18.3 x 36.4 x 26.2 cm (Blender X x Y x Z) == glTF x .183, height .262, depth .364
    body = [(x, y, z) for x in (-.0915, .0915) for y in (0.0, .262) for z in (-.182, .182)]
    bulb = [(x, y, z) for x in (-.03, .03) for y in (.17, .23) for z in (.10, .16)]
    switch = [(x, y, z) for x in (-.01, .01) for y in (.02, .04) for z in (-.17, -.15)]
    return [('pipe_metal', False, body), ('bulb_glass', True, bulb), ('switch', False, switch)]


def test_bedside_pipe_lamp_on_nightstand_real_dimensions():
    asset = B.measure_table_lamp(pipe_lamp_prims())
    assert asset['dimensions_m'] == pytest.approx([.183, .262, .364])
    stand = lambda x, z: (3.5, 'side_table_01', 1.0) if -3.8 <= x <= -3.3 and -3.35 <= z <= -2.85 else None
    plan = B.plan_bedside(asset, stand)
    assert plan['asset'] == 'industrial_pipe_lamp' and plan['support_object'] == 'side_table_01'
    assert plan['origin_source_m'][1] == pytest.approx(3.5)
    assert plan['origin_source_m'][0] == pytest.approx(-3.55) and plan['origin_source_m'][2] == pytest.approx(-3.1)
    assert plan['bulb_source_m'][2] == pytest.approx(-3.1 + .13)  # real offset kept, reported
    assert B.light_relation(plan)['proposal'] is not None
    with pytest.raises(B.RefuseError):  # 36.4 cm deep lamp does not fit a 30 cm top
        B.plan_bedside(asset, lambda x, z: (3.5, 'side_table_01', 1.0) if -3.25 <= z <= -2.95 else None)


def test_resolve_reviewed_directory(tmp_path):
    (tmp_path / 'industrial_pipe_lamp_1k.gltf').write_text('{}')
    assert B.resolve_asset(tmp_path).name == 'industrial_pipe_lamp_1k.gltf'
    (tmp_path / 'other.glb').write_bytes(b'')
    with pytest.raises(ValueError):
        B.resolve_asset(tmp_path)


def test_wording_modeled_not_scanned():
    for key in ('desk_lamp_arm_01', 'modern_ceiling_lamp_01', 'industrial_pipe_lamp'):
        assert B.POLYHAVEN[key]['acquisition'].startswith('modeled')
        assert B.POLYHAVEN[key]['licence'] == 'CC0 1.0'
    text = (ROOT / 'tools/build_real_lamps.py').read_text() + (ROOT / 'docs/proposed/real-lamps.md').read_text()
    for line in text.splitlines():
        low = line.lower()
        if ('scanned' in low or 'photographed' in low) and 'desk_lamp' in low:
            assert 'not' in low, line


# --------------------------------------------------------------- emission
class Sock:
    def __init__(self, v):
        self.default_value = v
        self.links = []


class Node:
    def __init__(self, kind):
        self.type = kind
        self.inputs = ({'Emission Strength': Sock(5.0), 'Emission Color': Sock((1, .9, .6, 1))} if kind == 'BSDF_PRINCIPLED'
                       else {'Strength': Sock(3.0)})


class Links(list):
    def remove(self, link):
        link[1].links.remove(link)


class Mat:
    def __init__(self):
        self.use_nodes = True
        bsdf, em = Node('BSDF_PRINCIPLED'), Node('EMISSION')
        link = ('tex', bsdf.inputs['Emission Color'])
        bsdf.inputs['Emission Color'].links.append(link)
        self.node_tree = type('T', (), {'nodes': [bsdf, em], 'links': Links([link])})()


def test_emission_zeroed_on_imported_materials():
    m = Mat()
    changed = B.zero_material_emission(m)
    bsdf, em = m.node_tree.nodes
    assert bsdf.inputs['Emission Strength'].default_value == 0.0
    assert bsdf.inputs['Emission Color'].default_value == (0, 0, 0, 1) and not bsdf.inputs['Emission Color'].links
    assert em.inputs['Strength'].default_value == 0.0
    assert 'Emission Strength' in changed


# --------------------------------------------------------------- fake unreal
class V:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = x, y, z


class FakeActor:
    def __init__(self, name, label, loc):
        self._name, self._label, self.loc = name, label, V(*loc)
        self.hidden = False
        self.temp_hidden = False
        self.tags = []
        self.comp = FakeComp()
        self.props = {'hidden': False}

    def get_name(self):
        return self._name

    def get_actor_label(self):
        return self._label

    def set_actor_label(self, label):
        self._label = label

    def get_actor_location(self):
        return self.loc

    def set_actor_location(self, loc, *a):
        self.loc = loc

    def set_actor_rotation(self, rot, *a):
        self.rot = rot

    def set_actor_scale3d(self, s):
        self.scale = s

    def get_component_by_class(self, cls):
        return self.comp

    def set_actor_hidden_in_game(self, v):
        self.props['hidden'] = v

    def set_is_temporarily_hidden_in_editor(self, v):
        self.temp_hidden = v

    def is_temporarily_hidden_in_editor(self):
        return self.temp_hidden

    def get_editor_property(self, k):
        return self.props[k]

    def set_editor_property(self, k, v):
        self.props[k] = v

    def get_path_name(self):
        return '/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.' + self._name


class FakeComp:
    def __init__(self):
        self.mesh = None
        self.props = {}

    def set_static_mesh(self, m):
        self.mesh = m

    def set_editor_property(self, k, v):
        self.props[k] = v


class FakeMIC:
    def __init__(self, path):
        self.path = path
        self.scalars = {'EmissiveStrength': 4.0, 'Roughness': .5}
        self.vectors = {'EmissiveFactor': (1, 1, 1, 1)}
        self.textures = {'BaseColorTexture': FakeTex(False), 'NormalTexture': FakeTex(True)}

    def get_path_name(self):
        return self.path

    def get_name(self):
        return self.path.rsplit('.', 1)[-1]


class FakeTex:
    def __init__(self, srgb):
        self.props = {'srgb': srgb, 'compression_settings': 'TC_NORMALMAP' if not srgb else 'TC_DEFAULT'}

    def get_editor_property(self, k):
        return self.props[k]

    def set_editor_property(self, k, v):
        self.props[k] = v
        if k == 'compression_settings':
            self.props['srgb'] = False

    def get_path_name(self):
        return '/Game/Sub01Home/RealLamps/T'


class FakeSM:
    def __init__(self, role):
        self.mat = FakeMIC(f'/Game/Sub01Home/RealLamps/{role}/MI.MI')

    def get_editor_property(self, k):
        mat = self.mat
        return [type('S', (), {'get_editor_property': lambda s, key: mat if key == 'material_interface' else 'Slot0'})()]


class FakeUnreal:
    def __init__(self, actors):
        self.actors = actors
        self.imports = []
        self.saved = 0
        u = self

        class World:
            def get_path_name(self):
                return '/Game/Sub01Home/ActualHome.ActualHome'

        class Editor:
            def get_editor_world(self):
                return World()

        class EAS:
            def get_all_level_actors(self):
                return list(u.actors)

            def spawn_actor_from_class(self, cls, loc, rot):
                a = FakeActor(f'StaticMeshActor_{len(u.actors)}', 'new', (loc.x, loc.y, loc.z))
                u.actors.append(a)
                return a

            def destroy_actor(self, a):
                u.actors.remove(a)

        class LES:
            def save_current_level(self):
                u.saved += 1
                return True

        self._subs = {'ed': Editor(), 'eas': EAS(), 'les': LES()}
        self.UnrealEditorSubsystem, self.EditorActorSubsystem, self.LevelEditorSubsystem = 'ed', 'eas', 'les'
        self.StaticMeshActor = object
        self.StaticMeshComponent = object
        self.StaticMesh = FakeSM
        self.MaterialInstanceConstant = FakeMIC
        self.TextureCompressionSettings = type('Compression', (), {'TC_DEFAULT': 'TC_DEFAULT', 'TC_NORMALMAP': 'TC_NORMALMAP'})
        self.meshes = {}

        class Task:
            def __init__(self):
                self.p = {}

            def set_editor_property(self, k, v):
                self.p[k] = v

        self.AssetImportTask = Task

        class Tools:
            def import_asset_tasks(self, tasks):
                for t in tasks:
                    role = t.p['destination_path'].rsplit('/', 1)[-1]
                    u.meshes.setdefault(role, FakeSM(role))
                    u.imports.append(role)

        self.AssetToolsHelpers = type('H', (), {'get_asset_tools': staticmethod(lambda: Tools())})

        class EAL:
            @staticmethod
            def list_assets(path, recursive=True, include_folder=False):
                role = path.rsplit('/', 1)[-1]
                return [role] if role in u.meshes else []

            @staticmethod
            def load_asset(p):
                return u.meshes[p]

            @staticmethod
            def save_loaded_asset(a):
                return True

        self.EditorAssetLibrary = EAL

        class MEL:
            get_scalar_parameter_names = staticmethod(lambda m: list(m.scalars))
            get_vector_parameter_names = staticmethod(lambda m: list(m.vectors))
            get_texture_parameter_names = staticmethod(lambda m: list(m.textures))
            get_material_instance_texture_parameter_value = staticmethod(lambda m, n: m.textures[n])

            @staticmethod
            def set_material_instance_scalar_parameter_value(m, n, v):
                m.scalars[n] = v

            @staticmethod
            def set_material_instance_vector_parameter_value(m, n, v):
                m.vectors[n] = v

        self.MaterialEditingLibrary = MEL
        self.LinearColor = lambda *c: tuple(c)
        self.Vector = V
        self.Rotator = lambda roll=0.0, pitch=0.0, yaw=0.0: type('R', (), {'yaw': yaw})()
        self.Name = str

    def get_editor_subsystem(self, key):
        return self._subs[key]


def ue(p):
    return (p[0] * 100 + 7, p[2] * 100 - 3, p[1] * 100 + 1)  # verified (x, z, y) mapping plus offset


def test_import_repairs_normal_misclassified_albedo_after_compression_reset():
    u = FakeUnreal([])
    mesh = FakeSM('DeskLamp')
    U.sanitize_materials(u, mesh, 'DeskLamp')
    albedo = mesh.mat.textures['BaseColorTexture']
    normal = mesh.mat.textures['NormalTexture']
    assert albedo.props == {'srgb': True, 'compression_settings': 'TC_DEFAULT'}
    assert normal.props == {'srgb': False, 'compression_settings': 'TC_NORMALMAP'}


def test_import_leaves_inherited_unowned_texture_immutable():
    u = FakeUnreal([])
    mesh = FakeSM('DeskLamp')
    placeholder = FakeTex(True)
    placeholder.get_path_name = lambda: '/Engine/EngineMaterials/DefaultNormal'
    before = dict(placeholder.props)
    mesh.mat.textures['InheritedNormalTexture'] = placeholder
    rows = U.sanitize_materials(u, mesh, 'DeskLamp')
    assert placeholder.props == before
    assert rows[0]['textures']['InheritedNormalTexture']['inherited_read_only']


def make_outputs(tmp_path, roles=('DeskLamp', 'LowerPendant')):
    d, _, _ = build_home()
    nodes, parts = identify(d)
    manifest = B.build_hide_manifest(parts, B.identify_red_lamp(nodes), roles)
    report = {'schema': B.SCHEMA, 'roles': {}, 'exports': {}}
    for role in roles:
        glb = tmp_path / f'SUB01_RealLamp_{role}.glb'
        glb.write_bytes(role.encode())
        report['exports'][glb.name] = hashlib.sha256(role.encode()).hexdigest()
        report['roles'][role] = {'role': role, 'asset': 'desk_lamp_arm_01' if role == 'DeskLamp' else 'modern_ceiling_lamp_01',
                                 'origin_source_m': [1.0, .845, -3.3], 'yaw_source_deg': 180.0 if role == 'DeskLamp' else 0.0,
                                 'bulb_source_m': list(B.LIGHT_SOURCE[role]), 'light_source_m': list(B.LIGHT_SOURCE[role]),
                                 'ue_glb': glb.name}
    (tmp_path / 'placement-report.json').write_text(json.dumps(report))
    (tmp_path / 'original-hide-manifest.json').write_text(json.dumps(manifest))
    actors = [FakeActor(e['ue_actor_name'], e['source_node_name'], ue(e['source_translation_m'])) for e in manifest['entries']]
    actors += [FakeActor('L_' + r, 'SUB01_AuthoredLight_' + r, ue(B.LIGHT_SOURCE[r])) for r in roles]
    actors.append(FakeActor('full-home_node_220', 'Monitor_screen', (200, -330, 116)))
    return FakeUnreal(actors), manifest


def test_unreal_import_hide_idempotent_and_restore(tmp_path):
    u, manifest = make_outputs(tmp_path)
    dry = U.run(tmp_path, dry_run=True, u=u)
    assert dry['transform']['axes'] == (0, 2, 1) and u.imports == []
    assert dry['planned']['LowerPendant']['light_status'] == 'at-bulb'
    U.run(tmp_path, u=u)
    labels = [a.get_actor_label() for a in u.actors]
    assert labels.count('SUB01_RealLamp_DeskLamp') == 1 and labels.count('SUB01_RealLamp_LowerPendant') == 1
    by = {a.get_name(): a for a in u.actors}
    assert by['full-home_node_126'].props['hidden'] and by['full-home_node_126'].temp_hidden
    assert not by['full-home_node_220'].props['hidden']  # screen untouched
    assert 'full-home_node_163' not in by  # batch never hidden (excised by root's surgery)
    mic = u.meshes['DeskLamp'].mat
    assert mic.scalars['EmissiveStrength'] == 0.0 and mic.vectors['EmissiveFactor'] == (0, 0, 0, 1)
    assert mic.textures['BaseColorTexture'].props['srgb'] and not mic.textures['NormalTexture'].props['srgb']
    pend = next(a for a in u.actors if a.get_actor_label() == 'SUB01_RealLamp_LowerPendant')
    assert pend.comp.props['cast_shadow'] is False
    n = len(u.actors)
    U.run(tmp_path, u=u)  # idempotent
    assert len(u.actors) == n
    U.run(tmp_path, restore=True, u=u)
    assert not any(a.get_actor_label().startswith('SUB01_RealLamp_') for a in u.actors)
    assert not by['full-home_node_126'].props['hidden'] and not by['full-home_node_126'].temp_hidden


def test_unreal_refuses_before_mutation(tmp_path):
    u, manifest = make_outputs(tmp_path)
    light = next(a for a in u.actors if a.get_actor_label() == 'SUB01_AuthoredLight_DeskLamp')
    light.loc = V(light.loc.x + 10, light.loc.y, light.loc.z)
    with pytest.raises(U.Refuse, match='expected'):
        U.run(tmp_path, u=u)
    assert u.imports == [] and not any(a.props['hidden'] for a in u.actors)
    u2, _ = make_outputs(tmp_path)
    u2.actors.append(FakeActor('full-home_node_126', 'Mesh_106', (0, 0, 0)))
    with pytest.raises(U.Refuse, match='exactly one'):
        U.run(tmp_path, u=u2)
    (tmp_path / 'SUB01_RealLamp_DeskLamp.glb').write_bytes(b'tampered')
    with pytest.raises(U.Refuse, match='sha256'):
        U.run(tmp_path, u=u2)


def test_unreal_manifest_screen_and_batch_refusal(tmp_path):
    u, manifest = make_outputs(tmp_path)
    m = json.loads((tmp_path / 'original-hide-manifest.json').read_text())
    m['entries'].append(dict(m['entries'][0], source_node_index=163, ue_actor_name='full-home_node_163',
                             source_node_name='house-static-batch-163', materials=['Material_8']))
    (tmp_path / 'original-hide-manifest.json').write_text(json.dumps(m))
    with pytest.raises(U.Refuse, match='hidden as a whole'):
        U.run(tmp_path, u=u)
    m['entries'][-1].update(source_node_index=220, ue_actor_name='full-home_node_220', source_node_name='Monitor_screen',
                            materials=['monitor_screen'])
    (tmp_path / 'original-hide-manifest.json').write_text(json.dumps(m))
    with pytest.raises(U.Refuse, match='protected'):
        U.run(tmp_path, u=u)
