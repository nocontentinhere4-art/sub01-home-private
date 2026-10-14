"""Import the real CC0 lamps built by tools/build_real_lamps.py into the loaded ActualHome.

Sole editor owner, ActualHome already loaded (never loads a level, never builds lighting):

  run(out_dir)                 # import + place + hide originals (idempotent)
  run(out_dir, dry_run=True)   # validate everything, change nothing
  run(out_dir, restore=True)   # unhide exactly what this tool hid, remove SUB01_RealLamp_* actors

out_dir holds placement-report.json, original-hide-manifest.json and the per-role
SUB01_RealLamp_<role>.glb files. Fail closed: every identity (file hashes, original
actors, authored light anchors, the verified import transform) is checked before the
first mutation. Originals are hidden in game and editor, never destroyed; collision is
left unchanged. Shared batches (e.g. node 163) are never hidden: their exact lamp
components (desk stem: node 163 / prim 0 / tris 1800..1839) are removed by root's
byte-preserving glTF splice from the reviewed union manifest, never by this script. SUB01_AuthoredLight_* components are never moved; their position
relative to the new bulb is reported with a proposal. Imported materials are owned
copies under /Game/Sub01Home/RealLamps/ and have every emissive parameter zeroed.
Screens/devices are protected: any hide target that looks like one is refused.
"""
import hashlib
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from unreal_home_coordinates import infer_import_transform, convert_position  # noqa: E402

LEVEL = '/Game/Sub01Home/ActualHome'
DEST = '/Game/Sub01Home/RealLamps'
ACTOR_PREFIX = 'SUB01_RealLamp_'
LIGHT_PREFIX = 'SUB01_AuthoredLight_'
STATE_NAME = 'unreal-real-lamps-state.json'
SCREEN_PATTERN = re.compile(r'screen|monitor|display|lcd|tv|television|phone|keyboard|keycap|pc_|tower|'
                            r'computer|laptop|tablet', re.I)
PROTECTED_NODES = {66}  # kitchen work strip is never a replaced lamp
BEDSIDE_EMITTERS = {198, 199}  # hidden (not destroyed/excised) only when BedLamp is replaced
ANCHOR_TOL_CM = 1.5
SRGB_PARAMS = ('basecolor', 'base_color', 'diffuse', 'albedo')
LINEAR_PARAMS = ('normal', 'metallic', 'roughness', 'occlusion', 'arm', 'orm')


class Refuse(RuntimeError):
    pass


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_inputs(out_dir):
    out_dir = Path(out_dir)
    report = json.loads((out_dir / 'placement-report.json').read_text())
    manifest = json.loads((out_dir / 'original-hide-manifest.json').read_text())
    if report.get('schema') != 'sub01.real-lamps.v1' or manifest.get('schema') != 'sub01.real-lamps.v1.hide-manifest':
        raise Refuse('unexpected report/manifest schema')
    exports = report.get('exports') or {}
    for role, plan in report['roles'].items():
        glb = out_dir / plan['ue_glb']
        if not glb.exists() or exports.get(glb.name) != sha256(glb):
            raise Refuse(f'{role}: exported GLB missing or sha256 differs from placement report')
    for e in manifest['entries']:
        if e['role'] not in report['roles']:
            raise Refuse(f'manifest hides {e["ue_actor_name"]} for unplaced role {e["role"]}')
        if e['source_node_index'] in PROTECTED_NODES:
            raise Refuse(f'protected node {e["source_node_index"]} in hide manifest')
        if e['source_node_index'] in BEDSIDE_EMITTERS and e['role'] != 'BedLamp':
            raise Refuse(f'bedside emitter {e["source_node_index"]} hidden for role {e["role"]}')
        if e['source_node_index'] in {x['node'] for x in manifest.get('excisions', [])}:
            raise Refuse(f'shared batch node {e["source_node_index"]} would be hidden as a whole')
        for text in [e.get('source_node_name') or ''] + list(e.get('materials') or []):
            if SCREEN_PATTERN.search(text) and not text.startswith('desk_lamp_arm_01'):
                raise Refuse(f'protected screen/device identity in hide manifest: {text}')
        if e['ue_actor_name'] != f'full-home_node_{e["source_node_index"]}':
            raise Refuse('hide manifest actor name differs from source node index')
    red_new = [r for r in report['roles'].values() if r['asset'] == 'desk_lamp_arm_01']
    red_hidden = [e for e in manifest['entries'] if e['part'] == 'relocated_red_desk_lamp_arm_01']
    if len(red_new) > 1 or (red_new and not red_hidden):
        raise Refuse('a second red desk lamp would remain visible')
    return report, manifest


