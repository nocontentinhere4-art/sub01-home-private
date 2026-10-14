"""Reject stale physical200-triangle native scene before any office staging."""
import hashlib,json,sys,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import unreal_import_real_office_bundle as module

class Mesh:
 def __init__(self,path):self.path=path
 def get_path_name(self):return self.path
class Component:
 def __init__(self,path,mesh,collision,material):self.path=path;self.mesh=Mesh(mesh);self.collision=collision;self.material=material
 def get_path_name(self):return self.path
 def get_editor_property(self,name):return self.mesh if name=='static_mesh'else True
 def get_collision_enabled(self):return self.collision
 def get_collision_profile_name(self):return 'BlockAll'
 def get_num_materials(self):return 1
 def get_material(self,index):return self.material
class Actor:
 def __init__(self,name,label,hidden,component):self.name=name;self.label=label;self.hidden=hidden;self.component=component
 def get_name(self):return self.name
 def get_actor_label(self):return self.label
 def get_path_name(self):return '/actual/'+self.name
 def get_editor_property(self,name):return self.hidden
 def get_components_by_class(self,cls):return [self.component]

class ExactUnion(unittest.TestCase):
 def exercise(self,active200=False,count160=160):
  raw=b'exact-reviewed-160-source';digest=hashlib.sha256(raw).hexdigest();material=Mesh('/Game/Sub01Home/ImportedScene/full-home/Materials/Material_8.Material_8')
  actors=[Actor('full-home_node_'+str(n),'source',True,Component('/old/'+str(n),f'/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Mesh_{n-41}.Mesh_{n-41}',0,material if n==163 else Mesh('/Game/Sub01Home/ImportedScene/full-home/Materials/Material_1.Material_1')))for n in(162,163)]
  actors.append(Actor('union','SUB01_VerifiedLampUnion160_'+digest[:12],False,Component('/union/component','/Game/Sub01Home/StructuralLampUnionMeshOnly/V_'+digest[:12]+'/Mesh',1,material)))
  actors.append(Actor('old200','SUB01_VerifiedRails_SUB01_PreservedSource_163_0',not active200,Component('/old200/component','/Game/Sub01Home/StructuralRails/V_d586193fee24/Mesh',1 if active200 else 0,material)))
  receipt={'source_sha256':'9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b','union_sha256':digest,'roundtrip':{'ok':True,'replacement_sha256':digest,'checks':[{'triangle_count':160}]},'new_union_component':'/union/component','old_owned_remainder_hidden':'/actual/old200'}
  points=[(0.,0.,0.),(100.,0.,0.),(0.,0.,100.)]
  doc={'nodes':[{}],'meshes':[{'primitives':[{'attributes':{'POSITION':0}}]}]}
  u=NS(Paths=NS(project_dir=lambda:'/private/project'),StaticMeshComponent=object,CollisionEnabled=NS(NO_COLLISION=0,QUERY_AND_PHYSICS=1))
  with patch.object(Path,'read_text',return_value=json.dumps(receipt)),patch.object(Path,'read_bytes',return_value=raw),patch.object(module,'surface',return_value=(points,count160)),patch.object(module,'read_gltf',return_value=(doc,b'')),patch('structural_rail_source_patch.accessor',return_value=[(0.,0.,0.),(1.,0.,0.),(0.,1.,0.)]):return module.verify_native_structural_union(u,actors)
 def test_active_old200_refused(self):
  with self.assertRaisesRegex(RuntimeError,'Old200 remainder'):self.exercise(active200=True)
 def test_wrong_union200_refused(self):
  with self.assertRaisesRegex(RuntimeError,'triangle/material'):self.exercise(count160=200)
 def test_exact_active160_and_retired_originals_allowed_readonly(self):
  r=self.exercise();self.assertEqual(r['native_triangles'],160);self.assertEqual(r['mutations'],0)
if __name__=='__main__':unittest.main()
