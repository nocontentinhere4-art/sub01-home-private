"""Leveled Tokyo backdrop: projection math, image checks, night grade, editor script with fake unreal."""
import json
import math
import struct
import sys
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import exterior_backdrop_geometry as geo  # noqa: E402
import reference_home_lighting as rhl  # noqa: E402
import unreal_exterior_backdrop_fix as fix  # noqa: E402

PANORAMA = ROOT / 'web/house/assets/tokyo-residential/residential-4096.webp'


# ------------------------------------------------------------------ projection
@pytest.mark.parametrize('yaw', range(0, 361, 15))
def test_horizon_is_horizontal_for_every_yaw(yaw):
    for az in range(0, 360, 10):
        d = (math.cos(math.radians(az)), math.sin(math.radians(az)), 0.0)
        assert geo.equirect_uv(d, yaw_deg=yaw)[1] == pytest.approx(0.5, abs=1e-12)


def test_horizon_row_is_at_eye_height_from_any_standing_position():
    for eye_xy in ((0, 0), (200, 725), (-300, 400)):
        eye = (eye_xy[0], eye_xy[1], geo.EYE_HEIGHT_CM)
        for far in ((5000, 0), (0, -8000), (-3000, 3000)):
            at_eye = (eye[0] + far[0], eye[1] + far[1], geo.EYE_HEIGHT_CM)
            assert geo.uv_of_world_point(at_eye, eye)[1] == pytest.approx(0.5)
            above = (at_eye[0], at_eye[1], 1000.0)
            below = (at_eye[0], at_eye[1], 0.0)
            assert geo.uv_of_world_point(above, eye)[1] < 0.5 < geo.uv_of_world_point(below, eye)[1]


def test_zenith_nadir_and_inverse_roundtrip():
    assert geo.equirect_uv((0, 0, 1))[1] == pytest.approx(0.0)
    assert geo.equirect_uv((0, 0, -1))[1] == pytest.approx(1.0)
    for u in (0.05, 0.3, 0.5, 0.77, 0.95):
        for v in (0.2, 0.5, 0.8):
            assert geo.equirect_uv(geo.direction_for_uv(u, v, yaw_deg=37), yaw_deg=37) == pytest.approx((u, v))


def test_photo_centre_faces_yaw_and_turning_right_pans_right():
    u0, _ = geo.equirect_uv((0, 1, 0), yaw_deg=90)  # +Y
    assert u0 == pytest.approx(0.5)
    u1, _ = geo.equirect_uv((math.cos(math.radians(100)), math.sin(math.radians(100)), 0), yaw_deg=90)
    assert u1 > u0  # not mirrored


def test_photo_level_corrections_default_to_identity_and_can_tilt():
    d = (0.3, -0.8, 0.2)
    assert geo.equirect_uv(d, pitch_fix_deg=0, roll_fix_deg=0) == geo.equirect_uv(d)
    assert geo.equirect_uv((1, 0, 0), yaw_deg=0, pitch_fix_deg=5)[1] != pytest.approx(0.5)


def test_hlsl_matches_python_twin_structurally():
    for name in geo.CUSTOM_INPUTS:
        assert name in geo.HLSL
    assert 'normalize(-CamVec)' in geo.HLSL and 'return float2(u, v);' in geo.HLSL


def test_root_cause_python_rotator_positional_is_pitch_and_tilts_the_sphere():
    # tools/unreal_home_exterior.py:80 u.Rotator(0, -90, 0) -> roll 0, pitch -90, yaw 0.
    rot = geo.python_rotator_positional(0, -90, 0)
    assert rot == {'roll': 0.0, 'pitch': -90.0, 'yaw': 0.0}
    assert geo.equator_tilt_deg(rot) == pytest.approx(90.0)
    assert geo.equator_tilt_deg(geo.leveled_rotation()) == pytest.approx(0.0, abs=1e-9)
    for yaw in range(0, 360, 30):
        assert geo.equator_tilt_deg({'pitch': 0, 'yaw': yaw, 'roll': 0}) == pytest.approx(0.0, abs=1e-9)
    assert fix.plan()['rotation'] == {'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0}


# ------------------------------------------------------------------ image
def _png(path, w, h):
    ihdr = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
    chunk = struct.pack('>I', 13) + b'IHDR' + ihdr + struct.pack('>I', zlib.crc32(b'IHDR' + ihdr))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk)
    return path


