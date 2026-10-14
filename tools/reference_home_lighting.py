"""Reference lighting/atmosphere pass for the actual private house level.

Target look (SimbasJungles reference, see docs/design/reference-lighting):
warm cream rooms, measured warm daylight, soft sun with contact shadows,
clean Lumen GI, a barely-there volumetric haze for sun shafts, stable
interior exposure. Night: sun off, sky low, warm practical lamps carry the
room.

Operates on the EXISTING movable authored lights placed by
tools/unreal_home_lights.py (labels ``SUB01_AuthoredLight_<name>``) in
/Game/Sub01Home/ActualHome. It never deletes or spawns lights. It only owns
helper actors by exact label: an unbound PostProcessVolume and, when the
level has no height fog, an ExponentialHeightFog; plus a bounded near-camera
LocalFogVolume and an owned graded material instance for the authored Tokyo
exterior backdrop (the original exterior material is left untouched).

Structure
- Pure functions (no ``unreal``): solar position (NOAA / Meeus), sunrise and
  sunset, colour temperature and illuminance tables, presets, the full
  property plan, and label validation. ``plan(...)`` returns the planned
  property changes as JSON-serialisable data (dry run).
- ``apply(preset, when=None)`` runs inside the UE editor (or with an injected
  fake ``unreal`` module in tests). It validates EVERYTHING first (labels,
  duplicates, component classes, every property name, project exposure
  setting) and only then mutates. A refusal leaves the level untouched.

Photometric scale: the house uses the repository's authored SI recipe
(directional lux, point/spot candela, HDR SkyLight 0.4225) without the
Cycles 683 factor. The sun keeps that recipe's 3.2 lux zenith scale and
follows a clear-sky direct-normal curve (Meinel air-mass model) for its
relative strength, so it stays balanced against the authored lamps and HDR.

House orientation: the repository has NO consistent geographic north. The
live web clock (web/house/lighting.mjs) rises the sun at source -X, peaks at
+Z and sets at +X, which is mirror-handed in a right-handed Y-up frame, while
web/house/home.js calls (-12, 10, 14) its "afternoon sun" (south-west in a
right-handed frame with north = -Z). The orientation is therefore an
explicit parameter, ``north_source_xz``: the horizontal glTF-source (x, z)
direction of geographic north. Default (0, -1): north = -Z, east = +X,
south = +Z (agrees with the clock's noon and with home.js's afternoon sun).

Server use (GPU editor only, after unreal_setup_home.py):
  UnrealEditor-Cmd <project>.uproject /Game/Sub01Home/ActualHome \
    -ExecutePythonScript="<repo>/tools/reference_home_lighting.py --apply --preset morning --quit" ...
Dry run anywhere:
  python tools/reference_home_lighting.py --preset night --when 2026-10-14T21:30:00+09:00
"""
import argparse
import datetime as _dt
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from unreal_home_lights import authored_lights  # pure module (imports math only)

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
LEVEL_PATH = '/Game/Sub01Home/ActualHome'
LABEL_PREFIX = 'SUB01_AuthoredLight_'  # exact prefix used by unreal_home_lights.place_authored_lights
SUN_NAME = 'SUN'
LAMP_NAMES = ('DeskLamp', 'BedLamp', 'KitchenWork', 'LowerPendant', 'UpperPendant')
LIGHT_NAMES = (SUN_NAME,) + LAMP_NAMES
LIGHT_LABELS = tuple(LABEL_PREFIX + name for name in LIGHT_NAMES)
SKY_LABEL = 'SUB01_ActualHDR_Sky'  # spawned by unreal_setup_home.py
PPV_LABEL = 'SUB01_ReferenceLighting_PostProcess'
FOG_LABEL = 'SUB01_ReferenceLighting_HeightFog'
LOCAL_FOG_LABEL = 'SUB01_ReferenceLighting_LocalFog'
EXTERIOR_LABEL = 'SUB01_ActualHistoricalTokyoBackground'  # tools/unreal_home_exterior.py
EXTERIOR_TEXTURE = '/Game/Sub01Home/Environment/TokyoResidential'  # imported from TokyoResidential.png
EXTERIOR_GRADED_DIR = '/Game/Sub01Home/Environment/ReferenceLighting'
EXTERIOR_GRADED_MATERIAL = 'M_Sub01ReferenceTokyoBackgroundGraded'
EXTERIOR_GRADED_INSTANCE = 'MI_Sub01ReferenceTokyoBackgroundGraded'
REPORT_NAME = 'reference-home-lighting.json'

TOKYO_LATITUDE = 35.68
TOKYO_LONGITUDE = 139.69
JST = _dt.timezone(_dt.timedelta(hours=9), 'JST')
SUNRISE_ELEVATION = -0.833  # geometric centre: refraction 0.567 + semidiameter 0.266
DEFAULT_NORTH_SOURCE_XZ = (0.0, -1.0)

# Authored scale (tools/unreal_home_lights.py / web/house/lighting.mjs).
AUTHORED_SUN_ZENITH_LUX = 3.2
AUTHORED_SKY_INTENSITY = 0.4225
NIGHT_SKY_INTENSITY = 0.02
SUN_SOURCE_ANGLE_DEG = 0.8  # real disc 0.53 deg; slightly softer for sheer curtains/haze
SUN_CONTACT_SHADOW_LENGTH = 0.05  # screen fraction
LAMP_CONTACT_SHADOW_LENGTH = 0.03
SUN_VOLUMETRIC_SCATTERING = 0.6  # modest: subtle shafts, no blown-out room
LAMP_VOLUMETRIC_SCATTERING = 0.2

# (elevation deg, kelvin): monotonic, warm low sun, ~5500-6000K high sun.
SUN_TEMPERATURE_TABLE = (
    (0.0, 3000.0), (3.0, 3200.0), (6.0, 3500.0), (10.0, 3900.0), (15.0, 4300.0),
    (20.0, 4600.0), (30.0, 5100.0), (40.0, 5450.0), (50.0, 5700.0),
    (60.0, 5850.0), (90.0, 6000.0),
)

# Practical lamps: authored candela from unreal_home_lights.authored_lights,
# warm 2700-3000K, soft source radius (cm) for penumbrae.
LAMP_TEMPERATURE_K = {'DeskLamp': 2900.0, 'BedLamp': 2700.0, 'KitchenWork': 3000.0,
                      'LowerPendant': 2800.0, 'UpperPendant': 2800.0}
LAMP_SOURCE_RADIUS_CM = {'DeskLamp': 4.0, 'BedLamp': 6.0, 'KitchenWork': 3.0,
                         'LowerPendant': 8.0, 'UpperPendant': 10.0}
