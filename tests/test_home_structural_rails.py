import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import build_home_structural_rails as rail


class StructuralRailTests(unittest.TestCase):
    def test_existing_source_contract_selects_rails_only(self):
        self.assertEqual(len(rail.old_rails()),45)
        self.assertEqual(sum(r['name']=='incline post' for r in rail.old_rails()),18)
        self.assertEqual(sum(r['name']=='west loft post' for r in rail.old_rails()),17)
        self.assertEqual(sum(r['name']=='north landing post' for r in rail.old_rails()),6)

    def test_tread_and_floor_anchors_clear_real_soffit_and_native_centre_route(self):
        self.assertEqual(rail.geometry_checks(),[])
        parts=rail.replacement_parts()
        for p in parts:
            lo,hi=rail.part_bounds(p)
            if 'tread anchor plate' in p['name']:
                i=int(p['name'].rsplit(' ',1)[1]);surface=(i+1)*3/17+.0235
                self.assertAlmostEqual(lo[1],surface)
                self.assertGreaterEqual(lo[0],-.21);self.assertLessEqual(hi[0],.81)
            if 'loft baseplate' in p['name']:
                self.assertLessEqual(hi[0],-.2)
                self.assertAlmostEqual(lo[1],3.025)
            if 'inclined oak grip' in p['name']:
                self.assertGreater(min(abs(p['a'][0]-.3),abs(p['b'][0]-.3)),.16+p['radius'])
                if p['a'][0]<0:self.assertGreater(lo[0],-.2)

    def test_wall_standoffs_really_contact_existing_north_wall(self):
        fixtures=[p for p in rail.replacement_parts() if 'mounting rosette' in p['name']]
        self.assertEqual(len(fixtures),3)
        for p in fixtures:
            self.assertEqual(p['a'][2],-3.91)
            self.assertGreater(p['b'][2],p['a'][2])
        self.assertTrue(any(p['name']=='North west return wall flange' for p in rail.replacement_parts()))


if __name__=='__main__':unittest.main()
