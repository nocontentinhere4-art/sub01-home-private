"""Install four proved photographic plants only in the independent home copy.

Retirement is exact actor/component ownership, never a shared mesh edit. Every
other native actor stays exact, including source furniture, doors and devices.
"""
import copy,hashlib,json,shutil,time
from pathlib import Path
from uuid import uuid4
ROOT=Path('/workspace/sub01-home-private/reference-photo-plant-placement-r1/output')
HOME_SHA='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
OLD_NODES=[*range(211,215),*range(221,225),*range(226,230),*range(231,235)]
SOURCE_SHAS={0:'6664e1f86ca83a7b5e267574d2d555ce17f4203506881082d9140617953b0633',1:'211f9669e1f1c6730bf1dae281ba3b8c13b49a636016d457a774949c4ebccfcd',2:'7fe1534d81742d608f8f43c014a57f480380df0be5257d64a515b1a75c238b12',3:'3250808c4991a8dc25e1dc4664a31c67e0587103027ab40d205086aadb67335d'}

def validate(proof,inventory_bytes,map_sha):
 if(proof.get('schema')!='sub01.actual-candidate-photo-plant-placement.v1'or proof.get('ok')is not True or proof.get('epsilon_m')!=0 or proof.get('ignored_home_pairs')!=0 or proof.get('retired_original_nodes')!=OLD_NODES or proof.get('protected_home_sha256')!=HOME_SHA or proof.get('candidate_map_sha256')!=map_sha or proof.get('inventory_sha256')!=hashlib.sha256(inventory_bytes).hexdigest()):raise RuntimeError('Exact actual saved candidate placement proof required')
 rows=proof.get('plants',[])
 if len(rows)!=4 or {p.get('variant')for p in rows}!={0,1,2,3}:raise RuntimeError('Exactly four distinct authored plant varieties required')
 for p in rows:
  if p.get('source_sha256')!=SOURCE_SHAS[p['variant']]or p.get('unresolved')!=[]:raise RuntimeError('Complete frozen source and no unresolved protected surface crossings required')
 return rows

def validate_placed_source(original,original_blob,placed,placed_blob,variant,position):
 expected=copy.deepcopy(original);roots=list(expected['scenes'][expected.get('scene',0)]['nodes']);index=len(expected['nodes']);expected['nodes'].append({'name':'PPPlacement%d'%variant,'translation':[position[0]/100,position[2]/100,position[1]/100],'children':roots});expected['scenes'][expected.get('scene',0)]['nodes']=[index]
 for mi,m in enumerate(expected.get('materials',[])):m['name']='PP%dM%02d'%(variant,mi)
 for ni,n in enumerate(expected['nodes']):
  if'mesh'in n:n['name']='PP%d_%02d'%(variant,ni);expected['meshes'][n['mesh']]['name']=n['name']
 if placed!=expected or bytes(placed_blob)!=bytes(original_blob):raise RuntimeError('Botanical placement may only translate roots and alias names; complete geometry/UV/image/PBR source must stay exact')

def actual_material_property(material,name,override_flag):
 """Follow actual native MI overrides to the root rendered material."""
 seen=set();m=material
 while m:
  path=m.get_path_name()
  if path in seen:raise RuntimeError('Material parent cycle')
  seen.add(path)
  try:
   overrides=m.get_editor_property('base_property_overrides')
   if overrides.get_editor_property(override_flag):return overrides.get_editor_property(name)
   m=m.get_editor_property('parent')
  except Exception:
   return m.get_editor_property(name)
 raise RuntimeError('Actual rendered material property unavailable')

