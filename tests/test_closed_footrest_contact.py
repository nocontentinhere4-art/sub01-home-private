"""Run in leased server Python/Blender with NumPy; no scene or asset writes."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from closed_footrest_contact import ClosedFootrest

class ClosedFootrestTests(unittest.TestCase):
    @staticmethod
    def boxes():
        vertices=[(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]
        faces=[(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
        return [[[tuple(v+(4*node if axis==0 else 0)for axis,v in enumerate(vertices[i]))for i in face]for face in faces]for node in range(19)]
    def make(self):
        boxes=self.boxes();return ClosedFootrest([t for box in boxes for t in box],[n for n in range(19)for t in boxes[n]])
    def test_inside_outside_and_edge_endcap_normal_counterexample(self):
        contact=self.make()
        self.assertTrue(contact.contains_part((0,0,0),0))
        self.assertFalse(contact.contains_part((.999999,2,2),0))
        # A nearest endcap's +X normal gives a negative dot here, although
        # this point is outside the closed solid in Y and Z.
        self.assertLess(.999999-1,0)
        self.assertEqual(contact.signed_distance((.999999,2,2),2**.5),2**.5)
        self.assertEqual(contact.signed_distance((0,0,0),1),-1)
        self.assertEqual(contact.signed_distance((1,0,0),0),0)
    def test_missing_face_is_refused_not_skipped(self):
        boxes=self.boxes();boxes[17].pop()
        with self.assertRaisesRegex(ValueError,'not closed/manifold 17'):
            ClosedFootrest([t for box in boxes for t in box],[n for n in range(19)for t in boxes[n]])
    def test_nonmanifold_duplicate_face_is_refused(self):
        boxes=self.boxes();boxes[2].append(boxes[2][0])
        with self.assertRaisesRegex(ValueError,'not closed/manifold 2'):
            ClosedFootrest([t for box in boxes for t in box],[n for n in range(19)for t in boxes[n]])

if __name__=='__main__':unittest.main()
