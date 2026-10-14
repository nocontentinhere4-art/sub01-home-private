import unittest
from types import SimpleNamespace
from pathlib import Path
from tools.unreal_import_structural_lamp_union import import_owned_union_mesh
class Mesh:
 def __init__(self,path,triangles=160):self.path=path;self.triangles=triangles
 def get_path_name(self):return self.path
 def get_editor_property(self,name):return [object()]
class AssetOnlyTest(unittest.TestCase):
 def api(self,existing=0,triangles=160):
  dest='/Game/Sub01Home/StructuralLampUnionMeshOnly/V_0123456789ab';assets={dest+'/mesh'+str(i):Mesh(dest+'/mesh'+str(i),triangles) for i in range(existing)};calls=[]
  def imported(tasks):
   calls.append(tasks[0]);assets[dest+'/mesh']=Mesh(dest+'/mesh',triangles)
  u=SimpleNamespace(StaticMesh=Mesh,AssetImportTask=lambda:SimpleNamespace(),
   EditorAssetLibrary=SimpleNamespace(list_assets=lambda *a,**kw:list(assets),load_asset=lambda p:assets[p]),
   AssetToolsHelpers=SimpleNamespace(get_asset_tools=lambda:SimpleNamespace(import_asset_tasks=imported)),
   InterchangeManager=SimpleNamespace(get_interchange_manager_scripted=lambda:SimpleNamespace(wait_until_all_tasks_done=lambda flag:None)),
   ProceduralMeshLibrary=SimpleNamespace(get_section_from_static_mesh=lambda mesh,lod,section:([],list(range(mesh.triangles*3)))))
  return u,calls
 def test_asset_only_import_and_hot_retry(self):
  u,calls=self.api();import_owned_union_mesh(u,Path('/source.glb'),'0123456789abcdef');self.assertEqual(len(calls),1);self.assertFalse(calls[0].replace_existing)
  import_owned_union_mesh(u,Path('/source.glb'),'0123456789abcdef');self.assertEqual(len(calls),1)
 def test_ambiguous_assets_refused_before_placement(self):
  u,calls=self.api(existing=2)
  with self.assertRaisesRegex(RuntimeError,'exactly one'):import_owned_union_mesh(u,Path('/source.glb'),'0123456789abcdef')
  self.assertEqual(calls,[])
 def test_incomplete_import_geometry_refused(self):
  u,_=self.api(triangles=159)
  with self.assertRaisesRegex(RuntimeError,'exactly160'):import_owned_union_mesh(u,Path('/source.glb'),'0123456789abcdef')
if __name__=='__main__':unittest.main()
