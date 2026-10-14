"""Owner skeleton parity between the 65-joint GLB skin and the native UE skeleton.

The native USkeleton has 66 bones: the 65 skin joints plus one structural, parentless Mixamo
node above the hips. A raw count of 66 is therefore not a mismatch. Parity is proven instead:

  * every one of the owner's 65 semantic joints exists, with exactly the owner's parent;
  * at most one extra bone, which is the single parentless root and the parent of the owner's
    root joint(s);
  * that structural root has a constant transform at the sampled clip times (0, 3 and 8 s,
    clamped to the clip), so it carries no motion of its own.

Pure Python; tools/unreal_import_life_fbx.py feeds it the imported skeleton and clip samples.
"""
from __future__ import annotations

import math

SAMPLE_TIMES_S = (0.0, 3.0, 8.0)
TRANSLATION_TOLERANCE_CM = 1e-3
ROTATION_TOLERANCE_DEG = 1e-3
SCALE_TOLERANCE = 1e-6


def sample_times(duration_s: float) -> list[float]:
    """The fixed sample times, clamped into the clip; duplicates removed in order."""
    out = []
    for t in SAMPLE_TIMES_S:
        clamped = min(max(t, 0.0), duration_s)
        if not out or abs(out[-1] - clamped) > 1e-9:
            out.append(clamped)
    return out


def _angle_deg(a, b) -> float:
    dot = abs(sum(x * y for x, y in zip(a, b)))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if not na or not nb:
        return math.inf
    return math.degrees(2 * math.acos(min(1.0, dot / (na * nb))))


def structural_root_parity(ue_names, ue_parents, owner_parents, root_samples=()):
    """Prove the UE skeleton is the owner skeleton (plus at most one constant structural root).

    ue_names: bone names in the UE skeleton. ue_parents: name -> parent name, or None.
    owner_parents: the owner's 65 skin joints, name -> parent name or None.
    root_samples: [(time_s, translation_cm(3), rotation_xyzw(4), scale(3))] for the
    structural root at sample_times(); required when the UE skeleton has an extra bone.
    Returns {'pass': bool, 'failures': [...], 'structural_root': name or None, ...}.
    """
    failures = []
    names = list(ue_names)
    semantic = set(owner_parents)
    if len(names) != len(set(names)):
        failures.append('duplicate UE bone names')
    missing = sorted(semantic - set(names))
    if missing:
        failures.append(f'missing owner joints: {missing}')
    extra = [n for n in names if n not in semantic]
    roots = [n for n in names if ue_parents.get(n) in (None, '', 'None')]
    structural = None
    if len(extra) > 1:
        failures.append(f'more than one non-owner bone: {extra}')
    elif extra:
        structural = extra[0]
        if roots != [structural]:
            failures.append(f'structural bone {structural} must be the only parentless bone (roots {roots})')
    owner_roots = [n for n, p in owner_parents.items() if p is None]
    for name, parent in sorted(owner_parents.items()):
        if name not in ue_parents:
            continue
        got = ue_parents.get(name)
        got = None if got in ('', 'None') else got
        expected = structural if parent is None else parent
        if got != expected:
            failures.append(f'{name}: UE parent {got!r}, owner parent {expected!r}')
    if structural:
        if len(root_samples) < 2:
            failures.append('structural root needs transform samples at the fixed times')
        else:
            t0, p0, q0, s0 = root_samples[0]
            for t, p, q, s in root_samples[1:]:
                move = math.dist(p, p0)
                turn = _angle_deg(q, q0)
                grow = max(abs(a - b) for a, b in zip(s, s0))
                if move > TRANSLATION_TOLERANCE_CM or turn > ROTATION_TOLERANCE_DEG or grow > SCALE_TOLERANCE:
                    failures.append(f'structural root {structural} moves between {t0:g}s and {t:g}s '
                                    f'({move:.6f} cm, {turn:.6f} deg, scale {grow:.2e})')
    return {'pass': not failures, 'failures': failures, 'structural_root': structural,
            'ue_bone_count': len(names), 'owner_joint_count': len(semantic), 'owner_roots': owner_roots,
            'sampled_times_s': [r[0] for r in root_samples]}