LAMP_KIND = {row['name']: row['kind'] for row in authored_lights(12, True)}
LAMP_CANDELA = {row['name']: float(row['intensity'])
                for row in authored_lights(12, True) if row['name'] != SUN_NAME}

DUSK_LAMPS = ('DeskLamp', 'KitchenWork', 'LowerPendant')

# Named presets: clock time on the chosen JST date ('sunset' is relative).
PRESET_CLOCK = {'morning': (7, 30), 'day': (12, 0), 'afternoon': (15, 0), 'night': (21, 30)}
SUNSET_PRESET_OFFSET_MIN = -25
PRESETS = ('auto', 'morning', 'day', 'afternoon', 'sunset', 'night')

# Exposure: clamped histogram auto exposure (EV100; requires the project's
# "extend default luminance range" setting, the UE5 default; apply() checks it).
EXPOSURE = {
    'day':    {'min_ev100': -2.0, 'max_ev100': 2.0, 'bias': 0.5, 'manual_bias': 2.0},
    'golden': {'min_ev100': -2.5, 'max_ev100': 1.5, 'bias': 0.3, 'manual_bias': 2.0},
    'night':  {'min_ev100': -3.0, 'max_ev100': 1.0, 'bias': 0.0, 'manual_bias': 2.3},
}

# Actual ground floor in glTF source metres (web/house/home.js shell): 8 x 8 m
# house, outer walls at x/z = +-4 with 0.18 m thickness; upper floor finish at
# y ~3.05 (tools/build_home_bath_fixtures.py), so the ground-floor air is
# conservatively y 0..2.85. First-person camera: (2, 1.65, 3.1) looking -Z.
GROUND_INTERIOR_SOURCE = {'x': (-3.91, 3.91), 'y': (0.0, 2.85), 'z': (-3.91, 3.91)}
ROOM_DIAGONAL_M = math.dist((-3.91, 0.0, -3.91), (3.91, 2.85, 3.91))  # ~11.4 m
FIRST_PERSON_CAMERA_SOURCE = (2.0, 1.65, 3.1)

# Global height fog stays subtle: the analytic part starts past the near room
# (the reference's problem was UE's far default start, solved with LOCAL fog),
# and its volumetric part covers only the house, starting at the camera.
FOG = {
    'fog_density': 0.005, 'fog_height_falloff': 0.2, 'start_distance': 600.0,
    'fog_max_opacity': 0.15, 'volumetric_fog_scattering_distribution': 0.6,
    'volumetric_fog_extinction_scale': 0.4, 'volumetric_fog_start_distance': 0.0,
    'volumetric_fog_distance': 1400.0, 'volumetric_fog_albedo': (240, 232, 218),
}
# Bounded local fog ellipsoid near the camera (source metres), inside the room.
LOCAL_FOG = {
    'center_source': (2.0, 1.45, 1.0), 'semi_axes_source_m': (1.7, 1.35, 2.6),
    'radial_fog_extinction': 0.03,  # per metre at the centre: low, optical depth << 1
    'height_fog_extinction': 0.0, 'fog_phase_g': 0.6,
    'fog_albedo': (0.96, 0.93, 0.87), 'fog_emissive': (0.0, 0.0, 0.0),
}
LOCAL_FOG_UNIT_RADIUS_CM_FALLBACK = 500.0  # measured from actor bounds at apply time when possible

# Authored Tokyo exterior backdrop grade per sky state (unlit emissive photo).
EXTERIOR_DAY = {'brightness': 1.0, 'tint': (1.0, 1.0, 1.0), 'desaturation': 0.0}
EXTERIOR_GOLDEN = {'brightness': 0.6, 'tint': (1.0, 0.82, 0.62), 'desaturation': 0.1}
EXTERIOR_NIGHT = {'brightness': 0.05, 'tint': (0.45, 0.55, 1.0), 'desaturation': 0.6}
FOG_INSCATTER = {'day': (0.50, 0.47, 0.42), 'golden': (0.30, 0.24, 0.18), 'night': (0.02, 0.025, 0.04)}
NIGHT_SKY_TINT = (0.55, 0.65, 1.0)


class LightingValidationError(RuntimeError):
    """Raised before any mutation when the level is not as expected."""


# --------------------------------------------------------------------------
# Solar position (NOAA spreadsheet algorithm, after Meeus)
# --------------------------------------------------------------------------
def _as_utc(when):
    if when.tzinfo is None:
        when = when.replace(tzinfo=JST)  # naive datetimes are Tokyo local time
    return when.astimezone(_dt.timezone.utc)


def julian_day(when):
    t = _as_utc(when)
    a = (14 - t.month) // 12
    y = t.year + 4800 - a
    m = t.month + 12 * a - 3
    jdn = t.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    return jdn + (t.hour - 12) / 24 + t.minute / 1440 + (t.second + t.microsecond / 1e6) / 86400


def _refraction_deg(elevation):
    if elevation > 85:
        return 0.0
    te = math.tan(math.radians(elevation))
    if elevation > 5:
        arcsec = 58.1 / te - 0.07 / te ** 3 + 0.000086 / te ** 5
    elif elevation > -0.575:
        e = elevation
        arcsec = 1735 + e * (-518.2 + e * (103.4 + e * (-12.79 + e * 0.711)))
    else:
        arcsec = -20.772 / te
    return arcsec / 3600


def solar_position(when, latitude=TOKYO_LATITUDE, longitude=TOKYO_LONGITUDE, refraction=True):
    """Sun elevation/azimuth (deg). Azimuth clockwise from geographic north."""
    jd = julian_day(when)
    T = (jd - 2451545.0) / 36525.0
    L0 = (280.46646 + T * (36000.76983 + T * 0.0003032)) % 360
    M = 357.52911 + T * (35999.05029 - 0.0001537 * T)
    e = 0.016708634 - T * (0.000042037 + 0.0000001267 * T)
    Mr = math.radians(M)
    C = (math.sin(Mr) * (1.914602 - T * (0.004817 + 0.000014 * T))
         + math.sin(2 * Mr) * (0.019993 - 0.000101 * T) + math.sin(3 * Mr) * 0.000289)
    omega = math.radians(125.04 - 1934.136 * T)
    apparent_long = math.radians(L0 + C - 0.00569 - 0.00478 * math.sin(omega))
    eps0 = 23 + (26 + (21.448 - T * (46.815 + T * (0.00059 - T * 0.001813))) / 60) / 60
    eps = math.radians(eps0 + 0.00256 * math.cos(omega))
    decl = math.asin(math.sin(eps) * math.sin(apparent_long))
    y = math.tan(eps / 2) ** 2
    L0r = math.radians(L0)
    eot_min = 4 * math.degrees(
        y * math.sin(2 * L0r) - 2 * e * math.sin(Mr) + 4 * e * y * math.sin(Mr) * math.cos(2 * L0r)
        - 0.5 * y * y * math.sin(4 * L0r) - 1.25 * e * e * math.sin(2 * Mr))
    t = _as_utc(when)
    utc_minutes = t.hour * 60 + t.minute + (t.second + t.microsecond / 1e6) / 60
    true_solar_minutes = (utc_minutes + eot_min + 4 * longitude) % 1440
    hour_angle = math.radians(true_solar_minutes / 4 - 180)
    lat = math.radians(latitude)
    cos_zenith = math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.cos(hour_angle)
    elevation = 90 - math.degrees(math.acos(max(-1.0, min(1.0, cos_zenith))))
    azimuth = (math.degrees(math.atan2(
        math.sin(hour_angle),
        math.cos(hour_angle) * math.sin(lat) - math.tan(decl) * math.cos(lat))) + 180) % 360
    if refraction:
        elevation += _refraction_deg(elevation)
    return {'elevation_deg': elevation, 'azimuth_deg': azimuth,
            'declination_deg': math.degrees(decl), 'equation_of_time_min': eot_min,
            'hour_angle_deg': math.degrees(hour_angle)}


