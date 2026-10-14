"""Tests for tools/home_materials_spec.py and tools/unreal_home_materials_fix.py (fake ``unreal``)."""
import copy
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import home_materials_spec as spec  # noqa: E402
import unreal_home_materials_fix as fix  # noqa: E402

BED_GROUPS = [('CC0_queen_0', 'Original_walnut_grain_001'), ('CC0_queen_1', 'Original_teal_upholstery_001'),
              ('CC0_queen_2', 'Original_cream_upholstery_001'), ('CC0_queen_3', 'Original_linen_upholstery_001'),
              ('CC0_queen_4', 'Original_blue_fabric_upholstery_001'), ('CC0_queen_5', 'Original_oak_grain_001')]
MAT_DIR = '/Game/Sub01Home/ImportedScene/full-home/Materials/'
GLTF_PARENT = '/Interchange/gltf/MaterialInstances/MI_Default_Opaque'


# ---------------------------------------------------------------------------
# Fake unreal
# ---------------------------------------------------------------------------
class Obj:
    def __init__(self, path):
        self._path = path
        self._props = {}

    def get_path_name(self):
        return self._path

    def get_name(self):
        return self._path.rsplit('/', 1)[-1].split('.')[0].split(':')[-1]

    def get_editor_property(self, name):
        return self._props.get(name)

    def set_editor_property(self, name, value):
        self._props[name] = value


class MaterialInterface(Obj):
    pass


class Material(MaterialInterface):
    pass


class MaterialInstance(MaterialInterface):
    def __init__(self, path, parent=None):
        super().__init__(path)
        self._props['parent'] = parent
        self.scalars, self.vectors, self.textures = {}, {}, {}


class MaterialInstanceConstant(MaterialInstance):
    pass


class Texture2D(Obj):
    def __init__(self, path, size=(512, 512), srgb=True):
        super().__init__(path)
        self.size = size
        self._props['srgb'] = srgb

    def blueprint_get_size_x(self):
        return self.size[0]

    def blueprint_get_size_y(self):
        return self.size[1]


class LinearColor:
    def __init__(self, r, g, b, a=1.0):
        self.r, self.g, self.b, self.a = r, g, b, a


class Vec:
    def __init__(self, *v):
        self.x, self.y, self.z = v[:3]
        self.w = v[3] if len(v) > 3 else 0.0


class Transform:
    def __init__(self, t):
        self.translation, self.rotation, self.scale3d = Vec(*t), Vec(0, 0, 0, 1), Vec(1, 1, 1)


class StaticMeshComponent(Obj):
    def __init__(self, path, mesh, materials, location=(0, 0, 0)):
        super().__init__(path)
        self._props['static_mesh'] = mesh
        self.materials = list(materials)
        self.transform = Transform(location)
        self.collision = 'QUERY_AND_PHYSICS'
        self.set_calls = []

    def get_num_materials(self):
        return len(self.materials)

    def get_material(self, i):
        return self.materials[i]

    def get_materials(self):
        return list(self.materials)

    def set_material(self, i, m):
        self.set_calls.append((i, m))
        self.materials[i] = m

    def get_world_transform(self):
        return self.transform

    def get_collision_enabled(self):
        return self.collision

    def get_collision_profile_name(self):
        return 'Custom'


class LightComponent(Obj):
    pass


class Actor(Obj):
    def __init__(self, label, components):
        super().__init__('/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.' + label)
        self.label, self.components = label, components

    def get_actor_label(self):
        return self.label

    def get_components_by_class(self, cls):
        return [c for c in self.components if isinstance(c, cls)]


class World:
    def __init__(self, project_dir):
        self.assets, self.actors, self.saved_assets, self.level_saves = {}, [], [], 0
        self.project_dir = str(project_dir)
        self.names_override = {}


