"""Atomic owned source-derived bathroom adjustment; preserves original assets.

No backend profile, privacy box, pawn or runtime configuration is changed here.
Those require the separately compiled optional profile and an actual receipt.
"""
import copy
import hashlib
import json
import shutil
import struct
import time
import uuid
from pathlib import Path

from prepare_frame_backing_remainder import read, elements, SOURCE_SHA
from prepare_bathroom_corridor_widening import NODES, MESHES, MATERIALS
from unreal_import_reference_dressing import fingerprint
from unreal_component_collision_state import capture, restore
from unreal_remove_frame_backings import native_triangles, same_triangles

ROOT=Path('/workspace/sub01-home-private/bathroom-corridor-source-r1')
CONTRACT_SHA='dbe28857c96054836813f5d6c35f14097bd7d118df39e02480a04348cbf44e79'
SHA='5ffac2406e668a327427e60bc75e3ee3ecf13a89381d0312b821277386cb9c91'
PREFIX='/Game/Sub01Home/BathroomCorridor/V_'+SHA[:12]+'/Attempt_'
RECEIPT='bathroom-corridor-native-import.json'


def load_contract(root=ROOT):
    raw=(root/'accepted-source-contract.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=CONTRACT_SHA:
        raise RuntimeError('Exact independently accepted corridor source contract required')
    contract=json.loads(raw)
    if (contract.get('schema')!='sub01.accepted-bathroom-corridor-source-contract.v1'
            or contract.get('source_sha256')!=SOURCE_SHA or contract.get('export_sha256')!=SHA
            or contract.get('original_source_nodes')!=list(NODES)
            or contract.get('owned_geometry_triangles')!=876
            or contract.get('native_imported')is not False):
        raise RuntimeError('Corridor source scope differs')
    for name,row in contract['files'].items():
        if name not in ('bath-corridor.glb','bath-corridor.json','source-clearance-proof.json','independent-corner-bytes.json'):
            raise RuntimeError('Unreviewed corridor source member')
        data=(root/name).read_bytes()
        if len(data)!=row['bytes'] or hashlib.sha256(data).hexdigest()!=row['sha256']:
            raise RuntimeError('Actual proved source artifact changed '+name)
    proof=json.loads((root/'bath-corridor.json').read_text())
    clear=json.loads((root/'source-clearance-proof.json').read_text())
    corners=json.loads((root/'independent-corner-bytes.json').read_text())
    if ([p.get('source_node')for p in proof.get('parts',[])]!=list(NODES)
            or sum(p.get('triangles',0)for p in proof['parts'])!=876
            or clear.get('source_sampled_path_and_sweep_pass')is not True
            or clear.get('continuous_full_source_door_sweep_clear')is not True
            or corners.get('protected_architecture_position_corner_triangles_exact')!=432
            or corners.get('all_UV_normals_other_corner_bytes_exact')is not True):
        raise RuntimeError('Full source/corner/path/door proof unavailable')
    return contract,proof


def source_triangles(raw):
    doc,blob=read(raw);result={}
    for ni,node in zip(NODES,doc['nodes']):
        expected_name='SUB01_BathCorridor_SourceNode_'+str(ni)
        mesh=doc['meshes'][node['mesh']]
        if node.get('name')!=expected_name or mesh.get('name')!=expected_name or any(k in node for k in ('matrix','translation','rotation','scale')):
            raise RuntimeError('Exact identity/world-baked source part required')
        p=mesh['primitives'][0];pos,fmt=elements(doc,blob,p['attributes']['POSITION']);pos=[struct.unpack(fmt,v)for v in pos]
        ids,fmt=elements(doc,blob,p['indices']);ids=[struct.unpack(fmt,v)[0]for v in ids]
        result[ni]=[[[pos[j][0]*100,pos[j][2]*100,pos[j][1]*100]for j in ids[i:i+3]]for i in range(0,len(ids),3)]
    return result


def bounds(triangles):
    points=[p for t in triangles for p in t]
    return [[min(p[a]for p in points)for a in range(3)],
            [max(p[a]for p in points)for a in range(3)]]


def main(u):
    contract,proof=load_contract();project=Path(u.Paths.project_dir());audit=project/'private-audit'
    if (audit/RECEIPT).exists():raise RuntimeError('Existing corridor receipt requires deliberate review; no duplicate import')
    if hashlib.sha256((project/'SourceAssets/full-home.glb').read_bytes()).hexdigest()!=SOURCE_SHA:
        raise RuntimeError('Original immutable source955 differs')
    world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if not world or world.get_path_name()!='/Game/Sub01Home/ActualHome.ActualHome':
        raise RuntimeError('Exact saved ActualHome Editor world required')
    eas=u.get_editor_subsystem(u.EditorActorSubsystem);original=list(eas.get_all_level_actors())
    before=fingerprint(u,original);hidden={a.get_path_name():bool(a.get_editor_property('hidden'))for a in original}
    owners={};preflight=[]
    for ni in NODES:
        found=[a for a in original if a.get_name()=='full-home_node_'+str(ni)]
        if len(found)!=1:raise RuntimeError('Exact original source actor required '+str(ni))
        actor=found[0];cs=actor.get_components_by_class(u.StaticMeshComponent)
        if len(cs)!=1:raise RuntimeError('Exact original source component required '+str(ni))
        c=cs[0];mesh=c.get_editor_property('static_mesh');material=c.get_material(0)
        want_mesh='/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Mesh_'+str(MESHES[ni])+'.Mesh_'+str(MESHES[ni])
        want_material='/Game/Sub01Home/ImportedScene/full-home/Materials/Material_'+str(MATERIALS[ni])+'.Material_'+str(MATERIALS[ni])
        if not mesh or mesh.get_path_name()!=want_mesh or c.get_num_materials()!=1 or not material or material.get_path_name()!=want_material or hidden[actor.get_path_name()]or not c.get_editor_property('visible'):
            raise RuntimeError('Original source geometry/material/visibility identity differs '+str(ni))
        owners[ni]=(actor,c,material,capture(u,c))
        preflight.append({'source_node':ni,'actor':actor.get_path_name(),'component':c.get_path_name(),'mesh':want_mesh,'material':want_material,'current_world_transform':str(c.get_world_transform())})
    source=ROOT/'bath-corridor.glb';expected=source_triangles(source.read_bytes())
    backup=project/'Saved/PrivateMapBackups'/('bath-corridor-'+str(time.time_ns()));backup.mkdir(parents=True)
    shutil.copy2(project/'Content/Sub01Home/ActualHome.umap',backup/'ActualHome.umap')
    for name in ('__ExternalActors__','__ExternalObjects__'):
        folder=project/'Content'/name/'Sub01Home/ActualHome'
        if folder.exists():shutil.copytree(folder,backup/name)
    dest=PREFIX+uuid.uuid4().hex;created=[];parts=[];activated=False
    try:
        task=u.AssetImportTask();task.filename=str(source);task.destination_path=dest;task.automated=True;task.replace_existing=False;task.save=False
        u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        meshes=[m for m in (u.EditorAssetLibrary.load_asset(p)for p in u.EditorAssetLibrary.list_assets(dest,recursive=True,include_folder=False))if isinstance(m,u.StaticMesh)]
        by_name={m.get_name():m for m in meshes}
        if len(meshes)!=9 or set(by_name)!={'SUB01_BathCorridor_SourceNode_'+str(n)for n in NODES}or any(not m.get_path_name().startswith(dest+'/')for m in meshes):
            raise RuntimeError('Exact nine unique owned source meshes required')
        sub=u.get_editor_subsystem(u.StaticMeshEditorSubsystem)
        for ni in NODES:
            mesh=by_name['SUB01_BathCorridor_SourceNode_'+str(ni)];settings=sub.get_nanite_settings(mesh)
            for key,value in (('enabled',False),('keep_percent_triangles',1.),('trim_relative_error',0.),('fallback_percent_triangles',1.),('fallback_relative_error',0.)):
                settings.set_editor_property(key,value)
            sub.set_nanite_settings(mesh,settings,True)
            mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag',u.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
            if not u.EditorAssetLibrary.save_loaded_asset(mesh,only_if_is_dirty=False):raise RuntimeError('Owned source mesh save failed '+str(ni))
            actor=eas.spawn_actor_from_class(u.StaticMeshActor,u.Vector(0,0,0));c=actor.get_components_by_class(u.StaticMeshComponent)[0];created.append((actor,c))
            actor.set_actor_hidden_in_game(True);c.set_static_mesh(mesh);c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
            c.set_material(0,owners[ni][2]);actor.set_actor_label('SUB01_BathCorridor_SourceNode_'+str(ni))
            c.set_mobility(u.ComponentMobility.MOVABLE if ni==118 else u.ComponentMobility.STATIC)
            tag='SUB01BathroomCorridor:'+SHA+':SourceNode'+str(ni);c.set_editor_property('component_tags',[u.Name(tag)])
            actual=native_triangles(u,c)
            if not same_triangles(expected[ni],actual,.001):
                raise RuntimeError('Owned full source world surface differs '+str(ni)+' expected='+str(len(expected[ni]))+' actual='+str(len(actual)))
            parts.append({'source_node':ni,'actor':actor.get_path_name(),'component':c.get_path_name(),'mesh':mesh.get_path_name(),'material':owners[ni][2].get_path_name(),'native_world_triangles':len(actual),'full_source_world_triangle_parity':True,'world_bounds_ue_cm':bounds(actual),'tag':tag})
        if fingerprint(u,original)!=before or hidden!={a.get_path_name():bool(a.get_editor_property('hidden'))for a in original}:
            raise RuntimeError('Protected originals changed before activation')
        # Every complete replacement is proved before any original is hidden.
        activated=True
        for ni,(actor,c)in zip(NODES,created):
            old,old_component,material,state=owners[ni]
            restore(u,c,state,force_response_copy=True)
            old.set_actor_hidden_in_game(True);old_component.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
            actor.set_actor_hidden_in_game(False)
            if c.get_material(0)!=material:raise RuntimeError('Exact original PBR binding changed')
        allowed=copy.deepcopy(before)
        for ni in NODES:allowed[owners[ni][0].get_path_name()]['components'][0]['collision']=str(u.CollisionEnabled.NO_COLLISION)
        after_hidden=dict(hidden)
        for ni in NODES:after_hidden[owners[ni][0].get_path_name()]=True
        if fingerprint(u,original)!=allowed or after_hidden!={a.get_path_name():bool(a.get_editor_property('hidden'))for a in original}:
            raise RuntimeError('Corridor activation changed an unrelated original or field')
        if not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Corridor map save failed')
        result={'schema':'sub01.bathroom-corridor-native-import.v1','source_sha256':SOURCE_SHA,'export_sha256':SHA,'source_contract_sha256':CONTRACT_SHA,
                'source_nodes':list(NODES),'saved':True,'originals_preserved':True,'protected_originals_verified':len(original),'parts':parts,
                'old_originals':preflight,'originals_state_before':{owners[n][0].get_path_name():before[owners[n][0].get_path_name()]for n in NODES},
                'backup':str(backup),'saved_map_sha256':hashlib.sha256((project/'Content/Sub01Home/ActualHome.umap').read_bytes()).hexdigest(),
                'asset_prefix':dest+'/','source_triangle_count':876,'native_triangle_count':sum(p['native_world_triangles']for p in parts),
                'geometry_and_materials_verified':True,'source_contract':contract,'native_collision_or_privacy_or_route_accepted':False,'visual_acceptance':False,
                'backend_profile_changed':False,'pawn_or_camera_changed':False}
        audit.mkdir(exist_ok=True);temp=audit/(RECEIPT+'.pending');temp.write_text(json.dumps(result,indent=2)+'\n');temp.chmod(0o600);temp.replace(audit/RECEIPT)
        return result
    except Exception as error:
        for actor,c in created:
            c.set_static_mesh(None);eas.destroy_actor(actor)
        if activated:
            for ni in NODES:
                old,c,_,state=owners[ni]
                if bool(old.get_editor_property('hidden'))!=hidden[old.get_path_name()]:old.set_actor_hidden_in_game(hidden[old.get_path_name()])
                restore(u,c,state)
        audit.mkdir(exist_ok=True);(audit/'bathroom-corridor-native-refusal.json').write_text(json.dumps({'error':str(error),'owned_assets_quarantined':dest,'proved_parts':parts,'original_preflight':preflight,'backup':str(backup)},indent=2)+'\n')
        if fingerprint(u,original)!=before or hidden!={a.get_path_name():bool(a.get_editor_property('hidden'))for a in original}:
            raise RuntimeError('Corridor rollback differs; stop further imports and retain map backup')from error
        if activated and not u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level():raise RuntimeError('Corridor rollback save failed')from error
        raise


def run():
    import unreal
    return main(unreal)
