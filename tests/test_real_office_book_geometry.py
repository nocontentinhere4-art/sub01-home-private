"""All46 whole books verified; only20 private source meshes rebuilt; failed proof cleans up."""
import copy
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import unreal_office_book_geometry as B
import unreal_monitor_support_fix as G
from test_real_office_plant_owned_geometry import Mesh,Settings,Component,TRI

class CompleteBooks(unittest.TestCase):
 def exercise(self,bad=False):
  originals=[Mesh('/Game/Sub01Home/RealBooks/V_611a3d848858/M'+str(i))for i in range(20)]
  books=[]
  for i in range(46):
   c=Component(originals[i%20]);c.get_path_name=lambda i=i:'originalComponent'+str(i)
   books.append((NS(),c,{'id':f'SUB01_RealBook_{i+1:02d}','actual_source_triangle_count':1}))
  created=[];destroyed=[];deleted=[];rebuild=[];queries=[]
  def duplicate(src,dst):m=Mesh(dst+'.'+dst.rsplit('/',1)[-1]);created.append(m);return m
  def spawn(*args):
   a=NS(c=Component(None));a.set_actor_label=lambda x:None;a.set_actor_hidden_in_game=lambda x:None;a.get_component_by_class=lambda x:a.c;return a
  def apply(m,s,changes):m.settings=copy.deepcopy(s.d);rebuild.append(changes)
  sub=NS(get_nanite_settings=lambda m:Settings(m.settings),set_nanite_settings=apply)
  lib=NS(does_directory_exist=lambda d:bool(created)and not deleted,duplicate_asset=duplicate,save_loaded_asset=lambda *a,**k:True,delete_directory=lambda d:deleted.append(d))
  u=NS(StaticMeshEditorSubsystem=object,get_editor_subsystem=lambda x:sub,EditorAssetLibrary=lib,StaticMeshActor=object,StaticMeshComponent=object,Vector=lambda *x:x,CollisionEnabled=NS(NO_COLLISION=0))
  eas=NS(spawn_actor_from_class=spawn,destroy_actor=lambda a:destroyed.append(a))
  def actual(*args):queries.append(1);return []if bad and len(queries)==40 else TRI
  with tempfile.TemporaryDirectory()as td:
   source=Path(td)/'source.glb';source.write_bytes(b'authentic fixture')
   doc={'nodes':[{'name':p['id'],'mesh':0}for a,c,p in books]}
   with patch.object(B,'SOURCE',source),patch.object(B,'SHA',hashlib.sha256(source.read_bytes()).hexdigest()),patch.object(B,'read_gltf',return_value=(doc,b'')),patch.object(G,'triangles',return_value=TRI),patch.object(G,'native_triangles',side_effect=actual):
    if bad:
     with self.assertRaisesRegex(RuntimeError,'full source triangles differ'):B.stage(u,books,eas,True)
     self.assertEqual(len(deleted),1);self.assertEqual(len(destroyed),40)
    else:
     result=B.stage(u,books,eas,True);self.assertEqual(len(result['proof']),46);self.assertEqual(len(result['replacements']),46)
     self.assertEqual(len(created),20);self.assertEqual(len(rebuild),20);self.assertEqual(len(destroyed),46)
     self.assertEqual(len({m.get_path_name()for m in created}),20)
   for i,(a,c,p)in enumerate(books):self.assertIs(c.mesh,originals[i%20])
   self.assertTrue(all(m.settings['enabled']for m in originals))
 def test_complete46_world_proofs_share_only20_owned_rebuilds(self):self.exercise()
 def test_failed_later_book_proof_deletes_private_assets_without_binding_originals(self):self.exercise(True)
if __name__=='__main__':unittest.main()
