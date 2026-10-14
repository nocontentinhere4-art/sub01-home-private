"""Level the native Tokyo exterior backdrop and give it a real night grade.

Root runs this in the sole UE editor (gameplay stopped), AFTER
tools/unreal_home_exterior.py and independent of the finite courtyard
(tools/unreal_extend_private_entry.py) and duplicate-sky correction
(tools/unreal_remove_duplicate_private_sky.py). It owns only:
  /Game/Sub01Home/Environment/BackdropFix/M_Sub01TokyoBackdropLevel
  /Game/Sub01Home/Environment/BackdropFix/MI_Sub01TokyoBackdropLevel
  /Game/Sub01Home/Environment/BackdropFix/MPC_Sub01ExteriorTime
and changes exactly one existing actor, SUB01_ActualHistoricalTokyoBackground:
its rotation becomes (pitch 0, yaw 0, roll 0) and its slot-0 material becomes
the owned instance. Location (eye height), 2 km scale, collision and shadows
are kept. The original texture and M_Sub01ActualTokyoBackground are not edited.

Why: tools/unreal_home_exterior.py:80 calls ``u.Rotator(0, -90, 0)``. UE
Python's positional order is (roll, pitch, yaw), so that is PITCH -90, not the
C++ FRotator(0,-90,0) yaw it reads like; and its material samples the Engine
sphere's own mesh UVs. The owned material instead derives equirectangular UVs
from the view direction (see tools/exterior_backdrop_geometry.py), so the
horizon is at eye height for every yaw, independent of mesh UVs and rotation.
Night: lerp of graded parameters driven by MPC scalars Daylight/GoldenWeight;
presets write the MPC defaults, the native hour hook (proposed diff) sets them
at runtime. Exposure-locked (EyeAdaptationInverse) when the engine has it, so
night auto-exposure cannot lift the dark photo back to daytime brightness.

Validates everything before the first mutation; refuses on a missing or
duplicated backdrop, missing texture, non-2:1 image, courtyard outside the
sphere margin, or missing engine classes. Idempotent: a second run with the
same arguments reuses the owned assets, skips the graph rebuild (metadata
version tag) and makes no actor change.

Root (GPU editor, private server only):
  UnrealEditor-Cmd <Project>.uproject /Game/Sub01Home/ActualHome \
    -ExecutePythonScript="<repo>/tools/unreal_exterior_backdrop_fix.py --apply --preset night --quit"
Dry run anywhere: python3 tools/unreal_exterior_backdrop_fix.py --preset night
Rollback: ... -ExecutePythonScript="<repo>/tools/unreal_exterior_backdrop_fix.py --restore --quit"
"""
import argparse
import datetime as _dt
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import exterior_backdrop_geometry as geo  # noqa: E402  (pure)

LEVEL_PATH = '/Game/Sub01Home/ActualHome'
EXTERIOR_LABEL = 'SUB01_ActualHistoricalTokyoBackground'
EXTERIOR_TEXTURE = '/Game/Sub01Home/Environment/TokyoResidential'
SOURCE_IMAGE = 'SourceAssets/TokyoResidential.png'
COURTYARD_PREFIX = 'SUB01_PrivateEntry_'
SKY_LABEL = 'SUB01_ActualHDR_Sky'
REPORT_NAME = 'exterior-backdrop-fix.json'
GRAPH_TAG = 'sub01_backdrop_graph'
GRAPH_VERSION = hashlib.sha256((geo.HLSL + repr(geo.CUSTOM_INPUTS) + 'v1').encode()).hexdigest()[:16]
REQUIRED_CLASSES = ('Material', 'MaterialFactoryNew', 'MaterialInstanceConstant',
                    'MaterialInstanceConstantFactoryNew', 'MaterialParameterCollection',
                    'MaterialParameterCollectionFactoryNew', 'CollectionScalarParameter',
                    'MaterialExpressionCustom', 'CustomInput', 'MaterialExpressionCameraVectorWS',
                    'MaterialExpressionTextureSample', 'MaterialExpressionScalarParameter',
                    'MaterialExpressionVectorParameter', 'MaterialExpressionCollectionParameter',
                    'MaterialExpressionLinearInterpolate', 'MaterialExpressionPower',
                    'MaterialExpressionDesaturation', 'MaterialExpressionMultiply',
                    'StaticMeshComponent', 'Texture2D')


