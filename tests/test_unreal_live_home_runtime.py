import importlib.util
import re
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import unreal_live_home_runtime as live
import stage_unreal_home_runtime as stage
from home_world import NODES,EDGES,route

class LiveHomeRuntime(unittest.TestCase):
    def test_source_floor_waypoints_and_graph(self):
        code=live.graph_source()
        nodes={name:tuple(map(float,values))for name,*values in re.findall(r'LiveHomeNodes.Add\(TEXT\("([^"]+)"\),FVector\(([-.0-9]+),([-.0-9]+),([-.0-9]+)\)\)',code)}
        self.assertEqual(set(nodes),set(NODES))
        for name,(x,y,z)in NODES.items():
            for actual,expected in zip(nodes[name],(x*100,z*100,(y-1.65)*100)):
                self.assertAlmostEqual(actual,expected,places=5)
        for a,b in EDGES:
            self.assertIn(f'LiveHomeEdges.FindOrAdd(TEXT("{a}")).Add(TEXT("{b}"));',code)
        # Backend already asleep atbed cannot justify a straight entry->bed move.
        actual=route('door','bed');self.assertIn('stair_bottom',actual);self.assertIn('stair_top',actual)
        self.assertGreater(len(actual),5)
    def test_actual_generator_wiring_and_privacy_combination(self):
        import tempfile
        with tempfile.TemporaryDirectory()as tmp:
            p=Path(tmp);(p/'Config').mkdir();(p/'Sub01HomeLab.uproject').write_text('{}');stage.stage(p)
            h=(p/'Source/Sub01HomeLab/Sub01HomeLab.h').read_text();c=(p/'Source/Sub01HomeLab/Sub01HomeLab.cpp').read_text()
            begin=c.split('void ASub01HomeCharacter::BeginPlay() {',1)[1].split('void ASub01HomeCharacter::SetupPlayerInputComponent',1)[0]
            self.assertEqual(begin.count(' BeginLiveHome();'),1)
            self.assertEqual(c.count(' UpdateLiveHome(DeltaSeconds);'),1)
            self.assertIn('LiveHomePrivate||(Eye.Z>300',c)
            self.assertIn('StartCameraFade(Hidden?1:0,Hidden?1:0',c)
            self.assertIn('class FJsonObject;',h)
            self.assertIn('TryNativeHomeDevice(Hit.GetComponent())',c)
    def test_safety_guards_no_position_commands(self):
        c=live.METHODS
        self.assertNotIn('SetActorLocation',c);self.assertNotIn('Teleport',c)
        self.assertIn('AddMovementInput(Delta/Distance',c)
        self.assertIn('Now-LiveHomeLastReceived>3',c)
        self.assertIn('Now-LiveHomeProgressAt>4',c)
        self.assertIn('LiveHomeOrigin!=TEXT("http://127.0.0.1:8821")',c)
        self.assertIn('HandsDiagnosticSeat||RouteActive',c)
if __name__=='__main__':unittest.main()
