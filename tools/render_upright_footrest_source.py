"""Leased server CPU diagnostic of the unchanged candidate and genuine assets.
No native/world changes; no acceptance is inferred from this source render.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path


def render(merged,chair,chair_report,desk,footrest,fit_report,output):
    import bpy
    from mathutils import Vector
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    report=json.loads(Path(fit_report).read_text());measured=json.loads(Path(chair_report).read_text())['chair']['transform']
    if report['written_glb_sha256']!='5e216ec4af102fbfcd919b91adb510229f2d1468098153d1c3cc983760de6de8':raise ValueError('Preserve exact failed candidate for diagnosis')
    bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene;scene.render.fps=30
    def load(path):
        before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(path));return set(bpy.data.objects)-before
    owner=load(merged);arms=[o for o in owner if o.type=='ARMATURE']
    if len(arms)!=1 or len(arms[0].data.bones)!=65:raise ValueError('Actual65-bone owner required')
    arm=arms[0]
    for track in arm.animation_data.nla_tracks:track.mute=True
    actions=[a for a in bpy.data.actions if a.name.startswith('SUB01_SeatedIdle_upright_footrest')]
    if len(actions)!=1:raise ValueError('Exact candidate action not unique')
    arm.animation_data.action=actions[0]
    if len(actions[0].slots)==1:arm.animation_data.action_slot=actions[0].slots[0]
    else:raise ValueError('Unexpected actual owner animation slots')
    scene.frame_set(60)
    body=bpy.data.objects.new('DiagnosticActualBodyPlacement',None);bpy.context.collection.objects.link(body);body.location=(2.00025,1.998,-.006);body.rotation_euler.z=math.pi
    for o in owner:
        if o.parent is None:o.parent=body
    chair_objects=load(chair);meshes=[o for o in chair_objects if o.type=='MESH']
    if len(meshes)!=1:raise ValueError('Actual single-mesh chair source required')
    c=meshes[0];native=measured['translation_cm'];c.location=(native[0]/100,-native[1]/100,(native[2]+2.5001)/100)
    c.scale=tuple(measured['scale'])
    load(desk)
    foot_objects=load(footrest);placement=bpy.data.objects.new('DiagnosticRigidFootrestPlacement',None);bpy.context.collection.objects.link(placement)
    placement.location.y=-report['params'][10]/100
    for o in foot_objects:
        if o.parent is None:o.parent=placement
    witness=report.get('collision',{}).get('footrest',{}).get('worst_witness')
    if witness:
        point=witness['body_point_ue_cm'];bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=8,radius=.006,location=(point[0]/100,-point[1]/100,point[2]/100))
        marker=bpy.context.object;marker.name='DIAGNOSTIC_ONLY_collision_witness';mat=bpy.data.materials.new('Diagnostic red witness');mat.use_nodes=True;bs=mat.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(.8,.01,.005,1);bs.inputs['Emission Color'].default_value=(.8,.01,.005,1);bs.inputs['Emission Strength'].default_value=1;marker.data.materials.append(mat)
    bpy.ops.mesh.primitive_plane_add(size=4,location=(2.,2.5,.025));ground=bpy.context.object;ground.name='DIAGNOSTIC_ONLY_actual_floor_2p5cm'
    floor=bpy.data.materials.new('Neutral diagnostic ground');floor.diffuse_color=(.19,.19,.19,1);ground.data.materials.append(floor)
    bpy.ops.object.camera_add(location=(3.85,2.45,1.30));camera=bpy.context.object;target=Vector((2.05,2.45,.80));camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.type='ORTHO';camera.data.ortho_scale=2.05;scene.camera=camera
    scene.world=bpy.data.worlds.new('Neutral source diagnostic');scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.5,.5,.5,1);scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.3
    for location,power,size in [((3.,1.,3.),350.,2.),((.5,3.,2.5),200.,2.)]:
        bpy.ops.object.light_add(type='AREA',location=location);light=bpy.context.object;light.data.energy=power;light.data.size=size;light.rotation_euler=(target-light.location).to_track_quat('-Z','Y').to_euler()
    bpy.context.view_layer.update()
    sys.path.insert(0,'/workspace/sub01-home-private/upright-footrest-full-9cd/tools')
    import numpy as np
    import life_gltf as G
    import export_seat_fit_source as E
    names=[E.short(b.name)for b in arm.pose.bones]
    W,_=E.joint_worlds(G.Gltf(Path(report['written_glb'])),names,[2.])
    expected=E.to_ue(W[0,:,:3,3]);expected[:,:2]+=np.asarray([-3.875,32.5])
    actual=np.asarray([[p.x*100,-p.y*100,p.z*100]for p in(arm.matrix_world@b.head for b in arm.pose.bones)])
    error=float(np.max(np.linalg.norm(actual-expected,axis=1)))
    (output/'bone-placement-diagnostic.json').write_text(json.dumps({'action_frame_range':list(actions[0].frame_range),'frame':scene.frame_current,'joint_errors_cm':dict(zip(names,np.linalg.norm(actual-expected,axis=1).tolist())),'actual':actual.tolist(),'expected':expected.tolist()},indent=2))
    if error>.02:raise ValueError('Rendered owner bones differ actual candidate '+str(error))
    chair_min=min((c.matrix_world@v.co).z for v in c.data.vertices)
    if abs(chair_min-.025001)>1e-5:raise ValueError('Rendered chair castors differ actual floor '+str(chair_min))
    bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(output/'upright-source-diagnostic.blend'))
    scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=16;scene.render.resolution_x=960;scene.render.resolution_y=720;scene.render.resolution_percentage=100
    scene.render.filepath=str(output/'upright-source-diagnostic.png');bpy.ops.render.render(write_still=True)
    (output/'source-preview-receipt.json').write_text(json.dumps({'schema':'sub01.upright-source-diagnostic.v1','candidate_sha256':report['written_glb_sha256'],'frame':60,'whole_chair_lift_cm':2.5001,'rigid_footrest_delta_y_cm':report['params'][10],'original65_bones':True,'all65_blender_joint_head_world_error_max_cm':error,'actual_chair_castor_min_z_m':chair_min,'diagnostic_markers_not_production_geometry':True,'native_imported':False,'source_ready':False,'png_sha256':hashlib.sha256((output/'upright-source-diagnostic.png').read_bytes()).hexdigest()},indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in('merged','chair','chair-report','desk','footrest','fit-report','output'):p.add_argument('--'+name,required=True)
    args=sys.argv[sys.argv.index('--')+1:]if '--'in sys.argv else sys.argv[1:];a=p.parse_args(args);render(a.merged,a.chair,a.chair_report,a.desk,a.footrest,a.fit_report,a.output)