def test_actual_panorama_header_is_2_to_1():
    assert geo.image_size(PANORAMA) == (4096, 2048)
    assert geo.require_equirect(4096, 2048)['aspect'] == 2.0


@pytest.mark.parametrize('size', [(3000, 2000), (4096, 2047), (1920, 1080), (512, 256), (0, 0)])
def test_sphere_mode_refuses_non_equirect(size):
    with pytest.raises(ValueError):
        geo.require_equirect(*size)


def test_png_header_reader(tmp_path):
    assert geo.image_size(_png(tmp_path / 'a.png', 4096, 2048)) == (4096, 2048)
    (tmp_path / 'x.bin').write_bytes(b'nope' * 20)
    with pytest.raises(ValueError):
        geo.image_size(tmp_path / 'x.bin')


# ------------------------------------------------------------------ grade
def _luma(rgb):
    return sum(rgb[i] * geo.LUMA[i] for i in range(3))


def _photo_samples():
    try:
        from PIL import Image
        im = Image.open(PANORAMA).convert('RGB').resize((64, 32))
        raw = im.tobytes()
        return [tuple(raw[i + k] / 255.0 for k in range(3)) for i in range(0, len(raw), 3)]
    except Exception:  # PIL optional
        return [(0.55, 0.7, 0.95), (0.8, 0.75, 0.65), (0.4, 0.38, 0.33), (0.9, 0.9, 0.88), (0.2, 0.3, 0.15)]


def test_night_is_darker_and_bluer_than_day():
    day, night = geo.blended_grade(1, 0), geo.blended_grade(0, 0)
    samples = _photo_samples()
    d = [geo.grade_rgb(c, day) for c in samples]
    n = [geo.grade_rgb(c, night) for c in samples]
    assert sum(map(_luma, n)) < 0.15 * sum(map(_luma, d))
    blue = lambda rows: sum(r[2] for r in rows) / sum(r[0] + r[1] + r[2] for r in rows)  # noqa: E731
    assert blue(n) > blue(d) + 0.05
    assert all(geo.grade_rgb(c, night)[2] >= geo.grade_rgb(c, night)[0] for c in samples)


def test_day_grade_is_the_unmodified_photo_and_sunset_is_warm():
    for c in _photo_samples()[:50]:
        assert geo.grade_rgb(c, geo.blended_grade(1, 0)) == pytest.approx(c)
    gold = geo.grade_rgb((0.6, 0.6, 0.6), geo.blended_grade(1, 1))
    assert gold[0] > gold[2]


def test_preset_factors_tie_to_lighting_presets():
    assert geo.preset_factors('night')['Daylight'] == 0.0
    assert geo.preset_factors('afternoon')['Daylight'] == pytest.approx(1.0)
    sunset = geo.preset_factors('sunset')
    assert 0 < sunset['GoldenWeight'] <= sunset['Daylight'] <= 1
    for preset in ('night', 'sunset', 'day'):
        data = rhl.plan(preset)
        f = geo.preset_factors(preset)
        assert data['exterior']['leveled_factors'] == {'Daylight': pytest.approx(f['Daylight']),
                                                       'GoldenWeight': pytest.approx(f['GoldenWeight'])}


def test_native_hour_factors_night_and_noon():
    assert geo.native_hour_factors(21) == (0.0, 0.0)
    assert geo.native_hour_factors(2) == (0.0, 0.0)
    assert geo.native_hour_factors(12)[0] == pytest.approx(1.0)
    assert 0 < geo.native_hour_factors(18)[1] < geo.native_hour_factors(18)[0]