def apply_owned_alpha_cutoff(u,component,source,destination):
 """Make the rendered owned MASK instance explicitly match authored glTF cutoff.

 Interchange also supplies AlphaCutoff to its body function, but its root native
 clip value is zero. Set only the newly owned MI base override, never the shared
 Interchange material or an original home's material.
 """
 if source.get('alphaMode','OPAQUE')!='MASK':return
 material=component.get_material(0)
 if not isinstance(material,u.MaterialInstanceConstant)or not material.get_path_name().startswith(destination+'/'):raise RuntimeError('Only fresh owned botanical MASK material may receive source clipping override')
 # Fresh Interchange MI update can overwrite its clip override during deferred
 # initialization. Actual owned-alpha probe029 proved independent duplicates
 # preserve both stored and rendered values after update. Copy source params
 # into one new owned MI; the original imported/shared parent remains untouched.
 material=u.EditorAssetLibrary.duplicate_asset(material.get_path_name().split('.',1)[0],destination+'/AlphaCorrect/A_'+uuid4().hex)
 if not isinstance(material,u.MaterialInstanceConstant)or not material.get_path_name().startswith(destination+'/AlphaCorrect/'):raise RuntimeError('Independent owned alpha MI copy refused')
 component.set_material(0,material)
 cutoff=float(source.get('alphaCutoff',.5))
 if not 0<=cutoff<=1:raise RuntimeError('Authored alpha cutoff outside glTF range')
 overrides=material.get_editor_property('base_property_overrides');overrides.set_editor_property('override_opacity_mask_clip_value',True);overrides.set_editor_property('opacity_mask_clip_value',cutoff);material.set_editor_property('base_property_overrides',overrides);u.MaterialEditingLibrary.update_material_instance(material)
 if abs(float(actual_material_property(material,'opacity_mask_clip_value','override_opacity_mask_clip_value'))-cutoff)>1e-5:raise RuntimeError('Owned source alpha cutoff did not apply: '+str({'actual':actual_material_property(material,'opacity_mask_clip_value','override_opacity_mask_clip_value'),'wanted':cutoff,'flag':material.get_editor_property('base_property_overrides').get_editor_property('override_opacity_mask_clip_value'),'stored':material.get_editor_property('base_property_overrides').get_editor_property('opacity_mask_clip_value')}))

def verify_leaf_mode(u,component,source):
 material=component.get_material(0);mode=actual_material_property(material,'blend_mode','override_blend_mode');two=actual_material_property(material,'two_sided','override_two_sided')
 wanted={'OPAQUE':u.BlendMode.BLEND_OPAQUE,'MASK':u.BlendMode.BLEND_MASKED}.get(source.get('alphaMode','OPAQUE'))
 if wanted is None or mode!=wanted or bool(two)!=bool(source.get('doubleSided',False)):raise RuntimeError('Actual botanical opacity/two-sided source mode differs: '+str((source.get('name'),str(mode),str(wanted),bool(two),source.get('doubleSided'))))
 result={'actual_blend_mode':str(mode),'actual_two_sided':bool(two),'source_extensions_retained':source.get('extensions',{}),'advanced_extension_render_acceptance':False}
 if wanted==u.BlendMode.BLEND_MASKED:
  cutoff=float(actual_material_property(material,'opacity_mask_clip_value','override_opacity_mask_clip_value'))
  if abs(cutoff-source.get('alphaCutoff',.5))>1e-5:raise RuntimeError('Actual botanical alpha clipping differs')
  result['actual_alpha_cutoff']=cutoff
 return result

