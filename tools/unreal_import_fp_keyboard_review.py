"""Owned arms/keyboard REVIEW assets only; no world/config/readiness changes.

Actual original owner USkeleton and material are reused. The known 240Hz hover,
open housing contacts, and source/native wrist-frame difference remain unaccepted.
Failed asynchronous assets are quarantined, never force-deleted.
"""
import hashlib
import json
import uuid
import math
import re
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))

import native_life_skeleton_parity as parity
from verified_owner_skeleton import read_project_owner_parents
from unreal_import_phone_grip import existing_owner

SOURCE=Path('/workspace/sub01-home-private/fp-keyboard-review-fbx-r5')
MESH_SHA='a862cbd3457c2b25da227c0eea2e04dcd8fe1f637115da0ccc69fbcf888ad154'
CLIP_SHA='0cd1395b0b1d8187c928aeb93950df69abc67f7eeefa91ed1df58c1ea761f5db'
FBX_SHA='07baf00adbe6e9fa49f22ea954787e3590ba602a5c7ab6f247cc990a50205d53'
MATERIAL_SLOT='tripo_material_6bf04053-4eb9-4c81-aed9-ebf290057e82'
UV_SOURCE=Path('/workspace/sub01-home-private/fp-keyboard-review-uv-r1/uv-roundtrip.json')
MESH_SOURCE=Path('/workspace/sub01-home-private/fp-arms-candidate-r1/SUB01_FirstPersonArms_SourceCandidate.glb')
CLIP_SOURCE=Path('/workspace/sub01-home-private/fp-keyboard-loop-r3/SUB01_FirstPersonKeyboard_LoopCandidate.glb')
DEST='/Game/Sub01Hands/KeyboardReview'
RECEIPT='unreal-fp-keyboard-review-import.json'


def check_source(report,uv):
    if report.get('schema')!='sub01.fp-keyboard-review-fbx.v1' or report.get('arms_mesh_glb_sha256')!=MESH_SHA or report.get('derived_clip_sha256')!=CLIP_SHA or report.get('fbx_sha256')!=FBX_SHA:
        raise RuntimeError('Exact written review-only source export required')
    if report.get('keys')!=409 or report.get('fps')!=120 or abs(report.get('duration_s',-1)-3.4)>1e-6 or report.get('actual_roundtrip_curve_counts')!=[409]:
        raise RuntimeError('Review clip must retain all409 written120Hz keys')
    names=report.get('original_joint_names',[])
    if len(names)!=65 or len(set(names))!=65 or not 0<=report.get('all409_keys_all65_joint_heads_max_error_cm',1)<=.02:
        raise RuntimeError('Actual original65joint FBX roundtrip required')
    if any(report.get(k)is not False for k in ('source_ready','native_ready','activity_ready','source_native_skeleton_mutated')):
        raise RuntimeError('Diagnostic export cannot claim acceptance')
    if report.get('original_joints')!=65 or report.get('actual_roundtrip_curves')!=659 or report.get('original_source_material_slots')!=[MATERIAL_SLOT]:
        raise RuntimeError('Actual complete source rig/curves/material identity required')
    for key in ('source_GLTF_to_Blender_skin_geometry','FBX_roundtrip_skin_geometry'):
        rows=report.get(key,[])
        if len(rows)!=4 or any(r.get('triangles')!=88592 or r.get('same_triangle_count')is not True or r.get('all_triangles_within0_02cm')is not True or not finite_band(r.get('maximum_nearest_triangle_corner_error_cm'),.02)for r in rows):
            raise RuntimeError('All four actual geometry probes must preserve source arm triangles')
    if uv.get('schema')!='sub01.fp-keyboard-review-fbx-uv.v1' or uv.get('fbx_sha256')!=FBX_SHA or uv.get('triangles')!=88592 or uv.get('one_to_one_position_AND_UV_triangle_matches')!=88592 or uv.get('all_source_and_target_triangles_used_once')is not True:
        raise RuntimeError('Actual bijective position and UV FBX triangle proof required')
    if uv.get('source_material_slots')!=[MATERIAL_SLOT] or uv.get('FBX_material_slots')!=[MATERIAL_SLOT] or not finite_band(uv.get('max_nearest_valid_position_error_cm'),.02)or not finite_band(uv.get('max_nearest_valid_uv_error'),1.e-6):
        raise RuntimeError('FBX UV/material source contract differs')
    if any(uv.get(k)is not False for k in ('source_ready','native_ready','activity_ready')):
        raise RuntimeError('Source UV proof cannot grant native acceptance')
    return names


def finite_band(value,maximum):
    return type(value)in(int,float)and math.isfinite(value)and 0<=value<=maximum


