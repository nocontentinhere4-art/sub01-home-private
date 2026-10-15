"""Exact desk-item transforms for the original-scale LINEA140 (scale 1.0), from the scale-1 geometry and the recorded
root placements. Usage: python tools/desk_original_scale_items.py <proposal.json> <out.json>"""
import json, sys, itertools
from pathlib import Path
R = str(Path(__file__).resolve().parents[1]) + '/'
S = (.845 - .025) / .755
g = json.load(open(R + 'docs/proposed/desk-original-scale/real-linea140-geometry-scale1.json'))
g0 = json.load(open(R + 'docs/proposed/seated-typing-ik/real-linea140-geometry.json'))
prop = json.load(open(sys.argv[1]))
slab = g['tabletop_slab']; top = slab['top_cm']; top0 = g0['tabletop_slab']['top_cm']
DROP = top - top0                      # -6.5
lo, hi = slab['min_cm'][:2], slab['max_cm'][:2]
def margins(box):
    (x0, y0), (x1, y1) = box
    return {'front_cm': round(hi[1] - y1, 4), 'rear_cm': round(y0 - lo[1], 4), 'left_cm': round(x0 - lo[0], 4), 'right_cm': round(hi[0] - x1, 4)}
def ue_box(w, d, x, z):   # home.js box w (x) d (three z) at (x, z): UE plan box
    return [[round((x - w / 2) * 100, 4), round((z - d / 2) * 100, 4)], [round((x + w / 2) * 100, 4), round((z + d / 2) * 100, 4)]]
LIFT = 2.499999824837346            # origin/main monitor-support-fix-20261015.json derived_delta_z_cm
MON_DX = 4.0                        # +4 cm UE X: the panel's left edge (x 164) would overlap the scale-1 grommet rim in plan
                                    # (x <= 165.53, y >= -326.53 after the +2 Y move); +4 keeps the lamp pole 3.8 cm clear (root scale: 3.86)
MON_DY = 2.0                        # minimal plan move: the stand foot (depth .09) rear edge sits exactly on the scale-1
                                    # rear edge (-334.5); +2.0 cm UE Y (toward the body) gives the 2 cm flat-top margin
items = {}
stand_bottom0 = (0.88 - 0.06) * 100 + LIFT          # 84.4999998 (support fix)
dz_mon = top - stand_bottom0                         # -> stand bottom exactly on 78.0
items['monitor_stand'] = {'home_js_main': 'box(0.12, 0.12, 0.09, 2, 0.88, -3.3, M.metal, 0.005)', 'support_fix_dz_cm': LIFT,
    'delta_ue_cm': [MON_DX, MON_DY, dz_mon], 'delta_vs_main_home_js_three_m': [MON_DX / 100, round((LIFT + dz_mon) / 100, 9), MON_DY / 100],
    'proposed_home_js': f'box(0.12, 0.12, 0.09, {2 + MON_DX / 100:.2f}, {0.88 + (LIFT + dz_mon) / 100:.9f}, {-3.3 + MON_DY / 100:.4f}, M.metal, 0.005)',
    'bottom_cm': round(stand_bottom0 + dz_mon, 9), 'plan_cm': ue_box(.12, .09, 2 + MON_DX / 100, -3.3 + MON_DY / 100)}
items['monitor_frame'] = {'home_js_main': 'box(0.72, 0.44, 0.035, 2, 1.16, -3.3, M.black, 0.025)', 'delta_ue_cm': [MON_DX, MON_DY, dz_mon],
    'proposed_home_js': f'box(0.72, 0.44, 0.035, {2 + MON_DX / 100:.2f}, {1.16 + (LIFT + dz_mon) / 100:.9f}, {-3.3 + MON_DY / 100:.4f}, M.black, 0.025)',
    'screen_plane_home_js': f'screen.position.set({2 + MON_DX / 100:.2f}, {1.16 + (LIFT + dz_mon) / 100:.9f}, {-3.276 + MON_DY / 100:.4f})',
    'plan_cm': ue_box(.72, .035, 2 + MON_DX / 100, -3.3 + MON_DY / 100)}
