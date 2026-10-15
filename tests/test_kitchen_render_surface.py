import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from kitchen_render_surface import compare


class RenderSurface(unittest.TestCase):
    def setUp(self):
        self.face = [[0., 0., 0.], [10., 0., 0.], [0., 10., 0.]]

    def test_only_collapsed_source_padding_may_be_discarded(self):
        zero = [[1., 1., 0.]]*3
        thin = [[0., 0., 0.], [10., 0., 0.], [5., 1e-8, 0.]]
        result = compare([zero, self.face, thin], [list(reversed(self.face))])
        self.assertEqual(len(result['discarded_subprecision_faces']), 2)
        self.assertFalse(result['discarded_faces_are_contact_surfaces'])

    def test_missing_resolvable_skin_and_extra_faces_refused(self):
        with self.assertRaisesRegex(ValueError, 'resolvable'):
            compare([self.face], [])
        with self.assertRaisesRegex(ValueError, 'extra/unmatched'):
            compare([self.face], [self.face, self.face])

    def test_source_winding_and_order_do_not_change_parity(self):
        second = [[x+20, y, z] for x, y, z in self.face]
        self.assertFalse(compare([self.face, second], [list(reversed(second)), self.face])['discarded_subprecision_faces'])

    def test_nonfinite_coordinates_refused(self):
        with self.assertRaisesRegex(ValueError, 'Nonfinite'):
            compare([[[math.nan, 0, 0]]*3], [])
