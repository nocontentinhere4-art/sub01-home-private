"""Import the measured DERIVED phone clip onto the existing owner skeleton only.

No config, actor, original Phone clip or readiness flag is changed. Failed owned
assets stay quarantined; never ForceDelete an asynchronously referenced asset.
Renderer owns the fixed Editor queue and actual first-person visual review.
"""
import hashlib
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
import native_life_skeleton_parity as parity
from verified_owner_skeleton import read_project_owner_parents

SOURCE=Path('/workspace/sub01-home-private/phone-grip-derived-fbx-e5dbdac')
DERIVED_SHA='81c1d4e10c0a71f46cb4aac36eafd605f92f2fa9397f8d444cc10775445823b2'
FBX_SHA='30ce52419d204f914bda05d1a73aefbd49affd0c3f3bfd62f2ccfeacdb82e9d4'
DEST='/Game/Sub01Hands/Phone'
ASSET='SUB01_PhoneGrip'
OBJECT=DEST+'/'+ASSET+'.'+ASSET
RECEIPT='unreal-phone-grip-import.json'
SCHEMA='sub01.unreal-phone-grip-import.v1'
KEYS=557
DURATION=(KEYS-1)/30


def check_source(audit,roundtrip,contract):
    clips=audit.get('clips',[])
    if audit.get('schema')!='sub01.phone-grip-fbx-audit.v1' or len(clips)!=1 or audit.get('bone_edits') is not False or audit.get('fps')!=30:
        raise RuntimeError('Exact derived Phone conversion audit required')
    row=clips[0]
    if row.get('role')!='PhoneGripDerived' or row.get('derived_glb_sha256')!=DERIVED_SHA or row.get('sha256')!=FBX_SHA or row.get('file')!='PhoneGrip.fbx' or row.get('frames')!=KEYS or abs(float(row.get('duration_s',-1))-DURATION)>1e-3:
        raise RuntimeError('Phone source hash/keys/duration differs actual export')
    names=audit.get('bone_names',[])
    if len(names)!=65 or len(set(names))!=65 or any(not n.startswith('mixamorig:') for n in names):raise RuntimeError('Original 65 owner names required')
    if roundtrip.get('schema')!='sub01.phone-grip-fbx-source-roundtrip.v1' or roundtrip.get('derived_glb_sha256')!=DERIVED_SHA or roundtrip.get('fbx_sha256')!=FBX_SHA or roundtrip.get('bones')!=65 or roundtrip.get('actual_fbx_key_counts')!=[KEYS] or roundtrip.get('actual_fbx_unique_times')!=KEYS or not 0<=roundtrip.get('all557_frames_all65_joint_heads_max_error_cm',1)<=.02:
        raise RuntimeError('Actual written FBX roundtrip proof required')
    if contract.get('ok') is not True or contract.get('derived_sha256')!=DERIVED_SHA or contract.get('errors')!=[]:raise RuntimeError('Actual raw-owner-derived byte contract required')
    if audit.get('runtime_ready') is not False or audit.get('phone_grip_verified') is not False or any(roundtrip.get(k) is not False for k in ('native_ready','phone_contact_accepted','ue_imported')):
        raise RuntimeError('Source proof must not claim native acceptance')
    return row


def existing_owner(u,root):
    receipt=root/'unreal-fbx-hands-import.json'
    if receipt.is_file():
        data=json.loads(receipt.read_text());mesh=u.load_asset(data['mesh']);skeleton=u.load_asset(data['skeleton'])
    else:
        mesh=u.load_asset('/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner')
        typing=u.load_asset('/Game/Sub01Hands/FBX/SUB01_DeskTyping.SUB01_DeskTyping')
        if not isinstance(typing,u.AnimSequence):raise RuntimeError('Existing captured typing skeleton absent')
        skeleton=typing.get_editor_property('skeleton')
    if not isinstance(mesh,u.SkeletalMesh) or not skeleton or mesh.get_editor_property('skeleton')!=skeleton:raise RuntimeError('Existing original owner skeleton required')
    return mesh,skeleton


def verify_clip(u,clip,mesh,skeleton,names,parents,owner):
    if not isinstance(clip,u.AnimSequence) or clip.get_editor_property('skeleton')!=skeleton:raise RuntimeError('Phone animation is not on unchanged owner skeleton')
    duration=float(clip.get_editor_property('sequence_length'));keys=int(u.AnimationLibrary.get_num_keys(clip))
    if abs(duration-DURATION)>1e-3 or keys!=KEYS:raise RuntimeError('Native Phone duration/557 sampled keys differ source')
    structure=parity.structural_root_parity(names,parents,owner,structure_only=True)
    if not structure['pass']:raise RuntimeError('Owner skeleton hierarchy differs')
    samples=[]
    if structure['structural_root']:
        for t in parity.sample_times(duration):
            pose=u.AnimationLibrary.get_bone_poses_for_time(clip,[structure['structural_root']],t,False,mesh)[0]
            p,q,s=pose.translation,pose.rotation,pose.scale3d
            samples.append((t,(p.x,p.y,p.z),(q.x,q.y,q.z,q.w),(s.x,s.y,s.z)))
    proof=parity.structural_root_parity(names,parents,owner,samples)
    if not proof['pass']:raise RuntimeError('Phone structural root carries unexpected motion')
    return {'role':'PhoneGrip','object_path':clip.get_path_name(),'duration_s':duration,'sampled_keys':keys,
            'same_existing_skeleton':True,'skeleton_parity':proof,'fbx_sha256':FBX_SHA,'derived_glb_sha256':DERIVED_SHA}