def make_unreal(world):
    u = types.ModuleType('unreal')
    for cls in (Material, MaterialInstance, MaterialInstanceConstant, Texture2D, LinearColor,
                StaticMeshComponent, LightComponent):
        setattr(u, cls.__name__, cls)
    u.MaterialFactoryNew = lambda: 'MaterialFactoryNew'
    u.MaterialInstanceConstantFactoryNew = lambda: 'MICFactory'
    u.LevelEditorSubsystem, u.EditorActorSubsystem = 'Level', 'Actor'
    u.log = lambda *_: None

    class LevelSub:
        def load_level(self, path):
            return path == fix.LEVEL_PATH

        def save_current_level(self):
            world.level_saves += 1
            return True

    class ActorSub:
        def get_all_level_actors(self):
            return list(world.actors)

    u.get_editor_subsystem = lambda kind: LevelSub() if kind == 'Level' else ActorSub()
    u.Paths = types.SimpleNamespace(project_dir=lambda: world.project_dir)
    u.load_asset = lambda path: world.assets.get(path.split('.')[0])

    class Tools:
        def create_asset(self, name, folder, cls, factory):
            asset = cls(folder + '/' + name + '.' + name) if cls is not MaterialInstanceConstant \
                else MaterialInstanceConstant(folder + '/' + name + '.' + name)
            world.assets[folder + '/' + name] = asset
            return asset

    u.AssetToolsHelpers = types.SimpleNamespace(get_asset_tools=lambda: Tools())
    u.EditorAssetLibrary = types.SimpleNamespace(save_loaded_asset=lambda a: world.saved_assets.append(a.get_path_name()) or True,
                                                 get_metadata_tag=lambda a, t: None,
                                                 set_metadata_tag=lambda a, t, v: None)
    u.SystemLibrary = types.SimpleNamespace(quit_editor=lambda: None)

    def chain(material, attr):
        out = {}
        stack = []
        m = material
        while m is not None:
            stack.append(m)
            m = m.get_editor_property('parent') if isinstance(m, MaterialInstance) else None
        for m in reversed(stack):
            out.update(getattr(m, attr, {}) or {})
        return out

    def names(attr):
        def get(material):
            if material.get_path_name() in world.names_override:
                return world.names_override[material.get_path_name()].get(attr, [])
            return sorted(chain(material, attr))
        return get

    mel = types.SimpleNamespace()
    mel.get_scalar_parameter_names = names('scalars')
    mel.get_vector_parameter_names = names('vectors')
    mel.get_texture_parameter_names = names('textures')
    mel.get_material_instance_scalar_parameter_value = lambda m, n: chain(m, 'scalars').get(n, 0.0)
    mel.get_material_instance_vector_parameter_value = lambda m, n: chain(m, 'vectors').get(n, LinearColor(0, 0, 0, 0))
    mel.get_material_instance_texture_parameter_value = lambda m, n: chain(m, 'textures').get(n)
    mel.get_material_default_scalar_parameter_value = mel.get_material_instance_scalar_parameter_value
    mel.get_material_default_vector_parameter_value = mel.get_material_instance_vector_parameter_value
    mel.get_material_default_texture_parameter_value = mel.get_material_instance_texture_parameter_value
    mel.set_material_instance_parent = lambda m, p: m.set_editor_property('parent', p)
    mel.set_material_instance_vector_parameter_value = lambda m, n, v: m.vectors.__setitem__(n, v)
    mel.set_material_instance_scalar_parameter_value = lambda m, n, v: m.scalars.__setitem__(n, v)
    mel.set_material_instance_texture_parameter_value = lambda m, n, v: m.textures.__setitem__(n, v)
    mel.update_material_instance = lambda m: None
    u.MaterialEditingLibrary = mel
    return u


