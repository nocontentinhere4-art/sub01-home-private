"""Hide source-proven old cube books and owned generated decor; preserve real models."""
import hashlib,json,time,shutil
from pathlib import Path
from home_asset_audit import read_gltf
from structural_rail_source_patch import accessor,transformed,world_matrices
from unreal_import_reference_dressing import fingerprint
SHA='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
def loft_cube_nodes(source):
 if hashlib.sha256(source.read_bytes()).hexdigest()!=SHA:raise RuntimeError('Original source differs')
 doc,binary=read_gltf(source);matrices=world_matrices(doc);found=[]
 for i,node in enumerate(doc['nodes']):
  if 'mesh' not in node:continue
  prims=doc['meshes'][node['mesh']]['primitives']
  if len(prims)!=1:continue
  meta=doc['accessors'][prims[0]['attributes']['POSITION']]
  if 'min' not in meta or 'max' not in meta:continue
  corners=[transformed(matrices[i],(x,y,z)) for x in (meta['min'][0],meta['max'][0]) for y in (meta['min'][1],meta['max'][1]) for z in (meta['min'][2],meta['max'][2])]
  low=[min(v[k] for v in corners) for k in range(3)];high=[max(v[k] for v in corners) for k in range(3)];dims=[high[k]-low[k] for k in range(3)];centre=[(high[k]+low[k])/2 for k in range(3)]
  step=round((centre[0]+3.3)/.054)
  if 0<=step<5 and abs(centre[0]-(-3.3+.054*step))<.0003 and abs(centre[2]-1)<.0003 and abs(low[1]-3.035)<.0003 and .0347<=dims[0]<=.0553 and .1597<=dims[1]<=.2803 and abs(dims[2]-.14)<.0003:found.append({'node':i,'name':node.get('name'),'source_bounds':[low,high],'step':step})
 if len(found)!=5 or {r['step'] for r in found}!=set(range(5)) or {r['node'] for r in found}!=set(range(112,117)):raise RuntimeError('Exact five loft cube books not found '+str(found))
 return found

