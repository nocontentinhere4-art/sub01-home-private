"""Replace only the owned200-triangle remainder with its exact160-triangle union."""
import hashlib,json
from pathlib import Path
from unreal_import_reference_dressing import fingerprint
ROOT=Path('/workspace/sub01-home-private/structural-rails-20261014')
def run():
 import unreal as u
 project=Path(u.Paths.project_dir());source=ROOT/'structural-lamp-union-remainder-only.glb';proof=json.loads((ROOT/'remainder-lamp-union-roundtrip.json').read_text())
 digest=hashlib.sha256(source.read_bytes()).hexdigest()
 if not proof['ok'] or proof['replacement_sha256']!=digest or proof['checks'][0]['triangle_count']!=160:raise RuntimeError('Exact160 union proof missing')
 actors=u.get_editor_subsystem(u.EditorActorSubsystem);level=u.get_editor_subsystem(u.LevelEditorSubsystem);original=list(actors.get_all_level_actors());before=fingerprint(u,original)
 old=[a for a in original if a.get_actor_label().startswith('SUB01_VerifiedRails_') and 'PreservedSource_163_0' in a.get_actor_label()]
 batches=[a for a in original if a.get_name()=='full-home_node_163']
 if len(old)!=1 or len(batches)!=1:raise RuntimeError('Old owned remainder/batch identity differs')
 old_comp=old[0].get_components_by_class(u.StaticMeshComponent)
 if len(old_comp)!=1 or '/StructuralRails/V_d586193fee24/' not in old_comp[0].get_editor_property('static_mesh').get_path_name():raise RuntimeError('Unreviewed previous remainder version')
 material=batches[0].get_components_by_class(u.StaticMeshComponent)[0].get_material(0)
 dest='/Game/Sub01Home/StructuralLampUnion/V_'+digest[:12]
 manager=u.InterchangeManager.get_interchange_manager_scripted();params=u.ImportAssetParameters();params.set_editor_property('is_automated',True);data=manager.create_source_data(str(source))
 if not manager.import_scene(dest,data,params):raise RuntimeError('Union scene import failed')
 manager.wait_until_all_tasks_done(False)
 current=list(actors.get_all_level_actors());added=[a for a in current if a.get_path_name() not in before];comps=[]
 for a in added:
  a.set_actor_label('SUB01_VerifiedLampUnion_'+a.get_actor_label())
  for c in a.get_components_by_class(u.StaticMeshComponent):
   mesh=c.get_editor_property('static_mesh')
   if not mesh or not mesh.get_path_name().startswith(dest+'/'):raise RuntimeError('Unowned union mesh')
   if 'PreservedSource_163_0' not in mesh.get_name():raise RuntimeError('Union contains unrelated mesh')
   body=mesh.get_editor_property('body_setup')
   if not body:raise RuntimeError('Union collision missing')
   body.set_editor_property('collision_trace_flag',u.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
   c.set_material(0,material);c.set_collision_profile_name('BlockAll');c.set_collision_enabled(u.CollisionEnabled.QUERY_AND_PHYSICS);comps.append(c)
 if len(comps)!=1:raise RuntimeError('Union must contain exactlyone component')
 if fingerprint(u,original)!=before:raise RuntimeError('Originalchanged by union import')
 old[0].set_actor_hidden_in_game(True);old_comp[0].set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
 expected=json.loads(json.dumps(before));expected[old[0].get_path_name()]['components'][0]['collision']=str(u.CollisionEnabled.NO_COLLISION)
 if fingerprint(u,original)!=expected:raise RuntimeError('Unexpected mutation replacing own remainder')
 if not u.EditorAssetLibrary.save_directory(dest,only_if_is_dirty=False,recursive=True) or not level.save_current_level():raise RuntimeError('Union save failed')
 report={'source_sha256':proof['source_sha256'],'union_sha256':digest,'roundtrip':proof,'old_owned_remainder_hidden':old[0].get_path_name(),'new_union_component':comps[0].get_path_name(),'old_state_before':before[old[0].get_path_name()],'native_verified':False}
 (project/'private-audit/native-structural-lamp-union.json').write_text(json.dumps(report,indent=2)+'\n');u.log('SUB01_LAMP_UNION_IMPORTED '+digest);return report
