"""Schema checks for docs/proposed/real-furniture-acquisition-packet.json (no network)."""
import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
PACKET = json.loads((ROOT / 'docs/proposed/real-furniture-acquisition-packet.json').read_text())
OFFICIAL = {'polyhaven.com', 'api.polyhaven.com', 'dl.polyhaven.org'}
EPS = 1e-6


def test_licence_and_hosts():
    assert PACKET['assets']
    for a in PACKET['assets']:
        assert a['licence'] == 'CC0-1.0' and 'CC0' in a['licence_quote']
        assert urlparse(a['licence_source']).hostname in OFFICIAL
        assert urlparse(a['page_url']).hostname in OFFICIAL
        assert a['target_dir'].startswith('/workspace/sub01-home-private/reviewed-furniture/' + a['id'])
        assert any(f['path'].endswith('.gltf') for f in a['files'])
        for f in a['files']:
            assert urlparse(f['url']).scheme == 'https' and urlparse(f['url']).hostname in OFFICIAL
            assert len(f['sha256']) == 64 and len(f['md5']) == 32


def test_measured_size_matches_api():
    for a in PACKET['assets']:
        size = sorted(a['measured_bounds_gltf_m']['size'])
        api = sorted(v / 1000 for v in a['api_dimensions_mm'])
        assert all(abs(s - p) < 0.002 for s, p in zip(size, api)), a['id']


def test_ue_conversion():
    for a in PACKET['assets']:
        for p in a['placements']:
            x, y, z = p['source_m']
            assert p['ue_cm'] == [round(x * 100, 2), round(z * 100, 2), round(y * 100, 2)]
            assert (p['ue_yaw_deg'] + p['source_yaw_deg']) % 360 == 0


def test_footprints_within_slots():
    slots = PACKET['slots']
    for a in PACKET['assets']:
        s, d = slots[a['slot']], a['dimensions_m']
        if a['slot'] == 'office_shelf_wall':
            assert d['depth'] <= s['max_depth'] + EPS and d['height'] < s['max_height_under_art']
            fx, fz = a['footprint_m']['x'], a['footprint_m']['z']
            lo, hi = s['conservative_x_span']
            assert lo - EPS <= fx[0] and fx[1] <= hi + EPS
            assert fz[0] >= s['z_back'] - EPS and fz[1] <= s['z_front_limit'] + EPS
            assert abs((fx[1] - fx[0]) - a['count'] * d['width']) < 1e-3
        elif a['slot'] == 'kitchen_table_area':
            fps = a['footprint_m'].values() if 'west' in a['footprint_m'] else [a['footprint_m']]
            for fp in fps:
                assert s['x_min'] - EPS <= fp['x'][0] and fp['x'][1] <= s['x_max'] + EPS
                assert s['z_min'] - EPS <= fp['z'][0] and fp['z'][1] <= s['z_max'] + EPS
                for ex in s['exclusions_padded'].values():
                    apart_x = fp['x'][1] <= ex['x'][0] or fp['x'][0] >= ex['x'][1]
                    apart_z = fp['z'][1] <= ex['z'][0] or fp['z'][0] >= ex['z'][1]
                    assert apart_x or apart_z, (a['id'], fp, ex)
        elif a['slot'] == 'kitchen_counter_top':
            fp = a['footprint_m']
            assert s['x_min'] <= fp['x'][0] and fp['x'][1] <= s['x_max']
            assert s['z_min'] <= fp['z'][0] and fp['z'][1] <= s['z_max']
            assert abs(a['placements'][0]['source_m'][1] - s['y']) < EPS


def test_rejected_have_reasons():
    assert all(r['reason'] and r['page_url'].startswith('https://polyhaven.com/a/') for r in PACKET['rejected'])
