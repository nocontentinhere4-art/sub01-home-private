import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import unreal_native_daylight_exposure as day
import unreal_native_fixture_emission as fixture
import unreal_native_view_settings as view
import stage_unreal_home_runtime as runtime


class DaylightExposureTests(unittest.TestCase):
    def test_bounded_day_curve_and_unchanged_night(self):
        compiler=shutil.which('c++')
        if not compiler:self.skipTest('C++ compiler unavailable')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);day.stage(root)
            source=root/'day.cpp';binary=root/'day'
            source.write_text('''#include "Sub01NativeDaylightExposurePolicy.h"
#include <cassert>
#include <limits>
int main(){using Sub01NativeDaylightExposure::DayMin;
using Sub01NativeDaylightExposure::MaximumScale;
using Sub01NativeDaylightExposure::FloorClamped;
assert(MaximumScale(-3,1,.78)==16);
assert(std::abs(MaximumScale(DayMin(11),1,.78)-31.25307)<.0001);
assert(FloorClamped(.01183,-3,.78)); // Actual native avg below .0225 floor.
assert(!FloorClamped(.0225,-3,.78));
assert(!FloorClamped(.03,-3,.78));
assert(MaximumScale(-3,1,0)==0);
for(int i=0;i<=2400;i++){double h=i/100.,v=DayMin(h);assert(v>=-4&&v<=-3);if(h<=6||h>=18)assert(std::abs(v+3)<1e-12);}
assert(DayMin(12)==-4);assert(std::abs(DayMin(11)+3.9659258263)<1e-9);
assert(DayMin(-1)==-3&&DayMin(25)==-3);
assert(DayMin(std::numeric_limits<double>::quiet_NaN())==-3);}
''')
            subprocess.run([compiler,'-std=c++17',str(source),'-o',str(binary)],check=True,capture_output=True)
            subprocess.run([str(binary)],check=True,capture_output=True)

    def test_actual_view_template_and_fixture_integration_is_gated_and_narrow(self):
        header,cpp=fixture.install(runtime.HEADER+view.FIELDS,runtime.CPP+view.METHODS)
        header,cpp=day.install(header,cpp)
        self.assertIn('NativeDaylightExposureVerified=false',header)
        self.assertLess(cpp.index('if(HasHour&&!ValidateNativeDaylightExposure())'),cpp.index('if(HasFov)ViewCamera->SetFieldOfView'))
        self.assertIn('ApplyNativeDaylightExposure(PrivateEnvironmentHour);',cpp)
        self.assertIn('Sky->SetIntensity(.4225f*FMath::Max(.08f,Elevation));',cpp)
        self.assertIn('Sun->SetIntensity(3.2f*Elevation);',cpp)
        self.assertIn('ApplyNativeFixtureEmission(LampName,Enabled);',cpp)
        self.assertNotIn('SetActorLocation',day.METHODS)
        self.assertIn('r.EyeAdaptation.LensAttenuation',day.METHODS)
        self.assertIn('r.DefaultFeature.AutoExposure.ExtendDefaultLuminanceRange',day.METHODS)
        self.assertIn('Settings.AutoExposureBiasCurve',day.METHODS)
        self.assertEqual(day.METHODS.count('Post->Settings.'),1)
        with self.assertRaises(ValueError):day.install(header,cpp)


if __name__=='__main__':unittest.main()
