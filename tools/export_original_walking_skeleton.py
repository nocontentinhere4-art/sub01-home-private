"""Runpod-only original FBX skeleton/animation export; no old owner retarget."""
import bpy
import hashlib
import json
import sys
from pathlib import Path

source, output = map(Path, sys.argv[sys.argv.index('--') + 1:])
assert hashlib.sha256(source.read_bytes()).hexdigest() == 'a4d2b808cf81b3d8b8d4b4b837bd1e4088f8f83f49fa1dd8d27273607d68ea62'
output.mkdir(exist_ok=False, parents=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.scene.render.fps = 30
bpy.ops.import_scene.fbx(filepath=str(source), use_anim=True)
scene = bpy.context.scene
arms = [o for o in scene.objects if o.type == 'ARMATURE']
assert len(arms) == 1
arm = arms[0]
assert not [o for o in scene.objects if o.type == 'MESH']
actions = list(bpy.data.actions)
assert len(actions) == 1
arm.animation_data_create()
arm.animation_data.action = actions[0]
for track in arm.animation_data.nla_tracks:
    track.mute = True
start, end = actions[0].frame_range
scene.frame_start, scene.frame_end = int(start), int(end)
records = []
for frame in [start, (start + end)/2, end]:
    scene.frame_set(int(frame), subframe=frame-int(frame))
    bpy.context.view_layer.update()
    records.append({'frame': frame, 'bones': {
        b.name: {'head_world_m': list(arm.matrix_world @ b.head),
                 'tail_world_m': list(arm.matrix_world @ b.tail)}
        for b in arm.pose.bones if 'Hand' in b.name}})
scene.frame_set(int(start))
path = output / 'original-walking-skeleton.glb'
bpy.ops.export_scene.gltf(filepath=str(path), export_format='GLB', export_animations=True,
                          export_skins=True, export_force_sampling=True,
                          export_anim_single_armature=True, export_def_bones=False)
raw = path.read_bytes()
doc = json.loads(raw[20:20+int.from_bytes(raw[12:16], 'little')])
assert doc.get('animations') and any('HandIndex1' in n.get('name', '') for n in doc['nodes'])
report = {'schema': 'sub01.original-walking-capture-export.v1', 'source_fbx_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
          'output_sha256': hashlib.sha256(raw).hexdigest(), 'fps': scene.render.fps/scene.render.fps_base,
          'action_frame_range': [start, end], 'original_bone_names': [b.name for b in arm.data.bones],
          'bones': len(arm.data.bones), 'glb_nodes': len(doc['nodes']), 'glb_animation_channels': len(doc['animations'][0]['channels']),
          'actual_source_bone_samples': records, 'old_owner_mesh_or_retarget_used': False,
          'native_imported': False, 'hand_visual_or_contact_accepted': False}
(output/'original-capture-report.json').write_text(json.dumps(report, indent=2)+'\n')
print('ORIGINAL_CAPTURE_EXPORTED', json.dumps({k: report[k] for k in ['output_sha256','fps','action_frame_range','bones','glb_nodes','glb_animation_channels']}), flush=True)
