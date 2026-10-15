"""One bounded offline Runpod-only motion generation, with CPU text encoding."""
import json
import os
import sys
import time
from pathlib import Path


def main():
    root = Path('/workspace/sub01-home-private/motion-runtime')
    window = json.loads(Path('/run/sub01-home-private/runtime-window.json').read_text())
    assert time.time() < window['deadline_epoch'] and window['stop_guards_authenticated']
    acquired = json.loads((root / 'receipts/authorized-encoder-download.json').read_text())
    assert acquired['finished'] and all(m['acquired'] for m in acquired['models'])
    os.environ.update(HF_HOME=str(root / 'hf-cache'), HF_HUB_OFFLINE='1',
                      HF_HUB_DISABLE_TELEMETRY='1', TRANSFORMERS_OFFLINE='1',
                      LOCAL_CACHE='True', TEXT_ENCODER_MODE='local', TEXT_ENCODER_DEVICE='cpu',
                      OMP_NUM_THREADS='2', MKL_NUM_THREADS='2', TOKENIZERS_PARALLELISM='false')
    # Pin the default cache lookup to the exact acquired official snapshots.
    models = acquired['models'] + [{
        'repo': 'nvidia/Kimodo-SOMA-RP-v1.1',
        'revision': '6c9233af1180b8151e3c4703477104af5dce9dd5'}]
    for m in models:
        cache = root / 'hf-cache/hub' / ('models--' + m['repo'].replace('/', '--'))
        assert (cache / 'snapshots' / m['revision']).is_dir()
        (cache / 'refs').mkdir(exist_ok=True)
        (cache / 'refs/main').write_text(m['revision'])
    import torch
    import numpy as np
    torch.set_num_threads(2)
    torch.set_num_interop_threads(2)
    assert torch.cuda.is_available(), 'Inference belongs on the authorized GPU server'
    torch.cuda.set_per_process_memory_fraction(0.15)
    free, total = torch.cuda.mem_get_info()
    assert free > 6 * 2**30, 'Preserve original home GPU headroom'
    output = root / 'generated-r2-verified-adapters'
    output.mkdir(exist_ok=True)
    receipt = output / 'generation-receipt.json'
    report = {'schema': 'sub01.private-kimodo-generation.v1', 'started_epoch': time.time(),
              'prompt': 'A person walks slowly forward with relaxed shoulders and natural arm swing, then gently comes to a stop',
              'duration_seconds': 3.0, 'seed': 105, 'text_encoder_device': 'cpu',
              'gpu_memory_fraction_limit': 0.15, 'finished': False,
              'native_imported': False, 'contact_accepted': False}
    receipt.write_text(json.dumps(report, indent=2) + '\n')
    try:
        # Transformers 5 emits a preliminary adapter-key mismatch report.
        # Inspect the final PEFT load rather than assuming that report is benign.
        from peft import PeftModel
        from safetensors import safe_open
        original_load = PeftModel.from_pretrained
        audits = []
        by_repo = {m['repo']: m for m in acquired['models']}

        def canonical(name):
            assert 'layers.' in name, 'Unexpected adapter tensor target'
            return name[name.index('layers.'):].replace('.default.', '.')

        def verified_load(cls, model, model_id, *args, **kwargs):
            loaded = original_load(model, model_id, *args, **kwargs)
            assert model_id in by_repo, 'Only acquired official adapters are permitted'
            file = Path(by_repo[model_id]['snapshot_path']) / 'adapter_model.safetensors'
            actual = {}
            for name, parameter in loaded.named_parameters():
                if 'lora_' not in name:
                    continue
                name = canonical(name)
                assert name not in actual, 'Ambiguous nested adapter tensor'
                actual[name] = parameter.detach()
            checked = 0
            with safe_open(file, framework='pt', device='cpu') as weights:
                for name in weights.keys():
                    expected = weights.get_tensor(name)
                    parameter = actual[canonical(name)]
                    assert tuple(expected.shape) == tuple(parameter.shape)
                    assert torch.isfinite(parameter).all()
                    assert torch.equal(expected.to(device=parameter.device, dtype=parameter.dtype), parameter), 'Final adapter weights differ from official checkpoint'
                    checked += 1
            assert checked >= 64, 'Incomplete adapter load'
            audits.append({'repo': model_id, 'official_tensors_exact_after_dtype_cast': checked})
            print('ADAPTER_WEIGHTS_VERIFIED', model_id, checked, flush=True)
            return loaded

        PeftModel.from_pretrained = classmethod(verified_load)
        from kimodo.scripts.generate import main as generate
        sys.argv = ['kimodo_gen', report['prompt'], '--model', 'Kimodo-SOMA-RP-v1.1',
                    '--duration', '3', '--num_samples', '1', '--diffusion_steps', '50',
                    '--seed', '105', '--output', str(output / 'relaxed-walk-stop'), '--bvh']
        generate()
        assert len(audits) == 2, 'Both official encoder adapters must be verified'
        report['adapter_weight_audits'] = audits
        path = output / 'relaxed-walk-stop.npz'
        with np.load(path, allow_pickle=False) as motion:
            arrays = {k: {'shape': list(motion[k].shape), 'dtype': str(motion[k].dtype)} for k in motion.files}
            for key in ['posed_joints', 'global_rot_mats']:
                assert np.isfinite(motion[key]).all(), 'Non-finite generated body motion'
        report.update(finished=True, completed_epoch=time.time(), arrays=arrays,
                      npz_bytes=path.stat().st_size, gpu_peak_allocated_bytes=torch.cuda.max_memory_allocated())
    except Exception as error:
        report['error_type'] = type(error).__name__
        # No credential is loaded into this process; retain diagnostic stack locally.
        import traceback
        traceback.print_exc()
    receipt.write_text(json.dumps(report, indent=2) + '\n')
    print('GENERATION_RECEIPT', json.dumps(report), flush=True)
    if not report['finished']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
