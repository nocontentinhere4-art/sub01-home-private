"""Bed placement fitter (pure Python + numpy; a PROPOSAL, never verification).

    python3 tools/fit_bed_placement.py BED_SURFACE.json CLIP.glb [--time S | --frame K] [--head-margin-cm 25]
        [--approach-side left|right] [--owner web/room/char_mixamo.glb] [--out PLACEMENT.json]

Given the measured mattress top (tools/unreal_bed_surface_audit.py -> native-bed-surface.json) and a lying frame of
an owner-skeleton clip (e.g. the LieDown output of tools/bed_transition_pipeline.py at its last frame), compute the
rigid body transform (yaw about vertical + translation) that would put the lying body's fixed support patches on the
mattress, by the seat contact rule of tools/validate_unreal_seat_contact.py (imported, not edited):
  * every patch is a LOCAL SUPPORT PATCH: its lowest vertex within SEAT_BAND_CM of the surface (touching, at most the
    band's compression), and at least MIN_SUPPORT_VERTICES patch vertices inside the band;
  * at least MIN_PATCH_VERTICES patch vertices are over the mattress footprint;
  * non-penetration: no skin vertex over the mattress is deeper than the band's lower edge.
Patch membership is a FIXED bind-space selection (never a per-pose minimum): posterior-facing skin (bind normal .
-forward > 0.7) dominated by the torso joints ("torso_back": Hips, Spine, Spine1, Spine2), by the thighs and shins
("posterior_legs") and by the head/neck ("head_back"); for a side-lying frame the lateral selections are used instead.

Frames. Body points are in the mesh component frame, Z up, cm: X = the owner's rest forward (+Z glTF), Y = the
owner's rest right (-X glTF), Z = up (+Y glTF), i.e. UE character-local axes. Mattress triangles are UE world cm.
The result maps component points to world: p_world = Rz(yaw) p + t. The mesh component's relative transform to the
actor (capsule offset, any -90 deg mesh yaw) is NOT known here and must be taken from the live character.

Output: 'accepted': False and 'native_bed_verified': False always. Only the server placement audit (imported clips
played at the proposed approach, skin measured against this exact bed report) may write native-life-bed-evidence.json.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import validate_unreal_seat_contact as C  # noqa: E402  (read-only: SEAT_BAND_CM, MIN_PATCH_VERTICES, MIN_SUPPORT_VERTICES)
from unreal_life_clips_runtime import MIN_MATTRESS_AREA_CM2, life_id, mattress_area_cm2, mattress_triangles  # noqa: E402

SCHEMA = 'sub01.bed-placement-proposal.v1'
BAND_CM = C.SEAT_BAND_CM                 # (-2.5, +0.5): touching to the cushion's allowed compression
MIN_PATCH_VERTICES = C.MIN_PATCH_VERTICES
MIN_SUPPORT_VERTICES = C.MIN_SUPPORT_VERTICES
HEAD_MARGIN_CM = 25.0                    # head top this far inside the head edge (pillow zone); a stated default
PATCH_JOINTS = {
    'torso_back': ('Hips', 'Spine', 'Spine1', 'Spine2'),
    'posterior_legs': ('LeftUpLeg', 'RightUpLeg', 'LeftLeg', 'RightLeg'),
    'head_back': ('Neck', 'Head'),
}
GATED_PATCHES = ('torso_back',)                    # THE lying back (or side) support patch, gated on the mattress top
INFO_PATCHES = ('posterior_legs', 'head_back')     # reported, not gated: knees may be up; the head rests on the pillow
NORMAL_MIN = 0.7


# ------------------------------------------------------------------ geometry
def triangles_array(tris_flat):
    t = np.asarray(tris_flat, dtype=float).reshape(-1, 3, 3)
    if not np.isfinite(t).all():
        raise ValueError('BedUnmeasured: nonfinite mattress triangle')
    return t


def surface_height(points_xy, tris):
    """Highest mattress-top height under each XY point (nan where no triangle covers it)."""
    p = np.asarray(points_xy, float)
    out = np.full(len(p), np.nan)
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    v0, v1 = (b - a)[:, :2], (c - a)[:, :2]
    den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
    ok = np.abs(den) > 1e-12
    for s in range(0, len(p), 4096):
        q = p[s:s + 4096]
        v2 = q[:, None, :] - a[None, :, :2]
        u = (v2[..., 0] * v1[None, :, 1] - v1[None, :, 0] * v2[..., 1]) / np.where(ok, den, 1)[None]
        w = (v0[None, :, 0] * v2[..., 1] - v2[..., 0] * v0[None, :, 1]) / np.where(ok, den, 1)[None]
        inside = ok[None] & (u >= -1e-9) & (w >= -1e-9) & (u + w <= 1 + 1e-9)
        z = a[None, :, 2] + u * (b - a)[None, :, 2] + w * (c - a)[None, :, 2]
        z = np.where(inside, z, -np.inf)
        best = z.max(axis=1)
        out[s:s + 4096] = np.where(np.isfinite(best), best, np.nan)
    return out


def mattress_frame(tris, head_dir=None):
    """Centroid, long axis (unit XY, toward the head end when head_dir is given) and extents.
    Exact area second moments of the triangles (repeated vertices do not bias the axis)."""
    e1, e2 = tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]
    area = 0.5 * np.linalg.norm(np.cross(e1, e2), axis=1)
    cent = tris.mean(axis=1)[:, :2]
    c = (cent * area[:, None]).sum(0) / area.sum()
    d = tris[:, :, :2] - c                                         # (T,3,2)
    s = d.sum(axis=1)                                              # (T,2)
    cov = np.einsum('t,tij->ij', area / 12, np.einsum('tvi,tvj->tij', d, d) + np.einsum('ti,tj->tij', s, s))
    vals, vecs = np.linalg.eigh(cov)
    ax = vecs[:, int(np.argmax(vals))]
    if head_dir is not None and float(np.dot(ax, head_dir)) < 0:
        ax = -ax
    lat = np.array([-ax[1], ax[0]])
    pts = tris.reshape(-1, 3)[:, :2] - c
    along, across = pts @ ax, pts @ lat
    return {'centroid': c, 'axis': ax, 'lateral': lat, 'head_edge': float(along.max()), 'foot_edge': float(along.min()),
            'half_width': [float(across.min()), float(across.max())], 'area_cm2': float(area.sum())}


def rotz(yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


# ------------------------------------------------------------------ the fit
def fit(body_points, patches, head_top, hips, tris_flat, head_dir=None, head_margin_cm=HEAD_MARGIN_CM,
        lateral_offset_cm=0.0, start_hips=None, approach_side=None, info_patches=None):
    """Propose the component->world transform for a lying frame.

    body_points: (N,3) all skinned vertices (component frame, cm). patches: {name: (M,3)}.
    head_top, hips: (3,) joints of the same frame. tris_flat: mattress triangles (world cm, flat list of 3*T points).
    start_hips: optional (3,) hips at the clip's first frame (standing), to check the approach side.
    """
    tris = triangles_array(tris_flat)
    area = mattress_area_cm2([list(p) for p in tris.reshape(-1, 3)])
    out = {'schema': SCHEMA, 'accepted': False, 'native_bed_verified': False, 'band_cm': list(BAND_CM),
           'rule': 'tools/validate_unreal_seat_contact.py: local support patch + non-penetration (constants imported)',
           'mattress_area_cm2': round(area, 3), 'refusals': [], 'proposal_ok': False, 'transform': None}
    if area < MIN_MATTRESS_AREA_CM2:
        out['refusals'].append(f'BedUnmeasured: mattress area {area:.0f} cm2 < {MIN_MATTRESS_AREA_CM2:.0f} cm2')
        return out
    mf = mattress_frame(tris, None if head_dir is None else np.asarray(head_dir, float))
    if head_dir is None:
        out['refusals'].append('head end direction unknown (the bed report has no pillow-derived head_end_direction_xy)')
        return out
    body = np.asarray(body_points, float)
    head_top, hips = np.asarray(head_top, float), np.asarray(hips, float)
    long_body = (head_top - hips)[:2]
    if np.linalg.norm(long_body) < 20:
        out['refusals'].append('the frame is not lying: hips->head horizontal extent < 20 cm')
        return out
    yaw = math.atan2(mf['axis'][1], mf['axis'][0]) - math.atan2(long_body[1], long_body[0])
    Rz = rotz(yaw)
    rot = lambda p: np.asarray(p) @ Rz.T  # noqa: E731
    # along: head top at head_margin inside the head edge; across: support patches centred (+ offset)
    sup = np.concatenate([np.asarray(v, float) for v in patches.values()]) if patches else body
    sup_c = rot(sup)[:, :2].mean(0)
    ht = rot(head_top)[:2]
    along_shift = (mf['head_edge'] - head_margin_cm) - float((ht - mf['centroid']) @ mf['axis'])
    centre = 0.5 * (mf['half_width'][0] + mf['half_width'][1]) + lateral_offset_cm
    across_shift = centre - float((sup_c - mf['centroid']) @ mf['lateral'])
    # p_world_xy = rot(p)_xy + t: the head top lands head_margin inside the head edge, the patches centred across
    t = np.zeros(3)
    t[:2] = along_shift * mf['axis'] + across_shift * mf['lateral']
    # vertical: the patches' lowest gaps at dz = 0
    gaps0, over = {}, {}
    for name, pts in patches.items():
        w = rot(np.asarray(pts, float)) + t
        z = surface_height(w[:, :2], tris)
        g = w[:, 2] - z
        over[name] = int(np.isfinite(z).sum())
        gaps0[name] = g
    wb = rot(body) + t
    zb = surface_height(wb[:, :2], tris)
    gb = wb[:, 2] - zb
    over_body = np.isfinite(zb)
    low, high = BAND_CM
    lo, hi, binding = -math.inf, math.inf, {}
    for name, g in gaps0.items():
        if over[name] < MIN_PATCH_VERTICES:
            out['refusals'].append(f'{name}: only {over[name]} patch vertices over the mattress (< {MIN_PATCH_VERTICES})')
            continue
        if over[name] < len(g):
            out['refusals'].append(f'{name}: {len(g) - over[name]} of {len(g)} support-patch vertices hang off the mattress '
                                   '(the patch is not over its surface)')
        gmin = float(np.nanmin(g))  # over the mattress only
        if low - gmin > lo:
            lo, binding['lower'] = low - gmin, name
        if high - gmin < hi:
            hi, binding['upper'] = high - gmin, name
    if over_body.any():
        body_lo = low - float(np.nanmin(gb[over_body]))
        if body_lo > lo:
            lo, binding['lower'] = body_lo, 'whole_body_non_penetration'
    patch_rows = {}
    if out['refusals']:
        dz = None
    elif lo > hi:
        dz = None
        out['refusals'].append(f'patches disagree: the vertical range is empty ({lo:.2f} > {hi:.2f} cm, bound by '
                               f'{binding}); the lying pose does not rest on this flat top (pose, not translation)')
    else:
        # within the allowed range, the vertical with the most support (max of the smallest per-patch band count);
        # ties go to the least compression (highest dz). Scanned at 0.05 cm.
        cands = np.unique(np.append(np.arange(hi, lo - 1e-9, -0.05), lo))[::-1]
        best = None
        for d in cands:
            counts = [int(((g + d >= low - 1e-9) & (g + d <= high + 1e-9)).sum()) for g in gaps0.values()]
            score = min(counts) if counts else 0
            if best is None or score > best[0]:
                best = (score, float(d))
        dz = best[1]
        t[2] = dz
        for name, g in gaps0.items():
            gg = g + dz
            band = int(((gg >= low - 1e-9) & (gg <= high + 1e-9)).sum())
            patch_rows[name] = {'over_mattress_vertices': over[name], 'min_gap_cm': round(float(np.nanmin(gg)), 4),
                                'median_gap_cm': round(float(np.nanmedian(gg)), 4), 'band_vertices': band,
                                'pass': band >= MIN_SUPPORT_VERTICES}
            if band < MIN_SUPPORT_VERTICES:
                out['refusals'].append(f'{name}: {band} vertices within the band (< {MIN_SUPPORT_VERTICES}): point contact, '
                                       'not a support patch')
    info_rows = {}
    for name, pts in (info_patches or {}).items():
        w = rot(np.asarray(pts, float)) + t
        z = surface_height(w[:, :2], tris)
        g = w[:, 2] - z
        info_rows[name] = {'over_mattress_vertices': int(np.isfinite(z).sum()),
                           'min_gap_to_mattress_cm': None if not np.isfinite(z).any() else round(float(np.nanmin(g)), 4),
                           'gated': False,
                           'why': ('rests on the pillow; the pillow top is not measured' if name.startswith('head')
                                   else 'legs may be bent (knees up) in a captured lying pose; reported only')}
    wb2 = rot(body) + t
    along_b = (wb2[:, :2] - mf['centroid']) @ mf['axis']
    across_b = (wb2[:, :2] - mf['centroid']) @ mf['lateral']
    overhang = {'past_head_edge_cm': round(float(max(0.0, along_b.max() - mf['head_edge'])), 3),
                'past_foot_edge_cm': round(float(max(0.0, mf['foot_edge'] - along_b.min())), 3),
                'past_sides_cm': [round(float(max(0.0, mf['half_width'][0] - across_b.min())), 3),
                                  round(float(max(0.0, across_b.max() - mf['half_width'][1])), 3)],
                'vertices_not_over_mattress': int((~over_body).sum())}
    approach = None
    if start_hips is not None:
        s = rot(np.asarray(start_hips, float)) + t
        a_s = float((s[:2] - mf['centroid']) @ mf['axis'])
        l_s = float((s[:2] - mf['centroid']) @ mf['lateral'])
        if a_s < mf['foot_edge']:
            side = 'foot_end'
        elif a_s > mf['head_edge']:
            side = 'head_end'
        else:
            side = 'left' if l_s < mf['half_width'][0] else ('right' if l_s > mf['half_width'][1] else 'over_mattress')
        approach = {'floor_frame_hips_world_cm': [round(float(v), 3) for v in s], 'side': side,
                    'distance_from_edge_cm': round(float(min(abs(l_s - mf['half_width'][0]), abs(l_s - mf['half_width'][1]))), 3),
                    'along_axis_cm': round(a_s, 3),
                    'side_convention': 'left/right of the mattress long axis looking toward the head end; foot_end / '
                                       'head_end beyond the ends (hips position only; the feet are not checked)'}
        if side == 'over_mattress':
            out['refusals'].append('the clip\'s floor frame (standing beside the bed) lands over the mattress')
        elif approach_side and side != approach_side:
            out['refusals'].append(f'the clip approaches from the {side} side; the requested approach is {approach_side}')
    out.update({
        'transform': {'yaw_deg': round(math.degrees(yaw), 4), 'translation_cm': [round(float(v), 4) for v in t],
                      'maps': 'p_world = Rz(yaw) p_component + translation (UE Z-up cm)'} if dz is not None else None,
        'vertical_range_cm': [round(lo, 4), round(hi, 4)], 'chosen_vertical_cm': None if dz is None else round(dz, 4),
        'vertical_rule': 'every patch lowest within the band and no skin deeper than its lower edge; inside that range '
                         'the most support (smallest per-patch band count maximised), ties to the least compression',
        'binding': binding, 'patches': patch_rows,
        'reported_not_gated': info_rows,
        'body_min_gap_over_mattress_cm': None if dz is None or not over_body.any() else round(float(np.nanmin(gb[over_body]) + dz), 4),
        'overhang': overhang, 'approach': approach,
        'mattress': {'centroid_cm': [round(float(v), 3) for v in mf['centroid']], 'long_axis_toward_head': [round(float(v), 6) for v in mf['axis']],
                     'head_edge_cm': round(mf['head_edge'], 3), 'foot_edge_cm': round(mf['foot_edge'], 3),
                     'lateral_extent_cm': [round(v, 3) for v in mf['half_width']]},
        'head_margin_cm': head_margin_cm, 'lateral_offset_cm': lateral_offset_cm,
        'proposal_ok': not out['refusals'] and dz is not None,
    })
    return out


# ------------------------------------------------------------------ the owner's skin at a clip frame
def skinned_frame(clip_glb: Path, owner_glb: Path, time_s=None, frame=None, work=None):
    """All owner skin vertices and the fixed support patches at one frame, in the component frame (cm, Z up)."""
    import life_gltf as G
    import verify_life_idle_candidate as V
    work = Path(work or Path(clip_glb).parent)
    owner_d = G.Gltf(V.decoded(Path(owner_glb), work))
    owner = V.Owner(G.Gltf(owner_glb))
    doc = owner_d.doc
    skin = doc['skins'][0]
    ibm = np.array(owner_d.accessor(skin['inverseBindMatrices'])).reshape(-1, 4, 4).transpose(0, 2, 1)
    names = [V.canonical(doc['nodes'][j]['name']) for j in skin['joints']]
    pos, nrm, jts, wts, seen = [], [], [], [], set()
    for node in doc['nodes']:
        if 'mesh' not in node or node.get('skin') != 0 or node['mesh'] in seen:
            continue
        seen.add(node['mesh'])
        for prim in doc['meshes'][node['mesh']]['primitives']:
            a = prim['attributes']
            pos.append(np.array(owner_d.accessor(a['POSITION'])))
            nrm.append(np.array(owner_d.accessor(a['NORMAL'])))
            jts.append(np.array(owner_d.accessor(a['JOINTS_0'])).astype(int))
            wts.append(np.array(owner_d.accessor(a['WEIGHTS_0'])))
    pos, nrm, jts, wts = (np.concatenate(x) for x in (pos, nrm, jts, wts))
    g = G.Gltf(clip_glb)
    cand = V.Candidate(g, owner)
    times = cand.times()
    t = times[frame] if frame is not None else (times[-1] if time_s is None else time_s)
    w = G.world_pose(g, cand.clip, t)
    mats = np.zeros((len(names), 4, 4))
    for k, n in enumerate(names):
        wt = w[cand.node[n]]
        mats[k] = V.trs_matrix(wt[0], wt[1], wt[2]) @ ibm[k]
    homog = np.hstack([pos, np.ones((len(pos), 1))])
    sk_pos = np.zeros((len(pos), 4))
    for k in range(4):
        sk_pos += wts[:, k:k + 1] * np.einsum('nij,nj->ni', mats[jts[:, k]], homog)
    rest = G.world_pose(owner.gltf, G.RestPose, 0)
    right = np.array(rest[owner.node['RightUpLeg']][0]) - np.array(rest[owner.node['LeftUpLeg']][0])
    right[1] = 0
    right /= np.linalg.norm(right)
    up = np.array([0.0, 1.0, 0.0])
    fwd = np.cross(up, right)

    def comp(p):                                    # glTF metres -> component (forward, right, up) cm
        p = np.asarray(p, float)
        return np.stack([p @ fwd, p @ right, p @ up], axis=-1) * 100
    dominant = np.array([names[j[np.argmax(wv)]] for j, wv in zip(jts, wts)])
    # fixed bind-space selections
    back = nrm @ (-fwd) > NORMAL_MIN
    left = nrm @ (-right) > NORMAL_MIN
    rightn = nrm @ right > NORMAL_MIN
    sel = {}
    for name, joints in PATCH_JOINTS.items():
        dom = np.isin(dominant, joints)
        sel[name] = dom & back
        sel[name + '_left_side'] = dom & left
        sel[name + '_right_side'] = dom & rightn
    body = comp(sk_pos[:, :3])
    joints = {n: comp(w[cand.node[n]][0]) for n in ('Hips', 'Head', 'HeadTop_End') if n in cand.node}
    first = G.world_pose(g, cand.clip, times[0], [cand.node['Hips']])
    last = G.world_pose(g, cand.clip, times[-1], [cand.node['Hips']])
    return {'time_s': t, 'body': body, 'patches_all': {k: body[v] for k, v in sel.items()},
            'patch_counts': {k: int(v.sum()) for k, v in sel.items()}, 'joints': joints,
            'start_hips': comp(first[cand.node['Hips']][0]), 'end_hips': comp(last[cand.node['Hips']][0]),
            'vertices': int(len(body))}


def support_triangles(bed: dict, support='mattress'):
    """The measured support: the mattress top, or (support='duvet') the audit's measured duvet top sections."""
    if support == 'mattress':
        return mattress_triangles(bed)
    sections = [{'vertices_world_cm': d['vertices_world_cm'], 'mattress_surface': d['top_surface']}
                for d in bed.get('duvet_sections', []) if d.get('top_surface') and d.get('vertices_world_cm')]
    if not sections:
        raise ValueError('BedUnmeasured: no measured duvet top in the bed report (re-run unreal_bed_surface_audit.py)')
    return mattress_triangles({'errors': bed.get('errors'), 'bed': {'sections': sections}})


