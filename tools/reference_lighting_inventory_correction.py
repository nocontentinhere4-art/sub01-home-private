"""Inventory-guarded, colour-only lighting correction for the actual private home.

Preset ``inventory-corrected``. Root is the only editor operator; this file is
source only and was not run in Unreal by its author.

What the measured inventory shows
(docs/proposed/actual-home-material-bindings-20261014.json, read-only editor dump):
- no PostProcessVolume in /Game/Sub01Home/ActualHome;
- six authored lights; every one has ``use_temperature False`` and a stored
  FColor that equals the authored *linear* colour x 255 (e.g. SUN
  #ffead0 -> linear (1, .823, .631) -> stored (255, 210, 161)). This is what
  tools/unreal_home_lights.py's ``set_light_color(linear, False)`` produces.
  UE interprets ULightComponent::LightColor (an FColor) as sRGB when it builds
  the render colour (FLinearColor(FColor) decodes sRGB), so the authored warm
  tint is applied twice: the SUN renders ~3900 K instead of the intended
  ~5050 K and the BedLamp ~2150 K instead of ~3500 K (McCamy CCT estimates;
  see ``diagnose``). The engine-semantics step is from UE source behaviour and
  must be confirmed by root (Details panel colour of SUB01_AuthoredLight_SUN
  reads #FFD2A1 hex = the stored bytes).

What this changes (small, guarded, idempotent, reversible)
1. Lights: colour only. ``light_color`` -> white and ``use_temperature`` ->
   True with an explicit Kelvin value: SUN 5500 K (warm-leaning daylight),
   lamps 2700-3000 K. Intensities, units, mobility, positions, volumetric and
   shadow settings are NOT touched, because the native runtime hour/lamp
   switch (tools/unreal_native_view_settings.py) rewrites sun/sky/lamp
   intensities but never colour, so a colour fix persists at runtime while an
   intensity fix would be overwritten.
2. One owned unbound PostProcessVolume ``SUB01_ReferencePost``: histogram auto
   exposure bounded to EV100 [-3, +3], white balance 5500 K (= sun key) / tint 0.
   Exposure compensation, speeds and the tone curve stay at engine/project
   defaults (see the doc for the justification of each value).

Guards: the level's lights must match the inventory exactly (same labels and
component classes, nothing extra, nothing missing); no other PostProcessVolume
may exist; each light's current colour state must equal the inventory state or
the already-corrected state (``--allow-drift`` overrides). Everything is
validated before the first mutation. ``--restore`` puts back the recorded
colours and removes the owned volume if this script spawned it.

Order for root: tools/unreal_exterior_backdrop_fix.py -> tools/unreal_home_materials_fix.py
-> this script. Do not combine with tools/reference_home_lighting.py --apply
(its own PostProcessVolume makes this script refuse, by design).

Dry run / diagnosis anywhere:  python3 tools/reference_lighting_inventory_correction.py
Camera shots (UE cm/deg):      python3 tools/reference_lighting_inventory_correction.py --shots
Editor (root):
  UnrealEditor-Cmd <project>/Sub01HomeLab.uproject /Game/Sub01Home/ActualHome \
    -ExecutePythonScript="<repo>/tools/reference_lighting_inventory_correction.py --apply --preset inventory-corrected --quit" -unattended -nosplash
  rollback: same with "--restore --quit"
"""
import argparse
import json
import math
import re
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = REPO / 'docs/proposed/actual-home-material-bindings-20261014.json'
INVENTORY_SCHEMA = 'sub01-private-actual-visual-inventory-v1'
LEVEL_PATH = '/Game/Sub01Home/ActualHome'
PRESET = 'inventory-corrected'
PPV_LABEL = 'SUB01_ReferencePost'
REPORT_NAME = 'reference-lighting-inventory-correction.json'
LABEL_PREFIX = 'SUB01_AuthoredLight_'

