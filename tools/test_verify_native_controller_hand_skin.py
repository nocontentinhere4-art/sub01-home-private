import copy,math,random,unittest
import verify_native_controller_hand_skin as V

class HandSkinVerifierTests(unittest.TestCase):
 def test_actual_transform_units_and_inverse(self):
  t=V.parse_transform('200,300,5|0,90,0|2,2,2')
  p=V.transform((1,0,0),t);self.assertAlmostEqual(p[0],200);self.assertAlmostEqual(p[1],302);self.assertEqual(p[2],5)
  for a,b in zip(V.inverse_transform(p,t),(1,0,0)):self.assertAlmostEqual(a,b)
  self.assertEqual(V.basis_cm((.1,.2,.3)),(10,30,20))
  with self.assertRaises(ValueError):V.parse_transform('0,0,0|0,0,0|0,1,1')
 def test_bind_identity_requires_weights_not_nearest_joint(self):
  rows=[{'source_id':[0,0,7],'bind_cm':(1,2,3),'weights':{'RightHandIndex3':1}}, {'source_id':[0,0,8],'bind_cm':(1,2,3),'weights':{'RightHandThumb3':1}}]
  native={'globalVertex':90,'bindPositionCm':[1.00001,2,3],'weights':[{'bone':'mixamorig_RightHandThumb3','raw':65535}]}
  match,proof=V.BindLookup(rows).match(native);self.assertEqual(match['source_id'],[0,0,8]);self.assertEqual(proof['equivalent_source_candidates'],[[0,0,8]])
  native['weights'][0]['bone']='RightHandRing3'
  with self.assertRaises(ValueError):V.BindLookup(rows).match(native)
 def test_authored_inverse_bind_and_skin_vertex_are_used(self):
  identity=(1,0,0,0,0,1,0,0,0,0,1,0,.4,0,0,1)
  class Owner:
   nodes=[{'name':'mesh','skin':0,'mesh':0},{'name':'mixamorig:RightHand'}]
   doc={'skins':[{'joints':[1],'inverseBindMatrices':0}],'meshes':[{'primitives':[{'attributes':{'POSITION':1,'JOINTS_0':2,'WEIGHTS_0':3}}]}]}
   def accessor(self,i):return {0:[identity],1:[(.1,.2,.3)],2:[(0,0,0,0)],3:[(1,0,0,0)]}[i]
  class Clip:
   nodes=[{'name':'mixamorig:RightHand'}]
   def animation(self):return None
  class Reader:
   @staticmethod
   def world_pose(*args):return {0:((1,0,0),(0,0,0,1),1)}
  rows,_,_=V.source_vertices(Reader,Owner(),Clip(),4,((0,0,0),(0,0,0,1),(1,1,1)))
  self.assertEqual(rows[0]['bind_cm'],(10,30,20));self.assertEqual(rows[0]['world_cm'],(150,30,20))
  self.assertNotEqual(rows[0]['world_cm'],(100,0,0)) # Joint centre is not the skin.
 def test_actual_triangle_surface_bvh_matches_brute(self):
  rng=random.Random(42);triangles=[tuple(tuple(rng.uniform(-2,2)for _ in range(3))for _ in range(3))for i in range(35)]
  triangles.append(((5,0,0),(5,0,0),(5,0,0)))
  surface=V.Surface(triangles)
  for _ in range(30):
   p=tuple(rng.uniform(-3,3)for _ in range(3));d,_=surface.nearest(p);brute=min(V.distance(p,V.closest_triangle(p,*t))for t in triangles);self.assertAlmostEqual(d,brute,places=12)
 def test_actual4s_identity_and_false_acceptance_required(self):
  asset={'schema':'sub01.native-controller-asset.v1','source_sha256':V.CONTROLLER_SHA,'import_source_sha256':V.NORMALIZED_CONTROLLER_SHA,'physical_assembly':{'mesh':'/Game/Physical.controller','component':'actual.component'}}
  doc={'schema':'sub01.actual-hand-skin-witness.v1','owner_asset':V.OWNER_ASSET,'capture_asset':V.CLIP_ASSET,'capture_time':4,'contact_accepted':False,'activity_ready':False,'native_pid':123,'native_start_ticks':456,'skin':{'invalidInfluences':0,'vertices':[{'globalVertex':1}]},'actual_props':[{'mesh':'/Game/Physical.controller','component':'actual.component'}]}
  V.validate_capture(doc,asset)
  for key,value in [('capture_time',0),('contact_accepted',True),('capture_asset','/Game/Raw')]:
   wrong=copy.deepcopy(doc);wrong[key]=value
   with self.assertRaises(ValueError):V.validate_capture(wrong,asset)
  wrong=copy.deepcopy(doc);wrong['actual_props'][0]['mesh']='/Game/controller_contact'
  with self.assertRaises(ValueError):V.validate_capture(wrong,asset)

if __name__=='__main__':unittest.main()
