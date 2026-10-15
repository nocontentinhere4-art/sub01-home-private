"""Next-window Runpod proof/export for the complete authentic native kitchen.

Wraps the reviewed sink/feet/eight-door proof; adds retained-house triangles,
every pair of independently positioned doors and exact exported part metadata.
No Blender is imported by the lightweight validation/manifest functions.
"""
import argparse
import hashlib
import itertools
import json
import math
import re
import struct
import sys
from pathlib import Path

import prepare_real_kitchen_bundle as base
from home_asset_audit import read_gltf
from structural_rail_source_patch import accessor, world_matrices, transformed

SCHEMA = 'sub01.real-kitchen-native-bundle.v1'
OLD = {63: ('Lower_cabinet_carcass', 47), 178: ('Cabinet_carcass', 135)}


def bounds(points):
    return [[f(p[k] for p in points) for k in range(3)] for f in (min, max)]


def intersects(a, b):
    return all(a[0][k] <= b[1][k] and b[0][k] <= a[1][k] for k in range(3))


def allowed_contact(points, source_points, node, contacts):
    """Only actual floor top / countertop underside planar contacts, 1µm float bound."""
    plane = contacts['floor_m'] if node == 0 else contacts['counter_underside_m'] if node == 65 else None
    return plane is not None and all(abs(p[1]-plane) <= 1e-6 for p in points+source_points)