# Target colour temperatures (K). Daylight 5500 K: inside the 5500-6500 K
# daylight band, at its warm end (the reference's warm daylight); lamps are
# incandescent/LED warm white 2700-3000 K.
TARGET_TEMPERATURE_K = {
    'SUB01_AuthoredLight_SUN': 5500.0,
    'SUB01_AuthoredLight_DeskLamp': 2900.0,
    'SUB01_AuthoredLight_BedLamp': 2700.0,
    'SUB01_AuthoredLight_KitchenWork': 3000.0,
    'SUB01_AuthoredLight_LowerPendant': 2800.0,
    'SUB01_AuthoredLight_UpperPendant': 2800.0,
}
WHITE = (255, 255, 255, 255)

# Post process (EV100 needs the project's extended luminance range, checked).
# White balance = the sun key, so a neutral ivory lit by the key renders neutral
# (materials are judged under a neutral key; warmth comes from lamps/golden hour).
WHITE_BALANCE_K = TARGET_TEMPERATURE_K['SUB01_AuthoredLight_SUN']
EXPOSURE_MIN_EV100 = -3.0
EXPOSURE_MAX_EV100 = 3.0
POST_SETTINGS = (
    ('auto_exposure_method', {'enum': 'AutoExposureMethod', 'value': 'AEM_HISTOGRAM'}),
    ('auto_exposure_min_brightness', EXPOSURE_MIN_EV100),
    ('auto_exposure_max_brightness', EXPOSURE_MAX_EV100),
    ('white_temp', WHITE_BALANCE_K),
    ('white_tint', 0.0),
)
NOT_OVERRIDDEN = {
    'auto_exposure_bias': 'project default; keeps the backdrop fix and current baseline brightness unchanged',
    'auto_exposure_speed_up/down': 'engine defaults (3 / 1 EV/s)',
    'tone curve (film_slope/toe/shoulder/black_clip/white_clip)': 'engine filmic defaults; materials are judged on them',
    'bloom, vignette, local exposure, Lumen methods': 'unchanged; Lumen GI/reflections already set in DefaultEngine.ini',
}

# Materials doc (docs/proposed/home-materials-fix.md section 6) shot positions, UE cm.
SHOTS = (
    ('bed close-up', (-100, -100, 420), (-240, -260, 355)),
    ('sofa', (-160, 10, 140), (-360, 10, 60)),
    ('desk + wood floor', (200, -75, 165), (200, -300, 75)),
    ('kitchen', (-180, -180, 165), (-220, -350, 120)),
)


class CorrectionRefused(RuntimeError):
    """Raised before any mutation."""


# --------------------------------------------------------------------------
# Inventory parsing (pure)
# --------------------------------------------------------------------------
_COLOR = re.compile(r"\{b: (\d+), g: (\d+), r: (\d+), a: (\d+)\}")
_UNITS = re.compile(r"LightUnits\.(\w+)")


def parse_fcolor(text):
    """'<Struct 'Color' (...) {b: 161, g: 210, r: 255, a: 255}>' -> (r, g, b, a)."""
    match = _COLOR.search(text or '')
    if not match:
        raise ValueError('Unparseable light_color: %r' % (text,))
    b, g, r, a = (int(v) for v in match.groups())
    return (r, g, b, a)


def load_inventory(path=DEFAULT_INVENTORY):
    data = json.loads(Path(path).read_text())
    if data.get('schema') != INVENTORY_SCHEMA or data.get('read_only') is not True:
        raise CorrectionRefused('Not a read-only visual inventory: %s' % path)
    if not str(data.get('level', '')).startswith(LEVEL_PATH):
        raise CorrectionRefused('Inventory is for another level: %s' % data.get('level'))
    lights = {}
    for row in data.get('lights', []):
        label = row['actor']
        if label in lights:
            raise CorrectionRefused('Inventory lists %s twice' % label)
        units = _UNITS.search(str(row.get('intensity_units', '')))
        lights[label] = {
            'class': row['class'], 'intensity': float(row['intensity']),
            'units': 'LUX' if row['class'] == 'DirectionalLightComponent' else (units.group(1) if units else None),
            'light_color': parse_fcolor(row['light_color']),
            'use_temperature': bool(row.get('use_temperature')),
            'temperature': float(row.get('temperature', 6500.0)),
        }
    return {'level': data['level'], 'lights': lights, 'post_processing': list(data.get('post_processing', []))}


