"""SERVER ONLY (root): convert the committed DERIVED grip clip, merged with the owner skin, to one animation-only FBX
for tools/unreal_import_gaming_grip.py. Modelled on tools/export_unreal_life_fbx.py: no render, rig or bone edits,
no trims, no new motion.

    node tools/uncompress_unreal_glb.mjs web/room/char_mixamo.glb OWNER.glb
    node tools/merge_unreal_skin_clips.mjs OWNER.glb MERGED.glb docs/proposed/controller-play/SUB01_GamingGrip_derived.glb
    blender -b --python tools/export_unreal_gaming_grip_fbx.py -- MERGED.glb <project>/SourceAssets/ControllerFBX \
        docs/proposed/controller-play/SUB01_GamingGrip_derived.glb

Refuses unless the clip GLB is byte-identical to the committed derived clip (sha bf31d645...) and the merged action
has its 152 keys. Writes GamingGrip.fbx and gaming-grip-fbx-audit.json (sub01.gaming-grip-fbx-audit.v1).
"""
import bpy
import hashlib
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unreal_import_gaming_grip as grip  # noqa: E402  (pure constants/checks; no unreal import at module level)

args = sys.argv[sys.argv.index('--') + 1:]
source, out, clip = Path(args[0]), Path(args[1]), Path(args[2])
clip_sha = hashlib.sha256(clip.read_bytes()).hexdigest()
if clip_sha != grip.DERIVED_GLB_SHA256:
    raise RuntimeError('Clip is not the committed derived grip GLB; nothing is substituted')
out.mkdir(parents=True, exist_ok=True)
raw = source.read_bytes()
doc = json.loads(raw[20:20 + int.from_bytes(raw[12:16], 'little')])
expected_bones = {doc['nodes'][i]['name'] for i in doc['skins'][0]['joints']}
if len(expected_bones) != 65:
    raise RuntimeError('Actual owner 65-joint contract changed')
name = clip.stem                                   # merge_unreal_skin_clips names a single-animation clip by basename
keys = [doc['accessors'][s['input']] for a in doc['animations'] if a['name'] == name for s in a['samplers']]
if not keys or max(k['count'] for k in keys) != grip.FRAMES:
    raise RuntimeError(f'Merged source lacks {name} with {grip.FRAMES} keys')
glb_duration = max(k['max'][0] for k in keys) - min(k['min'][0] for k in keys)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.scene.render.fps = 30
bpy.ops.import_scene.gltf(filepath=str(source.resolve()))
arms = [o for o in bpy.context.scene.objects if o.type == 'ARMATURE']
if len(arms) != 1:
    raise RuntimeError('Expected one actual source armature')
arm = arms[0]
if set(b.name for b in arm.data.bones) != expected_bones:
    raise RuntimeError('Imported bone names differ; do not retarget silently')
for track in arm.animation_data.nla_tracks:
    track.mute = True
for obj in bpy.context.scene.objects:
    obj.select_set(obj == arm)
bpy.context.view_layer.objects.active = arm
actions = [a for a in bpy.data.actions if a.name == name or a.name.startswith(name + '.')]
if len(actions) != 1:
    raise RuntimeError('Ambiguous source grip action ' + name)
arm.animation_data.action = actions[0]
start, end = actions[0].frame_range
if abs((end - start) / 30 - glb_duration) > 1e-3:
    raise RuntimeError('Actual derived grip duration changed')
bpy.context.scene.frame_start, bpy.context.scene.frame_end = math.floor(start), math.ceil(end)
bpy.context.scene.frame_set(math.floor(start))
path = out / 'GamingGrip.fbx'
bpy.ops.export_scene.fbx(filepath=str(path.resolve()), use_selection=True, object_types={'ARMATURE'}, add_leaf_bones=False,
                         use_armature_deform_only=False, apply_unit_scale=True, axis_forward='-Z', axis_up='Y', bake_anim=True,
                         bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False, bake_anim_simplify_factor=0, bake_anim_step=1)
row = {'role': grip.ROLE, 'source_action': name, 'source_clip': grip.DERIVED_GLB, 'derived_glb_sha256': clip_sha,
       'source_fbx_sha256': grip.controller.GAMING_FBX_SHA256, 'frames': grip.FRAMES, 'duration_s': glb_duration,
       'source_frame_range': [start, end], 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'file': path.name}
grip.check_audit({'schema': grip.AUDIT_SCHEMA, 'bone_names': sorted(expected_bones), 'bone_edits': False, 'fps': 30, 'clips': [row]})
(out / grip.AUDIT_FILE).write_text(json.dumps({
    'schema': grip.AUDIT_SCHEMA, 'source_sha256': hashlib.sha256(raw).hexdigest(), 'bone_names': sorted(expected_bones),
    'clips': [row], 'bone_edits': False, 'fps': 30, 'blender': bpy.app.version_string,
    'controller_grip_verified': False, 'runtime_ready': False}, indent=2) + '\n')