def _geometric_elevation(when, latitude, longitude):
    return solar_position(when, latitude, longitude, refraction=False)['elevation_deg']


def sun_events(date, latitude=TOKYO_LATITUDE, longitude=TOKYO_LONGITUDE, tz=JST):
    """Sunrise, solar noon and sunset (aware datetimes in ``tz``) for a local date."""
    start = _dt.datetime(date.year, date.month, date.day, tzinfo=tz)
    step = _dt.timedelta(minutes=10)
    samples = [start + step * i for i in range(145)]
    values = [_geometric_elevation(s, latitude, longitude) - SUNRISE_ELEVATION for s in samples]

    def bisect(a, b, fa):
        for _ in range(40):
            mid = a + (b - a) / 2
            fm = _geometric_elevation(mid, latitude, longitude) - SUNRISE_ELEVATION
            if (fm > 0) == (fa > 0):
                a, fa = mid, fm
            else:
                b = mid
        return a + (b - a) / 2

    sunrise = sunset = None
    for i in range(len(samples) - 1):
        if values[i] <= 0 < values[i + 1] and sunrise is None:
            sunrise = bisect(samples[i], samples[i + 1], values[i])
        elif values[i] > 0 >= values[i + 1]:
            sunset = bisect(samples[i], samples[i + 1], values[i])
    noon_index = max(range(len(samples)), key=values.__getitem__)
    lo = samples[max(0, noon_index - 1)]
    hi = samples[min(len(samples) - 1, noon_index + 1)]
    for _ in range(40):  # golden-section-free ternary search for the maximum
        m1 = lo + (hi - lo) / 3
        m2 = hi - (hi - lo) / 3
        if _geometric_elevation(m1, latitude, longitude) < _geometric_elevation(m2, latitude, longitude):
            lo = m1
        else:
            hi = m2
    return {'sunrise': sunrise, 'solar_noon': lo + (hi - lo) / 2, 'sunset': sunset}