def test_native_hook_patch_targets_roots_file_once_and_is_idempotent():
    text = (ROOT / geo.NATIVE_FILE).read_text()
    patched = geo.patch_native_view_settings(text)
    assert patched.count(geo.NATIVE_MARKER) == 1 and patched.count('KismetMaterialLibrary.h') == 1
    assert geo.patch_native_view_settings(patched) == patched
    assert geo.COLLECTION_PATH in patched and 'Daylight' in patched
    with pytest.raises(ValueError):
        geo.patch_native_view_settings(text.replace(geo.NATIVE_HOUR_ANCHOR, ''))
    assert geo.native_patch_diff(ROOT).startswith('--- a/' + geo.NATIVE_FILE)


# ------------------------------------------------------------------ courtyard
# tools/unreal_extend_private_entry.py rows (centre, size) in cm.
COURTYARD = [([200, 725, 0], [250, 290, 5]), ([77.5, 725, 57.5], [5, 290, 110]),
             ([322.5, 725, 57.5], [5, 290, 110]), ([200, 867.5, 57.5], [250, 5, 110])]


def _boxes(rows):
    return [{'min': [c[i] - s[i] / 2 for i in range(3)], 'max': [c[i] + s[i] / 2 for i in range(3)]} for c, s in rows]


def test_finite_courtyard_is_far_inside_the_backdrop():
    ok, worst = geo.courtyard_clear(_boxes(COURTYARD))
    assert ok and worst < 1000
    assert not geo.courtyard_clear(_boxes([([199500, 0, 0], [10, 10, 10])]))[0]


# ------------------------------------------------------------------ fake unreal
class Obj:
    def __init__(self, *a, **k):
        self.props = dict(k)

    def set_editor_property(self, name, value):
        self.props[name] = value

    def get_editor_property(self, name):
        return self.props.get(name)

    def get_path_name(self):
        return self.props.get('path', 'none')


class V:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = x, y, z


class R:
    def __init__(self, roll=0.0, pitch=0.0, yaw=0.0):
        self.roll, self.pitch, self.yaw = roll, pitch, yaw


class Mesh:
    def __init__(self, log, collision='NO', lo=(-50, -50, -50), hi=(50, 50, 50), offset=(0, 0, 0)):
        self.log, self.collision, self.material = log, collision, None
        self.lo, self.hi, self.offset = V(*lo), V(*hi), offset
        box = SimpleNamespace(min=V(*lo), max=V(*hi))
        self.static_mesh = SimpleNamespace(get_bounding_box=lambda: box)

    def get_collision_enabled(self):
        return self.collision

    def get_editor_property(self, name):
        return getattr(self, name)

    def get_material(self, i):
        return self.material

    def set_material(self, i, m):
        self.log.append('set_material')
        self.material = m

    def get_local_bounds(self):
        return self.lo, self.hi

    def get_world_transform(self):
        o = self.offset
        return SimpleNamespace(transform_location=lambda p: V(p.x + o[0], p.y + o[1], p.z + o[2]))


class Actor:
    def __init__(self, label, log, mesh=None, location=(0, 0, 165), rotation=(0, -90, 0), scale=4000.0):
        self.label, self.log = label, log
        self.mesh = mesh or Mesh(log)
        self.location, self.rotation, self.scale = V(*location), R(*rotation), V(scale, scale, scale)

    def get_actor_label(self):
        return self.label

    def get_components_by_class(self, cls):
        return [self.mesh]

    def get_component_by_class(self, cls):
        return self.mesh

    def get_actor_location(self):
        return self.location

    def get_actor_rotation(self):
        return self.rotation

    def get_actor_scale3d(self):
        return self.scale

    def set_actor_rotation(self, rot, teleport):
        self.log.append('set_actor_rotation')
        self.rotation = rot


