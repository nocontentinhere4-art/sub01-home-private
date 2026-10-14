"""Guarded, additive material fixes for the private SUB-01 home (Unreal editor Python).

Root runs this in the sole UE editor with gameplay stopped. Nothing is changed unless
``--apply`` (or ``--restore``) is given, and then only after a complete pre-flight.

Modes
  python3 tools/unreal_home_materials_fix.py --dry-run [--preset bed-intended ...]
      Pure plan without ``unreal``: targets, intended factors, predicted mean albedo/hue.

  python3 tools/unreal_home_materials_fix.py --mapping-check --inventory <report.json>
      Pure Python. Parses root's read-only inventory (tools/unreal_home_visual_inventory.py,
      schema sub01-private-actual-visual-inventory-v1) and checks every bed/sofa slot binding
      against the measured source groups, the parent parameters that really exist, and the
      plan. Prints mismatches; exit status 2 when the mapping is not safe to apply.

  ... -ExecutePythonScript="<repo>/tools/unreal_home_materials_fix.py --mapping-check --quit"
      Same check from a LIVE read-only enumeration (fallback when no inventory file).

  ... -ExecutePythonScript="<repo>/tools/unreal_home_materials_fix.py --apply --preset bed-intended --quit"
      Live pre-flight (refuses on any missing, ambiguous or duplicate target, a slot whose
      binding is not the expected source material, a parameter the real parent does not
      enumerate, or an unexpected current factor), then creates OWNED
      MaterialInstanceConstants /Game/Sub01Home/MaterialFix/SUB01_MatFix_<source> parented to
      the EXISTING material, overrides only enumerated parameters, and assigns them to the
      same component slots by exact component path. The original material of each slot is
      recorded (first run only) in <project>/Saved/SUB01MaterialFix/backup.json and the map
      is copied to Saved/PrivateMapBackups before the save. A second identical run changes
      nothing.

  ... --restore --quit
      Puts every recorded slot back to its original material.

Owned master (explicit fallback only): with ``--allow-owned-master``, a target whose parent
lacks a base-colour factor parameter is instead given a MIC of the owned
/Game/Sub01Home/MaterialFix/SUB01_MatFix_Master (BaseColorTexture x Tint with optional
Desaturation, Roughness, NormalTexture x NormalStrength, UVTiling, Metallic) that reuses the
ORIGINAL texture assets read from the parent. Without the flag such a target is refused.

Never reimports or rebuilds the house; never moves, scales or rotates actors; never changes
collision, meshes or physics; never edits or deletes original materials or textures.
No visual match with the SimbasJungles reference is claimed.
"""
import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import home_materials_spec as spec  # noqa: E402  (pure)
import unreal_export_texture_parity as parity_mod  # noqa: E402  (pure parts only)

LEVEL_PATH = '/Game/Sub01Home/ActualHome'
OWNED_DIR = '/Game/Sub01Home/MaterialFix'
OWNED_PREFIX = 'SUB01_MatFix_'
MASTER_NAME = OWNED_PREFIX + 'Master'
MASTER_PATH = OWNED_DIR + '/' + MASTER_NAME
MASTER_TAG = 'sub01_matfix_master'
MASTER_VERSION = 'v1'
STATE_DIR = 'Saved/SUB01MaterialFix'
BACKUP_NAME = 'backup.json'
MAPPING_NAME = 'mapping-check.json'
REPORT_NAME = 'apply-report.json'
INVENTORY_SCHEMA = 'sub01-private-actual-visual-inventory-v1'
TOL = 1e-4


class MaterialFixError(RuntimeError):
    """Raised before any mutation when the level, assets or parameters are not as expected."""


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def norm(name):
    """'Original teal upholstery.001', 'Original_teal_upholstery_001', 'MI_Original_teal_upholstery'
    and '/Game/.../Original_teal_upholstery_001.Original_teal_upholstery_001' -> 'original_teal_upholstery'."""
    s = str(name or '')
    if '/' in s:
        s = s.rsplit('/', 1)[-1].split('.')[0]
    s = re.sub(r'[^0-9a-z]+', '_', s.lower()).strip('_')
    s = re.sub(r'^(mi|m|mat|material)_', '', s)
    s = re.sub(r'(_\d{3})+$', '', s)
    return s


def asset_name(path):
    return str(path or '').rsplit('/', 1)[-1].split('.')[0]


def owned_name(source_name):
    return OWNED_PREFIX + norm(source_name)


def is_owned(path):
    return asset_name(path).startswith(OWNED_PREFIX)


def pick_parameter(available, candidates):
    """First candidate the editor actually enumerated on the parent, else None (never invented)."""
    available = list(available or [])
    for name in candidates:
        if name in available:
            return name
    return None


def close(a, b, tol=2e-3):
    return a is not None and b is not None and len(a) >= 3 and all(abs(float(x) - float(y)) <= tol
                                                                   for x, y in zip(a[:3], b[:3]))


# ---------------------------------------------------------------------------
# Scene model: one row per mesh-component slot, from an inventory file or live
# ---------------------------------------------------------------------------
def model_from_inventory(report):
    """Parse root's tools/unreal_home_visual_inventory.py JSON into the scene model."""
    if report.get('schema') != INVENTORY_SCHEMA:
        raise MaterialFixError('Unexpected inventory schema %r' % report.get('schema'))
    materials = {}
    for path, row in (report.get('materials') or {}).items():
        params = row.get('parameters') or {}
        materials[path] = {'path': path, 'class': row.get('class'), 'parent': row.get('parent'),
                           'names': {k: sorted(params.get(k, {})) for k in ('scalar', 'vector', 'texture')},
                           'values': {k: dict(params.get(k, {})) for k in ('scalar', 'vector', 'texture')},
                           'texture_sizes': {}, 'errors': list(row.get('errors') or [])}
    rows = [{'actor_label': b.get('actor', ''), 'component_path': b['component'], 'mesh': b.get('mesh'),
             'slot': int(b['slot']), 'slot_name': b.get('slot_name', ''), 'material_path': b['material']}
            for b in report.get('bindings') or []]
    return {'source': 'inventory', 'rows': rows, 'materials': materials}


def _try(fn, *args):
    try:
        return fn(*args)
    except Exception:  # noqa: BLE001 - reporting must survive one odd asset
        return None


def _path(obj):
    return obj.get_path_name() if obj is not None else None


def _color(value):
    return None if value is None else [round(float(getattr(value, c)), 6) for c in 'rgba']


def live_material_record(u, material):
    mel = u.MaterialEditingLibrary
    instance = isinstance(material, u.MaterialInstance)
    record = {'path': _path(material), 'class': type(material).__name__,
              'parent': _path(_try(material.get_editor_property, 'parent')) if instance else None,
              'names': {}, 'values': {}, 'texture_sizes': {}, 'errors': []}
    for kind in ('scalar', 'vector', 'texture'):
        getter = getattr(mel, 'get_%s_parameter_names' % kind, None)
        names = _try(getter, material) if getter else None
        if names is None:
            record['errors'].append(kind + ':names')
            names = []
        record['names'][kind] = sorted(str(n) for n in names)
        fn = getattr(mel, ('get_material_instance_%s_parameter_value' if instance
                           else 'get_material_default_%s_parameter_value') % kind, None)
        values = {}
        for name in record['names'][kind]:
            value = _try(fn, material, name) if fn else None
            if kind == 'scalar':
                values[name] = None if value is None else float(value)
            elif kind == 'vector':
                values[name] = _color(value)
            else:
                values[name] = _path(value)
                if value is not None and hasattr(value, 'blueprint_get_size_x'):
                    record['texture_sizes'][name] = [int(value.blueprint_get_size_x()),
                                                     int(value.blueprint_get_size_y())]
        record['values'][kind] = values
    return record


