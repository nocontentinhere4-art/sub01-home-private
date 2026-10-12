"""Private, held-out TimesFM 2.5 comparison on existing QC-passed resting fMRI.

Does not send MRI data to a hosted model and does not alter the live brain.
Run in the isolated TimesFM environment; artifacts stay under ignored data/.
"""
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault('OMP_NUM_THREADS', '2')
os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'data/timesfm'
NETWORKS = ('Vis', 'SomMot', 'DorsAttn', 'SalVentAttn', 'Limbic', 'Cont', 'Default')
CONTEXT, HORIZON = 256, 60

def autoregression(context, horizon, order=8):
    mean, std = context.mean(), max(context.std(), 1e-6)
    z = (context - mean) / std
    X = np.array([np.r_[1, z[i-order:i][::-1]] for i in range(order, len(z))])
    regularization = np.eye(order + 1) * .1
    regularization[0, 0] = 0
    coef = np.linalg.solve(X.T @ X + regularization, X.T @ z[order:])
    history = list(z)
    for _ in range(horizon):
        history.append(float(np.r_[1, history[-order:][::-1]] @ coef))
    return np.asarray(history[-horizon:]) * std + mean

def main():
    import psutil
    import shutil
    import timesfm
    import torch
    global OUTPUT, HORIZON, NETWORKS
    live = '--live' in sys.argv
    OUTPUT = ROOT / ('data/timesfm/live' if live else 'data/timesfm')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    available = psutil.virtual_memory().available
    if available < 4 * 2**30 or shutil.disk_usage(OUTPUT).free < 3 * 2**30:
        raise RuntimeError('Insufficient free memory/disk for the isolated forecast trial')
    torch.set_num_threads(2)
    torch.set_float32_matmul_precision('high')
    names = json.loads((ROOT / 'out/atlas_names.json').read_text())
    qc = json.loads((ROOT / 'out/rest/qc.json').read_text())
    candidates = sorted(p for p in (ROOT / 'out/rest').glob('*.npz') if qc.get(p.stem, {}).get('kept', True))
    chosen = [candidates[i] for i in np.linspace(0, len(candidates)-1, 6, dtype=int)]
    contexts, truths, labels = [], [], []
    if live:
        chosen = [ROOT / 'data/timesfm/live_trace.npz']
        HORIZON = 240  # 60 seconds at 4 Hz.
        with np.load(chosen[0]) as d:
            names = d['names'].tolist()
        NETWORKS = tuple(names)
    for path in chosen:
        with np.load(path) as d:
            ts, tr = d['ts'], float(d['tr'])
        if ts.shape[0] < CONTEXT + HORIZON + 2:
            continue
        for cut in np.linspace(CONTEXT, len(ts) - HORIZON, 3, dtype=int):
            for network in NETWORKS:
                columns = [i for i, name in enumerate(names) if name == network or f'_{network}_' in name]
                values = ts[:, columns].mean(axis=1).astype(np.float32)
                context = values[cut-CONTEXT:cut]
                future = values[cut:cut+HORIZON]
                if not np.isfinite(context).all() or not np.isfinite(future).all():
                    continue
                contexts.append(context); truths.append(future)
                labels.append({'run': path.stem, 'network': network, 'cut': int(cut), 'tr': tr})
    actual = np.asarray(truths)
    baseline = {
        'last_value': np.array([np.repeat(c[-1], HORIZON) for c in contexts]),
        'context_mean': np.array([np.repeat(c.mean(), HORIZON) for c in contexts]),
        'ar8': np.array([autoregression(c, HORIZON) for c in contexts]),
    }
    print('Free memory GB:', round(available / 2**30, 1), 'Tasks:', len(contexts), flush=True)
    model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
        'google/timesfm-2.5-200m-pytorch',
        revision='1d952420fba87f3c6dee4f240de0f1a0fbc790e3',
        cache_dir=str(ROOT / 'data/timesfm/weights'))
    model.compile(timesfm.ForecastConfig(max_context=CONTEXT, max_horizon=HORIZON,
        normalize_inputs=True, infer_is_positive=False, per_core_batch_size=8,
        use_continuous_quantile_head=True, fix_quantile_crossing=True))
    start = time.monotonic()
    # The batch implementation pads its input list in-place; preserve the
    # original task windows for metrics and reproducible artifacts.
    forecast, quantiles = model.forecast(horizon=HORIZON, inputs=[c.copy() for c in contexts])
    elapsed = time.monotonic() - start
    if forecast.shape != actual.shape or quantiles.shape[:2] != actual.shape:
        raise ValueError('Forecast alignment does not match the withheld targets')
    predictions = {'timesfm': forecast, **baseline}
    mae = {k: np.abs(v-actual).mean(axis=1) for k, v in predictions.items()}
    report = {
        'model': 'google/timesfm-2.5-200m-pytorch', 'live_brain_changed': False,
        'weights_revision': '1d952420fba87f3c6dee4f240de0f1a0fbc790e3',
        'dataset': 'Local live simulated network activity, 4 Hz' if live else 'Existing QC-passed MyConnectome resting-state fMRI network means; not live simulated firing',
        'protocol': '3 chronological origins per recording; context 256; withheld future',
        'context_samples': CONTEXT, 'horizon_samples': HORIZON,
        'horizon_seconds': sorted({HORIZON*a['tr'] for a in labels}),
        'recordings_selected': len(chosen),
        'recordings_tested': len({a['run'] for a in labels}),
        'limitations': ('Single 150-second local trace; overlapping forecast windows are not independent; network amplitudes are not behavioral predictions.' if live else 'Small offline fMRI check; recording preprocessing predates this test; overlapping windows are not independent.') + ' Quantile coverage is measured, not assumed calibrated. No consciousness conclusion.',
        'tasks': len(contexts), 'forecast_seconds': elapsed,
        'mean_mae': {k: float(v.mean()) for k, v in mae.items()},
        'median_mae': {k: float(np.median(v)) for k, v in mae.items()},
        'beats_fraction': {k: float((mae['timesfm'] < v).mean()) for k, v in mae.items() if k != 'timesfm'},
        'q10_q90_coverage': float(((actual >= quantiles[:, :, 1]) & (actual <= quantiles[:, :, 9])).mean()),
        'by_network': {n: {k: float(v[[i for i, a in enumerate(labels) if a['network']==n]].mean()) for k,v in mae.items()} for n in NETWORKS},
        'labels': labels,
    }
    np.savez_compressed(OUTPUT / 'comparison.npz', context=np.array(contexts), actual=actual,
        timesfm=forecast, quantiles=quantiles, **baseline)
    (OUTPUT / 'report.json').write_text(json.dumps(report, indent=2))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), layout='constrained')
    for ax, index in zip(axes.flat, [0, 1, 5, 6]):
        c = contexts[index]
        tr = labels[index]['tr']; future_time = np.arange(HORIZON)*tr
        ax.plot(np.arange(-90, 0)*tr, c[-90:], color='#8694a0', label='History')
        ax.plot(future_time,actual[index], color='#f2f2f2', label='Actual')
        ax.plot(future_time,forecast[index], color='#ff7a12', label='TimesFM')
        ax.plot(future_time,baseline['ar8'][index], color='#42b6c4', linestyle='--', label='AR(8)')
        ax.fill_between(future_time, quantiles[index,:,1],quantiles[index,:,9],color='#ff7a12',alpha=.15)
        ax.axvline(0,color='#89919b',linestyle=':'); ax.set_title(labels[index]['network'])
        ax.set_facecolor('#151c23'); ax.tick_params(colors='#b7c0c8')
        ax.title.set_color('#f2f2f2'); ax.legend(fontsize=8)
    fig.patch.set_facecolor('#10161c')
    fig.suptitle('SUB-01 / '+('live brain' if live else 'fMRI')+' forecast trial — withheld future (seconds)',color='white')
    fig.savefig(OUTPUT / 'comparison.png',dpi=150)
    print(json.dumps({k:v for k,v in report.items() if k not in ('labels','by_network')},indent=2),flush=True)

if __name__ == '__main__':
    main()
