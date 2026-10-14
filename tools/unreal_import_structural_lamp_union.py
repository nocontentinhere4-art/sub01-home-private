"""Replace only the owned200-triangle remainder with its exact160-triangle union."""
import hashlib,json,time
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
 # Existing imported OWNED static mesh; avoid Interchange scene actor UID reuse.
 mesh_path='/Game/Sub01Home/StructuralLampUnion/V_920edd7a573e/structural-lamp-union-remainder-only/StaticMeshes/SUB01_PreservedSource_163_0.SUB01_PreservedSource_163_0'
 mesh=u.load_asset(mesh_path)
 if not mesh:raise SystemExit('Union pending: source-proven owned160 asset unavailable; saved removal preserved')
 from home_asset_audit import read_gltf,IDENTITY,node_matrix
 from structural_rail_source_patch import accessor
 doc,binary=read_gltf(source)
 if node_matrix(doc['nodes'][0])!=IDENTITY:raise RuntimeError('Union requires exact identity source matrix')
 points=accessor(doc,binary,doc['meshes'][0]['primitives'][0]['attributes']['POSITION'])
 expected_bounds=[[(min if side==0 else max)(p[k] for p in points)*100 for k in (0,2,1)] for side in (0,1)]
 actor=actors.spawn_actor_from_class(u.StaticMeshActor,u.Vector(0,0,0),u.Rotator(0,0,0))
 actor.set_actor_label('SUB01_VerifiedLampUnion160_'+digest[:12])
 actor.set_actor_transform(old[0].get_actor_transform(),False,False)
 component=actor.get_component_by_class(u.StaticMeshComponent);component.set_static_mesh(mesh);component.set_material(0,material)
 origin,extent=actor.get_actor_bounds(False);actual_bounds=[[getattr(origin,k)+sign*getattr(extent,k) for k in ('x','y','z')] for sign in (-1,1)]
 if max(abs(a-b) for x,y in zip(actual_bounds,expected_bounds) for a,b in zip(x,y))>.05:raise RuntimeError('Actual native160 mesh bounds differ from source')
 body=mesh.get_editor_property('body_setup')
 if not body:raise RuntimeError('Union collision missing')
 body.set_editor_property('collision_trace_flag',u.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
 component.set_collision_profile_name('BlockAll');component.set_collision_enabled(u.CollisionEnabled.QUERY_AND_PHYSICS);comps=[component]
 imported=fingerprint(u,original)
 if imported!=before:
  diffs={k:{'before':before[k],'actual':v} for k,v in imported.items() if before.get(k)!=v}
  (project/'private-audit/native-union-import-guard-differences.json').write_text(json.dumps(diffs,indent=2)+'\n')
  raise RuntimeError('Originalchanged by owned mesh placement '+json.dumps(diffs))
 old[0].set_actor_hidden_in_game(True);old_comp[0].set_collision_profile_name('NoCollision')
 old_comp[0].set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
 expected=json.loads(json.dumps(before));expected[old[0].get_path_name()]['components'][0]['collision']=str(u.CollisionEnabled.NO_COLLISION);expected[old[0].get_path_name()]['components'][0]['profile']='NoCollision'
 after=fingerprint(u,original)
 if after!=expected:
  diffs={k:{'expected':expected[k],'actual':v} for k,v in after.items() if expected.get(k)!=v}
  (project/'private-audit/native-union-guard-differences.json').write_text(json.dumps(diffs,indent=2)+'\n')
  raise RuntimeError('Unexpected mutation replacing own remainder '+json.dumps(diffs))
 if not u.EditorAssetLibrary.save_loaded_asset(mesh) or not level.save_current_level():raise RuntimeError('Union save failed')
 report={'source_sha256':proof['source_sha256'],'union_sha256':digest,'roundtrip':proof,'old_owned_remainder_hidden':old[0].get_path_name(),'new_union_component':comps[0].get_path_name(),'old_state_before':before[old[0].get_path_name()],'native_verified':False}
 (project/'private-audit/native-structural-lamp-union.json').write_text(json.dumps(report,indent=2)+'\n');u.log('SUB01_LAMP_UNION_IMPORTED '+digest);return report
