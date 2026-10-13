"""Gate actual server-imported POV animation bindings, not source-name matches."""
def validate_bindings(source_manifest, imported_report):
    source=source_manifest['binding_requirements']
    mesh=imported_report.get('skeletal_mesh')
    if not mesh or mesh.get('class')!='SkeletalMesh' or not mesh.get('object_path') or not mesh.get('skeleton_path'):
        raise ValueError('Real imported SkeletalMesh/skeleton is not bound')
    if mesh.get('bind_pose_verified') is not True:
        raise ValueError('Actual skin bind matrices/scale/arm axes are not verified')
    valid,unavailable={},{}
    for role in ['Walk','DeskTyping','DeskMouse','Phone']:
        source_path=source['animation_sources'].get(role)
        clip=imported_report.get('clips',{}).get(role)
        if not source_path:
            unavailable[role]='No genuine source capture; another activity is not a substitute'
            continue
        if not clip or clip.get('source_file')!=source_path or clip.get('class')!='AnimSequence' or not clip.get('object_path'):
            unavailable[role]='Actual imported animation is not bound to its source'
            continue
        if clip.get('skeleton_path')!=mesh['skeleton_path']:
            unavailable[role]='Imported USkeleton differs from actual skin'
            continue
        if clip.get('retarget_verified') is not True or clip.get('pov_placement_verified') is not True:
            unavailable[role]='Rest-pose retarget/scale/POV placement is not accepted'
            continue
        if role=='Walk' and clip.get('in_place_root_motion_verified') is not True:
            unavailable[role]='Root displacement would move arms independently of the capsule'
            continue
        if role in ('DeskTyping','DeskMouse','Phone') and clip.get('physical_contact_verified') is not True:
            unavailable[role]='Contact with the actual keyboard/mouse/phone has not been verified'
            continue
        valid[role]=clip['object_path']
    return {'mesh_path':mesh['object_path'],'validated_postures':valid,'unavailable':unavailable,
            'scope':'Imported compatible skeletal clips plus explicit server retarget/POV/contact acceptance; no backend connection or animation compile/render success inferred'}

def native_config(report):
    lines=['[/Script/Sub01HomeLab.Sub01HomeCharacter]',f'HandsMeshPath={report["mesh_path"]}']
    fields={'Walk':'WalkClipPath','DeskTyping':'TypingClipPath','DeskMouse':'MouseClipPath','Phone':'PhoneClipPath'}
    for role,path in report['validated_postures'].items():
        lines.extend([f'{fields[role]}={path}',f'+ValidatedHandsPostures={role}'])
    return '\n'.join(lines)+'\n'

if __name__=='__main__':
    import argparse
    import json
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_manifest',type=Path)
    parser.add_argument('actual_import_report',type=Path)
    parser.add_argument('output_ini',type=Path)
    args=parser.parse_args()
    report=validate_bindings(json.loads(args.source_manifest.read_text()),json.loads(args.actual_import_report.read_text()))
    args.output_ini.parent.mkdir(parents=True,exist_ok=True)
    args.output_ini.write_text(native_config(report))
    print(json.dumps({'validated_postures':list(report['validated_postures']),'unavailable':report['unavailable']}))
