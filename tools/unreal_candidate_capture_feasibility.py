"""Actual exposed native/Python API inventory, no capture or scene mutation."""
import json,time,hashlib

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 assert active_candidate_guard();eas=u.get_editor_subsystem(u.EditorActorSubsystem);before=snapshot(u,eas.get_all_level_actors());m=CANDIDATE/'Content/Sub01Home/ActualHome.umap';old=hashlib.sha256(m.read_bytes()).hexdigest()
 names=['Sub01HomeHandsInstance','SkeletalMesh','SkeletalMeshComponent','GeometryScriptLibrary_StaticMeshFunctions','GeometryScriptLibrary_SceneUtilityFunctions','GeometryScriptLibrary_MeshBoneWeightFunctions','GeometryScriptBoneWeight','Modules','ModuleManager']
 result={}
 for name in names:
  cls=getattr(u,name,None)
  if cls is None:result[name]={'available':False};continue
  keys=[k for k in dir(cls)if any(w in k.lower()for w in ['skin','vertex','vertic','bone_weight','pose','foot_witness','hand_witness','seat','cpu','copy_mesh','load_module'])]
  result[name]={'available':True,'methods':{k:str(getattr(cls,k).__doc__)[:1800]for k in keys}}
 assert active_candidate_guard()and snapshot(u,eas.get_all_level_actors())==before and hashlib.sha256(m.read_bytes()).hexdigest()==old
 p=CANDIDATE/'private-audit'/('wholeclip-native-capture-feasibility-'+str(time.time_ns())+'.json');p.write_text(json.dumps({'schema':'sub01.actual-native-capture-feasibility.v1','api':result,'world_unchanged':True,'map_unchanged':True,'input_or_capture_delivered':False,'all_contact_readiness':False},indent=2)+'\n');return {'report':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'world_unchanged':True}
