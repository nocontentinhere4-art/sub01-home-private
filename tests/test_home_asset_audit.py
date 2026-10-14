"""Static furniture/material audit: GLB parsing, scoring and repository smoke run."""
import importlib.util
import json
import math
import struct
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('home_asset_audit', ROOT / 'tools/home_asset_audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def png_bytes(width, height):
    raw = b''.join(b'\x00' + b'\x80' * (width * 3) for _ in range(height))
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


def jpeg_header(width, height):
    app0 = b'\xff\xe0' + struct.pack('>H', 16) + b'JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
    sof = b'\xff\xc0' + struct.pack('>HBHHB', 11, 8, height, width, 1) + b'\x01\x11\x00'
    return b'\xff\xd8' + app0 + sof + b'\xff\xd9'


def write_glb(path, doc, binary=b''):
    while len(binary) % 4:
        binary += b'\x00'
    doc = dict(doc)
    if binary:
        doc['buffers'] = [{'byteLength': len(binary)}]
    text = json.dumps(doc).encode()
    while len(text) % 4:
        text += b' '
    body = struct.pack('<II', len(text), 0x4E4F534A) + text
    if binary:
        body += struct.pack('<II', len(binary), 0x004E4942) + binary
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack('<III', 0x46546C67, 2, 12 + len(body)) + body)


def box_doc(size=(1, 1, 1), node=None, materials=None, images=None, textures=None, primitives=1, tris=12):
    half = [s / 2 for s in size]
    accessors, prims = [], []
    for i in range(primitives):
        accessors.append({'count': 24, 'type': 'VEC3', 'componentType': 5126,
                          'min': [-h for h in half], 'max': half})
        accessors.append({'count': tris * 3, 'type': 'SCALAR', 'componentType': 5123})
        prims.append({'attributes': {'POSITION': 2 * i}, 'indices': 2 * i + 1,
                      **({'material': 0} if materials else {})})
    doc = {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': [0]}],
           'nodes': [dict(node or {}, mesh=0)], 'meshes': [{'primitives': prims}], 'accessors': accessors}
    if materials is not None:
        doc['materials'] = materials
    if images is not None:
        doc['images'] = images
    if textures is not None:
        doc['textures'] = textures
    return doc


def test_image_headers():
    assert audit.image_size(png_bytes(3, 2)) == (3, 2)
    assert audit.image_size(jpeg_header(1024, 512)) == (1024, 512)
    vp8x = b'RIFF' + b'\0' * 4 + b'WEBPVP8X' + b'\0' * 8 + (2047).to_bytes(3, 'little') + (1023).to_bytes(3, 'little')
    assert audit.image_size(vp8x) == (2048, 1024)
    assert audit.image_size(b'not an image') is None


def test_transformed_bounds_and_triangles(tmp_path):
    rotation = [0, math.sin(math.pi / 4), 0, math.cos(math.pi / 4)]  # 90 degrees about +Y
    doc = box_doc(size=(2, 1, .5), node={'rotation': rotation, 'scale': [2, 2, 2], 'translation': [1, 0, 0]},
                  primitives=2, tris=10)
    path = tmp_path / 'web/house/assets/thing/thing.glb'
    write_glb(path, doc)
    entry = audit.audit_model(path, tmp_path)
    assert entry['triangles'] == 20
    assert entry['extent_m'] == pytest.approx([1.0, 2.0, 4.0])
    assert entry['bounds_m'][0] == pytest.approx([0.5, -1.0, -2.0])


def test_meshopt_counts_from_json_only(tmp_path):
    doc = box_doc(tris=7)
    doc['extensionsUsed'] = ['EXT_meshopt_compression']
    path = tmp_path / 'web/house/assets/packed/packed.glb'
    write_glb(path, doc)
    entry = audit.audit_model(path, tmp_path)
    assert entry['compressed'] == ['EXT_meshopt_compression'] and entry['triangles'] == 7


