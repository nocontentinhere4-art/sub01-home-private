"""Saved lamp proof uses a temporary private full-source copy, never its live component."""
import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import unreal_saved_lamp_source_proof as L
from test_real_office_plant_owned_geometry import Mesh,Settings,Component
class SavedLamp(unittest.TestCase):
 def exercise(self,bad=False):
  original=Mesh('/Game/Sub01Home/RealLamps/Shared.Shared');c=Component(original);created=[];destroyed=[];deleted=[]
  def duplicate(src,dst):m=Mesh(dst+'.Mesh');created.append(m);return m
  def spawn(*args):
   t=NS(c=Component(None));t.set_actor_label=lambda x:None;t.set_actor_hidden_in_game=lambda x:None;t.get_component_by_class=lambda x:t.c;return t
  def apply(m,s,change):m.settings=copy.deepcopy(s.d)
  sub=NS(get_nanite_settings=lambda m:Settings(m.settings),set_nanite_settings=apply)
  lib=NS(does_directory_exist=lambda d:bool(created)and not deleted,duplicate_asset=duplicate,save_loaded_asset=lambda *a,**k:True,delete_directory=lambda d:(deleted.append(d)or True))
  u=NS(StaticMeshEditorSubsystem=object,get_editor_subsystem=lambda x:sub,EditorAssetLibrary=lib,StaticMeshActor=object,StaticMeshComponent=object,Vector=lambda *x:x,CollisionEnabled=NS(NO_COLLISION=0))
  eas=NS(spawn_actor_from_class=spawn,destroy_actor=lambda a:(destroyed.append(a)or True))
  mount={'lamp_source_triangle_count':4 if bad else 3,'old_native_aabb_cm':[[0,0,0],[1,1,1]]}
  surface=lambda u,c:([[0,0,0],[1,1,1]],1 if c.mesh.settings['enabled']else 3)
  close=lambda a,b:all(abs(x-y)<1e-6 for x,y in zip(a,b))
  if bad:
   with self.assertRaisesRegex(RuntimeError,'still differs'):L.prove(u,eas,c,mount,'/Game/Sub01Home/RealEdgeClampLamp/V_test_SavedSourceProof',surface,close)
  else:
   result=L.prove(u,eas,c,mount,'/Game/Sub01Home/RealEdgeClampLamp/V_test_SavedSourceProof',surface,close)
   self.assertEqual(result['native_full_triangles'],3);self.assertTrue(result['temporary_clone_never_activated'])
  self.assertIs(c.mesh,original);self.assertTrue(original.settings['enabled'])
  self.assertEqual(len(created),1);self.assertEqual(len(destroyed),1);self.assertEqual(len(deleted),1)
 def test_temporary_full_source_pass_cleans_copy_and_preserves_live_saved_lamp(self):self.exercise()
 def test_still_incomplete_source_fails_and_cleans_copy(self):self.exercise(True)
if __name__=='__main__':unittest.main()
