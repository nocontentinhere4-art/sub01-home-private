"""Remove foreign digit weights only on independently identified isolated skin branches.

Run on the private server. Original editable rig stays untouched. No pose changes.
"""
import bpy, hashlib, json, math, sys
from pathlib import Path

source, output = map(Path, sys.argv[sys.argv.index('--') + 1:])
output.mkdir(parents=True, exist_ok=False)
bpy.ops.wm.open_mainfile(filepath=str(source))
rig = bpy.data.objects['CC0AnatomicalHandRig']
digits = ('Thumb', 'Index', 'Middle', 'Ring', 'Pinky')
report = {'source_blend_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
          'geometry_changed': False, 'rest_changed': False, 'native_accepted': False,
          'cut_plane_world_z_m': .79, 'transition_m': .008, 'sides': {}}
for side in ('Left', 'Right'):
    obj = bpy.data.objects['CC0Adult_' + side + '_ForearmHand_SOURCE_UNRIGGED']
    coords = [tuple(v.co) for v in obj.data.vertices]
    points = [obj.matrix_world @ v.co for v in obj.data.vertices]
    tips = {d: rig.matrix_world @ rig.data.bones['mixamorig:' + side + 'Hand' + d + '4'].head_local for d in digits}
    attempts = []
    resolved = False
    for cut in [.79 - .001 * k for k in range(91)]:
        active = {i for i, p in enumerate(points) if p.z < cut}
        adjacency = {i: set() for i in active}
        for e in obj.data.edges:
            a, b = e.vertices
            if a in active and b in active:
                adjacency[a].add(b); adjacency[b].add(a)
        components = []
        while active:
            first = active.pop(); stack = [first]; found = [first]
            while stack:
                for j in adjacency[stack.pop()]:
                    if j in active:
                        active.remove(j); stack.append(j); found.append(j)
            if len(found) >= 40:
                components.append(found)
        identities = []
        for component in components:
            ds = sorted((min((points[i] - tip).length for i in component), d) for d, tip in tips.items())
            identities.append({'digit': ds[0][1], 'distance': ds[0][0], 'margin': ds[1][0] - ds[0][0]})
        attempts.append({'cut': cut, 'component_sizes': [len(c) for c in components], 'identities': identities})
        if len(components) == 4 and {x['digit'] for x in identities} == set(digits[1:]) and all(x['distance'] < .014 and x['margin'] > .006 for x in identities):
            resolved = True; break
    if not resolved:
        (output / ('unresolved-' + side + '.json')).write_text(json.dumps(attempts, indent=2))
    assert resolved, (side, 'No unambiguous four anatomical branches; diagnostic saved')
    branches = []; labels = set()
    for component in components:
        distances = sorted((min((points[i] - tip).length for i in component), d) for d, tip in tips.items())
        distance, digit = distances[0]
        assert digit != 'Thumb' and digit not in labels and distance < .014, (side, distances)
        assert distances[1][0] - distance > .006, (side, distances)
        labels.add(digit)
        own = {'mixamorig:' + side + 'Hand' + digit + str(n) for n in (1, 2, 3)}
        foreign = {'mixamorig:' + side + 'Hand' + d + str(n) for d in digits if d != digit for n in (1, 2, 3)}
        changed = 0; removed = 0.; max_before = 0.; max_after = 0.
        for index in component:
            vertex = obj.data.vertices[index]
            weights = {obj.vertex_groups[g.group].name: g.weight for g in vertex.groups if g.weight > 0}
            before = sum(w for name, w in weights.items() if name in foreign)
            max_before = max(max_before, before)
            # Smooth fade at actual connected branch's palm cut. Distal anatomy is unambiguous.
            t = min(1., max(0., (cut - points[index].z) / .008))
            fade = t * t * (3. - 2. * t)
            if before > 1e-8 and fade > 0:
                assert sum(w for name, w in weights.items() if name in own) > .15, (side, digit, index, weights)
                updated = {name: w * (1. - fade) if name in foreign else w for name, w in weights.items()}
                total = sum(updated.values()); assert total > .1
                for name, w in updated.items():
                    obj.vertex_groups[name].add([index], w / total, 'REPLACE')
                removed += before - sum(w / total for name, w in updated.items() if name in foreign)
                changed += 1
            after = sum(g.weight for g in vertex.groups if obj.vertex_groups[g.group].name in foreign)
            max_after = max(max_after, after)
        branches.append({'digit_verified_by_actual_endpoint': digit, 'vertices': len(component),
                         'endpoint_distances_m': distances, 'changed_vertices': changed,
                         'foreign_weight_sum_removed': removed, 'max_foreign_before': max_before,
                         'max_foreign_after_including_transition': max_after})
    assert labels == set(digits[1:])
    assert coords == [tuple(v.co) for v in obj.data.vertices]
    errors = [abs(sum(g.weight for g in v.groups) - 1.) for v in obj.data.vertices]
    assert max(errors) < 1e-6
    report['sides'][side] = {'cut_plane_search': attempts, 'cut_plane_world_z_m': cut, 'branches': branches, 'max_weight_sum_error': max(errors),
                             'vertices': len(coords), 'coordinates_exactly_unchanged': True}
bpy.ops.wm.save_as_mainfile(filepath=str(output / 'official-adult-hand-pair-rig.blend'))
bpy.ops.object.select_all(action='DESELECT')
rig.select_set(True)
for side in ('Left', 'Right'):
    bpy.data.objects['CC0Adult_' + side + '_ForearmHand_SOURCE_UNRIGGED'].select_set(True)
bpy.context.view_layer.objects.active = rig
target = output / 'official-adult-hand-pair-rig.glb'
bpy.ops.export_scene.gltf(filepath=str(target), export_format='GLB', use_selection=True,
                          export_animations=False, export_skins=True, export_yup=True)
report['output_glb_sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
(output / 'weight-cleanup-report.json').write_text(json.dumps(report, indent=2) + '\n')
print('ACTUAL_ANATOMICAL_BRANCH_WEIGHT_CLEANUP', json.dumps(report), flush=True)