def test_embedded_and_linked_textures_and_missing_maps(tmp_path):
    image = png_bytes(4, 4)
    linked = tmp_path / 'web/house/assets/chair/tex/diff.png'
    linked.parent.mkdir(parents=True)
    linked.write_bytes(png_bytes(8, 2))
    doc = box_doc(materials=[{'name': 'wood', 'pbrMetallicRoughness': {'baseColorTexture': {'index': 0}},
                              'normalTexture': {'index': 1}}],
                  images=[{'uri': 'tex/diff.png'}, {'bufferView': 0, 'mimeType': 'image/png'}],
                  textures=[{'source': 0}, {'source': 1}])
    doc['bufferViews'] = [{'buffer': 0, 'byteOffset': 0, 'byteLength': len(image)}]
    path = tmp_path / 'web/house/assets/chair/chair.glb'
    write_glb(path, doc, image)
    entry = audit.audit_model(path, tmp_path)
    assert [i['size'] for i in entry['images']] == [[8, 2], [4, 4]]
    assert entry['materials'][0]['normal_map'] and entry['materials'][0]['missing'] == ['roughness_map']


def test_placeholder_box_scores_above_detailed_asset():
    prov = {'ok': True}
    weak = {'file': 'a', 'triangles': 12, 'meshes': 1, 'materials': [], 'images': [], 'extent_m': [1, 1, 1],
            'provenance': prov}
    good = {'file': 'b', 'triangles': 9000, 'meshes': 3, 'images': [{'size': [1024, 1024], 'missing': False}],
            'materials': [{'name': 'm', 'normal_map': True, 'roughness_map': True}], 'extent_m': [1, 1, 1],
            'provenance': prov}
    assert audit.score_model(weak)[0] >= 5 > audit.score_model(good)[0]
    huge = dict(good, extent_m=[120, 1, 1])
    assert any('non-metric' in r for r in audit.score_model(huge)[1])
    unknown = dict(good, provenance={'ok': False})
    assert audit.score_model(unknown)[0] >= 3


HOME_JS = """
const deskFallback = [box(2.4, .09, .8, 2, .8, -3.1, M.wood, .045)];
const bedFrameFallback = [
  box(1.65, 0.3, 2.25, -2.4, 3.25, -2.35, M.darkwood, 0.06),
  box(1.65, 0.98, 0.16, -2.4, 3.63, -3.5, M.cream, 0.08),
];
// Washroom fixture.
box(0.62, 0.66, 0.48, -3.5, 3.36, 1.1, M.wood, 0.02);
box(0.68, 0.1, 0.5, -3.5, 3.73, 1.1, M.white, 0.04);
obstacle(-3.5, 1.1, 0.68, 0.5, 1);
furnished("modern_arm_chair_01", -1.2, 3, 4.5, 0.65);
box(0.65, 0.16, 0.68, -1.2, 3.44, 4.5, M.cream, 0.07);
box(1.8, 0.4, 1.8, 10, 6.4, 24, M.white, 0);
box(8, 6, 0.18, 0, 3, -4, M.wall, 0);
"""


def test_procedural_clusters_roles_colliders_and_overlap(tmp_path):
    home = tmp_path / 'home.js'
    home.write_text(HOME_JS)
    clusters = audit.procedural_box_furnishings(home)
    roles = {c['label']: c['role'] for c in clusters}
    by_line = {c['lines'][0]: c for c in clusters}
    assert by_line[2]['role'] == 'fallback'               # same-line fallback array
    assert by_line[4]['role'] == 'fallback' and by_line[4]['lines'] == [4, 5]
    vanity = by_line[8]
    assert vanity['role'] == 'visible-furnishing' and vanity['lines'] == [8, 9]
    assert vanity['collider']['width'] == .68 and vanity['collider']['level'] == 1
    assert vanity['bounds_m'] == [[-3.84, 3.03, 0.85], [-3.16, 3.78, 1.35]]
    chair = by_line[12]
    assert chair['overlapping_assets'] == ['modern_arm_chair_01']
    assert by_line[13]['role'] == 'exterior'
    assert all(c['lines'][0] != 14 for c in clusters)     # walls are architecture, not furnishings
    assert 'Washroom fixture.' in roles or any('vanity' in label for label in roles)
    scored = {c['lines'][0]: audit.score_procedural(c)[0] for c in clusters}
    assert scored[12] > scored[8] > scored[2] and scored[13] < 2


def test_material_helper_flags(tmp_path):
    helper = tmp_path / 'web/house/flat_material.mjs'
    helper.parent.mkdir(parents=True)
    helper.write_text("export const a=()=>new T.MeshStandardMaterial({color:'#fff', roughness:.5});\n"
                      "export const b=()=>new T.MeshPhysicalMaterial({map:x, normalMap:y, roughness:1});\n")
    report = audit.audit_material_helpers(tmp_path)
    assert report[0]['file'] == 'web/house/flat_material.mjs'
    assert [m['normal_map'] for m in report[0]['materials']] == [False, True]
    assert len(report[0]['flags']) == 1 and 'flat colour' in report[0]['flags'][0]


