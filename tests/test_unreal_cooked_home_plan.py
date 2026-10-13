import sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from plan_unreal_cooked_home import make_plan
from stage_unreal_home_runtime import stage

class CookedPlan(unittest.TestCase):
 def sources(self):
  with tempfile.TemporaryDirectory()as tmp:
   project=Path(tmp)/'Sub01HomeLab';project.mkdir();(project/'Config').mkdir();(project/'Sub01HomeLab.uproject').write_text('{}');stage(project)
   return (project/'Source/Sub01HomeLab/Sub01HomeLab.Build.cs').read_text(),(project/'Source/Sub01HomeLab.Target.cs').read_text()
 def test_actual_staged_game_target_and_dynamic_content_are_preserved(self):
  build,target=self.sources();plan=make_plan('/engine','/baseline/Sub01HomeLab.uproject','/proposal','/archive',build,target)
  self.assertEqual(plan['kind'],'proposed-not-executed-linux-game-cook')
  self.assertIn('ImageCore',plan['runtime_modules_verified'])
  argv=plan['cook_argv'];self.assertIn('-MapsToCook=/Game/Sub01Home/ActualHome',argv)
  self.assertIn('-cookdir=/proposal/Content/Sub01Hands/FBX+/proposal/Content/Sub01Home/Devices',argv)
  self.assertIn('unreal-skinned-contact-audit.json',plan['prepare_separate_copy_only_after_gates']['entries'])
  self.assertEqual(len(plan['required_verified_gates']),3)
  self.assertNotIn('-run',argv);self.assertNotIn('-server',argv)
 def test_accepted_baseline_and_editor_dependency_cannot_be_packaged_silently(self):
  build,target=self.sources()
  for proposal in ('/baseline/Sub01HomeLab.uproject','/baseline','/baseline/Content/cooked'):
   with self.assertRaises(ValueError):make_plan('/engine','/baseline/Sub01HomeLab.uproject',proposal,'/archive',build,target)
  with self.assertRaises(ValueError):make_plan('/engine','/baseline/Sub01HomeLab.uproject','/proposal','/baseline/Content/archive',build,target)
  with self.assertRaises(ValueError):make_plan('/engine','/baseline/Sub01HomeLab.uproject','/proposal','/archive',build.replace('"ImageCore"','"UnrealEd"'),target)
  with self.assertRaises(ValueError):make_plan('/engine','/baseline/Sub01HomeLab.uproject','/proposal','/archive',build,target.replace('TargetType.Game','TargetType.Editor'))

if __name__=='__main__':unittest.main()
