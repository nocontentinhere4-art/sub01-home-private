"""Import the exact three-part real pendant and independent switched bathroom light.

Sole Editor owner, ActualHome already loaded. Source/PBR/full native triangles
are checked before activation. Original actors remain exact; no seat/privacy or
activity gates change. Native illumination/contact/ON-OFF acceptance is separate.
"""
import hashlib
import json
import shutil
import copy
import struct
import time
import uuid
from pathlib import Path

SHA='c953ce7625525ce501f0bfc05eadd108a55754c6288159c3f4457ea7e4277b6e'
HOME_SHA='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
PREFIX='SUB01_RealBathroomPendant_'
ROLES={'Glass':'modern_ceiling_lamp_01_glass','Metal':'modern_ceiling_lamp_01','Globe':'modern_ceiling_globe'}
BULB=[-260.05779787898064,155.12141708284616,550.7088584303856]


def validate(source):
    from home_asset_audit import read_gltf
    source=Path(source);proof=json.loads(source.with_suffix('.json').read_text())
    if (hashlib.sha256(source.read_bytes()).hexdigest()!=SHA or proof.get('glb_sha256')!=SHA
            or proof.get('home_sha256')!=HOME_SHA or proof.get('native_material_parts')!=3
            or not proof.get('split_world_triangle_corners_and_uvs_exact')
            or proof.get('original_polygons')!=5602 or proof.get('uniform_scale')!=1.
            or proof.get('new_cable_length_m')!=.03 or proof.get('bulb_ue_cm')!=BULB):
        raise RuntimeError('Frozen genuine complete three-part source proof required')
    doc,blob=read_gltf(source)
    if len(doc.get('nodes',[]))!=3 or {n.get('name') for n in doc['nodes']}!={PREFIX+r for r in ROLES}:
        raise RuntimeError('Exact original three material role nodes required')
    for n in doc['nodes']:
        primitives=doc['meshes'][n['mesh']]['primitives']
        if len(primitives)!=1 or doc['materials'][primitives[0]['material']]['name']!=ROLES[n['name'][len(PREFIX):]]:
            raise RuntimeError('Actual source role/material binding differs')
    return proof,doc,blob


def prepare_native_input(source, target):
    """Normalize only mesh identities; retain every binary/PBR/transform byte."""
    from home_asset_audit import read_gltf
    proof,doc,blob=validate(source);prepared=copy.deepcopy(doc)
    for node in prepared['nodes']:
        prepared['meshes'][node['mesh']]['name']=node['name']
    target=Path(target)
    if target.exists():raise RuntimeError('Prepared owned input must be new')
    target.parent.mkdir(parents=True,exist_ok=True)
    text=json.dumps(prepared,separators=(',',':')).encode();text+=b' '*(-len(text)%4)
    payload=bytes(blob);payload+=b'\0'*(-len(payload)%4)
    target.write_bytes(struct.pack('<III',0x46546c67,2,28+len(text)+len(payload))+struct.pack('<II',len(text),0x4e4f534a)+text+struct.pack('<II',len(payload),0x004e4942)+payload)
    actual,binary=read_gltf(target);restored=copy.deepcopy(actual)
    for index,mesh in enumerate(doc['meshes']):restored['meshes'][index]['name']=mesh['name']
    if restored!=doc or bytes(binary)!=bytes(blob):raise RuntimeError('Names-only input changed source payload')
    return {'schema':'sub01.bathroom-pendant-owned-import-identities.v1','source_sha256':SHA,
            'prepared_input_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
            'source_document_except_mesh_names_and_all_binary_exact':True,
            'native_mesh_names':[m['name'] for m in actual['meshes']]}


def source_slot_binding(c,source,dest):
    """Bind preserved glTF material slot, never a truncated UE asset basename."""
    mesh=c.get_editor_property('static_mesh');slots=list(mesh.get_editor_property('static_materials'))
    mat=c.get_material(0)
    if (len(slots)!=1 or str(slots[0].get_editor_property('material_slot_name'))!=source['name']
            or not mat or slots[0].get_editor_property('material_interface')!=mat
            or not mat.get_path_name().startswith(dest+'/')):
        raise RuntimeError('Exact original material slot and assigned owned instance required')
    return {source['name']:mat.get_path_name()}