def model_from_live(u, actors):
    rows, materials, objects = [], {}, {'components': {}, 'materials': {}}
    for actor in actors.get_all_level_actors():
        label = actor.get_actor_label()
        for component in actor.get_components_by_class(u.StaticMeshComponent):
            mesh = component.get_editor_property('static_mesh')
            if mesh is None:
                continue
            cpath = component.get_path_name()
            objects['components'].setdefault(cpath, []).append(component)
            slot_names = [str(_try(s.get_editor_property, 'material_slot_name') or '')
                          for s in (_try(mesh.get_editor_property, 'static_materials') or [])]
            for slot in range(component.get_num_materials()):
                material = component.get_material(slot)
                mpath = _path(material)
                rows.append({'actor_label': label, 'component_path': cpath, 'mesh': _path(mesh), 'slot': slot,
                             'slot_name': slot_names[slot] if slot < len(slot_names) else '',
                             'material_path': mpath})
                for m in (material, _try(material.get_editor_property, 'parent')
                          if material is not None and isinstance(material, u.MaterialInstance) else None):
                    if m is not None and _path(m) not in materials:
                        materials[_path(m)] = live_material_record(u, m)
                        objects['materials'][_path(m)] = m
    return {'source': 'live', 'rows': rows, 'materials': materials, 'objects': objects}


def original_path(model, path):
    """An owned SUB01_MatFix_ MIC stands for its parent (idempotence / re-check after apply)."""
    if path and is_owned(path):
        record = model['materials'].get(path)
        if record and record.get('parent'):
            return record['parent']
    return path


# ---------------------------------------------------------------------------
# Mapping check (pure, on the model)
# ---------------------------------------------------------------------------
def _identity(row):
    return '_' + '_'.join(norm(x) for x in (row['actor_label'], row['component_path'], row.get('mesh'),
                                            row.get('slot_name'))) + '_'


def original_texture_status(parity, originals):
    """Report (never accept) how the ORIGINAL bed textures were imported, from a parity file."""
    if not parity:
        return None
    rows = {t.get('asset_path'): t for t in parity.get('textures') or []}
    out = {}
    for path in originals:
        t = rows.get(path)
        if t is None:
            continue
        normal_import = t.get('srgb') is False or str(t.get('compression')).endswith('TC_NORMALMAP')
        out[path] = {'srgb': t.get('srgb'), 'compression': t.get('compression'),
                     'pixel_match_reference': (t.get('source_provenance') or {}).get('pixel_match_reference'),
                     'verdict': 'imported as a NORMAL MAP: refused as colour' if normal_import else 'colour import'}
    return out


def bed_texture_paths(model):
    """Base-colour texture paths of the four bed upholstery materials, from the model."""
    out = set()
    for path, record in model['materials'].items():
        if norm(path) in {norm(n) for n in spec.BED_SOURCES}:
            tname = pick_parameter((record.get('names') or {}).get('texture'),
                                   spec.PARAM_CANDIDATES['base_color_texture'])
            if tname:
                out.add(((record.get('values') or {}).get('texture') or {}).get(tname))
    return sorted(p for p in out if p)


def mapping_check(model, presets=None, parity=None, albedo_clones=False):
    presets = list(presets or spec.DEFAULT_PRESETS)
    albedo_clones = albedo_clones or 'albedo-color-clones' in presets
    measured, parity_problems = None, None
    if parity is not None:
        textures = bed_texture_paths(model)
        if albedo_clones:
            clone_of = {parity_mod.clone_path(t): t for t in textures}
            parity_problems, mean, p99 = parity_mod.validate_parity(parity, sorted(clone_of), clone_of=clone_of)
        else:
            parity_problems, mean, p99 = parity_mod.validate_parity(parity, textures)
        if not parity_problems:
            measured = {'linear_mean': mean, 'linear_p99': p99, 'source': 'texture parity (actual UE pixels)'}
    plan = spec.plan(presets, measured)
    if albedo_clones:
        for t in plan['targets']:
            # Bed mapping also guards wooden rails/slats. Only the four proven
            # upholstery source images belong to the albedo-copy repair.
            if t.get('bed') and t.get('class') == 'fabric' and set(t.get('source_materials', [])) == set(spec.BED_SOURCES):
                t['albedo_clones'] = True
    bed = spec.source_bed_groups()
    mesh_of_material = {norm(v[0]): k for k, v in bed['groups'].items()}
    mismatches, notes, slots = [], [], []
    for row in model['rows']:
        mpath = original_path(model, row['material_path'])
        ident = _identity(row)
        by_identity = [g for g in bed['groups'] if '_' + norm(g) + '_' in ident]
        by_material = mesh_of_material.get(norm(mpath))
        sofa_part = next((p for p in spec.SOFA_PARTS if '_' + norm(p) + '_' in ident), None)
        if not by_identity and not by_material and not sofa_part:
            continue
        entry = {'actor_label': row['actor_label'], 'component_path': row['component_path'], 'slot': row['slot'],
                 'material': row['material_path'], 'original_material': mpath,
                 'group_by_identity': by_identity, 'group_by_material': by_material, 'sofa_part': sofa_part}
        if len(by_identity) > 1:
            mismatches.append(dict(kind='ambiguous_identity', **entry))
        elif by_identity and by_material and by_identity[0] != by_material:
            mismatches.append(dict(kind='slot_bound_to_other_group_material', expected=bed['groups'][by_identity[0]][0],
                                   **entry))
        elif by_identity and not by_material:
            mismatches.append(dict(kind='bed_slot_with_unexpected_material', expected=bed['groups'][by_identity[0]][0],
                                   **entry))
        slots.append(entry)
    # Each bed source group -> exactly one distinct UE material.
    group_materials = {}
    for e in slots:
        if e['group_by_material']:
            group_materials.setdefault(e['group_by_material'], set()).add(e['original_material'])
    for g, paths in sorted(group_materials.items()):
        if len(paths) > 1:
            mismatches.append({'kind': 'group_with_several_materials', 'group': g, 'materials': sorted(paths)})
    missing = sorted(set(bed['groups']) - set(group_materials))
    if missing:
        notes.append('bed groups without a UE material named after their source material: ' + ', '.join(missing))
    if slots and not any(e['group_by_identity'] for e in slots if e['group_by_material']):
        notes.append('bed slots carry no CC0_queen_N identity in actor/component/mesh names; mapping is by '
                     'material name only')
    # Users of the headboard (teal) material: expected only the headboard group.
    teal = [p for g, ps in group_materials.items() if 'teal' in bed['groups'][g][0] for p in ps]
    teal_users = [e for e in slots if e['original_material'] in teal]
    other_ident = [e for e in teal_users if e['group_by_identity'] and e['group_by_identity'][0] != 'CC0_queen_1']
    if other_ident:
        mismatches.append({'kind': 'headboard_material_on_other_bed_parts', 'slots': other_ident})
    # Per planned target: the binding and parameter facts that --apply will rely on.
    targets = []
    for target in plan['targets']:
        targets.append(check_target(model, target, slots, mismatches, parity, parity_problems))
    bed_required = any(t.get('bed') for t in plan['targets'])
    ok = all(t['ok'] for t in targets) and (not bed_required or (not mismatches and not missing))
    return {'schema': 'sub01.home-materials-mapping.v1', 'model_source': model['source'],
            'presets': presets, 'source_bed': bed, 'bed_and_sofa_slots': slots,
            'headboard_material_slot_users': len(teal_users), 'targets': targets,
            'bed_mapping_required': bed_required, 'parity_problems': parity_problems,
            'albedo_clones': albedo_clones,
            'original_texture_status': original_texture_status(parity, bed_texture_paths(model)),
            'texture_mean_used': measured,
            'mismatches': mismatches, 'notes': notes, 'ok': ok, 'visual_match_claimed': False}


def target_slots(model, target):
    """Rows a target applies to, keyed by the ORIGINAL material path."""
    found = {}
    for row in model['rows']:
        mpath = original_path(model, row['material_path'])
        if mpath is None:
            continue
        if target['match'] == 'material_name':
            hit = norm(mpath) in {norm(n) for n in target['source_materials']}
        elif target['match'] == 'factor_fingerprint':
            record = model['materials'].get(mpath) or {}
            fname = pick_parameter((record.get('names') or {}).get('vector'),
                                   spec.PARAM_CANDIDATES['base_color_factor'])
            have = ((record.get('values') or {}).get('vector') or {}).get(fname) if fname else None
            hit = have is not None and any(close(have, f, 3e-3) for f in [target['fingerprint'], target['factor']])
        else:  # actor prefix
            hit = any(norm(row['actor_label']).startswith(norm(p)) or ('_' + norm(p)) in _identity(row)
                      for p in target['actor_prefixes'])
        if hit:
            found.setdefault(mpath, []).append(row)
    return found


