import math
import unittest
from solve_upright_footrest_transitions import rotation_with_preserved_scale

class TransitionScaleTest(unittest.TestCase):
    def test_centimetre_rig_toe_offset_does_not_grow_one_hundred_times(self):
        angle=.61;c,s=math.cos(angle),math.sin(angle);rotation=[[c,0,s],[0,1,0],[-s,0,c]];ref=[[.01,0,0],[0,.01,0],[0,0,.01]]
        out=rotation_with_preserved_scale(rotation,ref)
        toe_local=[0.,0.,18.9]
        actual=[sum(out[r][i]*toe_local[i]for i in range(3))for r in range(3)]
        self.assertAlmostEqual(math.sqrt(sum(x*x for x in actual)),.189)
        unit_error=math.sqrt(sum((sum(rotation[r][i]*toe_local[i]for i in range(3))-actual[r])**2 for r in range(3)))
        self.assertGreater(unit_error,18.)
    def test_original_column_scales_all_preserved(self):
        out=rotation_with_preserved_scale([[0,-1,0],[1,0,0],[0,0,1]],[[.01,0,0],[0,.02,0],[0,0,.03]])
        self.assertEqual([math.sqrt(sum(out[r][c]**2 for r in range(3)))for c in range(3)],[.01,.02,.03])

if __name__=='__main__':unittest.main()
