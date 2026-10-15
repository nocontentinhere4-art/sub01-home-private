"""Recheck the committed seated fits under origin/main's STRONG seat-patch rule (recheck only).

origin/main:tools/validate_unreal_seat_contact.py gates every patch (buttocks, both posterior thighs, both
soles) per sample: overSurfaceVertices >= MIN_PATCH_VERTICES, minGap >= band low, p50 (median) gap <= band high and
bandVertices / overSurfaceVertices >= MIN_BAND_COVERAGE. The branch replaced that with a local-support rule; the
committed docs/proposed/seat-pose-fit clips were judged with the branch rule. This tool:

 * reads main's validator BYTES with `git show <ref>:tools/validate_unreal_seat_contact.py`, refuses them unless their
   sha256 is MAIN_VALIDATOR_SHA256, and imports them from a temporary copy under a private module name (the branch
   file is never touched or imported for the verdict);
 * re-runs the fitter's measurement on the ACTUAL chair exactly as finish_clip does (written GLB read back, body at
   actual_chair.body_offset_from_audited_transform_cm, the committed actual cushion, Trial.seat/soles patch metrics,
   which already compute the per-patch median);
 * judges every gated frame of each clip with main's own validate(): DeskTyping's 301 native audit samples are passed
   as they are; any other clip's gated frame is passed as a 301-sample constant block (main's validate requires that
   shape) so that main's code, not a reimplementation, decides each frame.

It changes no clip, verdict field or importer pin.

    python tools/recheck_seat_fit_main_rule.py --out docs/proposed/seat-pose-fit/main-strong-rule-recheck.json
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

MAIN_REF = 'origin/main'
MAIN_VALIDATOR_PATH = 'tools/validate_unreal_seat_contact.py'
MAIN_VALIDATOR_SHA256 = 'dd95f1b1a8c3fc9a7d08b6d599985b86440c84752d85ae9f12fa8d480397a18f'
FIT_DIR = ROOT / 'docs/proposed/seat-pose-fit'
CLIPS = ('SeatedIdle', 'SitDown_seated', 'GetUp_seated', 'DeskTyping_seated', 'SitToType_seated', 'TypeToSit_seated')


def main_validator_bytes(ref=MAIN_REF):
    return subprocess.run(['git', 'show', f'{ref}:{MAIN_VALIDATOR_PATH}'], cwd=ROOT, check=True,
                          capture_output=True).stdout


def load_main_validator(data: bytes):
    """Import main's validator from a temporary copy; refuse bytes that are not the pinned main file."""
    sha = hashlib.sha256(data).hexdigest()
    if sha != MAIN_VALIDATOR_SHA256:
        raise ValueError(f'main validator sha256 {sha} != pinned {MAIN_VALIDATOR_SHA256}')
    tmp = Path(tempfile.mkdtemp(prefix='main-seat-validator-')) / 'main_validate_unreal_seat_contact.py'
    tmp.write_bytes(data)
    spec = importlib.util.spec_from_file_location('main_validate_unreal_seat_contact', tmp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.SOURCE_SHA256 = sha
    return mod


def region_row(name, m, f):
    """One patch of one frame in the field names of tools/unreal_audit_seat_contact.py (main's input)."""
    low = m['lowest'][f]
    med = m['median'][f]
    return {'region': name, 'selectedVertices': int(m['facing'][f]), 'facingVertices': int(m['facing'][f]),
            'overSurfaceVertices': int(m['over'][f]), 'bandVertices': int(m['band'][f]),
            'minGapCm': float(low) if np.isfinite(low) else 1e9, 'p10GapCm': float(med) if np.isfinite(med) else 1e9,
            'p50GapCm': float(med) if np.isfinite(med) else 1e9, 'p90GapCm': float(med) if np.isfinite(med) else 1e9,
            'maxGapCm': float(med) if np.isfinite(med) else 1e9}


def frame_regions(metrics, f):
    return [region_row(n, metrics[n], f) for n in metrics]


def judge_frame(V, regions):
    """main's validate() on one frame (a 301-sample constant block); None = pass, else main's message."""
    data = {'samples': [{'time': 3 + i / 60, 'invalidInfluences': 0, 'regions': regions} for i in range(301)]}
    try:
        V.validate(data)
        return None
    except ValueError as e:
        return str(e).rsplit(' at ', 1)[0]


def decompose(V, name, r):
    """Which of main's per-sample conditions a patch meets (reported next to main's own verdict)."""
    low, high = V.band(name)
    over = r['overSurfaceVertices']
    cov = r['bandVertices'] / over if over else 0.
    return {'over_ok': over >= V.MIN_PATCH_VERTICES, 'min_gap_ok': r['minGapCm'] >= low,
            'median_ok': r['p50GapCm'] <= high, 'coverage_ok': cov >= V.MIN_BAND_COVERAGE, 'coverage': cov}


def measure_clip(name, base, tri, keys, P, E, G):
    """finish_clip's actual-chair read-back, returning per-frame patch metrics on the gated frames."""
    rep = json.loads((FIT_DIR / f'SUB01_{name}.report.json').read_text())
    g = G.Gltf(FIT_DIR / f'SUB01_{name}.glb')
    times = [float(t) for t in g.animation().key_times()]
    if rep['role'] == 'DeskTyping_seated':
        t0 = float(G.Gltf(ROOT / rep['labels']['source_clip']).animation().key_times()[0])
        t_aud = [t - t0 for t in E.TIMES]                   # finish_clip: native audit times rebased on the source
    else:
        t_aud = times
    W_out, _ = E.joint_worlds(g, base.names, t_aud)
    off = rep['actual_chair']['body_offset_from_audited_transform_cm']
    d = dict(base.d)
    d['joint_world'], d['times'] = W_out, np.array(t_aud)
    fit_out = P.SeatFit(E.Source(d), tri, keys, (0., 0.))
    fa = P.actual_fit(fit_out, tri, keys, off)
    Wa = P.place_body(W_out, off)
    s, so = fa.trial.seat(Wa), fa.trial.soles(Wa)
    pf = rep['actual_chair'].get('per_frame')
    mask = np.asarray(pf['support_mask'], bool) if pf else np.ones(len(Wa), bool)
    metrics = {n: s[n] for n in P.T.SEAT_PATCHES}
    metrics.update({n: so[n] for n in P.T.SOLE_PATCHES})
    # reproduction check against what the fitter stored (lowest gap on the gated frames)
    repro = {}
    if pf:
        for n in metrics:
            stored = np.asarray(pf['patches'][n]['lowest_cm'], float)
            repro[n] = float(np.nanmax(np.abs(np.asarray(metrics[n]['lowest']) - stored)))
    else:
        g_seat = rep['actual_chair']['gates']['seat']
        for n in P.T.SEAT_PATCHES:
            lo, hi = g_seat[n]['corrected']['lowest_gap_cm']
            got = np.asarray(metrics[n]['lowest'])[mask]
            repro[n] = float(max(abs(np.nanmin(got) - lo), abs(np.nanmax(got) - hi)))
    return rep, metrics, mask, repro, len(Wa)


def recheck(V, name, metrics, mask, F):
    gated = [int(i) for i in np.nonzero(mask)[0]]
    names = list(metrics)
    fails, per_patch_fail = {}, {n: {'over': [], 'min_gap': [], 'median': [], 'coverage': []} for n in names}
    worst = {}
    for f in gated:
        regions = frame_regions(metrics, f)
        msg = judge_frame(V, regions)
        if msg:
            fails[f] = msg
        for r in regions:
            n, c = r['region'], decompose(V, r['region'], r)
            for k, ok in (('over', c['over_ok']), ('min_gap', c['min_gap_ok']), ('median', c['median_ok']),
                          ('coverage', c['coverage_ok'])):
                if not ok:
                    per_patch_fail[n][k].append(f)
            w = worst.setdefault(n, {'band_cm': list(V.band(n)), 'min_gap_cm': (math.inf, None),
                                     'max_median_gap_cm': (-math.inf, None), 'min_coverage': (math.inf, None),
                                     'min_over_surface_vertices': (math.inf, None)})
            if r['minGapCm'] < w['min_gap_cm'][0]:
                w['min_gap_cm'] = (r['minGapCm'], f)
            if r['p50GapCm'] > w['max_median_gap_cm'][0]:
                w['max_median_gap_cm'] = (r['p50GapCm'], f)
            if c['coverage'] < w['min_coverage'][0]:
                w['min_coverage'] = (c['coverage'], f)
            if r['overSurfaceVertices'] < w['min_over_surface_vertices'][0]:
                w['min_over_surface_vertices'] = (r['overSurfaceVertices'], f)
    worst = {n: {k: (v if k == 'band_cm' else {'value': round(float(v[0]), 4), 'frame': v[1]}) for k, v in w.items()}
             for n, w in worst.items()}
    # nearest vertical correction under main's rule: shift d of a patch moves min and median by d (as main's
    # propose_vertical_anchor); seat-only, then all patches
    def interval(ns):
        lo, hi = -math.inf, math.inf
        for f in gated:
            for n in ns:
                low, high = V.band(n)
                lo = max(lo, low - float(metrics[n]['lowest'][f]))
                hi = min(hi, high - float(metrics[n]['median'][f]))
        return [round(lo, 4), round(hi, 4)]
    spread = {}
    for n in names:
        low, high = V.band(n)
        sp = np.array([float(metrics[n]['median'][f]) - float(metrics[n]['lowest'][f]) for f in gated])
        spread[n] = {'band_width_cm': high - low, 'max_median_minus_min_cm': round(float(sp.max()), 4),
                     'frames_wider_than_band': int((sp > high - low).sum()),
                     'note': 'median - min > band width: no rigid vertical shift of this patch passes that frame'}
    seat_iv = interval(V.SEAT_REGIONS)
    per_seat_iv = {n: interval((n,)) for n in V.SEAT_REGIONS}
    return {'frames': F, 'gated_frames': len(gated), 'gated_frame_indices': gated,
            'pass_main_rule': not fails, 'failing_frames': sorted(fails), 'failing_frame_count': len(fails),
            'main_validate_message_by_frame': {str(k): v for k, v in sorted(fails.items())},
            'failing_frames_by_patch_and_condition': {n: {k: v for k, v in d.items() if v} for n, d in per_patch_fail.items()
                                                      if any(d.values())},
            'worst': worst,
            'vertical_shift_window_cm': {
                'rule': "main's propose_vertical_anchor arithmetic per patch on the gated frames: a vertical shift d is "
                        'allowed when min + d >= band low and median + d <= band high; [lo, hi] empty (lo > hi) means no '
                        'rigid shift of that set can pass',
                'seat_patches_together': seat_iv, 'each_seat_patch': per_seat_iv,
                'each_sole': {n: interval((n,)) for n in V.SOLE_REGIONS}},
            'patch_spread_vs_band': spread}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--source', default=str(ROOT / 'private-audit/seat-fit-source.npz'))
    ap.add_argument('--ref', default=MAIN_REF)
    ap.add_argument('--out', default=str(FIT_DIR / 'main-strong-rule-recheck.json'))
    args = ap.parse_args(argv)
    V = load_main_validator(main_validator_bytes(args.ref))
    import export_seat_fit_source as E
    import fit_seat_pelvis_pitch as P
    import life_gltf as G
    base = E.Source.load(args.source)
    tri, cmeta = P.load_cushion()
    keys = P.T.keycaps_from_glb()
    clips, branch_verdicts = {}, {}
    for name in CLIPS:
        rep, metrics, mask, repro, F = measure_clip(name, base, tri, keys, P, E, G)
        res = recheck(V, name, metrics, mask, F)
        res['glb_sha256'] = rep['sha256']
        res['measurement_reproduction_max_abs_lowest_gap_diff_cm'] = {n: round(v, 6) for n, v in repro.items()}
        res['branch_rule_verdict_unchanged'] = {'all_gates_pass': rep['all_gates_pass'],
                                                'actual_chair_all_gates_pass': rep['actual_chair']['all_gates_pass']}
        res['gated_frames_rule'] = ('actual_chair.per_frame.support_mask (seat AND soles, as per_frame_gate)'
                                    if rep['actual_chair'].get('per_frame') else
                                    ('the 301 native audit samples (3..8 s @60 Hz)' if name == 'DeskTyping_seated'
                                     else 'every written key'))
        if name == 'DeskTyping_seated':       # exactly main's 301-sample input: one direct validate() call too
            data = {'samples': [{'time': 3 + i / 60, 'invalidInfluences': 0, 'regions': frame_regions(metrics, i)}
                                for i in range(F)]}
            try:
                V.validate(data)
                res['main_validate_direct_301'] = 'pass'
            except ValueError as e:
                res['main_validate_direct_301'] = f'FAIL: {e}'
        clips[name] = res
    doc = {'schema': 'sub01.seat-fit-main-strong-rule-recheck.v1', 'recheck_only': True,
           'changes_verdicts_or_pins': False,
           'main_validator': {'ref': args.ref, 'path': MAIN_VALIDATOR_PATH, 'sha256': V.SOURCE_SHA256,
                              'seat_band_cm': list(V.SEAT_BAND_CM), 'sole_band_cm': list(V.SOLE_BAND_CM),
                              'min_patch_vertices': V.MIN_PATCH_VERTICES, 'min_band_coverage': V.MIN_BAND_COVERAGE,
                              'regions': list(V.REGIONS),
                              'rule': 'per sample and patch: over >= MIN_PATCH_VERTICES, minGap >= band low, '
                                      'p50 <= band high, band/over >= MIN_BAND_COVERAGE (soles too, band 0..+1 cm)'},
           'cushion': {k: cmeta.get(k) for k in ('file', 'sha256', 'source')},
           'measurement': ('fit_seat_pelvis_pitch finish_clip actual-chair read-back of each committed GLB (Trial.seat / '
                           'Trial.soles patch_metrics: over = facing-down skin over the surface, band = in-band count, '
                           'lowest = minGap, median = p50); skin every vertex of the owner patch sets in the source npz'),
           'input_mapping_note': ('p10/p90/max are not used by main validate(); they are filled with the median. '
                                  'Non-DeskTyping frames are each judged as a 301-sample constant block because main '
                                  'validate() requires exactly 301 samples.'),
           'clips': clips,
           'summary': {n: {'pass_main_rule': c['pass_main_rule'], 'failing_frames': c['failing_frame_count'],
                           'gated_frames': c['gated_frames']} for n, c in clips.items()}}
    Path(args.out).write_text(json.dumps(doc, indent=1) + '\n')
    print(json.dumps(doc['summary'], indent=1))
    return doc


if __name__ == '__main__':
    main()