def protected_triangles(home, region):
    doc, binary = read_gltf(home)
    if base.sha(home) != base.HOME_SHA:
        raise ValueError('Exact original home identity unavailable')
    matrices = world_matrices(doc)
    rows = []
    for ni, node in enumerate(doc['nodes']):
        if 'mesh' not in node:
            continue
        if ni in OLD:
            if (node.get('name'), node['mesh']) != OLD[ni]:
                raise ValueError('Exact retired cabinet identity differs')
            continue
        for pi, primitive in enumerate(doc['meshes'][node['mesh']]['primitives']):
            if primitive.get('mode', 4) != 4:
                raise ValueError('Non-triangle protected source')
            meta = doc['accessors'][primitive['attributes']['POSITION']]
            corners = [transformed(matrices[ni], c) for c in itertools.product(*zip(meta['min'], meta['max']))]
            if not intersects(bounds(corners), region):
                continue
            verts = [transformed(matrices[ni], p) for p in accessor(doc, binary, primitive['attributes']['POSITION'])]
            ids = [i[0] for i in accessor(doc, binary, primitive['indices'])]
            for j in range(0, len(ids), 3):
                triangle = [verts[k] for k in ids[j:j+3]]
                if intersects(bounds(triangle), region):
                    rows.append({'node': ni, 'primitive': pi, 'triangle': j//3, 'points': triangle})
    return rows


def full_collision_proof(bpy, report, home):
    from mathutils.bvhtree import BVHTree
    objects = [o for o in bpy.data.objects if o.type == 'MESH']
    parents = sorted([o for o in bpy.data.objects if o.type == 'EMPTY' and
                      ('hinge_' in o.name or o.name.startswith('Cabinet hinge '))], key=lambda o: o.name)
    if len(parents) != 8:
        raise ValueError('Exactly eight complete hinges required')
    # Covers full retained source and every 88.2° door arc, not only closed cabinetry.
    region = [[-3.95, 0., -4.05], [-.35, 2.6, -2.25]]
    rows = protected_triangles(home, region)
    protected = BVHTree.FromPolygons([(p[0], -p[2], p[1]) for r in rows for p in r['points']],
        [tuple(range(3*i, 3*i+3)) for i in range(len(rows))], all_triangles=True, epsilon=0.)
    issues, contacts, poses = [], [], {}

    def check_home(parts, identity):
        tree, owners = base.source_bvh(bpy, parts)
        allpoints = [(p.x, p.z, -p.y) for o in parts for p in (o.matrix_world @ v.co for v in o.data.vertices)]
        if any(not all(region[0][k] <= p[k] <= region[1][k] for k in range(3)) for p in allpoints):
            raise ValueError('Actual kitchen pose leaves audited protected-house region '+identity)
        polygons = [(o, p) for o in parts for p in o.data.polygons]
        for a, b in tree.overlap(protected):
            obj, poly = polygons[a]
            vertices = [obj.matrix_world @ obj.data.vertices[i].co for i in poly.vertices]
            points = [(p.x, p.z, -p.y) for p in vertices]
            target = rows[b]
            detail = {'object': owners[a], 'pose': identity, 'source_node': target['node'],
                      'source_primitive': target['primitive'], 'source_triangle': target['triangle']}
            if allowed_contact(points, target['points'], target['node'], report['actual_home_contacts']):
                contacts.append(detail)
            elif len(issues) < 32:
                issues.append(detail)
        return tree, bounds([(p.x, p.y, p.z) for o in parts for p in (o.matrix_world @ v.co for v in o.data.vertices)])

    check_home([o for o in objects if '_cabinet_body_' in o.name], 'static')
    try:
        for parent in parents:
            states = []
            for step in range(90):
                parent.rotation_euler.z = -math.pi*.49*step/89
                bpy.context.view_layer.update()
                states.append(check_home([o for o in parent.children if o.type == 'MESH'],
                                         parent.name+':'+str(step)))
            poses[parent.name] = states
            parent.rotation_euler.z = 0
            bpy.context.view_layer.update()
        tests, broad_rejects = 0, 0
        for left, right in itertools.combinations(poses, 2):
            for ai, (a, ab) in enumerate(poses[left]):
                for bi, (b, bb) in enumerate(poses[right]):
                    if not intersects(ab, bb):
                        broad_rejects += 1
                        continue
                    tests += 1
                    hits = a.overlap(b)
                    if hits and len(issues) < 32:
                        issues.append({'left': left, 'right': right, 'left_pose': ai,
                                       'right_pose': bi, 'triangle_pairs': len(hits)})
    finally:
        for parent in parents:
            parent.rotation_euler.z = 0
        bpy.context.view_layer.update()
    return {'ok': not issues, 'issues': issues, 'epsilon_m': 0., 'retained_source_sha256': base.HOME_SHA,
            'retired_source_nodes': [63, 178], 'protected_triangle_count': len(rows),
            'door_home_poses': 720, 'door_pair_bvh_tests': tests,
            'door_pair_aabb_rejects': broad_rejects, 'measured_planar_contacts': contacts,
            'contact_float_bound_m': 1e-6, 'all_poses_inside_audited_region': True, 'native_ready': False}


def make_manifest(output, report):
    """Use actual exported bytes/attributes; prefix nodes without changing BIN bytes."""
    path = output/'real-kitchen.glb'
    doc, binary = read_gltf(path)
    original_digest = base.sha(path)
    prefix = 'SUB01_RealKitchen_'+original_digest[:12]+'_'
    matrices = world_matrices(doc)
    expected = {r['assembly']+'__'+r['source_part'] for r in report['exported_parts']}
    mesh_names = {n.get('name') for n in doc['nodes'] if 'mesh' in n}
    if mesh_names != expected or len(expected) != 152:
        raise ValueError('Actual complete 152-part kitchen export required')
    parts = []
    for index, node in enumerate(doc['nodes']):
        if 'mesh' in node:
            assembly, source_part = node['name'].rsplit('__', 1)
            points, triangles = [], 0
            for primitive in doc['meshes'][node['mesh']]['primitives']:
                points += [transformed(matrices[index], p) for p in accessor(doc, binary, primitive['attributes']['POSITION'])]
                triangles += doc['accessors'][primitive['indices']]['count']//3
            parts.append({'name': prefix+node['name'], 'assembly': assembly, 'source_part': source_part,
                          'bounds_browser_m': bounds(points), 'triangles': triangles})
        node['name'] = prefix+node.get('name', 'node_'+str(index))
    for index, scene in enumerate(doc.get('scenes', [])):
        scene['name'] = prefix+'Scene_'+str(index)
    for index, mesh in enumerate(doc.get('meshes', [])):
        mesh['name'] = prefix+'Mesh_'+str(index)
    raw = json.dumps(doc, separators=(',', ':')).encode()
    raw += b' '*((-len(raw)) % 4)
    packed = struct.pack('<III', 0x46546c67, 2, 12+8+len(raw)+8+len(binary))
    packed += struct.pack('<II', len(raw), 0x4e4f534a)+raw+struct.pack('<II', len(binary), 0x004e4942)+binary
    target = output/'native-kitchen.glb'
    target.write_bytes(packed)
    reread, actual_bin = read_gltf(target)
    if binary != actual_bin:
        raise ValueError('Kitchen unique-name staging changed actual geometry/PBR BIN')
    hinges = []
    for row in report['assemblies']:
        if row['hinge_browser_m'] is None:
            continue
        is_lower = row['name'].startswith('Lower_')
        number = int(row['name'].rsplit('_' if is_lower else ' ', 1)[1])-1
        hinges.append({'index': number+(4 if is_lower else 0), 'assembly': row['name'],
                       'hinge_ue_cm': [100*row['hinge_browser_m'][k] for k in (0, 2, 1)],
                       'parts': [p['name'] for p in parts if p['assembly'] == row['name']]})
    return {'schema': SCHEMA, 'source_sha256': base.HOME_SHA, 'export_sha256': base.sha(target),
            'unprefixed_export_sha256': original_digest, 'prefix': prefix, 'parts': parts,
            'hinges': sorted(hinges, key=lambda r: r['index']), 'source_report': report,
            'full_collision_proof': report['source_collision_checks']['protected_home_and_cross_doors'],
            'hide_only_source_nodes': [63, 178], 'binary_geometry_pbr_unchanged_by_uid': True,
            'native_ready': False}


def validate_manifest(proof):
    if (proof.get('schema') != SCHEMA or proof.get('source_sha256') != base.HOME_SHA
            or not proof.get('binary_geometry_pbr_unchanged_by_uid')
            or proof.get('hide_only_source_nodes') != [63, 178]):
        raise ValueError('Complete actual kitchen native bundle identity required')
    for key in ('export_sha256', 'unprefixed_export_sha256'):
        if not re.fullmatch('[0-9a-f]{64}', proof.get(key, '')):
            raise ValueError('Actual exported kitchen digest required')
    prefix = 'SUB01_RealKitchen_'+proof['unprefixed_export_sha256'][:12]+'_'
    if proof.get('prefix') != prefix:
        raise ValueError('Deterministic owned kitchen UID required')
    report = proof.get('source_report', {})
    source_checks = report.get('source_collision_checks', {})
    if (not report.get('source_export_ready') or report.get('derived_sha256') != proof['unprefixed_export_sha256']
            or not source_checks.get('passed') or not source_checks.get('sink_source_bvh_clear')
            or source_checks.get('epsilon_m') != 0. or len(source_checks.get('doors', [])) != 8
            or any(not d.get('closed_and_sweep_passed') or d.get('tested_poses') != 90 for d in source_checks['doors'])
            or len(report.get('leg_contacts', [])) != 16
            or any(not math.isfinite(v.get('floor_contact_error_m', math.nan))
                   or not 0 <= v['floor_contact_error_m'] <= .0001 for v in report['leg_contacts'])):
        raise ValueError('Actual sink, feet and eight complete source door sweeps required')
    if any(report.get('source', {}).get(k, {}).get('sha256') != v[1] for k, v in base.SOURCES.items()):
        raise ValueError('Authentic three source-model identities required')
    collision = proof.get('full_collision_proof', {})
    if (not collision.get('ok') or collision.get('epsilon_m') != 0.
            or collision.get('retained_source_sha256') != base.HOME_SHA
            or collision.get('retired_source_nodes') != [63, 178]
            or collision.get('protected_triangle_count', 0) < 1
            or not collision.get('all_poses_inside_audited_region')
            or collision.get('door_home_poses') != 720
            or collision.get('door_pair_bvh_tests', -1)+collision.get('door_pair_aabb_rejects', -1) != 28*90*90):
        raise ValueError('Actual protected-home and independent cross-door proof missing')
    parts = proof.get('parts', [])
    hinges = proof.get('hinges', [])
    names = {p['name'] for p in parts}
    if len(parts) != len(names) or len(parts) != 152 or len(hinges) != 8 or [h['index'] for h in hinges] != list(range(8)):
        raise ValueError('Complete 152-part / eight-hinge identities required')
    expected = {}
    for i in range(1, 5):
        expected['Lower_cabinet_body_'+str(i)] = 18
        expected['Upper_cabinet_body_'+str(i)] = 10
        expected['Lower_cabinet_hinge_'+str(i)] = 5
        expected['Cabinet hinge '+str(i)] = 5
    for assembly, count in expected.items():
        rows = [p for p in parts if p['assembly'] == assembly]
        if {p['source_part'] for p in rows} != {'mesh-'+str(i) for i in range(count)} or len(rows) != count:
            raise ValueError('Complete authored kitchen assembly required '+assembly)
    for part in parts:
        if (part['name'] != prefix+part['assembly']+'__'+part['source_part']
                or not isinstance(part.get('triangles'), int) or part['triangles'] <= 0
                or len(part.get('bounds_browser_m', [])) != 2
                or any(len(side) != 3 or not all(math.isfinite(v) for v in side) for side in part['bounds_browser_m'])
                or any(a > b for a, b in zip(*part['bounds_browser_m']))):
            raise ValueError('Actual finite exported native part geometry required')
    for hinge in hinges:
        own = [p for p in parts if p['assembly'] == hinge['assembly']]
        if ({p['source_part'] for p in own} != {'mesh-'+str(i) for i in range(5)}
                or set(hinge['parts']) != {p['name'] for p in own}
                or not all(math.isfinite(v) for v in hinge['hinge_ue_cm'])):
            raise ValueError('Exact five authored parts per moving hinge required')
        i = hinge['index']
        center = base.UPPER_CENTERS[i] if i < 4 else base.LOWER_CENTERS[i-4]
        expected_hinge = [100*(center-(.771/2 if i < 4 else .325)), -353.1 if i < 4 else -319.2, 205. if i < 4 else 44.]
        if max(abs(a-b) for a, b in zip(hinge['hinge_ue_cm'], expected_hinge)) > 1e-7:
            raise ValueError('Original authored cabinet hinge world position changed')
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
    import bpy
    previous = base.verify_source_collisions

    def verify(actual_bpy, report):
        result = previous(actual_bpy, report)
        full = full_collision_proof(actual_bpy, report, args.home)
        result['protected_home_and_cross_doors'] = full
        result['passed'] = result['passed'] and full['ok']
        return result
    base.verify_source_collisions = verify
    report = base.plan(base.inventory(args.root), base.home_contacts(args.home))
    try:
        base.export_blender(args.root, args.output, report)
        proof = validate_manifest(make_manifest(args.output, report))
        (args.output/'native-kitchen.json').write_text(json.dumps(proof, indent=2)+'\n')
    finally:
        base.verify_source_collisions = previous


if __name__ == '__main__':
    main()
