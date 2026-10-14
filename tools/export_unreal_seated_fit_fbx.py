"""SERVER ONLY (root): convert the committed seat-pose-fit clips, merged with the owner skin, to one animation-only FBX
per role for tools/unreal_import_seated_fit_fbx.py. Owned wrapper next to root's tools/export_unreal_seating_fbx.py
(left untouched): same FBX export options and 65-joint/bone-name checks, no render, rig or bone edits, no trims, no
new motion. Each role is exported at its own key rate (DeskTypingSeated 60 fps, the others 30 fps), so every
written GLB key is one FBX frame.

    node tools/uncompress_unreal_glb.mjs web/room/char_mixamo.glb OWNER.glb
    node tools/merge_unreal_skin_clips.mjs OWNER.glb MERGED.glb docs/proposed/seat-pose-fit/SUB01_DeskTyping_seated.glb \
        docs/proposed/seat-pose-fit/SUB01_SeatedIdle.glb docs/proposed/seat-pose-fit/SUB01_SitDown_seated.glb \
        docs/proposed/seat-pose-fit/SUB01_SitToType_seated.glb docs/proposed/seat-pose-fit/SUB01_TypeToSit_seated.glb \
        docs/proposed/seat-pose-fit/SUB01_GetUp_seated.glb
    blender -b --python tools/export_unreal_seated_fit_fbx.py -- MERGED.glb <project>/SourceAssets/SeatedFitFBX

All six roles are converted, failing fits included; the audit records each per-clip fit verdict (`fit_pass`) and the
importer decides (it never accepts a failing fit). Refuses unless every clip GLB is byte-identical to the committed
fit and the merged source carries each action with the report's key count. Writes <Role>.fbx and
seated-fit-fbx-audit.json (sub01.seated-fit-fbx-audit.v1).
"""
import bpy
import hashlib
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unreal_import_seated_fit_fbx as fit  # noqa: E402  (pure checks; no unreal import at module level)

args = sys.argv[sys.argv.index('--') + 1:]
source, out = Path(args[0]), Path(args[1])
plan = fit.plan_clips()                                # committed GLB bytes, reports, verdicts and key rates
out.mkdir(parents=True, exist_ok=True)
raw = source.read_bytes()
doc = json.loads(raw[20:20 + int.from_bytes(raw[12:16], 'little')])
expected_bones = {doc['nodes'][i]['name'] for i in doc['skins'][0]['joints']}
if len(expected_bones) != 65:
    raise RuntimeError('Actual owner 65-joint contract changed')
for row in plan:
    merged = fit.glb_animation(raw, row['source_action'])
    if merged['keys'] != row['frames'] or abs(merged['duration_s'] - row['duration_s']) > 1e-6:
        raise RuntimeError(f'Merged source lacks {row["source_action"]} with {row["frames"]} keys')
rows = []
for row in plan:
    fps = row['fps']
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps = fps                 # the glTF importer keys at the scene rate: one key per frame
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
    name = row['source_action']
    actions = [a for a in bpy.data.actions if a.name == name or a.name.startswith(name + '.')]
    if len(actions) != 1:
        raise RuntimeError('Ambiguous source seated-fit action ' + name)
    arm.animation_data.action = actions[0]
    start, end = actions[0].frame_range
    if abs((end - start) / fps - row['duration_s']) > 1e-3:
        raise RuntimeError(f'Actual seated-fit duration changed for {name}')
    bpy.context.scene.frame_start, bpy.context.scene.frame_end = math.floor(start), math.ceil(end)
    bpy.context.scene.frame_set(math.floor(start))
    path = out / (row['role'] + '.fbx')
    bpy.ops.export_scene.fbx(filepath=str(path.resolve()), use_selection=True, object_types={'ARMATURE'}, add_leaf_bones=False,
                             use_armature_deform_only=False, apply_unit_scale=True, axis_forward='-Z', axis_up='Y', bake_anim=True,
                             bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False, bake_anim_simplify_factor=0,
                             bake_anim_step=1)
    rows.append({'role': row['role'], 'source_action': name, 'glb': row['glb'], 'glb_sha256': row['glb_sha256'],
                 'report': row['report'], 'fit_pass': row['fit_pass'], 'fps': fps, 'frames': row['frames'],
                 'duration_s': row['duration_s'], 'source_frame_range': [start, end],
                 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'file': path.name})
audit = {'schema': fit.AUDIT_SCHEMA, 'source_sha256': hashlib.sha256(raw).hexdigest(), 'bone_names': sorted(expected_bones),
         'clips': rows, 'bone_edits': False, 'blender': bpy.app.version_string,
         'physical_seat_contact_verified': False, 'runtime_ready': False}
fit.check_audit(audit)
(out / fit.AUDIT_FILE).write_text(json.dumps(audit, indent=2) + '\n')
