import itertools
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from unreal_home_coordinates import infer_import_transform,convert_position

class CoordinateTests(unittest.TestCase):
    def test_all_eight_horizontal_import_orientations_and_real_cm_scale(self):
        points=[(0,0,0),(3,0,2),(-2,3,1),(2,1.65,3.1)]
        for axes in [(0,2,1),(2,0,1)]:
            for x,y in itertools.product((-1,1),repeat=2):
                expected={'axes':axes,'signs':(x,y,1),'offset_cm':(10,-20,4)}
                pairs=[(p,convert_position(p,expected))for p in points[:3]]
                found=infer_import_transform(pairs)
                self.assertEqual(found['axes'],axes)
                self.assertEqual(found['signs'],(x,y,1))
                self.assertEqual(convert_position(points[3],found),convert_position(points[3],expected))
                self.assertAlmostEqual(convert_position((2,1.65,3.1),found)[2]-convert_position((2,0,3.1),found)[2],165)

    def test_wrong_scale_or_unverified_pivots_are_refused(self):
        points=[(0,0,0),(3,0,2),(-2,3,1)]
        with self.assertRaises(ValueError):infer_import_transform([(p,p)for p in points])
        with self.assertRaises(ValueError):infer_import_transform([(p,(p[0]*100,p[2]*100,p[1]*100))for p in points[:2]])
        with self.assertRaises(ValueError):infer_import_transform([((i,0,i),(i*100,i*100,0))for i in range(3)])

if __name__=='__main__':unittest.main()
