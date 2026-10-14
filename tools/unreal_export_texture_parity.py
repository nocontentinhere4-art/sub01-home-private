"""Texture content-equivalence (parity) evidence for the SUB-01 home material fix.

Why: the four queen-bed upholstery materials bind four DIFFERENT UE texture assets
(Image_148/149/1410/1411) although the source full-home.glb shares one image (index 15,
bufferView 157). tools/unreal_home_materials_fix.py refuses bed presets on distinct
textures unless this parity file proves they hold the same pixels as GLB image 15 and are
imported with neutral colour settings.

Phase 1 (root, sole UE editor, READ ONLY: no asset save, no level change):
  UnrealEditor-Cmd <project>/Sub01HomeLab.uproject /Game/Sub01Home/ActualHome \
    -ExecutePythonScript="<repo>/tools/unreal_export_texture_parity.py --export <outdir> --quit" -unattended -nosplash
  Exports each texture's SOURCE pixels (the imported art, pre-GPU-compression) to
  <outdir>/<asset>.png through AssetExportTask, and writes <outdir>/texture-settings.json
  (sRGB, compression, LOD bias, mip/adjust settings, import source file).
  Default textures are the four bed upholstery textures; override with --texture (repeatable).

Phase 2 (anywhere with PIL/numpy, pure):
  python3 tools/unreal_export_texture_parity.py --finalize <outdir> --glb <project>/SourceAssets/full-home.glb \
      [--image-index 15] > texture-parity.json
  Decodes every PNG and the GLB image, hashes the decoded RGBA pixels, computes stats and the
  max abs difference against the GLB image, and writes the parity JSON (schema below).

Phase 3: python3 tools/unreal_home_materials_fix.py --mapping-check --inventory <inv.json> --parity texture-parity.json

Parity schema ``sub01.texture-parity.v1``::

  {"schema": "sub01.texture-parity.v1", "generated_utc": str, "exporter": "tools/unreal_export_texture_parity.py",
   "reference": {"glb": str, "glb_sha256": str, "image_index": 15, "buffer_view": 157, "mime_type": str,
                 "width": int, "height": int, "decoded_rgba_sha256": str},
   "textures": [{
      "asset_path": "/Game/.../Image_148.Image_148",
      "source_provenance": {"import_source_file": str|null,  # AssetImportData first filename
                            "glb_image_index": int|null, "buffer_view": int|null,  # when the import data says
                            "pixel_match_reference": bool},  # decoded RGBA hash == reference hash
      "width": int, "height": int, "srgb": bool, "compression": "TC_DEFAULT", "lod_bias": int,
      "mip_gen_settings": str, "adjust": {"adjust_brightness": 1.0, ...},
      "png": {"file": str, "file_sha256": str},
      "decoded_rgba_sha256": str,
      "stats": {"mean_rgb_8bit": [r,g,b], "stddev_rgb_8bit": [r,g,b], "linear_mean": [r,g,b],
                "linear_p99": [r,g,b]},
      "max_abs_diff_vs_reference_8bit": int,
      "reencode_proven": bool, "reencode_note": str|null}]}

Acceptance (``validate_parity``): identical dimensions; decoded RGBA hash equal to the GLB
image (max abs diff 0), or max abs diff <= 1 only when ``reencode_proven`` is true with a
note; import source file is the full-home GLB (or the import data names image 15 / bufferView
157); sRGB true; compression TC_DEFAULT; LOD bias 0; every colour-adjust property at its
neutral default. Anything missing or different refuses.
"""
import argparse
import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

PARITY_SCHEMA = 'sub01.texture-parity.v1'
SETTINGS_SCHEMA = 'sub01.texture-settings.v1'
REFERENCE_IMAGE_INDEX = 15
REFERENCE_BUFFER_VIEW = 157
BED_TEXTURES = tuple('/Game/Sub01Home/ImportedScene/full-home/Textures/%s.%s' % (n, n)
                     for n in ('Image_148', 'Image_149', 'Image_1410', 'Image_1411'))
