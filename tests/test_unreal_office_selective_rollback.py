"""Rollback changes one actor location once; untouched/root poses are never reset."""
import copy,sys,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import unreal_import_real_office_bundle as O
class Component:
 def __init__(self,a):self.a=a;self.mesh='original';self.profile='Custom';self.materials=['material'];self.tags=[];self.visible=True;self.mesh_sets=0
 def get_path_name(self):return self.a.name+'/root'
 def get_editor_property(self,n):return {'static_mesh':self.mesh,'component_tags':self.tags,'visible':self.visible}[n]
 def get_materials(self):return self.materials
 def set_static_mesh(self,m):self.mesh=m;self.profile='BlockAll';self.mesh_sets+=1
 def set_world_transform(self,*a):raise AssertionError('Root component must not receive second world transform')
class Actor:
 def __init__(self,name):self.name=name;self.location=[0.,0.,0.];self.c=Component(self);self.moves=0
 def get_path_name(self):return self.name
 def get_attach_parent_actor(self):return None
 def get_actor_label(self):return self.name
 def get_editor_property(self,n):return {'root_component':self.c,'hidden':False}[n]
 def set_actor_location(self,p,*args):self.location=[p.x,p.y,p.z];self.moves+=1;return True
 def set_actor_transform(self,*a):raise AssertionError('Translation-only rollback must not decompose transform')
def pose(a):return {'translation':a.location[:],'rotation':[0,0,0,1],'scale':[1,1,1]}
def fingerprint(u,actors):
 return {a.name:{'label':a.name,'transform':pose(a),'components':[{'path':a.c.get_path_name(),'mesh':a.c.mesh,'profile':a.c.profile,'transform':pose(a)}]}for a in actors}
class Rollback(unittest.TestCase):
 def test_only_changed_mesh_and_translation_restored_without_device_or_root_setters(self):
  actors=[Actor('book'),Actor('protected_device')];before=copy.deepcopy(fingerprint(None,actors))
  states=[(a,pose(a),a.name,False,[(a.c,pose(a),a.c.mesh,list(a.c.materials),[],True,3,'Custom')])for a in actors]
  actors[0].location=[2,3,4];actors[0].c.mesh='privateclone';actors[0].c.profile='BlockAll'
  forced=[]
  def restore(u,c,state,force_response_copy=False):
   forced.append((c.get_path_name(),force_response_copy));c.profile=state['profile']
  with patch.object(O,'fingerprint',side_effect=fingerprint),patch.object(O,'restore_collision',side_effect=restore):
   O.restore_originals(NS(Vector=lambda x,y,z:NS(x=x,y=y,z=z)),states,before,{a.c.get_path_name():{'profile':'Custom'}for a in actors})
  self.assertEqual(fingerprint(None,actors),before)
  self.assertEqual([a.moves for a in actors],[1,0]);self.assertEqual([a.c.mesh_sets for a in actors],[1,0])
  self.assertEqual(forced,[('book/root',True),('protected_device/root',False)])
if __name__=='__main__':unittest.main()
