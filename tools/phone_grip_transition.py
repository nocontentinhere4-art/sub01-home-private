"""Pickup / use / put-down plan for the original five-part phone (proposal, never accepted).

The phone is a world object until the hand actually reaches it, a wrist-attached rigid body
while held, and a world object again after release. Nothing teleports:

* REACH    phone stays at its rest transform; the wrist IK target is the pre-grasp wrist pose
           ``rest * inverse(attach_offset)`` approached from above the desk.
* GRASP    attach only when the measured skin-to-case gap (fit_phone_grip residuals on that frame)
           is within the contact band; ``attach_offset = inverse(wrist) * rest`` is taken from the
           actual wrist transform on that frame, so the phone does not move at the instant of attach.
* LIFT     the wrist-local offset blends from ``attach_offset`` to the solved texting mount ``mount``
           (slerp + smoothstep) while the wrist rises; the phone's case bottom must stay above the
           measured desk top on every sampled frame.
* USE      held at ``mount`` for the captured Texting clip; live browser screen unchanged.
* LOWER    reverse blend ``mount`` -> ``place_offset`` where ``place_offset = inverse(wrist_release) * rest``.
* RELEASE  detach when the case bottom is within the contact band of the desk top; phone keeps the
           exact world transform it had on the release frame.

Transforms are (R 3x3, t cm). Callers supply actual wrist world frames (root's native log or the
owner skin export); this module computes phone poses and refuses discontinuities.
"""
import math

import numpy as np

from tools.fit_phone_grip import matrix_to_quat, quat_to_matrix


def compose(a, b):
    return a[0]@b[0], a[0]@b[1]+a[1]


def inverse(a):
    return a[0].T, -a[0].T@a[1]


def slerp(qa, qb, s):
    qa, qb = np.asarray(qa, float), np.asarray(qb, float)
    d = float(qa@qb)
    if d < 0:
        qb, d = -qb, -d
    if d > 0.9995:
        q = qa+s*(qb-qa)
        return q/np.linalg.norm(q)
    th = math.acos(d)
    return (math.sin((1-s)*th)*qa+math.sin(s*th)*qb)/math.sin(th)


def smoothstep(s):
    s = min(max(s, 0.0), 1.0)
    return s*s*(3-2*s)


def blend_offset(a, b, s):
    s = smoothstep(s)
    q = slerp(matrix_to_quat(a[0]), matrix_to_quat(b[0]), s)
    return quat_to_matrix(q), (1-s)*a[1]+s*b[1]


def case_bottom(phone_world, half=(3.75, 7.5, .75)):
    """Lowest world height (axis index 2 = UE Z / caller's up axis) of the case box."""
    R, t = phone_world
    h = np.asarray(half)
    corners = np.array([[sx*h[0], sy*h[1], sz*h[2]] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])
    return float((corners@R.T+t)[:, 2].min())


def plan(wrists, times, rest, mount, grasp_index, lift_seconds, release_index=None, lower_seconds=None,
         desk_top=None, band=0.3, max_step_cm=3.0, up_axis_world=2):
    """Phone world transform per wrist frame. ``wrists`` are world (R,t) in the caller's frame."""
    if up_axis_world != 2:
        raise ValueError('Supply world frames with Z up (UE world)')
    attach = compose(inverse(wrists[grasp_index]), rest)
    place = compose(inverse(wrists[release_index]), rest) if release_index is not None else None
    out, phases = [], []
    for i, (w, t) in enumerate(zip(wrists, times)):
        if i < grasp_index or (release_index is not None and i > release_index):
            pose, phase = rest if i < grasp_index else out[release_index], 'world'
        else:
            s_lift = (t-times[grasp_index])/lift_seconds
            off, phase = (blend_offset(attach, mount, s_lift), 'lift') if s_lift < 1 else (mount, 'use')
            if release_index is not None and lower_seconds:
                s_low = 1-(times[release_index]-t)/lower_seconds
                if s_low > 0:
                    off, phase = blend_offset(mount, place, s_low), 'lower'
            pose = compose(w, off)
        out.append(pose)
        phases.append(phase)
    report = {'phases': phases, 'max_step_cm': 0.0, 'desk_clearance_min_cm': None, 'refusals': []}
    for i in range(1, len(out)):
        step = float(np.linalg.norm(out[i][1]-out[i-1][1]))
        report['max_step_cm'] = max(report['max_step_cm'], step)
        if step > max_step_cm:
            report['refusals'].append({'frame': i, 'reason': 'phone step %.2f cm exceeds %.2f' % (step, max_step_cm)})
    if desk_top is not None:
        held = [i for i, p in enumerate(phases) if p != 'world']
        if held:
            clear = min(case_bottom(out[i])-desk_top for i in held)
            report['desk_clearance_min_cm'] = round(clear, 4)
            if clear < -band:
                report['refusals'].append({'reason': 'case passes %.2f cm into the desk' % -clear})
    for idx, name in ((grasp_index, 'attach'), (release_index, 'release')):
        if idx is not None and np.linalg.norm(out[idx][1]-rest[1]) > 1e-6:
            report['refusals'].append({'frame': idx, 'reason': f'phone moved at {name}'})
    report['verified'] = False
    return out, report
