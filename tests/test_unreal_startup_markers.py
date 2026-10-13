import sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import stage_unreal_home_runtime as stage

class StartupMarkers(unittest.TestCase):
    def test_real_generated_initialization_boundaries_and_engine_world_hooks(self):
        with tempfile.TemporaryDirectory()as tmp:
            p=Path(tmp);(p/'Config').mkdir();(p/'Sub01HomeLab.uproject').write_text('{}');stage.stage(p)
            c=(p/'Source/Sub01HomeLab/Sub01HomeLab.cpp').read_text()
        begin=c.split('void ASub01HomeCharacter::BeginPlay() {',1)[1].split('void ASub01HomeCharacter::SetupPlayerInputComponent',1)[0]
        stages=['ConfigureActualPC();','BeginLiveHome();','SUB01_NATIVE_INIT_PC_DONE','BeginNativeRouteTest();','SUB01_NATIVE_INIT_INPUT_MODE_BEGIN','Player->SetInputMode','SUB01_NATIVE_BEGINPLAY_RETURN']
        positions=[begin.index(s)for s in stages];self.assertEqual(positions,sorted(positions))
        self.assertEqual(begin.count('BeginNativeRouteTest();'),1)
        self.assertIn('FCoreDelegates::OnBeginFrame.AddLambda',c)
        self.assertIn('FWorldDelegates::OnWorldTickStart.AddLambda',c)
        self.assertIn('FCoreDelegates::OnBeginFrame.Remove(EngineFrameHandle)',c)
        self.assertIn('FWorldDelegates::OnWorldTickStart.Remove(WorldTickHandle)',c)
        actor=c.split('void ASub01HomeCharacter::Tick(float DeltaSeconds)',1)[1]
        self.assertIn('SUB01_FIRST_ACTUAL_GAME_TICK',actor)
if __name__=='__main__':unittest.main()
