"""Read only already imported owned cloth materials after a refused PBR check."""
from pathlib import Path
import json

def _property(obj, name):
 try:
  value = obj.get_editor_property(name)
  if hasattr(value, 'get_path_name'): return value.get_path_name()
  if isinstance(value, (bool, int, float, str)) or value is None: return value
  if all(hasattr(value, c) for c in ('r', 'g', 'b', 'a')):
   return [float(getattr(value, c)) for c in ('r', 'g', 'b', 'a')]
  return str(value)
 except Exception as error: return {'unavailable': type(error).__name__}

def root_graph(u, instance):
 current=instance; seen=set(); chain=[]
 while isinstance(current,u.MaterialInstance):
  path=current.get_path_name()
  if path in seen: return {'available':False,'reason':'parent cycle'}
  seen.add(path);chain.append(path);current=current.get_editor_property('parent')
 if not isinstance(current,u.Material):return {'available':False,'reason':'no concrete root'}
 mel=u.MaterialEditingLibrary;inputs={}
 for name in ('MP_BASE_COLOR','MP_EMISSIVE_COLOR','MP_OPACITY','MP_NORMAL','MP_MATERIAL_ATTRIBUTES'):
  prop=getattr(u.MaterialProperty,name,None)
  if prop is None:inputs[name]={'unavailable':'enum absent'};continue
  try:
   node=mel.get_material_property_input_node(current,prop)
   inputs[name]={'node':node.get_path_name()if node else None,'output_name':str(mel.get_material_property_input_node_output_name(current,prop))}
  except Exception as error:inputs[name]={'unavailable':type(error).__name__}
 expressions=[]
 for expression in mel.get_material_expressions(current):
  expressions.append({'path':expression.get_path_name(),'class':expression.get_class().get_name(),
   'properties':{name:_property(expression,name)for name in('parameter_name','constant','r','g','b','a','material_function')}})
 return {'available':True,'root':current.get_path_name(),'instance_chain':chain,
  'blend_mode':_property(current,'blend_mode'),'shading_model':_property(current,'shading_model'),
  'two_sided':_property(current,'two_sided'),'use_material_attributes':_property(current,'use_material_attributes'),
  'property_inputs':inputs,'expressions':expressions,
  'zero_emission_verified':False,'note':'Graph evidence only; material-attribute/function routes require review before a zero-emission claim.'}

def run():
 import unreal as u
 root='/Game/Sub01Home/Sheer/V_b531ac1eaa30';rows=[];mel=u.MaterialEditingLibrary
 for path in u.EditorAssetLibrary.list_assets(root,recursive=True,include_folder=False):
  material=u.EditorAssetLibrary.load_asset(path)
  if not isinstance(material,u.MaterialInstanceConstant):continue
  parent=material.get_editor_property('parent')
  rows.append({'material':material.get_path_name(),'parent':parent.get_path_name()if parent else None,
   'root_graph':root_graph(u,material),
   'vectors':{str(n):[float(getattr(mel.get_material_instance_vector_parameter_value(material,n),c))for c in('r','g','b','a')]for n in mel.get_vector_parameter_names(material)},
   'scalars':{str(n):float(mel.get_material_instance_scalar_parameter_value(material,n))for n in mel.get_scalar_parameter_names(material)},
   'textures':{str(n):(lambda t:t.get_path_name()if t else None)(mel.get_material_instance_texture_parameter_value(material,n))for n in mel.get_texture_parameter_names(material)}})
 p=Path(u.Paths.project_dir()).resolve()/'private-audit/sheer-owned-material-readonly.json';p.write_text(json.dumps({'schema':'sub01.sheer-owned-material-readonly.v1','read_only':True,'world_modified':False,'materials':rows},indent=2));return {'read_only':True,'materials':rows}
