import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import unreal_loaded_plant_clone_audit as A

class Diagnostic(unittest.TestCase):
    def test_counts_degenerate_triangles_without_discarding_them(self):
        rows=[[[0,0,0],[1,0,0],[0,1,0]],[[0,0,0],[1,0,0],[1,0,0]]]
        report=A.summary(rows)
        self.assertEqual(report['triangles'],2)
        self.assertEqual(report['exact_zero_area_triangle_count'],1)
        self.assertEqual(report['first_zero_area_triangle_indices'],[1])
    def test_absent_loaded_object_fails_without_loading_or_scene_access(self):
        with tempfile.TemporaryDirectory()as td:
            u=NS(Paths=NS(project_dir=lambda:td),find_object=lambda outer,path:None)
            with self.assertRaisesRegex(RuntimeError,'no load attempted'):A.run(u)
            self.assertTrue((Path(td)/'private-audit/office-plant222-clone-audit.json').exists())
if __name__=='__main__':unittest.main()