def run(dry_run=True):
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard
 from home_asset_audit import read_gltf
 from unreal_import_reference_entry import snapshot
 from unreal_import_real_wc import expected_triangles,owned_geometry
 from unreal_remove_frame_backings import native_triangles,same_triangles
 from unreal_import_reference_wall_console import positive_triangles
 from unreal_import_real_bathroom_pendant import verify_owned_material
 from unreal_import_reference_bed_finish import audit_original_full_source
 from unreal_owned_import_cleanup import detach_added
 project=Path(u.Paths.project_dir()).resolve();assert active_candidate_guard(project)
 map_path=project/'Content/Sub01Home/ActualHome.umap';inventory_bytes=(project/'private-audit/plant-placement-inventory.json').read_bytes();inventory=json.loads(inventory_bytes);proof=json.loads((ROOT/'placement-proof.json').read_text());rows=validate(proof,inventory_bytes,hashlib.sha256(map_path.read_bytes()).hexdigest())
 home=project/'SourceAssets/full-home.glb';assert hashlib.sha256(home.read_bytes()).hexdigest()==HOME_SHA;hd,hb=read_gltf(home)
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);by={a.get_name():a for a in actors};old=[];audits=[];bindings={};states=[]
 if any(a.get_actor_label().startswith('SUB01PhotoPlant_')for a in actors):raise RuntimeError('Photographic plants already present; inspect saved receipt')
 for node in OLD_NODES:
  a=by.get('full-home_node_'+str(node));cs=a.get_components_by_class(u.StaticMeshComponent)if a else[]
  if len(cs)!=1 or a.get_editor_property('hidden'):raise RuntimeError('Exact original visible plant actor required')
  c=cs[0];record=next((r for r in inventory['components']if r['component']==c.get_path_name()),None)
  if not record or record['mesh']!=c.get_editor_property('static_mesh').get_path_name():raise RuntimeError('Actual photographed plant replacement ownership differs')
  bindings[node]=record['mesh'];old.append((a,c));states.append((a,bool(a.get_editor_property('hidden')),a.is_temporarily_hidden_in_editor(),c,c.get_collision_profile_name(),c.get_collision_enabled()))
 destination='/Game/Sub01Home/PhotoPlants/V_'+hashlib.sha256((ROOT/'placement-proof.json').read_bytes()).hexdigest()[:12]+'/A_'+uuid4().hex
 from real_office_plant import source_plan
 office_plan,_=source_plan(home)
 def audit_sources(preflight):
  for node,(a,c)in zip(OLD_NODES,old):
   expected=expected_triangles(hd,hb,node)
   if node in(221,222,223,224):
    # These exact actors were already moved by the previously saved genuine
    # office transaction. Their private full-source copies are not the old
    # untouched scene transforms; retain that proved rigid placement in audit.
    delta=office_plan['rigid_delta_ue_cm']
    if delta!=[v*100 for v in(-.4,0.,-.0157754111289978)]or not bindings[node].startswith('/Game/Sub01Home/RealOfficePlant/V_9556495fa816_')or not bindings[node].endswith('_FullSource/SourceNode%d.SourceNode%d'%(node,node)):raise RuntimeError('Exact previously proved office plant placement and ownership required')
    expected=[[[p[i]+delta[i]for i in range(3)]for p in t]for t in expected]
   try:audits.append(audit_original_full_source(u,eas,c,expected,node,bindings,destination,preflight))
   except Exception as exc:raise RuntimeError('Exact retiring plant source node%d failed: %s'%(node,str(exc)))from exc
 if dry_run:audit_sources(True)
 result={'schema':'sub01.actual-candidate-photo-plants-native.v1','dry_run':dry_run,'placement_proof_sha256':hashlib.sha256((ROOT/'placement-proof.json').read_bytes()).hexdigest(),'inventory_sha256':hashlib.sha256(inventory_bytes).hexdigest(),'retired_original_nodes':OLD_NODES,'old_source_audits':audits,'native_visual_verified':False,'runtime_contact_accepted':False,'promoted_to_live':False,'advanced_material_extension_render_acceptance':False}
 if dry_run:return result
 backup=project/'Saved/PrivateMapBackups'/('photo-plants-'+str(time.time_ns()));backup.mkdir(parents=True);shutil.copy2(map_path,backup/'ActualHome.umap');parts=[];geometry=[];materials=[];save_attempted=False
 try:
  for row in rows:
   variant=row['variant'];source=ROOT/('placed-photo-plant-%d.glb'%variant)
   if hashlib.sha256(source.read_bytes()).hexdigest()!=row['placed_sha256']:raise RuntimeError('Exact native placed source bytes required')
   doc,blob=read_gltf(source);original_path=Path('/workspace/sub01-home-private/reference-plants-ph-r1/output-r3')/('photo-plant-%d.glb'%variant)
   if hashlib.sha256(original_path.read_bytes()).hexdigest()!=SOURCE_SHAS[variant]:raise RuntimeError('Exact original photographic plant source required')
   original_doc,original_blob=read_gltf(original_path);validate_placed_source(original_doc,original_blob,doc,blob,variant,row['position_cm']);nodes={n['name']for n in doc['nodes']if'mesh'in n};dest=destination+'/Plant'+str(variant)
   manager=u.InterchangeManager.get_interchange_manager_scripted();params=u.ImportAssetParameters();params.set_editor_property('is_automated',True)
   if not manager.import_scene(dest,manager.create_source_data(str(source)),params):raise RuntimeError('Reviewed botanical source import refused')
   manager.wait_until_all_tasks_done(False);added=[a for a in eas.get_all_level_actors()if a.get_path_name()not in before];matches={}
   for a in added:
    a.set_actor_hidden_in_game(True)
    for c in a.get_components_by_class(u.StaticMeshComponent):
     mesh=c.get_editor_property('static_mesh')
     if not mesh or not mesh.get_path_name().startswith(dest+'/'):continue
     for key in{a.get_actor_label(),mesh.get_name()}:
      if key in nodes:matches.setdefault(key,{})[c.get_path_name()]=(a,c)
   for ni,node in enumerate(doc['nodes']):
    if'mesh'not in node:continue
    found=list(matches.get(node['name'],{}).values())
    if len(found)!=1:raise RuntimeError('Exact unique botanical source node binding required')
    a,c=found[0];mesh=c.get_editor_property('static_mesh');owned_geometry(u,mesh,destination);wanted,zero=positive_triangles(expected_triangles(doc,blob,ni));actual=native_triangles(u,c)
    if not same_triangles(wanted,actual,tolerance=.0001):raise RuntimeError('Actual complete native botanical geometry differs '+node['name'])
    primitives=doc['meshes'][node['mesh']]['primitives']
    if len(primitives)!=1 or len(a.get_components_by_class(u.StaticMeshComponent))!=1:raise RuntimeError('Standalone exact source primitive required')
    source_mat=doc['materials'][primitives[0]['material']];pbr=verify_owned_material(u,c,source_mat,destination,source_primitive_verified=True);apply_owned_alpha_cutoff(u,c,source_mat,destination);mode=verify_leaf_mode(u,c,source_mat)
    original_material=original_doc['materials'][primitives[0]['material']];solid='plant pot'in original_material.get('name','').lower();c.set_collision_profile_name('BlockAll'if solid else'NoCollision');c.set_collision_enabled(u.CollisionEnabled.QUERY_AND_PHYSICS if solid else u.CollisionEnabled.NO_COLLISION);c.set_cast_shadow(True);a.set_actor_label('SUB01PhotoPlant_'+node['name']);parts.append((a,c));geometry.append({'node':node['name'],'variant':variant,'positive_triangles':len(actual),'source_exact_zero_indices':zero,'component':c.get_path_name()});materials.append({'source':source_mat['name'],'core_pbr':pbr,'botanical_mode':mode})
  if len(parts)!=18 or sum(p['positive_triangles']for p in geometry)>42128 or snapshot(u,actors)!=before:raise RuntimeError('Complete four source plants and unchanged originals required')
  # Verify inexpensive new-source material/geometry first; every full original
  # retirement audit still completes before any original actor can be hidden.
  audit_sources(False)
  if snapshot(u,actors)!=before:raise RuntimeError('Complete original plant source audits must leave protected world exact')
  if not u.EditorAssetLibrary.save_directory(destination,only_if_is_dirty=False,recursive=True):raise RuntimeError('Owned exact plant assets save refused')
  expected_after=copy.deepcopy(before)
  for a,c in old:
   a.set_actor_hidden_in_game(True);a.set_is_temporarily_hidden_in_editor(True);c.set_collision_profile_name('NoCollision');c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
   r=expected_after[a.get_path_name()];r['hidden']=True;r['editor_hidden']=True;cr=next(x for x in r['components']if x['path']==c.get_path_name());cr['profile']='NoCollision';cr['collision']=str(u.CollisionEnabled.NO_COLLISION)
  for a,c in parts:a.set_actor_hidden_in_game(False)
  if snapshot(u,actors)!=expected_after:raise RuntimeError('Only exact sixteen old plant components may retire')
  result.update(owned_destination=destination,backup=str(backup),parts=[{'actor':a.get_path_name(),'component':c.get_path_name()}for a,c in parts],geometry=geometry,materials=materials,protected_other_actors_exact=True,plant_physics='Actual ceramic pot surfaces BlockAll; foliage/soil NoCollision; physical-contact readiness remains unverified')
  assert active_candidate_guard(project);pending=project/'private-audit/reference-photo-plants-native.pending.json';pending.write_text(json.dumps(result,indent=2));save_attempted=True
  if not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Candidate photographic plant map save refused')
  result['saved']=True;pending.write_text(json.dumps(result,indent=2));pending.replace(project/'private-audit/reference-photo-plants-native.json');return result
 except Exception:
  for a,h,eh,c,profile,collision in states:a.set_actor_hidden_in_game(h);a.set_is_temporarily_hidden_in_editor(eh);c.set_collision_profile_name(profile);c.set_collision_enabled(collision)
  detach_added(u,eas,before)
  if snapshot(u,list(eas.get_all_level_actors()))!=before:raise RuntimeError('Botanical rollback must restore the complete candidate snapshot')
  if save_attempted and not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Candidate botanical rollback save refused')
  raise
