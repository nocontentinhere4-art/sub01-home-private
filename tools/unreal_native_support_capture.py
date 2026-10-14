"""SERVER UE editor capture: the imported clips evaluated on the ACTUAL owner mesh against the measured bed/sofa/controller.

    SUB01_SUPPORT_CAPTURE=/srv/private/capture-bed.json \\
    UnrealEditor-Cmd <project>/Sub01HomeLab.uproject -ExecutePythonScript="<repo>/tools/unreal_native_support_capture.py" -unattended

then, on any CPU (numpy for the grip gate):

    python3 tools/native_support_contact_evidence.py bed|sofa|grip <project> <project>/private-audit/native-<kind>-capture.json

Pattern: tools/unreal_audit_seat_contact.py (AnimationLibrary.get_bone_poses_for_time composed down the parent chain,
the renderer's native USub01HomeHandsInstance.AnalyzeCapturedSeatSkin per sample). This script only OBSERVES and writes
private-audit/native-<kind>-capture.json (schema sub01.native-support-contact-capture.v1); acceptance is the offline
evaluator's, from these observations only. No mesh, actor, pose, collision or config is changed.

Config (JSON at $SUB01_SUPPORT_CAPTURE; every number MEASURED on the server from the live character/home, recorded
verbatim; nothing is defaulted):
  common: {"kind": "bed"|"sofa"|"controller_grip", "floor_cm": <CharacterMovement CurrentFloor impact Z>,
           "floor_evidence": "<log line/file>", "placement": {...}}
  bed placement: {"approach_cm": [x, y], "capsule_z_cm": z, "yaw_deg": yaw,            (capsule after the turn in place)
                  "hands_base_offset_cm": [x, y, z], "hands_mesh_rotation_deg": {"pitch":..,"yaw":..,"roll":..}}
      + <project>/private-audit/native-life-root-paths.json (tools/unreal_bed_root_motion.py stage-paths): the body
        follows the same root path the C++ SampleLifeRootPath applies (SleepLoop looping), capsule at the approach.
  sofa / controller_grip placement: {"approach_cm": [x, y], "capsule_z_cm": z, "yaw_deg": yaw,
                  "body_offset_cm": [x, y, z], "body_yaw_deg": yaw, "hands_mesh_rotation_deg": {...}}
      (the controller adapter: FirstPersonBody relative location = body_offset_cm, rotation = HandsMeshRotation +
       (0, body_yaw, 0)); controller_grip reads the accepted private-audit/native-controller-play-evidence.json grip
       offset/rotation and the controller mesh from private-audit/native-controller-asset.json, and needs
       tools/unreal_controller_grip_contact_native.py installed and compiled.
NOT RUN in this repository (no engine here); the pure helpers are tested.
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unreal_life_clips_runtime as life  # noqa: E402
import unreal_controller_play_runtime as controller  # noqa: E402
import unreal_bed_root_motion as root_motion  # noqa: E402
from native_support_contact_evidence import CAPTURE_SCHEMA, GRIP_ANALYZER, MIN_RATE_HZ, SEAT_ANALYZER  # noqa: E402

OWNER_MESH = '/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner'
PALM_BAND_CM = (-.3, .3)          # == tools/fit_controller_grip.py PALM_BAND_CM (checked by the tests; numpy-free here)
GRIP_MARGIN_CM = 5.0              # culling only (AnalyzeCapturedControllerGrip): a far palm cannot be in the +-0.3 band


def sample_times(duration: float, rate: int = MIN_RATE_HZ):
    """0, 1/rate, ... and the clip's last instant: the evaluator's coverage rule (>= int(duration*rate), both ends)."""
    if not (isinstance(duration, (int, float)) and math.isfinite(duration) and duration > 0):
        raise ValueError('clip duration must be positive')
    times = [k / rate for k in range(int(math.floor(duration * rate + 1e-9)) + 1)]
    if duration - times[-1] > 1e-6:
        times.append(float(duration))
    return times


def sample_root_path(path, fps: float, seconds: float, loop: bool):
    """Python twin of the C++ SampleLifeRootPath (tools/unreal_bed_root_motion.py): forward/right cm at a clip time."""
    if len(path) < 2 or fps <= 0:
        raise ValueError('root path needs >= 2 samples and fps > 0')
    last = float(len(path) - 1)
    x = seconds * fps
    x = math.fmod(max(x, 0.0), last) if loop else min(max(x, 0.0), last)
    a = min(max(int(math.floor(x)), 0), len(path) - 1)
    b = min(a + 1, len(path) - 1)
    f = x - a
    return (path[a][0] + (path[b][0] - path[a][0]) * f, path[a][1] + (path[b][1] - path[a][1]) * f)


def load_root_paths(doc: dict):
    if doc.get('schema') != root_motion.ROOT_PATH_SCHEMA:
        raise ValueError('native-life-root-paths.json has another schema')
    fps = float(doc.get('fps', 30))
    paths = {}
    for role in life.BED_ROLES:
        r = doc['roles'][role]
        if len(r['forward_cm']) != len(r['right_cm']) or len(r['forward_cm']) < 2:
            raise ValueError(f'root path for {role} is malformed')
        paths[role] = list(zip(r['forward_cm'], r['right_cm']))
    return fps, paths


def require_placement(cfg: dict, keys):
    p = cfg.get('placement') or {}
    missing = [k for k in keys if k not in p]
    if missing:
        raise ValueError('placement must be measured on the server; missing ' + ', '.join(missing))
    if not (isinstance(cfg.get('floor_cm'), (int, float)) and math.isfinite(cfg['floor_cm']) and cfg.get('floor_evidence')):
        raise ValueError('floor_cm and floor_evidence (the native CharacterMovement floor) are required')
    return p


def run():  # pragma: no cover - server only (Unreal Editor Python)
    import unreal as u
    root = Path(u.Paths.project_dir()).resolve()
    audit = root / 'private-audit'
    cfg = json.loads(Path(os.environ['SUB01_SUPPORT_CAPTURE']).read_text())
    kind = cfg.get('kind')
    out = audit / f'native-{kind}-capture.json'
    capture = {'schema': CAPTURE_SCHEMA, 'kind': kind, 'observation': 'native_editor_clip_evaluation',
               'analyzer': GRIP_ANALYZER if kind == 'controller_grip' else SEAT_ANALYZER, 'owner_mesh': OWNER_MESH,
               'config': cfg, 'clips': [], 'samples': [], 'errors': []}
    try:
        if kind not in ('bed', 'sofa', 'controller_grip'):
            raise ValueError('kind must be bed, sofa or controller_grip')
        mesh = u.load_asset(OWNER_MESH)
        if not isinstance(mesh, u.SkeletalMesh):
            raise RuntimeError('Actual owner mesh missing')
        u.Sub01HomeHandsInstance.finish_pending_skin_compilation()
        component = u.SkeletalMeshComponent()
        component.set_skeletal_mesh_asset(mesh)
        names = [component.get_bone_name(i) for i in range(component.get_num_bones())]
        parents = {str(n): str(component.get_parent_bone(n)) for n in names}

        def component_pose(clip, time):
            local = {str(n): p for n, p in zip(names, u.AnimationLibrary.get_bone_poses_for_time(clip, names, time, False, mesh))}
            resolved = {}

            def pose(name):
                if name not in resolved:
                    parent = parents[name]
                    resolved[name] = u.MathLibrary.compose_transforms(local[name], pose(parent)) if parent in local else local[name]
                return resolved[name]
            return [pose(str(n)) for n in names]

        def load_clip(path):
            clip = u.load_asset(path)
            if not isinstance(clip, u.AnimSequence) or clip.get_editor_property('skeleton') != mesh.get_editor_property('skeleton'):
                raise RuntimeError(f'{path}: not an AnimSequence on the owner USkeleton')
            return clip

        def rotator(d):
            return u.Rotator(roll=float(d['roll']), pitch=float(d['pitch']), yaw=float(d['yaw']))

        if kind == 'bed':
            p = require_placement(cfg, ('approach_cm', 'capsule_z_cm', 'yaw_deg', 'hands_base_offset_cm', 'hands_mesh_rotation_deg'))
            text = (audit / 'native-bed-surface.json').read_text()
            capture['surface_report'] = {'file': 'private-audit/native-bed-surface.json', 'revision': str(life.life_id(text))}
            triangles = [u.Vector(*q) for q in life.mattress_triangles(json.loads(text))]
            fps, paths = load_root_paths(json.loads((audit / root_motion.ROOT_PATH_FILE).read_text()))
            capture['root_path'] = {'file': 'private-audit/' + root_motion.ROOT_PATH_FILE, 'fps': fps}
            yaw = float(p['yaw_deg'])
            c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
            for role in life.BED_ROLES:
                clip = load_clip(life.clip_object_path(role))
                duration = float(clip.get_play_length())
                capture['clips'].append({'role': role, 'object_path': life.clip_object_path(role), 'duration_s': duration, 'rate_hz': MIN_RATE_HZ})
                for t in sample_times(duration):
                    fwd, right = sample_root_path(paths[role], fps, t, role == 'SleepLoop')
                    # Capsule at the approach (yaw after the turn); body = HandsBaseOffset + root path in the actor frame.
                    actor = u.Transform(location=u.Vector(p['approach_cm'][0], p['approach_cm'][1], p['capsule_z_cm']), rotation=u.Rotator(yaw=yaw))
                    rel = u.Transform(location=u.Vector(p['hands_base_offset_cm'][0] + fwd, p['hands_base_offset_cm'][1] + right,
                                                        p['hands_base_offset_cm'][2]), rotation=rotator(p['hands_mesh_rotation_deg']))
                    body = u.MathLibrary.compose_transforms(rel, actor)
                    row = json.loads(u.Sub01HomeHandsInstance.analyze_captured_seat_skin(mesh, component_pose(clip, t), body, triangles, cfg['floor_cm']))
                    capture['samples'].append({'role': role, 'time': t, 'root_path_cm': [fwd, right], **row})
                    if 'error' in row:
                        raise RuntimeError(row['error'])
        else:
            p = require_placement(cfg, ('approach_cm', 'capsule_z_cm', 'yaw_deg', 'body_offset_cm', 'body_yaw_deg', 'hands_mesh_rotation_deg'))
            m = p['hands_mesh_rotation_deg']
            actor = u.Transform(location=u.Vector(p['approach_cm'][0], p['approach_cm'][1], p['capsule_z_cm']), rotation=u.Rotator(yaw=float(p['yaw_deg'])))
            rel = u.Transform(location=u.Vector(*p['body_offset_cm']),
                              rotation=u.Rotator(roll=float(m['roll']), pitch=float(m['pitch']), yaw=float(m['yaw']) + float(p['body_yaw_deg'])))
            body = u.MathLibrary.compose_transforms(rel, actor)
            clip = load_clip(controller.CLIP_OBJECT_PATH)
            duration = float(clip.get_play_length())
            capture['clips'].append({'role': controller.ROLE, 'object_path': controller.CLIP_OBJECT_PATH, 'duration_s': duration, 'rate_hz': MIN_RATE_HZ})
            if kind == 'sofa':
                text = (audit / controller.SOFA_REPORT).read_text()
                capture['surface_report'] = {'file': 'private-audit/' + controller.SOFA_REPORT, 'revision': str(controller.play_id(text))}
                triangles = [u.Vector(*q) for q in controller.sofa_seat_triangles(json.loads(text))[0]]
                for t in sample_times(duration):
                    row = json.loads(u.Sub01HomeHandsInstance.analyze_captured_seat_skin(mesh, component_pose(clip, t), body, triangles, cfg['floor_cm']))
                    capture['samples'].append({'role': controller.ROLE, 'time': t, **row})
                    if 'error' in row:
                        raise RuntimeError(row['error'])
            else:
                if not hasattr(u.Sub01HomeHandsInstance, 'analyze_captured_controller_grip'):
                    raise RuntimeError('AnalyzeCapturedControllerGrip is not compiled (tools/unreal_controller_grip_contact_native.py install)')
                ev_text = (audit / controller.EVIDENCE).read_text()
                ev = json.loads(ev_text)
                if ev.get('schema') != controller.EVIDENCE_SCHEMA or ev.get('accepted') is not True:
                    raise RuntimeError('Controller play evidence is not accepted')
                capture['evidence_revision'] = str(controller.play_id(ev_text))
                asset = json.loads((audit / controller.CONTROLLER_ASSET_RECEIPT).read_text())
                if asset.get('schema') != controller.CONTROLLER_ASSET_SCHEMA or asset.get('source_sha256') != controller.CONTROLLER_SOURCE_SHA256:
                    raise RuntimeError('Controller asset receipt is not the reviewed controller')
                mesh_path = asset['physical_assembly']['mesh']
                if 'contact' in mesh_path.lower():
                    raise RuntimeError('The baked contact shadow is never grip geometry')
                prop = u.load_asset(mesh_path)
                local = []
                for section in range(prop.get_num_sections(0)):
                    verts, indices, *_ = u.ProceduralMeshLibrary.get_section_from_static_mesh(prop, 0, section)
                    local.extend(verts[i] for i in indices)
                hand = next(str(n) for n in names if str(n).endswith('RightHand'))
                offset, quat = ev['grip_offset_cm'], ev['grip_rotation_xyzw']
                capture['controller'] = {'mesh': mesh_path, 'triangles': len(local) // 3, 'grip_bone': hand}
                frames = None
                if hasattr(u.AnimationLibrary, 'get_num_frames') and hasattr(u.AnimationLibrary, 'get_time_at_frame'):
                    frames = [(k, float(u.AnimationLibrary.get_time_at_frame(clip, k))) for k in range(int(u.AnimationLibrary.get_num_frames(clip)))]
                    capture['frame_basis'] = 'AnimationLibrary.get_num_frames/get_time_at_frame'
                else:
                    frames = list(enumerate(sample_times(duration)))
                    capture['frame_basis'] = '30 Hz key times (derived clip keys every 1/30 s: controller.GLTF_FIRST_KEY_S)'
                for k, t in frames:
                    row = json.loads(u.Sub01HomeHandsInstance.analyze_captured_controller_grip(
                        mesh, component_pose(clip, t), body, hand, u.Vector(*offset), u.Quat(*quat), local,
                        PALM_BAND_CM[0], PALM_BAND_CM[1], GRIP_MARGIN_CM))
                    capture['samples'].append({'frame': k, 'time': t, **row})
                    if 'error' in row:
                        raise RuntimeError(row['error'])
    except Exception as exc:
        capture['errors'].append(str(exc))
        out.write_text(json.dumps(capture, indent=2) + '\n')
        raise
    out.write_text(json.dumps(capture, indent=2) + '\n')
    u.log(f'SUB01_SUPPORT_CAPTURE {kind} samples={len(capture["samples"])} {out}; evaluate offline with '
          f'tools/native_support_contact_evidence.py')


if __name__ == '__main__':
    run()
