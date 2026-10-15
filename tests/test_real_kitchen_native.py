"""No Blender/UE: fail-closed packet/bridge guards and executed native motion policy."""
import ast
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
sys.path.insert(0, str(ROOT))
import prepare_real_kitchen_native_bundle as bundle
import unreal_kitchen_hinge_runtime as runtime
import unreal_kitchen_state_bridge as bridge
from unreal_import_real_kitchen import same_triangles


def fixture():
    """Synthetic metadata only. Never an actual retained-house collision receipt."""
    receipt = json.loads((ROOT/'docs/proposed/actual-kitchen-source-proof-20261014.json').read_text())
    report = copy.deepcopy(receipt['source_report'])
    digest = report['derived_sha256']
    prefix = 'SUB01_RealKitchen_'+digest[:12]+'_'
    parts = [{'name': prefix+r['assembly']+'__'+r['source_part'], 'assembly': r['assembly'],
              'source_part': r['source_part'], 'bounds_browser_m': [[0., 0., 0.], [1., 1., 1.]],
              'triangles': r['polygons']} for r in report['exported_parts']]
    hinges = []
    for r in report['assemblies']:
        if r['hinge_browser_m'] is None:
            continue
        lower = r['name'].startswith('Lower_')
        i = int(r['name'].rsplit('_' if lower else ' ', 1)[1])-1+(4 if lower else 0)
        hinges.append({'index': i, 'assembly': r['name'],
                       'hinge_ue_cm': [r['hinge_browser_m'][k]*100 for k in (0, 2, 1)],
                       'parts': [p['name'] for p in parts if p['assembly'] == r['name']]})
    return {'schema': bundle.SCHEMA, 'source_sha256': bundle.base.HOME_SHA,
            'export_sha256': 'a'*64, 'unprefixed_export_sha256': digest, 'prefix': prefix,
            'binary_geometry_pbr_unchanged_by_uid': True, 'hide_only_source_nodes': [63, 178],
            'parts': parts, 'hinges': sorted(hinges, key=lambda r: r['index']), 'source_report': report,
            'full_collision_proof': {'ok': True, 'epsilon_m': 0., 'retained_source_sha256': bundle.base.HOME_SHA,
                'retired_source_nodes': [63, 178], 'protected_triangle_count': 1, 'door_home_poses': 720,
                'all_poses_inside_audited_region': True,
                'door_pair_bvh_tests': 0, 'door_pair_aabb_rejects': 28*90*90}}


