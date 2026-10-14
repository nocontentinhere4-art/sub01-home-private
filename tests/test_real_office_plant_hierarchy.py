"""Exact office parent225 is moved once; kitchen220 is never selected."""
import sys,unittest
from pathlib import Path
from types import SimpleNamespace as NS
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from real_office_plant import native_preflight,MESHES
class Actor:
 def __init__(self,node,parent=None):self.node=node;self.parent=parent
 def get_name(self):return 'full-home_node_'+str(self.node)
 def get_attach_parent_actor(self):return self.parent
 def get_components_by_class(self,cls):
  if self.node not in MESHES:return []
  path=f'/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Mesh_{MESHES[self.node]}.Mesh_{MESHES[self.node]}'
  return [NS(get_editor_property=lambda name:NS(get_path_name=lambda:path))]
class Hierarchy(unittest.TestCase):
 def fixture(self,mode):
  root=Actor(225);kitchen=Actor(220);members=[Actor(n,root if mode=='attached'or(mode=='mixed'and n==221)else None)for n in MESHES]
  plan={'members':[{'node':n,'source_triangle_count':1,'old_bounds_ue_m':[[0,0,0],[1,1,1]]}for n in MESHES]}
  surface=lambda u,c:([[0,0,0],[100,100,100]],1)
  close=lambda a,b:max(abs(x-y)for x,y in zip(a,b))<1e-6
  return native_preflight(NS(StaticMeshComponent=object),[kitchen,root,*members],plan,surface,close)
 def test_attached_whole_group_moves_parent225_only(self):self.assertEqual([a.node for a in self.fixture('attached')['move']],[225])
 def test_independent_children_and_empty225_anchor_move_once(self):self.assertEqual([a.node for a in self.fixture('independent')['move']],[225,221,222,223,224])
 def test_mixed_attachment_refuses_double_translation(self):
  with self.assertRaisesRegex(RuntimeError,'Mixed'):self.fixture('mixed')
if __name__=='__main__':unittest.main()