def test_repository_audit_smoke(tmp_path):
    report = audit.run_audit(ROOT)
    assert report['schema'] == 'sub01-home-asset-audit/1'
    files = {m['file']: m for m in report['models']}
    sofa = files['web/house/assets/haven-sofa/sofa.glb']
    assert sofa['runtime_referenced'] and sofa['provenance']['ok']
    assert 2.0 < sofa['extent_m'][0] < 2.5
    # Every sidecar that records a GLB hash must still describe the committed bytes.
    for model in report['models']:
        assert model['provenance'].get('sidecar_sha256_matches') is not False, model['file']
    labels = ' '.join(r['id'] for r in report['weakest_furnishings'][:6])
    assert 'bathroom vanity' in labels and 'bathroom toilet' in labels
    out = tmp_path / 'audit.json'
    assert audit.main(['--json', str(out), '--limit', '3']) == 0
    assert json.loads(out.read_text())['weakest_furnishings']


def test_furnished_placement_matches_load_furnished():
    cube = [(x, y, z) for x in (-1, 1) for y in (0, 2) for z in (-.5, .5)]
    placed = audit.furnished_placement(cube, 10, 3, -2, 1.0)            # width 1 along x -> scale .5
    xs, ys, zs = zip(*placed)
    assert (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)) == pytest.approx((9.5, 10.5, 3, 4, -2.25, -1.75))
    turned = audit.furnished_placement(cube, 0, 0, 0, 1.0, math.pi / 2)  # yaw: depth now spans x
    xs, _, zs = zip(*turned)
    assert max(xs) - min(xs) == pytest.approx(1) and max(zs) - min(zs) == pytest.approx(2)


def test_balcony_placeholder_boxes_removed_and_chair_collider_kept():
    """The audit measured the old cream box chair inside the real armchair (seat box 100%
    inside, 1,397 chair vertices; backrest on its front). Main d03e673 removed those four
    lines (proposed hunk H6); they must not come back, and the armchair keeps its collider."""
    home_js = (ROOT / 'web/house/home.js').read_text()
    for removed in ('box(0.65, 0.16, 0.68, -1.2, 3.44, 4.5, M.cream, 0.07)',
                    'box(0.65, 0.6, 0.16, -1.2, 3.77, 4.8, M.cream, 0.07)',
                    'beam([x, 3, z], [x, 3.4, z], 0.025, M.wood)'):
        assert removed not in home_js
    assert 'furnished("modern_arm_chair_01", -1.2, 3, 4.5, 0.65)' in home_js
    assert 'obstacle(-1.2, 4.55, 0.72, 0.8, 1)' in home_js


def test_balcony_boxes_measured_against_actual_chair(tmp_path):
    # Keep the regression's original overlap even after removing the bad boxes
    # from the actual house. Auditing every asset is unnecessary for this case.
    legacy = tmp_path / 'legacy-balcony.js'
    legacy.write_text('''
furnished("modern_arm_chair_01", -1.2, 3, 4.5, 0.65);
box(0.65, 0.16, 0.68, -1.2, 3.44, 4.5, M.cream, 0.07);
box(0.65, 0.6, 0.16, -1.2, 3.77, 4.8, M.cream, 0.07);
''')
    balcony = audit.procedural_box_furnishings(legacy)[0]
    boxes = [{'low': [p['centre_m'][i] - p['size_m'][i]/2 for i in range(3)],
              'high': [p['centre_m'][i] + p['size_m'][i]/2 for i in range(3)]}
             for p in balcony['parts']]
    overlap = audit.asset_overlap(ROOT, boxes, 'modern_arm_chair_01',
                                  balcony['loaded_calls']['modern_arm_chair_01'])
    assert overlap['asset'] == 'modern_arm_chair_01' and overlap['asset_back_side'] == '-z'
    seat, back = overlap['parts']
    assert seat['volume_fraction_inside_asset_bounds'] == 1 and seat['asset_vertices_inside_box'] > 1000
    assert back['protrudes_above_asset_m'] > .2 and back['low'][2] > 4.7  # old backrest on the chair's front side
    current = audit.procedural_box_furnishings(ROOT / 'web/house/home.js')
    assert not any('modern_arm_chair_01' in c['overlapping_assets']
                   and c['role'] == 'visible-furnishing' for c in current)
