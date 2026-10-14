"""Run the exact native contact decision, including the measured hover defect."""
import importlib.util
from pathlib import Path
import subprocess
import shutil
import pytest


def test_signed_actual_key_contact(tmp_path):
    compiler = shutil.which('c++')
    if not compiler:
        pytest.skip('C++ compiler unavailable')
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('key_contact', root / 'tools/unreal_keyboard_contact_target.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / 'contact.cpp'
    source.write_text('#include <cmath>\n#include <cassert>\n#include <limits>\n' + module.CPP + r'''
int main(){
 double d;
 // Actual right-hand frame 3.2: the over-key skin floats, even though an
 // outside-key fingertip is lower. It must move DOWN, not up three cm.
 assert(Sub01KeyboardContactCorrection(87.38975858,88.19919327,350,d));
 assert(d<0&&std::fabs(d+.72943469)<1.e-7);
 assert(std::fabs(88.19919327+d-87.46975858)<1.e-7);
 // Actual left-hand frame 3.0: penetrating true over-key skin needs lifting.
 assert(Sub01KeyboardContactCorrection(87.38975858,82.63389979,225,d));
 assert(d>0&&std::fabs(d-4.83585879)<1.e-7);
 assert(!Sub01KeyboardContactCorrection(10,10.08,4,d));
 assert(!Sub01KeyboardContactCorrection(10,0,3,d)&&d==0);
 assert(!Sub01KeyboardContactCorrection(10,-20,4,d)&&d==0);
 assert(!Sub01KeyboardContactCorrection(10,40,4,d)&&d==0);
 assert(!Sub01KeyboardContactCorrection(std::numeric_limits<double>::quiet_NaN(),10,4,d));
 assert(!Sub01KeyboardContactCorrection(10,std::numeric_limits<double>::infinity(),4,d));
}
''')
    executable = tmp_path / 'contact'
    subprocess.run([compiler, '-std=c++17', str(source), '-o', str(executable)], check=True, capture_output=True)
    subprocess.run([str(executable)], check=True, capture_output=True)


def test_native_solver_uses_true_contact_and_preserves_fingers():
    source = (Path(__file__).resolve().parents[1] / 'tools/unreal_skin_contact_native.py').read_text()
    assert 'Sub01KeyboardContactCorrection(KeyMax.Z' in source
    assert 'GetNumberField(TEXT("overMinCm"))' in source
    assert 'Pen+.08' not in source
    assert 'Local[N]=OriginalLocal[N]' in source
    assert 'C.SetRotation(CapturedWrist)' in source
