"""Official synchronous Unreal import of one canonical skin + captured clips.

Run only in the actual server editor. Imported skeleton identity/duration/finger
motion are checked; POV/contact/backend readiness is deliberately left false.
"""
import hashlib
import json
import math
import re
from pathlib import Path
import unreal as u
import sys
sys.path.insert(0,str(Path(__file__).parent))
from unreal_skin_bounds import select_built_primary,source_body_candidate

ROOT=Path(u.Paths.project_dir()).resolve()
source=ROOT/'SourceAssets/owner-with-clips-unreal.glb'
audit=json.loads(source.with_suffix('.glb.audit.json').read_text())
raw=source.read_bytes()
if hashlib.sha256(raw).hexdigest()!=audit['output_sha256']:
    raise RuntimeError('Canonical combined import file changed after semantic validation')
doc=json.loads(raw[20:20+int.from_bytes(raw[12:16],'little')])
if doc.get('extensionsRequired') or not audit.get('all_captured_animation_values_unchanged') or not audit.get('reference_pose_alignment_verified'):
    raise RuntimeError('Canonical clip package is compressed or lacks semantic source-reference/capture proof')
manager=u.InterchangeManager.get_interchange_manager_scripted()
params=u.ImportAssetParameters();params.set_editor_property('is_automated',True)
data=manager.create_source_data(str(source))
if not manager.can_translate_source_data(data):
    raise RuntimeError('Official glTF translator does not support this canonical source')
imported=manager.import_asset('/Game/Sub01Hands/Canonical',data,params)
if not imported:
    raise RuntimeError('Actual canonical skeletal import returned no objects')
objects=[u.load_asset(path)for path in u.EditorAssetLibrary.list_assets('/Game/Sub01Hands/Canonical',recursive=True,include_folder=False)]
meshes=[obj for obj in objects if isinstance(obj,u.SkeletalMesh)]
clips=[obj for obj in objects if isinstance(obj,u.AnimSequence)]
if not meshes or len(clips)!=len(doc['animations']):
    raise RuntimeError('Actual imported mesh/animation count differs from canonical source')
canonical=lambda name:re.sub('[^a-z0-9]','',re.sub('^mixamorig[:_]?','',str(name),flags=re.I).lower())
source_bones={canonical(doc['nodes'][joint]['name'])for joint in doc['skins'][0]['joints']}
mesh_rows=[]
for mesh in meshes:
    component=u.SkeletalMeshComponent();component.set_skeletal_mesh_asset(mesh)
    bone_names=[component.get_bone_name(i)for i in range(component.get_num_bones())]
    missing=source_bones-{canonical(name)for name in bone_names}
    if missing:raise RuntimeError('Imported skin loses actual hand/body joints: '+repr(sorted(missing)))
    skeleton=mesh.get_editor_property('skeleton')
    if not skeleton:raise RuntimeError('Imported skeletal skin has no actual USkeleton')
    bounds=mesh.get_bounds();extent=bounds.box_extent
    imported_bounds=mesh.get_imported_bounds();imported_extent=imported_bounds.box_extent
    mesh_rows.append({'mesh':mesh,'bones':bone_names,'volume':extent.x*extent.y*extent.z,'row':{
        'class':'SkeletalMesh','object_path':mesh.get_path_name(),'skeleton_path':skeleton.get_path_name(),
        'bone_count':len(bone_names),'canonical_source_joints_matched':len(source_bones),
        'bounds_extent_cm':[extent.x,extent.y,extent.z],'imported_bounds_extent_cm':[imported_extent.x,imported_extent.y,imported_extent.z],'bind_pose_verified':False}})
primary=select_built_primary(mesh_rows)
diagnostic_source_body=source_body_candidate(doc,mesh_rows,canonical)
# A source-name match permits bone-motion diagnostics, NOT runtime readiness.
pose_probe=primary or diagnostic_source_body or mesh_rows[0]
mesh=pose_probe['mesh'];skeleton=mesh.get_editor_property('skeleton')
if any(item['mesh'].get_editor_property('skeleton')!=skeleton for item in mesh_rows):
    raise RuntimeError('Canonical body parts imported into different actual skeleton assets')
roles={'typing':'DeskTyping','walking':'Walk','walk':'Walk','texting':'Phone','phone':'Phone','gaming':'Gaming'}
source_roles=json.loads((ROOT/'SourceAssets/source-manifest.json').read_text())['binding_requirements']['animation_sources']
clip_rows={}
for clip in clips:
    if clip.get_editor_property('skeleton')!=skeleton:
        raise RuntimeError('Actual imported animation does not share canonical owner USkeleton: '+clip.get_path_name())
    matched=[animation for animation in doc['animations']if canonical(animation['name'])in canonical(clip.get_name())]
    if len(matched)!=1:raise RuntimeError('Ambiguous imported clip/source name association: '+clip.get_name())
    animation=matched[0]
    expected=max(doc['accessors'][sampler['input']]['max'][0]for sampler in animation['samplers'])
    duration=clip.get_editor_property('sequence_length')
    if abs(duration-expected)>.067:raise RuntimeError('Actual captured clip duration changed during import')
    finger_names=[name for name in pose_probe['bones']if re.search('hand(thumb|index|middle|ring|pinky)[123]$',canonical(name))]
    poses=[u.AnimationLibrary.get_bone_poses_for_time(clip,finger_names,min(duration*.95,duration*i/16),False,mesh)for i in range(17)]
    moving=0
    for index in range(len(finger_names)):
        first=poses[0][index].rotation
        if any(1-abs(first.x*p[index].rotation.x+first.y*p[index].rotation.y+first.z*p[index].rotation.z+first.w*p[index].rotation.w)>1e-7 for p in poses[1:]):moving+=1
    role=roles.get(animation['name'].lower(),animation['name'])
    clip_rows[role]={'class':'AnimSequence','object_path':clip.get_path_name(),'skeleton_path':skeleton.get_path_name(),
        'source_file':source_roles.get(role),'duration':duration,'expected_duration':expected,
        'actual_moving_finger_segments_observed':moving,'same_actual_skeleton_verified':True,
        'retarget_source_math_verified':True,'retarget_verified':False,'pov_placement_verified':False,
        'in_place_root_motion_verified':False,'physical_contact_verified':False}
u.EditorAssetLibrary.save_directory('/Game/Sub01Hands/Canonical',only_if_is_dirty=False,recursive=True)
report={'source_sha256':audit['output_sha256'],'skeletal_mesh':primary['row']if primary else None,
        'primary_geometry_bounds_verified':primary is not None,
        'source_body_candidate_diagnostic_only':diagnostic_source_body['row']if diagnostic_source_body else None,
        'skeletal_mesh_parts':[item['row']for item in mesh_rows],'clips':clip_rows,
        'runtime_ready':False,'backend_connected':False,
        'scope':'Actual imported UE objects, shared USkeleton, all65 source joints, capture durations and observed finger motion. Zero bounds never select a runtime primary. Source-name candidate is diagnostic only. Multipart skin/POV/contact/locomotion/native runtime rendering acceptance remains pending.'}
(ROOT/'unreal-hands-import.json').write_text(json.dumps(report,indent=2)+'\n')
u.log('SUB01_CANONICAL_HANDS_IMPORTED_NOT_YET_POV_ACCEPTED '+json.dumps(report))
