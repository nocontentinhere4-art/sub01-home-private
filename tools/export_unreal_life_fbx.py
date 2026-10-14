"""SERVER ONLY (root): convert accepted GLB life captures, merged with the owner skin, to
animation-only FBX for tools/unreal_import_life_fbx.py. No render, rig or bone edits, no trims,
no root-motion removal, no new motion.

Prepare the merged source with the existing tools (owner skin + the chosen clip GLBs):
    node tools/uncompress_unreal_glb.mjs ...  &&  node tools/merge_unreal_skin_clips.mjs ...
Run:
    blender -b --python tools/export_unreal_life_fbx.py -- MERGED.glb OUT_DIR INVENTORY.json ROLE=CLIP.glb [ROLE=CLIP.glb ...]
Each ROLE=CLIP.glb names a repository clip that the inventory accepted for that role; its action in
MERGED.glb is the clip's basename (merge_unreal_skin_clips naming).
"""
import bpy
import hashlib
import json
import math
import sys
from pathlib import Path

args = sys.argv[sys.argv.index('--') + 1:]
source, out, inventory = Path(args[0]), Path(args[1]), json.loads(Path(args[2]).read_text())
picks = dict(item.split('=', 1) for item in args[3:])
if not picks or set(picks) - {'Idle', 'LieDown', 'SleepLoop', 'GetUp'}:
    raise RuntimeError('Pick at least one of Idle, LieDown, SleepLoop, GetUp')
out.mkdir(parents=True, exist_ok=True)
raw = source.read_bytes()
doc = json.loads(raw[20:20 + int.from_bytes(raw[12:16], 'little')])
expected_bones = {doc['nodes'][i]['name'] for i in doc['skins'][0]['joints']}
if len(expected_bones) != 65:
    raise RuntimeError('Actual owner 65-joint contract changed')
durations = {a['name']: max(doc['accessors'][s['input']]['max'][0] for s in a['samplers']) for a in doc['animations']}
chosen = {}
for role, clip in picks.items():
    rows = [c for c in inventory['candidates'] if c.get('role') == role and c.get('file') == clip and c.get('verdict') == 'Candidate']
    if len(rows) != 1:
        raise RuntimeError(f'{role}: {clip} is not an accepted inventory capture; nothing is substituted')
    name = Path(clip).stem
    if name not in durations or abs(durations[name] - rows[0]['duration_s']) > 1e-3:
        raise RuntimeError(f'{role}: merged source lacks {name} at its measured duration')
    chosen[role] = (name, rows[0])
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
rows = []
for role, (name, record) in chosen.items():
    actions = [a for a in bpy.data.actions if a.name == name or a.name.startswith(name + '.')]
    if len(actions) != 1:
        raise RuntimeError('Ambiguous source life action ' + name)
    action = actions[0]
    arm.animation_data.action = action
    start, end = action.frame_range
    if abs((end - start) / 30 - record['duration_s']) > 1e-3:
        raise RuntimeError('Actual captured duration changed')
    bpy.context.scene.frame_start = math.floor(start)
    bpy.context.scene.frame_end = math.ceil(end)
    bpy.context.scene.frame_set(math.floor(start))
    path = out / (role + '.fbx')
    bpy.ops.export_scene.fbx(filepath=str(path.resolve()), use_selection=True, object_types={'ARMATURE'}, add_leaf_bones=False,
                             use_armature_deform_only=False, apply_unit_scale=True, axis_forward='-Z', axis_up='Y', bake_anim=True,
                             bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False, bake_anim_simplify_factor=0, bake_anim_step=1)
    rows.append({'role': role, 'source_action': name, 'source_clip': record['file'], 'inventory_sha256': record['sha256'],
                 'duration_s': record['duration_s'], 'source_frame_range': [start, end],
                 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'file': path.name})
(out / 'life-fbx-audit.json').write_text(json.dumps({
    'source_sha256': hashlib.sha256(raw).hexdigest(), 'bone_names': sorted(expected_bones), 'clips': rows, 'bone_edits': False,
    'fps': 30, 'blender': bpy.app.version_string, 'bed_contact_verified': False, 'runtime_ready': False}, indent=2) + '\n')