def verify_owned_material(u,c,source,dest):
    from unreal_import_real_linea140 import verify_materials
    binding=source_slot_binding(c,source,dest)
    mat=c.get_material(0);mel=u.MaterialEditingLibrary
    if not mat or not mat.get_path_name().startswith(dest+'/'):
        raise RuntimeError('Only newly owned imported fixture materials may be checked')
    factor=mel.get_material_instance_vector_parameter_value(mat,'EmissiveFactor')
    wanted=source.get('emissiveFactor',[0.,0.,0.])
    if max(abs(a-b) for a,b in zip((factor.r,factor.g,factor.b),wanted))>1e-5:
        raise RuntimeError('Actual authentic source emission differs')
    # Existing rigorous PBR verifier requires an unlit material. Scope this
    # temporary normalization to the NEW hidden owned material, then restore
    # exact authored emission even when another PBR check refuses the import.
    if any(wanted):mel.set_material_instance_vector_parameter_value(mat,'EmissiveFactor',u.LinearColor(0,0,0,0))
    try:
        result=verify_materials(u,[c],{'materials':[source]},dest,material_bindings=binding)
    finally:
        if any(wanted):mel.set_material_instance_vector_parameter_value(mat,'EmissiveFactor',factor)
    restored=mel.get_material_instance_vector_parameter_value(mat,'EmissiveFactor')
    if (restored.r,restored.g,restored.b,restored.a)!=(factor.r,factor.g,factor.b,factor.a):
        raise RuntimeError('New owned source emission was not restored exactly')
    return {'pbr':result,'authored_emission_rgb':wanted,'authored_emission_restored_exact':True}


