"""Pure tests for tools/reference_lighting_inventory_correction.py on the REAL inventory file.

No Unreal or renderer is launched; the editor path uses a fake ``unreal``.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import reference_lighting_inventory_correction as lc  # noqa: E402

INVENTORY = ROOT / 'docs/proposed/actual-home-material-bindings-20261014.json'


# ------------------------------------------------------------ real inventory
def test_real_inventory_parses_six_lights_and_no_post_process():
    inv = lc.load_inventory(INVENTORY)
    assert set(inv['lights']) == set(lc.TARGET_TEMPERATURE_K)
    assert inv['post_processing'] == []
    sun = inv['lights']['SUB01_AuthoredLight_SUN']
    assert sun['class'] == 'DirectionalLightComponent' and sun['units'] == 'LUX'
    assert sun['intensity'] == pytest.approx(3.09, abs=0.01)
    assert sun['light_color'] == (255, 210, 161, 255) and sun['use_temperature'] is False
    assert inv['lights']['SUB01_AuthoredLight_LowerPendant']['class'] == 'SpotLightComponent'
    assert all(l['units'] == 'CANDELAS' for k, l in inv['lights'].items() if not k.endswith('SUN'))


def test_stored_colours_are_authored_linear_bytes_so_ue_decodes_srgb_twice():
    from unreal_home_lights import authored_lights, srgb_hex_linear
    inv = lc.load_inventory(INVENTORY)
    for row in authored_lights(11, True):
        stored = inv['lights'][lc.LABEL_PREFIX + row['name']]['light_color'][:3]
        assert stored == tuple(round(v * 255) for v in srgb_hex_linear(row['color']))


def test_diagnosis_effective_colour_warmer_than_authored_and_targets_in_band():
    diag = lc.diagnose(lc.load_inventory(INVENTORY))
    rows = {r['actor']: r for r in diag['lights']}
    sun = rows['SUB01_AuthoredLight_SUN']
    assert sun['double_srgb_decode'] and sun['effective_cct_k'] < 4200 < 4800 < sun['authored_cct_k']
    assert rows['SUB01_AuthoredLight_BedLamp']['effective_cct_k'] < 2400  # deeper than any warm-white lamp
    assert 5500 <= lc.TARGET_TEMPERATURE_K['SUB01_AuthoredLight_SUN'] <= 6500
    assert all(2700 <= k <= 3000 for label, k in lc.TARGET_TEMPERATURE_K.items() if not label.endswith('SUN'))
    assert diag['findings']['post_process_volumes'] == 0
    assert diag['findings']['sun_stored_hex'] == '#ffd2a1'
    low, high = diag['findings']['sun_effective_below_daylight_k']
    assert 1400 < low < high < 2700
    assert diag['findings']['sun_vs_physical_factor'] > 10000


def test_exposure_estimates_cover_bounds_and_show_inverted_balance():
    table = lc.exposure_table()
    day_shade = table['day: sky-lit wall, ~1/10 of the sun patch']['ev100']
    night_wall = table['night: wall 2.5 m from a 10 cd pendant (1.6 lux)']['ev100']
    assert night_wall > day_shade  # lamp-lit night brighter than sky-lit day on this scale
    assert lc.EXPOSURE_MIN_EV100 <= day_shade <= lc.EXPOSURE_MAX_EV100
    assert lc.EXPOSURE_MIN_EV100 <= night_wall <= lc.EXPOSURE_MAX_EV100
    assert lc.ev100(12.5 / 100) == pytest.approx(0.0)


def test_plan_is_colour_only_and_white_balance_between_sun_and_sky():
    data = lc.plan(lc.load_inventory(INVENTORY))
    json.dumps(data)
    assert 'intensity' in data['unchanged_light_properties']
    assert all(row['to']['light_color'] == [255, 255, 255, 255] and row['to']['use_temperature']
               for row in data['lights'].values())
    props = {r['property']: r['value'] for r in data['post_process']['settings']}
    assert props['white_temp'] == lc.TARGET_TEMPERATURE_K['SUB01_AuthoredLight_SUN']  # key renders neutral
    assert 'auto_exposure_bias' not in props and data['post_process']['label'] == 'SUB01_ReferencePost'
    assert data['order'][0].endswith('unreal_exterior_backdrop_fix.py') and data['visual_match_claimed'] is False


def test_shots_reuse_materials_doc_positions_and_look_toward_targets():
    rows = {r['shot']: r for r in lc.shots()}
    assert set(rows) == {'bed close-up', 'sofa', 'desk + wood floor', 'kitchen'}
    desk = rows['desk + wood floor']['rotation_deg']
    assert desk['yaw'] == pytest.approx(-90) and desk['pitch'] < 0
    assert rows['sofa']['rotation_deg']['yaw'] == pytest.approx(180)


def test_unexpected_inventory_light_refused(tmp_path):
    data = json.loads(INVENTORY.read_text())
    data['lights'].append(dict(data['lights'][1], actor='Stray_PointLight'))
    path = tmp_path / 'inv.json'
    path.write_text(json.dumps(data))
    with pytest.raises(lc.CorrectionRefused):
        lc.plan(lc.load_inventory(path))


# ------------------------------------------------------------- fake editor
class Comp:
    def __init__(self, cls, row, log):
        self.cls, self.log = cls, log
        r, g, b, a = row['light_color']
        self.props = {'light_color': SimpleNamespace(r=r, g=g, b=b, a=a),
                      'use_temperature': row['use_temperature'], 'temperature': row['temperature']}

    def get_class(self):
        return SimpleNamespace(get_name=lambda: self.cls)

    def get_editor_property(self, name):
        return self.props[name]

    def set_editor_property(self, name, value):
        self.log.append(('set', name))
        self.props[name] = value

    def set_light_color(self, color, srgb):
        self.log.append(('color', srgb))
        self.props['light_color'] = SimpleNamespace(**{k: int(v * 255.999) for k, v in zip('rgba', color)})


class Settings:
    def __init__(self):
        self.values = {}

    def get_editor_property(self, name):
        return self.values.get(name, 0)

    def set_editor_property(self, name, value):
        self.values[name] = value


class FakeUnreal:
    class PostProcessVolume:
        def __init__(self, label, log):
            self.label, self.log, self.props = label, log, {'settings': Settings()}

        def get_actor_label(self):
            return self.label

        def set_actor_label(self, label):
            self.label = label

        def get_components_by_class(self, cls):
            return []

        def get_editor_property(self, name):
            return self.props[name]

        def set_editor_property(self, name, value):
            self.log.append(('ppv', name))
            self.props[name] = value

    LightComponent = RendererSettings = LevelEditorSubsystem = object
    AutoExposureMethod = SimpleNamespace(AEM_HISTOGRAM='AEM_HISTOGRAM')
    LinearColor = staticmethod(lambda *c: c)
    Vector = staticmethod(lambda *v: v)

    def __init__(self, project):
        self.Paths = SimpleNamespace(project_dir=lambda: str(project))
        self.saved = 0

    def PostProcessSettings(self):
        return Settings()

    def get_default_object(self, cls):
        return SimpleNamespace(get_editor_property=lambda name: True)

    def get_editor_subsystem(self, cls):
        return SimpleNamespace(save_current_level=self._save, load_level=lambda path: True)

    def _save(self):
        self.saved += 1
        return True

    def log(self, message):
        pass


class Actor:
    def __init__(self, label, comps):
        self.label, self.comps = label, comps

    def get_actor_label(self):
        return self.label

    def get_components_by_class(self, cls):
        return self.comps


class Actors:
    def __init__(self, actors, u, log):
        self.actors, self.u, self.log = actors, u, log

    def get_all_level_actors(self):
        return list(self.actors)

    def spawn_actor_from_class(self, cls, location):
        self.log.append(('spawn',))
        actor = cls('spawned', self.log)
        self.actors.append(actor)
        return actor

    def destroy_actor(self, actor):
        self.log.append(('destroy',))
        self.actors.remove(actor)


def level(tmp_path, extra=()):
    inv = lc.load_inventory(INVENTORY)
    log = []
    u = FakeUnreal(tmp_path)
    actors = [Actor(label, [Comp(row['class'], row, log)]) for label, row in inv['lights'].items()]
    actors += list(extra)
    return u, Actors(actors, u, log), log


def run(u, actors, **kw):
    return lc.run(INVENTORY, u=u, actor_subsystem=actors, load_level=False, backup=False, **kw)


def test_apply_then_rerun_is_idempotent_then_restore_round_trips(tmp_path):
    u, actors, log = level(tmp_path)
    first = run(u, actors)
    assert len(first['changed_lights']) == 6 and log.count(('spawn',)) == 1
    sun = next(a for a in actors.actors if a.get_actor_label().endswith('SUN')).comps[0]
    assert (sun.props['light_color'].r, sun.props['light_color'].b) == (255, 255)
    assert sun.props['use_temperature'] is True and sun.props['temperature'] == 5500.0
    ppv = next(a for a in actors.actors if a.get_actor_label() == lc.PPV_LABEL)
    assert ppv.props['unbound'] is True and ppv.props['settings'].values['override_white_temp'] is True
    second = run(u, actors)
    assert second['changed_lights'] == [] and log.count(('spawn',)) == 1
    assert second['before'] == first['before']  # original state kept across re-runs
    lc.restore(INVENTORY, u=u, actor_subsystem=actors)
    assert (sun.props['light_color'].r, sun.props['light_color'].g, sun.props['light_color'].b) == (255, 210, 161)
    assert sun.props['use_temperature'] is False and log.count(('destroy',)) == 1
    assert not any(a.get_actor_label() == lc.PPV_LABEL for a in actors.actors)


@pytest.mark.parametrize('extra_kind', ['light', 'ppv', 'duplicate'])
def test_unexpected_actor_refused_without_mutation(tmp_path, extra_kind):
    log = []
    row = {'light_color': (255, 255, 255, 255), 'use_temperature': False, 'temperature': 6500.0}
    extra = {'light': Actor('Stray_PointLight', [Comp('PointLightComponent', row, log)]),
             'ppv': FakeUnreal.PostProcessVolume('SomeoneElsesPost', log),
             'duplicate': Actor('SUB01_AuthoredLight_DeskLamp', [Comp('PointLightComponent', row, log)])}[extra_kind]
    u, actors, log2 = level(tmp_path, [extra])
    with pytest.raises(lc.CorrectionRefused):
        run(u, actors)
    assert log == [] and log2 == [] and u.saved == 0


def test_colour_drift_refused_unless_allowed(tmp_path):
    u, actors, log = level(tmp_path)
    actors.actors[0].comps[0].props['light_color'] = SimpleNamespace(r=10, g=20, b=30, a=255)
    with pytest.raises(lc.CorrectionRefused, match='allow-drift'):
        run(u, actors)
    assert log == []
    assert run(u, actors, allow_drift=True)['applied']


@pytest.mark.parametrize('value,accepted', [(1, True), (0, False)])
def test_deprecated_setting_uses_actual_renderer_cvar(tmp_path, value, accepted):
    inventory = lc.load_inventory(INVENTORY)
    u, actors, log = level(tmp_path)
    def absent(cls):
        raise AttributeError('deprecated editor field unavailable')
    u.get_default_object = absent
    u.SystemLibrary = SimpleNamespace(get_console_variable_int_value=lambda name: value)
    if accepted:
        assert lc.validate(u, actors.get_all_level_actors(), inventory)['ev100_extended_range'] is True
    else:
        with pytest.raises(lc.CorrectionRefused, match='EV100'):
            lc.validate(u, actors.get_all_level_actors(), inventory)