def make_unreal(tmp_path, actors, texture_size=(4096, 2048), texture=True):
    log = []
    store = {}
    names = {}

    def cls(name):
        return type(name, (Obj,), {})

    u = SimpleNamespace(**{n: cls(n) for n in fix.REQUIRED_CLASSES})
    u.MaterialExpressionEyeAdaptationInverse = cls('MaterialExpressionEyeAdaptationInverse')
    u.StaticMeshComponent = cls('StaticMeshComponent')
    u.CollisionEnabled = SimpleNamespace(NO_COLLISION='NO')
    for enum in ('CustomMaterialOutputType', 'MaterialShadingModel', 'MaterialSamplerType',
                 'TextureMipValueMode', 'MaterialProperty'):
        setattr(u, enum, SimpleNamespace(**{k: k for k in ('CMOT_FLOAT2', 'MSM_UNLIT', 'SAMPLERTYPE_COLOR',
                                                           'TMVM_MIP_LEVEL', 'MP_EMISSIVE_COLOR')}))
    if texture:
        tex = u.Texture2D(path=fix.EXTERIOR_TEXTURE)
        tex.blueprint_get_size_x = lambda: texture_size[0]
        tex.blueprint_get_size_y = lambda: texture_size[1]
        store[fix.EXTERIOR_TEXTURE] = tex
    u.load_asset = lambda path: store.get(path)
    u.Rotator = R
    u.Vector = V
    u.LinearColor = lambda r, g, b, a=1.0: SimpleNamespace(r=r, g=g, b=b, a=a)
    u.Paths = SimpleNamespace(project_dir=lambda: str(tmp_path))
    u.log = lambda message: log.append('log')

    def create_asset(name, folder, klass, factory):
        log.append('create:' + name)
        asset = klass(path=folder + '/' + name + '.' + name)
        store[folder + '/' + name] = asset
        return asset
    u.AssetToolsHelpers = SimpleNamespace(get_asset_tools=lambda: SimpleNamespace(create_asset=create_asset))
    meta = {}
    u.EditorAssetLibrary = SimpleNamespace(
        save_loaded_asset=lambda a: log.append('save_asset'),
        get_metadata_tag=lambda a, t: meta.get((id(a), t)),
        set_metadata_tag=lambda a, t, v: meta.__setitem__((id(a), t), v))
    params = {}

    def expr(material, klass, x, y):
        log.append('expr')
        return klass()
    u.MaterialEditingLibrary = SimpleNamespace(
        delete_all_material_expressions=lambda m: log.append('graph_reset'),
        create_material_expression=expr,
        connect_material_expressions=lambda a, o, b, i: True,
        connect_material_property=lambda a, o, p: True,
        recompile_material=lambda m: log.append('recompile'),
        set_material_instance_parent=lambda i, p: i.set_editor_property('parent', p),
        get_material_instance_scalar_parameter_value=lambda i, n: params.get(n, -1.0),
        set_material_instance_scalar_parameter_value=lambda i, n, v: params.__setitem__(n, v),
        get_material_instance_vector_parameter_value=lambda i, n: params.get(n, SimpleNamespace(r=-1, g=-1, b=-1)),
        set_material_instance_vector_parameter_value=lambda i, n, v: params.__setitem__(n, v))
    level = SimpleNamespace(load_level=lambda p: True, save_current_level=lambda: log.append('save_level') or True)
    u.LevelEditorSubsystem = 'level'
    u.EditorActorSubsystem = 'actors'
    subsystem = SimpleNamespace(get_all_level_actors=lambda: list(actors))
    u.get_editor_subsystem = lambda name: level if name == 'level' else subsystem
    u.CollectionScalarParameter = lambda: Obj(default_value=0.0)
    u.CustomInput = Obj
    u.params = params
    return u, log


def scene(log):
    return [Actor(fix.EXTERIOR_LABEL, log),
            Actor(fix.COURTYARD_PREFIX + 'Support', log,
                  mesh=Mesh(log, 'QP', lo=(-125, -145, -2.5), hi=(125, 145, 2.5), offset=(200, 725, 0)))]


def run(u, **k):
    return fix.run('night', u=u, backup=False, **k)


