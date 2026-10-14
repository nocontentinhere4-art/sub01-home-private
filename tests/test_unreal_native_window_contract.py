import ast,sys,tempfile,unittest,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import stage_unreal_home_runtime as stage

class NativeWindowContract(unittest.TestCase):
    def test_head_origin_camera_refuses_ordinary_house_launch_before_process_creation(self):
        result=subprocess.run([sys.executable,str(ROOT/'tools/run_unreal_native_window_recording.py'),'--deadline-epoch','9999999999','--startup-view','manual','--phone-head-camera'],capture_output=True,text=True,timeout=5)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Head-origin camera requires explicit phone diagnostic',result.stderr)
    def test_measured_eye_review_refuses_wrong_role_time_and_two_camera_flags(self):
        for extra,message in [(['--startup-view','manual'], 'explicit phone diagnostic'),
                              (['--startup-view','phone-diagnostic','--phone-pose-time','5'], 'original 4s witness'),
                              (['--startup-view','phone-diagnostic','--phone-head-camera'], 'no Head-origin flag')]:
            result=subprocess.run([sys.executable,str(ROOT/'tools/run_unreal_native_window_recording.py'),
                                   '--deadline-epoch','9999999999','--phone-eye-camera',*extra],capture_output=True,text=True,timeout=5)
            self.assertNotEqual(result.returncode,0)
            self.assertIn(message,result.stderr)
    def test_real_generated_replay_keeps_fingers_and_refuses_live_view(self):
        with tempfile.TemporaryDirectory()as tmp:
            project=Path(tmp);(project/'Config').mkdir();(project/'Sub01HomeLab.uproject').write_text('{}');stage.stage(project)
            module=project/'Source/Sub01HomeLab';cpp=(module/'Sub01HomeLab.cpp').read_text()
            for header in ('Sub01GuestInputQueue.h','Sub01GuestFrameLayout.h'):self.assertTrue((module/header).is_file())
            self.assertIn('"ImageCore"',(module/'Sub01HomeLab.Build.cs').read_text())
        replay=cpp.split('bool Replay=false;',1)[1].split('FString Capture;',1)[0]
        self.assertIn('HandsDiagnosticSeat&&Hands&&Hands->ContactTimes.Num()==301',replay)
        self.assertIn('Hands->ContactSequence==HandsClips.FindRef(TEXT("DeskTyping"))',replay)
        self.assertIn('++Hands->ContactRestartSerial',replay)
        self.assertNotIn('SetBone',replay);self.assertNotIn('SetActorLocation',replay)
        self.assertIn('MotionBlurAmount=0',cpp);self.assertIn('MotionBlurMax=0',cpp)
    def test_actual_window_launcher_uses_pixels_and_separate_display_environment(self):
        source=(ROOT/'tools/run_unreal_native_window_recording.py').read_text();tree=ast.parse(source)
        self.assertNotIn('-RenderOffscreen',source)
        self.assertIn("'-f','x11grab'",source);self.assertIn("'-corelimit=8'",source)
        self.assertIn("'-nolisten','tcp'",source);self.assertNotIn("'-ac'",source)
        self.assertIn("if not k.startswith('SUB01_')",source)
        self.assertIn("'replayTyping':True",source)
        self.assertIn("'--kill-after=5'",source)
        # Password/cookie values are only passed on stdin or environment, never argv.
        self.assertIn("input=f'add :99 . {cookie}",source)
        self.assertFalse(any(isinstance(n,ast.Call)and isinstance(n.func,ast.Attribute)and n.func.attr=='copy'for n in ast.walk(tree)))

if __name__=='__main__':unittest.main()
