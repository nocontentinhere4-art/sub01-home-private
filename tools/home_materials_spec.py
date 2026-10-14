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
           'wood_scale': wood_scale_audit(),
           'presets': {name: plan([name]) for name in PRESETS},
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



# ---------------------------------------------------------------------------
# Physical reference ranges (sources noted; linear albedo, GGX roughness)
# ---------------------------------------------------------------------------
PHYSICAL_SOURCES = {
    'albedo_bounds': ('Dielectric albedo kept within ~0.04-0.85 linear (sRGB ~50-240): Allegorithmic/Adobe '
                      '"The PBR Guide" vol. 2 (2015-2018), and Lagarde & de Rousiers, "Moving Frostbite to PBR", '
                      'SIGGRAPH 2014 course notes (charcoal ~0.02-0.04, fresh snow ~0.8-0.9).'),
    'fabric_measured': ('In-repo measured CC0 scans: queen-bed source "Original cream upholstery" texture mean '
                        'Y 0.75; Haven oatmeal linen basecolor Y 0.49 (texture-manifest.json, no grading).'),
    'fabric_roughness': 'Woven cotton/linen: diffuse-dominated, GGX roughness ~0.8-1.0 (Frostbite 2014, cloth).',
    'oak_roughness': 'Oiled / lacquered oak: roughness ~0.35-0.6 (owner task brief; Poly Haven oak scan G mean 0.44).',
    'plaster_roughness': 'Matte interior paint/plaster: ~0.85-0.95 (Poly Haven white_plaster_02 rough mean 0.91).',
    'ceramic_roughness': 'Glazed ceramic/porcelain: ~0.05-0.25.',
    'metals_f0': ('Metals: metallic 1 with F0 as base colour (Hoffman, "Physics and Math of Shading", SIGGRAPH '
                  '2015: iron .56/.57/.58, aluminium .91/.92/.92); plastics/powdercoat are dielectrics, metallic 0.'),
    'dark_wood': 'Dark stained walnut-like wood: linear albedo Y ~0.04-0.10 (above the 0.04 floor).',
}

RANGES = {
    'plastic': {'albedo_Y': (0.01, 0.85), 'roughness': (0.3, 1.0)},
    'metal': {'albedo_Y': (0.0, 1.0), 'roughness': (0.0, 1.0)},
    'fabric': {'albedo_Y': (0.04, 0.85), 'roughness': (0.75, 1.0)},
    'oak': {'albedo_Y': (0.10, 0.50), 'roughness': (0.35, 0.60)},
    'dark_wood': {'albedo_Y': (0.04, 0.10), 'roughness': (0.35, 0.70)},
    'plaster': {'albedo_Y': (0.50, 0.85), 'roughness': (0.85, 0.97)},
    'ceramic': {'albedo_Y': (0.50, 0.85), 'roughness': (0.05, 0.25)},
}

# Parameter names this script will look for on the REAL parent, in order. Only a name the
# editor enumerates on the parent is ever used; none present -> the target is refused.
PARAM_CANDIDATES = {
    'base_color_factor': ('BaseColorFactor', 'Base Color Factor', 'BaseColor_Factor'),
    'base_color_texture': ('BaseColorTexture', 'Base Color Texture', 'BaseColor_Texture'),
    'roughness_factor': ('RoughnessFactor', 'Roughness Factor', 'Roughness_Factor'),
    'metallic_factor': ('MetallicFactor', 'Metallic Factor', 'Metallic_Factor'),
    'normal_scale': ('NormalScale', 'Normal Scale', 'NormalTexture_Scale'),
}