# --------------------------------------------------------------------------
# Colour science (pure)
# --------------------------------------------------------------------------
def srgb_decode(byte):
    c = byte / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def cct_mccamy(linear_rgb):
    """Approximate CCT (K) of a linear sRGB/Rec.709 colour (McCamy 1992)."""
    r, g, b = linear_rgb
    x_ = 0.4124 * r + 0.3576 * g + 0.1805 * b
    y_ = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z_ = 0.0193 * r + 0.1192 * g + 0.9505 * b
    s = x_ + y_ + z_
    x, y = x_ / s, y_ / s
    n = (x - 0.3320) / (0.1858 - y)
    return 449 * n ** 3 + 3525 * n ** 2 + 6823.3 * n + 5520.33


def effective_light(light):
    """Colour UE actually renders: FColor decoded as sRGB, or blackbody when use_temperature."""
    r, g, b, _ = light['light_color']
    effective = tuple(srgb_decode(v) for v in (r, g, b))
    authored = tuple(v / 255.0 for v in (r, g, b))  # what the authoring code meant (linear)
    cct = cct_mccamy(effective) if (r, g, b) != (255, 255, 255) else 6500.0
    if light['use_temperature']:
        cct = None  # tint x blackbody; not estimated
    return {'effective_linear': [round(v, 4) for v in effective],
            'authored_linear': [round(v, 4) for v in authored],
            'effective_cct_k': None if cct is None else round(cct),
            'authored_cct_k': round(cct_mccamy(authored)) if (r, g, b) != (255, 255, 255) else 6500,
            'double_srgb_decode': (r, g, b) != (255, 255, 255) and not light['use_temperature']}


def lambert_luminance(lux, albedo):
    return lux * albedo / math.pi


def ev100(luminance_nits):
    """Exposure value at ISO 100 for a luminance (K = 12.5, as UE's auto exposure)."""
    return math.log2(luminance_nits * 100.0 / 12.5)


EXPOSURE_ESTIMATES = {
    # (description, illuminance lux, albedo)
    'day: sunlit cream wall, sun 3.09 lux at normal incidence': (3.09, 0.7),
    'day: sky-lit wall, ~1/10 of the sun patch': (0.309, 0.7),
    'day: deep interior, ~1/50 of the sun patch': (0.0618, 0.7),
    'night: desk 12 cd at 1 m (12 lux)': (12.0, 0.7),
    'night: wall 2.5 m from a 10 cd pendant (1.6 lux)': (1.6, 0.7),
    'physical: wall in real 100 klux sun': (100000.0, 0.7),
}


def exposure_table():
    return {name: {'lux': lux, 'luminance_nits': round(lambert_luminance(lux, a), 4),
                   'ev100': round(ev100(lambert_luminance(lux, a)), 2)}
            for name, (lux, a) in EXPOSURE_ESTIMATES.items()}


def diagnose(inventory):
    lights = []
    for label, light in inventory['lights'].items():
        row = dict(actor=label, cls=light['class'], intensity=light['intensity'], units=light['units'],
                   light_color_fcolor=list(light['light_color']), use_temperature=light['use_temperature'],
                   temperature_k=light['temperature'],
                   mobility='not recorded in inventory (authored code sets Movable)',
                   volumetric_scattering='not recorded in inventory',
                   ies_profile='not recorded in inventory (authored code sets none)')
        row.update(effective_light(light))
        row['target_temperature_k'] = TARGET_TEMPERATURE_K.get(label)
        lights.append(row)
    sun = inventory['lights'].get(LABEL_PREFIX + 'SUN')
    sun_eff = effective_light(sun) if sun else None
    findings = {
        'sun_stored_hex': sun and '#%02x%02x%02x' % sun['light_color'][:3],
        'sun_authored_hex_in_source': '#ffead0 (tools/unreal_home_lights.py; same value one sRGB decode earlier)',
        'sun_effective_cct_k': sun_eff and sun_eff['effective_cct_k'],
        'sun_effective_below_daylight_k': sun_eff and [5500 - sun_eff['effective_cct_k'], 6500 - sun_eff['effective_cct_k']],
        'post_process_volumes': len(inventory['post_processing']),
        'sun_lux': sun and sun['intensity'],
        'sun_vs_physical_factor': sun and round(100000.0 / sun['intensity']),
        'lamp_units': sorted({l['units'] for k, l in inventory['lights'].items() if not k.endswith('SUN')}),
        'lamps_currently_off_in_editor': all(l['intensity'] == 0 for k, l in inventory['lights'].items()
                                             if not k.endswith('SUN')),
    }
    return {'lights': lights, 'findings': findings, 'exposure_estimates': exposure_table()}


