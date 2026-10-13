import ast
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from unreal_runtime_environment import build_unreal_environment

class RuntimeEnvironment(unittest.TestCase):
    def test_driver_contract_preserved_cloud_control_secrets_excluded(self):
        source={'PATH':'/usr/bin','LD_LIBRARY_PATH':'/driver/lib','NVIDIA_VISIBLE_DEVICES':'8',
                'NVIDIA_DRIVER_CAPABILITIES':'graphics,video,utility','VK_ICD_FILENAMES':'/driver/nvidia.json',
                'DISPLAY':':7','XDG_RUNTIME_DIR':'/run/user/1001','SDL_VIDEODRIVER':'x11',
                'RUNPOD_API_KEY':'fake-cloud-control','JUPYTER_TOKEN':'fake-jupyter-secret',
                'AWS_SECRET_ACCESS_KEY':'fake-cloud-secret','ANTHROPIC_API_KEY':'fake-service-secret',
                'SUB01_ADMIN_TOKEN':'stale-operator-token','UNRELATED_VARIABLE':'not-needed'}
        with tempfile.TemporaryDirectory()as tmp:
            token=Path(tmp)/'operator-token';token.write_text('protected-current-token\n')
            env=build_unreal_environment(source,token)
        for name in ('PATH','LD_LIBRARY_PATH','NVIDIA_VISIBLE_DEVICES','NVIDIA_DRIVER_CAPABILITIES','VK_ICD_FILENAMES','DISPLAY','XDG_RUNTIME_DIR','SDL_VIDEODRIVER'):
            self.assertEqual(env[name],source[name])
        for name in ('RUNPOD_API_KEY','JUPYTER_TOKEN','AWS_SECRET_ACCESS_KEY','ANTHROPIC_API_KEY','UNRELATED_VARIABLE'):
            self.assertNotIn(name,env)
        self.assertEqual(env['SUB01_ADMIN_TOKEN'],'protected-current-token')
        self.assertEqual(source['SUB01_ADMIN_TOKEN'],'stale-operator-token')
        self.assertEqual(env['SUB01_PC_ORIGIN'],'http://127.0.0.1:8811')
        self.assertEqual(env['SUB01_HOME_ORIGIN'],'http://127.0.0.1:8821')
        self.assertEqual(env['UE-ZenDataPath'],'/workspace/sub01-unreal/cache/zen')
        self.assertEqual(env['UE-LocalDataCachePath'],'/workspace/sub01-unreal/cache/filesystem')
    def test_actual_launcher_uses_the_filtered_environment_only(self):
        source=(ROOT/'tools/run_unreal_contact_recording.py').read_text()
        self.assertIn('-ZenDataPath=/workspace/sub01-unreal/cache/zen',source)
        tree=ast.parse(source)
        assignment=next(n for n in ast.walk(tree)if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='env'for t in n.targets))
        self.assertIsInstance(assignment.value,ast.Call);self.assertEqual(assignment.value.func.id,'build_unreal_environment')
        launch=next(n for n in ast.walk(tree)if isinstance(n,ast.Call)and isinstance(n.func,ast.Attribute)and n.func.attr=='Popen')
        self.assertEqual(next(k.value.id for k in launch.keywords if k.arg=='env'),'env')
        self.assertFalse(any(isinstance(n,ast.Call)and isinstance(n.func,ast.Attribute)and n.func.attr=='copy'for n in ast.walk(tree)))
if __name__=='__main__':unittest.main()