def build_world(tmp_path, *, drop=None, teal_on=None, with_factor=True, duplicate=False, texture_size=(512, 512),
                sofa=False):
    world = World(tmp_path)
    (tmp_path / 'Content/Sub01Home').mkdir(parents=True)
    (tmp_path / 'Content/Sub01Home/ActualHome.umap').write_bytes(b'map')
    parent = MaterialInstanceConstant(GLTF_PARENT + '.MI_Default_Opaque')
    parent.scalars = {'RoughnessFactor': 1.0, 'MetallicFactor': 1.0, 'NormalScale': 1.0}
    if with_factor:
        parent.vectors = {'BaseColorFactor': LinearColor(1, 1, 1, 1)}
    parent.textures = {'BaseColorTexture': None, 'NormalTexture': None}
    world.assets[GLTF_PARENT] = parent
    linen = Texture2D('/Game/Sub01Home/ImportedScene/full-home/Textures/Image_14.Image_14', texture_size)
    oak = Texture2D('/Game/Sub01Home/ImportedScene/full-home/Textures/Image_15.Image_15', (512, 512))
    mats = {}
    for _, name in BED_GROUPS:
        m = MaterialInstanceConstant(MAT_DIR + name + '.' + name, parent)
        m.textures = {'BaseColorTexture': linen if 'upholstery' in name else oak}
        m.scalars = {'RoughnessFactor': 0.92}
        world.assets[MAT_DIR + name] = m
        mats[name] = m
    if duplicate:
        extra = MaterialInstanceConstant(MAT_DIR + 'Original_cream_upholstery_002.Original_cream_upholstery_002', parent)
        extra.textures = {'BaseColorTexture': linen}
        world.assets[MAT_DIR + 'Original_cream_upholstery_002'] = extra
    for i, (label, name) in enumerate(BED_GROUPS):
        if drop and drop in name:
            continue
        material = mats[name]
        if teal_on and teal_on == label:
            material = mats['Original_teal_upholstery_001']
        comp = StaticMeshComponent('/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.%s.StaticMeshComponent0' % label,
                                   Obj('/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Mesh_%d.Mesh_%d' % (i, i)),
                                   [material], location=(i * 10.0, 5.0, 1.0))
        world.actors.append(Actor(label, [comp]))
    if duplicate:
        comp = StaticMeshComponent('/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.extra.StaticMeshComponent0',
                                   Obj('/Game/M/Mesh_99.Mesh_99'), [world.assets[MAT_DIR + 'Original_cream_upholstery_002']])
        world.actors.append(Actor('house-cc0-queen-bed-extra', [comp]))
    if sofa:
        for part in ('Haven_linen', 'Haven_seams'):
            m = MaterialInstanceConstant(MAT_DIR + 'Material_%s.Material_%s' % (part, part), parent)
            m.textures = {'BaseColorTexture': Texture2D('/Game/T/%s.%s' % (part, part), (512, 512))}
            world.assets[MAT_DIR + 'Material_' + part] = m
            comp = StaticMeshComponent('/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.%s.StaticMeshComponent0' % part,
                                       Obj('/Game/M/%s.%s' % (part, part)), [m])
            world.actors.append(Actor(part, [comp]))
    world.actors.append(Actor('SUB01_Wall', [StaticMeshComponent('/Game/W.W:PersistentLevel.Wall.SMC',
                                                                 Obj('/Game/M/Wall.Wall'), [Material('/Game/M/Wall_Mat.Wall_Mat')])]))
    return world


def bed_components(world):
    return {a.label: a.components[0] for a in world.actors if a.label.startswith('CC0_queen_')}


def fingerprints(u, world):
    return {c.get_path_name(): fix.component_fingerprint(u, c) for a in world.actors for c in a.components}