class KitchenGuards(unittest.TestCase):
    def test_native_retained_triangle_check_detects_changed_shape_with_same_bounds(self):
        source = [[[0., 0., 0.], [100., 0., 0.], [0., 100., 0.]],
                  [[100., 0., 0.], [100., 100., 0.], [0., 100., 0.]]]
        reordered = [list(reversed(t)) for t in reversed(source)]
        self.assertTrue(same_triangles(source, reordered))
        modified = copy.deepcopy(reordered)
        modified[0][1][0] -= 1.
        self.assertFalse(same_triangles(source, modified))
        self.assertFalse(same_triangles(source, source[:1]))

    def test_actual_previous_sink_only_pass_cannot_activate_native_import(self):
        previous = json.loads((ROOT/'docs/proposed/actual-kitchen-source-proof-20261014.json').read_text())
        self.assertTrue(previous['source_report']['source_export_ready'])
        with self.assertRaises(ValueError):
            bundle.validate_manifest(previous['source_report'])
        good = fixture()
        bundle.validate_manifest(good)
        for mutation in (
            lambda d: d['parts'].pop(),
            lambda d: d['hinges'][0]['hinge_ue_cm'].__setitem__(0, -375.),
            lambda d: d['full_collision_proof'].__setitem__('door_pair_aabb_rejects', 28*90*90-1),
            lambda d: d['source_report']['leg_contacts'][0].__setitem__('floor_contact_error_m', .001),
            lambda d: d['parts'][0]['bounds_browser_m'][0].__setitem__(0, float('nan')),
            lambda d: d['hide_only_source_nodes'].append(164),
            lambda d: d['source_report']['source_collision_checks'].__setitem__('sink_source_bvh_clear', False),
        ):
            bad = copy.deepcopy(good)
            mutation(bad)
            with self.assertRaises(ValueError):
                bundle.validate_manifest(bad)

    def test_contact_is_only_actual_floor_or_counter_underside_not_penetration(self):
        actual = {'floor_m': .025, 'counter_underside_m': .8675}
        triangle = [[-3., .025, -3.8], [-2., .025, -3.8], [-3., .025, -3.2]]
        self.assertTrue(bundle.allowed_contact(triangle, triangle, 0, actual))
        self.assertFalse(bundle.allowed_contact(triangle, triangle, 160, actual))
        penetrating = copy.deepcopy(triangle)
        penetrating[0][1] -= .00001
        self.assertFalse(bundle.allowed_contact(penetrating, triangle, 0, actual))
        slab_top = [[x, .9225, z] for x, y, z in triangle]
        self.assertFalse(bundle.allowed_contact(slab_top, slab_top, 65, actual))

    def test_real_bridge_installer_preserves_existing_controls_and_masks_private_stale(self):
        original = (ROOT/'tools/unreal_home_state_bridge.py').read_text()
        patched = bridge.install(original)
        ast.parse(patched)
        module = types.ModuleType('kitchen_bridge_test')
        module.__file__ = str(ROOT/'tools/unreal_home_state_bridge.py')
        sys.modules[module.__name__] = module
        try:
            exec(compile(patched, module.__file__, 'exec'), module.__dict__)
            patch = {'lowerCabinets': [True, False, False, True], 'doors': {'front': 'open'}}
            self.assertEqual(module.validate_controls(patch), patch)
            for malformed in ([0, 0, 0, 0], [True]*5, 'false', None):
                with self.assertRaises(ValueError):
                    module.validate_controls({'cabinets': malformed})
            with self.assertRaises(ValueError):
                module.validate_controls({'lamp': True})
            from home_world import HomeWorld
            clock = [1000.]
            model = module.HomeStateModel(clock=lambda: clock[0])
            world = HomeWorld()
            world.settings['cabinets'] = [True, False, False, False]
            model.set_connected(True)
            model.apply_tick({'type': 'tick', 'home': world.view(), 'sleep': {'stage': 'AWAKE'}})
            doc = model.document()
            self.assertEqual(doc['kitchen']['cabinets'], [True, False, False, False])
            doc['kitchen']['cabinets'][0] = False
            self.assertTrue(model.document()['kitchen']['cabinets'][0])
            clock[0] += 4
            self.assertIsNone(model.document()['kitchen'])
            self.assertIsNone(bridge.kitchen_state(world.view(), 'live', True))
            with self.assertRaises(ValueError):
                bridge.install(patched)
        finally:
            del sys.modules[module.__name__]

    def test_optional_adapter_requires_exact_packet_and_unique_generator_hooks(self):
        header = ' void Forward(float Value);'
        cpp = ' ConfigureActualPC();\n Super::Tick(DeltaSeconds);\n FString Device;\n'
        h, c = runtime.install(header, cpp, fixture())
        self.assertIn('SUB01_KITCHEN_RUNTIME', c)
        self.assertIn('if(TryNativeKitchen(Hit.GetComponent()))return;', c)
        self.assertNotIn('@@', c)
        with self.assertRaises(ValueError):
            runtime.install(h, c, fixture())

    @unittest.skipUnless(shutil.which('c++'), 'C++ compiler required')
    def test_native_policy_stops_at_intermediate_obstacles_both_directions_without_teleport(self):
        source = runtime.POLICY+r'''
#include <cassert>
#include <limits>
int main(){
 auto clear=[](double,double){return false;};double angle=0;
 for(int i=0;i<100;++i)angle=Sub01Kitchen::Advance(angle,88.2,1./60,clear);
 assert(angle==88.2);
 auto obstacle=[](double a,double b){return std::fmin(a,b)<41.2&&std::fmax(a,b)>41.;};
 assert(Sub01Kitchen::Advance(40.,88.2,.05,obstacle)==40.);
 assert(Sub01Kitchen::Advance(43.,0.,.05,obstacle)==43.);
 assert(Sub01Kitchen::Advance(0.,88.2,20.,clear)==3.5);
 assert(Sub01Kitchen::Advance(20.,0.,-1.,clear)==20.);
 assert(Sub01Kitchen::Advance(20.,0.,std::numeric_limits<double>::quiet_NaN(),clear)==20.);
 assert(Sub01Kitchen::Advance(100.,0.,.05,clear)==100.);
 for(int i=0;i<100;++i)angle=Sub01Kitchen::Advance(angle,0.,1./60,clear);
 assert(angle==0.);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'motion.cpp').write_text(source)
            subprocess.run(['c++', '-std=c++17', str(root/'motion.cpp'), '-o', str(root/'motion')], check=True, capture_output=True)
            subprocess.run([str(root/'motion')], check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