def patches_for(frame_data, lying='supine', names=GATED_PATCHES):
    suffix = {'supine': '', 'side_left': '_left_side', 'side_right': '_right_side'}[lying]
    return {k: frame_data['patches_all'][k + suffix] for k in names}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('bed', type=Path)
    ap.add_argument('clip', type=Path)
    ap.add_argument('--owner', type=Path, default=ROOT / 'web/room/char_mixamo.glb')
    ap.add_argument('--time', type=float)
    ap.add_argument('--frame', type=int)
    ap.add_argument('--lying', default='supine', choices=('supine', 'side_left', 'side_right'))
    ap.add_argument('--head-margin-cm', type=float, default=HEAD_MARGIN_CM)
    ap.add_argument('--lateral-offset-cm', type=float, default=0.0)
    ap.add_argument('--approach-side', choices=('left', 'right'))
    ap.add_argument('--floor-frame', default='first', choices=('first', 'last', 'none'),
                    help='the clip frame that must stand on the floor beside the bed: first (LieDown), last (GetUp)')
    ap.add_argument('--support', default='mattress', choices=('mattress', 'duvet'),
                    help='duvet: fit the back patch onto the measured duvet top (if the duvet stays visible in sleep)')
    ap.add_argument('--work', type=Path)
    ap.add_argument('--out', type=Path)
    args = ap.parse_args(argv)
    text = args.bed.read_text()
    bed = json.loads(text)
    tris = support_triangles(bed, args.support)
    head = None
    for section in bed['bed']['sections']:
        head = section.get('mattress_surface', {}).get('head_end_direction_xy') or head
    f = skinned_frame(args.clip, args.owner, args.time, args.frame, args.work)
    floor = {'first': f['start_hips'], 'last': f['end_hips'], 'none': None}[args.floor_frame]
    res = fit(f['body'], patches_for(f, args.lying), f['joints']['HeadTop_End'], f['joints']['Hips'], tris, head,
              args.head_margin_cm, args.lateral_offset_cm, floor, args.approach_side,
              info_patches=patches_for(f, args.lying, INFO_PATCHES))
    res.update({'support': args.support, 'floor_frame_checked': args.floor_frame, 'bed_report': str(args.bed), 'bed_revision': str(life_id(text)), 'clip': str(args.clip),
                'clip_time_s': f['time_s'], 'lying': args.lying, 'patch_counts': f['patch_counts'],
                'component_to_actor': 'UNKNOWN here: take the live mesh component relative transform before writing an approach'})
    s = json.dumps(res, indent=1, sort_keys=True) + '\n'
    if args.out:
        args.out.write_text(s)
    print(s if not args.out else json.dumps({'proposal_ok': res['proposal_ok'], 'refusals': res['refusals']}))
    return 0 if res['proposal_ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
