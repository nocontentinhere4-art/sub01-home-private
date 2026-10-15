import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import unreal_import_real_wc as wc
from home_asset_audit import read_gltf

FIXTURE=Path(__file__).resolve().parents[1]/'docs/proposed/real-compact-wc-source'


class RealWCImportProofTests(unittest.TestCase):
    def test_actual_server_pass_has_all_positive_geometry_and_exact_remainders(self):
        proof=wc.validate_source(FIXTURE)
        doc,blob=read_gltf(FIXTURE/'real-wc.glb')
        triangles=[t for node,n in enumerate(doc['nodes'])if 'mesh'in n for t in wc.expected_triangles(doc,blob,node)]
        self.assertEqual(len(triangles),4560)
        for node,count in [(166,300),(168,600)]:
            d,b=read_gltf(FIXTURE/f'remainder-{node}.glb')
            self.assertEqual(len(wc.expected_triangles(d,b,0)),count)
        self.assertEqual(proof['issues'],[])
        self.assertFalse(proof['native_imported'])

    def test_rejects_failed_support_missing_remainder_and_changed_bytes(self):
        mutations=[lambda p:p.update(ok=False),
                   lambda p:p.update(foot_vertices_inside_actual_tile_top_triangles=False),
                   lambda p:p.update(issues=[{'home_node':158}]),
                   lambda p:p['remainders'][0].update(retained_triangle_ids=list(range(1,301)))]
        for mutate in mutations:
            with self.subTest(mutation=mutate),tempfile.TemporaryDirectory()as folder:
                root=Path(folder);shutil.copytree(FIXTURE,root,dirs_exist_ok=True)
                proof=json.loads((root/'wc-source-proof.json').read_text());mutate(proof)
                (root/'wc-source-proof.json').write_text(json.dumps(proof))
                with self.assertRaises(RuntimeError):wc.validate_source(root)
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder);shutil.copytree(FIXTURE,root,dirs_exist_ok=True)
            (root/'remainder-168.glb').write_bytes(b'changed')
            with self.assertRaises(RuntimeError):wc.validate_source(root)

    def test_world_placement_has_real_floor_and_four_mm_wall_gap(self):
        doc,blob=read_gltf(FIXTURE/'real-wc.glb')
        points=[p for node,n in enumerate(doc['nodes'])if 'mesh'in n for tri in wc.expected_triangles(doc,blob,node)for p in tri]
        self.assertAlmostEqual(min(p[2]for p in points),305.25000859051943,places=6)
        self.assertAlmostEqual(265-max(p[1]for p in points),.4,places=5)
        self.assertAlmostEqual(max(p[0]for p in points)-min(p[0]for p in points),43.20000112056732,places=5)
