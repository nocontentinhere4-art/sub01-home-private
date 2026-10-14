"""Import the real shelf books into the existing private native map; hide (never destroy) the cube books.

Root runs this in the UE editor on the authorized server with the native game stopped:
    UnrealEditor-Cmd <project> -run=pythonscript \
        -script="/workspace/sub01-home-private/tools/unreal_import_real_shelf_books.py --root /workspace/sub01-home-private/out/real-books"
    ... add --restore to undo (unhide originals, delete only SUB01_RealBook_* actors and /Game/Sub01Home/RealBooks).

Inputs (written by tools/build_real_shelf_books.py, never edited by hand):
    real-shelf-books.json, real-shelf-books.glb, original-hide-manifest.json

Fail closed:
  * the Blender receipt must be a real (not dry-run) evaluated build whose GLB sha256 matches;
  * every original cube book, the shelf object and the reference pivots must resolve to exactly one
    actor (canonical node name on actor label or component name, as tools/unreal_setup_home.py does);
  * the import transform is inferred (tools/unreal_home_coordinates.py) from originals + reference
    pivots, and the shelf actor must sit within SHELF_TOL_CM of the Blender base, else refuse;
  * every imported book actor must land within PLACE_TOL_CM of its exported pivot with uniform scale;
  * book textures must end with albedo sRGB + TC_Default, normal TC_Normalmap (non-sRGB), roughness /
    metallic-roughness / occlusion non-sRGB; owned textures are corrected, re-checked, else refused;
  * every pre-existing actor is fingerprinted (transform, meshes, materials, collision) before and after:
    any difference rolls back the import and refuses to save.
Material-batched cube books (several books, or books plus other geometry, in one node) are NEVER hidden
whole: the manifest lists them under `excisions` (triangle IDs + remainder spec) and this script refuses
until root has applied that excision and passes --excision-applied; those nodes are then left untouched.
Originals: actor hidden in game + component visibility off (editor), collision untouched. New books:
NoCollision (decor never alters pawn movement or the seat/keyboard contact audits).
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from unreal_home_coordinates import infer_import_transform, convert_position  # noqa: E402

LEVEL = '/Game/Sub01Home/ActualHome'
DESTINATION = '/Game/Sub01Home/RealBooks'
LABEL_PREFIX = 'SUB01_RealBook_'
ACTOR_TAG = 'SUB01RealShelfBooks'
FOLDER = 'SUB01_RealShelfBooks'
RECEIPT = 'real-shelf-books-import.json'
SHELF_TOL_CM = 0.5
PLACE_TOL_CM = 0.5


def canonical(name):
    return re.sub('[^a-z0-9]', '', str(name).lower())


def validate_receipt(report, manifest, glb, excision_applied=False):
    export = report.get('additive_glb') or {}
    if (report.get('mode') != 'blender' or report.get('basis') != 'evaluated-geometry'
            or report.get('existing_objects_verified_unchanged', 0) < 1 or not report.get('built')
            or not export.get('objects') or not export.get('verified_additive_only')):
        raise ValueError('Missing successful real additive Blender receipt')
    if any(not n.startswith(LABEL_PREFIX) for n in export['objects']):
        raise ValueError('Export contains an object outside the owned real-books collection')
    digest = hashlib.sha256(Path(glb).read_bytes()).hexdigest()
    if digest != export.get('sha256') or manifest.get('additive_glb_sha256') != digest:
        raise ValueError('Actual additive GLB differs from the Blender receipt / hide manifest')
    originals = manifest.get('originals') or []
    excisions = manifest.get('excisions') or []
    excised = sum(len(x['excise']['components']) for x in excisions)
    if (len(originals) + excised != manifest.get('expected_count')
            or len({o['canonical'] for o in originals}) != len(originals)):
        raise ValueError('Hide manifest does not list the exact expected cube books')
    if {o['name'] for o in originals} & {x['node'] for x in excisions}:
        raise ValueError('A material-batched node is listed for hiding; never hide a shared batch')
    if excisions and not excision_applied:
        raise ValueError('Cube books are material-batched in ' + ', '.join(x['node'] for x in excisions) +
                         ': apply the triangle excision (manifest `excisions`) first, then pass --excision-applied')
    if not manifest.get('shelf_objects'):
        raise ValueError('Hide manifest has no shelf object to verify against')
    return digest


def required_texture_state(role):
    """(srgb, allowed compression names) for a glTF texture role."""
    if role == 'base_color':
        return True, ('TC_DEFAULT',)
    if role == 'normal':
        return False, ('TC_NORMALMAP',)
    return False, ('TC_DEFAULT', 'TC_MASKS', 'TC_GRAYSCALE')


def _enum_name(value):
    return str(value).split('.')[-1].split(':')[0].strip('<> ').upper()


def texture_role(asset_name, roles):
    """Role of an imported texture from the GLB image roles (exact canonical name), else from the
    Poly Haven suffix convention; None if unknown (the caller refuses)."""
    key = canonical(asset_name)
    hits = {role for image, role in roles.items() if canonical(Path(image).stem) and
            (key == canonical(Path(image).stem) or key.endswith(canonical(Path(image).stem)))}
    if len(hits) == 1:
        return hits.pop()
    if len(hits) > 1:
        return None
    low = asset_name.lower()
    for fragment, role in (('_diff', 'base_color'), ('basecolor', 'base_color'), ('_nor', 'normal'),
                           ('normal', 'normal'), ('_rough', 'metallic_roughness'), ('_arm', 'metallic_roughness'),
                           ('metallicroughness', 'metallic_roughness'), ('_ao', 'occlusion')):
        if fragment in low:
            return role
    return None


def check_textures(textures, roles, fix=True):
    """textures: [(name, texture obj with get/set_editor_property)]. Returns rows; raises on a texture
    without a role or one that still violates its colour space after the (owned-only) correction."""
    import_u = sys.modules.get('unreal')
    rows, bad = [], []
    for name, tex in textures:
        role = texture_role(name, roles)
        if role is None:
            bad.append({'texture': name, 'error': 'unknown role'})
            continue
        srgb, compressions = required_texture_state(role)
        if fix and import_u is not None:
            if bool(tex.get_editor_property('srgb')) != srgb:
                tex.set_editor_property('srgb', srgb)
            if _enum_name(tex.get_editor_property('compression_settings')) not in compressions:
                tex.set_editor_property('compression_settings',
                                        getattr(import_u.TextureCompressionSettings, compressions[0]))
        state = {'texture': name, 'role': role, 'srgb': bool(tex.get_editor_property('srgb')),
                 'compression': _enum_name(tex.get_editor_property('compression_settings'))}
        if state['srgb'] != srgb or state['compression'] not in compressions:
            bad.append({**state, 'error': 'colour space'})
        rows.append(state)
    if bad:
        raise RuntimeError('Book textures fail the colour-space contract: ' + json.dumps(bad))
    return rows


def fingerprint(u, actors):
    def tr(t):
        a, r, s = t.translation, t.rotation, t.scale3d
        return [round(float(x), 4) for x in (a.x, a.y, a.z, r.x, r.y, r.z, r.w, s.x, s.y, s.z)]
    result = {}
    for actor in actors:
        comps = []
        for c in actor.get_components_by_class(u.StaticMeshComponent):
            mesh = c.get_editor_property('static_mesh')
            comps.append({'path': c.get_path_name(), 'mesh': mesh.get_path_name() if mesh else None,
                          'transform': tr(c.get_world_transform()), 'collision': str(c.get_collision_enabled()),
                          'profile': str(c.get_collision_profile_name()),
                          'materials': [m.get_path_name() if m else None for m in c.get_materials()]})
        result[actor.get_path_name()] = {'label': actor.get_actor_label(), 'transform': tr(actor.get_actor_transform()),
                                         'components': sorted(comps, key=lambda e: e['path'])}
    return result


def resolve_unique(u, actors, entry):
    """Exactly one actor whose label or a static-mesh component name canonically equals the node
    name (or its bakeId). Returns (actor, component)."""
    keys = {entry['canonical'], entry.get('canonical_ident') or entry['canonical']}
    hits = []
    for actor in actors:
        if any(str(t) == ACTOR_TAG for t in actor.get_editor_property('tags')):
            continue
        comps = [c for c in actor.get_components_by_class(u.StaticMeshComponent) if c.get_editor_property('static_mesh')]
        if canonical(actor.get_actor_label()) in keys and comps:
            hits.append((actor, comps[0]))
            continue
        for c in comps:
            if canonical(c.get_name()) in keys:
                hits.append((actor, c))
                break
    if len(hits) != 1:
        raise RuntimeError(f'{entry["name"]}: expected exactly one actor, found {len(hits)} '
                           f'{[a.get_actor_label() for a, _ in hits][:6]}')
    return hits[0]


def import_transform(u, actors, manifest):
    """Infer the full-home import mapping from originals + reference pivots (never the shelf), then
    verify the shelf actor against it."""
    pairs = []
    for entry in manifest['originals'] + manifest.get('reference_pivots', []):   # batched nodes: never used
        if any(entry['name'] == s['name'] for s in manifest['shelf_objects']):
            continue
        try:
            _, comp = resolve_unique(u, actors, entry)
        except RuntimeError:
            if entry in manifest['originals']:
                raise
            continue
        loc = comp.get_world_location()
        pairs.append((tuple(entry['pivot_runtime_m']), (loc.x, loc.y, loc.z)))
    transform = infer_import_transform(pairs)
    shelf = []
    for entry in manifest['shelf_objects']:
        _, comp = resolve_unique(u, actors, entry)
        loc = comp.get_world_location()
        expected = convert_position(tuple(entry['pivot_runtime_m']), transform)
        err = max(abs(a - b) for a, b in zip((loc.x, loc.y, loc.z), expected))
        if err > SHELF_TOL_CM:
            raise RuntimeError(f'Shelf actor {entry["name"]} is {err:.2f} cm from the Blender base; refuse')
        shelf.append({'name': entry['name'], 'error_cm': round(err, 3)})
    return transform, shelf


def hide_originals(u, actors, manifest, hide=True, previous=None):
    rows = []
    for entry in manifest['originals']:
        actor, _ = resolve_unique(u, actors, entry)
        comps = actor.get_components_by_class(u.StaticMeshComponent)
        state = (previous or {}).get(entry['name'])
        rows.append({'name': entry['name'], 'actor': actor.get_path_name(),
                     'hidden_in_game': bool(actor.get_editor_property('hidden')),
                     'visible': [bool(c.get_editor_property('visible')) for c in comps]})
        if hide:
            actor.set_actor_hidden_in_game(True)
            for c in comps:
                c.set_visibility(False, False)
        else:
            actor.set_actor_hidden_in_game(bool(state['hidden_in_game']) if state else False)
            for i, c in enumerate(comps):
                c.set_visibility(bool(state['visible'][i]) if state and i < len(state['visible']) else True, False)
    return rows


def owned_actors(u, actors):
    return [a for a in actors if any(str(t) == ACTOR_TAG for t in a.get_editor_property('tags'))
            or a.get_actor_label().startswith(LABEL_PREFIX)]


def restore(u, level, actor_sub, project_dir, manifest):
    receipt_path = Path(project_dir) / RECEIPT
    previous = None
    if receipt_path.is_file():
        previous = {r['name']: r for r in json.loads(receipt_path.read_text()).get('originals_before', [])}
    actors = list(actor_sub.get_all_level_actors())
    for actor in owned_actors(u, actors):
        actor_sub.destroy_actor(actor)
    actors = list(actor_sub.get_all_level_actors())
    hide_originals(u, actors, manifest, hide=False, previous=previous)
    if u.EditorAssetLibrary.does_directory_exist(DESTINATION):
        u.EditorAssetLibrary.delete_directory(DESTINATION)
    if not level.save_current_level():
        raise RuntimeError('Map failed to save after restore')
    if receipt_path.is_file():
        receipt_path.rename(receipt_path.with_suffix('.restored.json'))
    u.log('SUB01_REAL_SHELF_BOOKS_RESTORED')
    return {'restored': True}


def apply(u, level, actor_sub, project_dir, report, manifest, glb, digest):
    receipt_path = Path(project_dir) / RECEIPT
    actors = list(actor_sub.get_all_level_actors())
    owned = owned_actors(u, actors)
    if owned:
        prior = json.loads(receipt_path.read_text()) if receipt_path.is_file() else {}
        if prior.get('source_sha256') == digest and len(owned) == len(report['built']):
            hide_originals(u, actors, manifest, hide=True)           # idempotent: re-assert hidden
            u.log('SUB01_REAL_SHELF_BOOKS_ALREADY_APPLIED ' + digest)
            return {'already_applied': True, 'source_sha256': digest}
        raise RuntimeError('Different real-books version present; run with --restore first')
    transform, shelf = import_transform(u, actors, manifest)
    before = fingerprint(u, actors)
    originals_before = [{'name': e['name'], **{k: v for k, v in r.items() if k != 'name'}}
                        for e, r in zip(manifest['originals'], _states(u, actors, manifest))]
    destination = DESTINATION + '/V_' + digest[:12]
    manager = u.InterchangeManager.get_interchange_manager_scripted()
    params = u.ImportAssetParameters()
    params.set_editor_property('is_automated', True)
    data = manager.create_source_data(str(glb))
    if not manager.can_translate_source_data(data, True):
        raise RuntimeError('glTF scene translator unavailable')
    if not manager.import_scene(destination, data, params):
        raise RuntimeError('Real-books import failed; map not saved')
    manager.wait_until_all_tasks_done(False)
    current = list(actor_sub.get_all_level_actors())
    added = [a for a in current if a.get_path_name() not in before]

    def rollback(reason):
        for a in added:
            actor_sub.destroy_actor(a)
        if u.EditorAssetLibrary.does_directory_exist(destination):
            u.EditorAssetLibrary.delete_directory(destination)
        raise RuntimeError(reason + '; import rolled back, map not saved')
    expected = {canonical(b['id']): b for b in report['built']}
    placed, seen = [], set()
    for actor in added:
        comps = [c for c in actor.get_components_by_class(u.StaticMeshComponent) if c.get_editor_property('static_mesh')]
        key = canonical(actor.get_actor_label())
        if not comps:
            actor.tags = list(actor.tags) + [ACTOR_TAG]          # scene root from the importer: owned, mesh-less
            actor.set_folder_path(FOLDER)
            continue
        if key not in expected or key in seen:
            rollback(f'Unexpected imported actor {actor.get_actor_label()}')
        seen.add(key)
        book = expected[key]
        for c in comps:
            if not c.get_editor_property('static_mesh').get_path_name().startswith(destination + '/'):
                rollback('Import reused an unowned mesh')
        loc = comps[0].get_world_location()
        want = convert_position(tuple(book['pivot_runtime_m']), transform)
        err = max(abs(a - b) for a, b in zip((loc.x, loc.y, loc.z), want))
        s = actor.get_actor_scale3d()
        if err > PLACE_TOL_CM or max(abs(s.x - s.y), abs(s.y - s.z)) > 1e-4:
            rollback(f'{book["id"]} lands {err:.2f} cm from its exported pivot or has non-uniform scale')
        actor.set_actor_label(book['id'])
        actor.tags = list(actor.tags) + [ACTOR_TAG]
        actor.set_folder_path(FOLDER)
        for c in comps:
            c.set_mobility(u.ComponentMobility.STATIC)
            c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
        placed.append({'id': book['id'], 'error_cm': round(err, 3)})
    if len(placed) != len(report['built']):
        rollback(f'Imported {len(placed)} of {len(report["built"])} books')
    textures = [(a.asset_name, u.EditorAssetLibrary.load_asset(a.package_name))
                for a in u.AssetRegistryHelpers.get_asset_registry().get_assets_by_path(destination, recursive=True)
                if str(a.asset_class_path.asset_name) == 'Texture2D']
    try:
        texture_rows = check_textures([(str(n), t) for n, t in textures], report['additive_glb'].get('texture_roles', {}))
    except RuntimeError as error:
        rollback(str(error))
    if not textures:
        rollback('No book textures were imported')
    hide_originals(u, current, manifest, hide=True)
    retained = [a for a in actor_sub.get_all_level_actors() if a.get_path_name() in before]
    if fingerprint(u, retained) != before:
        hide_originals(u, current, manifest, hide=False, previous={o['name']: o for o in originals_before})
        rollback('Import changed an existing actor (transform/mesh/material/collision)')
    u.EditorAssetLibrary.save_directory(destination, only_if_is_dirty=False, recursive=True)
    if not level.save_current_level():
        raise RuntimeError('Map failed to save after the real-books import')
    result = {'schema': 'sub01.real-shelf-books-import.v1', 'source_sha256': digest, 'level': LEVEL,
              'destination': destination, 'shelf_verified': shelf, 'placed': placed,
              'textures': texture_rows, 'originals_before': originals_before,
              'originals_hidden': len(manifest['originals']), 'original_collision_changed': False,
              'original_actors_verified_unchanged': len(before), 'visually_verified': False}
    receipt_path.write_text(json.dumps(result, indent=2) + '\n')
    u.log('SUB01_REAL_SHELF_BOOKS_IMPORTED ' + json.dumps({'placed': len(placed), 'sha256': digest}))
    return result


def _states(u, actors, manifest):
    rows = []
    for entry in manifest['originals']:
        actor, _ = resolve_unique(u, actors, entry)
        rows.append({'actor': actor.get_path_name(), 'hidden_in_game': bool(actor.get_editor_property('hidden')),
                     'visible': [bool(c.get_editor_property('visible'))
                                 for c in actor.get_components_by_class(u.StaticMeshComponent)]})
    return rows


def run(argv=None):
    import unreal as u
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='/workspace/sub01-home-private/out/real-books')
    ap.add_argument('--restore', action='store_true')
    ap.add_argument('--excision-applied', action='store_true',
                    help='root already excised the batched book triangles (manifest `excisions`); those nodes stay untouched here')
    args, _ = ap.parse_known_args(sys.argv[1:] if argv is None else argv)
    root = Path(args.root)
    manifest = json.loads((root / 'original-hide-manifest.json').read_text())
    level = u.get_editor_subsystem(u.LevelEditorSubsystem)
    actor_sub = u.get_editor_subsystem(u.EditorActorSubsystem)
    if not level.load_level(LEVEL):
        raise RuntimeError('Existing private native map is unavailable')
    project_dir = u.Paths.project_dir()
    if args.restore:
        return restore(u, level, actor_sub, project_dir, manifest)
    report = json.loads((root / 'real-shelf-books.json').read_text())
    glb = root / 'real-shelf-books.glb'
    digest = validate_receipt(report, manifest, glb, args.excision_applied)
    return apply(u, level, actor_sub, project_dir, report, manifest, glb, digest)


if __name__ == '__main__':
    run()
