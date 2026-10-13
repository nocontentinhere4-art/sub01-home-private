"""Install a completed, packed private-house bake; reject mixed or unfinished inputs."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

try:
    from tools.home_sky_contract import validate_sky_pair, MATCHED
except ModuleNotFoundError:
    from home_sky_contract import validate_sky_pair, MATCHED


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_file(folder, relative):
    candidate = (folder / relative).resolve()
    if not candidate.is_relative_to(folder.resolve()):
        raise ValueError('Bake component escapes its directory')
    return candidate


def validate_combined_day(folder, record):
    if (record.get('combined_world_sky') is not True or record.get('sum_verified') is not True
            or record.get('direct') is not True or record.get('indirect') is not True
            or record.get('surface_albedo') is not False):
        raise ValueError('Expected verified disjoint direct sky plus indirect day map')
    components = record.get('components', [])
    if len(components) != 2 or {c.get('role') for c in components} != {'indirect', 'sky-direct'}:
        raise ValueError('Expected exactly indirect and sky-direct components')
    checked = {}
    for component in components:
        manifest = local_file(folder, component['manifest_file'])
        raw = local_file(folder, component['raw_file'])
        if digest(manifest) != component['manifest_sha256'] or digest(raw) != component['raw_sha256']:
            raise ValueError('Sky component file hash mismatch')
        metadata = json.loads(manifest.read_text())
        if metadata.get('output_sha256') != component['raw_sha256']:
            raise ValueError('Sky component EXR differs from its finished recipe')
        checked[component['role']] = metadata
    matched = validate_sky_pair(checked['indirect'], checked['sky-direct'])
    if any(record.get(key) != matched[key] for key in MATCHED):
        raise ValueError('Combined map differs from its component geometry or settings')
    if checked['indirect'].get('mode') != 'day' or checked['sky-direct'].get('mode') != 'day':
        raise ValueError('Sky components must be daylight passes')
    return components


def install(root, destination, layout):
    records = {mode: json.loads((root / mode / 'bake.json').read_text())
               for mode in ('day', 'night')}
    source_hash = digest(root / 'source.glb')
    atlas_hash = digest(root / 'architecture.glb')
    shared = ('samples', 'threads', 'seed', 'receivers', 'width', 'height',
              'adaptive_sampling', 'denoising')
    for mode, record in records.items():
        if not record['finished'] or record['mode'] != mode:
            raise ValueError(f'{mode} bake is not finished')
        if record['source_sha256'] != source_hash or record['atlas_sha256'] != atlas_hash:
            raise ValueError(f'{mode} source/atlas changed during bake')
        if record['output_sha256'] != digest(local_file(root / mode, record.get('output_file', 'indirect.exr'))):
            raise ValueError(f'{mode} EXR hash mismatch')
        if mode == 'day' and record.get('combined_world_sky'):
            validate_combined_day(root / mode, record)
            if (record.get('night_source_sha256') != records['night']['output_sha256']
                    or record.get('night_preserved_sha256') != records['night']['output_sha256']):
                raise ValueError('Night bake was not preserved alongside the sky combination')
        elif record['direct'] or record['surface_albedo'] or not record['indirect']:
            raise ValueError('Expected indirect-only radiance')
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
    if (manifest.get('source_sha256') != source_hash
            or manifest.get('day', {}).get('source_exr_sha256') != stats['day']['source_exr_sha256']):
        # A controlled comparison belongs to the exact scene and radiance pass.
        manifest.pop('day_sampling_comparison', None)
    manifest.update(source_sha256=source_hash, layout=layout,
                    direct_light=records['day']['direct'],
                    albedo_in_bake=records['day']['surface_albedo'],
                    sampling_note='Matched finished day/night bakes; packed without denoising or atlas blur.',
                    atlas_orientation='raw glTF UV; day/night flipY=false', **stats)
    manifest.update({key: records['day'][key] for key in shared if key not in ('width', 'height')})
    if records['day'].get('combined_world_sky'):
        manifest['receiver_diffuse'] = 'occluded-direct-sky-plus-indirect-v1'
        manifest['day_components'] = records['day']['components']
        manifest['day_linear_sum_sha256'] = records['day']['output_sha256']
    else:
        for key in ('receiver_diffuse', 'day_components', 'day_linear_sum_sha256'):
            manifest.pop(key, None)
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
