"""Never rebuild shared source assets; source geometry gates remain caller-owned."""
import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from unreal_owned_mesh_source_geometry import prepare

class Settings:
 def __init__(self,values):self.values=copy.deepcopy(values)
 def get_editor_property(self,p):return self.values[p]
 def set_editor_property(self,p,v):self.values[p]=v
class FullSource(unittest.TestCase):
 def test_foreign_mesh_refused_before_any_api_mutation(self):
  mesh=NS(get_path_name=lambda:'/Game/Sub01Home/ImportedScene/Shared.Shared')
  with self.assertRaisesRegex(RuntimeError,'unowned/shared'):prepare(NS(),mesh,'/Game/Sub01Home/RealKitchen/V_test')
 def test_owned_nanite_mesh_rebuilds_and_saves_full_source(self):
  values={'enabled':True,'fallback_relative_error':1.,'keep_percent_triangles':.5,'trim_relative_error':.1}
  mesh=NS(get_path_name=lambda:'/Game/Sub01Home/RealKitchen/V_test/M.M',values=values)
  calls=[]
  def apply(m,s,apply):calls.append(apply);m.values=s.values
  sub=NS(get_nanite_settings=lambda m:Settings(m.values),set_nanite_settings=apply)
  u=NS(StaticMeshEditorSubsystem=object,get_editor_subsystem=lambda c:sub,EditorAssetLibrary=NS(save_loaded_asset=lambda *a,**kw:True))
  result=prepare(u,mesh,'/Game/Sub01Home/RealKitchen/V_test')
  self.assertEqual(calls,[True]);self.assertTrue(result['rebuilt']);self.assertFalse(mesh.values['enabled'])
  self.assertEqual(mesh.values['keep_percent_triangles'],1.);self.assertEqual(mesh.values['trim_relative_error'],0.)
 def test_already_full_non_nanite_mesh_is_untouched(self):
  mesh=NS(get_path_name=lambda:'/Game/Sub01Home/RealLinea140/V_test/M.M')
  sub=NS(get_nanite_settings=lambda m:Settings({'enabled':False}))
  u=NS(StaticMeshEditorSubsystem=object,get_editor_subsystem=lambda c:sub)
  self.assertFalse(prepare(u,mesh,'/Game/Sub01Home/RealLinea140/V_test')['rebuilt'])
if __name__=='__main__':unittest.main()
