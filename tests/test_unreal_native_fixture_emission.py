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
        self.assertEqual(fixture.METHODS.count('SetScalarParameterValue'),2)
        self.assertEqual(fixture.METHODS.count('if(I==6)'),2)
        self.assertIn('I==6?1:0,Prepared[I]', fixture.METHODS)
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
using Sub01NativeFixtureEmission::ValidBinding;
using Sub01NativeFixtureEmission::SameFactor;
assert(ValidBinding(198,true,true,false,false,false));
assert(!ValidBinding(198,true,false,false,false,false));
assert(ValidBinding(199,false,false,true,true,true));
assert(!ValidBinding(198,false,false,true,true,true)); // Colour MIC allowed on node199 only.
assert(!ValidBinding(199,false,false,false,true,true)); // Broad owned-prefix match forbidden.
assert(!ValidBinding(199,false,false,true,false,true)); // Extra parent chain forbidden.
assert(!ValidBinding(199,false,false,true,true,false)); // Unreviewed variant forbidden.
assert(SameFactor(.08,.04568999,.0161245,1,.08,.04568999,.0161245,1));
assert(!SameFactor(.08,.04568999,.0161245,1,.081,.04568999,.0161245,1));
assert(ValidOriginalFactor(1,.62396038,.23074006,1));
assert(ValidOriginalFactor(.08,.04568999,.0161245,1));
assert(!ValidOriginalFactor(0,0,0,1));
assert(!ValidOriginalFactor(-1,1,1,1));
assert(!ValidOriginalFactor(1,1,1,std::numeric_limits<double>::infinity()));
assert(!ValidOriginalFactor(std::numeric_limits<double>::quiet_NaN(),1,1,1));}
''')
            subprocess.run([compiler,'-std=c++17',str(source),'-o',str(binary)],check=True,capture_output=True)
            subprocess.run([str(binary)],check=True,capture_output=True)

    def test_genuine_bulb_uses_pinned_source_emission_not_zeroed_importer_values(self):
        import hashlib
        import json
        source=Path(__file__).resolve().parents[1]/'web/house/assets/desk_lamp_arm_01/desk_lamp_arm_01.gltf'
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),
                         '2ac8389afc1519449a9cfdf7efd9fa36780a2177bb47ab58f7a7dda7d247dc8c')
        material=json.loads(source.read_text())['materials'][1]
        self.assertEqual(material['name'],'desk_lamp_arm_01_light')
        self.assertEqual(material['emissiveFactor'],[1,.9837890267372131,.649111270904541])
        self.assertNotIn('KHR_materials_emissive_strength',material.get('extensions',{}))
        self.assertIn('FLinearColor(1.f,.9837890267372131f,.649111270904541f,1.f)',fixture.METHODS)
        # The importer zeroed BOTH parameters: restoring factor alone stays dark.
        self.assertIn('GetAllScalarParameterInfo',fixture.METHODS)
        self.assertIn('SavedStrength!=0.f',fixture.METHODS)
        self.assertIn('if(I==6)MID->SetScalarParameterValue(TEXT("EmissiveStrength"),Enabled[I]?1.f:0.f)',fixture.METHODS)
        self.assertIn('if(I==6)NativeFixtureMIDs[I]->SetScalarParameterValue(TEXT("EmissiveStrength"),Enabled?1.f:0.f)',fixture.METHODS)
        self.assertLess(fixture.METHODS.index('SavedStrength!=0.f'),fixture.METHODS.index('UMaterialInstanceDynamic::Create'))
        self.assertIn('const bool RealEnabled=Enabled[1];Enabled.Add(RealEnabled);',fixture.METHODS)
        self.assertIn('NativeFixtureComponents[I]->GetMaterial(I==6?1:0)',fixture.METHODS)

    def test_genuine_lamp_enabled_append_executes_without_self_alias(self):
        compiler = shutil.which('c++')
        if not compiler:self.skipTest('C++ compiler unavailable')
        # Execute the generated append with the same address-range guard as TArray.
        # Spare capacity is deliberate: UE rejects aliasing even without reallocation.
        import re
        statement = re.search(r'const bool RealEnabled=Enabled\[1\];Enabled\.Add\(RealEnabled\);', fixture.METHODS)
        self.assertIsNotNone(statement)
        harness = r"""#include <cstdint>
#include <initializer_list>
#include <stdexcept>
struct BoolArray {
 bool values[22]{}; int count=6;
 bool& operator[](int i){return values[i];}
 void Add(const bool& value){
  auto p=reinterpret_cast<std::uintptr_t>(&value);
  auto lo=reinterpret_cast<std::uintptr_t>(values);
  if(p>=lo && p<lo+sizeof(values))throw std::runtime_error("self alias");
  values[count++]=value;
 }
};
int main(){for(bool state:{false,true}){BoolArray Enabled;Enabled[1]=state;
APPEND
if(Enabled.count!=7 || Enabled[6]!=state)return 3;
}return 0;}
"""
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name,append,expected in [('fixed',statement.group(),0),('old','Enabled.Add(Enabled[1]);',None)]:
                source=root/(name+'.cpp');binary=root/name
                source.write_text(harness.replace('APPEND',append))
                subprocess.run([compiler,'-std=c++17',str(source),'-o',str(binary)],check=True,capture_output=True)
                result=subprocess.run([str(binary)],capture_output=True)
                if expected is None:self.assertNotEqual(result.returncode,0)
                else:self.assertEqual(result.returncode,expected,result.stderr)

    def test_exact_owned_colour_mic_path_matches_repair_naming(self):
        from unreal_home_materials_fix import usage_mic_name
        original='/Game/Sub01Home/ImportedScene/full-home/Materials/Material_91.Material_91'
        name=usage_mic_name(original)
        path='/Game/Sub01Home/MaterialFix/'+name+'.'+name
        self.assertIn(path, fixture.METHODS)
        self.assertIn('NativeFixtureEmissionParentMaterial13', fixture.FIELDS)
        self.assertIn('NativeFixtureEmissionParentMaterial63', fixture.FIELDS)
        self.assertIn('NativeFixtureEmissionParentMaterial91', fixture.FIELDS)


if __name__ == '__main__':
    unittest.main()
