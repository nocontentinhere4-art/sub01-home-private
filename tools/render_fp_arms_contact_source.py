"""Exact skinned source triangles at an iris camera; diagnostic CPU views only."""
import copy,hashlib,json,math,sys,time
from pathlib import Path


def run():
    import bpy
    import numpy as np
    from mathutils import Matrix,Vector
    root=Path('/workspace/sub01-home-private/upright-footrest-full-9cd');sys.path[:0]=[str(root/'tools'),'/home/unreal/runtime-tools','/workspace/sub01-home-private/upright-footrest-python/scipy-1.14.1-cp311']
    import life_gltf as G
    import export_seat_fit_source as E
    import fit_seat_pelvis_pitch as P
    began=time.monotonic();out=Path('/workspace/sub01-home-private/fp-arms-contact-views-r2-uvcorrect');out.mkdir(exist_ok=False)
    candidate=G.Gltf('/workspace/sub01-home-private/fp-arms-candidate-r1/SUB01_FirstPersonArms_SourceCandidate.glb');assert candidate.sha256=='a862cbd3457c2b25da227c0eea2e04dcd8fe1f637115da0ccc69fbcf888ad154'
    report=json.loads(Path('/workspace/sub01-home-private/fp-arms-contact-fit-r2/contact-fit-trial.json').read_text());clip=G.Gltf(report['output_glb']);assert clip.sha256==report['output_sha256'];base=E.Source.load(root/'private-audit/seat-fit-source.npz');iris=json.loads(Path('/workspace/sub01-home-private/fp-arms-candidate-r1/arms-source-packet.json').read_text())
    bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
    def load(path):
        before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(path));return set(bpy.data.objects)-before
    imported=load(candidate.path if hasattr(candidate,'path')else '/workspace/sub01-home-private/fp-arms-candidate-r1/SUB01_FirstPersonArms_SourceCandidate.glb');material=next(m for m in bpy.data.materials if m.name.startswith('tripo_material'))
    for obj in imported:bpy.data.objects.remove(obj,do_unlink=True)
    load('/workspace/sub01-home-private/out/real-office-bundle/desk.glb')
    home=G.Gltf('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb');assert home.sha256=='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b';doc=copy.deepcopy(home.doc)
    for i,node in enumerate(doc['nodes']):
        if i not in (184,185,186,187,237,238):node.pop('mesh',None);node.pop('skin',None)
    doc.pop('animations',None);source_devices=out/'exact-source-devices.glb';G.write_glb(source_devices,doc,bytes(home.buffers[0]));load(source_devices)
    pr=candidate.doc['meshes'][0]['primitives'][0];a=pr['attributes'];index=E.accessor(candidate,pr['indices']).astype(int).reshape(-1,3);ids,inv=np.unique(index,return_inverse=True);faces=inv.reshape(-1,3);pos=E.accessor(candidate,a['POSITION'])[ids];joints=E.accessor(candidate,a['JOINTS_0'])[ids].astype(int);weights=E.accessor(candidate,a['WEIGHTS_0'])[ids];weights/=weights.sum(1,keepdims=True);uv=E.accessor(candidate,a['TEXCOORD_0'])[ids];normal=E.accessor(candidate,a['NORMAL'])[ids]
    mesh=bpy.data.meshes.new('ExactSelectedOriginalArms');mesh.from_pydata(np.zeros((len(ids),3)),[],faces.tolist());mesh.materials.append(material);obj=bpy.data.objects.new('SourceOnly_ExactSkinnedArms',mesh);bpy.context.collection.objects.link(obj);layer=mesh.uv_layers.new(name='OriginalSourceUV')
    for poly in mesh.polygons:
        poly.use_smooth=True
        for li in poly.loop_indices:u,v=uv[mesh.loops[li].vertex_index];layer.data[li].uv=(u,1-v)
    bpy.ops.object.camera_add();camera=bpy.context.object;scene.camera=camera;camera.data.lens_unit='FOV';camera.data.angle=math.radians(75);camera.data.clip_start=.01
    scene.world=bpy.data.worlds.new('Diagnostic studio');scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.5
    for loc,power in [((2.,2.5,2.5),350),((1.,3.5,2.),150)]:
        bpy.ops.object.light_add(type='AREA',location=loc);bpy.context.object.data.energy=power;bpy.context.object.data.size=2
    scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=12;scene.render.resolution_x=960;scene.render.resolution_y=540;scene.render.resolution_percentage=100;rows=[]
    for frame in (45,150,315):
        W,_=E.joint_worlds(clip,base.names,[frame/30]);points=E.to_ue(P.skin_points((pos,joints,weights),base.ibm,W))[0];blender=points*np.asarray([.01,-.01,.01]);mesh.vertices.foreach_set('co',blender.ravel());skin=(W[0]@base.ibm)[joints];n=np.einsum('vkij,vj,vk->vi',np.linalg.inv(skin[:,:,:3,:3]).swapaxes(-1,-2),normal,weights);n=E.to_ue_dir(n)*np.asarray([1.,-1.,1.]);n/=np.linalg.norm(n,axis=1,keepdims=True);mesh.normals_split_custom_set_from_vertices(n.tolist());mesh.update()
        eye=np.asarray(iris['captured_iris_camera_path_ue_cm'][frame]);head=base.names.index('Head');M=W[0,head]@base.ibm[head];f=E.to_ue_dir(M[:3,2]);up=E.to_ue_dir(M[:3,1]);f/=np.linalg.norm(f);up-=f*np.dot(up,f);up/=np.linalg.norm(up);angle=math.radians(35);forward=math.cos(angle)*f-math.sin(angle)*up;forward*=np.asarray([1.,-1.,1.]);camera.location=eye*np.asarray([.01,-.01,.01]);camera.rotation_euler=Vector(forward).to_track_quat('-Z','Y').to_euler();bpy.context.view_layer.update();path=out/f'fps-source-frame{frame:03d}.png';scene.render.filepath=str(path);bpy.ops.render.render(write_still=True);rows.append({'frame':frame,'time_s':frame/30,'camera_actual_source_iris_ue_cm':eye.tolist(),'additional_down_pitch_deg':35,'png':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'mesh_triangles':len(faces),'vertices':len(ids)})
    (out/'source-view-receipt.json').write_text(json.dumps({'schema':'sub01.fp-arms-source-view.v1','clip_sha256':clip.sha256,'arms_mesh_sha256':candidate.sha256,'exact_original_triangles_uv_pbr':True,'preview_uv_convention':'Blender UV=(glTF u,1-glTF v); source GLB UV bytes unchanged','explicit_double_precision_skinning_not_Blender_armature_retarget':True,'diagnostic_studio_not_Game_lighting':True,'source_contact_accepted':False,'native_ready':False,'views':rows,'elapsed_s':time.monotonic()-began},indent=2)+'\n')

if __name__=='__main__':run()
