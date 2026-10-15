"""Read exact rendered kitchen objects and their original source ownership."""
import hashlib,json,time,os

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 from unreal_extend_private_entry import world_bounds
 from home_asset_audit import read_gltf
 assert active_candidate_guard();eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);doc,_=read_gltf(CANDIDATE/'SourceAssets/full-home.glb');rows=[]
 for a in actors:
  for c in a.get_components_by_class(u.StaticMeshComponent):
   mesh=c.get_editor_property('static_mesh')
   if not mesh:continue
   rendered=not a.get_editor_property('hidden')and c.get_editor_property('visible')and not c.get_editor_property('hidden_in_game')
   if not rendered:continue
   b=world_bounds(u,c)
   if not(b['max'][2]>89 and b['min'][2]<180 and b['min'][0]<-50 and b['min'][1]<-310 and b['max'][1]>-390):continue
   item={'actor':a.get_path_name(),'name':a.get_name(),'label':a.get_actor_label(),'component':c.get_path_name(),'mesh':mesh.get_path_name(),'bounds_cm':b,'snapshot':before[a.get_path_name()]}
   if a.get_name().startswith('full-home_node_'):
    n=int(a.get_name().rsplit('_',1)[1]);node=doc['nodes'][n];m=doc['meshes'][node['mesh']];item['original_source']={'node':n,'name':node.get('name'),'mesh_index':node['mesh'],'materials':[doc['materials'][p['material']]['name']for p in m['primitives']],'source_triangles':sum(doc['accessors'][p['indices']]['count']//3 for p in m['primitives'])}
   rows.append(item)
 assert snapshot(u,eas.get_all_level_actors())==before;mapsha=hashlib.sha256((CANDIDATE/'Content/Sub01Home/ActualHome.umap').read_bytes()).hexdigest();r={'schema':'sub01.actual-kitchen-detail-inventory.v1','read_only':True,'world_unchanged':True,'editor_pid':os.getpid(),'candidate_map_sha256':mapsha,'components':rows,'epoch':time.time()};(CANDIDATE/'private-audit/kitchen-detail-inventory.json').write_text(json.dumps(r,indent=2)+'\n');return {'read_only':True,'world_unchanged':True,'components':len(rows),'report':str(CANDIDATE/'private-audit/kitchen-detail-inventory.json')}
