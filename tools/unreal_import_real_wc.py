"""Install the proven genuine WC and exact shared-batch remainders, Editor only.

Renderer owns execution in a later warm batch. All 4560 authentic faces and
PBR are verified before retiring the two shared originals; vanity and balcony
geometry remain as exact original-material remainders. No activity gates change.
"""
import copy
import hashlib
import json
import re
import shutil
import time
import uuid
from pathlib import Path

from home_asset_audit import read_gltf
from structural_rail_source_patch import world_matrices
from prepare_real_wc_bundle import HOME_SHA, WC_SHA, node_geometry
from unreal_remove_frame_backings import native_triangles, same_triangles
from unreal_import_real_linea140 import verify_materials
from unreal_import_reference_dressing import fingerprint
from unreal_component_collision_state import capture, restore
from unreal_owned_import_cleanup import detach_added

ROOT=Path('/workspace/sub01-home-private/real-compact-wc-source-3dd8c8d5-r2')
PLACED_SHA='ec3df0b92b0734f2705318e7c1c57a58164ef08926c0bde1240af4e4137067c3'
REMAINDERS={166:('e0999dee30f6653f97d3487d8ca6b44acedf0e01033834e72b71ff71c074d070',125,68,300),
            168:('824774adc7d89db316584702cd9e134a344da12d481c7687361492bc11037039',127,69,600)}
LABEL='SUB01_GenuineCompactWC_3dd8c8d5'


def validate_source(root):
    root=Path(root);proof=json.loads((root/'wc-source-proof.json').read_text())
    if (proof.get('schema')!='sub01.real-compact-wc-source.v1' or proof.get('home_sha256')!=HOME_SHA
        or proof.get('model_sha256')!=WC_SHA or proof.get('output_sha256')!=PLACED_SHA
        or not proof.get('ok') or proof.get('issues') or not proof.get('source_collision_proof_complete')
        or not proof.get('complete_binary_and_pbr_unchanged') or proof.get('source_triangles')!=4560
        or proof.get('exact_zero_area_source_faces')!=[] or proof.get('floor_node')!=117
        or proof.get('actual_tile_top_triangle_ids')!=[4,5]
        or not proof.get('foot_vertices_inside_actual_tile_top_triangles')
        or abs(proof.get('positive_area_foot_contact_m2',0)-.08892201250544826)>1e-12):
        raise RuntimeError('Exact actual R2 complete WC collision/support proof required')
    if hashlib.sha256((root/'real-wc.glb').read_bytes()).hexdigest()!=PLACED_SHA:
        raise RuntimeError('Actual proven complete WC bytes differ')
    rows={r['node']:r for r in proof.get('remainders',[])}
    if set(rows)!=set(REMAINDERS):raise RuntimeError('Both exact shared-batch remainders required')
    for node,(sha,mesh,material,count) in REMAINDERS.items():
        row=rows[node];keep=list(range(300))if node==166 else list(range(300,900))
        if (row.get('mesh')!=mesh or row.get('original_material')!=material
            or row.get('retained_triangles')!=count or row.get('retained_triangle_ids')!=keep
            or row.get('removed_triangle_ids')!=[i for i in range(900)if i not in keep]
            or not row.get('retained_corner_attributes_byte_exact') or row.get('glb_sha256')!=sha
            or hashlib.sha256((root/f'remainder-{node}.glb').read_bytes()).hexdigest()!=sha):
            raise RuntimeError('Exact vanity/balcony remainder bytes required '+str(node))
    return proof


def expected_triangles(doc,blob,node):
    rows=node_geometry(doc,blob,node,world_matrices(doc))
    return [[[float(p[0])*100,float(p[2])*100,float(p[1])*100]for p in (row['points'][j]for j in f)]
            for row in rows for f in row['faces']]


