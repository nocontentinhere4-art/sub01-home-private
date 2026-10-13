"""Recompute the constants in web/house/furnishing_detail.mjs from the owned
maps and GLBs: mean-preserving clamped roughness factors and UV densities."""
import json
import re
import struct
from pathlib import Path

import pytest

np = pytest.importorskip('numpy')
Image = pytest.importorskip('PIL.Image')

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'web/house/assets'
MODULE = (ROOT / 'web/house/furnishing_detail.mjs').read_text()


def factors(block):
    text = re.search(block + r":\s*Object\.freeze\(\{(.*?)\}\)\s*,?\s*\}\)", MODULE, re.S).group(1)
    full = float(re.search(r'full:\s*([\d.]+)', text).group(1))
    lite = float(re.search(r'lite:\s*([\d.]+)', text).group(1))
    previous = float(re.search(r'previousRoughness:\s*([\d.]+)', text).group(1))
    return previous, {'full': full, 'lite': lite}


def clamped_mean(path, factor):
    g = np.asarray(Image.open(path).convert('RGB')).astype(float)[..., 1] / 255
    return float(np.minimum(1, factor * g).mean())


@pytest.mark.parametrize('block,relative', [
    ('queenBedOak', 'home_oak_veneer/rough.jpg'),
    ('havenSeams', 'haven-sofa/maps/linen_roughness.jpg'),
    ('wovenRug', 'rough_linen/rough.jpg'),
])
def test_roughness_factors_preserve_previous_mean(block, relative):
    previous, tiers = factors(block)
    assert clamped_mean(ASSETS / relative, tiers['full']) == pytest.approx(previous, abs=5e-4)
    assert clamped_mean(ASSETS / 'lite' / relative, tiers['lite']) == pytest.approx(previous, abs=5e-4)


def glb_uv_density(path):
    data = path.read_bytes()
    n = struct.unpack('<I', data[12:16])[0]
    doc = json.loads(data[20:20 + n])
    binary = data[20 + n + 8:]
    kinds = {5126: np.float32, 5123: np.uint16, 5125: np.uint32}
    width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3}

    def accessor(index):
        a = doc['accessors'][index]
        view = doc['bufferViews'][a['bufferView']]
        dtype = np.dtype(kinds[a['componentType']])
        assert view.get('byteStride', dtype.itemsize * width[a['type']]) == dtype.itemsize * width[a['type']]
        start = view.get('byteOffset', 0) + a.get('byteOffset', 0)
        return np.frombuffer(binary, dtype, a['count'] * width[a['type']], start).reshape(a['count'], -1).astype(float)

    result = {}
    for node in doc['nodes']:
        prim = doc['meshes'][node['mesh']]['primitives'][0]
        P, U = accessor(prim['attributes']['POSITION']), accessor(prim['attributes']['TEXCOORD_0'])
        I = accessor(prim['indices']).astype(int).reshape(-1, 3)
        a, b, c = P[I[:, 0]], P[I[:, 1]], P[I[:, 2]]
        world = np.linalg.norm(np.cross(b - a, c - a), axis=1).sum() / 2
        e1, e2 = U[I[:, 1]] - U[I[:, 0]], U[I[:, 2]] - U[I[:, 0]]
        uv = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]).sum() / 2
        result[node['name']] = (float(np.sqrt(uv / world)), doc['materials'][prim['material']]['name']
                                if 'material' in prim and doc.get('materials') else None)
    return result


def test_queen_bed_wood_uvs_are_one_metre_per_unit():
    density = glb_uv_density(ASSETS / 'cc0-queen-bed/queen-bed.glb')
    wood = {k: v for k, v in density.items() if 'grain' in v[1]}
    assert len(wood) == 2
    stated = float(re.search(r'sourceUvPerMetre:\s*([\d.]+)', MODULE).group(1))
    for value, _ in wood.values():
        assert value == pytest.approx(stated, rel=.03)


def test_haven_seams_share_linen_uv_density():
    density = glb_uv_density(ASSETS / 'haven-sofa/sofa.glb')
    assert density['Haven_seams'][0] == pytest.approx(density['Haven_linen'][0], rel=.06)