ALLOWED_ROOT = '/Game/Sub01Home/ImportedScene/'
ALLOWED_COMPRESSION = ('TC_DEFAULT', 'TextureCompressionSettings.TC_DEFAULT')
ADJUST_DEFAULTS = {'adjust_brightness': 1.0, 'adjust_brightness_curve': 1.0, 'adjust_saturation': 1.0,
                   'adjust_vibrance': 0.0, 'adjust_rgb_curve': 1.0, 'adjust_hue': 0.0,
                   'adjust_min_alpha': 0.0, 'adjust_max_alpha': 1.0}


class ParityError(RuntimeError):
    pass


def _enum_name(value):
    s = str(value)
    if '.' in s and not s.startswith('<'):
        s = s.split('.')[-1]
    if s.startswith('<') and ':' in s:      # "<TextureCompressionSettings.TC_DEFAULT: 0>"
        s = s[1:].split(':')[0].split('.')[-1]
    return s


# ---------------------------------------------------------------------------
# Phase 1: editor, read only
# ---------------------------------------------------------------------------
def export_textures(out_dir, paths=BED_TEXTURES, *, u=None):
    if u is None:
        import unreal as u  # noqa: N813
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise ParityError('Export directory must be empty: %s' % out)
    rows, problems = [], []
    textures = []
    for path in paths:
        if not path.startswith(ALLOWED_ROOT):
            problems.append('%s is outside %s' % (path, ALLOWED_ROOT))
            continue
        texture = u.load_asset(path.split('.')[0])
        if texture is None or not isinstance(texture, u.Texture2D):
            problems.append('%s is missing or not a Texture2D' % path)
            continue
        textures.append((path, texture))
    if problems:
        raise ParityError('Refused (nothing exported): ' + '; '.join(problems))
    for path, texture in textures:
        name = path.rsplit('/', 1)[-1].split('.')[0]
        png = out / (name + '.png')
        task = u.AssetExportTask()
        for key, value in (('object', texture), ('filename', str(png)), ('automated', True),
                           ('prompt', False), ('replace_identical', True), ('selected', False)):
            task.set_editor_property(key, value)
        if not u.Exporter.run_asset_export_task(task) or not png.is_file():
            raise ParityError('PNG export failed for %s' % path)
        settings = {}
        for key in ('srgb', 'compression_settings', 'lod_bias', 'mip_gen_settings', 'lod_group', 'filter',
                    'never_stream', *ADJUST_DEFAULTS):
            try:
                value = texture.get_editor_property(key)
            except Exception:  # noqa: BLE001
                value = None
            settings[key] = value if isinstance(value, (bool, int, float, str, type(None))) else _enum_name(value)
        source = None
        try:
            data = texture.get_editor_property('asset_import_data')
            source = data.get_first_filename() if data is not None else None
        except Exception:  # noqa: BLE001
            source = None
        rows.append({'asset_path': path, 'png': png.name, 'width': int(texture.blueprint_get_size_x()),
                     'height': int(texture.blueprint_get_size_y()), 'settings': settings,
                     'import_source_file': source})
    report = {'schema': SETTINGS_SCHEMA, 'generated_utc': _dt.datetime.now(_dt.timezone.utc).isoformat(),
              'read_only': True, 'textures': rows}
    (out / 'texture-settings.json').write_text(json.dumps(report, indent=1) + '\n')
    u.log('SUB01_TEXTURE_PARITY_EXPORT %d textures -> %s' % (len(rows), out))
    return report


