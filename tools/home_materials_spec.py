"""Pure-Python material spec, measurement and validation for the SUB-01 home.

No ``unreal`` and no ``bpy`` imports. Used by tools/unreal_home_materials_fix.py
(editor side) and tests/test_home_materials_fix.py, and runnable on its own to
regenerate docs/proposed/home-materials-audit.json:

    python3 tools/home_materials_spec.py --audit docs/proposed/home-materials-audit.json

Scope and honesty notes
- The real full-home GLB used by Unreal (SourceAssets/full-home.glb on the
  private server) is NOT in this repository. This module measures the repo GLBs
  and the repo texture sets that the browser export and the Blender assembly
  embed into it, and reconstructs the factors that tools/assemble_home_blender.py
  and web/house/home.js write. ``audit_glb(path)`` audits any GLB, so root can
  run it on the real file (``--glb``).
- Measurements are texture statistics, never a visual comparison with the
  SimbasJungles reference; no visual match is claimed anywhere.
"""
import argparse
import colorsys
import hashlib
import io
import json
import math
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'web/house/assets'

# ---------------------------------------------------------------------------
# Colour maths (IEC 61966-2-1 sRGB transfer, Rec.709 luminance)
# ---------------------------------------------------------------------------
LUMA = (0.2126, 0.7152, 0.0722)
ALBEDO_MIN, ALBEDO_MAX = 0.04, 0.85   # linear, dielectric (see PHYSICAL_SOURCES)


