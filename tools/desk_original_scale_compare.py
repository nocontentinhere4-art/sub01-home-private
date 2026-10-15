import json, sys
import numpy as np
R = '/home/user/sub01-home-private/'
A_DIR, B_DIR = R + 'docs/proposed/ergonomic-layout-refit/', R + 'docs/proposed/desk-original-scale/chair-roll-7p702/'
T = {'elbow_above_top_cm': (0., 10.), 'upper_arm_deg': (-1e9, 20.), 'wrist_flexion_deg': (-15., 15.), 'wrist_deviation_deg': (-20., 10.)}
def stats(d):
    out = {}
    pf = json.load(open(d + 'per-frame.json'))
    for s in ('left', 'right'):
        rows = pf[s]
        o = {}
        for k in ('elbow_above_top_cm', 'upper_arm_deg', 'wrist_flexion_deg', 'wrist_deviation_deg', 'shoulder_elevation_deg'):
            v = np.array([r[k] for r in rows], float)
            o[k] = {'min': round(v.min(), 2), 'median': round(float(np.median(v)), 2), 'max': round(v.max(), 2)}
            if k in T:
                lo, hi = T[k]
                o[k]['in_target'] = f'{int(((v >= lo) & (v <= hi)).sum())}/{len(v)}'
                o[k]['in_target_pct'] = round(100 * float(((v >= lo) & (v <= hi)).mean()), 1)
        ok = np.ones(len(rows), bool)
        for k, (lo, hi) in T.items():
            v = np.array([r[k] for r in rows], float); ok &= (v >= lo) & (v <= hi)
        o['all_four_in_target_pct'] = round(100 * float(ok.mean()), 1)
        out[s] = o
    return out
res = {'targets': {k: list(v) for k, v in T.items()}, 'scale_1p086_9f4e199': stats(A_DIR), 'scale_1p0_desk_original_scale': stats(B_DIR)}
json.dump(res, open(sys.argv[1], 'w'), indent=1)
lines = ['| metric | side | 9f4e199 (scale 1.086, top 84.5) min / median / max [in target] | original scale (1.0, top 78.0) min / median / max [in target] |', '|---|---|---|---|']
for k in ('elbow_above_top_cm', 'upper_arm_deg', 'wrist_flexion_deg', 'wrist_deviation_deg', 'shoulder_elevation_deg'):
    for s in ('left', 'right'):
        a, b = res['scale_1p086_9f4e199'][s][k], res['scale_1p0_desk_original_scale'][s][k]
        f = lambda x: f"{x['min']} / {x['median']} / {x['max']}" + (f" [{x['in_target']} = {x['in_target_pct']}%]" if 'in_target' in x else '')
        lines.append(f'| {k} | {s} | {f(a)} | {f(b)} |')
for s in ('left', 'right'):
    lines.append(f"| all four in target | {s} | {res['scale_1p086_9f4e199'][s]['all_four_in_target_pct']}% | {res['scale_1p0_desk_original_scale'][s]['all_four_in_target_pct']}% |")
open(sys.argv[2], 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
