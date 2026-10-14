"""Pure tests for tools/reference_home_lighting.py; no Unreal or renderer launched."""
import datetime as dt
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import reference_home_lighting as rl  # noqa: E402

JST = rl.JST


def minutes(t):
    return t.hour * 60 + t.minute + t.second / 60


# ---------------------------------------------------------------- solar math
def test_equinox_noon_elevation_matches_latitude_and_declination():
    noon = rl.sun_events(dt.date(2026, 3, 20))['solar_noon']
    sun = rl.solar_position(noon, refraction=False)
    assert abs(sun['declination_deg']) < 0.5  # equinox 2026-03-20 14:46 UTC
    assert sun['elevation_deg'] == pytest.approx(90 - rl.TOKYO_LATITUDE + sun['declination_deg'], abs=0.05)
    assert sun['elevation_deg'] == pytest.approx(54.3, abs=0.6)
    assert sun['azimuth_deg'] == pytest.approx(180, abs=0.5)  # due south at solar noon


@pytest.mark.parametrize('date,sunrise,sunset', [
    # Published Tokyo (NAOJ-style) times, JST.
    (dt.date(2026, 3, 20), (5, 45), (17, 53)),
    (dt.date(2026, 6, 21), (4, 25), (19, 0)),
    (dt.date(2026, 12, 21), (6, 47), (16, 32)),
])
def test_sunrise_sunset_tokyo_within_ten_minutes(date, sunrise, sunset):
    events = rl.sun_events(date)
    assert abs(minutes(events['sunrise']) - (sunrise[0] * 60 + sunrise[1])) <= 10
    assert abs(minutes(events['sunset']) - (sunset[0] * 60 + sunset[1])) <= 10
    assert events['sunrise'] < events['solar_noon'] < events['sunset']


def test_solstice_noon_and_azimuth_quadrants():
    june = rl.solar_position(rl.sun_events(dt.date(2026, 6, 21))['solar_noon'], refraction=False)
    assert june['elevation_deg'] == pytest.approx(90 - 35.68 + 23.44, abs=0.2)
    morning = rl.solar_position(dt.datetime(2026, 10, 14, 8, 0, tzinfo=JST))
    evening = rl.solar_position(dt.datetime(2026, 10, 14, 16, 0, tzinfo=JST))
    assert 90 < morning['azimuth_deg'] < 180 and 180 < evening['azimuth_deg'] < 270
    night = rl.solar_position(dt.datetime(2026, 10, 14, 23, 0, tzinfo=JST))
    assert night['elevation_deg'] < -20


def test_naive_datetime_is_tokyo_local():
    naive = rl.solar_position(dt.datetime(2026, 10, 14, 12, 0))
    aware = rl.solar_position(dt.datetime(2026, 10, 14, 3, 0, tzinfo=dt.timezone.utc))
    assert naive['elevation_deg'] == pytest.approx(aware['elevation_deg'])


# ---------------------------------------------------------- photometric tables
def test_colour_temperature_monotonic_and_in_range():
    values = [rl.sun_temperature_k(e) for e in range(0, 91)]
    assert all(b >= a for a, b in zip(values, values[1:]))
    assert 3000 <= rl.sun_temperature_k(2) <= 4000
    assert 5500 <= rl.sun_temperature_k(60) <= 6000
    assert all(2700 <= k <= 3000 for k in rl.LAMP_TEMPERATURE_K.values())


def test_sun_illuminance_monotonic_on_authored_scale():
    values = [rl.sun_illuminance_lux(e) for e in range(0, 91)]
    assert values[0] == 0 and all(b > a for a, b in zip(values, values[1:]))
    assert values[-1] == pytest.approx(rl.AUTHORED_SUN_ZENITH_LUX)
    assert rl.sky_intensity(30) == pytest.approx(rl.AUTHORED_SKY_INTENSITY, rel=1e-3)
    assert rl.sky_intensity(-20) == pytest.approx(rl.NIGHT_SKY_INTENSITY)


