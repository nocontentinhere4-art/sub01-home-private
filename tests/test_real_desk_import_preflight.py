import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from unreal_real_desk_import_preflight import activate,validate_export

class FailClosed(unittest.TestCase):
 def test_missing_actual_export_is_refused(self):
  with self.assertRaisesRegex(ValueError,'receipt missing'):validate_export('/missing',{})
 def test_unreviewed_lamp_binding_cannot_activate(self):
  with self.assertRaisesRegex(RuntimeError,'REFUSED'):activate()

if __name__=='__main__':unittest.main()