# ---------------------------------------------------------------------------
# Unreal-side behaviour
# ---------------------------------------------------------------------------
def test_apply_restores_intended_bed_tints_only_on_material_slots(tmp_path):
    world = build_world(tmp_path)
    u = make_unreal(world)
    before = fingerprints(u, world)
    report = fix.apply(['bed-intended'], u=u)
    assert len(report['slot_changes']) == 4
    comps = bed_components(world)
    for label, name in BED_GROUPS:
        material = comps[label].get_material(0)
        if 'upholstery' in name:
            assert material.get_name() == fix.OWNED_PREFIX + fix.norm(name)
            assert material.get_editor_property('parent') is world.assets[MAT_DIR + name]
            want = spec.hex_to_linear('#b99845' if 'teal' in name else '#f7f4eb')
            got = material.vectors['BaseColorFactor']
            assert [got.r, got.g, got.b] == pytest.approx(list(want), abs=1e-4)
            assert set(material.vectors) == {'BaseColorFactor'} and not material.scalars and not material.textures
        else:
            assert material is world.assets[MAT_DIR + name]
    assert fingerprints(u, world) == before            # transforms, mesh, collision untouched
    assert world.level_saves == 1
    backup = json.loads((tmp_path / fix.STATE_DIR / fix.BACKUP_NAME).read_text())
    assert len(backup['slots']) == 4
    assert list((tmp_path / 'Saved/PrivateMapBackups').iterdir())


def test_second_apply_is_idempotent(tmp_path):
    world = build_world(tmp_path)
    u = make_unreal(world)
    fix.apply(['bed-intended'], u=u)
    saves, assets, backup = world.level_saves, list(world.saved_assets), \
        (tmp_path / fix.STATE_DIR / fix.BACKUP_NAME).read_text()
    calls = {k: len(c.set_calls) for k, c in bed_components(world).items()}
    report = fix.apply(['bed-intended'], u=u)
    assert report['slot_changes'] == []
    assert world.level_saves == saves and world.saved_assets == assets
    assert {k: len(c.set_calls) for k, c in bed_components(world).items()} == calls
    assert (tmp_path / fix.STATE_DIR / fix.BACKUP_NAME).read_text() == backup
    assert len(list((tmp_path / 'Saved/PrivateMapBackups').iterdir())) == 1


def test_restore_puts_back_originals(tmp_path):
    world = build_world(tmp_path)
    u = make_unreal(world)
    originals = {k: c.get_material(0) for k, c in bed_components(world).items()}
    fix.apply(['bed-intended'], u=u)
    assert fix.restore(u=u) == {'restored_slots': 4}
    assert {k: c.get_material(0) for k, c in bed_components(world).items()} == originals
    with pytest.raises(fix.MaterialFixError):
        fix.restore(u=u)  # nothing recorded any more


@pytest.mark.parametrize('kwargs, needle', [
    ({'drop': 'cream'}, 'expected 4 distinct material'),
    ({'duplicate': True}, 'expected 4 distinct material'),
    ({'teal_on': 'CC0_queen_4'}, 'slot_bound_to_other_group_material'),
    ({'texture_size': (256, 256)}, 'expected [[512, 512]'),
])
def test_preflight_refuses_and_changes_nothing(tmp_path, kwargs, needle):
    world = build_world(tmp_path, **kwargs)
    u = make_unreal(world)
    before = {k: c.get_material(0) for k, c in bed_components(world).items()}
    with pytest.raises(fix.MaterialFixError) as error:
        fix.apply(['bed-intended'], u=u)
    assert needle in str(error.value)
    assert {k: c.get_material(0) for k, c in bed_components(world).items()} == before
    assert world.level_saves == 0 and world.saved_assets == []
    assert not (tmp_path / fix.STATE_DIR / fix.BACKUP_NAME).exists()


def test_missing_parameter_fails_closed_without_owned_master(tmp_path):
    world = build_world(tmp_path, with_factor=False)
    u = make_unreal(world)
    with pytest.raises(fix.MaterialFixError) as error:
        fix.apply(['bed-intended'], u=u)
    assert 'allow-owned-master' in str(error.value)
    assert world.level_saves == 0


def test_unexpected_existing_factor_is_refused(tmp_path):
    world = build_world(tmp_path)
    world.assets[MAT_DIR + 'Original_cream_upholstery_001'].vectors = {'BaseColorFactor': LinearColor(0.2, 0.9, 0.1)}
    u = make_unreal(world)
    with pytest.raises(fix.MaterialFixError) as error:
        fix.apply(['bed-intended'], u=u)
    assert 'neither the expected' in str(error.value)


