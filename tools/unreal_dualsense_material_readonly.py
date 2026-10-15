"""Read actual owned transmission material after strict refused import."""
import json,time

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_sheer_material_readonly import root_graph
 assert active_candidate_guard();mel=u.MaterialEditingLibrary;rows=[]
 for p in u.EditorAssetLibrary.list_assets('/Game/Sub01Home/RealDualSense',recursive=True,include_folder=False):
  m=u.load_asset(p)
  if not isinstance(m,u.MaterialInstanceConstant):continue
  rows.append({'path':m.get_path_name(),'graph':root_graph(u,m),'vectors':{str(n):[float(getattr(mel.get_material_instance_vector_parameter_value(m,n),k))for k in('r','g','b','a')]for n in mel.get_vector_parameter_names(m)},'scalars':{str(n):float(mel.get_material_instance_scalar_parameter_value(m,n))for n in mel.get_scalar_parameter_names(m)},'textures':{str(n):(lambda t:t.get_path_name()if t else None)(mel.get_material_instance_texture_parameter_value(m,n))for n in mel.get_texture_parameter_names(m)}})
 r={'schema':'sub01.actual-dualsense-glass-readonly.v1','read_only':True,'materials':rows,'epoch':time.time()};(CANDIDATE/'private-audit/dualsense-material-readonly.json').write_text(json.dumps(r,indent=2)+'\n');return {'read_only':True,'materials':len(rows)}
