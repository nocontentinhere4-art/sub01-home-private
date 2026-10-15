"""Export the user's original, hash-pinned phone capture on Runpod only.

The old owner retarget is deliberately not used as the finger-motion source.
"""
import hashlib
import json
import sys
from pathlib import Path

import bpy

source, output = map(Path, sys.argv[sys.argv.index('--') + 1:])
expected = '458a0d3e73da67c873332fc67761173e7437b37f32de6e7fffaec356537aedb4'
assert hashlib.sha256(source.read_bytes()).hexdigest() == expected
assert str(output).startswith('/workspace/sub01-home-private/')
output.mkdir(exist_ok=False, parents=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.fps = 30
bpy.ops.import_scene.fbx(filepath=str(source), use_anim=True)
arms = [obj for obj in scene.objects if obj.type == 'ARMATURE']
assert len(arms) == 1 and not [obj for obj in scene.objects if obj.type == 'MESH']
arm = arms[0]
assert len(bpy.data.actions) == 1
action = bpy.data.actions[0]
arm.animation_data_create()
arm.animation_data.action = action
for track in arm.animation_data.nla_tracks:
    track.mute = True
start, end = action.frame_range
scene.frame_start, scene.frame_end = int(start), int(end)
records = []
for frame in (start, (start + end) / 2, end):
    scene.frame_set(int(frame), subframe=frame-int(frame))
    bpy.context.view_layer.update()
    records.append({'frame': frame, 'bones': {
        bone.name: {'head_world_m': list(arm.matrix_world @ bone.head),
                    'tail_world_m': list(arm.matrix_world @ bone.tail)}
        for bone in arm.pose.bones if 'Hand' in bone.name}})
scene.frame_set(int(start))
path = output / 'original-phone-skeleton.glb'
bpy.ops.export_scene.gltf(
    filepath=str(path), export_format='GLB', export_animations=True,
    export_skins=True, export_force_sampling=True,
    export_anim_single_armature=True, export_def_bones=False,
    export_anim_slide_to_zero=True)
raw = path.read_bytes()
doc = json.loads(raw[20:20+int.from_bytes(raw[12:16], 'little')])
assert len(doc.get('animations', [])) == 1
assert any('HandIndex1' in node.get('name', '') for node in doc['nodes'])
report = {
    'schema': 'sub01.original-phone-capture-export.v1',
    'source_fbx_sha256': expected,
    'output_sha256': hashlib.sha256(raw).hexdigest(),
    'fps': scene.render.fps / scene.render.fps_base,
    'action_frame_range': [start, end],
    'original_bone_names': [bone.name for bone in arm.data.bones],
    'bones': len(arm.data.bones), 'glb_nodes': len(doc['nodes']),
    'glb_animation_channels': len(doc['animations'][0]['channels']),
    'export_time_origin': 'First captured frame shifted to elapsed zero',
    'actual_source_bone_samples': records,
    'old_owner_mesh_or_retarget_used': False,
    'native_imported': False, 'hand_visual_or_contact_accepted': False,
}
(output / 'original-phone-capture-report.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps({key: report[key] for key in (
    'output_sha256', 'fps', 'action_frame_range', 'bones', 'glb_nodes',
    'glb_animation_channels')}), flush=True)