def authentic_slot(materials):
    slots=[s for s in materials if str(s.get_editor_property('material_slot_name'))==MATERIAL_SLOT]
    if len(slots)!=1:
        raise RuntimeError('Unique exact original source material slot required; no shortened alias')
    return slots[0]


def material_snapshot(materials):
    return [(str(s.get_editor_property('material_slot_name')),s.get_editor_property('material_interface').get_path_name()if s.get_editor_property('material_interface')else None)for s in materials]


def imported_geometry_counts(text):
    match=re.match(r'importedVertices=(\d+) lods=(\d+) softVertices=(\d+) ',str(text))
    if not match or any(int(value)<=0 for value in match.groups()):
        raise RuntimeError('Actual imported CPU skin geometry is absent or incomplete')
    return dict(zip(('imported_vertices','lods','soft_vertices'),map(int,match.groups())))


def skeleton_state(u,mesh):
    probe=u.SkeletalMeshComponent();probe.set_skeletal_mesh_asset(mesh)
    names=[str(probe.get_bone_name(i))for i in range(probe.get_num_bones())]
    parents={n:(None if str(probe.get_parent_bone(n))in('None','')else str(probe.get_parent_bone(n)))for n in names}
    probe.set_skeletal_mesh_asset(None)
    return names,parents