# --------------------------------------------------------------------------
# Plan, shots (pure)
# --------------------------------------------------------------------------
def light_target(label):
    return {'light_color': WHITE, 'use_temperature': True, 'temperature': TARGET_TEMPERATURE_K[label]}


def light_state_matches(state, target):
    return (tuple(state['light_color']) == tuple(target['light_color'])
            and bool(state['use_temperature']) == bool(target['use_temperature'])
            and abs(float(state['temperature']) - float(target['temperature'])) < 0.5)


def plan(inventory):
    unknown = sorted(set(inventory['lights']) - set(TARGET_TEMPERATURE_K))
    missing = sorted(set(TARGET_TEMPERATURE_K) - set(inventory['lights']))
    if unknown or missing:
        raise CorrectionRefused('Inventory lights differ from the expected six (unknown %s, missing %s)'
                                % (unknown, missing))
    return {
        'preset': PRESET, 'level': LEVEL_PATH,
        'lights': {label: {'from': {'light_color': list(l['light_color']), 'use_temperature': l['use_temperature'],
                                    'temperature': l['temperature']},
                           'to': dict(light_target(label), light_color=list(WHITE))}
                   for label, l in inventory['lights'].items()},
        'unchanged_light_properties': ['intensity', 'intensity_units', 'mobility', 'transform',
                                       'volumetric_scattering_intensity', 'shadows', 'attenuation'],
        'post_process': {'label': PPV_LABEL, 'unbound': True, 'priority': 0.0, 'blend_weight': 1.0,
                         'settings': [{'property': p, 'value': v} for p, v in POST_SETTINGS],
                         'not_overridden': NOT_OVERRIDDEN},
        'order': ['tools/unreal_exterior_backdrop_fix.py', 'tools/unreal_home_materials_fix.py', PRESET],
        'visual_match_claimed': False,
    }


def look_at_rotation(camera, target):
    dx, dy, dz = (t - c for c, t in zip(camera, target))
    return {'pitch': round(math.degrees(math.atan2(dz, math.hypot(dx, dy))), 2),
            'yaw': round(math.degrees(math.atan2(dy, dx)), 2), 'roll': 0.0}


def shots():
    return [{'shot': name, 'location_cm': list(cam), 'look_at_cm': list(tgt),
             'rotation_deg': look_at_rotation(cam, tgt)} for name, cam, tgt in SHOTS]


# --------------------------------------------------------------------------
# Editor (validated first; injected ``u`` in tests)
# --------------------------------------------------------------------------
def _light_components(u, actors):
    rows = {}
    for actor in actors:
        for component in actor.get_components_by_class(u.LightComponent):
            rows.setdefault(actor.get_actor_label(), []).append(component)
    return rows


def _state(component):
    color = component.get_editor_property('light_color')
    return {'light_color': (int(color.r), int(color.g), int(color.b), int(color.a)),
            'use_temperature': bool(component.get_editor_property('use_temperature')),
            'temperature': float(component.get_editor_property('temperature'))}


