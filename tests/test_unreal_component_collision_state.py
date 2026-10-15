"""No whole-body assignment, enum-count guesses or false hidden-channel proof."""
import copy,sys,unittest
from pathlib import Path
from types import SimpleNamespace as NS
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import unreal_component_collision_state as C
class Responses:
 def __init__(self,values):self.values=values
 def copy(self):return Responses(self.values[:])
 def get_editor_property(self,name):raise AttributeError('Hidden container not exposed')
class Component:
 def __init__(self):self.profile='Custom';self.object_type=0;self.enabled=3;self.responses=Responses([2]*64);self.responses.values[57]=1;self.overlap=True;self.use_default=False
 def get_collision_profile_name(self):return self.profile
 def get_collision_object_type(self):return self.object_type
 def get_collision_enabled(self):return self.enabled
 def get_collision_response_to_channel(self,c):return self.responses.values[c]
 def set_collision_object_type(self,x):self.object_type=x;self.profile='Custom'
 def set_collision_enabled(self,x):self.enabled=x;self.profile='BlockAll'
 def set_collision_response_to_channel(self,c,r):self.responses.values[c]=r;self.profile='Custom'
 def get_editor_property(self,n):
  if n=='generate_overlap_events':return self.overlap
  if n=='use_default_collision':return self.use_default
  if n=='body_instance':return NS(get_editor_property=lambda name:self.responses if name=='collision_responses'else self.profile,set_editor_property=self.body_set)
  raise AssertionError(n)
 def body_set(self,name,value):
  if name=='collision_profile_name':self.profile=value
  elif name=='collision_responses':self.responses=value
  else:raise AssertionError(name)
 def set_editor_property(self,n,v):
  if n=='generate_overlap_events':self.overlap=v
  elif n=='use_default_collision':self.use_default=v
  else:raise AssertionError('No entire body instance assignment allowed')
def api():return NS(CollisionChannel=NS(ECC_WORLD_STATIC=0,ECC_PAWN=2))
class Preserve(unittest.TestCase):
 def test_data_copy_preserves_unexposed_channel57_without_claiming_it_queried(self):
  u=api();c=Component();state=C.capture(u,c)
  c.profile='BlockAll';c.responses=Responses([2]*64);c.enabled=0;c.object_type=1;c.overlap=False
  C.restore(u,c,state)
  self.assertEqual(C.signature(C.capture(u,c)),C.signature(state));self.assertEqual(c.responses.values[57],1)
  self.assertIsNone(state['hidden_container_export']);self.assertEqual(len(state['visible_responses']),2)
 def test_detached_body_wrapper_cannot_pretend_original_profile_restored(self):
  u=api();c=Component();state=C.capture(u,c);c.profile='BlockAll';old=c.get_editor_property
  c.get_editor_property=lambda n:NS(get_editor_property=lambda key:c.responses if key=='collision_responses'else c.profile,set_editor_property=lambda *a:None)if n=='body_instance'else old(n)
  with self.assertRaisesRegex(RuntimeError,'restore failed'):C.restore(u,c,state)
if __name__=='__main__':unittest.main()