def test_sofa_preset_binds_by_actor_prefix(tmp_path):
    world = build_world(tmp_path, sofa=True)
    u = make_unreal(world)
    report = fix.apply(['sofa-intended'], u=u)
    assert len(report['slot_changes']) == 2
    linen = next(a for a in world.actors if a.label == 'Haven_linen').components[0].get_material(0)
    got = linen.vectors['BaseColorFactor']
    assert [got.r, got.g, got.b] == pytest.approx(list(spec.hex_to_linear('#737e87')), abs=1e-4)


def test_conflicting_presets_are_duplicates():
    with pytest.raises(ValueError, match='duplicate'):
        spec.plan(['bed-intended', 'bed-balanced'])


# ---------------------------------------------------------------------------
# Inventory (root's read-only report) -> mapping check
# ---------------------------------------------------------------------------
def inventory_from(world, u):
    materials, bindings = {}, []
    for actor in world.actors:
        for comp in actor.components:
            for slot, m in enumerate(comp.get_materials()):
                bindings.append({'actor': actor.label, 'component': comp.get_path_name(),
                                 'mesh': comp.get_editor_property('static_mesh').get_path_name(), 'slot': slot,
                                 'material': m.get_path_name()})
                if m.get_path_name() in materials or not isinstance(m, MaterialInstanceConstant):
                    materials.setdefault(m.get_path_name(), {'class': type(m).__name__, 'parameters': {}, 'errors': []})
                    continue
                rec = fix.live_material_record(u, m)
                materials[m.get_path_name()] = {'class': 'MaterialInstanceConstant', 'parent': rec['parent'],
                                                'parameters': rec['values'], 'errors': []}
    return {'schema': fix.INVENTORY_SCHEMA, 'level': fix.LEVEL_PATH, 'read_only': True,
            'bindings': bindings, 'materials': materials, 'lights': [], 'post_processing': []}


def test_inventory_mapping_check_ok_and_detects_swap(tmp_path):
    world = build_world(tmp_path)
    u = make_unreal(world)
    good = fix.mapping_check(fix.model_from_inventory(inventory_from(world, u)), ['bed-intended'])
    assert good['ok'], good
    assert good['headboard_material_slot_users'] == 1
    t = good['targets'][0]
    assert {m['factor_parameter'] for m in t['materials']} == {'BaseColorFactor'}
    assert {m['current_factor'][0] for m in t['materials']} == {1.0}
    swapped = build_world(tmp_path / 'b', teal_on='CC0_queen_2')
    u2 = make_unreal(swapped)
    bad = fix.mapping_check(fix.model_from_inventory(inventory_from(swapped, u2)), ['bed-intended'])
    assert not bad['ok']
    kinds = {m['kind'] for m in bad['mismatches']}
    assert 'slot_bound_to_other_group_material' in kinds
    assert 'headboard_material_on_other_bed_parts' in kinds


def test_inventory_cli_exit_codes(tmp_path, capsys):
    world = build_world(tmp_path)
    u = make_unreal(world)
    path = tmp_path / 'inventory.json'
    path.write_text(json.dumps(inventory_from(world, u), default=lambda o: None))
    assert fix.main(['--mapping-check', '--inventory', str(path)]) == 0
    broken = json.loads(path.read_text())
    broken['bindings'] = [b for b in broken['bindings'] if 'CC0_queen_3' not in b['actor']]
    path.write_text(json.dumps(broken))
    assert fix.main(['--mapping-check', '--inventory', str(path)]) == 2
    capsys.readouterr()


def test_inventory_schema_is_checked():
    with pytest.raises(fix.MaterialFixError):
        fix.model_from_inventory({'schema': 'other'})