def tint_factor(texture_mean_linear, target_hex, target_luminance, texture_p99=None, cap=ALBEDO_MAX):
    """Per-channel linear factor so that factor x texture_mean = target chromaticity at target luminance.

    The texture's spatial variation is kept (it is multiplied, not replaced). If the brightest 1% of any
    channel would exceed ``cap``, the whole factor is scaled down uniformly (hue kept).
    Returns (factor, predicted_mean).
    """
    chroma_lin = hex_to_linear(target_hex)
    k = target_luminance / luminance(chroma_lin)
    target = tuple(c * k for c in chroma_lin)
    factor = [t / max(m, 1e-6) for t, m in zip(target, texture_mean_linear)]
    if texture_p99:
        worst = max(f * p for f, p in zip(factor, texture_p99))
        if worst > cap:
            factor = [f * cap / worst for f in factor]
    factor = tuple(round(f, 5) for f in factor)
    return factor, mul(factor, texture_mean_linear)


TEXTURE_SRGB = {'base_color': True, 'normal': False, 'roughness': False, 'metallic_roughness': False}
PARAM_CANDIDATES['normal_texture'] = ('NormalTexture', 'Normal Texture', 'Normal_Texture')

# Root's measurement of the real full-home.glb (2026-10-14): bed materials 98..101 all use
# Image_14, a 512x512 PNG, 8-bit sRGB mean [144.65, 170.4, 204.73], and carry NO baseColorFactor
# (the assembly's MixRGB tints were dropped by the Blender glTF export). The repo's lite
# rough_linen diff.jpg (the V4 export used the lite tier) has 8-bit mean [145.3, 171.3, 205.0],
# so its linear mean below stands in for Image_14.
REAL_BED_TEXTURE = {'image': 'Image_14', 'size': [512, 512], 'srgb_mean_8bit': [144.65, 170.4, 204.73],
                    'factor_present': False}
SOFA_PARTS = ('Haven_linen', 'Haven_seams', 'Haven_legs', 'Haven_felt')
SOFA_TINTS = {'Haven_linen': '#737e87', 'Haven_seams': '#58616a'}   # assemble_home_blender.py:401-404


def _linen_stats():
    path = ASSETS / 'lite/rough_linen/diff.jpg'
    d = texture_stats(path.open('rb'), 'color')
    return tuple(d['linear_mean']['linear']), tuple(d['linear_p99']), tuple(d['size'])


def _haven_stats():
    path = ASSETS / 'lite/haven-sofa/maps/linen_basecolor.jpg'
    if not path.is_file():
        path = ASSETS / 'haven-sofa/maps/linen_basecolor.jpg'
    d = texture_stats(path.open('rb'), 'color')
    return tuple(d['linear_mean']['linear']), tuple(d['linear_p99']), tuple(d['size'])


BED_SOURCES = ('Original teal upholstery', 'Original cream upholstery', 'Original linen upholstery',
               'Original blue_fabric upholstery')
BED_SIGNATURE = {'sizes': [[512, 512], [511, 512], [1024, 1026]],
                 'source': 'real Image_14 512x512 (root); repo rough_linen diff.jpg lite 511x512 / full 1024x1026'}


def _norm(name):
    import re
    s = re.sub(r'[^0-9a-z]+', '_', str(name).rsplit('/', 1)[-1].split('.')[0].lower()).strip('_')
    s = re.sub(r'^(mi|m|mat|material)_', '', s)
    return re.sub(r'(_\d{3})+$', '', s)


def intended_factor(target, material_path):
    """The linear factor a target wants on one ORIGINAL material (None: factor untouched)."""
    if 'factor' in target:
        return target['factor']
    if 'factors' not in target:
        return None
    key = _norm(material_path)
    for name, factor in target['factors'].items():
        if _norm(name) == key:
            return factor
    raise KeyError('%s has no factor for %s' % (target['id'], material_path))


def _bed_target(target_id, factors, why, optional, mean=None):
    if mean is None:
        mean, _, _ = _linen_stats()
    predicted = {k: {'before_real (factor lost, white)': describe(mean),
                     'after': describe(mul(v, mean))} for k, v in factors.items()}
    return {'id': target_id, 'class': 'fabric', 'match': 'material_name', 'source_materials': list(BED_SOURCES),
            'expected_materials': 4, 'same_texture': True, 'optional': optional, 'bed': True,
            'factors': {k: [round(c, 5) for c in v] for k, v in factors.items()},
            'texture_signature': BED_SIGNATURE, 'why': why, 'predicted': predicted,
            'texture_linear_mean_used': [round(c, 4) for c in mean]}


