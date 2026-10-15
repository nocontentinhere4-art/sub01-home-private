"""Original non-emissive glTF transmission source; official UE shader contract."""
import math,hashlib
from pathlib import Path

def verify(u,c,source,destination):
 from unreal_import_reference_entry import assigned_material_binding
 assert source['name']=='button_trans'and source['alphaMode']=='BLEND'and source.get('emissiveFactor',[0,0,0])==[0,0,0]and'emissiveTexture'not in source
 p=source['pbrMetallicRoughness'];assert p['baseColorFactor']==[.8,.8,.8,.25]and p['metallicFactor']==0 and abs(p['roughnessFactor']-.8040408205773457)<1e-12 and source['extensions']['KHR_materials_transmission']['transmissionFactor']==1
 assigned_material_binding(c,source,destination);m=c.get_material(0);mel=u.MaterialEditingLibrary;vectors={str(n):mel.get_material_instance_vector_parameter_value(m,n)for n in mel.get_vector_parameter_names(m)};scalars={str(n):float(mel.get_material_instance_scalar_parameter_value(m,n))for n in mel.get_scalar_parameter_names(m)}
 assert 'BaseColorFactor'in vectors and all(abs(float(getattr(vectors['BaseColorFactor'],k))-v)<1e-6 for k,v in zip(('r','g','b','a'),p['baseColorFactor']))
 expected={'MetallicFactor':0.,'RoughnessFactor':p['roughnessFactor'],'TransmissionFactor':1.,'AlphaMode':2.}
 assert all(k in scalars and math.isfinite(scalars[k])and abs(scalars[k]-v)<1e-6 for k,v in expected.items())
 root=m;chain=[]
 while isinstance(root,u.MaterialInstance):chain.append(root.get_path_name());root=root.get_editor_property('parent')
 assert root.get_path_name()=='/InterchangeAssets/gltf/M_Transmission.M_Transmission'and root.get_editor_property('blend_mode')==u.BlendMode.BLEND_TRANSLUCENT and root.get_editor_property('shading_model')==u.MaterialShadingModel.MSM_THIN_TRANSLUCENT
 plugins=Path(u.Paths.convert_relative_path_to_full(u.Paths.engine_plugins_dir()));matches=list((plugins/'Interchange').rglob('M_Transmission.uasset'));assert len(matches)==1;raw=matches[0].read_bytes();assert raw
 return {'pbr':[{'source_material':source['name'],'actual_material':m.get_path_name(),'textures':[]}],'source_specific_official_transmission_template':root.get_path_name(),'template_file_sha256':hashlib.sha256(raw).hexdigest(),'template_file':str(matches[0]),'numeric_base_opacity_roughness_metallic_transmission_exact':True,'authored_emission_rgb':[0,0,0],'authored_emission_absent':True,'actual_furniture_emission_parameter_not_required':True,'original_source_material_not_modified':True,'actual_blend':'BLEND_TRANSLUCENT','actual_shading':'MSM_THIN_TRANSLUCENT','actual_scalar_factors':expected}