# ---------------------------------------------------------------------------
# Pure maths and spec
# ---------------------------------------------------------------------------
def test_name_normalisation():
    assert fix.norm('Original teal upholstery.001') == 'original_teal_upholstery'
    assert fix.norm(MAT_DIR + 'Original_teal_upholstery_001.Original_teal_upholstery_001') == 'original_teal_upholstery'
    assert fix.norm('MI_Original_blue_fabric_upholstery') == 'original_blue_fabric_upholstery'
    assert fix.pick_parameter(['A', 'BaseColorFactor'], spec.PARAM_CANDIDATES['base_color_factor']) == 'BaseColorFactor'
    assert fix.pick_parameter(['Tint'], spec.PARAM_CANDIDATES['base_color_factor']) is None


def test_srgb_roundtrip_and_tint_maths():
    for v in (0.0, 0.02, 0.2, 0.5, 1.0):
        assert spec.linear_to_srgb(spec.srgb_to_linear(v)) == pytest.approx(v, abs=1e-9)
    assert spec.hex_to_linear('#b99845') == pytest.approx((0.4851, 0.3140, 0.0595), abs=1e-3)
    blue = (0.2846, 0.409, 0.6109)
    res = spec.tint_product('#f7f4eb', blue)
    assert res['linear_product (correct glTF)']['hue_deg'] == pytest.approx(211, abs=2)
    # double linearisation darkens a saturated tint
    teal = spec.tint_product('#b99845', blue)
    assert teal['tint_double_linearised']['luminance'] < teal['linear_product (correct glTF)']['luminance']


def test_balanced_fabric_moves_toward_neutral_within_albedo_bounds():
    blue, p99, _ = spec._linen_stats()
    before = spec.mul(spec.hex_to_linear('#f7f4eb'), blue)
    factor, after = spec.tint_factor(blue, '#f7f4eb', 0.62, p99)
    assert spec.chroma(after) < spec.chroma(before) / 4
    assert spec.chroma(after) == pytest.approx(spec.chroma(spec.hex_to_linear('#f7f4eb')), abs=1e-3)
    assert spec.ALBEDO_MIN <= spec.luminance(after) <= spec.ALBEDO_MAX
    assert max(f * p for f, p in zip(factor, p99)) <= spec.ALBEDO_MAX + 1e-6
    # an unreachable target is capped uniformly (hue preserved)
    capped, out = spec.tint_factor(blue, '#f7f4eb', 0.95, p99)
    assert max(f * p for f, p in zip(capped, p99)) == pytest.approx(spec.ALBEDO_MAX, abs=1e-4)
    assert spec.hue_sat(out)[0] == pytest.approx(spec.hue_sat(spec.hex_to_linear('#f7f4eb'))[0], abs=1)


def test_all_preset_predictions_within_physical_ranges():
    for name in spec.PRESETS:
        for target in spec.plan([name])['targets']:
            assert spec.validate_target(target) == [], (name, target['id'])


def test_texture_colour_space_rules():
    assert spec.TEXTURE_SRGB == {'base_color': True, 'normal': False, 'roughness': False,
                                 'metallic_roughness': False}
    u = types.SimpleNamespace()
    good = {'base_color': Texture2D('/T/a.a', srgb=True), 'normal': Texture2D('/T/n.n', srgb=False)}
    assert fix.ensure_texture_colour_spaces(u, good) == []
    bad = {'normal': Texture2D('/T/n.n', srgb=True), 'roughness': Texture2D('/T/r.r', srgb=True)}
    problems = fix.ensure_texture_colour_spaces(u, bad)
    assert len(problems) == 2 and all('expected False' in p for p in problems)


def test_wood_uv_scale_maths():
    assert spec.cm_per_repeat(coverage_m=1.2, repeat=1.0) == pytest.approx(120.0)
    assert spec.cm_per_repeat(coverage_m=1.2, repeat=2.0) == pytest.approx(60.0)
    assert spec.cm_per_repeat(uv_per_metre=0.99 / 1.83) == pytest.approx(184.8, abs=0.1)
    assert spec.plank_width_cm([0, 80, 160, 240], 1024, 1.2) == pytest.approx(9.375)
    assert spec.uv_tiling_for_plank(9.5, 14.25) == pytest.approx(2 / 3)
    seams, n = spec.plank_seams(spec.ASSETS / 'home_oak_floor/diff.jpg')
    width = spec.plank_width_cm(seams, n, 1.2)
    assert 6.0 < width < 20.0