def test_happy_path_levels_rotation_and_assigns_owned_instance(tmp_path):
    log = []
    actors = scene(log)
    u, ulog = make_unreal(tmp_path, actors)
    report = run(u)
    backdrop = actors[0]
    assert (backdrop.rotation.pitch, backdrop.rotation.yaw, backdrop.rotation.roll) == (0, 0, 0)
    assert backdrop.mesh.material.get_path_name().split('.')[0] == geo.INSTANCE_PATH
    assert report['actor_changed'] and report['graph_rebuilt'] and report['exposure_lock']
    assert report['before']['rotation']['pitch'] == -90
    assert report['courtyard_boxes'] == 1 and 'save_level' in ulog
    assert u.params['NightBrightness'] == geo.GRADE_NIGHT['brightness']
    collection = u.load_asset(geo.COLLECTION_PATH)
    values = {p.get_editor_property('parameter_name'): p.get_editor_property('default_value')
              for p in collection.get_editor_property('scalar_parameters')}
    assert values == {'Daylight': 0.0, 'GoldenWeight': 0.0}
    assert json.loads((tmp_path / fix.REPORT_NAME).read_text())['visual_match_claimed'] is False


def test_second_run_is_idempotent(tmp_path):
    log = []
    actors = scene(log)
    u, ulog = make_unreal(tmp_path, actors)
    run(u)
    ulog.clear()
    log.clear()
    report = run(u)
    assert not report['actor_changed'] and not report['graph_rebuilt']
    assert not report['instance_changed'] and not report['collection_changed']
    assert log == [] and 'save_level' not in ulog and not any(e.startswith('create:') for e in ulog)
    assert 'graph_reset' not in ulog and 'save_asset' not in ulog


def test_preset_switch_only_changes_collection(tmp_path):
    log = []
    actors = scene(log)
    u, ulog = make_unreal(tmp_path, actors)
    run(u)
    ulog.clear()
    report = fix.run('afternoon', u=u, backup=False)
    assert report['collection_changed'] and not report['actor_changed'] and not report['graph_rebuilt']
    assert fix.set_time_of_day(u, 0.0, 0.0) is True


@pytest.mark.parametrize('case', ['missing_actor', 'duplicate_actor', 'missing_texture', 'not_2_to_1',
                                  'collision', 'courtyard_outside', 'no_custom_node'])
def test_refuses_without_mutation(tmp_path, case):
    log = []
    actors = scene(log)
    kwargs = {}
    if case == 'missing_actor':
        actors = actors[1:]
    elif case == 'duplicate_actor':
        actors.append(Actor(fix.EXTERIOR_LABEL, log))
    elif case == 'missing_texture':
        kwargs['texture'] = False
    elif case == 'not_2_to_1':
        kwargs['texture_size'] = (3000, 2000)
    elif case == 'collision':
        actors[0].mesh.collision = 'QP'
    elif case == 'courtyard_outside':
        actors[1].mesh.offset = (199900, 0, 0)
    u, ulog = make_unreal(tmp_path, actors, **kwargs)
    if case == 'no_custom_node':
        del u.MaterialExpressionCustom
    with pytest.raises(fix.BackdropFixError):
        run(u)
    assert log == []
    assert not [e for e in ulog if e not in ('log',)]
    assert not (tmp_path / fix.REPORT_NAME).exists()


def test_source_png_size_must_match_texture(tmp_path):
    (tmp_path / 'SourceAssets').mkdir()
    _png(tmp_path / fix.SOURCE_IMAGE, 2048, 1024)
    log = []
    u, ulog = make_unreal(tmp_path, scene(log))
    with pytest.raises(fix.BackdropFixError, match='differs'):
        run(u)
    assert log == []


def test_restore_puts_back_recorded_rotation_and_material(tmp_path):
    log = []
    actors = scene(log)
    u, _ = make_unreal(tmp_path, actors)
    original = Obj(path='/Game/Sub01Home/Environment/M_Sub01ActualTokyoBackground.M_Sub01ActualTokyoBackground')
    actors[0].mesh.material = original
    u_load = u.load_asset
    u.load_asset = lambda p: original if p == original.get_path_name() else u_load(p)
    run(u)
    fix.restore(u=u)
    assert actors[0].rotation.pitch == -90 and actors[0].mesh.material is original


def test_dry_run_plan_is_json():
    data = fix.plan('night')
    json.dumps(data)
    assert data['factors']['Daylight'] == 0 and data['scalars']['HorizonV'] == 0.5
    assert data['night_window_lights'].startswith('none')