def validate(u, actors, inventory, allow_drift=False, restoring=False):
    """Return a context, or raise CorrectionRefused without changing anything."""
    problems = []
    found = _light_components(u, actors)
    expected = inventory['lights']
    for label in sorted(set(found) | set(expected)):
        comps = found.get(label, [])
        if label not in expected:
            problems.append('unexpected light actor not in inventory: ' + label)
        elif not comps:
            problems.append('inventory light missing in level: ' + label)
        elif len(comps) != 1:
            problems.append('%s has %d light components' % (label, len(comps)))
        elif comps[0].get_class().get_name() != expected[label]['class']:
            problems.append('%s class %s != inventory %s' % (label, comps[0].get_class().get_name(),
                                                            expected[label]['class']))
    ppvs = [a for a in actors if isinstance(a, u.PostProcessVolume)]
    owned = [a for a in ppvs if a.get_actor_label() == PPV_LABEL]
    foreign = [a.get_actor_label() for a in ppvs if a.get_actor_label() != PPV_LABEL]
    if foreign:
        problems.append('unexpected PostProcessVolume(s) not in inventory: ' + ', '.join(foreign))
    if len(owned) > 1:
        problems.append('%s is duplicated' % PPV_LABEL)
    states = {}
    if not problems:
        for label in expected:
            component = found[label][0]
            for prop in ('light_color', 'use_temperature', 'temperature'):
                try:
                    component.get_editor_property(prop)
                except Exception:
                    problems.append('%s lacks %s' % (label, prop))
            if problems:
                continue
            state = _state(component)
            states[label] = state
            if not restoring and not allow_drift and not (
                    light_state_matches(state, expected[label]) or light_state_matches(state, light_target(label))):
                problems.append('%s colour state %s matches neither the inventory nor the corrected target '
                                '(use --allow-drift after checking)' % (label, state))
    probe = u.PostProcessSettings()
    for prop, value in POST_SETTINGS:
        for name in (prop, 'override_' + prop):
            try:
                probe.get_editor_property(name)
            except Exception:
                problems.append('PostProcessSettings lacks ' + name)
    try:
        extended = u.get_default_object(u.RendererSettings).get_editor_property(
            'extend_default_luminance_range_in_auto_exposure_settings')
    except Exception:
        extended = None
    if extended is False:
        problems.append('auto exposure bounds would not be EV100 (extended luminance range is off)')
    if problems:
        raise CorrectionRefused('Refusing %s, no changes made: %s' % (PRESET, '; '.join(problems)))
    return {'components': {label: found[label][0] for label in expected}, 'states': states,
            'ppv': owned[0] if owned else None, 'ev100_extended_range': extended}


def _resolve(u, value):
    if isinstance(value, dict) and 'enum' in value:
        return getattr(getattr(u, value['enum']), value['value'])
    return value


def _set_light(u, component, state):
    r, g, b, a = state['light_color']
    # bSRGB=False stores the bytes exactly (ToFColor without gamma), matching the recorded FColor.
    component.set_light_color(u.LinearColor(r / 255.0, g / 255.0, b / 255.0, a / 255.0), False)
    component.set_editor_property('use_temperature', bool(state['use_temperature']))
    component.set_editor_property('temperature', float(state['temperature']))


def _backup_map(u):
    root = Path(u.Paths.project_dir())
    map_file = root / 'Content/Sub01Home/ActualHome.umap'
    if not map_file.is_file():
        raise CorrectionRefused('Actual saved map missing; no recoverable change')
    backup = root / 'Saved/PrivateMapBackups' / ('%d-lighting-inventory-correction' % time.time_ns())
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(map_file, backup / map_file.name)
    for folder in ('__ExternalActors__', '__ExternalObjects__'):
        path = root / 'Content' / folder / 'Sub01Home/ActualHome'
        if path.exists():
            shutil.copytree(path, backup / folder)
    return str(backup)