def main(u,root=None):
    root=Path(root or u.Paths.project_dir()).resolve();report=json.loads((SOURCE/'keyboard-review-fbx-roundtrip.json').read_text());uv=json.loads(UV_SOURCE.read_text());source_names=check_source(report,uv)
    file=SOURCE/'FirstPersonKeyboardReview.fbx'
    for path,expected in ((file,FBX_SHA),(MESH_SOURCE,MESH_SHA),(CLIP_SOURCE,CLIP_SHA)):
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise RuntimeError('Review source bytes changed: '+path.name)
    canonical=read_project_owner_parents(root)
    if set(canonical)!=set(source_names):raise RuntimeError('Review rig differs immutable original65owner')
    original,skeleton=existing_owner(u,root);u.Sub01HomeHandsInstance.finish_pending_skin_compilation();before=skeleton_state(u,original)
    owner=parity.map_owner_parents_to_ue(canonical,before[0])
    if not parity.structural_root_parity(*before,owner,structure_only=True)['pass']:raise RuntimeError('Existing owner structural hierarchy differs')
    original_materials=list(original.get_editor_property('materials'))
    original_binding=material_snapshot(original_materials)
    material=authentic_slot(original_materials).get_editor_property('material_interface')
    if not material:raise RuntimeError('Authentic original source material is unbound')
    tx=uuid.uuid4().hex;dest=DEST+'/V_'+FBX_SHA[:12]+'_'+tx;lib=u.EditorAssetLibrary
    if lib.does_directory_exist(dest):raise RuntimeError('Review namespace already exists')
    world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world();u.SystemLibrary.execute_console_command(world,'Interchange.FeatureFlags.Import.FBX 0')
    options=u.FbxImportUI()
    for k,v in [('automated_import_should_detect_type',False),('import_as_skeletal',True),('import_mesh',True),('import_animations',True),('import_materials',False),('import_textures',False),('create_physics_asset',False),('mesh_type_to_import',u.FBXImportType.FBXIT_SKELETAL_MESH),('skeleton',skeleton)]:options.set_editor_property(k,v)
    skin=options.get_editor_property('skeletal_mesh_import_data')
    skin.set_editor_property('update_skeleton_reference_pose',False);skin.set_editor_property('use_t0_as_ref_pose',False)
    animation=options.get_editor_property('anim_sequence_import_data');animation.set_editor_property('use_default_sample_rate',False);animation.set_editor_property('custom_sample_rate',120)
    task=u.AssetImportTask();task.filename=str(file);task.destination_path=dest;task.destination_name='SUB01_FirstPersonKeyboardReview';task.automated=True;task.replace_existing=False;task.save=False;task.options=options
    try:
        u.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task]);paths=list(map(str,task.imported_object_paths))
        if not paths or any(not p.startswith(dest+'/')for p in paths):raise RuntimeError('Import escaped unique owned review namespace')
        # The legacy FBX task returns the mesh before its generated animation is
        # listed in imported_object_paths. Finish actual asset compilation, then
        # enumerate only this fresh unique owned namespace (never another import).
        u.Sub01HomeHandsInstance.finish_pending_skin_compilation()
        owned_paths=list(map(str,lib.list_assets(dest,recursive=True,include_folder=False)))
        if not owned_paths or any(not p.startswith(dest+'/')for p in owned_paths):raise RuntimeError('Actual review assets escaped fresh owned namespace')
        objects=[u.load_asset(p)for p in owned_paths];meshes=[o for o in objects if isinstance(o,u.SkeletalMesh)];clips=[o for o in objects if isinstance(o,u.AnimSequence)]
        if len(objects)!=2 or len(meshes)!=1 or len(clips)!=1:raise RuntimeError('Expected one authentic arms mesh and one review clip')
        mesh,clip=meshes[0],clips[0];u.Sub01HomeHandsInstance.finish_pending_skin_compilation()
        if mesh.get_editor_property('skeleton')!=skeleton or clip.get_editor_property('skeleton')!=skeleton or skeleton_state(u,original)!=before:raise RuntimeError('Existing original skeleton changed or review skeleton differs')
        names,parents=skeleton_state(u,mesh);mapped=parity.map_owner_parents_to_ue(canonical,names)
        if not parity.structural_root_parity(names,parents,mapped,structure_only=True)['pass']:raise RuntimeError('Review arms hierarchy differs original')
        if (names,parents)!=before:raise RuntimeError('Review mesh reference hierarchy differs actual original owner')
        if int(u.AnimationLibrary.get_num_keys(clip))!=409 or abs(float(clip.get_editor_property('sequence_length'))-3.4)>1e-3:raise RuntimeError('Native review clip was resampled or truncated')
        structure=parity.structural_root_parity(names,parents,mapped,structure_only=True)
        samples=[]
        if structure['structural_root']:
            for time in parity.sample_times(3.4):
                pose=u.AnimationLibrary.get_bone_poses_for_time(clip,[structure['structural_root']],time,False,mesh)[0]
                p,q,s=pose.translation,pose.rotation,pose.scale3d
                samples.append((time,(p.x,p.y,p.z),(q.x,q.y,q.z,q.w),(s.x,s.y,s.z)))
        skeleton_proof=parity.structural_root_parity(names,parents,mapped,samples)
        if not skeleton_proof['pass']:raise RuntimeError('Review structural root carries unexpected animation')
        materials=list(mesh.get_editor_property('materials'))
        if len(materials)!=1:raise RuntimeError('Review arms material slot count differs source')
        authentic_slot(materials).set_editor_property('material_interface',material);mesh.set_editor_property('materials',materials)
        bounds=mesh.get_bounds().box_extent
        if any(not math.isfinite(v)or v<=0 for v in (bounds.x,bounds.y,bounds.z)):raise RuntimeError('Review mesh has no real three-dimensional skin')
        geometry=u.Sub01HomeHandsInstance.describe_imported_skin_geometry(mesh)
        geometry_counts=imported_geometry_counts(geometry)
        if material_snapshot(original.get_editor_property('materials'))!=original_binding:raise RuntimeError('Original owner material bindings changed')
        for o in (mesh,clip):
            if not lib.save_loaded_asset(o,only_if_is_dirty=False):raise RuntimeError('Owned review asset save failed')
        result={'schema':'sub01.unreal-fp-keyboard-review-import.v1','mesh':mesh.get_path_name(),'clip':clip.get_path_name(),'skeleton':skeleton.get_path_name(),'fbx_sha256':FBX_SHA,'derived_clip_sha256':CLIP_SHA,'arms_mesh_sha256':MESH_SHA,'keys':409,'fps':120,'duration_s':3.4,'native_geometry_probe':geometry,'native_bones':len(names),'skeleton_parity':skeleton_proof,'authentic_material':material.get_path_name(),'source_export':report,'source_UV_bijection':uv,'authentic_material_slot':MATERIAL_SLOT,'source_arm_triangles':88592,'native_triangle_count_verified':False,'native_skin_and_UV_parity_accepted':False,'original_owner_untouched':True,'world_and_config_untouched':True,'source_ready':False,'native_ready':False,'activity_ready':False,'visual_acceptance':False,'label':'PRIVATE REVIEW ONLY; contact/skin/material/POV require actual Game inspection'}
        result['native_geometry_counts']=geometry_counts
        pending=root/(RECEIPT+'.pending');pending.write_text(json.dumps(result,indent=2)+'\n');pending.chmod(0o600);pending.replace(root/RECEIPT);return result
    except Exception as error:
        audit=root/'private-audit';audit.mkdir(exist_ok=True);(audit/'fp-keyboard-review-import-refusal.json').write_text(json.dumps({'error':str(error),'owned_assets_quarantined':dest,'force_delete_used':False,'world_and_config_untouched':True},indent=2)+'\n');raise


def run():
    import unreal
    return main(unreal)
