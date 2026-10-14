"""Guarded replacement of exact batched rails; retain every other source triangle."""
import hashlib,json,shutil,time,struct
from pathlib import Path
from unreal_import_reference_dressing import fingerprint
SOURCE_SHA='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
ROOT=Path('/workspace/sub01-home-private/structural-rails-20261014')
def run():
 import unreal as u
 project=Path(u.Paths.project_dir());source=ROOT/'structural-stair-rails-byte-preserved.glb'
 proof=json.loads((ROOT/'remainder-byte-roundtrip.json').read_text())
 raw=source.read_bytes();digest=hashlib.sha256(raw).hexdigest()
 json_length=struct.unpack_from('<I',raw,12)[0];glb=json.loads(raw[20:20+json_length]);expected_meshes=sum('mesh' in n for n in glb['nodes'])
 if not proof.get('ok') or proof['replacement_sha256']!=digest or proof['source_sha256']!=SOURCE_SHA:raise RuntimeError('Real byte roundtrip proof missing')
 if hashlib.sha256((project/'SourceAssets/full-home.glb').read_bytes()).hexdigest()!=SOURCE_SHA:raise RuntimeError('Original source changed')
 level=u.get_editor_subsystem(u.LevelEditorSubsystem); actors=u.get_editor_subsystem(u.EditorActorSubsystem)
 if not level.load_level('/Game/Sub01Home/ActualHome'):raise RuntimeError('Map missing')
 original=list(actors.get_all_level_actors());before=fingerprint(u,original)
 targets=[];materials={}
 for index,role in ((162,'oak'),(163,'metal')):
  matches=[a for a in original if a.get_name()=='full-home_node_'+str(index)]
  if len(matches)!=1:raise RuntimeError('Source batch identity ambiguous '+str(index))
  actor=matches[0];components=actor.get_components_by_class(u.StaticMeshComponent)
  if len(components)!=1 or components[0].get_num_materials()!=1:raise RuntimeError('Source batch material layout differs')
  materials[role]=components[0].get_material(0)
  if not materials[role]:raise RuntimeError('Original material missing')
  targets.append(actor)
 if any(a.get_actor_label().startswith('SUB01_VerifiedRails_') for a in original):raise RuntimeError('Replacement already exists')
 hidden={a.get_path_name():bool(a.get_editor_property('hidden')) for a in original}
 backup=project/'Saved/PrivateMapBackups'/('structural-'+str(time.time_ns()));backup.mkdir(parents=True)
 shutil.copy2(project/'Content/Sub01Home/ActualHome.umap',backup/'ActualHome.umap')
 for name in ('__ExternalActors__','__ExternalObjects__'):
  p=project/'Content'/name/'Sub01Home/ActualHome'
  if p.exists():shutil.copytree(p,backup/name)
 dest='/Game/Sub01Home/StructuralRails/V_'+digest[:12]
 manager=u.InterchangeManager.get_interchange_manager_scripted();params=u.ImportAssetParameters();params.set_editor_property('is_automated',True)
 data=manager.create_source_data(str(source))
 if not manager.can_translate_source_data(data,True) or not manager.import_scene(dest,data,params):raise RuntimeError('Official scene import refused')
 manager.wait_until_all_tasks_done(False)
 current=list(actors.get_all_level_actors());added=[a for a in current if a.get_path_name() not in before]
 if fingerprint(u,original)!=before:raise RuntimeError('Import modified original geometry')
 rows=[];remainders=0;grips=0
 for actor in added:
  name=actor.get_actor_label();actor.set_actor_label('SUB01_VerifiedRails_'+name)
  for component in actor.get_components_by_class(u.StaticMeshComponent):
   mesh=component.get_editor_property('static_mesh')
   if not mesh or not mesh.get_path_name().startswith(dest+'/'):raise RuntimeError('Unowned imported mesh')
   key=name+' '+mesh.get_name()
   remainder='PreservedSource_163_0' in key
   oak='ContinuousOakGrip' in key
   if remainder:remainders+=1
   if oak:grips+=1
   for slot in range(component.get_num_materials()):component.set_material(slot,materials['oak' if oak else 'metal'])
   if True:
    body=mesh.get_editor_property('body_setup')
    if not body:raise RuntimeError('New rail collision missing')
    body.set_editor_property('collision_trace_flag',u.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    component.set_collision_profile_name('BlockAll');component.set_collision_enabled(u.CollisionEnabled.QUERY_AND_PHYSICS)
   rows.append({'component':component.get_path_name(),'mesh':mesh.get_path_name(),'remainder':remainder,'material_role':'oak' if oak else 'metal'})
 if remainders!=1 or grips!=2 or len(rows)!=expected_meshes:raise RuntimeError('Incomplete replacement geometry '+str((remainders,grips,len(rows))))
 if fingerprint(u,original)!=before:raise RuntimeError('Original transforms/material/collision changed')
 for actor in targets:
  actor.set_actor_hidden_in_game(True)
  for c in actor.get_components_by_class(u.StaticMeshComponent):c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
 for actor in original:
  expected=True if actor in targets else hidden[actor.get_path_name()]
  if bool(actor.get_editor_property('hidden'))!=expected:raise RuntimeError('Unexpected original visibility change')
 after=fingerprint(u,original)
 expected=json.loads(json.dumps(before))
 for actor in targets:
  for row in expected[actor.get_path_name()]['components']:row['collision']=str(u.CollisionEnabled.NO_COLLISION)
 if after!=expected:raise RuntimeError('Unexpected source mutation')
 if not u.EditorAssetLibrary.save_directory(dest,only_if_is_dirty=False,recursive=True):raise RuntimeError('Owned assets failed save')
 if not level.save_current_level():raise RuntimeError('Map failed save')
 result={'source_sha256':SOURCE_SHA,'replacement_sha256':digest,'strict_remainder_roundtrip':proof,'backup':str(backup),'hidden_originals':[a.get_path_name() for a in targets],'added_components':rows,'original_state_before':before,'original_hidden_before':hidden,'original_fingerprints_unchanged_except_reviewed_visibility_collision':len(before),'runtime_visually_verified':False}
 (project/'private-audit').mkdir(exist_ok=True)
 (project/'private-audit/native-structural-rails-import.json').write_text(json.dumps(result,indent=2)+'\n')
 u.log('SUB01_STRUCTURAL_RAILS_IMPORTED '+json.dumps({'count':len(rows),'digest':digest}))
 return result
