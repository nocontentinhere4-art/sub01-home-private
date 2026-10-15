import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from build_reference_footrest import rounded_outline

class FootrestOutlineTests(unittest.TestCase):
    def test_capsule_grip_has_no_zero_length_seam_edges(self):
        points=rounded_outline(.320,.028,.014)
        self.assertEqual(len(points),50)  # Old52 vertices duplicated both end seams.
        for a,b in zip(points,points[1:]+points[:1]):self.assertGreater(math.dist(a,b),1e-12)
        area=abs(sum(a[0]*b[1]-a[1]*b[0]for a,b in zip(points,points[1:]+points[:1])))/2
        expected=(.320-.028)*.028+math.pi*.014**2
        self.assertAlmostEqual(area,expected,delta=1e-5)

    def test_vertical_adjustment_slot_also_removes_coincident_caps(self):
        points=rounded_outline(.012,.052,.006)
        self.assertEqual(len(points),50)
        self.assertEqual(len(set(points)),len(points))
        self.assertAlmostEqual(max(x for x,y in points)-min(x for x,y in points),.012)
        self.assertAlmostEqual(max(y for x,y in points)-min(y for x,y in points),.052)
