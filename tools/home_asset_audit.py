#!/usr/bin/env python3
"""Static, CPU-only audit of the private home's furniture and material assets.

Reads only files already in the repository: glTF/GLB JSON and accessor
metadata, image headers, provenance sidecars and the browser material helper
modules. Nothing is decoded on a GPU, rendered, downloaded or modified.
Meshopt/Draco compressed assets are reported from their JSON accessor counts.

The ranking is a heuristic against the written SimbasJungles direction
(warm photographic Japanese/modern apartment: coherent light oak, linen and
plaster, believable metric scale, no placeholder boxes). It is a triage list
for the next modelling pass, not a visual comparison with the reference.

Usage:
    python tools/home_asset_audit.py [--root .] [--json out/home-asset-audit.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path('web/house/assets')
RUNTIME_SOURCES = ('web/house/home.js', 'web/house/*.mjs')
MATERIAL_HELPERS = ('web/house/*_material*.mjs', 'web/house/haven_sofa_materials.mjs',
                    'web/house/clean_oak_material.mjs', 'web/house/woven_rug_material.mjs',
                    'web/house/street_materials.mjs')
# Directories that are not furnishings: baked architecture, skinned body/clips
# and derived low-resolution copies of other assets.
NON_FURNISHING_DIRS = {'lighting', 'lighting-audit', 'first-person', 'lite', 'tokyo-residential',
                       'residential-street-pbr'}
# Materials whose role in home.js contradicts the light oak/linen/plaster palette.
OFF_PALETTE_MATERIALS = {'M.darkwood', 'M.wood'}
FURNISHING_MATERIALS = {'M.wood', 'M.darkwood', 'M.white', 'M.cream', 'M.black', 'M.kitchenOak',
                        'M.architectureOak', 'M.brass', 'M.metal'}
COMPRESSION_EXTENSIONS = {'EXT_meshopt_compression', 'KHR_draco_mesh_compression',
                          'KHR_meshopt_compression'}
MAX_FURNISHING_EXTENT_M = 4.0
MIN_FURNISHING_EXTENT_M = 0.03
PLACEHOLDER_TRIANGLES = 200
GLB_MAGIC = 0x46546C67

# ---------------------------------------------------------------- images

def image_size(data: bytes):
    """Return (width, height) from PNG, JPEG or WebP header bytes, else None."""
    if data[:8] == b'\x89PNG\r\n\x1a\n' and len(data) >= 24:
        return struct.unpack('>II', data[16:24])
    if data[:2] == b'\xff\xd8':
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            length = struct.unpack('>H', data[i + 2:i + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack('>HH', data[i + 5:i + 9])
                return w, h
            i += 2 + length
        return None
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        chunk = data[12:16]
        if chunk == b'VP8 ' and len(data) >= 30:
            w, h = struct.unpack('<HH', data[26:30])
            return w & 0x3FFF, h & 0x3FFF
        if chunk == b'VP8L' and len(data) >= 25:
            b = data[21:25]
            w = 1 + (((b[1] & 0x3F) << 8) | b[0])
            h = 1 + (((b[3] & 0x0F) << 10) | (b[2] << 2) | ((b[1] & 0xC0) >> 6))
            return w, h
        if chunk == b'VP8X' and len(data) >= 30:
            w = 1 + int.from_bytes(data[24:27], 'little')
            h = 1 + int.from_bytes(data[27:30], 'little')
            return w, h
    return None

# ---------------------------------------------------------------- glTF

def read_gltf(path: Path):
    """Return (json, bin_chunk_or_None) for .glb or .gltf files."""
    data = path.read_bytes()
    if path.suffix.lower() == '.glb':
        magic, version, length = struct.unpack('<III', data[:12])
        if magic != GLB_MAGIC:
            raise ValueError(f'{path}: not a GLB file')
        offset, doc, binary = 12, None, None
        while offset + 8 <= min(length, len(data)):
            chunk_len, chunk_type = struct.unpack('<II', data[offset:offset + 8])
            chunk = data[offset + 8:offset + 8 + chunk_len]
            if chunk_type == 0x4E4F534A:
                doc = json.loads(chunk.decode('utf-8'))
            elif chunk_type == 0x004E4942:
                binary = chunk
            offset += 8 + chunk_len
        if doc is None:
            raise ValueError(f'{path}: GLB without JSON chunk')
        return doc, binary
    return json.loads(data.decode('utf-8')), None


def _quat_matrix(q):
    x, y, z, w = q
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]


def node_matrix(node):
    """4x4 row-major local matrix of a glTF node."""
    if 'matrix' in node:
        m = node['matrix']  # column-major
        return [[m[c * 4 + r] for c in range(4)] for r in range(4)]
    t = node.get('translation', [0, 0, 0])
    r = _quat_matrix(node.get('rotation', [0, 0, 0, 1]))
    s = node.get('scale', [1, 1, 1])
    return [[r[i][0] * s[0], r[i][1] * s[1], r[i][2] * s[2], t[i]] for i in range(3)] + [[0, 0, 0, 1]]


def matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


IDENTITY = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]


def primitive_triangles(doc, prim):
    accessors = doc.get('accessors', [])
    mode = prim.get('mode', 4)
    if 'indices' in prim:
        count = accessors[prim['indices']].get('count', 0)
    else:
        count = accessors[prim['attributes']['POSITION']].get('count', 0) if 'POSITION' in prim.get('attributes', {}) else 0
    if mode == 4:
        return count // 3
    if mode in (5, 6):
        return max(0, count - 2)
    return 0


def world_bounds(doc):
    """Axis-aligned bounds in glTF metres (Y up) of all mesh nodes in the default scene."""
    accessors = doc.get('accessors', [])
    nodes = doc.get('nodes', [])
    scenes = doc.get('scenes', [])
    roots = scenes[doc.get('scene', 0)]['nodes'] if scenes else [
        i for i in range(len(nodes)) if not any(i in n.get('children', []) for n in nodes)]
    lo, hi = [math.inf] * 3, [-math.inf] * 3
    stack = [(i, IDENTITY) for i in roots]
    while stack:
        index, parent = stack.pop()
        node = nodes[index]
        world = matmul(parent, node_matrix(node))
        if 'mesh' in node:
            for prim in doc['meshes'][node['mesh']].get('primitives', []):
                pos = accessors[prim['attributes']['POSITION']] if 'POSITION' in prim.get('attributes', {}) else None
                if not pos or 'min' not in pos or 'max' not in pos:
                    continue
                for cx in (pos['min'][0], pos['max'][0]):
                    for cy in (pos['min'][1], pos['max'][1]):
                        for cz in (pos['min'][2], pos['max'][2]):
                            p = [sum(world[r][c] * v for c, v in enumerate((cx, cy, cz, 1))) for r in range(3)]
                            for k in range(3):
                                lo[k], hi[k] = min(lo[k], p[k]), max(hi[k], p[k])
        stack.extend((c, world) for c in node.get('children', []))
    if lo[0] == math.inf:
        return None
    return [lo, hi]


def image_bytes(doc, binary, image, base: Path):
    if 'uri' in image:
        uri = image['uri']
        if uri.startswith('data:'):
            return None, 'data-uri'
        path = (base / uri).resolve()
        return (path.read_bytes() if path.is_file() else None), str(path)
    if 'bufferView' in image and binary is not None:
        view = doc['bufferViews'][image['bufferView']]
        start = view.get('byteOffset', 0)
        return binary[start:start + view['byteLength']], 'embedded'
    return None, 'unresolved'


def audit_model(path: Path, root: Path):
    doc, binary = read_gltf(path)
    rel = path.relative_to(root).as_posix()
    extensions = sorted(doc.get('extensionsUsed', []))
    compressed = sorted(set(extensions) & COMPRESSION_EXTENSIONS)
    triangles = 0
    for mesh in doc.get('meshes', []):
        for prim in mesh.get('primitives', []):
            triangles += primitive_triangles(doc, prim)
    images = []
    for index, image in enumerate(doc.get('images', [])):
        data, where = image_bytes(doc, binary, image, path.parent)
        size = image_size(data) if data else None
        images.append({'index': index, 'source': image.get('uri', where), 'size': list(size) if size else None,
                       'sha256': hashlib.sha256(data).hexdigest() if data else None,
                       'missing': data is None})
    textures = doc.get('textures', [])

    def texture_image(info):
        if not info or info.get('index') is None or info['index'] >= len(textures):
            return None
        tex = textures[info['index']]
        source = tex.get('source')
        if source is None:
            for ext in tex.get('extensions', {}).values():
                source = ext.get('source', source)
        return source

    materials = []
    for mat in doc.get('materials', []):
        pbr = mat.get('pbrMetallicRoughness', {})
        entry = {
            'name': mat.get('name', ''),
            'base_color_map': texture_image(pbr.get('baseColorTexture')) is not None,
            'normal_map': texture_image(mat.get('normalTexture')) is not None,
            'roughness_map': texture_image(pbr.get('metallicRoughnessTexture')) is not None,
            'roughness_factor': pbr.get('roughnessFactor', 1.0),
            'metallic_factor': pbr.get('metallicFactor', 1.0),
        }
        entry['missing'] = [k for k in ('normal_map', 'roughness_map') if not entry[k]]
        materials.append(entry)
    bounds = world_bounds(doc)
    extent = [hi - lo for lo, hi in zip(*bounds)] if bounds else None
    return {
        'file': rel,
        'bytes': path.stat().st_size,
        'extensions': extensions,
        'compressed': compressed,
        'meshes': len(doc.get('meshes', [])),
        'nodes': len(doc.get('nodes', [])),
        'skins': len(doc.get('skins', [])),
        'animations': len(doc.get('animations', [])),
        'triangles': triangles,
        'materials': materials,
        'images': images,
        'bounds_m': bounds,
        'extent_m': extent,
    }

# ---------------------------------------------------------------- provenance

def manifest_files(root: Path):
    manifest = root / ASSETS / 'manifest.json'
    covered = {}
    if manifest.is_file():
        for entry in json.loads(manifest.read_text()):
            for f in entry.get('files', []):
                covered[f['file']] = entry.get('license', '')
    return covered


def provenance(asset_dir: Path, model: Path, root: Path, manifest: dict):
    rel_to_assets = model.relative_to(root / ASSETS).as_posix()
    if rel_to_assets.startswith('lite/'):
        # Lite copies inherit the provenance of the full-resolution asset they mirror.
        full = root / ASSETS / rel_to_assets[len('lite/'):]
        if full.is_file():
            return provenance(full.parent, full, root, manifest)
    sidecar = model.with_suffix('.json')
    if not sidecar.is_file() and model.stem.endswith('-lite'):
        sidecar = model.with_name(model.stem[:-len('-lite')] + '.json')
    sidecar_data = None
    if sidecar.is_file() and sidecar != model:
        try:
            sidecar_data = json.loads(sidecar.read_text())
        except json.JSONDecodeError:
            sidecar_data = None
    meta = sidecar_data if isinstance(sidecar_data, dict) else {}
    generator = meta.get('generator') or meta.get('builder')
    if generator:
        generator = str(generator).split()[0]
    generator_exists = bool(generator) and (root / generator).is_file()
    if not generator_exists:
        # Original Blender assets: find the builder that writes this directory.
        needles = (f"/{asset_dir.name}'", f'/{asset_dir.name}"', f"'{asset_dir.name}'", f'/{asset_dir.name}/')
        for g in sorted((root / 'tools').glob('*.py')):
            if any(n in g.read_text(errors='replace') for n in needles):
                generator, generator_exists = g.relative_to(root).as_posix(), True
                break
    declared_hash = meta.get('sha256')
    result = {
        'license_file': (asset_dir / 'LICENSE.txt').is_file(),
        'provenance_json': (asset_dir / 'provenance.json').is_file(),
        'sidecar_json': sidecar_data is not None,
        'sidecar_license': meta.get('license'),
        'manifest_listed': rel_to_assets in manifest,
        'manifest_license': manifest.get(rel_to_assets),
        'generator': generator,
        'generator_exists': generator_exists,
        'editable_blend': any(asset_dir.glob('*.blend')),
        'sidecar_sha256_matches': (None if not declared_hash else
                                   declared_hash == hashlib.sha256(model.read_bytes()).hexdigest()),
    }
    result['ok'] = bool(result['license_file'] or result['provenance_json'] or result['manifest_listed']
                        or result['sidecar_license'] or (result['sidecar_json'] and generator_exists))
    return result, sidecar_data


def sidecar_bounds_mismatch(sidecar, extent):
    """Compare Blender Z-up sidecar bounds with glTF Y-up extents (mm tolerance)."""
    if not isinstance(sidecar, dict) or not extent:
        return None
    b = sidecar.get('blender_bounds_m')
    if not (isinstance(b, list) and len(b) == 2 and all(isinstance(v, list) and len(v) == 3 for v in b)):
        return None
    dims = [b[1][i] - b[0][i] for i in range(3)]
    expected = [dims[0], dims[2], dims[1]]  # Blender X,Y,Z -> glTF X,Z(up),Y
    worst = max(abs(e - a) for e, a in zip(expected, extent))
    return round(worst, 6)

# ---------------------------------------------------------------- runtime and helpers

def runtime_text(root: Path):
    parts = []
    for pattern in RUNTIME_SOURCES:
        for path in sorted(root.glob(pattern)):
            parts.append(path.read_text(errors='replace'))
    return '\n'.join(parts)


def runtime_references(text: str, asset_dir: str, model: Path):
    name = model.stem
    needles = [f'assets/{asset_dir}/{model.name}', f"'{asset_dir}/", f'"{asset_dir}/',
               f"furnished('{asset_dir}'", f'furnished("{asset_dir}"']
    if asset_dir == name:
        needles += [f"'{name}'", f'"{name}"']
    return any(n in text for n in needles)


BOX_CALL = re.compile(r'^\s*(?:(?:const|let)\s+(\w+)\s*=\s*\[?)?box\(\s*([-\d.]+),\s*([-\d.]+),\s*([-\d.]+),\s*'
                      r'([-\d.]+),\s*([-\d.]+),\s*([-\d.]+),\s*([\w.]+)')
OBSTACLE_CALL = re.compile(r'^\s*obstacle\(\s*([-\d.]+),\s*([-\d.]+),\s*([-\d.]+),\s*([-\d.]+)(?:,\s*(\d+))?\)')
# Interior plan of the house in runtime metres (x, z); anything outside is street/skyline.
INTERIOR_XZ = ((-4.2, 4.2), (-4.2, 5.6))
DEVICE_MATERIALS = {'M.black', 'M.metal'}
FURNISHED_CALL = re.compile(r'furnished\(\s*[\'"]([\w-]+)[\'"]\s*,\s*([-\d.]+),\s*([-\d.]+),\s*([-\d.]+),\s*([-\d.]+)')
# Hand-identified from home.js coordinates (runtime x, floor y, z) so the
# report names fixtures that have no preceding comment.
KNOWN_FIXTURE_HINTS = {
    (-3.5, 3.3, 1.1): 'loft bathroom vanity (oak box, white top, basin cylinder)',
    (-2.9, 3.3, 2.23): 'loft bathroom toilet (three white boxes)',
    (-0.85, 4.05, 1.35): 'loft bathroom door leaf',
    (-1.2, 3.5, 4.5): 'balcony reading chair',
    (2.0, 1.0, -3.3): 'office monitor shell and stand',
    (-3.8, 1.65, -0.05): 'lounge TV shell',
}


def _label(lines, first_line, name):
    for back in range(1, 7):
        index = first_line - 1 - back
        if index < 0:
            break
        text = lines[index].strip()
        if text.startswith('//'):
            return text.lstrip('/ ').strip()[:120]
    return name or 'unlabelled'


def procedural_box_furnishings(home_js: Path):
    """Group literal box() calls with furnishing materials into placeholder clusters.

    Fallbacks (hidden once the real asset loads), removed templates, exterior
    blocks and device shells are retained but classified so they rank lower.
    """
    if not home_js.is_file():
        return []
    lines = home_js.read_text(errors='replace').splitlines()
    clusters, current, in_fallback_array = [], None, False
    for number, line in enumerate(lines, 1):
        opener = re.search(r'[Ff]allback\w*\s*=\s*\[(.*)$', line)
        if opener and ']' not in opener.group(1):
            in_fallback_array = True
        m = BOX_CALL.match(line)
        same_line_fallback = bool(opener)
        if in_fallback_array and re.match(r'^\s*\]', line):
            in_fallback_array = False
        if not m:
            continue
        name = m.group(1)
        if same_line_fallback and not name:
            name = re.search(r'(\w*[Ff]allback\w*)', line).group(1)
        w, h, d, x, y, z = (float(v) for v in m.groups()[1:7])
        material = m.group(8)
        if material not in FURNISHING_MATERIALS or max(w, h, d) > 2.5 or (w * h * d) < 2e-4:
            continue
        part = {'line': number, 'name': name, 'size_m': [w, h, d], 'centre_m': [x, y, z], 'material': material,
                'fallback': in_fallback_array or 'allback' in (name or '')}
        def xz_gap(a, b):
            gaps = [abs(a['centre_m'][i] - b['centre_m'][i]) - (a['size_m'][i] + b['size_m'][i]) / 2 for i in (0, 2)]
            return max(0.0, max(gaps))
        if (current and number - current['parts'][-1]['line'] <= 3
                and part['fallback'] == current['parts'][0]['fallback']
                and min(xz_gap(part, other) for other in current['parts']) <= .3):
            current['parts'].append(part)
        else:
            current = {'parts': [part]}
            clusters.append(current)
    obstacles = []
    for number, line in enumerate(lines, 1):
        m = OBSTACLE_CALL.match(line)
        if m:
            x, z, w, d = (float(v) for v in m.groups()[:4])
            obstacles.append({'line': number, 'x': x, 'z': z, 'width': w, 'depth': d,
                              'level': int(m.group(5) or 0)})
    loaded = []
    for number, line in enumerate(lines, 1):
        m = FURNISHED_CALL.search(line)
        if m:
            loaded.append({'line': number, 'name': m.group(1), 'x': float(m.group(2)), 'y': float(m.group(3)),
                           'z': float(m.group(4)), 'width': float(m.group(5))})
    for cluster in clusters:
        parts = cluster['parts']
        first, last = parts[0]['line'], parts[-1]['line']
        lo = [min(p['centre_m'][i] - p['size_m'][i] / 2 for p in parts) for i in range(3)]
        hi = [max(p['centre_m'][i] + p['size_m'][i] / 2 for p in parts) for i in range(3)]
        cluster['lines'] = [first, last]
        cluster['bounds_m'] = [[round(v, 4) for v in lo], [round(v, 4) for v in hi]]
        cluster['materials'] = sorted({p['material'] for p in parts})
        cx, cz = (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2
        near = [o for o in obstacles if abs(o['x'] - cx) <= .3 and abs(o['z'] - cz) <= .3
                and -12 <= o['line'] - last <= 12]
        near.sort(key=lambda o: abs(o['line'] - last))
        cluster['collider'] = near[0] if near else None
        names = [p['name'] for p in parts if p['name']]
        hint = next((label for (hx, hy, hz), label in KNOWN_FIXTURE_HINTS.items()
                     if abs(hx - cx) <= .25 and abs(hz - cz) <= .25 and lo[1] - .05 <= hy <= hi[1] + .05), None)
        cluster['label'] = hint or _label(lines, first, names[0] if names else None)
        # A scanned/authored asset placed at the same spot makes the boxes redundant
        # and likely interpenetrating, not merely low fidelity.
        cluster['overlapping_assets'] = [
            a['name'] for a in loaded
            if lo[0] - .1 <= a['x'] <= hi[0] + .1 and lo[2] - .1 <= a['z'] <= hi[2] + .1
            and lo[1] - .6 <= a['y'] <= hi[1]]
        follow = '\n'.join(lines[last:last + 2])
        if all(p['fallback'] for p in parts):
            role = 'fallback'
        elif any(f'scene.remove({n})' in follow for n in names):
            role = 'template'
        elif not (INTERIOR_XZ[0][0] <= cx <= INTERIOR_XZ[0][1] and INTERIOR_XZ[1][0] <= cz <= INTERIOR_XZ[1][1]):
            role = 'exterior'
        elif set(cluster['materials']) <= DEVICE_MATERIALS:
            role = 'device-shell'
        else:
            role = 'visible-furnishing'
        cluster['role'] = role
    return clusters


MATERIAL_BLOCK = re.compile(r'new\s+T\.(MeshPhysicalMaterial|MeshStandardMaterial)\s*\(\s*\{(.*?)\}\s*\)', re.S)


def audit_material_helpers(root: Path):
    seen, reports = set(), []
    for pattern in MATERIAL_HELPERS:
        for path in sorted(root.glob(pattern)):
            if path in seen:
                continue
            seen.add(path)
            text = path.read_text(errors='replace')
            materials = []
            for m in MATERIAL_BLOCK.finditer(text):
                body = m.group(2)
                rough = re.search(r'roughness\s*:\s*([-\d.]+)', body)
                normal_scale = re.search(r'normalScale\s*:\s*new\s+T\.Vector2\(\s*([-\d.\w]+)', body)
                materials.append({
                    'type': m.group(1),
                    'map': bool(re.search(r'\bmap\s*[:,]', body)),
                    'normal_map': 'normalMap' in body,
                    'roughness_map': 'roughnessMap' in body or 'roughnessFactor' in text,
                    'roughness': float(rough.group(1)) if rough else None,
                    'normal_scale': normal_scale.group(1) if normal_scale else None,
                })
            textures = sorted(set(re.findall(r"['\"`]([\w/.${}-]+\.(?:jpg|png|webp))['\"`]", text)))
            flags = []
            for i, mat in enumerate(materials):
                if not mat['map'] and not mat['normal_map']:
                    flags.append(f'material #{i} ({mat["type"]}) is a flat colour without texture or normal detail')
                elif not mat['normal_map']:
                    flags.append(f'material #{i} has colour map but no normal map')
            if 'roughnessMap=null' in text.replace(' ', ''):
                flags.append('drops scanned roughness map in favour of a constant roughness')
            reports.append({'file': path.relative_to(root).as_posix(), 'materials': materials,
                            'texture_refs': textures, 'flags': flags})
    return reports


def texture_libraries(root: Path, manifest: dict):
    """Shared PBR texture sets (directories of diff/normal/rough images)."""
    libs = []
    base = root / ASSETS
    for d in sorted(p for p in base.iterdir() if p.is_dir()):
        imgs = sorted(f for f in d.iterdir() if f.suffix.lower() in ('.jpg', '.png', '.webp'))
        if not imgs or any(d.glob('*.gl*')):
            continue
        names = ' '.join(f.stem.lower() for f in imgs)
        maps = {k: any(t in names for t in tokens) for k, tokens in {
            'color': ('diff', 'color', 'albedo', 'basecolor'), 'normal': ('normal', 'nor'),
            'roughness': ('rough', 'arm')}.items()}
        sizes = {f.name: list(image_size(f.read_bytes()[:65536]) or ()) for f in imgs}
        rel = [f.relative_to(base).as_posix() for f in imgs]
        libs.append({'dir': d.relative_to(root).as_posix(), 'maps': maps, 'sizes': sizes,
                     'provenance': (d / 'provenance.json').is_file() or (d / 'manifest.json').is_file()
                     or any(r in manifest for r in rel),
                     'lite_variant': (base / 'lite' / d.name).is_dir()})
    return libs

# ---------------------------------------------------------------- scoring

def score_model(entry):
    reasons, score = [], 0
    if entry['triangles'] <= PLACEHOLDER_TRIANGLES and entry['meshes'] <= 1 and len(entry['materials']) <= 1:
        score += 5
        reasons.append(f'placeholder-like: {entry["triangles"]} triangles, single mesh/material')
    ext = entry.get('extent_m')
    if ext and (max(ext) > MAX_FURNISHING_EXTENT_M or max(ext) < MIN_FURNISHING_EXTENT_M):
        score += 2
        reasons.append('non-metric extent %.3f m; runtime must rescale' % max(ext))
    if entry['materials']:
        missing_normal = [m['name'] for m in entry['materials'] if not m['normal_map']]
        missing_rough = [m['name'] for m in entry['materials'] if not m['roughness_map']]
        if missing_normal:
            score += 1
            reasons.append('materials without normal map: ' + ', '.join(missing_normal[:4]))
        if missing_rough:
            score += 0.5
            reasons.append('materials without roughness map: ' + ', '.join(missing_rough[:4]))
    else:
        reasons.append('no glTF materials: runtime assigns shared house materials by mesh name')
    small = [i['size'] for i in entry['images'] if i['size'] and max(i['size']) < 1024]
    if small:
        score += 0.5
        reasons.append(f'{len(small)} texture(s) below 1K')
    if any(i['missing'] for i in entry['images']):
        score += 3
        reasons.append('referenced texture missing on disk')
    if not entry['provenance']['ok']:
        score += 3
        reasons.append('no LICENSE/provenance/manifest/generator record')
    if entry['provenance'].get('sidecar_sha256_matches') is False:
        score += 2
        reasons.append('GLB bytes differ from the sha256 recorded in its sidecar json')
    if entry.get('sidecar_bounds_error_m') is not None and entry['sidecar_bounds_error_m'] > .002:
        score += 1
        reasons.append('GLB extent differs from sidecar blender_bounds_m by %.4f m' % entry['sidecar_bounds_error_m'])
    if 'sofa_03' in entry['file'] or 'modern_coffee_table_01' in entry['file']:
        reasons.append('photographed CC0 source style chosen for availability, not authored to the reference palette')
        score += 1
    return score, reasons


PROCEDURAL_ROLE_BASE = {'visible-furnishing': 6.0, 'device-shell': 3.0, 'fallback': 1.0,
                        'template': .5, 'exterior': .5}


def score_procedural(cluster):
    reasons = [f'{cluster["role"]}: {len(cluster["parts"])} literal box primitive(s) in home.js lines '
               f'{cluster["lines"][0]}-{cluster["lines"][1]}']
    score = PROCEDURAL_ROLE_BASE[cluster['role']] + min(len(cluster['parts']), 4) * .25
    off = sorted(set(cluster['materials']) & OFF_PALETTE_MATERIALS)
    if off:
        score += 1
        reasons.append('uses ' + ', '.join(off) + ' (box() maps small M.wood to M.darkwood), off the light-oak palette')
    if set(cluster['materials']) <= {'M.white', 'M.cream'}:
        reasons.append('untextured flat colour surfaces only')
        score += .5
    if cluster.get('overlapping_assets') and cluster['role'] == 'visible-furnishing':
        reasons.append('shares its position with loaded asset(s) ' + ', '.join(cluster['overlapping_assets'])
                       + ': redundant legacy boxes, probably interpenetrating')
        score += 1
    return score, reasons


def run_audit(root: Path = ROOT):
    root = Path(root).resolve()
    base = root / ASSETS
    manifest = manifest_files(root)
    text = runtime_text(root)
    models = []
    seen_images = {}
    for path in sorted(list(base.rglob('*.glb')) + list(base.rglob('*.gltf'))):
        rel_parts = path.relative_to(base).parts
        asset_dir = rel_parts[0]
        entry = audit_model(path, root)
        prov, sidecar = provenance(path.parent, path, root, manifest)
        entry['asset_dir'] = asset_dir
        entry['provenance'] = prov
        entry['sidecar_bounds_error_m'] = sidecar_bounds_mismatch(sidecar, entry['extent_m'])
        entry['furnishing'] = asset_dir not in NON_FURNISHING_DIRS and path.stem != 'source'
        entry['runtime_referenced'] = runtime_references(text, asset_dir, path)
        for image in entry['images']:
            if image['sha256']:
                seen_images.setdefault(image['sha256'], set()).add(entry['file'])
        models.append(entry)
    def family(file):
        parts = Path(file).relative_to(ASSETS).parts
        return parts[1] if parts[0] == 'lite' else parts[0]
    duplicates = [{'sha256': h, 'used_by': sorted(files),
                   # Same-family copies (source.glb vs runtime, lite mirrors) are expected.
                   'cross_asset': len({family(f) for f in files}) > 1}
                  for h, files in seen_images.items() if len(files) > 1]
    clusters = procedural_box_furnishings(root / 'web/house/home.js')
    ranking = []
    for entry in models:
        if not entry['furnishing']:
            continue
        score, reasons = score_model(entry)
        entry['weakness_score'], entry['weakness_reasons'] = score, reasons
        if entry['runtime_referenced']:
            ranking.append({'kind': 'asset', 'id': entry['file'], 'score': score, 'reasons': reasons})
    for cluster in clusters:
        score, reasons = score_procedural(cluster)
        cluster['weakness_score'], cluster['weakness_reasons'] = score, reasons
        ranking.append({'kind': 'procedural', 'id': f'home.js:{cluster["lines"][0]} {cluster["label"]}'[:120],
                        'role': cluster['role'],
                        'score': score, 'reasons': reasons, 'bounds_m': cluster['bounds_m'],
                        'collider': cluster['collider']})
    ranking.sort(key=lambda r: (-r['score'], r['id']))
    return {
        'schema': 'sub01-home-asset-audit/1',
        'reference_direction': 'SimbasJungles first-person home (written notes only; no visual comparison made)',
        'models': models,
        'duplicate_images': duplicates,
        'texture_libraries': texture_libraries(root, manifest),
        'material_helpers': audit_material_helpers(root),
        'procedural_placeholders': clusters,
        'weakest_furnishings': ranking,
    }


def summary_lines(report, limit=10):
    out = ['Weakest runtime furnishings vs written reference direction (heuristic):']
    for i, item in enumerate(report['weakest_furnishings'][:limit], 1):
        out.append(f'{i:2d}. [{item["score"]:.2f}] {item["kind"]}: {item["id"]}')
        for reason in item['reasons'][:3]:
            out.append(f'      - {reason}')
    flagged = [h for h in report['material_helpers'] if h['flags']]
    if flagged:
        out.append('Material helper flags:')
        for h in flagged:
            for flag in h['flags']:
                out.append(f'  {h["file"]}: {flag}')
    dups = report['duplicate_images']
    out.append(f'Duplicate images across models: {len(dups)} '
               f'({sum(d["cross_asset"] for d in dups)} across different asset families)')
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--root', default=str(ROOT))
    parser.add_argument('--json', help='write the full JSON report here (keep under ignored out/)')
    parser.add_argument('--limit', type=int, default=10)
    args = parser.parse_args(argv)
    report = run_audit(Path(args.root))
    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2))
    print('\n'.join(summary_lines(report, args.limit)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