class BackdropFixError(RuntimeError):
    """Raised before any mutation when the level or engine is not as expected."""


def plan(preset='night', when=None, yaw_deg=geo.DEFAULT_YAW_DEG, pitch_fix=0.0, roll_fix=0.0,
         horizon_v=geo.HORIZON_V):
    factors = geo.preset_factors(preset, when)
    return {'schema': 'sub01.exterior-backdrop-fix.v1', 'level': LEVEL_PATH, 'actor': EXTERIOR_LABEL,
            'rotation': geo.leveled_rotation(), 'factors': factors,
            'grade_now': geo.blended_grade(factors['Daylight'], factors['GoldenWeight']),
            'scalars': {'YawDegrees': yaw_deg, 'PhotoPitchFix': pitch_fix, 'PhotoRollFix': roll_fix,
                        'HorizonV': horizon_v,
                        **{side + key.capitalize(): grade[key] for side, grade in
                           (('Day', geo.GRADE_DAY), ('Night', geo.GRADE_NIGHT), ('Golden', geo.GRADE_GOLDEN))
                           for key in ('brightness', 'desaturation', 'gamma')}},
            'vectors': {side + 'Tint': list(grade['tint']) for side, grade in
                        (('Day', geo.GRADE_DAY), ('Night', geo.GRADE_NIGHT), ('Golden', geo.GRADE_GOLDEN))},
            'assets': {'material': geo.OWNED_DIR + '/' + geo.MATERIAL_NAME, 'instance': geo.INSTANCE_PATH,
                       'collection': geo.COLLECTION_PATH},
            'eye_height_cm': geo.EYE_HEIGHT_CM, 'graph_version': GRAPH_VERSION,
            'night_window_lights': 'none: no real emissive mask exists for this capture'}


