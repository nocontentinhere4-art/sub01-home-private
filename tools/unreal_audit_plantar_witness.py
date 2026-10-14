"""Read-only server UE bind-space plantar-membership witnesses.

Broad foot-weight vertices are dumped at fixed identities, not declared soles.
The data lets an auditor distinguish cuff/upper-foot from actual plantar skin
using original geometry/material/topology before a foot contact gate is chosen.
"""
import json
from pathlib import Path
import unreal as u


def run():
    mesh=u.load_asset('/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner')
    clip=u.load_asset('/Game/Sub01Hands/FBX/SUB01_DeskTyping.SUB01_DeskTyping')
    if not mesh or not clip or mesh.get_editor_property('skeleton') != clip.get_editor_property('skeleton'):
        raise RuntimeError('Actual matching owner/typing skeleton required')
    u.Sub01HomeHandsInstance.finish_pending_skin_compilation()
    component=u.SkeletalMeshComponent();component.set_skeletal_mesh_asset(mesh)
    names=[component.get_bone_name(i) for i in range(component.get_num_bones())]
    parents={str(n):str(component.get_parent_bone(n)) for n in names}
    body=u.Transform(location=u.Vector(203.9,-232.3,-.6),rotation=u.Rotator(yaw=180))
    rows=[]
    for time in (3.,6.,8.):
        local=dict(zip(map(str,names),u.AnimationLibrary.get_bone_poses_for_time(clip,names,time,False,mesh)))
        resolved={}
        def pose(name):
            if name not in resolved:
                parent=parents[name]
                resolved[name]=u.MathLibrary.compose_transforms(local[name],pose(parent)) if parent in local else local[name]
            return resolved[name]
        row=json.loads(u.Sub01HomeHandsInstance.dump_imported_foot_witness(mesh,[pose(str(n)) for n in names],body))
        if 'error' in row or row.get('invalidInfluences') or not row.get('vertices'):
            raise RuntimeError('Invalid actual imported foot witness: '+str(row.get('error',row.get('invalidInfluences'))))
        rows.append({'time':time,**row})
    identities=[(v['section'],v['vertex']) for v in rows[0]['vertices']]
    for row in rows[1:]:
        if [(v['section'],v['vertex']) for v in row['vertices']]!=identities:
            raise RuntimeError('Witness membership changed with pose')
    result={'schema':'sub01.imported-foot-witness.v1','runtime_ready':False,'contact_accepted':False,
            'selection_basis':'fixed original bind geometry and weights; no posed-height or posed-normal gate',
            'owner':mesh.get_path_name(),'clip':clip.get_path_name(),'samples':rows}
    out=Path(u.Paths.project_dir())/'private-audit/native-plantar-witness.json';out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result,indent=2)+'\n');u.log('SUB01_FIXED_BIND_FOOT_WITNESS '+str(out))

if __name__=='__main__':run()