def check_target(model, target, slots, mismatches, parity=None, parity_problems=None):
    result = {'id': target['id'], 'ok': True, 'problems': [], 'materials': []}
    if target.get('held'):
        result['problems'].append('held: ' + target['held'])
    found = target_slots(model, target)
    expect = target['expected_materials']
    if len(found) != expect:
        result['problems'].append('expected %d distinct material(s), found %d: %s' % (expect, len(found),
                                                                                    sorted(found)))
    for mpath, rows in sorted(found.items()):
        record = model['materials'].get(mpath) or {}
        names = record.get('names') or {}
        values = record.get('values') or {}
        item = {'material': mpath, 'slots': [(r['component_path'], r['slot']) for r in rows],
                'parent': record.get('parent'), 'path': None}
        keys = item['slots']
        if len(set(keys)) != len(keys):
            result['problems'].append('%s: duplicate slot rows' % mpath)
        intended = spec.intended_factor(target, mpath)
        item['intended_factor'] = intended
        factor_name = pick_parameter(names.get('vector'), spec.PARAM_CANDIDATES['base_color_factor'])
        tex_name = pick_parameter(names.get('texture'), spec.PARAM_CANDIDATES['base_color_texture'])
        item['factor_parameter'], item['texture_parameter'] = factor_name, tex_name
        item['texture'] = values.get('texture', {}).get(tex_name) if tex_name else None
        item['albedo_clone'] = None
        if target.get('albedo_clones'):
            if not tex_name or not item['texture']:
                result['problems'].append('%s: no enumerated base-colour texture parameter to re-point' % mpath)
            else:
                item['albedo_clone'] = parity_mod.clone_path(item['texture'])
        current = values.get('vector', {}).get(factor_name) if factor_name else None
        item['current_factor'] = current
        satisfied = []
        if intended is None:
            item['path'] = 'mic_of_original'
        elif factor_name:
            item['path'] = 'mic_of_original'
            accepted = target.get('factor_expect') or [[1, 1, 1]]
            satisfied.append(bool(current is not None and close(current, intended)))
            if current is not None and not any(close(current, a) for a in accepted) and not close(current, intended):
                result['problems'].append('%s: current %s=%s is neither the expected %s nor the intended %s; '
                                          'refusing' % (mpath, factor_name, current, accepted, intended))
        else:
            item['path'] = 'owned_master_required'
            if not tex_name:
                result['problems'].append('%s: no base-colour factor and no base-colour texture parameter '
                                          'enumerated (%s); cannot even feed the owned master' % (mpath, names))
        item['scalar_overrides'] = []
        for override in target.get('scalars', []):
            pname = pick_parameter(names.get('scalar'), spec.PARAM_CANDIDATES[override['param']])
            if pname is None:
                result['problems'].append('%s: no %s parameter among %s; refusing (no invented parameters)' % (
                    mpath, override['param'], names.get('scalar')))
                continue
            have = values.get('scalar', {}).get(pname)
            done = have is not None and abs(float(have) - override['value']) <= 2e-3
            satisfied.append(done)
            if not done and have is not None and override.get('expect') is not None and \
                    not any(abs(float(have) - e) <= 2e-3 for e in override['expect']):
                result['problems'].append('%s: current %s=%s is not the expected %s; refusing' % (
                    mpath, pname, have, override['expect']))
            item['scalar_overrides'].append(('scalar', pname, float(override['value'])))
        if item['path'] == 'owned_master_required' and target.get('scalars'):
            result['problems'].append('%s: scalar-only target needs the real parent; no owned master' % mpath)
        if item['albedo_clone']:
            satisfied.append(item['texture'] == item['albedo_clone'])
        item['already_intended'] = bool(satisfied) and all(satisfied)
        sig = target.get('texture_signature')
        size = (record.get('texture_sizes') or {}).get(tex_name) if tex_name else None
        item['texture_size'] = size
        if sig and size is not None and list(size) not in [list(s) for s in sig['sizes']]:
            result['problems'].append('%s: base-colour texture %s is %s, expected %s (%s)' % (
                mpath, item['texture'], size, sig['sizes'], sig['source']))
        if target['match'] == 'material_name':
            bad = [e for e in slots if e['original_material'] == mpath and e['group_by_identity']
                   and norm(spec.source_bed_groups()['groups'][e['group_by_identity'][0]][0]) != norm(mpath)]
            if bad:
                result['problems'].append('%s: bound on slots of other source groups %s' % (mpath, bad))
        result['materials'].append(item)
    textures = {m['albedo_clone'] or m['texture'] for m in result['materials'] if m['texture']}
    if target.get('albedo_clones') and parity is None:
        result['problems'].append('albedo clones need a parity file of the CLONES (pixels == GLB image 15, '
                                  'sRGB True, TC_DEFAULT)')
    if target.get('same_texture') and len(textures) > 1:
        # Distinct UE assets are accepted only with content-equivalence evidence (texture parity file).
        if parity is None:
            result['problems'].append('materials use different base-colour textures %s and no texture parity '
                                      'file proves they hold the same pixels' % sorted(textures))
        elif parity_problems:
            result['problems'].append('texture parity refused: %s' % parity_problems)
        else:
            result['texture_equivalence'] = 'accepted by parity file (identical decoded pixels, neutral settings)'
    if target.get('same_texture') and parity is not None and len(textures) == 1 and parity_problems:
        result['problems'].append('texture parity refused: %s' % parity_problems)
    result['ok'] = not result['problems']
    return result


# ---------------------------------------------------------------------------
# Owned master (explicit fallback)
# ---------------------------------------------------------------------------
def _load_or_create(u, name, cls, factory):
    path = OWNED_DIR + '/' + name
    asset = u.load_asset(path)
    created = asset is None
    if created:
        asset = u.AssetToolsHelpers.get_asset_tools().create_asset(name, OWNED_DIR, getattr(u, cls), getattr(u, factory)())
    if asset is None or not isinstance(asset, getattr(u, cls)):
        raise MaterialFixError('Owned path holds a different asset type: ' + path)
    return asset, created