# --------------------------------------------------------------------- presets
def test_night_preset_sun_off_sky_low_all_lamps_on():
    data = rl.plan('night', dt.datetime(2026, 10, 14, tzinfo=JST))
    sun = data['lights'][rl.LABEL_PREFIX + 'SUN']
    assert sun['intensity'] == 0 and sun['visible'] is False
    assert data['sky']['intensity'] <= 0.05
    assert data['phase'] == 'night'
    for name in rl.LAMP_NAMES:
        lamp = data['lights'][rl.LABEL_PREFIX + name]
        assert lamp['visible'] and lamp['intensity'] == rl.LAMP_CANDELA[name] > 0
        assert lamp['mobility'] == 'MOVABLE' and lamp['intensity_units']['value'] == 'CANDELAS'
        assert 2700 <= lamp['temperature'] <= 3000


def test_day_preset_sun_on_lamps_off_and_plan_is_json():
    data = rl.plan('afternoon', dt.datetime(2026, 10, 14, tzinfo=JST))
    sun = data['lights'][rl.LABEL_PREFIX + 'SUN']
    assert sun['intensity'] > 0 and sun['visible'] and sun['light_source_angle'] > 0.53
    assert sun['contact_shadow_length'] > 0 and sun['cast_volumetric_shadow']
    assert not any(data['lamps_on'].values())
    json.dumps(data)  # dry run must be serialisable
    assert rl.day_night_preset(True) == 'night' and rl.day_night_preset(False) in rl.PRESETS


def test_sunset_preset_is_golden_before_sunset():
    when = rl.resolve_time('sunset', dt.datetime(2026, 10, 14, tzinfo=JST))
    assert when < rl.sun_events(dt.date(2026, 10, 14))['sunset']
    data = rl.plan('sunset', when)
    assert data['phase'] == 'golden'
    assert data['lights'][rl.LABEL_PREFIX + 'SUN']['temperature'] < 4000


def test_lamp_toggle_plan_and_unknown_lamp():
    planned = rl.lamp_toggle_plan({'DeskLamp': True, 'BedLamp': False})
    assert planned[rl.LABEL_PREFIX + 'DeskLamp']['intensity'] == 12
    assert planned[rl.LABEL_PREFIX + 'BedLamp']['intensity'] == 0
    with pytest.raises(ValueError):
        rl.lamp_toggle_plan({'Chandelier': True})


def test_labels_follow_authored_light_code():
    assert all(re.fullmatch(r'SUB01_AuthoredLight_\w+', label) for label in rl.LIGHT_LABELS)
    from unreal_home_lights import authored_lights
    assert [row['name'] for row in authored_lights(12, True)] == list(rl.LIGHT_NAMES)


def test_fog_start_distance_sane_for_interior():
    fog = {c[0]: v for c, v, _ in rl.fog_properties('day')}
    assert 1000 <= fog['start_distance'] <= 3000  # beyond the < 12 m interior, not km
    assert fog['fog_density'] <= 0.02 and fog['volumetric_fog'] is True
    assert fog['volumetric_fog_extinction_scale'] <= 1.0
    assert fog['fog_max_opacity'] <= 0.5


def test_orientation_default_north_minus_z_and_ue_rotation():
    south = rl.sun_direction_source(0, 180)
    assert south == pytest.approx((0, 0, 1), abs=1e-9)
    east = rl.sun_direction_source(0, 90)
    assert east == pytest.approx((1, 0, 0), abs=1e-9)
    identity = {'axes': [0, 2, 1], 'signs': [1, 1, 1]}
    ue = rl.source_direction_to_ue(rl.sun_direction_source(45, 180), identity)
    rot = rl.directional_rotation_ue(ue)
    assert rot['pitch'] == pytest.approx(-45)  # light points down into the room


# ------------------------------------------------- validation with fake unreal
class FakeComponent:
    def __init__(self, log):
        self.log = log

    def get_editor_property(self, name):
        return 0

    def __getattr__(self, name):
        if name.startswith('set_'):
            return lambda *a, **k: self.log.append(name)
        raise AttributeError(name)