# clamp lamp: root mount on the grommet rim (node 35) of the scaled desk; the lamp itself is not rescaled, so it follows
# the grommet centre: delta = (grommet centre at 1.0) - (at S) in plan, and the top drop in Z.
import subprocess
lamp = json.loads(subprocess.run(['git', '-C', R, 'show', 'origin/main:docs/proposed/real-linea-grommet-lamp-mount-20261014.json'], check=True, capture_output=True).stdout)
rim = next(p for p in g['parts'] if p['node'] == 35); rim0 = next(p for p in g0['parts'] if p['node'] == 35)
c1 = [(rim['min_cm'][a] + rim['max_cm'][a]) / 2 for a in range(2)]; c0 = [(rim0['min_cm'][a] + rim0['max_cm'][a]) / 2 for a in range(2)]
# exact centre move about the desk centre (210, -302): (c - centre) * (1 - S)
ex = [(c1[0] - 210.) * (1 - S), (c1[1] + 302.) * (1 - S)]
dl = [ex[0], ex[1], DROP]
items['clamp_lamp'] = {'record': 'origin/main docs/proposed/real-linea-grommet-lamp-mount-20261014.json',
    'old_origin_ue_cm': lamp['new_origin_ue_cm'], 'delta_ue_cm': dl,
    'new_origin_ue_cm': [lamp['new_origin_ue_cm'][a] + dl[a] for a in range(3)],
    'old_bulb_ue_cm': lamp['new_bulb_ue_cm'], 'new_bulb_ue_cm': [lamp['new_bulb_ue_cm'][a] + dl[a] for a in range(3)],
    'yaw_deg': 90, 'scale': 'unchanged (lamp source not rescaled)',
    'new_world_aabb_cm': [[lamp['lamp_world_aabb_m'][k][a] * 100 + dl[a] for a in range(3)] for k in (0, 1)],
    'grommet_rim_centre_scale1_cm': c1, 'grommet_rim_centre_root_scale_cm': c0,
    'note': 'radial pin clearance and contact tolerance unchanged (rigid move with the grommet); the native collision proof is root\'s'}
items['grommet'] = {'source_nodes': [7, 8, 35], 'moves_with_desk_scale': True,
    'rim_node35_aabb_cm': [rim['min_cm'], rim['max_cm']], 'rim_top_cm': rim['max_cm'][2], 'centre_xy_cm': c1,
    'root_scale_rim_aabb_cm': [rim0['min_cm'], rim0['max_cm']]}
items['phone'] = {'home_js_main': 'box(0.075, 0.015, 0.15, 2.7, 0.858, -2.92, M.black, 0.014) (+ its speaker/volume/power boxes)',
    'delta_ue_cm': [0.0, 0.0, DROP], 'plan_cm': ue_box(.075, .15, 2.7, -2.92), 'note': 'rigid -6.5 cm with every phone part (keeps main\'s bottom-to-top relation)'}
cfg = prop.get('configuration') or prop.get('proposed')
dev = prop.get('devices', {})
if cfg:
    items['keyboard'] = {'delta_ue_cm': cfg['keyboard']['delta_ue_cm'], 'proposed_home_js': cfg['keyboard']['proposed_home_js'],
                         'proposed_three_m': cfg['keyboard']['proposed_three_m'], 'plan_cm': [d[:2] for d in dev['keyboard']['footprint_cm']],
                         'bottom_cm': dev['keyboard']['bottom_cm'], 'key_field_cm': dev['keyboard']['key_field_cm']}
    items['mouse'] = {'delta_ue_cm': cfg['mouse']['delta_ue_cm'], 'proposed_home_js': cfg['mouse']['proposed_home_js'],
                      'proposed_three_m': cfg['mouse']['proposed_three_m'], 'plan_cm': [d[:2] for d in dev['mouse']['footprint_cm']],
                      'palm_target_cm': dev['mouse']['palm_target_cm']}
gr = [rim['min_cm'][:2], rim['max_cm'][:2]]
plans = {k: v['plan_cm'] for k, v in items.items() if 'plan_cm' in v}
plans['grommet_rim'] = gr
out = {'schema': 'sub01.desk-original-scale-items.v1', 'desk_scale': 1.0, 'worktop_top_cm': top, 'device_plane_cm': top,
       'drop_cm': DROP, 'slab_cm': [slab['min_cm'], slab['max_cm']], 'items': items,
       'slab_margins_cm': {k: margins(v) for k, v in plans.items()},
       'plan_overlaps_on_top': {f'{a}|{b}': not (plans[a][1][0] <= plans[b][0][0] or plans[b][1][0] <= plans[a][0][0] or plans[a][1][1] <= plans[b][0][1] or plans[b][1][1] <= plans[a][0][1])
                                for a, b in itertools.combinations([k for k in plans], 2)},
       'note': 'plan boxes are the items\' footprints on the worktop; the clamp lamp is mounted IN the grommet (not on the top) and its arm overhangs, so lamp|grommet and lamp overhead overlaps are by design and are checked natively by root\'s collision proof'}
out['plan_overlaps_on_top'] = {k: v for k, v in out['plan_overlaps_on_top'].items()}
json.dump(out, open(sys.argv[2], 'w'), indent=1)
print(json.dumps({'margins': out['slab_margins_cm'], 'overlaps': {k: v for k, v in out['plan_overlaps_on_top'].items() if v}}, indent=0))
