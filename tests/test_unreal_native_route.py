"""Acceptance route source parity; physical success still requires actual UE run."""
import ast
import re
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from stage_unreal_home_runtime import stage
from unreal_native_route import METHODS

class RouteSourceTests(unittest.TestCase):
    def test_route_matches_actual_world_nodes(self):
        tree=ast.parse((ROOT/'home_world.py').read_text())
        nodes=next(ast.literal_eval(a.value)for a in tree.body if isinstance(a,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='NODES'for t in a.targets))
        names=['door','front','stair_approach','stair_bottom','stair_top','landing','loft','bed']
        targets=re.findall(r'FVector\((-?[\d.]+),(-?[\d.]+),(-?[\d.]+)\)',METHODS.split('RouteTargets=')[1].split(';')[0])
        self.assertEqual(len(targets),8)
        for name,point in zip(names[1:],targets[1:]):
            x,eye,z=nodes[name]
            self.assertAlmostEqual(float(point[0]),100*x)
            self.assertAlmostEqual(float(point[1]),100*z)
            self.assertLessEqual(abs(float(point[2])-(eye*100-74)),5)
    def test_native_route_is_opt_in_real_input_not_position_forcing(self):
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder);(root/'Config').mkdir();(root/'Sub01HomeLab.uproject').write_text('{}');stage(root)
            cpp=(root/'Source/Sub01HomeLab/Sub01HomeLab.cpp').read_text()
            header=(root/'Source/Sub01HomeLab/Sub01HomeLab.h').read_text()
            self.assertEqual(header.count('void UpdateNativeRouteTest();'),1)
            self.assertEqual(header.count('void UpdateNativeCapture();'),1)
            declarations=re.findall(r'^\s*(?:virtual\s+)?(?:UFUNCTION.*)?\s*([A-Za-z_][\w]*)\([^;{}]*\);\s*$',header,re.MULTILINE)
            self.assertNotIn('UpdateNativeCapture',declarations,'bare function without return type must never appear')
            self.assertEqual(cpp.count('BeginNativeRouteTest();'),1)
            self.assertIn('FParse::Param(FCommandLine::Get(),TEXT("Sub01RouteTest"))',cpp)
            self.assertIn('AddMovementInput(Delta/Distance',cpp)
            self.assertIn('Distance<12&&HeightError<20&&GetCharacterMovement()->IsMovingOnGround()',cpp)
            self.assertIn('Now-RouteLastProgress>3',cpp)
            self.assertIn('RequestExitWithStatus(false,RouteFailed?2:0)',cpp)
            self.assertNotIn('SetActorLocation',cpp);self.assertNotIn('Teleport',cpp)

if __name__=='__main__':unittest.main()