def srgb_to_linear(c):
    c = float(c)
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c):
    c = max(0.0, float(c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def hex_to_srgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def hex_to_linear(h):
    return tuple(srgb_to_linear(c) for c in hex_to_srgb(h))


def luminance(rgb):
    return sum(w * c for w, c in zip(LUMA, rgb))


def hue_sat(rgb_linear):
    """Hue (deg) and HSV saturation of a linear colour, measured in sRGB-encoded space."""
    s = [linear_to_srgb(c) for c in rgb_linear]
    h, sat, _ = colorsys.rgb_to_hsv(*[min(1.0, x) for x in s])
    return round(h * 360.0, 1), round(sat, 4)


def chroma(rgb_linear):
    """Distance from the neutral axis, relative to luminance (0 = grey)."""
    y = luminance(rgb_linear)
    if y <= 0:
        return 0.0
    return math.sqrt(sum((c / y - 1.0) ** 2 for c in rgb_linear) / 3.0)


def mul(a, b):
    return tuple(x * y for x, y in zip(a, b))


def describe(rgb_linear):
    h, s = hue_sat(rgb_linear)
    return {'linear': [round(c, 4) for c in rgb_linear], 'srgb_hex': '#' + ''.join(
        '%02x' % round(255 * min(1.0, linear_to_srgb(c))) for c in rgb_linear),
        'luminance': round(luminance(rgb_linear), 4), 'hue_deg': h, 'saturation': s,
        'chroma': round(chroma(rgb_linear), 4)}


# ---------------------------------------------------------------------------
# GLB parsing (stdlib); meshopt-compressed views go through the existing
# tools/uncompress_unreal_glb.mjs readGLB/viewBytes (no new codec).
# ---------------------------------------------------------------------------
def read_glb(path):
    raw = Path(path).read_bytes()
    if raw[:4] != b'glTF':
        raise ValueError('not a GLB: %s' % path)
    doc, binary, p = None, b'', 12
    while p < len(raw):
        size, kind = struct.unpack_from('<II', raw, p)
        chunk = raw[p + 8:p + 8 + size]
        if kind == 0x4E4F534A:
            doc = json.loads(chunk)
        elif kind == 0x004E4942:
            binary = chunk
        p += 8 + size
    return doc, binary, hashlib.sha256(raw).hexdigest()


_NODE_VIEW = r"""
import {readGLB, viewBytes} from %s;
const f = readGLB(process.argv[1]);
const out = await viewBytes(f, Number(process.argv[2]));
process.stdout.write(out);
"""


def view_bytes(path, doc, binary, index):
    view = doc['bufferViews'][index]
    if (view.get('extensions') or {}).get('EXT_meshopt_compression'):
        helper = json.dumps((ROOT / 'tools/uncompress_unreal_glb.mjs').as_uri())
        result = subprocess.run(['node', '--input-type=module', '-e', _NODE_VIEW % helper, '--',
                                 str(path), str(index)], capture_output=True, check=True)
        return result.stdout
    start = view.get('byteOffset', 0)
    return binary[start:start + view['byteLength']]


_COMP = {5120: ('b', 1), 5121: ('B', 1), 5122: ('h', 2), 5123: ('H', 2), 5125: ('I', 4), 5126: ('f', 4)}
_NCOMP = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}


def read_accessor(path, doc, binary, index, cache=None):
    acc = doc['accessors'][index]
    if acc.get('sparse'):
        raise ValueError('sparse accessor unsupported')
    fmt, width = _COMP[acc['componentType']]
    n = _NCOMP[acc['type']]
    cache = {} if cache is None else cache
    key = acc['bufferView']
    if key not in cache:
        cache[key] = view_bytes(path, doc, binary, key)
    data = cache[key]
    stride = doc['bufferViews'][key].get('byteStride') or width * n
    off = acc.get('byteOffset', 0)
    out = []
    for i in range(acc['count']):
        vals = struct.unpack_from('<' + fmt * n, data, off + i * stride)
        if acc.get('normalized'):
            scale = {'b': 127.0, 'B': 255.0, 'h': 32767.0, 'H': 65535.0}.get(fmt, 1.0)
            vals = tuple(max(-1.0, v / scale) for v in vals)
        out.append(vals)
    return out


def image_bytes(path, doc, binary, image_index):
    img = doc['images'][image_index]
    if 'bufferView' in img:
        return view_bytes(path, doc, binary, img['bufferView'])
    return (Path(path).parent / img['uri']).read_bytes()


def texture_stats(data, kind='color'):
    """Mean sRGB / linear colour, hue and saturation of the texture itself (PIL+numpy)."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:  # pragma: no cover
        return {'unavailable': 'PIL/numpy missing'}
    image = Image.open(io.BytesIO(data) if isinstance(data, (bytes, bytearray)) else data)
    a = np.asarray(image.convert('RGB'), dtype=np.float64) / 255.0
    stats = {'size': list(image.size), 'mode': image.mode}
    if kind == 'color':
        lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
        mean = tuple(float(x) for x in lin.reshape(-1, 3).mean(0))
        y = lin @ np.array(LUMA)
        stats.update({'srgb_mean_8bit': [round(float(x) * 255, 1) for x in a.reshape(-1, 3).mean(0)],
                      'linear_mean': describe(mean),
                      'luminance_p01_p99': [round(float(np.percentile(y, 1)), 4), round(float(np.percentile(y, 99)), 4)],
                      'linear_p99': [round(float(np.percentile(lin[..., c], 99)), 4) for c in range(3)]})
    elif kind == 'roughness':
        g = a[..., 1]
        stats.update({'green_mean': round(float(g.mean()), 4), 'green_sd': round(float(g.std()), 4),
                      'green_p05_p95': [round(float(np.percentile(g, 5)), 4), round(float(np.percentile(g, 95)), 4)]})
    else:
        stats.update({'mean_rgb': [round(float(x), 4) for x in a.reshape(-1, 3).mean(0)]})
    return stats


def triangle_area_and_uv_density(path, doc, binary, prim, cache):
    """World-agnostic: object-space area (m^2), UV area and sqrt(UV area / area) = UV units per metre."""
    attrs = prim['attributes']
    pos = read_accessor(path, doc, binary, attrs['POSITION'], cache)
    uv = read_accessor(path, doc, binary, attrs['TEXCOORD_0'], cache) if 'TEXCOORD_0' in attrs else None
    idx = (read_accessor(path, doc, binary, prim['indices'], cache) if 'indices' in prim
           else [(i,) for i in range(len(pos))])
    idx = [i[0] for i in idx]
    area = uv_area = 0.0
    for t in range(0, len(idx) - 2, 3):
        a, b, c = (pos[idx[t + k]] for k in range(3))
        ab = [b[i] - a[i] for i in range(3)]
        ac = [c[i] - a[i] for i in range(3)]
        cr = (ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0])
        area += 0.5 * math.sqrt(sum(x * x for x in cr))
        if uv:
            p, q, r = (uv[idx[t + k]] for k in range(3))
            uv_area += 0.5 * abs((q[0] - p[0]) * (r[1] - p[1]) - (r[0] - p[0]) * (q[1] - p[1]))
    return area, uv_area


def audit_glb(path, with_geometry=True, with_textures=True):
    """Every material: users, factors, maps, extensions, texture stats, UV density."""
    path = Path(path)
    doc, binary, sha = read_glb(path)
    cache = {}
    users = {}
    geometry = {}
    for mi, mesh in enumerate(doc.get('meshes', [])):
        for prim in mesh['primitives']:
            m = prim.get('material')
            users.setdefault(m, []).append(mesh.get('name', 'mesh_%d' % mi))
            if with_geometry:
                try:
                    area, uv_area = triangle_area_and_uv_density(path, doc, binary, prim, cache)
                except (KeyError, ValueError, subprocess.CalledProcessError) as error:
                    area, uv_area = None, None
                    geometry.setdefault(m, {})['error'] = str(error)
                g = geometry.setdefault(m, {'area_m2': 0.0, 'uv_area': 0.0})
                if area is not None:
                    g['area_m2'] += area
                    g['uv_area'] += uv_area
    tex_cache = {}

    def tex(info, kind):
        if info is None:
            return None
        t = doc['textures'][info['index']]
        src = t.get('source')
        for ext in ('EXT_texture_webp', 'KHR_texture_basisu'):
            src = (t.get('extensions') or {}).get(ext, {}).get('source', src)
        out = {'texture': info['index'], 'image': src, 'texCoord': info.get('texCoord', 0),
               'name': (doc['images'][src].get('name') if src is not None else None),
               'texture_transform': (info.get('extensions') or {}).get('KHR_texture_transform')}
        if with_textures and src is not None:
            key = (src, kind)
            if key not in tex_cache:
                try:
                    tex_cache[key] = texture_stats(image_bytes(path, doc, binary, src), kind)
                except Exception as error:  # noqa: BLE001 - audit must not abort on one image
                    tex_cache[key] = {'error': str(error)}
            out['stats'] = tex_cache[key]
        return out

    materials = []
    for i, m in enumerate(doc.get('materials', [])):
        pbr = m.get('pbrMetallicRoughness', {})
        factor = tuple(pbr.get('baseColorFactor', [1, 1, 1, 1])[:3])
        entry = {'index': i, 'name': m.get('name', ''), 'users': users.get(i, []),
                 'baseColorFactor': list(factor), 'baseColorFactor_desc': describe(factor),
                 'metallicFactor': pbr.get('metallicFactor', 1.0), 'roughnessFactor': pbr.get('roughnessFactor', 1.0),
                 'baseColorTexture': tex(pbr.get('baseColorTexture'), 'color'),
                 'metallicRoughnessTexture': tex(pbr.get('metallicRoughnessTexture'), 'roughness'),
                 'normalTexture': tex(m.get('normalTexture'), 'normal'),
                 'normalScale': (m.get('normalTexture') or {}).get('scale'),
                 'extensions': sorted((m.get('extensions') or {}).keys()),
                 'extension_values': m.get('extensions') or {}}
        stats = (entry['baseColorTexture'] or {}).get('stats') or {}
        if 'linear_mean' in stats:
            entry['effective_mean_albedo'] = describe(mul(factor, stats['linear_mean']['linear']))
        else:
            entry['effective_mean_albedo'] = describe(factor)
        g = geometry.get(i)
        if g and g.get('area_m2'):
            uvpm = math.sqrt(g['uv_area'] / g['area_m2']) if g['area_m2'] else 0
            tt = (entry['baseColorTexture'] or {}).get('texture_transform') or {}
            scale = tt.get('scale', [1, 1])
            uvpm_eff = uvpm * math.sqrt(abs(scale[0] * scale[1]))
            entry['geometry'] = {'object_space_area_m2': round(g['area_m2'], 4),
                                 'uv_units_per_metre': round(uvpm, 4),
                                 'cm_per_texture_repeat': round(100 / uvpm_eff, 2) if uvpm_eff else None,
                                 'note': 'object space, before node scale'}
        entry['flags'] = flat_flags(entry)
        materials.append(entry)
    return {'file': str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path), 'sha256': sha,
            'extensionsUsed': doc.get('extensionsUsed', []), 'materials': materials}


def flat_flags(entry):
    flags = []
    if not entry['normalTexture']:
        flags.append('no_normal_map')
    if not entry['metallicRoughnessTexture']:
        flags.append('constant_roughness')
    if not entry['baseColorTexture']:
        flags.append('no_albedo_variation')
    if len(flags) == 3:
        flags.append('plastic_flat_candidate')
    metal = entry['metallicFactor']
    if 0.05 < metal < 0.95:
        flags.append('nonphysical_partial_metal')
    y = entry['effective_mean_albedo']['luminance']
    if metal < 0.5 and not (ALBEDO_MIN <= y <= ALBEDO_MAX):
        flags.append('albedo_out_of_range')
    return flags


# ---------------------------------------------------------------------------
# Repo texture sets (Poly Haven CC0 scans and CC0 haven-sofa maps)
# ---------------------------------------------------------------------------
TEXTURE_SETS = {
    # name: (folder, coverage metres per tile (None = unknown), licence)
    'home_oak_floor': ('home_oak_floor', 1.2, 'CC0-1.0 Poly Haven oak_wood_planks'),
    'home_oak_veneer': ('home_oak_veneer', 1.83, 'CC0-1.0 Poly Haven (see provenance.json)'),
    'fine_grained_wood': ('fine_grained_wood', None, 'CC0-1.0 Poly Haven fine_grained_wood'),
    'rough_linen': ('rough_linen', None, 'CC0-1.0 Poly Haven rough_linen'),
    'quatrefoil_jacquard_fabric': ('quatrefoil_jacquard_fabric', None, 'CC0-1.0 Poly Haven quatrefoil_jacquard_fabric'),
    'white_plaster_02': ('white_plaster_02', None, 'CC0-1.0 Poly Haven white_plaster_02'),
    'interior_tiles': ('interior_tiles', None, 'CC0-1.0 Poly Haven interior_tiles'),
    'marble_01': ('marble_01', None, 'CC0-1.0 Poly Haven marble_01'),
    'marble_slab_012': ('marble_slab_012', None, 'CC0-1.0 (repo manifest)'),
    'haven_linen': ('haven-sofa/maps', None, 'CC0-1.0 Innerscene Haven 224 (texture-manifest.json)'),
}


def texture_set_stats(name):
    folder, coverage, licence = TEXTURE_SETS[name]
    base = ASSETS / folder
    prefix = 'linen_' if name == 'haven_linen' else ''
    files = {'diff': prefix + ('basecolor.jpg' if prefix else 'diff.jpg'),
             'rough': prefix + ('roughness.jpg' if prefix else 'rough.jpg'),
             'normal': prefix + 'normal.jpg'}
    out = {'folder': 'web/house/assets/' + folder, 'licence': licence, 'coverage_m': coverage}
    for key, kind in (('diff', 'color'), ('rough', 'roughness'), ('normal', 'normal')):
        p = base / files[key]
        out[key] = texture_stats(p.open('rb'), kind) if p.is_file() else None
    neutral = base / 'neutral.jpg'
    if neutral.is_file():
        out['neutral'] = texture_stats(neutral.open('rb'), 'color')
    return out


# ---------------------------------------------------------------------------
# Measured queen-bed facts (tools/assemble_home_blender.py lines 380-388)
# ---------------------------------------------------------------------------
BED_TINTS = {'teal': '#b99845', 'other_upholstery': '#f7f4eb', 'wood': '#e7dcc9'}
BED_ASSEMBLE_LINES = [
    "upholstery = 'upholstery' in material.name",
    "tint = '#b99845' if 'teal' in material.name else '#f7f4eb'",
    "set_base(material, tint if upholstery else '#e7dcc9',",
    "         linen_image if upholstery else oak_image, 2 if upholstery else 1)",
    "set_roughness(material, .92 if upholstery else .82, old_factor)",
]


def tint_product(tint_hex, texture_linear_mean):
    """Mean result of a base-colour tint times a texture, three ways."""
    t_lin = hex_to_linear(tint_hex)
    t_srgb = hex_to_srgb(tint_hex)
    tex_srgb = tuple(linear_to_srgb(c) for c in texture_linear_mean)
    correct = mul(t_lin, texture_linear_mean)                         # glTF/UE: linear factor x linear texel
    srgb_multiplied = tuple(srgb_to_linear(c) for c in mul(t_srgb, tex_srgb))  # multiply in display space
    double_linearised = mul(tuple(srgb_to_linear(c) for c in t_lin), texture_linear_mean)  # factor linearised twice
    return {'tint': tint_hex, 'tint_linear': describe(t_lin), 'texture_mean': describe(texture_linear_mean),
            'linear_product (correct glTF)': describe(correct),
            'srgb_space_product': describe(srgb_multiplied),
            'tint_double_linearised': describe(double_linearised),
            'tint_alone_no_texture': describe(t_lin)}


def bed_tint_analysis():
    linen = texture_set_stats('rough_linen')['diff']['linear_mean']['linear']
    doc, binary, _ = read_glb(ASSETS / 'cc0-queen-bed/queen-bed.glb')
    src = {}
    for m in doc['materials']:
        info = m['pbrMetallicRoughness'].get('baseColorTexture')
        if info:
            img = doc['textures'][info['index']]['source']
            st = texture_stats(image_bytes(ASSETS / 'cc0-queen-bed/queen-bed.glb', doc, binary, img), 'color')
            src[m['name']] = st['linear_mean']['linear']
    return {
        'assemble_lines': BED_ASSEMBLE_LINES,
        'linen_image_note': ("assemble_home_blender.py:203 linen_image = base_image(pillow.data.materials[0]); in the V4 "
                             "export the pillow uses M.linen = pbr('rough_linen') (home.js:193), whose diff.jpg is "
                             "measured below. If the native pillow texture differs, rerun --glb on the real file."),
        'teal_with_rough_linen': tint_product(BED_TINTS['teal'], linen),
        'cream_with_rough_linen': tint_product(BED_TINTS['other_upholstery'], linen),
        'teal_with_original_teal_texture': tint_product(BED_TINTS['teal'], src['Original teal upholstery']),
        'cream_with_original_cream_texture': tint_product(BED_TINTS['other_upholstery'], src['Original cream upholstery']),
        'source_group_textures': {k: describe(v) for k, v in src.items()},
    }


def source_bed_groups():
    """Primitive -> material groups of the repo queen-bed GLB (the source the assembly imports)."""
    doc, _, sha = read_glb(ASSETS / 'cc0-queen-bed/queen-bed.glb')
    return {'file': 'web/house/assets/cc0-queen-bed/queen-bed.glb', 'sha256': sha,
            'groups': {mesh['name']: [doc['materials'][p['material']]['name'] for p in mesh['primitives']]
                       for mesh in doc['meshes']}}


BED_GROUP_ROLE = {  # from measured object-space bounds below (queen-bed.glb, Y up, headboard at -Z)
    'Original walnut grain': 'frame (rails/legs), non-upholstery -> oak image #e7dcc9 rough .82',
    'Original teal upholstery': 'HEADBOARD panel only (6.5 cm thick at z=-1.11..-1.05, 0.25..1.27 m high) -> #b99845',
    'Original cream upholstery': 'mattress (full length, 0.38..0.60 m) -> #f7f4eb',
    'Original linen upholstery': 'pillows (z -0.89..-0.45) -> #f7f4eb',
    'Original blue_fabric upholstery': 'duvet/cover (z -0.47..+1.00, top 0.70 m) -> #f7f4eb',
    'Original oak grain': 'slats (0.355..0.38 m), non-upholstery -> oak image #e7dcc9 rough .82',
}


def bed_group_geometry():
    path = ASSETS / 'cc0-queen-bed/queen-bed.glb'
    doc, binary, _ = read_glb(path)
    cache, out = {}, {}
    for mesh in doc['meshes']:
        for prim in mesh['primitives']:
            name = doc['materials'][prim['material']]['name']
            area, uv_area = triangle_area_and_uv_density(path, doc, binary, prim, cache)
            acc = doc['accessors'][prim['attributes']['POSITION']]
            out[mesh['name']] = {'material': name, 'role': BED_GROUP_ROLE.get(name),
                                 'branch': 'upholstery' if 'upholstery' in name else 'oak',
                                 'assembled_tint': (BED_TINTS['teal'] if 'teal' in name else BED_TINTS['other_upholstery'])
                                 if 'upholstery' in name else BED_TINTS['wood'],
                                 'area_m2': round(area, 3), 'area_share': None,
                                 'bounds_min_m': [round(x, 3) for x in acc['min']],
                                 'bounds_max_m': [round(x, 3) for x in acc['max']],
                                 'uv_units_per_metre': round(math.sqrt(uv_area / area), 3)}
    total = sum(v['area_m2'] for v in out.values() if v['branch'] == 'upholstery')
    for v in out.values():
        if v['branch'] == 'upholstery':
            v['area_share'] = round(v['area_m2'] / total, 3)
    return out


def source_sofa_groups():
    doc, _, sha = read_glb(ASSETS / 'haven-sofa/source.glb')
    groups = {}
    for mesh in doc['meshes']:
        groups[mesh['name']] = [doc['materials'][p['material']]['name'] if 'material' in p else None
                                for p in mesh['primitives']]
    return {'file': 'web/house/assets/haven-sofa/source.glb', 'sha256': sha, 'groups': groups,
            'runtime_rule': ("home.js:601 object.material = havenSofaMaterials[object.name] || Haven_linen; "
                             "home.js:592-593 Haven_linen '#737e87', Haven_seams '#58616a'")}


REPO_GLBS = ['cc0-queen-bed/queen-bed.glb', 'cc0-porta-espresso/porta-espresso.glb',
             'kitchen-cabinet-original/cabinet.glb', 'keyboard/keyboard.glb', 'coffee-machine/coffee-machine.glb']


def build_audit():
    out = {'schema': 'sub01.home-materials-audit.v1',
           'scope': ('Repo-side measurements only. The real full-home.glb (server, sha 9556495f..., 110 materials) is '
                     'not in the repository: run `python3 tools/home_materials_spec.py --glb <full-home.glb>` there. '
                     'No visual comparison or match is claimed.'),
           'texture_sets': {name: texture_set_stats(name) for name in TEXTURE_SETS},
           'bed': {'source_groups': source_bed_groups(), 'group_geometry': bed_group_geometry(), 'tints': bed_tint_analysis()},
           'sofa': {'source_groups': source_sofa_groups()},
           'glbs': []}
    for rel in REPO_GLBS:
        out['glbs'].append(audit_glb(ASSETS / rel))
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--audit', type=Path, help='write the repo audit JSON here')
    p.add_argument('--glb', type=Path, help='audit any GLB (e.g. the real server full-home.glb) to stdout')
    args = p.parse_args(argv)
    if args.glb:
        print(json.dumps(audit_glb(args.glb), indent=1))
    if args.audit:
        args.audit.write_text(json.dumps(build_audit(), indent=1) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
