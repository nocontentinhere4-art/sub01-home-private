"""Exact source/runtime photometry parity; no Unreal/renderer launched."""
import json
import subprocess
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from unreal_home_lights import authored_lights,srgb_hex_linear

class LightRecipeTests(unittest.TestCase):
    def test_actual_three_sun_clock_matches(self):
        script="import {homeLighting} from './web/house/lighting.mjs'; console.log(JSON.stringify([0,7,11,12,17,23].map(h=>homeLighting((h-9)*3600))));"
        source=json.loads(subprocess.check_output(['node','--input-type=module','-e',script],cwd=ROOT,text=True))
        for hour,expected in zip([0,7,11,12,17,23],source):
            row=authored_lights(hour)[0]
            self.assertAlmostEqual(row['intensity'],expected['sunIntensity'])
            self.assertEqual(row['color'],expected['sunColor'])
            for a,b in zip(row['position'],expected['sunPosition']):self.assertAlmostEqual(a,b)
            self.assertEqual(row['unit'],'lux')
    def test_authored_fixture_values_and_preview_gating(self):
        rows=authored_lights(0,True)
        self.assertEqual([row['intensity']for row in rows[1:]],[12,3.5,2.4,10,10])
        self.assertTrue(all(row['unit']=='candela'for row in rows[1:]))
        self.assertTrue(all(row['intensity']==0 for row in authored_lights(11,False)[1:]))
        self.assertEqual(rows[4]['position'],[-2,2.43,.5])
        self.assertAlmostEqual(rows[4]['outer_angle_degrees'],66.6)
        self.assertEqual(srgb_hex_linear('#ffffff'),[1,1,1])
        self.assertAlmostEqual(srgb_hex_linear('#808080')[0],.2158605001)

if __name__=='__main__':unittest.main()
