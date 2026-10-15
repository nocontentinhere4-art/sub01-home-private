"""Custom profile survives mesh defaults; hidden channel responses remain exact."""
import sys,unittest
from pathlib import Path
from types import SimpleNamespace as NS
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import unreal_component_collision_state as C
class Component:
 def __init__(self):self.profile='Custom';self.object_type=0;self.enabled=3;self.responses=[2]*32;self.responses[27]=1;self.overlap=True
 def get_collision_profile_name(self):return self.profile
 def get_collision_object_type(self):return self.object_type
 def get_collision_enabled(self):return self.enabled
 def get_collision_response_to_channel(self,c):return self.responses[c]
 def set_collision_object_type(self,x):self.object_type=x;self.profile='Custom'
 def set_collision_enabled(self,x):self.enabled=x;self.profile='BlockAll'
 def set_collision_response_to_channel(self,c,r):self.responses[c]=r;self.profile='Custom'
 def get_editor_property(self,n):
  if n=='generate_overlap_events':return self.overlap
  if n=='body_instance':return NS(get_editor_property=lambda name:self.profile,set_editor_property=lambda name,value:setattr(self,'profile',value))
  raise AssertionError(n)
 def set_editor_property(self,n,v):
  if n=='generate_overlap_events':self.overlap=v
  else:raise AssertionError('No entire body instance assignment allowed')
class Preserve(unittest.TestCase):
 def test_mesh_default_does_not_replace_custom_hidden_channel_state(self):
  u=NS(CollisionChannel=NS(cast=lambda i:i));c=Component();state=C.capture(u,c)
  c.profile='BlockAll';c.responses=[2]*32;c.enabled=0;c.object_type=1;c.overlap=False
  C.restore(u,c,state)
  self.assertEqual(C.capture(u,c),state);self.assertEqual(c.responses[27],1);self.assertEqual(len(state['responses']),32)
 def test_detached_body_wrapper_cannot_pretend_original_profile_restored(self):
  u=NS(CollisionChannel=NS(cast=lambda i:i));c=Component();state=C.capture(u,c);c.profile='BlockAll'
  old=c.get_editor_property
  c.get_editor_property=lambda n:NS(get_editor_property=lambda key:c.profile,set_editor_property=lambda *a:None)if n=='body_instance'else old(n)
  with self.assertRaisesRegex(RuntimeError,'restore failed'):C.restore(u,c,state)
if __name__=='__main__':unittest.main()