def preset_bed_intended():
    """Restore exactly the assembly's lost tints (linear factors), nothing else."""
    factors = {name: hex_to_linear(BED_TINTS['teal'] if 'teal' in name else BED_TINTS['other_upholstery'])
               for name in BED_SOURCES}
    return _bed_target('bed-intended', factors,
                       'assemble_home_blender.py:383 tints lost by the Blender glTF export; restored as linear '
                       'baseColorFactor. Note: ivory x blue linen is still blue-grey (#8da4bd).', False)


def preset_bed_balanced(measured=None):
    """OPTIONAL: same groups, factors also cancel the linen scan's blue cast (white balance).

    ``measured`` = {'linear_mean': [...], 'linear_p99': [...], 'source': str} from the texture parity file
    (the ACTUAL UE texture pixels). Without it the target is HELD: factors are only a repo-texture preview.
    """
    if measured:
        mean, p99 = tuple(measured['linear_mean']), tuple(measured['linear_p99'])
    else:
        mean, p99, _ = _linen_stats()
    factors = {}
    for name in BED_SOURCES:
        if 'teal' in name:
            factors[name] = tint_factor(mean, BED_TINTS['teal'], 0.20, p99)[0]
        else:
            factors[name] = tint_factor(mean, BED_TINTS['other_upholstery'], 0.62, p99)[0]
    target = _bed_target('bed-balanced', factors,
                         'Option for root: the intended hues (#f7f4eb ivory, #b99845 ochre headboard) after '
                         'cancelling the blue scan cast; ivory at Y 0.62 (CC0 cream upholstery scan Y 0.75, '
                         'linen Y 0.49), ochre at dyed-textile Y 0.20.', True, mean=mean)
    target['texture_mean_source'] = measured.get('source', 'parity') if measured else 'repo lite rough_linen (preview)'
    if not measured:
        target['held'] = 'awaiting the texture parity file: factors must come from the actual UE texture pixels'
    return target


def _sofa_target(part):
    mean, _, size = _haven_stats()
    factor = [round(c, 5) for c in hex_to_linear(SOFA_TINTS[part])]
    return {'id': 'sofa-intended-' + part.split('_')[1], 'class': 'fabric', 'match': 'actor_prefix',
            'actor_prefixes': [part], 'source_materials': [part], 'expected_materials': 1, 'optional': True,
            'factor': factor, 'texture_signature': None,
            'why': 'assemble_home_blender.py:401-404 tint %s, applied only if the inventory shows it lost '
                   '(white factor); refused if a different non-white factor is present.' % SOFA_TINTS[part],
            'predicted': {'before_if_lost': describe(mean), 'after': describe(mul(factor, mean))}}


def preset_darkwood():
    """M.darkwood (home.js:207/213, fine_grained_wood x #c5aa83) is far below the dielectric floor."""
    d = texture_set_stats('fine_grained_wood')['diff']
    mean, p99 = tuple(d['linear_mean']['linear']), tuple(d['linear_p99'])
    tint = hex_to_linear('#c5aa83')
    before = mul(tint, mean)
    target_y = 0.05
    k = target_y / luminance(before)
    factor = [round(c * k, 5) for c in tint]
    after = mul(factor, mean)
    return {'id': 'darkwood-albedo', 'class': 'dark_wood', 'match': 'factor_fingerprint',
            'fingerprint': [round(c, 5) for c in tint], 'source_materials': ['M.darkwood (unnamed in export)'],
            'expected_materials': 1, 'optional': True, 'factor': factor, 'factor_expect': [list(tint)],
            'texture_signature': {'sizes': [[1024, 1024], [512, 512]], 'source': 'fine_grained_wood diff.jpg'},
            'why': ('fine_grained_wood mean Y %.4f x #c5aa83 gives Y %.4f (below 0.04). Same hue, scaled to '
                    'Y 0.05 (dark walnut 0.04-0.10). Matched by its exact current factor, so only the material '
                    'that really carries #c5aa83 is touched; brightest 1%% texel %.3f.'
                    % (luminance(mean), luminance(before), max(f * p for f, p in zip(factor, p99)))),
            'predicted': {'before': describe(before), 'after': describe(after)}}


