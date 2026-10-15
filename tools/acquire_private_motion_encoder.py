"""Download authorized motion-encoder weights on the private GPU server only.

Reads a separately protected model-only HF token. Never prints/persists the
token in logs, receipts, commands or persistent model cache.
"""
import json
import os
import time
from pathlib import Path


def main():
    root = Path('/workspace/sub01-home-private/motion-runtime')
    assert root.is_dir() and Path('/home/unreal/.venvs/sub01-kimodo').is_dir()
    credential = Path('/home/unreal/.sub01-private/hf-motion-read.token')
    assert credential.stat().st_mode & 0o077 == 0, 'Private credential permissions required'
    token = credential.read_text().strip()
    assert token.startswith('hf_')
    os.environ['HF_HOME'] = str(root / 'hf-cache')
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    from huggingface_hub import HfApi, snapshot_download

    models = [
        ('meta-llama/Meta-Llama-3-8B-Instruct', '8afb486c1db24fe5011ec46dfbe5b5dccdb575c2', True),
        ('McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp', '31474e395ada192e8ed1586db6be79fb3b70c9c0', False),
        ('McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp-supervised', 'baa8ebf04a1c2500e61288e7dad65e8ae42601a7', False),
    ]
    report = {'schema': 'sub01.private-motion-encoder-acquisition.v1', 'started_epoch': time.time(),
              'gpu_inference_started': False, 'models': [], 'finished': False}
    receipt = root / 'receipts' / 'authorized-encoder-download.json'

    def save():
        tmp = receipt.with_suffix('.tmp')
        tmp.write_text(json.dumps(report, indent=2) + '\n')
        tmp.replace(receipt)

    save()
    try:
        for repo, revision, gated in models:
            # Only the one authorized gated repo receives the user's credential.
            auth = token if gated else False
            info = HfApi(token=auth).model_info(repo, revision=revision, files_metadata=True)
            assert info.sha == revision, 'Pinned model revision differs'
            files = [f for f in info.siblings if '/' not in f.rfilename and
                     f.rfilename.endswith(('.safetensors', '.json', '.model', '.txt'))]
            size = sum(f.size or 0 for f in files)
            assert 0 < size < (18 * 2**30 if gated else 1 * 2**30), 'Download exceeds planned size'
            entry = {'repo': repo, 'revision': revision, 'selected_bytes': size,
                     'files': [f.rfilename for f in files], 'acquired': False}
            report['models'].append(entry)
            save()
            print('DOWNLOAD_BEGIN', repo, size, flush=True)
            path = snapshot_download(repo, revision=revision, token=auth,
                                     allow_patterns=entry['files'], max_workers=2)
            entry.update(acquired=True, snapshot_path=path, completed_epoch=time.time())
            save()
            print('DOWNLOAD_COMPLETE', repo, revision, flush=True)
        report.update(finished=True, completed_epoch=time.time())
        save()
    except Exception as error:
        # Exception text can contain private request headers/URLs; omit it.
        report['error_type'] = type(error).__name__
        save()
        print('DOWNLOAD_FAILED', type(error).__name__, flush=True)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