# --------------------------------------------------------------------------
# Validation (no mutation)
# --------------------------------------------------------------------------
def _world_bounds(u, component):
    lo, hi = component.get_local_bounds()
    t = component.get_world_transform()
    pts = [t.transform_location(u.Vector(x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
    return {'min': [min(getattr(p, k) for p in pts) for k in 'xyz'],
            'max': [max(getattr(p, k) for p in pts) for k in 'xyz']}


def validate(u, actors, project_dir, data, exposure_lock='auto'):
    problems = [name for name in REQUIRED_CLASSES if not hasattr(u, name)]
    if problems:
        raise BackdropFixError('Engine lacks: ' + ', '.join(problems))
    all_actors = list(actors.get_all_level_actors())
    backdrops = [a for a in all_actors if a.get_actor_label() == EXTERIOR_LABEL]
    if len(backdrops) != 1:
        raise BackdropFixError('Expected exactly one %s, found %d' % (EXTERIOR_LABEL, len(backdrops)))
    actor = backdrops[0]
    meshes = actor.get_components_by_class(u.StaticMeshComponent)
    if len(meshes) != 1:
        raise BackdropFixError('Backdrop must have exactly one StaticMeshComponent')
    mesh = meshes[0]
    if mesh.get_collision_enabled() != u.CollisionEnabled.NO_COLLISION:
        raise BackdropFixError('Backdrop collision differs from the measured scene (expected NoCollision)')
    texture = u.load_asset(EXTERIOR_TEXTURE)
    if texture is None or not isinstance(texture, u.Texture2D):
        raise BackdropFixError('Exterior texture missing: ' + EXTERIOR_TEXTURE)
    size = (int(texture.blueprint_get_size_x()), int(texture.blueprint_get_size_y()))
    try:
        image = geo.require_equirect(*size)
    except ValueError as error:
        raise BackdropFixError(str(error)) from None
    source = Path(project_dir) / SOURCE_IMAGE
    source_size = geo.image_size(source) if source.is_file() else None
    if source_size is not None and source_size != size:
        raise BackdropFixError('Imported texture %s differs from %s %s' % (size, SOURCE_IMAGE, source_size))
    courtyard = []
    for other in all_actors:
        if other.get_actor_label().startswith(COURTYARD_PREFIX):
            for component in other.get_components_by_class(u.StaticMeshComponent):
                courtyard.append(_world_bounds(u, component))
    location = actor.get_actor_location()
    center = (location.x, location.y, location.z)
    box = mesh.get_editor_property('static_mesh').get_bounding_box()
    scale = actor.get_actor_scale3d()
    radius = max(abs(box.max.x), abs(box.min.x)) * min(scale.x, scale.y, scale.z)
    ok, worst = geo.courtyard_clear(courtyard, center, radius)
    if not ok:
        raise BackdropFixError('Courtyard reaches %.0f cm, inside-sphere limit %.0f cm' % (worst, radius - geo.COURTYARD_MARGIN_CM))
    lock = hasattr(u, 'MaterialExpressionEyeAdaptationInverse') if exposure_lock == 'auto' else exposure_lock == 'on'
    if lock and not hasattr(u, 'MaterialExpressionEyeAdaptationInverse'):
        raise BackdropFixError('Exposure lock requested but engine lacks MaterialExpressionEyeAdaptationInverse')
    rotation = actor.get_actor_rotation()
    current = mesh.get_material(0)
    return {'actor': actor, 'mesh': mesh, 'texture': texture, 'image': image, 'source_size': source_size,
            'courtyard_boxes': len(courtyard), 'courtyard_max_distance_cm': worst, 'radius_cm': radius,
            'center_cm': list(center), 'exposure_lock': lock,
            'skies': sum(1 for a in all_actors if a.get_actor_label() == SKY_LABEL),
            'before': {'rotation': {'pitch': rotation.pitch, 'yaw': rotation.yaw, 'roll': rotation.roll},
                       'material': current.get_path_name() if current else None}}


# --------------------------------------------------------------------------
# Owned assets
# --------------------------------------------------------------------------
def _load_or_create(u, name, cls, factory):
    path = geo.OWNED_DIR + '/' + name
    asset = u.load_asset(path)
    created = asset is None
    if created:
        asset = u.AssetToolsHelpers.get_asset_tools().create_asset(name, geo.OWNED_DIR, getattr(u, cls), getattr(u, factory)())
    if asset is None or not isinstance(asset, getattr(u, cls)):
        raise BackdropFixError('Owned path holds a different asset type: ' + path)
    return asset, created


def ensure_collection(u, values):
    collection, created = _load_or_create(u, geo.COLLECTION_NAME, 'MaterialParameterCollection',
                                          'MaterialParameterCollectionFactoryNew')
    params = list(collection.get_editor_property('scalar_parameters') or [])
    names = [str(p.get_editor_property('parameter_name')) for p in params]
    changed = created
    for name in geo.COLLECTION_PARAMETERS:
        if name not in names:
            p = u.CollectionScalarParameter()
            p.set_editor_property('parameter_name', name)
            params.append(p)
            names.append(name)
            changed = True
    for p in params:
        name = str(p.get_editor_property('parameter_name'))
        if name in values and abs(float(p.get_editor_property('default_value')) - values[name]) > 1e-6:
            p.set_editor_property('default_value', float(values[name]))
            changed = True
    if changed:
        collection.set_editor_property('scalar_parameters', params)
        u.EditorAssetLibrary.save_loaded_asset(collection)
    return collection, changed


def build_material(u, texture, collection, exposure_lock):
    material, created = _load_or_create(u, geo.MATERIAL_NAME, 'Material', 'MaterialFactoryNew')
    version = GRAPH_VERSION + ('-lock' if exposure_lock else '-nolock')
    if not created and u.EditorAssetLibrary.get_metadata_tag(material, GRAPH_TAG) == version:
        return material, False
    mel = u.MaterialEditingLibrary
    material.set_editor_property('two_sided', True)
    material.set_editor_property('shading_model', u.MaterialShadingModel.MSM_UNLIT)
    mel.delete_all_material_expressions(material)
    links = []

    def node(cls, x, y, **props):
        expression = mel.create_material_expression(material, getattr(u, cls), x, y)
        for key, value in props.items():
            expression.set_editor_property(key, value)
        return expression

    def link(a, out, b, inp):
        links.append((a, out, b, inp, mel.connect_material_expressions(a, out, b, inp)))

    def scalar(name, default, x, y):
        return node('MaterialExpressionScalarParameter', x, y, parameter_name=name, default_value=float(default))

    camera = node('MaterialExpressionCameraVectorWS', -2200, 0)
    inputs = []
    for name in geo.CUSTOM_INPUTS:
        item = u.CustomInput()
        item.set_editor_property('input_name', name)
        inputs.append(item)
    custom = node('MaterialExpressionCustom', -1900, 0, code=geo.HLSL, description='Sub01LeveledEquirectUV',
                  output_type=u.CustomMaterialOutputType.CMOT_FLOAT2, inputs=inputs)
    link(camera, '', custom, 'CamVec')
    for i, (name, default) in enumerate((('YawDegrees', geo.DEFAULT_YAW_DEG), ('PhotoPitchFix', 0.0),
                                         ('PhotoRollFix', 0.0), ('HorizonV', geo.HORIZON_V))):
        link(scalar(name, default, -2200, 150 + 100 * i), '', custom, geo.CUSTOM_INPUTS[i + 1])
    # Mip 0 sampling: no derivative seam at the atan2 wrap; at 11.4 texels/degree
    # the 4096 capture is magnified at the native 50-110 deg FOV, so no aliasing.
    sample = node('MaterialExpressionTextureSample', -1600, 0, texture=texture,
                  sampler_type=u.MaterialSamplerType.SAMPLERTYPE_COLOR,
                  mip_value_mode=u.TextureMipValueMode.TMVM_MIP_LEVEL, const_mip_value=0)
    link(custom, '', sample, 'UVs')
    daylight = node('MaterialExpressionCollectionParameter', -1600, 500, collection=collection, parameter_name='Daylight')
    golden = node('MaterialExpressionCollectionParameter', -1600, 600, collection=collection, parameter_name='GoldenWeight')

    def blended(key, vector, y):
        make = (lambda side, x: node('MaterialExpressionVectorParameter', x, y, parameter_name=side + 'Tint',
                                     default_value=u.LinearColor(*getattr(geo, 'GRADE_' + side.upper())['tint'], 1.0))) \
            if vector else (lambda side, x: scalar(side + key, getattr(geo, 'GRADE_' + side.upper())[key.lower()], x, y))
        night, day, gold = make('Night', -1300), make('Day', -1300), make('Golden', -1300)
        first = node('MaterialExpressionLinearInterpolate', -1100, y)
        link(night, '', first, 'A'); link(day, '', first, 'B'); link(daylight, '', first, 'Alpha')
        second = node('MaterialExpressionLinearInterpolate', -950, y)
        link(first, '', second, 'A'); link(gold, '', second, 'B'); link(golden, '', second, 'Alpha')
        return second

    gamma, desat, tint, bright = (blended('Gamma', False, 300), blended('Desaturation', False, 450),
                                  blended('Tint', True, 600), blended('Brightness', False, 750))
    power = node('MaterialExpressionPower', -1300, 0)
    link(sample, 'RGB', power, 'Base'); link(gamma, '', power, 'Exponent')
    gray = node('MaterialExpressionDesaturation', -1100, 0)
    link(power, '', gray, ''); link(desat, '', gray, 'Fraction')
    tinted = node('MaterialExpressionMultiply', -900, 0)
    link(gray, '', tinted, 'A'); link(tint, '', tinted, 'B')
    lit = node('MaterialExpressionMultiply', -700, 0)
    link(tinted, '', lit, 'A'); link(bright, '', lit, 'B')
    final = lit
    if exposure_lock:
        inverse = node('MaterialExpressionEyeAdaptationInverse', -700, 200)
        final = node('MaterialExpressionMultiply', -500, 0)
        link(lit, '', final, 'A'); link(inverse, '', final, 'B')
    ok = mel.connect_material_property(final, '', u.MaterialProperty.MP_EMISSIVE_COLOR)
    failed = [(type(a).__name__, o, type(b).__name__, i) for a, o, b, i, r in links if not r]
    if failed or not ok:
        raise BackdropFixError('Owned material graph failed to connect (scene untouched): %s' % failed)
    mel.recompile_material(material)
    u.EditorAssetLibrary.set_metadata_tag(material, GRAPH_TAG, version)
    u.EditorAssetLibrary.save_loaded_asset(material)
    return material, True


def ensure_instance(u, material, data):
    instance, created = _load_or_create(u, geo.INSTANCE_NAME, 'MaterialInstanceConstant',
                                        'MaterialInstanceConstantFactoryNew')
    mel = u.MaterialEditingLibrary
    changed = created or instance.get_editor_property('parent') != material
    if changed:
        mel.set_material_instance_parent(instance, material)
    for name, value in data['scalars'].items():
        if abs(mel.get_material_instance_scalar_parameter_value(instance, name) - value) > 1e-6:
            mel.set_material_instance_scalar_parameter_value(instance, name, value)
            changed = True
    for name, rgb in data['vectors'].items():
        have = mel.get_material_instance_vector_parameter_value(instance, name)
        if any(abs(getattr(have, c) - rgb[i]) > 1e-6 for i, c in enumerate('rgb')):
            mel.set_material_instance_vector_parameter_value(instance, name, u.LinearColor(*rgb, 1.0))
            changed = True
    if changed:
        u.EditorAssetLibrary.save_loaded_asset(instance)
    return instance, changed


def set_time_of_day(u, daylight, golden_weight):
    """Write the MPC defaults (used by reference_home_lighting presets). Returns True if changed."""
    if u.load_asset(geo.COLLECTION_PATH) is None:
        raise BackdropFixError('Leveled backdrop collection missing: ' + geo.COLLECTION_PATH)
    return ensure_collection(u, {'Daylight': daylight, 'GoldenWeight': golden_weight})[1]


def _backup_map(u):
    root = Path(u.Paths.project_dir())
    map_file = root / 'Content/Sub01Home/ActualHome.umap'
    if not map_file.is_file():
        raise BackdropFixError('Actual saved map missing; no recoverable change')
    backup = root / 'Saved/PrivateMapBackups' / ('%d-backdrop-fix' % time.time_ns())
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(map_file, backup / map_file.name)
    for folder in ('__ExternalActors__', '__ExternalObjects__'):
        path = root / 'Content' / folder / 'Sub01Home/ActualHome'
        if path.exists():
            shutil.copytree(path, backup / folder)
    return str(backup)


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------
def run(preset='night', when=None, yaw_deg=geo.DEFAULT_YAW_DEG, *, u=None, actor_subsystem=None,
        exposure_lock='auto', load_level=True, save=True, backup=True, write_report=True):
    if u is None:
        import unreal as u  # noqa: N813 - editor only
    level = u.get_editor_subsystem(u.LevelEditorSubsystem) if (load_level or save) else None
    if load_level and not level.load_level(LEVEL_PATH):
        raise BackdropFixError('Actual home map is missing: ' + LEVEL_PATH)
    actors = actor_subsystem or u.get_editor_subsystem(u.EditorActorSubsystem)
    data = plan(preset, when, yaw_deg)
    ctx = validate(u, actors, u.Paths.project_dir(), data, exposure_lock)
    # ---- mutation: owned assets first, the scene actor last ----
    collection, collection_changed = ensure_collection(u, {k: data['factors'][k] for k in geo.COLLECTION_PARAMETERS})
    material, rebuilt = build_material(u, ctx['texture'], collection, ctx['exposure_lock'])
    instance, instance_changed = ensure_instance(u, material, data)
    actor, mesh = ctx['actor'], ctx['mesh']
    before = ctx['before']
    rotation_ok = all(abs(before['rotation'][k]) < 1e-4 for k in ('pitch', 'yaw', 'roll'))
    material_ok = before['material'] is not None and before['material'].split('.')[0] == geo.INSTANCE_PATH
    actor_changed = not (rotation_ok and material_ok)
    backup_dir = None
    if actor_changed:
        if backup and save:
            backup_dir = _backup_map(u)
        actor.set_actor_rotation(u.Rotator(roll=0.0, pitch=0.0, yaw=0.0), False)
        mesh.set_material(0, instance)
        after = actor.get_actor_rotation()
        if any(abs(getattr(after, k)) > 1e-3 for k in ('pitch', 'yaw', 'roll')):
            raise BackdropFixError('Backdrop rotation did not level; map not saved')
        if save and not level.save_current_level():
            raise BackdropFixError('Leveled backdrop failed to save; backup at %s' % backup_dir)
    report = dict(data, applied=True, before=before, actor_changed=actor_changed, graph_rebuilt=rebuilt,
                  instance_changed=instance_changed, collection_changed=collection_changed,
                  exposure_lock=ctx['exposure_lock'], image=ctx['image'], source_size=ctx['source_size'],
                  courtyard_boxes=ctx['courtyard_boxes'], courtyard_max_distance_cm=ctx['courtyard_max_distance_cm'],
                  backdrop_radius_cm=ctx['radius_cm'], backdrop_center_cm=ctx['center_cm'],
                  owned_skies_seen=ctx['skies'], recoverable_backup=backup_dir, visual_match_claimed=False)
    if write_report:
        path = Path(u.Paths.project_dir()) / REPORT_NAME
        if actor_changed or not path.is_file():
            path.write_text(json.dumps(report, indent=2, default=str) + '\n')
    u.log('SUB01_EXTERIOR_BACKDROP_LEVELED ' + json.dumps({'preset': preset, 'actor_changed': actor_changed,
                                                          'graph_rebuilt': rebuilt}))
    return report


def restore(*, u=None, actor_subsystem=None, save=True):
    """Put back the pre-fix material and rotation recorded in exterior-backdrop-fix.json."""
    if u is None:
        import unreal as u  # noqa: N813
    report = json.loads((Path(u.Paths.project_dir()) / REPORT_NAME).read_text())
    level = u.get_editor_subsystem(u.LevelEditorSubsystem)
    if not level.load_level(LEVEL_PATH):
        raise BackdropFixError('Actual home map is missing')
    actors = actor_subsystem or u.get_editor_subsystem(u.EditorActorSubsystem)
    found = [a for a in actors.get_all_level_actors() if a.get_actor_label() == EXTERIOR_LABEL]
    if len(found) != 1:
        raise BackdropFixError('Expected exactly one backdrop to restore')
    before = report['before']
    material = u.load_asset(before['material']) if before['material'] else None
    if before['material'] and material is None:
        raise BackdropFixError('Recorded original material missing: ' + before['material'])
    rot = before['rotation']
    found[0].set_actor_rotation(u.Rotator(roll=rot['roll'], pitch=rot['pitch'], yaw=rot['yaw']), False)
    found[0].get_component_by_class(u.StaticMeshComponent).set_material(0, material)
    if save and not level.save_current_level():
        raise BackdropFixError('Restore failed to save')
    return before


def _parse(argv):
    parser = argparse.ArgumentParser(description='Level the SUB-01 Tokyo backdrop (dry run unless --apply).')
    parser.add_argument('--preset', default='night', choices=geo.PRESETS)
    parser.add_argument('--when', help='ISO datetime; naive = JST')
    parser.add_argument('--yaw', type=float, default=geo.DEFAULT_YAW_DEG)
    parser.add_argument('--exposure-lock', default='auto', choices=('auto', 'on', 'off'))
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--restore', action='store_true')
    parser.add_argument('--no-save', action='store_true')
    parser.add_argument('--quit', action='store_true')
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse(sys.argv[1:] if argv is None else argv)
    when = _dt.datetime.fromisoformat(args.when) if args.when else None
    if not (args.apply or args.restore):
        print(json.dumps(plan(args.preset, when, args.yaw), indent=2, default=str))
        return 0
    import unreal as u  # noqa: N813
    try:
        if args.restore:
            print(json.dumps({'restored': restore(u=u, save=not args.no_save)}))
        else:
            result = run(args.preset, when, args.yaw, u=u, exposure_lock=args.exposure_lock, save=not args.no_save)
            print(json.dumps({'applied': True, 'actor_changed': result['actor_changed']}))
    finally:
        if args.quit:
            u.SystemLibrary.quit_editor()
    return 0


if __name__ == '__main__':
    sys.exit(main())
