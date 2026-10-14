import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import stage_unreal_home_runtime as stage
from unreal_native_control import METHODS


class MovementOwner(unittest.TestCase):
    def test_actual_generated_keyboard_branches_cannot_fight_route_or_live(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "Config").mkdir()
            (project / "Sub01HomeLab.uproject").write_text("{}")
            stage.stage(project)
            cpp = (project / "Source/Sub01HomeLab/Sub01HomeLab.cpp").read_text()
            forward = cpp.split("void ASub01HomeCharacter::Forward(float Value) {", 1)[1].split("\n}", 1)[0]
            right = cpp.split("void ASub01HomeCharacter::Right(float Value) {", 1)[1].split("\n}", 1)[0]
        pre = r'''
#include <cassert>
enum class EPrivateViewMode {Manual,Diagnostic,Live};
EPrivateViewMode PrivateViewMode=EPrivateViewMode::Manual;
bool LiveHome=false,RouteActive=false,HandsDiagnosticSeat=false;
struct Rot{float Yaw=0;};struct Control{Rot GetControlRotation(){return {};}}controller;
Control*Controller=&controller;struct FRotator{FRotator(int,float,int){}};
enum class EAxis{X,Y};struct FRotationMatrix{FRotationMatrix(FRotator){}int GetUnitAxis(EAxis){return 1;}};
int Calls=0;void AddMovementInput(int,float){++Calls;}
void Forward(float Value){
''' + forward + "\n}\nvoid Right(float Value){\n" + right + r'''
}
void both(){Forward(1);Right(1);}
int main(){both();assert(Calls==2);
 LiveHome=true;both();assert(Calls==2);LiveHome=false;
 RouteActive=true;both();assert(Calls==2);RouteActive=false;
 HandsDiagnosticSeat=true;both();assert(Calls==2);HandsDiagnosticSeat=false;
 PrivateViewMode=EPrivateViewMode::Diagnostic;both();assert(Calls==2);
 PrivateViewMode=EPrivateViewMode::Live;both();assert(Calls==2);
 PrivateViewMode=EPrivateViewMode::Manual;both();assert(Calls==4);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "owner.cpp"
            binary = Path(directory) / "owner"
            source.write_text(pre)
            subprocess.run(["c++", "-std=c++17", str(source), "-o", str(binary)], check=True, capture_output=True)
            subprocess.run([str(binary)], check=True)

    def test_explicit_mode_switch_invalidates_physical_evidence_without_teleport(self):
        switch = METHODS.split("bool ASub01HomeCharacter::SwitchNativeWalkView", 1)[1].split("void ASub01HomeCharacter::UpdatePrivateNativeControl", 1)[0]
        self.assertNotIn("SetActorLocation", switch)
        self.assertNotIn("NativeSeatVerified=true", switch)
        self.assertIn("NativeSeatVerified=false", switch)
        self.assertIn("PCBridge->SetOperatorFocus(false)", switch)
        self.assertIn("NativeFeedbackLastAck=-1", switch)
        self.assertIn("NativeFeedbackConsumer=FGuid::NewGuid()", switch)
        self.assertIn('TEXT("manual")', METHODS)
        self.assertIn("SwitchNativeWalkView(Live)", METHODS)

    def test_actual_manual_reset_releases_only_cached_live_privacy(self):
        body = METHODS.split(" LiveHome=false;", 1)[1].split(" NativeFeedbackBound=false;", 1)[0]
        code = "#include <cassert>\nbool LiveHome=true,LiveHomeFresh=true,LiveHomeBindWaiting=true,NativeSeatVerified=true,LiveHomePrivate=true;\nvoid reset(bool UseLiveSource){LiveHome=false;" + body + "}\nint main(){reset(true);assert(LiveHomePrivate);assert(!NativeSeatVerified&&!LiveHomeFresh);reset(false);assert(!LiveHomePrivate);}\n"
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"privacy.cpp";binary=Path(directory)/"privacy"
            source.write_text(code)
            subprocess.run(["c++","-std=c++17",str(source),"-o",str(binary)],check=True,capture_output=True)
            subprocess.run([str(binary)],check=True)


if __name__ == "__main__":
    unittest.main()