def _scalar_target(target_id, cls, names, param, value, expect, why):
    return {'id': target_id, 'class': cls, 'match': 'material_name', 'source_materials': list(names),
            'expected_materials': len(names), 'optional': True,
            'scalars': [{'param': param, 'value': value, 'expect': expect}], 'why': why, 'predicted': {}}


def preset_metals():
    """Dielectric/metal binarisation for named repo materials with non-physical metallic values."""
    return [
        _scalar_target('metal-keyboard-plastic', 'plastic', ['plastic_black'], 'metallic_factor', 0.0, [1.0],
                       'keyboard.glb plastic_black has metallic 1.0 and roughness 1.0: a plastic is a dielectric.'),
        _scalar_target('metal-espresso-powdercoat', 'plastic', ['Charcoal fine-textured powdercoat'],
                       'metallic_factor', 0.0, [0.25], 'Powder coat is a polymer film: dielectric (0.25 -> 0).'),
        _scalar_target('metal-espresso-steel', 'metal', ['Satin galvanized steel', 'Blackened steel mounting hardware',
                                                         'Satin champagne bronze'],
                       'metallic_factor', 1.0, [0.78, 0.75, 0.8],
                       'Bare metals are metallic 1 (Hoffman 2015); 0.75-0.8 mixes are non-physical.'),
    ]


def preset_bed_wood_roughness():
    return dict(_scalar_target('bed-wood-roughness', 'oak', ['Original walnut grain', 'Original oak grain'],
                               'roughness_factor', 0.5, [0.82],
                               'Assembly sets the queen-bed wood to roughness .82 (near matte); oiled/lacquered '
                               'oak 0.35-0.6, scan mean 0.44-0.53. Only applied if the real value is .82.'),
                bed=True)


PRESETS = {'bed-intended': preset_bed_intended, 'bed-balanced': preset_bed_balanced,
           'sofa-intended': lambda: [_sofa_target('Haven_linen'), _sofa_target('Haven_seams')],
           'darkwood-albedo': preset_darkwood,
           'metal-keyboard': lambda: preset_metals()[:1], 'metal-espresso': lambda: preset_metals()[1:],
           'bed-wood-roughness': preset_bed_wood_roughness}
DEFAULT_PRESETS = ('bed-intended',)


MEASURED_AWARE = ('bed-balanced',)


def plan(presets=DEFAULT_PRESETS, measured=None):
    unknown = [p for p in presets if p not in PRESETS]
    if unknown:
        raise ValueError('unknown preset(s): %s' % unknown)
    targets = []
    for p in dict.fromkeys(presets):
        made = PRESETS[p](measured) if p in MEASURED_AWARE else PRESETS[p]()
        targets.extend(made if isinstance(made, list) else [made])
    seen = {}
    for t in targets:
        for name in t['source_materials']:
            if name in seen:
                raise ValueError('duplicate target material %r in %s and %s' % (name, seen[name], t['id']))
            seen[name] = t['id']
    return {'schema': 'sub01.home-materials-plan.v1', 'presets': list(presets), 'targets': targets,
            'real_bed_texture': REAL_BED_TEXTURE, 'sources': PHYSICAL_SOURCES, 'visual_match_claimed': False}