def run(source,dry_run=True):
    import unreal as u
    from unreal_import_reference_dressing import fingerprint
    from unreal_import_real_wc import owned_geometry,expected_triangles
    from unreal_remove_frame_backings import native_triangles,same_triangles
    from unreal_owned_import_cleanup import detach_added
    source=Path(source);proof,doc,blob=validate(source);project=Path(u.Paths.project_dir())
    if hashlib.sha256((project/'SourceAssets/full-home.glb').read_bytes()).hexdigest()!=HOME_SHA:
        raise RuntimeError('Actual original home source differs')
    world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if not world or world.get_path_name().split('.',1)[0]!='/Game/Sub01Home/ActualHome':
        raise RuntimeError('Sole Editor owner must have actual private map loaded')
    eas=u.get_editor_subsystem(u.EditorActorSubsystem);original=list(eas.get_all_level_actors());before=fingerprint(u,original)
    hidden={a.get_path_name():bool(a.get_editor_property('hidden')) for a in original}
    if any(a.get_actor_label().startswith(PREFIX) or a.get_actor_label()=='SUB01_AuthoredLight_BathroomCeiling' for a in original):
        raise RuntimeError('Bathroom fixture/light already exists; inspect receipt')
    result={'schema':'sub01.real-bathroom-pendant-native-import.v1','source':proof,'dry_run':dry_run,
            'native_visual_verified':False,'runtime_ready':False,'activity_gates_changed':False}
    if dry_run:return result
    backup=project/'Saved/PrivateMapBackups'/('real-bathroom-pendant-'+str(time.time_ns()));backup.mkdir(parents=True)
    shutil.copy2(project/'Content/Sub01Home/ActualHome.umap',backup/'ActualHome.umap')
    for name in ('__ExternalActors__','__ExternalObjects__'):
        folder=project/'Content'/name/'Sub01Home/ActualHome'
        if folder.exists():shutil.copytree(folder,backup/name)
    dest='/Game/Sub01Home/RealBathroomPendant/V_'+SHA[:12]+'/Attempt_'+uuid.uuid4().hex
    audit=project/'private-audit';audit.mkdir(exist_ok=True)
    try:
        manager=u.InterchangeManager.get_interchange_manager_scripted();params=u.ImportAssetParameters();params.set_editor_property('is_automated',True)
        prepared=project/'Saved/PrivateImportInputs'/('bathroom-pendant-'+uuid.uuid4().hex+'.glb')
        input_proof=prepare_native_input(source,prepared)
        if not manager.import_scene(dest,manager.create_source_data(str(prepared)),params):raise RuntimeError('Owned fixture import refused')
        manager.wait_until_all_tasks_done(False)
        added=[a for a in eas.get_all_level_actors() if a.get_path_name() not in before]
        for a in added:a.set_actor_hidden_in_game(True)
        parts=[];materials=[];total=0;by_mesh={};inventory=[]
        for actor in added:
            record={'actor':actor.get_path_name(),'label':actor.get_actor_label(),'components':[],'material_bindings':[]}
            for component in actor.get_components_by_class(u.StaticMeshComponent):
                mesh=component.get_editor_property('static_mesh')
                record['components'].append(mesh.get_path_name() if mesh else None)
                record['material_bindings'].append({'materials':[m.get_path_name() if m else None for m in component.get_materials()],
                    'source_slots':[str(v.get_editor_property('material_slot_name')) for v in mesh.get_editor_property('static_materials')] if mesh else []})
                if mesh and mesh.get_path_name().startswith(dest+'/'):
                    by_mesh.setdefault(mesh.get_name(),[]).append(actor)
            inventory.append(record)
        (audit/'real-bathroom-pendant-import-inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
        for ni,n in enumerate(doc['nodes']):
            matches=by_mesh.get(n['name'],[])
            if len(matches)!=1:raise RuntimeError('Unique exact source role actor required')
            actor=matches[0];actor.set_actor_label(n['name']);actor.set_editor_property('tags',list(actor.get_editor_property('tags'))+[u.Name(n['name'])]);cs=actor.get_components_by_class(u.StaticMeshComponent)
            if len(cs)!=1 or cs[0].get_num_materials()!=1:raise RuntimeError('Actual source component/material differs')
            c=cs[0];owned_geometry(u,c.get_editor_property('static_mesh'),dest)
            actual=native_triangles(u,c);expected=expected_triangles(doc,blob,ni)
            if not same_triangles(expected,actual,tolerance=.0001):raise RuntimeError('Full actual native source triangle corners differ')
            total+=len(actual);role=n['name'][len(PREFIX):]
            source_material=doc['materials'][doc['meshes'][n['mesh']]['primitives'][0]['material']]
            source_slot_binding(c,source_material,dest)
            materials.append(verify_owned_material(u,c,source_material,dest))
            c.set_collision_profile_name('BlockAll');c.set_collision_enabled(u.CollisionEnabled.QUERY_AND_PHYSICS)
            # Opal emitter and surrounding glass transmit light; the metal
            # canopy/cable retain their physical shadows independently.
            c.set_cast_shadow(role=='Metal')
            parts.append((actor,c,role))
        if total!=5602 or len(parts)!=3:raise RuntimeError('Complete authentic three-part fixture required')
        light=eas.spawn_actor_from_class(u.PointLight,u.Vector(*BULB));light.set_actor_label('SUB01_AuthoredLight_BathroomCeiling')
        light.set_editor_property('tags',list(light.get_editor_property('tags'))+[u.Name('SUB01_AuthoredLight_BathroomCeiling')])
        light.set_actor_hidden_in_game(True);lc=light.get_component_by_class(u.PointLightComponent)
        lc.set_mobility(u.ComponentMobility.MOVABLE);lc.set_editor_property('intensity_units',u.LightUnits.CANDELAS)
        lc.set_editor_property('use_inverse_squared_falloff',True);lc.set_editor_property('attenuation_radius',400.)
        lc.set_editor_property('use_temperature',True);lc.set_editor_property('temperature',3000.)
        lc.set_editor_property('cast_shadows',True);lc.set_intensity(5.5)
        if fingerprint(u,original)!=before or hidden!={a.get_path_name():bool(a.get_editor_property('hidden')) for a in original}:
            raise RuntimeError('Fixture import changed protected originals')
        if not u.EditorAssetLibrary.save_directory(dest,only_if_is_dirty=False,recursive=True):raise RuntimeError('Owned authentic fixture asset save failed')
        for actor,c,role in parts:actor.set_actor_hidden_in_game(False)
        light.set_actor_hidden_in_game(False)
        result.update(owned_destination=dest,backup=str(backup),prepared_input=input_proof,complete_native_triangles=total,
                      actors=[{'actor':a.get_path_name(),'component':c.get_path_name(),'role':r} for a,c,r in parts],materials=materials,
                      light_actor=light.get_path_name(),bulb_ue_cm=BULB,intensity_cd=5.5,temperature_kelvin=3000.,protected_originals_unchanged=True)
        pending=audit/'real-bathroom-pendant-import.pending.json';pending.write_text(json.dumps(result,indent=2)+'\n')
        if not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Coherent fixture/light map save failed')
        pending.replace(audit/'real-bathroom-pendant-import.json');return result
    except Exception as error:
        cleanup=detach_added(u,eas,before)
        equal=fingerprint(u,original)==before and hidden=={a.get_path_name():bool(a.get_editor_property('hidden')) for a in original}
        (audit/'real-bathroom-pendant-refusal.json').write_text(json.dumps({'error':str(error),'cleanup':cleanup,'protected_originals_unchanged':equal,'quarantined_destination':dest,'backup':str(backup)},indent=2)+'\n')
        if not equal:raise RuntimeError('Protected originals differ; preserve map backup and stop') from error
        if not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Fixture rollback map save failed') from error
        raise
