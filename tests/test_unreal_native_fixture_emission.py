import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import unreal_native_fixture_emission as fixture
import unreal_native_view_settings as view
import stage_unreal_home_runtime as runtime


class NativeFixtureEmissionTests(unittest.TestCase):
    def test_actual_view_hooks_preflight_before_light_mutation_and_duplicate_refusal(self):
        header, cpp = fixture.install(runtime.HEADER+view.FIELDS, runtime.CPP+view.METHODS)
        self.assertIn('NativeFixtureEmissionVerified=false', header)
        self.assertLess(cpp.index('if(LampChanges&&!PrepareNativeFixtureEmission())'), cpp.index('Light->SetIntensity(Enabled?Lamps[LampName]:0.f)'))
        self.assertIn('ApplyNativeFixtureEmission(LampName,Enabled)', cpp)
        self.assertLess(fixture.METHODS.index('GetAllVectorParameterInfo'), fixture.METHODS.index('UMaterialInstanceDynamic::Create'))
        self.assertLess(fixture.METHODS.index('UMaterialInstanceDynamic::Create'), fixture.METHODS.index('Components[I]->SetMaterial'))
        self.assertIn('Enabled?NativeFixtureOriginalFactors[I]:FLinearColor(0,0,0,0)', cpp)
        self.assertNotIn('SetScalarParameterValue', fixture.METHODS)
        self.assertNotIn('SetActorLocation', fixture.METHODS)
        with self.assertRaises(ValueError):fixture.install(header, cpp)
        with self.assertRaises(ValueError):fixture.install(runtime.HEADER+view.FIELDS, runtime.CPP)

    def test_native_factor_guard_executes_finite_nonzero_and_negative_checks(self):
        compiler = shutil.which('c++')
        if not compiler:self.skipTest('C++ compiler unavailable')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);fixture.stage(root)
            source=root/'guard.cpp';binary=root/'guard'
            source.write_text('''#include "Sub01NativeFixtureEmissionPolicy.h"
#include <cassert>
#include <limits>
int main(){using Sub01NativeFixtureEmission::ValidOriginalFactor;
assert(ValidOriginalFactor(1,.62396038,.23074006,1));
assert(ValidOriginalFactor(.08,.04568999,.0161245,1));
assert(!ValidOriginalFactor(0,0,0,1));
assert(!ValidOriginalFactor(-1,1,1,1));
assert(!ValidOriginalFactor(1,1,1,std::numeric_limits<double>::infinity()));
assert(!ValidOriginalFactor(std::numeric_limits<double>::quiet_NaN(),1,1,1));}
''')
            subprocess.run([compiler,'-std=c++17',str(source),'-o',str(binary)],check=True,capture_output=True)
            subprocess.run([str(binary)],check=True,capture_output=True)


if __name__ == '__main__':
    unittest.main()
