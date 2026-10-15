"""CPU-only fixed-camera source motion views; never native visual acceptance."""
import hashlib
import json
import sys
from pathlib import Path


def run():
    import bpy
    import numpy as np
    sys.path.insert(0,'/workspace/sub01-home-private/upright-footrest-full-9cd/tools')
    import export_seat_fit_source as E
    import life_gltf as G
    out=Path('/workspace/sub01-home-private/upright-transition-preview-r12/uid1001/output');bpy.ops.wm.open_mainfile(filepath=str(out/'upright-source-diagnostic.blend'));scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=16;scene.render.resolution_x=960;scene.render.resolution_y=720;scene.render.resolution_percentage=100
    body=bpy.data.objects['DiagnosticActualBodyPlacement'];arm=next(o for o in body.children_recursive if o.type=='ARMATURE');names=[E.short(b.name)for b in arm.pose.bones];clip=G.Gltf('/workspace/sub01-home-private/upright-transition-sit-r12/SUB01_SitDown_upright_footrest.glb');assert clip.sha256=='3da7b1f46a7e503f1bea8c3f33a07cdbcf8d931924dbe3a39c1be5123d9700ea';rows=[]
    for frame in [0,52,78]:
        scene.frame_set(frame);bpy.context.view_layer.update();W,_=E.joint_worlds(clip,names,[frame/30]);expected=E.to_ue(W[0,:,:3,3]);expected[:,:2]+=np.asarray([-3.875,32.5]);actual=np.asarray([[p.x*100,-p.y*100,p.z*100]for p in(arm.matrix_world@b.head for b in arm.pose.bones)]);error=float(np.linalg.norm(actual-expected,axis=1).max());assert error<.02
        path=out/f'source-phase-frame{frame:03d}.png';scene.render.filepath=str(path);bpy.ops.render.render(write_still=True);rows.append({'blender_frame':frame,'source_time_s':frame/30,'written65_joint_head_error_max_cm':error,'png':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    (out/'sequence-preview-receipt.json').write_text(json.dumps({'schema':'sub01.upright-source-sequence-preview.v1','clip_sha256':clip.sha256,'owner_sha256':'831790a62b81e7e2faa5a201e04740d0911c5bfebd49aa03b124808521e3a2b1','same_fixed_camera':True,'diagnostic_studio_lights_not_Game':True,'frames':rows,'native_imported':False,'source_ready':False},indent=2)+'\n')

if __name__=='__main__':run()
