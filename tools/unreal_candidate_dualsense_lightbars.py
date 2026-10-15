"""User correction: genuine controller emission restricted to real touchpad sidebars."""
import json,time,uuid,copy,hashlib,shutil

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 assert active_candidate_guard();audit=CANDIDATE/'private-audit';r=json.loads((audit/'genuine-dualsense-native-assets.json').read_text());assembly=json.loads((audit/'genuine-gaming-static-assembly.json').read_text());row=next(p for p in r['parts']if p['material_name']!='button_trans');original=u.load_asset(row['pbr']['pbr'][0]['actual_material']);mel=u.MaterialEditingLibrary;parent=original;chain=[]
 while isinstance(parent,u.MaterialInstance):chain.append(parent);parent=parent.get_editor_property('parent')
 assert isinstance(parent,u.Material);dest='/Game/Sub01Home/RealDualSense/CorrectLightbars_'+uuid.uuid4().hex;root=u.EditorAssetLibrary.duplicate_asset(parent.get_path_name(),dest+'/M_OnlyTouchpadBars');assert isinstance(root,u.Material);node=mel.get_material_property_input_node(root,u.MaterialProperty.MP_EMISSIVE_COLOR);output=str(mel.get_material_property_input_node_output_name(root,u.MaterialProperty.MP_EMISSIVE_COLOR));assert node
 uv=mel.create_material_expression(root,u.MaterialExpressionTextureCoordinate,-400,400);uv.set_editor_property('coordinate_index',0);item=u.CustomInput();item.set_editor_property('input_name','UV');mask=mel.create_material_expression(root,u.MaterialExpressionCustom,0,400);mask.set_editor_property('inputs',[item]);mask.set_editor_property('output_type',u.CustomMaterialOutputType.CMOT_FLOAT1);mask.set_editor_property('description','Only two measured original-emission touchpad side strips');mask.set_editor_property('code','float2 p=UV*4096.0; float L=step(970.0,p.x)*step(p.x,1070.0)*step(3270.0,p.y)*step(p.y,3630.0); float R=step(3680.0,p.x)*step(p.x,3780.0)*step(3350.0,p.y)*step(p.y,3710.0); return saturate(L+R);');mult=mel.create_material_expression(root,u.MaterialExpressionMultiply,400,100);assert mel.connect_material_expressions(uv,'',mask,'UV')and mel.connect_material_expressions(node,output,mult,'A')and mel.connect_material_expressions(mask,'',mult,'B')and mel.connect_material_property(mult,'',u.MaterialProperty.MP_EMISSIVE_COLOR);mel.recompile_material(root)
 newparent=root
 for i,source in enumerate(reversed(chain)):
  new=u.EditorAssetLibrary.duplicate_asset(source.get_path_name(),dest+'/MI_Lightbars_'+str(i));assert isinstance(new,u.MaterialInstanceConstant);mel.set_material_instance_parent(new,newparent);newparent=new
 # Same original texture sampling/normal/roughness/color: only emission gating/strength.
 for name in mel.get_texture_parameter_names(original):assert mel.get_material_instance_texture_parameter_value(new,name)==mel.get_material_instance_texture_parameter_value(original,name)
 scalars={str(n):mel.get_material_instance_scalar_parameter_value(original,n)for n in mel.get_scalar_parameter_names(original)}
 strength=[n for n in scalars if 'emissive'in n.lower()and'strength'in n.lower()];assert len(strength)==1;mel.set_material_instance_scalar_parameter_value(new,strength[0],.5)
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);expected=copy.deepcopy(before);by={a.get_path_name():a for a in actors};changed=[]
 for p in assembly['parts']:
  if not p['role'].startswith('dualsense-')or p['material']!=original.get_path_name():continue
  a=by[p['actor']];cs=a.get_components_by_class(u.StaticMeshComponent);assert len(cs)==1 and cs[0].get_material(0)==original;changed.append((a,cs[0]));expected[a.get_path_name()]['components'][0]['materials'][0]=new.get_path_name()
 assert len(changed)==2;backup=CANDIDATE/'Saved/PrivateMapBackups'/('dualsense-lightbars-'+str(time.time_ns()));backup.mkdir(parents=True);shutil.copy2(CANDIDATE/'Content/Sub01Home/ActualHome.umap',backup/'ActualHome.umap')
 try:
  assert u.EditorAssetLibrary.save_directory(dest,only_if_is_dirty=False,recursive=True)
  for a,c in changed:c.set_material(0,new)
  assert snapshot(u,actors)==expected and active_candidate_guard();assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level();result={'schema':'sub01.genuine-dualsense-touchpad-lightbars-only.v1','saved':True,'original_material':original.get_path_name(),'owned_corrected_material':new.get_path_name(),'texture_files_and_source_geometry_unchanged':True,'uv0_pixel_rois_4096':[[970,1070,3270,3630],[3680,3780,3350,3710]],'emissive_strength':.5,'changed_actor_paths':[a.get_path_name()for a,c in changed],'only_material_bindings_changed':True,'backup':str(backup),'game_changed':False,'epoch':time.time()};(audit/'genuine-dualsense-lightbars-only.json').write_text(json.dumps(result,indent=2)+'\n');return result
 except Exception:
  for a,c in changed:c.set_material(0,original)
  assert snapshot(u,actors)==before;raise