# --------------------------------------------------------------------------
# Photometric tables
# --------------------------------------------------------------------------
def _interp(table, x):
    if x <= table[0][0]:
        return table[0][1]
    for (x0, y0), (x1, y1) in zip(table, table[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return table[-1][1]


def _smoothstep(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def sun_temperature_k(elevation_deg):
    return _interp(SUN_TEMPERATURE_TABLE, max(0.0, elevation_deg))


def air_mass(elevation_deg):
    """Kasten & Young (1989) relative optical air mass."""
    zenith = 90.0 - max(0.0, elevation_deg)
    return 1.0 / (math.cos(math.radians(zenith)) + 0.50572 * (96.07995 - zenith) ** -1.6364)


def direct_normal_irradiance(elevation_deg):
    """Meinel & Meinel clear-sky beam irradiance, W/m^2 (0 below horizon)."""
    if elevation_deg <= 0:
        return 0.0
    return 1353.0 * 0.7 ** (air_mass(elevation_deg) ** 0.678)


def sun_illuminance_lux(elevation_deg):
    """Directional-light lux on the authored scale (3.2 lux at the zenith)."""
    return AUTHORED_SUN_ZENITH_LUX * direct_normal_irradiance(elevation_deg) / direct_normal_irradiance(90.0)


def sky_intensity(elevation_deg):
    """HDR SkyLight scalar: authored 0.4225 by day, fading through civil/nautical twilight."""
    k = _smoothstep(-12.0, 8.0, elevation_deg)
    return NIGHT_SKY_INTENSITY + (AUTHORED_SKY_INTENSITY - NIGHT_SKY_INTENSITY) * k


def phase_for(elevation_deg):
    if elevation_deg < 0:
        return 'night'
    if elevation_deg < 10:
        return 'golden'
    return 'day'


# --------------------------------------------------------------------------
# Orientation
# --------------------------------------------------------------------------
def sun_direction_source(elevation_deg, azimuth_deg, north_source_xz=DEFAULT_NORTH_SOURCE_XZ):
    """Unit vector toward the sun in the glTF source frame (Y up, metres).

    East is derived right-handedly: E = N x Up, i.e. (-n_z, 0, n_x).
    """
    nx, nz = north_source_xz
    length = math.hypot(nx, nz)
    if length < 1e-9:
        raise ValueError('north_source_xz must be a non-zero horizontal direction')
    nx, nz = nx / length, nz / length
    ex, ez = -nz, nx
    el, az = math.radians(elevation_deg), math.radians(azimuth_deg)
    h = math.cos(el)
    return (h * (math.sin(az) * ex + math.cos(az) * nx), math.sin(el),
            h * (math.sin(az) * ez + math.cos(az) * nz))


def source_direction_to_ue(direction, coordinates):
    """Map a source-frame direction with the verified import transform (no offset/scale)."""
    return tuple(coordinates['signs'][i] * direction[coordinates['axes'][i]] for i in range(3))


def directional_rotation_ue(sun_dir_ue):
    """Rotator (deg) whose forward (+X) points FROM the sun INTO the scene."""
    fx, fy, fz = (-c for c in sun_dir_ue)
    return {'pitch': math.degrees(math.asin(max(-1.0, min(1.0, fz)))),
            'yaw': math.degrees(math.atan2(fy, fx)), 'roll': 0.0}


# --------------------------------------------------------------------------
# Presets and lamp toggles (pure)
# --------------------------------------------------------------------------
def resolve_time(preset='auto', when=None):
    """Instant for a preset. 'auto' uses ``when`` (default now); named presets
    use only the JST date of ``when`` (default today) and their own clock time."""
    if preset not in PRESETS:
        raise ValueError('Unknown preset %r; expected one of %s' % (preset, ', '.join(PRESETS)))
    if when is None:
        when = _dt.datetime.now(JST)
    elif when.tzinfo is None:
        when = when.replace(tzinfo=JST)
    local = when.astimezone(JST)
    if preset == 'auto':
        return local
    if preset == 'sunset':
        sunset = sun_events(local.date())['sunset'] + _dt.timedelta(minutes=SUNSET_PRESET_OFFSET_MIN)
        return sunset.replace(second=0, microsecond=0)
    hour, minute = PRESET_CLOCK[preset]
    return _dt.datetime(local.year, local.month, local.day, hour, minute, tzinfo=JST)


def lamps_for(elevation_deg, preset='auto'):
    """Which practical lamps are on: none by day, a dusk set at golden hour, all at night."""
    if preset == 'night' or elevation_deg < 0:
        return {name: True for name in LAMP_NAMES}
    if elevation_deg < 6:
        return {name: name in DUSK_LAMPS for name in LAMP_NAMES}
    return {name: False for name in LAMP_NAMES}


def day_night_preset(is_night):
    """Public day/night preset name: 'night' or 'afternoon' (warm, measured daylight)."""
    return 'night' if is_night else 'afternoon'


def _enum(type_name, value):
    return {'enum': type_name, 'value': value}


def _linear(rgb, a=1.0):
    return {'struct': 'LinearColor', 'rgba': [float(rgb[0]), float(rgb[1]), float(rgb[2]), float(a)]}


def lamp_properties(name, on):
    """Planned component properties for one practical lamp (stays Movable)."""
    if name not in LAMP_NAMES:
        raise ValueError('Unknown lamp %r' % name)
    radius = LAMP_SOURCE_RADIUS_CM[name]
    return {
        'mobility': 'MOVABLE', 'visible': bool(on),
        'intensity_units': _enum('LightUnits', 'CANDELAS'),
        'intensity': LAMP_CANDELA[name] if on else 0.0,
        'use_temperature': True, 'temperature': LAMP_TEMPERATURE_K[name],
        'light_color': _linear((1, 1, 1)),
        'cast_shadows': True, 'source_radius': radius, 'soft_source_radius': radius * 0.5,
        'contact_shadow_length': LAMP_CONTACT_SHADOW_LENGTH, 'contact_shadow_length_in_ws': False,
        'volumetric_scattering_intensity': LAMP_VOLUMETRIC_SCATTERING,
        'cast_volumetric_shadow': False,
    }


def lamp_toggle_plan(states):
    """Labels -> properties for a lamp on/off mapping, e.g. {'DeskLamp': True}."""
    unknown = sorted(set(states) - set(LAMP_NAMES))
    if unknown:
        raise ValueError('Unknown lamps: %s' % ', '.join(unknown))
    return {LABEL_PREFIX + name: lamp_properties(name, on) for name, on in states.items()}


def sun_properties(elevation_deg, sun_on=True):
    on = sun_on and elevation_deg > 0
    return {
        'mobility': 'MOVABLE', 'visible': on,
        'intensity': sun_illuminance_lux(elevation_deg) if on else 0.0,
        'use_temperature': True, 'temperature': sun_temperature_k(elevation_deg),
        'light_color': _linear((1, 1, 1)), 'cast_shadows': True,
        'light_source_angle': SUN_SOURCE_ANGLE_DEG, 'light_source_soft_angle': 0.0,
        'contact_shadow_length': SUN_CONTACT_SHADOW_LENGTH, 'contact_shadow_length_in_ws': False,
        'volumetric_scattering_intensity': SUN_VOLUMETRIC_SCATTERING,
        'cast_volumetric_shadow': on,
    }


def post_process_settings(phase, exposure_mode='clamped_auto'):
    """(property, value, required) rows for the unbound PostProcessVolume."""
    exp = EXPOSURE[phase]
    rows = [
        ('dynamic_global_illumination_method', _enum('DynamicGlobalIlluminationMethod', 'LUMEN'), True),
        ('reflection_method', _enum('ReflectionMethod', 'LUMEN'), True),
        ('lumen_scene_lighting_quality', 1.0, False),
        ('lumen_scene_detail', 1.0, False),
        ('lumen_final_gather_quality', 1.5, False),  # cleaner GI in dim interior corners
        ('lumen_max_trace_distance', 2000.0, False),  # house scale
        ('lumen_reflection_quality', 1.0, False),  # engine default, deliberately not raised
        ('lumen_ray_lighting_mode', _enum('LumenRayLightingModeOverride', 'SURFACE_CACHE'), False),
        ('lumen_max_roughness_to_trace_reflections', 0.4, False),
        ('lumen_front_layer_translucency_reflections', False, False),
        ('lumen_skylight_leaking', 0.0, False),
        ('white_temp', 6500.0, False),
        ('bloom_intensity', 0.4, False),
        ('vignette_intensity', 0.3, False),
        ('local_exposure_highlight_contrast_scale', 0.85 if phase != 'night' else 1.0, False),
        ('local_exposure_shadow_contrast_scale', 0.95 if phase != 'night' else 1.0, False),
        ('auto_exposure_apply_physical_camera_exposure', False, True),
    ]
    if exposure_mode == 'manual':
        rows += [('auto_exposure_method', _enum('AutoExposureMethod', 'AEM_MANUAL'), True),
                 ('auto_exposure_bias', exp['manual_bias'], True)]
    elif exposure_mode == 'clamped_auto':
        rows += [('auto_exposure_method', _enum('AutoExposureMethod', 'AEM_HISTOGRAM'), True),
                 ('auto_exposure_bias', exp['bias'], True),
                 ('auto_exposure_min_brightness', exp['min_ev100'], True),
                 ('auto_exposure_max_brightness', exp['max_ev100'], True),
                 ('auto_exposure_speed_up', 2.0, False),
                 ('auto_exposure_speed_down', 1.0, False)]
    else:
        raise ValueError('exposure_mode must be clamped_auto or manual')
    return rows


def fog_properties(phase):
    """(candidate property names, value, required) rows for the height fog component."""
    r, g, b = FOG['volumetric_fog_albedo']
    return [
        (('fog_density',), FOG['fog_density'], True),
        (('fog_height_falloff',), FOG['fog_height_falloff'], True),
        (('start_distance',), FOG['start_distance'], True),
        (('fog_max_opacity',), FOG['fog_max_opacity'], True),
        (('fog_inscattering_luminance', 'fog_inscattering_color'), _linear(FOG_INSCATTER[phase]), False),
        (('volumetric_fog',), True, True),
        (('volumetric_fog_scattering_distribution',), FOG['volumetric_fog_scattering_distribution'], True),
        (('volumetric_fog_extinction_scale',), FOG['volumetric_fog_extinction_scale'], True),
        (('volumetric_fog_start_distance',), FOG['volumetric_fog_start_distance'], False),
        (('volumetric_fog_distance',), FOG['volumetric_fog_distance'], False),
        (('volumetric_fog_albedo',), {'struct': 'Color', 'rgba': [r, g, b, 255]}, False),
    ]


def _ellipsoid_bounds(center, semi_axes):
    return {axis: (center[i] - semi_axes[i], center[i] + semi_axes[i]) for i, axis in enumerate('xyz')}


def local_fog_bounds_source():
    return _ellipsoid_bounds(LOCAL_FOG['center_source'], LOCAL_FOG['semi_axes_source_m'])


def local_fog_contains(point_source):
    c, r = LOCAL_FOG['center_source'], LOCAL_FOG['semi_axes_source_m']
    return sum(((point_source[i] - c[i]) / r[i]) ** 2 for i in range(3)) <= 1.0


def local_fog_plan(coordinates=None):
    """Near-camera LocalFogVolume: ellipsoid inside the ground-floor footprint."""
    c, r = LOCAL_FOG['center_source'], LOCAL_FOG['semi_axes_source_m']
    out = {'label': LOCAL_FOG_LABEL, 'center_source': list(c), 'semi_axes_source_m': list(r),
           'bounds_source': {k: list(v) for k, v in local_fog_bounds_source().items()},
           'contains_first_person_camera': local_fog_contains(FIRST_PERSON_CAMERA_SOURCE),
           'peak_optical_depth': LOCAL_FOG['radial_fog_extinction'] * 2 * max(r),
           'properties': [
               (('radial_fog_extinction',), LOCAL_FOG['radial_fog_extinction'], True),
               (('height_fog_extinction',), LOCAL_FOG['height_fog_extinction'], False),
               (('fog_phase_g',), LOCAL_FOG['fog_phase_g'], False),
               (('fog_albedo',), _linear(LOCAL_FOG['fog_albedo']), False),
               (('fog_emissive',), _linear(LOCAL_FOG['fog_emissive']), False)],
           'location_ue_cm': None, 'semi_axes_ue_cm': None}
    out['properties'] = [{'candidates': list(n), 'value': v, 'required': q} for n, v, q in out['properties']]
    if coordinates is not None and 'offset_cm' in coordinates:
        from unreal_home_coordinates import convert_position
        out['location_ue_cm'] = list(convert_position(c, coordinates))
        out['semi_axes_ue_cm'] = [100.0 * r[coordinates['axes'][i]] for i in range(3)]
    return out


def exterior_grade(elevation_deg, preset='auto'):
    """Brightness/tint/desaturation for the authored Tokyo backdrop; dark blue at night."""
    day = 0.0 if preset == 'night' else _smoothstep(-12.0, 8.0, elevation_deg)
    golden = 0.0 if preset == 'night' else max(0.0, 1.0 - abs(elevation_deg - 3.0) / 9.0)

    def mix(a, b, t):
        return a + (b - a) * t

    out = {'brightness': mix(EXTERIOR_NIGHT['brightness'], EXTERIOR_DAY['brightness'], day),
           'tint': [mix(EXTERIOR_NIGHT['tint'][i], EXTERIOR_DAY['tint'][i], day) for i in range(3)],
           'desaturation': mix(EXTERIOR_NIGHT['desaturation'], EXTERIOR_DAY['desaturation'], day)}
    if golden > 0:  # warm, dimmer backdrop around sunset/sunrise
        out['brightness'] = mix(out['brightness'], EXTERIOR_GOLDEN['brightness'], golden * day)
        out['tint'] = [mix(out['tint'][i], EXTERIOR_GOLDEN['tint'][i], golden * day) for i in range(3)]
        out['desaturation'] = mix(out['desaturation'], EXTERIOR_GOLDEN['desaturation'], golden * day)
    return out


def plan(preset='auto', when=None, coordinates=None, north_source_xz=DEFAULT_NORTH_SOURCE_XZ,
         exposure_mode='clamped_auto', lamp_overrides=None):
    """Full JSON-serialisable property plan (the dry run). No ``unreal`` needed."""
    instant = resolve_time(preset, when)
    solar = solar_position(instant)
    events = sun_events(instant.date())
    elevation = solar['elevation_deg']
    sun_on = preset != 'night' and elevation > 0
    phase = 'night' if preset == 'night' else phase_for(elevation)
    lamp_states = lamps_for(elevation, preset)
    lamp_states.update(lamp_overrides or {})
    lights = {LABEL_PREFIX + SUN_NAME: sun_properties(elevation, sun_on)}
    lights.update(lamp_toggle_plan(lamp_states))
    direction = sun_direction_source(max(elevation, 0.5), solar['azimuth_deg'], north_source_xz)
    orientation = {'north_source_xz': list(north_source_xz),
                   'convention': 'glTF source frame, Y up; east = north x up (right-handed)',
                   'sun_direction_source': list(direction),
                   'sun_direction_ue': None, 'sun_rotation_ue': None}
    if coordinates is not None:
        ue = source_direction_to_ue(direction, coordinates)
        orientation['sun_direction_ue'] = list(ue)
        orientation['sun_rotation_ue'] = directional_rotation_ue(ue)
    night_mix = 1.0 - _smoothstep(-12.0, 8.0, elevation)
    tint = [1.0 + (t - 1.0) * night_mix for t in NIGHT_SKY_TINT]
    sky_level = NIGHT_SKY_INTENSITY if preset == 'night' else sky_intensity(elevation)
    return {
        'level': LEVEL_PATH, 'preset': preset, 'phase': phase,
        'when_jst': instant.astimezone(JST).isoformat(),
        'location': {'name': 'Tokyo', 'latitude': TOKYO_LATITUDE, 'longitude': TOKYO_LONGITUDE, 'utc_offset_h': 9},
        'solar': dict(solar, sunrise_jst=events['sunrise'] and events['sunrise'].isoformat(timespec='seconds'),
                      solar_noon_jst=events['solar_noon'].isoformat(timespec='seconds'),
                      sunset_jst=events['sunset'] and events['sunset'].isoformat(timespec='seconds'),
                      direct_normal_w_m2=direct_normal_irradiance(elevation)),
        'orientation': orientation,
        'lamps_on': {name: bool(on) for name, on in lamp_states.items()},
        'lights': lights,
        'sky': {'label': SKY_LABEL, 'intensity': sky_level, 'light_color': _linear(tint)},
        'post_process': {'label': PPV_LABEL, 'unbound': True, 'priority': 10.0, 'blend_weight': 1.0,
                         'exposure_mode': exposure_mode,
                         'settings': [{'property': p, 'value': v, 'required': r}
                                      for p, v, r in post_process_settings(phase, exposure_mode)]},
        'height_fog': {'label_if_spawned': FOG_LABEL, 'reuse_single_existing': True,
                       'properties': [{'candidates': list(c), 'value': v, 'required': r}
                                      for c, v, r in fog_properties(phase)]},
        'local_fog': local_fog_plan(coordinates),
        'exterior': dict(exterior_grade(elevation, preset), label=EXTERIOR_LABEL, texture=EXTERIOR_TEXTURE,
                         graded_instance=EXTERIOR_GRADED_DIR + '/' + EXTERIOR_GRADED_INSTANCE,
                         original_material_untouched=True),
        'dust': 'none added: no UE particle/Niagara dust asset exists in this repository',
        'unchanged_engine_defaults_assumed': {
            'r.Lumen.HardwareRayTracing': 0, 'r.Lumen.ScreenProbeGather.ScreenTraces': 1,
            'r.Lumen.Reflections.ScreenTraces': 1, 'r.VolumetricFog': 1},
    }


# --------------------------------------------------------------------------
# Validation (pure: works on any objects exposing get_actor_label())
# --------------------------------------------------------------------------
def find_unique_actors(actors, labels, required=True):
    """Exactly one actor per label, or raise. Never mutates anything."""
    found = {label: [] for label in labels}
    for actor in actors:
        label = actor.get_actor_label()
        if label in found:
            found[label].append(actor)
    missing = [label for label, hits in found.items() if not hits]
    duplicated = [label for label, hits in found.items() if len(hits) > 1]
    problems = []
    if missing and required:
        problems.append('missing: ' + ', '.join(missing))
    if duplicated:
        problems.append('duplicated: ' + ', '.join(duplicated))
    if problems:
        raise LightingValidationError('Refusing reference lighting, no changes made (' + '; '.join(problems) + ')')
    return {label: hits[0] for label, hits in found.items() if hits}


def validate_authored_lights(actors):
    return find_unique_actors(actors, LIGHT_LABELS)


# --------------------------------------------------------------------------
# Editor application
# --------------------------------------------------------------------------
def _resolve(u, value):
    if isinstance(value, dict) and 'enum' in value:
        return getattr(getattr(u, value['enum']), value['value'])
    if isinstance(value, dict) and value.get('struct') == 'LinearColor':
        return u.LinearColor(*value['rgba'])
    if isinstance(value, dict) and value.get('struct') == 'Color':
        r, g, b, a = value['rgba']
        return u.Color(r=r, g=g, b=b, a=a)
    return value


_METHOD_PROPS = {'mobility', 'visible', 'intensity', 'light_color'}


def _probe(obj, name):
    try:
        obj.get_editor_property(name)
        return True
    except Exception:
        return False


def _load_coordinates(project_dir):
    path = Path(project_dir) / 'unreal-home-setup.json'
    if not path.is_file():
        raise LightingValidationError('Missing %s: run unreal_setup_home.py first (verified import transform needed)' % path)
    coordinates = json.loads(path.read_text()).get('coordinates')
    if not coordinates or 'axes' not in coordinates or 'signs' not in coordinates:
        raise LightingValidationError('unreal-home-setup.json has no verified coordinates')
    return coordinates


def apply(preset='auto', when=None, *, u=None, actor_subsystem=None, coordinates=None,
          north_source_xz=DEFAULT_NORTH_SOURCE_XZ, exposure_mode='clamped_auto',
          lamp_overrides=None, load_level=True, save=True, write_report=True):
    """Validate everything, then apply the plan to the open house level."""
    if u is None:
        import unreal as u  # noqa: N813 - editor only
    if load_level:
        level = u.get_editor_subsystem(u.LevelEditorSubsystem)
        if not level.load_level(LEVEL_PATH):
            raise LightingValidationError('Actual home map is missing: ' + LEVEL_PATH)
    actors = actor_subsystem or u.get_editor_subsystem(u.EditorActorSubsystem)
    all_actors = list(actors.get_all_level_actors())

    # ---- validation phase: no mutation below until 'apply phase' ----
    lights = validate_authored_lights(all_actors)
    sky = find_unique_actors(all_actors, [SKY_LABEL], required=False).get(SKY_LABEL)
    ppv = find_unique_actors(all_actors, [PPV_LABEL], required=False).get(PPV_LABEL)
    fogs = [a for a in all_actors if isinstance(a, u.ExponentialHeightFog)]
    if len(fogs) > 1:
        raise LightingValidationError('Refusing: %d ExponentialHeightFog actors (UE uses only one)' % len(fogs))
    other_ppvs = [a.get_actor_label() for a in all_actors
                  if isinstance(a, u.PostProcessVolume) and a.get_actor_label() != PPV_LABEL]
    if coordinates is None:
        coordinates = _load_coordinates(u.Paths.project_dir())
    data = plan(preset, when, coordinates, north_source_xz, exposure_mode, lamp_overrides)

    components, problems = {}, []
    expected_kind = {'directional': 'DirectionalLightComponent', 'point': 'PointLightComponent',
                     'spot': 'SpotLightComponent'}
    for label, actor in lights.items():
        name = label[len(LABEL_PREFIX):]
        component = actor.get_component_by_class(getattr(u, expected_kind[LAMP_KIND[name]]))
        if component is None:
            problems.append('%s has no %s' % (label, expected_kind[LAMP_KIND[name]]))
            continue
        components[label] = component
        for prop in data['lights'][label]:
            if prop not in _METHOD_PROPS and not _probe(component, prop):
                problems.append('%s lacks property %s' % (label, prop))
    sky_component = sky.get_component_by_class(u.SkyLightComponent) if sky else None
    probe_settings = u.PostProcessSettings()
    pp_rows = []
    for row in data['post_process']['settings']:
        ok = _probe(probe_settings, row['property']) and _probe(probe_settings, 'override_' + row['property'])
        try:
            _resolve(u, row['value'])
        except AttributeError:
            ok = False
        if ok:
            pp_rows.append(row)
        elif row['required']:
            problems.append('PostProcessSettings lacks ' + row['property'])
    fog_default = u.get_default_object(u.ExponentialHeightFogComponent)
    fog_rows, skipped = [], []
    for row in data['height_fog']['properties']:
        name = next((c for c in row['candidates'] if _probe(fog_default, c)), None)
        if name:
            fog_rows.append((name, row['value']))
        elif row['required']:
            problems.append('ExponentialHeightFogComponent lacks ' + '/'.join(row['candidates']))
        else:
            skipped.append('/'.join(row['candidates']))
    skipped += [row['property'] for row in data['post_process']['settings'] if row not in pp_rows]
    if exposure_mode == 'clamped_auto':
        try:
            settings = u.get_default_object(u.RendererSettings)
            extended = settings.get_editor_property('extend_default_luminance_range_in_auto_exposure_settings')
        except Exception:
            extended = None
        if extended is False:
            problems.append('Project auto exposure is not in EV100 (extend default luminance range is off)')
        data['ev100_luminance_range_setting'] = extended
    # Near-camera local fog volume (owned label, bounded inside the room).
    local_plan = data['local_fog']
    local_fog = find_unique_actors(all_actors, [LOCAL_FOG_LABEL], required=False).get(LOCAL_FOG_LABEL)
    local_rows = []
    if not hasattr(u, 'LocalFogVolume') or not hasattr(u, 'LocalFogVolumeComponent'):
        problems.append('Engine has no LocalFogVolume (UE 5.3+ required for near-camera fog)')
    else:
        local_default = u.get_default_object(u.LocalFogVolumeComponent)
        for row in local_plan['properties']:
            name = next((c for c in row['candidates'] if _probe(local_default, c)), None)
            if name:
                local_rows.append((name, row['value']))
            elif row['required']:
                problems.append('LocalFogVolumeComponent lacks ' + '/'.join(row['candidates']))
            else:
                skipped.append('local fog ' + '/'.join(row['candidates']))
    if local_plan['location_ue_cm'] is None:
        problems.append('Verified coordinates lack offset_cm; cannot place the local fog volume')
    # Authored Tokyo exterior backdrop (optional actor, unique if present).
    exterior = find_unique_actors(all_actors, [EXTERIOR_LABEL], required=False).get(EXTERIOR_LABEL)
    exterior_texture = None
    if exterior is not None:
        exterior_texture = u.load_asset(EXTERIOR_TEXTURE)
        if exterior_texture is None or not isinstance(exterior_texture, u.Texture2D):
            problems.append('Exterior backdrop present but its texture %s is missing' % EXTERIOR_TEXTURE)
        elif exterior.get_component_by_class(u.StaticMeshComponent) is None:
            problems.append('Exterior backdrop has no StaticMeshComponent')
    if problems:
        raise LightingValidationError('Refusing reference lighting, no changes made: ' + '; '.join(problems))

    # ---- apply phase ----
    # Owned graded exterior assets first (asset-only, the scene is still untouched).
    if exterior is not None:
        instance = _ensure_exterior_instance(u, exterior_texture, data['exterior'])
        exterior_mesh = exterior.get_component_by_class(u.StaticMeshComponent)
        original = exterior_mesh.get_material(0)
        data['exterior']['original_material'] = original.get_path_name() if original else None
        exterior_mesh.set_material(0, instance)
    else:
        skipped.append('exterior grade (no %s actor)' % EXTERIOR_LABEL)
    before = {}
    for label, component in components.items():
        props = data['lights'][label]
        before[label] = {'intensity': component.get_editor_property('intensity')}
        component.set_mobility(u.ComponentMobility.MOVABLE)
        for prop, value in props.items():
            if prop in ('mobility', 'visible', 'intensity', 'light_color'):
                continue
            component.set_editor_property(prop, _resolve(u, value))
        component.set_light_color(_resolve(u, props['light_color']), True)
        component.set_intensity(props['intensity'])
        component.set_visibility(props['visible'], False)
    rot = data['orientation']['sun_rotation_ue']
    lights[LABEL_PREFIX + SUN_NAME].set_actor_rotation(
        u.Rotator(roll=rot['roll'], pitch=rot['pitch'], yaw=rot['yaw']), False)
    if sky_component is not None:
        sky_component.set_intensity(data['sky']['intensity'])
        sky_component.set_light_color(_resolve(u, data['sky']['light_color']))
    else:
        skipped.append('sky (no %s actor)' % SKY_LABEL)

    if ppv is None:
        ppv = actors.spawn_actor_from_class(u.PostProcessVolume, u.Vector(0, 0, 0))
        ppv.set_actor_label(PPV_LABEL)
    ppv.set_editor_property('unbound', True)
    ppv.set_editor_property('priority', data['post_process']['priority'])
    ppv.set_editor_property('blend_weight', data['post_process']['blend_weight'])
    settings = ppv.get_editor_property('settings')
    for row in pp_rows:
        settings.set_editor_property('override_' + row['property'], True)
        settings.set_editor_property(row['property'], _resolve(u, row['value']))
    ppv.set_editor_property('settings', settings)

    floor = tuple(coordinates['offset_cm'][i] for i in range(3)) if 'offset_cm' in coordinates else (0, 0, 0)
    if fogs:
        fog = fogs[0]
    else:
        fog = actors.spawn_actor_from_class(u.ExponentialHeightFog, u.Vector(*floor))
        fog.set_actor_label(FOG_LABEL)
    fog_component = fog.get_component_by_class(u.ExponentialHeightFogComponent)
    for name, value in fog_rows:
        fog_component.set_editor_property(name, _resolve(u, value))

    local_location = u.Vector(*local_plan['location_ue_cm'])
    if local_fog is None:
        local_fog = actors.spawn_actor_from_class(u.LocalFogVolume, local_location)
        local_fog.set_actor_label(LOCAL_FOG_LABEL)
    local_fog.set_actor_location(local_location, False, False)
    local_fog.set_actor_scale3d(u.Vector(1.0, 1.0, 1.0))
    try:
        _, extent = local_fog.get_actor_bounds(False)
        unit = max(extent.x, extent.y, extent.z)
    except Exception:
        unit = 0.0
    if not 1.0 < unit < 100000.0:
        unit = LOCAL_FOG_UNIT_RADIUS_CM_FALLBACK
    local_plan['unit_radius_cm_measured'] = unit
    local_fog.set_actor_scale3d(u.Vector(*[axis / unit for axis in local_plan['semi_axes_ue_cm']]))
    local_component = local_fog.get_component_by_class(u.LocalFogVolumeComponent)
    for name, value in local_rows:
        local_component.set_editor_property(name, _resolve(u, value))

    data.update(applied=True, before=before, skipped_optional=skipped, other_post_process_volumes=other_ppvs,
                height_fog_actor=fog.get_actor_label())
    if save:
        if not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():
            raise RuntimeError('Reference lighting applied but the level failed to save')
    if write_report:
        (Path(u.Paths.project_dir()) / REPORT_NAME).write_text(json.dumps(data, indent=2) + '\n')
    u.log('SUB01_REFERENCE_LIGHTING_APPLIED ' + json.dumps({'preset': preset, 'when': data['when_jst'],
                                                           'phase': data['phase']}))
    return data


def _ensure_exterior_instance(u, texture, grade):
    """Owned unlit material: photo -> desaturate -> * tint -> * brightness -> emissive."""
    tools = u.AssetToolsHelpers.get_asset_tools()
    mel = u.MaterialEditingLibrary
    parent_path = EXTERIOR_GRADED_DIR + '/' + EXTERIOR_GRADED_MATERIAL
    parent = u.load_asset(parent_path)
    if parent is None:
        parent = tools.create_asset(EXTERIOR_GRADED_MATERIAL, EXTERIOR_GRADED_DIR, u.Material, u.MaterialFactoryNew())
    if not isinstance(parent, u.Material):
        raise RuntimeError('Owned graded exterior path holds a different asset type: ' + parent_path)
    parent.set_editor_property('two_sided', True)
    parent.set_editor_property('shading_model', u.MaterialShadingModel.MSM_UNLIT)
    mel.delete_all_material_expressions(parent)
    sample = mel.create_material_expression(parent, u.MaterialExpressionTextureSample, -900, 0)
    sample.set_editor_property('texture', texture)
    sample.set_editor_property('sampler_type', u.MaterialSamplerType.SAMPLERTYPE_COLOR)
    desat = mel.create_material_expression(parent, u.MaterialExpressionDesaturation, -650, 0)
    fraction = mel.create_material_expression(parent, u.MaterialExpressionScalarParameter, -900, 250)
    fraction.set_editor_property('parameter_name', 'Desaturation')
    tint = mel.create_material_expression(parent, u.MaterialExpressionVectorParameter, -650, 250)
    tint.set_editor_property('parameter_name', 'Tint')
    tint.set_editor_property('default_value', u.LinearColor(1, 1, 1, 1))
    brightness = mel.create_material_expression(parent, u.MaterialExpressionScalarParameter, -400, 250)
    brightness.set_editor_property('parameter_name', 'Brightness')
    brightness.set_editor_property('default_value', 1.0)
    tinted = mel.create_material_expression(parent, u.MaterialExpressionMultiply, -400, 0)
    lit = mel.create_material_expression(parent, u.MaterialExpressionMultiply, -200, 0)
    links = [mel.connect_material_expressions(sample, 'RGB', desat, ''),
             mel.connect_material_expressions(fraction, '', desat, 'Fraction'),
             mel.connect_material_expressions(desat, '', tinted, 'A'),
             mel.connect_material_expressions(tint, '', tinted, 'B'),
             mel.connect_material_expressions(tinted, '', lit, 'A'),
             mel.connect_material_expressions(brightness, '', lit, 'B'),
             mel.connect_material_property(lit, '', u.MaterialProperty.MP_EMISSIVE_COLOR)]
    if not all(links):
        raise RuntimeError('Graded exterior material graph failed to connect (owned asset only; scene untouched)')
    mel.recompile_material(parent)
    instance_path = EXTERIOR_GRADED_DIR + '/' + EXTERIOR_GRADED_INSTANCE
    instance = u.load_asset(instance_path)
    if instance is None:
        instance = tools.create_asset(EXTERIOR_GRADED_INSTANCE, EXTERIOR_GRADED_DIR,
                                      u.MaterialInstanceConstant, u.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(instance, parent)
    mel.set_material_instance_scalar_parameter_value(instance, 'Brightness', grade['brightness'])
    mel.set_material_instance_scalar_parameter_value(instance, 'Desaturation', grade['desaturation'])
    mel.set_material_instance_vector_parameter_value(instance, 'Tint', u.LinearColor(*grade['tint'], 1.0))
    u.EditorAssetLibrary.save_loaded_asset(parent)
    u.EditorAssetLibrary.save_loaded_asset(instance)
    return instance


def set_lamps(states, *, u=None, actor_subsystem=None):
    """Editor: switch practical lamps on/off with authored candela + warm temperature."""
    if u is None:
        import unreal as u  # noqa: N813
    actors = actor_subsystem or u.get_editor_subsystem(u.EditorActorSubsystem)
    planned = lamp_toggle_plan(states)
    found = find_unique_actors(list(actors.get_all_level_actors()), list(planned))
    components = {label: actor.get_component_by_class(u.LightComponent) for label, actor in found.items()}
    missing = [label for label, c in components.items() if c is None]
    if missing:
        raise LightingValidationError('No LightComponent on: ' + ', '.join(missing))
    for label, component in components.items():
        props = planned[label]
        component.set_mobility(u.ComponentMobility.MOVABLE)
        component.set_editor_property('intensity_units', _resolve(u, props['intensity_units']))
        component.set_editor_property('use_temperature', True)
        component.set_editor_property('temperature', props['temperature'])
        component.set_intensity(props['intensity'])
        component.set_visibility(props['visible'], False)
    return planned


def _parse_args(argv):
    parser = argparse.ArgumentParser(description='SUB-01 reference house lighting (dry run unless --apply).')
    parser.add_argument('--preset', default='auto', choices=PRESETS)
    parser.add_argument('--when', help='ISO datetime; naive = JST. Named presets use only its date.')
    parser.add_argument('--north', default='0,-1', help='source-frame north as "x,z" (default 0,-1)')
    parser.add_argument('--exposure', default='clamped_auto', choices=('clamped_auto', 'manual'))
    parser.add_argument('--coordinates', help='unreal-home-setup.json for UE rotations in the dry run')
    parser.add_argument('--apply', action='store_true', help='editor only: validate then apply')
    parser.add_argument('--no-save', action='store_true')
    parser.add_argument('--quit', action='store_true', help='editor only: quit after applying')
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    when = _dt.datetime.fromisoformat(args.when) if args.when else None
    north = tuple(float(v) for v in args.north.split(','))
    if args.apply:
        import unreal as u  # noqa: N813
        try:
            result = apply(args.preset, when, u=u, north_source_xz=north,
                           exposure_mode=args.exposure, save=not args.no_save)
            print(json.dumps({'applied': True, 'phase': result['phase'], 'when_jst': result['when_jst']}))
        finally:
            if args.quit:
                u.SystemLibrary.quit_editor()
        return 0
    coordinates = None
    if args.coordinates:
        coordinates = json.loads(Path(args.coordinates).read_text())['coordinates']
    print(json.dumps(plan(args.preset, when, coordinates, north, args.exposure), indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
