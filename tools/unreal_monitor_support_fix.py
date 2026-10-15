"""Guarded warm-Editor rigid support correction for source955 monitor73/74/75.

No imports, geometry/material edits, level loads or runtime activation. The
completed genuine office and exact live-screen binding update are prerequisites.
"""
import hashlib
import json
import math
import shutil
import time
from pathlib import Path

from home_asset_audit import read_gltf
from structural_rail_source_patch import accessor, world_matrices, transformed
from unreal_import_real_kitchen import same_triangles, snapshot

HOME_SHA = '9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
DESK_SHA = '99bdf3fd42eea5fc4cb2fadd52c8cae18c4459a94000b85f7df4c515234ba43d'
LEVEL = '/Game/Sub01Home/ActualHome'
NODES = {73: (56, 14, 300), 74: (57, 17, 300), 75: (58, 18, 2)}
PREFIX = '/Game/Sub01Home/ImportedScene/full-home/'


def triangles(doc, binary, node):
    matrix = world_matrices(doc)[node]
    result = []
    for p in doc['meshes'][doc['nodes'][node]['mesh']]['primitives']:
        pts = [transformed(matrix, v) for v in accessor(doc, binary, p['attributes']['POSITION'])]
        pts = [[v[k]*100 for k in (0, 2, 1)] for v in pts]
        ids = [v[0] for v in accessor(doc, binary, p['indices'])]
        result += [[pts[k] for k in ids[i:i+3]] for i in range(0, len(ids), 3)]
    return result


def native_triangles(u, component):
    mesh = component.get_editor_property('static_mesh')
    world = component.get_world_transform()
    result = []
    for section in range(mesh.get_num_sections(0)):
        vertices, ids, *_ = u.ProceduralMeshLibrary.get_section_from_static_mesh(mesh, 0, section)
        points = [world.transform_location(p) for p in vertices]
        pts = [[float(p.x), float(p.y), float(p.z)] for p in points]
        if len(ids) % 3:
            raise RuntimeError('Native monitor/worktop has partial triangles')
        result += [[pts[k] for k in ids[i:i+3]] for i in range(0, len(ids), 3)]
    return result


def area(poly):
    return abs(sum(a[0]*b[1]-a[1]*b[0] for a, b in zip(poly, poly[1:]+poly[:1])))/2


def intersect(subject, clip):
    """Convex triangle clipping; actual projected support area, not ray samples."""
    orientation = sum(a[0]*b[1]-a[1]*b[0] for a, b in zip(clip, clip[1:]+clip[:1]))
    sign = 1 if orientation >= 0 else -1
    result = [list(p[:2]) for p in subject]
    for a, b in zip(clip, clip[1:]+clip[:1]):
        def side(p):
            return sign*((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]))
        previous = result
        result = []
        if not previous:
            break
        for p, q in zip(previous, previous[1:]+previous[:1]):
            sp, sq = side(p), side(q)
            if sp >= 0:
                result.append(p)
            if (sp >= 0) != (sq >= 0):
                t = sp/(sp-sq)
                result.append([p[k]+t*(q[k]-p[k]) for k in range(2)])
    return result


def support(stand, top):
    """Full planar foot triangle coverage by actual planar walnut top triangles."""
    if not stand or not top or any(not math.isfinite(v) for ts in (stand, top) for t in ts for p in t for v in p):
        raise ValueError('Finite complete stand/top geometry required')
    low = min(p[2] for t in stand for p in t)
    high = max(p[2] for t in top for p in t)
    if abs(low-82) > .02 or abs(high-84.5) > .005:
        raise ValueError('Actual source stand82 / genuine LINEA top84.5 required')
    feet = [t for t in stand if all(abs(p[2]-low) < .0001 for p in t) and area(t) > 1e-9]
    boards = [t for t in top if all(abs(p[2]-high) < .0001 for p in t) and area(t) > 1e-9]
    if not feet or not boards:
        raise ValueError('Actual flat support faces absent')
    total = 0.
    for foot in feet:
        want = area(foot)
        covered = sum(area(intersect(foot, board)) for board in boards)
        if abs(covered-want) > max(1e-5, want*1e-7):
            raise ValueError('Full genuine walnut coverage of monitor foot failed')
        total += want
    return {'native_stand_bottom_cm': low, 'native_desk_top_cm': high,
            'delta_z_cm': high-low, 'flat_foot_triangles': len(feet),
            'flat_top_triangles': len(boards), 'supported_foot_area_cm2': total,
            'full_flat_foot_area_covered': True}


