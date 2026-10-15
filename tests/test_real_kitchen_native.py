"""No Blender/UE: fail-closed packet/bridge guards and executed native motion policy."""
import ast
import copy
import json
import math
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
from unreal_import_real_kitchen import same_triangles, run as native_import, detach_failed_import


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


def native_fixture(proof, suffix='_R5'):
    root = '/Game/Sub01Home/RealKitchen/V_'+proof['export_sha256'][:12]+suffix+'/'
    return {'schema': 'sub01.real-kitchen-native-import.v1', 'export_sha256': proof['export_sha256'],
            'parts': [{'part': p['name'], 'mesh': root+'Scene/StaticMeshes/Mesh_'+str(i)+'.Mesh_'+str(i),
                       'surface_parity': {'all_native_triangles_matched': True}} for i, p in enumerate(proof['parts'])],
            'hinges': copy.deepcopy(proof['hinges']), 'protected_originals_verified': 583}


class KitchenGuards(unittest.TestCase):
    def test_failed_import_detaches_every_new_mesh_before_any_actor_destroy(self):
        events = []
        class Component:
            def set_static_mesh(self, mesh):
                self.mesh = mesh
                events.append('detach')
        class Actor:
            def __init__(self, name):
                self.name, self.components = name, [Component(), Component()]
            def get_path_name(self):
                return self.name
            def get_components_by_class(self, cls):
                return self.components
        original, one, two = Actor('protected'), Actor('owned1'), Actor('owned2')
        class Editor:
            def get_all_level_actors(self):
                return [original, one, two]
            def destroy_actor(self, actor):
                self.assert_detached = all(c.mesh is None for a in (one, two) for c in a.components)
                if not self.assert_detached:
                    raise AssertionError('destroyed actor before releasing all meshes')
                events.append('destroy')
                return True
        self.assertEqual(detach_failed_import(types.SimpleNamespace(StaticMeshComponent=Component), Editor(), {'protected': {}}), 2)
        self.assertEqual(events, ['detach']*4+['destroy']*2)
        self.assertTrue(all(not hasattr(c, 'mesh') for c in original.components))

    def test_analytic_swept_bound_contains_between_endpoint_extremum(self):
        # Endpoint-only AABBs miss x=sqrt(2) halfway through this real circular arc.
        box = bundle.swept_bounds([(1., 1., 2.)], (0., 0., 0.), -math.pi/2)
        self.assertGreaterEqual(box[1][0], math.sqrt(2))
        for i in range(1001):
            angle = -math.pi/2*i/1000
            point = (math.cos(angle)-math.sin(angle), math.sin(angle)+math.cos(angle), 2.)
            self.assertTrue(all(box[0][k] <= point[k] <= box[1][k] for k in range(3)))

    def test_native_retained_triangle_check_detects_changed_shape_with_same_bounds(self):
        source = [[[0., 0., 0.], [100., 0., 0.], [0., 100., 0.]],
                  [[100., 0., 0.], [100., 100., 0.], [0., 100., 0.]]]
        reordered = [list(reversed(t)) for t in reversed(source)]
        self.assertTrue(same_triangles(source, reordered))
        modified = copy.deepcopy(reordered)
        modified[0][1][0] -= 1.
        self.assertFalse(same_triangles(source, modified))
        self.assertFalse(same_triangles(source, source[:1]))
        self.assertFalse(same_triangles(source, [source[0], source[1][:2]]))

    def test_actual_previous_sink_only_pass_cannot_activate_native_import(self):
        previous = json.loads((ROOT/'docs/proposed/actual-kitchen-source-proof-20261014.json').read_text())
        self.assertTrue(previous['source_report']['source_export_ready'])
        with self.assertRaises(ValueError):
            bundle.validate_manifest(previous['source_report'])
        class NoNativeActions:
            def __getattr__(self, name):
                raise AssertionError('Old receipt reached native API '+name)
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'native-kitchen.json').write_text(json.dumps(previous['source_report']))
            with self.assertRaises(ValueError):
                native_import(directory, dry_run=False, u=NoNativeActions())
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
        underside = [[x, .8675, z] for x, y, z in triangle]
        board_side = [underside[0], underside[1], [-3., .8495, -3.8]]
        self.assertTrue(bundle.allowed_contact(board_side, underside, 65, actual))
        board_side[2][1] = .86751
        self.assertFalse(bundle.allowed_contact(board_side, underside, 65, actual))
        foot_side = [triangle[0], triangle[1], [-3., .125, -3.8]]
        self.assertTrue(bundle.allowed_contact(foot_side, triangle, 0, actual))

    def test_shipped_bridge_preserves_existing_controls_and_masks_private_stale(self):
        original = (ROOT/'tools/unreal_home_state_bridge.py').read_text()
        patched = original  # Exercise the actual shipped bridge, not an optional installer.
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
        proof = fixture()
        h, c = runtime.install(header, cpp, proof, native_fixture(proof))
        self.assertIn('/V_aaaaaaaaaaaa_R5/', c)
        self.assertIn('SUB01_KITCHEN_RUNTIME', c)
        self.assertIn('if(TryNativeKitchen(Hit.GetComponent()))return;', c)
        self.assertNotIn('@@', c)
        with self.assertRaises(ValueError):
            runtime.install(h, c, proof, native_fixture(proof))

    def test_adapter_refuses_absent_or_mixed_wrong_native_asset_versions(self):
        proof = fixture()
        with self.assertRaises(ValueError):
            runtime.methods(proof)
        native = native_fixture(proof)
        self.assertEqual(runtime.native_asset_root(proof, native), '/Game/Sub01Home/RealKitchen/V_aaaaaaaaaaaa_R5/')
        for mutate in (
            lambda d: d['parts'][0].update(mesh=d['parts'][0]['mesh'].replace('_R5/', '_R6/')),
            lambda d: d['parts'][0].update(mesh=d['parts'][0]['mesh'].replace('aaaaaaaaaaaa', 'bbbbbbbbbbbb')),
            lambda d: d['parts'].pop(),
            lambda d: d['hinges'].pop(),
            lambda d: d['parts'][0].update(surface_parity={'all_native_triangles_matched': False}),
        ):
            bad = copy.deepcopy(native)
            mutate(bad)
            with self.assertRaises(ValueError):
                runtime.native_asset_root(proof, bad)

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