# ---------------------------------------------------------------------------
# Real repo data
# ---------------------------------------------------------------------------
BED_GLB = spec.ASSETS / 'cc0-queen-bed/queen-bed.glb'


@pytest.mark.skipif(not BED_GLB.is_file(), reason='repo queen-bed GLB absent')
def test_real_bed_glb_audit_and_groups():
    audit = spec.audit_glb(BED_GLB)
    names = [m['name'] for m in audit['materials']]
    assert names == ['Original walnut grain', 'Original teal upholstery', 'Original cream upholstery',
                     'Original linen upholstery', 'Original blue_fabric upholstery', 'Original oak grain']
    geo = spec.bed_group_geometry()
    head = geo['CC0_queen_1']
    assert head['material'] == 'Original teal upholstery'
    assert head['bounds_max_m'][2] - head['bounds_min_m'][2] < 0.1   # a thin panel: the headboard
    assert head['bounds_max_m'][1] > 1.2
    assert sum(v['area_share'] for v in geo.values() if v['area_share']) == pytest.approx(1.0, abs=0.01)
    assert all(m['effective_mean_albedo']['luminance'] > 0 for m in audit['materials'])


@pytest.mark.skipif(not (ROOT / 'docs/proposed/home-materials-audit.json').is_file(), reason='audit not generated')
def test_committed_audit_is_small_and_honest():
    path = ROOT / 'docs/proposed/home-materials-audit.json'
    assert path.stat().st_size < 400_000
    data = json.loads(path.read_text())
    assert 'No visual comparison' in data['scope']


# ---------------------------------------------------------------------------
# Widened presets (increment 3)
# ---------------------------------------------------------------------------
def add_material_actor(world, label, name, *, vectors=None, scalars=None, texture_size=(1024, 1024)):
    parent = world.assets[GLTF_PARENT]
    m = MaterialInstanceConstant(MAT_DIR + name + '.' + name, parent)
    m.vectors = dict(vectors or {})
    m.scalars = dict(scalars or {})
    m.textures = {'BaseColorTexture': Texture2D('/Game/T/%s_tex.%s_tex' % (name, name), texture_size)}
    world.assets[MAT_DIR + name] = m
    comp = StaticMeshComponent('/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.%s.StaticMeshComponent0' % label,
                               Obj('/Game/M/%s.%s' % (label, label)), [m], location=(1.0, 2.0, 3.0))
    world.actors.append(Actor(label, [comp]))
    return comp


def test_metals_preset_binarises_only_enumerated_metallic(tmp_path):
    world = build_world(tmp_path)
    comps = {
        'kb': add_material_actor(world, 'house-keyboard', 'plastic_black', scalars={'MetallicFactor': 1.0}),
        'pc': add_material_actor(world, 'esp1', 'Charcoal_fine_textured_powdercoat', scalars={'MetallicFactor': 0.25}),
    }
    for i, name in enumerate(['Satin_galvanized_steel', 'Blackened_steel_mounting_hardware', 'Satin_champagne_bronze']):
        comps[name] = add_material_actor(world, 'esp_s%d' % i, name, scalars={'MetallicFactor': [0.78, 0.75, 0.8][i]})
    u = make_unreal(world)
    before = fingerprints(u, world)
    report = fix.apply(['metal-keyboard', 'metal-espresso'], u=u)
    assert len(report['slot_changes']) == 5
    assert comps['kb'].get_material(0).scalars == {'MetallicFactor': 0.0}
    assert comps['Satin_galvanized_steel'].get_material(0).scalars == {'MetallicFactor': 1.0}
    assert not comps['kb'].get_material(0).vectors       # no base-colour change for scalar-only targets
    assert fingerprints(u, world) == before
    assert fix.apply(['metal-keyboard', 'metal-espresso'], u=u)['slot_changes'] == []


