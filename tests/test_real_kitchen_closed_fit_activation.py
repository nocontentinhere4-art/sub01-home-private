"""Regression checks for exact old-kitchen retirement and native hinge rebinding."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import unreal_replace_real_kitchen_closed_fit as activation
import unreal_kitchen_hinge_runtime as runtime
from test_real_kitchen_native import fixture, native_fixture


class ClosedFitActivation(unittest.TestCase):
    def test_retiring_collision_intentionally_changes_only_disabled_profile(self):
        actor=SimpleNamespace(get_path_name=lambda:'actor')
        component=SimpleNamespace(get_path_name=lambda:'component')
        before={'actor':{'hidden':False,'components':[{'path':'component','collision':'QueryAndPhysics','profile':'BlockAll','tags':['SUB01Kitchen:old','protected']}],'materials':['original']}}
        u=SimpleNamespace(CollisionEnabled=SimpleNamespace(NO_COLLISION='NoCollision'))
        after=activation.retired_snapshot_expected(u,before,[(actor,component)])
        self.assertEqual(after['actor']['components'][0]['profile'],'Custom')
        self.assertEqual(after['actor']['components'][0]['tags'],['protected'])
        self.assertTrue(after['actor']['hidden'])
        self.assertEqual(before['actor']['components'][0]['profile'],'BlockAll')
        self.assertEqual(after['actor']['materials'],before['actor']['materials'])

    def old_receipt(self):
        rows=[]
        for i in range(152):
            rows.append({'part':'part'+str(i),'component':activation.OLD_ACTOR_PREFIX+str(i),
                         'mesh':activation.OLD_PREFIX+'Scene/StaticMeshes/Mesh_'+str(i),
                         'moving_hinge':i//5 if i<40 else None,
                         'surface_parity':{'all_native_triangles_matched':True}})
        return {'schema':'sub01.real-kitchen-native-import.v1','export_sha256':activation.OLD_EXPORT,'parts':rows}

    def validate(self, row):
        raw=json.dumps(row).encode()
        with mock.patch.object(activation,'PREVIOUS_SHA',hashlib.sha256(raw).hexdigest()):
            return activation.validate_previous(raw)

    def test_receipt_requires_all_152_distinct_proved_old_parts_and_forty_hinges(self):
        row=self.old_receipt()
        self.assertEqual(len(self.validate(row)['parts']),152)
        for change in ('duplicate','foreign','unproved','hinge'):
            bad=copy.deepcopy(row)
            if change=='duplicate':bad['parts'][1]['component']=bad['parts'][0]['component']
            if change=='foreign':bad['parts'][1]['mesh']='/Game/Foreign/Mesh'
            if change=='unproved':bad['parts'][1]['surface_parity']['all_native_triangles_matched']=False
            if change=='hinge':bad['parts'][1]['moving_hinge']=7
            with self.assertRaises(ValueError,msg=change):self.validate(bad)
        with self.assertRaises(ValueError):activation.validate_previous(json.dumps(row).encode())

    def proofs(self):
        old=fixture();old['export_sha256']=activation.OLD_EXPORT
        new=copy.deepcopy(old);new['export_sha256']=activation.NEW_EXPORT
        return old,new

    def test_rebinding_changes_only_source_tables_preserving_motion_and_input(self):
        old,new=self.proofs()
        cpp='prefix\n'+runtime.methods(old,native_fixture(old))+'\nsuffix'
        result=runtime.rebind_installed(cpp,new,native_fixture(new))
        self.assertIn('V_accd954c120a_R5/',result)
        self.assertNotIn(activation.OLD_EXPORT,result)
        boundary='void ASub01HomeCharacter::InspectActualKitchen(){'
        self.assertEqual(cpp.split(boundary)[1],result.split(boundary)[1])
        self.assertTrue(result.startswith('prefix\n'))
        self.assertTrue(result.endswith('\nsuffix'))
        with self.assertRaises(ValueError):runtime.rebind_installed(result,new,native_fixture(new))
        with self.assertRaises(ValueError):runtime.rebind_installed(cpp,new,None)
        with self.assertRaises(ValueError):runtime.rebind_installed(cpp.replace('mesh-0','mesh-1',1),new,native_fixture(new))

    def test_sink_retention_requires_exact_proved_full_source_mesh(self):
        row={'retained_sink_full_source_restore':[{'node':164,'source_triangles':2700,'native_full_triangles':2700,
              'owned_mesh':'/Game/Sub01Home/RealKitchen/V_9556495fa816_RetainedSink164/Mesh.Mesh'}]}
        self.assertEqual(list(activation.retained_paths(row)),[164])
        row['retained_sink_full_source_restore'][0]['native_full_triangles']=100
        with self.assertRaises(ValueError):activation.retained_paths(row)


if __name__=='__main__':unittest.main()