def main(u,root=None):
    root=Path(root or u.Paths.project_dir()).resolve()
    audit=json.loads((SOURCE/'phone-grip-fbx-audit.json').read_text())
    roundtrip=json.loads((SOURCE/'phone-grip-fbx-roundtrip.json').read_text())
    contract=json.loads((SOURCE/'packet-contract-check.json').read_text());check_source(audit,roundtrip,contract)
    file=SOURCE/'PhoneGrip.fbx'
    if hashlib.sha256(file.read_bytes()).hexdigest()!=FBX_SHA:raise RuntimeError('Written Phone FBX changed')
    owner_parents=read_project_owner_parents(root)
    if set(owner_parents)!=set(audit['bone_names']):raise RuntimeError('Phone conversion owner differs portable original owner')
    mesh,skeleton=existing_owner(u,root);u.Sub01HomeHandsInstance.finish_pending_skin_compilation()
    probe=u.SkeletalMeshComponent();probe.set_skeletal_mesh_asset(mesh)
    names=[str(probe.get_bone_name(i)) for i in range(probe.get_num_bones())]
    parents={n:(None if str(probe.get_parent_bone(n)) in ('None','') else str(probe.get_parent_bone(n))) for n in names}
    owner=parity.map_owner_parents_to_ue(owner_parents,names)
    probe.set_skeletal_mesh_asset(None)
    if not parity.structural_root_parity(names,parents,owner,structure_only=True)['pass']:raise RuntimeError('Existing owner hierarchy differs')
    lib=u.EditorAssetLibrary;final=DEST+'/'+ASSET
    if lib.does_asset_exist(final):
        saved=json.loads((root/RECEIPT).read_text())
        if saved.get('schema')!=SCHEMA or saved.get('clip',{}).get('fbx_sha256')!=FBX_SHA or saved.get('clip',{}).get('object_path')!=OBJECT:raise RuntimeError('Existing PhoneGrip asset has no matching receipt; untouched')
        verify_clip(u,u.load_asset(OBJECT),mesh,skeleton,names,parents,owner)
        return dict(saved,preserved_existing=True)
    txid=uuid.uuid4().hex;staging=DEST+'/_Staging_'+txid
    world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    u.SystemLibrary.execute_console_command(world,'Interchange.FeatureFlags.Import.FBX 0')
    options=u.FbxImportUI()
    for k,v in [('automated_import_should_detect_type',False),('import_as_skeletal',True),('import_mesh',False),('import_animations',True),('import_materials',False),('import_textures',False),('mesh_type_to_import',u.FBXImportType.FBXIT_ANIMATION),('skeleton',skeleton)]:options.set_editor_property(k,v)
    options.get_editor_property('anim_sequence_import_data').set_editor_property('use_default_sample_rate',True)
    task=u.AssetImportTask();task.filename=str(file);task.destination_path=staging;task.destination_name=ASSET
    task.automated=True;task.replace_existing=False;task.save=False;task.options=options
    try:
        u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        if any(not str(p).startswith(staging+'/') for p in task.imported_object_paths):raise RuntimeError('Phone import wrote outside owned staging')
        clips=[c for c in (u.load_asset(p) for p in task.imported_object_paths) if isinstance(c,u.AnimSequence)]
        if len(clips)!=1:raise RuntimeError('Expected one derived Phone animation only')
        row=verify_clip(u,clips[0],mesh,skeleton,names,parents,owner)
        if lib.does_asset_exist(final) or not lib.rename_asset(clips[0].get_path_name().split('.')[0],final):raise RuntimeError('Verified Phone final path unavailable; existing assets untouched')
        clip=u.load_asset(OBJECT);row=verify_clip(u,clip,mesh,skeleton,names,parents,owner)
        if not lib.save_asset(final,only_if_is_dirty=False):raise RuntimeError('Derived Phone asset save failed; owned asset quarantined')
        result={'schema':SCHEMA,'owner':mesh.get_path_name(),'skeleton':skeleton.get_path_name(),'clip':row,'transaction_id':txid,
                'derived_glb_sha256':DERIVED_SHA,'fbx_sha256':FBX_SHA,'object_path':row['object_path'],'duration_s':row['duration_s'],'sampled_keys':row['sampled_keys'],
                'original_SUB01_Phone_untouched':True,'label':'derived_from_capture','source_roundtrip':roundtrip,
                'phone_grip_verified':False,'native_contact_verified':False,'visual_acceptance':False,'activity_binding':False,'runtime_ready':False}
        pending=root/(RECEIPT+'.pending');pending.write_text(json.dumps(result,indent=2)+'\n');pending.replace(root/RECEIPT)
        return result
    except Exception as error:
        (root/'private-audit').mkdir(exist_ok=True)
        (root/'private-audit/phone-grip-import-refusal.json').write_text(json.dumps({'error':str(error),'owned_staging_quarantined':staging,'possible_owned_final_quarantined':final,'original_assets_never_deleted_or_replaced':True},indent=2)+'\n')
        raise


def run():
    import unreal
    return main(unreal)
