"""Read actual owned exterior bindings and projection values; never change scene."""
import json,hashlib
from pathlib import Path

def run():
 import unreal as u
 from unreal_import_reference_dressing import fingerprint
 world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
 if not world or world.get_path_name().split('.',1)[0]!='/Game/Sub01Home/ActualHome':raise RuntimeError('ActualHome already loaded required')
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=fingerprint(u,actors)
 rows=[]
 for a in actors:
  label=a.get_actor_label()
  if label!='SUB01_ActualHistoricalTokyoBackground' and not label.startswith('SUB01_PrivateEntry_'):continue
  row={'actor':a.get_path_name(),'label':label,'components':[]}
  for c in a.get_components_by_class(u.StaticMeshComponent):
   m=c.get_editor_property('static_mesh');entry={'mesh':m.get_path_name()if m else None,'collision':str(c.get_collision_enabled()),'materials':[]}
   for mat in c.get_materials():
    if not mat:continue
    md={'material':mat.get_path_name()}
    if isinstance(mat,u.MaterialInstanceConstant):
     parent=mat.get_editor_property('parent');md['parent']=parent.get_path_name()if parent else None
     md['scalars']={str(n):float(u.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(mat,n))for n in u.MaterialEditingLibrary.get_scalar_parameter_names(mat)}
     md['textures']={}
     for n in u.MaterialEditingLibrary.get_texture_parameter_names(mat):
      tex=u.MaterialEditingLibrary.get_material_instance_texture_parameter_value(mat,n);md['textures'][str(n)]=tex.get_path_name()if tex else None
    entry['materials'].append(md)
   row['components'].append(entry)
  rows.append(row)
 if len([x for x in rows if x['label']=='SUB01_ActualHistoricalTokyoBackground'])!=1:raise RuntimeError('Unique actual exterior panorama required')
 p=Path(u.Paths.project_dir());photo=p/'SourceAssets/TokyoResidential.png'
 result={'schema':'sub01.actual-exterior-readonly.v1','native_changed':False,'read_only':True,'actors':rows,'photo_sha256':hashlib.sha256(photo.read_bytes()).hexdigest()if photo.is_file()else None,'scope':'Actual Editor material parameters and geometry binding only. No human camera/private image, FOV change or projection change.'}
 if fingerprint(u,actors)!=before:raise RuntimeError('Read-only exterior diagnostic changed actors')
 out=p/'private-audit/exterior-actual-readonly.json';out.write_text(json.dumps(result,indent=2)+'\n');return result