def validate_target(target):
    """Physical-range check of predicted means and scalar overrides; returns a list of problems."""
    problems = []
    rng = RANGES[target['class']]
    pred = target.get('predicted') or {}
    afters = ([v['after'] for v in pred.values() if isinstance(v, dict) and 'after' in v]
              or ([pred['after']] if 'after' in pred else []))
    for after in afters:
        y = after['luminance']
        if not rng['albedo_Y'][0] <= y <= rng['albedo_Y'][1]:
            problems.append('%s predicted Y %.3f outside %s' % (target['id'], y, rng['albedo_Y']))
        if max(after['linear']) > ALBEDO_MAX:
            problems.append('%s channel above %.2f' % (target['id'], ALBEDO_MAX))
    for o in target.get('scalars', []):
        if o['param'] == 'roughness_factor' and not rng['roughness'][0] <= o['value'] <= rng['roughness'][1]:
            problems.append('%s roughness %.3f outside %s' % (target['id'], o['value'], rng['roughness']))
        if o['param'] == 'metallic_factor' and o['value'] not in (0.0, 1.0):
            problems.append('%s metallic %.2f is not binary' % (target['id'], o['value']))
    return problems


# ---------------------------------------------------------------------------
# Wood scale (texel density) maths
# ---------------------------------------------------------------------------
def plank_seams(path, axis=0, window=12, sigma=2.0, merge_px=10):
    """Pixel positions of dark plank seams across ``axis`` (0: seams are rows, planks run along x)."""
    import numpy as np
    from PIL import Image
    a = np.asarray(Image.open(path).convert('L'), dtype=np.float64)
    profile = a.mean(axis=1 - axis)
    n = len(profile)
    base = np.array([np.median(profile[max(0, i - window):i + window + 1]) for i in range(n)])
    d = profile - base
    thr = -sigma * float(np.std(d))
    out = []
    for i in range(1, n - 1):
        if d[i] < thr and d[i] <= d[i - 1] and d[i] <= d[i + 1]:
            if out and i - out[-1] < merge_px:
                if d[i] < d[out[-1]]:
                    out[-1] = i
            else:
                out.append(i)
    return out, n


def plank_width_cm(seams, pixels, coverage_m):
    """Median seam spacing converted to centimetres at the scan's physical coverage."""
    gaps = sorted(b - a for a, b in zip(seams, seams[1:]))
    if not gaps:
        return None
    mid = len(gaps) // 2
    median = gaps[mid] if len(gaps) % 2 else 0.5 * (gaps[mid - 1] + gaps[mid])
    return 100.0 * coverage_m * median / pixels


def cm_per_repeat(coverage_m=None, uv_per_metre=None, repeat=1.0):
    """World centimetres covered by one texture tile. Either the scan coverage (metric UVs:
    1 UV = coverage metres, e.g. home.js floor() repeat w/1.2), or measured UV units per metre."""
    if uv_per_metre:
        return 100.0 / (uv_per_metre * repeat)
    return 100.0 * coverage_m / repeat


def uv_tiling_for_plank(measured_width_cm, target_width_cm):
    """Tiling multiplier that turns the measured plank width into the target width."""
    return measured_width_cm / target_width_cm


def wood_scale_audit():
    out = {}
    for name in ('home_oak_floor', 'home_oak_veneer'):
        folder, coverage, _ = TEXTURE_SETS[name]
        seams, n = plank_seams(ASSETS / folder / 'diff.jpg', axis=0)
        out[name] = {'coverage_m': coverage, 'seams_px': seams, 'pixels': n,
                     'plank_width_cm': round(plank_width_cm(seams, n, coverage), 2) if len(seams) > 1 else None,
                     'reference': 'solid oak boards ~12-20 cm; Japanese composite flooring grooves 7.5 / 15 cm',
                     'note': 'seam detector: row-mean luminance dips > 2 sd below a 25 px running median'}
    out['floor_cm_per_repeat'] = cm_per_repeat(coverage_m=1.2, repeat=1.0)
    out['queen_bed_oak_cm_per_repeat'] = round(cm_per_repeat(uv_per_metre=0.99 / (1 * 1.83)), 1)
    return out


if __name__ == '__main__':
    raise SystemExit(main())
