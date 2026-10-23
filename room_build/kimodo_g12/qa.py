"""Contact QA every 0.1 s: the v5 skin (retargeted clip) against the surfaces the MakeHuman body touches in the same clip.
Both bodies are skinned (linear blend) in the v5 rig's frame (the MakeHuman clip turned 90 deg about Y, as the retarget).
  floor   : lowest v5 sole point (m; < 0 = through the floor)
  slide   : planted feet: ankle drift during each contact (max, m); flagged above SLIDE_MAX_M
  seat    : seated frames: v5 lowest skin under the hips - the chair seat (0.505 m live chair; also vs the MH body's)
  bed     : lying frames: v5 lowest torso/limb skin - the mattress (the MH body's own lowest point there = the clip's mattress)
  hands   : v5 wrist - MH wrist (door handle, window sill, bed push)
  walk    : a walk clip (--walk): the reference foot speed, cycle time and stride length measured from its feet, with the
            foot slide and the loop seam (walk_metrics.py); the sidecar (--sidecar) carries them for the page
  seam    : a loop clip (--loop): the largest joint displacement between its last and first pose (m); flagged above
            SEAM_POP_MAX_M

Thresholds are the constants below (walk_metrics.py holds the walk ones).

python qa.py <json dir> <clip> <retargeted.json> [seat] [--loop] [--walk] [--sidecar OUT.json]
python qa.py --glb <clip.glb> <rig> [--anim NAME] [--sidecar OUT.json] [--meta IN.json]

Exit status 1 when a check fails; each failure is printed as a FAILED line."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import walk_metrics as W  # noqa: E402

CONTACT_TOL_M = W.CONTACT_ON_M      # a foot is in contact while its joint is within 1 cm of its floor
SLIDE_MAX_M = W.SLIDE_MAX_M         # a planted foot drifts at most 1 cm during a contact
SEAM_POP_MAX_M = W.SEAM_POP_MAX_M   # a loop's last pose is within 1 cm of its first
REF_TOL = W.REF_TOL                 # a sidecar's walk values agree with the clip within 5%
SEAT_DEFAULT = 0.505                # the desk chair's seat (m)
FPS = 30


def flag_list(summary, limits):
    """The failed checks of a summary: (name, text) for each value above its limit."""
    bad = []
    for name, limit in limits.items():
        v = summary.get(name)
        if v is not None and not np.isnan(v) and v > limit:
            bad.append((name, f"{v:.4f} > {limit:.4f}"))
    return bad


def print_failures(bad, label):
    for name, text in bad:
        print(f"FAILED {label}: {name} {text}")


def walk_check(times, joints, hips, sidecar_meta=None):
    """Measure a walk and, when a sidecar is given, compare its values within REF_TOL. Returns (measured, failures)."""
    m = W.measure_walk(times, joints, hips)
    fails = W.compare_meta(m, sidecar_meta, REF_TOL) if sidecar_meta else []
    return m, fails


def run_json(jdir, clip, outj, seat=SEAT_DEFAULT, loop=False, walk=False, sidecar=None):
    """The Kimodo path: the retargeted clip (outj) against its source (jdir/<clip>.json) and the MakeHuman body."""
    from rt import Skel, qrot, qmul, qy, FPS as RFPS
    from skinlib import mats, skin_setup, skin, seat_low, thigh_radius
    C = qy(np.pi / 2)
    v5 = json.load(open(Path(jdir) / 'v5.json')); rj = json.load(open(outj))
    ts = Skel(rj)
    an = rj['anims'][0]; dur = max(max(c['t']) for c in an['ch'])
    tq = np.arange(0, dur + 1e-6, 0.1); F = len(tq)
    Fs = int(round(dur * RFPS)) + 1
    T, R = ts.sample(an, Fs); fi = np.round(tq * RFPS).astype(int)
    P30, _, _ = ts.fk(T, R)                    # every frame at 30 fps (the walk and seam checks)
    T, R = T[fi], R[fi]
    P, Q, Sc = ts.fk(T, R)
    M = mats(P, Q, Sc)
    vn = [n['name'] for n in v5['nodes']]
    J, ibm, V, JI, WW = skin_setup(v5, 5)
    Jn = np.array([ts.ix[vn[j]] for j in J])
    X = skin(M, Jn, ibm, V, JI, WW)
    dom = np.array(vn)[J[JI[np.arange(len(JI)), WW.argmax(1)]]]
    sole = np.isin(dom, ['L_Foot', 'R_Foot', 'L_ToeBase', 'R_ToeBase'])
    seatv = np.isin(dom, ['L_Thigh', 'R_Thigh', 'L_ThighTwist01', 'R_ThighTwist01', 'L_ThighTwist02', 'R_ThighTwist02'])
    torso = ~np.isin(dom, ['L_Foot', 'R_Foot', 'L_ToeBase', 'R_ToeBase', 'L_Calf', 'R_Calf', 'L_CalfTwist01', 'R_CalfTwist01', 'L_CalfTwist02', 'R_CalfTwist02'])

    src = json.load(open(Path(jdir) / f'{clip}.json')); mh = json.load(open(Path(jdir) / 'mh_body.json'))
    ss = Skel(src); sT, sR = ss.sample(src['anims'][0], Fs); sT, sR = sT[fi], sR[fi]
    sP, sQ, sSc = ss.fk(sT, sR)
    sP = qrot(C, sP); sQ = qmul(np.broadcast_to(C, sQ.shape), sQ)
    sM = mats(sP, sQ, sSc)
    mn = [n['name'] for n in mh['nodes']]
    mh2 = dict(mh); mh2['mesh'] = mh['mesh'][:1]
    mJ, mibm, mV, mJI, mWW = skin_setup(mh2, 3)
    MHB = all(mn[j] in ss.ix for j in mJ)
    mJn = np.array([ss.ix[mn[j]] for j in mJ]) if MHB else None
    backv = np.isin(dom, ['Hip', 'Pelvis', 'Waist', 'Spine01'])
    mdom = np.array(mn)[mJ[mJI[np.arange(len(mJI)), mWW.argmax(1)]]]
    mback = np.array([d.startswith(('Hips', 'Spine02', 'spine04', 'Spine01', 'pelvis')) for d in mdom])
    Y = skin(sM, mJn, mibm, mV, mJI, mWW) if MHB else None

    _P0, _Q0, _S0 = ts.fk(ts.T[None], ts.R[None]); RTH = thigh_radius(skin(mats(_P0, _Q0, _S0), Jn, ibm, V, JI, WW)[0], _P0[0], ts.ix, dom)
    hipsY = sP[:, ss.ix['Hips'], 1]; headY = sP[:, ss.ix['Head'], 1]
    seated = (hipsY < 0.68) & (headY > 1.05)
    lying = headY < 1.0
    rows = []
    for f in range(F):
        x, y = X[f], (Y[f] if Y is not None else None)
        row = {'t': round(float(tq[f]), 1), 'floor': float(x[sole, 1].min())}
        if seated[f]:
            lo = seat_low(P[f], ts.ix, RTH)
            row['seat'] = lo - seat
            hv = P[f, ts.ix['Hip']]; beh = seatv & (np.linalg.norm(x[:, [0, 2]] - hv[[0, 2]], axis=1) < 0.12)
            row['buttock_sag'] = float(x[beh, 1].min() - seat)
        if lying[f] and Y is not None:
            row['bed_vs_mh'] = float(x[backv, 1].min() - y[mback, 1].min())
        for s, m in (('L', 'Left'), ('R', 'Right')):
            row[f'hand{s}'] = float(np.linalg.norm(P[f, ts.ix[f'{s}_Hand']] - sP[f, ss.ix[f'{m}Hand']]))
        rows.append(row)
    # sliding: ankle drift while the MH ankle is planted (low and still), the contact within CONTACT_TOL_M of its floor
    slide = 0.0
    for s, m in (('L', 'Left'), ('R', 'Right')):
        a = sP[:, ss.ix[f'{m}Foot']]; low = a[:, 1] < a[:, 1].min() + CONTACT_TOL_M
        v = np.r_[0, np.linalg.norm(np.diff(a[:, [0, 2]], axis=0), axis=1) / 0.1]; on = low & (v < 0.15)
        b = P[:, ts.ix[f'{s}_Foot']]
        f0 = None
        for f in range(F + 1):
            if f < F and on[f]: f0 = f if f0 is None else f0
            elif f0 is not None:
                if f - f0 >= 3: slide = max(slide, float(np.linalg.norm(b[f0:f, [0, 2]] - b[f0, [0, 2]], axis=1).max()))
                f0 = None
    summ = {'clip': clip, 'samples': F, 'floor_min': round(min(r['floor'] for r in rows), 3),
            'slide_max': round(slide, 3),
            'seat_min': round(min([r['seat'] for r in rows if 'seat' in r] or [np.nan]), 3), 'seat_max': round(max([r['seat'] for r in rows if 'seat' in r] or [np.nan]), 3),
            'buttock_sag_min': round(min([r['buttock_sag'] for r in rows if 'buttock_sag' in r] or [np.nan]), 3),
            'bed_vs_mh_min': round(min([r['bed_vs_mh'] for r in rows if 'bed_vs_mh' in r] or [np.nan]), 3),
            'bed_vs_mh_max': round(max([r['bed_vs_mh'] for r in rows if 'bed_vs_mh' in r] or [np.nan]), 3),
            'hand_err_max': round(max(max(r['handL'], r['handR']) for r in rows), 3)}
    fails = flag_list(summ, {'slide_max': SLIDE_MAX_M})
    if loop:
        seam = W.seam_pop(P30[0], P30[-1], P30[0, ts.ix['Hip']], P30[-1, ts.ix['Hip']])
        summ['seam_pop'] = seam
        fails += flag_list(summ, {'seam_pop': SEAM_POP_MAX_M})
    if walk:
        # the v5 joints are named L_Foot / L_ToeBase, R_Foot / R_ToeBase, and the hips Hip (walk_metrics.RIGS['v5'])
        joints = {side: {'Foot': P30[:, ts.ix[f'{side}_Foot']], 'ToeBase': P30[:, ts.ix[f'{side}_ToeBase']]} for side in ('L', 'R')}
        meta = json.load(open(sidecar)) if sidecar and Path(sidecar).exists() else None
        m, wf = walk_check(np.arange(Fs) / RFPS, joints, P30[:, ts.ix['Hip']], meta)
        summ['walk'] = m
        if sidecar and not Path(sidecar).exists():
            Path(sidecar).write_text(json.dumps(W.sidecar_from_measure(m, Path(outj).name, clip, 'v5'), indent=1) + '\n')
        fails += [('walk', msg) for msg in wf]
        fails += flag_list({'walk_slide': m['slideM'], 'walk_seam': m['seamFeetM']}, {'walk_slide': SLIDE_MAX_M, 'walk_seam': SEAM_POP_MAX_M})
    json.dump({'summary': summ, 'rows': rows}, open(outj.replace('.json', '_qa.json'), 'w'), indent=0)
    print(json.dumps(summ))
    print_failures(fails, clip)
    return 1 if fails else 0


def run_glb(path, rig, anim, sidecar_out, meta_in):
    """A walk GLB (no meshopt): measure it, write its sidecar, compare it with an existing one."""
    t, joints, hips = W.read_glb(path, rig, anim)
    m = W.measure_walk(t, joints, hips)
    print(json.dumps(m))
    meta = json.load(open(meta_in)) if meta_in else None
    fails = [('walk', msg) for msg in (W.compare_meta(m, meta, REF_TOL) if meta else [])]
    fails += flag_list({'slide': m['slideM'], 'seam_feet': m['seamFeetM']}, {'slide': SLIDE_MAX_M, 'seam_feet': SEAM_POP_MAX_M})
    if sidecar_out:
        Path(sidecar_out).write_text(json.dumps(W.sidecar(path, rig, anim), indent=1) + '\n')
    print_failures(fails, Path(path).name)
    return 1 if fails else 0


def main(argv):
    def opt(name, default=None):
        if name in argv:
            i = argv.index(name)
            val = argv[i + 1]
            del argv[i:i + 2]
            return val
        return default

    if '--glb' in argv:
        argv.remove('--glb')
        sidecar_out = opt('--sidecar'); meta_in = opt('--meta'); anim = opt('--anim')
        path, rig = argv[0], argv[1]
        return run_glb(path, rig, anim, sidecar_out, meta_in)
    loop = '--loop' in argv
    walk = '--walk' in argv
    argv = [a for a in argv if a not in ('--loop', '--walk')]
    sidecar = opt('--sidecar')
    jdir, clip, outj = argv[:3]
    seat = float(argv[3]) if len(argv) > 3 else SEAT_DEFAULT
    return run_json(jdir, clip, outj, seat, loop, walk, sidecar)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