# ---------------------------------------------------------------------------
# Phase 2: pure
# ---------------------------------------------------------------------------
def decoded_stats(data):
    import io
    import numpy as np
    from PIL import Image
    image = Image.open(io.BytesIO(data) if isinstance(data, (bytes, bytearray)) else data).convert('RGBA')
    rgba = np.asarray(image, dtype=np.uint8)
    rgb = rgba[..., :3].astype(np.float64)
    a = rgb / 255.0
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    return rgba, {'width': image.width, 'height': image.height,
                  'decoded_rgba_sha256': hashlib.sha256(rgba.tobytes()).hexdigest(),
                  'stats': {'mean_rgb_8bit': [round(float(x), 3) for x in rgb.reshape(-1, 3).mean(0)],
                            'stddev_rgb_8bit': [round(float(x), 3) for x in rgb.reshape(-1, 3).std(0)],
                            'linear_mean': [round(float(x), 5) for x in lin.reshape(-1, 3).mean(0)],
                            'linear_p99': [round(float(np.percentile(lin[..., c], 99)), 5) for c in range(3)]}}


def reference_image(glb, image_index=REFERENCE_IMAGE_INDEX):
    import home_materials_spec as spec
    doc, binary, sha = spec.read_glb(glb)
    image = doc['images'][image_index]
    data = spec.image_bytes(glb, doc, binary, image_index)
    rgba, stats = decoded_stats(data)
    return rgba, {'glb': str(glb), 'glb_sha256': sha, 'image_index': image_index,
                  'buffer_view': image.get('bufferView'), 'mime_type': image.get('mimeType'),
                  'width': stats['width'], 'height': stats['height'],
                  'decoded_rgba_sha256': stats['decoded_rgba_sha256'], 'stats': stats['stats']}


def finalize(export_dir, glb, image_index=REFERENCE_IMAGE_INDEX):
    import numpy as np
    export_dir = Path(export_dir)
    settings = json.loads((export_dir / 'texture-settings.json').read_text())
    if settings.get('schema') != SETTINGS_SCHEMA:
        raise ParityError('Unexpected settings schema')
    ref_rgba, reference = reference_image(glb, image_index)
    textures = []
    for row in settings['textures']:
        data = (export_dir / row['png']).read_bytes()
        rgba, stats = decoded_stats(data)
        if rgba.shape == ref_rgba.shape:
            diff = int(np.abs(rgba.astype(np.int16) - ref_rgba.astype(np.int16)).max())
        else:
            diff = None
        s = row['settings']
        textures.append({
            'asset_path': row['asset_path'],
            'source_provenance': {'import_source_file': row.get('import_source_file'),
                                  'glb_image_index': None, 'buffer_view': None,
                                  'pixel_match_reference': stats['decoded_rgba_sha256'] == reference['decoded_rgba_sha256']},
            'width': stats['width'], 'height': stats['height'],
            'editor_size': [row['width'], row['height']],
            'srgb': s.get('srgb'), 'compression': s.get('compression_settings'), 'lod_bias': s.get('lod_bias'),
            'mip_gen_settings': s.get('mip_gen_settings'),
            'adjust': {k: s.get(k) for k in ADJUST_DEFAULTS},
            'png': {'file': row['png'], 'file_sha256': hashlib.sha256(data).hexdigest()},
            'decoded_rgba_sha256': stats['decoded_rgba_sha256'], 'stats': stats['stats'],
            'max_abs_diff_vs_reference_8bit': diff, 'reencode_proven': False, 'reencode_note': None})
    return {'schema': PARITY_SCHEMA, 'generated_utc': _dt.datetime.now(_dt.timezone.utc).isoformat(),
            'exporter': 'tools/unreal_export_texture_parity.py', 'reference': reference, 'textures': textures}


