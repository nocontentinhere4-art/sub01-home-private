import importlib.util
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('keyboard_keycap_surface',ROOT/'tools/keyboard_keycap_surface.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

PRIVATE_PROOF = ROOT/'out/first-person-assets/ReferenceT/keyboard-keycaps-world.json'


class ProjectedTriangleTests(unittest.TestCase):
    def test_sloped_height_is_independent_of_winding(self):
        triangle = [[0, 0, 80], [2, 0, 82], [0, 2, 84]]
        for ordered in [triangle, list(reversed(triangle))]:
            with self.subTest(winding=ordered):
                self.assertAlmostEqual(module.projected_triangle_z(.5, .5, ordered), 81.5)
                self.assertIsNone(module.projected_triangle_z(2, 2, ordered))

    def test_edges_and_vertices_are_included_in_both_orientations(self):
        triangle = [[0, 0, 80], [2, 0, 82], [0, 2, 84]]
        for ordered in [triangle, list(reversed(triangle))]:
            for x, y, z in [(0, 0, 80), (2, 0, 82), (0, 2, 84), (1, 1, 83)]:
                with self.subTest(winding=ordered, point=(x, y)):
                    self.assertAlmostEqual(module.projected_triangle_z(x, y, ordered), z)

    def test_degenerate_and_vertical_projections_are_rejected(self):
        for triangle in [
            [[0, 0, 0], [0, 0, 1], [0, 0, 2]],
            [[0, 0, 0], [1, 1, 1], [2, 2, 2]],
            [[1, 1, 5], [1, 1, 5], [1, 1, 5]],
        ]:
            self.assertIsNone(module.projected_triangle_z(0, 0, triangle))


@unittest.skipUnless(PRIVATE_PROOF.is_file(), 'Private authored-geometry integration proof is unavailable')
class PrivateKeyboardGeometryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.surface=module.KeyboardSurface(PRIVATE_PROOF)

    def test_all_actual_top_triangle_centroids_and_vertices(self):
        count=0
        for key in self.surface.keycaps:
            for tri in key['topTrianglesUECm']:
                x,y,z=[sum(p[a]for p in tri)/3 for a in range(3)]
                hit=self.surface.height_at(x,y)
                self.assertIsNotNone(hit)
                self.assertAlmostEqual(hit['zCm'],z,places=6)
                for p in tri:
                    self.assertIsNotNone(self.surface.height_at(p[0],p[1]))
                count+=1
        self.assertGreater(count,170)

    def test_real_gaps_and_overhang_are_not_infinite_plane_contact(self):
        # Both lie inside the old rectangle but outside actual cap geometry.
        for x,y in [(200,-303),(200,-285)]:
            self.assertTrue(182.5<=x<=217.5 and -304<=y<=-284)
            self.assertIsNone(self.surface.height_at(x,y))
            self.assertIsNone(self.surface.height_at(x,y,include_bevels=True))
        gaps=[]
        for xi in range(1830,2170,2):
            for yi in range(-3010,-2880,2):
                x,y=xi/10,yi/10
                if self.surface.height_at(x,y,include_bevels=True)is None:
                    gaps.append((x,y))
                    if len(gaps)>=3:break
            if len(gaps)>=3:break
        self.assertEqual(len(gaps),3)

    def test_actual_bevel_below_top_is_separate_from_top_mask(self):
        found=None
        for key in self.surface.keycaps:
            for ids in key['trianglesUEVertexIds']:
                tri=[self.surface.vertices[i]for i in ids]
                x,y=[sum(p[a]for p in tri)/3 for a in range(2)]
                hit=self.surface.height_at(x,y,include_bevels=True)
                top=self.surface.height_at(x,y)
                if hit and top is None and hit['zCm']<key['topCm']-.01:
                    found=(x,y,hit);break
            if found:break
        self.assertIsNotNone(found,'actual cap has a bevel zone outside flat top mask')
        self.assertLess(found[2]['zCm'],87.38975857927267)

if __name__=='__main__':unittest.main()