def run(inventory_path=DEFAULT_INVENTORY, *, u=None, actor_subsystem=None, allow_drift=False,
        load_level=True, save=True, backup=True, write_report=True):
    if u is None:
        import unreal as u  # noqa: N813
    inventory = load_inventory(inventory_path)
    data = plan(inventory)
    if load_level and not u.get_editor_subsystem(u.LevelEditorSubsystem).load_level(LEVEL_PATH):
        raise CorrectionRefused('Actual home map is missing')
    actors_sub = actor_subsystem or u.get_editor_subsystem(u.EditorActorSubsystem)
    actors = list(actors_sub.get_all_level_actors())
    ctx = validate(u, actors, inventory, allow_drift)
    report_path = Path(u.Paths.project_dir()) / REPORT_NAME if write_report else None
    previous = json.loads(report_path.read_text()) if report_path and report_path.is_file() else {}
    # Keep the ORIGINAL pre-correction state across idempotent re-runs.
    before = previous.get('before') or {label: dict(s, light_color=list(s['light_color']))
                                        for label, s in ctx['states'].items()}
    spawned = bool(previous.get('ppv_spawned_by_this_script')) or ctx['ppv'] is None
    backup_dir = _backup_map(u) if (backup and save) else None
    changed = []
    for label, component in ctx['components'].items():
        target = light_target(label)
        if not light_state_matches(ctx['states'][label], target):
            _set_light(u, component, target)
            changed.append(label)
    ppv = ctx['ppv']
    if ppv is None:
        ppv = actors_sub.spawn_actor_from_class(u.PostProcessVolume, u.Vector(0, 0, 0))
        ppv.set_actor_label(PPV_LABEL)
    ppv.set_editor_property('unbound', True)
    ppv.set_editor_property('priority', data['post_process']['priority'])
    ppv.set_editor_property('blend_weight', data['post_process']['blend_weight'])
    settings = ppv.get_editor_property('settings')
    for prop, value in POST_SETTINGS:
        settings.set_editor_property('override_' + prop, True)
        settings.set_editor_property(prop, _resolve(u, value))
    ppv.set_editor_property('settings', settings)
    if save and not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():
        raise RuntimeError('Correction applied but the level failed to save; restore from ' + str(backup_dir))
    data.update(applied=True, before=before, changed_lights=changed, ppv_spawned_by_this_script=spawned,
                backup=backup_dir, ev100_extended_range=ctx['ev100_extended_range'])
    if report_path:
        report_path.write_text(json.dumps(data, indent=2) + '\n')
    u.log('SUB01_LIGHTING_INVENTORY_CORRECTION changed=%d spawned_ppv=%s' % (len(changed), spawned))
    return data


def restore(inventory_path=DEFAULT_INVENTORY, *, u=None, actor_subsystem=None, save=True, report=None):
    if u is None:
        import unreal as u  # noqa: N813
    report_path = Path(u.Paths.project_dir()) / REPORT_NAME
    record = report if report is not None else (json.loads(report_path.read_text()) if report_path.is_file() else None)
    if not record or 'before' not in record:
        raise CorrectionRefused('No correction report to restore from: ' + str(report_path))
    inventory = load_inventory(inventory_path)
    actors_sub = actor_subsystem or u.get_editor_subsystem(u.EditorActorSubsystem)
    actors = list(actors_sub.get_all_level_actors())
    ctx = validate(u, actors, inventory, restoring=True)
    if set(record['before']) != set(ctx['components']):
        raise CorrectionRefused('Report lights differ from the level; refusing restore')
    for label, component in ctx['components'].items():
        _set_light(u, component, record['before'][label])
    if ctx['ppv'] is not None and record.get('ppv_spawned_by_this_script'):
        actors_sub.destroy_actor(ctx['ppv'])
    if save and not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():
        raise RuntimeError('Restore applied but the level failed to save')
    if report is None and report_path.is_file():
        report_path.rename(report_path.with_suffix('.restored.json'))
    return {'restored': sorted(record['before']), 'ppv_removed': bool(ctx['ppv'] and record.get('ppv_spawned_by_this_script'))}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Inventory-guarded lighting colour + post correction.')
    parser.add_argument('--preset', default=PRESET, choices=(PRESET,))
    parser.add_argument('--inventory', default=str(DEFAULT_INVENTORY))
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--restore', action='store_true')
    parser.add_argument('--allow-drift', action='store_true')
    parser.add_argument('--no-save', action='store_true')
    parser.add_argument('--shots', action='store_true', help='print the four camera positions/rotations')
    parser.add_argument('--quit', action='store_true')
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.shots:
        print(json.dumps(shots(), indent=2))
        return 0
    if args.apply or args.restore:
        import unreal as u  # noqa: N813
        try:
            result = (restore(args.inventory, u=u, save=not args.no_save) if args.restore else
                      run(args.inventory, u=u, allow_drift=args.allow_drift, save=not args.no_save))
            print(json.dumps({k: result[k] for k in result if k in ('applied', 'changed_lights', 'restored')}))
        finally:
            if args.quit:
                u.SystemLibrary.quit_editor()
        return 0
    inventory = load_inventory(args.inventory)
    print(json.dumps({'diagnosis': diagnose(inventory), 'plan': plan(inventory)}, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
