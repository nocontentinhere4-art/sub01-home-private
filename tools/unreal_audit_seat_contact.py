"""Server UE editor audit: seated buttocks/thighs on the actual chair cushion and soles on the floor.

Run on the authorized private GPU editor only, after tools/unreal_chair_surface_audit.py
has written private-audit/native-chair-surface.json. Reads the actual owner mesh, the
captured DeskTyping clip (3-8 s at 60 Hz, the same samples as the typing contact audit) and
the diagnostic body transform. Writes private-audit/native-seat-contact.json, then gates it
with tools/validate_unreal_seat_contact.py and writes the proposed vertical anchor correction
(private-audit/native-seat-correction.json). Probe only: no mesh, actor, pose or collision is
changed, and nothing here sets NativeSeatVerified.
"""
import json
import sys
from pathlib import Path

import unreal as u

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_unreal_seat_contact import cushion_triangles, propose_vertical_anchor, validate  # noqa: E402

BODY_CM, BODY_YAW, FLOOR_CM = (203.9, -232.3, -.6), 180, 0.0   # unreal_hands_diagnostic.py seat pose; ground floor


def run():
    root = Path(u.Paths.project_dir()).resolve()
    chair = json.loads((root / 'private-audit/native-chair-surface.json').read_text())
    triangles = [u.Vector(*p) for p in cushion_triangles(chair)]
    mesh = u.load_asset('/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner')
    clip = u.load_asset('/Game/Sub01Hands/FBX/SUB01_DeskTyping.SUB01_DeskTyping')
    if not mesh or not clip:
        raise RuntimeError('Actual owner mesh/DeskTyping clip missing')
    u.Sub01HomeHandsInstance.finish_pending_skin_compilation()
    component = u.SkeletalMeshComponent()
    component.set_skeletal_mesh_asset(mesh)
    names = [component.get_bone_name(i) for i in range(component.get_num_bones())]
    parents = {str(n): str(component.get_parent_bone(n)) for n in names}
    body = u.Transform(location=u.Vector(*BODY_CM), rotation=u.Rotator(yaw=BODY_YAW))
    rows = []
    for frame in range(180, 481):
        time = frame / 60
        poses = u.AnimationLibrary.get_bone_poses_for_time(clip, names, time, False, mesh)
        local = {str(n): p for n, p in zip(names, poses)}
        resolved = {}

        def pose(name):
            if name not in resolved:
                parent = parents[name]
                resolved[name] = u.MathLibrary.compose_transforms(local[name], pose(parent)) if parent in local else local[name]
            return resolved[name]

        report = json.loads(u.Sub01HomeHandsInstance.analyze_captured_seat_skin(
            mesh, [pose(str(n)) for n in names], body, triangles, FLOOR_CM))
        if 'error' in report:
            raise RuntimeError(report['error'])
        rows.append({'time': time, **report})
    result = {'schema': 'sub01.native-seat-contact.v1', 'body_cm': list(BODY_CM), 'body_yaw': BODY_YAW,
              'floor_cm': FLOOR_CM, 'chair_component': chair['chair']['component'], 'samples': rows}
    out = root / 'private-audit/native-seat-contact.json'
    out.write_text(json.dumps(result, indent=2) + '\n')
    # Probe only: the result is evidence for a pose/anchor correction, never NativeSeatVerified.
    proposal = propose_vertical_anchor(result)
    (root / 'private-audit/native-seat-correction.json').write_text(json.dumps(proposal, indent=2, default=str) + '\n')
    u.log('SUB01_SEAT_CONTACT_CORRECTION ' + json.dumps({k: proposal[k] for k in ('recommended_delta_cm', 'diagnosis')}))
    try:
        summary = validate(result)
        u.log('SUB01_SEAT_CONTACT_PROBE_IN_BAND ' + json.dumps(summary, default=str))
    except ValueError as error:
        u.log_warning(f'SUB01_SEAT_CONTACT_PROBE_OUT_OF_BAND {error}; report {out}')


if __name__ == '__main__':
    run()
