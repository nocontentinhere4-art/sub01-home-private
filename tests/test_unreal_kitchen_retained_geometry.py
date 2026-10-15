"""Private exact sink proof and unchanged source/native cabinet identity distinction."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import unreal_kitchen_retained_geometry as K
import unreal_monitor_support_fix as G
import unreal_import_real_kitchen as I
from prepare_real_kitchen_native_bundle import OLD
from test_real_office_plant_owned_geometry import Mesh,Settings,Component,TRI

class SinkProof(unittest.TestCase):
 def test_source_mesh_index_and_native_asset_name_remain_distinct(self):
  self.assertEqual(OLD[178],('Cabinet_carcass',135))
  self.assertEqual(I.NATIVE_OLD_MESH[178],136)
 def exercise(self,bad=False):
  original=Mesh('/Original.SharedSink');c=Component(original);created=[];destroyed=[];deleted=[]
  a=NS(get_name=lambda:'full-home_node_164',get_components_by_class=lambda cls:[c])
  def duplicate(src,dst):m=Mesh(dst+'.Mesh');created.append(m);return m
  def spawn(*args):
   t=NS(c=Component(None));t.set_actor_label=lambda x:None;t.set_actor_hidden_in_game=lambda x:None;t.get_component_by_class=lambda x:t.c;return t
  def apply(m,s,b):m.settings=copy.deepcopy(s.d)
  sub=NS(get_nanite_settings=lambda m:Settings(m.settings),set_nanite_settings=apply)
  lib=NS(does_directory_exist=lambda d:bool(created)and not deleted,duplicate_asset=duplicate,save_loaded_asset=lambda *a,**k:True,delete_directory=lambda d:deleted.append(d))
  u=NS(StaticMeshEditorSubsystem=object,get_editor_subsystem=lambda x:sub,EditorAssetLibrary=lib,StaticMeshActor=object,StaticMeshComponent=object,Vector=lambda *x:x,CollisionEnabled=NS(NO_COLLISION=0))
  eas=NS(spawn_actor_from_class=spawn,destroy_actor=lambda a:destroyed.append(a))
  with tempfile.TemporaryDirectory()as td:
   source=Path(td)/'source.glb';source.write_bytes(b'source')
   with patch.object(K,'hashlib',NS(sha256=lambda b:NS(hexdigest=lambda:'9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'))),patch.object(K,'read_gltf',return_value=({},b'')),patch.object(G,'triangles',return_value=TRI*2700),patch.object(G,'native_triangles',return_value=TRI*(576 if bad else 2700)):
    if bad:
     with self.assertRaisesRegex(RuntimeError,'every source2700'):K.stage(u,[a],[{'node':164,'component':'originalComponent','source_geometry_verified':False}],source,eas)
     self.assertEqual(len(deleted),1)
    else:
     result=K.stage(u,[a],[{'node':164,'component':'originalComponent','source_geometry_verified':False}],source,eas)
     self.assertEqual(result['proof'][0]['native_full_triangles'],2700)
     self.assertEqual(len(result['replacements']),1)
   self.assertIs(c.mesh,original);self.assertTrue(original.settings['enabled']);self.assertEqual(len(destroyed),1)
 def test_full2700_source_geometry_proved_without_touching_original(self):self.exercise()
 def test_actual576_fallback_cannot_pass_or_bind_original(self):self.exercise(True)
if __name__=='__main__':unittest.main()
