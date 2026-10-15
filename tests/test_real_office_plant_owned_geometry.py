"""Owned full-source clones preserve originals and refuse incomplete rebuilt geometry."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import real_office_plant as P
import home_asset_audit as H
import unreal_monitor_support_fix as G

TRI=[[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]]]
class Settings:
 def __init__(self,d):self.d=copy.deepcopy(d)
 def get_editor_property(self,n):return self.d[n]
 def set_editor_property(self,n,v):self.d[n]=v
class Mesh:
 def __init__(self,path):self.path=path;self.settings={'enabled':True,'fallback_percent_triangles':1.,'fallback_relative_error':1.,'fallback_target':'AUTO','keep_percent_triangles':1.,'trim_relative_error':0.}
 def get_path_name(self):return self.path
 def get_editor_property(self,n):return Settings(self.settings)
class Component:
 def __init__(self,mesh):self.mesh=mesh;self.mats=[NS(get_path_name=lambda:'originalMaterial')]
 def get_editor_property(self,n):return self.mesh
 def get_world_transform(self):return 'unchangedWorld'
 def get_materials(self):return self.mats
 def get_path_name(self):return 'originalComponent'
 def set_static_mesh(self,m):self.mesh=m
 def set_world_transform(self,*a):pass
 def set_collision_enabled(self,*a):pass
 def set_material(self,i,m):self.mats[i]=m

class OwnedGeometry(unittest.TestCase):
 def exercise(self,bad=False):
  original=Mesh('/Original.SharedPlant');component=Component(original);settings_before=copy.deepcopy(original.settings);created=[];destroyed=[];deleted=[]
  def duplicate(src,dst):
   self.assertEqual(src,original.path);m=Mesh(dst+'.'+dst.rsplit('/',1)[-1]);created.append(m);return m
  def spawn(*args):
   a=NS(c=Component(None));a.set_actor_label=lambda x:None;a.set_actor_hidden_in_game=lambda x:None;a.get_component_by_class=lambda x:a.c;return a
  sub=NS(get_nanite_settings=lambda m:Settings(m.settings),set_nanite_settings=lambda m,s,apply:setattr(m,'settings',copy.deepcopy(s.d)))
  library=NS(does_directory_exist=lambda d:bool(created)and not deleted,duplicate_asset=duplicate,save_loaded_asset=lambda *a,**kw:True,delete_directory=lambda d:deleted.append(d))
  with tempfile.TemporaryDirectory()as td:
   root=Path(td);(root/'SourceAssets').mkdir();(root/'SourceAssets/full-home.glb').write_bytes(b'source')
   u=NS(Paths=NS(project_dir=lambda:td),StaticMeshEditorSubsystem=object,StaticMeshActor=object,StaticMeshComponent=object,Vector=lambda *x:x,CollisionEnabled=NS(NO_COLLISION=0),EditorAssetLibrary=library,get_editor_subsystem=lambda cls:sub)
   ctx={'requires_owned_geometry_rebuild':[{'source_node':221}],'rows':[(NS(),component,{'node':221,'source_triangle_count':1})]}
   def destroy(a):
    self.assertIsNone(a.c.mesh,'Mesh must detach before actor destruction')
    destroyed.append(a);return True
   eas=NS(spawn_actor_from_class=spawn,destroy_actor=destroy)
   with patch.object(P.hashlib,'sha256',return_value=NS(hexdigest=lambda:'9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b')),patch.object(H,'read_gltf',return_value=({},b'')),patch.object(G,'triangles',return_value=TRI),patch.object(G,'native_triangles',return_value=[]if bad else TRI):
    if bad:
     with self.assertRaisesRegex(RuntimeError,'differs exact source'):P.stage_exact_owned_geometry(u,ctx,eas)
     self.assertEqual(deleted,[])
    else:
     result=P.stage_exact_owned_geometry(u,ctx,eas);self.assertEqual(result['proof'][0]['native_full_triangles'],1)
     self.assertIs(result['replacements']['originalComponent'],created[0]);self.assertFalse(deleted)
   self.assertIs(component.mesh,original)
   self.assertEqual(original.settings,settings_before)
   self.assertEqual(created[0].settings['enabled'],False)
   self.assertEqual(created[0].settings['fallback_relative_error'],0.)
   self.assertEqual(len(destroyed),1)
 def test_owned_rebuild_does_not_modify_shared_mesh_or_original_component(self):self.exercise()
 def test_wrong_geometry_refuses_detaches_and_quarantines_owned_assets(self):self.exercise(True)
if __name__=='__main__':unittest.main()
