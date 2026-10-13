import copy,unittest,math
from tools.home_sky_contract import validate_recipe,validate_sky_pair,validate_night,validate_radiance_bounds
class SkyContractTest(unittest.TestCase):
 def setUp(self):
  self.base=dict(finished=True,direct=False,indirect=True,surface_albedo=False,source_sha256='source',atlas_sha256='atlas',samples=512,threads=4,seed=0,adaptive_sampling=False,denoising=False,receivers=103,width=1378,height=1379,mode='day')
  self.sky=dict(self.base,direct=True,indirect=False,world_only=True,emissive_materials_disabled=True,world_rgb=[.76,.84,1.0],world_strength=.12)
 def test_matching_components(self):
  self.assertEqual(validate_sky_pair(self.base,self.sky)['receivers'],103)
  validate_recipe(self.base,'source','atlas',512,4,0)
  validate_night(self.base,dict(self.base,mode='night'))
 def test_geometry_and_sampling_mismatch_rejected(self):
  for key,value in [('source_sha256','other'),('atlas_sha256','other'),('samples',128),('threads',8),('seed',1),('width',2048),('receivers',102)]:
   with self.subTest(key=key):
    sky=dict(self.sky,**{key:value})
    with self.assertRaises(ValueError):validate_sky_pair(self.base,sky)
 def test_unfinished_or_duplicate_indirect_rejected(self):
  for patch in [{'finished':False},{'indirect':True},{'direct':False},{'surface_albedo':True},{'world_only':False},{'emissive_materials_disabled':False},{'world_strength':.5}]:
   with self.subTest(patch=patch):
    with self.assertRaises(ValueError):validate_sky_pair(self.base,dict(self.sky,**patch))
 def test_bad_reference_and_night_rejected(self):
  with self.assertRaises(ValueError):validate_recipe(dict(self.base,finished=False),'source','atlas',512,4,0)
  with self.assertRaises(ValueError):validate_recipe(self.base,'wrong','atlas',512,4,0)
  with self.assertRaises(ValueError):validate_night(self.base,dict(self.base,mode='day'))
  with self.assertRaises(ValueError):validate_night(self.base,dict(self.base,mode='night',seed=3))
 def test_nonfinite_negative_radiance_rejected(self):
  validate_radiance_bounds(0,3.0,True)
  for minimum,maximum,finite in [(-.001,1,True),(0,float('inf'),True),(float('nan'),1,True),(0,1,False)]:
   with self.subTest(bounds=(minimum,maximum,finite)):
    with self.assertRaises(ValueError):validate_radiance_bounds(minimum,maximum,finite)
 def physical(self,base):
  record=copy.deepcopy(base)
  record.update(recipe='home-physical-source-v1',diagnostic_only=False,
    written_receiver_ids=[str(i) for i in range(103)],device='METAL',gpu_names=['test GPU'],
    source_recipe_sha256='a'*64,preparation_recipe_sha256='b'*64,
    material_grades_sha256='c'*64,geometry_proof_sha256='d'*64,
    preparation=dict(recipe='home-physical-source-v1',mode='day',hdr_strength=.4225,
      hemisphere_intensity=.22,runtime_hdr_rotation_y=-math.pi/2,
      cycles_hdr_lookup_rotation_z=math.pi/2,source_runtime_photometric_intensities_changed=False,
      import_energy_factor=683,hdr_sha256='e'*64,
      fixture_emission_policy='positive finite lampEmission metadata only, night only',
      world_only=False,lights=[{'type':'SUN'}],enabled_fixtures=[]))
  return record
 def test_physical_pair_and_night(self):
  day=self.physical(self.base);sky=self.physical(self.sky)
  sky['preparation'].update(world_only=True,lights=[])
  validate_sky_pair(day,sky)
  night=copy.deepcopy(day);night['mode']='night'
  night['preparation'].update(mode='night',hdr_strength=0,enabled_fixtures=[{'lampEmission':.6}])
  validate_night(day,night)
 def test_subset_or_mismatched_physics_cannot_install(self):
  day=self.physical(self.base);sky=self.physical(self.sky)
  sky['preparation'].update(world_only=True,lights=[])
  changes=[('diagnostic_only',True),('written_receiver_ids',['67']),
    ('preparation_recipe_sha256','f'*64),('device','CPU'),('gpu_names',[])]
  for key,value in changes:
   with self.subTest(key=key):
    bad=copy.deepcopy(sky);bad[key]=value
    with self.assertRaises(ValueError):validate_sky_pair(day,bad)
  for key,value in [('hdr_sha256','f'*64),('runtime_hdr_rotation_y',0),
    ('lights',[{'type':'SUN'}]),('enabled_fixtures',[{'lampEmission':.6}])]:
   with self.subTest(preparation=key):
    bad=copy.deepcopy(sky);bad['preparation'][key]=value
    with self.assertRaises(ValueError):validate_sky_pair(day,bad)
if __name__=='__main__':unittest.main()