def _only(rows, label):
    if len(rows) != 1:
        raise RuntimeError('Exact unique native identity unavailable: '+label)
    return rows[0]


def preflight(root, u):
    root = Path(root)
    office = json.loads((root/'office-bundle.json').read_text())
    saved = json.loads((root/'native-office-bundle.json').read_text())
    if office.get('schema') != 'sub01.real-office-bundle.v1' or not office.get('source_triangle_collision_proof', {}).get('ok'):
        raise RuntimeError('Passed frozen genuine office source proof required')
    # Native receipt is a prerequisite, never manufacture it from source success.
    if saved.get('schema') != 'sub01.real-office-native-import.v1' or saved.get('source_bundle') != office:
        raise RuntimeError('Completed genuine native office receipt required')
    source = root/'desk.glb'
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if office['desk']['source_sha256'] != DESK_SHA or office['desk']['output_sha256'] != digest:
        raise RuntimeError('Frozen complete genuine desk bytes differ')
    project = Path(u.Paths.project_dir())
    home = project/'SourceAssets/full-home.glb'
    if hashlib.sha256(home.read_bytes()).hexdigest() != HOME_SHA:
        raise RuntimeError('Exact original source955 required')
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if not world or world.get_path_name().split('.', 1)[0] != LEVEL:
        raise RuntimeError('Sole warm ActualHome Editor required')
    actors = list(u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors())
    for retired in (181, 182):
        old = _only([a for a in actors if a.get_name() == f'full-home_node_{retired}'], 'retired desk '+str(retired))
        oldcs = old.get_components_by_class(u.StaticMeshComponent)
        if not old.get_editor_property('hidden') or not oldcs or any(c.get_collision_enabled() != u.CollisionEnabled.NO_COLLISION for c in oldcs):
            raise RuntimeError('Original generated desk must already be retired by genuine office transaction')
    doc, binary = read_gltf(home)
    rows = []
    for node, (mesh_index, material_index, count) in NODES.items():
        actor = _only([a for a in actors if a.get_name() == f'full-home_node_{node}'], str(node))
        cs = actor.get_components_by_class(u.StaticMeshComponent)
        c = _only(cs, 'component '+str(node))
        mesh = c.get_editor_property('static_mesh')
        if (not mesh or mesh.get_path_name() != PREFIX+f'StaticMeshes/Mesh_{mesh_index}.Mesh_{mesh_index}'
                or actor.get_attach_parent_actor() or c != actor.get_root_component()
                or actor.get_editor_property('hidden') or not c.get_editor_property('visible')):
            raise RuntimeError('Exact independent visible source monitor assembly required')
        paths = [m.get_path_name() if m else None for m in c.get_materials()]
        expected = PREFIX+f'Materials/Material_{material_index}.Material_{material_index}'
        allowed = [expected]
        if node == 75:
            allowed += ['/Game/Sub01Home/Devices/M_Sub01LivePC.M_Sub01LivePC']
        if len(paths) != 1 or paths[0] not in allowed:
            raise RuntimeError('Unreviewed monitor material binding '+str(node))
        wanted, actual = triangles(doc, binary, node), native_triangles(u, c)
        if len(wanted) != count or not same_triangles(wanted, actual):
            raise RuntimeError('Full native monitor source geometry differs '+str(node))
        rows.append((node, actor, c, actual))
    top_actor = _only([a for a in actors if a.get_actor_label() == 'SUB01_RealLinea140_99bdf3fd_Node044'], 'genuine worktop44')
    top_component = _only(top_actor.get_components_by_class(u.StaticMeshComponent), 'worktop44 component')
    if top_actor.get_editor_property('hidden') or not top_component.get_editor_property('visible'):
        raise RuntimeError('Genuine desk worktop inactive')
    dest = '/Game/Sub01Home/RealLinea140/V_'+digest[:12]+'/'
    if not top_component.get_editor_property('static_mesh').get_path_name().startswith(dest):
        raise RuntimeError('Genuine worktop exact owned mesh version required')
    placed, data = read_gltf(source)
    node = _only([i for i, n in enumerate(placed['nodes']) if n.get('name') == top_actor.get_actor_label()], 'source worktop44')
    top = native_triangles(u, top_component)
    if not same_triangles(triangles(placed, data, node), top):
        raise RuntimeError('Full genuine native walnut triangles differ')
    proof = support(rows[1][3], top)
    return actors, rows, proof, project