class FakeActor:
    def __init__(self, label, log):
        self.label, self.log = label, log

    def get_actor_label(self):
        return self.label

    def get_component_by_class(self, cls):
        return FakeComponent(self.log)

    def __getattr__(self, name):
        if name.startswith('set_'):
            return lambda *a, **k: self.log.append(name)
        raise AttributeError(name)


class FakeActors:
    def __init__(self, actors, log):
        self.actors, self.log = actors, log

    def get_all_level_actors(self):
        return list(self.actors)

    def spawn_actor_from_class(self, *a, **k):
        self.log.append('spawn')
        return FakeActor('spawned', self.log)


class FakeUnreal:
    class ExponentialHeightFog: pass
    class PostProcessVolume: pass
    LightComponent = DirectionalLightComponent = PointLightComponent = SpotLightComponent = object
    SkyLightComponent = ExponentialHeightFogComponent = RendererSettings = object

    def __init__(self, log):
        self.log = log

    def get_editor_subsystem(self, cls):
        raise AssertionError('tests inject subsystems')


def fake_level(labels):
    log = []
    return FakeUnreal(log), FakeActors([FakeActor(label, log) for label in labels], log), log


@pytest.mark.parametrize('labels,reason', [
    ([label for label in rl.LIGHT_LABELS if not label.endswith('BedLamp')] + [rl.SKY_LABEL], 'missing'),
    (list(rl.LIGHT_LABELS) + [rl.LABEL_PREFIX + 'DeskLamp', rl.SKY_LABEL], 'duplicated'),
])
def test_apply_refuses_without_any_mutation(labels, reason):
    u, actors, log = fake_level(labels)
    with pytest.raises(rl.LightingValidationError, match=reason):
        rl.apply('night', dt.datetime(2026, 10, 14, tzinfo=JST), u=u, actor_subsystem=actors,
                 coordinates={'axes': [0, 2, 1], 'signs': [1, 1, 1]}, load_level=False,
                 save=False, write_report=False)
    assert log == []  # nothing set, spawned or saved


def test_set_lamps_refuses_duplicate_without_mutation():
    u, actors, log = fake_level(list(rl.LIGHT_LABELS) + [rl.LABEL_PREFIX + 'BedLamp'])
    with pytest.raises(rl.LightingValidationError):
        rl.set_lamps({'DeskLamp': True, 'BedLamp': True}, u=u, actor_subsystem=actors)
    assert log == []


def test_validate_authored_lights_returns_each_once():
    log = []
    found = rl.validate_authored_lights([FakeActor(label, log) for label in rl.LIGHT_LABELS + ('Other',)])
    assert set(found) == set(rl.LIGHT_LABELS)


class _Enum:
    def __getattr__(self, name):
        return name


class FullFakeUnreal(FakeUnreal):
    LightUnits = DynamicGlobalIlluminationMethod = ReflectionMethod = _Enum()
    LumenRayLightingModeOverride = AutoExposureMethod = ComponentMobility = _Enum()

    def PostProcessSettings(self):
        return FakeComponent(self.log)

    def get_default_object(self, cls):
        return FakeComponent([])

    LinearColor = Color = Rotator = Vector = staticmethod(lambda *a, **k: (a, k))


def test_apply_happy_path_with_fake_editor_sets_lights_ppv_and_fog():
    log = []
    u = FullFakeUnreal([])
    u.log = lambda message: None  # mimics unreal.log
    actors = FakeActors([FakeActor(label, log) for label in rl.LIGHT_LABELS + (rl.SKY_LABEL,)], log)
    FakeActor.get_editor_property = lambda self, name: FakeComponent(log)
    try:
        data = rl.apply('morning', dt.datetime(2026, 10, 14, tzinfo=JST), u=u, actor_subsystem=actors,
                        coordinates={'axes': [0, 2, 1], 'signs': [1, -1, 1], 'offset_cm': [0, 0, 0]},
                        load_level=False, save=False, write_report=False)
    finally:
        del FakeActor.get_editor_property
    assert data['applied'] and data['phase'] in ('day', 'golden')
    assert log.count('spawn') == 2  # owned PPV + height fog (none existed)
    assert log.count('set_intensity') >= len(rl.LIGHT_LABELS) and 'set_actor_rotation' in log