def test_scalar_target_refuses_unexpected_current_value(tmp_path):
    world = build_world(tmp_path)
    add_material_actor(world, 'bedwood0', 'Original_walnut_grain_002', scalars={'RoughnessFactor': 0.3})
    world.actors = [a for a in world.actors if a.label not in ('CC0_queen_0',)]
    u = make_unreal(world)
    with pytest.raises(fix.MaterialFixError) as error:
        fix.apply(['bed-wood-roughness'], u=u)
    assert 'not the expected' in str(error.value) or 'expected 2 distinct' in str(error.value)
    assert world.level_saves == 0


def test_bed_wood_roughness(tmp_path):
    world = build_world(tmp_path)
    for name in ('Original_walnut_grain_001', 'Original_oak_grain_001'):
        world.assets[MAT_DIR + name].scalars = {'RoughnessFactor': 0.82}
    u = make_unreal(world)
    report = fix.apply(['bed-wood-roughness'], u=u)
    assert len(report['slot_changes']) == 2
    comp = bed_components(world)['CC0_queen_5']
    assert comp.get_material(0).scalars == {'RoughnessFactor': 0.5}


def test_darkwood_matched_by_exact_factor_fingerprint(tmp_path):
    world = build_world(tmp_path)
    tint = spec.hex_to_linear('#c5aa83')
    comp = add_material_actor(world, 'house-static-12', 'Material_012', vectors={'BaseColorFactor': LinearColor(*tint)})
    add_material_actor(world, 'house-static-13', 'Material_013',
                       vectors={'BaseColorFactor': LinearColor(0.5, 0.5, 0.5)})   # not darkwood: untouched
    u = make_unreal(world)
    report = fix.apply(['darkwood-albedo'], u=u)
    assert len(report['slot_changes']) == 1
    got = comp.get_material(0).vectors['BaseColorFactor']
    target = spec.plan(['darkwood-albedo'])['targets'][0]
    assert [got.r, got.g, got.b] == pytest.approx(target['factor'], abs=1e-4)
    # a second material carrying the same fingerprint makes it ambiguous
    world2 = build_world(tmp_path / 'b')
    add_material_actor(world2, 'a1', 'Material_020', vectors={'BaseColorFactor': LinearColor(*tint)})
    add_material_actor(world2, 'a2', 'Material_021', vectors={'BaseColorFactor': LinearColor(*tint)})
    with pytest.raises(fix.MaterialFixError, match='expected 1 distinct'):
        fix.apply(['darkwood-albedo'], u=make_unreal(world2))


def test_darkwood_prediction_in_dark_wood_range():
    target = spec.plan(['darkwood-albedo'])['targets'][0]
    assert target['predicted']['before']['luminance'] < spec.ALBEDO_MIN
    assert 0.04 <= target['predicted']['after']['luminance'] <= 0.10
    assert target['predicted']['after']['hue_deg'] == pytest.approx(target['predicted']['before']['hue_deg'], abs=1.5)


def test_non_bed_preset_not_blocked_by_bed_mismatch_but_bed_preset_is(tmp_path):
    world = build_world(tmp_path, teal_on='CC0_queen_2')
    add_material_actor(world, 'house-keyboard', 'plastic_black', scalars={'MetallicFactor': 1.0})
    u = make_unreal(world)
    model = fix.model_from_live(u, u.get_editor_subsystem('Actor'))
    kb = fix.mapping_check(model, ['metal-keyboard'])
    assert kb['mismatches'] and not kb['bed_mapping_required']
    assert kb['ok'] and [t['id'] for t in kb['targets']] == ['metal-keyboard-plastic']
    assert not fix.mapping_check(model, ['bed-intended'])['ok']