def validate_parity(parity, texture_paths, glb_name='full-home'):
    """Return (problems, mean_linear, p99_linear) for a set of UE texture paths claimed equivalent."""
    problems = []
    if not parity or parity.get('schema') != PARITY_SCHEMA:
        return ['no valid %s parity file' % PARITY_SCHEMA], None, None
    ref = parity.get('reference') or {}
    if ref.get('image_index') != REFERENCE_IMAGE_INDEX or ref.get('buffer_view') not in (REFERENCE_BUFFER_VIEW, None):
        problems.append('reference is not GLB image %d / bufferView %d: %s' % (
            REFERENCE_IMAGE_INDEX, REFERENCE_BUFFER_VIEW, {k: ref.get(k) for k in ('image_index', 'buffer_view')}))
    if ref.get('buffer_view') is None:
        problems.append('reference bufferView not recorded')
    by_path = {t.get('asset_path'): t for t in parity.get('textures') or []}
    means, p99s = [], []
    for path in sorted(texture_paths):
        t = by_path.get(path)
        if t is None:
            problems.append('%s: not in the parity file' % path)
            continue
        if (t.get('width'), t.get('height')) != (ref.get('width'), ref.get('height')):
            problems.append('%s: %sx%s differs from reference %sx%s' % (path, t.get('width'), t.get('height'),
                                                                       ref.get('width'), ref.get('height')))
        diff = t.get('max_abs_diff_vs_reference_8bit')
        same_hash = t.get('decoded_rgba_sha256') == ref.get('decoded_rgba_sha256') and ref.get('decoded_rgba_sha256')
        if not same_hash:
            if diff is None or diff > 1 or (diff == 1 and not (t.get('reencode_proven') and t.get('reencode_note'))):
                problems.append('%s: pixels differ from GLB image %d (max abs diff %s, re-encode proven %s)' % (
                    path, REFERENCE_IMAGE_INDEX, diff, t.get('reencode_proven')))
        prov = t.get('source_provenance') or {}
        tied = (prov.get('glb_image_index') == REFERENCE_IMAGE_INDEX or prov.get('buffer_view') == REFERENCE_BUFFER_VIEW
                or glb_name in str(prov.get('import_source_file') or ''))
        if not tied:
            problems.append('%s: import provenance does not name the %s GLB or image %d: %s' % (
                path, glb_name, REFERENCE_IMAGE_INDEX, prov))
        if t.get('srgb') is not True:
            problems.append('%s: sRGB is %s, expected True for base colour' % (path, t.get('srgb')))
        if t.get('compression') not in ALLOWED_COMPRESSION:
            problems.append('%s: compression %s, expected TC_DEFAULT' % (path, t.get('compression')))
        if t.get('lod_bias') != 0:
            problems.append('%s: LOD bias %s, expected 0' % (path, t.get('lod_bias')))
        for key, want in ADJUST_DEFAULTS.items():
            have = (t.get('adjust') or {}).get(key)
            if have is None or abs(float(have) - want) > 1e-6:
                problems.append('%s: %s=%s, expected %s' % (path, key, have, want))
        stats = t.get('stats') or {}
        if stats.get('linear_mean') and stats.get('linear_p99'):
            means.append(stats['linear_mean'])
            p99s.append(stats['linear_p99'])
        else:
            problems.append('%s: stats missing' % path)
    if problems or not means:
        return problems or ['no texture stats'], None, None
    mean = [sum(m[i] for m in means) / len(means) for i in range(3)]
    p99 = [max(p[i] for p in p99s) for i in range(3)]
    return [], mean, p99


def main(argv=None):
    p = argparse.ArgumentParser(description='Texture parity export (editor, read only) and finalize (pure).')
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--export', type=Path, help='editor: export PNGs + settings into this EMPTY directory')
    mode.add_argument('--finalize', type=Path, help='pure: build the parity JSON from an export directory')
    p.add_argument('--texture', action='append', help='UE texture object path (default: the 4 bed textures)')
    p.add_argument('--glb', type=Path, help='full-home.glb for --finalize')
    p.add_argument('--image-index', type=int, default=REFERENCE_IMAGE_INDEX)
    p.add_argument('--quit', action='store_true')
    args = p.parse_args(argv)
    if args.finalize:
        if not args.glb:
            p.error('--finalize needs --glb')
        print(json.dumps(finalize(args.finalize, args.glb, args.image_index), indent=1))
        return 0
    import unreal as u  # noqa: N813
    try:
        export_textures(args.export, tuple(args.texture or BED_TEXTURES), u=u)
    finally:
        if args.quit:
            u.SystemLibrary.quit_editor()
    return 0


if __name__ == '__main__':
    sys.exit(main())