def run(root='/workspace/sub01-home-private/out/real-office-bundle', dry_run=True, u=None):
    if u is None:
        import unreal as u
    root = Path(root)
    actors, rows, proof, project = preflight(root, u)
    result = {'schema': 'sub01.monitor-support-native-fix.v1', 'source_sha256': HOME_SHA,
              'source_nodes': list(NODES), 'support': proof, 'delta_ue_cm': [0, 0, proof['delta_z_cm']],
              'screen_expected_center_ue_cm': [200, -327.6, 118.5], 'native_visual_verified': False,
              'native_pc_input_verified': False, 'runtime_binding_expectation_update_required': True}
    if dry_run:
        return dict(result, dry_run=True, mutations=0)
    backup = project/'Saved/PrivateMapBackups'/('monitor-support-'+str(time.time_ns()))
    backup.mkdir(parents=True)
    shutil.copy2(project/'Content/Sub01Home/ActualHome.umap', backup/'ActualHome.umap')
    for directory in ('__ExternalActors__', '__ExternalObjects__'):
        folder = project/'Content'/directory/'Sub01Home/ActualHome'
        if folder.exists():
            shutil.copytree(folder, backup/directory)
    before = snapshot(u, actors)
    states = [(a, a.get_actor_transform(), c, c.get_world_transform(), list(c.get_materials())) for _, a, c, _ in rows]
    protected = [a for a in actors if all(a != row[1] for row in rows)]
    wanted_protected = {a.get_path_name(): before[a.get_path_name()] for a in protected}
    save_attempted = False
    try:
        for _, a, _, _ in rows:
            p = a.get_actor_location()
            if not a.set_actor_location(u.Vector(p.x, p.y, p.z+proof['delta_z_cm']), False, False):
                raise RuntimeError('Rigid monitor actor move failed')
        if snapshot(u, protected) != wanted_protected:
            raise RuntimeError('Monitor support correction changed protected actors')
        for node, a, c, original in rows:
            moved = native_triangles(u, c)
            expected = [[[p[0], p[1], p[2]+proof['delta_z_cm']] for p in t] for t in original]
            if not same_triangles(expected, moved, .001):
                raise RuntimeError('Whole monitor rigid move differs '+str(node))
            old = before[a.get_path_name()]
            now = snapshot(u, [a])[a.get_path_name()]
            # Only actor/component world translation may change; all mesh,
            # materials, tags, visibility, collision, rotation/scale stay exact.
            for item in [now['transform']]+[c['transform'] for c in now['components']]:
                item['translation'][2] -= proof['delta_z_cm']
            if now != old:
                # Floating arithmetic is tolerated only for translated Z.
                for x, y in zip([now['transform']]+[c['transform'] for c in now['components']],
                                [old['transform']]+[c['transform'] for c in old['components']]):
                    if abs(x['translation'][2]-y['translation'][2]) < 1e-5:
                        x['translation'][2] = y['translation'][2]
                if now != old:
                    raise RuntimeError('Monitor mesh/material/transform invariant changed')
        new_low = min(p[2] for t in native_triangles(u, rows[1][2]) for p in t)
        if abs(new_low-proof['native_desk_top_cm']) > .001:
            raise RuntimeError('Actual native monitor foot is not on actual walnut top')
        result['map_backup'] = str(backup)
        result['preserved_original_actors'] = len(protected)
        pending = root/'monitor-support.pending.json'
        pending.write_text(json.dumps(result, indent=2)+'\n')
        save_attempted = True
        if not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():
            raise RuntimeError('Monitor support level save failed')
        pending.replace(root/'monitor-support-native.json')
        return result
    except Exception:
        for a, transform, c, world, materials in states:
            a.set_actor_transform(transform, False, False)
            c.set_world_transform(world, False, False)
            for slot, material in enumerate(materials):
                c.set_material(slot, material)
        if snapshot(u, actors) != before:
            raise RuntimeError('Monitor rollback incomplete; preserve backup '+str(backup))
        if save_attempted and not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():
            raise RuntimeError('Monitor rollback save failed; restore backup '+str(backup))
        raise