def build_master(u):
    """SUB01_MatFix_Master: default lit, BaseColorTexture x Tint (optional desaturation), Roughness,
    NormalTexture x NormalStrength, UVTiling, Metallic. Rebuilt only when its version tag differs."""
    material, created = _load_or_create(u, MASTER_NAME, 'Material', 'MaterialFactoryNew')
    if not created and u.EditorAssetLibrary.get_metadata_tag(material, MASTER_TAG) == MASTER_VERSION:
        return material, False
    mel = u.MaterialEditingLibrary
    mel.delete_all_material_expressions(material)
    links = []

    def node(cls, x, y, **props):
        e = mel.create_material_expression(material, getattr(u, cls), x, y)
        for k, v in props.items():
            e.set_editor_property(k, v)
        return e

    def link(a, out, b, inp):
        links.append((type(a).__name__, out, type(b).__name__, inp, mel.connect_material_expressions(a, out, b, inp)))

    coords = node('MaterialExpressionTextureCoordinate', -1600, 0)
    tiling = node('MaterialExpressionScalarParameter', -1600, 120, parameter_name='UVTiling', default_value=1.0)
    uv = node('MaterialExpressionMultiply', -1400, 0)
    link(coords, '', uv, 'A'); link(tiling, '', uv, 'B')
    base = node('MaterialExpressionTextureSampleParameter2D', -1200, 0, parameter_name='BaseColorTexture',
                sampler_type=u.MaterialSamplerType.SAMPLERTYPE_COLOR)
    link(uv, '', base, 'UVs')
    desat_amount = node('MaterialExpressionScalarParameter', -1200, 250, parameter_name='Desaturation',
                        default_value=0.0)
    desat = node('MaterialExpressionDesaturation', -950, 0)
    link(base, 'RGB', desat, ''); link(desat_amount, '', desat, 'Fraction')
    tint = node('MaterialExpressionVectorParameter', -950, 250, parameter_name='Tint',
                default_value=u.LinearColor(1.0, 1.0, 1.0, 1.0))
    tinted = node('MaterialExpressionMultiply', -700, 0)
    link(desat, '', tinted, 'A'); link(tint, '', tinted, 'B')
    rough = node('MaterialExpressionScalarParameter', -700, 300, parameter_name='Roughness', default_value=0.85)
    metal = node('MaterialExpressionScalarParameter', -700, 400, parameter_name='Metallic', default_value=0.0)
    normal = node('MaterialExpressionTextureSampleParameter2D', -1200, 500, parameter_name='NormalTexture',
                  sampler_type=u.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    link(uv, '', normal, 'UVs')
    flat = node('MaterialExpressionConstant3Vector', -950, 650, constant=u.LinearColor(0.0, 0.0, 1.0, 1.0))
    strength = node('MaterialExpressionScalarParameter', -950, 750, parameter_name='NormalStrength', default_value=1.0)
    blend = node('MaterialExpressionLinearInterpolate', -700, 550)
    link(flat, '', blend, 'A'); link(normal, 'RGB', blend, 'B'); link(strength, '', blend, 'Alpha')
    ok = all([mel.connect_material_property(tinted, '', u.MaterialProperty.MP_BASE_COLOR),
              mel.connect_material_property(rough, '', u.MaterialProperty.MP_ROUGHNESS),
              mel.connect_material_property(metal, '', u.MaterialProperty.MP_METALLIC),
              mel.connect_material_property(blend, '', u.MaterialProperty.MP_NORMAL)])
    failed = [l for l in links if not l[-1]]
    if failed or not ok:
        raise MaterialFixError('Owned master graph failed to connect (scene untouched): %s' % failed)
    mel.recompile_material(material)
    u.EditorAssetLibrary.set_metadata_tag(material, MASTER_TAG, MASTER_VERSION)
    u.EditorAssetLibrary.save_loaded_asset(material)
    return material, True


def ensure_texture_colour_spaces(u, textures):
    """Base colour sRGB, normal/roughness linear. Only reports a mismatch; textures are not edited
    unless a non-sRGB-required map is flagged sRGB (then it is a refusal for the master path)."""
    problems = []
    for role, texture in textures.items():
        if texture is None:
            continue
        srgb = _try(texture.get_editor_property, 'srgb')
        want = spec.TEXTURE_SRGB[role]
        if srgb is not None and bool(srgb) != want:
            problems.append('%s texture %s has sRGB=%s, expected %s' % (role, _path(texture), srgb, want))
    return problems


# ---------------------------------------------------------------------------
# Live mutation
# ---------------------------------------------------------------------------
def _state_dir(u):
    path = Path(u.Paths.project_dir()) / STATE_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _backup_map(u):
    root = Path(u.Paths.project_dir())
    map_file = root / 'Content/Sub01Home/ActualHome.umap'
    if not map_file.is_file():
        raise MaterialFixError('Actual saved map missing; no recoverable change')
    backup = root / 'Saved/PrivateMapBackups' / ('%d-materials-fix' % time.time_ns())
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(map_file, backup / map_file.name)
    for folder in ('__ExternalActors__', '__ExternalObjects__'):
        path = root / 'Content' / folder / 'Sub01Home/ActualHome'
        if path.exists():
            shutil.copytree(path, backup / folder)
    return str(backup)


def component_fingerprint(u, component):
    t = component.get_world_transform()
    return {'translation': [round(float(getattr(t.translation, c)), 4) for c in 'xyz'],
            'rotation': [round(float(getattr(t.rotation, c)), 6) for c in 'xyzw'],
            'scale': [round(float(getattr(t.scale3d, c)), 6) for c in 'xyz'],
            'mesh': _path(component.get_editor_property('static_mesh')),
            'collision': str(component.get_collision_enabled()),
            'profile': str(component.get_collision_profile_name())}


def ensure_instance(u, model, item, allow_master):
    """Owned MIC for one original material. Returns (instance, changed, overrides)."""
    mel = u.MaterialEditingLibrary
    original = model['objects']['materials'][item['material']]
    name = owned_name(item['material'])
    factor = [float(v) for v in (item['intended_factor'] or [1, 1, 1])[:3]]
    if item['path'] == 'mic_of_original':
        parent = original
        overrides = ([('vector', item['factor_parameter'], factor + [1.0])] if item['intended_factor'] is not None
                     else []) + list(item.get('scalar_overrides') or [])
        if item.get('albedo_clone'):
            clone = u.load_asset(item['albedo_clone'].split('.')[0])
            if clone is None or not item.get('texture_parameter'):
                raise MaterialFixError('Albedo clone %s missing; run --repair-albedo-textures' % item['albedo_clone'])
            overrides.append(('texture', item['texture_parameter'], clone))
    else:
        if not allow_master:
            raise MaterialFixError('%s needs the owned master; rerun with --allow-owned-master' % item['material'])
        parent, _ = build_master(u)
        record = model['materials'][item['material']]
        # The ORIGINAL texture assets, read from the original material's own parameter values.
        base = u.load_asset(record['values']['texture'][item['texture_parameter']])
        normal_param = pick_parameter(record['names'].get('texture'), spec.PARAM_CANDIDATES['normal_texture'])
        normal = u.load_asset(record['values']['texture'][normal_param]) if normal_param else None
        problems = ensure_texture_colour_spaces(u, {'base_color': base, 'normal': normal})
        if problems or base is None:
            raise MaterialFixError('Owned-master inputs refused: %s' % (problems or 'base texture missing'))
        rough_param = pick_parameter(record['names'].get('scalar'), spec.PARAM_CANDIDATES['roughness_factor'])
        nscale_param = pick_parameter(record['names'].get('scalar'), spec.PARAM_CANDIDATES['normal_scale'])
        overrides = [('texture', 'BaseColorTexture', base), ('vector', 'Tint', factor + [1.0]),
                     ('scalar', 'Desaturation', float(item.get('desaturation', 0.0))),
                     ('scalar', 'UVTiling', float(item.get('uv_tiling', 1.0))),
                     ('scalar', 'Roughness', float(record['values']['scalar'].get(rough_param, 0.9)
                                                   if rough_param else item.get('roughness', 0.9)))]
        if normal is not None:
            overrides += [('texture', 'NormalTexture', normal),
                          ('scalar', 'NormalStrength', float(record['values']['scalar'].get(nscale_param, 1.0)
                                                             if nscale_param else 1.0))]
    instance, created = _load_or_create(u, name, 'MaterialInstanceConstant', 'MaterialInstanceConstantFactoryNew')
    changed = created
    have_parent = _path(instance.get_editor_property('parent'))
    if have_parent != _path(parent):
        if not created:
            raise MaterialFixError('Owned %s is parented to %s, not %s' % (name, have_parent, _path(parent)))
        mel.set_material_instance_parent(instance, parent)
        changed = True
    for kind, pname, value in overrides:
        if kind == 'vector':
            have = _color(mel.get_material_instance_vector_parameter_value(instance, pname))
            if have is None or any(abs(have[i] - value[i]) > TOL for i in range(4)):
                mel.set_material_instance_vector_parameter_value(instance, pname, u.LinearColor(*value))
                changed = True
        elif kind == 'scalar':
            have = mel.get_material_instance_scalar_parameter_value(instance, pname)
            if have is None or abs(float(have) - value) > TOL:
                mel.set_material_instance_scalar_parameter_value(instance, pname, value)
                changed = True
        else:
            have = mel.get_material_instance_texture_parameter_value(instance, pname)
            if _path(have) != _path(value):
                mel.set_material_instance_texture_parameter_value(instance, pname, value)
                changed = True
    if changed:
        mel.update_material_instance(instance)
        u.EditorAssetLibrary.save_loaded_asset(instance)
    return instance, changed, [(k, n, _path(v) if k == 'texture' else v) for k, n, v in overrides]


def _load_backup(u):
    path = _state_dir(u) / BACKUP_NAME
    if path.is_file():
        return json.loads(path.read_text())
    return {'schema': 'sub01.home-materials-backup.v1', 'slots': {}}


def _live_actors(u, actor_subsystem, load_level):
    level = u.get_editor_subsystem(u.LevelEditorSubsystem)
    if load_level and not level.load_level(LEVEL_PATH):
        raise MaterialFixError('Actual home map is missing: ' + LEVEL_PATH)
    return level, actor_subsystem or u.get_editor_subsystem(u.EditorActorSubsystem)


# ---------------------------------------------------------------------------
# Albedo texture repair: owned sRGB / TC_DEFAULT duplicates (originals never touched)
# ---------------------------------------------------------------------------
NEUTRAL_KEYS = ('lod_bias',) + tuple(parity_mod.ADJUST_DEFAULTS)


def texture_settings(u, texture):
    out = {}
    for key in ('srgb', 'compression_settings') + NEUTRAL_KEYS:
        value = _try(texture.get_editor_property, key)
        out[key] = value if isinstance(value, (bool, int, float, type(None))) else parity_mod._enum_name(value)
    out['size'] = [int(texture.blueprint_get_size_x()), int(texture.blueprint_get_size_y())]
    return out


def _package_file(u, object_path):
    rel = object_path.split('.')[0]
    if not rel.startswith('/Game/'):
        return None
    return Path(u.Paths.project_dir()) / 'Content' / (rel[len('/Game/'):] + '.uasset')


def _file_sha(path):
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest() if path and path.is_file() else None


def _export_sha(u, texture, tag):
    """sha256 of the PNG the editor exports from the texture's SOURCE pixels (deterministic exporter)."""
    import hashlib
    folder = _state_dir(u) / 'pixel-compare'
    folder.mkdir(parents=True, exist_ok=True)
    png = folder / ('%s-%d.png' % (tag, time.time_ns()))
    task = u.AssetExportTask()
    for key, value in (('object', texture), ('filename', str(png)), ('automated', True), ('prompt', False),
                       ('replace_identical', True), ('selected', False)):
        task.set_editor_property(key, value)
    if not u.Exporter.run_asset_export_task(task) or not png.is_file():
        raise MaterialFixError('PNG export failed for %s' % _path(texture))
    digest = hashlib.sha256(png.read_bytes()).hexdigest()
    png.unlink()
    return digest


def clone_problems(u, original, clone, original_path):
    """Why an existing owned clone is NOT an exact sRGB/TC_DEFAULT colour copy of the original (empty = ok)."""
    problems = []
    if not isinstance(clone, u.Texture2D):
        return ['not a Texture2D']
    if (u.EditorAssetLibrary.get_metadata_tag(clone, parity_mod.DUPLICATE_TAG) or '').split('.')[0] != \
            original_path.split('.')[0]:
        problems.append('duplicate_of tag is not %s' % original_path)
    have = texture_settings(u, clone)
    if have['srgb'] is not True:
        problems.append('sRGB %s' % have['srgb'])
    if have['compression_settings'] != 'TC_DEFAULT':
        problems.append('compression %s' % have['compression_settings'])
    if original is not None:
        want = texture_settings(u, original)
        for key in NEUTRAL_KEYS + ('size',):
            if have[key] != want[key]:
                problems.append('%s %s differs from original %s' % (key, have[key], want[key]))
        if not problems and _export_sha(u, clone, 'clone') != _export_sha(u, original, 'original'):
            problems.append('exported source pixels differ from the original')
    return problems


def _create_clone(u, state, path, original, settings, clone_obj_path):
    """Duplicate one original texture into its owned clone: compression first, then sRGB; tag; prove the
    original unchanged and the exported pixels identical; save ONLY the clone."""
    package = _package_file(u, path)
    before_file = _file_sha(package)
    clone = u.EditorAssetLibrary.duplicate_asset(path.split('.')[0], clone_obj_path.split('.')[0])
    if clone is None or not isinstance(clone, u.Texture2D):
        raise MaterialFixError('duplicate_asset failed for %s' % path)
    owned = state.setdefault('owned_assets', [])
    if clone_obj_path.split('.')[0] not in owned:
        owned.append(clone_obj_path.split('.')[0])
    (_state_dir(u) / BACKUP_NAME).write_text(json.dumps(state, indent=1) + '\n')
    # TC_NORMALMAP forces sRGB off in PostEditChange; leave normal-map
    # compression first, then enable the colour texture's sRGB sampling.
    clone.set_editor_property('compression_settings', u.TextureCompressionSettings.TC_DEFAULT)
    clone.set_editor_property('srgb', True)
    u.EditorAssetLibrary.set_metadata_tag(clone, parity_mod.DUPLICATE_TAG, path)
    if texture_settings(u, original) != settings or _file_sha(package) != before_file:
        raise MaterialFixError('Original %s changed while cloning; clone NOT saved' % path)
    problems = clone_problems(u, original, clone, path)
    if problems:
        raise MaterialFixError('New clone %s is not exact: %s; NOT saved' % (clone_obj_path, problems))
    if not u.EditorAssetLibrary.save_loaded_asset(clone, False):
        raise MaterialFixError('Saving clone %s failed' % clone_obj_path)
    if texture_settings(u, original) != settings or _file_sha(package) != before_file:
        raise MaterialFixError('Original %s changed after saving the clone' % path)
    return {'original': path, 'clone': clone_obj_path, 'action': 'created',
            'original_settings': settings, 'clone_settings': texture_settings(u, clone)}


def repair_albedo_textures(*, u=None, actor_subsystem=None, load_level=True):
    """Create (or verify) owned colour clones of the four bed albedo textures. Idempotent, fail closed."""
    if u is None:
        import unreal as u  # noqa: N813
    _, actors = _live_actors(u, actor_subsystem, load_level)
    model = model_from_live(u, actors)
    check = mapping_check(model, ['bed-intended'])
    other = [p for t in check['targets'] for p in t['problems'] if 'different base-colour textures' not in p]
    if check['mismatches'] or check['notes'] or other:
        raise MaterialFixError('Repair refused: bed mapping not clean: %s' % json.dumps(
            {'mismatches': check['mismatches'], 'notes': check['notes'], 'problems': other}, default=str))
    originals = bed_texture_paths(model)
    if len(originals) != 4:
        raise MaterialFixError('Repair refused: expected 4 bed albedo textures, found %s' % originals)
    work, report = [], []
    for path in originals:
        if not path.startswith(parity_mod.ALLOWED_ROOT):
            raise MaterialFixError('Repair refused: %s is outside %s' % (path, parity_mod.ALLOWED_ROOT))
        original = u.load_asset(path.split('.')[0])
        if original is None or not isinstance(original, u.Texture2D):
            raise MaterialFixError('Repair refused: %s missing or not a Texture2D' % path)
        settings = texture_settings(u, original)
        if not (settings['srgb'] is False and settings['compression_settings'] == 'TC_NORMALMAP'):
            raise MaterialFixError('Repair refused: %s is not the measured normal-map import (%s)' % (path, settings))
        if any(settings[k] != v for k, v in parity_mod.ADJUST_DEFAULTS.items()) or settings['lod_bias'] != 0:
            raise MaterialFixError('Repair refused: %s has non-neutral LOD/adjust settings %s' % (path, settings))
        clone_obj_path = parity_mod.clone_path(path)
        existing = u.load_asset(clone_obj_path.split('.')[0])
        if existing is not None:
            problems = clone_problems(u, original, existing, path)
            if problems:
                raise MaterialFixError('Repair refused: existing clone %s differs: %s' % (clone_obj_path, problems))
            report.append({'original': path, 'clone': clone_obj_path, 'action': 'verified existing'})
            continue
        work.append((path, original, settings, clone_obj_path))
    # ---- mutation: owned duplicates only ----
    state = _load_backup(u)
    for path, original, settings, clone_obj_path in work:
        report.append(_create_clone(u, state, path, original, settings, clone_obj_path))
    u.log('SUB01_ALBEDO_REPAIR ' + json.dumps([(r['clone'], r['action']) for r in report]))
    return {'schema': 'sub01.home-materials-albedo-repair.v1', 'textures': report}


# ---------------------------------------------------------------------------
# Generic albedo colour-space repair driven by root's texture-usage audit
# (tools/unreal_home_texture_usage_audit.py, schema sub01-private-texture-usage-audit-v1)
# ---------------------------------------------------------------------------
USAGE_SCHEMA = 'sub01-private-texture-usage-audit-v1'
USAGE_MISMATCH = 'normalmap_compression_used_as_albedo'
USAGE_MIC_PREFIX = OWNED_PREFIX + 'AlbedoMI_'


def usage_mic_name(material_path):
    raw = re.sub(r'[^0-9A-Za-z_]+', '_', asset_name(material_path))
    return USAGE_MIC_PREFIX + raw


def _real_bed_textures():
    return {p.split('.')[0] for p in parity_mod.BED_TEXTURES}


def select_usage_repairs(doc, exclude=None):
    """Pure. Textures DEFINITELY sampled as albedo but imported as normal maps, from the usage audit.

    Selected only when: the file reports the definite mismatch; sRGB False and TC_NORMALMAP; every usage is
    the albedo parameter (never also a NormalTexture anywhere in the file); no settings errors; under an
    allowed original root; not already repaired (the 4 bed textures by default). Everything else that
    carries a mismatch or warning is listed under 'excluded' / 'ambiguous' with the reason, never touched.
    """
    if doc.get('schema') != USAGE_SCHEMA:
        raise MaterialFixError('Unexpected usage schema %r' % doc.get('schema'))
    if doc.get('errors') or not doc.get('complete_for_declared_scope'):
        raise MaterialFixError('Usage audit incomplete or has errors: %s' % doc.get('errors'))
    exclude = {p.split('.')[0] for p in (exclude if exclude is not None else _real_bed_textures())}
    roles_by_texture = {}
    for t in doc['textures']:
        for use in t.get('usages') or []:
            roles_by_texture.setdefault(t['asset_path'].split('.')[0], set()).add(use.get('role'))
    selected, excluded, ambiguous = [], [], []
    clone_names = {}
    for t in doc['textures']:
        path = t['asset_path']
        flagged = t.get('definite_binding_settings_mismatches') or t.get('warnings')
        if not flagged:
            continue
        key = path.split('.')[0]
        roles = roles_by_texture.get(key, set())
        reasons = []
        if key in exclude:
            excluded.append({'texture': path, 'reason': 'already repaired (bed albedo clones)'})
            continue
        if USAGE_MISMATCH not in (t.get('definite_binding_settings_mismatches') or []):
            reasons.append('no definite %s mismatch (warnings only: %s)' % (USAGE_MISMATCH, t.get('warnings')))
        if roles != {'albedo'}:
            reasons.append('roles %s (also used as a normal map or unknown)' % sorted(r or '?' for r in roles))
        if any(use.get('parameter') != 'BaseColorTexture' for use in t.get('usages') or []):
            reasons.append('a usage is not BaseColorTexture')
        if not (t.get('srgb') is False and t.get('compression_settings') == 'TC_NORMALMAP'):
            reasons.append('settings sRGB %s / %s' % (t.get('srgb'), t.get('compression_settings')))
        if t.get('settings_errors'):
            reasons.append('settings errors %s' % t['settings_errors'])
        if not path.startswith(parity_mod.ORIGINAL_ROOTS):
            reasons.append('outside %s' % (parity_mod.ORIGINAL_ROOTS,))
        if not any(use.get('bindings') for use in t.get('usages') or []):
            reasons.append('no bound slot')
        clone = parity_mod.clone_path(path)
        if clone in clone_names:
            reasons.append('clone name collides with %s' % clone_names[clone])
        if reasons:
            ambiguous.append({'texture': path, 'reasons': reasons})
            continue
        clone_names[clone] = path
        selected.append({'texture': path, 'clone': clone, 'srgb': t['srgb'],
                         'compression_settings': t['compression_settings'],
                         'usages': [{'material': use['material'], 'parameter': use['parameter'],
                                     'bindings': [(b['component'], int(b['slot']), b.get('actor'))
                                                  for b in use.get('bindings') or []]}
                                    for use in t['usages']]})
    materials = {}
    for row in selected:
        for use in row['usages']:
            if use['material'] in materials:
                raise MaterialFixError('Material %s samples two selected textures as albedo' % use['material'])
            materials[use['material']] = row['texture']
    return {'schema': 'sub01.home-materials-usage-selection.v1', 'source_generated_utc': doc.get('generated_utc'),
            'selected': selected, 'excluded': excluded, 'ambiguous': ambiguous,
            'count': len(selected), 'materials': materials}


def repair_usage_albedo(doc, *, u=None, actor_subsystem=None, load_level=True, save=True, backup=True,
                        expect_count=None):
    """Clone every selected texture (sRGB/TC_DEFAULT, originals untouched) and re-point ONLY the
    BaseColorTexture of each material that samples it as albedo, through owned child MICs on the same
    slots. No tint or other parameter changes. Idempotent; fail closed; --restore reverts."""
    if u is None:
        import unreal as u  # noqa: N813
    selection = select_usage_repairs(doc)
    if expect_count is not None and selection['count'] != expect_count:
        raise MaterialFixError('Usage selection has %d textures, expected %d: %s' % (
            selection['count'], expect_count, [r['texture'] for r in selection['selected']]))
    level, actors = _live_actors(u, actor_subsystem, load_level)
    model = model_from_live(u, actors)
    components = model['objects']['components']
    rows_by_slot = {(r['component_path'], r['slot']): r for r in model['rows']}
    # ---- pre-flight: textures ----
    clone_work, verified = [], []
    for row in selection['selected']:
        path = row['texture']
        original = u.load_asset(path.split('.')[0])
        if original is None or not isinstance(original, u.Texture2D):
            raise MaterialFixError('Usage repair refused: %s missing or not a Texture2D' % path)
        settings = texture_settings(u, original)
        if not (settings['srgb'] is False and settings['compression_settings'] == 'TC_NORMALMAP'):
            raise MaterialFixError('Usage repair refused: %s live state %s differs from the usage file' % (path, settings))
        if any(settings[k] != v for k, v in parity_mod.ADJUST_DEFAULTS.items()) or settings['lod_bias'] != 0:
            raise MaterialFixError('Usage repair refused: %s has non-neutral LOD/adjust settings %s' % (path, settings))
        existing = u.load_asset(row['clone'].split('.')[0])
        if existing is not None:
            problems = clone_problems(u, original, existing, path)
            if problems:
                raise MaterialFixError('Usage repair refused: existing clone %s differs: %s' % (row['clone'], problems))
            verified.append({'original': path, 'clone': row['clone'], 'action': 'verified existing'})
        else:
            clone_work.append((path, original, settings, row['clone']))
    # ---- pre-flight: materials and slots ----
    mic_work = []
    for row in selection['selected']:
        for use in row['usages']:
            mpath = use['material']
            record = model['materials'].get(mpath)
            material = model['objects']['materials'].get(mpath)
            if record is None or material is None:
                raise MaterialFixError('Usage repair refused: material %s is not bound in the live level' % mpath)
            tname = pick_parameter(record['names'].get('texture'), ('BaseColorTexture',))
            if tname is None:
                raise MaterialFixError('Usage repair refused: %s does not enumerate BaseColorTexture (%s)' % (
                    mpath, record['names'].get('texture')))
            if str(record['values']['texture'].get(tname) or '').split('.')[0] != row['texture'].split('.')[0]:
                raise MaterialFixError('Usage repair refused: %s BaseColorTexture is %s, not %s' % (
                    mpath, record['values']['texture'].get(tname), row['texture']))
            slots = []
            for cpath, slot, _ in use['bindings']:
                live = rows_by_slot.get((cpath, slot))
                if live is None or len(components.get(cpath, [])) != 1:
                    raise MaterialFixError('Usage repair refused: slot %s#%d missing or not unique' % (cpath, slot))
                bound = original_path(model, live['material_path'])
                if str(bound).split('.')[0] != mpath.split('.')[0]:
                    raise MaterialFixError('Usage repair refused: slot %s#%d binds %s, not %s' % (
                        cpath, slot, live['material_path'], mpath))
                slots.append((cpath, slot, live['material_path']))
            live_users = [(r['component_path'], r['slot']) for r in model['rows']
                          if str(original_path(model, r['material_path'])).split('.')[0] == mpath.split('.')[0]]
            if sorted(live_users) != sorted((c, s_) for c, s_, _ in slots):
                raise MaterialFixError('Usage repair refused: %s live slots %s differ from the usage file %s' % (
                    mpath, sorted(live_users), sorted((c, s_) for c, s_, _ in slots)))
            mic_work.append({'material': mpath, 'object': material, 'parameter': tname, 'clone': row['clone'],
                             'texture': row['texture'], 'slots': slots})
    # ---- mutation: clones, owned MICs, then slots ----
    state = _load_backup(u)
    created = [_create_clone(u, state, *w) for w in clone_work]
    mel = u.MaterialEditingLibrary
    pending, mic_report = [], []
    for item in mic_work:
        clone = u.load_asset(item['clone'].split('.')[0])
        name = usage_mic_name(item['material'])
        instance, made = _load_or_create(u, name, 'MaterialInstanceConstant', 'MaterialInstanceConstantFactoryNew')
        changed = made
        parent = _path(instance.get_editor_property('parent'))
        if parent != _path(item['object']):
            if not made:
                raise MaterialFixError('Owned %s is parented to %s, not %s' % (name, parent, item['material']))
            mel.set_material_instance_parent(instance, item['object'])
        if _path(mel.get_material_instance_texture_parameter_value(instance, item['parameter'])) != _path(clone):
            mel.set_material_instance_texture_parameter_value(instance, item['parameter'], clone)
            changed = True
        if changed:
            mel.update_material_instance(instance)
            if not u.EditorAssetLibrary.save_loaded_asset(instance):
                raise MaterialFixError('Saving owned colour material %s failed; slots unchanged' % name)
        if made:
            owned = state.setdefault('owned_assets', [])
            if _path(instance).split('.')[0] not in owned:
                owned.append(_path(instance).split('.')[0])
        mic_report.append({'material': item['material'], 'instance': _path(instance), 'created': made,
                           'override': {item['parameter']: item['clone']}})
        for cpath, slot, current in item['slots']:
            if current != _path(instance):
                pending.append((cpath, slot, components[cpath][0], current, instance))
    (_state_dir(u) / BACKUP_NAME).write_text(json.dumps(state, indent=1) + '\n')
    map_backup = _backup_map(u) if (pending and backup and save) else None
    touched, changes = {}, []
    for cpath, slot, component, current, instance in pending:
        key = '%s#%d' % (cpath, slot)
        state['slots'].setdefault(key, {'component_path': cpath, 'slot': slot, 'original_material': current,
                                        'target': 'usage-albedo-repair'})
        if cpath not in touched:
            touched[cpath] = (component, component_fingerprint(u, component))
        component.set_material(slot, instance)
        if _path(component.get_material(slot)) != _path(instance):
            raise MaterialFixError('Slot assignment did not take: ' + key)
        changes.append({'slot': key, 'from': current, 'to': _path(instance)})
    for cpath, (component, before) in touched.items():
        if component_fingerprint(u, component) != before:
            raise MaterialFixError('Non-material property changed on %s; map not saved' % cpath)
    if pending:
        (_state_dir(u) / BACKUP_NAME).write_text(json.dumps(state, indent=1) + '\n')
        if save and not level.save_current_level():
            raise MaterialFixError('Level failed to save; map backup at %s' % map_backup)
    report = {'schema': 'sub01.home-materials-usage-repair.v1', 'selection': selection,
              'textures': verified + created, 'instances': mic_report, 'slot_changes': changes,
              'map_backup': map_backup, 'visual_match_claimed': False}
    (_state_dir(u) / 'usage-repair-report.json').write_text(json.dumps(report, indent=1, default=str) + '\n')
    u.log('SUB01_USAGE_ALBEDO_REPAIR ' + json.dumps({'textures': len(selection['selected']),
                                                     'created_clones': len(created), 'slot_changes': len(changes)}))
    return report


def repair_and_apply(presets, *, u=None, actor_subsystem=None, load_level=True, save=True, glb=None):
    """(b) repair clones, (c) parity export of originals + clones and finalize, (d) mapping check, (e) apply.
    Stops at the first failure."""
    if u is None:
        import unreal as u  # noqa: N813
    repair = repair_albedo_textures(u=u, actor_subsystem=actor_subsystem, load_level=load_level)
    _, actors = _live_actors(u, actor_subsystem, False)
    originals = bed_texture_paths(model_from_live(u, actors))
    out = _state_dir(u) / ('parity-%d' % time.time_ns())
    parity_mod.export_textures(out, tuple(originals) + tuple(parity_mod.clone_path(o) for o in originals), u=u)
    glb = Path(glb) if glb else Path(u.Paths.project_dir()) / 'SourceAssets/full-home.glb'
    try:
        parity = parity_mod.finalize(out, glb)
    except ImportError as error:
        raise MaterialFixError('Stopped after the clone export: PIL/numpy unavailable in the editor (%s). Run '
                               '`python3 tools/unreal_export_texture_parity.py --finalize %s --glb %s > '
                               'texture-parity.json`, then --apply --albedo-clones --parity texture-parity.json'
                               % (error, out, glb)) from None
    (out / 'texture-parity.json').write_text(json.dumps(parity, indent=1) + '\n')
    report = apply(presets, u=u, actor_subsystem=actor_subsystem, load_level=False, save=save,
                   parity=parity, albedo_clones=True)
    report['albedo_repair'] = repair
    report['parity_file'] = str(out / 'texture-parity.json')
    return report


def apply(presets, *, u=None, actor_subsystem=None, load_level=True, save=True, backup=True,
          allow_master=False, parity=None, albedo_clones=False):
    if u is None:
        import unreal as u  # noqa: N813
    level, actors = _live_actors(u, actor_subsystem, load_level)
    model = model_from_live(u, actors)
    check = mapping_check(model, presets, parity, albedo_clones)
    if not check['ok']:
        raise MaterialFixError('Pre-flight refused (nothing changed): %s' % json.dumps(
            {'mismatches': check['mismatches'], 'notes': check['notes'],
             'targets': [t for t in check['targets'] if not t['ok']]}, default=str))
    for target in check['targets']:
        for item in target['materials']:
            if item['path'] == 'owned_master_required' and not allow_master:
                raise MaterialFixError('Pre-flight refused: %s has no enumerated base-colour factor; owned master '
                                       'needs --allow-owned-master' % item['material'])
    for target in check['targets']:
        for item in target['materials']:
            # Never tint through a colour texture that is really a normal-map import.
            texture = u.load_asset(item['texture'].split('.')[0]) if item.get('texture') else None
            if texture is not None and not item.get('albedo_clone') and texture_settings(u, texture)['srgb'] is False:
                raise MaterialFixError('Pre-flight refused: %s samples %s, which is imported with sRGB False (%s); '
                                       'repair with owned albedo clones first' % (
                                           item['material'], item['texture'], texture_settings(u, texture)))
            if item.get('albedo_clone'):
                clone = u.load_asset(item['albedo_clone'].split('.')[0])
                if clone is None:
                    raise MaterialFixError('Pre-flight refused: albedo clone missing: ' + item['albedo_clone'])
                problems = clone_problems(u, texture, clone, item['texture'])
                if problems:
                    raise MaterialFixError('Pre-flight refused: albedo clone %s: %s' % (item['albedo_clone'], problems))
    components = model['objects']['components']
    for target in check['targets']:
        for item in target['materials']:
            for cpath, _ in item['slots']:
                if len(components.get(cpath, [])) != 1:
                    raise MaterialFixError('Pre-flight refused: component path not unique: ' + cpath)
    # ---- mutation: owned assets first, slots last ----
    state = _load_backup(u)
    instances, pending, new_owned = {}, [], False
    for target in check['targets']:
        for item in target['materials']:
            if item['already_intended']:
                continue  # the real parent already carries the intended factor: nothing to restore
            item = dict(item, desaturation=target.get('desaturation', 0.0), uv_tiling=target.get('uv_tiling', 1.0))
            existed = u.load_asset(OWNED_DIR + '/' + owned_name(item['material'])) is not None
            instance, changed, overrides = ensure_instance(u, model, item, allow_master)
            if not existed:
                owned = state.setdefault('owned_assets', [])
                if _path(instance).split('.')[0] not in owned:
                    owned.append(_path(instance).split('.')[0])
                    new_owned = True
            instances[item['material']] = {'path': _path(instance), 'changed': changed, 'overrides': overrides,
                                           'target': target['id']}
            for cpath, slot in item['slots']:
                component = components[cpath][0]
                current = component.get_material(slot)
                if _path(current) != _path(instance):
                    pending.append((target['id'], cpath, slot, component, current, instance))
    map_backup = _backup_map(u) if (pending and backup and save) else None
    changes, touched = [], {}
    for target_id, cpath, slot, component, current, instance in pending:
        key = '%s#%d' % (cpath, slot)
        state['slots'].setdefault(key, {'component_path': cpath, 'slot': slot,
                                        'original_material': _path(current), 'target': target_id})
        if cpath not in touched:
            touched[cpath] = (component, component_fingerprint(u, component))
        component.set_material(slot, instance)
        if _path(component.get_material(slot)) != _path(instance):
            raise MaterialFixError('Slot assignment did not take: ' + key)
        changes.append({'slot': key, 'from': _path(current), 'to': _path(instance)})
    for cpath, (component, before) in touched.items():
        if component_fingerprint(u, component) != before:
            raise MaterialFixError('Non-material property changed on %s; map not saved' % cpath)
    if pending or new_owned:
        (_state_dir(u) / BACKUP_NAME).write_text(json.dumps(state, indent=1) + '\n')
    if pending:
        if save and not level.save_current_level():
            raise MaterialFixError('Level failed to save; map backup at %s' % map_backup)
    report = {'schema': 'sub01.home-materials-apply.v1', 'presets': list(presets), 'slot_changes': changes,
              'instances': instances, 'map_backup': map_backup, 'mapping': check, 'visual_match_claimed': False}
    (_state_dir(u) / REPORT_NAME).write_text(json.dumps(report, indent=1, default=str) + '\n')
    u.log('SUB01_MATERIALS_FIX ' + json.dumps({'presets': list(presets), 'slot_changes': len(changes)}))
    return report


def restore(*, u=None, actor_subsystem=None, load_level=True, save=True):
    if u is None:
        import unreal as u  # noqa: N813
    level, actors = _live_actors(u, actor_subsystem, load_level)
    state = _load_backup(u)
    if not state['slots'] and not state.get('owned_assets'):
        raise MaterialFixError('No recorded material backup to restore')
    components = {}
    for actor in actors.get_all_level_actors():
        for component in actor.get_components_by_class(u.StaticMeshComponent):
            components.setdefault(component.get_path_name(), []).append(component)
    problems, work = [], []
    for key, entry in sorted(state['slots'].items()):
        found = components.get(entry['component_path'], [])
        if len(found) != 1:
            problems.append('%s: %d components with that path' % (key, len(found)))
            continue
        material = u.load_asset(entry['original_material']) if entry['original_material'] else None
        if entry['original_material'] and material is None:
            problems.append('%s: original material missing %s' % (key, entry['original_material']))
            continue
        work.append((found[0], entry['slot'], material))
    if problems:
        raise MaterialFixError('Restore refused (nothing changed):\n  ' + '\n  '.join(problems))
    for component, slot, material in work:
        before = component_fingerprint(u, component)
        component.set_material(slot, material)
        if component_fingerprint(u, component) != before:
            raise MaterialFixError('Restore changed a non-material property; map not saved')
    if save and not level.save_current_level():
        raise MaterialFixError('Restore failed to save')
    deleted = []
    for asset in reversed(state.get('owned_assets', [])):     # MICs first, then texture clones
        if not asset.startswith(OWNED_DIR + '/') or not asset_name(asset).startswith(OWNED_PREFIX):
            raise MaterialFixError('Refusing to delete non-owned asset %s' % asset)
        if u.load_asset(asset) is not None:
            if not u.EditorAssetLibrary.delete_asset(asset):
                raise MaterialFixError('Could not delete owned asset %s' % asset)
            deleted.append(asset)
    path = _state_dir(u) / BACKUP_NAME
    path.rename(path.with_name('restored-%d-%s' % (time.time_ns(), BACKUP_NAME)))
    return {'restored_slots': len(work), 'deleted_owned_assets': deleted}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parse(argv):
    p = argparse.ArgumentParser(description='SUB-01 home material fixes (dry run unless --apply).')
    p.add_argument('--preset', action='append', choices=sorted(spec.PRESETS),
                   help='repeatable; default: %s' % ','.join(spec.DEFAULT_PRESETS))
    mode = p.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--mapping-check', action='store_true')
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--restore', action='store_true')
    mode.add_argument('--repair-albedo-textures', action='store_true',
                      help='create/verify owned sRGB TC_DEFAULT clones of the bed albedo textures (originals untouched)')
    mode.add_argument('--repair-and-apply', action='store_true',
                      help='repair clones, export+finalize parity, mapping check, apply; stops at the first failure')
    p.add_argument('--albedo-clones', action='store_true', help='bed materials sample the owned albedo clones')
    p.add_argument('--scope', choices=('bed', 'usage-file'), default='bed',
                   help='--repair-albedo-textures scope: the 4 bed textures, or every texture selected from --usage-file')
    p.add_argument('--usage-file', type=Path, help='root texture-usage audit JSON (sub01-private-texture-usage-audit-v1)')
    p.add_argument('--expect-count', type=int, help='refuse unless the usage selection has exactly this many textures')
    p.add_argument('--select-only', action='store_true', help='pure: print the usage-file selection and exit')
    p.add_argument('--glb', type=Path, help='full-home.glb for --repair-and-apply (default <project>/SourceAssets)')
    p.add_argument('--inventory', type=Path, help='root inventory JSON for a pure --mapping-check')
    p.add_argument('--parity', type=Path, help='texture parity JSON (tools/unreal_export_texture_parity.py)')
    p.add_argument('--allow-owned-master', action='store_true',
                   help='explicit fallback: MIC of the owned SUB01_MatFix_Master for parents without a factor')
    p.add_argument('--no-save', action='store_true')
    p.add_argument('--quit', action='store_true')
    return p.parse_args(argv)


def main(argv=None):
    args = _parse(sys.argv[1:] if argv is None else argv)
    presets = args.preset or list(spec.DEFAULT_PRESETS)
    if args.select_only:
        if not args.usage_file:
            raise MaterialFixError('--select-only needs --usage-file')
        selection = select_usage_repairs(json.loads(args.usage_file.read_text()))
        print(json.dumps(selection, indent=1))
        return 0 if args.expect_count in (None, selection['count']) else 2
    parity = json.loads(args.parity.read_text()) if args.parity else None
    if args.mapping_check and args.inventory:
        report = mapping_check(model_from_inventory(json.loads(args.inventory.read_text())), presets, parity,
                               args.albedo_clones)
        print(json.dumps(report, indent=1, default=str))
        return 0 if report['ok'] else 2
    if not (args.apply or args.restore or args.mapping_check or args.repair_albedo_textures or args.repair_and_apply):
        print(json.dumps(spec.plan(presets), indent=1, default=str))
        return 0
    import unreal as u  # noqa: N813
    try:
        if args.mapping_check:
            _, actors = _live_actors(u, None, True)
            report = mapping_check(model_from_live(u, actors), presets, parity, args.albedo_clones)
            (_state_dir(u) / MAPPING_NAME).write_text(json.dumps(report, indent=1, default=str) + '\n')
            u.log('SUB01_MATERIALS_MAPPING ' + json.dumps({'ok': report['ok'], 'mismatches': len(report['mismatches'])}))
            print(json.dumps({'ok': report['ok'], 'mismatches': report['mismatches'], 'notes': report['notes']},
                             default=str))
        elif args.restore:
            print(json.dumps(restore(u=u, save=not args.no_save)))
        elif args.repair_albedo_textures and args.scope == 'usage-file':
            if not args.usage_file:
                raise MaterialFixError('--scope usage-file needs --usage-file')
            report = repair_usage_albedo(json.loads(args.usage_file.read_text()), u=u, save=not args.no_save,
                                         expect_count=args.expect_count)
            print(json.dumps({'textures': len(report['textures']), 'slot_changes': len(report['slot_changes'])}))
        elif args.repair_albedo_textures:
            print(json.dumps(repair_albedo_textures(u=u), default=str))
        elif args.repair_and_apply:
            report = repair_and_apply(presets, u=u, save=not args.no_save, glb=args.glb)
            print(json.dumps({'applied': True, 'slot_changes': len(report['slot_changes']),
                              'parity_file': report['parity_file']}))
        else:
            report = apply(presets, u=u, save=not args.no_save, allow_master=args.allow_owned_master,
                           parity=parity, albedo_clones=args.albedo_clones)
            print(json.dumps({'applied': True, 'slot_changes': len(report['slot_changes'])}))
    finally:
        if args.quit:
            u.SystemLibrary.quit_editor()
    return 0


if __name__ == '__main__':
    sys.exit(main())
