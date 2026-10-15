"""Independent original sculpt-boundary identity check of the actual saved rig."""
import bpy, collections, hashlib, json, sys
from pathlib import Path
from mathutils import Vector

rig_path, output = map(Path, sys.argv[sys.argv.index('--') + 1:])
source = Path('/workspace/sub01-home-private/human-base-hands-r1/source/human-base-meshes-bundle-v1.4.1/human_base_meshes_bundle.blend')
bpy.ops.wm.open_mainfile(filepath=str(rig_path))
rig = bpy.data.objects['CC0AnatomicalHandRig']
with bpy.data.libraries.load(str(source), link=False) as (src, dst):
    dst.objects = ['GEO-body_male_realistic']
body = dst.objects[0]
bpy.context.scene.collection.objects.link(body)
bpy.context.view_layer.update()
groups = collections.defaultdict(set)
attr = body.data.attributes['.sculpt_face_set']
assert attr.domain == 'FACE' and attr.data_type == 'INT'
for face in body.data.polygons:
    groups[attr.data[face.index].value].update(face.vertices)
mapping = {'Left': (9, {'Thumb': 80, 'Index': 76, 'Middle': 72, 'Ring': 68, 'Pinky': 64}),
           'Right': (10, {'Thumb': 84, 'Index': 88, 'Middle': 92, 'Ring': 96, 'Pinky': 100})}
records = []
for side, (palm, digits) in mapping.items():
    endpoint_positions = []
    for digit, base in digits.items():
        for index, pair in enumerate(((palm, base), (base, base + 1), (base + 1, base + 2)), 1):
            ids = groups[pair[0]] & groups[pair[1]]
            assert len(ids) >= 3
            center = sum((body.matrix_world @ body.data.vertices[i].co for i in ids), Vector()) / len(ids)
            bone = rig.data.bones['mixamorig:' + side + 'Hand' + digit + str(index)]
            actual = rig.matrix_world @ bone.head_local
            # Actual shared sculpt ring, plus <=4mm skin medial projection and
            # <=3.5mm bounded internal fit in each axis. Do not use donor bones.
            distance = (center - actual).length
            assert distance < .012, (side, digit, index, distance)
            records.append({'side': side, 'digit': digit, 'joint': index,
                            'original_face_sets': pair, 'shared_vertices': sorted(ids),
                            'actual_joint_world': list(actual), 'boundary_center_world': list(center),
                            'distance_m': distance})
        end = rig.matrix_world @ rig.data.bones['mixamorig:' + side + 'Hand' + digit + '4'].head_local
        endpoint_positions.append((digit, end))
    separations = [(a, b, (x - y).length) for i, (a, x) in enumerate(endpoint_positions) for b, y in endpoint_positions[i+1:]]
    assert min(x[2] for x in separations) > .014, (side, separations)
output.write_text(json.dumps({'schema': 'sub01.independent-authored-joint-identity.v1',
    'rig_blend_sha256': hashlib.sha256(rig_path.read_bytes()).hexdigest(),
    'original_source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'original_sculpt_boundaries_recomputed': True, 'joints': records,
    'independent_digit_identity_pass': True, 'motion_contact_accepted': False}, indent=2) + '\n')
print('INDEPENDENT_AUTHORED_DIGIT_IDENTITY_PASS', len(records), flush=True)