def _vec(v):
    return [float(v.x), float(v.y), float(v.z)]


def _actors_by_name(actors):
    by = {}
    for a in actors:
        by.setdefault(a.get_name(), []).append(a)
    return by


def _actors_by_label(actors):
    by = {}
    for a in actors:
        by.setdefault(a.get_actor_label(), []).append(a)
    return by


def verify_anchors(u, actors, report, manifest):
    """Verified import transform from the exact original node pivots, cross-checked on the lights."""
    by_name = _actors_by_name(actors)
    pairs, targets = [], []
    for e in manifest['entries']:
        found = by_name.get(e['ue_actor_name'], [])
        if len(found) != 1:
            raise Refuse(f'{e["ue_actor_name"]}: expected exactly one actual actor, found {len(found)}')
        actor = found[0]
        if e.get('source_node_name') and actor.get_actor_label() != e['source_node_name']:
            raise Refuse(f'{e["ue_actor_name"]}: label {actor.get_actor_label()} differs from source node name')
        pairs.append((tuple(e['source_translation_m']), tuple(_vec(actor.get_actor_location()))))
        targets.append((e, actor))
    # unique pivots only (several red-lamp nodes can share a pivot)
    unique = list({tuple(round(c, 4) for c in p[0]): p for p in pairs}.values())
    try:
        transform = infer_import_transform(unique, ANCHOR_TOL_CM)
    except ValueError as exc:
        raise Refuse(f'anchor transform not verified: {exc}')
    by_label = _actors_by_label(actors)
    lights = {}
    for role, plan in report['roles'].items():
        label = LIGHT_PREFIX + role
        found = by_label.get(label, [])
        if len(found) != 1:
            raise Refuse(f'{label}: expected exactly one authored light, found {len(found)}')
        actual = _vec(found[0].get_actor_location())
        expected = convert_position(plan['light_source_m'], transform)
        if math.dist(actual, expected) > ANCHOR_TOL_CM:
            raise Refuse(f'{label}: at {actual}, expected {expected} from verified anchors')
        lights[role] = found[0]
    return transform, targets, lights


def ue_yaw(yaw_source_deg, transform):
    axes, signs = transform['axes'], transform['signs']

    def m(v):
        return [signs[i] * v[axes[i]] for i in range(3)]
    t = math.radians(yaw_source_deg)
    a = m((1.0, 0.0, 0.0))
    b = m((math.cos(t), 0.0, -math.sin(t)))
    psi = math.degrees(math.atan2(b[1], b[0]) - math.atan2(a[1], a[0]))
    return (psi + 180.0) % 360.0 - 180.0


def _owned_assets(u, role):
    path = f'{DEST}/{role}'
    return [a for a in u.EditorAssetLibrary.list_assets(path, recursive=True, include_folder=False)]


def import_role(u, glb, role):
    task = u.AssetImportTask()
    task.set_editor_property('filename', str(glb))
    task.set_editor_property('destination_path', f'{DEST}/{role}')
    task.set_editor_property('automated', True)
    task.set_editor_property('replace_existing', True)
    task.set_editor_property('save', True)
    u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    meshes = []
    for path in _owned_assets(u, role):
        asset = u.EditorAssetLibrary.load_asset(path)
        if isinstance(asset, u.StaticMesh):
            meshes.append(asset)
    if len(meshes) != 1:
        raise Refuse(f'{role}: import produced {len(meshes)} static meshes, expected 1')
    return meshes[0]