def run():
 import unreal as u
 from unreal_import_real_shelf_books import resolve_unique
 project=Path(u.Paths.project_dir());rows=loft_cube_nodes(project/'SourceAssets/full-home.glb')
 actors=u.get_editor_subsystem(u.EditorActorSubsystem);level=u.get_editor_subsystem(u.LevelEditorSubsystem);original=list(actors.get_all_level_actors());before=fingerprint(u,original)
 dressing=json.loads((project/'reference-dressing-import.json').read_text())
 if dressing['source_sha256']!='d21ed8de356b81fdb3f029a2c05aa930422cc354cce95f9d9b8d108ebadbcf89':raise RuntimeError('Unreviewed generated decor version')
 paths={p.rsplit('.',1)[0] for p in dressing['added_mesh_components']}
 targets=[a for a in original if a.get_path_name() in paths]
 if not paths or len(targets)!=len(paths):raise RuntimeError('Owned generated decor exact receipt actors differ')
 for a in targets:
  if not a.get_actor_label().startswith('SUB01_ReferenceDressing_'):raise RuntimeError('Generated ownership label differs')
 for row in rows:
  found=[a for a in original if a.get_name()=='full-home_node_'+str(row['node'])]
  if len(found)!=1:raise RuntimeError('Loft cube actor ambiguous')
  targets.append(found[0])
 manifest=json.loads(Path('/workspace/sub01-home-private/out/real-books-complete/original-hide-manifest.json').read_text())
 for entry in manifest['originals']:targets.append(resolve_unique(u,original,entry)[0])
 lamp_manifest=json.loads(Path('/workspace/sub01-home-private/out/real-lamps/original-hide-manifest.json').read_text())
 for entry in lamp_manifest['entries']:
  found=[a for a in original if a.get_name()==entry['ue_actor_name']]
  if len(found)!=1 or not found[0].get_editor_property('hidden'):raise RuntimeError('Retired lamp not uniquely already hidden')
  targets.append(found[0])
 # Parent-reviewed standalone generated cup, rug layers and canvases; not the bath sign.
 doc,_=read_gltf(project/'SourceAssets/full-home.glb')
 for index in (274,61,62,110,111,108,109):
  node=doc['nodes'][index]
  if 'mesh' not in node:raise RuntimeError('Reviewed standalone decor node lacks mesh')
  if sum(n.get('mesh')==node['mesh'] for n in doc['nodes'])!=1:raise RuntimeError('Generated decor mesh shared with protected geometry')
  found=[a for a in original if a.get_name()=='full-home_node_'+str(index)]
  if len(found)!=1 or (node.get('name') and found[0].get_actor_label()!=node['name']):raise RuntimeError('Generated decor exact identity differs '+str(index))
  targets.append(found[0])
 if len({a.get_path_name() for a in targets})!=len(targets):raise RuntimeError('Removal scopes overlap')
 backup=project/'Saved/PrivateMapBackups'/('remove-generated-'+str(time.time_ns()));backup.mkdir(parents=True);shutil.copy2(project/'Content/Sub01Home/ActualHome.umap',backup/'ActualHome.umap')
 expected=json.loads(json.dumps(before));hidden_before={a.get_path_name():bool(a.get_editor_property('hidden')) for a in targets}
 for a in targets:
  a.set_actor_hidden_in_game(True)
  for c in a.get_components_by_class(u.StaticMeshComponent):c.set_collision_profile_name('NoCollision');c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
  for component, c in zip(sorted(a.get_components_by_class(u.StaticMeshComponent),key=lambda item:item.get_path_name()),expected[a.get_path_name()]['components']):
   if component.get_collision_enabled()!=u.CollisionEnabled.NO_COLLISION or str(component.get_collision_profile_name())!='NoCollision':raise RuntimeError('Explicit NoCollision did not apply')
   c['collision']=str(component.get_collision_enabled());c['profile']=str(component.get_collision_profile_name())
 # Deferred component registration can reset unrelated owned book collision profiles.
 # Restore their exact pre-operation collision state, then retain the full strict guard.
 target_paths={a.get_path_name() for a in targets}
 for a in original:
  if a.get_path_name() in target_paths:continue
  prior={c['path']:c for c in before[a.get_path_name()]['components']}
  for component in a.get_components_by_class(u.StaticMeshComponent):
   old=prior[component.get_path_name()]
   if str(component.get_collision_enabled())!=old['collision'] or str(component.get_collision_profile_name())!=old['profile']:
    component.set_collision_profile_name(old['profile'])
    enum_name=old['collision'].split('CollisionEnabled.',1)[1].split(':',1)[0].split('>',1)[0]
    component.set_collision_enabled(getattr(u.CollisionEnabled,enum_name))
 current=fingerprint(u,original)
 if current!=expected:
  (project/'private-audit/generated-removal-differences.json').write_text(json.dumps({k:{'expected':expected[k],'actual':current[k]} for k in expected if expected[k]!=current[k]},indent=2))
  raise RuntimeError('Unexpected transform/material/mesh change removing generated decor')
 if not all(a.get_editor_property('hidden') for a in targets):raise RuntimeError('Generated geometry not hidden')
 if not level.save_current_level():raise RuntimeError('Removal map failed save')
 result={'source_sha256':SHA,'loft_cube_source_proof':rows,'removed_actor_paths':[a.get_path_name() for a in targets],'old_state_before':{a.get_path_name():before[a.get_path_name()] for a in targets},'hidden_before':hidden_before,'backup':str(backup),'approved_stairs_chair_real_models_unchanged':True}
 (project/'private-audit/rejected-generated-decor-hidden.json').write_text(json.dumps(result,indent=2)+'\n');u.log('SUB01_REJECTED_GENERATED_DECOR_HIDDEN '+str(len(targets)));return result
