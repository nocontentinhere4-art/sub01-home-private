import ast,copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import next_game_device_policy_refresh as m
class PolicyTests(unittest.TestCase):
 def source(self):return (Path(__file__).resolve().parents[1]/'home_minecraft_input.py').read_text()
 def test_only_three_exact_identity_assignments_change(self):
  before=ast.parse(self.source());after=ast.parse(m.policy_for_next(self.source(),222222,999999999));allowed={'PROJECT','NATIVE_PID','NATIVE_START_TICKS'}
  for tree in (before,after):
   tree.body=[n for n in tree.body if not(isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id in allowed for t in n.targets))]
  self.assertEqual(ast.dump(before,include_attributes=False),ast.dump(after,include_attributes=False))
  out=m.policy_for_next(self.source(),222222,999999999);self.assertIn(repr(m.NEXT_PROJECT),out);self.assertNotIn(repr(m.OLD_PROJECT),out)
 def test_invalid_or_duplicate_native_identity_refused(self):
  for pid,start in [(True,5),(1,False),(0,5),(-1,5),(1,0),('193148',5)]:
   with self.subTest(pid=pid,start=start),self.assertRaises(AssertionError):m.policy_for_next(self.source(),pid,start)
  with self.assertRaises(AssertionError):m.policy_for_next(self.source()+'\nPROJECT = '+repr(m.OLD_PROJECT)+'\n',222222,999999999)
 def test_proven_templates_are_pinned_and_compile(self):
  for name in m.TEMPLATE_SHA:compile(m.template(name),name,'exec')
if __name__=='__main__':unittest.main()