def sanitize_materials(u, mesh, role):
    """Zero every emissive parameter on owned imported materials; check texture colour spaces."""
    report = []
    for i, sm in enumerate(mesh.get_editor_property('static_materials')):
        mat = sm.get_editor_property('material_interface')
        row = {'slot': i, 'slot_name': str(sm.get_editor_property('material_slot_name')),
               'material': mat.get_path_name() if mat else None, 'emissive_zeroed': [], 'textures': {}}
        if mat is None or not mat.get_path_name().startswith(DEST + '/'):
            raise Refuse(f'{role}: slot {i} material is not an owned import under {DEST}')
        if isinstance(mat, u.MaterialInstanceConstant):
            mel = u.MaterialEditingLibrary
            for name in mel.get_scalar_parameter_names(mat):
                if 'emiss' in str(name).lower():
                    mel.set_material_instance_scalar_parameter_value(mat, name, 0.0)
                    row['emissive_zeroed'].append(str(name))
            for name in mel.get_vector_parameter_names(mat):
                if 'emiss' in str(name).lower():
                    mel.set_material_instance_vector_parameter_value(mat, name, u.LinearColor(0, 0, 0, 1))
                    row['emissive_zeroed'].append(str(name))
            for name in mel.get_texture_parameter_names(mat):
                tex = mel.get_material_instance_texture_parameter_value(mat, name)
                low = str(name).lower()
                if tex is None:
                    continue
                if 'emiss' in low:
                    raise Refuse(f'{role}: emissive texture bound on {mat.get_name()}.{name}')
                want = True if any(k in low for k in SRGB_PARAMS) else False if any(k in low for k in LINEAR_PARAMS) else None
                srgb = bool(tex.get_editor_property('srgb'))
                if want is not None and srgb != want:
                    tex.set_editor_property('srgb', want)
                    u.EditorAssetLibrary.save_loaded_asset(tex)
                row['textures'][str(name)] = {'texture': tex.get_path_name(), 'srgb': want if want is not None else srgb,
                                              'fixed': want is not None and srgb != want}
            u.EditorAssetLibrary.save_loaded_asset(mat)
        else:
            raise Refuse(f'{role}: slot {i} is not a MaterialInstanceConstant; emission cannot be verified')
        report.append(row)
    return report


