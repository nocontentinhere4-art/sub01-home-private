"""Install a completed, packed private-house bake; reject mixed or unfinished inputs."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def install(root, destination, layout):
    records = {mode: json.loads((root / mode / 'bake.json').read_text())
               for mode in ('day', 'night')}
    source_hash = digest(root / 'source.glb')
    atlas_hash = digest(root / 'architecture.glb')
    shared = ('samples', 'seed', 'receivers', 'width', 'height',
              'adaptive_sampling', 'denoising')
    for mode, record in records.items():
        if not record['finished'] or record['mode'] != mode:
            raise ValueError(f'{mode} bake is not finished')
        if record['source_sha256'] != source_hash or record['atlas_sha256'] != atlas_hash:
            raise ValueError(f'{mode} source/atlas changed during bake')
        if record['output_sha256'] != digest(root / mode / 'indirect.exr'):
            raise ValueError(f'{mode} EXR hash mismatch')
        if record['direct'] or record['surface_albedo'] or not record['indirect']:
            raise ValueError('Expected indirect-only irradiance')
    if any(records['day'][key] != records['night'][key] for key in shared):
        raise ValueError('Day/night settings or atlas differ')
    files = {'gi-architecture.glb': root / 'architecture.glb'}
    stats = {}
    for mode in records:
        packed = root / (mode + '-packed')
        stats[mode] = json.loads((packed / 'indirect.json').read_text())
        if stats[mode]['source_exr_sha256'] != records[mode]['output_sha256']:
            raise ValueError(f'{mode} packed from a different EXR')
        if (stats[mode]['width'], stats[mode]['height']) != (records[mode]['width'], records[mode]['height']):
            raise ValueError(f'{mode} packed dimensions mismatch')
        for suffix in ('', '-lite'):
            asset = packed / ('indirect' + suffix + '.hdr')
            if not asset.read_bytes().startswith(b'#?'):
                raise ValueError(f'{asset} is not HDR')
            files['indirect-' + mode + suffix + '.hdr'] = asset
    manifest = json.loads((destination / 'indirect-bake.json').read_text())
    manifest.update(source_sha256=source_hash, layout=layout,
                    sampling_note='Matched finished day/night bakes; packed without denoising or atlas blur.',
                    atlas_orientation='raw glTF UV; day/night flipY=false', **stats)
    manifest.update({key: records['day'][key] for key in shared if key not in ('width', 'height')})
    manifest['files'] = [{'file': name, 'sha256': digest(path), 'bytes': path.stat().st_size}
                         for name, path in files.items()]
    # All validations precede writes. Preserve the exact installed prior version.
    backup = root / 'previous'
    backup.mkdir(exist_ok=True)
    for name in (*files, 'indirect-bake.json'):
        old = destination / name
        if old.exists() and not (backup / name).exists():
            shutil.copy2(old, backup / name)
    for name, path in files.items():
        shutil.copy2(path, destination / name)
    (destination / 'indirect-bake.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'installed': len(files), 'receivers': manifest['receivers'],
                      'samples': manifest['samples'], 'source_sha256': source_hash}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--destination', type=Path, default=Path('web/house/assets/lighting'))
    parser.add_argument('--layout', required=True)
    args = parser.parse_args()
    install(args.root, args.destination, args.layout)
