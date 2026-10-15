"""Actual verify_materials regression for UE's normal-compression sRGB clamp."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from unreal_import_real_linea140 import verify_materials
DEST='/Game/Sub01Home/RealKitchen/V_test'
class Texture:
 def __init__(self,name):self.name=name;self.state={'srgb':False,'compression_settings':'normal'};self.calls=[]
 def get_path_name(self):return DEST+'/'+self.name
 def get_editor_property(self,k):return self.state[k]
 def set_editor_property(self,k,v):
  self.calls.append(k)
  self.state[k]=False if k=='srgb'and v and self.state['compression_settings']=='normal'else v
class Mat:
 def get_name(self):return 'TestMaterial'
 def get_path_name(self):return DEST+'/TestMaterial'
class Roles(unittest.TestCase):
 def test_verified_roles_survive_realistic_normal_compression_clamp(self):
  tex={p:Texture(p)for p in ('BaseColorTexture','MetallicRoughnessTexture','NormalTexture')}
  mat=Mat()
  mel=NS(get_vector_parameter_names=lambda m:['BaseColorFactor','EmissiveFactor'],get_scalar_parameter_names=lambda m:['MetallicFactor','RoughnessFactor','NormalScale'],get_texture_parameter_names=lambda m:list(tex),get_material_instance_vector_parameter_value=lambda m,n:NS(r=1.,g=1.,b=1.,a=1.)if n=='BaseColorFactor'else NS(r=0.,g=0.,b=0.,a=1.),get_material_instance_scalar_parameter_value=lambda m,n:{'MetallicFactor':0.,'RoughnessFactor':.7,'NormalScale':.2}[n],get_material_instance_texture_parameter_value=lambda m,n:tex[n])
  u=NS(MaterialEditingLibrary=mel,MaterialInstanceConstant=Mat,TextureCompressionSettings=NS(TC_DEFAULT='default',TC_MASKS='masks',TC_NORMALMAP='normal'))
  source={'name':'TestMaterial','normalTexture':{'index':2,'scale':.2},'pbrMetallicRoughness':{'baseColorTexture':{'index':0},'metallicRoughnessTexture':{'index':1},'metallicFactor':0.,'roughnessFactor':.7}}
  rows=verify_materials(u,[NS(get_materials=lambda:[mat])],{'materials':[source]},DEST)
  self.assertTrue(tex['BaseColorTexture'].state['srgb'])
  self.assertEqual(tex['BaseColorTexture'].state['compression_settings'],'default')
  self.assertFalse(tex['NormalTexture'].state['srgb']);self.assertFalse(tex['MetallicRoughnessTexture'].state['srgb'])
  self.assertEqual(len(rows[0]['textures']),3)
  self.assertTrue(all(t.calls==['compression_settings','srgb']for t in tex.values()))
if __name__=='__main__':unittest.main()