def run(out_dir, dry_run=False, restore=False, u=None):
    if u is None:
        import unreal as u
    out_dir = Path(out_dir)
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if world is None or world.get_path_name().split('.', 1)[0] != LEVEL:
        raise Refuse('ActualHome must already be loaded by the sole editor owner')
    eas = u.get_editor_subsystem(u.EditorActorSubsystem)
    actors = list(eas.get_all_level_actors())
    state_path = out_dir / STATE_NAME
    if restore:
        state = json.loads(state_path.read_text()) if state_path.exists() else {'hidden': []}
        by_name = _actors_by_name(actors)
        plan = []
        for row in state['hidden']:
            found = by_name.get(row['ue_actor_name'], [])
            if len(found) != 1:
                raise Refuse(f'restore: {row["ue_actor_name"]} not uniquely present')
            plan.append((found[0], row))
        owned = [a for a in actors if a.get_actor_label().startswith(ACTOR_PREFIX)]
        if dry_run:
            return {'restore': True, 'dry_run': True, 'unhide': [r['ue_actor_name'] for _, r in plan],
                    'remove': [a.get_actor_label() for a in owned]}
        for actor, row in plan:
            actor.set_actor_hidden_in_game(bool(row['was_hidden_in_game']))
            actor.set_is_temporarily_hidden_in_editor(bool(row['was_hidden_in_editor']))
            try:
                actor.set_editor_property('hidden_ed', bool(row['was_hidden_in_editor']))
            except Exception:
                pass
        for a in owned:
            eas.destroy_actor(a)
        state_path.write_text(json.dumps({'hidden': []}, indent=2))
        u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
        return {'restore': True, 'unhidden': [r['ue_actor_name'] for _, r in plan],
                'removed': [a.get_actor_label() for a in owned]}

    report, manifest = load_inputs(out_dir)
    if not report['roles']:
        raise Refuse('placement report has no placed roles')
    transform, targets, lights = verify_anchors(u, actors, report, manifest)
    by_label = _actors_by_label(actors)
    for role in report['roles']:
        if len(by_label.get(ACTOR_PREFIX + role, [])) > 1:
            raise Refuse(f'duplicate {ACTOR_PREFIX}{role} actors')
    planned = {}
    for role, plan in report['roles'].items():
        loc = convert_position(plan['origin_source_m'], transform)
        bulb = convert_position(plan['bulb_source_m'], transform)
        light = _vec(lights[role].get_actor_location())
        d = math.dist(light, bulb)
        planned[role] = {'location_cm': list(loc), 'yaw_deg': ue_yaw(plan['yaw_source_deg'], transform),
                         'bulb_cm': list(bulb), 'light_cm': light, 'light_to_bulb_cm': d,
                         'light_status': 'at-bulb' if d <= 3 else 'off-bulb (proposal: move light to bulb_cm; not moved)'}
    result = {'transform': transform, 'planned': planned, 'hide': [e['ue_actor_name'] for e in manifest['entries']],
              'dry_run': dry_run}
    if dry_run:
        return result

    # ---- mutations (all identities verified above) ----
    previous = json.loads(state_path.read_text()) if state_path.exists() else {'hidden': []}
    known = {r['ue_actor_name']: r for r in previous['hidden']}
    for role, plan in report['roles'].items():
        mesh = import_role(u, out_dir / plan['ue_glb'], role)
        planned[role]['materials'] = sanitize_materials(u, mesh, role)
        existing = by_label.get(ACTOR_PREFIX + role, [])
        loc = u.Vector(*planned[role]['location_cm'])
        rot = u.Rotator(roll=0.0, pitch=0.0, yaw=planned[role]['yaw_deg'])
        actor = existing[0] if existing else eas.spawn_actor_from_class(u.StaticMeshActor, loc, rot)
        actor.set_actor_label(ACTOR_PREFIX + role)
        actor.set_actor_location(loc, False, False)
        actor.set_actor_rotation(rot, False)
        actor.set_actor_scale3d(u.Vector(1.0, 1.0, 1.0))
        comp = actor.get_component_by_class(u.StaticMeshComponent)
        comp.set_static_mesh(mesh)
        if role in ('LowerPendant', 'UpperPendant'):
            comp.set_editor_property('cast_shadow', False)  # globe must not trap the pendant light
        actor.tags = [u.Name('SUB01RealLamp'), u.Name(role)]
        planned[role]['actor'] = actor.get_path_name()
    for e, actor in targets:
        if e['ue_actor_name'] not in known:
            known[e['ue_actor_name']] = {'ue_actor_name': e['ue_actor_name'],
                                         'was_hidden_in_game': bool(actor.get_editor_property('hidden')),
                                         'was_hidden_in_editor': bool(actor.is_temporarily_hidden_in_editor())}
        actor.set_actor_hidden_in_game(True)
        actor.set_is_temporarily_hidden_in_editor(True)
        try:
            actor.set_editor_property('hidden_ed', True)  # persistent editor hide where exposed
        except Exception:
            pass
    state_path.write_text(json.dumps({'hidden': list(known.values())}, indent=2))
    u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
    (out_dir / 'unreal-real-lamps-report.json').write_text(json.dumps(result, indent=2, default=str))
    return result


if __name__ == '__main__':  # pragma: no cover
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('out_dir')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--restore', action='store_true')
    a = p.parse_args()
    try:
        print(json.dumps(run(a.out_dir, a.dry_run, a.restore), indent=2, default=str))
    except Refuse as exc:
        print('REFUSED:', exc)
        raise SystemExit(2)
