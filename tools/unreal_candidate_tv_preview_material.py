"""Exposure-correct static Editor preview, matching live PC display compensation."""
import json,time,uuid,hashlib

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 assert active_candidate_guard();eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);a=next(a for a in actors if a.get_name()=='full-home_node_131');cs=a.get_components_by_class(u.StaticMeshComponent);assert len(cs)==1;c=cs[0];original=c.get_material(0);assert original.get_path_name()=='/Game/Sub01Home/ImportedScene/full-home/Materials/Material_64.Material_64'
 mel=u.MaterialEditingLibrary;parent=original;chain=[]
 while isinstance(parent,u.MaterialInstance):chain.append(parent);parent=parent.get_editor_property('parent')
 assert parent.get_path_name()=='/InterchangeAssets/gltf/M_Unlit.M_Unlit'
 dest='/Game/Sub01Home/EditorPreview/TV_'+uuid.uuid4().hex;root=u.EditorAssetLibrary.duplicate_asset(parent.get_path_name(),dest+'/M_ExposureCompensated');assert isinstance(root,u.Material)
 node=mel.get_material_property_input_node(root,u.MaterialProperty.MP_EMISSIVE_COLOR);output=str(mel.get_material_property_input_node_output_name(root,u.MaterialProperty.MP_EMISSIVE_COLOR));assert node and output=='UnlitColor'
 inverse=mel.create_material_expression(root,u.MaterialExpressionEyeAdaptationInverse,500,0);one=mel.create_material_expression(root,u.MaterialExpressionConstant,300,200);one.set_editor_property('r',1.)
 import re
 names={re.sub('[^a-z]','',str(v).lower()):str(v)for v in mel.get_material_expression_input_names(inverse)};light=next(names[k]for k in('lightvalue','lightvalueinput')if k in names);alpha=next(names[k]for k in('alpha','alphainput')if k in names)
 assert mel.connect_material_expressions(node,output,inverse,light)and mel.connect_material_expressions(one,'',inverse,alpha)and mel.connect_material_property(inverse,'',u.MaterialProperty.MP_EMISSIVE_COLOR)
 mel.recompile_material(root);newparent=root
 for index,item in enumerate(reversed(chain)):
  new=u.EditorAssetLibrary.duplicate_asset(item.get_path_name(),dest+'/MI_TVPreview_'+str(index));assert isinstance(new,u.MaterialInstanceConstant);mel.set_material_instance_parent(new,newparent);newparent=new
 assert [str(n)for n in mel.get_texture_parameter_names(new)]==[str(n)for n in mel.get_texture_parameter_names(original)]
 for n in mel.get_texture_parameter_names(original):assert mel.get_material_instance_texture_parameter_value(new,n)==mel.get_material_instance_texture_parameter_value(original,n)
 assert u.EditorAssetLibrary.save_directory(dest,only_if_is_dirty=False,recursive=True);expected=json.loads(json.dumps(before));expected[a.get_path_name()]['components'][0]['materials'][0]=new.get_path_name();mapfile=CANDIDATE/'Content/Sub01Home/ActualHome.umap'
 import shutil
 backup=CANDIDATE/'Saved/PrivateMapBackups'/('editor-tv-preview-'+str(time.time_ns()));backup.mkdir(parents=True);shutil.copy2(mapfile,backup/'ActualHome.umap')
 try:
  c.set_material(0,new);assert snapshot(u,eas.get_all_level_actors())==expected and active_candidate_guard();assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
  r={'schema':'sub01.candidate-editor-tv-preview-exposure.v1','saved':True,'original_material':original.get_path_name(),'owned_preview_material':new.get_path_name(),'texture_and_uv_parameters_preserved':True,'only_added_eye_adaptation_inverse_alpha':1.,'actual_game_live_parent_unchanged':True,'runtime_configure_replaces_preview':True,'protected_all_actors_exact_except_tv_material':True,'live_game_changed':False,'backup':str(backup),'map_sha256':hashlib.sha256(mapfile.read_bytes()).hexdigest(),'epoch':time.time()};(CANDIDATE/'private-audit/editor-tv-preview-exposure.json').write_text(json.dumps(r,indent=2)+'\n');return r
 except Exception:
  c.set_material(0,original);assert snapshot(u,eas.get_all_level_actors())==before;assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level();raise
