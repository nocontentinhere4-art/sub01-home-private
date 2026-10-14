"""Execute the generated capture completion branches, not a copied policy."""
import ast
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from unreal_home_hands_runtime import CHARACTER_METHODS


class PersistentNativeCapture(unittest.TestCase):
    def test_actual_success_and_timeout_only_exit_when_explicit(self):
        start = CHARACTER_METHODS.index(" if(CaptureRequested&&Now-CaptureRequestedAt>1")
        end = CHARACTER_METHODS.index("\n}\n\nvoid ASub01HomeCharacter::LoadHandsAssets", start)
        branch = CHARACTER_METHODS[start:end]
        cpp = r'''
#include <cassert>
#define TEXT(x) x
#define UE_LOG(...) ((void)0)
bool ExitFlag=false;int Exits=0,ExitCode=-1;long FileBytes=0;
struct FParse {static bool Param(const char*,const char*){return ExitFlag;}};
struct FCommandLine {static const char*Get(){return "args";}};
struct FPlatformMisc {static void RequestExitWithStatus(bool,int code){++Exits;ExitCode=code;}};
struct IFileManager {static IFileManager&Get(){static IFileManager m;return m;}long FileSize(const char*){return FileBytes;}};
bool CaptureRequested=true,RouteFailed=false;double CaptureRequestedAt=0,Now=2;float CaptureAfter=45;const char*CapturePath="image";
void actualCompletion(){
''' + branch.replace("*CapturePath", "CapturePath") + r'''
}
int main(){
 FileBytes=1;actualCompletion();assert(Exits==0&&CaptureAfter==-1);
 ExitFlag=true;CaptureAfter=45;actualCompletion();assert(Exits==1&&ExitCode==0);
 RouteFailed=true;CaptureAfter=45;actualCompletion();assert(Exits==2&&ExitCode==2);
 ExitFlag=false;FileBytes=0;Now=41;CaptureAfter=45;actualCompletion();assert(Exits==2&&CaptureAfter==-1);
 ExitFlag=true;CaptureAfter=45;actualCompletion();assert(Exits==3&&ExitCode==2);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "capture.cpp"
            binary = Path(directory) / "capture"
            source.write_text(cpp)
            subprocess.run(["c++", "-std=c++17", str(source), "-o", str(binary)], check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, capture_output=True)

    def test_isolated_diagnostic_callers_opt_in_but_house_does_not(self):
        for name in ("run_unreal_desk_diagnostic.py", "run_unreal_contact_diagnostic.py"):
            tree = ast.parse((ROOT / "tools" / name).read_text())
            self.assertTrue(any(isinstance(x, ast.Constant) and x.value == "-Sub01ExitAfterCapture" for x in ast.walk(tree)))
        self.assertNotIn("-Sub01ExitAfterCapture", (ROOT / "tools/run_unreal_native_window_recording.py").read_text())


if __name__ == "__main__":
    unittest.main()
