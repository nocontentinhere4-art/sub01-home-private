"""Private REVIEW ONLY: original arms geometry/rig plus declared derived keyboard loop.

Uses the proven owner/Gaming/Phone FBX coordinate flags. Never imports Unreal,
changes readiness/config, or replaces the canonical full-body owner.
"""
import hashlib,json,math,subprocess,sys,time
from pathlib import Path

MESH_SHA='a862cbd3457c2b25da227c0eea2e04dcd8fe1f637115da0ccc69fbcf888ad154'
CLIP_SHA='0cd1395b0b1d8187c928aeb93950df69abc67f7eeefa91ed1df58c1ea761f5db'


def run(packet,out):
    import bpy,numpy as np
    began=time.monotonic();packet=Path(packet);out=Path(out);out.mkdir(exist_ok=False)
    mesh=Path('/workspace/sub01-home-private/fp-arms-candidate-r1/SUB01_FirstPersonArms_SourceCandidate.glb');clip=Path('/workspace/sub01-home-private/fp-keyboard-loop-r3/SUB01_FirstPersonKeyboard_LoopCandidate.glb')
    assert hashlib.sha256(mesh.read_bytes()).hexdigest()==MESH_SHA and hashlib.sha256(clip.read_bytes()).hexdigest()==CLIP_SHA
    merged=out/'arms-with-keyboard-review.glb';node='/workspace/sub01-home-private/streaming/node-v22.14.0-linux-x64/bin/node';subprocess.run([node,str(packet/'tools/merge_unreal_skin_clips.mjs'),str(mesh),str(merged),str(clip)],check=True,timeout=40)
    root=Path('/workspace/sub01-home-private/upright-footrest-full-9cd');sys.path[:0]=[str(root/'tools'),'/home/unreal/runtime-tools','/workspace/sub01-home-private/upright-footrest-python/scipy-1.14.1-cp311']
    from scipy.spatial import cKDTree
    import life_gltf as G
    import export_seat_fit_source as E
    import fit_seat_pelvis_pitch as P
    source=G.Gltf(merged);names=[source.nodes[i]['name']for i in source.doc['skins'][0]['joints']];assert len(set(names))==65;short=[E.short(n)for n in names];base=E.Source.load(root/'private-audit/seat-fit-source.npz');assert short==base.names;action_name=clip.stem
    bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene;scene.render.fps=120;bpy.ops.import_scene.gltf(filepath=str(merged))
    arms=[o for o in scene.objects if o.type=='ARMATURE'];assert len(arms)==1;arm=arms[0]
    # The glTF importer creates an unskinned42-vertex Icosphere custom bone display.
    # Select only the actual source node with this skin, never that display helper.
    source_mesh_nodes=[n['name']for n in source.nodes if n.get('skin')==0 and 'mesh'in n];assert len(source_mesh_nodes)==1
    meshes=[o for o in scene.objects if o.type=='MESH'and o.name==source_mesh_nodes[0]and any(m.type=='ARMATURE'and m.object==arm for m in o.modifiers)]
    assert len(meshes)==1;body=meshes[0];body.data.calc_loop_triangles();assert len(body.data.loop_triangles)==88592;assert set(arm.data.bones.keys())==set(names)

    for track in arm.animation_data.nla_tracks:track.mute=True
    actions=[a for a in bpy.data.actions if a.name==action_name or a.name.startswith(action_name+'.')];assert len(actions)==1;arm.animation_data.action=actions[0]
    if len(actions[0].slots)==1:arm.animation_data.action_slot=actions[0].slots[0]
    start,end=actions[0].frame_range;start_i,end_i=round(start),round(end);assert abs(start-start_i)<.001 and abs(end-end_i)<.001 and end_i-start_i==408
    scene.frame_start,scene.frame_end=start_i,end_i;frames=list(range(start_i,end_i+1));probe=[0,120,240,396]
    def heads(arm,frames):
        values=[]
        for frame in frames:
            bpy.context.scene.frame_set(round(frame));values.append([tuple((arm.matrix_world@arm.pose.bones[n].matrix).translation)for n in names])
        return np.asarray(values)
    def geometry(obj,frame):
        bpy.context.scene.frame_set(round(frame));bpy.context.view_layer.update();evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());m=evaluated.to_mesh();m.calc_loop_triangles();points=np.asarray([tuple(evaluated.matrix_world@v.co)for v in m.vertices]);faces=np.asarray([t.vertices for t in m.loop_triangles],int);tri=points[faces];uv=np.asarray([[tuple(m.uv_layers.active.data[i].uv)for i in t.loops]for t in m.loop_triangles]);evaluated.to_mesh_clear();return tri,uv
    source_heads=heads(arm,frames);source_geometry=[geometry(body,start_i+i)for i in probe];material_names=[m.name for m in body.data.materials];assert len(material_names)==1
    # Original glTF skin versus Blender import: do not hide per-bone bind incompatibility.
    p=source.doc['meshes'][0]['primitives'][0];a=p['attributes'];indices=E.accessor(source,p['indices']).astype(int).reshape(-1,3);ids,inv=np.unique(indices,return_inverse=True);pos=E.accessor(source,a['POSITION'])[ids];j=E.accessor(source,a['JOINTS_0'])[ids].astype(int);w=E.accessor(source,a['WEIGHTS_0'])[ids];w/=w.sum(1,keepdims=True);W,_=E.joint_worlds(source,short,[i/120 for i in probe]);expected=P.skin_points((pos,j,w),base.ibm,W);expected=expected[:,:,[0,2,1]]*np.asarray([1.,-1.,1.]);expected=expected[:,inv.reshape(-1,3)]
    def compare(reference,target):
        if len(reference)!=len(target):return {'same_triangle_count':False,'source_triangles':len(reference),'target_triangles':len(target)}
        # Full triangle corners, not merely bounds or a vertex cloud. Reordering is allowed.
        tree=cKDTree(reference.mean(1));k=min(8,len(reference));_,which=tree.query(target.mean(1),k=k,workers=1);which=np.asarray(which).reshape(len(target),k);candidate=reference[which];perms=((0,1,2),(0,2,1),(1,0,2),(1,2,0),(2,0,1),(2,1,0));best=np.full((len(target),k),np.inf)
        for perm in perms:best=np.minimum(best,np.linalg.norm(candidate[:,:,perm,:]-target[:,None,:,:],axis=-1).max(-1))
        nearest=best.min(1);return {'same_triangle_count':True,'triangles':len(target),'maximum_nearest_triangle_corner_error_cm':float(nearest.max()*100),'all_triangles_within0_02cm':bool((nearest<=.0002).all()),'comparison':'Every target triangle matched to a source triangle with3corners; original source count preserved; not a uniqueness/UV proof'}
    source_import=[compare(expected[i],source_geometry[i][0])for i in range(len(probe))]
    for obj in scene.objects:obj.select_set(obj==arm or obj==body)
    bpy.context.view_layer.objects.active=arm;scene.frame_set(start_i);bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(out/'first-person-keyboard-review.blend'))
    path=out/'FirstPersonKeyboardReview.fbx';bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,object_types={'ARMATURE','MESH'},add_leaf_bones=False,use_armature_deform_only=False,use_mesh_modifiers=False,apply_unit_scale=True,axis_forward='-Z',axis_up='Y',bake_anim=True,bake_anim_use_all_actions=False,bake_anim_use_nla_strips=False,bake_anim_simplify_factor=0,bake_anim_step=1,path_mode='COPY',embed_textures=True)
    bpy.ops.wm.read_factory_settings(use_empty=True);bpy.context.scene.render.fps=120;bpy.ops.import_scene.fbx(filepath=str(path),use_anim=True);arms=[o for o in bpy.context.scene.objects if o.type=='ARMATURE'];meshes=[o for o in bpy.context.scene.objects if o.type=='MESH'];assert len(arms)==1 and len(meshes)==1;arm=arms[0];body=meshes[0];assert set(arm.data.bones.keys())==set(names)
    curves=[]
    for action in bpy.data.actions:
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:curves.extend(bag.fcurves)
    counts=sorted(set(len(c.keyframe_points)for c in curves));assert counts==[409],counts;times=sorted(set(round(float(p.co.x),5)for c in curves for p in c.keyframe_points));assert len(times)==409 and abs(times[-1]-times[0]-408)<.001;actual_heads=heads(arm,times);head_error=float(np.linalg.norm(actual_heads-source_heads,axis=-1).max()*100);assert head_error<=.02
    parity=[compare(source_geometry[i][0],geometry(body,times[0]+frame)[0])for i,frame in enumerate(probe)]
    report={'schema':'sub01.fp-keyboard-review-fbx.v1','label':'Private native visual/skin-contact DIAGNOSTIC candidate only','arms_mesh_glb_sha256':MESH_SHA,'derived_clip_sha256':CLIP_SHA,'merged_glb_sha256':source.sha256,'fbx_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'fbx':str(path),'editable_blend':str(out/'first-person-keyboard-review.blend'),'original_joint_names':names,'original_joints':65,'fps':120,'keys':409,'duration_s':3.4,'source_frame_range':[start_i,end_i],'actual_roundtrip_frame_range':[times[0],times[-1]],'actual_roundtrip_curve_counts':counts,'actual_roundtrip_curves':len(curves),'all409_keys_all65_joint_heads_max_error_cm':head_error,'original_source_material_slots':material_names,'source_GLTF_to_Blender_skin_geometry':source_import,'FBX_roundtrip_skin_geometry':parity,'probe_frames':probe,'elapsed_s':time.monotonic()-began,'source_ready':False,'native_ready':False,'activity_ready':False,'source_native_skeleton_mutated':False,'limitations':['4extra240Hz hover diagnostics up0.276cm remain explicitlyunaccepted','Keyboard housing/proximal contacts are diagnostic observations, not blanket fullcontact acceptance','Mesh exported with exact original names; actual existing66UEskeleton/skin/material binding must be checked by sole Editor owner','No full-take/mouse/body/seat readiness claim']};(out/'keyboard-review-fbx-roundtrip.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)

if __name__=='__main__':
    args=sys.argv[sys.argv.index('--')+1:];run(args[0],args[1])