def owned_geometry(u,mesh,dest):
    if not mesh or not mesh.get_path_name().startswith(dest+'/'):raise RuntimeError('WC may rebuild only its fresh owned meshes')
    sub=u.get_editor_subsystem(u.StaticMeshEditorSubsystem);settings=sub.get_nanite_settings(mesh)
    for key,value in (('enabled',False),('keep_percent_triangles',1.),('trim_relative_error',0.),('fallback_percent_triangles',1.),('fallback_relative_error',0.)):
        settings.set_editor_property(key,value)
    sub.set_nanite_settings(mesh,settings,True)
    body=mesh.get_editor_property('body_setup')
    if not body:raise RuntimeError('Owned authentic WC/remainder body setup missing')
    body.set_editor_property('collision_trace_flag',u.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    if not u.EditorAssetLibrary.save_loaded_asset(mesh,only_if_is_dirty=False) or sub.get_nanite_settings(mesh).get_editor_property('enabled'):
        raise RuntimeError('Owned full-source non-Nanite mesh rebuild/save failed')


def run(dry_run=True):
    import unreal as u
    proof=validate_source(ROOT);project=Path(u.Paths.project_dir())
    if hashlib.sha256((project/'SourceAssets/full-home.glb').read_bytes()).hexdigest()!=HOME_SHA:raise RuntimeError('Original955 home source changed')
    eas=u.get_editor_subsystem(u.EditorActorSubsystem);original=list(eas.get_all_level_actors());before=fingerprint(u,original)
    hidden={a.get_path_name():bool(a.get_editor_property('hidden'))for a in original}
    if any(a.get_actor_label().startswith(LABEL)for a in original):raise RuntimeError('Genuine WC already installed; inspect receipt')
    floor_actors=[a for a in original if a.get_name()=='full-home_node_117']
    if len(floor_actors)!=1:raise RuntimeError('Actual unchanged bathroom support slab required')
    floor_components=floor_actors[0].get_components_by_class(u.StaticMeshComponent)
    if len(floor_components)!=1:raise RuntimeError('Actual bathroom support component differs')
    floor_component=floor_components[0];floor_mesh=floor_component.get_editor_property('static_mesh')
    if not floor_mesh or floor_mesh.get_path_name()!='/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Mesh_100.Mesh_100' or hidden[floor_actors[0].get_path_name()] or not floor_component.get_editor_property('visible') or floor_component.get_collision_enabled()==u.CollisionEnabled.NO_COLLISION:
        raise RuntimeError('Actual original tile support identity/visibility/collision differs')
    home_doc,home_blob=read_gltf(project/'SourceAssets/full-home.glb')
    if not same_triangles(expected_triangles(home_doc,home_blob,117),native_triangles(u,floor_component)):
        raise RuntimeError('Actual bathroom support slab differs proven source world geometry')
    targets={};states={}
    for node,(_,mesh_id,material_id,_) in REMAINDERS.items():
        actors=[a for a in original if a.get_name()==f'full-home_node_{node}']
        if len(actors)!=1:raise RuntimeError('Exact original WC shared actor required '+str(node))
        actor=actors[0];components=actor.get_components_by_class(u.StaticMeshComponent)
        if len(components)!=1:raise RuntimeError('Exact WC shared component required')
        c=components[0];mesh=c.get_editor_property('static_mesh');material=c.get_material(0)
        if (c.get_name()!='StaticMeshComponent0' or not mesh
            or mesh.get_path_name()!=f'/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Mesh_{mesh_id}.Mesh_{mesh_id}'
            or c.get_num_materials()!=1 or not material
            or material.get_path_name()!=f'/Game/Sub01Home/ImportedScene/full-home/Materials/Material_{material_id}.Material_{material_id}'
            or hidden[actor.get_path_name()] or not c.get_editor_property('visible')):
            raise RuntimeError('Exact original WC binding/visibility differs '+str(node))
        targets[node]=(actor,c,material);states[node]=capture(u,c)
    result={'schema':'sub01.real-compact-wc-native-import.v1','source_proof':proof,'dry_run':dry_run,
            'native_visual_verified':False,'runtime_ready':False,'original_states':{a.get_path_name():before[a.get_path_name()]for a,c,m in targets.values()}}
    if dry_run:return result
    backup=project/'Saved/PrivateMapBackups'/('genuine-wc-'+str(time.time_ns()));backup.mkdir(parents=True)
    shutil.copy2(project/'Content/Sub01Home/ActualHome.umap',backup/'ActualHome.umap')
    for name in ('__ExternalActors__','__ExternalObjects__'):
        folder=project/'Content'/name/'Sub01Home/ActualHome'
        if folder.exists():shutil.copytree(folder,backup/name)
    dest='/Game/Sub01Home/RealCompactWC/V_'+PLACED_SHA[:12]+'/Attempt_'+uuid.uuid4().hex
    added=[];activated=False;audit=project/'private-audit';audit.mkdir(exist_ok=True)
    try:
        manager=u.InterchangeManager.get_interchange_manager_scripted();params=u.ImportAssetParameters();params.set_editor_property('is_automated',True)
        if not manager.import_scene(dest,manager.create_source_data(str(ROOT/'real-wc.glb')),params):raise RuntimeError('Authentic WC scene import refused')
        manager.wait_until_all_tasks_done(False)
        added=[a for a in eas.get_all_level_actors()if a.get_path_name()not in before]
        for a in added:a.set_actor_hidden_in_game(True)
        doc,blob=read_gltf(ROOT/'real-wc.glb');parts=[]
        for node,n in enumerate(doc['nodes']):
            if 'mesh'not in n:continue
            matches=[a for a in added if a.get_actor_label()==n['name']]
            if len(matches)!=1:raise RuntimeError('Authentic WC source part not unique '+n['name'])
            actor=matches[0];components=actor.get_components_by_class(u.StaticMeshComponent)
            if len(components)!=1:raise RuntimeError('Authentic WC part component differs')
            c=components[0];owned_geometry(u,c.get_editor_property('static_mesh'),dest)
            primitives=doc['meshes'][n['mesh']]['primitives']
            if not c.get_editor_property('visible') or c.get_num_materials()!=len(primitives):raise RuntimeError('Complete WC visible material sections required')
            canon=lambda text:re.sub('[^a-z0-9]','',text.lower())
            for slot,primitive in enumerate(primitives):
                material=c.get_material(slot);source_name=doc['materials'][primitive['material']]['name']
                if not material or canon(source_name)not in canon(material.get_name()):raise RuntimeError('Authentic WC part/source material assignment differs')
            expected=expected_triangles(doc,blob,node);actual=native_triangles(u,c)
            if not same_triangles(expected,actual):
                (audit/'wc-native-geometry-refusal.json').write_text(json.dumps({'node':node,'expected':len(expected),'actual':len(actual),'mesh':c.get_editor_property('static_mesh').get_path_name()},indent=2))
                raise RuntimeError('Authentic WC full world triangle geometry differs '+str(node))
            parts.append((actor,c));c.set_collision_profile_name('BlockAll');c.set_collision_enabled(u.CollisionEnabled.QUERY_AND_PHYSICS)
        if len(parts)!=10:raise RuntimeError('Complete authentic ten-part WC required')
        material_proof=verify_materials(u,[c for a,c in parts],doc,dest)
        remainders=[]
        for node,(_,_,_,count)in REMAINDERS.items():
            source=ROOT/f'remainder-{node}.glb';subdest=dest+'/Remainder_'+str(node)
            task=u.AssetImportTask();task.filename=str(source);task.destination_path=subdest;task.automated=True;task.replace_existing=False;task.save=False
            u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
            meshes=[u.EditorAssetLibrary.load_asset(p)for p in u.EditorAssetLibrary.list_assets(subdest,recursive=True,include_folder=False)]
            meshes=[m for m in meshes if isinstance(m,u.StaticMesh)]
            if len(meshes)!=1:raise RuntimeError('One exact preserved shared remainder required')
            mesh=meshes[0];owned_geometry(u,mesh,subdest)
            old,oc,material=targets[node];actor=eas.spawn_actor_from_class(u.StaticMeshActor,u.Vector(0,0,0));added.append(actor)
            c=actor.get_components_by_class(u.StaticMeshComponent)[0];c.set_static_mesh(mesh);c.set_material(0,material)
            actor.set_actor_transform(oc.get_world_transform(),False,True);actor.set_actor_hidden_in_game(True)
            restore(u,c,states[node],force_response_copy=True)
            rd,rb=read_gltf(source);actual=native_triangles(u,c)
            if len(actual)!=count or not same_triangles(expected_triangles(rd,rb,0),actual):raise RuntimeError('Exact vanity/balcony remainder world geometry differs')
            if c.get_material(0)!=material:raise RuntimeError('Original remainder PBR binding differs')
            remainders.append((node,actor,c))
        if fingerprint(u,original)!=before or hidden!={a.get_path_name():bool(a.get_editor_property('hidden'))for a in original}:raise RuntimeError('Import changed protected originals before activation')
        if not u.EditorAssetLibrary.save_directory(dest,only_if_is_dirty=False,recursive=True):raise RuntimeError('Authentic WC owned geometry/PBR asset save failed')
        activated=True
        for node,(actor,c,material)in targets.items():actor.set_actor_hidden_in_game(True);c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
        for node,actor,c in remainders:actor.set_actor_label(LABEL+'_Preserved_'+str(node));actor.set_actor_hidden_in_game(False)
        for index,(actor,c)in enumerate(parts):actor.set_actor_label(LABEL+'_Part_'+str(index));actor.set_actor_hidden_in_game(False)
        allowed=copy.deepcopy(before);wanted_hidden=dict(hidden)
        for actor,c,m in targets.values():allowed[actor.get_path_name()]['components'][0]['collision']=str(u.CollisionEnabled.NO_COLLISION);wanted_hidden[actor.get_path_name()]=True
        if fingerprint(u,original)!=allowed or wanted_hidden!={a.get_path_name():bool(a.get_editor_property('hidden'))for a in original}:raise RuntimeError('WC activation changed protected originals')
        result.update(owned_destination=dest,backup=str(backup),materials=material_proof,full_native_source_triangles=4560,
                      authentic_actors=[a.get_path_name()for a,c in parts],remainders=[{'source_node':n,'actor':a.get_path_name(),'material':c.get_material(0).get_path_name()}for n,a,c in remainders],protected_originals_unchanged=True)
        pending=audit/'real-compact-wc-import.pending.json';pending.write_text(json.dumps(result,indent=2)+'\n')
        if not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Coherent WC/remainders map save failed')
        pending.replace(audit/'real-compact-wc-import.json');return result
    except Exception as error:
        cleanup=detach_added(u,eas,before)
        if activated:
            for node,(actor,c,material)in targets.items():
                if bool(actor.get_editor_property('hidden'))!=hidden[actor.get_path_name()]:actor.set_actor_hidden_in_game(hidden[actor.get_path_name()])
                restore(u,c,states[node])
        rollback_equal=fingerprint(u,original)==before and hidden=={a.get_path_name():bool(a.get_editor_property('hidden'))for a in original}
        (audit/'real-compact-wc-refusal.json').write_text(json.dumps({'error':str(error),'quarantined_destination':dest,'cleanup':cleanup,'rollback_equal':rollback_equal,'backup':str(backup)},indent=2)+'\n')
        if not rollback_equal:raise RuntimeError('WC rollback differs; preserve saved backup and stop mutations')from error
        if activated and not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('WC rollback map save failed')from error
        raise
