"""SERVER ONLY (root): convert the committed DERIVED phone-grip clip, merged with the owner skin, to one
animation-only FBX for native VISUAL review. Mirrors tools/export_unreal_gaming_grip_fbx.py: no render, rig or bone
edits, no trims, no new motion. Never replaces the original captured Phone asset.

    python tools/phone_grip_packet.py check
    node tools/uncompress_unreal_glb.mjs web/room/char_mixamo.glb OWNER.glb
    node tools/merge_unreal_skin_clips.mjs OWNER.glb MERGED.glb docs/proposed/phone-grip-derived/SUB01_PhoneGrip_derived.glb
    blender -b --python tools/export_unreal_phone_grip_fbx.py -- MERGED.glb <project>/SourceAssets/PhoneFBX

Refuses unless docs/proposed/phone-grip-derived/packet.json pins the derived GLB sha, the merged source holds that
clip with 557 keys on the owner's 65 joints, and its duration matches. Writes PhoneGrip.fbx and
phone-grip-fbx-audit.json (sub01.phone-grip-fbx-audit.v1, phone_grip_verified/runtime_ready false).
"""
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT/'docs/proposed/phone-grip-derived/packet.json'
CLIP_NAME = 'SUB01_PhoneGrip_derived'
FRAMES, JOINTS, AUDIT_FILE, AUDIT_SCHEMA = 557, 65, 'phone-grip-fbx-audit.json', 'sub01.phone-grip-fbx-audit.v1'

args = sys.argv[sys.argv.index('--')+1:]
source, out = Path(args[0]), Path(args[1])
packet = json.loads(PACKET.read_text())
clip = ROOT/packet['files']['derived_glb']['path']
clip_sha = hashlib.sha256(clip.read_bytes()).hexdigest()
if clip_sha != packet['files']['derived_glb']['sha256'] or packet['ready'] is not False:
    raise RuntimeError('Derived phone clip is not the packet-pinned GLB; nothing is substituted')
out.mkdir(parents=True, exist_ok=True)
raw = source.read_bytes()
doc = json.loads(raw[20:20+int.from_bytes(raw[12:16], 'little')])
expected_bones = {doc['nodes'][i]['name'] for i in doc['skins'][0]['joints']}
if len(expected_bones) != JOINTS:
    raise RuntimeError('Actual owner 65-joint contract changed')
keys = [doc['accessors'][s['input']] for a in doc['animations'] if a['name'] == CLIP_NAME for s in a['samplers']]
if not keys or max(k['count'] for k in keys) != FRAMES:
    raise RuntimeError(f'Merged source lacks {CLIP_NAME} with {FRAMES} keys')
glb_duration = max(k['max'][0] for k in keys)-min(k['min'][0] for k in keys)
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
actions = [a for a in bpy.data.actions if a.name == CLIP_NAME or a.name.startswith(CLIP_NAME+'.')]
if len(actions) != 1:
    raise RuntimeError('Ambiguous derived phone action')
arm.animation_data.action = actions[0]
start, end = actions[0].frame_range
if abs((end-start)/30-glb_duration) > 1e-3:
    raise RuntimeError('Derived phone clip duration changed')
bpy.context.scene.frame_start, bpy.context.scene.frame_end = math.floor(start), math.ceil(end)
bpy.context.scene.frame_set(math.floor(start))
path = out/'PhoneGrip.fbx'
bpy.ops.export_scene.fbx(filepath=str(path.resolve()), use_selection=True, object_types={'ARMATURE'}, add_leaf_bones=False,
                         use_armature_deform_only=False, apply_unit_scale=True, axis_forward='-Z', axis_up='Y', bake_anim=True,
                         bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False, bake_anim_simplify_factor=0, bake_anim_step=1)
(out/AUDIT_FILE).write_text(json.dumps({
    'schema': AUDIT_SCHEMA, 'source_sha256': hashlib.sha256(raw).hexdigest(), 'bone_names': sorted(expected_bones),
    'clips': [{'role': 'PhoneGripDerived', 'source_action': CLIP_NAME, 'derived_glb_sha256': clip_sha, 'frames': FRAMES,
               'duration_s': glb_duration, 'source_frame_range': [start, end], 'file': path.name,
               'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}],
    'label': 'derived_from_capture', 'bone_edits': False, 'fps': 30, 'blender': bpy.app.version_string,
    'phone_grip_verified': False, 'runtime_ready': False}, indent=2)+'\n')
