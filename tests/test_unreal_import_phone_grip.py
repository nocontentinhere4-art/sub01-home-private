import copy
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import unreal_import_phone_grip as phone


class PhoneImportTests(unittest.TestCase):
    def source(self):
        root=ROOT/'docs/proposed/phone-grip-native-export'
        return [json.loads((root/n).read_text()) for n in ('phone-grip-fbx-audit.json','phone-grip-fbx-roundtrip.json','packet-contract-check.json')]

    def test_actual_written_export_and_roundtrip_are_coherent(self):
        row=phone.check_source(*self.source())
        self.assertEqual(row['frames'],557)
        self.assertAlmostEqual(row['duration_s'],556/30,places=4)
        self.assertEqual(phone.OBJECT,'/Game/Sub01Hands/Phone/SUB01_PhoneGrip.SUB01_PhoneGrip')
        self.assertNotIn('SUB01_Phone.',phone.OBJECT)

    def test_other_clip_or_missing_sample_cannot_be_substituted(self):
        for field,value in [('sha256','wrong'),('derived_glb_sha256','wrong'),('frames',556),('duration_s',18.0)]:
            audit,rt,contract=self.source();audit['clips'][0][field]=value
            with self.subTest(field=field),self.assertRaises(RuntimeError):phone.check_source(audit,rt,contract)
        audit,rt,contract=self.source();rt['actual_fbx_key_counts']=[556,557]
        with self.assertRaises(RuntimeError):phone.check_source(audit,rt,contract)

    def test_owner_names_and_source_only_gates_are_required(self):
        audit,rt,contract=self.source();audit['bone_names'][-1]=audit['bone_names'][0]
        with self.assertRaises(RuntimeError):phone.check_source(audit,rt,contract)
        audit,rt,contract=self.source();rt['ue_imported']=True
        with self.assertRaises(RuntimeError):phone.check_source(audit,rt,contract)


if __name__=='__main__':unittest.main()
