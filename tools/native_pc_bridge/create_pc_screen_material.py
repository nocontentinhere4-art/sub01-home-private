"""Rebuild only the actual PC material, with live-canvas UV/exposure correction.

Run inside the authorized Runpod UE editor. Does not alter scene actors/lights.
"""
import re
import unreal as u
path='/Game/Sub01Home/Devices';name='M_Sub01LivePC'
material=u.load_asset(path+'/'+name)
if material is None:
    material=u.AssetToolsHelpers.get_asset_tools().create_asset(name,path,u.Material,u.MaterialFactoryNew())
if material is None:raise RuntimeError('Cannot create the actual PC material')
edit=u.MaterialEditingLibrary
# This asset is owned by this helper; rebuilding makes repeated runs idempotent.
edit.delete_all_material_expressions(material)
material.set_editor_property('shading_model',u.MaterialShadingModel.MSM_UNLIT)
material.set_editor_property('two_sided',True)
def node(kind,x,y):return edit.create_material_expression(material,kind,x,y)
def connect(a,out,b,pin):
    names=[str(n) for n in edit.get_material_expression_input_names(b)]
    key=lambda value:re.sub('[^a-z0-9]','',str(value).lower())
    choices=[n for n in names if key(n)==key(pin)]
    if not choices and len(names)==1:choices=[names[0]]
    if not choices and key(pin)=='uvs':choices=[n for n in names if key(n) in ('coordinates','uv','uvs')]
    if not choices:raise RuntimeError('PC input pin unresolved: '+str(pin)+' actual='+str(names))
    actual=choices[0]
    if not edit.connect_material_expressions(a,out,b,actual):raise RuntimeError('PC material connection failed: '+str(pin)+' resolved='+str(actual)+' actual='+str(names))

uv=node(u.MaterialExpressionTextureCoordinate,-850,0)
u_mask=node(u.MaterialExpressionComponentMask,-650,-80);u_mask.set_editor_property('r',True);u_mask.set_editor_property('g',False)
v_mask=node(u.MaterialExpressionComponentMask,-650,100);v_mask.set_editor_property('r',False);v_mask.set_editor_property('g',True)
v_flip=node(u.MaterialExpressionOneMinus,-480,100)
uv_fixed=node(u.MaterialExpressionAppendVector,-310,0)
connect(uv,'',u_mask,'Input');connect(uv,'',v_mask,'Input');connect(v_mask,'',v_flip,'Input')
connect(u_mask,'',uv_fixed,'A');connect(v_flip,'',uv_fixed,'B')
texture=node(u.MaterialExpressionTextureSampleParameter2D,-120,0)
texture.set_editor_property('parameter_name','PCFrame')
texture.set_editor_property('texture',u.load_asset('/Engine/EngineResources/WhiteSquareTexture.WhiteSquareTexture'))
connect(uv_fixed,'',texture,'UVs')
inverse=node(u.MaterialExpressionEyeAdaptationInverse,160,0)
full=node(u.MaterialExpressionConstant,-70,200);full.set_editor_property('r',1.0)
names=list(edit.get_material_expression_input_names(inverse))
normalized={re.sub('[^a-z]','',str(n).lower()):str(n) for n in names}
light=next((normalized[n] for n in ('lightvalue','lightvalueinput') if n in normalized),None)
alpha=next((normalized[n] for n in ('alpha','alphainput') if n in normalized),None)
if light is None or alpha is None:raise RuntimeError('Unexpected official eye-adaptation inputs: '+str(names))
connect(texture,'RGB',inverse,light);connect(full,'',inverse,alpha)
if not edit.connect_material_property(inverse,'',u.MaterialProperty.MP_EMISSIVE_COLOR):raise RuntimeError('PC emissive connection failed')
edit.recompile_material(material)
if not u.EditorAssetLibrary.save_loaded_asset(material):raise RuntimeError('PC material save failed')
print('SUB01_REAL_PC_MATERIAL_READY='+material.get_path_name()+' UV=u,1-v EyeAdaptationInverse=1 nodes='+str(edit.get_num_material_expressions(material)))
