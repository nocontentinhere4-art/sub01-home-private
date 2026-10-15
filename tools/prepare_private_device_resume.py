"""Package tracked device source and a non-secret persistent-volume handoff.

Does not contact a provider, start services, move state, or copy credentials.
The returned target identity must be reviewed before installing runtime gates.
"""
import argparse
import hashlib
import json
import subprocess
import tarfile
from pathlib import Path

PERSISTENT = '/workspace/sub01-home-private'
ROOTFS = '/home/unreal/sub01-backend'
DEPENDENCIES = [
    'numpy==2.2.6', 'scipy==1.15.3', 'aiohttp==3.14.5', 'chess==1.11.2',
    'anthropic==0.69.0', 'playwright==1.63.0', 'Pillow==11.3.0',
]


def selected_source(name):
    p = Path(name)
    if p.is_absolute() or '..' in p.parts:
        return False
    if name in {'out/connectome.npz', 'out/atlas_names.json'}:
        return True
    return (p.suffix in {'.py', '.cjs', '.js', '.json', '.html', '.css', '.wasm', '.csv', '.npz'}
            and ('/' not in name or name.startswith((
                'computer/', 'games/minecraft/', 'scripts/home_',
                'tools/unreal_home_state_bridge', 'tools/unreal_home_coordinates',
                'tools/pixel_streaming/native_live',
                'tools/pixel_streaming/native_view',
                'tools/pixel_streaming/native_input', 'twin/', 'spiking/', 'web/'))))


def prepare(root, output):
    root = root.resolve()
    names = subprocess.check_output(['git', 'ls-files'], cwd=root, text=True).splitlines()
    output.mkdir(parents=True, exist_ok=True)
    archive = output / 'device-source.tar.gz'
    files = {}
    with tarfile.open(archive, 'w:gz') as bundle:
        for name in sorted(filter(selected_source, names)):
            path = root / name
            if path.is_symlink() or not path.is_file():
                continue
            files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            bundle.add(path, arcname=name, recursive=False)
    manifest = {
        'schema': 1, 'target_pod': None, 'deployment_authorized': False,
        'native_ready': False, 'source_files_sha256': files,
        'source_archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
        'persistent_source_destination': PERSISTENT + '/device-runtime/source',
        'persistent_paths_keep_existing': [PERSISTENT + '/' + p for p in [
            'pc-vga-state-fresh', 'TinyCore-11.0.iso', 'backend-state',
            'streaming/node-v22.14.0-linux-x64',
            'minecraft-prepared/source/games/minecraft/node_modules',
            'minecraft-prepared/playwright-browsers',
            'device-runtime/wheels', 'device-runtime/public-debs']],
        'backend_brain_files_verify_after_source_restore': [
            ROOTFS + '/out/connectome.npz', ROOTFS + '/out/atlas_names.json'],
        'shutdown_policy': 'Read authenticated runtime-window deadline at service launch; '
                           'work milestone does not shorten authorized GPU retention.',
        'protected_rootfs_operator_file': '/home/unreal/.sub01-private/operator-token',
        'credential_policy': 'Restore same authorized operator role through private channel; '
                             '0600 owner1001, parent0700; never on volume or in source archive.',
        'rootfs_backend': ROOTFS, 'python_dependencies': DEPENDENCIES,
        'java': 'Official OpenJDK17; existing Minecraft1.20.1 jar/class61 only',
        'ports_loopback_only': {'pc': 8811, 'backend': 8820, 'bridge': 8821, 'viewer': 8892},
        'startup_order': [
            'Verify returned target and allocation; authenticate current budget guards.',
            'Pin launcher/viewer/native project identity to reviewed returned target.',
            'Verify preserved snapshot/world and source archive hashes; never overwrite state.',
            'Restore protected operator role; rootfs source and pinned dependencies.',
            'Require HOME_NATIVE_REQUIRED=1; manual TV input OFF; native flags absent.',
            'Refuse duplicate service ports/processes; start only bounded loopback services.',
            'Arm snapshot/world graceful save before automatic global stop.',
            'Require fresh actual Game PID/startticks/privacy/pixels before capture or input.'
        ],
    }
    (output / 'device-resume-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.root, args.output)
    print(json.dumps({'files': len(result['source_files_sha256']),
                      'sha256': result['source_archive_sha256'], 'native_ready': False}))
